import unittest

from scripts.shadow_cycle import run_shadow_4_cycles


class ShadowCycleTests(unittest.TestCase):
    def test_shadow_4_cycles_runs_and_triggers_host_stop_without_llm(self):
        rep = run_shadow_4_cycles()
        self.assertEqual(rep["cycles_completed"], 4)
        self.assertTrue(rep["host_stop_triggered_without_llm"])
        self.assertEqual(rep["symbol"], "USDTTMN")
        self.assertIn("final_cash_tmn", rep)
        self.assertEqual(len(rep["log"]), 4)


if __name__ == "__main__":
    unittest.main()
