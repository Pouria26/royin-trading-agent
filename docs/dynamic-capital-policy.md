## Current audit and provider authority — 2026-10-23 evening

BoxAPI/gpt-6-luna is the current operator-selected provider; the APMix operational selection below is historical and superseded. Current funding is documented in funded-boxapi-runtime.md. Read [risk and WAIT causal audit](risk-wait-audit.md):1%account drawdown reduces the future planned risk budget, not every order automatically;25k at5M is not a guaranteed actual loss ceiling. The current captured WAITs were not rejected by capital gates. Trading parameters remain unchanged.

# Dynamic capital and current evidence — 2026-10-23

The operator explicitly requested real autonomous trading through Monday and
delegated trading judgment. This supersedes the fixed-150k-only policy for the
**new** financial mission. It does not resolve the historical UNKNOWN request,
reset its counter/reserve, authorize leveraged trading, or establish profitability.

`VOLATILITY_CAPITAL_V1` sizes from observed risk rather than an uncalibrated LLM
confidence score. The planned loss budget is 0.5% of current account equity.
The stop distance is max(1.2%, 2 × ATR14 / entry price); above 6% the entry is
rejected. Stop distance plus both fees, a 0.1% execution allowance and one tick
determine the loss fraction. Debit is the minimum of available mission cash,
50% account equity, 80% account equity, 5% observed two-sided book depth, and
loss budget divided by that fraction, rounded down. Exchange execution can
exceed a planned loss during gaps/outages; stops do not guarantee fills.

The first completed actual round-trip is limited to 150,000 TMN debit. Only its
durable closure permits the predeclared dynamic sizing; restart never creates
that evidence. A five-million account may allocate at most four million to this
mission, retaining at least 100,000 outside as historical-risk quarantine. The
implementation deliberately holds **one position at a time** and rotates markets;
it does not implement a simultaneous multi-asset portfolio. Consequently the
50% single-position cap is stricter than the 80% overall ceiling.

After 1% peak-to-current account drawdown, future planned risk halves. A 2%
loss from the durable UTC-day starting equity pauses entries until the next UTC
day. A 4% mission peak drawdown persists a mission halt across days. These
capital gates request exit of an existing position independently of the LLM.
Daily rollover does not reset order counts, fills, intents, model consumption or
mission loss limits. One immutable permit also limits total BUY and HTTP attempts.

The scheduling contract's 150k amount remains the signal/bootstrap research
amount. The financial permit explicitly binds dynamic policy and allocation;
the transport independently checks first-trip, single-position, debit and planned
loss constraints. A model cannot change this policy or submit arbitrary orders.

Entry limits now derive from a fresh post-inference ask. The original forecast
target is preserved; fees, rounding, full entry/unwind depth, account totals and
a final fresh book are checked before submission. Repricing does not justify
buying above the original conditional target. Stops, trailing, forecast expiry
and final conversion run without model availability. Model-budget exhaustion
closes entries, while position protection remains active.

The model tool schema now enumerates host-issued candidate hashes, symbols,
prices and evidence IDs. Cross-candidate binding is still rejected by the host;
no response hash is silently repaired. APMix Sonnet is the previously qualified
alternative selected for multi-day operation; the original BoxAPI daily/global
limits remain intact. Existing APMix consumption was extended from 20M to 200M
reserved-token allowance with an append-only extension receipt, not reset or
refunded. This is a local bound, not a provider balance or profit estimate.

## Prospective test stopped at operator request

`paired-hour-forward-20261023-1` started at 14:54:59 Tehran, was stopped at
16:50:17, and ended `STOPPED_FLAT / PARTIAL`, with unchanged source, 115 cycles
and 535 public GETs. It is **not a completed three-hour test**. Original manifests,
terminal snapshots and their hashes remain ignored local evidence.

| Arm | Net TMN | Closed round-trips | Actual-model decisions | Host fallback |
| --- | ---: | ---: | ---: | ---: |
| Cash | 0 | 0 | — | — |
| Hold | -1389.50331768 | 1 | — | — |
| Rule | -3321.877789326 | 2 | — | — |
| GPT | 0 | 0 | 10 | 12 |
| APMix | 0 | 0 | 14 | 8 |

Both models had zero executed paper orders/fills. Some WAITs were valid bearish
market decisions; invalid selected hashes/evidence and timeouts also contributed.
One APMix ENTER was rejected because the fresh ask exceeded the old limit.
Accounting replays verified all four recorded arms. Zero return with no trades
does not establish alpha, and unit-test orders/fills are synthetic evidence only.

Validation of the integrated candidate: 479 core tests and 13 dashboard tests
passed; Ruff, compileall, sample config and JavaScript syntax passed. Fresh real
provider compatibility, actual exchange fills and Liara operation are separate
acceptance steps and remain unconfirmed at this implementation checkpoint.

Sizing rationale: [CME position sizing](https://www.cmegroup.com/education/courses/trade-and-risk-management/proper-position-size).
The exact risk fractions here are team policy, not a validated optimal strategy.
