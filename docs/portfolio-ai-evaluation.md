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
