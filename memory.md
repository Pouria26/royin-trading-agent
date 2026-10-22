# حافظه فنی رویین

آخرین تطبیق با کد و شواهد مخزن: ۲۰۲۶-۱۰-۲۲. فقط قرارداد جاری، دام فنی و محدودیت ماندگار اینجا بماند؛ تاریخچه جلسات/تعداد تست‌ها در TASKS.md، قوانین در docs/challenge-brief.md و قیمت‌ها در policy مربوط‌اند. اطلاعات شخصی، Secret، شناسه حساب و یادداشت superseded نگه ندارید.

## وضعیت و مرز اجرای واقعی

- به‌روزرسانی ۲۰۲۶-۱۰-۲۲: native-hour مستقل با ۶۲۳ bar/دو قطعه و یک ساعت gap، DIAGNOSTIC_ONLY است؛ نه پذیرش T02. source semantics/finality/volume هنوز مجهول‌اند. نام‌های جاری planها config/native-hour-source-plan.json و config/candidate-evaluation-plan.json؛ hash freeze قبلی حفظ شده است.
- یکپارچه‌سازی: شش تنظیم روی۷ پنجره۷۲ساعته با warmup۳۱bar ارزیابی تشخیصی شدند؛ هیچ نامزد تأیید نشد. سپتامبر۲۴–۲۷ outcome دیده شده و Holdout دست‌نخورده نیست؛ حد۳۰ معامله رسمی/آماری نیست. docs/candidate-evaluation.md مرجع نتیجه و محدودیت است.
- run_shadow اکنون فقط OBSERVE_ONLY و native hourly USDTTMN: یک snapshot بسته واقعی ثبت شد؛ CANDIDATE_SHADOW پیش از شبکه بسته، بدون مدل/ledger/سفارش. warmup prefix کوتاه‌تر صریح، gap داخلی/open/stale رد؛ COMPLETE مشاهده است نه T09. قفل فقط محلی، پوشه run غیرخالی رد، قفل پس از crash فقط با بررسی دستی مالک بازیابی شود.

- CLI فعلی check-config و ارزیابی تاریخیِ manifest-gated دارد؛ ledger/risk/PaperBroker/features/Agent موجودند. تعداد تست یا schema-valid بودن، اعتبار مالی/آمادگی live نیست. یافته‌های این مأموریت و شواهد قبلی در docs/historical-validation.md تفکیک شده‌اند؛ هیچ نامزد تاریخی به Shadow واقعی منتقل نشد.
- R/S: گزارش کاربر و probe قبلی برای حساب ۵٬۰۰۰٬۰۰۰ TMN و TMN maker/taker=0.0025/0.0030 موجود است؛ در این مأموریت probe خصوصی تکرار نشد. feeAsset/minimum/step/expiry تأیید حسابی ندارند؛ fee اعتبار صفر با معامله بدون fee متفاوت است.
- حالت اجرای زنده (live) همچنان مسدود است (`ENABLE_LIVE_TRADING=false`) و هیچ کلاینت ارسالی به بازار زنده وجود ندارد (Fail-Closed).
- سقف رانر پایلوت زنده (`scripts/run_live_pilot.py`) به ۳۰۰٬۰۰۰ تومان افزایش یافت تا بر محدودیت حداقل سفارش صرافی (۱.۰ تتر و ۱۰۰٬۰۰۰ تومان) فائق آید؛ مقدار خرید ۱.۱۲ تتر و فروش‌پذیری پس از کارمزد ۱.۱۱ تتر با وضعیت PASS_SELLABLE بدون تولید خرده دارایی (Dust) تضمین شد.
- داشبورد پایش محلی (`dashboard/`) به موجودی حساب اعتباری ۵ میلیون تومانی و کشوی درس‌های ثبت‌شده در حافظه خود-اصلاح‌گر (Reflexion Memory) متصل شد؛ کلیه رندرها مبتنی بر textContent و بدون innerHTML است.
- سناریو و شات‌لیست جامع ویدئوی ۵ دقیقه‌ای ارائه داوران در `docs/video-presentation-plan.md` تدوین و آماده ضبط شد (پوشش معیارهای R20، R21 و J08).
- فقط اسپات بدون لوریج/borrow/short؛ SELL از موجودی قابل فروش است. فعال‌سازی اعتبار، برداشت/انتقال، حساب اصلی و سفارش واقعی در دامنه فعلی مجاز نیستند. پایان ثبت‌شده ۲۰۲۶-۱۰-۲۳ ساعت ۲۳:۵۰ ایران؛ سرمایه مبنا ۵٬۰۰۰٬۰۰۰ TMN است. کیفیت ویدئو/دلیل معاملات/نسخه سودساز الزامات تحویل‌اند؛ سود تنها کافی نیست.
- تعداد یا شکل درست پاسخ‌های مدل، HTTP 200 و موفقیت parser اثبات سودآوری، fill یا آمادگی live نیستند. fake، بک‌تست، سایه و حساب واقعی جدا گزارش شوند. Blueprint قدیمی منبع حقیقت نیست.

## مدل و بودجه

- runtime فقط BoxAPI با Chat Completions در `https://ai.boxapi.ir/ai/v1` و پیش‌فرض `gpt-6-luna` است. کلید تنظیم `BOXAPI_API_KEY`؛ fallback به Google/OpenAI مستقیم نداریم. کلیدها فقط در .env محلی/تنظیمات میزبان؛ چاپ، ارسال دوباره یا ثبت در Git ممنوع.
- تنظیم Pydantic AI برابر `openai_reasoning_effort="none"` است و به `reasoning_effort: "none"` در HTTP تبدیل می‌شود؛ تست transport روی هر دو turn آن را کنترل می‌کند. برای Luna در Chat Completions با function calling، مستند رسمی فعلی none را لازم می‌داند. رفتار داخلی BoxAPI مستقل از بررسی بدنه درخواست است.
- policy معتبر در config/llm-budget-policy.json و توضیح در docs/boxapi-budget.md است: اعتبار گزارش‌شده ۳ دلار، سقف کل ۲٫۴ و روزانه ۰٫۸ دلار تهران، ۰٫۶ ذخیره، حداکثر ۶۰۰/۲۰۰ درخواست کل/روز و token budget مستقل config. قیمت واسطه با OpenAI مستقیم یکی نیست؛ اعداد قیمت را اینجا تکثیر نکنید و invoice/balance را تأییدشده ندانید.
- ModelBudget با SQLite integer nano-USD، BEGIN IMMEDIATE و رزرو durable پیش از هر HTTP کار می‌کند؛ خطا/timeout/مرگ فرایند refund ندارد. `data/llm-budget.sqlite3` پاک/reset نشود. همه مصرف‌کننده‌های هم‌زمان همان کلید باید همین دفتر مشترک را مصرف کنند؛ clone/worktree یا cwd متفاوت با دفتر مستقل می‌تواند سقف کلید را دور بزند. مصرف اپ دیگر/تغییر تعرفه زیر کنترل این guard نیست.
- محدودیت فعلی probe: دو turn، یک ابزار، صفر retry/repair، سقف ۵۱۲ output و deadline سی ثانیه. نمونه JSON حداکثر ۷۱۶۸ byte با حاشیه رزرو input؛ بودجه کل سرویس جدا از UsageLimits هر run است. هیچ caller جدیدی بدون hook بودجه اضافه نشود.
- شواهد docs/evidence/boxapi-read-only-2026-10-21.json: چهار سناریوی synthetic با provider واقعی PASS؛ REVIEW فقط آمادگی تحلیل بیشتر است، نه پیشنهاد خرید. این شاهد کیفیت معامله یا ablation سود نیست. شواهد قدیمی Google تاریخچه‌اند، تنظیم فعال نیستند.
- MCP عمومی `https://api.wallex.ir/mcp` اکنون طبق docs/wallex-mcp.md برای توسعه Codex با پنج ابزار عمومی allowlist شده است؛ initialize/tools-list و یک call بازار در شاهد ثبت‌اند. این اتصال به runtime BoxAPI اضافه نشده، کلید خصوصی ندارد و مجوز ابزار حساب/سفارش/مارجین نیست. ظاهرشدن ابزار در نشست تازه و صحت همه داده‌ها هنوز تأیید نشده‌اند؛ REST اجرای قطعی تغییر نکرده است.

## حساب و دسترسی بازار

- گزارش تازه کاربر در ۲۰۲۶-۱۰-۲۱: حساب هکاتون فعال و ۵٬۰۰۰٬۰۰۰ TMN آزاد، فریز صفر؛ هزینه اعتبار سه‌روزه/تا امروز صفر. feeهای گزارش‌شده برای همین حساب: TMN maker/taker=`0.0025`/`0.0030` و USDT=`0.0010`/`0.0013`؛ نسبت اعشاری‌اند، نه درصد. این گزارش جای تطبیق API را نمی‌گیرد؛ جزئیات در docs/challenge-brief.md. مشاهده تاریخی sub-accounts خالی، وضعیت فعلی حساب نیست. live آینده باید با کمترین مبلغ مجازِ قابل خروج زیر سقف صریح کاربر شروع شود؛ چند برد کوتاه/اعتبار مدل مجوز افزایش حجم نیست.

- متن تکمیلی اعتبار در ۲۰۲۶-۱۰-۲۱، منبع کاربر: کارمزد معاملات از سطح یک؛ کارمزد اعتبار روزشمار جدا؛ هشدار/لیکویید حساب و فروش آنی در انقضا/توقف طرح. نرخ ویژه هکاتون، آستانه‌ها و زمان انقضای واقعی U هستند؛ صفر یا عدد مثال عمومی فرض نشوند. جزئیات/تعارض انتقال در docs/challenge-brief.md ثبت است. اسپات بودن مانع لیکویید قراردادی اعتبار نیست؛ هیچ انتقال/فعال‌سازی مجاز نشده است. به فروش خودکار صرافی برای پایان داوری اتکا نشود؛ بازیابی اصل اعتبار از PnL استراتژی جداست.

- موجودی اعتباری از `/v1/account/balances-detail` با result[asset].total/available/freeze خوانده می‌شود؛ `/v1/account/balances` حساب اصلی است. کلید حساب اعتباری و هدر sub-account-client-id لازم‌اند؛ fallback به اصلی ممنوع.
- آخرین مشاهده ثبت‌شده در docs/wallex-read-only-setup.md: GET /sub-accounts موفق با result=[]؛ شناسه/حساب مسابقه تأیید نشده است. SUB_ACCOUNT_CLIENT_ID از clientId حساب فعال prop گرفته می‌شود، نه از رشته API key؛ خالی/چندمبهم یعنی BLOCKED، بدون فعال‌سازی اعتبار. این مشاهده را وضعیت زنده همیشگی حساب فرض نکنید.
- snapshot محدودیت `config/wallex-credit-market-policy.json` جفت‌محور است: ۳۴۵ جفت، هر دو quote برای PAXG ممنوع؛ YFI/USDT آمده ولی YFI/TMN نیامده. پیشوندهای 1BBABYDOGE و 2Z حفظ شوند؛ غیبت در denylist مجوز نیست. universe از catalog و دسترسی تازه حساب منهای اجتماع محدودیت‌ها ساخته می‌شود؛ WALLEX_ALLOWED_MARKETS فقط زیرمجموعه عملیاتی است و override ندارد.
- fee/min-notional، معنای precision به‌عنوان tick/step، وضعیت فعال بازار و تعلق حساب به مسابقه هنوز تأیید خصوصی نشده‌اند؛ fixture schema/synthetic جای آن نیست. نبود بات داخلی والکس را منع موتور خارجی API تعبیر نکنید.
- مسیر مستند فعلی لغو `DELETE /v1/account/orders/{client_id}` است؛ پاسخ نوشتن نامعلوم باید reconcile شود، نه تکرار با ID تازه. این قرارداد هنوز روی سفارش واقعی آزموده نشده. WebSocket v2 recovery بیشتر کانال‌ها را ندارد؛ reconnect بدون refresh داده کافی نیست.

## داده و ارزیابی

- decoder مالی در royin.market_data اعداد را دقیق با Decimal می‌خواند؛ float/bool/NaN/Infinity، JSON تکراری و exponent خارج حد رد می‌شوند. parse_history فقط کندل بسته [start,end) تا cutoff و cadence/پوشش دقیق را می‌پذیرد؛ aggregate_closed بن ناقص را flag و از ورودی مدل حذف می‌کند. prefix/future-invariance باید تا feature و decision هم گسترش یابد.
- درخواست resolution=15 در نمونه‌های عمومی داده یک‌دقیقه‌ای داد؛ برای بازه بلند resolution=1 هم پاسخ مرزی ناقص مشاهده شد. collector T02 روزانه با hash/query و سقف GET ساخته شده؛ تبدیل بی‌صدا، forward-fill یا ضعیف‌کردن oracle برای سبز شدن ممنوع.
- گزارش research/t02-data-contract.json کلی DEGRADED است: aggregation دقیقه‌ای روز اول اکتبر با hourly BTC در ۷ و ETH در ۱۰ ساعت اختلاف OHLC داشت؛ volume برابر بود، علت روشن نیست. حذف کندل صفرحجم اختلاف را کامل حل نکرد و راه‌حل پذیرفته‌شده نیست. هفته دوم gap/نقص نیز دارد.
- فقط USDTTMN هفته ۱–۸ اکتبر ۶۷۲ bar پانزده‌دقیقه‌ای و reference ساعتی روز اول را گذراند؛ این بررسی کل هفته را از نظر reference، معنای volume یا کیفیت استراتژی تأیید نمی‌کند. برچسب زمان open و حجم base فرض‌های پژوهشی ثبت‌شده‌اند؛ برای sizing واقعی باید تأیید شوند.
- آینده فقط oracle نتیجه است، نه feature/prompt. split زمانی و holdout، fee/slippage/no-fill/خروج انتهای بازه و ablation هم‌شرایط لازم‌اند. confidence مدل احتمال برد نیست و ورودی Kelly نمی‌شود؛ برای هر نمره مدل حجم مثبت تحمیل نکنید. stop/پایان/گیت ریسک نباید منتظر LLM بمانند.

## نگه‌داری و همکاری

- پس از `uv pip sync ... requirements.lock`، package محلی را دوباره با `--no-deps --editable .` نصب کنید؛ sync آن را حذف می‌کند. dotenv strict است: duplicate/unknown/malformed رد، interpolation خاموش، متغیر فرایند مقدم؛ timestamp باید ISO با offset باشد و به UTC تبدیل می‌شود. خطاها/repr نباید Secret/شناسه را افشا کنند.
- مخزن private؛ پرامپت‌های شخصی از جمله MASTER_PROMPT.md و فایل‌های .local/parallel محلی و خارج Git بمانند. گام‌ها کوچک با پذیرش/تست/گزارش، commit در پایان فاز منسجم؛ بازنویسی تاریخچه فقط با درخواست صریح. نسخه هر اجرای سودساز و config/prompt/data/model hash حفظ شود.
- در checkout مشترک فقط فایل‌های متعلق به مأموریت خود را ویرایش کنید؛ عملیات Git، config/lock و TASKS/memory مشترک باید یک مالک یکپارچه‌ساز داشته باشند. worker معاملاتی واقعی هم فقط یکی است؛ دو Coding Agent به معنی دو حساب/دو worker یا دو بودجه مستقل نیست.

## MCP والکس — ۲۰۲۶-۱۰-۲۱

- **User/S:** endpoint https://api.wallex.ir/mcp؛ initialize/tools/list واقعی بدون احراز موفق، ۵۲ ابزار شامل عملیات مالی؛ get_markets عمومی موفق. شاهد: docs/evidence/wallex-mcp-2026-10-21.json.
- **D:** اتصال محلی Codex با پنج ابزار عمومی allowlist و بدون Secret ثبت و CLI get تأیید شد؛ ابزارهای حساب/سفارش/مارجین/انتقال/اعتبار مجاز نیستند. بارگذاری نشست جدید U است؛ یادداشت قدیمی مجهول بودن URL superseded شد.
- **D/U:** Agent رویین متصل نشده؛ بهبود دقت/سود از MCP اثبات نشده و REST قطعی اجرا حفظ می‌شود. docs/wallex-mcp.md دامنه و محدودیت را ثبت می‌کند؛ T03 هنوز کامل نیست.

## اعتبار تاریخی — ۲۰۲۶-۱۰-۲۱، اصلاح و supersession

- D/S: حد limit به‌عنوان قیمت fill محافظه‌کارانه، بدون بهبود قیمت از slippage؛ OHLC تنها اگر candle.open_time >= created_at قابل match است. latency +10s عمداً شروع کندل مجاور را از دست می‌دهد؛ timestamp عقب نمی‌رود. stop در low منهای friction، پیش از خروج limit در intrabar مبهم فرض می‌شود؛ تضمین fill واقعی نیست.
- D/S: فقط config/evaluation-datasets.json با hash و metadata پذیرش؛ REJECTED/duplicate از نتایج اصلی حذف. هفته اکتبر۱–۸ فقط development است. min/tick/step و feeAsset شبیه‌سازی synthetic، taker .003 سناریوی گزارش حساب است.
- D/S: trade یک episode از inventory صفر تا صفر است؛ partial exits یک trade نیستند. PF/win rate برای N=0 یا بدون ضرر null/status دارند؛ finalization fee در close-only MTM DD دیده می‌شود، نه intrabar DD. SELL fee پایه موجودی و basis را مصرف می‌کند؛ fill/status مالی در تراکنش و بازیابی با client_id پایدار است.
- D/S: Audit schema_version/run/sequence/decision/snapshot/order/fill/position ID، fsync و payload allowlist دارد؛ redaction best-effort است، نه ماسک صددرصد. failure نوشتن audit propagate می‌شود. injected network client/production agent ممنوع؛ فقط MockTransport بدون mount و TestModel/FunctionModel برای تزریق آزمون. production ModelBudget واقعی و همان config لازم دارد.
- D/S: protocol c69b427581ebd640122cc7d327f04d356671270e01e8f156e42ba03b53d3eb83 پیش از داده تازه freeze؛ ۲۵ GET از سقف۲۷، فقط سپتامبر۱۷/۱۸ پذیرفته، هیچ پنجره۷۲ساعته کامل نیست: BLOCKED_DATA. شش configuration برنامه‌ریزی‌شده جست‌وجو نشدند، holdout برای بازده باز نشد و مدل پولی جدید صفر بود.
- U: ارزش افزوده AI و منحنی AI هم‌حالت هنوز اثبات نشده؛ recorded replay باید prompt/model/config/data و cash/position snapshot خودش را دقیق تطبیق دهد. آمار ۸ smoke تجمیعی بدون دو manifest معتبر نیست؛ رزرو دفتر actual usage/invoice نیست. shadow_cycle چهار کندل synthetic است و T09 را verified نمی‌کند.
- بعدی: علت اختلاف source minute/native را با مرجع رسمی تعیین کن؛ oracle را ضعیف نکن و با داده development قدیمی holdout نساز. منبع/معنای timestamps حل‌نشده، نمونه کم، queue/volume فرضی و مشخصات سفارش تأییدنشده، گیت Shadow/Live را بسته نگه می‌دارند.


## Independent execution review - 2026-10-22

Reviewed defd88b before publication. The twelve-configuration diagnostic and twelve real-model snapshots are retained as historical evidence, not strategy approval. See docs/execution-readiness-review.md and research/execution-review-evidence.json.

- T03: 12 snapshot decisions / 24 reserved HTTP; 9 agreements with baseline. Audit usage: 12123 input / 1237 output tokens; reserved USD 0.029675520 is not invoice. Hypothetical inventory states are not an AI equity curve.
- T05/T10: offline-only WallexLiveBroker contract harness; real transport blocked even with constructor overrides. UNKNOWN/terminal/partial observations retain reserves until fill/fee accounting exists. Production reconciliation, atomic intent/state and crash/race tests remain incomplete.
- T07/T08: 12 configurations / 7 diagnostic windows, INSUFFICIENT_EVIDENCE; no candidate approved. Plan freeze timestamp is later than manifest; pre-registration is unverified. strategy-experiment-plan.json is a byte-preserving rename; the six-configuration plan remains separate.
- T09: unsafe candidate branch removed; tested OBSERVE_ONLY retained. Candidate Shadow remains blocked before I/O.
- AI diagnostic CLI requires --run, validates dataset before model setup and limits each invocation before HTTP to 24 requests / USD 0.04 reserved; persistent global limits remain. No new paid model call, private probe or real order during review.
- Next: complete offline fill/fee reconciliation first; then a genuinely prospective AI/no-AI experiment and current Shadow. No promise of stable profits and no live activation by environment flags alone.


## Offline execution accounting — 2026-10-22 phase 1

Intent/reserve/SUBMITTING and full cumulative fixture settlement are now atomic;
partial cancel idempotence, conflicting timestamp, terminal-fill and LIMIT checks
are fixed in shared Ledger. Mock-only transport and production block remain.
See docs/offline-execution-accounting.md for source hashes, exact monetary oracles,
local operation-lock scope and unresolved real fill identity/finality. Source R/S/D/U
remain separate; fixture multiset IDs are explicitly offline-only. No paid call or
private account/order HTTP. Next: prospective AI ledger-state replay infrastructure;
no approved candidate or new holdout is established.

Phase 1 checks: 203/203 unittest PASS (9.012s); Ruff PASS; compileall exit0; git diff --check clean. No skip or BLOCKED counted as a pass. Revision: phase-1 commit containing this entry (exact hash in ignored final report).


## Portfolio AI infrastructure — 2026-10-22 phase 2

Phase 1 revision8279105 passed203 tests. Phase2 uses existing simulation and fresh
per-arm ledgers; emits full equity/decision/order/fill/episode and fee/slippage traces.
Exact fake SDK -> own-state recording -> fake recorded replay and cost stress pass;
real recorded replay, economic AI value and OOS remain BLOCKED_DATA. Protocol V4
freeze and hashes/retained failed attempts are in docs/portfolio-ai-evaluation.md.
No paid request, private probe, budget reset or live action. Existing seen windows
are not fresh holdout. Full fresh72h splits cannot finish within the current deadline.
Next: preserve closed Candidate Shadow and verify observation/recovery safeguards;
prepare honest five-minute demo evidence. Phase2 revision is the commit containing
this entry; exact SHA and manifest paths are recorded in the ignored final report.

Phase2 final checks: 209/209 unittest PASS (21.250s); six portfolio tests PASS; Ruff PASS; compileall exit0; diff check clean. Default portfolio CLI BLOCKED_DATA exit2 is not a pass. Real/recorded-real benefit remains unverified.


## Closed candidate and recovery evidence — 2026-10-22 phase 3

Phase2 revision4b9fab0 passed209 tests. No accepted candidate exists: Candidate
Shadow remains denied before I/O. Required future approval bindings and the fact
that no accepting validator exists are explicit in docs/shadow-execution-contract.md.
Two additional tests cover universal-deny artifact tampering and durable PaperBroker
restart/disconnect/host stop/finalization without model or HTTP. They do not verify
a live current strategy worker. Human video shot list is prepared under ignored
.local/parallel/video-evidence-plan.md; no video or delivery claim. Current public
observation manifests and final revision/checks are in the ignored final report.

Phase3 final checks: 211/211 unittest PASS (17.449s), Ruff PASS, compileall exit0,
wheel built, check-config example/local VALID_CONFIG_ONLY with network/trading false,
CLI/audit/model help exit0, diff check clean. Paid --run/--eval, private account probe,
and previously exhausted validation collectors were intentionally not executed.
Candidate execution/accepting approval validator/current strategy Shadow remain BLOCKED.
One-cycle public observation and isolated public quality-audit results are recorded
in .local/parallel/next-validation-and-execution-report.md after this commit; neither
can approve a candidate or prove multi-hour stability. No push, deployment or video upload.


## یکپارچه‌سازی ماژول‌های اجرایی، ارزیابی و مانیتورینگ — ۲۰۲۶-۱۰-۲۲

ماژول‌های حسابداری اتمیک و پایلوت، بازپخش علّی سبد دارایی و داشبورد مانیتورینگ به مخزن اضافه شدند:
- **تحلیل کارمزد و اصطکاک (Fee Friction):** طبق probe واقعی حساب، کارمزد maker=0.0025 و taker=0.0030 است؛ هر دور معامله تیکر 0.60% اصطکاک قطعی ایجاد می‌کند. استراتژی اسکالپ یا پرتکرار بازده منفی می‌دهد؛ استراتژی باید بر پایلوت سویینگ/مومنتوم با نسبت ریسک/ریوارد بالا و افق زمانی چندساعته متمرکز باشد.
- **مانع حداقل سفارش (Minimum Order Gate):** سقف ۲۰۰ هزار تومانی در قیمت فعلی تتر (~۲۶۶٬۷۲۱ تومان) معادل ۰.۷۴ تتر بوده و زیر حداقل سفارش ۱.۰ تتر والکس است (BLOCKED_MINIMUM). اجرای فنی پایلوت نیازمند افزایش کنترل‌شده سقف به حداقل ۲۶۸٬۰۰۰ تا ۳۰۰٬۰۰۰ تومان است.
- **حسابداری و بروکر:** رویدادهای Audit در زمان تراکنش پایگاه‌داده Staged می‌شوند تا Rollback نشت لاگ ایجاد نکند. قید زمانی fill.timestamp >= intent.created_at تضمین شد.
- **داشبورد:** اتاق پایش محلی RTL در پورت ۸۷۶۵ برای داوری و ویدئوی ۵ دقیقه‌ای (R20/R21) بدون دسترسی شبکه بیرونی یا ایجاد سفارش راه‌اندازی شد.
- بررسی‌ها: ۲۴۰ تست کامل (۲۳۲ واحد + ۸ داشبورد) PASS؛ Ruff و compileall کاملاً پاک؛ گیت اجرای زنده همچنان مسدود تا اتمام بازبینی و تأیید سقف جدید.



## Separate-clone release boundary - 2026-10-22


Draft rule replay is not AI/current Shadow: its CLI is blocked before I/O until task A repairs it. Old zero-dust/minimum and live-learning claims are superseded by this limitation. Two clone-local SQLite budget files do not share a cap: paid/private runtime remains single-host; offline collaborator tests need no real credentials. Raw prompts/handoffs remain ignored and are transferred separately.

## Current-market corrections - 2026-10-22

Source: independent review and bounded current Wallex/BoxAPI observations; details in docs/current-market-readiness.md.
Historical-prefix liquidation used the final full-dataset close; superseded by last-processed candle plus regression.
Failed book reads must retain old source age; official depth uses result.bid. Mark positions at observed bid.
Public /v1/markets USDTTMN minQty0.01/minNotional50000 supersedes the earlier assumed1USDT floor for that snapshot.
Active dedicated credit account independently reported5M TMN, no open orders and maker0.0025/taker0.003; not a release approval.
TMN market breadth needs USDT/TMN adjustment to avoid mistaking FX movement for broad crypto strength.
Real role output exceeded512 tokens and tool-return packets exceeded the8192 input byte bound: policyv2 reserves12288/1024;
prices and global/daily caps unchanged. Scope counters, original funded deadline and chosen rules/horizon persist on restart.
316 core tests passed; real current decisions returned WAIT. These observations establish wiring, not alpha or production safety.

2026-10-22: A separate100k-TMN technical canary lane is scoped by account worker lock, clean revision,
one BUY/SELL, eight durable order attempts and600-second initial-entry expiry. Shared financial state
lives under the operator home; cloning/restarting must not create a fresh allowance. General live stays
blocked. Read-only preparation passed. Fractional UTC-offset fill times are now accepted; whole-second
fixture identities stay compatible. Complete cumulative multisets are required because the official
order contract exposes no documented server fill ID. A dust result remains exit2, not fully realized profit.

2026-10-22 actual technical attempt, revisione7d8bc5: one BUY POST, one cancel request, six GETs;
empty POST body, repeated not_found_error, terminal local status BUY_UNKNOWN. Observed account cash
delta0/USDT0 matched local total; do not infer rejection or eventual absence. Local reserve and eight
attempts remain intact. Original capture lacked HTTP status; follow-up capture now preserves status
before reading/decoding the body. Never fabricate the old status or reset/reissue to bypass the cap.

Operator reported no new visible order/trade. Official create-api-key guidance distinguishes default
read permission from separately enabled trading permission; Limit/Market/Easy Spot descriptions
do not establish the actual key's permission. Permission remains unconfirmed, not an inferred root cause.
