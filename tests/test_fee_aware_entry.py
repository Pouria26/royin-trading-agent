"""Fee-aware entry gate and per-market paper rules."""

import unittest
from decimal import Decimal as D
from types import SimpleNamespace

from scripts.run_market_paper import build_default_rules, fee_aware_entry


def snap(*, evidences=("EV_TREND_BULLISH", "EV_BB_EXPANDING"), atr="0.1", close="100",
         interval=3600, fast="101", slow="100"):
    return SimpleNamespace(
        evidences=set(evidences), atr_14=D(atr), last_close=D(close),
        interval_seconds=interval, trend_sma_fast=D(fast), trend_sma_slow=D(slow),
    )


class FeeAwareEntryTests(unittest.TestCase):
    def test_strong_trend_and_expected_move_pass(self):
        self.assertTrue(fee_aware_entry(snap(), hold_seconds=259200))

    def test_missing_bb_volume_trend_or_atr_is_rejected(self):
        self.assertFalse(fee_aware_entry(snap(evidences=("EV_TREND_BULLISH",)), hold_seconds=259200))
        self.assertFalse(fee_aware_entry(snap(evidences=("EV_BB_EXPANDING",)), hold_seconds=259200))
        self.assertFalse(fee_aware_entry(snap(atr="0.00001"), hold_seconds=259200))
        self.assertFalse(fee_aware_entry(snap(close="0"), hold_seconds=259200))

    def test_short_horizon_needs_more_per_bar_volatility(self):
        self.assertFalse(fee_aware_entry(snap(atr="0.001", interval=900), hold_seconds=900))

    def test_paper_minimums_are_not_one_btc(self):
        self.assertEqual(build_default_rules("USDTTMN").min_quantity, D("1.0"))
        btc = build_default_rules("BTCTMN")
        self.assertEqual(btc.min_quantity, D("0.0001"))
        self.assertEqual(btc.step_size, D("0.00001"))
        self.assertEqual(btc.base_asset, "BTC")


if __name__ == "__main__":
    unittest.main()
