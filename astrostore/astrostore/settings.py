"""
Django settings for the Astrostore Persian storefront.
Secrets and deployment-specific values are loaded from the environment.
"""
import os
from pathlib import Path
from urllib.parse import unquote, urlsplit

from django.core.exceptions import ImproperlyConfigured


BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent


def _load_env_file(path):
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


_load_env_file(PROJECT_ROOT / ".env")
_load_env_file(BASE_DIR / ".env")


def env_bool(name, default=False):
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


DEBUG = env_bool("DJANGO_DEBUG", True)
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "django-insecure-local-development-only-change-before-deploy")
if not DEBUG and SECRET_KEY.startswith("django-insecure-local"):
    raise ImproperlyConfigured("Set DJANGO_SECRET_KEY to a unique secret before production.")

ALLOWED_HOSTS = [host.strip() for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",") if host.strip()]
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if origin.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sitemaps",
    "account.apps.AccountConfig",
    "catalog.apps.CatalogConfig",
    "commerce.apps.CommerceConfig",
    "payments.apps.PaymentsConfig",
    "storefront.apps.StorefrontConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.gzip.GZipMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "astrostore.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates", PROJECT_ROOT / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "storefront.context_processors.store_context",
            ],
        },
    },
]
WSGI_APPLICATION = "astrostore.wsgi.application"
ASGI_APPLICATION = "astrostore.asgi.application"

database_url = os.environ.get("DATABASE_URL", "").strip()
if database_url.startswith(("postgres://", "postgresql://", "postgresql+psycopg://")):
    parsed = urlsplit(database_url.replace("postgresql+psycopg://", "postgresql://", 1))
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": unquote(parsed.path.lstrip("/")),
            "USER": unquote(parsed.username or ""),
            "PASSWORD": unquote(parsed.password or ""),
            "HOST": parsed.hostname or "localhost",
            "PORT": parsed.port or 5432,
            "CONN_MAX_AGE": int(os.environ.get("DB_CONN_MAX_AGE", "60")),
            "OPTIONS": {"sslmode": os.environ.get("DB_SSLMODE", "prefer")},
        }
    }
else:
    if not DEBUG:
        raise ImproperlyConfigured("Production requires DATABASE_URL configured for PostgreSQL.")
    sqlite_path = BASE_DIR / "db.sqlite3"
    if database_url.startswith("sqlite:///"):
        sqlite_path = Path(unquote(database_url[len("sqlite:///"):]))
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": sqlite_path, "OPTIONS": {"timeout": 20}}}

AUTH_USER_MODEL = "account.User"
AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "fa-ir"
LANGUAGES = [("fa", "فارسی")]
TIME_ZONE = "Asia/Tehran"
USE_I18N = True
USE_TZ = True
DATE_FORMAT = "Y/m/d"
DATETIME_FORMAT = "Y/m/d H:i"
USE_THOUSAND_SEPARATOR = True
THOUSAND_SEPARATOR = ","
NUMBER_GROUPING = 3

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", str(BASE_DIR / "media")))
PRIVATE_MEDIA_ROOT = Path(os.environ.get("PRIVATE_MEDIA_ROOT", str(BASE_DIR / "private_media")))
DIGITAL_MAX_UPLOAD_MB = int(os.environ.get("DIGITAL_MAX_UPLOAD_MB", "200"))
DIGITAL_DOWNLOAD_LIMIT = int(os.environ.get("DIGITAL_DOWNLOAD_LIMIT", "5"))
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"
            if not DEBUG else "django.contrib.staticfiles.storage.StaticFilesStorage"
        )
    },
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024

LOGIN_URL = "account:login"
LOGIN_REDIRECT_URL = "account:profile"
LOGOUT_REDIRECT_URL = "storefront:home"

SESSION_COOKIE_AGE = 60 * 60 * 24 * 30
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", not DEBUG)
SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_HSTS_SECONDS", "31536000" if not DEBUG else "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("DJANGO_HSTS_INCLUDE_SUBDOMAINS", False)
SECURE_HSTS_PRELOAD = env_bool("DJANGO_HSTS_PRELOAD", False)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "no-reply@example.invalid")

KAVENEGAR_API_KEY = os.environ.get("KAVENEGAR_API_KEY", "")
KAVENEGAR_OTP_TEMPLATE = os.environ.get("KAVENEGAR_OTP_TEMPLATE", "")
OTP_CONSOLE_FALLBACK = env_bool("OTP_CONSOLE_FALLBACK", True)
KAVENEGAR_TIMEOUT = int(os.environ.get("KAVENEGAR_TIMEOUT", "8"))
OTP_EXPIRY_SECONDS = int(os.environ.get("OTP_EXPIRY_SECONDS", "300"))
OTP_RESEND_COOLDOWN_SECONDS = int(os.environ.get("OTP_RESEND_COOLDOWN_SECONDS", "60"))
OTP_MAX_ATTEMPTS = int(os.environ.get("OTP_MAX_ATTEMPTS", "5"))
OTP_PHONE_LIMIT_PER_HOUR = int(os.environ.get("OTP_PHONE_LIMIT_PER_HOUR", "5"))
OTP_IP_LIMIT_PER_HOUR = int(os.environ.get("OTP_IP_LIMIT_PER_HOUR", "20"))
OTP_VERIFY_PHONE_LIMIT_PER_HOUR = int(os.environ.get("OTP_VERIFY_PHONE_LIMIT_PER_HOUR", "15"))
OTP_VERIFY_IP_LIMIT_PER_HOUR = int(os.environ.get("OTP_VERIFY_IP_LIMIT_PER_HOUR", "40"))

ZARINPAL_MERCHANT_ID = os.environ.get("ZARINPAL_MERCHANT_ID", "")
ZARINPAL_SANDBOX = env_bool("ZARINPAL_SANDBOX", DEBUG)
_default_gateway_host = "https://sandbox.zarinpal.com" if ZARINPAL_SANDBOX else "https://api.zarinpal.com"
ZARINPAL_API_BASE_URL = os.environ.get("ZARINPAL_API_BASE_URL", _default_gateway_host)
ZARINPAL_PAYMENT_BASE_URL = os.environ.get(
    "ZARINPAL_PAYMENT_BASE_URL",
    "https://sandbox.zarinpal.com/pg/StartPay/" if ZARINPAL_SANDBOX else "https://www.zarinpal.com/pg/StartPay/",
)
ZARINPAL_TOMAN_TO_RIAL = int(os.environ.get("ZARINPAL_TOMAN_TO_RIAL", "10"))
ZARINPAL_TIMEOUT = int(os.environ.get("ZARINPAL_TIMEOUT", "10"))
PAYMENT_RESERVATION_SECONDS = int(os.environ.get("PAYMENT_RESERVATION_SECONDS", "1800"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
}
