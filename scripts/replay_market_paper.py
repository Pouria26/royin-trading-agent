"""Offline validation of recorded host decisions and accounting, never new AI evidence."""

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from royin.decision import (
    Decision,
    EntryOpportunityContext,
    MarketEntryProposal,
    PositionReviewContext,
    RoleDecisionProposal,
    bind_decision,
    validate_role_proposal,
)
from royin.evaluation import source_bundle_sha256
from royin.features import FeatureSnapshot
from royin.ledger import Ledger
from royin.market_data import decimal_number
from scripts.score_market_forecast import current_forecasts

PUBLIC_ENDPOINTS = {"/hector/web/v1/markets", "/v1/markets", "/v1/udf/history", "/v1/depth"}
DECIMAL_FEATURES = {"last_close", "trend_sma_fast", "trend_sma_slow", "rsi_14", "atr_14",
                    "volume_ratio", "current_position_base", "available_tmn_cash"}


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical_hash(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def signed_decimal(value):
    if isinstance(value,(bool,float)) or not isinstance(value,(str,int,Decimal)):
        raise ValueError("Exact signed decimal required")
    result = Decimal(value)
    decimal_number(abs(result))
    return result


def reject_credentials(value):
    if isinstance(value,dict):
        if {str(k).lower() for k in value}.intersection({"authorization","x-api-key",
                "wallex_api_key","boxapi_api_key","sub-account-client-id"}):
            raise ValueError("Private credentials are not allowed in replay artifacts")
        for item in value.values():
            reject_credentials(item)
    elif isinstance(value,list):
        for item in value:
            reject_credentials(item)
    elif isinstance(value,str):
        if re.search(r"\b\d{3,8}\|[A-Za-z0-9]{20,}|\bsk-[A-Za-z0-9_-]{20,}|\bbox-ai-[A-Za-z0-9_-]{24,}",value):
            raise ValueError("Credential-shaped content is not allowed")
        if value.startswith(("{","[")):
            try:
                decoded = json.loads(value)
            except ValueError:
                return
            reject_credentials(decoded)


def read_bounded(path, limit):
    with path.open("rb") as stream:
        raw = stream.read(limit+1)
    if len(raw) > limit:
        raise ValueError("Recorded input exceeds size allowance")
    return raw


def balances(ledger):
    return {asset:dict(free=str(b.free),locked=str(b.locked))
            for asset,b in ledger.get_all_balances().items() if b.total}


def normalized_balances(values):
    result = {}
    for asset,row in values.items():
        free, locked = decimal_number(row["free"]), decimal_number(row["locked"])
        if free or locked:
            result[asset] = dict(free=str(free),locked=str(locked))
    return result


def equal_balances(left, right):
    a, b = normalized_balances(left), normalized_balances(right)
    return a.keys() == b.keys() and all(
        Decimal(a[k][part]) == Decimal(b[k][part]) for k in a for part in ("free","locked"))


def replay_accounting(manifest):
    arm = manifest["arms"]["paper_portfolio"]
    journal = manifest.get("accounting")
    if journal is None:
        return dict(status="ACCOUNTING_REPLAY_UNCONFIRMED",reason="Original journal is absent"), None
    if journal.get("schema_version") != 1 or len(journal["events"]) > 100000:
        raise ValueError("Unsupported accounting journal")
    ledger = Ledger(":memory:")
    ledger.initialize_portfolio(decimal_number(arm["initial_capital_tmn"],positive=True),
        binding=canonical_hash(journal),quote_asset="TMN")
    states, fill_rows, intents = [balances(ledger)], [], 0
    for event in journal["events"]:
        kind, row = event["event_type"], event["payload"]
        if kind == "INTENT":
            if row["quote_asset"] != "TMN":
                raise ValueError("Replay only supports the recorded TMN portfolio")
            ledger.record_intent(**{k:row[k] for k in ("client_id","symbol","side","order_type",
                "timestamp","quote_asset","base_asset")}, price=decimal_number(row["price"],positive=True),
                quantity=decimal_number(row["quantity"],positive=True),
                quote_fee_reserve=decimal_number(row["quote_fee_reserve"]))
            intents += 1
        elif kind == "FILL":
            args = {k:row[k] for k in ("fill_id","client_id","fee_asset","timestamp")}
            args.update(price=decimal_number(row["price"],positive=True),
                quantity=decimal_number(row["quantity"],positive=True),fee=decimal_number(row["fee"]))
            ledger.record_fill(**args)
            before = balances(ledger), ledger.get_realized_pnl()
            ledger.record_fill(**args)
            if before != (balances(ledger),ledger.get_realized_pnl()):
                raise ValueError("Recorded fill is not idempotent")
            fill_rows.append({k:str(v) if isinstance(v,Decimal) else v for k,v in args.items()})
        elif kind == "CANCEL":
            if not ledger.cancel_intent(row["client_id"]):
                raise ValueError("Cancellation has no active recorded intent")
        else:
            raise ValueError("Unsupported journal event")
        states.append(balances(ledger))
    if (not equal_balances(balances(ledger),journal["balances"])
            or ledger.get_realized_pnl() != signed_decimal(journal["realized_pnl_tmn"])
            or Decimal(arm["final_cash_tmn"]) != ledger.get_balance("TMN").free
            or intents != len(arm["orders"]) or fill_rows != arm["fills"]):
        raise ValueError("Recorded journal, manifest totals or fills disagree")
    return dict(status="VERIFIED_RECORDED_ACCOUNTING",balances=balances(ledger),
        realized_pnl_tmn=str(ledger.get_realized_pnl()),events=len(journal["events"]),
        closed_round_trips=int(ledger.get_meta("closed_round_trips") or "0")), states


def recorded_proposal(trace):
    requests, responses = trace["requests"], trace["responses"]
    if len(requests) != 2 or len(responses) != 2 or any(r["status_code"] != 200 for r in responses):
        raise ValueError("Successful role requires the bounded two-request tool sequence")
    bodies = [json.loads(raw) for raw in requests]
    for body in bodies:
        instructions = [m["content"] for m in body["messages"] if m["role"] == "system"]
        if (len(instructions) != 1 or sha256(instructions[0].encode()) != trace["prompt_sha256"]
                or body["model"] != trace["model"] or body.get("stream") or body.get("n",1) != 1):
            raise ValueError("Recorded model/prompt/request mismatch")
    read_calls = json.loads(responses[0]["body"])["choices"][0]["message"]["tool_calls"]
    if len(read_calls) != 1 or read_calls[0]["function"]["name"] != "read_market_snapshot":
        raise ValueError("Recorded read-only tool sequence is invalid")
    call = read_calls[0]
    prefix = bodies[0]["messages"]
    messages = bodies[1]["messages"]
    if (not any(m["role"] == "user" for m in prefix) or messages[:len(prefix)] != prefix
            or len(messages) != len(prefix)+2 or messages[-2].get("role") != "assistant"
            or messages[-2].get("tool_calls") != read_calls):
        raise ValueError("Recorded conversation does not preserve the provider tool call")
    tool_rows = [m for m in bodies[1]["messages"] if m["role"] == "tool"]
    if len(tool_rows) != 1 or tool_rows[0]["tool_call_id"] != call["id"]:
        raise ValueError("Recorded tool-call ID/result mismatch")
    expected = {k:v for k,v in trace["context"].items() if k not in ("research_universe","research_view")}
    if json.loads(tool_rows[0]["content"]) != expected:
        raise ValueError("Recorded tool result differs from decision context")
    if "research_universe" in trace["context"]:
        selected = json.loads(call["function"]["arguments"])["symbols"]
        context = trace["context"]
        allowed = {m["symbol"] for m in context["research_universe"]["markets"]}
        if (selected != context["requested_symbols"] or len(selected) != len(set(selected))
                or not 1 <= len(selected) <= 10 or not set(selected).issubset(allowed)
                or not {c["symbol"] for c in context["candidates"]}.issubset(selected)):
            raise ValueError("Recorded research selection is outside its universe")
    output = json.loads(responses[-1]["body"])["choices"][0]["message"]["tool_calls"]
    if len(output) != 1 or output[0]["function"]["name"] != "final_result":
        raise ValueError("Missing unique final provider result")
    cls = MarketEntryProposal if trace["context"].get("candidates") is not None else RoleDecisionProposal
    return cls.model_validate_json(output[0]["function"]["arguments"])


def replay_decision(row, states):
    trace = row.get("model_trace") or {}
    if not trace:
        if row["decision"]["action"] == "ENTER":
            raise ValueError("An entry cannot lack its recorded model decision")
        return dict(status="PRESERVED_HOST_EVENT")
    if trace.get("host_outcome") == "HOST_FALLBACK":
        if row["decision"]["action"] != "WAIT" or row["decision"].get("forecast") is not None:
            raise ValueError("Host fallback cannot create a trade")
        return dict(status="PRESERVED_HOST_FALLBACK")
    if (trace.get("host_outcome") != "MODEL_DECISION" or trace.get("provider") != "boxapi"
            or trace.get("evidence_kind") != "REAL_MODEL_ATTEMPT"):
        raise ValueError("Explicit original real-provider evidence is required")
    proposal = recorded_proposal(trace)
    decision = Decision.model_validate(row["decision"])
    source = row["snapshot"]
    snap = FeatureSnapshot(**{**source,**{k:decimal_number(source[k])
        for k in DECIMAL_FEATURES},"snapshot_sha256":row["snapshot_sha256"]})
    if not snap.verify_hash() or decision.snapshot_sha256 != snap.snapshot_sha256:
        raise ValueError("Snapshot identity mismatch")
    context = trace["context"]
    position = PositionReviewContext.model_validate_json(json.dumps(context["position"])) if context.get("position") else None
    opportunity_data = row.get("opportunity") or context.get("opportunity")
    opp = EntryOpportunityContext.model_validate_json(json.dumps(opportunity_data)) if opportunity_data else None
    has_context = decision.action != "ENTER" or opp is not None
    if context.get("candidates") is not None:
        if canonical_hash(context["candidates"]) != context["batch_sha256"]:
            raise ValueError("Recorded market batch hash mismatch")
        selected = [c for c in context["candidates"] if c["symbol"] == snap.symbol]
        if (len(selected) != 1 or selected[0]["snapshot_sha256"] != snap.snapshot_sha256
                or (opp is not None and selected[0]["opportunity_sha256"] != opp.sha256)):
            raise ValueError("Selected snapshot/opportunity is outside the recorded batch")
        batch = {snap.symbol:(snap,opp)}
    else:
        if context.get("snapshot") != source or context.get("snapshot_sha256") != snap.snapshot_sha256:
            raise ValueError("Recorded single-role context mismatch")
        batch = None
    if has_context:
        validate_role_proposal(proposal,role=context["role"],snapshot=snap,position=position,
            opportunity=None if proposal.action == "WAIT" and batch is not None else opp,
            market_batch=batch,horizon_bounds=tuple(context.get("horizon_bounds",(300,36000))),
            remaining_seconds=context.get("remaining_seconds"))
    rebound = bind_decision(proposal,decision_id=decision.decision_id,symbol=snap.symbol,
        cutoff=snap.cutoff,snapshot_sha256=snap.snapshot_sha256,available_evidence_ids=set(snap.evidences))
    if rebound != decision or trace.get("decision") != row["decision"]:
        raise ValueError("Host/provider decision identity mismatch")
    input_state = row.get("host_input_state")
    own_state = states is not None and input_state is not None
    if own_state:
        index = input_state["accounting_event_count"]
        if type(index) is not int or not 0 <= index < len(states) or not equal_balances(input_state["balances"],states[index]):
            raise ValueError("Decision did not use its own recorded ledger state")
        actual = normalized_balances(states[index])
        cash = actual.get("TMN",dict(free="0",locked="0"))
        base = actual.get(snap.symbol.removesuffix("TMN"),dict(free="0",locked="0"))
        if (snap.available_tmn_cash != Decimal(cash["free"])
                or snap.current_position_base != Decimal(base["free"])+Decimal(base["locked"])):
            raise ValueError("Model input cash or position differs from its own ledger")
    return dict(status="VERIFIED_HOST_DECISION" if has_context and own_state else "BINDING_VERIFIED_CONTEXT_UNCONFIRMED",
        decision_id=decision.decision_id,action=decision.action,symbol=decision.symbol,
        snapshot_sha256=decision.snapshot_sha256,own_ledger_verified=own_state)


def replay_manifest(path, expected_sha256, output_dir, *, bundle=False):
    """Pure offline replay. Source hashes bind artifacts, not independent provider signatures."""
    path, output = Path(path).resolve(), Path(output_dir).resolve()
    if output.is_relative_to(path.parent) or path.parent.is_relative_to(output):
        raise ValueError("Replay output must be separate from the original run")
    raw = read_bounded(path,64_000_000)
    if not re.fullmatch(r"[0-9a-f]{64}",expected_sha256) or sha256(raw) != expected_sha256:
        raise ValueError("Original manifest hash mismatch")
    manifest = json.loads(raw)
    if manifest.get("mode") != "CURRENT_PAPER" or manifest.get("model_mode") != "REAL_MODEL":
        raise ValueError("Replay requires an original current real-model manifest")
    # Reject credential-shaped data rather than silently rewriting evidence/hashes.
    reject_credentials(manifest)
    current_forecasts(path)
    captures, total = [], 0
    if len(manifest.get("public_captures",[])) > 4096:
        raise ValueError("Capture count exceeds allowance")
    for capture in manifest.get("public_captures",[]):
        sha = capture["sha256"]
        if (capture["endpoint"] not in PUBLIC_ENDPOINTS or not re.fullmatch(r"[0-9a-f]{64}",sha)
                or not set(capture["query"]).issubset({"symbol","resolution","from","to"})):
            raise ValueError("Only allowlisted public market captures may be bundled")
        source = (path.parent/"raw"/(sha+".json")).resolve()
        if not source.is_relative_to(path.parent/"raw"):
            raise ValueError("Capture escapes the original raw directory")
        data = read_bounded(source,4_000_000)
        reject_credentials(json.loads(data))
        total += len(data)
        if sha256(data) != sha or total > 128_000_000:
            raise ValueError("Raw capture hash/size mismatch")
        captures.append((source,sha))
    accounting, states = replay_accounting(manifest)
    rows = [replay_decision(row,states) for row in manifest["arms"]["paper_portfolio"]["decision_traces"]]
    verified = all(r["status"] in ("VERIFIED_HOST_DECISION","PRESERVED_HOST_FALLBACK","PRESERVED_HOST_EVENT") for r in rows)
    root = Path(__file__).resolve().parents[1]
    report = dict(evidence_kind="RECORDED_HOST_REPLAY",origin_run_id=manifest["run_id"],
        origin_manifest_sha256=expected_sha256,origin_model_mode="REAL_MODEL",mode="RECORDED_HOST_REPLAY",
        replayed_at_utc=datetime.now(UTC).isoformat(),origin_bindings=manifest["bindings"],
        replayer_code_sha256=source_bundle_sha256(root,[Path(__file__),*root.glob("src/royin/*.py"),root/"requirements.lock"]),
        status="PASS_RECORDED_HOST_REPLAY" if verified and states is not None else "PARTIAL_RECORDED_HOST_REPLAY",
        model_http=0,public_http=0,orders_sent=0,decisions=rows,accounting=accounting,
        verified_public_capture_hashes=len(captures),execution_replay="EXECUTION_REPLAY_UNCONFIRMED",
        limits=["Recorded decisions and accounting only; not a complete event-scheduled market replay",
                "No new model inference, forecast observation, realized account profit or provider signature",
                "Historical validator/prompt revisions can differ; original artifacts are preserved"])
    output.mkdir(parents=True,exist_ok=False)
    if bundle:
        (output/"source").mkdir()
        (output/"source/manifest.json").write_bytes(raw)
        (output/"source/raw").mkdir()
        for source,sha in captures:
            data = read_bounded(source,4_000_000)
            if sha256(data) != sha:
                raise ValueError("Original capture changed while packaging")
            (output/"source/raw"/(sha+".json")).write_bytes(data)
    if sha256(read_bounded(path,64_000_000)) != expected_sha256:
        raise ValueError("Original manifest changed during replay")
    (output/"report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paper-manifest",type=Path,required=True)
    parser.add_argument("--manifest-sha256",required=True)
    parser.add_argument("--output-dir",type=Path,required=True)
    parser.add_argument("--bundle",action="store_true",help="Include reviewed credential-free public captures and original manifest")
    args = parser.parse_args(argv)
    try:
        result = replay_manifest(args.paper_manifest,args.manifest_sha256,args.output_dir,bundle=args.bundle)
    except (OSError,ValueError,KeyError,TypeError,ArithmeticError) as exc:
        print(json.dumps(dict(status="BLOCKED_REPLAY_INPUT",error_type=type(exc).__name__,model_http=0,orders_sent=0)))
        return 2
    print(json.dumps({k:result[k] for k in ("status","evidence_kind","model_http","public_http","execution_replay")}))
    return 0 if result["status"] == "PASS_RECORDED_HOST_REPLAY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
