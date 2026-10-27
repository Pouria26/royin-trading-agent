"""Single explicit operator entry; never a model forecast or a reset of its mandate."""

import hashlib
import json
import uuid
from dataclasses import asdict
from decimal import ROUND_DOWN, Decimal

from royin.market_data import conservative_book_price
from royin.risk import RiskResult, choose_lot_quantity_for_exit, project_exit_cash

AUTH_KEY = "fresh_operator_entry_v1"
STATE_KEY = "fresh_operator_entry_state_v1"
RUNTIME_KEY = "fresh_operator_entry_runtime_v1"
POLICY = "BOUNDED_OPERATOR_ENTRY_V1"
SYMBOLS = ("BTCTMN", "PEPETMN", "PUMPTMN", "ARBTMN", "LTCTMN", "HBARTMN")


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def authorize_operator_entry(
    ledger, permit, *, now, expires_at, operator_instruction, symbol="BTCTMN", request_sha256=None
):
    """Caller owns the service lock, either in maintenance or in its sole worker."""
    from royin.runtime_release import source_history

    if (
        type(now) is not int
        or type(expires_at) is not int
        or not permit.start_at <= now < expires_at <= min(now + 7200, permit.entry_end_at)
        or not isinstance(operator_instruction, str)
        or not operator_instruction.strip()
        or symbol not in SYMBOLS
        or ledger.get_meta("fresh_permit") != permit.canonical()
    ):
        raise ValueError("Explicit bounded original-mission operator authority required")
    with ledger.transaction() as db:
        from royin.residuals import quarantined_residuals

        history = json.loads(ledger.get_meta(AUTH_KEY) or "[]")
        previous = load_operator_authority(ledger, permit) if history else None
        if request_sha256 and any(x.get("request_sha256") == request_sha256 for x in history):
            return next(x for x in history if x.get("request_sha256") == request_sha256)
        residuals = quarantined_residuals(ledger)
        if (
            len(history) >= 3
            or (previous and previous[1]["state"] not in ("COMPLETE", "EXPIRED"))
            or db.execute(
                "select 1 from order_intents where status not in ('FILLED','CANCELED','PARTIALLY_FILLED_CANCELED','REJECTED') limit 1"
            ).fetchone()
            or any(
                a != "TMN" and a not in residuals and b.total
                for a, b in ledger.get_all_balances().items()
            )
        ):
            raise ValueError(
                "Operator entry requires a flat reconciled lane and at most three authorities"
            )
        used = json.loads(ledger.get_meta("fresh_transport"))
        if used["buys"] >= permit.max_buys or used["attempts"] >= permit.max_attempts - 16:
            raise ValueError("Original financial allowance cannot be extended")
        body = dict(
            policy=POLICY,
            mission_id=permit.mission_id,
            account_sha256=permit.account_sha256,
            permit_sha256=hashlib.sha256(permit.canonical().encode()).hexdigest(),
            source_sha256=source_history(ledger)[-1],
            journal_id=ledger.get_meta("journal_id"),
            operator_instruction=operator_instruction,
            authorized_at=now,
            expires_at=expires_at,
            client_id=permit.mission_id + "_op_" + uuid.uuid4().hex[:12],
            symbol=symbol,
            max_debit_tmn="150000",
            stop_fraction="0.02",
            cancel_after_seconds=60,
            max_holding_seconds=900,
            max_buys=1,
            max_planned_loss_tmn="5000",
            sequence=len(history) + 1,
            previous_authority_sha256=history[-1]["sha256"] if history else None,
            previous_result=previous[1] if previous else None,
            request_sha256=request_sha256,
        )
        authority = {**body, "sha256": digest(body)}
        ledger.set_meta(AUTH_KEY, json.dumps([*history, authority]))
        ledger.set_meta(
            STATE_KEY, json.dumps(dict(state="AUTHORIZED", authority_sha256=authority["sha256"]))
        )
    return authority


def load_operator_authority(ledger, permit, *, _allow_pending_migration=False):
    from royin.runtime_release import source_history

    raw = ledger.get_meta(AUTH_KEY)
    if raw is None:
        return None
    history = json.loads(raw)
    if not isinstance(history, list) or not 1 <= len(history) <= 3:
        raise ValueError("Invalid bounded operator history")
    chain = source_history(ledger)
    for index, item in enumerate(history):
        if (
            not isinstance(item, dict)
            or item.get("sha256") != digest({k: v for k, v in item.items() if k != "sha256"})
            or item.get("sequence") != index + 1
            or item.get("previous_authority_sha256")
            != (history[index - 1]["sha256"] if index else None)
            or item.get("source_sha256") not in chain
        ):
            raise ValueError("Operator authority prefix changed")
    auth = history[-1]
    body = {k: v for k, v in auth.items() if k != "sha256"}
    if (
        auth.get("sha256") != digest(body)
        or auth.get("policy") != POLICY
        or auth.get("mission_id") != permit.mission_id
        or auth.get("account_sha256") != permit.account_sha256
        or auth.get("permit_sha256") != hashlib.sha256(permit.canonical().encode()).hexdigest()
        or auth.get("journal_id") != ledger.get_meta("journal_id")
        or auth.get("symbol") not in SYMBOLS
        or auth.get("max_debit_tmn") != "150000"
        or auth.get("stop_fraction") != "0.02"
        or auth.get("cancel_after_seconds") != 60
        or auth.get("max_holding_seconds") != 900
        or auth.get("max_buys") != 1
        or auth.get("max_planned_loss_tmn") != "5000"
        or not isinstance(auth.get("client_id"), str)
        or not auth["client_id"].startswith(permit.mission_id + "_op_")
        or type(auth.get("authorized_at")) is not int
        or type(auth.get("expires_at")) is not int
        or not permit.start_at
        <= auth["authorized_at"]
        < auth["expires_at"]
        <= min(auth["authorized_at"] + 7200, permit.entry_end_at)
    ):
        raise ValueError("Operator authority binding changed")
    state = json.loads(ledger.get_meta(STATE_KEY) or "null")
    if (
        not isinstance(state, dict)
        or state.get("authority_sha256") != auth["sha256"]
        or state.get("state") not in ("AUTHORIZED", "CLAIMED", "ATTEMPTED", "COMPLETE", "EXPIRED")
    ):
        raise ValueError("Operator authority state changed")
    source = operator_runtime_source(ledger, auth, chain)
    if (
        state["state"] in ("AUTHORIZED", "CLAIMED")
        and source != chain[-1]
        and not _allow_pending_migration
    ):
        raise ValueError("Pending operator authority belongs to another runtime")
    return auth, state


def operator_runtime_source(ledger, auth, chain):
    receipts = json.loads(ledger.get_meta(RUNTIME_KEY) or "[]")
    if not isinstance(receipts, list) or len(receipts) > 4:
        raise ValueError("Operator runtime amendments exceed their finite bound")
    previous = None
    source = auth["source_sha256"]
    for receipt in receipts:
        body = {k: v for k, v in receipt.items() if k != "sha256"}
        if (
            receipt.get("sha256") != digest(body)
            or receipt.get("previous_sha256") != previous
            or receipt.get("from_source_sha256") not in chain
            or receipt.get("to_source_sha256") not in chain
        ):
            raise ValueError("Operator runtime amendment prefix changed")
        if receipt["authority_sha256"] == auth["sha256"]:
            if receipt["from_source_sha256"] != source:
                raise ValueError("Operator runtime amendment source differs")
            source = receipt["to_source_sha256"]
        previous = receipt["sha256"]
    return source


def authorize_operator_runtime(
    ledger, permit, *, expected_authority_sha256, operator_instruction, now
):
    """Quiescent repair before POST; authority, time, state and attempt counters stay intact."""
    from royin.runtime_release import source_history

    auth, state = load_operator_authority(ledger, permit, _allow_pending_migration=True)
    chain = source_history(ledger)
    source = operator_runtime_source(ledger, auth, chain)
    with ledger.transaction() as db:
        if (
            auth["sha256"] != expected_authority_sha256
            or state["state"] != "AUTHORIZED"
            or not auth["authorized_at"] <= now < auth["expires_at"]
            or source == chain[-1]
            or db.execute(
                "select 1 from order_intents where client_id=?", (auth["client_id"],)
            ).fetchone()
            or auth["client_id"] in json.loads(ledger.get_meta("fresh_transport"))["post_ids"]
            or not isinstance(operator_instruction, str)
            or not operator_instruction.strip()
        ):
            raise ValueError(
                "Only an unattempted operator authority may receive an explicit runtime repair"
            )
        history = json.loads(ledger.get_meta(RUNTIME_KEY) or "[]")
        if len(history) >= 4:
            raise ValueError("Operator runtime amendment allowance exhausted")
        body = dict(
            authority_sha256=auth["sha256"],
            from_source_sha256=source,
            to_source_sha256=chain[-1],
            previous_sha256=history[-1]["sha256"] if history else None,
            at=now,
            operator_instruction_sha256=hashlib.sha256(operator_instruction.encode()).hexdigest(),
        )
        receipt = {**body, "sha256": digest(body)}
        ledger.set_meta(RUNTIME_KEY, json.dumps([*history, receipt]))
    load_operator_authority(ledger, permit)
    return receipt


def ingest_operator_requests(ledger, permit, directory, *, now):
    """The sole financial worker consumes durable operator requests, without another trader."""
    if not directory.exists():
        return
    if not ledger._worker_active:
        raise ValueError("Operator request ingestion requires the original financial worker")
    for path in sorted(directory.glob("request-*.json"))[:3]:
        request = json.loads(path.read_text(encoding="utf-8"))
        body = {k: v for k, v in request.items() if k != "sha256"}
        if (
            request.get("sha256") != digest(body)
            or request.get("mission_id") != permit.mission_id
            or request.get("permit_sha256")
            != hashlib.sha256(permit.canonical().encode()).hexdigest()
            or request.get("account_sha256") != permit.account_sha256
        ):
            raise ValueError("Operator request is not bound to the original mission")
        authority = authorize_operator_entry(
            ledger,
            permit,
            now=now,
            expires_at=request["expires_at"],
            operator_instruction=request["operator_instruction"],
            symbol=request["symbol"],
            request_sha256=request["sha256"],
        )
        applied = path.with_suffix(".applied")
        if applied.exists() and json.loads(applied.read_text(encoding="utf-8")) != request:
            raise ValueError("Operator request receipt identity changed")
        path.replace(applied)
        path.with_suffix(".receipt").write_text(
            json.dumps(
                dict(
                    authority_sha256=authority["sha256"],
                    client_id=authority["client_id"],
                    sequence=authority["sequence"],
                )
            ),
            encoding="utf-8",
        )


def plan_operator_entry(auth, rules, depth, *, equity_tmn, free_cash_tmn, risk_scale):
    """Passive best-bid LIMIT, explicit 2% stop; all four fee/residual cases stay enforced."""
    if (
        rules.symbol != auth["symbol"]
        or rules.quote_asset != "TMN"
        or rules.taker_fee_rate > Decimal(".003")
    ):
        raise ValueError("Operator market or fee is outside authority")
    bid = Decimal(depth["result"]["bid"][0]["price"])
    ask = Decimal(depth["result"]["ask"][0]["price"])
    if (
        not bid.is_finite()
        or not ask.is_finite()
        or not 0 < bid <= ask
        or 1 - bid / ask > Decimal(".005")
    ):
        raise ValueError("Operator book or spread is invalid")
    price = (bid / rules.tick_size).to_integral_value(rounding=ROUND_DOWN) * rules.tick_size
    stop = (price * (1 - Decimal(auth["stop_fraction"])) / rules.tick_size).to_integral_value(
        rounding=ROUND_DOWN
    ) * rules.tick_size
    cap = min(Decimal(auth["max_debit_tmn"]), free_cash_tmn, equity_tmn * Decimal(".50"))
    quantity = choose_lot_quantity_for_exit(
        rules,
        rules.quantize_quantity(cap / (price * (1 + rules.taker_fee_rate))),
        price,
        stop,
        reserve_exit_base_fee=True,
    )
    if quantity is None:
        raise ValueError("Operator quantity has no bounded sellable exit")
    buy = conservative_book_price(depth, "BUY", quantity)
    sell = conservative_book_price(depth, "SELL", quantity)
    if buy is None or sell is None or sell > buy:
        raise ValueError("Operator order lacks full entry and unwind depth")
    cases = project_exit_cash(
        rules=rules,
        quantity=quantity,
        entry_price=price,
        exit_price=stop,
        reserve_exit_base_fee=True,
    )
    debit = quantity * price * (1 + rules.taker_fee_rate)
    loss = max(-Decimal(c["net_lower_bound_tmn"]) for c in cases)
    reserve = debit * (
        Decimal(auth["stop_fraction"])
        + 2 * rules.taker_fee_rate
        + Decimal(".001")
        + rules.tick_size / price
    ) + Decimal(500)
    if (
        not all(c["sellable"] and c["residual_within_budget"] for c in cases)
        or not Decimal(0) < risk_scale <= 1
        or reserve > equity_tmn * Decimal(".005") * risk_scale
        or max(loss, reserve) > Decimal(auth["max_planned_loss_tmn"])
    ):
        raise ValueError("Operator planned stop loss exceeds existing account risk or explicit cap")
    risk = RiskResult(
        True,
        "Explicit one-time operator entry; no model profit claim",
        "ENTER",
        rules.symbol,
        quantity,
        price,
        stop,
        quantity * price * rules.taker_fee_rate,
    )
    plan = dict(
        policy=POLICY,
        source_kind="OPERATOR",
        approved=True,
        max_debit_tmn=auth["max_debit_tmn"],
        projected_debit_tmn=str(debit),
        planned_stop_loss_tmn=str(loss),
        planned_loss_reserve_tmn=str(reserve),
        account_risk_budget_tmn=format(
            (equity_tmn * Decimal(".005") * risk_scale).normalize(), "f"
        ),
        stop_fraction=auth["stop_fraction"],
        actual_loss_cap_guaranteed=False,
        fee_cases=cases,
    )
    return risk, plan


def validate_operator_post(
    ledger, permit, rules, evidence, *, cid, price, quantity, now, equity_tmn
):
    """Inside the transport transaction: consume the one-off permission before network I/O."""
    loaded = load_operator_authority(ledger, permit)
    if loaded is None:
        raise ValueError("Missing explicit operator authority")
    auth, state = loaded
    end = evidence.get("position_end_at")
    if (
        state["state"] != "CLAIMED"
        or state.get("client_id") != cid
        or cid != auth["client_id"]
        or not auth["authorized_at"] <= now < auth["expires_at"]
        or evidence.get("operator_authority_sha256") != auth["sha256"]
        or evidence.get("source_kind") != "OPERATOR"
        or evidence.get("action") != "ENTER"
        or evidence.get("symbol") != auth["symbol"]
        or rules.symbol != auth["symbol"]
        or evidence.get("rules_sha256")
        != hashlib.sha256(
            json.dumps(asdict(rules), default=str, sort_keys=True).encode()
        ).hexdigest()
        or evidence.get("target_net_approved") is not False
        or evidence.get("account_reconciled") is not True
        or type(evidence.get("quote_received_at")) is not int
        or not 0 <= now - evidence["quote_received_at"] <= 5
        or type(end) is not int
        or not now
        < end
        <= min(state["claimed_at"] + auth["max_holding_seconds"], permit.entry_end_at)
        or evidence.get("cancel_after_seconds") != 60
    ):
        raise ValueError("Fresh bound one-time operator evidence required")
    depth = evidence.get("final_depth")
    risk, plan = plan_operator_entry(
        auth,
        rules,
        depth,
        equity_tmn=equity_tmn,
        free_cash_tmn=Decimal(auth["max_debit_tmn"]),
        risk_scale=Decimal(evidence["risk_scale"]),
    )
    if (
        risk.price != Decimal(price)
        or risk.quantity != Decimal(quantity)
        or plan != evidence.get("capital_plan")
        or ledger.get_meta("capital_block_reason")
        or ledger.get_meta("entry_block_reason")
    ):
        raise ValueError("Operator price, capital or current risk state changed")
    ledger.set_meta(
        STATE_KEY,
        json.dumps(
            dict(
                state="ATTEMPTED",
                authority_sha256=auth["sha256"],
                client_id=cid,
                claimed_at=state["claimed_at"],
                attempted_at=now,
            )
        ),
    )


def operator_order_origin(ledger, client_id, authority):
    """Persist true attribution for later cumulative fills and outbox replay."""
    from royin.runtime_release import source_history

    audit = ledger.audit
    origin = dict(
        run_id=getattr(audit, "run_id", authority["mission_id"]),
        mode=getattr(audit, "mode", "LIVE_BOUNDED"),
        source="OPERATOR",
        hashes=dict(
            operator_authority=authority["sha256"],
            source=operator_runtime_source(ledger, authority, source_history(ledger)),
        ),
        context=dict(symbol=authority["symbol"]),
    )
    if ledger.get_meta("audit_order_" + client_id) is not None:
        raise ValueError("An existing order origin cannot be overwritten")
    ledger.set_meta("audit_order_" + client_id, json.dumps(origin))
