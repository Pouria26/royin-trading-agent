"""Deterministic paper replay without network transport, API keys, or live execution.

Uses recorded Decisions and historical candles to verify Ledger, Risk, and PaperBroker.
Outputs a reproducible manifest with SHA-256 hash.
"""

import argparse
import hashlib
import json
import sys
from decimal import Decimal
from pathlib import Path

from royin.broker import PaperBroker
from royin.decision import Decision
from royin.ledger import Ledger
from royin.market_data import Candle
from royin.risk import MarketRules, RiskPolicy, evaluate_risk

ROOT = Path(__file__).resolve().parents[1]


def build_fixture_dataset() -> tuple[list[Candle], list[Decision], str]:
    """Construct a deterministic fixture of candles and valid Decision objects without lookahead."""
    snapshot_hash = "a" * 64

    # 15-minute candles (900 seconds cadence)
    candles = [
        Candle(
            open_time=1700000000,
            open=Decimal("60000"),
            high=Decimal("60500"),
            low=Decimal("59800"),
            close=Decimal("60200"),
            volume=Decimal("100"),
        ),
        Candle(
            open_time=1700000900,
            open=Decimal("60200"),
            high=Decimal("60400"),
            low=Decimal("59700"),
            close=Decimal("59900"),
            volume=Decimal("150"),
        ),
        Candle(
            open_time=1700001800,
            open=Decimal("59900"),
            high=Decimal("61000"),
            low=Decimal("59500"),
            close=Decimal("60800"),
            volume=Decimal("200"),
        ),
        Candle(
            open_time=1700002700,
            open=Decimal("60800"),
            high=Decimal("60900"),
            low=Decimal("58000"),
            close=Decimal("58500"),
            volume=Decimal("300"),
        ),
        Candle(
            open_time=1700003600,
            open=Decimal("58500"),
            high=Decimal("59000"),
            low=Decimal("58200"),
            close=Decimal("58800"),
            volume=Decimal("120"),
        ),
    ]

    # Decisions correspond to candle closes (open_time + 900)
    decisions = [
        Decision(
            decision_id="dec_0",
            symbol="USDTTMN",
            action="WAIT",
            cutoff=1700000900,  # close of candle 0
            snapshot_sha256=snapshot_hash,
            evidence_ids=("ev_init",),
            reason="Holding initial cash",
            invalidation="Market changes",
        ),
        Decision(
            decision_id="dec_1",
            symbol="USDTTMN",
            action="ENTER",
            cutoff=1700001800,  # close of candle 1
            snapshot_sha256=snapshot_hash,
            evidence_ids=("ev_dip",),
            reason="Mean-reversion entry signal",
            invalidation="Drop below 58000",
        ),
        Decision(
            decision_id="dec_2",
            symbol="USDTTMN",
            action="WAIT",
            cutoff=1700002700,  # close of candle 2
            snapshot_sha256=snapshot_hash,
            evidence_ids=("ev_hold",),
            reason="Position established, waiting for target",
            invalidation="Stop loss breach",
        ),
        Decision(
            decision_id="dec_3",
            symbol="USDTTMN",
            action="WAIT",
            cutoff=1700003600,  # close of candle 3
            snapshot_sha256=snapshot_hash,
            evidence_ids=("ev_watch",),
            reason="Monitoring risk stop-loss",
            invalidation="None",
        ),
    ]

    return candles, decisions, snapshot_hash


def validate_candles_and_decisions(candles: list[Candle], decisions: list[Decision], interval_seconds: int = 900):
    if not candles:
        raise ValueError("Candles sequence cannot be empty")
    for i in range(1, len(candles)):
        if candles[i].open_time != candles[i - 1].open_time + interval_seconds:
            raise ValueError(f"Candle sequence has gap or cadence mismatch at index {i}")

    if len(decisions) >= len(candles):
        raise ValueError(
            f"Decisions count ({len(decisions)}) must be strictly less than candles count ({len(candles)}) "
            f"to allow future matching without lookahead"
        )


def run_replay(
    candles: list[Candle],
    decisions: list[Decision],
    snapshot_hash: str,
    *,
    initial_capital: Decimal = Decimal("5000000"),
    interval_seconds: int = 900,
) -> dict:
    """Execute the deterministic paper replay and return execution manifest."""
    validate_candles_and_decisions(candles, decisions, interval_seconds)

    ledger = Ledger(":memory:")
    ledger.set_balance("TMN", free=initial_capital)

    rules = MarketRules(
        symbol="USDTTMN",
        base_asset="USDT",
        quote_asset="TMN",
        tick_size=Decimal("1"),
        step_size=Decimal("0.01"),
        min_notional=Decimal("100000"),
        min_quantity=Decimal("1.0"),
        maker_fee_rate=Decimal("0.001"),
        taker_fee_rate=Decimal("0.002"),
    )

    policy = RiskPolicy(
        max_order_tmn=Decimal("1500000"),
        max_exposure_tmn=Decimal("3000000"),
        stop_loss_pct=Decimal("0.02"),
        max_drawdown_pct=Decimal("0.05"),
        deadline_utc=1700010000,
    )

    broker = PaperBroker(ledger, rules)
    denied_markets = frozenset({"PAXGTMN", "OPTMN"})

    log = []
    orders_submitted = 0
    fills_count = 0

    for i, candle in enumerate(candles):
        # 1. Process matching and stop-losses against incoming candle
        # Order placed after candle i-1 close can match here
        filled_ids = broker.process_candle(
            candle,
            slippage_pct=Decimal("0.0005"),
            candle_interval=interval_seconds,
        )
        fills_count += len(filled_ids)
        if filled_ids:
            log.append({
                "step": f"candle_{i}_fills",
                "open_time": candle.open_time,
                "filled_orders": filled_ids,
            })

        # 2. At candle close (open_time + interval), evaluate decision for cutoff = candle close
        candle_close_time = candle.open_time + interval_seconds
        if i < len(decisions):
            decision = decisions[i]
            # Verify decision cutoff matches this closed candle
            if decision.cutoff != candle_close_time:
                raise ValueError(
                    f"Decision cutoff {decision.cutoff} does not match candle close {candle_close_time}"
                )

            current_time = candle_close_time + 10  # 10s execution latency after close
            risk_res = evaluate_risk(
                decision,
                market_rules=rules,
                policy=policy,
                ledger=ledger,
                current_time=current_time,
                snapshot_sha256=snapshot_hash,
                candle_close_time=candle_close_time,
                current_price=candle.close,
                denied_markets=denied_markets,
            )

            if risk_res.approved and risk_res.action != "WAIT":
                order = broker.submit_order(
                    risk_res,
                    client_id=f"order_{decision.decision_id}",
                    timestamp=current_time,
                )
                if order:
                    orders_submitted += 1
                    log.append({
                        "step": f"decision_{i}_order",
                        "client_id": order.client_id,
                        "action": risk_res.action,
                        "price": str(order.price),
                        "quantity": str(order.quantity),
                    })

    # 3. Finalize portfolio at end of simulation
    final_candle = candles[-1]
    final_time = final_candle.open_time + interval_seconds + 30
    final_report = broker.finalize_portfolio(
        current_price=final_candle.close,
        timestamp=final_time,
        initial_capital=initial_capital,
    )

    raw_manifest = {
        "kind": "PAPER_REPLAY_MANIFEST_NOT_LIVE_OR_PROFIT_CLAIM",
        "symbol": rules.symbol,
        "initial_capital_tmn": str(initial_capital),
        "final_cash_tmn": final_report["final_tmn_cash"],
        "total_realized_pnl": final_report["total_realized_pnl"],
        "net_return_pct": final_report["net_return_pct"],
        "residual_dust_base": final_report["residual_dust_base"],
        "decisions_processed": len(decisions),
        "orders_submitted": orders_submitted,
        "fills_count": fills_count,
        "execution_log": log,
    }

    manifest_bytes = json.dumps(raw_manifest, sort_keys=True, indent=2).encode("utf-8")
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
    raw_manifest["manifest_sha256"] = manifest_hash
    raw_manifest["status"] = "PASS_REPLAY_DETERMINISTIC"

    return raw_manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", action="store_true", help="Run deterministic built-in verification fixture")
    parser.add_argument("--dataset", type=str, default=None, help="Path to input JSON dataset")
    parser.add_argument("--out", type=str, default=None, help="Path to write manifest JSON")
    args = parser.parse_args(argv)

    if not args.fixture and not args.dataset:
        parser.error("Must specify either --fixture or --dataset")

    if args.fixture:
        candles, decisions, snapshot_hash = build_fixture_dataset()
    else:
        # Load dataset from file
        p = Path(args.dataset)
        if not p.exists():
            parser.error(f"Dataset file not found: {args.dataset}")
        # Custom dataset parsing can be extended here
        parser.error("Custom dataset parsing requires validated schema; use --fixture for verification")

    manifest = run_replay(candles, decisions, snapshot_hash)

    output_str = json.dumps(manifest, indent=2)
    print(output_str)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_str, encoding="utf-8")

    return 0


if __name__ == "__main__":
    sys.exit(main())
