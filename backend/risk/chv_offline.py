from __future__ import annotations

import hashlib
import hmac
import json
import re
import uuid
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Max, Q
from django.utils import timezone

from .chv_localization import (
    DEFAULT_CHV_LANGUAGE,
    LanguageResolution,
    resolve_language_preference,
)
from .models import (
    CHV,
    CHVAssignment,
    CHVDeviceRegistration,
    CHVOfflineRejectedSubmissionAudit,
    MessageTemplate,
    PreparednessAction,
    PreparednessActionEvent,
    SyncQueue,
    Ward,
)


OFFLINE_CHV_CONTRACT_VERSION = "chv-offline-v1"
OFFLINE_CHV_TASK_BUNDLE_SCHEMA_VERSION = "chv-task-bundle-v1"
OFFLINE_CHV_GUIDANCE_BUNDLE_SCHEMA_VERSION = "chv-guidance-bundle-v1"
OFFLINE_CHV_RULE_BUNDLE_VERSION = "cholera-triage-rules-v1"
OFFLINE_CHV_SYNC_HEALTH_SCHEMA_VERSION = "chv-sync-health-v1"
OFFLINE_CHV_UPLOAD_ENVELOPE_VERSION = "chv-upload-envelope-v1"
OFFLINE_CHV_UPLOAD_PAYLOAD_VERSION = "chv-upload-payload-v1"
OFFLINE_CHV_MONITORING_SCHEMA_VERSION = "chv-offline-monitoring-v1"
OFFLINE_CHV_ACTIVE_DEVICE_DAYS = 7
OFFLINE_CHV_STALE_BUNDLE_HOURS = 24
OFFLINE_CHV_MONITORING_WINDOW_HOURS = 24
OFFLINE_CHV_MONITORING_AUDIT_DAYS = 7
OFFLINE_CHV_REJECTED_UPLOAD_THRESHOLD = 3
OFFLINE_CHV_REJECTION_AUDIT_MAX_ITEMS = 20

OFFLINE_CHV_DECISION_SUPPORT_RECOMMENDATION_TEMPLATE_KEYS = {
    "urgent_referral": "cholera.chv.triage.urgent_referral_offline",
    "facility_assessment": "cholera.chv.triage.facility_assessment_offline",
    "ors_and_prevention": "cholera.chv.triage.ors_and_prevention_offline",
    "record_symptoms": "cholera.chv.triage.record_symptoms_offline",
}

SUPPORTED_PHASE_1_UPLOAD_TYPES = {
    SyncQueue.UPLOAD_SYMPTOM_TRIAGE,
    SyncQueue.UPLOAD_SUSPECTED_CASE_SIGNAL,
}
SUPPORTED_PHASE_4_UPLOAD_TYPES = {
    SyncQueue.UPLOAD_SYMPTOM_TRIAGE,
    SyncQueue.UPLOAD_SUSPECTED_CASE_SIGNAL,
    SyncQueue.UPLOAD_PREVENTION_VISIT,
    SyncQueue.UPLOAD_TASK_ACK,
    SyncQueue.UPLOAD_ALERT_ACK,
}
ACTION_SYNC_UPLOAD_TYPES = {
    SyncQueue.UPLOAD_PREVENTION_VISIT,
    SyncQueue.UPLOAD_TASK_ACK,
    SyncQueue.UPLOAD_ALERT_ACK,
}
SAFE_AUDIT_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
SAFE_FIELD_PATH_TOKEN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
PRIVACY_FINDING_LOCATION_RE = re.compile(r"(?:^|;\s+)([A-Za-z0-9_.\[\]-]+):\s")
PII_STAGE_HINTS = (
    "remove direct identifiers",
    "direct identifier",
    "contact details",
    "household location",
    "household_name",
    "household_head_name",
    "patient_name",
    "caregiver_name",
    "child_name",
    "national_id",
    "phone_number",
    "medical_notes",
    "clinical_notes",
    "gps",
    "coordinates",
)
REJECTION_STAGE_ERROR_CODES = {
    CHVOfflineRejectedSubmissionAudit.STAGE_ENVELOPE_VALIDATION: "chv_offline_envelope_validation_failed",
    CHVOfflineRejectedSubmissionAudit.STAGE_PAYLOAD_SCHEMA: "chv_offline_payload_schema_failed",
    CHVOfflineRejectedSubmissionAudit.STAGE_PII_MINIMIZATION: "chv_offline_pii_minimization_failed",
    CHVOfflineRejectedSubmissionAudit.STAGE_CONTRACT_VERSION: "chv_offline_contract_version_rejected",
    CHVOfflineRejectedSubmissionAudit.STAGE_WARD_SCOPE: "chv_offline_ward_scope_rejected",
    CHVOfflineRejectedSubmissionAudit.STAGE_DEVICE_REGISTRATION: "chv_offline_device_registration_rejected",
}


@dataclass(frozen=True)
class OfflineWorkflowDefinition:
    key: str
    title: str
    priority: int
    offline_required: bool
    upload_type: str
    minimum_capture: tuple[str, ...]
    risky_pii_fields: tuple[str, ...]
    phase_1_processing: str


OFFLINE_FIELD_WORKFLOWS: tuple[OfflineWorkflowDefinition, ...] = (
    OfflineWorkflowDefinition(
        key="assigned_follow_up_tasks",
        title="View assigned follow-up tasks",
        priority=1,
        offline_required=True,
        upload_type=SyncQueue.UPLOAD_TASK_ACK,
        minimum_capture=("task_public_id", "status", "recorded_at", "coded_reason"),
        risky_pii_fields=("household_name", "exact_household_location", "free_text_medical_notes"),
        phase_1_processing="contract_only",
    ),
    OfflineWorkflowDefinition(
        key="ward_guidance",
        title="Open ward guidance",
        priority=2,
        offline_required=True,
        upload_type="download_only",
        minimum_capture=("ward_public_id", "guidance_bundle_version", "downloaded_at"),
        risky_pii_fields=("household_contact", "patient_identifier", "free_text_notes"),
        phase_1_processing="download_bundle",
    ),
    OfflineWorkflowDefinition(
        key="symptom_triage",
        title="Triage suspected cholera symptoms",
        priority=3,
        offline_required=True,
        upload_type=SyncQueue.UPLOAD_SYMPTOM_TRIAGE,
        minimum_capture=("ward_id", "diarrhea", "vomiting", "dehydration", "fever", "recorded_at"),
        risky_pii_fields=("child_name", "caregiver_name", "patient_phone_in_notes", "clinical_notes"),
        phase_1_processing="accepted",
    ),
    OfflineWorkflowDefinition(
        key="household_prevention_visit",
        title="Record household prevention visit",
        priority=4,
        offline_required=True,
        upload_type=SyncQueue.UPLOAD_PREVENTION_VISIT,
        minimum_capture=(
            "task_public_id",
            "visit_completed",
            "households_reached_count",
            "messages_delivered_count",
            "recorded_at",
        ),
        risky_pii_fields=("household_head_name", "exact_address", "gps_coordinates", "household_phone"),
        phase_1_processing="contract_only",
    ),
    OfflineWorkflowDefinition(
        key="suspected_case_signal",
        title="Submit suspected-case signal",
        priority=5,
        offline_required=True,
        upload_type=SyncQueue.UPLOAD_SUSPECTED_CASE_SIGNAL,
        minimum_capture=("ward_id", "diarrhea", "vomiting", "dehydration", "fever", "recorded_at"),
        risky_pii_fields=("patient_name", "national_id", "exact_household_location", "medical_notes"),
        phase_1_processing="accepted",
    ),
    OfflineWorkflowDefinition(
        key="alert_follow_up_ack",
        title="Acknowledge alert follow-up",
        priority=6,
        offline_required=True,
        upload_type=SyncQueue.UPLOAD_ALERT_ACK,
        minimum_capture=("alert_public_id", "task_public_id", "acknowledgment_status", "recorded_at"),
        risky_pii_fields=("caller_phone", "household_name", "free_text_case_detail"),
        phase_1_processing="contract_only",
    ),
    OfflineWorkflowDefinition(
        key="sync_later",
        title="Sync later when connectivity returns",
        priority=7,
        offline_required=True,
        upload_type="sync_health",
        minimum_capture=("idempotency_key", "client_submission_id", "created_at", "retry_count"),
        risky_pii_fields=("raw_payload_after_retention", "unredacted_error_message", "stale_free_text"),
        phase_1_processing="accepted",
    ),
)


def workflow_audit_payload() -> list[dict]:
    return [asdict(workflow) for workflow in sorted(OFFLINE_FIELD_WORKFLOWS, key=lambda item: item.priority)]


def sync_contract_payload() -> dict:
    return {
        "device_registration": {
            "version": "chv-device-registration-v1",
            "required_fields": ["device_id", "contract_version"],
            "optional_fields": ["app_version", "platform", "metadata"],
            "scope_rule": "device registration is pinned to the authenticated user's assigned ward",
        },
        "user_session_scope": {
            "version": "chv-session-scope-v1",
            "required_fields": ["user_id", "role", "ward_id", "ward_public_id", "scope_key", "language"],
            "privacy_rule": "no phone number or household identifier is required in the bundle scope",
        },
        "language_preference": {
            "version": "chv-language-preference-v1",
            "supported_languages": ["en", "sw", "luo"],
            "default_language": "en",
            "fields": ["requested_language", "resolved_language", "fallback_used"],
        },
        "download_bundle_version": {
            "version": "chv-download-bundle-v1",
            "contents": ["task_bundle", "guidance_bundle", "decision_support_rule_bundle"],
            "stale_after_hours": 24,
        },
        "task_bundle": {
            "version": OFFLINE_CHV_TASK_BUNDLE_SCHEMA_VERSION,
            "scope_rule": "CHV users receive only tasks explicitly assigned to their user or CHV roster identity",
        },
        "guidance_bundle": {
            "version": OFFLINE_CHV_GUIDANCE_BUNDLE_SCHEMA_VERSION,
            "source": "approved offline_chv_bundle message templates; missing governed content fails closed with content_unavailable metadata",
        },
        "decision_support_rule_bundle": {
            "version": OFFLINE_CHV_RULE_BUNDLE_VERSION,
            "boundary_code": "chv_decision_support_not_diagnosis",
            "display_copy_rule": "CHV-visible decision-support copy must come from approved offline_chv_bundle recommendation templates.",
        },
        "upload_envelope": {
            "version": OFFLINE_CHV_UPLOAD_ENVELOPE_VERSION,
            "payload_version": OFFLINE_CHV_UPLOAD_PAYLOAD_VERSION,
            "required_fields": ["client_submission_id", "idempotency_key", "upload_type", "payload"],
            "supported_phase_1_upload_types": sorted(SUPPORTED_PHASE_1_UPLOAD_TYPES),
            "supported_phase_4_upload_types": sorted(SUPPORTED_PHASE_4_UPLOAD_TYPES),
        },
        "idempotency_key": {
            "version": "chv-idempotency-v1",
            "scope": "source_device_id + idempotency_key",
            "fallback_scope": "source_device_id + client_submission_id for legacy clients",
        },
        "conflict_state": {
            "version": "chv-conflict-state-v1",
            "states": [choice[0] for choice in SyncQueue.CONFLICT_CHOICES],
        },
        "server_receipt": {
            "version": "chv-server-receipt-v1",
            "fields": ["receipt_id", "accepted_at", "status", "replayed", "domain_record"],
        },
        "sync_health_record": {
            "version": OFFLINE_CHV_SYNC_HEALTH_SCHEMA_VERSION,
            "fields": ["last_successful_sync_at", "pending_upload_count", "failed_upload_count", "sync_health"],
        },
    }


def _json_hash(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def resolve_chv_for_user(user, ward: Ward) -> CHV | None:
    phone_number = (getattr(user, "phone_number", "") or "").strip()
    queryset = CHV.objects.filter(ward=ward, is_active=True)
    if phone_number:
        chv = queryset.filter(phone_number=phone_number).first()
        if chv is not None:
            return chv
    return None


def resolve_chv_language_for_user(
    user,
    ward: Ward,
    *,
    requested_language: str | None = None,
    device_registration: CHVDeviceRegistration | None = None,
    chv: CHV | None = None,
) -> LanguageResolution:
    return resolve_language_preference(
        requested_language=requested_language,
        device_registration=device_registration,
        chv=chv if chv is not None else resolve_chv_for_user(user, ward),
        user=user,
    )


def build_session_scope(user, ward: Ward, *, language_resolution: LanguageResolution | None = None) -> dict:
    chv = resolve_chv_for_user(user, ward)
    chv_public_id = str(chv.public_id) if chv else None
    scope_key = f"ward:{ward.public_id}:chv:{chv_public_id or f'user-{user.id}'}"
    language_metadata = language_resolution.as_metadata() if language_resolution is not None else {}
    return {
        "user_id": user.id,
        "role": getattr(user, "role", ""),
        "ward_id": ward.id,
        "ward_public_id": str(ward.public_id),
        "ward_name": ward.name,
        "county": ward.county,
        "sub_county": ward.sub_county,
        "chv_public_id": chv_public_id,
        "scope_type": "assigned_chv_ward" if chv else "assigned_user_ward",
        "scope_key": scope_key,
        "language": language_metadata,
    }


def _task_from_preparedness_action(action: PreparednessAction) -> dict:
    return {
        "task_public_id": str(action.public_id),
        "task_type": "preparedness_action",
        "action_type": action.action_type,
        "source_trigger_type": action.source_trigger_type,
        "status": action.status,
        "priority": action.priority,
        "ward_id": action.ward_id,
        "ward_public_id": str(action.ward.public_id),
        "due_at": action.due_at,
        "allowed_upload_types": [SyncQueue.UPLOAD_TASK_ACK, SyncQueue.UPLOAD_PREVENTION_VISIT],
        "minimum_capture": ["task_public_id", "status", "coded_reason", "recorded_at"],
    }


def _task_from_assignment(assignment: CHVAssignment) -> dict:
    return {
        "task_public_id": str(assignment.public_id),
        "task_type": "chv_coverage_assignment",
        "coverage_request_public_id": str(assignment.coverage_request.public_id),
        "status": assignment.status,
        "priority": assignment.coverage_request.priority,
        "ward_id": assignment.ward_id,
        "ward_public_id": str(assignment.ward.public_id),
        "start_at": assignment.start_at,
        "end_at": assignment.end_at,
        "allowed_upload_types": [SyncQueue.UPLOAD_TASK_ACK, SyncQueue.UPLOAD_ALERT_ACK],
        "minimum_capture": ["task_public_id", "acknowledgment_status", "recorded_at"],
    }


def build_task_bundle(
    user,
    ward: Ward,
    *,
    language_resolution: LanguageResolution | None = None,
) -> dict:
    language_resolution = language_resolution or resolve_chv_language_for_user(user, ward)
    chv = resolve_chv_for_user(user, ward)
    action_queryset = (
        PreparednessAction.objects.filter(ward=ward, status__in=PreparednessAction.ACTIVE_STATUSES)
        .select_related("ward", "chv")
        .order_by("due_at", "-created_at")
    )
    assignment_queryset = (
        CHVAssignment.objects.filter(ward=ward, status=CHVAssignment.STATUS_ACTIVE)
        .select_related("ward", "chv", "coverage_request")
        .order_by("start_at", "-created_at")
    )

    if getattr(user, "role", "") == "CHV":
        if chv is None:
            action_queryset = action_queryset.none()
            assignment_queryset = assignment_queryset.none()
        else:
            action_queryset = action_queryset.filter(Q(chv=chv) | Q(assigned_to=user))
            assignment_queryset = assignment_queryset.filter(chv=chv)

    action_tasks = [_task_from_preparedness_action(action) for action in action_queryset[:100]]
    assignment_tasks = [_task_from_assignment(assignment) for assignment in assignment_queryset[:100]]

    return {
        "schema_version": OFFLINE_CHV_TASK_BUNDLE_SCHEMA_VERSION,
        "scope_key": build_session_scope(user, ward, language_resolution=language_resolution)["scope_key"],
        "requested_language": language_resolution.requested_language,
        "resolved_language": language_resolution.resolved_language,
        "fallback_used": language_resolution.fallback_used,
        "language": language_resolution.as_metadata(),
        "tasks": [*action_tasks, *assignment_tasks],
        "retention_rule": "keep assigned task metadata until successful sync plus 7 days, then purge local details",
    }


def _select_guidance_templates(language_resolution: LanguageResolution):
    requested_language = language_resolution.resolved_language
    queryset = MessageTemplate.objects.filter(
        channel=MessageTemplate.CHANNEL_OFFLINE_CHV_BUNDLE,
        approval_status=MessageTemplate.APPROVAL_APPROVED,
        retired_at__isnull=True,
        audience_type__in=[MessageTemplate.AUDIENCE_CHV, MessageTemplate.AUDIENCE_HOUSEHOLD],
    ).exclude(
        template_key__in=OFFLINE_CHV_DECISION_SUPPORT_RECOMMENDATION_TEMPLATE_KEYS.values(),
    ).filter(
        Q(language=DEFAULT_CHV_LANGUAGE)
        | Q(
            language=requested_language,
            translation_status=MessageTemplate.TRANSLATION_APPROVED,
            source_template__isnull=False,
            source_template__approval_status=MessageTemplate.APPROVAL_APPROVED,
            source_template__retired_at__isnull=True,
        )
    ).order_by(
        "template_key",
        "-version",
        "language",
    )

    selected_by_key: dict[str, MessageTemplate] = {}
    for template in queryset[:200]:
        existing = selected_by_key.get(template.template_key)
        if existing is None:
            selected_by_key[template.template_key] = template
            continue
        if existing.language != requested_language and template.language == requested_language:
            selected_by_key[template.template_key] = template
    return list(selected_by_key.values())


def build_guidance_bundle(
    user,
    ward: Ward,
    *,
    language_resolution: LanguageResolution | None = None,
) -> dict:
    language_resolution = language_resolution or resolve_chv_language_for_user(user, ward)
    templates = _select_guidance_templates(language_resolution)

    guidance_items = [
        {
            "guidance_public_id": str(template.public_id),
            "template_key": template.template_key,
            "language": template.language,
            "requested_language": language_resolution.requested_language,
            "resolved_language": template.language,
            "fallback_used": language_resolution.fallback_used or template.language != language_resolution.requested_language,
            "version": template.version,
            "audience_type": template.audience_type,
            "title": template.title,
            "body": template.body,
            "public_health_caveats": template.public_health_caveats,
        }
        for template in templates[:50]
    ]

    bundle_resolved_language = (
        language_resolution.resolved_language
        if any(item["language"] == language_resolution.resolved_language for item in guidance_items)
        else DEFAULT_CHV_LANGUAGE
    )
    bundle_fallback_used = (
        language_resolution.fallback_used
        or any(item["fallback_used"] for item in guidance_items)
        or bundle_resolved_language != language_resolution.requested_language
    )

    return {
        "schema_version": OFFLINE_CHV_GUIDANCE_BUNDLE_SCHEMA_VERSION,
        "ward_public_id": str(ward.public_id),
        "requested_language": language_resolution.requested_language,
        "resolved_language": bundle_resolved_language,
        "fallback_used": bundle_fallback_used,
        "content_unavailable": not guidance_items,
        "governance_status": "approved" if guidance_items else "no_approved_guidance_templates",
        "items": guidance_items,
        "retention_rule": "replace when a newer bundle version is downloaded or after 24 hours without refresh",
    }


def _select_decision_support_recommendation_templates(language_resolution: LanguageResolution):
    requested_language = language_resolution.resolved_language
    required_template_keys = set(OFFLINE_CHV_DECISION_SUPPORT_RECOMMENDATION_TEMPLATE_KEYS.values())
    english_sources = MessageTemplate.objects.filter(
        channel=MessageTemplate.CHANNEL_OFFLINE_CHV_BUNDLE,
        audience_type=MessageTemplate.AUDIENCE_CHV,
        template_key__in=required_template_keys,
        language=DEFAULT_CHV_LANGUAGE,
        approval_status=MessageTemplate.APPROVAL_APPROVED,
        retired_at__isnull=True,
    ).order_by("template_key", "-version")

    source_by_key: dict[str, MessageTemplate] = {}
    for source in english_sources:
        source_by_key.setdefault(source.template_key, source)

    selected: dict[str, MessageTemplate] = {}
    for recommendation_key, template_key in OFFLINE_CHV_DECISION_SUPPORT_RECOMMENDATION_TEMPLATE_KEYS.items():
        source = source_by_key.get(template_key)
        if source is None:
            continue
        if requested_language == DEFAULT_CHV_LANGUAGE:
            selected[recommendation_key] = source
            continue
        translation = MessageTemplate.objects.filter(
            channel=MessageTemplate.CHANNEL_OFFLINE_CHV_BUNDLE,
            audience_type=MessageTemplate.AUDIENCE_CHV,
            template_key=template_key,
            version=source.version,
            language=requested_language,
            approval_status=MessageTemplate.APPROVAL_APPROVED,
            translation_status=MessageTemplate.TRANSLATION_APPROVED,
            source_template=source,
            retired_at__isnull=True,
            source_template__approval_status=MessageTemplate.APPROVAL_APPROVED,
            source_template__retired_at__isnull=True,
        ).first()
        selected[recommendation_key] = translation or source
    return selected


def _decision_support_recommendation_items(language_resolution: LanguageResolution) -> list[dict]:
    selected_templates = _select_decision_support_recommendation_templates(language_resolution)
    items: list[dict] = []
    for recommendation_key, template_key in OFFLINE_CHV_DECISION_SUPPORT_RECOMMENDATION_TEMPLATE_KEYS.items():
        template = selected_templates.get(recommendation_key)
        if template is None:
            continue
        items.append(
            {
                "recommendation_public_id": str(template.public_id),
                "recommendation_key": recommendation_key,
                "template_key": template.template_key,
                "language": template.language,
                "requested_language": language_resolution.requested_language,
                "resolved_language": template.language,
                "fallback_used": language_resolution.fallback_used
                or template.language != language_resolution.requested_language,
                "version": template.version,
                "audience_type": template.audience_type,
                "title": template.title,
                "body": template.body,
                "public_health_caveats": template.public_health_caveats,
                "source": "governed_message_template",
                "governance_status": "approved",
            }
        )
    return items


def build_decision_support_rule_bundle(
    *,
    language_resolution: LanguageResolution | None = None,
) -> dict:
    language_resolution = language_resolution or LanguageResolution(
        requested_language=DEFAULT_CHV_LANGUAGE,
        resolved_language=DEFAULT_CHV_LANGUAGE,
        fallback_used=False,
        preference_source="default",
    )
    recommendations = _decision_support_recommendation_items(language_resolution)
    missing_recommendation_keys = [
        recommendation_key
        for recommendation_key in OFFLINE_CHV_DECISION_SUPPORT_RECOMMENDATION_TEMPLATE_KEYS
        if not any(item["recommendation_key"] == recommendation_key for item in recommendations)
    ]
    bundle_resolved_language = (
        language_resolution.resolved_language
        if any(item["language"] == language_resolution.resolved_language for item in recommendations)
        else DEFAULT_CHV_LANGUAGE
    )
    bundle_fallback_used = (
        language_resolution.fallback_used
        or any(item["fallback_used"] for item in recommendations)
        or bundle_resolved_language != language_resolution.requested_language
    )
    return {
        "version": OFFLINE_CHV_RULE_BUNDLE_VERSION,
        "requested_language": language_resolution.requested_language,
        "resolved_language": bundle_resolved_language,
        "fallback_used": bundle_fallback_used,
        "content_unavailable": bool(missing_recommendation_keys),
        "governance_status": "approved" if not missing_recommendation_keys else "missing_required_recommendation_templates",
        "missing_recommendation_keys": missing_recommendation_keys,
        "rules": [
            {
                "rule_id": "danger_sign_referral",
                "when": {"dehydration": True, "any_of": ["diarrhea", "vomiting"]},
                "then": {"referral_needed": True, "recommendation_key": "urgent_referral"},
            },
            {
                "rule_id": "cholera_symptom_cluster",
                "when": {"diarrhea": True, "any_of": ["vomiting", "fever"]},
                "then": {"referral_needed": True, "recommendation_key": "facility_assessment"},
            },
            {
                "rule_id": "diarrhea_prevention_advice",
                "when": {"diarrhea": True},
                "then": {"referral_needed": False, "recommendation_key": "ors_and_prevention"},
            },
        ],
        "recommendations": recommendations,
        "medical_boundary": {
            "code": "chv_decision_support_not_diagnosis",
            "display_copy_rule": "Render CHV-visible boundary copy only from governed templates.",
        },
    }


def build_download_bundle(
    user,
    ward: Ward,
    *,
    language_resolution: LanguageResolution | None = None,
) -> dict:
    now = timezone.now()
    language_resolution = language_resolution or resolve_chv_language_for_user(user, ward)
    task_bundle = build_task_bundle(user, ward, language_resolution=language_resolution)
    guidance_bundle = build_guidance_bundle(user, ward, language_resolution=language_resolution)
    rule_bundle = build_decision_support_rule_bundle(language_resolution=language_resolution)
    task_updated_at = PreparednessAction.objects.filter(ward=ward).aggregate(Max("updated_at"))["updated_at__max"]
    assignment_updated_at = CHVAssignment.objects.filter(ward=ward).aggregate(Max("updated_at"))["updated_at__max"]
    guidance_updated_at = MessageTemplate.objects.filter(
        channel=MessageTemplate.CHANNEL_OFFLINE_CHV_BUNDLE,
        approval_status=MessageTemplate.APPROVAL_APPROVED,
        retired_at__isnull=True,
    ).aggregate(Max("updated_at"))["updated_at__max"]
    fingerprint = {
        "contract_version": OFFLINE_CHV_CONTRACT_VERSION,
        "ward_public_id": str(ward.public_id),
        "task_count": len(task_bundle["tasks"]),
        "task_updated_at": task_updated_at,
        "assignment_updated_at": assignment_updated_at,
        "guidance_updated_at": guidance_updated_at,
        "guidance_items": [
            (item["template_key"], item["language"], item["version"]) for item in guidance_bundle["items"]
        ],
        "decision_support_recommendations": [
            (item["recommendation_key"], item["template_key"], item["language"], item["version"], item["governance_status"])
            for item in rule_bundle["recommendations"]
        ],
        "requested_language": language_resolution.requested_language,
        "resolved_language": guidance_bundle["resolved_language"],
        "language_fallback_used": guidance_bundle["fallback_used"] or rule_bundle["fallback_used"],
        "rule_version": rule_bundle["version"],
    }
    version = f"chv-bundle-{_json_hash(fingerprint)[:16]}"
    return {
        "version": version,
        "generated_at": now,
        "expires_at": now + timedelta(hours=24),
        "requested_language": language_resolution.requested_language,
        "resolved_language": guidance_bundle["resolved_language"],
        "fallback_used": guidance_bundle["fallback_used"] or rule_bundle["fallback_used"],
        "task_bundle": task_bundle,
        "guidance_bundle": guidance_bundle,
        "decision_support_rule_bundle": rule_bundle,
    }


def _record_offline_bundle_request(
    registration: CHVDeviceRegistration | None,
    *,
    language_resolution: LanguageResolution,
    download_bundle: dict,
) -> None:
    if registration is None:
        return

    now = timezone.now()
    requested_language = language_resolution.requested_language
    resolved_language = download_bundle["resolved_language"]
    fallback_used = bool(language_resolution.fallback_used or download_bundle["fallback_used"])
    metadata = dict(registration.metadata or {})
    language_metadata = metadata.get("language") if isinstance(metadata.get("language"), dict) else {}
    request_counts = metadata.get("offline_bundle_request_counts")
    if not isinstance(request_counts, list):
        request_counts = []

    matched = False
    for entry in request_counts:
        if not isinstance(entry, dict):
            continue
        if (
            entry.get("requested_language") == requested_language
            and entry.get("resolved_language") == resolved_language
            and bool(entry.get("fallback_used")) == fallback_used
        ):
            try:
                entry["count"] = int(entry.get("count", 0)) + 1
            except (TypeError, ValueError):
                entry["count"] = 1
            matched = True
            break
    if not matched:
        request_counts.append(
            {
                "requested_language": requested_language,
                "resolved_language": resolved_language,
                "fallback_used": fallback_used,
                "count": 1,
            }
        )

    metadata["offline_bundle_request_counts"] = request_counts
    metadata["last_offline_bundle_request"] = {
        "requested_language": requested_language,
        "resolved_language": resolved_language,
        "fallback_used": fallback_used,
        "bundle_version": download_bundle["version"],
        "requested_at": now.isoformat(),
    }
    metadata["language"] = {
        **language_metadata,
        **language_resolution.as_metadata(),
        "bundle_resolved_language": resolved_language,
        "bundle_fallback_used": download_bundle["fallback_used"],
    }
    registration.metadata = metadata
    registration.last_bundle_version = download_bundle["version"]
    registration.last_seen_at = now
    registration.save(update_fields=["metadata", "last_bundle_version", "last_seen_at", "updated_at"])


def build_sync_health_record(
    *,
    ward: Ward,
    device_registration: CHVDeviceRegistration | None = None,
    source_device_id: str = "",
    phone_number: str = "",
) -> dict:
    queryset = SyncQueue.objects.filter(ward=ward)
    if device_registration is not None:
        queryset = queryset.filter(device_registration=device_registration)
    elif source_device_id:
        queryset = queryset.filter(source_device_id=source_device_id)
    elif phone_number:
        queryset = queryset.filter(phone_number=phone_number)
    else:
        queryset = queryset.none()

    last_successful_sync_at = queryset.filter(status=SyncQueue.STATUS_PROCESSED).aggregate(Max("processed_at"))[
        "processed_at__max"
    ]
    pending_count = queryset.filter(status=SyncQueue.STATUS_PENDING).count()
    failed_count = queryset.filter(status=SyncQueue.STATUS_FAILED).count()
    if last_successful_sync_at is None:
        sync_health = "OFFLINE"
    elif timezone.now() - last_successful_sync_at <= timedelta(minutes=30):
        sync_health = "ONLINE"
    elif timezone.now() - last_successful_sync_at <= timedelta(hours=6):
        sync_health = "DELAYED"
    else:
        sync_health = "OFFLINE"

    return {
        "schema_version": OFFLINE_CHV_SYNC_HEALTH_SCHEMA_VERSION,
        "last_successful_sync_at": last_successful_sync_at,
        "pending_upload_count": pending_count,
        "failed_upload_count": failed_count,
        "sync_health": sync_health,
    }


def build_chv_offline_contract(
    user,
    ward: Ward,
    *,
    requested_language: str | None = None,
    device_registration: CHVDeviceRegistration | None = None,
) -> dict:
    language_resolution = resolve_chv_language_for_user(
        user,
        ward,
        requested_language=requested_language,
        device_registration=device_registration,
    )
    download_bundle = build_download_bundle(user, ward, language_resolution=language_resolution)
    _record_offline_bundle_request(
        device_registration,
        language_resolution=language_resolution,
        download_bundle=download_bundle,
    )
    return {
        "contract_version": OFFLINE_CHV_CONTRACT_VERSION,
        "generated_at": timezone.now(),
        "requested_language": language_resolution.requested_language,
        "resolved_language": download_bundle["resolved_language"],
        "fallback_used": language_resolution.fallback_used or download_bundle["fallback_used"],
        "language": {
            **language_resolution.as_metadata(),
            "bundle_resolved_language": download_bundle["resolved_language"],
            "bundle_fallback_used": download_bundle["fallback_used"],
        },
        "workflow_audit": workflow_audit_payload(),
        "sync_contracts": sync_contract_payload(),
        "session_scope": build_session_scope(user, ward, language_resolution=language_resolution),
        "download_bundle": download_bundle,
        "sync_health_record": build_sync_health_record(
            ward=ward,
            phone_number=(getattr(user, "phone_number", "") or "").strip(),
        ),
    }


def register_chv_device(
    *,
    user,
    ward: Ward,
    device_id: str,
    contract_version: str,
    app_version: str = "",
    platform: str = CHVDeviceRegistration.PLATFORM_UNKNOWN,
    preferred_language: str = "",
    metadata: dict | None = None,
) -> CHVDeviceRegistration:
    chv = resolve_chv_for_user(user, ward)
    language_resolution = resolve_chv_language_for_user(
        user,
        ward,
        requested_language=preferred_language,
        chv=chv,
    )
    download_bundle = build_download_bundle(user, ward, language_resolution=language_resolution)
    normalized_platform = (platform or CHVDeviceRegistration.PLATFORM_UNKNOWN).strip().upper()
    valid_platforms = {choice[0] for choice in CHVDeviceRegistration.PLATFORM_CHOICES}
    if normalized_platform not in valid_platforms:
        normalized_platform = CHVDeviceRegistration.PLATFORM_UNKNOWN
    registration, _created = CHVDeviceRegistration.objects.update_or_create(
        user=user,
        device_id=device_id.strip(),
        defaults={
            "chv": chv,
            "ward": ward,
            "contract_version": contract_version.strip() or OFFLINE_CHV_CONTRACT_VERSION,
            "app_version": app_version.strip(),
            "platform": normalized_platform,
            "preferred_language": language_resolution.resolved_language,
            "last_bundle_version": download_bundle["version"],
            "last_seen_at": timezone.now(),
            "is_active": True,
            "metadata": {
                **(metadata or {}),
                "language": language_resolution.as_metadata(),
            },
        },
    )
    return registration


def device_registration_payload(registration: CHVDeviceRegistration, user) -> dict:
    ward = registration.ward
    language_resolution = resolve_chv_language_for_user(
        user,
        ward,
        requested_language=registration.preferred_language,
        device_registration=registration,
    )
    return {
        "public_id": str(registration.public_id),
        "device_id": registration.device_id,
        "contract_version": registration.contract_version,
        "app_version": registration.app_version,
        "platform": registration.platform,
        "preferred_language": registration.preferred_language,
        "requested_language": language_resolution.requested_language,
        "resolved_language": language_resolution.resolved_language,
        "fallback_used": language_resolution.fallback_used,
        "language": language_resolution.as_metadata(),
        "is_active": registration.is_active,
        "registered_at": registration.registered_at,
        "last_seen_at": registration.last_seen_at,
        "last_sync_at": registration.last_sync_at,
        "download_bundle_version": registration.last_bundle_version,
        "session_scope": build_session_scope(
            user,
            ward,
            language_resolution=language_resolution,
        ),
        "sync_health_record": build_sync_health_record(ward=ward, device_registration=registration),
    }


def _isoformat_or_none(value) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _safe_audit_identifier(value: object, max_length: int) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if not text or len(text) > max_length:
        return ""
    if not SAFE_AUDIT_IDENTIFIER_RE.match(text):
        return ""
    return text


def _canonical_payload_bytes(payload: object) -> bytes:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return encoded.encode("utf-8")


def _request_body_hmac(request, raw_payload: object) -> str:
    body = b""
    try:
        body = request.body
    except Exception:
        body = b""
    if not body:
        body = _canonical_payload_bytes(raw_payload if raw_payload is not None else {})
    secret = str(settings.SECRET_KEY).encode("utf-8")
    return hmac.new(secret, body, hashlib.sha256).hexdigest()


def _safe_request_metadata(request) -> dict:
    return {
        "method": getattr(request, "method", ""),
        "path": getattr(request, "path", ""),
        "content_type": (getattr(request, "content_type", "") or "")[:120],
    }


def _trusted_rejection_ward(user, raw_payload: Mapping | None) -> Ward | None:
    role = getattr(user, "role", "")
    user_ward_id = getattr(user, "ward_id", None)
    if role in {"CHV", "SUPERVISOR"} and user_ward_id:
        return Ward.objects.filter(id=user_ward_id, is_active=True).first()

    raw_payload = raw_payload or {}
    ward_id = raw_payload.get("ward_id")
    session_scope = raw_payload.get("session_scope")
    if ward_id is None and isinstance(session_scope, Mapping):
        ward_id = session_scope.get("ward_id")
    try:
        ward_id = int(ward_id)
    except (TypeError, ValueError):
        return None
    return Ward.objects.filter(id=ward_id, is_active=True).first()


def _trusted_rejection_device_registration(user, raw_payload: Mapping | None, ward: Ward | None) -> CHVDeviceRegistration | None:
    raw_payload = raw_payload or {}
    raw_public_id = raw_payload.get("device_registration_id")
    if not raw_public_id:
        return None
    try:
        registration_public_id = uuid.UUID(str(raw_public_id))
    except (TypeError, ValueError):
        return None

    queryset = CHVDeviceRegistration.objects.filter(public_id=registration_public_id, is_active=True)
    if getattr(user, "is_authenticated", False):
        queryset = queryset.filter(user=user)
    if ward is not None:
        queryset = queryset.filter(ward=ward)
    return queryset.select_related("ward", "chv").first()


def _normalize_error_path(path: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.\[\]-]", "", path).strip(".")[:160]


def _append_error_path(paths: list[str], path: str) -> None:
    normalized = _normalize_error_path(path)
    if normalized and normalized not in paths:
        paths.append(normalized)


def _privacy_location_path(prefix: str, location: str) -> str:
    if not prefix:
        return location
    if location == prefix or location.startswith(f"{prefix}."):
        return location
    if location.startswith("payload.") and (prefix == "payload" or prefix.endswith(".payload")):
        root = prefix[: -len("payload")].rstrip(".")
        return f"{root}.{location}" if root else location
    return f"{prefix}.{location}"


def _collect_rejection_field_paths(errors: object, prefix: str = "") -> list[str]:
    paths: list[str] = []
    if isinstance(errors, Mapping):
        for key, value in errors.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            for path in _collect_rejection_field_paths(value, child_prefix):
                _append_error_path(paths, path)
        return paths

    if isinstance(errors, (list, tuple)):
        for index, value in enumerate(errors):
            if isinstance(value, (Mapping, list, tuple)):
                child_prefix = f"{prefix}.{index}" if prefix else str(index)
                for path in _collect_rejection_field_paths(value, child_prefix):
                    _append_error_path(paths, path)
                continue

            text = str(value)
            if prefix:
                _append_error_path(paths, prefix)
            if prefix and SAFE_FIELD_PATH_TOKEN_RE.fullmatch(text):
                _append_error_path(paths, f"{prefix}.{text}")
            for location in PRIVACY_FINDING_LOCATION_RE.findall(text):
                _append_error_path(paths, _privacy_location_path(prefix, location))
        return paths

    if prefix:
        _append_error_path(paths, prefix)
    return paths


def chv_offline_rejection_field_paths(serializer_errors: object) -> list[str]:
    paths: list[str] = []
    for path in _collect_rejection_field_paths(serializer_errors):
        _append_error_path(paths, path)
    return paths[:50]


def classify_chv_offline_rejection_stage(serializer_errors: object) -> str:
    error_text = json.dumps(serializer_errors, default=str).lower()
    if any(hint in error_text for hint in PII_STAGE_HINTS):
        return CHVOfflineRejectedSubmissionAudit.STAGE_PII_MINIMIZATION

    field_paths = chv_offline_rejection_field_paths(serializer_errors)
    if any(path.startswith(("uploads", "payloads", "payload")) for path in field_paths):
        return CHVOfflineRejectedSubmissionAudit.STAGE_PAYLOAD_SCHEMA
    if any(path == "source_device_id" or path.startswith("source_device_id.") for path in field_paths):
        return CHVOfflineRejectedSubmissionAudit.STAGE_ENVELOPE_VALIDATION
    if "device_registration_id" in error_text:
        return CHVOfflineRejectedSubmissionAudit.STAGE_DEVICE_REGISTRATION
    return CHVOfflineRejectedSubmissionAudit.STAGE_ENVELOPE_VALIDATION


def _rejected_upload_items(raw_payload: Mapping | None) -> list[Mapping]:
    raw_payload = raw_payload or {}
    items: list[Mapping] = []
    for collection_key in ("uploads", "payloads"):
        collection = raw_payload.get(collection_key)
        if isinstance(collection, list):
            items.extend(item if isinstance(item, Mapping) else {} for item in collection)
    return (items or [{}])[:OFFLINE_CHV_REJECTION_AUDIT_MAX_ITEMS]


def record_chv_offline_rejected_submission_audit(
    *,
    request,
    raw_payload: object,
    serializer_errors: object | None = None,
    rejection_stage: str | None = None,
    error_code: str = "",
    safe_error_summary: str = "",
    status_code: int = 400,
    ward: Ward | None = None,
    device_registration: CHVDeviceRegistration | None = None,
) -> list[CHVOfflineRejectedSubmissionAudit]:
    raw_mapping = raw_payload if isinstance(raw_payload, Mapping) else {}
    user = request.user if getattr(getattr(request, "user", None), "is_authenticated", False) else None
    audit_ward = ward or _trusted_rejection_ward(user, raw_mapping)
    audit_device_registration = device_registration or _trusted_rejection_device_registration(user, raw_mapping, audit_ward)
    source_device_id = _safe_audit_identifier(raw_mapping.get("source_device_id"), 120)
    if not source_device_id and audit_device_registration is not None:
        source_device_id = audit_device_registration.device_id

    stage = rejection_stage or classify_chv_offline_rejection_stage(serializer_errors or {})
    summary = safe_error_summary or f"Rejected before sync persistence during {stage.lower()}."
    field_paths = chv_offline_rejection_field_paths(serializer_errors or {})
    request_hmac = _request_body_hmac(request, raw_payload)
    request_metadata = _safe_request_metadata(request)
    contract_version = _safe_audit_identifier(raw_mapping.get("contract_version"), 64)
    created: list[CHVOfflineRejectedSubmissionAudit] = []

    for item in _rejected_upload_items(raw_mapping):
        created.append(
            CHVOfflineRejectedSubmissionAudit.objects.create(
                user=user,
                ward=audit_ward,
                device_registration=audit_device_registration,
                source_device_id=source_device_id,
                client_submission_id=_safe_audit_identifier(item.get("client_submission_id"), 120),
                idempotency_key=_safe_audit_identifier(item.get("idempotency_key"), 160),
                upload_type=_safe_audit_identifier(item.get("upload_type"), 40),
                contract_version=contract_version,
                rejection_stage=stage,
                error_code=error_code or REJECTION_STAGE_ERROR_CODES.get(stage, "chv_offline_rejected_before_sync"),
                safe_error_summary=summary,
                field_paths=field_paths,
                status_code=status_code,
                request_body_hmac=request_hmac,
                request_metadata=request_metadata,
            )
        )

    return created


def _sync_domain_record(sync_item: SyncQueue) -> dict:
    server_receipt = sync_item.server_receipt if isinstance(sync_item.server_receipt, dict) else {}
    domain_record = server_receipt.get("domain_record")
    return domain_record if isinstance(domain_record, dict) else {}


def _sync_decision_record(sync_item: SyncQueue) -> dict:
    domain_record = _sync_domain_record(sync_item)
    if sync_item.status == SyncQueue.STATUS_PROCESSED:
        decision = "ACCEPTED"
        record_type = domain_record.get("type") or "domain record"
        explanation = f"Accepted {sync_item.upload_type} and linked it to {record_type}."
    elif sync_item.status == SyncQueue.STATUS_FAILED:
        decision = "REJECTED"
        conflict_state = sync_item.conflict_state
        if conflict_state == SyncQueue.CONFLICT_NONE:
            conflict_state = "PROCESSING_ERROR"
        explanation = sync_item.error_message or f"Rejected with conflict state {conflict_state}."
    else:
        decision = "PENDING"
        explanation = "Upload is queued for processing."

    return {
        "id": sync_item.id,
        "created_at": _isoformat_or_none(sync_item.created_at),
        "processed_at": _isoformat_or_none(sync_item.processed_at),
        "ward_id": sync_item.ward_id,
        "ward_name": sync_item.ward.name if sync_item.ward_id else "",
        "upload_type": sync_item.upload_type,
        "status": sync_item.status,
        "decision": decision,
        "conflict_state": sync_item.conflict_state,
        "client_submission_id": sync_item.client_submission_id,
        "idempotency_key": sync_item.idempotency_key,
        "download_bundle_version": sync_item.download_bundle_version,
        "domain_record": domain_record,
        "explanation": explanation,
    }


def _audit_check(
    *,
    key: str,
    title: str,
    count: int,
    summary: str,
    sample_records: list[dict],
    failed_status: str = "WARN",
) -> dict:
    return {
        "key": key,
        "title": title,
        "status": "PASS" if count == 0 else failed_status,
        "count": count,
        "summary": summary,
        "sample_records": sample_records[:5],
    }


def _action_matches_chv_actor(action: PreparednessAction, actor) -> bool:
    if actor is None:
        return False
    if action.assigned_to_id and action.assigned_to_id == getattr(actor, "id", None):
        return True

    actor_phone = (getattr(actor, "phone_number", "") or "").strip()
    action_phone = (getattr(action.chv, "phone_number", "") or "").strip()
    return bool(actor_phone and action_phone and actor_phone == action_phone)


def _build_out_of_assignment_audit(ward_ids: list[int], audit_cutoff) -> dict:
    sample_records: list[dict] = []
    count = 0
    events = (
        PreparednessActionEvent.objects.select_related(
            "actor",
            "preparedness_action",
            "preparedness_action__ward",
            "preparedness_action__chv",
        )
        .filter(
            preparedness_action__ward_id__in=ward_ids,
            metadata__source="chv_offline_sync",
            created_at__gte=audit_cutoff,
        )
        .order_by("-created_at")[:500]
    )

    for event in events:
        actor = event.actor
        if getattr(actor, "role", None) != "CHV":
            continue

        action = event.preparedness_action
        actor_ward_id = getattr(actor, "ward_id", None)
        outside_actor_ward = actor_ward_id is not None and action.ward_id != actor_ward_id
        outside_assignment = not _action_matches_chv_actor(action, actor)
        if not outside_actor_ward and not outside_assignment:
            continue

        count += 1
        sample_records.append(
            {
                "event_public_id": str(event.public_id),
                "action_public_id": str(action.public_id),
                "ward_id": action.ward_id,
                "ward_name": action.ward.name,
                "actor_username": getattr(actor, "username", ""),
                "sync_queue_id": event.metadata.get("sync_queue_id"),
                "created_at": _isoformat_or_none(event.created_at),
            }
        )

    summary = (
        "No offline CHV action audit events were outside the actor assignment."
        if count == 0
        else f"{count} offline action audit event{'s' if count != 1 else ''} did not match the CHV assignment."
    )
    return _audit_check(
        key="out_of_assignment_data",
        title="CHV data outside assignment",
        count=count,
        summary=summary,
        sample_records=sample_records,
        failed_status="FAIL",
    )


def _build_stale_bundle_action_audit(sync_queryset, audit_cutoff) -> dict:
    sample_records: list[dict] = []
    count = 0
    sync_items = (
        sync_queryset.select_related("ward", "device_registration")
        .filter(
            status=SyncQueue.STATUS_PROCESSED,
            upload_type__in=ACTION_SYNC_UPLOAD_TYPES,
            created_at__gte=audit_cutoff,
        )
        .order_by("-created_at")[:500]
    )

    for sync_item in sync_items:
        domain_record = _sync_domain_record(sync_item)
        completed_action = (
            domain_record.get("type") == "preparedness_action"
            and domain_record.get("status") == PreparednessAction.STATUS_COMPLETED
        )
        if not completed_action:
            continue

        registered_bundle = ""
        if sync_item.device_registration_id:
            registered_bundle = sync_item.device_registration.last_bundle_version

        stale_by_conflict = sync_item.conflict_state == SyncQueue.CONFLICT_STALE_BUNDLE
        stale_by_mismatch = bool(sync_item.download_bundle_version and registered_bundle and sync_item.download_bundle_version != registered_bundle)
        if not stale_by_conflict and not stale_by_mismatch:
            continue

        count += 1
        sample_records.append(
            {
                "sync_queue_id": sync_item.id,
                "ward_id": sync_item.ward_id,
                "ward_name": sync_item.ward.name if sync_item.ward_id else "",
                "upload_type": sync_item.upload_type,
                "used_bundle_version": sync_item.download_bundle_version,
                "registered_bundle_version": registered_bundle,
                "processed_at": _isoformat_or_none(sync_item.processed_at),
            }
        )

    summary = (
        "No completed offline actions used a stale guidance bundle."
        if count == 0
        else f"{count} completed offline action{'s' if count != 1 else ''} used a stale guidance bundle."
    )
    return _audit_check(
        key="stale_bundle_action_completion",
        title="Stale bundle action completion",
        count=count,
        summary=summary,
        sample_records=sample_records,
    )


def _build_repeated_rejected_uploads_audit(sync_queryset, audit_cutoff) -> dict:
    grouped_rejections = (
        sync_queryset.filter(status=SyncQueue.STATUS_FAILED, created_at__gte=audit_cutoff)
        .exclude(source_device_id="")
        .values("source_device_id")
        .annotate(rejected_count=Count("id"), last_rejected_at=Max("processed_at"))
        .filter(rejected_count__gte=OFFLINE_CHV_REJECTED_UPLOAD_THRESHOLD)
        .order_by("-rejected_count", "-last_rejected_at")
    )
    sample_records = [
        {
            "source_device_id": item["source_device_id"],
            "rejected_count": item["rejected_count"],
            "last_rejected_at": _isoformat_or_none(item["last_rejected_at"]),
        }
        for item in grouped_rejections[:5]
    ]
    count = sum(item["rejected_count"] for item in grouped_rejections)
    summary = (
        "No device has repeated rejected offline uploads in the audit window."
        if count == 0
        else f"{count} rejected upload{'s' if count != 1 else ''} came from devices crossing the repeat threshold."
    )
    return _audit_check(
        key="repeated_rejected_uploads",
        title="Repeated rejected uploads",
        count=count,
        summary=summary,
        sample_records=sample_records,
    )


def _rejected_submission_audit_record(audit: CHVOfflineRejectedSubmissionAudit) -> dict:
    return {
        "public_id": str(audit.public_id),
        "created_at": _isoformat_or_none(audit.created_at),
        "ward_id": audit.ward_id,
        "ward_name": audit.ward.name if audit.ward_id else "",
        "source_device_id": audit.source_device_id,
        "client_submission_id": audit.client_submission_id,
        "idempotency_key": audit.idempotency_key,
        "upload_type": audit.upload_type,
        "contract_version": audit.contract_version,
        "rejection_stage": audit.rejection_stage,
        "error_code": audit.error_code,
        "safe_error_summary": audit.safe_error_summary,
        "field_paths": audit.field_paths if isinstance(audit.field_paths, list) else [],
        "status_code": audit.status_code,
    }


def _build_pre_validation_rejections_audit(rejection_queryset, audit_cutoff) -> dict:
    queryset = rejection_queryset.filter(created_at__gte=audit_cutoff)
    count = queryset.count()
    sample_records = [
        _rejected_submission_audit_record(audit)
        for audit in queryset.select_related("ward").order_by("-created_at")[:5]
    ]
    summary = (
        "No CHV sync submissions were rejected before sync persistence in the audit window."
        if count == 0
        else f"{count} CHV sync submission{'s' if count != 1 else ''} were rejected before sync persistence."
    )
    return _audit_check(
        key="pre_validation_rejections",
        title="Rejected before sync persistence",
        count=count,
        summary=summary,
        sample_records=sample_records,
    )


def _build_unlinked_field_submission_audit(sync_queryset, audit_cutoff) -> dict:
    sample_records: list[dict] = []
    count = 0
    sync_items = (
        sync_queryset.select_related("ward")
        .filter(
            status=SyncQueue.STATUS_PROCESSED,
            upload_type__in=ACTION_SYNC_UPLOAD_TYPES,
            created_at__gte=audit_cutoff,
        )
        .order_by("-created_at")[:500]
    )

    for sync_item in sync_items:
        domain_record = _sync_domain_record(sync_item)
        if domain_record.get("type") == "preparedness_action":
            continue

        count += 1
        sample_records.append(
            {
                "sync_queue_id": sync_item.id,
                "ward_id": sync_item.ward_id,
                "ward_name": sync_item.ward.name if sync_item.ward_id else "",
                "upload_type": sync_item.upload_type,
                "domain_record_type": domain_record.get("type", ""),
                "processed_at": _isoformat_or_none(sync_item.processed_at),
            }
        )

    summary = (
        "No processed offline action submissions are missing a preparedness action link."
        if count == 0
        else f"{count} processed offline action submission{'s' if count != 1 else ''} lacked a preparedness action link."
    )
    return _audit_check(
        key="unlinked_field_submissions",
        title="Unlinked field submissions",
        count=count,
        summary=summary,
        sample_records=sample_records,
    )


def _build_offline_completion_latency_minutes(ward_ids: list[int], audit_cutoff) -> float | None:
    completion_events = (
        PreparednessActionEvent.objects.select_related("preparedness_action")
        .filter(
            preparedness_action__ward_id__in=ward_ids,
            metadata__source="chv_offline_sync",
            new_status=PreparednessAction.STATUS_COMPLETED,
            created_at__gte=audit_cutoff,
        )
        .order_by("-created_at")[:500]
    )
    latencies = []
    for event in completion_events:
        started_at = event.preparedness_action.created_at
        if started_at and event.created_at >= started_at:
            latencies.append((event.created_at - started_at).total_seconds() / 60)

    if not latencies:
        return None
    return round(sum(latencies) / len(latencies), 1)


def _ward_sync_health(last_successful_sync_at, pending_upload_count: int, failed_upload_count_24h: int) -> str:
    if last_successful_sync_at and timezone.now() - last_successful_sync_at <= timedelta(hours=OFFLINE_CHV_MONITORING_WINDOW_HOURS):
        if failed_upload_count_24h == 0:
            return "ONLINE"
        return "DELAYED"
    if pending_upload_count or failed_upload_count_24h:
        return "DELAYED"
    return "OFFLINE"


def build_chv_offline_monitoring_snapshot(ward_queryset=None, *, now=None) -> dict:
    now = now or timezone.now()
    since_24h = now - timedelta(hours=OFFLINE_CHV_MONITORING_WINDOW_HOURS)
    audit_cutoff = now - timedelta(days=OFFLINE_CHV_MONITORING_AUDIT_DAYS)
    active_device_cutoff = now - timedelta(days=OFFLINE_CHV_ACTIVE_DEVICE_DAYS)
    stale_bundle_cutoff = now - timedelta(hours=OFFLINE_CHV_STALE_BUNDLE_HOURS)

    if ward_queryset is None:
        ward_queryset = Ward.objects.filter(is_active=True)

    wards = list(ward_queryset.order_by("name"))
    ward_ids = [ward.id for ward in wards]
    devices = CHVDeviceRegistration.objects.filter(ward_id__in=ward_ids, is_active=True)
    sync_queryset = SyncQueue.objects.filter(ward_id__in=ward_ids)
    rejection_queryset = CHVOfflineRejectedSubmissionAudit.objects.filter(ward_id__in=ward_ids)

    registered_device_count = devices.count()
    active_device_count = devices.filter(Q(last_seen_at__gte=active_device_cutoff) | Q(last_sync_at__gte=active_device_cutoff)).count()
    successful_syncs_24h = sync_queryset.filter(status=SyncQueue.STATUS_PROCESSED, processed_at__gte=since_24h).count()
    failed_syncs_24h = sync_queryset.filter(status=SyncQueue.STATUS_FAILED, created_at__gte=since_24h).count()
    pre_validation_rejections_24h = rejection_queryset.filter(created_at__gte=since_24h).count()
    pending_uploads = sync_queryset.filter(status=SyncQueue.STATUS_PENDING).count()
    stale_guidance_bundles = devices.filter(
        Q(last_bundle_version="") | Q(last_seen_at__isnull=True) | Q(last_seen_at__lt=stale_bundle_cutoff)
    ).count()
    conflict_count_7d = sync_queryset.filter(created_at__gte=audit_cutoff).exclude(conflict_state=SyncQueue.CONFLICT_NONE).count()
    completion_latency_minutes = _build_offline_completion_latency_minutes(ward_ids, audit_cutoff)

    ward_sync_aggregates = {
        item["ward_id"]: item
        for item in sync_queryset.values("ward_id").annotate(
            successful_syncs_24h=Count("id", filter=Q(status=SyncQueue.STATUS_PROCESSED, processed_at__gte=since_24h)),
            pending_upload_count=Count("id", filter=Q(status=SyncQueue.STATUS_PENDING)),
            failed_upload_count_24h=Count("id", filter=Q(status=SyncQueue.STATUS_FAILED, created_at__gte=since_24h)),
            conflict_count_7d=Count("id", filter=~Q(conflict_state=SyncQueue.CONFLICT_NONE) & Q(created_at__gte=audit_cutoff)),
            last_successful_sync_at=Max("processed_at", filter=Q(status=SyncQueue.STATUS_PROCESSED)),
        )
    }
    active_devices_by_ward = {
        item["ward_id"]: item["device_count"]
        for item in devices.filter(Q(last_seen_at__gte=active_device_cutoff) | Q(last_sync_at__gte=active_device_cutoff))
        .values("ward_id")
        .annotate(device_count=Count("id"))
    }
    registered_devices_by_ward = {
        item["ward_id"]: item["device_count"]
        for item in devices.values("ward_id").annotate(device_count=Count("id"))
    }
    pre_validation_rejections_by_ward = {
        item["ward_id"]: item["rejection_count"]
        for item in rejection_queryset.filter(created_at__gte=since_24h)
        .values("ward_id")
        .annotate(rejection_count=Count("id"))
    }

    sync_health_by_ward = []
    for ward in wards:
        aggregate = ward_sync_aggregates.get(ward.id, {})
        last_successful_sync_at = aggregate.get("last_successful_sync_at")
        ward_pending_count = aggregate.get("pending_upload_count", 0)
        ward_failed_count = aggregate.get("failed_upload_count_24h", 0)
        sync_health_by_ward.append(
            {
                "ward_id": ward.id,
                "ward_name": ward.name,
                "registered_device_count": registered_devices_by_ward.get(ward.id, 0),
                "active_device_count": active_devices_by_ward.get(ward.id, 0),
                "successful_syncs_24h": aggregate.get("successful_syncs_24h", 0),
                "pending_upload_count": ward_pending_count,
                "failed_upload_count_24h": ward_failed_count,
                "pre_validation_rejection_count_24h": pre_validation_rejections_by_ward.get(ward.id, 0),
                "conflict_count_7d": aggregate.get("conflict_count_7d", 0),
                "last_successful_sync_at": _isoformat_or_none(last_successful_sync_at),
                "sync_health": _ward_sync_health(last_successful_sync_at, ward_pending_count, ward_failed_count),
            }
        )

    recent_sync_decisions = [
        _sync_decision_record(sync_item)
        for sync_item in sync_queryset.select_related("ward", "device_registration").order_by("-created_at")[:20]
    ]
    recent_rejected_submission_audits = [
        _rejected_submission_audit_record(audit)
        for audit in rejection_queryset.select_related("ward").order_by("-created_at")[:20]
    ]

    return {
        "schema_version": OFFLINE_CHV_MONITORING_SCHEMA_VERSION,
        "generated_at": _isoformat_or_none(now),
        "scope": {
            "ward_ids": ward_ids,
            "ward_count": len(ward_ids),
            "window_hours": OFFLINE_CHV_MONITORING_WINDOW_HOURS,
            "audit_window_days": OFFLINE_CHV_MONITORING_AUDIT_DAYS,
        },
        "metrics": {
            "registered_chv_devices": registered_device_count,
            "active_chv_devices": active_device_count,
            "successful_syncs_24h": successful_syncs_24h,
            "failed_syncs_24h": failed_syncs_24h,
            "pre_validation_rejections_24h": pre_validation_rejections_24h,
            "pending_uploads": pending_uploads,
            "stale_guidance_bundles": stale_guidance_bundles,
            "conflict_count_7d": conflict_count_7d,
            "offline_task_completion_latency_minutes": completion_latency_minutes,
        },
        "audit_checks": [
            _build_out_of_assignment_audit(ward_ids, audit_cutoff),
            _build_stale_bundle_action_audit(sync_queryset, audit_cutoff),
            _build_repeated_rejected_uploads_audit(sync_queryset, audit_cutoff),
            _build_unlinked_field_submission_audit(sync_queryset, audit_cutoff),
            _build_pre_validation_rejections_audit(rejection_queryset, audit_cutoff),
        ],
        "sync_health_by_ward": sync_health_by_ward,
        "recent_sync_decisions": recent_sync_decisions,
        "recent_rejected_submission_audits": recent_rejected_submission_audits,
    }
