"""Independent regressions for diagnostic observation, never candidate acceptance."""
import contextlib
import io
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import httpx

from royin.market_data import Candle
from scripts.run_shadow import PublicMarketFeed, ShadowSingleWorkerLock, main, run_shadow_loop

NOW = 1792618800
END = NOW // 3600 * 3600


def candles():
    return [Candle(END - (40 - i) * 3600, Decimal("100"), Decimal("101"),
                   Decimal("99"), Decimal("100"), Decimal("10")) for i in range(40)]


class ShadowObservationTests(unittest.TestCase):
    def run_fixture(self, data, cycles=1, attempts=1):
        feed = PublicMarketFeed(custom_candle_fetcher=lambda *_: data)
        with tempfile.TemporaryDirectory() as temp, patch("scripts.run_shadow.time.time", return_value=NOW), patch("scripts.run_shadow.time.sleep"):
            report = run_shadow_loop("OBSERVE_ONLY", feed, max_cycles=cycles,
                max_poll_attempts=attempts, cycle_interval_seconds=0, run_dir=Path(temp))
            snapshots = [json.loads(p.read_text()) for p in Path(temp).glob("snapshot-*.json")]
            return report, snapshots

    def test_rejected_lock_owner_cannot_release_active_lock(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "worker.lock"
            owner, rejected = ShadowSingleWorkerLock(path), ShadowSingleWorkerLock(path)
            self.assertTrue(owner.acquire())
            try:
                self.assertFalse(rejected.acquire())
                rejected.release()
                self.assertTrue(path.exists())
                self.assertFalse(ShadowSingleWorkerLock(path).acquire())
            finally:
                owner.release()
            self.assertTrue(rejected.acquire())
            rejected.release()

    def test_open_tail_cannot_enter_snapshot_or_cutoff(self):
        data = candles()
        data.append(Candle(END, Decimal("100"), Decimal("999999"), Decimal("99"),
                           Decimal("999999"), Decimal("10")))
        report, snapshots = self.run_fixture(data)
        self.assertEqual(report["status"], "COMPLETE")
        self.assertEqual(snapshots[0]["last_close"], "100")
        self.assertEqual(snapshots[0]["cutoff"], END)
        self.assertLessEqual(snapshots[0]["cutoff"], NOW)
        self.assertEqual(report["orders_submitted"], 0)
        self.assertEqual(report["model_requests"], 0)
        self.assertEqual(report["evidence_kind"], "SYNTHETIC")

    def test_duplicate_poll_is_partial_not_successful_second_cycle(self):
        report, _ = self.run_fixture(candles(), cycles=2, attempts=2)
        self.assertEqual(report["cycles_completed"], 1)
        self.assertEqual(report["status"], "PARTIAL")

    def test_stale_gap_invalid_ohlc_and_future_only_are_rejected(self):
        for data in [
            [Candle(c.open_time - 7200, c.open, c.high, c.low, c.close, c.volume) for c in candles()],
            candles()[:20] + candles()[21:],
            [*candles()[:-1], Candle(END - 3600, Decimal("100"), Decimal("90"), Decimal("99"), Decimal("100"), Decimal("10"))],
            [Candle(END + 3600, Decimal("100"), Decimal("101"), Decimal("99"), Decimal("100"), Decimal("10"))],
        ]:
            with self.subTest(data=data[-1].open_time):
                report, _ = self.run_fixture(data)
                self.assertEqual(report["cycles_completed"], 0)
                self.assertEqual(report["status"], "PARTIAL")
                self.assertTrue(report["errors"])

    def test_candidate_path_fails_before_feed_or_output(self):
        feed = PublicMarketFeed(custom_candle_fetcher=lambda *_: self.fail("Unexpected feed call"))
        with self.assertRaisesRegex(ValueError, "BLOCKED_CANDIDATE"):
            run_shadow_loop("CANDIDATE_SHADOW", feed)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exc:
            main(["--mode", "CANDIDATE_SHADOW"])
        self.assertEqual(exc.exception.code, 2)
        self.assertEqual(feed.request_count, 0)

    def test_existing_run_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            (path / "evidence.json").write_text("preserve")
            with self.assertRaisesRegex(ValueError, "overwrite"):
                run_shadow_loop("OBSERVE_ONLY", PublicMarketFeed(), run_dir=path)
            self.assertEqual((path / "evidence.json").read_text(), "preserve")

    def test_injected_fetcher_obeys_same_request_cap(self):
        feed = PublicMarketFeed(max_requests=1, custom_candle_fetcher=lambda *_: candles())
        feed.fetch_latest_candles()
        with self.assertRaisesRegex(ValueError, "cap"):
            feed.fetch_latest_candles()
        self.assertEqual(feed.request_count, 1)

    def test_public_transport_uses_exact_parser_and_excludes_inclusive_tail(self):
        rows = [*candles(), Candle(END, Decimal("100"), Decimal("100000"), Decimal("99"), Decimal("100000"), Decimal("10"))]
        payload = {"s": "ok", "t": [c.open_time for c in rows]}
        for key, field in [("o","open"),("h","high"),("l","low"),("c","close"),("v","volume")]:
            payload[key] = [str(getattr(c, field)) for c in rows]
        requests = []
        def transport(request):
            requests.append(request)
            self.assertNotIn("x-api-key", request.headers)
            return httpx.Response(200, json=payload)
        with httpx.Client(transport=httpx.MockTransport(transport)) as client, patch("scripts.run_shadow.time.time", return_value=NOW):
            feed = PublicMarketFeed(http_client=client)
            result = feed.fetch_latest_candles()
            self.assertEqual(len(result), 40)
            self.assertEqual(result[-1].open_time, END - 3600)
            self.assertEqual(requests[0].url.params["resolution"], "60")
            # Explicitly shorter warmup is allowed; no interior row may be removed.
            for key in ("t", "o", "h", "l", "c", "v"):
                payload[key] = payload[key][2:]
            with patch("scripts.run_shadow.time.sleep"):
                self.assertEqual(len(feed.fetch_latest_candles()), 38)
            self.assertEqual(feed.coverage["actual_start"], END - 38 * 3600)
            payload["t"].pop()
            with patch("scripts.run_shadow.time.sleep"), self.assertRaises(ValueError):
                feed.fetch_latest_candles()

    def test_invalid_request_bounds_and_resolution_fail_before_io(self):
        for kwargs in [{"max_requests": 0}, {"max_requests": 41}, {"interval_seconds": 900},
                       {"rate_spacing_seconds": 0}, {"timeout_seconds": 21}]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                PublicMarketFeed(**kwargs)


if __name__ == "__main__":
    unittest.main()
