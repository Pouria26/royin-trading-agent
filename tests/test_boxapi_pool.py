"""Synthetic funding, credential selection and continuity; no provider or exchange HTTP."""

import asyncio
import hashlib
import json
import sqlite3
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from pathlib import Path

import httpx2
from openai import APITimeoutError, AsyncOpenAI

from royin.agent import RoleRunEnvelope
from royin.boxapi_pool import BoxAPIPool
from royin.config import RuntimeConfig
from royin.model_budget import BudgetBlocked, ModelBudget
from royin.service_contract import ServiceContract
from tests.test_multiday_service import policy


class BoxAPIPoolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'original.sqlite3'
        self.keys = ['box-ai-' + letter * 48 for letter in ('a','b','c')]
        self.fps = [hashlib.sha256(k.encode()).hexdigest() for k in self.keys]
        self.file = self.root / 'boxapi-pool-keys.private.json'
        self.file.write_text(json.dumps(dict(zip(self.fps,self.keys,strict=True))))
        self.file.chmod(0o600)
        legacy = RuntimeConfig(BOXAPI_API_KEY='synthetic-legacy', LLM_COST_BUDGET='2.40',
                               LLM_COST_CURRENCY='USD', LLM_TOKEN_BUDGET=6000000)
        ModelBudget(legacy,self.path).reserve()
        self.config = RuntimeConfig(BOXAPI_API_KEY=self.keys[0],BOXAPI_CREDIT_ID='original-funded',
            LLM_COST_BUDGET='2.822355',LLM_COST_CURRENCY='USD',LLM_TOKEN_BUDGET=22000000)
        ModelBudget.initialize_boxapi_credit(self.config,self.path,reported_credit_usd='2.9709',reason='test-credit')
        self.original = ModelBudget(self.config,self.path,require_existing=True)
        self.original.reserve()
        self.pool_id = 'boxapi-pool-test'

    def authorize(self, amounts=('2.5','2.4555','2.5'), **changes):
        members = [dict(credential_sha256=fp,available_nano_usd=int(D(amount)*1000000000),
            basis='UNSPENT_DURABLE_ALLOWANCE' if i==0 else 'USER_REPORTED_REMAINING',
            evidence_sha256=str(i)*64) for i,(fp,amount) in enumerate(zip(self.fps,amounts,strict=True))]
        self.receipt = BoxAPIPool.authorize(self.original, **(dict(pool_id=self.pool_id,members=members,
            expires_at=int(time.time())+86400,independent_accounts_confirmed=True,
            reason='Synthetic explicit85percent independent-account authority') | changes))
        return self.receipt

    def budget(self):
        return ModelBudget(self.config,self.path,require_existing=True,pool_id=self.pool_id,
                           pool_sha256=self.receipt['authority_sha256'])

    def rows(self):
        with closing(sqlite3.connect(self.path)) as db:
            return db.execute('SELECT * FROM model_reservations ORDER BY id').fetchall()

    def request(self):
        return httpx2.Request('POST','https://ai.boxapi.ir/ai/v1/chat/completions',
            headers={'Authorization':'Bearer '+self.keys[0]},json={'model':'gpt-6-luna','max_completion_tokens':16})

    def test_exact85percent_authority_preserves_original_grants_and_reservations(self):
        before = self.rows()
        with closing(sqlite3.connect(self.path)) as db:
            grant = db.execute('SELECT * FROM boxapi_credits').fetchall()
        receipt = self.authorize()
        self.assertEqual(D(receipt['limit_usd']), D('6.337175'))
        b = self.budget()
        self.assertIsNone(b.daily_limit)
        self.assertEqual(b.total_limit,D('6.337175'))
        self.assertEqual(self.rows(),before)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT * FROM boxapi_credits').fetchall(),grant)
        with self.assertRaisesRegex(BudgetBlocked,'already authorized'):
            self.authorize()

    def test_all_three_keys_are_selected_before_http_and_only_hashes_are_persisted(self):
        self.authorize()
        b = self.budget()
        chosen = []
        for _ in range(3):
            req = self.request()
            asyncio.run(b.before_request(req))
            chosen.append(req.headers['Authorization'])
            self.assertEqual(req.extensions['royin_pool_id'],self.pool_id)
        self.assertEqual(chosen,['Bearer '+k for k in self.keys])
        with closing(sqlite3.connect(self.path)) as db:
            dump = '\n'.join(db.iterdump())
        for key in self.keys:
            self.assertNotIn(key,dump)
        self.assertEqual(len(self.rows()),5)

    def test_atomic_per_key_limits_restart_and_next_day_never_refund(self):
        self.authorize(amounts=('.02','.02','.02'))
        before = self.rows()
        def reserve(_):
            try:
                self.budget().reserve()
                return True
            except BudgetBlocked:
                return False
        with ThreadPoolExecutor(max_workers=4) as workers:
            self.assertEqual(sum(workers.map(reserve,range(16))),9)
        self.assertEqual(self.rows()[:len(before)],before)
        b = self.budget()
        with self.assertRaises(BudgetBlocked):
            b.reserve()
        with self.assertRaises(BudgetBlocked):
            b.reserve(now=datetime.now(UTC)+timedelta(hours=20))
        self.assertEqual(len(self.rows()),len(before)+9)

    def test_daily_caps_removed_only_for_explicit_pool_not_legacy_funding(self):
        self.authorize()
        self.assertEqual(self.original.daily_limit,D('1.10'))
        self.assertIsNone(self.budget().daily_limit)
        with self.assertRaises(BudgetBlocked):
            ModelBudget(self.config,self.path,require_existing=True)
        legacy=self.config.model_copy(update={'BOXAPI_CREDIT_ID':None})
        with self.assertRaises(BudgetBlocked):
            ModelBudget(legacy,self.path,require_existing=True)
        with self.assertRaises(BudgetBlocked):
            ModelBudget(self.config,self.path,require_existing=True,pool_id=self.pool_id,pool_sha256='f'*64)

    def test_missing_or_changed_credentials_and_deleted_ledger_block_before_http(self):
        self.authorize()
        b = self.budget()
        before = self.rows()
        self.file.write_text(json.dumps({self.fps[0]:self.keys[1]}))
        with self.assertRaises(BudgetBlocked):
            asyncio.run(b.before_request(self.request()))
        self.assertEqual(self.rows(),before)
        self.path.unlink()
        with self.assertRaises(BudgetBlocked):
            self.budget()
        self.assertFalse(self.path.exists())

    def test_shared_account_unconfirmed_and_anchor_overallocation_are_rejected(self):
        before = self.rows()
        with self.assertRaises(BudgetBlocked):
            self.authorize(independent_accounts_confirmed=False)
        with self.assertRaises(BudgetBlocked):
            self.authorize(amounts=('2.9','2.5','2.5'))
        self.assertEqual(self.rows(),before)

    def test_authority_never_persists_unrecognized_secret_fields(self):
        members=[dict(credential_sha256=fp,available_nano_usd=10000000,basis='USER_REPORTED_REMAINING',
            evidence_sha256='a'*64,key=key) for fp,key in zip(self.fps,self.keys,strict=True)]
        BoxAPIPool.authorize(self.original,pool_id=self.pool_id,members=members,expires_at=int(time.time())+3600,
            independent_accounts_confirmed=True,reason='Synthetic redaction check')
        with closing(sqlite3.connect(self.path)) as db:
            dump='\n'.join(db.iterdump())
        for key in self.keys:
            self.assertNotIn(key,dump)

    def test_provider_failure_is_charged_and_next_request_uses_another_key_without_retry(self):
        self.authorize()
        b = self.budget()
        req = self.request()
        asyncio.run(b.before_request(req))
        failed = req.extensions['royin_pool_member']
        asyncio.run(b.after_response(httpx2.Response(402,request=req)))
        for _ in range(6):
            req = self.request()
            asyncio.run(b.before_request(req))
            self.assertNotEqual(req.extensions['royin_pool_member'],failed)
        self.assertEqual(len(self.rows()),9)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM boxapi_pool_reservations WHERE credential_sha256=?',
                                        (failed,)).fetchone()[0],1)
        b.pool.observe(failed,429)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT permanent FROM boxapi_pool_health WHERE credential_sha256=?',
                                        (failed,)).fetchone()[0],1)

    def test_actual_sdk_sends_rotated_authorization_with_unchanged_model_and_no_extra_retry(self):
        self.authorize()
        b=self.budget()
        seen=[]
        def handler(request):
            seen.append(request.headers['Authorization'])
            payload=json.loads(request.content)
            self.assertEqual(payload['model'],'gpt-6-luna')
            self.assertNotIn('box-ai-',request.content.decode())
            return httpx2.Response(200,json=dict(id='synthetic',object='chat.completion',created=1,
                model='gpt-6-luna',choices=[dict(index=0,message=dict(role='assistant',content='OK'),finish_reason='stop')]))
        async def exercise():
            async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler),
                event_hooks={'request':[b.before_request],'response':[b.after_response]}) as client:
                sdk=AsyncOpenAI(api_key=self.keys[0],base_url='https://ai.boxapi.ir/ai/v1',http_client=client,max_retries=0)
                for _ in range(3):
                    output=await sdk.chat.completions.create(model='gpt-6-luna',
                        messages=[dict(role='user',content='Return OK')],max_completion_tokens=16)
                    self.assertEqual(output.choices[0].message.content,'OK')
        asyncio.run(exercise())
        self.assertEqual(seen,['Bearer '+k for k in self.keys])

    def test_sdk_timeout_remains_charged_once_and_survives_reconstruction(self):
        self.authorize()
        b=self.budget()
        seen=[]
        def handler(request):
            seen.append(request.headers['Authorization'])
            raise httpx2.ReadTimeout('synthetic timeout',request=request)
        async def exercise():
            async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler),event_hooks={'request':[b.before_request]}) as client:
                sdk=AsyncOpenAI(api_key=self.keys[0],base_url='https://ai.boxapi.ir/ai/v1',http_client=client,max_retries=0)
                with self.assertRaises(APITimeoutError):
                    await sdk.chat.completions.create(model='gpt-6-luna',messages=[dict(role='user',content='OK')],max_completion_tokens=16)
        asyncio.run(exercise())
        self.assertEqual(len(seen),1)
        self.assertEqual(len(self.rows()),3)
        req=self.request()
        asyncio.run(self.budget().before_request(req))
        self.assertNotEqual(req.headers['Authorization'],seen[0])
        self.assertEqual(len(self.rows()),4)

    def test_new_pool_scope_preserves_old_scope_and_original_mission_clock(self):
        start=datetime.now(UTC)-timedelta(hours=1)
        values=policy().model_dump()
        values.update(started_at=start,submission_deadline_at=start+timedelta(minutes=30),
            finalize_start_at=start+timedelta(hours=20),trading_end_at=start+timedelta(hours=21))
        contract=ServiceContract(**values)
        old = RoleRunEnvelope(self.original,scope_id=contract.service_id,
            duration_seconds=contract.duration_seconds,service_contract=contract)
        old.claim_run()
        with closing(sqlite3.connect(self.path)) as db:
            before=db.execute('SELECT * FROM role_run_envelopes').fetchall()
        self.authorize()
        new=RoleRunEnvelope(self.budget(),scope_id=contract.service_id,
            duration_seconds=contract.duration_seconds,service_contract=contract)
        new.claim_run()
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT * FROM role_run_envelopes WHERE scope=?',(old.scope_id,)).fetchall(),before)
            self.assertEqual(db.execute('SELECT started FROM role_run_envelopes WHERE scope=?',(new.scope_id,)).fetchone()[0],
                contract.started_at.timestamp())
        restored=RoleRunEnvelope(self.budget(),scope_id=contract.service_id,
            duration_seconds=contract.duration_seconds,service_contract=contract)
        self.assertEqual(restored.agent_runs,1)
        self.assertNotEqual(new.scope_id,old.scope_id)
