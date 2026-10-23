"""Synthetic shared-execution accounting checks; never evidence of a profitable model."""

import asyncio
import json
import sqlite3
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from royin.broker import PaperBroker
from royin.config import RuntimeConfig
from royin.decision import Decision
from royin.ledger import Ledger
from royin.model_budget import ModelBudget
from royin.model_profiles import PROVIDER_ORIGINS
from royin.risk import RiskResult
from scripts import run_paired_paper as paired
from scripts.run_market_paper import MarketPaperOrchestrator, build_default_rules
from scripts.run_paper_trader import ScanCandidate
from tests.test_market_selection import opportunity, snapshot


class SharedPaperExecutionTests(unittest.TestCase):
    def test_terminal_order_insert_failure_rolls_back_fill_cash_and_stops(self):
        ledger = Ledger()
        ledger.initialize_portfolio(D(5000000), binding="f" * 64, quote_asset="TMN")
        rules = build_default_rules("ETHTMN", tick_size=D(".01"))
        broker = PaperBroker(ledger, rules)
        risk = RiskResult(
            True, "Synthetic atomicity case", "ENTER", "ETHTMN", D(1000), D(100), D(97), D(300)
        )
        broker.submit_order(risk, client_id="buy", timestamp=8100)
        broker.reconcile_order(
            "buy", simulated_state="FILLED", timestamp=8101, executed_price=D(100)
        )
        before = (ledger.get_balance("TMN"), ledger.get_balance("ETH"), ledger.get_realized_pnl())
        with ledger.connection() as db:
            db.execute(
                "CREATE TRIGGER synthetic_disk_failure BEFORE INSERT ON broker_orders "
                "WHEN NEW.side='SELL' BEGIN SELECT RAISE(ABORT,'synthetic final order failure'); END"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            broker.finalize_portfolio(D(103), timestamp=8200)
        self.assertEqual(
            (ledger.get_balance("TMN"), ledger.get_balance("ETH"), ledger.get_realized_pnl()),
            before,
        )
        self.assertEqual(set(broker.orders), {"buy"})
        self.assertEqual(broker.active_stop_prices["ETHTMN"], D(97))
        with ledger.connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM fills").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM order_intents").fetchone()[0], 1)
            db.execute("DROP TRIGGER synthetic_disk_failure")
        broker.finalize_portfolio(D(103), timestamp=8200)
        restored = PaperBroker(ledger, rules)
        self.assertEqual(restored.orders["finalize_8200"].status, "FILLED")
        self.assertEqual(ledger.get_balance("ETH").total, D(0))

    def test_rule_entry_and_model_wait_keep_separate_cash_and_exact_fee_accounting(self):
        with tempfile.TemporaryDirectory() as tmp, patch("time.time", return_value=8105):
            arms = [
                MarketPaperOrchestrator(
                    run_id=name,
                    capture_dir=Path(tmp) / name,
                    config=RuntimeConfig(),
                    duration_seconds=3600,
                    cycles=61,
                    order_tmn=D(150000),
                    minimum_notional_tmn=D(100000),
                )
                for name in ("rule", "ai")
            ]
            try:
                snap = snapshot("ETHTMN")
                opp = opportunity().model_copy(update={"best_bid": D("100.99"), "best_ask": D(101)})
                rules = build_default_rules("ETHTMN", tick_size=D(".01"))
                feed = MagicMock()
                feed.get.return_value = (
                    {
                        "success": True,
                        "result": {
                            "bid": [{"price": "100.99", "quantity": "100000"}],
                            "ask": [{"price": "101", "quantity": "100000"}],
                        },
                    },
                    8105,
                )
                for arm, action in zip(arms, ("ENTER", "WAIT"), strict=True):
                    d = Decision(
                        decision_id=arm.run_id,
                        symbol=snap.symbol,
                        action=action,
                        cutoff=snap.cutoff,
                        snapshot_sha256=snap.snapshot_sha256,
                        evidence_ids=("EV_DATA_FRESH",),
                        reason="Synthetic accounting case",
                        invalidation="Next closed candle",
                    )
                    asyncio.run(
                        arm._apply_entry_decision(
                            feed,
                            d,
                            {snap.symbol: (snap, opp)},
                            primary_snap=snap,
                            report={"market_rules": {snap.symbol: rules}},
                            bootstrap_attempts=[],
                            input_state=arm._replay_input_state(),
                            model_trace={},
                        )
                    )
                rule, ai = arms
                self.assertEqual(ai.ledger.get_balance("TMN").free, D(5000000))
                self.assertEqual(ai.ledger.get_balance("ETH").total, D(0))
                qty = rule.ledger.get_balance("ETH").total
                self.assertGreater(qty, D(0))
                self.assertLessEqual(D(5000000) - rule.ledger.get_balance("TMN").free, D(150000))
                initial = rule.ledger.get_balance("TMN").free
                rule.broker.finalize_portfolio(D(103), timestamp=8200, slippage_pct=D(".0005"))
                # Same host liquidation formula as the engine; fees and slippage reduce proceeds.
                expected = initial + qty * D(103) * D(".9995") * D(".997")
                self.assertEqual(rule.ledger.get_balance("TMN").free, expected)
                self.assertEqual(rule.ledger.get_balance("ETH").total, D(0))
                self.assertEqual(
                    json.loads(rule.ledger.get_meta("protection_ETHTMN"))["status"], "CLOSED"
                )
            finally:
                for arm in arms:
                    arm.close()

    def test_shared_books_fetch_once_preserve_bytes_and_reject_expiry_without_retry(self):
        original = {
            "success": True,
            "result": {
                "bid": [{"price": "100", "quantity": "10"}],
                "ask": [{"price": "101", "quantity": "10"}],
            },
        }
        feed = MagicMock()
        feed.get.return_value = original, 8105
        common = paired.SharedBooks(feed)
        with patch("time.time", return_value=8105):
            first, _ = common.get("/v1/depth", {"symbol": "ETHTMN"}, cutoff=8105)
            first["result"]["bid"][0]["price"] = "999"
            second, _ = common.get("/v1/depth", {"symbol": "ETHTMN"}, cutoff=8105)
            self.assertEqual(second["result"]["bid"][0]["price"], "100")
        with patch("time.time", return_value=8166), self.assertRaisesRegex(ValueError, "expired"):
            common.get("/v1/depth", {"symbol": "ETHTMN"}, cutoff=8166)
        self.assertEqual(feed.get.call_count, 1)

    def test_failed_shared_book_is_not_retried_by_another_arm(self):
        feed = MagicMock()
        feed.get.side_effect = OSError("Synthetic outage")
        common = paired.SharedBooks(feed)
        with self.assertRaises(OSError):
            common.get("/v1/depth", {"symbol": "ETHTMN"}, cutoff=8105)
        with self.assertRaises(ValueError):
            common.get("/v1/depth", {"symbol": "ETHTMN"}, cutoff=8105)
        self.assertEqual(feed.get.call_count, 1)

    def test_portfolio_cash_rebinding_preserves_market_data_and_original_snapshot(self):
        snap = snapshot("ETHTMN")
        before = snap.to_canonical_dict()
        mapped = paired.account_batch({snap.symbol: (snap, opportunity())}, D(4999000))
        changed = mapped[snap.symbol][0]
        self.assertTrue(changed.verify_hash())
        self.assertEqual(changed.available_tmn_cash, D(4999000))
        self.assertNotEqual(changed.snapshot_sha256, snap.snapshot_sha256)
        self.assertEqual(snap.to_canonical_dict(), before)
        for key, value in before.items():
            if key != "available_tmn_cash":
                self.assertEqual(changed.to_canonical_dict()[key], value)

    def test_baseline_has_no_synthetic_trade_quota_and_hold_enters_only_once(self):
        snap = snapshot("ETHTMN")
        batch = {snap.symbol: (snap, opportunity())}
        self.assertEqual(paired.baseline_decision("rule", batch).action, "WAIT")
        self.assertEqual(paired.baseline_decision("hold", batch).action, "ENTER")
        self.assertEqual(paired.baseline_decision("hold", batch, entered=True).action, "WAIT")

    def test_without_explicit_run_no_key_db_or_network_is_touched(self):
        with patch.object(paired, "run", side_effect=AssertionError("Execution forbidden")):
            self.assertEqual(paired.main(["--run-id", "synthetic", "--keys-file", "absent"]), 2)

    def test_coordinator_closes_paper_hold_and_replays_accounting_on_graceful_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "data"
            state.mkdir()
            box = RuntimeConfig(
                BOXAPI_API_KEY="synthetic-box",
                LLM_TOKEN_BUDGET=20000000,
                LLM_COST_BUDGET="2.40",
                LLM_COST_CURRENCY="USD",
            )
            # Synthetic prior reservation allows the real durable continuation check.
            ModelBudget(box, state / "llm-budget.sqlite3").reserve()
            apmix = RuntimeConfig(
                LLM_PROVIDER="apmix",
                LLM_BASE_URL=PROVIDER_ORIGINS["apmix"],
                LLM_MODEL="claude-sonnet-4-6-free",
                APMIX_API_KEY="synthetic-apmix",
                LLM_TOKEN_BUDGET=20000000,
            )
            ModelBudget.initialize_provider_state(apmix, state / "apmix-model-usage.sqlite3")
            keyfile = root / "keys.json"
            keyfile.write_text(
                json.dumps(
                    {
                        "boxapi": {"api_key": "synthetic-box"},
                        "apmix": {"api_key": "synthetic-apmix"},
                    }
                )
            )
            snap = snapshot("ETHTMN")
            opp = opportunity().model_copy(update={"best_bid": D("100.99"), "best_ask": D(101)})
            report = dict(
                status="CANDIDATES",
                batch=[ScanCandidate(snap, D(0), opp)],
                market_rules={snap.symbol: build_default_rules(snap.symbol, tick_size=D(".01"))},
                rejections=[],
                coverage={"accepted": 1},
            )
            feed = MagicMock()
            feed.requests = 0
            feed.captures = []
            feed.get.side_effect = [
                (
                    {
                        "success": True,
                        "result": {
                            "bid": [{"price": "100.99", "quantity": "100000"}],
                            "ask": [{"price": "101", "quantity": "100000"}],
                        },
                    },
                    8105,
                ),
                (
                    {
                        "success": True,
                        "result": {
                            "bid": [{"price": "103", "quantity": "100000"}],
                            "ask": [{"price": "103.01", "quantity": "100000"}],
                        },
                    },
                    8105,
                ),
            ]
            output = root / "output"
            original_write = paired.write_json

            def record(path, value):
                original_write(path, value)
                if path.name == "progress.json":
                    (path.parent / "STOP_REQUESTED").write_text("Synthetic stop")

            async def fake_decide(**kwargs):
                kwargs["model_trace"].update(
                    evidence_kind="FAKE_MODEL", host_outcome="MODEL_DECISION"
                )
                return paired.baseline_decision("rule", kwargs["market_batch"])

            args = SimpleNamespace(
                run_id="synthetic-pair",
                keys_file=keyfile,
                output_dir=output,
                duration_seconds=3600,
                public_get_cap=400,
            )
            with (
                patch("royin.model_budget.ROOT", root),
                patch("time.time", return_value=8105),
                patch.object(paired, "collect_batch", return_value=report),
                patch.object(paired, "ScannerPublicFeed", return_value=feed),
                patch.object(paired, "decide_role", side_effect=fake_decide),
                patch.object(paired, "write_json", side_effect=record),
                patch("httpx2.AsyncClient.send", side_effect=AssertionError("Network forbidden")),
                patch("urllib.request.urlopen", side_effect=AssertionError("Network forbidden")),
            ):
                self.assertEqual(asyncio.run(paired.run(args)), 0)
            result = json.loads((output / args.run_id / "report.json").read_text())
            self.assertEqual(result["status"], "STOPPED_FLAT")
            self.assertEqual(result["completeness"], "PARTIAL")
            self.assertTrue(result["stop_requested"])
            self.assertFalse(result["errors"])
            hold = result["results"]["hold"]["accounting"]
            self.assertEqual(hold["status"], "VERIFIED_RECORDED_ACCOUNTING")
            self.assertEqual(hold["closed_round_trips"], 1)
            self.assertGreater(D(hold["realized_pnl_tmn"]), D(0))
            self.assertEqual(D(hold["realized_pnl_excluding_best_trip_tmn"]), D(0))
            for name in ("boxapi", "apmix", "rule"):
                self.assertEqual(result["results"][name]["accounting"]["closed_round_trips"], 0)
                self.assertEqual(D(result["results"][name]["final_cash_tmn"]), D(5000000))

    def test_one_finalization_failure_does_not_skip_other_arm_exit(self):
        broken, other = MagicMock(), MagicMock()
        broken._finish_current.side_effect = OSError("Synthetic disk failure")
        other._finish_current.side_effect = OSError("Synthetic second finalization")
        errors = []
        result, residual = paired.finalize_arms(
            {"broken": broken, "other": other}, MagicMock(), Path("unused"), errors
        )
        other._finish_current.assert_called_once()
        self.assertTrue(residual)
        self.assertEqual(len(errors), 2)
        self.assertIsNone(result["broken"]["net_return_pct"])
