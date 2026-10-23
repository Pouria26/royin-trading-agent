"""Reserve conservative USD/token limits durably before each BoxAPI request."""

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta, timezone
from decimal import ROUND_CEILING, Decimal
from pathlib import Path

from royin.market_data import decimal_number
from royin.model_profiles import PROVIDER_MODELS

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "config/llm-budget-policy.json"


class BudgetBlocked(ValueError):
    pass


class ModelBudget:
    def __init__(self, config, path=None, *, audit=None, require_existing=False):
        self.audit = audit
        self.config = config
        self.is_priced_usd = config.LLM_PROVIDER == "boxapi"
        self.credit_id = config.BOXAPI_CREDIT_ID if self.is_priced_usd else None
        if self.credit_id and not require_existing:
            raise BudgetBlocked("Funded credit requires the original durable ledger")
        name = "llm-budget.sqlite3" if self.is_priced_usd else f"{config.LLM_PROVIDER}-model-usage.sqlite3"
        self.path = Path(path) if path is not None else ROOT / "data" / name
        self.require_existing = require_existing
        if not self.is_priced_usd and not require_existing:
            raise BudgetBlocked("External provider usage requires explicit one-time initialization")
        if require_existing:
            with closing(self.connect()) as db:
                self.validate_durable(db)
        if not self.is_priced_usd:
            self.policy = dict(version=1,billing_mode="UNPRICED_USER_AUTHORIZED",provider=config.LLM_PROVIDER,
                max_requests_total=8192,max_requests_daily=8192,max_input_tokens=65536,max_output_tokens=8192)
            self.policy_hash = hashlib.sha256(json.dumps(self.policy,sort_keys=True).encode()).hexdigest()
            if config.LLM_TOKEN_BUDGET is None or config.LLM_TOKEN_BUDGET <= 0:
                raise BudgetBlocked("Explicit positive token bound required for an external experiment")
            self.total_limit = self.daily_limit = None
            # Zero is internal arithmetic only; no USD price or invoice is asserted.
            self.input_rate = self.output_rate = Decimal(0)
            return
        raw = POLICY_PATH.read_bytes()
        self.policy = json.loads(raw)
        self.policy_hash = hashlib.sha256(raw).hexdigest()
        p = self.policy
        if (
            p["currency"] != "USD"
            or config.LLM_COST_CURRENCY != "USD"
            or (config.LLM_COST_BUDGET is None or config.LLM_TOKEN_BUDGET is None)
        ):
            raise BudgetBlocked("Explicit USD and token budgets are required")
        if self.credit_id:
            with closing(self.connect()) as db:
                grant = self._credit(db)
            self.total_limit = min(Decimal(grant[1]) / 1_000_000_000, config.LLM_COST_BUDGET)
            self.daily_limit = Decimal(grant[2]) / 1_000_000_000
            self.policy.update({k: p["funded_credit"][k] for k in ("max_requests_total", "max_requests_daily")})
        else:
            self.total_limit = min(decimal_number(p["total_limit_usd"]), config.LLM_COST_BUDGET)
            if not 0 < self.total_limit <= Decimal("2.40"):
                raise BudgetBlocked("Budget must preserve at least USD 0.60 of the reported USD 3")
            self.daily_limit = decimal_number(p["daily_limit_usd"])
            if not 0 < self.daily_limit <= Decimal("0.80"):
                raise BudgetBlocked("Daily budget exceeds the three-day allocation")
        rate = p["rates_per_million"][config.LLM_MODEL]
        self.input_rate = decimal_number(rate["input"], positive=True)
        self.output_rate = decimal_number(rate["output"], positive=True)

    def connect(self):
        """Continuation never creates a replacement ledger, including after deletion races."""
        if self.require_existing:
            try:
                return sqlite3.connect(self.path.resolve().as_uri() + "?mode=rw", uri=True, timeout=2)
            except sqlite3.Error as exc:
                raise BudgetBlocked("BLOCKED_MISSING_DURABLE_STATE: restore the original model budget") from exc
        self.path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self.path, timeout=2)

    @staticmethod
    def validate_existing(db, *, allow_empty=False):
        try:
            if db.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise BudgetBlocked("BLOCKED_INVALID_DURABLE_STATE: model budget integrity")
            rows = db.execute("SELECT day,nano_usd,tokens,model,policy_hash FROM model_reservations").fetchall()
            if (not rows and not allow_empty) or any(
                not isinstance(day, str) or type(cost) is not int or cost < 0
                or type(tokens) is not int or tokens <= 0 or not model
                or not isinstance(sha, str) or len(sha) != 64
                for day, cost, tokens, model, sha in rows
            ):
                raise BudgetBlocked("BLOCKED_INVALID_DURABLE_STATE: continuation requires prior reservations")
        except sqlite3.Error as exc:
            raise BudgetBlocked("BLOCKED_INVALID_DURABLE_STATE: model reservation schema") from exc

    def validate_durable(self, db):
        self.validate_existing(db,allow_empty=not self.is_priced_usd)
        if self.credit_id:
            self._credit(db)
        elif self.is_priced_usd and db.execute(
                "SELECT 1 FROM sqlite_master WHERE name='boxapi_credits'").fetchone():
            key = self.config.model_api_key
            fingerprint = hashlib.sha256(key.get_secret_value().encode()).hexdigest() if key else None
            if db.execute("SELECT 1 FROM boxapi_credits WHERE credential_sha256=?", (fingerprint,)).fetchone():
                raise BudgetBlocked("Funded BoxAPI key requires its original credit allocation")
        try:
            binding = dict(db.execute("SELECT key,value FROM provider_usage_binding"))
        except sqlite3.OperationalError:
            if self.is_priced_usd:
                return
            raise BudgetBlocked("BLOCKED_INVALID_DURABLE_STATE: missing provider initialization") from None
        if self.is_priced_usd:
            raise BudgetBlocked("External usage state cannot replace the original BoxAPI budget")
        key = self.config.model_api_key
        expected = hashlib.sha256(key.get_secret_value().encode()).hexdigest() if key else None
        if (binding.get("provider") != self.config.LLM_PROVIDER or binding.get("credential_sha256") != expected
                or not str(binding.get("token_limit","")).isdigit() or int(binding["token_limit"]) <= 0):
            raise BudgetBlocked("BLOCKED_INVALID_DURABLE_STATE: provider/key/limit binding changed")
        if any(row[0] not in PROVIDER_MODELS[self.config.LLM_PROVIDER]
                for row in db.execute("SELECT DISTINCT model FROM model_reservations")):
            raise BudgetBlocked("BLOCKED_INVALID_DURABLE_STATE: model belongs to another provider")

    def _credit(self, db):
        try:
            row = db.execute("SELECT credential_sha256,limit_nano_usd,daily_nano_usd,token_limit "
                "FROM boxapi_credits WHERE credit_id=?", (self.credit_id,)).fetchone()
            columns = {r[1] for r in db.execute("PRAGMA table_info(model_reservations)")}
        except sqlite3.Error:
            raise BudgetBlocked("BLOCKED_MISSING_DURABLE_STATE: funded BoxAPI allocation") from None
        key = self.config.model_api_key
        fingerprint = hashlib.sha256(key.get_secret_value().encode()).hexdigest() if key else None
        funded = json.loads(POLICY_PATH.read_bytes())["funded_credit"]
        cap = decimal_number(funded["max_reported_credit_usd"]) * decimal_number(funded["spend_fraction"])
        if (not row or row[0] != fingerprint or "credit_id" not in columns
                or any(type(n) is not int or n <= 0 for n in row[1:])
                or Decimal(row[1]) > cap * 1_000_000_000
                or Decimal(row[2]) > decimal_number(funded["daily_limit_usd"]) * 1_000_000_000):
            raise BudgetBlocked("BLOCKED_INVALID_DURABLE_STATE: funded provider/key/limit binding")
        return row

    @staticmethod
    def initialize_boxapi_credit(config, path, *, reported_credit_usd, reason):
        """Append a separately funded key allowance to the original ledger; never reset spend."""
        import re

        if (config.LLM_PROVIDER != "boxapi" or not config.BOXAPI_CREDIT_ID or not config.model_api_key
                or not isinstance(reason, str) or not re.fullmatch(r"[a-z0-9-]{1,64}", reason)
                or config.LLM_COST_CURRENCY != "USD" or not config.LLM_TOKEN_BUDGET):
            raise BudgetBlocked("Explicit funded BoxAPI authorization required")
        funded = json.loads(POLICY_PATH.read_bytes())["funded_credit"]
        reported = decimal_number(reported_credit_usd, positive=True)
        if reported > decimal_number(funded["max_reported_credit_usd"]):
            raise BudgetBlocked("Reported credit exceeds the authorized policy")
        cap = reported * decimal_number(funded["spend_fraction"])
        if config.LLM_COST_BUDGET is None or not 0 < config.LLM_COST_BUDGET <= cap:
            raise BudgetBlocked("Funded spending must preserve five percent of reported credit")
        # mode=rw deliberately refuses a missing original database.
        try:
            db = sqlite3.connect(Path(path).resolve().as_uri()+"?mode=rw", uri=True, timeout=2)
        except sqlite3.Error:
            raise BudgetBlocked("BLOCKED_MISSING_DURABLE_STATE: original BoxAPI ledger") from None
        with closing(db), db:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            ModelBudget.validate_existing(db)
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='provider_usage_binding'").fetchone():
                raise BudgetBlocked("External usage cannot replace the original BoxAPI ledger")
            db.execute("CREATE TABLE IF NOT EXISTS boxapi_credits (credit_id TEXT PRIMARY KEY,"
                "credential_sha256 TEXT NOT NULL UNIQUE,limit_nano_usd INTEGER NOT NULL,"
                "daily_nano_usd INTEGER NOT NULL,token_limit INTEGER NOT NULL,"
                "reason TEXT NOT NULL,authorized_at TEXT NOT NULL)")
            if "credit_id" not in {r[1] for r in db.execute("PRAGMA table_info(model_reservations)")}:
                db.execute("ALTER TABLE model_reservations ADD COLUMN credit_id TEXT")
            try:
                db.execute("INSERT INTO boxapi_credits VALUES (?,?,?,?,?,?,?)", (
                    config.BOXAPI_CREDIT_ID, hashlib.sha256(config.model_api_key.get_secret_value().encode()).hexdigest(),
                    int(config.LLM_COST_BUDGET * 1_000_000_000),
                    int(decimal_number(funded["daily_limit_usd"]) * 1_000_000_000),
                    config.LLM_TOKEN_BUDGET, reason, datetime.now(UTC).isoformat()))
            except sqlite3.IntegrityError:
                raise BudgetBlocked("Funded key or allocation already exists; restore and continue it") from None
        return dict(status="APPENDED_FUNDED_BOXAPI_CREDIT", limit_usd=str(config.LLM_COST_BUDGET),
            reservations_reset=False)

    @staticmethod
    def initialize_provider_state(config, path):
        if config.LLM_PROVIDER == "boxapi" or not config.model_api_key or not config.LLM_TOKEN_BUDGET:
            raise BudgetBlocked("Only a new explicitly authorized external provider can be initialized")
        path = Path(path)
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open("xb"):
            pass
        with closing(sqlite3.connect(path)) as db,db:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("CREATE TABLE model_reservations (id INTEGER PRIMARY KEY,day TEXT NOT NULL,"
                "nano_usd INTEGER NOT NULL,tokens INTEGER NOT NULL,model TEXT NOT NULL,policy_hash TEXT NOT NULL)")
            db.execute("CREATE TABLE provider_usage_binding (key TEXT PRIMARY KEY,value TEXT NOT NULL)")
            db.executemany("INSERT INTO provider_usage_binding VALUES (?,?)",[
                ("provider",config.LLM_PROVIDER),
                ("credential_sha256",hashlib.sha256(config.model_api_key.get_secret_value().encode()).hexdigest()),
                ("token_limit",str(config.LLM_TOKEN_BUDGET)),("billing_mode","UNPRICED_USER_AUTHORIZED")])

    def reserve(self, *, now=None):
        p = self.policy
        tokens = p["max_input_tokens"] + p["max_output_tokens"]
        cost = (
            p["max_input_tokens"] * self.input_rate + p["max_output_tokens"] * self.output_rate
        ) / Decimal(1_000_000)
        nano_usd = int((cost * 1_000_000_000).to_integral_value(rounding=ROUND_CEILING))
        now = now or datetime.now(UTC)
        # The competition's Tehran dates use +03:30; no host timezone or optional tz database.
        day = now.astimezone(timezone(timedelta(hours=3, minutes=30))).date().isoformat()
        with closing(self.connect()) as db, db:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            if self.require_existing:
                self.validate_durable(db)
            else:
                db.execute("""CREATE TABLE IF NOT EXISTS model_reservations (
                    id INTEGER PRIMARY KEY, day TEXT NOT NULL, nano_usd INTEGER NOT NULL,
                    tokens INTEGER NOT NULL, model TEXT NOT NULL, policy_hash TEXT NOT NULL)""")
            columns = {r[1] for r in db.execute("PRAGMA table_info(model_reservations)")}
            where, args = (" WHERE credit_id=?", (self.credit_id,)) if self.credit_id else (
                (" WHERE credit_id IS NULL", ()) if "credit_id" in columns else ("", ()))
            total, total_tokens, count = db.execute(
                "SELECT COALESCE(SUM(nano_usd),0),COALESCE(SUM(tokens),0),COUNT(*) "
                "FROM model_reservations" + where, args
            ).fetchone()
            daily, daily_count = db.execute(
                "SELECT COALESCE(SUM(nano_usd),0),COUNT(*) FROM model_reservations" + where
                + (" AND" if where else " WHERE") + " day=?", (*args, day),
            ).fetchone()
            token_limit = self.config.LLM_TOKEN_BUDGET
            if self.credit_id:
                token_limit = min(token_limit, self._credit(db)[3])
            if not self.is_priced_usd:
                token_limit = min(token_limit,int(db.execute(
                    "SELECT value FROM provider_usage_binding WHERE key='token_limit'").fetchone()[0]))
            if (
                (self.total_limit is not None and Decimal(total + nano_usd) > self.total_limit * 1_000_000_000)
                or (self.daily_limit is not None and Decimal(daily + nano_usd) > self.daily_limit * 1_000_000_000)
                or total_tokens + tokens > token_limit
                or count >= p["max_requests_total"]
                or daily_count >= p["max_requests_daily"]
            ):
                raise BudgetBlocked("Persistent model budget exhausted; no request sent")
            extra = ",credit_id" if self.credit_id else ""
            db.execute("INSERT INTO model_reservations(day,nano_usd,tokens,model,policy_hash" + extra
                + ") VALUES (?,?,?,?,?" + (",?" if self.credit_id else "") + ")",
                (day, nano_usd, tokens, self.config.LLM_MODEL, self.policy_hash)
                + ((self.credit_id,) if self.credit_id else ()))
        # No refund: timeout, failure or process death may still be billed by the provider.
        return cost

    def extend_external_token_limit(self, new_limit, *, reason):
        """Explicit audited extension; reservations and BoxAPI limits are never reset."""
        import re

        if (self.is_priced_usd or not self.require_existing or type(new_limit) is not int
                or not 1 <= new_limit <= 1000000000 or not isinstance(reason,str)
                or not re.fullmatch(r"[a-z0-9-]{1,64}",reason)):
            raise BudgetBlocked("Only explicit external-provider token extensions are allowed")
        with closing(self.connect()) as db, db:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            self.validate_durable(db)
            previous = int(db.execute("SELECT value FROM provider_usage_binding WHERE key='token_limit'").fetchone()[0])
            if new_limit <= previous:
                raise BudgetBlocked("Token bound must increase without changing consumption")
            db.execute("CREATE TABLE IF NOT EXISTS provider_limit_extensions (id INTEGER PRIMARY KEY,"
                "old_limit INTEGER NOT NULL,new_limit INTEGER NOT NULL,reason TEXT NOT NULL,"
                "authorized_at TEXT NOT NULL)")
            db.execute("INSERT INTO provider_limit_extensions(old_limit,new_limit,reason,authorized_at) VALUES (?,?,?,?)",
                (previous,new_limit,reason,datetime.now(UTC).isoformat()))
            db.execute("UPDATE provider_usage_binding SET value=? WHERE key='token_limit'",(str(new_limit),))
        return dict(old_limit=previous,new_limit=new_limit,reservations_reset=False)

    async def before_request(self, request):
        if request.method != "POST" or str(request.url) != self.config.LLM_BASE_URL + "/chat/completions":
            raise BudgetBlocked("Only the selected provider's exact Chat Completions endpoint is allowed")
        raw = request.content
        payload = json.loads(raw)
        limit = payload.get("max_completion_tokens", payload.get("max_tokens"))
        if (
            len(raw) + 1024 > self.policy["max_input_tokens"]
            or (type(limit) is not int or not 0 < limit <= self.policy["max_output_tokens"])
            or payload.get("stream")
            or payload.get("n", 1) != 1
            or (
                payload.get("model") != self.config.LLM_MODEL
                or any(tool.get("type") != "function" for tool in payload.get("tools", []))
            )
        ):
            raise BudgetBlocked("Request exceeds the reserved token/model contract")
        cost = self.reserve()
        if self.audit:
            self.audit.record_event(
                "MODEL_RESERVATION",
                "BUDGET",
                {
                    "reserved_input_tokens": self.policy["max_input_tokens"],
                    "reserved_output_tokens": self.policy["max_output_tokens"],
                    "reserved_cost_usd": str(cost) if self.is_priced_usd else None,
                    "billing_mode": "PRICED_USD" if self.is_priced_usd else "UNPRICED_USER_AUTHORIZED",
                    "provider_reported_usage": None,
                },
            )
