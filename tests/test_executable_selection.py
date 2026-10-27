"""Offline regressions for fresh selection, with real SDK and fake HTTP only."""

import copy
import hashlib
import json
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import patch

import httpx2

from royin.agent import _entry_rows, _serialize_model_context, decide_role
from royin.config import RuntimeConfig
from royin.decision import MarketEntryProposal, validate_role_proposal
from royin.model_budget import ModelBudget
from royin.risk import entry_cost_context
from tests.test_agent_dossier import research_fixture
from tests.test_market_selection import enter_proposal


def mixed_batch(*, all_blocked=False):
    loaded, universe = research_fixture(2, with_reference=True)
    for symbol in loaded:
        if symbol == "ETHTMN" or all_blocked:
            snap, opp = loaded[symbol]
            cap = opp.execution_capacity.model_copy(update=dict(step_size=D(".00001")))
            loaded[symbol] = (snap, opp.model_copy(update=dict(execution_capacity=cap)))
    return loaded, universe


def proposal_for(loaded, symbol, *, action="WAIT", median=".012"):
    snap, opp = loaded[symbol]
    proposal = enter_proposal(snap)
    proposal.update(action=action, opportunity_sha256=opp.sha256,
        compared_symbols=list(loaded), feasible_symbols=[symbol for symbol, (a, b) in loaded.items()
            if entry_cost_context(a, b).get("capacity", {}).get("status") == "SELLABLE_WITH_BOUNDED_RESIDUAL"])
    proposal["forecast"].update(return_q50=median)
    return proposal


def validate(loaded, data, *, require_comparison=True):
    proposal = MarketEntryProposal.model_validate(data)
    snap, opp = loaded[proposal.symbol]
    return validate_role_proposal(proposal, role="ENTRY_ANALYST", snapshot=snap,
        position=None, opportunity=opp if proposal.action == "ENTER" else None,
        market_batch=loaded, horizon_bounds=(300, 14400), require_comparison=require_comparison)


async def sdk_selection(symbol, *, action="WAIT", median=".012", all_blocked=False):
    loaded, universe = mixed_batch(all_blocked=all_blocked)
    snap, opp = next(iter(loaded.values()))
    data = proposal_for(loaded, symbol, action=action, median=median)
    data['candidate_medians']=[[candidate,horizon,median]
        for candidate in data['feasible_symbols'] for horizon in (3600,10800)]
    for key in ('snapshot_sha256','opportunity_sha256'):
        data.pop(key)
    bodies, trace = [], {}

    async def provider(request):
        bodies.append(bytes(request.content))
        if len(bodies) == 1:
            message = dict(role="assistant", content=None, tool_calls=[dict(id="research-one", type="function",
                function=dict(name="read_market_snapshot", arguments=json.dumps(dict(symbols=list(loaded)))))])
        else:
            message = dict(role="assistant", content=json.dumps(data))
        return httpx2.Response(200, json=dict(id="offline", object="chat.completion", created=0,
            model="gpt-6-luna", choices=[dict(index=0, message=message, finish_reason="stop")],
            usage=dict(prompt_tokens=100, completion_tokens=50, total_tokens=150)))

    async def loader(_symbols):
        return loaded

    with tempfile.TemporaryDirectory() as directory:
        config = RuntimeConfig(BOXAPI_API_KEY="fake", LLM_COST_BUDGET="2.40",
            LLM_TOKEN_BUDGET=6000000, LLM_COST_CURRENCY="USD")
        budget = ModelBudget(config, Path(directory) / "budget.sqlite3")
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(provider),
            event_hooks={"request": [budget.before_request]}) as client:
            decision = await decide_role(snap, market_batch={snap.symbol: (snap, opp)},
                market_universe=universe, market_loader=loader, config=config, client=client,
                allowed_symbols=tuple(row.symbol for row in universe.markets),
                model_trace=trace, timeout_seconds=60, horizon_bounds=(300, 14400))
    return decision, trace, [json.loads(body) for body in bodies], bodies


class ExecutableSelectionTests(unittest.IsolatedAsyncioTestCase):
    def test_fixture_proves_fit_and_minimum_residual_failure_independently(self):
        loaded, _ = mixed_batch()
        costs = {symbol: entry_cost_context(*pair) for symbol, pair in loaded.items()}
        self.assertEqual(costs["BTCTMN"]["capacity"]["status"], "SELLABLE_WITH_BOUNDED_RESIDUAL")
        self.assertEqual(costs["ETHTMN"]["capacity"]["status"], "BLOCKED_MINIMUM_OR_RESIDUAL")
        self.assertGreater(D(costs["ETHTMN"]["capacity"]["worst_residual_mark_tmn"]), D(500))

    def test_blocked_wait_is_rejected_even_with_truthful_comparison_lists(self):
        loaded, _ = mixed_batch()
        with self.assertRaisesRegex(ValueError, "fresh feasible"):
            validate(loaded, proposal_for(loaded, "ETHTMN"))

    def test_guard_also_covers_direct_batches_with_rules(self):
        loaded, _ = mixed_batch()
        with self.assertRaisesRegex(ValueError, "fresh feasible"):
            validate(loaded, proposal_for(loaded, "ETHTMN"), require_comparison=False)

    def test_positive_forecast_cannot_authorize_a_blocked_candidate(self):
        loaded, _ = mixed_batch()
        with self.assertRaisesRegex(ValueError, "fresh feasible"):
            validate(loaded, proposal_for(loaded, "ETHTMN", action="ENTER"))

    def test_all_blocked_allows_diagnostic_wait_but_rejects_enter(self):
        loaded, _ = mixed_batch(all_blocked=True)
        validate(loaded, proposal_for(loaded, "ETHTMN"))
        with self.assertRaisesRegex(ValueError, "no proven execution capacity"):
            validate(loaded, proposal_for(loaded, "ETHTMN", action="ENTER"))

    def test_fit_enter_is_still_reachable_without_weakening_economics(self):
        loaded, _ = mixed_batch()
        validate(loaded, proposal_for(loaded, "BTCTMN", action="ENTER"))
        with self.assertRaisesRegex(ValueError, "central forecast"):
            validate(loaded, proposal_for(loaded, "BTCTMN", action="ENTER", median=".001"))

    def test_projection_retains_inventory_and_full_hash_but_excludes_blocked_features(self):
        loaded, _ = mixed_batch()
        context = dict(candidates=_entry_rows(loaded))
        original = copy.deepcopy(context)
        projected = json.loads(_serialize_model_context(context))
        self.assertEqual(projected["accepted_symbols"], ["BTCTMN", "ETHTMN"])
        self.assertEqual(projected["selectable_symbols"], ["BTCTMN"])
        self.assertEqual([row["symbol"] for row in projected["candidates"]], ["BTCTMN"])
        self.assertEqual(projected["execution_comparison"]["blocked"], ["ETHTMN"])
        full = json.dumps(context, sort_keys=True, separators=(",", ":"))
        self.assertEqual(projected["model_projection"]["full_dossier_sha256"], hashlib.sha256(full.encode()).hexdigest())
        self.assertEqual(context, original)

    def test_all_blocked_has_null_admission_hurdles_and_separate_unit_costs(self):
        loaded, _ = mixed_batch(all_blocked=True)
        projected = json.loads(_serialize_model_context(dict(candidates=_entry_rows(loaded))))
        self.assertEqual(projected["selection_scope"], "NO_PROVEN_EXECUTABLE_CANDIDATE")
        for row in projected["candidates"]:
            metrics = dict(zip(projected["model_projection"]["metric_columns"], row["metrics"], strict=True))
            self.assertIsNone(metrics["execution_cost_context"]["entry_hurdle_fraction"])
            self.assertIsNotNone(metrics["execution_cost_context"]["per_unit_hurdle_fraction"])

    def test_fit_label_without_cash_cost_is_never_promoted_to_selectable(self):
        loaded, _ = mixed_batch()
        rows = _entry_rows(loaded)
        del rows[0]["execution_cost_context"]["cash_break_even_reference_return_fraction"]
        projected = json.loads(_serialize_model_context(dict(candidates=rows)))
        self.assertEqual(projected["selectable_symbols"], [])
        self.assertIn("BTCTMN", projected["execution_comparison"]["unavailable"])

    async def test_actual_sdk_schema_excludes_blocked_symbol_hash_and_reference(self):
        with patch("httpx2.AsyncHTTPTransport.handle_async_request", side_effect=AssertionError("network forbidden")):
            decision, trace, requests, bodies = await sdk_selection("BTCTMN")
        self.assertEqual(decision.symbol, "BTCTMN")
        self.assertEqual(decision.action, "WAIT")
        self.assertEqual(trace["host_outcome"], "MODEL_DECISION")
        self.assertEqual(len(requests), 2)
        self.assertLessEqual(max(map(len, bodies)), 31744)
        final = next(tool["function"]["parameters"] for tool in requests[1]["tools"]
                     if tool["function"]["name"] == "final_result")
        self.assertEqual(final["properties"]["symbol"]["enum"], ["BTCTMN"])
        self.assertEqual(final["$defs"]["ReturnForecast"]["properties"]["symbol"]["enum"], ["BTCTMN"])
        self.assertEqual(final["properties"]["compared_symbols"]["items"]["enum"], ["BTCTMN", "ETHTMN"])
        self.assertEqual(final["properties"]["feasible_symbols"]["minItems"], 1)
        self.assertEqual(final["properties"]["feasible_symbols"]["items"]["enum"], ["BTCTMN"])
        self.assertNotIn("snapshot_sha256", final["properties"])
        self.assertNotIn("opportunity_sha256", final["properties"])
        self.assertEqual(trace["host_binding"]["snapshot_sha256"], decision.snapshot_sha256)
        self.assertEqual(len(final["$defs"]["ReturnForecast"]["properties"]["reference_price"]["enum"]), 1)

    async def test_provider_ignoring_schema_is_rejected_without_paid_retry(self):
        decision, trace, requests, _ = await sdk_selection("ETHTMN")
        self.assertEqual(decision.action, "WAIT")
        self.assertEqual(trace["host_outcome"], "HOST_FALLBACK")
        self.assertEqual(trace["host_validation_code"], "SELECTED_CANDIDATE_NOT_FEASIBLE")
        self.assertEqual(len(requests), 2)
        self.assertEqual(trace["context"]["candidates"][1]["symbol"], "ETHTMN")

    async def test_model_wait_is_distinct_from_host_rejection_and_no_capacity(self):
        _, below, _, _ = await sdk_selection("BTCTMN", median="-.001")
        self.assertEqual(below["selection_diagnostic"]["status"], "MODEL_WAIT_CENTRAL_NOT_ABOVE_COST")
        _, above, _, _ = await sdk_selection("BTCTMN")
        self.assertEqual(above["selection_diagnostic"]["status"], "MODEL_WAIT_OTHER_JUDGMENT")
        _, blocked, requests, _ = await sdk_selection("ETHTMN", all_blocked=True)
        self.assertEqual(blocked["selection_diagnostic"]["status"], "NO_PROVEN_EXECUTABLE_CANDIDATE")
        self.assertIsNone(blocked["selection_diagnostic"]["cash_hurdle_fraction"])
        schema = requests[1]["tools"][0]["function"]["parameters"]
        self.assertEqual(schema["properties"]["action"]["enum"], ["WAIT"])

    async def test_enter_still_survives_full_mock_sdk_path(self):
        decision, trace, requests, _ = await sdk_selection("BTCTMN", action="ENTER")
        self.assertEqual(decision.action, "ENTER", trace.get("host_validation_code"))
        self.assertEqual(trace["selection_diagnostic"]["status"], "MODEL_ENTER")
        self.assertEqual(len(requests), 2)


if __name__ == "__main__":
    unittest.main()
