"""Bounded real-credit mission, independent of historical canary state and paper fills."""

import argparse
import asyncio
import hashlib
import json
import os
import signal
import sqlite3
import subprocess
import time
from contextlib import closing, suppress
from dataclasses import asdict, replace
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import httpx

from royin.config import load_config
from royin.fresh_mission import FreshMissionPermit, FreshMissionTransport, authorize_fresh_mission
from royin.ledger import Ledger
from royin.live_broker import WallexLiveBroker
from royin.logger import AuditLogger
from royin.market_data import conservative_book_price, decimal_number, decode_json
from royin.markets import (
    load_restrictions,
    parse_catalog,
    parse_credit_balances,
    parse_fee_rates,
    parse_spot_rules,
)
from royin.risk import (
    RiskPolicy,
    RiskResult,
    allocate_entry_capital,
    assess_target_net,
    evaluate_risk,
    rules_with_notional_floor,
)
from royin.service_contract import ServiceContract
from scripts.probe_wallex_account import choose_credit_account
from scripts.run_market_paper import DEFAULT_SLIPPAGE_PCT, MarketPaperOrchestrator
from scripts.run_paper_trader import ScannerPublicFeed
from scripts.run_service import atomic_json, owner_lock, service_paths

ROOT = Path(__file__).resolve().parents[1]
TERMINAL = ("FILLED", "CANCELED", "PARTIALLY_FILLED_CANCELED")


class EntrySignals(MarketPaperOrchestrator):
    """Reuse causal market research and AI validation; this override cannot submit paper orders."""

    selection = None
    signal_only = True

    async def _apply_entry_decision(self, feed, decision, batch_map, **context):
        self.selection = None
        chosen = batch_map.get(decision.symbol)
        snapshot = chosen[0] if chosen else context["primary_snap"]
        if decision.action == "ENTER" and decision.symbol in batch_map:
            self.selection = (decision, batch_map[decision.symbol], context["model_trace"])
        self.decision_traces.append(
            dict(
                decision=decision.model_dump(mode="json"),
                issued_at_utc=datetime.now(UTC).isoformat(),
                snapshot=snapshot.to_canonical_dict(),
                snapshot_sha256=snapshot.snapshot_sha256,
                model_trace=context["model_trace"],
                execution_mode="SIGNAL_ONLY_NO_PAPER_FILL",
                market_context=context["report"].get("market_context"),
            )
        )


def signals_for(contract, config, root):
    return EntrySignals(
        run_id=contract.service_id,
        model_mode="REAL_MODEL",
        config=config,
        duration_seconds=contract.duration_seconds,
        cycles=contract.cycles,
        interval_seconds=contract.poll_seconds,
        public_get_cap=contract.max_public_gets,
        order_tmn=contract.max_debit_tmn,
        minimum_notional_tmn=contract.minimum_notional_tmn,
        horizon_max_seconds=contract.horizon_max_seconds,
        capture_dir=root / "signals",
        service_contract=contract,
    )


class AccountReads:
    """Dedicated account only. Durable bounded reads; no main wallet or arbitrary routes."""

    def __init__(self, config, ledger, root, client):
        self.config, self.ledger, self.root, self.client = config, ledger, root, client

    def get(self, path):
        if path not in (
            "/sub-accounts",
            "/v1/account/balances-detail",
            "/v1/account/openOrders",
            "/v1/account/fee",
        ):
            raise ValueError("Unscoped account read")
        with self.ledger.transaction():
            attempts = int(self.ledger.get_meta("fresh_account_gets") or 0)
            if attempts >= 4096:
                raise ValueError("Account read allowance exhausted")
            self.ledger.set_meta("fresh_account_gets", str(attempts + 1))
        headers = {"x-api-key": self.config.WALLEX_API_KEY.get_secret_value()}
        if path != "/sub-accounts":
            headers["sub-account-client-id"] = self.config.SUB_ACCOUNT_CLIENT_ID.get_secret_value()
        response = self.client.get("https://api.wallex.ir" + path, headers=headers)
        raw = response.content
        digest = hashlib.sha256(raw).hexdigest()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / (digest + ".json")).write_bytes(raw)
        atomic_json(
            self.root / f"read-{attempts + 1}.json",
            dict(
                path=path, received_at=int(time.time()), status=response.status_code, sha256=digest
            ),
        )
        response.raise_for_status()
        data = decode_json(raw)
        if not isinstance(data, dict) or data.get("success") is not True:
            raise ValueError("Unsuccessful account observation")
        return data

    def snapshot(self):
        account = self.config.SUB_ACCOUNT_CLIENT_ID.get_secret_value()
        choose_credit_account(self.get("/sub-accounts"), account)
        balances = parse_credit_balances(self.get("/v1/account/balances-detail"))
        orders = self.get("/v1/account/openOrders")
        rows = orders.get("result")
        rows = rows.get("orders") if isinstance(rows, dict) else rows
        info = orders.get("result_info", {})
        if (
            not isinstance(rows, list)
            or not isinstance(info, dict)
            or info.get("total_count", len(rows)) != len(rows)
        ):
            raise ValueError("Incomplete account open order list")
        ids = [row["clientOrderId"] for row in rows]
        return balances, ids


def account_matches(ledger, balances, ids):
    """Compare total assets, keeping exchange-locked cash distinct from local fee reserves."""
    authorization = json.loads(ledger.get_meta("fresh_authorization"))
    with ledger.connection() as db:
        known = {r[0] for r in db.execute("SELECT client_id FROM live_broker_orders")}
    if not set(ids).issubset(known):
        return False
    outside = Decimal(authorization["cash_baseline_tmn"]) - Decimal(authorization["allocation_tmn"])
    assets = set(balances) | set(ledger.get_all_balances())
    return all(
        (balances[a].total if a in balances else Decimal(0))
        == ledger.get_balance(a).total + (outside if a == "TMN" else 0)
        for a in assets
    )


class FreshEngine:
    def __init__(self, ledger, permit, contract, config, root, *, client, feed, signals):
        self.ledger, self.permit, self.contract = ledger, permit, contract
        self.config, self.root, self.client, self.feed, self.signals = (
            config,
            root,
            client,
            feed,
            signals,
        )
        self.reads = AccountReads(config, ledger, root / "account-captures", client)
        self.policy = RiskPolicy(
            min(Decimal("150000"), permit.allocation_tmn),
            permit.allocation_tmn,
            Decimal(".02"),
            Decimal(".05"),
            permit.entry_end_at,
            min_seconds_before_deadline=0,
            max_stale_seconds=300,
        )

    def capital_status(self, now, inventory_tmn=Decimal(0)):
        if self.permit.capital_policy != "VOLATILITY_CAPITAL_V1":
            return Decimal(1)
        authorization = json.loads(self.ledger.get_meta("fresh_authorization"))
        equity = (Decimal(authorization["cash_baseline_tmn"]) - self.permit.allocation_tmn
                  + self.ledger.get_balance("TMN").total + inventory_tmn)
        day = datetime.fromtimestamp(now, UTC).date().isoformat()
        with self.ledger.transaction():
            if self.ledger.get_meta("risk_utc_day") != day:
                self.ledger.set_meta("risk_utc_day", day)
                self.ledger.set_meta("risk_day_start_equity", str(equity))
            peak = max(equity, Decimal(self.ledger.get_meta("risk_peak_account_equity") or str(equity)))
            self.ledger.set_meta("risk_peak_account_equity", str(peak))
            day_start = Decimal(self.ledger.get_meta("risk_day_start_equity"))
            drawdown = (peak - equity) / peak if peak else Decimal(1)
            day_loss = (day_start - equity) / day_start if day_start else Decimal(1)
            if drawdown >= Decimal(".04"):
                self.ledger.set_meta("risk_mission_halted", "1")
            reason = ("MISSION_DRAWDOWN_BUDGET" if self.ledger.get_meta("risk_mission_halted") == "1"
                      else "DAILY_LOSS_BUDGET" if day_loss >= Decimal(".02") else "")
            self.ledger.set_meta("capital_block_reason", reason)
            self.ledger.set_meta("risk_account_equity", str(equity))
        return None if reason else Decimal(".5") if drawdown >= Decimal(".01") else Decimal(1)

    def entry_gate(self, decision, reason, *, approved=False):
        record = dict(decision_id=decision.decision_id, snapshot_sha256=decision.snapshot_sha256,
            symbol=decision.symbol, cutoff=decision.cutoff, action="ENTER", approved=approved,
            reason=reason, timestamp=int(time.time()))
        name = hashlib.sha256(decision.decision_id.encode()).hexdigest()
        atomic_json(self.root/("entry-gate-"+name+".json"), record)
        if self.ledger.audit:
            self.ledger.audit.record_event("ENTRY_GATE", "RISK", record)

    def export_monitor(self, now):
        authorization = json.loads(self.ledger.get_meta("fresh_authorization"))
        outside = Decimal(authorization["cash_baseline_tmn"]) - self.permit.allocation_tmn
        balances = {a: dict(free=str(b.free), locked=str(b.locked), total=str(b.total))
                    for a, b in self.ledger.get_all_balances().items()}
        for field in ("free", "total"):
            balances["TMN"][field] = str(Decimal(balances["TMN"][field]) + outside)
        state = json.loads(self.ledger.get_meta("fresh_position") or "null")
        equity = Decimal(balances["TMN"]["total"])
        for asset, values in balances.items():
            if asset != "TMN" and Decimal(values["total"]):
                if not state or not state.get("last_bid"):
                    equity = None
                    break
                equity += Decimal(values["total"]) * Decimal(state["last_bid"])
        directory = ROOT / ".local/dashboard"
        directory.mkdir(parents=True, exist_ok=True)
        atomic_json(directory / "engine-snapshot.json", dict(schema_version="royin.engine-monitor.v1",
            source="RECORDED_FINANCIAL_LEDGER", evidence_kind="REAL_CREDIT_ACCOUNT", mode="LIVE_BOUNDED",
            run_id=self.permit.mission_id, worker_state=self.ledger.get_meta("service_state"),
            heartbeat_at=now, observed_at=now, account=dict(balances=balances, equity_tmn=str(equity) if equity is not None else None),
            risk=dict(status=self.ledger.get_meta("capital_block_reason") or self.ledger.get_meta("entry_block_reason") or "HOST_GATES_ACTIVE"),
            warnings=["RECORDED_BROKER_LEDGER_NOT_EXCHANGE_STREAM", "HISTORICAL_FINALITY_UNCONFIRMED"]))

    def rules(self, symbol):
        fees = self.reads.get("/v1/account/fee")
        maker, taker = parse_fee_rates(fees, symbol)
        if max(maker, taker) > Decimal(".003"):
            raise ValueError("Fee exceeds reviewed conservative policy")
        payload, _ = self.feed.get("/v1/markets", cutoff=int(time.time()), max_age_seconds=0)
        rules = rules_with_notional_floor(
            parse_spot_rules(payload, maker_fee_rate=maker, taker_fee_rate=taker)[symbol],
            Decimal("100000"),
        )
        catalog, _ = self.feed.get(
            "/hector/web/v1/markets", cutoff=int(time.time()), max_age_seconds=0
        )
        if (
            not parse_catalog(catalog)[symbol].is_spot
            or rules.quote_asset != "TMN"
            or f"{rules.base_asset}/TMN"
            in load_restrictions(ROOT / "config/wallex-credit-market-policy.json")
        ):
            raise ValueError("Selected market is outside the approved spot policy")
        return rules

    def broker(self, rules):
        scoped = self.config.model_copy(update={"WALLEX_ALLOWED_MARKETS": (rules.symbol,)})
        transport = FreshMissionTransport(self.ledger, rules, scoped, permit=self.permit)
        client = httpx.Client(
            transport=transport, timeout=10, follow_redirects=False, trust_env=False
        )
        return WallexLiveBroker(
            self.ledger,
            rules,
            scoped,
            http_client=client,
            enable_live_trading=True,
            run_mode="live",
            restrictions_path=ROOT / "config/wallex-credit-market-policy.json",
        ), client

    def active_order(self):
        with self.ledger.connection() as db:
            return db.execute(
                "SELECT client_id,side,status,created_at FROM live_broker_orders "
                "WHERE status NOT IN ('FILLED','CANCELED','PARTIALLY_FILLED_CANCELED')"
            ).fetchone()

    def reconcile(self, now):
        pending = self.active_order()
        if not pending:
            return False
        cid, side, status, created = pending
        from royin.risk import MarketRules

        saved = json.loads(self.ledger.get_meta("fresh_active_rules"))
        rules = MarketRules(
            **{
                k: Decimal(v) if k not in ("symbol", "base_asset", "quote_asset") else v
                for k, v in saved.items()
            }
        )
        broker, client = self.broker(rules)
        try:
            # At most one cancellation, then cumulative GET; never resubmit a timed-out POST.
            key = "fresh_cancel_" + cid
            if (
                now - created >= 30
                and status in ("OPEN", "PARTIALLY_FILLED")
                and self.ledger.get_meta(key) is None
            ):
                self.ledger.set_meta(key, str(now))
                outcome = broker.cancel_order(cid, timestamp=now)
            else:
                outcome = broker.reconcile_order(cid, timestamp=now)
            atomic_json(
                self.root / "last-order-observation.json",
                dict(client_id=cid, side=side, outcome=outcome),
            )
        finally:
            client.close()
        return True

    def position_tick(self, now):
        """Host-owned stop/trailing/deadline. No model completion is needed to request exit."""
        from royin.risk import MarketRules

        balances = self.ledger.get_all_balances()
        held = [(a, b) for a, b in balances.items() if a != "TMN" and b.total]
        if not held:
            return False
        if len(held) != 1:
            raise ValueError("More than one held asset")
        saved = json.loads(self.ledger.get_meta("fresh_active_rules"))
        rules = MarketRules(
            **{
                k: Decimal(v) if k not in ("symbol", "base_asset", "quote_asset") else v
                for k, v in saved.items()
            }
        )
        asset, balance = held[0]
        if asset != rules.base_asset:
            raise ValueError("Held asset/rules mismatch")
        state = json.loads(self.ledger.get_meta("fresh_position") or "null")
        if state is None:
            selected = json.loads(self.ledger.get_meta("fresh_selected_position"))
            with self.ledger.connection() as db:
                row = db.execute(
                    "SELECT total_cost_quote FROM cost_basis WHERE asset=?", (asset,)
                ).fetchone()
            basis = Decimal(row[0])
            entry = basis / balance.total
            stop_fraction = Decimal(selected.get("stop_fraction", ".02"))
            state = dict(
                entry_price=str(entry),
                stop_fraction=str(stop_fraction),
                high_water=str(entry),
                stop=str(entry * (1 - stop_fraction)),
                forecast_end_at=selected["forecast_end_at"],
                reason=None,
            )
            self.ledger.set_meta("fresh_position", json.dumps(state))
        if now >= min(self.permit.entry_end_at, state["forecast_end_at"]) and not state["reason"]:
            state["reason"] = "DEADLINE_OR_FORECAST"
            self.ledger.set_meta("fresh_position", json.dumps(state))
        depth, received = self.feed.get(
            "/v1/depth", {"symbol": rules.symbol}, cutoff=now, max_age_seconds=0
        )
        quantity = rules.quantize_quantity(balance.free)
        if quantity < rules.min_quantity or quantity == 0:
            self.ledger.set_meta("entry_block_reason", "UNSELLABLE_RESIDUAL")
            return True
        bid = conservative_book_price(depth, "SELL", quantity)
        if not 0 <= int(time.time()) - received <= 5:
            raise ValueError("No fresh full-quantity exit depth")
        if bid is None:
            best_bid = decimal_number(depth["result"]["bid"][0]["price"], positive=True)
            if best_bid <= Decimal(state["stop"]) and not state["reason"]:
                state["reason"] = "STOP_OR_TRAILING"
                self.ledger.set_meta("fresh_position", json.dumps(state))
            self.ledger.set_meta("entry_block_reason", "EXIT_REQUIRES_EXECUTABLE_DEPTH")
            return True
        capital_ok = self.capital_status(now, balance.total * bid)
        if capital_ok is None and not state["reason"]:
            state["reason"] = "ACCOUNT_RISK_LIMIT"
        peak = max(Decimal(state["high_water"]), bid)
        trail = max(Decimal(".01"), min(Decimal(".04"), Decimal(state.get("stop_fraction", ".02")) * Decimal(".75")))
        stop = Decimal(state["stop"])
        if peak > Decimal(state.get("entry_price", state["high_water"])) * (1 + rules.taker_fee_rate * 2):
            stop = max(stop, peak * (1 - trail))
        reason = state["reason"] or (
            "STOP_OR_TRAILING"
            if bid <= stop
            else "DEADLINE_OR_FORECAST"
            if now >= min(self.permit.entry_end_at, state["forecast_end_at"])
            else None
        )
        state.update(high_water=str(peak), stop=str(stop), reason=reason, last_bid=str(bid), last_quote_at=received)
        self.ledger.set_meta("fresh_position", json.dumps(state))
        if not reason:
            return True
        price = (bid * (1 - DEFAULT_SLIPPAGE_PCT) / rules.tick_size).to_integral_value(
            rounding=ROUND_DOWN
        ) * rules.tick_size
        if quantity < rules.min_quantity or quantity * price < rules.min_notional:
            self.ledger.set_meta("entry_block_reason", "UNSELLABLE_RESIDUAL")
            return True
        risk = RiskResult(
            True,
            reason,
            "EXIT",
            rules.symbol,
            quantity,
            price,
            None,
            quantity * price * rules.taker_fee_rate,
        )
        cid = self.permit.mission_id + "_exit_" + str(now)
        broker, client = self.broker(rules)
        try:
            broker.submit_order(risk, client_id=cid, timestamp=int(time.time()))
        finally:
            client.close()
        return True

    async def entry_tick(self, now):
        if self.signals.model_startup_blocked:
            self.ledger.set_meta("entry_block_reason", "MODEL_STATE_BLOCKED_PROTECTION_ONLY")
            return
        if now >= self.permit.entry_end_at:
            return
        if now < int(self.signals.ledger.get_meta("next_entry_analysis_at") or 0):
            return
        model_block = self.signals.ledger.get_meta("entry_block_reason")
        if model_block in (
            "BUDGET_EXHAUSTED",
            "MODEL_STATE_BLOCKED_PROTECTION_ONLY",
        ):
            self.ledger.set_meta("entry_block_reason", model_block)
            return
        if self.ledger.get_meta("entry_block_reason"):
            return
        risk_scale = self.capital_status(now)
        if risk_scale is None:
            return
        state = json.loads(self.ledger.get_meta("fresh_transport"))
        if state["buys"] >= self.permit.max_buys:
            return
        balances, ids = self.reads.snapshot()
        if not account_matches(self.ledger, balances, ids):
            self.ledger.set_meta("entry_block_reason", "ACCOUNT_RECONCILIATION_REQUIRED")
            return
        self.signals.selection = None
        await self.signals._execute_cycle(self.feed, now)
        model_block = self.signals.ledger.get_meta("entry_block_reason")
        if model_block in ("BUDGET_EXHAUSTED", "MODEL_STATE_BLOCKED_PROTECTION_ONLY"):
            self.ledger.set_meta("entry_block_reason", model_block)
        self.signals.completed_cycles += 1
        self.signals._checkpoint_and_export(int(time.time()))
        if self.signals.selection is None:
            return
        decision, (snapshot, opportunity), trace = self.signals.selection
        if trace.get("host_outcome") != "MODEL_DECISION" or trace.get("evidence_kind") != "REAL_MODEL_ATTEMPT":
            raise ValueError("Fresh entry requires a validated real-provider decision")
        if decision.forecast is None:
            raise ValueError("A valid real forecast is required")
        rules = self.rules(decision.symbol)
        depth, received = self.feed.get(
            "/v1/depth", {"symbol": rules.symbol}, cutoff=int(time.time()), max_age_seconds=0
        )
        if not 0 <= int(time.time()) - received <= 5:
            self.entry_gate(decision, "Post-inference entry book is stale")
            return
        # Reprice before reserving; the original forecast target and full debit/cost gates stay fixed.
        ask = decimal_number(depth["result"]["ask"][0]["price"], positive=True)
        price = (ask * (1 + DEFAULT_SLIPPAGE_PCT) / rules.tick_size).to_integral_value(
            rounding=ROUND_DOWN
        ) * rules.tick_size
        capital_plan = None
        if self.permit.capital_policy == "VOLATILITY_CAPITAL_V1":
            capital_plan = allocate_entry_capital(
                equity_tmn=Decimal(self.ledger.get_meta("risk_account_equity")),
                free_cash_tmn=self.ledger.get_balance("TMN").free,
                price_tmn=price, atr_tmn=snapshot.atr_14,
                depth_tmn=min(opportunity.bid_depth_tmn, opportunity.ask_depth_tmn),
                fee_rate=rules.taker_fee_rate, tick_size=rules.tick_size,
                bootstrap=int(self.ledger.get_meta("closed_round_trips") or 0) == 0,
                risk_scale=risk_scale,
            )
            if not capital_plan["approved"]:
                self.entry_gate(decision, capital_plan["reason"])
                return
            self.policy = replace(self.policy, max_order_tmn=Decimal(capital_plan["debit_limit_tmn"]),
                                  stop_loss_pct=Decimal(capital_plan["stop_fraction"]))
        risk = evaluate_risk(
            decision,
            market_rules=rules,
            policy=self.policy,
            ledger=self.ledger,
            current_time=int(time.time()),
            snapshot_sha256=snapshot.snapshot_sha256,
            candle_close_time=snapshot.cutoff,
            current_price=price,
            denied_markets=load_restrictions(ROOT / "config/wallex-credit-market-policy.json"),
        )
        if not risk.approved:
            self.entry_gate(decision, risk.reason)
            return
        executable = conservative_book_price(depth, "BUY", risk.quantity, limit_price=price)
        unwind = conservative_book_price(depth, "SELL", risk.quantity)
        if executable is None or unwind is None or unwind > executable:
            self.entry_gate(decision, "No full executable entry/unwind depth within limit")
            return
        economics = assess_target_net(
            forecast=decision.forecast,
            rules=rules,
            quantity=risk.quantity,
            entry_price=price,
            spread_pct=1 - unwind / executable,
            slippage_pct=DEFAULT_SLIPPAGE_PCT,
        )
        if not economics["approved"]:
            self.entry_gate(decision, "Conditional target does not clear fees and executable costs")
            return
        # Refresh account after inference, then fetch the final book so receipt age is at most five seconds.
        balances, ids = self.reads.snapshot()
        if not account_matches(self.ledger, balances, ids) or ids:
            raise ValueError("Account changed during inference")
        depth, received = self.feed.get(
            "/v1/depth", {"symbol": rules.symbol}, cutoff=int(time.time()), max_age_seconds=0
        )
        executable = conservative_book_price(depth, "BUY", risk.quantity, limit_price=price)
        unwind = conservative_book_price(depth, "SELL", risk.quantity)
        if executable is None or unwind is None or unwind > executable:
            self.entry_gate(decision, "Final entry/unwind book changed")
            return
        economics = assess_target_net(
            forecast=decision.forecast,
            rules=rules,
            quantity=risk.quantity,
            entry_price=price,
            spread_pct=1 - unwind / executable,
            slippage_pct=DEFAULT_SLIPPAGE_PCT,
        )
        if not economics["approved"]:
            self.entry_gate(decision, "Final conditional economics rejected")
            return
        cid = self.permit.mission_id + "_buy_" + str(int(time.time()))
        evidence = dict(
            limit_basis="POST_INFERENCE_FRESH_ASK",
            analysis_ask=str(opportunity.best_ask),
            admission_ask=str(ask),
            source_kind="REAL_MODEL",
            action="ENTER",
            symbol=rules.symbol,
            rules_sha256=hashlib.sha256(
                json.dumps(asdict(rules), default=str, sort_keys=True).encode()
            ).hexdigest(),
            quote_received_at=received,
            forecast_end_at=decision.forecast.cutoff + decision.forecast.horizon_seconds,
            target_net_approved=True,
            account_reconciled=True,
            economics=economics,
            decision=decision.model_dump(mode="json"),
            model_trace=trace,
            capital_plan=capital_plan,
        )
        with self.ledger.transaction():
            self.ledger.set_meta("fresh_evidence_" + cid, json.dumps(evidence, default=str))
            self.ledger.set_meta("fresh_active_rules", json.dumps(asdict(rules), default=str))
            self.ledger.set_meta(
                "fresh_selected_position",
                json.dumps(dict(forecast_end_at=evidence["forecast_end_at"], stop_fraction=str(self.policy.stop_loss_pct))),
            )
            self.ledger.set_meta("fresh_position", "null")
        self.entry_gate(decision, "Validated real-AI entry passed fresh account, risk and conditional economics", approved=True)
        broker, client = self.broker(rules)
        try:
            if self.ledger.audit:
                self.ledger.audit.context = dict(decision_id=decision.decision_id, symbol=rules.symbol,
                    snapshot_sha256=snapshot.snapshot_sha256, cutoff=snapshot.cutoff)
            outcome = broker.submit_order(risk, client_id=cid, timestamp=int(time.time()))
            atomic_json(
                self.root / "last-order-observation.json", dict(client_id=cid, outcome=outcome)
            )
        finally:
            client.close()


def prepare(root, permit, contract, config, *, old_state, instruction):
    validate_schedule(permit, contract, config)
    release = ROOT / "release-manifest.json"
    if release.is_file():
        revision = json.loads(release.read_text())["revision"]
    elif os.environ.get("ROYIN_RELEASE_REVISION"):
        revision = os.environ["ROYIN_RELEASE_REVISION"]
    else:
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        if subprocess.check_output(
            ["git", "diff", "HEAD", "--name-only"], cwd=ROOT, text=True
        ).strip():
            raise ValueError("Financial preparation requires committed source")
    if revision != permit.revision:
        raise ValueError("Financial release revision differs from permit")
    from royin.model_budget import ModelBudget

    ModelBudget(config, require_existing=True)
    run, _, _ = service_paths(root, contract)
    path = run / "financial.sqlite3"
    with owner_lock(root):
        if run.exists():
            raise ValueError("Fresh mission directory already exists")
        run.mkdir(parents=True)
        audit = AuditLogger(run/"financial-audit", False, run_id=permit.mission_id, mode="live",
            source="REAL_MODEL", hashes={"code":permit.revision, "contract":contract.sha256})
        ledger = Ledger(path, audit=audit)
        WallexLiveBroker.initialize_state(ledger)
        with (
            httpx.Client(timeout=10, trust_env=False, follow_redirects=False) as client,
            ledger.worker(
                account_fingerprint=permit.account_sha256, lock_directory=Path.home() / ".royin-credit-locks"
            ),
        ):
            # Read-attempt accounting must not make the financial portfolio nonempty before authorization.
            preflight = Ledger(run / "preflight.sqlite3")
            reads = AccountReads(config, preflight, run / "account-captures", client)
            balances, ids = reads.snapshot()
            if any(b.locked or (a != "TMN" and b.total) for a, b in balances.items()):
                raise ValueError("Fresh mission requires cash-only account")
            authorize_fresh_mission(
                ledger,
                permit,
                old_state_path=old_state,
                operator_instruction=instruction,
                observed_cash_tmn=balances["TMN"].total,
                open_order_ids=ids,
            )
            signals = signals_for(contract, config, run)
            try:
                ledger.set_meta("fresh_source_sha256", signals.code_sha256)
                ledger.set_meta("fresh_contract_sha256", contract.sha256)
                ledger.set_meta("fresh_config_sha256", hashlib.sha256(config.model_dump_json().encode()).hexdigest())
                ledger.set_meta("service_state", "PREPARED")
            finally:
                signals.close()
                audit.close()
    return dict(status="PREPARED_FRESH_FINANCIAL_MISSION", orders_sent=0)


async def run(root, permit, contract, config, *, port=3000):
    validate_schedule(permit, contract, config)
    run_dir, _, _ = service_paths(root, contract)
    path = run_dir / "financial.sqlite3"
    if not path.is_file():
        raise ValueError("Prepared financial state missing")
    with owner_lock(root):
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            bound = db.execute("SELECT value FROM metadata WHERE key='fresh_config_sha256'").fetchone()
        if not bound or bound[0] != hashlib.sha256(config.model_dump_json().encode()).hexdigest():
            raise ValueError("Prepared financial runtime config missing or changed")
        audit = AuditLogger(run_dir/"financial-audit", False, run_id=permit.mission_id, mode="live",
            source="REAL_MODEL", hashes={"code":permit.revision, "contract":contract.sha256})
        ledger = Ledger(path, audit=audit)
        WallexLiveBroker.initialize_state(ledger)
        if (
            ledger.get_meta("fresh_permit") != permit.canonical()
            or ledger.get_meta("fresh_contract_sha256") != contract.sha256
        ):
            raise ValueError("Financial permit or scheduling contract changed")
        signals = signals_for(contract, config, run_dir)
        if ledger.get_meta("fresh_source_sha256") != signals.code_sha256:
            signals.close()
            raise ValueError("Prepared financial source changed")
        stop = asyncio.Event()
        server = fresh_health_server(path, permit.mission_id, port)
        old_handlers = {
            sig: signal.signal(sig, lambda *_: stop.set())
            for sig in (signal.SIGINT, signal.SIGTERM)
        }
        try:
            with (
                ledger.worker(
                    account_fingerprint=permit.account_sha256, lock_directory=Path.home() / ".royin-credit-locks"
                ),
                httpx.Client(timeout=10, follow_redirects=False, trust_env=False) as client,
            ):
                feed = ScannerPublicFeed(
                    run_dir / "public",
                    max_requests=contract.max_public_gets,
                    before_request=signals._reserve_public_request,
                    service_contract=contract,
                )
                feed.requests = int(signals.ledger.get_meta("engine_public_attempts") or 0)
                engine = FreshEngine(
                    ledger,
                    permit,
                    contract,
                    config,
                    run_dir,
                    client=client,
                    feed=feed,
                    signals=signals,
                )
                ledger.set_meta("service_state", "RUNNING")
                if signals.model_startup_blocked:
                    ledger.set_meta("entry_block_reason", "MODEL_STATE_BLOCKED_PROTECTION_ONLY")
                while not stop.is_set() and int(time.time()) < permit.end_at:
                    now = int(time.time())
                    ledger.set_meta("engine_heartbeat", str(now))
                    try:
                        if (run_dir / "STOP_NEW_ENTRIES").exists():
                            ledger.set_meta("entry_block_reason", "OPERATOR_STOP_NEW_ENTRIES")
                        if not engine.reconcile(now) and not engine.position_tick(now):
                            await engine.entry_tick(now)
                    except (
                        ValueError,
                        OSError,
                        RuntimeError,
                        sqlite3.Error,
                        httpx.HTTPError,
                        ArithmeticError,
                        KeyError,
                        TypeError,
                    ) as exc:
                        ledger.set_meta("last_cycle_error", type(exc).__name__)
                        atomic_json(
                            run_dir / "last-error.json", dict(error_type=type(exc).__name__, at=now)
                        )
                    else:
                        ledger.set_meta("last_cycle_error", "")
                    engine.export_monitor(int(time.time()))
                    with suppress(TimeoutError):
                        await asyncio.wait_for(stop.wait(), timeout=contract.poll_seconds)
                residual = {
                    a: str(b.total)
                    for a, b in ledger.get_all_balances().items()
                    if a != "TMN" and b.total
                }
                state = (
                    "PAUSED_RESTART"
                    if stop.is_set()
                    else (
                        "STOPPED_OPEN_RECONCILIATION_REQUIRED"
                        if residual or engine.active_order()
                        else "COMPLETED_FLAT"
                    )
                )
                ledger.set_meta("service_state", state)
                atomic_json(
                    run_dir / "financial-result.json",
                    dict(
                        status=state,
                        residual=residual,
                        allocation_cash_tmn=str(ledger.get_balance("TMN").total),
                        evidence_kind="REAL_CREDIT_ACCOUNT",
                        historical_finality="UNCONFIRMED_OPERATOR_AUTHORIZED_NEW_MISSION",
                    ),
                )
                # Keep terminal health observable, without restarting inference or order submission.
                while not stop.is_set() and int(time.time()) < permit.end_at + 3600:
                    ledger.set_meta("engine_heartbeat", str(int(time.time())))
                    with suppress(TimeoutError):
                        await asyncio.wait_for(stop.wait(), timeout=30)
        finally:
            for sig, handler in old_handlers.items():
                signal.signal(sig, handler)
            signals.close()
            audit.close()
            server.shutdown()
            server.server_close()


def validate_schedule(permit, contract, config):
    if (
        permit.start_at != int(contract.started_at.timestamp())
        or permit.entry_end_at != int(contract.finalize_start_at.timestamp())
        or permit.end_at != int(contract.effective_end_at.timestamp())
        or contract.max_debit_tmn != Decimal("150000")
        or config.financial_end_at != contract.effective_end_at
        or contract.finalize_start_at != config.FINALIZE_START_AT
        or not config.WALLEX_API_KEY
        or not config.SUB_ACCOUNT_CLIENT_ID
        or hashlib.sha256(config.SUB_ACCOUNT_CLIENT_ID.get_secret_value().encode()).hexdigest()
        != permit.account_sha256
    ):
        raise ValueError("Fresh financial permit and runtime schedule/account must match")
    permit.canonical()


def read_fresh_health(path, mission_id, *, now=None):
    now = int(time.time()) if now is None else now
    body = dict(mode="LIVE_BOUNDED", mission_id=mission_id, ready=False, alive=False)
    try:
        with closing(sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=1)) as db:
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            meta = dict(db.execute("SELECT key,value FROM metadata WHERE key IN "
                "('service_state','engine_heartbeat','entry_block_reason','fresh_permit','fresh_transport',"
                "'capital_block_reason','last_cycle_error')"))
            pending = db.execute("SELECT status FROM live_broker_orders WHERE status NOT IN "
                "('FILLED','CANCELED','PARTIALLY_FILLED_CANCELED') LIMIT 1").fetchone()
            held = any(Decimal(free) + Decimal(locked) > 0 for free, locked in db.execute(
                "SELECT free,locked FROM balances WHERE asset != 'TMN' LIMIT 33"))
        permit = FreshMissionPermit.model_validate_json(meta["fresh_permit"])
        permit.canonical()
        if permit.mission_id != mission_id:
            raise ValueError("Mission binding mismatch")
        used = json.loads(meta["fresh_transport"])
        age = now - int(meta.get("engine_heartbeat", "0"))
        block = meta.get("entry_block_reason") or meta.get("capital_block_reason") or meta.get("last_cycle_error")
        if pending:
            block = "ORDER_RECONCILIATION_REQUIRED"
        elif held:
            block = "POSITION_OPEN_PROTECTION_ONLY"
        elif not permit.start_at <= now < permit.entry_end_at:
            block = "OUTSIDE_ENTRY_WINDOW"
        elif used["buys"] >= permit.max_buys or used["attempts"] >= permit.max_attempts:
            block = "FINANCIAL_ALLOWANCE_EXHAUSTED"
        body.update(status=meta.get("service_state"), heartbeat_age_seconds=age,
                    entry_block_reason=block, alive=0 <= age <= 300,
                    ready=0 <= age <= 300 and meta.get("service_state") == "RUNNING" and not block)
    except (sqlite3.Error, OSError, ValueError, KeyError, TypeError, ArithmeticError):
        pass
    return body


def fresh_health_server(path, mission_id, port):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path not in ("/healthz", "/readyz"):
                self.send_error(404)
                return
            body = read_fresh_health(path, mission_id)
            raw = json.dumps(body).encode()
            self.send_response(
                200 if body["alive" if self.path == "/healthz" else "ready"] else 503
            )
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    return server


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--state-root", type=Path, default=Path("/state"))
    parser.add_argument("--policy", type=Path, default=Path("/state/service-contract.json"))
    parser.add_argument("--permit", type=Path, default=Path("/state/fresh-permit.json"))
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--old-state", type=Path)
    parser.add_argument("--authorization-file", type=Path)
    args = parser.parse_args(argv)
    try:
        contract = ServiceContract.model_validate_json(args.policy.read_text())
        permit = FreshMissionPermit.model_validate_json(args.permit.read_text())
        config = load_config(args.env_file)
        if args.prepare:
            report = prepare(
                args.state_root,
                permit,
                contract,
                config,
                old_state=args.old_state,
                instruction=args.authorization_file.read_text(encoding="utf-8"),
            )
            print(json.dumps(report))
        else:
            asyncio.run(run(args.state_root, permit, contract, config))
        return 0
    except (ValueError, OSError, TypeError, sqlite3.Error) as exc:
        print(json.dumps(dict(status="BLOCKED_FRESH_SERVICE", error_type=type(exc).__name__)))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
