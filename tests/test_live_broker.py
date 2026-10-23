"""Safety and response-contract tests; never use production transport."""

import json
import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import httpx

from royin.config import RuntimeConfig
from royin.ledger import Ledger
from royin.live_broker import LiveOrderError, LiveTradingSafetyGateError, WallexLiveBroker
from royin.risk import MarketRules, RiskResult

ROOT = Path(__file__).resolve().parents[1]


class WallexLiveBrokerTests(unittest.TestCase):
    def setUp(self):
        self.ledger = Ledger(":memory:")
        self.ledger.set_balance("TMN", Decimal("5000000"))
        self.rules = MarketRules(
            "USDTTMN",
            "USDT",
            "TMN",
            Decimal("1"),
            Decimal(".01"),
            Decimal("100000"),
            Decimal("1"),
            Decimal(".0025"),
            Decimal(".003"),
        )
        self.config = RuntimeConfig(
            WALLEX_API_KEY="synthetic-key",
            SUB_ACCOUNT_CLIENT_ID="synthetic-account",
            WALLEX_ALLOWED_MARKETS=("USDTTMN",),
        )
        self.risk = RiskResult(
            True,
            "fixture",
            "ENTER",
            "USDTTMN",
            Decimal("6.50"),
            Decimal("230000"),
            Decimal("225400"),
            Decimal("4485"),
        )
        self.requests = []
        self.clients = []

    def tearDown(self):
        for client in self.clients:
            client.close()

    def broker(self, response=None, handler=None, **kwargs):
        def transport(request):
            self.requests.append(request)
            self.assertEqual(request.headers["x-api-key"], "synthetic-key")
            self.assertEqual(request.headers["sub-account-client-id"], "synthetic-account")
            return handler(request) if handler else response or self.response()

        client = httpx.Client(transport=httpx.MockTransport(transport))
        self.clients.append(client)
        return WallexLiveBroker(
            self.ledger,
            self.rules,
            self.config,
            http_client=client,
            enable_live_trading=True,
            run_mode="live",
            restrictions_path=ROOT / "config/wallex-credit-market-policy.json",
            **kwargs,
        )

    @staticmethod
    def response(status="NEW", executed="0", code=201):
        return httpx.Response(
            code,
            json={
                "success": True,
                "result": {
                    "clientOrderId": "order_1",
                    "status": status,
                    "executedQty": executed,
                    "symbol": "USDTTMN",
                    "side": "BUY",
                    "type": "LIMIT",
                    "price": "230000",
                    "origQty": "6.50",
                    "executedSum": "0",
                    "fills": [],
                    "active": True,
                },
            },
        )

    def submit(self, broker):
        return broker.submit_order(self.risk, client_id="order_1", timestamp=1788220800)

    def test_default_flags_and_override_cannot_enable_production(self):
        for overrides in [{}, {"enable_live_trading": True, "run_mode": "live"}]:
            broker = WallexLiveBroker(self.ledger, self.rules, self.config, **overrides)
            with self.assertRaises(LiveTradingSafetyGateError):
                self.submit(broker)
        self.assertEqual(self.ledger.get_balance("TMN").locked, 0)

    def test_documented_201_acknowledges_only_open_order(self):
        result = self.submit(self.broker())
        self.assertEqual(result["status"], "OPEN")
        payload = json.loads(self.requests[0].content)
        self.assertEqual(payload["client_id"], "order_1")
        self.assertEqual(payload["quantity"], "6.50")
        self.assertEqual(self.ledger.get_balance("USDT").total, 0)
        self.assertEqual(self.ledger.get_balance("TMN").locked, Decimal("1499485"))

    def test_mounted_transport_cannot_bypass_offline_gate(self):
        broker = self.broker()
        broker._injected_client._mounts[httpx._utils.URLPattern("https://api.wallex.ir")] = (
            httpx.MockTransport(lambda _: self.fail("Mounted transport must not be reached"))
        )
        with self.assertRaises(LiveTradingSafetyGateError):
            self.submit(broker)
        self.assertFalse(self.requests)
        self.assertEqual(self.ledger.get_balance("TMN").locked, 0)

    def test_network_and_response_ambiguity_retain_reservations(self):
        cases = [
            httpx.Response(500, json={"success": False}),
            httpx.Response(404, json={}),
            httpx.Response(200, content=b"not JSON"),
            httpx.Response(201, json={"success": True}),
            httpx.Response(201, json=[]),
            httpx.Response(
                201, json={"success": True, "result": {"clientOrderId": "order_1", "status": "NEW"}}
            ),
            self.response("FINISHED", "6.5"),
            self.response("PARTIALLY_FILLED", "1"),
        ]
        for response in cases:
            with self.subTest(response=response):
                self.ledger = Ledger(":memory:")
                self.ledger.set_balance("TMN", Decimal("5000000"))
                result = self.submit(self.broker(response=response))
                self.assertEqual(result["status"], "UNKNOWN")
                self.assertEqual(self.ledger.get_balance("TMN").locked, Decimal("1499485"))
                self.assertEqual(self.ledger.get_balance("USDT").total, 0)

    def test_timeout_and_connection_loss_are_unknown(self):
        for exc in [httpx.ReadTimeout("synthetic"), httpx.RemoteProtocolError("synthetic")]:
            self.ledger = Ledger(":memory:")
            self.ledger.set_balance("TMN", Decimal("5000000"))

            def handler(_request, error=exc):
                raise error

            result = self.submit(self.broker(handler=handler))
            self.assertEqual(result["status"], "UNKNOWN")
            self.assertEqual(result["failure_reason"], "TRANSPORT_ERROR")
            self.assertEqual(result["error_type"], type(exc).__name__)
            self.assertGreater(self.ledger.get_balance("TMN").locked, 0)

    def test_http_json_and_contract_failures_remain_distinguishable_without_secrets(self):
        cases = [
            (httpx.Response(403, content=b""), "HTTP_ERROR"),
            (httpx.Response(422, json={"message": "synthetic-key"}), "HTTP_ERROR"),
            (httpx.Response(201, content=b"synthetic-key"), "INVALID_RESPONSE_JSON"),
            (httpx.Response(201, json={"success": False}), "INVALID_RESPONSE_CONTRACT"),
            (self.response("FILLED", "1"), "INVALID_ORDER_SNAPSHOT"),
        ]
        for response, reason in cases:
            with self.subTest(reason=reason, code=response.status_code):
                self.ledger = Ledger(":memory:")
                self.ledger.set_balance("TMN", Decimal("5000000"))
                outcome = self.submit(self.broker(response=response))
                self.assertEqual(outcome["status"], "UNKNOWN")
                self.assertEqual(outcome["http_status"], response.status_code)
                self.assertEqual(outcome["failure_reason"], reason)
                self.assertNotIn("synthetic-key", json.dumps(outcome))
                self.assertEqual(self.ledger.get_balance("TMN").locked, Decimal("1499485"))
                self.assertEqual(self.ledger.get_balance("USDT").total, 0)

    def test_404_reconciliation_never_frees_funds(self):
        broker = self.broker()
        self.submit(broker)
        broker._injected_client.close()
        broker._injected_client = httpx.Client(
            transport=httpx.MockTransport(lambda _: httpx.Response(404, json={}))
        )
        self.clients.append(broker._injected_client)
        self.assertEqual(
            broker.reconcile_order("order_1", timestamp=1788220900)["status"], "UNKNOWN"
        )
        self.assertEqual(self.ledger.get_balance("TMN").locked, Decimal("1499485"))

    def test_cancel_with_partial_fill_requires_accounting_not_unlock(self):
        broker = self.broker(response=self.response("CANCELED", "1"))
        self.submit(broker)
        result = broker.cancel_order("order_1", timestamp=1788220900)
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual(self.ledger.get_balance("TMN").locked, Decimal("1499485"))

    def test_unknown_or_malformed_id_cannot_reconcile(self):
        broker = self.broker()
        for cid in ["other_order", "../balances", "order?token=x"]:
            with self.assertRaises(LiveOrderError):
                broker.reconcile_order(cid, timestamp=1788220900)
        self.assertFalse(self.requests)

    def test_policy_missing_or_cross_symbol_fails_before_intent(self):
        broker = self.broker()
        with self.assertRaises(LiveOrderError):
            broker.submit_order(
                replace(self.risk, symbol="BTCTMN"), client_id="order_1", timestamp=1
            )
        with tempfile.TemporaryDirectory() as temp:
            broker.restrictions_path = Path(temp) / "missing.json"
            with self.assertRaises(LiveOrderError):
                self.submit(broker)
        self.assertEqual(self.ledger.get_balance("TMN").locked, 0)
        self.assertFalse(self.requests)

    def test_duplicate_submission_never_sends_second_request(self):
        broker = self.broker()
        self.submit(broker)
        with self.assertRaises(ValueError):
            self.submit(broker)
        self.assertEqual(len(self.requests), 1)

    def test_missing_credentials_block_before_reservation(self):
        broker = self.broker()
        broker.config = RuntimeConfig(WALLEX_ALLOWED_MARKETS=("USDTTMN",))
        with self.assertRaises(ValueError):
            self.submit(broker)
        self.assertEqual(self.ledger.get_balance("TMN").locked, 0)


if __name__ == "__main__":
    unittest.main()
