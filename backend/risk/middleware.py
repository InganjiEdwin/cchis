import logging
import time


request_logger = logging.getLogger("risk.request")


def _safe_request_path(path: str) -> str:
    """Redact the secret route segment used by provider callbacks."""

    marker = "/sms/mobitech/callback/"
    if marker not in path:
        return path
    prefix = path.split(marker, 1)[0]
    return f"{prefix}{marker}<redacted>/"


class MobitechCallbackPathRedactionFilter(logging.Filter):
    """Keep callback route secrets out of console log messages."""

    def filter(self, record):
        if isinstance(record.msg, str):
            record.msg = _safe_request_path(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(
                _safe_request_path(value) if isinstance(value, str) else value
                for value in record.args
            )
        return True


class RequestLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.perf_counter()
        response = self.get_response(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        request_logger.info(
            "request_complete",
            extra={
                "method": request.method,
                "path": _safe_request_path(request.path),
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )

        return response
