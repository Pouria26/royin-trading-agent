import contextlib
import io
import os
import unittest
from unittest.mock import patch

from scripts.probe_model import main


class ModelProbeSafetyTests(unittest.TestCase):
    def test_missing_key_blocks_without_provider_request(self):
        with (
            patch("sys.argv", ["probe_model.py", "--run"]),
            patch.dict(os.environ, {"GOOGLE_API_KEY": ""}),
            patch("scripts.probe_model.load_dotenv"),
            patch("scripts.probe_model.probe") as model_probe,
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(main(), 2)
            self.assertIn("BLOCKED", output.getvalue())
            model_probe.assert_not_called()

    def test_no_explicit_run_does_not_read_credentials_or_call_model(self):
        with (
            patch("sys.argv", ["probe_model.py"]),
            patch("scripts.probe_model.load_dotenv") as load_credentials,
            patch("scripts.probe_model.probe") as model_probe,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(main(), 0)
            load_credentials.assert_not_called()
            model_probe.assert_not_called()
