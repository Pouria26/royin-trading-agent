"""Public data checks: legacy protocol or separate bounded native-hour source plan."""

import argparse
import hashlib
import json
import subprocess
import time
import uuid
from contextlib import suppress
from dataclasses import asdict
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path

import httpx

from royin.datasets import validate_candles
from royin.logger import AuditLogger
from royin.market_data import aggregate_closed, decode_json, parse_history
from royin.markets import load_restrictions, parse_catalog
from scripts.prepare_market_data import fetch_public

ROOT = Path(__file__).resolve().parents[1]


def native_segments(days):
    """Join adjacent closed days; equal endpoint overlaps are evidence, never gap fill."""
    segments = []
    current = []
    previous_tail = None
    for day in days:
        candles = day.get("candles", ())
        if not candles:
            if current:
                segments.append(current)
            current, previous_tail = [], None
            continue
        validate_candles(candles, 3600)
        if current and candles[0].open_time != current[-1].open_time + 3600:
            segments.append(current)
            current = []
        if current and previous_tail is not None and previous_tail != candles[0]:
            raise ValueError("Conflicting daily endpoint overlap")
        current.extend(candles)
        previous_tail = day.get("tail")
    if current:
        segments.append(current)
    return segments


def native_parts(payload, start, end, cutoff):
    """Validate every closed row, partition only at explicit missing UTC hours."""
    arrays = [payload.get(k) for k in ("t", "o", "h", "l", "c", "v")]
    if (payload.get("s") != "ok" or any(not isinstance(a, list) for a in arrays)
            or len({len(a) for a in arrays}) != 1 or len(arrays[0]) > 100001):
        raise ValueError("Invalid history arrays")
    times = arrays[0]
    if (not times or any(type(t) is not int or not start <= t <= end or t % 3600 for t in times)
            or any(b <= a for a, b in pairwise(times))):
        raise ValueError("Invalid native-hour timestamps")
    selected = [i for i, t in enumerate(times) if t < min(end, cutoff // 3600 * 3600)]
    groups = []
    for i in selected:
        if not groups or times[i] != times[groups[-1][-1]] + 3600:
            groups.append([])
        groups[-1].append(i)
    parts = []
    for indices in groups:
        subset = {k: [payload[k][i] for i in indices] for k in ("t", "o", "h", "l", "c", "v")}
        subset["s"] = "ok"
        parts.append(parse_history(subset, start=times[indices[0]], end=times[indices[-1]] + 3600,
                                   interval_seconds=3600, cutoff=cutoff).candles)
    return parts


def collect_native(plan_path, replay_path=None):
    """A separate source-only native-hour contract; never relabel legacy T02 data."""
    plan_raw = plan_path.read_bytes()
    plan = json.loads(plan_raw)
    start = int(datetime.fromisoformat(plan["start"]).replace(tzinfo=UTC).timestamp())
    end = int(datetime.fromisoformat(plan["end_exclusive"]).replace(tzinfo=UTC).timestamp())
    estimate = 1 + (end - start) // 86400 + len(plan["diagnostics"])
    if (
        plan["contract_id"] != "WALLEX_NATIVE_60_SOURCE_V1"
        or plan["symbols"] != ["USDTTMN"]
        or plan["resolution"] != "60" or plan["interval_seconds"] != 3600
        or not 0 < estimate <= plan["public_get_cap"] <= 80
        or estimate != plan["public_get_estimate"]
        or plan["retry"] != 0 or not 1 <= plan["rate_spacing_seconds"] <= 60
        or not 0 < plan["timeout_seconds"] <= 20
        or not 0 < start < end <= plan["cutoff"] <= int(time.time())
        or start % 86400 or end % 86400
    ):
        raise ValueError("Invalid source-only plan")
    for diagnostic in plan["diagnostics"]:
        q = diagnostic["query"]
        if (q["symbol"] != "USDTTMN" or q["resolution"] not in ("1", "15", "60")
                or not 0 < q["from"] < q["to"] <= plan["cutoff"]
                or q["to"] - q["from"] > 2 * 86400):
            raise ValueError("Unbounded diagnostic query")
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    directory = ROOT / "data/round-2-data" / run_id
    directory.mkdir(parents=True)
    report = {"schema_version": 1, "run_id": run_id, "contract_id": plan["contract_id"],
              "source_plan_sha256": hashlib.sha256(plan_raw).hexdigest(),
              "source_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
              "source_hashes": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in
                                ("scripts/collect_validation_data.py", "scripts/prepare_market_data.py",
                                 "src/royin/market_data.py", "src/royin/datasets.py")},
              "actual_gets": 0, "requests": [], "days": [], "datasets": [],
              "account_market_access": "UNVERIFIED_PUBLIC_SOURCE_ONLY"}
    replay = None
    if replay_path is not None:
        parent_raw = replay_path.read_bytes()
        parent = json.loads(parent_raw)
        if parent["source_plan_sha256"] != report["source_plan_sha256"]:
            raise ValueError("Replay plan mismatch")
        replay = iter(parent["requests"])
        report.update(parent_capture_sha256=hashlib.sha256(parent_raw).hexdigest(),
                      parent_capture_path=str(replay_path), replayed_requests=0)

    def save():
        (directory / "manifest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    with httpx.Client(timeout=plan["timeout_seconds"], follow_redirects=False, trust_env=False) as client:
        def fetch(label, endpoint, query):
            if replay is not None:
                captured = next(replay)
                if captured["label"] != label or captured["query"] != query:
                    raise ValueError("Replay query mismatch")
                report["replayed_requests"] += 1
                if "source" not in captured:
                    raise ValueError("Captured request failed")
                source = captured["source"]
                if source["source_url"] != "https://api.wallex.ir" + endpoint:
                    raise ValueError("Replay endpoint mismatch")
                raw = (ROOT / source["raw_file"]).read_bytes()
                if hashlib.sha256(raw).hexdigest() != source["raw_sha256"]:
                    raise ValueError("Replay raw hash mismatch")
                report["requests"].append(captured)
                return decode_json(raw), source
            if report["actual_gets"] >= plan["public_get_cap"]:
                raise ValueError("GET cap reached")
            time.sleep(plan["rate_spacing_seconds"])
            row = {"label": label, "query": query, "requested_at_utc": datetime.now(UTC).isoformat()}
            report["actual_gets"] += 1
            report["requests"].append(row)
            save()
            try:
                payload, source = fetch_public(client, endpoint, query, directory)
                row["source"] = source
                return payload, source
            except (ValueError, httpx.HTTPError) as exc:
                row["error_type"] = type(exc).__name__
                if isinstance(exc, httpx.HTTPStatusError):
                    row["http_status"] = exc.response.status_code
                raise
            finally:
                row["received_at_utc"] = datetime.now(UTC).isoformat()
                save()

        try:
            payload, report["catalog"] = fetch("catalog", "/hector/web/v1/markets", {})
            market = parse_catalog(payload)["USDTTMN"]
            denied = load_restrictions(ROOT / "config/wallex-credit-market-policy.json")
            if not market.is_spot or f"{market.base_asset}/{market.quote_asset}" in denied:
                raise ValueError("Source symbol is not eligible under existing policy")
            for diagnostic in plan["diagnostics"]:
                with suppress(ValueError, httpx.HTTPError):
                    fetch(diagnostic["label"], "/v1/udf/history", diagnostic["query"])
            parsed = []
            for day in range(start, end, 86400):
                row = {"start": day, "end": day + 86400, "status": "REJECTED"}
                items = []
                try:
                    payload, row["source"] = fetch("daily_native", "/v1/udf/history",
                        {"symbol": "USDTTMN", "resolution": "60", "from": day, "to": day + 86400})
                    parts = native_parts(payload, day, day + 86400, plan["cutoff"])
                    items = [{"candles": candles} for candles in parts]
                    if not items:
                        raise ValueError("No closed native data")
                    if day + 86400 in payload["t"] and day + 90000 <= plan["cutoff"]:
                        i = payload["t"].index(day + 86400)
                        tail = {k: [payload[k][i]] for k in ("t", "o", "h", "l", "c", "v")}
                        tail["s"] = "ok"
                        items[-1]["tail"] = parse_history(tail, start=day + 86400, end=day + 90000,
                            interval_seconds=3600, cutoff=plan["cutoff"]).candles[0]
                    count = sum(len(item["candles"]) for item in items)
                    present = {c.open_time for item in items for c in item["candles"]}
                    row.update(status="ACCEPTED" if count == 24 else "REJECTED", bars=count,
                               missing_hours=sorted(set(range(day, day + 86400, 3600)) - present),
                               partial_segments=len(items))
                except (ValueError, KeyError, httpx.HTTPError) as exc:
                    items = []
                    row["error_type"] = type(exc).__name__
                parsed.extend(items or [{}])
                report["days"].append(row)
                save()
            for candles in native_segments(parsed):
                normalized = {"symbol": "USDTTMN", "base_asset": market.base_asset,
                    "quote_asset": market.quote_asset, "interval_seconds": 3600,
                    "cutoff": candles[-1].open_time + 3600, "incomplete_bins": [],
                    "source_contract": plan["contract_id"],
                    "sources": [d["source"] for d in report["days"] if d.get("bars", 0)
                                and d["end"] > candles[0].open_time
                                and d["start"] < candles[-1].open_time + 3600],
                    "candles": [asdict(c) for c in candles]}
                raw = json.dumps(normalized, default=str, sort_keys=True).encode()
                digest = hashlib.sha256(raw).hexdigest()
                name = f"normalized-{digest}.json"
                (directory / name).write_bytes(raw)
                report["datasets"].append({"path": name, "sha256": digest, "symbol": "USDTTMN",
                    "interval_seconds": 3600, "start": candles[0].open_time,
                    "end": normalized["cutoff"], "status": "ACCEPTED",
                    "purpose": "SOURCE_ONLY_COVERAGE_NOT_SPLIT_PERMISSION",
                    "quality": {"contract_id": plan["contract_id"], "bars": len(candles),
                                "cross_resolution_verified": False}})
        except (ValueError, KeyError, httpx.HTTPError) as exc:
            report["error_type"] = type(exc).__name__
            report["datasets"] = []
    report["status"] = "SOURCE_CANDIDATES_REQUIRE_SEMANTIC_REVIEW" if report["datasets"] else "BLOCKED_DATA"
    report["finished_at_utc"] = datetime.now(UTC).isoformat()
    save()
    print(json.dumps({k: report[k] for k in ("run_id", "status", "actual_gets")}))
    return 0 if report["datasets"] else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--protocol", type=Path, default=ROOT / "config/historical-validation-protocol.json"
    )
    parser.add_argument("--source-plan", type=Path, help="Independent round-2 native-hour source plan")
    parser.add_argument("--replay-source-run", type=Path, help="Offline replay of immutable source capture")
    args = parser.parse_args(argv)
    if args.source_plan:
        return collect_native(args.source_plan, args.replay_source_run)
    if args.replay_source_run:
        parser.error("--replay-source-run requires --source-plan")
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
