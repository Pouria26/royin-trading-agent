"""Synthetic source transitions preserve trades, balances, cadence and historical bindings."""

import json
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import patch

from royin.config import RuntimeConfig
from royin.ledger import Ledger
from royin.live_broker import WallexLiveBroker
from royin.runtime_release import authorize_source_transition, source_history
from scripts.run_market_paper import MarketPaperOrchestrator


class RuntimeReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ledger = Ledger(self.root / "financial.sqlite3")
        WallexLiveBroker.initialize_state(self.ledger)
        self.ledger.initialize_portfolio(D(150000), quote_asset="TMN", binding="f" * 64)
        for key, value in dict(fresh_source_sha256="a" * 64, fresh_config_sha256="b" * 64,
                fresh_permit="original-permit", service_state="PAUSED_RESTART").items():
            self.ledger.set_meta(key, value)

    def upgrade(self, **kwargs):
        defaults = dict(expected_source_sha256="a" * 64,target_source_sha256="c" * 64,
            artifact_sha256="d" * 64,backup_receipt_sha256="e" * 64,
            operator_instruction="Synthetic explicit operator continuation authority")
        return authorize_source_transition(self.ledger, **(defaults | kwargs))

    def test_completed_trades_and_all_previous_metadata_are_preserved(self):
        for side, price in [("BUY", D(100)), ("SELL", D(102))]:
            cid = "synthetic_" + side
            self.ledger.record_intent(client_id=cid, symbol="ETHTMN", side=side, order_type="LIMIT",
                price=price, quantity=D(1400), quote_fee_reserve=D(420) if side == "BUY" else D(0),
                quote_asset="TMN", base_asset="ETH", timestamp=1000)
            self.ledger.record_fill(fill_id=cid, client_id=cid, price=price, quantity=D(1400),
                fee=price * D(1400) * D(".003"), fee_asset="TMN", timestamp=1001)
        with self.ledger.connection() as db:
            before = list(db.iterdump())
        receipt = self.upgrade()
        with self.ledger.connection() as db:
            after = [line for line in db.iterdump() if "runtime_source_history" not in line]
        self.assertEqual(before, after)
        self.assertEqual(source_history(self.ledger), ("a" * 64, "c" * 64))
        self.assertEqual(receipt["from_source_sha256"], "a" * 64)
        self.assertEqual(self.ledger.get_meta("closed_round_trips"), "1")
        with self.assertRaisesRegex(ValueError, "Expected active"):
            self.upgrade()

    def test_active_unknown_or_held_position_cannot_be_upgraded(self):
        self.ledger.set_meta("service_state", "RUNNING")
        with self.assertRaisesRegex(ValueError, "paused"):
            self.upgrade()
        self.ledger.set_meta("service_state", "PAUSED_RESTART")
        self.ledger.record_intent(client_id="unknown", symbol="ETHTMN", side="BUY", order_type="LIMIT",
            price=D(100), quantity=D(1000), quote_fee_reserve=D(300), quote_asset="TMN", base_asset="ETH", timestamp=1000)
        with self.assertRaisesRegex(ValueError, "flat reconciled"):
            self.upgrade()
        self.assertIsNone(self.ledger.get_meta("runtime_source_history"))
        self.assertGreater(self.ledger.get_balance("TMN").locked, 0)

    def test_tampered_receipt_config_or_target_never_authorizes_source(self):
        self.upgrade()
        old = self.ledger.get_meta("runtime_source_history")
        data = json.loads(old)
        data[0]["to_source_sha256"] = "f" * 64
        self.ledger.set_meta("runtime_source_history", json.dumps(data))
        with self.assertRaisesRegex(ValueError, "binding mismatch"):
            source_history(self.ledger)
        self.ledger.set_meta("runtime_source_history", old)
        self.ledger.set_meta("fresh_config_sha256", "f" * 64)
        with self.assertRaisesRegex(ValueError, "binding mismatch"):
            source_history(self.ledger)

    def test_observed_container_quiescence_does_not_forge_a_graceful_terminal_status(self):
        self.ledger.set_meta("service_state", "RUNNING")
        receipt = self.upgrade(quiescent_restart_receipt_sha256="9" * 64)
        self.assertEqual(self.ledger.get_meta("service_state"), "RUNNING")
        self.assertEqual(receipt["quiescent_restart_receipt_sha256"], "9" * 64)

    def test_audited_dust_survives_source_upgrade_without_becoming_cash_or_round_trip(self):
        from royin.residuals import quarantine_residual
        from tests.test_residuals import ResidualTests
        fixture = ResidualTests()
        fixture.setUp()
        self.ledger = fixture.ledger
        fixture.position()
        self.assertTrue(quarantine_residual(self.ledger,fixture.rules,
            price_tmn=D(1000),quote_received_at=1200,now=1202))
        for k,v in dict(fresh_source_sha256="a"*64,fresh_config_sha256="b"*64,
                        fresh_permit="original-permit",service_state="PAUSED_RESTART").items():
            self.ledger.set_meta(k,v)
        before = fixture.financial_snapshot()
        receipt = self.upgrade()
        self.assertEqual(receipt["preserved_residual_assets"],{"ETH":"0.0076"})
        self.assertEqual(fixture.financial_snapshot(),before)
        self.assertEqual(self.ledger.get_balance("ETH").total,D(".0076"))
        self.assertIsNone(self.ledger.get_meta("closed_round_trips"))
        self.ledger.set_balance("ETH",D(".0077"))
        with self.assertRaises(ValueError):
            self.upgrade(expected_source_sha256="c"*64,target_source_sha256="9"*64)

    def test_signal_restart_retains_original_traces_cadence_and_coverage(self):
        folder = self.root / "signals"
        config = RuntimeConfig()
        with patch("scripts.run_market_paper.source_bundle_sha256", return_value="a" * 64):
            first = MarketPaperOrchestrator(run_id="same_run", config=config, capture_dir=folder)
            first.decision_traces.append(dict(decision={"action":"WAIT","reason":"Original recorded decision"},
                                              model_trace={"code_sha256":"a" * 64}))
            first.ledger.set_meta("next_entry_analysis_at", "99999")
            first.ledger.set_meta("engine_bootstrap_attempt_counts", '{"ETHTMN":4}')
            first._checkpoint_and_export(8100)
            original_manifest = (folder / "manifest.json").read_bytes()
            first.close()
        with patch("scripts.run_market_paper.source_bundle_sha256", return_value="c" * 64):
            resumed = MarketPaperOrchestrator(run_id="same_run", config=config, capture_dir=folder,
                                              source_history=("a" * 64, "c" * 64))
            try:
                self.assertEqual(resumed.ledger.get_meta("next_entry_analysis_at"), "99999")
                self.assertEqual(resumed.ledger.get_meta("engine_bootstrap_attempt_counts"), '{"ETHTMN":4}')
                self.assertEqual(resumed.ledger.get_meta("engine_source_sha256"), "a" * 64)
                self.assertEqual(resumed.decision_traces[0]["model_trace"]["code_sha256"], "a" * 64)
                self.assertEqual((folder / "manifest.json").read_bytes(), original_manifest)
                resumed._checkpoint_and_export(8200)
                published = json.loads((folder / "manifest.json").read_text())
                self.assertEqual(published["bindings"]["code_sha256"], "c" * 64)
                self.assertEqual(published["runtime_source_history"], ["a" * 64, "c" * 64])
                self.assertEqual(published["arms"]["paper_portfolio"]["decision_traces"][0]
                                 ["model_trace"]["code_sha256"], "a" * 64)
            finally:
                resumed.close()

    def test_seventeenth_transition_preserves_the_original_sixteen_receipts(self):
        active = "a" * 64
        for i in range(17):
            if i == 16:
                prefix = json.loads(self.ledger.get_meta("runtime_source_history"))
            target = f"{i+100:064x}"
            self.upgrade(expected_source_sha256=active,target_source_sha256=target)
            active = target
        receipts = json.loads(self.ledger.get_meta("runtime_source_history"))
        self.assertEqual(receipts[:16], prefix)
        self.assertEqual(len(receipts), 17)
        self.assertEqual(receipts[16]["previous_receipt_sha256"], prefix[-1]["sha256"])
        self.assertEqual(source_history(self.ledger)[-1], active)
        self.assertEqual(self.ledger.get_meta("fresh_source_sha256"), "a" * 64)

    def test_source_transition_history_remains_bounded_and_never_prunes_receipts(self):
        active = "a" * 64
        for i in range(32):
            target = f"{i+100:064x}"
            self.upgrade(expected_source_sha256=active,target_source_sha256=target)
            active = target
        before = self.ledger.get_meta("runtime_source_history")
        with self.assertRaisesRegex(ValueError, "allowance exhausted"):
            self.upgrade(expected_source_sha256=active,target_source_sha256="9"*64)
        self.assertEqual(self.ledger.get_meta("runtime_source_history"), before)
        self.assertEqual(len(source_history(self.ledger)), 33)
        too_long = [*json.loads(before), json.loads(before)[-1]]
        self.ledger.set_meta("runtime_source_history",json.dumps(too_long))
        with self.assertRaisesRegex(ValueError, "Invalid bounded runtime source history"):
            source_history(self.ledger)


if __name__ == "__main__":
    unittest.main()
