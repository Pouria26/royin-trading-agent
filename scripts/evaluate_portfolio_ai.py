"""Offline portfolio wiring/replay check. No paid-model or exchange transport."""

import argparse
import asyncio
import hashlib
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx2
from pydantic_ai import Agent, RunContext, models
from pydantic_ai.models.test import TestModel

from royin.agent import SYSTEM_INSTRUCTIONS, decide
from royin.config import RuntimeConfig
from royin.decision import DecisionProposal
from royin.evaluation import (
    baseline_rule_decision,
    portfolio_bindings,
    recorded_portfolio_producer,
    run_portfolio_ablation,
)
from royin.features import FeatureSnapshot
from royin.market_data import Candle
from royin.risk import MarketRules, RiskPolicy

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "config/portfolio-ai-protocol-v4.json"


def synthetic_scenario():
    """Explicit invented prices, unrelated to market returns or historical holdout."""
    candles = []
    for i in range(64):
        price = Decimal(230000 + ((i % 12) - 6) * 300)
        candles.append(
            Candle(1700002800 + i * 3600, price, price + 500, price - 500, price, Decimal(100))
        )
    rules = MarketRules(
        "USDTTMN",
        "USDT",
        "TMN",
        Decimal(1),
        Decimal(".01"),
        Decimal(100000),
        Decimal(1),
        Decimal(".0025"),
        Decimal(".003"),
    )
    policy = RiskPolicy(
        Decimal(1500000),
        Decimal(3000000),
        Decimal(".02"),
        Decimal(".05"),
        candles[-1].open_time + 3600,
    )
    return candles, rules, policy


def run_self_check(protocol_path=PROTOCOL):
    candles, rules, policy = synthetic_scenario()
    initial, interval, slip = Decimal(5000000), 3600, Decimal(".0005")
    bindings = portfolio_bindings(candles, rules, policy, initial, interval, slip)
    protocol = json.loads(Path(protocol_path).read_text(encoding="utf8"))
    if protocol["offline_bindings"] != bindings:
        raise ValueError(
            "Protocol/source/config/data hash mismatch; freeze a new version before outcomes"
        )
    records = []
    record_bindings = bindings
    skip_first_entry = True

    def fake(snapshot):
        nonlocal skip_first_entry
        baseline = baseline_rule_decision(snapshot)
        # Skip exactly the first opportunity to exercise a different own-ledger path.
        action = baseline.action
        if action == "ENTER" and skip_first_entry:
            action, skip_first_entry = "WAIT", False
        proposal = DecisionProposal(
            action=action,
            evidence_ids=baseline.evidence_ids,
            reason="FAKE_MODEL wiring fixture",
            invalidation="Next closed bar",
        )
        agent = Agent(
            TestModel(
                custom_output_args=proposal.model_dump(), call_tools=["read_market_snapshot"]
            ),
            deps_type=FeatureSnapshot,
            output_type=DecisionProposal,
            instructions=SYSTEM_INSTRUCTIONS,
        )

        @agent.tool
        def read_market_snapshot(ctx: RunContext[FeatureSnapshot]) -> str:
            return json.dumps(ctx.deps.to_canonical_dict())

        async def invoke():
            async with httpx2.AsyncClient(
                transport=httpx2.MockTransport(
                    lambda _: (_ for _ in ()).throw(AssertionError("HTTP forbidden"))
                )
            ) as client:
                return await decide(
                    snapshot,
                    config=RuntimeConfig(),
                    client=client,
                    agent=agent,
                    decision_id=f"fake_{snapshot.cutoff}",
                )

        decision = asyncio.run(invoke())
        records.append(
            {
                "source": "FAKE_MODEL",
                "manifest": record_bindings,
                "snapshot_sha256": snapshot.snapshot_sha256,
                "snapshot": snapshot.to_canonical_dict(),
                "decision": decision.model_dump(mode="json"),
            }
        )
        return decision

    old_requests = models.ALLOW_MODEL_REQUESTS
    models.ALLOW_MODEL_REQUESTS = False
    try:
        first = run_portfolio_ablation(candles, rules, policy, fake, source="FAKE_MODEL")
        producer = recorded_portfolio_producer(records, bindings, source="FAKE_MODEL")
        replay = run_portfolio_ablation(
            candles, rules, policy, producer, source="FAKE_MODEL_REPLAY"
        )
        for arm in first:
            for field in ("equity_curve", "decision_traces", "fills", "orders", "episodes"):
                if first[arm][field] != replay[arm][field]:
                    raise AssertionError(f"Non-deterministic replay: {arm}/{field}")
        # Real decisions from a different cost scenario must be generated on that own-state path.
        # Reusing the base-cost records would be an invalid sensitivity experiment.
        record_bindings = portfolio_bindings(
            candles, rules, policy, initial, interval, Decimal(".002")
        )
        skip_first_entry = True
        stress = run_portfolio_ablation(
            candles, rules, policy, fake, slippage_pct=Decimal(".002"), source="FAKE_MODEL"
        )
    finally:
        models.ALLOW_MODEL_REQUESTS = old_requests
    return {
        "status": "PASS_OFFLINE_WIRING_ONLY",
        "primary_status": "BLOCKED_DATA",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "bindings": bindings,
        "protocol_sha256": hashlib.sha256(Path(protocol_path).read_bytes()).hexdigest(),
        "evidence_kind": "SYNTHETIC_DATA_FAKE_MODEL_AND_FAKE_RECORDED_REPLAY",
        "http_requests": 0,
        "paid_requests": 0,
        "provider_usage": None,
        "invoice": None,
        "model_records": records[: len(first["rule_ai"]["decision_traces"])],
        "arms": first,
        "cost_sensitivity_fake_only": stress,
        "real_recorded_replay": "BLOCKED: no exact own-ledger records",
        "out_of_sample_performance": None,
        "independent_exposures": None,
        "independence_note": "Closed episodes counted per arm; serial episodes are not statistically independent observations",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="Synthetic data and fake SDK model only; zero HTTP",
    )
    args = parser.parse_args(argv)
    if not args.self_check:
        print(
            "BLOCKED_DATA: no semantics-approved prospective splits or exact own-ledger model records; no paid mode"
        )
        return 2
    report = run_self_check()
    directory = (
        ROOT
        / "artifacts/portfolio-ai"
        / (datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8])
    )
    directory.mkdir(parents=True, exist_ok=False)
    path = directory / "manifest.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "primary_status": report["primary_status"],
                "manifest": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
