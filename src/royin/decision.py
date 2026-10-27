import hashlib
import re
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from royin.market_context import MarketContext
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


class ResearchExecutionCapacity(BaseModel):
    """Observed rules and a research debit ceiling, never financial authorization."""
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    debit_ceiling_tmn: Decimal = Field(gt=0, allow_inf_nan=False)
    tick_size: Decimal = Field(gt=0, allow_inf_nan=False)
    step_size: Decimal = Field(gt=0, allow_inf_nan=False)
    min_notional: Decimal = Field(gt=0, allow_inf_nan=False)
    min_quantity: Decimal = Field(gt=0, allow_inf_nan=False)
    maker_fee_rate: Decimal = Field(ge=0, lt=1, allow_inf_nan=False)
    taker_fee_rate: Decimal = Field(ge=0, lt=1, allow_inf_nan=False)
    reserve_exit_base_fee: bool = False


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
    market_context: MarketContext | None = None
    asset_return_24h: Decimal | None = Field(default=None, allow_inf_nan=False)
    relative_strength_24h: Decimal | None = Field(default=None, allow_inf_nan=False)
    best_bid: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    best_ask: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    execution_capacity: ResearchExecutionCapacity | None = None

    @property
    def orderbook_imbalance(self):
        """Static notional imbalance inside the scanner's spread band, not trade flow."""
        return (self.bid_depth_tmn - self.ask_depth_tmn) / (self.bid_depth_tmn + self.ask_depth_tmn)

    @property
    def sha256(self):
        # Preserve historical opportunity hashes when this new optional dossier is absent.
        exclude = {"execution_capacity"} if self.execution_capacity is None else None
        return hashlib.sha256(self.model_dump_json(exclude=exclude).encode()).hexdigest()


MAX_RESEARCH_SYMBOLS = 10


class MarketCatalogCandidate(BaseModel):
    """Validated public catalog facts for research selection, never an entry signal."""
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    symbol: str = Field(pattern=r"^[A-Z0-9]+TMN$")
    price_tmn: Decimal = Field(gt=0, allow_inf_nan=False)
    turnover_tmn: Decimal = Field(gt=0, allow_inf_nan=False)
    return_24h: Decimal | None = Field(default=None, ge=-1, allow_inf_nan=False)
    research_requests: int = Field(default=0, strict=True, ge=0)
    accepted_research_count: int = Field(default=0, strict=True, ge=0)
    lot_hint: Literal["FIT_ESTIMATE", "NO_FIT_FOUND", "UNKNOWN"] | None = None
    last_research_status: Literal["DATA_OK", "HISTORY_PARSE_FAILED", "HISTORY_FETCH_FAILED",
        "SPREAD_TOO_WIDE", "DEPTH_TOO_SHALLOW", "DEPTH_FETCH_FAILED", "OTHER_REJECTION"] | None = None
    last_research_at: int | None = Field(default=None, strict=True, ge=0)
    last_capacity_status: Literal["FIT", "BLOCKED"] | None = None
    last_cash_hurdle: Decimal | None = Field(default=None, allow_inf_nan=False)
    last_trend: Literal["BULLISH", "BEARISH", "NEUTRAL"] | None = None

    @model_validator(mode="after")
    def coherent_observation(self):
        if self.last_capacity_status is not None and (
                self.last_research_status != "DATA_OK" or self.last_research_at is None):
            raise ValueError("Observed capacity requires a timestamped successful data row")
        return self


class MarketResearchUniverse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    observed_at: int = Field(strict=True, ge=0)
    markets: tuple[MarketCatalogCandidate, ...] = Field(min_length=1, max_length=256)
    unavailable_symbols: tuple[str, ...] = ()
    control_symbols: tuple[str, ...] = Field(default=(), max_length=2)

    @model_validator(mode="after")
    def unique_symbols(self):
        if len({row.symbol for row in self.markets}) != len(self.markets):
            raise ValueError("Research universe symbols must be unique")
        if (len(set(self.unavailable_symbols)) != len(self.unavailable_symbols)
                or not set(self.unavailable_symbols).issubset({row.symbol for row in self.markets})):
            raise ValueError("Unavailable research symbols must be unique universe members")
        if (len(set(self.control_symbols)) != len(self.control_symbols)
                or not set(self.control_symbols).issubset({row.symbol for row in self.markets})
                or set(self.control_symbols).intersection(self.unavailable_symbols)):
            raise ValueError("Research controls must be distinct available universe members")
        return self

    def screening_view(self):
        # Absolute price is unnecessary for catalog triage; exact values remain in the source trace.
        with localcontext() as ctx:
            ctx.prec = 160
            rows = [[row.symbol, int(row.turnover_tmn // Decimal(1000000)),
                str(row.return_24h.quantize(Decimal("0.0001"),rounding=ROUND_HALF_EVEN))
                    if row.return_24h is not None else None, row.research_requests,
                row.accepted_research_count] for row in self.markets]
        result = dict(catalog_sha256=self.catalog_sha256,observed_at=self.observed_at,
            columns=["symbol","turnover_million_tmn_floor","return_24h_fraction_rounded_4dp",
                "research_requests", "accepted_research_count"],rows=rows,
            unavailable_for_current_cutoff=list(self.unavailable_symbols))
        if self.control_symbols:
            result.update(host_research_controls=list(self.control_symbols),
                model_selection_limit=MAX_RESEARCH_SYMBOLS-len(self.control_symbols))
        if any(row.lot_hint is not None or row.last_research_status is not None for row in self.markets):
            statuses = ["DATA_OK", "HISTORY_PARSE_FAILED", "HISTORY_FETCH_FAILED", "SPREAD_TOO_WIDE",
                        "DEPTH_TOO_SHALLOW", "DEPTH_FETCH_FAILED", "OTHER_REJECTION"]
            result["selection_hints"] = dict(
                basis="Catalog-price lot estimate, not book validation/admission or a permanent ban; row indexes are zero-based",
                lot_fit=[i for i,row in enumerate(self.markets) if row.lot_hint == "FIT_ESTIMATE"],
                lot_no_fit=[i for i,row in enumerate(self.markets) if row.lot_hint == "NO_FIT_FOUND"],
                status_legend=statuses, recent_result_columns=["row","status_index","age_minutes"],
                recent_results=[[i,statuses.index(row.last_research_status),(self.observed_at-row.last_research_at)//60]
                    for i,row in enumerate(self.markets)
                    if row.last_capacity_status is None and row.last_research_status is not None and row.last_research_at is not None
                    and 0 <= self.observed_at-row.last_research_at <= 3600])
            observations=[]
            for i,row in enumerate(self.markets):
                if (row.last_capacity_status is not None and row.last_research_at is not None
                        and 0 <= self.observed_at-row.last_research_at <= 3600):
                    observations.append([i,(self.observed_at-row.last_research_at)//60,
                        1 if row.last_capacity_status=="FIT" else 0,
                        int((row.last_cash_hurdle*10000).to_integral_value(rounding=ROUND_HALF_EVEN))
                            if row.last_cash_hurdle is not None else None,
                        {"BULLISH":1,"BEARISH":-1,"NEUTRAL":0}.get(row.last_trend)])
            if observations:
                result["selection_hints"].update(
                    candidate_columns=["data_ok_row","age_minutes","capacity_fit_1_blocked_0","indicative_cash_hurdle_bps","trend_sign"],
                    recent_candidates=observations)
        return result


class ReturnForecast(BaseModel):
    """Model-issued terminal-horizon return distribution; host validates, never clamps."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    forecast_id: str = Field(min_length=1, max_length=64)
    symbol: str
    cutoff: int = Field(strict=True, ge=0)
    reference_price: Decimal
    reference_kind: Literal["LAST_CLOSE"]
    horizon_seconds: int = Field(strict=True, ge=60, le=259200)
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
        if isinstance(value, float):
            value = str(value)
        return decimal_number(value, positive=True)

    @field_validator("return_q10", "return_q50", "return_q90", mode="before")
    @classmethod
    def signed_return_fraction(cls, value):
        if isinstance(value, float):
            # JSON models emit numbers; the forecast is a research estimate, not money.
            if value != value or value in (float("inf"), float("-inf")):
                raise ValueError("Return must be finite")
            value = str(value)
        if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
            raise ValueError("Return must be an exact decimal, never an arbitrary object")
        number = Decimal(value)
        if not number.is_finite() or abs(number) > 1:
            raise ValueError("Return fraction must be finite and within [-1, 1]")
        if len(number.as_tuple().digits) > 128 or abs(number.as_tuple().exponent) > 128:
            raise ValueError("Decimal exceeds supported precision/range")
        return number

    @field_validator("target_return_fraction", mode="before")
    @classmethod
    def positive_target(cls, value):
        if value is None:
            return None
        if isinstance(value, float):
            value = str(value)
        return decimal_number(value, positive=True)

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
    # Role agents forecast returns; execution risk parameters belong to the host.
    target_profit_pct: None = None
    stop_loss_pct: None = None
    role: Literal["ENTRY_ANALYST", "POSITION_REVIEWER"]
    cutoff: int = Field(strict=True, ge=0)
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    position_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    opportunity_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$",
        description="ENTER must copy the selected candidate's exact opportunity_sha256; null is only allowed for WAIT or position review.")
    symbol: str | None = None
    horizon_seconds: int | None = Field(default=None, strict=True, ge=60, le=259200)
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


class MarketEntryProposal(RoleDecisionProposal):
    """Batch entry output: a forecast is mandatory even when the model waits."""

    forecast: ReturnForecast
    horizon_seconds: int = Field(strict=True, ge=60, le=259200)
    review_after_seconds: int = Field(strict=True, ge=0)
    compared_symbols: tuple[str, ...] | None = Field(default=None, max_length=MAX_RESEARCH_SYMBOLS)
    feasible_symbols: tuple[str, ...] | None = Field(default=None, max_length=MAX_RESEARCH_SYMBOLS)
    candidate_medians: tuple[tuple[str, int, Decimal], ...] | None = Field(
        default=None, max_length=3*MAX_RESEARCH_SYMBOLS)

    @field_validator("candidate_medians", mode="before")
    @classmethod
    def exact_candidate_medians(cls, value):
        if value is None:
            return None
        if not isinstance(value,(list,tuple)) or len(value)>3*MAX_RESEARCH_SYMBOLS:
            raise ValueError("Bounded candidate-horizon estimates required")
        result=[]
        for row in value:
            if (not isinstance(row,(list,tuple)) or len(row)!=3 or not isinstance(row[0],str)
                    or not re.fullmatch(r"^[A-Z0-9]+(?:TMN|USDT)$",row[0])
                    or type(row[1]) is not int or not 60<=row[1]<=259200):
                raise ValueError("Exact candidate-horizon estimate required")
            result.append((row[0],row[1],ReturnForecast.signed_return_fraction(row[2])))
        if len({(s,h) for s,h,_ in result})!=len(result):
            raise ValueError("Duplicate candidate-horizon estimate")
        return tuple(result)

    @field_validator("compared_symbols", "feasible_symbols", mode="before")
    @classmethod
    def distinct_compared_symbols(cls, value):
        if value is None:
            return None
        if (not isinstance(value,(list,tuple)) or any(not isinstance(s,str)
                or not re.fullmatch(r"^[A-Z0-9]+(?:TMN|USDT)$",s) for s in value)
                or len(set(value))!=len(value)):
            raise ValueError("Comparison symbols must be distinct canonical symbols")
        return tuple(value)


class MarketEntrySignal(MarketEntryProposal):
    """Model price/action signal; source hashes belong exclusively to the host."""

    symbol: str = Field(pattern=r"^[A-Z0-9]+(?:TMN|USDT)$")
    snapshot_sha256: None = Field(default=None, exclude=True)
    opportunity_sha256: None = Field(default=None, exclude=True)

    @model_validator(mode="before")
    @classmethod
    def host_owned_source_hashes(cls, value):
        if isinstance(value,dict) and any(key in value for key in ("snapshot_sha256","opportunity_sha256")):
            raise ValueError("Source hashes are host-owned and forbidden in model signals")
        return value


def validate_role_proposal(
    proposal, *, role, snapshot, position, opportunity,
    market_batch=None, horizon_bounds=None, remaining_seconds=None, require_forecast=False,
    require_comparison=False, evaluation_horizons=None,
):
    """Reject cross-role/state output before the unchanged execution Decision boundary.

    market_batch maps symbol -> (FeatureSnapshot, EntryOpportunityContext). When supplied,
    the entry role selects a symbol from that bounded batch; the host still owns risk.
    """
    if not isinstance(proposal, RoleDecisionProposal):
        raise ValueError("Invalid role proposal type")
    bindings = {"role": (proposal.role, role), "cutoff": (proposal.cutoff, snapshot.cutoff),
        "snapshot_sha256": (proposal.snapshot_sha256, snapshot.snapshot_sha256),
        "position_sha256": (proposal.position_sha256, position.sha256 if position else None)}
    if not (market_batch is not None and proposal.action == "WAIT"):
        bindings["opportunity_sha256"] = (proposal.opportunity_sha256, opportunity.sha256 if opportunity else None)
    for name, (actual, expected) in bindings.items():
        if actual != expected:
            raise ValueError("Role binding mismatch: " + name)
    allowed = {"WAIT", "ENTER"} if role == "ENTRY_ANALYST" else {"WAIT", "EXIT"}
    if proposal.action not in allowed or (
        proposal.target_profit_pct is not None or proposal.stop_loss_pct is not None
    ):
        raise ValueError("Role action or model-owned risk policy forbidden")

    if proposal.symbol is not None and proposal.symbol != snapshot.symbol:
        raise ValueError("Selected symbol does not match the bound snapshot")
    if any(eid not in snapshot.evidences for eid in proposal.evidence_ids):
        raise ValueError("Decision cites evidence outside the chosen snapshot")
    if market_batch is not None:
        if role != "ENTRY_ANALYST" or snapshot.symbol not in market_batch:
            raise ValueError("Batch is only valid for the entry role")
        if require_comparison and (not isinstance(proposal,MarketEntryProposal)
                or proposal.compared_symbols is None or set(proposal.compared_symbols)!=set(market_batch)):
            raise ValueError("Comparison does not cover the accepted research batch")
        explicit_capacity = any(opp.execution_capacity is not None for _snap,opp in market_batch.values())
        if require_comparison or explicit_capacity:
            from royin.risk import entry_cost_context
            costs={symbol:entry_cost_context(snap,opp) for symbol,(snap,opp) in market_batch.items()}
            feasible={symbol for symbol,cost in costs.items()
                if cost.get('capacity',{}).get('status')=='SELLABLE_WITH_BOUNDED_RESIDUAL'
                and cost.get('cash_break_even_reference_return_fraction') is not None}
            if require_comparison and (proposal.feasible_symbols is None or set(proposal.feasible_symbols)!=feasible):
                raise ValueError("Comparison misstates fresh execution capacity")
            if feasible and snapshot.symbol not in feasible:
                raise ValueError("Final selection must use a fresh feasible candidate")
            if proposal.action == "ENTER" and explicit_capacity and snapshot.symbol not in feasible:
                raise ValueError("Entry candidate has no proven execution capacity")
            if evaluation_horizons is not None:
                if (not require_comparison or not isinstance(evaluation_horizons,tuple)
                        or not evaluation_horizons or len(set(evaluation_horizons))!=len(evaluation_horizons)
                        or horizon_bounds is None or any(type(h) is not int
                            or not horizon_bounds[0]<=h<=horizon_bounds[1] for h in evaluation_horizons)):
                    raise ValueError("Host comparison horizons are invalid")
                horizons=set(evaluation_horizons)
                if snapshot.symbol in feasible and proposal.forecast is not None:
                    horizons.add(proposal.forecast.horizon_seconds)
                expected={(symbol,horizon) for symbol in feasible for horizon in horizons}
                estimates=proposal.candidate_medians
                if estimates is None or {(s,h) for s,h,_ in estimates}!=expected:
                    raise ValueError("Numeric comparison does not cover the candidate-horizon grid")
                if snapshot.symbol in feasible and proposal.forecast is not None:
                    selected=next(q for s,h,q in estimates if s==snapshot.symbol
                        and h==proposal.forecast.horizon_seconds)
                    if selected!=proposal.forecast.return_q50:
                        raise ValueError("Numeric comparison differs from the selected forecast")
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
            target = proposal.forecast.target_return_fraction
            if target is None or target <= 0:
                raise ValueError("Entry requires a positive target forecast")
            if opportunity.best_bid is not None and opportunity.best_ask is not None:
                # Local import avoids the existing risk -> Decision dependency at module load.
                from royin.risk import entry_cost_context
                cost = entry_cost_context(snapshot, opportunity)
                hurdle = Decimal(cost.get("cash_break_even_reference_return_fraction",
                                          cost["break_even_reference_return_fraction"]))
                if target <= hurdle:
                    raise ValueError("Entry target does not clear observed execution costs")
                if proposal.forecast.return_q50 <= hurdle:
                    raise ValueError("Entry central forecast does not clear observed execution costs")
            if (opportunity.market_context is not None
                    and opportunity.market_context.regime == "BEARISH" and not (
                    opportunity.relative_strength_24h is not None and opportunity.relative_strength_24h > 0
                    and "EV_TREND_BULLISH" in snapshot.evidences
                    )):
                raise ValueError("Bear-market exception lacks observed relative strength")
            if (
                proposal.horizon_seconds != proposal.forecast.horizon_seconds
                or proposal.review_after_seconds != proposal.forecast.review_after_seconds
            ):
                raise ValueError("Horizon fields disagree with the forecast")
        elif proposal.forecast is not None:
            # A WAIT may carry one research forecast; it never creates a position.
            if proposal.forecast.symbol != snapshot.symbol:
                raise ValueError("WAIT research forecast must bind the echoed snapshot")
            if horizon_bounds is None:
                raise ValueError("Host horizon bounds required")
            validate_forecast(
                proposal.forecast, snapshot=snapshot,
                horizon_min_seconds=horizon_bounds[0], horizon_max_seconds=horizon_bounds[1],
                remaining_seconds=None,  # A research WAIT forecast commits no funds or holding time.
            )
            if (
                (proposal.horizon_seconds is not None
                 and proposal.horizon_seconds != proposal.forecast.horizon_seconds)
                or (proposal.review_after_seconds is not None
                    and proposal.review_after_seconds != proposal.forecast.review_after_seconds)
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
            horizon_max_seconds=horizon_bounds[1] if horizon_bounds else 259200,
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
    horizon_seconds: int | None = None
    review_after_seconds: int | None = None
    forecast: ReturnForecast | None = None

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
        horizon_seconds=getattr(proposal, "horizon_seconds", None),
        review_after_seconds=getattr(proposal, "review_after_seconds", None),
        forecast=getattr(proposal, "forecast", None),
    )

