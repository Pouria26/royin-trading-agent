"""Exact Wallex OHLCV decoding and causal, complete-bar aggregation."""

import json
from dataclasses import dataclass
from decimal import Decimal, Inexact, InvalidOperation, localcontext
from itertools import pairwise


def decimal_number(value, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError("Expected an exact decimal, never a float or boolean")
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise ValueError("Invalid decimal") from None
    if not number.is_finite() or number < 0 or (positive and number == 0):
        raise ValueError("Expected a finite nonnegative decimal")
    if len(number.as_tuple().digits) > 128 or abs(number.as_tuple().exponent) > 128:
        raise ValueError("Decimal exceeds the host's supported precision/range")
    return number


def decode_json(raw):
    def reject_constant(_value):
        raise ValueError("Nonstandard JSON number")

    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    return json.loads(
        raw, parse_float=Decimal, parse_constant=reject_constant, object_pairs_hook=unique_keys,
    )


@dataclass(frozen=True)
class Candle:
    open_time: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal  # Base units assumed for research; source semantics must be verified before sizing.


@dataclass(frozen=True)
class CandleSeries:
    candles: tuple[Candle, ...]
    interval_seconds: int
    incomplete_bins: tuple[int, ...] = ()


def parse_history(payload, *, start, end, interval_seconds, cutoff):
    """Accept [start,end), dropping bars not closed by cutoff; reject gaps/cadence drift."""
    if any(type(v) is not int for v in (start, end, interval_seconds, cutoff)) or not (
        0 <= start < end and interval_seconds > 0 and cutoff >= start
    ):
        raise ValueError("Invalid history window")
    if start % interval_seconds or end % interval_seconds:
        raise ValueError("Window is not aligned to the source interval")
    if not isinstance(payload, dict) or payload.get("s") != "ok":
        raise ValueError("History unavailable")
    keys = ("t", "o", "h", "l", "c", "v")
    if any(not isinstance(payload.get(key), list) for key in keys):
        raise ValueError("Missing history arrays")
    if len({len(payload[key]) for key in keys}) != 1:
        raise ValueError("History array lengths differ")
    if len(payload["t"]) > 100_001 or (end - start) // interval_seconds > 100_000:
        raise ValueError("History window exceeds the host's 100000-bar limit")
    times = payload["t"]
    if any(type(t) is not int or not start <= t <= end for t in times):
        raise ValueError("Invalid or out-of-window timestamp")
    if any(b <= a for a, b in pairwise(times)):
        raise ValueError("Duplicate or unordered timestamps")
    closed_end = min(end, cutoff // interval_seconds * interval_seconds)
    selected = [i for i, t in enumerate(times) if start <= t < closed_end]
    if [times[i] for i in selected] != list(range(start, closed_end, interval_seconds)):
        raise ValueError("Missing candles or unexpected cadence; no forward fill")
    candles = []
    for i in selected:
        op, high, low, close = (
            decimal_number(payload[key][i], positive=True) for key in ("o", "h", "l", "c")
        )
        volume = decimal_number(payload["v"][i])
        if not low <= min(op, close) <= max(op, close) <= high:
            raise ValueError("Inconsistent OHLC")
        candles.append(Candle(times[i], op, high, low, close, volume))
    return CandleSeries(tuple(candles), interval_seconds)


def aggregate_closed(series, interval_seconds):
    """UTC-aligned bins: incomplete edges are flagged and never supplied as model input."""
    source_step = series.interval_seconds
    if type(source_step) is not int or source_step <= 0:
        raise ValueError("Invalid source interval")
    if type(interval_seconds) is not int or interval_seconds < source_step or (
        interval_seconds % source_step
    ):
        raise ValueError("Target interval must be a multiple of source interval")
    if any(b.open_time - a.open_time != source_step for a, b in pairwise(series.candles)):
        raise ValueError("Cannot aggregate a gapped series")
    groups = {}
    for candle in series.candles:
        bucket = candle.open_time // interval_seconds * interval_seconds
        groups.setdefault(bucket, []).append(candle)
    complete, incomplete = [], list(series.incomplete_bins)
    for bucket, candles in groups.items():
        if [c.open_time for c in candles] != list(
            range(bucket, bucket + interval_seconds, source_step)
        ):
            incomplete.append(bucket)
            continue
        with localcontext() as context:
            context.prec = 128
            context.traps[Inexact] = True  # Refuse rounding rather than silently lose source volume.
            volume = sum((c.volume for c in candles), Decimal(0))
        complete.append(Candle(
            bucket, candles[0].open, max(c.high for c in candles), min(c.low for c in candles),
            candles[-1].close, volume,
        ))
    return CandleSeries(tuple(complete), interval_seconds, tuple(incomplete))
