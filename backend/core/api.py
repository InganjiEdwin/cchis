from rest_framework.pagination import PageNumberPagination
from rest_framework.views import exception_handler


class DefaultPageNumberPagination(PageNumberPagination):
    page_size_query_param = "page_size"
    max_page_size = 100


def cchis_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None

    data = response.data
    if isinstance(data, dict) and "detail" in data:
        return response

    if isinstance(data, dict):
        response.data = {
            "detail": "Validation error.",
            "errors": data,
            **data,
        }
        return response

    if isinstance(data, list):
        response.data = {
            "detail": "Validation error.",
            "errors": data,
        }
        return response

    response.data = {"detail": str(data)}
    return response
