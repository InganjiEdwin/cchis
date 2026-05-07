import logging
import time

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.conf import settings
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.validators import UniqueValidator
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenObtainSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from risk.models import Ward

from .audit import get_client_ip
from .models import AccessRequest, AuthAuditEvent, UserPolicyAcceptance
from .services import build_policy_acceptance_status, get_current_policy_versions
from .two_factor import (
    build_totp_provisioning_uri,
    create_pre_auth_token,
    get_two_factor_policy_for_user,
    is_totp_enrolled,
    user_must_enroll_two_factor,
    user_requires_two_factor,
)


User = get_user_model()
security_logger = logging.getLogger("accounts.security")


def normalize_kenyan_phone_number(value: str) -> str:
    trimmed = value.strip()
    if not trimmed:
        return ""

    compact = trimmed.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")

    if compact.startswith("+254") and len(compact) == 13 and compact[1:].isdigit():
        return compact
    if compact.startswith("254") and len(compact) == 12 and compact.isdigit():
        return f"+{compact}"
    if compact.startswith("0") and len(compact) == 10 and compact.isdigit():
        return f"+254{compact[1:]}"

    return compact


class UserSerializer(serializers.ModelSerializer):
    ward_name = serializers.CharField(source="ward.name", read_only=True)
    scope_type = serializers.SerializerMethodField()
    scope_ward_id = serializers.SerializerMethodField()
    two_factor_policy = serializers.SerializerMethodField()
    is_totp_enabled = serializers.BooleanField(read_only=True)
    account_created_at = serializers.DateTimeField(source="date_joined", read_only=True)
    last_login_at = serializers.DateTimeField(source="last_login", read_only=True, allow_null=True)
    profile_capabilities = serializers.SerializerMethodField()
    policy_acceptance = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "full_name",
            "phone_number",
            "role",
            "theme_preference",
            "ward",
            "ward_name",
            "scope_type",
            "scope_ward_id",
            "two_factor_policy",
            "is_totp_enabled",
            "is_active",
            "account_created_at",
            "last_login_at",
            "profile_capabilities",
            "policy_acceptance",
        ]

    def get_scope_type(self, obj):
        if obj.role in [User.ROLE_ADMIN, User.ROLE_ANALYST]:
            return "BROAD"
        if obj.ward_id:
            return "WARD"
        return "NONE"

    def get_scope_ward_id(self, obj):
        if obj.role in [User.ROLE_ADMIN, User.ROLE_ANALYST]:
            return None
        return obj.ward_id

    def get_two_factor_policy(self, obj):
        return get_two_factor_policy_for_user(obj)

    def get_profile_capabilities(self, obj):
        two_factor_policy = get_two_factor_policy_for_user(obj)
        can_update_identity = obj.is_active and is_totp_enrolled(obj)
        return {
            "can_change_password": obj.is_active,
            "can_update_appearance": obj.is_active,
            "can_manage_totp": obj.is_active and two_factor_policy != "NONE",
            "can_view_own_activity": obj.is_active,
            "can_update_identity": can_update_identity,
            "can_review_sessions": False,
            "can_generate_profile_report": False,
            "identity_update_mode": "totp_step_up" if can_update_identity else "admin_managed",
            "mode": "auth_contract_backed_profile",
        }

    def get_policy_acceptance(self, obj):
        return build_policy_acceptance_status(obj)


class PolicyAcceptanceSerializer(serializers.Serializer):
    accepted_terms = serializers.BooleanField()
    accepted_privacy = serializers.BooleanField()
    accepted_cookie_notice = serializers.BooleanField()
    terms_version = serializers.CharField(max_length=64)
    privacy_version = serializers.CharField(max_length=64)
    cookie_notice_version = serializers.CharField(max_length=64)
    acceptance_context = serializers.ChoiceField(
        choices=[choice[0] for choice in UserPolicyAcceptance.ACCEPTANCE_CONTEXT_CHOICES],
        required=False,
    )

    def validate(self, attrs):
        errors = {}
        required_acknowledgements = {
            "accepted_terms": "Accept the current Terms of Service to continue.",
            "accepted_privacy": "Acknowledge the current Privacy Policy to continue.",
            "accepted_cookie_notice": "Acknowledge the current Cookie Notice to continue.",
        }

        for field, message in required_acknowledgements.items():
            if attrs.get(field) is not True:
                errors[field] = message

        current_versions = get_current_policy_versions()
        version_checks = {
            "terms_version": current_versions["terms_version"],
            "privacy_version": current_versions["privacy_version"],
            "cookie_notice_version": current_versions["cookie_notice_version"],
        }
        for field, current_version in version_checks.items():
            if attrs.get(field) != current_version:
                errors[field] = (
                    "This policy version is no longer current. Refresh and review the latest version."
                )

        if errors:
            raise serializers.ValidationError(errors)

        return attrs


class UserAppearanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["theme_preference"]


class UserProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["username", "email", "full_name", "phone_number", "theme_preference"]
        extra_kwargs = {
            "username": {"required": False},
            "email": {"required": False},
            "full_name": {"required": False, "allow_blank": True},
            "phone_number": {"required": False, "allow_blank": True, "allow_null": True},
            "theme_preference": {"required": False},
        }

    def validate_username(self, value):
        username = value.strip()
        if not username:
            raise serializers.ValidationError("Username cannot be blank.")
        if self.instance and username.lower() == self.instance.username.lower():
            return username
        queryset = User.objects.filter(username__iexact=username)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("This username is already in use.")
        return username

    def validate_email(self, value):
        email = value.strip().lower()
        if not email:
            raise serializers.ValidationError("Email address cannot be blank.")
        if self.instance and email == self.instance.email.lower():
            return email
        queryset = User.objects.filter(email__iexact=email)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("This email address is already in use.")
        return email

    def validate_phone_number(self, value):
        if value in {None, ""}:
            return None

        phone_number = normalize_kenyan_phone_number(value)
        if self.instance and phone_number == (self.instance.phone_number or ""):
            return phone_number
        queryset = User.objects.filter(phone_number=phone_number)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("This phone number is already in use.")
        return phone_number


class RegisterSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(
        required=True,
        validators=[UniqueValidator(queryset=User.objects.all())],
    )
    password = serializers.CharField(write_only=True, min_length=settings.PASSWORD_MIN_LENGTH)

    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "full_name",
            "phone_number",
            "role",
            "ward",
            "password",
        ]

    def validate_email(self, value):
        return value.strip().lower()

    def validate(self, attrs):
        role = attrs.get("role", User.ROLE_CHV)
        ward = attrs.get("ward")
        password = attrs.get("password", "")

        if role == User.ROLE_CHV and ward is None:
            raise serializers.ValidationError(
                {"ward": "Ward is required when creating a CHV user."}
            )

        user = User(
            username=attrs.get("username", ""),
            email=attrs.get("email", ""),
            full_name=attrs.get("full_name", ""),
        )
        try:
            validate_password(password, user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)}) from exc

        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=settings.PASSWORD_MIN_LENGTH)

    def validate_current_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate_new_password(self, value):
        user = self.context["request"].user
        try:
            validate_password(value, user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value


class PasswordResetRequestSerializer(serializers.Serializer):
    identifier = serializers.CharField(max_length=255)

    def validate_identifier(self, value):
        return value.strip()


class PasswordResetConfirmSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=128)
    new_password = serializers.CharField(write_only=True, min_length=settings.PASSWORD_MIN_LENGTH)

    def validate_token(self, value):
        return value.strip()

    def validate_new_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value


class VerifyTwoFactorSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=128)
    code = serializers.CharField(max_length=64)

    def validate_token(self, value):
        return value.strip()

    def validate_code(self, value):
        code = value.strip()
        if not code:
            raise serializers.ValidationError("Enter an authentication or recovery code.")
        return code


class VerifyAuthenticatedTwoFactorSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=6)

    def validate_code(self, value):
        digits_only = "".join(ch for ch in value.strip() if ch.isdigit())
        if len(digits_only) != 6:
            raise serializers.ValidationError("Enter a valid 6-digit code.")
        return digits_only


class BeginTwoFactorEnrollmentSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=128, required=False, allow_blank=True)

    def validate_token(self, value):
        return value.strip()


class ConfirmTwoFactorEnrollmentSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=128, required=False, allow_blank=True)
    code = serializers.CharField(max_length=6)

    def validate_token(self, value):
        return value.strip()

    def validate_code(self, value):
        digits_only = "".join(ch for ch in value.strip() if ch.isdigit())
        if len(digits_only) != 6:
            raise serializers.ValidationError("Enter a valid 6-digit code.")
        return digits_only


class RegenerateTwoFactorRecoveryCodesSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    code = serializers.CharField(max_length=64)

    def validate_current_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate_code(self, value):
        code = value.strip()
        if not code:
            raise serializers.ValidationError("Enter an authentication or recovery code.")
        return code


class TwoFactorEnrollmentSetupSerializer(serializers.Serializer):
    manual_entry_key = serializers.CharField(read_only=True)
    provisioning_uri = serializers.CharField(read_only=True)
    account_name = serializers.CharField(read_only=True)
    issuer = serializers.CharField(read_only=True)
    two_factor_policy = serializers.CharField(read_only=True)
    is_totp_enabled = serializers.BooleanField(read_only=True)

    @classmethod
    def build_response(cls, user):
        issuer = "CCHIS"
        if not user.totp_secret:
            raise serializers.ValidationError("TOTP secret is not available for this user.")
        return {
            "manual_entry_key": user.totp_secret,
            "provisioning_uri": build_totp_provisioning_uri(
                secret=user.totp_secret,
                username=user.username,
                issuer=issuer,
            ),
            "account_name": user.username,
            "issuer": issuer,
            "two_factor_policy": get_two_factor_policy_for_user(user),
            "is_totp_enabled": is_totp_enrolled(user),
        }


class AccessRequestSerializer(serializers.ModelSerializer):
    contact_email = serializers.EmailField()
    phone_number = serializers.CharField(required=False, allow_blank=True, max_length=20)
    county = serializers.CharField(max_length=120)
    administrative_ward = serializers.CharField(max_length=120)
    organization = serializers.CharField(required=False, allow_blank=True, max_length=255)
    message = serializers.CharField(required=False, allow_blank=True)
    website = serializers.CharField(required=False, allow_blank=True, write_only=True, max_length=255)
    client_started_at_ms = serializers.IntegerField(required=False, write_only=True)
    turnstile_token = serializers.CharField(required=False, allow_blank=True, write_only=True, max_length=2048)

    class Meta:
        model = AccessRequest
        fields = [
            "full_name",
            "phone_number",
            "county",
            "administrative_ward",
            "organization",
            "desired_role",
            "contact_email",
            "message",
            "website",
            "client_started_at_ms",
            "turnstile_token",
        ]

    def validate_full_name(self, value):
        return value.strip()

    def validate_phone_number(self, value):
        normalized = normalize_kenyan_phone_number(value)
        if normalized and (not normalized.startswith("+254") or len(normalized) != 13 or not normalized[1:].isdigit()):
            raise serializers.ValidationError("Use +254711000123, 254711000123, or 0711000123.")
        return normalized

    def validate_county(self, value):
        return value.strip()

    def validate_administrative_ward(self, value):
        return value.strip()

    def validate_organization(self, value):
        return value.strip()

    def validate_contact_email(self, value):
        return value.strip().lower()

    def validate_message(self, value):
        return value.strip()

    def validate(self, attrs):
        request = self.context.get("request")
        honeypot_value = (attrs.get("website") or "").strip()
        if honeypot_value:
            security_logger.warning(
                "access_request_honeypot_rejected",
                extra={
                    "event_type": "access_request_honeypot_rejected",
                    "ip_address": get_client_ip(request) if request else None,
                    "request_path": getattr(request, "path", None),
                },
            )
            raise serializers.ValidationError("Unable to process request.")

        client_started_at_ms = attrs.get("client_started_at_ms")
        if client_started_at_ms is not None:
            # Compare against server time to reject suspicious near-instant submissions.
            current_timestamp_ms = int(time.time() * 1000)
            minimum_age_ms = settings.ACCESS_REQUEST_MIN_SUBMISSION_AGE_MS
            if client_started_at_ms > current_timestamp_ms or (current_timestamp_ms - client_started_at_ms) < minimum_age_ms:
                security_logger.warning(
                    "access_request_timing_rejected",
                    extra={
                        "event_type": "access_request_timing_rejected",
                        "reason": "submission_too_fast",
                        "ip_address": get_client_ip(request) if request else None,
                        "request_path": getattr(request, "path", None),
                        "submission_age_ms": current_timestamp_ms - client_started_at_ms,
                        "minimum_age_ms": minimum_age_ms,
                    },
                )
                raise serializers.ValidationError("Unable to process request.")

        county = attrs.get("county", "").strip()
        ward_name = attrs.get("administrative_ward", "").strip()

        if county and ward_name and not Ward.objects.filter(
            county__iexact=county,
            name__iexact=ward_name,
            is_active=True,
        ).exists():
            raise serializers.ValidationError(
                {"administrative_ward": "Select a ward that belongs to the chosen county."}
            )

        return attrs

    def create(self, validated_data):
        validated_data.pop("website", None)
        validated_data.pop("client_started_at_ms", None)
        validated_data.pop("turnstile_token", None)
        return super().create(validated_data)


class AccessRequestAdminSerializer(serializers.ModelSerializer):
    duplicate_email_count = serializers.IntegerField(read_only=True)
    duplicate_phone_count = serializers.IntegerField(read_only=True)
    duplicate_ip_count = serializers.IntegerField(read_only=True)
    pending_related_count = serializers.IntegerField(read_only=True)
    review_flags = serializers.SerializerMethodField()

    class Meta:
        model = AccessRequest
        fields = [
            "id",
            "full_name",
            "phone_number",
            "county",
            "administrative_ward",
            "organization",
            "desired_role",
            "contact_email",
            "message",
            "decision_message",
            "submitted_from_ip",
            "challenge_verified",
            "review_status",
            "submitted_at",
            "reviewed_at",
            "duplicate_email_count",
            "duplicate_phone_count",
            "duplicate_ip_count",
            "pending_related_count",
            "review_flags",
        ]

    def get_review_flags(self, obj):
        flags = []

        if getattr(obj, "duplicate_email_count", 0):
            flags.append("email_reuse")
        if getattr(obj, "duplicate_phone_count", 0):
            flags.append("phone_reuse")
        if getattr(obj, "duplicate_ip_count", 0):
            flags.append("ip_reuse")
        if getattr(obj, "pending_related_count", 0):
            flags.append("related_pending_requests")
        if getattr(obj, "challenge_verified", False):
            flags.append("challenge_verified")

        return flags


class AccessRequestOptionsSerializer(serializers.Serializer):
    counties = serializers.ListField(child=serializers.CharField())
    wards = serializers.ListField(child=serializers.DictField())


class AccessRequestDecisionSerializer(serializers.Serializer):
    message = serializers.CharField(required=False, allow_blank=True, max_length=1000)


class CCHISTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        try:
            refresh = RefreshToken(attrs["refresh"])
        except TokenError as exc:
            raise InvalidToken("Invalid or expired refresh token.") from exc
        user_id = refresh.get("user_id")

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist as exc:
            raise AuthenticationFailed("User not found.", code="user_not_found") from exc

        if not user.is_active:
            raise AuthenticationFailed("User account is inactive.", code="user_inactive")

        return super().validate(attrs)


class CCHISTokenObtainPairSerializer(TokenObtainPairSerializer):
    turnstile_token = serializers.CharField(required=False, allow_blank=True, write_only=True, max_length=2048)

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["username"] = user.username
        token["role"] = user.role
        token["ward_id"] = user.ward_id
        return token

    @classmethod
    def build_token_response(cls, user):
        refresh = cls.get_token(user)
        return {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": UserSerializer(user).data,
            "requires_2fa": False,
        }

    def validate(self, attrs):
        TokenObtainSerializer.validate(self, attrs)

        if user_must_enroll_two_factor(self.user):
            token_record = create_pre_auth_token(self.user)
            return {
                "requires_2fa": False,
                "requires_2fa_enrollment": True,
                "temp_token": token_record.token,
                "detail": "Two-factor enrollment must be completed before dashboard access is granted.",
            }

        if user_requires_two_factor(self.user):
            token_record = create_pre_auth_token(self.user)
            return {
                "requires_2fa": True,
                "requires_2fa_enrollment": False,
                "temp_token": token_record.token,
            }

        data = self.build_token_response(self.user)
        data["requires_2fa_enrollment"] = False
        data["user"]["is_totp_enabled"] = is_totp_enrolled(self.user)
        return data


class AuthAuditEventSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source="actor.username", read_only=True)
    target_username = serializers.CharField(source="target_user.username", read_only=True)
    ward_name = serializers.CharField(source="ward.name", read_only=True)

    class Meta:
        model = AuthAuditEvent
        fields = [
            "id",
            "event_type",
            "status",
            "actor",
            "actor_username",
            "target_user",
            "target_username",
            "ward",
            "ward_name",
            "ip_address",
            "user_agent",
            "metadata",
            "created_at",
        ]


class OwnAuthActivityEventSerializer(serializers.ModelSerializer):
    title = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()

    EVENT_COPY = {
        AuthAuditEvent.EVENT_LOGIN_SUCCESS: (
            "Login successful",
            "Your account signed in successfully.",
        ),
        AuthAuditEvent.EVENT_LOGIN_FAILED: (
            "Login failed",
            "A sign-in attempt for your account failed.",
        ),
        AuthAuditEvent.EVENT_LOGOUT: (
            "Signed out",
            "Your account signed out.",
        ),
        AuthAuditEvent.EVENT_REFRESH_SUCCESS: (
            "Session refreshed",
            "Your dashboard session was refreshed.",
        ),
        AuthAuditEvent.EVENT_REFRESH_FAILED: (
            "Session refresh failed",
            "A dashboard session refresh for your account failed.",
        ),
        AuthAuditEvent.EVENT_PASSWORD_CHANGED: (
            "Password changed",
            "Your account password was changed.",
        ),
        AuthAuditEvent.EVENT_PASSWORD_RESET_COMPLETED: (
            "Password reset completed",
            "Your account password was reset successfully.",
        ),
        AuthAuditEvent.EVENT_2FA_ENROLLMENT_REQUIRED: (
            "Two-factor setup required",
            "Your account was asked to complete two-factor setup.",
        ),
        AuthAuditEvent.EVENT_2FA_ENROLLMENT_STARTED: (
            "Two-factor setup started",
            "Two-factor setup was opened for your account.",
        ),
        AuthAuditEvent.EVENT_2FA_ENROLLMENT_COMPLETED: (
            "Two-factor setup completed",
            "Two-factor authentication was enabled for your account.",
        ),
        AuthAuditEvent.EVENT_2FA_REQUIRED: (
            "Two-factor verification required",
            "Your account was asked for a two-factor verification code.",
        ),
        AuthAuditEvent.EVENT_2FA_VERIFIED: (
            "Two-factor verified",
            "A two-factor challenge for your account was verified.",
        ),
        AuthAuditEvent.EVENT_2FA_FAILED: (
            "Two-factor verification failed",
            "A two-factor verification attempt for your account failed.",
        ),
        AuthAuditEvent.EVENT_2FA_RECOVERY_CODES_GENERATED: (
            "Recovery codes generated",
            "Recovery codes were generated for your account.",
        ),
        AuthAuditEvent.EVENT_2FA_RECOVERY_CODES_REGENERATED: (
            "Recovery codes regenerated",
            "Your account recovery codes were replaced.",
        ),
        AuthAuditEvent.EVENT_2FA_RECOVERY_CODE_USED: (
            "Recovery code used",
            "A recovery code was used for your account.",
        ),
        AuthAuditEvent.EVENT_2FA_RECOVERY_CODE_FAILED: (
            "Recovery code failed",
            "A recovery code verification attempt failed.",
        ),
        AuthAuditEvent.EVENT_2FA_RECOVERY_CODES_LOW: (
            "Recovery codes low",
            "Your account has few unused recovery codes remaining.",
        ),
        AuthAuditEvent.EVENT_POLICY_ACCEPTANCE_REQUIRED: (
            "Policy review required",
            "Your account was asked to review the current CHIS policies.",
        ),
        AuthAuditEvent.EVENT_POLICY_ACCEPTED: (
            "Policies accepted",
            "Your account accepted the current CHIS Terms, Privacy Policy, and Cookie Notice.",
        ),
        AuthAuditEvent.EVENT_USER_CREATED: (
            "Account created",
            "Your user account was created.",
        ),
        AuthAuditEvent.EVENT_USER_DEACTIVATED: (
            "Account deactivated",
            "Your user account was deactivated.",
        ),
        AuthAuditEvent.EVENT_USER_REACTIVATED: (
            "Account reactivated",
            "Your user account was reactivated.",
        ),
    }

    class Meta:
        model = AuthAuditEvent
        fields = [
            "id",
            "event_type",
            "status",
            "title",
            "description",
            "created_at",
        ]

    def get_title(self, obj):
        return self.EVENT_COPY.get(
            obj.event_type,
            (obj.get_event_type_display(), ""),
        )[0]

    def get_description(self, obj):
        default_description = f"{obj.get_event_type_display()} was recorded for your account."
        return self.EVENT_COPY.get(obj.event_type, ("", default_description))[1]


class OwnAuthActivityQuerySerializer(serializers.Serializer):
    page = serializers.IntegerField(required=False, min_value=1)
    page_size = serializers.IntegerField(required=False, min_value=1)
    event_type = serializers.ChoiceField(
        choices=[choice[0] for choice in AuthAuditEvent.EVENT_CHOICES],
        required=False,
        allow_blank=True,
    )
    status = serializers.ChoiceField(
        choices=[choice[0] for choice in AuthAuditEvent.STATUS_CHOICES],
        required=False,
        allow_blank=True,
    )
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    security_only = serializers.BooleanField(required=False, default=True)
    include_refresh_events = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        date_from = attrs.get("date_from")
        date_to = attrs.get("date_to")

        if date_from and date_to and date_to < date_from:
            raise serializers.ValidationError(
                {"date_to": "Date to must be the same as or later than date from."}
            )

        return attrs
