"""Host risk gates, market rules, exposure controls, and post-fee sellability checks."""

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from decimal import ROUND_CEILING, ROUND_DOWN, ROUND_FLOOR, ROUND_HALF_UP, Decimal, localcontext
from fractions import Fraction
from typing import Literal

from royin.decision import Decision
from royin.ledger import Ledger, validate_decimal


@dataclass(frozen=True)
class MarketRules:
    symbol: str
    base_asset: str
    quote_asset: str
    tick_size: Decimal
    step_size: Decimal
    min_notional: Decimal
    min_quantity: Decimal
    maker_fee_rate: Decimal
    taker_fee_rate: Decimal

    def __post_init__(self):
        validate_decimal(self.tick_size, "tick_size", strictly_positive=True)
        validate_decimal(self.step_size, "step_size", strictly_positive=True)
        validate_decimal(self.min_notional, "min_notional", strictly_positive=True)
        validate_decimal(self.min_quantity, "min_quantity", strictly_positive=True)
        validate_decimal(self.maker_fee_rate, "maker_fee_rate", allow_zero=True)
        validate_decimal(self.taker_fee_rate, "taker_fee_rate", allow_zero=True)
        if self.maker_fee_rate >= 1 or self.taker_fee_rate >= 1:
            raise ValueError("Fee fractions must be below one")
        if not self.symbol or not isinstance(self.symbol, str):
            raise ValueError("symbol must be a non-empty string")
        if not self.base_asset or not isinstance(self.base_asset, str):
            raise ValueError("base_asset must be a non-empty string")
        if not self.quote_asset or not isinstance(self.quote_asset, str):
            raise ValueError("quote_asset must be a non-empty string")

    def quantize_price(self, price: Decimal) -> Decimal:
        validate_decimal(price, "price", strictly_positive=True)
        return (price / self.tick_size).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        ) * self.tick_size

    def quantize_quantity(self, quantity: Decimal, round_down: bool = True) -> Decimal:
        validate_decimal(quantity, "quantity", allow_zero=True)
        rounding = ROUND_DOWN if round_down else ROUND_HALF_UP
        return (quantity / self.step_size).quantize(
            Decimal("1"), rounding=rounding
        ) * self.step_size


def rules_with_notional_floor(rules: MarketRules, floor_tmn: Decimal) -> MarketRules:
    """A team/organizer floor may tighten observed rules; it never converts quote units."""
    validate_decimal(floor_tmn, "minimum TMN notional", allow_zero=True)
    if rules.quote_asset != "TMN":
        raise ValueError("A TMN notional floor requires TMN market rules")
    return replace(rules, min_notional=max(rules.min_notional, floor_tmn))


@dataclass(frozen=True)
class RiskPolicy:
    max_order_tmn: Decimal
    max_exposure_tmn: Decimal
    stop_loss_pct: Decimal
    max_drawdown_pct: Decimal
    deadline_utc: int
    min_seconds_before_deadline: int = 3600
    max_stale_seconds: int = 1800

    def __post_init__(self):
        validate_decimal(self.max_order_tmn, "max_order_tmn", strictly_positive=True)
        validate_decimal(self.max_exposure_tmn, "max_exposure_tmn", strictly_positive=True)
        validate_decimal(self.stop_loss_pct, "stop_loss_pct", strictly_positive=True)
        validate_decimal(self.max_drawdown_pct, "max_drawdown_pct", strictly_positive=True)
        if type(self.deadline_utc) is not int or self.deadline_utc <= 0:
            raise ValueError("deadline_utc must be a positive integer timestamp")


@dataclass(frozen=True)
class RiskResult:
    approved: bool
    reason: str
    action: Literal["WAIT", "ENTER", "EXIT"]
    symbol: str
    quantity: Decimal
    price: Decimal
    stop_price: Decimal | None
    estimated_fee_quote: Decimal


def allocate_entry_capital(*, equity_tmn, free_cash_tmn, price_tmn, atr_tmn, depth_tmn,
                           fee_rate, tick_size, bootstrap, risk_scale,
                           residual_loss_reserve_tmn=Decimal("0")):
    """Versioned host capital plan. Conditional stop loss is not a guaranteed maximum loss."""
    for name, value in (("equity", equity_tmn), ("price", price_tmn), ("depth", depth_tmn), ("tick", tick_size)):
        validate_decimal(value, name, strictly_positive=True)
    for name, value in (("cash", free_cash_tmn), ("ATR", atr_tmn), ("fee", fee_rate)):
        validate_decimal(value, name, allow_zero=True)
    validate_decimal(risk_scale, "risk scale", strictly_positive=True)
    validate_decimal(residual_loss_reserve_tmn, "residual loss reserve", allow_zero=True)
    if type(bootstrap) is not bool or risk_scale > 1 or fee_rate > Decimal(".003"):
        raise ValueError("Invalid capital policy inputs")
    stop = max(Decimal(".012"), 2 * atr_tmn / price_tmn)
    loss_fraction = stop + 2 * fee_rate + Decimal(".001") + tick_size / price_tmn
    risk_budget = equity_tmn * Decimal(".005") * risk_scale
    trading_risk_budget = max(Decimal("0"), risk_budget - residual_loss_reserve_tmn)
    cap = min(free_cash_tmn, equity_tmn * Decimal(".50"), equity_tmn * Decimal(".80"),
              depth_tmn * Decimal(".05"), trading_risk_budget / loss_fraction)
    if bootstrap:
        cap = min(cap, Decimal("150000"))
    cap = cap.quantize(Decimal(".01"), rounding=ROUND_DOWN)
    return dict(policy="VOLATILITY_CAPITAL_V1", approved=stop <= Decimal(".06") and cap >= Decimal("100300"),
                reason="ATR stop exceeds six percent" if stop > Decimal(".06") else
                "Insufficient post-fee capital or liquidity" if cap < Decimal("100300") else "HOST_RISK_SIZED",
                debit_limit_tmn=str(cap), stop_fraction=str(stop), loss_fraction=str(loss_fraction),
                risk_budget_tmn=str(risk_budget), bootstrap=bootstrap,
                residual_loss_reserve_tmn=str(residual_loss_reserve_tmn),
                confidence_used_as_probability=False)


@dataclass(frozen=True)
class PositionProtectionPolicy:
    """Explicit paper policy; checkpoints request review, never force profit taking."""

    initial_stop_pct: Decimal
    trailing_drawdown_pct: Decimal
    checkpoint_profit_pct: Decimal
    review_interval_seconds: int
    hard_holding_seconds: int
    deadline_utc: int
    exit_buffer_seconds: int
    max_quote_age_seconds: int
    max_loss_tmn: Decimal
    profit_retention_ratio: Decimal = Decimal("0")
    net_activation_fraction: Decimal = Decimal("0")

    def __post_init__(self):
        validate_decimal(self.max_loss_tmn, "maximum position loss", strictly_positive=True)
        for value in (self.initial_stop_pct, self.trailing_drawdown_pct, self.checkpoint_profit_pct):
            validate_decimal(value, "protection fraction", strictly_positive=True)
            if value >= 1:
                raise ValueError("Protection fractions must be below one")
        for value in (self.review_interval_seconds, self.hard_holding_seconds,
                      self.deadline_utc, self.max_quote_age_seconds):
            if type(value) is not int or value <= 0:
                raise ValueError("Protection times must be positive integers")
        if type(self.exit_buffer_seconds) is not int or not 0 <= self.exit_buffer_seconds < self.deadline_utc:
            raise ValueError("Invalid exit buffer")
        if self.review_interval_seconds > self.hard_holding_seconds:
            raise ValueError("Review interval exceeds hard holding cap")
        validate_decimal(self.profit_retention_ratio, "profit retention ratio", allow_zero=True)
        validate_decimal(self.net_activation_fraction, "net activation fraction", allow_zero=True)
        if self.profit_retention_ratio > 1 or self.net_activation_fraction >= 1:
            raise ValueError("Retention ratio must be <= 1 and activation fraction < 1")

    @property
    def sha256(self):
        return hashlib.sha256(json.dumps(asdict(self), default=str, sort_keys=True).encode()).hexdigest()


def calculate_retention_stop_price(
    *,
    cost_basis: Decimal,
    sellable_quantity: Decimal,
    desired_net_profit: Decimal,
    taker_fee_rate: Decimal,
    slippage_pct: Decimal = Decimal("0.0005"),
    tick_size: Decimal = Decimal("1"),
) -> Decimal:
    """Calculate the exact stop price needed to secure desired_net_profit upon exit.

    Formula: S = ceil_tick((cost_basis + desired_net_profit) / (quantity * (1 - fee) * (1 - slippage)), tick_size)
    Ceiling quantize to tick_size guarantees rounding never weakens the net floor.
    """
    validate_decimal(cost_basis, "cost_basis", strictly_positive=True)
    validate_decimal(sellable_quantity, "sellable_quantity", strictly_positive=True)
    validate_decimal(desired_net_profit, "desired_net_profit", allow_zero=True)
    validate_decimal(taker_fee_rate, "taker_fee_rate", allow_zero=True)
    validate_decimal(slippage_pct, "slippage_pct", allow_zero=True)
    validate_decimal(tick_size, "tick_size", strictly_positive=True)

    denom = sellable_quantity * (Decimal(1) - taker_fee_rate) * (Decimal(1) - slippage_pct)
    if denom <= Decimal(0):
        raise ValueError("Invalid denominator in retention stop calculation")
    raw_price = (cost_basis + desired_net_profit) / denom
    from decimal import ROUND_CEILING
    ticks = (raw_price / tick_size).quantize(Decimal("1"), rounding=ROUND_CEILING)
    return ticks * tick_size


def entry_cost_context(snapshot, opportunity, *, slippage_pct=Decimal("0.0005")):
    """Per-unit research hurdle; actual size, fee asset and ticks remain host gates.

    The scanner supplies the sum of two assumed fees. This is a declared symmetric
    fee estimate, never an exchange fee observation or an expected-value estimate.
    """
    validate_decimal(slippage_pct, "slippage fraction", allow_zero=True)
    validate_decimal(opportunity.round_trip_fee_pct, "round-trip fee", allow_zero=True)
    if slippage_pct >= 1 or opportunity.round_trip_fee_pct >= 1:
        raise ValueError("Execution fractions must be below one")
    if opportunity.best_bid is None or opportunity.best_ask is None:
        return dict(policy="BOOK_COST_CONTEXT_V1", status="UNAVAILABLE_MISSING_QUOTES")
    bid, ask, reference = opportunity.best_bid, opportunity.best_ask, snapshot.last_close
    for value in (bid, ask, reference):
        validate_decimal(value, "positive research price", strictly_positive=True)
    if bid > ask:
        raise ValueError("Crossed research quotes")
    fee = opportunity.round_trip_fee_pct / 2
    # Keep the original candle reference: the ask may have moved above that price.
    entry = ask * (1 + slippage_pct) * (1 + fee)
    liquidation_factor = (bid / ask) * (1 - slippage_pct) * (1 - fee)
    break_even = entry / (reference * liquidation_factor) - 1
    result = dict(policy="BOOK_COST_CONTEXT_V1", status="ESTIMATE_NOT_ADMISSION",
        reference_kind="LAST_CLOSE", ask_return_from_reference=str(ask/reference-1),
        break_even_reference_return_fraction=str(break_even),
        assumed_fee_per_side=str(fee), slippage_per_side=str(slippage_pct),
        assumptions="Symmetric quote fees; observed bid/ask ratio; excludes quantity/tick rounding and future book changes")
    capacity = getattr(opportunity,"execution_capacity",None)
    if capacity is not None:
        rules = MarketRules(snapshot.symbol,snapshot.symbol.removesuffix("TMN"),"TMN",
            capacity.tick_size,capacity.step_size,capacity.min_notional,capacity.min_quantity,
            capacity.maker_fee_rate,capacity.taker_fee_rate)
        price = rules.quantize_price(ask*(1+slippage_pct))
        validate_decimal(price,"stepped research entry",strictly_positive=True)
        requested = rules.quantize_quantity(capacity.debit_ceiling_tmn/(price*(1+rules.taker_fee_rate)))
        exit_price = (bid*(1-slippage_pct)/rules.tick_size).to_integral_value(rounding=ROUND_DOWN)*rules.tick_size
        selected = choose_lot_quantity_for_exit(rules, requested, price, exit_price,
            reserve_exit_base_fee=capacity.reserve_exit_base_fee)
        quantity = selected if selected is not None else requested
        scenarios = project_exit_cash(rules=rules,quantity=quantity,entry_price=price,
            exit_price=exit_price,
            reserve_exit_base_fee=capacity.reserve_exit_base_fee)
        viable = selected is not None
        result["capacity"] = dict(status="SELLABLE_WITH_BOUNDED_RESIDUAL" if viable and all(
            s["sellable"] and s["residual_within_budget"] for s in scenarios) else "BLOCKED_MINIMUM_OR_RESIDUAL",
            basis="RESEARCH_DEBIT_CEILING_NOT_POSITION_AUTHORITY",debit_ceiling_tmn=str(capacity.debit_ceiling_tmn),
            entry_quantity=str(selected or Decimal(0)),requested_quantity_ceiling=str(requested),
            step_size=str(rules.step_size),min_notional_tmn=str(rules.min_notional),
            exit_base_fee_reserved=capacity.reserve_exit_base_fee,
            lot_fit=dict(policy="BOUNDED_DOWNWARD_LOT_FIT_V1",attempt_limit=256,
                status="FIT_WITHIN_EXISTING_CAPS" if viable else "INCOMPLETE_OR_NO_FIT_ABOVE_MINIMUM",
                decrements=int((requested-selected)/rules.step_size) if viable else None,
                scenarios_basis="SELECTED_QUANTITY" if viable else "REQUESTED_CEILING_DIAGNOSTIC_ONLY"),
            worst_residual_mark_tmn=max((s["residual_upper_bound_tmn"] for s in scenarios),key=Decimal),
            scenarios=scenarios)
        if viable and all(Decimal(s["proceeds_tmn"]) > 0 for s in scenarios):
            # Future bid tracks target*(bid/ask); cash proceeds also charge unsold lots.
            cash_hurdle = max(ask/reference * (Decimal(s["cash_debit_proceeds_ratio_upper"])
                             if s["cash_debit_proceeds_ratio_upper"] is not None
                             else Decimal(s["entry_debit_tmn"])/Decimal(s["proceeds_tmn"]))-1
                             for s in scenarios)
            result["cash_break_even_reference_return_fraction"] = str(max(break_even, cash_hurdle))
    return result


def _reserved_residual_bound(rules, quantity, entry_price, *, entry_asset):
    """Supremum for any aggregate BUY/SELL fee in [0, taker], not endpoint sampling.

    With a reserved SELL, S=h*floor(B/(h*(1+f))). The remaining base is largest
    when the actual SELL fee is zero. B-S increases within each floor cell and
    jumps down at its right boundary. Only the last boundary in the BUY-base
    interval and its upper endpoint can maximize it. Fractions keep floor-cell
    decisions exact; serialized upper bounds round up, never down.
    """
    upper, fee, step = Fraction(quantity), Fraction(rules.taker_fee_rate), Fraction(rules.step_size)
    lower = upper*(1-fee) if entry_asset == "base" else upper
    cell_width = step*(1+fee)
    last_cell = upper // cell_width
    bound = upper-last_cell*step
    boundary = last_cell*cell_width
    if lower < boundary <= upper:
        bound = max(bound, boundary-(last_cell-1)*step)
    with localcontext() as context:
        context.prec = 96
        context.rounding = ROUND_CEILING
        mark = bound*Fraction(entry_price)
        return (Decimal(bound.numerator)/Decimal(bound.denominator),
                Decimal(mark.numerator)/Decimal(mark.denominator))


def _reserved_cash_bounds(rules, quantity, entry_price, exit_price):
    """Cash bounds also cover different fee assets across fills without double fees.

    If b base units pay BUY fees, quote fees c obey c/entry <= q*f-b.
    Therefore debit <= entry*(B+q*f), B=q-b. Proceeds are minimized by
    quote SELL fees at f. Within a lot cell net cash decreases with B; at
    cell boundaries it is linear in the cell index. Its two extreme boundaries
    and the interval endpoints suffice. The debit/proceeds ratio has the same
    endpoint property. All comparisons and floor choices use exact fractions.
    """
    q, fee, step = Fraction(quantity), Fraction(rules.taker_fee_rate), Fraction(rules.step_size)
    entry, exit_ = Fraction(entry_price), Fraction(exit_price)
    lower, upper, width = q*(1-fee), q, step*(1+fee)
    points = [(lower, (lower//width)*step), (upper, (upper//width)*step)]
    first, last = lower//width+1, upper//width
    for cell in {first, last}:
        boundary = cell*width
        if lower < boundary <= upper:
            points.append((boundary, (cell-1)*step))
    values = [(entry*(base+q*fee), sold*exit_*(1-fee)) for base, sold in points]
    net = min(proceeds-debit for debit, proceeds in values)
    ratio = max(debit/proceeds for debit, proceeds in values) if all(p > 0 for _, p in values) else None
    with localcontext() as context:
        context.prec = 96
        context.rounding = ROUND_FLOOR
        net_bound = Decimal(net.numerator)/Decimal(net.denominator)
        context.rounding = ROUND_CEILING
        ratio_bound = Decimal(ratio.numerator)/Decimal(ratio.denominator) if ratio is not None else None
        return net_bound, ratio_bound


def project_exit_cash(*, rules, quantity, entry_price, exit_price, reserve_exit_base_fee=False):
    """Conservative cash points plus continuous fee-rate bounds for reserved dust.

    The four points retain fixed-taker cash lower bounds. Dust admission uses
    the full 0..taker rate interval, including mixed fills and fee discounts.
    A lower fee is not necessarily conservative after SELL lot rounding.
    """
    validate_decimal(quantity,"projected quantity",allow_zero=True)
    validate_decimal(entry_price,"projected entry",strictly_positive=True)
    validate_decimal(exit_price,"projected exit",allow_zero=True)
    if type(reserve_exit_base_fee) is not bool:
        raise TypeError("Explicit exit base-fee reserve boolean required")
    if rules.maker_fee_rate > rules.taker_fee_rate:
        raise ValueError("Advertised maker fee exceeds the reserved taker fee ceiling")
    notional, fee = quantity * entry_price, rules.taker_fee_rate
    cash_bounds = _reserved_cash_bounds(rules, quantity, entry_price, exit_price) if reserve_exit_base_fee else None
    scenarios = []
    for entry_asset in ("quote", "base"):
        base = quantity if entry_asset == "quote" else quantity * (1-fee)
        debit = notional * (1+fee) if entry_asset == "quote" else notional
        bounds = (_reserved_residual_bound(rules, quantity, entry_price, entry_asset=entry_asset)
                  if reserve_exit_base_fee else None)
        for exit_asset in ("quote", "base"):
            sold = rules.quantize_quantity(base/(1+fee) if reserve_exit_base_fee or exit_asset == "base" else base)
            proceeds = sold * exit_price * (1-fee if exit_asset == "quote" else 1)
            residual = base-sold*(1+fee if exit_asset == "base" else 1)
            residual_mark = residual*entry_price
            upper_base, upper_mark = bounds if bounds is not None else (residual, residual_mark)
            scenarios.append(dict(entry_fee_asset=entry_asset,exit_fee_asset=exit_asset,
                sellable=sold >= rules.min_quantity and sold*exit_price >= rules.min_notional,
                sellable_quantity=str(sold),entry_debit_tmn=str(debit),proceeds_tmn=str(proceeds),
                net_at_target_tmn=str(proceeds-debit),residual_base=str(residual),
                net_lower_bound_tmn=str(cash_bounds[0] if cash_bounds is not None else proceeds-debit),
                cash_debit_proceeds_ratio_upper=str(cash_bounds[1]) if cash_bounds is not None and cash_bounds[1] is not None else None,
                residual_mark_tmn=str(residual_mark),
                residual_upper_bound_base=str(upper_base),residual_upper_bound_tmn=str(upper_mark),
                residual_bound_policy="CONTINUOUS_FEE_0_TO_TAKER_V1" if reserve_exit_base_fee else "FIXED_TAKER_POINT",
                residual_within_budget=upper_mark <= min(Decimal(500),notional*Decimal(".005"))))
    return scenarios


def choose_lot_quantity_for_exit(rules, quantity_ceiling, entry_price, exit_price,
                                 reserve_exit_base_fee=True, max_attempts=256):
    """Fit only downward under existing minimums and all four fee-asset cases.

    None means no fit was found within the bounded search, not proof that no
    feasible quantity exists. This is capacity validation, never an ENTER signal.
    """
    if type(rules) is not MarketRules:
        raise TypeError("Exact market rules required for lot fitting")
    validate_decimal(quantity_ceiling, "quantity ceiling", allow_zero=True)
    validate_decimal(entry_price, "entry price", strictly_positive=True)
    validate_decimal(exit_price, "exit price", allow_zero=True)
    if type(reserve_exit_base_fee) is not bool or type(max_attempts) is not int or not 1 <= max_attempts <= 256:
        raise ValueError("Lot fitting requires an explicit boolean and 1..256 attempts")
    quantity = rules.quantize_quantity(quantity_ceiling)
    for _ in range(max_attempts):
        if quantity <= 0 or quantity < rules.min_quantity or quantity*entry_price < rules.min_notional:
            return None
        scenarios = project_exit_cash(rules=rules, quantity=quantity, entry_price=entry_price,
            exit_price=exit_price, reserve_exit_base_fee=reserve_exit_base_fee)
        if all(s["sellable"] and s["residual_within_budget"] for s in scenarios):
            return quantity
        quantity -= rules.step_size
    return None


def assess_target_net(*, forecast, rules, quantity, entry_price, spread_pct, slippage_pct,
                      reserve_exit_base_fee=False, require_central=False):
    """Conditional proceeds at the stated target, NOT expected value or a fill forecast.

    Use the observed full-quantity spread and a downward tick/slippage haircut. Check
    both base/quote fee assets independently; do not charge both for the same fill.
    Residual base is valued at zero because the challenge requires realized TMN.
    """
    if type(require_central) is not bool:
        raise TypeError("Central forecast policy must be an explicit boolean")
    for value, name in ((quantity, "quantity"), (entry_price, "entry price")):
        validate_decimal(value, name, strictly_positive=True)
    for value in (spread_pct, slippage_pct):
        validate_decimal(value, "execution cost fraction")
        if value >= 1:
            raise ValueError("Execution cost fractions must be below one")
    if forecast.symbol != rules.symbol or forecast.target_return_fraction is None:
        raise ValueError("A bound target forecast is required")
    target = forecast.reference_price * (1 + forecast.target_return_fraction)
    exit_price = (target * (1-spread_pct) * (1-slippage_pct) / rules.tick_size).to_integral_value(
        rounding=ROUND_DOWN) * rules.tick_size
    scenarios = project_exit_cash(rules=rules,quantity=quantity,entry_price=entry_price,
        exit_price=exit_price,reserve_exit_base_fee=reserve_exit_base_fee)
    central_scenarios = None
    if require_central:
        central_price = forecast.reference_price * (1 + forecast.return_q50)
        central_exit = (central_price*(1-spread_pct)*(1-slippage_pct)/rules.tick_size).to_integral_value(
            rounding=ROUND_DOWN)*rules.tick_size
        central_scenarios = project_exit_cash(rules=rules,quantity=quantity,entry_price=entry_price,
            exit_price=central_exit,reserve_exit_base_fee=reserve_exit_base_fee)
    central_approved = central_scenarios is None or all(s["sellable"] and Decimal(s["net_lower_bound_tmn"]) > 0
        and (not reserve_exit_base_fee or s["residual_within_budget"]) for s in central_scenarios)
    return dict(policy="CONDITIONAL_TARGET_CENTRAL_NET_V2" if require_central else "CONDITIONAL_TARGET_NET_V1", target_price=str(target),
        exit_price_bound=str(exit_price), spread_fraction=str(spread_pct),
        slippage_fraction=str(slippage_pct), fee_fraction=str(rules.taker_fee_rate), scenarios=scenarios,
        central_scenarios=central_scenarios, central_required=require_central,
        exit_base_fee_reserved=reserve_exit_base_fee,
        approved=central_approved and all(s["sellable"] and Decimal(s["net_lower_bound_tmn"]) > 0
            and (not reserve_exit_base_fee or s["residual_within_budget"]) for s in scenarios))


def evaluate_risk(
    decision: Decision,
    *,
    market_rules: MarketRules,
    policy: RiskPolicy,
    ledger: Ledger,
    current_time: int,
    snapshot_sha256: str,
    candle_close_time: int,
    current_price: Decimal,
    denied_markets: frozenset[str],
    peak_equity: Decimal | None = None,
) -> RiskResult:
    """Evaluate host risk constraints independently of LLM."""
    symbol = market_rules.symbol
    zero = Decimal(0)
    validate_decimal(current_price, "current_price", strictly_positive=True)

    # 1. Action WAIT
    if decision.action == "WAIT":
        return RiskResult(
            approved=True,
            reason="Approved WAIT",
            action="WAIT",
            symbol=symbol,
            quantity=zero,
            price=zero,
            stop_price=None,
            estimated_fee_quote=zero,
        )

    # 2. Symbol cross-check
    if decision.symbol != symbol:
        return RiskResult(
            approved=False,
            reason=f"Rejected: Decision symbol '{decision.symbol}' does not match market rule symbol '{symbol}'",
            action="WAIT",
            symbol=symbol,
            quantity=zero,
            price=zero,
            stop_price=None,
            estimated_fee_quote=zero,
        )

    # 3. Currency quote check (MVP strictly TMN)
    if market_rules.quote_asset != "TMN":
        return RiskResult(
            approved=False,
            reason=f"Rejected: Market quote asset '{market_rules.quote_asset}' is not TMN; multi-currency conversion not verified",
            action="WAIT",
            symbol=symbol,
            quantity=zero,
            price=zero,
            stop_price=None,
            estimated_fee_quote=zero,
        )

    # 4. Denylist verification
    market_pair = f"{market_rules.base_asset}/{market_rules.quote_asset}"
    if symbol in denied_markets or market_pair in denied_markets:
        return RiskResult(
            approved=False,
            reason=f"Rejected: Market {symbol} is denied by policy snapshot",
            action="WAIT",
            symbol=symbol,
            quantity=zero,
            price=zero,
            stop_price=None,
            estimated_fee_quote=zero,
        )

    # 5. Snapshot hash & cutoff consistency
    if decision.snapshot_sha256 != snapshot_sha256:
        return RiskResult(
            approved=False,
            reason="Rejected: Snapshot hash mismatch between decision and host context",
            action="WAIT",
            symbol=symbol,
            quantity=zero,
            price=zero,
            stop_price=None,
            estimated_fee_quote=zero,
        )
    if decision.cutoff != candle_close_time:
        return RiskResult(
            approved=False,
            reason="Rejected: Decision cutoff timestamp does not match candle close time",
            action="WAIT",
            symbol=symbol,
            quantity=zero,
            price=zero,
            stop_price=None,
            estimated_fee_quote=zero,
        )

    # 6. Future timestamp or negative latency check
    if current_time < candle_close_time:
        return RiskResult(
            approved=False,
            reason=f"Rejected: Future or negative latency timestamp (current_time {current_time} < candle_close {candle_close_time})",
            action="WAIT",
            symbol=symbol,
            quantity=zero,
            price=zero,
            stop_price=None,
            estimated_fee_quote=zero,
        )

    # 7. Data freshness
    if (current_time - candle_close_time > policy.max_stale_seconds) and decision.action == "ENTER":
        return RiskResult(
            approved=False,
            reason="Rejected: Data is stale for new ENTER orders",
            action="WAIT",
            symbol=symbol,
            quantity=zero,
            price=zero,
            stop_price=None,
            estimated_fee_quote=zero,
        )

    # 8. Deadline check
    if (
        current_time >= policy.deadline_utc - policy.min_seconds_before_deadline
    ) and decision.action == "ENTER":
        return RiskResult(
            approved=False,
            reason="Rejected: Competition deadline approaching; new entries closed",
            action="WAIT",
            symbol=symbol,
            quantity=zero,
            price=zero,
            stop_price=None,
            estimated_fee_quote=zero,
        )

    # 9. Portfolio drawdown kill-switch with durable metadata persistence
    from royin.residuals import quarantined_residuals
    residuals = quarantined_residuals(ledger) if ledger.get_meta("fresh_permit") else {}
    if decision.action == "ENTER" and market_rules.base_asset in residuals:
        return RiskResult(False,"A quarantined residual cannot be merged into a new position","WAIT",symbol,zero,zero,None,zero)
    if decision.action == "ENTER" and ledger.get_meta("portfolio") and any(
        asset != market_rules.quote_asset and asset not in residuals and balance.total > 0
        for asset,balance in ledger.get_all_balances().items()
    ):
        return RiskResult(False, "One-position portfolio is already invested", "WAIT", symbol, zero, zero, None, zero)
    if residuals:
        # Retain actual balances/cost basis. This is a conservative liquid-value
        # risk calculation, never a declaration that residual coins became cash.
        current_equity = ledger.get_balance(market_rules.quote_asset).total
        for asset,balance in ledger.get_all_balances().items():
            if balance.total and asset != market_rules.quote_asset and asset not in residuals:
                if asset != market_rules.base_asset:
                    raise ValueError("A held asset lacks a valuation price")
                current_equity += balance.total*current_price
    else:
        current_equity = ledger.get_equity({symbol:current_price},quote_currency=market_rules.quote_asset)
    if peak_equity is None:
        saved_peak = ledger.get_meta(f"peak_equity_{market_rules.quote_asset}")
        if saved_peak:
            peak_equity = Decimal(saved_peak)

    if peak_equity is None or current_equity > peak_equity:
        peak_equity = current_equity
        ledger.set_meta(f"peak_equity_{market_rules.quote_asset}", str(peak_equity))

    if peak_equity > zero:
        drawdown = (peak_equity - current_equity) / peak_equity
        if drawdown >= policy.max_drawdown_pct and decision.action == "ENTER":
            return RiskResult(
                approved=False,
                reason=f"Rejected: Portfolio drawdown {drawdown:.2%} breaches limit {policy.max_drawdown_pct:.2%}",
                action="WAIT",
                symbol=symbol,
                quantity=zero,
                price=zero,
                stop_price=None,
                estimated_fee_quote=zero,
            )

    with ledger.connection() as db:
        pending = db.execute(
            "SELECT 1 FROM order_intents WHERE status NOT IN "
            "('FILLED','CANCELED','PARTIALLY_FILLED_CANCELED','REJECTED') LIMIT 1",
        ).fetchone()
    if pending:
        return RiskResult(
            False,
            "Rejected: pending order requires reconciliation before another intent",
            "WAIT",
            symbol,
            zero,
            zero,
            None,
            zero,
        )

    # 10. Action ENTER (Spot Buy)
    if decision.action == "ENTER":
        if ledger.get_meta("audit_failed") == "1" or ledger.get_meta("entry_block_reason"):
            return RiskResult(False, "Host entry gate is closed", "WAIT", symbol, zero, zero, None, zero)
        free_cash = ledger.get_balance(market_rules.quote_asset).free
        current_base_bal = ledger.get_balance(market_rules.base_asset)
        current_exposure = current_base_bal.total * current_price
        remaining_exposure = policy.max_exposure_tmn - current_exposure

        if remaining_exposure <= zero:
            return RiskResult(
                approved=False,
                reason="Rejected: Max portfolio exposure already reached",
                action="WAIT",
                symbol=symbol,
                quantity=zero,
                price=zero,
                stop_price=None,
                estimated_fee_quote=zero,
            )

        spend_budget = min(free_cash, policy.max_order_tmn, remaining_exposure)
        if spend_budget < market_rules.min_notional:
            return RiskResult(
                approved=False,
                reason=f"Rejected: Available spend budget {spend_budget} is less than min_notional {market_rules.min_notional}",
                action="WAIT",
                symbol=symbol,
                quantity=zero,
                price=zero,
                stop_price=None,
                estimated_fee_quote=zero,
            )

        target_price = market_rules.quantize_price(current_price)
        raw_qty = spend_budget / (target_price * (Decimal(1) + market_rules.taker_fee_rate))
        target_qty = market_rules.quantize_quantity(raw_qty, round_down=True)

        if target_qty < market_rules.min_quantity:
            return RiskResult(
                approved=False,
                reason=f"Rejected: Order quantity {target_qty} below min_quantity {market_rules.min_quantity}",
                action="WAIT",
                symbol=symbol,
                quantity=zero,
                price=zero,
                stop_price=None,
                estimated_fee_quote=zero,
            )

        notional = target_qty * target_price
        if notional < market_rules.min_notional:
            return RiskResult(
                approved=False,
                reason=f"Rejected: Order notional {notional} below min_notional {market_rules.min_notional}",
                action="WAIT",
                symbol=symbol,
                quantity=zero,
                price=zero,
                stop_price=None,
                estimated_fee_quote=zero,
            )

        # Post-fee sellability test
        net_base_after_fee = target_qty * (Decimal(1) - market_rules.taker_fee_rate)
        sellable_qty = market_rules.quantize_quantity(net_base_after_fee, round_down=True)
        if (
            sellable_qty < market_rules.min_quantity
            or (sellable_qty * target_price) < market_rules.min_notional
        ):
            return RiskResult(
                approved=False,
                reason="Rejected: Post-fee balance would produce unsellable dust",
                action="WAIT",
                symbol=symbol,
                quantity=zero,
                price=zero,
                stop_price=None,
                estimated_fee_quote=zero,
            )

        stop_price = market_rules.quantize_price(target_price * (Decimal(1) - policy.stop_loss_pct))
        est_fee = notional * market_rules.taker_fee_rate

        return RiskResult(
            approved=True,
            reason="Approved ENTER within risk policy bounds",
            action="ENTER",
            symbol=symbol,
            quantity=target_qty,
            price=target_price,
            stop_price=stop_price,
            estimated_fee_quote=est_fee,
        )

    # 11. Action EXIT (Spot Sell)
    if decision.action == "EXIT":
        available_base = ledger.get_balance(market_rules.base_asset).free
        target_qty = market_rules.quantize_quantity(available_base, round_down=True)

        if target_qty < market_rules.min_quantity:
            return RiskResult(
                approved=False,
                reason="Rejected: Cannot SELL with 0 available base balance",
                action="WAIT",
                symbol=symbol,
                quantity=zero,
                price=zero,
                stop_price=None,
                estimated_fee_quote=zero,
            )

        target_price = market_rules.quantize_price(current_price)
        notional = target_qty * target_price

        if notional < market_rules.min_notional:
            return RiskResult(
                approved=False,
                reason=f"Rejected: Residual balance notional {notional} is below min_notional {market_rules.min_notional}",
                action="WAIT",
                symbol=symbol,
                quantity=zero,
                price=zero,
                stop_price=None,
                estimated_fee_quote=zero,
            )

        est_fee = notional * market_rules.taker_fee_rate

        return RiskResult(
            approved=True,
            reason="Approved EXIT (liquidating available base balance)",
            action="EXIT",
            symbol=symbol,
            quantity=target_qty,
            price=target_price,
            stop_price=None,
            estimated_fee_quote=est_fee,
        )

    return RiskResult(
        approved=False,
        reason=f"Rejected: Unknown action '{decision.action}'",
        action="WAIT",
        symbol=symbol,
        quantity=zero,
        price=zero,
        stop_price=None,
        estimated_fee_quote=zero,
    )
