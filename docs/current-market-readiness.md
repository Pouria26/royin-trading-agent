# Current-market agent readiness

Status: **in progress; production order transport remains blocked**. The full requested outcome
includes real execution, not just this analysis phase. No profit or score is guaranteed.

Follow-up: docs/credit-canary.md records a separately restricted technical attempt at e7d8bc5.
It ended BUY_UNKNOWN with observed cash delta0 and no verified fill. General strategy live remains
blocked; preserve the unresolved intent and caps. The technical exception is not an alpha release.

| Requirement | Evidence | Remaining work |
|---|---|---|
| Review TradingAgents | Source commit e8f5503e9b86d5c2710b0c76b1f686703968c9df: researchers, manager, trader, backtest | Evaluate adaptations on Wallex |
| Broad permitted-market screening | Real catalog469; diagnostic120 eligible,5 researched,4 accepted | Forward observations; public catalog is not private account permission |
| Real AI selection | Real BoxAPI decision and provider usage, not a disguised rule | Prospective outcomes and reviewed live adapter |
| >2% gross opportunities,5min–10h | Host target/horizon checks and a valid WAIT path | Calibration and net economic evaluation |
| Bearish market and relative strength | Currency-adjusted observed breadth/median, countertrend evidence gate | Validate the heuristic across regimes |
| Position control | Durable selected horizon/rules, model reviewer and independent host protection | Multi-hour forward/fault/restart evidence |
| Accurate execution evidence | Prefix, symbol, bid-key, freshness and valuation regressions | Restricted production release and real fill/fee reconciliation |
| Small real pilot | Active credit account and public spot-rule observations | Clean reviewed revision, scoped transport and canary |

## Architecture and policy

The cheap catalog screens the eligible universe; a bounded expensive batch preserves liquidity
coverage and includes relative movers. The model does not deeply analyze every listed market.
TMN quotes avoid introducing an unimplemented conversion ledger. Existing banned markets stay
excluded. The model sees both supporting and opposing evidence; the two runtime roles remain
Entry Analyst and Position Reviewer. The host owns sizing, risk, stops and order permission.

This adapts TradingAgents' specialized evidence critique without copying its stock fundamentals,
debate loops, LangGraph dependencies or model-owned sizing. It is not the full TradingAgents framework.

Market context removes observed USDT/TMN movement from eligible TMN asset returns when that
benchmark is available. Positive breadth>=0.6 plus positive median is BULLISH; breadth<=0.4 plus
negative median is BEARISH; fewer than three observations is UNKNOWN. These are research heuristics,
not calibrated probabilities or forecasts. A 24h mover is not necessarily an attractive new entry.

Context-bearing ENTER proposals need a gross target above0.02 and a horizon within300..36000 seconds
and the funded session deadline. A bearish exception additionally needs positive asset return,
positive relative strength and bullish trend evidence. These conditions do not prove expected profit.
A WAIT research forecast may outlive a short diagnostic because it commits no funds. Fees remain payable.

Paper entries use observed spot rules and an observed ask. The public `/v1/markets` snapshot returned
USDTTMN stepSize=2, tickSize=0, minQty=0.01 and minNotional=50000. This supersedes the one-USDT
assumption for public spot metadata; it does not attest every credit-package exception. The current
credit account separately reported maker0.0025/taker0.003,5M TMN free and no open orders.

Position policies, market rules and selected horizons persist. Changed source/profile bindings
cannot silently reinterpret an existing portfolio. Provider traces, selected snapshots, capture
hashes and budget-policy hashes are exported. Host protection is labeled HOST_PROTECTION.
Historical REAL_MODEL/RECORDED modes without matching decision dispatch are rejected. Restart
preserves the original session deadline and avoids repeatedly billing the same entry candle.

## Budget and real observations

Budget policy v2 reserves12288 input tokens and1024 output tokens per HTTP. Actual multi-market
tests exposed a blocked second request under the old conservative byte bound and truncated output
under512 tokens. Tariffs and global/daily USD limits did not increase. Worst-case Luna reservation
is USD0.00200192 per request: the existing USD0.04 envelope allows19 such requests, despite its
separate24-HTTP cap. Failures are not refunded and durable scope counters survive restart.

A successful real diagnostic selected USOONTMN as the interesting countertrend candidate but
returned WAIT: bearish breadth, weak volume and no supported >2% continuation. It reported two
requests,3478 input tokens and530 output tokens. This proves compatibility/decision flow, not
portfolio profitability, calibration or superiority. Failed/truncated observations were preserved.

Current diagnostics have a32-GET cap. A longer forward session needs an explicitly budgeted
monitoring profile; do not restart collectors to reset the cap. A two-minute diagnostic cannot fund
a five-minute position plus liquidation buffer. No real order was sent in this phase.

Verified diagnostic interface (real model spend; virtual funds):

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts\run_market_paper.py --mode CURRENT_PAPER --model-mode REAL_MODEL --cycles 1 --duration-seconds 120 --order-tmn 100000 --horizon-max 36000
```

Every source revision needs a fresh run. Prior artifacts remain immutable. No secret or private
account identifier is sent to the model.

## Sources and next phase

- https://github.com/TauricResearch/TradingAgents/tree/e8f5503e9b86d5c2710b0c76b1f686703968c9df
- https://developers.wallex.ir/docs/spot-create-order
- https://developers.wallex.ir/docs/spot-single-order-detail
- https://api.wallex.ir/v1/markets

Complete a narrowly scoped real-execution release, verify cumulative fills/fees and fault recovery,
freeze a clean revision and run a tiny technical canary if those checks pass. The paper1.5M default
is not a live allowance. Then measure net strategy outcomes on fresh data with cash/rule baselines
and each arm's own state. Stable profit and a perfect competition score are not established.

## Bounded forward-session lifecycle — 2026-10-22

The default remains32 public GETs. An explicit --public-get-cap (16..4096) funds a
longer public-only session; it does not raise model or financial limits. The selected
cycle count, poll interval and GET budget bind the run at initialization. Every HTTP
attempt, including failures, is reserved durably before network access; restarts retain
both attempts and completed cycles. Current protection polls at most60 seconds apart.
The loop stops ahead of public-budget exhaustion to retain terminal quote capacity.

A bounded stop (duration, cycle cap, public-budget limit or requested shutdown) attempts
paper liquidation using a fresh uncached public bid with enough top-level quantity.
Missing/stale/shallow quotes leave the asset explicit and return PARTIAL/exit2; residual
dust is also PARTIAL. No previous valuation is reused to manufacture a successful exit.
Worker state is STOPPED_FLAT or STOPPED_OPEN, not ACTIVE after completion. Dashboard
balances use the actual selected base asset. These are paper fills, not exchange fills.

Each new model decision records its own issuance timestamp so a later session export
cannot erase pre-outcome evidence. Older diagnostic manifests retain their prior
manifest-time fallback; this does not strengthen their original evidence.

Verified:342 core tests passed in43.281s; Ruff, compileall, wheel and diff check passed.
No financial transport or canary-state policy changed. Proposed forward trial before
observing outcomes:900 seconds /15 cycles /60-second polling /160 public GETs /100000
TMN virtual maximum order /existing USD0.04 durable model envelope. No forced entry:
WAIT remains a valid outcome and this short trial cannot validate ten-hour returns.

```powershell
.\.venv\Scripts\python.exe -X utf8 -m scripts.run_market_paper --mode CURRENT_PAPER --model-mode REAL_MODEL --duration-seconds 900 --cycles 15 --interval-seconds 60 --public-get-cap 160 --order-tmn 100000 --horizon-max 36000
```

## Forward observation and output-contract correction

The predeclared trial completed at2026-10-22T18:35:50Z after15 cycles (elapsed883 seconds
from the persisted start). It used48 public GETs and8 real model HTTP requests. Three
model decisions were accepted; one ENTER proposal became HOST_FALLBACK. No paper
order/fill occurred; cash remained5M TMN and paper return0%. This is runtime evidence,
not profitable trading, win-rate measurement or superiority over cash.

Original manifest SHA256: ac047e6468051f7021a1af45adade82fc880a21379061f414778f5202b7828db.
Raw/provider/account data remain ignored. An offline source revalidation accepted3
pre-outcome forecasts and skipped the fallback; their horizons have not matured.
Provider-reported aggregate usage:14449 input/2045 output tokens. Eight worst-case
reservations at the frozen tariff imply USD0.01601536, not an invoice.

Offline replay of the rejected provider output found target_profit_pct=2 in the legacy
execution-risk field. The role schema had advertised optional numeric fields that the
host correctly prohibited. They now have null-only types; the host rejection stays.
The prompt distinguishes forecast.target_return_fraction (>0.02 for ENTER) from these
host-owned fields and explicitly says not to inflate estimates. Fixed host-validation
messages are captured separately from raw provider errors. This is a protocol repair,
not evidence of an improved forecast.

The cycle limit also bounds funded holding time; a one-cycle diagnostic cannot claim
to fund a longer position merely by declaring a long wall-clock duration. Current
checkpoint timestamps are recorded after decision processing. Summary counts separate
valid model decisions from host fallback.344 core tests passed, plus Ruff, compileall,
wheel and diff check. A fresh real-provider diagnostic is still needed for this revision.

Remaining: broaden model-directed market screening beyond the five researched markets;
obtain fresh matured outcome/own-state baseline comparisons; resolve the original
financial UNKNOWN without resetting its reserve/cap; verify actual fills before scaling.

### Fresh real-provider contract observation

At clean source revision dcc0aa4, run role-schema-real-20261022-1 completed one diagnostic
cycle using12 public GETs and2 real model HTTPs. Its structured WAIT was accepted with
0 host fallbacks and0 paper orders; offline source revalidation accepted its pre-outcome
forecast. The model issued a negative ten-hour PEPETMN median forecast instead of
inflating it into a >2% long setup. This is one successful protocol observation, not a
measured improvement in predictive accuracy. No forecast outcome was fetched early.

The prior15-cycle trial and this diagnostic ended STOPPED_FLAT. No background worker
remains from these commands. The financial canary reserve/counter/UNKNOWN is unchanged.

## Model-directed catalog research — 2026-10-22

REAL_MODEL entry now sees a validated public catalog universe of eligible liquid TMN markets
(up to256 rows), not just the deterministic five-market diagnostic shortlist. The existing Entry
Analyst selects1..5 exact symbols in its single read_market_snapshot tool call. Only those
symbols receive candle/depth research; the final proposal must bind an accepted researched
snapshot. A verified anchor initializes the existing decision contract; it is not a recommendation.
FAKE_MODEL diagnostics retain their existing ranked shortlist. No third agent or dependency added.

The host independently filters the credit denylist, activity, spot metadata and the existing
100M-TMN24h-turnover research floor. Catalog24h performance is not a forecast. The model can
reject all researched candidates. The research universe records catalog hash/time; the trace
retains requested symbols, accepted batch hash, public captures and provider requests/responses.
Coverage distinguishes eligible catalog rows, model-visible liquid TMN rows, researched symbols
and accepted snapshots. Other quote currencies require a conversion-ledger implementation.

Unlisted/repeated symbols, changing catalog hashes, substituted symbols and a final decision
that skips research fail closed. The tool collector has an explicit short deadline under the
30-second role budget; cancellation joins the owned collector before terminal export/worker
release. The old12-role/24-HTTP/USD0.04 envelope and durable global budget remain unchanged.
There is no financial transport in this paper tool.

A discovered accounting defect was fixed at its shared boundary: positive held assets without
a valuation price now raise instead of silently contributing zero equity. Residual/unprotected
inventory stops another paid entry scan and proceeds to explicit session finalization.

Verification:352 core tests passed in39.646s; an additional owned-collector cancellation test
passed separately; Ruff, compileall, wheel and diff check passed. Synthetic tool tests prove
selection outside the initial anchor with two provider messages, not trading alpha. A fresh
real-provider/current-data observation is required before claiming operational compatibility.

Predeclared next public-only trial:900 seconds/15 cycles/60-second polling/160 GET cap,
100000 TMN virtual order ceiling, REAL_MODEL and existing shared model budget. No forced entry,
no early forecast outcome retrieval and no change to the financial UNKNOWN/counter/reserve.

### First wider-universe real attempt: failed before model I/O

Run model-universe-forward-20261022-1 at e043fe5 exited1 before a model call or order.
Public catalog receipt could occur after cycle start; using that older start as the
current freshness clock incorrectly produced an empty liquid universe. The following
indexing then failed. The original SQLite/raw captures and external terminal-process
observation are preserved; its persisted RUNNING flag is not proof of a live process.

The caller now checks freshness at the actual post-receipt time, explicitly handles an
empty universe without paid/deep research, and records cycle IndexError as a failed
cycle instead of escaping without a session result.19 readiness tests, including a
one-second receipt delay and an empty-universe case, passed; Ruff/compileall/diff passed.
Retry uses a new source-bound run ID and the same predeclared monetary/model/public caps.
