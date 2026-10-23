# BoxAPI funded continuation — 2026-10-23

The operator replaced the operational provider selection with BoxAPI only and supplied a distinct key with reported USD2.9709 remaining credit. The explicit spending ceiling is95%: **USD2.822355**, leaving USD0.148545 untouched. Provider balance and prices are operator/policy inputs; conservative local reservations are not an invoice or a guaranteed final balance.

## Durable funding contract

`BOXAPI_CREDIT_ID` selects a one-time credential-bound allocation appended to the **original** `data/llm-budget.sqlite3`. `ModelBudget.initialize_boxapi_credit` requires an existing valid BoxAPI ledger, explicit reported balance, finite cost/token limits and authorization reason. It adds `boxapi_credits` and a nullable `credit_id` column to reservations. Historical rows remain unchanged with NULL allocation; new requests append rows for the funded key. Duplicate key/allocation initialization is rejected, including after restart. No reservation is refunded.

Continuation verifies the key fingerprint, allocation, durable schema and positive policy-bounded ceilings before any model HTTP. Omission of the allocation for an already funded key is rejected. Deleting the ledger or losing the grant cannot recreate zero consumption. Old key consumption retains the historical USD2.40 total / USD0.80 Tehran-day limits. External-provider ledgers remain preserved and are not a substitute.

Policyv4 retains the original prices/input/output limits: gpt-6-luna,32768 input plus1024 output reserved per HTTP, **USD0.00435712** each. The funded allocation permits at most647 HTTP requests total,252 per Tehran day, USD1.10 per Tehran day and22million tokens; the exact allocation ceiling still wins if smaller. Two-request analysis costs at most USD0.00871424, allowing323 complete analyses with one spare request. Usage elsewhere with the same key is outside this local ledger.

## Runtime cadence and financial separation

The new service contract selects **900seconds** between entry analyses, claimed durably before I/O; polling and host protection remain30seconds. Restart cannot advance the next analysis. Around75hours to Monday's internal finalization requires about301 full analyses, reserving roughly USD2.623; remaining capacity covers bounded failures/additional role work. No request is made simply to consume95%.

New funded service envelopes take their finite decision ceiling and binding from the immutable service contract and funded allocation. Existing pilot scopes keep their stored limits; an allocation change cannot reuse their contract binding. Standard shadow/live defaults remain closed. The independent financial lane still requires its explicit permit, source/config bindings, account reconciliation, allowlist, cost/depth/sellability checks and historical quarantine.

The actual fresh-financial lane currently uses AI for entry selection and host-only position exits; the separate paper Position Reviewer exists but is not represented as active in that lane. Stops, deadline exits and reconciliation remain independent of model availability. One position, first actual completed round-trip debit<=150000TMN, subsequent volatility sizing with50%asset /80%total ceilings; no calibrated success probability is claimed.

## Acceptance evidence

Synthetic regressions cover exact funding ceiling, preservation of legacy spend, key/allocation mismatch, duplicate initialization, missing original ledger, no midnight total reset, concurrent reservation atomicity, funded scope restart, old pilot limits and15minute durable cadence. Real server compatibility, real model result and actual order/fill counts must be checked separately after release. Earlier APMix/River failures and the zero-trade paper results remain evidence; provider replacement does not turn them into success.
