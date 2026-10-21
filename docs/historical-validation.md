# اعتبار تاریخی — شواهد ناکافی برای انتقال نامزد

**نتیجه: `INSUFFICIENT_EVIDENCE` / `BLOCKED_DATA`.** هیچ نامزد به Shadow واقعی منتقل نشد. صحت محدود آزمون‌های آفلاین، سود پایدار یا آمادگی Live نیست. این گزارش ادعاهای قبلی «کامل/نهادی»، Shadow جاری، هشت smoke تجمیعی و actual بودن هزینه رزروشده را supersede می‌کند؛ فایل‌های شواهد قدیمی حفظ شده‌اند.

## اصلاحات و قرارداد اجرا

- LIMIT در قیمت limit پر می‌شود؛ افزایش slippage برای آن price improvement ایجاد نمی‌کند. touch همراه با حجم کافی هنوز فرض fill است، نه اثبات صف. penetration/no-fill/تأخیر، stress مستقل‌اند. Market خروج/stop اصطکاک نامساعد دارد؛ همه fills با taker گزارش‌شده حساب (`.003`) محاسبه می‌شوند، نه maker صرفاً به علت limit بودن.
- فقط کندلی که `open_time >= created_at` دارد قابل match است. تأخیر پیش‌فرض ده ثانیه حفظ شده؛ کندل آغازشده پیش از دسترس‌پذیری سفارش حذف می‌شود. ورود و stop در یک کندل بدبینانه، stop پیش از limit exit مبهم، و خروج در low منهای اصطکاک فرض شده‌اند؛ تضمین اجرای واقعی نیستند.
- ledger هنگام ثبت fill، status متناظر broker را در همان تراکنش به‌روز می‌کند. restore به ledger رجوع می‌کند؛ fill جزئی فقط با مقدار باقی‌مانده ادامه می‌یابد. fee فروش در دارایی پایه، موجودی و basis را مصرف می‌کند. سفارش معلق ورود/خروج بعدی را می‌بندد؛ stop مستقل می‌ماند. این آزمون‌ها تمام مرزهای crash/دیسک/صرافی واقعی را اثبات نمی‌کنند.
- trade یک episode از inventory صفر تا صفر است؛ partial exit یک round-trip جدا نیست. PF بدون زیان و سنجه نمونه صفر null/status دارند. realized، cash، MTM، residual/basis، تعداد سفارش/fill/round-trip و exposure جدا گزارش می‌شوند. fee دوباره از PnL خالص کم نمی‌شود. DD فقط نقاط close و خروج نهایی شامل fee را می‌بیند؛ intrabar DD نیست.
- passive buy-once بدون stop/reentry، از hold با risk مشترک جداست. سرمایه آغاز و سقف تخصیص یکسان‌اند؛ passive همان ریسک stop را ندارد و بازده پوزیشن با بازده کل حساب یکی نیست. thresholdهای baseline قدیمی کالیبره نشده‌اند؛ ATR جهت یا edge نیست.
- production در `decide` کلاینت HTTP و ModelBudget خود را دارد؛ تزریق network client یا Agent تولیدی رد می‌شود. MockTransport بدون mount و TestModel/FunctionModel صرفاً برای آزمون آفلاین‌اند. بودجه/دفتر reset یا refund نشده‌اند.

## داده و پروتکل

`config/evaluation-datasets.json` تنها ورودی پذیرش CLI است: status/hash/symbol/interval/bounds/metadata باید تطبیق کنند. REJECTED وارد ranking نمی‌شود و داده اقتصادی یکسان با provenance متفاوت دوباره شمرده نمی‌شود. چهار فایل قدیمی شامل BTC/ETH ردشده و دو نسخه USDT بودند؛ تنها hash پذیرفته USDT در T02 مصرف می‌شود. هفته اکتبر۱–۸ **development-only** و مبتنی بر پذیرش محدود T02 است؛ cross-check native آن فقط روز اول را پوشش می‌داد، نه پروتکل سخت‌گیرانه جدید برای تمام روزها.

پروتکل پیش از دریافت تازه، در `2026-10-21T19:58:47.598019+00:00` با hash زیر freeze شد:

```text
c69b427581ebd640122cc7d327f04d356671270e01e8f156e42ba03b53d3eb83
```

فقط USDTTMN به دلیل کیفیت قبلی انتخاب شد؛ account-specific access تازه تأیید نشده است. سپتامبر۱۵–۲۱ توسعه (دو پنجره۷۲ساعته)، ۲۱–۲۴ validation و ۲۴–۲۷ holdout با یک روز warmup پیشین برنامه‌ریزی شدند. شش configuration از دو خانواده در پروتکل فهرست شده‌اند؛ **هیچ‌یک جست‌وجو نشدند** چون داده گیت را رد کرد. holdout برای بازده باز نشد؛ inspection کیفیت داده با استفاده آن در انتخاب استراتژی متفاوت است.

از سقف ۲۷ GET، **۲۵ GET واقعی، صفر retry** انجام شد. از ۱۳ روز، فقط سپتامبر۱۷ و۱۸ پذیرفته شدند. هفت روز مجموعاً ۱۵ ساعت OHLCV ناسازگار داشتند؛ سپتامبر۲۲ هشتاد دقیقه و سپتامبر۲۶ یک دقیقه کم داشتند؛ دو روز خطای شبکه داشتند. بنابراین هیچ پنجره کامل۷۲ساعته با warmup معتبر وجود ندارد. علت اختلاف native/minute حل نشده و hypothesis باقی است؛ مرجع دلخواه برای سبزشدن انتخاب نشد. snapshot ممنوع‌ها دست‌نخورده ماند.

raw/query/fetch time/hash محلی ثبت‌اند؛ hash دقیق فایل collector هنگام capture اولیه dirty ثبت نشده بود. این ضعف صریح provenance است: آن capture به commit نهایی نسبت داده نمی‌شود. سپس ۲۲ hash raw و طبقه‌بندی ۱۱ روز دارای دو پاسخ، با parser نهایی آفلاین دوباره بررسی و همسان شدند؛ دو خطای شبکه قابل replay نبودند. collector اکنون hash فایل و revision/dirty را برای اجرای بعدی ثبت می‌کند.

tick/step/minimum و feeAsset شبیه‌سازی **synthetic/unverified** هستند؛ fee طبق گزارش حساب کاربر سناریوی quote-fee است. min قابل خروج و expiry حساب از این اجرا تأیید نمی‌شوند. policy تاریخ پایان هر dataset با توقف ورود در یک ساعت آخر را مصرف می‌کند؛ این جای انقضای واقعی حساب مسابقه را نمی‌گیرد. پایان ثبت‌شده مسابقه `2026-10-23T23:50:00+03:30` است.

## AI و audit

چهار مسیر قدیمی baseline بدون AI هستند. مسیر recorded REAL_MODEL فقط با snapshot دقیق cash/position همان شاخه و manifest مطابق prompt/model/config/data قابل replay است؛ mismatch بسته می‌شود. منحنی کامل AI اجرا نشده و prompt فعلی نقش افزوده‌ای فراتر از تکرار قواعد را اثبات نمی‌کند. `REAL_MODEL` صرفاً برچسبی است که provenance واردشده باید آن را پشتیبانی کند؛ unit fixture مدرک فراخوان واقعی نیست.

Audit موجود اکنون مرز snapshot/host/risk/intent/fill/fee/reconciliation/stop/finalization/residual و AI request/result/error را ثبت می‌کند؛ run/sequence، زمان با offset، decision/snapshot/client/fill/position ID و hashes قابل دنبال‌کردن‌اند. JSONL با fsync، payload allowlist و خطای صریح از لاگ انسانی جداست. redaction تضمین صددرصد ندارد؛ raw response/header مجاز نیست. synthetic nested/SecretStr/URL/bearer/pipe/exception و token counter آزموده شده‌اند. یک audit آفلاین شامل rejection و fallback در شاهد محلی run-specific نگهداری شده است.

فایل smoke قبلی روی دیسک **۷ snapshot و۱۴ reservation** دارد؛ وجود هشتمین نمونه تجمیعی با این فایل اثبات نمی‌شود. ۱۲۱۸۵۶ token و حدود `.017311 USD` در فیلدهای قدیمی، **رزرو** هستند؛ actual usage/invoice آن اجرا unknown است. دفتر مشترک هنگام مشاهده ۲۶ reservation و `.03214848 USD` رزرو داشت؛ این مأموریت **صفر تصمیم/HTTP پولی و صفر رزرو جدید** داشت. باقی‌مانده محلی سقف کل `2.36785152` و سقف روز `0.76785152 USD` بود؛ موجودی provider نیست. رزروها reset/refund نشدند. تست اولیه bypass، پیش از اصلاح، یک درخواست با dummy-key ساختگی به BoxAPI فرستاد و 401 گرفت؛ کلید واقعی مصرف نشد. این تلاش unauthenticated جدا از درخواست پولی/تصمیم مدل ثبت است. تست نهایی با send spy کاملاً آفلاین است.

`scripts/shadow_cycle.py` همچنان تست مفید چهارکندلی synthetic recovery/stop است؛ feed جاری و شاهد T09 نیست. ابزار workflow خواندنی موجود حفظ شد؛ مقاله [Anthropic](https://www.anthropic.com/engineering/writing-tools-for-agents) درباره ابزار متمرکز، مشاهده این پروژه را جایگزین نمی‌کند. دریافت [مقاله overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf) timeout شد؛ ادعای مطالعه کامل آن نداریم.

## اجرای آزموده و محدودیت نتیجه

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m ruff check src scripts tests
.\.venv\Scripts\python.exe -m compileall -q src scripts tests
.\.venv\Scripts\python.exe -X utf8 scripts\run_eval.py --help
.\.venv\Scripts\python.exe -X utf8 scripts\run_eval.py --manifest config\evaluation-datasets.json --all
.\.venv\Scripts\python.exe -X utf8 -m scripts.collect_validation_data --protocol config\historical-validation-protocol.json
git diff --check
```

۱۵۲ تست پاس، صفر fail/skip؛ Ruff و compileall و help و diff check موفق. collector نتیجه BLOCKED_DATA و خروجی غیرصفر داشت؛ آن را pass حساب نمی‌کنیم. CLI ارزیابی موفق فقط baseline روی development پذیرفته‌شده ساخت. مسیر خروجی هر run جدید است و فایل قبلی overwrite نمی‌شود. [شاهد sanitized و hashها](evidence/historical-validation-2026-10-21.json) جزئیات نتایج diagnostic و sensitivity را نگه می‌دارد؛ raw، audit کامل و گزارش نهایی در artifacts/data و `.local/parallel/historical-validation-report.md` ignored هستند. تست‌ها روی dirty tree مبتنی بر f4970f3 اجرا شدند؛ hashes منبع، نسبت‌دادن نتایج به نسخه دیگر را منع می‌کنند.

هیچ live broker، سفارش/اعتبار/انتقال واقعی، UI، subagent یا framework اضافه نشد. گیت نامزد به دلیل داده، نمونه کافی، نقش افزوده AI، access/مشخصات سفارش و ریسک عددی مصوب باز نشده است. قدم بعدی واحد: **رفع معنای timestamp و اختلاف native/minute با مرجع رسمی، سپس پروتکل داده تازه و ارزیابی دوباره؛ بدون ضعیف‌کردن oracle**.
