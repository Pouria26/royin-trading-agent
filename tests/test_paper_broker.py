import unittest
from decimal import Decimal

from royin.broker import PaperBroker
from royin.ledger import Ledger
from royin.market_data import Candle
from royin.risk import MarketRules, RiskResult


class PaperBrokerTests(unittest.TestCase):
    def setUp(self):
        self.ledger = Ledger(":memory:")
        self.ledger.set_balance("TMN", free=Decimal("5000000"))

        self.rules = MarketRules(
            symbol="USDTTMN",
            base_asset="USDT",
            quote_asset="TMN",
            tick_size=Decimal("1"),
            step_size=Decimal("0.01"),
            min_notional=Decimal("100000"),
            min_quantity=Decimal("1.0"),
            maker_fee_rate=Decimal("0.001"),
            taker_fee_rate=Decimal("0.002"),
        )
        self.broker = PaperBroker(self.ledger, self.rules)

    def _make_risk_result(
        self,
        action="ENTER",
        quantity=Decimal("20.0"),
        price=Decimal("60000"),
        stop_price=Decimal("58200"),
    ):
        return RiskResult(
            approved=True,
            reason="Approved by test",
            action=action,
            symbol="USDTTMN",
            quantity=quantity,
            price=price,
            stop_price=stop_price,
            estimated_fee_quote=quantity * price * Decimal("0.002"),
        )

    def test_submit_order_reserves_funds_in_ledger(self):
        res = self._make_risk_result("ENTER", quantity=Decimal("20.0"), price=Decimal("60000"))
        order = self.broker.submit_order(res, client_id="cid_1", timestamp=1790812800)
        self.assertIsNotNone(order)
        self.assertEqual(order.status, "OPEN")
        # 20 * 60,000 = 1,200,000 cost + 2,400 fee reserve = 1,202,400 locked
        tmn = self.ledger.get_balance("TMN")
        self.assertEqual(tmn.free, Decimal("3797600.0000"))
        self.assertEqual(tmn.locked, Decimal("1202400.0000"))

    def test_process_candle_fills_buy_order_with_slippage(self):
        res = self._make_risk_result("ENTER", quantity=Decimal("20.0"), price=Decimal("60000"))
        self.broker.submit_order(res, client_id="cid_buy", timestamp=1790812800)

        # Candle reaches low 59,500 <= 60,000
        candle = Candle(
            open_time=1790813700,
            open=Decimal("60500"),
            high=Decimal("61000"),
            low=Decimal("59500"),
            close=Decimal("60200"),
            volume=Decimal("100"),
        )
        filled = self.broker.process_candle(candle, slippage_pct=Decimal("0.0005"))
        self.assertIn("cid_buy", filled)
        order = self.broker.orders["cid_buy"]
        self.assertEqual(order.status, "FILLED")
        self.assertEqual(self.ledger.get_balance("USDT").free, Decimal("20.0"))
        self.assertEqual(self.ledger.get_balance("TMN").locked, Decimal(0))

    def test_stop_loss_triggers_automatically_on_candle_drop(self):
        # 1. Buy 20 USDT at 60,000 with stop loss at 58,200
        res = self._make_risk_result("ENTER", quantity=Decimal("20.0"), price=Decimal("60000"), stop_price=Decimal("58200"))
        self.broker.submit_order(res, client_id="cid_sl_buy", timestamp=1790812800)

        # Candle 1 fills the buy order
        c1 = Candle(
            open_time=1790813700,
            open=Decimal("60000"),
            high=Decimal("60500"),
            low=Decimal("59800"),
            close=Decimal("60100"),
            volume=Decimal("50"),
        )
        self.broker.process_candle(c1)
        self.assertEqual(self.ledger.get_balance("USDT").free, Decimal("20.0"))

        # Candle 2 drops sharply below stop price 58,200 (low = 57,500)
        c2 = Candle(
            open_time=1790814600,
            open=Decimal("59000"),
            high=Decimal("59200"),
            low=Decimal("57500"),
            close=Decimal("57800"),
            volume=Decimal("80"),
        )
        filled = self.broker.process_candle(c2)
        # Stop loss order must trigger and sell the 20 USDT!
        self.assertEqual(self.ledger.get_balance("USDT").total, Decimal(0))
        self.assertNotIn("USDTTMN", self.broker.active_stop_prices)
        self.assertTrue(any(f.startswith("stop_") for f in filled))

    def test_reconcile_unknown_order(self):
        res = self._make_risk_result("ENTER", quantity=Decimal("10.0"), price=Decimal("60000"))
        order = self.broker.submit_order(res, client_id="cid_unk", timestamp=1790812800, simulate_unknown=True)
        self.assertEqual(order.status, "UNKNOWN")

        # Reconcile as FILLED without generating a new client_id!
        reconciled = self.broker.reconcile_order("cid_unk", simulated_state="FILLED", timestamp=1790812900)
        self.assertEqual(reconciled.status, "FILLED")
        self.assertEqual(reconciled.client_id, "cid_unk")
        self.assertEqual(self.ledger.get_balance("USDT").free, Decimal("10.0"))

    def test_finalize_portfolio_is_idempotent(self):
        # Buy 10 USDT and keep 10 USDT open
        res = self._make_risk_result("ENTER", quantity=Decimal("10.0"), price=Decimal("60000"))
        self.broker.submit_order(res, client_id="cid_b", timestamp=1790812800)
        c = Candle(
            open_time=1790813700,
            open=Decimal("60000"),
            high=Decimal("60500"),
            low=Decimal("59500"),
            close=Decimal("60100"),
            volume=Decimal("50"),
        )
        self.broker.process_candle(c)

        # Submit another order that remains OPEN
        res2 = self._make_risk_result("ENTER", quantity=Decimal("10.0"), price=Decimal("55000"))
        self.broker.submit_order(res2, client_id="cid_open", timestamp=1790813800)

        # Call finalize_portfolio at price 62,000 TMN
        fin1 = self.broker.finalize_portfolio(current_price=Decimal("62000"), timestamp=1792788600)
        self.assertEqual(fin1["status"], "FINALIZED")
        self.assertEqual(self.ledger.get_balance("USDT").total, Decimal(0))
        self.assertEqual(self.ledger.get_balance("TMN").locked, Decimal(0))

        cash1 = fin1["final_tmn_cash"]

        # Call finalize_portfolio again (idempotent check)
        fin2 = self.broker.finalize_portfolio(current_price=Decimal("62000"), timestamp=1792788600)
        self.assertEqual(fin2["final_tmn_cash"], cash1)
        self.assertEqual(fin2["liquidated_base_quantity"], "0")


if __name__ == "__main__":
    unittest.main()
