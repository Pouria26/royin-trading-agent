"""Read-only credit-account and market contract verification. Never activate credit, trade, or mutate .env."""

import argparse
import json
from decimal import ROUND_DOWN, Decimal
from pathlib import Path

import httpx

from royin.config import load_config
from royin.market_data import decimal_number, decode_json
from royin.markets import Balance, parse_credit_balances

ACCOUNT_MARKET_GET_CAP = 8
DOCS_GET_CAP = 4

ALLOWED_CREDIT_ENDPOINTS = (
    "/sub-accounts",
    "/v1/account/balances-detail",
    "/v1/account/fee",
    "/v1/account/openOrders",
    "/hector/web/v1/markets",
)


def read_account(client, endpoint, api_key=None, account_id=None):
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Allow bounded authenticated GETs only (cap 8)")
    args = parser.parse_args(argv)
    if not args.run:
        parser.print_help()
        return 0
    report = {
        "kind": "READ_ONLY_CREDIT_ACCOUNT_AND_MARKET_CONTRACT",
        "orders_sent": 0,
        "credit_activated": False,
        "env_modified": False,
        "gets_used": 0,
        "gets_cap": ACCOUNT_MARKET_GET_CAP,
    }
    output = Path("data/private")
    try:
        config = load_config()
        if config.WALLEX_API_KEY is None:
            raise ValueError("Missing dedicated Wallex key")
        output.mkdir(parents=True, exist_ok=True)
        gets_used = 0

        with httpx.Client(timeout=15, follow_redirects=False, trust_env=False) as client:
            # 1. Probe sub-accounts list
            if gets_used >= ACCOUNT_MARKET_GET_CAP:
                raise ValueError("GET cap reached")
            subaccounts_payload = read_account(client, "/sub-accounts", config.WALLEX_API_KEY.get_secret_value())
            gets_used += 1
            (output / "sub-accounts.json").write_text(json.dumps(subaccounts_payload, default=str), encoding="utf-8")
            rows = subaccounts_payload.get("result", [])
            report["subaccount_count"] = len(rows) if isinstance(rows, list) else 0

            existing = (
                config.SUB_ACCOUNT_CLIENT_ID.get_secret_value()
                if config.SUB_ACCOUNT_CLIENT_ID
                else None
            )
            account_id = choose_credit_account(subaccounts_payload, existing)
            report["account_id_matched"] = bool(existing and account_id == existing)

            # Extract subaccount metadata
            target_sub = next((r for r in rows if isinstance(r, dict) and r.get("clientId") == account_id), {})
            report["subaccount_type"] = target_sub.get("type")
            report["subaccount_active"] = target_sub.get("isActive")
            report["subaccount_suspended"] = target_sub.get("isSuspend")
            report["subaccount_created_at"] = target_sub.get("createdAt")

            # 2. Probe credit balances
            if gets_used >= ACCOUNT_MARKET_GET_CAP:
                raise ValueError("GET cap reached")
            balances = read_account(
                client, "/v1/account/balances-detail", config.WALLEX_API_KEY.get_secret_value(), account_id
            )
            gets_used += 1
            (output / "credit-balances.json").write_text(json.dumps(balances, default=str), encoding="utf-8")
            parsed_balances = parse_credit_balances(balances)
            report["asset_count"] = len(parsed_balances)
            tmn_bal = parsed_balances.get("TMN", Balance(Decimal(0), Decimal(0), Decimal(0)))
            usdt_bal = parsed_balances.get("USDT", Balance(Decimal(0), Decimal(0), Decimal(0)))
            report["tmn_balance"] = {
                "available": str(tmn_bal.available),
                "locked": str(tmn_bal.locked),
                "total": str(tmn_bal.total),
            }
            report["usdt_balance"] = {
                "available": str(usdt_bal.available),
                "locked": str(usdt_bal.locked),
                "total": str(usdt_bal.total),
            }

            # 3. Probe fee schedule
            if gets_used >= ACCOUNT_MARKET_GET_CAP:
                raise ValueError("GET cap reached")
            usdttmn_fee = None
            try:
                fees = read_account(client, "/v1/account/fee", config.WALLEX_API_KEY.get_secret_value(), account_id)
                gets_used += 1
                (output / "credit-fees.json").write_text(json.dumps(fees, default=str), encoding="utf-8")
                report["fee_schedule_available"] = True
                fee_result = fees.get("result", {})
                usdttmn_fee = fee_result.get("USDTTMN", {})
                report["usdttmn_fee"] = {
                    "makerFeeRate": usdttmn_fee.get("makerFeeRate"),
                    "takerFeeRate": usdttmn_fee.get("takerFeeRate"),
                }
            except (httpx.HTTPError, ValueError):
                report["fee_schedule_available"] = False

            # 4. Probe open orders for the credit subaccount
            if gets_used >= ACCOUNT_MARKET_GET_CAP:
                raise ValueError("GET cap reached")
            try:
                open_orders = read_account(
                    client, "/v1/account/openOrders", config.WALLEX_API_KEY.get_secret_value(), account_id
                )
                gets_used += 1
                (output / "open-orders.json").write_text(json.dumps(open_orders, default=str), encoding="utf-8")
                orders_list = open_orders.get("result", [])
                if isinstance(orders_list, dict):
                    orders_list = orders_list.get("orders", [])
                report["open_orders_count"] = len(orders_list) if isinstance(orders_list, list) else 0
            except (httpx.HTTPError, ValueError):
                report["open_orders_probed"] = False

            # 5. Probe market catalog for USDTTMN metadata
            if gets_used >= ACCOUNT_MARKET_GET_CAP:
                raise ValueError("GET cap reached")
            market_data = read_account(client, "/hector/web/v1/markets")
            gets_used += 1
            all_markets = market_data.get("result", {}).get("markets", [])
            usdttmn_m = next((m for m in all_markets if m.get("symbol") == "USDTTMN"), None)
            if usdttmn_m:
                (output / "market-usdttmn.json").write_text(json.dumps(usdttmn_m, default=str), encoding="utf-8")
                report["usdttmn_market"] = {
                    "price": str(usdttmn_m.get("price")),
                    "amount_precision": usdttmn_m.get("amount_precision"),
                    "price_precision": usdttmn_m.get("price_precision"),
                    "is_spot": usdttmn_m.get("is_spot"),
                    "is_market_type_enable": usdttmn_m.get("is_market_type_enable"),
                }

            # 6. Evaluate proposed pilot post-fee sellability test
            proposed_ceiling_tmn = Decimal("200000")
            min_notional = Decimal("100000")
            min_quantity = Decimal("1.0")
            if usdttmn_m and usdttmn_fee:
                price = decimal_number(usdttmn_m["price"])
                taker_fee_rate = decimal_number(usdttmn_fee["takerFeeRate"])
                amount_prec = int(usdttmn_m.get("amount_precision", 2))
                step_size = Decimal(10) ** -amount_prec
                price_prec = int(usdttmn_m.get("price_precision", 0))
                tick_size = Decimal(10) ** -price_prec

                raw_qty = proposed_ceiling_tmn / (price * (Decimal(1) + taker_fee_rate))
                target_qty = (raw_qty / step_size).quantize(Decimal("1"), rounding=ROUND_DOWN) * step_size
                net_base = target_qty * (Decimal(1) - taker_fee_rate)
                sellable_qty = (net_base / step_size).quantize(Decimal("1"), rounding=ROUND_DOWN) * step_size
                sellable_notional = sellable_qty * price

                if target_qty < min_quantity:
                    pilot_eval = {
                        "status": "BLOCKED_MINIMUM",
                        "reason": (
                            f"Proposed ceiling {proposed_ceiling_tmn} TMN yields {target_qty} USDT, "
                            f"which is below min_quantity {min_quantity} USDT at price {price} TMN"
                        ),
                        "target_qty": str(target_qty),
                        "min_quantity": str(min_quantity),
                        "current_price": str(price),
                        "step_size": str(step_size),
                        "tick_size": str(tick_size),
                    }
                elif sellable_qty < min_quantity or sellable_notional < min_notional:
                    pilot_eval = {
                        "status": "BLOCKED_MINIMUM",
                        "reason": (
                            f"Post-fee sellable quantity {sellable_qty} USDT ({sellable_notional} TMN) "
                            f"is below min_quantity {min_quantity} or min_notional {min_notional} TMN"
                        ),
                        "sellable_qty": str(sellable_qty),
                        "sellable_notional": str(sellable_notional),
                    }
                else:
                    pilot_eval = {
                        "status": "PASS_SELLABLE",
                        "target_qty": str(target_qty),
                        "sellable_qty": str(sellable_qty),
                    }
                report["proposed_pilot_evaluation"] = pilot_eval

            report["gets_used"] = gets_used
            report["status"] = "PASS_CREDIT_READ_ONLY_CONTRACT_VERIFIED"
    except httpx.HTTPStatusError as exc:
        report.update(status="BLOCKED", http_status=exc.response.status_code)
    except (httpx.HTTPError, ValueError, OSError) as exc:
        report.update(status="BLOCKED", error_type=type(exc).__name__)

    if output.exists():
        (output / "probe-report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    return 0 if report.get("status", "").startswith("PASS_") else 2


if __name__ == "__main__":
    raise SystemExit(main())
