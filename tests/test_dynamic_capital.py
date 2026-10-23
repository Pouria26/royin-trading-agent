"""Host sizing changes with observed risk; model confidence is never a probability input."""

import unittest
from decimal import Decimal as D

from royin.risk import allocate_entry_capital


class DynamicCapitalTests(unittest.TestCase):
    def plan(self, **changes):
        params = dict(equity_tmn=D(5000000), free_cash_tmn=D(4000000),
            price_tmn=D(100), atr_tmn=D(".5"), depth_tmn=D(100000000), fee_rate=D(".003"),
            tick_size=D(".01"), bootstrap=False, risk_scale=D(1))
        return allocate_entry_capital(**(params | changes))

    def test_bootstrap_is_bounded_then_volatility_changes_the_debit(self):
        first = self.plan(bootstrap=True)
        calm = self.plan()
        volatile = self.plan(atr_tmn=D(2))
        self.assertEqual(D(first["debit_limit_tmn"]), D(150000))
        self.assertGreater(D(calm["debit_limit_tmn"]), D(150000))
        self.assertLess(D(volatile["debit_limit_tmn"]), D(calm["debit_limit_tmn"]))
        for plan in (first, calm, volatile):
            self.assertTrue(plan["approved"])
            self.assertLessEqual(D(plan["debit_limit_tmn"]), D(2500000))
            self.assertLessEqual(D(plan["debit_limit_tmn"]) * D(plan["loss_fraction"]), D(plan["risk_budget_tmn"]))

    def test_liquidity_free_cash_and_reduced_risk_are_real_constraints(self):
        self.assertLess(D(self.plan(risk_scale=D(".5"))["debit_limit_tmn"]), D(self.plan()["debit_limit_tmn"]))
        self.assertFalse(self.plan(depth_tmn=D(1000000))["approved"])
        self.assertFalse(self.plan(free_cash_tmn=D(100000))["approved"])
        self.assertFalse(self.plan(atr_tmn=D(5))["approved"])

    def test_non_decimal_nan_and_negative_inputs_are_rejected(self):
        for value in (1.0, D("NaN"), D("Infinity"), D(-1)):
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError)):
                self.plan(atr_tmn=value)

    def test_reduced_risk_does_not_halve_a_nonbinding_bootstrap_cap(self):
        # Synthetic counterexample: the first-trip cap binds before the loss budget.
        normal = self.plan(bootstrap=True, risk_scale=D(1))
        reduced = self.plan(bootstrap=True, risk_scale=D(".5"))
        self.assertTrue(normal["approved"] and reduced["approved"])
        self.assertEqual(D(normal["debit_limit_tmn"]), D(150000))
        self.assertEqual(D(reduced["debit_limit_tmn"]), D(150000))
        self.assertEqual(D(reduced["risk_budget_tmn"]), D(normal["risk_budget_tmn"]) / 2)
        self.assertLess(D(reduced["debit_limit_tmn"]) * D(reduced["loss_fraction"]),
                        D(reduced["risk_budget_tmn"]))


if __name__ == "__main__":
    unittest.main()
