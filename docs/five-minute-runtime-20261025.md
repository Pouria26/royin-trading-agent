# Five-minute entry cadence — 2026-10-25 Tehran

The operator explicitly requested entry analysis every five minutes, retaining BoxAPI and replacing its key later if needed. This authorizes the cadence change; it supplies neither a new credential nor an additional funded allowance today.

## Implementation and invariants

An optional scheduling amendment is appended to the existing runtime source-transition receipt. It binds `entry_analysis_interval_seconds=300` to the ORIGINAL service-contract hash, original config/permit bindings, source hashes, backup and quiescence receipts, and the operator instruction hash. Existing receipts stay unchanged and remain valid. No service contract, scope limit, budget row, financial intent or reserve is rewritten.

`signals_for` reads and validates the amendment from the original financial metadata and passes the effective interval to the existing orchestrator. The orchestrator durably claims `now+300` before I/O. The pre-existing `next_entry_analysis_at` is preserved on upgrade and restart; therefore the first pending old appointment may still follow its old 15-minute spacing. Subsequent entry analyses use five minutes. Closed-bar publication/freshness windows, one position, open-order reconciliation, every economic/risk/UNKNOWN gate and 30-second host risk polling remain in force. This is an analysis cadence, not a promise to buy every five minutes.

The manifest now reports the effective `entry_analysis_interval_seconds` separately from the immutable original contract. Later source upgrades without a new schedule inherit the previous authorized interval. Malformed/partial cadence fields, booleans/strings, unsupported intervals and another contract are rejected. An ordinary restart creates no new analysis allowance.

## Validation

Before implementation, five new regressions failed (ten errors including subcases) because no authorized cadence override existed. After implementation,44 targeted runtime/fresh-mission/multiday tests PASS in9.132s. Full core598 PASS in74.167s; dashboard31 PASS in8.838s. Ruff,compileall,diff check, four paper self-checks and example config PASS. These are synthetic/offline, not exchange fill or forecast-profit evidence.

Minimal runtime delta against frozen2638 is three files: `src/royin/runtime_release.py`, `scripts/run_fresh_service.py`, `scripts/run_market_paper.py`. Test `tests/test_entry_cadence.py` checks the original contract and DB dump remain intact, signed receipt fields cannot be changed/omitted, a subsequent upgrade keeps300, live signal wiring receives the amendment, and restart retains the pending deadline then claims exactly300 before a deliberately failed public I/O. The claim survives that failure; a second same-window attempt performs no I/O.

Candidate `0af4add04a9573e63f1dd962d0007d6096888101` is CONTENT_HASH_NOT_GIT_COMMIT; source `1836f59cb6f33263786dd1a7fdff203cbbccda776bb791373a5bea04c1431b2e`,ZIP `0861795dfc447361155c1f2c8ead2b1f1e369a6fe3486b58651d80e99d5c090d`,71 runtime files. No commit, push, UI or financial-size change.

## Budget and later key replacement

At the last pre-upgrade observation, the original ledger held578 total reservations; the active funded key held275 reservations/USD1.198208 conservatively reserved, not an invoice or provider balance. Original funded ceiling2.822355USD, daily1.10USD,647 HTTP and22Mtokens remain. The service scope had139 roles/270 HTTP with limit323 roles. Five-minute work can reach today's daily cap in roughly4–5hours, and finite scope/global/token limits can also bind. A new key has not been installed or tested. Budget exhaustion closes new model entries; existing host exits/reconciliation do not depend on a successful model call.

A future BoxAPI key must be installed through a controlled credential-bound transition. An env-only replacement under the old credit ID is deliberately rejected by fingerprint checks. A new funded allocation must be appended to the ORIGINAL DB using the reported new balance and explicit spending authority; original credential use stays recorded. Effective config/credit and durable role-scope bindings must be migrated with old counters retained, and any newly authorized scope ceiling must be explicit. Existing runtime source receipts bind the original config and must never be rewritten to imitate a clean start. A budget-only entry block may be cleared only after its new funding/binding is verified; an UNKNOWN/reconciliation block is not a budget block and must remain. Open-position restart/credential migration is not verified by this release; prefer a flat controlled handover. Wallex account/key, balances and trading journal are independent and remain unchanged.

## Deployment acceptance

Pending actual receipt. Package preparation or offline tests alone do not prove the running cadence. Verify all71 file hashes/import roots, old budget/trace prefixes and original journal/config/permit/UNKNOWN, then observe normal runtime claiming a300-second next deadline. No worker should be started in parallel with the financial owner.

## Actual deployment and first five-minute claim — 2026-10-25 18:24 Tehran

The original mission9 was quiesced under the exclusive service-owner lock; its stored old status remained RUNNING because platform termination did not persist a graceful terminal record. A separate quiescence receipt recorded the new maintenance process/lock ownership; old status was not relabeled. Consistent backups are `/state/upgrades/five-minute-20261025`. All tables in financial/signals/budget/historical and the original manifest matched backups before activation, except the authorized append-only source transition.

Source-transition SHA `c673c3f8e431027cf202db796681d54e0ce6e0d09131003dac0ef1b05f7805a8` includes the300-second amendment and original service-contract SHA `de435c5812cf093f13b6c0d1c492d3cef90722e2dac4bcf8d2c403a68526aeb5`. All71 actual hashes/import roots verified; original journal/config/permit/UNKNOWN/raw SHA and27 env preserved except release-control variables. Original image/disk/mission retained; no commit, push, UI change or second financial worker. PID1 start ticks1353440002. Single original publisherac046/settings/PID22 restored without financial env or settings changes. Health/readiness200,monitorAVAILABLE,HTML/JS/CSS unchanged.

The pending old deadline1792939943 remained intact before the first new cycle. At1792939964, the live financial heartbeat was1792939953 and the newly persisted analysis deadline1792940253: **exactly300 seconds**. Tehran times18:22:33 ->18:27:33. The code claims this deadline before public/model I/O; no artificial restart call was inserted. After completion, the manifest reports effective interval300 while the immutable original contract still reports900.

The normal production cycle issued18:23:05.586Tehran/14:53:05.586UTC,trace175/record176:BoxAPI/gpt-6-luna,2 HTTP200,request10048/25394bytes,SDK10729input/561output,source binding matches,comparison VERIFIED with6 accepted/2 feasible,MODEL_DECISION/WAIT(PEPEq50zero),no host validation error or last-cycle error. There are still zero actual orders/fills/financial attempts. This validates the first normal cadence claim and provider compatibility, not profitable entry or completion of a real buy/sell.

The first cadence observation proves a scheduled five-minute interval; it is not a measured guarantee of exactly12 completed analyses each hour. Publication windows,30-second polling, model/network time, budget, an existing position or pending reconciliation can defer work. No new key or additional allowance was installed; later credential/config/scope migration remains a separate controlled operation when the operator supplies the next credential and funded authority.

Final continuation check18:26Tehran: all original578 reservation rows and175 traces are exact prefixes; current580/176,29 scopes with original bindings and monotonic usage, cadence/coverage/bootstrap monotonic, journal/config/permit/UNKNOWN raw unchanged. One read-only exec connection failure recovered on retry; it was not silently counted as a pass. EngineRUNNING,last_errorempty,financial orders/fills/attempts0.
