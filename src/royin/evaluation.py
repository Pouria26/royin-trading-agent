"""Evaluation, replay, benchmarking, and causal ablation harnesses for AI decisions."""

import hashlib
import json
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, replace
from decimal import Decimal
from pathlib import Path
from typing import Any

from royin.agent import SYSTEM_INSTRUCTIONS, decide
from royin.broker import PaperBroker
from royin.config import RuntimeConfig
from royin.decision import Decision, DecisionProposal, bind_decision
from royin.features import FeatureSnapshot, extract_features
from royin.ledger import Ledger, validate_decimal
from royin.logger import AuditLogger
from royin.market_data import Candle, CandleSeries, decimal_number
from royin.markets import load_restrictions
from royin.risk import MarketRules, RiskPolicy, evaluate_risk


@dataclass(frozen=True)
class EvaluationTrace:
    decision: Decision
    snapshot: FeatureSnapshot
    wall_seconds: float
    is_ai: bool


def always_wait_decision(snapshot: FeatureSnapshot, decision_id: str | None = None) -> Decision:
    """Cash baseline: Always WAIT, preserving 100% capital with zero fees and zero drawdown."""
    did = decision_id or f"wait_{snapshot.cutoff}"
    return Decision(
        decision_id=did,
        symbol=snapshot.symbol,
        action="WAIT",
        cutoff=snapshot.cutoff,
        snapshot_sha256=snapshot.snapshot_sha256,
        evidence_ids=("EV_DATA_FRESH",),
        reason="Cash baseline: preserve 100% capital in risk-free cash",
        invalidation="None",
    )


def buy_and_hold_decision(snapshot: FeatureSnapshot, decision_id: str | None = None) -> Decision:
    """Buy and hold baseline: Enters on the first available bar, then holds to track underlying asset."""
    did = decision_id or f"bnh_{snapshot.cutoff}"
    has_position = snapshot.current_position_base > Decimal(0)
    if not has_position:
        proposal = DecisionProposal(
            action="ENTER",
            evidence_ids=("EV_DATA_FRESH", "EV_POSITION_FLAT"),
            reason="Buy and Hold: initial entry to track underlying asset",
            invalidation="Never",
        )
    else:
        proposal = DecisionProposal(
            action="WAIT",
            evidence_ids=("EV_DATA_FRESH", "EV_POSITION_LONG"),
            reason="Buy and Hold: holding long position passively",
            invalidation="Never",
        )
    return bind_decision(
        proposal,
        decision_id=did,
        symbol=snapshot.symbol,
        cutoff=snapshot.cutoff,
        snapshot_sha256=snapshot.snapshot_sha256,
        available_evidence_ids=frozenset(snapshot.evidences.keys()),
    )


def baseline_rule_decision(
    snapshot: FeatureSnapshot,
    *,
    decision_id: str | None = None,
    allowed_symbols: Sequence[str] = ("USDTTMN",),
) -> Decision:
    """Deterministic naive crossover baseline without fee-hurdle awareness."""
    did = decision_id or f"base_{snapshot.cutoff}"
    if snapshot.symbol not in allowed_symbols:
        return Decision(
            decision_id=did,
            symbol=snapshot.symbol,
            action="WAIT",
            cutoff=snapshot.cutoff,
            snapshot_sha256=snapshot.snapshot_sha256,
            evidence_ids=("EV_DATA_FRESH",),
            reason=f"Baseline WAIT: Symbol {snapshot.symbol} outside allowed universe",
            invalidation="Allowlist update",
        )

    has_position = snapshot.current_position_base > Decimal(0)

    # Bullish entry condition
    if not has_position and "EV_TREND_BULLISH" in snapshot.evidences:
        proposal = DecisionProposal(
            action="ENTER",
            evidence_ids=("EV_TREND_BULLISH", "EV_POSITION_FLAT"),
            reason="Baseline rule ENTER on bullish SMA crossover",
            invalidation="Fast SMA crosses below slow SMA",
        )
    # Bearish or overbought exit condition
    elif has_position and (
        "EV_TREND_BEARISH" in snapshot.evidences or "EV_RSI_OVERBOUGHT" in snapshot.evidences
    ):
        exit_evs = []
        if "EV_TREND_BEARISH" in snapshot.evidences:
            exit_evs.append("EV_TREND_BEARISH")
        if "EV_RSI_OVERBOUGHT" in snapshot.evidences:
            exit_evs.append("EV_RSI_OVERBOUGHT")
        exit_evs.append("EV_POSITION_LONG")
        proposal = DecisionProposal(
            action="EXIT",
            evidence_ids=tuple(exit_evs),
            reason="Baseline rule EXIT on trend reversal or overbought RSI",
            invalidation="RSI drops back to neutral",
        )
    else:
        proposal = DecisionProposal(
            action="WAIT",
            evidence_ids=(
                "EV_DATA_FRESH",
                "EV_POSITION_LONG" if has_position else "EV_POSITION_FLAT",
            ),
            reason="Baseline rule WAIT: No breakout or exit signal triggered",
            invalidation="Next candle close",
        )

    return bind_decision(
        proposal,
        decision_id=did,
        symbol=snapshot.symbol,
        cutoff=snapshot.cutoff,
        snapshot_sha256=snapshot.snapshot_sha256,
        available_evidence_ids=frozenset(snapshot.evidences.keys()),
        allowed_symbols=frozenset(allowed_symbols),
    )


def conviction_fee_aware_decision(
    snapshot: FeatureSnapshot,
    *,
    decision_id: str | None = None,
    allowed_symbols: Sequence[str] = ("USDTTMN",),
    min_spread_pct: Decimal = Decimal("0.005"),  # 0.5% SMA spread hurdle
    min_atr_pct: Decimal = Decimal("0.006"),  # 0.6% ATR volatility hurdle
) -> Decision:
    """Conviction-filtered strategy: Only enters when trend and volatility comfortably exceed round-trip fees (0.60%)."""
    did = decision_id or f"conv_{snapshot.cutoff}"
    if snapshot.symbol not in allowed_symbols:
        return always_wait_decision(snapshot, did)

    has_position = snapshot.current_position_base > Decimal(0)

    # Calculate spreads and ratios
    sma_spread = (
        (snapshot.trend_sma_fast - snapshot.trend_sma_slow) / snapshot.trend_sma_slow
        if snapshot.trend_sma_slow > Decimal(0)
        else Decimal(0)
    )
    atr_pct = (
        snapshot.atr_14 / snapshot.last_close if snapshot.last_close > Decimal(0) else Decimal(0)
    )

    if not has_position:
        # High conviction entry condition:
        # 1. Bullish SMA with spread >= hurdle
        # 2. Volatility ATR >= hurdle to guarantee profit potential > fee
        # 3. RSI between 45 and 68 (not extreme overbought)
        # 4. Volume ratio >= 1.05
        is_bullish = "EV_TREND_BULLISH" in snapshot.evidences and sma_spread >= min_spread_pct
        has_volatility = atr_pct >= min_atr_pct
        rsi_healthy = Decimal("45") <= snapshot.rsi_14 <= Decimal("68")
        vol_healthy = snapshot.volume_ratio >= Decimal("1.05")

        if is_bullish and has_volatility and rsi_healthy and vol_healthy:
            proposal = DecisionProposal(
                action="ENTER",
                evidence_ids=("EV_TREND_BULLISH", "EV_POSITION_FLAT"),
                reason=f"Conviction ENTER: SMA spread {sma_spread * 100:.2f}% and ATR {atr_pct * 100:.2f}% clear 0.6% fee hurdle",
                invalidation=f"Price drops below Fast SMA {snapshot.trend_sma_fast}",
            )
        else:
            proposal = DecisionProposal(
                action="WAIT",
                evidence_ids=("EV_DATA_FRESH", "EV_POSITION_FLAT"),
                reason="Conviction WAIT: Market does not meet minimum fee hurdle or volume criteria",
                invalidation="Breakout with volume surge",
            )
    else:
        # Exit when trend reverses or strong overbought RSI occurs
        is_reversal = "EV_TREND_BEARISH" in snapshot.evidences or sma_spread < Decimal(0)
        is_overbought = snapshot.rsi_14 >= Decimal("75")
        if is_reversal or is_overbought:
            proposal = DecisionProposal(
                action="EXIT",
                evidence_ids=(
                    "EV_TREND_BEARISH" if is_reversal else "EV_RSI_OVERBOUGHT",
                    "EV_POSITION_LONG",
                ),
                reason="Conviction EXIT: Trend momentum exhausted or RSI overbought",
                invalidation="New high breakout",
            )
        else:
            proposal = DecisionProposal(
                action="WAIT",
                evidence_ids=("EV_DATA_FRESH", "EV_POSITION_LONG"),
                reason="Conviction WAIT: Trend remains favorable, riding position",
                invalidation="Stop-loss hit",
            )

    return bind_decision(
        proposal,
        decision_id=did,
        symbol=snapshot.symbol,
        cutoff=snapshot.cutoff,
        snapshot_sha256=snapshot.snapshot_sha256,
        available_evidence_ids=frozenset(snapshot.evidences.keys()),
        allowed_symbols=frozenset(allowed_symbols),
    )


def build_candidate_producer(
    config: dict[str, Any],
    allowed_symbols: Sequence[str] = ("USDTTMN",),
) -> Callable[[FeatureSnapshot], Decision]:
    """Factory creating deterministic Decision producer for a frozen candidate configuration."""
    if (
        not isinstance(config, dict)
        or not isinstance(config.get("id"), str)
        or not config["id"].strip()
    ):
        raise ValueError("Candidate needs a nonempty ID")
    if config.get("family") == "trend":
        if set(config) != {"id", "family", "sma_spread"}:
            raise ValueError("Unknown trend configuration fields")
        if decimal_number(config["sma_spread"]) >= 1:
            raise ValueError("SMA spread must be a ratio below one")
    elif config.get("family") == "mean_reversion":
        if set(config) != {"id", "family", "rsi_entry", "rsi_exit"}:
            raise ValueError("Unknown reversion configuration fields")
        entry, exit_ = decimal_number(config["rsi_entry"]), decimal_number(config["rsi_exit"])
        if not 0 <= entry < exit_ <= 100:
            raise ValueError("RSI thresholds must be ordered within 0..100")
    elif config.get("family") == "volatility_breakout":
        if set(config) != {"id", "family", "atr_hurdle", "min_spread", "rsi_exit"}:
            raise ValueError("Unknown volatility_breakout configuration fields")
        atr_h = decimal_number(config["atr_hurdle"])
        min_sp = decimal_number(config["min_spread"])
        rsi_ex = decimal_number(config["rsi_exit"])
        if not (0 < atr_h < 1 and 0 <= min_sp < 1 and 50 < rsi_ex <= 100):
            raise ValueError("Invalid volatility_breakout parameters")
    elif config.get("family") == "regime_momentum":
        if set(config) != {
            "id",
            "family",
            "sma_spread",
            "min_volume_ratio",
            "rsi_entry_max",
            "rsi_exit",
        }:
            raise ValueError("Unknown regime_momentum configuration fields")
        sma_sp = decimal_number(config["sma_spread"])
        min_vr = decimal_number(config["min_volume_ratio"])
        rsi_max_in = decimal_number(config["rsi_entry_max"])
        rsi_ex = decimal_number(config["rsi_exit"])
        if not (0 <= sma_sp < 1 and min_vr >= 1 and 40 < rsi_max_in < rsi_ex <= 100):
            raise ValueError("Invalid regime_momentum parameters")
    else:
        raise ValueError("Unknown candidate family")
    family = config["family"]
    config_id = config["id"]

    if family == "trend":
        sma_spread_hurdle = Decimal(str(config["sma_spread"]))

        def trend_producer(snapshot: FeatureSnapshot) -> Decision:
            did = f"{config_id}_{snapshot.cutoff}"
            if snapshot.symbol not in allowed_symbols:
                return always_wait_decision(snapshot, did)

            has_position = snapshot.current_position_base > Decimal(0)
            sma_spread = (
                (snapshot.trend_sma_fast - snapshot.trend_sma_slow) / snapshot.trend_sma_slow
                if snapshot.trend_sma_slow > Decimal(0)
                else Decimal(0)
            )

            if not has_position:
                if "EV_TREND_BULLISH" in snapshot.evidences and sma_spread >= sma_spread_hurdle:
                    proposal = DecisionProposal(
                        action="ENTER",
                        evidence_ids=("EV_TREND_BULLISH", "EV_POSITION_FLAT"),
                        reason=f"Candidate {config_id} ENTER on bullish SMA spread {sma_spread:.4f} >= {sma_spread_hurdle}",
                        invalidation="Price drops below fast SMA",
                    )
                else:
                    proposal = DecisionProposal(
                        action="WAIT",
                        evidence_ids=("EV_DATA_FRESH", "EV_POSITION_FLAT"),
                        reason=f"Candidate {config_id} WAIT: SMA spread {sma_spread:.4f} below hurdle {sma_spread_hurdle}",
                        invalidation="Bullish crossover with required spread",
                    )
            else:
                if (
                    "EV_TREND_BEARISH" in snapshot.evidences
                    or sma_spread < Decimal(0)
                    or "EV_RSI_OVERBOUGHT" in snapshot.evidences
                ):
                    evs = ["EV_POSITION_LONG"]
                    if "EV_TREND_BEARISH" in snapshot.evidences:
                        evs.append("EV_TREND_BEARISH")
                    if "EV_RSI_OVERBOUGHT" in snapshot.evidences:
                        evs.append("EV_RSI_OVERBOUGHT")
                    proposal = DecisionProposal(
                        action="EXIT",
                        evidence_ids=tuple(evs),
                        reason=f"Candidate {config_id} EXIT on trend reversal or overbought RSI",
                        invalidation="Regime stabilizes",
                    )
                else:
                    proposal = DecisionProposal(
                        action="WAIT",
                        evidence_ids=("EV_DATA_FRESH", "EV_POSITION_LONG"),
                        reason=f"Candidate {config_id} WAIT: Holding trend position",
                        invalidation="Stop-loss or trend breach",
                    )

            return bind_decision(
                proposal,
                decision_id=did,
                symbol=snapshot.symbol,
                cutoff=snapshot.cutoff,
                snapshot_sha256=snapshot.snapshot_sha256,
                available_evidence_ids=frozenset(snapshot.evidences.keys()),
                allowed_symbols=frozenset(allowed_symbols),
            )

        return trend_producer

    elif family == "mean_reversion":
        rsi_entry = Decimal(str(config["rsi_entry"]))
        rsi_exit = Decimal(str(config["rsi_exit"]))

        def reversion_producer(snapshot: FeatureSnapshot) -> Decision:
            did = f"{config_id}_{snapshot.cutoff}"
            if snapshot.symbol not in allowed_symbols:
                return always_wait_decision(snapshot, did)

            has_position = snapshot.current_position_base > Decimal(0)

            if not has_position:
                if snapshot.rsi_14 <= rsi_entry:
                    proposal = DecisionProposal(
                        action="ENTER",
                        evidence_ids=("EV_DATA_FRESH", "EV_POSITION_FLAT"),
                        reason=f"Candidate {config_id} ENTER: Oversold RSI {snapshot.rsi_14:.1f} <= {rsi_entry}",
                        invalidation="RSI fails to bounce",
                    )
                else:
                    proposal = DecisionProposal(
                        action="WAIT",
                        evidence_ids=("EV_DATA_FRESH", "EV_POSITION_FLAT"),
                        reason=f"Candidate {config_id} WAIT: RSI {snapshot.rsi_14:.1f} > entry threshold {rsi_entry}",
                        invalidation="Oversold dip",
                    )
            else:
                if snapshot.rsi_14 >= rsi_exit:
                    proposal = DecisionProposal(
                        action="EXIT",
                        evidence_ids=("EV_DATA_FRESH", "EV_POSITION_LONG"),
                        reason=f"Candidate {config_id} EXIT: Reversion target reached RSI {snapshot.rsi_14:.1f} >= {rsi_exit}",
                        invalidation="New downward wave",
                    )
                else:
                    proposal = DecisionProposal(
                        action="WAIT",
                        evidence_ids=("EV_DATA_FRESH", "EV_POSITION_LONG"),
                        reason=f"Candidate {config_id} WAIT: Holding until RSI reaches {rsi_exit}",
                        invalidation="Stop loss hit",
                    )

            return bind_decision(
                proposal,
                decision_id=did,
                symbol=snapshot.symbol,
                cutoff=snapshot.cutoff,
                snapshot_sha256=snapshot.snapshot_sha256,
                available_evidence_ids=frozenset(snapshot.evidences.keys()),
                allowed_symbols=frozenset(allowed_symbols),
            )

        return reversion_producer

    elif family == "volatility_breakout":
        atr_hurdle = Decimal(str(config["atr_hurdle"]))
        min_spread = Decimal(str(config["min_spread"]))
        rsi_exit = Decimal(str(config["rsi_exit"]))

        def breakout_producer(snapshot: FeatureSnapshot) -> Decision:
            did = f"{config_id}_{snapshot.cutoff}"
            if snapshot.symbol not in allowed_symbols:
                return always_wait_decision(snapshot, did)

            has_position = snapshot.current_position_base > Decimal(0)
            sma_spread = (
                (snapshot.trend_sma_fast - snapshot.trend_sma_slow) / snapshot.trend_sma_slow
                if snapshot.trend_sma_slow > Decimal(0)
                else Decimal(0)
            )
            atr_pct = (
                snapshot.atr_14 / snapshot.last_close
                if snapshot.last_close > Decimal(0)
                else Decimal(0)
            )

            if not has_position:
                is_bullish = "EV_TREND_BULLISH" in snapshot.evidences and sma_spread >= min_spread
                vol_expansion = atr_pct >= atr_hurdle
                rsi_not_extreme = snapshot.rsi_14 <= Decimal("70")
                if is_bullish and vol_expansion and rsi_not_extreme:
                    proposal = DecisionProposal(
                        action="ENTER",
                        evidence_ids=("EV_TREND_BULLISH", "EV_POSITION_FLAT"),
                        reason=f"Candidate {config_id} ENTER on breakout with ATR expansion {atr_pct * 100:.2f}% >= {atr_hurdle * 100:.2f}% and spread {sma_spread * 100:.2f}%",
                        invalidation="Price drops below fast SMA",
                    )
                else:
                    proposal = DecisionProposal(
                        action="WAIT",
                        evidence_ids=("EV_DATA_FRESH", "EV_POSITION_FLAT"),
                        reason=f"Candidate {config_id} WAIT: ATR expansion {atr_pct * 100:.2f}% or spread {sma_spread * 100:.2f}% below hurdle",
                        invalidation="Volatility surge and trend breakout",
                    )
            else:
                if (
                    "EV_TREND_BEARISH" in snapshot.evidences
                    or sma_spread < Decimal(0)
                    or snapshot.rsi_14 >= rsi_exit
                ):
                    evs = ["EV_POSITION_LONG"]
                    if "EV_TREND_BEARISH" in snapshot.evidences:
                        evs.append("EV_TREND_BEARISH")
                    if snapshot.rsi_14 >= rsi_exit:
                        evs.append("EV_RSI_OVERBOUGHT")
                    proposal = DecisionProposal(
                        action="EXIT",
                        evidence_ids=tuple(evs),
                        reason=f"Candidate {config_id} EXIT on trend breakdown or RSI {snapshot.rsi_14:.1f} >= {rsi_exit}",
                        invalidation="Trend continuation",
                    )
                else:
                    proposal = DecisionProposal(
                        action="WAIT",
                        evidence_ids=("EV_DATA_FRESH", "EV_POSITION_LONG"),
                        reason=f"Candidate {config_id} WAIT: Holding volatility breakout position",
                        invalidation="Stop-loss or momentum reversal",
                    )

            return bind_decision(
                proposal,
                decision_id=did,
                symbol=snapshot.symbol,
                cutoff=snapshot.cutoff,
                snapshot_sha256=snapshot.snapshot_sha256,
                available_evidence_ids=frozenset(snapshot.evidences.keys()),
                allowed_symbols=frozenset(allowed_symbols),
            )

        return breakout_producer

    elif family == "regime_momentum":
        sma_spread_hurdle = Decimal(str(config["sma_spread"]))
        min_volume_ratio = Decimal(str(config["min_volume_ratio"]))
        rsi_entry_max = Decimal(str(config["rsi_entry_max"]))
        rsi_exit = Decimal(str(config["rsi_exit"]))

        def regime_producer(snapshot: FeatureSnapshot) -> Decision:
            did = f"{config_id}_{snapshot.cutoff}"
            if snapshot.symbol not in allowed_symbols:
                return always_wait_decision(snapshot, did)

            has_position = snapshot.current_position_base > Decimal(0)
            sma_spread = (
                (snapshot.trend_sma_fast - snapshot.trend_sma_slow) / snapshot.trend_sma_slow
                if snapshot.trend_sma_slow > Decimal(0)
                else Decimal(0)
            )

            if not has_position:
                is_bullish = (
                    "EV_TREND_BULLISH" in snapshot.evidences and sma_spread >= sma_spread_hurdle
                )
                vol_surge = snapshot.volume_ratio >= min_volume_ratio
                rsi_in_range = Decimal("45") <= snapshot.rsi_14 <= rsi_entry_max
                if is_bullish and vol_surge and rsi_in_range:
                    proposal = DecisionProposal(
                        action="ENTER",
                        evidence_ids=("EV_TREND_BULLISH", "EV_POSITION_FLAT"),
                        reason=f"Candidate {config_id} ENTER on regime momentum spread {sma_spread * 100:.2f}% and volume ratio {snapshot.volume_ratio:.2f}x",
                        invalidation="Spread collapses below hurdle or volume dries up",
                    )
                else:
                    proposal = DecisionProposal(
                        action="WAIT",
                        evidence_ids=("EV_DATA_FRESH", "EV_POSITION_FLAT"),
                        reason=f"Candidate {config_id} WAIT: Regime momentum criteria not met",
                        invalidation="Volume surge with bullish spread",
                    )
            else:
                if (
                    "EV_TREND_BEARISH" in snapshot.evidences
                    or sma_spread < Decimal(0)
                    or snapshot.rsi_14 >= rsi_exit
                ):
                    evs = ["EV_POSITION_LONG"]
                    if "EV_TREND_BEARISH" in snapshot.evidences:
                        evs.append("EV_TREND_BEARISH")
                    if snapshot.rsi_14 >= rsi_exit:
                        evs.append("EV_RSI_OVERBOUGHT")
                    proposal = DecisionProposal(
                        action="EXIT",
                        evidence_ids=tuple(evs),
                        reason=f"Candidate {config_id} EXIT on momentum reversal or RSI {snapshot.rsi_14:.1f} >= {rsi_exit}",
                        invalidation="New breakout surge",
                    )
                else:
                    proposal = DecisionProposal(
                        action="WAIT",
                        evidence_ids=("EV_DATA_FRESH", "EV_POSITION_LONG"),
                        reason=f"Candidate {config_id} WAIT: Holding regime momentum position",
                        invalidation="Stop-loss or trend breach",
                    )

            return bind_decision(
                proposal,
                decision_id=did,
                symbol=snapshot.symbol,
                cutoff=snapshot.cutoff,
                snapshot_sha256=snapshot.snapshot_sha256,
                available_evidence_ids=frozenset(snapshot.evidences.keys()),
                allowed_symbols=frozenset(allowed_symbols),
            )

        return regime_producer

    else:
        raise ValueError(f"Unknown candidate family: {family}")


def evaluate_candidate_configurations(
    candles: Sequence[Candle],
    rules: MarketRules,
    policy: RiskPolicy,
    configurations: Sequence[dict[str, Any]],
    *,
    initial_capital: Decimal = Decimal("5000000"),
    interval_seconds: int = 900,
    **simulation_kwargs,
) -> dict[str, dict[str, Any]]:
    """Evaluate a set of candidate configurations on identical candles."""
    if not configurations or len({c["id"] for c in configurations}) != len(configurations):
        raise ValueError("Candidate configurations must be nonempty and unique")
    results = {}
    for cfg in configurations:
        cid = cfg["id"]
        producer = build_candidate_producer(cfg, allowed_symbols=(rules.symbol,))
        res = run_simulation(
            candles,
            producer,
            rules,
            policy,
            initial_capital=initial_capital,
            interval_seconds=interval_seconds,
            **simulation_kwargs,
        )
        res["config_id"] = cid
        res["family"] = cfg["family"]
        results[cid] = res
    return results


def rank_and_select_candidate(
    development_results: Sequence[dict[str, dict[str, Any]]],
    configurations: Sequence[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Rank candidate configurations across development windows and select the best candidate.

    Ranking protocol:
    1. Highest worst-window net return (%)
    2. Highest aggregate net return (%)
    3. Lowest maximum drawdown (%)
    4. Alphabetical on config id (tie-breaker)
    """
    if not development_results or not configurations:
        raise ValueError("No development observations; ranking would invent a winner")
    ids = {c["id"] for c in configurations}
    if len(ids) != len(configurations) or any(set(w) != ids for w in development_results):
        raise ValueError("Each window must contain every unique candidate")
    ranked = []
    for cfg in configurations:
        cid = cfg["id"]
        window_returns = [Decimal(str(w[cid]["net_return_pct"])) for w in development_results]
        window_dds = [Decimal(str(w[cid]["max_drawdown_pct"])) for w in development_results]

        if any(not v.is_finite() for v in window_returns + window_dds) or any(
            v < 0 for v in window_dds
        ):
            raise ValueError("Invalid window metrics")
        worst_window_ret = min(window_returns)
        aggregate_ret = sum(window_returns, Decimal(0))
        max_dd = max(window_dds) if window_dds else Decimal(0)

        ranked.append(
            {
                "config_id": cid,
                "family": cfg["family"],
                "worst_window_net_return_pct": str(worst_window_ret),
                "aggregate_net_return_pct": str(aggregate_ret),
                "max_drawdown_pct": str(max_dd),
                "_sort_key": (-worst_window_ret, -aggregate_ret, max_dd, cid),
            }
        )

    ranked.sort(key=lambda x: x["_sort_key"])
    selected_id = ranked[0]["config_id"]
    for r in ranked:
        del r["_sort_key"]
    return selected_id, ranked


async def replay_snapshots(
    snapshots: Sequence[FeatureSnapshot],
    *,
    config: RuntimeConfig,
    budget=None,
    client=None,
    allowed_symbols: Sequence[str] = ("USDTTMN",),
) -> list[EvaluationTrace]:
    """Replay evaluation over a series of snapshots recording decisions and latency."""
    traces = []
    for i, snap in enumerate(snapshots):
        started = time.monotonic()
        decision = await decide(
            snap,
            config=config,
            budget=budget,
            client=client,
            allowed_symbols=allowed_symbols,
            decision_id=f"rep_{snap.cutoff}_{i:04d}",
        )
        elapsed = round(time.monotonic() - started, 4)
        traces.append(
            EvaluationTrace(
                decision=decision,
                snapshot=snap,
                wall_seconds=elapsed,
                is_ai=client is None,
            )
        )
    return traces


def run_ablation_comparison(
    snapshots: Sequence[FeatureSnapshot],
    ai_decisions: Sequence[Decision],
    *,
    allowed_symbols: Sequence[str] = ("USDTTMN",),
) -> dict:
    """Compare AI decisions against baseline rules on identical snapshots."""
    if len(snapshots) != len(ai_decisions):
        raise ValueError("Snapshots and AI decisions count must match")

    total = len(snapshots)
    agreements = 0
    divergences = []

    for snap, ai_dec in zip(snapshots, ai_decisions, strict=True):
        if (ai_dec.snapshot_sha256, ai_dec.symbol, ai_dec.cutoff) != (
            snap.snapshot_sha256,
            snap.symbol,
            snap.cutoff,
        ):
            raise ValueError("Ablation decision/snapshot state mismatch")
        base_dec = baseline_rule_decision(
            snap,
            decision_id=f"base_{snap.cutoff}",
            allowed_symbols=allowed_symbols,
        )
        if ai_dec.action == base_dec.action:
            agreements += 1
        else:
            divergences.append(
                {
                    "cutoff": snap.cutoff,
                    "symbol": snap.symbol,
                    "ai_action": ai_dec.action,
                    "ai_reason": ai_dec.reason,
                    "baseline_action": base_dec.action,
                    "baseline_reason": base_dec.reason,
                }
            )

    return {
        "total_evaluations": total,
        "action_agreements": agreements,
        "agreement_rate": round(agreements / total, 4) if total > 0 else 1.0,
        "divergences_count": len(divergences),
        "divergences": divergences,
    }


def verify_decision_causality(
    full_series: CandleSeries,
    prefix_series: CandleSeries,
    symbol: str,
    cutoff: int,
    recorded_proposal: DecisionProposal,
) -> tuple[bool, Decision, Decision]:
    """Verify that decisions are strictly invariant to future data given a fixed proposal."""
    snap_full = extract_features(full_series, symbol, cutoff=cutoff)
    snap_prefix = extract_features(prefix_series, symbol, cutoff=cutoff)

    dec_full = bind_decision(
        recorded_proposal,
        decision_id="causal_full",
        symbol=symbol,
        cutoff=cutoff,
        snapshot_sha256=snap_full.snapshot_sha256,
        available_evidence_ids=frozenset(snap_full.evidences.keys()),
    )
    dec_prefix = bind_decision(
        recorded_proposal,
        decision_id="causal_prefix",
        symbol=symbol,
        cutoff=cutoff,
        snapshot_sha256=snap_prefix.snapshot_sha256,
        available_evidence_ids=frozenset(snap_prefix.evidences.keys()),
    )

    is_identical = (
        snap_full.snapshot_sha256 == snap_prefix.snapshot_sha256
        and dec_full.snapshot_sha256 == dec_prefix.snapshot_sha256
        and dec_full.action == dec_prefix.action
        and dec_full.evidence_ids == dec_prefix.evidence_ids
    )
    return is_identical, dec_full, dec_prefix


def position_metrics(ledger: Ledger, rules: MarketRules) -> dict:
    """One trade is a flat-to-flat inventory episode, including all partial exits and fees."""
    quantity = cost = episode_pnl = Decimal(0)
    completed, episodes, episode_fills = [], [], []
    buys = sells = 0
    with ledger.connection() as db:
        rows = db.execute(
            "SELECT i.side,f.price,f.quantity,f.fee,f.fee_asset,f.fill_id,f.timestamp FROM fills f "
            "JOIN order_intents i ON i.client_id=f.client_id ORDER BY f.rowid"
        ).fetchall()
    for side, price, qty, fee, asset, fill_id, timestamp in rows:
        episode_fills.append({"fill_id": fill_id, "timestamp": timestamp})
        price, qty, fee = Decimal(price), Decimal(qty), Decimal(fee)
        if side == "BUY":
            buys += 1
            quantity += qty - (fee if asset == rules.base_asset else 0)
            cost += price * qty + (fee if asset == rules.quote_asset else 0)
        else:
            sells += 1
            consumed = qty + (fee if asset == rules.base_asset else 0)
            allocated = cost if consumed == quantity else cost * consumed / quantity
            episode_pnl += price * qty - (fee if asset == rules.quote_asset else 0) - allocated
            quantity -= consumed
            cost -= allocated
            if quantity == 0:
                completed.append(episode_pnl)
                episodes.append(
                    {"fills": episode_fills, "realized_pnl_tmn": str(episode_pnl), "closed": True}
                )
                episode_fills = []
                episode_pnl = Decimal(0)
    wins = [p for p in completed if p > 0]
    losses = [p for p in completed if p < 0]
    profit, loss = sum(wins, Decimal(0)), -sum(losses, Decimal(0))
    return {
        "closed_round_trips": len(completed),
        "metric_sample_n": len(completed),
        "buy_fills": buys,
        "sell_fills": sells,
        "round_trip_pnls": [str(p) for p in completed],
        "winning_round_trips": len(wins),
        "losing_round_trips": len(losses),
        "win_rate_pct": 100 * len(wins) / len(completed) if completed else None,
        "profit_factor": str(profit / loss) if loss else None,
        "profit_factor_status": "DEFINED"
        if loss
        else ("NO_LOSSES" if wins else "NO_TRADES_OR_ZERO_PNL"),
        "payoff_ratio": str((profit / len(wins)) / (loss / len(losses)))
        if wins and losses
        else None,
        "residual_basis_tmn": str(cost),
        "open_episode_realized_pnl_tmn": str(episode_pnl),
        "episodes": episodes
        + (
            [{"fills": episode_fills, "realized_pnl_tmn": str(episode_pnl), "closed": False}]
            if episode_fills
            else []
        ),
    }


def run_simulation(
    candles: Sequence[Candle],
    decision_producer: Callable[[FeatureSnapshot], Decision],
    rules: MarketRules,
    policy: RiskPolicy,
    *,
    initial_capital: Decimal = Decimal("5000000"),
    interval_seconds: int = 900,
    slippage_pct: Decimal = Decimal("0.0005"),
    slow_period: int = 30,
    enable_logging: bool = True,
    audit: AuditLogger | None = None,
    decision_latency_seconds: int = 10,
    limit_penetration_pct: Decimal = Decimal(0),
    no_fill: bool = False,
    passive: bool = False,
    decision_source: str = "HOST_BASELINE",
) -> dict[str, Any]:
    """Run an end-to-end historical simulation over candles using production Ledger, Risk, and PaperBroker."""
    validate_decimal(initial_capital, "initial_capital", strictly_positive=True)
    validate_decimal(slippage_pct, "slippage_pct")
    if slippage_pct >= 1:
        raise ValueError("Slippage fraction must be below one")
    if len(candles) < slow_period + 2:
        raise ValueError(f"Need at least {slow_period + 2} candles for simulation")

    if type(decision_latency_seconds) is not int or decision_latency_seconds < 0:
        raise ValueError("Invalid decision latency")
    from royin.datasets import validate_candles

    validate_candles(candles, interval_seconds)
    for i in range(1, len(candles)):
        if candles[i].open_time != candles[i - 1].open_time + interval_seconds:
            raise ValueError(f"Candle sequence has gap at index {i}")

    import hashlib
    import json
    from dataclasses import asdict

    data_hash = hashlib.sha256(
        json.dumps([asdict(c) for c in candles], default=str, sort_keys=True).encode()
    ).hexdigest()
    own_logger = enable_logging and audit is None
    logger = audit or (
        AuditLogger(
            enable_console=False,
            hashes={
                "code": hashlib.sha256(
                    b"".join(
                        p.name.encode() + p.read_bytes()
                        for p in sorted(Path(__file__).parent.glob("*.py"))
                    )
                ).hexdigest(),
                "config": hashlib.sha256(
                    repr(
                        (
                            rules,
                            policy,
                            interval_seconds,
                            slippage_pct,
                            decision_latency_seconds,
                            limit_penetration_pct,
                            no_fill,
                            passive,
                        )
                    ).encode()
                ).hexdigest(),
                "data": data_hash,
                "prompt": None,
                "model": None,
            },
        )
        if enable_logging
        else None
    )
    if logger:
        logger.hashes["data"] = data_hash
        logger.hashes["config"] = hashlib.sha256(
            repr(
                (
                    rules,
                    policy,
                    initial_capital,
                    interval_seconds,
                    slippage_pct,
                    decision_latency_seconds,
                    limit_penetration_pct,
                    no_fill,
                    passive,
                )
            ).encode()
        ).hexdigest()
        logger.record_event(
            "DATA_ACCEPTED",
            "EVAL",
            {
                "symbol": rules.symbol,
                "data_sha256": data_hash,
                "count": len(candles),
                "interval_seconds": interval_seconds,
                "source": "PAPER",
            },
        )
    ledger = Ledger(":memory:", audit=logger)
    ledger.set_balance(rules.quote_asset, free=initial_capital)
    broker = PaperBroker(ledger, rules)
    denied_markets = load_restrictions(
        Path(__file__).resolve().parents[2] / "config/wallex-credit-market-policy.json"
    )
    if f"{rules.base_asset}/{rules.quote_asset}" in denied_markets:
        raise ValueError("Research market is denied by policy")

    decisions_count = 0
    orders_submitted = 0
    fills_count = 0
    peak_equity = initial_capital
    peak_exposure = Decimal(0)
    exposed_seconds = 0
    passive_submitted = False
    max_drawdown = Decimal(0)
    equity_curve, decision_traces = [], []

    def equity_point(timestamp, phase, price):
        equity = ledger.get_equity({rules.symbol: price}, rules.quote_asset)
        realized = ledger.get_realized_pnl(rules.symbol)
        return {
            "timestamp": timestamp,
            "phase": phase,
            "net_equity_tmn": str(equity),
            "realized_pnl_tmn": str(realized),
            "unrealized_pnl_tmn": str(equity - initial_capital - realized),
            "balances": {
                a: {"free": str(b.free), "locked": str(b.locked)}
                for a, b in ledger.get_all_balances().items()
            },
        }

    for i, candle in enumerate(candles):
        # 1. Match pending orders and stop loss against this candle
        filled = broker.process_candle(
            candle,
            slippage_pct=slippage_pct,
            candle_interval=interval_seconds,
            limit_penetration_pct=limit_penetration_pct,
            no_fill=no_fill,
        )
        fills_count += len(filled)

        exposure = ledger.get_balance(rules.base_asset).total * candle.close
        peak_exposure = max(peak_exposure, exposure)
        if exposure > 0:
            exposed_seconds += interval_seconds
        # 2. Check current equity and track max drawdown
        eq = ledger.get_equity({rules.symbol: candle.close}, quote_currency=rules.quote_asset)
        if eq > peak_equity:
            peak_equity = eq
        elif peak_equity > Decimal(0):
            dd = (peak_equity - eq) / peak_equity
            if dd > max_drawdown:
                max_drawdown = dd

        # 3. If closed bars count is sufficient, evaluate decision for candle close
        candle_close_time = candle.open_time + interval_seconds
        equity_curve.append(equity_point(candle_close_time, "CLOSED_BAR", candle.close))
        if i >= slow_period and i < len(candles) - 1:
            series_slice = CandleSeries(
                candles=tuple(candles[: i + 1]), interval_seconds=interval_seconds
            )
            pos = ledger.get_balance(rules.base_asset).total
            cash = ledger.get_balance(rules.quote_asset).free

            snap = extract_features(
                series_slice,
                rules.symbol,
                cutoff=candle_close_time,
                current_position_base=pos,
                available_tmn_cash=cash,
                slow_period=slow_period,
            )
            if logger:
                logger.context = {
                    "symbol": rules.symbol,
                    "cutoff": snap.cutoff,
                    "snapshot_sha256": snap.snapshot_sha256,
                }
                logger.record_event("SNAPSHOT", "EVAL", {"snapshot": snap.to_canonical_dict()})
            decision = decision_producer(snap)
            if logger:
                logger.context["decision_id"] = decision.decision_id
                logger.record_event(
                    "HOST_DECISION",
                    "EVAL",
                    {
                        "decision_id": decision.decision_id,
                        "action": decision.action,
                        "reason": decision.reason,
                        "source": decision_source,
                        "evidence_ids": decision.evidence_ids,
                    },
                )
            decisions_count += 1

            current_time = candle_close_time + decision_latency_seconds
            risk_res = evaluate_risk(
                decision,
                market_rules=rules,
                policy=policy,
                ledger=ledger,
                current_time=current_time,
                snapshot_sha256=snap.snapshot_sha256,
                candle_close_time=candle_close_time,
                current_price=candle.close,
                denied_markets=denied_markets,
                peak_equity=peak_equity,
            )
            decision_traces.append(
                {
                    "snapshot": snap.to_canonical_dict(),
                    "snapshot_sha256": snap.snapshot_sha256,
                    "decision": decision.model_dump(mode="json"),
                    "client_id": None,
                    "risk": {
                        k: str(v) if isinstance(v, Decimal) else v
                        for k, v in asdict(risk_res).items()
                    },
                }
            )

            if logger:
                logger.record_event(
                    "RISK_APPROVED" if risk_res.approved else "RISK_REJECTED",
                    "RISK",
                    {
                        "approved": risk_res.approved,
                        "action": risk_res.action,
                        "reason": risk_res.reason,
                        "event_time": current_time,
                    },
                )
            if passive and passive_submitted:
                continue
            if risk_res.approved and risk_res.action != "WAIT":
                if passive:
                    risk_res = replace(risk_res, stop_price=None)
                order = broker.submit_order(
                    risk_res,
                    client_id=f"ord_{candle_close_time}_{i}",
                    timestamp=current_time,
                )
                if order:
                    decision_traces[-1]["client_id"] = order.client_id
                    orders_submitted += 1
                    passive_submitted = passive_submitted or passive
                    if logger:
                        logger.record_event(
                            "SIM_ORDER_SUBMITTED",
                            "EVAL",
                            {
                                "client_id": order.client_id,
                                "action": risk_res.action,
                                "price": str(order.price),
                                "quantity": str(order.quantity),
                            },
                        )

    # 4. Finalize portfolio
    final_candle = candles[-1]
    final_time = final_candle.open_time + interval_seconds + 30
    fin_report = broker.finalize_portfolio(
        current_price=final_candle.close,
        timestamp=final_time,
        initial_capital=initial_capital,
        slippage_pct=slippage_pct,
    )
    equity_curve.append(equity_point(final_time, "FINAL_SETTLEMENT", final_candle.close))

    # 5. Extract realized PnL rows and fee audit
    with ledger.connection() as db:
        fills_count = db.execute("SELECT COUNT(*) FROM fills").fetchone()[0]
        total_orders = db.execute("SELECT COUNT(*) FROM order_intents").fetchone()[0]
        filled_orders = db.execute("SELECT COUNT(DISTINCT client_id) FROM fills").fetchone()[0]
        turnover = sum(
            (Decimal(p) * Decimal(q) for p, q in db.execute("SELECT price,quantity FROM fills")),
            Decimal(0),
        )
        simulated_slippage_tmn = sum(
            (
                Decimal(p) * Decimal(q) * slippage_pct / (1 - slippage_pct)
                for p, q in db.execute(
                    "SELECT f.price,f.quantity FROM fills f JOIN order_intents i ON i.client_id=f.client_id WHERE i.order_type='MARKET' AND i.side='SELL'"
                )
            ),
            Decimal(0),
        )

        # Total fees paid
        fee_rows = db.execute("SELECT fee, fee_asset FROM fills").fetchall()
        fills = [
            dict(
                zip(
                    ("fill_id", "client_id", "price", "quantity", "fee", "fee_asset", "timestamp"),
                    row,
                    strict=True,
                )
            )
            for row in db.execute(
                "SELECT fill_id,client_id,price,quantity,fee,fee_asset,timestamp FROM fills ORDER BY rowid"
            )
        ]
        orders = [
            dict(
                zip(
                    ("client_id", "side", "price", "quantity", "status", "created_at"),
                    row,
                    strict=True,
                )
            )
            for row in db.execute(
                "SELECT client_id,side,price,quantity,status,created_at FROM order_intents ORDER BY rowid"
            )
        ]
        total_fees_tmn = sum(Decimal(r[0]) for r in fee_rows if r[1] == "TMN")
        total_fees_base = sum(Decimal(r[0]) for r in fee_rows if r[1] == rules.base_asset)

    metrics = position_metrics(ledger, rules)
    final_equity = ledger.get_equity({rules.symbol: final_candle.close}, rules.quote_asset)
    best_episode = max((Decimal(p) for p in metrics["round_trip_pnls"]), default=None)
    peak_equity = max(peak_equity, final_equity)
    max_drawdown = max(max_drawdown, (peak_equity - final_equity) / peak_equity)
    if own_logger:
        logger.close()
    return {
        "run_id": logger.run_id if logger else None,
        "symbol": rules.symbol,
        "initial_capital_tmn": str(initial_capital),
        "final_cash_tmn": fin_report["final_tmn_cash"],
        "total_realized_pnl": fin_report["total_realized_pnl"],
        "residual_dust_base": fin_report["residual_dust_base"],
        "decisions_count": decisions_count,
        "orders_submitted": orders_submitted,
        "total_orders_including_stop_finalization": total_orders,
        "orders_with_any_fill": filled_orders,
        "orders_without_fill": total_orders - filled_orders,
        "fills_count": fills_count,
        "fills": fills,
        "orders": orders,
        "equity_curve": equity_curve,
        "decision_traces": decision_traces,
        **metrics,
        "evidence_kind": "REAL_MODEL_DECISIONS_PAPER_EXECUTION"
        if decision_source == "REAL_MODEL_REPLAY"
        else "PAPER_BASELINE_NO_AI",
        "execution_model": "OHLC conservative LIMIT at limit; stop at low; taker fee; no queue proof",
        "final_equity_mtm_tmn": str(final_equity),
        "net_return_pct": str((final_equity / initial_capital - 1) * 100),
        "cash_return_pct": fin_report["net_return_pct"],
        "gross_pnl_before_quote_fees_tmn": str(final_equity - initial_capital + total_fees_tmn),
        "net_pnl_mtm_tmn": str(final_equity - initial_capital),
        "best_closed_episode_pnl_tmn": str(best_episode) if best_episode is not None else None,
        "best_closed_episode_fraction_of_net_pnl": str(
            best_episode / (final_equity - initial_capital)
        )
        if best_episode is not None and final_equity != initial_capital
        else None,
        "net_return_without_best_closed_episode_pct": str(
            (final_equity - initial_capital - best_episode) / initial_capital * 100
        )
        if best_episode is not None
        else None,
        "net_pnl_without_best_closed_episode_tmn": str(
            final_equity - initial_capital - best_episode
        )
        if best_episode is not None
        else None,
        "without_best_episode_contract": "accounting subtraction only, not a counterfactual rerun; open residual remains included",
        "independent_exposures": None,
        "pnl_contract": "weighted average basis includes buy quote fee; realized sells net of sell fee; fees informational, not subtracted twice; gross only for this quote-fee simulation",
        "return_denominator": "whole initial account; not position return",
        "drawdown_basis": "closed-candle MTM plus final exit fee; not intrabar",
        "peak_exposure_tmn": str(peak_exposure),
        "time_exposed_seconds": exposed_seconds,
        "turnover_tmn": str(turnover),
        "latency_seconds": decision_latency_seconds,
        "total_fees_paid_tmn": str(total_fees_tmn),
        "total_fees_paid_base": str(total_fees_base),
        "simulated_market_exit_slippage_tmn": str(simulated_slippage_tmn),
        "slippage_contract": "scenario adverse fraction on market/stop exits; LIMIT at limit; not measured exchange slippage",
        "max_drawdown_pct": str(round(max_drawdown * Decimal(100), 4)),
    }


def source_bundle_sha256(root, paths, *, binding_schema_version=2):
    """V1 preserves raw legacy bytes; V2 replaces CRLF with LF and length-frames files."""
    if type(binding_schema_version) is not int or binding_schema_version not in (1, 2):
        raise ValueError("Unsupported portfolio binding schema")
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda p: p.relative_to(root).as_posix()):
        name, content = path.relative_to(root).as_posix().encode(), path.read_bytes()
        if binding_schema_version == 1:
            digest.update(name + b"\0" + content)
        else:
            content = content.replace(b"\r\n", b"\n")
            digest.update(len(name).to_bytes(8, "big") + name)
            digest.update(len(content).to_bytes(8, "big") + content)
    return digest.hexdigest()


def portfolio_bindings(
    candles,
    rules,
    policy,
    initial_capital,
    interval_seconds,
    slippage_pct,
    *,
    binding_schema_version=2,
):
    """Bind replay to executable sources and the entire shared execution scenario."""
    root = Path(__file__).resolve().parents[2]
    paths = sorted(
        [*root.glob("src/royin/*.py"), *root.glob("scripts/*.py"), root / "requirements.lock"]
    )
    bindings = {
        "code_sha256": source_bundle_sha256(
            root, paths, binding_schema_version=binding_schema_version
        ),
        "prompt_sha256": hashlib.sha256(SYSTEM_INSTRUCTIONS.encode()).hexdigest(),
        "model": "gpt-6-luna",
        "provider": "boxapi",
        "reasoning": "none",
        "data_sha256": hashlib.sha256(
            json.dumps([asdict(c) for c in candles], default=str, sort_keys=True).encode()
        ).hexdigest(),
        "config_sha256": hashlib.sha256(
            repr(
                (
                    rules,
                    policy,
                    initial_capital,
                    interval_seconds,
                    slippage_pct,
                    10,
                    Decimal(0),
                    False,
                    False,
                )
            ).encode()
        ).hexdigest(),
        "family": "existing_naive_crossover_with_ai_decision",
    }
    if binding_schema_version == 2:
        bindings.update(
            binding_schema_version=2,
            source_bytes_contract="CRLF_TO_LF_LENGTH_FRAMED_V2",
            ai_role="FULL_DECISION_PROPOSAL_NOT_VETO",
        )
    return bindings


def recorded_portfolio_producer(records, expected, *, source, real_lineage=None):
    """No nearest-input reuse; another arm's cash/position is another model input."""
    if source not in ("REAL_MODEL", "FAKE_MODEL"):
        raise ValueError("Explicit model evidence kind required")
    if source == "REAL_MODEL" and (not real_lineage or expected.get("binding_schema_version") != 2):
        raise ValueError("Reviewed REAL_MODEL response lineage and binding V2 required")
    indexed = {}
    for record in records:
        key = record.get("snapshot_sha256")
        if record.get("manifest") != expected or record.get("source") != source or key in indexed:
            raise ValueError("Recorded portfolio binding/source/uniqueness mismatch")
        if source == "REAL_MODEL":
            proof = real_lineage.get(record.get("response_sha256"))
            if (
                record.get("origin_kind") != "REAL_MODEL_PROVIDER_RESPONSE"
                or not proof
                or proof.get("review_status") != "INDEPENDENTLY_REVIEWED"
                or proof.get("manifest") != expected
                or proof.get("snapshot_sha256") != key
                or proof.get("decision") != record.get("decision")
                or not record.get("request_sha256")
                or proof.get("request_sha256") != record["request_sha256"]
                or proof.get("request_capture_verified") is not True
            ):
                raise ValueError("Missing reviewed provider response provenance")
            request = proof["request"]
            if request != {
                "system_instructions": SYSTEM_INSTRUCTIONS,
                "user_prompt": f"Evaluate market snapshot for {record['snapshot']['symbol']} at cutoff {record['snapshot']['cutoff']}.",
                "snapshot": record["snapshot"],
            }:
                raise ValueError("REAL_MODEL request/input mismatch")
            response = proof["response"]
            if (
                response.get("object") != "chat.completion"
                or response.get("model") != expected["model"]
                or not isinstance(response.get("id"), str)
                or not response["id"]
                or len(response.get("choices", [])) != 1
            ):
                raise ValueError("Invalid recorded provider completion")
            choice = response["choices"][0]
            calls = choice.get("message", {}).get("tool_calls", [])
            if (
                choice.get("finish_reason") != "tool_calls"
                or len(calls) != 1
                or calls[0].get("function", {}).get("name") != "final_result"
            ):
                raise ValueError("Missing final typed provider output")
            proposal = DecisionProposal.model_validate_json(calls[0]["function"]["arguments"])
            decision = Decision.model_validate(record["decision"])
            if proposal.model_dump() != {
                k: getattr(decision, k) for k in type(proposal).model_fields
            }:
                raise ValueError("Provider output/decision mismatch")
        indexed[key] = record

    def producer(snapshot):
        record = indexed.get(snapshot.snapshot_sha256)
        if not record or record.get("snapshot") != snapshot.to_canonical_dict():
            raise RecordedPortfolioBlocked("Missing exact own-ledger model input")
        decision = Decision.model_validate(record["decision"])
        if (decision.symbol, decision.cutoff, decision.snapshot_sha256) != (
            snapshot.symbol,
            snapshot.cutoff,
            snapshot.snapshot_sha256,
        ) or not set(decision.evidence_ids).issubset(snapshot.evidences):
            raise ValueError("Recorded decision/input/evidence mismatch")
        return decision

    return producer


class RecordedPortfolioBlocked(ValueError):
    """No reviewed real decision exists for this arm's exact evolving state."""


def run_portfolio_ablation(
    candles,
    rules,
    policy,
    ai_producer,
    *,
    initial_capital=Decimal("5000000"),
    interval_seconds=3600,
    slippage_pct=Decimal(".0005"),
    source,
):
    """Four arms; each run creates its own ledger and identical execution/risk gates."""
    if source not in (
        "REAL_MODEL_REPLAY",
        "FAKE_MODEL",
        "FAKE_MODEL_REPLAY",
        "BLOCKED_RECORDED_AI",
    ):
        raise ValueError("Model evidence source required")
    results = {}
    for name, producer in {
        "cash": always_wait_decision,
        "hold_shared_risk": buy_and_hold_decision,
        "rule": baseline_rule_decision,
        "rule_ai": ai_producer,
    }.items():
        if name == "rule_ai" and ai_producer is None:
            results[name] = {
                "status": "BLOCKED_RECORDED_AI",
                "equity_curve": None,
                "net_return_pct": None,
                "evidence_kind": "NO_MODEL_RECORDS",
            }
            continue
        result = run_simulation(
            candles,
            producer,
            rules,
            policy,
            initial_capital=initial_capital,
            interval_seconds=interval_seconds,
            slippage_pct=slippage_pct,
            enable_logging=False,
            decision_source=source if name == "rule_ai" else "HOST_BASELINE",
        )
        result["evidence_kind"] = source if name == "rule_ai" else "PAPER_BASELINE_NO_AI"
        result["benchmark_contract"] = (
            "same initial capital, risk, cost, exposure cap, cutoff and execution; hold may stop/reenter"
        )
        results[name] = result
    return results


def run_role_ablation(candles, rules, policy, *, single_model=None, two_roles=None,
                      source="NO_MODEL_RECORDS", initial_capital=Decimal("5000000"),
                      interval_seconds=3600, slippage_pct=Decimal(".0005")):
    """Conditional same-symbol wiring comparison, NOT causal whole-catalog selection evidence."""
    if source not in ("NO_MODEL_RECORDS", "FAKE_MODEL"):
        raise RecordedPortfolioBlocked("BLOCKED_RECORDED_AI: reviewed full-position role replay required")
    if source == "NO_MODEL_RECORDS" and (single_model is not None or two_roles is not None):
        raise ValueError("Unattributed model producer")
    results = {}
    for name, producer in (("rule", baseline_rule_decision), ("single_model", single_model), ("two_roles", two_roles)):
        if producer is None:
            results[name] = dict(status="BLOCKED_RECORDED_AI", evidence_kind="NO_MODEL_RECORDS",
                                 equity_curve=None, total_realized_pnl=None)
            continue
        report = run_simulation(candles, producer, rules, policy, initial_capital=initial_capital,
            interval_seconds=interval_seconds, slippage_pct=slippage_pct, enable_logging=False,
            decision_source="HOST_BASELINE" if name == "rule" else source)
        report.update(evidence_kind="PAPER_BASELINE_NO_AI" if name == "rule" else source,
                      mode="HISTORICAL_REPLAY", selection_contract="CONDITIONAL_FIXED_SYMBOL_NOT_SCANNER_BACKTEST")
        results[name] = report
    return results


def evaluate_strategy_suite(
    candles: Sequence[Candle],
    rules: MarketRules,
    policy: RiskPolicy,
    *,
    initial_capital: Decimal = Decimal("5000000"),
    interval_seconds: int = 900,
    ai_records: Sequence[dict] | None = None,
) -> dict[str, dict[str, Any]]:
    """Baselines without AI; optional REAL_MODEL replay must bind the entire own-state manifest."""
    if ai_records is not None:
        expected = {
            "prompt_sha256": hashlib.sha256(SYSTEM_INSTRUCTIONS.encode()).hexdigest(),
            "model": "gpt-6-luna",
            "data_sha256": hashlib.sha256(
                json.dumps([asdict(c) for c in candles], default=str, sort_keys=True).encode()
            ).hexdigest(),
            "config_sha256": hashlib.sha256(
                repr((rules, policy, initial_capital, interval_seconds)).encode()
            ).hexdigest(),
        }
        if any(
            r.get("manifest") != expected or r.get("source") != "REAL_MODEL" for r in ai_records
        ):
            raise ValueError("Recorded AI prompt/model/config/data manifest mismatch")
    strategies = {
        "1_Cash_Baseline": lambda s: always_wait_decision(s),
        "2_Buy_and_Hold": lambda s: buy_and_hold_decision(s),
        "3_Naive_Crossover": lambda s: baseline_rule_decision(s, allowed_symbols=(rules.symbol,)),
        "4_Fee_Aware_Conviction": lambda s: conviction_fee_aware_decision(
            s, allowed_symbols=(rules.symbol,)
        ),
    }

    results = {}
    for name, producer in strategies.items():
        res = run_simulation(
            candles,
            producer,
            rules,
            policy,
            initial_capital=initial_capital,
            interval_seconds=interval_seconds,
        )
        res["benchmark_contract"] = (
            "shared risk, may stop and reenter; same initial cash/max order/exposure"
        )
        results[name] = res
    results["2b_Passive_Buy_Once"] = run_simulation(
        candles,
        buy_and_hold_decision,
        rules,
        policy,
        initial_capital=initial_capital,
        interval_seconds=interval_seconds,
        passive=True,
    )
    results["2b_Passive_Buy_Once"]["benchmark_contract"] = (
        "buy once, no stop/reentry; same max initial allocation; not identical risk"
    )
    if ai_records is not None:
        records = {r["snapshot_sha256"]: r for r in ai_records}
        if len(records) != len(ai_records) or any(
            r.get("source") != "REAL_MODEL" for r in ai_records
        ):
            raise ValueError("AI records must be unique real model decisions")

        def recorded_ai(snap):
            r = records.get(snap.snapshot_sha256)
            if not r or r.get("snapshot") != snap.to_canonical_dict():
                raise ValueError(
                    "No REAL_MODEL decision for this strategy's exact position/cash snapshot"
                )
            raise ValueError(
                "Legacy REAL_MODEL records lack reviewed V2 response lineage; use the research importer"
            )

        results["5_Recorded_REAL_MODEL"] = run_simulation(
            candles,
            recorded_ai,
            rules,
            policy,
            initial_capital=initial_capital,
            interval_seconds=interval_seconds,
            decision_source="REAL_MODEL_REPLAY",
        )
        results["5_Recorded_REAL_MODEL"]["evidence_kind"] = "REAL_MODEL_DECISIONS_PAPER_EXECUTION"
    return results


def format_scorecard_markdown(
    scorecard: dict[str, dict[str, Any]], title: str = "Strategy Comparative Evaluation Scorecard"
) -> str:
    """Format comparative scorecard into clean GitHub Markdown table."""
    lines = [
        f"### {title}",
        "",
        "| Strategy | Return (%) | Realized PnL (TMN) | Max DD (%) | Trades | Win Rate (%) | Profit Factor | Total Fees (TMN) |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]

    for name, r in scorecard.items():
        ret = f"{float(r['net_return_pct']):+.2f}%"
        pnl = f"{float(r['total_realized_pnl']):+,.0f}"
        mdd = f"{float(r['max_drawdown_pct']):.2f}%"
        trades = r["closed_round_trips"]
        wr = "undefined" if r["win_rate_pct"] is None else f"{r['win_rate_pct']:.1f}%"
        pf = r["profit_factor"]
        fees = f"{float(r['total_fees_paid_tmn']):,.0f}"
        lines.append(f"| **{name}** | {ret} | {pnl} | {mdd} | {trades} | {wr} | {pf} | {fees} |")

    lines.append("")
    return "\n".join(lines)

# --- Terminal-return forecast scoring (uncertainty, not trade PnL) -----------------

def _forecast_value(item, name):
    return item[name] if isinstance(item, dict) else getattr(item, name)


def _median(values):
    ordered = sorted(values)
    if not ordered:
        raise ValueError("Median of empty sample")
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / Decimal(2)


def empirical_interval(returns, *, lower_q=Decimal("0.1"), upper_q=Decimal("0.9")):
    """Development-only empirical interval with linear interpolation; never fit on test."""
    values = sorted(returns)
    if not values or not 0 < lower_q < upper_q < 1:
        raise ValueError("Invalid empirical interval sample")
    def at(q):
        index = q * Decimal(len(values) - 1)
        lo = int(index)
        hi = min(lo + 1, len(values) - 1)
        frac = index - lo
        return values[lo] * (Decimal(1) - frac) + values[hi] * frac
    return at(lower_q), at(upper_q)


def winkler_score(lower, upper, outcome, *, alpha=Decimal("0.2")):
    """Interval score from the task contract: width, plus 2/alpha penalty outside."""
    if not lower <= upper:
        raise ValueError("Interval bounds are inverted")
    if not 0 < alpha < 1:
        raise ValueError("alpha must be in (0, 1)")
    if outcome < lower:
        return (upper - lower) + (Decimal(2) / alpha) * (lower - outcome)
    if outcome > upper:
        return (upper - lower) + (Decimal(2) / alpha) * (outcome - upper)
    return upper - lower


def score_return_forecasts(forecasts, outcomes, *, alpha=Decimal("0.2")):
    """Score issued forecasts; pending/missing outcomes stay visible, never interpolated."""
    forecasts = list(forecasts)
    ids = [_forecast_value(f, "forecast_id") for f in forecasts]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate forecast ids")
    pending = missing = 0
    rows = []
    for f in forecasts:
        fid = _forecast_value(f, "forecast_id")
        if fid not in outcomes:
            pending += 1
            continue
        outcome = outcomes[fid]
        if outcome is None:
            missing += 1
            continue
        y = Decimal(outcome)
        q10 = Decimal(_forecast_value(f, "return_q10"))
        q50 = Decimal(_forecast_value(f, "return_q50"))
        q90 = Decimal(_forecast_value(f, "return_q90"))
        if not q10 <= q50 <= q90:
            raise ValueError("Quantile crossing")
        rows.append(dict(
            forecast_id=fid, horizon_seconds=_forecast_value(f, "horizon_seconds"),
            outcome=y, q10=q10, q50=q50, q90=q90,
            abs_error=abs(y - q50), bias=y - q50,
            covered=q10 <= y <= q90, width=q90 - q10,
            winkler=winkler_score(q10, q90, y, alpha=alpha),
        ))
    n = len(rows)
    result = dict(
        issued=len(forecasts), scored=n, pending=pending, missing_outcome=missing,
        median_abs_error=_median([r["abs_error"] for r in rows]) if n else None,
        mean_abs_error=(sum((r["abs_error"] for r in rows), Decimal(0)) / n) if n else None,
        zero_point_comparison=dict(
            scored_pairs=n,
            model_better=sum(r["abs_error"] < abs(r["outcome"]) for r in rows),
            model_worse=sum(r["abs_error"] > abs(r["outcome"]) for r in rows),
            tied=sum(r["abs_error"] == abs(r["outcome"]) for r in rows),
            mean_absolute_error_difference=sum(
                (r["abs_error"] - abs(r["outcome"]) for r in rows), Decimal(0)) / n,
        ) if n else None,
        point_diagnostics=dict(
            status="DESCRIPTIVE_NOT_CALIBRATED",n=n,
            mean_forecast=sum((r["q50"] for r in rows),Decimal(0))/n,
            mean_outcome=sum((r["outcome"] for r in rows),Decimal(0))/n,
            mean_forecast_minus_outcome=sum((r["q50"]-r["outcome"] for r in rows),Decimal(0))/n,
            forecast_sign_counts={label:sum((r["q50"]>0)-(r["q50"]<0)==sign for r in rows)
                for label,sign in (("positive",1),("zero",0),("negative",-1))},
            outcome_sign_counts={label:sum((r["outcome"]>0)-(r["outcome"]<0)==sign for r in rows)
                for label,sign in (("positive",1),("zero",0),("negative",-1))},
            mae_skill_vs_zero=(1-sum((r["abs_error"] for r in rows),Decimal(0))/sum(
                (abs(r["outcome"]) for r in rows),Decimal(0)))
                if any(r["outcome"]!=0 for r in rows) else None,
        ) if n else None,
        bias=(sum((r["bias"] for r in rows), Decimal(0)) / n) if n else None,
        coverage=(Decimal(sum(1 for r in rows if r["covered"])) / n) if n else None,
        mean_width=(sum((r["width"] for r in rows), Decimal(0)) / n) if n else None,
        mean_winkler=(sum((r["winkler"] for r in rows), Decimal(0)) / n) if n else None,
        per_horizon={},
        rows=rows,
    )
    buckets = {}
    for r in rows:
        buckets.setdefault(r["horizon_seconds"], []).append(r)
    for horizon, group in sorted(buckets.items()):
        count = len(group)
        result["per_horizon"][horizon] = dict(
            n=count,
            median_abs_error=_median([r["abs_error"] for r in group]),
            mean_abs_error=sum((r["abs_error"] for r in group), Decimal(0)) / count,
            bias=sum((r["bias"] for r in group), Decimal(0)) / count,
            coverage=Decimal(sum(1 for r in group if r["covered"])) / count,
            mean_width=sum((r["width"] for r in group), Decimal(0)) / count,
            mean_winkler=sum((r["winkler"] for r in group), Decimal(0)) / count,
        )
    return result


def score_zero_baseline(outcome_returns, *, interval=None):
    """Zero point forecast plus a development empirical interval, same scoring contract."""
    values = [Decimal(v) for v in outcome_returns]
    if not values:
        raise ValueError("Baseline needs outcomes")
    errors = [abs(v) for v in values]
    if interval is None:
        return dict(n=len(values),median_abs_error=_median(errors),
                    mean_abs_error=sum(errors,Decimal(0))/len(values),bias=sum(values,Decimal(0))/len(values),
                    coverage=None,mean_width=None,mean_winkler=None,q10=None,q90=None,
                    interval_status="BLOCKED_NO_DEVELOPMENT_INTERVAL")
    q10, q90 = interval
    return dict(
        n=len(values),
        median_abs_error=_median(errors),
        mean_abs_error=sum(errors, Decimal(0)) / len(values),
        bias=sum(values, Decimal(0)) / len(values),
        coverage=Decimal(sum(1 for v in values if q10 <= v <= q90)) / len(values),
        mean_width=q90 - q10,
        mean_winkler=sum((winkler_score(q10, q90, v) for v in values), Decimal(0)) / len(values),
        q10=q10, q90=q90,
    )
