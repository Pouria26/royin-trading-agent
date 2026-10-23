"""Bounded production transport checks using only offline HTTP fixtures."""

import hashlib
import json
import tempfile
import unittest
from datetime import UTC, datetime
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import patch

import httpx

from royin.canary import CreditCanaryTransport, clean_revision
from royin.config import RuntimeConfig
from royin.ledger import Ledger
from royin.live_broker import WallexLiveBroker
from royin.risk import MarketRules, RiskPolicy, RiskResult
from scripts.run_live_pilot import run_pilot_round_trip


class CreditCanaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ledger = Ledger(Path(self.temp.name)/"state.sqlite3")
        self.ledger.set_balance("TMN",D(100000))
        self.rules = MarketRules("USDTTMN","USDT","TMN",D(1),D(".01"),D(50000),D(".01"),D(".0025"),D(".003"))
        self.config = RuntimeConfig(WALLEX_API_KEY="synthetic-key",SUB_ACCOUNT_CLIENT_ID="synthetic-account",
            WALLEX_ALLOWED_MARKETS=("USDTTMN",),CHALLENGE_END_AT="2030-01-01T00:00:00+00:00")
        self.now = 1788220800
        self.clock = patch("royin.canary.time.time",return_value=self.now)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.calls = []
        def handler(request):
            self.calls.append(request)
            return httpx.Response(200,json={"success":True,"result":dict(clientOrderId="canary_buy",symbol="USDTTMN",
                side="BUY",type="LIMIT",price="250000",origQty="0.36",executedQty="0",executedSum="0",fills=[],active=True,status="NEW")})
        self.transport = CreditCanaryTransport(self.ledger,self.rules,self.config,revision="a"*40,
            expires_at=self.now+600,inner=httpx.MockTransport(handler))
        self.client = httpx.Client(transport=self.transport,trust_env=False)
        self.addCleanup(self.client.close)
        self.broker = WallexLiveBroker(self.ledger,self.rules,self.config,http_client=self.client,
            enable_live_trading=True,run_mode="live")
        self.fingerprint = hashlib.sha256(b"synthetic-account").hexdigest()

    def worker(self):
        return self.ledger.worker(account_fingerprint=self.fingerprint,lock_directory=Path(self.temp.name)/"locks")

    def request(self, method="POST", cid="canary_buy", price="250000", quantity="0.36",side="BUY",url=None):
        return httpx.Request(method,url or "https://api.wallex.ir/v1/account/orders"+("" if method=="POST" else "/"+cid),
            headers={"x-api-key":"synthetic-key","sub-account-client-id":"synthetic-account"},
            json=dict(client_id=cid,symbol="USDTTMN",type="LIMIT",side=side,price=price,quantity=quantity) if method=="POST" else None)

    def intent(self,cid="canary_buy",price="250000",quantity="0.36",side="BUY"):
        self.ledger.record_intent(client_id=cid,symbol="USDTTMN",side=side,order_type="LIMIT",price=D(price),quantity=D(quantity),
            quote_fee_reserve=D(price)*D(quantity)*D(".003"),quote_asset="TMN",base_asset="USDT",timestamp=self.now)

    def test_broker_canary_records_one_small_order_and_requires_shared_lock(self):
        risk = RiskResult(True,"technical","ENTER","USDTTMN",D(".36"),D(250000),D(245000),D(270))
        with self.worker():
            self.assertEqual(self.broker.submit_order(risk,client_id="canary_buy",timestamp=self.now)["status"],"OPEN")
        self.assertEqual(len(self.calls),1)
        self.assertEqual(self.ledger.get_balance("TMN").locked,D(90270))
        self.assertEqual(self.ledger.get_balance("USDT").total,0)
        self.assertEqual(json.loads(self.ledger.get_meta(self.transport.state_key))["attempts"],1)
        with self.ledger.worker(), self.assertRaises(ValueError):
            self.transport.handle_request(self.request("GET"))
        self.assertEqual(len(self.calls),1)

    def test_endpoint_account_intent_and_cash_cap_fail_before_socket(self):
        self.intent(quantity=".39")
        cases = [self.request(url="https://evil.example/v1/account/orders"),self.request("GET",cid="unknown"),
                 self.request(url="https://api.wallex.ir/v1/account/orders?override=true"),self.request(quantity=".4")]
        bad = self.request(quantity=".39")
        bad.headers["sub-account-client-id"] = "other-account"
        cases.append(bad)
        with self.worker():
            for request in cases:
                with self.assertRaises(ValueError):
                    self.transport.handle_request(request)
        self.assertFalse(self.calls)
        other = Ledger(Path(self.temp.name)/"large.sqlite3")
        other.set_balance("TMN",D(200000))
        other.record_intent(client_id="large",symbol="USDTTMN",side="BUY",order_type="LIMIT",price=D(250000),quantity=D(".4"),
            quote_fee_reserve=D(300),quote_asset="TMN",base_asset="USDT",timestamp=self.now)
        transport = CreditCanaryTransport(other,self.rules,self.config,revision="a"*40,expires_at=self.now+600,inner=httpx.MockTransport(lambda _:self.fail("over cap")))
        with other.worker(account_fingerprint=self.fingerprint,lock_directory=Path(self.temp.name)/"locks"), self.assertRaises(ValueError):
            transport.handle_request(self.request(cid="large",quantity=".4"))

    def test_retry_restart_and_expiry_cannot_reset_allowance(self):
        self.intent()
        with self.worker():
            self.transport.handle_request(self.request())
            with self.assertRaises(ValueError):
                self.transport.handle_request(self.request())
        resumed = CreditCanaryTransport(self.ledger,self.rules,self.config,revision="a"*40,expires_at=self.now+600,
            inner=httpx.MockTransport(lambda _:httpx.Response(200,json={})))
        with patch("royin.canary.time.time",return_value=self.now+700):
            resumed = CreditCanaryTransport(self.ledger,self.rules,self.config,revision="a"*40,expires_at=self.now+600,
                inner=httpx.MockTransport(lambda _:httpx.Response(200,json={})))
            with self.worker():
                for _ in range(7):
                    resumed.handle_request(self.request("GET"))
                with self.assertRaises(ValueError):
                    resumed.handle_request(self.request("GET"))
        self.assertEqual(json.loads(self.ledger.get_meta(resumed.state_key))["attempts"],8)
        with self.assertRaises(ValueError):
            CreditCanaryTransport(self.ledger,self.rules,self.config,revision="b"*40,expires_at=self.now+600)

    def test_expired_permit_still_allows_owed_position_exit(self):
        self.intent()
        with self.worker():
            self.transport.handle_request(self.request())
        self.ledger.cancel_intent("canary_buy")
        self.ledger.set_balance("USDT",D(".36"))
        self.intent(cid="canary_sell",side="SELL")
        with patch("royin.canary.time.time",return_value=self.now+700),self.worker():
            self.transport.handle_request(self.request(cid="canary_sell",side="SELL"))
            with self.assertRaises(ValueError):
                self.transport.handle_request(self.request(cid="canary_sell",side="SELL"))
        self.assertEqual(len(self.calls),2)

    def test_dirty_revision_fails_closed(self):
        with patch("royin.canary.subprocess.check_output",side_effect=["a"*40," M source.py"]), self.assertRaises(ValueError):
            clean_revision(Path(self.temp.name))

    def test_old_financial_revision_is_reported_before_network_and_preserved(self):
        from scripts import execute_credit_canary as cli
        binding = json.dumps(dict(revision="a"*40,expires_at=self.now+10,initial_tmn="100000"))
        self.ledger.set_meta("canary_binding",binding)
        root = Path(self.temp.name)/"review"
        with patch.object(cli,"ROOT",root),patch.object(cli,"load_config",return_value=self.config), \
             patch.object(cli,"clean_revision",return_value="b"*40), \
             patch.object(cli,"canary_state_path",return_value=Path(self.ledger.db_path)), \
             patch.object(cli,"preflight",side_effect=AssertionError("Must not reach network")), \
             patch("builtins.print"):
            self.assertEqual(cli.run(True),2)
        report = json.loads(next((root/"data/private").glob("*/report.json")).read_text())
        self.assertEqual(report["blocked_reason"],"EXISTING_FINANCIAL_RUN_SOURCE_MISMATCH")
        self.assertTrue(report["reconciliation_required"])
        self.assertEqual(report["orders_attempted"],0)
        self.assertEqual(self.ledger.get_meta("canary_binding"),binding)
        self.assertEqual(self.ledger.get_balance("TMN").free,D(100000))

    def test_cancel_failure_observation_survives_restart_without_new_order(self):
        self.transport.inner = httpx.MockTransport(lambda _:httpx.Response(503,content=b""))
        policy = RiskPolicy(D(100000),D(100000),D(".02"),D(".05"),self.now+600,min_seconds_before_deadline=0)
        with self.worker():
            for elapsed in (0,40,41):
                with patch("royin.canary.time.time",return_value=self.now+elapsed):
                    state = run_pilot_round_trip(self.broker,self.ledger,self.rules,policy,D(250000),
                        self.now+elapsed,"a"*64)
        self.assertEqual(state["status"],"CANCEL_ATTEMPTED_RECONCILIATION_REQUIRED")
        self.assertEqual(state["last_exchange_observation"]["http_status"],503)
        self.assertEqual(state["last_exchange_observation"]["failure_reason"],"HTTP_ERROR")
        self.assertEqual(json.loads(self.ledger.get_meta("pilot_pilot")),state)
        self.assertEqual(state["orders_attempted"],1)
        self.assertGreater(self.ledger.get_balance("TMN").locked,0)

    def test_empty_http_failure_keeps_status_and_never_refunds_attempt(self):
        self.intent()
        self.transport.inner = httpx.MockTransport(lambda _:httpx.Response(403,content=b""))
        with self.worker():
            response = self.transport.handle_request(self.request())
        self.assertEqual(response.status_code,403)
        observed = json.loads((Path(self.ledger.db_path).parent/"captures/attempt-1-http.json").read_text())
        self.assertEqual(observed["status_code"],403)
        self.assertEqual(observed["attempt"],1)
        self.assertNotIn("synthetic-key",json.dumps(observed))
        self.assertEqual(json.loads(self.ledger.get_meta(self.transport.state_key))["buy"],1)

    def test_full_round_trip_reports_exact_fee_and_residual_instead_of_zero_dust(self):
        def fills(request):
            payload = json.loads(request.content)
            side, quantity, price = payload["side"], D(payload["quantity"]), D(payload["price"])
            fee = quantity*D(".003") if side == "BUY" else quantity*price*D(".003")
            return httpx.Response(201,json={"success":True,"result":dict(clientOrderId=payload["client_id"],symbol="USDTTMN",side=side,
                type="LIMIT",price=str(price),origQty=str(quantity),executedQty=str(quantity),executedSum=str(price*quantity),
                status="FILLED",active=False,fills=[dict(symbol="USDTTMN",isBuyer=side=="BUY",price=str(price),quantity=str(quantity),
                    sum=str(price*quantity),fee=str(fee),feeAsset="USDT" if side=="BUY" else "TMN",
                    timestamp=datetime.fromtimestamp(self.now+(side=="SELL"),UTC).isoformat())])})
        self.transport.inner = httpx.MockTransport(fills)
        policy = RiskPolicy(D(100000),D(100000),D(".02"),D(".05"),self.now+600,min_seconds_before_deadline=0)
        with self.worker():
            first = run_pilot_round_trip(self.broker,self.ledger,self.rules,policy,D(250000),self.now,"a"*64)
            self.assertEqual(first["stage"],"SELL")
            self.assertEqual(first["last_exchange_observation"]["http_status"],201)
            with patch("royin.canary.time.time",return_value=self.now+1):
                final = run_pilot_round_trip(self.broker,self.ledger,self.rules,policy,D(250000),self.now+1,"b"*64,
                    exit_quote=dict(price=D(249875),timestamp=self.now+1))
            self.assertEqual(final["status"],"RECONCILIATION_OR_RESIDUAL_REQUIRED")
            self.assertEqual(final["orders_attempted"],2)
            # Buy .39 for97500, receive .38883; sell .38 for94952.5 less284.8575 fee.
            self.assertEqual(D(final["terminal_cash_quote"]),D("97167.64250"))
            self.assertEqual(D(final["terminal_dust_base"]),D(".00883"))
            self.assertEqual(run_pilot_round_trip(self.broker,self.ledger,self.rules,policy,D(250000),self.now+2,"c"*64),final)

    def test_fractional_fill_timestamp_settles_without_changing_whole_second_ids(self):
        risk = RiskResult(True,"technical","ENTER","USDTTMN",D(".36"),D(250000),D(245000),D(270))
        with self.worker():
            self.broker.submit_order(risk,client_id="canary_buy",timestamp=self.now)
        response = dict(clientOrderId="canary_buy",symbol="USDTTMN",side="BUY",type="LIMIT",price="250000",origQty=".36",
            executedQty=".36",executedSum="90000",active=False,status="FILLED",fills=[dict(symbol="USDTTMN",isBuyer=True,
                price="250000",quantity=".36",sum="90000",fee=".00108",feeAsset="USDT",
                timestamp=datetime.fromtimestamp(self.now+1.123456,UTC).isoformat())])
        self.transport.inner = httpx.MockTransport(lambda _:httpx.Response(200,json={"success":True,"result":response}))
        with patch("royin.canary.time.time",return_value=self.now+10), self.worker():
            self.assertEqual(self.broker.reconcile_order("canary_buy",timestamp=self.now+10)["status"],"FILLED")
            self.assertEqual(self.broker.reconcile_order("canary_buy",timestamp=self.now+10)["status"],"FILLED")
        self.assertEqual(self.ledger.get_balance("USDT").free,D(".35892"))
        self.assertEqual(self.ledger.get_balance("TMN").free,D(10000))

    def fill_with_receipt(self, fill_offset, receipt_offset):
        risk = RiskResult(True,"technical","ENTER","USDTTMN",D(".36"),D(250000),D(245000),D(270))
        result = dict(clientOrderId="canary_buy",symbol="USDTTMN",side="BUY",type="LIMIT",price="250000",
            origQty=".36",executedQty=".36",executedSum="90000",active=False,status="FILLED",
            fills=[dict(symbol="USDTTMN",isBuyer=True,price="250000",quantity=".36",sum="90000",
                fee=".00108",feeAsset="USDT",timestamp=datetime.fromtimestamp(self.now+fill_offset,UTC).isoformat())])
        self.transport.inner = httpx.MockTransport(lambda _:httpx.Response(201,json=dict(success=True,result=result)))
        with patch("royin.canary.time.time",return_value=self.now+receipt_offset), self.worker():
            return self.broker.submit_order(risk,client_id="canary_buy",timestamp=self.now)

    def test_fill_between_send_and_receipt_settles(self):
        self.assertEqual(self.fill_with_receipt(2,3)["status"],"FILLED")
        self.assertEqual(self.ledger.get_balance("USDT").free,D(".35892"))
        self.assertEqual(self.ledger.get_balance("TMN").locked,0)
        self.assertEqual(self.ledger.get_balance("TMN").free,D(10000))

    def test_fill_after_receipt_stays_unknown_and_reserved(self):
        self.assertEqual(self.fill_with_receipt(4,3)["status"],"UNKNOWN")
        self.assertEqual(self.ledger.get_balance("USDT").total,0)
        self.assertEqual(self.ledger.get_balance("TMN").locked,D(90270))

    def test_backwards_receipt_clock_stays_unknown_and_reserved(self):
        self.assertEqual(self.fill_with_receipt(0,-1)["status"],"UNKNOWN")
        self.assertEqual(self.ledger.get_balance("USDT").total,0)
        self.assertEqual(self.ledger.get_balance("TMN").locked,D(90270))

    def test_runner_reconciles_real_account_delta_and_never_reports_dust_as_complete(self):
        from royin.markets import Balance
        from scripts import execute_credit_canary as cli
        for mismatch in (False,True):
            root = Path(self.temp.name)/("mismatch" if mismatch else "match")
            (root/"config").mkdir(parents=True)
            (root/"config/wallex-credit-market-policy.json").write_bytes(Path("config/wallex-credit-market-policy.json").read_bytes())
            def server(request, mismatch=mismatch):
                if request.method == "POST":
                    order = json.loads(request.content)
                    p,q = D(order["price"]),D(order["quantity"])
                    buy = order["side"]=="BUY"
                    result = dict(clientOrderId=order["client_id"],symbol="USDTTMN",side=order["side"],type="LIMIT",price=str(p),origQty=str(q),
                        executedQty=str(q),executedSum=str(p*q),active=False,status="FILLED",fills=[dict(symbol="USDTTMN",isBuyer=buy,
                            price=str(p),quantity=str(q),sum=str(p*q),fee=str((q if buy else p*q)*D(".003")),feeAsset="USDT" if buy else "TMN",
                            timestamp=datetime.fromtimestamp(self.now,UTC).isoformat())])
                else:
                    cash = "5000000" if mismatch else "4997071.535"
                    result = {a:dict(symbol=a,total=v,available=v,freeze="0") for a,v in (("TMN",cash),("USDT",".00883"))}
                return httpx.Response(200,json=dict(success=True,result=result))
            with patch.object(cli,"ROOT",root),patch.object(cli,"load_config",return_value=self.config), \
                 patch.object(cli,"clean_revision",return_value="a"*40),patch.object(cli,"canary_state_path",return_value=root/"state.sqlite3"), \
                 patch.object(cli,"preflight",return_value=(self.rules,{"TMN":Balance(D(5000000),D(5000000),D(0))})), \
                 patch.object(cli.CanaryReads,"quote",return_value=(D(249875),D(250000),self.now,"c"*64)), \
                 patch("royin.canary.httpx.HTTPTransport",return_value=httpx.MockTransport(server)), \
                 patch("httpx._client.HTTPTransport",return_value=httpx.MockTransport(server)), \
                 patch.object(cli.time,"sleep"),patch("builtins.print"):
                self.assertEqual(cli.run(True),2)
            report = json.loads(next((root/"data/private").glob("*/report.json")).read_text())
            self.assertEqual(report["orders_attempted"],2)
            self.assertIn("account_reconciliation",report,report)
            self.assertEqual(report["account_reconciliation"],"MISMATCH" if mismatch else "MATCH")
            self.assertEqual(report["status"],"ACCOUNT_RECONCILIATION_REQUIRED" if mismatch else "RECONCILIATION_OR_RESIDUAL_REQUIRED")


if __name__ == "__main__":
    unittest.main()
