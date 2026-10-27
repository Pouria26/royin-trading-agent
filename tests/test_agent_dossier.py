"""Actual SDK request-size regressions; synthetic provider and isolated budget only."""

import hashlib
import json
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx2

from royin.agent import _serialize_model_context, decide_role
from royin.config import RuntimeConfig
from royin.decision import (
    EntryOpportunityContext,
    MarketCatalogCandidate,
    MarketResearchUniverse,
    ResearchExecutionCapacity,
)
from royin.features import extract_features
from royin.market_data import Candle, CandleSeries
from royin.model_budget import ModelBudget
from tests.test_market_selection import enter_proposal


def research_fixture(count, *, with_reference=False):
    symbols = ("BTCTMN", "ETHTMN", "SOLTMN", "ADATMN", "DOGETMN", "XRPTMN", "BNBTMN", "TRXTMN", "LTCTMN", "XLMTMN")[:count]
    loaded = {}
    for index, symbol in enumerate(symbols):
        base = D(73456789+index*417891)
        candles = []
        for bar in range(-160 if with_reference else 0,40):
            slope=D("-.000287") if with_reference and index%2 else D(".000321")
            close = base*(1+D(bar)*slope)
            opened = close*(D("1.000013") if bar%3 else D(".999897"))
            high=close*(D("1.005") if with_reference and index%3 else D("1.00137"))
            volume=D(200) if with_reference and index%3==0 and bar==39 else D("19.1843")+D(bar)*D(".0317")
            candles.append(Candle(1792852200+bar*300, opened, high,close*D(".99863"), close,volume))
        snap = extract_features(CandleSeries(tuple(candles[-40:]),300),symbol,cutoff=1792864200,
            reference_series=CandleSeries(tuple(candles),300) if with_reference else None)
        cap = ResearchExecutionCapacity(debit_ceiling_tmn=D(150000),tick_size=D(1),step_size=D(".00000001"),
            min_notional=D(100000),min_quantity=D(".00000001"),maker_fee_rate=D(".0025"),
            taker_fee_rate=D(".003"),reserve_exit_base_fee=True)
        opp = EntryOpportunityContext(spread_pct=D(".001"),round_trip_fee_pct=D(".006"),
            bid_depth_tmn=D("43827469.8175"),ask_depth_tmn=D("47817492.1938"),
            catalog_sha256="c"*64,catalog_received_at=1792864201,candle_received_at=1792864202,
            depth_received_at=1792864203,observed_at=1792864205,best_bid=snap.last_close*D(".9995"),
            best_ask=snap.last_close*D("1.0005"),asset_return_24h=D(".0172394"),
            relative_strength_24h=D(".01976532749"),execution_capacity=cap)
        loaded[symbol] = (snap,opp)
    all_symbols = (*symbols,*(f"COIN{i}TMN" for i in range(57-count)))
    universe = MarketResearchUniverse(catalog_sha256="c"*64,observed_at=1792864205,
        markets=tuple(MarketCatalogCandidate(symbol=s,price_tmn=D(73456789),turnover_tmn=D(217891827),
            return_24h=D(".0172394"),research_requests=7,accepted_research_count=5) for s in all_symbols))
    return loaded,universe


async def sdk_case(count, *, legacy=False, with_selection_hints=False, unavailable_proxy=False, with_reference=False,
                   with_controls=False, feasible_override=None, with_rejected_request=False,omit_output_fields=(), model_metadata=None,provider_outputs=None):
    loaded,universe = research_fixture(count,with_reference=with_reference)
    if unavailable_proxy:
        # A second researched candidate may have flat closed bars with no defined volume proxy.
        snap, opp = list(loaded.values())[-1]
        snap.evidences.clear()
        snap.evidences.update(EV_DATA_FRESH="Closed data", EV_VOLUME_PRESSURE_UNAVAILABLE=(
            "20 closed-bar close-location volume proxy=None; range [-1,1]; "
            "not measured buyer/seller aggressor flow or net capital inflow"))
        canonical = snap.to_canonical_dict()
        digest = hashlib.sha256(json.dumps(canonical,sort_keys=True,separators=(",",":")).encode()).hexdigest()
        from dataclasses import replace
        loaded[snap.symbol] = (replace(snap,snapshot_sha256=digest),opp)
    if with_selection_hints:
        universe=universe.model_copy(update=dict(markets=tuple(row.model_copy(update=dict(
            lot_hint="FIT_ESTIMATE" if i%3 else "NO_FIT_FOUND",last_research_status="DATA_OK" if with_reference else "HISTORY_PARSE_FAILED",
            last_research_at=universe.observed_at-900,
            **(dict(last_capacity_status='FIT' if i%3 else 'BLOCKED',last_cash_hurdle=D('.012345'),
                    last_trend='BULLISH') if with_reference else {}))) for i,row in enumerate(universe.markets))))
    selected=list(loaded)
    if with_controls:
        universe=universe.model_copy(update=dict(control_symbols=tuple(selected[-2:])))
        selected=selected[:-2]
    rejected_symbol=universe.markets[-1].symbol
    if with_rejected_request:
        selected.append(rejected_symbol)
    snap,opp = next(iter(loaded.values()))
    proposal = enter_proposal(snap)
    proposal["opportunity_sha256"] = opp.sha256
    proposal["compared_symbols"] = list(loaded)
    from royin.risk import entry_cost_context
    proposal['feasible_symbols'] = [s for s,(a,b) in loaded.items() if
        entry_cost_context(a,b).get('capacity',{}).get('status')=='SELLABLE_WITH_BOUNDED_RESIDUAL']
    if feasible_override is not None:
        proposal['feasible_symbols']=feasible_override
    proposal['candidate_medians']=[[symbol,horizon,proposal['forecast']['return_q50']]
        for symbol in proposal['feasible_symbols'] for horizon in (3600,10800)]
    for key in ('snapshot_sha256','opportunity_sha256'):
        proposal.pop(key)
    proposal.update(model_metadata or {})
    for field in omit_output_fields:
        proposal.pop(field)
    bodies,received = [],[]
    async def capture(request):
        bodies.append(bytes(request.content))
    async def handler(request):
        received.append(bytes(request.content))
        if len(received)==1:
            message = dict(role="assistant",content=None,tool_calls=[dict(id="research1",type="function",
                function=dict(name="read_market_snapshot",arguments=json.dumps({"symbols":selected})))])
        else:
            message = dict(role="assistant",content=json.dumps(proposal))
            if provider_outputs is not None:
                provider_outputs.append(message['content'])
        return httpx2.Response(200,json=dict(id="synthetic",object="chat.completion",created=0,
            model="gpt-6-luna",choices=[dict(index=0,message=message,finish_reason="stop")],
            usage=dict(prompt_tokens=100,completion_tokens=50,total_tokens=150)))
    trace = {}
    async def load_selected(_symbols):
        if with_rejected_request:
            trace['research_rejections']=[dict(symbol=rejected_symbol,reason='SPREAD_TOO_WIDE')]
        return loaded
    with tempfile.TemporaryDirectory() as directory:
        config = RuntimeConfig(BOXAPI_API_KEY="fake",LLM_COST_BUDGET="2.40",
            LLM_TOKEN_BUDGET=6000000,LLM_COST_CURRENCY="USD")
        budget = ModelBudget(config,Path(directory)/"budget.sqlite3")
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler),
                event_hooks={"request":[capture,budget.before_request]}) as client:
            options = dict(market_batch={snap.symbol:(snap,opp)},market_universe=universe,
                market_loader=AsyncMock(side_effect=load_selected),client=client,config=config,
                allowed_symbols=tuple(row.symbol for row in universe.markets),model_trace=trace,timeout_seconds=60,
                horizon_bounds=(300,14400))
            if legacy:
                with patch("royin.agent._serialize_model_context",side_effect=lambda context:json.dumps(context)):
                    result = await decide_role(snap,**options)
            else:
                result = await decide_role(snap,**options)
    return result,trace,bodies,received


class AgentDossierTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejected_requested_symbol_stays_in_trace_but_not_final_choices_and_enter_remains_valid(self):
        result,trace,bodies,sent=await sdk_case(2,with_rejected_request=True)
        self.assertEqual(len(sent),2)
        self.assertEqual(result.action,'ENTER',trace.get('host_validation_code'))
        self.assertEqual(trace['host_outcome'],'MODEL_DECISION')
        tool=json.loads(next(m['content'] for m in json.loads(bodies[1])['messages'] if m['role']=='tool'))
        self.assertEqual(tool['accepted_symbols'],['BTCTMN','ETHTMN'])
        self.assertEqual(tool['horizon_bounds'],[300,14400])
        self.assertEqual(tool['output_bindings'],dict(role='ENTRY_ANALYST',cutoff=trace['context']['cutoff'],position_sha256=None))
        rejected=tool['research_rejections'][0]['symbol']
        self.assertNotIn(rejected,tool['accepted_symbols'])
        self.assertIn(rejected,trace['context']['requested_symbols'])
        self.assertIn(rejected,trace['context']['researched_symbols'])
        for name in ('requested_symbols','researched_symbols','host_research_control_symbols'):
            self.assertNotIn(name,tool)
        output=next(t['function'] for t in json.loads(bodies[1])['tools'] if t['function']['name']=='final_result')
        comparison=output['parameters']['properties']['compared_symbols']
        self.assertEqual(comparison['items']['enum'],tool['accepted_symbols'])
        self.assertEqual((comparison['minItems'],comparison['maxItems']),(2,2))

    async def test_required_root_bindings_omitted_by_model_are_not_injected_from_template(self):
        for omitted in ('role','cutoff'):
            with self.subTest(omitted=omitted):
                result,trace,_,sent=await sdk_case(2,omit_output_fields=(omitted,))
                self.assertEqual(len(sent),2)
                self.assertEqual(result.action,'WAIT')
                self.assertEqual(trace['host_outcome'],'HOST_FALLBACK')
                self.assertEqual(trace['host_validation_code'],'UnexpectedModelBehavior')

    async def test_omitting_btc_from_two_feasible_markets_is_a_classified_host_rejection(self):
        result,trace,_,sent=await sdk_case(2,feasible_override=['ETHTMN'])
        self.assertEqual(len(sent),2)
        self.assertEqual(result.action,'WAIT')
        self.assertEqual(trace['host_outcome'],'HOST_FALLBACK')
        self.assertEqual(trace['host_validation_code'],'COMPARISON_CAPACITY_MISMATCH')

    async def test_projected_admission_hurdle_uses_cash_debit_not_smaller_per_unit_number(self):
        result,trace,bodies,sent=await sdk_case(10,with_selection_hints=True,with_reference=True,with_controls=True)
        self.assertEqual(len(sent),2,trace.get('host_budget_code'))
        self.assertEqual(result.action,'ENTER')
        tool=json.loads(next(m['content'] for m in json.loads(bodies[1])['messages'] if m['role']=='tool'))
        projection=tool['model_projection']
        distinct=False
        for row,full in zip(tool['candidates'],trace['context']['candidates'],strict=True):
            metrics=dict(zip(projection['metric_columns'],row['metrics'],strict=True))
            cost=metrics['execution_cost_context']
            exact=full['execution_cost_context']
            per_unit=D(exact['break_even_reference_return_fraction'])
            effective=D(exact.get('cash_break_even_reference_return_fraction',str(per_unit)))
            self.assertEqual(cost['entry_hurdle_fraction'],format(effective,'.10g'))
            self.assertNotIn('per_unit_hurdle_fraction',cost)
            self.assertNotIn('capacity',cost)
            self.assertNotIn('cash_break_even_reference_return_fraction',cost)
            self.assertNotIn('break_even_reference_return_fraction',cost)
            distinct |= effective > per_unit
        self.assertTrue(distinct,'Fixture must expose a cost difference that can change admission')

    async def test_control_research_refreshes_same_ten_slots_and_keeps_actual_sdk_budget(self):
        result,trace,bodies,sent=await sdk_case(10,with_selection_hints=True,with_reference=True,with_controls=True)
        self.assertEqual(len(sent),2,trace.get('host_budget_code'))
        self.assertEqual(result.action,'ENTER',trace.get('host_validation_code'))
        self.assertLessEqual(max(map(len,bodies)),32768-1024)
        context=trace['context']
        self.assertEqual(len(context['requested_symbols']),8)
        self.assertEqual(context['host_research_control_symbols'],['LTCTMN','XLMTMN'])
        self.assertEqual(context['researched_symbols'],context['requested_symbols']+['LTCTMN','XLMTMN'])
        self.assertEqual([c['symbol'] for c in context['candidates']],sorted(context['researched_symbols']))
        tool=next(t['function'] for t in json.loads(bodies[0])['tools'] if t['function']['name']=='read_market_snapshot')
        self.assertEqual(tool['parameters']['properties']['symbols']['maxItems'],8)

    async def test_full_reference_and_recent_capacity_fit_unchanged_real_sdk_request_bound(self):
        result,trace,bodies,sent=await sdk_case(10,with_selection_hints=True,with_reference=True)
        self.assertEqual(len(sent),2,dict(sizes=[len(b) for b in bodies],code=trace.get('host_budget_code')))
        self.assertEqual(result.action,'ENTER',trace.get('host_validation_code'))
        self.assertLessEqual(max(map(len,bodies)),32768-1024)
        exact=trace['context']['candidates'][0]['historical_return_reference']
        self.assertEqual([v['segments'] for v in exact['horizons']],[66,16,5])
        tool=json.loads(next(m['content'] for m in json.loads(bodies[1])['messages'] if m['role']=='tool'))
        columns=tool['model_projection']['metric_columns']
        metrics=dict(zip(columns,tool['candidates'][0]['metrics'],strict=True))
        self.assertEqual(tool['model_projection']['version'],'ENTRY_DOSSIER_COMPACT_V9')
        self.assertEqual([v['n'] for v in metrics['historical_return_reference']],[66,16,5])

    async def test_unavailable_proxy_in_one_candidate_does_not_abort_other_candidate_decision(self):
        result,trace,bodies,sent = await sdk_case(2,unavailable_proxy=True)
        self.assertEqual(len(sent),2)
        self.assertEqual(result.action,"ENTER",trace.get("host_validation_code"))
        self.assertEqual(trace["host_outcome"],"MODEL_DECISION")
        full = trace["context"]["candidates"][-1]
        self.assertIn("EV_VOLUME_PRESSURE_UNAVAILABLE",full["volume_pressure_proxy"])
        tool = json.loads(next(m["content"] for m in json.loads(bodies[1])["messages"] if m["role"]=="tool"))
        row = tool["candidates"][-1]
        values = dict(zip(tool["model_projection"]["metric_columns"],row["metrics"],strict=True))
        self.assertEqual(values["volume_pressure_proxy"],{"EV_VOLUME_PRESSURE_UNAVAILABLE":None})
        self.assertEqual(row["snapshot_sha256"],full["snapshot_sha256"])
        self.assertEqual(row["evidences"],full["evidences"])

    async def test_full_universe_hints_fit_actual_sdk_and_do_not_remove_candidates(self):
        result,trace,bodies,sent=await sdk_case(10,with_selection_hints=True)
        self.assertEqual(len(sent),2,dict(sizes=[len(b) for b in bodies],code=trace.get('host_budget_code')))
        self.assertEqual(result.action,"ENTER",trace.get('host_validation_code'))
        self.assertLessEqual(max(map(len,bodies)),32768-1024)
        view=trace['context']['research_view']
        self.assertEqual(len(view['rows']),57)
        self.assertTrue(view['selection_hints']['lot_fit'])
        self.assertEqual(view['unavailable_for_current_cutoff'],[])

    async def test_real_sdk_nine_and_ten_candidates_fit_unchanged_budget_where_legacy_did_not(self):
        for count in (9,10):
            with self.subTest(count=count):
                old,_,old_bodies,old_sent = await sdk_case(count,legacy=True)
                self.assertEqual(len(old_bodies),2)
                self.assertGreater(len(old_bodies[1]),32768-1024)
                self.assertEqual(len(old_sent),1)
                self.assertEqual(old.action,"WAIT")
                result,trace,bodies,received = await sdk_case(count)
                self.assertEqual(len(received),2)
                self.assertEqual([len(body) for body in bodies], [len(body) for body in received])
                self.assertEqual(result.action,"ENTER",trace)
                self.assertEqual(trace["host_outcome"],"MODEL_DECISION")
                self.assertEqual(len(trace["context"]["candidates"]),count)
                self.assertLessEqual(max(map(len,bodies)),32768-1024)
                tool = json.loads(next(message["content"] for message in json.loads(bodies[1])["messages"]
                    if message["role"] == "tool"))
                full = {key:value for key,value in trace["context"].items()
                    if key not in ("research_universe","research_view")}
                self.assertEqual(tool["model_projection"]["full_dossier_sha256"],
                    hashlib.sha256(json.dumps(full,sort_keys=True,separators=(",",":")).encode()).hexdigest())
                self.assertEqual(tool["batch_sha256"],trace["context"]["batch_sha256"])
                for compact,exact in zip(tool["candidates"],full["candidates"],strict=True):
                    for key in ("symbol","snapshot_sha256","opportunity_sha256","last_close"):
                        self.assertEqual(compact[key],exact[key])
                    columns = tool["model_projection"]
                    self.assertEqual(set(compact['evidences'])|set(columns.get('common_evidence_ids',[])),set(exact['evidences']))
                    metrics = dict(zip(columns["metric_columns"],compact["metrics"],strict=True))
                    cost = metrics["execution_cost_context"]
                    scenarios = exact["execution_cost_context"]["capacity"]["scenarios"]
                    self.assertEqual(len(scenarios),4)  # Exact host trace was not compacted or mutated.
                    self.assertTrue(all(case["sellable"] for case in scenarios))
                    self.assertIn(exact['symbol'],tool['execution_comparison']['feasible'])
                    self.assertNotIn('capacity',cost)

    def test_single_role_and_snapshot_serialization_preserve_legacy_data(self):
        context = dict(role="POSITION_REVIEWER",quantity=".0012345678912345",evidences=["EV_POSITION_LONG"])
        self.assertEqual(json.loads(_serialize_model_context(context)),context)


if __name__ == "__main__":
    unittest.main()
