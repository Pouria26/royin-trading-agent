"""The model's indicative capacity must include the same declared minimum as the host."""
import unittest
from decimal import Decimal as D
from unittest.mock import MagicMock, patch

from scripts.run_paper_trader import scan_current_market
from tests.test_market_scanner import catalog, depth


class ResearchCapacityFloorTests(unittest.TestCase):
    def test_public_50k_metadata_cannot_override_declared_100k_research_floor(self):
        feed = MagicMock()
        def get(endpoint, params, **kwargs):
            if endpoint == "/hector/web/v1/markets":
                return catalog(),30005
            if endpoint == "/v1/markets":
                return dict(success=True,result=dict(symbols=dict(BTCTMN=dict(symbol="BTCTMN",
                    baseAsset="BTC",quoteAsset="TMN",stepSize=2,tickSize=2,
                    minNotional="50000",minQty=".01")))),30005
            if endpoint == "/v1/depth":
                return depth(),30005
            times = list(range(params["from"],params["to"],60))
            return dict(s="ok",t=times,o=["100"]*len(times),h=["102"]*len(times),
                l=["98"]*len(times),c=["100"]*len(times),v=["1000"]*len(times)),30005
        feed.get.side_effect = get
        with patch("time.time",return_value=30005):
            report = scan_current_market(feed,account_symbols={"BTCTMN"},account_as_of=30000,
                round_trip_fee_pct=D(".006"),min_depth_tmn=D(10000),max_spread_pct=D(".005"),
                available_tmn_cash=D(150000),selected_symbols=["BTCTMN"],use_spot_rules=True,
                research_debit_tmn=D(150000),research_min_notional_tmn=D(100000))
        self.assertEqual(report["status"],"CANDIDATES",report)
        self.assertEqual(report["market_rules"]["BTCTMN"].min_notional,D(50000))
        self.assertEqual(report["batch"][0].opportunity.execution_capacity.min_notional,D(100000))


if __name__ == "__main__":
    unittest.main()
