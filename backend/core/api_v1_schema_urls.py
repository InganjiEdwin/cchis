from django.urls import include, path


urlpatterns = [
    path("api/v1/", include("core.api_v1_urls")),
]
