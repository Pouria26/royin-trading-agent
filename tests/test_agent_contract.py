"""Pydantic AI wiring checks with fake responses, not trading or real-model evals."""

import unittest
from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic_ai import Agent, models
from pydantic_ai.exceptions import UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import UsageLimits


class ProbeDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["WAIT", "REVIEW"]
    evidence_id: str


class AgentContractTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.old = models.ALLOW_MODEL_REQUESTS
        models.ALLOW_MODEL_REQUESTS = False

    def tearDown(self):
        models.ALLOW_MODEL_REQUESTS = self.old

    async def test_read_tool_result_reaches_typed_output(self):
        calls = []

        def model(messages, info):
            if len(messages) == 1:
                return ModelResponse(parts=[ToolCallPart("read_snapshot", {})])
            self.assertIn("SNAPSHOT_1", repr(messages))
            return ModelResponse(parts=[ToolCallPart(
                info.output_tools[0].name,
                {"action": "WAIT", "evidence_id": "SNAPSHOT_1"},
            )])

        agent = Agent(FunctionModel(model), output_type=ProbeDecision)

        @agent.tool_plain
        def read_snapshot() -> str:
            calls.append("read")
            return "SNAPSHOT_1: stale market data"

        result = await agent.run("Inspect the data", usage_limits=UsageLimits(request_limit=2))
        self.assertEqual(calls, ["read"])
        self.assertEqual(result.output.action, "WAIT")
        self.assertEqual(result.output.evidence_id, "SNAPSHOT_1")

    async def test_invalid_output_is_not_silently_accepted(self):
        def invalid(messages, info):
            return ModelResponse(parts=[ToolCallPart(
                info.output_tools[0].name,
                {"action": "BUY_EVERYTHING", "evidence_id": "SNAPSHOT_1"},
            )])

        agent = Agent(FunctionModel(invalid), output_type=ProbeDecision, retries=0)
        with self.assertRaises(UnexpectedModelBehavior):
            await agent.run("Inspect")

    async def test_request_budget_stops_loop(self):
        calls = []

        def looping(messages, info):
            return ModelResponse(parts=[ToolCallPart("read_snapshot", {})])

        agent = Agent(FunctionModel(looping))

        @agent.tool_plain
        def read_snapshot() -> str:
            calls.append("read")
            return "snapshot"

        with self.assertRaises(UsageLimitExceeded):
            await agent.run("Inspect", usage_limits=UsageLimits(request_limit=1))
        self.assertEqual(calls, ["read"])


if __name__ == "__main__":
    unittest.main()
