"""Market/horizon selection by the model, with host-only eligibility and binding checks.

Synthetic transport only; REAL_MODEL evidence is separate and never claimed here.
"""

import json
import unittest
from decimal import Decimal as D

import httpx2

from royin.agent import decide_role
from royin.config import RuntimeConfig
from royin.decision import EntryOpportunityContext, MarketEntryProposal
from royin.features import extract_features
from royin.market_data import Candle, CandleSeries


def snapshot(symbol):
    candles = tuple(Candle(6000 + i * 60, D(100), D(102), D(99), D(101), D(20)) for i in range(35))
    return extract_features(CandleSeries(candles, 60), symbol, cutoff=8100)


def opportunity():
    return EntryOpportunityContext(
        spread_pct=D(".001"), round_trip_fee_pct=D(".006"),
        bid_depth_tmn=D(100000), ask_depth_tmn=D(100000),
        catalog_sha256="c" * 64, catalog_received_at=8101,
        candle_received_at=8102, depth_received_at=8103, observed_at=8105,
    )


def batch(symbols=("BTCTMN", "ETHTMN")):
    return {symbol: (snapshot(symbol), opportunity()) for symbol in symbols}


def forecast(snap, *, horizon=10800, q10="-.005", q50=".012", q90=".03", target=".02"):
    return {
        "forecast_id": "fc_" + snap.symbol,
        "symbol": snap.symbol,
        "cutoff": snap.cutoff,
        "reference_price": str(snap.last_close),
        "reference_kind": "LAST_CLOSE",
        "horizon_seconds": horizon,
        "return_q10": q10,
        "return_q50": q50,
        "return_q90": q90,
        "target_return_fraction": target,
        "review_after_seconds": 1800,
        "invalidation": "close below entry structure",
        "evidence_ids": ["EV_DATA_FRESH"],
    }


def enter_proposal(snap, *, horizon=10800):
    return {
        "role": "ENTRY_ANALYST", "action": "ENTER", "symbol": snap.symbol,
        "cutoff": snap.cutoff, "snapshot_sha256": snap.snapshot_sha256,
        "position_sha256": None, "opportunity_sha256": opportunity().sha256,
        "evidence_ids": ["EV_DATA_FRESH"], "reason": "model-selected candidate",
        "invalidation": "structure breaks",
        "horizon_seconds": horizon, "review_after_seconds": 1800,
        "forecast": forecast(snap, horizon=horizon),
    }


class MarketSelectionTests(unittest.IsolatedAsyncioTestCase):
    config = RuntimeConfig(BOXAPI_API_KEY="fake")

    async def test_role_schema_cannot_advertise_host_owned_legacy_risk_fields(self):
        schema = MarketEntryProposal.model_json_schema()
        proposal = enter_proposal(snapshot("BTCTMN"))
        for field in ("target_profit_pct","stop_loss_pct"):
            self.assertEqual(schema["properties"][field]["type"],"null")
            with self.subTest(field=field),self.assertRaises(ValueError):
                MarketEntryProposal.model_validate({**proposal,field:"0.02"})

    async def call(self, proposal, market_batch, *, trace=None, remaining_seconds=None):
        bodies = []

        async def handler(request):
            bodies.append(json.loads(request.content))
            if len(bodies) == 1:
                message = {"role": "assistant", "content": None, "tool_calls": [dict(
                    id="read1", type="function", function=dict(name="read_market_snapshot", arguments="{}"))]}
                finish = "tool_calls"
            else:
                message = {"role": "assistant", "content": json.dumps(proposal)}
                finish = "stop"
            return httpx2.Response(200, json=dict(
                id="fake", object="chat.completion", created=0, model="gpt-6-luna",
                choices=[dict(index=0, finish_reason=finish, message=message)],
                usage=dict(prompt_tokens=100, completion_tokens=20, total_tokens=120)))

        trace = {} if trace is None else trace
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
            decision = await decide_role(
                next(iter(market_batch.values()))[0], market_batch=market_batch,
                config=self.config, client=client, model_trace=trace,
                allowed_symbols=tuple(market_batch), remaining_seconds=remaining_seconds,
            )
        return decision, trace, bodies

    async def test_entry_tool_exposes_executable_quotes_and_receipt_time(self):
        market_batch = batch()
        snap,opp = market_batch["ETHTMN"]
        opp = opp.model_copy(update={"best_bid":D(100),"best_ask":D(102)})
        market_batch["ETHTMN"] = snap,opp
        proposal = enter_proposal(snap)
        proposal["opportunity_sha256"] = opp.sha256
        _,trace,_ = await self.call(proposal,market_batch)
        row = next(row for row in trace["context"]["candidates"] if row["symbol"] == "ETHTMN")
        self.assertEqual((row["best_bid"],row["best_ask"],row["last_close"]),("100","102","101"))
        self.assertEqual(row["quote_observed_at"],8103)

    async def test_model_can_pick_second_symbol_contrary_to_host_order(self):
        market_batch = batch()
        host_order = list(market_batch)
        chosen = host_order[1]
        decision, trace, bodies = await self.call(enter_proposal(market_batch[chosen][0]), market_batch)
        self.assertEqual(decision.action, "ENTER")
        self.assertEqual(decision.symbol, chosen)
        self.assertEqual(decision.snapshot_sha256, market_batch[chosen][0].snapshot_sha256)
        self.assertEqual([c["symbol"] for c in trace["context"]["candidates"]], sorted(host_order))
        tool = json.loads(next(m for m in bodies[-1]["messages"] if m["role"] == "tool")["content"])
        self.assertEqual(tool["batch_sha256"], trace["context"]["batch_sha256"])

    async def test_out_of_batch_forbidden_symbol_and_hash_fail_closed_to_wait(self):
        market_batch = batch()
        base = enter_proposal(market_batch["BTCTMN"][0])
        for mutation in (
            dict(symbol="TONTMN"),
            dict(snapshot_sha256="f" * 64),
            dict(opportunity_sha256="f" * 64),
            dict(cutoff=8101),
        ):
            with self.subTest(mutation=mutation):
                proposal = dict(base)
                proposal.update(mutation)
                decision, _, _ = await self.call(proposal, market_batch)
                self.assertEqual(decision.action, "WAIT")
                self.assertIn("rejected", decision.reason)
                self.assertNotIn("TONTMN", decision.symbol)

    async def test_enter_requires_forecast_and_consistent_horizon(self):
        market_batch = batch()
        snap = market_batch["BTCTMN"][0]
        cases = []
        proposal = enter_proposal(snap)
        proposal.pop("forecast")
        cases.append(proposal)
        proposal = enter_proposal(snap)
        proposal["horizon_seconds"] = 7200  # disagrees with forecast 10800
        cases.append(proposal)
        proposal = enter_proposal(snap)
        proposal["forecast"]["return_q10"] = ".05"
        proposal["forecast"]["return_q50"] = ".01"
        cases.append(proposal)
        proposal = enter_proposal(snap, horizon=36001)
        proposal["forecast"]["horizon_seconds"] = 36001
        cases.append(proposal)  # beyond the current ten-hour host policy
        for proposal in cases:
            with self.subTest(proposal=proposal):
                decision, _, _ = await self.call(proposal, market_batch)
                self.assertEqual(decision.action, "WAIT")
        decision, _, _ = await self.call(
            enter_proposal(snap, horizon=21600), market_batch, remaining_seconds=3600)
        self.assertEqual(decision.action, "WAIT")

    async def test_model_wait_is_preserved_without_fallback_symbol(self):
        market_batch = batch()
        snap = market_batch["BTCTMN"][0]
        proposal = {
            "role": "ENTRY_ANALYST", "action": "WAIT", "symbol": None,
            "cutoff": 8100, "snapshot_sha256": snap.snapshot_sha256,
            "position_sha256": None, "opportunity_sha256": None,
            "evidence_ids": ["EV_DATA_FRESH"], "reason": "no attractive candidate",
            "invalidation": "next candle",
            "horizon_seconds": 10800, "review_after_seconds": 1800,
            "forecast": forecast(snap),
        }
        decision, trace, _ = await self.call(proposal, market_batch)
        self.assertEqual(decision.action, "WAIT")
        self.assertEqual(trace["host_outcome"], "MODEL_DECISION")

    async def test_malformed_enter_is_a_clear_wait_fallback(self):
        market_batch = batch()
        proposal = enter_proposal(market_batch["BTCTMN"][0])
        proposal["forecast"]["return_q50"] = "NaN"
        decision, trace, _ = await self.call(proposal, market_batch)
        self.assertEqual(decision.action, "WAIT")
        self.assertEqual(trace["host_outcome"], "HOST_FALLBACK")
        self.assertIn("rejected", decision.reason)


if __name__ == "__main__":
    unittest.main()
