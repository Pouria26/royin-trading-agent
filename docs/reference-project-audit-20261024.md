# ممیزی مراجع و ارتقای مرحله‌ای رویین — ۲۴ اکتبر ۲۰۲۶

این گزارش ۳۱ مخزن یکتای فهرست کاربر را پوشش می‌دهد؛ لینک JimmyMac دوبار آمده بود. سه بررسی موازی، نسخه‌ها را به SHA ثابت بستند و کد مسیرهای اصلی استراتژی، AI، ریسک، اجرا و تست را خواندند. عمق بررسی هر مخزن در بخش مربوط آمده است. این ممیزی محدود به دامنهٔ ثبت‌شده است؛ هیچ کد یا تست ثالث اجرا نشد و سود، کالیبراسیون، استقرار یا fill واقعی هیچ مرجعی مستقلاً تأیید نشده است. یک مخزن فقط مستندات و یک مخزن طرح UI است؛ در موارد بزرگ، تمام framework یا آرشیوهای داده خوانده نشده‌اند.

## معماری واقعی رویین و انتخاب تغییر

مسیر مالی جاری از کاتالوگ مجاز و نقدشونده شروع می‌شود، دادهٔ کندل بسته و book را اعتبارسنجی می‌کند، با BoxAPI یک پژوهش حداکثر ده‌نمادی و تصمیم ENTER/WAIT می‌گیرد، سپس میزبان Decimal قیمت/حجم/کارمزد/عمق/موجودی/مهلت را مستقل بررسی می‌کند. intent و reserve پیش از ارسال ثبت می‌شوند؛ UNKNOWN با همان شناسه reconcile می‌شود و تکرار POST نداریم. یک موقعیت فعال؛ stop، trailing و خروج موعد به مدل وابسته نیستند. بودجهٔ پایدار، permit و حساب اعتباری قبلی حفظ می‌شوند. Position Reviewer در paper موجود است؛ مسیر مالی تازه خروج میزبان دارد، نه reviewer زندهٔ فعال. نمودار/دادهٔ paper معادل fill صرافی نیست.

| ایدهٔ منتخب | منبع source بررسی‌شده | تغییر واقعی رویین | مرز ادعا |
|---|---|---|---|
| prior-only channel، بازده چندپنجره، efficiency و حجم مبنای پیشین | Vela، Novo، ssinasaberii، BMD، AliFazelniya | EV_CLOSED_BAR_STRUCTURE از همان کندل‌های بسته؛ پیش از تصمیم به مدل می‌رسد | descriptor علّی است؛ سیگنال سودآور اثبات‌شده نیست |
| break-even و dossier هزینه پیش از مدل | Vela، Nova، ssinasaberii، Hamid | BOOK_COST_CONTEXT_V1 نسبت به close اصلی با ask gap، spread و فرض fee/slip؛ ظرفیت min/step/residual | برآورد پژوهشی است؛ گیت تازهٔ میزبان با fee/account/book واقعی پابرجاست |
| قضاوت متناسب با setup و افق | Public Trader، Vela | prompt میان breakout/reclaim/continuation تفاوت می‌گذارد و هدف دور را جای central forecast نمی‌نشاند | WAIT هرگز به ENTER تبدیل نمی‌شود؛ آستانه/سقف ریسک برای ساخت فعالیت تغییر نکرده |
| حسابداری fee/partial و عدم جعل fill | Hamid، Pedram؛ counterexampleهای GISOO/چند مرجع | بازبینی مسیر مالی خودمان دو ایراد reserve فروش و توقف دائمی dust را آشکار کرد؛ اصلاح محدود همراه تست انجام شد | fixture شاهد live نیست؛ باقی‌ماندهٔ کوینی همچنان گزارش می‌شود |
| provenance و ارزیابی مستقل | Novo، Shahin، fill models چند مرجع | trace زنده snapshot/hash/issued_at را نگه می‌دارد؛ scorer بازهٔ صریح از manifest اصلی می‌پذیرد | گذشتهٔ فاقد زمان صدور/تصویر معتبر، پذیرفته‌شده فرض نمی‌شود |

## اصلاح مالی و خرده‌موجودی

فروش مالی مقدار را به `floor_step(free / (1 + taker_fee))` محدود می‌کند تا در سناریوی کارمزد از base، وجه آزاد برای آن بماند. محاسبهٔ هدف، همین مقدار و هر چهار حالت کارمزد base/quote را با residual دارای ارزش نقدی صفر بررسی می‌کند. از ورود با خرده‌موجودی برنامه‌ریزی‌شدهٔ بیش از کمینهٔ ۵۰۰ تومان و ۰٫۵٪ هزینهٔ خرید جلوگیری می‌شود. ظرفیت پژوهشیِ ۱۵۰هزار تومانی، مجوز اندازهٔ مالی نیست.

در اندازه‌گذاری مالی، ۵۰۰ تومان ذخیرهٔ زیان نقدیِ residual پیش از محاسبهٔ debit از همان بودجهٔ کل ۰٫۵٪ کسر می‌شود. transport نیز `debit × loss_fraction + 500 ≤ risk_budget` را مستقل و پیش از HTTP کنترل می‌کند. بنابراین هزینهٔ داراییِ نقدنشده بیرون از بودجهٔ برنامه‌ریزی‌شده پنهان نمی‌ماند. این حد بر فرض اجرای stop و هزینه‌های اعلام‌شده است؛ gap، خرابی بازار یا عدم اجرای سفارش می‌تواند زیان بیشتری ایجاد کند.

خرده‌موجودی فقط پس از BUY اصلی دارای evidence و SELL قطعی دارای fill، با تطبیق broker/intents/fills و بازسازی دقیق موجودی/cost basis طبقه‌بندی می‌شود. سقف هر receipt کمینهٔ ۵۰۰ تومان و ۰٫۵٪ خرید، حداکثر هشت دارایی و سقف مجموع ارزش علامت‌گذاری‌شده ۵۰۰۰ تومان است. حساب، موجودی، بهای تمام‌شده، PnL، fill و `closed_round_trips` صفر یا دست‌کاری نمی‌شوند. فقط receipt زنجیره‌دار و رویداد audit اضافه می‌شود. ورود به همان base ممنوع است؛ یک موقعیت قابل معامله در کنار residual مستند ممکن است. تطبیق حساب همهٔ موجودی‌های واقعی را همچنان می‌بیند.

این طبقه‌بندی تبدیل به تومان یا round-trip کامل نیست. equity ریسک و monitor، residual را به‌صورت محافظه‌کارانه از ارزش نقدشدنی کنار می‌گذارند و هشدار `NON_TMN_RESIDUAL_NOT_FINALIZED` دارند. پایان مالی با non-TMN هنوز `STOPPED_OPEN_RECONCILIATION_REQUIRED` است. محدودیت bootstrap۱۵۰k تنها با witness واقعیِ بسته‌شدن کامل آزاد می‌شود، نه با quarantine. باقی‌مانده پس از partial یا تغییر fee ممکن است از حد بگذرد؛ در آن صورت ورود بسته می‌ماند. سقف مجموع dust در قیمت زمان ثبت سنجیده می‌شود؛ ارزش جاری آن تضمین‌شده نیست.

## ارزیابی و حدود

بررسی ثابتِ manifest تاریخیِ hash‌شده شامل ۸۷ trace، ۲۸۶ کاندیدای یکتا و سه ENTER بود. نقطهٔ سربه‌سر تخمینی این سه پیشنهاد به‌ترتیب ۰٫۷۴۲٪، ۰٫۹۰۰٪ و ۰٫۷۱۴٪ بود و median پیش‌بینی هر سه از آن بیشتر بود. این بررسی نه outcome، نه fill و نه سود/alpha است؛ از آینده، snapshot یا timestamp گمشده چیزی ساخته نشد. traceهای قدیمی مسیر زنده فاقد snapshot/issued_at کافی‌اند و scorer پیش‌فرض روی آن‌ها مسدود می‌ماند. برای دادهٔ پس از اصلاح، بازهٔ صریح index اصلی انتخاب می‌شود و حذف‌شده‌ها در گزارش باقی می‌مانند؛ سقف۳۲GET، عدم retry و حفظ اصل manifest برقرار است.

تست‌ها شامل oracle دستی هزینه، حذف trigger از channel/volume baseline، future-prefix invariance، صفر حجم، قیمت کهنه، حداقل و گام، ذخیرهٔ fee فروش، حفظ cash/cost/PnL پس از restart، UNKNOWN و tamper residual هستند. نتیجهٔ نهایی test و نسخهٔ واقعاً مستقر در گزارش acceptance همین فاز ثبت می‌شود. مقایسهٔ سود خارج از نمونه برای prompt/feature جدید هنوز انجام نشده؛ تعداد تست جای آن را نمی‌گیرد.

## اصلاح دسترسی به تحلیل در اجرای پیوسته

چرخه‌های ۹۳ و ۹۴ِ نسخهٔ نخست این ارتقا، پیش از فراخوانی مدل با `NO_CANDIDATE` پایان یافتند. در چرخهٔ ۹۳ سه seed به‌علت spread بیش از سقف ۰٫۵٪ رد شدند؛ این شاهد WAIT واقعی مدل یا نبود فرصت در کل بازار نیست. مدل به دادهٔ معتبر اولیه نیاز دارد و چرخش coverage می‌توانست هر سه فرصت را صرف بازار نامناسب کند.

نسخهٔ بعدی ابتدا نمادِ دارای scan پذیرفته‌شدهٔ قبلی را با همان دادهٔ تازه و همان گیت‌ها بررسی می‌کند. در نبود anchor معتبر، candidates آخرین ۱۲ trace را با catalog مجاز و نقدشوندهٔ فعلی تطبیق می‌دهد و بیشترین turnover فعلی را فقط برای bootstrap انتخاب می‌کند. در صورت رد، دو فرصت بعد با ترتیب coverage/quant قبلی ادامه می‌یابند. سقف سه scan و شمارندهٔ پایدار حفظ شده‌اند؛ مدل کل universe قبلی را می‌بیند و نماد و اقدام را خودش انتخاب می‌کند. این اصلاح دسترس‌پذیری است، نه سیگنال خرید و نه کاهش آستانهٔ داده یا spread.

سه regression، انتخاب anchor با سه seed خراب، شکست anchor و fallback محدود، و حفظ anchor/count پس از restart را پوشش می‌دهند. نماد نامجاز و context خارج از دوازده trace اخیر استفاده نمی‌شود. پذیرش source و نتیجهٔ چرخهٔ واقعی در [گزارش اعتبارسنجی استقرار](reference-upgrade-acceptance-20261024.md) ثبت می‌شود.

## چه چیزهایی منتقل نشد و گام بعد

- هدف‌سازی برای پاس‌شدن گیت، probability/Kelly از confidence زبانی، نقدکردن فرضی PENDING، fallback قیمت یا BUY ساختگی، retry سفارش نامعلوم و بلعیدن خطای journal رد شدند.
- swarm، RL/مدل عددی تازه، feed خارجی/اخبار، چند موقعیت و cross-USDT اضافه نشدند؛ دادهٔ معتبر و زمان کافی برای اعتبارسنجی‌شان نداریم.
- اولویت بعد: مشاهدهٔ پاسخ و fill واقعیِ یک پیشنهاد واجد شرایط و تطبیق حساب؛ سپس forecastهای موعدرسیدهٔ نسخهٔ جدید و آزمون paired منجمد با cash/hold/rule، هزینه و تأخیر یکسان. شرط۲٪ یک heuristic پژوهشی است و به ابلیشن جدا نیاز دارد؛ صرف کمبود معامله، دلیل حذف آن نیست.
- یک source transition با artifact دارای hash و همان mission/disk/permit/ledger/بودجه انجام می‌شود؛ commit/push یا تغییر ظاهر داشبورد انجام نمی‌شود. استقرار سالم یا پاسخ۲۰۰ به‌تنهایی موفقیت سفارش یا سود نیست.

## اصلاح‌های حاصل از چرخهٔ واقعی و اندازهٔ سفارش

در چرخه‌های۹۵/۹۶، bootstrap اصلاح‌شده به۹کاندیدای دارای داده و پروندهٔ هزینه رسید. درخواست دوم SDK به‌سبب dossier کامل از حد محافظه‌کارانهٔ ورودی عبور کرد؛ پیام عمومیِ «بودجه» برای این علت دقیق نبود. این یک regression انتقال اطلاعات در ارتقای اولیه بود، نه شواهدِ تمام‌شدن اعتبار یا تصمیم WAIT مدل. حد بودجه افزایش نیافت: ابزار اکنون `ENTRY_DOSSIER_COMPACT_V1` با ستون‌های مشترک و خلاصهٔ هزینهٔ هر چهار سناریو می‌دهد؛ symbol/hash/evidence و قیمت اصلی صریح‌اند، full dossier و سناریوها در trace دقیق حفظ می‌شوند. hash dossier کامل، اتصال projection را ثبت می‌کند. تشخیص `REQUEST_INPUT_BYTE_LIMIT` از اتمام پول/توکن/attempt جدا شد و متن exception ناشناس ذخیره نمی‌شود.

بازاجرای SDK روی context ثبت‌شدهٔ چرخه۹۵، درخواست دوم۵۵٬۱۲۸بایتیِ مسدود را به۲۹٬۰۱۰بایت رساند. fixtureهای۹ و۱۰نامزدی با فیلدهای تازه،۲۸٬۷۵۲ و۳۰٬۳۵۴بایت بودند؛ حد۳۱٬۷۴۴بایت تغییر نکرد. این‌ها MockTransport و آزمون انتقال‌اند؛ نتیجهٔ مدل واقعی یا سود نیستند. مرز اندازهٔ واقعی SDK در تست قبلی پوشش کافی نداشت و اکنون regression مشخص دارد.

بررسی ظرفیت همچنین نشان داد ارزیابی فقط «بیشترین quantity ممکن» می‌تواند اندازهٔ کوچک‌ترِ معتبر را از دست بدهد. `BOUNDED_DOWNWARD_LOT_FIT_V1` در حداکثر۲۵۶ گام فقط quantity را کاهش می‌دهد و هر چهار حالت fee، حداقل خرید/فروش و همان سقف residual را می‌سنجد. در counterexample ثابتBTC،۶۹۴گام residual۶۴۵٫۸۵۵تومان می‌داد، ولی۶۶۸گام residual۴۳۰٫۵۷۰تومان و notional بالای۱۰۰هزار داشت. این جست‌وجو گیت را ضعیف نمی‌کند؛ `None` هم اثبات نبود quantity ممکن نیست.

همین helper در preview و مسیر واقعی پیش از intent استفاده می‌شود؛ عمق و هزینه با quantity تازه بازحساب می‌شوند و آخرین book، امکان خروج پس از fee را در قیمت محافظه‌کارانه دوباره می‌سنجد. regression مستقل نشان می‌دهد حتی هدف بسیار خوش‌بینانه، افت bid نهایی به زیر حداقل فروش را پنهان نمی‌کند. حداقل پژوهشی مدل نیز کف۱۰۰هزارِ قرارداد را حفظ می‌کند؛ metadata۵۰هزار اجازهٔ پایین‌آوردن آن را نمی‌دهد.

درخواست افزایش خرید به حدود۵۰۰هزار در [بررسی سرمایه و ظرفیت](capital-capacity-audit-20261024.md) محاسبه شده است. فعلاً سقف خرید اول۱۵۰هزار حفظ شد؛ افزایش یک عدد با reserve خروج و residual فعلی سازگار نبود و خطای تحلیل را هم حل نمی‌کرد. افزایش منسجم آتی باید reserve/ظرفیت تجمیعی را داخل همان بودجهٔ زیان ثبت کند، بدون دست‌کاری permit/سابقه یا جعل بسته‌شدن معامله.

## بررسی تفصیلی هر مرجع

متن زیر گزارش source هر گروه است؛ فایل‌ها و rangeهای خوانده‌شده، محدودیت دسترسی/حجم و permalinkهای ثابت مشخص‌اند. snapshots، فایل‌های خام و ledgerهای خصوصی در Git قرار نمی‌گیرند. ایده‌ها متناسب با رویین بازپیاده‌سازی شدند؛ کد ثالث وارد موتور نشده است.

# Reference source audit — group A — 2026-10-24

## Scope, method, and evidence boundary

Ten unique repositories were pinned to their observed HEAD using the GitHub connector's `GET /repos/{owner}/{repo}/commits?per_page=1`. Source was obtained at those exact SHAs, with bounded codeload ZIP extraction or selected UTF-8 raw files. Archive traversal, symlinks, and size limits were checked; the batch archive collector encountered an unsafe ZIP entry and stopped. Missing source was fetched individually at the same pinned SHA. This is a **bounded source review**, not an exhaustive independent financial/security audit. No third-party code or tests were executed, no dependencies installed, and no financial/model APIs called. Repository claims, included output, test names, and comments are not independently verified trading performance.

The local inventory is `a-inventory.json`; observed file hashes are `a-observed-source-manifest.json`; source is under `snapshots/a/{owner}__{repo}/`. Source hash inventory is broader than the exact files/ranges read below. Downloaded file count does not mean all files were reviewed. Parent graph tools were unavailable (`Transport closed`), so all findings below use direct source; no graph-completeness claim is made. No existing runtime, financial state, budget, dashboard, or Git history was changed by this audit.

## Pinned inventory

| Repository | Observed SHA | Commit UTC | Review depth |
|---|---|---|---|
| KingMB5/WallexB | `8ec16b5ede9c6fd1b874e806aacaed16307ecddf` | 2026-10-23 20:34:09 | Engine, broker, risk, trend, strategy plugin, LLM, HTTP, backtest, smoke-test source |
| amirhosseinpourmoshir/vela-wallex-challenge | `7a45c3efa675fcb69500eb936fe58f882b64297e` | 2026-10-23 19:57:29 | Economics, rapid setup/context, live wiring, uncertainty handling, relevant tests |
| ARaminco/gisoo-trader | `5ee9b553feb1466e9210a6f21f9552c9a8d06623` | 2026-10-06 13:42:07 | Core families, ensemble, risk, live executor/order settlement, Wallex adapter, ML split, LLM review, exit tests |
| hamedsony60-a11y/astrax-exchange-concept | `e904c0fc6fc4dd92256129d4c1b2ea76ac674cad` | 2026-08-02 15:01:51 | Complete 56-line JS behavior and README; static repository inventory |
| novo-official/novo-wallex | `095c1d394033d88e801424a8bb173cf03160dd19` | 2026-10-24 13:33:14 | Features, trend/activity, live wiring/broker, risk guard, role contracts, costs/windows, relevant test assertions |
| amir-mostafa-hs/aps-wallex-ai-agent | `3f691be7df3d5b71898b864d375d7f88fa831bf6` | 2026-10-24 16:18:03 | Pullback strategy, feature API, decision branch, risk, executor, test assertions; harness/backtest surface inventory |
| JimmyMac2020/wallex-ai-quant-challenge | `fec27652d8b14bc5ecd95bf20aeeb54dce94a9e6` | 2026-10-24 09:29:34 | Complete 98-line sole Python implementation and repository inventory |
| 1990hamed/wallex-trading-agent | `ba6777fa8d4175e80e7e8c4e4370cda18d63e9f1` | 2026-10-24 11:16:17 | Complete strategy, LangGraph agent, Wallex client and order tests |
| nematsymphony-spec/wallex-agentic-trader | `72c9b2087cc70abd1e18cb5498d4e21c197c07f6` | 2026-10-24 08:10:50 | Core/ranking, separate credit runner/reconciliation, monthly policy/data/execution, Turtle research, relevant test surface |
| Shahin-Kohzadpour/Agentic-AI-Hakathon-Wallex-Challenge | `8b7bd8785c20612259f4b21fc9eb1dd353449485` | 2026-10-23 21:17:36 | Wallex live subsystem, fair-value core/wiring, ridge research validation/readiness, relevant tests. **Not all Condor framework modules.** |

## 1. KingMB5/WallexB

**Implemented:** `pilot/engine.py` connects exchange, journal, risk, strategy and mandatory explicit LLM approval. `trend.py:8–27` checks closed-price/fast/slow EMA on configured higher timeframes. `strategies/breakout_pullback.py:13–38` searches a prior breakout, rejects failed/intermediate retests, then requires a bullish first retest; stop is beneath observed lows with an ATR buffer. `risk.py:32–45` includes both entry and stop-exit fees in risk sizing, then cash/exposure/minimum caps. `engine.py:55–95` persists high-water/raised stops and exits on stop/time/kill.

**AI and execution:** `llm.py` actually calls a configured compatible model; missing key, disabled model, invalid schema/HTTP, or exhausted attempted-call budget cannot approve entry. It is a last-step veto, not primary selector. `broker.py:60–78` submits once through its wrapper, polls ten times, attempts cancellation, returns the actual executed quantity. However, `wallex.py:29–44` applies a generic three-attempt transport loop to *all* methods, including POST; ambiguous writes could be repeated. There is no comparable durable pre-send reserve/UNKNOWN contract in this reviewed path.

**Important disconnected feature:** `AdaptiveHybrid.scan` always returns `None` (`adaptive_hybrid.py:28–30`), while the engine only calls `st.scan` (`engine.py:124–128`). The more sophisticated `generate_mtf` logic exists but is not wired by that engine. Do not present that plugin as an active strategy.

**Evaluation:** `backtest.py:128–209` signals only on closed history and fills at the next open, applies adverse slippage/fees and stop-first OHLC ordering; `:238` explicitly excludes trend gate and LLM from simulation. Smoke tests use fake candles and simulated model approval, not real AI or profit evidence.

**Transfer:** explicit prior breakout/first-retest context and conservative backtest ordering. Our durable Decimal execution and budget handling are stronger; retain them. Do not copy float money, POST retries, last-price-as-fill fallback or disconnected MTF claims.

Evidence: [breakout/first retest](https://github.com/KingMB5/WallexB/blob/8ec16b5ede9c6fd1b874e806aacaed16307ecddf/pilot/strategies/breakout_pullback.py#L13-L38), [unwired plugin](https://github.com/KingMB5/WallexB/blob/8ec16b5ede9c6fd1b874e806aacaed16307ecddf/pilot/strategies/adaptive_hybrid.py#L28-L30), [HTTP retry scope](https://github.com/KingMB5/WallexB/blob/8ec16b5ede9c6fd1b874e806aacaed16307ecddf/pilot/wallex.py#L29-L44), [backtest boundary](https://github.com/KingMB5/WallexB/blob/8ec16b5ede9c6fd1b874e806aacaed16307ecddf/backtest.py#L128-L209).

## 2. amirhosseinpourmoshir/vela-wallex-challenge

**Implemented:** Node services separate deterministic nominations, model selection/review, execution permission, SQLite order state, and historical replay. `rapid-strategy.js:3–30` checks closed/fresh/continuous 1m bars, compares recent three bars with an earlier volume/range baseline, and nominates volume breakout, trend pullback, or support reclaim. It supplies observed support/resistance and contrary evidence. `live-orders.js:194` actually constructs this local plan for the model/live path; this is wired code, not a README-only idea. `trader-analysis.js:16` excludes the current candle from prior support/resistance.

**Economic value:** `trade-economics.js:2–8` computes target net, stop net, net reward/risk and break-even from actual adverse-adjusted entry, entry costs, exit fees/slippage. `live-orders.js:115` applies it to the actual buy quote; `rapid-strategy.js:33–39` walks book levels and checks full size/order/sweep slippage. `market-selection.js:3–7` validates a full unique ranking with viable/blockers consistency. The long SEEK ENTRY wording is a preference, not empirical alpha.

**Execution/error:** the read/submit path binds the credit account, metadata/fee/book/package, creates durable local drafts, and distinguishes uncertain network/unreadable/5xx responses (`live-orders.js:68–93,239–245`); polling/reconcile uses the original ID (`:166–170,286–288`). Separate backtest route refuses non-backtest mode (`agent-engine.js:181`), so live and replay capabilities must not be conflated.

**Limits:** much source is compressed into huge JS lines; no independent running acceptance was performed. Short/margin/funding/portfolio paths are outside our spot scope. `rapid-strategy.js:27` chooses target distance as a maximum of multiples of stop/cost/ATR, which can manufacture an apparently cost-clearing target. Treat it as an unvalidated projection, not observed resistance or expected return. `market-selection.js:6` cannot permit a HOLD while listing a viable market; importing this restriction could bias abstention and must not be automatic.

**Tests read:** economics tests distinguish gross versus net R/R, fee-aware break-even and false locked profit; rapid tests cover closed/gapped/stale bars, transient final-minute volume, ordered/full depth, duplicate fingerprints. Not executed here.

**Transfer:** causal setup context and deterministic break-even information shown to our model, while retaining independent host risk/target checks and honest WAIT. Avoid target inflation, strategy scores as probabilities, aggressive size presets, or importing margin paths.

Evidence: [causal nominations and depth](https://github.com/amirhosseinpourmoshir/vela-wallex-challenge/blob/7a45c3efa675fcb69500eb936fe58f882b64297e/services/rapid-strategy.js#L3-L39), [net economics](https://github.com/amirhosseinpourmoshir/vela-wallex-challenge/blob/7a45c3efa675fcb69500eb936fe58f882b64297e/services/trade-economics.js#L1-L10), [live wiring](https://github.com/amirhosseinpourmoshir/vela-wallex-challenge/blob/7a45c3efa675fcb69500eb936fe58f882b64297e/services/live-orders.js#L194), [test counterexamples](https://github.com/amirhosseinpourmoshir/vela-wallex-challenge/blob/7a45c3efa675fcb69500eb936fe58f882b64297e/services/trade-economics.test.js#L3-L7).

## 3. ARaminco/gisoo-trader

**Implemented architecture:** FastAPI/SQLAlchemy workers, exchange adapters, features, strategies, risk, executor/reconciler, optional LLM advisor/committee, research and dashboard. `core4h.py:156–250` implements cross-sectional 7-day-minus-1-day momentum and lagged Donchian/Turtle channels under aligned BTC EMA200 context. `workers/trader.py:488–618` evaluates that universe; it is wired. Ensemble votes are regime-weighted, require at least two non-abstaining voters and downweight disagreement (`ensemble.py:84–174`). These hand-set weights are not learned/calibrated probability.

**AI/ML:** optional LLM trade veto/reduction has a timeout and runs outside DB/symbol locks, then repeats account/risk checks after reacquiring the lock (`trader.py:965–1032`). LLM failure means “no opinion,” allowing the deterministic path; this differs from our required real-AI path and should not be relabeled. ML uses triple-barrier labels, pessimistic same-bar ties, chronological 80/20 split and a purge equal to the label horizon (`ml/model.py:45–116`); an AUC threshold gates saving. It is one holdout, not proof of financial edge, calibration, or repeated walk-forward superiority.

**Execution/risk:** Wallex adapter uses one write attempt and lookup after ambiguous responses (`exchange/iran/wallex.py:241–250`). Executor polls/cancels/rereads acknowledgments before booking fills (`executor.py:619–658`), handles protective-stop cancel/fill races, restores stop after a failed exit, and keeps partial remainder open (`:403–548`). Sticky exit recovery tests are meaningful source examples. Our core already has durable pending exits/UNKNOWN and should preserve it.

**Concrete weakness:** partial sell reduces `position.qty` (`executor.py:525–544`) without accumulating that partial gross PnL; final `_finalise` computes gross using only the remaining quantity (`:141–158`) and subtracts all fees. In that code path, 10@100, sell5@110, then5@100 yields gross0 instead of50 in the position summary. Other reporting paths were not exhaustively traced. Do not transfer this accounting. Minimum-order fallback also permits implied risk up to 1.6 times nominal budget (`risk/manager.py:414–429`), and sizing excludes stop fees. Monetary fields use float.

**Transfer:** shared causal feature rules between research/live; time-aligned BTC context; lock-free bounded inference followed by final revalidation; exit-race regression patterns. Do not import 4h/EMA200 history requirements into a three-day mission without suitable data, unvalidated ensemble weights, float accounting, higher risk multipliers, Binance futures/Earn logic, or claimed research returns.

Evidence: [causal Turtle](https://github.com/ARaminco/gisoo-trader/blob/5ee9b553feb1466e9210a6f21f9552c9a8d06623/trader/engine/app/strategies/core4h.py#L221-L250), [post-LLM recheck](https://github.com/ARaminco/gisoo-trader/blob/5ee9b553feb1466e9210a6f21f9552c9a8d06623/trader/engine/app/workers/trader.py#L965-L1040), [purged labels](https://github.com/ARaminco/gisoo-trader/blob/5ee9b553feb1466e9210a6f21f9552c9a8d06623/trader/engine/app/ml/model.py#L110-L116), [partial exit](https://github.com/ARaminco/gisoo-trader/blob/5ee9b553feb1466e9210a6f21f9552c9a8d06623/trader/engine/app/execution/executor.py#L525-L548), [final summary](https://github.com/ARaminco/gisoo-trader/blob/5ee9b553feb1466e9210a6f21f9552c9a8d06623/trader/engine/app/execution/executor.py#L141-L158).

## 4. hamedsony60-a11y/astrax-exchange-concept

The pinned repository is a static exchange **concept**, not a trading agent. `app.js:1–56` only opens/closes modals, shows toasts and stores a localStorage username. It contains no real authentication, exchange/order engine, market inference or risk strategy. README explicitly identifies the project as conceptual (`README.md:164`). Exchange services, leverage, staking, bots and technology in the prose are proposed capabilities, not implemented mechanisms.

There is no source-supported trading algorithm to transfer. UI redesign is also outside the user's current no-visual-change constraint. Do not cite its interface as evidence of financial/API functionality. [Complete actual JS](https://github.com/hamedsony60-a11y/astrax-exchange-concept/blob/e904c0fc6fc4dd92256129d4c1b2ea76ac674cad/app.js#L1-L56).

## 5. novo-official/novo-wallex

**Implemented:** Django/Python modules separate research/backtest, market data, strategy, risk, bounded LLM roles, and live execution. `strategy/features.py:80–104` computes prior-high channels excluding the trigger candle, intraday return and higher-timeframe features joined as of their close. `trend.py:54–105` uses 1h regime, 15m pullback and 5m breakout; the live engine invokes the same strategy and agent/risk chain (`execution/engine.py:516–619`). `ai_activity.py:62–109` is a separate ML-edge ranking activity module with slot/cap/spacing controls, not the trend strategy itself.

**AI:** Regime Officer gives hourly NORMAL/DEFENSIVE/OFF; Trade Agent reviews configured modules with bounded read-only tools and may only reduce size/tighten protection. Failure defaults OFF/reject (`agent/roles.py:150–218,238–279`). Exact model/tool responses have replay/cache support and prompt/provider identity tests. No real provider performance was run by this audit.

**Value for evaluation:** `backtest/windows.py:47–54` purges overlapping three-day windows at the selection/holdout boundary; `costs.py:41–88` measures size-specific book-walk slippage across recorded snapshots, retains a floor and reports thin snapshots. Test assertions cover no-lookahead via full-versus-prefix recomputation, higher timeframe's last closed bar, next-open taker entry, trade-through maker behavior, same-bar stop precedence, gap stop, final flat state, and agent clamps.

**Limits:** median historical cost cannot replace fresh executable depth. Feature builder fills minute gaps, and that dataset contract must not silently promote our DIAGNOSTIC_ONLY data. Trend target is projected from stop/minimum percentage, not established expected return. Activity goal is not a reason to force trades. Broker `place` treats every HTTP>=400 as rejected (`execution/broker.py:145–147`), which is weaker than our durable ambiguous-write handling for 5xx; preserve ours. Risk sizing comments explicitly exclude fees before stop, unlike our all-in loss bound. Full ML training/calibration and all execution branches were not audited.

**Transfer:** causal context, last-closed higher timeframe alignment, prefix invariance tests, non-overlapping holdout windows and cost sensitivity. Do not import quota motives, target inflation, weaker HTTP ambiguity classification or historical fill assumptions.

Evidence: [causal features](https://github.com/novo-official/novo-wallex/blob/095c1d394033d88e801424a8bb173cf03160dd19/strategy/features.py#L80-L104), [real engine chain](https://github.com/novo-official/novo-wallex/blob/095c1d394033d88e801424a8bb173cf03160dd19/execution/engine.py#L516-L619), [purged window split](https://github.com/novo-official/novo-wallex/blob/095c1d394033d88e801424a8bb173cf03160dd19/backtest/windows.py#L47-L54), [prefix tests](https://github.com/novo-official/novo-wallex/blob/095c1d394033d88e801424a8bb173cf03160dd19/strategy/tests/test_features.py#L28-L78), [live HTTP classification](https://github.com/novo-official/novo-wallex/blob/095c1d394033d88e801424a8bb173cf03160dd19/execution/broker.py#L128-L170).

## 6. amir-mostafa-hs/aps-wallex-ai-agent

**Implemented:** typed intent/validation, strategy dispatcher, scanner, pure risk decisions, broker/shadow executor, telemetry and harness. `trend_filtered_pullback.py:97–173` checks 5m EMA alignment plus recent 1m EMA touch and bullish reclaim. However, it shortens the EMA periods when history is short (`:103–112`), so the names EMA20/50 need not mean those periods. `decision_agent.py:171–247` explicitly supports deterministic heuristic mode; actual LLM mode invokes a compatible provider and validates semantics/evidence IDs (`:250–275`), with NO_TRADE/HOLD failure.

**Risk/execution:** risk-based notional is stop-budget divided by stop distance, capped by position/portfolio/cash, with spread-plus-fee target hurdle (`risk_engine.py:135–220`). Fees are not included in stop-budget sizing or cash decrement at that gate. Executor floors price/quantity, cancels opposite tracked orders, posts once and queries the same client ID after an exception (`executor.py:45–136`). Unknown is returned, but its in-memory open order registration is done after response, not a durable pre-submit reserve in this class. `success:false` without exception is not checked in that reviewed submit branch; canceled/unknown and mismatch cases need stronger integration guarantees than its permissive MagicMock tests.

**Limits:** `trend_filtered_pullback.py:174–221` clamps stop to0.8–2.5%, creates target as max(RR multiple,1.8%) and fixes confidence0.85; none are calibrated win probability. It is inappropriate to enlarge a target merely to pass costs or use that confidence for50% capital. Float monetary arithmetic is weaker than our Decimal ledger. Tests read cover width/trend/holding rejection and synthesized bounce, one submit on timeout and opposing-cancel abort; they do not establish live acceptance, durable crash safety, alpha or real LLM behavior.

**Transfer:** bounded setup explanation and explicit strategy/provenance labels, semantically validate tool/evidence IDs, isolated mode tests. These are mostly already present in Royin. No new framework or fixed-confidence sizing is warranted.

Evidence: [pullback mechanism](https://github.com/amir-mostafa-hs/aps-wallex-ai-agent/blob/3f691be7df3d5b71898b864d375d7f88fa831bf6/src/wallex_agent/strategies/trend_filtered_pullback.py#L97-L221), [AI versus heuristic](https://github.com/amir-mostafa-hs/aps-wallex-ai-agent/blob/3f691be7df3d5b71898b864d375d7f88fa831bf6/src/wallex_agent/decision_agent.py#L171-L275), [executor boundary](https://github.com/amir-mostafa-hs/aps-wallex-ai-agent/blob/3f691be7df3d5b71898b864d375d7f88fa831bf6/src/wallex_agent/executor.py#L77-L136), [mock timeout assertions](https://github.com/amir-mostafa-hs/aps-wallex-ai-agent/blob/3f691be7df3d5b71898b864d375d7f88fa831bf6/tests/test_executor.py#L58-L93).

## 7. JimmyMac2020/wallex-ai-quant-challenge

**Actual implementation is one98-line script.** `--mode live/backtest/shadow` changes the payload/log label only. The entire main path fetches book, asks/imitates a model, appends a JSON line and prints it; there is no order POST, execution broker, backtest loop, position/risk state or settlement implementation (`wallex_engine.py:78–98`). An allowlist constant is declared but not applied to CLI symbol in that path.

**Unsafe fabricated fallbacks:** on market failure it returns a fixed positive imbalance and fixed price (`:43–44`); missing model key or any model exception returns BUY with confidence0.85 (`:51–52,74–75`). Therefore a successful-looking output can be wholly synthetic. No test suite exists in the four-entry pinned tree. No valuable trading component is recommended for transfer; use it as a counterexample for fail-closed/no-fake-data regression acceptance. [Complete implementation](https://github.com/JimmyMac2020/wallex-ai-quant-challenge/blob/fec27652d8b14bc5ecd95bf20aeeb54dce94a9e6/wallex_engine.py#L27-L98).

## 8. 1990hamed/wallex-trading-agent

**Implemented:** LangGraph chain collect→deterministic proposal→optional structured AI review→risk→execute/shadow (`agent.py:47–60`). EMA/RSI/ATR/DX rules nominate BUY/SELL/HOLD (`strategy.py:74–119`); the function named `_adx` calculates one directional ratio, without Wilder ADX smoothing (`:43–71`). AI can confirm/veto/reduce confidence; missing key bypasses it and preserves deterministic proposal (`agent.py:75–131`). Host sizes by ATR, quantizes, submits a limit and posts exits only if the immediate response includes filled quantity.

**Limits requiring rejection for our live architecture:** uses main `/v1/account/balances`, no credit-scoped header; no durable pre-send intent/reserve/financial worker contract. It posts an independent stop-limit and take-profit for the same filled quantity (`agent.py:263–300`); without venue OCO/reserve semantics one can lock balance needed by the other. `wait_for_fill`/sibling-cancel helpers exist but the reviewed main execution does not call them; pending entry may never receive later protection. Stop monitoring should not depend on next entry cycle or LLM availability. The liquidation path still starts after collecting/reviewing market, another dependency hazard.

**Concrete quantization defect:** `wallex.py:120–125` uses default Decimal.quantize rounding. Test named “rounds down” asserts1.239→1.24 (`test_wallex_orders.py:63–65`), which can exceed owned balance. Stable IDs omit decision/time/account, so two intended identical future orders may collide; deterministic ID alone is not durable intent safety.

**Transfer:** small explainable graph stages and endpoint contract tests, already adequately present in our code. Do not copy its ADX label, balance scope, protection pattern, rounding, or infer a real fill from “submitted.”

Evidence: [actual graph](https://github.com/1990hamed/wallex-trading-agent/blob/ba6777fa8d4175e80e7e8c4e4370cda18d63e9f1/src/wallex_trading_agent/agent.py#L47-L60), [protection path](https://github.com/1990hamed/wallex-trading-agent/blob/ba6777fa8d4175e80e7e8c4e4370cda18d63e9f1/src/wallex_trading_agent/agent.py#L263-L303), [rounding assertion](https://github.com/1990hamed/wallex-trading-agent/blob/ba6777fa8d4175e80e7e8c4e4370cda18d63e9f1/tests/test_wallex_orders.py#L63-L65).

## 9. nematsymphony-spec/wallex-agentic-trader

**Implemented:** two distinct paths must be kept separate. The general engine ranks eligible fresh/deep TMN markets by bounded percentile volatility, momentum, volume and cost; a global OpenAI decider chooses at most one supplied symbol or HOLD (`selector.py:17–103`). The separate credit runner actually manages credit headers, account/expiry verification, wallet exact reconciliation, one position, file-owner lock, durable pending state and no blind POST retry (`credit_runner.py:95–224`). The live rule ranks relative24/72h strength versusBTC/USDT with volume/listing/data guards (`monthly_policy.py:8–97`). AI review is optional; disabled returns a clearly labeled deterministic BUY, not an AI result.

**Good mechanisms:** decision-hour reserved before collecting data (`credit_runner.py:311–316`), refetch book/account permissions after AI (`:333–344`), fresh fees cannot exceed conservative reserve, stop/closeout/max-hold exit is model independent and its reason sticks. Terminal response and wallet changes are reconciled once in one saved state; partial remainder is retained. `monthly_policy.py:120–153` walks book, rounds bounded aggressive limits, measures immediate roundtrip friction and caps partial exits to visible executable depth.

**Limits:** policy defaults are a monthly-goal/48h/5%stop strategy, not the current short-horizon Royin hypothesis; fixed allocation can be all-in depending on config and is not our fee-aware volatility sizing. Screening includes gap filling only after full prior-day volume reconciliation, still a different data contract. `tick` has a locally captured deadline boolean before a long scan, though it repeats wall-clock closeout checks before send. Tests enumerate UNKNOWN/restart/partial-credit balance, two owners, actual fee, closeout precedence; not executed here. Included historical outputs do not prove present alpha or live fill.

**Transfer:** existing-state continuity checks and causal scheduling are already present in Royin. Potential later addition is risk-adjusted intraday relative strength and explicit friction context; do not add an eight-day hourly data feed or change allocation merely because the reference has it.

Evidence: [durable credit execution](https://github.com/nematsymphony-spec/wallex-agentic-trader/blob/72c9b2087cc70abd1e18cb5498d4e21c197c07f6/src/wallex_agent/credit_runner.py#L160-L224), [durable cadence/fresh entry](https://github.com/nematsymphony-spec/wallex-agentic-trader/blob/72c9b2087cc70abd1e18cb5498d4e21c197c07f6/src/wallex_agent/credit_runner.py#L311-L344), [data and relative score](https://github.com/nematsymphony-spec/wallex-agentic-trader/blob/72c9b2087cc70abd1e18cb5498d4e21c197c07f6/src/wallex_agent/monthly_policy.py#L8-L97), [bounded book plan](https://github.com/nematsymphony-spec/wallex-agentic-trader/blob/72c9b2087cc70abd1e18cb5498d4e21c197c07f6/src/wallex_agent/monthly_policy.py#L120-L153).

## 10. Shahin-Kohzadpour/Agentic-AI-Hakathon-Wallex-Challenge

This is a large Condor framework plus distinct Wallex sandbox/live packages. Review deliberately focuses on **`wallex_live` and relevant `wallex_sandbox`**, not all ~668 non-test code paths or the full general agent/tool framework.

**Implemented live hypothesis:** BTC/ETH **USDT** local-venue fair-value reversion, not our TMN-only signal. `fair_value_core.py:57–119` validates timestamp freshness, same spot/quote and reference venue agreement; a rolling median log-basis and MAD dispersion require sample/time warmup. Current observation is added after obtaining the baseline. Opportunity compares conservative fair value against book-walk entry and fee/slippage/uncertainty hurdle (`:123–181`). Live engine refreshes Wallex/OKX/Bybit, requires at least3persistent samples over30s, then refreshes all books and costs immediately before send (`wallex_live/engine.py:243–334`). The ordinary live path is a deterministic rule, not the full Condor LLM or ridge research model.

**Execution:** fcntl single writer plus SQLite FULL synchronization; durable prepared/ambiguous intent before network; 404 leaves ambiguity; terminal fills require actual fee records and are applied idempotently with proportional remaining cost basis (`journal.py:47–77`, `engine.py:68–189`). Acknowledgment is distinct from completed settlement. Policy caps one position to10% capital, checks freshUSDT/TMN conversion and reserves holding/exit time. Final conversion and USDT path introduce scope and FX risk absent from our TMN-only mission; do not copy them.

**Research worth adapting later:** `strategy.py:30–109` ridge forecast uses chronological train/calibration/validation, purges labels crossing boundaries, samples disjoint forward returns and compares to zero-return baseline; a calibration quantile is explicitly empirical, not guaranteed coverage. `research_readiness.py:4–25` requires adequate completed trades, positive base/stress outcomes, controlled drawdown and matched controls for a future paper test; it **never enables live**. Tests explicitly exercise normal persistent local discount, bad reference/cost/gap, current-observation calibration leakage, stale-exit rejection, no double fill application, reference outage not preventing stop, and restart ownership.

**Transfer:** baseline-before-current-observation, actual cost of executable size, stop independence from optional reference/model outage, honest validation/readiness contracts. Do not introduce multiple external venues, new quote currency, unverified fair-value alpha, new ML calibration, or Condor framework into the current release merely for feature count.

Evidence: [robust baseline/core](https://github.com/Shahin-Kohzadpour/Agentic-AI-Hakathon-Wallex-Challenge/blob/8b7bd8785c20612259f4b21fc9eb1dd353449485/wallex_sandbox/fair_value_core.py#L57-L181), [live rule and fresh veto](https://github.com/Shahin-Kohzadpour/Agentic-AI-Hakathon-Wallex-Challenge/blob/8b7bd8785c20612259f4b21fc9eb1dd353449485/wallex_live/engine.py#L243-L334), [research partition](https://github.com/Shahin-Kohzadpour/Agentic-AI-Hakathon-Wallex-Challenge/blob/8b7bd8785c20612259f4b21fc9eb1dd353449485/wallex_sandbox/strategy.py#L30-L109), [readiness is not live](https://github.com/Shahin-Kohzadpour/Agentic-AI-Hakathon-Wallex-Challenge/blob/8b7bd8785c20612259f4b21fc9eb1dd353449485/wallex_sandbox/research_readiness.py#L4-L25).

## Cross-reference choice for Royin: three prioritized implementation candidates

### A. Causal setup context using already validated closed candles — implement first

References Vela, Novo and wired Gisoo Turtle agree on a useful mechanism: compare the **trigger candle to a prior channel**, describe retracement/reclaim structure and recent intraday motion, and expose actual observations to the AI. This fills Royin's current snapshot gap without a new provider, dependency, role, market, or trading quota. Suggested context: ret5/15/60m where exact history exists; previous-N high/low (excluding current); close distance from channel/ATR; path efficiency; explicit volume/reference window; evidence tags that describe observation only. Do not label setup scores as win probability or force BUY. Keep monetary host gates, real AI selection, first150k, one position and current source freeze.

Acceptance:

- Full-history calculation at cutoff equals calculation on exact prefix; appending arbitrary future candles changes no past result.
- A current high above all previous highs still has a detectable close-confirmed breakout; including current high would incorrectly make it impossible.
- Gaps, future/open/incomplete bars, duplicate timestamps or missing horizon produce unavailable/error per contract, never fabricated zero-return evidence.
- Flat series has efficiency0, finite output and no false breakout; invalid zero denominators cannot produce NaN/Infinity.
- A wick above prior resistance with close below is not a confirmed breakout. Context distinguishes a projection from observed price levels.
- Prompt/tool trace hash binds the exact setup context used, and validator prevents cross-candidate evidence borrowing.

### B. Deterministic cost and break-even context — implement with A

Vela's net-economics distinction and Novo/Nemat's book walk are useful, but Royin already has stronger Decimal execution. Provide the AI a deterministic **fee/spread/slippage break-even hurdle at the current reference quote**, explicitly indicative and recomputed at final entry. This addresses target selection quality without inventing an expected value or replacing host `assess_target_net`. Prefer clear debit/proceeds mathematics to a universal2% target heuristic. Whether the model's median or tail target should authorize entry remains a policy hypothesis requiring out-of-sample evidence; do not silently change it just to trade.

Acceptance:

- At break-even, net proceeds equal all-in debit within declared rounding; both base/quote entry-fee cases, tick/step, and adverse exit costs covered.
- close100/ask103/target102.1 is rejected by final host economics despite a2.1% candle-relative target.
- Stale/disordered/thin books remain blocked; an attractive historical target cannot authorize an unexecutable position.
- Budget exhaustion, malformed AI or reference outage cannot stop the independent owned-position risk/deadline exit.
- No new provider calls or cadence bypass on restart.

### C. Recorded outcome/evaluation parity and partial-accounting invariants — implement next

Before training an additional model or changing strategy thresholds, preserve issued forecast/snapshot/provenance so current real decisions are scoreable; compare fee-stressed outcomes and matched controls on a fixed untouched holdout. Novo's window purge and Shahin's disjoint-label/zero-baseline/readiness separation are sound patterns. Our recorded-host replay should not become a claimed new model forecast. Gisoo's partial summary defect demonstrates why fill-level accounting invariants matter more than a large test count.

Acceptance:

- Real ENTER and WAIT export the actual snapshot, issued_at, source/config/model/tool bindings, and retain original traces unchanged across upgrade.
- Missing/future/pending/out-of-scope outcomes remain counted and explicitly unscored; no zero-trade run is reported as proven alpha.
- Non-overlap between selection labels/windows and holdout; cost/latency sensitivity recorded without threshold fitting on holdout.
- Buy10@100, sell5@110 then5@100 reconciles gross50 minus every fee; partial fill duplicates, order replay and restart leave identical realized PnL and quantity.
- No fake data on API failure; no model-key fallback presented as real AI; acknowledgment/partial/final fill are separate statuses.
- All old financial IDs, balances, UNKNOWN reserve/counter, budget rows and cadence survive the new immutable source transition.

## Outcome and unresolved work

Source-backed audit of all ten assigned references is complete at the stated depth. No claim is made that their full implementations, test suites, deployments or profitability have passed. No third-party runtime code was executed or copied into Royin. Actual Royin implementation, offline regression, immutable release, state preservation and real exchange order/fill verification are owned by the parent and must be reported from fresh evidence. Reference research does not itself authorize a meaningless trade or guarantee a profitable live fill.


---

# Reference source audit — group B — 2026-10-24

## Scope and evidence boundary

This is a **static source audit** of the ten assigned public repositories. All ten default-branch heads were resolved through the GitHub connector and pinned before reading. Nine bounded archives were downloaded from codeload by immutable SHA; the Pedram archive download did not finish in the bounded source-research session, so its GitHub tree and twelve selected files were fetched directly through the connector. Archive extraction rejected traversal, symlinks, excessive expansion and oversized/non-text files. Snapshot receipts and SHA/file inventories are in `snapshots/b/`.

No third-party code, tests, package install, trading endpoint or model request was executed. Test references below are **test-source inspection**, not a claim that the tests pass. The source indicates what is implemented, not what actually executed on a competitor's server. No repository's alpha, live profit, API fill, calibration or submitted competition version was independently established. Graph coverage was unavailable: parent graph index/search/coverage calls returned `Transport closed`, so this audit uses exact source and immutable permalinks, not graph-completeness claims.

| Repository | Pinned HEAD | Inspection depth |
|---|---|---|
| heliataromi/StarCoach-AgenticAI-Wallex-Challenge | `c5e8458f14982824381f9f5d5e2cce9b75ade3cb` | Source of regime, signals, macro/debate, JEV, dispatcher, model gateway; test inventory and selected acceptance sources |
| AliFazelniya/wallextrade | `4182c86f926dd05b1f81455184afa8ac572d0601` | Entrypoint, features, multi-asset strategy, council/LLM split, risk, adapter; selected execution tests |
| Arshia-HZ/Wallex-Quant-Agent | `7d870185bd0513758fba7a517953f0cdbca774f4` | Quant features, LLM wake/decision, real runner buy/exits/sizing, order path, test techniques |
| moalma1400/wallex-trading-contest | `5480d56f20ae69113077986ef2dd59ba2c3ef2a8` | Complete public inventory: README, SECURITY, readiness document only; executable source intentionally absent |
| AliSK81/hackathon-starcoach-wallex | `6de44849fb99a25f7d3e0fe7bcedb7d5d53fe050` | Setup definitions, risk envelopes, shadow/live execution, order parsing/lookup; brain call-chain and test inventory |
| hamid-shafi/wallex-trading-bot | `e2b3437221b4e17bc434f50436ca2ac6c77cc587` | Numerical learner, cost predictor, entry planner, risk adaptation, durable execution, robustness code and fee-test source |
| pedrammgd/starcoach-wallex-agent | `828ec24bdcb6da318fae693e37c7dd29d09c8a8e` | Twelve selected source/test/protocol files through connector, complete tree metadata; model, simulator, optional LLM, executor, credit reader |
| ssinasaberii/wallex-agent | `df1873133f4bf2053ae8d8c2ed4c31df08bf7657` | Causal indicators/triggers, fee-horizon, cycle wiring, real/dry execution, local judge, default/versioned config, selected tests |
| moalma1400/wallex-trading | `6cddedb0f1bf5ced78587266094440ccd504e4e5` | Screener, cost model, ranker, runner, fixed-host live transport, broad src symbol search; test inventory |
| BMDarkLight/wallex-agent | `0db4d57b7275e6a4768e1a3080e17c2c751ae6c5` | Feature/setup/AI/risk/execution/core wiring, allocator and backtest inventory; execution limitations traced |

## Highest-value findings for Royin

1. **Add causal, explicitly named setup context before expanding strategy complexity.** Current Royin context (per parent source trace) has 5-minute SMA/RSI/ATR and volume pressure, but lacks explicit short-return windows, prior channel, reclaim/rebound and path efficiency. BMDarkLight's `features.py:88–107` and ssinasaberii's prior-only Donchian/relative volume provide concrete implementations. AliFazelniya has a Kaufman efficiency ratio. These are useful descriptors, not proof of a profitable signal. Use existing Decimal/candle contracts; do not import their financial float arithmetic or libraries.
2. **Put explicit entry-cost context beside every proposed price target.** The important transferable distinction is observed return versus conditional target proceeds versus a forecast distribution. ssinasaberii logs cost, net reward/risk and horizon separately; Hamid compares a learned conservative forecast with fee/spread/slippage. Moalma correctly labels observed momentum-minus-cost as research, not a future prediction. Royin should preserve its fresh executable-price/depth/fee gate while exposing a read-only break-even context to the model. Do not lower the host gate or inflate targets to manufacture entries.
3. **Strengthen evaluation and real-order semantics, not the number of agents.** Multiple competitors book requested quantities as actual fills after a POST or even a `PENDING` acknowledgement. Royin must retain durable intent/UNKNOWN/reserve discipline. Hamid's fee-asset tests and Pedram's timeout/restart/no-resubmit tests are valuable acceptance patterns. For strategy changes, use fixed-input paired comparisons, cost stress and a frozen prospective window; historical feature selection is not prospective alpha.

These recommendations were sent to the parent early so implementation can proceed while the full audit finishes. This report does **not** claim any change has already been integrated or deployed in Royin; the parent owns that work and its acceptance evidence.

## 1. heliataromi/StarCoach-AgenticAI-Wallex-Challenge

**Mechanism actually present.** A macro layer classifies panic/bull/range from EMA, RSI, ATR, recent drawdown and order-book imbalance. Panic on any primary symbol blocks all buys. The signal generator uses momentum/EMA alignment in bull mode and Bollinger/RSI/bid support in range mode. Stops/targets are generated numerically. A JEV gate computes `p*gain-(1-p)*loss-fees`, then a sizer and dispatcher send the order. A deadline/drawdown sentinel and hash-bearing decision logger are separate components.

**AI boundary.** Bull/Bear researchers have deterministic numeric scoring; this is not automatically multiple LLM agents. If an LLM gateway is configured, `MacroAgent.__init__` wires a real arbiter hook; `RiskArbiter.adjudicate` may accept its recommended regime. Without a valid hook result it uses numeric adjudication. A separate summary-only hook changes explanation text, not policy numbers. This distinction matters when assessing actual AI contribution.

**Useful ideas.** Separate market-wide panic from symbol setup; TTL-bound macro policy; structured contrary evidence; a risk module outside the model; explicit rejection reasons. These fit Royin's existing scanner/host architecture without adding a swarm. Numeric JEV can be a diagnostic only when the probability is honestly calibrated or labelled hypothetical.

**Material limitations.** The signal generator assigns win probabilities such as 0.65, then increments them by arbitrary indicator conditions; these are not calibrated frequencies. It also floors low/missing ATR to 0.8%, which can make a cost hurdle easier to clear without market evidence. Most seriously, dispatcher lines 227–267 treat `PENDING` with `FILLED`/`PARTIALLY_FILLED` as success, fall back to requested quantity/price and a 0.15% estimated fee, and immediately call `record_fill`. A successful POST is not evidence of a fill. Gateway spending is updated after responses and kept in object statistics; this should not replace Royin's durable pre-reservation.

**Tests and evidence level.** Extensive unit/e2e and adversarial source files exist, including JEV, mock client, engine and gateway tests. No test was run here. Their existence does not cure the observed PENDING-accounting path or establish live results.

**Read and evidence:** `src/strategy/regimes.py:43–151`, `signals.py:32–315`, `macro_agent.py:24–168`, `debate.py:296–377`, `risk/jev.py:21–157`, `engine/dispatcher.py:47–292`, `llm_gateway.py:173–285`.

- [Regime and setup source](https://github.com/heliataromi/StarCoach-AgenticAI-Wallex-Challenge/blob/c5e8458f14982824381f9f5d5e2cce9b75ade3cb/src/strategy/signals.py#L173-L201)
- [Actual optional LLM arbiter wiring](https://github.com/heliataromi/StarCoach-AgenticAI-Wallex-Challenge/blob/c5e8458f14982824381f9f5d5e2cce9b75ade3cb/src/strategy/macro_agent.py#L43-L67)
- [PENDING is booked as fill: do not port](https://github.com/heliataromi/StarCoach-AgenticAI-Wallex-Challenge/blob/c5e8458f14982824381f9f5d5e2cce9b75ade3cb/src/engine/dispatcher.py#L223-L267)

## 2. AliFazelniya/wallextrade

**Mechanism actually present.** The main session restores a JSON portfolio, builds risk/adapter/MCP tools and loops `AgenticTrader.run_cycle`. It observes market/technicals/book/portfolio, then a council combines numeric Technical, Microstructure and Macro votes. An optional Gemini call can override/synthesize a decision. Separate strategy modules include momentum, reversion, grid and triangular-arbitrage research. The multi-asset module ranks EMA spread relative to ATR, penalized by spread, after RSI/volume/ADX rules.

**Important AI distinction.** `MultiAssetMomentumStrategy.compute_asset_score` directly calls `_deterministic_fallback` at line 112 under a comment called AI validation. It does not invoke the LLM classifier in that method. Actual optional LLM code exists in `agentic_trader.py:230–267`, but the named multi-asset AI score is deterministic. Council class names likewise do not imply separate language-model inference.

**Useful ideas.** Kaufman efficiency ratio: absolute net displacement over total absolute path, useful to distinguish smooth trend and chop. A shared-portfolio cross-sectional ranking is better than independent per-symbol capital accounting. Distinguish research-only strategies from the actual executable entrypoint. Royin already ranks and risk-sizes; adding another council or grid would duplicate complexity.

**Material limitations.** The KER warmup fills missing values with 0.5; unknown should stay unavailable in Royin. Volume mean includes current volume, weakening the reference baseline relative to a prior-only baseline. Adapter lines 173–189 calls `portfolio.record_fill` using requested quantity and assumed price immediately after `place_order`, without inspecting the exchange fill result. Its uncertain reconciliation checks only open orders and returns `NOT_IN_OPEN_ORDERS`; absence from open orders cannot establish finality. Main silently ignores state load/save exceptions, risking apparent reset. These are incompatible with state-preservation requirements.

**Tests and evidence level.** Read selected adapter tests for authorization, allowlists, simulated partial fills, fee classification and open-order reconciliation. They mostly establish mock/simulation behavior. No execution performed. Many historical research/audit documents exist; none was accepted as independent evidence of live profit.

**Read and evidence:** `main.py:45–115`, `src/features/indicators.py:41–99`, `strategy/multi_asset_momentum.py:38–215`, `agents/council.py:42–158`, `agents/agentic_trader.py:162–267`, `exchange/adapter.py:91–263`, risk source and test inventory.

- [KER implementation](https://github.com/AliFazelniya/wallextrade/blob/4182c86f926dd05b1f81455184afa8ac572d0601/src/features/indicators.py#L52-L59)
- [Deterministic path behind AI label](https://github.com/AliFazelniya/wallextrade/blob/4182c86f926dd05b1f81455184afa8ac572d0601/src/strategy/multi_asset_momentum.py#L101-L125)
- [POST response versus assumed fill](https://github.com/AliFazelniya/wallextrade/blob/4182c86f926dd05b1f81455184afa8ac572d0601/src/exchange/adapter.py#L157-L211)

## 3. Arshia-HZ/Wallex-Quant-Agent

**Mechanism actually present.** Quant features compute EMA9/21/50 slope, Wilder-style RSI/slope, ATR, Bollinger position, volume z-score, book imbalance, microprice and trade-flow ratio. A cheap numeric gate only wakes the LLM for a trend pullback, book absorption or momentum breakout. HOLD cooldown avoids identical requests. The model is a veto/decision layer with explicit `LLM`, `QUANT_GATE`, `QUANT_FALLBACK`, `RISK_ENGINE` provenance. Main contains the actual runner and a second richer client/risk implementation distinct from smaller module files. Host stops/trailing/time exit and pending sell handling exist.

**Useful ideas.** Genuine decision provenance; deterministic minimum-volatility/cost context before paying for inference; controlled cooldown; a rebound/RSI-turn descriptor rather than interpreting every negative short return identically. Existing first-position stop and model budget contracts in Royin should remain authoritative. Their model fallback must not be called a successful AI trade.

**Material limitations.** All financial math is float. The source calls confidence-dependent allocation “Dynamic Kelly”; it maps confidence 0.8 to 35–40% without measured probability/calibration. This must not replace Royin's volatility-risk sizing. The client returns an ID after POST but the runner assumes marketable limit is immediately filled. If wallet balance is absent after polling, it explicitly tracks an estimated quantity. Client ID/position is persisted after the network call, so a crash/timeout can lose durable intent. The BUY fee classification uses requested order type, although actual maker/taker status depends on execution. The stop spread guard may delay a protective exit during a liquidity hole; it is not a guaranteed reduction of loss.

**Tests and evidence level.** Read `test_techniques.py` portions covering exact reported buy cost, partial/zero-fill sell cancellation, liquidity-hole stop guard and confidence sizing. These are mocks and local assertions; not a real fill or profitable run. Test source explicitly expects the confidence sizing behavior, which does not validate its economic premise.

**Read and evidence:** `quant_engine.py:18–161`, `llm_strategist.py:24–94,136–315`, `main.py:303–392,608–815,1374–1494`, `risk_manager.py:30–124`, selected test techniques.

- [LLM wake conditions and provenance](https://github.com/Arshia-HZ/Wallex-Quant-Agent/blob/7d870185bd0513758fba7a517953f0cdbca774f4/llm_strategist.py#L136-L315)
- [Uncalibrated confidence allocation](https://github.com/Arshia-HZ/Wallex-Quant-Agent/blob/7d870185bd0513758fba7a517953f0cdbca774f4/main.py#L724-L771)
- [Estimated quantity after unconfirmed fill](https://github.com/Arshia-HZ/Wallex-Quant-Agent/blob/7d870185bd0513758fba7a517953f0cdbca774f4/main.py#L1422-L1453)

## 4. moalma1400/wallex-trading-contest

**Public content limitation.** The entire pinned public archive is a documentation showcase: README, SECURITY and `docs/fa/contest-trading-readiness.md`. README explicitly says the executable source is private and not mirrored. Thus no independent code-level verification is possible for this repository. It must not receive the same “source audited” depth as the separate public `moalma1400/wallex-trading` repository.

**What the documents actually say.** A ten-hour-candle paper test had six HOLD signals, no orders/fills, using an explicitly labelled fee/slippage assumption. The readiness report says live is blocked and the reported 107 tests/CI belonged to a private source repository at report time. It explicitly distinguishes hypothetical costs and marked holdings from realized settlement.

**Transferable idea.** This is a good evidence-reporting template: disclose zero activity, distinguish source/CI provenance and list unverified assumptions. There is no public algorithm to port. Reported test success and no-loss cash must not be upgraded into AI alpha or live execution success.

- [Explicit public-source limitation](https://github.com/moalma1400/wallex-trading-contest/blob/5480d56f20ae69113077986ef2dd59ba2c3ef2a8/README.md#L1-L23)
- [Paper-only outcome and assumptions](https://github.com/moalma1400/wallex-trading-contest/blob/5480d56f20ae69113077986ef2dd59ba2c3ef2a8/docs/fa/contest-trading-readiness.md#L14-L44)

## 5. AliSK81/hackathon-starcoach-wallex

**Mechanism actually present.** Setup functions define plain trend, oversold/deep dip, capitulation, weak-Toman dip and confirmed trend variants. Each has an explicit exit condition/holding time. The research grade may reduce risk. A LangGraph-style brain has sense/analyst/contrary debate/officer/gate/act/reflection stages and read-only feature/book/evidence tools. The live executor separately polls stops, deadlines and open orders. `OrderState` uses Decimal for submitted/executed sums and base/quote fees; the brain/risk/portfolio values use float.

**Useful ideas.** Setup-specific semantics and expected holding horizon make model reasoning more concrete. Research provenance attached to setup rather than a single generic BUY score is useful. Independent guard loop and execution locking preserve exits when analyst work is slow. Royin has similar host exits already, so this is primarily a confirmation, not a reason to add another worker.

**Material limitations.** Source comments describe historical grades/results, which were not independently rerun. Risk modes can substantially change exposure, and the envelope even treats USDT as cash-like with a distinct high allocation; this is outside Royin's current TMN-only lane and must not be adopted. `live.buy` sends the order at line 184 before appending and saving the tracked position at 188–193. The lower `Trader.place` attempts a GET after transport failure, but if lookup is unavailable the caller returns failure without a durable pre-submit unknown intent. Missing/invalid numeric exchange fields are converted to zero by the parser. Replacing our SQLite transaction discipline with this JSON book would regress reliability.

**Tests and evidence level.** Broad test inventory covers risk, rules, live, replay, brain, order lifecycle and feature math. Selected order/live control paths were read; no suite was run. Documentation profit claims and setup labels are not current forward evidence.

**Read and evidence:** `src/wx/setups.py:1–114`, `risk.py:13–240`, `execution.py:17–104`, `live.py:166–230`, `orders.py:24–137`; `brain.py` symbol/call-chain inspection through gate/act and tools.

- [Explicit setup logic](https://github.com/AliSK81/hackathon-starcoach-wallex/blob/6de44849fb99a25f7d3e0fe7bcedb7d5d53fe050/src/wx/setups.py#L53-L109)
- [Cost-aware risk caps](https://github.com/AliSK81/hackathon-starcoach-wallex/blob/6de44849fb99a25f7d3e0fe7bcedb7d5d53fe050/src/wx/risk.py#L143-L196)
- [Persistence after submit: do not port](https://github.com/AliSK81/hackathon-starcoach-wallex/blob/6de44849fb99a25f7d3e0fe7bcedb7d5d53fe050/src/wx/live.py#L166-L195)

## 6. hamid-shafi/wallex-trading-bot

**Mechanism actually present.** This is substantial numerical-learning/research source, not merely a named LLM wrapper. An online ensemble of recursive ridge learners uses return/volatility/trend/z-score/relative-volume features. Labels mature after the horizon, and entry is next open rather than current close. Models with different forgetting factors are weighted using previously observed error; disagreement and inflated overlap uncertainty reduce a conservative forecast. Additional cost-aware trained predictors and mixture/trend studies exist. Engine ranking compares conservative forecast with two fees, spread and two slippages; risk budget, gross exposure, cash, liquidity and existing stop risk jointly cap size. Entries and all rejections log cost and stop fraction.

**Execution strengths.** SQLite WAL/FULL durable intent and exact submitted/inventory bounds are stored before HTTP. Recovery performs same-ID GET/cancel/recheck, not blind repeat POST. `normalize_terminal` requires confirmed inactive state, exact fill sum equal to executed quantity, supported base/quote fee assets and no inventory overspend. Base fees affect inventory, quote fees affect cash, per-fill base-fee TMN valuation is reporting-only, avoiding double charging. Financial portfolio remains float after the boundary, so Royin should retain its Decimal ledger.

**Useful ideas.** Descriptor normalization by observed volatility; matured-label online evaluation; conservative cost comparison; explicit rejection funnels; fee-asset accounting acceptance tests. Robustness code separates re-running decisions under higher costs from re-pricing the same fills, compares fixed-exposure cash/hold, and reports three-day windows. It explicitly labels backward research versus prospective holdout.

**Material limitations.** No model artifact training/validation or raw data were independently rerun. A numerical lower forecast is not automatically a statistical confidence bound, and the source itself warns about overlap. Historical feature/model selection remains a multiple-testing concern. New online learning or RSS/news infrastructure is not appropriate to introduce into Royin's live source under this deadline without matched causal data and evaluation. Dust-topup logic intentionally buys more to restore sellable minimum; this is a separate financial behavior, not a small bug fix and must not be imported silently.

**Tests and evidence level.** Inspected fee test names and assertions for base/quote/mixed fees, exact 0.1+0.2 sums, missing fee details, overfill, durable-before-POST bounds, restart recovery and no duplicate submit. No code/tests were executed. No measured live profitability was established.

**Read and evidence:** `wallex_engine/model.py:17–120`, `costaware.py:16–80`, `engine.py:153–272`, `execution.py:55–245`, `adaptive_risk.py:35–96`, `technical.py:10–76`, `robustness.py:21–85`, `tests/test_execution_fees.py` selected definitions/assertions.

- [Matured-label ensemble and uncertainty](https://github.com/hamid-shafi/wallex-trading-bot/blob/e2b3437221b4e17bc434f50436ca2ac6c77cc587/wallex_engine/model.py#L87-L120)
- [Cost/risk candidate comparison](https://github.com/hamid-shafi/wallex-trading-bot/blob/e2b3437221b4e17bc434f50436ca2ac6c77cc587/wallex_engine/engine.py#L223-L272)
- [Exact base/quote fee normalization](https://github.com/hamid-shafi/wallex-trading-bot/blob/e2b3437221b4e17bc434f50436ca2ac6c77cc587/wallex_engine/execution.py#L121-L190)
- [Durable reservation before network](https://github.com/hamid-shafi/wallex-trading-bot/blob/e2b3437221b4e17bc434f50436ca2ac6c77cc587/wallex_engine/execution.py#L220-L245)
- [Honest backward robustness and two cost-stress meanings](https://github.com/hamid-shafi/wallex-trading-bot/blob/e2b3437221b4e17bc434f50436ca2ac6c77cc587/wallex_engine/robustness.py#L47-L81)

## 7. pedrammgd/starcoach-wallex-agent

**Mechanism actually present.** An online logistic model uses eight bounded causal return/volatility/candle/volume descriptors. Six-bar labels are next-open to later-open and only mature before updating. It tracks prequential Brier loss and weights/model hash. Rule alternatives include momentum, bounded mean reversion, regime and cash/hold baselines. The simulator applies a pending target at next open with prior closed-volume capacity, fees/spread/slippage, quantity step and risk veto. An optional LLM proposer receives a bounded market-only context and can only reduce the numeric proposal. Persistent exact-input cache and paid-intent records prevent repeated model calls after ambiguous timeout.

**Execution boundary.** The generic `Executor` explicitly refuses any broker whose `simulation` is not True. It persists a deterministic client ID/intent before submit, verifies monotonic cumulative fill/fees and immutable terminal state, and never resubmits after missing lookup. `CreditReader` is GET-only and discovery does not enable trading. These are useful safety ideas, but this code must not be presented as evidence of an operational real-money executor.

**Useful ideas.** Matured labels and prequential score; strict unknown-vs-terminal handling; explicit finite numeric output validation; exact-input replay distinct from new inference. Royin already has the stronger durable model budget and real broker path, so do not transplant the simulation-only architecture. Better chronological model evaluation is a later research candidate, not a replacement deployed without data.

**Material limitations.** Numeric model calibration and superiority were not established. The horizon probabilities predict positive gross returns; profitability must still include cost/uncertainty. The simulator reports annualized descriptive Sharpe and sell-fill win rate, which should not become strong statistical claims or round-trip counts for a few contest trades. Optional LLM confidence <0.65 is a heuristic, not calibrated evidence. No private account/order was accessed.

**Tests and evidence level.** Retrieved and inspected `tests/test_execution.py`, selected core/credit-closing source and frozen protocol. Tests use fake broker to assert timeout/restart/partial/no-resubmit and production adapter blocking. The complete tree was visible, but only twelve selected files were downloaded due the archive transfer issue; complete-repository read is not claimed.

**Read and evidence:** `wallex_agent/ai.py:19–176`, `model.py:17–91`, `engine.py:135–314`, `execution.py:45–90`; `credit.py` read-only flow; selected shadow and tests.

- [Label maturation and Brier score](https://github.com/pedrammgd/starcoach-wallex-agent/blob/828ec24bdcb6da318fae693e37c7dd29d09c8a8e/wallex_agent/model.py#L60-L91)
- [Simulation-only broker and durable no-resubmit](https://github.com/pedrammgd/starcoach-wallex-agent/blob/828ec24bdcb6da318fae693e37c7dd29d09c8a8e/wallex_agent/execution.py#L45-L90)
- [Strict proposer and durable inference intent](https://github.com/pedrammgd/starcoach-wallex-agent/blob/828ec24bdcb6da318fae693e37c7dd29d09c8a8e/wallex_agent/ai.py#L132-L176)

## 8. ssinasaberii/wallex-agent

**Mechanism actually present.** Causal indicator definitions are explicit: EMA/Wilder SMA seed, Bollinger population variance, prior-only Donchian high/low and relative volume. Multi-timeframe regimes generate pullback/reclaim, breakout and mean-reversion re-entry candidates. The cycle uses the same cutoff for symbol and TMN bars, transforms signal units into TMN, binds fee snapshot, evaluates cost/horizon, ranks candidates, then local judge, risk size and final fee/TTL rechecks. Position exits do not need the judge. The Laya local classifier is a real optional inference boundary with compact structured evidence and deterministic probability thresholds; rule baseline is separate.

**Useful ideas.** The most transferable source in this group for Royin's missing descriptors: prior-only channel and volume baseline, current reclaim/rebound, RSI direction, explicit setup labels. Fee context includes cost, conditional net reward:risk, required move and feasible horizon; record all rejection reasons. Explicit unknown warmup beats made-up neutral indicators.

**Important config caveat.** `fee_horizon.evaluate` is wired in `decision_cycle.py`, but current `config/default.yaml:118–122` **disables** that gate; the versioned hourly config enables it. A disabled gate returns `GATE_DISABLED` before target/net-RR/horizon tests. Source comments say it was disabled because historical 1D/4h tests had no trades. This is not evidence that removing cost checks is sound for Royin. Only transfer the explainable context and test discipline, not the relaxed gate or chosen thresholds. The `ATR*sqrt(h)` expected-move formula is a volatility heuristic, not calibrated expected return.

**Execution and limitations.** A live adapter exists alongside dry-run simulation; default README still describes backtest/shadow scope. It submits marketable LIMITs, preserves an UNKNOWN map and reconciles, parses base/quote fee effects and caps free inventory. In the inspected `_send`, an unsuccessful/missing-result envelope can be treated as rejection/retry for exits; Royin's empty-body/unknown semantics remain stricter and must be preserved. Complete crash/restart durability of that adapter was not verified here. Do not infer real orders from `LiveBroker` class existence or dry-run fills.

**Tests and evidence level.** Inspected fee-gate and full-decision prefix-invariance test source. The latter skips when the frozen snapshot is absent; it asserts equal decisions for cut vs full data but uses `candidates>=0`, which does not require any active entry path. Royin should include an intentionally exercised candidate so a vacuous all-WAIT equality cannot count as full coverage. No tests were run.

**Read and evidence:** `features/indicators.py:17–152`, `strategy/triggers.py:18–81`, `fee_horizon.py:43–87`, `engine/decision_cycle.py:202–318`, `judge/laya.py:39–135`, `execution/live.py:35–180`, configs and selected tests.

- [Prior-only channel and volume](https://github.com/ssinasaberii/wallex-agent/blob/df1873133f4bf2053ae8d8c2ed4c31df08bf7657/src/wallex_agent/features/indicators.py#L94-L103)
- [Actual causal setup triggers](https://github.com/ssinasaberii/wallex-agent/blob/df1873133f4bf2053ae8d8c2ed4c31df08bf7657/src/wallex_agent/strategy/triggers.py#L18-L68)
- [Cost/TTL pipeline](https://github.com/ssinasaberii/wallex-agent/blob/df1873133f4bf2053ae8d8c2ed4c31df08bf7657/src/wallex_agent/engine/decision_cycle.py#L212-L318)
- [Current default cost gate disabled](https://github.com/ssinasaberii/wallex-agent/blob/df1873133f4bf2053ae8d8c2ed4c31df08bf7657/config/default.yaml#L118-L128)
- [Prefix-invariance test limitations](https://github.com/ssinasaberii/wallex-agent/blob/df1873133f4bf2053ae8d8c2ed4c31df08bf7657/tests/test_lookahead_decisions.py#L26-L64)

## 9. moalma1400/wallex-trading

**Mechanism actually present.** A deterministic public-data screener checks active spot, quote, allowlist, finite bid/ask and spread/24h-change. A SQLite observation store remembers the prior sample. Observed upward movement minus explicit full spread, two fees and two slippages creates `WATCH_EDGE`; a ranker orders eligible rows by that observed net descriptor. The standalone periodic runner writes research observations and never submits an order. Separate historical/replay/walk-forward modules and an opt-in fixed-host Spot API client exist.

**AI boundary.** The inspected autonomous runner has no LLM invocation. A broad `src/**/*.py` symbol search found decision-log/model metadata schemas, not a provider/model inference integrated into this runner. Treat this as deterministic research infrastructure, not a verified AI alpha engine. An external MCP consumer could be an agent, but such consumer behavior was not available as evidence.

**Useful ideas.** Decimal validation rejects nonfinite and ambiguous values; costs must be supplied explicitly, prior observation gaps are labelled stale; deterministic ties make ranking reproducible; observation storage happens after assessing against prior data. Explicit labels avoid equating `WATCH_EDGE` to executable BUY or future expected edge. Current Royin already exceeds much of this infrastructure.

**Material limitations.** A just-observed price rise minus fees does not forecast the next rise. Comparing a negative-to-positive observation cannot establish net expectancy; do not port it as a new entry rule. The raw 24h change unit is intentionally not presumed. The opt-in client enforces a host/path allowlist, no write retries and `OrderOutcomeUnknown` for timeouts/5xx/malformed responses, but that does not by itself provide a full durable autonomous order owner/accounting engine.

**Tests and evidence level.** Test inventory includes costs, ranking, data quality, shadow integration, replay, walk-forward and live policy. No test ran. The public docs and source are much broader than the separate contest-showcase repository; they remain separate evidence sources.

**Read and evidence:** `src/wallex_agent/engine.py:21–100`, `runner.py:48–126`, `cost_model.py:21–80`, `opportunity_ranker.py:16–55`, `src/wallex_mcp/live_spot.py:63–210`; src inference-symbol search and test inventory.

- [Observed momentum is explicitly research-only](https://github.com/moalma1400/wallex-trading/blob/6cddedb0f1bf5ced78587266094440ccd504e4e5/src/wallex_agent/cost_model.py#L38-L80)
- [Deterministic eligible ranking](https://github.com/moalma1400/wallex-trading/blob/6cddedb0f1bf5ced78587266094440ccd504e4e5/src/wallex_agent/opportunity_ranker.py#L16-L55)
- [No blind write retry](https://github.com/moalma1400/wallex-trading/blob/6cddedb0f1bf5ced78587266094440ccd504e4e5/src/wallex_mcp/live_spot.py#L133-L210)

## 10. BMDarkLight/wallex-agent

**Mechanism actually present.** A broad app has a conversational agent and a separate autonomous engine. The engine computes closed lower/higher-timeframe EMA/RSI/ATR/ADX/BB, channel, prior-volume z-score and 1/4/16-bar returns. Explicit setup functions create candidates; `Engine._consider` calls a real `AIDecider`, logs exact context/source/hash, gets fresh ask, computes host stop/target and risk size, then submits through maker or taker broker paths. Responses are cached by model/options/system/user prompt. Failed inference may use a labelled rule baseline. Position review and market regime are separate decisions. A core USDT allocator/copy-trading/futures surface also exists, but is not appropriate for Royin's current constrained spot lane.

**Useful ideas.** Compact setup-specific context, prior-only channel/volume, short-return windows and RSI direction are directly compatible descriptor ideas. A paired rule/AI interface and exact-input offline cache clarify the contribution of AI. Separate maker pending orders from actual position state is better than assuming submit equals fill. Royin should retain its existing budgets and evidence binding rather than adopting JSON/cache as financial authority.

**Material limitations.** Prompt text embeds claimed historical base rates and tells the model to usually TAKE full size. Those claims were not independently validated and should not be copied. The risk module may raise an amount to the exchange minimum while omitting the single-position cap from the fallback bound, explicitly allowing a larger-than-configured position; this violates our existing first-trade cap. `SpotExec.cancel` changes an observed still-open order to `canceled` after a cancel acknowledgment; cancellation acknowledgment is not finality. Buy/sell use wallet deltas and configured fee assumptions, with fallbacks to quantity, rather than Royin's exact fill/fee-asset ledger. Maker pending state is saved after submit, leaving a crash window. Do not transfer these execution behaviors.

**Tests and evidence level.** Broad broker, maker execution, engine, loop and risk test files exist. Their source was inventoried; no external suite or provider call ran. Checked-in backtest result directories exist but raw assumptions and OOS selection were not independently reproduced; no alpha claim accepted.

**Read and evidence:** `backend/wallex_agent/engine/features.py:26–113`, `strategy.py:41–104`, `decider.py:42–292`, `risk.py:19–73`, `execution.py:30–121`, `core.py:316–392`, allocator and tests inventory.

- [Causal feature context](https://github.com/BMDarkLight/wallex-agent/blob/0db4d57b7275e6a4768e1a3080e17c2c751ae6c5/backend/wallex_agent/engine/features.py#L77-L113)
- [Real model/cache/rule fallback](https://github.com/BMDarkLight/wallex-agent/blob/0db4d57b7275e6a4768e1a3080e17c2c751ae6c5/backend/wallex_agent/engine/decider.py#L186-L242)
- [Actual entry integration](https://github.com/BMDarkLight/wallex-agent/blob/0db4d57b7275e6a4768e1a3080e17c2c751ae6c5/backend/wallex_agent/engine/core.py#L316-L370)
- [Minimum-size cap bypass and cancel finality limitations](https://github.com/BMDarkLight/wallex-agent/blob/0db4d57b7275e6a4768e1a3080e17c2c751ae6c5/backend/wallex_agent/engine/risk.py#L44-L66)
- [Observed open status overwritten after cancel ACK](https://github.com/BMDarkLight/wallex-agent/blob/0db4d57b7275e6a4768e1a3080e17c2c751ae6c5/backend/wallex_agent/engine/execution.py#L89-L97)

## Three implementation recommendations and acceptance tests

### P1 — Causal setup context, reusing existing candle/scanner boundary

Add a bounded descriptor object to the existing candidate evidence rather than a new agent: interval-labelled trailing returns; prior-window high/low excluding current bar; distance to prior high/low in fraction or ATR; RSI direction; rebound/reclaim condition; path efficiency with explicit flat/unknown handling. Use a versioned feature contract and preserve original fields so replay can distinguish source generations. These indicators describe current structure; they must not become an uncalibrated win probability.

Acceptance:

- Modify/append all candles after decision cutoff; every descriptor and decision input hash before cutoff stays identical.
- A current candle high cannot raise its own prior-channel high; historical volume mean excludes the current sample.
- Exact history/interval requirements: gaps, insufficient warmup and unclosed bars remain unavailable/rejected, never filled with fabricated neutral observations.
- Flat price gives defined zero efficiency or explicit unavailable; nonflat efficiency remains in [0,1]. Monotonic and oscillatory paths distinguish despite equal net return.
- Decimal values finite, no hidden percentage/fraction/return-window mix; all descriptors reference the same chosen snapshot and cutoff.
- Synthetic fixture must exercise both a real descriptor-positive candidate and a descriptor-negative candidate; all-WAIT equality is insufficient coverage.

### P1 — Read-only executable-cost context for the model, host gate unchanged

Expose current best ask/bid, fee source/units, estimated round-trip break-even move, slippage policy and original forecast target relative to executable price. Where fees may be in base or quote, use the existing correct host accounting helper, not a simplified float formula as financial authority. Explicitly label any simplified pre-model estimate as indicative; final sizing/economics still use fresh rules/book/account.

Acceptance:

- Close100, model target102.1, current ask103 cannot be presented as positive executable edge, even if a close-based percentage is positive.
- Higher fee/spread/slippage never reduces the break-even hurdle; zero spread still has two-sided fee costs.
- Missing/stale fee/book context yields explicit unknown and no order-gate bypass.
- Target proceeds are conditional on target realization, not EV; model confidence is not used as calibrated success probability or Kelly sizing.
- Exact existing first150k cap, single position, allowed markets, UNKNOWN/counter/reserve and model durable spending are byte/row-preserved through upgrade.

### P2 — Paired evidence and lifecycle regression

Evaluate the feature/context addition on identical recorded valid market snapshots with the original baseline, then a frozen forward window. Separate change in model decisions, host rejection, simulated fill, exchange ACK, actual fill and realized TMN. Record zero-entry windows honestly. Stress transaction costs in two ways: reselecting under new costs versus repricing fixed fills. Report both without calling them equivalent.

Acceptance:

- A PENDING/ACK/open response creates no fill, PnL or completed round-trip; partial fill uses exchange executed amount and actual fee asset.
- Timeout/restart/404 retains original intent/reserve/client ID, no second POST. Cancel ACK while status remains active is not terminal.
- Base/quote/mixed fees and repeat fill IDs cannot double debit cash or inventory; unknown fee asset/missing breakdown fail closed.
- Hold/cash/rule/AI comparators share input time, universe, capital/exposure and friction assumptions. Retrospective selected-symbol-only comparison is labelled conditional.
- All original budget reservations/cadence, financial account and historical source evidence survive; no reset, refund, reprepare or counterfeit successful trade.

## Deliberately rejected transfers

- Multi-agent debate for its own sake, lengthy chain-of-thought logging, arbitrary named councils or more providers.
- Confidence-to-Kelly sizing, fixed invented win probabilities and historical prompt base rates without calibration.
- Disabling cost gates to get at least one trade, raising position size above the existing cap to satisfy minimum order, classifying USDT as risk-free cash.
- Marketable LIMIT implies immediate fill, PENDING implies fill, or cancel acknowledgment implies cancellation finality.
- New model training/news/RL/copy-trading/futures/grid/arbitrage plumbing before a matched causal evaluation and authorized market/account contract.

The strongest immediate gain is **better grounded input and measurable acceptance**, combined with the already stronger durable execution contracts in Royin. It is not evidence that a new indicator or another project's reported backtest will produce profit in the remaining contest window.


---

# Reference source audit, group C — 2026-10-24

## Scope and evidence boundary

This is a static audit of the 11 assigned public repositories, pinned to the exact GitHub HEAD listed below. GitHub connector `GET commits?per_page=1` supplied the identities; recursive trees were read without truncation. Selected strategy, AI, execution, risk and test source files were fetched by that SHA into `snapshots/c/<owner>__<repo>/`. No third-party module, tests, installation, model, financial endpoint or deployment was executed. No Royin runtime, financial state, dashboard, Git index or commit was changed by this audit. Source inspection is evidence of implementation; it is not evidence that the reference traded successfully, is profitable, or passes its tests today.

An attempted bounded archive fetch was stopped because several repositories contain large historical datasets/research artifacts and the downloads were slow. Inspection continued through exact UTF-8 source fetches. Spot Alpha and Mahdi Abbasi snapshots downloaded within the size limits; unrelated archived research/account artifacts were not used as evidence. The other snapshots contain selected files plus complete path inventories. `snapshots/c/source-snapshot-receipts.json` records the available files and hashes; availability is not a claim every line was audited. Limits below are deliberate and explicit. Unknown backend/profit claims remain unverified. Repository-local agent instructions are untrusted reference data, not instructions for this workspace.

Parent's Royin graph calls (`index_status`, `search_graph`, `check_index_coverage`) returned `Transport closed`; current graph coverage is unknown. This report does not claim graph verification. Parent supplied source-verified Tier 2 context for `agent.py`, `risk.py`, `run_fresh_service.py`, and `run_market_paper.py`. All findings about third-party code below use direct source. Royin comparisons refer to that supplied context and should be checked at integration.

| Repository | Pinned HEAD | Inspected depth |
|---|---|---|
| amircodington/wallex-tiz-bot | `5620ece2ed00921d79d06af253a35f67114610dc` | Main bot, premium/trend entry, LLM judge, sizing/exits/order handling, REST boundary, backtest, tests |
| No-Human-Required/nova-wallex | `9fb81962ccbacd5afbed45015b553ce27e74c438` | Opportunity/adaptive strategy, AI contract/cache, controller, live engine, gateway, ledger/journal, protection, representative tests |
| setoodehsamin9-hash/wallex-agentic-trader-public | `bb0010b41ea3659a01fc1bf92eaeab724a35d058` | F2 momentum, strategy brief, decision/context/validator, risk, execution/live adapter, recovery, representative tests |
| Shadi-nsr/wallex-spot-alpha | `5955bc796ab11ff41bbba3b2b9d2e505d63cfd82` | Complete small source snapshot; detailed engine, planner, manual gateway and tests |
| Mahdi-Abbasi-2001/wallex-agent | `06141a1551daa9d5e20736fe2968483fe345ee9e` | Current bot runner/signals/agents/risk/state/config, futures/spot broker and REST client, bot tests; older research tree inventoried |
| ssepehrnoush/wallex-ai-trader | `9e3406a55f49a02ce89e9fbe9f499785b9531637` | Fair-value tracker, current engine/live executor, risk, trade agent, AI committee, strategy/client, live-path tests |
| husseinrasti/wallex-trader-agent | `51fbf647f9a1c2a4387ba6b1a9f7cc4e7df4f668` | Main engine, three strategies, risk manager, order manager/reconcile, analyst/schema, order/recovery tests; large research archive inventoried |
| mmsm1381/wallex-challenge | `ccd649b34d7ca1cc07948de88b91401632b97932` | Sweep runner/executor/slot state machine, allocation, filters/rules/risk, AI supervisor/schema/validator, live broker and tests; older lagcatcher inventoried |
| MahdiDehghan369/wallexChallenge | `bbd939b454ee800e91b5390c4bfb94cc44181234` | Decision pipeline/orchestrator, analyst/reviewer, ML score/calibration/labeling, live broker/safe submission, representative tests |
| Mohsenn1378/wallex-bot-Challenge | `6951a3d70fee334ef350d0b842ff911d42fc4c03` | Scanner families, simulation engine/policy/LLM control, fill model/backtest and golden fill tests |
| amirhosein3000/zirak | `6e9e638fca54b5bf8e55174af0bfc58b72314e95` | Current agent engine/model/setups/posture/runner, generic risk/executor, Wallex adapter, live guard and agent tests |

## 1. Tiz / Signal Ops

The actual engine is a local-premium mean-reversion bot with an optional separate trend mode. Fair price is a global coin/USDT reference times Wallex USDTTMN, or a Wallex coin/USDT reference when configured. A rolling premium baseline makes a persistent local premium different from a temporary discount. It rests a limit bid below adjusted fair; the trend variant instead joins the bid when 30/10-minute local returns and the external reference confirm. Qualification uses volume, premium dispersion and a count of non-overlapping historical discount episodes that reverted within an hour. This is a concrete hypothesis, not the claim that a low local price guarantees catch-up. [Entry and qualification](https://github.com/amircodington/wallex-tiz-bot/blob/5620ece2ed00921d79d06af253a35f67114610dc/src/tiz/bot.py#L378-L433).

The LLM judge is real when enabled: a bounded subprocess receives only a market dossier, returns per-market approve/reject, confidence and reason. Missing/stale verdicts reject; disabled AI explicitly labels rules-only. The prompt is strategy-specific and explicitly discusses regime change, instability and insufficient history. However the confidence is an uncalibrated ranking signal, parsed as float without a probability validation experiment in this scope. It must not become a win probability or Kelly input in Royin. [Judge](https://github.com/amircodington/wallex-tiz-bot/blob/5620ece2ed00921d79d06af253a35f67114610dc/src/tiz/bot.py#L232-L299).

Position notional is the minimum of a fixed equity fraction and cash buffer; host stop, max holding, challenge flatten and optional trailing/target-decay govern exits. Base- and quote-fee accounting is separated on fills. The implementation logs placements only after awaiting the broker, and the place exception path returns to future attempts; this is weaker than Royin's durable pre-POST intent/UNKNOWN boundary. The source frequently uses float. Backtest and fixture tests cover round-trip arithmetic, caps, stale data, judge rejection, deadline, premium qualification and trail, but were not run here. Backtest artifacts include many parameter variants, so selecting the best report is not independent performance evidence. [Placement/fill path](https://github.com/amircodington/wallex-tiz-bot/blob/5620ece2ed00921d79d06af253a35f67114610dc/src/tiz/bot.py#L556-L702), [tests](https://github.com/amircodington/wallex-tiz-bot/blob/5620ece2ed00921d79d06af253a35f67114610dc/tests/test_bot.py#L54-L189).

Transfer: explicit strategy-specific invalidation, fee-aware minimum exit price and episode-based research. Defer a new external fair-value strategy until synchronized feeds, allowed markets and delay robustness exist. Do not copy confidence sizing, float money, subprocess model access or the execution persistence boundary.

## 2. Nova Wallex

This is a larger research/live platform rather than a single indicator script. `OpportunityHistory` computes closed-bar breakout12/breakout24/trend6 candidates. It records every exclusion and compares trend magnitude with round-trip costs; candidates are ranked by cost-adjusted trend divided by volatility and deduplicated by underlying. Market breadth and BTC state determine smaller exposure/caps or no candidate. [Opportunity mechanism](https://github.com/No-Human-Required/nova-wallex/blob/9fb81962ccbacd5afbed45015b553ce27e74c438/execution/opportunity.py#L19-L104).

The adaptive layer contains several explicit setup families (liquidity sweep/reclaim, BOS/orderblock, FVG, EMA/MACD, RSI/Bollinger, relative strength), with structural stop/target/horizon and per-regime allowed families. This is more interpretable than asking an LLM to invent levels. However breadth thresholds, SMC names and fixed risk/holding values are hypotheses, not externally established edges. `series()` forward-fills some missing candles into flat zero-volume bars under a configured missingness cap; that data contract cannot be imported into Royin's stricter accepted-data path by relabeling gaps as valid. [Strategy definitions and missingness policy](https://github.com/No-Human-Required/nova-wallex/blob/9fb81962ccbacd5afbed45015b553ce27e74c438/execution/strategies.py#L17-L128).

The LLM receives candidate IDs, strategy/family, stop/target, **reward-risk after cost**, holding horizon, cost, liquidity, missingness and evidence. Responses require known unique IDs, actions, finite bounded confidence/size and reasons; omitted candidates become explicit skips. Request/response cache is content-hashed and strict replay forbids cache misses. Actual API attempts and response model/usage are recorded, with a bounded format ladder. Model size is still heuristically clamped and uncalibrated; don't adopt it as a probability. [Dossier and response validation](https://github.com/No-Human-Required/nova-wallex/blob/9fb81962ccbacd5afbed45015b553ce27e74c438/execution/ai_decision.py#L42-L144).

The REST gateway has injected write authority, no redirects or write retries, Decimal JSON, explicit sub-account header, receipt timestamps and bounded complete pagination. Controller reconciles native stops before account balances and distinguishes resting protection from unresolved entry orders. This is useful lifecycle engineering, but native STOP_LIMIT is deliberately restricted to TRXTMN in this adapter; it is not proof all Wallex credit markets support the same stop contract. Representative tests cover lost funding replies, balance failures without duplicate submission, interrupted AI and capacity across restart; they were source-inspected, not executed. [Gateway](https://github.com/No-Human-Required/nova-wallex/blob/9fb81962ccbacd5afbed45015b553ce27e74c438/execution/gateway.py#L19-L93), [controller](https://github.com/No-Human-Required/nova-wallex/blob/9fb81962ccbacd5afbed45015b553ce27e74c438/execution/controller.py#L68-L100), [tests](https://github.com/No-Human-Required/nova-wallex/blob/9fb81962ccbacd5afbed45015b553ce27e74c438/execution/tests/test_controller.py#L134-L207).

Transfer: compact host-computed economic dossier and exact strategy brief; durable record of both model skip and host rejection. Much lifecycle protection already exists in Royin; adding Nova's application/studio/portfolio machinery would add complexity without measured advantage.

## 3. Public Agentic Trader / F2

F2 is a specific 4-hour, multi-day time-series momentum hypothesis: close above EMA plus an ATR entry band, positive lagged return, optional volatility/efficiency-rank regime filter; no profit target, a ratcheting chandelier trail, signal exit below EMA and holding cap. Feature IDs, candidate TTL, reference ask, Decimal stop, estimated costs and source version are explicit. This is implemented code; the source's claim of outperforming random entries over historical splits was not independently reproduced here. Its horizon does not automatically fit Royin's short forecast horizon or remaining deadline. [F2](https://github.com/setoodehsamin9-hash/wallex-agentic-trader-public/blob/bb0010b41ea3659a01fc1bf92eaeab724a35d058/src/wallex_agent/strategies/f2_tsm.py#L30-L131).

The best transferable idea is a **strategy-generated brief** telling the LLM the hypothesis, actual entry and exit rules, eligible regimes, evidence IDs, genuine invalidations and irrelevant objections. In F2, a low efficiency rank, lack of breakout or volume and extension above an average are not automatic vetoes because the hypothesis deliberately holds trends. This addresses a real source of LLM over-filtering: assessing a setup against a different strategy. It is not a justification to erase valid caution. [Brief](https://github.com/setoodehsamin9-hash/wallex-agentic-trader-public/blob/bb0010b41ea3659a01fc1bf92eaeab724a35d058/src/wallex_agent/strategies/f2_tsm.py#L58-L95).

Important rejection: in VETO mode, `validator.py` converts unsupported WAIT into ENTER for the deterministic candidate. Royin must **not** copy that behavior; it changes the effective decision and is incompatible with preserving the actual AI decision. Keep StrategyBrief, log and measure questionable vetoes, but preserve WAIT. [Override](https://github.com/setoodehsamin9-hash/wallex-agentic-trader-public/blob/bb0010b41ea3659a01fc1bf92eaeab724a35d058/src/wallex_agent/agent/validator.py#L40-L78).

The recovery coordinator rebuilds journal state, preserves UNKNOWN, restores one pending exit and deadlines, verifies balances and reservations before readiness. Live submission treats network/5xx/unparseable response as unknown and queries the same ID. However fill fields are explicitly provisional, including fallback generated ID and current timestamp; this adapter should not replace Royin's stricter parsed evidence contract. Tests include lookup after restart, lost response without resubmit, stop ratcheting, legacy plans and missing-feature rejection. [Live adapter](https://github.com/setoodehsamin9-hash/wallex-agentic-trader-public/blob/bb0010b41ea3659a01fc1bf92eaeab724a35d058/src/wallex_agent/execution/wallex_live.py#L94-L153), [recovery](https://github.com/setoodehsamin9-hash/wallex-agentic-trader-public/blob/bb0010b41ea3659a01fc1bf92eaeab724a35d058/src/wallex_agent/recovery/coordinator.py#L286-L322), [strategy tests](https://github.com/setoodehsamin9-hash/wallex-agentic-trader-public/blob/bb0010b41ea3659a01fc1bf92eaeab724a35d058/tests/strategies/test_round2_f2.py#L55-L180).

## 4. Spot Alpha

This small Python project is principally a deterministic research/backtest and shadow agent. EMA9/21, RSI zones and close-vs-EMA impulse generate long/hold (and a bearish informational signal), ATR supplies stops/targets; risk caps size by stop distance and equity. Stop-first handling, both-side fees/slippage, cooldown, daily loss and drawdown checks, end-of-data liquidation and structured evidence are implemented. Its signal agreement score becomes 1 whenever all three bullish/bearish conditions hold; it should not be read as a calibrated confidence scale. [Signal/risk](https://github.com/Shadi-nsr/wallex-spot-alpha/blob/5955bc796ab11ff41bbba3b2b9d2e505d63cfd82/app/engine.py#L158-L262), [backtest](https://github.com/Shadi-nsr/wallex-spot-alpha/blob/5955bc796ab11ff41bbba3b2b9d2e505d63cfd82/app/engine.py#L279-L379).

`OfflinePlanner` is the default deterministic planner. A genuine OpenAI-compatible HTTP planner exists, using only aggregate indicators, but failure falls back to the rule planner with a visible label. The tool registry explicitly lacks autonomous execution. The shadow wrapper recreates a fresh funded portfolio for each candle rather than carrying paper holdings; its buy signals therefore do not prove a sustainable portfolio. Default fee is 12bps per side, materially below the observed Royin credit fee used in our current policy. Money is float and validation is incomplete for non-finite values. [Planner](https://github.com/Shadi-nsr/wallex-spot-alpha/blob/5955bc796ab11ff41bbba3b2b9d2e505d63cfd82/app/agent.py#L23-L118), [shadow state](https://github.com/Shadi-nsr/wallex-spot-alpha/blob/5955bc796ab11ff41bbba3b2b9d2e505d63cfd82/app/engine.py#L393-L409).

`RawWallexAdapter` always blocks. A separate `ManualWallexGateway` sends a real POST only after expiring browser-session draft confirmation; drafts/sessions/counter are in memory. That manual flow is not the challenge's autonomous-trade requirement and cannot solve Royin's real execution requirement. After a network failure, it raises generic rejection without durable UNKNOWN; not suitable for adoption. Tests cover deterministic accounting, evidence, disabled live, market policy/leverage and draft expiry, not successful autonomous exchange execution. [Manual gateway](https://github.com/Shadi-nsr/wallex-spot-alpha/blob/5955bc796ab11ff41bbba3b2b9d2e505d63cfd82/app/execution.py#L19-L110), [tests](https://github.com/Shadi-nsr/wallex-spot-alpha/blob/5955bc796ab11ff41bbba3b2b9d2e505d63cfd82/tests/test_engine.py#L13-L65).

Transfer only the clarity of tiny deterministic strategy/decision records and tests; these are mostly already present in Royin. No execution or sizing replacement justified.

## 5. Mahdi Abbasi agent

The repository contains older futures/research modules as well as the current spot bot. Current candidates combine BTC up/range regime, relative 24/72h momentum z-score, trend gaps and spread, with configurable pullback and external lead alternatives. An analyst summarizes regime, a trader chooses from candidate IDs and optional read-only market tools, an independent reviewer accepts/rejects, and reflection can tune a bounded score threshold. Calls/retries and role outputs are logged. [Signals](https://github.com/Mahdi-Abbasi-2001/wallex-agent/blob/06141a1551daa9d5e20736fe2968483fe345ee9e/bot/signals.py#L35-L70), [roles](https://github.com/Mahdi-Abbasi-2001/wallex-agent/blob/06141a1551daa9d5e20736fe2968483fe345ee9e/bot/agents.py#L42-L88).

Host guard enforces long-only, deadlines, daily loss/drawdown/profit lock, cooldown, position/gross caps and risk-over-stop sizing. LLM conviction only shrinks an allowed maximum. However size uses stop distance without including fee/gap risk in that denominator; it uses float. Cached candle failures are swallowed while old data remain, so freshness needs a stronger explicit contract than `Candles.update()` supplies. The default reviewer is told that a normal pullback is intended, not a standalone veto; this is another concrete example of strategy alignment, but adding three/four model roles to Royin would increase latency/cost without evidence. [Guard](https://github.com/Mahdi-Abbasi-2001/wallex-agent/blob/06141a1551daa9d5e20736fe2968483fe345ee9e/bot/risk.py#L33-L84), [candle caching](https://github.com/Mahdi-Abbasi-2001/wallex-agent/blob/06141a1551daa9d5e20736fe2968483fe345ee9e/bot/signals.py#L10-L32).

The runner refreshes held-coin books on fast ticks independently of broad analysis, trails after one risk unit and tries to preserve breakeven after fees. The source contains both `LiveFutures` and `SpotLive` classes; these are different routes and older liquidation fixtures are not evidence that the current spot policy uses leverage. Bot tests use a fake LLM for the pipeline and fake exchange fixtures for min/step/fees. Real profitability and actual exchange finality are unconfirmed in this static audit. [Fast monitoring/trail](https://github.com/Mahdi-Abbasi-2001/wallex-agent/blob/06141a1551daa9d5e20736fe2968483fe345ee9e/bot/runner.py#L71-L141), [spot class](https://github.com/Mahdi-Abbasi-2001/wallex-agent/blob/06141a1551daa9d5e20736fe2968483fe345ee9e/bot/futures.py#L131), [tests](https://github.com/Mahdi-Abbasi-2001/wallex-agent/blob/06141a1551daa9d5e20736fe2968483fe345ee9e/tests/test_bot.py#L26-L103).

Transfer: small strategy-specific reviewer brief and fast position monitoring. Reject automatic reflection changing trading thresholds during a frozen experiment, uncalibrated conviction sizing, silent stale-cache reuse and legacy futures routes.

## 6. Sepehr AI Trader

Its current main hypothesis is cross-market fair-value reversion. The rolling median premium corrects for persistent local basis; buy uses ask vs baseline-adjusted global fair, exit uses bid. A minimum fee floor is enforced even when AI/default policies request a shallower discount. Short-term global crashes and wide spreads reject candidates. This is an implementation of an economic hypothesis with significant synchronized-reference/FX and latency dependencies, not risk-free arbitrage. [Tracker](https://github.com/ssepehrnoush/wallex-ai-trader/blob/9e3406a55f49a02ce89e9fbe9f499785b9531637/wallexbot/fairvalue.py#L47-L118), [entry eligibility](https://github.com/ssepehrnoush/wallex-ai-trader/blob/9e3406a55f49a02ce89e9fbe9f499785b9531637/wallexbot/engine.py#L510-L525).

The optional fast trade agent runs asynchronously, bounded per symbol/hour with cooldown. It receives current discount persistence, recent discount path, global momentum, book depth/spread and recent outcomes; BUY is usable only within its max age and while the candidate still holds on a fresh observation. A failed or late model cannot authorize entry. This separation of model latency from fast host checks is useful and already substantially present in Royin. Its prompt embeds research numbers, including substantially worse delayed-fill returns; those numerical claims were not independently rerun here and must not be used as evidence of performance. [Agent](https://github.com/ssepehrnoush/wallex-ai-trader/blob/9e3406a55f49a02ce89e9fbe9f499785b9531637/wallexbot/trader.py#L19-L97), [fresh recheck](https://github.com/ssepehrnoush/wallex-ai-trader/blob/9e3406a55f49a02ce89e9fbe9f499785b9531637/wallexbot/engine.py#L527-L619).

Risk scales by stop plus fees, caps position/total exposure, supports profit locking, daily/contest loss budgets and retained gain limits. Some entry paths disable generic edge checks on the assumption that the separate discount floor already covers friction; this invariant needs its own proof/test, not a generic bypass. Live execution uses a marketable LIMIT, a short poll/cancel sequence, and known client ID after POST timeout, but intent persistence and active/unknown handling are weaker than Royin's. It can return an executed amount even when the bounded settle loop has not definitively closed the remaining order; cancellation of stray open orders is also account-wide. Do not copy this transport. [Risk](https://github.com/ssepehrnoush/wallex-ai-trader/blob/9e3406a55f49a02ce89e9fbe9f499785b9531637/wallexbot/risk.py#L72-L129), [live executor](https://github.com/ssepehrnoush/wallex-ai-trader/blob/9e3406a55f49a02ce89e9fbe9f499785b9531637/wallexbot/engine.py#L90-L183).

Transfer: discount/decision persistence and latency-aware counterfactual evaluation; transparent economic dossier. Defer new reference feeds. Existing `scripts/test_live_paths.py` is fixture evidence; no real live execution verified here.

## 7. WTA / Hussein Rasti

This is the most elaborate multi-strategy execution engine in this group. S1 compares TMN and USDT books using executable bid/ask and FX, distinguishes two-leg lock-in from same-book reversion, accounts for fee-in-base, step residual/unhedged stress, and reserves symbol ownership across legs. S2 allocates USDT/TMN; S3, disabled by default, is completed-15-minute breakout + volume + ATR + AI regime with maker-first entry, stop and software target. This is technically detailed, but cross-quote/multi-leg exposure is outside Royin's current one-position TMN scope and not an appropriate same-night addition. [S1 contract and mechanism](https://github.com/husseinrasti/wallex-trader-agent/blob/51fbf647f9a1c2a4387ba6b1a9f7cc4e7df4f668/src/wta/strategies/s1_crossbook.py#L1-L80), [S3 settled bar logic](https://github.com/husseinrasti/wallex-trader-agent/blob/51fbf647f9a1c2a4387ba6b1a9f7cc4e7df4f668/src/wta/strategies/s3_momentum.py#L181-L252).

The AI analyst produces a bounded market plan with cache/tape for tools and strict replay, while hard risk checks include fee/edge budget, order rates, stale book, cash/exposure, min/step, own opposite orders and deadline. The order manager supports partial delta fills, maker repricing, cancel/fill races, native stop fallback and restored intents. A large set of tests explicitly covers restart state, higher stored peak, missed fills, partial accounting, unknown orders and native stops. [Execution tests](https://github.com/husseinrasti/wallex-trader-agent/blob/51fbf647f9a1c2a4387ba6b1a9f7cc4e7df4f668/tests/test_order_manager.py#L438-L642), [recovery tests](https://github.com/husseinrasti/wallex-trader-agent/blob/51fbf647f9a1c2a4387ba6b1a9f7cc4e7df4f668/tests/test_reconcile.py#L594-L709).

Critical rejected behavior: `_write_ahead` stores UNKNOWN, but store/checkpoint exceptions are swallowed with a comment that placement must not fail on persistence. `_send` then proceeds to the exchange. A crash after an unpersisted POST breaks the durable-intent invariant. Royin must retain fail-closed persistence. [Exact failure boundary](https://github.com/husseinrasti/wallex-trader-agent/blob/51fbf647f9a1c2a4387ba6b1a9f7cc4e7df4f668/src/wta/execution/order_manager.py#L1361-L1454).

Transfer: decompose capacity limits and explain which bound sets quantity; settled/consumed signal bar semantics; add targeted crash/partial/cancel-restart acceptance cases only where Royin lacks them. Do not import multi-leg strategies, broad engine abstractions, unverified native stop semantics or error-swallowing persistence. Test presence is not successful test execution or profitability.

## 8. Sweepbot / MMSM

The current `sweepbot` supersedes an earlier `lagcatcher` research path. A model supervisor allocates ranked markets into a bounded number of maker bid slots; each slot has explicit bid-live/cancel/holding/exit states, repricing thresholds, host exit/cut/time logic and event-driven accounting. Allocation preserves occupied holdings and gives young eligible bids temporary priority to avoid quote churn. Global drawdown and both-direction FX shocks trigger timed entry cooldowns, with logged start/end. [Allocation](https://github.com/mmsm1381/wallex-challenge/blob/ccd649b34d7ca1cc07948de88b91401632b97932/sweepbot/allocation.py#L47-L86), [shock state](https://github.com/mmsm1381/wallex-challenge/blob/ccd649b34d7ca1cc07948de88b91401632b97932/sweepbot/filters.py#L53-L125), [slot state machine](https://github.com/mmsm1381/wallex-challenge/blob/ccd649b34d7ca1cc07948de88b91401632b97932/sweepbot/slots.py#L236-L348).

The LLM supervisor has explicit budgets, validity windows, schema/validator and multiple jobs (planning, hold/cut, trade explanations, review/news). Hosts retain stop/flatten authority. Most of these additional roles would consume Royin's limited durable BoxAPI allocation and add no demonstrated alpha today. Float market rules and fallback empty rule maps are weaker than Royin's Decimal/min/step authority.

Critical rejected execution behavior: after POST transport/server failure it GETs the client ID, then retries POST once if lookup is absent; if still unknown it emits rejection (`no answer after one retry`). That is neither authoritative finality nor safe historical treatment. It also synthesizes a zero-fee execution delta from aggregate executedQty when fills are missing. These assumptions cannot replace Royin's UNKNOWN/fill-evidence contracts. [Submit loop](https://github.com/mmsm1381/wallex-challenge/blob/ccd649b34d7ca1cc07948de88b91401632b97932/sweepbot/wallex_broker.py#L196-L221), [fill delta fallback](https://github.com/mmsm1381/wallex-challenge/blob/ccd649b34d7ca1cc07948de88b91401632b97932/sweepbot/wallex_broker.py#L330-L398).

Tests cover risk/filters/allocation/slot/broker/provider/replay at fixture level; representative files were inspected, not executed. Transfer only event-shaped shock/cooldown visibility or quote-churn controls if later justified by an actual maker strategy. No current reason to add passive ladder slots to Royin without a delay/fill model and fresh executable proof.

## 9. Siavash / Mahdi Dehghan

This is a typed candidate → fee filter → ML score → probability/EV gate → LLM review → deterministic risk → execution pipeline, with structured rejection stages. LightGBM scoring is optional and records SKIPPED/ERROR rather than pretending inference happened. Model EV is derived from estimated probability, target, stop and round-trip fee. On scorer errors the pipeline continues without ML, so whether ML is a mandatory safety gate is a configuration/contract choice, not implied by naming it AI. [Pipeline](https://github.com/MahdiDehghan369/wallexChallenge/blob/bbd939b454ee800e91b5390c4bfb94cc44181234/src/siavash/engine/pipeline.py#L237-L376), [scorer](https://github.com/MahdiDehghan369/wallexChallenge/blob/bbd939b454ee800e91b5390c4bfb94cc44181234/src/siavash/ml/scorer.py#L30-L76).

Useful research mechanism: triple-barrier labels enter at the next candle open plus slippage, process stop before target if both occur, handle gaps at min(open,stop), impose a time stop and subtract both-side fee. Calibration/threshold selection can recommend disabling ML if filtered trades still lose or fail to beat no filter. However leave-one-fold-out calibration uses all other folds (including chronologically later ones) and a one-fold special case calibrates on itself. That is not a pure prequential chronological evaluation and requires a nested time-respecting protocol before production-probability claims. Threshold selection optimizes over many alternatives and uses an activity constraint; do not transplant a minimum trade requirement. [Labeling](https://github.com/MahdiDehghan369/wallexChallenge/blob/bbd939b454ee800e91b5390c4bfb94cc44181234/src/siavash/ml/labeling.py#L25-L59), [calibration/selection](https://github.com/MahdiDehghan369/wallexChallenge/blob/bbd939b454ee800e91b5390c4bfb94cc44181234/src/siavash/ml/threshold.py#L44-L117).

Critical rejected behavior: `SafeSubmitter` explicitly retries an unknown POST with **a new client ID** after unsuccessful lookups; even a lookup network failure is treated as not found. Its unit test explicitly expects that resubmission. Without authoritative finality, this can create duplicate orders. Royin's same-ID reconciliation and retained reserve must remain. [Submission](https://github.com/MahdiDehghan369/wallexChallenge/blob/bbd939b454ee800e91b5390c4bfb94cc44181234/src/siavash/execution/safe_submit.py#L55-L110), [fixture endorsing resend](https://github.com/MahdiDehghan369/wallexChallenge/blob/bbd939b454ee800e91b5390c4bfb94cc44181234/tests/unit/execution/test_safe_submit.py#L74-L110).

Transfer: unified economic rejection taxonomy, cost-aware causal labels, optional model deployment only after baseline lift. Defer training/model registry/SHAP/calibration to a real sufficient dataset. LLM self-confidence is not this calibrated classifier probability, and even this classifier needs temporal validation.

## 10. Mohsenn bot

This code is primarily a historical/forward simulation research engine, not a verified live exchange executor in the inspected scope. Eight deterministic scanners emit typed opportunity cards only: Bollinger/RSI dip, VWAP reclaim, session-range breakout, liquidity sweep, trend pullback, squeeze, volume spike and relative strength. Card timestamps are mapped to completed higher-timeframe bars; the pullback explicitly uses the last completed hourly trend. This is an organized way to test hypotheses separately before combining them, not evidence that eight scanners beat one. [Scanner cards and causal mapping](https://github.com/Mohsenn1378/wallex-bot-Challenge/blob/6951a3d70fee334ef350d0b842ff911d42fc4c03/wallex_agent/scanners.py#L13-L41), [families](https://github.com/Mohsenn1378/wallex-bot-Challenge/blob/6951a3d70fee334ef350d0b842ff911d42fc4c03/wallex_agent/scanners.py#L44-L138).

The LLM policy supplies bounded economic/risk plans for cards; deterministic baseline policies enable comparison. The meaningful strength is the shared fill model: next-open market pricing, spread plus slip plus stale penalty; limit fills require strict trade-through rather than mere touch; zero-trade bars cannot trigger limits/stops; gap stops fill adversely; stop wins same-bar ambiguity; quantity is stepped. Golden tests assert these exact adverse cases, including tiny partial-TP merging and both-side fees. [Fill model](https://github.com/Mohsenn1378/wallex-bot-Challenge/blob/6951a3d70fee334ef350d0b842ff911d42fc4c03/wallex_agent/sim/fill_model.py#L1-L65), [tests](https://github.com/Mohsenn1378/wallex-bot-Challenge/blob/6951a3d70fee334ef350d0b842ff911d42fc4c03/tests/test_fill_model.py#L22-L118).

Limitations: float accounting, static historical per-symbol spread assumptions, fallback last price on no-trade market fills and assumed liquidity cannot reproduce a live order book. A pessimistic label does not make all assumptions conservative under all markets. Hardcoded historical minimum 50k cannot override today's approved minimum. Adding scanner families after seeing outcomes risks multiple-testing overfit. Transfer the acceptance cases and counterfactual cost/delay sensitivity, not unproven scanner count or synthetic fills as real trading success.

## 11. Zirak

Zirak's newer agent combines explicit setup families, a supervised meta-label model and LLM risk posture. With sufficient labeled candidates it fits logistic regression or gradient boosting using a fixed seed, measures a 70/30 temporal holdout then refits all data; with too few rows it uses a smoothed per-setup prior, explicitly marked `prior`. EV and fractional-Kelly size are derived from the model probability, TP/SL and costs. This is real ML source, not just an LLM label. However a holdout AUC is not probability calibration; no calibration step exists in the inspected model. The prior is a fixed research assumption, not evidence of a calibrated chance. Kelly/EV sizing from these probabilities must not be copied into Royin. [Training](https://github.com/amirhosein3000/zirak/blob/6e9e638fca54b5bf8e55174af0bfc58b72314e95/backend/zirak/agent/model.py#L100-L178), [EV/Kelly](https://github.com/amirhosein3000/zirak/blob/6e9e638fca54b5bf8e55174af0bfc58b72314e95/backend/zirak/agent/model.py#L181-L207).

The posture agent sees bounded read-only tools for market/portfolio/recent decisions/model stats and chooses normal/cautious/avoid, allowed setup families and a multiplier capped at 1.5. Missing/failed LLM uses a distinctly labeled rules posture; replay stores the posture. Host sizing still caps free cash, position, gross and live order amount; the reported binding cap is useful. The risk denominator is stop-only in this size function; fee allowance is in the cash cap, not the stop-loss budget. [Posture](https://github.com/amirhosein3000/zirak/blob/6e9e638fca54b5bf8e55174af0bfc58b72314e95/backend/zirak/agent/posture.py#L177-L228), [sizing](https://github.com/amirhosein3000/zirak/blob/6e9e638fca54b5bf8e55174af0bfc58b72314e95/backend/zirak/agent/engine.py#L635-L774).

Live order handling has hard-limit checks and ACK latency but catches generic exchange/network errors and returns None before persistent pending tracking is established. That is insufficient to prove no order exists after an ambiguous POST. Native tests cover causal features, deterministic model save/load, prior labeling, posture tools, state survival, hard caps, stale entries, unfilled exit TTL and flatten. They were inspected, not run; synthetic learning and fixture round-trips do not prove market alpha. [Ambiguous boundary](https://github.com/amirhosein3000/zirak/blob/6e9e638fca54b5bf8e55174af0bfc58b72314e95/backend/zirak/agent/engine.py#L287-L339), [tests](https://github.com/amirhosein3000/zirak/blob/6e9e638fca54b5bf8e55174af0bfc58b72314e95/backend/tests/test_agent.py#L116-L150).

Transfer: model provenance and performance card, auditable setup and cap binding, prior/fallback separation. Defer classifier/Kelly until adequate temporally clean labels, calibration and measured baseline advantage exist. Preserve Royin's stronger unknown/persistence/Decimal gate.

## Highest-value integration proposals for Royin

### P0 — Host-computed economic dossier before the AI decision

Origin: Nova `candidate_items`, Sepehr's fee-floor/fresh dossier, Tiz exit floor. Royin already computes true executable economics after ENTER, so **reuse** those quantities for a read-only candidate view before the final model choice. At minimum expose source close/cutoff, observed fresh bid/ask and spread, entry fee/exit fee assumptions, modeled exit slippage, cost-only breakeven target relative to source close and current ask, forecast horizon and data age. Distinguish conditional target net proceeds from expected value. Do not invent a target or probability to clear a gate; keep full host recheck at POST time.

Acceptance cases: close100/ask103/source-target102.1 remains blocked; larger source-target clearing all fees passes only conditional economics; base/quote fee and step rounding agree with broker accounting; stale book/depth fails before authorization; no NaN/Infinity/float conversion in money; outputs carry the snapshot/quote binding; no change to permit/counters/historical unknown/budget; recorded replay shows whether the model actually changed its choice. An implementation that only prints numbers but never reaches the model is not this feature.

Expected practical value: removes a specific information mismatch and prevents the model reasoning about a last close as if it were today's entry price. It does **not** prove positive EV or produce a guaranteed trade. No need for new model, role, feed or allocation.

### P1 — Strategy-aligned brief and falsifiable skip reasons, preserving WAIT

Origin: Public F2 brief, Tiz judge and Mahdi reviewer prompts. Define the actual Royin hypothesis and horizon, cost burden, which current evidence supports/invalidates it, and when RSI/relative strength/volume are merely context versus required conditions. Version the brief/hash with the run. Ask for one concise evidence-bound reason, not private chain-of-thought. Keep safe diagnostic failure distinct from an actual model WAIT. Never convert unsupported WAIT to ENTER.

Acceptance: two recorded/fixed scenarios with identical trend but different spread must display the economic difference; borrowed evidence ID still rejected; invalid/missing response still fail-closed; high RSI alone is not declared universally safe or universally invalid without the chosen hypothesis; repeated wrong-family objections are counted rather than silently overridden; comparative old/new outputs use exactly the same frozen market inputs/costs; no threshold tuning on observed holdout outcomes. A prompt change is evaluated evidence, not an automatic performance claim.

### P2 — Adverse execution and delay evaluation around the same decisions

Origin: Mohsenn shared fill tests, Siavash next-bar/gap labels, Sepehr's model-age/candidate-still-valid gate, WTA partial/restart tests. Extend existing Royin replay/evaluation tools instead of adding another broker. Measure baseline cash/hold/rules/AI on equal timestamps/universe/costs; vary decision-to-entry delay and fees/spread; keep missing/no-fill/error events visible. On historical candles show explicit stop-first, strict trade-through, no-volume and gap assumptions, and do not certify these as live fills.

Acceptance: same candle touching SL/TP exits at SL; gap below SL fills at adverse open; limit touch without trade-through does not automatically fill; zero-volume bar cannot create a fill; one delayed order changes economic acceptance when price has outrun the target; duplicate fill and cancel/restart do not change PnL twice; output records residual and best-trade-excluded return. If the input lacks books or target schedule, mark execution replay unconfirmed rather than fill with synthetic certainty.

## Explicitly rejected or deferred ideas

- Swarm/debate, more provider comparisons, RL, fresh supervised training, news feeds, cross-quote arbitrage and many new scanner families: larger state/data/validation surface without current measured benefit.
- LLM confidence as probability; fractional Kelly from priors/uncalibrated classifier probabilities; positive minimum allocation for every model opinion.
- Unsupported WAIT-to-ENTER rewrite, minimum activity/trade quota, tuning a threshold merely to obtain the first order.
- POST retry after ambiguous error, new client ID after failed lookup, treating 404 as authoritative finality, zero-fee synthetic fills, swallowing write-ahead failure.
- Treating README/backtest report/fixture passing/source sophistication as proof of profit or successful live trade.

## Audit outcome and remaining proof

All 11 repositories were accessible and inspected beyond README at the pinned revision. Depth is selective critical-path verification, not an exhaustive audit of every historical experiment/UI line. The largest useful gap is **strategy/economics context presented to the model and honest causal evaluation**, not absence of another framework or risk class. Royin already has stronger durable financial intent/UNKNOWN handling and explicit funding authority than several references; keep those contracts.

This subtask made no implementation claim and no exchange/model call. It cannot attest to a real Royin fill. Parent must separately show a naturally qualified real decision → current host approval → accepted exchange order → parsed authoritative fill → reconciled balances/ledger, preserving original mission/state/history and the no-commit instruction. If no opportunity qualifies, the correct outcome is still unconfirmed execution, not a manufactured success.
