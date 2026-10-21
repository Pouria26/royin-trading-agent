import copy
import unittest

from scripts.audit_market_data import profile_history


class HistoricalContractTests(unittest.TestCase):
    def setUp(self):
        self.payload = {
            "s": "ok",
            "t": [0, 900, 1800],
            "o": ["10"] * 3,
            "h": ["12"] * 3,
            "l": ["9"] * 3,
            "c": ["11"] * 3,
            "v": ["2"] * 3,
        }

    def test_end_boundary_is_excluded(self):
        result = profile_history(self.payload, 0, 1800)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["selected_rows"], 2)
        self.assertEqual(result["boundary_end_rows_excluded"], 1)

    def test_length_mismatch_and_unavailable_are_errors(self):
        for payload in ({"s": "no_data"}, {**self.payload, "c": []}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                profile_history(payload, 0, 1800)

    def test_gap_and_duplicate_do_not_pass(self):
        self.payload["t"] = [0, 0, 1800]
        result = profile_history(self.payload, 0, 1800)
        self.assertEqual(result["status"], "DEGRADED")
        self.assertEqual(result["duplicates"], 1)
        self.assertEqual(result["missing_candles"], 1)

    def test_invalid_price_or_ohlc_does_not_pass(self):
        for invalid in ("NaN", "Infinity", "-1", "13", None, True):
            payload = copy.deepcopy(self.payload)
            payload["c"][0] = invalid
            with self.subTest(invalid=invalid):
                self.assertEqual(profile_history(payload, 0, 1800)["status"], "DEGRADED")

    def test_out_of_order_and_out_of_range_are_visible(self):
        self.payload["t"] = [900, 0, 2700]
        result = profile_history(self.payload, 0, 1800)
        self.assertEqual(result["non_increasing_pairs"], 1)
        self.assertEqual(result["outside_requested_range"], 1)

    def test_future_prices_do_not_enter_the_selected_sample(self):
        original = profile_history(self.payload, 0, 1800)
        self.payload["c"][2] = "not a number"
        self.assertEqual(profile_history(self.payload, 0, 1800), original)

    def test_resolution_mismatch_is_not_reported_as_complete(self):
        self.payload["t"] = [0, 60, 120]
        result = profile_history(self.payload, 0, 900)
        self.assertEqual(result["status"], "DEGRADED")
        self.assertEqual(result["requested_interval_seconds"], 900)
        self.assertEqual(result["modal_observed_interval_seconds"], 60)
        self.assertEqual(result["off_grid_candles"], 2)


if __name__ == "__main__":
    unittest.main()
