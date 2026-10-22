"""Paper broker simulating order lifecycle, execution matching, reconciliation, and portfolio finalization."""

import json
import uuid
from dataclasses import dataclass
from decimal import Decimal
from functools import wraps
from typing import Literal

from royin.ledger import Ledger, validate_decimal
from royin.market_data import Candle
from royin.risk import MarketRules, PositionProtectionPolicy, RiskResult


def paper_atomic(method):
    @wraps(method)
    def run(self, *args, **kwargs):
        try:
            with self.ledger.transaction():
                return method(self, *args, **kwargs)
        finally:
            self._restore_from_db()
    return run


@dataclass(frozen=True)
class PaperOrder:
    client_id: str
    symbol: str
    side: Literal["BUY", "SELL"]
    price: Decimal
    quantity: Decimal
    stop_price: Decimal | None
    status: Literal[
        "INTENT",
        "SUBMITTING",
        "UNKNOWN",
        "OPEN",
        "PARTIALLY_FILLED",
        "FILLED",
        "CANCELED",
        "REJECTED",
    ]
    created_at: int


class PaperBroker:
    """Deterministic simulation broker backed by durable SQLite state without any network transport."""

    def __init__(self, ledger: Ledger, market_rules: MarketRules):
        self.ledger = ledger
        self.rules = market_rules
        self.orders: dict[str, PaperOrder] = {}
        self.active_stop_prices: dict[str, Decimal] = {}  # symbol -> stop_price
        self._init_broker_db()
        self._restore_from_db()

    def _init_broker_db(self):
        with self.ledger.connection() as db, db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS broker_orders (
                    client_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    price TEXT NOT NULL,
                    quantity TEXT NOT NULL,
                    stop_price TEXT,
                    status TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS broker_stops (
                    symbol TEXT PRIMARY KEY,
                    stop_price TEXT NOT NULL
                )
            """)

    def _restore_from_db(self):
        self.orders.clear()
        self.active_stop_prices.clear()
        with self.ledger.connection() as db:
            order_rows = db.execute(
                "SELECT b.client_id, b.symbol, b.side, "
                "COALESCE((SELECT f.price FROM fills f WHERE f.client_id=b.client_id ORDER BY f.rowid DESC LIMIT 1),b.price), "
                "b.quantity, b.stop_price, "
                "CASE WHEN i.status IN ('FILLED','PARTIALLY_FILLED','CANCELED','PARTIALLY_FILLED_CANCELED') "
                "THEN i.status ELSE b.status END, b.created_at FROM broker_orders b "
                "JOIN order_intents i ON i.client_id=b.client_id"
            ).fetchall()
            for r in order_rows:
                sp = Decimal(r[5]) if r[5] else None
                order = PaperOrder(
                    client_id=r[0],
                    symbol=r[1],
                    side=r[2],  # type: ignore
                    price=Decimal(r[3]),
                    quantity=Decimal(r[4]),
                    stop_price=sp,
                    status=r[6],  # type: ignore
                    created_at=r[7],
                )
                self.orders[r[0]] = order

            # Recover full filled buys whose stop write was interrupted, but never resurrect a sold position.
            if self.ledger.get_balance(self.rules.base_asset).total > 0:
                for order in self.orders.values():
                    if (
                        order.side == "BUY"
                        and order.status in ("FILLED", "PARTIALLY_FILLED")
                        and order.stop_price
                    ):
                        self.active_stop_prices[order.symbol] = order.stop_price
            stop_rows = db.execute("SELECT symbol, stop_price FROM broker_stops").fetchall()
            for r in stop_rows:
                if self.ledger.get_balance(self.rules.base_asset).total > 0:
                    self.active_stop_prices[r[0]] = Decimal(r[1])

    @paper_atomic
    def submit_order(
        self,
        risk_result: RiskResult,
        *,
        client_id: str | None = None,
        timestamp: int,
        simulate_unknown: bool = False,
    ) -> PaperOrder | None:
        """Submit an approved RiskResult to paper matching, reserving funds and worst-case fee."""
        if not risk_result.approved or risk_result.action == "WAIT":
            return None

        cid = client_id or f"paper_{uuid.uuid4().hex[:12]}"
        side: Literal["BUY", "SELL"] = "BUY" if risk_result.action == "ENTER" else "SELL"

        # Record intent in ledger (reserves funds and fee atomically)
        self.ledger.record_intent(
            client_id=cid,
            symbol=self.rules.symbol,
            side=side,
            order_type="LIMIT",
            price=risk_result.price,
            quantity=risk_result.quantity,
            quote_fee_reserve=risk_result.estimated_fee_quote,
            timestamp=timestamp,
            quote_asset=self.rules.quote_asset,
            base_asset=self.rules.base_asset,
        )

        status: Literal["UNKNOWN", "OPEN"] = "UNKNOWN" if simulate_unknown else "OPEN"
        order = PaperOrder(
            client_id=cid,
            symbol=self.rules.symbol,
            side=side,
            price=risk_result.price,
            quantity=risk_result.quantity,
            stop_price=risk_result.stop_price,
            status=status,
            created_at=timestamp,
        )
        self.orders[cid] = order

        with self.ledger.connection() as db, db:
            db.execute(
                "INSERT INTO broker_orders (client_id, symbol, side, price, quantity, stop_price, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(client_id) DO UPDATE SET status = excluded.status",
                (
                    cid,
                    self.rules.symbol,
                    side,
                    str(risk_result.price),
                    str(risk_result.quantity),
                    str(risk_result.stop_price) if risk_result.stop_price else None,
                    status,
                    timestamp,
                ),
            )

        if self.ledger.audit:
            self.ledger._stage_event(
                "STATE_TRANSITION",
                "BROKER",
                {
                    "client_id": cid,
                    "status": status,
                    "timestamp": timestamp,
                },
            )
        return order

    @paper_atomic
    def reconcile_order(
        self,
        client_id: str,
        *,
        simulated_state: Literal["FILLED", "OPEN", "REJECTED", "CANCELED"],
        timestamp: int,
        executed_price: Decimal | None = None,
    ) -> PaperOrder:
        """Reconcile an UNKNOWN or OPEN order without creating a new client_id."""
        if client_id not in self.orders:
            raise ValueError(f"Unknown client_id: {client_id}")

        order = self.orders[client_id]
        if order.status == "FILLED":
            if simulated_state != "FILLED":
                raise ValueError("Cannot transition a filled order to a non-filled state")
            return order

        if simulated_state == "CANCELED":
            self.ledger.cancel_intent(client_id)
            reconciled = PaperOrder(
                client_id=order.client_id,
                symbol=order.symbol,
                side=order.side,
                price=order.price,
                quantity=order.quantity,
                stop_price=order.stop_price,
                status="CANCELED",
                created_at=order.created_at,
            )
        elif simulated_state == "FILLED":
            with self.ledger.connection() as db:
                executed = sum(
                    (
                        Decimal(r[0])
                        for r in db.execute(
                            "SELECT quantity FROM fills WHERE client_id=?", (client_id,)
                        )
                    ),
                    Decimal(0),
                )
            remaining = order.quantity - executed
            if remaining == 0:
                self._restore_from_db()
                return self.orders[client_id]
            fill_price = executed_price or order.price
            validate_decimal(fill_price, "executed_price", strictly_positive=True)
            if (order.side == "BUY" and fill_price > order.price) or (
                order.side == "SELL" and fill_price < order.price
            ):
                raise ValueError("Reconciled LIMIT fill violates its limit")
            fee = remaining * fill_price * self.rules.taker_fee_rate
            self.ledger.record_fill(
                fill_id=f"fill_{client_id}",
                client_id=client_id,
                price=fill_price,
                quantity=remaining,
                fee=fee,
                fee_asset=self.rules.quote_asset,
                timestamp=timestamp,
            )
            reconciled = PaperOrder(
                client_id=order.client_id,
                symbol=order.symbol,
                side=order.side,
                price=fill_price,
                quantity=order.quantity,
                stop_price=order.stop_price,
                status="FILLED",
                created_at=order.created_at,
            )
        elif simulated_state == "REJECTED":
            self.ledger.cancel_intent(client_id)
            reconciled = PaperOrder(
                client_id=order.client_id,
                symbol=order.symbol,
                side=order.side,
                price=order.price,
                quantity=order.quantity,
                stop_price=order.stop_price,
                status="REJECTED",
                created_at=order.created_at,
            )
        else:  # OPEN
            reconciled = PaperOrder(
                client_id=order.client_id,
                symbol=order.symbol,
                side=order.side,
                price=order.price,
                quantity=order.quantity,
                stop_price=order.stop_price,
                status="OPEN",
                created_at=order.created_at,
            )

        self.orders[client_id] = reconciled
        with self.ledger.connection() as db, db:
            db.execute(
                "UPDATE broker_orders SET status = ?, price = ? WHERE client_id = ?",
                (reconciled.status, str(reconciled.price), client_id),
            )
            if reconciled.status == "FILLED" and order.side == "BUY" and order.stop_price:
                self.active_stop_prices[order.symbol] = order.stop_price
                db.execute(
                    "INSERT INTO broker_stops(symbol,stop_price) VALUES (?,?) "
                    "ON CONFLICT(symbol) DO UPDATE SET stop_price=excluded.stop_price",
                    (order.symbol, str(order.stop_price)),
                )
        if self.ledger.audit:
            self.ledger._stage_event(
                "STATE_TRANSITION",
                "BROKER",
                {
                    "client_id": client_id,
                    "status": reconciled.status,
                    "timestamp": timestamp,
                },
            )
        return reconciled

    @paper_atomic
    def process_candle(
        self,
        candle: Candle,
        *,
        slippage_pct: Decimal = Decimal("0.0005"),
        candle_interval: int = 900,
        limit_penetration_pct: Decimal = Decimal(0),
        no_fill: bool = False,
    ) -> list[str]:
        """Match open orders and check stop-losses strictly without lookahead or limit violations."""
        validate_decimal(slippage_pct, "slippage_pct")
        validate_decimal(limit_penetration_pct, "limit_penetration_pct")
        if (
            limit_penetration_pct >= 1
            or slippage_pct >= 1
            or type(candle_interval) is not int
            or candle_interval <= 0
        ):
            raise ValueError("Invalid execution assumptions")
        filled_order_ids = []
        candle_close_time = candle.open_time + candle_interval

        stop_at_open = self.active_stop_prices.get(self.rules.symbol)
        if stop_at_open and candle.low <= stop_at_open:
            for cid, order in list(self.orders.items()):
                if order.side == "SELL" and order.status in ("OPEN", "UNKNOWN", "PARTIALLY_FILLED"):
                    self.reconcile_order(
                        cid, simulated_state="CANCELED", timestamp=candle_close_time
                    )

        # 1. Match OPEN limit orders
        for cid, order in list(self.orders.items()):
            if order.status not in ("OPEN", "PARTIALLY_FILLED"):
                continue

            # Causality guard: cannot match orders created in the future
            if candle.open_time < order.created_at:
                continue

            with self.ledger.connection() as db:
                executed = sum(
                    (
                        Decimal(r[0])
                        for r in db.execute("SELECT quantity FROM fills WHERE client_id=?", (cid,))
                    ),
                    Decimal(0),
                )
            fill_quantity = order.quantity - executed
            if no_fill or candle.volume < fill_quantity:
                continue
            if order.side == "BUY" and candle.low <= order.price * (1 - limit_penetration_pct):
                # LIMIT BUY cannot fill above order.price
                # Slippage can at best fill at order.price, never higher
                exec_price = order.price
                fee = fill_quantity * exec_price * self.rules.taker_fee_rate
                self.ledger.record_fill(
                    fill_id=f"fill_{cid}",
                    client_id=cid,
                    price=exec_price,
                    quantity=fill_quantity,
                    fee=fee,
                    fee_asset=self.rules.quote_asset,
                    timestamp=candle_close_time,
                )
                self.orders[cid] = PaperOrder(
                    client_id=order.client_id,
                    symbol=order.symbol,
                    side=order.side,
                    price=exec_price,
                    quantity=order.quantity,
                    stop_price=order.stop_price,
                    status="FILLED",
                    created_at=order.created_at,
                )
                with self.ledger.connection() as db, db:
                    db.execute(
                        "UPDATE broker_orders SET status = 'FILLED', price = ? WHERE client_id = ?",
                        (str(exec_price), cid),
                    )
                if order.stop_price:
                    self.active_stop_prices[order.symbol] = order.stop_price
                    with self.ledger.connection() as db, db:
                        db.execute(
                            "INSERT INTO broker_stops(symbol,stop_price) VALUES (?,?) "
                            "ON CONFLICT(symbol) DO UPDATE SET stop_price=excluded.stop_price",
                            (order.symbol, str(order.stop_price)),
                        )
                filled_order_ids.append(cid)

            elif order.side == "SELL" and candle.high >= order.price * (1 + limit_penetration_pct):
                # LIMIT SELL cannot fill below order.price
                exec_price = order.price
                fee = fill_quantity * exec_price * self.rules.taker_fee_rate
                self.ledger.record_fill(
                    fill_id=f"fill_{cid}",
                    client_id=cid,
                    price=exec_price,
                    quantity=fill_quantity,
                    fee=fee,
                    fee_asset=self.rules.quote_asset,
                    timestamp=candle_close_time,
                )
                self.orders[cid] = PaperOrder(
                    client_id=order.client_id,
                    symbol=order.symbol,
                    side=order.side,
                    price=exec_price,
                    quantity=order.quantity,
                    stop_price=order.stop_price,
                    status="FILLED",
                    created_at=order.created_at,
                )
                with self.ledger.connection() as db, db:
                    db.execute(
                        "UPDATE broker_orders SET status = 'FILLED', price = ? WHERE client_id = ?",
                        (str(exec_price), cid),
                    )
                    db.execute("DELETE FROM broker_stops WHERE symbol = ?", (self.rules.symbol,))
                filled_order_ids.append(cid)
                if self.rules.symbol in self.active_stop_prices:
                    del self.active_stop_prices[self.rules.symbol]

        # 2. Check Stop Loss (Independent of AI)
        stop_price = self.active_stop_prices.get(self.rules.symbol)
        if stop_price and candle.low <= stop_price:
            if self.ledger.audit:
                self.ledger._stage_event(
                    "STOP",
                    "BROKER",
                    {
                        "symbol": self.rules.symbol,
                        "stop_price": stop_price,
                        "timestamp": candle_close_time,
                    },
                )
            base_bal = self.ledger.get_balance(self.rules.base_asset).free
            sellable_qty = self.rules.quantize_quantity(base_bal, round_down=True)
            if (
                sellable_qty >= self.rules.min_quantity
                and sellable_qty * min(stop_price, candle.low) * (1 - slippage_pct)
                >= self.rules.min_notional
            ):
                stop_cid = f"stop_{candle_close_time}"
                exec_price = min(stop_price, candle.low) * (Decimal(1) - slippage_pct)
                self.ledger.record_intent(
                    client_id=stop_cid,
                    symbol=self.rules.symbol,
                    side="SELL",
                    order_type="MARKET",
                    price=exec_price,
                    quantity=sellable_qty,
                    timestamp=candle_close_time,
                    quote_asset=self.rules.quote_asset,
                    base_asset=self.rules.base_asset,
                )
                fee = sellable_qty * exec_price * self.rules.taker_fee_rate
                self.ledger.record_fill(
                    fill_id=f"fill_{stop_cid}",
                    client_id=stop_cid,
                    price=exec_price,
                    quantity=sellable_qty,
                    fee=fee,
                    fee_asset=self.rules.quote_asset,
                    timestamp=candle_close_time,
                )
                self.orders[stop_cid] = PaperOrder(
                    client_id=stop_cid,
                    symbol=self.rules.symbol,
                    side="SELL",
                    price=exec_price,
                    quantity=sellable_qty,
                    stop_price=None,
                    status="FILLED",
                    created_at=candle_close_time,
                )
                with self.ledger.connection() as db, db:
                    db.execute(
                        "INSERT INTO broker_orders (client_id, symbol, side, price, quantity, status, created_at) "
                        "VALUES (?, ?, 'SELL', ?, ?, 'FILLED', ?)",
                        (
                            stop_cid,
                            self.rules.symbol,
                            str(exec_price),
                            str(sellable_qty),
                            candle_close_time,
                        ),
                    )
                filled_order_ids.append(stop_cid)

            if self.ledger.get_balance(self.rules.base_asset).total == 0:
                self.active_stop_prices.pop(self.rules.symbol, None)
                with self.ledger.connection() as db, db:
                    db.execute("DELETE FROM broker_stops WHERE symbol = ?", (self.rules.symbol,))

        return filled_order_ids

    @paper_atomic
    def finalize_portfolio(
        self,
        current_price: Decimal,
        *,
        timestamp: int,
        initial_capital: Decimal = Decimal("5000000"),
        slippage_pct: Decimal = Decimal(0),
    ) -> dict:
        """Idempotently cancel open orders, liquidate base assets, and produce settlement report."""
        validate_decimal(current_price, "current_price", strictly_positive=True)
        validate_decimal(slippage_pct, "slippage_pct")
        if slippage_pct >= 1:
            raise ValueError("Invalid slippage")
        current_price *= Decimal(1) - slippage_pct
        # Cancel all open or unknown orders
        for cid, order in list(self.orders.items()):
            if order.status in ("OPEN", "UNKNOWN", "PARTIALLY_FILLED"):
                self.reconcile_order(cid, simulated_state="CANCELED", timestamp=timestamp)

        # Clear stops
        self.active_stop_prices.clear()
        with self.ledger.connection() as db, db:
            db.execute("DELETE FROM broker_stops")

        # Liquidate remaining base asset to quote cash
        base_bal = self.ledger.get_balance(self.rules.base_asset).free
        sellable_qty = self.rules.quantize_quantity(base_bal, round_down=True)
        liquidated_qty = Decimal(0)
        liquidation_cash = Decimal(0)

        if (
            sellable_qty >= self.rules.min_quantity
            and (sellable_qty * current_price) >= self.rules.min_notional
        ):
            liq_cid = f"finalize_{timestamp}"
            self.ledger.record_intent(
                client_id=liq_cid,
                symbol=self.rules.symbol,
                side="SELL",
                order_type="MARKET",
                price=current_price,
                quantity=sellable_qty,
                timestamp=timestamp,
                quote_asset=self.rules.quote_asset,
                base_asset=self.rules.base_asset,
            )
            fee = sellable_qty * current_price * self.rules.taker_fee_rate
            self.ledger.record_fill(
                fill_id=f"fill_{liq_cid}",
                client_id=liq_cid,
                price=current_price,
                quantity=sellable_qty,
                fee=fee,
                fee_asset=self.rules.quote_asset,
                timestamp=timestamp,
            )
            self.orders[liq_cid] = PaperOrder(
                client_id=liq_cid,
                symbol=self.rules.symbol,
                side="SELL",
                price=current_price,
                quantity=sellable_qty,
                stop_price=None,
                status="FILLED",
                created_at=timestamp,
            )
            liquidated_qty = sellable_qty
            liquidation_cash = (sellable_qty * current_price) - fee

        final_tmn = self.ledger.get_balance(self.rules.quote_asset).free
        residual_base = self.ledger.get_balance(self.rules.base_asset).free
        realized_pnl = self.ledger.get_realized_pnl(self.rules.symbol)
        net_return_pct = ((final_tmn / initial_capital) - Decimal(1)) * Decimal(100)

        if self.ledger.audit:
            self.ledger._stage_event(
                "FINALIZATION",
                "BROKER",
                {
                    "timestamp": timestamp,
                    "final_tmn_cash": final_tmn,
                    "total_realized_pnl": realized_pnl,
                },
            )
            self.ledger._stage_event(
                "RESIDUAL",
                "BROKER",
                {
                    "timestamp": timestamp,
                    "residual_dust_base": residual_base,
                },
            )
        return {
            "status": "FINALIZED_WITH_RESIDUAL" if residual_base else "FINALIZED",
            "final_tmn_cash": str(final_tmn),
            "liquidated_base_quantity": str(liquidated_qty),
            "liquidation_cash_received": str(liquidation_cash),
            "residual_dust_base": str(residual_base),
            "total_realized_pnl": str(realized_pnl),
            "initial_capital_tmn": str(initial_capital),
            "net_return_pct": str(round(net_return_pct, 4)),
            "timestamp": timestamp,
        }

    def arm_protection(self, policy: PositionProtectionPolicy, *, opened_at, entry_price):
        """Bind the actual filled position to one immutable policy, without resetting its peak."""
        validate_decimal(entry_price, "entry price", strictly_positive=True)
        if type(opened_at) is not int or opened_at <= 0 or opened_at >= policy.deadline_utc-policy.exit_buffer_seconds:
            raise ValueError("Invalid filled-position opening time")
        key = "protection_" + self.rules.symbol
        with self.ledger.transaction() as db:
            old = self.ledger.get_meta(key)
            if old and json.loads(old)["status"] != "CLOSED":
                state = json.loads(old)
                if (state["policy_sha256"], state["opened_at"], state["entry_price"]) != (
                    policy.sha256, opened_at, str(entry_price),
                ):
                    raise ValueError("Position/policy binding mismatch; cannot reset high-water")
                return state
            if self.ledger.get_balance(self.rules.base_asset).total <= 0:
                raise ValueError("No actual filled position")
            if db.execute("SELECT 1 FROM order_intents WHERE side='BUY' AND status NOT IN "
                          "('FILLED','CANCELED','PARTIALLY_FILLED_CANCELED','REJECTED')").fetchone():
                raise ValueError("Partial/unknown buy requires reconciliation before arming")
            fills = db.execute("SELECT f.price,f.quantity FROM fills f JOIN order_intents i "
                               "ON i.client_id=f.client_id WHERE i.symbol=? AND i.side='BUY' AND f.timestamp>=?",
                               (self.rules.symbol,opened_at)).fetchall()
            quantity = sum((Decimal(q) for _,q in fills),Decimal(0))
            if not quantity or sum((Decimal(p)*Decimal(q) for p,q in fills),Decimal(0))/quantity != entry_price:
                raise ValueError("Entry price has no matching actual fill evidence")
            stop = entry_price * (1-policy.initial_stop_pct)
            existing_stop=self.active_stop_prices.get(self.rules.symbol,stop)
            stop=max(stop,existing_stop)
            state = dict(status="OPEN",policy_sha256=policy.sha256, opened_at=opened_at,
                entry_price=str(entry_price), initial_stop_price=str(stop), trailing_stop_price=str(stop),
                high_water=str(entry_price), last_source_time=opened_at, last_bid=str(entry_price),
                last_review_at=opened_at, checkpoint_seen=False, exit_reason=None)
            self.ledger.set_meta(key,json.dumps(state,sort_keys=True))
            db.execute("INSERT INTO broker_stops(symbol,stop_price) VALUES (?,?) ON CONFLICT(symbol) "
                       "DO UPDATE SET stop_price=excluded.stop_price",(self.rules.symbol,str(stop)))
        self._restore_from_db()
        return state

    @paper_atomic
    def observe_quote(self, bid, *, source_time, received_at, now, policy, slippage_pct=Decimal(".0005")):
        """One bounded host-monitor tick, independent of model completion or token budget."""
        validate_decimal(bid,"bid",strictly_positive=True)
        validate_decimal(slippage_pct,"slippage")
        if slippage_pct >= 1 or any(type(t) is not int or t <= 0 for t in (source_time,received_at,now)) or not source_time <= received_at <= now:
            raise ValueError("Invalid quote observation")
        key="protection_"+self.rules.symbol
        state=json.loads(self.ledger.get_meta(key) or "null")
        if state is None or state["policy_sha256"] != policy.sha256:
            raise ValueError("Position protection policy is unbound or changed")
        if source_time < state["last_source_time"] or now < state["opened_at"]:
            raise ValueError("Reordered position observation")
        if source_time == state["last_source_time"] and bid != Decimal(state["last_bid"]):
            raise ValueError("Conflicting quote timestamp")
        self.ledger.set_meta("engine_heartbeat",str(now))
        hard_exit_at=min(state["opened_at"]+policy.hard_holding_seconds,policy.deadline_utc-policy.exit_buffer_seconds)
        if now-source_time > policy.max_quote_age_seconds:
            self.ledger.set_meta("entry_block_reason","STALE_QUOTE")
            return dict(status="EXIT_REQUIRED_STALE_QUOTE" if now>=hard_exit_at else "STALE_QUOTE",
                        action="WAIT",entry_enabled=False,exit_required=now>=hard_exit_at)
        if self.ledger.get_meta("entry_block_reason") == "STALE_QUOTE":
            self.ledger.set_meta("entry_block_reason","")
        quantity=self.ledger.get_balance(self.rules.base_asset).total
        if quantity == 0:
            state["status"]="CLOSED"
            self.ledger.set_meta(key,json.dumps(state,sort_keys=True))
            return dict(status="FLAT",action="WAIT",review_due=False)
        stop=Decimal(state["trailing_stop_price"])
        with self.ledger.connection() as db:
            basis_row=db.execute("SELECT total_cost_quote FROM cost_basis WHERE asset=?",(self.rules.base_asset,)).fetchone()
        basis=Decimal(basis_row[0]) if basis_row else Decimal(0)
        net_if_exit=quantity*bid*(1-slippage_pct)*(1-self.rules.taker_fee_rate)-basis
        reason=("STOP_OR_TRAILING" if bid<=stop else "MAX_NET_LOSS" if net_if_exit<=-policy.max_loss_tmn
                else "HARD_HOLDING_OR_DEADLINE" if now>=hard_exit_at else None)
        if reason:
            portfolio=json.loads(self.ledger.get_meta("portfolio") or "{}")
            report=self.finalize_portfolio(bid,timestamp=now,slippage_pct=slippage_pct,
                initial_capital=Decimal(portfolio.get("initial_capital","5000000")))
            state.update(status="CLOSED" if self.ledger.get_balance(self.rules.base_asset).total==0 else "EXIT_REQUIRED_RESIDUAL",exit_reason=reason)
            self.ledger.set_meta(key,json.dumps(state,sort_keys=True))
            return dict(status=state["status"],action="EXIT",exit_reason=reason,settlement=report,review_due=False)
        peak=max(Decimal(state["high_water"]),bid)
        tightened=max(stop,peak*(1-policy.trailing_drawdown_pct))
        checkpoint=bid>=Decimal(state["entry_price"])*(1+policy.checkpoint_profit_pct)
        due=(checkpoint and not state["checkpoint_seen"]) or now-state["last_review_at"]>=policy.review_interval_seconds
        state.update(high_water=str(peak),trailing_stop_price=str(tightened),last_source_time=source_time,last_bid=str(bid))
        if due:
            state.update(last_review_at=now,checkpoint_seen=state["checkpoint_seen"] or checkpoint)
        self.ledger.set_meta(key,json.dumps(state,sort_keys=True))
        with self.ledger.connection() as db:
            db.execute("UPDATE broker_stops SET stop_price=? WHERE symbol=?",(str(tightened),self.rules.symbol))
        return {**state,"status":"PROTECTED","action":"WAIT","review_due":due,"hard_exit_at":hard_exit_at}

    def export_state(self, bid, *, now):
        """Read-only paper equity/protection view; never claims exchange/account equity."""
        validate_decimal(bid,"export bid",strictly_positive=True)
        state=json.loads(self.ledger.get_meta("protection_"+self.rules.symbol) or "null")
        quantity=self.ledger.get_balance(self.rules.base_asset).total
        with self.ledger.connection() as db:
            basis_row=db.execute("SELECT total_cost_quote FROM cost_basis WHERE asset=?",(self.rules.base_asset,)).fetchone()
            fees=sum((Decimal(f) for f, in db.execute("SELECT fee FROM fills WHERE fee_asset=?",(self.rules.quote_asset,))),Decimal(0))
            pending=db.execute("SELECT client_id,status FROM order_intents WHERE status NOT IN "
                "('FILLED','CANCELED','PARTIALLY_FILLED_CANCELED','REJECTED')").fetchall()
        basis=Decimal(basis_row[0]) if basis_row else Decimal(0)
        sellable=self.rules.quantize_quantity(self.ledger.get_balance(self.rules.base_asset).free)
        if sellable<self.rules.min_quantity or sellable*bid<self.rules.min_notional:
            sellable=Decimal(0)
        liquidation=sellable*bid*(1-self.rules.taker_fee_rate)
        return dict(mode="PAPER",evidence_kind="SIMULATED_EXECUTION_NOT_ACCOUNT",symbol=self.rules.symbol,
            exported_at=now,engine_heartbeat=self.ledger.get_meta("engine_heartbeat"),protection=state,
            cash_tmn=str(self.ledger.get_balance(self.rules.quote_asset).total),quantity=str(quantity),
            equity_mtm_tmn=str(self.ledger.get_equity({self.rules.symbol:bid},self.rules.quote_asset)),
            realized_pnl_tmn=str(self.ledger.get_realized_pnl(self.rules.symbol)),cost_basis_tmn=str(basis),
            gross_price_change_tmn=str(quantity*(bid-Decimal(state["entry_price"]))) if state else None,
            unrealized_before_exit_cost_tmn=str(quantity*bid-basis),net_liquidation_tmn=str(liquidation),
            net_if_exit_pnl_tmn=str(liquidation-basis),quote_fees_tmn=str(fees),pending_orders=pending,
            sellable_quantity=str(sellable),residual_base=str(quantity-sellable),
            entry_block_reason=self.ledger.get_meta("entry_block_reason"),audit_failed=self.ledger.get_meta("audit_failed")=="1")
