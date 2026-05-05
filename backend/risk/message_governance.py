from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
import re
from string import Formatter
from typing import Any

from django.core.exceptions import ValidationError
from django.utils import timezone

from risk.chv_localization import (
    DEFAULT_CHV_LANGUAGE,
    SUPPORTED_CHV_LANGUAGES,
    build_chv_localization_inventory_report,
    resolve_language_preference,
)
from risk.models import (
    Alert,
    CHV,
    CHVDeviceRegistration,
    CHVMessage,
    CHVOfflineRejectedSubmissionAudit,
    ContactPreference,
    FacilityReadinessUpdateRequest,
    MessageTemplate,
    SyncQueue,
    UssdMenuVersion,
    UssdSessionLog,
)
from risk.ussd_governance import (
    USSD_RESPONSE_TEXT_MAX_CHARS,
    build_ussd_governance_audit,
)


MESSAGE_GOVERNANCE_SCHEMA_VERSION = "message-governance-phase-7-v1"
MESSAGE_AUDIENCE_GOVERNANCE_SCHEMA_VERSION = "message-audience-governance-phase-2-v1"
DEFAULT_LANGUAGE_FALLBACK = DEFAULT_CHV_LANGUAGE
REQUIRED_TRANSLATION_LANGUAGES = ("en", "sw", "luo")
LOCALIZATION_ROLLOUT_SCHEMA_VERSION = "chv-localization-rollout-phase-7-v1"
REQUIRED_CHV_OFFLINE_GUIDANCE_TEMPLATE_KEYS = (
    "cholera.household.prevention_guidance_offline_bundle",
)
REQUIRED_CHV_OFFLINE_DECISION_SUPPORT_TEMPLATE_KEYS = (
    "cholera.chv.triage.urgent_referral_offline",
    "cholera.chv.triage.facility_assessment_offline",
    "cholera.chv.triage.ors_and_prevention_offline",
    "cholera.chv.triage.record_symptoms_offline",
)
SAFE_ERROR_VALUE_PATTERNS = (
    re.compile(r"\+?254\d{9}\b"),
    re.compile(r"\b0[17]\d{8}\b"),
    re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE),
)
RAW_ERROR_COPY_PATTERNS = (
    re.compile(r"[\{\[]\s*['\"]?[A-Za-z_][A-Za-z0-9_]*['\"]?\s*[:=]"),
    re.compile(
        r"\b(raw_payload|phone_number|patient_name|caregiver_name|child_name|household_name|"
        r"national_id|gps|coordinates|medical_notes|clinical_notes|free_text|text_input)\b",
        re.IGNORECASE,
    ),
)
SENSITIVE_PAYLOAD_KEYS = {
    "caregiver_name",
    "child_name",
    "clinical_notes",
    "coordinates",
    "exact_address",
    "exact_household_location",
    "free_text",
    "free_text_case_detail",
    "free_text_medical_notes",
    "gps",
    "gps_coordinates",
    "household_contact",
    "household_head_name",
    "household_name",
    "household_phone",
    "medical_notes",
    "name",
    "national_id",
    "note",
    "notes",
    "patient_identifier",
    "patient_name",
    "phone",
    "phone_number",
    "raw_payload",
    "address",
    "text_input",
}


@dataclass(frozen=True)
class MessageInventoryItem:
    message_key: str
    title: str
    owner: str
    audience_type: str
    channel: str
    language: str
    risk_level: str
    current_location: str
    template_key: str
    default_body: str
    placeholders: tuple[str, ...] = ()
    managed_by_template: bool = False
    emergency_override_allowed: bool = False
    notes: str = ""


@dataclass(frozen=True)
class TemplateRenderResult:
    template: MessageTemplate
    body: str
    metadata: dict[str, Any]


CURRENT_MESSAGE_INVENTORY: tuple[MessageInventoryItem, ...] = (
    MessageInventoryItem(
        message_key="alert_sms",
        title="Risk alert SMS to assigned CHVs",
        owner="county_public_health_operations",
        audience_type=MessageTemplate.AUDIENCE_CHV,
        channel=MessageTemplate.CHANNEL_SMS,
        language="en",
        risk_level=MessageTemplate.RISK_HIGH,
        current_location="risk.services.create_alerts_for_riskscore",
        template_key="cholera.alert.chv.high_risk_sms",
        default_body=(
            "CHVs: {ward_name} is in a high-risk state. Review field conditions, prioritize follow-up, "
            "and report urgent changes."
        ),
        placeholders=("ward_name",),
        emergency_override_allowed=True,
        notes="Direct SMS is sent only to active CHVs in the ward and is filtered by contact preference checks.",
    ),
    MessageInventoryItem(
        message_key="chv_workflow_message",
        title="CHV workflow message",
        owner="ward_supervisor",
        audience_type=MessageTemplate.AUDIENCE_CHV,
        channel=MessageTemplate.CHANNEL_SMS,
        language="en",
        risk_level=MessageTemplate.RISK_MEDIUM,
        current_location="risk.views.CHVMessageListCreateAPIView",
        template_key="cholera.chv.workflow_check_in_sms",
        default_body="Please confirm field readiness for {ward_name} and report urgent cholera concerns.",
        placeholders=("ward_name",),
        emergency_override_allowed=True,
        notes="Current API still accepts operator-entered body text; the path is inventoried as governed free text.",
    ),
    MessageInventoryItem(
        message_key="ussd_root_menu",
        title="USSD root menu",
        owner="county_health_promotion",
        audience_type=MessageTemplate.AUDIENCE_HOUSEHOLD,
        channel=MessageTemplate.CHANNEL_USSD,
        language="en",
        risk_level=MessageTemplate.RISK_LOW,
        current_location="risk.ussd_governance.DEFAULT_USSD_MENU_TREE",
        template_key="cholera.ussd.root_menu",
        default_body=(
            "CON Welcome to CCHIS Health Menu\n"
            "1. Flood safety advice\n"
            "2. Child diarrhea support\n"
            "3. Heat health advice"
        ),
        notes="USSD copy is rendered through the phase 3 versioned menu governance layer.",
    ),
    MessageInventoryItem(
        message_key="ussd_flood_safety",
        title="USSD flood safety advice",
        owner="county_health_promotion",
        audience_type=MessageTemplate.AUDIENCE_HOUSEHOLD,
        channel=MessageTemplate.CHANNEL_USSD,
        language="en",
        risk_level=MessageTemplate.RISK_MEDIUM,
        current_location="risk.ussd_governance.DEFAULT_USSD_MENU_TREE",
        template_key="cholera.ussd.flood_safety",
        default_body=(
            "END Flood safety:\n"
            "Use treated water, avoid flood water, wash hands often, and seek care if child has diarrhea or vomiting."
        ),
    ),
    MessageInventoryItem(
        message_key="ussd_diarrhea_support",
        title="USSD child diarrhea support menu",
        owner="county_health_promotion",
        audience_type=MessageTemplate.AUDIENCE_HOUSEHOLD,
        channel=MessageTemplate.CHANNEL_USSD,
        language="en",
        risk_level=MessageTemplate.RISK_HIGH,
        current_location="risk.ussd_governance.DEFAULT_USSD_MENU_TREE",
        template_key="cholera.ussd.child_diarrhea_support",
        default_body="CON Child diarrhea support\n1. Diarrhea with vomiting or dehydration\n2. Mild diarrhea only",
    ),
    MessageInventoryItem(
        message_key="facility_update_request_text",
        title="Facility update request",
        owner="facility_readiness_lead",
        audience_type=MessageTemplate.AUDIENCE_FACILITY_CONTACT,
        channel=MessageTemplate.CHANNEL_SMS,
        language="en",
        risk_level=MessageTemplate.RISK_MEDIUM,
        current_location="risk.services.create_facility_readiness_update_request",
        template_key="cholera.facility.readiness_update_request_sms",
        default_body=(
            "Please update readiness status for {facility_name}: ORS stock, staffing, bed/capacity notes, "
            "and any urgent constraints. Reason: {reason_codes}."
        ),
        placeholders=("facility_name", "reason_codes"),
        emergency_override_allowed=True,
        notes="Facility contact must be active and verified before a request can be queued.",
    ),
    MessageInventoryItem(
        message_key="household_prevention_guidance",
        title="Household prevention guidance",
        owner="county_health_promotion",
        audience_type=MessageTemplate.AUDIENCE_HOUSEHOLD,
        channel=MessageTemplate.CHANNEL_OFFLINE_CHV_BUNDLE,
        language="en",
        risk_level=MessageTemplate.RISK_HIGH,
        current_location="risk.models.PreparednessAction.ACTION_HOUSEHOLD_PREVENTION_MESSAGE",
        template_key="cholera.household.prevention_guidance_offline_bundle",
        default_body=(
            "Use treated water, wash hands with soap, prepare ORS for diarrhea, and seek care quickly for dehydration."
        ),
        notes="No direct household broadcast sender is implemented in this phase.",
    ),
    MessageInventoryItem(
        message_key="public_health_escalation_text",
        title="Public-health escalation text",
        owner="county_public_health_operations",
        audience_type=MessageTemplate.AUDIENCE_COUNTY_OPERATOR,
        channel=MessageTemplate.CHANNEL_DASHBOARD,
        language="en",
        risk_level=MessageTemplate.RISK_HIGH,
        current_location="risk.services.create_alerts_for_riskscore",
        template_key="cholera.operator.public_health_escalation_dashboard",
        default_body="{ward_name} requires public-health escalation review for cholera preparedness.",
        placeholders=("ward_name",),
        notes="Dashboard escalation copy is visible to authorized operators.",
    ),
)

UNMANAGED_FREE_TEXT_PATHS: tuple[dict[str, str], ...] = (
    {
        "path": "risk.serializers.CHVMessageCreateSerializer.message_body",
        "audience_type": MessageTemplate.AUDIENCE_CHV,
        "channel": MessageTemplate.CHANNEL_SMS,
        "risk_level": MessageTemplate.RISK_MEDIUM,
        "mitigation": "PII-safe validation plus contact preference checks; template_key support is now available.",
    },
    {
        "path": "risk.serializers.FacilityReadinessUpdateRequestCreateSerializer.message_body",
        "audience_type": MessageTemplate.AUDIENCE_FACILITY_CONTACT,
        "channel": MessageTemplate.CHANNEL_SMS,
        "risk_level": MessageTemplate.RISK_MEDIUM,
        "mitigation": "Verified facility contact and contact preference checks; template_key support is now available.",
    },
    {
        "path": "risk.serializers.TriggerAlertRequestSerializer.message_override",
        "audience_type": MessageTemplate.AUDIENCE_CHV,
        "channel": MessageTemplate.CHANNEL_SMS,
        "risk_level": MessageTemplate.RISK_HIGH,
        "mitigation": "PII-safe validation and alert metadata record the edited-message mode.",
    },
)

EMERGENCY_OVERRIDE_CASES: tuple[dict[str, str], ...] = (
    {
        "case": "chv_operational_opt_out_override",
        "audience_type": MessageTemplate.AUDIENCE_CHV,
        "channel": MessageTemplate.CHANNEL_SMS,
        "required_reason": "urgent ward public health response",
        "audit_event": "ContactPreferenceAuditEvent.ACTION_EMERGENCY_OVERRIDE_USED",
    },
    {
        "case": "facility_contact_opt_out_override",
        "audience_type": MessageTemplate.AUDIENCE_FACILITY_CONTACT,
        "channel": MessageTemplate.CHANNEL_SMS,
        "required_reason": "urgent facility readiness response",
        "audit_event": "ContactPreferenceAuditEvent.ACTION_EMERGENCY_OVERRIDE_USED",
    },
    {
        "case": "household_public_health_override",
        "audience_type": MessageTemplate.AUDIENCE_HOUSEHOLD,
        "channel": MessageTemplate.CHANNEL_SMS,
        "required_reason": "approved lawful-basis public health emergency",
        "audit_event": "ContactPreferenceAuditEvent.ACTION_EMERGENCY_OVERRIDE_USED",
    },
)


def build_message_inventory_report() -> dict[str, Any]:
    entries = [asdict(item) for item in CURRENT_MESSAGE_INVENTORY]
    missing_required_fields = [
        entry["message_key"]
        for entry in entries
        if not all(entry[field] for field in ("owner", "audience_type", "language", "risk_level"))
    ]
    return {
        "schema_version": MESSAGE_GOVERNANCE_SCHEMA_VERSION,
        "inventory_count": len(entries),
        "inventory": entries,
        "missing_required_fields": missing_required_fields,
        "unmanaged_free_text_paths": list(UNMANAGED_FREE_TEXT_PATHS),
        "emergency_override_cases": list(EMERGENCY_OVERRIDE_CASES),
    }


def template_reference(template: MessageTemplate | None) -> dict[str, Any]:
    if template is None:
        return {"template_key": "", "template_version": None, "template_public_id": ""}
    return {
        "template_key": template.template_key,
        "template_version": template.version,
        "template_public_id": str(template.public_id),
        "audience_type": template.audience_type,
        "channel": template.channel,
        "language": template.language,
        "approval_status": template.approval_status,
        "approved_at": template.approved_at.isoformat() if template.approved_at else None,
        "retired_at": template.retired_at.isoformat() if template.retired_at else None,
    }


def validate_message_template_definition(template: MessageTemplate) -> set[str]:
    declared = template.placeholders or []
    if not isinstance(declared, list):
        raise ValidationError("Template placeholders must be a list.")
    if any(not isinstance(name, str) for name in declared):
        raise ValidationError("Template placeholders must be strings.")
    if len(set(declared)) != len(declared):
        raise ValidationError("Template placeholders must not contain duplicates.")

    body_placeholders = _body_placeholders(template.body)
    declared_set = set(declared)
    if body_placeholders != declared_set:
        missing = sorted(body_placeholders - declared_set)
        unused = sorted(declared_set - body_placeholders)
        details = []
        if missing:
            details.append("body placeholders missing from registry: " + ", ".join(missing))
        if unused:
            details.append("registered placeholders not used by body: " + ", ".join(unused))
        raise ValidationError("; ".join(details))
    return body_placeholders


def _body_placeholders(body: str) -> set[str]:
    placeholders: set[str] = set()
    try:
        parsed = Formatter().parse(body or "")
    except ValueError as exc:
        raise ValidationError(f"Template body has invalid placeholder syntax: {exc}") from exc

    for _literal, field_name, format_spec, conversion in parsed:
        if field_name is None:
            continue
        if format_spec or conversion or "." in field_name or "[" in field_name:
            raise ValidationError(
                "Template placeholders must be simple names like {ward_name}; advanced formatting is not supported."
            )
        if (
            not field_name
            or not field_name.replace("_", "").isalnum()
            or not field_name[0].isalpha()
            or field_name.lower() != field_name
        ):
            raise ValidationError("Template placeholders must be lowercase snake_case names.")
        placeholders.add(field_name)
    return placeholders


def _resolve_message_template(
    *,
    template_key: str,
    version: int | None,
    language: str,
    allow_unapproved: bool,
) -> MessageTemplate:
    normalized_key = (template_key or "").strip()
    normalized_language = (language or "en").strip().lower() or "en"
    if not normalized_key:
        raise ValueError("A template key is required.")
    if version is not None and version < 1:
        raise ValueError("Template version must be a positive integer.")

    queryset = MessageTemplate.objects.filter(template_key=normalized_key, language=normalized_language)
    if version is not None:
        queryset = queryset.filter(version=version)
    if allow_unapproved:
        queryset = queryset.filter(retired_at__isnull=True)
    else:
        queryset = queryset.filter(
            approval_status=MessageTemplate.APPROVAL_APPROVED,
            retired_at__isnull=True,
        )
        if normalized_language != DEFAULT_LANGUAGE_FALLBACK:
            queryset = queryset.filter(
                translation_status=MessageTemplate.TRANSLATION_APPROVED,
                source_template__isnull=False,
                source_template__approval_status=MessageTemplate.APPROVAL_APPROVED,
                source_template__retired_at__isnull=True,
            )

    template = queryset.order_by("-version", "-created_at").first()
    if template is None:
        version_label = f" v{version}" if version is not None else ""
        raise ValueError(f"No message template registered for {normalized_key}{version_label} ({normalized_language}).")
    return template


def _resolve_active_message_template_candidate(
    *,
    template_key: str,
    version: int | None,
    language: str,
) -> MessageTemplate | None:
    normalized_key = (template_key or "").strip()
    normalized_language = (language or "en").strip().lower() or "en"
    if not normalized_key:
        return None

    queryset = MessageTemplate.objects.filter(
        template_key=normalized_key,
        language=normalized_language,
        retired_at__isnull=True,
    )
    if version is not None:
        queryset = queryset.filter(version=version)
    return queryset.order_by("-version", "-created_at").first()


def _assert_template_usable_for_delivery(
    template: MessageTemplate,
    *,
    allow_unapproved: bool,
    household_broadcast: bool,
) -> None:
    if template.retired_at is not None or template.approval_status == MessageTemplate.APPROVAL_RETIRED:
        raise ValueError("Retired message templates cannot be used for delivery.")

    is_household_broadcast = household_broadcast or (
        not allow_unapproved
        and template.audience_type == MessageTemplate.AUDIENCE_HOUSEHOLD
        and template.channel in {MessageTemplate.CHANNEL_SMS, MessageTemplate.CHANNEL_OFFLINE_CHV_BUNDLE}
    )
    if template.approval_status != MessageTemplate.APPROVAL_APPROVED or template.approved_at is None:
        if is_household_broadcast:
            raise ValueError("Unapproved household broadcast templates cannot be used for delivery.")
        if not allow_unapproved:
            raise ValueError("Only approved message templates can be used for delivery.")
    if not allow_unapproved and template.language != DEFAULT_LANGUAGE_FALLBACK:
        source = template.source_template
        if template.translation_status != MessageTemplate.TRANSLATION_APPROVED or source is None:
            raise ValueError("Translated message templates require approved translation review before delivery.")
        if source.approval_status != MessageTemplate.APPROVAL_APPROVED or source.retired_at is not None:
            raise ValueError("Translated message templates require an active approved English source before delivery.")
        if sorted(template.placeholders or []) != sorted(source.placeholders or []):
            raise ValueError("Translated message templates must preserve English source placeholders before delivery.")
        public_health_copy = (
            template.audience_type in {MessageTemplate.AUDIENCE_CHV, MessageTemplate.AUDIENCE_HOUSEHOLD}
            or template.channel in {MessageTemplate.CHANNEL_USSD, MessageTemplate.CHANNEL_OFFLINE_CHV_BUNDLE}
            or template.risk_level in {MessageTemplate.RISK_HIGH, MessageTemplate.RISK_CRITICAL}
        )
        if public_health_copy and not template.public_health_caveats.strip():
            raise ValueError("Translated public-health message templates require caveats before delivery.")


def render_message_template(
    *,
    template_key: str,
    version: int | None = None,
    language: str = "en",
    context: dict[str, Any] | None = None,
    audience_type: str | None = None,
    channel: str | None = None,
    household_broadcast: bool = False,
    allow_unapproved: bool = False,
) -> TemplateRenderResult:
    language_resolution = resolve_language_preference(requested_language=language)
    fallback_used = language_resolution.fallback_used
    try:
        template = _resolve_message_template(
            template_key=template_key,
            version=version,
            language=language_resolution.resolved_language,
            allow_unapproved=allow_unapproved,
        )
    except ValueError as exc:
        if household_broadcast and not allow_unapproved:
            candidate = _resolve_active_message_template_candidate(
                template_key=template_key,
                version=version,
                language=language_resolution.resolved_language,
            )
            if candidate is not None:
                template = candidate
            else:
                if language_resolution.resolved_language == DEFAULT_LANGUAGE_FALLBACK:
                    raise
                try:
                    template = _resolve_message_template(
                        template_key=template_key,
                        version=version,
                        language=DEFAULT_LANGUAGE_FALLBACK,
                        allow_unapproved=allow_unapproved,
                    )
                    fallback_used = True
                except ValueError:
                    fallback_candidate = _resolve_active_message_template_candidate(
                        template_key=template_key,
                        version=version,
                        language=DEFAULT_LANGUAGE_FALLBACK,
                    )
                    if fallback_candidate is None:
                        raise exc
                    template = fallback_candidate
                    fallback_used = True
        elif language_resolution.resolved_language == DEFAULT_LANGUAGE_FALLBACK:
            raise
        else:
            try:
                template = _resolve_message_template(
                    template_key=template_key,
                    version=version,
                    language=DEFAULT_LANGUAGE_FALLBACK,
                    allow_unapproved=allow_unapproved,
                )
                fallback_used = True
            except ValueError:
                raise exc

    def validate_resolved_template(candidate: MessageTemplate) -> None:
        if audience_type and candidate.audience_type != audience_type:
            raise ValueError(f"Template {candidate.template_key} is for {candidate.audience_type}, not {audience_type}.")
        if channel and candidate.channel != channel:
            raise ValueError(f"Template {candidate.template_key} is for {candidate.channel}, not {channel}.")
        validate_message_template_definition(candidate)
        _assert_template_usable_for_delivery(
            candidate,
            allow_unapproved=allow_unapproved,
            household_broadcast=household_broadcast,
        )

    try:
        validate_resolved_template(template)
    except ValueError as exc:
        if template.language == DEFAULT_LANGUAGE_FALLBACK or allow_unapproved:
            raise
        try:
            fallback_template = _resolve_message_template(
                template_key=template_key,
                version=version,
                language=DEFAULT_LANGUAGE_FALLBACK,
                allow_unapproved=allow_unapproved,
            )
            validate_resolved_template(fallback_template)
        except ValueError:
            raise exc
        template = fallback_template
        fallback_used = True

    render_context = context or {}
    declared_placeholders = set(template.placeholders or [])
    missing = sorted(name for name in declared_placeholders if name not in render_context)
    if missing:
        raise ValueError("Template context is missing placeholders: " + ", ".join(missing))

    try:
        body = template.body.format(**{name: render_context[name] for name in declared_placeholders})
    except KeyError as exc:
        raise ValueError(f"Template context is missing placeholder: {exc.args[0]}") from exc

    return TemplateRenderResult(
        template=template,
        body=body,
        metadata={
            **template_reference(template),
            "requested_language": language_resolution.requested_language,
            "resolved_language": template.language,
            "fallback_used": fallback_used or template.language != language_resolution.requested_language,
            "lineage_metadata": template.lineage_metadata,
            "rendered_placeholder_keys": sorted(declared_placeholders),
        },
    )


def _check_result(check_id: str, status: str, answer: str, evidence: dict[str, Any], gaps: list[str]) -> dict[str, Any]:
    return {
        "id": check_id,
        "status": status,
        "answer": answer,
        "evidence": evidence,
        "gaps": gaps,
    }


def _percent(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100, 6)


def _template_validation_issues() -> list[dict[str, Any]]:
    issues = []
    for template in MessageTemplate.objects.order_by("template_key", "language", "version"):
        try:
            validate_message_template_definition(template)
        except (ValidationError, ValueError) as exc:
            issues.append(
                {
                    "template_public_id": str(template.public_id),
                    "template_key": template.template_key,
                    "version": template.version,
                    "language": template.language,
                    "message": "; ".join(getattr(exc, "messages", [str(exc)])),
                }
            )
    return issues


def _delivery_template_issues() -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    model_specs = (
        ("risk.Alert", Alert.objects.exclude(template_key=""), "message", MessageTemplate.AUDIENCE_CHV),
        ("risk.CHVMessage", CHVMessage.objects.exclude(template_key=""), "message_body", MessageTemplate.AUDIENCE_CHV),
        (
            "risk.FacilityReadinessUpdateRequest",
            FacilityReadinessUpdateRequest.objects.exclude(template_key=""),
            "message_body",
            MessageTemplate.AUDIENCE_FACILITY_CONTACT,
        ),
    )
    for model_label, queryset, body_field, fallback_audience in model_specs:
        for record in queryset.select_related("template").order_by("-created_at")[:500]:
            template = record.template
            if template is None:
                issues.append(
                    {
                        "model": model_label,
                        "record_id": record.pk,
                        "template_key": record.template_key,
                        "template_version": record.template_version,
                        "message": "Delivery record snapshots a template but is not linked to the concrete message template record.",
                    }
                )
                continue
            if record.template_key != template.template_key or record.template_version != template.version:
                issues.append(
                    {
                        "model": model_label,
                        "record_id": record.pk,
                        "template_key": record.template_key,
                        "template_version": record.template_version,
                        "template_public_id": str(template.public_id),
                        "message": "Delivery record template snapshot differs from the linked template.",
                    }
                )
            decision = _delivery_record_audience_decision(record)
            record_audience = _canonical_audience_type(
                decision.get("audience_type") or _delivery_record_default_audience(record, fallback_audience)
            )
            record_channel = _canonical_channel(decision.get("channel") or getattr(record, "channel", ""))
            if record_audience and _canonical_audience_type(template.audience_type) != record_audience:
                issues.append(
                    {
                        "model": model_label,
                        "record_id": record.pk,
                        "template_key": template.template_key,
                        "template_version": template.version,
                        "template_audience_type": template.audience_type,
                        "record_audience_type": record_audience,
                        "message": "Delivery record audience does not match the linked message template audience.",
                    }
                )
            if record_channel and _canonical_channel(template.channel) != record_channel:
                issues.append(
                    {
                        "model": model_label,
                        "record_id": record.pk,
                        "template_key": template.template_key,
                        "template_version": template.version,
                        "template_channel": template.channel,
                        "record_channel": record_channel,
                        "message": "Delivery record channel does not match the linked message template channel.",
                    }
                )
            if template.retired_at is not None and getattr(record, "created_at") >= template.retired_at:
                issues.append(
                    {
                        "model": model_label,
                        "record_id": record.pk,
                        "template_key": template.template_key,
                        "template_version": template.version,
                        "message": "Delivery record used a template after retirement.",
                    }
                )
            if template.approval_status != MessageTemplate.APPROVAL_APPROVED:
                issues.append(
                    {
                        "model": model_label,
                        "record_id": record.pk,
                        "template_key": template.template_key,
                        "template_version": template.version,
                        "message": "Delivery record used an unapproved template.",
                    }
                )
            if not getattr(record, body_field, "").strip():
                issues.append(
                    {
                        "model": model_label,
                        "record_id": record.pk,
                        "template_key": template.template_key,
                        "template_version": template.version,
                        "message": "Template-linked delivery record has an empty rendered body.",
                    }
                )
    return issues


def _delivery_governance_metadata_issues() -> tuple[list[dict[str, Any]], int]:
    issues: list[dict[str, Any]] = []
    governed_count = 0
    model_specs = (
        ("risk.Alert", Alert.objects.all(), "created_at", MessageTemplate.AUDIENCE_CHV),
        ("risk.CHVMessage", CHVMessage.objects.all(), "created_at", MessageTemplate.AUDIENCE_CHV),
        (
            "risk.FacilityReadinessUpdateRequest",
            FacilityReadinessUpdateRequest.objects.all(),
            "created_at",
            MessageTemplate.AUDIENCE_FACILITY_CONTACT,
        ),
    )
    for model_label, queryset, ordering_field, fallback_audience in model_specs:
        for record in queryset.order_by(f"-{ordering_field}", "-id")[:500]:
            metadata = record.governance_metadata if isinstance(record.governance_metadata, dict) else {}
            if not metadata:
                issues.append(
                    {
                        "model": model_label,
                        "record_id": record.pk,
                        "message": "Delivery record is missing message governance metadata.",
                    }
                )
                continue

            governed_count += 1
            audience_decision = metadata.get("audience_decision") if isinstance(metadata.get("audience_decision"), dict) else {}
            template_metadata = metadata.get("template") if isinstance(metadata.get("template"), dict) else {}
            if metadata.get("schema_version") != MESSAGE_AUDIENCE_GOVERNANCE_SCHEMA_VERSION:
                issues.append(
                    {
                        "model": model_label,
                        "record_id": record.pk,
                        "message": "Governed delivery metadata is missing the phase 2 schema version.",
                    }
                )
            if not audience_decision.get("allowed"):
                issues.append(
                    {
                        "model": model_label,
                        "record_id": record.pk,
                        "message": "Governed delivery metadata is missing an allowed audience decision.",
                    }
                )
            if audience_decision.get("schema_version") != MESSAGE_AUDIENCE_GOVERNANCE_SCHEMA_VERSION:
                issues.append(
                    {
                        "model": model_label,
                        "record_id": record.pk,
                        "message": "Governed delivery audience decision is missing the phase 2 schema version.",
                    }
                )
            expected_audience = _canonical_audience_type(_delivery_record_default_audience(record, fallback_audience))
            actual_audience = _canonical_audience_type(audience_decision.get("audience_type"))
            if actual_audience != expected_audience:
                issues.append(
                    {
                        "model": model_label,
                        "record_id": record.pk,
                        "expected_audience_type": expected_audience,
                        "metadata_audience_type": actual_audience,
                        "message": "Governed delivery audience decision does not match the delivery record audience.",
                    }
                )
            expected_channel = _canonical_channel(getattr(record, "channel", ""))
            actual_channel = _canonical_channel(audience_decision.get("channel"))
            if actual_channel != expected_channel:
                issues.append(
                    {
                        "model": model_label,
                        "record_id": record.pk,
                        "expected_channel": expected_channel,
                        "metadata_channel": actual_channel,
                        "message": "Governed delivery audience decision channel does not match the delivery record channel.",
                    }
                )
            if record.template_key and template_metadata.get("template_key") != record.template_key:
                issues.append(
                    {
                        "model": model_label,
                        "record_id": record.pk,
                        "template_key": record.template_key,
                        "metadata_template_key": template_metadata.get("template_key"),
                        "message": "Governed delivery metadata template snapshot does not match the delivery record.",
                    }
                )
            if record.template_key and template_metadata.get("template_version") != record.template_version:
                issues.append(
                    {
                        "model": model_label,
                        "record_id": record.pk,
                        "template_key": record.template_key,
                        "template_version": record.template_version,
                        "metadata_template_version": template_metadata.get("template_version"),
                        "message": "Governed delivery metadata template version does not match the delivery record.",
                    }
                )
            linked_template = getattr(record, "template", None)
            if record.template_key and linked_template is not None:
                metadata_template_public_id = template_metadata.get("template_public_id")
                if metadata_template_public_id != str(linked_template.public_id):
                    issues.append(
                        {
                            "model": model_label,
                            "record_id": record.pk,
                            "template_key": record.template_key,
                            "template_version": record.template_version,
                            "metadata_template_public_id": metadata_template_public_id,
                            "template_public_id": str(linked_template.public_id),
                            "message": "Governed delivery metadata template public id does not match the linked template.",
                        }
                    )
            if _canonical_audience_type(audience_decision.get("audience_type")) == MessageTemplate.AUDIENCE_HOUSEHOLD:
                if (
                    audience_decision.get("consent_status") != "GRANTED"
                    and not audience_decision.get("lawful_basis_approved")
                    and not audience_decision.get("emergency_override")
                ):
                    issues.append(
                        {
                            "model": model_label,
                            "record_id": record.pk,
                            "message": "Household audience decision lacks consent, approved lawful basis, or emergency override.",
                        }
                    )
    return issues, governed_count


def _delivery_language_traceability_issues() -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    model_specs = (
        ("risk.Alert", Alert.objects.select_related("template").filter(channel=Alert.CHANNEL_SMS).exclude(template_key="")),
        (
            "risk.CHVMessage",
            CHVMessage.objects.select_related("template").filter(channel=CHVMessage.CHANNEL_SMS).exclude(template_key=""),
        ),
    )
    for model_label, queryset in model_specs:
        for record in queryset.order_by("-created_at", "-id")[:500]:
            metadata = _delivery_record_metadata(record)
            template_metadata = metadata.get("template") if isinstance(metadata.get("template"), dict) else {}
            language_metadata = metadata.get("language") if isinstance(metadata.get("language"), dict) else {}
            requested_language = getattr(record, "requested_language", "")
            resolved_language = getattr(record, "resolved_language", "")
            fallback_used = bool(getattr(record, "fallback_used", False))
            template = _delivery_record_template(record)
            base_issue = _delivery_issue_base(model_label, record)

            if not requested_language or not resolved_language:
                issues.append(
                    {
                        **base_issue,
                        "message": "Template-linked CHV SMS delivery record is missing requested or resolved language fields.",
                    }
                )
            if resolved_language not in REQUIRED_TRANSLATION_LANGUAGES:
                issues.append(
                    {
                        **base_issue,
                        "resolved_language": resolved_language,
                        "message": "Template-linked CHV SMS delivery record resolved to an unsupported language.",
                    }
                )
            if template is None:
                issues.append(
                    {
                        **base_issue,
                        "message": "Template-linked CHV SMS delivery record cannot be resolved to a concrete template language version.",
                    }
                )
                continue
            if template.language != resolved_language:
                issues.append(
                    {
                        **base_issue,
                        "template_language": template.language,
                        "resolved_language": resolved_language,
                        "message": "Template-linked CHV SMS delivery record resolved language differs from linked template language.",
                    }
                )
            if template_metadata.get("requested_language") != requested_language:
                issues.append(
                    {
                        **base_issue,
                        "metadata_requested_language": template_metadata.get("requested_language"),
                        "requested_language": requested_language,
                        "message": "Template metadata requested language does not match the delivery record.",
                    }
                )
            if template_metadata.get("resolved_language") != resolved_language:
                issues.append(
                    {
                        **base_issue,
                        "metadata_resolved_language": template_metadata.get("resolved_language"),
                        "resolved_language": resolved_language,
                        "message": "Template metadata resolved language does not match the delivery record.",
                    }
                )
            if bool(template_metadata.get("fallback_used")) != fallback_used:
                issues.append(
                    {
                        **base_issue,
                        "metadata_fallback_used": bool(template_metadata.get("fallback_used")),
                        "fallback_used": fallback_used,
                        "message": "Template metadata fallback status does not match the delivery record.",
                    }
                )
            if language_metadata:
                if language_metadata.get("requested_language") != requested_language:
                    issues.append(
                        {
                            **base_issue,
                            "metadata_requested_language": language_metadata.get("requested_language"),
                            "requested_language": requested_language,
                            "message": "Delivery language metadata requested language does not match the delivery record.",
                        }
                    )
                if language_metadata.get("resolved_language") != resolved_language:
                    issues.append(
                        {
                            **base_issue,
                            "metadata_resolved_language": language_metadata.get("resolved_language"),
                            "resolved_language": resolved_language,
                            "message": "Delivery language metadata resolved language does not match the delivery record.",
                        }
                    )
                if bool(language_metadata.get("fallback_used")) != fallback_used:
                    issues.append(
                        {
                            **base_issue,
                            "metadata_fallback_used": bool(language_metadata.get("fallback_used")),
                            "fallback_used": fallback_used,
                            "message": "Delivery language metadata fallback status does not match the delivery record.",
                        }
                    )
    return issues


def _canonical_audience_type(value: str | None) -> str:
    raw = str(value or "").strip()
    aliases = {
        ContactPreference.AUDIENCE_CHV: MessageTemplate.AUDIENCE_CHV,
        ContactPreference.AUDIENCE_HOUSEHOLD: MessageTemplate.AUDIENCE_HOUSEHOLD,
        ContactPreference.AUDIENCE_FACILITY_CONTACT: MessageTemplate.AUDIENCE_FACILITY_CONTACT,
        ContactPreference.AUDIENCE_OPERATOR: MessageTemplate.AUDIENCE_COUNTY_OPERATOR,
    }
    return aliases.get(raw, aliases.get(raw.upper(), raw.lower()))


def _canonical_channel(value: str | None) -> str:
    raw = str(value or "").strip()
    aliases = {
        ContactPreference.CHANNEL_SMS: MessageTemplate.CHANNEL_SMS,
        ContactPreference.CHANNEL_USSD: MessageTemplate.CHANNEL_USSD,
        ContactPreference.CHANNEL_SYSTEM: MessageTemplate.CHANNEL_DASHBOARD,
        Alert.CHANNEL_DASHBOARD: MessageTemplate.CHANNEL_DASHBOARD,
        Alert.CHANNEL_SMS: MessageTemplate.CHANNEL_SMS,
    }
    return aliases.get(raw, aliases.get(raw.upper(), raw.lower()))


def _is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _delivery_audit_model_specs():
    return (
        (
            "risk.Alert",
            Alert.objects.select_related("template", "risk_score").all(),
            MessageTemplate.AUDIENCE_CHV,
        ),
        (
            "risk.CHVMessage",
            CHVMessage.objects.select_related("template").all(),
            MessageTemplate.AUDIENCE_CHV,
        ),
        (
            "risk.FacilityReadinessUpdateRequest",
            FacilityReadinessUpdateRequest.objects.select_related("template").all(),
            MessageTemplate.AUDIENCE_FACILITY_CONTACT,
        ),
    )


def _delivery_record_metadata(record) -> dict[str, Any]:
    metadata = getattr(record, "governance_metadata", {})
    return metadata if isinstance(metadata, dict) else {}


def _delivery_record_audience_decision(record) -> dict[str, Any]:
    metadata = _delivery_record_metadata(record)
    decision = metadata.get("audience_decision")
    return decision if isinstance(decision, dict) else {}


def _delivery_record_default_audience(record, fallback: str) -> str:
    if isinstance(record, Alert) and record.channel == Alert.CHANNEL_DASHBOARD:
        return MessageTemplate.AUDIENCE_COUNTY_OPERATOR
    return fallback


def _delivery_record_template(record) -> MessageTemplate | None:
    template = getattr(record, "template", None)
    if template is not None:
        return template
    template_key = getattr(record, "template_key", "")
    template_version = getattr(record, "template_version", None)
    if not template_key or template_version is None:
        return None
    queryset = MessageTemplate.objects.filter(template_key=template_key, version=template_version)
    resolved_language = getattr(record, "resolved_language", "")
    if resolved_language:
        resolved_template = queryset.filter(language=resolved_language).order_by("-created_at").first()
        if resolved_template is not None:
            return resolved_template
    return queryset.order_by("language", "-created_at").first()


def _delivery_issue_base(model_label: str, record) -> dict[str, Any]:
    return {
        "model": model_label,
        "record_id": record.pk,
        "record_public_id": str(record.public_id),
        "template_key": getattr(record, "template_key", ""),
        "template_version": getattr(record, "template_version", None),
    }


def _household_message_template_issues() -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for model_label, queryset, fallback_audience in _delivery_audit_model_specs():
        for record in queryset.order_by("-created_at", "-id")[:500]:
            template = _delivery_record_template(record)
            decision = _delivery_record_audience_decision(record)
            audience_type = _canonical_audience_type(
                decision.get("audience_type")
                or (template.audience_type if template else _delivery_record_default_audience(record, fallback_audience))
            )
            if audience_type != MessageTemplate.AUDIENCE_HOUSEHOLD:
                continue

            channel = _canonical_channel(decision.get("channel") or getattr(record, "channel", ""))
            if channel not in {MessageTemplate.CHANNEL_SMS, MessageTemplate.CHANNEL_OFFLINE_CHV_BUNDLE}:
                continue

            if (
                template is None
                or template.approval_status != MessageTemplate.APPROVAL_APPROVED
                or template.approved_at is None
                or template.retired_at is not None
            ):
                issues.append(
                    {
                        **_delivery_issue_base(model_label, record),
                        "audience_type": audience_type,
                        "channel": channel,
                        "message": "Household direct message used without an approved, non-retired message template.",
                    }
                )
    return issues


def _retired_template_usage_issues() -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for model_label, queryset, _fallback_audience in _delivery_audit_model_specs():
        for record in queryset.exclude(template_key="").order_by("-created_at", "-id")[:500]:
            template = _delivery_record_template(record)
            created_at = getattr(record, "created_at", None)
            if template is None or template.retired_at is None or created_at is None:
                continue
            if created_at >= template.retired_at:
                issues.append(
                    {
                        **_delivery_issue_base(model_label, record),
                        "template_public_id": str(template.public_id),
                        "retired_at": template.retired_at,
                        "created_at": created_at,
                        "message": "Delivery record used a message template after its retirement timestamp.",
                    }
                )
    return issues


def _language_fallback_issues() -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for template in MessageTemplate.objects.exclude(language=DEFAULT_LANGUAGE_FALLBACK).order_by(
        "template_key",
        "version",
        "language",
    ):
        fallback = MessageTemplate.objects.filter(
            template_key=template.template_key,
            version=template.version,
            language=DEFAULT_LANGUAGE_FALLBACK,
            retired_at__isnull=True,
        )
        if template.approval_status == MessageTemplate.APPROVAL_APPROVED:
            fallback = fallback.filter(
                approval_status=MessageTemplate.APPROVAL_APPROVED,
                approved_at__isnull=False,
            )
        if not fallback.exists():
            issues.append(
                {
                    "model": "risk.MessageTemplate",
                    "template_public_id": str(template.public_id),
                    "template_key": template.template_key,
                    "version": template.version,
                    "language": template.language,
                    "fallback_language": DEFAULT_LANGUAGE_FALLBACK,
                    "message": "Message template language variant does not have an English fallback for the same key and version.",
                }
            )

    for menu_version in UssdMenuVersion.objects.exclude(language=DEFAULT_LANGUAGE_FALLBACK).filter(
        retired_at__isnull=True,
    ).order_by("menu_key", "language", "version_label"):
        fallback = UssdMenuVersion.objects.filter(
            menu_key=menu_version.menu_key,
            language=DEFAULT_LANGUAGE_FALLBACK,
            retired_at__isnull=True,
        )
        if menu_version.approval_status == UssdMenuVersion.STATUS_APPROVED or menu_version.is_active:
            fallback = fallback.filter(approval_status=UssdMenuVersion.STATUS_APPROVED)
        if not fallback.exists():
            issues.append(
                {
                    "model": "risk.UssdMenuVersion",
                    "menu_public_id": str(menu_version.public_id),
                    "menu_key": menu_version.menu_key,
                    "version_label": menu_version.version_label,
                    "language": menu_version.language,
                    "fallback_language": DEFAULT_LANGUAGE_FALLBACK,
                    "message": "USSD menu language variant does not have an English fallback menu.",
                }
            )
    return issues


def _message_template_requires_translation(template: MessageTemplate) -> bool:
    return template.audience_type == MessageTemplate.AUDIENCE_CHV or template.channel in {
        MessageTemplate.CHANNEL_USSD,
        MessageTemplate.CHANNEL_OFFLINE_CHV_BUNDLE,
    }


def _template_translation_registry_issues() -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    templates = list(MessageTemplate.objects.select_related("source_template").order_by("template_key", "version", "language"))
    required_templates = [template for template in templates if _message_template_requires_translation(template)]
    by_identity = {
        (template.template_key, template.version, template.language): template
        for template in required_templates
    }

    english_sources = [
        template
        for template in required_templates
        if template.language == DEFAULT_LANGUAGE_FALLBACK
        and template.approval_status == MessageTemplate.APPROVAL_APPROVED
        and template.retired_at is None
    ]
    approved_english_source_keys = {template.template_key for template in english_sources}
    for template_key in (
        *REQUIRED_CHV_OFFLINE_GUIDANCE_TEMPLATE_KEYS,
        *REQUIRED_CHV_OFFLINE_DECISION_SUPPORT_TEMPLATE_KEYS,
    ):
        if template_key not in approved_english_source_keys:
            issues.append(
                {
                    "model": "risk.MessageTemplate",
                    "template_key": template_key,
                    "language": DEFAULT_LANGUAGE_FALLBACK,
                    "channel": MessageTemplate.CHANNEL_OFFLINE_CHV_BUNDLE,
                    "message": "Required offline CHV public-health English source template is missing or not approved.",
                }
            )
    for source in english_sources:
        for language in REQUIRED_TRANSLATION_LANGUAGES:
            variant = by_identity.get((source.template_key, source.version, language))
            if variant is None:
                issues.append(
                    {
                        "model": "risk.MessageTemplate",
                        "template_key": source.template_key,
                        "version": source.version,
                        "language": language,
                        "source_template_public_id": str(source.public_id),
                        "message": "Required CHV/USSD message template language variant is missing.",
                    }
                )
                continue

            if language == DEFAULT_LANGUAGE_FALLBACK:
                continue
            if (
                variant.approval_status != MessageTemplate.APPROVAL_APPROVED
                or variant.retired_at is not None
                or variant.translation_status != MessageTemplate.TRANSLATION_APPROVED
            ):
                issues.append(
                    {
                        "model": "risk.MessageTemplate",
                        "template_public_id": str(variant.public_id),
                        "template_key": variant.template_key,
                        "version": variant.version,
                        "language": variant.language,
                        "message": "Required translated message template variant is not active and approved for use.",
                    }
                )
            if variant.source_template_id != source.id:
                issues.append(
                    {
                        "model": "risk.MessageTemplate",
                        "template_public_id": str(variant.public_id),
                        "template_key": variant.template_key,
                        "version": variant.version,
                        "language": variant.language,
                        "message": "Translated message template is not linked to the English source version.",
                    }
                )
            if sorted(variant.placeholders or []) != sorted(source.placeholders or []):
                issues.append(
                    {
                        "model": "risk.MessageTemplate",
                        "template_public_id": str(variant.public_id),
                        "template_key": variant.template_key,
                        "version": variant.version,
                        "language": variant.language,
                        "message": "Translated message template placeholders differ from the English source.",
                    }
                )
            if source.public_health_caveats.strip() and not variant.public_health_caveats.strip():
                issues.append(
                    {
                        "model": "risk.MessageTemplate",
                        "template_public_id": str(variant.public_id),
                        "template_key": variant.template_key,
                        "version": variant.version,
                        "language": variant.language,
                        "message": "Translated public-health message template is missing public-health caveats.",
                    }
                )
            if variant.approval_status == MessageTemplate.APPROVAL_APPROVED and (
                variant.translation_status != MessageTemplate.TRANSLATION_APPROVED
                or variant.translation_reviewed_at is None
            ):
                issues.append(
                    {
                        "model": "risk.MessageTemplate",
                        "template_public_id": str(variant.public_id),
                        "template_key": variant.template_key,
                        "version": variant.version,
                        "language": variant.language,
                        "message": "Approved translated message template is missing approved translation review metadata.",
                    }
                )

    for variant in required_templates:
        if variant.language == DEFAULT_LANGUAGE_FALLBACK:
            continue
        source = variant.source_template
        if source is None:
            issues.append(
                {
                    "model": "risk.MessageTemplate",
                    "template_public_id": str(variant.public_id),
                    "template_key": variant.template_key,
                    "version": variant.version,
                    "language": variant.language,
                    "message": "Translated message template is missing English source linkage.",
                }
            )
            continue
        source_retired = source.retired_at is not None or source.approval_status == MessageTemplate.APPROVAL_RETIRED
        if source_retired and variant.translation_status not in {
            MessageTemplate.TRANSLATION_RETIRED,
            MessageTemplate.TRANSLATION_BLOCKED_SOURCE_RETIRED,
        }:
            issues.append(
                {
                    "model": "risk.MessageTemplate",
                    "template_public_id": str(variant.public_id),
                    "template_key": variant.template_key,
                    "version": variant.version,
                    "language": variant.language,
                    "message": "Translated message template is still usable after its English source was retired.",
                }
            )
    return issues


def _ussd_menu_tree_structure_signature(menu_tree: dict) -> dict[str, list[str]]:
    if not isinstance(menu_tree, dict):
        return {"routes": [], "nodes": [], "response_types": []}
    routes = menu_tree.get("routes")
    nodes = menu_tree.get("nodes")
    return {
        "routes": [f"{route}:{node_key}" for route, node_key in sorted(routes.items())]
        if isinstance(routes, dict)
        else [],
        "nodes": sorted(nodes.keys()) if isinstance(nodes, dict) else [],
        "response_types": [
            f"{node_key}:{str(node.get('response_type') or '').upper()}"
            for node_key, node in sorted(nodes.items())
            if isinstance(node, dict)
        ]
        if isinstance(nodes, dict)
        else [],
    }


def _ussd_translation_registry_issues() -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    menu_versions = list(
        UssdMenuVersion.objects.select_related("source_menu_version").order_by("menu_key", "language", "version_label")
    )
    active_by_menu_language = {
        (version.menu_key, version.language): version
        for version in menu_versions
        if (
            version.is_active
            and version.approval_status == UssdMenuVersion.STATUS_APPROVED
            and version.retired_at is None
        )
    }
    english_sources = [
        version
        for version in menu_versions
        if version.language == DEFAULT_LANGUAGE_FALLBACK
        and version.approval_status == UssdMenuVersion.STATUS_APPROVED
        and version.retired_at is None
        and version.is_active
    ]

    for source in english_sources:
        source_signature = _ussd_menu_tree_structure_signature(source.menu_tree or {})
        for language in REQUIRED_TRANSLATION_LANGUAGES:
            variant = active_by_menu_language.get((source.menu_key, language))
            if variant is None:
                issues.append(
                    {
                        "model": "risk.UssdMenuVersion",
                        "menu_key": source.menu_key,
                        "language": language,
                        "source_menu_public_id": str(source.public_id),
                        "message": "Required active approved USSD menu language variant is missing.",
                    }
                )
                continue
            if language == DEFAULT_LANGUAGE_FALLBACK:
                continue
            if variant.source_menu_version_id != source.id:
                issues.append(
                    {
                        "model": "risk.UssdMenuVersion",
                        "menu_public_id": str(variant.public_id),
                        "menu_key": variant.menu_key,
                        "language": variant.language,
                        "message": "Translated USSD menu is not linked to the active English source menu.",
                    }
                )
            if _ussd_menu_tree_structure_signature(variant.menu_tree or {}) != source_signature:
                issues.append(
                    {
                        "model": "risk.UssdMenuVersion",
                        "menu_public_id": str(variant.public_id),
                        "menu_key": variant.menu_key,
                        "language": variant.language,
                        "message": "Translated USSD menu routes or node keys differ from the English source.",
                    }
                )
            if not variant.safe_fallback_copy.strip():
                issues.append(
                    {
                        "model": "risk.UssdMenuVersion",
                        "menu_public_id": str(variant.public_id),
                        "menu_key": variant.menu_key,
                        "language": variant.language,
                        "message": "Translated USSD menu is missing safe fallback copy.",
                    }
                )
            if variant.approval_status == UssdMenuVersion.STATUS_APPROVED and (
                variant.translation_status != UssdMenuVersion.TRANSLATION_APPROVED
                or variant.translation_reviewed_at is None
            ):
                issues.append(
                    {
                        "model": "risk.UssdMenuVersion",
                        "menu_public_id": str(variant.public_id),
                        "menu_key": variant.menu_key,
                        "language": variant.language,
                        "message": "Approved translated USSD menu is missing approved translation review metadata.",
                    }
                )

    for variant in menu_versions:
        if variant.language == DEFAULT_LANGUAGE_FALLBACK:
            continue
        source = variant.source_menu_version
        if source is None:
            issues.append(
                {
                    "model": "risk.UssdMenuVersion",
                    "menu_public_id": str(variant.public_id),
                    "menu_key": variant.menu_key,
                    "language": variant.language,
                    "message": "Translated USSD menu is missing English source linkage.",
                }
            )
            continue
        source_retired = source.retired_at is not None or source.approval_status == UssdMenuVersion.STATUS_RETIRED
        if source_retired and variant.translation_status not in {
            UssdMenuVersion.TRANSLATION_RETIRED,
            UssdMenuVersion.TRANSLATION_BLOCKED_SOURCE_RETIRED,
        }:
            issues.append(
                {
                    "model": "risk.UssdMenuVersion",
                    "menu_public_id": str(variant.public_id),
                    "menu_key": variant.menu_key,
                    "language": variant.language,
                    "message": "Translated USSD menu is still usable after its English source was retired.",
                }
            )
    return issues


def _ussd_node_length_issues() -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    queryset = UssdMenuVersion.objects.filter(retired_at__isnull=True).filter(
        approval_status=UssdMenuVersion.STATUS_APPROVED,
    )
    for menu_version in queryset.order_by("menu_key", "language", "version_label")[:500]:
        menu_tree = menu_version.menu_tree if isinstance(menu_version.menu_tree, dict) else {}
        nodes = menu_tree.get("nodes")
        if isinstance(nodes, dict):
            for node_key, node in nodes.items():
                if not isinstance(node, dict):
                    continue
                response_type = str(node.get("response_type") or "").upper()
                body = str(node.get("body") or "").strip()
                response_text = f"{response_type} {body}".strip()
                if len(response_text) > USSD_RESPONSE_TEXT_MAX_CHARS:
                    issues.append(
                        {
                            "model": "risk.UssdMenuVersion",
                            "menu_public_id": str(menu_version.public_id),
                            "menu_key": menu_version.menu_key,
                            "version_label": menu_version.version_label,
                            "language": menu_version.language,
                            "node_key": node_key,
                            "char_count": len(response_text),
                            "max_chars": USSD_RESPONSE_TEXT_MAX_CHARS,
                            "message": "USSD node exceeds configured response length budget.",
                        }
                    )
        safe_fallback_copy = str(menu_version.safe_fallback_copy or "").strip()
        if len(safe_fallback_copy) > USSD_RESPONSE_TEXT_MAX_CHARS:
            issues.append(
                {
                    "model": "risk.UssdMenuVersion",
                    "menu_public_id": str(menu_version.public_id),
                    "menu_key": menu_version.menu_key,
                    "version_label": menu_version.version_label,
                    "language": menu_version.language,
                    "char_count": len(safe_fallback_copy),
                    "max_chars": USSD_RESPONSE_TEXT_MAX_CHARS,
                    "message": "USSD safe fallback copy exceeds configured response length budget.",
                }
            )
    return issues


def _opt_out_ignored_issues() -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for model_label, queryset, _fallback_audience in _delivery_audit_model_specs():
        for record in queryset.exclude(governance_metadata={}).order_by("-created_at", "-id")[:500]:
            decision = _delivery_record_audience_decision(record)
            if not _is_truthy(decision.get("allowed")):
                continue
            if decision.get("opt_out_status") != ContactPreference.OPT_OUT_OPTED_OUT:
                continue
            if _is_truthy(decision.get("emergency_override")):
                continue
            issues.append(
                {
                    **_delivery_issue_base(model_label, record),
                    "audience_type": _canonical_audience_type(decision.get("audience_type")),
                    "channel": _canonical_channel(decision.get("channel")),
                    "preference_public_id": decision.get("preference_public_id", ""),
                    "message": "Delivery record allowed direct messaging even though the audience decision shows opt-out.",
                }
            )
    return issues


def _high_risk_alert_source_reference_issues() -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for alert in Alert.objects.select_related("risk_score", "template").order_by("-created_at", "-id")[:500]:
        template = _delivery_record_template(alert)
        metadata = _delivery_record_metadata(alert)
        guided_metadata = alert.guided_request_metadata if isinstance(alert.guided_request_metadata, dict) else {}
        metadata_risk_level = str(metadata.get("risk_level") or guided_metadata.get("risk_level") or "").lower()
        risk_score_level = alert.risk_score.risk_level if alert.risk_score_id else ""
        template_high_risk = bool(
            template and template.risk_level in {MessageTemplate.RISK_HIGH, MessageTemplate.RISK_CRITICAL}
        )
        workflow = str(metadata.get("workflow") or guided_metadata.get("workflow") or "")
        looks_like_alert_message = bool(
            workflow.startswith("risk_alert")
            or alert.risk_score_id
            or ".alert." in (alert.template_key or "")
            or template_high_risk
        )
        is_high_risk = bool(
            risk_score_level == "HIGH"
            or metadata_risk_level in {MessageTemplate.RISK_HIGH, MessageTemplate.RISK_CRITICAL, "HIGH", "CRITICAL"}
            or template_high_risk
        )
        if not looks_like_alert_message or not is_high_risk:
            continue

        source_reference = (
            alert.risk_score_id
            or metadata.get("risk_score_id")
            or metadata.get("source_alert_reference")
            or metadata.get("source_risk_score_reference")
            or guided_metadata.get("risk_score_id")
            or guided_metadata.get("source_alert_reference")
            or guided_metadata.get("source_risk_score_reference")
        )
        if not source_reference:
            issues.append(
                {
                    **_delivery_issue_base("risk.Alert", alert),
                    "risk_level": risk_score_level or metadata_risk_level or (template.risk_level if template else ""),
                    "workflow": workflow,
                    "message": "High-risk alert message is missing a source risk score or alert reference.",
                }
            )
    return issues


def _language_supported(value: str | None) -> bool:
    return str(value or "").strip().lower() in SUPPORTED_CHV_LANGUAGES


def _language_from_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    language = metadata.get("language")
    if isinstance(language, dict):
        return language
    return {}


def _unsupported_language_code_issues() -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    field_specs = (
        ("risk.CHV", CHV.objects.all(), ("language", "preferred_language")),
        ("risk.CHVDeviceRegistration", CHVDeviceRegistration.objects.all(), ("preferred_language",)),
        ("risk.MessageTemplate", MessageTemplate.objects.all(), ("language",)),
        ("risk.UssdMenuVersion", UssdMenuVersion.objects.all(), ("language",)),
        ("risk.Alert", Alert.objects.exclude(template_key=""), ("requested_language", "resolved_language")),
        ("risk.CHVMessage", CHVMessage.objects.exclude(template_key=""), ("requested_language", "resolved_language")),
        ("risk.UssdSessionLog", UssdSessionLog.objects.all(), ("language", "requested_language", "resolved_language")),
    )
    for model_label, queryset, field_names in field_specs:
        for record in queryset.order_by("-id")[:1000]:
            for field_name in field_names:
                value = getattr(record, field_name, "")
                if not value:
                    continue
                if not _language_supported(value):
                    issues.append(
                        {
                            "model": model_label,
                            "record_id": record.pk,
                            "field": field_name,
                            "language": value,
                            "message": "Unsupported CHV localization language code is stored.",
                        }
                    )
    return issues


def _chv_language_preference_issues() -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for chv in CHV.objects.filter(is_active=True).order_by("id")[:1000]:
        if not chv.preferred_language:
            issues.append(
                {
                    "model": "risk.CHV",
                    "record_id": chv.pk,
                    "chv_public_id": str(chv.public_id),
                    "message": "Active CHV is missing a preferred language.",
                }
            )
        elif not _language_supported(chv.preferred_language):
            issues.append(
                {
                    "model": "risk.CHV",
                    "record_id": chv.pk,
                    "chv_public_id": str(chv.public_id),
                    "preferred_language": chv.preferred_language,
                    "message": "Active CHV has an invalid preferred language.",
                }
            )
        if chv.language != chv.preferred_language:
            issues.append(
                {
                    "model": "risk.CHV",
                    "record_id": chv.pk,
                    "chv_public_id": str(chv.public_id),
                    "language": chv.language,
                    "preferred_language": chv.preferred_language,
                    "message": "CHV legacy language field has drifted from preferred language.",
                }
            )
    for registration in CHVDeviceRegistration.objects.filter(is_active=True).order_by("id")[:1000]:
        if not registration.preferred_language or not _language_supported(registration.preferred_language):
            issues.append(
                {
                    "model": "risk.CHVDeviceRegistration",
                    "record_id": registration.pk,
                    "device_public_id": str(registration.public_id),
                    "preferred_language": registration.preferred_language,
                    "message": "Active CHV device registration has missing or invalid preferred language.",
                }
            )
    return issues


def _translated_public_health_copy_usage_issues() -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for model_label, queryset, _fallback_audience in _delivery_audit_model_specs():
        for record in queryset.exclude(template_key="").order_by("-created_at", "-id")[:500]:
            template = _delivery_record_template(record)
            if template is None or template.language == DEFAULT_LANGUAGE_FALLBACK:
                continue
            public_health_copy = (
                template.audience_type in {MessageTemplate.AUDIENCE_CHV, MessageTemplate.AUDIENCE_HOUSEHOLD}
                or template.channel in {MessageTemplate.CHANNEL_USSD, MessageTemplate.CHANNEL_OFFLINE_CHV_BUNDLE}
                or template.risk_level in {MessageTemplate.RISK_HIGH, MessageTemplate.RISK_CRITICAL}
            )
            if not public_health_copy:
                continue
            if (
                template.approval_status != MessageTemplate.APPROVAL_APPROVED
                or template.translation_status != MessageTemplate.TRANSLATION_APPROVED
                or template.translation_reviewed_at is None
            ):
                issues.append(
                    {
                        **_delivery_issue_base(model_label, record),
                        "template_public_id": str(template.public_id),
                        "template_language": template.language,
                        "approval_status": template.approval_status,
                        "translation_status": template.translation_status,
                        "message": "Translated public-health copy was used before approved translation review.",
                    }
                )
    return issues


def _language_mismatch_requires_fallback_flag(
    requested_language: Any,
    resolved_language: Any,
    fallback_used: Any,
) -> bool:
    requested = str(requested_language or "").strip().lower()
    resolved = str(resolved_language or "").strip().lower()
    return bool(requested and resolved and requested != resolved and not _is_truthy(fallback_used))


def _fallback_without_metadata_issues() -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for model_label, queryset, _fallback_audience in _delivery_audit_model_specs():
        for record in queryset.order_by("-created_at", "-id")[:500]:
            requested_language = getattr(record, "requested_language", "")
            resolved_language = getattr(record, "resolved_language", "")
            record_fallback_used = bool(getattr(record, "fallback_used", False))
            metadata = _delivery_record_metadata(record)
            language_metadata = _language_from_metadata(metadata)
            template_metadata = metadata.get("template") if isinstance(metadata.get("template"), dict) else {}

            if _language_mismatch_requires_fallback_flag(requested_language, resolved_language, record_fallback_used):
                issues.append(
                    {
                        **_delivery_issue_base(model_label, record),
                        "requested_language": requested_language,
                        "resolved_language": resolved_language,
                        "message": "Delivery record resolved a different language without marking fallback_used.",
                    }
                )

            if not record_fallback_used:
                continue

            if not language_metadata or bool(language_metadata.get("fallback_used")) is not True:
                issues.append(
                    {
                        **_delivery_issue_base(model_label, record),
                        "message": "Delivery record used language fallback without matching language metadata.",
                    }
                )
            if getattr(record, "template_key", "") and bool(template_metadata.get("fallback_used")) is not True:
                issues.append(
                    {
                        **_delivery_issue_base(model_label, record),
                        "message": "Template-linked delivery fallback is not reflected in template metadata.",
                    }
                )
            if _language_mismatch_requires_fallback_flag(
                language_metadata.get("requested_language"),
                language_metadata.get("resolved_language"),
                language_metadata.get("fallback_used"),
            ):
                issues.append(
                    {
                        **_delivery_issue_base(model_label, record),
                        "message": "Delivery language metadata resolves a different language without fallback_used.",
                    }
                )
            if _language_mismatch_requires_fallback_flag(
                template_metadata.get("requested_language"),
                template_metadata.get("resolved_language"),
                template_metadata.get("fallback_used"),
            ):
                issues.append(
                    {
                        **_delivery_issue_base(model_label, record),
                        "message": "Template language metadata resolves a different language without fallback_used.",
                    }
                )

    for log in UssdSessionLog.objects.order_by("-created_at", "-id")[:500]:
        metadata = log.governance_metadata if isinstance(log.governance_metadata, dict) else {}
        if _language_mismatch_requires_fallback_flag(log.requested_language, log.resolved_language, log.fallback_used):
            issues.append(
                {
                    "model": "risk.UssdSessionLog",
                    "record_id": log.pk,
                    "session_id": log.session_id,
                    "requested_language": log.requested_language,
                    "resolved_language": log.resolved_language,
                    "message": "USSD session resolved a different language without marking fallback_used.",
                }
            )
        if bool(log.fallback_used) and bool(metadata.get("fallback_used")) is not True:
            issues.append(
                {
                    "model": "risk.UssdSessionLog",
                    "record_id": log.pk,
                    "session_id": log.session_id,
                    "requested_language": log.requested_language,
                    "resolved_language": log.resolved_language,
                    "message": "USSD session used fallback without fallback metadata.",
                }
            )

    for sync_item in SyncQueue.objects.exclude(server_receipt={}).order_by("-created_at", "-id")[:500]:
        receipt = sync_item.server_receipt if isinstance(sync_item.server_receipt, dict) else {}
        language_metadata = _language_from_metadata(receipt)
        if bool(language_metadata.get("fallback_used")) and not (
            language_metadata.get("requested_language") and language_metadata.get("resolved_language")
        ):
            issues.append(
                {
                    "model": "risk.SyncQueue",
                    "record_id": sync_item.pk,
                    "client_submission_id": sync_item.client_submission_id,
                    "message": "Offline sync receipt records fallback without requested and resolved language metadata.",
                }
            )
        if _language_mismatch_requires_fallback_flag(
            language_metadata.get("requested_language"),
            language_metadata.get("resolved_language"),
            language_metadata.get("fallback_used"),
        ):
            issues.append(
                {
                    "model": "risk.SyncQueue",
                    "record_id": sync_item.pk,
                    "client_submission_id": sync_item.client_submission_id,
                    "message": "Offline sync receipt resolved a different language without marking fallback_used.",
                }
            )
    return issues


def _frontend_ui_dictionary_issues() -> list[dict[str, Any]]:
    path = Path(__file__).resolve().parents[2] / "frontend" / "lib" / "chv-localization.ts"
    if not path.exists():
        return [
            {
                "path": str(path),
                "message": "CHV frontend localization dictionary file is missing.",
            }
        ]
    text = path.read_text(encoding="utf-8")
    object_names = {
        "en": "EN_CHV_UI_TRANSLATIONS",
        "sw": "SW_CHV_UI_TRANSLATIONS",
        "luo": "LUO_CHV_UI_TRANSLATIONS",
    }
    key_sets: dict[str, set[str]] = {}
    placeholder_sets: dict[str, dict[str, set[str]]] = {}
    for language, object_name in object_names.items():
        match = re.search(
            rf"const\s+{object_name}[^=]*=\s*\{{(?P<body>.*?)\}}\s*(?:as const)?\s*;",
            text,
            re.DOTALL,
        )
        if match is None:
            return [
                {
                    "language": language,
                    "object_name": object_name,
                    "path": str(path),
                    "message": "CHV frontend localization dictionary object is missing.",
                }
            ]
        body = match.group("body")
        key_sets[language] = set(re.findall(r'^\s*"([^"]+)":', body, re.MULTILINE))
        placeholder_sets[language] = {
            key: set(re.findall(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", value))
            for key, value in re.findall(r'^\s*"([^"]+)":\s*"((?:[^"\\]|\\.)*)"', body, re.MULTILINE)
        }

    issues: list[dict[str, Any]] = []
    forbidden_public_health_prefixes = ("recommendation.",)
    for language, keys in key_sets.items():
        forbidden_keys = sorted(
            key for key in keys if key.startswith(forbidden_public_health_prefixes)
        )
        if forbidden_keys:
            issues.append(
                {
                    "language": language,
                    "path": str(path),
                    "keys": forbidden_keys,
                    "message": (
                        "CHV frontend UI dictionary contains public-health recommendation copy keys that must be governed backend templates."
                    ),
                }
            )
    supported_languages_match = re.search(
        r"export\s+const\s+CHV_SUPPORTED_LANGUAGES\s*=\s*\[(?P<body>.*?)\]\s*as const",
        text,
        re.DOTALL,
    )
    if supported_languages_match is None:
        issues.append(
            {
                "path": str(path),
                "message": "CHV frontend supported language list is missing.",
            }
        )
    else:
        frontend_supported_languages = re.findall(r'"([^"]+)"', supported_languages_match.group("body"))
        expected_supported_languages = list(SUPPORTED_CHV_LANGUAGES)
        if frontend_supported_languages != expected_supported_languages:
            issues.append(
                {
                    "path": str(path),
                    "frontend_supported_languages": frontend_supported_languages,
                    "expected_supported_languages": expected_supported_languages,
                    "message": "CHV frontend supported language list does not match backend supported languages.",
                }
            )

    english_keys = key_sets[DEFAULT_LANGUAGE_FALLBACK]
    for language in REQUIRED_TRANSLATION_LANGUAGES:
        missing = sorted(english_keys - key_sets.get(language, set()))
        extra = sorted(key_sets.get(language, set()) - english_keys)
        if missing or extra:
            issues.append(
                {
                    "language": language,
                    "missing_keys": missing,
                    "extra_keys": extra,
                    "message": "CHV frontend UI dictionary keys do not match English.",
                }
            )
        for key in sorted(english_keys & key_sets.get(language, set())):
            english_placeholders = placeholder_sets[DEFAULT_LANGUAGE_FALLBACK].get(key, set())
            language_placeholders = placeholder_sets[language].get(key, set())
            if english_placeholders != language_placeholders:
                issues.append(
                    {
                        "language": language,
                        "key": key,
                        "english_placeholders": sorted(english_placeholders),
                        "language_placeholders": sorted(language_placeholders),
                        "message": "CHV frontend UI dictionary placeholder keys do not match English.",
                    }
                )

    page_path = Path(__file__).resolve().parents[2] / "frontend" / "app" / "chv" / "page.tsx"
    if page_path.exists():
        page_text = page_path.read_text(encoding="utf-8")
        raw_attribute_patterns = (
            ("aria-label", re.compile(r'aria-label="([^"{]+)"')),
            ("placeholder", re.compile(r'placeholder="([^"{]+)"')),
            ("title", re.compile(r'title="([^"{]+)"')),
        )
        for attribute, pattern in raw_attribute_patterns:
            for match in pattern.finditer(page_text):
                raw_text = match.group(1).strip()
                if not raw_text:
                    continue
                issues.append(
                    {
                        "path": str(page_path),
                        "attribute": attribute,
                        "raw_text": raw_text,
                        "message": "CHV PWA UI attribute contains raw text instead of a localization dictionary key.",
                    }
                )
        if re.search(r"\breturn\s+error\.message\s*;", page_text):
            issues.append(
                {
                    "path": str(page_path),
                    "message": "CHV PWA sync error handling can display raw Error.message instead of safe localized copy.",
                }
            )
    else:
        issues.append(
            {
                "path": str(page_path),
                "message": "CHV PWA page file is missing from frontend localization audit.",
            }
        )
    return issues


def _extract_balanced_javascript_segment(
    text: str,
    open_index: int,
    *,
    open_char: str,
    close_char: str,
) -> str:
    if open_index < 0 or open_index >= len(text) or text[open_index] != open_char:
        return ""

    depth = 0
    quote_char = ""
    escaped = False
    for index in range(open_index, len(text)):
        char = text[index]
        if quote_char:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote_char:
                quote_char = ""
            continue
        if char in {"'", '"', "`"}:
            quote_char = char
            continue
        if char == open_char:
            depth += 1
        elif char == close_char:
            depth -= 1
            if depth == 0:
                return text[open_index : index + 1]
    return ""


def _extract_javascript_property_object(text: str, property_name: str) -> str:
    match = re.search(rf"\b{re.escape(property_name)}\s*:", text)
    if match is None:
        return ""
    open_index = text.find("{", match.end())
    return _extract_balanced_javascript_segment(text, open_index, open_char="{", close_char="}")


def _extract_javascript_property_array(text: str, property_name: str) -> str:
    match = re.search(rf"\b{re.escape(property_name)}\s*:", text)
    if match is None:
        return ""
    open_index = text.find("[", match.end())
    return _extract_balanced_javascript_segment(text, open_index, open_char="[", close_char="]")


def _javascript_array_has_static_values(text: str, property_name: str) -> bool:
    array_text = _extract_javascript_property_array(text, property_name)
    return bool(array_text and array_text[1:-1].strip())


def _javascript_boolean_property_is_true(text: str, property_name: str) -> bool:
    return bool(re.search(rf"\b{re.escape(property_name)}\s*:\s*true\b", text))


def _frontend_local_fallback_public_health_issues(path: Path, text: str) -> list[dict[str, Any]]:
    function_index = text.find("function buildFallbackBundle")
    if function_index < 0:
        return []
    function_open_index = text.find("{", function_index)
    function_body = _extract_balanced_javascript_segment(
        text,
        function_open_index,
        open_char="{",
        close_char="}",
    )
    if not function_body:
        return []

    issues: list[dict[str, Any]] = []
    bundle_specs = (
        (
            "guidance_bundle",
            "items",
            "Local CHV PWA fallback guidance bundle contains static guidance items instead of failing closed.",
            "Local CHV PWA fallback guidance bundle does not explicitly mark governed content as unavailable.",
        ),
        (
            "decision_support_rule_bundle",
            "recommendations",
            "Local CHV PWA fallback decision-support bundle contains static recommendations instead of failing closed.",
            "Local CHV PWA fallback decision-support bundle does not explicitly mark governed content as unavailable.",
        ),
    )
    for property_name, array_name, static_copy_message, availability_message in bundle_specs:
        block = _extract_javascript_property_object(function_body, property_name)
        if not block:
            continue
        if _javascript_array_has_static_values(block, array_name):
            issues.append(
                {
                    "path": str(path),
                    "property": property_name,
                    "array": array_name,
                    "message": static_copy_message,
                }
            )
        if not _javascript_boolean_property_is_true(block, "content_unavailable"):
            issues.append(
                {
                    "path": str(path),
                    "property": property_name,
                    "message": availability_message,
                }
            )
    return issues


def _static_public_health_fallback_issues() -> list[dict[str, Any]]:
    repo_root = Path(__file__).resolve().parents[2]
    forbidden_markers = (
        "static_safety_fallback",
        "cholera.prevention.core_fallback",
        "OFFLINE_GUIDANCE_FALLBACK_BODY",
        "Fallback content until an approved offline CHV bundle template is available.",
    )
    issues: list[dict[str, Any]] = []
    for relative_path in (
        "backend/risk/chv_offline.py",
        "backend/risk/message_management.py",
        "frontend/app/chv/page.tsx",
        "frontend/lib/chv-localization.ts",
    ):
        path = repo_root / relative_path
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        markers = [marker for marker in forbidden_markers if marker in text]
        if markers:
            issues.append(
                {
                    "path": str(path),
                    "markers": markers,
                    "message": (
                        "Static public-health fallback copy or unmanaged fallback markers remain outside governed templates."
                    ),
                }
            )
        if relative_path == "frontend/app/chv/page.tsx":
            issues.extend(_frontend_local_fallback_public_health_issues(path, text))
    return issues


def _safe_error_text_exposes_sensitive_value(value: str) -> bool:
    text = str(value or "")
    if not text:
        return False
    return any(pattern.search(text) for pattern in [*SAFE_ERROR_VALUE_PATTERNS, *RAW_ERROR_COPY_PATTERNS])


def _iter_sensitive_payload_values(payload: Any, *, parent_key: str = ""):
    if isinstance(payload, dict):
        for key, value in payload.items():
            normalized_key = str(key or "").strip().lower()
            if normalized_key in SENSITIVE_PAYLOAD_KEYS:
                if isinstance(value, (str, int, float)):
                    yield str(value)
                elif value not in (None, "", [], {}):
                    yield str(value)
            if isinstance(value, (dict, list, tuple)):
                yield from _iter_sensitive_payload_values(value, parent_key=normalized_key or parent_key)
    elif isinstance(payload, (list, tuple)):
        for value in payload:
            if isinstance(value, (dict, list, tuple)):
                yield from _iter_sensitive_payload_values(value, parent_key=parent_key)


def _safe_error_text_echoes_sensitive_payload_value(error_text: str, payload: Any) -> bool:
    text = str(error_text or "")
    if not text:
        return False
    for raw_value in _iter_sensitive_payload_values(payload):
        value = raw_value.strip()
        if len(value) < 4:
            continue
        if value in text:
            return True
    return False


def _sync_error_sensitive_copy_issues() -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    frontend_api_path = Path(__file__).resolve().parents[2] / "frontend" / "lib" / "chv-offline-api.ts"
    if frontend_api_path.exists():
        frontend_api_text = frontend_api_path.read_text(encoding="utf-8")
        if re.search(r"\breturn\s+body\.(?:detail|message)\s*;", frontend_api_text):
            issues.append(
                {
                    "path": str(frontend_api_path),
                    "field": "readErrorDetail",
                    "message": "CHV frontend offline API can propagate raw server error detail into sync error objects.",
                }
            )
    for audit in CHVOfflineRejectedSubmissionAudit.objects.order_by("-created_at", "-id")[:500]:
        if _safe_error_text_exposes_sensitive_value(audit.safe_error_summary):
            issues.append(
                {
                    "model": "risk.CHVOfflineRejectedSubmissionAudit",
                    "record_id": audit.pk,
                    "audit_public_id": str(audit.public_id),
                    "field": "safe_error_summary",
                    "message": "Safe CHV offline rejection copy appears to expose raw sensitive payload values.",
                }
            )
    for sync_item in SyncQueue.objects.exclude(error_message="").order_by("-created_at", "-id")[:500]:
        if _safe_error_text_exposes_sensitive_value(sync_item.error_message):
            issues.append(
                {
                    "model": "risk.SyncQueue",
                    "record_id": sync_item.pk,
                    "client_submission_id": sync_item.client_submission_id,
                    "field": "error_message",
                    "message": "CHV offline sync error copy appears to expose raw sensitive payload values.",
                }
            )
        elif _safe_error_text_echoes_sensitive_payload_value(sync_item.error_message, sync_item.payload):
            issues.append(
                {
                    "model": "risk.SyncQueue",
                    "record_id": sync_item.pk,
                    "client_submission_id": sync_item.client_submission_id,
                    "field": "error_message",
                    "message": "CHV offline sync error copy echoes a sensitive submitted payload value.",
                }
            )
    for sync_item in SyncQueue.objects.exclude(server_receipt={}).order_by("-created_at", "-id")[:500]:
        receipt = sync_item.server_receipt if isinstance(sync_item.server_receipt, dict) else {}
        explanation = receipt.get("explanation")
        if not isinstance(explanation, str) or not explanation.strip():
            continue
        if _safe_error_text_exposes_sensitive_value(explanation):
            issues.append(
                {
                    "model": "risk.SyncQueue",
                    "record_id": sync_item.pk,
                    "client_submission_id": sync_item.client_submission_id,
                    "field": "server_receipt.explanation",
                    "message": "CHV offline sync receipt explanation appears to expose raw sensitive payload values.",
                }
            )
        elif _safe_error_text_echoes_sensitive_payload_value(explanation, sync_item.payload):
            issues.append(
                {
                    "model": "risk.SyncQueue",
                    "record_id": sync_item.pk,
                    "client_submission_id": sync_item.client_submission_id,
                    "field": "server_receipt.explanation",
                    "message": "CHV offline sync receipt explanation echoes a sensitive submitted payload value.",
                }
            )
    return issues


def _counter_records(counter: Counter) -> list[dict[str, Any]]:
    return [
        {"key": key, "count": count}
        for key, count in sorted(counter.items(), key=lambda item: str(item[0]))
    ]


def _fallback_surface_metric(surface: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    total_count = sum(record["count"] for record in records)
    fallback_count = sum(record["count"] for record in records if record["fallback_used"])
    by_requested_language = Counter()
    by_language = Counter()
    fallback_by_language = Counter()
    for record in records:
        requested_language = record.get("requested_language") or "unknown"
        language = record["resolved_language"] or "unknown"
        by_requested_language[requested_language] += record["count"]
        by_language[language] += record["count"]
        if record["fallback_used"]:
            fallback_by_language[language] += record["count"]
    return {
        "surface": surface,
        "total_count": total_count,
        "fallback_count": fallback_count,
        "fallback_rate_pct": _percent(fallback_count, total_count),
        "by_requested_language": _counter_records(by_requested_language),
        "by_resolved_language": _counter_records(by_language),
        "fallback_by_resolved_language": _counter_records(fallback_by_language),
    }


def _delivery_language_records(queryset, status_field: str = "status") -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    value_fields = ["resolved_language", "fallback_used", status_field]
    if hasattr(queryset.model, "requested_language"):
        value_fields.append("requested_language")
    for row in queryset.values(*value_fields):
        records.append(
            {
                "requested_language": row.get("requested_language") or "unknown",
                "resolved_language": row.get("resolved_language") or "unknown",
                "fallback_used": bool(row.get("fallback_used")),
                "status": row.get(status_field) or "UNKNOWN",
                "count": 1,
            }
        )
    return records


def _sync_language_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for sync_item in SyncQueue.objects.order_by("-created_at", "-id")[:1000]:
        receipt = sync_item.server_receipt if isinstance(sync_item.server_receipt, dict) else {}
        language = _language_from_metadata(receipt)
        if not language:
            continue
        records.append(
            {
                "requested_language": language.get("requested_language") or "unknown",
                "resolved_language": language.get("resolved_language") or "unknown",
                "fallback_used": bool(language.get("fallback_used")),
                "status": sync_item.status,
                "count": 1,
            }
        )
    return records


def _coerce_positive_count(value: Any) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        return 0
    return max(count, 0)


def _device_bundle_language_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for registration in CHVDeviceRegistration.objects.filter(is_active=True).order_by("-updated_at", "-id")[:1000]:
        metadata = registration.metadata if isinstance(registration.metadata, dict) else {}
        request_counts = metadata.get("offline_bundle_request_counts")
        registration_request_records: list[dict[str, Any]] = []
        if isinstance(request_counts, list):
            for entry in request_counts:
                if not isinstance(entry, dict):
                    continue
                count = _coerce_positive_count(entry.get("count"))
                if count <= 0:
                    continue
                registration_request_records.append(
                    {
                        "requested_language": entry.get("requested_language") or "unknown",
                        "resolved_language": entry.get("resolved_language") or "unknown",
                        "fallback_used": bool(entry.get("fallback_used")),
                        "status": "BUNDLE_REQUEST",
                        "count": count,
                    }
                )
            if registration_request_records:
                records.extend(registration_request_records)
                continue
        elif isinstance(request_counts, dict):
            for key, raw_count in request_counts.items():
                count = _coerce_positive_count(raw_count)
                if count <= 0:
                    continue
                parts = str(key).split("|")
                details = {}
                for part in parts:
                    name, separator, value = part.partition("=")
                    if separator:
                        details[name.strip()] = value.strip()
                registration_request_records.append(
                    {
                        "requested_language": details.get("requested") or details.get("requested_language") or "unknown",
                        "resolved_language": details.get("resolved") or details.get("resolved_language") or "unknown",
                        "fallback_used": details.get("fallback") in {"1", "true", "yes"},
                        "status": "BUNDLE_REQUEST",
                        "count": count,
                    }
                )
            if registration_request_records:
                records.extend(registration_request_records)
                continue

        language = _language_from_metadata(metadata)
        records.append(
            {
                "requested_language": language.get("requested_language") or registration.preferred_language or "unknown",
                "resolved_language": language.get("bundle_resolved_language")
                or language.get("resolved_language")
                or registration.preferred_language
                or "unknown",
                "fallback_used": bool(language.get("bundle_fallback_used") or language.get("fallback_used")),
                "status": "ACTIVE_DEVICE",
                "count": 1,
            }
        )
    return records


def _translation_review_age_summary() -> dict[str, Any]:
    now = timezone.now()
    pending_records: list[dict[str, Any]] = []
    template_queryset = MessageTemplate.objects.filter(language__in=REQUIRED_TRANSLATION_LANGUAGES).exclude(
        language=DEFAULT_LANGUAGE_FALLBACK
    )
    for template in template_queryset.exclude(translation_status=MessageTemplate.TRANSLATION_APPROVED).order_by("-updated_at")[:500]:
        age_days = max((now - template.updated_at).days, 0)
        pending_records.append(
            {
                "model": "risk.MessageTemplate",
                "public_id": str(template.public_id),
                "key": template.template_key,
                "language": template.language,
                "status": template.translation_status,
                "age_days": age_days,
            }
        )
    menu_queryset = UssdMenuVersion.objects.filter(language__in=REQUIRED_TRANSLATION_LANGUAGES).exclude(
        language=DEFAULT_LANGUAGE_FALLBACK
    )
    for menu_version in menu_queryset.exclude(translation_status=UssdMenuVersion.TRANSLATION_APPROVED).order_by("-updated_at")[:500]:
        age_days = max((now - menu_version.updated_at).days, 0)
        pending_records.append(
            {
                "model": "risk.UssdMenuVersion",
                "public_id": str(menu_version.public_id),
                "key": menu_version.menu_key,
                "language": menu_version.language,
                "status": menu_version.translation_status,
                "age_days": age_days,
            }
        )
    ages = [record["age_days"] for record in pending_records]
    return {
        "pending_review_count": len(pending_records),
        "max_age_days": max(ages) if ages else 0,
        "average_age_days": round(sum(ages) / len(ages), 3) if ages else 0.0,
        "oldest_records": sorted(pending_records, key=lambda item: item["age_days"], reverse=True)[:10],
    }


def _is_missing_translation_issue(issue: dict[str, Any]) -> bool:
    message = str(issue.get("message", "")).lower()
    return "language variant is missing" in message


def build_chv_localization_rollout_snapshot() -> dict[str, Any]:
    chv_language_counts = Counter(
        chv.preferred_language or "missing"
        for chv in CHV.objects.filter(is_active=True).only("preferred_language")
    )
    device_language_counts = Counter(
        registration.preferred_language or "missing"
        for registration in CHVDeviceRegistration.objects.filter(is_active=True).only("preferred_language")
    )

    ussd_sessions_by_language_outcome = Counter()
    for log in UssdSessionLog.objects.order_by("-created_at", "-id")[:1000]:
        ussd_sessions_by_language_outcome[(log.resolved_language or "unknown", log.session_outcome or "UNKNOWN")] += 1

    chv_sms_deliveries_by_language_outcome = Counter()
    for record in Alert.objects.filter(channel=Alert.CHANNEL_SMS).exclude(template_key="").order_by("-created_at", "-id")[:1000]:
        chv_sms_deliveries_by_language_outcome[(record.resolved_language or "unknown", record.status or "UNKNOWN")] += 1
    for record in CHVMessage.objects.exclude(template_key="").order_by("-created_at", "-id")[:1000]:
        chv_sms_deliveries_by_language_outcome[(record.resolved_language or "unknown", record.status or "UNKNOWN")] += 1

    template_translation_issues = _template_translation_registry_issues()
    ussd_translation_issues = _ussd_translation_registry_issues()
    missing_translation_count = sum(
        1
        for issue in [*template_translation_issues, *ussd_translation_issues]
        if _is_missing_translation_issue(issue)
    )

    fallback_metrics = [
        _fallback_surface_metric(
            "chv_sms",
            [
                *_delivery_language_records(Alert.objects.filter(channel=Alert.CHANNEL_SMS).exclude(template_key="")),
                *_delivery_language_records(CHVMessage.objects.exclude(template_key="")),
            ],
        ),
        _fallback_surface_metric(
            "ussd",
            _delivery_language_records(UssdSessionLog.objects.all(), status_field="session_outcome"),
        ),
        _fallback_surface_metric("offline_sync", _sync_language_records()),
        _fallback_surface_metric("offline_bundle", _device_bundle_language_records()),
    ]
    total_fallback_count = sum(metric["fallback_count"] for metric in fallback_metrics)
    total_language_event_count = sum(metric["total_count"] for metric in fallback_metrics)

    return {
        "schema_version": LOCALIZATION_ROLLOUT_SCHEMA_VERSION,
        "generated_at": timezone.now(),
        "supported_languages": list(SUPPORTED_CHV_LANGUAGES),
        "default_language": DEFAULT_LANGUAGE_FALLBACK,
        "chv_preferred_language_counts": _counter_records(chv_language_counts),
        "active_chv_count": sum(chv_language_counts.values()),
        "device_preferred_language_counts": _counter_records(device_language_counts),
        "active_device_count": sum(device_language_counts.values()),
        "offline_bundle_requests_by_language": _fallback_surface_metric(
            "offline_bundle",
            _device_bundle_language_records(),
        ),
        "fallback_metrics": fallback_metrics,
        "fallback_rate_pct": _percent(total_fallback_count, total_language_event_count),
        "ussd_sessions_by_language_and_outcome": [
            {"language": language, "outcome": outcome, "count": count}
            for (language, outcome), count in sorted(ussd_sessions_by_language_outcome.items())
        ],
        "chv_sms_deliveries_by_language_and_outcome": [
            {"language": language, "outcome": outcome, "count": count}
            for (language, outcome), count in sorted(chv_sms_deliveries_by_language_outcome.items())
        ],
        "missing_translation_count": missing_translation_count,
        "translation_review_age": _translation_review_age_summary(),
        "rollout_path": [
            {
                "step": "ship_english_audit_with_required_language_gaps",
                "status": "complete",
            },
            {
                "step": "add_kiswahili_and_dholuo_drafts",
                "status": "complete" if missing_translation_count == 0 else "in_progress",
            },
            {
                "step": "approve_ussd_and_chv_high_risk_guidance",
                "status": "complete" if not template_translation_issues and not ussd_translation_issues else "blocked",
            },
            {
                "step": "enable_language_preference_for_pilot_ward",
                "status": "ready" if sum(chv_language_counts.values()) else "not_started",
            },
            {
                "step": "monitor_fallback_and_failure_rates",
                "status": "active" if total_language_event_count else "ready",
            },
            {
                "step": "expand_to_all_chv_users_after_audit_passes",
                "status": "ready" if missing_translation_count == 0 and total_fallback_count == 0 else "waiting",
            },
        ],
    }


def build_message_governance_audit() -> dict[str, Any]:
    inventory = build_message_inventory_report()
    localization_inventory = build_chv_localization_inventory_report()
    template_issues = _template_validation_issues()
    delivery_issues = _delivery_template_issues()
    governance_metadata_issues, governed_delivery_record_count = _delivery_governance_metadata_issues()
    delivery_language_traceability_issues = _delivery_language_traceability_issues()
    household_template_issues = _household_message_template_issues()
    retired_template_usage_issues = _retired_template_usage_issues()
    language_fallback_issues = _language_fallback_issues()
    template_translation_registry_issues = _template_translation_registry_issues()
    ussd_translation_registry_issues = _ussd_translation_registry_issues()
    opt_out_ignored_issues = _opt_out_ignored_issues()
    high_risk_alert_source_issues = _high_risk_alert_source_reference_issues()
    unsupported_language_code_issues = _unsupported_language_code_issues()
    chv_language_preference_issues = _chv_language_preference_issues()
    translated_public_health_copy_usage_issues = _translated_public_health_copy_usage_issues()
    fallback_without_metadata_issues = _fallback_without_metadata_issues()
    frontend_ui_dictionary_issues = _frontend_ui_dictionary_issues()
    static_public_health_fallback_issues = _static_public_health_fallback_issues()
    sync_error_sensitive_copy_issues = _sync_error_sensitive_copy_issues()
    ussd_node_length_issues = _ussd_node_length_issues()
    localization_rollout = build_chv_localization_rollout_snapshot()
    strict_localization_issue_count = sum(
        len(items)
        for items in (
            unsupported_language_code_issues,
            chv_language_preference_issues,
            template_translation_registry_issues,
            ussd_translation_registry_issues,
            language_fallback_issues,
            delivery_language_traceability_issues,
            translated_public_health_copy_usage_issues,
            fallback_without_metadata_issues,
            ussd_node_length_issues,
            frontend_ui_dictionary_issues,
            static_public_health_fallback_issues,
            sync_error_sensitive_copy_issues,
        )
    )
    ussd_audit = build_ussd_governance_audit()
    ussd_gaps = [
        gap
        for check in ussd_audit["checks"]
        for gap in check.get("gaps", [])
    ]
    checks = [
        _check_result(
            "phase_0_message_inventory_required_fields",
            "pass" if not inventory["missing_required_fields"] else "fail",
            (
                "Current SMS, USSD, prevention, facility, and escalation messages carry owner, audience, language, and risk metadata."
                if not inventory["missing_required_fields"]
                else "Some inventoried messages are missing required governance fields."
            ),
            {
                "inventory_count": inventory["inventory_count"],
                "missing_required_fields": inventory["missing_required_fields"],
            },
            inventory["missing_required_fields"],
        ),
        _check_result(
            "phase_0_unmanaged_free_text_paths_identified",
            "pass",
            "Unmanaged or operator-entered text paths are explicitly identified for later governance tightening.",
            {"unmanaged_free_text_path_count": len(inventory["unmanaged_free_text_paths"])},
            [],
        ),
        _check_result(
            "phase_0_emergency_overrides_documented",
            "pass" if inventory["emergency_override_cases"] else "fail",
            "Emergency override cases are documented and map to contact-preference audit events.",
            {"emergency_override_case_count": len(inventory["emergency_override_cases"])},
            [] if inventory["emergency_override_cases"] else ["missing_emergency_override_cases"],
        ),
        _check_result(
            "phase_0_chv_localization_surface_inventory",
            "pass" if not localization_inventory["missing_required_fields"] else "fail",
            (
                "CHV-facing PWA, offline bundle, SMS, sync, and USSD language surfaces are inventoried with owner, audience, channel, category, risk, and source."
                if not localization_inventory["missing_required_fields"]
                else "One or more CHV localization surfaces are missing required inventory metadata."
            ),
            {
                "surface_count": localization_inventory["surface_count"],
                "category_counts": localization_inventory["category_counts"],
                "missing_required_fields": localization_inventory["missing_required_fields"],
                "unmanaged_english_only_gap_count": len(localization_inventory["unmanaged_english_only_gaps"]),
            },
            ["missing_chv_localization_inventory_metadata"] if localization_inventory["missing_required_fields"] else [],
        ),
        _check_result(
            "phase_0_chv_english_only_gaps_documented",
            "pass",
            (
                "Any remaining English-only CHV localization gaps are explicitly documented."
                if localization_inventory["unmanaged_english_only_gaps"]
                else "No unmanaged English-only CHV localization gaps remain in the current inventory."
            ),
            {
                "unmanaged_english_only_gap_count": len(localization_inventory["unmanaged_english_only_gaps"]),
                "unmanaged_english_only_gaps": localization_inventory["unmanaged_english_only_gaps"][:25],
            },
            [],
        ),
        _check_result(
            "phase_1_template_registry_placeholder_validation",
            "pass" if not template_issues else "fail",
            (
                "Registered templates have bodies and placeholder declarations that agree."
                if not template_issues
                else "One or more registered templates have invalid placeholder declarations."
            ),
            {"issue_count": len(template_issues), "issues": template_issues[:25]},
            ["invalid_template_placeholder_registry"] if template_issues else [],
        ),
        _check_result(
            "phase_1_delivery_records_reference_templates",
            "pass" if not delivery_issues else "fail",
            (
                "Template-linked delivery records reference existing, approved, non-retired templates."
                if not delivery_issues
                else "One or more template-linked delivery records have unsafe template references."
            ),
            {"issue_count": len(delivery_issues), "issues": delivery_issues[:25]},
            ["unsafe_template_delivery_reference"] if delivery_issues else [],
        ),
        _check_result(
            "phase_2_delivery_records_include_audience_decisions",
            "pass" if not governance_metadata_issues else "fail",
            (
                "Governed delivery records include template and audience consent decision metadata."
                if not governance_metadata_issues
                else "One or more governed delivery records have incomplete phase 2 audience decision metadata."
            ),
            {
                "governed_delivery_record_count": governed_delivery_record_count,
                "issue_count": len(governance_metadata_issues),
                "issues": governance_metadata_issues[:25],
            },
            ["invalid_message_audience_governance_metadata"] if governance_metadata_issues else [],
        ),
        _check_result(
            "phase_5_chv_sms_delivery_language_traceability",
            "pass" if not delivery_language_traceability_issues else "fail",
            (
                "CHV SMS delivery records include requested language, resolved template language, and fallback status."
                if not delivery_language_traceability_issues
                else "One or more CHV SMS delivery records are missing or drifting from template language metadata."
            ),
            {
                "issue_count": len(delivery_language_traceability_issues),
                "issues": delivery_language_traceability_issues[:25],
            },
            ["invalid_chv_sms_delivery_language_traceability"] if delivery_language_traceability_issues else [],
        ),
        _check_result(
            "phase_3_ussd_menu_governance",
            ussd_audit["overall_status"],
            (
                "USSD sessions can be traced to menu version and language, and analytics classify completion, invalid input, and abandonment."
                if ussd_audit["overall_status"] == "pass"
                else "One or more USSD governance checks failed."
            ),
            {
                "schema_version": ussd_audit["schema_version"],
                "checks": ussd_audit["checks"],
            },
            ussd_gaps,
        ),
        _check_result(
            "phase_2_chv_template_translation_registry",
            "pass" if not template_translation_registry_issues else "fail",
            (
                "CHV-facing message templates have required language variants, English source linkage, placeholder parity, caveats, and translation review metadata."
                if not template_translation_registry_issues
                else "One or more CHV-facing message template translations are missing required coverage, source linkage, parity, caveats, or review metadata."
            ),
            {
                "required_languages": list(REQUIRED_TRANSLATION_LANGUAGES),
                "issue_count": len(template_translation_registry_issues),
                "issues": template_translation_registry_issues[:25],
            },
            ["invalid_chv_template_translation_registry"] if template_translation_registry_issues else [],
        ),
        _check_result(
            "phase_2_ussd_translation_registry",
            "pass" if not ussd_translation_registry_issues else "fail",
            (
                "USSD menu translations have required language variants, English source linkage, route parity, safe fallback copy, and translation review metadata."
                if not ussd_translation_registry_issues
                else "One or more USSD menu translations are missing required coverage, source linkage, route parity, or review metadata."
            ),
            {
                "required_languages": list(REQUIRED_TRANSLATION_LANGUAGES),
                "issue_count": len(ussd_translation_registry_issues),
                "issues": ussd_translation_registry_issues[:25],
            },
            ["invalid_ussd_translation_registry"] if ussd_translation_registry_issues else [],
        ),
        _check_result(
            "phase_5_household_messages_use_approved_templates",
            "pass" if not household_template_issues else "fail",
            (
                "Household direct-message records use approved, non-retired templates."
                if not household_template_issues
                else "One or more household direct-message records were sent without an approved template."
            ),
            {"issue_count": len(household_template_issues), "issues": household_template_issues[:25]},
            ["household_message_without_approved_template"] if household_template_issues else [],
        ),
        _check_result(
            "phase_5_templates_not_used_after_retirement",
            "pass" if not retired_template_usage_issues else "fail",
            (
                "No delivery records use templates after their retirement timestamp."
                if not retired_template_usage_issues
                else "One or more delivery records used a template after retirement."
            ),
            {"issue_count": len(retired_template_usage_issues), "issues": retired_template_usage_issues[:25]},
            ["template_used_after_retirement"] if retired_template_usage_issues else [],
        ),
        _check_result(
            "phase_5_language_fallbacks_present",
            "pass" if not language_fallback_issues else "fail",
            (
                "Message and USSD language variants have English fallback records."
                if not language_fallback_issues
                else "One or more message or USSD language variants are missing an English fallback."
            ),
            {"issue_count": len(language_fallback_issues), "issues": language_fallback_issues[:25]},
            ["missing_language_fallback"] if language_fallback_issues else [],
        ),
        _check_result(
            "phase_5_opt_outs_not_ignored",
            "pass" if not opt_out_ignored_issues else "fail",
            (
                "Allowed direct-message records do not ignore opt-out decisions."
                if not opt_out_ignored_issues
                else "One or more allowed direct-message records ignored an opt-out decision."
            ),
            {"issue_count": len(opt_out_ignored_issues), "issues": opt_out_ignored_issues[:25]},
            ["opt_out_ignored"] if opt_out_ignored_issues else [],
        ),
        _check_result(
            "phase_5_high_risk_alerts_have_source_references",
            "pass" if not high_risk_alert_source_issues else "fail",
            (
                "High-risk alert messages retain source risk score or alert references."
                if not high_risk_alert_source_issues
                else "One or more high-risk alert messages are missing source references."
            ),
            {"issue_count": len(high_risk_alert_source_issues), "issues": high_risk_alert_source_issues[:25]},
            ["high_risk_alert_missing_source_reference"] if high_risk_alert_source_issues else [],
        ),
        _check_result(
            "phase_7_supported_language_storage",
            "pass" if not unsupported_language_code_issues else "fail",
            (
                "Stored CHV localization language fields use only supported language codes."
                if not unsupported_language_code_issues
                else "One or more stored language fields use unsupported language codes."
            ),
            {
                "supported_languages": list(SUPPORTED_CHV_LANGUAGES),
                "issue_count": len(unsupported_language_code_issues),
                "issues": unsupported_language_code_issues[:25],
            },
            ["unsupported_language_code_stored"] if unsupported_language_code_issues else [],
        ),
        _check_result(
            "phase_7_chv_language_preferences_valid",
            "pass" if not chv_language_preference_issues else "fail",
            (
                "Active CHVs and device registrations carry valid preferred language values."
                if not chv_language_preference_issues
                else "One or more active CHVs or device registrations have missing or invalid language preferences."
            ),
            {
                "issue_count": len(chv_language_preference_issues),
                "issues": chv_language_preference_issues[:25],
            },
            ["invalid_chv_language_preference"] if chv_language_preference_issues else [],
        ),
        _check_result(
            "phase_7_translated_public_health_copy_approved_before_use",
            "pass" if not translated_public_health_copy_usage_issues else "fail",
            (
                "Translated public-health copy is used only after reviewer approval."
                if not translated_public_health_copy_usage_issues
                else "One or more translated public-health messages were used before approval."
            ),
            {
                "issue_count": len(translated_public_health_copy_usage_issues),
                "issues": translated_public_health_copy_usage_issues[:25],
            },
            ["translated_public_health_copy_used_before_approval"] if translated_public_health_copy_usage_issues else [],
        ),
        _check_result(
            "phase_7_fallback_metadata_complete",
            "pass" if not fallback_without_metadata_issues else "fail",
            (
                "Language fallback events include requested language, resolved language, and fallback metadata."
                if not fallback_without_metadata_issues
                else "One or more language fallback events are missing audit metadata."
            ),
            {
                "issue_count": len(fallback_without_metadata_issues),
                "issues": fallback_without_metadata_issues[:25],
            },
            ["fallback_without_language_metadata"] if fallback_without_metadata_issues else [],
        ),
        _check_result(
            "phase_7_ussd_node_length_budget",
            "pass" if not ussd_node_length_issues else "fail",
            (
                "Approved USSD menu nodes and fallback copy fit the configured response length budget."
                if not ussd_node_length_issues
                else "One or more approved USSD menu nodes exceed the configured response length budget."
            ),
            {
                "max_chars": USSD_RESPONSE_TEXT_MAX_CHARS,
                "issue_count": len(ussd_node_length_issues),
                "issues": ussd_node_length_issues[:25],
            },
            ["ussd_node_exceeds_length_budget"] if ussd_node_length_issues else [],
        ),
        _check_result(
            "phase_7_frontend_ui_dictionary_parity",
            "pass" if not frontend_ui_dictionary_issues else "fail",
            (
                "CHV frontend UI dictionaries contain the required English, Kiswahili, and Dholuo keys."
                if not frontend_ui_dictionary_issues
                else "One or more CHV frontend UI dictionaries are missing keys or placeholder parity."
            ),
            {
                "issue_count": len(frontend_ui_dictionary_issues),
                "issues": frontend_ui_dictionary_issues[:25],
            },
            ["frontend_ui_dictionary_missing_key"] if frontend_ui_dictionary_issues else [],
        ),
        _check_result(
            "phase_7_no_static_public_health_fallback_copy",
            "pass" if not static_public_health_fallback_issues else "fail",
            (
                "CHV public-health fallback copy is served only from governed templates or fails closed."
                if not static_public_health_fallback_issues
                else "One or more static public-health fallback copy paths remain outside governed templates."
            ),
            {
                "issue_count": len(static_public_health_fallback_issues),
                "issues": static_public_health_fallback_issues[:25],
            },
            ["static_public_health_fallback_copy"] if static_public_health_fallback_issues else [],
        ),
        _check_result(
            "phase_7_sync_error_copy_pii_safe",
            "pass" if not sync_error_sensitive_copy_issues else "fail",
            (
                "CHV sync and safe-error copy does not expose raw sensitive payload values."
                if not sync_error_sensitive_copy_issues
                else "One or more CHV sync or safe-error messages appear to expose sensitive payload values."
            ),
            {
                "issue_count": len(sync_error_sensitive_copy_issues),
                "issues": sync_error_sensitive_copy_issues[:25],
            },
            ["sync_error_copy_exposes_sensitive_payload"] if sync_error_sensitive_copy_issues else [],
        ),
        _check_result(
            "phase_7_rollout_monitoring_metrics_available",
            "pass",
            "Localization rollout monitoring includes language preference counts, fallback rates, USSD outcomes, SMS outcomes, missing translation count, and review age.",
            {
                "schema_version": localization_rollout["schema_version"],
                "active_chv_count": localization_rollout["active_chv_count"],
                "active_device_count": localization_rollout["active_device_count"],
                "fallback_rate_pct": localization_rollout["fallback_rate_pct"],
                "missing_translation_count": localization_rollout["missing_translation_count"],
                "translation_review_age": localization_rollout["translation_review_age"],
            },
            [],
        ),
        _check_result(
            "phase_7_strict_localization_audit",
            "pass" if strict_localization_issue_count == 0 and ussd_audit["overall_status"] == "pass" else "fail",
            (
                "Strict localization audit passes across storage, translation coverage, fallback metadata, USSD parity, frontend dictionaries, and safe sync copy."
                if strict_localization_issue_count == 0 and ussd_audit["overall_status"] == "pass"
                else "Strict localization audit found one or more rollout-blocking issues."
            ),
            {
                "strict_issue_count": strict_localization_issue_count,
                "ussd_audit_status": ussd_audit["overall_status"],
                "fallback_rate_pct": localization_rollout["fallback_rate_pct"],
                "missing_translation_count": localization_rollout["missing_translation_count"],
            },
            ["strict_localization_audit_failed"]
            if strict_localization_issue_count or ussd_audit["overall_status"] != "pass"
            else [],
        ),
    ]
    overall_status = "fail" if any(check["status"] == "fail" for check in checks) else "pass"
    return {
        "schema_version": MESSAGE_GOVERNANCE_SCHEMA_VERSION,
        "overall_status": overall_status,
        "inventory": inventory,
        "chv_localization_inventory": localization_inventory,
        "localization_rollout": localization_rollout,
        "strict_localization_issue_count": strict_localization_issue_count,
        "template_count": MessageTemplate.objects.count(),
        "audit_checks": checks,
    }
