"""Hand-calculated paper outcomes; technical correctness is not trading win probability."""

import json
import sqlite3
import tempfile
import unittest
from contextlib import suppress
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import MagicMock, patch

from royin.broker import PaperBroker
from royin.ledger import Ledger
from royin.market_data import Candle
from royin.risk import MarketRules, PositionProtectionPolicy, RiskResult


def rules():
    return MarketRules("USDTTMN","USDT","TMN",D(".01"),D(".01"),D(1),D(".01"),D(".003"),D(".003"))


def policy():
    return PositionProtectionPolicy(D(".02"),D(".01"),D(".025"),30,300,2000,10,5,D(30))


class ProtectionTests(unittest.TestCase):
    def test_replayed_audit_keeps_original_revision_and_run(self):
        from royin.logger import AuditLogger
        old=AuditLogger(Path(self.temp.name)/"old",False,run_id="original",hashes={"code":"a"*64})
        self.ledger.audit=old
        with patch.object(old,"record_event",side_effect=OSError),self.assertRaises(OSError):
            self.ledger.record_intent(client_id="another",symbol="USDTTMN",side="BUY",order_type="LIMIT",
                price=D(100),quantity=D(".1"),timestamp=1002,quote_fee_reserve=D(0))
        old.close()
        new=AuditLogger(Path(self.temp.name)/"new",False,run_id="new",hashes={"code":"b"*64})
        self.addCleanup(new.close)
        recovered=Ledger(self.path,audit=new)
        recovered.flush_audit()
        rows=[json.loads(line) for line in new.audit_path.read_text().splitlines()]
        last=rows[-1]
        self.assertEqual(last["run_id"],"original")
        self.assertEqual(last["hashes"]["code"],"a"*64)

    def test_model_timeout_does_not_own_the_host_stop(self):
        import asyncio
        async def check():
            model=asyncio.create_task(asyncio.sleep(30))
            try:
                result=self.tick("90",1010)
                self.assertEqual(result["action"],"EXIT")
                self.assertFalse(model.done())
            finally:
                model.cancel()
                with suppress(asyncio.CancelledError):
                    await model
        asyncio.run(check())

    def test_audit_write_before_ack_crash_replays_same_durable_event_id(self):
        audit=MagicMock()
        self.ledger.audit=audit
        with self.ledger.connection() as db,db:
            db.execute("CREATE TRIGGER fail_audit_ack BEFORE UPDATE ON audit_outbox BEGIN SELECT RAISE(ABORT,'synthetic ack failure'); END")
        with self.assertRaises(sqlite3.DatabaseError):
            self.ledger.flush_audit()
        first=audit.record_event.call_args.args[2]["journal_event_id"]
        with self.ledger.connection() as db,db:
            db.execute("DROP TRIGGER fail_audit_ack")
        audit.reset_mock()
        self.ledger.flush_audit()
        self.assertEqual(audit.record_event.call_args_list[0].args[2]["journal_event_id"],first)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/"paper.sqlite3"
        self.ledger=Ledger(self.path)
        self.ledger.initialize_portfolio(D(1000),quote_asset="TMN",binding="a"*64)
        self.broker=PaperBroker(self.ledger,rules())
        risk=RiskResult(True,"synthetic ENTER","ENTER","USDTTMN",D(1),D(100),D(98),D(".3"))
        self.broker.submit_order(risk,client_id="buy",timestamp=1000)
        self.broker.reconcile_order("buy",simulated_state="FILLED",timestamp=1001)
        self.broker.arm_protection(policy(),opened_at=1001,entry_price=D(100))

    def tick(self, price, t):
        return self.broker.observe_quote(D(price),source_time=t,received_at=t,now=t,policy=policy())

    def test_above_checkpoint_holds_then_trailing_exits_hand_oracle(self):
        first=self.tick("103",1010)
        self.assertEqual(first["action"],"WAIT")
        self.assertTrue(first["review_due"])
        view=self.broker.export_state(D(103),now=1010)
        self.assertEqual(D(view["gross_price_change_tmn"]),D(3))
        self.assertEqual(D(view["net_if_exit_pnl_tmn"]),D("2.391"))
        self.assertEqual(self.tick("104",1020)["trailing_stop_price"],"102.96")
        result=self.tick("102",1030)
        self.assertEqual(result["action"],"EXIT")
        self.assertEqual(self.ledger.get_balance("TMN").free,D("1001.343153"))
        self.assertEqual(self.ledger.get_realized_pnl(),D("1.343153"))
        self.assertEqual(self.ledger.get_balance("USDT").total,D(0))

    def test_unfillable_stop_is_durable_and_executes_after_recovery_even_if_price_bounces(self):
        result = self.broker.observe_quote(D(90),source_time=1010,received_at=1010,now=1010,
            policy=policy(),execution_available=False)
        self.assertEqual(result["status"],"EXIT_REQUIRED_NO_DEPTH")
        self.assertEqual(self.ledger.get_balance("USDT").total,D(1))
        state = json.loads(self.ledger.get_meta("protection_USDTTMN"))
        self.assertEqual(state["high_water"],"100")
        self.assertEqual(state["pending_exit_reason"],"STOP_OR_TRAILING")
        self.broker = PaperBroker(Ledger(self.path),rules())
        result = self.tick("105",1020)
        self.assertEqual(result["action"],"EXIT")
        self.assertEqual(self.ledger.get_balance("USDT").total,D(0))
        self.assertEqual(self.ledger.get_balance("TMN").free,D(1000)-D("100.3")+D(105)*D(".9995")*D(".997"))

    def test_unexecutable_high_never_tightens_stop_or_inflates_peak(self):
        result = self.broker.observe_quote(D(120),source_time=1010,received_at=1010,now=1010,
            policy=policy(),execution_available=False)
        self.assertEqual(result["status"],"NO_EXECUTABLE_DEPTH")
        state = json.loads(self.ledger.get_meta("protection_USDTTMN"))
        self.assertEqual(state["high_water"],"100")
        self.assertEqual(state["trailing_stop_price"],"98.00")
        self.assertNotIn("pending_exit_reason",state)

    def test_finalization_closes_protection_and_allows_a_new_fill_binding(self):
        result = self.broker.finalize_portfolio(D(105),timestamp=1010)
        self.assertEqual(result["status"],"FINALIZED")
        self.assertEqual(json.loads(self.ledger.get_meta("protection_USDTTMN"))["status"],"CLOSED")
        risk = RiskResult(True,"next technical entry","ENTER","USDTTMN",D(1),D(100),D(98),D(".3"))
        self.broker.submit_order(risk,client_id="second-buy",timestamp=1020)
        self.broker.reconcile_order("second-buy",simulated_state="FILLED",timestamp=1020)
        state = self.broker.arm_protection(policy(),opened_at=1020,entry_price=D(100))
        self.assertEqual(state["opened_at"],1020)
        self.assertEqual(state["status"],"OPEN")
        self.assertEqual(state["high_water"],"100")

    def test_gap_through_stop_uses_seen_bid_not_promised_stop_price(self):
        self.tick("90",1010)
        self.assertEqual(self.ledger.get_balance("TMN").free,D("989.385135"))
        self.assertEqual(self.ledger.get_realized_pnl(),D("-10.614865"))

    def test_restart_preserves_peak_no_reset_and_repeated_exit_no_duplicate(self):
        self.tick("110",1010)
        before=self.ledger.get_balance("TMN").free
        self.ledger=Ledger(self.path)
        self.assertFalse(self.ledger.initialize_portfolio(D(1000),quote_asset="TMN",binding="a"*64))
        self.assertEqual(self.ledger.get_balance("TMN").free,before)
        self.broker=PaperBroker(self.ledger,rules())
        state=self.broker.arm_protection(policy(),opened_at=1001,entry_price=D(100))
        self.assertEqual(state["high_water"],"110")
        self.assertEqual(state["trailing_stop_price"],"108.90")
        self.tick("108",1020)
        after=self.ledger.get_all_balances()
        self.tick("108",1020)
        self.assertEqual(self.ledger.get_all_balances(),after)
        with self.ledger.connection() as db:
            self.assertEqual(db.execute("select count(*) from fills").fetchone()[0],2)

    def test_stale_no_tighten_and_deadline_requires_fresh_execution_quote(self):
        result=self.broker.observe_quote(D(120),source_time=1010,received_at=1020,now=1400,policy=policy())
        self.assertEqual(result["status"],"EXIT_REQUIRED_STALE_QUOTE")
        self.assertEqual(self.ledger.get_balance("USDT").total,D(1))
        self.assertEqual(json.loads(self.ledger.get_meta("protection_USDTTMN"))["high_water"],"100")
        result=self.tick("101",1401)
        self.assertEqual(result["exit_reason"],"HARD_HOLDING_OR_DEADLINE")

    def test_future_high_not_used_before_same_bar_low_and_policy_never_loosened(self):
        self.broker.process_candle(Candle(1010,D(100),D(120),D(99),D(101),D(10)),candle_interval=60)
        self.assertEqual(self.ledger.get_balance("USDT").total,D(1))
        self.assertEqual(self.broker.active_stop_prices["USDTTMN"],D(98))
        with self.assertRaises(ValueError):
            self.broker.arm_protection(replace(policy(),trailing_drawdown_pct=D(".2")),opened_at=1001,entry_price=D(100))

    def test_audit_failure_after_commit_retains_outbox_and_recoverable_money(self):
        audit=MagicMock()
        audit.record_event.side_effect=OSError("synthetic disk failure")
        self.ledger.audit=audit
        with self.assertRaises(OSError):
            self.tick("90",1010)
        self.assertEqual(self.ledger.get_balance("USDT").total,D(0))
        self.assertEqual(self.ledger.get_balance("TMN").free,D("989.385135"))
        self.assertEqual(self.ledger.get_meta("audit_failed"),"1")
        recovered=Ledger(self.path,audit=MagicMock())
        recovered.flush_audit()
        self.assertIsNone(recovered.get_meta("audit_failed"))
        with recovered.connection() as db:
            self.assertEqual(db.execute("select count(*) from audit_outbox where delivered=0").fetchone()[0],0)

    def test_shared_account_lock_excludes_different_database_paths(self):
        other=Ledger(Path(self.temp.name)/"other.sqlite3")
        args=dict(account_fingerprint="b"*64,lock_directory=Path(self.temp.name)/"locks")
        with self.ledger.worker(**args),self.assertRaises(sqlite3.OperationalError),other.worker(**args):
            self.fail("second account worker entered")


if __name__=="__main__":
    unittest.main()
