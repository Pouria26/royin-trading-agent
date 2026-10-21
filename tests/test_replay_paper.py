import unittest
from decimal import Decimal

from scripts.replay_paper import build_fixture_dataset, run_replay


class ReplayPaperTests(unittest.TestCase):
    def test_deterministic_paper_replay_produces_identical_manifest_hash(self):
        candles, decisions, snapshot_hash = build_fixture_dataset()

        # Run 1
        m1 = run_replay(candles, decisions, snapshot_hash, initial_capital=Decimal("5000000"))
        # Run 2
        m2 = run_replay(candles, decisions, snapshot_hash, initial_capital=Decimal("5000000"))

        self.assertEqual(m1["status"], "PASS_REPLAY_DETERMINISTIC")
        self.assertEqual(m2["status"], "PASS_REPLAY_DETERMINISTIC")
        self.assertEqual(m1["manifest_sha256"], m2["manifest_sha256"])
        self.assertEqual(m1["final_cash_tmn"], m2["final_cash_tmn"])
        self.assertEqual(m1["total_realized_pnl"], m2["total_realized_pnl"])
        self.assertEqual(m1["fills_count"], 2)
        self.assertEqual(m1["residual_dust_base"], "0.00")

    def test_replay_with_all_wait_decisions_preserves_capital_exactly(self):
        candles, decisions, snapshot_hash = build_fixture_dataset()
        # Change all decisions to WAIT
        wait_decisions = [
            d.model_copy(update={"action": "WAIT", "reason": "Always wait"})
            for d in decisions
        ]

        manifest = run_replay(candles, wait_decisions, snapshot_hash, initial_capital=Decimal("5000000"))
        self.assertEqual(manifest["status"], "PASS_REPLAY_DETERMINISTIC")
        self.assertEqual(manifest["orders_submitted"], 0)
        self.assertEqual(manifest["fills_count"], 0)
        self.assertEqual(manifest["final_cash_tmn"], "5000000")
        self.assertEqual(manifest["total_realized_pnl"], "0")


if __name__ == "__main__":
    unittest.main()
