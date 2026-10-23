"""Synthetic deployment/recovery checks; no model or exchange trading evidence."""

import asyncio
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import MagicMock, patch

from pydantic import ValidationError

from royin.agent import RoleRunEnvelope
from royin.config import RuntimeConfig
from royin.model_budget import BudgetBlocked, ModelBudget
from royin.model_profiles import PROVIDER_ORIGINS
from royin.service_contract import ServiceContract
from scripts import run_service
from scripts.run_market_paper import MarketPaperOrchestrator, build_default_rules
from scripts.run_paper_trader import ScannerPublicFeed
from tests.test_market_selection import opportunity, snapshot


def policy(**changes):
    start = datetime.fromtimestamp(8100, UTC)
    return ServiceContract(
        **dict(
            service_id="svc_synthetic",
            started_at=start,
            submission_deadline_at=start + timedelta(hours=2),
            trading_end_at=start + timedelta(hours=80),
            finalize_start_at=start + timedelta(hours=79),
            **changes,
        )
    )


def config_for(contract, **changes):
    return RuntimeConfig(
        **dict(
            SUBMISSION_DEADLINE_AT=contract.submission_deadline_at.isoformat(),
            TRADING_END_AT=contract.trading_end_at.isoformat(),
            FINALIZE_START_AT=contract.finalize_start_at.isoformat(),
            **changes,
        )
    )


def engine_for_test(root, contract, config, *, model_mode="FAKE_MODEL"):
    return MarketPaperOrchestrator(
        run_id=contract.service_id,
        config=config,
        model_mode=model_mode,
        duration_seconds=contract.duration_seconds,
        cycles=contract.cycles,
        interval_seconds=contract.poll_seconds,
        public_get_cap=contract.max_public_gets,
        order_tmn=contract.max_debit_tmn,
        minimum_notional_tmn=contract.minimum_notional_tmn,
        horizon_max_seconds=contract.horizon_max_seconds,
        capture_dir=root / "mission",
        service_contract=contract,
    )


class MultidayContractTests(unittest.TestCase):
    def test_submission_does_not_end_financial_mission_and_credit_expiry_does(self):
        p = policy()
        self.assertEqual(p.duration_seconds, 80 * 3600)
        self.assertLess(p.submission_deadline_at, p.effective_end_at)
        values = p.model_dump()
        values.update(
            credit_expires_at=p.started_at + timedelta(hours=48),
            finalize_start_at=p.started_at + timedelta(hours=47),
        )
        shorter = ServiceContract(**values)
        self.assertEqual(shorter.duration_seconds, 48 * 3600)
        values["finalize_start_at"] = p.finalize_start_at
        with self.assertRaises(ValidationError):
            ServiceContract(**values)

    def test_ambiguous_naive_time_oversized_budget_float_money_and_live_are_rejected(self):
        p = policy().model_dump()
        for field, value in [
            ("started_at", "2026-10-23T12:00:00"),
            ("max_public_gets", 50001),
            ("max_debit_tmn", 150000.0),
            ("mode", "live"),
            ("trading_end_at", datetime.fromtimestamp(8100, UTC) + timedelta(days=5)),
        ]:
            with self.subTest(field=field), self.assertRaises(ValidationError):
                ServiceContract(**{**p, field: value})

    def test_old_and_new_deadline_conflict_is_not_silently_ignored(self):
        p = policy()
        with self.assertRaises(ValidationError):
            config_for(p, CHALLENGE_END_AT=p.submission_deadline_at.isoformat())
        config = config_for(p)
        self.assertEqual(config.financial_end_at, p.trading_end_at)
        with self.assertRaises(ValidationError):
            config_for(p, CREDIT_EXPIRES_AT=p.submission_deadline_at.isoformat())

    def test_large_runtime_and_get_budget_require_matching_mission(self):
        p = policy()
        with tempfile.TemporaryDirectory() as tmp, patch("time.time", return_value=8105):
            root = Path(tmp)
            arm = engine_for_test(root, p, config_for(p))
            try:
                self.assertEqual(arm.run_started_at, 8100)
                self.assertEqual(
                    arm.protection_policy.deadline_utc, int(p.effective_end_at.timestamp())
                )
                self.assertEqual(arm.protection_policy.exit_buffer_seconds, 3600)
            finally:
                arm.close()
            with self.assertRaises(ValueError):
                MarketPaperOrchestrator(
                    run_id="legacy",
                    duration_seconds=36001,
                    capture_dir=root / "legacy",
                    config=RuntimeConfig(),
                )
            with self.assertRaises(ValueError):
                ScannerPublicFeed(root / "raw", max_requests=4097)
            feed = ScannerPublicFeed(
                root / "raw", max_requests=p.max_public_gets, service_contract=p
            )
            self.assertEqual(feed.requests, 0)

    def test_short_supported_holding_horizon_keeps_review_within_holding_cap(self):
        values = policy().model_dump()
        values["horizon_max_seconds"] = 300
        short = ServiceContract(**values)
        with tempfile.TemporaryDirectory() as tmp, patch("time.time", return_value=8105):
            arm = engine_for_test(Path(tmp), short, config_for(short))
            try:
                self.assertEqual(arm.protection_policy.review_interval_seconds, 300)
                self.assertEqual(arm.protection_policy.hard_holding_seconds, 300)
            finally:
                arm.close()

    def test_new_external_role_scope_can_be_longer_but_old_scope_cannot_be_promoted(self):
        with tempfile.TemporaryDirectory() as tmp, patch("time.time", return_value=8105):
            config = RuntimeConfig(
                LLM_PROVIDER="apmix",
                LLM_MODEL="claude-sonnet-4-6-free",
                LLM_BASE_URL=PROVIDER_ORIGINS["apmix"],
                APMIX_API_KEY="synthetic-service-key",
                LLM_TOKEN_BUDGET=20000000,
            )
            path = Path(tmp) / "external.sqlite3"
            ModelBudget.initialize_provider_state(config, path)
            budget = ModelBudget(config, path, require_existing=True)
            p = policy()
            role = RoleRunEnvelope(
                budget,
                duration_seconds=p.duration_seconds,
                scope_id=p.service_id,
                service_contract=p,
            )
            for _ in range(49):
                role.claim_run()
            restored = RoleRunEnvelope(
                budget,
                duration_seconds=p.duration_seconds,
                scope_id=p.service_id,
                service_contract=p,
            )
            self.assertEqual(restored.agent_runs, 49)
            old = RoleRunEnvelope(budget, duration_seconds=600, scope_id="svc_old")
            old.claim_run()
            values = p.model_dump()
            values["service_id"] = "svc_old"
            changed = ServiceContract(**values)
            with self.assertRaises(BudgetBlocked):
                RoleRunEnvelope(
                    budget,
                    duration_seconds=changed.duration_seconds,
                    scope_id=changed.service_id,
                    service_contract=changed,
                )
            self.assertEqual(
                RoleRunEnvelope(budget, duration_seconds=600, scope_id="svc_old").agent_runs, 1
            )


class ProviderExtensionTests(unittest.TestCase):
    def test_external_extension_preserves_reservations_and_audits_without_box_bypass(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = RuntimeConfig(
                LLM_PROVIDER="apmix",
                LLM_MODEL="claude-sonnet-4-6-free",
                LLM_BASE_URL=PROVIDER_ORIGINS["apmix"],
                APMIX_API_KEY="synthetic-service-key",
                LLM_TOKEN_BUDGET=20000000,
            )
            path = Path(tmp) / "external.sqlite3"
            ModelBudget.initialize_provider_state(config, path)
            budget = ModelBudget(config, path, require_existing=True)
            budget.reserve()
            with closing(budget.connect()) as db:
                before = db.execute("SELECT * FROM model_reservations").fetchall()
            result = budget.extend_external_token_limit(300000000, reason="synthetic-multiday")
            self.assertFalse(result["reservations_reset"])
            with closing(budget.connect()) as db:
                self.assertEqual(db.execute("SELECT * FROM model_reservations").fetchall(), before)
                self.assertEqual(
                    db.execute(
                        "SELECT old_limit,new_limit FROM provider_limit_extensions"
                    ).fetchall(),
                    [(20000000, 300000000)],
                )
            with self.assertRaises(BudgetBlocked):
                budget.extend_external_token_limit(20000000, reason="synthetic-reset")
            box = RuntimeConfig(
                BOXAPI_API_KEY="synthetic-box",
                LLM_TOKEN_BUDGET=20000000,
                LLM_COST_BUDGET="2.40",
                LLM_COST_CURRENCY="USD",
            )
            boxpath = Path(tmp) / "box.sqlite3"
            ModelBudget(box, boxpath).reserve()
            with self.assertRaises(BudgetBlocked):
                ModelBudget(box, boxpath, require_existing=True).extend_external_token_limit(
                    300000000, reason="synthetic"
                )


class DurableServiceTests(unittest.TestCase):
    def test_volume_marker_missing_state_and_second_owner_fail_without_bootstrap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = policy()
            with self.assertRaises(ValueError):
                run_service.service_paths(root, p)
            (root / ".royin-volume-id").write_text("synthetic-volume-identity")
            run, db, prepared = run_service.service_paths(root, p)
            with self.assertRaises(ValueError):
                asyncio.run(run_service.run(root, p, config_for(p), park=False))
            self.assertFalse(run.exists())
            with (
                run_service.owner_lock(root),
                self.assertRaises(sqlite3.OperationalError),
                run_service.owner_lock(root),
            ):
                self.fail("second owner acquired lock")
            with run_service.owner_lock(root):
                self.assertFalse(db.exists())
                self.assertFalse(prepared.exists())

    def test_health_is_redacted_and_budget_degradation_keeps_liveness(self):
        with tempfile.TemporaryDirectory() as tmp, patch("time.time", return_value=8105):
            root = Path(tmp)
            p = policy()
            arm = engine_for_test(root, p, config_for(p))
            try:
                arm.ledger.set_meta("service_state", "RUNNING")
                arm.ledger.set_meta("engine_heartbeat", "8105")
                arm.ledger.set_meta("secret", "synthetic-should-not-leak")
                arm.ledger.set_meta("entry_block_reason", "BUDGET_EXHAUSTED")
                health = run_service.read_health(arm.db_path, p.service_id, now=8110)
                self.assertTrue(health["alive"])
                self.assertFalse(health["ready"])
                self.assertNotIn("synthetic-should-not-leak", json.dumps(health))
                self.assertFalse(
                    run_service.read_health(arm.db_path, p.service_id, now=8500)["alive"]
                )
            finally:
                arm.close()

    def test_restart_restores_position_stop_and_cadence_even_without_model_state(self):
        with tempfile.TemporaryDirectory() as tmp, patch("time.time", return_value=8105):
            root = Path(tmp)
            data = root / "data"
            data.mkdir()
            p = policy()
            config = config_for(
                p,
                BOXAPI_API_KEY="synthetic-box",
                LLM_TOKEN_BUDGET=20000000,
                LLM_COST_BUDGET="2.40",
                LLM_COST_CURRENCY="USD",
            )
            path = data / "llm-budget.sqlite3"
            ModelBudget(config, path).reserve()
            with patch("royin.model_budget.ROOT", root):
                arm = engine_for_test(root, p, config, model_mode="REAL_MODEL")
                from royin.decision import Decision

                snap = snapshot("ETHTMN")
                opp = opportunity().model_copy(update={"best_bid": D("100.99"), "best_ask": D(101)})
                rules = build_default_rules("ETHTMN", tick_size=D(".01"))
                decision = Decision(
                    decision_id="synthetic-enter",
                    symbol="ETHTMN",
                    action="ENTER",
                    cutoff=snap.cutoff,
                    snapshot_sha256=snap.snapshot_sha256,
                    evidence_ids=("EV_DATA_FRESH",),
                    reason="Synthetic restart test",
                    invalidation="Stop",
                )
                feed = MagicMock()
                feed.get.return_value = (
                    {
                        "success": True,
                        "result": {
                            "bid": [{"price": "100.99", "quantity": "100000"}],
                            "ask": [{"price": "101", "quantity": "100000"}],
                        },
                    },
                    8105,
                )
                asyncio.run(
                    arm._apply_entry_decision(
                        feed,
                        decision,
                        {snap.symbol: (snap, opp)},
                        primary_snap=snap,
                        report={"market_rules": {snap.symbol: rules}},
                        bootstrap_attempts=[],
                        input_state=arm._replay_input_state(),
                        model_trace={"evidence_kind": "SYNTHETIC"},
                    )
                )
                before = arm.ledger.get_balance("ETH").total
                self.assertGreater(before, D(0))
                arm.ledger.set_meta("next_entry_analysis_at", "8405")
                old_stop = json.loads(arm.ledger.get_meta("protection_ETHTMN"))[
                    "trailing_stop_price"
                ]
                arm._checkpoint_and_export(8105)
                arm.close()
                path.rename(
                    path.with_suffix(".unavailable")
                )  # Preserve the synthetic original, do not recreate it.
                restored = engine_for_test(root, p, config, model_mode="REAL_MODEL")
                try:
                    self.assertTrue(restored.model_startup_blocked)
                    self.assertFalse(path.exists())
                    self.assertEqual(restored.ledger.get_balance("ETH").total, before)
                    self.assertEqual(restored.ledger.get_meta("next_entry_analysis_at"), "8405")
                    self.assertEqual(
                        json.loads(restored.ledger.get_meta("protection_ETHTMN"))[
                            "trailing_stop_price"
                        ],
                        old_stop,
                    )
                    feed.get.return_value = (
                        {
                            "success": True,
                            "result": {
                                "bid": [{"price": "97", "quantity": "100000"}],
                                "ask": [{"price": "97.1", "quantity": "100000"}],
                            },
                        },
                        8106,
                    )
                    with patch(
                        "scripts.run_market_paper.decide_role",
                        side_effect=AssertionError("Model forbidden"),
                    ):
                        asyncio.run(restored._execute_cycle(feed, 8106))
                    self.assertEqual(restored.ledger.get_balance("ETH").total, D(0))
                    self.assertEqual(restored.ledger.get_meta("closed_round_trips"), "1")
                    self.assertFalse(path.exists())
                finally:
                    restored.close()


if __name__ == "__main__":
    unittest.main()
