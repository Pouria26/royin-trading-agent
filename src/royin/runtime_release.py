"""Explicit source transitions on the original mission; never initialize financial state."""

import hashlib
import json
import re
import time

# Bounded release history; old receipts stay byte-for-byte intact during extension.
MAX_SOURCE_TRANSITIONS = 32


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def source_history(metadata):
    """Validate append-only receipts while retaining the original source/permit binding."""
    get = metadata.get if isinstance(metadata, dict) else metadata.get_meta
    original = get("fresh_source_sha256")
    if not original or not re.fullmatch(r"[0-9a-f]{64}", original):
        raise ValueError("Original financial source binding required")
    receipts = json.loads(get("runtime_source_history") or "[]")
    if not isinstance(receipts, list) or len(receipts) > MAX_SOURCE_TRANSITIONS:
        raise ValueError("Invalid bounded runtime source history")
    sources, previous_receipt = [original], None
    for receipt in receipts:
        body = {k: v for k, v in receipt.items() if k != "sha256"}
        schedule = "entry_analysis_interval_seconds" in receipt or "service_contract_sha256" in receipt
        pool = "model_budget_pool_id" in receipt or "model_budget_pool_sha256" in receipt
        if (receipt.get("sha256") != digest(body)
                or receipt.get("previous_receipt_sha256") != previous_receipt
                or receipt.get("from_source_sha256") != sources[-1]
                or receipt.get("config_sha256") != get("fresh_config_sha256")
                or receipt.get("permit_sha256") != hashlib.sha256(get("fresh_permit").encode()).hexdigest()
                or not re.fullmatch(r"[0-9a-f]{64}", receipt.get("to_source_sha256", ""))
                or (schedule and (
                    type(receipt.get("entry_analysis_interval_seconds")) is not int
                    or receipt["entry_analysis_interval_seconds"] not in (300, 900, 1200)
                    or receipt.get("service_contract_sha256") != get("fresh_contract_sha256")
                    or not re.fullmatch(r"[0-9a-f]{64}", receipt.get("service_contract_sha256") or "")
                )) or (pool and (
                    not schedule
                    or not re.fullmatch(r"boxapi-pool-[a-z0-9_-]{1,40}", receipt.get("model_budget_pool_id") or "")
                    or not re.fullmatch(r"[0-9a-f]{64}", receipt.get("model_budget_pool_sha256") or "")
                ))):
            raise ValueError("Runtime source history binding mismatch")
        sources.append(receipt["to_source_sha256"])
        previous_receipt = receipt["sha256"]
    return tuple(sources)


def entry_analysis_interval(metadata, contract):
    """Apply only audited schedule amendments; never move a pending analysis deadline."""
    source_history(metadata)
    get = metadata.get if isinstance(metadata, dict) else metadata.get_meta
    interval = contract.analysis_interval_seconds
    for receipt in json.loads(get("runtime_source_history") or "[]"):
        if "entry_analysis_interval_seconds" in receipt:
            if receipt["service_contract_sha256"] != contract.sha256:
                raise ValueError("Entry cadence amendment differs from the original service contract")
            interval = receipt["entry_analysis_interval_seconds"]
    return interval


def model_pool_binding(metadata, contract):
    source_history(metadata)
    get = metadata.get if isinstance(metadata, dict) else metadata.get_meta
    result = (None, None)
    for receipt in json.loads(get("runtime_source_history") or "[]"):
        if "model_budget_pool_id" in receipt:
            if receipt["service_contract_sha256"] != contract.sha256:
                raise ValueError("Model funding pool differs from the original service contract")
            result = (receipt["model_budget_pool_id"],receipt["model_budget_pool_sha256"])
    return result


def authorize_source_transition(ledger, *, expected_source_sha256, target_source_sha256,
                                artifact_sha256, backup_receipt_sha256, operator_instruction,
                                quiescent_restart_receipt_sha256=None,
                                entry_analysis_interval_seconds=None,
                                model_budget_pool_id=None, model_budget_pool_sha256=None):
    """Caller holds the exclusive service owner lock and retains consistent backups.

    The platform may kill a container before its terminal status is persisted. That
    case needs a separate observed quiescence receipt, without relabeling old RUNNING
    metadata as a graceful stop. Tradable open-position upgrades are unsupported;
    proven bounded dust is retained explicitly, never called a flat cash account.
    """
    for value in (expected_source_sha256, target_source_sha256, artifact_sha256, backup_receipt_sha256):
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError("Exact source, artifact and backup hashes required")
    if not isinstance(operator_instruction, str) or not operator_instruction.strip():
        raise ValueError("Explicit operator source transition authority required")
    if entry_analysis_interval_seconds is not None and (
        type(entry_analysis_interval_seconds) is not int
        or entry_analysis_interval_seconds not in (300, 900, 1200)
        or not re.fullmatch(r"[0-9a-f]{64}", ledger.get_meta("fresh_contract_sha256") or "")
    ):
        raise ValueError("Bounded entry cadence and original service contract binding required")
    if (model_budget_pool_id is not None or model_budget_pool_sha256 is not None) and (
        entry_analysis_interval_seconds is None
        or not re.fullmatch(r"boxapi-pool-[a-z0-9_-]{1,40}", model_budget_pool_id or "")
        or not re.fullmatch(r"[0-9a-f]{64}", model_budget_pool_sha256 or "")
    ):
        raise ValueError("Complete model funding pool and schedule binding required")
    with ledger.transaction() as db:
        history = source_history(ledger)
        if expected_source_sha256 != history[-1] or target_source_sha256 == history[-1]:
            raise ValueError("Expected active runtime source differs or transition is redundant")
        state = ledger.get_meta("service_state")
        interrupted = (state == "RUNNING" and isinstance(quiescent_restart_receipt_sha256, str)
                       and re.fullmatch(r"[0-9a-f]{64}", quiescent_restart_receipt_sha256))
        if state != "PAUSED_RESTART" and not interrupted:
            raise ValueError("Runtime source transition requires a paused or externally verified quiescent mission")
        pending = db.execute("SELECT 1 FROM order_intents WHERE status NOT IN "
            "('FILLED','CANCELED','PARTIALLY_FILLED_CANCELED','REJECTED') LIMIT 1").fetchone()
        broker_pending = db.execute("SELECT 1 FROM live_broker_orders WHERE status NOT IN "
            "('FILLED','CANCELED','PARTIALLY_FILLED_CANCELED') LIMIT 1").fetchone()
        from royin.residuals import quarantined_residuals
        residuals = quarantined_residuals(ledger)
        if pending or broker_pending or any(a != "TMN" and a not in residuals and b.total
                                            for a, b in ledger.get_all_balances().items()):
            raise ValueError("Source transition requires flat reconciled state, preserving unknown intents")
        receipts = json.loads(ledger.get_meta("runtime_source_history") or "[]")
        if len(receipts) >= MAX_SOURCE_TRANSITIONS:
            raise ValueError("Runtime source transition allowance exhausted")
        receipt = dict(schema_version=1, at=int(time.time()), from_source_sha256=history[-1],
            to_source_sha256=target_source_sha256, artifact_sha256=artifact_sha256,
            backup_receipt_sha256=backup_receipt_sha256,
            quiescent_restart_receipt_sha256=quiescent_restart_receipt_sha256,
            preserved_residual_assets={a:str(q) for a,q in residuals.items()},
            operator_instruction_sha256=hashlib.sha256(operator_instruction.encode()).hexdigest(),
            config_sha256=ledger.get_meta("fresh_config_sha256"),
            permit_sha256=hashlib.sha256(ledger.get_meta("fresh_permit").encode()).hexdigest(),
            previous_receipt_sha256=receipts[-1]["sha256"] if receipts else None)
        if entry_analysis_interval_seconds is not None:
            receipt.update(entry_analysis_interval_seconds=entry_analysis_interval_seconds,
                service_contract_sha256=ledger.get_meta("fresh_contract_sha256"))
        if model_budget_pool_id is not None:
            receipt.update(model_budget_pool_id=model_budget_pool_id,
                           model_budget_pool_sha256=model_budget_pool_sha256)
        receipt["sha256"] = digest(receipt)
        ledger.set_meta("runtime_source_history", json.dumps([*receipts, receipt], sort_keys=True))
    return receipt
