# Strategy research and evidence limits

Reviewed 2026-10-22. This is a hypothesis inventory, not a profitability claim.

## Costs and actual implementation

Account-reported TMN fees: maker 0.0025, taker 0.0030. Two taker sides plus assumed slippage 0.0005 per side cost approximately 0.7% of position value. This is a scenario, not a universal minimum. Exact break-even depends on fill prices, fee asset and rounding. One losing experiment does not prove all frequent trading loses. A 1.5M TMN exposure on 5M capital is 30%, not 50%; it is not live authorization.

The implementation in build_candidate_decision_producer uses:

- trend: relative SMA spread and inventory state.
- mean_reversion: RSI entry/exit thresholds and inventory state.
- volatility_breakout: relative ATR and SMA spread filters, RSI exit. No Donchian channel is implemented.
- regime_momentum: SMA spread, volume ratio and RSI thresholds.

config/strategy-experiment-plan.json preserves the original twelve configurations and SHA256. Its internal freeze timestamp is AFTER the evaluation manifest timestamp, so prospective registration is unverified. The separate six-configuration config/candidate-evaluation-plan.json remains the CLI default; use --plan config/strategy-experiment-plan.json explicitly for twelve configurations.

## Results and next experiment

Seven 72-hour windows across two native-hour data segments are DIAGNOSTIC_ONLY. The actual manifest says INSUFFICIENT_EVIDENCE and no approved candidate. Timestamp semantics, volume units and finality remain uncertain. Exposed outcomes are not an untouched holdout.

Twelve AI snapshots use hypothetical account states. Agreement with a baseline is not correctness or added profit. A causal, same-capital/cost AI versus no-AI equity comparison and independent future observations are still needed. Report all attempted configurations, independent episodes, cost sensitivity, returns and drawdown. Do not demand a magic trade count or promise stable profits.

## Primary references and scope

- [Wallex order creation](https://developers.wallex.ir/docs/spot-create-order), [order detail](https://developers.wallex.ir/docs/spot-single-order-detail), [cancellation](https://developers.wallex.ir/docs/spot-cancel-order): fixture contracts, not proof of production accounting.
- [Freqtrade lookahead analysis](https://www.freqtrade.io/en/stable/lookahead-analysis/): methodology, not certification of this project.

Unsupported book attributions and claims that a single agent or mega-tool always outperforms alternatives were removed. The small architecture is a budget/time decision; financial superiority needs evidence.
