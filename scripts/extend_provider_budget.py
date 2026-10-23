"""Explicit local token-bound extension for an approved external provider; zero HTTP."""

import argparse
import json
from pathlib import Path

from royin.config import RuntimeConfig
from royin.model_budget import BudgetBlocked, ModelBudget
from royin.model_profiles import PROVIDER_MODELS, PROVIDER_ORIGINS


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extend", action="store_true")
    parser.add_argument(
        "--provider", choices=[name for name in PROVIDER_MODELS if name != "boxapi"], required=True
    )
    parser.add_argument("--model", required=True)
    parser.add_argument("--keys-file", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--new-token-limit", type=int, required=True)
    parser.add_argument("--reason", required=True)
    args = parser.parse_args(argv)
    if not args.extend:
        print(json.dumps(dict(status="BLOCKED_EXPLICIT_EXTENSION_REQUIRED", model_http=0)))
        return 2
    try:
        keys = json.loads(args.keys_file.read_text(encoding="utf-8"))
        config = RuntimeConfig(
            LLM_PROVIDER=args.provider,
            LLM_MODEL=args.model,
            LLM_BASE_URL=PROVIDER_ORIGINS[args.provider],
            LLM_TOKEN_BUDGET=args.new_token_limit,
            **{args.provider.upper() + "_API_KEY": keys[args.provider]["api_key"]},
        )
        budget = ModelBudget(config, args.ledger, require_existing=True)
        result = budget.extend_external_token_limit(args.new_token_limit, reason=args.reason)
        print(json.dumps(dict(status="EXTENDED_EXISTING_EXTERNAL_BOUND", model_http=0, **result)))
        return 0
    except (ValueError, OSError, KeyError, TypeError, BudgetBlocked):
        print(json.dumps(dict(status="BLOCKED_PROVIDER_EXTENSION", model_http=0)))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
