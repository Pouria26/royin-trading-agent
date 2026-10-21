import unittest
from decimal import Decimal
from unittest.mock import MagicMock

import httpx2
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from royin.agent import decide
from royin.config import RuntimeConfig
from royin.decision import DecisionProposal
from royin.features import FeatureSnapshot
from royin.model_budget import BudgetBlocked


def _make_dummy_snapshot(symbol="USDTTMN", cutoff=1700000000):
    return FeatureSnapshot(
        symbol=symbol,
        cutoff=cutoff,
        interval_seconds=900,
        closed_bars_count=35,
        last_close=Decimal("60000"),
        trend_sma_fast=Decimal("60100"),
        trend_sma_slow=Decimal("59900"),
        rsi_14=Decimal("55"),
        atr_14=Decimal("200"),
        volume_ratio=Decimal("1.1"),
        current_position_base=Decimal(0),
        available_tmn_cash=Decimal("5000000"),
        evidences={
            "EV_DATA_FRESH": "Candle closed at 1700000000",
            "EV_TREND_BULLISH": "Price above SMA",
            "EV_POSITION_FLAT": "No position",
        },
        snapshot_sha256="c" * 64,
    )


class AgentRegressionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config = RuntimeConfig(
            RUN_MODE="historical",
            ENABLE_LIVE_TRADING=False,
            BOXAPI_API_KEY="test-secret-key-12345",
            LLM_MODEL="gpt-6-luna",
            LLM_COST_BUDGET=Decimal("2.40"),
            LLM_TOKEN_BUDGET=300000,
            LLM_COST_CURRENCY="USD",
        )

    async def test_decide_without_budget_and_without_mock_client_fails_closed(self):
        """Calling decide without a client and without budget must raise ValueError (no bypass)."""
        snap = _make_dummy_snapshot()
        with self.assertRaises(ValueError) as ctx:
            await decide(snap, config=self.config, budget=None, client=None)
        self.assertIn("ModelBudget", str(ctx.exception))

    async def test_reusing_agent_does_not_leak_stale_snapshot_closures(self):
        """Reusing the same Agent instance across multiple calls evaluates each snapshot independently."""
        snap1 = _make_dummy_snapshot(cutoff=1700000000)
        snap2 = _make_dummy_snapshot(cutoff=1700000900)

        # Create a single Agent with TestModel
        mock_proposal = DecisionProposal(
            action="WAIT",
            evidence_ids=("EV_DATA_FRESH",),
            reason="Holding wait pattern",
            invalidation="Breakout",
        )
        test_model = TestModel(custom_output_args=mock_proposal.model_dump())
        agent = Agent(test_model, output_type=DecisionProposal, deps_type=FeatureSnapshot)

        mock_transport = httpx2.MockTransport(lambda req: httpx2.Response(200, json={}))
        async with httpx2.AsyncClient(transport=mock_transport) as client:
            d1 = await decide(snap1, config=self.config, client=client, agent=agent)
            d2 = await decide(snap2, config=self.config, client=client, agent=agent)

            self.assertEqual(d1.cutoff, 1700000000)
            self.assertEqual(d2.cutoff, 1700000900)
            self.assertEqual(d1.action, "WAIT")
            self.assertEqual(d2.action, "WAIT")

    async def test_budget_blocked_returns_safe_wait_with_real_evidence(self):
        """BudgetBlocked must return safe WAIT citing existing evidence from snapshot, not EV_FALLBACK."""
        snap = _make_dummy_snapshot()
        mock_budget = MagicMock()
        mock_budget.before_request.side_effect = BudgetBlocked("Total budget cap breached")

        mock_transport = httpx2.MockTransport(lambda req: httpx2.Response(200, json={}))
        async with httpx2.AsyncClient(transport=mock_transport, event_hooks={"request": [mock_budget.before_request]}) as client:
            decision = await decide(snap, config=self.config, budget=mock_budget, client=client)

            self.assertEqual(decision.action, "WAIT")
            self.assertIn("EV_DATA_FRESH", decision.evidence_ids)
            self.assertNotIn("EV_FALLBACK", decision.evidence_ids)
            self.assertIn("budget", decision.reason.lower())


if __name__ == "__main__":
    unittest.main()
