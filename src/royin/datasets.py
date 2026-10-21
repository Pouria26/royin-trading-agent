"""Accepted, hash-bound historical inputs; no directory glob grants acceptance."""

import hashlib
import time
from pathlib import Path

from royin.market_data import Candle, decimal_number, decode_json


def validate_candles(candles, interval_seconds, *, now=None):
    now = int(time.time()) if now is None else now
    if type(interval_seconds) is not int or interval_seconds <= 0 or not candles:
        raise ValueError("Empty data or invalid interval")
    previous = None
    for c in candles:
        if type(c.open_time) is not int or c.open_time <= 0 or c.open_time + interval_seconds > now:
            raise ValueError("Future/open candle or invalid time")
        if previous is not None and c.open_time != previous + interval_seconds:
            raise ValueError("Gap, duplicate or unordered data")
        for value in (c.open, c.high, c.low, c.close):
            decimal_number(value, positive=True)
        decimal_number(c.volume)
        if not c.low <= min(c.open, c.close) <= max(c.open, c.close) <= c.high:
            raise ValueError("Invalid OHLC")
        previous = c.open_time


def load_dataset(path, record=None):
    raw = Path(path).read_bytes()
    data = decode_json(raw)
    interval = data["interval_seconds"]
    if data.get("incomplete_bins"):
        raise ValueError("Incomplete dataset")
    candles = [
        Candle(
            c["open_time"],
            *(
                decimal_number(c[k], positive=k != "volume")
                for k in ("open", "high", "low", "close", "volume")
            ),
        )
        for c in data["candles"]
    ]
    validate_candles(candles, interval)
    if data["symbol"] != data["base_asset"] + data["quote_asset"] or data["quote_asset"] != "TMN":
        raise ValueError("Asset metadata mismatch")
    if data["cutoff"] != candles[-1].open_time + interval:
        raise ValueError("Cutoff metadata mismatch")
    if record is not None and (
        record["sha256"] != hashlib.sha256(raw).hexdigest()
        or record["symbol"] != data["symbol"]
        or record["interval_seconds"] != interval
        or record["start"] != candles[0].open_time
        or record["end"] != data["cutoff"]
        or record["status"] != "ACCEPTED"
    ):
        raise ValueError("Acceptance manifest/hash/metadata mismatch")
    return data, candles


def accepted_datasets(manifest_path):
    manifest_path = Path(manifest_path)
    manifest = decode_json(manifest_path.read_bytes())
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported acceptance manifest")
    seen = set()
    result = []
    for record in manifest["datasets"]:
        if record["status"] != "ACCEPTED":
            continue
        path = manifest_path.parent / record["path"]
        data, candles = load_dataset(path, record)
        # Ignore provenance serialization differences when deduplicating economic observations.
        key = (data["symbol"], data["interval_seconds"], tuple(candles))
        if key in seen:
            continue
        seen.add(key)
        result.append((path, data, candles, record))
    return result
