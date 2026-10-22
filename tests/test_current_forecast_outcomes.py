"""Forecast outcome oracles: synthetic provider traces, never real accuracy evidence."""

import copy
import hashlib
import io
import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from scripts import score_market_forecast as scorer
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
        model = dict(host_outcome="MODEL_DECISION",evidence_kind="REAL_MODEL_ATTEMPT",provider="boxapi",model="synthetic-model-label",
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
        self.assertEqual(scores["mean_winkler"],"0.14")
        self.assertEqual(report["zero_point_baseline"]["median_abs_error"],"0.04")
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


if __name__ == "__main__":
    unittest.main()
