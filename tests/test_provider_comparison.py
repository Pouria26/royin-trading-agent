"""Fixed-input comparison semantics and no-network preflight; synthetic evidence only."""

import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, patch

from scripts import compare_model_providers as compare
from tests.test_agent_roles import position, snapshot
from tests.test_market_selection import opportunity


class ProviderComparisonTests(unittest.TestCase):
    def packet(self):
        entry,held=snapshot(),snapshot(Decimal(1))
        return dict(evidence_kind="RECORDED_PUBLIC_ROLE_CASES",cases=[
            dict(case_id="entry",snapshot=entry.to_canonical_dict(),snapshot_sha256=entry.snapshot_sha256,
                 opportunity=opportunity().model_dump(mode="json")),
            dict(case_id="position",snapshot=held.to_canonical_dict(),snapshot_sha256=held.snapshot_sha256,
                 position=position().model_dump(mode="json"))])

    def test_fixed_cases_validate_hashes_and_both_roles_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"cases.json"
            packet=self.packet()
            path.write_text(json.dumps(packet),encoding="utf-8")
            original=path.read_bytes()
            digest,cases=compare.load_cases(path)
            self.assertEqual(len(digest),64)
            self.assertEqual([case[0] for case in cases],["entry","position"])
            self.assertEqual(path.read_bytes(),original)
            packet["cases"][1]["snapshot"]["last_close"]="999"
            path.write_text(json.dumps(packet),encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"hash"):
                compare.load_cases(path)

    def test_selection_requires_all_cases_and_both_roles_and_ignores_cost(self):
        valid=[dict(host_outcome="MODEL_DECISION",role=role,elapsed_seconds=latency,http_error_statuses=[])
               for role,latency in (("ENTRY_ANALYST",4),("POSITION_REVIEWER",6))]
        faster=[{**row,"elapsed_seconds":2} for row in valid]
        blocked=[{**row,"host_outcome":"HOST_FALLBACK","http_error_statuses":[503]} for row in valid]
        report=compare.rank_operational_results({"slower":valid,"faster":faster,"unavailable":blocked},2)
        self.assertEqual(report["selected"],"faster")
        self.assertEqual(report["profitability"],"UNCONFIRMED")
        self.assertIsNone(compare.rank_operational_results({"incomplete":valid[:1],"blocked":blocked},2)["selected"])

    def test_missing_run_flag_never_reads_keys_or_starts_a_budget(self):
        arguments=["--run-id","synthetic","--cases","missing","--keys-file","missing",
            "--state-dir","missing","--output-dir","missing","--candidates","dahl:unused","devora:unused"]
        with patch.object(compare,"ModelBudget",side_effect=AssertionError("budget forbidden")):
            self.assertEqual(compare.main(arguments),2)


class ComparisonDispatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_recorded_entry_uses_current_batch_contract_not_legacy_single_snapshot(self):
        snap=snapshot()
        opp=opportunity()
        with patch.object(compare,"decide_role",new_callable=AsyncMock,return_value="synthetic-result") as role:
            self.assertEqual(await compare.run_recorded_case(snap,None,opp,config=None,budget=None,
                envelope=None,trace={}),"synthetic-result")
        kwargs=role.call_args.kwargs
        self.assertEqual(kwargs["market_batch"],{snap.symbol:(snap,opp)})
        self.assertNotIn("opportunity",kwargs)
        self.assertNotIn("position",kwargs)

    async def test_position_dispatch_retains_its_bound_position_context(self):
        snap=snapshot(Decimal(1))
        pos=position()
        with patch.object(compare,"decide_role",new_callable=AsyncMock) as role:
            await compare.run_recorded_case(snap,pos,None,config=None,budget=None,envelope=None,trace={})
        self.assertIs(role.call_args.kwargs["position"],pos)
        self.assertNotIn("market_batch",role.call_args.kwargs)
