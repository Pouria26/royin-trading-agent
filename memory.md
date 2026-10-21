# حافظه فنی رویین

آخرین تطبیق با کد و شواهد مخزن: ۲۰۲۶-۱۰-۲۲. فقط قرارداد جاری، دام فنی و محدودیت ماندگار اینجا بماند؛ تاریخچه جلسات/تعداد تست‌ها در TASKS.md، قوانین در docs/challenge-brief.md و قیمت‌ها در policy مربوط‌اند. اطلاعات شخصی، Secret، شناسه حساب و یادداشت superseded نگه ندارید.

## وضعیت و مرز اجرای واقعی

- به‌روزرسانی ۲۰۲۶-۱۰-۲۲: native-hour مستقل با ۶۲۳ bar/دو قطعه و یک ساعت gap، DIAGNOSTIC_ONLY است؛ نه پذیرش T02. source semantics/finality/volume هنوز مجهول‌اند. نام‌های جاری planها config/native-hour-source-plan.json و config/candidate-evaluation-plan.json؛ hash freeze قبلی حفظ شده است.
- یکپارچه‌سازی: شش تنظیم روی۷ پنجره۷۲ساعته با warmup۳۱bar ارزیابی تشخیصی شدند؛ هیچ نامزد تأیید نشد. سپتامبر۲۴–۲۷ outcome دیده شده و Holdout دست‌نخورده نیست؛ حد۳۰ معامله رسمی/آماری نیست. docs/candidate-evaluation.md مرجع نتیجه و محدودیت است.
- run_shadow اکنون فقط OBSERVE_ONLY و native hourly USDTTMN: یک snapshot بسته واقعی ثبت شد؛ CANDIDATE_SHADOW پیش از شبکه بسته، بدون مدل/ledger/سفارش. warmup prefix کوتاه‌تر صریح، gap داخلی/open/stale رد؛ COMPLETE مشاهده است نه T09. قفل فقط محلی، پوشه run غیرخالی رد، قفل پس از crash فقط با بررسی دستی مالک بازیابی شود.

- CLI فعلی check-config و ارزیابی تاریخیِ manifest-gated دارد؛ ledger/risk/PaperBroker/features/Agent موجودند. تعداد تست یا schema-valid بودن، اعتبار مالی/آمادگی live نیست. یافته‌های این مأموریت و شواهد قبلی در docs/historical-validation.md تفکیک شده‌اند؛ هیچ نامزد تاریخی به Shadow واقعی منتقل نشد.
- R/S: گزارش کاربر و probe قبلی برای حساب ۵٬۰۰۰٬۰۰۰ TMN و TMN maker/taker=0.0025/0.0030 موجود است؛ در این مأموریت probe خصوصی تکرار نشد. feeAsset/minimum/step/expiry تأیید حسابی ندارند؛ fee اعتبار صفر با معامله بدون fee متفاوت است.
- حالت اجرای زنده (live) همچنان مسدود است (`ENABLE_LIVE_TRADING=false`) و هیچ کلاینت ارسالی به بازار زنده وجود ندارد (Fail-Closed).
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
