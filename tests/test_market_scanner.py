"""Causal catalog/depth tests, using synthetic data and exact monetary oracles."""

import copy
import json
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import MagicMock, patch

from royin.market_data import Candle, CandleSeries, decode_json
from scripts.run_paper_trader import (
    ScannerPublicFeed,
    build_candidate_batch,
    catalog_candidates,
    decode_closed_minutes,
    scan_current_market,
    shortlist_markets,
)


def catalog():
    rows = []
    for base, quote, volume, price in (
        ("BTC", "TMN", "200000000", "100"), ("ETH", "TMN", "300000000", "100"),
        ("TON", "TMN", "999999999999", "100"), ("TON", "USDT", "999999999999", "1"),
        ("USDT", "TMN", "10000000", "100"), ("BTC", "USDT", "4000000", "1"),
    ):
        rows.append(dict(symbol=base+quote, base_asset=base, quote_asset=quote, is_spot=True,
                         price_precision=2, amount_precision=2, quote_volume_24h=volume, price=price))
    return dict(success=True, result=dict(markets=rows))


def series():
    return CandleSeries(tuple(Candle(6000+i*60, D(100), D(102), D(98), D(100), D(200))
                              for i in range(35)), 60)


def depth():
    return dict(success=True, result=dict(bid=[dict(price="99.9", quantity="1000")],
                                         ask=[dict(price="100", quantity="1000")]))


class ScannerTests(unittest.TestCase):
    def test_model_can_select_a_liquid_market_outside_the_diagnostic_shortlist(self):
        payload = catalog()
        for base in ("DOGE","SOL","ADA","LTC","XLM","XRP"):
            row = dict(payload["result"]["markets"][0])
            row.update(symbol=base+"TMN",base_asset=base,quote_volume_24h="100000001")
            payload["result"]["markets"].append(row)
        symbols = {row["symbol"] for row in payload["result"]["markets"]}
        args = dict(account_symbols=symbols,cutoff=8105,received_at=8100,account_as_of=8100,tmn_only=True)
        candidates = catalog_candidates(payload,**args)
        self.assertGreater(len(candidates),5)
        requested = shortlist_markets(payload,**args,selected_symbols=["XRPTMN","SOLTMN"])
        self.assertEqual([row.symbol for row in requested],["XRPTMN","SOLTMN"])
        for selected in (["TONTMN"],["OPTMN"],["SOLTMN","SOLTMN"]):
            with self.subTest(selected=selected),self.assertRaises(ValueError):
                shortlist_markets(payload,**args,selected_symbols=selected)

    def test_current_pipeline_bounds_gets_and_unknown_access_precedes_io(self):
        feed = MagicMock()
        def get(endpoint, params, **kwargs):
            if endpoint.endswith("markets"):
                return catalog(),30005
            if endpoint.endswith("depth"):
                return depth(),30005
            times = list(range(params["from"],params["to"],60))
            return dict(s="ok",t=times,o=["100"]*len(times),h=["102"]*len(times),
                        l=["98"]*len(times),c=["100"]*len(times),v=["1000"]*len(times)),30005
        feed.get.side_effect = get
        args = dict(account_as_of=30000,round_trip_fee_pct=D(".006"),min_depth_tmn=D(10000),
                    max_spread_pct=D(".005"),available_tmn_cash=D(1234))
        with patch("time.time",return_value=30005):
            self.assertEqual(scan_current_market(feed,account_symbols=None,**args)["status"],"BLOCKED_ACCESS")
            feed.get.assert_not_called()
            report=scan_current_market(feed,account_symbols={"BTCTMN","ETHTMN","BTCUSDT"},**args)
        self.assertEqual(report["status"],"CANDIDATES")
        self.assertEqual(feed.get.call_count,7)
        self.assertEqual(len(report["batch"]), 3)
        self.assertEqual(report["batch"][0].snapshot.available_tmn_cash,D(1234))
        self.assertEqual(report["cutoff"], 30000)

    def shortlist(self, payload=None, **kwargs):
        params = dict(account_symbols={"BTCTMN", "ETHTMN", "TONTMN", "TONUSDT", "BTCUSDT"},
                      cutoff=8105, received_at=8100, account_as_of=8100)
        params.update(kwargs)
        return shortlist_markets(payload or catalog(), **params)

    def batch(self, rows=None, **kwargs):
        rows = rows if rows is not None else self.shortlist()
        symbols = [r.symbol for r in rows]
        params = dict(series_by_symbol={s:series() for s in symbols},
            depth_by_symbol={s:depth() for s in symbols}, cutoff=8105,
            snapshot_cutoff=8100,
            candle_received_at={s:8101 for s in symbols}, depth_received_at={s:8102 for s in symbols},
            round_trip_fee_pct=D(".006"), min_depth_tmn=D(10000), max_spread_pct=D(".005"),
            available_tmn_cash=D(1234))
        params.update(kwargs)
        return build_candidate_batch(rows, **params)

    def test_whole_catalog_turnover_is_tmn_and_ton_never_enters(self):
        rows = self.shortlist()
        self.assertEqual([r.symbol for r in rows], ["BTCUSDT", "ETHTMN", "BTCTMN"])
        self.assertEqual(rows[0].turnover_tmn, D(400000000))
        self.assertEqual(rows[0].quote_to_tmn, D(100))
        batch = self.batch(rows)
        self.assertEqual(len(batch), 3)
        self.assertEqual(batch[0].snapshot.available_tmn_cash, D(1234))
        self.assertEqual([c.snapshot.symbol for c in batch], ["BTCTMN", "BTCUSDT", "ETHTMN"])

    def test_unknown_access_stale_and_future_metadata_close_gate(self):
        for kwargs in (dict(account_as_of=None), dict(received_at=8000), dict(received_at=8106)):
            self.assertEqual(self.shortlist(**kwargs), ())
        with self.assertRaises(ValueError):
            self.shortlist(account_symbols=None)
        self.assertEqual(self.shortlist(account_symbols=[]), ())

    def test_replay_cannot_see_future_catalog_or_changed_future_candles(self):
        now = self.shortlist()
        self.assertEqual(self.shortlist(cutoff=8099), ())
        future = Candle(8100, D(1000), D(1200), D(10), D(900), D(999))
        # Open data must not reach the expensive stage as a completed snapshot.
        self.assertEqual(self.batch(now, series_by_symbol={r.symbol:CandleSeries((*series().candles, future),60)
                                                          for r in now}), ())
        from royin.features import extract_features
        original = extract_features(series(), "BTCTMN", cutoff=8100)
        full = extract_features(CandleSeries((*series().candles, future),60), "BTCTMN", cutoff=8100)
        self.assertEqual(original.snapshot_sha256, full.snapshot_sha256)

    def test_depth_spread_gap_stale_and_noise_are_handled(self):
        rows = self.shortlist()
        symbols = [r.symbol for r in rows]
        for changes in (
            dict(depth_by_symbol={s:dict(success=False) for s in symbols}),
            dict(depth_received_at={s:8000 for s in symbols}),
            dict(min_depth_tmn=D("1e20")),
            dict(max_spread_pct=D(".00001")),
            dict(series_by_symbol={s:CandleSeries(series().candles[:10]+series().candles[11:],60) for s in symbols}),
        ):
            with self.subTest(changes=changes):
                self.assertEqual(self.batch(rows, **changes), ())
        # Costs and ATR are ordering evidence, not hard eligibility gates.
        high_fee = self.batch(rows, round_trip_fee_pct=D(".1"))
        self.assertEqual(len(high_fee), 3)
        self.assertTrue(all(c.opportunity.round_trip_fee_pct == D(".1") for c in high_fee))

    def test_exact_decoding_and_no_gap_fill(self):
        raw = b'{"s":"ok","t":[600,660],"o":[1.0000000000000001,1],"h":[2,2],"l":[1,1],"c":[2,2],"v":[1,1]}'
        bars = decode_closed_minutes(raw, start=600, end=720, step=120, cutoff=720)
        self.assertEqual(bars.candles[0].open, D("1.0000000000000001"))
        payload = decode_json(raw)
        payload["t"][-1] = 720
        with self.assertRaises(ValueError):
            decode_closed_minutes(json.dumps(payload,default=str).encode(), start=600,end=720,step=120,cutoff=720)

    def test_public_get_cap_cache_age_and_no_fallback_on_error(self):
        with tempfile.TemporaryDirectory() as temp:
            feed = ScannerPublicFeed(Path(temp), max_requests=2)
            response = MagicMock()
            response.__enter__.return_value.read.return_value = b'{"success":true}'
            with patch("urllib.request.urlopen", return_value=response) as http, patch("time.time", return_value=8100):
                feed.get("/hector/web/v1/markets", {}, cutoff=8100)
                feed.get("/hector/web/v1/markets", {}, cutoff=8100)
                self.assertEqual(http.call_count, 1)
                self.assertEqual(feed.requests, 1)
                self.assertEqual(feed.captures[0]["received_at"], 8100)
            with patch("time.time", return_value=8200), patch("time.sleep"), patch("urllib.request.urlopen", side_effect=OSError):
                with self.assertRaises(OSError):
                    feed.get("/hector/web/v1/markets", {}, cutoff=8200)
                with self.assertRaisesRegex(ValueError, "cap"):
                    feed.get("/hector/web/v1/markets", {}, cutoff=8200)
            self.assertEqual(feed.requests, 2)
            with self.assertRaises(ValueError):
                feed.get("/v1/account/orders", {}, cutoff=8200)

    def test_no_raw_float_money_and_inactive_market_rejected(self):
        payload = copy.deepcopy(catalog())
        payload["result"]["markets"][0]["quote_volume_24h"] = 200000000.1
        payload["result"]["markets"][1]["is_active"] = False
        rows = self.shortlist(payload)
        self.assertNotIn("BTCTMN", [r.symbol for r in rows])
        self.assertNotIn("ETHTMN", [r.symbol for r in rows])


if __name__ == "__main__":
    unittest.main()
