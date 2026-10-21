"""Host risk gates, market rules, exposure controls, and post-fee sellability checks."""

from dataclasses import dataclass
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
        if not self.symbol or not isinstance(self.symbol, str):
            raise ValueError("symbol must be a non-empty string")
        if not self.base_asset or not isinstance(self.base_asset, str):
            raise ValueError("base_asset must be a non-empty string")
        if not self.quote_asset or not isinstance(self.quote_asset, str):
            raise ValueError("quote_asset must be a non-empty string")

    def quantize_price(self, price: Decimal) -> Decimal:
        validate_decimal(price, "price", strictly_positive=True)
        return (price / self.tick_size).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * self.tick_size

    def quantize_quantity(self, quantity: Decimal, round_down: bool = True) -> Decimal:
        validate_decimal(quantity, "quantity", allow_zero=True)
        rounding = ROUND_DOWN if round_down else ROUND_HALF_UP
        return (quantity / self.step_size).quantize(Decimal("1"), rounding=rounding) * self.step_size


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
    if (current_time >= policy.deadline_utc - policy.min_seconds_before_deadline) and decision.action == "ENTER":
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
    current_equity = ledger.get_equity({symbol: current_price}, quote_currency=market_rules.quote_asset)
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

    # 10. Action ENTER (Spot Buy)
    if decision.action == "ENTER":
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

        if target_qty <= zero:
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
