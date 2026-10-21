"""Frozen-protocol public data check; maximum 27 GETs, zero retries, no credentials."""

import argparse
import hashlib
import json
import subprocess
import time
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import httpx

from royin.logger import AuditLogger
from royin.market_data import aggregate_closed, parse_history
from royin.markets import load_restrictions, parse_catalog
from scripts.prepare_market_data import fetch_public

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--protocol", type=Path, default=ROOT / "config/historical-validation-protocol.json"
    )
    args = parser.parse_args(argv)
    protocol = json.loads(args.protocol.read_bytes())
    cap = protocol["public_get_cap"]
    if not 0 < cap <= 120 or protocol["symbols"] != ["USDTTMN"]:
        raise ValueError("Unsupported frozen collection plan")
    start = int(
        datetime.fromisoformat(protocol["first_day_including_warmup"])
        .replace(tzinfo=UTC)
        .timestamp()
    )
    end = int(datetime.fromisoformat(protocol["end_exclusive"]).replace(tzinfo=UTC).timestamp())
    estimate = 1 + 2 * ((end - start) // 86400)
    if estimate > cap or end > int(time.time()) or end <= start:
        raise ValueError("Plan exceeds budget or contains future data")
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    directory = ROOT / "data/validation" / run_id
    directory.mkdir(parents=True)
    report = {
        "schema_version": 1,
        "run_id": run_id,
        "kind": "PUBLIC_DATA_QUALITY_NOT_ACCOUNT_PERMISSION",
        "protocol_sha256": hashlib.sha256(args.protocol.read_bytes()).hexdigest(),
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "source_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "source_dirty": bool(
            subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()
        ),
        "estimated_gets": estimate,
        "actual_gets": 0,
        "days": [],
        "datasets": [],
        "account_market_access": "UNVERIFIED; no private endpoint used",
    }
    with (
        AuditLogger(directory / "audit", False, run_id=run_id) as audit,
        httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as client,
    ):

        def fetch(endpoint, query):
            if report["actual_gets"] >= cap:
                raise ValueError("GET cap reached")
            report["actual_gets"] += 1
            time.sleep(protocol["rate_spacing_seconds"])
            return fetch_public(client, endpoint, query, directory)

        try:
            payload, source = fetch("/hector/web/v1/markets", {})
            catalog = parse_catalog(payload)
            market = catalog["USDTTMN"]
            denied = load_restrictions(ROOT / "config/wallex-credit-market-policy.json")
            if not market.is_spot or f"{market.base_asset}/{market.quote_asset}" in denied:
                raise ValueError("Research symbol not eligible under existing policy")
            report["catalog"] = source
            for day in range(start, end, 86400):
                row = {
                    "symbol": "USDTTMN",
                    "start": day,
                    "end": day + 86400,
                    "status": "REJECTED",
                    "sources": [],
                }
                try:
                    minute, source = fetch(
                        "/v1/udf/history",
                        {"symbol": "USDTTMN", "resolution": "1", "from": day, "to": day + 86400},
                    )
                    row["sources"].append(source)
                    native, source = fetch(
                        "/v1/udf/history",
                        {"symbol": "USDTTMN", "resolution": "60", "from": day, "to": day + 86400},
                    )
                    row["sources"].append(source)
                    minutes = parse_history(
                        minute, start=day, end=day + 86400, interval_seconds=60, cutoff=day + 86400
                    )
                    hourly = parse_history(
                        native,
                        start=day,
                        end=day + 86400,
                        interval_seconds=3600,
                        cutoff=day + 86400,
                    )
                    derived = aggregate_closed(minutes, 3600)
                    mismatch = sum(
                        a != b for a, b in zip(hourly.candles, derived.candles, strict=True)
                    )
                    row["hourly_mismatches"] = mismatch
                    if mismatch:
                        raise ValueError("Native/minute disagreement")
                    series = aggregate_closed(minutes, 900)
                    normalized = {
                        "symbol": "USDTTMN",
                        "base_asset": "USDT",
                        "quote_asset": "TMN",
                        "interval_seconds": 900,
                        "cutoff": day + 86400,
                        "incomplete_bins": series.incomplete_bins,
                        "sources": row["sources"],
                        "candles": [asdict(c) for c in series.candles],
                    }
                    raw = json.dumps(normalized, default=str, sort_keys=True).encode()
                    digest = hashlib.sha256(raw).hexdigest()
                    (directory / f"normalized-{digest}.json").write_bytes(raw)
                    row.update(
                        status="ACCEPTED",
                        sha256=digest,
                        path=f"normalized-{digest}.json",
                        interval_seconds=900,
                    )
                    report["datasets"].append(
                        {
                            k: row[k]
                            for k in (
                                "symbol",
                                "start",
                                "end",
                                "status",
                                "sha256",
                                "path",
                                "interval_seconds",
                            )
                        }
                    )
                except (ValueError, KeyError, httpx.HTTPError) as exc:
                    row["error_type"] = type(exc).__name__
                report["days"].append(row)
                audit.record_event(
                    "DATA_ACCEPTED" if row["status"] == "ACCEPTED" else "DATA_REJECTED",
                    "DATA",
                    {
                        "symbol": row["symbol"],
                        "cutoff": row["end"],
                        "status": row["status"],
                        "error_type": row.get("error_type"),
                        "count": row.get("hourly_mismatches"),
                    },
                )
                (directory / "manifest.json").write_text(
                    json.dumps(report, indent=2) + "\n", encoding="utf-8"
                )
        except (ValueError, KeyError, httpx.HTTPError) as exc:
            report["error_type"] = type(exc).__name__
    report["status"] = (
        "PASS_DATA_ONLY" if len(report["datasets"]) == (end - start) // 86400 else "BLOCKED_DATA"
    )
    report["finished_at_utc"] = datetime.now(UTC).isoformat()
    (directory / "manifest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "run_id": run_id,
                "status": report["status"],
                "actual_gets": report["actual_gets"],
                "accepted_days": len(report["datasets"]),
                "manifest": str(directory / "manifest.json"),
            }
        )
    )
    return 0 if report["status"] == "PASS_DATA_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
