# رویین — موتور معاملاتی هوشمند برای چالش والکس

موتور معاملاتی خودکار و عامل‌محور (Agentic AI) برای بازار رمزارز صرافی والکس در چارچوب چالش هکاتون Agentic AI استارکوچ.

**وضعیت جاری: ۶۲۳ کندل native ساعتی در دو قطعه، صرفاً برای تشخیص و پژوهش پذیرفته شده‌اند؛ یک ساعت مفقود حفظ شده است. شش تنظیم روی هفت پنجره ۷۲ساعته بررسی شدند؛ نتیجه همچنان `INSUFFICIENT_EVIDENCE` و بدون نامزد منتخب است. پایش عمومی یک snapshot بسته را ثبت کرده، اما Shadow استراتژی و Live بسته‌اند. نقش افزوده مالی AI و Holdout مستقل تأیید نشده‌اند. [نتیجه و محدودیت‌ها](docs/candidate-evaluation.md).**

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
- [قرارداد و ابهام‌های منبع کندل ساعتی](docs/market-data-semantics.md)
- [ارزیابی نامزدها و راهنمای پایش فقط‌خواندنی](docs/candidate-evaluation.md)
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

برای یک چرخه پایش عمومیِ ساعتی، بدون مدل یا سفارش:

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts\run_shadow.py --mode OBSERVE_ONLY --cycles 1 --interval 3600 --max-attempts 1
```

این فرمان GET عمومی مصرف می‌کند. `COMPLETE` فقط تکمیل مشاهده درخواستی است؛ `PARTIAL` با exit 2 یعنی مشاهده کامل نشده است. مسیر `CANDIDATE_SHADOW` قبل از شبکه رد می‌شود. داده خام پژوهش ignored است؛ بازپخش دقیق در کلون تازه نیازمند بسته داده همراه تحویل است.


Latest execution review: [readiness and evidence limits](docs/execution-readiness-review.md). The order adapter is an offline contract harness; production orders and Candidate Shadow remain blocked. Twelve fixed AI snapshots are not proof of profitable trading.
