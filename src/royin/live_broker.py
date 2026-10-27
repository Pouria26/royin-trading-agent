"""Wallex order contract; general production is blocked outside a restricted technical canary."""

import hashlib
import json
import re
import threading
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from functools import wraps
from pathlib import Path

import httpx

from royin.config import RuntimeConfig
from royin.ledger import Ledger, validate_decimal
from royin.market_data import decimal_number, decode_json
from royin.markets import load_restrictions
from royin.risk import MarketRules, RiskResult


class LiveOrderError(Exception):
    """Invalid local operation or unresolved exchange observation."""


class LiveTradingSafetyGateError(RuntimeError):
    """Production execution is not approved."""


def single_worker(method):
    @wraps(method)
    def run(self, *args, **kwargs):
        if self.ledger._worker_active and self.ledger._worker_owner == threading.get_ident():
            return method(self, *args, **kwargs)
        with self.ledger.worker():
            return method(self, *args, **kwargs)

    return run


class WallexLiveBroker:
    """Order reconciliation shared by offline fixtures and a restricted credit canary.

    Complete cumulative synthetic snapshots reconcile atomically. Undocumented
    General strategy production is blocked. Flags alone cannot authorize real HTTP;
    the technical lane additionally enforces account lock and durable transport caps.
    """

    def __init__(
        self,
        ledger: Ledger,
        market_rules: MarketRules,
        config: RuntimeConfig,
        *,
        http_client=None,
        restrictions_path=Path("config/wallex-credit-market-policy.json"),
        enable_live_trading=None,
        run_mode=None,
        timeout_seconds=15.0,
    ):
        self.ledger, self.rules, self.config = ledger, market_rules, config
        self._injected_client = http_client
        self.restrictions_path = Path(restrictions_path)
        self.enable_live_trading = (
            config.ENABLE_LIVE_TRADING if enable_live_trading is None else enable_live_trading
        )
        self.run_mode = config.RUN_MODE if run_mode is None else run_mode
        self.timeout_seconds = timeout_seconds
        self.initialize_state(ledger)

    @staticmethod
    def initialize_state(ledger):
        """Create the broker journal without constructing an order transport."""
        with ledger.transaction() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS live_broker_orders (
                client_id TEXT PRIMARY KEY, symbol TEXT NOT NULL, side TEXT NOT NULL,
                order_type TEXT NOT NULL, price TEXT NOT NULL, quantity TEXT NOT NULL,
                exchange_order_id TEXT, status TEXT NOT NULL,
                created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)""")

    def _check_live_safety_gate(self):
        if self.enable_live_trading is not True or self.run_mode != "live":
            raise LiveTradingSafetyGateError("Live trading is disabled")
        client = self._injected_client
        from royin.canary import CreditCanaryTransport
        from royin.fresh_mission import FreshMissionTransport
        transport = client._transport if client is not None else None
        allowed = type(transport) is httpx.MockTransport or (
            type(transport) in (CreditCanaryTransport, FreshMissionTransport) and transport.ledger is self.ledger
            and transport.rules == self.rules and transport.config is self.config
        )
        if client is None or not allowed or client._mounts:
            raise LiveTradingSafetyGateError(
                "Production transport is blocked outside the restricted credit canary"
            )
        if not self.config.WALLEX_API_KEY or not self.config.SUB_ACCOUNT_CLIENT_ID:
            raise ValueError(
                "Live trading requires explicit WALLEX_API_KEY and SUB_ACCOUNT_CLIENT_ID"
            )
        if self.config.WALLEX_BASE_URL != "https://api.wallex.ir":
            raise LiveTradingSafetyGateError("Unexpected Wallex origin")

    @staticmethod
    def _validate_id(client_id, timestamp):
        if not isinstance(client_id, str) or not re.fullmatch(r"[A-Za-z0-9_]{1,64}", client_id):
            raise LiveOrderError("Invalid client order ID")
        if type(timestamp) is not int or timestamp < 0:
            raise LiveOrderError("Invalid timestamp")

    def _known_order(self, client_id, timestamp):
        self._check_live_safety_gate()
        self._validate_id(client_id, timestamp)
        with self.ledger.connection() as db:
            row = db.execute(
                "SELECT symbol FROM live_broker_orders WHERE client_id=?", (client_id,)
            ).fetchone()
        if not row or row[0] != self.rules.symbol:
            raise LiveOrderError("Unknown local order; refusing unscoped exchange request")

    def _set_status(self, client_id, timestamp, status, exchange_id=None):
        with self.ledger.transaction() as db:
            db.execute(
                "UPDATE live_broker_orders SET status=?,exchange_order_id=?,updated_at=? WHERE client_id=?",
                (status, exchange_id, timestamp, client_id),
            )
            if status != "UNKNOWN":
                db.execute(
                    "UPDATE order_intents SET status=? WHERE client_id=?", (status, client_id)
                )

    def _request(self, method, client_id, timestamp, payload=None):
        headers = {
            "x-api-key": self.config.WALLEX_API_KEY.get_secret_value(),
            "sub-account-client-id": self.config.SUB_ACCOUNT_CLIENT_ID.get_secret_value(),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        path = "/v1/account/orders" + ("/" + client_id if method == "GET" else "")
        # Any outcome after send may be ambiguous. Never free funds on transport/JSON/404 errors.
        self._set_status(client_id, timestamp, "UNKNOWN")
        observation = {"status": "UNKNOWN", "client_id": client_id,
                       "reconciliation_required": True, "failure_reason": "TRANSPORT_ERROR"}
        try:
            response = self._injected_client.request(
                method,
                self.config.WALLEX_BASE_URL + path,
                json=payload,
                params={"clientOrderId":client_id} if method=="DELETE" else None,
                headers=headers,
                timeout=self.timeout_seconds,
                follow_redirects=False,
            )
            observation["http_status"] = response.status_code
            if response.status_code not in (200, 201):
                return {**observation, "failure_reason": "HTTP_ERROR"}
            observation["failure_reason"] = "INVALID_RESPONSE_JSON"
            data = decode_json(response.content)
            observation["failure_reason"] = "INVALID_RESPONSE_CONTRACT"
            result = data.get("result") if isinstance(data, dict) else None
            if (
                not isinstance(data, dict)
                or data.get("success") is not True
                or not isinstance(result, dict)
                or result.get("clientOrderId") != client_id
            ):
                return observation
            from royin.canary import CreditCanaryTransport
            from royin.fresh_mission import FreshMissionTransport

            received_at = timestamp
            observation["failure_reason"] = "INVALID_HOST_RECEIPT_TIME"
            if type(self._injected_client._transport) in (CreditCanaryTransport, FreshMissionTransport):
                # Real fills can occur after send; only the host transport supplies receipt time.
                received_at = response.extensions.get("royin_received_at")
                if type(received_at) is not int or received_at < timestamp:
                    raise ValueError("Invalid host receipt time")
            observation["failure_reason"] = "INVALID_ORDER_SNAPSHOT"
            status = self._settle_snapshot(client_id, received_at, result, method)
            return {
                "status": status,
                "client_id": client_id,
                "exchange_order_id": client_id,
                "observed_exchange_status": result.get("status"),
                "http_status": response.status_code,
                "reconciliation_required": status == "UNKNOWN",
            }
        except (httpx.HTTPError, ValueError, KeyError, TypeError, ArithmeticError) as exc:
            return {**observation, "error_type": type(exc).__name__}

    def _settle_snapshot(self, client_id, timestamp, result, method):
        """Accept a complete cumulative multiset, never infer fills from status alone."""
        with self.ledger.transaction() as db:
            row = db.execute(
                "SELECT symbol,side,price,quantity,status,created_at FROM order_intents WHERE client_id=?",
                (client_id,),
            ).fetchone()
            symbol, side, price, quantity, previous_status, intent_created_at = row
            if (result["symbol"], result["side"], result["type"]) != (symbol, side, "LIMIT"):
                raise ValueError("Order identity mismatch")
            if decimal_number(result["origQty"]) != Decimal(quantity) or decimal_number(
                result["price"]
            ) != Decimal(price):
                raise ValueError("Order parameters mismatch")
            executed = decimal_number(result["executedQty"])
            total = decimal_number(result["executedSum"])
            raw_status = result["status"]
            if raw_status not in ("NEW", "PARTIALLY_FILLED", "FILLED", "CANCELED"):
                raise ValueError("Unknown exchange status")
            terminal = raw_status in ("FILLED", "CANCELED")
            if type(result["active"]) is not bool or result["active"] == terminal:
                raise ValueError("Inconsistent active/status")
            if not isinstance(result["fills"], list) or len(result["fills"]) > 1000:
                raise ValueError("Missing/bounded cumulative fills required")
            fills, occurrences = {}, Counter()
            for fill in result["fills"]:
                if (
                    fill["symbol"] != symbol
                    or type(fill["isBuyer"]) is not bool
                    or fill["isBuyer"] != (side == "BUY")
                ):
                    raise ValueError("Fill identity mismatch")
                p, q, fee = (decimal_number(fill[k]) for k in ("price", "quantity", "fee"))
                if p <= 0 or q <= 0 or decimal_number(fill["sum"]) != p * q:
                    raise ValueError("Invalid fill amounts")
                instant = datetime.fromisoformat(fill["timestamp"].replace("Z", "+00:00"))
                if instant.utcoffset() is None:
                    raise ValueError("Fill timestamps require an explicit offset")
                t = int(instant.timestamp())
                if t > timestamp:
                    raise ValueError("Future fill")
                if t < intent_created_at:
                    raise ValueError(
                        f"Fill timestamp {t} precedes intent creation time {intent_created_at}"
                    )
                canonical = json.dumps(
                    [
                        str(p.normalize()),
                        str(q.normalize()),
                        str(fee.normalize()),
                        fill["feeAsset"],
                        instant.astimezone(UTC).isoformat() if instant.microsecond else t,
                    ]
                )
                # shortcut: no server fill ID is documented; reject revised/incomplete cumulative multisets.
                digest = hashlib.sha256(canonical.encode()).hexdigest()
                occurrences[digest] += 1
                fid = f"{client_id}:{digest}:{occurrences[digest]}"
                fills[fid] = dict(
                    fill_id=fid,
                    client_id=client_id,
                    price=p,
                    quantity=q,
                    fee=fee,
                    fee_asset=fill["feeAsset"],
                    timestamp=t,
                )
            if (
                sum((f["quantity"] for f in fills.values()), Decimal(0)) != executed
                or sum((f["price"] * f["quantity"] for f in fills.values()), Decimal(0)) != total
            ):
                raise ValueError("Cumulative execution does not match fills")
            if (
                executed > Decimal(quantity)
                or (raw_status == "FILLED" and executed != Decimal(quantity))
                or (raw_status == "NEW" and executed != 0)
                or (raw_status == "PARTIALLY_FILLED" and not 0 < executed < Decimal(quantity))
            ):
                raise ValueError("Status/quantity mismatch")
            existing = {
                r[0]
                for r in db.execute("SELECT fill_id FROM fills WHERE client_id=?", (client_id,))
            }
            if not existing.issubset(fills):
                raise ValueError("Stale or revised cumulative snapshot")
            if previous_status in ("FILLED", "CANCELED", "PARTIALLY_FILLED_CANCELED"):
                expected = "FILLED" if previous_status == "FILLED" else "CANCELED"
                if set(fills) != existing or raw_status != expected:
                    raise ValueError("Observation conflicts with settled terminal order")
                self._set_status(client_id, timestamp, previous_status, client_id)
                return previous_status
            for f in sorted(fills.values(), key=lambda f: (f["timestamp"], f["fill_id"])):
                self.ledger.record_fill(**f)
            status = "OPEN" if executed == 0 else "PARTIALLY_FILLED"
            if raw_status == "FILLED":
                status = "FILLED"
            elif raw_status == "CANCELED":
                # DELETE acknowledgement alone cannot close the cancel/fill race.
                if method != "GET":
                    raise ValueError("Cancellation requires subsequent complete GET")
                self.ledger.cancel_intent(client_id)
                status = "CANCELED" if executed == 0 else "PARTIALLY_FILLED_CANCELED"
            self._set_status(client_id, timestamp, status, client_id)
            return status

    @single_worker
    def submit_order(self, risk_result: RiskResult, *, client_id, timestamp, order_type="LIMIT"):
        if not risk_result.approved or risk_result.action == "WAIT":
            return {"status": "SKIPPED", "client_id": client_id}
        self._check_live_safety_gate()
        self._validate_id(client_id, timestamp)
        if risk_result.symbol != self.rules.symbol or risk_result.action not in ("ENTER", "EXIT"):
            raise LiveOrderError("Risk result symbol/action mismatch")
        if order_type != "LIMIT":
            raise LiveOrderError("Only LIMIT contract fixtures are implemented")
        if self.rules.symbol not in self.config.WALLEX_ALLOWED_MARKETS:
            raise LiveOrderError("Symbol is not in WALLEX_ALLOWED_MARKETS")
        try:
            denied = load_restrictions(self.restrictions_path)
        except (OSError, ValueError) as exc:
            raise LiveOrderError("Market policy is unavailable") from exc
        if f"{self.rules.base_asset}/{self.rules.quote_asset}" in denied:
            raise LiveOrderError("Market is restricted by Wallex credit market policy")
        validate_decimal(risk_result.price, "price", strictly_positive=True)
        validate_decimal(risk_result.quantity, "quantity", strictly_positive=True)
        validate_decimal(risk_result.estimated_fee_quote, "fee")
        if (
            self.rules.quantize_price(risk_result.price) != risk_result.price
            or self.rules.quantize_quantity(risk_result.quantity) != risk_result.quantity
            or risk_result.quantity < self.rules.min_quantity
            or risk_result.price * risk_result.quantity < self.rules.min_notional
        ):
            raise LiveOrderError("Order does not meet exact market rules")
        fee_floor = risk_result.price * risk_result.quantity * self.rules.taker_fee_rate
        if risk_result.estimated_fee_quote < fee_floor:
            raise LiveOrderError("Fee reserve is below the conservative quote-fee fixture")
        side = "BUY" if risk_result.action == "ENTER" else "SELL"
        with self.ledger.transaction() as db:
            if db.execute(
                "SELECT 1 FROM live_broker_orders WHERE status NOT IN ('FILLED','CANCELED','PARTIALLY_FILLED_CANCELED')"
            ).fetchone():
                raise ValueError("Existing order requires reconciliation before new intent")
            self.ledger.record_intent(
                client_id=client_id,
                symbol=self.rules.symbol,
                side=side,
                order_type=order_type,
                price=risk_result.price,
                quantity=risk_result.quantity,
                quote_fee_reserve=risk_result.estimated_fee_quote,
                timestamp=timestamp,
                quote_asset=self.rules.quote_asset,
                base_asset=self.rules.base_asset,
            )
            db.execute(
                """INSERT INTO live_broker_orders
                (client_id,symbol,side,order_type,price,quantity,status,created_at,updated_at)
                VALUES (?,?,?,?,?,?,'SUBMITTING',?,?)""",
                (
                    client_id,
                    self.rules.symbol,
                    side,
                    order_type,
                    str(risk_result.price),
                    str(risk_result.quantity),
                    timestamp,
                    timestamp,
                ),
            )
            db.execute(
                "UPDATE order_intents SET status='SUBMITTING' WHERE client_id=?", (client_id,)
            )
        payload = {
            "symbol": self.rules.symbol,
            "side": side,
            "type": order_type,
            "price": str(risk_result.price),
            "quantity": str(risk_result.quantity),
            "client_id": client_id,
        }
        return self._request("POST", client_id, timestamp, payload)

    @single_worker
    def reconcile_order(self, client_id, *, timestamp):
        self._known_order(client_id, timestamp)
        return self._request("GET", client_id, timestamp)

    @single_worker
    def cancel_order(self, client_id, *, timestamp):
        self._known_order(client_id, timestamp)
        return self._request("DELETE", client_id, timestamp)
