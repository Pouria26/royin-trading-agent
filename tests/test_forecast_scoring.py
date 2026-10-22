"""Forecast validation and terminal-return scoring with hand-calculated oracles."""

import unittest
from decimal import Decimal as D

from royin.decision import ReturnForecast, validate_forecast
from royin.evaluation import (
    empirical_interval,
    score_return_forecasts,
    score_zero_baseline,
    winkler_score,
)
from royin.features import extract_features
from royin.market_data import Candle, CandleSeries


def snapshot():
    candles = tuple(Candle(6000 + i * 60, D(100), D(102), D(99), D(101), D(20)) for i in range(35))
    return extract_features(CandleSeries(candles, 60), "USDTTMN", cutoff=8100)


def forecast(**overrides):
    fields = dict(
        forecast_id="fc_1", symbol="USDTTMN", cutoff=8100, reference_price="101",
        reference_kind="LAST_CLOSE", horizon_seconds=10800,
        return_q10="-.01", return_q50=".012", return_q90=".03",
        target_return_fraction=".02", review_after_seconds=1800,
        invalidation="structure breaks", evidence_ids=("EV_DATA_FRESH",),
    )
    fields.update(overrides)
    return ReturnForecast(**fields)


class ForecastValidationTests(unittest.TestCase):
    def test_negative_forecast_is_valid_and_not_clamped(self):
        item = forecast(return_q10="-.05", return_q50="-.01", return_q90=".01")
        self.assertEqual(item.return_q50, D("-.01"))
        validate_forecast(item, snapshot=snapshot(), horizon_min_seconds=600, horizon_max_seconds=10800)

    def test_quantile_crossing_percent_units_and_float_are_rejected(self):
        for overrides in (
            dict(return_q10=".02", return_q50=".01"),
            dict(return_q50=".04", return_q90=".03"),
            dict(return_q50=D("2.5")),  # 2.5 percent written as a fraction
            dict(return_q50=0.012),  # raw float
            dict(horizon_seconds=30),
            dict(review_after_seconds=20000),
        ):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                forecast(**overrides)

    def test_host_horizon_bounds_remaining_time_and_reference_mismatch(self):
        snap = snapshot()
        item = forecast()
        with self.assertRaises(ValueError):
            validate_forecast(item, snapshot=snap, horizon_min_seconds=600, horizon_max_seconds=3600)
        with self.assertRaises(ValueError):
            validate_forecast(item, snapshot=snap, horizon_min_seconds=600, horizon_max_seconds=10800,
                              remaining_seconds=3600)
        with self.assertRaises(ValueError):
            validate_forecast(forecast(reference_price="102"), snapshot=snap,
                              horizon_min_seconds=600, horizon_max_seconds=10800)
        with self.assertRaises(ValueError):
            validate_forecast(forecast(cutoff=8101), snapshot=snap,
                              horizon_min_seconds=600, horizon_max_seconds=10800)

    def test_reviewer_child_cannot_extend_beyond_schema_or_parent_self(self):
        with self.assertRaises(ValueError):
            forecast(forecast_id="fc_2", parent_forecast_id="fc_2")


class WinklerTests(unittest.TestCase):
    def test_hand_example_outside_upper(self):
        # l=-.01, u=.03, y=.04 => .04 + 10*(.01) = .14
        self.assertEqual(winkler_score(D("-.01"), D(".03"), D(".04")), D(".14"))

    def test_inside_is_width_and_lower_tail(self):
        self.assertEqual(winkler_score(D("-.01"), D(".03"), D(".01")), D(".04"))
        self.assertEqual(winkler_score(D("-.01"), D(".03"), D("-.02")), D(".14"))
        with self.assertRaises(ValueError):
            winkler_score(D(".03"), D("-.01"), D("0"))

    def test_empirical_interval_and_zero_baseline(self):
        low, high = empirical_interval([D("-.02"), D("0"), D(".01"), D(".03")])
        self.assertEqual((low, high), (D("-.014"), D(".024")))
        result = score_zero_baseline([D("-.02"), D("0"), D(".01"), D(".03")],
                                     interval=(D("-.01"), D(".02")))
        self.assertEqual(result["n"], 4)
        self.assertEqual(result["coverage"], D("0.5"))
        self.assertEqual(result["mean_width"], D(".03"))


class ForecastScoreTests(unittest.TestCase):
    def test_pending_and_missing_outcomes_stay_visible(self):
        forecasts = [forecast(forecast_id="a"), forecast(forecast_id="b"), forecast(forecast_id="c")]
        result = score_return_forecasts(
            forecasts, {"a": D(".04"), "b": None})
        self.assertEqual((result["issued"], result["scored"], result["pending"], result["missing_outcome"]),
                         (3, 1, 1, 1))
        self.assertEqual(result["rows"][0]["abs_error"], D(".028"))
        self.assertEqual(result["rows"][0]["bias"], D(".028"))
        self.assertFalse(result["rows"][0]["covered"])
        self.assertEqual(result["rows"][0]["winkler"], D(".14"))
        self.assertEqual(result["median_abs_error"], D(".028"))

    def test_coverage_width_and_per_horizon(self):
        forecasts = [
            forecast(forecast_id="a", horizon_seconds=3600),
            forecast(forecast_id="b", horizon_seconds=3600),
            forecast(forecast_id="c", horizon_seconds=10800),
        ]
        result = score_return_forecasts(
            forecasts, {"a": D("-.02"), "b": D(".02"), "c": D(".01")})
        self.assertEqual(result["scored"], 3)
        self.assertEqual(result["coverage"], D(2) / D(3))
        self.assertEqual(result["mean_width"], D(".04"))
        self.assertEqual(result["per_horizon"][3600]["n"], 2)
        self.assertEqual(result["per_horizon"][3600]["coverage"], D("0.5"))

    def test_duplicate_ids_and_bad_quantiles_rejected(self):
        with self.assertRaises(ValueError):
            score_return_forecasts([forecast(), forecast()], {})
        broken = forecast().model_copy(update={"return_q10": D(".05")})
        with self.assertRaises(ValueError):
            score_return_forecasts([broken], {"fc_1": D("0")})


if __name__ == "__main__":
    unittest.main()
