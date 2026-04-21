import logging
import time


request_logger = logging.getLogger("risk.request")


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
                "path": request.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )

        return response