"""Restricted, durable transport for one small technical credit-account round trip."""

import hashlib
import json
import re
import subprocess
import time
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

import httpx

from royin.market_data import decimal_number, decode_json


def clean_revision(root):
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True)
    if dirty or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Canary execution requires a clean committed revision")
    return revision


class CreditCanaryTransport(httpx.BaseTransport):
    """Only known LIMIT intents; two POSTs/100k TMN/eight HTTP attempts, across restart.

    This is not the general live strategy transport. The caller holds the shared
    account worker lock throughout the pilot, including reconciliation and sleep.
    """

    def __init__(self, ledger, rules, config, *, revision, expires_at, inner=None):
        now = int(time.time())
        if (ledger.db_path == ":memory:" or not config.WALLEX_API_KEY
                or not config.SUB_ACCOUNT_CLIENT_ID or rules.symbol != "USDTTMN"
                or rules.quote_asset != "TMN" or rules.base_asset != "USDT"
                or not re.fullmatch(r"[0-9a-f]{40}", revision)
                or type(expires_at) is not int or expires_at <= 0):
            raise ValueError("Invalid dedicated canary binding")
        if config.CHALLENGE_END_AT is None or expires_at >= int(config.CHALLENGE_END_AT.timestamp()):
            raise ValueError("Canary must finish before the explicit contest deadline")
        self.ledger, self.rules, self.config = ledger, rules, config
        self.account_fingerprint = hashlib.sha256(config.SUB_ACCOUNT_CLIENT_ID.get_secret_value().encode()).hexdigest()
        binding = dict(revision=revision, account=self.account_fingerprint, expires_at=expires_at,
                       rules=asdict(rules), ceiling_tmn="100000")
        self.binding = json.dumps(binding, default=str, sort_keys=True)
        self.state_key = "credit_canary_transport"
        saved = ledger.get_meta(self.state_key)
        if saved is None:
            if not now < expires_at <= now+600:
                raise ValueError("New canary permit must expire within600 seconds")
            ledger.set_meta(self.state_key, json.dumps(dict(binding=self.binding, attempts=0, buy=0, sell=0)))
        elif json.loads(saved)["binding"] != self.binding:
            raise ValueError("Canary binding changed; no restart reset")
        self.expires_at = expires_at
        self.inner = inner if inner is not None else httpx.HTTPTransport(retries=0, trust_env=False)

    def handle_request(self, request):
        if (not self.ledger._worker_active
                or getattr(self.ledger,"_worker_account_fingerprint",None) != self.account_fingerprint):
            raise ValueError("Shared account worker lock required")
        url = request.url
        if (url.scheme != "https" or url.host != "api.wallex.ir" or url.port not in (None,443)
                or url.query or url.fragment or url.username or url.password
                or request.headers.get("x-api-key") != self.config.WALLEX_API_KEY.get_secret_value()
                or request.headers.get("sub-account-client-id") != self.config.SUB_ACCOUNT_CLIENT_ID.get_secret_value()):
            raise ValueError("Unscoped canary request")
        method = request.method
        payload = decode_json(request.content) if method == "POST" else None
        if method == "POST" and url.path == "/v1/account/orders":
            if not isinstance(payload,dict) or set(payload) != {"client_id","symbol","side","type","price","quantity"}:
                raise ValueError("Invalid canary order payload")
            cid = payload["client_id"]
        elif method in ("GET","DELETE") and re.fullmatch(r"/v1/account/orders/[A-Za-z0-9_]{1,64}",url.path):
            cid = url.path.rsplit("/",1)[1]
        else:
            raise ValueError("Canary endpoint/method forbidden")
        with self.ledger.transaction() as db:
            row = db.execute("SELECT symbol,side,price,quantity FROM order_intents WHERE client_id=?",(cid,)).fetchone()
            if not row or row[0] != self.rules.symbol:
                raise ValueError("No matching durable canary intent")
            state = json.loads(self.ledger.get_meta(self.state_key))
            if state["binding"] != self.binding or state["attempts"] >= 8:
                raise ValueError("Canary request allowance exhausted or binding changed")
            if method == "POST":
                symbol, side, price, quantity = row
                if (payload["symbol"] != symbol or payload["side"] != side or payload["type"] != "LIMIT"
                        or decimal_number(payload["price"]) != Decimal(price)
                        or decimal_number(payload["quantity"]) != Decimal(quantity)):
                    raise ValueError("Canary intent/payload mismatch")
                if side == "BUY":
                    if int(time.time()) >= self.expires_at or state["buy"] or state["sell"]:
                        raise ValueError("Canary BUY expired or already attempted")
                    if Decimal(price)*Decimal(quantity)*(1+self.rules.taker_fee_rate) > Decimal(100000):
                        raise ValueError("Canary exceeds100000 TMN cash debit")
                    state["buy"] += 1
                elif side == "SELL":
                    if state["buy"] != 1 or state["sell"]:
                        raise ValueError("Canary SELL is not a single owned-position exit")
                    state["sell"] += 1
                else:
                    raise ValueError("Unknown canary side")
            state["attempts"] += 1
            self.ledger.set_meta(self.state_key,json.dumps(state))
        # Attempt counters commit before any socket operation. Never refund ambiguity.
        directory = Path(self.ledger.db_path).parent/"captures"
        directory.mkdir(parents=True,exist_ok=True)
        observation = dict(attempt=state["attempts"],method=method,path=url.path,observed_at=int(time.time()))
        try:
            response = self.inner.handle_request(request)
        except httpx.HTTPError as exc:
            observation["error_type"] = type(exc).__name__
            with (directory/f"attempt-{state['attempts']}-http.json").open("x",encoding="utf-8") as out:
                json.dump(observation,out)
            raise
        observation.update(status_code=response.status_code,content_type=response.headers.get("content-type"))
        # Preserve the HTTP outcome even if body streaming fails or returns no JSON.
        with (directory/f"attempt-{state['attempts']}-http.json").open("x",encoding="utf-8") as out:
            json.dump(observation,out)
        raw = response.read()
        (directory/(f"attempt-{state['attempts']}-"+hashlib.sha256(raw).hexdigest()+"-body.json")).write_bytes(raw)
        return response

    def close(self):
        self.inner.close()


def canary_state_path(config):
    if not config.SUB_ACCOUNT_CLIENT_ID:
        raise ValueError("Dedicated credit account required")
    fingerprint = hashlib.sha256(config.SUB_ACCOUNT_CLIENT_ID.get_secret_value().encode()).hexdigest()
    return Path.home()/".royin-credit-state"/fingerprint/"canary.sqlite3"
