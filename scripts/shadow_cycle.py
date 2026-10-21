"""Four-cycle bounded shadow simulation demonstrating deterministic matching, recovery, and host stop-loss."""

import json
from decimal import Decimal

from royin.broker import PaperBroker
from royin.decision import Decision
from royin.ledger import Ledger
from royin.market_data import Candle
from royin.risk import MarketRules, RiskPolicy, evaluate_risk


def run_shadow_4_cycles() -> dict:
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

    # Four consecutive closed 15m cycles
    candles = [
        Candle(1790970000, Decimal("60000"), Decimal("60200"), Decimal("59800"), Decimal("60100"), Decimal("100")),
        Candle(1790970900, Decimal("60100"), Decimal("60300"), Decimal("59900"), Decimal("60200"), Decimal("120")),
        Candle(1790971800, Decimal("60200"), Decimal("60400"), Decimal("58500"), Decimal("58800"), Decimal("250")),  # Drops to 58500 -> triggers stop!
        Candle(1790972700, Decimal("58800"), Decimal("59000"), Decimal("58600"), Decimal("58900"), Decimal("80")),
    ]

    ledger = Ledger(":memory:")
    ledger.set_balance("TMN", free=Decimal("5000000"))
    broker = PaperBroker(ledger, rules)

    log = []

    # Cycle 1: Candle 0 closes at 1790970900. ENTER decision.
    dec_1 = Decision(
        decision_id="shadow_dec_1",
        symbol="USDTTMN",
        action="ENTER",
        cutoff=1790970900,
        snapshot_sha256="d" * 64,
        evidence_ids=("EV_TREND_BULLISH", "EV_POSITION_FLAT"),
        reason="Shadow cycle 1: Bullish trend entry",
        invalidation="Trend reversal",
    )
    risk_1 = evaluate_risk(
        dec_1,
        market_rules=rules,
        policy=policy,
        ledger=ledger,
        current_time=1790970910,
        snapshot_sha256="d" * 64,
        candle_close_time=1790970900,
        current_price=candles[0].close,
        denied_markets=denied,
    )
    assert risk_1.approved, f"Risk rejected cycle 1: {risk_1.reason}"
    order_1 = broker.submit_order(risk_1, client_id="shadow_ord_1", timestamp=1790970910)
    log.append({"cycle": 1, "action": "ORDER_SUBMITTED", "client_id": order_1.client_id, "price": str(order_1.price)})

    # Cycle 2: Candle 1 (1790970900 -> 1790971800) matches order_1!
    filled_c2 = broker.process_candle(candles[1], candle_interval=900)
    log.append({"cycle": 2, "action": "CANDLE_MATCHED", "fills": filled_c2, "usdt_bal": str(ledger.get_balance("USDT").free)})

    # Cycle 3: Candle 2 drops sharply below stop price 58,998 (low = 58,500). Host stop triggers automatically WITHOUT calling LLM!
    filled_c3 = broker.process_candle(candles[2], candle_interval=900)
    log.append({"cycle": 3, "action": "STOP_LOSS_AUTOMATIC_TRIGGER", "fills": filled_c3, "usdt_bal": str(ledger.get_balance("USDT").total)})

    # Cycle 4: Candle 3 closes. Portfolio finalized idempotently.
    fin = broker.finalize_portfolio(current_price=candles[3].close, timestamp=1790973600, initial_capital=Decimal("5000000"))
    log.append({"cycle": 4, "action": "FINALIZED", "final_cash": fin["final_tmn_cash"], "realized_pnl": fin["total_realized_pnl"]})

    report = {
        "kind": "SHADOW_4_CYCLES_VERIFICATION",
        "symbol": "USDTTMN",
        "cycles_completed": 4,
        "host_stop_triggered_without_llm": any("stop_" in f for f in filled_c3),
        "final_cash_tmn": fin["final_tmn_cash"],
        "total_realized_pnl": fin["total_realized_pnl"],
        "log": log,
    }
    return report


if __name__ == "__main__":
    rep = run_shadow_4_cycles()
    print(json.dumps(rep, indent=2))
