import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from royin.logger import AuditLogger, redact_secrets


class LoggerTests(unittest.TestCase):
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
