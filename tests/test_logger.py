import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from pydantic import SecretStr

from royin.logger import AuditLogger, _sanitize_for_json, redact_secrets


class LoggerTests(unittest.TestCase):
    def test_nested_free_text_pipe_url_exception_and_token_counts(self):
        secret = "12345|synthetic-only-suffix"
        payload = {
            "reason": "api_key=" + secret,
            "nested": [
                SecretStr("synthetic-hidden"),
                {
                    "message": "Bearer synthetic-bearer-value",
                    "url": "https://example.test/?api_key=" + secret,
                },
            ],
            "exception": ValueError(secret),
            "input_tokens": 123,
            "api_key": secret,
        }
        result = _sanitize_for_json(payload)
        encoded = json.dumps(result)
        for value in (secret, "synthetic-hidden", "synthetic-bearer-value", "example.test"):
            self.assertNotIn(value, encoded)
        self.assertEqual(result["input_tokens"], 123)

    def test_event_ids_link_intent_to_later_fill_and_unknown_payload_is_dropped(self):
        with tempfile.TemporaryDirectory() as tmp, AuditLogger(Path(tmp), False) as log:
            log.context = {"decision_id": "d1", "snapshot_sha256": "a" * 64}
            log.record_event(
                "INTENT", "LEDGER", {"client_id": "o1", "raw_response": "untrusted-raw"}
            )
            log.context = {"decision_id": "d2"}
            log.record_event("FILL", "LEDGER", {"client_id": "o1", "fill_id": "f1"})
            events = [json.loads(s) for s in log.audit_path.read_text().splitlines()]
            self.assertEqual(events[1]["context"]["decision_id"], "d1")
            self.assertEqual(events[1]["sequence"], 2)
            self.assertNotIn("raw_response", events[0]["payload"])

    def test_audit_write_failure_propagates(self):
        with tempfile.TemporaryDirectory() as tmp, AuditLogger(Path(tmp), False) as log:
            log.audit_path = Path(tmp)  # opening a directory must fail closed
            with self.assertRaises(OSError):
                log.record_event("INTENT", "LEDGER", {"client_id": "o"})

    def test_redact_secrets_masks_api_keys_and_tokens(self):
        text = "api_key: secret-key-998877665544 and authorization: Bearer tok-1234567890abcdef"
        redacted = redact_secrets(text)
        self.assertNotIn("secret-key-998877665544", redacted)
        self.assertNotIn("tok-1234567890abcdef", redacted)
        self.assertIn("[REDACTED]", redacted)

    def test_audit_logger_records_structured_event_to_jsonl(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            with AuditLogger(log_dir=log_dir, enable_console=False) as logger:
                payload = {
                    "decision_id": "dec_123",
                    "price": Decimal("60000"),
                    "status": "APPROVED",
                    "api_key": "super-secret-key-value-123",
                }
                logger.record_event("TEST_EVENT", "EVAL", payload)

                audit_file = log_dir / "audit_trail.jsonl"
                self.assertTrue(audit_file.exists())

                lines = audit_file.read_text(encoding="utf-8").strip().splitlines()
                self.assertEqual(len(lines), 1)

                entry = json.loads(lines[0])
                self.assertEqual(entry["event_type"], "TEST_EVENT")
                self.assertEqual(entry["component"], "EVAL")
                self.assertEqual(entry["payload"]["decision_id"], "dec_123")
                self.assertEqual(entry["payload"]["price"], "60000")
                # Must redact the secret key
                self.assertNotIn("super-secret-key-value-123", lines[0])


if __name__ == "__main__":
    unittest.main()
