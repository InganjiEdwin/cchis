from django.urls import path

from .consumers import DashboardNotificationConsumer


websocket_urlpatterns = [
    path("ws/notifications/stream/", DashboardNotificationConsumer.as_asgi()),
]
