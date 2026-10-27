# Operator accounting repair: active release; exact-zero settlement remains open

## Approved decision

The release fixes the observed fee/lot defect and implements two **separate, explicit policy authorities**. The direct human reply approved both exact exceptions and added a hard 23:30 Tehran settlement deadline. Both authorities have now been applied to production. The same original mission and budget were resumed; no fourth operator authority or cleanup purchase was created. After the user clarified that every crypto balance must be exactly zero, new entries were stopped durably at 21:24:46. The residual itself is still present.

1. Classify only the existing, fill-proven **0.475 PUMP** under one retained-operator-residual exception with a **600 TMN** initial marked-value ceiling. The original acquisition basis remains **547.619047619... TMN**. Every future residual remains subject to the ordinary **500 TMN** cap. The 0.5%-of-acquisition, eight-assets and aggregate 5,000-TMN limits still apply. This classification preserves the coin; it does not sell it, convert it to cash or create a completed round trip.
2. Accept a total discrepancy of at most **0.5 TMN** between integral TMN balance displays and the fill ledger, only with fresh, original-account, hash-verified API captures. Subtract **0.5 TMN** from displayed available cash before any order admission. No balance/fill/fee/basis adjustment is permitted. Non-TMN assets still match exactly, foreign or unresolved orders reject, and larger/accumulating discrepancies reject. This is a bounded operator policy, **not an established Wallex rounding contract**.

The exact two-exception question received the direct human answer: «اره پیش برو فقط حواست باشه مسابقه تا 12 امشب هست یعنی تا ساعت 11:30 شب باید ببندیم و تبدیل به ریال کنیم». A later clarification requires every cryptocurrency balance **exactly zero**. The separately approved residual policy preserves inventory and does not satisfy that final requirement.

## Current live facts

Production runs immutable artifact `bde2d9770d99dacc011baff6d29652dc4dc2e051`, source `4e7db4cbf3aabfe194799c59192fd498e3045cad62b820104291f54627d2b546`, with source history **22/MAX32**, retaining all 21 previous receipts. The original mission, image/disk, account, permit/config, 27 environment variables, 300s entry / 30s risk cadence and model funding remain intact. PID1 start ticks are `1363146335`.

The three actual operator BUY POSTs and one SELL POST remain the entire order history. BTC/LTC canceled unfilled. PUMP bought 130 at 1,150 with 0.325-PUMP fee; sold 129.2 at 1,158 with 448.8408-TMN fee. The actual remaining **0.475 PUMP** and basis **547.619047619... TMN** are retained. Exchange display is **4,999,665 TMN**, compared with fill-derived cash **4,999,664.7592 TMN** including the original 1M outside reserve. The approved bounded policy accepts the 0.2408-TMN difference while available allocation cash is conservatively 3,999,664.5 TMN; it does not correct the ledger to the display.

Fresh, hash-verified original-account GETs 1716–1718 all returned 200 at **21:40:49 Tehran**: 4,999,665 TMN free, zero locked, 0.475 PUMP free, zero locked, zero open orders. All six financial tables were unchanged by that observation. The motor reports RUNNING, empty last error and **OPERATOR_STOP_NEW_ENTRIES**. Operator-lane bookkeeping is COMPLETE, while exact-zero settlement remains **NOT_FULLY_SETTLED**. No closed round trip or model-origin ENTER is inferred.

## Root-cause correction

The previous calculation treated all fees at the taker rate. That was conservative for the four conditional cash examples but did not bound residuals after lot rounding: the actual lower maker fee left more coin. Checking maker/taker endpoints alone also misses intermediate rates and partial maker/taker combinations.

`project_exit_cash` now retains its four diagnostic fee-asset points and independently computes continuous upper bounds for residuals over the full 0..taker fee interval. The host always reserves taker base fees for a SELL. For acquired base B, step h and reserved fee f, sell quantity is `h*floor(B/(h*(1+f)))`. Remaining base increases within a floor cell, then jumps down; the interval endpoint and final internal boundary bound its supremum. Fraction arithmetic makes the floor-cell decisions exact and serialized bounds round upward.

Cash admission also covers fee-asset mixtures across BUY fills without charging full base and quote fees together. If b base units pay fees, quote fees satisfy `c/entry_price <= q*f-b`; the calculation retains that shared fee budget. Net cash is bounded at the relevant floor-cell boundaries. Target/median admission and operator planned loss use the conservative cash bound, while the raw point examples remain available as diagnostics. No forecast is increased and no entry is forced.

The actual 130-PUMP case now rejects. At the historical 1,150-TMN price, downward fitting selects **111.9 PUMP**, within the same 150,000-TMN debit ceiling and 100,000-TMN order floor. The old 668-lot BTC example is correctly rejected under the continuous residual bound; it is not removed from the market catalog. Tests preserve the original point calculations and add explicit regressions for the old false-positive admission.

A partial BUY below exchange minimum remains real inventory and blocks entry. This change does not claim that every possible partial execution can be fully liquidated.

## Reconciliation and restart behavior

`src/royin/reconciliation.py` defaults to exact matching. The optional authority binds the original journal, permit, account, source history and mission expiry. Bounded matching needs three fresh, successful, hash-verified original `/sub-accounts`, `/v1/account/balances-detail` and `/v1/account/openOrders` captures. The transport independently validates the witness after cash locking and checks the conservative cash lower bound. A bounded result cannot be relabeled as exact.

The existing residual validator gains one separately authorized, proof-bound schema-v2 exception. Ordinary schema-v1 receipts keep the original 500-TMN rule. The exception cannot be replaced, generalized to another asset, used for changed inventory/basis or applied to pending/UNKNOWN orders. The genuine original operator authority and actual BUY/SELL journal evidence are rechecked on every use.

On restart, only the obsolete `UNSELLABLE_RESIDUAL`/exit-depth reason can clear after the retained residual has been fully validated and no active order remains. Other account/operator/risk stops remain. A model proposal to repurchase the retained asset rejects before creating an intent. The existing operator lane can finish its bookkeeping while all three original authorities and the actual coin/basis remain intact; this does not increment closed round trips.

## Validation and independent Liara copy

- **711 core tests PASS in 89.669s**, **31 dashboard tests PASS in 8.544s**, Ruff, compile and four paper self-checks PASS. The last two regressions cover externally observed quiescence without forging a graceful-stop state.
- Original failing regressions and first full-suite failure are retained. The latter exposed a stale test assumption that BTC still had a valid lot fit; the test now explicitly checks the stricter, independently justified no-fit result while keeping both catalog entries.
- A keyless, network-disabled process on Liara loaded **all 74 exact candidate file hashes** and a consistent copy of the actual current financial database. It applied synthetic review-only authorities, preserved all six financial tables, every original operator authority, all transport counters and the complete 21-receipt source prefix, and exercised the restart path. No financial/model HTTP was possible in that process.
- The final isolated copy accepted the actual 0.2408-TMN display discrepancy with available allocation cash conservatively limited to **3,999,664.5 TMN** and retained exactly **0.475 PUMP** with its exact cost basis. Its fresh diagnostic bid was **1,174 TMN**, so the copied residual mark was 557.65 TMN, within the proposed 600-TMN exception. The earlier paused-only candidate and its separate successful copy evaluation are retained; both were isolated copy evaluations; the final candidate was subsequently activated only after direct human approval.
- Two diagnostic runs used a total of **six bounded private GETs and two public GETs** for fresh observations. The original production financial tables and PID1 start ticks **1361678471** were unchanged. There were zero new order POSTs, model diagnostics, source transitions, policy authorizations or financial-worker restarts in production. Final read-only preflight at **18:48:27 Tehran** verified the same 73 active file hashes, original 21 source receipts, four orders/two fills, 13 financial transport attempts, one original financial launcher and one publisher (observed PID22), no current error and the unchanged residual entry block. Durable account read count was 1,699; it was not reset.

The codebase graph transport is unavailable (`Transport closed`); exact source/test inspection was used. No complete graph-coverage claim is made.

## Frozen release and completed activation

- Content artifact: `bde2d9770d99dacc011baff6d29652dc4dc2e051`.
- Source: `4e7db4cbf3aabfe194799c59192fd498e3045cad62b820104291f54627d2b546`.
- ZIP SHA256: `36af78a4aed07ef8934bde1fc0ff8f3737a569615675ca1b6611b44d21237272`.
- Changed runtime files: risk, residuals, fresh_mission, operator_entry and run_fresh_service; one new shared reconciliation module. Tests and review artifacts are separate.

The original worker was put into maintenance and actual quiescence/owner-lock availability was observed before backup or policy application. Consistent backups of all original databases and the manifest are under `/state/upgrades/operator-accounting-20261026`. The 74-file immutable release was transferred and verified, fresh account/depth observations were collected, and the two approved policies, residual classification and source append were committed atomically. All original tables and manifest matched before reactivation, allowing only approved metadata, three account GETs and one OPERATOR classification audit event. No source, budget or authority history was reset.

- Human approval SHA256: `f337e98c108971cd34b59029cdb85c441a862e8edd746005c6f3c73edb605606`.
- Actual quiescence receipt: `e17d0ac8a5974adbc6deeaf92ad51a976296b3cdce0d10b657626dbceeeab848`.
- Residual-exception receipt: `4acaef881a91aa817ff8b20d67b2fb8014e5b82cebf8f7746dd9bb8a1aa5992a`.
- Display-precision receipt: `edf4251bacb48e300be49958c7382164d6cfb4c01fa7f42ca4be0d6a7dabaff5`.
- Source transition: `9fe33489866b1e0e5c58f061894f51034621ae2f5ff2c8583de6bee3d962e280`, history 21 -> 22.

The already committed apply controller must not be replayed. An initial restart readback still saw the old pod and the owner-lock guards rejected premature backup/transfer attempts without writes. The first long remote apply transport timed out before Python startup because canonical TTY input truncated the controller; a readback proved history21/policies absent/no ledger changes before the bounded raw-input helper applied it once. Those failed attempts remain in the ignored review artifacts; they are not omitted from the evidence.

## Actual runtime acceptance and limits

The first normal cycle of the active release issued at **21:17:01.985 Tehran**, with two BoxAPI HTTP200 responses, MODEL_DECISION and WAIT. Original 1,105 model reservations / 433 traces advanced to 1,107 / 434. Original prefix, exact scope identity, monotone usage, original grants, cadence, historical database, journal, config and permit checks passed. This is actual normal model execution, not evidence of forecast edge or an additional trade.

All 74 actual file hashes/import roots and the 22-receipt chain were verified. The original single publisher was restored from immutable `ac04648803ae5d16b67aa07e1e3795e0b9558bf93b54b899c1a80b7c916ad3a6` with original settings and model_credit_id=null; PID32 was observed. Engine health200 confirms alive; readiness503 reports POSITION_OPEN_PROTECTION_ONLY because non-TMN inventory remains. Do not claim readiness green. The monitor was AVAILABLE, HTML/JS/CSS hashes were unchanged, unauthenticated access401 and cross-site API403 passed. No commit/push, UI change or second financial worker occurred.

## Exact-zero deadline and remaining blocker

The user's final rule requires all crypto balances exactly zero by **2026-10-26 23:30 Tehran**, not merely below the minimum order. The durable STOP_NEW_ENTRIES file was written at **21:24:46** and the engine independently acknowledged OPERATOR_STOP_NEW_ENTRIES. It remains in place. Original entry cutoff21:50 and financial permit end22:50 already precede the user's deadline; neither was extended.

The ordinary PUMPTMN order path cannot fully sell 0.475 PUMP under the current minimum-notional and 0.1 quantity step. Official documentation exposes credit-package closure, but does not establish exact dust-zero behavior, fees or contest recognition. The exact read-only active-package preview returned HTTP401 while normal original-account reads returned200. No closure request was sent. The user reported no panel access to conversion/closure. An official native-settlement path is therefore still needed; details and a prepared inquiry are in [the settlement blocker report](final-settlement-blocker-20261026.md).

A one-shot heartbeat `automation-2` is active for **22:05 Tehran** to verify actual balances/orders and notify about an unresolved deadline. It performs read-only follow-up; it does not authorize financial execution. Full cash settlement, demonstrated model edge/profit and judge-side recognition remain **OPEN**.
