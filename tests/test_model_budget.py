import asyncio
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx2

from royin.config import RuntimeConfig
from royin.model_budget import BudgetBlocked, ModelBudget


class ModelBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "budget.sqlite3"
        self.config = RuntimeConfig(LLM_COST_BUDGET="2.40", LLM_COST_CURRENCY="USD",
                                    LLM_TOKEN_BUDGET=6_000_000)
        self.now = datetime(2026, 10, 21, 12, tzinfo=UTC)

    def test_known_tariff_reservation_and_restart_never_refund(self):
        config = self.config.model_copy(update={"LLM_TOKEN_BUDGET": 13312})
        budget = ModelBudget(config, self.path)
        self.assertEqual(str(budget.reserve(now=self.now)), "0.00200192")
        with self.assertRaises(BudgetBlocked):
            ModelBudget(config, self.path).reserve(now=self.now + timedelta(days=1))

    def test_daily_counter_uses_tehran_boundary_but_total_does_not_reset(self):
        budget = ModelBudget(self.config, self.path)
        budget.policy["max_requests_daily"] = 1
        budget.policy["max_requests_total"] = 2
        before_midnight = datetime(2026, 10, 21, 20, 29, tzinfo=UTC)
        budget.reserve(now=before_midnight)
        with self.assertRaises(BudgetBlocked):
            budget.reserve(now=before_midnight)
        budget.reserve(now=before_midnight + timedelta(minutes=2))
        with self.assertRaises(BudgetBlocked):
            budget.reserve(now=before_midnight + timedelta(days=2))

    def test_atomic_spending_cap_across_simultaneous_clients(self):
        config = RuntimeConfig(LLM_COST_BUDGET="0.0021", LLM_COST_CURRENCY="USD",
                               LLM_TOKEN_BUDGET=6_000_000)

        def attempt(_):
            try:
                ModelBudget(config, self.path).reserve(now=self.now)
                return True
            except BudgetBlocked:
                return False

        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(sum(pool.map(attempt, range(4))), 1)

    def test_invalid_endpoint_limits_model_or_builtin_tool_never_reserve(self):
        budget = ModelBudget(self.config, self.path)
        for change in ({"max_completion_tokens": 1025}, {"max_completion_tokens": True},
                       {"stream": True}, {"n": 2}, {"model": "gpt-6-astra"},
                       {"tools": [{"type": "web_search"}]}, {"messages": ["x" * 14000]}):
            payload = {"model": "gpt-6-luna", "max_completion_tokens": 512, **change}
            request = httpx2.Request("POST", "https://ai.boxapi.ir/ai/v1/chat/completions",
                                     json=payload)
            with self.subTest(change=list(change)), self.assertRaises(BudgetBlocked):
                asyncio.run(budget.before_request(request))
        with self.assertRaises(BudgetBlocked):
            asyncio.run(budget.before_request(httpx2.Request("POST", "https://example.com")))
        self.assertFalse(self.path.exists())

    def test_disk_failure_prevents_network_and_no_request_is_refunded(self):
        bad_parent = Path(self.temp.name) / "a-file"
        bad_parent.write_text("occupied", encoding="utf-8")
        with self.assertRaises(OSError):
            ModelBudget(self.config, bad_parent / "budget.sqlite3").reserve()
        budget = ModelBudget(self.config, self.path)
        request = httpx2.Request("POST", "https://ai.boxapi.ir/ai/v1/chat/completions",
                                 json={"model": "gpt-6-luna", "max_completion_tokens": 512})
        asyncio.run(budget.before_request(request))
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM model_reservations").fetchone()[0], 1)

    def test_http_hook_reserves_before_transport_and_blocks_second_request(self):
        config = self.config.model_copy(update={"LLM_TOKEN_BUDGET": 13312})
        budget = ModelBudget(config, self.path)
        calls = []

        def handle(request):
            with closing(sqlite3.connect(self.path)) as db:
                count = db.execute("SELECT COUNT(*) FROM model_reservations").fetchone()[0]
            self.assertEqual(count, 1)
            calls.append(request)
            return httpx2.Response(200, json={"ok": True})

        async def run():
            async with httpx2.AsyncClient(
                transport=httpx2.MockTransport(handle),
                event_hooks={"request": [budget.before_request]},
            ) as client:
                for _ in range(2):
                    await client.post("https://ai.boxapi.ir/ai/v1/chat/completions",
                                      json={"model": "gpt-6-luna", "max_completion_tokens": 512})

        with self.assertRaises(BudgetBlocked):
            asyncio.run(run())
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
