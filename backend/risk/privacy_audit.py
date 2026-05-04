from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from typing import Iterable

from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, F, Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from accounts.models import User

from .models import (
    Alert,
    CHVAssignment,
    CHVCoverageRequest,
    CHVMessage,
    ContactPreference,
    ContactPreferenceAuditEvent,
    HealthFacility,
    PreparednessAction,
    PreparednessActionEvent,
    PrivacyRetentionHold,
    SensitiveExportDownloadAudit,
    SensitiveExportRequest,
    SyncQueue,
    TriageSession,
    UssdSessionLog,
)
from .privacy_access import PHONE_CANDIDATE_PATTERN
from .privacy_minimization import (
    PHONE_NUMBER_PATTERN,
    PrivacyMinimizationViolation,
    ensure_pii_safe_mapping,
    ensure_pii_safe_text,
)
from .serializers import (
    AlertIntelligenceSerializer,
    AlertSerializer,
    CHVCoverageRequestSerializer,
    FacilityIntelligenceSerializer,
    HealthFacilitySerializer,
    UssdSessionLogSerializer,
)
from .sensitive_exports import validate_sensitive_export_filters
from .services import build_alert_intelligence_snapshot, build_facility_intelligence_snapshot


MAX_FINDINGS_PER_CHECK = 25
OPERATOR_HANDLING_DOC = "docs/PRIVACY_AUDIT_OPERATOR_HANDLING.md"


def _iso(value) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _public_ref(obj) -> str:
    value = getattr(obj, "public_id", None)
    return str(value) if value else ""


def _audit_check(
    *,
    check_id: str,
    severity: str,
    gaps: list[dict],
    pass_answer: str,
    fail_answer: str,
    evidence: dict | None = None,
) -> dict:
    status = "fail" if gaps and severity == "high" else "warning" if gaps else "pass"
    return {
        "id": check_id,
        "status": status,
        "severity": severity,
        "answer": fail_answer if gaps else pass_answer,
        "gaps": gaps[:MAX_FINDINGS_PER_CHECK],
        "evidence": evidence or {},
    }


def _active_hold_object_ids(model: type, object_ids: Iterable[object], now) -> set[str]:
    ids = [str(object_id) for object_id in object_ids]
    if not ids:
        return set()

    content_type = ContentType.objects.get_for_model(model)
    return set(
        PrivacyRetentionHold.objects.filter(
            content_type=content_type,
            object_id__in=ids,
            is_active=True,
        )
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        .values_list("object_id", flat=True)
    )


def _already_redacted_json(value) -> bool:
    return isinstance(value, dict) and value.get("retention_redacted") is True


def _audit_chv_assignment_scope() -> dict:
    gaps: list[dict] = []

    assignments = CHVAssignment.objects.select_related(
        "coverage_request",
        "coverage_request__ward",
        "ward",
        "chv",
        "chv__ward",
    )
    for assignment in assignments.order_by("id").iterator(chunk_size=500):
        issues = []
        if assignment.ward_id != assignment.coverage_request.ward_id:
            issues.append("assignment ward does not match coverage request ward")
        if assignment.chv.ward_id != assignment.ward_id:
            issues.append("assigned CHV belongs to a different ward")
        if not issues:
            continue
        gaps.append(
            {
                "model": "risk.CHVAssignment",
                "id": assignment.id,
                "public_id": _public_ref(assignment),
                "coverage_request_id": assignment.coverage_request_id,
                "issues": issues,
                "ward_id": assignment.ward_id,
                "coverage_request_ward_id": assignment.coverage_request.ward_id,
                "chv_ward_id": assignment.chv.ward_id,
            }
        )
        if len(gaps) >= MAX_FINDINGS_PER_CHECK:
            break

    if len(gaps) < MAX_FINDINGS_PER_CHECK:
        message_mismatches = CHVMessage.objects.select_related("chv", "ward").exclude(ward_id=F("chv__ward_id"))
        for message in message_mismatches.order_by("id").iterator(chunk_size=500):
            gaps.append(
                {
                    "model": "risk.CHVMessage",
                    "id": message.id,
                    "public_id": _public_ref(message),
                    "chv_id": message.chv_id,
                    "ward_id": message.ward_id,
                    "chv_ward_id": message.chv.ward_id,
                    "issues": ["CHV message ward does not match the CHV assignment ward"],
                }
            )
            if len(gaps) >= MAX_FINDINGS_PER_CHECK:
                break

    return _audit_check(
        check_id="chv_data_outside_assignment",
        severity="high",
        gaps=gaps,
        pass_answer="CHV assignments and CHV message rows are ward-scoped to the CHV or coverage request.",
        fail_answer="CHV data exists outside the ward assignment boundary.",
        evidence={
            "assignment_count": CHVAssignment.objects.count(),
            "chv_message_count": CHVMessage.objects.count(),
        },
    )


def _preference_event_issues(preference: ContactPreference, event: ContactPreferenceAuditEvent) -> list[str]:
    issues = []
    if preference.audience_type != ContactPreference.AUDIENCE_HOUSEHOLD:
        issues.append("linked preference is not a household preference")
    if preference.channel != event.channel:
        issues.append("linked preference channel does not match audit event channel")
    if preference.consent_status != ContactPreference.CONSENT_GRANTED:
        issues.append("linked household preference did not grant consent")
    if preference.opt_out_status == ContactPreference.OPT_OUT_OPTED_OUT:
        issues.append("linked household preference is opted out")
    if preference.expires_at and preference.expires_at <= event.created_at:
        issues.append("linked household preference expired before the audited allow event")

    event_phone = (event.phone_number or "").strip()
    preference_phone = (preference.phone_number or "").strip()
    if event_phone and preference_phone and event_phone != preference_phone:
        issues.append("audit event phone does not match linked preference phone")

    event_ref = (event.contact_reference or "").strip()
    preference_ref = (preference.contact_reference or "").strip()
    if event_ref and preference_ref and event_ref != preference_ref:
        issues.append("audit event contact reference does not match linked preference reference")

    return issues


def _audit_household_message_consent() -> dict:
    gaps: list[dict] = []
    household_events = ContactPreferenceAuditEvent.objects.filter(
        audience_type=ContactPreference.AUDIENCE_HOUSEHOLD,
        action__in=[
            ContactPreferenceAuditEvent.ACTION_ALLOWED,
            ContactPreferenceAuditEvent.ACTION_EMERGENCY_OVERRIDE_USED,
        ],
    ).select_related("preference")

    for event in household_events.order_by("-created_at").iterator(chunk_size=500):
        issues = []
        if event.action == ContactPreferenceAuditEvent.ACTION_ALLOWED:
            if event.preference is None:
                issues.append("household allow event has no linked consent preference")
            else:
                issues.extend(_preference_event_issues(event.preference, event))

        if event.action == ContactPreferenceAuditEvent.ACTION_EMERGENCY_OVERRIDE_USED and not event.reason.strip():
            issues.append("emergency override has no recorded reason")

        if not issues:
            continue

        gaps.append(
            {
                "model": "risk.ContactPreferenceAuditEvent",
                "id": event.id,
                "public_id": _public_ref(event),
                "action": event.action,
                "created_at": _iso(event.created_at),
                "preference_id": event.preference_id,
                "issues": issues,
            }
        )
        if len(gaps) >= MAX_FINDINGS_PER_CHECK:
            break

    return _audit_check(
        check_id="household_message_consent_or_override",
        severity="high",
        gaps=gaps,
        pass_answer="Household allow/override audit events are backed by valid consent or an explicit emergency reason.",
        fail_answer="Household messaging audit events include sends without valid consent or override reason.",
        evidence={
            "household_allowed_events": household_events.filter(
                action=ContactPreferenceAuditEvent.ACTION_ALLOWED
            ).count(),
            "household_override_events": household_events.filter(
                action=ContactPreferenceAuditEvent.ACTION_EMERGENCY_OVERRIDE_USED
            ).count(),
        },
    )


def _audit_contact_preference_phone_integrity() -> dict:
    gaps: list[dict] = []

    for preference in ContactPreference.objects.exclude(phone_number="").order_by("-created_at").iterator(chunk_size=500):
        if ContactPreference.is_valid_phone_number(preference.phone_number):
            continue
        gaps.append(
            {
                "model": "risk.ContactPreference",
                "id": preference.id,
                "public_id": _public_ref(preference),
                "audience_type": preference.audience_type,
                "channel": preference.channel,
                "issues": ["contact preference phone_number is not a valid Kenyan mobile number"],
            }
        )
        if len(gaps) >= MAX_FINDINGS_PER_CHECK:
            break

    if len(gaps) < MAX_FINDINGS_PER_CHECK:
        for event in ContactPreferenceAuditEvent.objects.exclude(phone_number="").order_by("-created_at").iterator(
            chunk_size=500
        ):
            if ContactPreference.is_valid_phone_number(event.phone_number):
                continue
            gaps.append(
                {
                    "model": "risk.ContactPreferenceAuditEvent",
                    "id": event.id,
                    "public_id": _public_ref(event),
                    "action": event.action,
                    "audience_type": event.audience_type,
                    "channel": event.channel,
                    "issues": ["contact preference audit phone_number is not a valid Kenyan mobile number"],
                }
            )
            if len(gaps) >= MAX_FINDINGS_PER_CHECK:
                break

    return _audit_check(
        check_id="contact_preference_phone_integrity",
        severity="high",
        gaps=gaps,
        pass_answer="Stored contact preference phone fields are normalized valid Kenyan mobile numbers.",
        fail_answer="Contact preference phone fields contain invalid explicit identifiers.",
        evidence={
            "contact_preferences_with_phone": ContactPreference.objects.exclude(phone_number="").count(),
            "contact_preference_audit_events_with_phone": ContactPreferenceAuditEvent.objects.exclude(
                phone_number=""
            ).count(),
        },
    )


def _audit_sensitive_export_downloads() -> dict:
    gaps: list[dict] = []
    successful_counts = {
        item["export_request_id"]: item["count"]
        for item in SensitiveExportDownloadAudit.objects.filter(
            outcome=SensitiveExportDownloadAudit.OUTCOME_DOWNLOADED
        )
        .values("export_request_id")
        .annotate(count=Count("id"))
    }
    auditable_exports = SensitiveExportRequest.objects.select_related("requester", "approved_by")

    for export_request in auditable_exports.order_by("-created_at").iterator(chunk_size=500):
        issues = []
        successful_audit_count = successful_counts.get(export_request.id, 0)
        try:
            validate_sensitive_export_filters(export_request.export_type, export_request.filters)
        except ValidationError as exc:
            issues.append(f"stored export filters are invalid or unsafe: {exc.detail}")
        try:
            ensure_pii_safe_text(export_request.purpose, location="purpose")
        except PrivacyMinimizationViolation as exc:
            issues.append(
                "stored export purpose is unsafe: "
                + "; ".join(f"{finding.location}: {finding.reason}" for finding in exc.findings)
            )
        try:
            ensure_pii_safe_mapping(export_request.metadata or {}, location="metadata")
        except PrivacyMinimizationViolation as exc:
            issues.append(
                "stored export metadata is unsafe: "
                + "; ".join(f"{finding.location}: {finding.reason}" for finding in exc.findings)
            )
        if export_request.rejection_reason:
            try:
                ensure_pii_safe_text(export_request.rejection_reason, location="rejection_reason")
            except PrivacyMinimizationViolation as exc:
                issues.append(
                    "stored export rejection reason is unsafe: "
                    + "; ".join(f"{finding.location}: {finding.reason}" for finding in exc.findings)
                )

        if export_request.download_count != successful_audit_count:
            issues.append("successful download count does not match downloaded audit events")
        if export_request.last_downloaded_at and successful_audit_count == 0:
            issues.append("last_downloaded_at is set without a successful download audit event")

        if export_request.approval_state == SensitiveExportRequest.APPROVAL_APPROVED and export_request.generated_payload:
            if not export_request.requester_id:
                issues.append("approved export payload has no requester attribution")
            if not export_request.purpose.strip():
                issues.append("approved export payload has no purpose")
            if not export_request.sensitive_fields_included:
                issues.append("approved export payload does not declare sensitive fields")
            if not export_request.generated_at:
                issues.append("approved export payload has no generated_at timestamp")
            if not export_request.expires_at:
                issues.append("approved export payload has no expiry")
            if not export_request.payload_sha256:
                issues.append("approved export payload has no payload hash")
            if export_request.requires_approval and not export_request.approved_by_id:
                issues.append("approval-required export payload has no approving user")
            if export_request.requires_approval and not export_request.approved_at:
                issues.append("approval-required export payload has no approval timestamp")
            if (
                export_request.generated_at
                and export_request.expires_at
                and export_request.expires_at <= export_request.generated_at
            ):
                issues.append("approved export payload expiry is not after generation")

        if not issues:
            continue

        gaps.append(
            {
                "model": "risk.SensitiveExportRequest",
                "id": export_request.id,
                "public_id": _public_ref(export_request),
                "export_type": export_request.export_type,
                "approval_state": export_request.approval_state,
                "download_count": export_request.download_count,
                "successful_download_audit_count": successful_audit_count,
                "issues": issues,
            }
        )
        if len(gaps) >= MAX_FINDINGS_PER_CHECK:
            break

    return _audit_check(
        check_id="sensitive_export_download_audit",
        severity="high",
        gaps=gaps,
        pass_answer="Sensitive export payloads and successful downloads are attributable and audit-backed.",
        fail_answer="Sensitive export state is missing required attribution, expiry, hash, or download audit evidence.",
        evidence={
            "sensitive_export_requests": SensitiveExportRequest.objects.count(),
            "download_audit_events": SensitiveExportDownloadAudit.objects.count(),
        },
    )


def _audit_stale_sync_payloads(*, now, stale_sync_days: int) -> dict:
    sync_cutoff = now - timedelta(days=stale_sync_days)
    triage_cutoff = now - timedelta(days=180)
    ussd_cutoff = now - timedelta(days=30)
    gaps: list[dict] = []
    stale_candidates = SyncQueue.objects.filter(
        status=SyncQueue.STATUS_PROCESSED,
        processed_at__lt=sync_cutoff,
    ).filter(Q(phone_number__gt="") | Q(error_message__gt="") | ~Q(payload={}))
    candidate_ids = list(stale_candidates.values_list("id", flat=True))
    held_ids = _active_hold_object_ids(SyncQueue, candidate_ids, now)

    for item in stale_candidates.order_by("processed_at", "id").iterator(chunk_size=500):
        if str(item.id) in held_ids:
            continue

        issues = []
        if item.phone_number:
            issues.append("stale processed sync row still has phone_number")
        if item.error_message:
            issues.append("stale processed sync row still has raw error_message")
        if item.payload and not _already_redacted_json(item.payload):
            issues.append("stale processed sync row still has unredacted raw payload")

        if not issues:
            continue
        gaps.append(
            {
                "model": "risk.SyncQueue",
                "id": item.id,
                "public_id": _public_ref(item),
                "processed_at": _iso(item.processed_at),
                "cutoff_at": _iso(sync_cutoff),
                "issues": issues,
            }
        )
        if len(gaps) >= MAX_FINDINGS_PER_CHECK:
            break

    triage_candidates = TriageSession.objects.filter(created_at__lt=triage_cutoff).filter(
        Q(phone_number__gt="") | Q(text_input__gt="")
    )
    triage_candidate_ids = list(triage_candidates.values_list("id", flat=True))
    triage_held_ids = _active_hold_object_ids(TriageSession, triage_candidate_ids, now)
    if len(gaps) < MAX_FINDINGS_PER_CHECK:
        for item in triage_candidates.order_by("created_at", "id").iterator(chunk_size=500):
            if str(item.id) in triage_held_ids:
                continue
            issues = []
            if item.phone_number:
                issues.append("stale triage row still has phone_number")
            if item.text_input:
                issues.append("stale triage row still has raw text_input")
            if not issues:
                continue
            gaps.append(
                {
                    "model": "risk.TriageSession",
                    "id": item.id,
                    "public_id": _public_ref(item),
                    "created_at": _iso(item.created_at),
                    "cutoff_at": _iso(triage_cutoff),
                    "issues": issues,
                }
            )
            if len(gaps) >= MAX_FINDINGS_PER_CHECK:
                break

    ussd_candidates = UssdSessionLog.objects.filter(created_at__lt=ussd_cutoff).filter(
        Q(phone_number__gt="") | Q(text__gt="") | Q(response_text__gt="")
    )
    ussd_candidate_ids = list(ussd_candidates.values_list("id", flat=True))
    ussd_held_ids = _active_hold_object_ids(UssdSessionLog, ussd_candidate_ids, now)
    if len(gaps) < MAX_FINDINGS_PER_CHECK:
        for item in ussd_candidates.order_by("created_at", "id").iterator(chunk_size=500):
            if str(item.id) in ussd_held_ids:
                continue
            issues = []
            if item.phone_number:
                issues.append("stale USSD log still has phone_number")
            if item.text:
                issues.append("stale USSD log still has raw text")
            if item.response_text:
                issues.append("stale USSD log still has raw response_text")
            if not issues:
                continue
            gaps.append(
                {
                    "model": "risk.UssdSessionLog",
                    "id": item.id,
                    "public_id": _public_ref(item),
                    "created_at": _iso(item.created_at),
                    "cutoff_at": _iso(ussd_cutoff),
                    "issues": issues,
                }
            )
            if len(gaps) >= MAX_FINDINGS_PER_CHECK:
                break

    return _audit_check(
        check_id="stale_raw_sync_payload_retained",
        severity="high",
        gaps=gaps,
        pass_answer="Processed sync, triage, and USSD raw records past retention windows are redacted or under active hold.",
        fail_answer="Raw sync, triage, or USSD records past retention windows still retain direct identifiers or raw payloads.",
        evidence={
            "stale_sync_days": stale_sync_days,
            "triage_stale_days": 180,
            "ussd_stale_days": 30,
            "sync_candidate_count": len(candidate_ids),
            "triage_candidate_count": len(triage_candidate_ids),
            "ussd_candidate_count": len(ussd_candidate_ids),
            "sync_active_hold_count": len(held_ids),
            "triage_active_hold_count": len(triage_held_ids),
            "ussd_active_hold_count": len(ussd_held_ids),
            "sync_cutoff_at": _iso(sync_cutoff),
            "triage_cutoff_at": _iso(triage_cutoff),
            "ussd_cutoff_at": _iso(ussd_cutoff),
        },
    )


def _find_unmasked_phone_values(value, *, path: str) -> list[dict]:
    findings: list[dict] = []
    if isinstance(value, dict):
        for key, nested_value in value.items():
            findings.extend(_find_unmasked_phone_values(nested_value, path=f"{path}.{key}"))
        return findings
    if isinstance(value, list):
        for index, nested_value in enumerate(value):
            findings.extend(_find_unmasked_phone_values(nested_value, path=f"{path}[{index}]"))
        return findings
    if isinstance(value, str):
        stripped = value.strip()
        if PHONE_CANDIDATE_PATTERN.match(stripped) or PHONE_NUMBER_PATTERN.search(stripped):
            findings.append({"path": path, "value_length": len(stripped)})
    return findings


def _sample_phone_alerts() -> list[Alert]:
    alerts = []
    for alert in Alert.objects.exclude(recipient="").order_by("-created_at")[:250]:
        if PHONE_CANDIDATE_PATTERN.match(alert.recipient.strip()):
            alerts.append(alert)
    return alerts


def _sample_facilities_with_phone() -> list[HealthFacility]:
    facilities = []
    for facility in HealthFacility.objects.exclude(contact_phone="").select_related("ward").order_by("-updated_at")[:250]:
        if PHONE_CANDIDATE_PATTERN.match(facility.contact_phone.strip()):
            facilities.append(facility)
    return facilities


def _sample_coverage_requests_with_assignments() -> list[CHVCoverageRequest]:
    return list(
        CHVCoverageRequest.objects.filter(assignments__chv__phone_number__gt="")
        .select_related("ward", "requested_by", "assigned_to_user", "reviewed_by")
        .prefetch_related("assignments__chv", "assignments__ward", "events", "linked_alert_links__alert")
        .distinct()
        .order_by("-created_at")[:250]
    )


def _sample_ussd_logs_with_phone() -> list[UssdSessionLog]:
    logs = []
    for log in UssdSessionLog.objects.exclude(phone_number="").select_related("ward").order_by("-created_at")[:250]:
        if PHONE_CANDIDATE_PATTERN.match(log.phone_number.strip()):
            logs.append(log)
    return logs


def _record_serialized_phone_findings(
    *,
    gaps: list[dict],
    model_label: str,
    obj,
    serializer_name: str,
    serialized_payload,
    issue: str,
) -> None:
    for finding in _find_unmasked_phone_values(serialized_payload, path=serializer_name):
        gaps.append(
            {
                "model": model_label,
                "id": obj.id,
                "public_id": _public_ref(obj),
                "serializer_path": finding["path"],
                "value_length": finding["value_length"],
                "issues": [issue],
            }
        )
        if len(gaps) >= MAX_FINDINGS_PER_CHECK:
            return


def _audit_frontend_role_response_pii() -> dict:
    gaps: list[dict] = []
    sample_alerts = _sample_phone_alerts()
    sample_facilities = _sample_facilities_with_phone()
    sample_coverage_requests = _sample_coverage_requests_with_assignments()
    sample_ussd_logs = _sample_ussd_logs_with_phone()

    analyst_user = SimpleNamespace(
        role=User.ROLE_ANALYST,
        is_authenticated=True,
        is_active=True,
        username="privacy-audit-analyst-contract",
    )
    supervisor_user = SimpleNamespace(
        role=User.ROLE_SUPERVISOR,
        is_authenticated=True,
        is_active=True,
        username="privacy-audit-supervisor-contract",
    )
    analyst_request = SimpleNamespace(user=analyst_user)
    supervisor_request = SimpleNamespace(user=supervisor_user)
    inspected_count = 0
    for sample_alert in sample_alerts:
        inspected_count += 1
        serialized_alert = AlertSerializer(sample_alert, context={"request": analyst_request}).data
        serialized_intelligence = AlertIntelligenceSerializer(
            build_alert_intelligence_snapshot(sample_alert, ward_detail=sample_alert.ward, user=analyst_user),
            context={"request": analyst_request},
        ).data

        _record_serialized_phone_findings(
            gaps=gaps,
            model_label="risk.Alert",
            obj=sample_alert,
            serializer_name="AlertSerializer",
            serialized_payload=serialized_alert,
            issue="analyst-facing alert response contains an unmasked phone-like value",
        )
        if len(gaps) >= MAX_FINDINGS_PER_CHECK:
            break
        _record_serialized_phone_findings(
            gaps=gaps,
            model_label="risk.Alert",
            obj=sample_alert,
            serializer_name="AlertIntelligenceSerializer",
            serialized_payload=serialized_intelligence,
            issue="analyst-facing alert intelligence response contains an unmasked phone-like value",
        )
        if len(gaps) >= MAX_FINDINGS_PER_CHECK:
            break

    if len(gaps) < MAX_FINDINGS_PER_CHECK:
        for facility in sample_facilities:
            inspected_count += 1
            serialized_facility = HealthFacilitySerializer(facility, context={"request": analyst_request}).data
            serialized_intelligence = FacilityIntelligenceSerializer(
                build_facility_intelligence_snapshot(facility, user=analyst_user),
                context={"request": analyst_request},
            ).data

            _record_serialized_phone_findings(
                gaps=gaps,
                model_label="risk.HealthFacility",
                obj=facility,
                serializer_name="HealthFacilitySerializer",
                serialized_payload=serialized_facility,
                issue="analyst-facing facility response contains an unmasked phone-like value",
            )
            if len(gaps) >= MAX_FINDINGS_PER_CHECK:
                break
            _record_serialized_phone_findings(
                gaps=gaps,
                model_label="risk.HealthFacility",
                obj=facility,
                serializer_name="FacilityIntelligenceSerializer",
                serialized_payload=serialized_intelligence,
                issue="analyst-facing facility intelligence response contains an unmasked phone-like value",
            )
            if len(gaps) >= MAX_FINDINGS_PER_CHECK:
                break

    if len(gaps) < MAX_FINDINGS_PER_CHECK:
        for request_record in sample_coverage_requests:
            inspected_count += 1
            serialized_request = CHVCoverageRequestSerializer(
                request_record,
                context={"request": analyst_request},
            ).data
            _record_serialized_phone_findings(
                gaps=gaps,
                model_label="risk.CHVCoverageRequest",
                obj=request_record,
                serializer_name="CHVCoverageRequestSerializer",
                serialized_payload=serialized_request,
                issue="analyst-facing CHV coverage response contains an unmasked phone-like value",
            )
            if len(gaps) >= MAX_FINDINGS_PER_CHECK:
                break

    if len(gaps) < MAX_FINDINGS_PER_CHECK:
        for ussd_log in sample_ussd_logs:
            inspected_count += 1
            serialized_ussd_log = UssdSessionLogSerializer(
                ussd_log,
                context={"request": supervisor_request},
            ).data
            _record_serialized_phone_findings(
                gaps=gaps,
                model_label="risk.UssdSessionLog",
                obj=ussd_log,
                serializer_name="UssdSessionLogSerializer",
                serialized_payload=serialized_ussd_log,
                issue="supervisor-facing USSD log response contains an unmasked phone-like value",
            )
            if len(gaps) >= MAX_FINDINGS_PER_CHECK:
                break

    sample_available = bool(sample_alerts or sample_facilities or sample_coverage_requests or sample_ussd_logs)
    return _audit_check(
        check_id="frontend_role_response_pii",
        severity="high",
        gaps=gaps,
        pass_answer=(
            "Role-facing alert, facility, CHV coverage, and USSD serializers mask direct contact values."
            if sample_available
            else "No direct-identifier response sample exists; role-response PII contract check had no live sample to inspect."
        ),
        fail_answer="Role-facing serializers expose direct phone-like contact values.",
        evidence={
            "sample_available": sample_available,
            "alert_sample_count": len(sample_alerts),
            "facility_sample_count": len(sample_facilities),
            "coverage_request_sample_count": len(sample_coverage_requests),
            "ussd_log_sample_count": len(sample_ussd_logs),
            "inspected_count": inspected_count,
        },
    )


def _minimization_gap(obj, *, field_name: str, findings) -> dict:
    return {
        "model": obj._meta.label,
        "id": obj.id,
        "public_id": _public_ref(obj),
        "field": field_name,
        "issues": [f"{finding.location}: {finding.reason}" for finding in findings],
    }


def _scan_text_field(queryset, field_name: str, gaps: list[dict]) -> None:
    for obj in queryset.exclude(**{field_name: ""}).order_by("id").iterator(chunk_size=500):
        try:
            ensure_pii_safe_text(getattr(obj, field_name), location=field_name)
        except PrivacyMinimizationViolation as exc:
            gaps.append(_minimization_gap(obj, field_name=field_name, findings=exc.findings))
            if len(gaps) >= MAX_FINDINGS_PER_CHECK:
                return


def _scan_mapping_field(queryset, field_name: str, gaps: list[dict]) -> None:
    for obj in queryset.exclude(**{field_name: {}}).order_by("id").iterator(chunk_size=500):
        try:
            ensure_pii_safe_mapping(getattr(obj, field_name) or {}, location=field_name)
        except PrivacyMinimizationViolation as exc:
            gaps.append(_minimization_gap(obj, field_name=field_name, findings=exc.findings))
            if len(gaps) >= MAX_FINDINGS_PER_CHECK:
                return


def _audit_unsupported_free_text_notes() -> dict:
    gaps: list[dict] = []

    _scan_text_field(CHVMessage.objects.all(), "message_body", gaps)
    if len(gaps) < MAX_FINDINGS_PER_CHECK:
        _scan_text_field(CHVCoverageRequest.objects.all(), "reason", gaps)
    if len(gaps) < MAX_FINDINGS_PER_CHECK:
        _scan_text_field(CHVCoverageRequest.objects.all(), "notes", gaps)
    if len(gaps) < MAX_FINDINGS_PER_CHECK:
        _scan_text_field(PreparednessAction.objects.all(), "notes", gaps)
    if len(gaps) < MAX_FINDINGS_PER_CHECK:
        _scan_text_field(PreparednessAction.objects.all(), "cancellation_reason", gaps)
    if len(gaps) < MAX_FINDINGS_PER_CHECK:
        _scan_mapping_field(PreparednessAction.objects.all(), "completion_evidence", gaps)
    if len(gaps) < MAX_FINDINGS_PER_CHECK:
        _scan_mapping_field(PreparednessAction.objects.all(), "lineage_metadata", gaps)
    if len(gaps) < MAX_FINDINGS_PER_CHECK:
        _scan_mapping_field(PreparednessAction.objects.all(), "escalation_metadata", gaps)
    if len(gaps) < MAX_FINDINGS_PER_CHECK:
        _scan_text_field(PreparednessActionEvent.objects.all(), "detail", gaps)
    if len(gaps) < MAX_FINDINGS_PER_CHECK:
        _scan_mapping_field(PreparednessActionEvent.objects.all(), "metadata", gaps)
    if len(gaps) < MAX_FINDINGS_PER_CHECK:
        _scan_text_field(ContactPreference.objects.all(), "source_reference", gaps)
    if len(gaps) < MAX_FINDINGS_PER_CHECK:
        _scan_mapping_field(ContactPreference.objects.all(), "metadata", gaps)
    if len(gaps) < MAX_FINDINGS_PER_CHECK:
        _scan_text_field(ContactPreferenceAuditEvent.objects.all(), "reason", gaps)
    if len(gaps) < MAX_FINDINGS_PER_CHECK:
        _scan_mapping_field(ContactPreferenceAuditEvent.objects.all(), "metadata", gaps)

    return _audit_check(
        check_id="unsupported_free_text_medical_notes",
        severity="high",
        gaps=gaps,
        pass_answer="Unsupported workflow free-text and metadata fields pass minimization checks.",
        fail_answer="Unsupported workflow fields contain direct identifiers, exact household locations, or free-text medical notes.",
        evidence={
            "scanned_models": [
                "risk.CHVMessage",
                "risk.CHVCoverageRequest",
                "risk.PreparednessAction",
                "risk.PreparednessActionEvent",
                "risk.ContactPreference",
                "risk.ContactPreferenceAuditEvent",
            ],
            "max_reported_findings": MAX_FINDINGS_PER_CHECK,
        },
    )


def build_privacy_controls_audit(*, now=None, stale_sync_days: int = 30) -> dict:
    now = now or timezone.now()
    checks = [
        _audit_chv_assignment_scope(),
        _audit_household_message_consent(),
        _audit_contact_preference_phone_integrity(),
        _audit_sensitive_export_downloads(),
        _audit_stale_sync_payloads(now=now, stale_sync_days=stale_sync_days),
        _audit_frontend_role_response_pii(),
        _audit_unsupported_free_text_notes(),
    ]

    if any(check["status"] == "fail" for check in checks):
        overall_status = "fail"
    elif any(check["status"] == "warning" for check in checks):
        overall_status = "warning"
    else:
        overall_status = "pass"

    return {
        "overall_status": overall_status,
        "generated_at": _iso(now),
        "record_totals": {
            "chv_assignments": CHVAssignment.objects.count(),
            "chv_messages": CHVMessage.objects.count(),
            "household_contact_audit_events": ContactPreferenceAuditEvent.objects.filter(
                audience_type=ContactPreference.AUDIENCE_HOUSEHOLD
            ).count(),
            "sensitive_export_requests": SensitiveExportRequest.objects.count(),
            "sensitive_export_download_audits": SensitiveExportDownloadAudit.objects.count(),
            "sync_queue_items": SyncQueue.objects.count(),
            "preparedness_actions": PreparednessAction.objects.count(),
            "preparedness_action_events": PreparednessActionEvent.objects.count(),
            "alerts": Alert.objects.count(),
        },
        "high_risk_finding_count": sum(len(check["gaps"]) for check in checks if check["severity"] == "high"),
        "warning_finding_count": sum(len(check["gaps"]) for check in checks if check["status"] == "warning"),
        "audit_checks": checks,
        "operator_handling": {
            "doc_path": OPERATOR_HANDLING_DOC,
            "strict_command": "python manage.py audit_privacy_controls --strict",
            "stale_sync_days": stale_sync_days,
        },
    }
