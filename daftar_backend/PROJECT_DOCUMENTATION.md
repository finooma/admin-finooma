# دفتر دارایی — مستندات پروژه و حفاظت از اطلاعات

## معرفی

این پروژه یک سامانه ثبت تراکنش و گزارش دارایی است. Backend با Flask/Gunicorn، رابط کاربری به‌صورت فایل HTML داخل پوشه `frontend` و دیتابیس SQLite اجرا می‌شود.

## اجرای پروژه

در محیط Docker، از پوشه‌ای که `docker-compose.yml` در آن قرار دارد اجرا کنید:

```bash
docker compose up -d --build
```

سرویس روی پورت `5000` اجرا می‌شود. در محیط واقعی بهتر است دسترسی عمومی از طریق Nginx و HTTPS باشد و پورت 5000 مستقیماً روی اینترنت باز نباشد.

## محل ذخیره اطلاعات

دیتابیس اصلی داخل کانتینر در مسیر زیر است:

```text
/data/daftar.sqlite3
```

این مسیر به volume دائمی Docker به نام `db_data` وصل است. بنابراین rebuild کردن image یا اجرای `docker compose down` اطلاعات را حذف نمی‌کند.

### دستورهای خطرناک

دستور زیر دیتابیس را حذف می‌کند و نباید برای توقف معمولی استفاده شود:

```bash
docker compose down -v
```

برای توقف عادی از این استفاده کنید:

```bash
docker compose down
```

یا:

```bash
docker compose stop
```

Git فقط کد پروژه را نگه می‌دارد؛ اطلاعات تراکنش داخل Git قرار نمی‌گیرد.

## بکاپ هفتگی

اسکریپت `backup_database.sh` از API داخلی SQLite یک snapshot سازگار می‌گیرد، بدون اینکه لازم باشد سرویس متوقف شود. بکاپ‌ها در پوشه `backups/` ذخیره می‌شوند و نسخه‌های قدیمی‌تر از ۱۲ هفته به‌صورت خودکار حذف می‌شوند.

روی سرور Ubuntu:

```bash
cd ~/admin-finooma
chmod +x daftar_backend/backup_database.sh
mkdir -p backups
./daftar_backend/backup_database.sh
```

برای اجرای خودکار هر هفته، cron را باز کنید:

```bash
crontab -e
```

این خط را اضافه کنید تا هر یکشنبه ساعت 03:30 اجرا شود:

```cron
30 3 * * 0 /home/ubuntu/admin-finooma/daftar_backend/backup_database.sh >> /home/ubuntu/admin-finooma/backups/backup.log 2>&1
```

### نکته حیاتی درباره بکاپ

بکاپ روی همان سرور برای خرابی دیسک یا حذف کامل سرور کافی نیست. پوشه `backups/` را به‌صورت دوره‌ای روی یک فضای جداگانه مثل Object Storage، سرور دوم یا کامپیوتر مدیر کپی کنید.

## بررسی بکاپ‌ها

```bash
ls -lh ~/admin-finooma/backups
tail -50 ~/admin-finooma/backups/backup.log
```

برای بررسی سلامت یک فایل بکاپ:

```bash
docker compose run --rm -v "$PWD/backups:/backups" daftar \
  python -c "import sqlite3,glob; p=sorted(glob.glob('/backups/daftar-*.sqlite3'))[-1]; c=sqlite3.connect(p); print(c.execute('PRAGMA integrity_check').fetchone()[0]); c.close()"
```

خروجی سالم باید `ok` باشد.

## بازیابی اطلاعات

قبل از بازیابی، از دیتابیس فعلی یک بکاپ جداگانه بگیرید. سپس سرویس را متوقف کنید و فایل بکاپ را داخل volume قرار دهید:

```bash
./daftar_backend/backup_database.sh
docker compose stop
docker compose cp backups/daftar-YYYY-MM-DD_HH-MM-SS.sqlite3 daftar:/data/daftar.sqlite3
docker compose start
```

در دستور بالا نام واقعی فایل بکاپ را جایگزین کنید. بعد از ورود، چند تراکنش و کاربر را بررسی کنید.

## به‌روزرسانی از GitHub

قبل از pull، بکاپ بگیرید:

```bash
./daftar_backend/backup_database.sh
git pull origin main
docker compose up -d --build
```

به‌روزرسانی کد، دیتابیس volume را حذف نمی‌کند.

## امنیت عملیاتی

- مقدار `DAFTAR_JWT_SECRET` را در فایل `.env` با یک مقدار تصادفی و طولانی تنظیم کنید.
- فایل `.env` و بکاپ دیتابیس را commit یا public نکنید.
- برای دامنه از HTTPS استفاده کنید.
- دسترسی SSH را با کلید محدود کنید و ورود root را غیرفعال کنید.
- هر هفته موفقیت cron و وجود فایل بکاپ را بررسی کنید.
