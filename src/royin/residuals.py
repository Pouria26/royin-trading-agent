"""Audited dust classification; inventory, cost basis and fills remain untouched."""

import hashlib
import json
from decimal import Decimal, Inexact, localcontext

from royin.ledger import Ledger, validate_decimal
from royin.risk import MarketRules

KEY = "fresh_residual_quarantine"
OPERATOR_EXCEPTION_KEY = "fresh_operator_residual_exception_v1"
OPERATOR_EXCEPTION_POLICY = "ONE_RETAINED_OPERATOR_RESIDUAL_V1"
TERMINAL = {"FILLED", "CANCELED", "PARTIALLY_FILLED_CANCELED", "REJECTED"}
FIELDS = {
    "schema_version", "journal_id", "asset", "symbol", "quantity", "mark_price_tmn",
    "marked_value_tmn", "value_bound_tmn", "acquisition_cost_tmn", "cost_basis_tmn",
    "origin_buy_client_id", "terminal_sell_client_id", "terminal_sell_quantity", "evidence_sha256", "rules",
    "entry_evidence_sha256", "entry_rules_sha256", "last_fill_at",
    "quote_received_at", "at", "previous_sha256", "sha256",
}


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _decimal(value):
    if not isinstance(value, str):
        raise ValueError("Residual receipt money must use decimal strings")
    try:
        result = Decimal(value)
        validate_decimal(result, "residual amount")
    except (ArithmeticError, TypeError, ValueError) as exc:
        raise ValueError("Invalid residual amount") from exc
    return result


def _timestamp(value):
    if type(value) is not int or value <= 0:
        raise ValueError("Residual timestamps must be positive integer seconds")
    return value


def _rules_dict(rules):
    return {"symbol": rules.symbol, "base_asset": rules.base_asset, "quote_asset": rules.quote_asset,
            "tick_size": str(rules.tick_size), "step_size": str(rules.step_size),
            "min_notional": str(rules.min_notional), "min_quantity": str(rules.min_quantity),
            "maker_fee_rate": str(rules.maker_fee_rate), "taker_fee_rate": str(rules.taker_fee_rate)}


def _proof(ledger, db, asset, symbol):
    """Recheck original acquisition, terminal sell and exact current accounting."""
    balance = ledger.get_balance(asset)
    if balance.free <= 0 or balance.locked != 0:
        raise ValueError("Residual must be positive, entirely free and unchanged")
    origin = ledger.get_meta("position_origin_" + asset)
    origin_row = db.execute("SELECT rowid FROM order_intents WHERE client_id=? AND base_asset=? "
                            "AND quote_asset='TMN' AND symbol=? AND side='BUY'", (origin, asset, symbol)).fetchone()
    if origin_row is None:
        raise ValueError("Original residual BUY provenance missing")
    raw_evidence = ledger.get_meta("fresh_evidence_" + origin)
    try:
        if not raw_evidence or len(raw_evidence) > 1_000_000:
            raise ValueError("Missing bounded entry evidence")
        evidence = json.loads(raw_evidence)
        if (evidence.get("source_kind") not in ("REAL_MODEL","OPERATOR") or evidence.get("action") != "ENTER"
                or evidence.get("symbol") != symbol or not isinstance(evidence.get("rules_sha256"), str)):
            raise ValueError("Residual entry has no original authorized source")
        if evidence["source_kind"]=="OPERATOR":
            from royin.fresh_mission import FreshMissionPermit
            from royin.operator_entry import AUTH_KEY, load_operator_authority

            permit=FreshMissionPermit.model_validate_json(ledger.get_meta("fresh_permit"))
            load_operator_authority(ledger,permit)
            authorities=json.loads(ledger.get_meta(AUTH_KEY))
            matched=[a for a in authorities if a["sha256"]==evidence.get("operator_authority_sha256")
                     and a["client_id"]==origin and a["symbol"]==symbol]
            if len(matched)!=1 or evidence.get("target_net_approved") is not False:
                raise ValueError("Residual operator origin has no bound human authority")
    except (TypeError, AttributeError, ValueError) as exc:
        raise ValueError("Residual original BUY evidence missing or invalid") from exc
    rows = db.execute("SELECT client_id,symbol,side,order_type,price,quantity,quote_fee_reserve,"
                      "quote_asset,base_asset,status,created_at FROM order_intents WHERE base_asset=? "
                      "AND rowid>=? ORDER BY rowid", (asset, origin_row[0])).fetchall()
    if (not rows or any(row[1] != symbol or row[7] != "TMN" or row[9] not in TERMINAL for row in rows)
            or [row[0] for row in rows if row[2] == "BUY"] != [origin]):
        raise ValueError("Residual order history is pending, unknown or belongs to another position")
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='live_broker_orders'").fetchone() is None:
        raise ValueError("Residual requires the original live broker journal")
    broker = db.execute("SELECT client_id,symbol,side,order_type,price,quantity,status,created_at,updated_at "
                        "FROM live_broker_orders WHERE symbol=? ORDER BY created_at,client_id", (symbol,)).fetchall()
    if any(row[6] not in TERMINAL for row in broker):
        raise ValueError("Residual has an unresolved broker order")
    broker_by_id = {row[0]: row for row in broker}
    fills = db.execute("SELECT f.fill_id,f.client_id,f.price,f.quantity,f.fee,f.fee_asset,f.timestamp "
                       "FROM fills f JOIN order_intents i ON i.client_id=f.client_id "
                       "WHERE i.base_asset=? AND i.rowid>=? ORDER BY f.rowid", (asset, origin_row[0])).fetchall()
    by_id = {row[0]: row for row in rows}
    totals = {row[0]: Decimal(0) for row in rows}
    quantity = cost = acquisition = Decimal(0)
    sold = False
    actual_sells = []
    for fill in fills:
        _, cid, price_s, qty_s, fee_s, fee_asset, at = fill
        row = by_id[cid]
        price, qty, fee = _decimal(price_s), _decimal(qty_s), _decimal(fee_s)
        if price <= 0 or qty <= 0 or fee_asset not in (asset, "TMN") or type(at) is not int or at < row[10]:
            raise ValueError("Invalid original residual fill")
        totals[cid] += qty
        if row[2] == "BUY":
            if sold:
                raise ValueError("Residual acquisition changed after liquidation")
            quantity += qty - (fee if fee_asset == asset else 0)
            debit = price * qty + (fee if fee_asset == "TMN" else 0)
            cost += debit
            acquisition += debit
        elif row[2] == "SELL":
            sold = True
            actual_sells.append(cid)
            removed = qty + (fee if fee_asset == asset else 0)
            if quantity <= 0 or removed > quantity:
                raise ValueError("Residual fills exceed acquired inventory")
            # Match Ledger's existing average-cost precision exactly.
            with localcontext() as ctx:
                ctx.prec = 36
                ctx.traps[Inexact] = False
                cost = max(Decimal(0), cost - cost / quantity * removed)
                quantity = max(Decimal(0), quantity - removed)
        else:
            raise ValueError("Invalid residual order side")
    for row in rows:
        total, requested = totals[row[0]], _decimal(row[5])
        if (total > requested or (row[9] == "FILLED" and total != requested)
                or (row[9] in {"CANCELED", "REJECTED"} and total != 0)
                or (row[9] == "PARTIALLY_FILLED_CANCELED" and not 0 < total < requested)):
            raise ValueError("Residual terminal intent contradicts actual fills")
    if not actual_sells or acquisition <= 0:
        raise ValueError("Residual has no completed real SELL fill")
    terminal = actual_sells[-1]
    for cid in (origin, terminal):
        row, observed = by_id[cid], broker_by_id.get(cid)
        if (observed is None or observed[1:4] != row[1:4] or observed[6] != row[9]
                or _decimal(observed[4]) != _decimal(row[4]) or _decimal(observed[5]) != _decimal(row[5])):
            raise ValueError("Original residual live order proof disagrees")
    basis = db.execute("SELECT total_quantity,total_cost_quote FROM cost_basis WHERE asset=?", (asset,)).fetchone()
    if (basis is None or quantity != balance.free or _decimal(basis[0]) != quantity
            or _decimal(basis[1]) != cost or cost <= 0):
        raise ValueError("Residual inventory or cost basis differs from original fills")
    return dict(origin_buy_client_id=origin, terminal_sell_client_id=terminal,
                terminal_sell_quantity=by_id[terminal][5],
                entry_evidence_sha256=hashlib.sha256(raw_evidence.encode()).hexdigest(),
                entry_rules_sha256=evidence["rules_sha256"], last_fill_at=max(fill[6] for fill in fills),
                acquisition_cost_tmn=str(acquisition), cost_basis_tmn=str(cost),
                evidence_sha256=_digest({"intents": rows, "fills": fills, "broker_orders": broker}),
                quantity=str(quantity))


def _operator_exception(ledger, db):
    """A separate, single-position authority; ordinary dust limits do not change."""
    raw = ledger.get_meta(OPERATOR_EXCEPTION_KEY)
    if raw is None:
        return None
    from royin.runtime_release import source_history

    receipt = json.loads(raw)
    fields = {"policy", "journal_id", "permit_sha256", "source_sha256", "asset", "symbol",
              "maximum_marked_value_tmn", "authorized_at", "operator_instruction", "proof", "sha256",
              "quiescent_restart_receipt_sha256"}
    if (not isinstance(receipt, dict) or set(receipt) != fields
            or receipt["sha256"] != _digest({k:v for k,v in receipt.items() if k != "sha256"})
            or receipt["policy"] != OPERATOR_EXCEPTION_POLICY
            or receipt["journal_id"] != ledger.get_meta("journal_id")
            or receipt["permit_sha256"] != hashlib.sha256(ledger.get_meta("fresh_permit").encode()).hexdigest()
            or receipt["source_sha256"] not in source_history(ledger)
            or receipt["maximum_marked_value_tmn"] != "600"
            or (receipt["quiescent_restart_receipt_sha256"] is not None and (
                not isinstance(receipt["quiescent_restart_receipt_sha256"],str)
                or len(receipt["quiescent_restart_receipt_sha256"]) != 64
                or any(c not in "0123456789abcdef" for c in receipt["quiescent_restart_receipt_sha256"])))
            or not isinstance(receipt["operator_instruction"], str) or not receipt["operator_instruction"].strip()):
        raise ValueError("Retained operator residual authority binding changed")
    proof = _proof(ledger, db, receipt["asset"], receipt["symbol"])
    evidence = json.loads(ledger.get_meta("fresh_evidence_"+proof["origin_buy_client_id"]))
    permit = json.loads(ledger.get_meta("fresh_permit"))
    if (proof != receipt["proof"] or evidence["source_kind"] != "OPERATOR"
            or not proof["last_fill_at"] <= _timestamp(receipt["authorized_at"]) < permit["end_at"]
            or _decimal(proof["acquisition_cost_tmn"]) > Decimal(150000)):
        raise ValueError("Retained operator residual proof changed")
    return receipt


def authorize_operator_residual_exception(ledger, rules, *, price_tmn, quote_received_at, now,
                                          operator_instruction, quiescent_restart_receipt_sha256=None):
    """Explicit approval of one already acquired residual up to 600 TMN; no purchase."""
    from royin.runtime_release import source_history

    validate_decimal(price_tmn, "operator residual mark", strictly_positive=True)
    if not 0 <= _timestamp(now)-_timestamp(quote_received_at) <= 5:
        raise ValueError("Retained operator residual requires a fresh quote")
    with ledger.transaction() as db:
        from royin.reconciliation import _quiescence_hash
        state = ledger.get_meta("service_state")
        interrupted = state == "RUNNING" and _quiescence_hash(quiescent_restart_receipt_sha256)
        if (ledger.get_meta(OPERATOR_EXCEPTION_KEY) is not None
                or (state != "PAUSED_RESTART" and not interrupted) or ledger._worker_active
                or not isinstance(operator_instruction, str) or not operator_instruction.strip()):
            raise ValueError("Paused original mission and one explicit residual exception required")
        proof = _proof(ledger, db, rules.base_asset, rules.symbol)
        evidence = json.loads(ledger.get_meta("fresh_evidence_"+proof["origin_buy_client_id"]))
        rules_hash = hashlib.sha256(json.dumps(_rules_dict(rules), sort_keys=True).encode()).hexdigest()
        quantity = _decimal(proof["quantity"])
        value = quantity*price_tmn
        bound = min(Decimal(600), _decimal(proof["acquisition_cost_tmn"])*Decimal(".005"))
        pending = db.execute("SELECT 1 FROM order_intents WHERE status NOT IN "
            "('FILLED','CANCELED','PARTIALLY_FILLED_CANCELED','REJECTED') LIMIT 1").fetchone()
        broker_pending = db.execute("SELECT 1 FROM live_broker_orders WHERE status NOT IN "
            "('FILLED','CANCELED','PARTIALLY_FILLED_CANCELED','REJECTED') LIMIT 1").fetchone()
        old_receipts, _, aggregate = _validated(ledger, db)
        if (rules.quote_asset != "TMN" or proof["entry_rules_sha256"] != rules_hash
                or evidence["source_kind"] != "OPERATOR" or pending or broker_pending
                or not Decimal(500) < value <= bound
                or aggregate+value > Decimal(5000) or len(old_receipts) >= 8
                or _decimal(proof["acquisition_cost_tmn"]) > Decimal(150000)
                or rules.quantize_quantity(quantity)*price_tmn >= rules.min_notional
                or quantity > rules.step_size+_decimal(proof["terminal_sell_quantity"])*rules.taker_fee_rate):
            raise ValueError("Existing operator residual is not within the reviewed one-position exception")
        body = dict(policy=OPERATOR_EXCEPTION_POLICY, journal_id=ledger.get_meta("journal_id"),
                    permit_sha256=hashlib.sha256(ledger.get_meta("fresh_permit").encode()).hexdigest(),
                    source_sha256=source_history(ledger)[-1], asset=rules.base_asset, symbol=rules.symbol,
                    maximum_marked_value_tmn="600", authorized_at=now,
                    operator_instruction=operator_instruction, proof=proof,
                    quiescent_restart_receipt_sha256=quiescent_restart_receipt_sha256)
        receipt = {**body, "sha256": _digest(body)}
        ledger.set_meta(OPERATOR_EXCEPTION_KEY, json.dumps(receipt, sort_keys=True))
        _operator_exception(ledger, db)
        return receipt


def _validated(ledger, db):
    try:
        receipts = json.loads(ledger.get_meta(KEY) or "[]")
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid residual quarantine history") from exc
    if not isinstance(receipts, list) or len(receipts) > 8:
        raise ValueError("Residual quarantine history exceeds the bounded contract")
    exception = _operator_exception(ledger, db)
    result, previous, aggregate = {}, None, Decimal(0)
    for receipt in receipts:
        enhanced = isinstance(receipt, dict) and "operator_exception_sha256" in receipt
        if not isinstance(receipt, dict) or set(receipt) != FIELDS | ({"operator_exception_sha256"} if enhanced else set()):
            raise ValueError("Invalid residual receipt schema")
        body = {k: v for k, v in receipt.items() if k != "sha256"}
        if (type(receipt["schema_version"]) is not int or receipt["schema_version"] != (2 if enhanced else 1) or receipt["sha256"] != _digest(body)
                or receipt["previous_sha256"] != previous
                or receipt["journal_id"] != ledger.get_meta("journal_id")):
            raise ValueError("Residual receipt hash or journal binding mismatch")
        try:
            raw_rules = receipt["rules"]
            rules = MarketRules(**{k: (_decimal(v) if k not in {"symbol", "base_asset", "quote_asset"} else v)
                                   for k, v in raw_rules.items()})
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("Invalid residual rules") from exc
        asset = receipt["asset"]
        if (not isinstance(asset, str) or asset in result or asset != rules.base_asset
                or receipt["symbol"] != rules.symbol or rules.quote_asset != "TMN"):
            raise ValueError("Residual asset/rules binding mismatch")
        proof = _proof(ledger, db, asset, rules.symbol)
        if any(receipt[key] != value for key, value in proof.items()):
            raise ValueError("Residual evidence changed after quarantine")
        rules_hash = hashlib.sha256(json.dumps(_rules_dict(rules), sort_keys=True).encode()).hexdigest()
        if proof["entry_rules_sha256"] != rules_hash:
            raise ValueError("Residual rules differ from original BUY evidence")
        quantity, price = _decimal(receipt["quantity"]), _decimal(receipt["mark_price_tmn"])
        if enhanced and (not exception or exception["asset"] != asset
                or exception["proof"] != proof or receipt["operator_exception_sha256"] != exception["sha256"]):
            raise ValueError("Retained residual exception differs from original authority")
        limit = Decimal(600) if enhanced else Decimal(500)
        value, bound = quantity * price, min(limit, _decimal(proof["acquisition_cost_tmn"]) * Decimal(".005"))
        quantity_bound = rules.step_size + _decimal(proof["terminal_sell_quantity"]) * rules.taker_fee_rate
        if (price <= 0 or quantity > quantity_bound
                or value > bound or _decimal(receipt["marked_value_tmn"]) != value
                or _decimal(receipt["value_bound_tmn"]) != bound
                or not 0 <= _timestamp(receipt["at"]) - _timestamp(receipt["quote_received_at"]) <= 5
                or receipt["quote_received_at"] < proof["last_fill_at"]
                or (rules.quantize_quantity(quantity) != 0 and rules.quantize_quantity(quantity) * price >= rules.min_notional)):
            raise ValueError("Residual exceeds its original bounded dust classification")
        result[asset], previous = quantity, receipt["sha256"]
        aggregate += value
    if aggregate > Decimal(5000):
        raise ValueError("Residual aggregate marked value exceeds limit")
    return receipts, result, aggregate


def quarantined_residuals(ledger: Ledger) -> dict[str, Decimal]:
    """Validate retained dust on every use; never call it flat or spendable cash."""
    with ledger.transaction() as db:
        return _validated(ledger, db)[1]


def quarantine_residual(ledger: Ledger, rules: MarketRules, *, price_tmn: Decimal,
                        quote_received_at: int, now: int) -> bool:
    """Append an auditable classification only; the caller still owns finalization."""
    validate_decimal(price_tmn, "residual mark price", strictly_positive=True)
    if rules.quote_asset != "TMN" or rules.base_asset == "TMN":
        raise ValueError("Residual quarantine supports TMN spot markets only")
    if not 0 <= _timestamp(now) - _timestamp(quote_received_at) <= 5:
        raise ValueError("Residual classification requires a fresh quote")
    with ledger.transaction() as db:
        receipts, existing, aggregate = _validated(ledger, db)
        if rules.base_asset in existing:
            if receipts[next(i for i, r in enumerate(receipts) if r["asset"] == rules.base_asset)]["rules"] != _rules_dict(rules):
                raise ValueError("Residual rules changed after quarantine")
            return True
        balance = ledger.get_balance(rules.base_asset)
        if balance.total <= 0:
            return False
        quantity, stepped = balance.total, rules.quantize_quantity(balance.free)
        if stepped and stepped * price_tmn >= rules.min_notional:
            return False
        proof = _proof(ledger, db, rules.base_asset, rules.symbol)
        rules_hash = hashlib.sha256(json.dumps(_rules_dict(rules), sort_keys=True).encode()).hexdigest()
        if proof["entry_rules_sha256"] != rules_hash or quote_received_at < proof["last_fill_at"]:
            raise ValueError("Residual rule or quote provenance differs from original fills")
        if quantity > rules.step_size + _decimal(proof["terminal_sell_quantity"]) * rules.taker_fee_rate:
            return False
        pending = db.execute("SELECT 1 FROM order_intents WHERE status NOT IN "
                             "('FILLED','CANCELED','PARTIALLY_FILLED_CANCELED','REJECTED') LIMIT 1").fetchone()
        broker_pending = db.execute("SELECT 1 FROM live_broker_orders WHERE status NOT IN "
                                    "('FILLED','CANCELED','PARTIALLY_FILLED_CANCELED','REJECTED') LIMIT 1").fetchone()
        if pending or broker_pending:
            raise ValueError("Unresolved orders block a new residual classification")
        value = quantity * price_tmn
        exception = _operator_exception(ledger, db)
        enhanced = bool(exception and exception["asset"] == rules.base_asset and exception["proof"] == proof)
        bound = min(Decimal(600) if enhanced else Decimal(500), _decimal(proof["acquisition_cost_tmn"]) * Decimal(".005"))
        if value > bound:
            return False
        if len(receipts) >= 8 or aggregate + value > Decimal(5000):
            raise ValueError("Residual quarantine allowance exhausted")
        receipt = dict(schema_version=2 if enhanced else 1, journal_id=ledger.get_meta("journal_id"), asset=rules.base_asset,
                       symbol=rules.symbol, **proof, mark_price_tmn=str(price_tmn), marked_value_tmn=str(value),
                       value_bound_tmn=str(bound), rules=_rules_dict(rules), quote_received_at=quote_received_at,
                       at=now, previous_sha256=receipts[-1]["sha256"] if receipts else None)
        if enhanced:
            receipt["operator_exception_sha256"] = exception["sha256"]
        receipt["sha256"] = _digest(receipt)
        ledger.set_meta(KEY, json.dumps([*receipts, receipt], sort_keys=True))
        ledger._stage_event("RESIDUAL_QUARANTINED", "RISK", {
            **receipt, "classification": "UNSELLABLE_DUST_RETAINS_INVENTORY_AND_COST",
            "cash_conversion": False, "completed_round_trip": False,
        })
        return True
