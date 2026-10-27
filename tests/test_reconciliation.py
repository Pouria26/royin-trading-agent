"""Display variance cannot become an implicit deposit, balance correction or retry."""

import hashlib
import json
import unittest
from decimal import Decimal as D

from royin.live_broker import WallexLiveBroker
from royin.markets import Balance
from royin.reconciliation import (
    KEY,
    assess_account_reconciliation,
    authorize_display_variance,
    verify_reconciliation_for_post,
)
from tests import test_fresh_mission as fresh_cases


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        fresh_cases.FreshMissionTests.setUp(self)
        fresh_cases.FreshMissionTests.authorize(self)
        WallexLiveBroker.initialize_state(self.ledger)
        self.ledger.set_meta("fresh_source_sha256", "a" * 64)
        self.ledger.set_meta("service_state", "PAUSED_RESTART")
        allocation = self.ledger.get_balance("TMN").total
        self.ledger.set_balance("TMN", allocation - D("335.2408"))
        self.balances = {"TMN": Balance(D(4999665), D(4999665), D(0))}
        self.now = 1100
        self.reads = [1, 2, 3]
        self.capture()

    def capture(self, *, balances=None, ids=None, account="synthetic-account", timestamp=None):
        directory = self.root / "account-captures"
        directory.mkdir(exist_ok=True)
        payloads = [
            dict(
                success=True,
                result=[dict(clientId=account, type="prop", isActive=True, isSuspend=False)],
            ),
            dict(
                success=True,
                result={
                    a: dict(
                        symbol=a,
                        total=str(b.total),
                        available=str(b.available),
                        freeze=str(b.locked),
                    )
                    for a, b in (balances or self.balances).items()
                },
            ),
            dict(
                success=True, result=dict(orders=[dict(clientOrderId=cid) for cid in (ids or [])])
            ),
        ]
        for index, (endpoint, data) in enumerate(
            zip(
                ("/sub-accounts", "/v1/account/balances-detail", "/v1/account/openOrders"),
                payloads,
                strict=True,
            ),
            1,
        ):
            raw = json.dumps(data).encode()
            sha = hashlib.sha256(raw).hexdigest()
            (directory / (sha + ".json")).write_bytes(raw)
            (directory / f"read-{index}.json").write_text(
                json.dumps(
                    dict(path=endpoint, received_at=timestamp or self.now, status=200, sha256=sha)
                )
            )

    def assess(self, **changes):
        args = dict(
            ledger=self.ledger,
            balances=self.balances,
            ids=[],
            now=self.now,
            read_numbers=self.reads,
        )
        args.update(changes)
        return assess_account_reconciliation(**args)

    def authorize_policy(self):
        return authorize_display_variance(
            self.ledger,
            balances=self.balances,
            ids=[],
            read_numbers=self.reads,
            now=self.now,
            operator_instruction="Synthetic explicit .5-TMN display discrepancy authority",
        )

    def financial(self):
        with self.ledger.connection() as db:
            return {
                name: db.execute("SELECT * FROM " + name + " ORDER BY rowid").fetchall()
                for name in (
                    "balances",
                    "fills",
                    "cost_basis",
                    "order_intents",
                    "realized_pnl",
                    "live_broker_orders",
                )
            }

    def test_small_variance_is_rejected_by_default(self):
        report = self.assess()
        self.assertFalse(report["approved"])
        self.assertEqual(D(report["cash_difference_tmn"]), D(".2408"))
        self.assertIsNone(self.ledger.get_meta(KEY))

    def test_observed_quiescence_keeps_original_running_metadata_instead_of_faking_pause(self):
        self.ledger.set_meta("service_state", "RUNNING")
        receipt = authorize_display_variance(
            self.ledger,
            balances=self.balances,
            ids=[],
            read_numbers=self.reads,
            now=self.now,
            operator_instruction="Synthetic observed exclusive owner lock in maintenance",
            quiescent_restart_receipt_sha256="e" * 64,
        )
        self.assertEqual(receipt["quiescent_restart_receipt_sha256"], "e" * 64)
        self.assertEqual(self.ledger.get_meta("service_state"), "RUNNING")
        self.assertTrue(self.assess()["approved"])

    def test_authorized_variance_preserves_money_and_subtracts_conservative_buffer(self):
        before = self.financial()
        authority = self.authorize_policy()
        report = self.assess()
        self.assertTrue(report["approved"])
        self.assertFalse(report["exact_match"])
        self.assertEqual(report["match_kind"], "BOUNDED_DISPLAY_VARIANCE")
        self.assertEqual(report["authority_sha256"], authority["sha256"])
        self.assertEqual(
            D(report["available_cash_lower_bound_tmn"]),
            self.ledger.get_balance("TMN").total - D(".2592"),
        )
        self.assertEqual(self.financial(), before)
        self.assertIsNone(self.ledger.get_meta("closed_round_trips"))
        self.assertEqual(
            self.old_hash, hashlib.sha256((self.root / "old.sqlite3").read_bytes()).hexdigest()
        )

    def test_policy_requires_paused_explicit_fresh_original_account_evidence(self):
        self.ledger.set_meta("service_state", "RUNNING")
        with self.assertRaises(ValueError):
            self.authorize_policy()
        self.ledger.set_meta("service_state", "PAUSED_RESTART")
        self.capture(account="foreign-account")
        with self.assertRaisesRegex(ValueError, "identity"):
            self.authorize_policy()
        self.capture(timestamp=self.now - 31)
        with self.assertRaisesRegex(ValueError, "stale"):
            self.authorize_policy()
        self.assertIsNone(self.ledger.get_meta(KEY))

    def test_no_unbounded_tolerance_asset_tolerance_or_policy_reset(self):
        self.authorize_policy()
        with self.assertRaises(ValueError):
            self.authorize_policy()
        for delta in (D(".5001"), D("-.5001"), D(1)):
            total = D(4999665) - delta
            original = self.ledger.get_balance("TMN").total
            outside = D(5000000) - D(
                json.loads(self.ledger.get_meta("fresh_authorization"))["allocation_tmn"]
            )
            self.ledger.set_balance("TMN", total - outside)
            self.assertFalse(self.assess()["approved"])
            self.ledger.set_balance("TMN", original)
        self.ledger.set_balance("PUMP", D(".00000001"))
        self.assertFalse(self.assess()["approved"])

    def test_capture_hash_foreign_order_and_fractional_display_fail_closed(self):
        self.authorize_policy()
        self.assertFalse(self.assess(ids=["foreign_order"])["approved"])
        decimal_cash = {"TMN": Balance(D("4999664.8"), D("4999664.8"), D(0))}
        self.assertFalse(self.assess(balances=decimal_cash)["approved"])
        receipt = json.loads((self.root / "account-captures/read-2.json").read_text())
        (self.root / "account-captures" / (receipt["sha256"] + ".json")).write_text("{}")
        with self.assertRaisesRegex(ValueError, "hash"):
            self.assess()

    def test_transport_witness_survives_owned_cash_lock_but_not_tampering_or_excess_debit(self):
        self.authorize_policy()
        report = self.assess()
        cid = "fresh_test_buy_1100"
        self.ledger.record_intent(
            client_id=cid,
            symbol="ETHTMN",
            side="BUY",
            order_type="LIMIT",
            price=D(100),
            quantity=D(1000),
            quote_fee_reserve=D(300),
            timestamp=self.now,
            base_asset="ETH",
            quote_asset="TMN",
        )
        evidence = dict(account_reconciliation=report)
        verify_reconciliation_for_post(
            self.ledger, evidence, cid=cid, debit_tmn=D(100300), now=self.now
        )
        with self.assertRaises(ValueError):
            verify_reconciliation_for_post(
                self.ledger, evidence, cid=cid, debit_tmn=D(5000000), now=self.now
            )
        report["cash_difference_tmn"] = "0"
        with self.assertRaises(ValueError):
            verify_reconciliation_for_post(
                self.ledger, evidence, cid=cid, debit_tmn=D(100300), now=self.now
            )

    def test_bounded_witness_cannot_be_relabelled_as_an_exact_match(self):
        self.authorize_policy()
        report = self.assess()
        report["match_kind"] = "EXACT"
        report["exact_match"] = True
        with self.assertRaises(ValueError):
            verify_reconciliation_for_post(
                self.ledger,
                dict(account_reconciliation=report),
                cid="unused",
                debit_tmn=D(1),
                now=self.now,
            )

    def test_actual_transport_checks_bounded_account_before_issuing_one_synthetic_post(self):
        from unittest.mock import patch

        import httpx

        from royin.risk import RiskResult

        self.authorize_policy()
        report = self.assess()
        cid = "fresh_test_buy_1100"
        fresh_cases.FreshMissionTests.evidence(
            self, cid, quote_received_at=self.now, account_reconciliation=report
        )
        payload = dict(
            success=True,
            result=dict(
                clientOrderId=cid,
                symbol="ETHTMN",
                side="BUY",
                type="LIMIT",
                price="100",
                origQty="1000",
                executedQty="0",
                executedSum="0",
                status="NEW",
                active=True,
                fills=[],
            ),
        )
        broker, _ = fresh_cases.FreshMissionTests.make_broker(self, response=payload)
        risk = RiskResult(
            True,
            "synthetic bounded account admission",
            "ENTER",
            "ETHTMN",
            D(1000),
            D(100),
            D(98),
            D(300),
        )
        with fresh_cases.FreshMissionTests.worker(self), patch("time.time", return_value=self.now):
            result = broker.submit_order(risk, client_id=cid, timestamp=self.now)
        self.assertEqual(result["status"], "OPEN")
        self.assertEqual(len(self.calls), 1)
        self.assertIsInstance(self.calls[0], httpx.Request)
        self.assertEqual(json.loads(self.ledger.get_meta("fresh_transport"))["buys"], 1)

    def test_expired_policy_stale_witness_and_rebound_account_cannot_authorize(self):
        self.authorize_policy()
        report = self.assess()
        self.assertFalse(self.assess(now=self.permit.end_at)["approved"])
        with self.assertRaises(ValueError):
            verify_reconciliation_for_post(
                self.ledger,
                dict(account_reconciliation=report),
                cid="unused",
                debit_tmn=D(1),
                now=self.now + 31,
            )
        policy = json.loads(self.ledger.get_meta(KEY))
        policy["max_total_variance_tmn"] = "5"
        from royin.reconciliation import _digest

        policy["sha256"] = _digest({k: v for k, v in policy.items() if k != "sha256"})
        self.ledger.set_meta(KEY, json.dumps(policy))
        with self.assertRaises(ValueError):
            self.assess()


if __name__ == "__main__":
    unittest.main()
