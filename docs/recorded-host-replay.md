# بازپخش آفلاین تصمیم و حسابداری

این مسیر `RECORDED_HOST_REPLAY` است: پاسخ قبلی مدل از validator/binder میزبان عبور می‌کند و journal همان حساب کاغذی با Ledger مشترک PaperBroker بازپخش می‌شود. هیچ استنتاج تازه، HTTP، رزرو بودجه یا سفارش واقعی ندارد. سود بازپخش، سود حساب مسابقه نیست.

## ورودی و اجرا

ورودی، snapshot ثابت manifest اصلی `CURRENT_PAPER / REAL_MODEL` همراه rawهای عمومی ارجاع‌شده است. hash پیش از بررسی ثبت شود؛ فایل فعال را هنگام نوشتن ندهید. خروجی باید تازه و خارج از پوشهٔ اجرای اصلی باشد.

```powershell
$manifestPath = 'artifacts/forecast-input-snapshots/RECEIVED-RUN/manifest.json'
$manifestHash = (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
.\.venv\Scripts\python.exe -X utf8 -m scripts.replay_market_paper --paper-manifest $manifestPath --manifest-sha256 $manifestHash --output-dir artifacts/host-replay/REVIEW-1
```

`--bundle` manifest بدون تغییر و rawهای عمومی را زیر `source/` خروجی قرار می‌دهد. فقط چهار endpoint collector مجازند؛ DB مالی/بودجه، `.env` و فایل دلخواه بسته‌بندی نمی‌شوند. credentialهای شناخته‌شده رد می‌شوند؛ این اسکن تضمین ناشناس‌سازی کامل نیست و پیش از اشتراک خارجی بازبینی انسانی لازم است. فرمان هیچ فایل را منتشر یا وارد Git نمی‌کند.

## شواهد و محدودیت

- hash manifest/raw، نماد، snapshot/batch، prompt ضبط‌شده، دو درخواست/پاسخ، ابزار خواندنی و tool-call ID/result و `final_result` تطبیق داده می‌شوند. زمان صدور forecast پیش از outcome از checker موجود بررسی می‌شود.
- قرارداد role، evidence و binder بازاجرا می‌شوند؛ `host_input_state` ماندهٔ همان arm را به offset دقیق journal متصل می‌کند. پاسخ روی cash/position یک arm دیگر استفاده نمی‌شود.
- journal نسخهٔ۱ شامل INTENT با reserve/واحدها، FILL و CANCEL مرتب است. رزرو، partial fill، fee در base/quote، لغو و fill تکراری با مانده و realized PnL اصلی تطبیق می‌شوند.
- `PASS_RECORDED_HOST_REPLAY` فقط پذیرش تصمیم/حسابداری ثبت‌شده است. `PARTIAL_RECORDED_HOST_REPLAY` و exit1 یعنی context/journal اصلی ناقص است؛ داده حدس زده نمی‌شود. ورودی ناسازگار `BLOCKED_REPLAY_INPUT` و exit2 است.
- هم‌زمانی ساعت، شکست GET، monitor، صف و fill بازار کاملاً بازسازی نمی‌شوند؛ `execution_replay=EXECUTION_REPLAY_UNCONFIRMED` باقی می‌ماند. hash امضای مستقل provider نیست. replayer revision و original bindings جدا ثبت می‌شوند.
- scorer خروجی replay را forecast مستقل تازه نمی‌پذیرد. سنجش موعدها فقط روی اصل ثابت با `scripts.score_market_forecast --paper-manifest ... --score` ادامه دارد؛ اصل فایل overwrite نمی‌شود.

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_recorded_host_replay tests.test_continuation_safety -v
```

این تست‌ها transcript مصنوعی و oracle دستی‌اند؛ کیفیت AI واقعی را ثابت نمی‌کنند. [قرارداد سنجش](current-forecast-evaluation.md) و [قرارداد ارزیابی](evaluation-plan.md) مرجع‌اند.
