"""Offline monetary oracles; none of these tests measures real-model profitability."""

import asyncio
import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from royin import risk as risk_module
from royin.agent import RoleRunEnvelope, decide
from royin.config import RuntimeConfig
from royin.decision import ReturnForecast
from royin.ledger import Ledger
from royin.model_budget import BudgetBlocked, ModelBudget
from royin.risk import MarketRules, assess_target_net
from scripts import run_market_paper as runner
from tests.test_market_selection import forecast, snapshot


class ContinuationBudgetTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name)/"budget.sqlite3"
        self.config = RuntimeConfig(LLM_COST_BUDGET="2.40", LLM_COST_CURRENCY="USD",
                                    LLM_TOKEN_BUDGET=6_000_000)

    def test_missing_empty_or_corrupt_state_never_bootstraps_a_continuation(self):
        with self.assertRaisesRegex(BudgetBlocked, "MISSING_DURABLE_STATE"):
            ModelBudget(self.config,self.path,require_existing=True)
        self.assertFalse(self.path.exists())
        with closing(sqlite3.connect(self.path)):
            pass
        with self.assertRaisesRegex(BudgetBlocked, "INVALID_DURABLE_STATE"):
            ModelBudget(self.config,self.path,require_existing=True)
        self.path.write_bytes(b"not a sqlite database")
        with self.assertRaisesRegex(BudgetBlocked, "INVALID_DURABLE_STATE"):
            ModelBudget(self.config,self.path,require_existing=True)

    def test_prior_spend_survives_and_deletion_cannot_recreate_the_database(self):
        ModelBudget(self.config,self.path).reserve()
        budget = ModelBudget(self.config,self.path,require_existing=True)
        budget.reserve()
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM model_reservations").fetchone()[0],2)
        self.path.unlink()
        for action in (budget.reserve,lambda:RoleRunEnvelope(budget,scope_id="not-a-new-budget")):
            with self.assertRaisesRegex(BudgetBlocked,"MISSING_DURABLE_STATE"):
                action()
            self.assertFalse(self.path.exists())

    def test_noncontinuation_budget_cannot_reach_owned_network_client(self):
        budget = ModelBudget(self.config,self.path)
        with patch("royin.agent.httpx2.AsyncClient",side_effect=AssertionError("Unexpected client")) as client, \
             self.assertRaisesRegex(BudgetBlocked,"MISSING_DURABLE_STATE"):
            asyncio.run(decide(snapshot("ETHTMN"),config=self.config,budget=budget,
                allowed_symbols=("ETHTMN",)))
        client.assert_not_called()
        self.assertFalse(self.path.exists())

    def test_real_model_missing_state_blocks_before_creating_a_paper_run(self):
        capture = self.path.parent/"must-not-be-created"
        with patch("royin.model_budget.ROOT",self.path.parent), \
             patch.object(runner,"ScannerPublicFeed") as feed, \
             self.assertRaisesRegex(BudgetBlocked,"MISSING_DURABLE_STATE"):
            runner.MarketPaperOrchestrator(run_id="blocked",model_mode="REAL_MODEL",
                config=self.config,capture_dir=capture)
        self.assertFalse(capture.exists())
        feed.assert_not_called()

    def test_cli_reports_blocked_with_zero_http_and_no_artifacts(self):
        capture = self.path.parent/"no-run"
        with patch("royin.model_budget.ROOT",self.path.parent), \
             patch.object(runner,"load_config",return_value=self.config),patch("sys.stdout",new_callable=io.StringIO) as output:
            code = runner.main(["--model-mode","REAL_MODEL","--capture-dir",str(capture)])
        result = json.loads(output.getvalue())
        self.assertEqual(code,2)
        self.assertEqual((result["status"],result["model_http"],result["orders_sent"]),("BLOCKED",0,0))
        self.assertFalse(capture.exists())


class TargetNetTests(unittest.TestCase):
    def check_target(self, *, entry="100", target=".021", fee=".003", step=".01", quantity="10"):
        fc = ReturnForecast.model_validate({**forecast(snapshot("ETHTMN")),
            "reference_price":"100","target_return_fraction":target})
        rules = MarketRules("ETHTMN","ETH","TMN",D(".01"),D(step),D(".01"),D(".01"),D(fee),D(fee))
        return assess_target_net(forecast=fc,rules=rules,quantity=D(quantity),entry_price=D(entry),
            spread_pct=D(".001"),slippage_pct=D(".0005"))

    def test_target_above_old_close_but_below_ask_is_a_loss(self):
        result = self.check_target(entry="103")
        self.assertFalse(result["approved"])
        self.assertEqual(result["exit_price_bound"],"101.94")
        self.assertEqual(D(result["scenarios"][0]["net_at_target_tmn"]),D("-16.74820"))

    def test_both_fee_assets_and_rounding_can_remove_an_apparent_edge(self):
        self.assertFalse(self.check_target(target=".005")["approved"])
        result = self.check_target(target=".05",step="1",quantity="1")
        self.assertFalse(result["approved"])
        self.assertTrue(any(not s["sellable"] for s in result["scenarios"]))

    def test_hand_computed_positive_target_remains_conditional_not_expected_value(self):
        result = self.check_target(target=".05",fee="0")
        self.assertTrue(result["approved"])
        self.assertEqual(result["exit_price_bound"],"104.84")
        self.assertEqual({D(s["net_at_target_tmn"]) for s in result["scenarios"]},{D("48.40")})


class PaperCapacityTests(unittest.TestCase):
    def test_infeasible_real_model_ceiling_stops_before_budget_or_run_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/"no-run"
            with patch.object(runner,"ModelBudget") as budget, self.assertRaisesRegex(
                    ValueError,"BLOCKED_ORDER_CAPACITY"):
                runner.MarketPaperOrchestrator(run_id="infeasible",model_mode="REAL_MODEL",
                    config=RuntimeConfig(),capture_dir=output,order_tmn=D(100000),
                    minimum_notional_tmn=D(100000))
            budget.assert_not_called()
            self.assertFalse(output.exists())

    def test_floor_only_raises_tmn_rules_and_never_converts_units(self):
        rules = runner.build_default_rules("USDTTMN")
        raised = risk_module.rules_with_notional_floor(rules,D(100000))
        self.assertEqual(raised.min_notional,max(rules.min_notional,D(100000)))
        self.assertEqual(risk_module.rules_with_notional_floor(raised,D(50000)),raised)
        from dataclasses import replace
        with self.assertRaises(ValueError):
            risk_module.rules_with_notional_floor(replace(rules,quote_asset="USDT"),D(100000))

    def test_paper_floor_is_bound_to_restart_profile_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            kwargs=dict(run_id="floor",capture_dir=Path(tmp),config=RuntimeConfig(),
                order_tmn=D(150000),minimum_notional_tmn=D(100000))
            obj=runner.MarketPaperOrchestrator(**kwargs)
            try:
                obj._checkpoint_and_export(obj.run_started_at)
                manifest=json.loads((Path(tmp)/"manifest.json").read_text())
                self.assertEqual(manifest["minimum_order_notional_tmn"],"100000")
                self.assertGreaterEqual(obj.rules.min_notional,D(100000))
            finally:
                obj.close()
            restored=runner.MarketPaperOrchestrator(**kwargs)
            restored.close()
            with self.assertRaisesRegex(ValueError,"settings changed"):
                runner.MarketPaperOrchestrator(**{**kwargs,"minimum_notional_tmn":D(50000)})


class InventoryAndCadenceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def make_runner(self):
        obj = runner.MarketPaperOrchestrator(run_id="offline-check",capture_dir=self.root,
            config=RuntimeConfig(),order_tmn=D(200000))
        self.addCleanup(obj.close)
        return obj

    def test_restart_and_candle_boundary_do_not_grant_an_extra_analysis(self):
        obj = self.make_runner()
        feed = MagicMock(requests=0)
        with patch.object(obj,"_handle_entry_cycle",new_callable=AsyncMock) as entry:
            asyncio.run(obj._execute_cycle(feed,8399))
            asyncio.run(obj._execute_cycle(feed,8401))
            entry.assert_awaited_once()
        obj.close()
        restored = self.make_runner()
        with patch.object(restored,"_handle_entry_cycle",new_callable=AsyncMock) as entry:
            asyncio.run(restored._execute_cycle(feed,8698))
            entry.assert_not_awaited()
            asyncio.run(restored._execute_cycle(feed,8699))
            entry.assert_awaited_once()

    def test_real_research_defers_late_cycle_without_claim_and_preserves_cadence_after_restart(self):
        obj = self.make_runner()
        obj.model_mode = "REAL_MODEL"
        feed = MagicMock(requests=0)
        with patch.object(obj,"_handle_entry_cycle",new_callable=AsyncMock) as entry:
            asyncio.run(obj._execute_cycle(feed,8399))
            entry.assert_not_awaited()
        self.assertIsNone(obj.ledger.get_meta("next_entry_analysis_at"))
        self.assertEqual(obj.ledger.get_meta("entry_block_reason"),"DEFERRED_CLOSED_CANDLE_TIME")
        obj.close()
        restored = self.make_runner()
        restored.model_mode = "REAL_MODEL"
        with patch.object(restored,"_handle_entry_cycle",new_callable=AsyncMock) as entry:
            asyncio.run(restored._execute_cycle(feed,8401))
            asyncio.run(restored._execute_cycle(feed,8461))
            entry.assert_awaited_once()
        self.assertEqual(restored.ledger.get_meta("next_entry_analysis_at"),"8701")

    def test_late_research_deferral_never_suppresses_position_monitoring(self):
        obj = self.make_runner()
        obj.model_mode = "REAL_MODEL"
        obj.ledger.set_balance("USDT",D(1))
        state = {"status":"OPEN"}
        obj.ledger.set_meta("protection_USDTTMN",json.dumps(state))
        with patch.object(obj,"_handle_position_cycle",new_callable=AsyncMock) as monitor:
            asyncio.run(obj._execute_cycle(MagicMock(requests=0),8399))
        monitor.assert_awaited_once()
        self.assertIsNone(obj.ledger.get_meta("next_entry_analysis_at"))

    def test_wait_exposure_is_zero_and_custom_limit_is_not_reported_as_inventory(self):
        obj = self.make_runner()
        with patch.object(runner,"ROOT",self.root):
            obj._checkpoint_and_export(1000)
        arm = json.loads((self.root/"manifest.json").read_text())["arms"]["paper_portfolio"]
        self.assertEqual(arm["peak_exposure_tmn"],"0")

    def test_partial_duplicate_and_closing_fills_have_one_durable_round_trip(self):
        ledger = Ledger(self.root/"ledger.sqlite3")
        ledger.set_balance("TMN",D(1000))
        ledger.record_intent(client_id="buy",symbol="USDTTMN",side="BUY",order_type="LIMIT",
            price=D(100),quantity=D(2),timestamp=1000)
        for i in range(2):
            ledger.record_fill(fill_id=f"buy-{i}",client_id="buy",price=D(100),quantity=D(1),
                fee=D(0),fee_asset="TMN",timestamp=1001+i)
        self.assertEqual(ledger.get_meta("peak_inventory_value_TMN"),"200")
        self.assertIsNone(ledger.get_meta("closed_round_trips"))
        ledger.record_intent(client_id="sell",symbol="USDTTMN",side="SELL",order_type="LIMIT",
            price=D(110),quantity=D(2),timestamp=1003)
        for i in range(2):
            args=dict(fill_id=f"sell-{i}",client_id="sell",price=D(110),quantity=D(1),
                fee=D(0),fee_asset="TMN",timestamp=1004+i)
            ledger.record_fill(**args)
            ledger.record_fill(**args)
        restored = Ledger(self.root/"ledger.sqlite3")
        self.assertEqual(restored.get_meta("closed_round_trips"),"1")
        self.assertEqual(restored.get_meta("peak_inventory_value_TMN"),"200")
        self.assertEqual(restored.get_realized_pnl(),D(20))

    def test_observed_quote_peak_survives_exit_and_restart(self):
        obj = self.make_runner()
        risk = runner.RiskResult(True,"technical position","ENTER","USDTTMN",D(1),D(250000),D(242500),D(750))
        obj.broker.submit_order(risk,client_id="peak-buy",timestamp=1000)
        obj.broker.reconcile_order("peak-buy",simulated_state="FILLED",timestamp=1000)
        obj.broker.arm_protection(obj.protection_policy,opened_at=1000,entry_price=D(250000))
        feed = MagicMock()
        feed.get.return_value = ({"success":True,"result":{
            "bid":[{"price":"260000","quantity":"10"}],"ask":[{"price":"260001","quantity":"10"}]}},1010)
        state = json.loads(obj.ledger.get_meta("protection_USDTTMN"))
        asyncio.run(obj._handle_position_cycle(feed,1010,state,allow_model=False))
        self.assertEqual(obj.ledger.get_meta("peak_inventory_value_TMN"),"260000")
        obj.broker.finalize_portfolio(D(260000),timestamp=1011)
        restored = Ledger(obj.db_path)
        self.assertEqual(restored.get_meta("peak_inventory_value_TMN"),"260000")
        self.assertEqual(restored.get_meta("closed_round_trips"),"1")

    def test_funded_forward_windows_are_declared_before_any_inference_and_survive_restart(self):
        obj = runner.MarketPaperOrchestrator(run_id="planned",capture_dir=self.root,
            config=RuntimeConfig(),duration_seconds=10800,cycles=181,interval_seconds=60)
        self.addCleanup(obj.close)
        planned = json.loads(obj.ledger.get_meta("engine_evaluation_windows"))
        self.assertEqual([w["end"]-w["start"] for w in planned],[5400,5400])
        self.assertEqual(planned[0]["end"],planned[1]["start"])
        self.assertFalse(obj.decision_traces)
        obj.close()
        restored = runner.MarketPaperOrchestrator(run_id="planned",capture_dir=self.root,
            config=RuntimeConfig(),duration_seconds=10800,cycles=181,interval_seconds=60)
        self.addCleanup(restored.close)
        self.assertEqual(json.loads(restored.ledger.get_meta("engine_evaluation_windows")),planned)
