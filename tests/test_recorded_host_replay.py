"""Synthetic provider transcripts and hand-accounting oracles; not real-model evidence."""

import copy
import json
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import patch

from royin.decision import MarketEntryProposal, bind_decision
from royin.ledger import Ledger
from scripts import replay_market_paper as replay
from scripts import score_market_forecast as scorer
from tests.test_market_selection import forecast, opportunity, snapshot


class RecordedHostReplayTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.source = self.root/"original/manifest.json"
        self.source.parent.mkdir()
        snap, opp = snapshot("ETHTMN"), opportunity()
        proposal = dict(role="ENTRY_ANALYST",action="WAIT",symbol=None,cutoff=snap.cutoff,
            snapshot_sha256=snap.snapshot_sha256,position_sha256=None,opportunity_sha256=None,
            evidence_ids=["EV_DATA_FRESH"],reason="synthetic no-entry case",invalidation="next candle",
            forecast=forecast(snap,horizon=3600),horizon_seconds=3600,review_after_seconds=1800)
        self.proposal = MarketEntryProposal.model_validate(proposal)
        decision = bind_decision(self.proposal,decision_id="recorded-test",symbol=snap.symbol,
            cutoff=snap.cutoff,snapshot_sha256=snap.snapshot_sha256,available_evidence_ids=set(snap.evidences))
        candidates = [dict(symbol=snap.symbol,snapshot_sha256=snap.snapshot_sha256,opportunity_sha256=opp.sha256)]
        self.context = dict(role="ENTRY_ANALYST",cutoff=snap.cutoff,candidates=candidates,
            batch_sha256=replay.canonical_hash(candidates),horizon_bounds=[300,36000],remaining_seconds=3600)
        trace = dict(host_outcome="MODEL_DECISION",evidence_kind="REAL_MODEL_ATTEMPT",provider="boxapi",
            model="gpt-6-luna",prompt_sha256=replay.sha256(b"synthetic instructions"),
            context=self.context,decision=decision.model_dump(mode="json"))
        state = dict(accounting_event_count=0,balances={"TMN":dict(free="5000000",locked="0")})
        self.row = dict(decision=decision.model_dump(mode="json"),snapshot=snap.to_canonical_dict(),
            snapshot_sha256=snap.snapshot_sha256,opportunity=opp.model_dump(mode="json"),
            model_trace=trace,host_input_state=state,issued_at_utc="1970-01-01T02:15:01+00:00")
        self.manifest = dict(run_id="synthetic-original",mode="CURRENT_PAPER",model_mode="REAL_MODEL",
            created_at_utc="1970-01-01T02:15:02+00:00",bindings=dict(code_sha256="a"*64),public_captures=[],
            accounting=dict(schema_version=1,events=[],balances=copy.deepcopy(state["balances"]),realized_pnl_tmn="0"),
            arms=dict(paper_portfolio=dict(initial_capital_tmn="5000000",final_cash_tmn="5000000",
                orders=[],fills=[],decision_traces=[self.row])))

    def save(self, *, rebuild_requests=True):
        trace = self.row["model_trace"]
        if rebuild_requests and trace.get("host_outcome") == "MODEL_DECISION":
            read = dict(id="read-1",type="function",function=dict(name="read_market_snapshot",arguments="{}"))
            tool = dict(role="tool",tool_call_id="read-1",content=json.dumps(self.context))
            system = dict(role="system",content="synthetic instructions")
            user = dict(role="user",content="Evaluate the supplied synthetic market context.")
            assistant = dict(role="assistant",content=None,tool_calls=[read])
            trace["requests"] = [json.dumps(dict(model=trace["model"],messages=[system,user])),
                json.dumps(dict(model=trace["model"],messages=[system,user,assistant,tool]))]
            trace["responses"] = [dict(status_code=200,body=json.dumps(dict(choices=[dict(message=dict(tool_calls=[read]))]))),
                dict(status_code=200,body=json.dumps(dict(choices=[dict(message=dict(tool_calls=[dict(
                    function=dict(name="final_result",arguments=self.proposal.model_dump_json()))]))])))]
        raw = json.dumps(self.manifest).encode()
        self.source.write_bytes(raw)
        return replay.sha256(raw)

    def test_offline_replay_and_bundle_are_repeatable_without_env_or_network(self):
        sha = self.save()
        original = self.source.read_bytes()
        with patch("urllib.request.urlopen",side_effect=AssertionError("network forbidden")), \
             patch("httpx2.AsyncClient.send",side_effect=AssertionError("paid HTTP forbidden")), \
             patch("royin.model_budget.ModelBudget.reserve",side_effect=AssertionError("budget forbidden")):
            first = replay.replay_manifest(self.source,sha,self.root/"replay-a",bundle=True)
            second = replay.replay_manifest(self.source,sha,self.root/"replay-b")
        self.assertEqual(first["status"],"PASS_RECORDED_HOST_REPLAY")
        self.assertEqual(first["decisions"],second["decisions"])
        self.assertEqual(first["accounting"],second["accounting"])
        self.assertEqual(first["accounting"]["balances"]["TMN"]["free"],"5000000")
        self.assertEqual(first["execution_replay"],"EXECUTION_REPLAY_UNCONFIRMED")
        self.assertEqual(self.source.read_bytes(),original)
        self.assertEqual((self.root/"replay-a/source/manifest.json").read_bytes(),original)
        self.assertFalse((self.root/"data").exists())

    def test_replay_cannot_relabel_a_model_as_another_provider(self):
        self.row["model_trace"]["provider"]="river"
        with self.assertRaisesRegex(ValueError,"provider"):
            replay.replay_manifest(self.source,self.save(),self.root/"wrong-provider")

    def test_external_credentials_are_rejected_in_shareable_artifacts(self):
        for prefix in ("dahl_","rv_","apx_live_","cc_","SK-DEVORA-"):
            with self.subTest(prefix=prefix),self.assertRaisesRegex(ValueError,"Credential"):
                replay.reject_credentials("prefix "+prefix+"z"*40)

    def test_hash_tool_state_and_prompt_tampering_are_blocked_before_output(self):
        sha = self.save()
        self.source.write_bytes(self.source.read_bytes()+b" ")
        with self.assertRaisesRegex(ValueError,"manifest hash"):
            replay.replay_manifest(self.source,sha,self.root/"bad-hash")
        sha = self.save()
        request = json.loads(self.row["model_trace"]["requests"][1])
        request["messages"][-1]["content"] = "{}"
        self.row["model_trace"]["requests"][1] = json.dumps(request)
        with self.assertRaisesRegex(ValueError,"tool result"):
            replay.replay_manifest(self.source,self.save(rebuild_requests=False),self.root/"bad-tool")
        self.row["host_input_state"]["balances"]["TMN"]["free"] = "123"
        with self.assertRaisesRegex(ValueError,"own recorded ledger"):
            replay.replay_manifest(self.source,self.save(),self.root/"bad-state")
        self.row["host_input_state"]["balances"]["TMN"]["free"] = "5000000"
        self.row["model_trace"]["prompt_sha256"] = "c"*64
        with self.assertRaisesRegex(ValueError,"prompt"):
            replay.replay_manifest(self.source,self.save(),self.root/"bad-prompt")
        self.assertFalse(any(p.is_dir() for p in self.root.glob("bad-*")))

    def test_missing_legacy_journal_is_partial_and_fallback_is_preserved(self):
        self.manifest.pop("accounting")
        report = replay.replay_manifest(self.source,self.save(),self.root/"legacy")
        self.assertEqual(report["status"],"PARTIAL_RECORDED_HOST_REPLAY")
        self.assertEqual(report["decisions"][0]["status"],"BINDING_VERIFIED_CONTEXT_UNCONFIRMED")
        self.row["model_trace"]["host_outcome"] = "HOST_FALLBACK"
        self.row["decision"]["forecast"] = None
        report = replay.replay_manifest(self.source,self.save(),self.root/"fallback")
        self.assertEqual(report["decisions"][0]["status"],"PRESERVED_HOST_FALLBACK")

    def test_deferred_research_is_preserved_only_without_model_http_or_trade(self):
        self.row["model_trace"] = dict(host_outcome="HOST_DEFERRED",
            defer_reason="INSUFFICIENT_CLOSED_CANDLE_TIME")
        self.row["decision"]["forecast"] = None
        report = replay.replay_manifest(self.source,self.save(),self.root/"deferred")
        self.assertEqual(report["status"],"PASS_RECORDED_HOST_REPLAY")
        self.assertEqual(report["decisions"][0]["status"],"PRESERVED_HOST_DEFERRED")
        for mutation in (dict(decision={**self.row["decision"],"action":"ENTER"}),
                         dict(client_id="unexplained-order"),dict(risk={"approved":True}),
                         dict(model_trace={**self.row["model_trace"],"requests":["{}"]}),
                         dict(model_trace={**self.row["model_trace"],"responses":[{}]}),
                         dict(model_trace={**self.row["model_trace"],"defer_reason":"invented"})):
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                replay.replay_decision({**self.row,**mutation},[])

    def test_replay_output_cannot_be_scored_as_a_new_real_forecast(self):
        replay.replay_manifest(self.source,self.save(),self.root/"result")
        with self.assertRaises(ValueError),patch("urllib.request.urlopen") as network:
            scorer.current_forecasts(self.root/"result/report.json")
        network.assert_not_called()

    def test_public_capture_tamper_private_content_and_original_output_are_rejected(self):
        raw = b'{"success":true,"result":{}}'
        sha = replay.sha256(raw)
        (self.source.parent/"raw").mkdir()
        capture = self.source.parent/"raw"/(sha+".json")
        capture.write_bytes(raw+b" ")
        self.manifest["public_captures"] = [dict(endpoint="/v1/depth",query=dict(symbol="ETHTMN"),
            received_at=8101,sha256=sha)]
        with self.assertRaisesRegex(ValueError,"capture hash"):
            replay.replay_manifest(self.source,self.save(),self.root/"bad-capture")
        capture.write_bytes(raw)
        with self.assertRaisesRegex(ValueError,"separate"):
            replay.replay_manifest(self.source,self.save(),self.source.parent/"overwrite")
        self.manifest["private"] = json.dumps(dict(Authorization="test credential"))
        with self.assertRaisesRegex(ValueError,"credentials"):
            replay.replay_manifest(self.source,self.save(),self.root/"private")

    def test_partial_base_fee_cancel_and_duplicate_fills_match_hand_arithmetic(self):
        ledger = Ledger()
        ledger.initialize_portfolio(D(5000000),binding="f"*64,quote_asset="TMN")
        ledger.record_intent(client_id="b",symbol="USDTTMN",side="BUY",order_type="LIMIT",
            price=D(100),quantity=D(2),quote_fee_reserve=D(".6"),timestamp=1000)
        ledger.record_fill(fill_id="bf",client_id="b",price=D(100),quantity=D(1),fee=D(".3"),fee_asset="TMN",timestamp=1001)
        ledger.cancel_intent("b")
        ledger.record_intent(client_id="s",symbol="USDTTMN",side="SELL",order_type="LIMIT",
            price=D(110),quantity=D(".5"),timestamp=1002)
        ledger.record_fill(fill_id="sf",client_id="s",price=D(110),quantity=D(".5"),fee=D(".001"),fee_asset="USDT",timestamp=1003)
        ledger.record_intent(client_id="s2",symbol="USDTTMN",side="SELL",order_type="LIMIT",
            price=D(110),quantity=D(".499"),timestamp=1004)
        ledger.record_fill(fill_id="sf2",client_id="s2",price=D(110),quantity=D(".499"),fee=D(".16467"),fee_asset="TMN",timestamp=1005)
        with ledger.connection() as db:
            events = [dict(event_type=t,payload={k:v for k,v in json.loads(p).items() if k != "_audit_origin"})
                for t,p in db.execute("SELECT event_type,payload FROM audit_outbox WHERE event_type IN ('INTENT','FILL','CANCEL') ORDER BY id")]
        fills = [{k:e["payload"][k] for k in ("fill_id","client_id","price","quantity","fee","fee_asset","timestamp")}
            for e in events if e["event_type"] == "FILL"]
        arm = self.manifest["arms"]["paper_portfolio"]
        arm.update(orders=[{}, {}, {}],fills=fills,final_cash_tmn="5000009.42533")
        self.manifest["accounting"] = dict(schema_version=1,events=events,
            balances={"TMN":dict(free="5000009.42533",locked="0")},realized_pnl_tmn="9.42533")
        result, states = replay.replay_accounting(self.manifest)
        self.assertEqual(D(result["realized_pnl_tmn"]),D("9.42533"))
        self.assertEqual(result["closed_round_trips"],1)
        self.assertEqual([D(pnl) for pnl in result["closed_round_trip_pnls_tmn"]],[D("9.42533")])
        self.assertEqual(D(result["realized_pnl_excluding_best_trip_tmn"]),D(0))
        self.assertEqual(len(states),len(events)+1)
        self.assertEqual(D(result["balances"]["TMN"]["free"]),D("5000009.42533"))


if __name__ == "__main__":
    unittest.main()
