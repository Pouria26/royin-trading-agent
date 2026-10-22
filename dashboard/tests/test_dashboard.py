"""Sanitized synthetic evidence, isolated temp roots and localhost only."""

import copy
import hashlib
import http.client
import importlib
import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode

from dashboard.server import make_server
from dashboard.sources import (
    MAX_BYTES,
    Sources,
    decimal,
    project_balances,
    public_tail,
    readonly_budget,
    text,
)


def fixture():
    snapshot = dict(symbol="USDTTMN", cutoff=1700000000, last_close="100.125",
                    current_position_base="0", available_tmn_cash="1000.125")
    sha = hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    arm = dict(symbol="USDTTMN", initial_capital_tmn="1000.125", final_equity_mtm_tmn="990.125",
               total_fees_paid_tmn="1.250", evidence_kind="FAKE_MODEL", benchmark_contract="same synthetic conditions",
               execution_model="synthetic only", drawdown_basis="closed bar", fills_count=1,
               equity_curve=[dict(timestamp=1700000000, net_equity_tmn="1000.125"),
                             dict(timestamp=1700003600, net_equity_tmn="990.125")],
               orders=[dict(client_id="order1", side="BUY", price="100.125", quantity="1", status="UNKNOWN")],
               fills=[dict(fill_id="fill1", client_id="order1", price="100.125", quantity="0.5", fee="0.250", fee_asset="TMN", timestamp=1700003600)],
               decision_traces=[dict(snapshot=snapshot, snapshot_sha256=sha, client_id="order1",
                                    decision=dict(decision_id="decision1", symbol="USDTTMN", action="ENTER", cutoff=1700000000,
                                                  snapshot_sha256=sha, reason='<img src=x onerror="alert(1)">', evidence_ids=["EV_TEST"]),
                                    risk=dict(approved=True, action="ENTER", reason="synthetic approval", stop_price="90"))])
    return dict(created_at_utc="2023-11-14T22:13:20+00:00", status="PASS_OFFLINE_WIRING_ONLY", primary_status="BLOCKED_DATA",
                evidence_kind="SYNTHETIC_DATA_FAKE_MODEL_AND_FAKE_RECORDED_REPLAY", bindings=dict(data_sha256="a"*64),
                arms={name: copy.deepcopy(arm) for name in ("cash", "hold_shared_risk", "rule", "rule_ai")},
                api_key="NEVER_EXPORT_ME", account_id="PRIVATE_ACCOUNT", base_url="https://private.invalid")


class DashboardTests(unittest.TestCase):
    def setUp(self):
        local = Path(__file__).resolve().parents[2] / ".local/dashboard"
        local.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="dashboard-tests-", dir=local)
        self.root = Path(self.temp.name)
        self.manifest = self.root / "artifacts/portfolio-ai/test_run/manifest.json"
        self.manifest.parent.mkdir(parents=True)
        self.data = fixture()
        self.write()
        self.sources = Sources(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def write(self):
        self.manifest.write_text(json.dumps(self.data), encoding="utf8")

    def test_decimal_units_missing_and_evidence(self):
        result = self.sources.evaluation("portfolio:test_run", "bound-dataset")
        self.assertEqual(result["units"]["money"], "TMN")
        arm = result["arms"][0]
        self.assertEqual(arm["metrics"]["final_equity_mtm_tmn"], "990.125")
        self.assertIsNone(arm["metrics"]["net_return_pct"])
        self.assertIsNone(arm["counts"]["orders_submitted"])
        self.assertEqual(result["gate"], "BLOCKED_DATA")
        self.assertIn("FAKE", result["evidence_kind"])
        self.assertEqual(arm["curve"][0]["drawdown_pct"], "0")
        self.assertTrue(arm["curve"][1]["drawdown_pct"].startswith("0.999875"))
        self.assertTrue(result["comparable"])
        for value in (1.25, "NaN", "Infinity", "1e999", "-1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                decimal(value, negative=False)
        self.data["arms"]["cash"]["execution_model"] = "different costs"
        self.write()
        self.assertFalse(self.sources.evaluation("portfolio:test_run", "bound-dataset")["comparable"])

    def test_import_is_inert_and_empty_root_never_supplies_demo(self):
        import dashboard.server
        import dashboard.sources
        with patch("sqlite3.connect", side_effect=AssertionError("import opened DB")), patch("socket.socket", side_effect=AssertionError("import opened socket")):
            importlib.reload(dashboard.sources)
            importlib.reload(dashboard.server)
        empty = Sources(self.root / "absent")
        self.assertEqual(empty.runs()["status"], "EMPTY")
        self.assertEqual(empty.overview()["observation"]["mode"], "UNKNOWN")
        self.assertIsNone(empty.overview()["account"]["balances"])

    def test_secret_projection_and_html_stays_text(self):
        rows = self.sources.rows("portfolio:test_run", "bound-dataset", "rule_ai", "decisions")
        exported = json.dumps(rows)
        self.assertNotIn("NEVER_EXPORT_ME", exported)
        self.assertNotIn("PRIVATE_ACCOUNT", exported)
        self.assertNotIn("private.invalid", exported)
        self.assertEqual(rows["items"][0]["reason"], '<img src=x onerror="alert(1)">')
        script = (Path(__file__).parents[1] / "static/app.js").read_text(encoding="utf8")
        self.assertNotIn("innerHTML", script)
        self.assertIn("textContent = content", script)
        self.assertEqual(text("Cash baseline: preserve 100% capital in risk-free cash"), "Cash baseline: preserve 100% capital in risk-free cash")
        self.assertEqual(text("Bearer PRIVATE_CREDENTIAL"), "[متن حساس حذف شد]")

    def test_real_id_link_hash_binding_and_duplicate_fills(self):
        arm = self.data["arms"]["rule_ai"]
        arm["fills"].append(copy.deepcopy(arm["fills"][0]))
        self.write()
        result = self.sources.rows("portfolio:test_run", "bound-dataset", "rule_ai", "decisions")
        record = result["items"][0]
        self.assertEqual(record["feature_binding"], "HASH_VERIFIED")
        self.assertEqual(len(record["orders"][0]["fills"]), 1)
        self.assertIn("UNKNOWN_ORDER_REQUIRES_ENGINE_RECONCILIATION", result["warnings"])
        arm["decision_traces"][0]["client_id"] = "unlinked"
        arm["decision_traces"][0]["snapshot"]["last_close"] = "101"
        self.write()
        record = self.sources.rows("portfolio:test_run", "bound-dataset", "rule_ai", "decisions")["items"][0]
        self.assertEqual(record["orders"], [])
        self.assertEqual(record["feature_binding"], "UNVERIFIED")
        arm["fills"][-1]["fee"] = "9"
        self.write()
        with self.assertRaises(ValueError):
            self.sources.rows("portfolio:test_run", "bound-dataset", "rule_ai", "orders")

    def test_partial_jsonl_stale_invalid_and_no_audit_fill(self):
        directory = self.root / "data/shadow/test_run"
        audit = directory / "audit/audit_trail.jsonl"
        audit.parent.mkdir(parents=True)
        event = dict(event_id="run:1", event_type="OBSERVE_SNAPSHOT", occurred_at="2023-11-14T22:13:20+00:00")
        audit.write_text(json.dumps(event)+"\n"+json.dumps(event)+"\n"+json.dumps(dict(event_id="run:2",event_type="FILL"))+"\n{",encoding="utf8")
        events, warnings = public_tail(audit)
        self.assertEqual(len(events), 1)
        self.assertIn("PARTIAL_APPEND_IGNORED", warnings)
        manifest = directory / "shadow_manifest.json"
        manifest.write_text(json.dumps(dict(mode="OBSERVE_ONLY", evidence_kind="PUBLIC_FEED_DIAGNOSTIC", run_id="test_run",
                                           interval_seconds=3600, heartbeats=[dict(observed_at_utc="2023-11-14T22:13:20+00:00")])))
        o = self.sources.overview()
        self.assertEqual(o["observation"]["status"], "STALE")
        self.assertEqual(o["observation"]["worker"], "UNKNOWN")
        self.assertEqual(o["account"]["status"], "UNAVAILABLE")
        self.assertIsNone(o["account"]["equity_tmn"])
        manifest.write_text('{"mode":')
        self.assertEqual(self.sources.overview()["observation"]["status"], "INVALID")

    def test_readonly_sqlite_financial_content_and_no_constructor(self):
        path = self.root / "data/llm-budget.sqlite3"
        path.parent.mkdir()
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("CREATE TABLE model_reservations(id INTEGER PRIMARY KEY,day TEXT,nano_usd INTEGER,tokens INTEGER,model TEXT,policy_hash TEXT)")
            db.execute("INSERT INTO model_reservations VALUES(1,'2026-10-22',123456789,512,'test','test')")
            db.execute("CREATE TABLE balances(asset TEXT,free TEXT,locked TEXT)")
            db.execute("INSERT INTO balances VALUES('TMN','1000.125','7.500')")
            before = list(db.iterdump())
        result = readonly_budget(path)
        self.assertEqual(result["amount"], "0.123456789")
        self.assertEqual(result["requests"], 1)
        self.assertIsNone(result["invoice"])
        self.assertIsNone(result["provider_usage"])
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(list(db.iterdump()), before)
        missing = self.root / "no-db.sqlite3"
        self.assertEqual(readonly_budget(missing)["status"], "UNAVAILABLE")
        self.assertFalse(missing.exists())
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("ALTER TABLE model_reservations ADD COLUMN unknown TEXT")
        self.assertEqual(readonly_budget(path)["status"], "INVALID")
        with closing(sqlite3.connect(path)) as db:
            db.execute("BEGIN EXCLUSIVE")
            self.assertEqual(readonly_budget(path)["status"], "UNAVAILABLE")
            db.rollback()

    def test_pagination_partial_invalid_byte_bound_and_cache(self):
        trace = self.data["arms"]["rule_ai"]["decision_traces"][0]
        traces = []
        for n in range(29):
            item = copy.deepcopy(trace)
            item["decision"]["decision_id"] = "decision"+str(n)
            traces.append(item)
        self.data["arms"]["rule_ai"]["decision_traces"] = traces
        self.write()
        rows = self.sources.rows("portfolio:test_run", "bound-dataset", "rule_ai", "decisions",25,25)
        self.assertEqual(len(rows["items"]), 4)
        self.assertEqual(rows["total"],29)
        self.assertIsNone(rows["next_offset"])
        self.assertEqual(self.sources.rows("portfolio:test_run", "bound-dataset", "rule_ai", "decisions",0,25,"WAIT")["status"],"EMPTY")
        self.manifest.write_text('{"arms":')
        self.assertEqual(self.sources.runs()["items"][0]["status"], "INVALID")
        self.manifest.write_bytes(b" " * (MAX_BYTES+1))
        self.assertEqual(self.sources.runs()["items"][0]["status"], "INVALID")

    def test_get_head_only_host_origin_paths_queries_and_no_outbound(self):
        server = make_server(0,self.root)
        thread = threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        port = server.server_port
        def request(method,path,headers=None):
            connection = http.client.HTTPConnection("127.0.0.1",port,timeout=3)
            connection.request(method,path,headers=headers or {})
            response = connection.getresponse()
            result = (response.status,dict(response.getheaders()),response.read())
            connection.close()
            return result
        try:
            # Engine/network clients would use these paths; local test connection uses HTTPConnection directly.
            with patch("urllib.request.urlopen",side_effect=AssertionError("outbound HTTP forbidden")):
                code,headers,body=request("GET","/api/v1/overview")
                self.assertEqual(code,200)
                self.assertEqual(headers["Cache-Control"],"no-store")
                self.assertNotIn("Access-Control-Allow-Origin",headers)
                self.assertEqual(json.loads(body)["account"]["status"],"UNAVAILABLE")
                for method in ("POST","PUT","PATCH","DELETE","OPTIONS","TRACE","CONNECT"):
                    self.assertEqual(request(method,"/api/v1/overview")[0],405)
                self.assertEqual(request("HEAD","/api/v1/overview")[2],b"")
                for path in ("/.env","/../src/royin/config.py","/%2e%2e/.env","/api/v1/run?path=.env"):
                    self.assertEqual(request("GET",path)[0],404)
                query=dict(run="portfolio:test_run",dataset="bound-dataset",arm="rule_ai")
                for extra in (dict(limit="101"),dict(offset="-1"),dict(offset="5001"),dict(sql="SELECT secret"),dict(action="DROP")):
                    self.assertEqual(request("GET","/api/v1/decisions?"+urlencode(query|extra))[0],400)
                for run in ("../../.env","x' OR 1=1 --"):
                    self.assertEqual(request("GET","/api/v1/decisions?"+urlencode(query|dict(run=run)))[0],404)
                self.assertEqual(request("GET","/api/v1/runs",{"Host":"attacker.invalid"})[0],403)
                self.assertEqual(request("GET","/api/v1/runs",{"Origin":"https://attacker.invalid"})[0],403)
                self.assertEqual(request("GET","/api/v1/runs?run=a&run=b")[0],400)
                code,_,body=request("GET","/api/v1/decisions?"+urlencode(query))
                self.assertEqual(code,200)
                self.assertNotIn(b"NEVER_EXPORT_ME",body)
                self.assertIn(b"onerror",body)  # JSON text, never injected into HTML by UI.
        finally:
            server.shutdown()
            server.server_close()
            thread.join(3)


    def test_paper_run_catalog_and_engine_snapshot_integration(self):
        paper_manifest = self.root / "artifacts/market-paper/paper_run_1/manifest.json"
        paper_manifest.parent.mkdir(parents=True, exist_ok=True)
        data = copy.deepcopy(self.data)
        data["evidence_kind"] = "PUBLIC_MARKET_PAPER"
        paper_manifest.write_text(json.dumps(data), encoding="utf8")

        entries = self.sources.catalog()
        self.assertIn("paper:paper_run_1", entries)
        runs_resp = self.sources.runs()
        paper_meta = next(r for r in runs_resp["items"] if r["run_id"] == "paper:paper_run_1")
        self.assertEqual(paper_meta["mode"], "PAPER")
        self.assertEqual(paper_meta["freshness"], "PAPER")

        eval_resp = self.sources.evaluation("paper:paper_run_1", "bound-dataset")
        self.assertEqual(eval_resp["run_id"], "paper:paper_run_1")
        self.assertIn("arms", eval_resp)

        # Test engine-snapshot in overview
        engine_snap = self.root / ".local/dashboard/engine-snapshot.json"
        engine_snap.parent.mkdir(parents=True, exist_ok=True)
        engine_snap.write_text(json.dumps({
            "schema_version": "royin.engine-monitor.v1",
            "source": "PAPER_ENGINE_SNAPSHOT",
            "evidence_kind": "PUBLIC_MARKET_PAPER",
            "mode": "PUBLIC_MARKET_PAPER",
            "heartbeat_at": 1700000000,
            "observed_at": 1700000000,
            "account": {
                "balances": {
                    "TMN": {"free": "5000000", "locked": "0", "total": "5000000"},
                    "USDT": {"free": "0", "locked": "0", "total": "0"},
                }
            },
            "warnings": ["DEMO_TEST_WARNING"],
        }), encoding="utf8")
        overview = self.sources.overview()
        self.assertEqual(overview["account"]["status"], "AVAILABLE")
        self.assertEqual(overview["account"]["balances"]["TMN"]["free"], "5000000")
        self.assertEqual(overview["observation"]["mode"], "PUBLIC_MARKET_PAPER")

        snapshot = json.loads(engine_snap.read_text())
        snapshot["account"] = dict(balances={
            "TMN":dict(free="4000000",locked="0",total="4000000"),
            "ETH":dict(free="0.01",locked="0.02",total="0.03")},equity_tmn="5050000")
        snapshot["worker_state"] = "STOPPED_OPEN"
        engine_snap.write_text(json.dumps(snapshot),encoding="utf8")
        overview = self.sources.overview()
        self.assertEqual(overview["engine_snapshot"]["balances"]["ETH"]["total"],"0.03")
        self.assertNotIn("USDT",overview["engine_snapshot"]["balances"])
        self.assertEqual(overview["engine_snapshot"]["worker_state"],"STOPPED_OPEN")
        self.assertEqual(overview["account"]["equity_tmn"],"5050000")
        del snapshot["account"]["equity_tmn"]
        engine_snap.write_text(json.dumps(snapshot),encoding="utf8")
        self.assertEqual(self.sources.overview()["engine_snapshot"]["status"],"INVALID")

    def test_asset_projection_rejects_invalid_missing_and_inconsistent_values(self):
        for balances in ({"ETH":dict(free=".1",locked=".2",total=".4")},
                         {"../.env":dict(free="0",locked="0",total="0")},
                         {"ETH":dict(free=.1,locked="0",total=".1")},
                         {"ETH":dict(free="0",locked="0")},{}):
            with self.subTest(balances=balances),self.assertRaises(ValueError):
                project_balances(balances,totals=True)
        self.assertEqual(project_balances({"ETH":dict(free="0.1",locked="0.2",total="0.3")},totals=True)
            ["ETH"]["total"],"0.3")


if __name__ == "__main__":
    unittest.main()
