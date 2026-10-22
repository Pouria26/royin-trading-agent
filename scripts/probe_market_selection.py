"""Bounded real-model market/entry pilot on public Wallex data; no orders, no account writes.

This is an A-side diagnostic, not the production runner (B owns that). It spends from the
shared durable ModelBudget under the 12-run/24-HTTP/USD 0.04 envelope and records the exact
provider request/response so the market choice and forecast can be audited.
"""

import argparse
import asyncio
import hashlib
import json
import time
from decimal import Decimal
from pathlib import Path

from royin.agent import RoleRunEnvelope, decide_role
from royin.config import load_config
from royin.markets import parse_catalog
from royin.model_budget import BudgetBlocked, ModelBudget
from scripts.run_paper_trader import ScannerPublicFeed, scan_current_market

ROOT = Path(__file__).resolve().parents[1]


def public_symbols(feed, *, cutoff):
    payload, received = feed.get("/hector/web/v1/markets", {}, cutoff=cutoff)
    catalog = parse_catalog(payload)
    return payload, received, {symbol for symbol in catalog}


async def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Required: spend the bounded real-model envelope")
    parser.add_argument("--horizon-max", type=int, default=1800, help="Upper horizon bound in seconds")
    parser.add_argument("--capture-dir", default=".local/task-a", help="Ignored raw capture directory")
    args = parser.parse_args(argv)
    if not args.run:
        parser.print_help()
        print("BLOCKED: --run is required; no request was sent.")
        return 2
    if not 600 <= args.horizon_max <= 3600:
        parser.error("horizon-max must be 600..3600")

    config = load_config()
    if config.BOXAPI_API_KEY is None:
        print("BLOCKED: BOXAPI_API_KEY missing in local .env; no request was sent.")
        return 2
    if config.WALLEX_API_KEY is None:
        print("BLOCKED: WALLEX_API_KEY missing; public data would still be allowed but the key is required by local policy.")
        return 2
    budget = ModelBudget(config)
    envelope = RoleRunEnvelope(budget)
    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "_" + hashlib.sha256(
        str(time.time()).encode()).hexdigest()[:8]
    run_dir = Path(args.capture_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    feed = ScannerPublicFeed(run_dir / "raw", max_requests=16)
    now = int(time.time())
    payload, received, symbols = public_symbols(feed, cutoff=now)
    report = scan_current_market(
        feed, account_symbols=symbols, account_as_of=received,
        interval_seconds=300, round_trip_fee_pct=Decimal(".006"),
        min_depth_tmn=Decimal("1000000"), max_spread_pct=Decimal(".003"),
        available_tmn_cash=Decimal("5000000"), batch_limit=2,
    )
    (run_dir / "scan.json").write_text(json.dumps(
        {"status": report["status"], "cutoff": report["cutoff"], "errors": report["errors"],
         "catalog_received_at": received, "catalog_sha256": hashlib.sha256(
             json.dumps(payload, default=str, sort_keys=True).encode()).hexdigest(),
         "profile": "PUBLIC_MARKET_PAPER; catalog universe, not account-verified"},
        indent=2, default=str), encoding="utf-8")
    if not report["batch"]:
        print(json.dumps({"run_id": run_id, "status": report["status"],
                          "errors": report["errors"], "http_requests": feed.requests}, default=str))
        return 0
    batch = {item.snapshot.symbol: (item.snapshot, item.opportunity) for item in report["batch"]}
    (run_dir / "batch.json").write_text(json.dumps([
        {"symbol": s, "snapshot": snap.to_canonical_dict(), "snapshot_sha256": snap.snapshot_sha256,
         "opportunity": opp.model_dump(mode="json"), "opportunity_sha256": opp.sha256}
        for s, (snap, opp) in sorted(batch.items())], indent=2), encoding="utf-8")
    trace = {}
    try:
        decision = await decide_role(
            next(iter(batch.values()))[0], market_batch=batch, config=config, budget=budget,
            run_envelope=envelope, model_trace=trace, allowed_symbols=tuple(batch),
            horizon_bounds=(600, args.horizon_max), remaining_seconds=args.horizon_max,
            timeout_seconds=30,
        )
    except BudgetBlocked as exc:
        print(json.dumps({"run_id": run_id, "status": "BLOCKED_BUDGET", "reason": str(exc),
                          "reservation_ceiling_usd": str(envelope.reservation_ceiling_usd)}))
        return 2
    usage = trace.get("usage") or {}
    summary = {
        "run_id": run_id,
        "status": "REAL_MODEL_DECISION",
        "profile": "PUBLIC_MARKET_PAPER",
        "cutoff": report["cutoff"],
        "batch_symbols": sorted(batch),
        "decision": decision.model_dump(mode="json"),
        "host_outcome": trace.get("host_outcome"),
        "usage": usage,
        "agent_runs": envelope.agent_runs,
        "http_attempts": envelope.http_attempts,
        "reservation_ceiling_usd": str(envelope.reservation_ceiling_usd),
        "model": config.LLM_MODEL,
        "prompt_sha256": trace.get("prompt_sha256"),
        "code_sha256": trace.get("code_sha256"),
        "config_sha256": trace.get("config_sha256"),
        "batch_sha256": (trace.get("context") or {}).get("batch_sha256"),
        "elapsed_seconds": trace.get("elapsed_seconds"),
    }
    (run_dir / "trace.json").write_text(json.dumps(trace, indent=2, default=str), encoding="utf-8")
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    research = ROOT / "research"
    research.mkdir(exist_ok=True)
    (research / f"task-a-market-ai-{run_id}.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
