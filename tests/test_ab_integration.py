"""A/B boundary exercise with actual SDK TestModel and paper money; no network or skill claim."""

import json
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path

import httpx2
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.test import TestModel

from royin.agent import ROLE_INSTRUCTIONS, decide_role
from royin.broker import PaperBroker
from royin.config import RuntimeConfig
from royin.decision import EntryOpportunityContext, PositionReviewContext, RoleDecisionProposal
from royin.features import FeatureSnapshot, extract_features
from royin.ledger import Ledger
from royin.market_data import Candle, CandleSeries
from royin.risk import MarketRules, PositionProtectionPolicy, RiskPolicy, evaluate_risk


async def fake_role(snapshot, action, *, opportunity=None, position=None):
    role="POSITION_REVIEWER" if position else "ENTRY_ANALYST"
    proposal=RoleDecisionProposal(action=action,role=role,cutoff=snapshot.cutoff,
        snapshot_sha256=snapshot.snapshot_sha256,position_sha256=position.sha256 if position else None,
        opportunity_sha256=opportunity.sha256 if opportunity else None,evidence_ids=("EV_DATA_FRESH",),
        reason="FAKE_MODEL A/B integration fixture",invalidation="Next current closed candle")
    agent=Agent(TestModel(custom_output_args=proposal.model_dump(mode="json"),call_tools=["read_market_snapshot"]),
        deps_type=FeatureSnapshot,output_type=RoleDecisionProposal,instructions=ROLE_INSTRUCTIONS[role])
    @agent.tool
    def read_market_snapshot(ctx:RunContext[FeatureSnapshot])->str:
        return json.dumps(ctx.deps.to_canonical_dict())
    trace={}
    async with httpx2.AsyncClient(transport=httpx2.MockTransport(
        lambda _: (_ for _ in ()).throw(AssertionError("Network forbidden")))) as client:
        decision=await decide_role(snapshot,config=RuntimeConfig(),client=client,agent=agent,
            opportunity=opportunity,position=position,model_trace=trace)
    return decision,trace


class ABIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_entry_hold_host_trailing_and_restart_single_portfolio(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"paper.sqlite3"
            ledger=Ledger(path)
            ledger.initialize_portfolio(D(5000000),quote_asset="TMN",binding="a"*64)
            rules=MarketRules("USDTTMN","USDT","TMN",D(1),D(".01"),D(100000),D(1),D(".003"),D(".003"))
            risk_policy=RiskPolicy(D(300000),D(300000),D(".02"),D(".05"),20000,min_seconds_before_deadline=1)
            protection=PositionProtectionPolicy(D(".02"),D(".01"),D(".025"),30,300,20000,10,5,D(10000))
            candles=tuple(Candle(6000+i*60,D(100000),D(102000),D(98000),D(100000),D(1000)) for i in range(35))
            snap=extract_features(CandleSeries(candles,60),"USDTTMN",cutoff=8100,available_tmn_cash=D(5000000))
            opportunity=EntryOpportunityContext(spread_pct=D(".001"),round_trip_fee_pct=D(".006"),
                bid_depth_tmn=D(10000000),ask_depth_tmn=D(10000000),catalog_sha256="f"*64,
                catalog_received_at=8101,candle_received_at=8102,depth_received_at=8103,observed_at=8105)
            ledger.claim_candle("USDTTMN",8100,snap.snapshot_sha256,60)
            enter,trace=await fake_role(snap,"ENTER",opportunity=opportunity)
            self.assertEqual(trace["evidence_kind"],"FAKE_MODEL")
            approved=evaluate_risk(enter,market_rules=rules,policy=risk_policy,ledger=ledger,current_time=8105,
                snapshot_sha256=snap.snapshot_sha256,candle_close_time=8100,current_price=D(100000),denied_markets=frozenset())
            self.assertTrue(approved.approved)
            broker=PaperBroker(ledger,rules)
            with ledger.transaction():
                broker.submit_order(approved,client_id="integration_entry",timestamp=8105)
                ledger.complete_candle("USDTTMN",8100,enter)
            self.assertFalse(ledger.claim_candle("USDTTMN",8100,snap.snapshot_sha256,60))
            first=Candle(8100,D(100000),D(102000),D(99000),D(100000),D(1000))
            second=Candle(8160,D(100000),D(102000),D(99000),D(100000),D(1000))
            self.assertEqual(broker.process_candle(first,candle_interval=60),[])
            self.assertEqual(ledger.get_balance("USDT").total,D(0))
            self.assertEqual(broker.process_candle(second,candle_interval=60),["integration_entry"])
            self.assertEqual(ledger.get_balance("USDT").total,D("2.99"))
            broker.arm_protection(protection,opened_at=8220,entry_price=D(100000))
            checkpoint=broker.observe_quote(D(103000),source_time=8221,received_at=8221,now=8221,policy=protection)
            self.assertEqual(checkpoint["action"],"WAIT")
            view=broker.export_state(D(103000),now=8221)
            held_snap=extract_features(CandleSeries((*candles,first,second),60),"USDTTMN",cutoff=8220,
                current_position_base=ledger.get_balance("USDT").total,available_tmn_cash=ledger.get_balance("TMN").free)
            position=PositionReviewContext(quantity=D(view["quantity"]),cost_basis_tmn=D(view["cost_basis_tmn"]),
                net_liquidation_tmn=D(view["net_liquidation_tmn"]),opened_at=8220,observed_at=8221,hard_exit_at=8520,
                initial_stop_price=D(checkpoint["initial_stop_price"]),trailing_stop_price=D(checkpoint["trailing_stop_price"]),checkpoint_profit_pct=D(".025"))
            held,review_trace=await fake_role(held_snap,"WAIT",position=position)
            self.assertEqual(held.action,"WAIT")
            self.assertEqual(review_trace["context"]["role"],"POSITION_REVIEWER")
            broker.observe_quote(D(104000),source_time=8222,received_at=8222,now=8222,policy=protection)
            # Actual SQLite restart preserves money and peak; no new model, balance reset or order.
            ledger=Ledger(path)
            self.assertFalse(ledger.initialize_portfolio(D(5000000),quote_asset="TMN",binding="a"*64))
            broker=PaperBroker(ledger,rules)
            result=broker.observe_quote(D(102000),source_time=8223,received_at=8223,now=8223,policy=protection)
            self.assertEqual(result["action"],"EXIT")
            self.assertEqual(ledger.get_balance("TMN").free,D("5004016.02747"))
            self.assertEqual(ledger.get_realized_pnl(),D("4016.02747"))
            self.assertEqual(ledger.get_balance("USDT").total,D(0))
            late_exit=held.model_copy(update={"action":"EXIT"})
            rejected=evaluate_risk(late_exit,market_rules=rules,policy=risk_policy,ledger=ledger,current_time=8223,
                snapshot_sha256=held_snap.snapshot_sha256,candle_close_time=8220,current_price=D(102000),denied_markets=frozenset())
            self.assertFalse(rejected.approved)
            with ledger.connection() as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM fills").fetchone()[0],2)


if __name__=="__main__":
    unittest.main()
