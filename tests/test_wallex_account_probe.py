import unittest

import httpx

from scripts.probe_wallex_account import choose_credit_account, read_account


class CreditAccountProbeTests(unittest.TestCase):
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
