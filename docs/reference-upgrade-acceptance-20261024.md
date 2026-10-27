# اعتبارسنجی ارتقای مبتنی بر مراجع — ۲۴ اکتبر ۲۰۲۶

## وضعیت تازه پس از اصلاح SDK و lot — ۱۸:۴۶UTC

بخش‌های بعدی snapshot فاز anchor هستند. نسخهٔ واقعاً فعال اکنون **`85fcf5dc2820794ee38ffe07677f09eaab59ba01`**، source binding **`542d9fef199a08c71b30b17934f95467c16e4eb3e33ab061245289de18e91bf3`** و ZIP SHA **`2aed5e20329baa37770e22dd509f8adcb7b7e314013a8a595afc74713da9d8da`** است. نوع همچنان `CONTENT_HASH_NOT_GIT_COMMIT` است؛ HEAD گیت قبلی حفظ شد و commit/push انجام نشد.

چرخه‌های۹۵/۹۶ به۹کاندیدای معتبر رسیدند، اما درخواست دوم به حد اندازهٔ ورودی خورد؛ این WAIT فنی و پیام عمومی بودجه، تصمیم نهایی مدل یا تمام‌شدن اعتبار نبود. projection نسخه‌دار ابزار، trace کامل و hashها را حفظ و درخواست SDK ثبت‌شده را از۵۵٬۱۲۸ به۲۹٬۰۱۰بایت کم کرد؛ fixture۹/۱۰با lot-fit تازه۲۸٬۷۵۲/۳۰٬۳۵۴بایت شدند، با حد۳۱٬۷۴۴بایتِ دست‌نخورده. تست‌ها SDK واقعی روی MockTransport و بودجهٔ جدا دارند، نه HTTP پولی.

lot-fit فقط مقدار را در حداکثر۲۵۶گام کاهش می‌دهد و چهار سناریوی fee/minimum/residual را حفظ می‌کند؛ BTC۶۹۴→۶۶۸lot شاهد عددی است، نه سفارش واقعی. کف پژوهش مدل۱۰۰هزار شد تا metadata۵۰هزار قرارداد میزبان را پایین نیاورد. آخرین book نیز پیش از POST امکان فروش پس از fee را در قیمت محافظه‌کارانه دوباره بررسی می‌کند؛ هدف خوش‌بینانه نمی‌تواند موجودی زیر minNotional را پنهان کند. جزئیات و تصمیم حفظ سقف۱۵۰هزار برای اولین اجرای واقعی در [بررسی ظرفیت سرمایه](capital-capacity-audit-20261024.md) آمده است.

آخرین مجموعهٔ کامل روی همین source: **۵۵۳ تست هسته، PASS در۶۳٫۱۳۷ثانیه**؛ ۲۷تست داشبورد قبلاً برای backend فعلی PASS و پس از آن source داشبورد تغییر نکرد. Ruff/compileall/diff و oracleهای دستی/config پاس‌اند. هر۷۰فایل و import root واقعی روی سرور تطبیق داده شدند. source و کلید/بودجه افزایش یا reset نشدند.

backup سازگار و هویت اصلی در `/state/upgrades/reference-dossier-20261024` است. پیش از activation، تمام جدول‌های financial/signals/budget/historical و manifest برابر بودند، جز append receipt منبع. **۹۶trace،۴۲۵رزرو،۲۹scope، anchor/count/coverage و cadence1792867288** حفظ شدند. این بار توقف graceful واقعاً `PAUSED_RESTART` ثبت شد؛ برخلاف توقف‌های قدیمی، چیزی جعل نشد. receipt انتقال منبع **`943876a132d604a9c50259d8283f61f1e2903c2c65ee835c9a6a7fd0c87e445a`** و backup receipt **`f1204930f2c19075567154f5ea4d47d00baf00e125840453fe907071e8575729`** است.

انتقال source یک timeout مشاهده داشت؛ بررسی اول هنوز artifact را ندید، قفل انحصاری آزاد بود. تلاش source-only با همان revision در صورت وجود پوشه با `FileExistsError` متوقف می‌شود و چیزی overwrite نمی‌کند؛ readback نهایی completion receipt و هر۷۰hash را تأیید کرد. هیچ POST مالی retry نشد. پوشهٔ source فقط خواندنی و image/دیسک/permit/کلید قبلی حفظ‌اند.

Publisher منفرد با همان source/settings و بدون environment مالی پس از restart بازیابی شد. ظاهر داشبورد تغییر نکرد. چرخهٔ نخست نسخهٔ جدید در مشاهده۱۸:۴۶:۳۰UTC شروع شده بود؛ تا آن لحظه۹۶trace،صفرسفارش/fill و۴M TMN در ledger تخصیص‌یافته وجود داشت. نتیجهٔ کامل مدل/مالی باید از receipt پس از پایان چرخه خوانده شود.

## نتیجه و مرز شواهد

### چرخهٔ واقعیِ کامل پس از استقرار — مشاهده۱۸:۵۱:۱۸UTC

چرخهٔ۹۷ در۱۸:۴۷:۱۰UTC با `MODEL_DECISION/WAIT` و بدون خطای validation یا runtime کامل شد. BoxAPI/gpt-6-luna دو پاسخHTTP200 داد؛ بدنهٔ دو درخواست۹۲۲۳ و۲۹۴۹۷بایت بود و ابزار واقعاً projection نسخه‌دار جدید را فرستاد. snapshot اصلی و زمان صدور موجودند، ۹کاندیدای معتبر structure/cost/capacity دارند و خطای پژوهش خالی است. SDK مصرف۱۱٬۸۲۱input و۶۲۶output token گزارش کرد؛ این صورتحساب provider نیست.

هش role با همان الگوریتم `source_bundle_sha256(src/royin/*.py,scripts/*.py,requirements.lock)` تطبیق داده شد. full runtime binding علاوه بر آن budget policy را دارد؛ این دو خانوادهٔ hash یکسان نیستند. reader تشخیصی اولیه به‌اشتباه hash خام ماژول‌ها را مقایسه کرده بود؛ source runtime تغییر نکرد، receipt اصلاح‌شده در `first-production-cycle-validated.json` نگه‌داری و reader اولیه جدا حفظ شد.

BTC با quantity۰٫۰۰۰۰۰۶۶۸، ظرفیت `SELLABLE_WITH_BOUNDED_RESIDUAL` داشت؛ هشت کاندیدای دیگر زیر قرارداد فعلی capacity مسدود بودند. مدل ضعف شواهد روند/بازده و هزینه را دلیل WAIT دانست؛ رشد مشاهده‌شده را پیش‌بینی سود یا probability ننامید. این مشاهده، امکان پژوهش و تصمیم واقعی پس از اصلاح را تأیید می‌کند و انتخاب بازار بهینه یا سودآوری را ثابت نمی‌کند.

مشاهدهٔ خصوصیِ hash-verified در۱۸:۴۶:۲۷UTC، حساب را با **۵٬۰۰۰٬۰۰۰TMN آزاد، صفر قفل و صفر non-TMN** نشان داد؛ ledger تخصیص‌یافته۴M و بیرون آن۱M طبق اجازهٔ اصلی حفظ‌اند. دفترکل واقعی تا مشاهدهٔ نهایی **صفر سفارش و صفر fill** دارد. بنابراین شرط «اولین خرید/خروج کامل واقعی» هنوز **UNCONFIRMED** است. receiptها در پوشهٔ backup همین فازند و rawها/کلیدها وارد Git نشدند.

۳۱ مخزن یکتای فهرست کاربر در سه بررسی موازی، با SHA ثابت و دامنهٔ source مشخص بررسی شدند. گزارش تفصیلیِ پیاده‌سازی، اتصال واقعی، الگوریتم، ریسک، تست‌های خوانده‌شده و محدودیت هر مخزن در [ممیزی مراجع](reference-project-audit-20261024.md) است. کد یا تست ثالث اجرا و سود آن‌ها تأیید نشد؛ کد ثالث به موتور کپی نشده است.

این فاز قابلیت‌های علّی و تشخیصی و صحت حسابداری را ارتقا داد. برتری سود، alpha خارج از نمونه یا fill واقعی از تعداد تست یا استقرار استنتاج نمی‌شود. وضعیت سفارشِ آخرین چرخه، جداگانه در انتهای همین گزارش ثبت می‌شود.

## پیاده‌سازی انجام‌شده

| تغییر | فایل‌های اصلی | علت و معیار پذیرش |
|---|---|---|
| ساختار کندل بسته، کانال prior-only، reclaim/breakout، بازده افق‌های واقعی، efficiency و حجم نسبت به ۲۰ کندل پیشین | `src/royin/features.py`, `src/royin/agent.py` | حذف trigger از مرجع، حفظ cutoff و hash؛ future-prefix invariance و صفر حجم |
| پروندهٔ هزینه و ظرفیت پیش از تصمیم AI | `risk.py`, `decision.py`, `agent.py`, `scripts/run_paper_trader.py`, `run_market_paper.py` | close اصلی، ask gap، fee/spread/slip و min/step/residual؛ تخمین پژوهشی از گیت واقعی تفکیک شده |
| ارزیابی متناسب با setup و central forecast | `agent.py` | confidence به احتمال برد تبدیل نمی‌شود؛ WAIT/ENTER را مدل انتخاب می‌کند؛ هدف برای عبور از گیت ساخته نمی‌شود |
| ذخیرهٔ snapshot اصلی و زمان صدور، سنجش بازهٔ صریح trace | `scripts/run_fresh_service.py`, `score_market_forecast.py` | اصل manifest/indices حفظ؛ زمان یا snapshot مفقود گذشته بازسازی نمی‌شود |
| reserve کارمزد فروش در base و پیش‌بینی چهار حالت fee | `run_fresh_service.py`, `risk.py` | cash، cost basis و PnL دقیق با خروج واقعیِ شبیه‌سازی‌شده و restart |
| residual محدود با proof معاملات اصلی | `src/royin/residuals.py`, `fresh_mission.py`, `runtime_release.py` | فقط append metadata/audit؛ بدون تغییر موجودی، fill، PnL یا شمار round-trip؛ UNKNOWN یا tamper رد می‌شود |
| residual داخل بودجهٔ زیان برنامه‌ریزی‌شده | `risk.py`, `fresh_mission.py`, `run_fresh_service.py` | پیش از HTTP، `debit × loss_fraction + 500 ≤ total_risk_budget`؛ بودجهٔ مصرف‌شده، cap صفر می‌دهد |
| anchor دسترسی به دادهٔ معتبر | `run_market_paper.py` | همان سه تلاش و همان scan/gates؛ fallback به دو فرصت coverage؛ شمارنده/anchor پس از restart محفوظ؛ انتخاب سرمایه‌گذاری همچنان با مدل |
| حفظ residual در انتقال backend مانیتور | `dashboard/monitor_snapshot.py` | publisher و server هر دو هشدار non-TMN و basis را نگه می‌دارند؛ ظاهر/assetها تغییر نکردند |

## آزمون‌ها

- **۵۳۷ تست هسته** در **۶۲٫۳۷۱ ثانیه**، PASS. آخرین log محلی: `.local/review/reference-anchor-core-tests.log`.
- **۲۷ تست داشبورد** برای همین تغییرات backend، PASS؛ پس از آن کد داشبورد تغییر نکرد.
- Ruff روی `src scripts tests dashboard`، compileall و `git diff --check`، PASS.
- چهار oracle دستی `scripts.run_market_paper --self-check`، `PASS_FUNCTIONAL_PAPER`؛ اجرای مصنوعی و بدون مدل/سفارش واقعی.
- `python -m royin check-config --env-file .env.example`، `VALID_CONFIG_ONLY`، shadow، network/trading false. این CLI اثبات live نیست.
- regressionها: علت/هش داده، هزینه با fee base/quote و rounding، restart و duplicate fill، UNKNOWN و tamper residual، حفظ منبع/بودجه/cadence، bootstrap anchor/fallback و بودجهٔ واقعی زیان شامل residual.
- آزمون مرورگر واقعی داشبورد عمومی در عرض‌های ۱۴۴۰ و ۳۹۰، font/control/focus و نبود overflow یا page error، PASS. این شواهد، تست روی تمام گوشی‌ها نیست.

## منبع واقعاً مستقر و حفظ state

نسخهٔ فعلی **`bf672b47970916d2aac5bb8a126a5e8ac0d85936`** از نوع `CONTENT_HASH_NOT_GIT_COMMIT` است. این شناسه، commit جدید نیست. HEAD گیت **`693f1f491a8a75c3b623899910defec489ce93ee`** حفظ شده؛ commit/push انجام نشد.

- Source binding: `1bd5bc18838024ee23b6f60286b62f0388731b21892482c4567915580d4b21b1`
- ZIP SHA256: `bff1d708a118747c080c0d0a1a27e27b3ffe8ad0dfc26e5873a2eed3c88c886a`
- **۷۰ فایل واقعی و import rootها** روی لیارا با manifest تطبیق داده شدند. پوشهٔ release فقط خواندنی است؛ source فعال hot-edit نشد.
- همان برنامه، image وابستگیِ آزموده‌شده، یک worker، UID10001، دیسک `/state`، mission `fresh_live_20261023_9` و service `svc_live_20261023_9` ادامه یافتند.
- تمام **۲۷ متغیر محیطی** حفظ شدند؛ فقط maintenance، revision و مسیر source برای انتقال تغییر کردند. کلید یا state در artifact/build context قرار نگرفت.
- backup سازگار financial/signals/budget/historical و manifest، در `/state/upgrades/reference-anchor-20261024` محفوظ‌اند. تمام جدول‌های قبلی پیش از activation برابر بودند؛ تنها receipt منبع به metadata اضافه شد.
- **۹۴ trace، ۴۲۳ رزرو مدل، ۲۹ scope، journal، permit/config، transport، coverage، bootstrap counts و `next_entry_analysis_at=1792865326`** حفظ شدند. restart حق درخواست یا سرمایهٔ تازه ایجاد نکرد.
- رخداد قدیمی UNKNOWN/reserve/counter8 و SHA بایتی `8bcb1259e6a633693fcf7cb6a598edc230c3eed1f44e6f62cf6bca089ad8c524` تغییر نکردند. lane جدید، finality تاریخی جعلی ثبت نمی‌کند.
- receipt انتقال: `ee2cd716f6bf211400d7f40b136c95fed0f59cb9469137914c054da47174bbef`؛ backup receipt: `11c06c7dbd542e31ddedc86d1d4ace2d4abe28e8c145b434652fe8bd42dd2b29`.

لیارا توقف graceful را در metadata قدیمی ثبت نکرد؛ `RUNNING` قدیمی بازنویسی نشد. پایان container و مالکیت انحصاریِ آزاد، با receipt quiescence مستقل ثبت شدند. یک timeout انتقال artifact رخ داد؛ پیش از هر اقدام بعدی، وجود receipt و تطبیق هر ۷۰ فایل با readback تأیید شد. انتقال کورکورانه تکرار نشد.

## مانیتور مستقل

[داشبورد عمومی](https://royin-monitor.liara.run/) همچنان برنامه‌ای مستقل با Basic authentication و انتشار HMAC دارد. source مانیتور `6adcec8c8bb90de865b6bf39` و ۱۶ فایل واقعی آن بررسی شده‌اند؛ کلید مالی در محیط آن نیست. publisher منفرد از پوشهٔ immutable `eb0596fe74a5d2cb4ecf788ec65e51a4f8b3143e9b36491367aa55a0579e089d` و همان settings ادامه یافت. پس از restart موتور، publisher با PID22 و UID10001، حدود ۲۸MiB RSS، accepted=true و بدون environment مالی تأیید شد؛ PID متن ثابت و تضمین آینده نیست.

HTML/JS/CSS و فونت‌ها تغییر نکردند. SHA سه asset اصلی:

- HTML: `e7d8491c27e30f40369e75ba42dc2e9e1e7b8aefaa71581c8da5db2966e4fbf0`
- JS: `d3162f5da602249b29f554f401c4384b5f44f335592646a51d2bb800658b06db`
- CSS: `64221491d845abd02f9729893564ffaa73eceec35a68556fc6c6d412a26620eb`

readback عمومی `/healthz` و `/readyz` موتور، هر دو HTTP200 و `LIVE_BOUNDED/RUNNING` با heartbeat تازه داشت. این‌ها شاهد در دسترس بودن سرویس‌اند، نه موفقیت سفارش. publisher با restart خود موتور از بین می‌رود و باید همان تک‌ناشر دوباره برقرار شود؛ restart مانیتور در push بعدی بازیابی می‌شود و دادهٔ stale صریح است.

## ارزیابی مالی و کار باقی‌مانده

تا snapshot پیش از چرخهٔ تازه، **صفر سفارش و صفر fill واقعی** ثبت شده است. سه ENTER تاریخی به خطای integration پیش از POST خورده بودند؛ `params` اجباریِ فراموش‌شده قبلاً اصلاح و regression آن حفظ شده است. WAIT واقعی مدل، fallback/ValueErrorِ شواهد نامعتبر و `NO_CANDIDATE` پیش از مدل، جدا ثبت می‌شوند. چرخه‌های ۹۳ و ۹۴ِ artifact قبلی، نمونهٔ دستهٔ سوم‌اند؛ سود یا موفقیت AI نامیده نمی‌شوند.

بررسی ۲۸۶ کاندیدای تاریخی و سه ENTER صرفاً تشخیص هزینه بود؛ به‌علت provenance ناکافی و نبود outcome/fill، backtest پذیرفته‌شده یا alpha نیست. ارتقای جدید هنوز مقایسهٔ prospective و خارج از نمونه در برابر cash/hold/rule با هزینه و زمان یکسان ندارد. اولویت بعد، ارزیابی چرخهٔ واقعی عادی و سپس سنجش forecastهای موعدرسیده با manifest منجمد است.

residual همچنان دارایی کوینی واقعی است، cash یا round-trip کامل نیست. ورود بزرگ‌تر پس از شاهد واقعیِ بسته‌شدن کامل ممکن می‌شود؛ reserve ممکن است bootstrap۱۵۰k را نگه دارد. سقف هشت residual محدود است و ارزش تجمیعی تاریخی، تضمین ارزش جاری نیست. Finalization با non-TMN هنوز `STOPPED_OPEN_RECONCILIATION_REQUIRED` است. سود، تکمیل تسویه یا کار بی‌خطا تا دوشنبه تضمین نشده است.
