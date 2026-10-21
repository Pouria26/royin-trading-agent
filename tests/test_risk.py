import unittest
from decimal import Decimal

from royin.decision import Decision
from royin.ledger import Ledger
from royin.risk import MarketRules, RiskPolicy, evaluate_risk


class RiskGateTests(unittest.TestCase):
    def setUp(self):
        self.ledger = Ledger(":memory:")
        self.ledger.set_balance("TMN", free=Decimal("5000000"))

        self.rules = MarketRules(
            symbol="USDTTMN",
            base_asset="USDT",
            quote_asset="TMN",
            tick_size=Decimal("1"),
            step_size=Decimal("0.01"),
            min_notional=Decimal("100000"),  # 100,000 TMN
            min_quantity=Decimal("1.0"),     # 1 USDT
            maker_fee_rate=Decimal("0.001"), # 0.1%
            taker_fee_rate=Decimal("0.002"), # 0.2%
        )

        self.policy = RiskPolicy(
            max_order_tmn=Decimal("1500000"),
            max_exposure_tmn=Decimal("4000000"),
            stop_loss_pct=Decimal("0.03"),
            max_drawdown_pct=Decimal("0.10"),
            deadline_utc=1792788600,
            min_seconds_before_deadline=3600,
            max_stale_seconds=1800,
        )

        self.current_time = 1790813000
        self.candle_close = 1790812800
        self.valid_hash = "f" * 64
        self.denied = frozenset({"PAXGTMN", "OPUSDT", "PAXG/TMN", "PAXG/USDT"})

    def _make_decision(self, action="ENTER", symbol="USDTTMN"):
        return Decision(
            decision_id="dec_test",
            symbol=symbol,
            action=action,
            cutoff=self.candle_close,
            snapshot_sha256=self.valid_hash,
            evidence_ids=("EV_TEST_1",),
            reason="Test signal",
            invalidation="Test invalidation",
        )

    def test_approved_enter(self):
        decision = self._make_decision("ENTER")
        res = evaluate_risk(
            decision,
            market_rules=self.rules,
            policy=self.policy,
            ledger=self.ledger,
            current_time=self.current_time,
            snapshot_sha256=self.valid_hash,
            candle_close_time=self.candle_close,
            current_price=Decimal("60000"),
            denied_markets=self.denied,
        )
        self.assertTrue(res.approved)
        self.assertEqual(res.action, "ENTER")
        self.assertEqual(res.price, Decimal("60000"))
        # Budget 1,500,000 TMN / (60000 * 1.002) = 24.950099... quantized down to 24.95 USDT
        self.assertEqual(res.quantity, Decimal("24.95"))
        # Stop loss 3% below 60000 = 58200
        self.assertEqual(res.stop_price, Decimal("58200"))

    def test_rejected_denied_market(self):
        paxg_rules = MarketRules(
            symbol="PAXGTMN",
            base_asset="PAXG",
            quote_asset="TMN",
            tick_size=Decimal("100"),
            step_size=Decimal("0.0001"),
            min_notional=Decimal("100000"),
            min_quantity=Decimal("0.0001"),
            maker_fee_rate=Decimal("0.001"),
            taker_fee_rate=Decimal("0.002"),
        )
        decision = self._make_decision("ENTER", symbol="PAXGTMN")
        res = evaluate_risk(
            decision,
            market_rules=paxg_rules,
            policy=self.policy,
            ledger=self.ledger,
            current_time=self.current_time,
            snapshot_sha256=self.valid_hash,
            candle_close_time=self.candle_close,
            current_price=Decimal("300000000"),
            denied_markets=self.denied,
        )
        self.assertFalse(res.approved)
        self.assertIn("denied by policy", res.reason.lower())

    def test_rejected_snapshot_mismatch(self):
        decision = self._make_decision("ENTER")
        res = evaluate_risk(
            decision,
            market_rules=self.rules,
            policy=self.policy,
            ledger=self.ledger,
            current_time=self.current_time,
            snapshot_sha256="0" * 64,  # Mismatched hash
            candle_close_time=self.candle_close,
            current_price=Decimal("60000"),
            denied_markets=self.denied,
        )
        self.assertFalse(res.approved)
        self.assertIn("hash mismatch", res.reason.lower())

    def test_rejected_stale_data_on_enter(self):
        decision = self._make_decision("ENTER")
        # Candle closed 2000s ago (> 1800s max_stale)
        res = evaluate_risk(
            decision,
            market_rules=self.rules,
            policy=self.policy,
            ledger=self.ledger,
            current_time=self.candle_close + 2000,
            snapshot_sha256=self.valid_hash,
            candle_close_time=self.candle_close,
            current_price=Decimal("60000"),
            denied_markets=self.denied,
        )
        self.assertFalse(res.approved)
        self.assertIn("stale", res.reason.lower())

    def test_rejected_deadline_approaching(self):
        candle_close = self.policy.deadline_utc - 1900
        decision = Decision(
            decision_id="dec_dl",
            symbol="USDTTMN",
            action="ENTER",
            cutoff=candle_close,
            snapshot_sha256=self.valid_hash,
            evidence_ids=("EV_TEST_1",),
            reason="Test signal",
            invalidation="Test invalidation",
        )
        # 30 minutes before deadline (< 3600s buffer)
        res = evaluate_risk(
            decision,
            market_rules=self.rules,
            policy=self.policy,
            ledger=self.ledger,
            current_time=self.policy.deadline_utc - 1800,
            snapshot_sha256=self.valid_hash,
            candle_close_time=candle_close,
            current_price=Decimal("60000"),
            denied_markets=self.denied,
        )
        self.assertFalse(res.approved)
        self.assertIn("deadline", res.reason.lower())

    def test_rejected_drawdown_kill_switch(self):
        decision = self._make_decision("ENTER")
        # Equity is 5M, peak was 6M -> drawdown is 16.6% (> 10% limit)
        res = evaluate_risk(
            decision,
            market_rules=self.rules,
            policy=self.policy,
            ledger=self.ledger,
            current_time=self.current_time,
            snapshot_sha256=self.valid_hash,
            candle_close_time=self.candle_close,
            current_price=Decimal("60000"),
            denied_markets=self.denied,
            peak_equity=Decimal("6000000"),
        )
        self.assertFalse(res.approved)
        self.assertIn("drawdown", res.reason.lower())

    def test_sell_without_balance_fails_closed(self):
        # Ledger has 0 USDT
        decision = self._make_decision("EXIT")
        res = evaluate_risk(
            decision,
            market_rules=self.rules,
            policy=self.policy,
            ledger=self.ledger,
            current_time=self.current_time,
            snapshot_sha256=self.valid_hash,
            candle_close_time=self.candle_close,
            current_price=Decimal("60000"),
            denied_markets=self.denied,
        )
        self.assertFalse(res.approved)
        self.assertIn("0 available base balance", res.reason)

    def test_approved_exit_with_balance(self):
        self.ledger.set_balance("USDT", free=Decimal("20.0"))
        decision = self._make_decision("EXIT")
        res = evaluate_risk(
            decision,
            market_rules=self.rules,
            policy=self.policy,
            ledger=self.ledger,
            current_time=self.current_time,
            snapshot_sha256=self.valid_hash,
            candle_close_time=self.candle_close,
            current_price=Decimal("62000"),
            denied_markets=self.denied,
        )
        self.assertTrue(res.approved)
        self.assertEqual(res.action, "EXIT")
        self.assertEqual(res.quantity, Decimal("20.0"))
        self.assertEqual(res.price, Decimal("62000"))


if __name__ == "__main__":
    unittest.main()
