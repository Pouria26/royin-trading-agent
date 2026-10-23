"""Funded-key monetary and restart oracles; no paid HTTP or trading."""

import asyncio
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from pydantic import SecretStr

from royin.agent import RoleRunEnvelope
from royin.config import RuntimeConfig
from royin.model_budget import BudgetBlocked, ModelBudget
from tests.test_multiday_service import config_for, engine_for_test, policy


class FundedBoxAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "original.sqlite3"
        self.old = RuntimeConfig(BOXAPI_API_KEY="original-test-key", LLM_COST_BUDGET="2.40",
            LLM_COST_CURRENCY="USD", LLM_TOKEN_BUDGET=6_000_000)
        ModelBudget(self.old, self.path).reserve()
        self.config = RuntimeConfig(BOXAPI_API_KEY="new-test-key", BOXAPI_CREDIT_ID="funded-test",
            LLM_COST_BUDGET="0.009", LLM_COST_CURRENCY="USD", LLM_TOKEN_BUDGET=22_000_000)

    def initialize(self, config=None):
        return ModelBudget.initialize_boxapi_credit(config or self.config, self.path,
            reported_credit_usd="2.9709", reason="explicit-operator-credit")

    def rows(self):
        with closing(sqlite3.connect(self.path)) as db:
            return db.execute("SELECT day,nano_usd,tokens,model,policy_hash FROM model_reservations ORDER BY id").fetchall()

    def test_new_funding_does_not_reset_or_charge_legacy_consumption(self):
        before = self.rows()
        self.initialize()
        b = ModelBudget(self.config, self.path, require_existing=True)
        self.assertEqual(b.reserve(), D(".00435712"))
        self.assertEqual(ModelBudget(self.config, self.path, require_existing=True).reserve(), D(".00435712"))
        with self.assertRaises(BudgetBlocked):
            ModelBudget(self.config, self.path, require_existing=True).reserve()
        self.assertEqual(self.rows()[:1], before)
        self.assertEqual(len(self.rows()), 3)
        ModelBudget(self.old, self.path, require_existing=True).reserve()
        self.assertEqual(len(self.rows()), 4)

    def test_key_mismatch_omitted_allocation_and_duplicate_initialization_block(self):
        self.initialize()
        for changes in ({"BOXAPI_API_KEY": SecretStr("other-key")}, {"BOXAPI_CREDIT_ID": "missing"},
                        {"BOXAPI_CREDIT_ID": None}):
            with self.subTest(changes=changes), self.assertRaises(BudgetBlocked):
                ModelBudget(self.config.model_copy(update=changes), self.path, require_existing=True)
        with self.assertRaises(BudgetBlocked):
            self.initialize()
        self.assertEqual(len(self.rows()), 1)

    def test_missing_original_state_never_initializes_or_continues(self):
        self.path.unlink()
        with self.assertRaisesRegex(BudgetBlocked, "MISSING_DURABLE_STATE"):
            self.initialize()
        with self.assertRaisesRegex(BudgetBlocked, "MISSING_DURABLE_STATE"):
            ModelBudget(self.config, self.path, require_existing=True)
        self.assertFalse(self.path.exists())

    def test_total_cap_is_exactly_bounded_and_never_resets_at_midnight(self):
        too_high = self.config.model_copy(update={"LLM_COST_BUDGET": D("2.822356")})
        with self.assertRaisesRegex(BudgetBlocked, "five percent"):
            self.initialize(too_high)
        self.initialize()
        start = datetime(2026, 10, 23, 20, 29, tzinfo=UTC)
        b = ModelBudget(self.config, self.path, require_existing=True)
        b.reserve(now=start)
        b.reserve(now=start + timedelta(minutes=2))
        with self.assertRaises(BudgetBlocked):
            b.reserve(now=start + timedelta(days=2))

    def test_service_scope_uses_funded_allowance_but_restart_preserves_old_limits(self):
        full = self.config.model_copy(update={"LLM_COST_BUDGET": D("2.822355")})
        self.initialize(full)
        b = ModelBudget(full, self.path, require_existing=True)
        contract = policy(max_role_decisions=323, analysis_interval_seconds=900)
        scope = RoleRunEnvelope(b, scope_id=contract.service_id,
            duration_seconds=contract.duration_seconds, service_contract=contract)
        self.assertEqual((scope.agent_limit, scope.cost_limit_usd), (323, D("2.822355")))
        scope.claim_run()
        resumed = RoleRunEnvelope(b, scope_id=contract.service_id,
            duration_seconds=contract.duration_seconds, service_contract=contract)
        self.assertEqual(resumed.agent_runs, 1)
        legacy = RoleRunEnvelope(ModelBudget(self.old, self.path, require_existing=True),
            scope_id="old-scope", duration_seconds=3600)
        self.assertEqual((legacy.agent_limit, legacy.cost_limit_usd), (48, D(".50")))

    def test_concurrent_funded_reservations_share_one_cap(self):
        from concurrent.futures import ThreadPoolExecutor

        one = self.config.model_copy(update={"LLM_COST_BUDGET": D(".0044")})
        self.initialize(one)
        def attempt(_):
            try:
                ModelBudget(one, self.path, require_existing=True).reserve()
                return 1
            except BudgetBlocked:
                return 0
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(sum(pool.map(attempt, range(4))), 1)
        self.assertEqual(len(self.rows()), 2)

    def test_fifteen_minute_analysis_cadence_survives_restart(self):
        contract = policy(analysis_interval_seconds=900)
        root = Path(self.temp.name) / "cadence"
        with patch("time.time", return_value=8105):
            arm = engine_for_test(root, contract, config_for(contract))
            with patch.object(arm, "_handle_entry_cycle", new_callable=AsyncMock) as entry:
                asyncio.run(arm._execute_cycle(MagicMock(requests=0), 8105))
                entry.assert_awaited_once()
            self.assertEqual(arm.ledger.get_meta("next_entry_analysis_at"), "9005")
            arm.close()
        with patch("time.time", return_value=8405):
            restored = engine_for_test(root, contract, config_for(contract))
            try:
                with patch.object(restored, "_handle_entry_cycle", new_callable=AsyncMock) as entry:
                    asyncio.run(restored._execute_cycle(MagicMock(requests=0), 9004))
                    entry.assert_not_awaited()
                    asyncio.run(restored._execute_cycle(MagicMock(requests=0), 9005))
                    entry.assert_awaited_once()
            finally:
                restored.close()
