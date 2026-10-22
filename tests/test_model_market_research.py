"""Model-directed research boundaries with synthetic provider traffic, never alpha evidence."""
import json
import unittest
from decimal import Decimal as D
from unittest.mock import AsyncMock

import httpx2

from royin.agent import decide_role
from royin.config import RuntimeConfig
from royin.decision import MarketCatalogCandidate, MarketResearchUniverse
from tests.test_market_selection import enter_proposal, opportunity, snapshot


class ModelResearchTests(unittest.IsolatedAsyncioTestCase):
    def test_screening_view_preserves_universe_and_explicit_units(self):
        universe = MarketResearchUniverse(catalog_sha256="c"*64,observed_at=8100,
            markets=(MarketCatalogCandidate(symbol="SOLTMN",price_tmn=D(101),
                turnover_tmn=D(299999999),return_24h=D(".012345")),))
        view = universe.screening_view()
        self.assertEqual(view["rows"],[["SOLTMN",299,"0.0123"]])
        self.assertEqual(universe.markets[0].turnover_tmn,D(299999999))
        self.assertIn("turnover_million_tmn_floor",view["columns"])

    async def run_case(self, *, selection=None, loaded_symbol="SOLTMN", skip_tool=False, bad_catalog=False, unavailable=()):
        symbols = ("BTCTMN","ETHTMN","DOGETMN","SOLTMN","ADATMN","LTCTMN","XLMTMN")
        universe = MarketResearchUniverse(catalog_sha256="c"*64,observed_at=8100,unavailable_symbols=unavailable,
            markets=tuple(MarketCatalogCandidate(symbol=s,price_tmn=D(101),turnover_tmn=D(200000000),
                return_24h=D(".01")) for s in symbols))
        anchor = snapshot("BTCTMN")
        chosen = snapshot(loaded_symbol)
        opp = opportunity()
        if bad_catalog:
            opp = opp.model_copy(update={"catalog_sha256":"d"*64})
        loader = AsyncMock(return_value={loaded_symbol:(chosen,opp)})
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
                allowed_symbols=symbols,model_trace=trace)
        return decision,trace,loader,bodies

    async def test_model_researches_outside_anchor_from_wider_universe_with_only_two_requests(self):
        decision,trace,loader,bodies = await self.run_case()
        self.assertEqual(decision.action,"ENTER")
        self.assertEqual(decision.symbol,"SOLTMN")
        loader.assert_awaited_once_with(("SOLTMN",))
        self.assertEqual(len(bodies),2)
        first = json.dumps(bodies[0]["messages"])
        self.assertIn("ADATMN",first)
        self.assertIn("LTCTMN",first)
        initial = next(row["content"] for row in bodies[0]["messages"] if row["role"] == "user")
        self.assertNotIn("BTCTMN",initial.split("Research selection context:")[0])
        self.assertEqual(len(trace["context"]["research_universe"]["markets"]),7)
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
