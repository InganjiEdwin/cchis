from __future__ import annotations

import hashlib
from typing import Any

from accounts.audit import get_client_ip

from risk.models import SourceDataUploadBatch, SourceDataUploadEvent


def _hash_audit_value(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def record_source_data_upload_event(
    *,
    request,
    batch: SourceDataUploadBatch,
    event_type: str,
    actor=None,
    metadata: dict[str, Any] | None = None,
) -> SourceDataUploadEvent:
    return SourceDataUploadEvent.objects.create(
        upload_batch=batch,
        actor=actor,
        event_type=event_type,
        ip_address_hash=_hash_audit_value(get_client_ip(request)),
        user_agent_hash=_hash_audit_value(request.META.get("HTTP_USER_AGENT", "")),
        metadata=metadata or {},
    )


def record_source_data_upload_system_event(
    *,
    batch: SourceDataUploadBatch,
    event_type: str,
    actor=None,
    metadata: dict[str, Any] | None = None,
) -> SourceDataUploadEvent:
    return SourceDataUploadEvent.objects.create(
        upload_batch=batch,
        actor=actor,
        event_type=event_type,
        metadata=metadata or {},
    )
