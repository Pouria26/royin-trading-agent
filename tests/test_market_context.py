"""Hand-labeled market breadth and currency-adjusted relative-strength tests."""
import copy
import unittest
from decimal import Decimal as D

from royin.decision import MarketEntryProposal, validate_role_proposal
from royin.market_context import catalog_return, market_context
from royin.markets import parse_spot_rules
from scripts.run_paper_trader import shortlist_markets
from tests.test_market_scanner import catalog
from tests.test_market_selection import enter_proposal, opportunity, snapshot


def context_payload(changes, cash="0"):
    rows = [{"symbol":"USDTTMN", "base_asset":"USDT", "quote_asset":"TMN", "change_24h":cash}]
    rows.extend({"symbol":base+"TMN", "base_asset":base, "quote_asset":"TMN", "change_24h":change}
                for base, change in zip(("BTC","ETH","DOGE"), changes, strict=True))
    return {"success":True, "result":{"markets":rows}}


class MarketContextTests(unittest.TestCase):
    def test_spot_rules_use_actual_spot_minimum_and_precision_counts(self):
        row = dict(symbol="USDTTMN",baseAsset="USDT",quoteAsset="TMN",
                   stepSize=2,tickSize=0,minQty=".01",minNotional="50000")
        payload = dict(success=True,result=dict(symbols={"USDTTMN":row}))
        rules = parse_spot_rules(payload,maker_fee_rate=D(".0025"),taker_fee_rate=D(".003"))["USDTTMN"]
        self.assertEqual((rules.step_size,rules.tick_size,rules.min_quantity,rules.min_notional),
                         (D(".01"),D(1),D(".01"),D(50000)))
        for bad in (True,-1,100,"2"):
            row["stepSize"] = bad
            with self.assertRaises(ValueError):
                parse_spot_rules(payload,maker_fee_rate=D(".0025"),taker_fee_rate=D(".003"))

    def test_local_fiat_rally_does_not_masquerade_as_crypto_bull_market(self):
        p = context_payload(("2","2","2"), cash="5")
        c = market_context(p, {r["symbol"] for r in p["result"]["markets"]}, observed_at=8100)
        self.assertEqual(c.regime, "BEARISH")
        self.assertEqual(c.positive_breadth, D(0))
        self.assertAlmostEqual(c.median_return_24h, D("1.02")/D("1.05")-1)

    def test_breadth_bull_mixed_and_missing_benchmark_are_explicit(self):
        for changes, expected in ((("4","2","3"),"BULLISH"), (("4","-2","0"),"MIXED")):
            p = context_payload(changes)
            c = market_context(p, {r["symbol"] for r in p["result"]["markets"]}, observed_at=8100)
            self.assertEqual(c.regime, expected)
        p = context_payload(("1","2","3"),cash=None)
        c = market_context(p, {"BTCTMN","ETHTMN","DOGETMN"},observed_at=8100)
        self.assertEqual(c.basis,"TMN_ONLY_UNADJUSTED")
        self.assertEqual(market_context(p,{"BTCTMN"},observed_at=8100).regime,"UNKNOWN")
        for invalid in (None,True,float("nan"),"NaN","-101","bad"):
            self.assertIsNone(catalog_return({"change_24h":invalid}))

    def test_diversified_shortlist_reaches_movers_without_allowing_denied_symbols(self):
        p = catalog()
        extra = copy.deepcopy(p["result"]["markets"][0])
        extra.update(symbol="DOGETMN",base_asset="DOGE",quote_volume_24h="150000000",change_24h="12")
        p["result"]["markets"].append(extra)
        rows = shortlist_markets(p,account_symbols={r["symbol"] for r in p["result"]["markets"]},
            cutoff=8105,received_at=8100,account_as_of=8100,limit=3,diversify=True,tmn_only=True)
        self.assertEqual({r.symbol for r in rows},{"BTCTMN","ETHTMN","DOGETMN"})

    def test_bearish_model_entry_cannot_override_observed_countertrend_gate(self):
        p = context_payload(("-3","-2","-1"))
        c = market_context(p,{"BTCTMN","ETHTMN","DOGETMN"},observed_at=8100)
        snap = snapshot("BTCTMN")
        opp = opportunity().model_copy(update={"market_context":c,"asset_return_24h":D("-.03"),"relative_strength_24h":D("-.01")})
        payload = enter_proposal(snap)
        payload["opportunity_sha256"] = opp.sha256
        payload["forecast"]["target_return_fraction"] = ".025"
        proposal = MarketEntryProposal.model_validate(payload)
        with self.assertRaisesRegex(ValueError,"relative strength"):
            validate_role_proposal(proposal,role="ENTRY_ANALYST",snapshot=snap,position=None,opportunity=opp,
                market_batch={"BTCTMN":(snap,opp)},horizon_bounds=(300,36000))
        payload["forecast"]["target_return_fraction"] = ".01"
        # The fixed gross objective is superseded; negative relative strength still blocks.
        with self.assertRaisesRegex(ValueError,"relative strength"):
            validate_role_proposal(MarketEntryProposal.model_validate(payload),role="ENTRY_ANALYST",snapshot=snap,
                position=None,opportunity=opp,market_batch={"BTCTMN":(snap,opp)},horizon_bounds=(300,36000))


if __name__ == "__main__":
    unittest.main()
