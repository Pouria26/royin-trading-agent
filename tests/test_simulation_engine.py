import unittest
from decimal import Decimal

from royin.decision import Decision
from royin.evaluation import baseline_rule_decision, run_simulation
from royin.market_data import Candle
from royin.risk import MarketRules, RiskPolicy


class SimulationEngineTests(unittest.TestCase):
    def setUp(self):
        self.rules = MarketRules(
            symbol="USDTTMN",
            base_asset="USDT",
            quote_asset="TMN",
            tick_size=Decimal("1"),
            step_size=Decimal("0.01"),
            min_notional=Decimal("100000"),
            min_quantity=Decimal("1.0"),
            maker_fee_rate=Decimal("0.0025"),
            taker_fee_rate=Decimal("0.0030"),
        )
        self.policy = RiskPolicy(
            max_order_tmn=Decimal("1500000"),
            max_exposure_tmn=Decimal("3000000"),
            stop_loss_pct=Decimal("0.02"),
            max_drawdown_pct=Decimal("0.05"),
            deadline_utc=1700100000,
        )
        # Create 40 candles (interval 900s)
        self.candles = [
            Candle(
                open_time=1700000000 + i * 900,
                open=Decimal("60000") + Decimal(i * 50),
                high=Decimal("60100") + Decimal(i * 50),
                low=Decimal("59900") + Decimal(i * 50),
                close=Decimal("60050") + Decimal(i * 50),
                volume=Decimal("100"),
            )
            for i in range(40)
        ]

    def test_cash_baseline_always_wait_preserves_capital_without_trades(self):
        def always_wait(snap):
            return Decision(
                decision_id=f"wait_{snap.cutoff}",
                symbol=snap.symbol,
                action="WAIT",
                cutoff=snap.cutoff,
                snapshot_sha256=snap.snapshot_sha256,
                evidence_ids=("EV_DATA_FRESH",),
                reason="Always wait cash baseline",
                invalidation="None",
            )

        res = run_simulation(
            self.candles,
            always_wait,
            self.rules,
            self.policy,
            initial_capital=Decimal("5000000"),
        )
        self.assertEqual(res["final_cash_tmn"], "5000000")
        self.assertEqual(res["total_realized_pnl"], "0")
        self.assertEqual(res["orders_submitted"], 0)
        self.assertEqual(res["fills_count"], 0)

    def test_rule_baseline_simulation_runs_to_completion(self):
        def rule_prod(snap):
            return baseline_rule_decision(snap, decision_id=f"base_{snap.cutoff}")

        res = run_simulation(
            self.candles,
            rule_prod,
            self.rules,
            self.policy,
            initial_capital=Decimal("5000000"),
        )
        self.assertEqual(res["symbol"], "USDTTMN")
        self.assertEqual(res["initial_capital_tmn"], "5000000")
        self.assertIn("final_cash_tmn", res)
        self.assertIn("net_return_pct", res)


if __name__ == "__main__":
    unittest.main()
