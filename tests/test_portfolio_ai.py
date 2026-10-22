"""Portfolio wiring evidence only; synthetic prices and fake SDK model."""

import copy
import unittest
from dataclasses import replace
from decimal import Decimal as D
from unittest.mock import patch

from royin.evaluation import always_wait_decision, recorded_portfolio_producer, run_simulation
from scripts.evaluate_portfolio_ai import main, run_self_check, synthetic_scenario


class PortfolioReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = run_self_check()

    def test_fake_replay_cash_oracle_and_each_arm_own_cash_path(self):
        report = self.report
        self.assertEqual(report["primary_status"], "BLOCKED_DATA")
        self.assertEqual(report["paid_requests"], 0)
        cash = report["arms"]["cash"]
        self.assertEqual(cash["fills"], [])
        self.assertTrue(all(D(p["net_equity_tmn"]) == 5000000 for p in cash["equity_curve"]))
        ai = report["arms"]["rule_ai"]
        inputs = [t["snapshot"] for t in ai["decision_traces"]]
        self.assertTrue(any(D(s["current_position_base"]) > 0 for s in inputs))
        self.assertTrue(any(D(s["available_tmn_cash"]) < 5000000 for s in inputs))
        self.assertTrue(
            any(
                a["decision"]["action"] != b["decision"]["action"]
                for a, b in zip(
                    ai["decision_traces"], report["arms"]["rule"]["decision_traces"], strict=True
                )
            )
        )
        for arm in report["arms"].values():
            last = arm["equity_curve"][-1]
            self.assertEqual(
                D(last["net_equity_tmn"]),
                D(5000000) + D(last["realized_pnl_tmn"]) + D(last["unrealized_pnl_tmn"]),
            )
            self.assertEqual(arm["equity_curve"][-1]["phase"], "FINAL_SETTLEMENT")

    def test_any_binding_or_own_state_tamper_rejected(self):
        report = self.report
        for field in report["bindings"]:
            records = copy.deepcopy(report["model_records"])
            records[0]["manifest"][field] = "tampered"
            with self.subTest(field=field), self.assertRaises(ValueError):
                recorded_portfolio_producer(records, report["bindings"], source="FAKE_MODEL")
        from royin.features import extract_features
        from royin.market_data import CandleSeries

        candles, _, _ = synthetic_scenario()
        record = report["model_records"][0]
        snap = extract_features(
            CandleSeries(tuple(candles[:31]), 3600),
            "USDTTMN",
            cutoff=record["snapshot"]["cutoff"],
            available_tmn_cash=D("4000000"),
        )
        replay = recorded_portfolio_producer(
            report["model_records"], report["bindings"], source="FAKE_MODEL"
        )
        with self.assertRaisesRegex(ValueError, "exact own-ledger"):
            replay(snap)
        with self.assertRaises(ValueError):
            recorded_portfolio_producer(
                report["model_records"], report["bindings"], source="REAL_MODEL"
            )

    def test_future_prices_change_outcome_not_earlier_inputs(self):
        candles, rules, policy = synthetic_scenario()
        one = run_simulation(
            candles,
            always_wait_decision,
            rules,
            policy,
            interval_seconds=3600,
            enable_logging=False,
        )
        candles[-1] = replace(candles[-1], high=D("900000"), close=D("800000"))
        two = run_simulation(
            candles,
            always_wait_decision,
            rules,
            policy,
            interval_seconds=3600,
            enable_logging=False,
        )
        self.assertEqual(one["decision_traces"], two["decision_traces"])

    def test_no_fill_scenario_has_no_invented_assets(self):
        from royin.evaluation import buy_and_hold_decision

        candles, rules, policy = synthetic_scenario()
        result = run_simulation(
            candles,
            buy_and_hold_decision,
            rules,
            policy,
            interval_seconds=3600,
            enable_logging=False,
            no_fill=True,
        )
        self.assertEqual(result["fills"], [])
        self.assertEqual(D(result["final_equity_mtm_tmn"]), D(5000000))
        self.assertEqual(result["episodes"], [])

    def test_host_blocks_fake_entry_at_deadline_and_invalid_cost(self):
        from royin.decision import Decision

        candles, rules, policy = synthetic_scenario()

        def unsafe(snapshot):
            return Decision(
                decision_id=f"unsafe_{snapshot.cutoff}",
                symbol=snapshot.symbol,
                cutoff=snapshot.cutoff,
                snapshot_sha256=snapshot.snapshot_sha256,
                action="ENTER",
                evidence_ids=("EV_DATA_FRESH",),
                reason="Unsafe fake",
                invalidation="Now",
            )

        expired = replace(policy, deadline_utc=candles[30].open_time)
        result = run_simulation(
            candles, unsafe, rules, expired, interval_seconds=3600, enable_logging=False
        )
        self.assertEqual(result["fills"], [])
        self.assertTrue(all(not t["risk"]["approved"] for t in result["decision_traces"]))
        for cost in (D(1), D("NaN"), D("-.1")):
            with self.assertRaises(ValueError):
                run_simulation(
                    candles, unsafe, rules, policy, slippage_pct=cost, enable_logging=False
                )

    def test_default_cli_blocks_without_configuration_or_model_io(self):
        with patch("scripts.evaluate_portfolio_ai.run_self_check") as run, patch("builtins.print"):
            self.assertEqual(main([]), 2)
        run.assert_not_called()
