# Proposed engine export — NOT IMPLEMENTED

Integration request to Agent 2 / integrator. No engine endpoint is assumed or
implemented here. Choose one engine-owned atomic sanitized JSON snapshot at
`.local/dashboard/engine-snapshot.json` (proposed location), or agree a real local
read-only endpoint first. The dashboard will need a small adapter after agreement.
Current UI account/current risk/reconciliation remains UNAVAILABLE.

Engine alone owns private Wallex transport, GET budgets, reconciliation, worker
ownership and exporter lifecycle. Dashboard must never read .env or receive keys,
account IDs, private URLs, raw headers, arbitrary paths or raw provider responses.
An archived account probe is not a current account snapshot. No second worker.

Required envelope, proposed `royin.engine-monitor.v1`:

| Field | Meaning |
|---|---|
| source, evidence_kind | ENGINE_EXCHANGE_SNAPSHOT / EXCHANGE_AUTHORITATIVE; synthetic has separate explicit value |
| run_id, revision, config_sha256 | actual producing run/version, never dashboard checkout substituted |
| observed_at, received_at, exported_at | offset-aware actual source/engine/export timestamps; absent=null |
| status, warnings | AVAILABLE/EMPTY/UNAVAILABLE/STALE/INVALID; never missing→zero |
| mode, worker_state, heartbeat_at | actual run mode; ACTIVE only with independently defined heartbeat lease |
| account.balances | allowed asset symbols, free/locked decimal strings, unit per asset |
| account.equity_tmn | decimal or null, mark source/time and valuation definition required |
| account.realized/unrealized/fees | decimal + unit + accounting scope or null; credit fees distinct |
| reconciliation | MATCH/MISMATCH/UNKNOWN, compared_at, engine/exchange scope, allowlisted differences |
| risk | recorded stop/kill policy/value/state/time; no dashboard-invented threshold |
| orders | bounded rows; local opaque order_ref/client_id, symbol, side, status and actual state event times |
| fills | unique exchange-attested opaque fill_ref linked to order_ref/client_id; exact quantity/price/fee/fee_asset/time |
| decisions | decision_id, snapshot_sha256, validated allowlisted features, short reason/evidence, model/fallback, host gate, client_id |
| model | recorded model/provider, request outcomes/latencies; reported usage vs reservation vs invoice independent |

No raw account/order response IDs beyond necessary opaque join references. Monetary
decimal strings only; no float, NaN/Infinity, ambiguous TMN/rial conversion. Include
actual row units and pagination/truncation flag. UNKNOWN orders and reconciliation
mismatches are important warnings. Producer should cap snapshot size (proposed
2MiB), publish atomically, and expose no financial controls. Snapshot's existence
does not prove worker liveness. Stale threshold/heartbeat lease must be exporter
contract values, not the dashboard's public-candle display rule.

Committed DB or exchange-attested fill state is authoritative; audit-only tentative
FILL must not enter totals. Export after successful financial commit, preserve
rollback semantics and idempotent IDs. Keep local PAPER and exchange account
separate; a mismatch is meaningful only when both snapshots are valid, comparable
and sufficiently contemporaneous under the agreed policy.

Acceptance needed before enabling adapter: Agent 2 supplies schema/version and
real sanitized sample, timestamp/freshness definitions, finality/commit semantics,
row/byte limits, unavailable behavior and a read-only integration test. Current
dashboard acceptance tests do not establish any of these engine guarantees.

Agent 1 request: export actual decision_traces.client_id when an order is created
and order created_at/state history if available. Older portfolio artifacts omit
the join; dashboard correctly refuses to infer it from timestamps. Preserve old
artifacts/protocols and supply a newly versioned run after the integration barrier.

## Multi-asset projection correction — 2026-10-22

The snapshot and evaluation projections retain validated asset symbols instead of assuming USDT.
Engine balances require exact decimal strings and free+locked=total. Noncash holdings require an
explicit engine equity valuation; cash alone is not substituted as total equity. The account card
distinguishes the virtual paper ledger from an archived credit-account observation and has no
hardcoded5M balance. Worker state passes through the producing engine; it is not proof of a live
process lease.10 dashboard tests, Ruff, compileall and JavaScript syntax checks passed.
