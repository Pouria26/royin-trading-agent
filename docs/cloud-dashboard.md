# Separate cloud dashboard

The trading source stays frozen at026a1be. The monitor is an independent Liara
application, `royin-monitor`, with its own512MB workload and no financial disk,
Wallex key, model key, Liara administrative token or trading imports.

`python -m dashboard.cloud` serves the existing RTL dashboard and local fonts.
All pages, fonts and monitoring APIs require HTTP Basic authentication over TLS;
only `/healthz` reports generic web-process availability without account data.
The private credentials are generated in an ignored local file and passed through
the monitor application's environment, never through the build context or CLI
arguments/output. Order/withdrawal/transfer endpoints do not exist.

The only write endpoint is `/internal/snapshot`: timestamped HMAC authentication,
nonce replay rejection,256KiB size limit, mission/schema validation and field
allowlists. Its effect is replacing an ephemeral monitoring copy in the monitor
container. It cannot write to the engine or financial databases.

## File-only publisher and noninterference

A low-priority, single-owner publisher in the existing engine container reads only:

- `/state/local/dashboard/engine-snapshot.json`;
- the current mission's atomic `signals/manifest.json`;
- a bounded tail of `financial-audit/audit_trail.jsonl`.

No financial SQLite connection is opened. Raw model messages, account identities,
private captures and credentials are not exported. Model manifests are reparsed
only when their modification signature changes; audit reads are bounded. Each
push has a five-second timeout, no redirects and no retry; the next scheduled
30second publication is independent. No market/model request is made by this
publisher. It has a finite deadline and a single-instance file lock. Its process
environment excludes all trading/model/Liara keys.

The publisher is launched without changing the engine's code, environment,
container release or PID1. Before/after process start time, journal/source/config/
permit identities must match; legitimate autonomous trades may change balances.
Do not require financial balances/counters to stay fixed during this comparison.

The publisher does **not** automatically survive an engine-container restart.
In that case the independent dashboard remains available but displays STALE once
the saved engine heartbeat exceeds120seconds. Trading protection does not depend
on this monitor. Relaunch the publisher using its existing settings and lock;
never restart/reprepare the engine or reinitialize a budget to fix monitoring.
Monitor-container restarts lose its ephemeral copy; the publisher's next normal
push restores it without touching the engine. No shared financial disk is mounted.

The activity panel is a bounded view of recorded model decisions and audit events,
not a complete order history or independent exchange finality. Missing history,
budgets and archived evaluation inputs stay unavailable. A recent delivery does
not make an old engine heartbeat fresh. Existing research views are retained but
not populated with fabricated data.

## Validation

23 dashboard tests passed, including authenticated real local HTTP, HMAC/replay,
stale heartbeat, source mission, float-money rejection, nonmutating file projection,
secret-field omission and legacy localhost-only behavior. Initial eight harness
errors used an unsupported HTTPConnection context manager; changing the harness
to contextlib.closing fixed them without weakening assertions.

Fresh desktop1440px and mobile390px browser contexts rendered the protected local
candidate: no horizontal overflow/page errors, both fonts loaded, report details
opened and pause/resume controls changed state. Before/after screenshots remain
ignored. The kit accuracy report is separate tooling evidence, not a product score.
Actual cloud release, authentication, repeated delivery and unchanged trading
process require post-deployment evidence; they are not established by these tests.
