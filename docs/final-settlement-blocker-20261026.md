# Exact-zero settlement record — 26 October 2026 (closed to further work)

## Closeout recorded during repository cleanup — 27 October 2026

The user ended this task and reported the competition finished. The 23:20 follow-up was canceled by deleting automation-2. No further trading, monitoring, deployment or account mutation was performed. This document preserves historical evidence; it is not a current account status or an instruction to resume execution.

Subsequent direct observations supersede the earlier0.475 PUMP snapshot below:

- 22:12:03Tehran: exchange-side LIMIT BUY5.2PUMP@1,145, value5,954TMN, open/unfilled; the user confirmed it was manually placed by the team. It was absent from the robot's owned-order journal.
- 22:15:18: actual manual BUY filled5.2PUMP@1,145, fee0.013PUMP (0.25%), net acquisition5.187PUMP.
- 22:17:01: actual manual SELL filled5.6PUMP@1,144, gross6,406.4TMN, fee19.2192TMN (0.30%), net6,387.1808TMN.
- 22:19:41: fresh original-account snapshot confirmed5,000,098TMN free, zero locked,0.062PUMP free, zero locked and zero open orders. Therefore the cash floor was observed, while exact-zero crypto settlement was not achieved in that observation.

The manual BUY bodySHA256 is `3b69c562a042e2ce3504a373252755afbb6e891771795320d7c0a073cb1584fb`; original-account trade-history bodySHA256 is `ebba233aefe77b9037c7a9e68e41df2f6c8ca2d647d77e58dfe4ffd86395a5fa`. The two new exchange fills are separate from the robot's unchanged original four orders/two fills/13financial transport attempts. No adoption, fabricated fill or balance/basis rewrite occurred. The last model-fee read still confirmed maker0.25%/taker0.30%. Durable account-read allowance reached1734 and was retained.

One important limit was corrected during investigation: the100,000TMN floor is an internal mission admission rule. Public spot metadata advertised50,000TMN, while the actual manual5,954TMN BUY was accepted. This discrepancy does not establish a general minimum exemption or exact fractional sell support. The earlier two hypothetical100k-floor cleanup examples are not an exhaustive impossibility proof. Public OTC metadata separately required90,000TMN for PUMPTMN; the public swap page did not establish support for exact credit-account dust conversion. The official credit-package FAQ says stopping a package deducts the received credit and fees and transfers the remainder to the main account; it must not be treated as proof that5M cash remains in the competition account. No package closure, OTC order or swap was submitted.

The ignored read-only final-balance diagnostic was tightened to distinguish exact crypto zero, no open orders/locked balances and a conservative cash lower bound of at least5M. Six offline counterexamples ensure that zero crypto with insufficient cash or an open order is not labeled complete. This diagnostic-only change did not modify the immutable deployed source.

Final exact-zero settlement, balance at the actual competition deadline and judge-side recognition remain **UNCONFIRMED**. No live refresh was performed during this27October Git cleanup.

## Historical investigation

## Requirement and actual observation

The user requires every cryptocurrency balance **exactly zero** and conversion to cash by **23:30 Asia/Tehran tonight**. The contest ends at midnight. The prior exception for retaining a small audited residual is not final settlement.

Fresh original-account reads at **21:40:49 Tehran** returned HTTP200 for `/sub-accounts`, `/v1/account/balances-detail` and `/v1/account/openOrders`. Original account identity and raw-body SHA256 were checked. Durable account-read counter advanced 1715 -> 1718; no financial table changed.

| Item | Observed value |
| --- | --- |
| TMN free / locked | 4,999,665 / 0 |
| PUMP free / locked | 0.475 / 0 |
| Other nonzero crypto | None in complete balance response |
| Open orders | 0 in complete original-account response |
| Recorded orders / fills | 4 / 2 |
| Financial transport attempts / BUY POST / SELL POST | 13 / 3 / 1 |
| Engine | RUNNING, OPERATOR_STOP_NEW_ENTRIES, no current error |
| Final settlement | NOT_FULLY_SETTLED |

This balance response has SHA256 `ab09d643889167098fb025727622d2e1ca12ebbd0c17f0f6f63a8f9c7d89154e`; the open-order response is `5381a2e05fc014867dc666e5a01f7b9f7de8f821b360c91700830854167b473a`. Full original read receipts stay on the persistent disk and in ignored private review artifacts. No account secret or account identifier is published here.

## Controls already applied

The immutable accounting repair `bde2d9770d99dacc011baff6d29652dc4dc2e051` is active with 22 retained source receipts, same original mission/account/permit/config/budget. The two exact human-approved policies were applied; no balance, fill, fee or basis was rewritten. Details and validation are in [the release report](operator-accounting-repair-20261026.md).

The durable STOP_NEW_ENTRIES flag was created at **21:24:46** and acknowledged by the actual engine. Its SHA256 is `9968c0e402b391efaa5f0f830eb20de5ab8a93e6f9d521c52b3508e0866c6501`. It must remain. Risk/reconciliation continue on the original worker. Original entry cutoff21:50 / permit end22:50 were not extended. There is no new operator authority or cleanup purchase.

## Why the ordinary SELL path cannot establish zero

The retained position is **0.475 PUMP**, approximately550TMN at the recorded mark. Its actual basis is **547.619047619... TMN**. Current PUMPTMN rules use quantity step0.1 and mission minimum-notional100,000TMN. The quantity cannot be submitted in full with that step, and its value is below the order floor. Selling part, recording a quarantine or zeroing a ledger row does not establish exchange-side zero. A further BUY can sometimes create a sellable exact quantity under a particular fee-asset/full-fill outcome; simply increasing gross volume does not establish that outcome or preserve final cash.

## User's conditional cleanup-purchase proposal — fresh analysis, no execution

The user subsequently proposed a cleanup BUY followed by a SELL, explicitly requiring final funds **at least5,000,000TMN**. This is conditional intent, not acceptance of a loss below that floor. No order, new authority, permit extension or STOP removal was performed.

Fresh original-account GETs at **21:53:27 Tehran** confirmed the same4,999,665TMN,0.475PUMP and no open orders; read allowance advanced1718->1721. Fresh account-fee GET1722 at **21:54:54** returned200 and confirms PUMPTMN maker0.25%/taker0.30%. Its bodySHA256 is `6ca271f534da6b0447193a7a8314795d4b6582bfe4d461f6388d98aa6048c144`. The first diagnostic formatter failed on Decimal serialization after the successful GET; the original captured body was verified/read back without another HTTP request. Actual financial attempts remain13/buys3/sells1.

Public PUMPTMN depth at **21:53:24** showed bid1,156/ask1,157, with top-level quantities sufficient for the following arithmetic examples. BodySHA256 `13acc0c90fdb7b04827ac801dd195b01429b4049ceeb78a64a9076f352e1e4a9`. These are conditional accounting examples under existing100k order floor/150k example ceiling, not issued orders or a promise that maker orders fill:

| Conditional full-fill example | Exact base after BUY under the stated base-fee assumption | Final cash from the displayed balance |
| --- | --- | --- |
|125PUMP at ask1,157, BUY fee0.3% in PUMP; sell125.1 at bid1,156 with0.3% TMN fee|125.1PUMP|4,999,221.7532TMN|
|110PUMP passive BUY at bid1,156, BUY fee0.25% in PUMP; passive SELL110.2 at ask1,157 with0.25% TMN fee|110.2PUMP|4,999,687.6465TMN|

Both examples can satisfy the0.1 quantity step in the stated fee branch, and both fail the user's5M final-cash condition. The .2408TMN display difference cannot reverse either result. Partial execution, mixed rates or another fee asset can create another residual. A higher exit price can change the calculation, but neither that price nor execution before the deadline is guaranteed. These two bounded examples do not prove that every conceivable market path is impossible. Original entry cutoff21:50 has already passed; financial permit end22:50 is unchanged. Conditional Decimal calculations and explicit quantity/cash oracles passed offline in the ignored review directory; production source was not modified.

## Official route investigated; unresolved effects and access

The current official [credit-account close guide](https://developers.wallex.ir/docs/trade-credit-close-sub-account), archived from its publicly served compiled documentation, exposes **DELETE `/v1/prop/user/packages`**, with `sub-account-client-id`. Its generated documentation says that it cancels the selected user package. Response fields include client_id, start_balance, final_balance, final_balance_without_transfers and currency. This is termination of the credit package, a broader action than an ordinary spot SELL. These fields do not prove fractional-dust liquidation, a zero crypto balance, fees or judge treatment.

The official read-only preview is **GET `/v1/prop/user/packages/active`**. A single bounded attempt with the current original trading key and account header returned **401**, message «ابتدا وارد شوید». Normal selected-account balance and open-order reads still return200, so that failure is not evidence that the trading key as a whole is invalid. No alternative credential, security bypass or package DELETE was attempted. The official public MCP catalog lists package-read/package-cancel and OTC tools; the inspected52-tool catalog supplies no dedicated dust-conversion tool. This is a bounded catalog observation, not proof that no native service exists.

The available browser has no authenticated Wallex account tab; attempted public page inspection also encountered browser transport timeouts. The user explicitly answered that they cannot see/access either small-asset conversion or package settlement in the panel. Native settlement is therefore blocked on an official access/mechanism clarification. Do not treat the generic credit-package close endpoint as a proven remedy or execute it blindly.

The official [Wallex home page](https://wallex.ir/) links «چت با پشتیبانی» and documents 24/7 support. An inquiry can also be directed to the competition organizer. No message has been sent to another party by the agent.

## Prepared inquiry for the user to send

> در حساب اعتبار مسابقه فقط ۰٫۴۷۵ واحد PUMP باقی مانده؛ سفارش باز نداریم و بقیهٔ دارایی نقد تومانی است. مقررات مسابقه می‌خواهد موجودی تمام رمزارزها تا ساعت۲۳:۳۰ امشب دقیقاً صفر باشد. این مانده زیر حداقل سفارش و خارج از گام حجم۰٫۱ است. در پنل دسترسی به تبدیل مانده نداریم و GET /v1/prop/user/packages/active با کلید حساب مسابقه۴۰۱ می‌دهد، ولی موجودی و سفارش‌های همان حساب۲۰۰ هستند. روش رسمی و مجاز تبدیل این مانده در همین حساب چیست؟ آیا بستن کل طرح لازم است، و در آن صورت اثرش بر کارمزد، تسویه و ثبت نتیجهٔ مسابقه چیست؟ لطفاً مسیر مورد تأیید و رسید قابل استناد را مشخص کنید.

This is a prepared draft, not a transmitted instruction or an authorization to close an account. Do not include passwords, OTPs or API keys in the inquiry.

## Verification after any human-controlled official settlement

Read the complete original-account balances and open orders again with fresh body hashes. Require every non-TMN total exactly0, no unknown/pending/open orders, and actual cash confirmation. If external settlement changes inventory, preserve all original fills/basis/quarantine receipts and reconcile the new authentic event separately; never fabricate a broker fill, delete a policy receipt or silently rewrite cost basis. Package closure may remove account access instead of returning zero, so a closed-account response alone is insufficient proof of final cash.

The bounded original-account verifier is `.local/review/operator-accounting-20261026/final-balance-check.json`, run through the reviewed raw-input remote helper. It performs three existing scoped account GETs, records read allowance and response hashes, checks unchanged six financial tables and order counters, and separately reports crypto zero, open/locked balances and the5M cash floor; the stricter reporting guard was added during the final read-only investigation. It does not mutate financial orders or close packages. If a new genuine settlement changes the order counters, review that event and its receipts before updating the verifier's expected baseline.

The **22:05** heartbeat performed fresh original-account verification at **22:06:58 Tehran**: GET1723–1725 all200, TMN4,999,665 and PUMP0.475 unchanged, no open orders,13attempts/3BUY/1SELL, financial tables unchanged, same source/PID and OPERATOR_STOP_NEW_ENTRIES, no current error. Balance bodySHA256 `2dfa56a5d6dfef6cfbb984dc4f75f3a30b21998a41b9234a700c31a95162abac`. No new actionable change was found beyond the previously reported settlement blocker, so no repeated user notification was issued.

Historical plan: heartbeat **automation-2** was updated to one final read-only check at **23:20 Tehran**, then deleted when the user stopped the task. That check was canceled. Normal financial-worker expiry22:50 must not be bypassed or treated as unexpected failure; account evidence and actual settlement still require independent verification. The schedule has been deleted; ending monitoring does not prove settlement. This is verification only, not an execution guarantee. Full settlement and contest-side acceptance remain OPEN until actual evidence arrives.
