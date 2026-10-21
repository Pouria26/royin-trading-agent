# حافظه پروژه رویین

نقطه شروع Agent: AGENTS.md. این فایل فقط نکته پایدار و قابل استناد دارد؛ وضعیت روزانه در TASKS.md، قانون رسمی در docs/challenge-brief.md. قالب یادداشت: تاریخ → منبع/نوع → یافته → اثر. با کشف خطا یادداشت را superseded کنید؛ تاریخچه اشتباه را واقعیت زنده نگه ندارید. Secret، شماره حساب و اطلاعات هویتی ثبت نشود.

## ۲۰۲۶-۱۰-۲۱

- **User / D:** تیم ماکارونی: پوریا Wallex، پژمان Liara، آیدین ترب؛ تقسیم کار و peer review برنامه داخلی‌اند. این Agent مربی/آماده‌ساز است؛ Coding Agent دیگر موتور را پیاده می‌کند.
- **User / R:** بریف دقیق و متن ویدئو در گفت‌وگو داده شده؛ الزامات و تمام بارم ۳۰۰ امتیازی در docs/challenge-brief.md استخراج شده‌اند. منبع آنلاین عمومی جزئیات بریف را مستقلاً تأیید نکرد.
- **GitHub API / S:** مخزن Pouria26/royin-trading-agent private بود و remote محلی مطابقت داشت؛ visibility عوض نشود. مسیر واقعی D:\royin-trading-agent است.
- **User / D:** سرمایه پنج میلیون تومان برای معامله است، نه پنج میلیون توکن. سهم توکن مدل نامشخص؛ هزینه/مصرف جدا ثبت شود. کلیدها هنوز داده نشده‌اند.
- **User + official Google / D/S:** مدل آزمایش gemini-3.5-flash-lite؛ GOOGLE_API_KEY در .env محلی. مدل مسابقه ممکن است عوض شود؛ smoke و eval لازم است.
- **User / resolved U01:** پایان معتبر جمعه ۲۰۲۶-۱۰-۲۳ ساعت ۲۳:۵۰ ایران. عبارت قبلی ۲۴:۰۰ superseded است. ویدئو زودتر؛ محل و ساعت دقیق ارسال هنوز روشن نیست.
- **Official Wallex docs / S:** لغو با DELETE /v1/account/orders/{client_id} است. نمونه قدیمی body در Blueprint استفاده نشود. کلید و sub-account-client-id حساب اعتباری لازم‌اند؛ fallback حساب اصلی ممنوع.
- **Official socket docs / S:** v2 ping ۲۵ ثانیه/مهلت ۸، حداکثر ۶۴ کانال؛ بیشتر کانال‌ها recovery ندارند. داده بعد از قطع اتصال باید تازه‌سازی شود؛ اعداد v1 با v2 مخلوط نشود.
- **Local API probe / S:** /hector/web/v1/markets نتیجه‌ای با result.markets داد؛ نمونه result.symbols همه endpointها را توصیف نمی‌کند. parser از قرارداد همان endpoint ساخته شود.
- **D:** Pydantic AI slim انتخاب اولیه برای نقش واقعی تصمیم و تست است، نه تضمین سود و نه کنترل سفارش. execution/risk مستقل و قطعی؛ MCP رسمی هنوز URL و قرارداد مشخص ندارد.
- **Risk review / D:** confidence مدل احتمال برد نیست؛ Kelly از آن ساخته نشود. حداقل position مثبت در همه شرایط خطاست. min buy، fee و min sell باید باهم چک شوند.
- **Evidence / D:** دریافت داده تاریخی واقعی با public endpoint ممکن است، اما probe کیفیت داده نه بک‌تست استراتژی است و نه اثبات سودآوری. ادعای سود فقط پس از engine+cost-aware holdout.
- **User / D:** امروز بهبود/تست، live از فردا و در کمترین مقدار مجاز؛ .env پیش‌فرض shadow بماند. Liara پس از تأیید شبکه/volume/restart گزینه ترجیحی اجراست.
- **U / superseded در بخش بازار:** یادداشت قبلی نبود فهرست با پیام تازه پوریا و snapshot ۳۴۵ جفت غیرفعال جایگزین شد؛ قاعده جدید «همه بازارهای قابل استفاده حساب به‌جز ممنوع‌ها» است. تطبیق دسترسی واقعی حساب هنوز لازم است؛ dust/مانده USDT و fee هکاتون همچنان باز است.
- **Measured / S:** در گزارش research/market-data-audit.json، درخواست resolution=15 برای شش نمونه فاصله غالب ۶۰ ثانیه داشت؛ کنترل BTCTMN یک‌روزه پاسخ res=1 و res=15 را با SHA256 یکسان و res=60 را با cadence ساعتی نشان داد. loader بدون assertion cadence وارد بک‌تست نشود؛ داده خودکار forward-fill/resample نشده است.
- **Measured / S:** برای USDTTMN در ۸–۱۵ اکتبر ۲۰۲۶، ۴۲۷ timestamp روی شبکه یک دقیقه غایب بود؛ برای BTC/ETH در همان پنجره هرکدام ۲. علت هنوز مشخص نیست. کیفیت عددی/OHLC/ترتیب با سودآوری یا کامل بودن داده یکی نیست.
- **Checks / S:** ۱۲ تست ابزارها در محیط موجود و محیط تازه نصب‌شده از lock گذشت؛ Ruff/compileall موفق. کلید Gemini خالی بود؛ مسیر مدل واقعی BLOCKED و هیچ درخواست مدل یا سفارش ارسال نشد.

یادگیری بعدی باید با تست/منبع مشخص اضافه شود؛ گزارش fake را real یا عدد حدسی را measured ننویسید.

## T02 — ۲۰۲۶-۱۰-۲۱

- **User / D:** commit کمتر و تمرکز بر بهبود دقت؛ یک checkpoint منسجم به جای commitهای ریز. ارجاع «چهار منبع» با متن تکمیلی شامل هفت repository شد؛ دامنه خوانده‌شده و blobها در research/source-review-manifest.json و تصمیم‌ها در docs/source-review.md ثبت است. برتری مناظره/MCP و اعداد دقت/latency متن منبع آزموده و پذیرفته نشده‌اند.
- **Real provider / S، supersedes نبود کلید در T01:** GOOGLE_API_KEY فقط محلی ثبت و probe PASS شد؛ ۱۶٫۶۲۵ ثانیه، دو درخواست، یک ابزار، WAIT، ۳۳۴/۴۱ token. این شاهد سازگاری است، نه دقت استراتژی. قیمت token و budget انبوه هنوز U هستند؛ Secret در حافظه ثبت نمی‌شود.
- **Official Swagger / S، supersedes balance reference قدیمی:** `/v1/account/balances` main wallet است. credit schema در `/v1/account/balances-detail`، result[asset] با total/available/freeze است؛ هدر sub-account-client-id در پارامتر ساخت‌یافته آمده. هیچ private call انجام نشد؛ parser و fee فقط با fixture schema/synthetic آزموده‌اند.
- **Wallex observation / S:** resolution=1 با بازه هفت‌روزه فقط مرز end داد، ولی درخواست روزانه کامل‌تر بود. loader روزانه/با cadence صریح و سقف داده ساخته شد. سری‌های gapped رد می‌شوند؛ هیچ fill یا resample خاموش انجام نمی‌شود.
- **Data contradiction / S/U:** روی روز اول اکتبر، aggregation دقیقه‌ای با hourly API برای BTC در ۷ و ETH در ۱۰ ساعت اختلاف داشت؛ علت اثبات نشده و dataset این پنجره‌ها رد است. USDT هفته اول ۶۷۲ bar و reference روز اول را گذراند؛ مقایسه ساعتی فقط همان یک روز و واحد volume/base و timestamp/open فرض استاندارد ثبت‌شده‌اند، تأیید معنایی کامل Wallex نیستند. T07 بدون رفع ابهام سود اعلام نکند.
- **Diagnostic / S:** در ساعت‌های ناسازگار، volume در همه موارد برابر بود و اختلاف در OHLC بود. فرضیه کنارگذاشتن کندل صفرحجم فقط ۴ از ۷ اختلاف BTC و ۷ از ۱۰ اختلاف ETH را رفع کرد؛ راه‌حل کامل یا قرارداد رسمی نیست و در aggregation اعمال نشد. oracle برای سبز شدن ضعیف نشود.
- **Checks / S:** ۴۹ تست پاس، صفر skip/fail؛ Ruff/compileall/wheel موفق. rawها در data/t02 ignored، شواهد sanitized در research و docs/evidence؛ hash و query نگه‌داری می‌شوند. هیچ درخواست سفارش/حساب خصوصی و هیچ استراتژی سودساز هنوز وجود ندارد.

## T01 — ۲۰۲۶-۱۰-۲۱

- **User / D، supersedes نقش آماده‌ساز بالا:** این Agent اکنون مالک پیاده‌سازی رویین است؛ فقط تسک محدود آماده را با تست/گزارش/commit پیش می‌برد. T01 تکمیل، قدم بعدی T02 است.
- **Code + checks / S:** package در src/royin و `python -m royin check-config` فقط اعتبارسنجی‌اند؛ هیچ transport/loop/broker ندارند. تمام liveها تا گیت‌های بعدی رد می‌شوند؛ قبول syntax نماد، eligibility حساب نیست. ۲۸ تست در محیط فعلی، محیط پاک lock و wheel نصب‌شده گذشت؛ این شواهد کیفیت AI یا سود نیست.
- **Regression / S:** Pydantic timestamp رشته عددی را epoch می‌پذیرفت؛ config اکنون ابتدا ISO را با datetime.fromisoformat می‌خواند و AwareDatetime offset را اجباری می‌کند. offset به UTC تبدیل و FINALIZE_START_AT قبل از CHALLENGE_END_AT بررسی می‌شود.
- **Config / D:** dotenv strict با parser نسخه قفل‌شده python-dotenv؛ unknown/duplicate/malformed رد، interpolation خاموش، تنظیم فرایند مقدم. خطاهای CLI فقط نام شناخته‌شده تنظیم/پیام ثابت دارند و Secret/account ID از repr/serialization حذف شده است. پس از uv pip sync، نصب دوباره package محلی با --no-deps لازم است.
- **Probe / S:** دریافت عمومی تازه در ۱۵:۲۶:۰۳ UTC، همان hashها و شش DEGRADED داشت؛ ایراد cadence باقی است. smoke مدل همچنان BLOCKED/exit 2 به علت نبود کلید؛ حساب خصوصی و مسیر معامله بررسی نشده‌اند.

## به‌روزرسانی محدودیت‌ها — ۲۰۲۶-۱۰-۲۱

- **User / D:** دو commit آماده‌سازی به درخواست صریح پوریا در یک commit تجمیع شوند. برای ادامه، گام‌به‌گام با تست/گزارش هر تسک و commit در سطح فاز منسجم پیش بروید؛ commit برای هر ویرایش کوچک لازم نیست. هیچ نسخه معاملاتی در این تجمیع وجود نداشت.

- **User / R:** فقط اسپات بدون لوریج؛ margin، borrow و short نداریم. فروش برای بستن/کم‌کردن دارایی واقعی SELL است و ممنوعیت short نباید آن را مسدود کند.
- **User-supplied source:** config/wallex-credit-market-policy.json عین ترتیب ۳۴۵ جفت ممنوع ارسالی است: ۱۷۱ TMN و ۱۷۴ USDT. URL و تاریخ انتشار متن معلوم نیست؛ account check مستقل هنوز انجام نشده است.
- **D:** universe از catalog و بازار قابل استفاده حساب منهای اجتماع محدودیت‌ها ساخته شود؛ WALLEX_ALLOWED_MARKETS فقط انتخاب عملیاتی است. نبودن در denylist مجوز قطعی نیست و بودن در env هم ممنوع را آزاد نمی‌کند. لازم نیست فهرست مثبت کامل دستی تازه از پوریا بخواهیم.
- **Pair scope:** PAXG هر دو quote ممنوع؛ YFI/USDT در فهرست است اما YFI/TMN نیست. restriction به coin تعمیم داده نشود؛ حفظ پیشوند 1BBABYDOGE/2Z در mapping لازم است.
- **Image / inference:** تصویر API و معامله پیشرفته/آنی را برای حساب اعتباری پشتیبانی می‌کند؛ بات داخلی، تعهدی، واریز/برداشت و انتقال بین حساب‌ها را خیر. مطابق بریف، موتور خارجی API با بات داخلی متفاوت است؛ دسترسی واقعی هنوز باید با حساب اختصاصی آزموده شود.
