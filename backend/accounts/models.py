import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    ROLE_ADMIN = "ADMIN"
    ROLE_SUPERVISOR = "SUPERVISOR"
    ROLE_CHV = "CHV"
    ROLE_ANALYST = "ANALYST"
    THEME_SYSTEM = "SYSTEM"
    THEME_LIGHT = "LIGHT"
    THEME_DARK = "DARK"

    ROLE_CHOICES = [
        (ROLE_ADMIN, "Admin"),
        (ROLE_SUPERVISOR, "Supervisor"),
        (ROLE_CHV, "CHV"),
        (ROLE_ANALYST, "Analyst"),
    ]
    THEME_PREFERENCE_CHOICES = [
        (THEME_SYSTEM, "System"),
        (THEME_LIGHT, "Light"),
        (THEME_DARK, "Dark"),
    ]

    full_name = models.CharField(max_length=255, blank=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True, unique=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_CHV)
    theme_preference = models.CharField(
        max_length=10,
        choices=THEME_PREFERENCE_CHOICES,
        default=THEME_SYSTEM,
    )
    ward = models.ForeignKey(
        "risk.Ward",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users",
    )
    is_totp_enabled = models.BooleanField(default=False)
    totp_secret = models.CharField(max_length=64, blank=True)

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
    EVENT_PASSWORD_RESET_COMPLETED = "PASSWORD_RESET_COMPLETED"
    EVENT_2FA_ENROLLMENT_REQUIRED = "TWO_FACTOR_ENROLLMENT_REQUIRED"
    EVENT_2FA_ENROLLMENT_STARTED = "TWO_FACTOR_ENROLLMENT_STARTED"
    EVENT_2FA_ENROLLMENT_COMPLETED = "TWO_FACTOR_ENROLLMENT_COMPLETED"
    EVENT_2FA_REQUIRED = "TWO_FACTOR_REQUIRED"
    EVENT_2FA_VERIFIED = "TWO_FACTOR_VERIFIED"
    EVENT_2FA_FAILED = "TWO_FACTOR_FAILED"
    EVENT_2FA_RECOVERY_CODES_GENERATED = "TWO_FACTOR_RECOVERY_CODES_GENERATED"
    EVENT_2FA_RECOVERY_CODES_REGENERATED = "TWO_FACTOR_RECOVERY_CODES_REGENERATED"
    EVENT_2FA_RECOVERY_CODE_USED = "TWO_FACTOR_RECOVERY_CODE_USED"
    EVENT_2FA_RECOVERY_CODE_FAILED = "TWO_FACTOR_RECOVERY_CODE_FAILED"
    EVENT_2FA_RECOVERY_CODES_LOW = "TWO_FACTOR_RECOVERY_CODES_LOW"
    EVENT_POLICY_ACCEPTANCE_REQUIRED = "POLICY_ACCEPTANCE_REQUIRED"
    EVENT_POLICY_ACCEPTED = "POLICY_ACCEPTED"
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
        (EVENT_PASSWORD_RESET_COMPLETED, "Password Reset Completed"),
        (EVENT_2FA_ENROLLMENT_REQUIRED, "Two-Factor Enrollment Required"),
        (EVENT_2FA_ENROLLMENT_STARTED, "Two-Factor Enrollment Started"),
        (EVENT_2FA_ENROLLMENT_COMPLETED, "Two-Factor Enrollment Completed"),
        (EVENT_2FA_REQUIRED, "Two-Factor Required"),
        (EVENT_2FA_VERIFIED, "Two-Factor Verified"),
        (EVENT_2FA_FAILED, "Two-Factor Failed"),
        (EVENT_2FA_RECOVERY_CODES_GENERATED, "Two-Factor Recovery Codes Generated"),
        (EVENT_2FA_RECOVERY_CODES_REGENERATED, "Two-Factor Recovery Codes Regenerated"),
        (EVENT_2FA_RECOVERY_CODE_USED, "Two-Factor Recovery Code Used"),
        (EVENT_2FA_RECOVERY_CODE_FAILED, "Two-Factor Recovery Code Failed"),
        (EVENT_2FA_RECOVERY_CODES_LOW, "Two-Factor Recovery Codes Low"),
        (EVENT_POLICY_ACCEPTANCE_REQUIRED, "Policy Acceptance Required"),
        (EVENT_POLICY_ACCEPTED, "Policy Accepted"),
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


class UserPolicyAcceptance(models.Model):
    DOCUMENT_TERMS = "TERMS"
    DOCUMENT_PRIVACY = "PRIVACY"
    DOCUMENT_COOKIE_NOTICE = "COOKIE_NOTICE"
    DOCUMENT_TYPE_CHOICES = [
        (DOCUMENT_TERMS, "Terms of Service"),
        (DOCUMENT_PRIVACY, "Privacy Policy"),
        (DOCUMENT_COOKIE_NOTICE, "Cookie Notice"),
    ]

    CONTEXT_FIRST_SIGN_IN = "first_sign_in"
    CONTEXT_VERSION_UPDATE = "version_update"
    CONTEXT_MANUAL_REVIEW = "manual_review"
    ACCEPTANCE_CONTEXT_CHOICES = [
        (CONTEXT_FIRST_SIGN_IN, "First sign-in"),
        (CONTEXT_VERSION_UPDATE, "Version update"),
        (CONTEXT_MANUAL_REVIEW, "Manual review"),
    ]

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="policy_acceptances",
    )
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPE_CHOICES)
    version = models.CharField(max_length=64)
    accepted_at = models.DateTimeField(default=timezone.now)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    acceptance_context = models.CharField(
        max_length=30,
        choices=ACCEPTANCE_CONTEXT_CHOICES,
        default=CONTEXT_FIRST_SIGN_IN,
    )
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-accepted_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "document_type", "version"],
                name="accounts_upa_user_doc_ver_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=["user", "document_type", "version"],
                name="accounts_upa_user_doc_ver_idx",
            ),
            models.Index(
                fields=["document_type", "version", "accepted_at"],
                name="accounts_upa_doc_ver_at_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} accepted {self.document_type} {self.version}"


class PasswordResetToken(models.Model):
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="password_reset_tokens",
    )
    token = models.CharField(max_length=128, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["token"]),
            models.Index(fields=["expires_at", "used_at"]),
        ]

    @property
    def is_expired(self) -> bool:
        return self.expires_at <= timezone.now()

    @property
    def is_usable(self) -> bool:
        return self.used_at is None and not self.is_expired


class AccessRequest(models.Model):
    STATUS_PENDING = "PENDING"
    STATUS_APPROVED = "APPROVED"
    STATUS_REJECTED = "REJECTED"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]

    full_name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=20, blank=True)
    county = models.CharField(max_length=120)
    administrative_ward = models.CharField(max_length=120)
    organization = models.CharField(max_length=255, blank=True)
    desired_role = models.CharField(max_length=20, choices=User.ROLE_CHOICES)
    contact_email = models.EmailField()
    message = models.TextField(blank=True)
    decision_message = models.TextField(blank=True)
    submitted_from_ip = models.GenericIPAddressField(null=True, blank=True)
    challenge_verified = models.BooleanField(default=False)
    review_status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-submitted_at"]
        indexes = [
            models.Index(fields=["review_status", "submitted_at"]),
            models.Index(fields=["contact_email", "submitted_at"]),
            models.Index(fields=["submitted_from_ip", "submitted_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.full_name} [{self.review_status}]"


class PreAuthToken(models.Model):
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="pre_auth_tokens",
    )
    token = models.CharField(max_length=128, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["token"]),
            models.Index(fields=["expires_at", "used_at"]),
        ]

    @property
    def is_expired(self) -> bool:
        return self.expires_at <= timezone.now()

    @property
    def is_usable(self) -> bool:
        return self.used_at is None and not self.is_expired


class TwoFactorRecoveryCode(models.Model):
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="two_factor_recovery_codes",
    )
    code_hash = models.CharField(max_length=255)
    code_hint = models.CharField(max_length=12, blank=True)
    batch_id = models.UUIDField(default=uuid.uuid4)
    used_at = models.DateTimeField(null=True, blank=True)
    invalidated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "batch_id"]),
            models.Index(fields=["user", "used_at", "invalidated_at"]),
            models.Index(fields=["batch_id", "created_at"]),
        ]

    @property
    def is_usable(self) -> bool:
        return self.used_at is None and self.invalidated_at is None

    def __str__(self) -> str:
        return f"Recovery code {self.code_hint or 'unhinted'} for {self.user_id}"
