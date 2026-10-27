"""Availability anchors preserve bounded bootstrap rotation without relaxing data gates."""

import asyncio
import json
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import MagicMock, patch

from royin.config import RuntimeConfig
from scripts import run_market_paper as runner
from scripts.run_paper_trader import MarketShortlistRow, ScanCandidate
from tests.test_market_scanner import catalog
from tests.test_market_selection import opportunity, snapshot


class MarketAvailabilityBootstrapTests(unittest.TestCase):
    def make_runner(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        obj = runner.MarketPaperOrchestrator(run_id="availability-test", config=RuntimeConfig(),
            capture_dir=Path(tmp.name))
        self.addCleanup(obj.close)
        obj.model_mode, obj.run_envelope = "REAL_MODEL", object()
        return obj

    def run_cycle(self, obj, healthy_symbol=None):
        symbols = ("SOLTMN", "ADATMN", "TONTMN", "BTCTMN", "ETHTMN")
        liquid = tuple(MarketShortlistRow(symbol, D(200000000-i), D(1), 8105, "c"*64)
            for i, symbol in enumerate(symbols))
        payload = catalog()
        payload["result"]["markets"] = [dict(payload["result"]["markets"][0], symbol=symbol)
            for symbol in symbols]
        snap = snapshot(healthy_symbol or "BTCTMN")
        proposal = runner.RoleDecisionProposal(role="ENTRY_ANALYST", action="WAIT", symbol=snap.symbol,
            cutoff=snap.cutoff, snapshot_sha256=snap.snapshot_sha256, evidence_ids=("EV_DATA_FRESH",),
            reason="synthetic availability test", invalidation="next cycle")

        def scan(*args, **kwargs):
            symbol = kwargs["selected_symbols"][0]
            if symbol == healthy_symbol:
                return dict(status="CANDIDATES", batch=[ScanCandidate(snap,D(0),opportunity())],
                    market_rules={s:runner.build_default_rules(s) for s in symbols})
            return dict(status="BLOCKED_DATA", batch=(), errors=["synthetic gap"],
                rejections=[dict(symbol=symbol, reason="GAP")])

        with patch.object(runner,"public_symbols",return_value=(payload,8105,set(symbols))), \
             patch.object(runner,"catalog_candidates",return_value=liquid), \
             patch.object(runner,"quant_candidate_score",return_value=D(0)), \
             patch.object(runner,"scan_current_market",side_effect=scan) as scans, \
             patch.object(runner,"decide_role",return_value=proposal) as infer, \
             patch.object(obj,"_apply_entry_decision"), patch("time.time",return_value=8105):
            asyncio.run(obj._handle_entry_cycle(MagicMock(),8105))
        return [call.kwargs["selected_symbols"][0] for call in scans.call_args_list], infer

    def test_recent_accepted_anchor_reaches_model_before_three_bad_rotation_seeds(self):
        obj = self.make_runner()
        obj.decision_traces.append(dict(model_trace=dict(context=dict(
            cutoff=8100,candidates=[dict(symbol="ETHTMN"), dict(symbol="BTCTMN")]))))
        attempted, infer = self.run_cycle(obj, "BTCTMN")
        self.assertEqual(attempted, ["BTCTMN"])
        infer.assert_awaited_once()
        self.assertEqual(len(infer.call_args.kwargs["market_universe"].markets), 5)
        self.assertEqual(obj.ledger.get_meta("engine_bootstrap_anchor_symbol"), "BTCTMN")
        self.assertEqual(json.loads(obj.ledger.get_meta("engine_bootstrap_attempt_counts")), {"BTCTMN":1})
        self.assertFalse(obj.broker.orders)

    def test_failed_persisted_seed_cannot_hide_recent_capacity_fit_btc(self):
        obj=self.make_runner()
        obj.ledger.set_meta('engine_bootstrap_anchor_symbol','SOLTMN')
        obj.ledger.set_meta('engine_bootstrap_attempt_counts','{"SOLTMN":48,"BTCTMN":4}')
        obj.decision_traces=[dict(model_trace=dict(context=dict(cutoff=7800,candidates=[
            dict(symbol='BTCTMN',execution_cost_context=dict(capacity=dict(status='SELLABLE_WITH_BOUNDED_RESIDUAL')))]))),
            dict(decision=dict(cutoff=8000),bootstrap_attempts=[dict(symbol='SOLTMN',accepted=False)])]
        attempted,infer=self.run_cycle(obj,'BTCTMN')
        self.assertEqual(attempted,['BTCTMN'])
        infer.assert_awaited_once()
        self.assertEqual(json.loads(obj.ledger.get_meta('engine_bootstrap_attempt_counts')),
                         {'SOLTMN':48,'BTCTMN':5})
        self.assertEqual(obj.ledger.get_meta('engine_bootstrap_anchor_symbol'),'BTCTMN')
        self.assertFalse(obj.broker.orders)

    def test_newer_failure_overrides_fit_and_expired_observations_do_not_ban(self):
        from scripts.run_paper_trader import bootstrap_research_order
        rows=tuple(MarketShortlistRow(s,D(100),D(1),8105,'c'*64) for s in ('SOLTMN','BTCTMN','ETHTMN'))
        traces=[dict(model_trace=dict(context=dict(cutoff=7800,candidates=[dict(symbol='BTCTMN',
            execution_cost_context=dict(capacity=dict(status='SELLABLE_WITH_BOUNDED_RESIDUAL')))]))),
            dict(decision=dict(cutoff=8000),bootstrap_attempts=[dict(symbol='BTCTMN',accepted=False)])]
        before=json.loads(json.dumps(traces))
        self.assertEqual([r.symbol for r in bootstrap_research_order(rows,traces,{},'SOLTMN',observed_at=8105)],
                         ['SOLTMN','ETHTMN','BTCTMN'])
        self.assertEqual([r.symbol for r in bootstrap_research_order(rows,traces,{},None,observed_at=12000)],
                         ['SOLTMN','BTCTMN','ETHTMN'])
        self.assertEqual(traces,before)

    def test_failed_anchor_keeps_three_attempt_cap_and_rotates_other_two(self):
        obj = self.make_runner()
        obj.ledger.set_meta("engine_bootstrap_anchor_symbol", "BTCTMN")
        attempted, infer = self.run_cycle(obj)
        self.assertEqual(attempted, ["BTCTMN", "SOLTMN", "ADATMN"])
        infer.assert_not_awaited()
        self.assertEqual(obj.ledger.get_meta("engine_bootstrap_anchor_symbol"), "BTCTMN")
        self.assertEqual(json.loads(obj.ledger.get_meta("engine_bootstrap_attempt_counts")),
            {"BTCTMN":1, "SOLTMN":1, "ADATMN":1})

    def test_anchor_survives_restart_and_foreign_or_old_context_is_ignored(self):
        obj = self.make_runner()
        obj.ledger.set_meta("engine_bootstrap_anchor_symbol", "BTCTMN")
        obj.ledger.set_meta("engine_bootstrap_attempt_counts", '{"BTCTMN":7}')
        obj.close()
        restored = runner.MarketPaperOrchestrator(run_id=obj.run_id, config=RuntimeConfig(),
            capture_dir=obj.capture_dir)
        self.addCleanup(restored.close)
        restored.model_mode, restored.run_envelope = "REAL_MODEL", object()
        attempted, infer = self.run_cycle(restored, "BTCTMN")
        self.assertEqual(attempted, ["BTCTMN"])
        infer.assert_awaited_once()
        self.assertEqual(json.loads(restored.ledger.get_meta("engine_bootstrap_attempt_counts")), {"BTCTMN":8})
        restored.ledger.set_meta("engine_bootstrap_anchor_symbol", "FOREIGNTMN")
        restored.decision_traces = [dict(model_trace=dict(context=dict(candidates=[dict(symbol="BTCTMN")])))]
        restored.decision_traces += [dict(model_trace=dict(context=dict(candidates=[dict(symbol="FOREIGNTMN")])))]*12
        attempted, infer = self.run_cycle(restored)
        self.assertEqual(attempted, ["SOLTMN", "ADATMN", "TONTMN"])
        infer.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
