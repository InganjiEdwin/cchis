from __future__ import annotations

from datetime import timedelta
import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from urllib.parse import urlencode

from communications.services import send_email
from communications.templates import (
    build_access_request_acknowledgement_email,
    build_access_request_decision_email,
    build_password_reset_email,
)

from .models import AccessRequest, PasswordResetToken


User = get_user_model()


def password_reset_token_lifetime() -> timedelta:
    return timedelta(minutes=getattr(settings, "PASSWORD_RESET_TOKEN_LIFETIME_MINUTES", 60))


def create_password_reset_token(user: User) -> PasswordResetToken:
    PasswordResetToken.objects.filter(user=user, used_at__isnull=True).update(used_at=timezone.now())
    return PasswordResetToken.objects.create(
        user=user,
        token=secrets.token_urlsafe(32),
        expires_at=timezone.now() + password_reset_token_lifetime(),
    )


def send_password_reset_email(user: User, token_record: PasswordResetToken):
    reset_link = f"{settings.FRONTEND_APP_URL}/reset-password?{urlencode({'token': token_record.token})}"
    content = build_password_reset_email(token_record.token, reset_link)
    return send_email(
        to_email=user.email,
        subject=content.subject,
        text_body=content.text_body,
        html_body=content.html_body,
    )


def send_access_request_acknowledgement(access_request: AccessRequest):
    content = build_access_request_acknowledgement_email(
        full_name=access_request.full_name,
        organization=access_request.organization,
        desired_role=access_request.desired_role,
    )
    return send_email(
        to_email=access_request.contact_email,
        subject=content.subject,
        text_body=content.text_body,
        html_body=content.html_body,
    )


def send_access_request_decision(
    access_request: AccessRequest,
    *,
    approved: bool,
    decision_message: str = "",
):
    content = build_access_request_decision_email(
        full_name=access_request.full_name,
        approved=approved,
        decision_message=decision_message,
    )
    return send_email(
        to_email=access_request.contact_email,
        subject=content.subject,
        text_body=content.text_body,
        html_body=content.html_body,
    )
