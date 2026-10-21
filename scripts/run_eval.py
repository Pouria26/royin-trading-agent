"""Manifest-gated historical BASELINES WITHOUT AI. Defaults never glob raw datasets."""

import argparse
import hashlib
import json
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from royin.datasets import accepted_datasets, load_dataset
from royin.evaluation import evaluate_strategy_suite, format_scorecard_markdown
from royin.risk import MarketRules, RiskPolicy

ROOT = Path(__file__).resolve().parents[1]


def load_candles_from_normalized_file(path: Path):
    data, candles = load_dataset(path)
    return data["symbol"], candles


def get_default_market_rules(symbol: str) -> MarketRules:
    """Synthetic tick/step/minimums for sensitivity only; account-reported taker fee scenario."""
    if symbol == "USDTTMN":
        return MarketRules(
            symbol="USDTTMN",
            base_asset="USDT",
            quote_asset="TMN",
            tick_size=Decimal("1"),
            step_size=Decimal("0.01"),
            min_notional=Decimal("100000"),
            min_quantity=Decimal("1.0"),
            maker_fee_rate=Decimal("0.0025"),
            taker_fee_rate=Decimal("0.0030"),
        )
    elif symbol == "BTCTMN":
        return MarketRules(
            symbol="BTCTMN",
            base_asset="BTC",
            quote_asset="TMN",
            tick_size=Decimal("1000"),
            step_size=Decimal("0.00001"),
            min_notional=Decimal("100000"),
            min_quantity=Decimal("0.00001"),
            maker_fee_rate=Decimal("0.0025"),
            taker_fee_rate=Decimal("0.0030"),
        )
    elif symbol == "ETHTMN":
        return MarketRules(
            symbol="ETHTMN",
            base_asset="ETH",
            quote_asset="TMN",
            tick_size=Decimal("500"),
            step_size=Decimal("0.0001"),
            min_notional=Decimal("100000"),
            min_quantity=Decimal("0.0001"),
            maker_fee_rate=Decimal("0.0025"),
            taker_fee_rate=Decimal("0.0030"),
        )
    else:
        raise ValueError(f"Unsupported symbol for eval: {symbol}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "config/evaluation-datasets.json")
    parser.add_argument("--dataset", type=Path, help="Must occur in the acceptance manifest")
    parser.add_argument(
        "--all", action="store_true", help="All accepted unique manifest datasets only"
    )
    parser.add_argument("--initial-capital", default="5000000")
    parser.add_argument("--out-markdown", type=Path)
    parser.add_argument("--out-json", type=Path)
    args = parser.parse_args(argv)
    try:
        datasets = accepted_datasets(args.manifest)
        if args.dataset:
            datasets = [d for d in datasets if d[0].resolve() == args.dataset.resolve()]
        if not datasets:
            raise ValueError("BLOCKED_DATA: no matching accepted dataset")
        initial = Decimal(args.initial_capital)
        if not initial.is_finite() or initial <= 0:
            raise ValueError("Invalid capital")
        run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
        directory = ROOT / "artifacts" / "evaluation" / run_id
        out_md = args.out_markdown or directory / "report.md"
        out_json = args.out_json or directory / "manifest.json"
        if out_md.exists() or out_json.exists():
            raise ValueError("Refusing to overwrite run evidence")
        results, sections = {}, ["# Historical baselines WITHOUT AI; old scorecards superseded", ""]
        for path, data, candles, record in datasets:
            rules = get_default_market_rules(data["symbol"])
            policy = RiskPolicy(
                Decimal("1500000"),
                Decimal("3000000"),
                Decimal("0.02"),
                Decimal("0.05"),
                record["end"],
            )
            card = evaluate_strategy_suite(
                candles,
                rules,
                policy,
                initial_capital=initial,
                interval_seconds=data["interval_seconds"],
            )
            results[path.name] = {"acceptance": record, "scorecard": card}
            sections.append(
                format_scorecard_markdown(card, title=data["symbol"] + " DEVELOPMENT_ONLY")
            )
        report = {
            "schema_version": 1,
            "run_id": run_id,
            "mode": "historical",
            "source": "PAPER_BASELINE_NO_AI",
            "created_at": datetime.now(UTC).isoformat(),
            "revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
            "dirty": bool(
                subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()
            ),
            "source_hashes": {
                str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted((ROOT / "src/royin").glob("*.py"))
            },
            "acceptance_manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
            "rules_provenance": {
                "tick_step_minimum": "SYNTHETIC_UNVERIFIED",
                "fees": "USER_ACCOUNT_REPORT maker .0025 / taker .003; all fills charged taker",
                "fee_asset": "SYNTHETIC_QUOTE; account feeAsset unverified",
                "risk_thresholds": "INTERNAL_RESEARCH; not approved live sizing",
                "deadline": "dataset end; no entries in final 3600s; endpoint liquidation assumption",
            },
            "selection_status": "INSUFFICIENT_EVIDENCE_DEVELOPMENT_ONLY",
            "results": results,
        }
        for path in (out_md, out_json):
            path.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        out_md.write_text("\n".join(sections), encoding="utf-8")
        print("\n".join(sections))
        print("Run manifest:", out_json)
        return 0
    except (ValueError, KeyError, OSError) as exc:
        print("BLOCKED:", type(exc).__name__)
        return 2


if __name__ == "__main__":
    sys.exit(main())
