import hashlib
import re
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from royin.market_data import decimal_number


class DecisionProposal(BaseModel):
    """Provisional decision proposed by the model or strategy logic."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    action: Literal["WAIT", "ENTER", "EXIT"]
    evidence_ids: tuple[str, ...]
    reason: str
    invalidation: str
    target_profit_pct: Decimal | None = None
    stop_loss_pct: Decimal | None = None
    exit_reason: str | None = None

    @field_validator("target_profit_pct", "stop_loss_pct", mode="before")
    @classmethod
    def exact_optional_fraction(cls, value):
        return None if value is None else decimal_number(value, positive=True)

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


class PositionReviewContext(BaseModel):
    """Read-only values supplied by execution owner B; no model-owned risk policy."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    quantity: Decimal
    cost_basis_tmn: Decimal
    net_liquidation_tmn: Decimal
    opened_at: int = Field(ge=0)
    observed_at: int = Field(ge=0)
    hard_exit_at: int = Field(ge=0)
    initial_stop_price: Decimal
    trailing_stop_price: Decimal
    checkpoint_profit_pct: Decimal

    @field_validator("quantity", "cost_basis_tmn", "initial_stop_price", "trailing_stop_price")
    @classmethod
    def positive_decimal(cls, value):
        return decimal_number(value, positive=True)

    @field_validator("net_liquidation_tmn", "checkpoint_profit_pct")
    @classmethod
    def nonnegative_decimal(cls, value):
        return decimal_number(value)

    @property
    def sha256(self):
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


class EntryOpportunityContext(BaseModel):
    """Fresh scanner cost/liquidity facts; never order sizing or account authorization."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    spread_pct: Decimal = Field(ge=0, lt=1, allow_inf_nan=False)
    round_trip_fee_pct: Decimal = Field(ge=0, lt=1, allow_inf_nan=False)
    bid_depth_tmn: Decimal = Field(gt=0, allow_inf_nan=False)
    ask_depth_tmn: Decimal = Field(gt=0, allow_inf_nan=False)
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    catalog_received_at: int = Field(ge=0)
    candle_received_at: int = Field(ge=0)
    depth_received_at: int = Field(ge=0)
    observed_at: int = Field(ge=0)

    @property
    def sha256(self):
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


class RoleDecisionProposal(DecisionProposal):
    role: Literal["ENTRY_ANALYST", "POSITION_REVIEWER"]
    cutoff: int = Field(strict=True, ge=0)
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    position_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    opportunity_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


def validate_role_proposal(proposal, *, role, snapshot, position, opportunity):
    """Reject cross-role/state output before the unchanged execution Decision boundary."""
    if not isinstance(proposal, RoleDecisionProposal) or (
        proposal.role != role or proposal.cutoff != snapshot.cutoff
        or proposal.snapshot_sha256 != snapshot.snapshot_sha256
        or proposal.position_sha256 != (position.sha256 if position else None)
        or proposal.opportunity_sha256 != (opportunity.sha256 if opportunity else None)
    ):
        raise ValueError("Role/cutoff/snapshot/position mismatch")
    allowed = {"WAIT", "ENTER"} if role == "ENTRY_ANALYST" else {"WAIT", "EXIT"}
    if proposal.action not in allowed or (
        proposal.target_profit_pct is not None or proposal.stop_loss_pct is not None
    ):
        raise ValueError("Role action or model-owned risk policy forbidden")


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
    target_profit_pct: Decimal | None = None
    stop_loss_pct: Decimal | None = None
    exit_reason: str | None = None

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

    target_profit = proposal.target_profit_pct
    stop_loss = proposal.stop_loss_pct
    if proposal.action == "ENTER":
        if target_profit is not None:
            # Safe corridor: minimum 1.2% (to beat 0.6% fee friction), capped at 3.5%
            target_profit = min(max(target_profit, Decimal("0.012")), Decimal("0.035"))
        if stop_loss is not None:
            # Safe corridor: floor 0.5% (avoid spread stopout), capped at 1.0% (strict capital protection)
            stop_loss = min(max(stop_loss, Decimal("0.005")), Decimal("0.010"))

    return Decision(
        decision_id=decision_id,
        symbol=symbol,
        action=proposal.action,
        cutoff=cutoff,
        snapshot_sha256=snapshot_sha256,
        evidence_ids=proposal.evidence_ids,
        reason=proposal.reason,
        invalidation=proposal.invalidation,
        target_profit_pct=target_profit,
        stop_loss_pct=stop_loss,
        exit_reason=proposal.exit_reason,
    )
