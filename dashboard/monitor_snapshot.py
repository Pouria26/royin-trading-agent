"""Allowlisted monitoring exports only; no trading imports or financial database connections."""

import json
from decimal import Decimal
from pathlib import Path

from dashboard.model_metrics import metrics_view
from dashboard.sources import decimal, ident, project_balances, text

MAX_PUSH_BYTES = 256 * 1024
MAX_SIGNAL_BYTES = 8 * 1024 * 1024
EVENT_FIELDS = ("client_id", "fill_id", "symbol", "side", "action", "status", "reason", "fee_asset")


def stamp(value):
    if type(value) is not int or not 0 < value < 4102444800:
        raise ValueError("Invalid monitoring timestamp")
    return value


def snapshot_view(raw, mission):
    if (raw.get("mode") != "LIVE_BOUNDED" or raw.get("run_id") != mission
            or raw.get("source") != "RECORDED_FINANCIAL_LEDGER"
            or raw.get("evidence_kind") != "REAL_CREDIT_ACCOUNT"):
        raise ValueError("Unexpected monitoring source")
    balances = project_balances(raw.get("account", {}).get("balances"), totals=True)
    if "TMN" not in balances:
        raise ValueError("Missing cash balance")
    equity = decimal(raw.get("account", {}).get("equity_tmn"), False)
    account = dict(balances=balances,equity_tmn=equity)
    warnings = ["RECORDED_BROKER_LEDGER_NOT_EXCHANGE_STREAM", "READ_ONLY_MONITOR_COPY"]
    residuals = raw.get("account",{}).get("residual_assets",{})
    if not isinstance(residuals,dict) or len(residuals) > 8:
        raise ValueError("Invalid residual monitor projection")
    if residuals:
        if raw["account"].get("equity_basis") != "LIQUID_VALUE_EXCLUDING_RECORDED_DUST":
            raise ValueError("Residual valuation basis is missing")
        clean = {}
        for asset, quantity in residuals.items():
            amount = decimal(quantity,False)
            if (asset == "TMN" or asset not in balances or amount is None or Decimal(amount) <= 0
                    or Decimal(amount) != Decimal(balances[asset]["total"])
                    or Decimal(balances[asset]["locked"]) != 0):
                raise ValueError("Residual projection disagrees with actual inventory")
            clean[asset] = amount
        account.update(residual_assets=clean,equity_basis="LIQUID_VALUE_EXCLUDING_RECORDED_DUST")
        warnings.append("NON_TMN_RESIDUAL_NOT_FINALIZED")
    return dict(schema_version="royin.engine-monitor.v1", source="RECORDED_FINANCIAL_LEDGER",
                evidence_kind="REAL_CREDIT_ACCOUNT", mode="LIVE_BOUNDED", run_id=mission,
                worker_state=ident(raw.get("worker_state")),
                heartbeat_at=stamp(raw.get("heartbeat_at")), observed_at=stamp(raw.get("observed_at")),
                account=account,
                risk=dict(status=ident(raw.get("risk", {}).get("status"))),
                warnings=warnings)


def activity_view(raw):
    decisions, events = [], []
    for row in raw.get("decisions", [])[-12:]:
        decisions.append(dict(decision_id=ident(row.get("decision_id")), symbol=ident(row.get("symbol")),
                              action=ident(row.get("action")), cutoff=stamp(row.get("cutoff")),
                              reason=text(row.get("reason")), host_outcome=ident(row.get("host_outcome")),
                              evidence_kind=ident(row.get("evidence_kind"))))
    for row in raw.get("events", [])[-80:]:
        kind = row.get("event_type")
        if kind not in ("INTENT", "FILL", "CANCEL", "ENTRY_GATE"):
            continue
        values = {key: text(row.get(key)) if key == "reason" else ident(row.get(key)) for key in EVENT_FIELDS}
        values.update({key: decimal(row.get(key)) for key in ("price", "quantity", "fee")})
        events.append(dict(event_type=kind, recorded_at=text(row.get("recorded_at")), **values))
    result = dict(decisions=decisions, events=events,
                  warnings=["RECENT_BOUNDED_RECORDS_NOT_FULL_HISTORY", "AUDIT_EVENT_ALONE_IS_NOT_EXCHANGE_FINALITY"])
    if raw.get("model_metrics") is not None:
        result["model_metrics"] = metrics_view(raw["model_metrics"])
    return result


def read_json(path, limit):
    with Path(path).open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("Monitoring source exceeds size limit")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Monitoring source must be an object")
    return data


def read_activity(mission_root):
    """Read existing atomic manifests and an audit tail without touching SQLite."""
    root = Path(mission_root)
    decisions, events = [], []
    warnings = []
    try:
        compact = root / "signals/monitor-decisions.json"
        if compact.is_file():
            projection = read_json(compact, MAX_PUSH_BYTES)
            if projection.get("schema_version") != "royin.monitor-decisions.v1":
                raise ValueError("Unexpected compact decision schema")
            decisions = projection["decisions"]
            rows = []
        else:
            manifest = read_json(root / "signals/manifest.json", MAX_SIGNAL_BYTES)
            rows = manifest.get("arms", {}).get("paper_portfolio", {}).get("decision_traces", [])
        for row in rows[-12:]:
            decision = row.get("decision", {})
            if decision.get("cutoff"):
                decisions.append(dict(**{k: decision.get(k) for k in
                                        ("decision_id", "symbol", "action", "cutoff", "reason")},
                                      host_outcome=row.get("model_trace", {}).get("host_outcome"),
                                      evidence_kind=row.get("model_trace", {}).get("evidence_kind")))
    except (OSError, ValueError, TypeError, AttributeError):
        warnings.append("SIGNAL_LOG_UNAVAILABLE")
    result = activity_view(dict(decisions=decisions, events=events))
    audit = read_audit(root)
    result.update(events=audit["events"])
    result["warnings"].extend([*warnings, *audit["warnings"]])
    return result


def read_audit(root):
    events, warnings = [], []
    try:
        with (Path(root) / "financial-audit/audit_trail.jsonl").open("rb") as stream:
            stream.seek(0, 2)
            start = max(0, stream.tell() - MAX_PUSH_BYTES)
            stream.seek(start)
            raw = stream.read(MAX_PUSH_BYTES)
        lines = raw.splitlines(keepends=True)
        if start:
            lines = lines[1:]
        for line in lines[-160:]:
            if not line.endswith(b"\n"):
                continue
            try:
                row = json.loads(line)
                events.append(dict(event_type=row.get("event_type"), recorded_at=row.get("recorded_at"),
                                   **{k: row.get("payload", {}).get(k) for k in
                                      (*EVENT_FIELDS, "price", "quantity", "fee")}))
            except (ValueError, TypeError, AttributeError):
                warnings.append("AUDIT_LINE_UNAVAILABLE")
    except OSError:
        warnings.append("AUDIT_LOG_UNAVAILABLE")
    result = activity_view(dict(decisions=[], events=events))
    result["warnings"].extend(warnings)
    return result
