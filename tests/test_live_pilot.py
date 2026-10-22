"""Tests for technical micro-pilot runner and safety gates."""

import json
import unittest
from decimal import Decimal

import httpx

from royin.config import RuntimeConfig
from royin.ledger import Ledger
from royin.live_broker import LiveTradingSafetyGateError, WallexLiveBroker
from royin.risk import MarketRules, RiskPolicy, RiskResult
from scripts.run_live_pilot import (
    evaluate_pilot_sellability,
    main,
    prepare_pilot_packet,
    run_pilot_round_trip,
)


class LivePilotTests(unittest.TestCase):
    def test_partial_buy_and_restart_never_resubmit_or_sell(self):
        from datetime import UTC, datetime
        seen=[]
        original={}
        now=1788220805
        def handle(request):
            seen.append(request.method)
            if request.method=="POST":
                original.update(json.loads(request.content))
            q=Decimal(original["quantity"])/2
            p=Decimal(original["price"])
            row=dict(clientOrderId=original["client_id"],symbol="USDTTMN",side="BUY",type="LIMIT",
                price=str(p),origQty=original["quantity"],executedQty=str(q),executedSum=str(p*q),
                active=True,status="PARTIALLY_FILLED",fills=[dict(symbol="USDTTMN",isBuyer=True,
                    price=str(p),quantity=str(q),sum=str(p*q),fee=str(p*q*Decimal(".003")),feeAsset="TMN",
                    timestamp=datetime.fromtimestamp(now,UTC).isoformat())])
            return httpx.Response(200,json=dict(success=True,result=row))
        ledger=Ledger()
        ledger.set_balance("TMN",Decimal(5000000))
        with httpx.Client(transport=httpx.MockTransport(handle)) as client:
            broker=WallexLiveBroker(ledger,self.rules,self.config,http_client=client,enable_live_trading=True,run_mode="live")
            kwargs=dict(broker=broker,ledger=ledger,rules=self.rules,policy=self.policy,current_price=Decimal(260000),
                        current_time=now,snapshot_sha256="a"*64)
            first=run_pilot_round_trip(**kwargs)
            second=run_pilot_round_trip(**kwargs)
        self.assertFalse(first["buy_settled"])
        self.assertFalse(second["sell_settled"])
        self.assertEqual(seen,["POST","GET"])
        self.assertEqual(first["buy_id"],second["buy_id"])

    def test_sellability_fee_asset_scenarios_have_manual_residual_oracles(self):
        args=dict(price=Decimal(100),taker_fee_rate=Decimal(".01"),step_size=Decimal(".1"),
                  ceiling_tmn=Decimal(202),min_quantity=Decimal(1),min_notional=Decimal(100),exit_drawdown_pct=Decimal(".1"))
        quote=evaluate_pilot_sellability(**args,fee_asset_scenario="QUOTE_BOTH")
        base=evaluate_pilot_sellability(**args,fee_asset_scenario="BASE_BOTH")
        mixed=evaluate_pilot_sellability(**args,fee_asset_scenario="BASE_BUY_QUOTE_SELL")
        self.assertEqual(Decimal(quote["cash_debit_tmn"]),Decimal(202))
        self.assertEqual(Decimal(quote["net_liquidation_tmn"]),Decimal("178.2"))
        self.assertEqual(Decimal(base["residual_base"]),Decimal(".061"))
        self.assertEqual(Decimal(mixed["residual_base"]),Decimal(".08"))
        for value in (Decimal("NaN"),Decimal(1),Decimal(-1)):
            with self.assertRaises(ValueError):
                evaluate_pilot_sellability(**{**args,"taker_fee_rate":value})

    def setUp(self):
        self.rules = MarketRules(
            symbol="USDTTMN",
            base_asset="USDT",
            quote_asset="TMN",
            tick_size=Decimal("1"),
            step_size=Decimal("0.01"),
            min_notional=Decimal("100000"),
            min_quantity=Decimal("1.0"),
            maker_fee_rate=Decimal("0.0025"),
            taker_fee_rate=Decimal("0.0030"),
        )
        self.policy = RiskPolicy(
            max_order_tmn=Decimal("500000"),
            max_exposure_tmn=Decimal("500000"),
            stop_loss_pct=Decimal("0.02"),
            max_drawdown_pct=Decimal("0.05"),
            deadline_utc=2000000000,
            min_seconds_before_deadline=3600,
            max_stale_seconds=1800,
        )
        self.config = RuntimeConfig(
            WALLEX_API_KEY="synthetic-key",
            SUB_ACCOUNT_CLIENT_ID="synthetic-account",
            WALLEX_ALLOWED_MARKETS=("USDTTMN",),
        )

    def test_safe_cli_no_args_prints_help_and_exits_zero(self):
        code = main([])
        self.assertEqual(code, 0)

    def test_run_cli_fails_closed_with_blocked_safety_gate(self):
        code = main(["--run"])
        self.assertEqual(code, 2)

    def test_sellability_at_200k_tmn_and_current_price_is_blocked_minimum(self):
        # At 266,721 TMN / USDT, 200,000 TMN buys ~0.74 USDT, below min_quantity 1.0 USDT
        result = evaluate_pilot_sellability(
            price=Decimal("266721"),
            taker_fee_rate=Decimal("0.0030"),
            step_size=Decimal("0.01"),
            ceiling_tmn=Decimal("200000"),
            min_quantity=Decimal("1.0"),
            min_notional=Decimal("100000"),
        )
        self.assertEqual(result["status"], "BLOCKED_MINIMUM")
        self.assertEqual(result["target_qty"], "0.74")
        self.assertIn("below min_quantity 1.0", result["reason"])

    def test_sellability_passes_when_notional_satisfies_min_quantity_and_min_notional(self):
        # At 266,721 TMN / USDT, 300,000 TMN buys ~1.12 USDT, post-fee sellable is ~1.11 USDT
        result = evaluate_pilot_sellability(
            price=Decimal("266721"),
            taker_fee_rate=Decimal("0.0030"),
            step_size=Decimal("0.01"),
            ceiling_tmn=Decimal("300000"),
            min_quantity=Decimal("1.0"),
            min_notional=Decimal("100000"),
        )
        self.assertEqual(result["status"], "PASS_SELLABLE")
        self.assertEqual(result["target_qty"], "1.12")
        self.assertEqual(result["sellable_qty"], "1.11")

    def test_prepare_packet_generation(self):
        packet = prepare_pilot_packet(
            config=self.config,
            market_rules=self.rules,
            current_price=Decimal("266721"),
            denied_markets=frozenset(),
        )
        self.assertEqual(packet["kind"], "TECHNICAL_MICRO_PILOT_REVIEW_PACKET")
        self.assertEqual(packet["symbol"], "USDTTMN")
        self.assertEqual(packet["gates_status"]["sellability_gate"], "PASS_SELLABLE")
        self.assertEqual(packet["recommended_action"], "NO_GO_CRITICAL_CONTRACT_UNKNOWN")
        self.assertEqual(packet["release_status"],"NO_GO")

    def test_prepare_packet_with_explicit_low_ceiling_is_blocked(self):
        packet = prepare_pilot_packet(
            config=self.config,
            market_rules=self.rules,
            current_price=Decimal("266721"),
            ceiling_tmn=Decimal("200000"),
            denied_markets=frozenset(),
        )
        self.assertEqual(packet["gates_status"]["sellability_gate"], "BLOCKED_MINIMUM")
        self.assertIn("BLOCKED_MINIMUM", packet["recommended_action"])

    def test_mock_round_trip_buy_and_exit_with_dust_reporting(self):
        ledger = Ledger(":memory:")
        ledger.set_balance("TMN", Decimal("5000000"))
        ledger.set_balance("USDT", Decimal("0"))

        now = 1788220805

        # Create MockTransport to handle BUY and EXIT SELL
        def handle_request(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            method = request.method
            if method == "POST" and path == "/v1/account/orders":
                body = json.loads(request.content.decode("utf-8"))
                side = body.get("side")
                client_id = body.get("client_id")
                qty = body.get("quantity")
                price = body.get("price")
                if side == "BUY":
                    # Instant fill
                    fee = (Decimal(qty) * Decimal(price) * Decimal("0.003")).quantize(Decimal("1"))
                    res = {
                        "clientOrderId": client_id,
                        "symbol": "USDTTMN",
                        "side": "BUY",
                        "type": "LIMIT",
                        "price": price,
                        "origQty": qty,
                        "executedQty": qty,
                        "executedSum": str(Decimal(qty) * Decimal(price)),
                        "active": False,
                        "status": "FILLED",
                        "fills": [
                            {
                                "symbol": "USDTTMN",
                                "isBuyer": True,
                                "price": price,
                                "quantity": qty,
                                "sum": str(Decimal(qty) * Decimal(price)),
                                "fee": str(fee),
                                "feeAsset": "TMN",
                                "timestamp": "2026-09-01T00:00:05Z",
                            }
                        ],
                    }
                else:
                    # SELL fill
                    fee = (Decimal(qty) * Decimal(price) * Decimal("0.003")).quantize(Decimal("1"))
                    res = {
                        "clientOrderId": client_id,
                        "symbol": "USDTTMN",
                        "side": "SELL",
                        "type": "LIMIT",
                        "price": price,
                        "origQty": qty,
                        "executedQty": qty,
                        "executedSum": str(Decimal(qty) * Decimal(price)),
                        "active": False,
                        "status": "FILLED",
                        "fills": [
                            {
                                "symbol": "USDTTMN",
                                "isBuyer": False,
                                "price": price,
                                "quantity": qty,
                                "sum": str(Decimal(qty) * Decimal(price)),
                                "fee": str(fee),
                                "feeAsset": "TMN",
                                "timestamp": "2026-09-01T00:01:05Z",
                            }
                        ],
                    }
                return httpx.Response(201, json={"success": True, "result": res})
            return httpx.Response(404, json={"success": False, "message": "Not found"})

        mock_client = httpx.Client(transport=httpx.MockTransport(handle_request))
        broker = WallexLiveBroker(
            ledger=ledger,
            market_rules=self.rules,
            config=self.config,
            http_client=mock_client,
            enable_live_trading=True,
            run_mode="live",
        )

        # Policy with max order 300,000 to allow >= 1.0 USDT order
        flexible_policy = RiskPolicy(
            max_order_tmn=Decimal("350000"),
            max_exposure_tmn=Decimal("500000"),
            stop_loss_pct=Decimal("0.02"),
            max_drawdown_pct=Decimal("0.05"),
            deadline_utc=2000000000,
        )

        summary = run_pilot_round_trip(
            broker=broker,
            ledger=ledger,
            rules=self.rules,
            policy=flexible_policy,
            current_price=Decimal("260000"),
            current_time=now,
            snapshot_sha256="0" * 64,
            client_id_prefix="mock_test",
        )

        self.assertEqual(summary["status"],"AWAIT_FRESH_EXIT_QUOTE")
        self.assertFalse(summary["sell_settled"])
        summary=run_pilot_round_trip(broker,ledger,self.rules,flexible_policy,Decimal("260000"),now+60,
            "0"*64,client_id_prefix="mock_test",exit_quote=dict(price=Decimal("260000"),timestamp=now+60))

        self.assertEqual(summary["status"], "COMPLETE_ROUND_TRIP")
        self.assertTrue(summary["buy_settled"])
        self.assertTrue(summary["sell_settled"])
        self.assertEqual(summary["orders_attempted"], 2)
        # Position returned to TMN cash
        final_usdt = ledger.get_balance("USDT")
        final_tmn = ledger.get_balance("TMN")
        self.assertEqual(final_usdt.total, Decimal("0"))
        self.assertTrue(final_tmn.total > Decimal("4900000"))

    def test_production_transport_rejection(self):
        # A live broker without MockTransport must raise LiveTradingSafetyGateError
        real_like_client = httpx.Client()
        broker = WallexLiveBroker(
            ledger=Ledger(":memory:"),
            market_rules=self.rules,
            config=self.config,
            http_client=real_like_client,
            enable_live_trading=True,
            run_mode="live",
        )
        risk_result = RiskResult(
            approved=True,
            reason="Approved",
            action="ENTER",
            symbol="USDTTMN",
            quantity=Decimal("1.0"),
            price=Decimal("260000"),
            stop_price=Decimal("254800"),
            estimated_fee_quote=Decimal("780"),
        )
        with self.assertRaises(LiveTradingSafetyGateError):
            broker.submit_order(risk_result, client_id="test_ord", timestamp=1000)


if __name__ == "__main__":
    unittest.main()
