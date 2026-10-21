"""Offline Wallex order-contract prototype. Production transport is deliberately blocked."""

import re
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


class WallexLiveBroker:
    """Mock-transport contract harness, not a live execution engine.

    Filled/canceled exchange observations need fill/fee reconciliation that this
    prototype does not implement. Reservations remain locked and status UNKNOWN.
    Flags/constructor overrides never authorize real network transport.
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
        with ledger.connection() as db, db:
            db.execute("""CREATE TABLE IF NOT EXISTS live_broker_orders (
                client_id TEXT PRIMARY KEY, symbol TEXT NOT NULL, side TEXT NOT NULL,
                order_type TEXT NOT NULL, price TEXT NOT NULL, quantity TEXT NOT NULL,
                exchange_order_id TEXT, status TEXT NOT NULL,
                created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)""")

    def _check_live_safety_gate(self):
        if self.enable_live_trading is not True or self.run_mode != "live":
            raise LiveTradingSafetyGateError("Live trading is disabled")
        client = self._injected_client
        if client is None or type(client._transport) is not httpx.MockTransport or client._mounts:
            raise LiveTradingSafetyGateError(
                "Production transport is blocked; offline MockTransport only"
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
        with self.ledger.connection() as db, db:
            db.execute(
                "UPDATE live_broker_orders SET status=?,exchange_order_id=?,updated_at=? WHERE client_id=?",
                (status, exchange_id, timestamp, client_id),
            )
            db.execute("UPDATE order_intents SET status=? WHERE client_id=?", (status, client_id))

    def _request(self, method, client_id, timestamp, payload=None):
        headers = {
            "x-api-key": self.config.WALLEX_API_KEY.get_secret_value(),
            "sub-account-client-id": self.config.SUB_ACCOUNT_CLIENT_ID.get_secret_value(),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        path = "/v1/account/orders" + ("" if method == "POST" else "/" + client_id)
        # Any outcome after send may be ambiguous. Never free funds on transport/JSON/404 errors.
        self._set_status(client_id, timestamp, "UNKNOWN")
        try:
            response = self._injected_client.request(
                method,
                self.config.WALLEX_BASE_URL + path,
                json=payload,
                headers=headers,
                timeout=self.timeout_seconds,
                follow_redirects=False,
            )
            data = decode_json(response.content)
            result = data.get("result") if isinstance(data, dict) else None
            if (
                response.status_code not in (200, 201)
                or not isinstance(data, dict)
                or data.get("success") is not True
                or not isinstance(result, dict)
                or result.get("clientOrderId") != client_id
            ):
                return {
                    "status": "UNKNOWN",
                    "client_id": client_id,
                    "reconciliation_required": True,
                }
            raw_status = str(result.get("status", "")).upper()
            executed = decimal_number(result["executedQty"])
            # An acknowledgement is not a fill; terminal/partial states retain reservations.
            status = (
                "OPEN"
                if method != "DELETE" and executed == 0 and raw_status in ("NEW", "OPEN", "ACTIVE")
                else "UNKNOWN"
            )
            self._set_status(client_id, timestamp, status, client_id)
            return {
                "status": status,
                "client_id": client_id,
                "exchange_order_id": client_id,
                "observed_exchange_status": raw_status,
                "reconciliation_required": status == "UNKNOWN",
            }
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return {"status": "UNKNOWN", "client_id": client_id, "reconciliation_required": True}

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
        with self.ledger.connection() as db, db:
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
        payload = {
            "symbol": self.rules.symbol,
            "side": side,
            "type": order_type,
            "price": str(risk_result.price),
            "quantity": str(risk_result.quantity),
            "client_id": client_id,
        }
        return self._request("POST", client_id, timestamp, payload)

    def reconcile_order(self, client_id, *, timestamp):
        self._known_order(client_id, timestamp)
        return self._request("GET", client_id, timestamp)

    def cancel_order(self, client_id, *, timestamp):
        self._known_order(client_id, timestamp)
        return self._request("DELETE", client_id, timestamp)
