import unittest
from decimal import Decimal

from royin.features import (
    compute_atr,
    compute_rsi,
    compute_sma,
    extract_features,
)
from royin.market_data import Candle, CandleSeries


class FeatureExtractionTests(unittest.TestCase):
    def setUp(self):
        # Create 50 synthetic 15-minute candles (step = 900)
        self.step = 900
        self.start = 1790812800
        candles = []
        base_price = Decimal("60000")
        for i in range(50):
            t = self.start + i * self.step
            # slight trend upward
            price = base_price + Decimal(i * 50)
            candles.append(Candle(
                open_time=t,
                open=price,
                high=price + Decimal(30),
                low=price - Decimal(20),
                close=price + Decimal(10),
                volume=Decimal("10.5"),
            ))
        self.series = CandleSeries(tuple(candles), self.step)

    def test_prefix_invariance(self):
        """Adding future candles must NOT alter features or snapshot hash for an earlier cutoff."""
        cutoff = self.start + 35 * self.step  # Cutoff at 35 candles

        snap_initial = extract_features(self.series, "USDTTMN", cutoff=cutoff)

        # Create an extended series with 20 additional future candles
        extended_candles = list(self.series.candles)
        last_t = extended_candles[-1].open_time
        for i in range(1, 21):
            t = last_t + i * self.step
            extended_candles.append(Candle(
                open_time=t,
                open=Decimal("65000"),
                high=Decimal("66000"),
                low=Decimal("64000"),
                close=Decimal("65500"),
                volume=Decimal("100"),
            ))
        extended_series = CandleSeries(tuple(extended_candles), self.step)

        snap_extended = extract_features(extended_series, "USDTTMN", cutoff=cutoff)

        # The snapshot must be 100% identical in values, evidences and SHA256 hash!
        self.assertEqual(snap_initial.snapshot_sha256, snap_extended.snapshot_sha256)
        self.assertEqual(snap_initial.closed_bars_count, snap_extended.closed_bars_count)
        self.assertEqual(snap_initial.last_close, snap_extended.last_close)
        self.assertEqual(snap_initial.trend_sma_fast, snap_extended.trend_sma_fast)
        self.assertEqual(snap_initial.trend_sma_slow, snap_extended.trend_sma_slow)
        self.assertEqual(snap_initial.rsi_14, snap_extended.rsi_14)
        self.assertEqual(snap_initial.atr_14, snap_extended.atr_14)
        self.assertEqual(snap_initial.evidences, snap_extended.evidences)

    def test_incomplete_candle_excluded_at_cutoff(self):
        """Candles whose close time exceeds cutoff must be excluded."""
        # 40 candles: 40th candle open_time = start + 39 * 900.
        # Its close time is start + 40 * 900.
        # If cutoff is start + 40 * 900 - 1, the 40th candle is incomplete!
        cutoff_incomplete = self.start + 40 * self.step - 1
        snap_incomplete = extract_features(self.series, "USDTTMN", cutoff=cutoff_incomplete)

        cutoff_complete = self.start + 40 * self.step
        snap_complete = extract_features(self.series, "USDTTMN", cutoff=cutoff_complete)

        self.assertEqual(snap_incomplete.closed_bars_count, 39)
        self.assertEqual(snap_complete.closed_bars_count, 40)
        self.assertNotEqual(snap_incomplete.snapshot_sha256, snap_complete.snapshot_sha256)

    def test_sma_calculation(self):
        candles = self.series.candles[:10]
        expected = sum((c.close for c in candles), Decimal(0)) / Decimal(10)
        self.assertEqual(compute_sma(candles, 10), expected)

    def test_rsi_bounds(self):
        rsi = compute_rsi(self.series.candles, 14)
        self.assertGreaterEqual(rsi, Decimal(0))
        self.assertLessEqual(rsi, Decimal(100))

    def test_atr_positive(self):
        atr = compute_atr(self.series.candles, 14)
        self.assertGreater(atr, Decimal(0))

    def test_evidence_generation(self):
        cutoff = self.start + 45 * self.step
        snap = extract_features(
            self.series,
            "USDTTMN",
            cutoff=cutoff,
            current_position_base=Decimal("150.0"),
        )
        self.assertIn("EV_DATA_FRESH", snap.evidences)
        self.assertIn("EV_POSITION_LONG", snap.evidences)
        self.assertIn("EV_TREND_BULLISH", snap.evidences)


if __name__ == "__main__":
    unittest.main()
