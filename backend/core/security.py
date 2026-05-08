from urllib.parse import urlparse

from django.conf import settings
from django.http import JsonResponse


CSRF_REJECTION_CODE = "cross_site_request_rejected"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def get_origin_from_url(value: str | None) -> str:
    if not value:
        return ""

    parsed = urlparse(value.strip())
    if not parsed.scheme or not parsed.netloc:
        return ""

    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def get_cookie_auth_origin(request) -> str:
    origin = get_origin_from_url(request.META.get("HTTP_ORIGIN"))
    if origin:
        return origin

    return get_origin_from_url(request.META.get("HTTP_REFERER"))


def get_allowed_cookie_auth_origins() -> set[str]:
    origin_sources = [
        getattr(settings, "FRONTEND_APP_URL", ""),
        *getattr(settings, "CSRF_TRUSTED_ORIGINS", []),
        *getattr(settings, "CORS_ALLOWED_ORIGINS", []),
    ]
    origins = {
        origin
        for origin in (get_origin_from_url(value) for value in origin_sources)
        if origin and "*" not in origin
    }

    return origins


def request_has_auth_cookie(request) -> bool:
    cookie_names = {
        getattr(settings, "AUTH_ACCESS_COOKIE_NAME", "cchis_access"),
        getattr(settings, "AUTH_REFRESH_COOKIE_NAME", "cchis_refresh"),
        *getattr(settings, "AUTH_REFRESH_COOKIE_LEGACY_NAMES", ()),
    }

    return any(request.COOKIES.get(cookie_name) for cookie_name in cookie_names if cookie_name)


def is_cookie_auth_write_route(request) -> bool:
    return (
        request.method.upper() in UNSAFE_METHODS
        and request.path.startswith("/api/")
        and request_has_auth_cookie(request)
    )


def csrf_rejection_response(detail: str) -> JsonResponse:
    return JsonResponse(
        {
            "detail": detail,
            "code": CSRF_REJECTION_CODE,
        },
        status=403,
    )


class CookieAuthOriginMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not is_cookie_auth_write_route(request):
            return self.get_response(request)

        if request.META.get("HTTP_SEC_FETCH_SITE", "").lower() == "cross-site":
            return csrf_rejection_response("Cross-site requests are not allowed for this action.")

        origin = get_cookie_auth_origin(request)
        if not origin:
            return csrf_rejection_response("Origin or referer is required for this action.")

        if origin not in get_allowed_cookie_auth_origins():
            return csrf_rejection_response("Request origin is not allowed for this action.")

        return self.get_response(request)
