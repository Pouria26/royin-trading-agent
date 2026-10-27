"""Forecast outcome oracles: synthetic provider traces, never real accuracy evidence."""

import asyncio
import copy
import hashlib
import io
import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from royin.decision import Decision, MarketEntrySignal
from scripts import score_market_forecast as scorer
from scripts.run_fresh_service import EntrySignals
from tests.test_forecast_scoring import forecast, snapshot


class CurrentForecastOutcomeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        snap = snapshot()
        fc = forecast(horizon_seconds=300,review_after_seconds=150,return_q50=".01")
        f = fc.model_dump(mode="json")
        self.provider = dict(action="WAIT",symbol=None,snapshot_sha256=snap.snapshot_sha256,forecast=f)
        candidates = [dict(symbol=snap.symbol,snapshot_sha256=snap.snapshot_sha256)]
        context = dict(cutoff=snap.cutoff,candidates=candidates,horizon_bounds=[300,36000],
            batch_sha256=hashlib.sha256(json.dumps(candidates,sort_keys=True,separators=(",",":")).encode()).hexdigest())
        decision = dict(action="WAIT",symbol=snap.symbol,cutoff=snap.cutoff,snapshot_sha256=snap.snapshot_sha256,forecast=f)
        model = dict(host_outcome="MODEL_DECISION",evidence_kind="REAL_MODEL_ATTEMPT",provider="boxapi",model="gpt-6-luna",
            prompt_sha256="b"*64,context=context,decision=copy.deepcopy(decision))
        self.row = dict(decision=decision,snapshot=snap.to_canonical_dict(),snapshot_sha256=snap.snapshot_sha256,model_trace=model)
        self.manifest = dict(mode="CURRENT_PAPER",model_mode="REAL_MODEL",run_id="synthetic-forecast",created_at_utc=datetime.fromtimestamp(8101,UTC).isoformat(),
            bindings=dict(code_sha256="a"*64),arms=dict(paper_portfolio=dict(decision_traces=[self.row])))
        self.payload = dict(s="ok",t=[8340],o=["101"],h=["106"],l=["100"],c=["105.04"],v=["20"])

    def source(self,name="manifest.json"):
        self.row["model_trace"]["responses"] = [dict(status_code=200,body=json.dumps(dict(choices=[dict(message=dict(tool_calls=[
            dict(function=dict(name="final_result",arguments=json.dumps(self.provider)))]))]))) ]
        path = self.root/name
        path.write_text(json.dumps(self.manifest),encoding="utf-8")
        return path

    def test_nullable_wait_matches_the_bound_forecast_symbol(self):
        path = self.source()
        _,rows,skipped = scorer.current_forecasts(path)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["forecast"].symbol,"USDTTMN")
        self.assertFalse(skipped)

    def host_bound_source(self):
        context=self.row['model_trace']['context']
        context['output_binding_policy']='HOST_OWNED_MARKET_BINDING_V1'
        self.provider.pop('snapshot_sha256')
        self.provider.update(role='ENTRY_ANALYST',symbol=self.row['decision']['symbol'],
            cutoff=self.row['decision']['cutoff'],evidence_ids=['EV_DATA_FRESH'],
            reason='Synthetic conditional forecast',invalidation='Next candle',
            horizon_seconds=300,review_after_seconds=150)
        signal=MarketEntrySignal.model_validate(self.provider).model_dump(mode='json')
        self.row['model_trace'].update(model_signal=signal,host_binding=dict(
            policy='HOST_OWNED_MARKET_BINDING_V1',symbol=signal['symbol'],
            snapshot_sha256=self.row['snapshot_sha256'],opportunity_sha256=None,
            validated_signal_sha256=hashlib.sha256(json.dumps(signal,sort_keys=True,separators=(',',':')).encode()).hexdigest()))
        return self.source('host-bound.json')

    def test_host_owned_source_binding_scores_the_unchanged_raw_model_forecast(self):
        path=self.host_bound_source()
        before=path.read_bytes()
        _,rows,_=scorer.current_forecasts(path)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['forecast'].model_dump(mode='json'),self.provider['forecast'])
        self.assertEqual(path.read_bytes(),before)

    def test_host_binding_tampering_or_forbidden_raw_hash_blocks_before_outcome_http(self):
        self.host_bound_source()
        original=copy.deepcopy(self.row['model_trace'])
        for mode in ('hash','signal_hash','signal','raw_hash','no_policy','no_batch'):
            with self.subTest(mode=mode):
                self.row['model_trace']=copy.deepcopy(original)
                if mode=='hash':
                    self.row['model_trace']['host_binding']['snapshot_sha256']='f'*64
                elif mode=='signal_hash':
                    self.row['model_trace']['host_binding']['validated_signal_sha256']='f'*64
                elif mode=='signal':
                    self.row['model_trace']['model_signal']['forecast']['return_q50']='.02'
                elif mode=='raw_hash':
                    self.provider['snapshot_sha256']=None
                elif mode=='no_policy':
                    del self.row['model_trace']['context']['output_binding_policy']
                else:
                    self.row['model_trace']['context'].pop('candidates')
                    self.row['model_trace']['context']['snapshot_sha256']=self.row['snapshot_sha256']
                with self.assertRaises((ValueError,KeyError)),patch.object(scorer.urllib.request,'urlopen') as http:
                    scorer.score_current([self.source()],self.root/('host-tamper-'+mode),now=8460)
                http.assert_not_called()
                self.provider.pop('snapshot_sha256',None)

    def test_host_deferral_without_decision_is_reported_without_losing_forecasts(self):
        self.source()
        deferred = dict(host_outcome="HOST_DEFERRED", cutoff=8100, reason="Publication delay",
                        model_trace=dict(host_outcome="HOST_DEFERRED"))
        self.manifest["arms"]["paper_portfolio"]["decision_traces"].insert(0, deferred)
        path = self.root/"deferred.json"
        path.write_text(json.dumps(self.manifest), encoding="utf-8")
        before = path.read_bytes()
        _, rows, skipped = scorer.current_forecasts(path)
        self.assertEqual(rows[0]["trace_index"], 1)
        self.assertEqual(skipped[0]["reason"], "HOST_DEFERRED_NO_FORECAST")
        self.assertEqual(path.read_bytes(), before)
        deferred["model_trace"]["responses"] = [dict(status_code=200, body="unverified")]
        path.write_text(json.dumps(self.manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "decision"):
            scorer.current_forecasts(path)

    def test_unexplained_missing_decision_still_blocks_before_outcome_http(self):
        self.source()
        self.manifest["arms"]["paper_portfolio"]["decision_traces"].insert(0, {})
        path = self.root/"malformed.json"
        path.write_text(json.dumps(self.manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "decision"), patch.object(scorer.urllib.request,"urlopen") as http:
            scorer.score_current([path], self.root/"malformed-out", now=8460)
        http.assert_not_called()

    def test_actual_signal_override_retains_snapshot_and_pre_outcome_issuance(self):
        # Exercise the live signal override, rather than a hand-written paper trace.
        self.source()
        snap = snapshot()
        signals = EntrySignals.__new__(EntrySignals)
        signals.decision_traces = []
        decision = Decision(decision_id="synthetic-live-signal", evidence_ids=("EV_DATA_FRESH",),
            reason="Synthetic WAIT", invalidation="Next candle", **self.row["decision"])
        with patch("scripts.run_fresh_service.datetime") as clock:
            clock.now.return_value = datetime.fromtimestamp(8101, UTC)
            asyncio.run(signals._apply_entry_decision(None, decision, {snap.symbol: (snap, None)},
                primary_snap=snap, model_trace=self.row["model_trace"], report={}))
        self.manifest["arms"]["paper_portfolio"]["decision_traces"] = signals.decision_traces
        self.manifest["created_at_utc"] = datetime.fromtimestamp(9000, UTC).isoformat()
        path = self.root/"live-signal.json"
        path.write_text(json.dumps(self.manifest), encoding="utf-8")
        _, rows, _ = scorer.current_forecasts(path)
        self.assertTrue(rows[0]["issued_before_outcome"])
        self.assertEqual(signals.decision_traces[0]["execution_mode"], "SIGNAL_ONLY_NO_PAPER_FILL")
        self.assertIsNone(signals.selection)

    def test_provider_label_cannot_rebind_a_model_from_another_catalog(self):
        self.row["model_trace"]["provider"]="river"
        with self.assertRaisesRegex(ValueError,"provider"):
            scorer.current_forecasts(self.source())
        self.row["model_trace"]["model"]="deepseek-ai/DeepSeek-V4.1-Flash"
        _,rows,_=scorer.current_forecasts(self.source())
        self.assertEqual(len(rows),1)

    def test_trace_issuance_survives_later_long_session_manifest_write(self):
        self.row["issued_at_utc"] = datetime.fromtimestamp(8101,UTC).isoformat()
        self.manifest["created_at_utc"] = datetime.fromtimestamp(9000,UTC).isoformat()
        _,rows,_ = scorer.current_forecasts(self.source())
        self.assertTrue(rows[0]["issued_before_outcome"])
        self.row["issued_at_utc"] = datetime.fromtimestamp(8401,UTC).isoformat()
        with self.assertRaisesRegex(ValueError,"pre-outcome"):
            scorer.current_forecasts(self.source())
        self.row["issued_at_utc"] = datetime.fromtimestamp(9001,UTC).isoformat()
        with self.assertRaisesRegex(ValueError,"issuance"):
            scorer.current_forecasts(self.source())

    def test_whole_second_manifest_and_fractional_issuance_use_recorded_precision(self):
        self.manifest["created_at_utc"] = "1970-01-01T02:15:01Z"
        self.row["issued_at_utc"] = "1970-01-01T02:15:01.900000+00:00"
        _, rows, _ = scorer.current_forecasts(self.source())
        self.assertEqual(len(rows),1)
        self.row["issued_at_utc"] = "1970-01-01T02:15:02+00:00"
        with self.assertRaisesRegex(ValueError,"issuance"):
            scorer.current_forecasts(self.source())
        self.manifest["created_at_utc"] = "1970-01-01T02:15:01.000000Z"
        self.row["issued_at_utc"] = "1970-01-01T02:15:01.900000+00:00"
        with self.assertRaisesRegex(ValueError,"issuance"):
            scorer.current_forecasts(self.source())

    def test_changed_forecast_snapshot_and_post_outcome_issuance_are_rejected(self):
        for mode in ("forecast","snapshot","late"):
            with self.subTest(mode=mode):
                original = copy.deepcopy(self.manifest)
                if mode == "forecast":
                    self.row["decision"]["forecast"]["return_q50"] = ".02"
                elif mode == "snapshot":
                    self.row["snapshot"]["last_close"] = "999"
                else:
                    self.manifest["created_at_utc"] = datetime.fromtimestamp(8401,UTC).isoformat()
                with self.assertRaises(ValueError),patch.object(scorer.urllib.request,"urlopen") as http:
                    scorer.score_current([self.source(mode+".json")],self.root/(mode+"-out"),now=8460)
                http.assert_not_called()
                self.manifest = original
                self.row = original["arms"]["paper_portfolio"]["decision_traces"][0]

    def test_wrong_provider_symbol_does_not_get_nullable_wait_exception(self):
        self.provider["symbol"] = "BTCTMN"
        with self.assertRaises(ValueError):
            scorer.current_forecasts(self.source())
        with patch.object(scorer.urllib.request,"urlopen") as http,patch("builtins.print") as output:
            self.assertEqual(scorer.main(["--paper-manifest",str(self.source()),"--score"]),2)
        http.assert_not_called()
        self.assertEqual(json.loads(output.call_args.args[0])["status"],"BLOCKED_FORECAST_INPUT")

    def test_hand_return_interval_score_and_zero_point_baseline_without_test_fit(self):
        path = self.source()
        before = path.read_bytes()
        output = self.root/"scored"
        with patch.object(scorer.urllib.request,"urlopen",return_value=io.BytesIO(json.dumps(self.payload).encode())) as http,patch("builtins.print"):
            self.assertEqual(scorer.score_current([path],output,now=8460),0)
        self.assertEqual(http.call_count,1)
        self.assertIn("resolution=1&from=8340&to=8400",http.call_args.args[0].full_url)
        report = json.loads((output/"report.json").read_text())
        scores = report["scores"]
        self.assertEqual(scores["scored"],1)
        self.assertEqual(scores["median_abs_error"],"0.03")
        self.assertEqual(scores["mean_abs_error"],"0.03")
        self.assertEqual(scores["zero_point_comparison"]["model_better"],1)
        self.assertEqual(scores["zero_point_comparison"]["mean_absolute_error_difference"],"-0.01")
        self.assertEqual(scores["mean_winkler"],"0.14")
        self.assertEqual(report["zero_point_baseline"]["median_abs_error"],"0.04")
        self.assertEqual(report["zero_point_baseline"]["mean_abs_error"],"0.04")
        self.assertIsNone(report["zero_point_baseline"]["q90"])
        self.assertEqual(path.read_bytes(),before)
        with self.assertRaises(FileExistsError),patch.object(scorer.urllib.request,"urlopen") as http:
            scorer.score_current([path],output,now=8460)
        http.assert_not_called()

    def test_future_outcome_is_pending_without_network(self):
        with patch.object(scorer.urllib.request,"urlopen") as http,patch("builtins.print"):
            self.assertEqual(scorer.score_current([self.source()],self.root/"pending",now=8399),2)
        http.assert_not_called()
        result = json.loads((self.root/"pending/report.json").read_text())
        self.assertEqual(result["scores"]["pending"],1)
        self.assertIsNone(result["zero_point_baseline"])

    def test_missing_target_minute_is_not_interpolated_from_a_later_bar(self):
        self.payload["t"] = [8400]
        with patch.object(scorer.urllib.request,"urlopen",return_value=io.BytesIO(json.dumps(self.payload).encode())),patch("builtins.print"):
            self.assertEqual(scorer.score_current([self.source()],self.root/"gap",now=8460),2)
        result = json.loads((self.root/"gap/report.json").read_text())
        self.assertEqual(result["scores"]["missing_outcome"],1)
        self.assertEqual(result["scores"]["scored"],0)

    def test_duplicate_sources_are_not_counted_twice(self):
        path = self.source()
        for paths in ([path,path], [path,self.root/"copy.json"]):
            (self.root/"copy.json").write_bytes(path.read_bytes())
            with self.assertRaises(ValueError),patch.object(scorer.urllib.request,"urlopen") as http:
                scorer.score_current(paths,self.root/"duplicate",now=8460)
            http.assert_not_called()

    def test_copied_provider_result_under_a_new_run_id_is_not_a_new_observation(self):
        first = self.source("first.json")
        self.manifest["run_id"] = "another-synthetic-run"
        second = self.source("second.json")
        with self.assertRaises(ValueError),patch.object(scorer.urllib.request,"urlopen") as http:
            scorer.score_current([first,second],self.root/"copied-provider",now=8460)
        http.assert_not_called()

    def test_subminute_horizon_is_missing_rather_than_rounded_to_future(self):
        for fc in (self.provider["forecast"],self.row["decision"]["forecast"],self.row["model_trace"]["decision"]["forecast"]):
            fc["horizon_seconds"] = 301
        with patch.object(scorer.urllib.request,"urlopen") as http,patch("builtins.print"):
            self.assertEqual(scorer.score_current([self.source()],self.root/"subminute",now=8461),2)
        http.assert_not_called()
        result = json.loads((self.root/"subminute/report.json").read_text())
        self.assertEqual(result["records"][0]["status"],"UNSUPPORTED_SUBMINUTE_HORIZON")

    def test_explicit_range_preserves_original_indexes_and_reports_excluded_legacy_rows(self):
        self.source()
        legacy = dict(decision=dict(action="WAIT", forecast={}))
        self.manifest["arms"]["paper_portfolio"]["decision_traces"].insert(0, legacy)
        source = self.root/"continued.json"
        source.write_text(json.dumps(self.manifest),encoding="utf-8")
        before = source.read_bytes()
        _, rows, skipped = scorer.current_forecasts(source,trace_start=1,trace_limit=1)
        self.assertEqual(rows[0]["trace_index"],1)
        self.assertEqual(skipped,[dict(run_id="synthetic-forecast",trace_index=0,
                                      reason="OUTSIDE_REQUESTED_TRACE_RANGE")])
        with self.assertRaises((ValueError, KeyError)):
            scorer.current_forecasts(source)
        for start, limit in ((-1,1),(True,1),(0,33),(0,0)):
            with self.assertRaises(ValueError),patch.object(scorer.urllib.request,"urlopen") as http:
                scorer.score_current([source],self.root/"bad-range",trace_start=start,trace_limit=limit)
            http.assert_not_called()
        self.assertEqual(source.read_bytes(),before)


if __name__ == "__main__":
    unittest.main()
