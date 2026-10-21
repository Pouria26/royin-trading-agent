# Candidate diagnostics and observation acceptance

Integration review: 2026-10-22 Asia/Tehran. This replaces the draft Agent 2 evaluation
report; the original draft is preserved locally in artifacts/integration-review.
This is acceptance of the delivered engineering scope, **not strategy acceptance**.

## What is independently verified

- Delivered pointer, raw-manifest hash, frozen data-plan hash, source hashes,
  dataset metadata and both normalized hashes were verified before edits.
- Native-hour coverage is 517 + 106 = 623 bars. The missing hour
  2026-09-22 13:00 UTC remains a gap. No filling, bridging or relabeling occurred.
- Offline replay of the 40 captured requests reproduced both segment hashes
  with zero new GETs. Original captures remain immutable and ignored.
- Six frozen rule configurations run through the existing feature/risk/ledger/
  PaperBroker engine. They are baselines **without AI**.
- Seven nonoverlapping 72-hour diagnostic windows were evaluated: six in the
  first segment, one in the second. Each has 31 preceding warmup bars; warmup
  may overlap adjacent diagnostic windows, but their evaluated hours do not.
- Hourly diagnostics use the same bar parameters as the archived 15-minute
  plan. They are a different timeframe experiment, not validation of that plan.
- No new paid model requests, credit actions or real orders occurred.

## Corrected diagnostic results

Source: artifacts/candidate-evaluation/20261021T221403Z_4da16f77/manifest.json.
The manifest records the dirty source revision and exact executable hashes.
Fees use the reported TMN taker ratio 0.003 per side; order precision/minimums,
fee asset and volume-based fill assumptions remain research assumptions.

| Segment | Candidate | Worst 72h net % | Sum of window net % | Closed round trips |
|---|---|---:|---:|---:|
| 517 bars / six windows | reversion_35 | -0.386719 | -1.081026 | 10 |
| 517 bars / six windows | reversion_30 | -0.647269 | -1.019376 | 6 |
| 517 bars / six windows | reversion_40 | -0.927899 | -1.830174 | 11 |
| 517 bars / six windows | trend_0_006 | -1.163942 | -3.133612 | 11 |
| 517 bars / six windows | trend_0_003 | -1.565283 | -2.711694 | 9 |
| 517 bars / six windows | trend_0 | -1.623676 | -4.355013 | 13 |
| 106 bars / one window | reversion_30 | +0.120389 | +0.120389 | 1 |

The sum compares independent windows reset to the same initial capital; it is
not a compounded account curve. A positive single trade does not establish an edge.
No candidate was selected or approved. The other five configurations also appear
in the machine-readable manifest; omitted table rows are not omitted experiments.

## Important corrections to the handoff

- Ranking development outcomes is not a validation gate. The earlier test of a
  local Boolean expression did not test a production gate; it was replaced with
  regressions against real ranking/configuration functions.
- The frozen plan had no dated new split and fixed a 900-second interval.
  Agent 2 nevertheless computed outcomes across both native-hour segments.
  In particular, September 24–27 outcomes were exposed. That interval can no
  longer be represented as an untouched holdout. No successful formal
  validation or holdout evaluation is claimed.
- Thirty trades is neither an official competition rule nor a sufficient
  statistical threshold. Sample sufficiency requires a defensible experiment,
  not an arbitrary counter; trading merely to reach a count is prohibited.
- A local lock file does not coordinate separate laptop/server filesystems.
  It only excludes processes sharing the same lock path.
- The initial observation runner could include an unfinished candle and permit
  candidate execution without an approval artifact. Both defects were corrected.
  Candidate execution is now unconditionally blocked before feed I/O.
- Source timestamp labels, volume units and finality remain unverified; hourly
  acceptance is DIAGNOSTIC_ONLY, not the old cross-resolution acceptance.

## Reproduce the diagnostic report

From the repository root, with the locally retained public captures:

~~~powershell
.\.venv\Scripts\python.exe -X utf8 -m scripts.evaluate_candidates --manifest data/round-2-data/20261021T213718Z_f8e726a7/manifest.json --manifest-sha256 a0f2e09cd732d183ffad674b2eb190b65018a16cc264a3b6acf0e8048a01b928
~~~

The tool verifies the manifest and dataset hashes, creates a new immutable run
directory, records code/plan/data provenance, and always labels this experiment
DIAGNOSTIC_ONLY with selected_candidate=null and candidate_shadow_approved=false.
A zero exit code means the diagnostic ran; it does not mean the strategy passed.
Exact offline replay needs the ignored capture bundle; a fresh clone alone does
not contain those public raw files. Include the bundle in the final judge package.

## Bounded public observation

~~~powershell
.\.venv\Scripts\python.exe -X utf8 scripts/run_shadow.py --mode OBSERVE_ONLY --cycles 1 --interval 3600 --max-attempts 1
~~~

Verified run: data/shadow/20261021T221522Z_0b227ff7/shadow_manifest.json:
one GET, one closed diagnostic snapshot, zero orders/model requests.
Two earlier strict attempts returned PARTIAL because the source omitted two
leading hours; evidence was retained. Shorter warmup coverage is now explicitly
recorded as requested_start versus actual_start. Interior gaps, invalid OHLC,
wrong cadence and stale data remain errors, not silently repaired.

For up to four distinct hourly observations in the foreground:

~~~powershell
.\.venv\Scripts\python.exe -X utf8 scripts/run_shadow.py --cycles 4 --max-attempts 4 --interval 3600 --poll-seconds 3600
~~~

This longer command is documented, **not executed or verified as a four-hour run**.
Ctrl+C stops it; after interruption check the process before removing a stale
local lock. After a crash, lock recovery is manual and fail-closed. No auto-delete
of another process's lock. No same-run resume: a nonempty output directory is
rejected to prevent overwriting evidence or resetting state.
COMPLETE means the requested number of diagnostic observations; PARTIAL exits 2.
Neither is a strategy Shadow result, AI evaluation, multi-hour stability proof,
deployment acceptance or live readiness.

## Next gates

Resolve or conservatively bound the native source timing/finality/volume contract;
freeze a new timeframe-compatible experiment and truly unexposed holdout before
further return inspection. Measure the actual AI contribution with a bounded
budget only on valid snapshots. A candidate must then earn real strategy Shadow
evidence and an independent execution/risk/account review before any live test.
Initial live size and growth remain subject to verified minimum/sellability and
an explicit user ceiling; there is no automatic move to 200k or 500k TMN.
