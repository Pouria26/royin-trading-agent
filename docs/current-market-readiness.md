# وضعیت جاری موتور و شواهد

## بررسی میزبان تازه — ۲۳ اکتبر، ۰۶:۳۷ تهران

**وضعیت اجرا/شواهد اصلی UNCONFIRMED است؛ ادعای RUNNING در ادامه تاریخی است.** این clone روی main است و source bundle `679ded0d…1fb8e` تغییر نکرده؛ فرایند متناظر، artifacts، `.env` و DBهای اصلی اینجا وجود ندارند. موجودی امروز خوانده نشده است. پایان یا مالکیت worker میزبان قبلی از نبود process محلی نتیجه نمی‌شود.

نامزد آفلاین `08f403c` در worktree متصل `offline-evidence`، بر مبنای `a76a420` آماده و commit شد؛ هنوز main یا worker آن را اجرا نمی‌کند. گارد ادامهٔ بودجه، گیت هزینهٔ target، peak/round-trip واقعی، cadence بادوام و replay محدود اضافه شده‌اند. snapshot دقیق stage‌شده با lock تازه:۳۹۳هسته/۱۰داشبورد/۴self-check،Ruff0.17.1 وcompileall پاس؛config فقطVALID_CONFIG_ONLY. logهای این آزمون‌ها محلی و ignored هستند. هیچ آزمون تازهٔ مدل/provider/حساب یا سود واقعی انجام نشده است.

قبل از هر درخواست پولی باید DB اصلی معتبر منتقل و مالک اجرای واحد احراز شود. قبل از live نیز BUY_UNKNOWN و canary با۸attempt مصرف‌شده باقی‌اند؛ ID/reserve/counter بازسازی یا reset نشد. ادامه و حدود شواهد در [TASKS](../TASKS.md) و [HANDOFF](../HANDOFF.md) ثبت است.

به‌روزرسانی۲۳اکتبر۲۰۲۶ به وقت تهران. **کار در جریان است؛ اجرای عمومی با پول واقعی و سودآوری پایدار تأیید نشده‌اند.** هدف همچنان انتخاب چندبازارهٔ AI، کنترل ریسک و خرید/فروش واقعیِ قابل بررسی است؛ آزمون کاغذی جای آن را نمی‌گیرد.

## وضعیت قابل تأیید

| بخش | شاهد موجود | آنچه هنوز ثابت نشده |
|---|---|---|
| انتخاب بازار | source3799e4a؛ کاتالوگ۴۶۹، واجد شرایط۱۲۰،۵۴ TMN نقدشونده؛ مدل تا۵ نماد را انتخاب می‌کند | تحلیل عمیق همهٔ بازارها یا مجوز خصوصی همهٔ نمادها |
| AI واقعی | BoxAPI/gpt-6-luna، دو نقش، tool/response/usage و evidence مرتبط | برتری معاملاتی بر قاعده و سود پایدار |
| افق/هدف |۳۰۰..۳۶۰۰۰ثانیه و هدف gross بالای۲٪؛ ورود محدود به زمان تأمین‌شدهٔ run | بازده قطعی یا حذف کارمزد |
| بازار نزولی | breadth و median تعدیل‌شده با FX، gate استثنای قدرت نسبی | احتمال برد کالیبره‌شده در همهٔ رژیم‌ها |
| ریسک/حسابداری | Decimal، intent/fill پایدار، stop/trailing/deadline مستقل،۳۶۰ تست هسته در۵۲.۰۷۱ثانیه | حفاظت مطلق از زیان، صفر dust یا آزمون کامل صرافی |
| حساب واقعی | آخرین GETها:۵M cash آزاد،۰locked،۰USDT، تاریخچهٔ کامل/باز خالی، همان ID404 | finality و علت پاسخ خالی canary؛ معاملهٔ واقعی موفق |
| بازتولید | hashes، lock، آزمون آفلاین، manifest و trace محلی | بستهٔ کامل replay داوری از clone بدون raw خصوصی |

جزئیات حساب و محدودیت‌ها در [credit-canary](credit-canary.md)، داده در [market-data-semantics](market-data-semantics.md) و ارزیابی در [evaluation-plan](evaluation-plan.md) است.

## آزمون واقعی نامزد ده‌نمادی — 23:38UTC

شاخهٔ `market-research-coverage` در source `dacb5a6` جدا از اجرای منجمد main آزموده شد. run محلی `coverage-provider-diagnostic-20261022T233813Z`: catalog۴۶۹/eligible۱۲۰/model-visible۵۴؛ مدل۱۰نماد درخواست کرد و۸دادهٔ معتبر پذیرفته شد.۲HTTPمدل با۲پاسخ،۲۱GETعمومی، زمان نقش۳۵٫۳۲۸ثانیه، usageگزارش‌شده۸۴۴۱input/۶۰۶output و رزرو پایدارUSD0.00871424 در همان budget اصلی ثبت شد؛ رزرو صورتحساب نیست.

تصمیم MODEL_DECISION/WAIT بود و شواهد به snapshot منتخب متصل ماندند. مدل askحدود۰٫۲۰٪ بالاتر از close و هزینه/بازار نزولی را در دلیل لحاظ کرد. USDTTMN خطای داده داشت؛ ARBTMN در snapshot spreadحدود۰٫۶۹۷۸٪، بیش از سقف داخلی۰٫۵٪ داشت. هیچ gate برای پذیرش آن‌ها ضعیف نشد. hashتمامcaptureها و تطابق forecast با پاسخ واقعی provider با scorer موجود، آفلاین بررسی شدند؛ raw و گزارش خصوصی/محلی ignored هستند.

این آزمون عمداً یک چرخه با remaining_seconds=0 و فاقد افق تأمین‌شدهٔ ورود بود؛۰سفارش/۰fill و STOPPED_FLAT. فقط سازگاری provider/tool/context/مهلت۶۰ثانیه و گسترش واقعی پژوهش تأیید محدود شد؛ نه سودآوری، تصمیم ورود در افق معتبر، پایش موقعیت، بهبود کنترل‌شده نسبت به نسخهٔ قبلی یا حساب واقعی. source اجرای main تغییر نکرد و قبل از terminal معتبر آن، نامزد فعال نمی‌شود.

سنجش جداگانهٔ اجرای قبلی در23:38UTC:۹forecastمعتبر،۳scored/۶pending،۰missing و۳GET. هر سه outcome فعلاً USOON و هم‌بسته‌اند؛ میانهٔ خطای مطلق مدل۰٫۱۹۷۲واحددرصد و baselineصفر۰٫۳۹۷۲واحددرصد شد. این مشاهدهٔ کوچک برتری معاملاتی یا calibration نیست. مسیر محلی `artifacts/forecast-outcomes/20261022T233833Z_695d034a/report.json`؛ با نتایج sourceهای دیگر ترکیب نشود.

## آزمون منجمد تاریخی — اجرای امروز UNCONFIRMED

شناسه `net-return-forward-20261023-2`، source3799e4a؛ کد هنگام اجرا ثابت بماند. مدت۱۰۸۰۰ثانیه،۱۸۱چرخه با فاصله۶۰ثانیه، سقف۱۲۰۰GET عمومی،۵M موجودی و سقف۱۰۰k سفارش **مجازی**، مدل/API عمومی واقعی.

فرمان اجراشده زیر را تا زنده بودن worker تکرار نکنید. run جدید به ID/source/profile تازه نیاز دارد؛ DB قبلی را پاک نکنید.

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/run_market_paper.py --model-mode REAL_MODEL --duration-seconds 10800 --cycles 181 --interval-seconds 60 --public-get-cap 1200 --horizon-max 36000 --order-tmn 100000 --run-id net-return-forward-20261023-2
```

اولین checkpoint۲۲:۳۸:۱۲Z:۱۱GET عمومی،۲HTTP واقعی مدل،۵۶۹۷input/۵۱۵output token؛ مدل USOON،BNB،TRX،BTC،USDT را بررسی خواست و سه candidate معتبر دریافت کرد. BTC فقط seed بود؛ سرمایه‌گذاری توسط host انتخاب نشده بود. مدل به دلیل ضعف روند/بازار نزولی WAIT داد و حدود۱۰۴۷۱ثانیه زمان قابل نگهداری داشت.

تا بررسی۲۲:۴۸Z سه چرخه تصمیم: دو MODEL_DECISION و یک HOST_FALLBACK ناشی از timeout،۰سفارش/۰fill و۰٪ بازده کاغذی. **این snapshot است، نه پایان آزمون.** status PASS_DATA_ONLY نتیجهٔ قبولی سود یا پذیرش live نیست. وجود RUNNING/lock نیز به‌تنهایی فرایند زنده را ثابت نمی‌کند؛ handle/PID باید بررسی شود.

اولین forecast تحقیقاتی USOON با cutoff۲۲:۳۵Z و horizon۱۸۰۰ثانیه، q50=-0.004 بود؛ outcome آن پس از۲۳:۰۵Z+۶۰ثانیه قابل سنجش است. [scorer](current-forecast-evaluation.md) نتیجهٔ نارس یا مفقود را جدا نگه می‌دارد؛ forecast مربوط به WAIT معامله ایجاد نمی‌کند.

Source bundle: `679ded0dd092780ec41720411f5a1b61fbb676e34277f3c28f96873abcb1fb8e`. manifest در `artifacts/market-paper/net-return-forward-20261023-2/manifest.json` محلی و ignored است. کد/تنظیمات را mid-run تغییر ندهید؛ مستندات می‌توانند بدون تغییر source bundle اصلاح شوند.

## یافته‌های مؤثر بر تصمیم بعدی

- آزمون کوتاه قبلی فرصت واقعی ورود نداشت: پس از buffer خروج۳۰۰ثانیه، زمان ناچیزی می‌ماند. از آن نتیجهٔ سودآوری یا ضعف استراتژی نگیریم.
- اجبار bootstrap روی USDTTMN، با gap آن بازار کل تحلیل را می‌بست. اجرای اول سه‌ساعته پیش از مدل و بدون سفارش متوقف و شکستش حفظ شد. fallback محدودِ حداکثر۳seed سالم و flags دادهٔ همان cutoff در source3799e4a اصلاح شده؛ forward-fill یا ممنوعیت دائمی جدید نداریم.
- چند پیش‌بینی واقعی گذشته از baseline صفر ضعیف‌تر بودند؛ سودهای+۰.۶۹٪/+۰.۷۳٪ گزارش قدیمی قاعده‌محور، اثبات سود AI نسخهٔ فعلی نیستند. آن گزارش و فرض‌هایش در آرشیو محلی و Git history مانده‌اند.
- ورود paper با ask مشاهده‌شده است، ولی context ورودی مدل هنوز best_bid/best_ask را صریح نمی‌دهد. بعد از پایان run، نسبت قیمت قابل اجرا/close قدیمی و هزینه بررسی شود. target نسبت به close، سود خالص ورود در ask را ثابت نمی‌کند؛ median terminal forecast نیز expected payoff معاملهٔ trailing نیست.
- تأخیر تحلیل، پایان نگهداری پیش‌بینی را تمدید نمی‌کند: expiry برابر cutoff+horizon است. stop/خروج با LLM قطع‌شده هم به وظیفهٔ میزبان وابسته است؛ قیمت خروج تضمین نمی‌شود.

## مسیر بعدی و تحویل

۱. همان فرایند فعال و خطاهایش را پایش؛ outcomeهای موعدرسیده را با GET عمومی و بدون تغییر source سنجش کنید.
۲. در پایان، terminal state، realized/MTM، fee، residual، drawdown، انتخاب نماد و valid/fallback را بررسی کنید؛ نبود فرصت معاملهٔ اجباری نمی‌سازد.
۳. context قیمت قابل اجرا، کیفیت مدل و گیت بازیابی سفارش قبلی را رفع و با داده/آزمون تازه بررسی کنید. پول واقعی تنها پس از قرارداد مالی معتبر وارد چرخهٔ کوچک الگوریتمی شود؛ افزایش حجم به شواهد وابسته است.
۴. بستهٔ replay مجاز، log دلیل هر معامله، تطابق سورس اجرا و ویدئوی حدود۵دقیقه آماده شود. معیارها در [بریف](challenge-brief.md)؛ امتیاز، stable profit یا production readiness خوداظهاری نمی‌شود.

[TradingAgents در revision بررسی‌شده](https://github.com/TauricResearch/TradingAgents/tree/e8f5503e9b86d5c2710b0c76b1f686703968c9df) برای تخصص نقش‌ها و نقد شواهد استفاده شد، نه کپی framework یا فرض انتقال سود سهام به والکس. معماری جاری در [ARCHITECTURE](../ARCHITECTURE.md) است.
