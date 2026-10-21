"""Evaluation, replay, benchmarking, and causal ablation harnesses for AI decisions."""

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from royin.agent import decide
from royin.broker import PaperBroker
from royin.config import RuntimeConfig
from royin.decision import Decision, DecisionProposal, bind_decision
from royin.features import FeatureSnapshot, extract_features
from royin.ledger import Ledger
from royin.logger import get_audit_logger
from royin.market_data import Candle, CandleSeries
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
            evidence_ids=("EV_DATA_FRESH", "EV_POSITION_LONG" if has_position else "EV_POSITION_FLAT"),
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
    min_atr_pct: Decimal = Decimal("0.006"),     # 0.6% ATR volatility hurdle
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
        snapshot.atr_14 / snapshot.last_close
        if snapshot.last_close > Decimal(0)
        else Decimal(0)
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
                reason=f"Conviction ENTER: SMA spread {sma_spread*100:.2f}% and ATR {atr_pct*100:.2f}% clear 0.6% fee hurdle",
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
                evidence_ids=("EV_TREND_BEARISH" if is_reversal else "EV_RSI_OVERBOUGHT", "EV_POSITION_LONG"),
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
        traces.append(EvaluationTrace(
            decision=decision,
            snapshot=snap,
            wall_seconds=elapsed,
            is_ai=True,
        ))
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
        base_dec = baseline_rule_decision(
            snap,
            decision_id=f"base_{snap.cutoff}",
            allowed_symbols=allowed_symbols,
        )
        if ai_dec.action == base_dec.action:
            agreements += 1
        else:
            divergences.append({
                "cutoff": snap.cutoff,
                "symbol": snap.symbol,
                "ai_action": ai_dec.action,
                "ai_reason": ai_dec.reason,
                "baseline_action": base_dec.action,
                "baseline_reason": base_dec.reason,
            })

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
    enable_logging: bool = False,
) -> dict[str, Any]:
    """Run an end-to-end historical simulation over candles using production Ledger, Risk, and PaperBroker."""
    if len(candles) < slow_period + 2:
        raise ValueError(f"Need at least {slow_period + 2} candles for simulation")

    for i in range(1, len(candles)):
        if candles[i].open_time != candles[i - 1].open_time + interval_seconds:
            raise ValueError(f"Candle sequence has gap at index {i}")

    logger = get_audit_logger() if enable_logging else None

    ledger = Ledger(":memory:")
    ledger.set_balance(rules.quote_asset, free=initial_capital)
    broker = PaperBroker(ledger, rules)
    denied_markets = frozenset({"PAXGTMN", "OPTMN"})

    decisions_count = 0
    orders_submitted = 0
    fills_count = 0
    peak_equity = initial_capital
    max_drawdown = Decimal(0)

    for i, candle in enumerate(candles):
        # 1. Match pending orders and stop loss against this candle
        filled = broker.process_candle(
            candle,
            slippage_pct=slippage_pct,
            candle_interval=interval_seconds,
        )
        fills_count += len(filled)

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
        if i >= slow_period:
            series_slice = CandleSeries(candles=tuple(candles[: i + 1]), interval_seconds=interval_seconds)
            pos = ledger.get_balance(rules.base_asset).free
            cash = ledger.get_balance(rules.quote_asset).free

            snap = extract_features(
                series_slice,
                rules.symbol,
                cutoff=candle_close_time,
                current_position_base=pos,
                available_tmn_cash=cash,
                slow_period=slow_period,
            )
            decision = decision_producer(snap)
            decisions_count += 1

            current_time = candle_close_time + 10
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

            if risk_res.approved and risk_res.action != "WAIT":
                order = broker.submit_order(
                    risk_res,
                    client_id=f"ord_{candle_close_time}_{i}",
                    timestamp=current_time,
                )
                if order:
                    orders_submitted += 1
                    if logger:
                        logger.record_event("SIM_ORDER_SUBMITTED", "EVAL", {
                            "client_id": order.client_id,
                            "action": risk_res.action,
                            "price": str(order.price),
                            "quantity": str(order.quantity),
                        })

    # 4. Finalize portfolio
    final_candle = candles[-1]
    final_time = final_candle.open_time + interval_seconds + 30
    fin_report = broker.finalize_portfolio(
        current_price=final_candle.close,
        timestamp=final_time,
        initial_capital=initial_capital,
    )

    # 5. Extract realized PnL rows and fee audit
    with ledger.connection() as db:
        pnl_rows = db.execute("SELECT pnl FROM realized_pnl WHERE symbol = ?", (rules.symbol,)).fetchall()
        pnls = [Decimal(r[0]) for r in pnl_rows]

        # Total fees paid
        fee_rows = db.execute("SELECT fee, fee_asset FROM fills").fetchall()
        total_fees_tmn = sum(Decimal(r[0]) for r in fee_rows if r[1] == "TMN")
        total_fees_base = sum(Decimal(r[0]) for r in fee_rows if r[1] == rules.base_asset)

    wins = [p for p in pnls if p > Decimal(0)]
    losses = [p for p in pnls if p < Decimal(0)]
    win_rate = (len(wins) / len(pnls) * 100) if pnls else 0.0

    gross_profit = sum(wins, Decimal(0))
    gross_loss = abs(sum(losses, Decimal(0)))
    profit_factor = (gross_profit / gross_loss) if gross_loss > Decimal(0) else (Decimal("999.9") if gross_profit > Decimal(0) else Decimal("1.0"))

    avg_win = (gross_profit / Decimal(len(wins))) if wins else Decimal(0)
    avg_loss = (gross_loss / Decimal(len(losses))) if losses else Decimal(0)
    payoff_ratio = (avg_win / avg_loss) if avg_loss > Decimal(0) else (Decimal("999.9") if avg_win > Decimal(0) else Decimal("1.0"))

    return {
        "symbol": rules.symbol,
        "initial_capital_tmn": str(initial_capital),
        "final_cash_tmn": fin_report["final_tmn_cash"],
        "total_realized_pnl": fin_report["total_realized_pnl"],
        "net_return_pct": fin_report["net_return_pct"],
        "residual_dust_base": fin_report["residual_dust_base"],
        "decisions_count": decisions_count,
        "orders_submitted": orders_submitted,
        "fills_count": fills_count,
        "closed_round_trips": len(pnls),
        "winning_round_trips": len(wins),
        "losing_round_trips": len(losses),
        "win_rate_pct": round(win_rate, 2),
        "profit_factor": str(round(profit_factor, 2)),
        "payoff_ratio": str(round(payoff_ratio, 2)),
        "total_fees_paid_tmn": str(round(total_fees_tmn, 2)),
        "total_fees_paid_base": str(round(total_fees_base, 6)),
        "max_drawdown_pct": str(round(max_drawdown * Decimal(100), 4)),
    }


def evaluate_strategy_suite(
    candles: Sequence[Candle],
    rules: MarketRules,
    policy: RiskPolicy,
    *,
    initial_capital: Decimal = Decimal("5000000"),
    interval_seconds: int = 900,
) -> dict[str, dict[str, Any]]:
    """Evaluate full comparative scorecard across all 4 strategy baselines."""
    strategies = {
        "1_Cash_Baseline": lambda s: always_wait_decision(s),
        "2_Buy_and_Hold": lambda s: buy_and_hold_decision(s),
        "3_Naive_Crossover": lambda s: baseline_rule_decision(s),
        "4_Fee_Aware_Conviction": lambda s: conviction_fee_aware_decision(s),
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
        results[name] = res
    return results


def format_scorecard_markdown(scorecard: dict[str, dict[str, Any]], title: str = "Strategy Comparative Evaluation Scorecard") -> str:
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
        wr = f"{r['win_rate_pct']:.1f}%"
        pf = r["profit_factor"]
        fees = f"{float(r['total_fees_paid_tmn']):,.0f}"
        lines.append(f"| **{name}** | {ret} | {pnl} | {mdd} | {trades} | {wr} | {pf} | {fees} |")

    lines.append("")
    return "\n".join(lines)
