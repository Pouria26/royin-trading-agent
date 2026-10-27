"""Telemetry projections tested with isolated recorded fixtures, never live model calls."""

import hashlib
import json
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path

from dashboard.model_metrics import MAX_MANIFEST_BYTES, ModelMetricsReader, metrics_view
from dashboard.monitor_snapshot import activity_view
from dashboard.tests.test_cloud import CloudMonitorTests, sample


def fixture(root):
    budget = root / "budget.sqlite3"
    with closing(sqlite3.connect(budget)) as db, db:
        db.execute("CREATE TABLE model_reservations(id INTEGER PRIMARY KEY,day TEXT,nano_usd INTEGER,"
                   "tokens INTEGER,model TEXT,policy_hash TEXT,credit_id TEXT)")
        db.executemany("INSERT INTO model_reservations VALUES(?,?,?,?,?,?,?)", [
            (1,"2026-10-23",900000000,1000,"gpt-6-luna","old",None),
            (2,"2026-10-25",4357120,33792,"gpt-6-luna","new","credit_test")])
    manifest = root / "manifest.json"
    rows = [dict(model_trace=dict(evidence_kind="REAL_MODEL_ATTEMPT", provider="boxapi", model="gpt-6-luna",
        host_outcome="MODEL_DECISION", usage=dict(input_tokens=91,output_tokens=7), elapsed_seconds=1.5,
        requests=["PRIVATE_KEY"], responses=[dict(body="PRIVATE_RAW")]))]
    rows.append(dict(decision=dict(reason="WAIT: Model inference timed out"), model_trace=dict(
        evidence_kind="REAL_MODEL_ATTEMPT", provider="boxapi", model="gpt-6-luna",
        host_outcome="HOST_FALLBACK", elapsed_seconds=60)))
    manifest.write_text(json.dumps(dict(model_mode="REAL_MODEL",
        arms=dict(paper_portfolio=dict(decision_traces=rows)))))
    return manifest, budget


class ModelMetricsTests(unittest.TestCase):
    def test_original_funded_credit_and_partial_sdk_usage_are_distinct_and_readonly(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest, budget = fixture(root)
            before = {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in (manifest,budget)}
            reader = ModelMetricsReader(manifest,budget,"credit_test")
            result = activity_view(dict(model_metrics=reader.read(int(time.time()))))["model_metrics"]
            self.assertEqual(result["reservation"]["amount"],"0.00435712")
            self.assertEqual(result["reservation"]["requests"],1)
            self.assertEqual(result["reservation"]["reserved_tokens"],33792)
            self.assertEqual(result["usage"]["input_tokens"],91)
            self.assertEqual(result["usage"]["reported_traces"],1)
            self.assertEqual(result["usage"]["attempted_traces"],2)
            self.assertEqual(result["model"]["errors"],1)
            self.assertEqual(result["model"]["timeouts"],1)
            self.assertNotIn("PRIVATE",json.dumps(result))
            self.assertNotIn("invoice",result["reservation"])
            self.assertEqual(before,{p:hashlib.sha256(p.read_bytes()).hexdigest() for p in before})
            cached = reader.cached
            reader.read(int(time.time()))
            self.assertIs(reader.cached,cached)
            # New attempts append to the original ledger, not a recreated zero budget.
            with closing(sqlite3.connect(budget)) as db, db:
                db.execute("INSERT INTO model_reservations VALUES(3,'2026-10-25',4357120,33792,"
                           "'gpt-6-luna','new','credit_test')")
            self.assertEqual(reader.read(int(time.time()))["reservation"]["requests"],2)

    def test_missing_or_invalid_source_does_not_create_database_or_invent_zero_usage(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            reader = ModelMetricsReader(root/"absent.json",root/"absent.sqlite3","credit_test")
            for name,row in reader.read(int(time.time())).items():
                if name in ("reservation","usage","model"):
                    self.assertEqual(row["status"],"UNAVAILABLE")
            self.assertFalse(list(root.iterdir()))
            manifest,budget = fixture(root)
            with manifest.open("wb") as stream:
                stream.truncate(MAX_MANIFEST_BYTES+1)
            result = ModelMetricsReader(manifest,budget,"credit_test").read(int(time.time()))
            self.assertEqual(result["usage"]["status"],"UNAVAILABLE")
            self.assertIsNone(result["usage"]["input_tokens"])
            self.assertEqual(result["reservation"]["status"],"AVAILABLE")

    def test_invalid_counts_float_money_and_false_coverage_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest,budget = fixture(Path(folder))
            original = ModelMetricsReader(manifest,budget,"credit_test").read(int(time.time()))
            for component,key,value in [("usage","input_tokens",-1),("usage","input_tokens",True),
                    ("reservation","amount",0.004),("usage","reported_traces",3),
                    ("reservation","amount","NaN")]:
                result = json.loads(json.dumps(original))
                result[component][key] = value
                with self.assertRaises(ValueError):
                    metrics_view(result)


class ModelMetricsCloudTests(CloudMonitorTests):
    # Inherit the actual HTTP harness; keep the test collection restricted below.
    def test_signed_metrics_reach_existing_cards_without_financial_disk_or_private_data(self):
        manifest,budget = fixture(self.root)
        metrics = ModelMetricsReader(manifest,budget,"credit_test").read(int(time.time()))
        payload = sample()
        metrics["provider_key"] = "PRIVATE_KEY"
        metrics["usage"]["raw_response"] = "PRIVATE_RAW"
        payload["activity"]["model_metrics"] = activity_view(dict(model_metrics=metrics))["model_metrics"]
        self.assertEqual(self.push(payload)[0],200)
        response = self.request("GET","/api/v1/overview",headers={"Authorization":self.auth})
        overview = json.loads(response[2])
        self.assertEqual(overview["reservation"]["amount"],"0.00435712")
        self.assertEqual(overview["archived_usage"]["input_tokens"],91)
        self.assertEqual(overview["model"]["model"],"gpt-6-luna")
        self.assertIsNone(overview["reservation"]["invoice"])
        self.assertNotIn(b"PRIVATE",response[2])
        self.assertFalse((self.root/"data").exists())
        payload["activity"]["model_metrics"]["observed_at"] = int(time.time())-200
        self.assertEqual(self.push(payload,nonce="c"*32)[0],200)
        overview=json.loads(self.request("GET","/api/v1/overview",headers={"Authorization":self.auth})[2])
        self.assertEqual(overview["reservation"]["status"],"STALE")
        payload["activity"]["model_metrics"]["observed_at"] = int(time.time())+120
        self.assertEqual(self.push(payload,nonce="d"*32)[0],400)


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite(loader.loadTestsFromTestCase(ModelMetricsTests))
    suite.addTest(ModelMetricsCloudTests(
        "test_signed_metrics_reach_existing_cards_without_financial_disk_or_private_data"))
    return suite
