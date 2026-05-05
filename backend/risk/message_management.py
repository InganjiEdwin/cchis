from __future__ import annotations

from collections import Counter
from string import Formatter
from typing import Any, Iterable

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Max, Q
from django.utils import timezone

from risk.chv_localization import DEFAULT_CHV_LANGUAGE, SUPPORTED_CHV_LANGUAGES
from risk.message_governance import build_message_governance_audit
from risk.models import (
    Alert,
    CHVMessage,
    ContactPreference,
    ContactPreferenceAuditEvent,
    FacilityReadinessUpdateRequest,
    MessageTemplate,
    UssdMenuVersion,
    UssdSessionLog,
)
from risk.ussd_governance import USSD_MENU_GOVERNANCE_SCHEMA_VERSION, validate_ussd_menu_tree


MESSAGE_MANAGEMENT_SCHEMA_VERSION = "message-management-phase-7-v1"
SUPPORTED_LOCALIZATION_LANGUAGES = tuple(SUPPORTED_CHV_LANGUAGES)
LANGUAGE_LABELS = {
    "en": "English",
    "sw": "Kiswahili",
    "luo": "Dholuo",
}
OFFLINE_DECISION_SUPPORT_RECOMMENDATION_TEMPLATE_KEYS = {
    "cholera.chv.triage.urgent_referral_offline",
    "cholera.chv.triage.facility_assessment_offline",
    "cholera.chv.triage.ors_and_prevention_offline",
    "cholera.chv.triage.record_symptoms_offline",
}


def _language_label(language: str) -> str:
    return LANGUAGE_LABELS.get(language, language.upper())


def _percent(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100, 6)


def _normalize_channel(channel: str) -> str:
    return (channel or "").strip().lower()


def _normalize_audience_type(audience_type: str) -> str:
    raw = (audience_type or "").strip()
    aliases = {
        ContactPreference.AUDIENCE_CHV: MessageTemplate.AUDIENCE_CHV,
        ContactPreference.AUDIENCE_HOUSEHOLD: MessageTemplate.AUDIENCE_HOUSEHOLD,
        ContactPreference.AUDIENCE_FACILITY_CONTACT: MessageTemplate.AUDIENCE_FACILITY_CONTACT,
        ContactPreference.AUDIENCE_OPERATOR: MessageTemplate.AUDIENCE_COUNTY_OPERATOR,
    }
    return aliases.get(raw, aliases.get(raw.upper(), raw.lower()))


def _placeholder_sample_value(name: str) -> str:
    samples = {
        "ward_name": "Kanyasa",
        "predicted_cases": "12",
        "risk_level": "high",
        "facility_name": "Kakrao Dispensary",
        "chv_name": "Amina Otieno",
        "county": "Migori",
        "sub_county": "Suna East",
    }
    return samples.get(name, f"sample_{name}")


def _preview_context(placeholders: Iterable[str]) -> dict[str, str]:
    return {placeholder: _placeholder_sample_value(placeholder) for placeholder in placeholders}


def _render_preview_body(template: MessageTemplate) -> dict[str, Any]:
    placeholders = [str(placeholder) for placeholder in template.placeholders or []]
    context = _preview_context(placeholders)
    try:
        rendered_body = template.body.format(**context)
        render_error = ""
    except (KeyError, ValueError) as exc:
        rendered_body = template.body
        render_error = str(exc)

    discovered_placeholders = sorted(
        {
            field_name
            for _, field_name, _, _ in Formatter().parse(template.body or "")
            if field_name
        }
    )
    return {
        "context": context,
        "rendered_body": rendered_body,
        "declared_placeholders": placeholders,
        "discovered_placeholders": discovered_placeholders,
        "render_error": render_error,
    }


def _requires_translation(template: MessageTemplate) -> bool:
    return (
        template.audience_type in {MessageTemplate.AUDIENCE_CHV, MessageTemplate.AUDIENCE_HOUSEHOLD}
        or template.channel in {MessageTemplate.CHANNEL_USSD, MessageTemplate.CHANNEL_OFFLINE_CHV_BUNDLE}
        or template.risk_level in {MessageTemplate.RISK_HIGH, MessageTemplate.RISK_CRITICAL}
    )


def _is_template_usable_for_language(template: MessageTemplate) -> bool:
    if template.approval_status != MessageTemplate.APPROVAL_APPROVED or template.retired_at is not None:
        return False
    if template.language == DEFAULT_CHV_LANGUAGE:
        return True
    return (
        template.translation_status == MessageTemplate.TRANSLATION_APPROVED
        and template.source_template_id is not None
        and template.translation_reviewed_at is not None
    )


def _message_template_source_for_variant(
    variant: MessageTemplate,
    variants_by_language: dict[str, MessageTemplate] | None = None,
) -> MessageTemplate | None:
    if variant.language == DEFAULT_CHV_LANGUAGE:
        return variant
    if variant.source_template is not None:
        return variant.source_template
    if variants_by_language and DEFAULT_CHV_LANGUAGE in variants_by_language:
        return variants_by_language[DEFAULT_CHV_LANGUAGE]
    return MessageTemplate.objects.filter(
        template_key=variant.template_key,
        version=variant.version,
        language=DEFAULT_CHV_LANGUAGE,
    ).first()


def _placeholder_parity_warnings(source: MessageTemplate | None, variant: MessageTemplate) -> list[str]:
    if variant.language == DEFAULT_CHV_LANGUAGE:
        return []
    if source is None:
        return ["Missing English source linkage for this translated variant."]

    warnings: list[str] = []
    source_declared = sorted(str(placeholder) for placeholder in source.placeholders or [])
    variant_declared = sorted(str(placeholder) for placeholder in variant.placeholders or [])
    if source_declared != variant_declared:
        warnings.append(
            "Declared placeholders differ from English source "
            f"(source: {source_declared or ['none']}; variant: {variant_declared or ['none']})."
        )

    source_discovered = _render_preview_body(source)["discovered_placeholders"]
    variant_discovered = _render_preview_body(variant)["discovered_placeholders"]
    if source_discovered != variant_discovered:
        warnings.append(
            "Body placeholders differ from English source "
            f"(source: {source_discovered or ['none']}; variant: {variant_discovered or ['none']})."
        )

    if source.approval_status != MessageTemplate.APPROVAL_APPROVED or source.retired_at is not None:
        warnings.append("English source is not active and approved.")
    if variant.source_template_id and variant.source_template_id != source.id:
        warnings.append("Variant is linked to a different English source than the selected version.")
    return warnings


def _placeholder_parity_status(source: MessageTemplate | None, variant: MessageTemplate) -> str:
    if variant.language == DEFAULT_CHV_LANGUAGE:
        return "source"
    return "warning" if _placeholder_parity_warnings(source, variant) else "pass"


def _audience_preview(template: MessageTemplate) -> dict[str, Any]:
    household_sms = (
        template.audience_type == MessageTemplate.AUDIENCE_HOUSEHOLD
        and template.channel == MessageTemplate.CHANNEL_SMS
    )
    emergency_allowed = household_sms and template.risk_level in {
        MessageTemplate.RISK_HIGH,
        MessageTemplate.RISK_CRITICAL,
    }
    if template.audience_type == MessageTemplate.AUDIENCE_CHV:
        scope = "assigned_chv_operational_scope"
        consent_requirement = "operational_contact_scope"
    elif template.audience_type == MessageTemplate.AUDIENCE_FACILITY_CONTACT:
        scope = "verified_facility_contact_scope"
        consent_requirement = "verified_facility_contact"
    elif template.audience_type == MessageTemplate.AUDIENCE_HOUSEHOLD:
        scope = "household_prevention_scope"
        consent_requirement = "consent_or_approved_lawful_basis"
    else:
        scope = "authorized_dashboard_operator_scope"
        consent_requirement = "role_authorized_operator"

    return {
        "audience_type": template.audience_type,
        "channel": template.channel,
        "risk_level": template.risk_level,
        "scope": scope,
        "consent_requirement": consent_requirement,
        "emergency_override_allowed": emergency_allowed,
        "public_health_caveats": template.public_health_caveats,
    }


def _template_usage_summary(template: MessageTemplate) -> dict[str, int]:
    template_match = Q(template=template) | Q(template_key=template.template_key, template_version=template.version)
    alert_count = Alert.objects.filter(template_match).count()
    chv_message_count = CHVMessage.objects.filter(template_match).count()
    facility_update_request_count = FacilityReadinessUpdateRequest.objects.filter(template_match).count()
    return {
        "alert_count": alert_count,
        "chv_message_count": chv_message_count,
        "facility_update_request_count": facility_update_request_count,
        "total_delivery_count": alert_count + chv_message_count + facility_update_request_count,
    }


def build_message_template_record(template: MessageTemplate) -> dict[str, Any]:
    return {
        "public_id": str(template.public_id),
        "template_key": template.template_key,
        "audience_type": template.audience_type,
        "channel": template.channel,
        "language": template.language,
        "version": template.version,
        "title": template.title,
        "body": template.body,
        "placeholders": template.placeholders or [],
        "approval_status": template.approval_status,
        "approved_by": template.approved_by_id,
        "approved_by_username": template.approved_by.username if template.approved_by else "",
        "approved_at": template.approved_at,
        "retired_at": template.retired_at,
        "translation_status": template.translation_status,
        "source_template": str(template.source_template.public_id) if template.source_template else "",
        "source_template_key": template.source_template.template_key if template.source_template else "",
        "source_template_version": template.source_template.version if template.source_template else None,
        "translation_reviewed_by": template.translation_reviewed_by_id,
        "translation_reviewed_by_username": template.translation_reviewed_by.username if template.translation_reviewed_by else "",
        "translation_reviewed_at": template.translation_reviewed_at,
        "translation_review_notes": template.translation_review_notes,
        "owner": template.owner,
        "risk_level": template.risk_level,
        "public_health_caveats": template.public_health_caveats,
        "lineage_metadata": template.lineage_metadata or {},
        "created_by": template.created_by_id,
        "created_by_username": template.created_by.username if template.created_by else "",
        "created_at": template.created_at,
        "updated_at": template.updated_at,
        "preview": _render_preview_body(template),
        "audience_preview": _audience_preview(template),
        "usage_summary": _template_usage_summary(template),
    }


def _language_variant_summary(
    *,
    language: str,
    variant: MessageTemplate | None,
    source: MessageTemplate | None,
) -> dict[str, Any]:
    if variant is None:
        return {
            "language": language,
            "label": _language_label(language),
            "exists": False,
            "public_id": "",
            "title": "",
            "approval_status": "",
            "translation_status": "",
            "placeholder_parity_status": "missing",
            "warnings": [f"Missing {_language_label(language)} variant."],
        }

    warnings = _placeholder_parity_warnings(source, variant)
    return {
        "language": language,
        "label": _language_label(language),
        "exists": True,
        "public_id": str(variant.public_id),
        "title": variant.title,
        "approval_status": variant.approval_status,
        "translation_status": variant.translation_status,
        "placeholder_parity_status": "warning" if warnings else ("source" if language == DEFAULT_CHV_LANGUAGE else "pass"),
        "warnings": warnings,
    }


def _build_template_language_preview(template_key: str, version: int) -> list[dict[str, Any]]:
    variants = list(
        MessageTemplate.objects.select_related(
            "approved_by",
            "source_template",
            "translation_reviewed_by",
        )
        .filter(template_key=template_key, version=version)
        .order_by("language")
    )
    variants_by_language = {variant.language: variant for variant in variants}
    source = variants_by_language.get(DEFAULT_CHV_LANGUAGE)
    if source is None:
        source = next((variant.source_template for variant in variants if variant.source_template_id), None)

    preview_rows: list[dict[str, Any]] = []
    for language in SUPPORTED_LOCALIZATION_LANGUAGES:
        variant = variants_by_language.get(language)
        if variant is None:
            fallback_preview = _render_preview_body(source) if source is not None else {}
            preview_rows.append(
                {
                    "language": language,
                    "label": _language_label(language),
                    "exists": False,
                    "public_id": "",
                    "title": "",
                    "approval_status": "",
                    "translation_status": "",
                    "source_template": str(source.public_id) if source else "",
                    "source_template_key": source.template_key if source else "",
                    "source_template_version": source.version if source else None,
                    "body": "",
                    "rendered_body": "",
                    "delivery_rendered_body": fallback_preview.get("rendered_body", ""),
                    "requested_language": language,
                    "resolved_language": source.language if source else "",
                    "fallback_used": bool(source),
                    "placeholders": [],
                    "placeholder_parity_status": "missing",
                    "placeholder_warnings": [f"Missing {_language_label(language)} variant; English fallback would be used."],
                    "render_error": "",
                }
            )
            continue

        variant_source = _message_template_source_for_variant(variant, variants_by_language)
        preview = _render_preview_body(variant)
        usable = _is_template_usable_for_language(variant)
        delivery_template = variant if usable else variant_source
        delivery_preview = _render_preview_body(delivery_template) if delivery_template is not None else preview
        warnings = _placeholder_parity_warnings(variant_source, variant)
        if language != DEFAULT_CHV_LANGUAGE and not usable:
            warnings.append("Variant is not approved for use; English fallback would be shown to users.")

        preview_rows.append(
            {
                "language": language,
                "label": _language_label(language),
                "exists": True,
                "public_id": str(variant.public_id),
                "title": variant.title,
                "approval_status": variant.approval_status,
                "translation_status": variant.translation_status,
                "source_template": str(variant_source.public_id) if variant_source else "",
                "source_template_key": variant_source.template_key if variant_source else "",
                "source_template_version": variant_source.version if variant_source else None,
                "body": variant.body,
                "rendered_body": preview["rendered_body"],
                "delivery_rendered_body": delivery_preview["rendered_body"],
                "requested_language": language,
                "resolved_language": delivery_template.language if delivery_template else language,
                "fallback_used": delivery_template is not None and delivery_template.id != variant.id,
                "placeholders": preview["declared_placeholders"],
                "placeholder_parity_status": "warning"
                if warnings
                else ("source" if language == DEFAULT_CHV_LANGUAGE else "pass"),
                "placeholder_warnings": warnings,
                "render_error": preview["render_error"],
            }
        )
    return preview_rows


def _apply_window(queryset, field_name: str, *, date_from=None, date_to=None):
    if date_from is not None:
        queryset = queryset.filter(**{f"{field_name}__gte": date_from})
    if date_to is not None:
        queryset = queryset.filter(**{f"{field_name}__lte": date_to})
    return queryset


def _apply_template_filter(queryset, template: MessageTemplate | None):
    if template is None:
        return queryset
    return queryset.filter(Q(template=template) | Q(template_key=template.template_key, template_version=template.version))


def build_opt_out_monitoring_summary(*, date_from=None, date_to=None) -> dict[str, Any]:
    now = timezone.now()
    active_opt_outs = ContactPreference.objects.filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=now),
        opt_out_status=ContactPreference.OPT_OUT_OPTED_OUT,
    )
    blocked_events = _apply_window(
        ContactPreferenceAuditEvent.objects.filter(action=ContactPreferenceAuditEvent.ACTION_BLOCKED_OPT_OUT),
        "created_at",
        date_from=date_from,
        date_to=date_to,
    )

    by_audience_channel: dict[tuple[str, str], dict[str, Any]] = {}
    for row in active_opt_outs.values("audience_type", "channel").annotate(
        current_opt_out_count=Count("id"),
        latest_opt_out_at=Max("recorded_at"),
    ):
        audience_type = _normalize_audience_type(row["audience_type"])
        channel = _normalize_channel(row["channel"])
        by_audience_channel[(audience_type, channel)] = {
            "audience_type": audience_type,
            "channel": channel,
            "current_opt_out_count": row["current_opt_out_count"],
            "blocked_opt_out_event_count": 0,
            "latest_opt_out_at": row["latest_opt_out_at"],
            "latest_blocked_at": None,
        }

    for row in blocked_events.values("audience_type", "channel").annotate(
        blocked_opt_out_event_count=Count("id"),
        latest_blocked_at=Max("created_at"),
    ):
        audience_type = _normalize_audience_type(row["audience_type"])
        channel = _normalize_channel(row["channel"])
        bucket = by_audience_channel.setdefault(
            (audience_type, channel),
            {
                "audience_type": audience_type,
                "channel": channel,
                "current_opt_out_count": 0,
                "blocked_opt_out_event_count": 0,
                "latest_opt_out_at": None,
                "latest_blocked_at": None,
            },
        )
        bucket["blocked_opt_out_event_count"] += row["blocked_opt_out_event_count"]
        bucket["latest_blocked_at"] = row["latest_blocked_at"]

    records = sorted(by_audience_channel.values(), key=lambda item: (item["audience_type"], item["channel"]))
    return {
        "total_current_opt_out_count": sum(row["current_opt_out_count"] for row in records),
        "total_blocked_opt_out_event_count": sum(row["blocked_opt_out_event_count"] for row in records),
        "by_audience_channel": records,
    }


def build_delivery_outcome_summary(
    *,
    date_from=None,
    date_to=None,
    template: MessageTemplate | None = None,
) -> dict[str, Any]:
    sources = [
        {
            "model": "risk.Alert",
            "audience_type": MessageTemplate.AUDIENCE_CHV,
            "recipient_field": "recipient",
            "queryset": _apply_template_filter(
                _apply_window(Alert.objects.all(), "created_at", date_from=date_from, date_to=date_to),
                template,
            ),
            "date_field": "created_at",
        },
        {
            "model": "risk.CHVMessage",
            "audience_type": MessageTemplate.AUDIENCE_CHV,
            "recipient_field": "chv_id",
            "queryset": _apply_template_filter(
                _apply_window(CHVMessage.objects.all(), "created_at", date_from=date_from, date_to=date_to),
                template,
            ),
            "date_field": "created_at",
        },
        {
            "model": "risk.FacilityReadinessUpdateRequest",
            "audience_type": MessageTemplate.AUDIENCE_FACILITY_CONTACT,
            "recipient_field": "contact_id",
            "queryset": _apply_template_filter(
                _apply_window(
                    FacilityReadinessUpdateRequest.objects.all(),
                    "created_at",
                    date_from=date_from,
                    date_to=date_to,
                ),
                template,
            ),
            "date_field": "created_at",
        },
    ]

    by_audience_channel_status: dict[tuple[str, str, str], dict[str, Any]] = {}
    reach_by_audience_channel: dict[tuple[str, str], dict[str, Any]] = {}
    by_template: dict[tuple[str, int | None], dict[str, Any]] = {}
    by_language: dict[tuple[str, str, str, bool], dict[str, Any]] = {}
    recent_records: list[dict[str, Any]] = []
    total_count = 0
    successful_count = 0
    failed_count = 0

    success_statuses = {"DELIVERED", "SENT", "ACKNOWLEDGED"}
    failure_statuses = {"FAILED", "CANCELLED"}
    for source in sources:
        queryset = source["queryset"]
        audience_type = source["audience_type"]
        model_label = source["model"]
        date_field = source["date_field"]
        recipient_field = source["recipient_field"]
        for row in queryset.values("channel", "status", "template_key", "template_version").annotate(
            count=Count("id"),
            latest_at=Max(date_field),
        ):
            channel = _normalize_channel(row["channel"])
            status = row["status"] or "UNKNOWN"
            count = row["count"]
            total_count += count
            if status in success_statuses:
                successful_count += count
            if status in failure_statuses:
                failed_count += count

            audience_key = (audience_type, channel, status)
            audience_bucket = by_audience_channel_status.setdefault(
                audience_key,
                {
                    "audience_type": audience_type,
                    "channel": channel,
                    "status": status,
                    "count": 0,
                    "latest_at": row["latest_at"],
                },
            )
            audience_bucket["count"] += count
            if row["latest_at"] and (audience_bucket["latest_at"] is None or row["latest_at"] > audience_bucket["latest_at"]):
                audience_bucket["latest_at"] = row["latest_at"]

            template_key = row["template_key"] or "unlinked"
            template_version = row["template_version"]
            template_bucket = by_template.setdefault(
                (template_key, template_version),
                {
                    "template_key": template_key,
                    "template_version": template_version,
                    "count": 0,
                    "statuses": {},
                    "latest_at": row["latest_at"],
                },
            )
            template_bucket["count"] += count
            template_bucket["statuses"][status] = template_bucket["statuses"].get(status, 0) + count
            if row["latest_at"] and (template_bucket["latest_at"] is None or row["latest_at"] > template_bucket["latest_at"]):
                template_bucket["latest_at"] = row["latest_at"]

        if hasattr(queryset.model, "resolved_language"):
            for row in queryset.values("resolved_language", "fallback_used", "status").annotate(
                count=Count("id"),
                latest_at=Max(date_field),
            ):
                language = row["resolved_language"] or "unknown"
                status = row["status"] or "UNKNOWN"
                fallback_used = bool(row["fallback_used"])
                language_key = (model_label, language, status, fallback_used)
                language_bucket = by_language.setdefault(
                    language_key,
                    {
                        "model": model_label,
                        "audience_type": audience_type,
                        "resolved_language": language,
                        "fallback_used": fallback_used,
                        "status": status,
                        "count": 0,
                        "latest_at": row["latest_at"],
                    },
                )
                language_bucket["count"] += row["count"]
                if row["latest_at"] and (
                    language_bucket["latest_at"] is None or row["latest_at"] > language_bucket["latest_at"]
                ):
                    language_bucket["latest_at"] = row["latest_at"]

        for row in queryset.values("channel").annotate(
            message_count=Count("id"),
            unique_recipient_count=Count(recipient_field, distinct=True),
            successful_count=Count("id", filter=Q(status__in=success_statuses)),
            failed_count=Count("id", filter=Q(status__in=failure_statuses)),
            latest_at=Max(date_field),
        ):
            channel = _normalize_channel(row["channel"])
            reach_key = (audience_type, channel)
            reach_bucket = reach_by_audience_channel.setdefault(
                reach_key,
                {
                    "audience_type": audience_type,
                    "channel": channel,
                    "message_count": 0,
                    "unique_recipient_count": 0,
                    "successful_count": 0,
                    "failed_count": 0,
                    "success_rate_pct": 0.0,
                    "latest_at": row["latest_at"],
                },
            )
            reach_bucket["message_count"] += row["message_count"]
            reach_bucket["unique_recipient_count"] += row["unique_recipient_count"]
            reach_bucket["successful_count"] += row["successful_count"]
            reach_bucket["failed_count"] += row["failed_count"]
            if row["latest_at"] and (reach_bucket["latest_at"] is None or row["latest_at"] > reach_bucket["latest_at"]):
                reach_bucket["latest_at"] = row["latest_at"]

        for record in queryset.order_by(f"-{date_field}")[:15]:
            recent_records.append(
                {
                    "model": model_label,
                    "public_id": str(record.public_id),
                    "audience_type": audience_type,
                    "channel": _normalize_channel(record.channel),
                    "template_key": record.template_key,
                    "template_version": record.template_version,
                    "requested_language": getattr(record, "requested_language", ""),
                    "resolved_language": getattr(record, "resolved_language", ""),
                    "fallback_used": bool(getattr(record, "fallback_used", False)),
                    "status": record.status,
                    "created_at": getattr(record, date_field),
                }
            )

    recent_records.sort(key=lambda item: item["created_at"], reverse=True)
    reach_records = sorted(
        reach_by_audience_channel.values(),
        key=lambda item: (item["audience_type"], item["channel"]),
    )
    for reach_record in reach_records:
        reach_record["success_rate_pct"] = _percent(reach_record["successful_count"], reach_record["message_count"])
    template_usage_by_version = sorted(
        by_template.values(),
        key=lambda item: (item["template_key"], item["template_version"] or 0),
    )
    return {
        "total_count": total_count,
        "successful_count": successful_count,
        "failed_count": failed_count,
        "success_rate_pct": _percent(successful_count, total_count),
        "by_audience_channel_status": sorted(
            by_audience_channel_status.values(),
            key=lambda item: (item["audience_type"], item["channel"], item["status"]),
        ),
        "by_template": sorted(
            by_template.values(),
            key=lambda item: (item["template_key"], item["template_version"] or 0),
        ),
        "by_language": sorted(
            by_language.values(),
            key=lambda item: (item["model"], item["resolved_language"], item["status"], item["fallback_used"]),
        ),
        "template_usage_by_version": template_usage_by_version,
        "reach_by_audience_channel": reach_records,
        "opt_out_summary": build_opt_out_monitoring_summary(date_from=date_from, date_to=date_to),
        "recent_records": recent_records[:20],
    }


def _build_template_language_coverage_matrix() -> dict[str, Any]:
    templates = list(
        MessageTemplate.objects.select_related(
            "approved_by",
            "source_template",
            "translation_reviewed_by",
        ).order_by("template_key", "version", "language")
    )
    grouped_templates: dict[tuple[str, int], list[MessageTemplate]] = {}
    for template in templates:
        grouped_templates.setdefault((template.template_key, template.version), []).append(template)

    rows: list[dict[str, Any]] = []
    missing_variant_count = 0
    placeholder_warning_count = 0
    translation_review_warning_count = 0

    for (template_key, version), variants in sorted(grouped_templates.items()):
        variants_by_language = {variant.language: variant for variant in variants}
        source = variants_by_language.get(DEFAULT_CHV_LANGUAGE)
        if source is None:
            source = next((variant.source_template for variant in variants if variant.source_template_id), None)
        representative = source or variants[0]
        requires_translation = any(_requires_translation(variant) for variant in variants)
        missing_languages: list[str] = []
        placeholder_warnings: list[dict[str, str]] = []
        translation_review_warnings: list[dict[str, str]] = []
        variant_summaries: list[dict[str, Any]] = []

        for language in SUPPORTED_LOCALIZATION_LANGUAGES:
            variant = variants_by_language.get(language)
            variant_summaries.append(_language_variant_summary(language=language, variant=variant, source=source))
            if variant is None:
                if requires_translation:
                    missing_languages.append(language)
                continue

            warnings = _placeholder_parity_warnings(source, variant)
            placeholder_warnings.extend(
                {
                    "language": language,
                    "label": _language_label(language),
                    "message": warning,
                }
                for warning in warnings
            )

            if language != DEFAULT_CHV_LANGUAGE and variant.approval_status == MessageTemplate.APPROVAL_APPROVED:
                if variant.translation_status != MessageTemplate.TRANSLATION_APPROVED:
                    translation_review_warnings.append(
                        {
                            "language": language,
                            "label": _language_label(language),
                            "message": "Approved variant does not have approved translation status.",
                        }
                    )
                if variant.translation_reviewed_at is None:
                    translation_review_warnings.append(
                        {
                            "language": language,
                            "label": _language_label(language),
                            "message": "Approved variant is missing translation review metadata.",
                        }
                    )

        missing_variant_count += len(missing_languages)
        placeholder_warning_count += len(placeholder_warnings)
        translation_review_warning_count += len(translation_review_warnings)
        rows.append(
            {
                "template_key": template_key,
                "version": version,
                "title": representative.title,
                "audience_type": representative.audience_type,
                "channel": representative.channel,
                "risk_level": representative.risk_level,
                "owner": representative.owner,
                "requires_translation": requires_translation,
                "present_languages": sorted(variants_by_language),
                "missing_languages": missing_languages,
                "missing_language_labels": [_language_label(language) for language in missing_languages],
                "variants": variant_summaries,
                "placeholder_warnings": placeholder_warnings,
                "translation_review_warnings": translation_review_warnings,
            }
        )

    return {
        "supported_languages": [
            {"code": language, "label": _language_label(language)}
            for language in SUPPORTED_LOCALIZATION_LANGUAGES
        ],
        "row_count": len(rows),
        "missing_variant_count": missing_variant_count,
        "placeholder_warning_count": placeholder_warning_count,
        "translation_review_warning_count": translation_review_warning_count,
        "rows": rows,
    }


def _build_missing_translation_dashboard(
    coverage_matrix: dict[str, Any],
    *,
    ussd_route_tree_preview: list[dict[str, Any]] | None = None,
    offline_guidance_preview: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for row in coverage_matrix["rows"]:
        for language in row["missing_languages"]:
            items.append(
                {
                    "issue_type": "missing_variant",
                    "severity": "high" if row["risk_level"] in {MessageTemplate.RISK_HIGH, MessageTemplate.RISK_CRITICAL} else "medium",
                    "template_key": row["template_key"],
                    "version": row["version"],
                    "version_label": f"v{row['version']}",
                    "title": row["title"],
                    "audience_type": row["audience_type"],
                    "channel": row["channel"],
                    "language": language,
                    "label": _language_label(language),
                    "message": f"Missing {_language_label(language)} variant before rollout.",
                }
            )
        for warning in row["placeholder_warnings"]:
            items.append(
                {
                    "issue_type": "placeholder_parity",
                    "severity": "high",
                    "template_key": row["template_key"],
                    "version": row["version"],
                    "version_label": f"v{row['version']}",
                    "title": row["title"],
                    "audience_type": row["audience_type"],
                    "channel": row["channel"],
                    "language": warning["language"],
                    "label": warning["label"],
                    "message": warning["message"],
                }
            )
        for warning in row["translation_review_warnings"]:
            items.append(
                {
                    "issue_type": "translation_review",
                    "severity": "medium",
                    "template_key": row["template_key"],
                    "version": row["version"],
                    "version_label": f"v{row['version']}",
                    "title": row["title"],
                    "audience_type": row["audience_type"],
                    "channel": row["channel"],
                    "language": warning["language"],
                    "label": warning["label"],
                    "message": warning["message"],
                }
            )

    for route_preview in ussd_route_tree_preview or []:
        for language_preview in route_preview["languages"]:
            if not language_preview["exists"]:
                items.append(
                    {
                        "issue_type": "missing_ussd_menu",
                        "severity": "high",
                        "template_key": route_preview["menu_key"],
                        "version": 0,
                        "version_label": route_preview["source_version_label"],
                        "title": route_preview["source_title"] or route_preview["menu_key"],
                        "audience_type": MessageTemplate.AUDIENCE_CHV,
                        "channel": MessageTemplate.CHANNEL_USSD,
                        "language": language_preview["language"],
                        "label": language_preview["label"],
                        "message": language_preview["warnings"][0]
                        if language_preview["warnings"]
                        else f"Missing active {language_preview['label']} USSD menu before rollout.",
                    }
                )
            for warning in language_preview["warnings"]:
                if not language_preview["exists"]:
                    continue
                items.append(
                    {
                        "issue_type": "ussd_route_parity",
                        "severity": "high",
                        "template_key": route_preview["menu_key"],
                        "version": 0,
                        "version_label": route_preview["source_version_label"],
                        "title": route_preview["source_title"] or route_preview["menu_key"],
                        "audience_type": MessageTemplate.AUDIENCE_CHV,
                        "channel": MessageTemplate.CHANNEL_USSD,
                        "language": language_preview["language"],
                        "label": language_preview["label"],
                        "message": warning,
                    }
                )

    for guidance_preview in offline_guidance_preview or []:
        for warning in guidance_preview["warnings"]:
            items.append(
                {
                    "issue_type": "offline_guidance_fallback",
                    "severity": "medium",
                    "template_key": "offline_chv_guidance",
                    "version": 0,
                    "version_label": guidance_preview["resolved_language"],
                    "title": "Offline CHV guidance",
                    "audience_type": MessageTemplate.AUDIENCE_CHV,
                    "channel": MessageTemplate.CHANNEL_OFFLINE_CHV_BUNDLE,
                    "language": guidance_preview["language"],
                    "label": guidance_preview["label"],
                    "message": warning,
                }
            )

    issue_counts = Counter(item["issue_type"] for item in items)
    severity_counts = Counter(item["severity"] for item in items)
    return {
        "total_issue_count": len(items),
        "by_issue_type": dict(issue_counts),
        "by_severity": dict(severity_counts),
        "items": items[:100],
    }


def _ussd_route_tree_signature(menu_tree: dict[str, Any]) -> dict[str, list[str]]:
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


def _route_preview_for_menu(menu_version: UssdMenuVersion | None) -> list[dict[str, Any]]:
    if menu_version is None:
        return []
    menu_tree = menu_version.menu_tree or {}
    routes = menu_tree.get("routes") if isinstance(menu_tree, dict) else {}
    nodes = menu_tree.get("nodes") if isinstance(menu_tree, dict) else {}
    if not isinstance(routes, dict) or not isinstance(nodes, dict):
        return []

    route_rows: list[dict[str, Any]] = []
    for route, node_key in sorted(routes.items(), key=lambda item: (len(item[0]), item[0])):
        node = nodes.get(node_key)
        if not isinstance(node, dict):
            continue
        response_type = str(node.get("response_type") or "").upper()
        body = str(node.get("body") or "")
        route_rows.append(
            {
                "route": route,
                "route_label": route or "root",
                "node_key": node_key,
                "response_type": response_type,
                "body": body,
                "response_text": f"{response_type} {body}".strip(),
                "character_count": len(f"{response_type} {body}".strip()),
            }
        )
    return route_rows


def _active_menu_preview_record(
    *,
    language: str,
    menu_version: UssdMenuVersion | None,
    fallback_menu: UssdMenuVersion | None,
    source_signature: dict[str, list[str]],
) -> dict[str, Any]:
    if menu_version is None:
        fallback_routes = _route_preview_for_menu(fallback_menu)
        return {
            "language": language,
            "label": _language_label(language),
            "exists": False,
            "public_id": "",
            "title": "",
            "approval_status": "",
            "translation_status": "",
            "safe_fallback_copy": fallback_menu.safe_fallback_copy if fallback_menu else "",
            "requested_language": language,
            "resolved_language": fallback_menu.language if fallback_menu else "",
            "fallback_used": bool(fallback_menu),
            "route_count": len(fallback_routes),
            "routes": fallback_routes,
            "warnings": [f"Missing active {_language_label(language)} USSD menu; English fallback would be used."],
        }

    warnings: list[str] = []
    if language != DEFAULT_CHV_LANGUAGE and _ussd_route_tree_signature(menu_version.menu_tree or {}) != source_signature:
        warnings.append("Route tree differs from the active English source menu.")
    if language != DEFAULT_CHV_LANGUAGE and menu_version.approval_status == UssdMenuVersion.STATUS_APPROVED:
        if menu_version.translation_status != UssdMenuVersion.TRANSLATION_APPROVED:
            warnings.append("Approved USSD menu does not have approved translation status.")
        if menu_version.translation_reviewed_at is None:
            warnings.append("Approved USSD menu is missing translation review metadata.")

    routes = _route_preview_for_menu(menu_version)
    return {
        "language": language,
        "label": _language_label(language),
        "exists": True,
        "public_id": str(menu_version.public_id),
        "title": menu_version.title,
        "approval_status": menu_version.approval_status,
        "translation_status": menu_version.translation_status,
        "safe_fallback_copy": menu_version.safe_fallback_copy,
        "requested_language": language,
        "resolved_language": menu_version.language,
        "fallback_used": False,
        "route_count": len(routes),
        "routes": routes,
        "warnings": warnings,
    }


def _build_ussd_route_tree_preview() -> list[dict[str, Any]]:
    versions = list(
        UssdMenuVersion.objects.select_related(
            "approved_by",
            "source_menu_version",
            "translation_reviewed_by",
        )
        .filter(
            approval_status=UssdMenuVersion.STATUS_APPROVED,
            retired_at__isnull=True,
            is_active=True,
        )
        .order_by("menu_key", "language", "-created_at")
    )
    grouped_versions: dict[str, dict[str, UssdMenuVersion]] = {}
    for version in versions:
        grouped_versions.setdefault(version.menu_key, {}).setdefault(version.language, version)

    previews: list[dict[str, Any]] = []
    for menu_key, versions_by_language in sorted(grouped_versions.items()):
        source = versions_by_language.get(DEFAULT_CHV_LANGUAGE)
        source_signature = _ussd_route_tree_signature(source.menu_tree if source else {})
        language_previews = [
            _active_menu_preview_record(
                language=language,
                menu_version=versions_by_language.get(language),
                fallback_menu=source,
                source_signature=source_signature,
            )
            for language in SUPPORTED_LOCALIZATION_LANGUAGES
        ]
        previews.append(
            {
                "menu_key": menu_key,
                "source_menu_version": str(source.public_id) if source else "",
                "source_version_label": source.version_label if source else "",
                "source_title": source.title if source else "",
                "languages": language_previews,
            }
        )
    return previews


def _ussd_menu_version_record(menu_version: UssdMenuVersion) -> dict[str, Any]:
    try:
        validate_ussd_menu_tree(menu_version.menu_tree or {})
        validation_status = "pass"
        validation_messages: list[str] = []
    except ValidationError as exc:
        validation_status = "fail"
        validation_messages = exc.messages

    menu_tree = menu_version.menu_tree or {}
    routes = menu_tree.get("routes") if isinstance(menu_tree, dict) else {}
    nodes = menu_tree.get("nodes") if isinstance(menu_tree, dict) else {}
    return {
        "public_id": str(menu_version.public_id),
        "menu_key": menu_version.menu_key,
        "version_label": menu_version.version_label,
        "language": menu_version.language,
        "title": menu_version.title,
        "approval_status": menu_version.approval_status,
        "approved_by": menu_version.approved_by_id,
        "approved_by_username": menu_version.approved_by.username if menu_version.approved_by else "",
        "approved_at": menu_version.approved_at,
        "retired_at": menu_version.retired_at,
        "translation_status": menu_version.translation_status,
        "source_menu_version": str(menu_version.source_menu_version.public_id) if menu_version.source_menu_version else "",
        "source_menu_version_label": menu_version.source_menu_version.version_label if menu_version.source_menu_version else "",
        "translation_reviewed_by": menu_version.translation_reviewed_by_id,
        "translation_reviewed_by_username": (
            menu_version.translation_reviewed_by.username if menu_version.translation_reviewed_by else ""
        ),
        "translation_reviewed_at": menu_version.translation_reviewed_at,
        "translation_review_notes": menu_version.translation_review_notes,
        "is_active": menu_version.is_active,
        "safe_fallback_copy": menu_version.safe_fallback_copy,
        "lineage_metadata": menu_version.lineage_metadata or {},
        "created_by": menu_version.created_by_id,
        "created_by_username": menu_version.created_by.username if menu_version.created_by else "",
        "created_at": menu_version.created_at,
        "updated_at": menu_version.updated_at,
        "route_count": len(routes) if isinstance(routes, dict) else 0,
        "node_count": len(nodes) if isinstance(nodes, dict) else 0,
        "route_tree_preview": _route_preview_for_menu(menu_version),
        "validation_status": validation_status,
        "validation_messages": validation_messages,
    }


def build_ussd_menu_version_record(menu_version: UssdMenuVersion) -> dict[str, Any]:
    return _ussd_menu_version_record(menu_version)


def transition_ussd_menu_version_approval(
    menu_version: UssdMenuVersion,
    *,
    action: str,
    actor,
    reason: str = "",
) -> UssdMenuVersion:
    normalized_action = (action or "approve").strip().lower()
    if normalized_action not in {"approve", "request_review", "reject", "retire"}:
        raise ValidationError({"action": ["Unsupported USSD menu approval action."]})

    now = timezone.now()
    lineage_metadata = dict(menu_version.lineage_metadata or {})
    approval_events = lineage_metadata.get("approval_events")
    if not isinstance(approval_events, list):
        approval_events = []
    approval_events.append(
        {
            "action": normalized_action,
            "actor_id": getattr(actor, "id", None),
            "actor_username": getattr(actor, "username", ""),
            "reason": reason.strip(),
            "previous_status": menu_version.approval_status,
            "created_at": now.isoformat(),
        }
    )
    lineage_metadata["approval_events"] = approval_events[-50:]

    with transaction.atomic():
        if normalized_action == "approve":
            if menu_version.language != DEFAULT_CHV_LANGUAGE and menu_version.source_menu_version_id is None:
                menu_version.source_menu_version = (
                    UssdMenuVersion.objects.filter(
                        menu_key=menu_version.menu_key,
                        language=DEFAULT_CHV_LANGUAGE,
                        approval_status=UssdMenuVersion.STATUS_APPROVED,
                        retired_at__isnull=True,
                        is_active=True,
                    )
                    .order_by("-approved_at", "-created_at", "-id")
                    .first()
                )
            menu_version.approval_status = UssdMenuVersion.STATUS_APPROVED
            menu_version.approved_by = actor
            menu_version.approved_at = now
            menu_version.retired_at = None
            menu_version.translation_status = UssdMenuVersion.TRANSLATION_APPROVED
            menu_version.translation_reviewed_by = actor
            menu_version.translation_reviewed_at = now
            menu_version.translation_review_notes = reason.strip()
            menu_version.is_active = True
            UssdMenuVersion.objects.filter(
                menu_key=menu_version.menu_key,
                language=menu_version.language,
                is_active=True,
            ).exclude(pk=menu_version.pk).update(is_active=False, updated_at=now)
        elif normalized_action == "request_review":
            menu_version.approval_status = UssdMenuVersion.STATUS_DRAFT
            menu_version.approved_by = None
            menu_version.approved_at = None
            menu_version.retired_at = None
            menu_version.is_active = False
            menu_version.translation_status = (
                UssdMenuVersion.TRANSLATION_NEEDS_REVIEW
                if menu_version.language != DEFAULT_CHV_LANGUAGE
                else UssdMenuVersion.TRANSLATION_DRAFT
            )
        elif normalized_action == "reject":
            menu_version.approval_status = UssdMenuVersion.STATUS_DRAFT
            menu_version.approved_by = None
            menu_version.approved_at = None
            menu_version.retired_at = None
            menu_version.is_active = False
            if menu_version.language != DEFAULT_CHV_LANGUAGE:
                menu_version.translation_status = UssdMenuVersion.TRANSLATION_DRAFT
                menu_version.translation_reviewed_by = None
                menu_version.translation_reviewed_at = None
                menu_version.translation_review_notes = reason.strip()
        elif normalized_action == "retire":
            menu_version.approval_status = UssdMenuVersion.STATUS_RETIRED
            menu_version.approved_by = None
            menu_version.approved_at = None
            menu_version.retired_at = now
            menu_version.is_active = False
            menu_version.translation_status = UssdMenuVersion.TRANSLATION_RETIRED

        menu_version.lineage_metadata = lineage_metadata
        menu_version.full_clean()
        menu_version.save()
        if normalized_action == "retire" and menu_version.language == DEFAULT_CHV_LANGUAGE:
            UssdMenuVersion.objects.filter(source_menu_version=menu_version).exclude(
                translation_status__in=[
                    UssdMenuVersion.TRANSLATION_RETIRED,
                    UssdMenuVersion.TRANSLATION_BLOCKED_SOURCE_RETIRED,
                ]
            ).update(
                is_active=False,
                translation_status=UssdMenuVersion.TRANSLATION_BLOCKED_SOURCE_RETIRED,
                updated_at=now,
            )

    return menu_version


def build_ussd_session_analytics(*, date_from=None, date_to=None) -> dict[str, Any]:
    queryset = _apply_window(UssdSessionLog.objects.select_related("menu_version"), "created_at", date_from=date_from, date_to=date_to)
    total_logs = queryset.count()
    total_sessions = queryset.values("session_id").distinct().count()
    completed_sessions = queryset.filter(session_outcome=UssdSessionLog.OUTCOME_COMPLETED).values("session_id").distinct().count()
    invalid_input_sessions = queryset.filter(session_outcome=UssdSessionLog.OUTCOME_INVALID_INPUT).values("session_id").distinct().count()
    abandoned_sessions = queryset.filter(session_outcome=UssdSessionLog.OUTCOME_ABANDONED_INFERRED).values("session_id").distinct().count()
    safe_fallback_sessions = queryset.filter(session_outcome=UssdSessionLog.OUTCOME_SAFE_FALLBACK).values("session_id").distinct().count()

    by_outcome = [
        {
            "session_outcome": row["session_outcome"] or "UNKNOWN",
            "log_count": row["log_count"],
            "session_count": row["session_count"],
            "latest_at": row["latest_at"],
        }
        for row in queryset.values("session_outcome").annotate(
            log_count=Count("id"),
            session_count=Count("session_id", distinct=True),
            latest_at=Max("created_at"),
        ).order_by("session_outcome")
    ]
    by_language = [
        {
            "language": row["language"] or "unknown",
            "log_count": row["log_count"],
            "session_count": row["session_count"],
            "invalid_input_count": row["invalid_input_count"],
            "abandoned_count": row["abandoned_count"],
        }
        for row in queryset.values("language").annotate(
            log_count=Count("id"),
            session_count=Count("session_id", distinct=True),
            invalid_input_count=Count("id", filter=Q(session_outcome=UssdSessionLog.OUTCOME_INVALID_INPUT)),
            abandoned_count=Count("id", filter=Q(session_outcome=UssdSessionLog.OUTCOME_ABANDONED_INFERRED)),
        ).order_by("language")
    ]
    by_menu_version = [
        {
            "menu_key": row["menu_key"] or "unknown",
            "menu_version_label": row["menu_version_label"] or "unknown",
            "language": row["language"] or "unknown",
            "log_count": row["log_count"],
            "session_count": row["session_count"],
            "completed_count": row["completed_count"],
            "invalid_input_count": row["invalid_input_count"],
            "abandoned_count": row["abandoned_count"],
            "latest_at": row["latest_at"],
        }
        for row in queryset.values("menu_key", "menu_version_label", "language").annotate(
            log_count=Count("id"),
            session_count=Count("session_id", distinct=True),
            completed_count=Count("id", filter=Q(session_outcome=UssdSessionLog.OUTCOME_COMPLETED)),
            invalid_input_count=Count("id", filter=Q(session_outcome=UssdSessionLog.OUTCOME_INVALID_INPUT)),
            abandoned_count=Count("id", filter=Q(session_outcome=UssdSessionLog.OUTCOME_ABANDONED_INFERRED)),
            latest_at=Max("created_at"),
        ).order_by("menu_key", "menu_version_label", "language")
    ]
    recent_logs = [
        {
            "id": log.id,
            "session_id": log.session_id,
            "menu_key": log.menu_key,
            "menu_version_label": log.menu_version_label,
            "language": log.language,
            "requested_language": log.requested_language,
            "resolved_language": log.resolved_language,
            "fallback_used": log.fallback_used,
            "menu_level": log.menu_level,
            "session_outcome": log.session_outcome,
            "invalid_option": log.invalid_option,
            "abandonment_reason": log.abandonment_reason,
            "is_terminal": log.is_terminal,
            "created_at": log.created_at,
        }
        for log in queryset.order_by("-created_at", "-id")[:20]
    ]

    return {
        "schema_version": USSD_MENU_GOVERNANCE_SCHEMA_VERSION,
        "total_logs": total_logs,
        "total_sessions": total_sessions,
        "completed_sessions": completed_sessions,
        "invalid_input_sessions": invalid_input_sessions,
        "abandoned_sessions": abandoned_sessions,
        "safe_fallback_sessions": safe_fallback_sessions,
        "completion_rate_pct": _percent(completed_sessions, total_sessions),
        "invalid_input_rate_pct": _percent(invalid_input_sessions, total_sessions),
        "abandonment_rate_pct": _percent(abandoned_sessions, total_sessions),
        "by_outcome": by_outcome,
        "by_language": by_language,
        "by_menu_version": by_menu_version,
        "recent_logs": recent_logs,
    }


def _select_offline_guidance_preview_templates(language: str) -> list[MessageTemplate]:
    queryset = (
        MessageTemplate.objects.select_related("source_template")
        .filter(
            channel=MessageTemplate.CHANNEL_OFFLINE_CHV_BUNDLE,
            approval_status=MessageTemplate.APPROVAL_APPROVED,
            retired_at__isnull=True,
            audience_type__in=[MessageTemplate.AUDIENCE_CHV, MessageTemplate.AUDIENCE_HOUSEHOLD],
        )
        .exclude(template_key__in=OFFLINE_DECISION_SUPPORT_RECOMMENDATION_TEMPLATE_KEYS)
        .filter(
            Q(language=DEFAULT_CHV_LANGUAGE)
            | Q(
                language=language,
                translation_status=MessageTemplate.TRANSLATION_APPROVED,
                source_template__isnull=False,
                source_template__approval_status=MessageTemplate.APPROVAL_APPROVED,
                source_template__retired_at__isnull=True,
            )
        )
        .order_by("template_key", "-version", "language")
    )

    selected_by_key: dict[str, MessageTemplate] = {}
    for template in queryset[:200]:
        existing = selected_by_key.get(template.template_key)
        if existing is None:
            selected_by_key[template.template_key] = template
            continue
        if existing.language != language and template.language == language:
            selected_by_key[template.template_key] = template
    return list(selected_by_key.values())


def _build_offline_guidance_preview() -> list[dict[str, Any]]:
    previews: list[dict[str, Any]] = []
    for language in SUPPORTED_LOCALIZATION_LANGUAGES:
        templates = _select_offline_guidance_preview_templates(language)
        guidance_items: list[dict[str, Any]] = []
        for template in templates[:25]:
            rendered = _render_preview_body(template)
            guidance_items.append(
                {
                    "guidance_public_id": str(template.public_id),
                    "template_key": template.template_key,
                    "version": template.version,
                    "title": template.title,
                    "language": template.language,
                    "requested_language": language,
                    "resolved_language": template.language,
                    "fallback_used": template.language != language,
                    "audience_type": template.audience_type,
                    "body": template.body,
                    "rendered_body": rendered["rendered_body"],
                    "public_health_caveats": template.public_health_caveats,
                }
            )

        resolved_language = language if any(item["language"] == language for item in guidance_items) else DEFAULT_CHV_LANGUAGE
        fallback_used = any(item["fallback_used"] for item in guidance_items)
        previews.append(
            {
                "language": language,
                "label": _language_label(language),
                "requested_language": language,
                "resolved_language": resolved_language,
                "fallback_used": fallback_used,
                "item_count": len(guidance_items),
                "content_unavailable": not guidance_items,
                "governance_status": "approved" if guidance_items else "no_approved_guidance_templates",
                "items": guidance_items,
                "warnings": (
                    ["No approved offline CHV guidance templates are available."]
                    if not guidance_items
                    else [f"{_language_label(language)} guidance uses English fallback."]
                    if fallback_used and language != DEFAULT_CHV_LANGUAGE
                    else []
                ),
            }
        )
    return previews


def _template_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(record["approval_status"] for record in records)
    audiences = Counter(record["audience_type"] for record in records)
    channels = Counter(record["channel"] for record in records)
    languages = sorted({record["language"] for record in records if record["language"]})
    unapproved_public_health = [
        record
        for record in records
        if record["risk_level"] in {MessageTemplate.RISK_HIGH, MessageTemplate.RISK_CRITICAL}
        and record["approval_status"] != MessageTemplate.APPROVAL_APPROVED
    ]
    return {
        "template_count": len(records),
        "approved_template_count": statuses.get(MessageTemplate.APPROVAL_APPROVED, 0),
        "pending_review_template_count": statuses.get(MessageTemplate.APPROVAL_PENDING_REVIEW, 0),
        "draft_template_count": statuses.get(MessageTemplate.APPROVAL_DRAFT, 0),
        "retired_template_count": statuses.get(MessageTemplate.APPROVAL_RETIRED, 0),
        "language_count": len(languages),
        "languages": languages,
        "audience_counts": dict(audiences),
        "channel_counts": dict(channels),
        "approval_status_counts": dict(statuses),
        "unapproved_high_risk_template_count": len(unapproved_public_health),
    }


def build_message_management_dashboard(
    template_queryset,
    *,
    date_from=None,
    date_to=None,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    templates = list(
        template_queryset.select_related(
            "approved_by",
            "created_by",
            "source_template",
            "translation_reviewed_by",
        )
    )
    template_records = [build_message_template_record(template) for template in templates]
    delivery_summary = build_delivery_outcome_summary(date_from=date_from, date_to=date_to)
    ussd_analytics = build_ussd_session_analytics(date_from=date_from, date_to=date_to)
    template_language_coverage = _build_template_language_coverage_matrix()
    ussd_route_tree_preview = _build_ussd_route_tree_preview()
    offline_guidance_preview = _build_offline_guidance_preview()
    missing_translation_dashboard = _build_missing_translation_dashboard(
        template_language_coverage,
        ussd_route_tree_preview=ussd_route_tree_preview,
        offline_guidance_preview=offline_guidance_preview,
    )
    ussd_menu_versions = [
        _ussd_menu_version_record(menu_version)
        for menu_version in UssdMenuVersion.objects.select_related(
            "approved_by",
            "created_by",
            "source_menu_version",
            "translation_reviewed_by",
        ).order_by("menu_key", "language", "-created_at")[:100]
    ]
    audit = build_message_governance_audit()
    template_summary = _template_summary(template_records)
    return {
        "schema_version": MESSAGE_MANAGEMENT_SCHEMA_VERSION,
        "generated_at": timezone.now(),
        "filters": filters or {},
        "available_filters": {
            "audience_types": [choice[0] for choice in MessageTemplate.AUDIENCE_CHOICES],
            "channels": [choice[0] for choice in MessageTemplate.CHANNEL_CHOICES],
            "languages": sorted(set(template_summary["languages"]) | set(SUPPORTED_LOCALIZATION_LANGUAGES)),
            "approval_statuses": [choice[0] for choice in MessageTemplate.APPROVAL_CHOICES],
        },
        "summary": {
            **template_summary,
            "delivery_record_count": delivery_summary["total_count"],
            "communication_reach_count": sum(
                row["unique_recipient_count"] for row in delivery_summary["reach_by_audience_channel"]
            ),
            "delivery_failure_count": delivery_summary["failed_count"],
            "delivery_success_rate_pct": delivery_summary["success_rate_pct"],
            "opt_out_count": delivery_summary["opt_out_summary"]["total_current_opt_out_count"],
            "opt_out_blocked_count": delivery_summary["opt_out_summary"]["total_blocked_opt_out_event_count"],
            "template_usage_version_count": len(delivery_summary["template_usage_by_version"]),
            "ussd_total_sessions": ussd_analytics["total_sessions"],
            "ussd_completion_rate_pct": ussd_analytics["completion_rate_pct"],
            "ussd_invalid_input_rate_pct": ussd_analytics["invalid_input_rate_pct"],
            "ussd_abandonment_rate_pct": ussd_analytics["abandonment_rate_pct"],
            "ussd_menu_version_count": len(ussd_menu_versions),
            "active_ussd_menu_version_count": len([version for version in ussd_menu_versions if version["is_active"]]),
            "missing_translation_count": template_language_coverage["missing_variant_count"],
            "placeholder_parity_warning_count": template_language_coverage["placeholder_warning_count"],
            "translation_review_warning_count": template_language_coverage["translation_review_warning_count"],
            "missing_translation_issue_count": missing_translation_dashboard["total_issue_count"],
            "offline_guidance_language_count": len(offline_guidance_preview),
            "strict_localization_issue_count": audit.get("strict_localization_issue_count", 0),
            "localization_fallback_rate_pct": (audit.get("localization_rollout") or {}).get("fallback_rate_pct", 0.0),
            "audit_status": audit["overall_status"],
        },
        "templates": template_records,
        "template_language_coverage": template_language_coverage,
        "missing_translation_dashboard": missing_translation_dashboard,
        "ussd_menu_versions": ussd_menu_versions,
        "ussd_route_tree_preview": ussd_route_tree_preview,
        "offline_guidance_preview": offline_guidance_preview,
        "delivery_summary": delivery_summary,
        "ussd_analytics": ussd_analytics,
        "audit": {
            "schema_version": audit["schema_version"],
            "overall_status": audit["overall_status"],
            "strict_localization_issue_count": audit.get("strict_localization_issue_count", 0),
            "localization_rollout": audit.get("localization_rollout", {}),
            "checks": audit["audit_checks"],
        },
    }


def build_message_template_detail(
    template: MessageTemplate,
    *,
    date_from=None,
    date_to=None,
) -> dict[str, Any]:
    version_history = [
        build_message_template_record(version)
        for version in MessageTemplate.objects.select_related(
            "approved_by",
            "created_by",
            "source_template",
            "translation_reviewed_by",
        )
        .filter(template_key=template.template_key, language=template.language)
        .order_by("-version")
    ]
    language_variants = [
        build_message_template_record(variant)
        for variant in MessageTemplate.objects.select_related(
            "approved_by",
            "created_by",
            "source_template",
            "translation_reviewed_by",
        )
        .filter(template_key=template.template_key, version=template.version)
        .order_by("language")
    ]
    return {
        "schema_version": MESSAGE_MANAGEMENT_SCHEMA_VERSION,
        "generated_at": timezone.now(),
        "template": build_message_template_record(template),
        "version_history": version_history,
        "language_variants": language_variants,
        "side_by_side_preview": _build_template_language_preview(template.template_key, template.version),
        "delivery_summary": build_delivery_outcome_summary(date_from=date_from, date_to=date_to, template=template),
    }


def transition_message_template_approval(
    template: MessageTemplate,
    *,
    action: str,
    actor,
    reason: str = "",
) -> MessageTemplate:
    normalized_action = (action or "approve").strip().lower()
    if normalized_action not in {"approve", "request_review", "reject", "retire"}:
        raise ValidationError({"action": ["Unsupported template approval action."]})

    previous_status = template.approval_status
    now = timezone.now()
    lineage_metadata = dict(template.lineage_metadata or {})
    approval_events = lineage_metadata.get("approval_events")
    if not isinstance(approval_events, list):
        approval_events = []
    approval_events.append(
        {
            "action": normalized_action,
            "actor_id": getattr(actor, "id", None),
            "actor_username": getattr(actor, "username", ""),
            "reason": reason.strip(),
            "previous_status": previous_status,
            "created_at": now.isoformat(),
        }
    )
    lineage_metadata["approval_events"] = approval_events[-50:]

    if normalized_action == "approve":
        if template.language != "en" and template.source_template_id is None:
            template.source_template = MessageTemplate.objects.filter(
                template_key=template.template_key,
                version=template.version,
                language="en",
            ).first()
        template.approval_status = MessageTemplate.APPROVAL_APPROVED
        template.approved_by = actor
        template.approved_at = now
        template.retired_at = None
        template.translation_status = MessageTemplate.TRANSLATION_APPROVED
        template.translation_reviewed_by = actor
        template.translation_reviewed_at = now
        template.translation_review_notes = reason.strip()
    elif normalized_action == "request_review":
        template.approval_status = MessageTemplate.APPROVAL_PENDING_REVIEW
        template.approved_by = None
        template.approved_at = None
        template.retired_at = None
        template.translation_status = (
            MessageTemplate.TRANSLATION_NEEDS_REVIEW
            if template.language != "en"
            else MessageTemplate.TRANSLATION_DRAFT
        )
    elif normalized_action == "reject":
        template.approval_status = MessageTemplate.APPROVAL_REJECTED
        template.approved_by = None
        template.approved_at = None
        template.retired_at = None
        if template.language != "en":
            template.translation_status = MessageTemplate.TRANSLATION_DRAFT
    elif normalized_action == "retire":
        template.approval_status = MessageTemplate.APPROVAL_RETIRED
        template.approved_by = None
        template.approved_at = None
        template.retired_at = now
        template.translation_status = MessageTemplate.TRANSLATION_RETIRED

    template.lineage_metadata = lineage_metadata
    template.full_clean()
    template.save()
    if normalized_action == "retire" and template.language == "en":
        MessageTemplate.objects.filter(source_template=template).exclude(
            translation_status__in=[
                MessageTemplate.TRANSLATION_RETIRED,
                MessageTemplate.TRANSLATION_BLOCKED_SOURCE_RETIRED,
            ]
        ).update(
            translation_status=MessageTemplate.TRANSLATION_BLOCKED_SOURCE_RETIRED,
            updated_at=now,
        )
    return template
