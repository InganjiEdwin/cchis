from __future__ import annotations

from dataclasses import asdict, dataclass
from string import Formatter
from typing import Any

from django.core.exceptions import ValidationError

from risk.models import (
    Alert,
    CHVMessage,
    ContactPreference,
    FacilityReadinessUpdateRequest,
    MessageTemplate,
    UssdMenuVersion,
)
from risk.ussd_governance import build_ussd_governance_audit


MESSAGE_GOVERNANCE_SCHEMA_VERSION = "message-governance-phase-0-5-v1"
MESSAGE_AUDIENCE_GOVERNANCE_SCHEMA_VERSION = "message-audience-governance-phase-2-v1"
DEFAULT_LANGUAGE_FALLBACK = "en"


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
    elif allow_unapproved:
        queryset = queryset.filter(retired_at__isnull=True)
    else:
        queryset = queryset.filter(
            approval_status=MessageTemplate.APPROVAL_APPROVED,
            retired_at__isnull=True,
        )

    template = queryset.order_by("-version", "-created_at").first()
    if template is None:
        version_label = f" v{version}" if version is not None else ""
        raise ValueError(f"No message template registered for {normalized_key}{version_label} ({normalized_language}).")
    return template


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
    template = _resolve_message_template(
        template_key=template_key,
        version=version,
        language=language,
        allow_unapproved=allow_unapproved,
    )

    if audience_type and template.audience_type != audience_type:
        raise ValueError(f"Template {template.template_key} is for {template.audience_type}, not {audience_type}.")
    if channel and template.channel != channel:
        raise ValueError(f"Template {template.template_key} is for {template.channel}, not {channel}.")

    validate_message_template_definition(template)
    _assert_template_usable_for_delivery(
        template,
        allow_unapproved=allow_unapproved,
        household_broadcast=household_broadcast,
    )

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
    return (
        MessageTemplate.objects.filter(template_key=template_key, version=template_version)
        .order_by("language", "-created_at")
        .first()
    )


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


def build_message_governance_audit() -> dict[str, Any]:
    inventory = build_message_inventory_report()
    template_issues = _template_validation_issues()
    delivery_issues = _delivery_template_issues()
    governance_metadata_issues, governed_delivery_record_count = _delivery_governance_metadata_issues()
    household_template_issues = _household_message_template_issues()
    retired_template_usage_issues = _retired_template_usage_issues()
    language_fallback_issues = _language_fallback_issues()
    opt_out_ignored_issues = _opt_out_ignored_issues()
    high_risk_alert_source_issues = _high_risk_alert_source_reference_issues()
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
    ]
    overall_status = "fail" if any(check["status"] == "fail" for check in checks) else "pass"
    return {
        "schema_version": MESSAGE_GOVERNANCE_SCHEMA_VERSION,
        "overall_status": overall_status,
        "inventory": inventory,
        "template_count": MessageTemplate.objects.count(),
        "audit_checks": checks,
    }
