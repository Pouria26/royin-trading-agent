"""Dust classification preserves actual financial state and demands original fills."""

import hashlib
import json
import unittest
from dataclasses import asdict, replace
from decimal import Decimal as D

from royin.ledger import Ledger
from royin.live_broker import WallexLiveBroker
from royin.residuals import KEY, quarantine_residual, quarantined_residuals
from royin.risk import MarketRules


class ResidualTests(unittest.TestCase):
    def setUp(self):
        self.ledger = Ledger()
        self.ledger.set_balance("TMN", D("5000000"))
        WallexLiveBroker.initialize_state(self.ledger)
        self.rules = MarketRules("ETHTMN", "ETH", "TMN", D(1), D(".01"), D(100000),
                                 D(".01"), D(".0025"), D(".003"))

    def position(self, rules=None, *, bought="100.0076", sold="100", partial=False,
                 buy_fee="0", buy_fee_asset="TMN", sell_fee="300", sell_fee_asset="TMN"):
        rules = rules or self.rules
        asset, symbol = rules.base_asset, rules.symbol
        buy, sell = asset + "_buy", asset + "_sell"
        self.ledger.set_meta("fresh_evidence_" + buy, json.dumps(dict(
            source_kind="REAL_MODEL", action="ENTER", symbol=symbol,
            rules_sha256=hashlib.sha256(json.dumps(asdict(rules), default=str, sort_keys=True).encode()).hexdigest())))
        self.ledger.record_intent(client_id=buy, symbol=symbol, side="BUY", order_type="LIMIT",
                                  price=D(1000), quantity=D(bought), timestamp=1000,
                                  base_asset=asset, quote_asset="TMN")
        self.ledger.record_fill(fill_id=buy + "_fill", client_id=buy, price=D(1000),
                                quantity=D(bought), fee=D(buy_fee), fee_asset=buy_fee_asset, timestamp=1001)
        self.ledger.record_intent(client_id=sell, symbol=symbol, side="SELL", order_type="LIMIT",
                                  price=D(1000), quantity=D(sold) + (D(".001") if partial else 0),
                                  timestamp=1100, base_asset=asset, quote_asset="TMN")
        self.ledger.record_fill(fill_id=sell + "_fill", client_id=sell, price=D(1000),
                                quantity=D(sold), fee=D(sell_fee), fee_asset=sell_fee_asset, timestamp=1101)
        if partial:
            self.ledger.cancel_intent(sell)
        with self.ledger.transaction() as db:
            for cid in (buy, sell):
                row = db.execute("SELECT client_id,symbol,side,order_type,price,quantity,status,created_at "
                                 "FROM order_intents WHERE client_id=?", (cid,)).fetchone()
                db.execute("INSERT INTO live_broker_orders(client_id,symbol,side,order_type,price,quantity,"
                           "status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)", (*row, 1102))
        return buy, sell

    def quarantine(self, rules=None, **kwargs):
        return quarantine_residual(self.ledger, rules or self.rules,
                                   **{"price_tmn": D(1000), "quote_received_at": 1200, "now": 1202, **kwargs})

    def financial_snapshot(self):
        with self.ledger.connection() as db:
            tables = ["balances", "order_intents", "fills", "cost_basis", "realized_pnl", "live_broker_orders"]
            return {name: db.execute("SELECT * FROM " + name + " ORDER BY rowid").fetchall() for name in tables}

    def test_audited_classification_preserves_money_origin_round_trips_and_is_idempotent(self):
        self.position()
        before = self.financial_snapshot()
        origin = self.ledger.get_meta("position_origin_ETH")
        self.assertEqual(self.ledger.get_meta("closed_round_trips"), None)
        self.assertTrue(self.quarantine())
        saved = self.ledger.get_meta(KEY)
        self.assertEqual(quarantined_residuals(self.ledger), {"ETH": D(".0076")})
        self.assertTrue(self.quarantine(now=1204))
        self.assertEqual(self.ledger.get_meta(KEY), saved)
        self.assertEqual(self.financial_snapshot(), before)
        self.assertEqual(self.ledger.get_meta("position_origin_ETH"), origin)
        self.assertEqual(self.ledger.get_meta("closed_round_trips"), None)

    def test_fee_reserve_plus_step_bound_is_accepted_without_inventing_fill(self):
        self.position(bought="100.30")
        self.assertTrue(self.quarantine())
        self.assertEqual(quarantined_residuals(self.ledger), {"ETH": D(".30")})

    def test_original_base_fees_and_average_cost_are_preserved(self):
        self.position(bought="100.31", sold="99.70", buy_fee=".3", buy_fee_asset="ETH",
                      sell_fee=".2991", sell_fee_asset="ETH")
        before = self.financial_snapshot()
        self.assertTrue(self.quarantine())
        self.assertEqual(quarantined_residuals(self.ledger), {"ETH": D(".0109")})
        self.assertEqual(self.financial_snapshot(), before)

    def test_tradeable_and_quantity_or_value_caps_cannot_be_quarantined(self):
        for bought, price in [("100.4", "1000"), ("100.0076", "100000"), ("200", "1000")]:
            with self.subTest(bought=bought, price=price):
                self.setUp()
                self.position(bought=bought)
                self.assertFalse(self.quarantine(price_tmn=D(price)))
                self.assertIsNone(self.ledger.get_meta(KEY))

    def test_acquisition_cost_fraction_is_enforced_independently_of_500_tmn(self):
        self.position(bought="1.0076", sold="1")
        self.assertFalse(self.quarantine())  # 7.6 TMN > 0.5% of 1007.6 TMN.

    def test_stale_future_or_invalid_quote_never_writes(self):
        self.position()
        for changes in ({"now": 1206}, {"now": 1199}, {"price_tmn": D("NaN")},
                        {"price_tmn": D(-1)}, {"quote_received_at": True}):
            with self.subTest(changes=changes), self.assertRaises((ValueError, TypeError)):
                self.quarantine(**changes)
        self.assertIsNone(self.ledger.get_meta(KEY))

    def test_missing_buy_sell_and_broker_proofs_fail_closed(self):
        self.ledger.set_balance("ETH", D(".001"))
        with self.assertRaises(ValueError):
            self.quarantine()
        self.setUp()
        self.position()
        with self.ledger.transaction() as db:
            db.execute("DELETE FROM live_broker_orders WHERE side='SELL'")
        with self.assertRaises(ValueError):
            self.quarantine()

    def test_pending_or_unknown_orders_block_classification(self):
        self.position()
        with self.ledger.transaction() as db:
            db.execute("UPDATE live_broker_orders SET status='UNKNOWN' WHERE side='SELL'")
        with self.assertRaises(ValueError):
            self.quarantine()
        self.assertIsNone(self.ledger.get_meta(KEY))

    def test_pending_other_asset_blocks_new_classification(self):
        self.position()
        self.ledger.record_intent(client_id="other", symbol="BTCTMN", side="BUY", order_type="LIMIT",
                                  price=D(1), quantity=D(1), timestamp=1150, base_asset="BTC")
        with self.assertRaises(ValueError):
            self.quarantine()

    def test_locked_or_growth_or_basis_change_invalidates_existing_receipt(self):
        for mutation in ("growth", "locked", "basis", "origin"):
            with self.subTest(mutation=mutation):
                self.setUp()
                self.position()
                self.quarantine()
                saved = self.ledger.get_meta(KEY)
                if mutation == "growth":
                    self.ledger.set_balance("ETH", D(".008"))
                elif mutation == "locked":
                    self.ledger.set_balance("ETH", D(".0066"), D(".001"))
                elif mutation == "origin":
                    self.ledger.set_meta("position_origin_ETH", "foreign")
                else:
                    with self.ledger.transaction() as db:
                        db.execute("UPDATE cost_basis SET total_cost_quote='1' WHERE asset='ETH'")
                with self.assertRaises(ValueError):
                    quarantined_residuals(self.ledger)
                self.assertEqual(self.ledger.get_meta(KEY), saved)

    def test_receipt_or_original_fill_tamper_is_rejected(self):
        self.position()
        self.quarantine()
        saved = self.ledger.get_meta(KEY)
        receipts = json.loads(saved)
        receipts[0]["quantity"] = ".001"
        self.ledger.set_meta(KEY, json.dumps(receipts))
        with self.assertRaises(ValueError):
            quarantined_residuals(self.ledger)
        self.ledger.set_meta(KEY, saved)
        with self.ledger.transaction() as db:
            db.execute("UPDATE fills SET timestamp=timestamp+1 WHERE client_id='ETH_sell'")
        with self.assertRaises(ValueError):
            quarantined_residuals(self.ledger)

    def test_original_model_evidence_and_rules_are_mandatory(self):
        self.position()
        with self.assertRaises(ValueError):
            self.quarantine(replace(self.rules, step_size=D(".02")))
        self.ledger.set_meta("fresh_evidence_ETH_buy", json.dumps({"source_kind": "FAKE_MODEL"}))
        with self.assertRaises(ValueError):
            self.quarantine()

    def test_pending_broker_after_quarantine_and_partial_fill_without_terminal_do_not_pass(self):
        self.position()
        self.quarantine()
        with self.ledger.transaction() as db:
            db.execute("UPDATE live_broker_orders SET status='UNKNOWN' WHERE side='SELL'")
        with self.assertRaises(ValueError):
            quarantined_residuals(self.ledger)

    def test_failed_append_rolls_back_and_retains_prior_receipts(self):
        self.position()
        with self.assertRaises(RuntimeError), self.ledger.transaction():
            self.quarantine()
            raise RuntimeError("synthetic outer crash")
        self.assertIsNone(self.ledger.get_meta(KEY))

    def test_partial_canceled_with_only_tiny_remaining_dust_requires_actual_fills(self):
        self.position(partial=True)
        self.assertTrue(self.quarantine())
        self.assertEqual(quarantined_residuals(self.ledger)["ETH"], D(".0076"))

    def test_empty_quarantine_and_changed_rules(self):
        self.assertEqual(quarantined_residuals(self.ledger), {})
        self.assertFalse(self.quarantine())
        self.position()
        self.quarantine()
        with self.assertRaises(ValueError):
            self.quarantine(replace(self.rules, step_size=D(".02")))

    def test_maximum_eight_assets_is_durable_and_append_only(self):
        original = []
        for number in range(8):
            rules = replace(self.rules, base_asset=f"A{number}", symbol=f"A{number}TMN")
            self.position(rules)
            self.assertTrue(self.quarantine(rules))
            receipts = json.loads(self.ledger.get_meta(KEY))
            self.assertEqual(receipts[:-1], original)
            original = receipts
        self.assertEqual(len(quarantined_residuals(self.ledger)), 8)
        rules = replace(self.rules, base_asset="A8", symbol="A8TMN")
        self.position(rules)
        with self.assertRaises(ValueError):
            self.quarantine(rules)
        self.assertEqual(json.loads(self.ledger.get_meta(KEY)), original)


if __name__ == "__main__":
    unittest.main()
