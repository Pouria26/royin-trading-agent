# برنامه اجرایی و دفتر وضعیت

وضعیت‌ها: TODO / IN_PROGRESS / BLOCKED / VERIFIED / FAILED. VERIFIED فقط با شاهد همان نسخه. وابستگی خارجی مسدود به معنی توقف کار مستقل نیست. مالک اصلی همه تسک‌های این مخزن Coding Agent کاربر است؛ کار انسانی لازم در هر ردیف روشن است.

**وضعیت جاری ۲۰۲۶-۱۰-۲۲:** داده native-hour برای diagnostics در دسترس است؛ منبع/حجم/finality و کفایت استراتژی تأیید نشده‌اند. مشاهده عمومی با یک snapshot بسته آزموده شد؛ Shadow استراتژی و Live بسته‌اند. پایان گزارش‌شده مسابقه ۲۰۲۶-۱۰-۲۳ ساعت۲۳:۵۰ Asia/Tehran است؛ ارسال ویدئو و زمان تحویل را برای لحظه آخر نگذارید.

## ترتیب و پذیرش

| ID / فاز / اولویت | هدف و محدوده | وابستگی | معیار پذیرش و تست لازم | وضعیت / شاهد |
|---|---|---|---|---|
| T00 / P0 / P0 | قرارداد چالش، ماتریس امتیاز، نقد Blueprint و طرح شروع | بریف کاربر و منابع | همه R01–R22 و J01–J09 پوشش؛ ابهام‌ها U ثبت؛ مستندات و Master Prompt متقابلاً سازگار؛ secret ignore بررسی | VERIFIED؛ docs/preparation-checks.md، آزمون ۱۲/۱۲ در محیط فعلی و پاک؛ آمادگی موتور ادعا نشده |
| T01 / P1 / P0 | کمترین package/CLI و config؛ بدون زیرساخت اضافی | T00 | lock نصب پاک؛ config ناقص/ناشناخته رد؛ shadow پیش‌فرض؛ تست mode و ممنوعیت live بدون حساب/allowlist/پایان/سیاست؛ دستور واقعی تست/اجرا به AGENTS افزوده شود | VERIFIED؛ ۲۸/۲۸ در محیط فعلی و پاک از lock، wheel نصب و آزموده؛ CLI فقط check-config، همه liveها بسته؛ گزارش T01 پایین |
| T02 / P1 / P0 | قرارداد market/account؛ ذخیره داده و profile زمانی | T01؛ بخش عمومی مستقل از کلید | parser قرارداد واقعی، price/qty/fee و واحد روشن، ترتیب/گپ/بازه/کندل بسته؛ fixture sanitized؛ داده عمومی مجوز بازار نیست | BLOCKED برای پذیرش کامل؛ کد و fixture قرارداد عمومی/خصوصی آزموده؛ اجرای واقعی DEGRADED، خصوصی/fee/min-order تأیید نشده؛ گزارش T02 پایین |
| T03 / P1 / P0 | Agent واقعی BoxAPI و اولین تصمیم قابل بررسی با ابزار خواندنی | T01، داده T02؛ کلید از کاربر | schema، آرگومان ابزار، no-op، malformed/timeout/budget؛ smoke واقعی مدل؛ تصمیم ورود/عدم اقدام/خروج از evidence؛ snapshot→AI→risk→simulated order | IN_PROGRESS؛ smoke قبلی منحنی AI یا ۸ نمونه تجمیعی را اثبات نمی‌کند؛ replay هم‌state ساخته، ارزش افزوده AI تأییدنشده |
| T04 / P1 / P0 | ledger و حسابداری مالی | T01 | Decimal و quantization؛ fill جزئی/fee پایه و quote/locked funds؛ مثال بازده ۲۵٪ و زیان ۱۰٪؛ عدم دوباره‌شماری cumulative fills و هزینه؛ تطبیق balance | IN_PROGRESS؛ SELL fee پایه و metrics partial-exit با oracle مستقل اصلاح؛ حساب واقعی/همه recoveryها تأییدنشده |
| T05 / P1 / P0 | broker مشترک و وضعیت سفارش مقاوم به تکرار | T02/T04؛ authenticated contract بعداً | shadow/historical هیچ write شبکه نکنند؛ intent قبل از side effect، UNKNOWN/reconcile، restart، cancel/fill race و duplicate event؛ تست با fake منطبق قرارداد | IN_PROGRESS؛ LIMIT/slippage/causal time و partial restart اصلاح؛ paper-only؛ live broker خارج scope |
| T06 / P1 / P0 | گیت ریسک و توقف/پایان مستقل از AI | T04/T05 | سقف حجم/exposure، stop، min buy/sell، fee، stale data، دارایی قفل؛ model malicious/NaN نتواند gate را دور بزند؛ end-time/ازسرگیری finalization و residual آزموده شوند | IN_PROGRESS؛ policy کامل مصرف، pending intent مانع stacking، stop مستقل؛ مقدار live و مشخصات سفارش تأییدنشده |
| T07 / P2 / P0 | بک‌تست causal و انتخاب یک نامزد قابل دفاع | T02–T06 | split از پیش ثبت، prefix-invariance، costs/fill بدبینانه، walk-forward/holdout؛ نقد/cash، hold و no-AI baseline؛ گزارش همه پنجره‌ها/تجربه‌ها؛ exposure/minimumهای واقعی در صورت موجود بودن | BLOCKED؛ داده تازه ۲/۱۳ روز پذیرفته، صفر پنجره۷۲ساعته؛ INSUFFICIENT_EVIDENCE، هیچ نامزد انتخاب نشد |
| T08 / P2 / P1 | بهبود نقش AI و انتخاب تنظیم کم‌هزینه | T03/T07؛ budget معلوم | ablation هم‌شرایط، نمونه fresh و تکرار حساس؛ ثبت semantic errors/latency/tokens؛ تصمیم بهتر با صرف هزینه بیشتر ثابت نشده باشد، پیچیدگی اضافه نشود | BLOCKED؛ ابتدا داده معتبر؛ صفر تصمیم جدید پولی؛ baselineها بدون AI و نقش افزوده مدل اثبات نشده |
| T09 / P3 / P0 | اجرای سایه پیوسته و میزبان منتخب | T03–T07؛ دسترسی سرور اگر لازم | حداقل هدف داخلی یک ساعت + restart/قطعی، تصمیم واقعی مدل و execution شبیه‌سازی؛ گزارش متمایز؛ Wallex/مدل از Liara، volume و single worker آزموده؛ لپ‌تاپ fallback مستند | BLOCKED؛ چهار کندل synthetic recovery/stop، نه Shadow جاری؛ یک ساعت feed تازه اجرا نشده |
| T10 / P4 / P0 | فعال‌سازی live حداقلی و تطبیق حساب | T09 + checklist docs/evaluation-plan + کلید/allowlist/fee | کاربر حساب و محدوده را تأیید کند؛ worker روی commit تمیز؛ اولین ورود/خروج خودکار در کمترین مقدار مجاز قابل فروش؛ log/fill/fee/balance تطبیق؛ هیچ تأیید دستی تک‌معامله | BLOCKED؛ دستور این مأموریت هیچ خرید/فروش/اعتبار/انتقالی را مجاز نمی‌کند؛ gateهای فنی بسته |
| T11 / P4 / P1 | پایش و اصلاح evidence-driven در دوره live | T10 | heartbeat/equity/افت/درصد موفقیت فنی و errors؛ تغییر با repro+regression و run جدید؛ بدون chase-loss، معامله اجباری یا افزایش حجم بی‌مدرک | TODO |
| T12 / P5 / P0 | بستن خودکار، freeze و تحویل | T06؛ شواهد T07/T09/T10 هرکدام با وضعیت واقعی | پایان در تومان/گزارش dust، cancel/reconcile؛ سورس تمام نسخه‌های سودساز، markdown و log دلیل، replay پاک؛ ویدئو حدود ۵ دقیقه با روایت، لینک و دسترسی داور و مدرک تحویل پیش از deadline | TODO؛ private حفظ شود |

## نقاط کنترل انسانی و زمان

- کنترل نهایی یکپارچه‌سازی: ۱۷۷ تست، صفر fail/skip؛ Ruff، compileall، wheel و diff check موفق. گیت‌ها همچنان بسته‌اند. در این یکپارچه‌سازی۳ GET عمومی مصرف شد (۲تلاش PARTIAL و۱مشاهده بسته COMPLETE)، صفر درخواست مدل و صفر سفارش؛ این اعداد مصرف دور تحویل Agent1/2 را جایگزین نمی‌کنند.

- **یکپارچه‌سازی ۲۰۲۶-۱۰-۲۲:** دو تحویل متوقف و hashهای pointer/contract/plan/source/dataset مستقلاً تأیید شدند؛ ۶۲۳ native-hour bar در۲قطعه با یک ساعت gap، DIAGNOSTIC_ONLY. بازپخش آفلاین۴۰پاسخ با صفر GET؛ شش تنظیم روی۷پنجره۷۲ساعته بدون AI اجرا شدند و نامزدی انتخاب نشد. جزئیات جاری docs/candidate-evaluation.md و research/integration-validation.json؛ ادعای Holdout دست‌نخورده سپتامبر۲۴–۲۷ و حد آماری۳۰trade تصحیح شدند. Runner کندل باز/gap/stale را رد، Candidate را قبل I/O مسدود و یک چرخه مشاهده عمومی را ثبت کرد. T07/T08/T09/T10 همچنان فاقد پذیرش استراتژی/AI/Shadow/Live هستند؛ هدف این تحویل یکپارچه‌سازی و diagnostics است.

- گزارش تازه حساب فعال: کاربر ۵٬۰۰۰٬۰۰۰ TMN آزاد، اعتبار بدون کارمزد و maker/taker مشخص برای دو quote را ارائه کرد؛ اعداد در docs/challenge-brief.md ثبت‌اند. T10 هنوز BLOCKED: هویت/دسترسی API، minimum/step، صحت موتور و شواهد معتبر لازم‌اند. بازبینی مستقل تحویل دو Agent: ۱۰۶ تست و Ruff پاس؛ با این حال partial fillهای `0.1+0.2` برای intent `0.3` با خطای دقت SQLite رد شدند و set_balance ورودی float را پذیرفت. دستور یکپارچه‌سازی محلی در .local/parallel/integration-review-prompt.md است و نباید commit شود؛ برچسب تکمیل handoffها پذیرش مستقل نیست.

- ۲۰۲۶-۱۰-۲۱ / متن تازه شرایط اعتبار: برای پذیرش live در T10، کارمزد معامله سطح یک، نرخ/معافیت هزینه اعتبار، وضعیت/زمان انقضا و شرایط هشدار/لیکویید همین طرح با مدرک حساب/پاسخ برگزارکننده تعیین شوند. T04/T07 هزینه‌ها را تفکیک کنند؛ T06/T12 انقضا و فروش اجباری صرافی را از خروج الگوریتم جدا تطبیق دهند. منبع نقل کاربر است، نه API واقعی؛ کد/فهرست بازار/تنظیمات تغییر نکرد. این گام فقط تطبیق مستندات است، نه تأیید آمادگی اجرا.

- اکنون: BoxAPI جای Gemini را گرفت؛ BOXAPI_API_KEY و WALLEX_API_KEY محلی ذخیره‌اند. کلید Google فعال حذف شد؛ budget نسخه‌دار و ledger پایدار است. مشاهده قدیمی خالی بودن SUB_ACCOUNT_CLIENT_ID وضعیت جاری نیست؛ وضعیت از probe محلی همان حساب بررسی شود و شناسه حدس زده نشود.
- امروز: Coding Agent یک vertical slice شبیه‌سازی‌شده، آزمون تاریخی معتبر و سپس سایه می‌سازد. ساخته نشدن/خرابی core به تعویق UI و فیچر اضافی منجر شود.
- مسیر آینده، پس از حساب فعال: راستی‌آزمایی read-only نوع حساب/بازار/fee → اتمام گیت‌های فنی → بررسی مستقل پیش از live حداقلی. نبود شواهد با خواست شروع سریع پوشانده نشود.
- بازبینی داخلی اواخر روز دوم برنامه تیم است؛ reviewer باید کد و خروجی تازه را بررسی کند و کاربر منطق را توضیح بدهد. بازنویسی معماری بدون خطای واقعی در این مقطع توجیه ندارد.
- روز پایانی: freeze مناسب باقی‌مانده زمان، finalization خودکار با buffer اندازه‌گیری‌شده، export لاگ و ارسال ویدئو زودتر از ۲۳:۵۰. ویدئو را برای آخرین دقیقه نگه ندارید.

## تصمیم‌های مهم

ترجیح تازه کاربر: پیاده‌سازی گام‌به‌گام، یک تسک فعال با پذیرش/تست/گزارش و به‌روزرسانی وضعیت پیش از تسک وابسته بعدی. commitها در سطح فاز منسجم باشند؛ دو commit آماده‌سازی با درخواست صریح او تجمیع می‌شوند. این تجمیع شامل نسخه معاملاتی نیست و مجوز بازنویسی خودکار تاریخچه در آینده نیست.

به‌روزرسانی ترجیح کاربر در T02: commit زیاد نزن؛ تمرکز بر کیفیت و بهبود قابل سنجش. این نوبت بدون commit میانی، فقط یک checkpoint برای مجموعه آزموده T02 و بررسی منابع ساخته می‌شود؛ شرط revision تمیز پیش از live پابرجاست.

به‌روزرسانی T02/T05/T06/T07/T10: فقط اسپات بدون لوریج و فروش از موجودی؛ `docs/market-access-policy.md` و snapshot `config/wallex-credit-market-policy.json` لازم‌الاجرا هستند. T02 به جای انتظار فهرست مثبت دستی تازه، universe را از catalog/دسترسی حساب پس از حذف اجتماع ممنوع‌ها می‌سازد. تست‌های اجرایی بعدی باید نماد ممنوع در env/پیشنهاد مدل، دو quote، پیشوند عددی، refresh محدودیت و SELL بدون موجودی را رد کنند. تست فعلی فقط صحت snapshot است، نه تأیید دسترسی یا گیت runtime.

| تصمیم | علت | پیامد/شرط بازبینی |
|---|---|---|
| یک موتور Python و یک Agent محدود، D01/D02 | بریف موتورمحور، زمان کم، قابلیت آزمون و نقش واقعی AI | مشکل provider/ablation می‌تواند SDK مستقیم را توجیه کند؛ agent بیشتر پیش‌فرض نیست |
| REST برای سفارش؛ ابزارهای مدل فقط خواندنی، D03 | مرز حساب، جلوگیری از تکرار و مسیر سریع اجرا | MCP رسمی اگر رسید فقط پس از خواندن قرارداد و سنجش اضافه شود |
| SQLite و یک worker، D04 | کمترین persistence لازم برای پول واقعی | روی Liara volume لازم؛ هم‌زمانی لپ‌تاپ/سرور ممنوع |
| AI در تصمیم؛ ریسک/stop/پایان قطعی، D05 | ۳۵ امتیاز AI همراه با حفاظت پول و سرعت | خروجی مدل حق دور زدن risk را ندارد |
| استقرار ترجیحی Liara پس از probe، D06 | کاهش خطر Sleep و قطع لپ‌تاپ | شبکه/دیسک/restart تأییدنشده است؛ deployment هنوز موفق گزارش نمی‌شود |
| live حداقل قابل خروج، درخواست کاربر | محدود کردن خطای نخستین اجرا | حداقل خرید با fee ممکن است قابل فروش نباشد؛ sizing باید این را بسنجد |

## لاگ جلسات و شواهد

### اعتبار تاریخی — بررسی مستقل روی f4970f3، ۲۰۲۶-۱۰-۲۱

- وضعیت آغاز clean، ۱۳۱ تست و Ruff پاس. reproهای slippage price improvement، intrabar timestamp، injected budget، crash status و SELL base-fee مستقل fail شدند و سپس اصلاح شدند؛ fixtureهای دستی metrics، partial restart و audit اضافه شد. نتیجه نهایی در docs/historical-validation.md و گزارش محلی ignored ثبت است.
- ادعاهای قبلی تکمیل جامع، «institutional»، ۸ smoke، هزینه actual و Shadow واقعی superseded هستند؛ تاریخچه و گزارش قدیمی حذف/بازنویسی نشدند. مدل واقعی قبلی از baseline بدون AI جداست.
- پروتکل شش configuration قبل دانلود ثبت شد؛ data run 20261021T195923Z_4757edf7 با ۲۵ GET و ۲ روز معتبر، BLOCKED_DATA. انتخاب نامزد/holdout/AI پولی جلو نرفت؛ پاسخ INSUFFICIENT_EVIDENCE است. baseline و sensitivity فقط diagnostic روی اکتبر۱–۸ development اجرا شدند.
- raw/log/DB ignored؛ پروتکل/پذیرش/شاهد sanitized قابل commit. MASTER_PROMPT.md و .local/parallel وارد index نمی‌شوند؛ push/بازنویسی تاریخچه مجاز نیست.
- قدم بعدی واحد: حل معنای زمانی/اختلاف OHLC minute-native با منبع رسمی و سپس پروتکل داده تازه؛ نه تغییر معیار برای عبور دادن داده ردشده.


### ۲۰۲۶-۱۰-۲۱ — بازبینی، حافظه فنی و تقسیم کار محلی

- مسیرهای config/CLI، parser و aggregation، دسترسی بازار/حساب، budget و probeها و تست‌های متناظر بررسی شدند. وضعیت همچنان foundation بدون موتور معاملاتی/بک‌تست است؛ داده جامع DEGRADED و تأیید حساب خصوصی مسدود است. در این بازبینی هیچ فراخوانی پولی یا احرازشده تازه‌ای انجام نشد.
- memory.md به قراردادهای فنی جاری، دام‌های داده و محدودیت‌های ماندگار خلاصه شد؛ نام افراد/تقسیم تیم، تاریخچه نقش‌ها، نتایج تکراری و تنظیم فعال قدیمی Google حذف شدند. دو گزاره قدیمی معماری درباره سقف turn/tool و نامشخص بودن policy مصرف با کد جاری هماهنگ شدند.
- reasoning=none از قبل در probe موجود بود. یک regression روی transport ساختگی، ارسال واقعی JSON هر دو turn به شکل reasoning_effort=none و مدل Luna را بررسی می‌کند؛ بودجه آن فقط tempfile است. suite کامل فعلی ۵۹ تست دارد؛ فرمان/نتیجه نهایی در گزارش محلی بازبینی ثبت می‌شود.
- دو مأموریت کدنویسی در .local/parallel آماده شدند: Agent 1 داده/Decision/AI و Agent 2 ledger/risk/paper broker. قرارداد مشترک، مالکیت فایل، محدودیت دست‌زدن به Git و مصرف API مشترک مشخص شد؛ فایل‌های جدید Markdown این پوشه با .git/info/exclude خارج از commit هستند. این مرحله هیچ Agent یا worker تازه‌ای اجرا نکرده است.

### ۲۰۲۶-۱۰-۲۱ — اتصال محدود MCP در Codex، درخواست مستقیم کاربر

- دامنه/AC: افزودن endpoint ارسالی با ابزار عمومی، بدون کلید/حساب/سفارش و حفظ تنظیمات قبلی؛ این کار تکمیل T03 نیست.
- واقعی: initialize و tools/list موفق، ۵۲ ابزار؛ یک tools/call عمومی get_markets موفق. پنج ابزار عمومی allowlist؛ TOML و حفظ تنظیمات با assert، سپس `codex mcp get wallex` موفق. شاهد: docs/wallex-mcp.md و docs/evidence/wallex-mcp-2026-10-21.json.
- بررسی‌نشده: reload نشست Codex، چهار فراخوان عمومی دیگر، احراز خصوصی/ساب‌اکانت و مقایسه دقت/تأخیر. موتور رویین REST باقی است؛ T03 همچنان IN_PROGRESS. هیچ مدل پولی/معامله/اعتبار اجرا نشد.

### ۲۰۲۶-۱۰-۲۱ — آماده‌سازی

- بریف و transcript کاربر خوانده شد؛ صفحه عمومی با HTTP مستقیم خوانده شد؛ GitHub API، private بودن و نبود commit اولیه را نشان داد.
- Blueprint کامل بررسی و غیرمرجع علامت‌گذاری شد. لغو سفارش و ping v2 با مستند رسمی تطبیق یافت. نبود فهرست مجاز، fee مسابقه و روش دقیق امتیازدهی ثبت شد.
- کاربر زمان پایان را ۲۳:۵۰، مدل تست را Gemini 3.5 Flash-Lite، سرمایه را پنج میلیون تومان و شروع حداقلی live را فردا تأیید کرد. مدل ID از منبع رسمی گوگل بررسی شد.
- تغییرات این مرحله فقط آماده‌سازی/قرارداد و probe است؛ استراتژی سودساز، موتور و backtest آن پیاده‌سازی نشده‌اند.
- tests آماده‌سازی ۱۲/۱۲ در محیط فعلی و محیط پاک نصب‌شده از lock گذشت؛ Ruff و compileall موفق؛ مسیر بدون key مدل BLOCKED/exit 2 و بدون درخواست بود. docs/preparation-checks.md شرح کامل را دارد.
- شش پنجره/نماد با درخواست resolution=15 همگی DEGRADED شدند؛ عمدتاً داده یک‌دقیقه‌ای آمد. کنترل 1 و 15 پاسخ یکسان و 60 پاسخ ساعتی داد. در پنجره دوم تتر ۴۲۷ ردیف روی شبکه یک دقیقه گم‌شده بود؛ loader T02 باید cadence و gap را صریح حل کند.
- commit آماده‌سازی فقط شواهد این مرحله است؛ revision از git log -1 قابل بازیابی است. هیچ کد سودساز یا نتیجه live به آن نسبت داده نشده است.

بعد از هر فاز همین‌جا بنویس: زمان/commit، هدف و AC، دستور/نتیجه، real/simulated/blocked، خطای باقیمانده و task بعدی. این دفتر جای log هر tick یا ذخیره Secret نیست.

### ۲۰۲۶-۱۰-۲۱ — مهاجرت BoxAPI، بودجه پایدار و read-only حساب

- **User / D:** Gemini کاملاً با BoxAPI جایگزین شود؛ کل اعتبار گزارش‌شده ۳ دلار؛ مدل کم‌هزینه فعلی، هیچ معامله یا فعال‌سازی اعتبار. دامنه این گام caller probe، config/env/lock/tests، guard بودجه و GET کشف حساب است؛ J06/J07/J08 و مقدمات R04/R05/R09. داده/ledger معاملاتی یا broker ساخته نشده‌اند.
- **S/D:** صفحه رسمی قیمت BoxAPI و GET models بررسی شدند؛ نرخ منتشرشده با ۱۵٪ افزایش نسبت به metadata مبنای رزرو شد. gpt-6-luna ارزان‌تر از Luna 5.6 و Mini 5.4 است؛ مقایسه در docs/boxapi-budget.md. env محلی و نمونه روی boxapi/gpt-6-luna، extra openai در lock؛ fallback/کلید/وابستگی Google فعال حذف شد. شواهد قدیمی Gemini تاریخچه‌اند.
- **کنترل پول:** سقف ۲٫۴ دلار کل/۰٫۸ روزانه تهران، ۶۰۰/۲۰۰ درخواست و ۶ میلیون token؛ باقی ۰٫۶ دلار از اعتبار گزارش‌شده ذخیره. reservation integer nano-USD در SQLite قبل از HTTP، بدون refund روی خطا؛ retry خاموش. تست restart، تغییر روز، رقابت هم‌زمان، دیسک خراب و spy رزرو پیش از transport گذشت. سقف، تضمین balance کلید در اپ دیگر یا تعرفه آینده نیست.
- **Real AI:** smoke اولیه PASS؛ سپس چهار سناریوی ثابت stale/fresh/missing/injection با provider واقعی همگی PASS/exit 0. REVIEW فقط تحلیل بیشتر است، نه خرید. مجموع ۱۰ HTTP، ۲۳۳۷ input و ۲۰۱ output token؛ تخمین بر اساس قیمت 0.00038433 دلار، رزرو محافظه‌کارانه 0.0123648 دلار؛ invoice و balance واقعی تأیید نشدند. docs/evidence/boxapi-read-only-2026-10-21.json ورودی/خروجی سناریو، latency، usage و hash کد/سیاست را دارد؛ تست دقت استراتژی یا سود نیست.
- **Real Wallex:** کلید در .env؛ GET /sub-accounts، HTTP 200 و success=true، result=[]؛ ابزار BLOCKED/exit 2. هیچ clientId برای ذخیره موجود نبود، هیچ main balance/سفارش/فعال‌سازی خوانده یا ارسال نشد. روش clientId و دستور تکرار پس از تخصیص در docs/wallex-read-only-setup.md؛ raw و گزارش در data/private ignored. نوع حساب، fee، min-order و محدودیت روز هنوز BLOCKED هستند.
- **Checks:** unittest کامل ۵۸ passed، صفر failed/skip در محیط فعلی و محیط پاک موقت نصب‌شده از lock جدید؛ Ruff و compileall و check-config و helpها موفق. نصب package با --no-deps بعد از sync و check-config از env نمونه هم در محیط پاک گذشت؛ هیچ تست paid انبوه یا سفارش انجام نشد.
- **Git:** MASTER_PROMPT.md قبلاً tracked بود؛ طبق درخواست کاربر با git rm --cached از tracking خارج شد و فایل محلی و rule .gitignore حفظ شد. تاریخچه بازنویسی نمی‌شود. تنها یک commit منسجم با عنوان `Switch to budgeted BoxAPI and probe credit accounts read-only` و parent 196c02a؛ push ممنوع. revision از git log روی src/royin/model_budget.py بازیابی می‌شود.
- **بعدی:** ادامه T03 برای تصمیم معاملاتی محدود و ارزیابی مستقل، سپس وابستگی‌های مالی/اجرا؛ داده ناسازگار T02 هنوز حل‌شده نیست. بعد از تخصیص برگزارکننده، probe خواندنی دوباره اجرا شود؛ کلیدها نیاز به ارسال مجدد ندارند. مدل قوی‌تر فقط با smoke/eval و هزینه صریح بعدی، بدون فرض بهبود خودکار.

### ۲۰۲۶-۱۰-۲۱ — T02 و اولین smoke واقعی مدل

- **دامنه/AC:** market/account parser، داده دقیق، source/hash، cutoff، gap/cadence و کندل کامل؛ فقط collector عمومی و tests مصرف‌کننده‌اند. J07/J08/J09 و مقدمات R08/R09/R18؛ بدون broker، استراتژی یا سفارش. callerهای probe قبلی دست‌نخورده‌اند؛ migration و وابستگی جدید لازم نشد.
- **ساخته‌شده و آزموده:** JSON بدون float/NaN/duplicate keys؛ Decimal غیرمنفی و سقف host برابر ۱۲۸ digit/exponent؛ پنجره حداکثر ۱۰۰هزار کندل؛ closed cutoff، UTC aggregation و flag bin ناقص؛ universe از metadata واقعی و account universe صریح منهای اجتماع ممنوع‌ها. account نامعلوم و selection ممنوع رد می‌شوند. precision صرفاً metadata است و min-order/tick از آن حدس زده نمی‌شود.
- **Simulated/private:** balance با total/available/freeze و fee coefficients طبق schema رسمی fixture دارند، نه پاسخ حساب واقعی. `/v1/account/balances` متعلق به حساب اصلی است؛ reference به balances-detail اصلاح شد. نبود کلید Wallex/شناسه، fee و min-order، تأیید خصوصی را BLOCKED نگه می‌دارد.
- **Real Google:** کلید فقط در .env ignored قرار گرفت؛ `probe_model.py --run`، PASS/exit 0، WAIT و یک read_snapshot، دو درخواست، ۳۳۴ input و ۴۱ output token، ۱۶٫۶۲۵ ثانیه. [شاهد sanitized](docs/evidence/google-smoke-2026-10-21.json) متعلق به probe revision d10e456 است؛ کیفیت تصمیم معاملاتی یا قیمت پولی token سنجیده نشد. نتیجه no-key قبلی superseded است، تست no-key همچنان موجود است.
- **Real Wallex:** ۴۶۹ بازار catalog parse شد. درخواست resolution=1 هفت‌روزه شش بار فقط ردیف end داد؛ شکست در research/t02-seven-day-request-rejected.json حفظ شد. collector به روزانه با حداکثر ۴۹ GET بدون retry محدود شد. اجرای نهایی **DEGRADED/exit 1**: هفته اول BTCTMN هفت و ETHTMN ده کندل ساعتی با aggregation دقیقه‌ای اختلاف داشتند؛ USDTTMN ۶۷۲ کندل ۱۵دقیقه و تطبیق ۲۴ ساعت روز اول را گذراند. هفته دوم هر سه در اولین روز گپ‌دار رد شدند؛ BTC/ETH هرکدام ۲ و USDT در همان روز ۸۷ دقیقه غایب داشتند؛ کل هفته با این توقف دوباره کامل profile نشد. [گزارش](research/t02-data-contract.json) hash/زمان/query دارد. عبور یک نمونه، تأیید کل داده یا سود نیست.
- **Checks:** `unittest discover -s tests -v`: **۴۹ passed / صفر failed / صفر skipped**؛ Ruff، compileall، build wheel، help ابزار جدید و check-config محلی موفق. نصب پاک مجدد در T02 انجام نشد؛ شاهد نصب پاک T01 برای همان lock است. spy عمومی فقط GET بدون header خصوصی و HTTP200/success=false و mismatch/rejection آزموده شد.
- **منابع:** README هفت مخزن و پنج فایل مرتبط بررسی و یافته/کاربرد/ادعای تأییدنشده در docs/source-review.md ثبت شد. هیچ افزونه، مدل، agent اضافه یا وعده دقت/latency از روی آن‌ها پذیرفته نشد.
- **Revision/commit:** فقط یک checkpoint بدون commit میانی، `Add exact market data contracts and public preparation`، parent d10e456؛ hash از `git log -1 --format=%H -- src/royin/market_data.py` قابل بازیابی است. تغییر مستقل .gitignore در حین کار دیده شد؛ حفظ و از commit این فاز خارج می‌شود. push انجام نمی‌شود.
- **قدم بعدی:** علت اختلاف OHLCV و semantics زمان از پاسخ رسمی/منبع مستقل بررسی شود؛ dataset گپ‌دار یا ناسازگار معیار سود نیست. T03 می‌تواند بر قرارداد fixture و مجموعه سناریوی مستقل کار کند، اما T07/backtest معتبر و T10/live تا رفع موانع تأیید نمی‌شوند. پیش از eval انبوه بودجه مدل معلوم شود؛ فردا WALLEX_API_KEY حساب اختصاصی و SUB_ACCOUNT_CLIENT_ID فقط در .env برای تأیید read-only لازم‌اند؛ هیچ دانلود فعلی از کاربر لازم نیست.

### ۲۰۲۶-۱۰-۲۱ — T01، config و CLI بدون transport

- **دامنه/AC:** فقط `src/royin`، packaging، تست config، مثال env و دستورها؛ caller معاملاتی، fixture جدید یا migration نداشت. پشتیبانی زیرساخت/استراتژی به این گام اضافه نشد. J08 نصب/اجرای مجدد و مقدمات J07/R04/R05/R08/R09 پوشش داده شد؛ حساب/بازار/ریسک runtime هنوز تأیید نشده‌اند.
- **D:** shadow پیش‌فرض؛ همه liveها حتی با پیش‌نیاز ادعایی رد می‌شوند تا گیت‌های T02–T10 پیاده و تأیید شوند. انتخاب نماد فقط syntax است و مجوز بازار نیست؛ سیاست ریسک ساختگی یا سوییچ تأیید دستی ساخته نشد.
- **S / checks:** `unittest discover -s tests -v`، ۲۸ passed و صفر fail/skip در .venv و محیط پاک موقت نصب‌شده از requirements.lock؛ سپس همان ۲۸ تست پس از نصب wheel هم گذشت. `ruff check src scripts tests` و `compileall -q src scripts tests` موفق. `uv build --wheel` موفق؛ `python -m royin --help` و `check-config` با مثال و env محلی موفق، `VALID_CONFIG_ONLY` و network/trading هر دو false.
- **S / regression:** parser پیش‌فرض timestamp عددی را می‌پذیرفت؛ قبل از پایان گام به ISO صریح با offset محدود شد و همان تست مرزی گذشت. خطا/نام تنظیم ناشناخته، محتوا یا Secret را در CLI چاپ نمی‌کند؛ spy اتصال و عدم ساخت SQLite آزموده شد.
- **Real public:** audit در ۱۵:۲۶:۰۳ UTC (۱۸:۵۶:۰۳ ایران)، شش DEGRADED/exit 1؛ hash تمام پاسخ‌ها با دریافت قبلی برابر بود. هیچ نتیجه مالی ندارد. `probe_model.py --run`، BLOCKED و exit واقعی 2؛ کلید نبود، درخواست provider ارسال نشد. تست‌های FunctionModel فقط simulated قراردادند.
- **Revision:** commit حاوی همین گزارش، با عنوان `Add fail-closed runtime configuration and CLI` و parent `5ab2002`؛ hash با `git log -1 --format=%H -- src/royin/config.py` بازیابی می‌شود. تغییرهای کاربر وجود نداشت؛ push/تغییر دسترسی انجام نمی‌شود.
- **قدم بعدی:** T02 عمومی، قرارداد داده causal و cadence/gap؛ قرارداد خصوصی منتظر کلید حساب اختصاصی است. برای smoke مدل، کاربر فقط GOOGLE_API_KEY را در .env بگذارد؛ دستور و انتظار دقیق در AGENTS و گزارش آماده‌سازی است. این مانع T02 عمومی نیست.

### ۲۰۲۶-۱۰-۲۱ — تکمیل محدودیت بازار و حساب

- توضیح جدید کاربر درباره اسپات بدون لوریج، فهرست جفت‌های غیرفعال و تصویر مقایسه حساب خوانده و به قرارداد، معماری، ارزیابی و Master Prompt منتقل شد. مجهول قبلی نبود قاعده بازار superseded شد؛ دسترسی واقعی حساب هنوز بررسی نشده است.
- snapshot کامل ۳۴۵ جفت در config/wallex-credit-market-policy.json ذخیره شد؛ ۱۷۱ TMN و ۱۷۴ USDT، بدون تکرار و با حفظ نام‌های عددی. سه تست snapshot اضافه شد؛ گیت runtime به Coding Agent سپرده شده و تأییدشده تلقی نمی‌شود.
- دستور unittest کامل روی همین نسخه: **۱۵ passed، صفر failed/skip**. Ruff موفق؛ بررسی whitespace و لینک‌های محلی قبل از commit انجام می‌شود. تست مدل واقعی/خصوصی و سفارش انجام نشده است؛ داده تاریخی دوباره دریافت نشد چون این تغییر به downloader دست نزده است.


## Independent execution review - 2026-10-22

Reviewed defd88b before publication. The twelve-configuration diagnostic and twelve real-model snapshots are retained as historical evidence, not strategy approval. See docs/execution-readiness-review.md and research/execution-review-evidence.json.

- T03: 12 snapshot decisions / 24 reserved HTTP; 9 agreements with baseline. Audit usage: 12123 input / 1237 output tokens; reserved USD 0.029675520 is not invoice. Hypothetical inventory states are not an AI equity curve.
- T05/T10: offline-only WallexLiveBroker contract harness; real transport blocked even with constructor overrides. UNKNOWN/terminal/partial observations retain reserves until fill/fee accounting exists. Production reconciliation, atomic intent/state and crash/race tests remain incomplete.
- T07/T08: 12 configurations / 7 diagnostic windows, INSUFFICIENT_EVIDENCE; no candidate approved. Plan freeze timestamp is later than manifest; pre-registration is unverified. strategy-experiment-plan.json is a byte-preserving rename; the six-configuration plan remains separate.
- T09: unsafe candidate branch removed; tested OBSERVE_ONLY retained. Candidate Shadow remains blocked before I/O.
- AI diagnostic CLI requires --run, validates dataset before model setup and limits each invocation before HTTP to 24 requests / USD 0.04 reserved; persistent global limits remain. No new paid model call, private probe or real order during review.
- Next: complete offline fill/fee reconciliation first; then a genuinely prospective AI/no-AI experiment and current Shadow. No promise of stable profits and no live activation by environment flags alone.

Final review checks: 194 tests passed (24.760s), Ruff clean, compileall exit 0, wheel built, git diff --check clean. Local transcript: .local/parallel/execution-review-tests.txt (ignored).


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
