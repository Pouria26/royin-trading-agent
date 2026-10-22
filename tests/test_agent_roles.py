"""Two-role correctness with synthetic provider transport; no real-model claims."""

import asyncio
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import patch

import httpx2

from royin.agent import RoleRunEnvelope, decide_role
from royin.config import RuntimeConfig
from royin.decision import EntryOpportunityContext, PositionReviewContext
from royin.features import extract_features
from royin.market_data import Candle, CandleSeries
from royin.model_budget import BudgetBlocked, ModelBudget


def snapshot(quantity=D(0)):
    candles = tuple(Candle(6000+i*60, D(100), D(102), D(99), D(101), D(20)) for i in range(35))
    return extract_features(CandleSeries(candles, 60), "USDTTMN", cutoff=8100,
                            current_position_base=quantity)


def position():
    return PositionReviewContext(quantity=D(1), cost_basis_tmn=D(98), net_liquidation_tmn=D(100),
        opened_at=7500, observed_at=8100, hard_exit_at=9000, initial_stop_price=D(95),
        trailing_stop_price=D(99), checkpoint_profit_pct=D(".025"))


class RoleTests(unittest.IsolatedAsyncioTestCase):
    config = RuntimeConfig(BOXAPI_API_KEY="fake", LLM_COST_BUDGET="2.40",
                           LLM_TOKEN_BUDGET=6000000, LLM_COST_CURRENCY="USD")

    async def call(self, *, quantity=D(0), action="WAIT", mutate=None, delay=0, timeout=30):
        snap = snapshot(quantity)
        pos = position() if quantity else None
        opportunity = None if pos else EntryOpportunityContext(spread_pct=D(".001"),
            round_trip_fee_pct=D(".006"), bid_depth_tmn=D(100000), ask_depth_tmn=D(100000),
            catalog_sha256="c"*64, catalog_received_at=8101, candle_received_at=8102,
            depth_received_at=8103, observed_at=8105)
        proposal = dict(role="POSITION_REVIEWER" if pos else "ENTRY_ANALYST", action=action,
            cutoff=snap.cutoff, snapshot_sha256=snap.snapshot_sha256,
            position_sha256=pos.sha256 if pos else None, evidence_ids=["EV_DATA_FRESH"],
            opportunity_sha256=opportunity.sha256 if opportunity else None,
            reason="Independent synthetic output", invalidation="Next closed candle")
        proposal.update(mutate or {})
        bodies = []

        async def handler(request):
            if delay:
                await asyncio.sleep(delay)
            payload = json.loads(request.content)
            bodies.append(payload)
            self.assertEqual(payload["reasoning_effort"], "none")
            message = {"role": "assistant", "content": json.dumps(proposal)}
            finish = "stop"
            if len(bodies) == 1:
                message = dict(role="assistant", content=None, tool_calls=[dict(id="read1", type="function",
                    function=dict(name="read_market_snapshot", arguments="{}"))])
                finish = "tool_calls"
            return httpx2.Response(200, json=dict(id="fake-completion", object="chat.completion",
                created=0, model="gpt-6-luna", choices=[dict(index=0, finish_reason=finish, message=message)],
                usage=dict(prompt_tokens=100, completion_tokens=20, total_tokens=120)))

        trace = {}
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
            decision = await decide_role(snap, position=pos, opportunity=opportunity, config=self.config, client=client,
                                         model_trace=trace, timeout_seconds=timeout)
        return decision, trace, bodies

    async def test_entry_action_changes_with_model_and_is_bound_to_context(self):
        enter, trace, bodies = await self.call(action="ENTER")
        wait, _, _ = await self.call(action="WAIT")
        self.assertEqual((enter.action, wait.action), ("ENTER", "WAIT"))
        self.assertEqual(trace["context"]["role"], "ENTRY_ANALYST")
        self.assertEqual(trace["evidence_kind"], "FAKE_MODEL")
        self.assertEqual(trace["usage"]["requests"], 2)
        self.assertEqual(len(bodies), 2)
        tool = next(m for m in bodies[-1]["messages"] if m["role"] == "tool")
        self.assertEqual(json.loads(tool["content"])["snapshot_sha256"], enter.snapshot_sha256)

    async def test_reviewer_can_hold_above_checkpoint_or_exit_below_it(self):
        hold, trace, _ = await self.call(quantity=D(1), action="WAIT")
        exit_decision, _, _ = await self.call(quantity=D(1), action="EXIT")
        self.assertEqual((hold.action, exit_decision.action), ("WAIT", "EXIT"))
        self.assertEqual(trace["context"]["position"]["cost_basis_tmn"], "98")

    async def test_cross_role_action_and_wrong_bindings_fail_closed(self):
        for quantity, mutation in (
            (D(1), dict(action="ENTER")), (D(0), dict(action="EXIT")),
            (D(0), dict(role="POSITION_REVIEWER")), (D(0), dict(cutoff=8101)),
            (D(0), dict(snapshot_sha256="f"*64)), (D(1), dict(position_sha256="f"*64)),
            (D(1), dict(stop_loss_pct=".5")),
            (D(0), dict(opportunity_sha256="f"*64)),
        ):
            with self.subTest(mutation=mutation):
                dec, _, _ = await self.call(quantity=quantity, mutate=mutation)
                self.assertEqual(dec.action, "WAIT")
                self.assertIn("rejected", dec.reason)

    async def test_timeout_is_wait_and_does_not_run_rule_as_ai(self):
        dec, trace, _ = await self.call(delay=.1, timeout=.01)
        self.assertEqual(dec.action, "WAIT")
        self.assertIn("timed out", dec.reason)
        self.assertNotIn("sdk_messages_json", trace)

    async def test_invalid_input_closes_before_model(self):
        for snap, pos in ((snapshot(D(1)), None),
                          (replace(snapshot(), snapshot_sha256="0"*64), None),
                          (snapshot(D(1)), position().model_copy(update={"hard_exit_at":8100}))):
            with self.subTest(position=pos), patch("royin.agent.decide") as model:
                with self.assertRaises(ValueError):
                    await decide_role(snap, position=pos, config=self.config)
                model.assert_not_called()

    async def test_both_roles_share_run_http_and_durable_reservation_caps(self):
        with tempfile.TemporaryDirectory() as temp:
            budget = ModelBudget(self.config, Path(temp)/"budget.sqlite3")
            envelope = RoleRunEnvelope(budget)
            for _ in range(12):
                envelope.claim_run()
            with self.assertRaises(BudgetBlocked):
                envelope.claim_run()
            request = httpx2.Request("POST", "https://ai.boxapi.ir/ai/v1/chat/completions",
                                    json=dict(model="gpt-6-luna",max_tokens=512))
            for _ in range(19):
                await envelope.before_request(request)
            with self.assertRaises(BudgetBlocked):
                await envelope.before_request(request)
            self.assertEqual(envelope.reservation_ceiling_usd, D(".03803648"))
            with closing(sqlite3.connect(budget.path)) as db:
                self.assertEqual(db.execute("select count(*) from model_reservations").fetchone()[0],19)
            with patch("time.monotonic", return_value=envelope.started+601), self.assertRaises(BudgetBlocked):
                await envelope.before_request(request)

    async def test_numeric_risk_proposal_rejects_float_nan_and_negative(self):
        from royin.decision import DecisionProposal
        for value in (0.1, "NaN", "Infinity", "-.1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                DecisionProposal(action="ENTER", evidence_ids=["EV_DATA_FRESH"],
                                 reason="test", invalidation="test",target_profit_pct=value)


if __name__ == "__main__":
    unittest.main()
