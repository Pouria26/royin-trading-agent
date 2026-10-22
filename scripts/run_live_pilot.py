"""Micro-pilot technical execution runner. Production is blocked until integrated review.

This runner is dedicated to technical execution verification (cumulative fills,
reconciliation, dust handling, and timeout), completely decoupled from strategy
alpha or profit claims. It strictly executes at most a single round-trip (1 BUY,
1 EXIT SELL) under host-enforced risk gates.
"""

import argparse
import json
import time
from decimal import ROUND_DOWN, Decimal
from pathlib import Path

from royin.config import RuntimeConfig, load_config
from royin.decision import Decision
from royin.ledger import Ledger, validate_decimal
from royin.live_broker import WallexLiveBroker
from royin.market_data import decimal_number
from royin.markets import load_restrictions
from royin.risk import MarketRules, RiskPolicy, evaluate_risk

PROPOSED_PILOT_SYMBOL = "USDTTMN"
PROPOSED_PILOT_CEILING_TMN = Decimal("200000")
PROPOSED_MIN_QUANTITY = Decimal("1.0")
PROPOSED_MIN_NOTIONAL = Decimal("100000")
PROPOSED_STOP_LOSS_PCT = Decimal("0.02")  # 2% stop-loss threshold (not a guaranteed exit price)
PROPOSED_MAX_HOLDING_SECONDS = 900  # 15 minutes timeout before forced exit


class PilotExecutionError(Exception):
    """Failure or gate block during pilot execution."""


def evaluate_pilot_sellability(
    price: Decimal,
    taker_fee_rate: Decimal,
    step_size: Decimal,
    ceiling_tmn: Decimal = PROPOSED_PILOT_CEILING_TMN,
    min_quantity: Decimal = PROPOSED_MIN_QUANTITY,
    min_notional: Decimal = PROPOSED_MIN_NOTIONAL,
) -> dict:
    """Check whether a proposed buy notional produces a post-fee sellable quantity."""
    validate_decimal(price, "price", strictly_positive=True)
    validate_decimal(taker_fee_rate, "taker_fee_rate", allow_zero=True)
    validate_decimal(step_size, "step_size", strictly_positive=True)
    validate_decimal(ceiling_tmn, "ceiling_tmn", strictly_positive=True)

    raw_qty = ceiling_tmn / (price * (Decimal(1) + taker_fee_rate))
    target_qty = (raw_qty / step_size).quantize(Decimal("1"), rounding=ROUND_DOWN) * step_size
    net_base = target_qty * (Decimal(1) - taker_fee_rate)
    sellable_qty = (net_base / step_size).quantize(Decimal("1"), rounding=ROUND_DOWN) * step_size
    sellable_notional = sellable_qty * price

    if target_qty < min_quantity:
        return {
            "status": "BLOCKED_MINIMUM",
            "reason": (
                f"Proposed ceiling {ceiling_tmn} TMN yields {target_qty} {PROPOSED_PILOT_SYMBOL[:4]}, "
                f"which is below min_quantity {min_quantity} at price {price} TMN"
            ),
            "target_qty": str(target_qty),
            "min_quantity": str(min_quantity),
            "sellable_qty": str(sellable_qty),
            "price": str(price),
        }
    if sellable_qty < min_quantity or sellable_notional < min_notional:
        return {
            "status": "BLOCKED_MINIMUM",
            "reason": (
                f"Post-fee sellable quantity {sellable_qty} ({sellable_notional} TMN) "
                f"falls below min_quantity {min_quantity} or min_notional {min_notional} TMN"
            ),
            "target_qty": str(target_qty),
            "min_quantity": str(min_quantity),
            "sellable_qty": str(sellable_qty),
            "sellable_notional": str(sellable_notional),
            "price": str(price),
        }
    return {
        "status": "PASS_SELLABLE",
        "target_qty": str(target_qty),
        "sellable_qty": str(sellable_qty),
        "sellable_notional": str(sellable_notional),
        "price": str(price),
    }


def prepare_pilot_packet(
    config: RuntimeConfig,
    market_rules: MarketRules,
    current_price: Decimal,
    *,
    denied_markets: frozenset[str] | None = None,
) -> dict:
    """Generate prepare-only review packet without any trading execution."""
    if denied_markets is None:
        denied_markets = load_restrictions(Path("config/wallex-credit-market-policy.json"))

    sellability = evaluate_pilot_sellability(
        price=current_price,
        taker_fee_rate=market_rules.taker_fee_rate,
        step_size=market_rules.step_size,
        ceiling_tmn=PROPOSED_PILOT_CEILING_TMN,
        min_quantity=market_rules.min_quantity,
        min_notional=market_rules.min_notional,
    )

    is_denied = (
        market_rules.symbol in denied_markets
        or f"{market_rules.base_asset}/{market_rules.quote_asset}" in denied_markets
    )

    packet = {
        "kind": "TECHNICAL_MICRO_PILOT_REVIEW_PACKET",
        "stage": "PREPARE_ONLY",
        "symbol": market_rules.symbol,
        "base_asset": market_rules.base_asset,
        "quote_asset": market_rules.quote_asset,
        "market_denied_by_policy": is_denied,
        "proposed_parameters": {
            "max_buy_notional_tmn": str(PROPOSED_PILOT_CEILING_TMN),
            "min_quantity": str(market_rules.min_quantity),
            "min_notional_tmn": str(market_rules.min_notional),
            "step_size": str(market_rules.step_size),
            "tick_size": str(market_rules.tick_size),
            "maker_fee_rate": str(market_rules.maker_fee_rate),
            "taker_fee_rate": str(market_rules.taker_fee_rate),
            "stop_loss_threshold_pct": str(PROPOSED_STOP_LOSS_PCT),
            "stop_loss_disclaimer": "Threshold only; does not guarantee fill price during gaps/fast markets",
            "max_holding_seconds": PROPOSED_MAX_HOLDING_SECONDS,
            "max_active_orders": 1,
            "max_round_trips": 1,
        },
        "market_observation": {
            "current_price_tmn": str(current_price),
            "sellability_evaluation": sellability,
        },
        "gates_status": {
            "sellability_gate": sellability["status"],
            "market_policy_gate": "BLOCKED_DENIED" if is_denied else "PASS",
            "live_safety_gate": "BLOCKED_SAFETY_GATE (offline MockTransport only)",
        },
        "recommended_action": (
            "BLOCKED_MINIMUM: 200,000 TMN ceiling is below the 1.0 USDT minimum order size at current price. "
            "Do NOT silently raise ceiling. Human review required."
            if sellability["status"] == "BLOCKED_MINIMUM"
            else "READY_FOR_INTEGRATION_REVIEW"
        ),
    }
    return packet


def run_pilot_round_trip(
    broker: WallexLiveBroker,
    ledger: Ledger,
    rules: MarketRules,
    policy: RiskPolicy,
    current_price: Decimal,
    current_time: int,
    snapshot_sha256: str,
    *,
    client_id_prefix: str = "pilot",
) -> dict:
    """Execute at most 1 BUY and 1 EXIT SELL round-trip under strict reconciliation."""
    summary = {
        "orders_attempted": 0,
        "buy_settled": False,
        "sell_settled": False,
        "terminal_dust_base": "0",
        "terminal_cash_quote": "0",
        "status": "INITIALIZED",
    }

    # Step 1: Evaluate Risk for ENTER
    enter_decision = Decision(
        decision_id=f"dec_enter_{current_time}",
        symbol=rules.symbol,
        action="ENTER",
        cutoff=current_time,
        snapshot_sha256=snapshot_sha256,
        evidence_ids=("pilot_eval_evidence",),
        reason="Micro-pilot execution test entry",
        invalidation="Micro-pilot stop loss reached",
    )
    denied_markets = load_restrictions(broker.restrictions_path)
    risk_result = evaluate_risk(
        enter_decision,
        market_rules=rules,
        policy=policy,
        ledger=ledger,
        current_time=current_time,
        snapshot_sha256=snapshot_sha256,
        candle_close_time=current_time,
        current_price=current_price,
        denied_markets=denied_markets,
    )
    if not risk_result.approved:
        summary["status"] = f"RISK_REJECTED: {risk_result.reason}"
        return summary

    buy_client_id = f"{client_id_prefix}_buy_{current_time}"
    summary["orders_attempted"] += 1

    # Step 2: Submit BUY order
    buy_outcome = broker.submit_order(risk_result, client_id=buy_client_id, timestamp=current_time)
    if buy_outcome.get("status") not in ("FILLED", "PARTIALLY_FILLED"):
        summary["status"] = f"BUY_NOT_FILLED: {buy_outcome.get('status')}"
        return summary
    summary["buy_settled"] = True

    # Step 3: Evaluate Risk for EXIT
    exit_time = current_time + 60
    exit_decision = Decision(
        decision_id=f"dec_exit_{exit_time}",
        symbol=rules.symbol,
        action="EXIT",
        cutoff=exit_time,
        snapshot_sha256=snapshot_sha256,
        evidence_ids=("pilot_exit_evidence",),
        reason="Micro-pilot execution test exit",
        invalidation="Micro-pilot exit invalidation",
    )
    exit_risk = evaluate_risk(
        exit_decision,
        market_rules=rules,
        policy=policy,
        ledger=ledger,
        current_time=exit_time,
        snapshot_sha256=snapshot_sha256,
        candle_close_time=exit_time,
        current_price=current_price,
        denied_markets=denied_markets,
    )
    if not exit_risk.approved:
        summary["status"] = f"EXIT_RISK_REJECTED: {exit_risk.reason}"
        return summary

    sell_client_id = f"{client_id_prefix}_sell_{exit_time}"
    summary["orders_attempted"] += 1

    # Step 4: Submit EXIT SELL order
    sell_outcome = broker.submit_order(exit_risk, client_id=sell_client_id, timestamp=exit_time)
    if sell_outcome.get("status") not in ("FILLED", "PARTIALLY_FILLED"):
        summary["status"] = f"SELL_NOT_FILLED: {sell_outcome.get('status')}"
        return summary
    summary["sell_settled"] = True

    # Step 5: Report terminal inventory and remaining dust
    base_bal = ledger.get_balance(rules.base_asset)
    quote_bal = ledger.get_balance(rules.quote_asset)
    summary["terminal_dust_base"] = str(base_bal.total)
    summary["terminal_cash_quote"] = str(quote_bal.total)
    summary["status"] = "COMPLETE_ROUND_TRIP"
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true", help="Output fail-closed review packet without trading")
    parser.add_argument("--run", action="store_true", help="Execute pilot (blocked by live safety gate)")
    args = parser.parse_args(argv)

    if not args.prepare and not args.run:
        parser.print_help()
        return 0

    config = load_config()
    market_rules = MarketRules(
        symbol=PROPOSED_PILOT_SYMBOL,
        base_asset="USDT",
        quote_asset="TMN",
        tick_size=Decimal("1"),
        step_size=Decimal("0.01"),
        min_notional=PROPOSED_MIN_NOTIONAL,
        min_quantity=PROPOSED_MIN_QUANTITY,
        maker_fee_rate=Decimal("0.0025"),
        taker_fee_rate=Decimal("0.0030"),
    )

    # Use observed reference price if available
    ref_price = Decimal("266721")
    private_m_path = Path("data/private/market-usdttmn.json")
    if private_m_path.exists():
        try:
            m_data = json.loads(private_m_path.read_text(encoding="utf-8"))
            if "price" in m_data:
                ref_price = decimal_number(m_data["price"])
        except (OSError, ValueError):
            pass

    if args.prepare:
        packet = prepare_pilot_packet(config, market_rules, ref_price)
        output_path = Path(".local/parallel/live-pilot-review-packet.md")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Format markdown packet
        md_text = f"""# Micro-Pilot Review Packet — {time.strftime('%Y-%m-%d %H:%M:%SZ', time.gmtime())}

## 1. Executive Summary
- **Symbol:** `{packet['symbol']}`
- **Kind:** `{packet['kind']}`
- **Recommended Action:** `{packet['recommended_action']}`
- **Sellability Gate:** `{packet['gates_status']['sellability_gate']}`
- **Live Safety Gate:** `{packet['gates_status']['live_safety_gate']}`

## 2. Proposed Financial Envelope
- **Max Buy Notional:** `{packet['proposed_parameters']['max_buy_notional_tmn']} TMN`
- **Minimum Quantity:** `{packet['proposed_parameters']['min_quantity']} USDT`
- **Minimum Notional:** `{packet['proposed_parameters']['min_notional_tmn']} TMN`
- **Step Size:** `{packet['proposed_parameters']['step_size']}`
- **Tick Size:** `{packet['proposed_parameters']['tick_size']}`
- **Taker Fee:** `{packet['proposed_parameters']['taker_fee_rate']}`
- **Stop Loss Threshold:** `{packet['proposed_parameters']['stop_loss_threshold_pct']}` ({packet['proposed_parameters']['stop_loss_disclaimer']})
- **Max Holding Time:** `{packet['proposed_parameters']['max_holding_seconds']}s` (15 min)
- **Max Active Orders:** `{packet['proposed_parameters']['max_active_orders']}`
- **Max Round Trips:** `{packet['proposed_parameters']['max_round_trips']}`

## 3. Post-Fee Sellability Analysis
- **Current Market Price:** `{packet['market_observation']['current_price_tmn']} TMN`
- **Evaluation Status:** `{packet['market_observation']['sellability_evaluation']['status']}`
- **Reason:** {packet['market_observation']['sellability_evaluation']['reason']}

## 4. Operational Boundaries
- **Single Worker Lock:** Coordinated exclusively on local SQLite ledger path.
- **Durable Intent:** Recorded in SQLite before any HTTP attempt.
- **Fail-Closed Gate:** Production transport is strictly blocked. No real orders sent in this round.
"""
        output_path.write_text(md_text, encoding="utf-8")
        print(json.dumps(packet, indent=2))
        return 0

    if args.run:
        # Execution is deliberately safety-gated
        print(json.dumps({
            "status": "BLOCKED_SAFETY_GATE",
            "reason": "Production execution is blocked until integration review and explicit authorization",
            "sellability": evaluate_pilot_sellability(ref_price, market_rules.taker_fee_rate, market_rules.step_size),
        }, indent=2))
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
