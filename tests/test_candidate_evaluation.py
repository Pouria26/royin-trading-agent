import json
import unittest
from decimal import Decimal
from pathlib import Path

from royin.evaluation import (
    build_candidate_producer,
    evaluate_candidate_configurations,
    rank_and_select_candidate,
)
from royin.features import extract_features
from royin.market_data import Candle, CandleSeries
from royin.risk import MarketRules, RiskPolicy

ROOT = Path(__file__).resolve().parents[1]


class CandidateEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.rules = MarketRules(
            symbol="USDTTMN",
            base_asset="USDT",
            quote_asset="TMN",
            tick_size=Decimal("1"),
            step_size=Decimal("0.01"),
            min_notional=Decimal("100000"),
            min_quantity=Decimal("1.0"),
            maker_fee_rate=Decimal("0.0025"),
            taker_fee_rate=Decimal("0.0030"),
        )
        self.policy = RiskPolicy(
            max_order_tmn=Decimal("1500000"),
            max_exposure_tmn=Decimal("3000000"),
            stop_loss_pct=Decimal("0.02"),
            max_drawdown_pct=Decimal("0.05"),
            deadline_utc=2000000000,
        )

        plan_path = ROOT / "config" / "candidate-evaluation-plan.json"
        self.plan = json.loads(plan_path.read_text(encoding="utf-8"))
        self.configurations = self.plan["configurations"]

        # Synthetic trending series of 45 bars
        self.trending_candles = [
            Candle(
                open_time=1700000000 + i * 900,
                open=Decimal("60000") + Decimal(i * 100),
                high=Decimal("60150") + Decimal(i * 100),
                low=Decimal("59950") + Decimal(i * 100),
                close=Decimal("60100") + Decimal(i * 100),
                volume=Decimal("200"),
            )
            for i in range(45)
        ]

        # Synthetic oscillating series (for mean reversion)
        self.oscillating_candles = [
            Candle(
                open_time=1700000000 + i * 900,
                open=Decimal("60000") + (Decimal("1000") if i % 4 in (1, 2) else Decimal("-1000")),
                high=Decimal("61200") if i % 4 in (1, 2) else Decimal("59500"),
                low=Decimal("59800") if i % 4 in (1, 2) else Decimal("58800"),
                close=Decimal("60000") + (Decimal("800") if i % 4 in (1, 2) else Decimal("-800")),
                volume=Decimal("150"),
            )
            for i in range(45)
        ]

    def test_all_six_frozen_configurations_have_valid_schemas(self):
        self.assertEqual(len(self.configurations), 6)
        config_ids = [c["id"] for c in self.configurations]
        expected_ids = [
            "trend_0",
            "trend_0_003",
            "trend_0_006",
            "reversion_30",
            "reversion_35",
            "reversion_40",
        ]
        self.assertEqual(config_ids, expected_ids)

    def test_build_candidate_producer_trend_family(self):
        cfg = {"id": "trend_0_003", "family": "trend", "sma_spread": "0.003"}
        producer = build_candidate_producer(cfg)

        series = CandleSeries(tuple(self.trending_candles), 900)
        snap = extract_features(series, "USDTTMN", cutoff=self.trending_candles[-1].open_time + 900)

        decision = producer(snap)
        self.assertIn(decision.action, ("ENTER", "WAIT", "EXIT"))
        self.assertEqual(decision.symbol, "USDTTMN")
        self.assertEqual(decision.cutoff, snap.cutoff)
        self.assertTrue(decision.decision_id.startswith("trend_0_003_"))

    def test_build_candidate_producer_reversion_family(self):
        cfg = {"id": "reversion_35", "family": "mean_reversion", "rsi_entry": 35, "rsi_exit": 65}
        producer = build_candidate_producer(cfg)

        series = CandleSeries(tuple(self.oscillating_candles), 900)
        snap = extract_features(series, "USDTTMN", cutoff=self.oscillating_candles[-1].open_time + 900)

        decision = producer(snap)
        self.assertIn(decision.action, ("ENTER", "WAIT", "EXIT"))
        self.assertEqual(decision.symbol, "USDTTMN")
        self.assertTrue(decision.decision_id.startswith("reversion_35_"))

    def test_evaluate_candidate_configurations_runs_all_six_without_omission(self):
        results = evaluate_candidate_configurations(
            self.trending_candles,
            self.rules,
            self.policy,
            self.configurations,
            initial_capital=Decimal("5000000"),
            interval_seconds=900,
        )
        self.assertEqual(len(results), 6)
        for cfg in self.configurations:
            cid = cfg["id"]
            self.assertIn(cid, results)
            self.assertIn("net_return_pct", results[cid])
            self.assertIn("max_drawdown_pct", results[cid])
            self.assertIn("closed_round_trips", results[cid])
            self.assertIn("total_fees_paid_tmn", results[cid])

    def test_causal_prefix_invariance_for_candidate_decisions(self):
        cfg = {"id": "trend_0", "family": "trend", "sma_spread": "0.0"}
        producer = build_candidate_producer(cfg)

        cutoff = self.trending_candles[35].open_time + 900
        full_series = CandleSeries(tuple(self.trending_candles), 900)
        prefix_series = CandleSeries(tuple(self.trending_candles[:36]), 900)

        snap_full = extract_features(full_series, "USDTTMN", cutoff=cutoff)
        snap_prefix = extract_features(prefix_series, "USDTTMN", cutoff=cutoff)

        self.assertEqual(snap_full.snapshot_sha256, snap_prefix.snapshot_sha256)

        dec_full = producer(snap_full)
        dec_prefix = producer(snap_prefix)

        self.assertEqual(dec_full.action, dec_prefix.action)
        self.assertEqual(dec_full.evidence_ids, dec_prefix.evidence_ids)
        self.assertEqual(dec_full.snapshot_sha256, dec_prefix.snapshot_sha256)

    def test_rank_and_select_candidate_uses_worst_window_net(self):
        # Mock results for 2 development windows
        window_1 = {
            "trend_0": {"net_return_pct": "1.5", "max_drawdown_pct": "1.0"},
            "trend_0_003": {"net_return_pct": "2.0", "max_drawdown_pct": "0.8"},
            "trend_0_006": {"net_return_pct": "0.5", "max_drawdown_pct": "0.5"},
            "reversion_30": {"net_return_pct": "-1.0", "max_drawdown_pct": "2.0"},
            "reversion_35": {"net_return_pct": "-0.5", "max_drawdown_pct": "1.5"},
            "reversion_40": {"net_return_pct": "0.0", "max_drawdown_pct": "1.0"},
        }
        window_2 = {
            "trend_0": {"net_return_pct": "0.8", "max_drawdown_pct": "1.2"},
            "trend_0_003": {"net_return_pct": "1.2", "max_drawdown_pct": "0.9"},
            "trend_0_006": {"net_return_pct": "1.0", "max_drawdown_pct": "0.6"},
            "reversion_30": {"net_return_pct": "-0.5", "max_drawdown_pct": "1.8"},
            "reversion_35": {"net_return_pct": "-0.2", "max_drawdown_pct": "1.2"},
            "reversion_40": {"net_return_pct": "0.1", "max_drawdown_pct": "1.1"},
        }

        # trend_0_003 worst window is 1.2% (min of 2.0 and 1.2), beating trend_0 (min of 1.5 and 0.8 = 0.8)
        selected_id, ranked = rank_and_select_candidate([window_1, window_2], self.configurations)
        self.assertEqual(selected_id, "trend_0_003")
        self.assertEqual(ranked[0]["config_id"], "trend_0_003")
        self.assertEqual(ranked[0]["worst_window_net_return_pct"], "1.2")

    def test_ranking_rejects_empty_incomplete_duplicate_and_nonfinite_evidence(self):
        cfg = self.configurations[:1]
        for windows, configs in [([], cfg), ([{}], cfg),
                ([{cfg[0]['id']: {'net_return_pct': 'NaN', 'max_drawdown_pct': '1'}}], cfg),
                ([{cfg[0]['id']: {'net_return_pct': '1', 'max_drawdown_pct': '1'}}], cfg + cfg)]:
            with self.subTest(windows=windows), self.assertRaises(ValueError):
                rank_and_select_candidate(windows, configs)

    def test_invalid_candidate_configuration_rejected_before_simulation(self):
        for cfg in [
            {'id': 'x', 'family': 'trend', 'sma_spread': 'NaN'},
            {'id': 'x', 'family': 'trend', 'sma_spread': -1},
            {'id': 'x', 'family': 'trend', 'sma_spread': True},
            {'id': 'x', 'family': 'trend', 'sma_spread': '0', 'extra': 1},
            {'id': 'x', 'family': 'mean_reversion', 'rsi_entry': 70, 'rsi_exit': 30},
        ]:
            with self.subTest(cfg=cfg), self.assertRaises(ValueError):
                build_candidate_producer(cfg)
        with self.assertRaises(ValueError):
            evaluate_candidate_configurations(self.trending_candles, self.rules, self.policy,
                                               [self.configurations[0]] * 2)

    def test_new_candidate_families_validation_and_producers(self):
        # Valid breakout configuration
        valid_breakout = {
            "id": "breakout_atr_1_0",
            "family": "volatility_breakout",
            "atr_hurdle": "0.010",
            "min_spread": "0.003",
            "rsi_exit": 75,
        }
        producer_bo = build_candidate_producer(valid_breakout, allowed_symbols=("USDTTMN",))
        self.assertTrue(callable(producer_bo))

        # Valid regime momentum configuration
        valid_regime = {
            "id": "regime_mom_vol12",
            "family": "regime_momentum",
            "sma_spread": "0.005",
            "min_volume_ratio": "1.2",
            "rsi_entry_max": 68,
            "rsi_exit": 75,
        }
        producer_rm = build_candidate_producer(valid_regime, allowed_symbols=("USDTTMN",))
        self.assertTrue(callable(producer_rm))

        # Rejection of invalid breakout configs
        for bad_bo in [
            {"id": "b1", "family": "volatility_breakout", "atr_hurdle": "0"},
            {"id": "b2", "family": "volatility_breakout", "atr_hurdle": "0.01", "min_spread": "0.003", "rsi_exit": 30},
            {"id": "b3", "family": "volatility_breakout", "atr_hurdle": "0.01", "min_spread": "0.003", "rsi_exit": 75, "extra": 1},
        ]:
            with self.subTest(bad_bo=bad_bo), self.assertRaises(ValueError):
                build_candidate_producer(bad_bo)

        # Rejection of invalid regime momentum configs
        for bad_rm in [
            {"id": "r1", "family": "regime_momentum", "sma_spread": "0.005"},
            {"id": "r2", "family": "regime_momentum", "sma_spread": "0.005", "min_volume_ratio": "0.5", "rsi_entry_max": 68, "rsi_exit": 75},
            {"id": "r3", "family": "regime_momentum", "sma_spread": "0.005", "min_volume_ratio": "1.2", "rsi_entry_max": 80, "rsi_exit": 70},
        ]:
            with self.subTest(bad_rm=bad_rm), self.assertRaises(ValueError):
                build_candidate_producer(bad_rm)

    def test_round_2_experiment_plan_contains_all_12_unique_valid_configurations(self):
        plan_r2_path = ROOT / "config" / "strategy-experiment-plan.json"
        self.assertTrue(plan_r2_path.exists())
        plan_r2 = json.loads(plan_r2_path.read_text(encoding="utf-8"))
        self.assertEqual(len(plan_r2["configurations"]), 12)
        cids = [c["id"] for c in plan_r2["configurations"]]
        self.assertEqual(len(set(cids)), 12)

        # Ensure all 12 producers can be built without error
        for cfg in plan_r2["configurations"]:
            producer = build_candidate_producer(cfg, allowed_symbols=("USDTTMN",))
            self.assertTrue(callable(producer))


if __name__ == "__main__":
    unittest.main()
