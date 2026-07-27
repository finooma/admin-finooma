# دفتر دارایی — نسخه‌ی متصل (Flask + SQLite + همان فرانت‌اند)

فرانت‌اند و بک‌اند حالا به هم وصل شده‌اند. بک‌اند خودِ فایل HTML را هم سرو می‌کند،
یعنی فقط با اجرای سرور، همه‌چیز از یک آدرس بالا می‌آید — بدون نیاز به CORS یا هاست جدا.

## اجرا با Docker (پیشنهادی)

یک کانتینر تنها — چون همین یک Flask، هم API را می‌دهد و هم خود فایل HTML را سرو
می‌کند، نیازی به کانتینر دوم نیست. دیتابیس SQLite روی یک **volume نام‌دار** نگه‌داری
می‌شود تا با هر بار `docker compose down` یا ری‌بیلد ایمیج، داده‌ها پاک نشوند.

```bash
# اختیاری ولی توصیه‌شده: یک .env با کلید JWT واقعی بسازید
cp .env.example .env
nano .env   # DAFTAR_JWT_SECRET را با یک مقدار تصادفی طولانی عوض کنید

docker compose up -d --build
```

بعد مرورگر را باز کنید: **http://localhost:5000**

فایل‌های مربوطه:
- `daftar_backend/Dockerfile` — ایمیج (Python 3.12 + gunicorn، یک worker چون SQLite است)
- `docker-compose.yml` (کنار همین فایل، یک پوشه بالاتر از `daftar_backend/`) — سرویس `daftar` را می‌سازد، پورت `5000` را باز می‌کند، و volume نام‌دار `db_data` را روی `/data` (مسیر `daftar.sqlite3` داخل کانتینر) mount می‌کند.
- `.env.example` — الگوی متغیرهای محیطی (کلید JWT)

دستورهای مفید:
```bash
docker compose logs -f          # دیدن لاگ‌ها
docker compose down             # توقف (داده‌ها می‌مانند، چون روی volume است)
docker compose down -v          # توقف و پاک کردن کامل داده‌ها (احتیاط!)
docker volume ls                # پیدا کردن نام واقعی volume دیتابیس
```

## اجرا بدون Docker (روش قبلی)

```bash
cd daftar_backend
pip install -r requirements.txt
python run.py
```

بعد در مرورگر باز کنید: **http://localhost:5000**

اولین اجرا، فایل دیتابیس (`daftar.sqlite3`) را خودش می‌سازد و صفحه‌ی «راه‌اندازی
اولیه» را نشان می‌دهد — همان‌جا اولین حساب (مدیر) را بسازید و وارد شوید.

## چه چیزی متصل شده

فایل `frontend/daftar-darayi.html` دیگر از `window.storage` استفاده نمی‌کند؛ هر
عملیات مستقیماً به API متصل بک‌اند می‌رود:

- ورود/ثبت‌نام → `/api/auth/login` و `/api/auth/register` (JWT، در `localStorage` مرورگر نگه‌داری می‌شود)
- ثبت/ویرایش/حذف تراکنش → `/api/portfolios/<id>/transactions`, `/api/transactions/<id>`
- قیمت روز → `/api/prices/<asset>`
- برداشت‌ها → `/api/portfolios/<id>/withdrawals`, `/api/withdrawals/<id>`
- پله‌های سود → `/api/portfolios/<id>/ladders/<category>`
- 🔒 سیو سود (فروش + برداشت اتمیک) → `/api/portfolios/<id>/secure-profit`
- گزارش روند عملکرد → `/api/portfolios/<id>/snapshots`
- سبدها و کاربران → `/api/portfolios`, `/api/users`
- درون‌ریزی از اکسل → هر ردیف به‌ترتیب با `POST /transactions` ثبت می‌شود

قابلیت «بازیابی از فایل پشتیبان محلی» در این نسخه غیرفعال شده، چون دیگر معنایی
ندارد — دیتابیس سرور (`daftar.sqlite3`) خودش منبع اصلی داده است؛ بکاپ گرفتن یعنی
کپی همان فایل.

## تست‌ها

```bash
cd daftar_backend
python3 tests/test_api.py
python3 -c "
import tests.test_business as t, inspect
for name, f in inspect.getmembers(t):
    if name.startswith('test_'): f()
print('OK')
"
```

هر دو مجموعه تست (منطق محاسباتی + جریان کامل API) پاس می‌شوند.

## اگر خواستید فرانت را جدا هاست کنید

اگر به‌جای سرو شدن توسط همین Flask، فایل `frontend/daftar-darayi.html` را جای
دیگری (مثلاً یک هاست استاتیک) گذاشتید، قبل از باز کردنش این خط را به آن اضافه
کنید (بالای تگ اسکریپت اصلی) و آدرس بک‌اند را وارد کنید:

```html
<script>window.__API_BASE__ = 'https://your-backend-domain.com/api';</script>
```

بک‌اند از قبل هدرهای CORS لازم را می‌فرستد، پس این حالت هم بدون مشکل کار می‌کند.
