"""Bounded public hourly observation; candidate execution remains blocked."""

import argparse
import contextlib
import hashlib
import json
import math
import os
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx

from royin.datasets import validate_candles
from royin.features import extract_features
from royin.logger import AuditLogger
from royin.market_data import CandleSeries, decode_json, parse_history

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SHADOW_DIR = ROOT / "data" / "shadow"
DEFAULT_LOCK_FILE = DEFAULT_SHADOW_DIR / "shadow_worker.lock"


class ShadowSingleWorkerLock:
    """Exclusive local lock; separate devices need operational exclusion."""

    def __init__(self, lock_path):
        self.lock_path, self._fd = Path(lock_path), None

    def acquire(self):
        if self._fd is not None:
            raise RuntimeError("This lock is already held")
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
        except FileExistsError:
            return False
        try:
            os.write(self._fd, json.dumps({"pid": os.getpid(), "time": datetime.now(UTC).isoformat()}).encode())
            os.fsync(self._fd)
        except OSError:
            self.release()
            raise
        return True

    def release(self):
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
            self.lock_path.unlink()

    def __enter__(self):
        if not self.acquire():
            raise BlockingIOError("Another local observer holds this lock")
        return self

    def __exit__(self, *args):
        self.release()


class PublicMarketFeed:
    """Count every public attempt; never use credentials or retries."""

    def __init__(self, symbol="USDTTMN", interval_seconds=3600, max_requests=40,
                 rate_spacing_seconds=1.0, timeout_seconds=20.0, http_client=None,
                 custom_candle_fetcher=None):
        if symbol != "USDTTMN" or type(interval_seconds) is not int or interval_seconds <= 0:
            raise ValueError("Only the USDTTMN research source is supported")
        if custom_candle_fetcher is None and interval_seconds != 3600:
            raise ValueError("Public observation requires native hourly candles")
        if type(max_requests) is not int or not 1 <= max_requests <= 40:
            raise ValueError("Request cap must be between 1 and 40")
        if not math.isfinite(rate_spacing_seconds) or rate_spacing_seconds < 1:
            raise ValueError("Spacing must be at least one second")
        if not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 20:
            raise ValueError("Invalid timeout")
        self.symbol, self.interval_seconds = symbol, interval_seconds
        self.max_requests, self.rate_spacing_seconds = max_requests, rate_spacing_seconds
        self.timeout_seconds = timeout_seconds
        self._client, self._custom_fetcher = http_client, custom_candle_fetcher
        self.request_count, self._last_request_time = 0, None
        self.last_response, self.last_query = None, None
        self.coverage = None

    def fetch_latest_candles(self):
        if self.request_count >= self.max_requests:
            raise ValueError("Public GET cap reached")
        if self._last_request_time is not None:
            time.sleep(max(0, self.rate_spacing_seconds - (time.monotonic() - self._last_request_time)))
        self.request_count += 1
        self._last_request_time = time.monotonic()
        self.last_response = None
        if self._custom_fetcher is not None:
            return self._custom_fetcher(self.symbol, self.interval_seconds)
        now = int(time.time())
        end = now // self.interval_seconds * self.interval_seconds
        start = end - 40 * self.interval_seconds
        self.last_query = {"symbol": self.symbol, "resolution": "60", "from": start, "to": end}
        with contextlib.ExitStack() as stack:
            client = self._client or stack.enter_context(httpx.Client(
                timeout=self.timeout_seconds, follow_redirects=False, trust_env=False))
            response = client.get("https://api.wallex.ir/v1/udf/history", params=self.last_query,
                                  timeout=self.timeout_seconds, follow_redirects=False)
            self.last_response = response.content
            response.raise_for_status()
            payload = decode_json(response.content)
            times = payload.get("t") if isinstance(payload, dict) else None
            if not isinstance(times, list) or not times or type(times[0]) is not int or not start <= times[0] < end:
                raise ValueError("No in-window observation history")
            # A missing prefix shortens warmup coverage; internal gaps still fail the exact parser.
            actual_start = times[0]
            self.coverage = {"requested_start": start, "actual_start": actual_start, "end": end}
            return list(parse_history(payload, start=actual_start, end=end,
                                      interval_seconds=self.interval_seconds, cutoff=now).candles)


def run_shadow_loop(mode, feed, *, max_cycles=1, max_poll_attempts=None,
                    cycle_interval_seconds=60.0, run_dir=None):
    """Observe closed diagnostic snapshots; no model, ledger or order transport."""
    if mode != "OBSERVE_ONLY":
        raise ValueError("BLOCKED_CANDIDATE: source and strategy acceptance are missing")
    attempts = max_poll_attempts if max_poll_attempts is not None else max_cycles
    if any(type(v) is not int or not 1 <= v <= 40 for v in (max_cycles, attempts)):
        raise ValueError("Cycles and attempts must be between 1 and 40")
    if not math.isfinite(cycle_interval_seconds) or not 0 <= cycle_interval_seconds <= 3600:
        raise ValueError("Invalid poll delay")
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    directory = Path(run_dir) if run_dir else DEFAULT_SHADOW_DIR / run_id
    directory.mkdir(parents=True, exist_ok=True)
    if any(directory.iterdir()):
        raise ValueError("Refusing to overwrite or reset an existing run")
    paths = [Path(__file__), ROOT / "src/royin/market_data.py", ROOT / "src/royin/features.py",
             ROOT / "docs/market-data-semantics.md"]
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    started, clock = datetime.now(UTC).isoformat(), time.monotonic()
    heartbeats, errors, captures, previous = [], [], [], None
    with AuditLogger(directory / "audit", False, run_id=run_id, mode="observation",
                     source="SYNTHETIC" if feed._custom_fetcher else "PUBLIC_FEED") as audit:
        audit.record_event("OBSERVATION_STARTED", "DATA", {"symbol": feed.symbol})
        for attempt in range(attempts):
            now = int(time.time())
            try:
                try:
                    raw = feed.fetch_latest_candles()
                finally:
                    if feed.last_response is not None:
                        digest = hashlib.sha256(feed.last_response).hexdigest()
                        (directory / (digest + ".json")).write_bytes(feed.last_response)
                        captures.append({"sha256": digest, "query": feed.last_query,
                                         "received_at_utc": datetime.now(UTC).isoformat()})
                # Interval-start labels remain a disclosed research assumption.
                closed = [c for c in raw if c.open_time + feed.interval_seconds <= now]
                validate_candles(closed, feed.interval_seconds, now=now)
                latest = closed[-1]
                cutoff = latest.open_time + feed.interval_seconds
                if now - cutoff > feed.interval_seconds:
                    raise ValueError("Stale closed data")
                if previous is not None and latest.open_time <= previous:
                    audit.record_event("DUPLICATE_CANDLE_SKIPPED", "DATA", {"cutoff": cutoff})
                else:
                    if previous is not None and latest.open_time != previous + feed.interval_seconds:
                        raise ValueError("Gap between observed cycles")
                    snapshot = extract_features(CandleSeries(tuple(closed), feed.interval_seconds),
                                                feed.symbol, cutoff=cutoff)
                    (directory / f"snapshot-{cutoff}.json").write_text(
                        json.dumps(snapshot.to_canonical_dict(), sort_keys=True), encoding="utf-8")
                    previous = latest.open_time
                    heartbeats.append({"cutoff": cutoff, "observed_at_utc": datetime.now(UTC).isoformat(),
                                       "snapshot_sha256": snapshot.snapshot_sha256,
                                       "status": "OBSERVED_DIAGNOSTIC_SNAPSHOT"})
                    audit.record_event("OBSERVE_SNAPSHOT", "DATA", {"cutoff": cutoff,
                                        "snapshot_sha256": snapshot.snapshot_sha256})
            except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError) as exc:
                errors.append({"attempt": attempt + 1, "error_type": type(exc).__name__})
                audit.record_event("OBSERVATION_ERROR", "DATA", {"error_type": type(exc).__name__})
            if len(heartbeats) >= max_cycles:
                break
            if attempt + 1 < attempts:
                time.sleep(cycle_interval_seconds)
        report = {"schema_version": 1, "run_id": run_id, "mode": mode,
                  "status": "COMPLETE" if len(heartbeats) == max_cycles else "PARTIAL",
                  "evidence_kind": "SYNTHETIC" if feed._custom_fetcher else "PUBLIC_FEED_DIAGNOSTIC",
                  "source_semantics": "timestamp start inferred; volume asset and finality unverified",
                  "source_hashes": hashes,
                  "revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                  "dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()),
                  "symbol": feed.symbol, "interval_seconds": feed.interval_seconds,
                  "started_at_utc": started, "finished_at_utc": datetime.now(UTC).isoformat(),
                  "elapsed_seconds": round(time.monotonic() - clock, 3),
                  "cycles_completed": len(heartbeats), "max_cycles": max_cycles,
                  "requests_made": feed.request_count, "attempts": attempt + 1,
                  "orders_submitted": 0, "fills_count": 0, "model_requests": 0,
                  "live_trading_enabled": False, "heartbeats": heartbeats, "errors": errors,
                  "captures": captures, "coverage": feed.coverage}
        audit.record_event("OBSERVATION_FINISHED", "DATA", {"status": report["status"], "count": len(heartbeats)})
        (directory / "shadow_manifest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["OBSERVE_ONLY", "CANDIDATE_SHADOW"], default="OBSERVE_ONLY")
    parser.add_argument("--symbol", default="USDTTMN")
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--max-attempts", type=int, default=1)
    parser.add_argument("--interval", type=int, default=3600)
    parser.add_argument("--poll-seconds", type=float, default=60)
    parser.add_argument("--out-dir", type=Path)
    args = parser.parse_args(argv)
    if args.mode != "OBSERVE_ONLY":
        parser.error("CANDIDATE_SHADOW is blocked pending source and strategy acceptance")
    if not math.isfinite(args.poll_seconds) or not 1 <= args.poll_seconds <= 3600:
        parser.error("--poll-seconds must be between 1 and 3600")
    try:
        feed = PublicMarketFeed(args.symbol, args.interval)
        with ShadowSingleWorkerLock(DEFAULT_LOCK_FILE):
            report = run_shadow_loop(args.mode, feed, max_cycles=args.cycles,
                                     max_poll_attempts=args.max_attempts,
                                     cycle_interval_seconds=args.poll_seconds, run_dir=args.out_dir)
    except (ValueError, OSError) as exc:
        print(json.dumps({"status": "BLOCKED", "error_type": type(exc).__name__, "orders_submitted": 0}))
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "COMPLETE" else 2


if __name__ == "__main__":
    sys.exit(main())
