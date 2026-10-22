"""Hash-bound OFFLINE market diagnostics and paid-pilot preparation; never paid execution."""

import argparse
import hashlib
import json
import subprocess
import uuid
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path

from pydantic_ai import models

from royin.datasets import load_dataset, validate_candles
from royin.evaluation import (
    RecordedPortfolioBlocked,
    portfolio_bindings,
    recorded_portfolio_producer,
    run_portfolio_ablation,
    run_simulation,
)
from royin.features import extract_features
from royin.market_data import Candle, CandleSeries, decimal_number, decode_json
from royin.markets import load_restrictions, parse_catalog
from royin.risk import MarketRules, RiskPolicy
from scripts.evaluate_portfolio_ai import fake_portfolio_producer

ROOT = Path(__file__).resolve().parents[1]


def checked_json(path, expected):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError(f"Hash mismatch: {Path(path).name}")
    return decode_json(raw)


def source_json(source, root):
    path = (root / source["raw_file"]).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Source path outside evidence root")
    fetched = datetime.fromisoformat(source["fetched_at_utc"])
    if fetched.utcoffset() is None or fetched > datetime.now(UTC):
        raise ValueError("Invalid source capture time")
    return checked_json(path, source["raw_sha256"])


def load_research_inputs(manifest_path, manifest_sha256, *, root=ROOT):
    """Reconcile normalized rows against every raw native source, retaining both segments."""
    manifest_path = Path(manifest_path)
    manifest = checked_json(manifest_path, manifest_sha256)
    if manifest.get("contract_id") != "WALLEX_NATIVE_60_SOURCE_V1":
        raise ValueError("Only the declared native source contract is supported")
    parent = checked_json(root / manifest["parent_capture_path"], manifest["parent_capture_sha256"])
    known_sources = {r["source"]["raw_sha256"]: r["source"] for r in parent["requests"]}
    catalog_source = manifest["catalog"]
    if (
        known_sources.get(catalog_source["raw_sha256"]) != catalog_source
        or catalog_source["source_url"] != "https://api.wallex.ir/hector/web/v1/markets"
    ):
        raise ValueError("Catalog capture lineage mismatch")
    catalog = parse_catalog(source_json(catalog_source, root))
    denied = load_restrictions(root / "config/wallex-credit-market-policy.json")
    datasets, all_times = [], set()
    for record in manifest["datasets"]:
        path = manifest_path.parent / record["path"]
        data, candles = load_dataset(path, record)
        market = catalog.get(data["symbol"])
        if (
            data["symbol"] != "USDTTMN"
            or data["interval_seconds"] != 3600
            or data.get("source_contract") != manifest["contract_id"]
            or not market
            or not market.is_spot
            or (market.base_asset, market.quote_asset) != ("USDT", "TMN")
            or "USDT/TMN" in denied
        ):
            raise ValueError("Research symbol/source/market policy mismatch")
        raw_rows = {}
        for source in data["sources"]:
            query = source["query"]
            if (
                known_sources.get(source["raw_sha256"]) != source
                or source["source_url"] != "https://api.wallex.ir/v1/udf/history"
                or query["symbol"] != "USDTTMN"
                or query["resolution"] != "60"
                or type(query["from"]) is not int
                or type(query["to"]) is not int
                or query["from"] >= query["to"]
            ):
                raise ValueError("Raw query/lineage mismatch")
            payload = source_json(source, root)
            arrays = [payload[k] for k in ("t", "o", "h", "l", "c", "v")]
            if (
                payload["s"] != "ok"
                or any(not isinstance(a, list) for a in arrays)
                or len({len(a) for a in arrays}) != 1
            ):
                raise ValueError("Invalid raw OHLCV arrays")
            previous = None
            for i, t in enumerate(payload["t"]):
                if (
                    type(t) is not int
                    or t % 3600
                    or not query["from"] <= t <= query["to"]
                    or (previous is not None and t <= previous)
                ):
                    raise ValueError("Raw time/cadence/order mismatch")
                previous = t
                c = Candle(
                    t,
                    *(
                        decimal_number(payload[k][i], positive=k != "v")
                        for k in ("o", "h", "l", "c", "v")
                    ),
                )
                validate_candles([c], 3600)
                if record["start"] <= t < record["end"] and t < query["to"]:
                    validate_candles(
                        [c],
                        3600,
                        now=int(datetime.fromisoformat(source["fetched_at_utc"]).timestamp()),
                    )
                    if t in raw_rows and raw_rows[t] != c:
                        raise ValueError("Conflicting raw overlap")
                    raw_rows[t] = c
        if candles != [raw_rows[t] for t in sorted(raw_rows)]:
            raise ValueError("Normalized rows differ from complete raw coverage")
        times = {c.open_time for c in candles}
        if times & all_times:
            raise ValueError("Duplicate/overlapping diagnostic segments")
        all_times |= times
        datasets.append((record, data, candles))
    if not datasets or sum(len(c) for _, _, c in datasets) > 10000:
        raise ValueError("Missing or excessive diagnostic coverage")
    datasets.sort(key=lambda item: item[2][0].open_time)
    return manifest, datasets


def validate_assumptions(plan):
    required = {
        "binding_stage": "TEMPORARY_LOGIC_ONLY_NOT_FINAL_FREEZE",
        "purpose": "DIAGNOSTIC_EXPOSED_NOT_HOLDOUT",
        "ai_role": "FULL_DECISION_PROPOSAL_NOT_VETO",
        "time_label_assumption": "INTERVAL_START_UNVERIFIED",
        "finality_assumption": "CAPTURED_CLOSED_NOT_EXCHANGE_FINALITY",
        "price_unit": "TMN_PER_USDT",
        "volume_asset_assumption": "BASE_USDT_UNVERIFIED_DIAGNOSTIC",
    }
    if any(plan.get(k) != v for k, v in required.items()):
        raise ValueError("Explicit diagnostic role/time/price/volume assumptions required")
    instant = datetime.fromisoformat(plan["registered_at_utc"])
    if instant.utcoffset() is None or instant > datetime.now(UTC):
        raise ValueError("Invalid diagnostic registration timestamp")
    for key in (
        "initial_capital_tmn",
        "max_order_tmn",
        "max_exposure_tmn",
        "stop_loss_pct",
        "max_drawdown_pct",
    ):
        decimal_number(plan[key], positive=True)
    if (
        not 0 < decimal_number(plan["stop_loss_pct"]) < 1
        or not 0 < decimal_number(plan["max_drawdown_pct"]) < 1
    ):
        raise ValueError("Risk scenario must be a fraction")
    if len(plan["cost_scenarios"]) != 2 or {c["name"] for c in plan["cost_scenarios"]} != {
        "base",
        "higher_cost",
    }:
        raise ValueError("Exactly the registered base and higher_cost scenarios required")
    for scenario in plan["cost_scenarios"]:
        if (
            not 0 <= decimal_number(scenario["taker_fee"]) < 1
            or not 0 <= decimal_number(scenario["slippage"]) < 1
        ):
            raise ValueError("Invalid fee/slippage fraction")
    for key in ("tick_size", "step_size", "min_quantity", "min_notional"):
        decimal_number(plan["synthetic_market_rules"][key], positive=True)


def scenario_rules(plan, scenario):
    r = plan["synthetic_market_rules"]
    fee = decimal_number(scenario["taker_fee"])
    return MarketRules(
        "USDTTMN",
        "USDT",
        "TMN",
        *(decimal_number(r[k]) for k in ("tick_size", "step_size", "min_notional", "min_quantity")),
        fee,
        fee,
    )


def quality_status(record, candles):
    return {
        "sha256": record["sha256"],
        "structural_quality": "PASS_RAW_RECONCILED",
        "time_semantics": "INTERVAL_START_ASSUMED_NOT_ATTESTED",
        "finality": "UNKNOWN",
        "volume_asset": "UNKNOWN; base USDT assumed only for diagnostic fill condition",
        "feature_use": "PROVISIONAL_NATIVE_PRICE_AND_RELATIVE_VOLUME_ONLY",
        "financial_claim_limit": "CONDITIONAL_SCENARIO_ONLY_NOT_SELECTION_OR_APPROVAL",
        "role": "DEVELOPMENT_EXPOSED_NOT_HOLDOUT",
        "bars": len(candles),
        "start": candles[0].open_time,
        "end": candles[-1].open_time + 3600,
        "account_market_permission": "UNVERIFIED; public spot catalog and unchanged denylist only",
    }


def load_real_lineage(path, expected_sha256, *, root=None):
    """Independent review receipt pins sanitized provider response bytes; no network access."""
    path = Path(path)
    root = path.parent if root is None else Path(root)
    manifest = checked_json(path, expected_sha256)
    if manifest.get("review_status") != "INDEPENDENTLY_REVIEWED" or not manifest.get(
        "reviewer_ref"
    ):
        raise ValueError("Independent REAL_MODEL lineage review required")
    proofs = {}
    for entry in manifest["responses"]:
        response_path = (root / entry["response_file"]).resolve()
        request_path = (root / entry["request_file"]).resolve()
        if not response_path.is_relative_to(root.resolve()) or entry["response_sha256"] in proofs:
            raise ValueError("Invalid/duplicate lineage path")
        if not request_path.is_relative_to(root.resolve()):
            raise ValueError("Request path outside evidence root")
        response = checked_json(response_path, entry["response_sha256"])
        requests = checked_json(request_path, entry["request_sha256"])
        if not isinstance(requests, list) or len(requests) != 2:
            raise ValueError("Two captured Chat Completions bodies required")
        expected = entry["request"]
        for request in requests:
            messages = request["messages"]
            if (
                request.get("model") != entry["manifest"]["model"]
                or request.get("reasoning_effort") != "none"
                or request.get("max_completion_tokens", request.get("max_tokens")) != 512
                or not any(
                    m.get("role") in ("system", "developer")
                    and m.get("content") == expected["system_instructions"]
                    for m in messages
                )
                or not any(
                    m.get("role") == "user" and m.get("content") == expected["user_prompt"]
                    for m in messages
                )
            ):
                raise ValueError("Captured model/request/prompt settings mismatch")
        messages = requests[-1]["messages"]
        tool_returns = [m for m in messages if m.get("role") == "tool"]
        tool_calls = [c for m in messages for c in m.get("tool_calls", [])]
        if (
            len(tool_returns) != 1
            or len(tool_calls) != 1
            or tool_calls[0]["function"]["name"] != "read_market_snapshot"
            or tool_calls[0]["id"] != tool_returns[0]["tool_call_id"]
            or decode_json(tool_returns[0]["content"]) != expected["snapshot"]
        ):
            raise ValueError("Captured tool snapshot/identity mismatch")
        proofs[entry["response_sha256"]] = {
            **entry,
            "response": response,
            "request_capture_verified": True,
            "review_status": manifest["review_status"],
        }
    return proofs


def diagnostic_report(
    manifest_path, manifest_sha256, plan_path, *, root=ROOT, records=None, real_lineage=None
):
    plan_raw = Path(plan_path).read_bytes()
    plan = decode_json(plan_raw)
    validate_assumptions(plan)
    manifest, datasets = load_research_inputs(manifest_path, manifest_sha256, root=root)
    summaries, before = [], None
    old_requests = models.ALLOW_MODEL_REQUESTS
    models.ALLOW_MODEL_REQUESTS = False
    try:
        for record, data, candles in datasets:
            results = {}
            for cost in plan["cost_scenarios"]:
                rules = scenario_rules(plan, cost)
                policy = RiskPolicy(
                    *(
                        decimal_number(plan[k])
                        for k in (
                            "max_order_tmn",
                            "max_exposure_tmn",
                            "stop_loss_pct",
                            "max_drawdown_pct",
                        )
                    ),
                    data["cutoff"],
                )
                initial, slip = (
                    decimal_number(plan["initial_capital_tmn"]),
                    decimal_number(cost["slippage"]),
                )
                bindings = portfolio_bindings(candles, rules, policy, initial, 3600, slip)
                bindings.update(
                    research_plan_sha256=hashlib.sha256(plan_raw).hexdigest(),
                    source_manifest_sha256=manifest_sha256,
                    normalized_raw_sha256=record["sha256"],
                    binding_stage=plan["binding_stage"],
                )
                before = before or bindings["code_sha256"]
                if bindings["code_sha256"] != before:
                    raise ValueError("Source changed during diagnostic run")
                fake_records = []
                fake = fake_portfolio_producer(fake_records, bindings)
                arms = run_portfolio_ablation(
                    candles,
                    rules,
                    policy,
                    fake,
                    initial_capital=initial,
                    slippage_pct=slip,
                    source="FAKE_MODEL",
                )
                fake_result = arms["rule_ai"]
                arms["rule_ai"] = {
                    "status": "BLOCKED_RECORDED_AI",
                    "equity_curve": None,
                    "net_return_pct": None,
                    "reason": "No reviewed exact own-ledger REAL_MODEL records",
                }
                if records:
                    matching = [
                        r
                        for r in records
                        if r["manifest"].get("data_sha256") == bindings["data_sha256"]
                        and r["manifest"].get("config_sha256") == bindings["config_sha256"]
                    ]
                    producer = recorded_portfolio_producer(
                        matching, bindings, source="REAL_MODEL", real_lineage=real_lineage
                    )
                    try:
                        real = run_simulation(
                            candles,
                            producer,
                            rules,
                            policy,
                            initial_capital=initial,
                            interval_seconds=3600,
                            slippage_pct=slip,
                            enable_logging=False,
                            decision_source="REAL_MODEL_REPLAY",
                        )
                    except RecordedPortfolioBlocked:
                        arms["rule_ai"]["reason"] = (
                            "Reviewed records do not cover evolving arm state; no partial curve published"
                        )
                    else:
                        arms["rule_ai"] = real
                results[cost["name"]] = {
                    "bindings": bindings,
                    "arms": arms,
                    "fake_wiring_arm": fake_result,
                    "fake_model_records": fake_records,
                    "fake_warning": "SDK TestModel on real market prices; NOT real AI performance",
                }
            summaries.append(
                {
                    "quality": quality_status(record, candles),
                    "source_queries": data["sources"],
                    "cost_scenarios": results,
                }
            )
        after = portfolio_bindings(candles, rules, policy, initial, 3600, slip)["code_sha256"]
        if after != before:
            raise ValueError("Source changed during diagnostic run")
    finally:
        models.ALLOW_MODEL_REQUESTS = old_requests
    gaps = [
        {"start": a[2][-1].open_time + 3600, "end": b[2][0].open_time}
        for a, b in pairwise(datasets)
        if a[2][-1].open_time + 3600 != b[2][0].open_time
    ]
    return {
        "status": "COMPLETE_DIAGNOSTIC_ONLY",
        "primary_status": "BLOCKED_DATA",
        "binding_stage": plan["binding_stage"],
        "selected_candidate": None,
        "ai_role": plan["ai_role"],
        "datasets": summaries,
        "gaps_preserved": gaps,
        "out_of_sample_performance": None,
        "independent_exposures": None,
        "source_manifest_sha256": manifest_sha256,
        "plan_sha256": hashlib.sha256(plan_raw).hexdigest(),
        "source_contract": manifest["contract_id"],
        "public_gets": 0,
        "paid_requests": 0,
        "provider_usage": None,
        "invoice": None,
        "global_budget_modified": False,
        "interpretation": "Conditional OHLC scenario on exposed market history; no prediction/edge/strategy acceptance",
    }


def prepare_pilot(manifest_path, manifest_sha256, plan_path, *, root=ROOT):
    plan = decode_json(Path(plan_path).read_bytes())
    validate_assumptions(plan)
    _, datasets = load_research_inputs(manifest_path, manifest_sha256, root=root)
    record, _, candles = datasets[0]
    # First twelve decision cutoffs, fixed before any new paid outcome, with 31-bar context.
    sample = candles[:43]
    if len(sample) != 43:
        raise ValueError("Pilot requires 31 context bars, twelve cutoffs and a final execution bar")
    cost = next(c for c in plan["cost_scenarios"] if c["name"] == "base")
    rules = scenario_rules(plan, cost)
    policy = RiskPolicy(
        *(
            decimal_number(plan[k])
            for k in ("max_order_tmn", "max_exposure_tmn", "stop_loss_pct", "max_drawdown_pct")
        ),
        sample[-1].open_time + 3600,
    )
    bindings = portfolio_bindings(
        sample,
        rules,
        policy,
        decimal_number(plan["initial_capital_tmn"]),
        3600,
        decimal_number(cost["slippage"]),
    )
    snapshot = extract_features(
        CandleSeries(tuple(sample[:31]), 3600),
        "USDTTMN",
        cutoff=sample[30].open_time + 3600,
        available_tmn_cash=decimal_number(plan["initial_capital_tmn"]),
    )
    return {
        "status": "PROPOSAL_ONLY_NOT_AUTHORIZED",
        "binding_stage": plan["binding_stage"],
        "source_manifest_sha256": manifest_sha256,
        "dataset_sha256": record["sha256"],
        "bindings": bindings,
        "sample_window": {
            "start": sample[0].open_time,
            "end": sample[-1].open_time + 3600,
            "bars": 43,
        },
        "plan_sha256": hashlib.sha256(Path(plan_path).read_bytes()).hexdigest(),
        "final_freeze_required": True,
        "ai_role": plan["ai_role"],
        "requested_model": "gpt-6-luna",
        "provider": "boxapi",
        "reasoning": "none",
        "first_snapshot": snapshot.to_canonical_dict(),
        "first_snapshot_sha256": snapshot.snapshot_sha256,
        "decision_cutoffs": [c.open_time + 3600 for c in sample[30:42]],
        "maximum_decisions": 12,
        "maximum_http_requests": 24,
        "maximum_reserved_usd": "0.04",
        "per_decision_deadline_seconds": 30,
        "overall_deadline_seconds": 600,
        "output_token_cap": 512,
        "maximum_read_tools_per_decision": 1,
        "automatic_retries": 0,
        "execution": "sequential offline ledger advances on next eligible bar; cash/position recomputed after each fill, no fixed hypothetical state",
        "schedule": "After both agents stop, integration checks/final freeze and explicit user choice; sequential historical cutoffs, not live trading",
        "recording": "Capture sanitized request/tool/final completion bytes, their SHA256, model metadata, SDK usage and linked decision. Independent lineage review required before REAL replay",
        "stop_on": [
            "source/binding/input mismatch",
            "missing required capture",
            "budget/deadline cap",
            "provider/schema/domain error",
            "storage/audit error",
        ],
        "global_budget": "Existing durable ledger, no refund/reset; reservation/SDK usage/invoice separate",
        "limitation": "Exposed diagnostic data and assumed semantics; twelve decisions test compatibility/recording only, not OOS or durable profitability",
        "paid_requests": 0,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--assumptions", type=Path, required=True)
    parser.add_argument("--mode", choices=("diagnostic", "prepare-pilot"), default="diagnostic")
    parser.add_argument("--records", type=Path)
    parser.add_argument("--records-sha256")
    parser.add_argument("--lineage-manifest", type=Path)
    parser.add_argument("--lineage-sha256")
    parser.add_argument("--out-root", type=Path, default=ROOT / "artifacts/research-portfolio")
    args = parser.parse_args(argv)
    try:
        if any(
            (args.records, args.records_sha256, args.lineage_manifest, args.lineage_sha256)
        ) and not all(
            (args.records, args.records_sha256, args.lineage_manifest, args.lineage_sha256)
        ):
            raise ValueError("Records and independent lineage files require explicit SHA256")
        if args.mode == "prepare-pilot":
            report = prepare_pilot(args.manifest, args.manifest_sha256, args.assumptions)
        else:
            records = checked_json(args.records, args.records_sha256) if args.records else None
            lineage = (
                load_real_lineage(args.lineage_manifest, args.lineage_sha256)
                if args.records
                else None
            )
            report = diagnostic_report(
                args.manifest,
                args.manifest_sha256,
                args.assumptions,
                records=records,
                real_lineage=lineage,
            )
        directory = args.out_root / (
            datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
        )
        directory.mkdir(parents=True, exist_ok=False)
        report.update(
            created_at_utc=datetime.now(UTC).isoformat(),
            revision=subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            dirty=bool(
                subprocess.check_output(
                    ["git", "status", "--porcelain"], cwd=ROOT, text=True
                ).strip()
            ),
        )
        path = directory / "manifest.json"
        path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf8")
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "manifest": str(path),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "paid_requests": 0,
                }
            )
        )
        return 0
    except (ValueError, KeyError, OSError) as exc:
        print(
            json.dumps(
                {
                    "status": "BLOCKED_RESEARCH_INPUT",
                    "error_type": type(exc).__name__,
                    "reason": str(exc),
                }
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
