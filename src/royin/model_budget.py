"""Reserve conservative USD/token limits durably before each BoxAPI request."""

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta, timezone
from decimal import ROUND_CEILING, Decimal
from pathlib import Path

from royin.market_data import decimal_number

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "config/llm-budget-policy.json"


class BudgetBlocked(ValueError):
    pass


class ModelBudget:
    def __init__(self, config, path=None, *, audit=None, require_existing=False):
        self.audit = audit
        self.config = config
        self.path = Path(path) if path is not None else ROOT / "data/llm-budget.sqlite3"
        self.require_existing = require_existing
        if require_existing:
            with closing(self.connect()) as db:
                self.validate_existing(db)
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
    def validate_existing(db):
        try:
            if db.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise BudgetBlocked("BLOCKED_INVALID_DURABLE_STATE: model budget integrity")
            rows = db.execute("SELECT day,nano_usd,tokens,model,policy_hash FROM model_reservations").fetchall()
            if not rows or any(
                not isinstance(day, str) or type(cost) is not int or cost < 0
                or type(tokens) is not int or tokens <= 0 or not model
                or not isinstance(sha, str) or len(sha) != 64
                for day, cost, tokens, model, sha in rows
            ):
                raise BudgetBlocked("BLOCKED_INVALID_DURABLE_STATE: continuation requires prior reservations")
        except sqlite3.Error as exc:
            raise BudgetBlocked("BLOCKED_INVALID_DURABLE_STATE: model reservation schema") from exc

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
                self.validate_existing(db)
            else:
                db.execute("""CREATE TABLE IF NOT EXISTS model_reservations (
                    id INTEGER PRIMARY KEY, day TEXT NOT NULL, nano_usd INTEGER NOT NULL,
                    tokens INTEGER NOT NULL, model TEXT NOT NULL, policy_hash TEXT NOT NULL)""")
            total, total_tokens, count = db.execute(
                "SELECT COALESCE(SUM(nano_usd),0),COALESCE(SUM(tokens),0),COUNT(*) "
                "FROM model_reservations"
            ).fetchone()
            daily, daily_count = db.execute(
                "SELECT COALESCE(SUM(nano_usd),0),COUNT(*) FROM model_reservations WHERE day=?",
                (day,),
            ).fetchone()
            if (
                Decimal(total + nano_usd) > self.total_limit * 1_000_000_000
                or Decimal(daily + nano_usd) > self.daily_limit * 1_000_000_000
                or total_tokens + tokens > self.config.LLM_TOKEN_BUDGET
                or count >= p["max_requests_total"]
                or daily_count >= p["max_requests_daily"]
            ):
                raise BudgetBlocked("Persistent model budget exhausted; no request sent")
            db.execute(
                "INSERT INTO model_reservations(day,nano_usd,tokens,model,policy_hash) "
                "VALUES (?,?,?,?,?)",
                (day, nano_usd, tokens, self.config.LLM_MODEL, self.policy_hash),
            )
        # No refund: timeout, failure or process death may still be billed by the provider.
        return cost

    async def before_request(self, request):
        if request.method != "POST" or str(request.url) != (
            "https://ai.boxapi.ir/ai/v1/chat/completions"
        ):
            raise BudgetBlocked("Only BoxAPI Chat Completions is allowed")
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
                    "reserved_cost_usd": str(cost),
                    "provider_reported_usage": None,
                },
            )
