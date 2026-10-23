"""Host risk gates, market rules, exposure controls, and post-fee sellability checks."""

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
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


def assess_target_net(*, forecast, rules, quantity, entry_price, spread_pct, slippage_pct):
    """Conditional proceeds at the stated target, NOT expected value or a fill forecast.

    Use the observed full-quantity spread and a downward tick/slippage haircut. Check
    both base/quote fee assets independently; do not charge both for the same fill.
    Residual base is valued at zero because the challenge requires realized TMN.
    """
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
    notional, fee = quantity * entry_price, rules.taker_fee_rate
    scenarios = []
    for entry_asset in ("quote", "base"):
        base = quantity if entry_asset == "quote" else quantity * (1-fee)
        debit = notional * (1+fee) if entry_asset == "quote" else notional
        for exit_asset in ("quote", "base"):
            sold = rules.quantize_quantity(base if exit_asset == "quote" else base/(1+fee))
            proceeds = sold * exit_price * (1-fee if exit_asset == "quote" else 1)
            sellable = sold >= rules.min_quantity and sold * exit_price >= rules.min_notional
            scenarios.append(dict(entry_fee_asset=entry_asset, exit_fee_asset=exit_asset,
                sellable=sellable, sellable_quantity=str(sold), entry_debit_tmn=str(debit),
                proceeds_tmn=str(proceeds), net_at_target_tmn=str(proceeds-debit)))
    return dict(policy="CONDITIONAL_TARGET_NET_V1", target_price=str(target),
        exit_price_bound=str(exit_price), spread_fraction=str(spread_pct),
        slippage_fraction=str(slippage_pct), fee_fraction=str(fee), scenarios=scenarios,
        approved=all(s["sellable"] and Decimal(s["net_at_target_tmn"]) > 0 for s in scenarios))


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
    if decision.action == "ENTER" and ledger.get_meta("portfolio") and any(
        asset != market_rules.quote_asset and balance.total > 0 for asset,balance in ledger.get_all_balances().items()
    ):
        return RiskResult(False, "One-position portfolio is already invested", "WAIT", symbol, zero, zero, None, zero)
    current_equity = ledger.get_equity(
        {symbol: current_price}, quote_currency=market_rules.quote_asset
    )
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
