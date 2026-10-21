# رویین — موتور معاملاتی تیم ماکارونی

چالش Wallex در هکاتون Agentic AI استارکوچ؛ مالک چالش: پوریا. پژمان مسئول Liara و آیدین مسئول ترب است. این تقسیم کار تصمیم داخلی تیم است.

**وضعیت: T01، package و CLI اعتبارسنجی config ساخته و آزموده شد؛ موتور معامله، بک‌تست استراتژی و اتصال خصوصی هنوز ساخته یا تأیید نشده‌اند.** این مخزن تا پایان مسابقه Private می‌ماند. عمومی کردن بعدی فقط پس از پاک‌سازی Secret، اطلاعات حساب و لاگ‌ها انجام می‌شود.

نقطه شروع Agent، [AGENTS.md](AGENTS.md) است. برای شروع پیاده‌سازی، متن [MASTER_PROMPT.md](MASTER_PROMPT.md) را به Coding Agent بدهید.

- [صورت‌مسئله، بارم‌بندی و ابهام‌ها](docs/challenge-brief.md)
- [محدودیت اسپات/حساب و بازارهای غیرفعال](docs/market-access-policy.md)، [فهرست قابل‌خواندن برای کد](config/wallex-credit-market-policy.json)
- [شناخت محصول](project-overview.md)، [معماری و انتخاب ابزار](ARCHITECTURE.md)، [اصول طراحی](DESIGN.md)
- [کارها و وضعیت فعلی](TASKS.md)، [حافظه پروژه](memory.md)
- [برنامه ارزیابی](docs/evaluation-plan.md)، [نتایج آماده‌سازی](docs/preparation-checks.md)

دستور نصب، آزمون و ساخت wheel در AGENTS.md است. پس از نصب، `python -m royin check-config` فقط تنظیمات را بررسی می‌کند؛ خروجی `VALID_CONFIG_ONLY`، بدون شبکه و بدون معامله است. هر live فعلاً بسته است. requirements.txt وابستگی مستقیم محیط توسعه/probe و requirements.lock محیط حل‌شده است؛ package با `--no-deps` بعد از sync نصب می‌شود.

سند قدیمی `wallex_trading_agent_blueprint.md` برای ایده است؛ قرارداد API، درصدهای ریسک و ادعاهای عملکرد آن منبع حقیقت پروژه نیستند. فایل ویدئو محلی و از Git خارج است.
