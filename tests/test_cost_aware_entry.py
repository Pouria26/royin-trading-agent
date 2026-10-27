"""Counterexamples for horizon-matched admission; synthetic, not alpha evidence."""
import unittest
from dataclasses import replace
from decimal import Decimal as D

from royin.decision import MarketEntryProposal, validate_role_proposal
from royin.market_context import MarketContext
from royin.risk import MarketRules, assess_target_net
from tests.test_market_selection import enter_proposal, opportunity, snapshot


class CostAwareEntryTests(unittest.TestCase):
    def case(self, *, target=".01", median=".009", ask="101", relative=".02"):
        snap = snapshot("BTCTMN")
        snap = replace(snap, evidences=snap.evidences | {"EV_TREND_BULLISH":"Synthetic bullish trend"})
        context = MarketContext(regime="BEARISH", observed_at=8100, catalog_sha256="c"*64,
            sample_count=10, positive_breadth=D(".2"), median_return_24h=D("-.03"),
            basis="TMN_ONLY_UNADJUSTED")
        opp = opportunity().model_copy(update=dict(best_bid=D(101), best_ask=D(ask),
            market_context=context, asset_return_24h=D("-.01"), relative_strength_24h=D(relative)))
        payload = enter_proposal(snap)
        payload["opportunity_sha256"] = opp.sha256
        payload["forecast"].update(target_return_fraction=target, return_q50=median)
        return snap, opp, MarketEntryProposal.model_validate(payload)

    def validate(self, **changes):
        snap, opp, proposal = self.case(**changes)
        validate_role_proposal(proposal, role="ENTRY_ANALYST", snapshot=snap, position=None,
            opportunity=opp, market_batch={snap.symbol:(snap,opp)}, horizon_bounds=(300,36000))

    def test_sub_two_percent_target_can_clear_costs_despite_negative_day_return(self):
        self.validate()

    def test_optimistic_target_cannot_hide_a_median_below_cost(self):
        with self.assertRaisesRegex(ValueError,"central forecast"):
            self.validate(target=".08", median=".002")

    def test_target_above_two_percent_is_insufficient_after_ask_gap(self):
        with self.assertRaisesRegex(ValueError,"cost"):
            self.validate(target=".021", median=".02", ask="104")

    def test_bearish_relative_weakness_still_blocks_even_with_positive_forecasts(self):
        with self.assertRaisesRegex(ValueError,"relative strength"):
            self.validate(relative="-.01")

    def test_fresh_economics_rechecks_central_cash_and_never_changes_forecast(self):
        _, _, proposal = self.case(target=".03", median=".001")
        rules = MarketRules("BTCTMN","BTC","TMN",D(".01"),D(".01"),D(100000),D(".01"),D(".003"),D(".003"))
        forecast = proposal.forecast
        result = assess_target_net(forecast=forecast, rules=rules, quantity=D(1400), entry_price=D(101),
            spread_pct=D(".001"), slippage_pct=D(".0005"), require_central=True)
        self.assertTrue(all(D(row["net_at_target_tmn"]) > 0 for row in result["scenarios"]))
        self.assertFalse(result["approved"])
        self.assertEqual(forecast.return_q50,D(".001"))

    def test_top_level_evidence_cannot_borrow_a_fact_from_another_candidate(self):
        snap, opp, proposal = self.case()
        self.assertNotIn("EV_PRIVATE_FAKE",snap.evidences)
        proposal=proposal.model_copy(update=dict(evidence_ids=("EV_PRIVATE_FAKE",)))
        with self.assertRaisesRegex(ValueError,"Decision cites evidence outside the chosen snapshot") as error:
            validate_role_proposal(proposal,role="ENTRY_ANALYST",snapshot=snap,position=None,
                opportunity=opp,market_batch={snap.symbol:(snap,opp)},horizon_bounds=(300,36000))
        self.assertNotIn("EV_PRIVATE_FAKE",str(error.exception))
