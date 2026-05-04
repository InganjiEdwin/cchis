from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from .models import (
    ModelRun,
    OperationalMetricDefinition,
    OperationalMetricSnapshot,
    OperationalSLAThreshold,
    Ward,
)
from .interoperability import build_interoperability_operational_kpi_feed
from .operational_metric_builders import (
    build_operational_kpi_source_coverage_audit,
    select_operational_baseline_for_snapshot,
)
from .operational_metric_thresholds import (
    evaluate_operational_kpi_thresholds,
    operational_threshold_applies_to_snapshot,
)
from .operational_metrics import sync_operational_metric_catalog


OPERATIONAL_KPI_DASHBOARD_SCHEMA_VERSION = "operational-kpi-dashboard-v1"

OPERATIONAL_OVERVIEW_KEYS = [
    "alerts_delivered_under_5m_pct",
    "trigger_activation_rate",
    "action_completion_rate",
    "overdue_action_count",
    "source_data_freshness_pass_rate",
]
SLA_PANEL_KEYS = [
    "alert_delivery_time_p95_seconds",
    "action_acknowledgement_time_p50_seconds",
    "overdue_action_count",
]
ADOPTION_COVERAGE_KEYS = [
    "chv_active_use_rate",
    "households_reached_count",
    "source_data_freshness_pass_rate",
]
RESPONSE_TIME_TREND_KEYS = [
    "alert_delivery_time_p50_seconds",
    "alert_delivery_time_p95_seconds",
    "action_acknowledgement_time_p50_seconds",
]
FACILITY_TREND_KEYS = ["facility_review_completion_rate"]
USSD_TREND_KEYS = ["ussd_completion_rate"]


def parse_dashboard_date(value: str | None, *, field_name: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field_name} must be a YYYY-MM-DD date.") from error


def _number(value: Decimal | int | float | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _format_value(value: Decimal | None, value_type: str, value_unit: str) -> str:
    if value is None:
        return "No value"
    numeric = float(value)
    if value_type == OperationalMetricDefinition.VALUE_PERCENT:
        return f"{numeric:.1f}%"
    if value_type == OperationalMetricDefinition.VALUE_DURATION_SECONDS:
        if numeric >= 3600:
            return f"{numeric / 3600:.1f} hr"
        if numeric >= 60:
            return f"{numeric / 60:.1f} min"
        return f"{numeric:.0f} sec"
    if value_type == OperationalMetricDefinition.VALUE_RATIO:
        return f"{numeric:.3f}"
    if value_type == OperationalMetricDefinition.VALUE_COUNT:
        return f"{numeric:,.0f}"
    return f"{numeric:.2f} {value_unit}".strip()


def _status_tone(status: str) -> str:
    if status == OperationalMetricSnapshot.STATUS_COMPLETE:
        return "success"
    if status == OperationalMetricSnapshot.STATUS_PARTIAL:
        return "warning"
    if status in {OperationalMetricSnapshot.STATUS_NO_SOURCE, OperationalMetricSnapshot.STATUS_STALE}:
        return "danger"
    if status == OperationalMetricSnapshot.STATUS_FAILED:
        return "danger"
    return "default"


def _threshold_status(snapshot: OperationalMetricSnapshot | None) -> dict:
    if snapshot is None or snapshot.value is None:
        return {"status": "not_evaluable", "label": "No current KPI value", "threshold": None}

    thresholds = (
        OperationalSLAThreshold.objects.filter(
            metric_definition=snapshot.metric_definition,
            is_active=True,
            effective_from__lte=timezone.now(),
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gt=timezone.now()))
        .order_by("-effective_from", "-updated_at")
    )
    threshold = next(
        (
            candidate
            for candidate in thresholds
            if operational_threshold_applies_to_snapshot(candidate, snapshot)
        ),
        None,
    )
    if threshold is None:
        return {"status": "not_configured", "label": "No active SLA threshold", "threshold": None}

    value = snapshot.value
    target = threshold.target_value
    comparator = threshold.comparator
    passes = {
        OperationalSLAThreshold.COMPARATOR_LTE: value <= target,
        OperationalSLAThreshold.COMPARATOR_LT: value < target,
        OperationalSLAThreshold.COMPARATOR_GTE: value >= target,
        OperationalSLAThreshold.COMPARATOR_GT: value > target,
    }[comparator]
    return {
        "status": "pass" if passes else "breach",
        "label": "Within target" if passes else "Outside target",
        "threshold": {
            "threshold_key": threshold.threshold_key,
            "display_name": threshold.display_name,
            "comparator": comparator,
            "target_value": _number(target),
            "warning_value": _number(threshold.warning_value),
            "critical_value": _number(threshold.critical_value),
            "value_unit": threshold.value_unit,
        },
    }


def _baseline_payload(snapshot: OperationalMetricSnapshot | None) -> dict:
    if snapshot is None or snapshot.value is None:
        return {"status": "not_evaluable", "baseline": None}

    baseline, active_baseline_count = select_operational_baseline_for_snapshot(snapshot)
    if baseline is None or baseline.baseline_value is None:
        return {
            "status": "not_configured",
            "baseline": None,
            "reason": (
                "no_dimension_matching_active_baseline"
                if active_baseline_count
                else "no_active_baseline"
            ),
        }

    delta = snapshot.value - baseline.baseline_value
    percent_delta = None if baseline.baseline_value == 0 else (delta / baseline.baseline_value) * Decimal("100")
    return {
        "status": "compared",
        "baseline": {
            "baseline_key": baseline.baseline_key,
            "name": baseline.name,
            "baseline_value": _number(baseline.baseline_value),
            "delta": _number(delta),
            "percent_delta": _number(percent_delta),
            "period_start": baseline.period_start.isoformat(),
            "period_end": baseline.period_end.isoformat(),
            "dimensions": baseline.dimensions,
        },
    }


def _snapshot_payload(
    definition: OperationalMetricDefinition,
    snapshot: OperationalMetricSnapshot | None,
) -> dict:
    value = snapshot.value if snapshot else None
    status = snapshot.status if snapshot else "MISSING"
    source_coverage = snapshot.source_coverage if snapshot else {}
    return {
        "metric_key": definition.metric_key,
        "display_name": definition.display_name,
        "description": definition.description,
        "metric_group": definition.metric_group,
        "metric_family": definition.metric_family,
        "owner": definition.owner,
        "formula": definition.formula,
        "window": definition.window,
        "source_model": definition.source_model,
        "source_models": definition.source_models,
        "interpretation": definition.interpretation,
        "value_type": definition.value_type,
        "value_unit": definition.value_unit,
        "value": _number(value),
        "display_value": _format_value(value, definition.value_type, definition.value_unit),
        "status": status,
        "status_tone": _status_tone(status),
        "snapshot_key": snapshot.snapshot_key if snapshot else None,
        "snapshot_date": snapshot.date.isoformat() if snapshot else None,
        "period_start": snapshot.period_start.isoformat() if snapshot else None,
        "period_end": snapshot.period_end.isoformat() if snapshot else None,
        "source_record_count": snapshot.source_record_count if snapshot else 0,
        "source_coverage_warnings": source_coverage.get("warnings", []),
        "dimension_values": snapshot.dimension_values if snapshot else {},
        "source_channel": snapshot.source_channel if snapshot else "",
        "baseline": _baseline_payload(snapshot),
        "sla": _threshold_status(snapshot),
    }


def _latest_snapshots_by_metric(snapshots: list[OperationalMetricSnapshot]) -> dict[str, OperationalMetricSnapshot]:
    latest: dict[str, OperationalMetricSnapshot] = {}
    for snapshot in sorted(snapshots, key=lambda item: (item.date, item.generated_at, item.id)):
        latest[snapshot.metric_definition.metric_key] = snapshot
    return latest


def _trend_series(
    *,
    definitions_by_key: dict[str, OperationalMetricDefinition],
    snapshots: list[OperationalMetricSnapshot],
    metric_keys: list[str],
) -> list[dict]:
    by_metric_date: dict[tuple[str, str], OperationalMetricSnapshot] = {}
    for snapshot in snapshots:
        metric_key = snapshot.metric_definition.metric_key
        if metric_key not in metric_keys:
            continue
        key = (metric_key, snapshot.date.isoformat())
        existing = by_metric_date.get(key)
        if existing is None or (snapshot.generated_at, snapshot.id) > (existing.generated_at, existing.id):
            by_metric_date[key] = snapshot

    series = []
    for metric_key in metric_keys:
        definition = definitions_by_key.get(metric_key)
        if definition is None:
            continue
        points = [
            {
                "date": snapshot.date.isoformat(),
                "value": _number(snapshot.value),
                "display_value": _format_value(snapshot.value, definition.value_type, definition.value_unit),
                "status": snapshot.status,
                "source_record_count": snapshot.source_record_count,
            }
            for (key, _), snapshot in sorted(by_metric_date.items(), key=lambda item: item[0][1])
            if key == metric_key
        ]
        series.append(
            {
                "metric_key": definition.metric_key,
                "display_name": definition.display_name,
                "value_type": definition.value_type,
                "value_unit": definition.value_unit,
                "points": points,
            }
        )
    return series


def _source_warning_payload(latest_snapshots: dict[str, OperationalMetricSnapshot], audit: dict) -> list[dict]:
    warnings: dict[tuple[str, str, str], dict] = {}
    for metric_key, snapshot in latest_snapshots.items():
        if snapshot.status in {
            OperationalMetricSnapshot.STATUS_PARTIAL,
            OperationalMetricSnapshot.STATUS_NO_SOURCE,
            OperationalMetricSnapshot.STATUS_STALE,
            OperationalMetricSnapshot.STATUS_FAILED,
        }:
            warnings[(metric_key, f"latest_snapshot_status_{snapshot.status.lower()}", snapshot.snapshot_key)] = {
                "metric_key": metric_key,
                "warning": f"latest_snapshot_status_{snapshot.status.lower()}",
                "snapshot_key": snapshot.snapshot_key,
                "snapshot_date": snapshot.date.isoformat(),
                "status": snapshot.status,
            }
        for warning in snapshot.source_coverage.get("warnings", []):
            warnings[(metric_key, warning, snapshot.snapshot_key)] = {
                "metric_key": metric_key,
                "warning": warning,
                "snapshot_key": snapshot.snapshot_key,
                "snapshot_date": snapshot.date.isoformat(),
                "status": snapshot.status,
            }

    for warning in audit.get("warnings", []):
        metric_key = warning.get("metric_key", "")
        key = (metric_key, warning.get("warning", ""), warning.get("snapshot_key", "audit"))
        warnings.setdefault(
            key,
            {
                "metric_key": metric_key,
                "warning": warning.get("warning", ""),
                "snapshot_key": warning.get("snapshot_key"),
                "snapshot_date": warning.get("latest_date"),
                "status": "AUDIT",
            },
        )
    return sorted(warnings.values(), key=lambda item: (item["metric_key"], item["warning"]))


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


def _available_filters() -> dict:
    return {
        "wards": list(Ward.objects.filter(is_active=True).order_by("name").values("id", "name", "county", "sub_county")[:250]),
        "sub_counties": list(
            Ward.objects.filter(is_active=True)
            .exclude(sub_county="")
            .order_by("sub_county")
            .values_list("sub_county", flat=True)
            .distinct()
        ),
        "source_channels": list(
            OperationalMetricSnapshot.objects.exclude(source_channel="")
            .order_by("source_channel")
            .values_list("source_channel", flat=True)
            .distinct()
        ),
    }


def build_operational_kpi_dashboard(raw_filters: dict | None = None) -> dict:
    sync_operational_metric_catalog()
    raw_filters = raw_filters or {}
    latest_snapshot = OperationalMetricSnapshot.objects.order_by("-date", "-generated_at").first()
    default_end = latest_snapshot.date if latest_snapshot else timezone.localdate()
    date_to = parse_dashboard_date(raw_filters.get("date_to"), field_name="date_to") or default_end
    date_from = parse_dashboard_date(raw_filters.get("date_from"), field_name="date_from") or date_to - timedelta(days=13)
    if date_from > date_to:
        raise ValueError("date_from must be on or before date_to.")

    ward_id = raw_filters.get("ward_id")
    try:
        parsed_ward_id = int(ward_id) if ward_id else None
    except (TypeError, ValueError) as error:
        raise ValueError("ward_id must be an integer.") from error
    ward = Ward.objects.filter(id=parsed_ward_id, is_active=True).first() if parsed_ward_id else None
    if parsed_ward_id and ward is None:
        raise ValueError("ward_id does not match an active dashboard ward.")

    filters = {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "ward_id": parsed_ward_id,
        "ward_name": ward.name if ward else "",
        "sub_county": (raw_filters.get("sub_county") or "").strip(),
        "source_channel": (raw_filters.get("source_channel") or "").strip().upper(),
    }

    definitions = list(
        OperationalMetricDefinition.objects.filter(
            is_active=True,
            metric_family=OperationalMetricDefinition.FAMILY_OPERATIONAL,
        ).order_by("metric_group", "metric_key")
    )
    definitions_by_key = {definition.metric_key: definition for definition in definitions}
    snapshots_queryset = OperationalMetricSnapshot.objects.select_related("metric_definition", "ward").filter(
        metric_definition__in=definitions,
        date__gte=date_from,
        date__lte=date_to,
    )
    snapshots_queryset = _apply_snapshot_filters(snapshots_queryset, filters)
    snapshots = list(snapshots_queryset.order_by("metric_definition__metric_key", "date", "generated_at", "id"))
    latest_by_metric = _latest_snapshots_by_metric(snapshots)
    latest_payloads = {
        definition.metric_key: _snapshot_payload(definition, latest_by_metric.get(definition.metric_key))
        for definition in definitions
    }

    grouped_status_counts: dict[str, int] = defaultdict(int)
    for item in latest_payloads.values():
        grouped_status_counts[item["status"]] += 1

    audit = build_operational_kpi_source_coverage_audit(
        as_of_date=date_to,
        stale_after_days=1,
        filters=filters,
    )
    source_warnings = _source_warning_payload(latest_by_metric, audit)
    interoperability_contracts = build_interoperability_operational_kpi_feed(as_of_date=date_to)
    source_warnings.extend(interoperability_contracts["source_coverage_warnings"])
    threshold_evaluation = evaluate_operational_kpi_thresholds(
        as_of_date=date_to,
        filters=filters,
        stale_after_days=1,
        persist=False,
    )
    threshold_alerts = threshold_evaluation["breaches"]
    complete_count = grouped_status_counts[OperationalMetricSnapshot.STATUS_COMPLETE]
    evaluable_count = len([item for item in latest_payloads.values() if item["status"] != "MISSING"])
    operational_health = "pass"
    if threshold_evaluation["critical_count"]:
        operational_health = "critical"
    elif source_warnings or threshold_alerts or complete_count != len(definitions):
        operational_health = "warning"

    latest_model_run = ModelRun.objects.order_by("-started_at").first()
    return {
        "schema_version": OPERATIONAL_KPI_DASHBOARD_SCHEMA_VERSION,
        "generated_at": timezone.now().isoformat(),
        "filters": filters,
        "available_filters": _available_filters(),
        "summary": {
            "metric_count": len(definitions),
            "snapshot_count": len(snapshots),
            "latest_snapshot_date": max((snapshot.date for snapshot in snapshots), default=None).isoformat() if snapshots else None,
            "complete_metric_count": complete_count,
            "evaluable_metric_count": evaluable_count,
            "warning_count": len(source_warnings),
            "threshold_alert_count": len(threshold_alerts),
            "critical_threshold_alert_count": threshold_evaluation["critical_count"],
            "warning_threshold_alert_count": threshold_evaluation["warning_count"],
            "status_counts": dict(grouped_status_counts),
            "operational_health": operational_health,
            "model_metric_count": OperationalMetricDefinition.objects.filter(
                is_active=True,
                metric_family=OperationalMetricDefinition.FAMILY_MODEL,
            ).count(),
        },
        "panels": {
            "operational_overview": [latest_payloads[key] for key in OPERATIONAL_OVERVIEW_KEYS if key in latest_payloads],
            "sla": [latest_payloads[key] for key in SLA_PANEL_KEYS if key in latest_payloads],
            "adoption_coverage": [latest_payloads[key] for key in ADOPTION_COVERAGE_KEYS if key in latest_payloads],
            "response_time_trends": _trend_series(
                definitions_by_key=definitions_by_key,
                snapshots=snapshots,
                metric_keys=RESPONSE_TIME_TREND_KEYS,
            ),
            "facility_preparedness_trends": _trend_series(
                definitions_by_key=definitions_by_key,
                snapshots=snapshots,
                metric_keys=FACILITY_TREND_KEYS,
            ),
            "ussd_completion_trends": _trend_series(
                definitions_by_key=definitions_by_key,
                snapshots=snapshots,
                metric_keys=USSD_TREND_KEYS,
            ),
            "model_vs_operations": {
                "separation_statement": "Operational KPIs measure delivery, adoption, response, and source health; model runs remain separate prediction artifacts.",
                "operational_metric_family": OperationalMetricDefinition.FAMILY_OPERATIONAL,
                "model_metric_family": OperationalMetricDefinition.FAMILY_MODEL,
                "latest_model_run": {
                    "model_version": latest_model_run.model_version if latest_model_run else None,
                    "status": latest_model_run.status if latest_model_run else None,
                    "started_at": latest_model_run.started_at.isoformat() if latest_model_run else None,
                    "completed_at": latest_model_run.completed_at.isoformat() if latest_model_run and latest_model_run.completed_at else None,
                    "evaluation_metrics": latest_model_run.evaluation_metrics if latest_model_run else {},
                },
                "operational_metric_groups": sorted({definition.metric_group for definition in definitions}),
            },
            "source_coverage_warnings": source_warnings,
            "threshold_alerts": threshold_alerts,
            "interoperability_contracts": interoperability_contracts,
        },
        "metrics": list(latest_payloads.values()),
    }
