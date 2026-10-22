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
