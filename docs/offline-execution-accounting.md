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

Audit and timeline regression resolutions:
1. Event staging on transaction boundary: Ledger stages audit events (`INTENT`, `FILL`,
   `LEDGER_RECONCILIATION`) in-memory during active database transactions. Events are flushed
   to the durable audit sink only after SQLite `db.commit()` succeeds. If an outer transaction
   aborts or rolls back (e.g. second-fill INSERT failure or trigger abort), staged events are
   cleared, leaving zero false audit claims.
2. Fill timestamp lower bound: Both `Ledger.record_fill` and `WallexLiveBroker._settle_snapshot`
   enforce `fill.timestamp >= intent.created_at`. Fills preceding intent creation are rejected
   fail-closed with `ValueError`, closing the pre-intent inventory loophole while allowing
   same-second execution (`timestamp == intent.created_at`).

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
snapshots, pre-intent fill timestamps, audit emission rollback, cancel/fill race,
duplicate terminal GET and process-kill lock recovery. SQLite trigger failures simulate
storage errors; no physical disk-full/power-loss experiment was performed. Existing database
fixtures are reopened; no migration or destructive reset is needed.

## Read-only account and market contract verification (2026-10-22)

Authenticated read-only verification executed 5 GET requests (against the 8 GET cap, 0 docs GETs):
- Sub-account: Verified single active prop account (`isActive=True`, `isSuspend=False`).
- Balances: 5,000,000 TMN available, 0 TMN locked; 0 USDT available, 0 USDT locked.
- Fee schedule: Maker fee 0.25%, Taker fee 0.30% for USDTTMN.
- Open orders: 0 active orders on sub-account.
- Market rules: USDTTMN spot enabled (`amount_precision=2`, `price_precision=0`, price ~266,721 TMN).
- Proposed pilot envelope (200,000 TMN): At current market price (~266,721 TMN), 200,000 TMN yields
  0.74 USDT, which is strictly below the exchange spot minimum order quantity of 1.0 USDT. Status
  is `BLOCKED_MINIMUM`. The ceiling is not raised without explicit human/organizer authorization.

Phase status: OFFLINE_CONTRACT_VERIFIED; read-only account confirmed; pilot execution BLOCKED_MINIMUM & BLOCKED_SAFETY_GATE.
This is not live readiness or evidence of strategy profit.

## B follow-up, 2026-10-22 — bounded release remains NO-GO

This section supersedes the earlier claim that min_qty1USDT was exchange-verified.
The current five-GET read-only observation confirmed the same selected active credit
account,5000000TMN free/0locked,0USDT,0open orders and USDTTMN maker.0025/taker.003.
Amount precision2/price precision0 and is_spot were observed. These are NOT proof of
spot minimum, tick/step, actual fee asset, package universe or expiry. Probe counts
attempts before send (including failures), rejects unknown/incomplete order-list
schemas rather than claiming zero, preserves raw SHA/times in fresh ignored paths,
never writes .env and returns NO_GO_CRITICAL_CONTRACT_UNKNOWN/exit2. No new order.
The5GET/8 allowance leaves3unused; no retry.4/4 docs GET were used without retry:
create,detail,package details and basic-service Swagger. Official package details
requires a known package ID and reports expire_days, not this account's actual expiry.
No package ID or date was guessed and OTC minimum was not repurposed as spot.

Implemented additive interfaces (legacy signatures preserved):
- Ledger.initialize_portfolio initializes only an entirely empty unbound ledger and
  binds initial capital/currency/config; reopening never set_balance or resets peak.
- claim_candle durably claims before inference; pending claims after restart require
  reconciliation, never another model call. complete_candle co-commits the exact
  decision with a paper intent in the same outer transaction. No outer transaction
  should surround network send; WallexLiveBroker persists intent before HTTP itself.
- Ledger.worker may span the worker lifetime and accept a shared lock directory plus
  account fingerprint; distinct DB paths in that directory exclude each other.
  OS releases SQLite lock on process death. This is local-host exclusion, not a
  distributed lock. No lock or DB was deleted. Broker methods reuse only the same
  thread's already-held worker session; no independent second-worker bypass.
- Financial events enter a new audit_outbox table in the money transaction. Rollback
  leaves no tentative event. Post-commit/pre-flush crash retains events. File delivery
  is at-least-once with stable journal event IDs, not an impossible cross-file exactly
  once claim; consumers dedupe by ID. Failure of either sink or acknowledgement marks
  audit_failed and blocks new entries. Paper money+order+stop writes are atomic and
  in-memory broker state reloads after errors. Exit settlement may commit even when
  audit later fails: caller must report the error and replay the outbox, not resubmit.
- Risk blocks all nonterminal pending states across the portfolio, including UNKNOWN
  and SUBMITTING, and applies one-position/no-adding protection for initialized pilot
  portfolios. EXIT independently checks min_quantity. Other quote execution remains
  rejected (TMN only); scanner USDT valuation is not authorization for USDT execution.

Pilot is now an explicit restartable offline step with durable IDs and request count.
OPEN/UNKNOWN/partial stays pending; restart GETs the same ID, never reposts. A filled
or reconciled canceled buy alone enables exit review. EXIT needs a caller-supplied
fresh quote/actual timestamp; the old artificial+60s/unchanged price has been removed.
TTL30s requests cancel once after reconciliation; DELETE ack does not settle reserves,
the next step GET must settle. Eight HTTP attempts/two created orders maximum; residual
or unresolved state is explicit, not COMPLETE. Production transport remains denied.

Sellability is explicitly scenario-only: quote fees, base fees on both sides and mixed
base-buy/quote-sell have independent arithmetic tests, cash debit<=ceiling and stressed
exit price. PASS_SELLABLE does not imply residual0: the old1.12/1.11 example can leave
.006640USDT under mixed fee assumptions. Unknown real feeAsset is not silently chosen.
--prepare has no implicit current-price fallback; no --price yields NO_GO unknown quote.
An explicit --price is HYPOTHETICAL_NOT_CURRENT and rules remain synthetic. --run rejects
before config/cache/account construction. Both technical pilot and first AI strategy
trade options are separately NO_GO; no amount increase, averaging or manual trade flow.

Reproducible functional demo, no network/keys/model:
`.venv/Scripts/python.exe -X utf8 scripts/run_live_pilot.py --self-check`
uses four independent synthetic5M portfolios and immutable hand-money expectations.
4/4 correctness oracles PASS (100% technical success), trading win rate/probability null.
Checkpoint->trailing final5002686.306; gap-through final4978770.270; hard-holding final
5000693.3030; target-only case retains2base with4799400cash, unliquidated equity separate.
These are not exchange profits or samples for an estimate of strategy success.
Existing raw artifacts/protocols/root status were not overwritten; final source freeze
belongs to integration. Exact test counts/revision/commands are in the private handoff.

Audit recovery also persists the original run/code hashes and order decision context
in the outbox, including across restart; unattributed legacy events stay explicitly
UNATTRIBUTED rather than being relabeled as new-run evidence. A failing regression
caught wrong d3 attribution for d2's fill; it was fixed in shared ledger staging,
not by weakening the existing historical oracle. All direct record_intent/record_fill/
cancel operations now keep their event in the same outer financial transaction.
