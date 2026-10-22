"""Bounded, allowlisted monitoring projections. No engine imports or outbound HTTP."""

import hashlib
import json
import re
import sqlite3
import threading
from contextlib import closing
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path

MAX_BYTES = 8 * 1024 * 1024
MAX_ROWS = 5000
ID = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")
HASH = re.compile(r"[a-f0-9]{64}\Z")
MONEY = re.compile(r"-?\d{1,40}(?:\.\d{1,40})?(?:[Ee][+-]?\d{1,3})?\Z")
ARM_NAMES = ("cash", "hold_shared_risk", "rule", "rule_ai")
METRICS = (
    "initial_capital_tmn", "final_cash_tmn", "final_equity_mtm_tmn",
    "total_realized_pnl", "net_pnl_mtm_tmn", "net_return_pct", "max_drawdown_pct",
    "total_fees_paid_tmn", "total_fees_paid_base", "peak_exposure_tmn",
    "residual_dust_base", "simulated_market_exit_slippage_tmn",
)
COUNTS = ("decisions_count", "orders_submitted", "total_orders_including_stop_finalization", "fills_count", "closed_round_trips")
FEATURES = ("last_close", "trend_sma_fast", "trend_sma_slow", "rsi_14", "atr_14",
            "volume_ratio", "current_position_base", "available_tmn_cash")


def text(value):
    if not isinstance(value, str):
        return None
    # Secret-bearing free text is omitted, not merely made visually safe.
    if re.search(r"(?i)(\bsk-[\w-]{12,}|bearer\s|api[_ -]?key|secret|password|https?://|[A-Z]:\\)", value):
        return "[متن حساس حذف شد]"
    return "".join(c for c in value[:600] if c >= " " or c == "\n")


def ident(value):
    return value if isinstance(value, str) and ID.fullmatch(value) else None


def digest(value):
    return value if isinstance(value, str) and HASH.fullmatch(value) else None


def decimal(value, negative=True):
    if value is None:
        return None
    if not isinstance(value, str) or not MONEY.fullmatch(value):
        raise ValueError("invalid decimal")
    try:
        number = Decimal(value)
        if not number.is_finite() or abs(number) > Decimal("1e40") or (not negative and number < 0):
            raise ValueError("invalid decimal")
        return value
    except InvalidOperation as exc:
        raise ValueError("invalid decimal") from exc


def project_balances(balances, *, totals=False):
    if not isinstance(balances, dict) or not 1 <= len(balances) <= 32:
        raise ValueError("invalid balances")
    result = {}
    for asset, balance in balances.items():
        if not isinstance(asset, str) or not re.fullmatch(r"[A-Z0-9]{1,20}", asset) or not isinstance(balance, dict):
            raise ValueError("invalid asset balance")
        fields = ("free", "locked", "total") if totals else ("free", "locked")
        values = {key: decimal(balance.get(key), False) for key in fields}
        if any(value is None for value in values.values()):
            raise ValueError("missing asset balance")
        with localcontext() as ctx:
            ctx.prec = 128
            if totals and Decimal(values["free"]) + Decimal(values["locked"]) != Decimal(values["total"]):
                raise ValueError("inconsistent asset balance")
        result[asset] = values
    return result


def count(value):
    if value is None:
        return None
    if type(value) is not int or not 0 <= value <= 10**12:
        raise ValueError("invalid count")
    return value


def timestamp(value):
    if value is None:
        return None
    if type(value) is int and 0 < value < 4102444800:
        return datetime.fromtimestamp(value, UTC).isoformat()
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is not None and 1970 < parsed.year < 2100:
                return parsed.astimezone(UTC).isoformat()
        except ValueError:
            pass
    raise ValueError("invalid timestamp")


def envelope(status="UNAVAILABLE", **values):
    return dict(schema_version="royin.monitor.v1", source=None, evidence_kind=None,
                run_id=None, revision=None, sha256=None, observed_at=None,
                received_at=None, status=status, warnings=[], **values)


def bounded_list(value):
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > MAX_ROWS:
        raise ValueError("row bound")
    return value


def readonly_budget(path):
    """One consistent bounded transaction; never constructs Ledger or migrations."""
    result = envelope(source_name="model_reservations", unit="USD", amount=None,
                      requests=None, reserved_tokens=None, provider_usage=None, invoice=None)
    result["source"] = "LOCAL_DURABLE_RESERVATION"
    result["evidence_kind"] = "CONSERVATIVE_RESERVATION_NOT_INVOICE"
    if not path.is_file():
        return result
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=.2)) as db:
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            columns = {row[1] for row in db.execute("PRAGMA table_info(model_reservations)")}
            if columns != {"id", "day", "nano_usd", "tokens", "model", "policy_hash"}:
                raise ValueError("schema")
            db.set_progress_handler(lambda: 1, 200000)
            rows = db.execute("SELECT nano_usd,tokens FROM model_reservations LIMIT 10001").fetchall()
            if len(rows) > 10000:
                raise ValueError("bound")
            for cost, tokens in rows:
                count(cost)
                count(tokens)
            total = sum(r[0] for r in rows)
            result.update(status="AVAILABLE" if rows else "EMPTY", requests=len(rows),
                          reserved_tokens=sum(r[1] for r in rows), amount=str(Decimal(total) / 10**9))
    except sqlite3.OperationalError:
        result.update(status="UNAVAILABLE", warnings=["BUDGET_BUSY_OR_UNREADABLE"])
    except (sqlite3.DatabaseError, ValueError):
        result.update(status="INVALID", warnings=["BUDGET_SCHEMA_OR_VALUES_INVALID"])
    return result


def readonly_reflections(path):
    result = envelope(source_name="trade_reflections", items=[])
    result["source"] = "LOCAL_DURABLE_LEDGER"
    result["evidence_kind"] = "REFLEXION_LEARNING_LOG"
    if not path.is_file():
        result.update(status="EMPTY", warnings=["LEDGER_NOT_INITIALIZED_YET"])
        return result
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=.2)) as db:
            db.execute("PRAGMA query_only=ON")
            has_table = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='trade_reflections'"
            ).fetchone()
            if not has_table:
                result.update(status="EMPTY", warnings=["NO_REFLECTIONS_TABLE"])
                return result
            rows = db.execute(
                "SELECT reflection_id, trade_id, symbol, entry_time, exit_time, net_pnl_tmn, return_pct, exit_reason, lesson, recorded_at "
                "FROM trade_reflections ORDER BY recorded_at DESC LIMIT 50"
            ).fetchall()
            items = []
            for r in rows:
                items.append({
                    "reflection_id": ident(r[0]),
                    "trade_id": ident(r[1]),
                    "symbol": ident(r[2]),
                    "entry_time": timestamp(r[3]),
                    "exit_time": timestamp(r[4]),
                    "net_pnl_tmn": decimal(r[5], negative=True),
                    "return_pct": decimal(r[6], negative=True),
                    "exit_reason": text(r[7]),
                    "lesson": text(r[8]),
                    "recorded_at": timestamp(r[9]),
                })
            result.update(status="AVAILABLE" if items else "EMPTY", items=items)
    except sqlite3.OperationalError:
        result.update(status="UNAVAILABLE", warnings=["LEDGER_BUSY_OR_UNREADABLE"])
    except (sqlite3.DatabaseError, ValueError):
        result.update(status="INVALID", warnings=["LEDGER_SCHEMA_OR_VALUES_INVALID"])
    return result


def public_tail(path):
    """Read at most 64 KiB; unfinished last line is never parsed as an event."""
    if not path.is_file():
        return [], []
    with path.open("rb") as stream:
        stream.seek(0, 2)
        size = stream.tell()
        start = max(0, size - 65536)
        stream.seek(start)
        raw = stream.read(65536)
    lines = raw.splitlines(keepends=True)
    if start and lines:
        lines.pop(0)
    warnings = []
    if lines and not lines[-1].endswith(b"\n"):
        lines.pop()
        warnings.append("PARTIAL_APPEND_IGNORED")
    events, seen = [], set()
    for line in lines[-100:]:
        try:
            event = json.loads(line)
            event_id = ident(event.get("event_id"))
            kind = event.get("event_type")
            if kind not in {"OBSERVATION_STARTED", "OBSERVE_SNAPSHOT", "OBSERVATION_FINISHED", "OBSERVATION_ERROR"}:
                continue
            if not event_id or event_id in seen:
                continue
            seen.add(event_id)
            events.append(dict(event_id=event_id, event_type=kind,
                               observed_at=timestamp(event.get("occurred_at")),
                               received_at=timestamp(event.get("recorded_at"))))
        except (ValueError, TypeError, AttributeError):
            warnings.append("INVALID_AUDIT_LINE_IGNORED")
    return events, sorted(set(warnings))


class Sources:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.cache = {}
        self.lock = threading.Lock()

    def read(self, path):
        path = path.resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("source outside root")
        stat = path.stat()
        if stat.st_size > MAX_BYTES:
            raise ValueError("byte bound")
        key = (stat.st_mtime_ns, stat.st_size)
        with self.lock:
            cached = self.cache.get(path)
            if cached and cached[0] == key:
                return cached[1:]
            raw = path.read_bytes()
            if len(raw) > MAX_BYTES or path.stat().st_mtime_ns != stat.st_mtime_ns:
                raise ValueError("source changed")
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("object required")
            sha = hashlib.sha256(raw).hexdigest()
            if len(self.cache) >= 160:
                self.cache.clear()
            self.cache[path] = (key, data, sha)
            return data, sha

    def catalog(self):
        entries = {}
        for family, pattern in (("paper", "artifacts/market-paper/*/manifest.json"),
                                ("portfolio", "artifacts/portfolio-ai/*/manifest.json"),
                                ("historical", "artifacts/evaluation/*/manifest.json")):
            for path in sorted(self.root.glob(pattern), reverse=True)[:60]:
                if ident(path.parent.name):
                    entries[family + ":" + path.parent.name] = path
        return entries

    def meta(self, key, data, sha):
        kind = data.get("evidence_kind", data.get("source"))
        result = envelope("AVAILABLE")
        mode = "PAPER" if "PAPER" in (kind or "") else ("REPLAY" if "REPLAY" in (kind or "") else ("OFFLINE" if "SYNTHETIC" in (kind or "") else "HISTORICAL"))
        freshness = "PAPER" if "PAPER" in (kind or "") else "HISTORICAL"
        result.update(source="LOCAL_ARCHIVED_MANIFEST", evidence_kind=ident(kind), run_id=key,
                      revision=ident(data.get("revision")), sha256=sha,
                      observed_at=timestamp(data.get("created_at_utc", data.get("created_at"))),
                      warnings=["ARCHIVED_NOT_CURRENT_WORKER", "BINDINGS_NOT_REVALIDATED_AGAINST_CHECKOUT"],
                      gate=ident(data.get("primary_status", data.get("selection_status", data.get("status")))),
                      mode=mode, freshness=freshness,
                      bindings={k: digest(data.get("bindings", {}).get(k)) for k in
                                ("code_sha256", "data_sha256", "config_sha256", "prompt_sha256")},
                      protocol_sha256=digest(data.get("protocol_sha256")))
        if not result["evidence_kind"]:
            raise ValueError("missing evidence kind")
        return result

    def runs(self):
        rows = []
        for key, path in self.catalog().items():
            try:
                data, sha = self.read(path)
                meta = self.meta(key, data, sha)
                if key.startswith("portfolio:") or key.startswith("paper:"):
                    datasets = ["bound-dataset"]
                else:
                    datasets = [name for name in data.get("results", {}) if ident(name)]
                meta.update(datasets=datasets)
                rows.append(meta)
            except (OSError, ValueError, TypeError, AttributeError):
                rows.append(dict(envelope("INVALID"), run_id=key,
                                 warnings=["MANIFEST_SCHEMA_OR_READ_FAILED"], datasets=[]))
        return dict(envelope("AVAILABLE" if rows else "EMPTY"), items=rows)

    def selected(self, run, dataset):
        if not ident(run) or run not in self.catalog():
            raise KeyError("unknown run")
        data, sha = self.read(self.catalog()[run])
        meta = self.meta(run, data, sha)
        if run.startswith("portfolio:") or run.startswith("paper:"):
            if dataset != "bound-dataset":
                raise KeyError("unknown dataset")
            arms = data.get("arms", {})
            acceptance = dict(sha256=meta["bindings"]["data_sha256"], start=None, end=None)
        else:
            if not ident(dataset) or dataset not in data.get("results", {}):
                raise KeyError("unknown dataset")
            source = data["results"][dataset]
            arms = source.get("scorecard", {})
            a = source.get("acceptance", {})
            acceptance = dict(sha256=digest(a.get("sha256")), start=timestamp(a.get("start")),
                              end=timestamp(a.get("end")), purpose=ident(a.get("purpose")))
        if not isinstance(arms, dict) or len(arms) > 12 or any(not ident(k) for k in arms):
            raise ValueError("invalid arms")
        return meta, arms, acceptance

    def evaluation(self, run, dataset):
        meta, arms, acceptance = self.selected(run, dataset)
        output = []
        signatures = []
        for name, arm in arms.items():
            row = dict(name=name, symbol=ident(arm.get("symbol")), evidence_kind=ident(arm.get("evidence_kind")),
                       metrics={k: decimal(arm.get(k)) for k in METRICS},
                       counts={k: count(arm.get(k)) for k in COUNTS}, curve=[],
                       execution_model=text(arm.get("execution_model")),
                       benchmark_contract=text(arm.get("benchmark_contract")),
                       pnl_contract=text(arm.get("pnl_contract")), drawdown_basis=text(arm.get("drawdown_basis")),
                       latest_balances=None, peak_equity_tmn=None, latest_unrealized_pnl_tmn=None)
            peak = None
            for point in bounded_list(arm.get("equity_curve")):
                equity = decimal(point.get("net_equity_tmn"), negative=False)
                if equity is None:
                    raise ValueError("missing curve equity")
                with localcontext() as ctx:
                    ctx.prec = 80
                    number = Decimal(equity)
                    peak = max(peak, number) if peak is not None else number
                    dd = str((peak - number) / peak * 100) if peak else None
                row["curve"].append(dict(observed_at=timestamp(point.get("timestamp")), equity_tmn=equity,
                                         drawdown_pct=dd, realized_pnl_tmn=decimal(point.get("realized_pnl_tmn")),
                                         unrealized_pnl_tmn=decimal(point.get("unrealized_pnl_tmn"))))
            if row["curve"]:
                row["peak_equity_tmn"] = str(peak)
                row["latest_unrealized_pnl_tmn"] = row["curve"][-1]["unrealized_pnl_tmn"]
                balances = arm["equity_curve"][-1].get("balances")
                if isinstance(balances, dict):
                    row["latest_balances"] = project_balances(balances)
            signatures.append((arm.get("benchmark_contract"), arm.get("initial_capital_tmn"),
                               arm.get("execution_model"), arm.get("drawdown_basis"),
                               tuple(p["observed_at"] for p in row["curve"])))
            output.append(row)
        comparable = bool(signatures and signatures[0][0] and signatures[0][-1]
                          and all(s == signatures[0] for s in signatures))
        meta.update(dataset=dataset, acceptance=acceptance, arms=output, comparable=comparable,
                    units=dict(money="TMN", base="asset symbol in balances", drawdown="percent"),
                    risk=dict(status="UNAVAILABLE", stop_policy=None, kill_switch=None,
                              warning="Thresholds not attested by this artifact; not a loss guarantee"))
        meta["record_linking"] = "REAL_IDS_ONLY_NO_TIMESTAMP_JOIN"
        if not comparable:
            meta["warnings"].append("COMPARABILITY_UNVERIFIED_SINGLE_ARM_ONLY")
        if "SYNTHETIC" in meta["evidence_kind"] or any("FAKE" in (r["evidence_kind"] or "") for r in output):
            meta["warnings"].append("SYNTHETIC_OR_FAKE_NOT_PROFITABILITY_EVIDENCE")
        return meta

    def rows(self, run, dataset, arm_name, section, offset=0, limit=25, action="ALL"):
        meta, arms, _ = self.selected(run, dataset)
        if arm_name not in arms:
            raise KeyError("unknown arm")
        arm = arms[arm_name]
        rows = []
        orders = bounded_list(arm.get("orders"))
        fills = bounded_list(arm.get("fills"))
        # Only committed own-ledger manifest fills; audit FILL is deliberately excluded.
        unique_fills = {}
        for fill in fills:
            fid = ident(fill.get("fill_id"))
            if not fid:
                raise ValueError("missing fill identity")
            if fid in unique_fills and unique_fills[fid] != fill:
                raise ValueError("conflicting fill identity")
            unique_fills[fid] = fill
        safe_fills = [dict(fill_id=fid, client_id=ident(f.get("client_id")), price=decimal(f.get("price"), False),
                           quantity=decimal(f.get("quantity"), False), fee=decimal(f.get("fee"), False),
                           fee_asset=ident(f.get("fee_asset")), observed_at=timestamp(f.get("timestamp")))
                      for fid, f in unique_fills.items()]
        safe_orders = [dict(client_id=ident(o.get("client_id")), symbol=ident(arm.get("symbol")),
                            side=ident(o.get("side")), state=ident(o.get("status")),
                            price=decimal(o.get("price"), False), quantity=decimal(o.get("quantity"), False),
                            fills=[f for f in safe_fills if f["client_id"] and f["client_id"] == o.get("client_id")],
                            reconciliation=None, locked=None, free=None)
                       for o in orders]
        if section == "orders":
            rows = safe_orders
            present = "orders" in arm
        else:
            present = "decision_traces" in arm
            seen = set()
            for trace in bounded_list(arm.get("decision_traces")):
                decision, snapshot, risk = trace.get("decision", {}), trace.get("snapshot", {}), trace.get("risk", {})
                did = ident(decision.get("decision_id"))
                snap_hash = digest(trace.get("snapshot_sha256"))
                if not did or did in seen:
                    continue
                seen.add(did)
                if action != "ALL" and decision.get("action") != action:
                    continue
                client_id = ident(trace.get("client_id"))
                computed = hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                binding = bool(snap_hash and snap_hash == computed == decision.get("snapshot_sha256")
                               and snapshot.get("symbol") == decision.get("symbol")
                               and snapshot.get("cutoff") == decision.get("cutoff"))
                row_item = dict(decision_id=did, symbol=ident(decision.get("symbol")),
                                 action=ident(decision.get("action")), reason=text(decision.get("reason")),
                                 observed_at=timestamp(decision.get("cutoff")), snapshot_sha256=snap_hash,
                                 evidence_ids=[ident(v) for v in bounded_list(decision.get("evidence_ids"))][:25],
                                 features={k: decimal(snapshot.get(k), False) for k in FEATURES},
                                 feature_binding="HASH_VERIFIED" if binding else "UNVERIFIED",
                                 risk=dict(approved=risk.get("approved") if type(risk.get("approved")) is bool else None,
                                           reason=text(risk.get("reason")), action=ident(risk.get("action")),
                                           stop_price=decimal(risk.get("stop_price"), False)),
                                 client_id=client_id, orders=[o for o in safe_orders if client_id and o["client_id"] == client_id])
                if isinstance(decision.get("forecast"), dict):
                    fc = decision["forecast"]
                    row_item["forecast"] = dict(
                        reference_price=decimal(str(fc.get("reference_price")), False),
                        return_q10=decimal(str(fc.get("return_q10"))),
                        return_q50=decimal(str(fc.get("return_q50"))),
                        return_q90=decimal(str(fc.get("return_q90"))),
                        target_return_fraction=decimal(str(fc.get("target_return_fraction")), False) if fc.get("target_return_fraction") else None,
                        horizon_seconds=count(fc.get("horizon_seconds")),
                        review_after_seconds=count(fc.get("review_after_seconds")),
                        invalidation=text(fc.get("invalidation")),
                        label="پیش‌بینی",
                    )
                if isinstance(trace.get("protection"), dict):
                    prot = trace["protection"]
                    hw = prot.get("high_water")
                    np = prot.get("net_peak_tmn", prot.get("net_peak"))
                    rf = prot.get("retained_floor_tmn")
                    tsp = prot.get("trailing_stop_price")
                    row_item["protection"] = dict(
                        high_water=decimal(str(hw), False) if hw is not None else None,
                        net_peak_tmn=decimal(str(np), False) if np is not None else None,
                        retained_floor_tmn=decimal(str(rf), False) if rf is not None else None,
                        retention_active=bool(prot.get("retention_active", False)),
                        trailing_stop_price=decimal(str(tsp), False) if tsp is not None else None,
                        last_tightened_at=timestamp(prot.get("last_tightened_at")),
                        target_checkpoint_price=decimal(str(prot.get("target_checkpoint_price")), False) if prot.get("target_checkpoint_price") is not None else None,
                        gross_return_pct=decimal(str(prot.get("gross_return_pct"))) if prot.get("gross_return_pct") is not None else None,
                        net_return_pct=decimal(str(prot.get("net_return_pct"))) if prot.get("net_return_pct") is not None else None,
                    )
                rows.append(row_item)
        if any(o["state"] == "UNKNOWN" for o in safe_orders):
            meta["warnings"].append("UNKNOWN_ORDER_REQUIRES_ENGINE_RECONCILIATION")
        meta.update(status="AVAILABLE" if rows else ("EMPTY" if present else "UNAVAILABLE"),
                    items=rows[offset:offset + limit], total=len(rows), offset=offset, limit=limit,
                    next_offset=offset + limit if offset + limit < len(rows) else None,
                    units=dict(price="TMN for USDTTMN", quantity="USDT for USDTTMN", fee="fee_asset"))
        return meta

    def overview(self):
        observation = envelope()
        observation.update(mode="UNKNOWN", worker="UNKNOWN", heartbeat=None, events=[], errors=[])
        paths = sorted(self.root.glob("data/shadow/*/shadow_manifest.json"), reverse=True)[:1]
        if paths:
            try:
                data, sha = self.read(paths[0])
                if data.get("mode") != "OBSERVE_ONLY" or data.get("evidence_kind") != "PUBLIC_FEED_DIAGNOSTIC":
                    raise ValueError("unknown observation schema")
                beats = bounded_list(data.get("heartbeats"))
                beat = beats[-1] if beats else {}
                captures = bounded_list(data.get("captures"))
                capture = captures[-1] if captures else {}
                observed = timestamp(beat.get("observed_at_utc"))
                age = (datetime.now(UTC) - datetime.fromisoformat(observed)).total_seconds() if observed else None
                interval = data.get("interval_seconds")
                if type(interval) is not int or not 1 <= interval <= 86400:
                    raise ValueError("interval")
                audit = (paths[0].parent / "audit/audit_trail.jsonl").resolve()
                if not audit.is_relative_to(self.root):
                    raise ValueError("source outside root")
                events, warnings = public_tail(audit)
                state = "UNAVAILABLE" if not observed else ("STALE" if age > 2 * interval else "AVAILABLE")
                if age is not None and age < -60:
                    state = "INVALID"
                observation.update(status=state, source="ARCHIVED_PUBLIC_OBSERVATION", sha256=sha,
                                   run_id=ident(data.get("run_id")), revision=ident(data.get("revision")),
                                   evidence_kind="PUBLIC_FEED_DIAGNOSTIC", mode="OBSERVE_ONLY",
                                   observed_at=observed, received_at=timestamp(capture.get("received_at_utc")),
                                   market_cutoff_at=timestamp(beat.get("cutoff")),
                                   heartbeat=observed, worker="UNKNOWN", recorded_status=ident(data.get("status")),
                                   events=events, warnings=[*warnings, "SAVED_DATA_NOT_WORKER_LIVENESS"],
                                   freshness_seconds=int(age) if age is not None else None,
                                   display_stale_after_seconds=2 * interval)
                observation["errors"] = [dict(error_type=ident(e.get("error_type")), attempt=count(e.get("attempt")))
                                         for e in bounded_list(data.get("errors"))[:100]]
            except (OSError, ValueError, TypeError, AttributeError):
                observation.update(status="INVALID", warnings=["OBSERVATION_SCHEMA_OR_READ_FAILED"])
        account = envelope()
        probe_path = self.root / "data/private/probe-report.json"
        engine_path = self.root / ".local/dashboard/engine-snapshot.json"
        engine_snapshot = envelope()

        if probe_path.is_file():
            try:
                p_data, p_sha = self.read(probe_path)
                tmn = p_data.get("tmn_balance", {})
                usdt = p_data.get("usdt_balance", {})
                tmn_free = decimal(str(tmn.get("available")), negative=False)
                tmn_locked = decimal(str(tmn.get("locked")), negative=False)
                usdt_free = decimal(str(usdt.get("available")), negative=False)
                usdt_locked = decimal(str(usdt.get("locked")), negative=False)
                total_tmn = decimal(str(tmn.get("total")), negative=False)
                account.update(
                    status="AVAILABLE",
                    source="READ_ONLY_PROBE_SNAPSHOT",
                    evidence_kind="READ_ONLY_CREDIT_ACCOUNT_AND_MARKET_CONTRACT",
                    sha256=p_sha,
                    subaccount_type=ident(p_data.get("subaccount_type")),
                    subaccount_active=bool(p_data.get("subaccount_active")),
                    balances={
                        "TMN": {"free": tmn_free, "locked": tmn_locked, "total": total_tmn},
                        "USDT": {"free": usdt_free, "locked": usdt_locked, "total": decimal(str(usdt.get("total")), negative=False)},
                    },
                    equity_tmn=total_tmn,
                    reconciliation="ATTESTED_READONLY_PROBE",
                    warnings=["READONLY_PROBE_SNAPSHOT_NOT_STREAMING_SOCKET"],
                )
            except (OSError, ValueError, TypeError, AttributeError):
                account.update(status="INVALID", warnings=["PROBE_REPORT_SCHEMA_INVALID"])

        if engine_path.is_file():
            try:
                e_data, e_sha = self.read(engine_path)
                acc = e_data.get("account", {})
                balances = project_balances(acc.get("balances"), totals=True)
                if "TMN" not in balances:
                    raise ValueError("Engine cash balance is missing")
                total_tmn = balances["TMN"]["total"]
                equity = decimal(acc.get("equity_tmn"), negative=False)
                if equity is None:
                    if any(Decimal(value["total"]) for asset,value in balances.items() if asset != "TMN"):
                        raise ValueError("Noncash engine assets need an observed valuation")
                    equity = total_tmn
                engine_snapshot.update(
                    status="AVAILABLE",
                    source=ident(e_data.get("source")) or "PAPER_ENGINE_SNAPSHOT",
                    evidence_kind=ident(e_data.get("evidence_kind")) or "PUBLIC_MARKET_PAPER",
                    sha256=e_sha,
                    run_id=ident(e_data.get("run_id")),
                    mode=ident(e_data.get("mode")),
                    worker_state=ident(e_data.get("worker_state")),
                    observed_at=timestamp(e_data.get("observed_at")),
                    heartbeat_at=timestamp(e_data.get("heartbeat_at")),
                    balances=balances,
                    equity_tmn=equity,
                    risk=e_data.get("risk"),
                    warnings=bounded_list(e_data.get("warnings")),
                )
                if not probe_path.is_file():
                    account.update(
                        status="AVAILABLE",
                        source=ident(e_data.get("source")) or "PAPER_ENGINE_SNAPSHOT",
                        evidence_kind=ident(e_data.get("evidence_kind")) or "PUBLIC_MARKET_PAPER",
                        sha256=e_sha,
                        balances=engine_snapshot["balances"],
                        equity_tmn=equity,
                        reconciliation="PAPER_INTERNAL_LEDGER",
                        warnings=engine_snapshot["warnings"],
                    )
                if e_data.get("heartbeat_at"):
                    observation.update(
                        mode=ident(e_data.get("mode")) or "PUBLIC_MARKET_PAPER",
                        heartbeat=timestamp(e_data.get("heartbeat_at")),
                        observed_at=timestamp(e_data.get("observed_at")),
                        status="AVAILABLE",
                    )
            except (OSError, ValueError, TypeError, AttributeError):
                engine_snapshot.update(status="INVALID", warnings=["ENGINE_SNAPSHOT_INVALID"])
        elif not probe_path.is_file():
            account.update(warnings=["WAITING_FOR_ENGINE_EXCHANGE_ATTESTED_EXPORT"], balances=None,
                           equity_tmn=None, reconciliation=None, free=None, locked=None)
        usage = readonly_budget(self.root / "data/llm-budget.sqlite3")
        reflections = readonly_reflections(self.root / "data/ledger.sqlite3")
        review = envelope()
        try:
            data, sha = self.read(self.root / "research/execution-review-evidence.json")
            review.update(status="AVAILABLE", source="ARCHIVED_EXECUTION_REVIEW",
                          evidence_kind="ARCHIVED_SDK_REPORTED_USAGE", sha256=sha,
                          revision=ident(data.get("reviewed_delivery_revision")),
                          input_tokens=count(data.get("sdk_reported_input_tokens")),
                          output_tokens=count(data.get("sdk_reported_output_tokens")),
                          invoice=None, warnings=["ARCHIVED_SDK_USAGE_NOT_CURRENT_GLOBAL_USAGE_OR_INVOICE"])
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        diagnostic = envelope()
        reports = sorted(self.root.glob("artifacts/ai-evaluation/*/ai_evaluation_report.json"), reverse=True)[:1]
        if reports:
            try:
                data, sha = self.read(reports[0])
                latency = data.get("average_latency_seconds")
                diagnostic.update(status="AVAILABLE", source="ARCHIVED_AI_DIAGNOSTIC",
                                  evidence_kind="REAL_MODEL_SNAPSHOTS_NOT_PORTFOLIO_REPLAY",
                                  run_id=ident(data.get("run_id")), sha256=sha,
                                  observed_at=timestamp(data.get("evaluated_at_utc")),
                                  model=ident(data.get("model")), provider=ident(data.get("provider")),
                                  decisions=count(data.get("total_ai_decisions")),
                                  average_latency_seconds=decimal(str(latency)) if latency is not None else None,
                                  errors=None, timeouts=None, warnings=["AGREEMENT_NOT_AI_ECONOMIC_VALUE"])
            except (OSError, ValueError, TypeError, AttributeError):
                diagnostic.update(status="INVALID")
        result = envelope("AVAILABLE")
        result.update(server="SERVER_AVAILABLE", server_time=datetime.now(UTC).isoformat(),
                      observation=observation, account=account, engine_snapshot=engine_snapshot,
                      reservation=usage, archived_usage=review, model=diagnostic, reflections=reflections,
                      risk=dict(status="UNAVAILABLE", stop=None, kill_switch=None),
                      warnings=["CANDIDATE_APPROVAL_NOT_ATTESTED", "DASHBOARD_IS_READ_ONLY"])
        return result
