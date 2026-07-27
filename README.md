# دفتر دارایی

## سریع‌ترین راه اجرا (Docker)

```bash
cp .env.example .env
nano .env               # DAFTAR_JWT_SECRET را با یک مقدار تصادفی طولانی عوض کنید
docker compose up -d --build
```

بعد مرورگر را باز کنید: **http://localhost:5000**

جزئیات کامل (بدون Docker، ساختار API، تست‌ها، معماری) در
[`daftar_backend/README.md`](./daftar_backend/README.md) و
[`daftar_backend/ARCHITECTURE.md`](./daftar_backend/ARCHITECTURE.md).

## ساختار پوشه‌ها

```
.
├── docker-compose.yml       ← این فایل را اجرا کنید (docker compose up)
├── .env.example             ← الگوی متغیر محیطی (کلید JWT)
└── daftar_backend/
    ├── Dockerfile
    ├── app/                 ← بک‌اند Flask
    ├── frontend/            ← daftar-darayi.html (همان فرانت، حالا به API وصل)
    └── tests/
```

## دستورهای پرکاربرد

```bash
docker compose logs -f     # لاگ‌های زنده
docker compose down        # توقف (دیتابیس روی volume می‌ماند)
docker compose down -v     # توقف + پاک کردن کامل دیتابیس (احتیاط!)
docker compose up -d --build   # ری‌بیلد بعد از تغییر کد
```
