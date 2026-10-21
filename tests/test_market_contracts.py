import copy
import unittest
from decimal import Decimal
from pathlib import Path

from royin.market_data import (
    CandleSeries,
    aggregate_closed,
    decimal_number,
    decode_json,
    parse_history,
)
from royin.markets import (
    eligible_markets,
    load_restrictions,
    parse_catalog,
    parse_credit_balances,
    parse_fee_rates,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


class CandleContractTests(unittest.TestCase):
    def setUp(self):
        self.payload = decode_json((FIXTURES / "wallex-minute-history.json").read_bytes())
        self.start = self.payload["t"][0]

    def parse(self, payload=None, *, cutoff=None, interval=60):
        return parse_history(
            self.payload if payload is None else payload, start=self.start,
            end=self.start + 1800, interval_seconds=interval,
            cutoff=self.start + 1800 if cutoff is None else cutoff,
        )

    def test_real_fixture_boundary_and_closed_cutoff(self):
        self.assertEqual(len(self.parse().candles), 30)
        series = self.parse(cutoff=self.start + 89)
        self.assertEqual(len(series.candles), 1)
        self.assertEqual(series.candles[0].close, Decimal(self.payload["c"][0]))

    def test_hand_computed_aggregation_and_partial_bin(self):
        payload = {"s": "ok", "t": [0, 60, 120], "o": ["10", "11", "12"],
                   "h": ["12", "14", "13"], "l": ["9", "10", "8"],
                   "c": ["11", "12", "9"], "v": ["0.1", "0.2", "0.3"]}
        series = parse_history(payload, start=0, end=180, interval_seconds=60, cutoff=180)
        result = aggregate_closed(series, 180).candles[0]
        self.assertEqual((result.open, result.high, result.low, result.close, result.volume),
                         tuple(map(Decimal, ("10", "14", "8", "9", "0.6"))))
        partial = aggregate_closed(CandleSeries(series.candles[:2], 60), 180)
        self.assertEqual(partial.candles, ())
        self.assertEqual(partial.incomplete_bins, (0,))

    def test_prefix_and_future_price_invariance(self):
        cutoff = self.start + 900
        expected = aggregate_closed(self.parse(cutoff=cutoff), 900)
        future = copy.deepcopy(self.payload)
        for key in ("o", "h", "l", "c", "v"):
            future[key][15:] = ["future invalid value"] * len(future[key][15:])
        self.assertEqual(aggregate_closed(self.parse(future, cutoff=cutoff), 900), expected)
        prefix = {key: values[:15] if isinstance(values, list) else values
                  for key, values in self.payload.items()}
        self.assertEqual(aggregate_closed(self.parse(prefix, cutoff=cutoff), 900), expected)

    def test_every_cutoff_keeps_only_completed_bins(self):
        full = aggregate_closed(self.parse(), 900)
        for seconds in (0, 59, 60, 899, 900, 901, 1799, 1800):
            result = aggregate_closed(self.parse(cutoff=self.start + seconds), 900)
            self.assertEqual(result.candles, tuple(
                c for c in full.candles if c.open_time + 900 <= self.start + seconds
            ))

    def test_gap_duplicate_order_range_and_cadence_are_rejected(self):
        for times in (
            self.payload["t"][1:], [self.start] * 31,
            list(reversed(self.payload["t"])),
            [self.start - 60, *self.payload["t"][1:]],
            [True, *self.payload["t"][1:]],
        ):
            payload = copy.deepcopy(self.payload)
            payload["t"] = times
            with self.subTest(times=times[:2]), self.assertRaises(ValueError):
                self.parse(payload)
        with self.assertRaises(ValueError):
            self.parse(interval=900)
        with self.assertRaises(ValueError):
            aggregate_closed(CandleSeries(self.parse().candles[::2], 60), 900)

    def test_empty_unavailable_and_unequal_arrays_are_not_a_success(self):
        for payload in ({"s": "no_data"}, {**self.payload, "c": []},
                        {k: [] if isinstance(v, list) else v for k, v in self.payload.items()}):
            with self.subTest(payload=payload.get("s")), self.assertRaises(ValueError):
                self.parse(payload)

    def test_invalid_ohlc_prices_and_volume_are_rejected(self):
        for key, value in (("c", "0"), ("c", "NaN"), ("c", "Infinity"), ("c", 1.1),
                           ("c", True), ("v", "-1"), ("h", "1")):
            payload = copy.deepcopy(self.payload)
            payload[key][0] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.parse(payload)

    def test_json_decimal_tokens_remain_exact_and_ambiguous_json_is_rejected(self):
        number = decode_json('{"price": 0.12345678901234567890123456789}')["price"]
        self.assertEqual(number, Decimal("0.12345678901234567890123456789"))
        for raw in ('{"v":NaN}', '{"v":1,"v":2}'):
            with self.assertRaises(ValueError):
                decode_json(raw)
        for value in (None, True, 0.1, "NaN", "Infinity", "-0.01"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                decimal_number(value)

    def test_extreme_window_and_decimal_exponents_are_bounded(self):
        with self.assertRaises(ValueError):
            parse_history(self.payload, start=0, end=60 * 10**12, interval_seconds=60,
                          cutoff=60 * 10**12)
        for value in ("1e1000000000", "1e-1000000000", "9" * 129):
            with self.assertRaises(ValueError):
                decimal_number(value)

    def test_aggregation_preserves_volume_beyond_default_decimal_precision(self):
        payload = {"s": "ok", "t": [0, 60], "o": ["1", "1"], "h": ["1", "1"],
                   "l": ["1", "1"], "c": ["1", "1"],
                   "v": ["0.12345678901234567890123456789", "0.00000000000000000000000000001"]}
        series = parse_history(payload, start=0, end=120, interval_seconds=60, cutoff=120)
        self.assertEqual(aggregate_closed(series, 120).candles[0].volume,
                         Decimal("0.12345678901234567890123456790"))


class MarketAccountContractTests(unittest.TestCase):
    def setUp(self):
        self.payload = decode_json((FIXTURES / "wallex-public-catalog.json").read_bytes())
        self.catalog = parse_catalog(self.payload)
        self.denied = load_restrictions(ROOT / "config" / "wallex-credit-market-policy.json")
        self.account = decode_json((FIXTURES / "wallex-credit-contract.json").read_bytes())

    def eligible(self, **kwargs):
        return eligible_markets(
            self.catalog, self.denied, account_symbols=tuple(self.catalog), **kwargs,
        )

    def test_metadata_maps_both_quotes_and_preserves_numeric_base(self):
        for quote in ("TMN", "USDT"):
            market = self.catalog["1BBABYDOGE" + quote]
            self.assertEqual(market.base_asset, "1BBABYDOGE")
            self.assertNotIn(market.symbol, self.eligible())
            self.assertNotIn("PAXG" + quote, self.eligible())
        self.assertIn("YFITMN", self.eligible())
        self.assertNotIn("YFIUSDT", self.eligible())

    def test_operational_selection_never_overrides_snapshot_or_account(self):
        for selected in (("PAXGTMN",), ("PAXG/USDT",), ("1BBABYDOGE/TMN",), ("UNKNOWN",)):
            with self.subTest(selected=selected), self.assertRaises(ValueError):
                self.eligible(selected=selected)
        with self.assertRaises(ValueError):
            eligible_markets(self.catalog, self.denied, account_symbols=("BTCTMN",),
                             selected=("BTCUSDT",))

    def test_account_unknown_and_malformed_permissions_fail_closed(self):
        for account in (None, "BTCTMN", ("UNKNOWN",)):
            with self.subTest(account=account), self.assertRaises(ValueError):
                eligible_markets(self.catalog, self.denied, account_symbols=account)
        self.assertEqual(eligible_markets(self.catalog, self.denied, account_symbols=()), frozenset())
        with self.assertRaises(ValueError):
            self.eligible(account_denied="BTCTMN")

    def test_refresh_unions_restrictions_and_inactive_spot_is_excluded(self):
        initial = self.eligible()
        refreshed = self.eligible(account_denied=("BTC/TMN",), organizer_denied=("BTCUSDT",))
        self.assertLess(refreshed, initial)
        self.assertNotIn("PAXGTMN", refreshed)
        self.payload["result"]["markets"][0]["is_spot"] = False
        symbol = self.payload["result"]["markets"][0]["symbol"]
        catalog = parse_catalog(self.payload)
        self.assertNotIn(symbol, eligible_markets(catalog, self.denied, account_symbols=(symbol,)))

    def test_catalog_rejects_false_success_duplicate_wrong_mapping_and_wrong_types(self):
        for mutate in (
            lambda p: p.update(success=False),
            lambda p: p["result"]["markets"].append(p["result"]["markets"][0]),
            lambda p: p["result"]["markets"][0].update(symbol="WRONG"),
            lambda p: p["result"]["markets"][0].update(is_spot="true"),
            lambda p: p["result"]["markets"][0].update(amount_precision=1.0),
        ):
            payload = copy.deepcopy(self.payload)
            mutate(payload)
            with self.assertRaises(ValueError):
                parse_catalog(payload)

    def test_documented_fee_coefficients_and_credit_available_frozen_units(self):
        self.assertEqual(parse_fee_rates(self.account["fee"], "BTCTMN"),
                         (Decimal("0.001"), Decimal("0.002")))
        balances = parse_credit_balances(self.account["balances"])
        self.assertEqual(balances["TMN"].total, Decimal("5000000"))
        self.assertEqual(balances["BTC"].available, Decimal("0.0015"))
        self.assertEqual(balances["BTC"].locked, Decimal("0.0005"))
        with self.assertRaises(ValueError):
            parse_credit_balances({"success": True, "result": {"balances": {}}})

    def test_invalid_fees_and_balances_fail_closed(self):
        for value in ("NaN", "Infinity", "-0.01", "1", True, 0.001):
            payload = copy.deepcopy(self.account["fee"])
            payload["result"]["BTCTMN"]["makerFeeRate"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_fee_rates(payload, "BTCTMN")
        for change in ({"available": "5000001"}, {"freeze": "-1"}, {"symbol": "USDT"},
                       {"available": 1.5}):
            payload = copy.deepcopy(self.account["balances"])
            payload["result"]["TMN"].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                parse_credit_balances(payload)


if __name__ == "__main__":
    unittest.main()
