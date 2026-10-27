"""Quantified candidate/horizon coverage is not proof of forecasting skill."""
import copy
import hashlib
import json
import unittest

from royin.decision import MarketEntryProposal, ReturnForecast, validate_role_proposal
from tests.test_agent_dossier import sdk_case
from tests.test_executable_selection import mixed_batch, proposal_for


class HorizonComparisonTests(unittest.IsolatedAsyncioTestCase):
    async def test_host_binds_source_hashes_without_rewriting_the_model_price_signal(self):
        outputs=[]
        result,trace,bodies,sent=await sdk_case(2,provider_outputs=outputs)
        self.assertEqual(result.action,'ENTER')
        raw=json.loads(outputs[0])
        self.assertNotIn('snapshot_sha256',raw)
        self.assertNotIn('opportunity_sha256',raw)
        self.assertEqual(ReturnForecast.model_validate(raw['forecast']),
            ReturnForecast.model_validate(trace['model_signal']['forecast']))
        self.assertEqual(raw['action'],result.action)
        binding=trace['host_binding']
        self.assertEqual(binding['snapshot_sha256'],result.snapshot_sha256)
        self.assertEqual(binding['validated_signal_sha256'],hashlib.sha256(json.dumps(
            trace['model_signal'],sort_keys=True,separators=(',',':')).encode()).hexdigest())
        self.assertEqual(len(sent),2)
        self.assertIn('do not output snapshot_sha256 or opportunity_sha256',json.loads(bodies[1])['messages'][0]['content'])

    async def test_model_supplied_source_hashes_are_rejected_even_when_null_or_correct(self):
        from tests.test_agent_dossier import research_fixture
        loaded,_=research_fixture(2)
        for metadata in ({'snapshot_sha256':loaded['BTCTMN'][0].snapshot_sha256},
                         {'snapshot_sha256':None},{'opportunity_sha256':None},{'snapshot_sha256':'f'*64}):
            with self.subTest(metadata=metadata):
                result,trace,_bodies,sent=await sdk_case(2,model_metadata=metadata)
                self.assertEqual(result.action,'WAIT')
                self.assertEqual(trace['host_outcome'],'HOST_FALLBACK')
                self.assertNotIn('host_binding',trace)
                self.assertEqual(len(sent),2)

    async def test_real_sdk_demands_a_numeric_comparison_instead_of_symbol_names_only(self):
        result,trace,bodies,sent=await sdk_case(2)
        self.assertEqual(result.action,'ENTER')
        self.assertEqual(len(sent),2)
        request=json.loads(bodies[1])
        tool=next(t['function'] for t in request['tools'] if t['function']['name']=='final_result')
        self.assertIn('candidate_medians',tool['parameters']['required'])
        view=json.loads(next(m['content'] for m in request['messages'] if m['role']=='tool'))
        self.assertEqual(view['evaluation_horizons'],[3600,10800])
        self.assertEqual(trace['horizon_comparison']['status'],'VERIFIED_NUMERIC_COVERAGE')

    async def test_provider_omission_is_classified_after_two_requests_without_a_paid_repair(self):
        result,trace,bodies,sent=await sdk_case(2,omit_output_fields=('candidate_medians',))
        self.assertEqual(result.action,'WAIT')
        self.assertEqual(len(sent),2)
        self.assertEqual(len(bodies),2)
        self.assertEqual(trace['host_validation_code'],'FORECAST_COMPARISON_COVERAGE_MISMATCH')

    async def test_shared_named_assumptions_preserve_each_candidate_fact_and_budget(self):
        result,trace,bodies,sent=await sdk_case(10,with_reference=True,with_selection_hints=True)
        self.assertEqual(result.action,'ENTER')
        self.assertEqual(len(sent),2)
        self.assertLessEqual(max(map(len,bodies)),31744)
        view=json.loads(next(m['content'] for m in json.loads(bodies[1])['messages'] if m['role']=='tool'))
        projection=view['model_projection']
        for candidate in view['candidates']:
            metrics=dict(zip(projection['metric_columns'],candidate['metrics'],strict=True))
            original=next(row for row in trace['context']['candidates'] if row['symbol']==candidate['symbol'])
            for key in ('execution_cost_context','closed_bar_structure'):
                combined=projection['shared_'+key] | metrics[key]
                for field,value in projection['shared_'+key].items():
                    self.assertEqual(value,original[key][field])
                    self.assertEqual(combined[field],original[key][field])

    def test_every_feasible_symbol_needs_both_horizons_even_when_not_selected(self):
        from tests.test_agent_dossier import research_fixture
        loaded,_=research_fixture(2,with_reference=True)
        data=proposal_for(loaded,'BTCTMN',action='WAIT')
        rows=[['BTCTMN',3600,'-.002'],['BTCTMN',10800,'.012'],
              ['ETHTMN',3600,'-.005'],['ETHTMN',10800,'.008']]
        snap,_opp=loaded['BTCTMN']
        def check():
            validate_role_proposal(MarketEntryProposal.model_validate(data),role='ENTRY_ANALYST',snapshot=snap,
                position=None,opportunity=None,market_batch=loaded,horizon_bounds=(300,14400),
                require_comparison=True,evaluation_horizons=(3600,10800))
        data['candidate_medians']=rows[:-1]
        with self.assertRaisesRegex(ValueError,'candidate-horizon'):
            check()
        data['candidate_medians']=rows
        check()

    def validate(self, data, *, all_blocked=False):
        loaded,_=mixed_batch(all_blocked=all_blocked)
        proposal=MarketEntryProposal.model_validate(data)
        snap,opp=loaded[proposal.symbol]
        return validate_role_proposal(proposal,role='ENTRY_ANALYST',snapshot=snap,position=None,
            opportunity=opp if proposal.action=='ENTER' else None,market_batch=loaded,
            horizon_bounds=(300,14400),require_comparison=True,evaluation_horizons=(3600,10800))

    def payload(self, *, action='WAIT', median='.012'):
        loaded,_=mixed_batch()
        data=proposal_for(loaded,'BTCTMN',action=action,median=median)
        data['candidate_medians']=[['BTCTMN',3600,'-.002'],['BTCTMN',10800,median]]
        return data

    def test_complete_negative_and_positive_estimates_are_both_valid_and_not_clamped(self):
        for median in ('-.004','.012'):
            data=self.payload(median=median)
            original=copy.deepcopy(data)
            self.validate(data)
            self.assertEqual(data,original)

    def test_missing_duplicate_blocked_or_wrong_horizon_cannot_claim_comparison(self):
        cases=(None,[],[['BTCTMN',10800,'.012']],
            [['BTCTMN',3600,'-.002'],['BTCTMN',3600,'.012']],
            [['ETHTMN',3600,'-.002'],['BTCTMN',10800,'.012']],
            [['BTCTMN',900,'-.002'],['BTCTMN',10800,'.012']])
        for estimates in cases:
            with self.subTest(estimates=estimates):
                data=self.payload()
                data['candidate_medians']=estimates
                with self.assertRaises(ValueError):
                    self.validate(data)

    def test_selected_forecast_cannot_replace_its_compared_median(self):
        data=self.payload()
        data['forecast']['return_q50']='.013'
        with self.assertRaisesRegex(ValueError,'selected forecast'):
            self.validate(data)

    def test_a_separately_chosen_allowed_horizon_needs_its_own_comparison(self):
        data=self.payload()
        data['horizon_seconds']=14400
        data['forecast']['horizon_seconds']=14400
        with self.assertRaisesRegex(ValueError,'candidate-horizon'):
            self.validate(data)
        data['candidate_medians'].append(['BTCTMN',14400,'.012'])
        self.validate(data)

    def test_valid_comparison_cannot_bypass_the_existing_economic_gate(self):
        data=self.payload(action='ENTER',median='.001')
        with self.assertRaisesRegex(ValueError,'central forecast'):
            self.validate(data)

    def test_no_capacity_has_empty_comparison_and_remains_wait(self):
        loaded,_=mixed_batch(all_blocked=True)
        data=proposal_for(loaded,'BTCTMN',action='WAIT')
        data['candidate_medians']=[]
        self.validate(data,all_blocked=True)

    def test_nonfinite_boolean_horizon_and_oversized_estimates_reject(self):
        for row in (['BTCTMN',True,'.01'],['BTCTMN',3600,'NaN'],['BTCTMN',3600,'Infinity'],
                    ['BTCTMN',3600,True],['BTCTMN',3600,'1.01']):
            with self.subTest(row=row):
                data=self.payload()
                data['candidate_medians']=[row]
                with self.assertRaises(ValueError):
                    self.validate(data)
