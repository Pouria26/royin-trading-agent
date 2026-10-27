"""Operator-authorized fresh financial lane; historical UNKNOWN evidence stays immutable."""

import hashlib
import json
import re
import sqlite3
import time
from contextlib import closing
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from royin.market_data import decode_json


class FreshMissionPermit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    mission_id: str = Field(pattern=r"^fresh_[A-Za-z0-9_]{1,35}$")
    revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    account_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    old_state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    authorization_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    start_at: int = Field(gt=0)
    entry_end_at: int = Field(gt=0)
    end_at: int = Field(gt=0)
    max_buys: int = Field(default=1, ge=1, le=32)
    max_attempts: int = Field(default=128, ge=16, le=4096)
    capital_policy: Literal["FIXED_BOOTSTRAP_V1", "VOLATILITY_CAPITAL_V1"] = "FIXED_BOOTSTRAP_V1"
    allocation_tmn: Decimal = Field(default=Decimal("150000"), ge=Decimal("150000"), le=Decimal("4000000"))

    @field_validator("allocation_tmn", mode="before")
    @classmethod
    def exact_allocation(cls, value):
        if not isinstance(value, (str, Decimal)):
            raise ValueError("Allocation requires a decimal string")
        return Decimal(value)

    def canonical(self):
        if not self.start_at < self.entry_end_at < self.end_at <= self.start_at + 345600:
            raise ValueError("Fresh permit requires ordered times within four days")
        if self.capital_policy == "FIXED_BOOTSTRAP_V1" and self.allocation_tmn != Decimal("150000"):
            raise ValueError("A larger allocation requires the explicit dynamic capital policy")
        return self.model_dump_json()


def authorize_fresh_mission(
    ledger, permit, *, old_state_path, operator_instruction, observed_cash_tmn, open_order_ids
):
    """Explicit one-time initialization; never infer old exchange finality or amend old state."""
    from royin.ledger import validate_decimal

    validate_decimal(observed_cash_tmn, "observed dedicated cash", strictly_positive=True)
    canonical = permit.canonical()
    if not isinstance(operator_instruction, str) or not operator_instruction.strip():
        raise ValueError("Direct operator instruction is required")
    if hashlib.sha256(operator_instruction.encode()).hexdigest() != permit.authorization_sha256:
        raise ValueError("Operator authorization binding mismatch")
    path = Path(old_state_path).resolve(strict=True)
    if Path(ledger.db_path).resolve() == path:
        raise ValueError("Fresh state must be separate from historical state")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    if before != permit.old_state_sha256 or open_order_ids:
        raise ValueError("Historical evidence changed or account has open orders")
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        if db.execute("PRAGMA quick_check").fetchone() != ("ok",):
            raise ValueError("Historical database is not a valid snapshot")
        # No UPDATE/DELETE: a new human instruction is not an exchange cancellation.
        previous = db.execute("SELECT client_id,status FROM order_intents").fetchall()
    if (observed_cash_tmn < permit.allocation_tmn + Decimal("100000")
            or permit.allocation_tmn > observed_cash_tmn * Decimal(".80")):
        raise ValueError("Fresh allocation plus historical quarantine is unavailable")
    if hashlib.sha256(path.read_bytes()).hexdigest() != before:
        raise ValueError("Historical state changed during authorization")
    with ledger.transaction() as db:
        if (
            ledger.get_meta("fresh_permit") is not None
            or db.execute("SELECT 1 FROM order_intents LIMIT 1").fetchone()
        ):
            raise ValueError("Existing financial mission cannot be reset")
        ledger.initialize_portfolio(
            permit.allocation_tmn,
            quote_asset="TMN",
            binding=hashlib.sha256(canonical.encode()).hexdigest(),
        )
        ledger.set_meta("fresh_permit", canonical)
        ledger.set_meta(
            "fresh_authorization",
            json.dumps(
                dict(
                    operator_instruction=operator_instruction,
                    historical_orders=previous,
                    exchange_finality="UNCONFIRMED",
                    old_state_sha256=before,
                    quarantined_tmn="100000",
                    cash_baseline_tmn=str(observed_cash_tmn),
                    allocation_tmn=str(permit.allocation_tmn),
                    authorized_at=int(time.time()),
                ),
                ensure_ascii=False,
            ),
        )
        ledger.set_meta(
            "fresh_transport", json.dumps(dict(attempts=0, buys=0, sells=0, post_ids=[]))
        )


class FreshMissionTransport(httpx.BaseTransport):
    """Known LIMIT intents only, explicit capital policy, one position, no POST retry."""

    def __init__(self, ledger, rules, config, *, permit, inner=None):
        self.ledger, self.rules, self.config, self.permit = ledger, rules, config, permit
        self.account_fingerprint = permit.account_sha256
        if (
            ledger.db_path == ":memory:"
            or rules.quote_asset != "TMN"
            or not config.WALLEX_API_KEY
            or not config.SUB_ACCOUNT_CLIENT_ID
            or hashlib.sha256(config.SUB_ACCOUNT_CLIENT_ID.get_secret_value().encode()).hexdigest()
            != self.account_fingerprint
            or ledger.get_meta("fresh_permit") != permit.canonical()
            or ledger.get_meta("fresh_transport") is None
        ):
            raise ValueError("Existing operator-authorized financial state required")
        self.rules_sha256 = hashlib.sha256(
            json.dumps(asdict(rules), default=str, sort_keys=True).encode()
        ).hexdigest()
        self.inner = inner if inner is not None else httpx.HTTPTransport(retries=0, trust_env=False)

    def account_equity(self):
        authorization = json.loads(self.ledger.get_meta("fresh_authorization"))
        return (Decimal(authorization["cash_baseline_tmn"]) - self.permit.allocation_tmn
                + self.ledger.get_balance("TMN").total)

    def buy_debit_cap(self):
        if (self.permit.capital_policy == "FIXED_BOOTSTRAP_V1"
                or int(self.ledger.get_meta("closed_round_trips") or 0) == 0):
            return Decimal("150000")
        return min(self.permit.allocation_tmn, self.account_equity() * Decimal(".50"))

    def handle_request(self, request):
        if (
            not self.ledger._worker_active
            or getattr(self.ledger, "_worker_account_fingerprint", None) != self.account_fingerprint
        ):
            raise ValueError("Shared account ownership required")
        url, method = request.url, request.method
        cancel_query=(method=="DELETE" and url.path=="/v1/account/orders"
            and len(url.params.multi_items())==1 and "clientOrderId" in url.params)
        if (
            url.scheme != "https"
            or url.host != "api.wallex.ir"
            or url.port not in (None, 443)
            or (url.query and not cancel_query)
            or url.fragment
            or url.username
            or url.password
            or request.headers.get("x-api-key") != self.config.WALLEX_API_KEY.get_secret_value()
            or request.headers.get("sub-account-client-id")
            != self.config.SUB_ACCOUNT_CLIENT_ID.get_secret_value()
        ):
            raise ValueError("Unscoped financial request")
        payload = decode_json(request.content) if method == "POST" else None
        if method == "POST" and url.path == "/v1/account/orders":
            if not isinstance(payload, dict) or set(payload) != {
                "client_id",
                "symbol",
                "side",
                "type",
                "price",
                "quantity",
            }:
                raise ValueError("Invalid LIMIT payload")
            cid = payload["client_id"]
        elif method == "GET" and re.fullmatch(
            r"/v1/account/orders/[A-Za-z0-9_]{1,64}", url.path
        ):
            cid = url.path.rsplit("/", 1)[1]
        elif cancel_query and re.fullmatch(r"[A-Za-z0-9_]{1,64}",url.params["clientOrderId"]):
            cid=url.params["clientOrderId"]
        else:
            raise ValueError("Financial endpoint forbidden")
        if not isinstance(cid, str) or not cid.startswith(self.permit.mission_id + "_"):
            raise ValueError("Historical/foreign client ID cannot be requested")
        with self.ledger.transaction() as db:
            state = json.loads(self.ledger.get_meta("fresh_transport"))
            if (
                self.ledger.get_meta("fresh_permit") != self.permit.canonical()
                or state["attempts"] >= self.permit.max_attempts
            ):
                raise ValueError("Financial allowance exhausted or changed")
            row = db.execute(
                "SELECT symbol,side,price,quantity FROM order_intents WHERE client_id=?", (cid,)
            ).fetchone()
            if not row or row[0] != self.rules.symbol:
                raise ValueError("Matching durable intent required")
            if method == "POST":
                symbol, side, price, quantity = row
                if cid in state["post_ids"] or payload != dict(
                    client_id=cid,
                    symbol=symbol,
                    side=side,
                    type="LIMIT",
                    price=price,
                    quantity=quantity,
                ):
                    raise ValueError("Changed/duplicate POST forbidden")
                now = int(time.time())
                if not self.permit.start_at <= now < self.permit.end_at:
                    raise ValueError("Financial permit expired")
                if side == "BUY":
                    from royin.reconciliation import verify_reconciliation_for_post
                    verified_evidence = json.loads(self.ledger.get_meta("fresh_evidence_" + cid) or "null")
                    if isinstance(verified_evidence, dict):
                        verify_reconciliation_for_post(self.ledger, verified_evidence, cid=cid,
                            debit_tmn=Decimal(price)*Decimal(quantity)*(1+self.rules.taker_fee_rate), now=now)
                    from royin.residuals import quarantined_residuals
                    residuals = quarantined_residuals(self.ledger)
                    # Reserve the final 16 HTTP attempts for cancellation/reconciliation/exit.
                    if (
                        now >= self.permit.entry_end_at
                        or state["buys"] >= self.permit.max_buys
                        or state["attempts"] >= self.permit.max_attempts - 16
                        or Decimal(price) * Decimal(quantity) * (1 + self.rules.taker_fee_rate)
                        > self.buy_debit_cap()
                        or any(
                            a != "TMN" and a not in residuals and b.total
                            for a, b in self.ledger.get_all_balances().items()
                        )
                        or self.rules.base_asset in residuals
                    ):
                        raise ValueError("BUY time, debit, position or attempt cap exceeded")
                    evidence = json.loads(self.ledger.get_meta("fresh_evidence_" + cid) or "null")
                    operator_entry = isinstance(evidence,dict) and evidence.get("source_kind")=="OPERATOR"
                    if operator_entry:
                        from royin.operator_entry import validate_operator_post

                        validate_operator_post(self.ledger,self.permit,self.rules,evidence,
                            cid=cid,price=price,quantity=quantity,now=now,equity_tmn=self.account_equity())
                    elif (
                        not isinstance(evidence, dict)
                        or evidence.get("source_kind") != "REAL_MODEL"
                        or evidence.get("action") != "ENTER"
                        or evidence.get("symbol") != symbol
                        or evidence.get("rules_sha256") != self.rules_sha256
                        or type(evidence.get("quote_received_at")) is not int
                        or not 0 <= now - evidence["quote_received_at"] <= 5
                        or type(evidence.get("forecast_end_at")) is not int
                        or now >= evidence["forecast_end_at"]
                        or evidence.get("target_net_approved") is not True
                        or evidence.get("account_reconciled") is not True
                    ):
                        raise ValueError(
                            "Fresh bound AI, book, economics and account evidence required"
                        )
                    if self.permit.capital_policy == "VOLATILITY_CAPITAL_V1" and not operator_entry:
                        from royin.ledger import validate_decimal

                        plan = evidence.get("capital_plan") or {}
                        if plan.get("policy") != "VOLATILITY_CAPITAL_V1" or plan.get("approved") is not True:
                            raise ValueError("Host dynamic capital evidence required")
                        cap, loss, risk_budget = (Decimal(plan[key]) for key in
                            ("debit_limit_tmn", "loss_fraction", "risk_budget_tmn"))
                        for value in (cap, loss, risk_budget):
                            validate_decimal(value, "capital evidence", strictly_positive=True)
                        residual_reserve = Decimal(plan.get("residual_loss_reserve_tmn", "0"))
                        validate_decimal(residual_reserve, "residual loss reserve", allow_zero=True)
                        debit = Decimal(price) * Decimal(quantity) * (1 + self.rules.taker_fee_rate)
                        if (residual_reserve != Decimal("500")
                                or debit > cap or debit * loss + residual_reserve > risk_budget
                                or risk_budget > self.account_equity() * Decimal(".005")):
                            raise ValueError("Dynamic capital or stop-risk budget exceeded")
                    state["buys"] += 1
                elif side == "SELL":
                    if state["buys"] == 0 or state["sells"] >= self.permit.max_buys * 3:
                        raise ValueError("Unowned/excess exit attempt")
                    state["sells"] += 1
                else:
                    raise ValueError("Invalid side")
                state["post_ids"].append(cid)
            state["attempts"] += 1
            self.ledger.set_meta("fresh_transport", json.dumps(state))
        # Durable reservation precedes all network operations; no automatic refund.
        directory = Path(self.ledger.db_path).parent / "captures"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"fresh-attempt-{state['attempts']}.json"
        observation = dict(method=method, client_id=cid, attempted_at=int(time.time()))
        try:
            response = self.inner.handle_request(request)
            observation["http_status"] = response.status_code
            raw = response.read()
            response.extensions["royin_received_at"] = int(time.time())
            observation["body_sha256"] = hashlib.sha256(raw).hexdigest()
            (directory / (observation["body_sha256"] + ".body")).write_bytes(raw)
            return response
        except httpx.HTTPError as exc:
            observation["error_type"] = type(exc).__name__
            raise
        finally:
            with path.open("x", encoding="utf-8") as stream:
                json.dump(observation, stream)

    def close(self):
        self.inner.close()
