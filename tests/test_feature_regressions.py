import unittest
from decimal import Decimal

from royin.features import FeatureSnapshot, compute_rsi, extract_features
from royin.market_data import Candle, CandleSeries


class FeatureRegressionTests(unittest.TestCase):
    def test_repro_flat_market_rsi_is_neutral_50_not_100(self):
        """When prices are completely constant (zero gain and zero loss), RSI must be 50, not 100."""
        candles = [
            Candle(
                open_time=1000 + i * 900,
                open=Decimal("60000"),
                high=Decimal("60000"),
                low=Decimal("60000"),
                close=Decimal("60000"),
                volume=Decimal("10"),
            )
            for i in range(20)
        ]
        rsi = compute_rsi(candles, period=14)
        self.assertEqual(rsi, Decimal(50))

    def test_gap_in_candle_series_is_rejected(self):
        """A series with a missing candle gap must be rejected rather than silently analyzed."""
        candles = [
            Candle(
                open_time=1000 + i * 900,
                open=Decimal("60000"),
                high=Decimal("60500"),
                low=Decimal("59500"),
                close=Decimal("60000"),
                volume=Decimal("10"),
            )
            for i in range(35)
        ]
        # Introduce a gap
        candles[20] = Candle(
            open_time=1000 + 20 * 900 + 1800,  # skipped 1800s
            open=Decimal("60000"),
            high=Decimal("60500"),
            low=Decimal("59500"),
            close=Decimal("60000"),
            volume=Decimal("10"),
        )
        series = CandleSeries(candles=tuple(candles), interval_seconds=900)
        with self.assertRaises(ValueError) as ctx:
            extract_features(series, "USDTTMN", cutoff=1000 + 35 * 900)
        self.assertIn("gap", str(ctx.exception).lower())

    def test_feature_snapshot_detects_hash_tampering(self):
        """FeatureSnapshot verify_hash must detect if payload was modified."""
        candles = [
            Candle(
                open_time=1000 + i * 900,
                open=Decimal("60000"),
                high=Decimal("60500"),
                low=Decimal("59500"),
                close=Decimal("60000") + Decimal(i * 10),
                volume=Decimal("10"),
            )
            for i in range(35)
        ]
        series = CandleSeries(candles=tuple(candles), interval_seconds=900)
        snap = extract_features(series, "USDTTMN", cutoff=1000 + 34 * 900 + 900)
        self.assertTrue(snap.verify_hash())

        # If created with bad hash, verify_hash returns False or raises
        bad_snap = FeatureSnapshot(
            symbol=snap.symbol,
            cutoff=snap.cutoff,
            interval_seconds=snap.interval_seconds,
            closed_bars_count=snap.closed_bars_count,
            last_close=snap.last_close,
            trend_sma_fast=snap.trend_sma_fast,
            trend_sma_slow=snap.trend_sma_slow,
            rsi_14=snap.rsi_14,
            atr_14=snap.atr_14,
            volume_ratio=snap.volume_ratio,
            current_position_base=snap.current_position_base,
            available_tmn_cash=snap.available_tmn_cash,
            evidences=snap.evidences,
            snapshot_sha256="0" * 64,  # wrong hash!
        )
        self.assertFalse(bad_snap.verify_hash())


if __name__ == "__main__":
    unittest.main()
