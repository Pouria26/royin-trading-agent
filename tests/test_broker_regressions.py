import unittest
from decimal import Decimal

from royin.broker import PaperBroker
from royin.ledger import Ledger
from royin.market_data import Candle
from royin.risk import MarketRules, RiskResult


class BrokerRegressionTests(unittest.TestCase):
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

    def test_repro_limit_buy_never_fills_above_limit_price(self):
        """A LIMIT BUY order at 60,000 must NEVER fill at a price higher than 60,000."""
        risk_res = RiskResult(
            approved=True,
            reason="Test BUY",
            action="ENTER",
            symbol="USDTTMN",
            quantity=Decimal("10.0"),
            price=Decimal("60000"),
            stop_price=Decimal("58000"),
            estimated_fee_quote=Decimal("1200"),
        )
        self.broker.submit_order(risk_res, client_id="cid_buy_limit", timestamp=1000)

        # Candle dips to low 59,000 (below 60,000). High is 61,000.
        candle = Candle(
            open_time=1100,
            open=Decimal("60500"),
            high=Decimal("61000"),
            low=Decimal("59000"),
            close=Decimal("59500"),
            volume=Decimal("100"),
        )
        self.broker.process_candle(candle, slippage_pct=Decimal("0.05"))  # 5% slippage

        order = self.broker.orders["cid_buy_limit"]
        self.assertEqual(order.status, "FILLED")
        # Execution price MUST be <= order.price (60,000), NEVER 60,000 * 1.05 = 63,000!
        self.assertLessEqual(order.price, Decimal("60000"))

    def test_repro_limit_sell_never_fills_below_limit_price(self):
        """A LIMIT SELL order at 60,000 must NEVER fill at a price lower than 60,000."""
        self.ledger.set_balance("USDT", free=Decimal("20.0"))
        risk_res = RiskResult(
            approved=True,
            reason="Test SELL",
            action="EXIT",
            symbol="USDTTMN",
            quantity=Decimal("10.0"),
            price=Decimal("60000"),
            stop_price=None,
            estimated_fee_quote=Decimal("1200"),
        )
        self.broker.submit_order(risk_res, client_id="cid_sell_limit", timestamp=1000)

        # Candle reaches high 61,000 (above 60,000). Low is 58,000.
        candle = Candle(
            open_time=1100,
            open=Decimal("59000"),
            high=Decimal("61000"),
            low=Decimal("58000"),
            close=Decimal("60500"),
            volume=Decimal("100"),
        )
        self.broker.process_candle(candle, slippage_pct=Decimal("0.05"))

        order = self.broker.orders["cid_sell_limit"]
        self.assertEqual(order.status, "FILLED")
        # Execution price MUST be >= order.price (60,000), NEVER 60,000 * 0.95 = 57,000!
        self.assertGreaterEqual(order.price, Decimal("60000"))

    def test_candle_before_order_creation_never_fills_order(self):
        """Candles from the past must not match orders created in the future."""
        risk_res = RiskResult(
            approved=True,
            reason="Future BUY",
            action="ENTER",
            symbol="USDTTMN",
            quantity=Decimal("10.0"),
            price=Decimal("60000"),
            stop_price=None,
            estimated_fee_quote=Decimal("1200"),
        )
        # Order created at timestamp 2000
        self.broker.submit_order(risk_res, client_id="cid_future", timestamp=2000)

        # Candle at timestamp 1000 (before order was created)
        old_candle = Candle(
            open_time=1000,
            open=Decimal("59000"),
            high=Decimal("59500"),
            low=Decimal("58500"),
            close=Decimal("59000"),
            volume=Decimal("100"),
        )
        filled = self.broker.process_candle(old_candle, candle_interval=900)
        self.assertNotIn("cid_future", filled)
        self.assertEqual(self.broker.orders["cid_future"].status, "OPEN")


if __name__ == "__main__":
    unittest.main()
