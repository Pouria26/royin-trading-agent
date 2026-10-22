import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from royin.ledger import Ledger


class LedgerAccountingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_ledger.sqlite3"
        self.ledger = Ledger(self.db_path)
        self.ledger.set_balance("TMN", free=Decimal("5000000"))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_initial_balance(self):
        tmn = self.ledger.get_balance("TMN")
        self.assertEqual(tmn.free, Decimal("5000000"))
        self.assertEqual(tmn.locked, Decimal(0))
        self.assertEqual(tmn.total, Decimal("5000000"))

    def test_buy_intent_locks_cash(self):
        # Buy 20 USDT at 60,000 TMN = 1,200,000 TMN
        intent = self.ledger.record_intent(
            client_id="order_buy_1",
            symbol="USDTTMN",
            side="BUY",
            order_type="LIMIT",
            price=Decimal("60000"),
            quantity=Decimal("20"),
            timestamp=1790812800,
        )
        self.assertEqual(intent.status, "OPEN")
        tmn = self.ledger.get_balance("TMN")
        self.assertEqual(tmn.free, Decimal("3800000"))
        self.assertEqual(tmn.locked, Decimal("1200000"))
        self.assertEqual(tmn.total, Decimal("5000000"))

    def test_reject_duplicate_client_id(self):
        self.ledger.record_intent(
            client_id="order_buy_1",
            symbol="USDTTMN",
            side="BUY",
            order_type="LIMIT",
            price=Decimal("60000"),
            quantity=Decimal("10"),
            timestamp=1790812800,
        )
        with self.assertRaises(ValueError) as ctx:
            self.ledger.record_intent(
                client_id="order_buy_1",
                symbol="USDTTMN",
                side="BUY",
                order_type="LIMIT",
                price=Decimal("60000"),
                quantity=Decimal("10"),
                timestamp=1790812800,
            )
        self.assertIn("duplicate", str(ctx.exception).lower())

    def test_reject_insufficient_balance(self):
        with self.assertRaises(ValueError) as ctx:
            self.ledger.record_intent(
                client_id="order_too_large",
                symbol="USDTTMN",
                side="BUY",
                order_type="LIMIT",
                price=Decimal("60000"),
                quantity=Decimal("100"),  # 6,000,000 > 5,000,000
                timestamp=1790812800,
            )
        self.assertIn("insufficient", str(ctx.exception).lower())

    def test_cancel_intent_releases_locked_funds(self):
        self.ledger.record_intent(
            client_id="order_cancel",
            symbol="USDTTMN",
            side="BUY",
            order_type="LIMIT",
            price=Decimal("60000"),
            quantity=Decimal("10"),
            timestamp=1790812800,
        )
        self.ledger.cancel_intent("order_cancel")
        tmn = self.ledger.get_balance("TMN")
        self.assertEqual(tmn.free, Decimal("5000000"))
        self.assertEqual(tmn.locked, Decimal(0))

    def test_partial_and_full_fills_with_quote_fee(self):
        # 1. Intent: Buy 20 USDT at 60,000 TMN = 1,200,000 TMN locked
        self.ledger.record_intent(
            client_id="order_pfill",
            symbol="USDTTMN",
            side="BUY",
            order_type="LIMIT",
            price=Decimal("60000"),
            quantity=Decimal("20"),
            timestamp=1790812800,
        )

        # 2. First partial fill: 10 USDT at 60,000 TMN, fee 600 TMN
        f1 = self.ledger.record_fill(
            fill_id="fill_1",
            client_id="order_pfill",
            price=Decimal("60000"),
            quantity=Decimal("10"),
            fee=Decimal("600"),
            fee_asset="TMN",
            timestamp=1790812850,
        )
        self.assertEqual(f1.quantity, Decimal("10"))

        usdt = self.ledger.get_balance("USDT")
        tmn = self.ledger.get_balance("TMN")
        self.assertEqual(usdt.free, Decimal("10"))
        # Locked remaining: 600,000 TMN
        self.assertEqual(tmn.locked, Decimal("600000"))
        # Free cash: 3,800,000 - 600 fee = 3,799,400 TMN
        self.assertEqual(tmn.free, Decimal("3799400"))

        # 3. Repeat fill_1 (idempotency check!)
        f1_repeat = self.ledger.record_fill(
            fill_id="fill_1",
            client_id="order_pfill",
            price=Decimal("60000"),
            quantity=Decimal("10"),
            fee=Decimal("600"),
            fee_asset="TMN",
            timestamp=1790812850,
        )
        self.assertEqual(f1_repeat.fill_id, "fill_1")
        # Balances must be completely unchanged!
        self.assertEqual(self.ledger.get_balance("USDT").free, Decimal("10"))
        self.assertEqual(self.ledger.get_balance("TMN").free, Decimal("3799400"))

        # 4. Second fill completing the order: 10 USDT at 60,000, fee 600 TMN
        self.ledger.record_fill(
            fill_id="fill_2",
            client_id="order_pfill",
            price=Decimal("60000"),
            quantity=Decimal("10"),
            fee=Decimal("600"),
            fee_asset="TMN",
            timestamp=1790812900,
        )
        usdt = self.ledger.get_balance("USDT")
        tmn = self.ledger.get_balance("TMN")
        self.assertEqual(usdt.free, Decimal("20"))
        self.assertEqual(tmn.locked, Decimal(0))
        self.assertEqual(tmn.free, Decimal("3798800"))

    def test_hand_calculated_realized_pnl_example(self):
        # Initial: 5,000,000 TMN
        # Buy 10 USDT at 60,000 TMN, fee 600 TMN. Total buy cost = 600,600 TMN (60,060 TMN/USDT)
        self.ledger.record_intent(
            client_id="order_b",
            symbol="USDTTMN",
            side="BUY",
            order_type="LIMIT",
            price=Decimal("60000"),
            quantity=Decimal("10"),
            timestamp=1790812800,
        )
        self.ledger.record_fill(
            fill_id="f_b",
            client_id="order_b",
            price=Decimal("60000"),
            quantity=Decimal("10"),
            fee=Decimal("600"),
            fee_asset="TMN",
            timestamp=1790812810,
        )

        # Sell 10 USDT at 65,000 TMN, fee 650 TMN.
        # Gross revenue = 650,000 TMN. Net revenue = 649,350 TMN.
        # Cost basis = 600,600 TMN.
        # Realized P&L = 649,350 - 600,600 = +48,750 TMN!
        self.ledger.record_intent(
            client_id="order_s",
            symbol="USDTTMN",
            side="SELL",
            order_type="LIMIT",
            price=Decimal("65000"),
            quantity=Decimal("10"),
            timestamp=1790816400,
        )
        self.ledger.record_fill(
            fill_id="f_s",
            client_id="order_s",
            price=Decimal("65000"),
            quantity=Decimal("10"),
            fee=Decimal("650"),
            fee_asset="TMN",
            timestamp=1790816410,
        )

        pnl = self.ledger.get_realized_pnl("USDTTMN")
        self.assertEqual(pnl, Decimal("48750"))

        # Final cash: 5,000,000 - 600,600 + 649,350 = 5,048,750 TMN
        tmn = self.ledger.get_balance("TMN")
        self.assertEqual(tmn.free, Decimal("5048750"))
        self.assertEqual(self.ledger.get_balance("USDT").total, Decimal(0))

    def test_buy_fill_with_base_fee(self):
        # Buy 10 USDT at 60,000 TMN, fee is 0.01 USDT (base asset fee)
        self.ledger.record_intent(
            client_id="order_base_fee",
            symbol="USDTTMN",
            side="BUY",
            order_type="LIMIT",
            price=Decimal("60000"),
            quantity=Decimal("10"),
            timestamp=1790812800,
        )
        self.ledger.record_fill(
            fill_id="f_base",
            client_id="order_base_fee",
            price=Decimal("60000"),
            quantity=Decimal("10"),
            fee=Decimal("0.01"),
            fee_asset="USDT",
            timestamp=1790812810,
        )
        usdt = self.ledger.get_balance("USDT")
        self.assertEqual(usdt.free, Decimal("9.99"))

    def test_equity_calculation(self):
        # Set up 2,000,000 TMN cash and 50 USDT
        self.ledger.set_balance("TMN", free=Decimal("2000000"))
        self.ledger.set_balance("USDT", free=Decimal("50"))

        # If USDT price is 60,000 TMN: total equity = 2,000,000 + 50 * 60,000 = 5,000,000 TMN
        equity = self.ledger.get_equity({"USDTTMN": Decimal("60000")})
        self.assertEqual(equity, Decimal("5000000"))

    def test_trade_reflection_lifecycle(self):
        self.ledger.record_reflection(
            trade_id="tr_01",
            symbol="USDTTMN",
            pnl_net=Decimal("-4000"),
            return_pct=Decimal("-0.008"),
            lesson_text="Entered on weak momentum break without volume; wait for RVOL > 1.5",
            timestamp=1790812800,
        )
        self.ledger.record_reflection(
            trade_id="tr_02",
            symbol="USDTTMN",
            pnl_net=Decimal("8000"),
            return_pct=Decimal("0.016"),
            lesson_text="Bollinger band squeeze breakout with high volume yielded clean +1.6%",
            timestamp=1790816400,
        )

        reflections = self.ledger.get_recent_reflections("USDTTMN", limit=2)
        self.assertEqual(len(reflections), 2)
        self.assertEqual(reflections[0]["trade_id"], "tr_02")
        self.assertEqual(reflections[0]["pnl_net"], Decimal("8000"))
        self.assertIn("Bollinger", reflections[0]["lesson_text"])
        self.assertEqual(reflections[1]["trade_id"], "tr_01")


if __name__ == "__main__":
    unittest.main()
