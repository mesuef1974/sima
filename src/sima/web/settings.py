"""إعدادات Django لسِمة. الأسرار من `.env` (خارج git)، والقاعدة PostgreSQL محلي على 127.0.0.1 فقط."""
from __future__ import annotations

from pathlib import Path

from ..config import ENV as _ENV  # القارئ الوحيد للبيئة (sima/env.py)
from ..config import ROOT


def env(key: str, default: str | None = None) -> str:
    v = _ENV.get(key, default)
    if v is None:
        raise RuntimeError(f"المتغير {key} غير معرَّف في .env")
    return v


BASE_DIR = ROOT
SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DJANGO_DEBUG", "0") == "1"
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
# أخطاء الخادم (500) تُكتب في مخرج المنصة دائمًا؛ دون هذا يخفيها Django حين DEBUG معطّل فلا يُعرف سببها
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False}},
}

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_vite",
    "sima.web.registry",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "sima.web.middleware.AdminSessionMiddleware",  # جلسة القاعدة للوحة الإدارة وحدها
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "sima.web.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [Path(__file__).resolve().parent / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = None

# حزمة Vue: يبنيها Vite إلى FRONTEND_DIST ويقرأ django-vite بيانها؛ وضع التطوير بـ SIMA_VITE_DEV=1 (خادم Vite على 5173)
FRONTEND_DIST = Path(__file__).resolve().parent / "frontend_dist"
STATIC_URL = "/static/"
STATICFILES_DIRS = [FRONTEND_DIST] if FRONTEND_DIST.is_dir() else []
DJANGO_VITE = {"default": {
    "dev_mode": env("SIMA_VITE_DEV", "0") == "1",
    "dev_server_host": "127.0.0.1",
    "dev_server_port": 5173,
    "manifest_path": FRONTEND_DIST / ".vite" / "manifest.json",
}}
DATA_UPLOAD_MAX_MEMORY_SIZE = 8192

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("SIMA_DB_NAME", "sima"),
        "USER": env("SIMA_DB_USER", "sima"),
        "PASSWORD": env("SIMA_DB_PASSWORD"),
        "HOST": env("SIMA_DB_HOST", "127.0.0.1"),
        "PORT": env("SIMA_DB_PORT", "5544"),
        "CONN_MAX_AGE": 60,
        "OPTIONS": {"connect_timeout": 5},
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LANGUAGE_CODE = "ar"
TIME_ZONE = "Asia/Qatar"
USE_I18N = True  # لوحة الإدارة بالعربية واتجاه RTL دائمًا، أيًّا كانت لغة المتصفح
LANGUAGES = [("ar", "العربية")]
USE_TZ = True

# لوحة الإدارة: جلسة HttpOnly وSecure وSameSite=Strict (المتصفح يعدّ localhost و127.0.0.1 سياقًا آمنًا)، تنتهي بإغلاق المتصفح
# وبعد ساعة خمول؛ وCSRF للأصل المحلي فقط.
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_AGE = 3600
SESSION_SAVE_EVERY_REQUEST = True
CSRF_TRUSTED_ORIGINS = [f"http://{h}:{env('SIMA_BOARD_PORT', '8766')}" for h in ("127.0.0.1", "localhost")]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Strict"
CSRF_COOKIE_SAMESITE = "Strict"
X_FRAME_OPTIONS = "SAMEORIGIN"
