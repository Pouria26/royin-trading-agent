"""Unit tests for multi-factor quant screening and order book imbalance scoring."""
import unittest
from decimal import Decimal as D

from scripts.run_paper_trader import (
    MarketShortlistRow,
    quant_candidate_score,
    shortlist_markets,
)


def mock_catalog():
    rows = [
        dict(symbol="BTCTMN", base_asset="BTC", quote_asset="TMN", is_spot=True,
             price_precision=0, amount_precision=8, quote_volume_24h="100000000000",
             price="22000000000", highest_24h_price="22500000000", lowest_24h_price="21500000000",
             change_24h="-2.0", change_7D="1.0"),
        dict(symbol="USDTTMN", base_asset="USDT", quote_asset="TMN", is_spot=True,
             price_precision=0, amount_precision=2, quote_volume_24h="60000000000",
             price="270000", highest_24h_price="271000", lowest_24h_price="269000",
             change_24h="1.5", change_7D="2.0"),
        dict(symbol="ATOMTMN", base_asset="ATOM", quote_asset="TMN", is_spot=True,
             price_precision=0, amount_precision=4, quote_volume_24h="500000000",
             price="470000", highest_24h_price="475000", lowest_24h_price="450000",
             change_24h="3.0", change_7D="5.0"),
        dict(symbol="TRXTMN", base_asset="TRX", quote_asset="TMN", is_spot=True,
             price_precision=0, amount_precision=2, quote_volume_24h="12000000000",
             price="90000", highest_24h_price="91000", lowest_24h_price="88000",
             change_24h="2.0", change_7D="4.0"),
        dict(symbol="DUMMYTMN", base_asset="DUMMY", quote_asset="TMN", is_spot=True,
             price_precision=0, amount_precision=2, quote_volume_24h="200000000",
             price="100", highest_24h_price="150", lowest_24h_price="100",
             change_24h="-8.0", change_7D="-15.0"),
    ]
    return dict(success=True, result=dict(markets=rows))


class QuantScreenerTests(unittest.TestCase):
    def test_tokenized_oil_is_not_penalized_as_a_stablecoin(self):
        from dataclasses import replace
        rows = {r["symbol"]:r for r in mock_catalog()["result"]["markets"]}
        rows["USOONTMN"] = dict(rows["ATOMTMN"],symbol="USOONTMN")
        row = MarketShortlistRow("ATOMTMN",D("500000000"),D(1),8100,"c"*64)
        self.assertEqual(quant_candidate_score(row,rows,D("-.02")),
            quant_candidate_score(replace(row,symbol="USOONTMN"),rows,D("-.02")))

    def test_malformed_optional_catalog_values_are_not_positive_evidence(self):
        row = MarketShortlistRow("ATOMTMN",D("500000000"),D(1),8100,"c"*64)
        empty_score = quant_candidate_score(row,{"ATOMTMN":{}},D(0))
        for bad in ("NaN","Infinity",float("inf"),True,"1e1000"):
            with self.subTest(bad=bad):
                rows = {"ATOMTMN":dict(price=bad,highest_24h_price="100",lowest_24h_price="1",change_7D=bad)}
                self.assertEqual(quant_candidate_score(row,rows,D(0)),empty_score)

    def test_stablecoin_is_penalized_in_quant_ranking(self):
        payload = mock_catalog()
        rows = {r["symbol"]: r for r in payload["result"]["markets"]}
        btc_ret = D("-0.02")
        cash_ret = D("0.015")

        usdt_row = MarketShortlistRow("USDTTMN", D("60000000000"), D(1), 8100, "c"*64)
        atom_row = MarketShortlistRow("ATOMTMN", D("500000000"), D(1), 8100, "c"*64)

        score_usdt = quant_candidate_score(usdt_row, rows, btc_ret, cash_ret)
        score_atom = quant_candidate_score(atom_row, rows, btc_ret, cash_ret)

        # ATOM has positive RS (+5% over BTC) and is not a stablecoin -> must score significantly higher
        self.assertGreater(score_atom, score_usdt)
        self.assertLess(score_usdt, D("-50"))  # Stablecoin penalty applied

    def test_relative_strength_leader_ranks_above_falling_large_cap(self):
        payload = mock_catalog()
        rows = {r["symbol"]: r for r in payload["result"]["markets"]}
        btc_ret = D("-0.02")

        btc_row = MarketShortlistRow("BTCTMN", D("100000000000"), D(1), 8100, "c"*64)
        atom_row = MarketShortlistRow("ATOMTMN", D("500000000"), D(1), 8100, "c"*64)
        dummy_row = MarketShortlistRow("DUMMYTMN", D("200000000"), D(1), 8100, "c"*64)

        score_btc = quant_candidate_score(btc_row, rows, btc_ret)
        score_atom = quant_candidate_score(atom_row, rows, btc_ret)
        score_dummy = quant_candidate_score(dummy_row, rows, btc_ret)

        # ATOM (+3% vs BTC -2%) beats BTC (0% RS vs itself) which beats DUMMY (-8% dump)
        self.assertGreater(score_atom, score_btc)
        self.assertGreater(score_btc, score_dummy)

    def test_shortlist_diversified_selects_top_quant_movers(self):
        payload = mock_catalog()
        symbols = {"BTCTMN", "USDTTMN", "ATOMTMN", "TRXTMN", "DUMMYTMN"}
        args = dict(account_symbols=symbols, cutoff=8105, received_at=8100, account_as_of=8100, tmn_only=True)

        # When diversify=True, ATOM and TRX (top momentum/RS) must be in the top 2
        shortlisted = shortlist_markets(payload, **args, limit=2, diversify=True)
        self.assertEqual(len(shortlisted), 2)
        top_symbols = [r.symbol for r in shortlisted]
        self.assertIn("ATOMTMN", top_symbols)
        self.assertIn("TRXTMN", top_symbols)
        # USDTTMN and DUMMYTMN must not be in the top 2
        self.assertNotIn("USDTTMN", top_symbols)
        self.assertNotIn("DUMMYTMN", top_symbols)


if __name__ == "__main__":
    unittest.main()
