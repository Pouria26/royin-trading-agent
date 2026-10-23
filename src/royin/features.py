"""Causal feature extraction and deterministic evidence generation for AI decision."""

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, Inexact, localcontext

from royin.ledger import validate_decimal
from royin.market_data import Candle, CandleSeries


@dataclass(frozen=True)
class FeatureSnapshot:
    """Deterministic, causal market state at a specific cutoff timestamp."""
    symbol: str
    cutoff: int
    interval_seconds: int
    closed_bars_count: int
    last_close: Decimal
    trend_sma_fast: Decimal
    trend_sma_slow: Decimal
    rsi_14: Decimal
    atr_14: Decimal
    volume_ratio: Decimal
    current_position_base: Decimal
    available_tmn_cash: Decimal
    evidences: dict[str, str]
    snapshot_sha256: str

    def to_canonical_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "cutoff": self.cutoff,
            "interval_seconds": self.interval_seconds,
            "closed_bars_count": self.closed_bars_count,
            "last_close": str(self.last_close),
            "trend_sma_fast": str(self.trend_sma_fast),
            "trend_sma_slow": str(self.trend_sma_slow),
            "rsi_14": str(self.rsi_14),
            "atr_14": str(self.atr_14),
            "volume_ratio": str(self.volume_ratio),
            "current_position_base": str(self.current_position_base),
            "available_tmn_cash": str(self.available_tmn_cash),
            "evidences": dict(sorted(self.evidences.items())),
        }

    def verify_hash(self) -> bool:
        """Verify that the stored SHA-256 hash strictly matches the canonical serialization."""
        raw_dict = self.to_canonical_dict()
        canonical_json = json.dumps(raw_dict, sort_keys=True, separators=(",", ":")).encode("utf-8")
        computed_hash = hashlib.sha256(canonical_json).hexdigest()
        return computed_hash == self.snapshot_sha256


def compute_sma(candles: Sequence[Candle], period: int) -> Decimal:
    if len(candles) < period or period <= 0:
        raise ValueError(f"Need at least {period} candles for SMA")
    with localcontext() as ctx:
        ctx.prec = 36
        ctx.traps[Inexact] = False
        return sum((c.close for c in candles[-period:]), Decimal(0)) / Decimal(period)


def compute_atr(candles: Sequence[Candle], period: int = 14) -> Decimal:
    if len(candles) <= period or period <= 0:
        raise ValueError(f"Need at least {period + 1} candles for ATR")
    tr_list = []
    for i in range(len(candles) - period, len(candles)):
        curr = candles[i]
        prev = candles[i - 1]
        tr = max(
            curr.high - curr.low,
            abs(curr.high - prev.close),
            abs(curr.low - prev.close),
        )
        tr_list.append(tr)
    with localcontext() as ctx:
        ctx.prec = 36
        ctx.traps[Inexact] = False
        return sum(tr_list, Decimal(0)) / Decimal(period)


def compute_rsi(candles: Sequence[Candle], period: int = 14) -> Decimal:
    if len(candles) <= period or period <= 0:
        raise ValueError(f"Need at least {period + 1} candles for RSI")
    gains = []
    losses = []
    for i in range(len(candles) - period, len(candles)):
        change = candles[i].close - candles[i - 1].close
        if change > 0:
            gains.append(change)
            losses.append(Decimal(0))
        else:
            gains.append(Decimal(0))
            losses.append(abs(change))

    with localcontext() as ctx:
        ctx.prec = 36
        ctx.traps[Inexact] = False
        avg_gain = sum(gains, Decimal(0)) / Decimal(period)
        avg_loss = sum(losses, Decimal(0)) / Decimal(period)

        if avg_gain == Decimal(0) and avg_loss == Decimal(0):
            return Decimal(50)  # Neutral RSI on zero-change flat market
        if avg_loss == Decimal(0):
            return Decimal(100)
        if avg_gain == Decimal(0):
            return Decimal(0)

        rs = avg_gain / avg_loss
        return Decimal(100) - (Decimal(100) / (Decimal(1) + rs))


def compute_bollinger_bands(
    candles: Sequence[Candle],
    period: int = 20,
    num_std: Decimal = Decimal(2),
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """Compute Bollinger Bands (middle, upper, lower, band_width_pct) causally with Decimal."""
    if len(candles) < period or period <= 0:
        raise ValueError(f"Need at least {period} candles for Bollinger Bands")
    closes = [c.close for c in candles[-period:]]
    with localcontext() as ctx:
        ctx.prec = 36
        ctx.traps[Inexact] = False
        middle = sum(closes, Decimal(0)) / Decimal(period)
        variance = sum(((c - middle) ** 2 for c in closes), Decimal(0)) / Decimal(period)
        std_dev = variance.sqrt()
        upper = middle + (num_std * std_dev)
        lower = middle - (num_std * std_dev)
        width_pct = ((upper - lower) / middle) if middle > Decimal(0) else Decimal(0)
        return middle, upper, lower, width_pct


def compute_wick_ratios(candle: Candle) -> tuple[Decimal, Decimal, Decimal]:
    """Compute upper wick ratio, body ratio, and lower wick ratio of a single candle."""
    candle_range = candle.high - candle.low
    if candle_range <= Decimal(0):
        return Decimal(0), Decimal(1), Decimal(0)
    with localcontext() as ctx:
        ctx.prec = 36
        ctx.traps[Inexact] = False
        upper_wick = candle.high - max(candle.open, candle.close)
        lower_wick = min(candle.open, candle.close) - candle.low
        body = abs(candle.close - candle.open)
        return (
            upper_wick / candle_range,
            body / candle_range,
            lower_wick / candle_range,
        )


def extract_features(
    series: CandleSeries,
    symbol: str,
    *,
    cutoff: int,
    current_position_base: Decimal = Decimal(0),
    available_tmn_cash: Decimal = Decimal("5000000"),
    fast_period: int = 10,
    slow_period: int = 30,
) -> FeatureSnapshot:
    """Extract causal features up to cutoff with strictly closed candles and gap validation."""
    step = series.interval_seconds
    if type(step) is not int or step <= 0:
        raise ValueError("Invalid interval or incomplete aggregate")
    if type(cutoff) is not int or cutoff <= 0:
        raise ValueError("Cutoff must be a positive integer timestamp")
    if any(bucket + step <= cutoff for bucket in series.incomplete_bins):
        raise ValueError("Incomplete aggregate before cutoff")

    validate_decimal(current_position_base, "current_position_base", allow_zero=True)
    validate_decimal(available_tmn_cash, "available_tmn_cash", allow_zero=True)

    # Strictly include candles that closed AT OR BEFORE cutoff
    valid_candles = [c for c in series.candles if c.open_time + step <= cutoff]
    if len(valid_candles) < slow_period + 1:
        raise ValueError(
            f"Insufficient closed candles before cutoff {cutoff}: "
            f"got {len(valid_candles)}, need at least {slow_period + 1}"
        )

    # Check for gaps or out-of-order candles
    for i in range(1, len(valid_candles)):
        expected_open = valid_candles[i - 1].open_time + step
        if valid_candles[i].open_time != expected_open:
            raise ValueError(
                f"Candle series contains gap or out-of-order timestamp at index {i}: "
                f"expected open {expected_open}, got {valid_candles[i].open_time}"
            )

    last_candle = valid_candles[-1]
    from royin.datasets import validate_candles

    validate_candles(valid_candles, step, now=cutoff)
    if cutoff - (last_candle.open_time + step) >= step:
        raise ValueError("Stale closed candles")
    last_close = last_candle.close

    sma_fast = compute_sma(valid_candles, fast_period)
    sma_slow = compute_sma(valid_candles, slow_period)
    rsi_14 = compute_rsi(valid_candles, 14)
    atr_14 = compute_atr(valid_candles, 14)

    # Volume ratio: last candle volume vs average volume of last 20 candles
    vol_period = min(20, len(valid_candles))
    with localcontext() as ctx:
        ctx.prec = 36
        ctx.traps[Inexact] = False
        avg_vol = sum((c.volume for c in valid_candles[-vol_period:]), Decimal(0)) / Decimal(vol_period)
        vol_ratio = (last_candle.volume / avg_vol) if avg_vol > 0 else Decimal(1)

    # Generate deterministic evidence dictionary
    evidences = {}
    evidences["EV_DATA_FRESH"] = f"Candle closed at {last_candle.open_time + step}"

    # Close location weighted by base volume is a pressure proxy, not observed aggressor flow.
    with localcontext() as ctx:
        ctx.prec = 36
        ctx.traps[Inexact] = False
        window = valid_candles[-20:]
        volume = sum((c.volume for c in window), Decimal(0))
        pressure = (sum((((2*c.close-c.high-c.low)/(c.high-c.low) if c.high > c.low else Decimal(0))
            * c.volume for c in window), Decimal(0))/volume) if volume else None
    direction = "UNAVAILABLE" if pressure is None else (
        "POSITIVE" if pressure > 0 else "NEGATIVE" if pressure < 0 else "NEUTRAL")
    evidences["EV_VOLUME_PRESSURE_"+direction] = (
        f"20 closed-bar close-location volume proxy={pressure}; range [-1,1]; "
        "not measured buyer/seller aggressor flow or net capital inflow"
    )

    if last_close > sma_slow and sma_fast > sma_slow:
        evidences["EV_TREND_BULLISH"] = (
            f"Price {last_close} and fast SMA {sma_fast:.2f} are above slow SMA {sma_slow:.2f}"
        )
    elif last_close < sma_slow and sma_fast < sma_slow:
        evidences["EV_TREND_BEARISH"] = (
            f"Price {last_close} and fast SMA {sma_fast:.2f} are below slow SMA {sma_slow:.2f}"
        )
    else:
        evidences["EV_TREND_NEUTRAL"] = (
            f"Price {last_close} oscillating around slow SMA {sma_slow:.2f}"
        )

    if rsi_14 < Decimal(30):
        evidences["EV_RSI_OVERSOLD"] = f"RSI is oversold at {rsi_14:.2f} (< 30)"
    elif rsi_14 > Decimal(70):
        evidences["EV_RSI_OVERBOUGHT"] = f"RSI is overbought at {rsi_14:.2f} (> 70)"
    else:
        evidences["EV_RSI_NORMAL"] = f"RSI is neutral at {rsi_14:.2f}"

    if vol_ratio >= Decimal("1.5"):
        evidences["EV_VOLUME_HIGH"] = f"Volume is {vol_ratio:.2f}x of recent average"
    else:
        evidences["EV_VOLUME_NORMAL"] = f"Volume ratio {vol_ratio:.2f}x is normal"

    if current_position_base > Decimal(0):
        evidences["EV_POSITION_LONG"] = f"Holding active base balance: {current_position_base}"
    else:
        evidences["EV_POSITION_FLAT"] = "No open position currently held"

    if len(valid_candles) >= 20:
        _, _, _, bb_width_pct = compute_bollinger_bands(valid_candles, 20)
        if bb_width_pct >= Decimal("0.015"):
            evidences["EV_BB_EXPANDING"] = f"Bollinger band width expanding at {bb_width_pct * 100:.2f}% (breakout volatility)"
        else:
            evidences["EV_BB_SQUEEZE"] = f"Bollinger band width compressed at {bb_width_pct * 100:.2f}% (low volatility squeeze)"

    upper_wick_ratio, body_ratio, _ = compute_wick_ratios(last_candle)
    if upper_wick_ratio >= Decimal("0.35"):
        evidences["EV_WICK_REJECTION"] = f"Upper wick rejection detected ({upper_wick_ratio * 100:.1f}% of candle range)"
    elif body_ratio >= Decimal("0.55") and last_candle.close > last_candle.open:
        evidences["EV_STRONG_BULLISH_BODY"] = f"Strong bullish candle body ({body_ratio * 100:.1f}% of candle range)"

    if current_position_base > Decimal(0) and (
        upper_wick_ratio >= Decimal("0.35") or (vol_ratio < Decimal("0.80") and last_close <= sma_fast)
    ):
        evidences["EV_MOMENTUM_STALL"] = "Holding position but forward momentum has stalled or met selling wick rejection"

    # Canonical snapshot hash
    raw_dict = {
        "symbol": symbol,
        "cutoff": cutoff,
        "interval_seconds": step,
        "closed_bars_count": len(valid_candles),
        "last_close": str(last_close),
        "trend_sma_fast": str(sma_fast),
        "trend_sma_slow": str(sma_slow),
        "rsi_14": str(rsi_14),
        "atr_14": str(atr_14),
        "volume_ratio": str(vol_ratio),
        "current_position_base": str(current_position_base),
        "available_tmn_cash": str(available_tmn_cash),
        "evidences": dict(sorted(evidences.items())),
    }
    canonical_json = json.dumps(raw_dict, sort_keys=True, separators=(",", ":")).encode("utf-8")
    snapshot_hash = hashlib.sha256(canonical_json).hexdigest()

    return FeatureSnapshot(
        symbol=symbol,
        cutoff=cutoff,
        interval_seconds=step,
        closed_bars_count=len(valid_candles),
        last_close=last_close,
        trend_sma_fast=sma_fast,
        trend_sma_slow=sma_slow,
        rsi_14=rsi_14,
        atr_14=atr_14,
        volume_ratio=vol_ratio,
        current_position_base=current_position_base,
        available_tmn_cash=available_tmn_cash,
        evidences=evidences,
        snapshot_sha256=snapshot_hash,
    )
