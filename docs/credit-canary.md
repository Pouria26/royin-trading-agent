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
