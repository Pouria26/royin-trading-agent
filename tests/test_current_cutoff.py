"""Current scheduler gate only; persistence and financial protection are B's boundary."""

import unittest
from decimal import Decimal as D

from royin.market_data import Candle, CandleSeries
from scripts.run_shadow import next_current_snapshot


class CurrentCutoffTests(unittest.TestCase):
    def call(self, now, previous=None, series=None):
        candles = tuple(Candle(6000+i*60,D(100),D(101),D(99),D(100),D(1)) for i in range(40))
        return next_current_snapshot(series or CandleSeries(candles,60), "USDTTMN", started_at=8105,
            now=now, previous_cutoff=previous, current_position_base=D(0), available_tmn_cash=D(1234))

    def test_warmup_open_tail_and_same_candle_restart_not_new_cycle(self):
        self.assertIsNone(self.call(8105))
        snap = self.call(8165)
        self.assertEqual(snap.cutoff,8160)
        self.assertEqual(snap.available_tmn_cash,D(1234))
        self.assertIsNone(self.call(8165,8160))
        self.assertEqual(self.call(8225,8160).cutoff,8220)

    def test_gap_stale_and_missing_checkpoint_fail_closed(self):
        for now, previous in ((8285,8160),(8225,None),(8165,8000)):
            with self.subTest(now=now), self.assertRaises(ValueError):
                self.call(now,previous)
        candles = tuple(Candle(6000+i*60,D(100),D(101),D(99),D(100),D(1)) for i in range(35))
        with self.assertRaises(ValueError):
            self.call(8225,8100,CandleSeries(candles,60))


if __name__ == "__main__":
    unittest.main()
