import logging

from django.conf import settings
from django.contrib.auth import get_user_model

from .models import AuthAuditEvent


User = get_user_model()
audit_logger = logging.getLogger("accounts.audit")


def get_client_ip(request) -> str | None:
    if getattr(settings, "TRUST_X_FORWARDED_FOR", False):
        forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "").strip()
        if forwarded_for:
            forwarded_ip = forwarded_for.split(",")[0].strip()
            if forwarded_ip:
                return forwarded_ip
    remote_addr = request.META.get("REMOTE_ADDR", "").strip()
    return remote_addr or None


def record_auth_event(
    *,
    request,
    event_type: str,
    status: str,
    actor=None,
    target_user=None,
    metadata: dict | None = None,
):
    metadata = metadata or {}
    ward = None
    if target_user is not None and getattr(target_user, "ward_id", None):
        ward = target_user.ward
    elif actor is not None and getattr(actor, "ward_id", None):
        ward = actor.ward

    event = AuthAuditEvent.objects.create(
        actor=actor,
        target_user=target_user,
        ward=ward,
        event_type=event_type,
        status=status,
        ip_address=get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:1000],
        metadata=metadata,
    )

    audit_logger.info(
        "auth_audit_event",
        extra={
            "event_type": event_type,
            "status": status,
            "actor_id": actor.id if actor else None,
            "target_user_id": target_user.id if target_user else None,
            "ward_id": ward.id if ward else None,
            "ip_address": event.ip_address,
            "request_path": getattr(request, "path", None),
            "request_method": getattr(request, "method", None),
            "auth_event_id": event.id,
        },
    )

    return event
