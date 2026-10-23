"""Authenticated monitoring boundaries with real local HTTP and temporary exports."""

import base64
import copy
import hashlib
import http.client
import json
import tempfile
import threading
import time
import unittest
from contextlib import closing
from pathlib import Path

from dashboard.cloud import make_cloud_server, signature
from dashboard.monitor_snapshot import read_activity, snapshot_view


def sample():
    now = int(time.time())
    return dict(schema_version="royin.monitor-push.v1", snapshot=dict(
        mode="LIVE_BOUNDED", run_id="mission_test", source="RECORDED_FINANCIAL_LEDGER",
        evidence_kind="REAL_CREDIT_ACCOUNT", worker_state="RUNNING", heartbeat_at=now, observed_at=now,
        account=dict(balances={"TMN": dict(free="5000000", locked="0", total="5000000")}, equity_tmn="5000000"),
        risk=dict(status="HOST_GATES_ACTIVE")), activity=dict(decisions=[dict(decision_id="decision_test",
        symbol="BTCTMN", action="WAIT", cutoff=now, reason="No supported entry", host_outcome="MODEL_DECISION")]))


class CloudMonitorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.key = "test-ingest-" + "k" * 32
        self.password = "test-password-" + "p" * 24
        self.server = make_cloud_server(host="monitor.test", port=0, root=self.root,
                                        username="test", password=self.password, ingest_key=self.key,
                                        mission="mission_test")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.auth = "Basic " + base64.b64encode(("test:" + self.password).encode()).decode()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, method, path, body=None, headers=None):
        with closing(http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)) as client:
            client.request(method, path, body, {"Host": "monitor.test", **(headers or {})})
            response = client.getresponse()
            return response.status, dict(response.getheaders()), response.read()

    def push(self, payload=None, *, nonce="a" * 32, sent_at=None, sign_key=None):
        body = json.dumps(payload if payload is not None else sample()).encode()
        sent = int(time.time()) if sent_at is None else sent_at
        return self.request("POST", "/internal/snapshot", body, {
            "X-Royin-Time": str(sent), "X-Royin-Nonce": nonce,
            "X-Royin-Signature": signature(sign_key or self.key, sent, nonce, body)})

    def test_every_dashboard_asset_and_api_requires_authentication(self):
        for path in ["/", "/app.js", "/fonts/InterVariable.woff2", "/api/v1/overview", "/api/v1/runs"]:
            status, headers, body = self.request("GET", path)
            self.assertEqual(status, 401)
            self.assertIn("WWW-Authenticate", headers)
            self.assertNotIn(b"5000000", body)
        self.assertEqual(self.request("GET", "/", headers={"Authorization": self.auth})[0], 200)

    def test_health_contains_no_snapshot_or_credentials(self):
        status, _, body = self.request("GET", "/healthz")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"status": "MONITOR_SERVER_AVAILABLE"})

    def test_authenticated_signed_push_displays_actual_balance_and_decision(self):
        self.assertEqual(self.push()[0], 200)
        status, _, body = self.request("GET", "/api/v1/overview", headers={"Authorization": self.auth})
        data = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(data["account"]["balances"]["TMN"]["free"], "5000000")
        self.assertEqual(data["observation"]["mode"], "LIVE_BOUNDED")
        self.assertEqual(data["live_activity"]["decisions"][0]["action"], "WAIT")
        self.assertFalse((self.root / "data").exists())

    def test_wrong_key_old_signature_and_replay_do_not_replace_snapshot(self):
        payload = sample()
        self.assertEqual(self.push(payload)[0], 200)
        path = self.root / ".local/dashboard/engine-snapshot.json"
        original = path.read_bytes()
        self.assertEqual(self.push(payload)[0], 409)
        self.assertEqual(self.push(payload, nonce="b" * 32, sign_key="wrong")[0], 403)
        self.assertEqual(self.push(payload, nonce="c" * 32, sent_at=int(time.time()) - 90)[0], 403)
        self.assertEqual(path.read_bytes(), original)

    def test_invalid_mission_float_money_and_future_observation_are_rejected(self):
        for variant in ["mission", "float", "future"]:
            payload = sample()
            if variant == "mission":
                payload["snapshot"]["run_id"] = "other_mission"
            elif variant == "float":
                payload["snapshot"]["account"]["balances"]["TMN"]["free"] = 5000000.0
            else:
                payload["snapshot"]["heartbeat_at"] += 120
            self.assertEqual(self.push(payload)[0], 400)
        self.assertFalse((self.root / ".local/dashboard/engine-snapshot.json").exists())

    def test_unknown_fields_and_sensitive_free_text_never_reach_api(self):
        payload = sample()
        payload["snapshot"]["api_key"] = "DO_NOT_EXPORT"
        payload["activity"]["model_messages"] = "DO_NOT_EXPORT"
        payload["activity"]["decisions"][0]["reason"] = "api_key=DO_NOT_EXPORT"
        self.assertEqual(self.push(payload)[0], 200)
        body = self.request("GET", "/api/v1/overview", headers={"Authorization": self.auth})[2]
        self.assertNotIn(b"DO_NOT_EXPORT", body)
        self.assertNotIn(b"model_messages", body)

    def test_stale_engine_is_not_made_fresh_by_recent_delivery(self):
        payload = sample()
        payload["snapshot"]["heartbeat_at"] -= 300
        payload["snapshot"]["observed_at"] -= 300
        self.assertEqual(self.push(payload)[0], 200)
        body = self.request("GET", "/api/v1/overview", headers={"Authorization": self.auth})[2]
        self.assertEqual(json.loads(body)["observation"]["status"], "STALE")

    def test_host_origin_and_order_mutations_stay_closed(self):
        self.assertEqual(self.request("GET", "/", headers={"Authorization": self.auth, "Host": "evil.test"})[0], 403)
        self.assertEqual(self.request("GET", "/", headers={"Authorization": self.auth, "Origin": "https://evil.test"})[0], 403)
        self.assertEqual(self.request("POST", "/api/v1/orders", b"{}", {"Authorization": self.auth})[0], 405)
        self.assertEqual(self.request("GET", "/.env", headers={"Authorization": self.auth})[0], 404)


class MonitoringProjectionTests(unittest.TestCase):
    def test_file_projection_omits_raw_model_response_and_preserves_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "signals/manifest.json"
            path.parent.mkdir()
            trace = dict(decision=sample()["activity"]["decisions"][0],
                         model_trace=dict(host_outcome="MODEL_DECISION", model_messages="PRIVATE_RAW"))
            path.write_text(json.dumps(dict(arms=dict(paper_portfolio=dict(decision_traces=[trace])))))
            audit = root / "financial-audit/audit_trail.jsonl"
            audit.parent.mkdir()
            audit.write_text(json.dumps(dict(event_type="FILL", recorded_at="2026-10-23T18:00:00Z",
                                             payload=dict(fill_id="fill_test", client_id="order_test", price="100.5",
                                                          quantity="2", fee="0.5", api_key="PRIVATE_RAW"))) + "\n" + '{"partial":')
            before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in [path, audit]}
            result = read_activity(root)
            self.assertEqual(len(result["decisions"]), 1)
            self.assertEqual(len(result["events"]), 1)
            self.assertNotIn("PRIVATE_RAW", json.dumps(result))
            self.assertEqual(before, {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in before})

    def test_snapshot_copy_does_not_mutate_input_or_convert_units(self):
        data = sample()["snapshot"]
        before = copy.deepcopy(data)
        result = snapshot_view(data, "mission_test")
        self.assertEqual(data, before)
        self.assertEqual(result["account"]["equity_tmn"], "5000000")


if __name__ == "__main__":
    unittest.main()
