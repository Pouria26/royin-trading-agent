"""Local configuration boundary; importing this module performs no I/O."""

import os
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

from dotenv.parser import parse_stream
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)


class RuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    RUN_MODE: Literal["historical", "shadow", "live"] = "shadow"
    ENABLE_LIVE_TRADING: bool = False
    WALLEX_BASE_URL: Literal["https://api.wallex.ir"] = "https://api.wallex.ir"
    WALLEX_API_KEY: SecretStr | None = Field(default=None, repr=False, exclude=True)
    SUB_ACCOUNT_CLIENT_ID: SecretStr | None = Field(default=None, repr=False, exclude=True)
    WALLEX_ALLOWED_MARKETS: tuple[str, ...] = ()
    LLM_PROVIDER: Literal["boxapi"] = "boxapi"
    LLM_BASE_URL: Literal["https://ai.boxapi.ir/ai/v1"] = "https://ai.boxapi.ir/ai/v1"
    LLM_MODEL: Literal["gpt-6-luna", "gpt-5.6-luna", "gpt-5.4-mini"] = "gpt-6-luna"
    BOXAPI_API_KEY: SecretStr | None = Field(default=None, repr=False, exclude=True)
    LLM_TOKEN_BUDGET: int | None = Field(default=None, ge=0)
    LLM_COST_BUDGET: Decimal | None = Field(default=None, ge=0)
    LLM_COST_CURRENCY: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    CHALLENGE_END_AT: AwareDatetime | None = None
    FINALIZE_START_AT: AwareDatetime | None = None
    STATE_DB_PATH: Path = Path("data/state.sqlite3")
    ARTIFACTS_DIR: Path = Path("artifacts")

    @field_validator(
        "WALLEX_API_KEY", "SUB_ACCOUNT_CLIENT_ID", "BOXAPI_API_KEY",
        "LLM_TOKEN_BUDGET", "LLM_COST_BUDGET", "LLM_COST_CURRENCY",
        "CHALLENGE_END_AT", "FINALIZE_START_AT", mode="before",
    )
    @classmethod
    def empty_optional(cls, value):
        return None if value == "" else value

    @field_validator("ENABLE_LIVE_TRADING", mode="before")
    @classmethod
    def explicit_boolean(cls, value):
        if type(value) is bool:
            return value
        if value not in ("true", "false"):
            raise ValueError("Use true or false")
        return value == "true"

    @field_validator("LLM_TOKEN_BUDGET", mode="before")
    @classmethod
    def integer_budget(cls, value):
        if value == "":
            return None
        if value is not None and not (
            type(value) is int or (isinstance(value, str) and re.fullmatch(r"[0-9]+", value))
        ):
            raise ValueError("Token budget must be an integer")
        return value

    @field_validator("LLM_COST_BUDGET", mode="before")
    @classmethod
    def decimal_budget(cls, value):
        if value is not None and not isinstance(value, (str, Decimal)):
            raise ValueError("Cost budget must be a decimal string")
        return value

    @field_validator("CHALLENGE_END_AT", "FINALIZE_START_AT", mode="before")
    @classmethod
    def explicit_timestamp(cls, value):
        if value is None or value == "":
            return None
        if not isinstance(value, str):
            raise ValueError("Use an ISO timestamp with UTC offset")
        return datetime.fromisoformat(value)

    @field_validator("CHALLENGE_END_AT", "FINALIZE_START_AT")
    @classmethod
    def utc_timestamp(cls, value):
        return value.astimezone(UTC) if value is not None else None

    @field_validator("WALLEX_ALLOWED_MARKETS", mode="before")
    @classmethod
    def selected_symbols(cls, value):
        if isinstance(value, str):
            value = tuple(part.strip() for part in value.split(",")) if value else ()
        if not isinstance(value, tuple) or any(
            not isinstance(symbol, str) or not re.fullmatch(r"[A-Z0-9]+(?:TMN|USDT)", symbol)
            for symbol in value
        ):
            raise ValueError("Use comma-separated API symbols; eligibility is checked in T02")
        if len(set(value)) != len(value):
            raise ValueError("Duplicate market selection")
        return value

    @field_validator("STATE_DB_PATH", "ARTIFACTS_DIR", mode="before")
    @classmethod
    def nonempty_path(cls, value):
        if isinstance(value, str) and not value.strip():
            raise ValueError("Path cannot be empty")
        return value

    @model_validator(mode="after")
    def closed_gates(self):
        if self.RUN_MODE == "live" or self.ENABLE_LIVE_TRADING:
            raise ValueError(
                "Live is unavailable until account, market, risk, deadline and T10 gates exist"
            )
        if self.FINALIZE_START_AT is not None and (
            self.CHALLENGE_END_AT is None or self.FINALIZE_START_AT >= self.CHALLENGE_END_AT
        ):
            raise ValueError("Finalization must precede an explicit end time")
        budgets = (self.LLM_TOKEN_BUDGET, self.LLM_COST_BUDGET, self.LLM_COST_CURRENCY)
        if any(value is not None for value in budgets) and any(value is None for value in budgets):
            raise ValueError("Supply token budget, cost budget and currency together")
        return self


def load_config(env_file: Path | None = None, *, environ: Mapping[str, str] | None = None):
    """Reject unknown file keys and malformed dotenv; process settings take precedence."""
    values = {}
    path = env_file if env_file is not None else Path(".env")
    if env_file is not None or path.exists():
        with path.open(encoding="utf-8-sig") as stream:
            for binding in parse_stream(stream):
                if binding.error or (binding.key is not None and binding.value is None):
                    raise ValueError("Malformed dotenv assignment")
                if binding.key is not None:
                    if binding.key in values:
                        raise ValueError("Duplicate dotenv key")
                    values[binding.key] = binding.value.strip()
    environment = os.environ if environ is None else environ
    for key, value in environment.items():
        if key in RuntimeConfig.model_fields or key.startswith(
            ("RUN_", "ENABLE_LIVE_", "WALLEX_", "SUB_ACCOUNT_", "LLM_", "BOXAPI_", "GOOGLE_API_")
        ):
            values[key] = value.strip()
    return RuntimeConfig.model_validate(values)
