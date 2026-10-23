"""Bounded diagnostic AI snapshots using BoxAPI within durable ModelBudget.

Evaluates 12 fixed snapshots with hypothetical account states; pre-registration
and profitability are not established by this diagnostic comparison:
- Conflicting signals (bullish trend with overbought RSI)
- Regime transitions (neutral and bearish markets)
- Healthy momentum breakouts with volume confirmation
- Long position management (holding vs exit on reversal)

Compares:
1. Real AI decision (gpt-6-luna via ModelBudget)
2. Naive Baseline Rule decision (SMA crossover)
3. Conviction Fee-Aware Rule decision (SMA spread + ATR hurdle)
"""

import argparse
import asyncio
import hashlib
import json
import sqlite3
import time
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from royin.agent import decide
from royin.config import load_config
from royin.datasets import load_dataset
from royin.evaluation import baseline_rule_decision, conviction_fee_aware_decision
from royin.features import extract_features
from royin.market_data import Candle, CandleSeries
from royin.model_budget import BudgetBlocked, ModelBudget

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = (
    ROOT
    / "data/round-2-data/20261021T213718Z_f8e726a7/normalized-8529bd60af259a07bfbc81cf32c16b0352f4e1723311f517c4d525dc9b7e8ffa.json"
)


def load_candles(dataset_path: Path) -> list[Candle]:
    expected = "8529bd60af259a07bfbc81cf32c16b0352f4e1723311f517c4d525dc9b7e8ffa"
    if hashlib.sha256(dataset_path.read_bytes()).hexdigest() != expected:
        raise ValueError("Diagnostic dataset hash mismatch")
    metadata, candles = load_dataset(dataset_path)
    if metadata["symbol"] != "USDTTMN" or metadata["interval_seconds"] != 3600:
        raise ValueError("Unexpected diagnostic market/timeframe")
    return candles


def limit_mission_budget(budget):
    """Bound this invocation before each durable reservation; global limits still apply."""
    original = budget.reserve
    cost = (budget.policy["max_input_tokens"] * budget.input_rate
            + budget.policy["max_output_tokens"] * budget.output_rate) / Decimal(1_000_000)
    state = {"requests": 0, "reserved_usd": Decimal(0)}

    def reserve(*, now=None):
        if state["requests"] >= 24 or state["reserved_usd"] + cost > Decimal("0.04"):
            raise BudgetBlocked("AI role evaluation mission limit reached before HTTP")
        reserved = original(now=now)
        state["requests"] += 1
        state["reserved_usd"] += reserved
        return reserved

    budget.reserve = reserve
    return state


async def run_ai_evaluation(dataset_path: Path = DEFAULT_DATASET) -> dict:
    candles = load_candles(dataset_path)
    config = load_config()
    budget = ModelBudget(config, require_existing=True)
    limit_mission_budget(budget)

    # Descriptive labels are not independent correctness or profitability oracles.
    scenarios = [
        {"idx": 35, "position": Decimal("0"), "name": "Bullish trend but Overbought RSI (Conflict)"},
        {"idx": 75, "position": Decimal("0"), "name": "Neutral choppy market with low volume"},
        {"idx": 120, "position": Decimal("0"), "name": "Bullish trend with elevated RSI"},
        {"idx": 160, "position": Decimal("0"), "name": "Bearish trend with oversold dip"},
        {"idx": 210, "position": Decimal("0"), "name": "Bullish momentum with high volume surge"},
        {"idx": 260, "position": Decimal("0"), "name": "Healthy bullish trend with neutral RSI"},
        {"idx": 310, "position": Decimal("0"), "name": "Neutral market with overbought RSI"},
        {"idx": 360, "position": Decimal("0"), "name": "Bullish trend with low volume"},
        {"idx": 410, "position": Decimal("0"), "name": "Bearish regime continuation"},
        {"idx": 450, "position": Decimal("0"), "name": "Strong bullish breakout with 2.1x volume surge"},
        {"idx": 35, "position": Decimal("10.0"), "name": "Holding Long position in Overbought territory"},
        {"idx": 160, "position": Decimal("10.0"), "name": "Holding Long position during Bearish breakdown"},
    ]

    db_path = ROOT / "data/llm-budget.sqlite3"
    conn = sqlite3.connect(db_path)
    res_before = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(nano_usd), 0), COALESCE(SUM(tokens), 0) FROM model_reservations"
    ).fetchone()
    conn.close()

    eval_results = []
    total_latency = 0.0

    print(f"Starting bounded evaluation of 12 snapshots with BoxAPI {config.LLM_MODEL}...")

    for i, sc in enumerate(scenarios, 1):
        idx = sc["idx"]
        pos = sc["position"]
        candle = candles[idx]
        cutoff = candle.open_time + 3600
        series_slice = CandleSeries(tuple(candles[: idx + 1]), 3600)

        snapshot = extract_features(
            series_slice,
            "USDTTMN",
            cutoff=cutoff,
            current_position_base=pos,
            available_tmn_cash=Decimal("5000000"),
        )

        # Baseline decision
        base_dec = baseline_rule_decision(snapshot, allowed_symbols=("USDTTMN",))

        # Conviction decision
        conv_dec = conviction_fee_aware_decision(snapshot, allowed_symbols=("USDTTMN",))

        # Real AI decision via ModelBudget
        start_t = time.monotonic()
        ai_dec = await decide(
            snapshot,
            config=config,
            budget=budget,
            allowed_symbols=("USDTTMN",),
            decision_id=f"eval_{cutoff}_{i:02d}",
        )
        elapsed = round(time.monotonic() - start_t, 3)
        total_latency += elapsed

        # Evidence validation check: ensure AI cited ONLY valid evidence IDs
        valid_ev_ids = set(snapshot.evidences.keys())
        ai_cites = set(ai_dec.evidence_ids)
        cites_valid = ai_cites.issubset(valid_ev_ids)

        eval_results.append(
            {
                "scenario_index": i,
                "name": sc["name"],
                "cutoff": cutoff,
                "position_base": str(pos),
                "last_close": str(snapshot.last_close),
                "rsi_14": str(snapshot.rsi_14),
                "atr_pct": str(round(snapshot.atr_14 / snapshot.last_close * Decimal(100), 2)),
                "volume_ratio": str(snapshot.volume_ratio),
                "evidences_present": list(snapshot.evidences.keys()),
                "ai_decision": {
                    "action": ai_dec.action,
                    "evidence_ids": list(ai_dec.evidence_ids),
                    "cites_strictly_valid": cites_valid,
                    "reason": ai_dec.reason,
                    "invalidation": ai_dec.invalidation,
                    "latency_seconds": elapsed,
                },
                "baseline_decision": {
                    "action": base_dec.action,
                    "reason": base_dec.reason,
                },
                "conviction_decision": {
                    "action": conv_dec.action,
                    "reason": conv_dec.reason,
                },
                "divergence_from_baseline": ai_dec.action != base_dec.action,
            }
        )
        print(
            f"[{i:02d}/12] Cutoff {cutoff} | AI: {ai_dec.action:5s} | Base: {base_dec.action:5s} | Conv: {conv_dec.action:5s} | Latency: {elapsed:.2f}s"
        )

    conn = sqlite3.connect(db_path)
    res_after = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(nano_usd), 0), COALESCE(SUM(tokens), 0) FROM model_reservations"
    ).fetchone()
    conn.close()

    new_requests = res_after[0] - res_before[0]
    new_nano_usd = res_after[1] - res_before[1]
    new_tokens = res_after[2] - res_before[2]
    new_usd = Decimal(new_nano_usd) / Decimal(10**9)

    agreements_with_baseline = sum(
        1 for r in eval_results if r["ai_decision"]["action"] == r["baseline_decision"]["action"]
    )
    divergences = [r for r in eval_results if r["divergence_from_baseline"]]

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    output_dir = ROOT / "artifacts/ai-evaluation" / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "run_id": run_id,
        "evaluated_at_utc": datetime.now(UTC).isoformat(),
        "model": config.LLM_MODEL,
        "provider": config.LLM_PROVIDER,
        "base_url": config.LLM_BASE_URL,
        "total_scenarios": len(scenarios),
        "total_ai_decisions": len(eval_results),
        "agreement_with_baseline_count": agreements_with_baseline,
        "agreement_rate": round(agreements_with_baseline / len(eval_results), 4),
        "divergences_count": len(divergences),
        "total_latency_seconds": round(total_latency, 3),
        "average_latency_seconds": round(total_latency / len(eval_results), 3),
        "budget_consumption": {
            "new_reservations_count": new_requests,
            "new_reserved_nano_usd": new_nano_usd,
            "new_reserved_usd": str(round(new_usd, 6)),
            "new_tokens_reserved": new_tokens,
            "within_mission_cap": new_requests <= 24 and new_usd <= Decimal("0.04"),
        },
        "all_evidence_cites_valid": all(
            r["ai_decision"]["cites_strictly_valid"] for r in eval_results
        ),
        "scenarios": eval_results,
    }

    report_path = output_dir / "ai_evaluation_report.json"
    report_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nEvaluation Complete! Results saved to {report_path}")
    print(f"Total new reservations: {new_requests} HTTP calls | Total cost reserved: ${new_usd:.4f} USD")
    print(f"Agreement rate with naive baseline: {summary['agreement_rate']*100:.1f}% ({len(divergences)} divergences)")

    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description="Paid diagnostic snapshots; not a profitability evaluation")
    parser.add_argument("--run", action="store_true", help="Authorize up to 24 HTTP / USD 0.04 reserved")
    args = parser.parse_args(argv)
    if not args.run:
        parser.print_help()
        return 0
    asyncio.run(run_ai_evaluation())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
