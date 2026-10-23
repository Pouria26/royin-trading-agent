# Multi-day runtime and release contract — 2026-10-23

## Authority and evidence

Organizer notice 13 supplied by the user keeps source/demo delivery at Friday
2026-10-23 23:50 Asia/Tehran and extends profit observation/conversion to the end
of Monday 2026-10-26. The notice does **not** specify Monday's exact hour.
The user confirmed credit extension through Monday. This is operator evidence;
the dedicated-key package-history endpoint returned 401, not a new expiry attestation.

Deployment is deferred until tonight at the user's request. The current CLI was
authenticated to a personal account: network creation succeeded but app creation
returned insufficient balance. The subsequently supplied team identity is the
intended deployment target. No application/worker was deployed in that attempt.
Do not top up an account or change unrelated applications.

## Explicit scheduling

`SUBMISSION_DEADLINE_AT` is separate from `TRADING_END_AT`; the earlier of the
financial end and an explicitly known `CREDIT_EXPIRES_AT` governs liquidation.
Conflicting legacy `CHALLENGE_END_AT` and new financial deadlines are rejected.
No field silently extends credit or the competition. A team-selected conservative
Monday cutoff must be labelled a policy choice, never an organizer-confirmed hour.

`ServiceContract` binds one mission to aware times, 30-second default protection
polling, durable 300-second entry cadence, fixed debit/minimum/horizon, and finite
public/model limits. It supports at most four days. Legacy experiment caps remain.
Restart cannot move the start, clear cadence, change source, or reinitialize state.

## Shadow service

`python -m scripts.run_service --prepare ...` is explicit initialization with the
original existing model ledger. `--run` requires the original prepared state,
source/config/contract bindings, and a provisioned persistent-volume marker.
No automatic empty budget or paper portfolio is created on normal service start.
Only one owner acquires the volume lock, before engine initialization writes.

Missing model state during restart closes entries and leaves position protection
operational. Risk stops, forecast expiry, and finalization do not require the LLM.
Actual public quotes are still necessary: outage/depth failure must leave an
explicit residual, not a fabricated fill. Terminal missions do not restart research.
`/healthz` is process/state liveness; `/readyz` separately reports entry readiness.

## Fresh financial mission

The user's new direct instruction authorizes proceeding with a fresh financial
mission despite the old unresolved request. This supersedes the previous
requirement to obtain authoritative historical finality **for starting a new lane**.
It does not establish that the exchange rejected/canceled the historical order.

`FreshMissionPermit` and `authorize_fresh_mission` record the exact operator
instruction/hash, account, release, historical SQLite hash, baseline cash, and
`exchange_finality=UNCONFIRMED`. The original financial DB, UNKNOWN intent,
reserve, counter=8, and client ID remain intact. At least 100,000 TMN stays outside
the new allocation as historical-risk quarantine. No historical POST is retried.

The new allocation/debit cap is 150,000 TMN, one position, no automatic size
increase. The default permit allows **one BUY**, bounded cumulative GET/DELETE,
and up to three owned SELL attempts after previous orders settle. A larger
predeclared finite trade count is a separate permit policy, not a restart reset.
This does not authorize using 70% of the wallet.

`FreshMissionTransport` accepts only exact durable LIMIT intents for that mission,
account, and symbol. It requires recent book/account/economic/real-AI evidence
before BUY, reserves counters before HTTP, never retries POST, and preserves
UNKNOWN on ambiguous responses. The received-response clock is host-supplied.
The ordinary `RuntimeConfig` live flags remain closed; only the explicit prepared
fresh-mission command constructs this transport.

`run_fresh_service` reuses the existing causal research/AI path through an
`EntrySignals` override that cannot simulate an entry. A separate financial
ledger tracks actual exchange fills. Account totals include the cash outside
the mission; foreign orders/assets close new entries. Cumulative fills, partial
fill cancellation, residuals, and UNKNOWN remain real broker observations.
Stops/trailing/forecast/finalization are host owned. The initial bounded live
exit policy is distinct from paper's policy; do not transfer paper return claims
to it. No profitability or production readiness follows from fixture tests.

## Deployment and state transfer

`scripts/package_release.py` exports an explicit committed allowlist with hashes;
it excludes .env, credentials, raw artifacts, databases, research, and .git.
Do not deploy the working repository as an unrestricted archive. Docker uses the
pinned Python image and exact requirements lock, non-root UID10001, one worker,
and `/state` for all persistent data/artifacts. The default entrypoint requires
prepared state. Explicit maintenance reports `MAINTENANCE_NO_ENGINE`, not readiness.

Use `scripts/backup_runtime_state.py` for a SQLite backup API snapshot, with a
30-second bound, quick_check, row counts and hash receipt. Copying a live DB file
without its journal is not a safe transfer. Preserve the original model ledger,
external consumption ledger and historical financial evidence. Confirm source
owner shutdown before transferring exclusive execution ownership to Liara.
Upload private state over Liara FTPS with verified TLS, never in an image/build.

On the team account create one dedicated Docker app and persistent disk, mount
`/state`, verify writable ownership for UID10001 and the volume marker, prepare
once, then run one instance. `ROYIN_SERVICE_KIND=shadow` is default;
`fresh-live` requires the separately prepared permit/state. Missing state must
block startup. Verify revision/hash, heartbeat, disk readback and restart behavior
on the real server. HTTP200 maintenance alone proves none of these.

## Evidence at implementation time

Linux lab: a synthetic held position, stop, cadence, one intent/fill and one model
reservation survived SIGKILL/restart unchanged. A second owner was rejected.
The lab had networking disabled and no real credentials/state. It did not prove
exchange exit execution, Liara volume behavior, strategy alpha, or profit.
On integrated main, 468 core tests and11 dashboard tests passed. The Linux
financial/service subset passed45 tests with networking disabled. An initial
Linux run without a prepared volume failed; a subsequent run exposed unwritable
HOME. Those failure logs are retained, and the rerun passed with persistent HOME.

The paired prospective paper experiment on 7df0d08 remains a separate frozen
experiment. Its terminal report and accounting replay must be evaluated before
this candidate replaces main. Live activation, real-provider validation of the
new prompt, and team Liara deployment are still separate acceptance steps.
