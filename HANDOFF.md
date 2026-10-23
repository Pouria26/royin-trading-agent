## Current authority and checked phase — 2026-10-23, after 17:18 Tehran

Latest direct operator instruction authorizes real autonomous execution and delegates trading judgment. Fixed 150k-only new-mission policy is superseded by VOLATILITY_CAPITAL_V1: 0.5% account planned risk, ATR stop, 50% asset / 80% mission ceilings, first completed actual round-trip <=150k, one position with rotation. Daily UTC loss 2%, persistent mission drawdown 4%, risk halves after 1% drawdown. No confidence-as-probability sizing. Historical UNKNOWN/reserve/counter8 remain immutable; this authorization creates an independent lane and is not historical exchange finality.

Frozen paired-hour-forward-20261023-1 stopped at operator request at16:50:17 Tehran, STOPPED_FLAT/PARTIAL, source unchanged,115cycles/535GET. Hold -1389.50331768TMN; rule -3321.877789326TMN; GPT/APMix zero fills, respectively10/14 valid model decisions and12/8 fallback. This is not a completed3h test or alpha evidence. Full terminal snapshots and hashes are in .local/review/paired-hour-stopped-snapshot.

Integrated changes: exact host candidate choices in output schema (binding validation retained); fresh post-inference entry quote with original conditional economics; durable dynamic sizing, actual-ledger dashboard monitor, config binding/readiness checks. 479 core tests/13 dashboard tests passed, Ruff/compileall/example-config/JS syntax passed. APMix existing usage allowance extended20M->200M with original115 reservations retained, no refund/reset; BoxAPI original limits unchanged. Real-provider compatibility with new schema, actual new order/fill, and Liara team deployment remain UNCONFIRMED at this checkpoint. See docs/dynamic-capital-policy.md and docs/multiday-runtime.md. Next: commit source, prepare fresh mission with real account reads, then single worker and verified persistent-volume deployment.

## وضعیت مقدم — پایان مقایسه و نامزد چندروزه، ۲۳ اکتبر

ابتدا Git و process واقعی بررسی شوند؛ یادداشت زمان‌دار کافی نیست. `paired-entry-forward-20261023-2` روی7df0d08 در11:14:45UTC کامل/STOPPED_FLAT شد و دو PID6940/25112 خارج شدند. چهار accounting replay معتبر؛hold+۱۷۵۰٫۴۱تومان،rule−۴٫۸۳،مدل‌ها۰fill.۱۵forecast همگی scored و از baselineصفر در meanAE ضعیف‌تر بودند. terminal snapshot/hashها در `.local/review/paired-final-snapshot`؛ گزارش خام و state خصوصی وارد Git نشوند.

قرارداد چندروزه/خروج مستقل/بازیابی/backup/بستهٔ Docker و مسیر مالی مستقل تازه پیاده شده‌اند؛ [قرارداد](docs/multiday-runtime.md) را کامل بخوانید.۴۶۸هسته/۱۱داشبورد روی main پاس؛ تست لینوکس جدا ثبت می‌شود. مسیر جدید مالی هنوز prepare/activate نشده و سودAI ثابت نیست.

دستور جدید کاربر اجازهٔ شروع lane تازه را بدون انتظار finality قدیمی می‌دهد؛ UNKNOWN قدیمی و counter/reserve/DB آن پاک یا بازتفسیر نشوند. FreshMissionPermit این اجازه را جدا ثبت می‌کند؛ سقف۱۵۰هزار/یک موقعیت/بدون افزایش خودکار. دیگر همان سؤال finality تاریخی از کاربر پرسیده نشود.

اطلاعیه۱۳: تحویل سورس/دمو جمعه۲۳:۵۰؛ سود تا پایان دوشنبه. تمدید اعتبار را کاربر تأیید کرده؛ ساعت دقیق دوشنبه هنوز اعلام نشده. config نمونه cutoff داخلی۲۲:۵۰/خروج۲۱:۵۰ دوشنبه دارد. استقرار **امشب پس از تست** به خواست تازهٔ کاربر، روی حساب تیم لیارا/دیسک پایدار است؛ ساخت برنامهٔ شخصی با کمبود اعتبار رد شد و هیچ worker ابری اجرا نشده. ویدئو/ارسال در scope این نوبت پیگیری نشود. دو فایل پژوهش untracked کاربر و Secretهای ignored حفظ شوند؛ push مجاز نیست.

قدم بعد: commit منسجم → آزمون تازهٔ سه‌ساعته با horizon ثابت۱ساعت و دو پنجره۹۰دقیقه؛ در اجرای فعال source را عوض نکنید یا workerمدل دوم روشن نکنید. forecast/error/zero trade را پنهان نکنید؛ نتیجه سپس مبنای انتخاب نسخهٔ امشب است.

## وقفهٔ run اول و ادامهٔ تازه — ۲۳ اکتبر

paired-entry-forward-20261023-1 روی349e136 با۰سفارش،۱۳GET وTypeError عددی book در۱۰۴ثانیهSTOPPED_FLAT/PARTIAL شد؛ مصرف/manifest اصلی حفظ شدند. Decimal copy/hash و harness PID ویندوز اصلاح،۴۴۷تست در۵۷٫۱۸۶ثانیه پاس شد. run بعدی شناسهٔ تازه می‌خواهد؛ پیش از edit، artifacts/paired-paper وPID واقعی را چک کنید. SOL smoke موعدرسیده−۰٫۹۱٪ دربرابرq50+۰٫۶٪ بود و از baselineصفر ضعیف‌تر شد؛ سودآوری ثابت نشده است.

## وضعیت مقدم — مقایسهٔ prospective ورود، ۲۳ اکتبر ۲۰۲۶

مسیر مقایسهٔ کاغذی shared-input/shared-book اضافه و ۴۴۷ تست هسته/۱۱داشبورد پاس شد؛ [قرارداد دقیق و فرمان اجرا](docs/paired-entry-evaluation.md). پیش از تغییر، process و artifacts/paired-paper را بررسی کنید: run فعال source منجمد دارد. این یادداشت به‌تنهایی شروع/پایان worker را ثابت نمی‌کند؛ protocol/progress/report و PID باید خوانده شوند. چهار arm مستقل و cash، entry-only و خروج host هستند، نه اجرای کامل Position Reviewer.

اصلاح مالی کاغذی: سفارش فروش نهایی اکنون با intent/fill/stop اتمیک در broker_orders ثبت می‌شود؛ replay تعداد سفارش‌ها را ضعیف نکردیم. مزیت سود هنوز ثابت نشده؛ مدل منتخب عملیاتی GPT و challenger Claude است. state مالی UNKNOWN و canary هشت attempt تغییر نکرده و live بسته است. دو فایل پژوهش untracked کاربر حفظ شوند؛ push مجاز نشده است.

# پرامپت انتقال پروژهٔ رویین به Agent جدید

## وضعیت مقدم بر یادداشت‌های تاریخی — ۲۳ اکتبر، پس از پایان run سه‌ساعته

**ادغام و استفادهٔ واقعی:** کد انتخاب provider و سه اصلاح قبلی اکنون روی main در108e784 هستند؛ source مقایسهed673294،۴۳۸هسته/۱۱داشبورد وchecks روی main پاس. smokeجاری تک‌چرخهٔ `provider-selection-runtime-smoke-20261023-2` با GPT منتخب،۱۰درخواست نماد/۳پذیرش/۲HTTP/۴۴٫۸۹ثانیه/۱WAIT معتبر،۰سفارش/fill وSTOPPED_FLAT دارد؛ replay پاس و forecast تا09:41UTC/۱۳:۱۱تهران pending است. smokeاول به‌درستی پیش از مدل و در دقیقهٔ آخر defer شد؛ آن را نتیجهٔ AI محسوب نکنید. این شاهد اتصال جاری است، نه آزمون تازهٔ سود.

اجرای `evidence-forward-20261023-1` در08:22:22UTC به STOPPED_FLAT رسید؛ دو PID آن واقعاً خارج شدند. receipt نهایی `.local/review/remote-integration-20261023/forward-postprocess-report.json` و snapshot hash `1c76e06ed501704d9d421368f2b3990f4b14e5a656743e2a1d5e419348de2374` مرجع‌اند. ۳۴trace،۱۳مدل واقعی/۱۰fallback/۱۱host،۰سفارش/fill/exposure/PnL؛ replay حسابداری پاس ولی اجرای کامل بازار UNCONFIRMED. هر۱۳forecast موعدرسیده سنجیده شد: meanAE مدل۰٫۳۷۳۷۰۲pp،صفر۰٫۲۹۷۸۰۲pp،۵بهتر/۸بدتر. cohort شش‌تایی پایین زیرمجموعه است؛ نتیجهٔ صفرمعامله را موفقیت سرمایه‌گذاری ننامید.

هدایت تازهٔ کاربر، آزمایش Devora/Dahl/River/APMix/Codecraft با معیار کیفیت و بدون رتبه‌بندی هزینه است. اتصال، ledger خارجیِ کلیدبسته و CLI مقایسه اضافه شده‌اند؛ [قرارداد و نتایج](docs/model-provider-evaluation.md) را بخوانید. در runs1..3 مسیر Entryِ harness اشتباهاً legacy بود؛ رد forecastهای آن کیفیت مدل را ثابت نمی‌کند. اصلاح روی batch فعلی و با run4 جدید آزموده شد: GPT-6-luna و APMix Sonnet4.6 هرکدام۶/۶ معتبر؛ دور تأییدی هرکدام۱۲/۱۲، median۷٫۹۸۴۵ و۲۱٫۱۸ثانیه. طبق قاعدهٔ عملیاتی GPT انتخاب و default حفظ شد؛ سودآوری هر دو نامعلوم. Codecraft کاتالوگ۲۰۰ اما inference۴۰۲ Billing verification failed دارد، حتی در درخواست ساده؛ مانده و علت بالادست قطعی نیستند. MiniMax انتخاب نهایی نشده است.

۴۳۸هسته در۴۲٫۴۱۲ثانیه،۱۱داشبورد در۱٫۴۵۵ثانیه،Ruff/compileall/چهارself-check/config پاس‌اند؛ هیچ source نامزد به worker قدیمی اعمال نشد. پیش از ادامه Git و process واقعی را دوباره بررسی کنید؛ run جدید revision/ID جدید می‌خواهد. بودجهٔ BoxAPI، canary۸attempt، intent/reserve و BUY_UNKNOWN محفوظ و live بسته‌اند. وظیفهٔ این نوبت موتور و ارزیابی است؛ از کاربر دربارهٔ ارسال ویدئو دوباره سؤال نکنید.

## زمان‌بندی پژوهش و نتیجهٔ واقعی بازبین — نامزد ادامه، ۲۳ اکتبر

در ۶ fallback پنجرهٔ اول، مدل با ۱۱..۳۹ ثانیه زمان باقی‌مانده تا کندل بعد شروع شده و همه پس از مرز cutoff برگشته‌اند. trace قدیمی کلید گم‌شده را ثبت نکرده؛ تطبیق با BLOCKED_CUTOFF_ADVANCED قرینه است، نه اثبات علت تک‌تک موارد. نامزد REAL_MODEL پیش از claim چرخهٔ دیرهنگام را به بعد موکول و پس از bootstrap نیز جا شدن کل deadline را پیش از claim نقش/HTTP بررسی می‌کند. cadence حداقل۳۰۰ثانیه و پایش موقعیت مستقل باقی‌اند؛ HOST_DEFERRED با صفر HTTP/forecast/order در replay جدا حفظ می‌شود.

پذیرش تازه: ۴۲۳ هسته در۴۵٫۹۴۱ثانیه،۱۱داشبورد در۱٫۷۹۸ثانیه،Ruff/compileall/چهار self-check/config پاس. تشخیص واقعی دوم Position Reviewer روی source94ac8c2/hash6f9dfd0، با موقعیت فرضی، EXIT معتبر با۲HTTP/۱۰٫۶۸۸ثانیه داد؛ USD0.00871424 رزرو شد و هیچ سفارش/fill نداشت. تشخیص ناموفق نخست پاک نشده است. این نتیجه provider همان source است، نه سود یا آزمون کل نسخهٔ بعدی.

شش forecast cohort نخست همگی موعدرسیده و سنجیده شدند: mean AE مدل۰٫۳۴۴۳۸۵pp در برابر صفر۰٫۳۲۸۲۰۶pp،۳بهتر/۳بدتر،۰pending/۰missing؛۴مورد PEPE و هم‌بسته‌اند. هیچ مزیت اقتصادی ثابت نشده است. کاربر اکنون آزمایش مدل‌های Devora/Dahl و انتخاب بر اساس کیفیت بدون معیار هزینه را صریحاً مجاز کرده؛ این هدایت بر محدودیت تاریخی BoxAPI-only مقدم است، اما اجرای فعال و ledger BoxAPI/مالی تغییر نکنند. کلیدهای تازه فقط ignored و دادهٔ ارسالی عمومی باشند؛ مقایسهٔ مدل‌ها هنوز تکمیل نشده است.

## اصلاح قرارداد ابزار و پژوهش مسدود — نامزد آفلاین ۲۳ اکتبر

پس از نامزد c15a389، ابزار `read_market_snapshot` برای پژوهشِ دارای universe، `symbols` اجباری دارد؛ برای snapshot متصل و Position Reviewer هیچ پارامتر انتخاب بازار ندارد. تشخیص واقعی نقش بازبین روی source منجمد f8a1748 شکست خورد: مدل طبق schema قبلی symbols فرستاد و میزبان ValueError داد. نتیجه و یک رزرو USD0.00435712 در artifact اصلی محفوظ‌اند؛ موقعیت فرضی و سفارش/fill صفر بودند. اصلاح هنوز با provider واقعی آزموده نشده و به اجرای فعال اعمال نشده است.

پژوهشی که از cutoff عبور کند یا batch/coverage معتبر نداشته باشد، پیش از درخواست دوم مدل با علت محدود ثبت می‌شود؛ KeyError جای وضعیت داده را نمی‌گیرد. تست‌های schema ابتدا قرمز شدند؛ پس از اصلاح ۴۱۹ هسته/۱۱ داشبورد، Ruff، compileall، چهار self-check و config پاس‌اند. prompt، cutoff، گیت مالی و سقف بودجه تغییر نکرده‌اند. قبل از ادغام، پایان واقعی worker و گزارش postprocess را بررسی کنید؛ اجرای جاری source ثابت دارد.

## نامزد آماده ولی فعال‌نشدهٔ دلایل رد

این commit بر پایهٔ e089bc3 در checkout آفلاین، علت‌های رد غربالگر را پایدار و حالت depth نامعتبر را از بازارهای سالم جدا می‌کند. ۴۱۶ تست هسته و ۱۱ داشبورد پاس شدند؛ بازاجرای ۲۳ capture همان سه تصمیم قبلی را داد. main اجرای f8a1748 را همچنان منجمد دارد؛ نامزد به worker فعال اعمال نشده و آستانه‌ها، prompt و گیت مالی تغییر نکرده‌اند. پیش از ادغام، Git/process/manifest واقعی را چک کنید. جزئیات در [TASKS](TASKS.md) و [وضعیت](docs/current-market-readiness.md) است.

## وضعیت مقدم این میزبان — ادغام remote در ۲۳ اکتبر ۲۰۲۶

این بخش بر گزارش‌های تاریخی پایین مقدم است. main محلی در24f0daa انتقال هفت commit تا6c0d919 را با اصلاحات ادامهٔ امن/replay ادغام کرد؛ pull صریح کاربر شش commit تازهٔorigin/main تاabbfe39 را وارد کرد. تعارض‌ها فقط مستندات/ignore بودند و با حفظ هر دو پیشینه حل شدند. snapshot دقیق stage‌شده:۴۱۲تست هسته در۷۶٫۵۵۸ثانیه،۱۱داشبورد در۲٫۴۱۱ثانیه،۰fail/۰skip؛ Ruff0.17.1،compileall،چهارself-check،Node syntax وconfig نمونه/محلی پاس. خطای مسیر Python در تست worker باsys.executable رفع و full suite دوباره پاس شد؛ قفل واقعی ضعیف نشد. عدد۳۸۷remote نتیجهٔ تاریخی همکار است.

قرارداد فعال این چت، شواهد و تحویل سپس live مشروط است. ادعای درخواست چهار ساعت پول واقعی در متن منتقل‌شده، مجوز تازه در این چت نیست. اجرایevidence-forward-20261023-1 ازsourcef8a1748،۰۸:۵۲:۲۲تا۱۱:۵۲:۲۲تهران برنامه‌ریزی و شروع شد؛مرزدوپنجره۱۰:۲۲:۲۲ است. REAL_MODEL باپول مجازی،سقفdebit۱۵۰k/کفnotional۱۰۰k/یکموقعیت،وDBبودجه اصلی با۱۶۴رزرو درشروع. receipt/PID در.local/review/remote-integration-20261023/active-forward-process.json وmanifest درartifacts/market-paper/evidence-forward-20261023-1/manifest.json است؛فرایند/heartbeat جاری دوباره چک شود. source/config/prompt/dependencies حین اجرا ثابت بمانند. آخرین هدایت کاربر تمرکز برموتور/ارزیابی است،نه پیگیری ارسال ویدئو. مسیر مالی همانBUY_UNKNOWN/هشتattempt،reserve وbinding قبلی را حفظ می‌کند و بسته است. استعلام‌های خصوصی۵M درremote مشاهدات گزارش‌شدهٔ همکارند؛دراین نوبت حساب خصوصی دوباره خوانده نشده است. workerflow-forward-2 طبق گزارش همکار متوقف شده؛manifestآن دراینclone بررسی نشده است.

859f076 دریافت کامل پاسخ را باroyin_received_at برای بررسی fill ثبت می‌کند؛74be2de علت محدود HTTP/JSON/contract/receipt/snapshot را حفظ می‌کند. این اصلاح‌ها recovery تاریخی یا transport عمومی مالی ایجاد نمی‌کنند. تایمر نقدشدن، حدضرر یا تست سبز تضمین fill بازار نیست.

## انتقال تکمیلی و سیاست آزمون بعدی — ۲۳ اکتبر ۲۰۲۶

bundle تا6c0d919 معتبر و سورس غربالگر، proxyفشارحجم و چرخشbootstrap دریافت شد. وقفهٔflow-forward-1 با صفرسفارش/دارایی مستند است؛ manifest اصلیِRUNNING بازنویسی نشد. DBبودجه۱۶۴رزرو اصلی را حفظ کرده وstatecanaryباهمانUNKNOWN/هشتattempt به مسیر پیش‌فرض مشترک حساب بازیابی شد؛ هیچ reset یا سفارش تازه‌ای انجام نشد.

کف۱۰۰k نقل‌شده در خلاصهٔ گروه باmetadataعمومی۵۰k یکسان نیست. کاربر تصمیم را واگذار کرد؛ paperبعدی سقفdebit۱۵۰k/کفnotional۱۰۰k/یکموقعیت دارد،liveهمان۱۰۰k و مسدود می‌ماند. گارد پیش از HTTP، کف مؤثر در قواعد ورود/خروج و bindingrestart اضافه شده‌اند. [توضیحات و منشأ تصمیم](docs/group-clarifications.md) و [قرارداد اجرا](docs/evaluation-plan.md). دادهٔ واقعی سه‌ساعته و برتری در برابر baselineها هنوز به اجرای تازه نیاز دارند.

بخش‌های «فایلغایب» در گزارش‌های قبلی پایین با این انتقال superseded شدند. paper/API واقعی با حساب مالی واقعی یکی نیستند؛ labelها،revisionها و sourceزمان‌آزمون حفظ شوند.

## بازیابی شواهد و ادغام — ۲۳ اکتبر ۲۰۲۶

کاربر بستهٔ انتقال و تحویل صریح مالکیت را ارائه کرد؛ روی checkout فعلی worker متناظر یافت نشد. نامزد `08f403c` بر مبنای `a76a420` با حفظ مستندات main ادغام شد؛ کد اجرای تاریخی و artifacts اصلی بازنویسی نشدند. آغاز worker پولی تازه مستقل از ادغام است و تا تعیین وضعیت `flow-forward-20261023-1`/مالک ledger و تنظیم کلید محلی متوقف می‌ماند.

رسید واقعی انتقال: سه manifest جاری، نه۴۷؛ snapshot اجرای `net-return-forward-20261023-2` هنوزRUNNING است. DB آن۸۲چرخه و heartbeat برابر00:00:19UTC دارد؛ terminal سه‌ساعته/STOPPED_FLAT تأیید نشد.۱۷تصمیم شامل۱۳MODEL_DECISION و۴HOST_FALLBACK،صفرسفارش/fill،۵M سرمایهٔ مجازی؛ این هم‌ارزی با cash است، نه سود.۱۹۰raw عمومی بدون hash نامعتبر بازیابی شد. DB بودجه quick_check=ok،۱۶۴رزرو و مجموعUSD0.35328 دارد؛ رزرو invoice نیست. backup سازگار به‌صورت ignored تهیه شد. state مالی canary و.env هنوز در این clone موجود نیستند؛ reset/ساخت جایگزین ممنوع.

۱۳forecast موعدرسیده با۱۲GET عمومی سنجیده شد:۰pending/۰missing؛ mean absolute error مدل۰٫۵۲۹۱pp دربرابر baselineصفر۰٫۳۳۱۳pp،medianمدل۰٫۳۴۸۳pp دربرابر۰٫۳۹۷۲pp. مدل۳مورد بهتر/۱۰مورد بدتر بود؛۱۰forecast رویUSOON و نمونه‌ها هم‌بسته‌اند. replay واقعی همین artifacts،۱۳binding و۴fallback را حفظ کرد؛ journal/input-state قدیمی غایب است و نتیجهPARTIAL_RECORDED_HOST_REPLAY ماند. [قرارداد بازپخش](docs/recorded-host-replay.md) و [وضعیت جاری](docs/current-market-readiness.md).

ادعای commit `e2d2237` با fetch تأیید نشد؛ تست untracked `test_quant_screener.py` تابع موجودنشدهٔquant_candidate_score را import می‌کند. فایل‌های دریافتی حفظ و hash/backup شدند؛ منبع تازه را از متن پژوهش حدس نزن و این تست را برای سبزکردن حذف نکن. گزارش‌های پایین تاریخی‌اند؛ نبود فایل/وضعیت source در آن‌ها با این بخش superseded شده است.

## وضعیت تأییدشدهٔ انتقال — ۲۳ اکتبر، ۰۶:۳۷ تهران

checkout اصلی روی `main` است. در این میزبان فرایند متناظر، `.env`، artifacts اصلی، `data/llm-budget.sqlite3` و state مالی یافت نشد؛ پایان/تحویل مالکیت میزبان قبلی **UNCONFIRMED** است. برچسب‌های RUNNING و ماندهٔ حساب در ادامهٔ سند، گزارش تاریخی‌اند. source bundle اصلی دوباره با hash ثبت‌شدهٔ `679ded0d…1fb8e` برابر بود و تغییر نکرده است.

نامزد `08f403c` در worktree متصل `C:\Users\Ariike.ir\.codex\worktrees\offline-evidence\royin-trading-agent` آماده و commit شده است؛ بر `a76a420` بنا شده و هنوز روی main ادغام یا اجرا نشده است. این نامزد گارد DB موجود برای همه CLIهای پولی و تابع تصمیم، گیت هزینهٔ target، سنجه و cadence بادوام و بازپخش آفلاین تصمیم/حسابداری را دارد. راهنمای آن در `08f403c:docs/recorded-host-replay.md` است. ۳۹۳ تست هسته در snapshot دقیق stage‌شده و محیط تازه، ۱۰ داشبورد، چهار self-check، Ruff0.17.1، compileall و config check پاس شدند؛ هیچ شواهد تازهٔ provider یا سود واقعی تولید نشد.

کار مستقل بعدی بعد از دریافت شواهد: terminal یا تحویل صریح مالکیت، manifest/captures ثابت با hash و backup سازگار DBهای اصلی را بررسی کن؛ سپس forecastهای موعدرسیده را بسنج. پس از رفع freeze، نامزد `08f403c` را با حفظ اصلاحات مستندات main ادغام کن؛ نامزد `a76a420` را دوباره پیاده‌سازی نکن. وجود کلید تازه، مجوز ساخت DB بودجهٔ صفرمصرف یا reset رخداد BUY_UNKNOWN/هشت attempt مصرف‌شده نیست. تمام مسیرهای پولی فعلاً مسدودند. [TASKS](TASKS.md) مانع‌ها و پذیرش باقی‌مانده را نگه می‌دارد.

### گزارش دریافت‌شده از remote؛ پیشینهٔ همین ادغام

## وضعیت معتبر تحویل — 2026-10-23، پس از `74be2de`

این بخش بر وضعیت‌های زمان‌دار قدیمیِ پایین اولویت دارد. قبل از تغییر، Git، فرایندها، memory.md و docs/credit-canary.md را دوباره بررسی کن.

- آخرین خواستهٔ کاربر: فعلاً خرید یا تلاش مالی تازه انجام نشود؛ نسخهٔ آزموده برای ادامهٔ همکار آماده باشد. خودکار سفارش، worker تازه یا تغییر تنظیمات live را شروع نکن.
- اصلاحات معتبر: `859f076` زمان دریافت میزبان را برای بررسی fill واقعی به‌کار می‌برد؛ `74be2de` وضعیت HTTP و علت خطا را حفظ می‌کند و نتیجهٔ لغو را پایدار ذخیره می‌کند. اصل UNKNOWN، reserve، شناسه‌ها و سقف درخواست‌ها حفظ شده‌اند.
- آزمون کامل همین کد:۳۸۷تست در۵۴٫۱۵۰ثانیه پاس. بررسی سریع دوباره:۱۲broker و۱۴canary، Ruff و compileall پاس؛ تست‌های سفارش آفلاین‌اند و موفقیت ارسال واقعی را ثابت نمی‌کنند.
- آخرین استعلام واقعی: حساب اعتباری مطابق،۵M TMN آزاد، قفل و USDT صفر، تاریخچهٔ بدون فیلتر و سفارش باز خالی،404 شناسهٔ قبلی. هیچ سفارش تازه ارسال نشده است. Secret فقط در .env محلی است و با Git منتقل نمی‌شود.
- توقف خرید واقعی هنوز باز است: binding اجرای اولیه به `e7d8bc5`، مجوز منقضی و۸attempt مصرف‌شده متصل است؛ رکورد محلی UNKNOWN باقی مانده. `EXISTING_FINANCIAL_RUN_SOURCE_MISMATCH` قفل محلی است، نه خطای اثبات‌شدهٔ API والکس. نبود سفارش در حساب با علت تاریخیِ POST خالی یکی نیست.
- طرح آزمایشیِ بستن محلی سفارشِ غایب و ساخت مجوز تازه وارد سورس تحویلی نشد؛ `--resolve-absent` یا مجوز after_absence در نسخهٔ معتبر وجود ندارد. پیش‌نویس ignored، آزموده/تأییدشده نیست و نباید مستقیم اعمال شود. همکار باید recovery را جدا طراحی و بازبینی کند، نه اینکه DB، reserve یا شمارنده را reset کند.
- worker قبلی `flow-forward-20261023-2` پیش از تغییر منبع، با صفر سفارش/fill متوقف شد؛ manifest قدیمی شاهد اجرای جاری نیست. داشبورد فقط پایش است. سودآوری پایدار، نامزد مستقل و مسیر چهار‌ساعتهٔ واقعی تأیید نشده‌اند.

ادامهٔ پیشنهادی: ابتدا قرارداد بازیابی/مجوز اجرای محدود را مستقل بررسی کن؛ سپس فرصت‌های بازار را روی دادهٔ معتبر و با fee/spread/depth مقایسه کن. confidence یا پیش‌بینی مدل تضمین سود نیست. هیچ خرید تترِ فنی را به‌عنوان انتخاب استراتژی سودآور معرفی نکن. سقف شروع مورد درخواست کاربر۱۰۰k TMN شامل کارمزد است؛ حداقل/گام واقعی و امکان فروش باید رعایت شوند.

---

### پیشینهٔ تاریخی؛ وضعیت‌های زیر ممکن است superseded باشند

**آخرین تحویل، حدود23:50UTC / 03:20تهران:** نامزد تازهٔ همان شاخه `market-research-coverage` اکنون `a76a420` است؛ finalizeحفاظت را هم می‌بندد و MODEL_EXIT پیش از GETخروج پایدار می‌شود، تا خرابیbook تصمیم خروج را فراموش نکند و ورود بعدی همان نماد ممکن باشد.۳۷۳هسته/۱۰داشبورد، Ruff/compileall و۴self-check پاس. آزمون واقعی قبلی مربوط به `dacb5a6` و نقش ورود بود؛ بازبین واقعی روی موقعیت باز و اصلاح خروج تازه هنوز آزموده نشده‌اند. کاربر محدودیت توکن و انتقال به Agentدیگر را خواست؛ پایلوت پولی تازه شروع نشد.

**علت فعلی نبود خرید:** اجرای قدیمی main در snapshot23:50UTC،۱۵تصمیم شامل۱۱MODEL_DECISION و۴HOST_FALLBACK (یک timeout و سه رد host/schema)،۰order/۰fill داشت. مدل واقعاً دادهٔ زنده را تحلیل می‌کند، اما WAITمی‌دهد؛ breadthگزارش‌شده۳٫۲۸٪ و median24hحدود−۵٫۰۱٪ بود. حتی USOONبا قدرت نسبی و روند مثبت کوتاه، به‌نظر مدل شاهد کافی برای بیش از۲٪رشد آینده نداشت و هزینهٔ fee+spreadحدود۰٫۷۲٪بود. این دلیل مدل است، نه اثبات نبود فرصت در کل بازار. مدل۹نماد متفاوت درخواست کرده و contextهای معتبر فقط۶نماد متفاوت داشتند؛ پوشش عمیق محدود و خطاهای فنی نیز سهم دارند. نبود ENTERبا بسته‌بودن جداگانهٔ مسیر پول واقعی/UNKNOWN فرق دارد. quotaورود یا کاهش دلخواه gateبرای ساخت خرید، راه‌حل نیست.

**آخرین نامزد، پس از انتقال اولیه:** شاخهٔ `market-research-coverage` / `dacb5a6` پوش شده، اما هنوز روی main ادغام/فعال نشده است؛ source3799e4aاجرای سه‌ساعتهٔ قبلی منجمد مانده. نامزد، پژوهش۱۰نمادی، پوشش durable، bid/askدرcontext، سقف پیش‌فرض۱۰۰k و اجرای paperبا عمق کل quantity/limit رزروشده و stopمعوقِ پایدار دارد. افزایش خودکار حجم و چند موقعیت هم‌زمان در آن نیست.۳۷۱هسته/۱۰داشبورد و۴self-check، Ruff وcompileall پاس شدند.

**آزمون واقعی نامزد در23:38UTC:** مدل از۵۴بازار۱۰نماد خواست و۸داده معتبر پذیرفته شد؛۲HTTPمدل/۲۱GET و۳۵٫۳۲۸ثانیه، WAITمعتبر و binding/hashتأییدشده. این diagnosticعمداً remaining_seconds=0داشت؛۰سفارش/۰fill/STOPPED_FLAT، نه آزمون سودآوری یا ورود با افق تأمین‌شده. fundedforward، positionreviewو حساب واقعی نامزد هنوز آزموده نشده‌اند. گزارش محلی `artifacts/candidate-provider-diagnostic/coverage-provider-diagnostic-20261022T233813Z/diagnostic-summary.json`؛ جزئیات در [وضعیت جاری](docs/current-market-readiness.md). پس از terminalمعتبر اجرای قبلی، diff/ادغام و runتازه بررسی شوند؛ sourceوسطrunتغییر نکند.

این سند را به‌عنوان مأموریت ادامهٔ پروژه بخوان؛ گزارش‌های تاریخی آن، جای بررسی وضعیت فعلی را نمی‌گیرند. زمان ثبت این انتقال: 2026-10-23 حدود02:45 به وقت تهران، برابر2026-10-22 حدود23:15UTC. ممکن است هنگام خواندن، فرایندها تمام شده یا کد تغییر کرده باشد.

## مأموریت و نقش‌ها

تو مهندس ارشد، ارزیاب مستقل و راهبر اجرای پروژهٔ «رویین»، موتور معاملاتی هوشمند والکس هستی. کاربر مالک محصول و اپراتور حساب اختصاصی چالش است؛ تصمیم‌های محصول، اعتبار و کلیدهای محلی را فراهم می‌کند و باید بتواند منطق سیستم را برای داور توضیح دهد. نام و اطلاعات شخصی اعضای تیم برای ادامهٔ مهندسی لازم نیست و وارد مستندات نمی‌شود.

پروژه برای «هکاتون آنلاین Agentic AI استارکوچ»، چالش Wallex ساخته می‌شود. هدف مسابقه، الگوریتم خودکار مبتنی بر AI با منطق قابل توضیح، سود خالص قابل بررسی، مدیریت ریسک و امکان اجرای مجدد است. سرمایهٔ اختصاصی۵٬۰۰۰٬۰۰۰ تومان، مدت اعلام‌شده سه روز و معاملات فقط اسپات بدون لوریج/borrow/short هستند. معاملهٔ دستی، self-trading، معاملات هماهنگ و wash trading ممنوع‌اند. بازار فعال باید از سیاست حساب و فهرست ممنوعه عبور کند؛ فهرست۳۴۵تایی ارائه‌شده توسط کاربر را سلیقه‌ای تغییر نده.

بریف و متن ویدئو توسط کاربر ارائه شده‌اند؛ [docs/challenge-brief.md](docs/challenge-brief.md) الزام گزارش‌شده، مشاهدهٔ منبع، تصمیم داخلی و مجهول را جدا می‌کند. صفحهٔ عمومی: https://starcoach.ir/hackathon/agentic-ai . مشخصات API از https://developers.wallex.ir/docs بررسی شده‌اند؛ رفتار حساب هکاتون باید جدا آزموده شود.

بارم گزارش‌شده از۳۰۰: سود نهایی۹۰، کنترل افت۳۰، فعالیت منظم و معقول۱۵، پایداری۱۵، منطق استراتژی۴۰، استفادهٔ واقعی ازAI۳۵، مدیریت سرمایه/ریسک۳۰، بازتولید۲۵، بک‌تست و سایه۲۰. سود رتبه‌ای است؛ هیچ نمره‌ای با تعداد تست، معماری، WAIT یا یک معامله تضمین نمی‌شود. نمرهٔ کامل و سود ثابت وعده نده.

خروجی لازم: سورس GitHub مطابق نسخهٔ ایجادکنندهٔ معاملات، سند منطق/معماری/AI/ریسک/اجرای مجدد، لاگ دلیل هر معامله و ویدئوی حدود۵دقیقه؛ نبود ویدئو موجب حذف است. بازده پایه نسبت به۵M، پس از fee؛ پایان، سود به تومان realized شود و residual پنهان نماند. مثال۶٫۲۵M در بریف سود صحیح۱٫۲۵M و بازده۲۵٪ دارد. پایان اعلام‌شده توسط کاربر جمعه۲۳اکتبر۲۳:۵۰ تهران بوده؛ قبل از هر اجرا، ساعت واقعی، انقضای اعتبار و مهلت ویدئو را بررسی کن، از زمان‌بندی قدیمی استفاده نکن.

هدف کاربر، افزایش واقعی سرمایه با بهترین نتیجهٔ قابل دفاع است. صرف ساخت زیرساخت یا ماندن در paper پایان مأموریت نیست؛ در عین حال، سود پایدار هنوز اثبات نشده و افزایش ریسک جای فقدان شواهد را نمی‌گیرد.

## اولین کار تو؛ پیش از هر تغییر

1. در `D:\royin-trading-agent` وضعیت Git، شاخه، آخرین commitها، diff و فایل‌های untracked را بررسی کن. تغییر هم‌زمان دیگران را حفظ کن. `AGENTS.md`، سپس `README.md`، `TASKS.md`، `memory.md`، `ARCHITECTURE.md` و قراردادهای مرتبط در docs را بخوان. فایل حذف‌شده را فقط به دلیل نامش در گزارش قدیمی دوباره نساز.
2. کاربر PR شاخهٔ قبلی را merge و شاخهٔ remote را حذف کرده؛ main با merge `b8a1cbf` همگام شد. این انتقال روی main ثبت می‌شود. طبق دستور تازه، روی main ادامه بده؛ اگر بعداً شاخه لازم شد، پیشوند `codex/` نگذار. `git fetch --prune origin` و تطبیق upstream فقط با حفظ تغییرهای محلی. force push، reset و بازنویسی تاریخچه خودسرانه ممنوع.
3. فرایند فعال پایین را با heartbeat، PID و محتوای manifest بررسی کن؛ فایل RUNNING یا lock به‌تنهایی شاهد حیات نیست. worker دوم روشن نکن. هنگام اجرای منجمد، src/scripts/config/وابستگی‌ها را تغییر نده. تغییر MD منبع اجرای آن را تغییر نمی‌دهد.
4. قبل از اصلاح، همهٔ caller/test/fixture/config/export مرتبط را با `rg` پیدا کن؛ معیار پذیرش، دامنه و خطر پول/داده را روشن کن. کمترین تغییر کامل، بدون dependency یا abstraction اضافی.
5. R/S/D/U را جدا نگه دار: بریف، مشاهده، تصمیم، مجهول. تعداد تست coverage نیست؛ schema-valid سودآور نیست؛ public price، fill حساب نیست؛ پیش‌بینی درست، معاملهٔ سودده نیست.

## مسیر طی‌شده و علت انتخاب‌ها

ابتدا بریف، Blueprint محلی و گزینه‌های framework بررسی شدند. Blueprint حقیقت یا معماری الزام‌آور نبود. Python، Pydantic AI، خروجی ساخت‌یافته، Decimal و SQLite انتخاب شدند؛ ORM و frontend پیچیده لازم نبود. Gemini اولیه کنار رفت و BoxAPI با مدل واقعی `gpt-6-luna` و reasoning=none مسیر فعلی است؛ Google/OpenAI مستقیم fallback نیستند. framework به‌تنهایی مزیت مالی ایجاد نمی‌کند.

دو مسیر موازی اولیه، داده/ویژگی علّی/قرارداد تصمیم/AI و لجر/ریسک/شبیه‌سازی را ساختند. یکپارچه‌سازی مستقل خطاهای مهمی مثل SUM ممیزشناور SQLite، رزرو ناکافی fee، fill خارج LIMIT، RSI بازار تخت، از دست رفتن stop/high-water پس از restart، fill تکراری متفاوت، قیمت‌گذاری صفر برای دارایی فاقد quote و دور زدن بودجه را اصلاح کرد. گزارش تحویل Agent را شاهد قطعی ندان؛ تست و مسیر واقعی را بخوان.

ارزیابی تاریخی ابتدا روی تتر/تومان متمرکز بود. دادهٔ minute/native در OHLC و cadence اختلاف داشت؛ یک پنجره۱۵دقیقه‌ای۶۷۲کندلی و بعد۶۲۳کندل native ساعتی در دو قطعه بررسی شدند. گپ۲۲سپتامبر۱۳:۰۰UTC حذف یا fill نشد. این داده‌ها DIAGNOSTIC_ONLY ماندند؛ علت اختلاف، خرابی مشخص سرور ثابت نشده است. برخی درخواست resolution مورد انتظار را برنگرداندند. timestamp آغاز کندل، حجم و finality منبع هنوز محدودیت تشخیصی دارند.

۶ و سپس۱۲ پیکربندی استراتژی و مقایسهٔ cash/hold با ریسک یکسان/rule/rule_ai ساخته شد. نامزد مستقل سودآور پذیرفته نشد. بازده‌های مثبت برخی گزارش‌های قدیمی/fake، اثبات مزیت AI جاری نیستند. سپتامبر۲۴–۲۷ قبلاً در diagnostics دیده شده و holdout دست‌نخورده نیست. N≥30 معیار داخلی بود، نه قانون مسابقه یا تضمین آماری.

کارمزد تیکر تومان۰٫۳۰٪ هر سمت است؛ حدود۰٫۶۰٪ رفت‌وبرگشت قبل از spread/slippage. با فرض۰٫۰۵٪ لغزش هر سمت، اصطکاک حدود۰٫۷۰٪ است، نه زیان قطعی تمام استراتژی‌ها یا نیاز به۰٫۷٪ «سود خالص» برای سربه‌سر. از یک هفته USDTTMN به تمام بازارها تعمیم نده. ATR بزرگ‌تر از fee، به‌تنهایی expected edge نیست.

رانر paper قدیمی قواعد impulse را اجرا می‌کرد و الزاماً `agent.decide` را صدا نمی‌زد. مسیر جدید `run_market_paper.py` با نقش‌های واقعی Entry Analyst و Position Reviewer ساخته شد؛ لفظ AI در نام runner کافی نیست. ادعاهای قدیمی «دوبل فسادناپذیر»، «ماسک۱۰۰٪ secret»، «پوشش۱۰۰٪ تست»، «۳۰۰تضمینی» یا «Reflexion یعنی یادگیری ثابت‌شده» معتبر نیستند.

کاربر با محدود کردن انتخاب به تتر یا چند ارز ثابت و سقف سود ثابت مخالف است. اکنون مدل catalog نقدشوندهٔ واجد شرایط را می‌بیند، حداکثر۵ نماد را برای دادهٔ عمیق انتخاب می‌کند و بر batch معتبر تصمیم می‌دهد. افق پژوهشی۵دقیقه تا۱۰ساعت است، درون زمان تأمین‌شدهٔ واقعی اجرا. target بالای۲٪ هدف gross است، نه تضمین و نه اجازهٔ خرید هر بازار پرنوسان. سود می‌تواند از۲٫۵٪ عبور کند؛ checkpoint الزام فروش نیست.

از TradingAgents در revision `e8f5503e9b86d5c2710b0c76b1f686703968c9df`، تخصص نقش و بررسی شواهد موافق/مخالف اقتباس شد. swarm، debate طولانی، تحلیل سهام و سپردن ریسک به مدل کپی نشد. تعداد agent یا bull/bear خودبه‌خود سود را بهتر نمی‌کند؛ اضافه شدن نقش نیازمند ablation همسان است. حافظهٔ متنی Reflexion نباید پس از چند معامله، سیاست ریسک یا آزمایش را پنهانی تغییر دهد.

## معماری واقعاً موجود

- `market_data.py`, `markets.py`, `market_context.py`: اعتبارسنجی بازار/کندل، metadata و heuristic رژیم. مسیر فعلی انتخاب، TMN است؛ مسیر multi-currency USDT ضمنی فرض نشود.
- `features.py`: SMA/RSI/ATR/Bollinger/حجم/شدو و evidenceهای علّی، snapshot hash و prefix-invariance؛ آینده فقط برای outcome، هرگز ورودی تصمیم نیست.
- `decision.py`, `agent.py`: پیشنهاد typed، symbol/cutoff/hash/evidence متصل، forecast با q10/q50/q90 و horizon، ابزار خواندنی محدود. مدل کلید، shell، URL دلخواه، ابزار خام سفارش یا تغییر ریسک نمی‌بیند. top-level target/stop legacy باید null باشند؛ forecast بازار، سیاست stop میزبان نیست.
- `market_context.py` و collector: catalog فعال منهای ممنوعه؛ حداکثر۲۵۶ ردیف نقدشونده و سقف انتخاب۵. در مشاهدهٔ واقعی۴۶۹ بازار catalog،۱۲۰ واجد شرایط و۵۴ بازار تومانی نقدشونده دیده شدند؛ این اعداد ثابت همیشگی نیستند. حد گردش۱۰۰M و طبقه‌بندی bull/bear سیاست heuristic هستند، نه قانون بریف یا احتمال کالیبره‌شده.
- `ledger.py`: SQLite، free/locked/total، intent و fee-reserve اتمیک، fill idempotent، Decimal، بهای تمام‌شده و PnL. آن را بدون قرارداد مستقل حسابداری دوبل ننام.
- `risk.py`, `broker.py`: حداقل/گام/fee، موجودی، exposure، freshness، deadline، stop/trailing/high-water پایدار و مستقل از LLM. stop پایین نمی‌رود، protection horizon برابر cutoff+horizon است، نه زمان ارسال+horizon. قطعی اینترنت قیمت stop را تضمین نمی‌کند.
- `live_broker.py`, `canary.py`: قرارداد آفلاین سفارش و transport واقعی بسیار محدود canary؛ موتور live عمومی آماده نیست.
- `model_budget.py`: رزرو بادوام قبل از HTTP؛ invoice و usage واقعی با رزرو متفاوت‌اند. بودجه با restart reset/refund نشود.
- `scripts/run_market_paper.py`: orchestration فعلی paper واقعی/مصنوعی، محدودیت زمانی/درخواست و manifest مستقل؛ `run_paper_trader.py` علاوه بر legacystrategy، helper جمع‌آوری داده دارد. `run_shadow.py` مسیر قدیمی مشاهده است؛ Candidate آن بسته مانده و با current paper یکسان نیست.
- `dashboard/`: localhost8765، فقط‌خواندنی، curve/مانده/تصمیم/ریسک/شواهد را از دادهٔ صادرشده و snapshot می‌خواند؛ endpoint خرید/فروش یا ارسال کلید به مرورگر ندارد. سبز بودن UI سلامت موتور/صرافی را ثابت نمی‌کند.

## حساس‌ترین رخداد مالی؛ فراموش نشود

حساب اختصاصی فعال و۵M تومان آزاد با API خواندنی مشاهده شده؛ کارمزد اعتبار طبق گزارش کاربر صفر است. کارمزد TMN خوانده‌شده maker=.0025/taker=.003 است؛ USDT طبق گزارش کاربر .001/.0013. همه را قبل از معامله تازه تأیید کن. metadata عمومی USDTTMN یک بار minNotional=50000، minQty=.01، stepSize=2، tickSize=0 داشت؛ step/tick تعداد اعشارند.۱۰۰یا۳۰۰هزار را حداقل ثابت همهٔ نمادها ننویس؛ فروش‌پذیری پس از fee/rounding مهم است.

**یک تلاش واقعی فنی در revision `e7d8bc5` به BUY_UNKNOWN رسید.** سقف debit۱۰۰k، یک BUY/یکSELL و۸درخواست سفارش: POST۱، DELETE۱، GET۶. بدنهٔ POST خالی بود و نسخهٔ قدیمی status HTTP را ذخیره نکرد؛ علت دقیق را نمی‌دانیم. GET همان شناسه404بود؛ این به‌تنهایی REJECTED یا finality تاریخی نیست. کاربر در UI چیزی ندید. بررسی‌های بعدی API، هویت حساب درست،۵M آزاد، صفر قفل، صفرUSDT، تاریخچهٔ کاملِ بدون فیلتر خالی و سفارش باز صفر نشان دادند. زیان یا fill واقعی قابل مشاهده تأیید نشده است.

کلید جایگزین طبق تأیید کاربر از داخل حساب اعتباری و با مجوز معامله ساخته شده؛ دوباره همین سؤال‌ها را نپرس و منشأ کلید/نبود مجوز را علت قطعی ندان. کلید فقط `.env` محلی است؛ آن را چاپ یا وارد prompt/گیت نکن.

intent، reserve قبلی و شمارنده۸attempt را حفظ کن. state مشترک حساب در `~/.royin-credit-state/<account-sha256>/canary.sqlite3` و قفل در `~/.royin-credit-locks/` است؛ clone تازه مجوز state تازه نیست. پاک‌کردن DB، آزادکردن دستی reserve، ID تازه یا resetcounter برای عبور از UNKNOWN ممنوع. مسیر فعلی status را پیش از خواندن body ثبت می‌کند، ولی status گذشته قابل بازسازی نیست.

`RUN_MODE=live` عمومی در config رد می‌شود؛ WallexLiveBroker هر transport دلخواه را قبول نمی‌کند. CreditCanaryTransport فقط مسیر محدود شرح‌داده‌شده در [docs/credit-canary.md](docs/credit-canary.md) است و تکرار `--execute` برای bypass مجاز نیست. شش GET آخرِ بررسی مستقل نیز مانده و تاریخچهٔ خالی را تأیید کردند، نه علت POST گذشته را. packet بدون کلید در `.local/review/market-readiness/wallex-order-support-packet.md` موجود است؛ پیامی به پشتیبانی از طرف کاربر ارسال نشده. درخواست قبلی کاربر بررسی خودمان بود؛ او را برای همان سؤال‌های حل‌شده معطل نکن.

MCP فعلاً ابزارهای عمومی markets/spotmarkets/candles/depth/latesttrades دارد؛ ابزار خصوصی سفارش/حساب در ابزارهای در دسترس دیده نشد. بررسی خصوصی با REST انجام شد. public trades را fill شخصی ندان. حساب اصلی، انتقال، برداشت و فعال‌سازی طرح خارج scopeاند.

## آخرین اجرای زندهٔ paper و بهترین دستاورد

run `net-return-forward-20261023-2` از source `3799e4a`، شروع حدود2026-10-22T22:37Z، برنامهٔ سه‌ساعته تا حدود2026-10-23T01:38Z،۱۸۱چرخه/فاصله۶۰ثانیه/سقف۱۲۰۰GET، سقف سفارش مجازی۱۰۰k، سرمایه مجازی۵M، مدل واقعی gpt-6-luna و دادهٔ عمومی زنده. هیچ مجوز معاملهٔ واقعی ندارد.

source bundle:
`679ded0dd092780ec41720411f5a1b61fbb676e34277f3c28f96873abcb1fb8e`

manifest: `artifacts/market-paper/net-return-forward-20261023-2/manifest.json`؛ handle/PID محلی: `.local/review/market-readiness/active-forward-process.json`. session4545 و PIDهای5016/11848 قبلاً تأیید شدند؛ به اعتبار همین شماره در چت جدید اتکا نکن، امکان دسترسی به session چت قبلی تضمین نیست. با فرایند/heartbeat تطبیق بده. آخرین poll هنگام تحویل، فرایند را زنده نشان داد. هنگام ثبت این سند، منبع اجرا با main یکسان بود؛ commit مستندات revision سودساز جدید ایجاد نمی‌کند.

بهترین دستاورد فعلی، **اجرای واقعی مسیر catalog→انتخاب مدل→دادهٔ عمیق→تصمیم bindشده و شواهد مستقل** است، نه سود اثبات‌شده. در اولین چرخه مدل از۵۴بازار،USOON/BNB/TRX/BTC/USDT را برای پژوهش خواست و۳نماد معتبر پذیرفته شدند؛ تصمیم WAIT صادر شد. bootstrap خراب USDTTMN قبلاً کل بازار را می‌بست؛3799 حداکثر۳seed نقدشونده را امتحان و عدم دسترسی را فقط برای cutoff جاری اعلام می‌کند، بدون ضعیف کردن qualitygate.

در snapshot23:11UTC،۷trace شامل۵پیش‌بینی معتبر و۲fallback بودند؛ یکی timeout۳۰ثانیه و دیگری خطای evidence بود. مدل برای USOON در top-level از EV_TREND_BULLISH مربوط به TRX استفاده کرده بود؛ host درست رد کرد. آرایه evidence در forecast معتبر بود، اما کل تصمیم نبود. شواهد هر دو سطح باید متعلق به نماد منتخب باشند؛ دلیل می‌تواند بازارهای دیگر را با نام مقایسه کند. validator را برای سبزشدن ضعیف نکن.

در بررسی پس از آن۸تصمیم، صفرorder/fill، صفرPnL و۵M مجازی دیده شد؛ نتیجهٔ نهایی سه‌ساعته هنوز نبود. `PASS_DATA_ONLY` یا `worker_state=RUNNING` را پذیرش سودآوری نخوان. این اجرا بازار نزولی دیده؛ WAIT لزوماً ضعف نیست و معاملهٔ اجباری برای فعالیت ممنوع است.

### نتیجهٔ تازهٔ آینده‌نگر، نه بک‌تست بازنویسی‌شده

در23:11UTC، کپی ثابت از manifest گرفته و فقط با۱GET عمومی سنجیده شد:۵پیش‌بینی صادرشده،۱scored،۴pending،۰missing؛ وضعیت PARTIAL_FORECAST_DIAGNOSTIC و exit1. اولین USOON با افق۱۸۰۰ثانیه،q50=−۰٫۴٪؛ بازده واقعی close انتهای افق=−۰٫۰۵۳۲۵٪. جهت منفی درست بود، اما خطای مدل۰٫۳۴۶۷۵واحددرصد و baselineصفر۰٫۰۵۳۲۵واحددرصد بود؛ مدل ضعیف‌تر از baseline بود. این WAIT است، نه زیان یا سود حساب.

گزارش: `artifacts/forecast-outcomes/20261022T231125Z_142a366e/report.json`؛ ورودی ثابت: `artifacts/forecast-input-snapshots/20261022T231115Z/manifest.json` همراه provenance/hash. هیچ مدل پولی یا درخواست سفارش در این سنجش اجرا نشد. این خروجی محلی ignored است و در clone تازه وجود ندارد.

پیش‌بینی‌های قبلی USOON/PUMP نیز روی point error از صفر بهتر نبودند؛ سه پیش‌بینی مثبت دیگرUSOON در پایان بازده منفی داشتند. بازهٔ عریض با coverage چند نمونه، calibration نیست؛ نمونه‌های همان جلسه هم‌بسته‌اند. افق‌های۱۰ساعتهٔ قدیمی PEPE هنگام تحویل هنوز بعضاًpending بودند. پیش‌بینی terminal با سود معاملهٔ trailing یک metric نیست.

### وضعیت آزمون مهندسی

آخرین source3799:۳۶۰تست هسته پاس، Ruff و compileall موفق؛ در مرحلهٔ تلخیص مستندات۱۰تست داشبورد پاس شد، لینک‌ها، عدم تطابق کلید واقعی/PII و hash آرشیو بررسی شدند. این انتقال تغییر کد موتور ندارد؛ نتیجهٔ قبلی را اجرای تازه جا نزن. ساخت wheel در مراحل قبلی پاس شده؛ برای این انتقال از نو اجرا نشده است. گزارش‌های۲۷۹/۲۴۶/۱۸۷ یا سود سناریوی مصنوعی، مربوط به revision/آزمون‌های دیگرند.

## ادامهٔ دقیق؛ با خروجی قابل سنجش

1. **تحویل اجرای موجود:** منبع را ثابت نگه دار؛ تا پایان معتبر یا خرابی واقعی، همان worker را پایش کن. counts واقعیvalid/fallback، علت، زمان،GET/HTTP/usage،order/fill،equity،terminalstate را استخراج کن. اگر قطع شد، incomplete ثبت کن و terminaldata جعل نکن. آزمون فعال را با restart/reset بی‌صدا عوض نکن.
2. **سنجش موعدها:** از manifest فعال کپی بایتی ثابت با زمان/hash بگیر؛ همان را به scorer بده تا ورودی وسط GET عوض نشود. outcome دقیق minute با آغازcutoff+horizon−60 و انتظار۶۰ثانیهٔ finality فرضی؛ gap/stale/missing را pass نکن. چند پیش‌بینی یا source متفاوت را نمونهٔ مستقل/مقایسهٔ کنترل‌شده ننام.
3. **پس از پایان sourcefreeze، اصلاح‌های کوچک و ریشه‌ای:**
   - `_entry_rows` اکنون close/spread/depth/features را می‌دهد ولی best_bid/best_ask موجود در context را به مدل نشان نمی‌دهد. قیمت واقعی خرید ask است؛ targetازclose ممکن است با gap و fee مصرف شده باشد. quoteقابل اجرا/سن آن و اثر هزینه باید در تحلیل/گیت روشن شود. q50، expectedpayoff trailing نیست.
   - prompt دو آرایهٔ evidence را صریحاً به همان snapshot منتخب محدود کند؛ خطای واقعی cross-market بالا regression شود، نه cleanup یا جعل شاهد پس از مدل.
   - entrypaper تمام حجم را در bestask فرض می‌کند؛ برخی خروج‌ها bestbid را به کار می‌برند. عمق کافی برای اندازهٔ معامله، spread و قیمت محافظه‌کارانه بررسی شوند. عبور stop با قیمت تضمینی، fullfill بدون عمق و fallback به quoteقدیمی گزارش سود را غیرواقعی می‌کند. روش اجرای چندسطحیِ دقیق/محافظه‌کارانه را کوچک و تست‌شده طراحی کن؛ این اصلاح هنوز پیاده نشده است.
   - latencyواقعی۲۱تا۳۰ثانیه و timeout بررسی شود؛ سقف را بدون اندازه‌گیری یا آزادکردن budget زیاد نکن. ورودی زائد/ابزاررفت‌وبرگشت و hosterror را از خطای provider جدا کن.
4. **ارزیابی عملکرد:** قبل از outcome طرح را ثبت کن، development/validation/holdout زمانی یا forward معتبر داشته باش. cash،hold با همانrisk،rule،rule+AI با داده/fee/execution یکسان مقایسه شوند. سودخالص،drawdown،exposure،تعدادroundtrip،fee،residual،latency و baseline forecast گزارش شوند. آینده واردfeature نشود؛ آستانه را بعد از دیدن زیان برای سبزشدن عوض نکن. baseline و null/fallback را حذف نکن. منابع جهانی را از مقاله/کد/مستندات اولیه بخوان؛ قابلیت ترندشده جای شواهد روی والکس نیست.
5. **مسیر پول واقعی جداست:** رخداد UNKNOWN با قرارداد بازیابی مستند حل شود؛ transport محدود، ACK/fill/feeAsset/partial/cancelrace/restart، minimum/step/expiry/finality و تطبیق مانده در شرایط واقعی باید بررسی شوند. مشاهدهٔ حساب خالی اجازهٔ resetstate نیست. کاربر قبلاً پایلوت کوچک را خواسته؛ برای همان مجوز/کلید تکرار سؤال نکن، اما از محدودیت فنی دور نزن. پس از احراز، کوچک‌ترین معاملهٔ الگوریتمیِ قابل فروش و سقف روشن، یک worker و sourceتمیز/commitشده اجرا شود. افزایش حجم تنها پس از شواهد اجرا و ارزیابی، نه صرف دو معاملهٔ تصادفی موفق.
6. **تحویل مسابقه:** replayپاک‌سازی‌شده و قابل اجرا درcloneتازه، source/config/prompt/model/datahash،دلایل متصل به سفارش و گزارش واقعی/شبیه‌سازی جدا؛ سپس ویدئوی۵دقیقه با نتیجه و محدودیت صادقانه و ارسال زودتر ازمهلت. لینکGit بدونrawمجاز، replayکامل را ثابت نمی‌کند.

## دستورها و مرزهای عملیاتی

ازPowerShell ریشه؛ روی `.venv` موجود venvنساز و `.env` را overwriteنکن:

```powershell
git status --short
git log -8 --oneline
.\.venv\Scripts\python.exe -m royin check-config --env-file .env.example
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m unittest discover -s dashboard/tests -v
.\.venv\Scripts\python.exe -m ruff check src scripts tests dashboard
.\.venv\Scripts\python.exe -m compileall -q src scripts tests dashboard
.\.venv\Scripts\python.exe -X utf8 scripts/run_market_paper.py --help
.\.venv\Scripts\python.exe -X utf8 scripts/run_market_paper.py --self-check
.\.venv\Scripts\python.exe -X utf8 -m scripts.score_market_forecast --help
```

سنجش روی **کپی ثابت و موجود**:
```powershell
.\.venv\Scripts\python.exe -X utf8 -m scripts.score_market_forecast --paper-manifest <immutable-manifest-path> --score
```

scorer سقف۳۲GET،بدونretry/مدل/سفارش دارد؛ exit1PARTIAL یعنی pending وجود دارد،نه passکامل. ابزار قدیمی `--run-dir` را با قرارداد manifestجاری مخلوط نکن. configpass فقط VALID_CONFIG_ONLY است، نه موتور/حساب/مجوزtrade.

کاربر مصرف واقعی BoxAPI را کم گزارش کرده و کیفیت را بر صرفه‌جویی افراطی مقدم می‌داند؛ ولی counterهای ایمنی را حذف نکن. budgetpolicyv3:input32768/output1024؛ scopeجدید۴۸نقش/۹۶HTTP/USD.50،globalUSD2.40،روزانهUSD.80/۲۰۰request؛ هرنقش max۲HTTP/۱ابزار وtimeout۳۰ثانیه. scopeقدیمی سقف قبلی دارد؛ رزرو با invoiceفرق دارد. `data/llm-budget.sqlite3` resetیاrefundخودکار ندارد. cap probeهای جداگانه ممکن است کمتر باشد؛ flag واقعی را ازhelp بخوان.

کلیدهایWallex/BoxAPI و شناسهٔ حساب فقط تنظیمات محلی‌اند؛ مقدارشان را حتی برایdebug چاپ نکن. `.local/`،`data/`،`artifacts/`،SQLite،رسانه و `.env` بهGitنروند. قدیم۳۲Markdown به۱۸سند فعال تلخیص و۱۴سند قدیمی در`.local/docs/history-c3a655c` باhashآرشیو شدند؛ درGitتاریخچه موجود است،درcloneتازه آرشیومحلی نیست. این HANDOFF طبق درخواست صریح کاربر سند فعال تازه است؛ فایلpromptشخصی اضافه نساز.

پس ازهرمرحله TASKS/memory فقطباواقعیت پایدار به‌روز شوند. فایل‌ها صریحstage،بدون`git add .`کورکورانه؛ commitیکعنوان،خطخالی وبدنهٔ چندخطی شامل دلیل/تغییر/آزمون/محدودیت داشته باشد. amend یاrewritetاریخچه فقطبا درخواستصریح؛ نسخهٔ معاملاتی محفوظ. مخزنPrivateبماند،pushعادی مطابق مأموریت؛ forcepushممنوع.

کار را با گزارش کوتاهِ «چه چیزی واقعاً زنده است، چه چیزی واقعاً اجرا شده، چه چیزی هنوز مسدود است و اولین اقدام مستقل چیست» شروع کن و سپس اقدام کن. برای توسعهٔ آینده، نقش اضافه، معیار احتمال/اطمینان، بازار یا حدسود را به دلیل ظاهری جذاب‌تر بودن انتخاب نکن. هدف، نتیجهٔ مالی واقعی و قابل دفاع همراه ریسک و بازتولید است؛ هنوز در نقطهٔ اثبات سودآوری یا production readiness نیستیم.
