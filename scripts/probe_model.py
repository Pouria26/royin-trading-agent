"""Explicit, small Gemini compatibility probe. No exchange or order access."""

import argparse
import asyncio
import json
import os
import time
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict
from pydantic_ai import Agent
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.usage import UsageLimits


class ProbeDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["WAIT", "REVIEW"]
    evidence_id: str


async def probe(model_name, api_key, base_url):
    provider = GoogleProvider(api_key=api_key, base_url=base_url or None)
    agent = Agent(
        GoogleModel(model_name, provider=provider),
        output_type=ProbeDecision,
        retries=0,
        model_settings={"max_tokens": 512, "max_retries": 0},
        instructions=(
            "Call read_snapshot exactly once. If the snapshot says stale=true, "
            "return WAIT with its evidence_id. Otherwise return REVIEW. "
            "This is a synthetic compatibility check; no trading is possible."
        ),
    )
    calls = []

    @agent.tool_plain
    def read_snapshot() -> str:
        calls.append("read_snapshot")
        return '{"evidence_id":"SYNTHETIC_STALE_1","stale":true}'

    started = time.monotonic()
    async with asyncio.timeout(30):
        result = await agent.run(
            "Inspect the snapshot using the tool and choose the allowed action.",
            usage_limits=UsageLimits(request_limit=2, tool_calls_limit=1),
        )
    valid = calls == ["read_snapshot"] and result.output == ProbeDecision(
        action="WAIT", evidence_id="SYNTHETIC_STALE_1"
    )
    print(json.dumps({
        "kind": "REAL_PROVIDER_COMPATIBILITY_NOT_TRADING_QUALITY",
        "status": "PASS" if valid else "FAIL",
        "model": model_name,
        "wall_seconds": round(time.monotonic() - started, 3),
        "tool_calls": calls,
        "output": result.output.model_dump(),
        "requests": result.usage.requests,
        "input_tokens": result.usage.input_tokens,
        "output_tokens": result.usage.output_tokens,
    }, indent=2))
    return int(not valid)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Allow this small, possibly paid probe")
    args = parser.parse_args()
    if not args.run:
        parser.print_help()
        return 0
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    api_key = os.getenv("GOOGLE_API_KEY", "").strip()
    if not api_key:
        print("BLOCKED: set GOOGLE_API_KEY in local .env; no model request was sent.")
        return 2
    if os.getenv("LLM_PROVIDER", "google") != "google":
        print("BLOCKED: this probe supports only the Google provider.")
        return 2
    try:
        return asyncio.run(probe(
            os.getenv("LLM_MODEL", "gemini-3.5-flash-lite"),
            api_key,
            os.getenv("LLM_BASE_URL", ""),
        ))
    except Exception as exc:  # noqa: BLE001 - CLI boundary must not leak provider secrets.
        # Provider exceptions can contain headers or request URLs: print only the type.
        print(f"FAIL: {type(exc).__name__}; check provider access and quota without sharing secrets.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
