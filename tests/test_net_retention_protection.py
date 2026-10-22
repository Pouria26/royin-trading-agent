"""Independent hand-calculated oracles for net-profit retention trailing protection.

Verifies the mathematical cost-model equations, tick-size ceiling preservation,
and long-position non-decreasing stop invariants from user prompt specifications.
"""

import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path

from royin.broker import PaperBroker
from royin.ledger import Ledger
from royin.risk import (
    MarketRules,
    PositionProtectionPolicy,
    RiskResult,
    calculate_retention_stop_price,
)


def rules(tick_size=D(".01"), taker_fee=D(".003")):
    return MarketRules(
        "USDTTMN", "USDT", "TMN", tick_size, D(".01"), D(1), D(".01"), D(".003"), taker_fee
    )


def retention_policy(
    retention_ratio=D(".5"),
    activation_fraction=D(".015"),
    deadline=2000,
):
    return PositionProtectionPolicy(
        initial_stop_pct=D(".02"),
        trailing_drawdown_pct=D(".01"),
        checkpoint_profit_pct=D(".025"),
        review_interval_seconds=30,
        hard_holding_seconds=300,
        deadline_utc=deadline,
        exit_buffer_seconds=10,
        max_quote_age_seconds=5,
        max_loss_tmn=D(50),
        profit_retention_ratio=retention_ratio,
        net_activation_fraction=activation_fraction,
    )


class NetRetentionProtectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "retention_paper.sqlite3"
        self.ledger = Ledger(self.path)
        self.ledger.initialize_portfolio(D(1000), quote_asset="TMN", binding="a" * 64)
        self.broker = PaperBroker(self.ledger, rules())

    def enter_position(self, price=D(100), qty=D(1)):
        fee_est = qty * price * D(".003")
        risk = RiskResult(True, "synthetic ENTER", "ENTER", "USDTTMN", qty, price, price * D(".98"), fee_est)
        self.broker.submit_order(risk, client_id="entry_order", timestamp=1000)
        self.broker.reconcile_order("entry_order", simulated_state="FILLED", timestamp=1001)
        # Cost basis C = qty * price + entry_fee = 100 + 0.3 = 100.3
        self.broker.arm_protection(retention_policy(), opened_at=1001, entry_price=price)

    def test_hand_calculated_cost_oracle_from_prompt(self):
        """Verify the exact numerical example from prompt:

        Buy 1 @ 100, entry fee 0.003, exit fee 0.003, zero slippage.
        Cost basis C = 100.3.
        Exit at 101.5: net profit = 101.5 * 0.997 - 100.3 = 0.8955, NOT 1.5.
        Net return 1.5% on C: threshold price = C * 1.015 / 0.997 = 101.8045 / 0.997 = 102.1108325...
        At bid 103: cash = 103 * 0.997 = 102.691.
        Net peak = 102.691 - 100.3 = 2.391.
        Half retention floor F = 2.391 * 0.5 = 1.1955.
        Raw stop price = (100.3 + 1.1955) / 0.997 = 101.4955 / 0.997 = 101.8009027...
        Ceiling to tick 0.01: 101.81.
        """
        # 1. Direct formula oracle check
        c_basis = D("100.3")
        f_net = c_basis * D(".015")  # 1.5045
        threshold_price = (c_basis + f_net) / D(".997")
        self.assertAlmostEqual(float(threshold_price), 102.110832497, places=6)

        # 2. Formula at bid 103: net peak = 2.391, floor = 1.1955
        desired_floor = D("2.391") * D(".5")
        calc_stop = calculate_retention_stop_price(
            cost_basis=c_basis,
            sellable_quantity=D(1),
            desired_net_profit=desired_floor,
            taker_fee_rate=D(".003"),
            slippage_pct=D(0),
            tick_size=D(".01"),
        )
        self.assertEqual(calc_stop, D("101.81"))
        # Verify that selling at 101.81 guarantees at least desired_floor:
        net_cash_at_stop = D("101.81") * D(".997")
        net_profit_at_stop = net_cash_at_stop - c_basis
        self.assertGreaterEqual(net_profit_at_stop, desired_floor)

    def test_broker_observes_bid_activates_retention_and_tightens_stop(self):
        self.enter_position(price=D(100), qty=D(1))
        pol = retention_policy(retention_ratio=D(".5"), activation_fraction=D(".015"))

        # At bid 101: net profit = 1 * 101 * (1 - .0005) * .997 - 100.3 = 100.6466515 - 100.3 = 0.3466515
        # 0.34665 / 100.3 = 0.345% < 1.5% activation -> retention not yet active
        tick1 = self.broker.observe_quote(D(101), source_time=1010, received_at=1010, now=1010, policy=pol)
        self.assertEqual(tick1["action"], "WAIT")
        self.assertFalse(tick1["retention_active"])
        self.assertEqual(tick1["trailing_stop_price"], "99.99")  # 101 * (1 - .01) = 99.99

        # At bid 103: net profit = 1 * 103 * (1 - .0005) * .997 - 100.3 = 2.3395 > 1.5% of C
        # Retention activates! Net peak ~ 2.3395, retained floor = 2.3395 * .5 = 1.16975
        tick2 = self.broker.observe_quote(D(103), source_time=1020, received_at=1020, now=1020, policy=pol)
        self.assertEqual(tick2["action"], "WAIT")
        self.assertTrue(tick2["retention_active"])
        stop2 = D(tick2["trailing_stop_price"])
        self.assertGreater(stop2, D("101.00"))  # tightened well above price-only trailing stop

        # Export state reflects full retention data
        state = self.broker.export_state(D(103), now=1020)
        self.assertTrue(state["retention_active"])
        self.assertIsNotNone(state["retained_floor_tmn"])
        self.assertEqual(state["last_tightened_at"], 1020)

    def test_long_rule_invariants_stop_and_floor_never_decrease(self):
        self.enter_position(price=D(100), qty=D(1))
        pol = retention_policy(retention_ratio=D(".5"), activation_fraction=D(".015"))

        # Peak at 104
        t1 = self.broker.observe_quote(D(104), source_time=1010, received_at=1010, now=1010, policy=pol)
        stop_peak = D(t1["trailing_stop_price"])
        floor_peak = D(t1["retained_floor_tmn"])

        # Price drops to 103.5
        t2 = self.broker.observe_quote(D("103.5"), source_time=1020, received_at=1020, now=1020, policy=pol)
        self.assertEqual(t2["action"], "WAIT")
        self.assertEqual(D(t2["trailing_stop_price"]), stop_peak)
        self.assertEqual(D(t2["retained_floor_tmn"]), floor_peak)
        self.assertGreaterEqual(D(t2["trailing_stop_price"]), stop_peak)

    def test_protection_breach_triggers_immediate_exit_without_downward_clamp(self):
        self.enter_position(price=D(100), qty=D(1))
        pol = retention_policy(retention_ratio=D(".5"), activation_fraction=D(".015"))

        # Peak at 105 -> stop is tightened high
        t1 = self.broker.observe_quote(D(105), source_time=1010, received_at=1010, now=1010, policy=pol)
        stop1 = D(t1["trailing_stop_price"])
        self.assertGreater(stop1, D(98))

        # Price drops below the tightened stop to 102 -> breach triggers EXIT
        t2 = self.broker.observe_quote(D(102), source_time=1020, received_at=1020, now=1020, policy=pol)
        self.assertEqual(t2["action"], "EXIT")
        self.assertEqual(t2["exit_reason"], "STOP_OR_TRAILING")
        self.assertEqual(self.ledger.get_balance("USDT").total, D(0))
        self.assertGreater(self.ledger.get_balance("TMN").free, D(1000))  # Net profit preserved

    def test_restart_preserves_retention_state_and_stop(self):
        self.enter_position(price=D(100), qty=D(1))
        pol = retention_policy(retention_ratio=D(".5"), activation_fraction=D(".015"))

        t1 = self.broker.observe_quote(D(104), source_time=1010, received_at=1010, now=1010, policy=pol)
        expected_stop = t1["trailing_stop_price"]
        expected_floor = t1["retained_floor_tmn"]

        # Simulate process restart by reloading Ledger and PaperBroker from disk
        restarted_ledger = Ledger(self.path)
        restarted_broker = PaperBroker(restarted_ledger, rules())
        recovered_state = restarted_broker.arm_protection(pol, opened_at=1001, entry_price=D(100))

        self.assertEqual(recovered_state["trailing_stop_price"], expected_stop)
        self.assertEqual(recovered_state["retained_floor_tmn"], expected_floor)
        self.assertTrue(recovered_state["retention_active"])
        self.assertEqual(recovered_state["high_water"], "104")


if __name__ == "__main__":
    unittest.main()
