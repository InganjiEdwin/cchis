from __future__ import annotations

from collections import Counter
from string import Formatter
from typing import Any, Iterable

from django.core.exceptions import ValidationError
from django.db.models import Count, Max, Q
from django.utils import timezone

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


MESSAGE_MANAGEMENT_SCHEMA_VERSION = "message-management-phase-5-v1"


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
        "template_usage_by_version": template_usage_by_version,
        "reach_by_audience_channel": reach_records,
        "opt_out_summary": build_opt_out_monitoring_summary(date_from=date_from, date_to=date_to),
        "recent_records": recent_records[:20],
    }


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
        "is_active": menu_version.is_active,
        "safe_fallback_copy": menu_version.safe_fallback_copy,
        "lineage_metadata": menu_version.lineage_metadata or {},
        "created_by": menu_version.created_by_id,
        "created_by_username": menu_version.created_by.username if menu_version.created_by else "",
        "created_at": menu_version.created_at,
        "updated_at": menu_version.updated_at,
        "route_count": len(routes) if isinstance(routes, dict) else 0,
        "node_count": len(nodes) if isinstance(nodes, dict) else 0,
        "validation_status": validation_status,
        "validation_messages": validation_messages,
    }


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
    templates = list(template_queryset.select_related("approved_by", "created_by"))
    template_records = [build_message_template_record(template) for template in templates]
    delivery_summary = build_delivery_outcome_summary(date_from=date_from, date_to=date_to)
    ussd_analytics = build_ussd_session_analytics(date_from=date_from, date_to=date_to)
    ussd_menu_versions = [
        _ussd_menu_version_record(menu_version)
        for menu_version in UssdMenuVersion.objects.select_related("approved_by", "created_by").order_by(
            "menu_key",
            "language",
            "-created_at",
        )[:100]
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
            "languages": template_summary["languages"],
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
            "audit_status": audit["overall_status"],
        },
        "templates": template_records,
        "ussd_menu_versions": ussd_menu_versions,
        "delivery_summary": delivery_summary,
        "ussd_analytics": ussd_analytics,
        "audit": {
            "schema_version": audit["schema_version"],
            "overall_status": audit["overall_status"],
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
        for version in MessageTemplate.objects.select_related("approved_by", "created_by")
        .filter(template_key=template.template_key, language=template.language)
        .order_by("-version")
    ]
    language_variants = [
        build_message_template_record(variant)
        for variant in MessageTemplate.objects.select_related("approved_by", "created_by")
        .filter(template_key=template.template_key, version=template.version)
        .order_by("language")
    ]
    return {
        "schema_version": MESSAGE_MANAGEMENT_SCHEMA_VERSION,
        "generated_at": timezone.now(),
        "template": build_message_template_record(template),
        "version_history": version_history,
        "language_variants": language_variants,
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
        template.approval_status = MessageTemplate.APPROVAL_APPROVED
        template.approved_by = actor
        template.approved_at = now
        template.retired_at = None
    elif normalized_action == "request_review":
        template.approval_status = MessageTemplate.APPROVAL_PENDING_REVIEW
        template.approved_by = None
        template.approved_at = None
        template.retired_at = None
    elif normalized_action == "reject":
        template.approval_status = MessageTemplate.APPROVAL_REJECTED
        template.approved_by = None
        template.approved_at = None
        template.retired_at = None
    elif normalized_action == "retire":
        template.approval_status = MessageTemplate.APPROVAL_RETIRED
        template.approved_by = None
        template.approved_at = None
        template.retired_at = now

    template.lineage_metadata = lineage_metadata
    template.full_clean()
    template.save()
    return template
