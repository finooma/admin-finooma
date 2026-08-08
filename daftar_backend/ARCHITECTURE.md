# دفتر دارایی — معماری بک‌اند (Flask + SQLite)

این سند طراحی بک‌اندی است که دقیقاً همان مدل داده و منطق تجاری فایل HTML فعلی
(`daftar-darayi_28.html`) را روی سرور پیاده می‌کند، تا در آینده بشود فرانت‌اند را
از `window.storage` جدا کرد و به این API وصل کرد — بدون تغییر در قوانین محاسباتی
(میانگین خرید وزنی، سود تحقق‌یافته، پله‌های سود، سیو سود، و غیره).

## نسخه‌ی دوم (v2) — الهام از Microsoft Money

سه تغییر ساختاری اصلی نسبت به نسخه‌ی اول، هر سه در سطح دیتابیس و منطق تجاری،
نه فقط UI:

1. **کتگوری‌ها یک موجودیت مدیریت‌شده شدند.** قبلاً هر تراکنش یک رشته‌ی متنی آزاد
   برای کتگوری داشت. حالا جدول `categories` وجود دارد؛ هر تراکنش/برداشت/پله‌ی سود
   به `category_id` اشاره می‌کند، نه به نام. یعنی از یک‌جا می‌شود کتگوری ساخت،
   **rename** کرد (و همه‌جا آنی اعمال می‌شود، چون فقط id ذخیره شده نه نام)، یا
   حذف کرد (فقط اگر هیچ تراکنشی از آن استفاده نکند). ۷ کتگوری پایه در اولین اجرا
   خودکار seed می‌شوند (`db.py: _seed_default_categories`).

2. **حساب‌های نقدی (cash accounts)، دقیقاً به سبک Microsoft Money.** هر سبد
   می‌تواند چند حساب نقدی داشته باشد (مثلاً «نقد تومانی»، «حساب بانک x»). خرید یک
   دارایی، حساب انتخابی را بدهکار می‌کند (به‌اندازه‌ی مبلغ + کارمزد)؛ فروش یا سود
   نقدی، همان حساب را بستانکار می‌کند. واریز/برداشت/انتقال بین حساب‌ها هم مستقیماً
   از همان تب قابل ثبت است. موجودی هیچ‌وقت ذخیره نمی‌شود — همیشه از پخش کامل
   دفترکل (opening_balance + هر واریز/برداشت/انتقال + هر تراکنشی که account_id آن
   را هدف گرفته) محاسبه می‌شود؛ همان فلسفه‌ی «replay the ledger» که هولدینگ‌ها از
   قبل داشتند (`business.py: compute_account_balance`). انتخاب حساب برای هر
   تراکنش اختیاری است (`account_id` می‌تواند NULL باشد) — برای کسی که نمی‌خواهد
   نقدینگی را دقیق دنبال کند.

3. **فیلد کارمزد (fee) روی هر تراکنش.** در خرید، کارمزد به مبلغ کل اضافه و بخشی
   از cost basis می‌شود (خرید ۱۰۰ با کارمزد ۲ یعنی هزینه‌ی واقعی ۱۰۲). در فروش،
   کارمزد از مبلغ کم می‌شود و سود واقعی/نقد واریزی را کاهش می‌دهد (فروش ۱۰۰ با
   کارمزد ۲ یعنی خالص دریافتی ۹۸). این منطق در `business.py` (`txn_cash_impact` و
   داخل `compute_holdings`) پیاده شده، نه فقط در UI — یعنی هر مصرف‌کننده‌ی API
   (نه فقط این فرانت‌اند) به همین قانون پایبند می‌ماند.

**نکته‌ی مهم درباره‌ی فرانت‌اند:** این سه تغییر فعلاً فقط در بک‌اند (schema.sql +
business.py + routes/) پیاده و تست شده‌اند. فایل `frontend/daftar-darayi.html`
هنوز به API قدیمی (category متنی، بدون fee، بدون accounts) وصل است و باید در یک
مرحله‌ی بعدی به‌روزرسانی شود — فیلد کارمزد و انتخاب کتگوری/حساب باید در فرم ثبت
تراکنش اضافه شوند، و یک تب جدید «کتگوری‌ها» و «حساب‌ها» ساخته شود.

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
      categories.py             # /api/categories*  (v2: کتگوری‌های مدیریت‌شده)
      accounts.py                # /api/portfolios/<pid>/accounts*, /api/accounts/<id>/*  (v2: حساب‌های نقدی)
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
- **categories** *(v2)*: `id, name (unique), is_default, created_at` — ۷ تای پایه در اولین اجرا seed می‌شوند؛ قابل rename/حذف (اگر استفاده نشده باشند)
- **accounts** *(v2)*: `id, portfolio_id (FK), name, opening_balance, created_at` — حساب‌های نقدی هر سبد؛ موجودی ذخیره نمی‌شود، همیشه محاسبه می‌شود (`compute_account_balance`)
- **cash_movements** *(v2)*: `id, account_id (FK), ts, type ('deposit'|'withdraw'|'transfer_in'|'transfer_out'), date, amount, note, transfer_group_id` — واریز/برداشت/انتقال دستی؛ خرید/فروش/سود نقدی مستقیماً از طریق `transactions.account_id` روی موجودی اثر می‌گذارند، نه از این جدول
- **transactions**: `id, portfolio_id (FK), ts, type ('buy'|'sell'|'dividend'), date (jalali text), asset, category_id (FK), account_id (FK، nullable), qty, price, amount, fee, location, note` — `fee` به cost basis خرید اضافه و از عواید فروش کم می‌شود
- **withdrawals**: `id, portfolio_id (FK), ts, category_id (FK), date, amount, dest, note, level (nullable int), source_txn_id (FK→transactions.id, nullable — لینک به فروشی که این برداشت را ساخته)`
- **prices**: `asset (PK), price, updated_at` — قیمت روز مشترک بین همه‌ی سبدها (دقیقاً مثل `PRICES`/`PRICES_UPDATED_AT` در فرانت)
- **snapshots**: `id, portfolio_id (FK), date, total_value, total_investment, total_unrealized, total_realized, category_breakdown (JSON, کلید=category_id), created_at`
- **ladders**: `portfolio_id (FK), category_id (FK), idx (0..2), threshold_pct, withdraw_pct` — کلید ترکیبی `(portfolio_id, category_id, idx)`

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
| GET/PUT | /api/portfolios/<pid>/ladders/<category_id> | خواندن/تنظیم پله‌های یک کتگوری |
| POST | /api/portfolios/<pid>/secure-profit | 🔒 سیو سود: فروش واقعی + برداشت لینک‌شده، اتمیک |
| GET/POST | /api/portfolios/<pid>/snapshots | ثبت/خواندن نقطه‌ی روند عملکرد |
| GET/POST/PUT/DELETE | /api/users | مدیریت کاربران (فقط ادمین) |
| GET/POST | /api/categories | لیست/ایجاد کتگوری |
| PUT/DELETE | /api/categories/<id> | rename / حذف کتگوری (فقط اگر استفاده نشده) |
| GET/POST | /api/portfolios/<pid>/accounts | لیست/ایجاد حساب نقدی این سبد |
| PUT/DELETE | /api/accounts/<id> | ویرایش/حذف حساب (فقط اگر سابقه‌ی تراکنش ندارد) |
| GET | /api/accounts/<id>/movements | تاریخچه‌ی واریز/برداشت/انتقال یک حساب |
| POST | /api/accounts/<id>/deposit | واریز نقدی به حساب |
| POST | /api/accounts/<id>/withdraw | برداشت نقدی از حساب |
| POST | /api/portfolios/<pid>/transfer | انتقال نقدی بین دو حساب همان سبد، اتمیک |

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
