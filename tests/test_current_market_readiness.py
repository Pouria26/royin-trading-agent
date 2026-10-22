"""Regressions for market execution boundaries, independent of model profitability."""
import asyncio
import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import MagicMock, patch

from royin.agent import RoleRunEnvelope
from royin.config import RuntimeConfig
from royin.decision import MarketEntryProposal, bind_decision
from royin.market_data import Candle
from royin.model_budget import BudgetBlocked, ModelBudget
from royin.risk import RiskResult
from scripts import run_market_paper as runner
from scripts.run_paper_trader import MarketShortlistRow, ScanCandidate, ScannerPublicFeed
from tests.test_market_scanner import catalog
from tests.test_market_selection import enter_proposal, opportunity, snapshot


class CurrentMarketReadinessTests(unittest.TestCase):
    def make_runner(self, **kwargs):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        o = runner.MarketPaperOrchestrator(run_id="readiness-test", config=RuntimeConfig(),
            capture_dir=Path(tmp.name), **kwargs)
        self.addCleanup(o.close)
        return o

    def test_prefix_settlement_uses_last_processed_price_not_dataset_future(self):
        candles = [Candle(900000+i*900, D(99900+i*100), D(100001+i*100),
                         D(99900+i*100), D(100000+i*100), D(100)) for i in range(42)]
        o = self.make_runner(mode="HISTORICAL_REPLAY", cycles=5)
        fixture = o.capture_dir / "fixture.json"
        fixture.write_text("{}", encoding="utf-8")
        original = runner.PaperBroker.finalize_portfolio
        prices = []
        def settle(broker, price, **kwargs):
            prices.append(price)
            return original(broker, price, **kwargs)
        with patch.object(runner, "load_dataset", return_value=({"symbol":"USDTTMN", "interval_seconds":900}, candles)), \
             patch.object(runner, "fee_aware_entry", return_value=True), \
             patch.object(o, "_checkpoint_and_export"), patch.object(o, "generate_summary", return_value={}), \
             patch.object(runner.PaperBroker, "finalize_portfolio", autospec=True, side_effect=settle):
            asyncio.run(o.run_historical_replay(fixture))
        self.assertEqual(prices, [candles[35].close])

    def test_broker_rejects_wrong_symbol_before_reserving_funds(self):
        o = self.make_runner()
        risk = RiskResult(True, "wrong market", "ENTER", "BTCTMN", D(1), D(300000), D(294000), D(900))
        with self.assertRaisesRegex(ValueError, "symbol"):
            o.broker.submit_order(risk, client_id="wrong", timestamp=1000)
        self.assertEqual(o.ledger.get_balance("TMN").locked, D(0))

    def test_residual_inventory_stops_before_paid_market_selection(self):
        o = self.make_runner()
        o.ledger.set_balance("USDT",D(".001"))
        o.ledger.set_meta("protection_USDTTMN",json.dumps({"status":"CLOSED","last_bid":"250000"}))
        with patch.object(o,"_handle_entry_cycle") as entry:
            asyncio.run(o._execute_cycle(MagicMock(),8105))
        entry.assert_not_awaited()
        self.assertTrue(o.shutdown_requested)
        self.assertEqual(o.ledger.get_meta("entry_block_reason"),"UNPROTECTED_OR_RESIDUAL_INVENTORY")

    def test_cancelled_model_research_joins_owned_collector_before_returning(self):
        o = self.make_runner()
        o.model_mode,o.run_envelope = "REAL_MODEL",object()
        snap = snapshot("ETHTMN")
        started,release,finished = threading.Event(),threading.Event(),threading.Event()
        def scan(*args,**kwargs):
            if threading.current_thread() is not threading.main_thread():
                started.set()
                self.assertTrue(release.wait(2))
                finished.set()
            return dict(batch=[ScanCandidate(snap,D(0),opportunity())],cutoff=8100,
                market_rules={"ETHTMN":runner.build_default_rules("ETHTMN")},coverage={},errors=[])
        async def infer(*args,**kwargs):
            task = asyncio.create_task(kwargs["market_loader"](("ETHTMN",)))
            self.assertTrue(await asyncio.to_thread(started.wait,2))
            task.cancel()
            release.set()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertTrue(finished.is_set())
            return runner.RoleDecisionProposal(role="ENTRY_ANALYST",action="WAIT",symbol=snap.symbol,
                cutoff=snap.cutoff,snapshot_sha256=snap.snapshot_sha256,evidence_ids=("EV_DATA_FRESH",),
                reason="synthetic cancellation boundary",invalidation="next cycle")
        feed = ScannerPublicFeed(o.capture_dir/"raw")
        with patch.object(runner,"public_symbols",return_value=(catalog(),8105,{"ETHTMN"})), \
             patch.object(runner,"scan_current_market",side_effect=scan), \
             patch.object(runner,"decide_role",side_effect=infer),patch("time.time",return_value=8105):
            asyncio.run(o._handle_entry_cycle(feed,8105))
        self.assertTrue(finished.is_set())
        self.assertIsNone(feed.deadline_monotonic)
        self.assertEqual(o.ledger.get_balance("TMN").free,D(5000000))

    def test_catalog_received_after_cycle_start_is_not_mislabeled_future(self):
        o = self.make_runner()
        o.model_mode,o.run_envelope = "REAL_MODEL",object()
        snap = snapshot("ETHTMN")
        decision = runner.RoleDecisionProposal(role="ENTRY_ANALYST",action="WAIT",symbol=snap.symbol,
            cutoff=snap.cutoff,snapshot_sha256=snap.snapshot_sha256,evidence_ids=("EV_DATA_FRESH",),
            reason="synthetic clock boundary",invalidation="next cycle")
        with patch.object(runner,"public_symbols",return_value=(catalog(),8106,{"ETHTMN"})), \
             patch.object(runner,"scan_current_market",return_value=dict(batch=[ScanCandidate(snap,D(0),opportunity())],
                market_rules={"ETHTMN":runner.build_default_rules("ETHTMN")})), \
             patch.object(runner,"decide_role",return_value=decision) as infer,patch("time.time",return_value=8106):
            asyncio.run(o._handle_entry_cycle(MagicMock(),8105))
        self.assertEqual([row.symbol for row in infer.call_args.kwargs["market_universe"].markets],["ETHTMN"])

    def test_empty_research_universe_skips_deep_scan_and_paid_model(self):
        o = self.make_runner()
        o.model_mode,o.run_envelope = "REAL_MODEL",object()
        with patch.object(runner,"public_symbols",return_value=(catalog(),8105,set())), \
             patch.object(runner,"scan_current_market") as scan,patch.object(runner,"decide_role") as infer, \
             patch("time.time",return_value=8105):
            asyncio.run(o._handle_entry_cycle(MagicMock(),8105))
        scan.assert_not_called()
        infer.assert_not_awaited()
        self.assertIn("NO_ELIGIBLE_LIQUID_RESEARCH_UNIVERSE",o.decision_traces[-1]["decision"]["reason"])

    def test_quote_failure_preserves_old_timestamp_instead_of_refreshing_it(self):
        o = self.make_runner()
        feed = MagicMock()
        feed.get.side_effect = OSError("offline")
        with patch.object(o.broker, "observe_quote", return_value={"status":"STALE_QUOTE", "action":"WAIT"}) as observe:
            asyncio.run(o._handle_position_cycle(feed, 2000, {"last_bid":"100", "last_source_time":1100}))
        self.assertEqual(observe.call_args.kwargs["source_time"], 1100)

    def test_position_quote_reads_official_bid_array(self):
        o = self.make_runner()
        feed = MagicMock()
        feed.get.return_value = ({"success":True, "result":{"bid":[{"price":"105", "quantity":"5"}]}}, 2000)
        with patch.object(o.broker, "observe_quote", return_value={"status":"PROTECTED", "action":"WAIT"}) as observe:
            asyncio.run(o._handle_position_cycle(feed, 2000, {"last_bid":"100", "last_source_time":1100}))
        self.assertEqual(observe.call_args.args[0], D(105))

    def test_summary_values_open_position_at_last_observed_bid(self):
        o = self.make_runner()
        o.ledger.set_balance("USDT", D(2))
        o.ledger.set_meta("protection_USDTTMN", json.dumps({"last_bid":"250000"}))
        self.assertEqual(D(o.generate_summary()["final_equity_tmn"]), D(5500000))
        self.assertEqual(o.generate_summary()["status"], "PARTIAL")

    def test_failed_public_attempt_is_durable_before_network_and_not_refunded(self):
        o = self.make_runner(public_get_cap=48)
        feed = ScannerPublicFeed(o.capture_dir/"raw", max_requests=48, before_request=o._reserve_public_request)
        def network(*args, **kwargs):
            self.assertEqual(o.ledger.get_meta("engine_public_attempts"), "1")
            raise OSError("timeout")
        with patch("urllib.request.urlopen", side_effect=network), patch("time.time", return_value=8100), self.assertRaises(OSError):
            feed.get("/v1/depth", {"symbol":"USDTTMN"}, cutoff=8100)
        o.close()
        restored = runner.MarketPaperOrchestrator(run_id=o.run_id, capture_dir=o.capture_dir,
            config=RuntimeConfig(), public_get_cap=48)
        self.addCleanup(restored.close)
        self.assertEqual(restored.ledger.get_meta("engine_public_attempts"), "1")
        restored.ledger.set_meta("engine_public_attempts", "48")
        with self.assertRaisesRegex(ValueError, "cap"):
            restored._reserve_public_request()

    def test_terminal_liquidation_has_hand_calculated_cash_and_stopped_worker(self):
        o = self.make_runner()
        o.ledger.record_intent(client_id="entry",symbol="USDTTMN",side="BUY",order_type="LIMIT",
            price=D(250000),quantity=D(1),timestamp=1000,quote_asset="TMN",base_asset="USDT")
        o.ledger.record_fill(fill_id="entry-fill",client_id="entry",price=D(250000),quantity=D(1),
            fee=D(750),fee_asset="TMN",timestamp=1001)
        o.ledger.set_meta("protection_USDTTMN",json.dumps({"last_bid":"250000", "status":"OPEN"}))
        feed = MagicMock()
        feed.get.return_value = ({"success":True,"result":{"bid":[{"price":"260000","quantity":"10"}]}},2000)
        with patch("time.time",return_value=2000):
            o._finish_current(feed)
        # 5M -250000 -750 +260000*(1-.0005)*(1-.003).
        self.assertEqual(o.ledger.get_balance("TMN").free,D("5008340.3900000"))
        self.assertEqual(o.ledger.get_balance("USDT").total,D(0))
        self.assertEqual(o.ledger.get_meta("engine_lifecycle"),"STOPPED_FLAT")
        self.assertEqual(json.loads(o.ledger.get_meta("protection_USDTTMN"))["status"],"CLOSED")
        self.assertEqual(feed.get.call_args.kwargs["max_age_seconds"],0)
        self.assertEqual(o.generate_summary()["status"],"COMPLETED")

    def test_terminal_failed_or_shallow_quote_cannot_fake_liquidate(self):
        for response in (None, {"success":True,"result":{"bid":[{"price":"260000","quantity":".1"}]}}):
            with self.subTest(response=response):
                o = self.make_runner()
                o.ledger.set_balance("USDT",D(1))
                o.ledger.set_meta("protection_USDTTMN",json.dumps({"last_bid":"250000"}))
                feed = MagicMock()
                if response is None:
                    feed.get.side_effect = OSError("no quote")
                else:
                    feed.get.return_value = (response,2000)
                with patch("time.time",return_value=2000):
                    o._finish_current(feed)
                self.assertEqual(o.ledger.get_balance("USDT").total,D(1))
                self.assertEqual(o.ledger.get_meta("engine_lifecycle"),"STOPPED_OPEN")
                self.assertEqual(o.generate_summary()["status"],"PARTIAL")

    def test_current_loop_finishes_and_persists_cycles_and_manifest_budget(self):
        o = self.make_runner()
        with patch.object(runner,"ROOT",o.capture_dir), patch.object(o,"_execute_cycle") as cycle, \
             patch.object(o,"_finish_current", wraps=o._finish_current) as finish:
            result = asyncio.run(o.run())
        cycle.assert_awaited_once()
        finish.assert_called_once()
        self.assertEqual(o.ledger.get_meta("engine_completed_cycles"),"1")
        self.assertEqual(result["status"],"COMPLETED")
        manifest = json.loads((o.capture_dir/"manifest.json").read_text())
        self.assertEqual(manifest["worker_state"],"STOPPED_FLAT")
        self.assertEqual(manifest["public_get_cap"],32)
        self.assertEqual(manifest["public_get_attempts"],0)

    def test_cycle_limit_bounds_funded_horizon_and_checkpoint_is_after_decision(self):
        o = self.make_runner(duration_seconds=36000,cycles=2,interval_seconds=30)
        self.assertEqual(o.protection_policy.deadline_utc,o.run_started_at+30)
        single = self.make_runner(duration_seconds=36000,cycles=1)
        self.assertEqual(single.protection_policy.deadline_utc,single.run_started_at)
        clock = [o.run_started_at]
        async def decide(*args):
            clock[0] += 12
            o.request_shutdown()
        with patch.object(o,"_execute_cycle",side_effect=decide), \
             patch.object(o,"_finish_current"),patch.object(o,"_checkpoint_and_export") as checkpoint, \
             patch.object(runner.time,"time",side_effect=lambda:clock[0]):
            asyncio.run(o.run())
        self.assertEqual(checkpoint.call_args_list[0].args[0],o.run_started_at+12)

    def test_dashboard_balance_uses_selected_base_asset(self):
        o = self.make_runner()
        o.rules = runner.build_default_rules("ETHTMN")
        o.broker = runner.PaperBroker(o.ledger,o.rules)
        with patch.object(runner,"ROOT",o.capture_dir):
            o._checkpoint_and_export(2000)
        dashboard = json.loads((o.capture_dir/".local/dashboard/engine-snapshot.json").read_text())
        self.assertIn("ETH",dashboard["account"]["balances"])
        self.assertNotIn("USDT",dashboard["account"]["balances"])

    def test_real_entry_binds_selected_symbol_horizon_and_restarts_same_policy(self):
        o = self.make_runner()
        snap = snapshot("ETHTMN")
        opp = opportunity().model_copy(update={"best_ask":D(101),"best_bid":D(100)})
        proposal = enter_proposal(snap, horizon=7200)
        proposal["opportunity_sha256"] = opp.sha256
        proposal["review_after_seconds"] = 600
        proposal["forecast"]["review_after_seconds"] = 600
        decision = bind_decision(MarketEntryProposal.model_validate(proposal),decision_id="chosen-eth",
            symbol=snap.symbol,cutoff=snap.cutoff,snapshot_sha256=snap.snapshot_sha256,
            available_evidence_ids=tuple(snap.evidences))
        o.model_mode, o.run_envelope = "REAL_MODEL", object()
        with patch.object(runner,"public_symbols",return_value=(catalog(),8105,{"ETHTMN"})), \
             patch.object(runner,"scan_current_market",return_value={"batch":[ScanCandidate(snap,D(0),opp)],
                 "market_rules":{"ETHTMN":runner.build_default_rules("ETHTMN")}}), \
             patch.object(runner,"decide_role",return_value=decision), patch("time.time",return_value=8105):
            asyncio.run(o._handle_entry_cycle(MagicMock(),8105))
        self.assertEqual(o.rules.symbol,"ETHTMN")
        self.assertEqual(o.protection_policy.hard_holding_seconds,7195)
        self.assertEqual(8105+o.protection_policy.hard_holding_seconds,decision.forecast.cutoff+decision.forecast.horizon_seconds)
        self.assertEqual(o.protection_policy.review_interval_seconds,600)
        saved_hash = o.protection_policy.sha256
        self.assertTrue(o.decision_traces[-1]["client_id"])
        o.close()
        restarted = runner.MarketPaperOrchestrator(run_id=o.run_id,config=RuntimeConfig(),capture_dir=o.capture_dir)
        try:
            self.assertEqual(restarted.rules.symbol,"ETHTMN")
            self.assertEqual(restarted.protection_policy.sha256,saved_hash)
        finally:
            restarted.close()

    def test_run_envelope_restart_cannot_reset_model_allowance(self):
        o = self.make_runner()
        cfg = RuntimeConfig(LLM_COST_BUDGET=D(".5"),LLM_TOKEN_BUDGET=100000,LLM_COST_CURRENCY="USD")
        budget = ModelBudget(cfg,o.capture_dir/"budget.sqlite3")
        first = RoleRunEnvelope(budget,duration_seconds=3600,scope_id="shared")
        for _ in range(48):
            first.claim_run()
        restarted = RoleRunEnvelope(budget,duration_seconds=3600,scope_id="shared")
        self.assertEqual(restarted.agent_runs,48)
        with self.assertRaises(BudgetBlocked):
            restarted.claim_run()
        with self.assertRaises(BudgetBlocked):
            RoleRunEnvelope(budget,duration_seconds=7200,scope_id="shared")
        with closing(sqlite3.connect(budget.path)) as db:
            self.assertEqual(db.execute("SELECT agent_runs FROM role_run_envelopes").fetchone()[0],48)

    def test_legacy_envelope_keeps_original_cost_cap(self):
        o = self.make_runner()
        cfg = RuntimeConfig(LLM_COST_BUDGET=D(".5"),LLM_TOKEN_BUDGET=100000,LLM_COST_CURRENCY="USD")
        budget = ModelBudget(cfg,o.capture_dir/"legacy-budget.sqlite3")
        import time
        with closing(sqlite3.connect(budget.path)) as db, db:
            db.execute("CREATE TABLE role_run_envelopes (scope TEXT PRIMARY KEY, started REAL, duration INTEGER, agent_runs INTEGER, http_attempts INTEGER, reserved TEXT)")
            db.execute("INSERT INTO role_run_envelopes VALUES (?,?,3600,2,4,'0.008')",("legacy",time.time()))
        resumed = RoleRunEnvelope(budget,duration_seconds=3600,scope_id="legacy")
        self.assertEqual(resumed.cost_limit_usd,D(".04"))
        self.assertEqual(resumed.http_attempts,4)
        self.assertEqual(resumed.agent_limit,12)
        self.assertEqual(RoleRunEnvelope(budget,duration_seconds=3600,scope_id="fresh").cost_limit_usd,D(".50"))

    def test_host_rechecks_denied_symbol_even_if_scanner_proposes_it(self):
        o = self.make_runner()
        snap = snapshot("TONTMN")
        opp = opportunity().model_copy(update={"symbol":"TONTMN","best_ask":D(101),"best_bid":D(100)})
        proposal = enter_proposal(snap,horizon=7200)
        proposal["opportunity_sha256"] = opp.sha256
        decision = bind_decision(MarketEntryProposal.model_validate(proposal),decision_id="banned-candidate",
            symbol=snap.symbol,cutoff=snap.cutoff,snapshot_sha256=snap.snapshot_sha256,available_evidence_ids=tuple(snap.evidences))
        o.model_mode,o.run_envelope = "REAL_MODEL",object()
        with patch.object(runner,"public_symbols",return_value=(catalog(),8105,{"TONTMN"})), \
             patch.object(runner,"catalog_candidates",return_value=(MarketShortlistRow("TONTMN",D(100000000),D(1),8105,"c"*64),)), \
             patch.object(runner,"scan_current_market",return_value={"batch":[ScanCandidate(snap,D(0),opp)],
                 "market_rules":{"TONTMN":runner.build_default_rules("TONTMN")}}), \
             patch.object(runner,"decide_role",return_value=decision),patch("time.time",return_value=8105):
            asyncio.run(o._handle_entry_cycle(MagicMock(),8105))
        self.assertEqual(o.ledger.get_balance("TMN").free,D(5000000))
        self.assertFalse(o.decision_traces[-1]["risk"]["approved"])
        self.assertIn("denied",o.decision_traces[-1]["risk"]["reason"])

    def test_host_protection_continues_and_cancels_a_slow_position_model(self):
        o = self.make_runner()
        o.ledger.set_balance("USDT",D(1))
        times = list(range(18000,30000,60))
        feed = MagicMock()
        feed.get.return_value = (dict(s="ok",t=times,o=["100"]*200,h=["102"]*200,
            l=["98"]*200,c=["100"]*200,v=["20"]*200),30005)
        canceled = []
        async def slow(*args,**kwargs):
            try:
                await asyncio.sleep(100)
            finally:
                canceled.append(True)
        original_wait = asyncio.wait
        async def short_wait(tasks,**kwargs):
            return await original_wait(tasks,timeout=.01)
        async def host(*args,**kwargs):
            self.assertFalse(kwargs["allow_model"])
            return D(99), {"action":"EXIT"}
        state = dict(opened_at=29700,hard_exit_at=40000,initial_stop_price="97",trailing_stop_price="98")
        with patch.object(o.broker,"export_state",return_value={"cost_basis_tmn":"100.3","net_liquidation_tmn":"99.7"}), \
             patch.object(runner,"decide_role",side_effect=slow), \
             patch.object(runner.asyncio,"wait",side_effect=short_wait), \
             patch.object(o,"_handle_position_cycle",side_effect=host) as guard:
            asyncio.run(o._review_position(feed,30005,D(100),state))
        guard.assert_awaited_once()
        self.assertEqual(canceled,[True])


if __name__ == "__main__":
    unittest.main()
