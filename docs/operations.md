# راهنمای عملیات

## محیط تولید

مقادیر واقعی را در secret manager محیط اجرا نگه دارید؛ فایل .env را commit نکنید. برای تولید، حداقل این موارد لازم است:

- DJANGO_DEBUG=False، DJANGO_SECRET_KEY یکتا و قوی، DJANGO_ALLOWED_HOSTS و در صورت نیاز DJANGO_CSRF_TRUSTED_ORIGINS.
- DATABASE_URL برای PostgreSQL. در تولید SQLite پذیرفته نیست.
- HTTPS پشت reverse proxy، DJANGO_SECURE_SSL_REDIRECT=True، HSTS پس از تأیید دامنه، و cookie امن.
- مسیر پایدار و پشتیبان‌گیری‌شده برای MEDIA_ROOT. فایل‌های رسانه‌ای را داخل انتشار transient نگه ندارید.
- KAVENEGAR_API_KEY و KAVENEGAR_OTP_TEMPLATE واقعی.
- ZARINPAL_MERCHANT_ID، endpointهای درست sandbox یا production و ضریب واحد معتبر.

## انتشار

از پوشهٔ astrostore:

    python manage.py check --deploy
    python manage.py migrate
    python manage.py collectstatic --noinput
    gunicorn astrostore.wsgi:application --bind 0.0.0.0:8000

reverse proxy باید مسیر /static/ را از staticfiles/ و /media/ را از حجم پایدار ارائه کند، TLS را اعمال کند، و X-Forwarded-Proto را فقط از proxy مورد اعتماد تنظیم کند. پیش از بازکردن فروشگاه، HTTPS، backup/restore، SMS و پرداخت sandbox را بررسی کنید.

## کارهای زمان‌بندی‌شده

این فرمان را دست‌کم هر دقیقه اجرا کنید تا رزروهای سررسیدشده آزاد شوند:

    python manage.py release_expired_reservations --limit 200

روزانه فرمان پاک‌سازی challengeهای OTP و محدودکننده‌های قدیمی را اجرا کنید:

    python manage.py cleanup_otp_data

فرمان‌ها idempotent هستند؛ اجرای مکرر باعث آزادسازی دوبارهٔ موجودی نمی‌شود.

## پشتیبان‌گیری و بازیابی PostgreSQL

نمونهٔ اجرای دستی، با اتصال و رمز عبور مدیریت‌شده خارج از خط فرمان:

    pg_dump --format=custom "$DATABASE_NAME" > astrostore-$(date +%F).dump
    pg_restore --clean --if-exists --dbname="$RESTORE_DATABASE_URL" astrostore-YYYY-MM-DD.dump

برای دادهٔ رسانه، snapshot زمان‌بندی‌شدهٔ جداگانه بگیرید. پشتیبان‌گیری تنها وقتی قابل اتکاست که بازیابی دوره‌ای در محیط جداگانه آزمایش شده باشد. کلیدهای provider و secret Django را در فایل dump یا مخزن کد قرار ندهید.

## پایش و بازیابی

- خطاهای 5xx، timeoutهای Kavenegar/ZarinPal، سفارش‌های payment_review و رسیدهای بازپرداخت تطبیق‌نشده را پایش کنید.
- callback زرین‌پال به‌تنهایی پرداخت را موفق نمی‌کند؛ وضعیت از verify سمت سرور می‌آید.
- اگر verify در دسترس نباشد، تراکنش به بررسی مدیر می‌رود. رسید یا تراکنش بانکی را با پنل پذیرنده تطبیق دهید و رویداد مدیر را ثبت کنید.
- پیش‌فرض ضریب تبدیل مبلغ Toman به مقدار مورد انتظار API در کد ۱۰ است. واحد مورد انتظار پذیرنده را با تراکنش sandbox تأیید کنید و مقدار ZARINPAL_TOMAN_TO_RIAL را صریح تعیین کنید.
- بازپرداخت خودکار به provider پیاده‌سازی نشده است. پنل ثبت بازپرداخت، مبلغ را کنترل می‌کند و مدیر باید رسید بیرونی را بعد از انجام واقعی تطبیق دهد.

