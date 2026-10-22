"""Independent regressions for the blocked replay draft, using no network."""

import json
import unittest
from decimal import Decimal as D
from unittest.mock import MagicMock, patch

from royin.features import extract_features
from royin.market_data import Candle, CandleSeries
from scripts.run_paper_trader import (
    evaluate_impulse_strategy,
    fetch_wallex_candles,
    scan_best_market,
)


class PaperDataRegressionTests(unittest.TestCase):
    def test_checkpoint_alone_does_not_force_exit_but_exhaustion_can(self):
        def feature(high):
            candles=tuple(Candle(6000+i*60,D(100),D(high),D(99),D(101),D(20)) for i in range(35))
            return extract_features(CandleSeries(candles,60),"USDTTMN",cutoff=8100,current_position_base=D(1))
        action,_,_,reason=evaluate_impulse_strategy(feature(102),True,entry_price=D(98),
            entry_time=8000,current_time=8100,target_tp_pct=D(".025"))
        self.assertEqual(action,"WAIT")
        self.assertIsNone(reason)
        action,_,_,reason=evaluate_impulse_strategy(feature(104),True,entry_price=D(100),
            entry_time=8000,current_time=8100,target_tp_pct=D(".025"))
        self.assertEqual(action,"EXIT")
        self.assertEqual(reason,"MOMENTUM_STALL_EARLY_EXIT")

    def test_partial_aggregate_is_rejected_instead_of_becoming_a_bar(self):
        payload = dict(s="ok", t=[600, 660, 780, 840],
                       o=[1]*4, h=[2]*4, l=[1]*4, c=[2]*4, v=[1]*4)
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(payload).encode()
        with (patch("scripts.run_paper_trader.time.time", return_value=900),
              patch("urllib.request.urlopen", return_value=response),
              self.assertRaises(ValueError)):
            fetch_wallex_candles("USDTTMN", resolution="5", lookback_bars=1)

    def test_unverified_scanner_has_no_default_candidate(self):
        with patch("scripts.run_paper_trader.fetch_wallex_candles", return_value=[]):
            self.assertIsNone(scan_best_market())


if __name__ == "__main__":
    unittest.main()
