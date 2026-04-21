from django.urls import path

from .views import (
    ChangePasswordAPIView,
    DeactivateUserAPIView,
    LoginAPIView,
    LogoutAPIView,
    MeAPIView,
    ReactivateUserAPIView,
    RefreshAPIView,
    RegisterAPIView,
    AuthAuditEventListAPIView,
    AuthAuditSummaryAPIView,
)

urlpatterns = [
    path("login/", LoginAPIView.as_view(), name="auth-login"),
    path("refresh/", RefreshAPIView.as_view(), name="auth-refresh"),
    path("logout/", LogoutAPIView.as_view(), name="auth-logout"),
    path("change-password/", ChangePasswordAPIView.as_view(), name="auth-change-password"),
    path("me/", MeAPIView.as_view(), name="auth-me"),
    path("register/", RegisterAPIView.as_view(), name="auth-register"),
    path("audit-events/", AuthAuditEventListAPIView.as_view(), name="auth-audit-events"),
    path("audit-events/summary/", AuthAuditSummaryAPIView.as_view(), name="auth-audit-summary"),
    path("users/<int:user_id>/deactivate/", DeactivateUserAPIView.as_view(), name="auth-user-deactivate"),
    path("users/<int:user_id>/reactivate/", ReactivateUserAPIView.as_view(), name="auth-user-reactivate"),
]
