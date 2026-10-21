"""Paper broker simulating order lifecycle, execution matching, reconciliation, and portfolio finalization."""

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from royin.ledger import Ledger
from royin.market_data import Candle
from royin.risk import MarketRules, RiskResult


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
        with self.ledger.connection() as db:
            order_rows = db.execute(
                "SELECT client_id, symbol, side, price, quantity, stop_price, status, created_at "
                "FROM broker_orders"
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

            stop_rows = db.execute("SELECT symbol, stop_price FROM broker_stops").fetchall()
            for r in stop_rows:
                self.active_stop_prices[r[0]] = Decimal(r[1])

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
            if risk_result.stop_price and side == "BUY":
                self.active_stop_prices[self.rules.symbol] = risk_result.stop_price
                db.execute(
                    "INSERT INTO broker_stops (symbol, stop_price) VALUES (?, ?) "
                    "ON CONFLICT(symbol) DO UPDATE SET stop_price = excluded.stop_price",
                    (self.rules.symbol, str(risk_result.stop_price)),
                )

        return order

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
            fill_price = executed_price or order.price
            fee = order.quantity * fill_price * self.rules.taker_fee_rate
            self.ledger.record_fill(
                fill_id=f"fill_{client_id}",
                client_id=client_id,
                price=fill_price,
                quantity=order.quantity,
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
        return reconciled

    def process_candle(
        self,
        candle: Candle,
        *,
        slippage_pct: Decimal = Decimal("0.0005"),
        candle_interval: int = 900,
    ) -> list[str]:
        """Match open orders and check stop-losses strictly without lookahead or limit violations."""
        filled_order_ids = []
        candle_close_time = candle.open_time + candle_interval

        # 1. Match OPEN limit orders
        for cid, order in list(self.orders.items()):
            if order.status != "OPEN":
                continue

            # Causality guard: cannot match orders created in the future
            if candle_close_time <= order.created_at:
                continue

            if order.side == "BUY" and candle.low <= order.price:
                # LIMIT BUY cannot fill above order.price
                # Slippage can at best fill at order.price, never higher
                exec_price = min(order.price, max(candle.low, order.price * (Decimal(1) - slippage_pct)))
                fee = order.quantity * exec_price * self.rules.taker_fee_rate
                self.ledger.record_fill(
                    fill_id=f"fill_{cid}",
                    client_id=cid,
                    price=exec_price,
                    quantity=order.quantity,
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
                filled_order_ids.append(cid)

            elif order.side == "SELL" and candle.high >= order.price:
                # LIMIT SELL cannot fill below order.price
                exec_price = max(order.price, min(candle.high, order.price * (Decimal(1) + slippage_pct)))
                fee = order.quantity * exec_price * self.rules.taker_fee_rate
                self.ledger.record_fill(
                    fill_id=f"fill_{cid}",
                    client_id=cid,
                    price=exec_price,
                    quantity=order.quantity,
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
            base_bal = self.ledger.get_balance(self.rules.base_asset).free
            sellable_qty = self.rules.quantize_quantity(base_bal, round_down=True)
            if sellable_qty >= self.rules.min_quantity:
                stop_cid = f"stop_{candle_close_time}"
                exec_price = max(Decimal(1), min(stop_price, candle.low) * (Decimal(1) - slippage_pct))
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
                        (stop_cid, self.rules.symbol, str(exec_price), str(sellable_qty), candle_close_time),
                    )
                filled_order_ids.append(stop_cid)

            if self.rules.symbol in self.active_stop_prices:
                del self.active_stop_prices[self.rules.symbol]
            with self.ledger.connection() as db, db:
                db.execute("DELETE FROM broker_stops WHERE symbol = ?", (self.rules.symbol,))

        return filled_order_ids

    def finalize_portfolio(
        self,
        current_price: Decimal,
        *,
        timestamp: int,
        initial_capital: Decimal = Decimal("5000000"),
    ) -> dict:
        """Idempotently cancel open orders, liquidate base assets, and produce settlement report."""
        # Cancel all open or unknown orders
        for cid, order in list(self.orders.items()):
            if order.status in ("OPEN", "UNKNOWN"):
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

        return {
            "status": "FINALIZED",
            "final_tmn_cash": str(final_tmn),
            "liquidated_base_quantity": str(liquidated_qty),
            "liquidation_cash_received": str(liquidation_cash),
            "residual_dust_base": str(residual_base),
            "total_realized_pnl": str(realized_pnl),
            "initial_capital_tmn": str(initial_capital),
            "net_return_pct": str(round(net_return_pct, 4)),
            "timestamp": timestamp,
        }
