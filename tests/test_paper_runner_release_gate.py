import contextlib
import io
import unittest
from unittest.mock import patch

from scripts.run_paper_trader import main


class PaperRunnerReleaseGateTests(unittest.TestCase):
    def test_default_and_scan_block_before_io_or_manifest(self):
        for args in ([], ["--scan"], ["--symbol", "DOGETMN", "--db-path", "data/existing.sqlite3"]):
            with (
                self.subTest(args=args),
                patch("scripts.run_paper_trader.fetch_wallex_candles") as fetch,
                patch("scripts.run_paper_trader.scan_best_market") as scan,
                patch("scripts.run_paper_trader.run_paper_session") as session,
                patch("scripts.run_paper_trader.save_manifest") as save,
                contextlib.redirect_stdout(io.StringIO()) as output,
            ):
                self.assertEqual(main(args), 2)
                self.assertIn("BLOCKED_UNREVIEWED_REPLAY", output.getvalue())
                for call in (fetch, scan, session, save):
                    call.assert_not_called()

    def test_help_remains_available_without_execution(self):
        with (
            contextlib.redirect_stdout(io.StringIO()) as output,
            self.assertRaises(SystemExit) as result,
        ):
            main(["--help"])
        self.assertEqual(result.exception.code, 0)
        self.assertIn("--scan", output.getvalue())
