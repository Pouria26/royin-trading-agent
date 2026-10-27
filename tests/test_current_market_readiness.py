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
from royin.decision import Decision, MarketEntryProposal, bind_decision
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
        o = self.make_runner(mode="HISTORICAL_REPLAY", cycles=5,order_tmn=D(1500000))
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

    def test_candle_boundary_during_collection_is_deferred_not_budget_exhaustion(self):
        for deferred in (True, False):
            with self.subTest(deferred=deferred):
                o = self.make_runner()
                o.model_mode, o.run_envelope = "REAL_MODEL", object()
                snap = snapshot("ETHTMN")
                report = dict(batch=[ScanCandidate(snap,D(0),opportunity())], cutoff=8100,
                    market_rules={"ETHTMN":runner.build_default_rules("ETHTMN")}, coverage={}, errors=[])
                async def infer(*args, deferred=deferred, **kwargs):
                    if deferred:
                        kwargs["model_trace"].update(host_outcome="HOST_DEFERRED",
                            defer_reason="INSUFFICIENT_CLOSED_CANDLE_TIME")
                    raise BudgetBlocked("CLOSED_CANDLE_TIME" if deferred else "Durable budget exhausted")
                with patch.object(runner,"public_symbols",return_value=(catalog(),8105,{"ETHTMN"})), \
                     patch.object(runner,"scan_current_market",return_value=report), \
                     patch.object(runner,"decide_role",side_effect=infer), \
                     patch.object(o,"_apply_entry_decision") as apply, patch("time.time",return_value=8105):
                    asyncio.run(o._handle_entry_cycle(MagicMock(),8105))
                self.assertEqual(o.ledger.get_meta("entry_block_reason"),
                    "DEFERRED_CLOSED_CANDLE_TIME" if deferred else "BUDGET_EXHAUSTED")
                if deferred:
                    apply.assert_not_awaited()
                    self.assertEqual(o.decision_traces[-1]["host_outcome"], "HOST_DEFERRED")
                else:
                    apply.assert_awaited_once()

    def test_research_coverage_is_durable_and_visible_on_the_next_model_call(self):
        o = self.make_runner()
        self.assertEqual(o.risk_policy.max_order_tmn,D(100000))
        o.model_mode,o.run_envelope = "REAL_MODEL",object()
        snap = snapshot("ETHTMN")
        coverage = []
        async def infer(*args,**kwargs):
            coverage.append(kwargs["market_universe"].markets[0])
            await kwargs["market_loader"](("ETHTMN",))
            return runner.RoleDecisionProposal(role="ENTRY_ANALYST",action="WAIT",symbol=snap.symbol,
                cutoff=snap.cutoff,snapshot_sha256=snap.snapshot_sha256,evidence_ids=("EV_DATA_FRESH",),
                reason="synthetic research coverage",invalidation="next cycle")
        def scan(*args,**kwargs):
            return dict(batch=[ScanCandidate(snap,D(0),opportunity())],cutoff=8100,
                market_rules={"ETHTMN":runner.build_default_rules("ETHTMN")},coverage={},errors=[])
        feed = ScannerPublicFeed(o.capture_dir/"raw")
        with patch.object(runner,"public_symbols",return_value=(catalog(),8105,{"ETHTMN"})), \
             patch.object(runner,"scan_current_market",side_effect=scan), \
             patch.object(runner,"decide_role",side_effect=infer),patch("time.time",return_value=8105):
            asyncio.run(o._handle_entry_cycle(feed,8105))
            # Durable state, not the in-memory trace, carries coverage into the next call.
            o.decision_traces.clear()
            asyncio.run(o._handle_entry_cycle(feed,8105))
        self.assertEqual((coverage[0].research_requests,coverage[1].research_requests),(0,1))
        self.assertEqual(coverage[1].accepted_research_count,1)
        counts = json.loads(o.ledger.get_meta("engine_research_coverage"))
        self.assertEqual(counts["ETHTMN"],{"requested":2,"accepted":2})
        self.assertEqual(o.decision_traces[-1]["coverage"]["unique_accepted_symbols"],1)
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

    def test_broken_bootstrap_market_does_not_block_healthy_universe(self):
        o = self.make_runner()
        o.model_mode,o.run_envelope = "REAL_MODEL",object()
        snap = snapshot("ETHTMN")
        decision = runner.RoleDecisionProposal(role="ENTRY_ANALYST",action="WAIT",symbol=snap.symbol,
            cutoff=snap.cutoff,snapshot_sha256=snap.snapshot_sha256,evidence_ids=("EV_DATA_FRESH",),
            reason="synthetic fallback boundary",invalidation="next cycle")
        liquid = tuple(MarketShortlistRow(s,D(200000000-i),D(1),8105,"c"*64)
            for i,s in enumerate(("BTCTMN","ETHTMN")))
        healthy = dict(batch=[ScanCandidate(snap,D(0),opportunity())],
            market_rules={"BTCTMN":runner.build_default_rules("BTCTMN"),"ETHTMN":runner.build_default_rules("ETHTMN")},
            status="CANDIDATES")
        with patch.object(runner,"public_symbols",return_value=(catalog(),8105,{"BTCTMN","ETHTMN"})), \
             patch.object(runner,"catalog_candidates",return_value=liquid), \
             patch.object(runner,"scan_current_market",side_effect=[dict(status="BLOCKED_DATA",batch=(),errors=["gap"]),healthy]) as scan, \
             patch.object(runner,"decide_role",return_value=decision) as infer,patch("time.time",return_value=8105):
            asyncio.run(o._handle_entry_cycle(MagicMock(),8105))
        self.assertEqual([call.kwargs["selected_symbols"] for call in scan.call_args_list],[["BTCTMN"],["ETHTMN"]])
        self.assertEqual(len(infer.call_args.kwargs["market_universe"].markets),2)
        self.assertEqual(infer.call_args.kwargs["market_universe"].unavailable_symbols,("BTCTMN",))
        self.assertEqual(o.decision_traces[-1]["bootstrap_attempts"][0]["status"],"BLOCKED_DATA")
        self.assertEqual(o.ledger.get_balance("TMN").free,D(5000000))

    def test_bootstrap_failures_are_bounded_and_do_not_call_model(self):
        o = self.make_runner()
        o.model_mode,o.run_envelope = "REAL_MODEL",object()
        liquid = tuple(MarketShortlistRow(s,D(200000000-i),D(1),8105,"c"*64)
            for i,s in enumerate(("BTCTMN","ETHTMN","SOLTMN","ADATMN")))
        def blocked(*args,**kwargs):
            symbol=kwargs["selected_symbols"][0]
            return dict(status="BLOCKED_DATA",batch=(),errors=["gap"],
                rejections=[dict(symbol=symbol,reason="HISTORY_PARSE_FAILED",error_type="ValueError")])
        with patch.object(runner,"public_symbols",return_value=(catalog(),8105,{x.symbol for x in liquid})), \
             patch.object(runner,"catalog_candidates",return_value=liquid), \
             patch.object(runner,"scan_current_market",side_effect=blocked) as scan, \
             patch.object(runner,"decide_role") as infer,patch("time.time",return_value=8105):
            asyncio.run(o._handle_entry_cycle(MagicMock(),8105))
        self.assertEqual(scan.call_count,3)
        infer.assert_not_awaited()
        self.assertEqual(len(o.decision_traces[-1]["bootstrap_attempts"]),3)
        attempted=[call.kwargs["selected_symbols"][0] for call in scan.call_args_list]
        self.assertEqual([row["rejections"][0]["symbol"] for row in o.decision_traces[-1]["bootstrap_attempts"]],attempted)
        self.assertEqual(o.decision_traces[-1]["scanner_rejections"][0]["symbol"],attempted[-1])
        o._checkpoint_and_export(8105)
        stored=json.loads((o.capture_dir/"manifest.json").read_text())["arms"]["paper_portfolio"]["decision_traces"][-1]
        self.assertEqual([row["rejections"][0]["reason"] for row in stored["bootstrap_attempts"]],
            ["HISTORY_PARSE_FAILED"]*3)

    def test_failed_seed_batch_rotates_after_restart_and_reaches_the_fourth_market(self):
        o = self.make_runner()
        o.model_mode,o.run_envelope = "REAL_MODEL",object()
        symbols = ("BTCTMN","ETHTMN","SOLTMN","USDTTMN")
        liquid = tuple(MarketShortlistRow(s,D(200000000-i),D(1),8105,"c"*64)
            for i,s in enumerate(symbols))
        payload = catalog()
        payload["result"]["markets"].append(dict(payload["result"]["markets"][1],symbol="SOLTMN",base_asset="SOL"))
        with patch.object(runner,"public_symbols",return_value=(payload,8105,set(symbols))), \
             patch.object(runner,"catalog_candidates",return_value=liquid), \
             patch.object(runner,"scan_current_market",return_value=dict(status="NO_CANDIDATE",batch=())) as scan, \
             patch.object(runner,"decide_role") as infer,patch("time.time",return_value=8105):
            asyncio.run(o._handle_entry_cycle(MagicMock(),8105))
        self.assertEqual([call.kwargs["selected_symbols"] for call in scan.call_args_list],
            [["BTCTMN"],["ETHTMN"],["SOLTMN"]])
        infer.assert_not_awaited()
        o.close()
        restored = runner.MarketPaperOrchestrator(run_id=o.run_id,capture_dir=o.capture_dir,config=RuntimeConfig())
        self.addCleanup(restored.close)
        restored.model_mode,restored.run_envelope = "REAL_MODEL",object()
        snap = snapshot("USDTTMN")
        decision = runner.RoleDecisionProposal(role="ENTRY_ANALYST",action="WAIT",symbol=snap.symbol,
            cutoff=snap.cutoff,snapshot_sha256=snap.snapshot_sha256,evidence_ids=("EV_DATA_FRESH",),
            reason="synthetic healthy fourth seed",invalidation="next cycle")
        healthy = dict(status="CANDIDATES",batch=[ScanCandidate(snap,D(0),opportunity())],
            market_rules={s:runner.build_default_rules(s) for s in symbols})
        with patch.object(runner,"public_symbols",return_value=(payload,8105,set(symbols))), \
             patch.object(runner,"catalog_candidates",return_value=liquid), \
             patch.object(runner,"scan_current_market",return_value=healthy) as scan, \
             patch.object(runner,"decide_role",return_value=decision) as infer,patch("time.time",return_value=8105):
            asyncio.run(restored._handle_entry_cycle(MagicMock(),8105))
        self.assertEqual(scan.call_args.kwargs["selected_symbols"],["USDTTMN"])
        infer.assert_awaited_once()
        self.assertEqual(len(infer.call_args.kwargs["market_universe"].markets),4)
        self.assertEqual(restored.ledger.get_balance("TMN").free,D(5000000))
        self.assertFalse(restored.broker.orders)

    def test_seed_coverage_prioritizes_quant_rank_instead_of_alphabetical_order(self):
        o = self.make_runner()
        o.model_mode, o.run_envelope = "REAL_MODEL", object()
        # Turnover gives this nonalphabetical ranking when the quant scores tie.
        symbols = ("SOLTMN", "ETHTMN", "BTCTMN", "ADATMN")
        liquid = tuple(MarketShortlistRow(s,D(200000000-i),D(1),8105,"c"*64)
            for i,s in enumerate(symbols))
        with patch.object(runner,"public_symbols",return_value=(catalog(),8105,set(symbols))), \
             patch.object(runner,"catalog_candidates",return_value=liquid), \
             patch.object(runner,"quant_candidate_score",return_value=D(0)), \
             patch.object(runner,"scan_current_market",return_value=dict(status="NO_CANDIDATE",batch=())) as scan, \
             patch.object(runner,"decide_role") as infer,patch("time.time",return_value=8105):
            asyncio.run(o._handle_entry_cycle(MagicMock(),8105))
        self.assertEqual([c.kwargs["selected_symbols"][0] for c in scan.call_args_list],list(symbols[:3]))
        counts=json.loads(o.ledger.get_meta("engine_bootstrap_attempt_counts"))
        self.assertEqual(counts,{"SOLTMN":1,"ETHTMN":1,"BTCTMN":1})
        infer.assert_not_awaited()

    def test_blocked_model_research_keeps_reason_and_stops_before_second_model_request(self):
        import httpx2

        from royin.agent import decide_role as real_decide_role
        for status in ("BLOCKED_CUTOFF_ADVANCED","BLOCKED_SPOT_RULES"):
            with self.subTest(status=status):
                o=self.make_runner()
                o.model_mode,o.run_envelope="REAL_MODEL",object()
                snap=snapshot("ETHTMN")
                healthy=dict(status="CANDIDATES",batch=[ScanCandidate(snap,D(0),opportunity())],
                    market_rules={"ETHTMN":runner.build_default_rules("ETHTMN")})
                blocked=dict(status=status,batch=(),cutoff=8100,errors=[],rejections=[])
                liquid=(MarketShortlistRow("ETHTMN",D(200000000),D(1),8105,"c"*64),)
                bodies=[]
                async def handler(request, bodies=bodies):
                    bodies.append(json.loads(request.content))
                    self.assertEqual(len(bodies),1,"Blocked data must not spend a final-answer request")
                    message=dict(role="assistant",content=None,tool_calls=[dict(id="bounded-research",type="function",
                        function=dict(name="read_market_snapshot",arguments=json.dumps(dict(symbols=["ETHTMN"]))))])
                    return httpx2.Response(200,json=dict(id="synthetic",object="chat.completion",created=0,
                        model="gpt-6-luna",choices=[dict(index=0,message=message,finish_reason="tool_calls")],
                        usage=dict(prompt_tokens=100,completion_tokens=50,total_tokens=150)))
                async def infer(primary,handler=handler,**kwargs):
                    kwargs.update(config=RuntimeConfig(BOXAPI_API_KEY="synthetic-only"),budget=None,run_envelope=None)
                    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
                        return await real_decide_role(primary,client=client,**kwargs)
                with patch.object(runner,"public_symbols",return_value=(catalog(),8105,{"ETHTMN"})), \
                     patch.object(runner,"catalog_candidates",return_value=liquid), \
                     patch.object(runner,"scan_current_market",side_effect=[healthy,blocked]), \
                     patch.object(runner,"decide_role",side_effect=infer),patch("time.time",return_value=8105):
                    asyncio.run(o._handle_entry_cycle(MagicMock(),8105))
                row=o.decision_traces[-1]
                self.assertNotIn("KeyError",row["decision"]["reason"])
                self.assertEqual(row["decision"]["action"],"WAIT")
                self.assertIsNone(row["decision"]["forecast"])
                self.assertEqual(row["model_trace"]["research_status"],status)
                self.assertEqual(row["model_trace"]["host_outcome"],"HOST_FALLBACK")
                self.assertEqual(len(bodies),1)
                self.assertFalse(o.broker.orders)
                self.assertEqual(o.ledger.get_balance("TMN").free,D(5000000))
                coverage=json.loads(o.ledger.get_meta("engine_research_coverage"))
                self.assertEqual(coverage["ETHTMN"],dict(requested=1,accepted=0))

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
        o.ledger.set_balance("USDT",D(1))
        feed.get.return_value = ({"success":True, "result":{"bid":[{"price":"105", "quantity":"5"}],
            "ask":[{"price":"106","quantity":"5"}]}}, 2000)
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
        feed.get.return_value = ({"success":True,"result":{"bid":[{"price":"260000","quantity":"10"}],
            "ask":[{"price":"260001","quantity":"10"}]}},2000)
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
        for response in (None, {"success":True,"result":{"bid":[{"price":"260000","quantity":".1"}],
            "ask":[{"price":"260001","quantity":"10"}]}}):
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
             patch.object(runner.time,"time",side_effect=lambda clock=clock:clock[0]):
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
        o = self.make_runner(order_tmn=D(150000), minimum_notional_tmn=D(100000))
        snap = snapshot("ETHTMN")
        opp = opportunity().model_copy(update={"best_ask":D(101),"best_bid":D(100)})
        proposal = enter_proposal(snap, horizon=7200)
        proposal["opportunity_sha256"] = opp.sha256
        proposal["review_after_seconds"] = 600
        proposal["forecast"]["review_after_seconds"] = 600
        # Both target and central forecast must clear coarse ticks and both fee assets.
        proposal["forecast"]["target_return_fraction"] = ".05"
        proposal["forecast"].update(return_q50=".04", return_q90=".06")
        decision = bind_decision(MarketEntryProposal.model_validate(proposal),decision_id="chosen-eth",
            symbol=snap.symbol,cutoff=snap.cutoff,snapshot_sha256=snap.snapshot_sha256,
            available_evidence_ids=tuple(snap.evidences))
        o.model_mode, o.run_envelope = "REAL_MODEL", object()
        feed = MagicMock()
        feed.get.return_value = ({"success":True,"result":{
            "bid":[{"price":"100","quantity":"10000"}],
            "ask":[{"price":"101","quantity":"10000"}]}},8105)
        with patch.object(runner,"public_symbols",return_value=(catalog(),8105,{"ETHTMN"})), \
             patch.object(runner,"scan_current_market",return_value={"batch":[ScanCandidate(snap,D(0),opp)],
                 "market_rules":{"ETHTMN":runner.replace(runner.build_default_rules("ETHTMN"),min_notional=D(50000))}}), \
             patch.object(runner,"decide_role",return_value=decision), patch("time.time",return_value=8105):
            asyncio.run(o._handle_entry_cycle(feed,8105))
        self.assertEqual(o.rules.symbol,"ETHTMN")
        self.assertEqual(o.rules.min_notional,D(100000))
        self.assertEqual(o.protection_policy.hard_holding_seconds,7195)
        self.assertEqual(8105+o.protection_policy.hard_holding_seconds,decision.forecast.cutoff+decision.forecast.horizon_seconds)
        self.assertEqual(o.protection_policy.review_interval_seconds,600)
        saved_hash = o.protection_policy.sha256
        self.assertTrue(o.decision_traces[-1]["client_id"])
        o.close()
        restarted = runner.MarketPaperOrchestrator(run_id=o.run_id,config=RuntimeConfig(),capture_dir=o.capture_dir,
            order_tmn=D(150000),minimum_notional_tmn=D(100000))
        try:
            self.assertEqual(restarted.rules.symbol,"ETHTMN")
            self.assertEqual(restarted.rules.min_notional,D(100000))
            self.assertEqual(restarted.protection_policy.sha256,saved_hash)
        finally:
            restarted.close()

    def test_positive_candle_target_below_fresh_ask_is_rejected_before_reservation(self):
        o = self.make_runner()
        snap = snapshot("ETHTMN")
        opp = opportunity().model_copy(update={"best_ask":D(104),"best_bid":D("103.99")})
        proposal = enter_proposal(snap,horizon=7200)
        proposal["opportunity_sha256"] = opp.sha256
        proposal["forecast"]["target_return_fraction"] = ".021"
        decision = bind_decision(MarketEntryProposal.model_validate(proposal),decision_id="cost-counterexample",
            symbol=snap.symbol,cutoff=snap.cutoff,snapshot_sha256=snap.snapshot_sha256,
            available_evidence_ids=tuple(snap.evidences))
        o.model_mode,o.run_envelope = "REAL_MODEL",object()
        feed = MagicMock()
        feed.get.return_value = ({"success":True,"result":{
            "bid":[{"price":"103.99","quantity":"10000"}],
            "ask":[{"price":"104","quantity":"10000"}]}},8105)
        rules = runner.replace(runner.build_default_rules("ETHTMN"),tick_size=D(".01"),min_notional=D(50000))
        with patch.object(runner,"public_symbols",return_value=(catalog(),8105,{"ETHTMN"})), \
             patch.object(runner,"scan_current_market",return_value={"batch":[ScanCandidate(snap,D(0),opp)],
                "market_rules":{"ETHTMN":rules}}), \
             patch.object(runner,"decide_role",return_value=decision),patch("time.time",return_value=8105):
            asyncio.run(o._handle_entry_cycle(feed,8105))
        self.assertFalse(o.decision_traces[-1]["risk"]["approved"])
        self.assertIn("conditional target",o.decision_traces[-1]["risk"]["reason"])
        self.assertFalse(o.decision_traces[-1]["execution"]["target_net_check"]["approved"])
        self.assertFalse(o.broker.orders)
        self.assertEqual(o.ledger.get_balance("TMN").free,D(5000000))
        self.assertEqual(o.ledger.get_balance("TMN").locked,D(0))

    def test_model_exit_survives_missing_book_and_recovers_without_a_second_model_call(self):
        o = self.make_runner()
        o.model_mode,o.run_envelope = "REAL_MODEL",object()
        risk = RiskResult(True,"technical position","ENTER","USDTTMN",D(1),D(250000),D(242500),D(750))
        o.broker.submit_order(risk,client_id="technical-buy",timestamp=1000)
        o.broker.reconcile_order("technical-buy",simulated_state="FILLED",timestamp=1000)
        o.broker.arm_protection(o.protection_policy,opened_at=1000,entry_price=D(250000))
        async def exit_model(snap,**kwargs):
            return Decision(decision_id="synthetic-exit",symbol=snap.symbol,action="EXIT",cutoff=snap.cutoff,
                snapshot_sha256=snap.snapshot_sha256,evidence_ids=("EV_POSITION_LONG",),
                reason="synthetic reviewer requests exit",invalidation="closed position")
        def get(endpoint,params,**kwargs):
            if endpoint == "/v1/udf/history":
                times = list(range(params["from"],params["to"],60))
                return dict(s="ok",t=times,o=["250000"]*len(times),h=["250000"]*len(times),
                    l=["250000"]*len(times),c=["250000"]*len(times),v=["1000"]*len(times)),15005
            raise OSError("temporary exit book failure")
        feed = MagicMock()
        feed.get.side_effect = get
        state = json.loads(o.ledger.get_meta("protection_USDTTMN"))
        state["hard_exit_at"] = 37000
        with patch.object(runner,"decide_role",side_effect=exit_model) as model,patch("time.time",return_value=15005):
            asyncio.run(o._review_position(feed,15005,D(250000),state))
            self.assertEqual(model.call_count,1)
        self.assertEqual(o.ledger.get_balance("USDT").total,D(1))
        self.assertEqual(json.loads(o.ledger.get_meta("protection_USDTTMN"))["pending_exit_reason"],"MODEL_EXIT")
        feed.get.side_effect = None
        feed.get.return_value = ({"success":True,"result":{
            "bid":[{"price":"260000","quantity":"10"}],"ask":[{"price":"260001","quantity":"10"}]}},15010)
        with patch.object(runner,"decide_role") as model:
            _,result = asyncio.run(o._handle_position_cycle(feed,15010,json.loads(o.ledger.get_meta("protection_USDTTMN"))))
            model.assert_not_called()
        self.assertEqual(result["exit_reason"],"MODEL_EXIT")
        self.assertEqual(o.ledger.get_balance("USDT").total,D(0))
        self.assertEqual(json.loads(o.ledger.get_meta("protection_USDTTMN"))["status"],"CLOSED")

    def test_unfillable_or_expired_entry_does_not_reserve_or_create_a_paper_order(self):
        for failure in ("shallow","outside_limit","expired"):
            with self.subTest(failure=failure):
                o = self.make_runner()
                snap = snapshot("ETHTMN")
                opp = opportunity().model_copy(update={"best_ask":D(101),"best_bid":D(100)})
                proposal = enter_proposal(snap,horizon=300)
                proposal["opportunity_sha256"] = opp.sha256
                proposal["review_after_seconds"] = 60
                proposal["forecast"]["review_after_seconds"] = 60
                decision = bind_decision(MarketEntryProposal.model_validate(proposal),decision_id="book-check",
                    symbol=snap.symbol,cutoff=snap.cutoff,snapshot_sha256=snap.snapshot_sha256,
                    available_evidence_ids=tuple(snap.evidences))
                o.model_mode,o.run_envelope = "REAL_MODEL",object()
                clock = [8105]
                def get(*args,failure=failure,clock=clock,**kwargs):
                    if failure == "expired":
                        clock[0] = 8401
                    return {"success":True,"result":{
                        "bid":[{"price":"100","quantity":"10000"}],
                        "ask":[{"price":"102" if failure == "outside_limit" else "101",
                                "quantity":".0001" if failure == "shallow" else "10000"}]}},clock[0]
                feed = MagicMock()
                feed.get.side_effect = get
                with patch.object(runner,"public_symbols",return_value=(catalog(),8105,{"ETHTMN"})), \
                     patch.object(runner,"scan_current_market",return_value={"batch":[ScanCandidate(snap,D(0),opp)],
                        "market_rules":{"ETHTMN":runner.replace(runner.build_default_rules("ETHTMN"),min_notional=D(50000))}}), \
                     patch.object(runner,"decide_role",return_value=decision),patch("time.time",side_effect=lambda clock=clock:clock[0]):
                    asyncio.run(o._handle_entry_cycle(feed,8105))
                self.assertEqual(o.ledger.get_balance("TMN").free,D(5000000))
                self.assertEqual(o.ledger.get_balance("TMN").locked,D(0))
                self.assertFalse(o.broker.orders)
                self.assertIsNone(o.decision_traces[-1]["client_id"])
                self.assertFalse(o.decision_traces[-1]["risk"]["approved"])
                self.assertIn("Executable entry book rejected",o.decision_traces[-1]["risk"]["reason"])

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
