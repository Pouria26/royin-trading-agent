"""Reserve conservative USD/token limits durably before each BoxAPI request."""

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta, timezone
from decimal import ROUND_CEILING, Decimal
from pathlib import Path

from royin.market_data import decimal_number

POLICY_PATH = Path("config/llm-budget-policy.json")


class BudgetBlocked(ValueError):
    pass


class ModelBudget:
    def __init__(self, config, path=Path("data/llm-budget.sqlite3")):
        self.config = config
        self.path = path
        raw = POLICY_PATH.read_bytes()
        self.policy = json.loads(raw)
        self.policy_hash = hashlib.sha256(raw).hexdigest()
        p = self.policy
        if p["currency"] != "USD" or config.LLM_COST_CURRENCY != "USD" or (
            config.LLM_COST_BUDGET is None or config.LLM_TOKEN_BUDGET is None
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

    def reserve(self, *, now=None):
        p = self.policy
        tokens = p["max_input_tokens"] + p["max_output_tokens"]
        cost = (p["max_input_tokens"] * self.input_rate
                + p["max_output_tokens"] * self.output_rate) / Decimal(1_000_000)
        nano_usd = int((cost * 1_000_000_000).to_integral_value(rounding=ROUND_CEILING))
        now = now or datetime.now(UTC)
        # The competition's Tehran dates use +03:30; no host timezone or optional tz database.
        day = now.astimezone(timezone(timedelta(hours=3, minutes=30))).date().isoformat()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=2)) as db, db:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("""CREATE TABLE IF NOT EXISTS model_reservations (
                id INTEGER PRIMARY KEY, day TEXT NOT NULL, nano_usd INTEGER NOT NULL,
                tokens INTEGER NOT NULL, model TEXT NOT NULL, policy_hash TEXT NOT NULL)""")
            db.execute("BEGIN IMMEDIATE")
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
                or count >= p["max_requests_total"] or daily_count >= p["max_requests_daily"]
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
        if len(raw) + 1024 > self.policy["max_input_tokens"] or (
            type(limit) is not int or not 0 < limit <= self.policy["max_output_tokens"]
        ) or payload.get("stream") or payload.get("n", 1) != 1 or (
            payload.get("model") != self.config.LLM_MODEL
            or any(tool.get("type") != "function" for tool in payload.get("tools", []))
        ):
            raise BudgetBlocked("Request exceeds the reserved token/model contract")
        self.reserve()
