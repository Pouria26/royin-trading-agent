import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.evaluate_candidates import ROOT, evaluate_diagnostics


class CandidateDiagnosticTests(unittest.TestCase):
    def test_exact_72_hour_windows_preserve_diagnostic_gate_and_own_warmup(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            start = 1788220800
            data = {"symbol": "USDTTMN", "base_asset": "USDT", "quote_asset": "TMN",
                    "interval_seconds": 3600, "cutoff": start + 103 * 3600,
                    "incomplete_bins": [], "candles": [
                        {"open_time": start + i * 3600, "open": "100000", "high": "100100",
                         "low": "99900", "close": "100000", "volume": "100"}
                        for i in range(103)]}
            raw = json.dumps(data).encode()
            (directory / "data.json").write_bytes(raw)
            record = {"status": "ACCEPTED", "path": "data.json", "symbol": "USDTTMN",
                      "interval_seconds": 3600, "start": start, "end": data["cutoff"],
                      "sha256": hashlib.sha256(raw).hexdigest(), "purpose": "DIAGNOSTIC_ONLY"}
            manifest = directory / "manifest.json"
            manifest.write_text(json.dumps({"schema_version": 1, "datasets": [record]}))
            digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
            report = evaluate_diagnostics(manifest, digest, ROOT / "config/candidate-evaluation-plan.json")
            self.assertFalse(report["candidate_shadow_approved"])
            self.assertIsNone(report["selected_candidate"])
            windows = report["datasets"][0]["windows"]
            self.assertEqual(len(windows), 1)
            self.assertEqual(windows[0]["end"] - windows[0]["start"], 72 * 3600)
            self.assertEqual(windows[0]["start"] - windows[0]["warmup_start"], 31 * 3600)
            self.assertEqual(len(windows[0]["results"]), 6)
            self.assertFalse(report["datasets"][0]["timeframe_matches_frozen_plan"])
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                evaluate_diagnostics(manifest, "0" * 64, ROOT / "config/candidate-evaluation-plan.json")


if __name__ == "__main__":
    unittest.main()
