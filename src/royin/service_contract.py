"""Explicit, immutable bounds for a single multi-day shadow mission."""

import hashlib
import math
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


class ServiceContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    schema_version: Literal[1] = 1
    service_id: str = Field(pattern=r"^svc_[A-Za-z0-9_-]{1,48}$")
    mode: Literal["shadow"] = "shadow"
    started_at: AwareDatetime
    submission_deadline_at: AwareDatetime
    trading_end_at: AwareDatetime
    finalize_start_at: AwareDatetime
    credit_expires_at: AwareDatetime | None = None
    poll_seconds: Literal[15, 30, 60] = 30
    analysis_interval_seconds: Literal[300, 900, 1200] = 300
    max_public_gets: int = Field(default=40000, ge=64, le=50000, strict=True)
    max_role_decisions: int = Field(default=1200, ge=1, le=2304, strict=True)
    max_debit_tmn: Decimal = Field(
        default=Decimal("150000"), ge=Decimal("100300"), le=Decimal("500000")
    )
    minimum_notional_tmn: Decimal = Field(default=Decimal("100000"), ge=Decimal("100000"))
    horizon_max_seconds: int = Field(default=14400, ge=300, le=36000, strict=True)

    @field_validator(
        "started_at",
        "submission_deadline_at",
        "trading_end_at",
        "finalize_start_at",
        "credit_expires_at",
        mode="before",
    )
    @classmethod
    def timestamp(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            value = datetime.fromisoformat(value)
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Explicit ISO time with UTC offset required")
        return value.astimezone(UTC)

    @field_validator("max_debit_tmn", "minimum_notional_tmn", mode="before")
    @classmethod
    def exact_money(cls, value):
        if not isinstance(value, (str, Decimal)):
            raise ValueError("Money must be a decimal string")
        return value

    @model_validator(mode="after")
    def ordered(self):
        if not self.started_at < self.finalize_start_at < self.effective_end_at:
            raise ValueError("Start < finalization < financial/credit end is required")
        if not 600 <= self.duration_seconds <= 345600:
            raise ValueError("Mission must last ten minutes to four days")
        if self.submission_deadline_at > self.trading_end_at:
            raise ValueError("Submission deadline must not follow the financial end")
        if self.max_debit_tmn < self.minimum_notional_tmn * Decimal("1.003"):
            raise ValueError("Minimum notional plus quote fee exceeds the debit cap")
        return self

    @property
    def effective_end_at(self):
        return min(self.trading_end_at, self.credit_expires_at or self.trading_end_at)

    @property
    def duration_seconds(self):
        return int((self.effective_end_at - self.started_at).total_seconds())

    @property
    def cycles(self):
        return math.ceil(self.duration_seconds / self.poll_seconds) + 1

    @property
    def sha256(self):
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()
