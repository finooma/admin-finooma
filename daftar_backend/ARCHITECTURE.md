# دفتر دارایی — معماری بک‌اند (Flask + SQLite)

این سند طراحی بک‌اندی است که دقیقاً همان مدل داده و منطق تجاری فایل HTML فعلی
(`daftar-darayi_28.html`) را روی سرور پیاده می‌کند، تا در آینده بشود فرانت‌اند را
از `window.storage` جدا کرد و به این API وصل کرد — بدون تغییر در قوانین محاسباتی
(میانگین خرید وزنی، سود تحقق‌یافته، پله‌های سود، سیو سود، و غیره).

## پشته فنی
- **Flask** (سبک، بدون نیاز به وابستگی‌های خارجی که در این محیط در دسترس نیستند)
- **SQLite** از طریق ماژول استاندارد `sqlite3` (فایل‌محور، بدون نیاز به سرویس جدا)
- **PyJWT** برای توکن‌های ورود (بدون کوکی/سشن سمت سرور)
- **werkzeug.security** برای هش کردن رمز عبور (`generate_password_hash` / `check_password_hash`)
- بدون ORM سنگین — یک لایه‌ی نازک دسترسی به داده (`db.py`) با کوئری‌های SQL خام،
  چون مدل داده کوچک و پایدار است و ORM فقط پیچیدگی اضافه می‌کند.

## ساختار پوشه‌ها
```
daftar_backend/
  app/
    __init__.py        # create_app() — factory الگوی Flask
    config.py          # تنظیمات (مسیر دیتابیس، کلید JWT، عمر توکن)
    db.py               # اتصال sqlite، init_db()، helperهای query
    schema.sql          # DDL همه‌ی جدول‌ها
    security.py         # هش رمز، ساخت/اعتبارسنجی JWT، دکوریتورهای auth
    business.py          # منطق تجاری خالص (بدون I/O): محاسبه هولدینگ‌ها،
                          # سود تحقق‌یافته، جمع دسته‌بندی، پله‌های پیش‌فرض
    errors.py            # کلاس‌های خطای دامنه + handlerهای JSON یکنواخت
    routes/
      auth_routes.py     # /api/auth/*
      portfolios.py       # /api/portfolios*
      transactions.py     # /api/portfolios/<pid>/transactions*
      holdings.py         # /api/portfolios/<pid>/holdings, /closed
      withdrawals.py       # /api/portfolios/<pid>/withdrawals*
      prices.py            # /api/prices*
      ladders.py            # /api/portfolios/<pid>/ladders*
      secure_profit.py       # /api/portfolios/<pid>/secure-profit  (فروش + برداشت اتمیک)
      snapshots.py            # /api/portfolios/<pid>/snapshots*
      users.py                 # /api/users*  (فقط ادمین)
  run.py                       # نقطه‌ی اجرا: python run.py
  requirements.txt
  tests/
    test_business.py            # تست منطق محاسباتی خالص
    test_api.py                  # تست انتها-به-انتهای API با Flask test client
```

## مدل داده (جدول‌ها)

هر جدول تقریباً یک‌به‌یک معادل آرایه‌ی جاوااسکریپتی همنام در فرانت‌اند است.

- **users**: `id, username (unique), password_hash, display_name, role ('admin'|'user'), allowed_tabs (JSON آرایه یا NULL), created_at`
- **portfolios**: `id, name, created_at`
- **transactions**: `id, portfolio_id (FK), ts, type ('buy'|'sell'|'dividend'), date (jalali text), asset, category, qty, price, amount, location, note`
- **withdrawals**: `id, portfolio_id (FK), ts, category, date, amount, dest, note, level (nullable int), source_txn_id (FK→transactions.id, nullable — لینک به فروشی که این برداشت را ساخته)`
- **prices**: `asset (PK), price, updated_at` — قیمت روز مشترک بین همه‌ی سبدها (دقیقاً مثل `PRICES`/`PRICES_UPDATED_AT` در فرانت)
- **snapshots**: `id, portfolio_id (FK), date, total_value, total_investment, total_unrealized, total_realized, created_at` — یک رکورد فشرده به ازای هر ثبت روند
- **ladders**: `portfolio_id (FK), category, idx (0..2), threshold_pct, withdraw_pct` — کلید ترکیبی `(portfolio_id, category, idx)`؛ معادل `LADDERS[pid][cat][idx]`

نکته‌ی طراحی: بر خلاف فرانت که `LADDERS` را کامل با `DEFAULT_LADDERS` لِیزی پر می‌کند،
بک‌اند فقط ردیف‌هایی را ذخیره می‌کند که واقعاً از پیش‌فرض تغییر کرده‌اند؛
`GET /ladders` همیشه هر ۷ کتگوری پایه را برمی‌گرداند و هرکدام را که در جدول نبود
از `DEFAULT_LADDERS` پر می‌کند — دقیقاً همان رفتار `ensurePortfolioLadders`.

## منطق تجاری (`business.py`) — پیاده‌سازی وفادار به فرانت‌اند

توابع زیر مستقیماً معادل نسخه‌ی جاوااسکریپتی‌شان‌اند و از همان الگوریتم پیروی می‌کنند
(میانگین خرید وزنی، fifo نبودن، بستن لات هنگام صفر شدن موجودی، نسبت‌دهی سود سهمی هنگام فروش جزئی):

- `compute_holdings(txns) -> (holdings, closed)`
- `compute_holdings_for_portfolio(pid, as_of_date=None)`
- `compute_asset_txn_realized(name, pid)`
- `category_agg(holdings, closed=None)`
- `current_qty_for_asset(name, pid, exclude_txn_id=None)` — برای اعتبارسنجی فروش بیش از موجودی

این جداسازی عمدی است: `business.py` هیچ import ای از Flask یا sqlite ندارد، فقط
لیست/دیکشنری پایتونی می‌گیرد و برمی‌گرداند — این یعنی می‌شود آن را کاملاً مستقل
یونیت‌تست کرد (`tests/test_business.py`) بدون بالا آوردن دیتابیس یا سرور.

## احراز هویت و مجوز

- `POST /api/auth/register` — فقط وقتی هیچ کاربری در سیستم نیست (بوت‌استرپ اولین ادمین)،
  دقیقاً مثل رفتار فعلی «ثبت‌نام مدیر» در فرانت.
- `POST /api/auth/login` → `{token, user}` — JWT با claim `sub=user_id`، عمر ۷ روزه.
- هدر `Authorization: Bearer <token>` روی همه‌ی مسیرهای محافظت‌شده.
- دکوریتور `@require_auth` → کاربر جاری را در `g.user` می‌گذارد.
- دکوریتور `@require_admin` → علاوه بر auth، `role=='admin'` را اجباری می‌کند
  (معادل `requireAdmin(...)` سمت کلاینت، اما این‌بار واقعاً قابل اتکا چون سمت سرور است).
- برای کاربر غیرادمین، تب‌های مجاز از `allowed_tabs` خوانده می‌شود و مسیرهای
  GET مربوط به هر تب همان را چک می‌کنند (معادل `isTabAllowedForCurrentUser`).

## مسیرهای اصلی API

| Method | Path | توضیح |
|---|---|---|
| POST | /api/auth/register | ثبت‌نام اولین مدیر |
| POST | /api/auth/login | ورود، دریافت توکن |
| GET  | /api/auth/me | اطلاعات کاربر جاری |
| GET/POST | /api/portfolios | لیست/ایجاد سبد |
| PUT/DELETE | /api/portfolios/<id> | ویرایش/حذف سبد |
| GET/POST | /api/portfolios/<pid>/transactions | لیست/ثبت تراکنش |
| PUT/DELETE | /api/transactions/<id> | ویرایش/حذف تراکنش (حذف، برداشت لینک‌شده را هم حذف می‌کند) |
| GET | /api/portfolios/<pid>/holdings?as_of=YYYY/MM/DD | هولدینگ‌های فعلی/تاریخی |
| GET | /api/portfolios/<pid>/closed | لات‌های بسته‌شده |
| GET | /api/portfolios/<pid>/category-summary | جمع سرمایه‌گذاری/ارزش/سود هر کتگوری |
| GET/POST | /api/portfolios/<pid>/withdrawals | لیست/ثبت برداشت دستی |
| DELETE | /api/withdrawals/<id> | حذف برداشت |
| GET/PUT | /api/prices | خواندن/به‌روزرسانی قیمت روز (مشترک بین سبدها) |
| GET/PUT | /api/portfolios/<pid>/ladders/<cat> | خواندن/تنظیم پله‌های یک کتگوری |
| POST | /api/portfolios/<pid>/secure-profit | 🔒 سیو سود: فروش واقعی + برداشت لینک‌شده، اتمیک |
| GET/POST | /api/portfolios/<pid>/snapshots | ثبت/خواندن نقطه‌ی روند عملکرد |
| GET/POST/PUT/DELETE | /api/users | مدیریت کاربران (فقط ادمین) |

## نکات مهم پیاده‌سازی

1. **اتمیک بودن سیو سود**: مسیر `secure-profit` هم تراکنش فروش و هم برداشت را
   در یک تراکنش دیتابیسی (`BEGIN ... COMMIT`) می‌نویسد؛ اگر یکی شکست بخورد،
   هیچ‌کدام ثبت نمی‌شود — چیزی که در فرانت به دلیل نبود دیتابیس واقعی تضمین‌شدنی نبود.
2. **حذف تراکنش لینک‌شده**: حذف یک تراکنش فروش که یک `withdrawals.source_txn_id`
   به آن اشاره دارد، آن برداشت را هم حذف می‌کند (پیام هشدار مشابه فرانت).
3. **جداسازی سبدها**: تمام محاسبات per-portfolio هستند؛ نمای «همه‌ی سبدها»
   در بک‌اند هم مثل فرانت، هر سبد را جدا محاسبه کرده و فقط نتیجه را merge می‌کند
   (هرگز خرید/فروش دو سبد را در یک miانگین قیمت مخلوط نمی‌کند).
4. **قیمت‌ها مشترک، تاریخچه ندارند**: جدول `prices` per-asset است، نه per-portfolio
   و نه per-date — دقیقاً مثل فرانت؛ نمای `as_of` تاریخی فقط تعداد/سود تحقق‌یافته
   را بازپخش می‌کند، نه قیمت آن روز را.
