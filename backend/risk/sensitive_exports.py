from __future__ import annotations

import csv
import hashlib
from datetime import datetime
from datetime import timedelta
from io import StringIO

from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from accounts.models import User

from .models import Alert, SensitiveExportDownloadAudit, SensitiveExportRequest, Ward
from .privacy_minimization import PrivacyMinimizationViolation, ensure_pii_safe_mapping

EXPORT_EXPIRY_DAYS = 30
ALERT_EXPORT_SENSITIVE_FIELDS = [
    "alert.recipient",
    "alert.message",
    "alert.error_message",
    "alert.external_id",
]


def user_can_request_sensitive_export(user: User) -> bool:
    return bool(user and user.is_authenticated and user.role in [User.ROLE_ADMIN, User.ROLE_SUPERVISOR])


def user_can_download_sensitive_export(user: User, export_request: SensitiveExportRequest) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.role == User.ROLE_ADMIN:
        return True
    return user.role == User.ROLE_SUPERVISOR and export_request.requester_id == user.id


def _parse_iso_datetime(value):
    if not value:
        return None
    if hasattr(value, "isoformat"):
        return value
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError({"filters": [f"Invalid datetime filter: {value}"]}) from exc
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _alert_queryset_for_user(user: User):
    queryset = Alert.objects.select_related("ward", "risk_score").all().order_by("-created_at")
    if user.role == User.ROLE_SUPERVISOR:
        if not user.ward_id:
            return queryset.none()
        return queryset.filter(ward_id=user.ward_id)
    return queryset


def _coerce_filters(value) -> dict:
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise ValidationError({"filters": ["Filters must be an object."]})
    return value


def _raise_filter_minimization_error(error: PrivacyMinimizationViolation) -> None:
    raise ValidationError({"filters": [str(error)]}) from error


def _parse_int_filter(value, field_name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError({"filters": [f"{field_name} must be an integer."]}) from exc


def _validate_alert_filter_shape(filters: dict, *, require_alert_id: bool = False) -> None:
    allowed_filter_keys = {"alert_id", "alert_ids", "ward_id", "status", "channel", "created_after", "created_before"}
    unsupported = sorted(set(filters) - allowed_filter_keys)
    if unsupported:
        raise ValidationError({"filters": [f"Unsupported export filter: {', '.join(unsupported)}"]})

    if require_alert_id and filters.get("alert_id") in (None, ""):
        raise ValidationError({"filters": ["alert_id is required for alert detail report exports."]})

    if filters.get("alert_id") not in (None, ""):
        _parse_int_filter(filters["alert_id"], "alert_id")

    alert_ids = filters.get("alert_ids")
    if alert_ids:
        if not isinstance(alert_ids, list):
            raise ValidationError({"filters": ["alert_ids must be a list."]})
        for value in alert_ids:
            _parse_int_filter(value, "alert_ids")

    if filters.get("ward_id") not in (None, ""):
        _parse_int_filter(filters["ward_id"], "ward_id")

    if filters.get("status"):
        status_value = str(filters["status"]).upper()
        valid_statuses = {choice[0] for choice in Alert.STATUS_CHOICES}
        if status_value not in valid_statuses:
            raise ValidationError({"filters": ["status is not a supported alert status."]})

    if filters.get("channel"):
        channel_value = str(filters["channel"]).upper()
        valid_channels = {choice[0] for choice in Alert.CHANNEL_CHOICES}
        if channel_value not in valid_channels:
            raise ValidationError({"filters": ["channel is not a supported alert channel."]})

    _parse_iso_datetime(filters.get("created_after"))
    _parse_iso_datetime(filters.get("created_before"))


def validate_sensitive_export_filters(export_type: str, filters=None) -> dict:
    filters = _coerce_filters(filters)
    try:
        ensure_pii_safe_mapping(filters, location="filters")
    except PrivacyMinimizationViolation as exc:
        _raise_filter_minimization_error(exc)

    if export_type == SensitiveExportRequest.EXPORT_ALERT_LIST_CSV:
        _validate_alert_filter_shape(filters)
    elif export_type == SensitiveExportRequest.EXPORT_ALERT_DETAIL_REPORT:
        _validate_alert_filter_shape(filters, require_alert_id=True)
    else:
        raise ValidationError({"export_type": ["Unsupported sensitive export type."]})
    return filters


def _filter_alert_queryset(queryset, filters: dict):
    if filters.get("alert_id") not in (None, ""):
        queryset = queryset.filter(pk=_parse_int_filter(filters["alert_id"], "alert_id"))

    alert_ids = filters.get("alert_ids")
    if alert_ids:
        if not isinstance(alert_ids, list):
            raise ValidationError({"filters": ["alert_ids must be a list."]})
        queryset = queryset.filter(pk__in=[_parse_int_filter(value, "alert_ids") for value in alert_ids])

    if filters.get("ward_id") not in (None, ""):
        queryset = queryset.filter(ward_id=_parse_int_filter(filters["ward_id"], "ward_id"))
    if filters.get("status"):
        queryset = queryset.filter(status=str(filters["status"]).upper())
    if filters.get("channel"):
        queryset = queryset.filter(channel=str(filters["channel"]).upper())
    created_after = _parse_iso_datetime(filters.get("created_after"))
    created_before = _parse_iso_datetime(filters.get("created_before"))
    if created_after:
        queryset = queryset.filter(created_at__gte=created_after)
    if created_before:
        queryset = queryset.filter(created_at__lte=created_before)
    return queryset


def _csv_payload(rows: list[list[object]]) -> str:
    output = StringIO()
    writer = csv.writer(output)
    writer.writerows(rows)
    return output.getvalue()


def _alert_public_id(alert: Alert) -> str:
    return f"AL-{str(alert.id).zfill(4)}"


def _build_alert_list_export(export_request: SensitiveExportRequest) -> tuple[str, int, str]:
    queryset = _filter_alert_queryset(
        _alert_queryset_for_user(export_request.requester),
        export_request.filters,
    )
    alerts = list(queryset[:500])
    rows = [
        ["Alert ID", "Ward", "Channel", "Status", "Created At", "Sent At", "Recipient", "Message", "Error", "External ID"],
    ]
    for alert in alerts:
        rows.append(
            [
                _alert_public_id(alert),
                alert.ward.name,
                alert.channel,
                alert.status,
                alert.created_at.isoformat(),
                alert.sent_at.isoformat() if alert.sent_at else "",
                alert.recipient,
                alert.message,
                alert.error_message,
                alert.external_id,
            ]
        )
    return _csv_payload(rows), len(alerts), "alerts-monitoring.csv"


def _build_alert_detail_export(export_request: SensitiveExportRequest) -> tuple[str, int, str]:
    alert_id = export_request.filters.get("alert_id")
    if alert_id in (None, ""):
        raise ValidationError({"filters": ["alert_id is required for alert detail report exports."]})
    alert = _filter_alert_queryset(
        _alert_queryset_for_user(export_request.requester),
        {"alert_id": alert_id},
    ).first()
    if alert is None:
        raise ValidationError({"filters": ["Alert is not available in the requester scope."]})

    ward: Ward = alert.ward
    rows = [
        ["Field", "Value"],
        ["Alert ID", _alert_public_id(alert)],
        ["Ward", ward.name],
        ["Channel", alert.channel],
        ["Status", alert.status],
        ["Created", alert.created_at.isoformat()],
        ["Sent", alert.sent_at.isoformat() if alert.sent_at else ""],
        ["Backend", alert.delivery_backend or ""],
        ["Recipient", alert.recipient],
        ["Message", alert.message],
        ["Error", alert.error_message or ""],
        ["Ward risk level", ward.current_risk_level],
        ["Ward risk score", ward.current_risk_score],
        ["External ID", alert.external_id],
    ]
    return _csv_payload(rows), 1, f"{_alert_public_id(alert).lower()}-report.csv"


def _generate_export_payload(export_request: SensitiveExportRequest, *, now=None) -> SensitiveExportRequest:
    now = now or timezone.now()
    if export_request.export_type == SensitiveExportRequest.EXPORT_ALERT_LIST_CSV:
        payload, row_count, filename = _build_alert_list_export(export_request)
    elif export_request.export_type == SensitiveExportRequest.EXPORT_ALERT_DETAIL_REPORT:
        payload, row_count, filename = _build_alert_detail_export(export_request)
    else:
        raise ValidationError({"export_type": ["Unsupported export type."]})

    export_request.generated_payload = payload
    export_request.generated_filename = filename
    export_request.generated_content_type = "text/csv"
    export_request.payload_sha256 = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    export_request.row_count = row_count
    export_request.generated_at = now
    export_request.expires_at = now + timedelta(days=EXPORT_EXPIRY_DAYS)
    export_request.save(
        update_fields=[
            "generated_payload",
            "generated_filename",
            "generated_content_type",
            "payload_sha256",
            "row_count",
            "generated_at",
            "expires_at",
            "updated_at",
        ]
    )
    return export_request


def sensitive_fields_for_export_type(export_type: str) -> list[str]:
    if export_type in {
        SensitiveExportRequest.EXPORT_ALERT_LIST_CSV,
        SensitiveExportRequest.EXPORT_ALERT_DETAIL_REPORT,
    }:
        return list(ALERT_EXPORT_SENSITIVE_FIELDS)
    return []


def request_sensitive_export(*, requester: User, export_type: str, purpose: str, filters=None) -> SensitiveExportRequest:
    if not user_can_request_sensitive_export(requester):
        raise PermissionDenied("Sensitive exports require admin or supervisor permissions.")
    filters = validate_sensitive_export_filters(export_type, filters)
    if len((purpose or "").strip()) < 12:
        raise ValidationError({"purpose": ["Purpose must explain why this sensitive export is needed."]})

    sensitive_fields = sensitive_fields_for_export_type(export_type)
    if not sensitive_fields:
        raise ValidationError({"export_type": ["Unsupported sensitive export type."]})

    requires_approval = requester.role != User.ROLE_ADMIN
    export_request = SensitiveExportRequest.objects.create(
        export_type=export_type,
        requester=requester,
        purpose=purpose.strip(),
        filters=filters,
        sensitive_fields_included=sensitive_fields,
        approval_state=(
            SensitiveExportRequest.APPROVAL_PENDING
            if requires_approval
            else SensitiveExportRequest.APPROVAL_APPROVED
        ),
        requires_approval=requires_approval,
        approved_by=None if requires_approval else requester,
        approved_at=None if requires_approval else timezone.now(),
        metadata={
            "governance_mode": "admin_auto_approved" if not requires_approval else "requires_admin_approval",
            "unsafe_reason": "direct_contact_identifiers_included",
        },
    )

    if not requires_approval:
        _generate_export_payload(export_request)

    return export_request


def approve_sensitive_export(export_request: SensitiveExportRequest, *, actor: User) -> SensitiveExportRequest:
    if actor.role != User.ROLE_ADMIN and not actor.is_superuser:
        raise PermissionDenied("Only admins can approve sensitive exports.")
    if export_request.approval_state != SensitiveExportRequest.APPROVAL_PENDING:
        raise ValidationError({"approval_state": ["Only pending exports can be approved."]})

    now = timezone.now()
    export_request.approval_state = SensitiveExportRequest.APPROVAL_APPROVED
    export_request.approved_by = actor
    export_request.approved_at = now
    export_request.rejected_by = None
    export_request.rejected_at = None
    export_request.rejection_reason = ""
    export_request.save(
        update_fields=[
            "approval_state",
            "approved_by",
            "approved_at",
            "rejected_by",
            "rejected_at",
            "rejection_reason",
            "updated_at",
        ]
    )
    return _generate_export_payload(export_request, now=now)


def reject_sensitive_export(export_request: SensitiveExportRequest, *, actor: User, reason: str) -> SensitiveExportRequest:
    if actor.role != User.ROLE_ADMIN and not actor.is_superuser:
        raise PermissionDenied("Only admins can reject sensitive exports.")
    if export_request.approval_state != SensitiveExportRequest.APPROVAL_PENDING:
        raise ValidationError({"approval_state": ["Only pending exports can be rejected."]})
    if len((reason or "").strip()) < 8:
        raise ValidationError({"reason": ["Rejection reason is required."]})

    export_request.approval_state = SensitiveExportRequest.APPROVAL_REJECTED
    export_request.rejected_by = actor
    export_request.rejected_at = timezone.now()
    export_request.rejection_reason = reason.strip()
    export_request.save(
        update_fields=[
            "approval_state",
            "rejected_by",
            "rejected_at",
            "rejection_reason",
            "updated_at",
        ]
    )
    return export_request


def _audit_download(export_request, *, downloader, outcome, reason="", request_metadata=None):
    return SensitiveExportDownloadAudit.objects.create(
        export_request=export_request,
        downloader=downloader if getattr(downloader, "is_authenticated", False) else None,
        outcome=outcome,
        reason=reason,
        request_metadata=request_metadata or {},
    )


def download_sensitive_export(export_request: SensitiveExportRequest, *, downloader: User, request_metadata=None) -> dict:
    if not user_can_download_sensitive_export(downloader, export_request):
        _audit_download(
            export_request,
            downloader=downloader,
            outcome=SensitiveExportDownloadAudit.OUTCOME_BLOCKED_PERMISSION,
            reason="downloader is neither admin nor original requester",
            request_metadata=request_metadata,
        )
        raise PermissionDenied("You cannot download this sensitive export.")

    if export_request.approval_state != SensitiveExportRequest.APPROVAL_APPROVED:
        _audit_download(
            export_request,
            downloader=downloader,
            outcome=SensitiveExportDownloadAudit.OUTCOME_BLOCKED_NOT_APPROVED,
            reason=f"export state is {export_request.approval_state}",
            request_metadata=request_metadata,
        )
        raise ValidationError({"approval_state": ["Sensitive export is not approved for download."]})

    if export_request.is_expired():
        export_request.approval_state = SensitiveExportRequest.APPROVAL_EXPIRED
        export_request.generated_payload = ""
        export_request.save(update_fields=["approval_state", "generated_payload", "updated_at"])
        _audit_download(
            export_request,
            downloader=downloader,
            outcome=SensitiveExportDownloadAudit.OUTCOME_BLOCKED_EXPIRED,
            reason="export expired before download",
            request_metadata=request_metadata,
        )
        raise ValidationError({"expires_at": ["Sensitive export has expired."]})

    if not export_request.generated_payload:
        _generate_export_payload(export_request)

    _audit_download(
        export_request,
        downloader=downloader,
        outcome=SensitiveExportDownloadAudit.OUTCOME_DOWNLOADED,
        reason="approved export downloaded",
        request_metadata=request_metadata,
    )
    export_request.download_count += 1
    export_request.last_downloaded_at = timezone.now()
    export_request.save(update_fields=["download_count", "last_downloaded_at", "updated_at"])
    return {
        "public_id": str(export_request.public_id),
        "filename": export_request.generated_filename,
        "content_type": export_request.generated_content_type,
        "payload": export_request.generated_payload,
        "payload_sha256": export_request.payload_sha256,
        "expires_at": export_request.expires_at,
    }


def expire_sensitive_exports(*, now=None) -> int:
    now = now or timezone.now()
    queryset = SensitiveExportRequest.objects.filter(
        approval_state=SensitiveExportRequest.APPROVAL_APPROVED,
        expires_at__lte=now,
    ).filter(Q(generated_payload__gt="") | ~Q(approval_state=SensitiveExportRequest.APPROVAL_EXPIRED))
    updated = 0
    for export_request in queryset:
        export_request.approval_state = SensitiveExportRequest.APPROVAL_EXPIRED
        export_request.generated_payload = ""
        export_request.save(update_fields=["approval_state", "generated_payload", "updated_at"])
        updated += 1
    return updated
