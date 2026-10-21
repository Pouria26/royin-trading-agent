import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import httpx2

from royin.agent import decide
from royin.config import RuntimeConfig
from royin.decision import Decision, DecisionProposal
from royin.evaluation import (
    baseline_rule_decision,
    run_ablation_comparison,
    verify_decision_causality,
)
from royin.features import extract_features
from royin.logger import AuditLogger
from royin.market_data import Candle, CandleSeries
from royin.model_budget import BudgetBlocked


class AgentDecisionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config = RuntimeConfig(
            BOXAPI_API_KEY="synthetic-boxapi-key",
            LLM_COST_BUDGET="2.40",
            LLM_TOKEN_BUDGET=6_000_000,
            LLM_COST_CURRENCY="USD",
        )
        self.step = 900
        self.start = 1790812800

        # Create 50 synthetic candles
        candles = []
        base_price = Decimal("60000")
        for i in range(50):
            t = self.start + i * self.step
            p = base_price + Decimal(i * 100)
            candles.append(Candle(
                open_time=t,
                open=p,
                high=p + Decimal(50),
                low=p - Decimal(20),
                close=p + Decimal(30),
                volume=Decimal("15.0"),
            ))
        self.series = CandleSeries(tuple(candles), self.step)
        self.cutoff = self.start + 45 * self.step

    def _make_mock_client(self, proposal: DecisionProposal):
        requests = []

        def handle(request):
            payload = json.loads(request.content)
            requests.append(payload)
            # Verify Luna wire contract
            self.assertEqual(payload["reasoning_effort"], "none")
            self.assertEqual(payload["model"], "gpt-6-luna")
            self.assertLessEqual(len(requests), 2)

            if len(requests) == 1:
                # First turn: model calls tool read_market_snapshot
                return httpx2.Response(200, json={
                    "id": "compl_1",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "gpt-6-luna",
                    "choices": [{
                        "index": 0,
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [{
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "read_market_snapshot",
                                    "arguments": "{}",
                                },
                            }],
                        },
                    }],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
                })
            else:
                # Second turn: model returns structured DecisionProposal
                return httpx2.Response(200, json={
                    "id": "compl_2",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "gpt-6-luna",
                    "choices": [{
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": proposal.model_dump_json(),
                        },
                    }],
                    "usage": {"prompt_tokens": 150, "completion_tokens": 50, "total_tokens": 200},
                })

        client = httpx2.AsyncClient(transport=httpx2.MockTransport(handle))
        return client, requests

    async def test_decide_enter_on_bullish_and_flat(self):
        snapshot = extract_features(
            self.series, "USDTTMN", cutoff=self.cutoff, current_position_base=Decimal(0)
        )
        self.assertIn("EV_TREND_BULLISH", snapshot.evidences)
        self.assertIn("EV_POSITION_FLAT", snapshot.evidences)

        proposal = DecisionProposal(
            action="ENTER",
            evidence_ids=("EV_TREND_BULLISH", "EV_POSITION_FLAT"),
            reason="Bullish trend verified with no active position",
            invalidation="Fast SMA crosses below slow SMA",
        )
        client, requests = self._make_mock_client(proposal)

        with tempfile.TemporaryDirectory() as temp:
            audit = AuditLogger(log_dir=Path(temp), enable_console=False)
            decision = await decide(
                snapshot, config=self.config, client=client,
                allowed_symbols=("USDTTMN",), audit=audit,
            )
            events = [json.loads(line) for line in audit.audit_path.read_text(encoding="utf-8").splitlines()]
            result = next(event for event in events if event["event_type"] == "AI_RESULT")
            self.assertEqual(result["payload"]["provider_reported_usage"]["input_tokens"], 250)
            self.assertEqual(result["payload"]["provider_reported_usage"]["output_tokens"], 70)
            audit.close()
        self.assertEqual(decision.action, "ENTER")
        self.assertEqual(decision.symbol, "USDTTMN")
        self.assertEqual(decision.cutoff, self.cutoff)
        self.assertEqual(decision.snapshot_sha256, snapshot.snapshot_sha256)
        self.assertEqual(len(requests), 2)

    async def test_decide_exit_on_long_position(self):
        snapshot = extract_features(
            self.series, "USDTTMN", cutoff=self.cutoff, current_position_base=Decimal("50.0")
        )
        self.assertIn("EV_POSITION_LONG", snapshot.evidences)

        proposal = DecisionProposal(
            action="EXIT",
            evidence_ids=("EV_POSITION_LONG", "EV_DATA_FRESH"),
            reason="Taking profit or risk reduction on active position",
            invalidation="Next bar close",
        )
        client, _requests = self._make_mock_client(proposal)

        decision = await decide(
            snapshot,
            config=self.config,
            client=client,
            allowed_symbols=("USDTTMN",),
        )
        self.assertEqual(decision.action, "EXIT")
        self.assertEqual(decision.symbol, "USDTTMN")

    async def test_fabricated_evidence_rejected_to_safe_wait(self):
        snapshot = extract_features(
            self.series, "USDTTMN", cutoff=self.cutoff, current_position_base=Decimal(0)
        )
        proposal = DecisionProposal(
            action="ENTER",
            evidence_ids=("EV_HALLUCINATED_NEWS",),
            reason="Fabricated evidence cited",
            invalidation="Never",
        )
        client, _ = self._make_mock_client(proposal)

        decision = await decide(
            snapshot,
            config=self.config,
            client=client,
            allowed_symbols=("USDTTMN",),
        )
        # Must fail closed to WAIT!
        self.assertEqual(decision.action, "WAIT")
        self.assertIn("rejected", decision.reason.lower())

    async def test_symbol_outside_allowed_universe_fails_closed(self):
        snapshot = extract_features(
            self.series, "PAXGTMN", cutoff=self.cutoff, current_position_base=Decimal(0)
        )
        decision = await decide(
            snapshot,
            config=self.config,
            client=None,
            allowed_symbols=("USDTTMN", "BTCTMN"),
        )
        self.assertEqual(decision.action, "WAIT")
        self.assertIn("not in allowed universe", decision.reason.lower())

    async def test_budget_blocked_fails_closed_to_wait(self):
        snapshot = extract_features(
            self.series, "USDTTMN", cutoff=self.cutoff, current_position_base=Decimal(0)
        )
        mock_budget = MagicMock()
        mock_budget.before_request.side_effect = BudgetBlocked("Exceeded cap")

        def handle(request):
            return httpx2.Response(200, json={})

        client = httpx2.AsyncClient(
            transport=httpx2.MockTransport(handle),
            event_hooks={"request": [mock_budget.before_request]},
        )
        decision = await decide(
            snapshot,
            config=self.config,
            client=client,
            allowed_symbols=("USDTTMN",),
        )
        self.assertEqual(decision.action, "WAIT")
        self.assertIn("budget", decision.reason.lower())

    def test_verify_decision_causality_and_prefix_invariance(self):
        proposal = DecisionProposal(
            action="ENTER",
            evidence_ids=("EV_TREND_BULLISH", "EV_POSITION_FLAT"),
            reason="Causal test proposal",
            invalidation="Breakout failure",
        )
        # Full series and prefix series
        prefix_candles = self.series.candles[:46]
        prefix_series = CandleSeries(tuple(prefix_candles), self.step)

        is_identical, dec_full, dec_prefix = verify_decision_causality(
            self.series, prefix_series, "USDTTMN", self.cutoff, proposal
        )
        self.assertTrue(is_identical)
        self.assertEqual(dec_full.snapshot_sha256, dec_prefix.snapshot_sha256)
        self.assertEqual(dec_full.action, dec_prefix.action)

    def test_ablation_comparison_detects_ai_divergence(self):
        snapshot = extract_features(
            self.series, "USDTTMN", cutoff=self.cutoff, current_position_base=Decimal(0)
        )
        # Rule baseline would say ENTER because EV_TREND_BULLISH is present
        base_decision = baseline_rule_decision(snapshot, decision_id="b1")
        self.assertEqual(base_decision.action, "ENTER")

        # But AI could decide WAIT due to caution
        ai_decision = Decision(
            decision_id="ai_1",
            symbol="USDTTMN",
            action="WAIT",
            cutoff=self.cutoff,
            snapshot_sha256=snapshot.snapshot_sha256,
            evidence_ids=("EV_DATA_FRESH", "EV_POSITION_FLAT"),
            reason="AI decided to wait despite bullish SMA due to low volatility",
            invalidation="Volatility surge",
        )

        comparison = run_ablation_comparison([snapshot], [ai_decision])
        self.assertEqual(comparison["total_evaluations"], 1)
        self.assertEqual(comparison["action_agreements"], 0)
        self.assertEqual(comparison["divergences_count"], 1)
        self.assertEqual(comparison["divergences"][0]["ai_action"], "WAIT")
        self.assertEqual(comparison["divergences"][0]["baseline_action"], "ENTER")


if __name__ == "__main__":
    unittest.main()
