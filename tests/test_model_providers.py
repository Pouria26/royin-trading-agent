"""Provider boundaries and durable unpriced usage; synthetic traffic, no return claims."""

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from decimal import Decimal
from pathlib import Path

import httpx2
from pydantic import ValidationError

from royin.config import RuntimeConfig
from royin.model_budget import BudgetBlocked, ModelBudget
from royin.model_profiles import PROVIDER_MODELS, PROVIDER_ORIGINS


def external_config(provider="dahl", **updates):
    values=dict(LLM_PROVIDER=provider,LLM_BASE_URL=PROVIDER_ORIGINS[provider],
        LLM_MODEL=PROVIDER_MODELS[provider][0],LLM_TOKEN_BUDGET=200000,
        **{provider.upper()+"_API_KEY":"synthetic-"+provider+"-secret"})
    return RuntimeConfig(**(values | updates))


class ModelProviderTests(unittest.TestCase):
    def test_provider_origin_and_model_must_match_and_secrets_stay_excluded(self):
        for provider in ("devora","dahl","river","apmix","codecraft"):
            config=external_config(provider)
            self.assertIsNotNone(config.model_api_key)
            self.assertNotIn("synthetic-",config.model_dump_json())
            for bad in (dict(LLM_BASE_URL="https://attacker.invalid/v1"),
                        dict(LLM_MODEL="gpt-6-luna"),dict(LLM_MODEL="../model")):
                with self.subTest(provider=provider,bad=bad),self.assertRaises(ValidationError):
                    external_config(provider,**bad)

    def test_external_ledger_requires_explicit_initialization_and_original_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"usage.sqlite3"
            config=external_config()
            with self.assertRaises(BudgetBlocked):
                ModelBudget(config,path,require_existing=True)
            self.assertFalse(path.exists())
            ModelBudget.initialize_provider_state(config,path)
            budget=ModelBudget(config,path,require_existing=True)
            self.assertFalse(budget.is_priced_usd)
            budget.reserve()
            with self.assertRaises(BudgetBlocked):
                ModelBudget(external_config(DAHL_API_KEY="different-secret"),path,require_existing=True)
            with self.assertRaises((BudgetBlocked,FileExistsError)):
                ModelBudget.initialize_provider_state(config,path)
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM model_reservations").fetchone()[0],1)
            path.unlink()
            with self.assertRaises(BudgetBlocked):
                budget.reserve()
            self.assertFalse(path.exists())

    def test_external_restart_cannot_raise_durable_token_cap_or_reuse_box_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"usage.sqlite3"
            config=external_config(LLM_TOKEN_BUDGET=73728)
            ModelBudget.initialize_provider_state(config,path)
            ModelBudget(config,path,require_existing=True).reserve()
            raised=ModelBudget(external_config(LLM_TOKEN_BUDGET=1000000),path,require_existing=True)
            with self.assertRaises(BudgetBlocked):
                raised.reserve()
            with self.assertRaises(BudgetBlocked):
                ModelBudget(RuntimeConfig(LLM_TOKEN_BUDGET=6000000,LLM_COST_BUDGET="2.40",
                    LLM_COST_CURRENCY="USD"),path,require_existing=True)

    def test_external_request_rejects_wrong_origin_model_and_oversized_output_before_reserve(self):
        import asyncio
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"usage.sqlite3"
            config=external_config()
            ModelBudget.initialize_provider_state(config,path)
            budget=ModelBudget(config,path,require_existing=True)
            for url,model,limit in (("https://attacker.invalid/v1/chat/completions",config.LLM_MODEL,8192),
                    (config.LLM_BASE_URL+"/chat/completions","unknown",8192),
                    (config.LLM_BASE_URL+"/chat/completions",config.LLM_MODEL,8193)):
                with self.subTest(url=url,model=model,limit=limit),self.assertRaises(BudgetBlocked):
                    asyncio.run(budget.before_request(httpx2.Request("POST",url,
                        content=json.dumps(dict(model=model,max_tokens=limit)))))
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM model_reservations").fetchone()[0],0)


if __name__=="__main__":
    unittest.main()


class ExternalRoleWireTests(unittest.IsolatedAsyncioTestCase):
    async def test_river_and_apmix_wire_parameters_match_the_documented_gateway(self):
        from tests.test_agent_roles import RoleTests
        for provider in ("river","apmix","codecraft"):
            with self.subTest(provider=provider):
                role=RoleTests()
                role.config=external_config(provider)
                decision,trace,bodies=await role.call(quantity=Decimal(1),action="EXIT")
                self.assertEqual(decision.action,"EXIT")
                self.assertEqual(trace["provider"],provider)
                self.assertTrue(all(body["max_tokens"]==8192 for body in bodies))
                self.assertNotIn("thinking",bodies[0])
                if provider=="river":
                    self.assertEqual(bodies[0]["reasoning_effort"],"none")
                else:
                    self.assertNotIn("reasoning_effort",bodies[0])

    async def test_minimax_uses_legacy_token_field_and_preserves_thinking_on_tool_return(self):
        from tests.test_agent_roles import RoleTests
        role=RoleTests()
        role.config=external_config()
        decision,trace,bodies=await role.call(quantity=Decimal(1),action="EXIT",
            tool_thinking="<think>Synthetic protocol state</think>")
        self.assertEqual(decision.action,"EXIT")
        self.assertEqual(trace["provider"],"dahl")
        self.assertEqual(trace["evidence_kind"],"FAKE_MODEL")
        self.assertTrue(all(body["max_tokens"]==8192 and "max_completion_tokens" not in body for body in bodies))
        assistant=next(m for m in bodies[1]["messages"] if m["role"]=="assistant")
        self.assertIn("Synthetic protocol state",assistant["content"])
        self.assertNotIn("reasoning_effort",bodies[0])
