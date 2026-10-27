"""Downward quantity fitting fixes coarse-lot residuals without raising any cap."""

import unittest
from dataclasses import replace
from decimal import Decimal as D
from types import SimpleNamespace
from unittest.mock import patch

from royin.decision import ResearchExecutionCapacity
from royin.risk import (
    MarketRules,
    choose_lot_quantity_for_exit,
    entry_cost_context,
    project_exit_cash,
)


class LotSizingTests(unittest.TestCase):
    def setUp(self):
        # Fixed public market-price counterexample. No runtime capture is required.
        self.rules = MarketRules("BTCTMN", "BTC", "TMN", D(1), D("1e-8"), D(100000),
                                 D("1e-8"), D(".0025"), D(".003"))
        self.entry = D("21528509382")
        self.exit = D("21474546844")
        self.ceiling = D(".00000694")

    def fit(self, **changes):
        args = dict(rules=self.rules, quantity_ceiling=self.ceiling, entry_price=self.entry,
                    exit_price=self.exit, reserve_exit_base_fee=True)
        args.update(changes)
        return choose_lot_quantity_for_exit(**args)

    def test_old_668_point_pass_does_not_prove_mixed_fee_residual_capacity(self):
        rejected = project_exit_cash(rules=self.rules, quantity=self.ceiling, entry_price=self.entry,
                                     exit_price=self.exit, reserve_exit_base_fee=True)
        self.assertEqual(D(rejected[0]["residual_mark_tmn"]), D("645.85528146"))
        self.assertFalse(rejected[0]["residual_within_budget"])
        self.assertIsNone(self.fit())
        # Quote-entry/quote-exit: floor(668 / 1.003)=666 lots, retaining exactly two.
        cases = project_exit_cash(rules=self.rules, quantity=D(".00000668"), entry_price=self.entry,
                                  exit_price=self.exit, reserve_exit_base_fee=True)
        self.assertEqual(D(cases[0]["sellable_quantity"]), D(".00000666"))
        self.assertEqual(D(cases[0]["residual_mark_tmn"]), D("430.57018764"))
        self.assertEqual(len(cases), 4)
        self.assertFalse(all(case["residual_within_budget"] for case in cases))
        self.assertEqual(D(cases[2]["residual_upper_bound_base"]), D(".00000002998"))
        self.assertGreater(D(cases[2]["residual_upper_bound_tmn"]), D(500))

    def test_first_passing_size_is_deterministic_and_bound_is_explicit(self):
        # 26 attempts examine 694..669; old attempt 27 was not a valid fee envelope.
        with patch("royin.risk.project_exit_cash", wraps=project_exit_cash) as evaluate:
            self.assertIsNone(self.fit(max_attempts=26))
            self.assertEqual(evaluate.call_count, 26)
        self.assertIsNone(self.fit(max_attempts=27))
        self.assertEqual(self.fit(), self.fit())

    def test_coarse_sol_has_no_fit_above_100k_in_this_bound(self):
        rules = MarketRules("SOLTMN", "SOL", "TMN", D(1), D(".00001"), D(100000),
                            D(".00001"), D(".0025"), D(".003"))
        self.assertIsNone(self.fit(rules=rules, quantity_ceiling=D(".00552"),
                                  entry_price=D("27069067"), exit_price=D("27015719")))

    def test_minimum_notional_quantity_and_zero_ceiling_cannot_be_bypassed(self):
        self.assertIsNone(self.fit(quantity_ceiling=D(0)))
        self.assertIsNone(self.fit(quantity_ceiling=D(".000001")))
        self.assertIsNone(self.fit(rules=replace(self.rules, min_quantity=D(".000007"))))
        self.assertIsNone(self.fit(exit_price=D(0)))

    def test_bad_decimal_bound_or_attempt_limit_is_rejected(self):
        for changes in ({"quantity_ceiling": D("NaN")}, {"quantity_ceiling": D("Infinity")},
                        {"quantity_ceiling": D(-1)}, {"quantity_ceiling": 0.1},
                        {"entry_price": D(0)}, {"exit_price": D("NaN")},
                        {"max_attempts": 257}, {"max_attempts": 0}, {"max_attempts": True},
                        {"reserve_exit_base_fee": 1}):
            with self.subTest(changes=changes), self.assertRaises((ValueError, TypeError)):
                self.fit(**changes)

    def test_unstepped_ceiling_is_rounded_down_and_never_increased(self):
        # A fine synthetic step isolates ceiling rounding from actual BTC's no-fit.
        rules = replace(self.rules, step_size=D("1e-9"), min_quantity=D("1e-9"))
        ceiling = D(".00000668001")
        chosen = self.fit(rules=rules, quantity_ceiling=ceiling)
        self.assertEqual(chosen, D(".000006680"))
        self.assertLess(chosen, ceiling)

    def test_incomplete_search_does_not_exceed_256_scenario_evaluations(self):
        failed_cases = [{"sellable": True, "residual_within_budget": False}] * 4
        with patch("royin.risk.project_exit_cash", return_value=failed_cases) as evaluate:
            self.assertIsNone(self.fit(quantity_ceiling=D(".00001")))
            self.assertEqual(evaluate.call_count, 256)

    def test_research_preview_exposes_no_fit_instead_of_the_old_false_capacity(self):
        capacity = ResearchExecutionCapacity(debit_ceiling_tmn=D(150000), tick_size=D(1),
            step_size=D("1e-8"), min_notional=D(100000), min_quantity=D("1e-8"),
            maker_fee_rate=D(".0025"), taker_fee_rate=D(".003"), reserve_exit_base_fee=True)
        snapshot = SimpleNamespace(symbol="BTCTMN", last_close=D("21469288285"))
        opportunity = SimpleNamespace(best_bid=D("21485289489"), best_ask=D("21517750507"),
                                      round_trip_fee_pct=D(".006"), execution_capacity=capacity)
        view = entry_cost_context(snapshot, opportunity)["capacity"]
        self.assertEqual(view["status"], "BLOCKED_MINIMUM_OR_RESIDUAL")
        self.assertEqual(D(view["requested_quantity_ceiling"]), self.ceiling)
        self.assertEqual(D(view["entry_quantity"]), 0)
        self.assertIsNone(view["lot_fit"]["decrements"])
        self.assertEqual(view["lot_fit"]["scenarios_basis"], "REQUESTED_CEILING_DIAGNOSTIC_ONLY")
        self.assertFalse(all(s["residual_within_budget"] for s in view["scenarios"]))

    def test_failed_preview_retains_diagnostic_ceiling_without_suggesting_an_order(self):
        capacity = ResearchExecutionCapacity(debit_ceiling_tmn=D(100000), tick_size=D(1),
            step_size=D(".00001"), min_notional=D(100000), min_quantity=D(".00001"),
            maker_fee_rate=D(".0025"), taker_fee_rate=D(".003"), reserve_exit_base_fee=True)
        snapshot = SimpleNamespace(symbol="SOLTMN", last_close=D("27012986"))
        opportunity = SimpleNamespace(best_bid=D("27029234"), best_ask=D("27055539"),
                                      round_trip_fee_pct=D(".006"), execution_capacity=capacity)
        view = entry_cost_context(snapshot, opportunity)["capacity"]
        self.assertEqual(view["status"], "BLOCKED_MINIMUM_OR_RESIDUAL")
        self.assertEqual(D(view["entry_quantity"]), D(0))
        self.assertGreater(D(view["requested_quantity_ceiling"]), 0)
        self.assertEqual(view["lot_fit"]["status"], "INCOMPLETE_OR_NO_FIT_ABOVE_MINIMUM")
        self.assertEqual(view["lot_fit"]["scenarios_basis"], "REQUESTED_CEILING_DIAGNOSTIC_ONLY")


if __name__ == "__main__":
    unittest.main()
