import hashlib
import re
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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


class ReturnForecast(BaseModel):
    """Model-issued terminal-horizon return distribution; host validates, never clamps."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    forecast_id: str = Field(min_length=1, max_length=64)
    symbol: str
    cutoff: int = Field(strict=True, ge=0)
    reference_price: Decimal
    reference_kind: Literal["LAST_CLOSE"]
    horizon_seconds: int = Field(strict=True, ge=60, le=21600)
    return_q10: Decimal
    return_q50: Decimal
    return_q90: Decimal
    target_return_fraction: Decimal | None = None
    review_after_seconds: int = Field(strict=True, ge=0)
    invalidation: str
    evidence_ids: tuple[str, ...]
    parent_forecast_id: str | None = Field(default=None, min_length=1, max_length=64)

    @field_validator("symbol")
    @classmethod
    def valid_symbol_pattern(cls, value):
        if not re.fullmatch(r"^[A-Z0-9]+(?:TMN|USDT)$", value):
            raise ValueError("Symbol must match canonical exchange pair format")
        return value

    @field_validator("reference_price", mode="before")
    @classmethod
    def positive_reference(cls, value):
        return decimal_number(value, positive=True)

    @field_validator("return_q10", "return_q50", "return_q90", mode="before")
    @classmethod
    def signed_return_fraction(cls, value):
        if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
            raise ValueError("Return must be an exact decimal, never a float")
        number = Decimal(value)
        if not number.is_finite() or abs(number) > 1:
            raise ValueError("Return fraction must be finite and within [-1, 1]")
        if len(number.as_tuple().digits) > 128 or abs(number.as_tuple().exponent) > 128:
            raise ValueError("Decimal exceeds supported precision/range")
        return number

    @field_validator("target_return_fraction", mode="before")
    @classmethod
    def positive_target(cls, value):
        return None if value is None else decimal_number(value, positive=True)

    @field_validator("forecast_id", "invalidation", mode="before")
    @classmethod
    def nonempty_text(cls, value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Text fields must be non-empty strings")
        return value.strip()

    @field_validator("evidence_ids", mode="before")
    @classmethod
    def normalized_evidence(cls, value):
        if isinstance(value, (list, tuple, set, frozenset)):
            items = tuple(str(x).strip() for x in value)
        else:
            raise ValueError("evidence_ids must be a collection of strings")
        if not items or any(not item for item in items) or len(set(items)) != len(items):
            raise ValueError("evidence_ids must be non-empty and unique")
        return items

    @model_validator(mode="after")
    def ordered_quantiles(self):
        if not self.return_q10 <= self.return_q50 <= self.return_q90:
            raise ValueError("Quantiles must satisfy q10 <= q50 <= q90")
        if self.review_after_seconds > self.horizon_seconds:
            raise ValueError("review_after_seconds cannot exceed horizon_seconds")
        if self.parent_forecast_id == self.forecast_id:
            raise ValueError("Forecast cannot parent itself")
        return self


def validate_forecast(
    forecast,
    *,
    snapshot,
    horizon_min_seconds: int,
    horizon_max_seconds: int,
    remaining_seconds: int | None = None,
) -> None:
    """Host checks for one forecast; never adjusts the model's numbers."""
    if not isinstance(forecast, ReturnForecast):
        raise ValueError("Forecast must be a ReturnForecast")
    if (
        forecast.symbol != snapshot.symbol
        or forecast.cutoff != snapshot.cutoff
        or forecast.reference_price != snapshot.last_close
        or forecast.reference_kind != "LAST_CLOSE"
    ):
        raise ValueError("Forecast does not match the chosen snapshot")
    if not horizon_min_seconds <= forecast.horizon_seconds <= horizon_max_seconds:
        raise ValueError("Forecast horizon outside the pre-registered policy range")
    if remaining_seconds is not None and forecast.horizon_seconds > remaining_seconds:
        raise ValueError("Forecast horizon exceeds the remaining run/deadline")
    if any(eid not in snapshot.evidences for eid in forecast.evidence_ids):
        raise ValueError("Forecast cites evidence outside the chosen snapshot")


class RoleDecisionProposal(DecisionProposal):
    role: Literal["ENTRY_ANALYST", "POSITION_REVIEWER"]
    cutoff: int = Field(strict=True, ge=0)
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    position_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    opportunity_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    symbol: str | None = None
    horizon_seconds: int | None = Field(default=None, strict=True, ge=60, le=21600)
    review_after_seconds: int | None = Field(default=None, strict=True, ge=0)
    forecast: ReturnForecast | None = None

    @field_validator("symbol")
    @classmethod
    def optional_symbol_pattern(cls, value):
        if value is None:
            return None
        if not re.fullmatch(r"^[A-Z0-9]+(?:TMN|USDT)$", value):
            raise ValueError("Symbol must match canonical exchange pair format")
        return value



def validate_role_proposal(
    proposal, *, role, snapshot, position, opportunity,
    market_batch=None, horizon_bounds=None, remaining_seconds=None, require_forecast=False,
):
    """Reject cross-role/state output before the unchanged execution Decision boundary.

    market_batch maps symbol -> (FeatureSnapshot, EntryOpportunityContext). When supplied,
    the entry role selects a symbol from that bounded batch; the host still owns risk.
    """
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

    if proposal.symbol is not None and proposal.symbol != snapshot.symbol:
        raise ValueError("Selected symbol does not match the bound snapshot")
    if market_batch is not None:
        if role != "ENTRY_ANALYST" or snapshot.symbol not in market_batch:
            raise ValueError("Batch is only valid for the entry role")
        if proposal.action == "ENTER":
            if proposal.symbol is None or proposal.symbol != snapshot.symbol:
                raise ValueError("ENTER must select exactly the bound batch symbol")
            if proposal.forecast is None or proposal.horizon_seconds is None:
                raise ValueError("ENTER requires a horizon forecast")
            if horizon_bounds is None:
                raise ValueError("Host horizon bounds required")
            validate_forecast(
                proposal.forecast, snapshot=snapshot,
                horizon_min_seconds=horizon_bounds[0], horizon_max_seconds=horizon_bounds[1],
                remaining_seconds=remaining_seconds,
            )
            if (
                proposal.horizon_seconds != proposal.forecast.horizon_seconds
                or proposal.review_after_seconds != proposal.forecast.review_after_seconds
            ):
                raise ValueError("Horizon fields disagree with the forecast")
    elif require_forecast and proposal.action == "ENTER":
        if proposal.forecast is None or proposal.horizon_seconds is None or horizon_bounds is None:
            raise ValueError("ENTER requires a horizon forecast")
        validate_forecast(
            proposal.forecast, snapshot=snapshot,
            horizon_min_seconds=horizon_bounds[0], horizon_max_seconds=horizon_bounds[1],
            remaining_seconds=remaining_seconds,
        )
        if (
            proposal.horizon_seconds != proposal.forecast.horizon_seconds
            or proposal.review_after_seconds != proposal.forecast.review_after_seconds
        ):
            raise ValueError("Horizon fields disagree with the forecast")
    elif proposal.forecast is not None:
        if role != "POSITION_REVIEWER":
            raise ValueError("Only the reviewer may attach a forecast on the single-snapshot path")
        validate_forecast(
            proposal.forecast, snapshot=snapshot,
            horizon_min_seconds=horizon_bounds[0] if horizon_bounds else 60,
            horizon_max_seconds=horizon_bounds[1] if horizon_bounds else 21600,
            remaining_seconds=remaining_seconds,
        )


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
