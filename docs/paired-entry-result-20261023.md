# Prospective shared-entry result — 2026-10-23

Frozen source: `7df0d08069a0d08e40900ed2774991fbe4b90f02`.
Source bundle: `54289f663f133a1a7e6e7f2899a81ba0c7ff8113dbe39276a61c02d87fd15c57`.
Run `paired-entry-forward-20261023-2`, 09:44:35–11:14:45 UTC,
90 minutes, two predeclared 45-minute windows. Complete, STOPPED_FLAT,
source unchanged, no coordinator errors, 235 public GET attempts. Both Python
processes exited before source integration. No private exchange order transport.

| Arm | Realized paper PnL, TMN | Closed trips | Quote fees, TMN | Peak exposure, TMN |
|---|---:|---:|---:|---:|
| cash | 0 | 0 | 0 | 0 |
| hold | 1750.411361 | 1 | 904.798510 | 152964.6435 |
| rule | -4.832324 | 2 | 1796.816492 | 152964.6435 |
| GPT-6-luna | 0 | 0 | 0 | 0 |
| APMix Sonnet 4.6 | 0 | 0 | 0 | 0 |

The first profitable round trip is shared by hold and rule; these are not two
independent successes. Rule's second trip lost 1755.243685 TMN. Excluding each
arm's best trade leaves hold at zero and rule at -1755.243685 TMN. A profitable
first checkpoint did not establish positive performance for the final rule arm.
Mark-to-market peak exposure can exceed the original 150k cash debit as price rises.

GPT issued eight valid WAITs and three host fallbacks. APMix issued six valid
WAITs, one valid ENTER and four host fallbacks. The valid ENTER could not buy
within its reserved limit: PEPE best ask 1.354 versus limit 1.3524, quantity110582.
The full-quantity depth existed at 1.354; no full fill existed within the limit.
The gate was not relaxed to manufacture an executed AI trade. Some rejected
outputs omitted opportunity_sha256; new prompt/schema descriptions explicitly
require this binding for ENTER and diagnostics name the rejected binding field.
The validator still rejects missing/wrong hashes.

All four arm accounting replays verified. Fifteen eligible real-model forecasts
were scored after their horizons, with zero pending/missing and ten public GETs.
Mean absolute q50 error: 0.760331 percentage points; zero-return point baseline:
0.544137 percentage points; five model forecasts better and ten worse. Forecasts
overlap and reuse symbols/cutoffs; they are not independent statistical samples.
This is a forecast diagnostic, not realized trading profit or an alpha estimate.

Raw reports, snapshots, hashes, provider responses and tapes remain ignored:
`artifacts/paired-paper/paired-entry-forward-20261023-2`,
`.local/review/paired-final-snapshot`, and
`artifacts/forecast-outcomes/paired-entry-forward-20261023-2-final`.
The terminal receipt records original manifest hashes. No raw account state is
part of this document. Accounting replay is not a full exchange-execution replay.

## Next preregistered test

A new run ID/revision will use three hours, two 90-minute windows, and a fixed
one-hour forecast/holding cap. The hypothesis is that a one-hour horizon better
fits the unchanged target above2% than thirty minutes. This is a new prospective
policy test, not a relabeling of the result above. Keep the same cash/hold/rule/GPT/
APMix arms, shared input/book barrier, 150k debit, 100k minimum, fees, host exits,
and strict binding/economic/depth rules. No prompt or threshold changes mid-run.
Original model budgets may block an arm; report that explicitly without resets
or automatic provider substitution. Profitability and live readiness remain unproven.
