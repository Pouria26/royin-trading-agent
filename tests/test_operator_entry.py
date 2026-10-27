"""Operator authority and real broker boundaries with synthetic HTTP only."""

import hashlib
import json
import unittest
from datetime import UTC, datetime
from decimal import Decimal as D
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx

from royin.fresh_mission import FreshMissionTransport
from royin.live_broker import WallexLiveBroker
from royin.markets import Balance
from royin.operator_entry import (
    AUTH_KEY,
    STATE_KEY,
    authorize_operator_entry,
    authorize_operator_runtime,
    digest,
    ingest_operator_requests,
    load_operator_authority,
)
from royin.risk import MarketRules
from scripts.run_fresh_service import FreshEngine
from tests import test_fresh_mission as fresh_cases


class OperatorEntryTests(unittest.TestCase):
    setUp_original = fresh_cases.FreshMissionTests.setUp
    authorize = fresh_cases.FreshMissionTests.authorize
    worker = fresh_cases.FreshMissionTests.worker

    def setUp(self):
        self.setUp_original()
        self.permit = self.permit.model_copy(
            update=dict(
                allocation_tmn=D(4000000), capital_policy="VOLATILITY_CAPITAL_V1", max_buys=3
            )
        )
        self.config = self.config.model_copy(update=dict(WALLEX_ALLOWED_MARKETS=("PUMPTMN",)))
        self.rules = MarketRules(
            "PUMPTMN", "PUMP", "TMN", D(1), D(".1"), D(100000), D(".1"), D(".0025"), D(".003")
        )
        self.authorize()
        WallexLiveBroker.initialize_state(self.ledger)
        self.ledger.set_meta("fresh_source_sha256", "a" * 64)
        self.ledger.set_meta("fresh_config_sha256", "b" * 64)
        self.now = 1010
        self.last_payload = None
        self.fill = False
        self.timeout = False
        self.canceled = False
        self.quote_age = 0
        self.evidence_change = None
        self.partial = None
        self.fill_times = {}

    def op(self, **changes):
        changes.setdefault("symbol", "PUMPTMN")
        return authorize_operator_entry(
            self.ledger,
            self.permit,
            now=self.now,
            expires_at=1800,
            operator_instruction="Synthetic explicit operator one-entry approval",
            **changes,
        )

    def book(self):
        return dict(
            success=True,
            result=dict(
                aggregate_volume=D("1.2500"),
                bid=[dict(price="1150", quantity="1000")],
                ask=[dict(price="1151", quantity="1000")],
            ),
        )

    def result(self, p, *, canceled=False):
        filled = D(p["quantity"]) if self.fill else D(0)
        if self.partial is not None and p["side"] == "BUY":
            filled = self.rules.quantize_quantity(D(p["quantity"]) * self.partial)
        status = (
            "FILLED"
            if filled == D(p["quantity"])
            else "CANCELED"
            if canceled
            else "PARTIALLY_FILLED"
            if filled
            else "NEW"
        )
        fill_time = self.fill_times.setdefault(p["client_id"], self.now)
        fills = (
            []
            if not filled
            else [
                dict(
                    symbol=p["symbol"],
                    isBuyer=p["side"] == "BUY",
                    price=p["price"],
                    quantity=str(filled),
                    sum=str(filled * D(p["price"])),
                    fee=str(filled * D(p["price"]) * D(".003")),
                    feeAsset="TMN",
                    timestamp=datetime.fromtimestamp(fill_time, UTC).isoformat(),
                )
            ]
        )
        return dict(
            success=True,
            result=dict(
                clientOrderId=p["client_id"],
                symbol=p["symbol"],
                side=p["side"],
                type="LIMIT",
                price=p["price"],
                origQty=p["quantity"],
                executedQty=str(filled),
                executedSum=str(filled * D(p["price"])),
                status=status,
                active=status in ("NEW", "PARTIALLY_FILLED"),
                fills=fills,
            ),
        )

    def factory(self, ledger, rules, config, *, permit):
        if self.evidence_change:
            auth, _state = load_operator_authority(ledger, permit)
            key = "fresh_evidence_" + auth["client_id"]
            evidence = json.loads(ledger.get_meta(key))
            evidence.update(self.evidence_change)
            ledger.set_meta(key, json.dumps(evidence))

        def handler(request):
            self.calls.append(request)
            if self.timeout:
                raise httpx.ReadTimeout("Synthetic uncertain send")
            if request.method == "POST":
                self.last_payload = json.loads(request.content)
                return httpx.Response(201, json=self.result(self.last_payload))
            if request.method == "DELETE":
                self.canceled = True
            return httpx.Response(200, json=self.result(self.last_payload, canceled=self.canceled))

        return FreshMissionTransport(
            ledger, rules, config, permit=permit, inner=httpx.MockTransport(handler)
        )

    def engine(self):
        feed = SimpleNamespace(get=lambda *a, **kw: (self.book(), self.now - self.quote_age))
        signals = SimpleNamespace(model_startup_blocked=True, _execute_cycle=MagicMock())
        engine = FreshEngine(
            self.ledger,
            self.permit,
            None,
            self.config,
            self.root,
            client=None,
            feed=feed,
            signals=signals,
        )
        engine.rules = lambda _symbol: self.rules
        engine.reads.snapshot = lambda: ({"TMN": Balance(D(5000000), D(5000000), D(0))}, [])
        return engine

    def run_entry(self, engine):
        with (
            self.worker(),
            patch("scripts.run_fresh_service.FreshMissionTransport", side_effect=self.factory),
            patch("time.time", side_effect=lambda: self.now),
        ):
            return engine.operator_entry_tick(self.now)

    def test_authority_preserves_original_permit_and_history_and_rejects_a_fourth_entry(self):
        original = self.ledger.get_meta("fresh_permit")
        for i in range(3):
            auth = self.op()
            saved = json.loads(self.ledger.get_meta(AUTH_KEY))
            self.assertEqual(len(saved), i + 1)
            self.assertEqual(auth["sequence"], i + 1)
            self.ledger.set_meta(
                STATE_KEY, json.dumps(dict(state="EXPIRED", authority_sha256=auth["sha256"]))
            )
        with self.assertRaises(ValueError):
            self.op()
        self.assertEqual(original, self.ledger.get_meta("fresh_permit"))
        self.assertEqual(
            hashlib.sha256((self.root / "old.sqlite3").read_bytes()).hexdigest(), self.old_hash
        )
        self.assertEqual(json.loads(self.ledger.get_meta("fresh_transport"))["attempts"], 0)

    def test_pending_authority_cannot_be_replaced_or_reinitialized(self):
        self.op()
        with self.assertRaises(ValueError):
            self.op(symbol="PEPETMN")
        self.assertEqual(len(json.loads(self.ledger.get_meta(AUTH_KEY))), 1)

    def test_unattempted_runtime_repair_preserves_authority_state_and_counters(self):
        auth = self.op()
        original = self.ledger.get_meta(AUTH_KEY)
        state = self.ledger.get_meta(STATE_KEY)
        transport = self.ledger.get_meta("fresh_transport")
        with patch("royin.runtime_release.source_history", return_value=("a" * 64, "c" * 64)):
            with self.assertRaises(ValueError):
                load_operator_authority(self.ledger, self.permit)
            receipt = authorize_operator_runtime(
                self.ledger,
                self.permit,
                expected_authority_sha256=auth["sha256"],
                operator_instruction="Synthetic serialization repair under existing approval",
                now=self.now,
            )
            self.assertEqual(receipt["to_source_sha256"], "c" * 64)
            load_operator_authority(self.ledger, self.permit)
            with self.assertRaises(ValueError):
                authorize_operator_runtime(
                    self.ledger,
                    self.permit,
                    expected_authority_sha256=auth["sha256"],
                    operator_instruction="No same-source duplicate amendment",
                    now=self.now,
                )
        self.assertEqual(self.ledger.get_meta(AUTH_KEY), original)
        self.assertEqual(self.ledger.get_meta(STATE_KEY), state)
        self.assertEqual(self.ledger.get_meta("fresh_transport"), transport)
        self.assertFalse(self.calls)

    def test_authority_cap_source_and_account_tampering_fail_closed(self):
        self.op()
        original = self.ledger.get_meta(AUTH_KEY)
        for key, value in (
            ("max_debit_tmn", "500000"),
            ("account_sha256", "f" * 64),
            ("source_sha256", "f" * 64),
        ):
            with self.subTest(key=key):
                history = json.loads(original)
                history[0][key] = value
                history[0]["sha256"] = digest(
                    {k: v for k, v in history[0].items() if k != "sha256"}
                )
                self.ledger.set_meta(AUTH_KEY, json.dumps(history))
                with self.assertRaises(ValueError):
                    load_operator_authority(self.ledger, self.permit)
        self.ledger.set_meta(AUTH_KEY, original)
        self.assertFalse(self.calls)

    def test_actual_broker_accepts_one_operator_limit_with_true_origin_and_no_forecast(self):
        self.op()
        engine = self.engine()
        self.assertTrue(self.run_entry(engine))
        self.assertEqual(len(self.calls), 1)
        payload = json.loads(self.calls[0].content)
        self.assertEqual(payload["symbol"], "PUMPTMN")
        self.assertEqual(D(payload["price"]), D("1150"))
        self.assertLessEqual(D(payload["price"]) * D(payload["quantity"]) * D("1.003"), D(150000))
        evidence = json.loads(self.ledger.get_meta("fresh_evidence_" + payload["client_id"]))
        self.assertEqual(evidence["source_kind"], "OPERATOR")
        self.assertIsNone(evidence["model_forecast"])
        self.assertFalse(evidence["target_net_approved"])
        self.assertEqual(
            json.loads(self.ledger.get_meta("audit_order_" + payload["client_id"]))["source"],
            "OPERATOR",
        )
        self.assertEqual(json.loads(self.ledger.get_meta(STATE_KEY))["state"], "ATTEMPTED")
        engine.signals._execute_cycle.assert_not_called()

    def test_stale_quote_or_changed_account_stops_before_intent_or_http(self):
        self.op()
        engine = self.engine()
        self.quote_age = 6
        with self.assertRaises(ValueError):
            self.run_entry(engine)
        self.assertFalse(self.calls)
        self.assertEqual(json.loads(self.ledger.get_meta(STATE_KEY))["state"], "AUTHORIZED")
        self.quote_age = 0
        engine.reads.snapshot = lambda: ({"TMN": Balance(D(4999999), D(4999999), D(0))}, [])
        self.run_entry(engine)
        self.assertFalse(self.calls)
        self.assertEqual(
            self.ledger.get_meta("entry_block_reason"), "ACCOUNT_RECONCILIATION_REQUIRED"
        )

    def test_timeout_keeps_unknown_reservation_and_cannot_send_another_buy_after_restart(self):
        self.op()
        self.timeout = True
        engine = self.engine()
        self.run_entry(engine)
        self.assertEqual(len(self.calls), 1)
        self.assertGreater(self.ledger.get_balance("TMN").locked, 0)
        restarted = self.engine()
        self.run_entry(restarted)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(json.loads(self.ledger.get_meta("fresh_transport"))["buys"], 1)

    def test_operator_cancel_waits_sixty_seconds_and_releases_only_after_exchange_receipt(self):
        self.op()
        engine = self.engine()
        self.run_entry(engine)
        self.now = 1069
        with (
            self.worker(),
            patch("scripts.run_fresh_service.FreshMissionTransport", side_effect=self.factory),
            patch("time.time", side_effect=lambda: self.now),
        ):
            engine.reconcile(self.now)
            self.assertEqual(self.calls[-1].method, "GET")
            self.now = 1070
            engine.reconcile(self.now)
            self.assertEqual(self.calls[-1].method, "DELETE")
            self.assertEqual(self.calls[-1].url.path, "/v1/account/orders")
            self.assertEqual(
                self.calls[-1].url.params.multi_items(),
                [("clientOrderId", self.last_payload["client_id"])],
            )
            self.assertGreater(self.ledger.get_balance("TMN").locked, 0)
            self.now = 1071
            engine.reconcile(self.now)
            self.assertEqual(self.calls[-1].method, "GET")
        self.assertEqual(self.ledger.get_balance("TMN").locked, 0)
        self.run_entry(engine)
        self.assertEqual(json.loads(self.ledger.get_meta(STATE_KEY))["state"], "COMPLETE")
        self.assertEqual(sum(r.method == "POST" for r in self.calls), 1)

    def test_real_fill_host_time_exit_and_restart_use_operator_source_not_model_source(self):
        self.op()
        self.fill = True
        engine = self.engine()
        self.run_entry(engine)
        self.assertGreater(self.ledger.get_balance("PUMP").total, 0)
        self.now = 1910
        restarted = self.engine()
        with (
            self.worker(),
            patch("scripts.run_fresh_service.FreshMissionTransport", side_effect=self.factory),
            patch("time.time", side_effect=lambda: self.now),
        ):
            self.assertTrue(restarted.position_tick(self.now))
        sell = json.loads(self.calls[-1].content)
        self.assertEqual(sell["side"], "SELL")
        self.assertEqual(
            json.loads(self.ledger.get_meta("fresh_position"))["reason"],
            "OPERATOR_MAX_HOLDING_TIME",
        )
        self.assertEqual(
            json.loads(self.ledger.get_meta("audit_order_" + sell["client_id"]))["source"],
            "OPERATOR",
        )
        self.assertEqual(sum(r.method == "POST" for r in self.calls), 2)
        from royin.residuals import quarantined_residuals

        self.now = 1911
        with self.worker(), patch("time.time", side_effect=lambda: self.now):
            self.assertFalse(restarted.position_tick(self.now))
            self.assertTrue(restarted.operator_entry_tick(self.now))
        self.assertIn("PUMP", quarantined_residuals(self.ledger))
        prior = json.loads(self.ledger.get_meta(AUTH_KEY))
        authorize_operator_entry(
            self.ledger,
            self.permit,
            now=self.now,
            expires_at=1990,
            operator_instruction="Synthetic sequential second operator mandate",
            symbol="PEPETMN",
        )
        self.assertEqual(json.loads(self.ledger.get_meta(AUTH_KEY))[:1], prior)
        self.assertIn("PUMP", quarantined_residuals(self.ledger))

    def test_unexpired_unauthorized_market_and_large_spread_cannot_reach_network(self):
        with self.assertRaises(ValueError):
            self.op(symbol="ETHTMN")
        self.op()
        engine = self.engine()
        bad = self.book()
        bad["result"]["ask"][0]["price"] = "22000000000"
        engine.feed.get = lambda *a, **kw: (bad, self.now)
        with self.assertRaises(ValueError):
            self.run_entry(engine)
        self.assertFalse(self.calls)

    def test_transport_independently_rejects_stale_operator_evidence_before_any_http(self):
        self.op()
        self.evidence_change = {"quote_received_at": 1004}
        self.run_entry(self.engine())
        self.assertFalse(self.calls)
        self.assertEqual(json.loads(self.ledger.get_meta("fresh_transport"))["attempts"], 0)
        self.assertEqual(json.loads(self.ledger.get_meta(STATE_KEY))["state"], "CLAIMED")

    def test_operator_stop_exit_runs_before_the_time_limit_without_model_http(self):
        self.op()
        self.fill = True
        engine = self.engine()
        self.run_entry(engine)
        self.now = 1020
        depth = dict(
            success=True,
            result=dict(
                bid=[dict(price="1100", quantity="1000")],
                ask=[dict(price="1101", quantity="1000")],
            ),
        )
        engine.feed.get = lambda *a, **kw: (depth, self.now)
        with (
            self.worker(),
            patch("scripts.run_fresh_service.FreshMissionTransport", side_effect=self.factory),
            patch("time.time", side_effect=lambda: self.now),
        ):
            self.assertTrue(engine.position_tick(self.now))
        self.assertEqual(
            json.loads(self.ledger.get_meta("fresh_position"))["reason"], "STOP_OR_TRAILING"
        )
        self.assertEqual(json.loads(self.calls[-1].content)["side"], "SELL")

    def test_small_partial_fill_is_retained_and_reported_without_fabricating_a_sell(self):
        self.op()
        self.partial = D(".25")
        engine = self.engine()
        self.run_entry(engine)
        self.assertGreater(self.ledger.get_balance("PUMP").total, 0)
        with (
            self.worker(),
            patch("scripts.run_fresh_service.FreshMissionTransport", side_effect=self.factory),
            patch("time.time", side_effect=lambda: self.now),
        ):
            self.now = 1070
            engine.reconcile(self.now)
            self.now = 1071
            engine.reconcile(self.now)
            self.now = 1910
            self.assertTrue(engine.position_tick(self.now))
        self.assertEqual(self.ledger.get_meta("entry_block_reason"), "UNSELLABLE_RESIDUAL")
        self.assertGreater(self.ledger.get_balance("PUMP").total, 0)
        self.assertEqual(sum(r.method == "POST" for r in self.calls), 1)

    def test_request_is_consumed_by_only_the_financial_worker_and_is_idempotent(self):
        directory = self.root / "operator-entry-requests"
        directory.mkdir()
        body = dict(
            mission_id=self.permit.mission_id,
            permit_sha256=hashlib.sha256(self.permit.canonical().encode()).hexdigest(),
            account_sha256=self.permit.account_sha256,
            symbol="PUMPTMN",
            expires_at=1800,
            operator_instruction="Synthetic wider operator approval",
        )
        request = {**body, "sha256": digest(body)}
        path = directory / "request-1.json"
        path.write_text(json.dumps(request))
        with self.assertRaises(ValueError):
            ingest_operator_requests(self.ledger, self.permit, directory, now=self.now)
        with self.worker():
            ingest_operator_requests(self.ledger, self.permit, directory, now=self.now)
            path.write_text(json.dumps(request))
            ingest_operator_requests(self.ledger, self.permit, directory, now=self.now)
        self.assertEqual(len(json.loads(self.ledger.get_meta(AUTH_KEY))), 1)
        self.assertFalse(self.calls)
