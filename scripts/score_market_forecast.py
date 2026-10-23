"""Record and score real-model terminal-return forecasts from bounded recorded traces.

The probe stores raw provider responses under ignored .local/. This tool re-validates the
model forecast against the recorded snapshot, then (after the horizon) fetches the public
1-minute close at cutoff+horizon and scores it. It never interpolates a missing outcome.
"""

import argparse
import hashlib
import json
import time
import urllib.request
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from royin.decision import ReturnForecast, validate_forecast
from royin.evaluation import score_return_forecasts, score_zero_baseline, source_bundle_sha256
from royin.market_data import decode_json, parse_history
from royin.model_profiles import matches_provider_model


def current_forecasts(manifest_path):
    """Verify issued forecasts against their snapshot, batch and actual provider output."""
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw)
    if manifest.get("mode") != "CURRENT_PAPER" or manifest.get("model_mode") != "REAL_MODEL":
        raise ValueError("Current forecast scoring requires an explicit real-model current run")
    sha = hashlib.sha256(raw).hexdigest()
    records, skipped = [], []
    for index, row in enumerate(manifest["arms"]["paper_portfolio"]["decision_traces"]):
        decision = row["decision"]
        if decision.get("forecast") is None:
            skipped.append(dict(run_id=manifest["run_id"],trace_index=index,reason="NO_ISSUED_MODEL_FORECAST"))
            continue
        issued_at = datetime.fromisoformat(row.get("issued_at_utc", manifest["created_at_utc"]).replace("Z","+00:00"))
        manifest_at = datetime.fromisoformat(manifest["created_at_utc"].replace("Z","+00:00"))
        if issued_at.utcoffset() is None or manifest_at.utcoffset() is None or issued_at > manifest_at:
            raise ValueError("Invalid recorded issuance timestamp")
        model = row.get("model_trace") or {}
        if (model.get("host_outcome") != "MODEL_DECISION" or model.get("evidence_kind") != "REAL_MODEL_ATTEMPT"
                or not matches_provider_model(model.get("provider"),model.get("model")) or not model.get("responses")):
            raise ValueError("Forecast lacks a successful real-provider trace")
        snapshot = row["snapshot"]
        snapshot_sha = hashlib.sha256(json.dumps(snapshot,sort_keys=True,separators=(",",":")).encode()).hexdigest()
        if row["snapshot_sha256"] != snapshot_sha or decision["snapshot_sha256"] != snapshot_sha:
            raise ValueError("Recorded snapshot hash mismatch")
        context = model["context"]
        if context["cutoff"] != snapshot["cutoff"]:
            raise ValueError("Model context cutoff mismatch")
        if context.get("candidates") is not None:
            batch_sha = hashlib.sha256(json.dumps(context["candidates"],sort_keys=True,separators=(",",":")).encode()).hexdigest()
            if batch_sha != context["batch_sha256"]:
                raise ValueError("Recorded market batch hash mismatch")
            chosen = [c for c in context["candidates"] if c["symbol"] == decision["symbol"]]
            if len(chosen) != 1 or chosen[0]["snapshot_sha256"] != snapshot_sha:
                raise ValueError("Forecast is outside the recorded model batch")
        elif context.get("snapshot_sha256") != snapshot_sha:
            raise ValueError("Single-snapshot context mismatch")
        response = model["responses"][-1]
        if response["status_code"] != 200:
            raise ValueError("Provider response was not successful")
        output = decode_json(response["body"])["choices"][0]["message"].get("tool_calls",[])
        finals = [json.loads(t["function"]["arguments"]) for t in output if t["function"]["name"] == "final_result"]
        if len(finals) != 1:
            raise ValueError("Missing unique structured provider result")
        forecast = ReturnForecast.model_validate(decision["forecast"])
        if (ReturnForecast.model_validate(finals[0]["forecast"]) != forecast
                or finals[0]["action"] != decision["action"]
                or (finals[0]["symbol"] != decision["symbol"] and not (decision["action"] == "WAIT" and finals[0]["symbol"] is None))
                or finals[0]["snapshot_sha256"] != snapshot_sha or model["decision"]["forecast"] != decision["forecast"]):
            raise ValueError("Host/provider forecast identity mismatch")
        bounds = context.get("horizon_bounds",[300,36000])
        validate_forecast(forecast,snapshot=SimpleNamespace(symbol=snapshot["symbol"],cutoff=snapshot["cutoff"],
            last_close=Decimal(snapshot["last_close"]),evidences=snapshot["evidences"]),
            horizon_min_seconds=bounds[0],horizon_max_seconds=bounds[1])
        if decision["symbol"] != forecast.symbol or decision["cutoff"] != forecast.cutoff:
            raise ValueError("Decision/forecast identity mismatch")
        if not forecast.cutoff <= issued_at.timestamp() < forecast.cutoff+forecast.horizon_seconds:
            raise ValueError("No recorded pre-outcome issuance evidence")
        records.append(dict(run_id=manifest["run_id"],trace_index=index,manifest_sha256=sha,
            scoring_id=f"{sha}:{index}:{forecast.forecast_id}",action=decision["action"],forecast=forecast,
            provider_response_sha256=hashlib.sha256(response["body"].encode()).hexdigest(),
            prompt_sha256=model["prompt_sha256"],model=model["model"],issued_before_outcome=True,
            status="PENDING",source_code_sha256=manifest["bindings"]["code_sha256"]))
    return sha,records,skipped


def terminal_close(payload, forecast, now):
    """Exact one-minute terminal bar under the documented local open-time assumption."""
    end = forecast.cutoff+forecast.horizon_seconds
    if now < end+60:
        raise ValueError("Outcome has not matured")
    series = parse_history(payload,start=end-60,end=end,interval_seconds=60,cutoff=now)
    if len(series.candles) != 1:
        raise ValueError("No exact closed terminal minute")
    return series.candles[0].close


def score_current(manifest_paths, output_dir=None, *, now=None):
    """No key/model/order; at most32 outcome GETs, no retries and no source mutation."""
    import uuid
    now = int(time.time()) if now is None else now
    if type(now) is not int or now < 0:
        raise ValueError("Invalid scoring clock")
    paths = [Path(p).resolve() for p in manifest_paths]
    if not paths or len(paths) > 32 or len(set(paths)) != len(paths):
        raise ValueError("Supply1..32 distinct source manifests")
    records, skipped, hashes = [], [], {}
    for path in paths:
        sha,items,omitted = current_forecasts(path)
        if sha in hashes.values():
            raise ValueError("Duplicate manifest content cannot count as a fresh observation")
        hashes[str(path)] = sha
        records.extend(items)
        skipped.extend(omitted)
    response_hashes = [r["provider_response_sha256"] for r in records]
    if len(set(response_hashes)) != len(response_hashes):
        raise ValueError("Duplicate provider results cannot count as fresh forecast observations")
    queries = {(r["forecast"].symbol,r["forecast"].cutoff+r["forecast"].horizon_seconds)
               for r in records if now >= r["forecast"].cutoff+r["forecast"].horizon_seconds+60}
    if len(queries) > 32:
        raise ValueError("Outcome GET allowance exceeded before I/O")
    output = Path(output_dir) if output_dir else Path("artifacts/forecast-outcomes")/(datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")+"_"+uuid.uuid4().hex[:8])
    output.mkdir(parents=True,exist_ok=False)
    source_root = Path(__file__).resolve().parents[1]
    scoring_code_sha256 = source_bundle_sha256(source_root,[Path(__file__),*source_root.glob("src/royin/*.py"),source_root/"requirements.lock"])
    outcomes, cache, gets = {}, {}, 0
    for row in records:
        f = row["forecast"]
        end = f.cutoff+f.horizon_seconds
        if now < end+60:
            continue
        if end % 60:
            row["status"] = "UNSUPPORTED_SUBMINUTE_HORIZON"
            outcomes[row["scoring_id"]] = None
            continue
        key = (f.symbol,end)
        if key not in cache:
            gets += 1
            request = urllib.request.Request("https://api.wallex.ir/v1/udf/history?"
                f"symbol={f.symbol}&resolution=1&from={end-60}&to={end}",headers={"User-Agent":"royin-forecast-outcome"})
            try:
                with urllib.request.urlopen(request,timeout=15) as response:
                    raw = response.read(4_000_001)
                if len(raw) > 4_000_000:
                    raise ValueError("Outcome response exceeds size limit")
                sha = hashlib.sha256(raw).hexdigest()
                (output/(sha+".json")).write_bytes(raw)
                close = terminal_close(decode_json(raw),f,now)
                cache[key] = dict(close=close,capture_sha256=sha,status="SCORED")
            except (OSError,ValueError,KeyError,TypeError) as exc:
                cache[key] = dict(status="MISSING_OR_INVALID_OUTCOME",error_type=type(exc).__name__)
        observation = cache[key]
        row.update(observation)
        if row["status"] == "SCORED":
            outcomes[row["scoring_id"]] = observation["close"]/f.reference_price-Decimal(1)
            row["outcome_return"] = outcomes[row["scoring_id"]]
        else:
            outcomes[row["scoring_id"]] = None
    scores = score_return_forecasts([{**r["forecast"].model_dump(),"forecast_id":r["scoring_id"]} for r in records],outcomes)
    baseline = score_zero_baseline([r["outcome"] for r in scores["rows"]]) if scores["scored"] else None
    for path in paths:
        if hashlib.sha256(path.read_bytes()).hexdigest() != hashes[str(path)]:
            raise ValueError("A source manifest changed during outcome scoring")
    report = dict(status="COMPLETE_FORECAST_DIAGNOSTIC" if records and scores["scored"]==len(records) else "PARTIAL_FORECAST_DIAGNOSTIC",
        created_at_utc=datetime.now(UTC).isoformat(),scoring_clock=now,actual_gets=gets,max_gets=32,
        scoring_code_sha256=scoring_code_sha256,policy="EXACT_TERMINAL_MINUTE_DIAGNOSTIC_V1",
        source_manifests=hashes,records=records,skipped_decisions=skipped,scores=scores,zero_point_baseline=baseline,
        limits=["Terminal price forecast, not a fill, executable profit, strategy win rate or calibration proof",
                "One-minute timestamps are interpreted as bar opens; source semantics remain diagnostic",
                "Repeated same-session observations are correlated; no independent holdout claim",
                "Source/prompt revisions may differ; this is not a controlled model comparison",
                "No baseline interval is fitted on these evaluation outcomes"])
    with (output/"report.json").open("x",encoding="utf-8") as out:
        json.dump(report,out,default=lambda x:x.model_dump(mode="json") if isinstance(x,ReturnForecast) else str(x),indent=2)
    print(json.dumps(dict(status=report["status"],issued=len(records),scored=scores["scored"],pending=scores["pending"],
                         missing=scores["missing_outcome"],actual_gets=gets,report=str(output/"report.json"))))
    return 0 if report["status"] == "COMPLETE_FORECAST_DIAGNOSTIC" else 2


def load_proposal(run_dir):
    trace = json.loads((run_dir / "trace.json").read_text(encoding="utf-8"))
    body = json.loads(trace["responses"][-1]["body"])
    arguments = body["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"]
    return json.loads(arguments)


def load_snapshot(run_dir, symbol):
    rows = json.loads((run_dir / "batch.json").read_text(encoding="utf-8"))
    for row in rows:
        if row["symbol"] == symbol:
            return row
    raise ValueError("Chosen symbol is not in the recorded batch")


def record(run_dir):
    proposal = load_proposal(run_dir)
    forecast = ReturnForecast(**proposal["forecast"])
    row = load_snapshot(run_dir, forecast.symbol)
    snapshot = SimpleNamespace(
        symbol=forecast.symbol, cutoff=forecast.cutoff,
        last_close=Decimal(row["snapshot"]["last_close"]),
        evidences=row["snapshot"]["evidences"],
    )
    validate_forecast(forecast, snapshot=snapshot, horizon_min_seconds=600, horizon_max_seconds=1800)
    payload = {
        "run_id": run_dir.name,
        "action": proposal["action"],
        "decision_symbol": proposal["symbol"],
        "forecast": forecast.model_dump(mode="json"),
        "reference_price": row["snapshot"]["last_close"],
        "outcome_at": forecast.cutoff + forecast.horizon_seconds,
        "status": "PENDING",
        "profile": "PUBLIC_MARKET_PAPER",
    }
    (run_dir / "forecast.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return payload


def fetch_close(symbol, at):
    start = at - 120
    request = urllib.request.Request(
        "https://api.wallex.ir/v1/udf/history?"
        f"symbol={symbol}&resolution=1&from={start}&to={at}",
        headers={"User-Agent": "royin-forecast-outcome"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = json.loads(response.read(2_000_000))
    if payload.get("s") != "ok":
        raise ValueError("History unavailable")
    pairs = list(zip(payload["t"], payload["c"], strict=False))
    for stamp, close in pairs:
        if stamp == at - 60:
            return Decimal(close)
    return None


def score(run_dir):
    payload = json.loads((run_dir / "forecast.json").read_text(encoding="utf-8"))
    forecast = ReturnForecast(**payload["forecast"])
    now = int(time.time())
    if now < forecast.cutoff + forecast.horizon_seconds + 60:
        print(json.dumps({"status": "PENDING", "seconds_left": forecast.cutoff + forecast.horizon_seconds - now}))
        return 1
    close = fetch_close(forecast.symbol, forecast.cutoff + forecast.horizon_seconds)
    if close is None:
        payload["status"] = "MISSING_OUTCOME"
        (run_dir / "forecast.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(json.dumps({"status": "MISSING_OUTCOME", "symbol": forecast.symbol}))
        return 2
    outcome_return = (close / forecast.reference_price) - Decimal(1)
    scores = score_return_forecasts([forecast], {forecast.forecast_id: outcome_return})
    baseline = score_zero_baseline([outcome_return])
    payload.update(status="SCORED", outcome_price=str(close), outcome_return=str(outcome_return),
                   scores=json.loads(json.dumps(scores, default=str)),
                   zero_baseline=json.loads(json.dumps(baseline, default=str)))
    (run_dir / "forecast.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    summary = {
        "run_id": run_dir.name, "symbol": forecast.symbol,
        "horizon_seconds": forecast.horizon_seconds,
        "reference_price": str(forecast.reference_price), "outcome_price": str(close),
        "outcome_return": str(outcome_return),
        "q10": str(forecast.return_q10), "q50": str(forecast.return_q50), "q90": str(forecast.return_q90),
        "abs_error_q50": str(scores["median_abs_error"]),
        "coverage": str(scores["coverage"]), "winkler": str(scores["mean_winkler"]),
        "zero_baseline": {k: str(v) for k, v in baseline.items() if k != "q10" and k != "q90"},
    }
    print(json.dumps(summary, indent=2))
    return 0


def replay(run_dir):
    """Recompute hashes and re-validate the recorded forecast without any network call."""
    import hashlib

    trace = json.loads((run_dir / "trace.json").read_text(encoding="utf-8"))
    proposal = load_proposal(run_dir)
    rows = json.loads((run_dir / "batch.json").read_text(encoding="utf-8"))
    by_symbol = {row["symbol"]: row for row in rows}
    chosen = proposal["symbol"]
    if chosen not in by_symbol:
        raise ValueError("Replay: chosen symbol missing from recorded batch")
    row = by_symbol[chosen]
    checks = {
        "proposal_snapshot_hash": proposal["snapshot_sha256"] == row["snapshot_sha256"],
        "proposal_opportunity_hash": proposal["opportunity_sha256"] == row["opportunity_sha256"],
        "proposal_cutoff": proposal["cutoff"] == row["snapshot"]["cutoff"],
        "batch_sha256": hashlib.sha256(json.dumps(
            trace["context"]["candidates"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        == trace["context"]["batch_sha256"],
    }
    forecast = ReturnForecast(**proposal["forecast"])
    snapshot = SimpleNamespace(symbol=forecast.symbol, cutoff=forecast.cutoff,
                               last_close=Decimal(row["snapshot"]["last_close"]),
                               evidences=row["snapshot"]["evidences"])
    validate_forecast(forecast, snapshot=snapshot, horizon_min_seconds=600, horizon_max_seconds=1800)
    checks["forecast_bound"] = True
    payload = {"run_id": run_dir.name, "status": "PASS" if all(checks.values()) else "FAIL",
               "checks": checks, "forecast_id": forecast.forecast_id}
    (run_dir / "replay.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if payload["status"] == "PASS" else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sources = parser.add_mutually_exclusive_group(required=True)
    sources.add_argument("--run-dir")
    sources.add_argument("--paper-manifest",nargs="+",type=Path)
    parser.add_argument("--output-dir",type=Path)
    parser.add_argument("--record", action="store_true")
    parser.add_argument("--score", action="store_true")
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args(argv)
    if args.paper_manifest:
        if not args.score or args.record or args.replay:
            parser.error("Paper manifests require --score alone")
        try:
            return score_current(args.paper_manifest,args.output_dir)
        except (OSError,ValueError,KeyError,TypeError) as exc:
            print(json.dumps(dict(status="BLOCKED_FORECAST_INPUT",error_type=type(exc).__name__)))
            return 2
    run_dir = Path(args.run_dir)
    if args.record:
        record(run_dir)
        return 0
    if args.score:
        return score(run_dir)
    if args.replay:
        return replay(run_dir)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
