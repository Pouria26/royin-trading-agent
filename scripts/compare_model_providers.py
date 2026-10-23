"""Compare real provider role decisions on fixed recorded inputs, without exchange access.

This diagnoses operational fitness. It does not rank realized returns or establish an edge.
"""

import argparse
import asyncio
import hashlib
import json
import re
import statistics
from decimal import Decimal
from pathlib import Path

from royin.agent import RoleRunEnvelope, decide_role
from royin.config import RuntimeConfig
from royin.decision import EntryOpportunityContext, PositionReviewContext
from royin.evaluation import source_bundle_sha256
from royin.features import FeatureSnapshot
from royin.model_budget import BudgetBlocked, ModelBudget
from royin.model_profiles import PROVIDER_MODELS, PROVIDER_ORIGINS

ROOT = Path(__file__).resolve().parents[1]
DECIMALS = ("last_close","trend_sma_fast","trend_sma_slow","rsi_14","atr_14","volume_ratio",
            "current_position_base","available_tmn_cash")


def load_cases(path):
    raw = path.read_bytes()
    if len(raw) > 2_000_000:
        raise ValueError("Recorded case input exceeds size bound")
    packet = json.loads(raw)
    if packet.get("evidence_kind") != "RECORDED_PUBLIC_ROLE_CASES":
        raise ValueError("Explicit public recorded-input case packet required")
    cases = packet["cases"]
    if not isinstance(cases,list) or not 2 <= len(cases) <= 12:
        raise ValueError("Comparison requires 2..12 predeclared cases")
    names = set()
    parsed = []
    for case in cases:
        name = case["case_id"]
        if not isinstance(name,str) or not re.fullmatch(r"[a-zA-Z0-9_.-]{1,64}",name) or name in names:
            raise ValueError("Case IDs must be unique and bounded")
        names.add(name)
        source = case["snapshot"]
        snap = FeatureSnapshot(**{**source,**{key:Decimal(source[key]) for key in DECIMALS},
            "snapshot_sha256":case["snapshot_sha256"]})
        if not snap.verify_hash():
            raise ValueError("Recorded feature snapshot hash mismatch")
        position = (PositionReviewContext.model_validate_json(json.dumps(case["position"]))
                    if case.get("position") else None)
        opportunity = (EntryOpportunityContext.model_validate_json(json.dumps(case["opportunity"]))
                       if case.get("opportunity") else None)
        if (snap.current_position_base > 0) != (position is not None) or (position is None) == (opportunity is None):
            raise ValueError("Each case must have exactly its own entry or position context")
        parsed.append((name,snap,position,opportunity))
    if not any(pos for _,_,pos,_ in parsed) or not any(opp for _,_,_,opp in parsed):
        raise ValueError("Both entry and position cases are required")
    return hashlib.sha256(raw).hexdigest(),parsed


def provider_config(provider, model, keys, token_bound):
    if provider not in PROVIDER_MODELS or model not in PROVIDER_MODELS[provider]:
        raise ValueError("Only approved catalog models can enter this comparison")
    return RuntimeConfig(RUN_MODE="historical",LLM_PROVIDER=provider,LLM_BASE_URL=PROVIDER_ORIGINS[provider],
        LLM_MODEL=model,LLM_TOKEN_BUDGET=token_bound,
        **(dict(LLM_COST_BUDGET="2.40",LLM_COST_CURRENCY="USD") if provider=="boxapi" else {}),
        **{provider.upper()+"_API_KEY":keys[provider]["api_key"]})


async def run_recorded_case(snap, pos, opp, *, config, budget, envelope, trace):
    """Use the same batch-entry/position dispatch as the current engine."""
    context = dict(position=pos) if pos is not None else dict(market_batch={snap.symbol:(snap,opp)})
    return await decide_role(snap,**context,config=config,budget=budget,
        run_envelope=envelope,allowed_symbols=(snap.symbol,),model_trace=trace,
        timeout_seconds=30,horizon_bounds=(300,36000),
        remaining_seconds=pos.hard_exit_at-pos.observed_at if pos else 36000)


def rank_operational_results(results, expected_cases):
    rows = []
    for model,items in results.items():
        valid = [item for item in items if item["host_outcome"] == "MODEL_DECISION"]
        roles = {item["role"] for item in valid}
        latencies = [item["elapsed_seconds"] for item in valid]
        eligible = len(valid) == expected_cases and roles == {"ENTRY_ANALYST","POSITION_REVIEWER"}
        rows.append(dict(candidate=model,valid=len(valid),attempted=len(items),expected=expected_cases,
            eligible=eligible,median_latency_seconds=statistics.median(latencies) if latencies else None,
            http_errors=sum(bool(item.get("http_error_statuses")) for item in items),
            non_http_fallbacks=sum(item["host_outcome"] != "MODEL_DECISION" and not item.get("http_error_statuses")
                for item in items)))
    rows.sort(key=lambda row:(not row["eligible"],-row["valid"],
        row["median_latency_seconds"] if row["median_latency_seconds"] is not None else float("inf"),row["candidate"]))
    selected = next((row["candidate"] for row in rows if row["eligible"]),None)
    return dict(status="OPERATIONAL_CANDIDATE_ONLY" if selected else "NO_QUALIFIED_MODEL",
        selected=selected,ranking=rows,profitability="UNCONFIRMED",
        selection_rule="All fixed cases valid in both roles; then lower median validated latency; cost excluded")


async def compare(args):
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}",args.run_id):
        raise ValueError("Bounded run ID required")
    digest,cases = load_cases(args.cases)
    keys = json.loads(args.keys_file.read_text(encoding="utf-8"))
    candidates = []
    for value in args.candidates:
        provider,model = value.split(":",1)
        config = provider_config(provider,model,keys,args.token_bound)
        state_name = "llm-budget.sqlite3" if provider=="boxapi" else f"{provider}-model-usage.sqlite3"
        budget = ModelBudget(config,args.state_dir/state_name,require_existing=True)
        candidates.append((value,config,budget))
    if len(set(args.candidates)) != len(args.candidates) or not 2 <= len(candidates) <= 12:
        raise ValueError("Compare 2..12 distinct models on identical cases")
    args.output_dir.mkdir(parents=True,exist_ok=False)
    code_sha = source_bundle_sha256(ROOT,[*ROOT.glob("src/royin/*.py"),*ROOT.glob("scripts/*.py"),ROOT/"requirements.lock"])
    protocol = dict(evidence_kind="RECORDED_INPUT_REAL_PROVIDER_COMPARISON",run_id=args.run_id,
        cases_sha256=digest,source_sha256=code_sha,candidates=args.candidates,repeats=args.repeats,
        case_ids=[case[0] for case in cases],role_timeout_seconds=30,max_tools_per_role=1,
        max_http_per_role=2,max_http=len(cases)*args.repeats*len(candidates)*2,concurrency=2,retries=0,
        entry_dispatch="CURRENT_BATCH_CONTRACT_SINGLE_RECORDED_CANDIDATE",
        pricing="EXCLUDED_FROM_SELECTION_BOX_ORIGINAL_LIMITS_PRESERVED",orders=0,
        limitations=["Recorded inputs and hypothetical positions; not prospective forecasting or realized returns",
            "Single-candidate entry context does not test whole-market selection",
            "Historical model knowledge and correlated cases preclude an independent holdout claim",
            "Provider errors are availability observations, not analysis-quality oracles"])
    (args.output_dir/"protocol.json").write_text(json.dumps(protocol,indent=2),encoding="utf-8")
    semaphore = asyncio.Semaphore(2)
    results = {}

    async def worker(identity, config, budget):
        envelope = RoleRunEnvelope(budget,duration_seconds=3600,
            scope_id=args.run_id+":"+hashlib.sha256(identity.encode()).hexdigest()[:16])
        rows = []
        for repetition in range(args.repeats):
            for name,snap,pos,opp in cases:
                case_key = hashlib.sha256(f"{identity}:{repetition}:{name}".encode()).hexdigest()
                path = args.output_dir/(case_key+".json")
                with path.open("x",encoding="utf-8") as out:
                    json.dump(dict(state="CLAIMED",candidate=identity,case_id=name,repetition=repetition),out)
                async with semaphore:
                    trace = {}
                    decision = await run_recorded_case(snap,pos,opp,config=config,budget=budget,
                        envelope=envelope,trace=trace)
                row = dict(candidate=identity,case_id=name,repetition=repetition,
                    role="POSITION_REVIEWER" if pos else "ENTRY_ANALYST",host_outcome=trace.get("host_outcome"),
                    elapsed_seconds=trace["elapsed_seconds"],decision=decision.model_dump(mode="json"),model_trace=trace,
                    http_error_statuses=[r["status_code"] for r in trace.get("responses",[]) if r["status_code"] >= 400],
                    orders=0,fills=0)
                path.write_text(json.dumps(row,indent=2),encoding="utf-8")
                rows.append(row)
                print(json.dumps({key:row[key] for key in ("candidate","case_id","repetition","host_outcome",
                    "elapsed_seconds","http_error_statuses","orders")}),flush=True)
        results[identity] = rows

    await asyncio.gather(*(worker(*candidate) for candidate in candidates))
    if source_bundle_sha256(ROOT,[*ROOT.glob("src/royin/*.py"),*ROOT.glob("scripts/*.py"),ROOT/"requirements.lock"]) != code_sha:
        raise ValueError("Comparison source changed; preserve results without selecting a model")
    report = dict(protocol=protocol,**rank_operational_results(results,len(cases)*args.repeats),orders=0,fills=0)
    (args.output_dir/"report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report),flush=True)
    return 0 if report["selected"] else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",action="store_true")
    parser.add_argument("--run-id",required=True)
    parser.add_argument("--cases",type=Path,required=True)
    parser.add_argument("--keys-file",type=Path,required=True)
    parser.add_argument("--state-dir",type=Path,required=True)
    parser.add_argument("--output-dir",type=Path,required=True)
    parser.add_argument("--candidates",nargs="+",required=True,help="provider:exact-model-id")
    parser.add_argument("--repeats",type=int,choices=(1,2,3),default=1)
    parser.add_argument("--token-bound",type=int,default=20000000)
    args = parser.parse_args(argv)
    if not args.run:
        print(json.dumps(dict(status="BLOCKED_EXPLICIT_RUN_REQUIRED",model_http=0,orders=0)))
        return 2
    try:
        return asyncio.run(compare(args))
    except (BudgetBlocked,ValueError,OSError,KeyError,TypeError) as exc:
        print(json.dumps(dict(status="BLOCKED_MODEL_COMPARISON",error_type=type(exc).__name__,orders=0)))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
