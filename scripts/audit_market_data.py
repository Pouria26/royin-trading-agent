"""Read-only Wallex data-quality probe; no strategy, credentials or order path."""

import argparse
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from itertools import pairwise
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
URL = "https://api.wallex.ir/v1/udf/history"
WINDOWS = (("2026-10-01", "2026-10-08"), ("2026-10-08", "2026-10-15"))
SYMBOLS = ("BTCTMN", "ETHTMN", "USDTTMN")


def epoch(day):
    return int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp())


def profile_history(payload, start, end, step=900):
    """Audit [start,end); the API may include the candle opening exactly at end."""
    if start >= end or step <= 0 or (end - start) % step:
        raise ValueError("Invalid audit window")
    if not isinstance(payload, dict) or payload.get("s") != "ok":
        raise ValueError("Historical data unavailable; not an empty successful sample")
    columns = ("t", "o", "h", "l", "c", "v")
    if any(not isinstance(payload.get(key), list) for key in columns):
        raise ValueError("Missing historical arrays")
    if len({len(payload[key]) for key in columns}) != 1:
        raise ValueError("Historical array lengths differ")
    times = payload["t"]
    if any(type(t) is not int for t in times):
        raise ValueError("Non-integer timestamp")
    selected = [i for i, t in enumerate(times) if start <= t < end]
    selected_times = [times[i] for i in selected]
    intervals = Counter(b - a for a, b in pairwise(selected_times) if b > a)
    modal_interval = intervals.most_common(1)[0][0] if intervals else None
    expected = set(range(start, end, step))
    observed = set(selected_times)
    invalid_rows = 0
    zero_volume_rows = 0
    for i in selected:
        try:
            values = [Decimal(str(payload[key][i])) for key in columns[1:]]
            if not all(value.is_finite() for value in values):
                invalid_rows += 1
                continue
            op, high, low, close, volume = values
            if (
                min(op, high, low, close) <= 0
                or volume < 0
                or not low <= min(op, close) <= max(op, close) <= high
            ):
                invalid_rows += 1
            zero_volume_rows += volume == 0
        except (InvalidOperation, ValueError, TypeError):
            invalid_rows += 1
    issues = {
        "duplicates": len(selected_times) - len(observed),
        "missing_candles": len(expected - observed),
        "off_grid_candles": len(observed - expected),
        "outside_requested_range": sum(t < start or t > end for t in times),
        "non_increasing_pairs": sum(b <= a for a, b in pairwise(times)),
        "invalid_numeric_or_ohlc_rows": invalid_rows,
    }
    return {
        "status": "PASS" if not any(issues.values()) else "DEGRADED",
        "expected_rows": len(expected),
        "selected_rows": len(selected),
        "boundary_end_rows_excluded": times.count(end),
        "first_timestamp": min(observed) if observed else None,
        "last_timestamp": max(observed) if observed else None,
        "zero_volume_rows": zero_volume_rows,
        "requested_interval_seconds": step,
        "modal_observed_interval_seconds": modal_interval,
        "observed_interval_counts": dict(sorted(intervals.items())),
        "missing_at_modal_interval": (
            len(set(range(start, end, modal_interval)) - observed) if modal_interval else None
        ),
        **issues,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    raw_dir = ROOT / "data" / "research"
    raw_dir.mkdir(parents=True, exist_ok=True)
    records = []
    controls = []
    with httpx.Client(timeout=20, follow_redirects=False) as client:
        for symbol in SYMBOLS:
            for first, last in WINDOWS:
                query = {
                    "symbol": symbol,
                    "resolution": "15",
                    "from": epoch(first),
                    "to": epoch(last),
                }
                record = {"query": query, "source_url": URL}
                try:
                    response = client.get(URL, params=query)
                    response.raise_for_status()
                    raw = response.content
                    raw_name = f"{symbol}_{first}_{last}_15.json"
                    (raw_dir / raw_name).write_bytes(raw)
                    record.update(
                        raw_sha256=hashlib.sha256(raw).hexdigest(),
                        raw_file=f"data/research/{raw_name}",
                        **profile_history(response.json(), query["from"], query["to"]),
                    )
                except (httpx.HTTPError, ValueError, TypeError) as exc:
                    record.update(status="ERROR", error_type=type(exc).__name__)
                records.append(record)
        for resolution, step in (("1", 60), ("15", 900), ("60", 3600)):
            first = epoch(WINDOWS[0][0])
            query = {"symbol": "BTCTMN", "resolution": resolution, "from": first, "to": first + 86400}
            record = {"query": query, "source_url": URL}
            try:
                response = client.get(URL, params=query)
                response.raise_for_status()
                raw = response.content
                raw_name = f"control_BTCTMN_2026-10-01_{resolution}.json"
                (raw_dir / raw_name).write_bytes(raw)
                record.update(
                    raw_sha256=hashlib.sha256(raw).hexdigest(),
                    raw_file=f"data/research/{raw_name}",
                    **profile_history(response.json(), first, first + 86400, step),
                )
            except (httpx.HTTPError, ValueError, TypeError) as exc:
                record.update(status="ERROR", error_type=type(exc).__name__)
            controls.append(record)
    report = {
        "kind": "PUBLIC_DATA_QUALITY_NOT_STRATEGY_PERFORMANCE",
        "fetched_at_utc": datetime.now(UTC).isoformat(),
        "scope": "3 public symbols, 2 fixed historical windows, 15-minute candles",
        "caveats": [
            "Public symbols are not the contest account allowlist.",
            "No fees, private account, LLM, strategy, fills or profitability tested.",
            "Historical order-book depth is not reconstructed from OHLCV.",
            "Raw snapshots are local and ignored; hashes identify this retrieval.",
        ],
        "records": records,
        "one_day_resolution_controls": controls,
    }
    output = ROOT / "research" / "market-data-audit.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(any(row["status"] != "PASS" for row in records))


if __name__ == "__main__":
    raise SystemExit(main())
