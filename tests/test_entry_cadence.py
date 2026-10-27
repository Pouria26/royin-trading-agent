"""An authorized cadence amendment preserves the mission and its pending deadline."""

import asyncio
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from royin.ledger import Ledger
from royin.live_broker import WallexLiveBroker
from royin.runtime_release import authorize_source_transition, digest, source_history
from scripts.run_fresh_service import signals_for
from scripts.run_market_paper import MarketPaperOrchestrator
from tests.test_multiday_service import config_for, policy


class EntryCadenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.contract = policy(analysis_interval_seconds=900)
        self.ledger = Ledger(self.root / "financial.sqlite3")
        WallexLiveBroker.initialize_state(self.ledger)
        for key, value in dict(fresh_source_sha256="a" * 64, fresh_config_sha256="b" * 64,
                fresh_permit="original-permit", fresh_contract_sha256=self.contract.sha256,
                service_state="PAUSED_RESTART").items():
            self.ledger.set_meta(key, value)

    def amend(self, **changes):
        return authorize_source_transition(self.ledger, **(dict(
            expected_source_sha256="a" * 64, target_source_sha256="c" * 64,
            artifact_sha256="d" * 64, backup_receipt_sha256="e" * 64,
            operator_instruction="Synthetic operator authorizes five-minute analysis",
            entry_analysis_interval_seconds=300) | changes))

    def test_amendment_binds_original_contract_and_changes_only_source_history(self):
        with self.ledger.connection() as db:
            before = list(db.iterdump())
        receipt = self.amend()
        self.assertEqual(receipt["entry_analysis_interval_seconds"], 300)
        self.assertEqual(receipt["service_contract_sha256"], self.contract.sha256)
        self.assertEqual(source_history(self.ledger), ("a" * 64, "c" * 64))
        with self.ledger.connection() as db:
            after = [line for line in db.iterdump() if "runtime_source_history" not in line]
        self.assertEqual(before, after)
        from royin.runtime_release import entry_analysis_interval
        self.assertEqual(entry_analysis_interval(self.ledger, self.contract), 300)
        self.assertEqual(self.contract.analysis_interval_seconds, 900)

    def test_invalid_or_wrong_contract_cadence_is_rejected_without_append(self):
        for value in (True, 0, 30, "300", 301):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.amend(entry_analysis_interval_seconds=value)
            self.assertIsNone(self.ledger.get_meta("runtime_source_history"))
        self.ledger.set_meta("fresh_contract_sha256", "not-a-contract-hash")
        with self.assertRaises(ValueError):
            self.amend()
        self.assertIsNone(self.ledger.get_meta("runtime_source_history"))

    def test_rehashed_but_mismatched_schedule_and_partial_fields_are_rejected(self):
        self.amend()
        original = json.loads(self.ledger.get_meta("runtime_source_history"))
        for changes in ({"service_contract_sha256": "f" * 64},
                        {"entry_analysis_interval_seconds": True},
                        {"entry_analysis_interval_seconds": None}):
            data = copy.deepcopy(original)
            data[-1].update(changes)
            data[-1]["sha256"] = digest({k:v for k,v in data[-1].items() if k != "sha256"})
            self.ledger.set_meta("runtime_source_history", json.dumps(data))
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                source_history(self.ledger)

    def test_followup_source_upgrade_retains_cadence_and_signals_receive_it(self):
        self.amend()
        authorize_source_transition(self.ledger, expected_source_sha256="c" * 64,
            target_source_sha256="f" * 64, artifact_sha256="d" * 64,
            backup_receipt_sha256="e" * 64, operator_instruction="Synthetic next upgrade")
        with patch("scripts.run_fresh_service.EntrySignals") as constructor:
            signals_for(self.contract, config_for(self.contract), self.root)
        self.assertEqual(constructor.call_args.kwargs["entry_analysis_interval_seconds"], 300)
        self.assertIs(constructor.call_args.kwargs["service_contract"], self.contract)

    def test_pool_authority_is_explicit_bound_and_reaches_live_signal_constructor(self):
        self.amend(model_budget_pool_id='boxapi-pool-test',model_budget_pool_sha256='d'*64)
        with patch("scripts.run_fresh_service.EntrySignals") as constructor:
            signals_for(self.contract,config_for(self.contract),self.root)
        self.assertEqual(constructor.call_args.kwargs['model_budget_pool_id'],'boxapi-pool-test')
        self.assertEqual(constructor.call_args.kwargs['model_budget_pool_sha256'],'d'*64)
        old=json.loads(self.ledger.get_meta('runtime_source_history'))
        del old[-1]['model_budget_pool_sha256']
        old[-1]['sha256']=digest({k:v for k,v in old[-1].items() if k!='sha256'})
        self.ledger.set_meta('runtime_source_history',json.dumps(old))
        with self.assertRaises(ValueError):
            source_history(self.ledger)

    def test_restart_keeps_pending_deadline_then_claims_five_minutes_before_io(self):
        kwargs = dict(run_id=self.contract.service_id, config=config_for(self.contract),
            duration_seconds=self.contract.duration_seconds, cycles=self.contract.cycles,
            interval_seconds=self.contract.poll_seconds, public_get_cap=self.contract.max_public_gets,
            order_tmn=self.contract.max_debit_tmn, minimum_notional_tmn=self.contract.minimum_notional_tmn,
            horizon_max_seconds=self.contract.horizon_max_seconds, service_contract=self.contract,
            capture_dir=self.root / "signals")
        with patch("scripts.run_market_paper.source_bundle_sha256", return_value="a" * 64):
            first = MarketPaperOrchestrator(**kwargs)
            first.ledger.set_meta("next_entry_analysis_at", "9005")
            first.close()
        with patch("scripts.run_market_paper.source_bundle_sha256", return_value="c" * 64):
            resumed = MarketPaperOrchestrator(**kwargs, source_history=("a" * 64, "c" * 64),
                entry_analysis_interval_seconds=300)
        try:
            feed = MagicMock(requests=0)
            with patch("scripts.run_market_paper.public_symbols", side_effect=RuntimeError("stop before HTTP")) as io:
                asyncio.run(resumed._execute_cycle(feed, 8990))
                io.assert_not_called()
                self.assertEqual(resumed.ledger.get_meta("next_entry_analysis_at"), "9005")
                with self.assertRaisesRegex(RuntimeError, "stop before HTTP"):
                    asyncio.run(resumed._execute_cycle(feed, 9090))
                self.assertEqual(resumed.ledger.get_meta("next_entry_analysis_at"), "9390")
                self.assertEqual(resumed.ledger.get_meta("last_entry_cutoff"), "9000")
                asyncio.run(resumed._execute_cycle(feed, 9100))
                self.assertEqual(io.call_count, 1)
            resumed._checkpoint_and_export(9100)
            manifest = json.loads((self.root / "signals/manifest.json").read_text())
            self.assertEqual(manifest["entry_analysis_interval_seconds"], 300)
        finally:
            resumed.close()
