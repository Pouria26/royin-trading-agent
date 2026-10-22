"""Deterministic financial ledger for order intents, fills, fee tracking, and P&L accounting."""

import json
import re
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal, Inexact, localcontext
from functools import wraps
from pathlib import Path
from typing import Any


def validate_decimal(
    val: Decimal,
    name: str,
    *,
    allow_zero: bool = True,
    strictly_positive: bool = False,
    allow_negative: bool = False,
) -> Decimal:
    """Strictly validate that val is a finite Decimal and not a float, bool, or invalid number."""
    if type(val) is not Decimal:
        raise TypeError(f"{name} must be a Decimal instance, got {type(val).__name__}")
    if not val.is_finite():
        raise ValueError(f"{name} must be finite (got {val})")
    if strictly_positive and val <= Decimal(0):
        raise ValueError(f"{name} must be strictly positive (got {val})")
    if not allow_zero and val == Decimal(0):
        raise ValueError(f"{name} cannot be zero (got {val})")
    if not allow_negative and val < Decimal(0):
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


def ledger_atomic(method):
    @wraps(method)
    def run(self,*args,**kwargs):
        with self.transaction():
            return method(self,*args,**kwargs)
    return run


class Ledger:
    """Atomic SQLite-backed ledger using Decimal arithmetic for all currency amounts."""

    def __init__(self, db_path: Path | str = ":memory:", *, audit=None):
        self.audit = audit
        self.db_path = str(db_path)
        self._memory_conn = None
        self._transaction_conn = None
        self._transaction_events: list[tuple[str, str, dict[str, Any]]] | None = None
        self._worker_active = False
        if self.db_path == ":memory:":
            self._memory_conn = sqlite3.connect(":memory:", timeout=10)
            self._memory_conn.execute("PRAGMA foreign_keys = ON")
        else:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _stage_event(self, event_type: str, category: str, payload: dict[str, Any]):
        if self._transaction_events is not None:
            from royin.logger import AuditLogger
            client_id=payload.get("client_id")
            saved_origin=self.get_meta("audit_order_"+client_id) if client_id else None
            if isinstance(self.audit,AuditLogger):
                payload={**payload,"_audit_origin":dict(run_id=self.audit.run_id,mode=self.audit.mode,
                    source=self.audit.source,hashes=dict(self.audit.hashes),context={k:v for k,v in self.audit.context.items()
                        if k in ("decision_id","snapshot_sha256","symbol","cutoff")})}
            else:
                payload={**payload,"_audit_origin":dict(run_id="UNATTRIBUTED_LEDGER",mode="unknown",
                    source="UNATTRIBUTED_LEDGER_REPLAY",hashes={},context={})}
            if saved_origin:
                payload["_audit_origin"]=json.loads(saved_origin)
            elif event_type=="INTENT" and client_id:
                self.set_meta("audit_order_"+client_id,json.dumps(payload["_audit_origin"]))
            self._transaction_events.append((event_type, category, payload))
        elif self.audit:
            self.audit.record_event(event_type, category, payload)

    @contextmanager
    def connection(self):
        if self._transaction_conn is not None:
            yield self._transaction_conn
        elif self._memory_conn is not None:
            yield self._memory_conn
        else:
            conn = sqlite3.connect(self.db_path, timeout=10)
            conn.execute("PRAGMA foreign_keys = ON")
            try:
                yield conn
            finally:
                conn.close()

    @contextmanager
    def transaction(self):
        """Compose ledger operations in one durable transaction, never nested commits."""
        if self._transaction_conn is not None:
            yield self._transaction_conn
            return
        with self.connection() as db:
            db.execute("PRAGMA synchronous = FULL")
            db.execute("BEGIN IMMEDIATE")
            self._transaction_conn = db
            self._transaction_events = []
            committed = False
            try:
                yield db
                for event_type, category, payload in self._transaction_events:
                    db.execute("INSERT INTO audit_outbox(event_type,category,payload) VALUES (?,?,?)",
                               (event_type, category, json.dumps(payload, default=str)))
                db.commit()
                committed = True
            except BaseException:
                db.rollback()
                self._transaction_events.clear()
                raise
            finally:
                events_to_emit = (
                    list(self._transaction_events)
                    if (committed and self._transaction_events)
                    else []
                )
                self._transaction_conn = None
                self._transaction_events = None

            if self.audit and events_to_emit:
                self.flush_audit()

    def flush_audit(self):
        """At-least-once delivery with stable IDs; crash after file write can duplicate an ID."""
        if self.audit is None or self._transaction_conn is not None:
            return
        with self.connection() as db:
            rows = db.execute("SELECT id,event_type,category,payload FROM audit_outbox WHERE delivered=0 ORDER BY id").fetchall()
            for event_id, event_type, category, payload in rows:
                try:
                    decoded=json.loads(payload)
                    origin=decoded.pop("_audit_origin",None)
                    self.audit.record_event(event_type, category, {
                        **decoded, "journal_event_id": f"{self.get_meta('journal_id')}:{event_id}",
                    },origin=origin)
                    with db:
                        db.execute("UPDATE audit_outbox SET delivered=1 WHERE id=?", (event_id,))
                except Exception:
                    with db:
                        db.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES ('audit_failed','1')")
                    raise
            with db:
                db.execute("DELETE FROM metadata WHERE key='audit_failed'")

    @contextmanager
    def worker(self, *, account_fingerprint=None, lock_directory=None):
        """One local execution operation, including HTTP; OS releases SQLite lock on crash."""
        if self._worker_active:
            raise BlockingIOError("Another execution operation is active")
        lock = None
        self._worker_active = True
        self._worker_owner = threading.get_ident()
        self._worker_account_fingerprint = account_fingerprint
        try:
            if account_fingerprint is not None or lock_directory is not None:
                if not isinstance(account_fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", account_fingerprint) or lock_directory is None:
                    raise ValueError("Explicit account fingerprint and shared lock directory required")
                directory = Path(lock_directory).resolve()
                directory.mkdir(parents=True, exist_ok=True)
                lock_path = directory / (account_fingerprint + ".sqlite3")
            else:
                lock_path = Path(str(Path(self.db_path).resolve()) + ".worker") if self.db_path != ":memory:" else None
            if lock_path is not None:
                lock = sqlite3.connect(lock_path, timeout=0)
                lock.execute("BEGIN EXCLUSIVE")
            yield
        finally:
            if lock is not None:
                lock.close()
            self._worker_active = False
            self._worker_owner = None
            self._worker_account_fingerprint = None

    def _init_db(self):
        with self.transaction() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS audit_outbox (
                id INTEGER PRIMARY KEY, event_type TEXT NOT NULL, category TEXT NOT NULL,
                payload TEXT NOT NULL, delivered INTEGER NOT NULL DEFAULT 0)""")
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
            db.execute("""
                CREATE TABLE IF NOT EXISTS trade_reflections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    pnl_net TEXT NOT NULL,
                    return_pct TEXT NOT NULL,
                    lesson_text TEXT NOT NULL,
                    timestamp INTEGER NOT NULL
                )
            """)
            db.execute("INSERT OR IGNORE INTO metadata(key,value) VALUES ('journal_id',?)", (uuid.uuid4().hex,))

    def initialize_portfolio(self, initial_capital, *, quote_asset, binding):
        validate_decimal(initial_capital, "initial capital", strictly_positive=True)
        if not isinstance(binding, str) or not re.fullmatch(r"[0-9a-f]{64}", binding) or quote_asset != "TMN":
            raise ValueError("Exact binding and TMN portfolio required")
        expected = json.dumps(dict(initial_capital=str(initial_capital), quote_asset=quote_asset, binding=binding), sort_keys=True)
        with self.transaction() as db:
            existing = self.get_meta("portfolio")
            if existing is not None:
                if existing != expected:
                    raise ValueError("Existing portfolio binding mismatch; no reset")
                return False
            if any(db.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone() for table in (
                "balances", "order_intents", "fills", "cost_basis", "realized_pnl", "audit_outbox",
            )) or db.execute("SELECT 1 FROM metadata WHERE key!='journal_id' LIMIT 1").fetchone():
                raise ValueError("Unbound nonempty ledger; recovery review required")
            self.set_balance(quote_asset, initial_capital)
            self.set_meta("portfolio", expected)
            self.set_meta("peak_equity_TMN", str(initial_capital))
        return True

    def claim_candle(self, symbol, cutoff, snapshot_sha256, interval_seconds):
        if not re.fullmatch(r"[A-Z0-9]+(?:TMN|USDT)", symbol) or (
            type(cutoff) is not int or type(interval_seconds) is not int or interval_seconds <= 0
            or cutoff <= 0 or cutoff % interval_seconds or not re.fullmatch(r"[0-9a-f]{64}", snapshot_sha256)
        ):
            raise ValueError("Invalid candle claim")
        with self.transaction():
            previous = self.get_meta("candle_claim")
            if previous:
                old = json.loads(previous)
                if old["status"] == "PENDING":
                    raise BlockingIOError("Interrupted model/decision requires reconciliation; no duplicate inference")
                if cutoff <= old["cutoff"]:
                    return False
                if cutoff != old["cutoff"] + interval_seconds:
                    raise ValueError("Current candle gap")
            self.set_meta("candle_claim", json.dumps(dict(symbol=symbol, cutoff=cutoff,
                snapshot_sha256=snapshot_sha256, status="PENDING")))
        return True

    def complete_candle(self, symbol, cutoff, decision):
        """Call in the same outer transaction as the paper intent, never around network I/O."""
        with self.transaction():
            claim = json.loads(self.get_meta("candle_claim") or "{}")
            if claim.get("status") != "PENDING" or (claim.get("symbol"),claim.get("cutoff")) != (symbol,cutoff):
                raise ValueError("No matching pending candle claim")
            if (decision.symbol,decision.cutoff,decision.snapshot_sha256) != (symbol,cutoff,claim["snapshot_sha256"]):
                raise ValueError("Decision claim binding mismatch")
            self.set_meta(f"decision_{cutoff}", decision.model_dump_json())
            self._stage_event("HOST_DECISION","ENGINE",decision.model_dump(mode="json"))
            self.set_meta("candle_claim", json.dumps({**claim, "status":"COMPLETE"}))

    def record_reflection(
        self,
        *,
        trade_id: str,
        symbol: str,
        pnl_net: Decimal,
        return_pct: Decimal,
        lesson_text: str,
        timestamp: int,
    ):
        """Record post-trade reflection lesson in durable SQLite storage with event staging."""
        validate_decimal(pnl_net, "pnl_net", allow_zero=True, allow_negative=True)
        validate_decimal(return_pct, "return_pct", allow_zero=True, allow_negative=True)
        if not lesson_text or not lesson_text.strip():
            raise ValueError("lesson_text cannot be blank")

        with self.transaction() as db:
            db.execute(
                """
                INSERT INTO trade_reflections (trade_id, symbol, pnl_net, return_pct, lesson_text, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (trade_id, symbol, str(pnl_net), str(return_pct), lesson_text.strip(), timestamp),
            )
            self._stage_event("TRADE_REFLECTION", "strategy", {
                "trade_id": trade_id,
                "symbol": symbol,
                "pnl_net": str(pnl_net),
                "return_pct": str(return_pct),
                "lesson_text": lesson_text.strip(),
                "timestamp": timestamp,
            })

    def get_recent_reflections(self, symbol: str | None = None, limit: int = 3) -> list[dict[str, Any]]:
        """Retrieve recent post-trade reflection lessons for in-context learning."""
        with self.connection() as db:
            if symbol:
                rows = db.execute(
                    """
                    SELECT trade_id, symbol, pnl_net, return_pct, lesson_text, timestamp
                    FROM trade_reflections
                    WHERE symbol = ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (symbol, limit),
                ).fetchall()
            else:
                rows = db.execute(
                    """
                    SELECT trade_id, symbol, pnl_net, return_pct, lesson_text, timestamp
                    FROM trade_reflections
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            return [
                {
                    "trade_id": r[0],
                    "symbol": r[1],
                    "pnl_net": Decimal(r[2]),
                    "return_pct": Decimal(r[3]),
                    "lesson_text": r[4],
                    "timestamp": r[5],
                }
                for r in rows
            ]

    def set_meta(self, key: str, value: str):
        with self.transaction() as db:
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

        with self.transaction() as db:
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

    @ledger_atomic
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

        with self.transaction() as db:
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

        self._stage_event(
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

    @ledger_atomic
    def cancel_intent(self, client_id: str) -> bool:
        """Cancel remaining unfilled intent and unlock reserved funds from durable record."""
        with self.transaction() as db:
            row = db.execute(
                "SELECT symbol, side, price, quantity, quote_fee_reserve, quote_asset, base_asset, status "
                "FROM order_intents WHERE client_id = ?",
                (client_id,),
            ).fetchone()
            if not row or row[7] in ("FILLED", "CANCELED", "REJECTED", "PARTIALLY_FILLED_CANCELED"):
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
                    unlock_amount = intent_price * remaining_qty + fee_reserve - fee_reserve * filled_qty / intent_qty
                    bal = db.execute(
                        "SELECT free, locked FROM balances WHERE asset = ?", (quote_asset,)
                    ).fetchone()
                    free, locked = Decimal(bal[0]), Decimal(bal[1])
                    actual_unlock = unlock_amount
                    if locked < actual_unlock:
                        raise ValueError("Reservation mismatch; refusing release")
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
                    actual_unlock = unlock_amount
                    if locked < actual_unlock:
                        raise ValueError("Reservation mismatch; refusing release")
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

    @ledger_atomic
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

        with self.transaction() as db:
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
                if (ex_cid, ex_p, ex_q, ex_f, ex_fa, existing[6]) != (
                    client_id,
                    price,
                    quantity,
                    fee,
                    fee_asset,
                    timestamp,
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
                "SELECT symbol, side, price, quantity, quote_fee_reserve, quote_asset, base_asset, status, created_at "
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
                intent_status,
                intent_created_at,
            ) = intent
            if intent_status in ("CANCELED", "REJECTED", "PARTIALLY_FILLED_CANCELED", "FILLED"):
                raise ValueError("New fill after terminal settlement requires reconciliation")
            if timestamp < intent_created_at:
                raise ValueError(
                    f"Fill timestamp {timestamp} precedes intent created_at {intent_created_at}"
                )
            if (side == "BUY" and price > Decimal(intent_price_str)) or (side == "SELL" and price < Decimal(intent_price_str)):
                raise ValueError("Fill violates LIMIT price")
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
                fee_release = (fee_reserve * (curr_filled + quantity) / intent_qty
                               - fee_reserve * curr_filled / intent_qty)
                quote_locked_to_release = intent_price * quantity + fee_release
                quote_cost = price * quantity

                q_bal = db.execute(
                    "SELECT free, locked FROM balances WHERE asset = ?", (quote_asset,)
                ).fetchone()
                q_free, q_locked = Decimal(q_bal[0]), Decimal(q_bal[1])

                effective_release = quote_locked_to_release
                if q_locked < effective_release:
                    raise ValueError("Reservation mismatch; refusing settlement")
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
                if net_quote_received < 0:
                    raise ValueError("SELL fee exceeds proceeds")

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

        self._stage_event(
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
        self._stage_event(
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
            elif bal.total:
                price = prices.get(f"{asset}{quote_currency}", prices.get(asset))
                if price is None:
                    raise ValueError("A held asset lacks a valuation price")
                validate_decimal(price, "valuation price", strictly_positive=True)
                total_equity += bal.total * price
        return total_equity
