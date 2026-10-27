"""Avoid cross-column market fact attribution; synthetic context, never alpha evidence."""
import copy
import json
import unittest
from decimal import Decimal

from royin.agent import _entry_rows, _serialize_model_context
from tests.test_agent_dossier import research_fixture, sdk_case


class NamedEntryFactsTests(unittest.IsolatedAsyncioTestCase):
    def test_price_gap_cannot_share_an_unlabelled_array_with_path_efficiency(self):
        rows=_entry_rows(research_fixture(2,with_reference=True)[0])
        for i,row in enumerate(rows):
            row['execution_cost_context']['ask_return_from_reference']='-.0008635578584' if i==0 else '.0023'
            row['closed_bar_structure']['path_efficiency_20']='.2432432432' if i==0 else '.72'
            row['closed_bar_structure']['relative_volume_prior_20']='.5128918246' if i==0 else '1.53'
        original=copy.deepcopy(rows)
        for ordered in (rows,rows[::-1]):
            view=json.loads(_serialize_model_context(dict(candidates=ordered)))
            for candidate in view['candidates']:
                metrics=dict(zip(view['model_projection']['metric_columns'],candidate['metrics'],strict=True))
                cost=metrics['execution_cost_context']
                structure=metrics['closed_bar_structure']
                self.assertIsInstance(cost,dict)
                self.assertIsInstance(structure,dict)
                expected=next(r for r in rows if r['symbol']==candidate['symbol'])
                for actual,want in ((cost['ask_return_from_reference'],expected['execution_cost_context']['ask_return_from_reference']),
                                    (structure['path_efficiency_20'],expected['closed_bar_structure']['path_efficiency_20']),
                                    (structure['relative_volume_prior_20'],expected['closed_bar_structure']['relative_volume_prior_20'])):
                    self.assertEqual(Decimal(actual),Decimal(want))
                self.assertNotEqual(cost['ask_return_from_reference'],structure['path_efficiency_20'])
        self.assertEqual(rows,original)

    async def test_completed_research_retains_first_catalog_and_exact_tool_history_within_original_bound(self):
        result,trace,bodies,sent=await sdk_case(10,with_selection_hints=True,with_reference=True)
        self.assertEqual(result.action,'ENTER',trace.get('host_validation_code'))
        self.assertEqual(len(sent),2)
        self.assertLessEqual(max(map(len,bodies)),32768-1024)
        first,second=map(json.loads,bodies)
        catalog=[m for m in first['messages'] if m['role']=='user'][-1]['content']
        self.assertIn('research_universe',catalog)
        users=[m for m in second['messages'] if m['role']=='user']
        self.assertNotIn('research_universe',users[-1]['content'])
        self.assertIn('Original catalog preview sha256=',users[-1]['content'])
        tool_messages=[m for m in second['messages'] if m['role']=='tool']
        self.assertEqual(len(tool_messages),1)
        tool=json.loads(tool_messages[0]['content'])
        self.assertEqual(len(tool['candidates']),10)
        calls=[c for m in second['messages'] if m['role']=='assistant' for c in m.get('tool_calls',[])]
        self.assertEqual([c['id'] for c in calls],[tool_messages[0]['tool_call_id']])
        self.assertEqual(len(trace['context']['research_universe']['markets']),57)
