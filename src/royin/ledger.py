"""Deterministic financial ledger for order intents, fills, fee tracking, and P&L accounting."""

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal, Inexact, localcontext
from pathlib import Path


def validate_decimal(
    val: Decimal,
    name: str,
    *,
    allow_zero: bool = True,
    strictly_positive: bool = False,
) -> Decimal:
    """Strictly validate that val is a finite Decimal and not a float, bool, or invalid number."""
    if type(val) is not Decimal:
        raise TypeError(f"{name} must be a Decimal instance, got {type(val).__name__}")
    if not val.is_finite():
        raise ValueError(f"{name} must be finite (got {val})")
    if strictly_positive and val <= Decimal(0):
        raise ValueError(f"{name} must be strictly positive (got {val})")
    if not allow_zero and val <= Decimal(0):
        raise ValueError(f"{name} cannot be zero or negative (got {val})")
    if val < Decimal(0):
        raise ValueError(f"{name} cannot be negative (got {val})")
    return val


@dataclass(frozen=True)
class Balance:
    asset: str
    free: Decimal
    locked: Decimal

    @property
    def total(self) -> Decimal:
        return self.free + self.locked


@dataclass(frozen=True)
class OrderIntent:
    client_id: str
    symbol: str
    side: str
    order_type: str
    price: Decimal
    quantity: Decimal
    quote_fee_reserve: Decimal
    quote_asset: str
    base_asset: str
    status: str
    created_at: int


@dataclass(frozen=True)
class FillRecord:
    fill_id: str
    client_id: str
    price: Decimal
    quantity: Decimal
    fee: Decimal
    fee_asset: str
    timestamp: int


class Ledger:
    """Atomic SQLite-backed ledger using Decimal arithmetic for all currency amounts."""

    def __init__(self, db_path: Path | str = ":memory:", *, audit=None):
        self.audit = audit
        self.db_path = str(db_path)
        self._memory_conn = None
        if self.db_path == ":memory:":
            self._memory_conn = sqlite3.connect(":memory:", timeout=10)
            self._memory_conn.execute("PRAGMA foreign_keys = ON")
        else:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def connection(self):
        if self._memory_conn is not None:
            yield self._memory_conn
        else:
            conn = sqlite3.connect(self.db_path, timeout=10)
            conn.execute("PRAGMA foreign_keys = ON")
            try:
                yield conn
            finally:
                conn.close()

    def _init_db(self):
        with self.connection() as db, db:
            db.execute("PRAGMA synchronous = FULL")
            db.execute("""
                CREATE TABLE IF NOT EXISTS balances (
                    asset TEXT PRIMARY KEY,
                    free TEXT NOT NULL,
                    locked TEXT NOT NULL
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS order_intents (
                    client_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    order_type TEXT NOT NULL,
                    price TEXT NOT NULL,
                    quantity TEXT NOT NULL,
                    quote_fee_reserve TEXT NOT NULL DEFAULT '0',
                    quote_asset TEXT NOT NULL DEFAULT 'TMN',
                    base_asset TEXT NOT NULL DEFAULT 'USDT',
                    status TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS fills (
                    fill_id TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL,
                    price TEXT NOT NULL,
                    quantity TEXT NOT NULL,
                    fee TEXT NOT NULL,
                    fee_asset TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,
                    FOREIGN KEY(client_id) REFERENCES order_intents(client_id)
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS cost_basis (
                    asset TEXT PRIMARY KEY,
                    total_quantity TEXT NOT NULL,
                    total_cost_quote TEXT NOT NULL
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS realized_pnl (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    pnl TEXT NOT NULL,
                    timestamp INTEGER NOT NULL
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)

    def set_meta(self, key: str, value: str):
        with self.connection() as db, db:
            db.execute(
                "INSERT INTO metadata (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def get_meta(self, key: str) -> str | None:
        with self.connection() as db:
            row = db.execute("SELECT value FROM metadata WHERE key = ?", (key,)).fetchone()
            return row[0] if row else None

    def set_balance(self, asset: str, free: Decimal, locked: Decimal = Decimal(0)):
        """Initialize or override an asset balance with strict Decimal validation."""
        validate_decimal(free, "free balance")
        validate_decimal(locked, "locked balance")
        if not asset or not isinstance(asset, str):
            raise ValueError("Asset must be a non-empty string")

        with self.connection() as db, db:
            db.execute(
                "INSERT INTO balances (asset, free, locked) VALUES (?, ?, ?) "
                "ON CONFLICT(asset) DO UPDATE SET free = excluded.free, locked = excluded.locked",
                (asset, str(free), str(locked)),
            )

    def get_balance(self, asset: str) -> Balance:
        with self.connection() as db:
            row = db.execute(
                "SELECT free, locked FROM balances WHERE asset = ?", (asset,)
            ).fetchone()
            if not row:
                return Balance(asset=asset, free=Decimal(0), locked=Decimal(0))
            return Balance(asset=asset, free=Decimal(row[0]), locked=Decimal(row[1]))

    def get_all_balances(self) -> dict[str, Balance]:
        with self.connection() as db:
            rows = db.execute("SELECT asset, free, locked FROM balances").fetchall()
            return {
                r[0]: Balance(asset=r[0], free=Decimal(r[1]), locked=Decimal(r[2])) for r in rows
            }

    def record_intent(
        self,
        *,
        client_id: str,
        symbol: str,
        side: str,
        order_type: str,
        price: Decimal,
        quantity: Decimal,
        timestamp: int,
        quote_fee_reserve: Decimal = Decimal(0),
        quote_asset: str = "TMN",
        base_asset: str = "USDT",
    ) -> OrderIntent:
        """Persist an order intent and lock funds atomically, including worst-case fee."""
        validate_decimal(price, "price", strictly_positive=True)
        validate_decimal(quantity, "quantity", strictly_positive=True)
        validate_decimal(quote_fee_reserve, "quote_fee_reserve")
        if type(timestamp) is not int or timestamp <= 0:
            raise ValueError("timestamp must be a positive integer UNIX time")
        if side not in ("BUY", "SELL"):
            raise ValueError("Side must be BUY or SELL")
        if not client_id or not isinstance(client_id, str):
            raise ValueError("client_id must be a non-empty string")

        with self.connection() as db, db:
            existing = db.execute(
                "SELECT client_id FROM order_intents WHERE client_id = ?", (client_id,)
            ).fetchone()
            if existing:
                raise ValueError(f"Duplicate client_id: {client_id}")

            if side == "BUY":
                needed_quote = (price * quantity) + quote_fee_reserve
                row = db.execute(
                    "SELECT free, locked FROM balances WHERE asset = ?", (quote_asset,)
                ).fetchone()
                current_free = Decimal(row[0]) if row else Decimal(0)
                current_locked = Decimal(row[1]) if row else Decimal(0)
                if current_free < needed_quote:
                    raise ValueError(
                        f"Insufficient free balance in {quote_asset}: "
                        f"needed {needed_quote} (cost {price * quantity} + fee reserve {quote_fee_reserve}), "
                        f"available {current_free}"
                    )
                new_free = current_free - needed_quote
                new_locked = current_locked + needed_quote
                db.execute(
                    "INSERT INTO balances (asset, free, locked) VALUES (?, ?, ?) "
                    "ON CONFLICT(asset) DO UPDATE SET free = ?, locked = ?",
                    (quote_asset, str(new_free), str(new_locked), str(new_free), str(new_locked)),
                )
            else:  # SELL
                needed_base = quantity
                row = db.execute(
                    "SELECT free, locked FROM balances WHERE asset = ?", (base_asset,)
                ).fetchone()
                current_free = Decimal(row[0]) if row else Decimal(0)
                current_locked = Decimal(row[1]) if row else Decimal(0)
                if current_free < needed_base:
                    raise ValueError(
                        f"Insufficient free balance in {base_asset}: "
                        f"needed {needed_base}, available {current_free}"
                    )
                new_free = current_free - needed_base
                new_locked = current_locked + needed_base
                db.execute(
                    "INSERT INTO balances (asset, free, locked) VALUES (?, ?, ?) "
                    "ON CONFLICT(asset) DO UPDATE SET free = ?, locked = ?",
                    (base_asset, str(new_free), str(new_locked), str(new_free), str(new_locked)),
                )

            db.execute(
                "INSERT INTO order_intents ("
                "  client_id, symbol, side, order_type, price, quantity, quote_fee_reserve, "
                "  quote_asset, base_asset, status, created_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?)",
                (
                    client_id,
                    symbol,
                    side,
                    order_type,
                    str(price),
                    str(quantity),
                    str(quote_fee_reserve),
                    quote_asset,
                    base_asset,
                    timestamp,
                ),
            )

        if self.audit:
            self.audit.record_event(
                "INTENT",
                "LEDGER",
                {
                    "client_id": client_id,
                    "symbol": symbol,
                    "side": side,
                    "price": price,
                    "quantity": quantity,
                    "timestamp": timestamp,
                    "order_type": order_type,
                },
            )
        return OrderIntent(
            client_id=client_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            price=price,
            quantity=quantity,
            quote_fee_reserve=quote_fee_reserve,
            quote_asset=quote_asset,
            base_asset=base_asset,
            status="OPEN",
            created_at=timestamp,
        )

    def cancel_intent(self, client_id: str) -> bool:
        """Cancel remaining unfilled intent and unlock reserved funds from durable record."""
        with self.connection() as db, db:
            row = db.execute(
                "SELECT symbol, side, price, quantity, quote_fee_reserve, quote_asset, base_asset, status "
                "FROM order_intents WHERE client_id = ?",
                (client_id,),
            ).fetchone()
            if not row or row[7] in ("FILLED", "CANCELED", "REJECTED"):
                return False

            _, side, price_str, qty_str, fee_res_str, quote_asset, base_asset, _ = row
            intent_price = Decimal(price_str)
            intent_qty = Decimal(qty_str)
            fee_reserve = Decimal(fee_res_str)

            # Sum in Python to avoid SQLite SUM(TEXT) IEEE float precision corruption
            fill_rows = db.execute(
                "SELECT quantity FROM fills WHERE client_id = ?", (client_id,)
            ).fetchall()
            filled_qty = sum((Decimal(r[0]) for r in fill_rows), Decimal(0))
            remaining_qty = intent_qty - filled_qty

            if remaining_qty > Decimal(0):
                if side == "BUY":
                    proportion = remaining_qty / intent_qty
                    unlock_amount = (intent_price * remaining_qty) + (fee_reserve * proportion)
                    bal = db.execute(
                        "SELECT free, locked FROM balances WHERE asset = ?", (quote_asset,)
                    ).fetchone()
                    free, locked = Decimal(bal[0]), Decimal(bal[1])
                    actual_unlock = min(locked, unlock_amount)
                    db.execute(
                        "UPDATE balances SET free = ?, locked = ? WHERE asset = ?",
                        (str(free + actual_unlock), str(locked - actual_unlock), quote_asset),
                    )
                else:  # SELL
                    unlock_amount = remaining_qty
                    bal = db.execute(
                        "SELECT free, locked FROM balances WHERE asset = ?", (base_asset,)
                    ).fetchone()
                    free, locked = Decimal(bal[0]), Decimal(bal[1])
                    actual_unlock = min(locked, unlock_amount)
                    db.execute(
                        "UPDATE balances SET free = ?, locked = ? WHERE asset = ?",
                        (str(free + actual_unlock), str(locked - actual_unlock), base_asset),
                    )

            new_status = "CANCELED" if filled_qty == Decimal(0) else "PARTIALLY_FILLED_CANCELED"
            db.execute(
                "UPDATE order_intents SET status = ? WHERE client_id = ?",
                (new_status, client_id),
            )
            return True

    def record_fill(
        self,
        *,
        fill_id: str,
        client_id: str,
        price: Decimal,
        quantity: Decimal,
        fee: Decimal,
        fee_asset: str,
        timestamp: int,
    ) -> FillRecord:
        """Atomically record a fill, settle funds, and calculate realized P&L."""
        validate_decimal(price, "price", strictly_positive=True)
        validate_decimal(quantity, "quantity", strictly_positive=True)
        validate_decimal(fee, "fee", allow_zero=True)
        if type(timestamp) is not int or timestamp <= 0:
            raise ValueError("timestamp must be a positive integer UNIX time")
        if not fill_id or not isinstance(fill_id, str):
            raise ValueError("fill_id must be a non-empty string")

        with self.connection() as db, db:
            existing = db.execute(
                "SELECT fill_id, client_id, price, quantity, fee, fee_asset, timestamp "
                "FROM fills WHERE fill_id = ?",
                (fill_id,),
            ).fetchone()
            if existing:
                ex_cid, ex_p, ex_q, ex_f, ex_fa = (
                    existing[1],
                    Decimal(existing[2]),
                    Decimal(existing[3]),
                    Decimal(existing[4]),
                    existing[5],
                )
                if (ex_cid, ex_p, ex_q, ex_f, ex_fa) != (
                    client_id,
                    price,
                    quantity,
                    fee,
                    fee_asset,
                ):
                    raise ValueError(
                        f"Conflicting payload for existing fill_id: {fill_id} "
                        f"(stored: {(ex_cid, ex_p, ex_q, ex_f, ex_fa)}, incoming: {(client_id, price, quantity, fee, fee_asset)})"
                    )
                return FillRecord(
                    fill_id=existing[0],
                    client_id=existing[1],
                    price=ex_p,
                    quantity=ex_q,
                    fee=ex_f,
                    fee_asset=ex_fa,
                    timestamp=existing[6],
                )

            intent = db.execute(
                "SELECT symbol, side, price, quantity, quote_fee_reserve, quote_asset, base_asset, status "
                "FROM order_intents WHERE client_id = ?",
                (client_id,),
            ).fetchone()
            if not intent:
                raise ValueError(f"Order intent not found for client_id: {client_id}")

            (
                symbol,
                side,
                intent_price_str,
                intent_qty_str,
                fee_res_str,
                quote_asset,
                base_asset,
                _,
            ) = intent
            position_row = db.execute(
                "SELECT value FROM metadata WHERE key=?", (f"position_origin_{base_asset}",)
            ).fetchone()
            position_id = position_row[0] if position_row else client_id
            intent_price = Decimal(intent_price_str)
            intent_qty = Decimal(intent_qty_str)
            fee_reserve = Decimal(fee_res_str)

            if fee_asset not in (quote_asset, base_asset):
                raise ValueError(
                    f"Unsupported fee asset: {fee_asset}; must be {quote_asset} or {base_asset}"
                )

            # Sum in Python to avoid SQLite float epsilon errors
            fill_rows = db.execute(
                "SELECT quantity FROM fills WHERE client_id = ?", (client_id,)
            ).fetchall()
            curr_filled = sum((Decimal(r[0]) for r in fill_rows), Decimal(0))

            if curr_filled + quantity > intent_qty:
                raise ValueError(
                    f"Fill quantity {quantity} exceeds remaining intent quantity {intent_qty - curr_filled}"
                )

            db.execute(
                "INSERT INTO fills (fill_id, client_id, price, quantity, fee, fee_asset, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (fill_id, client_id, str(price), str(quantity), str(fee), fee_asset, timestamp),
            )

            if side == "BUY":
                proportion = quantity / intent_qty
                quote_locked_to_release = (intent_price * quantity) + (fee_reserve * proportion)
                quote_cost = price * quantity

                q_bal = db.execute(
                    "SELECT free, locked FROM balances WHERE asset = ?", (quote_asset,)
                ).fetchone()
                q_free, q_locked = Decimal(q_bal[0]), Decimal(q_bal[1])

                effective_release = min(q_locked, quote_locked_to_release)
                new_q_locked = q_locked - effective_release

                if fee_asset == quote_asset:
                    savings = effective_release - quote_cost - fee
                    new_q_free = q_free + savings
                    net_base_received = quantity
                else:
                    savings = effective_release - quote_cost
                    new_q_free = q_free + savings
                    net_base_received = quantity - fee

                if (
                    new_q_free < Decimal(0)
                    or new_q_locked < Decimal(0)
                    or net_base_received < Decimal(0)
                ):
                    raise ValueError(
                        f"Settlement resulted in negative balance: free={new_q_free}, locked={new_q_locked}, net_base={net_base_received}"
                    )

                db.execute(
                    "UPDATE balances SET free = ?, locked = ? WHERE asset = ?",
                    (str(new_q_free), str(new_q_locked), quote_asset),
                )

                b_bal = db.execute(
                    "SELECT free, locked FROM balances WHERE asset = ?", (base_asset,)
                ).fetchone()
                b_free, b_locked = (
                    (Decimal(b_bal[0]), Decimal(b_bal[1])) if b_bal else (Decimal(0), Decimal(0))
                )
                db.execute(
                    "INSERT INTO balances (asset, free, locked) VALUES (?, ?, ?) "
                    "ON CONFLICT(asset) DO UPDATE SET free = ?, locked = ?",
                    (
                        base_asset,
                        str(b_free + net_base_received),
                        str(b_locked),
                        str(b_free + net_base_received),
                        str(b_locked),
                    ),
                )

                basis_row = db.execute(
                    "SELECT total_quantity, total_cost_quote FROM cost_basis WHERE asset = ?",
                    (base_asset,),
                ).fetchone()
                old_qty, old_cost = (
                    (Decimal(basis_row[0]), Decimal(basis_row[1]))
                    if basis_row
                    else (Decimal(0), Decimal(0))
                )
                if old_qty == 0:
                    position_id = client_id
                    db.execute(
                        "INSERT INTO metadata(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        (f"position_origin_{base_asset}", position_id),
                    )
                total_buy_cost = quote_cost + (fee if fee_asset == quote_asset else Decimal(0))
                db.execute(
                    "INSERT INTO cost_basis (asset, total_quantity, total_cost_quote) VALUES (?, ?, ?) "
                    "ON CONFLICT(asset) DO UPDATE SET total_quantity = ?, total_cost_quote = ?",
                    (
                        base_asset,
                        str(old_qty + net_base_received),
                        str(old_cost + total_buy_cost),
                        str(old_qty + net_base_received),
                        str(old_cost + total_buy_cost),
                    ),
                )

            else:  # SELL
                b_bal = db.execute(
                    "SELECT free, locked FROM balances WHERE asset = ?", (base_asset,)
                ).fetchone()
                b_free, b_locked = Decimal(b_bal[0]), Decimal(b_bal[1])
                extra_base_fee = fee if fee_asset == base_asset else Decimal(0)
                b_free -= extra_base_fee
                if b_free < 0:
                    raise ValueError("Insufficient free base balance for SELL fee")
                new_b_locked = b_locked - quantity
                if new_b_locked < Decimal(0):
                    raise ValueError("Base locked balance cannot be negative")
                db.execute(
                    "UPDATE balances SET free = ?, locked = ? WHERE asset = ?",
                    (str(b_free), str(new_b_locked), base_asset),
                )

                gross_quote = price * quantity
                net_quote_received = gross_quote - (fee if fee_asset == quote_asset else Decimal(0))

                q_bal = db.execute(
                    "SELECT free, locked FROM balances WHERE asset = ?", (quote_asset,)
                ).fetchone()
                q_free, q_locked = Decimal(q_bal[0]), Decimal(q_bal[1])
                db.execute(
                    "UPDATE balances SET free = ?, locked = ? WHERE asset = ?",
                    (str(q_free + net_quote_received), str(q_locked), quote_asset),
                )

                basis_row = db.execute(
                    "SELECT total_quantity, total_cost_quote FROM cost_basis WHERE asset = ?",
                    (base_asset,),
                ).fetchone()
                old_qty, old_cost = (
                    (Decimal(basis_row[0]), Decimal(basis_row[1]))
                    if basis_row
                    else (Decimal(0), Decimal(0))
                )

                if old_qty > Decimal(0):
                    with localcontext() as ctx:
                        ctx.prec = 36
                        ctx.traps[Inexact] = False
                        cost_per_unit = old_cost / old_qty
                        cost_of_sold = cost_per_unit * (quantity + extra_base_fee)
                        realized_pnl = net_quote_received - cost_of_sold
                        new_remaining_qty = max(Decimal(0), old_qty - quantity - extra_base_fee)
                        new_remaining_cost = max(Decimal(0), old_cost - cost_of_sold)
                else:
                    realized_pnl = net_quote_received
                    new_remaining_qty, new_remaining_cost = Decimal(0), Decimal(0)

                db.execute(
                    "INSERT INTO realized_pnl (client_id, symbol, pnl, timestamp) VALUES (?, ?, ?, ?)",
                    (client_id, symbol, str(realized_pnl), timestamp),
                )
                db.execute(
                    "INSERT INTO cost_basis (asset, total_quantity, total_cost_quote) VALUES (?, ?, ?) "
                    "ON CONFLICT(asset) DO UPDATE SET total_quantity = ?, total_cost_quote = ?",
                    (
                        base_asset,
                        str(new_remaining_qty),
                        str(new_remaining_cost),
                        str(new_remaining_qty),
                        str(new_remaining_cost),
                    ),
                )

            if curr_filled + quantity == intent_qty:
                db.execute(
                    "UPDATE order_intents SET status = 'FILLED' WHERE client_id = ?", (client_id,)
                )
            else:
                db.execute(
                    "UPDATE order_intents SET status = 'PARTIALLY_FILLED' WHERE client_id = ?",
                    (client_id,),
                )

            if db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='broker_orders'"
            ).fetchone():
                db.execute(
                    "UPDATE broker_orders SET status=(SELECT status FROM order_intents WHERE client_id=?) "
                    "WHERE client_id=?",
                    (client_id, client_id),
                )

        if self.audit:
            self.audit.record_event(
                "FILL",
                "LEDGER",
                {
                    "fill_id": fill_id,
                    "position_id": position_id,
                    "client_id": client_id,
                    "symbol": symbol,
                    "side": side,
                    "price": price,
                    "quantity": quantity,
                    "fee": fee,
                    "fee_asset": fee_asset,
                    "timestamp": timestamp,
                },
            )
            self.audit.record_event(
                "LEDGER_RECONCILIATION",
                "LEDGER",
                {
                    "client_id": client_id,
                    "fill_id": fill_id,
                    "realized_pnl_tmn": self.get_realized_pnl(symbol),
                    "position_id": position_id,
                    "balance": {
                        k: {"free": v.free, "locked": v.locked}
                        for k, v in self.get_all_balances().items()
                    },
                },
            )
        return FillRecord(
            fill_id=fill_id,
            client_id=client_id,
            price=price,
            quantity=quantity,
            fee=fee,
            fee_asset=fee_asset,
            timestamp=timestamp,
        )

    def get_realized_pnl(self, symbol: str | None = None) -> Decimal:
        with self.connection() as db:
            if symbol:
                rows = db.execute(
                    "SELECT pnl FROM realized_pnl WHERE symbol = ?", (symbol,)
                ).fetchall()
            else:
                rows = db.execute("SELECT pnl FROM realized_pnl").fetchall()
            return sum((Decimal(r[0]) for r in rows), Decimal(0))

    def get_equity(self, prices: dict[str, Decimal], quote_currency: str = "TMN") -> Decimal:
        """Calculate total mark-to-market equity in quote currency."""
        balances = self.get_all_balances()
        total_equity = Decimal(0)
        for asset, bal in balances.items():
            if asset == quote_currency:
                total_equity += bal.total
            else:
                price = prices.get(f"{asset}{quote_currency}", prices.get(asset, Decimal(0)))
                total_equity += bal.total * price
        return total_equity
