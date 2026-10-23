# داشبورد پایش رویین

سرور استاندارد Python و رابط فارسی RTL، فقط برای مشاهده شواهد. هیچ dependency
اضافی، خواندن .env، import موتور، API خصوصی، تماس مدل یا مسیر معامله ندارد.
این پوشه مستقل است؛ موتور Live یا پذیرش استراتژی را فعال نمی‌کند.

از ریشه مخزن، PowerShell؛ دستورهای زیر واقعاً اجرا شده‌اند:

```powershell
.\.venv\Scripts\python.exe -X utf8 dashboard/server.py --help
.\.venv\Scripts\python.exe -X utf8 dashboard/server.py --port 8765
```

نشانی: http://127.0.0.1:8765 . خروج با Ctrl+C. پورت 1024 تا 65535 قابل تغییر است؛
bind همواره 127.0.0.1 است. import بدون side effect شبکه/DB است. نصب لازم نیست.
در پایان بررسی مرورگر سرور آزمون خاموش شد؛ برای استفاده آن را دوباره اجرا کنید.

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s dashboard/tests -v
.\.venv\Scripts\python.exe -m ruff check dashboard
```

فقط تست‌های dashboard اجرا می‌شوند. fixtureها synthetic و در خود تست ساخته
می‌شوند؛ فایل‌های موقت در .local/dashboard و screenshotها همان‌جا هستند.
حالت پیش‌فرض هیچ fixture را بارگذاری نمی‌کند. شاهد مصنوعی موجود در artifacts
با نام SYNTHETIC / FAKE_MODEL نمایش داده می‌شود، نه به‌عنوان داده واقعی حساب.

## قرارداد API v1

Browser → same-origin monitoring API → allowlisted evidence projections.
تمام routeها مصرف‌کننده UI دارند. GET/HEAD؛ mutationهای استاندارد 405، route
ناشناخته 404، query/داده نامعتبر 400، فایل موقتاً ناموجود 503. Host و Origin
محلی، no CORS، no-store، CSP خودمیزبان، خطای عمومی بدون path/traceback.
static فقط /، /app.js، /style.css و دو مسیر دقیق فونت WOFF2 است؛ ریشه مخزن قابل browse نیست.

فونت فارسی وزیرمتن و لاتین Inter محلی‌اند؛ مجوزهای OFL، منبع نسخه‌بسته و hash
در `static/fonts/` هستند. endpoint عمومی برای browse آن پوشه وجود ندارد.
آزمون‌های `artifacts/paired-paper/*/protocol.json` نیز با چهار manifest فرزند
همان run نمایش داده می‌شوند. hash ترکیبی، checkpoint اتمیک یا تأیید یکسانی
checkout نیست. پیشرفت و پایان ثبت‌شدهٔ آزمون در نمای کلی می‌آید؛ وجود فایل
RUNNING به‌تنهایی اثبات زنده‌بودن PID نیست. پاسخ خام مدل به API پایش صادر نمی‌شود.

| Route | Query | UI |
|---|---|---|
| /api/v1/overview | ندارد | سرور، مشاهده، حساب unavailable، رزرو، usage تاریخی، مدل و رویداد |
| /api/v1/runs | ندارد | انتخاب run و dataset |
| /api/v1/evaluation | run, dataset | metrics، curves، مقایسه، ریسک unavailable، provenance |
| /api/v1/decisions | run,dataset,arm,offset=0,limit=25,action=ALL | timeline و drill-down |
| /api/v1/orders | همان query | سفارش و fills ثبت‌شده own-ledger |

run یک شناسه catalog مثل portfolio:20261022T053149Z_5868c530 است، نه path.
dataset در پاسخ runs می‌آید؛ هیچ path یا SQL ورودی پذیرفته نیست. limit=1…100،
offset=0…5000، action=ALL/WAIT/ENTER/EXIT؛ query تکراری/اضافی رد می‌شود.
فیلتر نماد در UI صریحاً فقط صفحه فعلی است. تطبیق decision→order فقط client_id
واقعی؛ timestamp برای اتصال حدس زده نمی‌شود. artifactهای قدیمی بدون این ID
در جزئیات UNAVAILABLE دارند. fillها بر fill_id یکتا می‌شوند؛ تعارض ID خطاست.

Envelope: schema_version=royin.monitor.v1، source، evidence_kind، run_id، revision،
sha256، observed_at، received_at، status، warnings. فیلد مفقود null است؛ زمان
mtime به زمان مشاهده تبدیل نمی‌شود. sha256 محاسبه byteهای manifest موجود است،
به معنی پذیرش protocol یا تطبیق کد جاری نیست. revision فقط اگر ثبت شده باشد.
sourceهای تو در تو envelope مستقل دارند؛ overview زمان فعلی سرور را جدا می‌دهد.

AVAILABLE داده خواندنی، EMPTY منبع معتبر با صفر رکورد، UNAVAILABLE منبع مفقود،
INVALID schema/value نامعتبر، STALE مشاهده عمومی قدیمی. research تاریخی عمداً
freshness=HISTORICAL دارد؛ تاریخ artifact نشانه heartbeat نیست. stale مشاهده
پس از دو interval همان manifest، فقط سیاست نمایشی است؛ آستانه ریسک نیست.
timestamp آینده بیش از 60 ثانیه INVALID است. وضعیت worker فقط از snapshot معتبر موتور گزارش می‌شود؛ سلامت HTTP داشبورد شاهد اجرای موتور نیست.
همه پول/قیمت/quantity/feeها decimal string هستند. پول scorecard به TMN، افت
درصد؛ base فقط برای USDTTMN، USDT است و برای نماد دیگر حدس زده نمی‌شود.
ناحیه حساب واقعی مستقل و unavailable است. موجودی منحنی فقط PAPER همان شاخه است.

## Source mapping و محدودیت

| منبع پشت API | mapping / اعتبار |
|---|---|
| artifacts/portfolio-ai/*/manifest.json | arms، equity_curve، decision_traces، orders، fills؛ SYNTHETIC/FAKE صریح |
| artifacts/evaluation/*/manifest.json | results[dataset].scorecard؛ baseline تاریخی، نبود curve/trace=unavailable |
| data/shadow/*/shadow_manifest.json | فقط mode=OBSERVE_ONLY و PUBLIC_FEED_DIAGNOSTIC؛ آخرین ذخیره، نه worker |
| همان run، audit/audit_trail.jsonl | فقط چهار event مشاهده عمومی؛ payload خام، FILL و INTENT صادر نمی‌شوند |
| data/llm-budget.sqlite3 | SELECT محدود model_reservations؛ رزرو USD/token/count، نه usage/invoice |
| research/execution-review-evidence.json | اصلاح مصرف SDK تاریخی، 12123/1237 در شاهد موجود؛ کلید یا حساب ندارد |
| artifacts/ai-evaluation/*/ai_evaluation_report.json | نام مدل/provider و latency snapshot تاریخی؛ نه بازده AI |

کاتالوگ حداکثر 60 manifest آخر هر خانواده؛ هر JSON حداکثر 8MiB، هر آرایه
حداکثر 5000 ردیف. cache با mtime/size و سقف 160 entry. JSONL حداکثر 64KiB tail
و 100 خط، خط آخر نیمه‌نویس حذف با warning؛ parse نامعتبر pass محسوب نمی‌شود.
هیچ artifact reference/path داخل manifest دنبال نمی‌شود. model_records خام صادر
نمی‌شود. SQLite با mode=ro، query_only، timeout=.2s، transaction خواندن، progress
budget و حداکثر 10000 reservation؛ schema جدید INVALID، busy UNAVAILABLE.
نه migration، نه journal_mode، نه کپی/backup DB. DB خصوصی حساب اصلاً خوانده نمی‌شود.

Drawdown منحنی با Decimal سمت سرور از peak همان منحنی محاسبه و string می‌شود؛
max_drawdown_pct scorecard جدا، با تعریف اصلی آن است. free/locked و unrealized
فقط اگر در آخرین نقطه موجود باشند. در نمودار JS فقط مختصات pixel محاسبه می‌شود.
مقایسه اصلی تنها داخل یک manifest/dataset با benchmark_contract، execution_model،
drawdown_basis، سرمایه آغاز و grid زمانی یکسان فعال است. این صرفاً قرارداد
ثبت‌شده منبع است؛ hash/freeze/protocol علیه checkout در این داشبورد revalidate
نمی‌شود. اجراهای مختلف به یک منحنی وصل نمی‌شوند. سیاست stop/kill جدید نداریم.

رکورد reason داده نامطمئن است؛ با textContent نمایش داده می‌شود. فیلدهای حساس
از ابتدا انتخاب نمی‌شوند و متن دارای الگوهای credential/URL خصوصی حذف می‌شود؛
این پالایش تضمین تشخیص هر Secret دلخواه نیست. exporter آینده باید sanitized باشد.
لاگ request، traceback، account ID، header، URL خصوصی و .env وارد API نمی‌شوند.

## اتصال فعلی موتور و حساب

Sources، فایل `.local/dashboard/engine-snapshot.json` صادرشده توسط موتور را برای run،
heartbeat، worker_state و موجودی چنددارایی می‌خواند. `data/private/probe-report.json`
در صورت وجود، snapshot خواندنی حساب را جدا فراهم می‌کند. این خواندن فایل است، نه
اتصال خصوصی مستقیم به صرافی یا streaming موجودی. نبود/خرابی منبع unavailable/invalid
است؛ label خوداظهاری snapshot، تأیید مستقل صرافی نیست.

اگر منبع paper جایگزین نمایش account شود، evidence_kind آن باید PAPER بماند؛ آن را
موجودی واقعی معرفی نکنید. route ثبت/لغو سفارش وجود ندارد و worker از سلامت HTTP
داشبورد نتیجه نمی‌شود. قرارداد schema در [ENGINE-CONTRACT](ENGINE-CONTRACT.md) و
وضعیت واقعی اجرای فعال در [وضعیت موتور](../docs/current-market-readiness.md) است.

آزمون رابط/منابع، تأیید live، invoice یا سود استراتژی نیست. screenshot و گزارش محلی
جای سنجش از همان source/config/run را نمی‌گیرند.
