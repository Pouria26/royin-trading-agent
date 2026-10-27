# اصلاح انتخاب نماد — کاندیدای آفلاین، ۲۵ اکتبر ۲۰۲۶

**وضعیت: کد اصلاح‌شده و آزموده شده؛ موتور مالی زنده تعویض نشده است.** دو فایل source محلی با artifact فعال `0d066ae7a8ccc0b476ce32079147195ce22443bf` تفاوت دارند. هیچ معامله، درخواست پولی مدل، reset، تغییر بودجه، کامیت یا deploy مالی در این فاز انجام نشد.

## علت تأییدشده

در trace اصلی index225، تصمیم `dec_0ea47fdf754c49fa` برای `XAUTTMN` از نوع WAIT بود. همان batch هشت نماد داشت؛ فقط BTC و PEPE ظرفیت اجرایی پژوهشی داشتند. XAUT در فهرست مسدودها بود.

در سورس قبلی:

- prompt انتخاب نماد feasible برای WAIT را فقط با `prefer` توصیه می‌کرد.
- schema نهایی symbol، snapshot و forecast را از تمام نمادهای پذیرفته‌شده می‌پذیرفت؛ «پذیرش داده» با «قابلیت اجرای مقدار» یکسان نبود.
- validator صحت فهرست feasible را بررسی می‌کرد، ولی WAIT روی نماد مسدود را با وجود گزینهٔ feasible رد نمی‌کرد.
- وقتی hurdle نقدی غایب بود، مقدار هزینهٔ هر واحد با نام `entry_hurdle_fraction` نمایش داده می‌شد؛ برای نماد فاقد ظرفیت، این عدد مانع نقدی قابل‌اجرای سفارش نبود.

این علت، یک نقص مشخص انتخاب/تبیین را ثابت می‌کند. وجود فرصت سودده در سایر نمادها یا غلط‌بودن تمام WAITها از آن نتیجه نمی‌شود.

## تغییر کد

`src/royin/agent.py`:

- انتخاب نهایی، snapshot، evidence و forecast در صورت وجود ظرفیت به همان مجموعهٔ feasible محدود می‌شوند؛ root و forecast enum مستقل‌اند و host هم bindingها را بررسی می‌کند.
- projection جدید `ENTRY_DOSSIER_COMPACT_V7`، ویژگی‌های جزئیِ نمادهای مسدود را از گزینه‌های نهایی جدا می‌کند. فهرست تمام acceptedها، علت مسدودی، trace کامل و hash ورودی حفظ می‌شوند.
- نبود cash hurdle با هزینهٔ هر واحد پر نمی‌شود؛ hurdle ورود null و مقدار هر واحد صرفاً diagnostic است.
- `feasible_symbols` دارای cardinality و enum دقیقِ مجموعهٔ feasible است؛ مدل نمی‌تواند گزینه‌ای از آن کم یا به آن اضافه کند.
- برای batch دارای ظرفیت معلوم ولی بدون گزینهٔ feasible، schema فقط WAIT را عرضه می‌کند.
- trace جدید `selection_diagnostic` میان نبود ظرفیت، `MODEL_WAIT_CENTRAL_NOT_ABOVE_COST` و `MODEL_WAIT_OTHER_JUDGMENT` فرق می‌گذارد. حالت آخر الزاماً خطا نیست و به ENTER تبدیل نمی‌شود.

`src/royin/decision.py`:

- validator با بازمحاسبهٔ مستقل هزینه/ظرفیت، انتخاب نماد مسدود را در حضور گزینهٔ feasible رد می‌کند؛ صرفاً به enum یا گفتهٔ مدل اعتماد نمی‌کند.
- اگر قواعد ظرفیت موجود باشد، ENTER بدون ظرفیت اثبات‌شده رد می‌شود؛ این بررسی برای batch مستقیم نیز فعال است.
- fixtureهای قدیمیِ فاقد قرارداد ظرفیت، semantics قدیمی خود را دارند؛ این مسیر قدیمی مجوز اجرای واقعی نیست. مسیر مالی همچنان به قواعد و بررسی‌های مستقل خود نیاز دارد.

سیاست q50/هزینه، اندازه، minimum، fee، residual، stop، deadline، quotas، تعداد دو HTTP/یک tool و حدود request تغییر نکرده‌اند. پیچیدگی بازبینی همان batch کران‌دار حداکثر ده نماد و محاسبهٔ مقدار با حداکثر ۲۵۶ تلاش برای هر نماد است.

## تست و مقایسه با قبل

۱۳ تست جدید در `tests/test_executable_selection.py` شامل:

- WAIT روی نماد مسدود با فهرست مقایسهٔ درست؛ ENTER مسدود با forecast مثبت؛ batch کاملاً مسدود؛ batch مستقیم.
- مسیر ENTER معتبر و رد median پایین‌تر از هزینه؛ مثبت‌کردن مصنوعی forecast انجام نمی‌شود.
- schema واقعی تولیدشده با SDK، اتصال symbol/hash/reference و حفظ فهرست acceptedها.
- پاسخ provider که enum را نادیده می‌گیرد: رد با `SELECTED_CANDIDATE_NOT_FEASIBLE`، بدون درخواست سوم یا repair پولی.
- تفکیک دلایل WAIT و حفظ داده/hash اصلی؛ cash hurdle غایب به FIT ارتقا داده نمی‌شود.

چهار regression اصلی روی کپی **سورس اصلی منجمد** هم اجرا شدند: هر چهار مورد با assertion عدم رد انتخاب نامعتبر شکست خوردند؛ روی کد جدید پاس شدند. آرشیو اصلی با SHA `734e49a2959fac5f1979bd63eda211cb9ab0e6d7cca2770820a5436c7aec21c4` و تمام ۷۲ عضو قرارداد بررسی و محفوظ ماند. فقط دو فایل runtime محلی تغییر کرده‌اند؛ تغییرات قبلی مخزن حفظ شدند.

- suite هسته: **۶۴۸ PASS در ۷۷٫۷۹۰ ثانیه**.
- suite داشبورد: **۳۱ PASS در ۸٫۷۱۶ ثانیه**؛ ظاهر و assets تغییر نکردند.
- Ruff، compileall، diff-check و config آفلاین پاس شدند؛ config همچنان shadow و trading/network disabled بود.
- تست اولیهٔ harness با patch کردن کلاس socket، event loop ویندوز را مختل کرد و یک timeout داد؛ guard شبکه به transport واقعی HTTP منتقل شد. baseline اولیه هم به‌علت PYTHONSAFEPATH مسیر tests را نداشت؛ با مسیر صریح اصلاح شد. این خطاها خطای محصول یا درخواست واقعی نبودند؛ نتیجهٔ نهایی پس از اصلاح harness ثبت شده است.

## آزمون ایزوله روی لیارا

کد کاندیدا در `/state/diagnostics/executable-selection-offline-20261025`، در فرایند جدا با محیط بدون کلید/توکن بررسی شد. فقط projection روی همان context ضبط‌شدهٔ trace225 اجرا شد؛ هیچ خواندن/نوشتن بودجه یا فراخوانی broker انجام نشد و مدل یا بازار دوباره فراخوانی نشدند. جداسازی محیط و مسیر import به معنی sandbox مجوزهای سیستم‌عامل نیست؛ ادعای منع دسترسی فایل با ACL یا منع شبکه در سطح سیستم‌عامل نداریم.

نتیجه `SAME_SERVER_OFFLINE_PROJECTION_PASS`:

- acceptedها همان هشت نماد ماندند؛ خروجی features نهایی از هشت به دو نماد BTC و PEPE محدود شد.
- XAUT از selectableها حذف شد؛ hash context اصلی و hurdleهای نقدی ثبت‌شده تغییر نکردند.
- SHA context: `a26894f62d0899a09740cc65c45fd5001028d9c840fa1b377ad747f4d208c5b4`.
- SHA کد کاندیدای agent: `b2b49148b870429714a53a136edca75a90aa70c98e534624bcf3a8347db5cd50`.
- SHA کد کاندیدای decision: `c6dbbf27e5282c30df155af5eb10776778968bd5e1222ba9eb7944eae90d421e`.
- صفر model HTTP و صفر order request؛ `budget_access=false` و `financial_deployment=false`.
- موتور مالی همچنان روی artifact اصلی و PID1 start ticks `1354470026` بود؛ engine restart انجام نشد.

آزمون اولِ اسکریپت کمکی سرور، پیش از اجرای candidate با IndentationError متوقف شد؛ قالب wrapper اصلاح و همان context/hash در اجرای جدا بررسی شد. این شکست اولیه حفظ شده و موفقیت مالی تلقی نشده است.

رسیدهای خام و patch محدود به همین فاز در `.local/review/executable-selection-offline/` هستند؛ وارد Git نشده‌اند. SHA رسید لیارا: `990f61fac7d0746f205408bcbb7bf98e9dfcac96d6e2ecbb2aabb6357108848f`. SHA patch: `43e806cc7be0d894cf8581f1706810a7c591c4c053631d220328c0472c289783`.

## مرز نتیجه

نقص مشخص انتخاب نماد در **کاندیدای آفلاین** رفع و regression آن تأیید شد. رفتار مدل واقعی با schema جدید، کیفیت forecastها، تعداد ورود آینده، اجرای خرید تا فروش و سودآوری این کاندیدا هنوز تأیید نشده‌اند. stricter selection می‌تواند پاسخ ناسازگار provider را به HOST_FALLBACK تبدیل کند؛ سازگاری واقعی باید جدا سنجیده شود.

**این آزمون، استقرار مالی نیست.** artifact فعال، environment، permit، state، UNKNOWN قدیمی، counter8، بودجه و source history مالی تغییر نکردند. local source دیگر با manifest نسخهٔ فعال برابر نیست؛ برای بررسی نسخهٔ فعال از سورس/آرشیو منجمد و شواهد سرور استفاده شود. عدم معاملهٔ نسخهٔ زنده با این patch محلی حل‌شده اعلام نمی‌شود.
