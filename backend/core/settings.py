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
    "daphne",
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
    "channels",
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
    "core.security.CookieAuthOriginMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "accounts.middleware.HighRiskActionAuditMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "core.urls"
ASGI_APPLICATION = "core.asgi.application"

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

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

SOURCE_DATA_OPS_ENABLED = config("SOURCE_DATA_OPS_ENABLED", cast=bool, default=True)
SOURCE_DATA_IMPORT_CONFIRM_ENABLED = config("SOURCE_DATA_IMPORT_CONFIRM_ENABLED", cast=bool, default=True)
SOURCE_DATA_DOWNSTREAM_ACTIONS_ENABLED = config("SOURCE_DATA_DOWNSTREAM_ACTIONS_ENABLED", cast=bool, default=True)
FACILITY_READINESS_SNAPSHOT_IMPORT_ENABLED = config(
    "FACILITY_READINESS_SNAPSHOT_IMPORT_ENABLED",
    cast=bool,
    default=True,
)
SOURCE_DATA_API_CONNECTORS_ENABLED = config("SOURCE_DATA_API_CONNECTORS_ENABLED", cast=bool, default=True)
SOURCE_DATA_PHASE_AUDIT_REQUIRED = config("SOURCE_DATA_PHASE_AUDIT_REQUIRED", cast=bool, default=False)
SOURCE_DATA_UPLOAD_STORAGE_BACKEND = config("SOURCE_DATA_UPLOAD_STORAGE_BACKEND", default="shared_filesystem")
SOURCE_DATA_UPLOAD_ROOT = Path(
    config("SOURCE_DATA_UPLOAD_ROOT", default="/var/lib/cchis/source_uploads")
)
SOURCE_DATA_RAW_UPLOAD_RETENTION_DAYS = config("SOURCE_DATA_RAW_UPLOAD_RETENTION_DAYS", cast=int, default=60)
SOURCE_DATA_REJECTED_DIAGNOSTIC_RETENTION_DAYS = config(
    "SOURCE_DATA_REJECTED_DIAGNOSTIC_RETENTION_DAYS",
    cast=int,
    default=30,
)
SOURCE_DATA_METADATA_AUDIT_RETENTION_DAYS = config(
    "SOURCE_DATA_METADATA_AUDIT_RETENTION_DAYS",
    cast=int,
    default=730,
)
SOURCE_DATA_MAX_UPLOAD_SIZE_BYTES = config("SOURCE_DATA_MAX_UPLOAD_SIZE_BYTES", cast=int, default=20 * 1024 * 1024)
SOURCE_DATA_MAX_UPLOAD_ROWS = config("SOURCE_DATA_MAX_UPLOAD_ROWS", cast=int, default=50000)
SOURCE_DATA_ASYNC_IMPORT_SIZE_BYTES = config("SOURCE_DATA_ASYNC_IMPORT_SIZE_BYTES", cast=int, default=5 * 1024 * 1024)
SOURCE_DATA_APPROVAL_EXPIRY_HOURS = config("SOURCE_DATA_APPROVAL_EXPIRY_HOURS", cast=int, default=72)
SOURCE_DATA_LARGE_DELTA_APPROVAL_ROW_THRESHOLD = config(
    "SOURCE_DATA_LARGE_DELTA_APPROVAL_ROW_THRESHOLD",
    cast=int,
    default=10000,
)
SOURCE_DATA_TASK_STALE_MINUTES = config("SOURCE_DATA_TASK_STALE_MINUTES", cast=int, default=30)
SOURCE_DATA_OPERATIONS_ALERT_LOOKBACK_HOURS = config(
    "SOURCE_DATA_OPERATIONS_ALERT_LOOKBACK_HOURS",
    cast=int,
    default=24,
)
SOURCE_DATA_FAILED_IMPORT_ALERT_THRESHOLD = config(
    "SOURCE_DATA_FAILED_IMPORT_ALERT_THRESHOLD",
    cast=int,
    default=3,
)
SOURCE_DATA_ARTIFACT_CLEANUP_HOUR = config("SOURCE_DATA_ARTIFACT_CLEANUP_HOUR", cast=int, default=2)
SOURCE_DATA_ARTIFACT_CLEANUP_MINUTE = config("SOURCE_DATA_ARTIFACT_CLEANUP_MINUTE", cast=int, default=15)
SOURCE_DATA_CONNECTOR_FIXTURE_DIR = config("SOURCE_DATA_CONNECTOR_FIXTURE_DIR", default="")
SOURCE_DATA_DHIS2_BASE_URL = config("SOURCE_DATA_DHIS2_BASE_URL", default="")
SOURCE_DATA_DHIS2_USERNAME = config("SOURCE_DATA_DHIS2_USERNAME", default="")
SOURCE_DATA_DHIS2_PASSWORD = config("SOURCE_DATA_DHIS2_PASSWORD", default="")
SOURCE_DATA_DHIS2_MAPPING_JSON = config("SOURCE_DATA_DHIS2_MAPPING_JSON", default="")
SOURCE_DATA_DHIS2_CANONICAL_CSV_URL = config("SOURCE_DATA_DHIS2_CANONICAL_CSV_URL", default="")
SOURCE_DATA_OPENMRS_BASE_URL = config("SOURCE_DATA_OPENMRS_BASE_URL", default="")
SOURCE_DATA_OPENMRS_CLIENT_ID = config("SOURCE_DATA_OPENMRS_CLIENT_ID", default="")
SOURCE_DATA_OPENMRS_CLIENT_SECRET = config("SOURCE_DATA_OPENMRS_CLIENT_SECRET", default="")
SOURCE_DATA_OPENMRS_MAPPING_JSON = config("SOURCE_DATA_OPENMRS_MAPPING_JSON", default="")
SOURCE_DATA_OPENMRS_CANONICAL_CSV_URL = config("SOURCE_DATA_OPENMRS_CANONICAL_CSV_URL", default="")
SOURCE_DATA_WORLDPOP_KNBS_SOURCE_URL = config("SOURCE_DATA_WORLDPOP_KNBS_SOURCE_URL", default="")
SOURCE_DATA_WORLDPOP_KNBS_RELEASE_VERSION = config("SOURCE_DATA_WORLDPOP_KNBS_RELEASE_VERSION", default="")
SOURCE_DATA_WORLDPOP_KNBS_CANONICAL_CSV_URL = config("SOURCE_DATA_WORLDPOP_KNBS_CANONICAL_CSV_URL", default="")
SOURCE_DATA_OSM_OVERPASS_ENDPOINT = config("SOURCE_DATA_OSM_OVERPASS_ENDPOINT", default="")
SOURCE_DATA_OSM_OVERPASS_QUERY_REF = config("SOURCE_DATA_OSM_OVERPASS_QUERY_REF", default="")
SOURCE_DATA_OSM_OVERPASS_CANONICAL_CSV_URL = config("SOURCE_DATA_OSM_OVERPASS_CANONICAL_CSV_URL", default="")
SOURCE_DATA_LOGISTICS_BASE_URL = config("SOURCE_DATA_LOGISTICS_BASE_URL", default="")
SOURCE_DATA_LOGISTICS_CLIENT_ID = config("SOURCE_DATA_LOGISTICS_CLIENT_ID", default="")
SOURCE_DATA_LOGISTICS_CLIENT_SECRET = config("SOURCE_DATA_LOGISTICS_CLIENT_SECRET", default="")
SOURCE_DATA_LOGISTICS_MAPPING_JSON = config("SOURCE_DATA_LOGISTICS_MAPPING_JSON", default="")
SOURCE_DATA_LOGISTICS_CANONICAL_CSV_URL = config("SOURCE_DATA_LOGISTICS_CANONICAL_CSV_URL", default="")
SOURCE_DATA_SCHEDULED_CONNECTOR_KEYS = tuple(
    connector_key.strip()
    for connector_key in config("SOURCE_DATA_SCHEDULED_CONNECTOR_KEYS", default="dhis2_surveillance_weekly").split(",")
    if connector_key.strip()
)
SOURCE_DATA_CONNECTOR_REFRESH_HOUR = config("SOURCE_DATA_CONNECTOR_REFRESH_HOUR", cast=int, default=5)
SOURCE_DATA_CONNECTOR_REFRESH_MINUTE = config("SOURCE_DATA_CONNECTOR_REFRESH_MINUTE", cast=int, default=45)

USE_X_FORWARDED_HOST = config("USE_X_FORWARDED_HOST", cast=bool, default=False)
TRUST_X_FORWARDED_FOR = config("TRUST_X_FORWARDED_FOR", cast=bool, default=False)
TRUST_X_FORWARDED_PROTO = config("TRUST_X_FORWARDED_PROTO", cast=bool, default=False)
TRUSTED_PROXY_CONFIGURED = config("TRUSTED_PROXY_CONFIGURED", cast=bool, default=False)

if TRUST_X_FORWARDED_PROTO:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
else:
    SECURE_PROXY_SSL_HEADER = None

SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", cast=bool, default=False)
SECURE_SSL_REDIRECT_REVERSE_PROXY_EXEMPTION = config(
    "SECURE_SSL_REDIRECT_REVERSE_PROXY_EXEMPTION",
    cast=bool,
    default=False,
)
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

PASSWORD_MIN_LENGTH = 12

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": PASSWORD_MIN_LENGTH},
    },
    {
        "NAME": "accounts.password_validation.StrongPasswordValidator",
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
        "accounts.authentication.PolicyAwareJWTAuthentication",
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
        "auth_read": config("THROTTLE_AUTH_READ", default="120/minute"),
        "auth_write": config("THROTTLE_AUTH_WRITE", default="60/minute"),
        "public_ussd": config("THROTTLE_PUBLIC_USSD", default="120/minute"),
        "source_data_upload": config("THROTTLE_SOURCE_DATA_UPLOAD", default="20/hour"),
        "source_data_validate": config("THROTTLE_SOURCE_DATA_VALIDATE", default="60/hour"),
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
AUTH_STEP_UP_DEFAULT_SECONDS = config(
    "AUTH_STEP_UP_DEFAULT_SECONDS",
    cast=int,
    default=600,
)
AUTH_STEP_UP_DOWNLOAD_SECONDS = config(
    "AUTH_STEP_UP_DOWNLOAD_SECONDS",
    cast=int,
    default=300,
)
AUTH_STEP_UP_FAILURE_NOTIFICATION_THRESHOLD = config(
    "AUTH_STEP_UP_FAILURE_NOTIFICATION_THRESHOLD",
    cast=int,
    default=3,
)
AUTH_STEP_UP_FAILURE_NOTIFICATION_WINDOW_MINUTES = config(
    "AUTH_STEP_UP_FAILURE_NOTIFICATION_WINDOW_MINUTES",
    cast=int,
    default=15,
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
AUTH_TOKEN_RESPONSE_MODE = config(
    "AUTH_TOKEN_RESPONSE_MODE",
    default="cookie_only" if IS_SHARED_ENVIRONMENT else "body_and_cookie",
).strip().lower()
if AUTH_TOKEN_RESPONSE_MODE not in {"body_and_cookie", "cookie_only"}:
    raise ImproperlyConfigured("AUTH_TOKEN_RESPONSE_MODE must be body_and_cookie or cookie_only.")
AUTH_ACCESS_COOKIE_NAME = config(
    "AUTH_ACCESS_COOKIE_NAME",
    default="__Host-cchis_access" if IS_SHARED_ENVIRONMENT else "cchis_access",
).strip()
AUTH_ACCESS_COOKIE_PATH = config("AUTH_ACCESS_COOKIE_PATH", default="/").strip() or "/"
AUTH_ACCESS_COOKIE_SECURE = config(
    "AUTH_ACCESS_COOKIE_SECURE",
    cast=bool,
    default=True if IS_SHARED_ENVIRONMENT else SESSION_COOKIE_SECURE,
)
AUTH_ACCESS_COOKIE_HTTPONLY = config("AUTH_ACCESS_COOKIE_HTTPONLY", cast=bool, default=True)
AUTH_ACCESS_COOKIE_SAMESITE = config("AUTH_ACCESS_COOKIE_SAMESITE", default="Lax").strip() or "Lax"
AUTH_REFRESH_COOKIE_NAME = config(
    "AUTH_REFRESH_COOKIE_NAME",
    default="__Host-cchis_refresh" if IS_SHARED_ENVIRONMENT else "cchis_refresh",
).strip()
AUTH_REFRESH_COOKIE_PATH = config("AUTH_REFRESH_COOKIE_PATH", default="/").strip() or "/"
AUTH_REFRESH_COOKIE_SECURE = config(
    "AUTH_REFRESH_COOKIE_SECURE",
    cast=bool,
    default=True if IS_SHARED_ENVIRONMENT else SESSION_COOKIE_SECURE,
)
AUTH_REFRESH_COOKIE_HTTPONLY = config("AUTH_REFRESH_COOKIE_HTTPONLY", cast=bool, default=True)
AUTH_REFRESH_COOKIE_SAMESITE = config("AUTH_REFRESH_COOKIE_SAMESITE", default="Lax").strip() or "Lax"
AUTH_REFRESH_COOKIE_LEGACY_NAMES = tuple(
    cookie_name.strip()
    for cookie_name in config(
        "AUTH_REFRESH_COOKIE_LEGACY_NAMES",
        default="cchis_refresh" if AUTH_REFRESH_COOKIE_NAME != "cchis_refresh" else "",
    ).split(",")
    if cookie_name.strip() and cookie_name.strip() != AUTH_REFRESH_COOKIE_NAME
)
AUTH_REFRESH_PREVIOUS_JTI_GRACE_SECONDS = config(
    "AUTH_REFRESH_PREVIOUS_JTI_GRACE_SECONDS",
    cast=int,
    default=10,
)
AUTH_SESSION_REFRESH_LIFETIME_ADMIN_HOURS = config(
    "AUTH_SESSION_REFRESH_LIFETIME_ADMIN_HOURS",
    cast=int,
    default=24,
)
AUTH_SESSION_REFRESH_LIFETIME_SUPERVISOR_HOURS = config(
    "AUTH_SESSION_REFRESH_LIFETIME_SUPERVISOR_HOURS",
    cast=int,
    default=24,
)
AUTH_SESSION_REFRESH_LIFETIME_ANALYST_HOURS = config(
    "AUTH_SESSION_REFRESH_LIFETIME_ANALYST_HOURS",
    cast=int,
    default=72,
)
AUTH_SESSION_REFRESH_LIFETIME_CHV_HOURS = config(
    "AUTH_SESSION_REFRESH_LIFETIME_CHV_HOURS",
    cast=int,
    default=168,
)
AUTH_SESSION_IDLE_TIMEOUT_ADMIN_MINUTES = config(
    "AUTH_SESSION_IDLE_TIMEOUT_ADMIN_MINUTES",
    cast=int,
    default=60,
)
AUTH_SESSION_IDLE_TIMEOUT_SUPERVISOR_MINUTES = config(
    "AUTH_SESSION_IDLE_TIMEOUT_SUPERVISOR_MINUTES",
    cast=int,
    default=60,
)
AUTH_SESSION_IDLE_TIMEOUT_ANALYST_MINUTES = config(
    "AUTH_SESSION_IDLE_TIMEOUT_ANALYST_MINUTES",
    cast=int,
    default=120,
)
AUTH_SESSION_IDLE_TIMEOUT_CHV_MINUTES = config(
    "AUTH_SESSION_IDLE_TIMEOUT_CHV_MINUTES",
    cast=int,
    default=10080,
)
CURRENT_TERMS_VERSION = (
    config("CURRENT_TERMS_VERSION", default="terms-2026-05").strip() or "terms-2026-05"
)
CURRENT_PRIVACY_VERSION = (
    config("CURRENT_PRIVACY_VERSION", default="privacy-2026-05").strip() or "privacy-2026-05"
)
CURRENT_COOKIE_NOTICE_VERSION = (
    config("CURRENT_COOKIE_NOTICE_VERSION", default="cookies-2026-05").strip()
    or "cookies-2026-05"
)
POLICY_ACCEPTANCE_REQUIRED = config("POLICY_ACCEPTANCE_REQUIRED", cast=bool, default=True)
PRE_AUTH_TOKEN_LIFETIME_MINUTES = config(
    "PRE_AUTH_TOKEN_LIFETIME_MINUTES",
    cast=int,
    default=5,
)


def collect_shared_environment_security_errors(
    *,
    environment: str,
    auth_refresh_cookie_secure: bool,
    auth_access_cookie_secure: bool,
    auth_refresh_cookie_httponly: bool,
    auth_access_cookie_httponly: bool,
    auth_refresh_cookie_samesite: str,
    auth_access_cookie_samesite: str,
    session_cookie_secure: bool,
    csrf_cookie_secure: bool,
    secure_ssl_redirect: bool,
    secure_ssl_redirect_reverse_proxy_exemption: bool,
    secure_hsts_seconds: int,
    allowed_hosts: list[str],
    cors_allow_all_origins: bool,
    cors_allowed_origins: list[str],
    auth_refresh_cookie_name: str,
    auth_refresh_cookie_path: str,
    auth_access_cookie_name: str,
    auth_access_cookie_path: str,
    auth_token_response_mode: str,
    debug: bool | None = None,
    secret_key: str | None = None,
    csrf_trusted_origins: list[str] | None = None,
    use_x_forwarded_host: bool | None = None,
    trust_x_forwarded_for: bool | None = None,
    trust_x_forwarded_proto: bool | None = None,
    secure_proxy_ssl_header: tuple | None = None,
    trusted_proxy_configured: bool | None = None,
    email_provider: str | None = None,
    sms_provider: str | None = None,
) -> list[str]:
    if environment not in {"staging", "production"}:
        return []

    errors = []
    if environment == "production" and debug is True:
        errors.append("DEBUG must be False in production.")
    if secret_key is not None:
        normalized_secret = secret_key.strip().lower()
        weak_secret_placeholders = {
            "change-me",
            "change_me",
            "replace-me",
            "replace_me",
            "secret",
            "secret-key",
            "your-secret-key",
        }
        placeholder_markers = (
            "change",
            "replace",
            "your-",
            "example",
            "placeholder",
            "random-characters",
        )
        if (
            len(secret_key.strip()) < 50
            or len(set(secret_key.strip())) < 5
            or normalized_secret in weak_secret_placeholders
            or normalized_secret.startswith("django-insecure")
            or any(marker in normalized_secret for marker in placeholder_markers)
        ):
            errors.append("SECRET_KEY must be a long, non-placeholder secret in shared environments.")
    if not auth_refresh_cookie_secure:
        errors.append("AUTH_REFRESH_COOKIE_SECURE must be True.")
    if not auth_access_cookie_secure:
        errors.append("AUTH_ACCESS_COOKIE_SECURE must be True.")
    if not auth_refresh_cookie_httponly:
        errors.append("AUTH_REFRESH_COOKIE_HTTPONLY must be True.")
    if not auth_access_cookie_httponly:
        errors.append("AUTH_ACCESS_COOKIE_HTTPONLY must be True.")
    if auth_refresh_cookie_samesite not in {"Lax", "Strict"}:
        errors.append("AUTH_REFRESH_COOKIE_SAMESITE must be Lax or Strict.")
    if auth_access_cookie_samesite not in {"Lax", "Strict"}:
        errors.append("AUTH_ACCESS_COOKIE_SAMESITE must be Lax or Strict.")
    if auth_token_response_mode != "cookie_only":
        errors.append("AUTH_TOKEN_RESPONSE_MODE must be cookie_only.")
    if not auth_refresh_cookie_name.startswith("__Host-"):
        errors.append("AUTH_REFRESH_COOKIE_NAME must use the __Host- prefix.")
    if not auth_access_cookie_name.startswith("__Host-"):
        errors.append("AUTH_ACCESS_COOKIE_NAME must use the __Host- prefix.")
    if not session_cookie_secure:
        errors.append("SESSION_COOKIE_SECURE must be True.")
    if not csrf_cookie_secure:
        errors.append("CSRF_COOKIE_SECURE must be True.")
    if not secure_ssl_redirect and not secure_ssl_redirect_reverse_proxy_exemption:
        errors.append(
            "SECURE_SSL_REDIRECT must be True unless SECURE_SSL_REDIRECT_REVERSE_PROXY_EXEMPTION=True is documented for the deployment."
        )
    if secure_hsts_seconds <= 0:
        errors.append("SECURE_HSTS_SECONDS must be greater than 0.")
    if not allowed_hosts:
        errors.append("ALLOWED_HOSTS must contain at least one explicit host.")
    if any("*" in host or host.startswith(".") for host in allowed_hosts):
        errors.append("ALLOWED_HOSTS must not contain wildcard hosts.")
    if csrf_trusted_origins is not None:
        if not csrf_trusted_origins:
            errors.append("CSRF_TRUSTED_ORIGINS must contain at least one explicit HTTPS origin.")
        for origin in csrf_trusted_origins:
            parsed_origin = urlparse(origin)
            if parsed_origin.scheme != "https" or not parsed_origin.netloc or "*" in origin:
                errors.append("CSRF_TRUSTED_ORIGINS must contain explicit HTTPS origins without wildcards.")
                break
    if cors_allow_all_origins or any("*" in origin for origin in cors_allowed_origins):
        errors.append("CORS must not allow wildcard origins.")
    if auth_refresh_cookie_name.startswith("__Host-") and auth_refresh_cookie_path != "/":
        errors.append("__Host- refresh cookies must use AUTH_REFRESH_COOKIE_PATH=/.")
    if auth_access_cookie_name.startswith("__Host-") and auth_access_cookie_path != "/":
        errors.append("__Host- access cookies must use AUTH_ACCESS_COOKIE_PATH=/.")
    forwarded_headers_enabled = any(
        value is True
        for value in (use_x_forwarded_host, trust_x_forwarded_for, trust_x_forwarded_proto)
    )
    if forwarded_headers_enabled and trusted_proxy_configured is not True:
        errors.append("Forwarded headers require TRUSTED_PROXY_CONFIGURED=True for an explicit trusted proxy.")
    if trust_x_forwarded_proto is True and secure_proxy_ssl_header != ("HTTP_X_FORWARDED_PROTO", "https"):
        errors.append("TRUST_X_FORWARDED_PROTO requires SECURE_PROXY_SSL_HEADER to be configured explicitly.")
    if email_provider is not None and not email_provider:
        errors.append("EMAIL_PROVIDER must be explicitly configured outside local environments.")
    if sms_provider is not None and not sms_provider:
        errors.append("SMS_PROVIDER must be explicitly configured outside local environments.")

    return errors


def enforce_shared_environment_security() -> None:
    errors = collect_shared_environment_security_errors(
        environment=CCHIS_ENVIRONMENT,
        auth_refresh_cookie_secure=AUTH_REFRESH_COOKIE_SECURE,
        auth_access_cookie_secure=AUTH_ACCESS_COOKIE_SECURE,
        auth_refresh_cookie_httponly=AUTH_REFRESH_COOKIE_HTTPONLY,
        auth_access_cookie_httponly=AUTH_ACCESS_COOKIE_HTTPONLY,
        auth_refresh_cookie_samesite=AUTH_REFRESH_COOKIE_SAMESITE,
        auth_access_cookie_samesite=AUTH_ACCESS_COOKIE_SAMESITE,
        session_cookie_secure=SESSION_COOKIE_SECURE,
        csrf_cookie_secure=CSRF_COOKIE_SECURE,
        secure_ssl_redirect=SECURE_SSL_REDIRECT,
        secure_ssl_redirect_reverse_proxy_exemption=SECURE_SSL_REDIRECT_REVERSE_PROXY_EXEMPTION,
        secure_hsts_seconds=SECURE_HSTS_SECONDS,
        allowed_hosts=ALLOWED_HOSTS,
        cors_allow_all_origins=CORS_ALLOW_ALL_ORIGINS,
        cors_allowed_origins=CORS_ALLOWED_ORIGINS,
        auth_refresh_cookie_name=AUTH_REFRESH_COOKIE_NAME,
        auth_refresh_cookie_path=AUTH_REFRESH_COOKIE_PATH,
        auth_access_cookie_name=AUTH_ACCESS_COOKIE_NAME,
        auth_access_cookie_path=AUTH_ACCESS_COOKIE_PATH,
        auth_token_response_mode=AUTH_TOKEN_RESPONSE_MODE,
        debug=DEBUG,
        secret_key=SECRET_KEY,
        csrf_trusted_origins=CSRF_TRUSTED_ORIGINS,
        use_x_forwarded_host=USE_X_FORWARDED_HOST,
        trust_x_forwarded_for=TRUST_X_FORWARDED_FOR,
        trust_x_forwarded_proto=TRUST_X_FORWARDED_PROTO,
        secure_proxy_ssl_header=SECURE_PROXY_SSL_HEADER,
        trusted_proxy_configured=TRUSTED_PROXY_CONFIGURED,
        email_provider=config("EMAIL_PROVIDER", default="stub" if not IS_SHARED_ENVIRONMENT else "").strip().lower(),
        sms_provider=config("SMS_PROVIDER", default="stub" if not IS_SHARED_ENVIRONMENT else "").strip().lower(),
    )
    if errors:
        raise ImproperlyConfigured(
            "Unsafe shared-environment security settings: " + " ".join(errors)
        )


enforce_shared_environment_security()


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
CHANNEL_REDIS_URL = config("CHANNEL_REDIS_URL", default=CELERY_BROKER_URL)
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": config("CHANNEL_LAYER_BACKEND", default="channels_redis.core.RedisChannelLayer").strip(),
        "CONFIG": {
            "hosts": [CHANNEL_REDIS_URL],
        },
    }
}
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    "etl-heartbeat": {
        "task": "risk.tasks.record_etl_heartbeat_task",
        "schedule": crontab(minute="*/10"),
    },
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
    "daily-facility-burden-forecast-run": {
        "task": "risk.tasks.run_facility_burden_forecast_task",
        "schedule": crontab(hour=6, minute=30),
        "kwargs": {
            "model_version": "fnb-v1",
            "horizon_days": 7,
        },
    },
    "source-data-upload-artifact-cleanup": {
        "task": "risk.tasks.cleanup_source_data_upload_artifacts_task",
        "schedule": crontab(
            hour=SOURCE_DATA_ARTIFACT_CLEANUP_HOUR,
            minute=SOURCE_DATA_ARTIFACT_CLEANUP_MINUTE,
        ),
    },
}
if SOURCE_DATA_API_CONNECTORS_ENABLED:
    for connector_key in SOURCE_DATA_SCHEDULED_CONNECTOR_KEYS:
        CELERY_BEAT_SCHEDULE[f"source-data-connector-{connector_key}-refresh"] = {
            "task": "risk.tasks.run_source_data_connector_refresh_task",
            "schedule": crontab(
                hour=SOURCE_DATA_CONNECTOR_REFRESH_HOUR,
                minute=SOURCE_DATA_CONNECTOR_REFRESH_MINUTE,
            ),
            "kwargs": {
                "connector_key": connector_key,
                "force": False,
                "options": {"execution_mode": "scheduled"},
            },
        }

EMAIL_PROVIDER = config(
    "EMAIL_PROVIDER",
    default="stub" if not IS_SHARED_ENVIRONMENT else "",
).strip().lower()
SMS_PROVIDER = config(
    "SMS_PROVIDER",
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

if SMS_PROVIDER not in {"stub", "mobitech", "africastalking"}:
    raise ImproperlyConfigured("SMS_PROVIDER must be one of: stub, mobitech, africastalking.")

if IS_SHARED_ENVIRONMENT and not EMAIL_PROVIDER:
    raise ImproperlyConfigured("EMAIL_PROVIDER must be explicitly set outside local environments.")

if IS_SHARED_ENVIRONMENT and not SMS_PROVIDER:
    raise ImproperlyConfigured("SMS_PROVIDER must be explicitly set outside local environments.")

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

AFRICAS_TALKING_ENABLED = config("AFRICAS_TALKING_ENABLED", default="false", cast=bool)
MOBITECH_API_URL = config(
    "MOBITECH_API_URL",
    default="https://app.mobitechtechnologies.com//sms/sendmultiple",
).strip()
MOBITECH_API_KEY = config("MOBITECH_API_KEY", default="").strip()
MOBITECH_SENDER_ID = config("MOBITECH_SENDER_ID", default="").strip()
MOBITECH_SERVICE_ID = config("MOBITECH_SERVICE_ID", default="0").strip() or "0"
MOBITECH_DELIVERY_CALLBACK_URL = config("MOBITECH_DELIVERY_CALLBACK_URL", default="").strip()
MOBITECH_DELIVERY_CALLBACK_TOKEN = config("MOBITECH_DELIVERY_CALLBACK_TOKEN", default="").strip()
MOBITECH_HTTP_TIMEOUT_SECONDS = config("MOBITECH_HTTP_TIMEOUT_SECONDS", default=20, cast=int)

if SMS_PROVIDER == "africastalking":
    if not AFRICAS_TALKING_ENABLED and IS_SHARED_ENVIRONMENT:
        raise ImproperlyConfigured("Africa's Talking is parked and disabled; use SMS_PROVIDER=mobitech.")
    AFRICASTALKING_USERNAME = config("AFRICASTALKING_USERNAME", default="").strip()
    AFRICASTALKING_API_KEY = config("AFRICASTALKING_API_KEY", default="").strip()
    missing_africastalking_settings = [
        name
        for name, value in (
            ("AFRICASTALKING_USERNAME", AFRICASTALKING_USERNAME),
            ("AFRICASTALKING_API_KEY", AFRICASTALKING_API_KEY),
        )
        if not value
    ]
    if missing_africastalking_settings:
        missing_values = ", ".join(missing_africastalking_settings)
        raise ImproperlyConfigured(
            f"Africa's Talking SMS delivery requires these settings: {missing_values}."
        )

if SMS_PROVIDER == "mobitech" and IS_SHARED_ENVIRONMENT:
    missing_mobitech_settings = [
        name
        for name, value in (
            ("MOBITECH_API_URL", MOBITECH_API_URL),
            ("MOBITECH_API_KEY", MOBITECH_API_KEY),
            ("MOBITECH_SENDER_ID", MOBITECH_SENDER_ID),
        )
        if not value
    ]
    if missing_mobitech_settings:
        missing_values = ", ".join(missing_mobitech_settings)
        raise ImproperlyConfigured(
            f"Mobitech SMS delivery requires these settings: {missing_values}."
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
