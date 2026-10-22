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
