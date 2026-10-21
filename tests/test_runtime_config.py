"""T01 safety boundary; no claim about market eligibility or trading quality."""

import contextlib
import io
import json
import os
import tempfile
import unittest
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from royin.__main__ import main
from royin.config import RuntimeConfig, load_config

ROOT = Path(__file__).resolve().parents[1]


class RuntimeConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / ".env"

    def load(self, text, environ=None):
        self.path.write_text(text, encoding="utf-8")
        return load_config(self.path, environ={} if environ is None else environ)

    def test_defaults_and_example_need_no_credentials(self):
        config = self.load("")
        self.assertEqual(config.RUN_MODE, "shadow")
        self.assertFalse(config.ENABLE_LIVE_TRADING)
        self.assertIsNone(config.WALLEX_API_KEY)
        example = load_config(ROOT / ".env.example", environ={})
        self.assertEqual(example.RUN_MODE, "shadow")
        self.assertEqual(example.CHALLENGE_END_AT, datetime(2026, 10, 23, 20, 20, tzinfo=UTC))

    def test_invalid_mode_flag_provider_and_origins_fail_closed(self):
        for text in (
            "RUN_MODE=shdaow", "RUN_MODE=", "ENABLE_LIVE_TRADING=yes",
            "ENABLE_LIVE_TRADING=1", "LLM_PROVIDER=other", "LLM_MODEL=",
            "WALLEX_BASE_URL=http://api.wallex.ir", "WALLEX_BASE_URL=https://example.com",
            "LLM_BASE_URL=https://example.com", "STATE_DB_PATH=", "ARTIFACTS_DIR=",
        ):
            with self.subTest(text=text), self.assertRaises(ValidationError):
                self.load(text)

    def test_live_stays_closed_with_or_without_claimed_prerequisites(self):
        claimed = (
            "WALLEX_API_KEY=synthetic-key\nSUB_ACCOUNT_CLIENT_ID=synthetic-account\n"
            "WALLEX_ALLOWED_MARKETS=BTCTMN\nCHALLENGE_END_AT=2026-10-23T23:50:00+03:30\n"
            "FINALIZE_START_AT=2026-10-23T23:00:00+03:30\n"
        )
        for mode in ("historical", "shadow", "live"):
            for enabled in ("true", "false"):
                if mode != "live" and enabled == "false":
                    continue
                for prerequisites in ("", claimed):
                    with (
                        self.subTest(mode=mode, enabled=enabled, prerequisites=bool(prerequisites)),
                        self.assertRaises(ValidationError),
                    ):
                        self.load(
                            f"RUN_MODE={mode}\nENABLE_LIVE_TRADING={enabled}\n" + prerequisites
                        )

    def test_unknown_file_and_scoped_process_keys_are_rejected(self):
        for text, environ in (
            ("RUN_MDOE=live", {}), ("LLM_TOKEN_BUDGETT=10", {}),
            ("", {"WALLEX_API_KE": "synthetic-key"}),
        ):
            with self.subTest(text=text), self.assertRaises(ValidationError):
                self.load(text, environ)

    def test_process_precedence_without_mutating_environment_or_interpolation(self):
        environment = {"RUN_MODE": "historical", "PATH": "ignored", "OTHER_SECRET": "ignored"}
        original = dict(environment)
        config = self.load("RUN_MODE=shadow\nGOOGLE_API_KEY='${OTHER_SECRET}'", environment)
        self.assertEqual(config.RUN_MODE, "historical")
        self.assertEqual(config.GOOGLE_API_KEY.get_secret_value(), "${OTHER_SECRET}")
        self.assertEqual(environment, original)

    def test_malformed_bare_or_duplicate_assignment_is_not_silently_ignored(self):
        for text in ("RUN_MODE='unclosed", "RUN_MODE", "RUN_MODE=live\nRUN_MODE=shadow"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.load(text)

    def test_missing_explicit_file_is_an_error(self):
        with self.assertRaises(FileNotFoundError):
            load_config(self.path, environ={})

    def test_deadline_requires_offset_and_finalization_precedes_end(self):
        for text in (
            "CHALLENGE_END_AT=2026-10-23T23:50:00",
            "CHALLENGE_END_AT=1792786800", "FINALIZE_START_AT=2026-10-23T23:00:00Z",
            "CHALLENGE_END_AT=2026-10-23T20:20:00Z\nFINALIZE_START_AT=2026-10-23T23:50:00+03:30",
            "CHALLENGE_END_AT=2026-10-23T20:20:00Z\nFINALIZE_START_AT=2026-10-23T20:21:00Z",
        ):
            with self.subTest(text=text), self.assertRaises(ValidationError):
                self.load(text)
        self.assertIsNotNone(self.load(
            "CHALLENGE_END_AT=2026-10-23T20:20:00Z\nFINALIZE_START_AT=2026-10-23T23:00:00+03:30"
        ).FINALIZE_START_AT)

    def test_budgets_are_explicit_finite_nonnegative_and_complete(self):
        template = "LLM_TOKEN_BUDGET={}\nLLM_COST_BUDGET={}\nLLM_COST_CURRENCY=USD"
        valid = self.load(template.format("100", "0.10"))
        self.assertEqual(valid.LLM_TOKEN_BUDGET, 100)
        self.assertEqual(valid.LLM_COST_BUDGET, Decimal("0.10"))
        for tokens, cost in (
            ("-1", "1"), ("1.5", "1"), ("1.0", "1"), ("1", "-0.1"),
            ("1", "NaN"), ("1", "Infinity"), ("1", ""), ("", "1"),
        ):
            with self.subTest(tokens=tokens, cost=cost), self.assertRaises(ValidationError):
                self.load(template.format(tokens, cost))
        with self.assertRaises(ValidationError):
            self.load("LLM_COST_BUDGET=1")
        for field, value in (("LLM_COST_BUDGET", 0.1), ("LLM_TOKEN_BUDGET", True)):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                RuntimeConfig.model_validate({field: value})

    def test_selection_preserves_symbols_but_grants_no_eligibility(self):
        selection = self.load("WALLEX_ALLOWED_MARKETS=BTCTMN, 1BBABYDOGEUSDT")
        self.assertEqual(selection.WALLEX_ALLOWED_MARKETS, ("BTCTMN", "1BBABYDOGEUSDT"))
        for symbols in ("BTC/TMN", "btctmn", "BTCTMN,", "BTCTMN,BTCTMN", "BTC"):
            with self.subTest(symbols=symbols), self.assertRaises(ValidationError):
                self.load("WALLEX_ALLOWED_MARKETS=" + symbols)

    def test_secrets_are_excluded_from_repr_and_serialization(self):
        secret = "synthetic-sensitive-value"
        config = self.load(
            f"WALLEX_API_KEY={secret}\nSUB_ACCOUNT_CLIENT_ID={secret}\nGOOGLE_API_KEY={secret}"
        )
        self.assertNotIn(secret, repr(config))
        self.assertNotIn(secret, config.model_dump_json())

    def test_cli_modes_never_connect_or_create_state_even_with_credentials(self):
        for mode in ("historical", "shadow"):
            self.path.write_text(
                f"RUN_MODE={mode}\nSTATE_DB_PATH={self.temp.name}/must-not-exist.sqlite3\n"
                "WALLEX_API_KEY=synthetic-sensitive-value\nGOOGLE_API_KEY=synthetic-sensitive-value",
                encoding="utf-8",
            )
            with (
                self.subTest(mode=mode), patch.dict(os.environ, {}, clear=True),
                patch("socket.socket.connect", side_effect=AssertionError("Unexpected network")),
                contextlib.redirect_stdout(io.StringIO()) as output,
            ):
                self.assertEqual(main(["check-config", "--env-file", str(self.path)]), 0)
            self.assertEqual(json.loads(output.getvalue()), {
                "status": "VALID_CONFIG_ONLY", "mode": mode,
                "network_enabled": False, "trading_enabled": False,
            })
            self.assertFalse((Path(self.temp.name) / "must-not-exist.sqlite3").exists())

    def test_cli_errors_do_not_echo_secrets_or_unknown_names(self):
        secret = "synthetic-sensitive-value"
        for text in (f"RUN_MODE={secret}", f"{secret}=x", f"WALLEX_API_KEY='{secret}"):
            self.path.write_text(text, encoding="utf-8")
            with (
                patch.dict(os.environ, {}, clear=True),
                contextlib.redirect_stdout(io.StringIO()) as output,
                contextlib.redirect_stderr(io.StringIO()) as errors,
            ):
                self.assertEqual(main(["check-config", "--env-file", str(self.path)]), 2)
            self.assertIn("BLOCKED", output.getvalue())
            self.assertNotIn(secret, output.getvalue() + errors.getvalue())


if __name__ == "__main__":
    unittest.main()
