"""Explicit multi-credential funding on the original reservation ledger."""

import hashlib
import json
import os
import re
import sqlite3
import time
from contextlib import closing
from datetime import timedelta, timezone
from decimal import ROUND_CEILING, Decimal
from pathlib import Path

from royin.model_budget import BudgetBlocked

NANO = 1_000_000_000


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


def credentials(path):
    """Secrets stay outside source, env changes, model inputs and reservation rows."""
    path = Path(path)
    try:
        if path.is_symlink() or path.stat().st_size > 8192:
            raise ValueError
        if os.name != "nt" and path.stat().st_mode & 0o077:
            raise ValueError
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not 1 <= len(data) <= 3:
            raise ValueError
        if any(not isinstance(key, str) or not re.fullmatch(r"box-ai-[A-Za-z0-9_-]{24,128}", key)
               or sha(key) != fingerprint for fingerprint, key in data.items()):
            raise ValueError
        return data
    except (OSError, ValueError, TypeError, AttributeError):
        raise BudgetBlocked("BLOCKED_POOL_CREDENTIALS: restore the private credential file") from None


class BoxAPIPool:
    def __init__(self, budget, pool_id, expected_sha256):
        if (not budget.require_existing or not budget.credit_id or not budget.is_priced_usd
                or not re.fullmatch(r"boxapi-pool-[a-z0-9_-]{1,40}", pool_id or "")
                or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256 or "")):
            raise BudgetBlocked("Explicit funded pool binding required")
        self.budget, self.pool_id, self.expected_sha256 = budget, pool_id, expected_sha256
        self.keys_path = budget.path.resolve().parent / "boxapi-pool-keys.private.json"
        with closing(budget.connect()) as db:
            self.authority = self.validate(db)
        self.total_limit = Decimal(self.authority["limit_nano_usd"]) / NANO
        self.max_requests = self.authority["max_requests"]
        self.token_limit = self.authority["token_limit"]

    def validate(self, db):
        try:
            row = db.execute("SELECT authority_json,authority_sha256 FROM boxapi_pools WHERE pool_id=?",
                             (self.pool_id,)).fetchone()
            body = json.loads(row[0]) if row else None
            if (not row or sha(row[0]) != self.expected_sha256 or row[1] != self.expected_sha256
                    or body["pool_id"] != self.pool_id or body["anchor_credit_id"] != self.budget.credit_id
                    or body["anchor_credential_sha256"] != sha(self.budget.config.model_api_key.get_secret_value())
                    or body["reservation_policy_sha256"] != self.budget.policy_hash
                    or body["model"] != self.budget.config.LLM_MODEL
                    or body["spend_fraction"] != "0.85" or body["daily_limit"] is not None
                    or body["independent_accounts_confirmed"] is not True
                    or type(body["expires_at"]) is not int
                    or type(body["max_requests"]) is not int or not 1 <= body["max_requests"] <= 4096
                    or type(body["token_limit"]) is not int or body["token_limit"] <= 0
                    or len(body["members"]) != 3):
                raise ValueError
            members = body["members"]
            keys = credentials(self.keys_path)
            if set(keys) != {m["credential_sha256"] for m in members} or len(keys) != 3:
                raise ValueError
            for member in members:
                if (type(member["available_nano_usd"]) is not int or member["available_nano_usd"] <= 0
                        or member["limit_nano_usd"] != int(Decimal(member["available_nano_usd"]) * Decimal(".85"))):
                    raise ValueError
            if body["limit_nano_usd"] != sum(m["limit_nano_usd"] for m in members):
                raise ValueError
            return body
        except (KeyError, TypeError, ValueError, sqlite3.Error):
            raise BudgetBlocked("BLOCKED_INVALID_DURABLE_STATE: pool authority or credentials") from None

    @staticmethod
    def authorize(budget, *, pool_id, members, expires_at, independent_accounts_confirmed, reason):
        """Append authority once; previously recorded grants/reservations are never changed."""
        if (not budget.require_existing or not budget.credit_id or not budget.is_priced_usd
                or getattr(budget, "pool", None) is not None
                or not re.fullmatch(r"boxapi-pool-[a-z0-9_-]{1,40}", pool_id or "")
                or independent_accounts_confirmed is not True or not isinstance(reason, str) or not reason.strip()
                or type(expires_at) is not int or not int(time.time()) < expires_at <= int(time.time()) + 345600
                or not isinstance(members, list) or len(members) != 3):
            raise BudgetBlocked("Explicit independent-account pool authority required")
        keys = credentials(budget.path.resolve().parent / "boxapi-pool-keys.private.json")
        if set(keys) != {m.get("credential_sha256") for m in members} or len(keys) != 3:
            raise BudgetBlocked("Pool member credentials do not match")
        anchor = sha(budget.config.model_api_key.get_secret_value())
        if anchor not in keys:
            raise BudgetBlocked("Original funded credential must anchor the pool")
        clean = []
        for member in members:
            amount = member.get("available_nano_usd")
            if (type(amount) is not int or not 0 < amount <= 100 * NANO
                    or member.get("basis") not in ("USER_REPORTED_REMAINING", "UNSPENT_DURABLE_ALLOWANCE")
                    or not re.fullmatch(r"[0-9a-f]{64}", member.get("evidence_sha256", ""))):
                raise BudgetBlocked("Exact remaining credit and evidence required")
            clean.append(dict(credential_sha256=member['credential_sha256'],available_nano_usd=amount,
                basis=member['basis'],evidence_sha256=member['evidence_sha256'],
                limit_nano_usd=int(Decimal(amount) * Decimal(".85"))))
        cost = (budget.policy["max_input_tokens"] * budget.input_rate
                + budget.policy["max_output_tokens"] * budget.output_rate) / Decimal(1_000_000)
        unit_nano = int((cost * NANO).to_integral_value(rounding=ROUND_CEILING))
        total = sum(m["limit_nano_usd"] for m in clean)
        requests = total // unit_nano
        if not 2 <= requests <= 4096:
            raise BudgetBlocked("Pool request allowance out of bounds")
        with closing(budget.connect()) as db, db:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            budget.validate_durable(db)
            if (db.execute("SELECT 1 FROM sqlite_master WHERE name='boxapi_pools'").fetchone()
                    and db.execute("SELECT 1 FROM boxapi_pools WHERE pool_id=? OR anchor_credit_id=?",
                                   (pool_id, budget.credit_id)).fetchone()):
                raise BudgetBlocked("Pool already authorized; restore it, never reinitialize")
            db.execute("CREATE TABLE IF NOT EXISTS boxapi_pools (pool_id TEXT PRIMARY KEY,"
                       "anchor_credit_id TEXT NOT NULL UNIQUE,authority_json TEXT NOT NULL,"
                       "authority_sha256 TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS boxapi_pool_reservations (reservation_id INTEGER PRIMARY KEY,"
                       "pool_id TEXT NOT NULL,credential_sha256 TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS boxapi_pool_health (pool_id TEXT NOT NULL,"
                       "credential_sha256 TEXT NOT NULL,blocked_until INTEGER NOT NULL,"
                       "permanent INTEGER NOT NULL,last_http INTEGER,PRIMARY KEY(pool_id,credential_sha256))")
            baseline = db.execute("SELECT MAX(id) FROM model_reservations").fetchone()[0]
            # Anchor allowance is observed under the same transaction as authorization.
            used = db.execute("SELECT COALESCE(SUM(nano_usd),0) FROM model_reservations WHERE credit_id=?",
                              (budget.credit_id,)).fetchone()[0]
            remaining = int(budget.total_limit * NANO) - used
            if next(m for m in clean if m["credential_sha256"] == anchor)["available_nano_usd"] > remaining:
                raise BudgetBlocked("Anchor credit exceeds its unspent durable allowance")
            body = dict(schema_version=1, pool_id=pool_id, anchor_credit_id=budget.credit_id,
                anchor_credential_sha256=anchor, members=clean, spend_fraction="0.85", limit_nano_usd=total,
                daily_limit=None, max_requests=requests,
                token_limit=requests * (budget.policy["max_input_tokens"] + budget.policy["max_output_tokens"]),
                reservation_policy_sha256=budget.policy_hash, model=budget.config.LLM_MODEL,
                independent_accounts_confirmed=True, baseline_reservation_id=baseline,
                authorized_at=int(time.time()), expires_at=expires_at, operator_instruction_sha256=sha(reason))
            raw = canonical(body)
            authority_hash = sha(raw)
            db.execute("INSERT INTO boxapi_pools VALUES (?,?,?,?)", (pool_id, budget.credit_id, raw, authority_hash))
            db.executemany("INSERT INTO boxapi_pool_health VALUES (?,?,0,0,NULL)",
                           [(pool_id, m["credential_sha256"]) for m in clean])
        return dict(pool_id=pool_id, authority_sha256=authority_hash, limit_usd=str(Decimal(total) / NANO),
                    max_requests=requests, reservations_reset=False)

    def reserve(self, *, now, cost, tokens, preferred=None):
        """Reserve both per-key and aggregate cost atomically before choosing Authorization."""
        epoch = int(now.timestamp())
        nano = int((cost * NANO).to_integral_value(rounding=ROUND_CEILING))
        day = now.astimezone(timezone(timedelta(hours=3, minutes=30))).date().isoformat()
        with closing(self.budget.connect()) as db, db:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            self.budget.validate_durable(db)
            body = self.validate(db)
            if not body["authorized_at"] <= epoch < body["expires_at"]:
                raise BudgetBlocked("Pool funding expired or clock is before authorization")
            rows = db.execute("SELECT r.nano_usd,r.tokens,p.credential_sha256,r.credit_id,r.id FROM model_reservations r "
                "JOIN boxapi_pool_reservations p ON p.reservation_id=r.id WHERE p.pool_id=?",
                (self.pool_id,)).fetchall()
            count = db.execute("SELECT COUNT(*) FROM model_reservations WHERE credit_id=?", (self.pool_id,)).fetchone()[0]
            if count != len(rows) or any(r[2] not in {m['credential_sha256'] for m in body['members']}
                    or r[3] != self.pool_id or r[4] <= body['baseline_reservation_id'] for r in rows):
                raise BudgetBlocked("Pool reservation attribution mismatch")
            used = sum(r[0] for r in rows)
            if (count >= body["max_requests"] or used + nano > body["limit_nano_usd"]
                    or sum(r[1] for r in rows) + tokens > body["token_limit"]):
                raise BudgetBlocked("Persistent model budget exhausted; no request sent")
            health = {r[0]:r[1:] for r in db.execute("SELECT credential_sha256,blocked_until,permanent "
                       "FROM boxapi_pool_health WHERE pool_id=?", (self.pool_id,))}
            choices = []
            for index, member in enumerate(body["members"]):
                fp = member["credential_sha256"]
                consumed = sum(r[0] for r in rows if r[2] == fp)
                if consumed > member["limit_nano_usd"]:
                    raise BudgetBlocked("Pool member allowance exceeded")
                if (fp not in health or (preferred is not None and fp != preferred)
                        or health[fp][1] or health[fp][0] > epoch
                        or consumed + nano > member["limit_nano_usd"]):
                    continue
                choices.append((Decimal(consumed) / member["limit_nano_usd"], index, fp))
            if not choices:
                temporary = any(not health.get(m['credential_sha256'], (0,1))[1]
                    and sum(r[0] for r in rows if r[2] == m['credential_sha256']) + nano <= m['limit_nano_usd']
                    for m in body['members'])
                raise BudgetBlocked("Pool credentials are temporarily unavailable" if temporary
                    else "Persistent model budget exhausted; no request sent")
            chosen = min(choices)[2]
            key = credentials(self.keys_path)[chosen]
            cursor = db.execute("INSERT INTO model_reservations(day,nano_usd,tokens,model,policy_hash,credit_id) "
                "VALUES (?,?,?,?,?,?)", (day,nano,tokens,self.budget.config.LLM_MODEL,self.budget.policy_hash,self.pool_id))
            db.execute("INSERT INTO boxapi_pool_reservations VALUES (?,?,?)", (cursor.lastrowid,self.pool_id,chosen))
        return chosen, key

    def observe(self, fingerprint, status):
        if not re.fullmatch(r"[0-9a-f]{64}", fingerprint or ""):
            return
        if status == 200:
            return
        permanent = int(status in (401, 402, 403))
        cooldown = 900 if status == 429 else 60
        with closing(self.budget.connect()) as db, db:
            db.execute("UPDATE boxapi_pool_health SET blocked_until=MAX(blocked_until,?),permanent=MAX(permanent,?),last_http=? "
                       "WHERE pool_id=? AND credential_sha256=?",
                       (int(time.time())+cooldown,permanent,status,self.pool_id,fingerprint))
