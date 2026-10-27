# Bounded operator execution, 2026-10-26

This report separates exchange execution from model forecasting. The human operator explicitly approved a BTC LIMIT entry, then authorized further analyzed operator entries. The stated competition requirement is an exchange-accepted order. Judge-side recognition has not been independently verified.

## Authority and limits

The implementation binds each human authority to the original mission `fresh_live_20261023_9`, account, permit, source and journal. This run permits at most three append-only authorities, one BUY POST per authority, at most 150,000 TMN including the conservative fee reserve, and one held position. Unfilled BUY orders receive one cancellation request after 60 seconds and require a complete cumulative GET before funds are released. Filled inventory receives the existing host stop/trailing/risk controller, a 2% initial stop measured from actual acquisition basis, and an exit deadline 900 seconds from submission. This is a host controller checked on the normal risk cadence; it is not an exchange-native stop or a guaranteed loss limit.

Operator entries are explicitly recorded as `OPERATOR`. They do not create fake `REAL_MODEL` signals, positive forecasts or model cost approval. The original model entry gates, BoxAPI pool, reservations, financial counters and mission deadline remain in force. There is no second financial worker.

## Actual exchange evidence

| Symbol | Accepted at, Tehran | Client order ID | Quantity / LIMIT price (TMN) | Observed result |
| --- | --- | --- | --- | --- |
| BTC | 17:10:41 | `fresh_live_20261023_9_op_a2819acd0170` | 0.00000668 / 21,570,899,157 | POST 201, success, NEW; DELETE 200 at +61s, then GET 200 CANCELED; no fills |
| LTC | 17:21:45 | `fresh_live_20261023_9_op_340bd446d5c6` | 0.00978 / 15,290,466 | POST 201, success, NEW; DELETE 200 at +61s, then GET 200 CANCELED; no fills |
| PUMP | 17:31:54 | `fresh_live_20261023_9_op_73a45b95a7b0` | 130 / 1,150 | POST 201, success, NEW; actual BUY fill at 17:32:43, cumulative GET confirmed FILLED |

The PUMP BUY spent **149,500 TMN**, acquired gross 130 PUMP and paid **0.325 PUMP** fee (actual maker coefficient 0.0025), leaving **129.675 PUMP**. The acquisition basis is retained as 149,500 TMN, or approximately 1,152.8822055 TMN per net PUMP. A cancellation request raced with this fill; its response already reported FILLED, and the subsequent GET supplied the original fill and fee. The cancellation acknowledgment alone did not create or settle that fill.

At 17:42:47, the original worker was RUNNING with a fresh heartbeat, no current error or entry block, three BUY POST IDs, no SELL yet, and exact retained inventory/basis. The controller's stop was approximately 1,129.8245614 TMN; last executable bid was 1,159 TMN. The operator exit deadline was **17:46:54 Tehran**. These are observations at a specific time, not a profit claim. The final exit and account reconciliation are recorded below when verified.

## Selection evidence and limitations

All additional market reviews used public GETs, not extra paid model diagnostics or a second financial process. The second review compared BTC, PEPE, PUMP, ARB, LTC and HBAR. LTC had relatively improved flow and a positive volume proxy, but its one-hour price trend was still negative; the engine waited while its spread exceeded the unchanged 0.5% gate and submitted only after that gate passed.

An initial third review had stale universe context and produced no usable candidates. That failed artifact is retained. The repeated review used the actual current universe from 17:26:02 and observed PUMP at 17:27:51: fitted capacity, indicative cash hurdle 0.8354%, spread 0.1744%, positive short-bar move and relative 24h strength. Counterevidence remained: negative 1h/15m returns and weak trigger volume. This was a bounded operator experiment under explicit authority, not demonstrated alpha or a claim that PUMP was objectively the best trade.

The exact raw market reviews, request hashes, authority chain, private account/order captures and readbacks are retained under ignored `.local/review/deadline-entry-20261026/` and the original server diagnostics. No credentials belong in this report.

## Implementation and corrections

- `src/royin/operator_entry.py` implements the three-authority chain, exact request idempotency, original-account/source binding, fresh passive LIMIT planning, downward lot fitting and independent pre-POST checks. Only the original worker consumes atomic operator request files. Each authority is consumed before a network POST; an uncertain POST is reconciled rather than retried.
- `scripts/run_fresh_service.py` integrates operator entry ahead of normal model cadence and manages actual inventory with the existing broker, stop, trailing and time-exit path. Decimal-valued public depth is serialized with `default=str`; a regression test uses real Decimal objects. A small partial BUY without a true SELL remains inventory, not post-liquidation dust.
- `src/royin/fresh_mission.py` permits only separately bound operator evidence while preserving original account, cash, risk, position and transport limits. `src/royin/residuals.py` requires the original operator authority plus genuine BUY/SELL and accounting proof for operator residual classification. Existing 500-TMN/0.5%-acquisition/aggregate dust limits are retained.
- `src/royin/live_broker.py` and `src/royin/canary.py` correct cancellation to `DELETE /v1/account/orders?clientOrderId=<owned-id>`. Only the exact owned-ID query is accepted. Complete subsequent GET reconciliation is still required. The actual BTC and LTC DELETE/GET sequences above verify this integration.

The first operator release failed on Decimal JSON persistence **before any intent or financial HTTP**. No order was silently retried or authority reset. The repair preserved the same unattempted BTC authority through a bounded append-only runtime compatibility receipt. An operator-request upload also failed before side effects because PTY canonical input truncated large JSON; the corrected raw-input transport delivered the same request once. These failures and their original receipts are retained.

## Active immutable runtime and preservation

- Active content artifact: `2299ea0077b7d0db595d53407a498a3f9d39c6ae`.
- Source binding: `31935f89220a7a23b4768fdcefe5cc7aa85d1cf53b14f1e34138212801bb2c19`.
- Source ZIP SHA256: `36b06b9cea99620afa470a498483d2b5879f0c49b3c4f3e0c0cd7ea32f6bcb5f`.
- Source transition: `2b929b9184ca833be63ae76121cb6e476b51606d103c845236623dd74fa02349`; history 21/MAX32, every prior receipt retained.
- Backups: `/state/upgrades/operator-entry-20261026` and `/state/upgrades/operator-decimal-20261026`.
- Runtime compatibility receipt: `541f30dc0bc08b7436d5a38f90b1eb48ca2b16e31784d209727136634cf10c84`.

All original tables and the manifest matched consistent backups before activation except explicitly appended source/operator authorization metadata. The repair retained exact authority/state and transport counters. Actual hashes/import roots for all 73 release files passed. The same original mission, disk, image, permit/config, 27 environment variables, account, funded model pool, 300s model entry cadence and 30s host risk policy continue. Original historical UNKNOWN records remain. No state, history, budget, grant or attempt counter was reset.

## Validation

Final source validation: **683 core tests PASS**, **31 dashboard tests PASS**, Ruff, compile and four paper self-checks PASS. The 14 new operator tests cover actual broker-shaped receipts, source authority/tamper, fee-inclusive debit, one-POST behavior, timeout reconciliation, 60s cancellation, restart/time/stop exits, partial BUY inventory, dust proof, request consumption and Decimal persistence. Tests use synthetic HTTP; live execution evidence is the independent exchange sequence above.

Graph index/coverage calls returned `Transport closed`; material source and tests were inspected directly. This is a graph availability limitation, not a claim of full graph coverage. Existing dirty work was preserved, HEAD and the empty staged diff were retained, and no commit/push or visual UI change was made. The original single monitor publisher was restored after the controlled release restart.

## Final exit and account reconciliation

The original host submitted `fresh_live_20261023_9_exit_1793024226` at **17:47:06 Tehran**, 12 seconds after the scheduled deadline on the normal 30-second risk cadence, and less than 15 minutes after the actual BUY fill. The exchange returned **HTTP 201, success, FILLED**, with the original complete SELL fill:

- Submitted LIMIT 1,157 TMN; actual execution price **1,158 TMN**.
- Quantity **129.2 PUMP**, gross proceeds **149,613.6 TMN**.
- Actual fee **448.8408 TMN**, coefficient 0.003; net proceeds **149,164.7592 TMN**.
- Actual fill/capture body SHA256 `e6e28e7ba0d6bf28420e3e976e7145faff32aa827b7cfe466e9514043f169a7d`.

Subsequent actual private account GET snapshots at 17:47:21 and **17:50:54** both showed **no open orders**, **0.475 PUMP free / zero locked**, and **4,999,665 TMN free / zero locked**. The allocation ledger retains exactly 3,999,664.7592 TMN plus the original 1,000,000-TMN outside reserve, for 4,999,664.7592 TMN calculated from fills. The private balance API exposes the integer 4,999,665 instead: the difference is **0.2408 TMN**. The strict `account_matches` check returns **false**. Rounding is consistent with these observations, but the precise API rounding contract is not independently established. No cash adjustment, fill rewrite or reconciliation tolerance was applied.

The real BUY and SELL are verified. **Full conversion to TMN is not complete**: the remaining 0.475 PUMP has cost basis **547.619047619... TMN** and a fresh marked value around 550 TMN, below the 100,000-TMN order floor but above the existing 500-TMN quarantine limit. At 17:49:48 the engine remained RUNNING, heartbeat age 10s, no current error, and explicitly blocked new entry with **`UNSELLABLE_RESIDUAL`**. The remaining inventory and cost basis were preserved. No fake completed round trip or zero balance was recorded. The operator state remains ATTEMPTED because this dust has not satisfied the completion contract; all three authorities have already had their sole BUY POST.

### Newly observed fee/lot defect and open engineering work

An independent Decimal replay reconciles the real residual exactly:

| BUY fee scenario | Net PUMP | SELL quantity after 0.3% base reserve | PUMP left when SELL fee is TMN | Mark at entry price |
| --- | --- | --- | --- | --- |
| Preflight's fixed taker 0.3% | 129.61 | 129.2 | 0.41 | 471.5 TMN, passes 500 |
| Actual maker 0.25% | 129.675 | 129.2 | 0.475 | 546.25 TMN, exceeds 500 |

The four original fee-asset cases hold the fee **rate** fixed at taker. They therefore did not bound the real maker-BUY/taker-SELL combination. A larger assumed fee is conservative for cash debit but is not monotone for residual inventory after lot rounding. This is a genuine sizing limitation exposed by the first actual trade, not evidence that the original forecast cost was double-counted. The current host correctly retains and blocks on the excess residual instead of waiving the 500-TMN gate.

Before additional entries, lot planning needs fee-rate/rounding coverage, and account reconciliation needs an evidence-backed API precision contract. Existing dust also needs a separately reviewed settlement path; an additional purchase merely to exceed the sell floor is a new exposure and was not submitted. No residual cap was raised, no extra fourth authority was created, and no active-position source upgrade was attempted. These items remain **OPEN**, along with model forecast edge, judge-side qualification and full final cash settlement. This run establishes real accepted orders and actual BUY-to-SELL execution; it does not establish a profitable autonomous model strategy.

Continuity checks at 17:43:18 passed original journal/config/permit/historical hash, all 1,101 original reservations, all 431 original traces, exact scope identities with monotone usage, unchanged grants and cadence. Current totals were 1,105 reservations and 433 traces; the operator path issued no extra diagnostic model HTTP. Final active-file readback verified all 73 immutable hashes/import roots and all 21 source receipts. Public health remained alive; readiness was 503 during position protection, with the explicit position/entry guard reason. Monitor was AVAILABLE, authentication boundaries held, and original HTML/JS/CSS hashes were unchanged. Readiness is not claimed green while this unresolved inventory is retained.
