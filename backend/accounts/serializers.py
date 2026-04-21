from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.validators import UniqueValidator
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from .models import AuthAuditEvent


User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    ward_name = serializers.CharField(source="ward.name", read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "full_name",
            "phone_number",
            "role",
            "ward",
            "ward_name",
            "is_active",
        ]


class RegisterSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(
        required=True,
        validators=[UniqueValidator(queryset=User.objects.all())],
    )
    password = serializers.CharField(write_only=True, min_length=8)

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


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)

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
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["username"] = user.username
        token["role"] = user.role
        token["ward_id"] = user.ward_id
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user).data
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
