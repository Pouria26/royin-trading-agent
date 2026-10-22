"""Read-only credit-account and market contract verification. Never activate credit, trade, or mutate .env."""

import argparse
import json
from pathlib import Path

import httpx

from royin.config import load_config
from royin.market_data import decode_json
from royin.markets import parse_credit_balances

ACCOUNT_MARKET_GET_CAP = 8
DOCS_GET_CAP = 4

ALLOWED_CREDIT_ENDPOINTS = (
    "/sub-accounts",
    "/v1/account/balances-detail",
    "/v1/account/fee",
    "/v1/account/openOrders",
    "/hector/web/v1/markets",
)


def read_account(client, endpoint, api_key=None, account_id=None, *, capture=None):
    if endpoint not in ALLOWED_CREDIT_ENDPOINTS:
        raise ValueError("Not an allowed credit read endpoint")
    if endpoint not in ("/sub-accounts", "/hector/web/v1/markets") and not account_id:
        raise ValueError("Credit account ID is required; main account fallback is forbidden")
    headers = {}
    if api_key and endpoint != "/hector/web/v1/markets":
        headers["x-api-key"] = api_key
    if account_id and endpoint in ("/v1/account/balances-detail", "/v1/account/fee", "/v1/account/openOrders"):
        headers["sub-account-client-id"] = account_id
    response = client.get("https://api.wallex.ir" + endpoint, headers=headers)
    if capture is not None:
        capture(response.content)
    response.raise_for_status()
    payload = decode_json(response.content)
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise ValueError("Unsuccessful credit read")
    return payload


def choose_credit_account(payload, existing=None):
    rows = payload.get("result")
    if not isinstance(rows, list):
        raise ValueError("Unknown sub-account list schema")
    pagination = payload.get("result_info", {})
    if not isinstance(pagination, dict) or pagination.get("total_count", len(rows)) != len(rows):
        raise ValueError("Sub-account list is incomplete; cannot select an account")
    candidates = [
        r
        for r in rows
        if isinstance(r, dict)
        and r.get("type") == "prop"
        and r.get("isActive") is True
        and r.get("isSuspend") is False
        and isinstance(r.get("clientId"), str)
        and r["clientId"].strip()
        and not any(ord(c) < 32 or ord(c) == 127 for c in r["clientId"])
    ]
    if existing:
        candidates = [r for r in candidates if r["clientId"] == existing]
    if len(candidates) != 1:
        raise ValueError("No unique active credit account; no activation or fallback attempted")
    return candidates[0]["clientId"]


def probe_credit_contract(config, client, output):
    """Bounded observations only; missing spot/order/expiry semantics remain NO-GO."""
    import hashlib
    import time
    from datetime import UTC, datetime

    output=Path(output)
    output.mkdir(parents=True,exist_ok=False)
    report=dict(kind="READ_ONLY_CREDIT_OBSERVATION_NOT_RELEASE",orders_sent=0,env_modified=False,
                gets_used=0,gets_cap=ACCOUNT_MARKET_GET_CAP,captures=[],errors=[],status="NO_GO")
    key=config.WALLEX_API_KEY.get_secret_value() if config.WALLEX_API_KEY else None
    if not key:
        raise ValueError("Dedicated credit key required")
    def get(endpoint, account_id=None):
        if report["gets_used"]>=ACCOUNT_MARKET_GET_CAP:
            raise ValueError("GET cap reached")
        report["gets_used"]+=1
        started=time.time()
        def capture(raw):
            sha=hashlib.sha256(raw).hexdigest()
            (output/(sha+".json")).write_bytes(raw)
            report["captures"].append(dict(endpoint=endpoint,raw_sha256=sha,
                received_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.time()-started))
        return read_account(client,endpoint,key,account_id,capture=capture)
    try:
        sub=get("/sub-accounts")
        existing=config.SUB_ACCOUNT_CLIENT_ID.get_secret_value() if config.SUB_ACCOUNT_CLIENT_ID else None
        account=choose_credit_account(sub,existing)
        row=next(r for r in sub["result"] if r.get("clientId")==account)
        report.update(account_id_matched=bool(existing and existing==account),active_credit_account=True,
            account_metadata_fields=sorted(k for k in row if k not in ("clientId","name","title")))
        balances=parse_credit_balances(get("/v1/account/balances-detail",account))
        report["balances"]={asset:dict(total=str(b.total),available=str(b.available),locked=str(b.locked))
                            for asset,b in balances.items() if asset in ("TMN","USDT")}
        for endpoint in ("/v1/account/fee","/v1/account/openOrders","/hector/web/v1/markets"):
            try:
                data=get(endpoint,account if endpoint!="/hector/web/v1/markets" else None)
                if endpoint.endswith("fee"):
                    from royin.markets import parse_fee_rates
                    maker,taker=parse_fee_rates(data,"USDTTMN")
                    report["usdttmn_fees"]=dict(maker=str(maker),taker=str(taker))
                elif endpoint.endswith("openOrders"):
                    rows=data.get("result")
                    if isinstance(rows,dict):
                        rows=rows.get("orders")
                    if not isinstance(rows,list):
                        raise ValueError("Unknown open orders schema")
                    info=data.get("result_info",{})
                    if not isinstance(info,dict) or info.get("total_count",len(rows))!=len(rows):
                        raise ValueError("Open orders pagination incomplete")
                    report["open_orders_count"]=len(rows)
                else:
                    from royin.markets import parse_catalog
                    market=parse_catalog(data).get("USDTTMN")
                    if market is None:
                        raise ValueError("Missing USDTTMN catalog row")
                    report["usdttmn_precision_observation"]=dict(is_spot=market.is_spot,
                        amount_precision=market.amount_precision,price_precision=market.price_precision)
            except (httpx.HTTPError,ValueError) as exc:
                report["errors"].append(dict(endpoint=endpoint,error_type=type(exc).__name__))
    except (httpx.HTTPError,ValueError) as exc:
        report["errors"].append(dict(error_type=type(exc).__name__))
    report["critical_unknowns"]=["account-active market universe and current package restrictions",
        "exchange-attested spot min_qty/min_notional/tick/step per symbol (OTC/precision are not proof)",
        "actual BUY/SELL feeAsset and rounding", "exact credit expiry", "private cumulative fill identity/completeness/finality"]
    report["status"]="NO_GO_CRITICAL_CONTRACT_UNKNOWN"
    (output/"probe-report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    return report


def main(argv=None):
    import uuid
    from datetime import UTC, datetime
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",action="store_true",help="Bounded authenticated GET observations only, maximum8")
    parser.add_argument("--env-file",type=Path)
    args=parser.parse_args(argv)
    if not args.run:
        parser.print_help()
        return 0
    try:
        config=load_config(args.env_file)
        output=Path("data/private")/(datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")+"_"+uuid.uuid4().hex[:8])
        with httpx.Client(timeout=10,follow_redirects=False,trust_env=False) as client:
            report=probe_credit_contract(config,client,output)
        print(json.dumps(report,indent=2))
    except (httpx.HTTPError,ValueError,OSError) as exc:
        print(json.dumps(dict(status="BLOCKED",error_type=type(exc).__name__,orders_sent=0)))
    return 2


if __name__=="__main__":
    raise SystemExit(main())
