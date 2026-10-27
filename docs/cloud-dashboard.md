# Separate cloud dashboard

## Recorded contract — 2026-10-25 morning

Financial source at that observation was immutable artifactd3e64d8b7a4213bbf98caa1cdf4f26702b7f92cc,
same original mission9. Earlier026a1be/eb0596 source references below are historical.
Cloudsource1defe3acc7f88b6c6bc40c151d39fce7e72d1641b8777b6a358dd4ea2d48e66b;
publisher sourceac04648803ae5d16b67aa07e1e3795e0b9558bf93b54b899c1a80b7c916ad3a6
is recorded in /state/monitoring/publisher-settings.json publisher_source. Restore it
after engine restart, never an old hardcoded publisher folder or a second worker.

Explicit extension to former file-only contract: single low-priority publisher also
reads ORIGINAL MODELbudget via bounded mode=ro/query_only SELECT. No financial DB,
trading constructor, provider request or financial/model credentials are involved.
Only selected funded aggregate reservations and cached bounded recorded SDK traces
are HMAC-published. Cloud has no original DB/financial keys. Missing/partial usage is
explicit; invoice unavailable. HTML/CSS/fonts/layout unchanged, JS existingdatafields
bind actual attempts/fallbacks/timeouts/usage coverage. Acceptance/limitations:
docs/live-wait-and-model-telemetry-20261025.md.

## Historical initial contract — 2026-10-23

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

## Separate dashboard deployed without engine restart — 2026-10-23, 22:20 Tehran

User authorized cloud dashboard deployment with no trading restart. Independent royin-monitor app on small-g2 (512MB), sourceecdad5e, is READY at https://royin-monitor.liara.run. Generic health200; unauthenticated page/API401 and authenticated200 verified.13 actual runtime hashes, UID10001 and absence of Wallex/BoxAPI/Liara keys passed. Credentials only in ignored .local/review/royin-dashboard-login.txt; do not print or commit them.

Detached single-owner file-only publisherPID107, stripped environment,29MB RSS, low priority,30second sends/5second timeout; no financial SQLite connection, market/model request or engine code/env/release mutation. Reads only current monitor JSON, signal manifest and bounded financial audit tail; emits allowlisted decisions/events without raw model messages. Same financial PID1 start1792778957, journal/source/config/permit/revision026a1be matched before/after. Dashboard itself was restarted; its PID1 start1792781151 advanced, a normal push restored LIVE_BOUNDED/3decisions, received_at advanced1792781090->1792781300, engine identities still unchanged. One local TLS handshake timeout was retained; subsequent actual cloud HTTP/browser and publisher receipt succeeded.

23dashboard tests, Ruff/compileall/JS syntax, fresh local and cloud desktop1440/mobile390 browser checks passed (fonts, controls, no horizontal overflow/page errors). Shared kit accuracy_report failed dependency discovery (ERR_MODULE_NOT_FOUND / Playwright not installed in kit); not a pass or product score. Independent bundled-browser checks above are actual product evidence. No change to financial source; no Git push. Publisher does not survive an ENGINE-container restart: dashboard becomes STALE after120s and publisher must be relaunched with existing settings, without restarting/preparing financial state. Monitor-only restart recovers automatically on next push. See docs/cloud-dashboard.md. Future trading fills/profit remain separate evidence.
