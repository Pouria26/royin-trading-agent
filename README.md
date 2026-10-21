# رویین — موتور معاملاتی هوشمند برای چالش والکس

موتور معاملاتی خودکار و عامل‌محور (Agentic AI) برای بازار رمزارز صرافی والکس در چارچوب چالش هکاتون Agentic AI استارکوچ.

**وضعیت جاری: ارزیاب تاریخی و حسابداری با regression اصلاح شده‌اند؛ نتیجه نامزد `INSUFFICIENT_EVIDENCE` است. دریافت تازه `BLOCKED_DATA` شد و هیچ پنجره کامل پذیرفته‌شده برای validation/holdout نداد. baselineهای بدون AI، شبیه‌سازی اجرا و smoke مدل، شواهد متفاوت‌اند؛ سود پایدار یا آمادگی Shadow واقعی/Live تأیید نشده است. اجرای زنده همچنان fail-closed است. [نتیجه و محدودیت‌ها](docs/historical-validation.md).**

نقطه شروع توسعه و راهنمای قوانین و گیت‌ها در [AGENTS.md](AGENTS.md) مستند شده است.

## مستندات کلیدی پروژه

- [صورت‌مسئله، بارم‌بندی و الزامات داوری](docs/challenge-brief.md)
- [محدودیت‌های بازار اسپات و سیاست دسترسی حساب](docs/market-access-policy.md)
- [شناخت محصول و دامنه نیازمندی‌ها](project-overview.md)
- [معماری سیستم و انتخاب ابزارها](ARCHITECTURE.md)
- [اصول طراحی سیستم](DESIGN.md)
- [پیگیری وظایف و وضعیت گام‌ها](TASKS.md)
- [حافظه پایدار پروژه و تصمیمات فنی](memory.md)
- [برنامه جامع ارزیابی و اعتبارسنجی](docs/evaluation-plan.md)
- [گزارش کیفیت داده‌های بازار](research/t02-data-contract.json)
- [پالیسی و سقف بودجه مدل BoxAPI](docs/boxapi-budget.md)
- [راه‌اندازی و آزمون فقط‌خواندنی حساب والکس](docs/wallex-read-only-setup.md)

## دستورهای اجرایی اصلی

برای اعتبارسنجی تنظیمات و محیط:
```powershell
.\.venv\Scripts\python.exe -m royin check-config
```

برای اجرای تست‌های رگرسیون و آزمون‌های واحد:
```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

برای اجرای سوئیت ارزیابی و جدول مقایسه استراتژی‌ها (Evaluation Scorecard):
```powershell
.\.venv\Scripts\python.exe -X utf8 scripts\run_eval.py --all
```

برای پروب فقط‌خواندنی حساب اعتباری والکس:
```powershell
.\.venv\Scripts\python.exe -X utf8 -m scripts.probe_wallex_account --run
```
