from django.contrib import admin
from django.urls import include, path
from rest_framework.permissions import AllowAny
from rest_framework.renderers import JSONOpenAPIRenderer
from rest_framework.schemas import get_schema_view

from .health import live_health, ready_health


v1_schema_view = get_schema_view(
    title="CCHIS Backend API",
    description=(
        "OpenAPI schema for the canonical CCHIS v1 API. Most routes require JWT "
        "authentication. The main intentional public endpoint is POST /api/v1/ussd/menu/."
    ),
    version="1.0.0",
    urlconf="core.api_v1_schema_urls",
    public=True,
    permission_classes=[AllowAny],
    renderer_classes=[JSONOpenAPIRenderer],
)

urlpatterns = [
    path("health/live/", live_health, name="health-live"),
    path("health/ready/", ready_health, name="health-ready"),
    path("admin/", admin.site.urls),
    path("api/v1/schema/", v1_schema_view, name="api-schema-v1"),
    path("api/v1/", include("core.api_v1_urls")),
]
