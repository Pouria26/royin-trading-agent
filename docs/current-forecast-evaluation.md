# Recorded current-market forecast evaluation

Status: **diagnostic evidence, not strategy approval**. The real credit canary remains
BUY_UNKNOWN; this evaluation sends only public GETs and does not modify that financial state.

The scorer consumes the existing CURRENT_PAPER/REAL_MODEL manifests. Before any GET it checks
snapshot and batch hashes, provider final_result against the recorded host forecast, symbol,
cutoff, horizon policy, evidence and pre-outcome manifest time. A nullable symbol on WAIT is
valid only when its forecast and echoed snapshot bind the same market. Missing forecasts,
unmatured outcomes and invalid candles remain visible rather than becoming successful samples.
Provider trace consistency is not a cryptographic attestation from the provider.

Outcome: the close of the one-minute candle with open timestamp exactly horizon_end-60.
The source open-time convention is still a diagnostic assumption; no interpolation, rounding
to a later minute or stale last-price substitution is permitted. Subminute horizons are unscored.
There are at most32 GETs, no retry and no model call. Source manifests stay untouched and each
evaluation gets a new output directory with source/scorer/capture hashes. Repeated copies cannot
inflate sample count; same-session forecasts remain correlated even when IDs differ.
Copied provider responses under different run IDs are rejected before HTTP as well.

Verified CLI, from the repository root:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m scripts.score_market_forecast --paper-manifest artifacts/market-paper/market-readiness-real-20261022-4/manifest.json artifacts/market-paper/market-readiness-real-20261022-7/manifest.json artifacts/market-paper/market-readiness-real-20261022-8/manifest.json --score
```

The actual aggregate run included all seven available manifests from the earlier eight diagnostic
attempt directories, including four decisions without an issued forecast. The failed attempt
without a manifest contributes no invented decision. These are mixed source revisions, not an A/B
comparison or independent holdout. The report retained three valid forecasts.

## Observation at2026-10-22T17:46:41Z

Actual public GETs:1. Model calls:0. Financial writes:0. Result:PARTIAL_FORECAST_DIAGNOSTIC,
one scored forecast, two pending and no missing outcome among the matured forecasts.

| Forecast | Action | Horizon | Median forecast | Observed terminal return | State |
|---|---|---|---|---|---|
| USOONTMN | WAIT |50min |+0.200% |+0.3870547% |Scored |
| PUMPTMN | WAIT |57min |-0.800% |Not yet scored |Pending |
| PEPETMN | WAIT |10h |-1.200% |Not yet scored |Pending |

For USOONTMN, absolute median error was0.1870547 percentage points, versus0.3870547 for
the zero-point forecast. Its q10..q90 interval was[-1.2%,+1.8%], width3 percentage points;
this single outcome was inside it. One covered outcome does not establish80% coverage/calibration.
This is a gross price move, not a filled trade or net profit. Fees/slippage would still be payable.

## Second maturity check at2026-10-22T17:55:32Z

The57-minute PUMPTMN forecast matured. Two public GETs produced a new report; the first
USOONTMN result and its capture hash were unchanged. No model or financial request was made.

| Forecast | Median forecast | Observed terminal return | Absolute error |
|---|---|---|---|
| USOONTMN |+0.200% |+0.3870547% |0.1870547 percentage points |
| PUMPTMN |-0.800% |+0.8064516% |1.6064516 percentage points |

Across these two correlated diagnostics, median absolute error was0.8967532 percentage points
for the model versus0.5967532 for the zero-point baseline. The model was worse on this metric;
the PUMPTMN sign forecast was wrong. Both outcomes fit the model's broad intervals, which does
not rescue the point forecast or prove calibration. PEPETMN remains pending until its ten-hour
horizon matures. This evidence does not justify increasing risk, adding a debate swarm or tuning
the same evaluation outcomes into an apparent improvement. Any forecast change needs fresh data.

Offline replay against the preserved source/capture hashes reproduced both terminal returns,
pending count and metric values with zero HTTP/model/order calls. Raw captures stay ignored.

The zero-point baseline now reports interval metrics as BLOCKED_NO_DEVELOPMENT_INTERVAL unless
an independently supplied development interval exists. Previously the helper fitted its default
interval on its own evaluation outcomes, contrary to the documented intended comparison. The
regression prevents that leakage; historical artifacts are preserved, not silently rewritten.

For replay, retain the ignored source manifests and outcome captures; a clean public clone does
not contain those raw records. Do not call this complete judge reproducibility until an allowed,
sanitized evidence package and replay inputs are assembled. No profitability, superiority over a
strategy baseline, stable income or competition score is established.

Verification for this phase:336 core tests, Ruff, compileall and wheel build passed. Existing
market-policy snapshots were not changed; the host now independently applies that denylist even
when a scanner/model proposes a prohibited symbol. No new model spend or financial write occurred.
