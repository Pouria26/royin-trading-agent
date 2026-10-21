# اتصال MCP والکس

**S، ۲۰۲۶-۱۰-۲۱:** [endpoint ارسالی کاربر](https://api.wallex.ir/mcp) بدون کلید به initialize و tools/list پاسخ HTTP 200 داد: protocolVersion=2024-11-05، serverInfo=api.wallex.ir/1.0.0، تعداد ۵۲ ابزار. فراخوان واقعی wallex_basic_get_markets نیز HTTP 200، بدون خطای JSON-RPC و isError=false، با result.markets بود. این آزمون کیفیت داده را ثابت نمی‌کند. [شاهد sanitized](evidence/wallex-mcp-2026-10-21.json)؛ catalog کامل در data/wallex-mcp-tools.json محلی و ignored است.

**D:** در `C:\Users\Pouria\.codex\config.toml` اتصال Streamable HTTP با نام wallex ثبت شد. مطابق [تنظیمات رسمی Codex](https://developers.openai.com/codex/mcp)، enabled_tools تنها این پنج ابزار عمومی را در اختیار Codex قرار می‌دهد:

- wallex_basic_get_markets
- wallex_spot_get_markets
- wallex_basic_get_market_depth
- wallex_basic_get_latest_trades
- wallex_basic_candle_history

هیچ کلید یا هدر خصوصی به MCP داده نشده است. ابزارهای حساب اصلی، سفارش/لغو، انتقال، فعال‌سازی اعتبار، کیف پول و مارجین در allowlist نیستند. catalog عمومی مجوز معامله نیست؛ سیاست بازار پروژه لازم‌الاجراست. ابزار جدید سرور خودکار مجاز نمی‌شود. تنظیمات قبلی Codex حفظ و TOML با assert بررسی شد؛ `codex mcp get wallex` اتصال فعال و همین پنج ابزار را تأیید کرد. تنظیم محلی و خارج از مخزن است.

برای مشاهده ابزارها نشست تازه Codex باز کنید؛ اگر ظاهر نشد برنامه را بازگشایی کنید. بارگذاری ابزار در نشست تازه هنوز بررسی نشده است. راستی‌آزمایی تنظیم:

```powershell
codex mcp get wallex
```

**D/U برای رویین:** اتصال بالا ابزار توسعه Codex است؛ Agent معاملاتی BoxAPI متصل نشده است. MCP قرارداد دسترسی است و بهبود دقت یا سود از آن نتیجه نمی‌شود. snapshot دارای cutoff و REST قطعی اجرا حفظ می‌شوند. افزودن MCP به موتور فقط پس از نیاز مشخص و مقایسه همان داده/هزینه/تأخیر با REST توجیه دارد؛ ابزار خام مالی به مدل داده نمی‌شود. قرارداد احراز هویت MCP و انتخاب حساب اعتباری آزموده نشده و fallback به اصلی ممنوع است.

هیچ درخواست مدل پولی، خریدوفروش یا فعال‌سازی اعتبار انجام نشد. چهار ابزار عمومی دیگر فقط از روی schema بررسی شدند و هنوز tools/call نشده‌اند؛ آزمون سودآوری و تمامیت داده خارج از این مرحله است.
