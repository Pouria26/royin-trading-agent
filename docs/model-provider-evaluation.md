# مقایسهٔ ارائه‌دهندگان مدل — ۲۳ اکتبر ۲۰۲۶

کاربر آزمایش Devora، Dahl، River، APMix و Codecraft را مجاز کرده و هزینه را از معیار انتخاب کنار گذاشته است. این هدایت، محدودیت تاریخی BoxAPI-only را برای این آزمایش‌ها supersede می‌کند. مجوز مدل، مجوز سفارش یا استفاده از کیف پول نیست؛ BUY_UNKNOWN، reserve، intent و هشت attempt قبلی محفوظ‌اند.

## اتصال و مالکیت مصرف

`RuntimeConfig` مدل، origin دقیق HTTPS و SecretStr همان ارائه‌دهنده را به هم متصل می‌کند. URL دلخواه، مدل خارج از کاتالوگ تأییدشده، fallback خودکار به حساب دیگر و فعال‌سازی live پذیرفته نیست. مدل فقط context عمومی و ابزار خواندنی محدود را می‌بیند.

| ارائه‌دهنده | origin مجاز | متغیر کلید محلی | state مصرف |
|---|---|---|---|
| BoxAPI | `https://ai.boxapi.ir/ai/v1` | `BOXAPI_API_KEY` | `data/llm-budget.sqlite3` اصلی |
| Devora | `https://api.devora.my.id/v1` | `DEVORA_API_KEY` | `data/devora-model-usage.sqlite3` |
| Dahl | `https://inference.dahl.global/v1` | `DAHL_API_KEY` | `data/dahl-model-usage.sqlite3` |
| River | `https://api.river.ai/v1` | `RIVER_API_KEY` | `data/river-model-usage.sqlite3` |
| APMix | `https://api.apmix.ai/v1` | `APMIX_API_KEY` | `data/apmix-model-usage.sqlite3` |
| Codecraft | `https://codecraftapi.com/v1` | `CODECRAFT_API_KEY` | `data/codecraft-model-usage.sqlite3` |

state جدید ارائه‌دهندگان فقط با `ModelBudget.initialize_provider_state(config, path)` یک بار ایجاد می‌شود. این روش برای BoxAPI ممنوع است. فایل موجود جایگزین نمی‌شود؛ ادامه با فایل غایب/خراب، کلید یا provider متفاوت و مدل ناسازگار مسدود است. سقف token ثبت‌شده با restart افزایش پیدا نمی‌کند. مصرف قبلی یا timeout خودکار refund نمی‌شود. این قرارداد برای جلوگیری از آزمایش تکراری/بی‌حد و ثبت شواهد است؛ هزینه در رتبه‌بندی دخیل نیست.

رزروهای خارجی `UNPRICED_USER_AUTHORIZED` هستند؛ `reserved_cost_usd=null` است و نرخ صفر داخلی ادعای رایگان‌بودن یا invoice نیست. tokenهای رزروشده، usage پاسخ و ماندهٔ پنل سه مشاهدهٔ متفاوت‌اند. ledger و سقف‌های USD قبلی BoxAPI تغییر نکرده‌اند. تخصیص یک‌بارهٔ پنج میلیون token رایگان Dahl به همان کلید، از مخزن حساب انجام و readback شد؛ این انتقال خرید اعتبار نبود و به معنی موفقیت inference نیست.

## سازگاری پروتکل

موتور از SDK نصب‌شده و Chat Completions استفاده می‌کند. origin و مدل‌های مجاز از GET کاتالوگ و مستندات ارائه‌دهنده استخراج شده‌اند؛ شناسهٔ اعلام‌شده، اثبات مستقل هویت backend نیست.

در [River](https://docs.river.ai/guides/inference-controls/)، DeepSeek با `reasoning_effort=none` و GLM با `low` استفاده می‌شود. GLM reasoning اجباری دارد. [APMix](https://apmix.ai/docs) و [Codecraft](https://codecraftapi.com/docs/chat-completions) مسیر OpenAI-compatible را مستند کرده‌اند؛ مسیر کاربر با همین اتصال موجود آزموده می‌شود. max_tokens خارجی ۸۱۹۲ است و reasoning لازم برای ادامهٔ tool طبق profile حفظ می‌شود؛ نسخهٔ BoxAPI همان تنظیم قدیمی را دارد.

ابزارها مرحله‌بندی می‌شوند: درخواست اول فقط `read_market_snapshot` را می‌بیند؛ پس از خواندن موفق، درخواست دوم فقط `final_result` را می‌بیند. این کار امکان final پیش از خواندن یا read+final هم‌زمان را از schema حذف می‌کند. محدودیت یک ابزار، دو HTTP، validation دامنه، evidence و سیاست ریسک حفظ می‌شوند. ساختار معتبر به معنی تصمیم سودآور نیست.

## پروتکل ثابت مقایسه

`scripts.compare_model_providers` بدون .env، کلید والکس، HTTP صرافی یا سفارش اجرا می‌شود. `--run` صریح، packet عمومی hash‌شده، credential file محلی و state اصلی هر ارائه‌دهنده لازم‌اند. BoxAPI نیز فقط به‌عنوان baseline با ledger و سقف USD اصلی پذیرفته می‌شود. بدون `--run` حتی فایل کلید یا DB خوانده نمی‌شود. نتایج زیر `artifacts/model-comparison/` ignored هستند؛ source، packet و حداکثر درخواست‌ها پیش از شروع ثبت می‌شوند و تغییر source انتخاب را مسدود می‌کند.

packet ثابت `fixed-cases-20261023-1/cases.json` با SHA256 زیر، چهار ورودی ورودِ ثبت‌شده و دو موقعیت فرضی دارد:

`97f7b4bff427c59007069427d5dc0c7de690e4dfe164a1574709f7262f44c9c6`

هر گزینه دقیقاً همان شش ورودی را با یک read، حداکثر دو HTTP، deadline سی ثانیه و بدون retry دریافت می‌کند. concurrency دو است. نتیجهٔ هر case پیش از درخواست claim و مستقل ذخیره می‌شود. اجرای ناقص خودکار از سر گرفته نمی‌شود؛ برای آزمایش بعدی run ID جدید لازم است.

معیار عملیاتی از پیش ثبت‌شده: تمام caseها در هر دو نقش باید از validator میزبان عبور کنند؛ میان واجدان، median زمان معتبر کمتر مقدم است. هزینه در رتبه‌بندی نیست. خروجی `OPERATIONAL_CANDIDATE_ONLY` فقط نامزد اجرای موتور است؛ `NO_QUALIFIED_MODEL` هم نتیجهٔ معتبر آزمایش است. timeout و HTTP 5xx کیفیت استدلال را اندازه نمی‌گیرند و جدا گزارش می‌شوند.

این آزمون انتخاب کل بازار، پیش‌بینی prospective، برتری نسبت به baseline معاملاتی یا PnL را نمی‌سنجد. ورودی‌های هم‌بسته/تاریخی holdout مستقل نیستند. پس از صلاحیت عملیاتی، کیفیت پیش‌بینی و نتیجهٔ paper باید جدا و با ورودی، هزینه و اجرای مشترک سنجیده شوند؛ از سرعت به سود استنتاج نمی‌شود.

## نتیجه‌های مشاهده‌شده

- capability کوچک: Devora Flash در۶۰٫۴۸۵ثانیه، Devora GLM در۳۱٫۹۵۳ثانیه و Dahl MiniMax در۱۲٫۱۴۱ثانیه یک tool smoke را تکمیل کردند. این اعداد معیار latency نقش کامل نیستند. Pro و GLM5.2 در Devora پاسخ۴۰۲ دادند؛ Dahl GLM/DeepSeek خطای availability داشتند.
- `provider-roles-20261023-1`: پنج مدل × شش case، هیچ تصمیم معتبر نهایی؛ MiniMax علاوه بر availability، توالی ابزار نامعتبر داشت. نتیجه و شکست‌ها حفظ شدند.
- `provider-roles-20261023-2`: پس از اصلاح مرحله‌بندی ابزار، همان پنج مدل/شش case همچنان صفر تصمیم معتبر داشتند؛ MiniMax پنج HTTP failure و یک fallback غیرHTTP، Dahl GLM و DeepSeek هرکدام شش HTTP failure، دو مدل Devora هرکدام شش timeout. نتیجه `NO_QUALIFIED_MODEL` است؛ MiniMax برندهٔ نهایی انتخاب نشده است.
- **تصحیح روش آزمون:** در runs1..3، Entry از مسیر قدیمی single-snapshot فراخوانی شده بود؛ این مسیر forecast ورود را نمی‌پذیرد. در run3 پاسخ واقعی نشان داد که رد `Only the reviewer may attach a forecast on the single-snapshot path` ناشی از اتصال نادرست harness است. این بخش از ردها شاهد ضعف مدل نیست؛ اصل artifact حفظ شده و ارزیابی عملیاتی معتبر با مسیر batch و run جدید تکرار شد. regression پیش از اصلاح به‌دلیل نبود dispatch درست شکست خورد؛ validator مالی تغییر نکرد.
- `provider-roles-20261023-3`: سه مدل River، یک APMix و شش مدل Codecraft؛ هر دو DeepSeek و APMix در دو Position Reviewer موفق شدند، اما Entryهای این run به علت بالا مبنای رتبه‌بندی نیستند. هر شش Codecraft در هر شش case پاسخ۴۰۲ با `insufficient_quota / Billing verification failed` دادند. درخواست مستقل ساده و بدون tool نیز همان۴۰۲ داد؛ علت حساب/بالادست و ماندهٔ واقعی تأیید نشده است. کاتالوگ۲۰۰ و تبلیغ Free این خطا را رفع نمی‌کنند؛ هیچ ارتقای پولی انجام نشد.
- `provider-roles-20261023-4`: قرارداد صحیح batch، همان packet، BoxAPI baseline و چهار گزینهٔ River/APMix. GPT-6-luna و APMix Claude Sonnet4.6 هر دو۶از۶ معتبر شدند؛ median۸٫۶۷۲ و۲۱٫۹۹۲۵ثانیه. River1017 سه، River Flash دو و GLM صفر تصمیم معتبر داشتند؛ همهٔ خطاها و timeoutها حفظ‌اند. انتخاب قاعدهٔ عملیاتی `boxapi:gpt-6-luna` است؛ دلیل، صحت قرارداد و latency مشاهده‌شده است، نه هزینه یا سود اثبات‌شده.
- `provider-finalists-20261023-1`: تکرار دو بار همان شش ورودی؛ هر دو نامزد۱۲/۱۲ معتبر، median GPT۷٫۹۸۴۵ وClaude۲۱٫۱۸ثانیه. انتخاب عملیاتی GPT-6-luna تأیید و default فعلی حفظ شد؛ APMix نامزد واجد شرایط ارزیابی بعدی است و fallback خودکار نیست. تکرار ورودی، نمونهٔ مستقل یا holdout تازه نمی‌سازد. source مشترک این دو مقایسه `ed673294cfef2a16253717135af8d6ace4367a59da54d256b0818fc8d06bc3e6` است.

بازتولید آفلاین از `replay_market_paper` همچنان forecast تازه نمی‌سازد. replay/scorer علاوه بر نام provider، تطابق مدل با کاتالوگ همان provider را بررسی می‌کنند؛ export الگوهای کلیدهای تازه را نیز رد می‌کند. fixtureهای مصنوعی و آزمون واحد، شاهد provider واقعی محسوب نمی‌شوند.
