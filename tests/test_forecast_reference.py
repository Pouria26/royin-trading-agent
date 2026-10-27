"""Hand-calculated causal references and strict required-window regressions."""
import json
import unittest
from dataclasses import replace
from decimal import Decimal as D
from decimal import Inexact, localcontext

from royin.features import extract_features
from royin.forecast_reference import historical_return_reference
from royin.market_data import Candle, CandleSeries
from scripts.run_paper_trader import parse_research_history


def series(count=200):
    return CandleSeries(tuple(Candle(300+i*300,D(100+i),D(101+i),D(99+i),D(100+i),D(10))
        for i in range(count)),300)


class ForecastReferenceTests(unittest.TestCase):
    def test_statistical_division_does_not_depend_on_callers_money_rounding_traps(self):
        expected=historical_return_reference(series(),cutoff=60300)
        with localcontext() as ctx:
            ctx.traps[Inexact]=True
            self.assertEqual(historical_return_reference(series(),cutoff=60300),expected)

    def test_hand_calculated_segments_quantiles_and_insufficient_horizon(self):
        result=historical_return_reference(series(40),cutoff=12300)
        short,hour,long=result['horizons']
        self.assertEqual([v['segments'] for v in result['horizons']],[13,3,1])
        with localcontext() as ctx:
            ctx.prec=36
            for key,value in [('q10',D(3)/133),('q50',D(3)/118),('q90',D(3)/103)]:
                self.assertLess(abs(D(short[key])-value),D('1e-34'))
        self.assertEqual(hour['status'],'INSUFFICIENT_SEGMENTS')
        self.assertIsNone(hour['q50'])
        self.assertIsNone(long['q90'])
        self.assertEqual(result['status'],'HISTORICAL_ONLY_NOT_FORECAST')

    def test_future_candles_cannot_change_reference_or_bound_snapshot(self):
        original=series()
        cutoff=60300
        future=Candle(cutoff,D(1),D(100000),D(1),D(99999),D(99999))
        extended=CandleSeries((*original.candles,future),300)
        self.assertEqual(historical_return_reference(original,cutoff=cutoff),
                         historical_return_reference(extended,cutoff=cutoff))
        main=CandleSeries(original.candles[-40:],300)
        a=extract_features(main,'BTCTMN',cutoff=cutoff,reference_series=original)
        b=extract_features(main,'BTCTMN',cutoff=cutoff,reference_series=extended)
        self.assertEqual(a.snapshot_sha256,b.snapshot_sha256)
        self.assertTrue(a.verify_hash())
        self.assertEqual(json.loads(a.evidences['EV_HORIZON_RETURN_REFERENCE'])['closed_bars'],200)
        self.assertEqual(a.last_close,main.candles[-1].close)

    def test_gap_stale_foreign_suffix_and_invalid_price_are_not_silently_used(self):
        original=series()
        main=CandleSeries(original.candles[-40:],300)
        for bad in [CandleSeries(original.candles[:10]+original.candles[11:],300),
                CandleSeries(original.candles[:-1],300),
                CandleSeries((*original.candles[:-1],replace(original.candles[-1],close=D('NaN'))),300)]:
            with self.assertRaises(ValueError):
                historical_return_reference(bad,cutoff=60300)
        bad=replace(original.candles[-1],close=D('299.5'),high=D(301))
        with self.assertRaises(ValueError):
            extract_features(main,'BTCTMN',cutoff=60300,
                reference_series=CandleSeries((*original.candles[:-1],bad),300))

    def test_old_optional_gap_leaves_original_current_window_valid_but_not_fabricated_history(self):
        end=60300
        times=list(range(end-60000,end+1,60))
        payload=dict(s='ok',t=times,**{k:['100']*len(times) for k in ('o','h','l','c','v')})
        original,reference=parse_research_history(payload,end=end,interval_seconds=300,cutoff=end,reference_bars=200)
        self.assertEqual((len(original.candles),len(reference.candles)),(40,200))
        for key in ('t','o','h','l','c','v'):
            payload[key].pop(2)
        current,missing=parse_research_history(payload,end=end,interval_seconds=300,cutoff=end,reference_bars=200)
        self.assertEqual(current,original)
        self.assertIsNone(missing)
        # The required recent range remains strict; an omitted minute still blocks the candidate.
        for key in ('t','o','h','l','c','v'):
            payload[key].pop(900)
        with self.assertRaises(ValueError):
            parse_research_history(payload,end=end,interval_seconds=300,cutoff=end,reference_bars=200)
