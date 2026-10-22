import tempfile
import unittest
from pathlib import Path

import httpx

from royin.config import RuntimeConfig
from scripts.probe_wallex_account import choose_credit_account, probe_credit_contract, read_account


class CreditAccountProbeTests(unittest.TestCase):
    def test_failed_get_counts_and_unknown_orders_are_not_zero_or_release(self):
        seen=[]
        def handler(request):
            seen.append(request.url.path)
            if request.url.path=="/sub-accounts":
                return httpx.Response(200,json=dict(success=True,result=[self.row]))
            if request.url.path.endswith("balances-detail"):
                return httpx.Response(200,json=dict(success=True,result={"TMN":dict(symbol="TMN",total="5000000",available="5000000",freeze="0")}))
            if request.url.path.endswith("fee"):
                raise httpx.ReadTimeout("synthetic")
            return httpx.Response(200,json=dict(success=True,result={}))
        with tempfile.TemporaryDirectory() as temp,httpx.Client(transport=httpx.MockTransport(handler)) as client:
            report=probe_credit_contract(RuntimeConfig(WALLEX_API_KEY="fake"),client,Path(temp)/"fresh")
        self.assertEqual(report["gets_used"],5)
        self.assertEqual(len(seen),5)
        self.assertNotIn("open_orders_count",report)
        self.assertEqual(report["status"],"NO_GO_CRITICAL_CONTRACT_UNKNOWN")
        self.assertTrue(report["critical_unknowns"])

    def setUp(self):
        self.row = {"clientId": "synthetic-credit-id", "type": "prop",
                    "isActive": True, "isSuspend": False}

    def test_unique_active_prop_only_and_no_guess_when_ambiguous(self):
        self.assertEqual(choose_credit_account({"result": [self.row]}), "synthetic-credit-id")
        for payload in ({"result": []}, {"result": [self.row, self.row]},
                        {"result": [self.row], "result_info": {"total_count": 2}},
                        {"result": [{**self.row, "type": "trading_bot_trade"}]},
                        {"result": [{**self.row, "isActive": False}]}):
            with self.assertRaises(ValueError):
                choose_credit_account(payload)
        with self.assertRaises(ValueError):
            choose_credit_account({"result": [self.row]}, existing="another-account")

    def test_main_balance_and_write_routes_block_before_transport(self):
        for endpoint in ("/v1/account/balances", "/v1/account/orders",
                         "/v1/prop/user/packages/activate", "/v1/account/balances-detail"):
            with self.assertRaises(ValueError):
                read_account(None, endpoint, "synthetic-key")

    def test_read_scope_and_headers_with_success_false_rejected(self):
        seen = []

        def handle(request):
            seen.append(request)
            return httpx.Response(200, json={"success": False})

        with (
            httpx.Client(transport=httpx.MockTransport(handle)) as client,
            self.assertRaises(ValueError),
        ):
            read_account(client, "/v1/account/balances-detail", "synthetic-key", "credit-id")
        self.assertEqual(seen[0].method, "GET")
        self.assertEqual(seen[0].headers["sub-account-client-id"], "credit-id")
        self.assertEqual(seen[0].url.host, "api.wallex.ir")
