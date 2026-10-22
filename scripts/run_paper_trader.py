"""Causal public scanner components; financial CLI awaits the execution-owner contract."""

import argparse
import hashlib
import json
import re
import time
import urllib.request
from dataclasses import dataclass
from decimal import Decimal, DecimalException, Inexact, localcontext
from itertools import pairwise
from pathlib import Path
from urllib.parse import urlencode

from royin.decision import EntryOpportunityContext
from royin.features import FeatureSnapshot, extract_features
from royin.market_data import (
    Candle,
    aggregate_closed,
    decimal_number,
    decode_json,
    parse_history,
)
from royin.markets import eligible_markets, load_restrictions, parse_catalog

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config/wallex-credit-market-policy.json"


@dataclass(frozen=True)
class MarketShortlistRow:
    symbol: str
    turnover_tmn: Decimal
    quote_to_tmn: Decimal
    received_at: int
    catalog_sha256: str


def _fresh(timestamp, cutoff, max_age):
    return type(timestamp) is int and type(cutoff) is int and 0 <= cutoff - timestamp <= max_age


def shortlist_markets(payload, *, account_symbols, cutoff, received_at,
                      account_as_of=None, limit=3, min_turnover_tmn=Decimal("100000000")):
    """All eligible catalog rows, ranked by quote turnover converted to TMN at this cutoff."""
    if type(limit) is not int or not 1 <= limit <= 5:
        raise ValueError("Shortlist cap must be 1..5")
    decimal_number(min_turnover_tmn, positive=True)
    if not _fresh(received_at, cutoff, 60) or not _fresh(account_as_of, cutoff, 3600):
        return ()
    catalog = parse_catalog(payload)
    eligible = eligible_markets(catalog, load_restrictions(POLICY_PATH), account_symbols=account_symbols)
    rows = {row["symbol"]: row for row in payload["result"]["markets"]}
    digest = hashlib.sha256(json.dumps(payload, default=str, sort_keys=True).encode()).hexdigest()
    conversion = None
    if "USDTTMN" in rows:
        conversion = decimal_number(rows["USDTTMN"].get("price"), positive=True)
    candidates = []
    for symbol in sorted(eligible):
        market, row = catalog[symbol], rows[symbol]
        if market.base_asset == "TON" or row.get("is_active") is False:
            continue
        rate = Decimal(1) if market.quote_asset == "TMN" else conversion
        if rate is None:
            continue
        try:
            with localcontext() as context:
                context.prec = 128
                context.traps[Inexact] = True
                turnover = decimal_number(row.get("quote_volume_24h")) * rate
            decimal_number(row.get("price"), positive=True)
        except (ValueError, DecimalException):
            continue
        if turnover >= min_turnover_tmn:
            candidates.append(MarketShortlistRow(symbol, turnover, rate, received_at, digest))
    return tuple(sorted(candidates, key=lambda row: (-row.turnover_tmn, row.symbol))[:limit])


@dataclass(frozen=True)
class ScanCandidate:
    snapshot: FeatureSnapshot
    score: Decimal
    opportunity: EntryOpportunityContext


def build_candidate_batch(shortlist, *, series_by_symbol, depth_by_symbol, cutoff,
                          candle_received_at, depth_received_at, round_trip_fee_pct,
                          min_depth_tmn, max_spread_pct, available_tmn_cash, limit=3,
                          snapshot_cutoff=None):
    """Bounded expensive stage: every liquidity-valid candidate, ordered for cheap review.

    Host ordering is not a selection. The model chooses one symbol or NO_TRADE; ATR and
    the old score are ordering evidence only, never hard eligibility gates.
    """
    decimal_number(round_trip_fee_pct)
    for amount in (min_depth_tmn, max_spread_pct):
        decimal_number(amount, positive=True)
    if type(limit) is not int or not 1 <= limit <= 5:
        raise ValueError("Invalid batch limit")
    if round_trip_fee_pct >= 1 or max_spread_pct >= 1 or len(shortlist) > 5:
        raise ValueError("Invalid scanner limits")
    snapshot_cutoff = cutoff if snapshot_cutoff is None else snapshot_cutoff
    if type(snapshot_cutoff) is not int or not 0 < snapshot_cutoff <= cutoff:
        raise ValueError("Invalid snapshot cutoff")
    accepted = []
    for row in shortlist:
        if not all(_fresh(t, cutoff, 60) for t in (
            row.received_at, candle_received_at.get(row.symbol), depth_received_at.get(row.symbol),
        )):
            continue
        try:
            series = series_by_symbol[row.symbol]
            closed_at = series.candles[-1].open_time + series.interval_seconds
            # One uniform cutoff: the model must compare candidates from the same instant.
            if closed_at != snapshot_cutoff:
                continue
            snapshot = extract_features(series, row.symbol, cutoff=snapshot_cutoff,
                                        available_tmn_cash=available_tmn_cash)
            depth = depth_by_symbol[row.symbol]
            if depth.get("success") is not True:
                continue
            book = depth["result"]
            bids, asks = book["bid"], book["ask"]
            if not bids or not asks or len(bids) > 100 or len(asks) > 100:
                continue
            def levels(rows):
                return [(decimal_number(r["price"], positive=True),
                         decimal_number(r["quantity"], positive=True)) for r in rows]
            bids, asks = levels(bids), levels(asks)
            if any(a[0] <= b[0] for a, b in pairwise(bids)) or (
                any(a[0] >= b[0] for a, b in pairwise(asks))
            ):
                continue
            bid, ask = bids[0][0], asks[0][0]
            spread = (ask - bid) / bid
            if not 0 <= spread <= max_spread_pct:
                continue
            with localcontext() as context:
                context.prec = 128
                context.traps[Inexact] = True
                bid_depth = sum((p*q*row.quote_to_tmn for p, q in bids if p >= bid*(1-max_spread_pct)), Decimal(0))
                ask_depth = sum((p*q*row.quote_to_tmn for p, q in asks if p <= ask*(1+max_spread_pct)), Decimal(0))
            if min(bid_depth, ask_depth) < min_depth_tmn:
                continue
            # Ordering evidence only; the entry model decides whether it is attractive.
            score = snapshot.atr_14 / snapshot.last_close - round_trip_fee_pct - spread
            opportunity = EntryOpportunityContext(spread_pct=spread, round_trip_fee_pct=round_trip_fee_pct,
                bid_depth_tmn=bid_depth, ask_depth_tmn=ask_depth, catalog_sha256=row.catalog_sha256,
                catalog_received_at=row.received_at, candle_received_at=candle_received_at[row.symbol],
                depth_received_at=depth_received_at[row.symbol], observed_at=cutoff)
            accepted.append(ScanCandidate(snapshot, score, opportunity))
        except (ValueError, KeyError, TypeError, IndexError, DecimalException):
            continue
    return tuple(sorted(accepted, key=lambda c: (-c.score, c.snapshot.symbol))[:limit])


class ScannerPublicFeed:
    """Public GET only, one attempt owner, bounded responses and age-limited cache."""

    def __init__(self, capture_dir, *, max_requests=16):
        if type(max_requests) is not int or not 1 <= max_requests <= 32:
            raise ValueError("GET cap must be 1..32")
        self.capture_dir = Path(capture_dir)
        self.max_requests, self.requests = max_requests, 0
        self.cache, self.captures = {}, []
        self.last_request = None

    def get(self, endpoint, params, *, cutoff):
        if endpoint not in ("/hector/web/v1/markets", "/v1/udf/history", "/v1/depth"):
            raise ValueError("Public endpoint outside scanner allowlist")
        symbol = params.get("symbol")
        if symbol is not None and not re.fullmatch(r"[A-Z0-9]+(?:TMN|USDT)", symbol):
            raise ValueError("Invalid symbol")
        now = int(time.time())
        if not _fresh(cutoff, now, 60):
            raise ValueError("Current feed cannot serve a replay cutoff")
        key = (endpoint, tuple(sorted(params.items())))
        cached = self.cache.get(key)
        if cached and _fresh(cached[1], cutoff, 60):
            return decode_json(cached[0]), cached[1]
        if self.requests >= self.max_requests:
            raise ValueError("Scanner GET cap reached")
        if self.last_request is not None:
            time.sleep(max(0, 1 - (time.monotonic() - self.last_request)))
        self.requests += 1
        self.last_request = time.monotonic()
        url = "https://api.wallex.ir" + endpoint + "?" + urlencode(params)
        with urllib.request.urlopen(urllib.request.Request(url), timeout=10) as response:
            raw = response.read(4_000_001)
        if len(raw) > 4_000_000:
            raise ValueError("Public response exceeds size cap")
        received = int(time.time())
        sha = hashlib.sha256(raw).hexdigest()
        self.capture_dir.mkdir(parents=True, exist_ok=True)
        path = self.capture_dir / (sha + ".json")
        if path.exists():
            if path.read_bytes() != raw:
                raise ValueError("Content-addressed capture mismatch")
        else:
            with path.open("xb") as out:
                out.write(raw)
        self.captures.append(dict(endpoint=endpoint, query=params, sha256=sha, received_at=received))
        self.cache[key] = (raw, received)
        return decode_json(raw), received


def scan_current_market(feed, *, account_symbols, account_as_of, interval_seconds=300,
                        round_trip_fee_pct, min_depth_tmn, max_spread_pct, available_tmn_cash,
                        batch_limit=3):
    """At most one catalog and two GETs per shortlisted symbol; never scan historical winners.

    Returns every liquidity-valid candidate at one uniform closed-candle cutoff. The entry
    model selects the symbol; this function never returns a host-chosen winner.
    """
    if interval_seconds not in (60, 300, 900, 1800, 3600):
        raise ValueError("Unsupported scanner interval")
    now = int(time.time())
    if account_symbols is None or not _fresh(account_as_of, now, 3600):
        return dict(status="BLOCKED_ACCESS", batch=(), errors=[], cutoff=None)
    errors = []
    try:
        payload, received = feed.get("/hector/web/v1/markets", {}, cutoff=now)
        rows = shortlist_markets(payload, account_symbols=account_symbols, cutoff=int(time.time()),
                                 received_at=received, account_as_of=account_as_of)
    except (OSError, ValueError) as exc:
        return dict(status="BLOCKED_DATA", batch=(), errors=[type(exc).__name__], cutoff=None)
    snapshot_cutoff = now // interval_seconds * interval_seconds
    series, depths, candle_times, depth_times = {}, {}, {}, {}
    for row in rows:
        try:
            end = now // interval_seconds * interval_seconds
            start = end - 40 * interval_seconds
            history, candle_times[row.symbol] = feed.get("/v1/udf/history", {
                "symbol": row.symbol, "resolution": "1", "from": start, "to": end,
            }, cutoff=now)
            minute = parse_history(history, start=start, end=end, interval_seconds=60, cutoff=now)
            bars = aggregate_closed(minute, interval_seconds)
            if bars.incomplete_bins:
                raise ValueError("Incomplete aggregation")
            series[row.symbol] = bars
            depths[row.symbol], depth_times[row.symbol] = feed.get(
                "/v1/depth", {"symbol": row.symbol}, cutoff=int(time.time()))
        except (OSError, ValueError) as exc:
            errors.append(dict(symbol=row.symbol, error_type=type(exc).__name__))
    batch = build_candidate_batch(rows, series_by_symbol=series, depth_by_symbol=depths,
        cutoff=int(time.time()), snapshot_cutoff=snapshot_cutoff,
        candle_received_at=candle_times, depth_received_at=depth_times,
        round_trip_fee_pct=round_trip_fee_pct, min_depth_tmn=min_depth_tmn, max_spread_pct=max_spread_pct,
        available_tmn_cash=available_tmn_cash, limit=batch_limit)
    status = "CANDIDATES" if batch else ("BLOCKED_DATA" if errors else "NO_CANDIDATE")
    return dict(status=status, batch=batch, errors=errors, cutoff=snapshot_cutoff)


def fetch_wallex_candles(
    symbol: str, resolution: str = "15", lookback_bars: int = 150,
) -> list[Candle]:
    """One public GET, exact minute decoding and complete aggregation; no cache fallback."""
    if not re.fullmatch(r"[A-Z0-9]+(?:TMN|USDT)", symbol):
        raise ValueError("Invalid symbol")
    if resolution not in ("1", "5", "15", "30", "60") or (
        type(lookback_bars) is not int or not 1 <= lookback_bars <= 200
    ):
        raise ValueError("Unsupported interval or lookback")
    step = int(resolution) * 60
    now = int(time.time())
    end = now // step * step
    start = end - lookback_bars * step
    query = urlencode(dict(symbol=symbol, resolution="1", **{"from": start, "to": end}))
    request = urllib.request.Request("https://api.wallex.ir/v1/udf/history?" + query)
    with urllib.request.urlopen(request, timeout=15) as response:
        raw = response.read(4_000_001)
    if len(raw) > 4_000_000:
        raise ValueError("History response exceeds size cap")
    return list(decode_closed_minutes(raw, start=start, end=end, step=step, cutoff=now).candles)


def decode_closed_minutes(raw, *, start, end, step, cutoff):
    series = parse_history(decode_json(raw), start=start, end=end, interval_seconds=60, cutoff=cutoff)
    result = aggregate_closed(series, step)
    if result.incomplete_bins or not result.candles:
        raise ValueError("Incomplete aggregate")
    return result


def evaluate_impulse_strategy(
    snapshot: FeatureSnapshot,
    in_position: bool,
    entry_price: Decimal | None = None,
    entry_time: int | None = None,
    current_time: int | None = None,
    target_tp_pct: Decimal = Decimal("0.018"),
    target_sl_pct: Decimal = Decimal("0.008"),
) -> tuple[str, list[str], str, str | None]:
    """Evaluate fast impulse momentum strategy with timely dynamic exit rules.

    Returns (action, evidence_ids, reason, exit_reason).
    """
    evidences = snapshot.evidences
    curr_price = snapshot.last_close

    if in_position and entry_price is not None and entry_time is not None:
        pnl_pct = (curr_price - entry_price) / entry_price if entry_price > 0 else Decimal(0)
        duration_seconds = (current_time or snapshot.cutoff) - entry_time

        # Profit targets are review checkpoints; only host protection or evidence can exit.
        # 2. Stop Loss Hit
        if pnl_pct <= -target_sl_pct:
            return (
                "EXIT",
                ["EV_POSITION_LONG"],
                f"Dynamic Stop Loss triggered: loss {pnl_pct * 100:.2f}% <= -{target_sl_pct * 100:.2f}%",
                "DYNAMIC_SL_HIT",
            )

        # 3. Momentum Stall / Exhaustion Early Exit (Take profit early when momentum stalls in green)
        if ("EV_MOMENTUM_STALL" in evidences or "EV_WICK_REJECTION" in evidences) and pnl_pct >= Decimal("0.007"):
            evs = ["EV_POSITION_LONG"]
            if "EV_MOMENTUM_STALL" in evidences:
                evs.append("EV_MOMENTUM_STALL")
            if "EV_WICK_REJECTION" in evidences:
                evs.append("EV_WICK_REJECTION")
            return (
                "EXIT",
                evs,
                f"Early Profit Take: Momentum exhaustion with locked profit (PnL: {pnl_pct * 100:+.2f}%)",
                "MOMENTUM_STALL_EARLY_EXIT",
            )

        # 4. Bearish Reversal
        if "EV_TREND_BEARISH" in evidences or "EV_RSI_OVERBOUGHT" in evidences:
            return (
                "EXIT",
                ["EV_POSITION_LONG", "EV_TREND_BEARISH" if "EV_TREND_BEARISH" in evidences else "EV_RSI_OVERBOUGHT"],
                f"Early Exit: Trend reversal or overbought RSI (PnL: {pnl_pct * 100:+.2f}%)",
                "TREND_REVERSAL_EXIT",
            )

        # 5. Time Stop (Max 30 minutes / 1800 seconds)
        if duration_seconds >= 1800:
            return (
                "EXIT",
                ["EV_POSITION_LONG"],
                f"Time-Stop: Position reached max 30m duration limit ({duration_seconds}s, PnL: {pnl_pct * 100:+.2f}%)",
                "TIME_STOP_30M",
            )

        return (
            "WAIT",
            ["EV_POSITION_LONG", "EV_DATA_FRESH"],
            f"Hold position: current PnL {pnl_pct * 100:+.2f}%, held for {duration_seconds // 60}m",
            None,
        )

    # FLAT Position: Scan for high-conviction breakout that comfortably clears 0.60% fees
    has_trend = "EV_TREND_BULLISH" in evidences
    has_squeeze_or_expand = "EV_BB_EXPANDING" in evidences or "EV_STRONG_BULLISH_BODY" in evidences
    no_wick_rejection = "EV_WICK_REJECTION" not in evidences
    healthy_rsi = Decimal("45") <= snapshot.rsi_14 <= Decimal("68")
    vol_surge = snapshot.volume_ratio >= Decimal("1.25")
    has_volatility = (snapshot.atr_14 / snapshot.last_close) >= Decimal("0.005") if snapshot.last_close > 0 else False

    # High conviction entry condition
    if has_trend and has_squeeze_or_expand and no_wick_rejection and healthy_rsi and vol_surge and has_volatility:
        entry_evs = ["EV_TREND_BULLISH", "EV_POSITION_FLAT"]
        if "EV_BB_EXPANDING" in evidences:
            entry_evs.append("EV_BB_EXPANDING")
        if "EV_STRONG_BULLISH_BODY" in evidences:
            entry_evs.append("EV_STRONG_BULLISH_BODY")

        return (
            "ENTER",
            entry_evs,
            f"High-conviction impulse breakout: Bullish trend, healthy RSI ({snapshot.rsi_14:.1f}), volume {snapshot.volume_ratio:.2f}x",
            None,
        )

    pos_ev = "EV_POSITION_LONG" if in_position else "EV_POSITION_FLAT"
    return (
        "WAIT",
        [pos_ev, "EV_DATA_FRESH"],
        "Scan active: waiting for confirmed momentum breakout clearing 0.6% fee hurdle",
        None,
    )


def run_paper_session(*args, **kwargs):
    """The removed draft cannot reset an existing portfolio or publish historical AI claims."""
    raise ValueError("BLOCKED_CURRENT_RUNTIME_ACCEPTANCE: use reviewed replay; exchange/source release contracts remain unknown")


def save_manifest(*args, **kwargs):
    raise ValueError("BLOCKED_UNVERIFIED_PROVENANCE: draft reports cannot be published")


def scan_best_market(*, catalog_payload=None, account_symbols=None, cutoff=None,
                     received_at=None, account_as_of=None, shortlist_size=3):
    """Cheap full-catalog shortlist; unknown access has no default candidate."""
    if catalog_payload is None or account_symbols is None:
        return None
    return shortlist_markets(catalog_payload, account_symbols=account_symbols, cutoff=cutoff,
                             received_at=received_at, account_as_of=account_as_of, limit=shortlist_size)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", type=str, default="USDTTMN", help="Target symbol (e.g. USDTTMN, BTCTMN, SOLTMN, AUTO)")
    parser.add_argument("--scan", action="store_true", help="Auto-scan top allowed markets to pick the best momentum pair")
    parser.add_argument("--capital", type=Decimal, default=Decimal("5000000"), help="Initial capital in TMN (default 5M)")
    parser.add_argument("--order-size", type=Decimal, default=Decimal("1500000"), help="Order size in TMN per trade")
    parser.add_argument("--resolution", type=str, default="5", help="Candle resolution in minutes (e.g. 5, 15, 60)")
    parser.add_argument("--lookback", type=int, default=160, help="Number of candles to analyze")
    parser.add_argument("--db-path", type=str, default=":memory:", help="SQLite database path for ledger and memory")
    parser.parse_args(argv)
    print("BLOCKED_RELEASE_CONTRACT_UNKNOWN (BLOCKED_UNREVIEWED_REPLAY): spot minimum/feeAsset/expiry, source acceptance and current-runtime validation pending. No market request or database write performed.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
