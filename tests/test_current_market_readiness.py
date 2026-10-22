"""Regressions for market execution boundaries, independent of model profitability."""
import asyncio
import json
import sqlite3
import tempfile
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
from scripts.run_paper_trader import ScanCandidate
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
        with patch.object(runner,"public_symbols",return_value=({},8105,{"ETHTMN"})), \
             patch.object(runner,"scan_current_market",return_value={"batch":[ScanCandidate(snap,D(0),opp)],
                 "market_rules":{"ETHTMN":runner.build_default_rules("ETHTMN")}}), \
             patch.object(runner,"decide_role",return_value=decision), patch("time.time",return_value=8105):
            asyncio.run(o._handle_entry_cycle(MagicMock(),8105))
        self.assertEqual(o.rules.symbol,"ETHTMN")
        self.assertEqual(o.protection_policy.hard_holding_seconds,7200)
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
        for _ in range(12):
            first.claim_run()
        restarted = RoleRunEnvelope(budget,duration_seconds=3600,scope_id="shared")
        self.assertEqual(restarted.agent_runs,12)
        with self.assertRaises(BudgetBlocked):
            restarted.claim_run()
        with self.assertRaises(BudgetBlocked):
            RoleRunEnvelope(budget,duration_seconds=7200,scope_id="shared")
        with closing(sqlite3.connect(budget.path)) as db:
            self.assertEqual(db.execute("SELECT agent_runs FROM role_run_envelopes").fetchone()[0],12)

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
