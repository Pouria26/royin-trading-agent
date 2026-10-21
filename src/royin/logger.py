"""Structured, redacted logging for auditability and real-time observability.

Ensures zero leakage of secrets, authorization tokens, or private credentials
while providing clean human-readable console output and machine-readable JSONL audit logs.
"""

import json
import logging
import re
import sys
import time
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

# Default log file locations
DEFAULT_LOG_DIR = Path("data/logs")
AUDIT_LOG_FILE = DEFAULT_LOG_DIR / "audit_trail.jsonl"
APP_LOG_FILE = DEFAULT_LOG_DIR / "trading_agent.log"

# Regex patterns for sensitive keys and tokens in plain text
_SECRET_PATTERNS = [
    re.compile(r'((?:api[_-]?key|secret|token|authorization|password)\s*[:=]\s*["\']?)[a-zA-Z0-9_\-\.]{8,}(["\']?)', re.IGNORECASE),
    re.compile(r'(Bearer\s+)[a-zA-Z0-9_\-\.]{10,}', re.IGNORECASE),
]


def redact_secrets(text: str) -> str:
    """Mask any discovered API keys or tokens with redaction placeholders."""
    if not isinstance(text, str):
        return text
    redacted = text
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(
            lambda m: f"{m.group(1)}[REDACTED]{m.group(2) if len(m.groups()) >= 2 and m.group(2) else ''}",
            redacted,
        )
    return redacted


def _sanitize_for_json(obj: Any) -> Any:
    """Convert Decimals and complex objects to JSON-serializable primitives while redacting sensitive fields."""
    if isinstance(obj, Decimal):
        return str(obj)
    if is_dataclass(obj) and not isinstance(obj, type):
        return _sanitize_for_json(asdict(obj))
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(x) for x in obj]
    if isinstance(obj, dict):
        clean = {}
        for k, v in obj.items():
            k_str = str(k)
            if any(s in k_str.lower() for s in ("key", "secret", "token", "auth", "password")):
                clean[k_str] = "[REDACTED]"
            else:
                clean[k_str] = _sanitize_for_json(v)
        return clean
    return obj


class AuditLogger:
    """Central audit and structured logging system."""

    def __init__(self, log_dir: Path | None = None, enable_console: bool = True):
        self.log_dir = log_dir or DEFAULT_LOG_DIR
        self.enable_console = enable_console
        self.audit_path = self.log_dir / "audit_trail.jsonl"
        self.app_path = self.log_dir / "trading_agent.log"

        self.log_dir.mkdir(parents=True, exist_ok=True)

        self._py_logger = logging.getLogger(f"royin.{id(self)}")
        self._py_logger.setLevel(logging.INFO)
        self._py_logger.handlers.clear()

        # Console handler with clean formatting
        if self.enable_console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.INFO)
            formatter = logging.Formatter(
                "%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            console_handler.setFormatter(formatter)
            self._py_logger.addHandler(console_handler)

        # File handler for plain text logs
        self._file_handler = logging.FileHandler(self.app_path, encoding="utf-8")
        self._file_handler.setLevel(logging.INFO)
        self._file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] [%(name)s] %(message)s"))
        self._py_logger.addHandler(self._file_handler)

    def close(self):
        """Close handlers to release file locks (especially on Windows)."""
        for handler in list(self._py_logger.handlers):
            handler.close()
            self._py_logger.removeHandler(handler)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def log(self, level: int, component: str, message: str, **kwargs):
        """Standard human-readable log with component prefix and secret masking."""
        safe_msg = redact_secrets(f"[{component}] {message}")
        if kwargs:
            clean_kwargs = {k: redact_secrets(str(v)) for k, v in kwargs.items()}
            safe_msg += f" | {clean_kwargs}"
        self._py_logger.log(level, safe_msg)

    def info(self, component: str, message: str, **kwargs):
        self.log(logging.INFO, component, message, **kwargs)

    def warning(self, component: str, message: str, **kwargs):
        self.log(logging.WARNING, component, message, **kwargs)

    def error(self, component: str, message: str, **kwargs):
        self.log(logging.ERROR, component, message, **kwargs)

    def record_event(self, event_type: str, component: str, payload: dict[str, Any]):
        """Write an immutable structured event to the JSONL audit trail."""
        timestamp = time.time()
        record = {
            "timestamp": timestamp,
            "event_type": event_type,
            "component": component,
            "payload": _sanitize_for_json(payload),
        }
        safe_json = json.dumps(record, sort_keys=True)

        # Write safely to JSONL
        with open(self.audit_path, "a", encoding="utf-8") as f:
            f.write(safe_json + "\n")

        # Also emit a concise human log
        summary = f"{event_type}: " + ", ".join(f"{k}={v}" for k, v in list(record["payload"].items())[:4])
        self.info(component, summary)


# Global singleton instance for easy import
_GLOBAL_AUDIT_LOGGER: AuditLogger | None = None


def get_audit_logger(log_dir: Path | None = None) -> AuditLogger:
    global _GLOBAL_AUDIT_LOGGER
    if _GLOBAL_AUDIT_LOGGER is None:
        _GLOBAL_AUDIT_LOGGER = AuditLogger(log_dir=log_dir)
    return _GLOBAL_AUDIT_LOGGER
