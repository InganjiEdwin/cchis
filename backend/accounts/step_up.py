from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import APIException
from rest_framework.permissions import BasePermission

from .audit import record_auth_event
from .models import AuthAuditEvent, StepUpGrant, UserSession
from .session_security import (
    build_session_event_metadata,
    get_request_context_hashes,
    validate_access_token_session,
)


HIGH_RISK_ACTION_AUDIT_ATTR = "_cchis_high_risk_action_audit"
STEP_UP_REQUIRED_DETAIL = "This action needs a quick security check. Enter your authenticator code to continue."


class StepUpRequired(APIException):
    status_code = 403
    default_code = "step_up_required"

    def __init__(self, purpose: str):
        super().__init__(
            detail={
                "detail": STEP_UP_REQUIRED_DETAIL,
                "code": self.default_code,
                "purpose": purpose,
            },
            code=self.default_code,
        )


def step_up_purposes() -> tuple[str, ...]:
    return tuple(purpose for purpose, _ in StepUpGrant.PURPOSE_CHOICES)


def get_step_up_ttl_seconds(purpose: str) -> int:
    if purpose == StepUpGrant.PURPOSE_SENSITIVE_EXPORT_DOWNLOAD:
        return max(1, int(getattr(settings, "AUTH_STEP_UP_DOWNLOAD_SECONDS", 300)))
    return max(1, int(getattr(settings, "AUTH_STEP_UP_DEFAULT_SECONDS", 600)))


def get_current_session_from_request(request) -> UserSession | None:
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return None

    validated_token = getattr(request, "auth", None)
    if not validated_token:
        return None

    return validate_access_token_session(user, validated_token)


def create_step_up_grant(
    *,
    user,
    session: UserSession,
    request,
    purpose: str,
    method: str,
) -> StepUpGrant:
    now = timezone.now()
    context_hashes = get_request_context_hashes(request)
    return StepUpGrant.objects.create(
        user=user,
        session=session,
        purpose=purpose,
        verified_at=now,
        expires_at=now + timedelta(seconds=get_step_up_ttl_seconds(purpose)),
        method=method,
        ip_prefix_hash=context_hashes["ip_prefix_hash"],
        user_agent_hash=context_hashes["user_agent_hash"],
    )


def _grant_matches_request_context(grant: StepUpGrant, request) -> bool:
    context_hashes = get_request_context_hashes(request)
    if (
        grant.ip_prefix_hash
        and context_hashes["ip_prefix_hash"]
        and grant.ip_prefix_hash != context_hashes["ip_prefix_hash"]
    ):
        return False
    if (
        grant.user_agent_hash
        and context_hashes["user_agent_hash"]
        and grant.user_agent_hash != context_hashes["user_agent_hash"]
    ):
        return False
    return True


def get_fresh_step_up_grant(request, purpose: str) -> StepUpGrant | None:
    session = get_current_session_from_request(request)
    if not session:
        return None

    now = timezone.now()
    grants = StepUpGrant.objects.filter(
        user=request.user,
        session=session,
        purpose=purpose,
        consumed_at__isnull=True,
        expires_at__gt=now,
    ).order_by("-verified_at", "-id")

    for grant in grants:
        if _grant_matches_request_context(grant, request):
            return grant
    return None


def has_fresh_step_up(request, purpose: str) -> bool:
    return get_fresh_step_up_grant(request, purpose) is not None


def requires_fresh_step_up(request, purpose: str) -> bool:
    return not has_fresh_step_up(request, purpose)


def mark_high_risk_action_for_audit(
    request,
    purpose: str,
    *,
    grant: StepUpGrant | None = None,
) -> None:
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return

    session = grant.session if grant else None
    if session is None:
        try:
            session = get_current_session_from_request(request)
        except Exception:
            session = None

    metadata = {"purpose": purpose}
    if session:
        metadata.update(build_session_event_metadata(session))
    if grant:
        metadata["step_up_grant_id"] = str(grant.public_id)

    audit_payload = {
        "actor": user,
        "target_user": user,
        "purpose": purpose,
        "metadata": metadata,
    }
    setattr(request, HIGH_RISK_ACTION_AUDIT_ATTR, audit_payload)
    raw_request = getattr(request, "_request", None)
    if raw_request is not None:
        setattr(raw_request, HIGH_RISK_ACTION_AUDIT_ATTR, audit_payload)


def record_step_up_required(request, purpose: str) -> None:
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return

    metadata = {"purpose": purpose}
    try:
        session = get_current_session_from_request(request)
    except Exception:
        session = None
    if session:
        metadata.update(build_session_event_metadata(session))

    record_auth_event(
        request=request,
        event_type=AuthAuditEvent.EVENT_STEP_UP_REQUIRED,
        status=AuthAuditEvent.STATUS_FAILED,
        actor=user,
        target_user=user,
        metadata=metadata,
    )


def RequireFreshStepUp(purpose: str, methods: tuple[str, ...] | list[str] | set[str] | None = None):
    allowed_methods = {method.upper() for method in methods} if methods else None

    class FreshStepUpPermission(BasePermission):
        def has_permission(self, request, view):
            if allowed_methods and request.method.upper() not in allowed_methods:
                return True
            grant = get_fresh_step_up_grant(request, purpose)
            if grant:
                mark_high_risk_action_for_audit(request, purpose, grant=grant)
                return True

            record_step_up_required(request, purpose)
            raise StepUpRequired(purpose)

    FreshStepUpPermission.__name__ = f"RequireFreshStepUp_{purpose}"
    return FreshStepUpPermission
