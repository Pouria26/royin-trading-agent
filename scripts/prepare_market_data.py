"""T02 public data contract check: at most 49 GETs, exact closed fifteen-minute bars."""

import argparse
import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import DecimalException
from pathlib import Path

import httpx

from royin.market_data import CandleSeries, aggregate_closed, decode_json, parse_history
from royin.markets import load_restrictions, parse_catalog
from scripts.audit_market_data import SYMBOLS, WINDOWS, epoch

ROOT = Path(__file__).resolve().parents[1]


def fetch_public(client, endpoint, query, directory):
    if endpoint not in ("/v1/udf/history", "/hector/web/v1/markets"):
        raise ValueError("Not an allowed public endpoint")
    url = "https://api.wallex.ir" + endpoint
    response = client.get(url, params=query)
    response.raise_for_status()
    raw = response.content
    if len(raw) > 16 * 1024 * 1024:
        raise ValueError("Public response exceeds 16 MiB")
    digest = hashlib.sha256(raw).hexdigest()
    path = directory / f"{digest}.json"
    if path.exists() and path.read_bytes() != raw:
        raise ValueError("Stored snapshot hash mismatch")
    if not path.exists():
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(raw)
        temporary.replace(path)
    return decode_json(raw), {
        "source_url": url, "query": query, "raw_sha256": digest,
        "raw_file": path.resolve().relative_to(ROOT).as_posix(),
        "fetched_at_utc": datetime.now(UTC).isoformat(),
        "public_cache_headers": {name: response.headers[name] for name in
                                 ("date", "age", "etag", "last-modified", "cache-control")
                                 if name in response.headers},
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    directory = ROOT / "data" / "t02"
    directory.mkdir(parents=True, exist_ok=True)
    report = {
        "kind": "PUBLIC_DATA_CONTRACT_NOT_BACKTEST_OR_ACCOUNT_PERMISSION",
        "records": [], "account_access": "BLOCKED_NO_PRIVATE_CONTRACT",
        "timestamp_semantics": "open time assumed; hourly comparison checked separately",
    }
    try:
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            payload, report["catalog"] = fetch_public(
                client, "/hector/web/v1/markets", {}, directory,
            )
            catalog = parse_catalog(payload)
            report["catalog"]["parsed_markets"] = len(catalog)
            policy_path = ROOT / "config" / "wallex-credit-market-policy.json"
            denied = load_restrictions(policy_path)
            report["policy_sha256"] = hashlib.sha256(policy_path.read_bytes()).hexdigest()
            for symbol in SYMBOLS:
                if symbol not in catalog or not catalog[symbol].is_spot:
                    raise ValueError("Research market is not active spot")
                market = catalog[symbol]
                if f"{market.base_asset}/{market.quote_asset}" in denied:
                    raise ValueError("Research market is denied by snapshot")
                for first, last in WINDOWS:
                    start, end = epoch(first), epoch(last)
                    record = {"symbol": symbol, "start": start, "end": end, "sources": []}
                    try:
                        candles = []
                        for day in range(start, end, 86400):
                            day_end = min(day + 86400, end)
                            query = {
                                "symbol": symbol, "resolution": "1", "from": day, "to": day_end,
                            }
                            payload, provenance = fetch_public(
                                client, "/v1/udf/history", query, directory,
                            )
                            record["sources"].append(provenance)
                            candles.extend(parse_history(
                                payload, start=day, end=day_end, interval_seconds=60, cutoff=day_end,
                            ).candles)
                        series = aggregate_closed(CandleSeries(tuple(candles), 60), 900)
                        native_payload, native_source = fetch_public(
                            client, "/v1/udf/history",
                            {"symbol": symbol, "resolution": "60", "from": start,
                             "to": start + 86400}, directory,
                        )
                        record["hourly_reference"] = native_source
                        native = parse_history(
                            native_payload, start=start, end=start + 86400,
                            interval_seconds=3600, cutoff=start + 86400,
                        )
                        derived = aggregate_closed(CandleSeries(tuple(candles[:1440]), 60), 3600)
                        mismatches = sum(a != b for a, b in zip(
                            native.candles, derived.candles, strict=True,
                        ))
                        record["hourly_reference_mismatches"] = mismatches
                        if mismatches:
                            raise ValueError("Source OHLCV disagrees across intervals")
                        normalized = json.dumps({
                            "symbol": symbol, "base_asset": market.base_asset,
                            "quote_asset": market.quote_asset, "interval_seconds": 900,
                            "cutoff": end, "sources": record["sources"],
                            "candles": [asdict(c) for c in series.candles],
                            "incomplete_bins": series.incomplete_bins,
                        }, default=str, indent=2).encode("utf-8")
                        digest = hashlib.sha256(normalized).hexdigest()
                        (directory / f"normalized-{digest}.json").write_bytes(normalized)
                        record.update(
                            status="PASS_DATA_ONLY", closed_bars=len(series.candles),
                            normalized_sha256=digest, incomplete_bins=series.incomplete_bins,
                        )
                    except (httpx.HTTPError, ValueError, DecimalException) as exc:
                        record.update(status="REJECTED", error_type=type(exc).__name__)
                    report["records"].append(record)
    except (httpx.HTTPError, ValueError, OSError) as exc:
        report.update(status="ERROR", error_type=type(exc).__name__)
    report["status"] = report.get("status", "PASS_DATA_ONLY" if all(
        r["status"] == "PASS_DATA_ONLY" for r in report["records"]
    ) else "DEGRADED")
    (directory / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return int(report["status"] != "PASS_DATA_ONLY")


if __name__ == "__main__":
    raise SystemExit(main())
