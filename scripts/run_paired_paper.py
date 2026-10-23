"""Prospective entry-policy comparison on shared public inputs and paper execution.

One owner; no private exchange API. Position exits are host-only in this experiment,
so differences isolate entry selection rather than a second, changing reviewer policy.
"""

import argparse
import asyncio
import hashlib
import json
import re
import shutil
import signal
import sqlite3
import subprocess
import time
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from royin.agent import decide_role
from royin.config import RuntimeConfig
from royin.decision import Decision
from royin.evaluation import source_bundle_sha256
from royin.market_context import catalog_return
from royin.model_budget import BudgetBlocked
from royin.model_profiles import PROVIDER_MODELS, PROVIDER_ORIGINS
from scripts.replay_market_paper import replay_accounting
from scripts.run_market_paper import (
    MarketPaperOrchestrator,
    fee_aware_entry,
    public_symbols,
)
from scripts.run_paper_trader import (
    ScannerPublicFeed,
    catalog_candidates,
    quant_candidate_score,
    scan_current_market,
)

ROOT = Path(__file__).resolve().parents[1]
HORIZON = 1800
CAPITAL = Decimal(5000000)
DEBIT = Decimal(150000)
FLOOR = Decimal(100000)


def fingerprint(root=ROOT):
    return source_bundle_sha256(
        root,
        [
            *root.glob("src/royin/*.py"),
            *root.glob("scripts/*.py"),
            root / "requirements.lock",
            root / "config/llm-budget-policy.json",
            root / "config/wallex-credit-market-policy.json",
        ],
    )


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")
    temporary.replace(path)


def account_batch(batch, cash):
    """Only portfolio cash changes; market features retain their common causal cutoff."""
    result = {}
    for symbol, (snapshot, opportunity) in batch.items():
        if snapshot.current_position_base != 0 or not snapshot.verify_hash():
            raise ValueError("Entry comparison requires verified flat snapshots")
        candidate = replace(snapshot, available_tmn_cash=cash)
        digest = hashlib.sha256(
            json.dumps(
                candidate.to_canonical_dict(), sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        result[symbol] = (replace(candidate, snapshot_sha256=digest), opportunity)
    return result


def baseline_decision(kind, batch, *, entered=False, horizon_seconds=HORIZON):
    rows = list(batch.values())
    chosen = None
    if kind == "hold" and not entered:
        chosen = rows[0]
    elif kind == "rule":
        chosen = next((row for row in rows if fee_aware_entry(row[0], hold_seconds=horizon_seconds)), None)
    elif kind not in ("hold", "rule"):
        raise ValueError("Unknown predeclared baseline")
    snap = (chosen or rows[0])[0]
    return Decision(
        decision_id=f"{kind}_{snap.cutoff}",
        symbol=snap.symbol,
        action="ENTER" if chosen else "WAIT",
        cutoff=snap.cutoff,
        snapshot_sha256=snap.snapshot_sha256,
        evidence_ids=tuple(snap.evidences)[:3],
        reason=(
            "Host baseline: first eligible candidate, shared risk, one entry"
            if kind == "hold"
            else "Host baseline: existing fee-aware trend rule"
        ),
        invalidation="Next closed candle",
    )


class SharedBooks:
    """All counterfactual arms using a symbol share the exact same fresh book bytes."""

    def __init__(self, feed):
        self.feed, self.books, self.failures = feed, {}, {}

    def get(self, endpoint, params, *, cutoff, max_age_seconds=0):
        if endpoint != "/v1/depth" or set(params) != {"symbol"} or max_age_seconds != 0:
            raise ValueError("Execution stage accepts only a fresh public depth request")
        symbol = params["symbol"]
        if symbol in self.failures:
            raise ValueError("Shared execution book was unavailable")
        if symbol not in self.books:
            try:
                self.books[symbol] = self.feed.get(
                    endpoint, params, cutoff=cutoff, max_age_seconds=0
                )
            except (ValueError, OSError, RuntimeError):
                self.failures[symbol] = True
                raise
        payload, received = self.books[symbol]
        if not 0 <= int(time.time()) - received <= 60:
            raise ValueError("Shared execution book expired")
        # A caller cannot mutate the book seen by another arm.
        return deepcopy(payload), received


async def protect(arms, feed):
    quotes = SharedBooks(feed)
    for arm in arms.values():
        quantity = arm.ledger.get_balance(arm.rules.base_asset).total
        state = json.loads(arm.ledger.get_meta("protection_" + arm.rules.symbol) or "null")
        if quantity and state and state.get("status") == "OPEN":
            await arm._handle_position_cycle(quotes, int(time.time()), state, allow_model=False)
        elif quantity:
            arm.ledger.set_meta("entry_block_reason", "UNPROTECTED_OR_RESIDUAL_INVENTORY")
            arm.shutdown_requested = True


def collect_batch(feed):
    now = int(time.time())
    payload, received, symbols = public_symbols(feed, cutoff=now)
    candidates = catalog_candidates(
        payload,
        account_symbols=symbols,
        cutoff=int(time.time()),
        received_at=received,
        account_as_of=received,
        tmn_only=True,
    )
    rows = {row["symbol"]: row for row in payload["result"]["markets"]}
    btc, cash = catalog_return(rows.get("BTCTMN", {})), catalog_return(rows.get("USDTTMN", {}))
    ranked = sorted(
        candidates,
        key=lambda row: (
            -quant_candidate_score(row, rows, btc, cash),
            -row.turnover_tmn,
            row.symbol,
        ),
    )
    selected = [row.symbol for row in ranked[:5]]
    if not selected:
        return dict(batch=(), status="NO_ELIGIBLE_CATALOG", rejections=[], coverage={})
    previous = feed.deadline_monotonic
    feed.deadline_monotonic = time.monotonic() + 45
    try:
        return scan_current_market(
            feed,
            account_symbols=symbols,
            account_as_of=received,
            interval_seconds=300,
            round_trip_fee_pct=Decimal(".006"),
            min_depth_tmn=Decimal(1000000),
            max_spread_pct=Decimal(".005"),
            available_tmn_cash=CAPITAL,
            batch_limit=5,
            selected_symbols=selected,
            diversify=True,
            tmn_only=True,
            use_spot_rules=True,
        )
    finally:
        feed.deadline_monotonic = previous


async def entry_round(arms, feed, report, output, round_id, *, should_stop=None):
    batch = {
        item.snapshot.symbol: (item.snapshot, item.opportunity) for item in report.get("batch", ())
    }
    if not batch:
        write_json(
            output / f"round-{round_id}.json",
            dict(
                status=report.get("status"),
                rejections=report.get("rejections", []),
                errors=report.get("errors", []),
                model_http=0,
            ),
        )
        return
    eligible = {
        name: arm
        for name, arm in arms.items()
        if not arm.shutdown_requested and not arm.ledger.get_balance(arm.rules.base_asset).total
    }
    inputs = {
        name: account_batch(batch, arm.ledger.get_balance("TMN").free)
        for name, arm in eligible.items()
    }
    tasks, decisions, traces = {}, {}, {}
    for name, arm in eligible.items():
        if name in ("rule", "hold"):
            decisions[name] = baseline_decision(
                name, inputs[name], entered=arm.ledger.get_meta("baseline_entered") == "true",
                horizon_seconds=arm.horizon_max_seconds,
            )
            traces[name] = {}
        else:
            traces[name] = {}
            tasks[name] = asyncio.create_task(
                decide_role(
                    market_batch=inputs[name],
                    config=arm.config,
                    budget=arm.budget,
                    run_envelope=arm.run_envelope,
                    model_trace=traces[name],
                    allowed_symbols=tuple(batch),
                    horizon_bounds=(arm.horizon_max_seconds, arm.horizon_max_seconds),
                    remaining_seconds=arm.protection_policy.deadline_utc
                    - arm.protection_policy.exit_buffer_seconds
                    - int(time.time()),
                    timeout_seconds=30,
                )
            )
    try:
        pending = set(tasks.values())
        while pending:
            _, pending = await asyncio.wait(pending, timeout=3)
            if pending:
                await protect(arms, feed)
        for name, task in tasks.items():
            try:
                decisions[name] = task.result()
            except BudgetBlocked:
                snap = next(iter(inputs[name].values()))[0]
                decisions[name] = Decision(
                    decision_id=f"budget_{name}_{snap.cutoff}",
                    symbol=snap.symbol,
                    action="WAIT",
                    cutoff=snap.cutoff,
                    snapshot_sha256=snap.snapshot_sha256,
                    evidence_ids=("EV_DATA_FRESH",),
                    reason="Original durable model budget blocked entry",
                    invalidation="Review original budget without resetting reservations",
                )
                traces[name].update(host_outcome="HOST_FALLBACK", budget_blocked=True)
                eligible[name].shutdown_requested = True
    finally:
        for task in tasks.values():
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks.values(), return_exceptions=True)
    if should_stop is not None and should_stop():
        write_json(
            output / f"round-{round_id}.json",
            dict(
                status="INTERRUPTED_BEFORE_ENTRY",
                decisions={name: d.model_dump(mode="json") for name, d in decisions.items()},
                orders=0,
            ),
        )
        return
    # All entries wait for the same model barrier and share the exact execution books.
    books = SharedBooks(feed)
    for name, decision in decisions.items():
        arm = eligible[name]
        await arm._apply_entry_decision(
            books,
            decision,
            inputs[name],
            primary_snap=next(iter(inputs[name].values()))[0],
            report=report,
            bootstrap_attempts=[],
            input_state=arm._replay_input_state(),
            model_trace=traces[name],
        )
        if name == "hold" and arm.ledger.get_balance(arm.rules.base_asset).total:
            arm.ledger.set_meta("baseline_entered", "true")
    write_json(
        output / f"round-{round_id}.json",
        dict(
            status="DECISION_ROUND",
            cutoff=next(iter(batch.values()))[0].cutoff,
            shared_symbols=list(batch),
            portfolio_cash={
                name: str(eligible[name].ledger.get_balance("TMN").free) for name in eligible
            },
            coverage=report.get("coverage"),
            rejections=report.get("rejections", []),
            decisions={name: d.model_dump(mode="json") for name, d in decisions.items()},
            execution_books={
                symbol: dict(
                    received_at=value[1],
                    sha256=hashlib.sha256(
                        json.dumps(value[0], sort_keys=True, default=str).encode()
                    ).hexdigest(),
                )
                for symbol, value in books.books.items()
            },
        ),
    )


def finalize_arms(arms, feed, output, errors):
    """One failed arm must not prevent independent host exits in the remaining arms."""
    quotes = SharedBooks(feed)
    results = {}
    residual = False
    for name, arm in arms.items():
        try:
            arm._finish_current(quotes)
            shutil.copytree(output / "raw", arm.capture_dir / "raw", dirs_exist_ok=True)
            arm._checkpoint_and_export(int(time.time()))
            manifest = json.loads((arm.capture_dir / "manifest.json").read_text(encoding="utf-8"))
            accounting, _ = replay_accounting(manifest)
            metrics = manifest["arms"]["paper_portfolio"]
            summary = arm.generate_summary()
            summary.update(
                accounting=accounting,
                metrics={
                    key: metrics.get(key)
                    for key in (
                        "max_drawdown_pct",
                        "peak_exposure_tmn",
                        "total_fees_paid_tmn",
                        "total_fees_paid_base",
                        "closed_round_trips",
                        "orders_submitted",
                        "fills_count",
                    )
                },
            )
            quote_fees = Decimal(metrics["total_fees_paid_tmn"])
            summary["fixed_trades_extra_25pct_quote_fee_pnl_tmn"] = (
                str(Decimal(accounting["realized_pnl_tmn"]) - quote_fees * Decimal(".25"))
                if Decimal(metrics["total_fees_paid_base"]) == 0
                else None
            )
            results[name] = summary
            residual = residual or bool(arm.ledger.get_balance(arm.rules.base_asset).total)
        except (
            ValueError,
            OSError,
            RuntimeError,
            KeyError,
            IndexError,
            TypeError,
            ArithmeticError,
            sqlite3.Error,
        ) as exc:
            errors.append(dict(phase="ARM_FINALIZATION", arm=name, error_type=type(exc).__name__))
            results[name] = dict(status="FINALIZATION_UNCONFIRMED", net_return_pct=None)
            residual = True
    return results, residual


async def run(args):
    horizon = getattr(args, "horizon_seconds", HORIZON)
    if horizon not in (1800, 3600, 7200) or args.duration_seconds < horizon+600:
        raise ValueError("Predeclared horizon must fit the bounded experiment")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,56}", args.run_id):
        raise ValueError("Bounded unique run ID required")
    output = args.output_dir / args.run_id
    if output.exists():
        raise ValueError("Run already exists; automatic restart/reset is prohibited")
    keys = json.loads(args.keys_file.read_text(encoding="utf-8"))
    configs = {}
    for provider, model in (("boxapi", "gpt-6-luna"), ("apmix", "claude-sonnet-4-6-free")):
        if model not in PROVIDER_MODELS[provider]:
            raise ValueError("Model not approved")
        configs[provider] = RuntimeConfig(
            RUN_MODE="shadow",
            LLM_PROVIDER=provider,
            LLM_MODEL=model,
            LLM_BASE_URL=PROVIDER_ORIGINS[provider],
            LLM_TOKEN_BUDGET=20000000,
            **(
                dict(LLM_COST_BUDGET="2.40", LLM_COST_CURRENCY="USD")
                if provider == "boxapi"
                else {}
            ),
            **{provider.upper() + "_API_KEY": keys[provider]["api_key"]},
        )
    # Preflight each original model ledger before creating any paper arm.
    from royin.model_budget import ModelBudget

    for config in configs.values():
        ModelBudget(config, require_existing=True)
    output.mkdir(parents=True, exist_ok=False)
    source = fingerprint()
    started = int(time.time())
    contest_end = int(datetime.fromisoformat("2026-10-23T23:50:00+03:30").timestamp())
    deadline = min(started + args.duration_seconds, contest_end)
    if deadline - started < horizon + 600:
        raise ValueError("Insufficient contest time for this fixed experiment")
    protocol = dict(
        evidence_kind="PROSPECTIVE_SHARED_INPUT_PAPER_ENTRY_ABLATION",
        run_id=args.run_id,
        revision=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        source_sha256=source,
        started_at=started,
        deadline=deadline,
        horizon_seconds=horizon,
        arms=["cash", "hold", "rule", "boxapi", "apmix"],
        max_debit_tmn=str(DEBIT),
        windows=[
            dict(
                start=started + i * args.duration_seconds // 2,
                end=started + (i + 1) * args.duration_seconds // 2,
            )
            for i in range(2)
        ],
        initial_capital_tmn=str(CAPITAL),
        minimum_notional_tmn=str(FLOOR),
        public_get_cap=args.public_get_cap,
        analysis_every_seconds=300,
        protection_every_seconds=60,
        model_role_http_cap=2,
        model_read_tool_cap=1,
        model_timeout_seconds=30,
        automatic_retries=0,
        stop_control="Create STOP_REQUESTED in this run directory for a bounded graceful stop",
        position_review="HOST_ONLY_ENTRY_ABLATION",
        pricing="EXCLUDED_FROM_MODEL_RANKING",
        policy="Shared host top-five quant universe; identical costs, books and post-model execution barrier",
        limitations=[
            "Paper fills are conservative snapshots, not exchange queue fills",
            "This tests entry policy with fixed host exits, not the full autonomous reviewer",
            "Fixed host shortlist differs from production model-selected deep research",
            "No resume: an interruption preserves ledgers and must be reviewed without resetting them",
            "A short positive result is not proof of future profitability or permission for live trading",
        ],
    )
    write_json(output / "protocol.json", protocol)
    (output / "raw").mkdir()
    arms = {}
    feed = ScannerPublicFeed(output / "raw", max_requests=args.public_get_cap)
    stop = False

    def should_stop():
        return stop or (output / "STOP_REQUESTED").exists()

    def request_stop(*_):
        nonlocal stop
        stop = True

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, request_stop)
    errors = []
    with ExitStack() as stack:
        try:
            for name in ("hold", "rule", "boxapi", "apmix"):
                arm = MarketPaperOrchestrator(
                    run_id=args.run_id + "-" + name,
                    model_mode="REAL_MODEL" if name in configs else "FAKE_MODEL",
                    duration_seconds=args.duration_seconds,
                    cycles=args.duration_seconds // 60 + 1,
                    interval_seconds=60,
                    public_get_cap=args.public_get_cap,
                    horizon_max_seconds=horizon,
                    order_tmn=DEBIT,
                    minimum_notional_tmn=FLOOR,
                    capture_dir=output / name,
                    config=configs.get(name, RuntimeConfig()),
                )
                arms[name] = arm
                stack.callback(arm.close)
                stack.enter_context(arm.ledger.worker())
                arm.public_feed = feed
                arm.ledger.set_meta("engine_lifecycle", "RUNNING")
            next_entry = 0
            cycle = 0
            while (
                not should_stop()
                and int(time.time()) < deadline
                and feed.requests < args.public_get_cap - 24
            ):
                tick = time.monotonic()
                if fingerprint() != source:
                    raise ValueError("Source changed during frozen comparison")
                await protect(arms, feed)
                now = int(time.time())
                if now >= next_entry and now % 300 < 200 and deadline - now > horizon + 300:
                    next_entry = now + 300
                    report = collect_batch(feed)
                    if not report.get("batch") or int(time.time()) % 300 < 240:
                        await entry_round(
                            arms, feed, report, output, cycle, should_stop=should_stop
                        )
                    else:
                        errors.append(
                            dict(
                                phase="ENTRY_DEFERRED", reason="COLLECTION_CROSSED_ANALYSIS_WINDOW"
                            )
                        )
                for arm in arms.values():
                    arm.completed_cycles += 1
                    arm._checkpoint_and_export(int(time.time()))
                cycle += 1
                write_json(
                    output / "progress.json",
                    dict(
                        status="RUNNING",
                        cycle=cycle,
                        next_entry_at=next_entry,
                        public_gets=feed.requests,
                        updated_at=int(time.time()),
                    ),
                )
                print(
                    json.dumps(dict(status="RUNNING", cycle=cycle, public_gets=feed.requests)),
                    flush=True,
                )
                while (
                    not should_stop()
                    and time.monotonic() - tick < 60
                    and int(time.time()) < deadline
                ):
                    await asyncio.sleep(0.5)
        except (
            ValueError,
            OSError,
            RuntimeError,
            KeyError,
            IndexError,
            TypeError,
            ArithmeticError,
            sqlite3.Error,
        ) as exc:
            errors.append(dict(phase="COMPARISON", error_type=type(exc).__name__))
        finally:
            results, residual = finalize_arms(arms, feed, output, errors)
            write_json(
                output / "report.json",
                dict(
                    protocol=protocol,
                    status="STOPPED_OPEN" if residual else "STOPPED_FLAT",
                    errors=errors,
                    public_gets=feed.requests,
                    source_unchanged=fingerprint() == source,
                    completeness="COMPLETE" if int(time.time()) >= deadline else "PARTIAL",
                    stop_requested=should_stop(),
                    cost_stress_contract="Fixed executed trades only; no decision or fill repricing",
                    results={"cash": dict(net_return_pct="0", fills_count=0), **results},
                    finished_at=int(time.time()),
                    financial_live="BLOCKED_NO_PRIVATE_TRANSPORT",
                ),
            )
    return 1 if errors else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--keys-file", type=Path, required=True)
    parser.add_argument("--duration-seconds", type=int, choices=(3600, 5400, 10800), default=5400)
    parser.add_argument("--horizon-seconds", type=int, choices=(1800, 3600, 7200), default=1800)
    parser.add_argument("--public-get-cap", type=int, choices=range(400, 1601), default=1200)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts/paired-paper")
    args = parser.parse_args(argv)
    if not args.run:
        print(json.dumps(dict(status="BLOCKED_EXPLICIT_RUN_REQUIRED", model_http=0, orders=0)))
        return 2
    try:
        return asyncio.run(run(args))
    except (ValueError, OSError, KeyError, TypeError):
        print(json.dumps(dict(status="BLOCKED_PAIRED_PREFLIGHT", orders=0)))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
