"""Model-directed research boundaries with synthetic provider traffic, never alpha evidence."""
import json
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx2

from royin.agent import RoleRunEnvelope, decide_role
from royin.config import RuntimeConfig
from royin.decision import MarketCatalogCandidate, MarketResearchUniverse
from royin.model_budget import BudgetBlocked, ModelBudget
from tests.test_market_selection import enter_proposal, opportunity, snapshot


class ModelResearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_current_research_must_fit_candle_before_envelope_claim_or_model_http(self):
        with tempfile.TemporaryDirectory() as temp:
            config = RuntimeConfig(BOXAPI_API_KEY="fake",LLM_COST_BUDGET="2.40",
                LLM_TOKEN_BUDGET=6000000,LLM_COST_CURRENCY="USD")
            budget = ModelBudget(config,Path(temp)/"budget.sqlite3")
            budget.reserve()
            envelope = RoleRunEnvelope(budget)
            snap = snapshot("BTCTMN")
            universe = MarketResearchUniverse(catalog_sha256="c"*64,observed_at=8149,
                markets=(MarketCatalogCandidate(symbol="BTCTMN",price_tmn=D(101),turnover_tmn=D(200000000)),))
            trace = {}
            with patch("time.time",return_value=8149),patch("royin.agent.decide",new_callable=AsyncMock,
                    side_effect=AssertionError("Late research reached the model")) as model, \
                 self.assertRaisesRegex(BudgetBlocked,"CLOSED_CANDLE_TIME"):
                await decide_role(snap,market_batch={snap.symbol:(snap,opportunity())},
                    market_universe=universe,market_loader=AsyncMock(),config=config,
                    budget=budget,run_envelope=envelope,allowed_symbols=(snap.symbol,),
                    timeout_seconds=60,model_trace=trace)
            model.assert_not_awaited()
            self.assertEqual(envelope.agent_runs,0)
            self.assertEqual(envelope.http_attempts,0)
            self.assertEqual(trace["host_outcome"],"HOST_DEFERRED")

    def test_screening_view_preserves_universe_and_explicit_units(self):
        universe = MarketResearchUniverse(catalog_sha256="c"*64,observed_at=8100,
            markets=(MarketCatalogCandidate(symbol="SOLTMN",price_tmn=D(101),
                turnover_tmn=D(299999999),return_24h=D(".012345")),))
        view = universe.screening_view()
        self.assertEqual(view["rows"],[["SOLTMN",299,"0.0123",0,0]])
        self.assertEqual(universe.markets[0].turnover_tmn,D(299999999))
        self.assertIn("turnover_million_tmn_floor",view["columns"])

    async def run_case(self, *, selection=None, loaded_symbol="SOLTMN", skip_tool=False, bad_catalog=False, unavailable=(), timeout=30, load_all=False):
        symbols = ("BTCTMN","ETHTMN","DOGETMN","SOLTMN","ADATMN","LTCTMN","XLMTMN","XRPTMN","BNBTMN","TRXTMN","BCHTMN")
        universe = MarketResearchUniverse(catalog_sha256="c"*64,observed_at=8100,unavailable_symbols=unavailable,
            markets=tuple(MarketCatalogCandidate(symbol=s,price_tmn=D(101),turnover_tmn=D(200000000),
                return_24h=D(".01")) for s in symbols))
        anchor = snapshot("BTCTMN")
        chosen = snapshot(loaded_symbol)
        opp = opportunity()
        if bad_catalog:
            opp = opp.model_copy(update={"catalog_sha256":"d"*64})
        loaded = {symbol:(snapshot(symbol),opp) for symbol in selection} if load_all else {loaded_symbol:(chosen,opp)}
        loader = AsyncMock(return_value=loaded)
        proposal = enter_proposal(anchor if skip_tool else chosen)
        bodies = []
        async def handler(request):
            bodies.append(json.loads(request.content))
            if len(bodies) == 1 and not skip_tool:
                message = dict(role="assistant",content=None,tool_calls=[dict(id="research1",type="function",
                    function=dict(name="read_market_snapshot",arguments=json.dumps({"symbols":selection or ["SOLTMN"]})))])
            else:
                message = dict(role="assistant",content=json.dumps(proposal))
            return httpx2.Response(200,json=dict(id="synthetic",object="chat.completion",created=0,
                model="gpt-6-luna",choices=[dict(index=0,message=message,finish_reason="stop")],
                usage=dict(prompt_tokens=100,completion_tokens=50,total_tokens=150)))
        trace = {}
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
            decision = await decide_role(anchor,market_batch={anchor.symbol:(anchor,opportunity())},
                market_universe=universe,market_loader=loader,client=client,config=RuntimeConfig(BOXAPI_API_KEY="fake"),
                allowed_symbols=symbols,model_trace=trace,timeout_seconds=timeout)
        return decision,trace,loader,bodies

    async def test_model_researches_outside_anchor_from_wider_universe_with_only_two_requests(self):
        decision,trace,loader,bodies = await self.run_case()
        self.assertEqual(decision.action,"ENTER")
        self.assertEqual(decision.symbol,"SOLTMN")
        loader.assert_awaited_once_with(("SOLTMN",))
        self.assertEqual(len(bodies),2)
        tool = next(t["function"] for t in bodies[0]["tools"]
                    if t["function"]["name"] == "read_market_snapshot")
        self.assertEqual(tool["parameters"]["required"],["symbols"])
        self.assertEqual(set(tool["parameters"]["properties"]),{"symbols"})
        self.assertEqual(tool["parameters"]["properties"]["symbols"]["type"],"array")
        first = json.dumps(bodies[0]["messages"])
        self.assertIn("ADATMN",first)
        self.assertIn("LTCTMN",first)
        initial = next(row["content"] for row in bodies[0]["messages"] if row["role"] == "user")
        self.assertNotIn("BTCTMN",initial.split("Research selection context:")[0])
        self.assertEqual(len(trace["context"]["research_universe"]["markets"]),11)
        self.assertEqual(trace["context"]["requested_symbols"],["SOLTMN"])
        self.assertEqual([row["symbol"] for row in trace["context"]["candidates"]],["SOLTMN"])
        self.assertEqual(trace["host_outcome"],"MODEL_DECISION")

    async def test_outside_and_duplicate_selections_cannot_start_public_research(self):
        for selected in (["TONTMN"],["SOLTMN","SOLTMN"],["https://attacker.invalid"]):
            with self.subTest(selected=selected):
                decision,trace,loader,_ = await self.run_case(selection=selected)
                self.assertEqual(decision.action,"WAIT")
                self.assertEqual(trace["host_outcome"],"HOST_FALLBACK")
                loader.assert_not_awaited()

    async def test_ten_distinct_model_choices_are_admitted_but_eleven_never_reach_loader(self):
        symbols = ["BTCTMN","ETHTMN","DOGETMN","SOLTMN","ADATMN","LTCTMN","XLMTMN","XRPTMN","BNBTMN","TRXTMN"]
        decision,trace,loader,_ = await self.run_case(selection=symbols,timeout=60,load_all=True)
        self.assertEqual(trace["host_outcome"],"MODEL_DECISION")
        self.assertEqual(decision.symbol,"SOLTMN")
        loader.assert_awaited_once_with(tuple(symbols))
        self.assertEqual(len(trace["context"]["candidates"]),10)
        _,trace,loader,_ = await self.run_case(selection=[*symbols,"BCHTMN"])
        self.assertEqual(trace["host_outcome"],"HOST_FALLBACK")
        loader.assert_not_awaited()

    async def test_research_timeout_stays_bounded_and_coverage_counters_reject_bool(self):
        with self.assertRaises(ValueError):
            await self.run_case(timeout=61)
        for field in ("research_requests","accepted_research_count"):
            with self.subTest(field=field),self.assertRaises(ValueError):
                MarketCatalogCandidate(symbol="SOLTMN",price_tmn=D(101),turnover_tmn=D(200000000),**{field:True})

    async def test_known_bad_current_data_cannot_be_requested_again(self):
        decision,trace,loader,_ = await self.run_case(selection=["SOLTMN"],unavailable=("SOLTMN",))
        self.assertEqual(decision.action,"WAIT")
        self.assertEqual(trace["host_outcome"],"HOST_FALLBACK")
        loader.assert_not_awaited()

    async def test_final_decision_cannot_skip_model_selected_research(self):
        decision,trace,loader,_ = await self.run_case(skip_tool=True)
        self.assertEqual(decision.action,"WAIT")
        self.assertEqual(trace["host_outcome"],"HOST_FALLBACK")
        loader.assert_not_awaited()

    async def test_loader_cannot_substitute_unrequested_market_or_changed_catalog(self):
        for kwargs in (dict(loaded_symbol="ETHTMN"),dict(bad_catalog=True)):
            with self.subTest(kwargs=kwargs):
                decision,trace,loader,_ = await self.run_case(**kwargs)
                self.assertEqual(decision.action,"WAIT")
                self.assertEqual(trace["host_outcome"],"HOST_FALLBACK")
                loader.assert_awaited_once()

    async def test_research_money_and_catalog_contract_reject_float_and_duplicate_rows(self):
        with self.assertRaises(ValueError):
            MarketCatalogCandidate(symbol="BTCTMN",price_tmn=1.2,turnover_tmn=D(100))
        row = MarketCatalogCandidate(symbol="BTCTMN",price_tmn=D(100),turnover_tmn=D(200000000))
        with self.assertRaises(ValueError):
            MarketResearchUniverse(catalog_sha256="c"*64,observed_at=8100,markets=(row,row))
