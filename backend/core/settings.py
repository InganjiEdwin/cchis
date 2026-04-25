from pathlib import Path
from datetime import timedelta
from urllib.parse import urlparse

from decouple import config
from celery.schedules import crontab
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def get_cchis_environment() -> str:
    environment = config("CCHIS_ENVIRONMENT", default="local").strip().lower()
    allowed_environments = {"local", "staging", "production"}
    if environment not in allowed_environments:
        allowed = ", ".join(sorted(allowed_environments))
        raise ValueError(f"CCHIS_ENVIRONMENT must be one of: {allowed}. Got: {environment}")
    return environment


SECRET_KEY = config("SECRET_KEY")
DEBUG = config("DEBUG", cast=bool, default=False)
CCHIS_ENVIRONMENT = get_cchis_environment()
IS_SHARED_ENVIRONMENT = CCHIS_ENVIRONMENT in {"staging", "production"}
ALLOWED_HOSTS = [host.strip() for host in config("ALLOWED_HOSTS", default="127.0.0.1,localhost").split(",") if host.strip()]
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in config("CSRF_TRUSTED_ORIGINS", default="").split(",")
    if origin.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.gis",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "accounts",
    "risk",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "risk.middleware.RequestLogMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "core.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "core.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.contrib.gis.db.backends.postgis",
        "NAME": config("DB_NAME"),
        "USER": config("DB_USER"),
        "PASSWORD": config("DB_PASSWORD"),
        "HOST": config("DB_HOST"),
        "PORT": config("DB_PORT"),
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Nairobi"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"
USE_X_FORWARDED_HOST = config("USE_X_FORWARDED_HOST", cast=bool, default=False)
TRUST_X_FORWARDED_FOR = config("TRUST_X_FORWARDED_FOR", cast=bool, default=False)

if config("TRUST_X_FORWARDED_PROTO", cast=bool, default=False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
else:
    SECURE_PROXY_SSL_HEADER = None

SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", cast=bool, default=False)
SESSION_COOKIE_SECURE = config("SESSION_COOKIE_SECURE", cast=bool, default=False)
CSRF_COOKIE_SECURE = config("CSRF_COOKIE_SECURE", cast=bool, default=False)
SESSION_COOKIE_HTTPONLY = config("SESSION_COOKIE_HTTPONLY", cast=bool, default=True)
CSRF_COOKIE_HTTPONLY = config("CSRF_COOKIE_HTTPONLY", cast=bool, default=False)
SECURE_HSTS_SECONDS = config("SECURE_HSTS_SECONDS", cast=int, default=0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = config("SECURE_HSTS_INCLUDE_SUBDOMAINS", cast=bool, default=False)
SECURE_HSTS_PRELOAD = config("SECURE_HSTS_PRELOAD", cast=bool, default=False)
SECURE_CONTENT_TYPE_NOSNIFF = config("SECURE_CONTENT_TYPE_NOSNIFF", cast=bool, default=True)
SECURE_REFERRER_POLICY = config("SECURE_REFERRER_POLICY", default="same-origin")
X_FRAME_OPTIONS = config("X_FRAME_OPTIONS", default="DENY")

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

CORS_ALLOW_ALL_ORIGINS = config("CORS_ALLOW_ALL_ORIGINS", cast=bool, default=False)
CORS_ALLOW_CREDENTIALS = config("CORS_ALLOW_CREDENTIALS", cast=bool, default=True)
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in config("CORS_ALLOWED_ORIGINS", default="http://localhost:3000").split(",")
    if origin.strip()
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_SCHEMA_CLASS": "rest_framework.schemas.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "core.api.DefaultPageNumberPagination",
    "PAGE_SIZE": config("API_PAGE_SIZE", cast=int, default=25),
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.ScopedRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "access_request": config("THROTTLE_ACCESS_REQUEST", default="3/hour"),
        "access_request_options": config("THROTTLE_ACCESS_REQUEST_OPTIONS", default="120/hour"),
        "auth_login": config("THROTTLE_AUTH_LOGIN", default="5/minute"),
        "auth_2fa": config("THROTTLE_AUTH_2FA", default="5/minute"),
        "auth_refresh": config("THROTTLE_AUTH_REFRESH", default="30/minute"),
        "auth_recovery": config("THROTTLE_AUTH_RECOVERY", default="20/hour"),
        "auth_write": config("THROTTLE_AUTH_WRITE", default="60/minute"),
        "public_ussd": config("THROTTLE_PUBLIC_USSD", default="120/minute"),
    },
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "EXCEPTION_HANDLER": "core.api.cchis_exception_handler",
}

ACCESS_REQUEST_MIN_SUBMISSION_AGE_MS = config(
    "ACCESS_REQUEST_MIN_SUBMISSION_AGE_MS",
    cast=int,
    default=1500,
)
ACCESS_REQUEST_DUPLICATE_WINDOW_HOURS = config(
    "ACCESS_REQUEST_DUPLICATE_WINDOW_HOURS",
    cast=int,
    default=24,
)
AUTH_LOGIN_FAILURE_LIMIT = config(
    "AUTH_LOGIN_FAILURE_LIMIT",
    cast=int,
    default=5,
)
AUTH_LOGIN_FAILURE_WINDOW_SECONDS = config(
    "AUTH_LOGIN_FAILURE_WINDOW_SECONDS",
    cast=int,
    default=900,
)
AUTH_LOGIN_COOLDOWN_SECONDS = config(
    "AUTH_LOGIN_COOLDOWN_SECONDS",
    cast=int,
    default=900,
)
AUTH_2FA_FAILURE_LIMIT = config(
    "AUTH_2FA_FAILURE_LIMIT",
    cast=int,
    default=5,
)
AUTH_2FA_FAILURE_WINDOW_SECONDS = config(
    "AUTH_2FA_FAILURE_WINDOW_SECONDS",
    cast=int,
    default=900,
)
AUTH_2FA_COOLDOWN_SECONDS = config(
    "AUTH_2FA_COOLDOWN_SECONDS",
    cast=int,
    default=900,
)
AUTH_LOGIN_TURNSTILE_ENABLED = config(
    "AUTH_LOGIN_TURNSTILE_ENABLED",
    cast=bool,
    default=False,
)
AUTH_LOGIN_TURNSTILE_THRESHOLD = config(
    "AUTH_LOGIN_TURNSTILE_THRESHOLD",
    cast=int,
    default=3,
)
AUTH_REFRESH_FAILURE_LIMIT = config(
    "AUTH_REFRESH_FAILURE_LIMIT",
    cast=int,
    default=5,
)
AUTH_REFRESH_FAILURE_WINDOW_SECONDS = config(
    "AUTH_REFRESH_FAILURE_WINDOW_SECONDS",
    cast=int,
    default=900,
)
AUTH_REFRESH_COOLDOWN_SECONDS = config(
    "AUTH_REFRESH_COOLDOWN_SECONDS",
    cast=int,
    default=900,
)
ACCESS_REQUEST_TURNSTILE_ENABLED = config(
    "ACCESS_REQUEST_TURNSTILE_ENABLED",
    cast=bool,
    default=False,
)
TURNSTILE_SECRET_KEY = config("TURNSTILE_SECRET_KEY", default="")
TURNSTILE_SITEVERIFY_URL = config(
    "TURNSTILE_SITEVERIFY_URL",
    default="https://challenges.cloudflare.com/turnstile/v0/siteverify",
)
TURNSTILE_EXPECTED_HOSTNAME = config(
    "TURNSTILE_EXPECTED_HOSTNAME",
    default=urlparse(config("FRONTEND_APP_URL", default="http://localhost:3000").strip().rstrip("/")).hostname or "",
)

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

PASSWORD_RESET_TOKEN_LIFETIME_MINUTES = config(
    "PASSWORD_RESET_TOKEN_LIFETIME_MINUTES",
    cast=int,
    default=60,
)
FRONTEND_APP_URL = config("FRONTEND_APP_URL", default="http://localhost:3000").strip().rstrip("/")
AUTH_REFRESH_COOKIE_NAME = config("AUTH_REFRESH_COOKIE_NAME", default="cchis_refresh").strip()
AUTH_REFRESH_COOKIE_PATH = config("AUTH_REFRESH_COOKIE_PATH", default="/").strip() or "/"
AUTH_REFRESH_COOKIE_SECURE = config(
    "AUTH_REFRESH_COOKIE_SECURE",
    cast=bool,
    default=SESSION_COOKIE_SECURE,
)
AUTH_REFRESH_COOKIE_HTTPONLY = config("AUTH_REFRESH_COOKIE_HTTPONLY", cast=bool, default=True)
AUTH_REFRESH_COOKIE_SAMESITE = config("AUTH_REFRESH_COOKIE_SAMESITE", default="Lax").strip() or "Lax"
PRE_AUTH_TOKEN_LIFETIME_MINUTES = config(
    "PRE_AUTH_TOKEN_LIFETIME_MINUTES",
    cast=int,
    default=5,
)


def parse_role_setting(setting_name: str, default: str) -> tuple[str, ...]:
    return tuple(
        role.strip().upper()
        for role in config(setting_name, default=default).split(",")
        if role.strip()
    )


TOTP_REQUIRED_ROLES = parse_role_setting("TOTP_REQUIRED_ROLES", default="ADMIN,SUPERVISOR")
TOTP_OPTIONAL_ROLES = parse_role_setting("TOTP_OPTIONAL_ROLES", default="ANALYST")

CELERY_BROKER_URL = config("CELERY_BROKER_URL", default="redis://redis:6379/0")
CELERY_RESULT_BACKEND = config("CELERY_RESULT_BACKEND", default="redis://redis:6379/1")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    "daily-rainfall-ingestion-run": {
        "task": "risk.tasks.run_rainfall_ingestion_task",
        "schedule": crontab(hour=5, minute=30),
    },
    "daily-risk-model-run": {
        "task": "risk.tasks.run_risk_model_task",
        "schedule": crontab(hour=6, minute=0),
        "kwargs": {
            "model_version": "lr-v1",
            "trigger_alerts": True,
            "send_sms": False,
        },
    },
}

EMAIL_PROVIDER = config(
    "EMAIL_PROVIDER",
    default="stub" if not IS_SHARED_ENVIRONMENT else "",
).strip().lower()
MAILGUN_API_KEY = config("MAILGUN_API_KEY", default="").strip()
MAILGUN_PASSKEY = config("MAILGUN_PASSKEY", default="").strip()
MAILGUN_HOST = config("MAILGUN_HOST", default="").strip()
MAILGUN_DOMAIN = config("MAILGUN_DOMAIN", default="").strip()
MAILGUN_FROM_EMAIL = config("MAILGUN_FROM_EMAIL", default="").strip()
MAILGUN_WEBHOOK_SIGNING_KEY = config("MAILGUN_WEBHOOK_SIGNING_KEY", default="").strip()
MAILERSEND_WEBHOOK_SECRET = config("MAILERSEND_WEBHOOK_SECRET", default="").strip()
MAILGUN_BASE_URL = config(
    "MAILGUN_BASE_URL",
    default="https://api.mailgun.net/v3",
).strip()
MAILGUN_REPLY_TO = config("MAILGUN_REPLY_TO", default="").strip()

if EMAIL_PROVIDER not in {"stub", "mailgun"}:
    raise ImproperlyConfigured("EMAIL_PROVIDER must be one of: stub, mailgun.")

if IS_SHARED_ENVIRONMENT and not EMAIL_PROVIDER:
    raise ImproperlyConfigured("EMAIL_PROVIDER must be explicitly set outside local environments.")

if EMAIL_PROVIDER == "mailgun":
    missing_mailgun_settings = [
        name
        for name, value in (
            ("MAILGUN_API_KEY", MAILGUN_API_KEY),
            ("MAILGUN_DOMAIN", MAILGUN_DOMAIN),
            ("MAILGUN_FROM_EMAIL", MAILGUN_FROM_EMAIL),
        )
        if not value
    ]
    if missing_mailgun_settings:
        missing_values = ", ".join(missing_mailgun_settings)
        raise ImproperlyConfigured(
            f"Mailgun email delivery requires these settings: {missing_values}."
        )

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s"
        },
        "request": {
            "format": "%(asctime)s %(levelname)s %(name)s method=%(method)s path=%(path)s status=%(status_code)s duration_ms=%(duration_ms)s"
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": True,
        },
        "risk": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "risk.request": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "risk.ml": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "risk.alerts": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "accounts.audit": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "communications.email": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
