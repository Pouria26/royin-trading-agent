"""Research-contract tests. No exchange, model, or financial-state operations."""

import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from research.candidate_coverage import (
    EVIDENCE_KIND,
    FIT,
    MAX_REQUEST_BYTES,
    RESPONSE_SCHEMA,
    assess_response,
    canonical,
    digest,
    main,
    prepare_capture,
    request_for,
)
from royin.decision import MarketEntryProposal


def capture():
    rows = []
    for i, symbol in enumerate(("BTCTMN", "PUMPTMN", "ETHTMN")):
        rows.append(dict(symbol=symbol, snapshot_sha256=str(i + 1) * 64,
            opportunity_sha256=str(i + 4) * 64, interval_seconds=300, last_close="100",
            evidences=["EV_DATA_FRESH", "EV_CLOSED_BAR_STRUCTURE"],
            historical_return_reference=dict(cutoff=900),
            closed_bar_structure=dict(path_efficiency_20="0.24", prior_high="101"),
            best_bid="99", best_ask="100", execution_cost_context=dict(
                status="ESTIMATE_NOT_ADMISSION", reference_kind="LAST_CLOSE",
                break_even_reference_return_fraction="0.01",
                cash_break_even_reference_return_fraction="0.015" if i < 2 else None,
                capacity=dict(status=FIT if i < 2 else "BLOCKED_MINIMUM_OR_RESIDUAL"))))
    return dict(kind="READ_ONLY_MARKET_REVIEW_CONTEXT", decision=dict(cutoff=900),
                candidates=rows, private_key="MUST_NOT_ENTER_PROJECTED_REQUEST")


def response(prepared):
    items = []
    for row in prepared["input"]["candidates"]:
        if row["recorded_capacity"] != FIT:
            continue
        items.append(dict(symbol=row["symbol"], snapshot_sha256=row["snapshot_sha256"],
            opportunity_sha256=row["opportunity_sha256"], status="ESTIMATED",
            thesis="Closed-bar structure is available.", counterevidence="History is limited.",
            forecast=dict(forecast_id="research-" + row["symbol"], symbol=row["symbol"],
                cutoff=900, reference_price="100", reference_kind="LAST_CLOSE",
                horizon_seconds=3600, return_q10="-0.02", return_q50="-0.001",
                return_q90="0.03", target_return_fraction=None, review_after_seconds=900,
                invalidation="New closed-bar data contradicts the thesis.",
                evidence_ids=["EV_CLOSED_BAR_STRUCTURE"], parent_forecast_id=None)))
    return dict(schema_version=RESPONSE_SCHEMA, input_sha256=prepared["input_sha256"],
                assessments=items)


class CandidateCoverageTests(unittest.TestCase):
    def setUp(self):
        self.raw = canonical(capture())
        self.prepared = prepare_capture(self.raw, horizon_seconds=3600)
        self.response = response(self.prepared)

    def evaluate(self):
        return assess_response(self.prepared, canonical(self.response))

    def test_full_independent_coverage_preserves_negative_forecasts(self):
        report = self.evaluate()
        self.assertEqual(report["required_assessments"], 2)
        self.assertEqual(report["recorded_candidates"], 3)
        self.assertEqual(report["evidence_kind"], EVIDENCE_KIND)
        self.assertFalse(report["trading_enabled"])
        first = report["candidates"][0]["assessment"]
        self.assertEqual(first["forecast"]["return_q50"], "-0.001")
        self.assertEqual(first["quantile_minus_recorded_cost_fraction"]["q50"], "-0.016")
        self.assertFalse(first["median_clears_recorded_cost"])
        self.assertIsNone(report["candidates"][1]["assessment"])

    def test_each_candidate_uses_own_forecast_and_cost(self):
        self.response["assessments"][1]["forecast"]["return_q50"] = "0.02"
        results = {r["symbol"]: r["assessment"] for r in self.evaluate()["candidates"]}
        self.assertFalse(results["BTCTMN"]["median_clears_recorded_cost"])
        self.assertTrue(results["PUMPTMN"]["median_clears_recorded_cost"])
        self.assertEqual(results["PUMPTMN"]["quantile_minus_recorded_cost_fraction"]["q50"], "0.005")

    def test_missing_candidate_is_not_all_market_wait(self):
        self.response["assessments"].pop()
        with self.assertRaisesRegex(ValueError, "exactly once"):
            self.evaluate()

    def test_duplicate_candidate_rejected(self):
        self.response["assessments"][1] = self.response["assessments"][0]
        with self.assertRaisesRegex(ValueError, "exactly once"):
            self.evaluate()

    def test_blocked_candidate_cannot_replace_required_one(self):
        self.response["assessments"][1]["symbol"] = "ETHTMN"
        with self.assertRaisesRegex(ValueError, "exactly once"):
            self.evaluate()

    def test_forecast_bindings_independently_rejected(self):
        original = copy.deepcopy(self.response)
        changes = dict(symbol="PUMPTMN", cutoff=1200, reference_price="101",
                       horizon_seconds=14400, evidence_ids=["EV_INVENTED"],
                       target_return_fraction="0.05", parent_forecast_id="live-original")
        for field, value in changes.items():
            with self.subTest(field=field):
                self.response = copy.deepcopy(original)
                self.response["assessments"][0]["forecast"][field] = value
                with self.assertRaisesRegex(ValueError, "mismatch"):
                    self.evaluate()

    def test_cross_snapshot_or_book_binding_rejected(self):
        for field in ("snapshot_sha256", "opportunity_sha256"):
            with self.subTest(field=field):
                self.response = response(self.prepared)
                self.response["assessments"][0][field] = "a" * 64
                with self.assertRaisesRegex(ValueError, "binding mismatch"):
                    self.evaluate()

    def test_other_input_response_rejected(self):
        self.response["input_sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "different input"):
            self.evaluate()

    def test_prepared_tampering_rejected(self):
        self.prepared["input"]["candidates"][0]["facts"]["last_close"] = "99"
        with self.assertRaisesRegex(ValueError, "binding mismatch"):
            self.evaluate()

    def test_explicit_abstention_is_not_zero_or_no_edge(self):
        self.response["assessments"][0].update(status="INSUFFICIENT_EVIDENCE", forecast=None)
        report = self.evaluate()
        self.assertEqual(report["status"], "COMPLETE_WITH_ABSTENTIONS")
        self.assertEqual(report["abstentions"], 1)
        self.assertIsNone(report["candidates"][0]["assessment"]["median_clears_recorded_cost"])

    def test_abstention_cannot_smuggle_a_forecast(self):
        self.response["assessments"][0]["status"] = "INSUFFICIENT_EVIDENCE"
        with self.assertRaises(ValidationError):
            self.evaluate()

    def test_forecast_id_must_be_unique(self):
        self.response["assessments"][1]["forecast"]["forecast_id"] = self.response["assessments"][0]["forecast"]["forecast_id"]
        with self.assertRaisesRegex(ValueError, "mismatch"):
            self.evaluate()

    def test_monetary_float_rejected(self):
        self.response["assessments"][0]["forecast"]["reference_price"] = 100.0
        with self.assertRaisesRegex(ValueError, "floats"):
            self.evaluate()

    def test_nonfinite_and_disordered_quantiles_rejected(self):
        for value in ("NaN", "Infinity", "0.5"):
            with self.subTest(value=value):
                self.response = response(self.prepared)
                self.response["assessments"][0]["forecast"]["return_q10"] = value
                with self.assertRaises(ValidationError):
                    self.evaluate()

    def test_order_authority_rejected(self):
        self.response["assessments"][0].update(action="ENTER", quantity="100")
        with self.assertRaises(ValidationError):
            self.evaluate()

    def test_research_response_is_not_production_decision(self):
        with self.assertRaises(ValidationError):
            MarketEntryProposal.model_validate(self.response)

    def test_no_unit_cost_fallback_for_missing_cash_cost(self):
        data = capture()
        del data["candidates"][0]["execution_cost_context"]["cash_break_even_reference_return_fraction"]
        with self.assertRaisesRegex(ValueError, "unit costs"):
            prepare_capture(canonical(data), horizon_seconds=3600)

    def test_duplicate_input_and_future_history_rejected(self):
        data = capture()
        data["candidates"][1] = copy.deepcopy(data["candidates"][0])
        with self.assertRaisesRegex(ValueError, "Unique"):
            prepare_capture(canonical(data), horizon_seconds=3600)
        data = capture()
        data["candidates"][0]["historical_return_reference"]["cutoff"] = 1200
        with self.assertRaisesRegex(ValueError, "cutoff"):
            prepare_capture(canonical(data), horizon_seconds=3600)

    def test_no_feasible_candidates_requires_no_forecasts(self):
        data = capture()
        for row in data["candidates"]:
            row["execution_cost_context"]["capacity"]["status"] = "BLOCKED_MINIMUM_OR_RESIDUAL"
        prepared = prepare_capture(canonical(data), horizon_seconds=3600)
        report = assess_response(prepared, canonical(response(prepared)))
        self.assertEqual(report["status"], "NO_RECORDED_FEASIBLE_CANDIDATES")
        self.assertEqual(request_for(prepared)["response_format"]["json_schema"]["schema"]["properties"]["assessments"]["maxItems"], 0)

    def test_request_keeps_named_features_and_omits_private_root_fields(self):
        request = request_for(self.prepared)
        text = canonical(request)
        self.assertNotIn(b"MUST_NOT_ENTER_PROJECTED_REQUEST", text)
        self.assertIn(b"path_efficiency_20", text)
        self.assertNotIn(b"quantity", canonical(json.loads(request["messages"][1]["content"])))
        self.assertLessEqual(len(text), MAX_REQUEST_BYTES)

    def test_oversized_request_is_blocked_not_silently_truncated(self):
        data = capture()
        data["candidates"][0]["volume_pressure_proxy"] = {"large": "x" * MAX_REQUEST_BYTES}
        prepared = prepare_capture(canonical(data), horizon_seconds=3600)
        with self.assertRaisesRegex(ValueError, "byte bound"):
            request_for(prepared)

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            assess_response(self.prepared, b'{"input_sha256":"a","input_sha256":"b"}')

    def test_cli_is_offline_and_never_overwrites_captures(self):
        with tempfile.TemporaryDirectory() as directory, patch("socket.socket", side_effect=AssertionError("network")):
            folder = Path(directory)
            source, prepared_path = folder / "capture.json", folder / "prepared.json"
            source.write_bytes(self.raw)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["prepare", "--capture", str(source), "--horizon-seconds", "3600", "--output", str(prepared_path)]), 0)
                self.assertEqual(main(["prepare", "--capture", str(source), "--horizon-seconds", "3600", "--output", str(source)]), 2)
            self.assertEqual(source.read_bytes(), self.raw)
            prepared_bytes = prepared_path.read_bytes()
            answer = folder / "response.json"
            answer.write_bytes(canonical(response(json.loads(prepared_bytes))))
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["validate", "--prepared", str(prepared_path), "--response", str(answer), "--output", str(folder / "report.json")]), 0)
            self.assertEqual(prepared_path.read_bytes(), prepared_bytes)
            self.assertEqual(digest(source.read_bytes()), digest(self.raw))


if __name__ == "__main__":
    unittest.main()
