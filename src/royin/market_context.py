"""Observed cross-market context, never a probability or a forecast of profit."""
import hashlib
import json
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MarketContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    regime: Literal["BULLISH", "BEARISH", "MIXED", "UNKNOWN"]
    observed_at: int = Field(ge=0)
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sample_count: int = Field(ge=0)
    positive_breadth: Decimal = Field(ge=0, le=1, allow_inf_nan=False)
    median_return_24h: Decimal = Field(allow_inf_nan=False)
    usdt_tmn_return_24h: Decimal | None = Field(default=None, allow_inf_nan=False)
    basis: Literal["CRYPTO_VS_USDT", "TMN_ONLY_UNADJUSTED"]


def catalog_return(row):
    """Wallex change_24h is percentage points; malformed/unknown is unavailable."""
    value = row.get("change_24h")
    if value is None or isinstance(value, (bool, float)):
        return None
    try:
        number = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return None
    if (not number.is_finite() or number < -100 or len(number.as_tuple().digits) > 128
            or abs(number.as_tuple().exponent) > 128):
        return None
    return number / 100


def market_context(payload, eligible_symbols, *, observed_at):
    rows = {r["symbol"]: r for r in payload["result"]["markets"]}
    cash_return = catalog_return(rows.get("USDTTMN", {}))
    if cash_return is not None and cash_return <= -1:
        cash_return = None
    returns = []
    for symbol in sorted(eligible_symbols):
        row = rows[symbol]
        if row.get("quote_asset") != "TMN" or row.get("base_asset") == "USDT":
            continue
        value = catalog_return(row)
        if value is not None:
            # Remove local fiat/USDT movement when this benchmark is available.
            returns.append((1 + value) / (1 + cash_return) - 1 if cash_return is not None else value)
    returns.sort()
    n = len(returns)
    breadth = Decimal(sum(r > 0 for r in returns)) / n if n else Decimal(0)
    median = (returns[(n-1)//2] + returns[n//2]) / 2 if n else Decimal(0)
    label = "UNKNOWN"
    if n >= 3:
        label = "BULLISH" if breadth >= Decimal(".6") and median > 0 else (
            "BEARISH" if breadth <= Decimal(".4") and median < 0 else "MIXED")
    return MarketContext(regime=label, observed_at=observed_at,
        catalog_sha256=hashlib.sha256(json.dumps(payload, default=str, sort_keys=True).encode()).hexdigest(),
        sample_count=n, positive_breadth=breadth, median_return_24h=median,
        usdt_tmn_return_24h=cash_return,
        basis="CRYPTO_VS_USDT" if cash_return is not None else "TMN_ONLY_UNADJUSTED")
