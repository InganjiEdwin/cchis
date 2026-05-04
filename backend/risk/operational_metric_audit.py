from __future__ import annotations

import csv
import hashlib
import json
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from io import StringIO

from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Q
from django.utils import timezone

from .models import (
    Alert,
    CHVMessage,
    OperationalMetricDefinition,
    OperationalMetricSnapshot,
    PreparednessAction,
    PreparednessActionEvent,
)
from .operational_metric_dashboard import build_operational_kpi_dashboard


OPERATIONAL_KPI_INTEGRITY_AUDIT_SCHEMA_VERSION = "operational-kpi-integrity-audit-v1"
OPERATIONAL_KPI_ME_EXPORT_SCHEMA_VERSION = "operational-kpi-me-export-v1"
OPERATIONAL_KPI_ME_EXPORT_CONTENT_SCHEMA_VERSION = "operational-kpi-me-export-content-v1"

OPERATIONAL_INTERPRETATION = {
    "model_separation": (
        "Operational KPIs measure delivery, adoption, response, and source-data health. "
        "They must not be interpreted as model accuracy, causal impact, or outbreak confirmation."
    ),
    "baseline_caution": (
        "Outcome or impact interpretation requires explicit baseline periods and mature surveillance labels."
    ),
    "source_caution": (
        "KPI values with missing source coverage, stale snapshots, or threshold warnings should be treated as operational review signals."
    ),
}


def parse_operational_metric_date(value: str | date | None, *, field_name: str) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as error:
        raise ValueError(f"{field_name} must be a YYYY-MM-DD date.") from error


def _default_date_range(date_from: date | None, date_to: date | None) -> tuple[date, date]:
    latest_snapshot = OperationalMetricSnapshot.objects.order_by("-date", "-generated_at").first()
    resolved_to = date_to or (latest_snapshot.date if latest_snapshot else timezone.localdate())
    resolved_from = date_from or resolved_to - timedelta(days=13)
    if resolved_from > resolved_to:
        raise ValueError("date_from must be on or before date_to.")
    return resolved_from, resolved_to


def _range_datetimes(date_from: date, date_to: date) -> tuple[datetime, datetime]:
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(date_from, time.min), tz)
    end = timezone.make_aware(datetime.combine(date_to + timedelta(days=1), time.min), tz)
    return start, end


def _number(value: Decimal | int | float | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _stable_json(value) -> str:
    return json.dumps(value, cls=DjangoJSONEncoder, sort_keys=True, separators=(",", ":"))


def _hash_payload(value) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _issue(
    *,
    check_id: str,
    severity: str,
    record_type: str,
    record_id: str,
    message: str,
    evidence: dict,
) -> dict:
    return {
        "check_id": check_id,
        "severity": severity,
        "record_type": record_type,
        "record_id": record_id,
        "message": message,
        "evidence": evidence,
    }


def _parse_operational_metric_ward_id(value: int | str | None) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("ward_id must be an integer.") from error


def _normalise_operational_metric_filters(
    *,
    ward_id: int | str | None = None,
    sub_county: str = "",
    source_channel: str = "",
) -> dict:
    return {
        "ward_id": _parse_operational_metric_ward_id(ward_id),
        "sub_county": (sub_county or "").strip(),
        "source_channel": (source_channel or "").strip().upper(),
    }


def _apply_ward_filters(queryset, filters: dict, *, ward_field: str = "ward"):
    ward_id = filters.get("ward_id")
    sub_county = filters.get("sub_county")
    if ward_id:
        queryset = queryset.filter(**{f"{ward_field}_id": ward_id})
    if sub_county:
        queryset = queryset.filter(**{f"{ward_field}__sub_county__iexact": sub_county})
    return queryset


def _apply_alert_filters(queryset, filters: dict):
    queryset = _apply_ward_filters(queryset, filters)
    source_channel = filters.get("source_channel")
    if source_channel:
        queryset = queryset.filter(channel__iexact=source_channel)
    return queryset


def _apply_action_filters(queryset, filters: dict):
    queryset = _apply_ward_filters(queryset, filters)
    if filters.get("source_channel"):
        return queryset.none()
    return queryset


def _apply_message_filters(queryset, filters: dict):
    queryset = _apply_ward_filters(queryset, filters)
    source_channel = filters.get("source_channel")
    if source_channel:
        queryset = queryset.filter(channel__iexact=source_channel)
    return queryset


def _snapshot_source_coverage_issues(snapshots) -> list[dict]:
    issues = []
    for snapshot in snapshots:
        coverage = snapshot.source_coverage
        if not isinstance(coverage, dict) or not coverage.get("schema_version"):
            issues.append(
                _issue(
                    check_id="snapshot_source_coverage_present",
                    severity="fail",
                    record_type="OperationalMetricSnapshot",
                    record_id=snapshot.snapshot_key,
                    message="KPI snapshot is missing source coverage schema metadata.",
                    evidence={
                        "metric_key": snapshot.metric_definition.metric_key,
                        "date": snapshot.date.isoformat(),
                        "status": snapshot.status,
                        "ward_id": snapshot.ward_id,
                        "sub_county": snapshot.sub_county,
                        "source_channel": snapshot.source_channel,
                        "source_coverage": coverage,
                    },
                )
            )
    return issues


def _alert_delivery_integrity_issues(start: datetime, end: datetime, *, filters: dict) -> list[dict]:
    issues = []
    delivered_alerts = Alert.objects.select_related("ward").filter(
        status=Alert.STATUS_DELIVERED,
        created_at__gte=start,
        created_at__lt=end,
    )
    delivered_alerts = _apply_alert_filters(delivered_alerts, filters)
    for alert in delivered_alerts.filter(sent_at__isnull=True).order_by("id"):
        issues.append(
            _issue(
                check_id="delivered_alert_has_delivery_timestamp",
                severity="fail",
                record_type="Alert",
                record_id=str(alert.public_id),
                message="Delivered alert has no delivery timestamp.",
                evidence={
                    "alert_id": alert.id,
                    "ward_id": alert.ward_id,
                    "ward_name": alert.ward.name,
                    "channel": alert.channel,
                    "created_at": alert.created_at.isoformat(),
                    "sent_at": None,
                },
            )
        )

    for alert in delivered_alerts.exclude(sent_at__isnull=True).order_by("id"):
        if alert.sent_at < alert.created_at:
            issues.append(
                _issue(
                    check_id="alert_delivery_latency_non_negative",
                    severity="fail",
                    record_type="Alert",
                    record_id=str(alert.public_id),
                    message="Delivered alert has an impossible negative delivery latency.",
                    evidence={
                        "alert_id": alert.id,
                        "ward_id": alert.ward_id,
                        "ward_name": alert.ward.name,
                        "channel": alert.channel,
                        "created_at": alert.created_at.isoformat(),
                        "sent_at": alert.sent_at.isoformat(),
                        "latency_seconds": (alert.sent_at - alert.created_at).total_seconds(),
                    },
                )
            )
    return issues


def _preparedness_action_integrity_issues(start: datetime, end: datetime, *, filters: dict) -> list[dict]:
    issues = []
    completed_actions = PreparednessAction.objects.select_related("ward").filter(
        status=PreparednessAction.STATUS_COMPLETED,
        created_at__lt=end,
    ).filter(Q(completed_at__gte=start, completed_at__lt=end) | Q(updated_at__gte=start, updated_at__lt=end))
    completed_actions = _apply_action_filters(completed_actions, filters)
    for action in completed_actions.order_by("id"):
        action_issues = []
        if action.completed_at is None:
            action_issues.append("missing_completed_at")
        elif action.completed_at < action.created_at:
            action_issues.append("completed_before_created")

        completion_event_exists = action.events.filter(event_type=PreparednessActionEvent.EVENT_COMPLETED).exists()
        created_event_exists = action.events.filter(event_type=PreparednessActionEvent.EVENT_CREATED).exists()
        if not created_event_exists:
            action_issues.append("missing_created_event")
        if not completion_event_exists:
            action_issues.append("missing_completed_event")

        if action_issues:
            issues.append(
                _issue(
                    check_id="completed_action_has_creation_evidence",
                    severity="fail",
                    record_type="PreparednessAction",
                    record_id=str(action.public_id),
                    message="Completed preparedness action is missing creation/completion chronology evidence.",
                    evidence={
                        "action_id": action.id,
                        "ward_id": action.ward_id,
                        "ward_name": action.ward.name,
                        "status": action.status,
                        "created_at": action.created_at.isoformat(),
                        "completed_at": action.completed_at.isoformat() if action.completed_at else None,
                        "issues": action_issues,
                    },
                )
            )
    return issues


def _snapshot_support_filters(snapshot: OperationalMetricSnapshot) -> dict:
    return {
        "ward_id": snapshot.ward_id,
        "sub_county": snapshot.sub_county,
        "source_channel": snapshot.source_channel,
    }


def _household_reach_integrity_issues(snapshots) -> list[dict]:
    issues = []
    for snapshot in snapshots:
        if snapshot.metric_definition.metric_key != "households_reached_count" or snapshot.value is None:
            continue
        support_filters = _snapshot_support_filters(snapshot)
        sent_messages = CHVMessage.objects.filter(
            status__in=[CHVMessage.STATUS_SENT, CHVMessage.STATUS_DELIVERED],
            created_at__gte=snapshot.period_start,
            created_at__lt=snapshot.period_end,
        )
        sent_messages = _apply_message_filters(sent_messages, support_filters)
        completed_actions = PreparednessAction.objects.filter(
            action_type=PreparednessAction.ACTION_HOUSEHOLD_PREVENTION_MESSAGE,
            status=PreparednessAction.STATUS_COMPLETED,
            completed_at__gte=snapshot.period_start,
            completed_at__lt=snapshot.period_end,
        )
        completed_actions = _apply_action_filters(completed_actions, support_filters)
        sent_message_count = sent_messages.count()
        completed_household_actions = completed_actions.count()
        denominator = int(snapshot.denominator) if snapshot.denominator is not None else 0
        maximum_supported_reach = max(sent_message_count + completed_household_actions, denominator)
        if snapshot.value > Decimal(str(maximum_supported_reach)):
            issues.append(
                _issue(
                    check_id="household_reach_not_above_sent_messages",
                    severity="fail",
                    record_type="OperationalMetricSnapshot",
                    record_id=snapshot.snapshot_key,
                    message="Household reach KPI exceeds the supporting sent-message/action count.",
                    evidence={
                        "metric_key": snapshot.metric_definition.metric_key,
                        "date": snapshot.date.isoformat(),
                        "value": _number(snapshot.value),
                        "denominator": _number(snapshot.denominator),
                        "ward_id": snapshot.ward_id,
                        "sub_county": snapshot.sub_county,
                        "source_channel": snapshot.source_channel,
                        "sent_or_delivered_chv_messages": sent_message_count,
                        "completed_household_actions": completed_household_actions,
                        "maximum_supported_reach": maximum_supported_reach,
                    },
                )
            )
    return issues


def _metric_definition_reference_time(snapshot: OperationalMetricSnapshot):
    return snapshot.generated_at or snapshot.period_end or timezone.now()


def _metric_definition_integrity_issues(snapshots) -> list[dict]:
    issues = []
    for snapshot in snapshots:
        definition = snapshot.metric_definition
        reference_time = _metric_definition_reference_time(snapshot)
        stale_reasons = []
        if definition.effective_from and definition.effective_from > reference_time:
            stale_reasons.append("metric_definition_effective_from_after_snapshot")
        if definition.effective_to and definition.effective_to <= reference_time:
            stale_reasons.append("metric_definition_effective_to_elapsed")
        if not definition.is_active and not definition.effective_to:
            stale_reasons.append("metric_definition_inactive_without_retirement_time")
        if stale_reasons:
            issues.append(
                _issue(
                    check_id="dashboard_uses_current_metric_definition",
                    severity="fail",
                    record_type="OperationalMetricSnapshot",
                    record_id=snapshot.snapshot_key,
                    message="Current operational KPI snapshot references a stale metric definition.",
                    evidence={
                        "metric_key": definition.metric_key,
                        "metric_version": definition.version,
                        "snapshot_date": snapshot.date.isoformat(),
                        "snapshot_generated_at": snapshot.generated_at.isoformat() if snapshot.generated_at else None,
                        "definition_validity_reference": reference_time.isoformat(),
                        "definition_is_active": definition.is_active,
                        "effective_from": definition.effective_from.isoformat() if definition.effective_from else None,
                        "effective_to": definition.effective_to.isoformat() if definition.effective_to else None,
                        "stale_reasons": stale_reasons,
                    },
                )
            )
    return issues


def build_operational_kpi_integrity_audit(
    *,
    date_from: date | str | None = None,
    date_to: date | str | None = None,
    ward_id: int | str | None = None,
    sub_county: str = "",
    source_channel: str = "",
) -> dict:
    resolved_from, resolved_to = _default_date_range(
        parse_operational_metric_date(date_from, field_name="date_from"),
        parse_operational_metric_date(date_to, field_name="date_to"),
    )
    filters = {
        "date_from": resolved_from.isoformat(),
        "date_to": resolved_to.isoformat(),
        **_normalise_operational_metric_filters(
            ward_id=ward_id,
            sub_county=sub_county,
            source_channel=source_channel,
        ),
    }
    start, end = _range_datetimes(resolved_from, resolved_to)
    snapshot_queryset = OperationalMetricSnapshot.objects.select_related("metric_definition", "ward").filter(
        date__gte=resolved_from,
        date__lte=resolved_to,
    )
    snapshot_queryset = _apply_snapshot_filters(snapshot_queryset, filters)
    snapshots = list(snapshot_queryset.order_by("metric_definition__metric_key", "date", "snapshot_key"))

    issues = []
    issues.extend(_snapshot_source_coverage_issues(snapshots))
    issues.extend(_alert_delivery_integrity_issues(start, end, filters=filters))
    issues.extend(_preparedness_action_integrity_issues(start, end, filters=filters))
    issues.extend(_household_reach_integrity_issues(snapshots))
    issues.extend(_metric_definition_integrity_issues(snapshots))

    failed = [issue for issue in issues if issue["severity"] == "fail"]
    warning = [issue for issue in issues if issue["severity"] == "warning"]
    alerts = _apply_alert_filters(Alert.objects.filter(created_at__gte=start, created_at__lt=end), filters)
    delivered_alerts = _apply_alert_filters(
        Alert.objects.filter(status=Alert.STATUS_DELIVERED, created_at__gte=start, created_at__lt=end),
        filters,
    )
    completed_actions = _apply_action_filters(
        PreparednessAction.objects.filter(
            status=PreparednessAction.STATUS_COMPLETED,
            created_at__lt=end,
        ).filter(Q(completed_at__gte=start, completed_at__lt=end) | Q(updated_at__gte=start, updated_at__lt=end)),
        filters,
    )
    return {
        "schema_version": OPERATIONAL_KPI_INTEGRITY_AUDIT_SCHEMA_VERSION,
        "date_from": resolved_from.isoformat(),
        "date_to": resolved_to.isoformat(),
        "filters": filters,
        "overall_status": "fail" if failed else "warning" if warning else "pass",
        "record_totals": {
            "snapshots": len(snapshots),
            "alerts": alerts.count(),
            "delivered_alerts": delivered_alerts.count(),
            "completed_actions": completed_actions.count(),
        },
        "issue_count": len(issues),
        "fail_count": len(failed),
        "warning_count": len(warning),
        "issues": sorted(issues, key=lambda item: (item["check_id"], item["record_type"], item["record_id"])),
    }


def _apply_snapshot_filters(queryset, filters: dict):
    ward_id = filters.get("ward_id")
    sub_county = filters.get("sub_county")
    source_channel = filters.get("source_channel")
    if ward_id:
        queryset = queryset.filter(ward_id=ward_id)
    if sub_county:
        queryset = queryset.filter(sub_county__iexact=sub_county)
    if source_channel:
        queryset = queryset.filter(source_channel__iexact=source_channel)
    return queryset


def _csv_scalar(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return _stable_json(value)
    return str(value)


def _snapshot_row(snapshot: OperationalMetricSnapshot) -> dict:
    definition = snapshot.metric_definition
    return {
        "metric_key": definition.metric_key,
        "metric_version": definition.version,
        "metric_group": definition.metric_group,
        "metric_family": definition.metric_family,
        "display_name": definition.display_name,
        "owner": definition.owner,
        "interpretation": definition.interpretation,
        "date": snapshot.date.isoformat(),
        "period_start": snapshot.period_start.isoformat(),
        "period_end": snapshot.period_end.isoformat(),
        "grain": snapshot.grain,
        "value": _number(snapshot.value),
        "value_unit": snapshot.value_unit,
        "numerator": _number(snapshot.numerator),
        "denominator": _number(snapshot.denominator),
        "status": snapshot.status,
        "source_record_count": snapshot.source_record_count,
        "source_warnings": sorted(snapshot.source_coverage.get("warnings", [])) if isinstance(snapshot.source_coverage, dict) else [],
        "snapshot_key": snapshot.snapshot_key,
        "county": snapshot.county,
        "sub_county": snapshot.sub_county,
        "ward_id": snapshot.ward_id,
        "ward_name": snapshot.ward.name if snapshot.ward_id else "",
        "source_channel": snapshot.source_channel,
        "action_type": snapshot.action_type,
        "alert_severity": snapshot.alert_severity,
        "model_version": snapshot.model_version,
        "dimension_values": snapshot.dimension_values,
    }


def _csv_payload(rows: list[dict], *, content: dict, data_sha256: str) -> str:
    fieldnames = [
        "row_type",
        "metadata_key",
        "metadata_value",
        "metric_key",
        "metric_version",
        "metric_group",
        "display_name",
        "owner",
        "date",
        "grain",
        "value",
        "value_unit",
        "numerator",
        "denominator",
        "status",
        "source_record_count",
        "source_warnings",
        "snapshot_key",
        "county",
        "sub_county",
        "ward_id",
        "ward_name",
        "source_channel",
        "action_type",
        "alert_severity",
        "model_version",
        "interpretation",
    ]
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    metadata_rows = [
        ("schema_version", content["schema_version"]),
        ("data_sha256", data_sha256),
        ("filters.date_from", content["filters"]["date_from"]),
        ("filters.date_to", content["filters"]["date_to"]),
        ("filters.ward_id", content["filters"]["ward_id"]),
        ("filters.sub_county", content["filters"]["sub_county"]),
        ("filters.source_channel", content["filters"]["source_channel"]),
        ("metric_row_count", len(rows)),
        ("audit.overall_status", content["audit"]["overall_status"]),
        ("audit.issue_count", content["audit"]["issue_count"]),
        ("threshold_alert_count", len(content["threshold_alerts"])),
        ("source_coverage_warning_count", len(content["source_coverage_warnings"])),
        ("interpretation.model_separation", content["interpretation"]["model_separation"]),
        ("interpretation.baseline_caution", content["interpretation"]["baseline_caution"]),
        ("interpretation.source_caution", content["interpretation"]["source_caution"]),
    ]
    for key, value in metadata_rows:
        writer.writerow(
            {
                "row_type": "metadata",
                "metadata_key": key,
                "metadata_value": _csv_scalar(value),
            }
        )
    for row in rows:
        csv_row = dict(row)
        csv_row["row_type"] = "metric"
        csv_row["source_warnings"] = "|".join(row["source_warnings"])
        writer.writerow(csv_row)
    return output.getvalue()


def build_operational_kpi_me_export(
    *,
    date_from: date | str | None = None,
    date_to: date | str | None = None,
    ward_id: int | str | None = None,
    sub_county: str = "",
    source_channel: str = "",
    output_format: str = "json",
    generated_at=None,
) -> dict:
    if output_format not in {"json", "csv"}:
        raise ValueError("output_format must be either json or csv.")
    resolved_from, resolved_to = _default_date_range(
        parse_operational_metric_date(date_from, field_name="date_from"),
        parse_operational_metric_date(date_to, field_name="date_to"),
    )
    normalised_filters = _normalise_operational_metric_filters(
        ward_id=ward_id,
        sub_county=sub_county,
        source_channel=source_channel,
    )
    filters = {
        "date_from": resolved_from.isoformat(),
        "date_to": resolved_to.isoformat(),
        **normalised_filters,
    }
    dashboard_filters = {key: value for key, value in filters.items() if value not in (None, "")}
    dashboard = build_operational_kpi_dashboard(dashboard_filters)
    audit = build_operational_kpi_integrity_audit(
        date_from=resolved_from,
        date_to=resolved_to,
        ward_id=normalised_filters["ward_id"],
        sub_county=normalised_filters["sub_county"],
        source_channel=normalised_filters["source_channel"],
    )
    snapshots = OperationalMetricSnapshot.objects.select_related("metric_definition", "ward").filter(
        date__gte=resolved_from,
        date__lte=resolved_to,
    )
    snapshots = _apply_snapshot_filters(snapshots, filters)
    metric_rows = [
        _snapshot_row(snapshot)
        for snapshot in snapshots.order_by("metric_definition__metric_key", "date", "snapshot_key")
    ]
    content = {
        "schema_version": OPERATIONAL_KPI_ME_EXPORT_CONTENT_SCHEMA_VERSION,
        "filters": filters,
        "interpretation": OPERATIONAL_INTERPRETATION,
        "summary": dashboard["summary"],
        "metric_rows": metric_rows,
        "threshold_alerts": dashboard["panels"]["threshold_alerts"],
        "source_coverage_warnings": dashboard["panels"]["source_coverage_warnings"],
        "audit": audit,
    }
    data_sha256 = _hash_payload(content)
    if output_format == "json":
        payload = json.dumps(content, cls=DjangoJSONEncoder, indent=2, sort_keys=True)
        content_type = "application/json"
        filename = f"operational-kpi-me-export-{resolved_from.isoformat()}-{resolved_to.isoformat()}.json"
    else:
        payload = _csv_payload(metric_rows, content=content, data_sha256=data_sha256)
        content_type = "text/csv"
        filename = f"operational-kpi-me-export-{resolved_from.isoformat()}-{resolved_to.isoformat()}.csv"

    return {
        "schema_version": OPERATIONAL_KPI_ME_EXPORT_SCHEMA_VERSION,
        "generated_at": (generated_at or timezone.now()).isoformat(),
        "filters": filters,
        "format": output_format,
        "filename": filename,
        "content_type": content_type,
        "row_count": len(metric_rows),
        "data_sha256": data_sha256,
        "payload_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "payload": payload,
        "audit_status": audit["overall_status"],
        "audit_issue_count": audit["issue_count"],
    }
