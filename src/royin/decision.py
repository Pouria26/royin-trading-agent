"""Contract for AI decisions bound to deterministic host snapshots."""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DecisionProposal(BaseModel):
    """Provisional decision proposed by the model or strategy logic."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    action: Literal["WAIT", "ENTER", "EXIT"]
    evidence_ids: tuple[str, ...]
    reason: str
    invalidation: str

    @field_validator("evidence_ids", mode="before")
    @classmethod
    def normalize_evidence_ids(cls, value):
        if isinstance(value, (list, tuple, set, frozenset)):
            items = tuple(str(x).strip() for x in value)
        else:
            raise ValueError("evidence_ids must be a collection of strings")
        if not items:
            raise ValueError("evidence_ids cannot be empty; every action must cite evidence")
        if any(not item for item in items):
            raise ValueError("evidence_id cannot be blank")
        if len(set(items)) != len(items):
            raise ValueError("duplicate evidence_ids are not allowed")
        return items

    @field_validator("reason", "invalidation", mode="before")
    @classmethod
    def nonempty_text(cls, value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Text fields must be non-empty strings")
        return value.strip()


class Decision(BaseModel):
    """Host-verified decision immutable data model."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    decision_id: str = Field(min_length=1)
    symbol: str
    action: Literal["WAIT", "ENTER", "EXIT"]
    cutoff: int
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_ids: tuple[str, ...]
    reason: str
    invalidation: str

    @field_validator("decision_id", "symbol", mode="before")
    @classmethod
    def clean_identifier(cls, value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Identifier must be a non-empty string")
        stripped = value.strip()
        if any(ord(c) < 32 or ord(c) == 127 for c in stripped):
            raise ValueError("Control characters are forbidden in identifiers")
        return stripped

    @field_validator("symbol")
    @classmethod
    def valid_symbol_pattern(cls, value):
        if not re.fullmatch(r"^[A-Z0-9]+(?:TMN|USDT)$", value):
            raise ValueError("Symbol must match canonical exchange pair format")
        return value

    @field_validator("cutoff", mode="before")
    @classmethod
    def integer_cutoff(cls, value):
        if type(value) is not int or isinstance(value, bool) or value < 0:
            raise ValueError("Cutoff must be a non-negative integer UNIX timestamp")
        return value

    @field_validator("evidence_ids", mode="before")
    @classmethod
    def normalize_evidence_ids(cls, value):
        if isinstance(value, (list, tuple, set, frozenset)):
            items = tuple(str(x).strip() for x in value)
        else:
            raise ValueError("evidence_ids must be a collection of strings")
        if not items:
            raise ValueError("evidence_ids cannot be empty")
        if any(not item for item in items):
            raise ValueError("evidence_id cannot be blank")
        if len(set(items)) != len(items):
            raise ValueError("duplicate evidence_ids are not allowed")
        return items

    @field_validator("reason", "invalidation", mode="before")
    @classmethod
    def nonempty_text(cls, value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Text fields must be non-empty strings")
        return value.strip()


def bind_decision(
    proposal: DecisionProposal,
    *,
    decision_id: str,
    symbol: str,
    cutoff: int,
    snapshot_sha256: str,
    available_evidence_ids: tuple[str, ...] | set[str] | frozenset[str],
    allowed_symbols: tuple[str, ...] | set[str] | frozenset[str] | None = None,
) -> Decision:
    """Bind a proposed decision to verified host metadata and validate evidence resolution."""
    if allowed_symbols is not None and symbol not in allowed_symbols:
        raise ValueError(f"Symbol '{symbol}' is not in the allowed universe")

    available = frozenset(available_evidence_ids)
    for eid in proposal.evidence_ids:
        if eid not in available:
            raise ValueError(f"Unresolvable or fabricated evidence_id: '{eid}'")

    return Decision(
        decision_id=decision_id,
        symbol=symbol,
        action=proposal.action,
        cutoff=cutoff,
        snapshot_sha256=snapshot_sha256,
        evidence_ids=proposal.evidence_ids,
        reason=proposal.reason,
        invalidation=proposal.invalidation,
    )
