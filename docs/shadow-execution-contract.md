# Shadow contract and delivery evidence — 2026-10-22

Status: **BLOCKED_CANDIDATE**. No candidate has independent source/strategy acceptance.
OBSERVE_ONLY is the sole active runner mode. The existing pre-I/O universal deny
remains stronger than a superficial APPROVED string. No approval parser or candidate
execution branch was added merely to demonstrate a green test.

## Approval contract required before any future opening

A reviewable approval must identify an independently accepted candidate, not just
assert APPROVED. It must bind all of: exact executable revision and source hashes;
validated non-secret runtime/risk/market config; prospective experiment plan hash;
source semantics contract hash; accepted dataset/manifest hash; full prompt/tool
contract hash; provider/model/settings hash including reasoning=none; symbol;
timeframe; issuance and UTC expiry; independently reviewed acceptance-result artifact
hash and its acceptance criteria/result. Acceptance must be for this exact binding
set and usable time period; diagnostic rankings and a self-authored string cannot
substitute. The host must derive expected bindings from current sources/config and
verify them before feed, ledger, model or transport construction. A change or expiry
must reject; unknown or absent fields must fail closed.

This is the future acceptance contract, **not an implemented accepting validator**.
No valid artifact or independent result exists from which to activate it. Current
runner refuses every Candidate request before I/O, including a plausible artifact
with any changed hash, symbol, timeframe or expiry. Those blanket-denial tests do
not establish accepting-validator coverage. An accepting validator and candidate
loop are deferred until source/strategy acceptance is real. There is no bypass flag.

## Current PaperBroker API and offline recovery

PaperOrder uses quantity and price; PaperBroker.submit_order returns PaperOrder,
process_candle matches bars, reconcile_order takes explicit simulated_state, and
finalize_portfolio performs host-owned settlement. No try_fill or amount field is
introduced. The runner does not call these methods while candidate gating is closed.

Additional independent synthetic tests reopen a durable paper ledger, recover the
host stop, inject a feed disconnect without changing money, then trigger the stop
with both model and HTTP calls forbidden. Hand calculation: initial1000, buy1@100
fee0.3, sell stop at90*.9995 fee0.003 => cash989.385135, base0. Repeated finalization
after reopening changes no money. The local Ledger.worker lock is used across each
paper execution section; its process-death exclusion/recovery is tested in phase1.
This is offline fault evidence, not a connected strategy run or cross-device lock.

## Bounded current observation and limits

A current public observation may be run with:

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts\run_shadow.py --mode OBSERVE_ONLY --cycles 1 --interval 3600 --max-attempts 1
```

It needs no .env/account/model, has no private write transport, excludes open candles
and preserves snapshots/raw hashes in a fresh directory. COMPLETE proves one current
diagnostic snapshot only; PARTIAL/exit2 is not a pass. A restart of the observer uses
a fresh manifest and never overwrites the first. Two quick snapshots do not prove
hour-boundary recovery, a one-hour strategy run, four cycles or multi-day stability.
Actual final revision, timing, manifest hashes and public audit outcomes belong in
the ignored final report. No Liara worker is deployed or started in this mission.

## Five-minute demonstration preparation

The detailed shot list and terminal commands are prepared at
.local/parallel/video-evidence-plan.md, without prompts, credentials or account logs
in Git. Planned sequence: challenge and closed gates45s; exact monetary/restart
oracle60s; own-ledger fake-vs-recorded replay75s; actual public diagnostic and hash
lineage60s; data/AI/production limitations and next decision60s. Show evidence-kind
labels before numbers; do not present invented equity as account profit. Recording,
voice narration, delivery destination and acceptance receipt require human work;
no video has been claimed recorded or submitted.

## Host position protection interfaces — B follow-up, 2026-10-22

PositionProtectionPolicy is explicit/hash-bound: initial_stop_pct, trailing_drawdown_pct,
checkpoint_profit_pct, review_interval_seconds, hard_holding_seconds, deadline_utc,
exit_buffer_seconds, max_quote_age_seconds and max_loss_tmn. All money is Decimal;
invalid fractions/time/mode reject. Parameters in the functional demo are synthetic
choices frozen before its outcomes, not tuned on actual trades or approved live risk.

PaperBroker.arm_protection requires actual fill evidence and terminal BUY state; it
binds entry/open time/policy once, preserves high-water on restart and never lowers
an existing stop. observe_quote checks the prior stop, net loss including estimated
exit fee/slippage, hard holding/deadline before raising the trailing stop. Actual
observed bid updates peak, not the future high of an ambiguous candle. Legacy candle
matching first evaluates old stops; the new monitor never uses high-before-low fiction.
Checkpoint requests a bounded review and does NOT force EXIT. Reviewer may exit normally
or HOLD; no model return is needed for the host-monitor function to enforce protection.
The independent caller must schedule these ticks while inference awaits; this branch
proves the function during a pending fake model task, not a deployed multi-hour worker.

Stale quotes block entries, never tighten peak or produce a fabricated fresh fill.
If a hard exit is due with stale data, EXIT_REQUIRED_STALE_QUOTE is visible and the
host needs fresh executable data; internet loss cannot promise a stop fill. Pending
orders require reconciliation/cancel. This deterministic paper controller does not
turn offline WallexLiveBroker into a production transport or override release gates.

PaperBroker.export_state is read-only: PAPER/SIMULATED_EXECUTION_NOT_ACCOUNT, quote
observation state/engine heartbeat, actual simulated free/locked balances, realized
net PnL, fee, gross price change, cost basis, net-if-exit estimate, sellable amount and
residual, pending IDs/status, high-water/trailing/exit reason. UI health must not be
engine health; this method performs no private request and dashboard code was not edited.
The5M paper portfolio is distinct from the separately observed5M account, never added.

Synthetic tests: above2.5% HOLD; rising peak then trailing exit; early discretionary
exit remains the existing risk/PaperBroker path; gap-through loss uses worse quote;
model timeout cannot own host stop; stale/hard deadline; restart peak and cash;
shared-account lock across different local DB paths; audit rollback and recovery
before/after flush acknowledgement. An audit replay may duplicate a stable event ID,
which the downstream exporter must deduplicate. Physical power loss/disk full and
real exchange fill identity/finality/expiry are unverified. Release stays NO-GO.
