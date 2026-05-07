from __future__ import annotations

from datetime import timedelta
import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from urllib.parse import urlencode

from communications.services import send_email
from communications.templates import (
    build_access_request_acknowledgement_email,
    build_access_request_decision_email,
    build_password_reset_email,
)

from .audit import get_client_ip
from .models import AccessRequest, PasswordResetToken, UserPolicyAcceptance


User = get_user_model()


def get_current_policy_versions() -> dict[str, str]:
    return {
        "terms_version": str(
            getattr(settings, "CURRENT_TERMS_VERSION", "terms-2026-05")
            or "terms-2026-05"
        ),
        "privacy_version": str(
            getattr(settings, "CURRENT_PRIVACY_VERSION", "privacy-2026-05")
            or "privacy-2026-05"
        ),
        "cookie_notice_version": str(
            getattr(settings, "CURRENT_COOKIE_NOTICE_VERSION", "cookies-2026-05")
            or "cookies-2026-05"
        ),
    }


def get_current_policy_documents() -> tuple[dict[str, str], ...]:
    versions = get_current_policy_versions()
    return (
        {
            "document_type": UserPolicyAcceptance.DOCUMENT_TERMS,
            "version": versions["terms_version"],
            "accepted_version_key": "accepted_terms_version",
        },
        {
            "document_type": UserPolicyAcceptance.DOCUMENT_PRIVACY,
            "version": versions["privacy_version"],
            "accepted_version_key": "accepted_privacy_version",
        },
        {
            "document_type": UserPolicyAcceptance.DOCUMENT_COOKIE_NOTICE,
            "version": versions["cookie_notice_version"],
            "accepted_version_key": "accepted_cookie_notice_version",
        },
    )


def build_policy_acceptance_status(user: User) -> dict:
    documents = get_current_policy_documents()
    current_versions_by_type = {
        document["document_type"]: document["version"] for document in documents
    }
    latest_versions_by_type = {}
    current_acceptances = set()

    acceptances = UserPolicyAcceptance.objects.filter(
        user=user,
        document_type__in=current_versions_by_type.keys(),
    ).order_by("document_type", "-accepted_at", "-id")

    for acceptance in acceptances:
        latest_versions_by_type.setdefault(acceptance.document_type, acceptance.version)
        if acceptance.version == current_versions_by_type.get(acceptance.document_type):
            current_acceptances.add(acceptance.document_type)

    missing_documents = [
        document["document_type"]
        for document in documents
        if document["document_type"] not in current_acceptances
    ]
    acceptance_required = bool(getattr(settings, "POLICY_ACCEPTANCE_REQUIRED", True))
    visible_missing_documents = missing_documents if acceptance_required else []

    payload = {
        "required": acceptance_required,
        "is_current": not visible_missing_documents,
        "terms_version": current_versions_by_type[UserPolicyAcceptance.DOCUMENT_TERMS],
        "privacy_version": current_versions_by_type[UserPolicyAcceptance.DOCUMENT_PRIVACY],
        "cookie_notice_version": current_versions_by_type[
            UserPolicyAcceptance.DOCUMENT_COOKIE_NOTICE
        ],
        "missing_documents": visible_missing_documents,
        "terms_url": "/terms",
        "privacy_url": "/privacy",
        "cookie_notice_url": "/privacy#cookies",
    }

    for document in documents:
        payload[document["accepted_version_key"]] = latest_versions_by_type.get(
            document["document_type"]
        )

    return payload


def infer_policy_acceptance_context(user: User) -> str:
    if UserPolicyAcceptance.objects.filter(user=user).exists():
        return UserPolicyAcceptance.CONTEXT_VERSION_UPDATE
    return UserPolicyAcceptance.CONTEXT_FIRST_SIGN_IN


def create_current_policy_acceptances(
    user: User,
    *,
    request=None,
    acceptance_context: str | None = None,
    metadata: dict | None = None,
) -> list[UserPolicyAcceptance]:
    accepted_at = timezone.now()
    ip_address = get_client_ip(request) if request is not None else None
    user_agent = request.META.get("HTTP_USER_AGENT", "")[:1000] if request is not None else ""
    context = acceptance_context or infer_policy_acceptance_context(user)
    acceptance_metadata = metadata or {}
    created_acceptances = []

    with transaction.atomic():
        for document in get_current_policy_documents():
            acceptance, created = UserPolicyAcceptance.objects.get_or_create(
                user=user,
                document_type=document["document_type"],
                version=document["version"],
                defaults={
                    "accepted_at": accepted_at,
                    "ip_address": ip_address,
                    "user_agent": user_agent,
                    "acceptance_context": context,
                    "metadata": dict(acceptance_metadata),
                },
            )
            if created:
                created_acceptances.append(acceptance)

    return created_acceptances


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
