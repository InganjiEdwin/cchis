from django.contrib.auth import get_user_model
from django.db.models import Count
from rest_framework import generics, permissions
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import get_object_or_404
from rest_framework import status
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .audit import record_auth_event
from .models import AuthAuditEvent
from .permissions import IsAdminOnly
from .serializers import (
    CCHISTokenRefreshSerializer,
    CCHISTokenObtainPairSerializer,
    ChangePasswordSerializer,
    LogoutSerializer,
    RegisterSerializer,
    AuthAuditEventSerializer,
    UserSerializer,
)


User = get_user_model()


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
        username = request.data.get("username", "")
        user = User.objects.filter(username=username).first()
        serializer = self.get_serializer(data=request.data)

        try:
            serializer.is_valid(raise_exception=True)
        except Exception:
            record_auth_event(
                request=request,
                event_type=AuthAuditEvent.EVENT_LOGIN_FAILED,
                status=AuthAuditEvent.STATUS_FAILED,
                target_user=user,
                metadata={"username": username},
            )
            raise

        user = serializer.user
        record_auth_event(
            request=request,
            event_type=AuthAuditEvent.EVENT_LOGIN_SUCCESS,
            status=AuthAuditEvent.STATUS_SUCCESS,
            actor=user,
            target_user=user,
        )

        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class RefreshAPIView(TokenRefreshView):
    permission_classes = [permissions.AllowAny]
    serializer_class = CCHISTokenRefreshSerializer
    throttle_scope = "auth_refresh"

    def post(self, request, *args, **kwargs):
        refresh_token = request.data.get("refresh", "")
        user = None

        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                user = User.objects.filter(id=token.get("user_id")).first()
            except TokenError:
                user = None

        serializer = self.get_serializer(data=request.data)

        try:
            serializer.is_valid(raise_exception=True)
        except Exception:
            record_auth_event(
                request=request,
                event_type=AuthAuditEvent.EVENT_REFRESH_FAILED,
                status=AuthAuditEvent.STATUS_FAILED,
                actor=user,
                target_user=user,
            )
            raise

        record_auth_event(
            request=request,
            event_type=AuthAuditEvent.EVENT_REFRESH_SUCCESS,
            status=AuthAuditEvent.STATUS_SUCCESS,
            actor=user,
            target_user=user,
        )

        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class MeAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class LogoutAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "auth_write"

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            token = RefreshToken(serializer.validated_data["refresh"])
            token.blacklist()
        except TokenError:
            record_auth_event(
                request=request,
                event_type=AuthAuditEvent.EVENT_LOGOUT,
                status=AuthAuditEvent.STATUS_FAILED,
                actor=request.user,
                target_user=request.user,
            )
            return Response(
                {"detail": "Invalid or expired refresh token."},
                status=400,
            )

        record_auth_event(
            request=request,
            event_type=AuthAuditEvent.EVENT_LOGOUT,
            status=AuthAuditEvent.STATUS_SUCCESS,
            actor=request.user,
            target_user=request.user,
        )
        return Response(status=205)


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
