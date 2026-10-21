# دستور اصلی Coding Agent — رویین / Wallex

از این فایل شروع کن. هدف کسب بهترین نتیجه قابل دفاع در بریف واقعی است؛ تعداد قابلیت یا agent معیار موفقیت نیست. مالک چالش پوریاست؛ چالش‌های پژمان و آیدین مستقل‌اند. بدون درخواست صریح، به agentهای دیگر پیام نده و روی مخزن آن‌ها کار نکن.

## پیش از هر تغییر

1. `git status --short`، فایل‌های موجود و وابستگی‌ها را بخوان؛ تغییر هم‌زمان کاربر را حفظ کن.
2. docs/challenge-brief.md، TASKS.md و memory.md را بخوان؛ سپس بخش مربوط ARCHITECTURE.md و docs/evaluation-plan.md. Blueprint فقط فرضیه است.
3. هر caller، test، fixture، config، export و migration مرتبط را با `rg` پیدا کن. دامنه تغییر، خطر پول/داده و acceptance task را پیش از نوشتن مشخص کن.
4. R/S/D/U را مخلوط نکن: الزام بریف، مشاهده منبع، تصمیم تیم و مجهول جدا هستند. معیار/امتیاز/نماد/کارمزد ناشناخته را حدس نزن.

## دستورهای موجود و تأییدشده

PowerShell، از ریشه مخزن. نتایج و محدودیت محیط در docs/preparation-checks.md ثبت می‌شود. uv در سیستم فعلی وجود دارد؛ Python خود .venv استفاده شود، نه alias فروشگاه Windows.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m ruff check src scripts tests
.\.venv\Scripts\python.exe -m compileall -q src scripts tests
.\.venv\Scripts\python.exe -X utf8 scripts\audit_market_data.py --help
.\.venv\Scripts\python.exe -X utf8 scripts\audit_market_data.py
.\.venv\Scripts\python.exe -X utf8 scripts\probe_model.py --help
```

audit_market_data فقط GET عمومی می‌زند و گزارش کیفیت داده می‌سازد؛ هیچ معامله‌ای نمی‌کند. اجرای مجدد ممکن است داده تازه‌ای بدهد؛ hash و زمان در خروجی ثبت می‌شود.

پس از قرار دادن کلید توسط پوریا در .env، smoke پولی کوچک و بدون سفارش:

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts\probe_model.py --run
```

این دستور در نبود کلید باید با خروجی `BLOCKED` و exit 2 متوقف شود؛ آن را pass حساب نکن. این probe کیفیت استراتژی را ثابت نمی‌کند. خطا/تأخیر/token usage و پاسخ‌ها را بدون Secret ثبت کن. درخواست `--run` فعال کردن live نیست.

برای نصب آماده‌سازی در محیط تازه با uv (lock پس از حل وابستگی‌ها):

```powershell
uv venv --python 3.12 .venv
uv pip sync --python .\.venv\Scripts\python.exe requirements.lock
uv pip install --python .\.venv\Scripts\python.exe --no-deps --editable .
```

روی .venv موجود دستور venv نزن. نصب package بعد از sync لازم است؛ sync بعدی package محلی را حذف می‌کند و باید دوباره نصب شود. pyproject فقط وابستگی‌های مصرف‌شده package را دارد؛ requirements.lock محیط کامل probe/test را قفل می‌کند.

دستورهای **اجراشده T01** برای CLI اعتبارسنجی و ساخت wheel:

```powershell
.\.venv\Scripts\python.exe -m royin --help
.\.venv\Scripts\python.exe -m royin check-config --env-file .env.example
.\.venv\Scripts\python.exe -m royin check-config
uv build --wheel
```

خروجی سالم `VALID_CONFIG_ONLY` و `network_enabled=false` و `trading_enabled=false` است؛ خطای config، `BLOCKED` و exit 2 است. این CLI **موتور معامله نیست**؛ همه liveها، حتی با کلید/allowlist، تا تکمیل گیت‌های بعدی رد می‌شوند. broker و سیاست ریسک هنوز وجود ندارند؛ موفقیت check-config مجوز بازار یا readiness نیست. compileall جای lint/typecheck نیست.

config از .env پوشه جاری (در صورت وجود) و سپس متغیرهای فرایند خوانده می‌شود؛ `--env-file` صریح باید وجود داشته باشد. کلید ناشناخته فایل و متغیر ناشناخته با پیشوند اختصاصی پروژه رد می‌شود؛ متغیرهای عمومی سیستم نادیده گرفته می‌شوند. dotenv نامعتبر/تکراری رد و interpolation غیرفعال است. بودجه‌های token/cost/currency یا هر سه خالی‌اند یا هر سه معتبر؛ خالی بودن در T01 هیچ درخواست مدلی فعال نمی‌کند. LLM_BASE_URL در runtime فقط خالی و WALLEX_BASE_URL فقط origin رسمی است؛ probe موجود مستقل باقی می‌ماند.

## قواعد غیرقابل مذاکره

- کمترین تغییر کامل: helper/الگوی موجود، سپس standard library، سپس dependency نصب‌شده. لایه، تنظیم و abstraction بی‌مصرف نساز. کد جابه‌جاشده validation و error handling را حفظ کند.
- منطق جدید غیرساده یک تست کوچک معنی‌دار می‌خواهد؛ bug fix پیش از edit همه callerها را جست‌وجو و regression مؤثر بساز. assertionی که فقط خروجی fake را با خودش مقایسه کند اثبات AI نیست.
- پول/price/quantity/fees با Decimal یا واحد صحیح مستند؛ float، NaN/Infinity، ورودی منفی/نامعتبر و واحد مبهم پذیرفته نشود. تبدیل TMN/ریال/USDT فقط در مرز مشخص و دارای تست.
- schema-valid به معنی معامله درست نیست. account، allowlist، حداقل/گام، freshness، موجودی آزاد/قفل، exposure، stop، کارمزد و deadline در host دوباره بررسی شوند.
- فقط اسپات بدون لوریج/borrow/short؛ SELL محدود به موجودی قابل فروش است. docs/market-access-policy.md و config/wallex-credit-market-policy.json مرجع محدودیت بازارند. allowlist اجرایی از بازار فعال حساب پس از حذف ممنوع‌ها ساخته شود؛ env یا مدل اجازه override ندارد. «بات داخلی والکس» با موتور خارجی API یکی نیست.
- `RUN_MODE=shadow` و `ENABLE_LIVE_TRADING=false` پیش‌فرض بمانند. historical/shadow بدون کلید خصوصی هم کار کنند و مسیر transport نوشتن نداشته باشند. mode نامعتبر fail closed.
- کلید حساب اعتباری و SUB_ACCOUNT_CLIENT_ID برای live اجباری؛ هیچ fallback به دارایی اصلی یا حساب شخصی. withdrawal، deposit، انتقال و فعال‌سازی اعتبار در scope نیستند.
- مدل فقط داده لازم و ابزار خواندنی محدود می‌بیند؛ Secret، URL دلخواه، shell، خام ثبت/لغو سفارش و تغییر سیاست ریسک نمی‌بیند. ورودی بازار/متن ابزار دستور سیستم نیست.
- تمام حلقه‌ها، retry، درخواست مدل، ابزار، token، هزینه و زمان سقف داشته باشند. یک مالک retry؛ timeout نوشتن UNKNOWN و نیازمند reconciliation است، نه ارسال مجدد با ID تازه.
- intent و client_id قبل از ارسال durable؛ fillهای تکراری و cancel/fill race idempotent؛ disk/journal failure ورود جدید را ببندد. یک worker فعال برای حساب.
- توقف ریسک/پایان زمان به LLM وابسته نباشد. عدم اقدام هم تصمیم است؛ quota ساختگی، wash trading یا self-cross برای امتیاز فعالیت ممنوع.
- حداقل حجم شروع طبق ترجیح پوریا با min-order و امکان فروش پس از fee/rounding سازگار شود. «حجم پیشنهادی مثبت برای هر confidence» یا Kelly با احتمال تخمینی مدل ممنوع.
- دلیل کوتاه، evidence، ورودی/خروجی AI، gate و سفارش/fill مرتبط ثبت شود؛ دلیل را بعد از معامله جعل نکن. زنجیره فکر خصوصی مدل لازم نیست.
- TypeScript فعلاً انتخاب نشده؛ اگر بعداً مصرف‌کننده واقعی داشت، `any` ممنوع مگر محدودیت مستند و تأیید صریح پوریا. unknown را اعتبارسنجی کن.
- UI در scope اولیه نیست؛ در صورت ساخت DESIGN.md را خودت با توکن‌های واقعی ادامه بده. رنگ/spacing پراکنده، AI Slop، تعامل غیرقابل دسترس و آمار جعلی ممنوع.
- ORM فعلاً نداریم؛ migration اجراشده را دستی بازنویسی نکن. اگر Prisma/Drizzle/ابزار دیگر انتخاب شد workflow همان نسخه واقعی را مستند و migration جدید بساز.
- shortcut شناخته‌شده با comment یک‌خطی `shortcut: <limit>, <when to upgrade>` و اثر آن در گزارش ثبت شود. validation، امنیت، جلوگیری از تکرار سفارش و خواسته کاربر shortcut نمی‌خورند.

## آزمون و صداقت شواهد

docs/evaluation-plan.md قرارداد آزمون است. ترتیب زمانی train/validation/holdout حفظ؛ فقط داده موجود تا cutoff تصمیم وارد مدل شود. future candle برای **سنجش** نتیجه است و هرگز feature/prompt زمان تصمیم نیست. LLM ممکن است تاریخ گذشته را بداند؛ این ریسک را حتی با حذف تاریخ مطلق ثبت کن. fee/slippage، partial fill، عدم fill، gaps و خروج انتهای بازه حساب شوند.

خروجی آزمون را واقعاً بخوان: پاس، fail، skip و BLOCKED جدا؛ fake model، public probe، backtest، shadow، live متفاوت‌اند. بدون کلید، سود، دقت AI، latency مدل واقعی یا آمادگی live ادعا نکن. مثال‌های دستی/تست را gold ثابت نگه دار؛ بعد از دیدن خروجی معیار را برای سبز شدن ضعیف نکن.

## Git، Secret و نسخه سودساز

- مخزن تا پایان مسابقه Private؛ visibility را تغییر نده. push فقط مطابق درخواست/مجوز جلسه؛ force push ممنوع و بازنویسی تاریخچه فقط با درخواست صریح پوریا و حفظ نسخه‌های معاملاتی مجاز است.
- .env محلی، رسانه، داده/لاگ حساب و artifacts خام ignored. قبل از stage، diff و secret leakage را بررسی کن؛ کلید واقعی را در خروجی ابزار، خط فرمان، exception، ویدئو و memory ننویس. PII اعضا لازم نیست.
- فایل‌های مرتبط را صریح stage کن؛ `git add .` کورکورانه نزن. بعد از هر فاز قابل تأیید و گذر checks، `git add` و commit انجام بده؛ فایل‌های کاربر را بدون نیاز وارد commit نکن.
- مطابق ترجیح پوریا، commit در پایان فاز منسجم و آزموده‌شده باشد، نه برای هر ویرایش کوچک. تجمیع commit فقط با درخواست صریح او؛ نسخه‌های ایجادکننده معامله و manifest آن‌ها حفظ شوند.
- اگر تست واقعی به کلید/سرور/عمل پوریا نیاز دارد، دقیق بگو کدام متغیر، کدام دستور و چه خروجی سالم/خراب انتظار می‌رود. تا آن چک انجام نشده، فاز مربوطه verified نیست؛ commit کار مستقل مجاز است با ذکر چک مسدود.
- قبل از live revision تمیز و commit شده باشد. manifest هر run با همان commit/config/prompt/dataset/model ثبت شود؛ تغییر کد باید run جدید داشته باشد. شواهد نسخه‌های مختلف را به یک نتیجه ساختگی ترکیب نکن.

## حافظه و پایان هر فاز

memory.md حافظه واحد پروژه است؛ فایل agent.md موازی نساز. نکته پایدار، خطای تکرارشونده، قرارداد تأییدشده و دلیل تصمیم را با تاریخ، منبع و اثر تست اضافه کن؛ فرضیه را واقعیت ننویس و با تصحیح، یادداشت قبلی را superseded کن.

TASKS.md را بعد از هر مرحله با وضعیت، revision، نتیجه تست/مانع و قدم بعدی به‌روز کن. گزارش فاز: تغییر → معیار داوری/AC → دستور و نتیجه واقعی → real/simulated → محدودیت → درخواست دقیق کار انسانی در صورت نیاز → commit. پایان پاسخ یک یا دو خط: چه چیزی چک نشد/کنار گذاشته شد و خطر باقیمانده. رتبه اول یا سود تضمینی ادعا نکن.
