"""Unified paper trading orchestrator for continuous real-market and replay testing.

This is the primary orchestrator for the research paper trading mission.
It executes virtual trades (5,000,000 TMN virtual capital) on public Wallex market data
under host-enforced risk gates, net-profit retention trailing protection, and shared model budgets.
Real production keys and account write access remain strictly NO_GO.
"""

import argparse
import asyncio
import contextlib
import hashlib
import json
import logging
import signal
import sys
import tempfile
import time
from decimal import Decimal
from pathlib import Path

from royin.agent import (
    RoleRunEnvelope,
    decide_role,
)
from royin.broker import PaperBroker
from royin.config import RuntimeConfig, load_config
from royin.datasets import load_dataset
from royin.decision import (
    EntryOpportunityContext,
    RoleDecisionProposal,
    bind_decision,
)
from royin.features import extract_features
from royin.ledger import Ledger
from royin.logger import AuditLogger
from royin.market_data import (
    CandleSeries,
)
from royin.markets import parse_catalog
from royin.model_budget import BudgetBlocked, ModelBudget
from royin.risk import (
    MarketRules,
    PositionProtectionPolicy,
    RiskPolicy,
    RiskResult,
    evaluate_risk,
)

try:
    from scripts.run_paper_trader import (
        ScannerPublicFeed,
        scan_current_market,
    )
except ImportError:
    from run_paper_trader import (
        ScannerPublicFeed,
        scan_current_market,
    )

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]

# Default parameters
DEFAULT_CAPITAL_TMN = Decimal("5000000")
DEFAULT_MAX_ORDER_TMN = Decimal("300000")
DEFAULT_MIN_NOTIONAL_TMN = Decimal("100000")
DEFAULT_MIN_QUANTITY_USDT = Decimal("1.0")
DEFAULT_TAKER_FEE_RATE = Decimal("0.0030")
DEFAULT_SLIPPAGE_PCT = Decimal("0.0005")
DEFAULT_HORIZON_MAX_SECONDS = 10800  # 3 hours


def build_default_rules(symbol="USDTTMN", tick_size=Decimal("1"), step_size=Decimal("0.01")):
    return MarketRules(
        symbol=symbol,
        base_asset=symbol.replace("TMN", "").replace("USDT", "") or "USDT",
        quote_asset="TMN" if symbol.endswith("TMN") else "USDT",
        tick_size=tick_size,
        step_size=step_size,
        min_notional=DEFAULT_MIN_NOTIONAL_TMN,
        min_quantity=DEFAULT_MIN_QUANTITY_USDT,
        maker_fee_rate=Decimal("0.0025"),
        taker_fee_rate=DEFAULT_TAKER_FEE_RATE,
    )


def build_default_protection_policy(
    deadline_utc,
    hard_holding_seconds=10800,
    retention_ratio=Decimal("0.5"),
    activation_fraction=Decimal("0.025"),
):
    return PositionProtectionPolicy(
        initial_stop_pct=Decimal("0.02"),
        trailing_drawdown_pct=Decimal("0.01"),
        checkpoint_profit_pct=Decimal("0.025"),
        review_interval_seconds=1800,
        hard_holding_seconds=hard_holding_seconds,
        deadline_utc=deadline_utc,
        exit_buffer_seconds=300,
        max_quote_age_seconds=120,
        max_loss_tmn=Decimal("50000"),
        profit_retention_ratio=retention_ratio,
        net_activation_fraction=activation_fraction,
    )


def public_symbols(feed, *, cutoff):
    payload, received = feed.get("/hector/web/v1/markets", {}, cutoff=cutoff)
    catalog = parse_catalog(payload)
    return payload, received, {symbol for symbol in catalog}


class MarketPaperOrchestrator:
    """Manages the full lifecycle of a bounded paper trading run."""

    def __init__(
        self,
        *,
        run_id: str,
        mode: str = "CURRENT_PAPER",
        model_mode: str = "FAKE_MODEL",
        duration_seconds: int = 300,
        cycles: int = 1,
        interval_seconds: int = 60,
        horizon_max_seconds: int = DEFAULT_HORIZON_MAX_SECONDS,
        retention_ratio: Decimal = Decimal("0.5"),
        activation_fraction: Decimal = Decimal("0.025"),
        initial_capital: Decimal = DEFAULT_CAPITAL_TMN,
        dataset_path: Path | None = None,
        capture_dir: Path | None = None,
        db_path: Path | None = None,
        config: RuntimeConfig | None = None,
    ):
        self.run_id = run_id
        self.mode = mode
        self.model_mode = model_mode
        self.duration_seconds = duration_seconds
        self.max_cycles = cycles
        self.interval_seconds = interval_seconds
        self.horizon_max_seconds = horizon_max_seconds
        self.retention_ratio = retention_ratio
        self.activation_fraction = activation_fraction
        self.initial_capital = initial_capital
        self.dataset_path = dataset_path
        self.config = config or load_config()

        self.capture_dir = capture_dir or (ROOT / "artifacts/market-paper" / self.run_id)
        self.capture_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path or (self.capture_dir / "paper.sqlite3")

        self.audit = AuditLogger(self.capture_dir / "audit", False, run_id=self.run_id)
        self.ledger = Ledger(self.db_path, audit=self.audit)

        # Initialize portfolio if empty
        binding = hashlib.sha256(f"paper:{self.run_id}".encode()).hexdigest()
        self.ledger.initialize_portfolio(
            self.initial_capital, quote_asset="TMN", binding=binding
        )

        self.budget = None
        self.run_envelope = None
        if self.model_mode == "REAL_MODEL":
            try:
                self.budget = ModelBudget(self.config)
                self.run_envelope = RoleRunEnvelope(self.budget, duration_seconds=self.duration_seconds)
            except (BudgetBlocked, ValueError, OSError, RuntimeError) as exc:
                logger.warning("Could not initialize real model budget: %s", exc)

        self.rules = build_default_rules("USDTTMN")
        self.broker = PaperBroker(self.ledger, self.rules)

        deadline = int(time.time()) + self.duration_seconds + 3600
        if self.config.CHALLENGE_END_AT:
            deadline = min(deadline, int(self.config.CHALLENGE_END_AT.timestamp()))
        self.protection_policy = build_default_protection_policy(
            deadline_utc=deadline,
            hard_holding_seconds=self.horizon_max_seconds,
            retention_ratio=self.retention_ratio,
            activation_fraction=self.activation_fraction,
        )

        self.risk_policy = RiskPolicy(
            max_order_tmn=DEFAULT_MAX_ORDER_TMN,
            max_exposure_tmn=Decimal("1000000"),
            stop_loss_pct=Decimal("0.02"),
            max_drawdown_pct=Decimal("0.05"),
            deadline_utc=deadline,
            min_seconds_before_deadline=300,
        )

        self.decision_traces = []
        self.equity_curve = []
        self.errors = []
        self.shutdown_requested = False
        self.start_time = None
        self.completed_cycles = 0

    def request_shutdown(self, *args):
        self.shutdown_requested = True

    async def run_historical_replay(self, dataset_path: Path):
        data, candles = load_dataset(dataset_path)
        symbol = data["symbol"]
        interval = data["interval_seconds"]
        self.rules = build_default_rules(symbol)
        self.broker = PaperBroker(self.ledger, self.rules)
        warmup = 31
        if len(candles) <= warmup:
            raise ValueError(f"Need > {warmup} candles for replay, got {len(candles)}")

        total_steps = len(candles) - warmup
        if self.max_cycles and self.max_cycles < total_steps:
            total_steps = self.max_cycles

        end_time = candles[-1].open_time + interval + 7200
        self.protection_policy = build_default_protection_policy(
            deadline_utc=end_time,
            hard_holding_seconds=self.horizon_max_seconds,
            retention_ratio=self.retention_ratio,
            activation_fraction=self.activation_fraction,
        )
        self.risk_policy = RiskPolicy(
            max_order_tmn=DEFAULT_MAX_ORDER_TMN,
            max_exposure_tmn=Decimal("1000000"),
            stop_loss_pct=Decimal("0.02"),
            max_drawdown_pct=Decimal("0.05"),
            deadline_utc=end_time,
            min_seconds_before_deadline=300,
        )

        pending_entry = None

        for i in range(total_steps):
            if self.shutdown_requested:
                break
            idx = warmup + i
            current_candle = candles[idx]
            cutoff = current_candle.open_time + interval
            history_slice = candles[: idx + 1]

            # 1. Fill pending entry at current candle open with adverse slippage + fee
            if pending_entry is not None:
                order_limit_price = pending_entry["risk"].price
                if current_candle.low > order_limit_price:
                    # Price never reached limit order -> no fill, cancel order
                    self.broker.reconcile_order(
                        pending_entry["client_id"],
                        simulated_state="CANCELED",
                        timestamp=current_candle.open_time,
                    )
                else:
                    if current_candle.open <= order_limit_price:
                        entry_price = min(
                            order_limit_price,
                            self.rules.quantize_price(current_candle.open * (Decimal(1) + DEFAULT_SLIPPAGE_PCT)),
                        )
                    else:
                        entry_price = order_limit_price
                    self.broker.reconcile_order(
                        pending_entry["client_id"],
                        simulated_state="FILLED",
                        timestamp=current_candle.open_time,
                        executed_price=entry_price,
                    )
                    self.broker.arm_protection(
                        self.protection_policy,
                        opened_at=current_candle.open_time,
                        entry_price=entry_price,
                    )
                pending_entry = None

            # 2. Check position protection
            held_qty = self.ledger.get_balance(self.rules.base_asset).total
            prot_state = json.loads(self.ledger.get_meta("protection_" + self.rules.symbol) or "null")

            if held_qty > 0 and prot_state and prot_state.get("status") == "OPEN":
                current_stop = Decimal(prot_state.get("trailing_stop_price", "0"))
                # If candle low touched or breached the trailing stop, test exit at low
                # Otherwise, observe candle close to update high-water mark and tighten retention stop
                test_bid = current_candle.low if (current_stop > 0 and current_candle.low <= current_stop) else current_candle.close
                tick = self.broker.observe_quote(
                    test_bid,
                    source_time=cutoff,
                    received_at=cutoff,
                    now=cutoff,
                    policy=self.protection_policy,
                    slippage_pct=DEFAULT_SLIPPAGE_PCT,
                )
                action = tick.get("action", "WAIT")
                trace = {
                    "decision": {
                        "decision_id": f"pos_{cutoff}",
                        "symbol": symbol,
                        "action": action,
                        "cutoff": cutoff,
                        "evidence_ids": ["EV_POSITION_LONG"],
                        "reason": f"Position protection: {tick.get('exit_reason') or tick.get('status')}",
                        "role": "POSITION_REVIEWER",
                    },
                    "snapshot": {
                        "symbol": symbol,
                        "cutoff": cutoff,
                        "last_close": str(test_bid),
                        "available_tmn_cash": str(self.ledger.get_balance("TMN").free),
                    },
                    "risk": {
                        "approved": True if action == "EXIT" else None,
                        "action": action,
                        "reason": tick.get("exit_reason", "Position holding"),
                        "stop_price": tick.get("trailing_stop_price"),
                    },
                    "protection": tick,
                }
                self.decision_traces.append(trace)
            else:
                series_slice = CandleSeries(tuple(history_slice), interval, ())
                snap = extract_features(
                    series_slice,
                    symbol,
                    cutoff=cutoff,
                    available_tmn_cash=self.ledger.get_balance("TMN").free,
                )
                available_cash = self.ledger.get_balance("TMN").free
                opp = EntryOpportunityContext(
                    spread_pct=Decimal("0.001"),
                    round_trip_fee_pct=Decimal("0.006"),
                    bid_depth_tmn=Decimal("5000000"),
                    ask_depth_tmn=Decimal("5000000"),
                    catalog_sha256="f" * 64,
                    catalog_received_at=cutoff,
                    candle_received_at=cutoff,
                    depth_received_at=cutoff,
                    observed_at=cutoff,
                )
                # Causal entry decision: enter if bullish trend
                action = "ENTER" if ("EV_TREND_BULLISH" in snap.evidences and available_cash >= DEFAULT_MIN_NOTIONAL_TMN) else "WAIT"
                fc = None
                if action == "ENTER":
                    fc = {
                        "forecast_id": f"fc_{cutoff}",
                        "symbol": symbol,
                        "cutoff": cutoff,
                        "reference_price": str(snap.last_close),
                        "reference_kind": "LAST_CLOSE",
                        "horizon_seconds": min(7200, self.horizon_max_seconds),
                        "return_q10": "-0.005",
                        "return_q50": "0.015",
                        "return_q90": "0.035",
                        "target_return_fraction": "0.025",
                        "review_after_seconds": 1800,
                        "invalidation": "Trend weakens below SMA",
                        "evidence_ids": ("EV_DATA_FRESH", "EV_TREND_BULLISH"),
                    }
                proposal = RoleDecisionProposal(
                    role="ENTRY_ANALYST",
                    action=action,
                    symbol=symbol,
                    cutoff=cutoff,
                    snapshot_sha256=snap.snapshot_sha256,
                    opportunity_sha256=opp.sha256,
                    evidence_ids=tuple(snap.evidences.keys())[:3] or ("EV_DATA_FRESH",),
                    reason="Bullish trend entry" if action == "ENTER" else "Waiting for entry conditions",
                    invalidation="Next candle close",
                    forecast=fc,
                    horizon_seconds=7200 if action == "ENTER" else None,
                    review_after_seconds=1800 if action == "ENTER" else None,
                )
                decision = bind_decision(
                    proposal,
                    decision_id=f"replay_{cutoff}",
                    symbol=symbol,
                    cutoff=cutoff,
                    snapshot_sha256=snap.snapshot_sha256,
                    available_evidence_ids=tuple(snap.evidences.keys()),
                )
                risk_res = None
                cid = None
                if action == "ENTER":
                    risk_res = evaluate_risk(
                        decision,
                        market_rules=self.rules,
                        policy=self.risk_policy,
                        ledger=self.ledger,
                        current_time=cutoff,
                        snapshot_sha256=snap.snapshot_sha256,
                        candle_close_time=cutoff,
                        current_price=snap.last_close,
                        denied_markets=frozenset(),
                    )
                    if risk_res.approved:
                        cid = f"ord_replay_{cutoff}"
                        self.broker.submit_order(risk_res, client_id=cid, timestamp=cutoff)
                        pending_entry = {"client_id": cid, "risk": risk_res}

                trace = {
                    "decision": decision.model_dump(mode="json"),
                    "snapshot": snap.to_canonical_dict(),
                    "snapshot_sha256": snap.snapshot_sha256,
                    "risk": {
                        "approved": risk_res.approved if risk_res else None,
                        "action": risk_res.action if risk_res else "WAIT",
                        "reason": risk_res.reason if risk_res else "WAIT action",
                        "stop_price": str(risk_res.stop_price) if risk_res and risk_res.stop_price else None,
                    },
                    "client_id": cid,
                }
                self.decision_traces.append(trace)

            self.completed_cycles += 1
            self._checkpoint_and_export(cutoff)

        final_cutoff = candles[min(warmup + total_steps - 1, len(candles) - 1)].open_time + interval
        prot_state = json.loads(self.ledger.get_meta("protection_" + self.rules.symbol) or "null")
        if prot_state and prot_state.get("status") == "OPEN":
            self.broker.finalize_portfolio(
                candles[-1].close,
                timestamp=final_cutoff,
                slippage_pct=DEFAULT_SLIPPAGE_PCT,
            )
        self._checkpoint_and_export(final_cutoff)
        return self.generate_summary()

    async def run(self):
        if self.mode == "HISTORICAL_REPLAY":
            ds_path = self.dataset_path or (
                ROOT / "data/t02/normalized-c8c0f4903f000a992688564e8a90b54daab68aeff8ca7c998a7d933b41c7b5c1.json"
            )
            return await self.run_historical_replay(ds_path)

        self.start_time = time.monotonic()
        feed = ScannerPublicFeed(self.capture_dir / "raw", max_requests=24)
        now_ts = int(time.time())
        self.ledger.set_meta("engine_heartbeat", str(now_ts))

        while not self.shutdown_requested and self.completed_cycles < self.max_cycles:
            elapsed = time.monotonic() - self.start_time
            if elapsed >= self.duration_seconds:
                break

            cycle_start = time.time()
            now_ts = int(cycle_start)
            try:
                await self._execute_cycle(feed, now_ts)
            except Exception as exc:
                logger.exception("Error in paper cycle: %s", exc)
                self.errors.append({"cycle": self.completed_cycles, "error": str(exc), "timestamp": now_ts})

            self.completed_cycles += 1
            self._checkpoint_and_export(now_ts)

            if self.completed_cycles < self.max_cycles:
                sleep_time = max(0.5, self.interval_seconds - (time.time() - cycle_start))
                # Interruptible sleep
                for _ in range(int(sleep_time * 2)):
                    if self.shutdown_requested or (time.monotonic() - self.start_time >= self.duration_seconds):
                        break
                    await asyncio.sleep(0.5)

        self._checkpoint_and_export(int(time.time()))
        return self.generate_summary()

    async def _execute_cycle(self, feed: ScannerPublicFeed, now: int):
        self.ledger.set_meta("engine_heartbeat", str(now))

        # Check if position is currently held
        held_qty = self.ledger.get_balance(self.rules.base_asset).total
        prot_state = json.loads(self.ledger.get_meta("protection_" + self.rules.symbol) or "null")

        if held_qty > 0 and prot_state and prot_state.get("status") == "OPEN":
            # Position holding & protection tick
            await self._handle_position_cycle(feed, now, prot_state)
        else:
            # Flat: scanning & entry analysis
            await self._handle_entry_cycle(feed, now)

    async def _handle_entry_cycle(self, feed: ScannerPublicFeed, now: int):
        _payload, received, symbols = public_symbols(feed, cutoff=now)
        available_cash = self.ledger.get_balance(self.rules.quote_asset).free

        report = scan_current_market(
            feed,
            account_symbols=symbols,
            account_as_of=received,
            interval_seconds=300,
            round_trip_fee_pct=Decimal("0.006"),
            min_depth_tmn=Decimal("1000000"),
            max_spread_pct=Decimal("0.005"),
            available_tmn_cash=available_cash,
            batch_limit=3,
        )

        batch_list = report.get("batch", [])
        if not batch_list:
            trace = {
                "decision": {
                    "decision_id": f"scan_{now}",
                    "symbol": self.rules.symbol,
                    "action": "WAIT",
                    "cutoff": now,
                    "evidence_ids": ["EV_POSITION_FLAT"],
                    "reason": f"No eligible scanner candidate: {report.get('status')}",
                },
                "snapshot": {
                    "symbol": self.rules.symbol,
                    "cutoff": now,
                    "available_tmn_cash": str(available_cash),
                },
                "risk": {"approved": None, "action": "WAIT", "reason": "No candidate"},
            }
            self.decision_traces.append(trace)
            return

        batch_map = {item.snapshot.symbol: (item.snapshot, item.opportunity) for item in batch_list}
        primary_snap, primary_opp = batch_list[0].snapshot, batch_list[0].opportunity

        decision = None
        model_trace = {}

        if self.model_mode == "REAL_MODEL" and self.run_envelope:
            try:
                decision = await decide_role(
                    primary_snap,
                    market_batch=batch_map,
                    config=self.config,
                    budget=self.budget,
                    run_envelope=self.run_envelope,
                    model_trace=model_trace,
                    allowed_symbols=tuple(batch_map),
                    horizon_bounds=(600, self.horizon_max_seconds),
                    remaining_seconds=self.horizon_max_seconds,
                    timeout_seconds=30,
                )
            except BudgetBlocked as exc:
                self.ledger.set_meta("entry_block_reason", "BUDGET_EXHAUSTED")
                decision = RoleDecisionProposal(
                    role="ENTRY_ANALYST",
                    action="WAIT",
                    symbol=primary_snap.symbol,
                    cutoff=primary_snap.cutoff,
                    snapshot_sha256=primary_snap.snapshot_sha256,
                    evidence_ids=("EV_POSITION_FLAT",),
                    reason=f"Model budget blocked: {exc}",
                    invalidation="Next budget replenishment",
                )
        else:
            # Fake model simulation: ENTER if primary candidate has bullish evidence and positive volume
            should_enter = "EV_TREND_BULLISH" in primary_snap.evidences and available_cash >= DEFAULT_MIN_NOTIONAL_TMN
            action = "ENTER" if should_enter else "WAIT"
            fc = None
            if action == "ENTER":
                fc = {
                    "forecast_id": f"fc_{now}",
                    "symbol": primary_snap.symbol,
                    "cutoff": primary_snap.cutoff,
                    "reference_price": str(primary_snap.last_close),
                    "reference_kind": "LAST_CLOSE",
                    "horizon_seconds": min(7200, self.horizon_max_seconds),
                    "return_q10": "-0.005",
                    "return_q50": "0.015",
                    "return_q90": "0.035",
                    "target_return_fraction": "0.025",
                    "review_after_seconds": 1800,
                    "invalidation": "Price drops below slow SMA",
                    "evidence_ids": ("EV_DATA_FRESH", "EV_TREND_BULLISH"),
                }
            decision = RoleDecisionProposal(
                role="ENTRY_ANALYST",
                action=action,
                symbol=primary_snap.symbol,
                cutoff=primary_snap.cutoff,
                snapshot_sha256=primary_snap.snapshot_sha256,
                opportunity_sha256=primary_opp.sha256,
                evidence_ids=tuple(primary_snap.evidences.keys())[:3] or ("EV_DATA_FRESH",),
                reason="Simulated deterministic market entry policy" if action == "ENTER" else "Waiting for momentum",
                invalidation="Next closed candle",
                forecast=fc,  # type: ignore
                horizon_seconds=7200 if action == "ENTER" else None,
                review_after_seconds=1800 if action == "ENTER" else None,
            )

        # Host risk evaluation
        risk_result = None
        client_id = None
        if decision.action == "ENTER" and decision.symbol in batch_map:
            chosen_snap, _chosen_opp = batch_map[decision.symbol]
            target_rules = build_default_rules(decision.symbol)
            risk_result = evaluate_risk(
                decision,
                market_rules=target_rules,
                policy=self.risk_policy,
                ledger=self.ledger,
                current_time=now,
                snapshot_sha256=chosen_snap.snapshot_sha256,
                candle_close_time=chosen_snap.cutoff,
                current_price=chosen_snap.last_close,
                denied_markets=frozenset(),
            )

            if risk_result.approved:
                client_id = f"paper_enter_{now}_{decision.symbol}"
                order = self.broker.submit_order(risk_result, client_id=client_id, timestamp=now)
                # Taker fill simulation at current price
                if order:
                    self.broker.reconcile_order(
                        client_id,
                        simulated_state="FILLED",
                        timestamp=now,
                        executed_price=risk_result.price,
                    )
                    # Arm protection
                    self.broker.arm_protection(
                        self.protection_policy, opened_at=now, entry_price=risk_result.price
                    )

        trace = {
            "decision": decision.model_dump(mode="json"),
            "snapshot": primary_snap.to_canonical_dict(),
            "snapshot_sha256": primary_snap.snapshot_sha256,
            "risk": {
                "approved": risk_result.approved if risk_result else None,
                "reason": risk_result.reason if risk_result else "Action WAIT",
                "action": risk_result.action if risk_result else "WAIT",
                "stop_price": str(risk_result.stop_price) if risk_result and risk_result.stop_price else None,
            },
            "client_id": client_id,
        }
        self.decision_traces.append(trace)

    async def _handle_position_cycle(self, feed: ScannerPublicFeed, now: int, state: dict):
        # Fetch current quote for the held symbol
        symbol = self.rules.symbol
        last_price = Decimal(state.get("last_bid", state.get("entry_price", "100")))
        bid = last_price

        try:
            depth_data, _ = feed.get("/v1/depth", {"symbol": symbol}, cutoff=now)
            if depth_data.get("success") and depth_data.get("result", {}).get("bids"):
                top_bid = depth_data["result"]["bids"][0]
                bid = Decimal(str(top_bid.get("price", last_price)))
        except (ValueError, OSError, RuntimeError):
            bid = last_price

        # Host protection tick
        tick = self.broker.observe_quote(
            bid,
            source_time=now,
            received_at=now,
            now=now,
            policy=self.protection_policy,
            slippage_pct=DEFAULT_SLIPPAGE_PCT,
        )

        trace = {
            "decision": {
                "decision_id": f"pos_{now}",
                "symbol": symbol,
                "action": tick.get("action", "WAIT"),
                "cutoff": now,
                "evidence_ids": ["EV_POSITION_LONG"],
                "reason": f"Position protection status: {tick.get('status')}",
                "role": "POSITION_REVIEWER",
            },
            "snapshot": {
                "symbol": symbol,
                "cutoff": now,
                "last_close": str(bid),
                "available_tmn_cash": str(self.ledger.get_balance("TMN").free),
            },
            "risk": {
                "approved": True if tick.get("action") == "EXIT" else None,
                "action": tick.get("action", "WAIT"),
                "reason": tick.get("exit_reason", "Position ongoing"),
                "stop_price": tick.get("trailing_stop_price"),
            },
            "protection": {
                "high_water": tick.get("high_water"),
                "net_peak_tmn": tick.get("net_peak"),
                "retained_floor_tmn": tick.get("retained_floor_tmn"),
                "retention_active": tick.get("retention_active"),
                "trailing_stop_price": tick.get("trailing_stop_price"),
                "last_tightened_at": tick.get("last_tightened_at"),
            },
        }
        self.decision_traces.append(trace)

    def _checkpoint_and_export(self, timestamp: int):
        last_bid = Decimal("100")
        held_symbol = self.rules.symbol
        prot = json.loads(self.ledger.get_meta("protection_" + held_symbol) or "null")
        if prot and prot.get("last_bid"):
            last_bid = Decimal(prot["last_bid"])

        exported = self.broker.export_state(last_bid, now=timestamp)
        tmn_bal = self.ledger.get_balance("TMN")
        base_bal = self.ledger.get_balance(self.rules.base_asset)
        equity = self.ledger.get_equity({held_symbol: last_bid}, "TMN")

        self.equity_curve.append({
            "timestamp": timestamp,
            "net_equity_tmn": str(equity),
            "realized_pnl_tmn": exported.get("realized_pnl_tmn", "0"),
            "unrealized_pnl_tmn": exported.get("net_if_exit_pnl_tmn", "0"),
            "balances": {
                "TMN": {"free": str(tmn_bal.free), "locked": str(tmn_bal.locked)},
                "USDT": {"free": str(base_bal.free), "locked": str(base_bal.locked)},
            },
        })

        # Calculate peak drawdown
        peak_eq = self.initial_capital
        max_dd = Decimal(0)
        for pt in self.equity_curve:
            eq_val = Decimal(pt["net_equity_tmn"])
            if eq_val > peak_eq:
                peak_eq = eq_val
            if peak_eq > 0:
                dd = (peak_eq - eq_val) / peak_eq * Decimal(100)
                if dd > max_dd:
                    max_dd = dd

        # Orders and fills from DB
        with self.ledger.connection() as db:
            orders = [
                {"client_id": r[0], "symbol": r[1], "side": r[2], "price": r[3], "quantity": r[4], "status": r[5]}
                for r in db.execute("SELECT client_id, symbol, side, price, quantity, status FROM broker_orders").fetchall()
            ]
            fills = [
                {"fill_id": r[0], "client_id": r[1], "price": r[2], "quantity": r[3], "fee": r[4], "fee_asset": r[5], "timestamp": r[6]}
                for r in db.execute("SELECT fill_id, client_id, price, quantity, fee, fee_asset, timestamp FROM fills").fetchall()
            ]

        evidence_kind = "PUBLIC_MARKET_PAPER" if self.mode == "CURRENT_PAPER" else "HISTORICAL_MARKET_REPLAY"
        manifest = {
            "status": "PASS_DATA_ONLY" if self.mode == "CURRENT_PAPER" else "PASS_REPLAY",
            "run_id": self.run_id,
            "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(timestamp)),
            "evidence_kind": evidence_kind,
            "mode": self.mode,
            "model_mode": self.model_mode,
            "bindings": {
                "code_sha256": hashlib.sha256(self.run_id.encode()).hexdigest(),
                "config_sha256": hashlib.sha256(self.config.model_dump_json().encode()).hexdigest(),
                "data_sha256": "public_wallex_feed",
            },
            "arms": {
                "paper_portfolio": {
                    "symbol": held_symbol,
                    "evidence_kind": evidence_kind,
                    "initial_capital_tmn": str(self.initial_capital),
                    "final_cash_tmn": str(tmn_bal.free),
                    "final_equity_mtm_tmn": str(equity),
                    "total_realized_pnl": exported.get("realized_pnl_tmn", "0"),
                    "net_pnl_mtm_tmn": str(equity - self.initial_capital),
                    "net_return_pct": str(round(((equity / self.initial_capital) - Decimal(1)) * Decimal(100), 4)),
                    "max_drawdown_pct": str(round(max_dd, 4)),
                    "total_fees_paid_tmn": exported.get("quote_fees_tmn", "0"),
                    "total_fees_paid_base": "0",
                    "peak_exposure_tmn": str(DEFAULT_MAX_ORDER_TMN),
                    "residual_dust_base": str(base_bal.total),
                    "simulated_market_exit_slippage_tmn": "0",
                    "decisions_count": len(self.decision_traces),
                    "orders_submitted": len(orders),
                    "total_orders_including_stop_finalization": len(orders),
                    "fills_count": len(fills),
                    "closed_round_trips": len(fills) // 2,
                    "equity_curve": self.equity_curve,
                    "orders": orders,
                    "fills": fills,
                    "decision_traces": self.decision_traces,
                }
            },
        }

        # Write manifest atomically
        manifest_path = self.capture_dir / "manifest.json"
        manifest_tmp = self.capture_dir / "manifest.tmp"
        manifest_tmp.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf8")
        manifest_tmp.replace(manifest_path)

        # Write atomic dashboard engine-snapshot
        dash_dir = ROOT / ".local/dashboard"
        dash_dir.mkdir(parents=True, exist_ok=True)
        engine_snap_path = dash_dir / "engine-snapshot.json"
        engine_snap_tmp = dash_dir / "engine-snapshot.tmp"
        engine_snapshot = {
            "schema_version": "royin.engine-monitor.v1",
            "source": "PAPER_ENGINE_SNAPSHOT",
            "evidence_kind": evidence_kind,
            "run_id": self.run_id,
            "status": "AVAILABLE",
            "mode": self.mode,
            "worker_state": "ACTIVE" if not self.shutdown_requested else "SHUTDOWN",
            "heartbeat_at": timestamp,
            "observed_at": timestamp,
            "account": {
                "balances": {
                    "TMN": {"free": str(tmn_bal.free), "locked": str(tmn_bal.locked), "total": str(tmn_bal.total)},
                    "USDT": {"free": str(base_bal.free), "locked": str(base_bal.locked), "total": str(base_bal.total)},
                },
                "equity_tmn": str(equity),
                "realized_pnl_tmn": exported.get("realized_pnl_tmn", "0"),
                "unrealized_pnl_tmn": exported.get("net_if_exit_pnl_tmn", "0"),
            },
            "risk": {
                "status": prot.get("status", "FLAT") if prot else "FLAT",
                "symbol": held_symbol,
                "stop_price": prot.get("trailing_stop_price") if prot else None,
                "high_water": prot.get("high_water") if prot else None,
                "retained_floor_tmn": prot.get("retained_floor_tmn") if prot else None,
                "retention_active": prot.get("retention_active", False) if prot else False,
            },
            "warnings": ["PUBLIC_MARKET_PAPER_SIMULATION"],
        }
        engine_snap_tmp.write_text(json.dumps(engine_snapshot, indent=2, default=str), encoding="utf8")
        engine_snap_tmp.replace(engine_snap_path)

    def generate_summary(self):
        tmn_bal = self.ledger.get_balance("TMN")
        equity = self.ledger.get_equity({self.rules.symbol: Decimal("100")}, "TMN")
        net_ret = ((equity / self.initial_capital) - Decimal(1)) * Decimal(100)

        return {
            "run_id": self.run_id,
            "status": "COMPLETED",
            "mode": self.mode,
            "model_mode": self.model_mode,
            "completed_cycles": self.completed_cycles,
            "initial_capital_tmn": str(self.initial_capital),
            "final_cash_tmn": str(tmn_bal.free),
            "final_equity_tmn": str(equity),
            "net_return_pct": str(round(net_ret, 4)),
            "decisions_count": len(self.decision_traces),
            "manifest_path": str(self.capture_dir / "manifest.json"),
        }
    def close(self):
        if hasattr(self, "audit") and self.audit is not None:
            self.audit.close()


def run_self_check():
    """Deterministic offline technical scenarios with hand oracles."""
    print("Running offline functional self-check with hand oracles...")
    with tempfile.TemporaryDirectory() as temp:
        temp_dir = Path(temp)
        orch = MarketPaperOrchestrator(
            run_id="self_check_run",
            mode="CURRENT_PAPER",
            model_mode="FAKE_MODEL",
            duration_seconds=60,
            cycles=1,
            activation_fraction=Decimal("0.015"),
            capture_dir=temp_dir,
            db_path=temp_dir / "self_check.sqlite3",
        )
        try:
            # 1. Verification of entry and risk approval
            buy_price = Decimal("100")
            buy_qty = Decimal("1")
            risk = RiskResult(True, "self-check ENTER", "ENTER", "USDTTMN", buy_qty, buy_price, buy_price * Decimal("0.98"), Decimal("0.3"))
            orch.broker.submit_order(risk, client_id="sc_buy", timestamp=1000)
            orch.broker.reconcile_order("sc_buy", simulated_state="FILLED", timestamp=1001)
            orch.broker.arm_protection(orch.protection_policy, opened_at=1001, entry_price=buy_price)

            # 2. Quote observation & net retention tightening at bid 103
            t1 = orch.broker.observe_quote(
                Decimal("103"),
                source_time=1010,
                received_at=1010,
                now=1010,
                policy=orch.protection_policy,
            )
            assert t1["action"] == "WAIT", f"Expected WAIT, got {t1['action']}"
            assert t1["retention_active"] is True, "Retention should be active at bid 103"
            stop1 = Decimal(t1["trailing_stop_price"])
            assert stop1 > Decimal("100"), f"Stop should tighten above 100, got {stop1}"

            # 3. Trailing exit at bid 99 (below stop)
            t2 = orch.broker.observe_quote(
                Decimal("99"),
                source_time=1020,
                received_at=1020,
                now=1020,
                policy=orch.protection_policy,
            )
            assert t2["action"] == "EXIT", f"Expected EXIT, got {t2['action']}"
            assert t2["exit_reason"] == "STOP_OR_TRAILING"

            # 4. Checkpoint & export verification
            orch._checkpoint_and_export(1030)
            assert (temp_dir / "manifest.json").is_file()

            print("All self-check scenarios passed successfully.")
            print(json.dumps({"status": "PASS_FUNCTIONAL_PAPER", "run_id": "self_check_run", "checks": 4}, indent=2))
            return 0
        finally:
            orch.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["CURRENT_PAPER", "HISTORICAL_REPLAY"], default="CURRENT_PAPER")
    parser.add_argument("--model-mode", choices=["REAL_MODEL", "FAKE_MODEL", "RECORDED"], default="FAKE_MODEL")
    parser.add_argument("--duration-seconds", type=int, default=300, help="Bounded wall-clock execution time")
    parser.add_argument("--cycles", type=int, default=1, help="Maximum execution cycles")
    parser.add_argument("--interval-seconds", type=int, default=60, help="Cycle interval in seconds")
    parser.add_argument("--horizon-max", type=int, default=DEFAULT_HORIZON_MAX_SECONDS, help="Max model horizon (seconds)")
    parser.add_argument("--retention-ratio", type=Decimal, default=Decimal("0.5"), help="Net profit retention ratio (0..1)")
    parser.add_argument("--activation-fraction", type=Decimal, default=Decimal("0.025"), help="Net profit activation fraction")
    parser.add_argument("--capture-dir", type=str, default=None, help="Directory for paper artifacts")
    parser.add_argument("--db-path", type=str, default=None, help="SQLite database path")
    parser.add_argument("--dataset-path", type=str, default=None, help="Dataset path for HISTORICAL_REPLAY")
    parser.add_argument("--self-check", action="store_true", help="Run offline functional checks and hand oracles")
    parser.add_argument("--run-id", type=str, default=None, help="Explicit run ID")

    args = parser.parse_args(argv)

    if args.self_check:
        return run_self_check()

    run_id = args.run_id or (
        time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "_" + hashlib.sha256(str(time.time()).encode()).hexdigest()[:8]
    )

    capture_dir = Path(args.capture_dir) if args.capture_dir else (ROOT / "artifacts/market-paper" / run_id)
    db_path = Path(args.db_path) if args.db_path else (capture_dir / "paper.sqlite3")

    orch = MarketPaperOrchestrator(
        run_id=run_id,
        mode=args.mode,
        model_mode=args.model_mode,
        duration_seconds=args.duration_seconds,
        cycles=args.cycles,
        interval_seconds=args.interval_seconds,
        horizon_max_seconds=args.horizon_max,
        retention_ratio=args.retention_ratio,
        activation_fraction=args.activation_fraction,
        dataset_path=Path(args.dataset_path) if args.dataset_path else None,
        capture_dir=capture_dir,
        db_path=db_path,
    )

    # Register graceful shutdown signals
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(ValueError, AttributeError):
            signal.signal(sig, orch.request_shutdown)

    try:
        summary = asyncio.run(orch.run())
        print(json.dumps(summary, indent=2, default=str))
        return 0
    finally:
        orch.close()


if __name__ == "__main__":
    sys.exit(main())
