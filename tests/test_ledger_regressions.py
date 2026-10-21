import unittest
from decimal import Decimal

from royin.ledger import Ledger


class LedgerRegressionTests(unittest.TestCase):
    def test_repro_sqlite_sum_text_float_precision_bug(self):
        """Repro: BUY price=1, qty=0.3; fill 1 = 0.1; fill 2 = 0.2 should not fail with float precision error."""
        ledger = Ledger(":memory:")
        ledger.set_balance("TMN", free=Decimal("100"))

        ledger.record_intent(
            client_id="cid_repro",
            symbol="USDTTMN",
            side="BUY",
            order_type="LIMIT",
            price=Decimal("1"),
            quantity=Decimal("0.3"),
            timestamp=1000,
            quote_fee_reserve=Decimal("0.001"),
        )

        # Fill 1: 0.1
        ledger.record_fill(
            fill_id="f1",
            client_id="cid_repro",
            price=Decimal("1"),
            quantity=Decimal("0.1"),
            fee=Decimal(0),
            fee_asset="TMN",
            timestamp=1001,
        )

        # Fill 2: 0.2 -> must succeed without float epsilon error
        ledger.record_fill(
            fill_id="f2",
            client_id="cid_repro",
            price=Decimal("1"),
            quantity=Decimal("0.2"),
            fee=Decimal(0),
            fee_asset="TMN",
            timestamp=1002,
        )

        bal_usdt = ledger.get_balance("USDT")
        self.assertEqual(bal_usdt.free, Decimal("0.3"))

    def test_repro_float_in_set_balance_and_strict_validation(self):
        """Float, bool, NaN, Infinity, negative, and invalid types must be rejected."""
        ledger = Ledger(":memory:")

        # float rejected
        with self.assertRaises(TypeError):
            ledger.set_balance("TMN", 1.25)  # type: ignore

        # bool rejected
        with self.assertRaises(TypeError):
            ledger.set_balance("TMN", True)  # type: ignore

        # negative rejected
        with self.assertRaises(ValueError):
            ledger.set_balance("TMN", Decimal("-10"))

        # NaN / Infinity rejected
        with self.assertRaises(ValueError):
            ledger.set_balance("TMN", Decimal("NaN"))
        with self.assertRaises(ValueError):
            ledger.set_balance("TMN", Decimal("Infinity"))

    def test_conflicting_fill_payload_with_same_id_is_rejected(self):
        ledger = Ledger(":memory:")
        ledger.set_balance("TMN", free=Decimal("1000"))

        ledger.record_intent(
            client_id="cid_conflict",
            symbol="USDTTMN",
            side="BUY",
            order_type="LIMIT",
            price=Decimal("10"),
            quantity=Decimal("10"),
            timestamp=1000,
            quote_fee_reserve=Decimal("1"),
        )

        ledger.record_fill(
            fill_id="fill_1",
            client_id="cid_conflict",
            price=Decimal("10"),
            quantity=Decimal("5"),
            fee=Decimal("0.1"),
            fee_asset="TMN",
            timestamp=1001,
        )

        # Exact duplicate payload should succeed idempotently
        dup = ledger.record_fill(
            fill_id="fill_1",
            client_id="cid_conflict",
            price=Decimal("10"),
            quantity=Decimal("5"),
            fee=Decimal("0.1"),
            fee_asset="TMN",
            timestamp=1001,
        )
        self.assertEqual(dup.fill_id, "fill_1")

        # Conflicting payload with different quantity must raise ValueError
        with self.assertRaises(ValueError):
            ledger.record_fill(
                fill_id="fill_1",
                client_id="cid_conflict",
                price=Decimal("10"),
                quantity=Decimal("6"),  # different
                fee=Decimal("0.1"),
                fee_asset="TMN",
                timestamp=1001,
            )

    def test_fee_reservation_prevents_negative_free_cash(self):
        """Fee must be paid out of reserved funds, never making free cash negative."""
        ledger = Ledger(":memory:")
        ledger.set_balance("TMN", free=Decimal("1000"))

        # Trader wants to buy 100 USDT at 10 TMN = 1000 TMN
        # Fee is 0.3% = 3 TMN
        # Total needed reserve = 1003 TMN. Since free is 1000, it must fail to record intent!
        with self.assertRaises(ValueError):
            ledger.record_intent(
                client_id="cid_nofee",
                symbol="USDTTMN",
                side="BUY",
                order_type="LIMIT",
                price=Decimal("10"),
                quantity=Decimal("100"),
                timestamp=1000,
                quote_fee_reserve=Decimal("3.0"),
            )

        # With 1003 TMN free, intent succeeds and locks 1003 TMN
        ledger.set_balance("TMN", free=Decimal("1003"))
        ledger.record_intent(
            client_id="cid_withfee",
            symbol="USDTTMN",
            side="BUY",
            order_type="LIMIT",
            price=Decimal("10"),
            quantity=Decimal("100"),
            timestamp=1000,
            quote_fee_reserve=Decimal("3.0"),
        )
        self.assertEqual(ledger.get_balance("TMN").free, Decimal(0))
        self.assertEqual(ledger.get_balance("TMN").locked, Decimal("1003.0"))

        # Fill with 3 TMN fee: free cash stays 0, not -3!
        ledger.record_fill(
            fill_id="f_full",
            client_id="cid_withfee",
            price=Decimal("10"),
            quantity=Decimal("100"),
            fee=Decimal("3.0"),
            fee_asset="TMN",
            timestamp=1005,
        )
        self.assertEqual(ledger.get_balance("TMN").free, Decimal(0))
        self.assertEqual(ledger.get_balance("TMN").locked, Decimal(0))
        self.assertEqual(ledger.get_balance("USDT").free, Decimal("100"))


if __name__ == "__main__":
    unittest.main()
