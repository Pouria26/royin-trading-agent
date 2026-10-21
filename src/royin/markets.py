"""Public metadata is not account permission; no private transport is provided here."""

import re
from dataclasses import dataclass
from decimal import Decimal, Inexact, localcontext
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from royin.market_data import decimal_number, decode_json


class Market(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)
    symbol: str = Field(pattern=r"^[A-Z0-9]+$")
    base_asset: str = Field(pattern=r"^[A-Z0-9]+$")
    quote_asset: Literal["TMN", "USDT"]
    is_spot: bool
    amount_precision: int = Field(ge=0)
    price_precision: int = Field(ge=0)

    @model_validator(mode="after")
    def actual_symbol(self):
        if self.symbol != self.base_asset + self.quote_asset or self.base_asset == self.quote_asset:
            raise ValueError("Metadata symbol and assets disagree")
        return self


def parse_catalog(payload):
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise ValueError("Unsuccessful catalog")
    result = payload.get("result")
    rows = result.get("markets") if isinstance(result, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ValueError("Missing market catalog")
    markets = {}
    for row in rows:
        market = Market.model_validate(row)
        if market.symbol in markets:
            raise ValueError("Duplicate market symbol")
        markets[market.symbol] = market
    return markets


def load_restrictions(path: Path):
    policy = decode_json(path.read_bytes())
    if not isinstance(policy, dict) or (
        type(policy.get("schema_version")) is not int or policy["schema_version"] != 1
        or policy.get("market_type") != "SPOT" or policy.get("leverage_allowed") is not False
    ):
        raise ValueError("Unsupported market policy")
    pairs = policy.get("unavailable_markets")
    if not isinstance(pairs, list) or any(
        not isinstance(pair, str) or not re.fullmatch(r"[A-Z0-9]+/(?:TMN|USDT)", pair)
        for pair in pairs
    ) or len(set(pairs)) != len(pairs):
        raise ValueError("Invalid restriction snapshot")
    return frozenset(pairs)


def eligible_markets(
    catalog, snapshot_pairs, *, account_symbols, account_denied=(), organizer_denied=(), selected=(),
):
    """Caller must supply a fresh, verified account universe; None always closes the gate."""
    if account_symbols is None:
        raise ValueError("Account market access is unknown")
    aliases = {f"{m.base_asset}/{m.quote_asset}": symbol for symbol, m in catalog.items()}
    aliases.update({symbol: symbol for symbol in catalog})

    def resolve(entries, *, allow_absent=False):
        if not isinstance(entries, (list, tuple, set, frozenset)):
            raise ValueError("Expected a collection of market identifiers")
        symbols = set()
        for entry in entries:
            if not isinstance(entry, str) or not re.fullmatch(r"[A-Z0-9]+(?:/(?:TMN|USDT))?", entry):
                raise ValueError("Invalid market identifier")
            if entry not in aliases:
                if allow_absent:
                    continue  # Delisted snapshot entries cannot grant access to anything.
                raise ValueError("Unknown market in account or operational selection")
            symbols.add(aliases[entry])
        return symbols

    denied = (
        resolve(snapshot_pairs, allow_absent=True)
        | resolve(account_denied, allow_absent=True)
        | resolve(organizer_denied, allow_absent=True)
    )
    eligible = {
        symbol for symbol in resolve(account_symbols) if catalog[symbol].is_spot and symbol not in denied
    }
    operational = resolve(selected)
    if operational - eligible:
        raise ValueError("Operational selection includes an ineligible market")
    return frozenset(eligible & operational if operational else eligible)


def parse_fee_rates(payload, symbol):
    """Documented coefficients, not percent values; private-account applicability is unverified."""
    if not isinstance(payload, dict) or ("success" in payload and payload["success"] is not True):
        raise ValueError("Unsuccessful fee response")
    result = payload.get("result")
    row = result.get(symbol) if isinstance(result, dict) else None
    if not isinstance(row, dict):
        raise ValueError("Missing market fee")
    rates = tuple(decimal_number(row.get(key)) for key in ("makerFeeRate", "takerFeeRate"))
    if any(rate >= 1 for rate in rates):
        raise ValueError("Fee coefficient must be less than one")
    return rates


@dataclass(frozen=True)
class Balance:
    total: Decimal
    available: Decimal
    locked: Decimal


def parse_credit_balances(payload):
    """/v1/account/balances-detail schema only; does not authenticate account ownership."""
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise ValueError("Unsuccessful credit balance response")
    rows = payload.get("result")
    if not isinstance(rows, dict) or not rows:
        raise ValueError("Missing credit balances")
    balances = {}
    for symbol, row in rows.items():
        if not isinstance(symbol, str) or not re.fullmatch(r"[A-Z0-9]+", symbol) or (
            not isinstance(row, dict) or row.get("symbol") != symbol
        ):
            raise ValueError("Balance asset and symbol disagree")
        total, available, locked = (
            decimal_number(row.get(key)) for key in ("total", "available", "freeze")
        )
        with localcontext() as context:
            context.prec = 128
            context.traps[Inexact] = True
            if total != available + locked:
                raise ValueError("Total does not equal available plus frozen balance")
        balances[symbol] = Balance(total, available, locked)
    return balances
