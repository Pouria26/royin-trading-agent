# برنامه اجرایی و دفتر وضعیت

وضعیت‌ها: TODO / IN_PROGRESS / BLOCKED / VERIFIED / FAILED. VERIFIED فقط با شاهد همان نسخه. وابستگی خارجی مسدود به معنی توقف کار مستقل نیست. مالک اصلی همه تسک‌های این مخزن Coding Agent پوریا است؛ کار انسانی لازم در هر ردیف روشن است.

**T02: قراردادها و ابزار عمومی ساخته شد؛ کیفیت کامل داده و تأیید خصوصی BLOCKED است. P1 هنوز مسیر عمودی کامل ندارد.** پایان معتبر بنا به تأیید پوریا: جمعه ۲۰۲۶-۱۰-۲۳، ۲۳:۵۰ Asia/Tehran. امروز ۲۱ اکتبر آماده‌سازی/آزمون؛ live از فردا به درخواست پوریا، مشروط به گیت‌های فنی. مهلت دقیق ارسال ویدئو باید زودتر نهایی شود. زمان‌ها را از ساعت واقعی بخوانید و reserve تحویل را قربانی فیچر نکنید.

## ترتیب و پذیرش

| ID / فاز / اولویت | هدف و محدوده | وابستگی | معیار پذیرش و تست لازم | وضعیت / شاهد |
|---|---|---|---|---|
| T00 / P0 / P0 | قرارداد چالش، ماتریس امتیاز، نقد Blueprint و طرح شروع | بریف پوریا و منابع | همه R01–R22 و J01–J09 پوشش؛ ابهام‌ها U ثبت؛ مستندات و Master Prompt متقابلاً سازگار؛ secret ignore بررسی | VERIFIED؛ docs/preparation-checks.md، آزمون ۱۲/۱۲ در محیط فعلی و پاک؛ آمادگی موتور ادعا نشده |
| T01 / P1 / P0 | کمترین package/CLI و config؛ بدون زیرساخت اضافی | T00 | lock نصب پاک؛ config ناقص/ناشناخته رد؛ shadow پیش‌فرض؛ تست mode و ممنوعیت live بدون حساب/allowlist/پایان/سیاست؛ دستور واقعی تست/اجرا به AGENTS افزوده شود | VERIFIED؛ ۲۸/۲۸ در محیط فعلی و پاک از lock، wheel نصب و آزموده؛ CLI فقط check-config، همه liveها بسته؛ گزارش T01 پایین |
| T02 / P1 / P0 | قرارداد market/account؛ ذخیره داده و profile زمانی | T01؛ بخش عمومی مستقل از کلید | parser قرارداد واقعی، price/qty/fee و واحد روشن، ترتیب/گپ/بازه/کندل بسته؛ fixture sanitized؛ داده عمومی مجوز بازار نیست | BLOCKED برای پذیرش کامل؛ کد و fixture قرارداد عمومی/خصوصی آزموده؛ اجرای واقعی DEGRADED، خصوصی/fee/min-order تأیید نشده؛ گزارش T02 پایین |
| T03 / P1 / P0 | Agent واقعی Gemini و اولین تصمیم قابل بررسی با ابزار خواندنی | T01، داده T02؛ کلید از پوریا | schema، آرگومان ابزار، no-op، malformed/timeout/budget؛ smoke واقعی مدل؛ تصمیم ورود/عدم اقدام/خروج از evidence؛ snapshot→AI→risk→simulated order | TODO؛ smoke واقعی کوچک PASS روی probe revision d10e456؛ تصمیم معاملاتی/برش کامل هنوز ساخته نشده |
| T04 / P1 / P0 | ledger و حسابداری مالی | T01 | Decimal و quantization؛ fill جزئی/fee پایه و quote/locked funds؛ مثال بازده ۲۵٪ و زیان ۱۰٪؛ عدم دوباره‌شماری cumulative fills و هزینه؛ تطبیق balance | TODO |
| T05 / P1 / P0 | broker مشترک و وضعیت سفارش مقاوم به تکرار | T02/T04؛ authenticated contract بعداً | shadow/historical هیچ write شبکه نکنند؛ intent قبل از side effect، UNKNOWN/reconcile، restart، cancel/fill race و duplicate event؛ تست با fake منطبق قرارداد | TODO |
| T06 / P1 / P0 | گیت ریسک و توقف/پایان مستقل از AI | T04/T05 | سقف حجم/exposure، stop، min buy/sell، fee، stale data، دارایی قفل؛ model malicious/NaN نتواند gate را دور بزند؛ end-time/ازسرگیری finalization و residual آزموده شوند | TODO؛ policy عددی پس از داده تنظیم شود |
| T07 / P2 / P0 | بک‌تست causal و انتخاب یک نامزد قابل دفاع | T02–T06 | split از پیش ثبت، prefix-invariance، costs/fill بدبینانه، walk-forward/holdout؛ نقد/cash، hold و no-AI baseline؛ گزارش همه پنجره‌ها/تجربه‌ها؛ exposure/minimumهای واقعی در صورت موجود بودن | TODO؛ نتیجه سودآوری هنوز نداریم |
| T08 / P2 / P1 | بهبود نقش AI و انتخاب تنظیم کم‌هزینه | T03/T07؛ budget معلوم | ablation هم‌شرایط، نمونه fresh و تکرار حساس؛ ثبت semantic errors/latency/tokens؛ تصمیم بهتر با صرف هزینه بیشتر ثابت نشده باشد، پیچیدگی اضافه نشود | TODO؛ provider بعدی مسابقه U |
| T09 / P3 / P0 | اجرای سایه پیوسته و میزبان منتخب | T03–T07؛ دسترسی سرور اگر لازم | حداقل هدف داخلی یک ساعت + restart/قطعی، تصمیم واقعی مدل و execution شبیه‌سازی؛ گزارش متمایز؛ Wallex/مدل از Liara، volume و single worker آزموده؛ لپ‌تاپ fallback مستند | TODO؛ deploy هنوز نشده |
| T10 / P4 / P0 | فعال‌سازی live حداقلی و تطبیق حساب | T09 + checklist docs/evaluation-plan + کلید/allowlist/fee | پوریا حساب و محدوده را تأیید کند؛ worker روی commit تمیز؛ اولین ورود/خروج خودکار در کمترین مقدار مجاز قابل فروش؛ log/fill/fee/balance تطبیق؛ هیچ تأیید دستی تک‌معامله | BLOCKED؛ دسترسی Wallex هنوز داده نشده؛ امروز سفارش واقعی ارسال نمی‌شود |
| T11 / P4 / P1 | پایش و اصلاح evidence-driven در دوره live | T10 | heartbeat/equity/افت/درصد موفقیت فنی و errors؛ تغییر با repro+regression و run جدید؛ بدون chase-loss، معامله اجباری یا افزایش حجم بی‌مدرک | TODO |
| T12 / P5 / P0 | بستن خودکار، freeze و تحویل | T06؛ شواهد T07/T09/T10 هرکدام با وضعیت واقعی | پایان در تومان/گزارش dust، cancel/reconcile؛ سورس تمام نسخه‌های سودساز، markdown و log دلیل، replay پاک؛ ویدئو حدود ۵ دقیقه با روایت، لینک و دسترسی داور و مدرک تحویل پیش از deadline | TODO؛ private حفظ شود |

## نقاط کنترل انسانی و زمان

- اکنون: GOOGLE_API_KEY در .env محلی قرار گرفت و smoke PASS شد؛ کلید از Git خارج است. مقدار budget آزمایش را پیش از اجرای انبوه تعیین کند.
- امروز: Coding Agent یک vertical slice شبیه‌سازی‌شده، آزمون تاریخی معتبر و سپس سایه می‌سازد. ساخته نشدن/خرابی core به تعویق UI و فیچر اضافی منجر شود.
- فردا: دریافت حساب → راستی‌آزمایی read-only نوع حساب/بازار/fee → اتمام گیت‌های فنی → live حداقلی. نبود شواهد با خواست شروع سریع پوشانده نشود.
- بازبینی داخلی اواخر روز دوم برنامه تیم است؛ reviewer باید کد و خروجی تازه را بررسی کند و پوریا منطق را توضیح بدهد. بازنویسی معماری بدون خطای واقعی در این مقطع توجیه ندارد.
- روز پایانی: freeze مناسب باقی‌مانده زمان، finalization خودکار با buffer اندازه‌گیری‌شده، export لاگ و ارسال ویدئو زودتر از ۲۳:۵۰. ویدئو را برای آخرین دقیقه نگه ندارید.

## تصمیم‌های مهم

ترجیح تازه پوریا: پیاده‌سازی گام‌به‌گام، یک تسک فعال با پذیرش/تست/گزارش و به‌روزرسانی وضعیت پیش از تسک وابسته بعدی. commitها در سطح فاز منسجم باشند؛ دو commit آماده‌سازی با درخواست صریح او تجمیع می‌شوند. این تجمیع شامل نسخه معاملاتی نیست و مجوز بازنویسی خودکار تاریخچه در آینده نیست.

به‌روزرسانی ترجیح پوریا در T02: commit زیاد نزن؛ تمرکز بر کیفیت و بهبود قابل سنجش. این نوبت بدون commit میانی، فقط یک checkpoint برای مجموعه آزموده T02 و بررسی منابع ساخته می‌شود؛ شرط revision تمیز پیش از live پابرجاست.

به‌روزرسانی T02/T05/T06/T07/T10: فقط اسپات بدون لوریج و فروش از موجودی؛ `docs/market-access-policy.md` و snapshot `config/wallex-credit-market-policy.json` لازم‌الاجرا هستند. T02 به جای انتظار فهرست مثبت دستی تازه، universe را از catalog/دسترسی حساب پس از حذف اجتماع ممنوع‌ها می‌سازد. تست‌های اجرایی بعدی باید نماد ممنوع در env/پیشنهاد مدل، دو quote، پیشوند عددی، refresh محدودیت و SELL بدون موجودی را رد کنند. تست فعلی فقط صحت snapshot است، نه تأیید دسترسی یا گیت runtime.

| تصمیم | علت | پیامد/شرط بازبینی |
|---|---|---|
| یک موتور Python و یک Agent محدود، D01/D02 | بریف موتورمحور، زمان کم، قابلیت آزمون و نقش واقعی AI | مشکل provider/ablation می‌تواند SDK مستقیم را توجیه کند؛ agent بیشتر پیش‌فرض نیست |
| REST برای سفارش؛ ابزارهای مدل فقط خواندنی، D03 | مرز حساب، جلوگیری از تکرار و مسیر سریع اجرا | MCP رسمی اگر رسید فقط پس از خواندن قرارداد و سنجش اضافه شود |
| SQLite و یک worker، D04 | کمترین persistence لازم برای پول واقعی | روی Liara volume لازم؛ هم‌زمانی لپ‌تاپ/سرور ممنوع |
| AI در تصمیم؛ ریسک/stop/پایان قطعی، D05 | ۳۵ امتیاز AI همراه با حفاظت پول و سرعت | خروجی مدل حق دور زدن risk را ندارد |
| استقرار ترجیحی Liara پس از probe، D06 | کاهش خطر Sleep و قطع لپ‌تاپ | شبکه/دیسک/restart تأییدنشده است؛ deployment هنوز موفق گزارش نمی‌شود |
| live حداقل قابل خروج، درخواست پوریا | محدود کردن خطای نخستین اجرا | حداقل خرید با fee ممکن است قابل فروش نباشد؛ sizing باید این را بسنجد |

## لاگ جلسات و شواهد

### ۲۰۲۶-۱۰-۲۱ — آماده‌سازی

- بریف و transcript پوریا خوانده شد؛ صفحه عمومی با HTTP مستقیم خوانده شد؛ GitHub API، private بودن و نبود commit اولیه را نشان داد.
- Blueprint کامل بررسی و غیرمرجع علامت‌گذاری شد. لغو سفارش و ping v2 با مستند رسمی تطبیق یافت. نبود فهرست مجاز، fee مسابقه و روش دقیق امتیازدهی ثبت شد.
- پوریا زمان پایان را ۲۳:۵۰، مدل تست را Gemini 3.5 Flash-Lite، سرمایه را پنج میلیون تومان و شروع حداقلی live را فردا تأیید کرد. مدل ID از منبع رسمی گوگل بررسی شد.
- تغییرات این مرحله فقط آماده‌سازی/قرارداد و probe است؛ استراتژی سودساز، موتور و backtest آن پیاده‌سازی نشده‌اند.
- tests آماده‌سازی ۱۲/۱۲ در محیط فعلی و محیط پاک نصب‌شده از lock گذشت؛ Ruff و compileall موفق؛ مسیر بدون key مدل BLOCKED/exit 2 و بدون درخواست بود. docs/preparation-checks.md شرح کامل را دارد.
- شش پنجره/نماد با درخواست resolution=15 همگی DEGRADED شدند؛ عمدتاً داده یک‌دقیقه‌ای آمد. کنترل 1 و 15 پاسخ یکسان و 60 پاسخ ساعتی داد. در پنجره دوم تتر ۴۲۷ ردیف روی شبکه یک دقیقه گم‌شده بود؛ loader T02 باید cadence و gap را صریح حل کند.
- commit آماده‌سازی فقط شواهد این مرحله است؛ revision از git log -1 قابل بازیابی است. هیچ کد سودساز یا نتیجه live به آن نسبت داده نشده است.

بعد از هر فاز همین‌جا بنویس: زمان/commit، هدف و AC، دستور/نتیجه، real/simulated/blocked، خطای باقیمانده و task بعدی. این دفتر جای log هر tick یا ذخیره Secret نیست.

### ۲۰۲۶-۱۰-۲۱ — T02 و اولین smoke واقعی مدل

- **دامنه/AC:** market/account parser، داده دقیق، source/hash، cutoff، gap/cadence و کندل کامل؛ فقط collector عمومی و tests مصرف‌کننده‌اند. J07/J08/J09 و مقدمات R08/R09/R18؛ بدون broker، استراتژی یا سفارش. callerهای probe قبلی دست‌نخورده‌اند؛ migration و وابستگی جدید لازم نشد.
- **ساخته‌شده و آزموده:** JSON بدون float/NaN/duplicate keys؛ Decimal غیرمنفی و سقف host برابر ۱۲۸ digit/exponent؛ پنجره حداکثر ۱۰۰هزار کندل؛ closed cutoff، UTC aggregation و flag bin ناقص؛ universe از metadata واقعی و account universe صریح منهای اجتماع ممنوع‌ها. account نامعلوم و selection ممنوع رد می‌شوند. precision صرفاً metadata است و min-order/tick از آن حدس زده نمی‌شود.
- **Simulated/private:** balance با total/available/freeze و fee coefficients طبق schema رسمی fixture دارند، نه پاسخ حساب واقعی. `/v1/account/balances` متعلق به حساب اصلی است؛ reference به balances-detail اصلاح شد. نبود کلید Wallex/شناسه، fee و min-order، تأیید خصوصی را BLOCKED نگه می‌دارد.
- **Real Google:** کلید فقط در .env ignored قرار گرفت؛ `probe_model.py --run`، PASS/exit 0، WAIT و یک read_snapshot، دو درخواست، ۳۳۴ input و ۴۱ output token، ۱۶٫۶۲۵ ثانیه. [شاهد sanitized](docs/evidence/google-smoke-2026-10-21.json) متعلق به probe revision d10e456 است؛ کیفیت تصمیم معاملاتی یا قیمت پولی token سنجیده نشد. نتیجه no-key قبلی superseded است، تست no-key همچنان موجود است.
- **Real Wallex:** ۴۶۹ بازار catalog parse شد. درخواست resolution=1 هفت‌روزه شش بار فقط ردیف end داد؛ شکست در research/t02-seven-day-request-rejected.json حفظ شد. collector به روزانه با حداکثر ۴۹ GET بدون retry محدود شد. اجرای نهایی **DEGRADED/exit 1**: هفته اول BTCTMN هفت و ETHTMN ده کندل ساعتی با aggregation دقیقه‌ای اختلاف داشتند؛ USDTTMN ۶۷۲ کندل ۱۵دقیقه و تطبیق ۲۴ ساعت روز اول را گذراند. هفته دوم هر سه در اولین روز گپ‌دار رد شدند؛ BTC/ETH هرکدام ۲ و USDT در همان روز ۸۷ دقیقه غایب داشتند؛ کل هفته با این توقف دوباره کامل profile نشد. [گزارش](research/t02-data-contract.json) hash/زمان/query دارد. عبور یک نمونه، تأیید کل داده یا سود نیست.
- **Checks:** `unittest discover -s tests -v`: **۴۹ passed / صفر failed / صفر skipped**؛ Ruff، compileall، build wheel، help ابزار جدید و check-config محلی موفق. نصب پاک مجدد در T02 انجام نشد؛ شاهد نصب پاک T01 برای همان lock است. spy عمومی فقط GET بدون header خصوصی و HTTP200/success=false و mismatch/rejection آزموده شد.
- **منابع:** README هفت مخزن و پنج فایل مرتبط بررسی و یافته/کاربرد/ادعای تأییدنشده در docs/source-review.md ثبت شد. هیچ افزونه، مدل، agent اضافه یا وعده دقت/latency از روی آن‌ها پذیرفته نشد.
- **Revision/commit:** فقط یک checkpoint بدون commit میانی، `Add exact market data contracts and public preparation`، parent d10e456؛ hash از `git log -1 --format=%H -- src/royin/market_data.py` قابل بازیابی است. تغییر مستقل .gitignore در حین کار دیده شد؛ حفظ و از commit این فاز خارج می‌شود. push انجام نمی‌شود.
- **قدم بعدی:** علت اختلاف OHLCV و semantics زمان از پاسخ رسمی/منبع مستقل بررسی شود؛ dataset گپ‌دار یا ناسازگار معیار سود نیست. T03 می‌تواند بر قرارداد fixture و مجموعه سناریوی مستقل کار کند، اما T07/backtest معتبر و T10/live تا رفع موانع تأیید نمی‌شوند. پیش از eval انبوه بودجه مدل معلوم شود؛ فردا WALLEX_API_KEY حساب اختصاصی و SUB_ACCOUNT_CLIENT_ID فقط در .env برای تأیید read-only لازم‌اند؛ هیچ دانلود فعلی از پوریا لازم نیست.

### ۲۰۲۶-۱۰-۲۱ — T01، config و CLI بدون transport

- **دامنه/AC:** فقط `src/royin`، packaging، تست config، مثال env و دستورها؛ caller معاملاتی، fixture جدید یا migration نداشت. پشتیبانی زیرساخت/استراتژی به این گام اضافه نشد. J08 نصب/اجرای مجدد و مقدمات J07/R04/R05/R08/R09 پوشش داده شد؛ حساب/بازار/ریسک runtime هنوز تأیید نشده‌اند.
- **D:** shadow پیش‌فرض؛ همه liveها حتی با پیش‌نیاز ادعایی رد می‌شوند تا گیت‌های T02–T10 پیاده و تأیید شوند. انتخاب نماد فقط syntax است و مجوز بازار نیست؛ سیاست ریسک ساختگی یا سوییچ تأیید دستی ساخته نشد.
- **S / checks:** `unittest discover -s tests -v`، ۲۸ passed و صفر fail/skip در .venv و محیط پاک موقت نصب‌شده از requirements.lock؛ سپس همان ۲۸ تست پس از نصب wheel هم گذشت. `ruff check src scripts tests` و `compileall -q src scripts tests` موفق. `uv build --wheel` موفق؛ `python -m royin --help` و `check-config` با مثال و env محلی موفق، `VALID_CONFIG_ONLY` و network/trading هر دو false.
- **S / regression:** parser پیش‌فرض timestamp عددی را می‌پذیرفت؛ قبل از پایان گام به ISO صریح با offset محدود شد و همان تست مرزی گذشت. خطا/نام تنظیم ناشناخته، محتوا یا Secret را در CLI چاپ نمی‌کند؛ spy اتصال و عدم ساخت SQLite آزموده شد.
- **Real public:** audit در ۱۵:۲۶:۰۳ UTC (۱۸:۵۶:۰۳ ایران)، شش DEGRADED/exit 1؛ hash تمام پاسخ‌ها با دریافت قبلی برابر بود. هیچ نتیجه مالی ندارد. `probe_model.py --run`، BLOCKED و exit واقعی 2؛ کلید نبود، درخواست provider ارسال نشد. تست‌های FunctionModel فقط simulated قراردادند.
- **Revision:** commit حاوی همین گزارش، با عنوان `Add fail-closed runtime configuration and CLI` و parent `5ab2002`؛ hash با `git log -1 --format=%H -- src/royin/config.py` بازیابی می‌شود. تغییرهای کاربر وجود نداشت؛ push/تغییر دسترسی انجام نمی‌شود.
- **قدم بعدی:** T02 عمومی، قرارداد داده causal و cadence/gap؛ قرارداد خصوصی منتظر کلید حساب اختصاصی است. برای smoke مدل، پوریا فقط GOOGLE_API_KEY را در .env بگذارد؛ دستور و انتظار دقیق در AGENTS و گزارش آماده‌سازی است. این مانع T02 عمومی نیست.

### ۲۰۲۶-۱۰-۲۱ — تکمیل محدودیت بازار و حساب

- توضیح جدید پوریا درباره اسپات بدون لوریج، فهرست جفت‌های غیرفعال و تصویر مقایسه حساب خوانده و به قرارداد، معماری، ارزیابی و Master Prompt منتقل شد. مجهول قبلی نبود قاعده بازار superseded شد؛ دسترسی واقعی حساب هنوز بررسی نشده است.
- snapshot کامل ۳۴۵ جفت در config/wallex-credit-market-policy.json ذخیره شد؛ ۱۷۱ TMN و ۱۷۴ USDT، بدون تکرار و با حفظ نام‌های عددی. سه تست snapshot اضافه شد؛ گیت runtime به Coding Agent سپرده شده و تأییدشده تلقی نمی‌شود.
- دستور unittest کامل روی همین نسخه: **۱۵ passed، صفر failed/skip**. Ruff موفق؛ بررسی whitespace و لینک‌های محلی قبل از commit انجام می‌شود. تست مدل واقعی/خصوصی و سفارش انجام نشده است؛ داده تاریخی دوباره دریافت نشد چون این تغییر به downloader دست نزده است.
