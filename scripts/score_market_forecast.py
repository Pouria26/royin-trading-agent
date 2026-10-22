"""Record and score one real-model terminal-return forecast from a bounded probe trace.

The probe stores raw provider responses under ignored .local/. This tool re-validates the
model forecast against the recorded snapshot, then (after the horizon) fetches the public
1-minute close at cutoff+horizon and scores it. It never interpolates a missing outcome.
"""

import argparse
import json
import time
import urllib.request
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from royin.decision import ReturnForecast, validate_forecast
from royin.evaluation import score_return_forecasts, score_zero_baseline


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
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--record", action="store_true")
    parser.add_argument("--score", action="store_true")
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args(argv)
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
