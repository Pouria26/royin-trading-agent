"""Micro-pilot technical execution runner. Production is blocked until integrated review.

This runner is dedicated to technical execution verification (cumulative fills,
reconciliation, dust handling, and timeout), completely decoupled from strategy
alpha or profit claims. It strictly executes at most a single round-trip (1 BUY,
1 EXIT SELL) under host-enforced risk gates.
"""

import argparse
import json
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from pathlib import Path

from royin.config import RuntimeConfig
from royin.decision import Decision
from royin.ledger import Ledger, validate_decimal
from royin.markets import load_restrictions
from royin.risk import MarketRules, evaluate_risk

PROPOSED_PILOT_SYMBOL = "USDTTMN"
PROPOSED_PILOT_CEILING_TMN = Decimal("300000")
PROPOSED_MIN_QUANTITY = Decimal("1.0")
PROPOSED_MIN_NOTIONAL = Decimal("100000")
PROPOSED_STOP_LOSS_PCT = Decimal("0.02")  # 2% stop-loss threshold (not a guaranteed exit price)
PROPOSED_MAX_HOLDING_SECONDS = 900  # 15 minutes timeout before forced exit


class PilotExecutionError(Exception):
    """Failure or gate block during pilot execution."""


def evaluate_pilot_sellability(
    price, taker_fee_rate, step_size, ceiling_tmn=PROPOSED_PILOT_CEILING_TMN,
    min_quantity=PROPOSED_MIN_QUANTITY, min_notional=PROPOSED_MIN_NOTIONAL,
    *, fee_asset_scenario="BASE_BUY_QUOTE_SELL", exit_drawdown_pct=Decimal(0),
):
    """Scenario arithmetic only; actual fee asset/minimum/step require exchange evidence."""
    for name,value in (("price",price),("step",step_size),("ceiling",ceiling_tmn),
                       ("minimum quantity",min_quantity),("minimum notional",min_notional)):
        validate_decimal(value,name,strictly_positive=True)
    for value in (taker_fee_rate,exit_drawdown_pct):
        validate_decimal(value,"fraction")
        if value>=1:
            raise ValueError("Fee/drawdown fraction must be below one")
    if fee_asset_scenario not in ("BASE_BUY_QUOTE_SELL","QUOTE_BOTH","BASE_BOTH"):
        raise ValueError("Unknown fee asset scenario")
    def floor(q):
        return (q/step_size).to_integral_value(rounding=ROUND_DOWN)*step_size
    raw_qty=ceiling_tmn/(price*(1+taker_fee_rate))
    target_qty=floor(raw_qty)
    buy_base_fee=fee_asset_scenario!="QUOTE_BOTH"
    sell_base_fee=fee_asset_scenario=="BASE_BOTH"
    net_base=target_qty*(1-taker_fee_rate) if buy_base_fee else target_qty
    sellable_qty=floor(net_base/(1+taker_fee_rate) if sell_base_fee else net_base)
    residual=net_base-sellable_qty*(1+taker_fee_rate if sell_base_fee else 1)
    stress_price=price*(1-exit_drawdown_pct)
    sellable_notional=sellable_qty*stress_price
    debit=target_qty*price*(1 if buy_base_fee else 1+taker_fee_rate)
    passed=(target_qty>=min_quantity and target_qty*price>=min_notional
            and sellable_qty>=min_quantity and sellable_notional>=min_notional and debit<=ceiling_tmn)
    return dict(status="PASS_SELLABLE" if passed else "BLOCKED_MINIMUM",
        reason=("Scenario satisfies both buy/sell minimums; residual is not zero by implication" if passed
                else f"Scenario quantity {target_qty} / sellable {sellable_qty} is below min_quantity {min_quantity} or min_notional {min_notional}"),
        target_qty=str(target_qty),sellable_qty=str(sellable_qty),sellable_notional=str(sellable_notional),
        price=str(price),cash_debit_tmn=str(debit),residual_base=str(residual),residual_value_tmn=str(residual*stress_price),
        net_liquidation_tmn=str(sellable_notional*(1 if sell_base_fee else 1-taker_fee_rate)),
        fee_asset_scenario=fee_asset_scenario,exit_drawdown_pct=str(exit_drawdown_pct),
        evidence_kind="SCENARIO_ASSUMPTIONS_NOT_EXCHANGE_RULES")


def prepare_pilot_packet(
    config: RuntimeConfig,
    market_rules: MarketRules,
    current_price: Decimal,
    *,
    ceiling_tmn: Decimal = PROPOSED_PILOT_CEILING_TMN,
    denied_markets: frozenset[str] | None = None,
) -> dict:
    """Generate prepare-only review packet without any trading execution."""
    if denied_markets is None:
        denied_markets = load_restrictions(Path("config/wallex-credit-market-policy.json"))

    sellability = evaluate_pilot_sellability(
        price=current_price,
        taker_fee_rate=market_rules.taker_fee_rate,
        step_size=market_rules.step_size,
        ceiling_tmn=ceiling_tmn,
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
        "release_options": [
            {"kind":"TECHNICAL_EXECUTION_PILOT","status":"NO_GO","strategy_profit_evidence":False},
            {"kind":"FIRST_AI_STRATEGY_TRADE","status":"NO_GO","requires":"fresh verified setup and real A decision; WAIT when absent"},
        ],
        "symbol": market_rules.symbol,
        "base_asset": market_rules.base_asset,
        "quote_asset": market_rules.quote_asset,
        "market_denied_by_policy": is_denied,
        "proposed_parameters": {
            "max_buy_notional_tmn": str(ceiling_tmn),
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
            "max_positions": 1,
            "max_orders": 2,
            "quote_max_age_seconds": 5,
            "order_ttl_seconds": 30,
            "max_http_attempts": 8,
            "cash_debit_ceiling_tmn":str(ceiling_tmn),
            "averaging_or_auto_size_increase":False,
            "exit_loss_threshold_estimate_tmn":str(ceiling_tmn*(PROPOSED_STOP_LOSS_PCT+2*market_rules.taker_fee_rate)),
            "expiry_utc":None,
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
        "critical_unknowns": ["spot minimum/step attestation", "feeAsset", "account expiry", "exchange fill finality"],
        "release_status": "NO_GO",
        "recommended_action": (
            f"BLOCKED_MINIMUM: {ceiling_tmn} TMN ceiling is below the 1.0 USDT minimum order size at current price. "
            "Do NOT silently raise ceiling. Human review required."
            if sellability["status"] == "BLOCKED_MINIMUM"
            else "NO_GO_CRITICAL_CONTRACT_UNKNOWN"
        ),
    }
    return packet


def run_pilot_round_trip(broker, ledger, rules, policy, current_price, current_time,
                         snapshot_sha256, *, client_id_prefix="pilot", exit_quote=None):
    """One restartable technical step; never invent an exit quote or treat partial as settled."""
    import hashlib
    from dataclasses import asdict
    if type(current_time) is not int or current_time<=0:
        raise ValueError("Explicit current clock required")
    validate_decimal(current_price,"current price",strictly_positive=True)
    binding=hashlib.sha256(json.dumps([asdict(rules),asdict(policy)],default=str,sort_keys=True).encode()).hexdigest()
    key="pilot_"+client_id_prefix
    state=json.loads(ledger.get_meta(key) or "null")
    if state is None:
        state=dict(binding=binding,buy_id=f"{client_id_prefix}_buy_{current_time}",sell_id=f"{client_id_prefix}_sell_{current_time}",
                   stage="BUY",orders_attempted=0,http_attempts=0,buy_settled=False,sell_settled=False,
                   started_at=current_time,cancel_requested=[],reconciliations=0,status="INITIALIZED")
        ledger.set_meta(key,json.dumps(state))
    if state["binding"]!=binding:
        raise ValueError("Pilot policy/rules changed; no restart reset")
    if state["stage"]=="DONE":
        return state
    if state["http_attempts"]>=8:
        return {**state,"status":"BLOCKED_REQUEST_CAP_RECONCILIATION_REQUIRED"}
    stage=state["stage"]
    cid=state["buy_id"] if stage=="BUY" else state["sell_id"]
    with ledger.connection() as db:
        existing=db.execute("SELECT status,created_at FROM live_broker_orders WHERE client_id=?",(cid,)).fetchone()
    if existing is None:
        if stage=="SELL":
            if exit_quote is None:
                return {**state,"status":"AWAIT_FRESH_EXIT_QUOTE"}
            price=exit_quote["price"]
            quote_time=exit_quote["timestamp"]
            validate_decimal(price,"exit price",strictly_positive=True)
            if type(quote_time) is not int or not 0<=current_time-quote_time<=5:
                raise ValueError("Stale/future exit quote")
        else:
            price=current_price
        action="ENTER" if stage=="BUY" else "EXIT"
        decision=Decision(decision_id=cid,symbol=rules.symbol,action=action,cutoff=current_time,
            snapshot_sha256=snapshot_sha256,evidence_ids=("TECHNICAL_PILOT_NOT_STRATEGY",),
            reason="Technical execution verification, not strategy alpha",invalidation="Host policy/deadline")
        risk=evaluate_risk(decision,market_rules=rules,policy=policy,ledger=ledger,current_time=current_time,
            snapshot_sha256=snapshot_sha256,candle_close_time=current_time,current_price=price,
            denied_markets=load_restrictions(broker.restrictions_path))
        if not risk.approved:
            return {**state,"status":"RISK_REJECTED: "+risk.reason}
        state["orders_attempted"]+=1
        state["http_attempts"]+=1
        ledger.set_meta(key,json.dumps(state))
        outcome=broker.submit_order(risk,client_id=cid,timestamp=current_time)
    else:
        state["http_attempts"]+=1
        expired=current_time>=existing[1]+30
        cancel=expired and state["reconciliations"]>0 and existing[0] not in ("FILLED","CANCELED","PARTIALLY_FILLED_CANCELED") and cid not in state["cancel_requested"]
        if cancel:
            state["cancel_requested"].append(cid)
        else:
            state["reconciliations"]+=1
        ledger.set_meta(key,json.dumps(state))
        if cancel:
            state["last_exchange_observation"] = broker.cancel_order(cid,timestamp=current_time)
            state["status"] = "CANCEL_ATTEMPTED_RECONCILIATION_REQUIRED"
            ledger.set_meta(key,json.dumps(state))
            return state
        outcome=broker.reconcile_order(cid,timestamp=current_time)
    state["last_exchange_observation"] = outcome
    terminal=outcome.get("status") in ("FILLED","CANCELED","PARTIALLY_FILLED_CANCELED")
    state["status"]=("BUY" if stage=="BUY" else "SELL")+"_"+outcome.get("status","UNKNOWN")
    if terminal:
        if stage=="BUY":
            state["buy_settled"]=True
            if ledger.get_balance(rules.base_asset).total>0:
                state.update(stage="SELL",status="AWAIT_FRESH_EXIT_QUOTE")
            else:
                state.update(stage="DONE",status="COMPLETE_NO_FILL")
        elif ledger.get_balance(rules.base_asset).total==0:
            state.update(stage="DONE",status="COMPLETE_ROUND_TRIP",sell_settled=True)
        else:
            state.update(stage="DONE",status="RECONCILIATION_OR_RESIDUAL_REQUIRED",sell_settled=False)
    state.update(terminal_dust_base=str(ledger.get_balance(rules.base_asset).total),
                 terminal_cash_quote=str(ledger.get_balance(rules.quote_asset).total))
    ledger.set_meta(key,json.dumps(state))
    return state


def run_functional_demo():
    """Frozen synthetic monetary scenarios, never a statistical strategy success estimate."""
    from royin.broker import PaperBroker
    from royin.risk import PositionProtectionPolicy, RiskResult
    cases=[("checkpoint_then_trailing",[(103000,1010),(104000,1020),(102000,1030)],"5002686.306",0),
           ("gap_through_stop",[(90000,1010)],"4978770.270",0),
           ("hard_holding_without_model",[(101000,1400)],"5000693.3030",0),
           ("no_forced_target",[(103000,1010)],"4799400",2)]
    reports=[]
    for name,quotes,expected_cash,expected_base in cases:
        ledger=Ledger()
        rules=MarketRules("USDTTMN","USDT","TMN",Decimal(1),Decimal(".01"),Decimal(100000),Decimal(1),Decimal(".003"),Decimal(".003"))
        protection=PositionProtectionPolicy(Decimal(".02"),Decimal(".01"),Decimal(".025"),30,300,2000,10,5,Decimal(10000))
        ledger.initialize_portfolio(Decimal(5000000),quote_asset="TMN",binding=protection.sha256)
        broker=PaperBroker(ledger,rules)
        broker.submit_order(RiskResult(True,"synthetic","ENTER",rules.symbol,Decimal(2),Decimal(100000),Decimal(98000),Decimal(600)),
                            client_id="synthetic_buy",timestamp=1000)
        broker.reconcile_order("synthetic_buy",simulated_state="FILLED",timestamp=1001)
        broker.arm_protection(protection,opened_at=1001,entry_price=Decimal(100000))
        events=[]
        for price,timestamp in quotes:
            events.append(broker.observe_quote(Decimal(price),source_time=timestamp,received_at=timestamp,now=timestamp,policy=protection))
        view=broker.export_state(Decimal(quotes[-1][0]),now=quotes[-1][1])
        passed=ledger.get_balance("TMN").free==Decimal(expected_cash) and ledger.get_balance("USDT").total==Decimal(expected_base)
        reports.append(dict(name=name,passed=passed,expected_cash_tmn=expected_cash,events=events,state=view))
    count=sum(case["passed"] for case in reports)
    return dict(status="PASS_SYNTHETIC_FUNCTIONAL" if count==len(reports) else "FAIL",evidence_kind="SYNTHETIC_HAND_ORACLES",
        checks_passed=count,checks_total=len(reports),technical_success_pct=str(Decimal(count)*100/len(reports)),
        trading_win_rate_pct=None,statistical_success_probability=None,reason="Curated correctness cases are not a sample of strategy trades",
        initial_capital_per_independent_scenario_tmn="5000000",actual_gets=0,actual_posts=0,actual_deletes=0,model_calls=0,cases=reports)


def main(argv=None):
    import uuid
    from datetime import UTC, datetime
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument("--prepare",action="store_true",help="Review NO-GO packet; optional explicitly hypothetical price")
    mode.add_argument("--run",action="store_true",help="Production remains blocked before I/O")
    mode.add_argument("--self-check",action="store_true",help="Offline functional scenarios and monetary hand oracles")
    parser.add_argument("--ceiling",default="300000")
    parser.add_argument("--price",help="Explicit hypothetical TMN price, not a current market attestation")
    args=parser.parse_args(argv)
    if args.run:
        print(json.dumps(dict(status="BLOCKED_SAFETY_GATE",reason="Critical exchange contract and integrated release approval absent",orders_sent=0)))
        return 2
    if not args.prepare and not args.self_check:
        parser.print_help()
        return 0
    if args.self_check:
        report=run_functional_demo()
    else:
        try:
            ceiling=Decimal(args.ceiling)
            validate_decimal(ceiling,"cash debit ceiling",strictly_positive=True)
            if args.price is None:
                report=dict(status="NO_GO",quote_status="UNKNOWN_NO_CURRENT_QUOTE",orders_sent=0,
                    critical_unknowns=["current quote","spot rules","feeAsset","expiry","fill finality","integrated release"])
            else:
                price=Decimal(args.price)
                rules=MarketRules("USDTTMN","USDT","TMN",Decimal(1),Decimal(".01"),PROPOSED_MIN_NOTIONAL,
                    PROPOSED_MIN_QUANTITY,Decimal(".0025"),Decimal(".003"))
                report=prepare_pilot_packet(RuntimeConfig(),rules,price,ceiling_tmn=ceiling)
                report.update(quote_status="HYPOTHETICAL_NOT_CURRENT",rule_evidence="SYNTHETIC_NOT_VERIFIED")
        except (ValueError,InvalidOperation) as exc:
            parser.error("Invalid hypothetical decimal: "+type(exc).__name__)
    directory=Path(".local/parallel")
    directory.mkdir(parents=True,exist_ok=True)
    path=directory/("execution-check-"+datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")+"_"+uuid.uuid4().hex[:8]+".json")
    with path.open("x",encoding="utf-8") as out:
        json.dump(report,out,indent=2)
    print(json.dumps(dict(report=report,artifact=str(path)),indent=2))
    return 0 if report.get("status")=="PASS_SYNTHETIC_FUNCTIONAL" else 2


if __name__=="__main__":
    raise SystemExit(main())
