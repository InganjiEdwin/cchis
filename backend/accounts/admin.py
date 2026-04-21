from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import AuthAuditEvent, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        (
            "CCHIS Profile",
            {
                "fields": (
                    "full_name",
                    "phone_number",
                    "role",
                    "ward",
                )
            },
        ),
    )

    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        (
            "CCHIS Profile",
            {
                "fields": (
                    "full_name",
                    "phone_number",
                    "role",
                    "ward",
                )
            },
        ),
    )

    list_display = (
        "username",
        "email",
        "full_name",
        "role",
        "ward",
        "is_staff",
        "is_active",
    )
    list_filter = ("role", "is_staff", "is_active")
    search_fields = ("username", "email", "full_name", "phone_number")


@admin.register(AuthAuditEvent)
class AuthAuditEventAdmin(admin.ModelAdmin):
    list_display = (
        "event_type",
        "status",
        "actor",
        "target_user",
        "ward",
        "ip_address",
        "created_at",
    )
    list_filter = ("event_type", "status", "ward", "created_at")
    search_fields = ("actor__username", "target_user__username", "ip_address", "user_agent")
    readonly_fields = (
        "actor",
        "target_user",
        "ward",
        "event_type",
        "status",
        "ip_address",
        "user_agent",
        "metadata",
        "created_at",
    )
