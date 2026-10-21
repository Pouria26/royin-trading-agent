"""Bounded live AI smoke test for Trading Agent using BoxAPI gpt-6-luna within budget."""

import asyncio
import json
import sqlite3
import sys
import time
from decimal import Decimal
from pathlib import Path

from royin.agent import decide
from royin.config import load_config
from royin.features import extract_features
from royin.market_data import Candle, CandleSeries
from royin.model_budget import ModelBudget
from royin.risk import MarketRules, RiskPolicy, evaluate_risk


def run_smoke_test(max_snapshots: int = 8) -> dict:
    config = load_config()
    budget = ModelBudget(config)

    # Load validated USDTTMN dataset
    dataset_path = Path("data/t02/normalized-c8c0f4903f000a992688564e8a90b54daab68aeff8ca7c998a7d933b41c7b5c1.json")
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset not found: {dataset_path}")

    raw_data = json.loads(dataset_path.read_text(encoding="utf-8"))
    candles = [
        Candle(
            c["open_time"],
            Decimal(c["open"]),
            Decimal(c["high"]),
            Decimal(c["low"]),
            Decimal(c["close"]),
            Decimal(c["volume"]),
        )
        for c in raw_data["candles"]
    ]

    rules = MarketRules(
        symbol="USDTTMN",
        base_asset="USDT",
        quote_asset="TMN",
        tick_size=Decimal("1"),
        step_size=Decimal("0.01"),
        min_notional=Decimal("100000"),
        min_quantity=Decimal("1.0"),
        maker_fee_rate=Decimal("0.0025"),
        taker_fee_rate=Decimal("0.0030"),
    )
    policy = RiskPolicy(
        max_order_tmn=Decimal("1500000"),
        max_exposure_tmn=Decimal("3000000"),
        stop_loss_pct=Decimal("0.02"),
        max_drawdown_pct=Decimal("0.05"),
        deadline_utc=1800000000,
    )
    denied = frozenset({"PAXGTMN", "OPTMN"})

    # Sample indices spaced across the dataset (e.g. index 35, 100, 200, 300, 400, 500, 600, 650)
    sample_indices = [35, 100, 180, 250, 320, 400, 500, 600][:max_snapshots]

    db_path = Path("data/llm-budget.sqlite3")
    conn = sqlite3.connect(db_path)
    res_before = conn.execute("SELECT COUNT(*), COALESCE(SUM(nano_usd), 0), COALESCE(SUM(tokens), 0) FROM model_reservations").fetchone()
    conn.close()

    results = []
    print(f"Executing real AI smoke test on {len(sample_indices)} snapshots with BoxAPI gpt-6-luna...")

    async def _evaluate_all():
        for idx in sample_indices:
            series_slice = CandleSeries(tuple(candles[: idx + 1]), 900)
            candle = candles[idx]
            close_time = candle.open_time + 900
            snap = extract_features(series_slice, "USDTTMN", cutoff=close_time)

            start_t = time.monotonic()
            decision = await decide(snap, config=config, budget=budget)
            elapsed = round(time.monotonic() - start_t, 3)

            # Evaluate through Risk gate
            from royin.ledger import Ledger
            temp_ledger = Ledger(":memory:")
            temp_ledger.set_balance("TMN", free=Decimal("5000000"))

            risk_res = evaluate_risk(
                decision,
                market_rules=rules,
                policy=policy,
                ledger=temp_ledger,
                current_time=close_time + 10,
                snapshot_sha256=snap.snapshot_sha256,
                candle_close_time=close_time,
                current_price=candle.close,
                denied_markets=denied,
            )

            results.append({
                "index": idx,
                "cutoff": close_time,
                "decision_id": decision.decision_id,
                "action": decision.action,
                "evidence_ids": list(decision.evidence_ids),
                "reason": decision.reason,
                "invalidation": decision.invalidation,
                "latency_seconds": elapsed,
                "risk_approved": risk_res.approved,
                "risk_reason": risk_res.reason,
            })
            print(f"  [{idx:03d}] action={decision.action} latency={elapsed}s risk_approved={risk_res.approved}")

    asyncio.run(_evaluate_all())

    conn = sqlite3.connect(db_path)
    res_after = conn.execute("SELECT COUNT(*), COALESCE(SUM(nano_usd), 0), COALESCE(SUM(tokens), 0) FROM model_reservations").fetchone()
    conn.close()

    count_diff = res_after[0] - res_before[0]
    nano_diff = res_after[1] - res_before[1]
    tokens_diff = res_after[2] - res_before[2]
    cost_usd = round(Decimal(nano_diff) / Decimal(1000000000), 6)

    manifest = {
        "kind": "AI_TRADING_AGENT_REAL_SMOKE_TEST_NOT_LIVE_ORDERS",
        "model": config.LLM_MODEL,
        "provider": config.LLM_PROVIDER,
        "snapshots_tested": len(results),
        "reservations_added": count_diff,
        "tokens_consumed": tokens_diff,
        "cost_usd": str(cost_usd),
        "results": results,
    }

    out_file = Path("artifacts/ai_smoke_test_manifest.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nSmoke test complete. Manifest saved to {out_file}")
    print(f"Tokens consumed: {tokens_diff}, Cost: ${cost_usd} USD ({count_diff} reservations)")
    return manifest


if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 7  # 7 additional + 1 run earlier = 8 total
    run_smoke_test(count)
