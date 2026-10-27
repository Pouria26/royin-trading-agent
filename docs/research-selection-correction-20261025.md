# اصلاح انتخاب پژوهش و اتصال collector واقعی — ۲۵ اکتبر ۲۰۲۶

## مسئله و علت

در مأموریت اصلی سه ENTER تاریخی ثبت شده‌اند، اما هیچ سفارش/fill واقعی جدید ثبت نشده است. ENTER مدل، عبور از میزبان، ارسال HTTP و fill صرافی مراحل جدا هستند. در آخرین چرخهٔ source قبلی، مدل۱۰نماد پژوهش کرد:۴historyparsefailed،۴spreadrejected و۲داده‌پذیرفته‌شده که هر دو capacityblocked بودند. مدل پیش از انتخاب، تعداد پژوهش‌های گذشته را می‌دید، اما برآورد ظرفیت lot و علت/سن نتیجهٔ اخیر را نمی‌دید. شمار accepted فقط پذیرش داده بود و می‌توانست با ظرفیت معامله اشتباه شود.

ضعف مستقلِ بازبینی: FreshEngine از collector خودش استفاده می‌کرد، اما `signals.public_feed` به آن متصل نبود؛ rawها روی دیسک بودند ولی `public_captures` مانیفست خالی می‌ماند. بنابراین پیوند query/symbol/received_at/rawSHA برای خطاهای قبلی از خود مانیفست قابل استخراج نبود. rawهای قدیمی بازسازی/نام‌گذاری حدسی نشدند.

## تغییر

- `research_selection_hints` در `scripts/run_paper_trader.py`: با catalog/rules موجود و همان سقف پژوهش/minimum/residual، جست‌وجوی محدود lot را پیش از مدل انجام می‌دهد؛ HTTP یا سفارش اضافه ندارد. قیمت catalog جای book نیست؛ NO_FIT_FOUND اثبات غیرممکن‌بودن معامله نیست.
- `MarketCatalogCandidate` و `screening_view`: برآورد FIT/NO_FIT و نتیجهٔ پژوهشِ حداکثر۱۲trace/یک‌ساعت اخیر، با index و legend فشرده به مدل می‌رسند. تمام نمادهای مجاز باقی می‌مانند؛ hint منع دائمی یا فرمان ورود نیست. تاریخچه/شمارنده reset نمی‌شوند؛ hint منقضی صرفاً نمایش داده نمی‌شود.
- `agent.py`: پذیرش داده از قابلیت اجرا تفکیک شد؛ توجه به ظرفیت و خطاهای تکرارشونده پیش از انتخاب و افق متناسب درخواست می‌شود. هدف/q50 را برای عبور از هزینه نمی‌سازد. `ENTRY_DOSSIER_COMPACT_V2` متن ثابت proxy را یک‌بار می‌فرستد و علامت/مقدار۱۰رقمی را حفظ می‌کند؛ اصل داده و hash کامل دست‌نخورده‌اند.
- `FreshEngine`: همان collector واقعی و فهرست receipt بازیابی‌شده به signals متصل شد؛ counter اولیهٔ GET و سقف‌ها تغییری نکردند. feed/worker دوم ساخته نمی‌شود.

## تست و حدود

**۵۶۷تست هسته PASS در۶۶٫۲۳۱ثانیه**؛ Ruff/compileall/diff،۴oracle آفلاین وconfig shadow پاس. backend/ظاهر داشبورد در این فاز تغییر نکرد. تست‌های جدید: lotدرشت ETH در برابر BTC، حفظ کل universe، انقضای hint بدون حذف تاریخچه، جایگزینی شکست با دادهٔ سالم، حفظ index collector و SDK واقعی روی MockTransport با۵۷نماد/۱۰نامزد. این‌ها سود یا HTTP واقعی مدل را اثبات نمی‌کنند.

نسخهٔ اولیهٔ hint در تست، درخواست دوم۳۲۷۲۴بایتی ساخت و پیش از HTTP مسدود شد. سقف۳۱۷۴۴بایت تغییر نکرد؛ حذف توضیحات تکراری/قالب فشرده، اندازه را به **۳۱۰۵۸** رساند. هیچ نامزد یا چهارحالت محاسبهٔ fee از trace اصلی حذف نشد.

GET خصوصی مستقل، نرخ‌های حساب BTC/ETH/PEPE را در۰۳:۱۹تهران مجدداً maker۰٫۰۰۲۵/taker۰٫۰۰۳ تأیید کرد؛ receipt در همان account-captures و counter اصلی ثبت شد. دارایی کسر کارمزد هر fill هنوز باید از پاسخ واقعی خوانده شود؛ [مستندات جزئیات سفارش والکس](https://developers.wallex.ir/spot/singleorderdetail) فیلدهای executedQty و fills/feeAsset را جدا ارائه می‌کند. نرخ fee جای fill نیست.

## استقرار و حفظ state

release فعال `aa15c0853d380e27aada3fedae68008c95c56beb` از نوع CONTENT_HASH_NOT_GIT_COMMIT؛ sourceSHA `bece8139171b24ac69ae5a75557725f3cb9488a297e81c6fe50caf734edcefe8`؛ZIP SHA `784c8ff0cad7200a024a4a474b8665ae8ebc38002f57ef79c63763c93b1568a9`.

همان mission9/image/disk/config/permit/۲۷env ادامه یافت. تمام۷۰hash و importroot واقعی بررسی شدند. پیش از activation، همهٔ جدول‌های financial/signals/budget/historical و مانیفست با backup سازگار برابر بودند؛ تنها source receipt append شد. **۴۵۹رزرو قبلی،۲۹scope،۱۱۶trace، coverage/anchor/count و nextanalysis1792885919** حفظ شدند. prefix همهٔ رزروهای قبلی و historicalrawSHA تأیید شد. گیت UNKNOWN/reserve/counter8 دست‌نخورده‌اند. قفل انحصاری واقعاً آزاد بود؛ metadataRUNNING قدیمی به terminal جعلی تبدیل نشد.

backup: `/state/upgrades/research-selection-20261025`؛ transition receipt `45365898b7cd4e6ef6cfcc18a340bda733b830d7fd87d441966309e665d67ceb`. پس از فعال‌شدن، bootstrap/coverage/cadence و scope با چرخهٔ عادی پیش رفتند؛ نابرابری آن‌ها با snapshot قبل از اجرا، به‌تنهایی reset نیست. ناشر منفرد با settings/source قبلی و PID مشاهده‌شده۲۴ بازگردانده شد. Git HEAD همان693f1f4 و index خالی ماند؛ commit/push یا UI change انجام نشد.

## اولین چرخهٔ واقعی

در **۰۳:۲۳:۰۲تهران**، trace۱۱۷ با BoxAPI/gpt-6-luna،۲HTTP200،requestbytes۱۰۷۶۴/۲۸۰۷۶،projectionV2 و hashrole/runtime متناظر کامل شد. SDK۱۱۷۸۸input/۵۲۲output گزارش کرد؛ invoice نیست. universe آن لحظه۵۱نماد داشت:۲۲lotfitestimate/۲۹nofit. مدل۱۰نماد انتخاب کرد؛۸دادهٔ معتبر پذیرفته شد. BTC وPEPE ظرفیت اجرایی داشتند. این بهبود از۲→۸، مشاهدهٔ دو چرخهٔ زمانی متفاوت است؛ A/B کنترل‌شده یا اثبات alpha نیست.

**۲۵receipt عمومی اکنون واقعاً در مانیفست بود.** از روی rawSHA/query همان چرخه، علت خطای SHIB مشخص شد:۱۸۴ردیف برای پنجرهٔ۲۰۰دقیقه‌ای، با cadence/gap نامعتبر. سری‌های سالم۲۰۱ردیف شامل boundary داشتند و parser۲۰۰کندل بسته را پذیرفت. دادهٔ مفقود interpolation نشد. PUMP نیز به‌علتspread کنار رفت.

پاسخ نهایی **MODEL_DECISION/WAIT** بود: q50پپه۰٫۴٪ در افق۱ساعت، در برابرcashhurdle حدود۱٫۲۱۵٪؛ target۱٫۲۲٪ بود. هدف نزدیک به هزینه، میانهٔ زیر هزینه را جبران نمی‌کند. این WAIT فنی یا ردشدن سفارش نیست. در snapshot۰۳:۲۳:۲۸، **صفرسفارش/صفرfill** و موجودی API۰۳:۲۲ برابر۵میلیونTMNآزاد/صفرقفل/non-TMNصفر ثبت شد.

ادعای رفع همهٔ ریسک‌ها، سودآوری، اجرای کامل واقعی یا نبود فرصت در تمام بازار قابل اثبات نیست. اصلاح دسترسی به گزینه‌های قابل‌پژوهش و شواهد، جای مزیت معاملاتی نمی‌گیرد. مدل/بازارهای پژوهش‌نشده و prospectiveنتیجهٔ سیاست جدید همچنان نیازمند داده‌اند.
