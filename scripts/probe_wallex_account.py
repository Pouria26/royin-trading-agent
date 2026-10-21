"""Read-only credit-account discovery. Never activate credit, trade, or query main balances."""

import argparse
import json
from pathlib import Path

import httpx
from dotenv import set_key

from royin.config import load_config
from royin.market_data import decode_json
from royin.markets import parse_credit_balances


def read_account(client, endpoint, api_key, account_id=None):
    if endpoint not in ("/sub-accounts", "/v1/account/balances-detail", "/v1/account/fee"):
        raise ValueError("Not an allowed credit read endpoint")
    if endpoint != "/sub-accounts" and not account_id:
        raise ValueError("Credit account ID is required; main account fallback is forbidden")
    headers = {"x-api-key": api_key}
    if account_id:
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
    candidates = [r for r in rows if isinstance(r, dict) and r.get("type") == "prop"
                  and r.get("isActive") is True and r.get("isSuspend") is False
                  and isinstance(r.get("clientId"), str) and r["clientId"].strip()
                  and not any(ord(c) < 32 or ord(c) == 127 for c in r["clientId"])]
    if existing:
        candidates = [r for r in candidates if r["clientId"] == existing]
    if len(candidates) != 1:
        raise ValueError("No unique active credit account; no activation or fallback attempted")
    return candidates[0]["clientId"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Allow bounded authenticated GETs only")
    args = parser.parse_args(argv)
    if not args.run:
        parser.print_help()
        return 0
    report = {"kind": "READ_ONLY_CREDIT_ACCOUNT_NOT_TRADING_READINESS",
              "orders_sent": 0, "credit_activated": False}
    output = Path("data/private")
    try:
        config = load_config()
        if config.WALLEX_API_KEY is None:
            raise ValueError("Missing dedicated Wallex key")
        output.mkdir(parents=True, exist_ok=True)
        with httpx.Client(timeout=15, follow_redirects=False, trust_env=False) as client:
            payload = read_account(client, "/sub-accounts", config.WALLEX_API_KEY.get_secret_value())
            (output / "sub-accounts.json").write_text(json.dumps(payload, default=str), encoding="utf-8")
            if isinstance(payload.get("result"), list):
                report["subaccount_count"] = len(payload["result"])
            existing = (config.SUB_ACCOUNT_CLIENT_ID.get_secret_value()
                        if config.SUB_ACCOUNT_CLIENT_ID else None)
            account_id = choose_credit_account(payload, existing)
            if not existing:
                set_key(".env", "SUB_ACCOUNT_CLIENT_ID", account_id, quote_mode="always")
            report["account_id_saved_locally"] = True
            balances = read_account(client, "/v1/account/balances-detail",
                                    config.WALLEX_API_KEY.get_secret_value(), account_id)
            parsed = parse_credit_balances(balances)
            (output / "credit-balances.json").write_text(json.dumps(balances, default=str), encoding="utf-8")
            report["asset_count"] = len(parsed)
            report["has_nonzero_balance"] = any(b.total > 0 for b in parsed.values())

            # Also probe fee schedule if available
            try:
                fees = read_account(client, "/v1/account/fee",
                                    config.WALLEX_API_KEY.get_secret_value(), account_id)
                (output / "credit-fees.json").write_text(json.dumps(fees, default=str), encoding="utf-8")
                report["fee_schedule_available"] = True
            except (httpx.HTTPError, ValueError):
                report["fee_schedule_available"] = False

            report["status"] = "PASS_CREDIT_READ_ONLY_IDENTITY_NOT_CONTEST_VERIFIED"
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
