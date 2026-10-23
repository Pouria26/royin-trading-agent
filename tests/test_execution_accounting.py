"""Independent hand arithmetic and crash boundaries; no exchange/private network."""

import copy
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import patch

import httpx

try:
    import test_live_broker as helpers
except ModuleNotFoundError:
    from tests import test_live_broker as helpers

from royin.ledger import Ledger


class PortfolioClaimTests(unittest.TestCase):
    def test_unbound_nonempty_db_never_initializes_or_resets_cash(self):
        ledger=Ledger()
        ledger.set_balance("TMN",D(1234))
        with self.assertRaises(ValueError):
            ledger.initialize_portfolio(D(5000000),quote_asset="TMN",binding="a"*64)
        self.assertEqual(ledger.get_balance("TMN").free,D(1234))

    def test_pending_claim_survives_restart_and_complete_is_bound(self):
        from royin.decision import Decision
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"state.sqlite3"
            ledger=Ledger(path)
            ledger.initialize_portfolio(D(5000000),quote_asset="TMN",binding="a"*64)
            self.assertTrue(ledger.claim_candle("USDTTMN",1200,"b"*64,60))
            ledger=Ledger(path)
            with self.assertRaises(BlockingIOError):
                ledger.claim_candle("USDTTMN",1200,"b"*64,60)
            decision=Decision(decision_id="d",symbol="USDTTMN",action="WAIT",cutoff=1200,
                snapshot_sha256="b"*64,evidence_ids=("synthetic",),reason="test",invalidation="test")
            with ledger.transaction():
                ledger.complete_candle("USDTTMN",1200,decision)
            self.assertFalse(ledger.claim_candle("USDTTMN",1200,"b"*64,60))
            with self.assertRaises(ValueError):
                ledger.claim_candle("USDTTMN",1320,"b"*64,60)
            self.assertEqual(ledger.get_balance("TMN").free,D(5000000))


class ExecutionAccountingTests(unittest.TestCase):
    def setUp(self):
        self.helper = helpers.WallexLiveBrokerTests()
        self.helper.setUp()
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "ledger.sqlite"
        self.helper.ledger = Ledger(self.path)
        self.helper.ledger.set_balance("TMN", D("5000000"))
        self.fixture = json.loads(
            (Path(__file__).parent / "fixtures/wallex-orders.json").read_text()
        )
        self.current = self.fixture["new"]
        self.broker = self.helper.broker(
            handler=lambda _: httpx.Response(200, json={"success": True, "result": self.current})
        )

    def tearDown(self):
        self.helper.tearDown()
        self.temp.cleanup()

    def submit(self):
        return self.helper.submit(self.broker)

    def reconcile(self):
        return self.broker.reconcile_order("order_1", timestamp=1788220900)

    def balances(self):
        return self.helper.ledger.get_all_balances()

    def test_partial_cancel_restart_exact_oracle_and_duplicate(self):
        self.submit()
        self.current = self.fixture["partial"]
        self.assertEqual(self.reconcile()["status"], "PARTIALLY_FILLED")
        # Reserve 1,499,485; allocation 460,000+1,380; savings 2,006.
        self.assertEqual(self.balances()["TMN"].free, D("3502521"))
        self.assertEqual(self.balances()["TMN"].locked, D("1038105"))
        self.assertEqual(self.balances()["USDT"].free, D("2"))
        self.current = self.fixture["canceled"]
        before = self.balances()
        self.assertEqual(
            self.broker.cancel_order("order_1", timestamp=1788220900)["status"], "UNKNOWN"
        )
        self.assertEqual(self.balances(), before)
        self.helper.ledger = Ledger(self.path)
        self.broker = self.helper.broker(
            handler=lambda _: httpx.Response(200, json={"success": True, "result": self.current})
        )
        self.assertEqual(self.reconcile()["status"], "PARTIALLY_FILLED_CANCELED")
        # Cost = 458000 + 1374 + 230000 = 689374; net base = 2 + 1 - .003.
        self.assertEqual(self.balances()["TMN"].free, D("4310626"))
        self.assertEqual(self.balances()["TMN"].locked, D(0))
        self.assertEqual(self.balances()["USDT"].free, D("2.997"))
        with self.helper.ledger.connection() as db:
            self.assertEqual(
                tuple(
                    map(
                        D,
                        db.execute(
                            "SELECT total_quantity,total_cost_quote FROM cost_basis"
                        ).fetchone(),
                    )
                ),
                (D("2.997"), D("689374")),
            )
        settled = self.balances()
        for _ in range(3):
            self.assertEqual(self.reconcile()["status"], "PARTIALLY_FILLED_CANCELED")
            self.assertEqual(self.balances(), settled)

    def test_missing_revised_stale_future_wrong_asset_fail_closed(self):
        self.submit()
        self.current = self.fixture["partial"]
        self.reconcile()
        expected = self.balances()
        changes = []
        for field, value in [
            ("fills", []),
            ("executedSum", "1"),
            ("executedQty", "6.5"),
            ("symbol", "BTCTMN"),
        ]:
            r = copy.deepcopy(self.fixture["canceled"])
            r[field] = value
            changes.append(r)
        for field, value in [
            ("fee", "1375"),
            ("feeAsset", "BTC"),
            ("timestamp", "2026-09-02T00:00:00Z"),
        ]:
            r = copy.deepcopy(self.fixture["canceled"])
            r["fills"][1][field] = value
            changes.append(r)
        changes.append(self.fixture["new"])
        for r in changes:
            with self.subTest(result=r):
                self.current = r
                self.assertEqual(self.reconcile()["status"], "UNKNOWN")
                self.assertEqual(self.balances(), expected)

    def test_intent_and_state_rollback_before_http_on_disk_error(self):
        with self.helper.ledger.transaction() as db:
            db.execute(
                "CREATE TRIGGER disk_failure BEFORE INSERT ON live_broker_orders BEGIN SELECT RAISE(ABORT,'disk fixture'); END"
            )
        with self.assertRaises(sqlite3.DatabaseError):
            self.submit()
        self.assertFalse(self.helper.requests)
        self.assertEqual(self.balances()["TMN"].free, D("5000000"))
        with self.helper.ledger.connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM order_intents").fetchone()[0], 0)

    def test_crash_before_send_recovers_same_intent_without_resubmission(self):
        with (
            patch.object(self.broker, "_request", side_effect=SystemExit),
            self.assertRaises(SystemExit),
        ):
            self.submit()
        self.assertFalse(self.helper.requests)
        restarted = Ledger(self.path)
        with restarted.connection() as db:
            self.assertEqual(
                db.execute("SELECT status FROM order_intents").fetchone()[0], "SUBMITTING"
            )
        self.helper.ledger = restarted
        self.broker = self.helper.broker(
            handler=lambda _: httpx.Response(
                200, json={"success": True, "result": self.fixture["canceled"]}
            )
        )
        self.assertEqual(self.reconcile()["status"], "PARTIALLY_FILLED_CANCELED")
        self.assertEqual(self.balances()["TMN"].free, D("4310626"))
        self.assertEqual([r.method for r in self.helper.requests], ["GET"])

    def test_whole_snapshot_rolls_back_on_second_fill_disk_error(self):
        self.submit()
        with self.helper.ledger.transaction() as db:
            db.execute(
                "CREATE TRIGGER disk_failure BEFORE INSERT ON fills WHEN NEW.quantity='1' BEGIN SELECT RAISE(ABORT,'disk fixture'); END"
            )
        before = self.balances()
        self.current = self.fixture["canceled"]
        with self.assertRaises(sqlite3.DatabaseError):
            self.reconcile()
        self.assertEqual(self.balances(), before)
        with self.helper.ledger.connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM fills").fetchone()[0], 0)

    def test_ordered_and_unordered_cumulative_fills_match(self):
        self.submit()
        self.current = copy.deepcopy(self.fixture["canceled"])
        self.current["fills"].reverse()
        self.reconcile()
        before = self.balances()
        self.current = self.fixture["canceled"]
        self.reconcile()
        self.assertEqual(self.balances(), before)

    def test_worker_lock_rejects_second_ledger_and_recovers_after_process_death(self):
        second = Ledger(self.path)
        with (
            self.helper.ledger.worker(),
            self.assertRaises(sqlite3.OperationalError),
            second.worker(),
        ):
            self.fail("second worker entered")
        code = "import sys; sys.path.insert(0,sys.argv.pop(1)); from royin.ledger import Ledger; import time; l=Ledger(sys.argv[1]);\nwith l.worker():\n print('LOCKED',flush=True); time.sleep(30)"
        # Windows venv python.exe may redirect to a second process; kill the actual lock owner.
        child = subprocess.Popen(
            [getattr(sys, "_base_executable", sys.executable), "-c", code,
             str(Path(__file__).resolve().parents[1] / "src"), str(self.path)],
            stdout=subprocess.PIPE,
            text=True,
        )
        try:
            self.assertEqual(child.stdout.readline().strip(), "LOCKED")
            with self.assertRaises(sqlite3.OperationalError), second.worker():
                self.fail("second worker entered")
        finally:
            child.kill()
            child.wait(timeout=5)
            child.stdout.close()
        with second.worker():
            self.assertTrue(True)


class LedgerCancellationOracles(unittest.TestCase):
    def test_quote_and_base_fee_sell_realized_and_residual_basis(self):
        ledger = Ledger()
        ledger.set_balance("TMN", D("1000"))
        for cid, side, price, quantity, fee, asset in [
            ("buy", "BUY", "100", "2", "2", "TMN"),
            ("sell_quote", "SELL", "120", "1", "1.2", "TMN"),
            ("sell_base", "SELL", "110", ".5", ".1", "USDT"),
        ]:
            ledger.record_intent(
                client_id=cid,
                symbol="USDTTMN",
                side=side,
                order_type="LIMIT",
                price=D(price),
                quantity=D(quantity),
                quote_fee_reserve=D(fee) if asset == "TMN" else D(0),
                timestamp=1000,
            )
            ledger.record_fill(
                fill_id=cid,
                client_id=cid,
                price=D(price),
                quantity=D(quantity),
                fee=D(fee),
                fee_asset=asset,
                timestamp=1001,
            )
        self.assertEqual(ledger.get_balance("TMN").free, D("971.8"))
        self.assertEqual(ledger.get_balance("USDT").free, D(".4"))
        self.assertEqual(ledger.get_realized_pnl(), D("12.2"))
        with ledger.connection() as db:
            self.assertEqual(
                tuple(
                    map(
                        D,
                        db.execute(
                            "SELECT total_quantity,total_cost_quote FROM cost_basis"
                        ).fetchone(),
                    )
                ),
                (D(".4"), D("40.4")),
            )
        self.assertEqual(ledger.get_equity({"USDTTMN": D("110")}), D("1015.8"))

    def test_repeated_partial_cancel_cannot_unlock_another_order(self):
        ledger = Ledger()
        ledger.set_balance("TMN", D("1000"))
        for cid in ("a", "b"):
            ledger.record_intent(
                client_id=cid,
                symbol="USDTTMN",
                side="BUY",
                order_type="LIMIT",
                price=D("10"),
                quantity=D("3"),
                quote_fee_reserve=D("1"),
                timestamp=1000,
            )
        fill = dict(
            fill_id="f",
            client_id="a",
            price=D("10"),
            quantity=D("1"),
            fee=D(".1"),
            fee_asset="TMN",
            timestamp=1001,
        )
        ledger.record_fill(**fill)
        self.assertTrue(ledger.cancel_intent("a"))
        self.assertFalse(ledger.cancel_intent("a"))
        self.assertEqual(ledger.get_balance("TMN").locked, D("31"))
        with self.assertRaises(ValueError):
            ledger.record_fill(**dict(fill, fill_id="new"))
        with self.assertRaises(ValueError):
            ledger.record_fill(**dict(fill, timestamp=1002))

    def test_audit_emits_no_tentative_fill_or_intent_on_rollback(self):
        from royin.logger import AuditLogger

        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "audit"
            audit = AuditLogger(
                log_dir=log_dir,
                enable_console=False,
                run_id="audit_rollback_test",
                mode="paper",
                source="PAPER",
            )
            ledger = Ledger(Path(temp_dir) / "audit_test.db", audit=audit)
            ledger.set_balance("TMN", D("5000000"))

            # 1. Rollback on second fill failure: no FILL or RECONCILIATION in audit
            with ledger.transaction() as db:
                db.execute(
                    "CREATE TRIGGER test_fill_disk_fail BEFORE INSERT ON fills "
                    "WHEN NEW.quantity='1' BEGIN SELECT RAISE(ABORT, 'fill disk failure'); END"
                )

            with self.assertRaises(sqlite3.DatabaseError), ledger.transaction():
                ledger.record_intent(
                    client_id="tx_ord_1",
                    symbol="USDTTMN",
                    side="BUY",
                    order_type="LIMIT",
                    price=D("100"),
                    quantity=D("3"),
                    timestamp=1000,
                )
                ledger.record_fill(
                    fill_id="f1",
                    client_id="tx_ord_1",
                    price=D("100"),
                    quantity=D("2"),
                    fee=D("0"),
                    fee_asset="TMN",
                    timestamp=1001,
                )
                ledger.record_fill(
                    fill_id="f2",
                    client_id="tx_ord_1",
                    price=D("100"),
                    quantity=D("1"),
                    fee=D("0"),
                    fee_asset="TMN",
                    timestamp=1002,
                )

            with ledger.connection() as db:
                self.assertEqual(db.execute("SELECT count(*) FROM fills").fetchone()[0], 0)
                self.assertEqual(db.execute("SELECT count(*) FROM order_intents").fetchone()[0], 0)

            audit.close()
            events = (
                [json.loads(line)["event_type"] for line in Path(audit.audit_path).read_text(encoding="utf-8").splitlines()]
                if Path(audit.audit_path).exists()
                else []
            )
            self.assertEqual(events, [], "Rollback must leave zero tentative audit events")

            # 2. Successful commit produces matching events
            audit2 = AuditLogger(
                log_dir=log_dir,
                enable_console=False,
                run_id="audit_commit_test",
                mode="paper",
                source="PAPER",
            )
            ledger.audit = audit2
            with ledger.transaction():
                ledger.record_intent(
                    client_id="comm_ord",
                    symbol="USDTTMN",
                    side="BUY",
                    order_type="LIMIT",
                    price=D("100"),
                    quantity=D("2"),
                    timestamp=2000,
                )
                ledger.record_fill(
                    fill_id="cf1",
                    client_id="comm_ord",
                    price=D("100"),
                    quantity=D("2"),
                    fee=D("0"),
                    fee_asset="TMN",
                    timestamp=2001,
                )

            audit2.close()
            committed_events = [
                json.loads(line)["event_type"]
                for line in Path(audit2.audit_path).read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(committed_events, ["INTENT", "FILL", "LEDGER_RECONCILIATION"])

    def test_pre_intent_fill_is_rejected_lower_bound(self):
        ledger = Ledger()
        ledger.set_balance("TMN", D("1000000"))
        ledger.record_intent(
            client_id="t_bound_ord",
            symbol="USDTTMN",
            side="BUY",
            order_type="LIMIT",
            price=D("100"),
            quantity=D("5"),
            timestamp=1000,
        )

        # Before intent (999) must be rejected
        with self.assertRaisesRegex(ValueError, "precedes intent created_at"):
            ledger.record_fill(
                fill_id="f_before",
                client_id="t_bound_ord",
                price=D("100"),
                quantity=D("1"),
                fee=D("0"),
                fee_asset="TMN",
                timestamp=999,
            )

        # Equal (1000) is accepted
        f_eq = ledger.record_fill(
            fill_id="f_equal",
            client_id="t_bound_ord",
            price=D("100"),
            quantity=D("1"),
            fee=D("0"),
            fee_asset="TMN",
            timestamp=1000,
        )
        self.assertEqual(f_eq.timestamp, 1000)

        # After (1001) is accepted
        f_after = ledger.record_fill(
            fill_id="f_after",
            client_id="t_bound_ord",
            price=D("100"),
            quantity=D("1"),
            fee=D("0"),
            fee_asset="TMN",
            timestamp=1001,
        )
        self.assertEqual(f_after.timestamp, 1001)
