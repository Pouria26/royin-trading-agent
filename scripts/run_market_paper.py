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
from dataclasses import asdict, replace
from decimal import ROUND_DOWN, Decimal, localcontext
from pathlib import Path

from royin.agent import (
    RoleRunEnvelope,
    decide_role,
)
from royin.broker import PaperBroker
from royin.config import RuntimeConfig, load_config
from royin.datasets import load_dataset
from royin.decision import (
    MAX_RESEARCH_SYMBOLS,
    EntryOpportunityContext,
    MarketCatalogCandidate,
    MarketResearchUniverse,
    PositionReviewContext,
    RoleDecisionProposal,
    bind_decision,
)
from royin.evaluation import source_bundle_sha256
from royin.features import extract_features
from royin.ledger import Ledger, validate_decimal
from royin.logger import AuditLogger
from royin.market_context import catalog_return
from royin.market_data import (
    CandleSeries,
    aggregate_closed,
    conservative_book_price,
    decimal_number,
    parse_history,
)
from royin.markets import load_restrictions, parse_catalog
from royin.model_budget import BudgetBlocked, ModelBudget
from royin.risk import (
    MarketRules,
    PositionProtectionPolicy,
    RiskPolicy,
    RiskResult,
    assess_target_net,
    evaluate_risk,
)

try:
    from scripts.run_paper_trader import (
        ScannerPublicFeed,
        catalog_candidates,
        scan_current_market,
    )
except ImportError:
    from run_paper_trader import (
        ScannerPublicFeed,
        catalog_candidates,
        scan_current_market,
    )

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]

# Default parameters
DEFAULT_CAPITAL_TMN = Decimal("5000000")
DEFAULT_MAX_ORDER_TMN = Decimal("100000")
DEFAULT_MIN_NOTIONAL_TMN = Decimal("100000")
DEFAULT_MIN_QUANTITY_USDT = Decimal("1.0")
DEFAULT_TAKER_FEE_RATE = Decimal("0.0030")
DEFAULT_SLIPPAGE_PCT = Decimal("0.0005")
DEFAULT_HORIZON_MAX_SECONDS = 36000  # User-selected maximum; the contest deadline may shorten it.
DEFAULT_STOP_PCT = Decimal("0.03")
DEFAULT_TRAIL_PCT = Decimal("0.02")
DEFAULT_CHECKPOINT_PCT = Decimal("0.03")
DEFAULT_MAX_LOSS_TMN = Decimal("75000")


def build_default_rules(symbol="USDTTMN", tick_size=Decimal("1"), step_size=None):
    base = symbol.replace("TMN", "").replace("USDT", "") or "USDT"
    # Historical fixture assumptions only; current entries require observed spot rules.
    if step_size is None:
        step_size = Decimal("0.01") if base == "USDT" else Decimal("0.00001")
    min_quantity = DEFAULT_MIN_QUANTITY_USDT if base == "USDT" else Decimal("0.0001")
    return MarketRules(
        symbol=symbol,
        base_asset=base,
        quote_asset="TMN" if symbol.endswith("TMN") else "USDT",
        tick_size=tick_size,
        step_size=step_size,
        min_notional=DEFAULT_MIN_NOTIONAL_TMN,
        min_quantity=min_quantity,
        maker_fee_rate=Decimal("0.0025"),
        taker_fee_rate=DEFAULT_TAKER_FEE_RATE,
    )


def build_default_protection_policy(
    deadline_utc,
    hard_holding_seconds=DEFAULT_HORIZON_MAX_SECONDS,
    retention_ratio=Decimal("0.5"),
    activation_fraction=Decimal("0.025"),
    stop_pct=DEFAULT_STOP_PCT,
    trailing_pct=DEFAULT_TRAIL_PCT,
    checkpoint_pct=DEFAULT_CHECKPOINT_PCT,
    max_loss_tmn=DEFAULT_MAX_LOSS_TMN,
):
    return PositionProtectionPolicy(
        initial_stop_pct=stop_pct,
        trailing_drawdown_pct=trailing_pct,
        checkpoint_profit_pct=checkpoint_pct,
        review_interval_seconds=1800,
        hard_holding_seconds=hard_holding_seconds,
        deadline_utc=deadline_utc,
        exit_buffer_seconds=300,
        max_quote_age_seconds=120,
        max_loss_tmn=max_loss_tmn,
        profit_retention_ratio=retention_ratio,
        net_activation_fraction=activation_fraction,
    )


def public_symbols(feed, *, cutoff):
    payload, received = feed.get("/hector/web/v1/markets", {}, cutoff=cutoff)
    catalog = parse_catalog(payload)
    return payload, received, {symbol for symbol in catalog}


ROUND_TRIP_COST_FRACTION = Decimal("0.006") + 2 * DEFAULT_SLIPPAGE_PCT


def fee_aware_entry(snapshot, *, hold_seconds: int, safety_factor: Decimal = Decimal("1.0")) -> bool:
    """Require trend plus an expected move that clears round-trip costs.

    ATR is a per-bar range estimate; scaling by sqrt(horizon bars) is a conservative
    heuristic, not a guarantee. The strict trend spread avoids chop entries whose
    gross move cannot clear the ~0.7% round-trip fee + slippage.
    """
    if "EV_TREND_BULLISH" not in snapshot.evidences or snapshot.last_close <= 0:
        return False
    if "EV_BB_EXPANDING" not in snapshot.evidences:
        return False
    bars = Decimal(hold_seconds) / Decimal(snapshot.interval_seconds)
    if bars <= 0:
        return False
    with localcontext() as ctx:
        ctx.prec = 36
        expected_move = (snapshot.atr_14 / snapshot.last_close) * bars.sqrt()
    return expected_move >= ROUND_TRIP_COST_FRACTION * safety_factor



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
        public_get_cap: int = 32,
        horizon_max_seconds: int = DEFAULT_HORIZON_MAX_SECONDS,
        retention_ratio: Decimal = Decimal("0.5"),
        activation_fraction: Decimal = Decimal("0.025"),
        order_tmn: Decimal = DEFAULT_MAX_ORDER_TMN,
        stop_pct: Decimal = DEFAULT_STOP_PCT,
        trail_pct: Decimal = DEFAULT_TRAIL_PCT,
        checkpoint_pct: Decimal = DEFAULT_CHECKPOINT_PCT,
        max_loss_tmn: Decimal = DEFAULT_MAX_LOSS_TMN,
        initial_capital: Decimal = DEFAULT_CAPITAL_TMN,
        dataset_path: Path | None = None,
        capture_dir: Path | None = None,
        db_path: Path | None = None,
        config: RuntimeConfig | None = None,
    ):
        if mode not in ("CURRENT_PAPER","HISTORICAL_REPLAY") or model_mode not in ("REAL_MODEL","FAKE_MODEL","RECORDED"):
            raise ValueError("Unknown execution/evidence mode")
        if (type(duration_seconds) is not int or not 1 <= duration_seconds <= 36000
                or type(cycles) is not int or cycles < (1 if mode == "CURRENT_PAPER" else 0)
                or type(interval_seconds) is not int or not 1 <= interval_seconds <= 3600):
            raise ValueError("Invalid bounded execution limits")
        if mode == "CURRENT_PAPER" and (type(horizon_max_seconds) is not int or not 300 <= horizon_max_seconds <= 36000):
            raise ValueError("Current holding policy must stay between five minutes and ten hours")
        if type(public_get_cap) is not int or not 16 <= public_get_cap <= 4096:
            raise ValueError("Public GET cap must be 16..4096")
        if mode == "CURRENT_PAPER" and interval_seconds > 60:
            raise ValueError("Current position protection must poll at least every60 seconds")
        if model_mode == "RECORDED" or (mode == "HISTORICAL_REPLAY" and model_mode != "FAKE_MODEL"):
            raise ValueError("This replay requires an explicit rule; recorded/model portfolio dispatch is not implemented")
        self.run_id = run_id
        self.mode = mode
        self.model_mode = model_mode
        self.duration_seconds = duration_seconds
        self.max_cycles = cycles
        self.interval_seconds = interval_seconds
        self.public_get_cap = public_get_cap
        self.horizon_max_seconds = horizon_max_seconds
        self.retention_ratio = retention_ratio
        self.activation_fraction = activation_fraction
        self.order_tmn = order_tmn
        self.stop_pct = stop_pct
        self.trail_pct = trail_pct
        self.checkpoint_pct = checkpoint_pct
        self.max_loss_tmn = max_loss_tmn
        self.initial_capital = initial_capital
        self.dataset_path = dataset_path
        self.config = config or load_config()
        source_root = Path(__file__).resolve().parents[1]
        self.code_sha256 = source_bundle_sha256(source_root, [
            *source_root.glob("src/royin/*.py"), *source_root.glob("scripts/*.py"), source_root/"requirements.lock",
            source_root/"config/llm-budget-policy.json"])
        self.dataset_sha256 = None
        self.public_feed = None
        # This is a continuation of an existing paid experiment, never a zero-spend bootstrap.
        self.budget = (ModelBudget(self.config, require_existing=True)
                       if self.model_mode == "REAL_MODEL" else None)

        self.capture_dir = capture_dir or (ROOT / "artifacts/market-paper" / self.run_id)
        self.capture_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path or (self.capture_dir / "paper.sqlite3")

        self.audit = AuditLogger(self.capture_dir / "audit", False, run_id=self.run_id)
        self.ledger = Ledger(self.db_path, audit=self.audit)
        binding = hashlib.sha256(f"paper:{self.run_id}".encode()).hexdigest()
        self.ledger.initialize_portfolio(self.initial_capital, quote_asset="TMN", binding=binding)
        old_binding = self.ledger.get_meta("engine_source_sha256")
        if old_binding is not None and old_binding != self.code_sha256:
            self.audit.close()
            raise ValueError("Run revision changed; preserve the previous run and use an explicit new run")
        self.ledger.set_meta("engine_source_sha256",self.code_sha256)
        profile = json.dumps([mode,model_mode,duration_seconds,horizon_max_seconds,str(order_tmn),
            str(initial_capital),str(stop_pct),str(trail_pct),str(activation_fraction),str(retention_ratio)],sort_keys=True)
        old_profile = self.ledger.get_meta("engine_profile")
        if old_profile is not None and old_profile != profile:
            self.audit.close()
            raise ValueError("Run settings changed; do not reinterpret an existing portfolio")
        self.ledger.set_meta("engine_profile",profile)
        polling_profile = json.dumps([cycles, interval_seconds, public_get_cap])
        previous_polling = self.ledger.get_meta("engine_polling_profile")
        if previous_polling is not None and previous_polling != polling_profile:
            raise ValueError("Run polling/budget settings changed; use a new run")
        self.ledger.set_meta("engine_polling_profile", polling_profile)
        created = self.ledger.get_meta("engine_started_at")
        self.run_started_at = int(created) if created is not None else int(time.time())
        if created is None:
            self.ledger.set_meta("engine_started_at",str(self.run_started_at))

        self.run_envelope = None
        if self.model_mode == "REAL_MODEL":
            self.run_envelope = RoleRunEnvelope(self.budget,
                duration_seconds=self.duration_seconds, scope_id=self.run_id)

        self.rules = build_default_rules("USDTTMN")
        self.broker = PaperBroker(self.ledger, self.rules)

        deadline = self.run_started_at + self.duration_seconds
        if self.mode == "CURRENT_PAPER":
            deadline = min(deadline, self.run_started_at + (self.max_cycles-1)*self.interval_seconds)
        if self.config.CHALLENGE_END_AT:
            deadline = min(deadline, int(self.config.CHALLENGE_END_AT.timestamp()))
        self.protection_policy = build_default_protection_policy(
            deadline_utc=deadline,
            hard_holding_seconds=self.horizon_max_seconds,
            retention_ratio=self.retention_ratio,
            activation_fraction=self.activation_fraction,
            stop_pct=self.stop_pct,
            trailing_pct=self.trail_pct,
            checkpoint_pct=self.checkpoint_pct,
            max_loss_tmn=self.max_loss_tmn,
        )
        self.base_protection_policy = self.protection_policy
        planned_windows = []
        if self.mode == "CURRENT_PAPER" and self.duration_seconds == 10800 and deadline-self.run_started_at == 10800:
            planned_windows = [dict(window_id=i+1,start=self.run_started_at+i*5400,
                end=self.run_started_at+(i+1)*5400) for i in range(2)]
        self.ledger.set_meta("engine_evaluation_windows",json.dumps(planned_windows))
        held_symbol = self.ledger.get_meta("active_symbol")
        if held_symbol:
            saved_rules = self.ledger.get_meta("bound_market_rules")
            if saved_rules is None:
                raise ValueError("Active market lacks durable observed spot rules")
            values = json.loads(saved_rules)
            held_rules = MarketRules(**{k:v if k in ("symbol","base_asset","quote_asset") else Decimal(v)
                                        for k,v in values.items()})
            if held_rules.symbol != held_symbol:
                raise ValueError("Stored market binding mismatch")
            if self.ledger.get_balance(held_rules.base_asset).total > 0:
                self.rules = held_rules
                self.broker = PaperBroker(self.ledger, held_rules)
                saved = self.ledger.get_meta("bound_position_policy")
                if saved is None:
                    raise ValueError("Held position lacks a durable protection policy")
                values = json.loads(saved)
                for key, value in asdict(self.base_protection_policy).items():
                    if isinstance(value, Decimal):
                        values[key] = Decimal(values[key])
                self.protection_policy = PositionProtectionPolicy(**values)

        self.risk_policy = RiskPolicy(
            max_order_tmn=self.order_tmn,
            max_exposure_tmn=self.order_tmn,
            stop_loss_pct=self.stop_pct,
            max_drawdown_pct=Decimal("0.05"),
            deadline_utc=deadline,
            min_seconds_before_deadline=300,
        )

        self.decision_traces = []
        self.equity_curve = []
        self.errors = []
        previous = self.capture_dir / "manifest.json"
        if previous.exists():
            saved = json.loads(previous.read_text(encoding="utf-8"))
            if saved.get("run_id") != self.run_id or saved["bindings"]["code_sha256"] != self.code_sha256:
                raise ValueError("Previous manifest does not bind this run/revision")
            arm = saved["arms"]["paper_portfolio"]
            self.decision_traces = arm["decision_traces"]
            self.equity_curve = arm["equity_curve"]
            self.errors = saved.get("errors",[])
            self.restored_captures = saved.get("public_captures",[])
        else:
            self.restored_captures = []
        self.shutdown_requested = False
        self.start_time = None
        self.completed_cycles = int(self.ledger.get_meta("engine_completed_cycles") or "0")

    def _reserve_public_request(self):
        attempts = int(self.ledger.get_meta("engine_public_attempts") or "0")
        if attempts >= self.public_get_cap:
            raise ValueError("Durable public GET cap reached")
        self.ledger.set_meta("engine_public_attempts", str(attempts + 1))

    def request_shutdown(self, *args):
        self.shutdown_requested = True

    async def run_historical_replay(self, dataset_path: Path):
        self.dataset_sha256 = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
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
            stop_pct=self.stop_pct,
            trailing_pct=self.trail_pct,
            checkpoint_pct=self.checkpoint_pct,
            max_loss_tmn=self.max_loss_tmn,
        )
        self.risk_policy = RiskPolicy(
            max_order_tmn=self.order_tmn,
            max_exposure_tmn=self.order_tmn,
            stop_loss_pct=self.stop_pct,
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
                        "role": "HOST_PROTECTION",
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
                # Fee-aware causal entry: trend plus expected move above round-trip costs.
                action = "ENTER" if (
                    fee_aware_entry(snap, hold_seconds=self.horizon_max_seconds)
                    and available_cash >= DEFAULT_MIN_NOTIONAL_TMN
                ) else "WAIT"
                fc = None
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
                        denied_markets=load_restrictions(ROOT/"config/wallex-credit-market-policy.json"),
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
        if pending_entry is not None:
            self.broker.reconcile_order(
                pending_entry["client_id"],
                simulated_state="CANCELED",
                timestamp=final_cutoff,
            )
            pending_entry = None
        prot_state = json.loads(self.ledger.get_meta("protection_" + self.rules.symbol) or "null")
        if prot_state and prot_state.get("status") == "OPEN":
            self.broker.finalize_portfolio(
                candles[min(warmup + total_steps - 1, len(candles) - 1)].close,
                timestamp=final_cutoff,
                slippage_pct=DEFAULT_SLIPPAGE_PCT,
            )
        self._checkpoint_and_export(final_cutoff)
        return self.generate_summary()

    async def run(self):
        with self.ledger.worker():
            return await self._run_owned()

    async def _run_owned(self):
        if self.mode == "HISTORICAL_REPLAY":
            ds_path = self.dataset_path or (
                ROOT / "data/t02/normalized-c8c0f4903f000a992688564e8a90b54daab68aeff8ca7c998a7d933b41c7b5c1.json"
            )
            return await self.run_historical_replay(ds_path)

        self.start_time = time.monotonic() - max(0,int(time.time())-self.run_started_at)
        feed = ScannerPublicFeed(self.capture_dir / "raw", max_requests=self.public_get_cap,
            before_request=self._reserve_public_request)
        feed.captures = list(self.restored_captures)
        feed.requests = int(self.ledger.get_meta("engine_public_attempts") or len(feed.captures))
        self.ledger.set_meta("engine_public_attempts", str(feed.requests))
        self.public_feed = feed
        self.ledger.set_meta("engine_lifecycle", "RUNNING")
        now_ts = int(time.time())
        self.ledger.set_meta("engine_heartbeat", str(now_ts))
        if self.completed_cycles == 0 and self.ledger.get_meta("engine_evaluation_windows") != "[]":
            # Publish the planned windows before the first inference/outcome, not after scoring.
            self._checkpoint_and_export(now_ts)

        while not self.shutdown_requested and self.completed_cycles < self.max_cycles:
            elapsed = time.monotonic() - self.start_time
            if elapsed >= self.duration_seconds:
                break
            # Leave room for a position review and a fresh terminal liquidation quote.
            if feed.requests >= self.public_get_cap - 8:
                break

            cycle_start = time.time()
            now_ts = int(cycle_start)
            try:
                await self._execute_cycle(feed, now_ts)
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, IndexError, ArithmeticError) as exc:
                logger.error("Paper cycle failed: %s", type(exc).__name__)
                self.errors.append({"cycle": self.completed_cycles, "error_type": type(exc).__name__, "timestamp": now_ts})

            self.completed_cycles += 1
            self.ledger.set_meta("engine_completed_cycles", str(self.completed_cycles))
            self._checkpoint_and_export(int(time.time()))

            if self.completed_cycles < self.max_cycles:
                sleep_time = max(0.5, self.interval_seconds - (time.time() - cycle_start))
                # Interruptible sleep
                for _ in range(int(sleep_time * 2)):
                    if self.shutdown_requested or (time.monotonic() - self.start_time >= self.duration_seconds):
                        break
                    await asyncio.sleep(0.5)

        self._finish_current(feed)
        self._checkpoint_and_export(int(time.time()))
        return self.generate_summary()

    def _finish_current(self, feed):
        """End a paper session using a fresh executable bid, never an old valuation."""
        quantity = self.ledger.get_balance(self.rules.base_asset).total
        if quantity > 0:
            try:
                now = int(time.time())
                depth, received = feed.get("/v1/depth", {"symbol":self.rules.symbol},
                    cutoff=now, max_age_seconds=0)
                if depth.get("success") is not True or not 0 <= int(time.time())-received <= 60:
                    raise ValueError("No fresh terminal quote")
                bid = conservative_book_price(depth,"SELL",self.rules.quantize_quantity(quantity))
                if bid is None:
                    raise ValueError("Terminal book cannot fill the held paper quantity")
                self._record_inventory_value(bid)
                settlement = self.broker.finalize_portfolio(bid, timestamp=received,
                    initial_capital=self.initial_capital, slippage_pct=DEFAULT_SLIPPAGE_PCT)
                key = "protection_" + self.rules.symbol
                state = json.loads(self.ledger.get_meta(key) or "null")
                if state:
                    state.update(last_bid=str(bid), last_source_time=received,
                        status="CLOSED" if settlement["status"] == "FINALIZED" else "RESIDUAL")
                    self.ledger.set_meta(key, json.dumps(state))
                self.decision_traces.append({"decision":{"action":"EXIT", "role":"HOST_SESSION_END",
                    "symbol":self.rules.symbol, "cutoff":received, "reason":"Bounded paper session ended"},
                    "settlement":settlement})
            except (ValueError, OSError, RuntimeError, KeyError, IndexError, TypeError, ArithmeticError) as exc:
                self.errors.append({"phase":"SESSION_FINALIZATION", "error_type":type(exc).__name__,
                    "timestamp":int(time.time())})
        residual = self.ledger.get_balance(self.rules.base_asset).total
        self.ledger.set_meta("engine_lifecycle", "STOPPED_OPEN" if residual else "STOPPED_FLAT")
        if residual:
            self.errors.append({"phase":"SESSION_RESIDUAL", "error_type":"UnliquidatedPaperAsset",
                "timestamp":int(time.time())})

    async def _execute_cycle(self, feed: ScannerPublicFeed, now: int):
        self.ledger.set_meta("engine_heartbeat", str(now))

        # Check if position is currently held
        held_qty = self.ledger.get_balance(self.rules.base_asset).total
        prot_state = json.loads(self.ledger.get_meta("protection_" + self.rules.symbol) or "null")

        if held_qty > 0 and prot_state and prot_state.get("status") == "OPEN":
            # Position holding & protection tick
            await self._handle_position_cycle(feed, now, prot_state)
        elif held_qty > 0:
            self.ledger.set_meta("entry_block_reason", "UNPROTECTED_OR_RESIDUAL_INVENTORY")
            self.shutdown_requested = True
        else:
            # Flat: scanning & entry analysis
            if feed.requests > self.public_get_cap - 16:
                return
            cutoff = now // 300 * 300
            next_analysis = self.ledger.get_meta("next_entry_analysis_at")
            if next_analysis is not None and now < int(next_analysis):
                return
            if self.ledger.get_meta("last_entry_cutoff") == str(cutoff):
                return
            # Claim before I/O, including failures; bucket boundaries/restart grant no new call.
            with self.ledger.transaction():
                self.ledger.set_meta("last_entry_cutoff",str(cutoff))
                self.ledger.set_meta("next_entry_analysis_at",str(now+300))
            await self._handle_entry_cycle(feed, now)

    async def _handle_entry_cycle(self, feed: ScannerPublicFeed, now: int):
        input_state = self._replay_input_state()
        payload, received, symbols = public_symbols(feed, cutoff=now)
        available_cash = self.ledger.get_balance(self.rules.quote_asset).free
        scan_options = dict(
            account_symbols=symbols,
            account_as_of=received,
            interval_seconds=300,
            round_trip_fee_pct=Decimal("0.006"),
            min_depth_tmn=Decimal("1000000"),
            max_spread_pct=Decimal("0.005"),
            available_tmn_cash=available_cash,
            diversify=True,
            tmn_only=True,
            use_spot_rules=True,
        )
        liquid = ()
        if self.model_mode == "REAL_MODEL":
            liquid = catalog_candidates(payload, account_symbols=symbols, cutoff=int(time.time()),
                received_at=received,account_as_of=received,tmn_only=True)
        bootstrap_attempts = []
        if self.model_mode == "REAL_MODEL":
            report = {"status":"NO_ELIGIBLE_LIQUID_RESEARCH_UNIVERSE", "batch":()}
            # Bootstrap data is not a trade pick; one broken market must not close the full universe.
            for row in liquid[:3]:
                report = scan_current_market(feed, **scan_options,batch_limit=1,selected_symbols=[row.symbol])
                bootstrap_attempts.append({"symbol":row.symbol,"status":report.get("status"),
                    "accepted":bool(report.get("batch")),"errors":report.get("errors",[])})
                if report.get("batch"):
                    break
        else:
            report = scan_current_market(feed, **scan_options,batch_limit=5)

        batch_list = [
            item for item in report.get("batch", [])
            if item.snapshot.symbol.endswith("TMN")
        ]
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
                "bootstrap_attempts":bootstrap_attempts,
            }
            self.decision_traces.append(trace)
            return

        batch_map = {item.snapshot.symbol: (item.snapshot, item.opportunity) for item in batch_list}
        primary_snap, primary_opp = batch_list[0].snapshot, batch_list[0].opportunity

        decision = None
        model_trace = {}

        if self.model_mode == "REAL_MODEL" and self.run_envelope:
            catalog_rows = {row["symbol"]:row for row in payload["result"]["markets"]}
            coverage_history = json.loads(self.ledger.get_meta("engine_research_coverage") or "{}")
            universe = MarketResearchUniverse(catalog_sha256=liquid[0].catalog_sha256, observed_at=received,
                markets=tuple(MarketCatalogCandidate(symbol=row.symbol,
                    price_tmn=decimal_number(catalog_rows[row.symbol]["price"],positive=True),
                    turnover_tmn=row.turnover_tmn, return_24h=catalog_return(catalog_rows[row.symbol]),
                    research_requests=coverage_history.get(row.symbol,{}).get("requested",0),
                    accepted_research_count=coverage_history.get(row.symbol,{}).get("accepted",0))
                    for row in liquid if row.symbol in report["market_rules"]),
                unavailable_symbols=tuple(row["symbol"] for row in bootstrap_attempts
                    if not row["accepted"] and row["symbol"] in report["market_rules"]))
            model_deadline = time.monotonic()+60
            async def load_selected(selected):
                for symbol in selected:
                    counts = coverage_history.setdefault(symbol,{"requested":0,"accepted":0})
                    counts["requested"] += 1
                self.ledger.set_meta("engine_research_coverage",json.dumps(coverage_history))
                def collect():
                    previous_deadline = feed.deadline_monotonic
                    feed.deadline_monotonic = min(model_deadline-1,time.monotonic()+35)
                    try:
                        return scan_current_market(feed,**scan_options,batch_limit=MAX_RESEARCH_SYMBOLS,selected_symbols=selected)
                    finally:
                        feed.deadline_monotonic = previous_deadline
                job = asyncio.create_task(asyncio.to_thread(collect))
                try:
                    researched = await asyncio.shield(job)
                except asyncio.CancelledError:
                    # Join the owned collector before releasing its worker/DB or exporting terminal state.
                    await asyncio.gather(job, return_exceptions=True)
                    raise
                if researched.get("cutoff") != primary_snap.cutoff:
                    raise ValueError("Model-selected research crossed its closed-candle cutoff")
                report.clear()
                report.update(researched)
                for item in researched["batch"]:
                    coverage_history[item.snapshot.symbol]["accepted"] += 1
                self.ledger.set_meta("engine_research_coverage",json.dumps(coverage_history))
                report["coverage"]["unique_requested_symbols"] = len(coverage_history)
                report["coverage"]["unique_accepted_symbols"] = sum(
                    counts["accepted"] > 0 for counts in coverage_history.values())
                report["coverage"]["model_accepted_symbols"] = [item.snapshot.symbol for item in researched["batch"]]
                report["coverage"]["model_visible_catalog"] = len(universe.markets)
                report["coverage"]["model_requested_symbols"] = list(selected)
                model_trace["research_errors"] = researched.get("errors", [])
                return {item.snapshot.symbol:(item.snapshot,item.opportunity) for item in report["batch"]}
            try:
                decision = await decide_role(
                    primary_snap,
                    market_batch=batch_map,
                    market_universe=universe,
                    market_loader=load_selected,
                    config=self.config,
                    budget=self.budget,
                    run_envelope=self.run_envelope,
                    model_trace=model_trace,
                    allowed_symbols=tuple(row.symbol for row in universe.markets),
                    horizon_bounds=(300, self.horizon_max_seconds),
                    remaining_seconds=max(0, min(self.horizon_max_seconds,
                        self.protection_policy.deadline_utc - self.protection_policy.exit_buffer_seconds - int(time.time()))),
                    timeout_seconds=60,
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
        elif self.model_mode == "REAL_MODEL":
            # No silent fake fallback: missing model runtime means no entry.
            self.ledger.set_meta("entry_block_reason", "MODEL_RUNTIME_UNAVAILABLE")
            decision = RoleDecisionProposal(
                role="ENTRY_ANALYST",
                action="WAIT",
                symbol=primary_snap.symbol,
                cutoff=primary_snap.cutoff,
                snapshot_sha256=primary_snap.snapshot_sha256,
                evidence_ids=("EV_POSITION_FLAT",),
                reason="REAL_MODEL requested but the shared model runtime is unavailable",
                invalidation="Model runtime restored",
            )
        else:
            chosen = next(
                (item for item in batch_list
                 if fee_aware_entry(item.snapshot, hold_seconds=self.horizon_max_seconds)),
                None,
            )
            action = "ENTER" if chosen and available_cash >= DEFAULT_MIN_NOTIONAL_TMN else "WAIT"
            base_snap = chosen.snapshot if chosen else primary_snap
            base_opp = chosen.opportunity if chosen else primary_opp
            decision = RoleDecisionProposal(
                role="ENTRY_ANALYST",
                action=action,
                symbol=base_snap.symbol,
                cutoff=base_snap.cutoff,
                snapshot_sha256=base_snap.snapshot_sha256,
                opportunity_sha256=base_opp.sha256,
                evidence_ids=tuple(base_snap.evidences.keys())[:3] or ("EV_DATA_FRESH",),
                reason=(
                    "Fee-aware trend entry: expected move clears round-trip costs"
                    if action == "ENTER"
                    else "Waiting: no candidate clears the fee-aware trend gate"
                ),
                invalidation="Next closed candle",
            )

        # Host risk evaluation
        risk_result = None
        client_id = None
        execution_evidence = None
        if decision.action == "ENTER" and decision.symbol in batch_map:
            submit_time = int(time.time())
            chosen_snap, _chosen_opp = batch_map[decision.symbol]
            if (decision.forecast is not None
                    and decision.forecast.cutoff + decision.forecast.horizon_seconds <= submit_time):
                raise ValueError("Forecast horizon already expired before execution")
            target_rules = report.get("market_rules",{}).get(decision.symbol)
            if target_rules is None:
                raise ValueError("Selected market lacks observed spot trading rules")
            execution_price = _chosen_opp.best_ask
            if execution_price is None or not 0 <= submit_time-_chosen_opp.depth_received_at <= 60:
                raise ValueError("Entry requires a fresh observed ask price")
            # Reserve at a bounded limit, so a worse fresh ask cannot exceed the cash ceiling.
            execution_price = (execution_price*(1+DEFAULT_SLIPPAGE_PCT)/target_rules.tick_size).to_integral_value(
                rounding=ROUND_DOWN)*target_rules.tick_size
            risk_result = evaluate_risk(
                decision,
                market_rules=target_rules,
                policy=self.risk_policy,
                ledger=self.ledger,
                current_time=submit_time,
                snapshot_sha256=chosen_snap.snapshot_sha256,
                candle_close_time=chosen_snap.cutoff,
                current_price=execution_price,
                denied_markets=load_restrictions(ROOT/"config/wallex-credit-market-policy.json"),
            )

            actual_fill_price = None
            if risk_result.approved:
                try:
                    depth, received = feed.get("/v1/depth",{"symbol":decision.symbol},
                        cutoff=int(time.time()),max_age_seconds=0)
                    actual_fill_price = conservative_book_price(depth,"BUY",risk_result.quantity,
                        limit_price=risk_result.price)
                    submit_time = int(time.time())
                    if actual_fill_price is None or not 0 <= submit_time-received <= 60:
                        raise ValueError("No full executable buy within the reserved limit")
                    if decision.forecast is not None and decision.forecast.cutoff+decision.forecast.horizon_seconds <= submit_time:
                        raise ValueError("Forecast expired while fetching the executable book")
                    risk_result = evaluate_risk(decision,market_rules=target_rules,policy=self.risk_policy,
                        ledger=self.ledger,current_time=submit_time,snapshot_sha256=chosen_snap.snapshot_sha256,
                        candle_close_time=chosen_snap.cutoff,current_price=execution_price,
                        denied_markets=load_restrictions(ROOT/"config/wallex-credit-market-policy.json"))
                    execution_evidence = dict(assumption="WORST_CONSUMED_ASK_WITHIN_LIMIT",
                        limit_price=str(risk_result.price),fill_price=str(actual_fill_price),received_at=received)
                    if risk_result.approved and decision.forecast is not None:
                        unwind_bid = conservative_book_price(depth,"SELL",risk_result.quantity)
                        if unwind_bid is None or unwind_bid > actual_fill_price:
                            raise ValueError("No conservative full-quantity unwind quote")
                        economics = assess_target_net(forecast=decision.forecast,rules=target_rules,
                            quantity=risk_result.quantity,entry_price=risk_result.price,
                            spread_pct=1-unwind_bid/actual_fill_price,slippage_pct=DEFAULT_SLIPPAGE_PCT)
                        execution_evidence["target_net_check"] = economics
                        if not economics["approved"]:
                            risk_result = replace(risk_result,approved=False,
                                reason="Rejected: conditional target cannot clear executable entry and exit costs")
                except (ValueError,OSError,RuntimeError,KeyError,IndexError,TypeError,ArithmeticError) as exc:
                    risk_result = replace(risk_result,approved=False,
                        reason="Executable entry book rejected: "+type(exc).__name__)

            if risk_result.approved:
                # Rebind execution rules/broker to the model-selected market.
                self.rules = target_rules
                self.broker = PaperBroker(self.ledger, target_rules)
                self.ledger.set_meta("approved_decision_"+decision.decision_id,
                    json.dumps({"decision":decision.model_dump(mode="json"),"model_trace":model_trace,
                        "snapshot":chosen_snap.to_canonical_dict(),"opportunity":_chosen_opp.model_dump(mode="json")}))
                self.ledger.set_meta("bound_market_rules", json.dumps(asdict(target_rules),default=str))
                self.ledger.set_meta("active_symbol", decision.symbol)
                client_id = f"paper_enter_{submit_time}_{decision.symbol}"
                order = self.broker.submit_order(risk_result, client_id=client_id, timestamp=submit_time)
                # Taker fill simulation at current price
                if order:
                    self.broker.reconcile_order(
                        client_id,
                        simulated_state="FILLED",
                        timestamp=submit_time,
                        executed_price=actual_fill_price,
                    )
                    # Arm protection
                    horizon = decision.horizon_seconds or self.horizon_max_seconds
                    if decision.forecast is not None:
                        horizon = decision.forecast.cutoff + decision.forecast.horizon_seconds - submit_time
                    self.protection_policy = replace(self.base_protection_policy,
                        hard_holding_seconds=horizon,
                        review_interval_seconds=max(1, min(decision.review_after_seconds or 1800, horizon)))
                    self.ledger.set_meta("bound_position_policy", json.dumps(asdict(self.protection_policy), default=str))
                    self.broker.arm_protection(
                        self.protection_policy, opened_at=submit_time, entry_price=actual_fill_price
                    )

        trace = {
            "issued_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "decision": decision.model_dump(mode="json"),
            "snapshot": batch_map.get(decision.symbol, (primary_snap, None))[0].to_canonical_dict(),
            "snapshot_sha256": decision.snapshot_sha256,
            "model_trace": model_trace,
            "host_input_state": input_state,
            "opportunity": batch_map.get(decision.symbol, (None,None))[1].model_dump(mode="json")
                if decision.symbol in batch_map else None,
            "market_context": report.get("market_context"),
            "bootstrap_attempts":bootstrap_attempts,
            "execution":execution_evidence,
            "coverage": report.get("coverage"),
            "risk": {
                "approved": risk_result.approved if risk_result else None,
                "reason": risk_result.reason if risk_result else "Action WAIT",
                "action": risk_result.action if risk_result else "WAIT",
                "stop_price": str(risk_result.stop_price) if risk_result and risk_result.stop_price else None,
            },
            "client_id": client_id,
        }
        self.decision_traces.append(trace)

    async def _review_position(self, feed, now, bid, state):
        """Model may exit early; host protection has already run and cannot be weakened."""
        interval = 300
        cutoff = now // interval * interval
        if cutoff < state["opened_at"]:
            return  # No closed post-entry candle exists yet; protection still ran.
        start = cutoff - 40 * interval
        try:
            history, _ = feed.get("/v1/udf/history", {"symbol":self.rules.symbol,
                "resolution":"1", "from":start, "to":cutoff}, cutoff=now)
            series = aggregate_closed(parse_history(history,start=start,end=cutoff,
                interval_seconds=60,cutoff=now), interval)
            if series.incomplete_bins:
                raise ValueError("Incomplete position review history")
            qty = self.ledger.get_balance(self.rules.base_asset).total
            snap = extract_features(series,self.rules.symbol,cutoff=cutoff,current_position_base=qty,
                available_tmn_cash=self.ledger.get_balance("TMN").free)
            exported = self.broker.export_state(bid,now=now)
            position = PositionReviewContext(quantity=qty,cost_basis_tmn=Decimal(exported["cost_basis_tmn"]),
                net_liquidation_tmn=Decimal(exported["net_liquidation_tmn"]),
                opened_at=state["opened_at"],observed_at=now,hard_exit_at=state["hard_exit_at"],
                initial_stop_price=Decimal(state["initial_stop_price"]),
                trailing_stop_price=Decimal(state["trailing_stop_price"]),
                checkpoint_profit_pct=self.protection_policy.checkpoint_profit_pct)
            model_trace = {}
            input_state = self._replay_input_state()
            model_task = asyncio.create_task(decide_role(snap,position=position,config=self.config,budget=self.budget,
                run_envelope=self.run_envelope,model_trace=model_trace,allowed_symbols=(self.rules.symbol,),
                remaining_seconds=state["hard_exit_at"]-now,horizon_bounds=(300,self.horizon_max_seconds)))
            try:
                while not model_task.done():
                    done, _ = await asyncio.wait((model_task,),timeout=3)
                    if not done:
                        current = json.loads(self.ledger.get_meta("protection_"+self.rules.symbol) or "null")
                        _, protected = await self._handle_position_cycle(feed,int(time.time()),current,allow_model=False)
                        if protected.get("action") == "EXIT":
                            return
                decision = await model_task
            finally:
                if not model_task.done():
                    model_task.cancel()
                    await asyncio.gather(model_task,return_exceptions=True)
            trace = {"issued_at_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "decision":decision.model_dump(mode="json"),"model_trace":model_trace,
                "snapshot":snap.to_canonical_dict(),"snapshot_sha256":snap.snapshot_sha256,
                "host_input_state":input_state}
            self.decision_traces.append(trace)
            if decision.action == "EXIT":
                protection_key = "protection_"+self.rules.symbol
                current = json.loads(self.ledger.get_meta(protection_key) or "null")
                if current and self.ledger.get_balance(self.rules.base_asset).total > 0:
                    current["pending_exit_reason"] = "MODEL_EXIT"
                    self.ledger.set_meta(protection_key,json.dumps(current,sort_keys=True))
                observed = int(time.time())
                depth, received = feed.get("/v1/depth",{"symbol":self.rules.symbol},cutoff=observed,max_age_seconds=0)
                if depth.get("success") is not True:
                    raise ValueError("Exit requires a fresh executable quote")
                if not 0 <= int(time.time())-received <= 60:
                    raise ValueError("Exit quote expired")
                fresh_bid = conservative_book_price(depth,"SELL",self.rules.quantize_quantity(
                    self.ledger.get_balance(self.rules.base_asset).total))
                if fresh_bid is None:
                    raise ValueError("Exit book cannot fill the held paper quantity")
                trace["execution_assumption"] = "WORST_CONSUMED_BID_PLUS_SLIPPAGE_BUFFER"
                trace["settlement"] = self.broker.finalize_portfolio(fresh_bid,timestamp=received,
                    slippage_pct=DEFAULT_SLIPPAGE_PCT)
        except (BudgetBlocked, ValueError, OSError, KeyError, IndexError, TypeError) as exc:
            self.errors.append({"phase":"POSITION_REVIEW", "error_type":type(exc).__name__,"timestamp":now})

    async def _handle_position_cycle(self, feed: ScannerPublicFeed, now: int, state: dict, *, allow_model=True):
        # Fetch current quote for the held symbol
        symbol = self.rules.symbol
        last_price = Decimal(state.get("last_bid", state.get("entry_price", "100")))
        bid = last_price
        source_time = state.get("last_source_time", state.get("opened_at", now))
        received_at = now
        execution_available = False

        try:
            depth_data, received = feed.get("/v1/depth", {"symbol": symbol}, cutoff=now,max_age_seconds=0)
            quantity = self.rules.quantize_quantity(self.ledger.get_balance(self.rules.base_asset).total)
            executable_bid = conservative_book_price(depth_data,"SELL",quantity)
            bid = executable_bid if executable_bid is not None else decimal_number(
                depth_data["result"]["bid"][0]["price"],positive=True)
            source_time = received
            received_at = received
            execution_available = executable_bid is not None
        except (ValueError, OSError, RuntimeError, KeyError, IndexError, TypeError, ArithmeticError):
            bid = last_price

        if execution_available and 0 <= max(now, received_at)-source_time <= 60:
            self._record_inventory_value(bid)
        # Host protection tick
        tick = self.broker.observe_quote(
            bid,
            source_time=source_time,
            received_at=received_at,
            now=max(now, received_at),
            policy=self.protection_policy,
            slippage_pct=DEFAULT_SLIPPAGE_PCT,
            execution_available=execution_available,
        )

        trace = {
            "decision": {
                "decision_id": f"pos_{now}",
                "symbol": symbol,
                "action": tick.get("action", "WAIT"),
                "cutoff": now,
                "evidence_ids": ["EV_POSITION_LONG"],
                "reason": f"Position protection status: {tick.get('status')}",
                "role": "HOST_PROTECTION",
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
            "execution_assumption": "WORST_CONSUMED_BID_PLUS_SLIPPAGE_BUFFER",
            "execution_available":execution_available,
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

        if (allow_model and tick.get("review_due") and self.model_mode == "REAL_MODEL"
                and self.run_envelope is not None and tick.get("status") == "PROTECTED"):
            await self._review_position(feed, max(now, received_at), bid, tick)
        return bid, tick

    def _replay_input_state(self):
        with self.ledger.connection() as db:
            count = db.execute("SELECT COUNT(*) FROM audit_outbox WHERE event_type IN ('INTENT','FILL','CANCEL')").fetchone()[0]
        return dict(accounting_event_count=count,balances={asset:dict(free=str(b.free),locked=str(b.locked))
            for asset,b in self.ledger.get_all_balances().items()})

    def _record_inventory_value(self, price):
        validate_decimal(price, "observed inventory price", strictly_positive=True)
        value = self.ledger.get_balance(self.rules.base_asset).total * price
        key = "peak_inventory_value_TMN"
        self.ledger.set_meta(key, str(max(Decimal(self.ledger.get_meta(key) or "0"), value)))

    def _checkpoint_and_export(self, timestamp: int):
        last_bid = Decimal("1")  # No price affects valuation when base inventory is zero.
        held_symbol = self.rules.symbol
        prot = json.loads(self.ledger.get_meta("protection_" + held_symbol) or "null")
        if prot and prot.get("last_bid"):
            last_bid = Decimal(prot["last_bid"])
        base_bal = self.ledger.get_balance(self.rules.base_asset)
        if base_bal.total > 0:
            if not prot or not prot.get("last_bid"):
                raise ValueError("Positive inventory lacks an observed valuation price")
            validate_decimal(last_bid, "last observed bid", strictly_positive=True)
            if 0 <= timestamp-int(prot.get("last_source_time", 0)) <= self.protection_policy.max_quote_age_seconds:
                self._record_inventory_value(last_bid)

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
                self.rules.base_asset: {"free": str(base_bal.free), "locked": str(base_bal.locked)},
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
            accounting_events = [dict(event_type=kind,payload={k:v for k,v in json.loads(payload).items()
                if k != "_audit_origin"}) for kind,payload in db.execute(
                    "SELECT event_type,payload FROM audit_outbox WHERE event_type IN ('INTENT','FILL','CANCEL') ORDER BY id")]

        evidence_kind = "PUBLIC_MARKET_PAPER" if self.mode == "CURRENT_PAPER" else "HISTORICAL_MARKET_REPLAY"
        captures = self.public_feed.captures if self.public_feed is not None else []
        manifest = {
            "status": "PARTIAL" if self.errors else ("PASS_DATA_ONLY" if self.mode == "CURRENT_PAPER" else "PASS_REPLAY"),
            "run_id": self.run_id,
            "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(timestamp)),
            "evidence_kind": evidence_kind,
            "mode": self.mode,
            "model_mode": self.model_mode,
            "bindings": {
                "code_sha256": self.code_sha256,
                "config_sha256": hashlib.sha256(self.config.model_dump_json().encode()).hexdigest(),
                "data_sha256": self.dataset_sha256 or hashlib.sha256(json.dumps(captures,sort_keys=True).encode()).hexdigest(),
            },
            "public_captures": captures,
            "public_get_attempts": int(self.ledger.get_meta("engine_public_attempts") or "0"),
            "public_get_cap": self.public_get_cap,
            "worker_state": self.ledger.get_meta("engine_lifecycle"),
            "evaluation_windows": json.loads(self.ledger.get_meta("engine_evaluation_windows") or "[]"),
            "errors": self.errors,
            "protection_policy": asdict(self.protection_policy),
            "risk_policy": asdict(self.risk_policy),
            "model_budget_policy_sha256": self.budget.policy_hash if self.budget is not None else None,
            "accounting": dict(schema_version=1,events=accounting_events,
                balances=self._replay_input_state()["balances"],realized_pnl_tmn=str(self.ledger.get_realized_pnl())),
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
                    "peak_exposure_tmn": self.ledger.get_meta("peak_inventory_value_TMN") or "0",
                    "peak_exposure_definition": "ONE_POSITION_OBSERVED_INVENTORY_VALUE_AT_FILL_OR_QUOTE",
                    "residual_dust_base": str(base_bal.total),
                    "simulated_market_exit_slippage_tmn": "0",
                    "decisions_count": len(self.decision_traces),
                    "orders_submitted": len(orders),
                    "total_orders_including_stop_finalization": len(orders),
                    "fills_count": len(fills),
                    "closed_round_trips": int(self.ledger.get_meta("closed_round_trips") or "0"),
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
            "worker_state": self.ledger.get_meta("engine_lifecycle") or "NOT_RUNNING",
            "heartbeat_at": timestamp,
            "observed_at": timestamp,
            "account": {
                "balances": {
                    "TMN": {"free": str(tmn_bal.free), "locked": str(tmn_bal.locked), "total": str(tmn_bal.total)},
                    self.rules.base_asset: {"free": str(base_bal.free), "locked": str(base_bal.locked), "total": str(base_bal.total)},
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
        try:
            engine_snap_tmp.replace(engine_snap_path)
        except PermissionError:
            # A running dashboard can briefly hold the snapshot on Windows; the run's
            # own manifest/DB remain authoritative, so do not abort the replay.
            logger.warning("Dashboard snapshot is locked; keeping the previous copy")
            engine_snap_tmp.unlink(missing_ok=True)

    def generate_summary(self):
        tmn_bal = self.ledger.get_balance("TMN")
        protection = json.loads(self.ledger.get_meta("protection_" + self.rules.symbol) or "null")
        if self.ledger.get_balance(self.rules.base_asset).total > 0 and not protection:
            raise ValueError("Open position has no observed valuation price")
        prices = {self.rules.symbol: Decimal(protection["last_bid"])} if protection else {}
        equity = self.ledger.get_equity(prices, "TMN")
        net_ret = ((equity / self.initial_capital) - Decimal(1)) * Decimal(100)

        return {
            "run_id": self.run_id,
            "status": "PARTIAL" if self.errors or self.ledger.get_balance(self.rules.base_asset).total else "COMPLETED",
            "mode": self.mode,
            "model_mode": self.model_mode,
            "completed_cycles": self.completed_cycles,
            "initial_capital_tmn": str(self.initial_capital),
            "final_cash_tmn": str(tmn_bal.free),
            "final_equity_tmn": str(equity),
            "net_return_pct": str(round(net_ret, 4)),
            "decisions_count": len(self.decision_traces),
            "valid_model_decisions": sum((row.get("model_trace") or {}).get("host_outcome") == "MODEL_DECISION"
                for row in self.decision_traces),
            "model_host_fallbacks": sum((row.get("model_trace") or {}).get("host_outcome") == "HOST_FALLBACK"
                for row in self.decision_traces),
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
    parser.add_argument("--public-get-cap", type=int, default=32, help="Durable public GET budget,16..4096; includes failed attempts")
    parser.add_argument("--horizon-max", type=int, default=DEFAULT_HORIZON_MAX_SECONDS, help="Max model horizon (seconds)")
    parser.add_argument("--retention-ratio", type=Decimal, default=Decimal("0.5"), help="Net profit retention ratio (0..1)")
    parser.add_argument("--activation-fraction", type=Decimal, default=Decimal("0.025"), help="Net profit activation fraction")
    parser.add_argument("--capture-dir", type=str, default=None, help="Directory for paper artifacts")
    parser.add_argument("--db-path", type=str, default=None, help="SQLite database path")
    parser.add_argument("--dataset-path", type=str, default=None, help="Dataset path for HISTORICAL_REPLAY")
    parser.add_argument("--order-tmn", type=Decimal, default=DEFAULT_MAX_ORDER_TMN, help="Paper order notional in TMN")
    parser.add_argument("--stop-pct", type=Decimal, default=DEFAULT_STOP_PCT, help="Initial hard stop fraction")
    parser.add_argument("--trail-pct", type=Decimal, default=DEFAULT_TRAIL_PCT, help="Trailing drawdown fraction")
    parser.add_argument("--checkpoint-pct", type=Decimal, default=DEFAULT_CHECKPOINT_PCT, help="Profit checkpoint fraction")
    parser.add_argument("--max-loss-tmn", type=Decimal, default=DEFAULT_MAX_LOSS_TMN, help="Max net position loss in TMN")
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

    try:
        orch = MarketPaperOrchestrator(
            run_id=run_id,
            mode=args.mode,
            model_mode=args.model_mode,
            duration_seconds=args.duration_seconds,
            cycles=args.cycles,
            interval_seconds=args.interval_seconds,
            public_get_cap=args.public_get_cap,
            horizon_max_seconds=args.horizon_max,
            retention_ratio=args.retention_ratio,
            activation_fraction=args.activation_fraction,
            order_tmn=args.order_tmn,
            stop_pct=args.stop_pct,
            trail_pct=args.trail_pct,
            checkpoint_pct=args.checkpoint_pct,
            max_loss_tmn=args.max_loss_tmn,
            dataset_path=Path(args.dataset_path) if args.dataset_path else None,
            capture_dir=capture_dir,
            db_path=db_path,
        )
    except BudgetBlocked as exc:
        print(json.dumps(dict(status="BLOCKED", reason=str(exc), model_http=0, orders_sent=0)))
        return 2

    # Register graceful shutdown signals
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(ValueError, AttributeError):
            signal.signal(sig, orch.request_shutdown)

    try:
        summary = asyncio.run(orch.run())
        print(json.dumps(summary, indent=2, default=str))
        return 0 if summary["status"] == "COMPLETED" else 2
    finally:
        orch.close()


if __name__ == "__main__":
    sys.exit(main())
