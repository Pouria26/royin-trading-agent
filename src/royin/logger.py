"""Structured, redacted logging for auditability and real-time observability.

Uses payload allowlists and best-effort secret redaction; no universal masking guarantee
while providing clean human-readable console output and machine-readable JSONL audit logs.
"""

import json
import logging
import os
import re
import sys
import time
import uuid
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import SecretStr

# Default log file locations
DEFAULT_LOG_DIR = Path("data/logs")
AUDIT_LOG_FILE = DEFAULT_LOG_DIR / "audit_trail.jsonl"
APP_LOG_FILE = DEFAULT_LOG_DIR / "trading_agent.log"

# Regex patterns for sensitive keys and tokens in plain text
_SECRET_PATTERNS = [
    re.compile(
        r"((?:x-)?(?:api[_-]?key|secret|token|authorization|password)\s*[:=]\s*[\"']?)(?:Bearer\s+)?[^\s\"'&,}]+",
        re.IGNORECASE,
    ),
    re.compile(r"(Bearer\s+)[^\s\"'&,}]+", re.IGNORECASE),
    re.compile(r"(\b)\d+\|[A-Za-z0-9_.-]+"),
    re.compile(r"(https?://)[^\s\"']+", re.IGNORECASE),
]

_SECRET_KEYS = {
    "key",
    "api_key",
    "apikey",
    "x-api-key",
    "secret",
    "token",
    "authorization",
    "password",
    "headers",
    "query",
    "url",
    "api-key",
    "access_token",
    "refresh_token",
}
_PAYLOAD_FIELDS = frozenset(
    [
        "journal_event_id",
        "decision_id",
        "snapshot_sha256",
        "symbol",
        "cutoff",
        "action",
        "reason",
        "source",
        "status",
        "price",
        "quantity",
        "stop_price",
        "client_id",
        "fill_id",
        "fee",
        "fee_asset",
        "timestamp",
        "side",
        "order_type",
        "snapshot",
        "evidence_ids",
        "approved",
        "current_position_base",
        "available_tmn_cash",
        "initial_capital_tmn",
        "final_tmn_cash",
        "final_equity_mtm_tmn",
        "residual_dust_base",
        "total_realized_pnl",
        "net_return_pct",
        "liquidated_base_quantity",
        "liquidation_cash_received",
        "error_type",
        "event_time",
        "data_sha256",
        "interval_seconds",
        "count",
        "balance",
        "free",
        "locked",
        "reserved_input_tokens",
        "reserved_output_tokens",
        "reserved_cost_usd",
        "provider_reported_usage",
        "cost_estimate_usd",
        "input_tokens",
        "output_tokens",
        "requests",
        "usage",
        "model",
        "policy_sha256",
        "realized_pnl_tmn",
        "residual_basis_tmn",
        "phase",
        "invalidation",
        "wall_seconds",
    ]
)


def redact_secrets(text: str) -> str:
    """Mask any discovered API keys or tokens with redaction placeholders."""
    if not isinstance(text, str):
        return text
    redacted = text
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(
            lambda m: f"{m.group(1)}[REDACTED]",
            redacted,
        )
    return redacted


def _sanitize_for_json(obj: Any) -> Any:
    """Convert Decimals and complex objects to JSON-serializable primitives while redacting sensitive fields."""
    if isinstance(obj, SecretStr):
        return "[REDACTED]"
    if isinstance(obj, BaseException):
        return type(obj).__name__
    if isinstance(obj, str):
        return redact_secrets(obj)
    if isinstance(obj, Decimal):
        return str(obj)
    if is_dataclass(obj) and not isinstance(obj, type):
        return _sanitize_for_json(asdict(obj))
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(x) for x in obj]
    if isinstance(obj, dict):
        clean = {}
        for k, v in obj.items():
            k_str = redact_secrets(str(k))
            if k_str.lower() in _SECRET_KEYS or k_str.lower().endswith(
                ("_api_key", "_secret", "_password")
            ):
                clean[k_str] = "[REDACTED]"
            else:
                clean[k_str] = _sanitize_for_json(v)
        return clean
    return obj if obj is None or type(obj) in (int, float, bool) else "[UNSUPPORTED]"


class AuditLogger:
    """Central audit and structured logging system."""

    def __init__(
        self,
        log_dir: Path | None = None,
        enable_console: bool = True,
        *,
        run_id=None,
        mode="historical",
        source="PAPER",
        hashes=None,
    ):
        self.run_id = run_id or uuid.uuid4().hex
        self.mode, self.source = mode, source
        self.sequence = 0
        self.context = {}
        self.order_contexts = {}
        self.hashes = hashes or {k: None for k in ("code", "config", "prompt", "model", "data")}
        self.log_dir = log_dir or DEFAULT_LOG_DIR / self.run_id
        self.enable_console = enable_console
        self.audit_path = self.log_dir / "audit_trail.jsonl"
        self.app_path = self.log_dir / "trading_agent.log"

        self.log_dir.mkdir(parents=True, exist_ok=True)

        self._py_logger = logging.getLogger(f"royin.{id(self)}")
        self._py_logger.setLevel(logging.INFO)
        self._py_logger.propagate = False
        for handler in list(self._py_logger.handlers):
            handler.close()
            self._py_logger.removeHandler(handler)

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
        self._file_handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] [%(name)s] %(message)s")
        )
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
            clean_kwargs = _sanitize_for_json(
                {
                    k: v
                    for k, v in kwargs.items()
                    if k in _PAYLOAD_FIELDS or k.lower() in _SECRET_KEYS
                }
            )
            safe_msg += f" | {clean_kwargs}"
        self._py_logger.log(level, safe_msg)

    def info(self, component: str, message: str, **kwargs):
        self.log(logging.INFO, component, message, **kwargs)

    def warning(self, component: str, message: str, **kwargs):
        self.log(logging.WARNING, component, message, **kwargs)

    def error(self, component: str, message: str, **kwargs):
        self.log(logging.ERROR, component, message, **kwargs)

    def record_event(self, event_type: str, component: str, payload: dict[str, Any], *, origin=None):
        """Write an immutable structured event to the JSONL audit trail."""
        journal_origin=origin
        timestamp = time.time()
        self.sequence += 1
        occurred = payload.get(
            "event_time",
            payload.get("timestamp", payload.get("cutoff", self.context.get("cutoff", timestamp))),
        )
        safe_payload = {k: v for k, v in payload.items() if k in _PAYLOAD_FIELDS}
        cid = payload.get("client_id")
        if event_type == "INTENT" and cid:
            self.order_contexts[cid] = dict(self.context)
        origin = self.order_contexts.get(cid, self.context)
        context = {k: v for k, v in origin.items() if k in _PAYLOAD_FIELDS}
        record = {
            "schema_version": 1,
            "run_id": self.run_id,
            "mode": self.mode,
            "source": payload.get("source")
            if payload.get("source") in ("REAL_MODEL", "SYNTHETIC", "PAPER", "SHADOW")
            else self.source,
            "sequence": self.sequence,
            "event_id": payload.get("journal_event_id", f"{self.run_id}:{self.sequence}"),
            "occurred_at": datetime.fromtimestamp(occurred, UTC).isoformat(),
            "recorded_at": datetime.fromtimestamp(timestamp, UTC).isoformat(),
            "hashes": self.hashes,
            "context": _sanitize_for_json(context),
            "timestamp": timestamp,
            "event_type": event_type,
            "component": component,
            "payload": _sanitize_for_json(safe_payload),
        }
        if journal_origin:
            record.update({key:journal_origin[key] for key in ("run_id","mode","source","hashes","context")})
        safe_json = json.dumps(record, sort_keys=True)

        # Write safely to JSONL
        with open(self.audit_path, "a", encoding="utf-8") as f:
            f.write(safe_json + "\n")
            f.flush()
            os.fsync(f.fileno())

        # Also emit a concise human log
        summary = f"{event_type}: " + ", ".join(
            f"{k}={v}" for k, v in list(record["payload"].items())[:4]
        )
        self.info(component, summary)


# Global singleton instance for easy import
_GLOBAL_AUDIT_LOGGER: AuditLogger | None = None


def get_audit_logger(log_dir: Path | None = None) -> AuditLogger:
    global _GLOBAL_AUDIT_LOGGER
    if _GLOBAL_AUDIT_LOGGER is None:
        _GLOBAL_AUDIT_LOGGER = AuditLogger(log_dir=log_dir)
    return _GLOBAL_AUDIT_LOGGER
