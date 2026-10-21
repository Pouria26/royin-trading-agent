import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx2

from royin.config import RuntimeConfig
from royin.model_budget import ModelBudget
from scripts.probe_model import main, run_probe


class ModelProbeSafetyTests(unittest.TestCase):
    def test_missing_key_blocks_without_provider_request(self):
        with (
            patch("sys.argv", ["probe_model.py", "--run"]),
            patch.dict(os.environ, {"BOXAPI_API_KEY": ""}),
            patch("scripts.probe_model.load_config", return_value=RuntimeConfig()),
            patch("scripts.probe_model.probe") as model_probe,
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(main(), 2)
            self.assertIn("BLOCKED", output.getvalue())
            model_probe.assert_not_called()

    def test_no_explicit_run_does_not_read_credentials_or_call_model(self):
        with (
            patch("sys.argv", ["probe_model.py"]),
            patch("scripts.probe_model.load_config", return_value=RuntimeConfig()) as load_credentials,
            patch("scripts.probe_model.probe") as model_probe,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(main(), 0)
            load_credentials.assert_not_called()
            model_probe.assert_not_called()


class ModelProbeWireContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_luna_tool_and_output_requests_both_disable_reasoning(self):
        config = RuntimeConfig(
            BOXAPI_API_KEY="synthetic-only", LLM_COST_BUDGET="2.40",
            LLM_TOKEN_BUDGET=6_000_000, LLM_COST_CURRENCY="USD",
        )
        requests = []

        def handle(request):
            payload = json.loads(request.content)
            requests.append(payload)
            self.assertEqual(payload["reasoning_effort"], "none")
            self.assertEqual(payload["model"], "gpt-6-luna")
            self.assertLessEqual(len(requests), 2)
            name = "read_snapshot" if len(requests) == 1 else next(
                tool["function"]["name"] for tool in payload["tools"]
                if tool["function"]["name"] != "read_snapshot"
            )
            arguments = {} if len(requests) == 1 else {"action": "WAIT", "evidence_id": "STALE_1"}
            return httpx2.Response(200, json={
                "id": "synthetic-completion", "object": "chat.completion", "created": 0,
                "model": "gpt-6-luna", "choices": [{"index": 0, "finish_reason": "tool_calls",
                    "message": {"role": "assistant", "content": None, "tool_calls": [{
                        "id": f"call_{len(requests)}", "type": "function",
                        "function": {"name": name, "arguments": json.dumps(arguments)},
                    }]}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
            })

        with tempfile.TemporaryDirectory() as directory:
            budget = ModelBudget(config, Path(directory) / "budget.sqlite3")
            async with httpx2.AsyncClient(
                transport=httpx2.MockTransport(handle),
                event_hooks={"request": [budget.before_request]},
            ) as client:
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(await run_probe(config, budget, client, "stale"), 0)
        self.assertEqual(len(requests), 2)
