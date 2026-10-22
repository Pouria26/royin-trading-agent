# سنجش پیش‌بینی‌های ثبت‌شده

پیش‌بینی قیمت، معاملهٔ اجراشده نیست. این مسیر تنها GET عمومی دارد و state مالی canary را تغییر نمی‌دهد؛ نتیجه، پذیرش استراتژی یا کالیبراسیون مدل نیست.

## قرارداد

`score_market_forecast` manifestهای `CURRENT_PAPER / REAL_MODEL` را بررسی می‌کند: hash snapshot/batch، پاسخ نهایی واقعی provider در برابر forecast میزبان، symbol، cutoff، horizon و شواهد، و صدور پیش از outcome. کپی پاسخ در run تازه نباید نمونهٔ جدید بسازد. تطابق trace، امضای مستقل provider نیست.

Outcome از close دقیقه‌ای با آغاز دقیق `cutoff + horizon - 60` خوانده می‌شود؛ تا پایان horizon به‌علاوه ۶۰ ثانیه منتظر می‌ماند. قرارداد آغاز کندل هنوز فرض تشخیصی است. نتیجهٔ نارس، مفقود یا cadence نامعتبر به pass تبدیل نمی‌شود. interpolation و استفاده از قیمت stale مجاز نیست. سقف ۳۲ GET، بدون retry و بدون مدل پولی است.

```powershell
.\.venv\Scripts\python.exe -X utf8 -m scripts.score_market_forecast --help
```

برای سنجش از `--paper-manifest <manifest-path> --score` استفاده کنید؛ چند manifest هم پذیرفته می‌شود. مسیر باید به شواهد موجود همان اجرا اشاره کند؛ rawها در clone تازه نیستند. هر ارزیابی مسیر خروجی و hash تازه دارد و source manifest را overwrite نمی‌کند. `pending` و `missing` را جدا گزارش کنید.

## شواهد فعلی و محدودیت

- دو پیش‌بینی اولیهٔ USOON/PUMP: مدل روی median absolute error از baseline بدون تغییر ضعیف‌تر بود؛ یکی جهت اشتباه داشت.
- سه پیش‌بینی بعدی USOON نیز مثبت بودند ولی terminal return واقعی منفی شد؛ baseline بدون تغییر نزدیک‌تر بود. این‌ها تصمیم WAIT بودند، نه fill یا زیان محقق‌شدهٔ حساب.
- برخی افق‌های ده‌ساعته هنوز موعد نرسیده بودند؛ تعداد pending با ساعت ارزیابی تغییر می‌کند. نتایج متفاوت source/prompt را مقایسهٔ کنترل‌شده ننامید.
- بازهٔ عریض q10..q90 و چند outcome پوشش‌داده‌شده، کالیبراسیون ۸۰٪ را ثابت نمی‌کند. میانگین/میانهٔ terminal forecast نیز expected payoff یک معاملهٔ دارای trailing نیست.
- baseline صفر فقط point forecast است؛ interval آن از همین outcomes fit نمی‌شود. بدون development interval مستقل، معیار interval آن BLOCKED است.
- مشاهدات یک جلسه هم‌بسته‌اند؛ نرخ برد استراتژی یا مزیت AI با چند پیش‌بینی اثبات نمی‌شود. پاسخ یا reason منطقی جای مقایسهٔ portfolio با اجرای یکسان را نمی‌گیرد.

برای replay داوری باید source، capture و پاسخ مجاز و پاک‌سازی‌شده فراهم شود. موجود بودن hash در Git بدون raw مجاز، اجرای کامل داوری از clone را ثابت نمی‌کند. وضعیت آزمایش فعال و موعد بعدی در [current-market-readiness](current-market-readiness.md) است.
