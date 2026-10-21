"""Offline diagnostic candidate evaluation; never grants validation or shadow approval."""

import argparse
import hashlib
import json
import subprocess
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from royin.datasets import accepted_datasets
from royin.evaluation import evaluate_candidate_configurations, rank_and_select_candidate
from royin.market_data import decode_json
from royin.risk import RiskPolicy
from scripts.run_eval import get_default_market_rules

ROOT = Path(__file__).resolve().parents[1]


def evaluate_diagnostics(manifest_path, expected_sha256, plan_path):
    raw = Path(manifest_path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("Data manifest hash mismatch")
    plan_raw = Path(plan_path).read_bytes()
    plan = decode_json(plan_raw)
    if plan.get("schema_version") != 1 or len(plan["configurations"]) != 6:
        raise ValueError("Expected the six frozen research candidates")
    datasets = accepted_datasets(manifest_path)
    if not datasets:
        raise ValueError("No structurally accepted data")
    policy = plan["risk_policy"]
    summaries = []
    for path, data, candles, record in datasets:
        step = data["interval_seconds"]
        if step not in (900, 3600) or plan["windows_72h_duration_seconds"] != 259200:
            raise ValueError("Unsupported diagnostic horizon")
        bars = 259200 // step
        warmup = 31
        windows = []
        rules = get_default_market_rules(data["symbol"])
        if rules.taker_fee_rate != Decimal(plan["fees"]["taker_per_side"]):
            raise ValueError("Cost contract mismatch")
        for offset in range(0, len(candles) - warmup - bars + 1, bars):
            sample = candles[offset:offset + warmup + bars]
            start = sample[warmup].open_time
            end = sample[-1].open_time + step
            risk = RiskPolicy(Decimal(policy["max_order_tmn"]), Decimal(policy["max_exposure_tmn"]),
                              Decimal(policy["stop_loss_pct"]), Decimal(policy["max_drawdown_pct"]), end)
            result = evaluate_candidate_configurations(sample, rules, risk, plan["configurations"],
                interval_seconds=step, initial_capital=Decimal(policy["initial_capital_tmn"]),
                slippage_pct=Decimal(plan["execution"]["base_adverse_slippage"]),
                decision_latency_seconds=plan["execution"]["latency_seconds"], enable_logging=False)
            windows.append({"start": start, "end": end, "warmup_start": sample[0].open_time,
                            "role": "DIAGNOSTIC_EXPOSED_NOT_HOLDOUT", "results": result})
        best, ranking = rank_and_select_candidate([w["results"] for w in windows], plan["configurations"]) if windows else (None, [])
        summaries.append({"dataset_sha256": record["sha256"], "path": str(path),
                          "symbol": data["symbol"], "bars": len(candles), "interval_seconds": step,
                          "acceptance": record, "windows": windows,
                          "diagnostic_best_id": best, "diagnostic_ranking": ranking,
                          "timeframe_matches_frozen_plan": step == plan["evaluation_interval_seconds"],
                          "interpretation": "Same bar parameters on another timeframe are a different diagnostic; no formal split/selection"})
    return {"status": "INSUFFICIENT_EVIDENCE", "permitted_use": "DIAGNOSTIC_ONLY",
            "selected_candidate": None, "candidate_shadow_approved": False,
            "reason": "Source semantics and independent validation/holdout unverified; ranking is not acceptance",
            "data_manifest_sha256": expected_sha256,
            "plan_sha256": hashlib.sha256(plan_raw).hexdigest(),
            "rules_provenance": "Account-reported fees; tick/step/minimum/feeAsset synthetic, not live rules",
            "model_requests": 0, "public_gets": 0, "datasets": summaries}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--plan", type=Path, default=ROOT / "config/candidate-evaluation-plan.json")
    args = parser.parse_args(argv)
    result = evaluate_diagnostics(args.manifest, args.manifest_sha256, args.plan)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    directory = ROOT / "artifacts/candidate-evaluation" / run_id
    directory.mkdir(parents=True)
    result.update(run_id=run_id, created_at_utc=datetime.now(UTC).isoformat(),
                  revision=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                  dirty=bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()),
                  source_hashes={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in [Path(__file__), *sorted((ROOT / "src/royin").glob("*.py"))]})
    (directory / "manifest.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"run_id": run_id, "status": result["status"], "manifest": str(directory / "manifest.json"),
                      "windows": sum(len(d["windows"]) for d in result["datasets"]),
                      "candidate_shadow_approved": False}))
    return 0  # Successful diagnostic execution is not a passing strategy gate.


if __name__ == "__main__":
    raise SystemExit(main())
