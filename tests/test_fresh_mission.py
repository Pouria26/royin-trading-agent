"""A new operator permit preserves historical ambiguity and cannot retry or overspend."""

import asyncio
import hashlib
import json
import tempfile
import unittest
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal as D
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from royin.config import RuntimeConfig
from royin.decision import Decision, ReturnForecast
from royin.fresh_mission import FreshMissionPermit, FreshMissionTransport, authorize_fresh_mission
from royin.ledger import Ledger
from royin.live_broker import WallexLiveBroker
from royin.risk import MarketRules, RiskResult, allocate_entry_capital
from scripts import run_fresh_service
from scripts.backup_runtime_state import backup
from scripts.run_fresh_service import FreshEngine, account_matches
from tests.test_market_selection import opportunity
from tests.test_market_selection import snapshot as market_snapshot


class FreshMissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.old = Ledger(self.root / "old.sqlite3")
        self.old.set_balance("TMN", D("100000"))
        self.old.record_intent(
            client_id="historical_unknown",
            symbol="ETHTMN",
            side="BUY",
            order_type="LIMIT",
            price=D("100"),
            quantity=D("980"),
            timestamp=1000,
        )
        self.old_hash = hashlib.sha256((self.root / "old.sqlite3").read_bytes()).hexdigest()
        self.ledger = Ledger(self.root / "fresh.sqlite3")
        self.instruction = "Synthetic operator accepts a new lane; old finality remains unknown"
        self.fingerprint = hashlib.sha256(b"synthetic-account").hexdigest()
        self.permit = FreshMissionPermit(
            mission_id="fresh_test",
            revision="a" * 40,
            account_sha256=self.fingerprint,
            old_state_sha256=self.old_hash,
            authorization_sha256=hashlib.sha256(self.instruction.encode()).hexdigest(),
            start_at=1000,
            entry_end_at=2000,
            end_at=3000,
        )
        self.config = RuntimeConfig(
            WALLEX_API_KEY="synthetic-key",
            SUB_ACCOUNT_CLIENT_ID="synthetic-account",
            WALLEX_ALLOWED_MARKETS=("ETHTMN",),
        )
        self.rules = MarketRules(
            "ETHTMN", "ETH", "TMN", D(1), D(".01"), D(100000), D(".01"), D(".0025"), D(".003")
        )
        self.clock = patch("royin.fresh_mission.time.time", return_value=1010)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.calls = []

    def authorize(self):
        authorize_fresh_mission(
            self.ledger,
            self.permit,
            old_state_path=self.root / "old.sqlite3",
            operator_instruction=self.instruction,
            observed_cash_tmn=D(5000000),
            open_order_ids=[],
        )

    def make_broker(self, *, response=None):
        def handler(request):
            self.calls.append(request)
            if response is None:
                raise httpx.ReadTimeout("synthetic timeout")
            return httpx.Response(200, json=response)

        transport = FreshMissionTransport(
            self.ledger,
            self.rules,
            self.config,
            permit=self.permit,
            inner=httpx.MockTransport(handler),
        )
        client = httpx.Client(transport=transport, trust_env=False)
        self.addCleanup(client.close)
        return WallexLiveBroker(
            self.ledger,
            self.rules,
            self.config,
            http_client=client,
            enable_live_trading=True,
            run_mode="live",
        ), transport

    def evidence(self, cid, **changes):
        evidence = dict(
            source_kind="REAL_MODEL",
            action="ENTER",
            symbol="ETHTMN",
            rules_sha256=hashlib.sha256(
                json.dumps(asdict(self.rules), default=str, sort_keys=True).encode()
            ).hexdigest(),
            quote_received_at=1010,
            forecast_end_at=1800,
            target_net_approved=True,
            account_reconciled=True,
        )
        self.ledger.set_meta("fresh_evidence_" + cid, json.dumps({**evidence, **changes}))

    def worker(self):
        return self.ledger.worker(
            account_fingerprint=self.fingerprint, lock_directory=self.root / "locks"
        )

    def test_live_health_is_not_ready_for_unknown_order_or_exhausted_entry_budget(self):
        self.authorize()
        broker, _ = self.make_broker()
        self.ledger.set_meta("service_state", "RUNNING")
        self.ledger.set_meta("engine_heartbeat", "1010")
        health = run_fresh_service.read_fresh_health(self.ledger.db_path, self.permit.mission_id, now=1010)
        self.assertTrue(health["ready"])
        cid = "fresh_test_buy_1010"
        self.evidence(cid)
        risk = RiskResult(True, "synthetic admission", "ENTER", "ETHTMN", D(1400), D(100), D(98), D(420))
        with self.worker():
            broker.submit_order(risk, client_id=cid, timestamp=1010)
        health = run_fresh_service.read_fresh_health(self.ledger.db_path, self.permit.mission_id, now=1010)
        self.assertTrue(health["alive"])
        self.assertFalse(health["ready"])
        self.assertEqual(health["entry_block_reason"], "ORDER_RECONCILIATION_REQUIRED")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(hashlib.sha256((self.root / "old.sqlite3").read_bytes()).hexdigest(), self.old_hash)

    def test_model_budget_block_is_propagated_to_financial_health_without_http(self):
        self.authorize()
        WallexLiveBroker.initialize_state(self.ledger)
        signals = MagicMock(model_startup_blocked=False)
        signals.ledger = Ledger()
        signals.ledger.set_meta("entry_block_reason", "BUDGET_EXHAUSTED")
        engine = FreshEngine(self.ledger, self.permit, None, self.config, self.root,
                            client=None, feed=None, signals=signals)
        asyncio.run(engine.entry_tick(1010))
        self.assertEqual(self.ledger.get_meta("entry_block_reason"), "BUDGET_EXHAUSTED")
        signals._execute_cycle.assert_not_called()
        self.assertFalse(self.calls)

    def test_prepared_config_change_blocks_before_signal_engine_or_financial_write(self):
        self.authorize()
        WallexLiveBroker.initialize_state(self.ledger)
        self.ledger.set_meta("fresh_config_sha256", hashlib.sha256(self.config.model_dump_json().encode()).hexdigest())
        destination = self.root / "financial.sqlite3"
        backup(Path(self.ledger.db_path), destination)
        before = hashlib.sha256(destination.read_bytes()).hexdigest()
        changed = self.config.model_copy(update={"LLM_TOKEN_BUDGET": 12345})
        with patch.object(run_fresh_service, "validate_schedule"), patch.object(
            run_fresh_service, "service_paths", return_value=(self.root, None, None)
        ), patch.object(run_fresh_service, "signals_for") as signals:
            with self.assertRaisesRegex(ValueError, "runtime config"):
                asyncio.run(run_fresh_service.run(self.root, self.permit, None, changed, port=0))
            signals.assert_not_called()
        self.assertEqual(hashlib.sha256(destination.read_bytes()).hexdigest(), before)
        self.assertFalse(self.calls)

    def test_authorization_is_separate_and_does_not_rewrite_or_settle_history(self):
        self.authorize()
        self.assertEqual(
            hashlib.sha256((self.root / "old.sqlite3").read_bytes()).hexdigest(), self.old_hash
        )
        self.assertEqual(self.old.get_balance("TMN").locked, D(98000))
        self.assertEqual(self.ledger.get_balance("TMN").free, D(150000))
        record = json.loads(self.ledger.get_meta("fresh_authorization"))
        self.assertEqual(record["exchange_finality"], "UNCONFIRMED")
        self.assertEqual(record["quarantined_tmn"], "100000")
        with self.assertRaises(ValueError):
            self.authorize()
        self.assertEqual(self.ledger.get_balance("TMN").free, D(150000))

    def test_timeout_reservation_survives_restart_and_cannot_create_second_buy(self):
        self.authorize()
        broker, transport = self.make_broker()
        cid = "fresh_test_buy_1010"
        self.evidence(cid)
        risk = RiskResult(
            True, "synthetic admission", "ENTER", "ETHTMN", D(1400), D(100), D(98), D(420)
        )
        with self.worker():
            self.assertEqual(
                broker.submit_order(risk, client_id=cid, timestamp=1010)["status"], "UNKNOWN"
            )
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.ledger.get_balance("TMN").locked, D(140420))
        reopened = Ledger(self.ledger.db_path)
        restarted = FreshMissionTransport(
            reopened,
            self.rules,
            self.config,
            permit=self.permit,
            inner=httpx.MockTransport(lambda _: self.fail("POST retry")),
        )
        self.addCleanup(restarted.close)
        self.assertEqual(json.loads(reopened.get_meta("fresh_transport"))["buys"], 1)
        with self.worker(), self.assertRaises(ValueError):
            broker.submit_order(risk, client_id="fresh_test_new_buy", timestamp=1010)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(json.loads(self.ledger.get_meta("fresh_transport"))["attempts"], 1)
        self.assertEqual(transport.permit, self.permit)

    def test_stale_book_and_wrong_rules_fail_before_http_without_refunding_intent(self):
        self.authorize()
        broker, _ = self.make_broker()
        cid = "fresh_test_stale"
        self.evidence(cid, quote_received_at=1000)
        risk = RiskResult(True, "synthetic", "ENTER", "ETHTMN", D(1400), D(100), D(98), D(420))
        with self.worker():
            result = broker.submit_order(risk, client_id=cid, timestamp=1010)
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertFalse(self.calls)
        self.assertEqual(self.ledger.get_balance("TMN").locked, D(140420))
        self.assertEqual(json.loads(self.ledger.get_meta("fresh_transport"))["attempts"], 0)

    def test_backup_is_consistent_and_does_not_modify_source_or_replace_backup(self):
        output = self.root / "backup.sqlite3"
        report = backup(self.root / "old.sqlite3", output)
        self.assertEqual(report["table_rows"]["order_intents"], 1)
        self.assertEqual(
            hashlib.sha256((self.root / "old.sqlite3").read_bytes()).hexdigest(), self.old_hash
        )
        with self.assertRaises(ValueError):
            backup(self.root / "old.sqlite3", output)

    def test_real_broker_receipt_and_host_stop_use_actual_fills_after_restart(self):
        self.authorize()
        cid = "fresh_test_buy_1010"
        self.evidence(cid)

        def snapshot(order_id, side, price, qty, instant):
            return {
                "success": True,
                "result": dict(
                    clientOrderId=order_id,
                    symbol="ETHTMN",
                    side=side,
                    type="LIMIT",
                    price=price,
                    origQty=qty,
                    executedQty=qty,
                    executedSum=str(D(price) * D(qty)),
                    active=False,
                    status="FILLED",
                    fills=[
                        dict(
                            symbol="ETHTMN",
                            isBuyer=side == "BUY",
                            price=price,
                            quantity=qty,
                            sum=str(D(price) * D(qty)),
                            fee=str(D(price) * D(qty) * D(".003")),
                            feeAsset="TMN",
                            timestamp=datetime.fromtimestamp(instant, UTC).isoformat(),
                        )
                    ],
                ),
            }

        # Fill at 1011 occurs after send=1010 but before fully received response=1012.
        broker, _ = self.make_broker(response=snapshot(cid, "BUY", "100", "1400", 1011))
        risk = RiskResult(True, "synthetic", "ENTER", "ETHTMN", D(1400), D(100), D(98), D(420))
        with self.worker(), patch("royin.fresh_mission.time.time", return_value=1012):
            self.assertEqual(
                broker.submit_order(risk, client_id=cid, timestamp=1010)["status"], "FILLED"
            )
        self.assertEqual(self.ledger.get_balance("ETH").total, D(1400))
        self.ledger.set_meta("fresh_active_rules", json.dumps(asdict(self.rules), default=str))
        self.ledger.set_meta("fresh_selected_position", json.dumps(dict(forecast_end_at=1800)))
        feed = SimpleNamespace(
            get=lambda *_, **kw: (
                {
                    "success": True,
                    "result": {
                        "bid": [{"price": "96", "quantity": "10000"}],
                        "ask": [{"price": "97", "quantity": "10000"}],
                    },
                },
                1020,
            )
        )
        no_ai = SimpleNamespace(model_startup_blocked=True)
        engine = FreshEngine(
            self.ledger,
            self.permit,
            None,
            self.config,
            self.root,
            client=None,
            feed=feed,
            signals=no_ai,
        )
        original = FreshMissionTransport

        def test_transport(ledger, rules, config, *, permit):
            def handler(request):
                self.calls.append(request)
                order = json.loads(request.content)
                return httpx.Response(
                    200,
                    json=snapshot(
                        order["client_id"], "SELL", order["price"], order["quantity"], 1020
                    ),
                )

            return original(
                ledger, rules, config, permit=permit, inner=httpx.MockTransport(handler)
            )

        with (
            self.worker(),
            patch("scripts.run_fresh_service.FreshMissionTransport", side_effect=test_transport),
            patch("royin.fresh_mission.time.time", return_value=1020),
        ):
            self.assertTrue(engine.position_tick(1020))
        self.assertEqual(self.ledger.get_balance("ETH").total, 0)
        # 1400*(95-100) - 420 buy fee - 399 sell fee = -7819; no simulated settlement.
        self.assertEqual(self.ledger.get_balance("TMN").total, D("142181"))
        self.assertEqual(
            json.loads(self.ledger.get_meta("fresh_position"))["reason"], "STOP_OR_TRAILING"
        )
        self.assertEqual(len(self.calls), 2)
        with self.ledger.connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM fills").fetchone()[0], 2)
        # The original UNKNOWN and its locked reserve still exist separately.
        self.assertEqual(
            hashlib.sha256((self.root / "old.sqlite3").read_bytes()).hexdigest(), self.old_hash
        )

    def test_account_reconciliation_quarantines_old_money_and_detects_foreign_assets(self):
        self.authorize()
        WallexLiveBroker.initialize_state(self.ledger)
        from royin.markets import Balance

        balances = {"TMN": Balance(D(5000000), D(5000000), D(0))}
        self.assertTrue(account_matches(self.ledger, balances, []))
        balances["ETH"] = Balance(D(1), D(1), D(0))
        self.assertFalse(account_matches(self.ledger, balances, []))
        self.assertFalse(
            account_matches(self.ledger, {"TMN": balances["TMN"]}, ["historical_unknown"])
        )

    def dynamic_permit(self):
        self.permit = self.permit.model_copy(update=dict(capital_policy="VOLATILITY_CAPITAL_V1",
            allocation_tmn=D(4000000), max_buys=32, max_attempts=1024))
        self.authorize()

    def test_dynamic_transport_allows_variable_sized_order_only_after_bootstrap_proof(self):
        self.dynamic_permit()
        self.assertEqual(self.ledger.get_balance("TMN").total, D(4000000))
        self.ledger.set_meta("closed_round_trips", "1")  # Synthetic prior execution receipt for this unit case.
        cid = "fresh_test_dynamic_buy"
        plan = allocate_entry_capital(equity_tmn=D(5000000), free_cash_tmn=D(4000000), price_tmn=D(100),
            atr_tmn=D(1), depth_tmn=D(100000000), fee_rate=D(".003"), tick_size=D(1), bootstrap=False, risk_scale=D(1))
        self.evidence(cid, capital_plan=plan)
        response = dict(success=True, result=dict(clientOrderId=cid, symbol="ETHTMN", side="BUY", type="LIMIT",
            price="100", origQty="6000", executedQty="0", executedSum="0", status="NEW", active=True, fills=[]))
        broker, _ = self.make_broker(response=response)
        risk = RiskResult(True, "synthetic dynamic admission", "ENTER", "ETHTMN", D(6000), D(100), D(98), D(1800))
        with self.worker():
            self.assertEqual(broker.submit_order(risk, client_id=cid, timestamp=1010)["status"], "OPEN")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.ledger.get_balance("TMN").locked, D(601800))
        self.assertEqual(hashlib.sha256((self.root / "old.sqlite3").read_bytes()).hexdigest(), self.old_hash)

    def test_dynamic_transport_keeps_first_order_small_and_preserves_unknown_reserve(self):
        self.dynamic_permit()
        cid = "fresh_test_oversized_first"
        self.evidence(cid, capital_plan=dict(policy="VOLATILITY_CAPITAL_V1", approved=True,
            debit_limit_tmn="2500000", loss_fraction=".01", risk_budget_tmn="25000"))
        broker, _ = self.make_broker()
        risk = RiskResult(True, "synthetic too early scale", "ENTER", "ETHTMN", D(6000), D(100), D(98), D(1800))
        with self.worker():
            self.assertEqual(broker.submit_order(risk, client_id=cid, timestamp=1010)["status"], "UNKNOWN")
        self.assertFalse(self.calls)
        self.assertEqual(self.ledger.get_balance("TMN").locked, D(601800))
        self.assertEqual(json.loads(self.ledger.get_meta("fresh_transport"))["attempts"], 0)

    def test_daily_risk_resume_does_not_reset_orders_or_mission_drawdown(self):
        self.dynamic_permit()
        engine = FreshEngine(self.ledger, self.permit, None, self.config, self.root,
                            client=None, feed=None, signals=None)
        self.assertEqual(engine.capital_status(1010), D(1))
        def losing_trip(index, stamp):
            buy, sell = f"synthetic_buy_{index}", f"synthetic_sell_{index}"
            self.ledger.record_intent(client_id=buy, symbol="ETHTMN", side="BUY", order_type="LIMIT",
                price=D(100), quantity=D(10000), quote_fee_reserve=D(3000), quote_asset="TMN", base_asset="ETH", timestamp=stamp)
            self.ledger.record_fill(fill_id=buy, client_id=buy, price=D(100), quantity=D(10000), fee=D(3000), fee_asset="TMN", timestamp=stamp)
            self.ledger.record_intent(client_id=sell, symbol="ETHTMN", side="SELL", order_type="LIMIT",
                price=D(90), quantity=D(10000), quote_fee_reserve=D(0), quote_asset="TMN", base_asset="ETH", timestamp=stamp+1)
            self.ledger.record_fill(fill_id=sell, client_id=sell, price=D(90), quantity=D(10000), fee=D(2700), fee_asset="TMN", timestamp=stamp+1)
        losing_trip(1, 1020)
        self.assertIsNone(engine.capital_status(1030))
        self.assertEqual(self.ledger.get_meta("capital_block_reason"), "DAILY_LOSS_BUDGET")
        self.assertEqual(engine.capital_status(87430), D(".5"))
        self.assertEqual(self.ledger.get_meta("closed_round_trips"), "1")
        losing_trip(2, 87440)
        self.assertIsNone(engine.capital_status(87450))
        self.assertEqual(self.ledger.get_meta("capital_block_reason"), "MISSION_DRAWDOWN_BUDGET")
        self.assertIsNone(engine.capital_status(173850))
        self.assertEqual(self.ledger.get_meta("closed_round_trips"), "2")

    def test_missing_authorization_old_evidence_and_open_orders_cannot_bootstrap(self):
        for changes in (
            dict(operator_instruction=""),
            dict(open_order_ids=["foreign"]),
            dict(observed_cash_tmn=D(150000)),
        ):
            args = dict(
                old_state_path=self.root / "old.sqlite3",
                operator_instruction=self.instruction,
                observed_cash_tmn=D(5000000),
                open_order_ids=[],
            )
            with self.assertRaises(ValueError):
                authorize_fresh_mission(self.ledger, self.permit, **{**args, **changes})
        self.assertIsNone(self.ledger.get_meta("fresh_permit"))
        with self.assertRaises(ValueError):
            self.make_broker()

    def test_prepare_keeps_read_attempts_separate_from_uninitialized_financial_portfolio(self):
        from royin.markets import Balance
        from royin.service_contract import ServiceContract

        (self.root / ".royin-volume-id").write_text("synthetic-volume-identity")
        (self.root / "missions").mkdir()
        contract = ServiceContract(service_id="svc_prepare_regression",
            started_at=datetime.fromtimestamp(1000, UTC),
            submission_deadline_at=datetime.fromtimestamp(2000, UTC),
            trading_end_at=datetime.fromtimestamp(3000, UTC),
            finalize_start_at=datetime.fromtimestamp(2000, UTC))
        config = self.config.model_copy(update={
            "TRADING_END_AT": datetime.fromtimestamp(3000, UTC),
            "FINALIZE_START_AT": datetime.fromtimestamp(2000, UTC),
            "SUBMISSION_DEADLINE_AT": datetime.fromtimestamp(2000, UTC)})
        def snapshot(reads):
            reads.ledger.set_meta("fresh_account_gets", "3")
            return {"TMN": Balance(D(5000000), D(5000000), D(0))}, []
        with patch.object(run_fresh_service.AccountReads, "snapshot", snapshot), \
                patch("royin.model_budget.ModelBudget"), \
                patch.object(run_fresh_service.subprocess, "check_output", side_effect=["a" * 40, ""]), \
                patch.object(run_fresh_service, "signals_for", return_value=SimpleNamespace(
                    code_sha256="b" * 64, close=lambda: None)):
            result = run_fresh_service.prepare(self.root, self.permit, contract, config,
                old_state=self.root / "old.sqlite3", instruction=self.instruction)
        self.assertEqual(result["orders_sent"], 0)
        financial = Ledger(self.root / "missions" / contract.service_id / "financial.sqlite3")
        self.assertEqual(financial.get_balance("TMN").free, D(150000))
        self.assertEqual(financial.get_meta("service_state"), "PREPARED")
        self.assertIsNone(financial.get_meta("fresh_account_gets"))
        preflight = Ledger(self.root / "missions" / contract.service_id / "preflight.sqlite3")
        self.assertEqual(preflight.get_meta("fresh_account_gets"), "3")

    def test_entry_coordinator_uses_ai_selection_and_records_real_order_without_paper_fill(self):
        self.permit = self.permit.model_copy(update=dict(start_at=8000, entry_end_at=9000, end_at=10000))
        self.authorize()
        WallexLiveBroker.initialize_state(self.ledger)
        snap = market_snapshot("ETHTMN")
        # Analysis quote moved while the model was running; the host must size from the fresh book.
        opp = opportunity().model_copy(update=dict(best_ask=D(100), best_bid=D("99.99")))
        forecast = ReturnForecast(forecast_id="synthetic-forward", symbol="ETHTMN", cutoff=snap.cutoff,
            reference_price=snap.last_close, reference_kind="LAST_CLOSE", horizon_seconds=300,
            return_q10=D("-.01"), return_q50=D(".03"), return_q90=D(".05"), target_return_fraction=D(".03"),
            review_after_seconds=60, invalidation="Synthetic stop", evidence_ids=("EV_DATA_FRESH",))
        decision = Decision(decision_id="synthetic-model-choice", action="ENTER", symbol="ETHTMN", cutoff=snap.cutoff,
            snapshot_sha256=snap.snapshot_sha256, evidence_ids=("EV_DATA_FRESH",), reason="Synthetic AI interface",
            invalidation="Next candle", forecast=forecast)
        signals = MagicMock(model_startup_blocked=False, selection=None, completed_cycles=0)
        signals.ledger = Ledger()
        async def select(*_):
            signals.selection = (decision, (snap, opp), dict(host_outcome="MODEL_DECISION", evidence_kind="REAL_MODEL_ATTEMPT"))
        signals._execute_cycle = AsyncMock(side_effect=select)
        feed = SimpleNamespace(get=lambda *_,**kw:({"success":True,"result":{"bid":[{"price":"100.99","quantity":"10000"}],
            "ask":[{"price":"101","quantity":"10000"}]}}, 8105))
        engine = FreshEngine(self.ledger, self.permit, None, self.config, self.root, client=None, feed=feed, signals=signals)
        from royin.markets import Balance
        engine.reads.snapshot = lambda:({"TMN":Balance(D(5000000), D(5000000), D(0))}, [])
        engine.rules = lambda _:self.rules
        transport_type = FreshMissionTransport
        def factory(ledger, rules, config, *, permit):
            def handler(request):
                self.calls.append(request)
                p = json.loads(request.content)
                return httpx.Response(200,json={"success":True,"result":dict(clientOrderId=p["client_id"],symbol=p["symbol"],
                    side="BUY",type="LIMIT",price=p["price"],origQty=p["quantity"],executedQty="0",executedSum="0",
                    status="NEW",active=True,fills=[])})
            return transport_type(ledger, rules, config, permit=permit, inner=httpx.MockTransport(handler))
        with self.worker(), patch("scripts.run_fresh_service.FreshMissionTransport", side_effect=factory), patch("royin.fresh_mission.time.time", return_value=8105):
            asyncio.run(engine.entry_tick(8105))
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.ledger.get_balance("ETH").total, 0)
        payload = json.loads(self.calls[0].content)
        self.assertEqual(D(payload["price"]), D(101))
        self.assertLessEqual(D(payload["price"]) * D(payload["quantity"]) * D("1.003"), D(150000))
        self.assertGreater(self.ledger.get_balance("TMN").locked, D(100000))
        with self.ledger.connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM fills").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT status FROM live_broker_orders").fetchone()[0], "OPEN")
        self.assertEqual(json.loads(self.ledger.get_meta("fresh_transport"))["buys"], 1)

    def test_repricing_above_the_original_forecast_target_cannot_send_an_order(self):
        self.permit = self.permit.model_copy(update=dict(start_at=8000, entry_end_at=9000, end_at=10000))
        self.authorize()
        WallexLiveBroker.initialize_state(self.ledger)
        snap = market_snapshot("ETHTMN")
        opp = opportunity().model_copy(update=dict(best_ask=D(100), best_bid=D("99.99")))
        fc = ReturnForecast(forecast_id="synthetic-cost-reject", symbol=snap.symbol, cutoff=snap.cutoff,
            reference_price=snap.last_close, reference_kind="LAST_CLOSE", horizon_seconds=300,
            return_q10=D("-.01"), return_q50=D(".03"), return_q90=D(".05"), target_return_fraction=D(".03"),
            review_after_seconds=60, invalidation="Synthetic invalidation", evidence_ids=("EV_DATA_FRESH",))
        decision = Decision(decision_id="synthetic-expensive-entry", action="ENTER", symbol=snap.symbol,
            cutoff=snap.cutoff, snapshot_sha256=snap.snapshot_sha256, evidence_ids=("EV_DATA_FRESH",),
            reason="Synthetic case", invalidation="Next candle", forecast=fc)
        signals = MagicMock(model_startup_blocked=False, selection=None, completed_cycles=0)
        signals.ledger = Ledger()
        async def select(*_):
            signals.selection = (decision, (snap, opp), dict(host_outcome="MODEL_DECISION", evidence_kind="REAL_MODEL_ATTEMPT"))
        signals._execute_cycle = AsyncMock(side_effect=select)
        feed = SimpleNamespace(get=lambda *_,**kw:({"success":True,"result":{
            "bid":[{"price":"104.99","quantity":"10000"}],"ask":[{"price":"105","quantity":"10000"}]}},8105))
        engine = FreshEngine(self.ledger, self.permit, None, self.config, self.root, client=None, feed=feed, signals=signals)
        from royin.markets import Balance
        engine.reads.snapshot = lambda:({"TMN":Balance(D(5000000), D(5000000), D(0))}, [])
        engine.rules = lambda _:self.rules
        engine.broker = MagicMock(side_effect=AssertionError("Unprofitable target reached transport"))
        with self.worker(), patch("royin.fresh_mission.time.time", return_value=8105):
            asyncio.run(engine.entry_tick(8105))
        engine.broker.assert_not_called()
        self.assertEqual(json.loads(self.ledger.get_meta("fresh_transport"))["buys"], 0)
        gates = list(self.root.glob("entry-gate-*.json"))
        self.assertEqual(len(gates), 1)
        self.assertIn("costs", json.loads(gates[0].read_text())["reason"])

    def test_stop_trigger_survives_insufficient_depth_bounce_and_restart_without_ai(self):
        self.authorize()
        self.ledger.record_intent(client_id="fresh_test_seed", symbol="ETHTMN", side="BUY", order_type="LIMIT",
            price=D(100), quantity=D(1400), quote_fee_reserve=D(420), quote_asset="TMN", base_asset="ETH", timestamp=1010)
        self.ledger.record_fill(fill_id="synthetic_seed_fill", client_id="fresh_test_seed", price=D(100), quantity=D(1400),
            fee=D(420), fee_asset="TMN", timestamp=1011)
        self.ledger.set_meta("fresh_active_rules", json.dumps(asdict(self.rules), default=str))
        self.ledger.set_meta("fresh_selected_position", json.dumps(dict(forecast_end_at=1800)))
        feed = MagicMock()
        def book(price, qty, stamp):
            return ({"success":True,"result":{"bid":[{"price":price,"quantity":qty}],
                "ask":[{"price":str(D(price)+1),"quantity":"10000"}]}},stamp)
        feed.get.return_value = book("96", "1", 1020)
        engine = FreshEngine(self.ledger, self.permit, None, self.config, self.root, client=None,
            feed=feed, signals=None)
        with patch("royin.fresh_mission.time.time", return_value=1020):
            self.assertTrue(engine.position_tick(1020))
        self.assertEqual(json.loads(self.ledger.get_meta("fresh_position"))["reason"], "STOP_OR_TRAILING")
        self.assertEqual(self.ledger.get_balance("ETH").total, D(1400))
        restored = FreshEngine(Ledger(self.ledger.db_path), self.permit, None, self.config, self.root,
            client=None, feed=feed, signals=None)
        feed.get.return_value = book("105", "10000", 1030)
        broker, client = MagicMock(), MagicMock()
        restored.broker = lambda _:(broker,client)
        with patch("royin.fresh_mission.time.time", return_value=1030):
            self.assertTrue(restored.position_tick(1030))
        risk = broker.submit_order.call_args.args[0]
        self.assertEqual((risk.action,risk.reason,risk.quantity), ("EXIT","STOP_OR_TRAILING",D(1400)))
        self.assertFalse(self.calls)


if __name__ == "__main__":
    unittest.main()
