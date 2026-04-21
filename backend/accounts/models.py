from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    ROLE_ADMIN = "ADMIN"
    ROLE_SUPERVISOR = "SUPERVISOR"
    ROLE_CHV = "CHV"
    ROLE_ANALYST = "ANALYST"

    ROLE_CHOICES = [
        (ROLE_ADMIN, "Admin"),
        (ROLE_SUPERVISOR, "Supervisor"),
        (ROLE_CHV, "CHV"),
        (ROLE_ANALYST, "Analyst"),
    ]

    full_name = models.CharField(max_length=255, blank=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True, unique=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_CHV)
    ward = models.ForeignKey(
        "risk.Ward",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users",
    )

    class Meta:
        ordering = ["username"]

    def __str__(self) -> str:
        return self.username


class AuthAuditEvent(models.Model):
    EVENT_LOGIN_SUCCESS = "LOGIN_SUCCESS"
    EVENT_LOGIN_FAILED = "LOGIN_FAILED"
    EVENT_LOGOUT = "LOGOUT"
    EVENT_REFRESH_SUCCESS = "REFRESH_SUCCESS"
    EVENT_REFRESH_FAILED = "REFRESH_FAILED"
    EVENT_PASSWORD_CHANGED = "PASSWORD_CHANGED"
    EVENT_USER_CREATED = "USER_CREATED"
    EVENT_USER_DEACTIVATED = "USER_DEACTIVATED"
    EVENT_USER_REACTIVATED = "USER_REACTIVATED"

    EVENT_CHOICES = [
        (EVENT_LOGIN_SUCCESS, "Login Success"),
        (EVENT_LOGIN_FAILED, "Login Failed"),
        (EVENT_LOGOUT, "Logout"),
        (EVENT_REFRESH_SUCCESS, "Refresh Success"),
        (EVENT_REFRESH_FAILED, "Refresh Failed"),
        (EVENT_PASSWORD_CHANGED, "Password Changed"),
        (EVENT_USER_CREATED, "User Created"),
        (EVENT_USER_DEACTIVATED, "User Deactivated"),
        (EVENT_USER_REACTIVATED, "User Reactivated"),
    ]

    STATUS_SUCCESS = "SUCCESS"
    STATUS_FAILED = "FAILED"
    STATUS_CHOICES = [
        (STATUS_SUCCESS, "Success"),
        (STATUS_FAILED, "Failed"),
    ]

    actor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="auth_events_triggered",
    )
    target_user = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="auth_events_received",
    )
    ward = models.ForeignKey(
        "risk.Ward",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="auth_audit_events",
    )
    event_type = models.CharField(max_length=40, choices=EVENT_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["event_type", "created_at"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} [{self.status}]"
