"""A reviewed legacy residual is retained; the ordinary 500-TMN gate stays strict."""

import hashlib
import json
import unittest
from dataclasses import asdict
from decimal import Decimal as D

from royin.live_broker import WallexLiveBroker
from royin.operator_entry import STATE_KEY, authorize_operator_entry
from royin.residuals import (
    KEY,
    OPERATOR_EXCEPTION_KEY,
    authorize_operator_residual_exception,
    quarantine_residual,
    quarantined_residuals,
)
from royin.risk import MarketRules
from royin.runtime_release import authorize_source_transition, source_history
from tests import test_fresh_mission as fresh_cases


class OperatorResidualExceptionTests(unittest.TestCase):
    def setUp(self):
        fresh_cases.FreshMissionTests.setUp(self)
        fresh_cases.FreshMissionTests.authorize(self)
        WallexLiveBroker.initialize_state(self.ledger)
        self.ledger.set_meta("fresh_source_sha256", "a" * 64)
        self.ledger.set_meta("fresh_config_sha256", "b" * 64)
        self.rules = MarketRules(
            "PUMPTMN", "PUMP", "TMN", D(1), D(".1"), D(100000), D(".1"), D(".0025"), D(".003")
        )
        auth = authorize_operator_entry(
            self.ledger,
            self.permit,
            now=1010,
            expires_at=1800,
            symbol="PUMPTMN",
            operator_instruction="Synthetic original operator entry authority",
        )
        self.buy = auth["client_id"]
        self.sell = "fresh_test_exit_1100"
        self.ledger.set_meta(
            "fresh_evidence_" + self.buy,
            json.dumps(
                dict(
                    source_kind="OPERATOR",
                    action="ENTER",
                    symbol=self.rules.symbol,
                    operator_authority_sha256=auth["sha256"],
                    target_net_approved=False,
                    rules_sha256=hashlib.sha256(
                        json.dumps(asdict(self.rules), sort_keys=True, default=str).encode()
                    ).hexdigest(),
                )
            ),
        )
        self.ledger.record_intent(
            client_id=self.buy,
            symbol=self.rules.symbol,
            side="BUY",
            order_type="LIMIT",
            price=D(1150),
            quantity=D(130),
            quote_fee_reserve=D("448.5"),
            timestamp=1011,
            base_asset="PUMP",
            quote_asset="TMN",
        )
        self.ledger.record_fill(
            fill_id="buy-fill",
            client_id=self.buy,
            price=D(1150),
            quantity=D(130),
            fee=D(".325"),
            fee_asset="PUMP",
            timestamp=1012,
        )
        self.ledger.record_intent(
            client_id=self.sell,
            symbol=self.rules.symbol,
            side="SELL",
            order_type="LIMIT",
            price=D(1157),
            quantity=D("129.2"),
            timestamp=1100,
            base_asset="PUMP",
            quote_asset="TMN",
        )
        self.ledger.record_fill(
            fill_id="sell-fill",
            client_id=self.sell,
            price=D(1158),
            quantity=D("129.2"),
            fee=D("448.8408"),
            fee_asset="TMN",
            timestamp=1101,
        )
        with self.ledger.transaction() as db:
            for cid in (self.buy, self.sell):
                row = db.execute(
                    "SELECT client_id,symbol,side,order_type,price,quantity,status,created_at "
                    "FROM order_intents WHERE client_id=?",
                    (cid,),
                ).fetchone()
                db.execute(
                    "INSERT INTO live_broker_orders(client_id,symbol,side,order_type,price,quantity,status,created_at,updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (*row, 1102),
                )
        self.ledger.set_meta(
            STATE_KEY,
            json.dumps(
                dict(state="ATTEMPTED", authority_sha256=auth["sha256"], client_id=self.buy)
            ),
        )
        self.ledger.set_meta("service_state", "PAUSED_RESTART")

    def approve(self, **changes):
        args = dict(
            price_tmn=D(1158),
            quote_received_at=1200,
            now=1202,
            operator_instruction="Synthetic explicit exception for the retained original residual, max600TMN",
        )
        args.update(changes)
        return authorize_operator_residual_exception(self.ledger, self.rules, **args)

    def quarantine(self):
        return quarantine_residual(
            self.ledger, self.rules, price_tmn=D(1158), quote_received_at=1200, now=1203
        )

    def financial(self):
        with self.ledger.connection() as db:
            return {
                name: db.execute("SELECT * FROM " + name + " ORDER BY rowid").fetchall()
                for name in (
                    "balances",
                    "cost_basis",
                    "fills",
                    "order_intents",
                    "realized_pnl",
                    "live_broker_orders",
                )
            }

    def test_actual_residual_stays_blocked_without_separate_authority(self):
        before = self.financial()
        self.assertFalse(self.quarantine())
        self.assertEqual(quarantined_residuals(self.ledger), {})
        self.assertIsNone(self.ledger.get_meta(OPERATOR_EXCEPTION_KEY))
        self.assertEqual(self.financial(), before)

    def test_observed_quiescence_does_not_forge_a_graceful_worker_stop(self):
        self.ledger.set_meta("service_state", "RUNNING")
        receipt = self.approve(quiescent_restart_receipt_sha256="e" * 64)
        self.assertEqual(receipt["quiescent_restart_receipt_sha256"], "e" * 64)
        self.assertEqual(self.ledger.get_meta("service_state"), "RUNNING")
        self.assertTrue(self.quarantine())

    def test_approved_receipt_retains_exact_inventory_basis_and_all_financial_rows(self):
        before = self.financial()
        authority = self.approve()
        self.assertTrue(self.quarantine())
        self.assertEqual(quarantined_residuals(self.ledger), {"PUMP": D(".475")})
        receipt = json.loads(self.ledger.get_meta(KEY))[0]
        self.assertEqual(receipt["schema_version"], 2)
        self.assertEqual(receipt["value_bound_tmn"], "600")
        self.assertEqual(D(receipt["marked_value_tmn"]), D("550.05"))
        self.assertEqual(receipt["operator_exception_sha256"], authority["sha256"])
        self.assertEqual(self.financial(), before)
        self.assertIsNone(self.ledger.get_meta("closed_round_trips"))
        self.assertEqual(self.ledger.get_meta("position_origin_PUMP"), self.buy)

    def test_missing_approval_nonquiescence_repeat_and_caps_fail_closed(self):
        for changes in (
            dict(operator_instruction=""),
            dict(price_tmn=D(1000)),
            dict(price_tmn=D(1300)),
            dict(now=1206),
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.approve(**changes)
            self.assertIsNone(self.ledger.get_meta(OPERATOR_EXCEPTION_KEY))
        self.ledger.set_meta("service_state", "RUNNING")
        with self.assertRaises(ValueError):
            self.approve()
        self.ledger.set_meta("service_state", "PAUSED_RESTART")
        self.approve()
        with self.assertRaises(ValueError):
            self.approve()

    def test_tampered_proof_cap_source_or_quarantine_authority_cannot_be_reused(self):
        self.approve()
        original = self.ledger.get_meta(OPERATOR_EXCEPTION_KEY)
        from royin.residuals import _digest

        for key, value in (
            ("maximum_marked_value_tmn", "1000"),
            ("source_sha256", "f" * 64),
            ("asset", "OTHER"),
        ):
            bad = json.loads(original)
            bad[key] = value
            bad["sha256"] = _digest({k: v for k, v in bad.items() if k != "sha256"})
            self.ledger.set_meta(OPERATOR_EXCEPTION_KEY, json.dumps(bad))
            with self.assertRaises(ValueError):
                quarantined_residuals(self.ledger)
        self.ledger.set_meta(OPERATOR_EXCEPTION_KEY, original)
        self.quarantine()
        saved = json.loads(self.ledger.get_meta(KEY))
        saved[0]["operator_exception_sha256"] = "f" * 64
        saved[0]["sha256"] = _digest({k: v for k, v in saved[0].items() if k != "sha256"})
        self.ledger.set_meta(KEY, json.dumps(saved))
        with self.assertRaises(ValueError):
            quarantined_residuals(self.ledger)

    def test_pending_unknown_or_changed_inventory_never_receives_an_exception(self):
        self.ledger.record_intent(
            client_id="fresh_test_unknown",
            symbol="ETHTMN",
            side="BUY",
            order_type="LIMIT",
            price=D(100),
            quantity=D(1000),
            timestamp=1200,
            base_asset="ETH",
            quote_asset="TMN",
        )
        with self.assertRaises(ValueError):
            self.approve()
        self.ledger.cancel_intent("fresh_test_unknown")
        self.ledger.set_balance("PUMP", D(".476"))
        with self.assertRaises(ValueError):
            self.approve()
        self.assertIsNone(self.ledger.get_meta(OPERATOR_EXCEPTION_KEY))

    def test_source_upgrade_preserves_exception_and_money_without_faking_completion(self):
        self.approve()
        self.quarantine()
        before = self.financial()
        original_authority = self.ledger.get_meta(OPERATOR_EXCEPTION_KEY)
        authorize_source_transition(
            self.ledger,
            expected_source_sha256="a" * 64,
            target_source_sha256="c" * 64,
            artifact_sha256="d" * 64,
            backup_receipt_sha256="e" * 64,
            operator_instruction="Synthetic reviewed immutable continuation after retained-residual authority",
        )
        self.assertEqual(source_history(self.ledger), ("a" * 64, "c" * 64))
        self.assertEqual(self.ledger.get_meta(OPERATOR_EXCEPTION_KEY), original_authority)
        self.assertEqual(quarantined_residuals(self.ledger), {"PUMP": D(".475")})
        self.assertEqual(self.financial(), before)
        self.assertIsNone(self.ledger.get_meta("closed_round_trips"))
        self.assertEqual(
            self.old_hash, hashlib.sha256((self.root / "old.sqlite3").read_bytes()).hexdigest()
        )

    def test_restart_unblocks_only_the_proven_residual_reason_and_consumes_no_authority(self):
        from scripts.run_fresh_service import FreshEngine

        self.approve()
        self.quarantine()
        engine = FreshEngine(
            self.ledger,
            self.permit,
            None,
            self.config,
            self.root,
            client=None,
            feed=None,
            signals=None,
        )
        self.ledger.set_meta("entry_block_reason", "UNSELLABLE_RESIDUAL")
        before = self.financial()
        self.assertFalse(engine.position_tick(1300))
        self.assertEqual(self.ledger.get_meta("entry_block_reason"), "")
        self.assertTrue(engine.operator_entry_tick(1300))
        self.assertEqual(json.loads(self.ledger.get_meta(STATE_KEY))["state"], "COMPLETE")
        self.assertEqual(self.financial(), before)
        self.assertIsNone(self.ledger.get_meta("closed_round_trips"))
        self.ledger.set_meta("entry_block_reason", "ACCOUNT_RECONCILIATION_REQUIRED")
        self.assertFalse(engine.position_tick(1301))
        self.assertEqual(
            self.ledger.get_meta("entry_block_reason"), "ACCOUNT_RECONCILIATION_REQUIRED"
        )

    def test_research_selection_of_the_retained_asset_cannot_create_an_intent(self):
        import asyncio
        from types import SimpleNamespace

        from scripts.run_fresh_service import FreshEngine

        self.approve()
        self.quarantine()
        engine = FreshEngine(
            self.ledger,
            self.permit,
            None,
            self.config,
            self.root,
            client=None,
            feed=None,
            signals=None,
        )
        engine.rules = lambda _: self.rules
        decision = SimpleNamespace(
            symbol="PUMPTMN",
            decision_id="synthetic-retained-asset",
            snapshot_sha256="a" * 64,
            cutoff=1300,
            forecast=object(),
        )
        before = self.financial()
        asyncio.run(
            engine.execute_selection(
                decision,
                None,
                None,
                dict(host_outcome="MODEL_DECISION", evidence_kind="REAL_MODEL_ATTEMPT"),
                D(1),
            )
        )
        self.assertEqual(self.financial(), before)
        gate = json.loads(self.ledger.get_meta("last_entry_gate"))
        self.assertEqual(gate["reason"], "Audited residual asset cannot be repurchased")
        self.assertFalse(gate["approved"])


if __name__ == "__main__":
    unittest.main()
