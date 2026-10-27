"""Exact reconciliation by default; any display variance needs separate authority.

No balance, fill, fee or cost basis is adjusted. The optional policy is a bounded
operator acceptance of an observed discrepancy, not a claim about API rounding.
"""

import hashlib
import json
from decimal import Decimal
from pathlib import Path

from royin.market_data import decode_json
from royin.markets import parse_credit_balances
from royin.runtime_release import source_history

KEY = "fresh_display_variance_authority_v1"
POLICY = "BOUNDED_TMN_DISPLAY_VARIANCE_V1"


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _quiescence_hash(value):
    return (
        isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)
    )


def _binding(ledger):
    from royin.fresh_mission import FreshMissionPermit

    raw = ledger.get_meta("fresh_permit")
    permit = FreshMissionPermit.model_validate_json(raw)
    return permit, dict(
        journal_id=ledger.get_meta("journal_id"),
        permit_sha256=hashlib.sha256(raw.encode()).hexdigest(),
        account_sha256=permit.account_sha256,
    )


def _authority(ledger):
    raw = ledger.get_meta(KEY)
    if raw is None:
        return None
    value = json.loads(raw)
    permit, binding = _binding(ledger)
    if (
        not isinstance(value, dict)
        or value.get("sha256") != _digest({k: v for k, v in value.items() if k != "sha256"})
        or any(value.get(k) != v for k, v in binding.items())
        or value.get("policy") != POLICY
        or value.get("max_total_variance_tmn") != "0.5"
        or value.get("display_quantum_tmn") != "1"
        or (
            value.get("quiescent_restart_receipt_sha256") is not None
            and not _quiescence_hash(value["quiescent_restart_receipt_sha256"])
        )
        or value.get("from_source_sha256") not in source_history(ledger)
        or type(value.get("authorized_at")) is not int
        or not permit.start_at <= value["authorized_at"] < permit.end_at
        or value.get("valid_until") != permit.end_at
        or not isinstance(value.get("operator_instruction"), str)
        or not value["operator_instruction"].strip()
    ):
        raise ValueError("Display variance authority binding changed")
    return value


def _captured_snapshot(ledger, read_numbers, *, now):
    """Re-read three real, fresh, hash-verified captures from this ledger's account."""
    if (
        not isinstance(read_numbers, (list, tuple))
        or len(read_numbers) != 3
        or any(type(n) is not int or n <= 0 for n in read_numbers)
        or list(read_numbers) != sorted(set(read_numbers))
    ):
        raise ValueError("Three unique ordered original account read numbers required")
    directory = Path(ledger.db_path).resolve().parent / "account-captures"
    payloads, receipts = {}, []
    endpoints = ("/sub-accounts", "/v1/account/balances-detail", "/v1/account/openOrders")
    for number, endpoint in zip(read_numbers, endpoints, strict=True):
        receipt = json.loads((directory / f"read-{number}.json").read_text())
        sha = receipt.get("sha256")
        if (
            not isinstance(sha, str)
            or len(sha) != 64
            or any(c not in "0123456789abcdef" for c in sha)
            or receipt.get("path") != endpoint
            or receipt.get("status") != 200
            or type(receipt.get("received_at")) is not int
            or not 0 <= now - receipt["received_at"] <= 30
        ):
            raise ValueError("Original account snapshot is stale, invalid or incomplete")
        raw = (directory / (sha + ".json")).read_bytes()
        if hashlib.sha256(raw).hexdigest() != sha:
            raise ValueError("Original account capture hash changed")
        data = decode_json(raw)
        if not isinstance(data, dict) or data.get("success") is not True:
            raise ValueError("Original account capture failed")
        payloads[endpoint] = data
        receipts.append(dict(read_number=number, **receipt))
    permit, _ = _binding(ledger)
    data = payloads[endpoints[0]]
    rows = data.get("result")
    if (
        not isinstance(rows, list)
        or not isinstance(data.get("result_info", {}), dict)
        or data.get("result_info", {}).get("total_count", len(rows)) != len(rows)
    ):
        raise ValueError("Original sub-account list is incomplete")
    matching = [
        row
        for row in rows
        if isinstance(row, dict)
        and row.get("type") == "prop"
        and row.get("isActive") is True
        and row.get("isSuspend") is False
        and isinstance(row.get("clientId"), str)
        and hashlib.sha256(row["clientId"].encode()).hexdigest() == permit.account_sha256
    ]
    if len(matching) != 1:
        raise ValueError("Original account identity differs")
    data = payloads[endpoints[2]]
    rows = data.get("result")
    rows = rows.get("orders") if isinstance(rows, dict) else rows
    info = data.get("result_info", {})
    if (
        not isinstance(rows, list)
        or not isinstance(info, dict)
        or info.get("total_count", len(rows)) != len(rows)
    ):
        raise ValueError("Original open order list is incomplete")
    ids = [row["clientOrderId"] for row in rows]
    return parse_credit_balances(payloads[endpoints[1]]), ids, _digest(receipts)


def _same_snapshot(left, right):
    return set(left) == set(right) and all(
        (left[a].total, left[a].available, left[a].locked)
        == (right[a].total, right[a].available, right[a].locked)
        for a in left
    )


def assess_account_reconciliation(
    ledger, balances, ids, *, now, read_numbers=None, active_intent_id=None, _candidate=False
):
    """Return explicit EXACT / BOUNDED_DISPLAY_VARIANCE / MISMATCH evidence."""
    authority = _authority(ledger)
    authorization = json.loads(ledger.get_meta("fresh_authorization"))
    outside = Decimal(authorization["cash_baseline_tmn"]) - Decimal(authorization["allocation_tmn"])
    local = ledger.get_all_balances()
    assets = set(balances) | set(local)
    differences = {
        a: (balances[a].total if a in balances else Decimal(0))
        - ledger.get_balance(a).total
        - (outside if a == "TMN" else 0)
        for a in assets
    }
    with ledger.connection() as db:
        known = {r[0] for r in db.execute("SELECT client_id FROM live_broker_orders")}
        pending = db.execute(
            "SELECT client_id FROM order_intents WHERE status NOT IN "
            "('FILLED','CANCELED','PARTIALLY_FILLED_CANCELED','REJECTED')"
        ).fetchall()
        pending += db.execute(
            "SELECT client_id FROM live_broker_orders WHERE status NOT IN "
            "('FILLED','CANCELED','PARTIALLY_FILLED_CANCELED','REJECTED')"
        ).fetchall()
    owned = isinstance(ids, list) and len(ids) == len(set(ids)) and set(ids).issubset(known)
    exact = owned and all(value == 0 for value in differences.values())
    cash = balances.get("TMN")
    lower = min(ledger.get_balance("TMN").total, cash.available - outside) if cash else Decimal(0)
    report = dict(
        policy=POLICY,
        approved=exact,
        match_kind="EXACT" if exact else "MISMATCH",
        observed_at=now,
        exact_match=exact,
        cash_difference_tmn=str(differences.get("TMN", 0)),
        non_cash_differences={
            a: str(v) for a, v in sorted(differences.items()) if a != "TMN" and v
        },
        authority_sha256=None,
        observed_read_numbers=list(read_numbers) if read_numbers else None,
        snapshot_sha256=None,
        cash_safety_reserve_tmn="0",
        available_cash_lower_bound_tmn=str(max(Decimal(0), lower)),
    )
    if exact:
        return report
    candidate = (
        owned
        and not ids
        and cash is not None
        and not report["non_cash_differences"]
        and cash.total == cash.total.to_integral_value()
        and cash.available == cash.available.to_integral_value()
        and cash.locked == 0
        and Decimal(0) < abs(differences.get("TMN", Decimal(0))) <= Decimal(".5")
        and all(r[0] == active_intent_id for r in pending)
    )
    if not candidate or (not authority and not _candidate) or read_numbers is None:
        return report
    if authority and now >= authority["valid_until"]:
        return report
    captured, captured_ids, snapshot_sha = _captured_snapshot(ledger, read_numbers, now=now)
    if not _same_snapshot(captured, balances) or captured_ids != ids:
        raise ValueError("Account assessment differs from original captured observations")
    lower = min(ledger.get_balance("TMN").total, cash.available - outside - Decimal(".5"))
    report.update(
        approved=authority is not None,
        match_kind="BOUNDED_DISPLAY_VARIANCE" if authority else "AUTHORITY_REQUIRED",
        authority_sha256=authority["sha256"] if authority else None,
        snapshot_sha256=snapshot_sha,
        cash_safety_reserve_tmn="0.5",
        available_cash_lower_bound_tmn=str(max(Decimal(0), lower)),
    )
    return report


def authorize_display_variance(
    ledger,
    *,
    balances,
    ids,
    read_numbers,
    now,
    operator_instruction,
    quiescent_restart_receipt_sha256=None,
):
    """One separately reviewed bounded policy; never apply a cash/balance correction."""
    with ledger.transaction():
        if ledger.get_meta(KEY) is not None:
            raise ValueError("Display variance policy cannot be replaced or reinitialized")
        state = ledger.get_meta("service_state")
        interrupted = state == "RUNNING" and _quiescence_hash(quiescent_restart_receipt_sha256)
        if (
            (state != "PAUSED_RESTART" and not interrupted)
            or ledger._worker_active
            or not isinstance(operator_instruction, str)
            or not operator_instruction.strip()
        ):
            raise ValueError(
                "Paused original mission and explicit display-policy authority required"
            )
        report = assess_account_reconciliation(
            ledger, balances, ids, now=now, read_numbers=read_numbers, _candidate=True
        )
        if report["match_kind"] != "AUTHORITY_REQUIRED":
            raise ValueError("No fresh, bounded original-account display discrepancy to authorize")
        permit, binding = _binding(ledger)
        if not permit.start_at <= now < permit.end_at:
            raise ValueError("Original mission has expired")
        body = dict(
            policy=POLICY,
            **binding,
            from_source_sha256=source_history(ledger)[-1],
            max_total_variance_tmn="0.5",
            display_quantum_tmn="1",
            authorized_at=now,
            valid_until=permit.end_at,
            operator_instruction=operator_instruction,
            original_observation_sha256=report["snapshot_sha256"],
            original_difference_tmn=report["cash_difference_tmn"],
            quiescent_restart_receipt_sha256=quiescent_restart_receipt_sha256,
        )
        receipt = {**body, "sha256": _digest(body)}
        ledger.set_meta(KEY, json.dumps(receipt, sort_keys=True))
        return receipt


def verify_reconciliation_for_post(ledger, evidence, *, cid, debit_tmn, now):
    """Independently recheck a bounded witness after the intent locks its cash."""
    report = evidence.get("account_reconciliation")
    if report is None:
        return  # Existing exact-account authority remains independently required by the transport.
    if (
        not isinstance(report, dict)
        or not report.get("approved")
        or report.get("match_kind") not in ("EXACT", "BOUNDED_DISPLAY_VARIANCE")
    ):
        raise ValueError("Unapproved account reconciliation witness")
    if report.get("match_kind") == "EXACT" and report.get("observed_read_numbers") is None:
        if report.get("exact_match") is not True:
            raise ValueError("Exact host account assertion changed")
        return
    if type(report.get("observed_at")) is not int or not 0 <= now - report["observed_at"] <= 30:
        raise ValueError("Bounded account reconciliation witness expired")
    balances, ids, _ = _captured_snapshot(ledger, report.get("observed_read_numbers"), now=now)
    checked = assess_account_reconciliation(
        ledger,
        balances,
        ids,
        now=report["observed_at"],
        read_numbers=report["observed_read_numbers"],
        active_intent_id=cid,
    )
    if (
        not checked["approved"]
        or checked != report
        or debit_tmn > Decimal(checked["available_cash_lower_bound_tmn"])
    ):
        raise ValueError("Bounded account witness or conservative available cash changed")
