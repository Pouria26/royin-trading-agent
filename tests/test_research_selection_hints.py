"""Preselection execution/data triage with no HTTP, orders or new budget."""
import copy
import unittest
from decimal import Decimal as D
from types import SimpleNamespace

from royin.decision import MarketCatalogCandidate, MarketResearchUniverse
from royin.risk import MarketRules
from scripts.run_paper_trader import research_control_symbols, research_selection_hints


class ResearchSelectionHintTests(unittest.TestCase):
    def test_controls_reserve_only_two_observed_feasible_slots_without_changing_catalog(self):
        symbols=('BTCTMN','PUMPTMN','PEPETMN','XRPTMN','ETHTMN','SOLTMN')
        rows=tuple(SimpleNamespace(symbol=s,turnover_tmn=D(200000000)) for s in symbols)
        hints={s:dict(lot_hint='FIT_ESTIMATE',last_research_status='DATA_OK',last_capacity_status='FIT',
                      last_research_at=8700,last_cash_hurdle=D('.01'),last_trend='BEARISH') for s in symbols}
        hints['BTCTMN'].update(last_trend='BULLISH',last_cash_hurdle=D('.02'))
        hints['PUMPTMN']['last_cash_hurdle']=D('.009')
        hints['XRPTMN']['last_capacity_status']='BLOCKED'
        hints['ETHTMN']['lot_hint']='NO_FIT_FOUND'
        hints['SOLTMN']['last_research_status']='HISTORY_PARSE_FAILED'
        original=copy.deepcopy(hints)
        self.assertEqual(research_control_symbols(rows,hints),('BTCTMN','PUMPTMN'))
        self.assertEqual(research_control_symbols(rows,hints,unavailable_symbols=('BTCTMN',)),('PUMPTMN','PEPETMN'))
        self.assertEqual(research_control_symbols(rows,{}),())
        self.assertEqual(hints,original)
        self.assertEqual(tuple(row.symbol for row in rows),symbols)

    def test_controls_must_be_distinct_available_universe_members_and_retain_all_markets(self):
        rows=tuple(MarketCatalogCandidate(symbol=s,price_tmn=D(1),turnover_tmn=D(100000000))
                   for s in ('BTCTMN','ETHTMN','SOLTMN'))
        params=dict(catalog_sha256='a'*64,observed_at=9000,markets=rows)
        for controls,unavailable in [(('BTCTMN','BTCTMN'),()),(('TONTMN',),()),
                                     (('BTCTMN',),('BTCTMN',)),(('BTCTMN','ETHTMN','SOLTMN'),())]:
            with self.subTest(controls=controls),self.assertRaises(ValueError):
                MarketResearchUniverse(**params,control_symbols=controls,unavailable_symbols=unavailable)
        view=MarketResearchUniverse(**params,control_symbols=('BTCTMN','SOLTMN')).screening_view()
        self.assertEqual(view['model_selection_limit'],8)
        self.assertEqual(view['host_research_controls'],['BTCTMN','SOLTMN'])
        self.assertEqual(len(view['rows']),3)

    def hints(self,traces=()):
        catalog={"ETHTMN":dict(price="624000000"),"BTCTMN":dict(price="21500000000")}
        rules={s:MarketRules(s,s[:-3],"TMN",D(1),step,D(50000),step,D(".0025"),D(".003"))
               for s,step in [("ETHTMN",D(".00001")),("BTCTMN",D(".00000001"))]}
        return research_selection_hints(catalog,rules,list(traces),observed_at=9000,
            debit_ceiling=D(150000),minimum_notional=D(100000),reserve_exit_base_fee=True)

    def test_coarse_lots_are_visible_before_research_without_banning_any_symbol(self):
        hints=self.hints()
        self.assertEqual(hints["ETHTMN"]["lot_hint"],"NO_FIT_FOUND")
        self.assertEqual(hints["BTCTMN"]["lot_hint"],"NO_FIT_FOUND")
        universe=MarketResearchUniverse(catalog_sha256="a"*64,observed_at=9000,
            markets=tuple(MarketCatalogCandidate(symbol=s,price_tmn=D(1),turnover_tmn=D(100000000),**h)
                          for s,h in hints.items()))
        view=universe.screening_view()
        self.assertEqual(view['selection_hints']['lot_fit'],[])
        self.assertEqual(view['selection_hints']['lot_no_fit'],[0,1])
        self.assertEqual(len(view['rows']),2)
        self.assertEqual(view['unavailable_for_current_cutoff'],[])

    def test_recent_errors_survive_from_traces_and_expire_without_resetting_history(self):
        traces=[dict(model_trace=dict(context=dict(cutoff=8100,candidates=[]),
                    research_rejections=[dict(symbol="ETHTMN",reason="HISTORY_PARSE_FAILED")]))]
        original=copy.deepcopy(traces)
        hints=self.hints(traces)
        self.assertEqual(hints['ETHTMN']['last_research_status'],'HISTORY_PARSE_FAILED')
        self.assertEqual(traces,original)
        traces[0]['model_trace']['context']['cutoff']=5000
        self.assertNotIn('last_research_status',self.hints(traces)['ETHTMN'])
        traces[0]['model_trace']['context']['cutoff']=9001
        self.assertNotIn('last_research_status',self.hints(traces)['ETHTMN'])

    def test_new_success_replaces_previous_failure_and_foreign_rows_cannot_extend_universe(self):
        traces=[dict(model_trace=dict(context=dict(cutoff=8100,candidates=[]),
                    research_rejections=[dict(symbol='ETHTMN',reason='HISTORY_PARSE_FAILED')])),
                dict(model_trace=dict(context=dict(cutoff=8700,candidates=[dict(symbol='ETHTMN'),dict(symbol='TONTMN')])))]
        hints=self.hints(traces)
        self.assertEqual(hints['ETHTMN']['last_research_status'],'DATA_OK')
        self.assertEqual(set(hints),{'ETHTMN','BTCTMN'})

    def test_actual_capacity_and_cost_are_visible_with_age_and_cleared_after_new_failure(self):
        candidate=dict(symbol='BTCTMN',evidences=['EV_TREND_BULLISH'],execution_cost_context=dict(
            cash_break_even_reference_return_fraction='.012345',capacity=dict(status='SELLABLE_WITH_BOUNDED_RESIDUAL')))
        traces=[dict(model_trace=dict(context=dict(cutoff=8100,candidates=[candidate])))]
        hints=self.hints(traces)
        row=MarketCatalogCandidate(symbol='BTCTMN',price_tmn=D(100),turnover_tmn=D(100000000),**hints['BTCTMN'])
        view=MarketResearchUniverse(catalog_sha256='a'*64,observed_at=9000,markets=(row,)).screening_view()
        self.assertEqual(view['selection_hints']['recent_candidates'],[[0,15,1,123,1]])
        traces.append(dict(model_trace=dict(context=dict(cutoff=8700,candidates=[]),
            research_rejections=[dict(symbol='BTCTMN',reason='SPREAD_TOO_WIDE')])))
        newer=self.hints(traces)['BTCTMN']
        self.assertNotIn('last_capacity_status',newer)
        self.assertNotIn('last_cash_hurdle',newer)
        self.assertEqual(newer['last_research_status'],'SPREAD_TOO_WIDE')
