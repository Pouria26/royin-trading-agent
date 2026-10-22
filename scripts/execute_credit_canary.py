"""One100k-TMN technical canary, not an AI strategy or a general live-trading switch."""

import argparse
import hashlib
import json
import sqlite3
import time
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

import httpx

from royin.canary import CreditCanaryTransport, canary_state_path, clean_revision
from royin.config import load_config
from royin.ledger import Ledger
from royin.live_broker import WallexLiveBroker
from royin.market_data import decimal_number, decode_json
from royin.markets import (
    load_restrictions,
    parse_catalog,
    parse_credit_balances,
    parse_fee_rates,
    parse_spot_rules,
)
from royin.risk import RiskPolicy
from scripts.probe_wallex_account import choose_credit_account
from scripts.run_live_pilot import evaluate_pilot_sellability, run_pilot_round_trip

ROOT = Path(__file__).resolve().parents[1]


class CanaryReads:
    def __init__(self, config, output, client):
        self.config, self.output, self.client = config, output, client
        self.attempts = 0
        self.captures = []

    def get(self, path, *, private=False, params=None):
        if path not in ("/sub-accounts","/v1/account/balances-detail","/v1/account/fee",
                        "/v1/account/openOrders","/hector/web/v1/markets","/v1/markets","/v1/depth"):
            raise ValueError("Unscoped canary read")
        if self.attempts >= 18:
            raise ValueError("Canary read allowance exhausted")
        self.attempts += 1
        headers = {}
        if private:
            if not self.config.WALLEX_API_KEY or not self.config.SUB_ACCOUNT_CLIENT_ID:
                raise ValueError("Dedicated credit credentials required")
            headers = {"x-api-key":self.config.WALLEX_API_KEY.get_secret_value()}
            if path != "/sub-accounts":
                headers["sub-account-client-id"] = self.config.SUB_ACCOUNT_CLIENT_ID.get_secret_value()
        response = self.client.get("https://api.wallex.ir"+path,params=params,headers=headers)
        sha = hashlib.sha256(response.content).hexdigest()
        (self.output/(sha+".json")).write_bytes(response.content)
        self.captures.append(dict(path=path,sha256=sha,received_at=int(time.time()),status=response.status_code))
        response.raise_for_status()
        data = decode_json(response.content)
        if not isinstance(data,dict) or data.get("success") is not True:
            raise ValueError("Unsuccessful canary read")
        return data

    def quote(self):
        data = self.get("/v1/depth",params={"symbol":"USDTTMN"})
        book = data["result"]
        bids = [(decimal_number(r["price"],positive=True),decimal_number(r["quantity"],positive=True)) for r in book["bid"]]
        asks = [(decimal_number(r["price"],positive=True),decimal_number(r["quantity"],positive=True)) for r in book["ask"]]
        bid, ask = max(p for p,q in bids), min(p for p,q in asks)
        if bid >= ask or (ask-bid)/bid > Decimal(".002"):
            raise ValueError("Crossed or wide canary book")
        if min(sum((p*q for p,q in bids if p>=bid*Decimal(".999")),Decimal(0)),
               sum((p*q for p,q in asks if p<=ask*Decimal("1.001")),Decimal(0))) < Decimal(300000):
            raise ValueError("Insufficient observed canary depth")
        return bid,ask,int(time.time()),hashlib.sha256(json.dumps(data,default=str,sort_keys=True).encode()).hexdigest()


def preflight(reads, config, *, resumed=False, known_ids=()):
    account = config.SUB_ACCOUNT_CLIENT_ID.get_secret_value() if config.SUB_ACCOUNT_CLIENT_ID else None
    if not account or choose_credit_account(reads.get("/sub-accounts",private=True),account) != account:
        raise ValueError("Dedicated active credit identity mismatch")
    balances = parse_credit_balances(reads.get("/v1/account/balances-detail",private=True))
    orders = reads.get("/v1/account/openOrders",private=True)
    rows = orders.get("result")
    rows = rows.get("orders") if isinstance(rows,dict) else rows
    info = orders.get("result_info",{})
    if (not isinstance(rows,list) or not isinstance(info,dict) or info.get("total_count",len(rows)) != len(rows)
            or any(r.get("clientOrderId") not in known_ids for r in rows)):
        raise ValueError("Unscoped or incomplete account open orders")
    if not resumed and (balances["TMN"].available < Decimal(100000)
                        or any(b.locked or (a!="TMN" and b.total) for a,b in balances.items())):
        raise ValueError("Fresh canary requires cash-only dedicated account")
    maker,taker = parse_fee_rates(reads.get("/v1/account/fee",private=True),"USDTTMN")
    if maker != Decimal(".0025") or taker != Decimal(".003"):
        raise ValueError("Credit fee observation changed; re-review required")
    rules = parse_spot_rules(reads.get("/v1/markets"),maker_fee_rate=maker,taker_fee_rate=taker)["USDTTMN"]
    catalog = parse_catalog(reads.get("/hector/web/v1/markets"))
    if not catalog["USDTTMN"].is_spot or "USDT/TMN" in load_restrictions(ROOT/"config/wallex-credit-market-policy.json"):
        raise ValueError("Canary market unavailable or restricted")
    if not resumed and (config.CHALLENGE_END_AT is None or int(config.CHALLENGE_END_AT.timestamp()) < int(time.time())+900):
        raise ValueError("Insufficient verified contest time for the technical canary")
    return rules,balances


def run(execute=False):
    import uuid
    config = load_config()
    revision = clean_revision(ROOT) if execute else None
    output = ROOT/"data/private"/("canary-review-"+str(int(time.time()))+"-"+uuid.uuid4().hex[:8])
    output.mkdir(parents=True,exist_ok=False)
    report = dict(kind="TECHNICAL_CANARY_NOT_STRATEGY_ALPHA",status="IN_PROGRESS",revision=revision,
                  cash_debit_ceiling_tmn="100000",observations=[],orders_attempted=0)
    ledger = None
    try:
        if execute:
            ledger = Ledger(canary_state_path(config))
        with httpx.Client(timeout=10,follow_redirects=False,trust_env=False) as client:
            reads = CanaryReads(config,output,client)
            # Preparation never creates or resets the financial state file.
            fingerprint = hashlib.sha256(config.SUB_ACCOUNT_CLIENT_ID.get_secret_value().encode()).hexdigest() if config.SUB_ACCOUNT_CLIENT_ID else ""
            from contextlib import nullcontext
            worker = ledger.worker(account_fingerprint=fingerprint,lock_directory=Path.home()/".royin-credit-locks") if ledger else nullcontext()
            with worker:
                previous = json.loads(ledger.get_meta("canary_binding") or "null") if ledger else None
                known_ids = ()
                if ledger:
                    with ledger.connection() as db:
                        known_ids = tuple(r[0] for r in db.execute("SELECT client_id FROM order_intents"))
                rules,balances = preflight(reads,config,resumed=previous is not None,known_ids=known_ids)
                bid,ask,quote_time,quote_sha = reads.quote()
                entry = rules.quantize_price(ask*Decimal("1.0005"))
                sellability = evaluate_pilot_sellability(entry,rules.taker_fee_rate,rules.step_size,
                    Decimal(100000),rules.min_quantity,rules.min_notional,exit_drawdown_pct=Decimal(".02"))
                report.update(rules=asdict(rules),sellability=sellability,read_captures=reads.captures,
                              quote_time=quote_time,quote_sha256=quote_sha)
                if sellability["status"] != "PASS_SELLABLE":
                    raise ValueError("100k TMN is not buyable and sellable under observed rules")
                if not execute:
                    report["status"] = "PREPARED_TECHNICAL_CANARY_ONLY"
                else:
                    expires = previous["expires_at"] if previous else int(time.time())+600
                    if previous and previous["revision"] != revision:
                        raise ValueError("Canary source changed; do not reinterpret an existing financial run")
                    if not previous:
                        previous = dict(revision=revision,expires_at=expires,initial_tmn=str(balances["TMN"].total))
                        with ledger.transaction():
                            ledger.initialize_portfolio(Decimal(100000),quote_asset="TMN",binding=hashlib.sha256(json.dumps(previous,sort_keys=True).encode()).hexdigest())
                            ledger.set_meta("canary_binding",json.dumps(previous))
                    scoped = config.model_copy(update={"WALLEX_ALLOWED_MARKETS":("USDTTMN",)})
                    transport = CreditCanaryTransport(ledger,rules,scoped,revision=revision,expires_at=expires)
                    policy = RiskPolicy(Decimal(100000),Decimal(100000),Decimal(".02"),Decimal(".05"),expires,
                                        min_seconds_before_deadline=0,max_stale_seconds=5)
                    with httpx.Client(transport=transport,timeout=10,follow_redirects=False,trust_env=False) as orders_client:
                        broker = WallexLiveBroker(ledger,rules,scoped,http_client=orders_client,
                            enable_live_trading=True,run_mode="live",restrictions_path=ROOT/"config/wallex-credit-market-policy.json")
                        for _ in range(8):
                            bid,ask,now,sha = reads.quote()
                            state = run_pilot_round_trip(broker,ledger,rules,policy,rules.quantize_price(ask*Decimal("1.0005")),now,sha,
                                client_id_prefix="credit_canary",exit_quote=dict(price=rules.quantize_price(bid*Decimal(".9995")),timestamp=now))
                            report["observations"].append(state)
                            report["orders_attempted"] = state["orders_attempted"]
                            if state["stage"] == "DONE" or state["http_attempts"] >= 8 or state["status"].startswith("RISK_REJECTED"):
                                break
                            time.sleep(10)
                    report["status"] = state["status"]
                    final = parse_credit_balances(reads.get("/v1/account/balances-detail",private=True))
                    report["account_cash_delta_tmn"] = str(final["TMN"].total-Decimal(previous["initial_tmn"]))
                    report["residual_usdt"] = str(final.get("USDT").total) if final.get("USDT") else "0"
                    report["local_balances"] = {a:dict(free=str(b.free),locked=str(b.locked)) for a,b in ledger.get_all_balances().items()}
                    expected_cash = Decimal(previous["initial_tmn"])-Decimal(100000)+ledger.get_balance("TMN").total
                    expected_base = ledger.get_balance("USDT").total
                    reconciled = final["TMN"].total == expected_cash and final.get("USDT") is not None and final["USDT"].total == expected_base
                    report["account_reconciliation"] = "MATCH" if reconciled else "MISMATCH"
                    if not reconciled:
                        report["status"] = "ACCOUNT_RECONCILIATION_REQUIRED"
    except (httpx.HTTPError,ValueError,KeyError,TypeError,OSError,ArithmeticError,sqlite3.Error) as exc:
        report.update(status="BLOCKED_OR_RECONCILIATION_REQUIRED",error_type=type(exc).__name__)
    finally:
        (output/"report.json").write_text(json.dumps(report,default=str,indent=2),encoding="utf-8")
    print(json.dumps(dict(status=report["status"],orders_attempted=report["orders_attempted"],report=str(output/"report.json"))))
    return 0 if report["status"] in ("PREPARED_TECHNICAL_CANARY_ONLY","COMPLETE_ROUND_TRIP") else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    flags = parser.add_mutually_exclusive_group()
    flags.add_argument("--prepare",action="store_true",help="Bounded reads, no order transport")
    flags.add_argument("--execute",action="store_true",help="One scoped real credit-account technical round trip")
    args = parser.parse_args(argv)
    if not args.prepare and not args.execute:
        parser.print_help()
        return 0
    return run(args.execute)


if __name__ == "__main__":
    raise SystemExit(main())
