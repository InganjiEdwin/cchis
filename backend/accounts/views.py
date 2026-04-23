import logging

from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.cache import cache
from django.db import models
from django.db.models import Count, IntegerField, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import generics, permissions
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import get_object_or_404
from rest_framework import status
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .audit import get_client_ip, record_auth_event
from .models import AccessRequest, AuthAuditEvent, PasswordResetToken
from .services import (
    create_password_reset_token,
    send_access_request_acknowledgement,
    send_access_request_decision,
    send_password_reset_email,
)
from .permissions import IsAdminOnly
from .serializers import (
    BeginTwoFactorEnrollmentSerializer,
    CCHISTokenRefreshSerializer,
    CCHISTokenObtainPairSerializer,
    ChangePasswordSerializer,
    ConfirmTwoFactorEnrollmentSerializer,
    RegisterSerializer,
    AuthAuditEventSerializer,
    UserAppearanceSerializer,
    UserSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
    VerifyTwoFactorSerializer,
    AccessRequestSerializer,
    AccessRequestAdminSerializer,
    AccessRequestOptionsSerializer,
    AccessRequestDecisionSerializer,
    TwoFactorEnrollmentSetupSerializer,
)
from .turnstile import is_turnstile_enabled, verify_turnstile_token
from .two_factor import (
    consume_pre_auth_token,
    generate_totp_secret,
    get_pre_auth_token,
    get_two_factor_policy_for_user,
    is_totp_enrolled,
    user_requires_two_factor,
    verify_totp_code,
)


User = get_user_model()
security_logger = logging.getLogger("accounts.security")


def get_refresh_cookie_name() -> str:
    return getattr(settings, "AUTH_REFRESH_COOKIE_NAME", "cchis_refresh")


def get_refresh_cookie_value(request) -> str:
    return str(request.COOKIES.get(get_refresh_cookie_name()) or "")


def set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=get_refresh_cookie_name(),
        value=refresh_token,
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        httponly=getattr(settings, "AUTH_REFRESH_COOKIE_HTTPONLY", True),
        secure=getattr(settings, "AUTH_REFRESH_COOKIE_SECURE", False),
        samesite=getattr(settings, "AUTH_REFRESH_COOKIE_SAMESITE", "Lax"),
        path=getattr(settings, "AUTH_REFRESH_COOKIE_PATH", "/"),
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=get_refresh_cookie_name(),
        path=getattr(settings, "AUTH_REFRESH_COOKIE_PATH", "/"),
        samesite=getattr(settings, "AUTH_REFRESH_COOKIE_SAMESITE", "Lax"),
    )


def build_session_response(*, authenticated: bool, user=None, access_token: str | None = None, session_source: str | None = None) -> Response:
    payload = {
        "authenticated": authenticated,
        "user": UserSerializer(user).data if user else None,
        "access": access_token,
        "session_source": session_source,
    }
    return Response(payload, status=status.HTTP_200_OK)


def build_login_attempt_key(request, username: str) -> str:
    client_ip = get_client_ip(request) or "unknown"
    normalized_username = username.strip().lower() or "blank"
    return f"auth:login_attempts:{client_ip}:{normalized_username}"


def build_login_cooldown_key(request, username: str) -> str:
    client_ip = get_client_ip(request) or "unknown"
    normalized_username = username.strip().lower() or "blank"
    return f"auth:login_cooldown:{client_ip}:{normalized_username}"


def get_failed_login_attempts(request, username: str) -> int:
    return int(cache.get(build_login_attempt_key(request, username), 0) or 0)


def register_failed_login_attempt(request, username: str) -> None:
    attempts_key = build_login_attempt_key(request, username)
    cooldown_key = build_login_cooldown_key(request, username)
    attempts = cache.get(attempts_key, 0) + 1
    cache.set(attempts_key, attempts, timeout=settings.AUTH_LOGIN_FAILURE_WINDOW_SECONDS)

    if attempts >= settings.AUTH_LOGIN_FAILURE_LIMIT:
        cache.set(cooldown_key, True, timeout=settings.AUTH_LOGIN_COOLDOWN_SECONDS)
        cache.delete(attempts_key)


def clear_failed_login_attempts(request, username: str) -> None:
    cache.delete(build_login_attempt_key(request, username))
    cache.delete(build_login_cooldown_key(request, username))


def is_login_cooldown_active(request, username: str) -> bool:
    return bool(cache.get(build_login_cooldown_key(request, username)))


def is_login_turnstile_required(request, username: str) -> bool:
    if not getattr(settings, "AUTH_LOGIN_TURNSTILE_ENABLED", False):
        return False

    threshold = max(1, int(getattr(settings, "AUTH_LOGIN_TURNSTILE_THRESHOLD", 3)))
    return get_failed_login_attempts(request, username) >= threshold


def build_two_factor_attempt_key(request, user_id: int | None) -> str:
    client_ip = get_client_ip(request) or "unknown"
    user_component = str(user_id or "anonymous")
    return f"auth:2fa_attempts:{client_ip}:{user_component}"


def build_two_factor_cooldown_key(request, user_id: int | None) -> str:
    client_ip = get_client_ip(request) or "unknown"
    user_component = str(user_id or "anonymous")
    return f"auth:2fa_cooldown:{client_ip}:{user_component}"


def register_failed_two_factor_attempt(request, user_id: int | None) -> None:
    attempts_key = build_two_factor_attempt_key(request, user_id)
    cooldown_key = build_two_factor_cooldown_key(request, user_id)
    attempts = cache.get(attempts_key, 0) + 1
    cache.set(attempts_key, attempts, timeout=settings.AUTH_2FA_FAILURE_WINDOW_SECONDS)

    if attempts >= settings.AUTH_2FA_FAILURE_LIMIT:
        cache.set(cooldown_key, True, timeout=settings.AUTH_2FA_COOLDOWN_SECONDS)
        cache.delete(attempts_key)


def clear_failed_two_factor_attempts(request, user_id: int | None) -> None:
    cache.delete(build_two_factor_attempt_key(request, user_id))
    cache.delete(build_two_factor_cooldown_key(request, user_id))


def is_two_factor_cooldown_active(request, user_id: int | None) -> bool:
    return bool(cache.get(build_two_factor_cooldown_key(request, user_id)))


def build_refresh_attempt_key(request, token_fingerprint: str) -> str:
    client_ip = get_client_ip(request) or "unknown"
    normalized_fingerprint = token_fingerprint or "blank"
    return f"auth:refresh_attempts:{client_ip}:{normalized_fingerprint}"


def build_refresh_cooldown_key(request, token_fingerprint: str) -> str:
    client_ip = get_client_ip(request) or "unknown"
    normalized_fingerprint = token_fingerprint or "blank"
    return f"auth:refresh_cooldown:{client_ip}:{normalized_fingerprint}"


def register_failed_refresh_attempt(request, token_fingerprint: str) -> None:
    attempts_key = build_refresh_attempt_key(request, token_fingerprint)
    cooldown_key = build_refresh_cooldown_key(request, token_fingerprint)
    attempts = cache.get(attempts_key, 0) + 1
    cache.set(attempts_key, attempts, timeout=settings.AUTH_REFRESH_FAILURE_WINDOW_SECONDS)

    if attempts >= settings.AUTH_REFRESH_FAILURE_LIMIT:
        cache.set(cooldown_key, True, timeout=settings.AUTH_REFRESH_COOLDOWN_SECONDS)
        cache.delete(attempts_key)


def clear_failed_refresh_attempts(request, token_fingerprint: str) -> None:
    cache.delete(build_refresh_attempt_key(request, token_fingerprint))
    cache.delete(build_refresh_cooldown_key(request, token_fingerprint))


def is_refresh_cooldown_active(request, token_fingerprint: str) -> bool:
    return bool(cache.get(build_refresh_cooldown_key(request, token_fingerprint)))


def fingerprint_refresh_token(token_value: str) -> str:
    token_value = token_value.strip()
    if not token_value:
        return "blank"
    return token_value[:12]


def with_access_request_review_signals(queryset):
    email_duplicate_count = (
        AccessRequest.objects.filter(contact_email__iexact=OuterRef("contact_email"))
        .exclude(pk=OuterRef("pk"))
        .values("contact_email")
        .annotate(total=Count("id"))
        .values("total")[:1]
    )
    phone_duplicate_count = (
        AccessRequest.objects.filter(phone_number=OuterRef("phone_number"))
        .exclude(pk=OuterRef("pk"))
        .exclude(phone_number="")
        .values("phone_number")
        .annotate(total=Count("id"))
        .values("total")[:1]
    )
    ip_duplicate_count = (
        AccessRequest.objects.filter(submitted_from_ip=OuterRef("submitted_from_ip"))
        .exclude(pk=OuterRef("pk"))
        .exclude(submitted_from_ip__isnull=True)
        .values("submitted_from_ip")
        .annotate(total=Count("id"))
        .values("total")[:1]
    )
    pending_peer_count = (
        AccessRequest.objects.filter(
            review_status=AccessRequest.STATUS_PENDING,
        )
        .filter(
            Q(contact_email__iexact=OuterRef("contact_email"))
            | (Q(phone_number=OuterRef("phone_number")) & ~Q(phone_number=""))
        )
        .exclude(pk=OuterRef("pk"))
        .values("review_status")
        .annotate(total=Count("id"))
        .values("total")[:1]
    )

    return queryset.annotate(
        duplicate_email_count=Coalesce(Subquery(email_duplicate_count, output_field=IntegerField()), Value(0)),
        duplicate_phone_count=Coalesce(Subquery(phone_duplicate_count, output_field=IntegerField()), Value(0)),
        duplicate_ip_count=Coalesce(Subquery(ip_duplicate_count, output_field=IntegerField()), Value(0)),
        pending_related_count=Coalesce(Subquery(pending_peer_count, output_field=IntegerField()), Value(0)),
    )


class RegisterAPIView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [IsAdminOnly]
    throttle_scope = "auth_write"

    def perform_create(self, serializer):
        user = serializer.save()
        record_auth_event(
            request=self.request,
            event_type=AuthAuditEvent.EVENT_USER_CREATED,
            status=AuthAuditEvent.STATUS_SUCCESS,
            actor=self.request.user,
            target_user=user,
            metadata={"role": user.role},
        )


class LoginAPIView(TokenObtainPairView):
    serializer_class = CCHISTokenObtainPairSerializer
    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth_login"

    def post(self, request, *args, **kwargs):
        username = str(request.data.get("username", "")).strip()
        user = User.objects.filter(username=username).first()

        if is_login_cooldown_active(request, username):
            security_logger.warning(
                "auth_login_cooldown_triggered",
                extra={
                    "event_type": "auth_login_cooldown_triggered",
                    "ip_address": get_client_ip(request),
                    "request_path": getattr(request, "path", None),
                    "username": username,
                },
            )
            record_auth_event(
                request=request,
                event_type=AuthAuditEvent.EVENT_LOGIN_FAILED,
                status=AuthAuditEvent.STATUS_FAILED,
                target_user=user,
                metadata={"username": username, "reason": "cooldown_active"},
            )
            return Response(
                {"detail": "Too many sign-in attempts. Please wait and try again."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        if is_login_turnstile_required(request, username):
            turnstile_token = str(request.data.get("turnstile_token", "")).strip()
            if not turnstile_token:
                security_logger.warning(
                    "auth_login_turnstile_required",
                    extra={
                        "event_type": "auth_login_turnstile_required",
                        "reason": "missing_token",
                        "ip_address": get_client_ip(request),
                        "request_path": getattr(request, "path", None),
                        "username": username,
                    },
                )
                record_auth_event(
                    request=request,
                    event_type=AuthAuditEvent.EVENT_LOGIN_FAILED,
                    status=AuthAuditEvent.STATUS_FAILED,
                    target_user=user,
                    metadata={"username": username, "reason": "turnstile_required"},
                )
                return Response(
                    {"detail": "Additional verification is required. Complete the challenge and try again."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            verification = verify_turnstile_token(turnstile_token, remote_ip=get_client_ip(request))
            if not verification.success:
                security_logger.warning(
                    "auth_login_turnstile_rejected",
                    extra={
                        "event_type": "auth_login_turnstile_rejected",
                        "reason": "invalid_token",
                        "ip_address": get_client_ip(request),
                        "request_path": getattr(request, "path", None),
                        "username": username,
                        "error_codes": list(verification.error_codes),
                    },
                )
                record_auth_event(
                    request=request,
                    event_type=AuthAuditEvent.EVENT_LOGIN_FAILED,
                    status=AuthAuditEvent.STATUS_FAILED,
                    target_user=user,
                    metadata={
                        "username": username,
                        "reason": "turnstile_failed",
                        "turnstile_error_codes": list(verification.error_codes),
                    },
                )
                return Response(
                    {"detail": "Additional verification is required. Complete the challenge and try again."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        serializer = self.get_serializer(data=request.data)

        try:
            serializer.is_valid(raise_exception=True)
        except Exception:
            register_failed_login_attempt(request, username)
            security_logger.warning(
                "auth_login_failed",
                extra={
                    "event_type": "auth_login_failed",
                    "reason": "invalid_credentials",
                    "ip_address": get_client_ip(request),
                    "request_path": getattr(request, "path", None),
                    "username": username,
                },
            )
            record_auth_event(
                request=request,
                event_type=AuthAuditEvent.EVENT_LOGIN_FAILED,
                status=AuthAuditEvent.STATUS_FAILED,
                target_user=user,
                metadata={"username": username, "reason": "invalid_credentials"},
            )
            raise AuthenticationFailed("Unable to sign in with those credentials.")

        user = serializer.user
        clear_failed_login_attempts(request, username)
        if serializer.validated_data.get("requires_2fa_enrollment"):
            record_auth_event(
                request=request,
                event_type=AuthAuditEvent.EVENT_2FA_ENROLLMENT_REQUIRED,
                status=AuthAuditEvent.STATUS_SUCCESS,
                actor=user,
                target_user=user,
                metadata={"username": username},
            )
        if serializer.validated_data.get("requires_2fa"):
            record_auth_event(
                request=request,
                event_type=AuthAuditEvent.EVENT_2FA_REQUIRED,
                status=AuthAuditEvent.STATUS_SUCCESS,
                actor=user,
                target_user=user,
            )
        else:
            record_auth_event(
                request=request,
                event_type=AuthAuditEvent.EVENT_LOGIN_SUCCESS,
                status=AuthAuditEvent.STATUS_SUCCESS,
                actor=user,
                target_user=user,
            )

        response = Response(serializer.validated_data, status=status.HTTP_200_OK)

        refresh_token = serializer.validated_data.get("refresh")
        if refresh_token:
            set_refresh_cookie(response, refresh_token)

        return response


class RefreshAPIView(TokenRefreshView):
    permission_classes = [permissions.AllowAny]
    serializer_class = CCHISTokenRefreshSerializer
    throttle_scope = "auth_refresh"

    def post(self, request, *args, **kwargs):
        refresh_token = get_refresh_cookie_value(request)
        refresh_fingerprint = fingerprint_refresh_token(str(refresh_token))
        user = None

        if not refresh_token:
            response = Response(
                {"detail": "Refresh session is missing or expired."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
            clear_refresh_cookie(response)
            return response

        if is_refresh_cooldown_active(request, refresh_fingerprint):
            record_auth_event(
                request=request,
                event_type=AuthAuditEvent.EVENT_REFRESH_FAILED,
                status=AuthAuditEvent.STATUS_FAILED,
                actor=user,
                target_user=user,
                metadata={"reason": "cooldown_active"},
            )
            return Response(
                {"detail": "Too many token refresh attempts. Please wait and try again."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                user = User.objects.filter(id=token.get("user_id")).first()
            except TokenError:
                user = None

        serializer = self.get_serializer(data={"refresh": refresh_token})

        try:
            serializer.is_valid(raise_exception=True)
        except Exception:
            register_failed_refresh_attempt(request, refresh_fingerprint)
            record_auth_event(
                request=request,
                event_type=AuthAuditEvent.EVENT_REFRESH_FAILED,
                status=AuthAuditEvent.STATUS_FAILED,
                actor=user,
                target_user=user,
                metadata={"reason": "invalid_refresh"},
            )
            response = Response(
                {"detail": "Invalid or expired refresh token."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
            clear_refresh_cookie(response)
            return response

        clear_failed_refresh_attempts(request, refresh_fingerprint)
        record_auth_event(
            request=request,
            event_type=AuthAuditEvent.EVENT_REFRESH_SUCCESS,
            status=AuthAuditEvent.STATUS_SUCCESS,
            actor=user,
            target_user=user,
        )

        response = Response(serializer.validated_data, status=status.HTTP_200_OK)
        issued_refresh = serializer.validated_data.get("refresh") or refresh_token
        if issued_refresh:
            set_refresh_cookie(response, issued_refresh)
        return response


class MeAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        serializer = UserAppearanceSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserSerializer(request.user).data, status=status.HTTP_200_OK)


class SessionAPIView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        jwt_authenticator = JWTAuthentication()
        authorization_header = request.META.get("HTTP_AUTHORIZATION")

        if authorization_header:
            try:
                auth_result = jwt_authenticator.authenticate(request)
            except AuthenticationFailed:
                auth_result = None

            if auth_result:
                user, _ = auth_result
                return build_session_response(
                    authenticated=True,
                    user=user,
                    session_source="access",
                )

        refresh_token = request.COOKIES.get(get_refresh_cookie_name())
        refresh_fingerprint = fingerprint_refresh_token(refresh_token or "")

        if not refresh_token:
            return build_session_response(authenticated=False)

        if is_refresh_cooldown_active(request, refresh_fingerprint):
            response = build_session_response(authenticated=False)
            clear_refresh_cookie(response)
            return response

        try:
            refresh = RefreshToken(refresh_token)
            refresh.check_blacklist()
            access_token = str(refresh.access_token)
            user = get_object_or_404(User, id=refresh["user_id"])
        except TokenError:
            register_failed_refresh_attempt(request, refresh_fingerprint)
            response = build_session_response(authenticated=False)
            clear_refresh_cookie(response)
            return response
        except AuthenticationFailed:
            register_failed_refresh_attempt(request, refresh_fingerprint)
            response = build_session_response(authenticated=False)
            clear_refresh_cookie(response)
            return response

        clear_failed_refresh_attempts(request, refresh_fingerprint)
        record_auth_event(
            request=request,
            event_type=AuthAuditEvent.EVENT_REFRESH_SUCCESS,
            status=AuthAuditEvent.STATUS_SUCCESS,
            actor=user,
            target_user=user,
            metadata={"source": "session_bootstrap"},
        )

        response = build_session_response(
            authenticated=True,
            user=user,
            access_token=access_token,
            session_source="refresh",
        )
        return response


class VerifyTwoFactorAPIView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth_2fa"

    def post(self, request):
        serializer = VerifyTwoFactorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        token_record = get_pre_auth_token(serializer.validated_data["token"])
        if not token_record:
            return Response(
                {"detail": "Invalid or expired 2FA token."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = token_record.user
        if is_two_factor_cooldown_active(request, user.id):
            record_auth_event(
                request=request,
                event_type=AuthAuditEvent.EVENT_2FA_FAILED,
                status=AuthAuditEvent.STATUS_FAILED,
                actor=user,
                target_user=user,
                metadata={"reason": "cooldown_active"},
            )
            return Response(
                {"detail": "Too many verification attempts. Please wait and try again."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        if not user_requires_two_factor(user):
            return Response(
                {"detail": "Two-factor verification is not required for this session."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not verify_totp_code(user.totp_secret, serializer.validated_data["code"]):
            register_failed_two_factor_attempt(request, user.id)
            record_auth_event(
                request=request,
                event_type=AuthAuditEvent.EVENT_2FA_FAILED,
                status=AuthAuditEvent.STATUS_FAILED,
                actor=user,
                target_user=user,
                metadata={"reason": "invalid_code"},
            )
            return Response(
                {"detail": "Invalid or expired code. Please try again."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        consume_pre_auth_token(token_record)
        clear_failed_two_factor_attempts(request, user.id)
        token_response = CCHISTokenObtainPairSerializer.build_token_response(user)
        record_auth_event(
            request=request,
            event_type=AuthAuditEvent.EVENT_2FA_VERIFIED,
            status=AuthAuditEvent.STATUS_SUCCESS,
            actor=user,
            target_user=user,
        )
        record_auth_event(
            request=request,
            event_type=AuthAuditEvent.EVENT_LOGIN_SUCCESS,
            status=AuthAuditEvent.STATUS_SUCCESS,
            actor=user,
            target_user=user,
        )
        response = Response(token_response, status=status.HTTP_200_OK)
        set_refresh_cookie(response, token_response["refresh"])
        return response


class BeginTwoFactorEnrollmentAPIView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth_2fa"

    def post(self, request):
        serializer = BeginTwoFactorEnrollmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        token_value = serializer.validated_data.get("token", "")
        token_record = get_pre_auth_token(token_value) if token_value else None
        user = request.user if getattr(request.user, "is_authenticated", False) else token_record.user if token_record else None

        if not user:
            return Response({"detail": "Authentication or a valid enrollment token is required."}, status=status.HTTP_401_UNAUTHORIZED)

        if get_two_factor_policy_for_user(user) == "NONE":
            return Response({"detail": "Two-factor enrollment is not available for this account."}, status=status.HTTP_400_BAD_REQUEST)

        if is_totp_enrolled(user):
            return Response(TwoFactorEnrollmentSetupSerializer.build_response(user), status=status.HTTP_200_OK)

        if not user.totp_secret:
            user.totp_secret = generate_totp_secret()
            user.save(update_fields=["totp_secret"])

        record_auth_event(
            request=request,
            event_type=AuthAuditEvent.EVENT_2FA_ENROLLMENT_STARTED,
            status=AuthAuditEvent.STATUS_SUCCESS,
            actor=user if getattr(request.user, "is_authenticated", False) else None,
            target_user=user,
        )
        return Response(TwoFactorEnrollmentSetupSerializer.build_response(user), status=status.HTTP_200_OK)


class ConfirmTwoFactorEnrollmentAPIView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth_2fa"

    def post(self, request):
        serializer = ConfirmTwoFactorEnrollmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        token_value = serializer.validated_data.get("token", "")
        token_record = get_pre_auth_token(token_value) if token_value else None
        user = request.user if getattr(request.user, "is_authenticated", False) else token_record.user if token_record else None

        if not user:
            return Response({"detail": "Authentication or a valid enrollment token is required."}, status=status.HTTP_401_UNAUTHORIZED)

        if not user.totp_secret:
            return Response({"detail": "Two-factor setup has not been started for this account."}, status=status.HTTP_400_BAD_REQUEST)

        if not verify_totp_code(user.totp_secret, serializer.validated_data["code"]):
            record_auth_event(
                request=request,
                event_type=AuthAuditEvent.EVENT_2FA_FAILED,
                status=AuthAuditEvent.STATUS_FAILED,
                actor=user if getattr(request.user, "is_authenticated", False) else None,
                target_user=user,
            )
            return Response({"detail": "Invalid or expired code. Please try again."}, status=status.HTTP_400_BAD_REQUEST)

        user.is_totp_enabled = True
        user.save(update_fields=["is_totp_enabled"])
        record_auth_event(
            request=request,
            event_type=AuthAuditEvent.EVENT_2FA_ENROLLMENT_COMPLETED,
            status=AuthAuditEvent.STATUS_SUCCESS,
            actor=user if getattr(request.user, "is_authenticated", False) else None,
            target_user=user,
        )

        if token_record:
            consume_pre_auth_token(token_record)
            token_response = CCHISTokenObtainPairSerializer.build_token_response(user)
            token_response["enrollment_completed"] = True
            response = Response(token_response, status=status.HTTP_200_OK)
            set_refresh_cookie(response, token_response["refresh"])
            return response

        return Response(
            {
                "detail": "Two-factor enrollment completed successfully.",
                "user": UserSerializer(user).data,
                "enrollment_completed": True,
            },
            status=status.HTTP_200_OK,
        )


class LogoutAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "auth_write"

    def post(self, request):
        refresh_token = get_refresh_cookie_value(request)

        if not refresh_token:
            response = Response(
                {"detail": "Refresh session is missing or expired."},
                status=status.HTTP_400_BAD_REQUEST,
            )
            clear_refresh_cookie(response)
            return response

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError:
            record_auth_event(
                request=request,
                event_type=AuthAuditEvent.EVENT_LOGOUT,
                status=AuthAuditEvent.STATUS_FAILED,
                actor=request.user,
                target_user=request.user,
            )
            response = Response(
                {"detail": "Invalid or expired refresh token."},
                status=400,
            )
            clear_refresh_cookie(response)
            return response

        record_auth_event(
            request=request,
            event_type=AuthAuditEvent.EVENT_LOGOUT,
            status=AuthAuditEvent.STATUS_SUCCESS,
            actor=request.user,
            target_user=request.user,
        )
        response = Response(status=205)
        clear_refresh_cookie(response)
        return response


def blacklist_user_refresh_tokens(user):
    for token in user.outstandingtoken_set.all():
        BlacklistedToken.objects.get_or_create(token=token)


class ChangePasswordAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "auth_write"

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=["password"])
        blacklist_user_refresh_tokens(request.user)
        record_auth_event(
            request=request,
            event_type=AuthAuditEvent.EVENT_PASSWORD_CHANGED,
            status=AuthAuditEvent.STATUS_SUCCESS,
            actor=request.user,
            target_user=request.user,
        )

        return Response({"detail": "Password changed successfully."}, status=status.HTTP_200_OK)


class PasswordResetRequestAPIView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth_recovery"

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        identifier = serializer.validated_data["identifier"]
        user = User.objects.filter(is_active=True).filter(
            models.Q(username__iexact=identifier) | models.Q(email__iexact=identifier)
        ).first()

        if user and user.email:
            token_record = create_password_reset_token(user)
            send_password_reset_email(user, token_record)

        return Response(
            {
                "detail": "If the account exists and is eligible for recovery, password reset instructions will be sent."
            },
            status=status.HTTP_200_OK,
        )


class PasswordResetConfirmAPIView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth_recovery"

    def get(self, request):
        token_value = str(request.query_params.get("token", "")).strip()
        token_record = PasswordResetToken.objects.select_related("user").filter(token=token_value).first()

        if not token_record or not token_record.is_usable:
            return Response(
                {"detail": "Invalid or expired reset token.", "valid": False},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"detail": "Reset token is valid.", "valid": True}, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        token_value = serializer.validated_data["token"]
        token_record = PasswordResetToken.objects.select_related("user").filter(token=token_value).first()
        if not token_record or not token_record.is_usable:
            return Response(
                {"detail": "Invalid or expired reset token."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = token_record.user
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        token_record.used_at = timezone.now()
        token_record.save(update_fields=["used_at"])
        blacklist_user_refresh_tokens(user)
        record_auth_event(
            request=request,
            event_type=AuthAuditEvent.EVENT_PASSWORD_RESET_COMPLETED,
            status=AuthAuditEvent.STATUS_SUCCESS,
            actor=user,
            target_user=user,
        )

        return Response({"detail": "Password reset successfully."}, status=status.HTTP_200_OK)


class AccessRequestAPIView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = "access_request"

    def post(self, request):
        serializer = AccessRequestSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        challenge_verified = False

        if is_turnstile_enabled():
            turnstile_token = str(serializer.validated_data.get("turnstile_token", "")).strip()
            if not turnstile_token:
                security_logger.warning(
                    "access_request_turnstile_rejected",
                    extra={
                        "event_type": "access_request_turnstile_rejected",
                        "reason": "missing_token",
                        "ip_address": get_client_ip(request),
                        "request_path": getattr(request, "path", None),
                    },
                )
                return Response(
                    {"detail": "Challenge verification failed. Please try again."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            challenge_verified = True

            verification = verify_turnstile_token(
                turnstile_token,
                remote_ip=get_client_ip(request),
            )
            if not verification.success:
                security_logger.warning(
                    "access_request_turnstile_rejected",
                    extra={
                        "event_type": "access_request_turnstile_rejected",
                        "reason": "verification_failed",
                        "ip_address": get_client_ip(request),
                        "request_path": getattr(request, "path", None),
                        "error_codes": verification.error_codes,
                        "hostname": verification.hostname,
                    },
                )
                return Response(
                    {"detail": "Challenge verification failed. Please try again."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        duplicate_window_start = timezone.now() - timezone.timedelta(
            hours=settings.ACCESS_REQUEST_DUPLICATE_WINDOW_HOURS
        )
        contact_email = serializer.validated_data["contact_email"]
        phone_number = serializer.validated_data.get("phone_number", "")
        desired_role = serializer.validated_data["desired_role"]

        duplicate_filters = models.Q(contact_email__iexact=contact_email)
        if phone_number:
            duplicate_filters |= models.Q(phone_number=phone_number)

        existing_request = (
            AccessRequest.objects.filter(
                duplicate_filters,
                desired_role=desired_role,
                review_status=AccessRequest.STATUS_PENDING,
                submitted_at__gte=duplicate_window_start,
            )
            .order_by("-submitted_at")
            .first()
        )

        if existing_request:
            security_logger.info(
                "access_request_duplicate_suppressed",
                extra={
                    "event_type": "access_request_duplicate_suppressed",
                    "ip_address": get_client_ip(request),
                    "request_path": getattr(request, "path", None),
                    "contact_email": contact_email,
                    "has_phone_number": bool(phone_number),
                    "desired_role": desired_role,
                    "existing_request_id": existing_request.id,
                },
            )
            return Response(
                {
                    "detail": "Access request submitted successfully.",
                    "review_status": existing_request.review_status,
                },
                status=status.HTTP_200_OK,
            )

        access_request = serializer.save(
            submitted_from_ip=get_client_ip(request),
            challenge_verified=challenge_verified,
        )
        security_logger.info(
            "access_request_created",
            extra={
                "event_type": "access_request_created",
                "ip_address": get_client_ip(request),
                "request_path": getattr(request, "path", None),
                "access_request_id": access_request.id,
                "desired_role": access_request.desired_role,
                "county": access_request.county,
            },
        )
        send_access_request_acknowledgement(access_request)

        return Response(
            {
                "detail": "Access request submitted successfully.",
                "review_status": access_request.review_status,
            },
            status=status.HTTP_201_CREATED,
        )


class AccessRequestOptionsAPIView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = "access_request"

    def get(self, request):
        from risk.models import Ward

        active_wards = Ward.objects.filter(is_active=True).order_by("county", "name")
        counties = sorted({ward.county for ward in active_wards if ward.county})
        wards = [
            {
                "id": ward.id,
                "name": ward.name,
                "county": ward.county,
                "sub_county": ward.sub_county,
            }
            for ward in active_wards
        ]

        serializer = AccessRequestOptionsSerializer(
            {
                "counties": counties,
                "wards": wards,
            }
        )
        return Response(serializer.data, status=status.HTTP_200_OK)


class AccessRequestListAPIView(generics.ListAPIView):
    serializer_class = AccessRequestAdminSerializer
    permission_classes = [IsAdminOnly]
    throttle_scope = "auth_write"
    filter_backends = [OrderingFilter]
    ordering_fields = ["submitted_at", "review_status", "desired_role", "contact_email"]
    ordering = ["-submitted_at"]

    def get_queryset(self):
        queryset = with_access_request_review_signals(AccessRequest.objects.all())
        review_status = self.request.query_params.get("review_status")
        desired_role = self.request.query_params.get("desired_role")

        if review_status:
            queryset = queryset.filter(review_status=review_status.upper())
        if desired_role:
            queryset = queryset.filter(desired_role=desired_role.upper())

        return queryset


class AccessRequestApproveAPIView(APIView):
    permission_classes = [IsAdminOnly]
    throttle_scope = "auth_write"

    def post(self, request, request_id: int):
        access_request = get_object_or_404(AccessRequest, id=request_id)
        if access_request.review_status != AccessRequest.STATUS_PENDING:
            return Response(
                {"detail": "Only pending access requests can be approved."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = AccessRequestDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        decision_message = serializer.validated_data.get("message", "")

        access_request.review_status = AccessRequest.STATUS_APPROVED
        access_request.decision_message = decision_message
        access_request.reviewed_at = timezone.now()
        access_request.save(update_fields=["review_status", "decision_message", "reviewed_at"])
        send_access_request_decision(
            access_request,
            approved=True,
            decision_message=decision_message,
        )

        return Response(
            {"detail": "Access request approved successfully."},
            status=status.HTTP_200_OK,
        )


class AccessRequestRejectAPIView(APIView):
    permission_classes = [IsAdminOnly]
    throttle_scope = "auth_write"

    def post(self, request, request_id: int):
        access_request = get_object_or_404(AccessRequest, id=request_id)
        if access_request.review_status != AccessRequest.STATUS_PENDING:
            return Response(
                {"detail": "Only pending access requests can be rejected."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = AccessRequestDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        decision_message = serializer.validated_data.get("message", "")

        access_request.review_status = AccessRequest.STATUS_REJECTED
        access_request.decision_message = decision_message
        access_request.reviewed_at = timezone.now()
        access_request.save(update_fields=["review_status", "decision_message", "reviewed_at"])
        send_access_request_decision(
            access_request,
            approved=False,
            decision_message=decision_message,
        )

        return Response(
            {"detail": "Access request rejected successfully."},
            status=status.HTTP_200_OK,
        )


class DeactivateUserAPIView(APIView):
    permission_classes = [IsAdminOnly]
    throttle_scope = "auth_write"

    def post(self, request, user_id: int):
        user = get_object_or_404(User, id=user_id)
        user.is_active = False
        user.save(update_fields=["is_active"])
        blacklist_user_refresh_tokens(user)
        record_auth_event(
            request=request,
            event_type=AuthAuditEvent.EVENT_USER_DEACTIVATED,
            status=AuthAuditEvent.STATUS_SUCCESS,
            actor=request.user,
            target_user=user,
        )
        return Response({"detail": "User deactivated successfully."}, status=status.HTTP_200_OK)


class ReactivateUserAPIView(APIView):
    permission_classes = [IsAdminOnly]
    throttle_scope = "auth_write"

    def post(self, request, user_id: int):
        user = get_object_or_404(User, id=user_id)
        user.is_active = True
        user.save(update_fields=["is_active"])
        record_auth_event(
            request=request,
            event_type=AuthAuditEvent.EVENT_USER_REACTIVATED,
            status=AuthAuditEvent.STATUS_SUCCESS,
            actor=request.user,
            target_user=user,
        )
        return Response({"detail": "User reactivated successfully."}, status=status.HTTP_200_OK)


class AuthAuditEventListAPIView(generics.ListAPIView):
    serializer_class = AuthAuditEventSerializer
    permission_classes = [IsAdminOnly]
    throttle_scope = "auth_write"
    filter_backends = [OrderingFilter]
    ordering_fields = ["created_at", "event_type", "status", "ip_address"]
    ordering = ["-created_at"]

    def get_queryset(self):
        queryset = AuthAuditEvent.objects.select_related("actor", "target_user", "ward").all()

        event_type = self.request.query_params.get("event_type")
        status_value = self.request.query_params.get("status")
        username = self.request.query_params.get("username")
        ward_id = self.request.query_params.get("ward_id")

        if event_type:
            queryset = queryset.filter(event_type=event_type)
        if status_value:
            queryset = queryset.filter(status=status_value)
        if username:
            queryset = queryset.filter(target_user__username=username)
        if ward_id:
            queryset = queryset.filter(ward_id=ward_id)

        return queryset


class AuthAuditSummaryAPIView(APIView):
    permission_classes = [IsAdminOnly]
    throttle_scope = "auth_write"

    def get(self, request):
        queryset = AuthAuditEvent.objects.all()

        event_type = request.query_params.get("event_type")
        status_value = request.query_params.get("status")

        if event_type:
            queryset = queryset.filter(event_type=event_type)
        if status_value:
            queryset = queryset.filter(status=status_value)

        total_events = queryset.count()
        recent_failures = queryset.filter(status=AuthAuditEvent.STATUS_FAILED).count()
        by_type = list(
            queryset.values("event_type").annotate(count=Count("id")).order_by("-count", "event_type")
        )
        by_status = list(
            queryset.values("status").annotate(count=Count("id")).order_by("-count", "status")
        )

        return Response(
            {
                "total_events": total_events,
                "failed_events": recent_failures,
                "by_type": by_type,
                "by_status": by_status,
            },
            status=status.HTTP_200_OK,
        )
