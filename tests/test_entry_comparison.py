"""The model receives named current eligibility facts, never a stale-hint classification."""
import copy
import json
import unittest

from royin.agent import _entry_rows, _serialize_model_context
from tests.test_agent_dossier import research_fixture


class EntryComparisonTests(unittest.TestCase):
    def test_two_fit_candidates_survive_permutation_and_rejected_symbols_stay_distinct(self):
        batch,_=research_fixture(4,with_reference=True)
        rows=_entry_rows(batch)
        for row in rows:
            row['execution_cost_context']['capacity']['status']='BLOCKED_MINIMUM_OR_RESIDUAL'
        for row in rows:
            if row['symbol'] in ('BTCTMN','ETHTMN'):
                row['execution_cost_context']['capacity']['status']='SELLABLE_WITH_BOUNDED_RESIDUAL'
        context=dict(candidates=rows,research_rejections=[dict(symbol='XRPTMN',reason='SPREAD_TOO_WIDE')],
                     old_hints=dict(BTCTMN='BLOCKED',XRPTMN='FIT'))
        original=copy.deepcopy(context)
        facts=json.loads(_serialize_model_context(context))['execution_comparison']
        self.assertEqual(set(facts['feasible']),{'BTCTMN','ETHTMN'})
        self.assertEqual(set(facts['blocked']),{'SOLTMN','ADATMN'})
        self.assertEqual(facts['research_rejected'],[dict(symbol='XRPTMN',reason='SPREAD_TOO_WIDE')])
        self.assertNotIn('XRPTMN',facts['feasible'])
        self.assertEqual(context,original)
        context['candidates']=rows[::-1]
        reverse=json.loads(_serialize_model_context(context))['execution_comparison']
        self.assertEqual(reverse['feasible'],facts['feasible'])
        self.assertEqual(set(reverse['blocked']),set(facts['blocked']))

    def test_absent_capacity_is_unavailable_and_never_promoted_to_fit(self):
        rows=_entry_rows(research_fixture(1)[0])
        rows[0]['execution_cost_context'].pop('capacity')
        facts=json.loads(_serialize_model_context(dict(candidates=rows)))['execution_comparison']
        self.assertEqual(facts['feasible'],{})
        self.assertEqual(facts['blocked'],[])
        self.assertEqual(facts['unavailable'],['BTCTMN'])

    def test_accepted_list_excludes_requested_but_rejected_symbols_without_rewriting_trace(self):
        rows=_entry_rows(research_fixture(2)[0])
        context=dict(role='ENTRY_ANALYST',cutoff=rows[0]['interval_seconds']*1000,
            candidates=rows,requested_symbols=['BTCTMN','TRXTMN'],
            researched_symbols=['BTCTMN','TRXTMN','ETHTMN'],host_research_control_symbols=['ETHTMN'],
            research_rejections=[dict(symbol='TRXTMN',reason='SPREAD_TOO_WIDE')])
        original=copy.deepcopy(context)
        projected=json.loads(_serialize_model_context(context))
        self.assertEqual(projected['accepted_symbols'],['BTCTMN','ETHTMN'])
        self.assertEqual(projected['output_bindings'],dict(role='ENTRY_ANALYST',cutoff=300000,position_sha256=None))
        for key in ('requested_symbols','researched_symbols','host_research_control_symbols'):
            self.assertNotIn(key,projected)
        self.assertEqual(projected['execution_comparison']['research_rejected'],context['research_rejections'])
        self.assertEqual(context,original)

    def test_named_history_horizons_keep_median_sign_and_missing_quantiles(self):
        rows=_entry_rows(research_fixture(1,with_reference=True)[0])
        history=rows[0]['historical_return_reference']['horizons']
        history[0].update(q10='-.003',q50='-.001',q90='.002')
        history[1].update(q10='-.0077422',q50='.0025394',q90='.012101')
        history[2].update(segments=1,q10=None,q50=None,q90=None)
        original=copy.deepcopy(rows)
        projected=json.loads(_serialize_model_context(dict(candidates=rows)))
        metrics=dict(zip(projected['model_projection']['metric_columns'],projected['candidates'][0]['metrics'],strict=True))
        named=metrics['historical_return_reference']
        self.assertEqual([row['seconds'] for row in named],[900,3600,10800])
        self.assertEqual([row['n'] for row in named],[66,16,1])
        self.assertEqual(named[0]['q50'],'-0.001')
        self.assertEqual(named[1]['q50'],'0.0025394')
        self.assertEqual([named[2][key] for key in ('q10','q50','q90')],[None,None,None])
        self.assertEqual(rows,original)
