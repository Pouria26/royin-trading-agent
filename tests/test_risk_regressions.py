import unittest
from decimal import Decimal

from royin.decision import Decision
from royin.ledger import Ledger
from royin.risk import MarketRules, RiskPolicy, evaluate_risk


class RiskRegressionTests(unittest.TestCase):
    def setUp(self):
        self.ledger = Ledger(":memory:")
        self.ledger.set_balance("TMN", free=Decimal("5000000"))
        self.rules = MarketRules(
            symbol="USDTTMN",
            base_asset="USDT",
            quote_asset="TMN",
            tick_size=Decimal("1"),
            step_size=Decimal("0.01"),
            min_notional=Decimal("100000"),
            min_quantity=Decimal("1.0"),
            maker_fee_rate=Decimal("0.001"),
            taker_fee_rate=Decimal("0.002"),
        )
        self.policy = RiskPolicy(
            max_order_tmn=Decimal("1500000"),
            max_exposure_tmn=Decimal("3000000"),
            stop_loss_pct=Decimal("0.02"),
            max_drawdown_pct=Decimal("0.05"),
            deadline_utc=1700010000,
        )
        self.snapshot_hash = "b" * 64
        self.denied = frozenset({"PAXGTMN"})

    def test_repro_cross_symbol_mismatch_is_rejected(self):
        """Decision for BTCTMN must be rejected by USDTTMN risk gate even if hash matches."""
        dec = Decision(
            decision_id="dec_cross",
            symbol="BTCTMN",  # mismatch!
            action="ENTER",
            cutoff=1700000000,
            snapshot_sha256=self.snapshot_hash,
            evidence_ids=("ev1",),
            reason="Bullish crossover",
            invalidation="None",
        )
        res = evaluate_risk(
            dec,
            market_rules=self.rules,
            policy=self.policy,
            ledger=self.ledger,
            current_time=1700000100,
            snapshot_sha256=self.snapshot_hash,
            candle_close_time=1700000000,
            current_price=Decimal("60000"),
            denied_markets=self.denied,
        )
        self.assertFalse(res.approved)
        self.assertIn("does not match", res.reason)

    def test_repro_future_timestamp_rejected(self):
        """Current time in the past relative to candle close (negative latency) must be rejected."""
        dec = Decision(
            decision_id="dec_future",
            symbol="USDTTMN",
            action="ENTER",
            cutoff=1700001000,
            snapshot_sha256=self.snapshot_hash,
            evidence_ids=("ev1",),
            reason="Bullish crossover",
            invalidation="None",
        )
        res = evaluate_risk(
            dec,
            market_rules=self.rules,
            policy=self.policy,
            ledger=self.ledger,
            current_time=1700000500,  # current_time < candle_close_time (1700001000)!
            snapshot_sha256=self.snapshot_hash,
            candle_close_time=1700001000,
            current_price=Decimal("60000"),
            denied_markets=self.denied,
        )
        self.assertFalse(res.approved)
        self.assertIn("Future or negative latency", res.reason)

    def test_peak_equity_and_drawdown_persists_across_ledger_restart(self):
        """Peak equity saved in ledger metadata enforces kill-switch even after broker restart."""
        # Record initial peak equity of 10,000,000 TMN
        self.ledger.set_meta("peak_equity_TMN", "10000000")
        # Current equity is 5,000,000 TMN -> 50% drawdown, well above 5% max_drawdown_pct!
        dec = Decision(
            decision_id="dec_dd",
            symbol="USDTTMN",
            action="ENTER",
            cutoff=1700000000,
            snapshot_sha256=self.snapshot_hash,
            evidence_ids=("ev1",),
            reason="Bullish",
            invalidation="None",
        )
        res = evaluate_risk(
            dec,
            market_rules=self.rules,
            policy=self.policy,
            ledger=self.ledger,
            current_time=1700000030,
            snapshot_sha256=self.snapshot_hash,
            candle_close_time=1700000000,
            current_price=Decimal("60000"),
            denied_markets=self.denied,
            peak_equity=None,  # should auto-load from ledger metadata!
        )
        self.assertFalse(res.approved)
        self.assertIn("drawdown", res.reason.lower())


if __name__ == "__main__":
    unittest.main()
