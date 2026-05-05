# Generated manually for child plan 11 audit hardening on 2026-05-05

from django.db import migrations


MESSAGE_AUDIENCE_GOVERNANCE_SCHEMA_VERSION = "message-audience-governance-phase-2-v1"
DEFAULT_LANGUAGE = "en"


def _canonical_alert_audience(record):
    if record.channel == "DASHBOARD":
        return "county_operator"
    return "chv"


def _legacy_decision(*, audience_type, channel):
    return {
        "schema_version": MESSAGE_AUDIENCE_GOVERNANCE_SCHEMA_VERSION,
        "audience_type": audience_type,
        "channel": channel,
        "allowed": True,
        "decision": "legacy_delivery_metadata_backfilled",
        "reason": "record_created_before_phase_2_audience_governance_metadata",
        "message_purpose": "legacy_operational_delivery",
        "legacy_backfilled": True,
    }


def _template_metadata(record, MessageTemplate):
    template = None
    template_id = getattr(record, "template_id", None)
    if template_id:
        template = MessageTemplate.objects.filter(id=template_id).first()
    if template is None and getattr(record, "template_key", "") and getattr(record, "template_version", None):
        template = (
            MessageTemplate.objects.filter(
                template_key=record.template_key,
                version=record.template_version,
                language=getattr(record, "resolved_language", DEFAULT_LANGUAGE),
            )
            .order_by("-created_at")
            .first()
        )
    if template is None and getattr(record, "template_key", "") and getattr(record, "template_version", None):
        template = (
            MessageTemplate.objects.filter(
                template_key=record.template_key,
                version=record.template_version,
            )
            .order_by("language", "-created_at")
            .first()
        )
    if template is None:
        if getattr(record, "template_key", ""):
            return {
                "template_key": record.template_key,
                "template_version": getattr(record, "template_version", None),
                "requested_language": getattr(record, "requested_language", DEFAULT_LANGUAGE),
                "resolved_language": getattr(record, "resolved_language", DEFAULT_LANGUAGE),
                "fallback_used": bool(getattr(record, "fallback_used", False)),
            }
        return {}

    return {
        "template_key": template.template_key,
        "template_version": template.version,
        "template_public_id": str(template.public_id),
        "language": template.language,
        "requested_language": getattr(record, "requested_language", template.language or DEFAULT_LANGUAGE),
        "resolved_language": getattr(record, "resolved_language", template.language or DEFAULT_LANGUAGE),
        "fallback_used": bool(getattr(record, "fallback_used", False)),
    }


def _language_metadata(record):
    return {
        "requested_language": getattr(record, "requested_language", DEFAULT_LANGUAGE),
        "resolved_language": getattr(record, "resolved_language", DEFAULT_LANGUAGE),
        "fallback_used": bool(getattr(record, "fallback_used", False)),
        "template_language": getattr(record, "resolved_language", DEFAULT_LANGUAGE),
    }


def _metadata_missing(record):
    metadata = getattr(record, "governance_metadata", None)
    return not isinstance(metadata, dict) or not metadata


def backfill_legacy_delivery_governance_metadata(apps, schema_editor):
    Alert = apps.get_model("risk", "Alert")
    CHVMessage = apps.get_model("risk", "CHVMessage")
    FacilityReadinessUpdateRequest = apps.get_model("risk", "FacilityReadinessUpdateRequest")
    MessageTemplate = apps.get_model("risk", "MessageTemplate")

    for alert in Alert.objects.all().iterator():
        if not _metadata_missing(alert):
            continue
        alert.governance_metadata = {
            "schema_version": MESSAGE_AUDIENCE_GOVERNANCE_SCHEMA_VERSION,
            "workflow": "legacy_alert_backfill",
            "template": _template_metadata(alert, MessageTemplate),
            "language": _language_metadata(alert),
            "audience_decision": _legacy_decision(
                audience_type=_canonical_alert_audience(alert),
                channel=alert.channel,
            ),
            "audience_scope": {
                "scope_kind": "legacy_delivery_record",
                "scope_allowed": True,
                "target_ward_id": alert.ward_id,
            },
            "legacy_backfilled": True,
        }
        alert.save(update_fields=["governance_metadata"])

    for message in CHVMessage.objects.all().iterator():
        if not _metadata_missing(message):
            continue
        message.governance_metadata = {
            "schema_version": MESSAGE_AUDIENCE_GOVERNANCE_SCHEMA_VERSION,
            "workflow": "legacy_chv_message_backfill",
            "template": _template_metadata(message, MessageTemplate),
            "language": _language_metadata(message),
            "audience_decision": _legacy_decision(
                audience_type="chv",
                channel=message.channel,
            ),
            "audience_scope": {
                "scope_kind": "legacy_delivery_record",
                "scope_allowed": True,
                "target_ward_id": message.ward_id,
            },
            "legacy_backfilled": True,
        }
        message.save(update_fields=["governance_metadata"])

    for request in FacilityReadinessUpdateRequest.objects.all().iterator():
        if not _metadata_missing(request):
            continue
        request.governance_metadata = {
            "schema_version": MESSAGE_AUDIENCE_GOVERNANCE_SCHEMA_VERSION,
            "workflow": "legacy_facility_update_request_backfill",
            "template": _template_metadata(request, MessageTemplate),
            "language": _language_metadata(request),
            "audience_decision": _legacy_decision(
                audience_type="facility_contact",
                channel=request.channel,
            ),
            "audience_scope": {
                "scope_kind": "legacy_delivery_record",
                "scope_allowed": True,
                "facility_id": request.facility_id,
            },
            "legacy_backfilled": True,
        }
        request.save(update_fields=["governance_metadata"])


class Migration(migrations.Migration):

    dependencies = [
        ("risk", "0069_chv_offline_guidance_templates"),
    ]

    operations = [
        migrations.RunPython(backfill_legacy_delivery_governance_metadata, migrations.RunPython.noop),
    ]
