from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from django.utils import timezone

from .models import AccessRequest, AuthAuditEvent, User, UserPolicyAcceptance
from .services import send_access_request_decision
from .two_factor import generate_totp_secret
from .views import with_access_request_review_signals


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
                    "theme_preference",
                    "ward",
                    "is_totp_enabled",
                    "totp_secret",
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
                    "theme_preference",
                    "ward",
                    "is_totp_enabled",
                    "totp_secret",
                )
            },
        ),
    )

    list_display = (
        "username",
        "email",
        "full_name",
        "role",
        "theme_preference",
        "ward",
        "is_totp_enabled",
        "is_staff",
        "is_active",
    )
    list_filter = ("role", "theme_preference", "is_totp_enabled", "is_staff", "is_active")
    search_fields = ("username", "email", "full_name", "phone_number")

    def save_model(self, request, obj, form, change):
        if obj.is_totp_enabled and not obj.totp_secret:
            obj.totp_secret = generate_totp_secret()
        super().save_model(request, obj, form, change)


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


@admin.register(UserPolicyAcceptance)
class UserPolicyAcceptanceAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "document_type",
        "version",
        "acceptance_context",
        "ip_address",
        "accepted_at",
    )
    list_filter = ("document_type", "version", "acceptance_context", "accepted_at")
    search_fields = ("user__username", "user__email", "version", "ip_address", "user_agent")
    readonly_fields = (
        "user",
        "document_type",
        "version",
        "accepted_at",
        "ip_address",
        "user_agent",
        "acceptance_context",
        "metadata",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AccessRequest)
class AccessRequestAdmin(admin.ModelAdmin):
    list_display = (
        "full_name",
        "desired_role",
        "county",
        "administrative_ward",
        "contact_email",
        "submitted_from_ip",
        "challenge_verified",
        "review_signals",
        "review_status",
        "decision_message_preview",
        "submitted_at",
        "reviewed_at",
    )
    list_filter = ("review_status", "desired_role", "county", "submitted_at", "reviewed_at")
    search_fields = (
        "full_name",
        "contact_email",
        "phone_number",
        "organization",
        "administrative_ward",
        "county",
        "submitted_from_ip",
    )
    readonly_fields = ("submitted_at", "reviewed_at", "submitted_from_ip", "challenge_verified", "review_signals")
    fieldsets = (
        (
            "Applicant",
            {
                "fields": (
                    "full_name",
                    "contact_email",
                    "phone_number",
                    "desired_role",
                )
            },
        ),
        (
            "Operational Context",
            {
                "fields": (
                    "county",
                    "administrative_ward",
                    "organization",
                    "message",
                    "submitted_from_ip",
                    "challenge_verified",
                    "review_signals",
                )
            },
        ),
        (
            "Ops Review",
            {
                "fields": (
                    "review_status",
                    "decision_message",
                    "submitted_at",
                    "reviewed_at",
                )
            },
        ),
    )

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return with_access_request_review_signals(queryset)

    @admin.display(description="Decision reason")
    def decision_message_preview(self, obj):
        if not obj.decision_message:
            return "-"
        return obj.decision_message[:48] + ("..." if len(obj.decision_message) > 48 else "")

    @admin.display(description="Review signals")
    def review_signals(self, obj):
        flags = []
        duplicate_email_count = getattr(obj, "duplicate_email_count", 0)
        duplicate_phone_count = getattr(obj, "duplicate_phone_count", 0)
        duplicate_ip_count = getattr(obj, "duplicate_ip_count", 0)
        pending_related_count = getattr(obj, "pending_related_count", 0)

        if duplicate_email_count:
            flags.append(f"email reuse ({duplicate_email_count})")
        if duplicate_phone_count:
            flags.append(f"phone reuse ({duplicate_phone_count})")
        if duplicate_ip_count:
            flags.append(f"ip reuse ({duplicate_ip_count})")
        if pending_related_count:
            flags.append(f"pending related ({pending_related_count})")
        if getattr(obj, "challenge_verified", False):
            flags.append("challenge verified")

        return ", ".join(flags) if flags else "-"

    def save_model(self, request, obj, form, change):
        previous = AccessRequest.objects.get(pk=obj.pk) if change else None
        review_changed = change and "review_status" in form.changed_data

        if review_changed and obj.review_status != AccessRequest.STATUS_PENDING:
            obj.reviewed_at = obj.reviewed_at or timezone.now()
        if review_changed and obj.review_status == AccessRequest.STATUS_PENDING:
            obj.reviewed_at = None

        super().save_model(request, obj, form, change)

        if (
            review_changed
            and previous
            and previous.review_status == AccessRequest.STATUS_PENDING
            and obj.review_status in {AccessRequest.STATUS_APPROVED, AccessRequest.STATUS_REJECTED}
        ):
            send_access_request_decision(
                obj,
                approved=obj.review_status == AccessRequest.STATUS_APPROVED,
                decision_message=obj.decision_message,
            )
