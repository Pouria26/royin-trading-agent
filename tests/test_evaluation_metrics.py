import unittest
from decimal import Decimal

from royin.evaluation import (
    always_wait_decision,
    buy_and_hold_decision,
    conviction_fee_aware_decision,
    evaluate_strategy_suite,
    format_scorecard_markdown,
)
from royin.features import FeatureSnapshot
from royin.market_data import Candle
from royin.risk import MarketRules, RiskPolicy


def _make_mock_snapshot(symbol="USDTTMN", spread_pct=Decimal("0.01"), atr=Decimal("600")):
    return FeatureSnapshot(
        symbol=symbol,
        cutoff=1700000900,
        interval_seconds=900,
        closed_bars_count=35,
        last_close=Decimal("60000"),
        trend_sma_fast=Decimal("60600"),
        trend_sma_slow=Decimal("60000"),
        rsi_14=Decimal("55"),
        atr_14=atr,
        volume_ratio=Decimal("1.2"),
        current_position_base=Decimal(0),
        available_tmn_cash=Decimal("5000000"),
        evidences={
            "EV_DATA_FRESH": "Candle closed at 1700000900",
            "EV_TREND_BULLISH": "Price above SMA",
            "EV_POSITION_FLAT": "No position",
        },
        snapshot_sha256="d" * 64,
    )


class EvaluationMetricsTests(unittest.TestCase):
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
        self.candles = [
            Candle(
                open_time=1700000000 + i * 900,
                open=Decimal("60000") + Decimal(i * 40),
                high=Decimal("60100") + Decimal(i * 40),
                low=Decimal("59900") + Decimal(i * 40),
                close=Decimal("60050") + Decimal(i * 40),
                volume=Decimal("100"),
            )
            for i in range(40)
        ]

    def test_always_wait_decision_is_strictly_wait(self):
        snap = _make_mock_snapshot()
        dec = always_wait_decision(snap)
        self.assertEqual(dec.action, "WAIT")
        self.assertEqual(dec.symbol, "USDTTMN")

    def test_buy_and_hold_enters_when_flat_then_waits(self):
        snap_flat = _make_mock_snapshot()
        dec_enter = buy_and_hold_decision(snap_flat)
        self.assertEqual(dec_enter.action, "ENTER")

        snap_long = FeatureSnapshot(
            symbol="USDTTMN",
            cutoff=1700001800,
            interval_seconds=900,
            closed_bars_count=36,
            last_close=Decimal("60050"),
            trend_sma_fast=Decimal("60650"),
            trend_sma_slow=Decimal("60050"),
            rsi_14=Decimal("56"),
            atr_14=Decimal("600"),
            volume_ratio=Decimal("1.2"),
            current_position_base=Decimal("25.0"),
            available_tmn_cash=Decimal("3500000"),
            evidences={"EV_DATA_FRESH": "fresh", "EV_POSITION_LONG": "long"},
            snapshot_sha256="e" * 64,
        )
        dec_wait = buy_and_hold_decision(snap_long)
        self.assertEqual(dec_wait.action, "WAIT")

    def test_conviction_fee_aware_decision_requires_hurdle(self):
        # Snap with high spread and high ATR -> enters
        snap_high_hurdle = _make_mock_snapshot(spread_pct=Decimal("0.01"), atr=Decimal("600"))
        dec = conviction_fee_aware_decision(snap_high_hurdle)
        self.assertEqual(dec.action, "ENTER")

        # Snap with low ATR (insufficient profit potential to clear fee) -> waits
        snap_low_atr = _make_mock_snapshot(spread_pct=Decimal("0.01"), atr=Decimal("50"))
        dec_low = conviction_fee_aware_decision(snap_low_atr)
        self.assertEqual(dec_low.action, "WAIT")

    def test_evaluate_strategy_suite_runs_all_four_baselines(self):
        suite = evaluate_strategy_suite(self.candles, self.rules, self.policy)
        self.assertIn("1_Cash_Baseline", suite)
        self.assertIn("2_Buy_and_Hold", suite)
        self.assertIn("3_Naive_Crossover", suite)
        self.assertIn("4_Fee_Aware_Conviction", suite)

        # Cash baseline must have 0 trades and 0 fees
        self.assertEqual(suite["1_Cash_Baseline"]["closed_round_trips"], 0)
        self.assertEqual(suite["1_Cash_Baseline"]["total_fees_paid_tmn"], "0")

        # Format markdown must contain all 4 strategies
        md = format_scorecard_markdown(suite)
        self.assertIn("1_Cash_Baseline", md)
        self.assertIn("2_Buy_and_Hold", md)
        self.assertIn("3_Naive_Crossover", md)
        self.assertIn("4_Fee_Aware_Conviction", md)


if __name__ == "__main__":
    unittest.main()
