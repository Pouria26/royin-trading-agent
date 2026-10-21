# رویین — موتور معاملاتی تیم ماکارونی

چالش Wallex در هکاتون Agentic AI استارکوچ؛ مالک چالش: پوریا. پژمان مسئول Liara و آیدین مسئول ترب است. این تقسیم کار تصمیم داخلی تیم است.

**وضعیت: مدل فعال BoxAPI/Luna6، بودجه پایدار و ۵۹ تست پاس؛ چهار سناریوی واقعی مدل موفق‌اند. کیفیت جامع داده DEGRADED و فهرست حساب فرعی والکس فعلاً خالی است؛ موتور معامله و بک‌تست استراتژی هنوز وجود ندارند.** فعلاً معامله/فعال‌سازی اعتبار مجاز نیست. این مخزن تا پایان مسابقه Private می‌ماند.

نقطه شروع Agent، [AGENTS.md](AGENTS.md) است. MASTER_PROMPT.md فایل شخصی محلی و ignored است؛ در clone مخزن تحویل داده نمی‌شود.

- [صورت‌مسئله، بارم‌بندی و ابهام‌ها](docs/challenge-brief.md)
- [محدودیت اسپات/حساب و بازارهای غیرفعال](docs/market-access-policy.md)، [فهرست قابل‌خواندن برای کد](config/wallex-credit-market-policy.json)
- [شناخت محصول](project-overview.md)، [معماری و انتخاب ابزار](ARCHITECTURE.md)، [اصول طراحی](DESIGN.md)
- [کارها و وضعیت فعلی](TASKS.md)، [حافظه پروژه](memory.md)
- [برنامه ارزیابی](docs/evaluation-plan.md)، [نتایج آماده‌سازی](docs/preparation-checks.md)
- [بررسی منابع ارسالی و کاربردهای انتخاب‌شده](docs/source-review.md)، [کیفیت داده T02](research/t02-data-contract.json)
- [مقایسه مدل و بودجه BoxAPI](docs/boxapi-budget.md)، [شناسه حساب اعتباری و تست خواندنی](docs/wallex-read-only-setup.md)

دستور نصب، آزمون و ساخت wheel در AGENTS.md است. پس از نصب، `python -m royin check-config` فقط تنظیمات را بررسی می‌کند؛ خروجی `VALID_CONFIG_ONLY`، بدون شبکه و بدون معامله است. هر live فعلاً بسته است. requirements.txt وابستگی مستقیم محیط توسعه/probe و requirements.lock محیط حل‌شده است؛ package با `--no-deps` بعد از sync نصب می‌شود.

سند قدیمی `wallex_trading_agent_blueprint.md` برای ایده است؛ قرارداد API، درصدهای ریسک و ادعاهای عملکرد آن منبع حقیقت پروژه نیستند. فایل ویدئو محلی و از Git خارج است.
