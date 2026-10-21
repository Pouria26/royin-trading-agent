import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from royin.model_budget import BudgetBlocked
from scripts.evaluate_ai_role import limit_mission_budget, load_candles, main


class AIRoleEvaluationTests(unittest.TestCase):
    def test_default_command_never_starts_paid_run(self):
        with patch("scripts.evaluate_ai_role.asyncio.run") as run, patch("builtins.print"):
            self.assertEqual(main([]), 0)
        run.assert_not_called()

    def test_changed_dataset_rejected_before_model_configuration(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "changed.json"
            path.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                load_candles(path)

    def budget(self, rate):
        return SimpleNamespace(
            policy={"max_input_tokens": 1000, "max_output_tokens": 0},
            input_rate=Decimal(rate),
            output_rate=Decimal(0),
            reserve=Mock(return_value=Decimal(rate) / 1000),
        )

    def test_request_cap_precedes_durable_reservation(self):
        budget = self.budget("0.01")
        original = budget.reserve
        state = limit_mission_budget(budget)
        for _ in range(24):
            budget.reserve()
        with self.assertRaises(BudgetBlocked):
            budget.reserve()
        self.assertEqual(original.call_count, 24)
        self.assertEqual(state["requests"], 24)

    def test_cost_cap_precedes_durable_reservation(self):
        budget = self.budget("20")
        original = budget.reserve
        limit_mission_budget(budget)
        budget.reserve()
        budget.reserve()
        with self.assertRaises(BudgetBlocked):
            budget.reserve()
        self.assertEqual(original.call_count, 2)
