"""Run institutional evaluation scorecard across market datasets and strategy baselines.

Usage:
    python -X utf8 scripts/run_eval.py --dataset data/t02/normalized-c8c0f4903f000a992688564e8a90b54daab68aeff8ca7c998a7d933b41c7b5c1.json
    python -X utf8 scripts/run_eval.py --all
"""

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

from royin.evaluation import evaluate_strategy_suite, format_scorecard_markdown
from royin.market_data import Candle, decode_json
from royin.risk import MarketRules, RiskPolicy

ROOT = Path(__file__).resolve().parents[1]


def load_candles_from_normalized_file(path: Path) -> tuple[str, list[Candle]]:
    """Parse normalized JSON dataset into symbol and Candle objects."""
    raw = decode_json(path.read_bytes())
    symbol = raw["symbol"]
    raw_candles = raw["candles"]
    candles = [
        Candle(
            open_time=int(c["open_time"]),
            open=Decimal(str(c["open"])),
            high=Decimal(str(c["high"])),
            low=Decimal(str(c["low"])),
            close=Decimal(str(c["close"])),
            volume=Decimal(str(c["volume"])),
        )
        for c in raw_candles
    ]
    return symbol, candles


def get_default_market_rules(symbol: str) -> MarketRules:
    """Construct verified market rules according to symbol and Wallex fee schedule."""
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
    parser.add_argument("--dataset", type=str, help="Path to normalized candle JSON dataset")
    parser.add_argument("--all", action="store_true", help="Run evaluation across all normalized datasets in data/t02")
    parser.add_argument("--initial-capital", type=str, default="5000000", help="Initial quote capital in TMN")
    parser.add_argument("--out-markdown", type=str, default="artifacts/evaluation_report.md", help="Path to write Markdown scorecard")
    parser.add_argument("--out-json", type=str, default="data/eval_scorecard.json", help="Path to write JSON scorecard")
    args = parser.parse_args(argv)

    dataset_files = []
    if args.all:
        t02_dir = ROOT / "data" / "t02"
        dataset_files = sorted(list(t02_dir.glob("normalized-*.json")))
        if not dataset_files:
            parser.error(f"No normalized datasets found in {t02_dir}")
    elif args.dataset:
        p = Path(args.dataset)
        if not p.exists():
            parser.error(f"Dataset not found: {args.dataset}")
        dataset_files = [p]
    else:
        # Default to primary USDTTMN dataset
        p = ROOT / "data" / "t02" / "normalized-c8c0f4903f000a992688564e8a90b54daab68aeff8ca7c998a7d933b41c7b5c1.json"
        if p.exists():
            dataset_files = [p]
        else:
            parser.error("Specify --dataset or --all")

    initial_capital = Decimal(args.initial_capital)
    policy = RiskPolicy(
        max_order_tmn=Decimal("1500000"),
        max_exposure_tmn=Decimal("3000000"),
        stop_loss_pct=Decimal("0.02"),
        max_drawdown_pct=Decimal("0.05"),
        deadline_utc=2000000000,
    )

    combined_scorecards = {}
    markdown_sections = ["# Strategy Evaluation & Baselines Scorecard (Evaluation Report)", ""]

    for file_path in dataset_files:
        symbol, candles = load_candles_from_normalized_file(file_path)
        rules = get_default_market_rules(symbol)

        scorecard = evaluate_strategy_suite(
            candles,
            rules,
            policy,
            initial_capital=initial_capital,
            interval_seconds=900,
        )

        title = f"Evaluation Results for {symbol} ({len(candles)} 15m bars - file: {file_path.name})"
        md_table = format_scorecard_markdown(scorecard, title=title)
        markdown_sections.append(md_table)
        markdown_sections.append("")

        combined_scorecards[file_path.name] = {
            "symbol": symbol,
            "candles_count": len(candles),
            "scorecard": scorecard,
        }

    # Write Markdown artifact
    out_md = Path(args.out_markdown)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(markdown_sections), encoding="utf-8")

    # Write JSON output
    out_json = Path(args.out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(combined_scorecards, indent=2), encoding="utf-8")

    # Print to stdout
    print("\n".join(markdown_sections))
    print(f"\n[OK] Evaluation report saved to: {out_md}")
    print(f"[OK] Evaluation JSON metrics saved to: {out_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
