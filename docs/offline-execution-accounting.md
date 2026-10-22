# Offline execution accounting — 2026-10-22

Scope: Ledger.record_intent/record_fill/cancel_intent and WallexLiveBroker; callers
PaperBroker and historical evaluation retain their APIs. No dependency, market policy,
credential, production transport or existing database schema/migration was changed.

## Official source observation (S)

Read current official pages over public GET, HTTP 200:
[create](https://developers.wallex.ir/docs/spot-create-order),
[detail](https://developers.wallex.ir/docs/spot-single-order-detail),
[cancel](https://developers.wallex.ir/docs/spot-cancel-order),
[order history](https://developers.wallex.ir/docs/spot-order-list).
The linked [Swagger](https://developers.wallex.ir/assets/files/spot-b9d06896d1009adc9ebc69b9a5495e7e.json)
SHA256 is `10d8667602b3f82428b7a35688174449843e6ed36c9de816050dccc3e6a69753`.
The obsolete /spot/... search results returned 404 on open; they were not treated as
current production attestation. Current page captures are ignored under .local/parallel.

POST /v1/account/orders documents 201. GET and DELETE
/v1/account/orders/{client_id} use client identity. GET /v1/account/orders is
paginated order history (per_page max100); no separate uniquely identified private
fill-history endpoint was found in this specification. OrderResource supplies
executedQty/executedSum and fills. TradeResource supplies price, quantity, sum,
fee, feeAsset, isBuyer, symbol and timestamp string, with no fill ID. Documentation
does not establish cumulative-list completeness, revisions, timestamp precision,
base-fee treatment of executedQty, or terminal finality for this credit account.
These remain U; public trades are not private account fills.

## Implemented offline contract (D, not exchange attestation)

Synthetic schema fixtures explicitly name their evidence kind. Every accepted
snapshot has full identity, exact origQty/price, supported active/status and totals
matching the complete fill multiset. Stable content+occurrence IDs preserve identical
repeated fills and array reordering. A missing/revised prior fill, unsupported fee,
future fill, inconsistent terminal or partial total is UNKNOWN with no settlement.
This mapping is offline-only, not a replacement for exchange-attested execution IDs.

Intent, reservation and SUBMITTING state commit together before any mock HTTP.
A cumulative snapshot settles all new fills, cost basis, P&L, terminal status and
unused reserve in one FULL-synchronous BEGIN IMMEDIATE transaction. DELETE cannot
settle canceled state: a subsequent complete GET is required. Timeout/404/invalid
JSON never releases funds or resubmits. There is no automatic HTTP retry. Unresolved
orders block new intents. New fills after a settled terminal state fail closed.

A SQLite exclusive operation lock spans mock HTTP and settlement, is released by
the OS after process death, and coordinates one shared local ledger path. It is not
a distributed account lock: different paths/devices are not coordinated. Production
transport remains unconditionally blocked; do not run laptop and Liara workers.

Shared fixes: repeated partial cancel cannot release another order's reserve;
conflicting duplicate fill timestamps reject; fills after terminal settlement reject;
LIMIT violations and negative sell proceeds reject. Decimal cumulative fee allocation
retains exact remainder rather than independent proportional rounding of each fill.

## Independent monetary oracles and fault evidence

Initial cash 5,000,000 TMN. Buy limit230,000 qty6.5 reserve fee4,485 => locked1,499,485.
Fill2 at229,000 with fee1,374 TMN => free3,502,521, locked1,038,105, base2.
Additional fill1 at230,000 with fee0.003 USDT then cancel => cash4,310,626,
locked0, base2.997, basis689,374. Reordered/repeated snapshots and reopening the
SQLite file retain those exact results. Independent sell oracle: buy2 at100 fee2;
sell1 at120 fee1.2 quote; sell0.5 at110 fee0.1 base => cash971.8, base0.4,
basis40.4, realized12.2, equity1015.8 at110 (unrealized3.6).

Fault checks include aborted state INSERT before HTTP, crash after intent commit
before HTTP, second-fill INSERT failure rolling back both fills, stale/revised/future
snapshots, cancel/fill race, duplicate terminal GET and process-kill lock recovery.
SQLite trigger failures simulate storage errors; no physical disk-full/power-loss
experiment or private account response was performed. Existing database fixtures are
reopened; no migration or destructive reset is needed.

Phase status: OFFLINE_CONTRACT_VERIFIED; production contract BLOCKED_SEMANTICS.
This is not live readiness or evidence of strategy profit.
