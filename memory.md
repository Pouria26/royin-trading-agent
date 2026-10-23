# حافظهٔ فنی پایدار

فقط قرارداد، خطای تکرارشونده و تصمیم مؤثر بر اجرا در این فایل ثبت شود؛ لاگ جلسه، نام افراد، کلید و گزارش‌های طولانی در آن نیست. نسخه‌های قبلی در آرشیو محلی و تاریخچهٔ Git حفظ شده‌اند.

## قراردادهای معتبر — 2026-10-23

- انتقال میزبان: نبود فرایند محلی یا گذشت زمان، پایان اجرای میزبان دیگر نیست. source main حفظ شد؛ نامزد آفلاین08f403c تا terminal/مالکیت معتبر ادغام نمی‌شود. منبع: بررسیGit/process/نبودartifacts وhashبرابر در۲۳اکتبر۰۶:۳۷تهران؛۳۹۳هسته/۱۰داشبورد/۴self-checkنامزد پاس، نه سود/provider تازه.
- ادامهٔ درخواست پولی باید DB اصلی بودجه را با backup سازگار، schema و prior reservations معتبر داشته باشد؛ نبود state مصرف صفر نیست. نامزد باSQLite mode=rw وگاردمرزشبکه آن را enforceمی‌کند؛ bootstrapآزمون مصنوعی مجوزHTTPواقعی ندارد. intent/reserve/۸attemptcanary قبلی resetنشوند.
- بازپخش ثبت‌شده، inference تازه یا بازسازی کامل بازار نیست. نامزد journal/input-state را از validator/binder/Ledger عبور می‌دهد؛ artifact قدیمی ناقصPARTIAL وexecutionUNCONFIRMEDمی‌ماند. منبع: تست مصنوعی مستقلpartial/basefee/cancel،بدونHTTP.

- هدف، موتور واقعی برای بازارهای مجاز اسپات است؛ paper و تست زیرساخت پایان کار نیستند. تضمین سود یا نمره نداریم. بریف، سیاست بازار، وضعیت جاری و تسک‌ها مرجع‌اند.
- مدل دو نقش Entry Analyst/Position Reviewer دارد. host مالک پول/سایز/stop/deadline/مجوز است. read_market_snapshot فقط دادهٔ خواندنی می‌دهد؛ snapshot/evidence/schema-valid مجوز معامله نیست.
- انتخاب بازار به یک نماد یا shortlist ثابت محدود نیست. مدل فهرست نقدشوندهٔ واجد شرایط را می‌بیند و۱..۵ نماد را بررسی می‌کند. bootstrap یک ابزار آماده‌سازی داده است و توصیهٔ سرمایه‌گذاری نیست.
- USDTTMN خراب/کم‌فعال قبلاً کل تحلیل را می‌بست. source3799e4a حداکثر۳ seed نقدشونده را امتحان و خرابی را فقط برای cutoff جاری ثبت می‌کند؛ gap همچنان رد می‌شود. نداشتن trade اخیر یک بازار، توقف کل صرافی نیست.
- hash، source/config/prompt/model/cutoff و پاسخ واقعی حفظ شوند. src/scripts/config هنگام اجرای منجمد تغییر نکنند؛ تغییر source نیازمند run تازه است. timeout مشاهده، شاهد مرگ فرایند نیست.
- صدور از کندل بسته و زمان آیندهٔ outcome جداست. timestamp آغاز کندل/finality منبع هنوز فرض تشخیصی دارد. gap، دادهٔ آینده، forward-fill پنهان و حذف زیان ممنوع. سپتامبر۲۴–۲۷ diagnostic مصرف شده؛ holdout نیست. N≥30 قانون رسمی نیست.
- قیمت/پول/fee با Decimal. SUM ممیزشناور SQLite برای پول استفاده نشود. دارایی مثبتِ بدون قیمت معتبر خطاست، نه صفر. stepSize/tickSize عمومی تعداد اعشارند؛ minNotional مشاهده‌شدهٔ USDTTMN۵۰k بود، نه حد ثابت همهٔ بازارها.
- forecast افق terminal از cutoff دارد؛ protection باید در cutoff+horizon تمام شود، نه submit_time+horizon. checkpoint اجبار خروج نیست؛ stop/high-water پایدار و مستقل از LLM است. قطعی اینترنت اجرای قیمت stop را تضمین نمی‌کند.
- بودجهٔ BoxAPI با صورتحساب فرق دارد. policy v3، input/output۳۲۷۶۸/۱۰۲۴؛ scope جدید۴۸ نقش/۹۶HTTP/USD0.50، global۲.۴۰/روزانه۰.۸۰؛ scope قدیمی cap خودش را حفظ می‌کند. ledger بودجه reset/refund خودکار ندارد.
- current REAL_MODEL در برابر fake صریح باشد. چند پیش‌بینی واقعیِ قبلی از baseline صفر ضعیف‌تر بودند؛ WAIT forecast، fill یا نرخ برد نیست. پوشش چند بازهٔ عریض، کالیبراسیون نیست؛ interval baseline روی outcomes ارزیابی fit نشود.
- حساب اعتباری مشاهده‌شده۵M cash آزاد و تاریخچهٔ سفارش خالی داشت، اما canary اصلی BUY_UNKNOWN باقی است. کلید جایگزین از حساب اعتباری و دارای مجوز معامله طبق تأیید کاربر است؛ این سؤال تکرار نشود. علت POST خالی به دلیل status مفقود ثابت نیست.
- intent، reserve و۸attempt اصلی حساب را حفظ کنید؛ retry با ID/DB تازه برای دور زدن UNKNOWN ممنوع. state و قفل حساب در home مشترک بین cloneهای همان میزبان‌اند؛ دو دستگاه قفل مشترک ندارند. [قرارداد مالی](docs/credit-canary.md) مرجع است.
- تست‌های۳۶۰تایی source3799e4a، صحت قراردادهای آزموده را نشان می‌دهند؛ coverage۱۰۰٪، alpha یا production readiness را ثابت نمی‌کنند. core و dashboard جدا گزارش شوند.

## پیگیری فعال

2026-10-23 / تحویل a76a420: علت نبود خرید را در سه دسته جدا بررسی کن: WAITواقعی مدل، fallbackفنی، و مسدودبودن transportمالی. snapshot23:50UTCاجرای main۱۵تصمیم (۱۱معتبر/۴fallback)،۹نماد درخواستی متمایز و۶contextمعتبر متمایز،۰سفارش داشت. دلیل WAITها بازارنزولی/هزینه/نبود شاهد >۲٪بود، نه اثبات نبود فرصت در تمامcatalog. نامزد۳۷۳هسته/۱۰داشبورد پاس؛ providerورود درنسخهٔقبلی آزموده شد، خروج مدل واقعی درموقعیت باز هنوز نه. به درخواست محدودیت توکن و انتقال، پایلوت پولی تازه شروع نشد.

2026-10-23 / آزمون providerنامزد dacb5a6: مدل واقعی۱۰نماد خواست و۸داده معتبر پذیرفت،۲HTTP/۲۱GET و۳۵٫۳۲۸ثانیه، evidence/batch/provider/hashمعتبر. مهلت۶۰ثانیهٔ پژوهش در این نمونه کار کرد؛ مقایسهٔ کنترل‌شدهٔ latency نیست. این diagnosticبا remaining_seconds=0،بدون سفارش/افق ورود بود؛ alphaیا fundedforward نیست. budgetهمان فایل اصلی و رزروUSD0.00871424بود،نه invoice؛ main/sourceاجرای قبلی تغییر نکرد. جزئیات در docs/current-market-readiness.md.

2026-10-23: طبق دستور تازه، PR قبلی روی main ادغام و شاخهٔ remote حذف شد؛ ادامه روی main و شاخهٔ بعدی بدون پیشوند codex. HANDOFF.md انتقال خودبسنده است؛ شواهد زمان‌دار آن باید بازبینی شوند. تغییر MD منبع3799e4a اجرای فعال را تغییر نداد.

سنجش23:11UTC از کپی بایتی ثابت manifest،۱GET و۱outcomeاز۵forecast (۴pending) داد. USOON30min با q50−۰٫۴٪، outcome−۰٫۰۵۳۲۵٪ و point error بیشتر ازصفر؛ جهت درست مزیت مقدار را ثابت نکرد. گزارش ignored در artifacts/forecast-outcomes/20261022T231125Z_142a366e/report.json. سنجش manifest فعال باید روی کپی ثابت باشد تا sourcehash حین درخواست عوض نشود.

گزارش تاریخی superseded از وضعیت جاری: `net-return-forward-20261023-2` از source3799e4a در حال آزمون۳ساعته ثبت شده بود؛ handle و PID محلی در `.local/review/market-readiness/active-forward-process.json` ثبت‌اند. snapshot RUNNING به‌تنهایی کافی نیست. آخرین checkpoint و نتیجهٔ نهایی از فرایند/manifest واقعی بررسی شوند. پس از پایان، بررسی executable bid/ask در برابر close، خطاهای مدل، outcome و گیت مالی ادامه دارد.

2026-10-23: مستندات فعال از۳۲به۱۸Markdown تلخیص شدند. گزارش مرحله/Blueprint محلی آرشیو است؛ clone همکاران به آن وابسته نیست. قرارداد داده، canary و scorer در Git باقی‌اند. لینک‌های داخلی و hash آرشیو بررسی شدند؛ گزارش قدیمی fake با سود AI جاری یکی نشود.
