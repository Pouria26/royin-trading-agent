# Restricted credit-account technical canary

This is one technical round trip, not a profitable strategy or an unrestricted live release.
The user's existing small-pilot authorization is the scope. No main-account fallback,
credit activation, transfer, withdrawal, averaging or automatic size increase exists.

The read-only preparation was executed successfully on2026-10-22: dedicated active account,
cash-only balance, no open orders, fee0.0025/0.003, active public USDTTMN spot rules and
buy/sell minimum checks for100000 TMN. Public minNotional was50000 and minQty0.01.
These observations can change; execution repeats the preflight. Credit expiry is not returned
by the observed account schema. The explicit contest deadline and a fresh active-account check
bound this tiny technical test; they do not attest the exact future package expiry.

```powershell
.\.venv\Scripts\python.exe -X utf8 -m scripts.execute_credit_canary --prepare
.\.venv\Scripts\python.exe -X utf8 -m scripts.execute_credit_canary --execute
```

No flag prints help. Prepare sends bounded reads only. Execute requires a clean committed
revision, an explicit future CHALLENGE_END_AT and the existing dedicated credit credentials.
It allows exactly one BUY and one SELL,100000 TMN worst-case BUY debit, at most8 order HTTP
attempts and18 reads. Initial entry permission expires in600 seconds; owed-position exit,
GET and cancellation remain possible after entry expiry. No ambiguous request is refunded.
The runtime holds a per-account cross-process SQLite lock in the operator's home directory.
State lives at `~/.royin-credit-state/<account-sha256>/canary.sqlite3`, shared across clones
under that operator account. Never delete, copy-reset or edit this database to retry a canary.
Raw order observations are private alongside that state; preparation reports stay in ignored
data/private. Keys and account identifiers are not sent to the model or committed.

Only scoped known LIMIT intents can reach the transport. It validates payload identity,
host/path/headers, cash cap, order counts and durable counters before opening a socket.
General RUN_MODE=live configuration remains rejected. The older run_live_pilot --run remains
blocked; it is not the new technical lane. Candle strategy decisions do not use this canary.

Partial/UNKNOWN needs reconciliation using the same client ID. A changed revision/rules binding,
unexpected account order, incomplete cumulative fills or exhausted request budget stops the lane.
Do not rerun with a new DB or new ID. Inspect the private report and known exchange order before
any further action. Local counters protect this lane, not unrelated manual/API activity.

Dust after base-asset fees/quantity rounding is possible. A residual result is exit2 and is not
COMPLETE_ROUND_TRIP or proof of fully realized TMN profit. Cash delta includes any base asset
still held. The technical test incurs real fees; a limit can remain unfilled, and neither a stop
threshold nor the transport guarantees a price or a maximum realized loss during outages.

Financial offline oracle: with100000 TMN and250000 entry, buy0.39 USDT for97500; after0.003
base fee receive0.38883. Selling0.38 at249875 yields94952.5 less284.8575 quote fee. Cash is
97167.64250 and residual0.00883 USDT. This synthetic example proves accounting, not profitability.

Before general AI strategy execution: independently inspect actual order/fee/finality evidence,
account delta and residuals, exercise recovery, then connect the approved current strategy to its
own scoped risk policy. A tiny technical success does not validate alpha or model forecasts.

Verification before execution:324 core tests and9 dashboard tests passed; Ruff, compileall and
wheel build passed. Eight new checks include an end-to-end mocked runner with matching/mismatching
account balances. No exchange order had been sent at this source checkpoint.

## Actual attempt at e7d8bc5,2026-10-22

The authorized technical attempt used one POST, one cancellation request and six order GETs,
with the same durable client ID. The POST body observation was empty, while subsequent order
lookups returned not_found_error. The final order state is BUY_UNKNOWN, not rejected or filled.
The observed dedicated-account cash delta was0 TMN and residual USDT0; total balances matched
the allocated local ledger total. This is not proof of eventual order absence or successful execution.
The local reserve and eight-attempt counter remain intact; no second BUY or SELL was attempted.
General strategy execution and further pilot orders are NO_GO pending resolution.

The original capture preserved bodies but omitted HTTP status metadata, so the exact POST status
cannot be reconstructed. A follow-up regression now records each response status before body
decoding (including empty bodies) and retains ambiguous attempt counts. It does not retroactively
invent the earlier status or authorize another financial attempt.

Operator check requested: inspect credit-account open orders/trade history and whether the
existing API key has trading permission. Do not send the key, reset financial state or create a
new client ID to get around this unresolved attempt. Private reports remain outside Git.

The operator subsequently reported no new order/trade visible in the credit account. API-key
trading permission is still unconfirmed. The official key guide distinguishes default read access
from separately enabled trading access; knowing supported order types does not verify key permission.
Source: https://developers.wallex.ir/docs/create-api-key . Follow-up checks:325 core tests passed;
Ruff and compileall passed. The existing9 dashboard tests passed before this transport-only change.

After an operator-requested credential replacement, read-only preparation passed again with5M TMN
available and0 locked. A separate single-GET diagnostic audit of the same existing order returned404.
No POST/DELETE was added; the8-attempt execution counter and UNKNOWN reserve remained unchanged.
There have therefore been8 original execution requests plus1 separately recorded diagnostic order
GET. The diagnostic is not a cap reset, rejection receipt or approval for a second BUY.
Trading permission of the replacement key remains unconfirmed. The official spot introduction also
requires the credit-account key plus `sub-account-client-id`; supported Limit/Market order types
alone establish neither condition: https://developers.wallex.ir/docs/spot-intro .

## Replacement-key permission and history audit — 2026-10-22

This checkpoint supersedes the earlier pending-permission statements: the operator explicitly
confirmed that trading access is enabled for the replacement key. This is operator confirmation,
not an exchange-attested permission probe. The operator also confirmed that the replacement
key was created inside the credit account, rather than the main account. Missing trading
permission or main-account key origin is therefore not an established root cause.

A separately bounded read-only audit used3 GETs with the same dedicated account header:
- GET /v1/account/orders, page1/per_page100: HTTP200, success=true, orders=[], has_more_pages=false.
- GET /v1/account/openOrders: HTTP200, success=true, orders=[], count0.
- GET /v1/account/balances-detail: HTTP200; TMN total/available5000000, locked0; USDT0.

Official history contract: https://developers.wallex.ir/docs/spot-order-list . No date, side or
market filter narrowed the history query. Raw account payloads and audit scripts remain ignored.
This adds3 diagnostic GETs to the earlier1 diagnostic GET and8 execution requests. No POST,
DELETE, counter reset, reserve release or new client ID occurred. The original POST HTTP status
remains unknown; an empty history observation alone does not attest eventual-consistency finality.
Financial state remains NO_GO_ORDER_UNKNOWN until an explicit, reviewed recovery contract resolves
the existing intent. Do not misreport this audit as a completed real trade or a failed-key diagnosis.
