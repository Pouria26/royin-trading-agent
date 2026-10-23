"""One durable shadow engine and a redacted health endpoint; no private order transport."""

import argparse
import asyncio
import hashlib
import json
import os
import signal
import sqlite3
import threading
import time
from contextlib import closing, contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from royin.config import load_config
from royin.model_budget import ModelBudget
from royin.service_contract import ServiceContract
from scripts.run_market_paper import MarketPaperOrchestrator


def atomic_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, default=str), encoding="utf-8")
    os.replace(temporary, path)


@contextmanager
def owner_lock(root):
    """Acquire before constructing an engine, including its initialization writes."""
    with closing(sqlite3.connect(root / "service-owner.sqlite3", timeout=0)) as db:
        db.execute("BEGIN EXCLUSIVE")
        yield


def service_paths(root, contract):
    root = root.resolve(strict=True)
    marker = root / ".royin-volume-id"
    if (
        not root.is_dir()
        or not marker.is_file()
        or not 16 <= len(marker.read_text().strip()) <= 128
    ):
        raise ValueError("Provisioned persistent volume marker required")
    run = root / "missions" / contract.service_id
    return run, run / "paper.sqlite3", run / "prepared.json"


def engine_for(contract, config, run, db_path):
    return MarketPaperOrchestrator(
        run_id=contract.service_id,
        model_mode="REAL_MODEL",
        duration_seconds=contract.duration_seconds,
        cycles=contract.cycles,
        interval_seconds=contract.poll_seconds,
        public_get_cap=contract.max_public_gets,
        horizon_max_seconds=contract.horizon_max_seconds,
        order_tmn=contract.max_debit_tmn,
        minimum_notional_tmn=contract.minimum_notional_tmn,
        capture_dir=run,
        db_path=db_path,
        config=config,
        service_contract=contract,
    )


def prepare(root, contract, config):
    run, db_path, prepared = service_paths(root, contract)
    with owner_lock(root):
        if run.exists():
            raise ValueError("Existing mission cannot be initialized again")
        # Missing original state must block before creating a new paper mission.
        ModelBudget(config, require_existing=True)
        engine = engine_for(contract, config, run, db_path)
        try:
            engine.ledger.set_meta("service_state", "PREPARED")
            engine.ledger.set_meta("service_contract_sha256", contract.sha256)
            engine._checkpoint_and_export(int(time.time()))
            record = dict(
                schema_version=1,
                contract_sha256=contract.sha256,
                source_sha256=engine.code_sha256,
                config_sha256=hashlib.sha256(config.model_dump_json().encode()).hexdigest(),
                service_id=contract.service_id,
                prepared_at=int(time.time()),
            )
            with prepared.open("x", encoding="utf-8") as stream:
                json.dump(record, stream, sort_keys=True)
        finally:
            engine.close()
    return record


def read_health(db_path, service_id, *, now=None):
    now = int(time.time()) if now is None else now
    result = dict(
        service_id=service_id,
        mode="SHADOW",
        live_trading=False,
        status="STATE_UNAVAILABLE",
        ready=False,
    )
    try:
        with closing(
            sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)
        ) as db:
            values = dict(
                db.execute(
                    "SELECT key,value FROM metadata WHERE key IN "
                    "('engine_heartbeat','engine_lifecycle','service_state','entry_block_reason','engine_completed_cycles')"
                )
            )
        state = values.get("service_state", "PREPARED")
        age = now - int(values.get("engine_heartbeat", "0"))
        terminal = state in ("COMPLETED_FLAT", "DEADLINE_OPEN", "STOPPED_BY_OPERATOR")
        result.update(
            status=state,
            heartbeat_age_seconds=age,
            completed_cycles=int(values.get("engine_completed_cycles", "0")),
            entry_block_reason=values.get("entry_block_reason"),
            ready=state == "RUNNING"
            and 0 <= age <= 300
            and values.get("entry_block_reason")
            not in ("BUDGET_EXHAUSTED", "MODEL_STATE_BLOCKED_PROTECTION_ONLY"),
            alive=terminal or (state == "RUNNING" and 0 <= age <= 300),
        )
    except (sqlite3.Error, ValueError, OSError, TypeError):
        result["alive"] = False
    return result


def health_server(db_path, service_id, port):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path not in ("/healthz", "/readyz"):
                self.send_error(404)
                return
            body = read_health(db_path, service_id)
            healthy = body.get("alive") if self.path == "/healthz" else body.get("ready")
            raw = json.dumps(body).encode()
            self.send_response(200 if healthy else 503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


async def run(root, contract, config, *, port=3000, park=True):
    run_dir, db_path, prepared = service_paths(root, contract)
    if not db_path.is_file() or not prepared.is_file():
        raise ValueError("Original prepared mission state missing; no automatic bootstrap")
    with owner_lock(root):
        with closing(sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='live_broker_orders'").fetchone():
                raise ValueError("Financial broker state cannot be opened as a shadow mission")
        expected = json.loads(prepared.read_text(encoding="utf-8"))
        if expected.get("contract_sha256") != contract.sha256:
            raise ValueError("Prepared contract changed")
        if (
            expected.get("config_sha256")
            != hashlib.sha256(config.model_dump_json().encode()).hexdigest()
        ):
            raise ValueError("Prepared runtime config changed")
        engine = engine_for(contract, config, run_dir, db_path)
        server = None
        stopped = False
        old_handlers = {}

        def stop(*_):
            nonlocal stopped
            stopped = True
            engine.request_shutdown()

        try:
            if engine.code_sha256 != expected.get("source_sha256"):
                raise ValueError("Prepared source changed")
            if engine.ledger.get_meta("service_contract_sha256") != contract.sha256:
                raise ValueError("Durable service contract missing or changed")
            server = health_server(db_path, contract.service_id, port)
            for sig in (signal.SIGINT, signal.SIGTERM):
                old_handlers[sig] = signal.signal(sig, stop)

            async def operator_stop():
                while not stopped and int(time.time()) < int(contract.effective_end_at.timestamp()):
                    if (run_dir / "STOP_REQUESTED").exists():
                        stop()
                        return
                    await asyncio.sleep(0.5)

            state = engine.ledger.get_meta("service_state")
            if state not in ("COMPLETED_FLAT", "DEADLINE_OPEN", "STOPPED_BY_OPERATOR"):
                # The paper broker has no remote fills: cancel only its own unfinished simulated intents.
                # Real financial UNKNOWN state is never opened or modified by this shadow service.
                with engine.ledger.worker():
                    for cid, order in list(engine.broker.orders.items()):
                        if order.status in (
                            "INTENT",
                            "SUBMITTING",
                            "UNKNOWN",
                            "OPEN",
                            "PARTIALLY_FILLED",
                        ):
                            engine.broker.reconcile_order(
                                cid, simulated_state="CANCELED", timestamp=int(time.time())
                            )
                engine.ledger.set_meta("service_state", "RUNNING")
                if engine.model_startup_blocked:
                    engine.ledger.set_meta(
                        "entry_block_reason", "MODEL_STATE_BLOCKED_PROTECTION_ONLY"
                    )
                watcher = asyncio.create_task(operator_stop())
                try:
                    await engine.run()
                finally:
                    watcher.cancel()
                    await asyncio.gather(watcher, return_exceptions=True)
                if stopped:
                    state = (
                        "STOPPED_BY_OPERATOR"
                        if (run_dir / "STOP_REQUESTED").exists()
                        else "PAUSED_RESTART"
                    )
                else:
                    state = "FINALIZING"
                engine.ledger.set_meta("service_state", state)
                # Only fresh public quotes are retried; no exchange mutation exists in this service.
                while (
                    state == "FINALIZING"
                    and engine.ledger.get_balance(engine.rules.base_asset).total
                ):
                    if int(time.time()) >= int(contract.effective_end_at.timestamp()):
                        break
                    await asyncio.sleep(contract.poll_seconds)
                    with engine.ledger.worker():
                        engine._finish_current(engine.public_feed)
                        engine._checkpoint_and_export(int(time.time()))
                    if stopped:
                        break
                if state == "FINALIZING":
                    state = (
                        "DEADLINE_OPEN"
                        if engine.ledger.get_balance(engine.rules.base_asset).total
                        else "COMPLETED_FLAT"
                    )
                    engine.ledger.set_meta("service_state", state)
                atomic_json(
                    run_dir / "service-result.json",
                    dict(
                        status=state,
                        stopped_at=int(time.time()),
                        evidence_kind="SHADOW_ONLY",
                        summary=engine.generate_summary(),
                        live_orders=0,
                    ),
                )
            # Keep a completed mission observable; never initialize a new run on process restart.
            while (
                park
                and not stopped
                and int(time.time()) < int(contract.effective_end_at.timestamp()) + 3600
            ):
                await asyncio.sleep(0.5)
            return state
        finally:
            for sig, previous in old_handlers.items():
                signal.signal(sig, previous)
            if server:
                server.shutdown()
                server.server_close()
            engine.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--port", type=int, default=3000)
    parser.add_argument("--require-mount", action="store_true")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--prepare", action="store_true")
    action.add_argument("--run", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not 1 <= args.port <= 65535:
            raise ValueError("Invalid port")
        if args.require_mount and not os.path.ismount(args.state_root):
            raise ValueError("Persistent state root is not a mounted volume")
        contract = ServiceContract.model_validate_json(args.policy.read_bytes())
        config = load_config(args.env_file)
        if config.RUN_MODE != "shadow" or config.ENABLE_LIVE_TRADING:
            raise ValueError("This service has no live exchange transport")
        if args.prepare:
            prepare(args.state_root, contract, config)
            print(json.dumps(dict(status="PREPARED_SHADOW_ONLY", model_http=0, live_orders=0)))
        else:
            status = asyncio.run(run(args.state_root, contract, config, port=args.port))
            print(json.dumps(dict(status=status, live_orders=0)))
        return 0
    except (ValueError, OSError, RuntimeError, sqlite3.Error, KeyError, TypeError) as exc:
        print(
            json.dumps(dict(status="BLOCKED_SERVICE", error_type=type(exc).__name__, live_orders=0))
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
