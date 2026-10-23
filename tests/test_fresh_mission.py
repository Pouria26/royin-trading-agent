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
from royin.risk import MarketRules, RiskResult
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

    def test_entry_coordinator_uses_ai_selection_and_records_real_order_without_paper_fill(self):
        self.permit = self.permit.model_copy(update=dict(start_at=8000, entry_end_at=9000, end_at=10000))
        self.authorize()
        WallexLiveBroker.initialize_state(self.ledger)
        snap = market_snapshot("ETHTMN")
        opp = opportunity().model_copy(update=dict(best_ask=D(101), best_bid=D("100.99")))
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
        self.assertGreater(self.ledger.get_balance("TMN").locked, D(100000))
        with self.ledger.connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM fills").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT status FROM live_broker_orders").fetchone()[0], "OPEN")
        self.assertEqual(json.loads(self.ledger.get_meta("fresh_transport"))["buys"], 1)

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
