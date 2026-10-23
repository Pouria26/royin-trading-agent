# رویین — ایجنت معاملاتی والکس

**وضعیت انتقال ۲۳ اکتبر:** source منجمد main حفظ شده و پایان/مالکیت اجرای میزبان قبلی UNCONFIRMED است. نامزد آفلاین `08f403c` با۳۹۳تست هسته پاس، هنوز ادغام یا اجرا نشده است. پیش از اجرای REAL_MODEL، DB اصلی بودجه و شواهد مالکیت باید بازیابی شوند؛ ساخت DB تازه مجاز نیست. [وضعیت و قدم بعدی](TASKS.md).


رویین برای تحلیل بازارهای مجاز اسپات والکس، انتخاب فرصت توسط مدل و مدیریت مستقل ریسک ساخته می‌شود. دو نقش مدل، تحلیل‌گر ورود و بازبین موقعیت‌اند؛ حسابداری، حجم سفارش، توقف و پایان زمان در اختیار میزبان است.

**وضعیت فعلی:** آزمون پیوسته با دادهٔ زنده و مدل واقعی در حال اجراست؛ پول آن کاغذی است. سودآوری پایدار یا آمادگی اجرای عمومی با پول واقعی تأیید نشده است. تلاش فنی قبلیِ ثبت سفارش به `BUY_UNKNOWN` رسیده؛ بررسی خواندنی اخیر هیچ سفارش و کاهش موجودی نشان نداده، اما علت پاسخ خالی آن ارسال مشخص نیست.

## از کجا شروع کنیم؟

| نیاز | مرجع |
|---|---|
| ادامهٔ کار در چت تازه و پیشینهٔ تصمیم‌ها | [هندآف کامل](HANDOFF.md)؛ وضعیت زمان‌دار آن را دوباره بررسی کنید |
| وضعیت امروز، آزمون فعال و کارهای بعدی | [وضعیت اجرا](docs/current-market-readiness.md)، [تسک‌ها](TASKS.md) |
| قوانین مسابقه و محدودیت بازار | [بریف](docs/challenge-brief.md)، [سیاست بازار](docs/market-access-policy.md) |
| توسعه و شناخت اجزا | [دستور ایجنت](AGENTS.md)، [معماری](ARCHITECTURE.md) |
| صحت داده و سنجش نتیجه | [قرارداد داده](docs/market-data-semantics.md)، [ارزیابی](docs/evaluation-plan.md)، [سنجش پیش‌بینی](docs/current-forecast-evaluation.md) |
| حساب واقعی، وضعیت UNKNOWN و بازیابی | [قرارداد حساب و اجرای مالی](docs/credit-canary.md) |
| مدل، مانیتورینگ و ارائه | [بودجه مدل](docs/boxapi-budget.md)، [داشبورد](dashboard/README.md)، [ویدئو](docs/video-presentation-plan.md) |

گزارش‌های میانی، Blueprint و نسخه‌های قبل از تلخیص در `.local/docs/` نگهداری می‌شوند؛ این پوشه ignored است و در clone همکاران وجود ندارد. قراردادها و راهنمای مورد نیاز در فایل‌های جدول بالا باقی مانده‌اند. تاریخچهٔ Git بازنویسی نشده است.

## نصب

Python 3.12 و uv؛ از ریشهٔ پروژه در PowerShell، فقط در محیط تازه:

```powershell
uv venv --python 3.12 .venv
uv pip sync --python .\.venv\Scripts\python.exe requirements.lock
uv pip install --python .\.venv\Scripts\python.exe --no-deps --editable .
```

روی محیط موجود دوباره `uv venv` نزنید. `sync` بستهٔ محلی را حذف می‌کند و نصب editable باید بعد از آن باشد. فایل `.env` محلی را بر اساس `.env.example` بسازید و فایل موجود را overwrite نکنید. نام تنظیمات در `.env.example` است؛ `.env` واقعی و کلیدها وارد Git نمی‌شوند. پیش‌فرض shadow است؛ تغییر پرچم به live، مسیر معاملاتی عمومی ایجاد نمی‌کند.

## فرمان‌های بررسی

```powershell
.\.venv\Scripts\python.exe -m royin check-config --env-file .env.example
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m unittest discover -s dashboard/tests -v
.\.venv\Scripts\python.exe -m ruff check src scripts tests dashboard
.\.venv\Scripts\python.exe -m compileall -q src scripts tests dashboard
```

`VALID_CONFIG_ONLY` فقط صحت تنظیمات را می‌سنجد؛ شاهد معامله یا سود نیست. آخرین بررسی هسته در منبع `3799e4a`: ۳۶۰ تست موفق. درصد پوشش کد اندازه‌گیری نشده است؛ تعداد تست تضمین صحت مالی در صرافی نیست.

## مشاهده و اجرای کاغذی

```powershell
.\.venv\Scripts\python.exe -X utf8 dashboard/server.py --port 8765
.\.venv\Scripts\python.exe -X utf8 scripts/run_market_paper.py --help
.\.venv\Scripts\python.exe -X utf8 scripts/run_market_paper.py --self-check
```

داشبورد در http://127.0.0.1:8765 فقط‌خواندنی است؛ نتیجهٔ کاغذی را موجودی واقعی حساب ندانید. `--self-check` آزمون مصنوعی قرارداد اجراست. برای اجرای مدل واقعی از پروتکل ثبت‌شده در [وضعیت اجرا](docs/current-market-readiness.md) استفاده کنید؛ آن فرمان هزینهٔ مدل دارد، با پول مجازی معامله می‌کند و نباید هم‌زمان با اجرای موجود تکرار شود.

هدف، بازده خالص پس از کارمزد و هزینهٔ اجراست. پیش‌بینی رشد بالای ۲٪ تضمین سود نیست و کارمزد را حذف نمی‌کند. دادهٔ ناقص، نبود فرصت و خطای مدل باید جدا گزارش شوند؛ برای امتیاز فعالیت معاملهٔ اجباری نداریم.
