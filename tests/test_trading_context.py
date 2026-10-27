"""Hand-calculated setup and cost observations; no model or profitability claim."""

import json
import unittest
from dataclasses import replace
from decimal import Decimal as D

from royin.agent import _entry_rows
from royin.decision import EntryOpportunityContext, ResearchExecutionCapacity
from royin.features import closed_bar_structure, extract_features
from royin.market_data import Candle, CandleSeries
from royin.risk import MarketRules, entry_cost_context, project_exit_cash
from tests.test_market_selection import opportunity, snapshot


def bars(closes):
    return tuple(Candle(300+i*300, D(c), D(c)+1, D(c)-1, D(c), D(10))
                 for i, c in enumerate(closes))


class TradingContextTests(unittest.TestCase):
    def test_trigger_high_is_excluded_and_breakout_can_be_observed(self):
        candles = bars([100]*20+[103])
        structure = closed_bar_structure(candles, 300)
        self.assertEqual(structure["prior_high"], "101")
        self.assertEqual(structure["prior_low"], "99")
        self.assertTrue(structure["last_close_above_prior_high"])
        self.assertEqual(D(structure["returns_by_seconds"]["3600"]), D(".03"))
        self.assertEqual(D(structure["path_efficiency_20"]), D(1))
        self.assertEqual(D(structure["relative_volume_prior_20"]), D(1))

    def test_large_trigger_volume_is_not_in_its_own_baseline(self):
        candles = bars([100]*21)
        candles = (*candles[:-1], replace(candles[-1], volume=D(40)))
        self.assertEqual(D(closed_bar_structure(candles, 300)["relative_volume_prior_20"]), D(4))

    def test_flat_path_zero_volume_and_nonexistent_timeframes_are_explicit(self):
        candles = tuple(replace(c, volume=D(0)) for c in bars([100]*21))
        structure = closed_bar_structure(candles, 900)
        self.assertEqual(D(structure["path_efficiency_20"]), D(0))
        self.assertIsNone(structure["relative_volume_prior_20"])
        self.assertNotIn("300", structure["returns_by_seconds"])
        self.assertFalse(structure["last_close_above_prior_high"])
        self.assertFalse(structure["prior_low_reclaim"])

    def test_whipsaw_has_low_efficiency_and_support_reclaim_is_observed(self):
        candles = bars([100, 101]*10+[100])
        structure = closed_bar_structure(candles, 300)
        self.assertEqual(D(structure["path_efficiency_20"]), D(0))
        reclaimed = (*candles[:-1], replace(candles[-1], low=D(98)))
        self.assertTrue(closed_bar_structure(reclaimed, 300)["prior_low_reclaim"])

    def test_future_bars_do_not_change_structure_or_snapshot_hash(self):
        candles = bars([100]*30+[103])
        cutoff = candles[-1].open_time+300
        first = extract_features(CandleSeries(candles, 300), "BTCTMN", cutoff=cutoff)
        future = Candle(cutoff, D(999), D(1000), D(998), D(999), D(200))
        extended = extract_features(CandleSeries((*candles, future), 300), "BTCTMN", cutoff=cutoff)
        self.assertEqual(first.snapshot_sha256, extended.snapshot_sha256)
        self.assertEqual(json.loads(first.evidences["EV_CLOSED_BAR_STRUCTURE"])["prior_high"], "101")
        self.assertTrue(first.verify_hash())

    def test_unchanged_book_requires_more_than_the_sum_of_fees(self):
        snap = replace(snapshot("BTCTMN"), last_close=D(100))
        opp = opportunity().model_copy(update=dict(best_bid=D(100), best_ask=D(100)))
        cost = entry_cost_context(snap, opp, slippage_pct=D(0))
        # Buy one unit for100.3; selling it at100.3/.997 repays the debit.
        hurdle = D(cost["break_even_reference_return_fraction"])
        self.assertLess(abs(hurdle-D(".006018054162487462387161484")), D("1e-27"))
        self.assertGreater(hurdle, D(".006"))
        self.assertEqual(cost["status"], "ESTIMATE_NOT_ADMISSION")

    def test_ask_gap_and_spread_make_a_small_target_uneconomic(self):
        snap = replace(snapshot("BTCTMN"), last_close=D(100))
        opp = opportunity().model_copy(update=dict(best_bid=D(102), best_ask=D(103)))
        cost = entry_cost_context(snap, opp)
        self.assertGreater(D(cost["break_even_reference_return_fraction"]), D(".04"))
        self.assertEqual(D(cost["ask_return_from_reference"]), D(".03"))
        row = _entry_rows({snap.symbol: (snap, opp)})[0]
        self.assertEqual(row["execution_cost_context"], cost)

    def test_missing_quotes_never_become_a_zero_hurdle_and_crossed_quotes_fail(self):
        snap, opp = snapshot("BTCTMN"), opportunity()
        self.assertEqual(entry_cost_context(snap, opp)["status"], "UNAVAILABLE_MISSING_QUOTES")
        with self.assertRaises(ValueError):
            entry_cost_context(snap, opp.model_copy(update=dict(best_bid=D(101), best_ask=D(100))))
        with self.assertRaises(ValueError):
            entry_cost_context(snap, opp, slippage_pct=D("NaN"))

    def test_capacity_exposes_coarse_lot_losses_before_model_decides(self):
        cap = ResearchExecutionCapacity(debit_ceiling_tmn=D(150000),tick_size=D(1),step_size=D(".0001"),
            min_notional=D(100000),min_quantity=D(".0001"),maker_fee_rate=D(".0025"),
            taker_fee_rate=D(".003"),reserve_exit_base_fee=True)
        snap = replace(snapshot("USOONTMN"),last_close=D(45000000))
        opp = opportunity().model_copy(update=dict(best_bid=D(45000000),best_ask=D(45000000),execution_capacity=cap))
        capacity = entry_cost_context(snap,opp)["capacity"]
        self.assertEqual(capacity["status"],"BLOCKED_MINIMUM_OR_RESIDUAL")
        self.assertGreater(D(capacity["worst_residual_mark_tmn"]),D(500))
        self.assertLessEqual(D(capacity["entry_quantity"])*D(45022500)*D("1.003"),D(150000))
        # Changing only observed lot precision can make the same debit executable.
        fine = opp.model_copy(update=dict(execution_capacity=cap.model_copy(update=dict(step_size=D(".00000001"),min_quantity=D(".00000001")))))
        self.assertEqual(entry_cost_context(snap,fine)["capacity"]["status"],"SELLABLE_WITH_BOUNDED_RESIDUAL")

    def test_fee_reserve_scenarios_include_unsold_cost_and_never_overdraw_base(self):
        rules = MarketRules("ETHTMN","ETH","TMN",D(1),D(".01"),D(100000),D(".01"),D(".0025"),D(".003"))
        cases = project_exit_cash(rules=rules,quantity=D(1400),entry_price=D(100),exit_price=D(105),reserve_exit_base_fee=True)
        quote = next(c for c in cases if c["entry_fee_asset"] == c["exit_fee_asset"] == "quote")
        self.assertEqual(D(quote["sellable_quantity"]),D("1395.81"))
        self.assertEqual(D(quote["residual_base"]),D("4.19"))
        self.assertEqual(D(quote["proceeds_tmn"]),D("146120.36985"))
        self.assertEqual(D(quote["net_at_target_tmn"]),D("5700.36985"))
        self.assertTrue(all(D(c["residual_base"]) >= 0 for c in cases))

    def test_legacy_opportunity_hash_survives_new_optional_capacity_field(self):
        opp = opportunity()
        legacy_json = opp.model_dump_json(exclude={"execution_capacity"})
        restored = EntryOpportunityContext.model_validate_json(legacy_json)
        import hashlib
        self.assertEqual(restored.sha256,hashlib.sha256(legacy_json.encode()).hexdigest())


if __name__ == "__main__":
    unittest.main()
