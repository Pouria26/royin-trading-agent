import copy
import hashlib
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import httpx

from royin.datasets import accepted_datasets, load_dataset
from royin.market_data import Candle, parse_history
from scripts import prepare_market_data
from scripts.collect_validation_data import collect_native, native_parts, native_segments


class NativeHourDataTests(unittest.TestCase):
    def setUp(self):
        self.start = 1789344000
        self.candle = Candle(self.start, *map(Decimal, ("100", "102", "99", "101", "3")))
        self.data = {
            "symbol": "USDTTMN", "base_asset": "USDT", "quote_asset": "TMN",
            "interval_seconds": 3600, "cutoff": self.start + 7200, "incomplete_bins": [],
            "sources": [], "candles": [dict(open_time=self.start + i * 3600, open="100",
                high="102", low="99", close="101", volume="3") for i in range(2)],
        }

    def test_schema_rejects_each_corruption_with_independent_manifest(self):
        def change(data, field, value):
            data["candles"][0][field] = value

        corruptions = {
            "interval": lambda d: d.update(interval_seconds=900),
            "duplicate": lambda d: d["candles"][1].update(open_time=self.start),
            "gap": lambda d: d["candles"][1].update(open_time=self.start + 7200),
            "open_future": lambda d: change(d, "open_time", 4102444800),
            "volume": lambda d: change(d, "volume", "-1"),
            "OHLC": lambda d: change(d, "high", "98"),
            "nonfinite": lambda d: change(d, "close", "NaN"),
            "cutoff": lambda d: d.update(cutoff=self.start + 7199),
            "metadata": lambda d: d.update(base_asset="BTC"),
        }
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "normalized.json"
            good = json.dumps(self.data).encode()
            record = {"sha256": hashlib.sha256(good).hexdigest(), "status": "ACCEPTED",
                "symbol": "USDTTMN", "interval_seconds": 3600, "start": self.start,
                "end": self.start + 7200, "path": path.name}
            path.write_bytes(good)
            self.assertEqual(len(load_dataset(path, record)[1]), 2)
            for name, corrupt in corruptions.items():
                with self.subTest(name=name):
                    data = copy.deepcopy(self.data)
                    corrupt(data)
                    path.write_text(json.dumps(data))
                    with self.assertRaises(ValueError):
                        load_dataset(path, record)
            path.write_bytes(good)
            with self.assertRaises(ValueError):
                load_dataset(path, dict(record, sha256="0" * 64))
            path.write_bytes(good + b" ")
            with self.assertRaises(ValueError):
                load_dataset(path, record)
            path.write_bytes(good)
            manifest = Path(temp) / "manifest.json"
            manifest.write_text(json.dumps({"schema_version": 1, "datasets": [record, record]}))
            self.assertEqual(len(accepted_datasets(manifest)), 1)

    def test_boundary_tail_is_excluded_and_wrong_resolution_rejected(self):
        payload = {"s": "ok", "t": [self.start, self.start + 3600],
                   "o": ["100"] * 2, "h": ["102"] * 2, "l": ["99"] * 2,
                   "c": ["101"] * 2, "v": ["3"] * 2}
        series = parse_history(payload, start=self.start, end=self.start + 3600,
                               interval_seconds=3600, cutoff=self.start + 3600)
        self.assertEqual(series.candles, (self.candle,))
        self.assertEqual(parse_history(payload, start=self.start, end=self.start + 3600,
                         interval_seconds=3600, cutoff=self.start + 3599).candles, ())
        payload["t"][1] = self.start + 60
        with self.assertRaises(ValueError):
            parse_history(payload, start=self.start, end=self.start + 3600,
                          interval_seconds=3600, cutoff=self.start + 3600)

    def test_join_checks_overlap_and_never_hides_missing_day(self):
        next_bar = Candle(self.start + 3600, self.candle.open, self.candle.high,
                          self.candle.low, self.candle.close, self.candle.volume)
        days = [{"candles": [self.candle], "tail": next_bar}, {"candles": [next_bar]}]
        self.assertEqual(native_segments(days), [[self.candle, next_bar]])
        self.assertEqual(native_segments([days[0], {}, days[1]]), [[self.candle], [next_bar]])
        bad = Candle(next_bar.open_time, Decimal("101"), next_bar.high, next_bar.low,
                     next_bar.close, next_bar.volume)
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            native_segments([days[0], {"candles": [bad]}])

    def test_missing_native_hour_splits_coverage_without_removing_other_bad_rows(self):
        payload = {"s": "ok", "t": [self.start, self.start + 7200, self.start + 10800],
                   "o": ["100"] * 3, "h": ["102"] * 3, "l": ["99"] * 3,
                   "c": ["101"] * 3, "v": ["3"] * 3}
        parts = native_parts(payload, self.start, self.start + 10800, self.start + 14400)
        self.assertEqual([[c.open_time for c in p] for p in parts],
                         [[self.start], [self.start + 7200]])
        for field, value in (("v", "-1"), ("h", "98"), ("c", "NaN")):
            bad = copy.deepcopy(payload)
            bad[field][1] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                native_parts(bad, self.start, self.start + 10800, self.start + 14400)
        for times in ([self.start, self.start], [self.start + 60], [self.start - 3600],
                      [self.start + 3600, self.start]):
            bad = {k: [v[0]] * len(times) for k, v in payload.items() if k != "s"}
            bad.update(s="ok", t=times)
            with self.subTest(times=times), self.assertRaises(ValueError):
                native_parts(bad, self.start, self.start + 10800, self.start + 14400)

    def test_public_provenance_allows_only_cache_headers(self):
        def response(request):
            return httpx.Response(200, json={"s": "ok"}, headers={
                "date": "Wed, 21 Oct 2026 21:00:00 GMT", "x-test-private": "synthetic-only"})

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(prepare_market_data, "ROOT", root), httpx.Client(
                transport=httpx.MockTransport(response)
            ) as client:
                _, source = prepare_market_data.fetch_public(client, "/v1/udf/history", {}, root)
            self.assertEqual(source["public_cache_headers"],
                             {"date": "Wed, 21 Oct 2026 21:00:00 GMT"})

    def test_native_get_cap_rejected_before_client_or_state_creation(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "plan.json"
            path.write_text(json.dumps({"contract_id": "WALLEX_NATIVE_60_SOURCE_V1",
                "symbols": ["USDTTMN"], "resolution": "60", "interval_seconds": 3600,
                "start": "2026-09-14", "end_exclusive": "2026-09-15", "diagnostics": [],
                "public_get_cap": 81}))
            with patch("scripts.collect_validation_data.httpx.Client") as client:
                with self.assertRaises(ValueError):
                    collect_native(path)
                client.assert_not_called()


if __name__ == "__main__":
    unittest.main()
