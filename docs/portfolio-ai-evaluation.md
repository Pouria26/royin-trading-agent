# AI portfolio experiment status — 2026-10-22

Primary result: **BLOCKED_DATA / INSUFFICIENT_EVIDENCE**. No AI economic benefit,
OOS result, independent-exposure sample size or candidate approval is established.
Existing 12 settings / 7 windows and 12 real-model snapshots remain diagnostics.
Nine agreements with a baseline are not correctness or avoided losses.

## Scope and executable infrastructure

The existing `run_simulation` owns a fresh Ledger and PaperBroker for every arm.
`run_portfolio_ablation` compares cash, hold under shared risk (may stop/reenter),
the existing naive crossover, and that rule with a model decision. All four arms
share initial capital, order/exposure caps, costs, cutoff and execution. Passive
buy-once is a separate existing comparator with a different risk contract and is
not mislabeled as the shared-risk arm.

Each report now retains every decision with exact own-ledger cash/position snapshot,
host risk result, order/fill list, flat-to-flat episodes and closed-bar/final net equity.
Realized and unrealized P&L, fees, simulated market-exit slippage, no-fill count and
close/final-settlement max drawdown are separate. Independent exposures are unknown;
closed episode count is not automatically an independent statistical sample.

`recorded_portfolio_producer` requires exact source/code/config/prompt/model/provider/
reasoning/data/family bindings, full canonical input, decision cutoff/symbol/hash and
valid evidence. Wrong cash paths, changed costs, duplicate records and fake-vs-real
source mismatch reject. It never substitutes the nearest snapshot or a baseline.
Real-model replay is BLOCKED: there are no matching own-ledger records. Imported
source metadata is not cryptographic proof of provider execution; actual audit/raw
model response provenance still needs review before using REAL_MODEL evidence.

## Prospective registration and retained attempts

- V1 frozen 05:26:46 UTC: rejected before outcomes because invented fixture dates
  were in the future. Its bytes remain in config/portfolio-ai-protocol-v1.json.
- V2 frozen 05:28:42 UTC: fake wiring ran, but the intended divergent action did
  not occur. The assertion failed; the oracle was not weakened.
- V3 frozen 05:30:01 UTC: fake now skips the first entry, exercising a different
  ledger path. Synthetic cash/replay/own-state/future-input/no-fill tests passed.
- V4 frozen 05:31:29 UTC: explicit no-fill/slippage outputs and cost-domain checks.
  SHA256 `cf6fd66e779095bf0bdb7309116958573f952bc93b010fc1caa83110032c2990`.
  Each file records its predecessor hash/reason; earlier outcomes remain ignored
  artifacts, never relabeled as results of the new source.

These are pre-run registrations for **synthetic infrastructure checks**. No primary
market dataset hash or temporal split boundaries can be approved yet. The primary
split contract remains development -> validation -> untouched holdout, 31h warmup
and 72h windows; the source/fresh data gate is not lowered. Three fresh 72h windows
cannot complete before the user-reported 2026-10-23 23:50 Tehran deadline. This
mission cannot manufacture a fresh holdout from previously inspected September data.
Historical model memory remains a risk even if absolute dates are removed.

## Commands and evidence

```powershell
.\.venv\Scripts\python.exe -X utf8 -m scripts.evaluate_portfolio_ai
.\.venv\Scripts\python.exe -X utf8 -m scripts.evaluate_portfolio_ai --self-check
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_portfolio_ai.py -v
```

The default returns2 / BLOCKED_DATA before model/config/network setup. There is no
paid mode in this CLI. Self-check uses 64 invented bars, the SDK TestModel, one read
snapshot tool, disabled real-model requests and a transport that raises on any HTTP.
It runs the four arms, exact recorded **fake** replay, and fresh own-state fake cost
stress; equality covers curve, decision traces, fills, orders and episodes. All six
targeted tests passed. V4 manifest:
`artifacts/portfolio-ai/20261022T053149Z_5868c530/manifest.json`, SHA256
`b0fd521e9cab049b7f2725829bcc304a5261d9fe977573f07c96cfb1ee4bf562`.
Synthetic returns are deliberately not presented as AI performance. The ledger's
cash identity, rejection of future feature leakage, no-fill preservation and a host
rejection of unsafe fake entry after deadline are the relevant oracles.

## Paid choice prepared, not authorized

After valid data and a new bound protocol exist, a compatibility/own-state recording
pilot could use 12 decisions, at most24 HTTP and USD0.04 conservative reservations.
This small pilot would not complete a portfolio-benefit test. The nominal three72h
split evaluation would require up to216 decisions/432 HTTP, about USD0.54 under the
versioned local tariff, plus replay records for changed cost paths; it is neither
implemented as a paid runner nor authorized. Do not bypass the existing per-run or
shared global budget. SDK token usage, local reservation and provider invoice are
three separate observations; no new provider usage or invoice was obtained here.

Next highest-value action: obtain source-attested timestamp/finality and private fill
identity/completeness semantics, preserve this no-cost evidence for delivery, then
explicitly choose a feasible new experiment and paid budget. A Secret is not needed
in chat. Running the old --eval or twelve hypothetical snapshots cannot close the
portfolio/OOS gap.


## Agent1 research follow-up — 2026-10-22 (parallel dirty tree, not final freeze)

Research is no longer stopped merely because primary source semantics are unknown.
A new offline CLI `scripts/research_portfolio.py` accepts explicit manifest SHA256 and
an assumptions file. It reconciles every normalized native row with captured raw
OHLCV/query/hash and the parent capture/catalog, checks closed-at-capture timestamps,
retains both whole segments/gap, and runs a fixed existing family with independent
per-arm ledger state. Public catalog spot eligibility and unchanged denylist are
checked; actual account permission remains unverified. No new GET or paid request.

The pre-outcome local assumptions at `.local/parallel/research-diagnostic-plan.json`
explicitly choose **FULL_DECISION_PROPOSAL_NOT_VETO**: the current agent proposes
WAIT/ENTER/EXIT at each own-ledger cutoff, rather than merely vetoing an existing
rule opportunity. Host alone sizes, gates, stops and finalizes. The baseline is the
existing naive crossover; no family or parameter search. The SDK fake copies a rule
with a deliberate first-entry skip only to test state divergence, not real AI skill.

### Versioned binding contract

`portfolio_bindings` defaults to schema2. Relative POSIX paths sort lexically.
For each file, only literal CRLF bytes are replaced with LF, then SHA256 receives
8-byte unsigned big-endian path length + UTF8 path + 8-byte content length + content.
No whitespace trimming, AST/token normalization, BOM removal, lone-CR conversion or
Unicode normalization. All src/royin/*.py, scripts/*.py and requirements.lock remain
in the bundle. Changes to code, prompt, config or data remain mismatches. Paths and
length framing prevent ambiguous concatenation. A fixed-byte oracle and an independent
struct.pack reconstruction of31 files confirm identical LF/CRLF canonical hash and
different legacy raw hashes. Tests include changed executable token, space, BOM and
lone CR; only CRLF/LF equivalence is granted.

Schema1 explicitly retains the legacy raw path+NUL+bytes recipe; absent version in
v1-v4 means schema1. Those four files/hashes were not edited, deleted or re-frozen.
The old V4 self-check should still reject current source bytes. A new final protocol
must be created after both agents stop editing and integration checks pass. Current
logic tests use labelled temporary local bindings, not a rewritten V4 or final freeze.
The self-check CLI accepts --protocol and prints binding_stage explicitly.

### Actual market diagnostic (conditional simulation, not acceptance)

Delivery run: `artifacts/research-portfolio/20261022T065854Z_5dd7f08d/manifest.json`,
SHA256 `797aaf9439f39e58723e63a0a350bcc9b5152e6aa59f376f30df3fc18f11d21a`.
It is based on dc7a7e3 plus recorded dirty source bindings, not clean HEAD execution.
Code bundle was checked unchanged across this run; final integration freeze is pending.
Both segments are development/exposed, never new holdout. Every scenario keeps
5,000,000TMN initial capital, 1.5m max order/3m exposure caps and host risk rules.
Base fee .003 each side/slippage .0005; higher-cost fee .006/slippage .002. Fee asset
quote, tick1/step.01/minimum100000/min_qty1 are explicit synthetic scenarios. Volume
is assumed base USDT only for the conditional fill test; exchange volume asset is
unknown. Timestamp start is assumed; finality is unknown. No primary gate is opened.

| Bars | Cost | Arm | Net return % | Max close/final DD % | Orders/fills/closed episodes |
|---:|---|---|---:|---:|---|
| 517 | base | cash | 0 | 0.0000 | 0/0/0 |
| 517 | base | hold_shared_risk | 0.00000 | 0.0000 | 1/0/0 |
| 517 | base | rule | 0.00000 | 0.0000 | 1/0/0 |
| 517 | higher_cost | cash | 0 | 0.0000 | 0/0/0 |
| 517 | higher_cost | hold_shared_risk | 0.00000 | 0.0000 | 1/0/0 |
| 517 | higher_cost | rule | 0.00000 | 0.0000 | 1/0/0 |
| 106 | base | cash | 0 | 0.0000 | 0/0/0 |
| 106 | base | hold_shared_risk | 0.125678687397200 | 0.3656 | 2/2/1 |
| 106 | base | rule | -0.530662996091900 | 0.5752 | 6/6/3 |
| 106 | higher_cost | cash | 0 | 0.0000 | 0/0/0 |
| 106 | higher_cost | hold_shared_risk | -0.099231159883200 | 0.3648 | 2/2/1 |
| 106 | higher_cost | rule | -1.10961926099600 | 1.1096 | 6/6/3 |

The 517-bar segment has a pending first LIMIT with no fill until cancellation at
finalization; pending-order risk blocks further intents. Zero return here is not
proof of capital-preserving signal quality or market tracking. No expiry/forced fill
was added after observing this result. The106-bar base rule loses26,533.149804595TMN
with26,894.459669595TMN fees and three episodes; higher-cost loss55,480.96304980TMN.
Hold's small base gain6,283.934369860TMN comes from one closed episode; removing it
by accounting subtraction leaves zero. No selection/independence/edge claim follows.

Each true `rule_ai` result is **BLOCKED_RECORDED_AI**, with null curve/return, because
no reviewed own-ledger real records exist. The SDK fake curve/records live separately
under fake_wiring_arm and never stand in for missing AI performance. All decisions
link client_id to intent/order/fills; closed/open episodes, realized/unrealized,
fees/slippage, orders/no-fill/time exposure, drawdown and best-episode contribution
are retained. Removing the best episode is accounting subtraction, not a new strategy
counterfactual. Independent exposure count/OOS remain null. Primary status BLOCKED_DATA.

### Real-record importer and next paid proposal

A REAL_MODEL label is insufficient. V2 importer requires origin metadata plus a
SHA-bound independent-review receipt, exact canonical own-state input, complete
manifest bindings, final Chat Completions output and sanitized captured request bodies.
Two bounded request bodies must match model/reasoning=none/output cap512, instructions,
user cutoff and the matching read_market_snapshot tool result. Raw request/response
files are hash checked. Final result arguments must equal the linked DecisionProposal.
Changing only FAKE_MODEL to REAL_MODEL fails. Handwritten provider-shaped unit fixtures
validate the importer only; they are not real-model evidence. The review receipt is
a trusted human provenance boundary, not cryptographic proof of the provider; it must
not be self-approved from fabricated JSON. Legacy suite cannot bypass this importer.
Unknown response/model alias shapes reject for review rather than being guessed.

Prepared, not run: `artifacts/research-portfolio/20261022T065828Z_27c9e299/manifest.json`,
SHA256 `2ecd245f4fb3eace9326d53bb22aecf7c930792278bc6270c50a5d2ec8538bf2`.
It fixes a43-bar exposed-data pilot window, first exact cash/position snapshot and
12 chronological cutoffs; later states must derive from that arm's ledger. Caps:
12 decisions/24 HTTP/USD0.04 reserved,30s per decision/600s overall, one read tool,
512 output tokens, no automatic retry. Stop on binding/data/capture/provider/storage
failure or budget/deadline. Shared global budget remains durable; reservations,
reported SDK usage and invoice are different observations. No paid mode exists in
this new CLI. Capturing real SDK HTTP bodies and independent receipt review is an
integration requirement before explicit paid authorization. This pilot measures
compatibility/recording only; it cannot populate a full historical AI curve by itself.

The existing three fresh72h windows cannot fit the contest deadline. This blocks the
primary strategy claim, not an independently authorized technical order-contract
micro-pilot with its own risk policy. No profitable candidate was invented to enable
that separate execution task. Full suite/final freeze are deferred to integration
while Agent2 edits shared hashed sources. Selected tests and current blockers are in
.local/parallel/research-agent-handoff.md; no commit/push or worker from Agent1.

## Task A repair boundary — 2026-10-22, based on ef48b9a

**Current strategy runtime: BLOCKED_PENDING_B_CONTRACT.** These new components do
not enable the financial CLI, Candidate Shadow or LIVE. B's separate clone owns the
ledger/broker/risk, trailing, restart and exporter; the requested interface is a
proposal until B replies. No root status, dependency, policy, dashboard or B source
was changed by A. The original outcomes, protocols V1–V6 and raw artifacts remain
immutable; a new integrated freeze is required after both branches stop changing.

Independent reproduction of the old draft (synthetic, zero HTTP/model calls) found:
existing cash1234 was reset to5000000; one fetch produced three historical decisions
with zero decide/model calls; the saved arm was named rule_ai with constant code
binding; order.created_at1790830800 preceded decision.cutoff1790831700 and the old
same-bar simulation filled at that cutoff. Two pre-fix regressions separately failed
on a missing minute accepted as a full aggregate and all scanner failures returning
DOGETMN. These are old-code correctness failures, not historical financial evidence.
The unsafe session and fake-provenance publisher have been removed from the callable
path and now fail before side effects. Existing artifacts were not relabeled in place.

A supplies `decide_role` with deterministic ENTRY_ANALYST or POSITION_REVIEWER dispatch,
using the existing BoxAPI Chat Completions/Pydantic AI transport. Entry proposes ENTER
or WAIT; reviewer proposes WAIT/HOLD or EXIT. Each must read the bounded context once,
echo role/cutoff/snapshot/position/opportunity hashes, and cite existing evidence.
Host rejects wrong roles/actions/state and any model stop/target proposal. The old
Decision schema and bind_decision signature remain compatible with B. Its legacy
finite target clamp remains a validation corridor; it is not itself a profit cap.
A's draft baseline no longer exits solely at the profit checkpoint. No change to B's
protection was assumed or made. Reviewer cost basis/net-if-exit/stop/age input remains
a proposed typed contract, not an attested financial-state calculation.

The new role trace captures context, code/config/prompt/model, SDK messages and usage,
and (on the owned production transport) request/final response bodies without headers.
REAL_MODEL_ATTEMPT is not proof of a successful provider decision; HOST_FALLBACK is
separate from MODEL_DECISION. Raw captures need private storage and independent review
before economic claims/replay. Fake transport traces remain FAKE_MODEL. No learning
or reflection improvement has been established; no third reflection role was added.
No model claim is supported solely by SQLite reservations or a source label.

Both roles share one RoleRunEnvelope and the same operator-host ModelBudget: at most
12 agent attempts,24 HTTP,USD0.04 reserved,512 output tokens,30s per call and600s per
invocation; no repairs/retries. Actual maximum reservation at the current Luna rate
is USD0.02967552/208896 reserved tokens. The envelope is invocation-local, NOT durable
financial recovery or a cross-host lock. The durable global budget is never reset.
The user chose this pilot only after B integration and single-host designation; no
paid call has run on A's branch. Protection during inference and durable same-candle
claims remain B integration requirements, not tests claimed passed by this branch.

`run_role_ablation` provides separate same-capital ledgers for rule/single-model/two-role
wiring with identical costs/risk/fill assumptions. Missing model arms have null
curves/PnL and BLOCKED_PENDING_B_CONTRACT. Supplied synthetic producers are explicitly
FAKE_MODEL; a REAL_MODEL_REPLAY label is rejected until full-position lineage/recovery
integration exists. This is a fixed-symbol conditional comparison, not a historical
whole-catalog scanner backtest or fresh holdout. No new return table, model skill,
realized AI advantage or current Shadow uptime is claimed.

Offline role tests demonstrate output-dependent ENTER versus WAIT and HOLD versus
EXIT, invalid bindings, timeout and joint budget caps; scanner/current-cutoff tests
cover gaps, stale/open/future data, warmup, duplicate/restart cutoff input and future
invariance. These are synthetic correctness checks, not real-model economic oracles.
B must still implement/test host trailing on reversal, deadline during timeout,
atomic financial restart/peak/pending recovery and the read-only dashboard export.
A's CLI remains blocked before feed, DB, model or manifest work; there is no new worker.

## A/B integration follow-up — 2026-10-22

A c620521 and B c69855e are merged on a separate codex/agent-ab-integration branch;
main is unchanged. The earlier BLOCKED_PENDING_B_CONTRACT is superseded for the
implemented offline boundary only. The financial CLI now names the remaining
BLOCKED_RELEASE_CONTRACT_UNKNOWN; missing real AI comparison records remain
BLOCKED_RECORDED_AI with null curves. No source approval, production transport,
real-model call or current strategy worker is enabled by a branch merge.

A new end-to-end synthetic SDK test connects Entry Analyst ENTER -> host risk ->
atomic candle claim/decision/paper intent -> strictly later candle fill -> Reviewer
HOLD above checkpoint -> host trailing -> real SQLite restart -> host exit. Single
5M paper capital and pending reserves persist; a late model EXIT after host liquidation
is rejected with no extra fill. Independent money oracle: qty2.99@100000, buy fee897,
exit2.99@101949 after gap/slippage, sell fee914.48253 => realized4016.02747TMN,
cash5004016.02747/base0. It is FAKE_MODEL/synthetic data, not an AI profit estimate.
No future price is included in either role's input; future observations only drive
later host ticks. Official account/source critical unknowns still close real release.

## Market selection and terminal forecast — first real-model run, 2026-10-22

Follow-up implementation: docs/current-forecast-evaluation.md adds hash/provider-bound scoring
for current paper manifests. The zero-baseline helper now actually blocks interval metrics when
no development interval is supplied; older raw artifacts remain unchanged.

This section supersedes nothing above; it adds a separate, bounded protocol
(`config/market-ai-forecast-protocol-v1.json`, frozen 17:08 Tehran before the outcome).

**Profile:** `PUBLIC_MARKET_PAPER` on current Wallex public data. The universe is the
current catalog after the existing denylist/TON exclusion, not an account-verified
universe; no order, account write or private endpoint was used.

**What the model did:** host verified catalog, depth, uniform 5m closed cutoff, fee
(0.006 round trip) and freshness, then exposed two liquidity-valid candidates
(BTCTMN, PEPETMN) in host order. The Entry Analyst chose PEPETMN over the first
candidate, returned WAIT, and issued a 900-second terminal forecast:
q10 -0.018, q50 0.002, q90 0.022, target 0.012, reference 1.2196.
The host accepted the decision (no fallback), bound it to the PEPETMN snapshot hash
and opportunity hash, and recorded the provider request/response trace.
Model: `gpt-6-luna`; 2390 input / 474 output tokens, 2 HTTP attempts,
USD 0.00247296 reserved ceiling.

**Outcome and scoring (N=1, diagnostic only):** the 1-minute close at cutoff+900s
was 1.2168, a terminal return of **-0.0022958** (-0.2296%). The model's q50 was
+0.002, so absolute q50 error is 0.0042958 (0.4296%). The -0.2296% outcome lies
inside q10..q90 (coverage 1), interval width 0.04, Winkler score 0.040. A zero-point
forecast had absolute error 0.0022958. An empirical-interval baseline is **BLOCKED**:
one outcome cannot estimate development quantiles, and fitting on this outcome would
be leakage. No calibration, superiority, profitability or future-accuracy claim follows.

**Replay:** `scripts/score_market_forecast.py --replay` recomputes the batch SHA256
from the recorded candidate view, re-checks the chosen snapshot/opportunity hashes
and cutoff, and re-validates the forecast against the recorded snapshot: **PASS**.
The outcome step (`--score`) fetches only the 1-minute close at the exact horizon;
it returns `MISSING_OUTCOME` rather than interpolating a missing quote.

**Operational findings retained as engineering facts:**
- The provider's second request carries the tool result; with three full candidates
  it exceeded the policy's 7,168-byte safe input bound (8,158 bytes) and was correctly
  blocked by `ModelBudget` before HTTP. The candidate view is now compact (IDs, key
  features, cost) and the probe uses two candidates.
- JSON numbers in the model forecast (e.g. `-0.018`) are accepted only for forecast
  *estimates*, converted through their shortest decimal string; price/quantity money
  paths remain exact-string/Decimal and unchanged.
- WAIT with a forecast is a research record, not a position. The scored forecast did
  not create an order; realized trading P&L for this run is zero because no trade
  occurred, and is reported separately from forecast error.

Limits: single forecast; current catalog (not historical causal membership); absolute
timestamps visible to the model; no account minimum/feeAsset/finality verification;
no independent-exposure sample. The positive-result gate remains **not established**.
