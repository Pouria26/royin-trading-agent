"""Independent fee/lot counterexamples, including the actual PUMP fill economics."""

import unittest
from decimal import Decimal as D

from royin.risk import MarketRules, choose_lot_quantity_for_exit, project_exit_cash


class FeeRateResidualTests(unittest.TestCase):
    def setUp(self):
        self.rules = MarketRules(
            "PUMPTMN", "PUMP", "TMN", D(1), D(".1"), D(100000), D(".1"), D(".0025"), D(".003")
        )

    def project(self, quantity=D(130), **changes):
        return project_exit_cash(
            rules=self.rules,
            quantity=quantity,
            entry_price=D(1150),
            exit_price=D(1127),
            reserve_exit_base_fee=True,
            **changes,
        )

    def test_actual_maker_buy_taker_sell_rejects_old_130_quantity(self):
        cases = self.project()
        base_quote = next(
            c for c in cases if c["entry_fee_asset"] == "base" and c["exit_fee_asset"] == "quote"
        )
        # The old fixed-taker point predicted .41; the real maker fill left .475.
        self.assertEqual(D(base_quote["residual_base"]), D(".410"))
        actual_net = D(130) - D(".325")
        actual_sold = self.rules.quantize_quantity(actual_net / D("1.003"))
        self.assertEqual(actual_sold, D("129.2"))
        self.assertEqual((actual_net - actual_sold) * D(1150), D("546.25"))
        self.assertFalse(base_quote["residual_within_budget"])
        self.assertGreaterEqual(D(base_quote["residual_upper_bound_tmn"]), D("546.25"))

    def test_fee_interval_interior_can_be_worse_than_both_endpoints(self):
        # B immediately below 129.9888 jumps from 129.5 to 129.6 sellable PUMP.
        cases = self.project()
        case = next(
            c for c in cases if c["entry_fee_asset"] == "base" and c["exit_fee_asset"] == "quote"
        )
        self.assertEqual(D(case["residual_upper_bound_base"]), D(".4888"))
        self.assertEqual(D(case["residual_upper_bound_tmn"]), D("562.12"))
        fee = D(".000086154")
        net = D(130) * (1 - fee)
        sold = self.rules.quantize_quantity(net / D("1.003"))
        self.assertGreater(net - sold, D(".48879"))
        self.assertLessEqual(net - sold, D(case["residual_upper_bound_base"]))

    def test_fitted_pump_size_bounds_every_sampled_mixed_fee_and_fee_asset(self):
        chosen = choose_lot_quantity_for_exit(self.rules, D(130), D(1150), D(1127))
        self.assertEqual(chosen, D("111.9"))
        self.assertLessEqual(chosen * D(1150) * D("1.003"), D(150000))
        self.assertGreaterEqual(chosen * D(1150), D(100000))
        cases = self.project(quantity=chosen)
        self.assertTrue(all(c["sellable"] and c["residual_within_budget"] for c in cases))
        for index in range(1001):
            buy_fee = D(index) * D(".000003")
            for entry_asset in ("base", "quote"):
                net = chosen * (1 - buy_fee) if entry_asset == "base" else chosen
                sold = self.rules.quantize_quantity(net / D("1.003"))
                for exit_asset in ("base", "quote"):
                    case = next(
                        c
                        for c in cases
                        if c["entry_fee_asset"] == entry_asset and c["exit_fee_asset"] == exit_asset
                    )
                    for sell_fee in (D(0), D(".00071"), D(".0025"), D(".003")):
                        remainder = net - sold * (1 + sell_fee if exit_asset == "base" else 1)
                        self.assertGreaterEqual(remainder, 0)
                        self.assertLessEqual(remainder, D(case["residual_upper_bound_base"]))
                        self.assertLessEqual(remainder * D(1150), D(500))

    def test_fixed_base_amount_has_no_fictitious_rounding_jump(self):
        case = self.project()[0]  # Quote fee on BUY: acquired base is exactly 130.
        self.assertEqual(D(case["residual_upper_bound_base"]), D(".4"))
        self.assertEqual(D(case["residual_upper_bound_tmn"]), D(460))

    def test_zero_fee_and_exact_step_boundary_have_zero_residual(self):
        rules = MarketRules("XTMN", "X", "TMN", D(1), D(".1"), D(1), D(".1"), D(0), D(0))
        cases = project_exit_cash(
            rules=rules,
            quantity=D(130),
            entry_price=D(1150),
            exit_price=D(1127),
            reserve_exit_base_fee=True,
        )
        self.assertTrue(all(D(c["residual_upper_bound_base"]) == 0 for c in cases))

    def test_endpoint_jump_is_a_supremum_and_not_rounded_down(self):
        # q=1.003 lies exactly at the jump; fee=0 is not its maximum residual.
        rules = MarketRules("XTMN", "X", "TMN", D(1), D(".1"), D(1), D(".1"), D(".0025"), D(".003"))
        cases = project_exit_cash(
            rules=rules,
            quantity=D("1.003"),
            entry_price=D(1000),
            exit_price=D(1000),
            reserve_exit_base_fee=True,
        )
        case = next(c for c in cases if c["entry_fee_asset"] == "base")
        self.assertEqual(D(case["residual_upper_bound_base"]), D(".103"))

    def test_maker_above_reserve_ceiling_fails_closed(self):
        from dataclasses import replace

        with self.assertRaisesRegex(ValueError, "maker.*taker|fee.*ceiling"):
            project_exit_cash(
                rules=replace(self.rules, maker_fee_rate=D(".004")),
                quantity=D(130),
                entry_price=D(1150),
                exit_price=D(1127),
                reserve_exit_base_fee=True,
            )

    def test_cash_bounds_cover_mixed_fee_assets_without_charging_both_fees_in_full(self):
        cases = project_exit_cash(
            rules=self.rules,
            quantity=D(130),
            entry_price=D(1150),
            exit_price=D(1158),
            reserve_exit_base_fee=True,
        )
        lower = D(cases[0]["net_lower_bound_tmn"])
        ratio = D(cases[0]["cash_debit_proceeds_ratio_upper"])
        for index in range(1001):
            base_fee = D(130) * D(".003") * D(index) / D(1000)
            quote_fee = (D(130) * D(".003") - base_fee) * D(1150)
            acquired = D(130) - base_fee
            sold = self.rules.quantize_quantity(acquired / D("1.003"))
            debit = D(130) * D(1150) + quote_fee
            proceeds = sold * D(1158) * D(".997")
            self.assertLessEqual(lower, proceeds - debit)
            self.assertGreaterEqual(ratio, debit / proceeds)
        # A hypothetical full base fee AND full quote fee would overstate costs.
        impossible_debit = D(130) * D(1150) * D("1.003")
        impossible_proceeds = D("129.2") * D(1158) * D(".997")
        self.assertGreater(lower, impossible_proceeds - impossible_debit)


if __name__ == "__main__":
    unittest.main()
