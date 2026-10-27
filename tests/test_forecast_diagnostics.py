"""Hand-computed point diagnostics; no fitted corrections or changed forecasts."""
import copy
import unittest
from decimal import Decimal as D

from royin.evaluation import score_return_forecasts


class ForecastDiagnosticTests(unittest.TestCase):
    def test_bias_and_zero_skill_have_explicit_sign_and_hand_computed_oracle(self):
        forecasts=[dict(forecast_id=str(i),horizon_seconds=3600,return_q10='-.02',
                       return_q50=v,return_q90='.02') for i,v in enumerate(('.01','-.01','0'))]
        original=copy.deepcopy(forecasts)
        values={'0':'.002','1':'.001','2':'-.001'}
        d=score_return_forecasts(forecasts,values)['point_diagnostics']
        self.assertEqual(d['status'],'DESCRIPTIVE_NOT_CALIBRATED')
        self.assertEqual(d['mean_forecast'],D(0))
        self.assertEqual(d['mean_outcome'],D('.002')/3)
        self.assertEqual(d['mean_forecast_minus_outcome'],-D('.002')/3)
        self.assertEqual(d['mae_skill_vs_zero'],D(-4))  # .020 error vs .004 error.
        self.assertEqual(d['forecast_sign_counts'],dict(positive=1,zero=1,negative=1))
        self.assertEqual(d['outcome_sign_counts'],dict(positive=2,zero=0,negative=1))
        self.assertEqual(forecasts,original)

    def test_no_issued_outcomes_or_zero_baseline_error_never_claim_positive_skill(self):
        f=dict(forecast_id='x',horizon_seconds=900,return_q10='-.01',return_q50='.001',return_q90='.01')
        self.assertIsNone(score_return_forecasts([f],{})['point_diagnostics'])
        self.assertIsNone(score_return_forecasts([f],{'x':None})['point_diagnostics'])
        d=score_return_forecasts([f],{'x':'0'})['point_diagnostics']
        self.assertIsNone(d['mae_skill_vs_zero'])
        self.assertEqual(d['mean_forecast_minus_outcome'],D('.001'))
