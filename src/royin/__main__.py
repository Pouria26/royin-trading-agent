"""Validate runtime configuration only; no trading loop or network transport exists yet."""

import argparse
import json
from pathlib import Path

from pydantic import ValidationError

from royin.config import RuntimeConfig, load_config


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check-config", help="Validate settings without network or trading")
    check.add_argument("--env-file", type=Path, help="Dotenv file; defaults to local .env if present")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.env_file)
    except ValidationError as exc:
        fields = sorted({
            str(error["loc"][0])
            if error["loc"] and error["loc"][0] in RuntimeConfig.model_fields
            else "unknown setting or cross-field gate"
            for error in exc.errors(include_input=False, include_context=False, include_url=False)
        })
        print("BLOCKED: invalid configuration: " + ", ".join(fields))
        return 2
    except (OSError, UnicodeError, ValueError):
        # File paths and parser errors can contain secrets; report only a fixed diagnostic.
        print("BLOCKED: cannot read configuration; check file, syntax and duplicate keys.")
        return 2
    print(json.dumps({
        "status": "VALID_CONFIG_ONLY",
        "mode": config.RUN_MODE,
        "network_enabled": False,
        "trading_enabled": False,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
