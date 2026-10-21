import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from scripts import prepare_market_data

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class PublicPreparationTests(unittest.TestCase):
    def run_probe(self, *, mismatch=False, unsuccessful=False):
        requests = []

        def handle(request):
            requests.append(request)
            if request.url.path == "/hector/web/v1/markets":
                payload = json.loads((FIXTURES / "wallex-public-catalog.json").read_bytes())
                if unsuccessful:
                    payload["success"] = False
            else:
                query = request.url.params
                step = 60 if query["resolution"] == "1" else 3600
                times = list(range(int(query["from"]), int(query["to"]) + 1, step))
                n = len(times)
                payload = {"s": "ok", "t": times, "o": ["10"] * n,
                           "h": ["12"] * n, "l": ["9"] * n,
                           "c": ["10" if mismatch and step == 3600 else "11"] * n,
                           "v": [str(step // 60)] * n}
            return httpx.Response(200, json=payload)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            (root / "config" / "wallex-credit-market-policy.json").write_text(json.dumps({
                "schema_version": 1, "market_type": "SPOT", "leverage_allowed": False,
                "unavailable_markets": ["PAXG/TMN", "PAXG/USDT"],
            }), encoding="utf-8")
            client = httpx.Client(transport=httpx.MockTransport(handle))
            with (
                patch.object(prepare_market_data, "ROOT", root),
                patch.object(prepare_market_data, "SYMBOLS", ("BTCTMN",)),
                patch.object(prepare_market_data, "WINDOWS", (("2026-10-01", "2026-10-02"),)),
                patch.object(prepare_market_data.httpx, "Client", return_value=client),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                exit_code = prepare_market_data.main([])
            report = json.loads((root / "data" / "t02" / "report.json").read_bytes())
            normalized = list((root / "data" / "t02").glob("normalized-*.json"))
            if normalized:
                self.assertEqual(len(json.loads(normalized[0].read_bytes())["candles"]), 96)
            return exit_code, report, requests, len(normalized)

    def test_public_get_only_pipeline_saves_verified_source_and_complete_bars(self):
        code, report, requests, outputs = self.run_probe()
        self.assertEqual(code, 0)
        self.assertEqual(outputs, 1)
        self.assertEqual(report["records"][0]["hourly_reference_mismatches"], 0)
        self.assertEqual(report["account_access"], "BLOCKED_NO_PRIVATE_CONTRACT")
        self.assertEqual(len(requests), 3)
        for request in requests:
            self.assertEqual(request.method, "GET")
            self.assertEqual(request.url.host, "api.wallex.ir")
            self.assertNotIn("x-api-key", request.headers)
            self.assertNotIn("sub-account-client-id", request.headers)

    def test_cross_interval_price_mismatch_blocks_strategy_dataset(self):
        code, report, _, outputs = self.run_probe(mismatch=True)
        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "DEGRADED")
        self.assertEqual(report["records"][0]["hourly_reference_mismatches"], 24)
        self.assertEqual(outputs, 0)

    def test_http_200_with_false_success_is_not_a_success(self):
        code, report, requests, outputs = self.run_probe(unsuccessful=True)
        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "ERROR")
        self.assertEqual(len(requests), 1)
        self.assertEqual(outputs, 0)

    def test_order_endpoint_is_rejected_before_transport(self):
        with self.assertRaises(ValueError):
            prepare_market_data.fetch_public(None, "/v1/account/orders", {}, Path("data"))
