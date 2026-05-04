from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import (
    Alert,
    AlertWorkflowState,
    CHV,
    CHVAssignment,
    CHVMessage,
    ETLHeartbeat,
    FacilityReadinessReview,
    FacilityReadinessReviewEvent,
    IngestionRun,
    OperationalBaselinePeriod,
    OperationalMetricDefinition,
    OperationalMetricSnapshot,
    PopulationExposureIngestionRun,
    PreparednessAction,
    SurveillanceIngestionRun,
    SurveillanceLabelWindow,
    SurveillanceOutbreakLabel,
    SyncQueue,
    TriageSession,
    UssdSessionLog,
)
from .operational_metrics import OPERATIONAL_KPI_DEFINITIONS, sync_operational_metric_catalog


OPERATIONAL_KPI_SNAPSHOT_SCHEMA_VERSION = "operational-kpi-snapshot-v1"
OPERATIONAL_KPI_AUDIT_SCHEMA_VERSION = "operational-kpi-source-coverage-audit-v1"
OPERATIONAL_KPI_BASELINE_COMPARISON_SCHEMA_VERSION = "operational-kpi-baseline-comparison-v1"


@dataclass
class MetricSnapshotDraft:
    metric_key: str
    value: Decimal | None
    numerator: Decimal | None = None
    denominator: Decimal | None = None
    status: str = OperationalMetricSnapshot.STATUS_COMPLETE
    source_record_count: int = 0
    source_coverage: dict = field(default_factory=dict)
    dimension_values: dict = field(default_factory=lambda: {"scope": "global"})
    county: str = ""
    sub_county: str = ""
    ward: object | None = None
    facility: object | None = None
    chv: object | None = None
    source_channel: str = ""
    action_type: str = ""
    alert_severity: str = ""
    model_version: str = ""
    grain: str = OperationalMetricSnapshot.GRAIN_DAILY


def parse_snapshot_date(value: str | None) -> date:
    if not value:
        return timezone.localdate()
    return date.fromisoformat(value)


def daily_period(snapshot_date: date) -> tuple[datetime, datetime]:
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(snapshot_date, time.min), tz)
    return start, start + timedelta(days=1)


def _decimal(value: int | float | Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def _percent(numerator: int | float, denominator: int | float) -> Decimal | None:
    if denominator == 0:
        return None
    return _decimal((float(numerator) / float(denominator)) * 100.0)


def _ratio(numerator: int | float, denominator: int | float) -> Decimal | None:
    if denominator == 0:
        return None
    return _decimal(float(numerator) / float(denominator))


def _percentile(values: list[float], percentile: float) -> Decimal | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return _decimal(ordered[0])
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return _decimal(ordered[int(position)])
    fraction = position - lower
    return _decimal(ordered[lower] + (ordered[upper] - ordered[lower]) * fraction)


def _source_coverage(
    *,
    metric_key: str,
    source_models: list[str],
    period_start: datetime,
    period_end: datetime,
    warnings: list[str] | None = None,
    details: dict | None = None,
) -> dict:
    return {
        "schema_version": "operational-kpi-source-coverage-v1",
        "metric_key": metric_key,
        "source_models": source_models,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "warnings": warnings or [],
        "details": details or {},
    }


def _definition_specs_by_key() -> dict[str, dict]:
    return {item["metric_key"]: item for item in OPERATIONAL_KPI_DEFINITIONS}


def _status_for(total: int, usable: int, warnings: list[str]) -> str:
    if total == 0:
        return OperationalMetricSnapshot.STATUS_NO_SOURCE
    if usable == 0 or warnings:
        return OperationalMetricSnapshot.STATUS_PARTIAL
    return OperationalMetricSnapshot.STATUS_COMPLETE


def _alert_latencies(period_start: datetime, period_end: datetime) -> tuple[list[float], int, list[str], dict]:
    alerts = list(
        Alert.objects.select_related("risk_score", "ward")
        .filter(created_at__gte=period_start, created_at__lt=period_end)
        .order_by("id")
    )
    latencies: list[float] = []
    missing_delivery_timestamp = 0
    negative_latency = 0
    for alert in alerts:
        if alert.status != Alert.STATUS_DELIVERED:
            continue
        if alert.sent_at is None:
            missing_delivery_timestamp += 1
            continue
        latency = (alert.sent_at - alert.created_at).total_seconds()
        if latency < 0:
            negative_latency += 1
            continue
        latencies.append(latency)

    warnings: list[str] = []
    if alerts and not latencies:
        warnings.append("no_delivered_alerts_with_usable_delivery_timestamp")
    if missing_delivery_timestamp:
        warnings.append("delivered_alerts_missing_sent_at")
    if negative_latency:
        warnings.append("delivered_alerts_with_negative_latency_excluded")
    details = {
        "alerts_in_window": len(alerts),
        "usable_delivered_alerts": len(latencies),
        "delivered_alerts_missing_sent_at": missing_delivery_timestamp,
        "delivered_alerts_with_negative_latency": negative_latency,
    }
    return latencies, len(alerts), warnings, details


def _build_alert_delivery_metric(metric_key: str, period_start: datetime, period_end: datetime) -> MetricSnapshotDraft:
    latencies, total, warnings, details = _alert_latencies(period_start, period_end)
    if metric_key == "alert_delivery_time_p50_seconds":
        value = _percentile(latencies, 0.50)
    elif metric_key == "alert_delivery_time_p95_seconds":
        value = _percentile(latencies, 0.95)
    else:
        under_5m = sum(1 for latency in latencies if latency <= 300)
        value = _percent(under_5m, len(latencies))
        details["delivered_under_5m"] = under_5m

    specs = _definition_specs_by_key()[metric_key]
    return MetricSnapshotDraft(
        metric_key=metric_key,
        value=value,
        numerator=_decimal(details.get("delivered_under_5m", len(latencies))),
        denominator=_decimal(len(latencies)) if metric_key == "alerts_delivered_under_5m_pct" else _decimal(1 if latencies else 0),
        status=_status_for(total, len(latencies), warnings),
        source_record_count=total,
        source_coverage=_source_coverage(
            metric_key=metric_key,
            source_models=specs["source_models"],
            period_start=period_start,
            period_end=period_end,
            warnings=warnings,
            details=details,
        ),
    )


def _build_trigger_activation_rate(period_start: datetime, period_end: datetime) -> MetricSnapshotDraft:
    workflows = list(
        AlertWorkflowState.objects.filter(
            last_evaluated_at__gte=period_start,
            last_evaluated_at__lt=period_end,
            trigger_severity__in=[AlertWorkflowState.SEVERITY_HIGH, AlertWorkflowState.SEVERITY_MEDIUM],
        ).order_by("id")
    )
    workflow_ids = [workflow.id for workflow in workflows]
    action_workflow_ids = set(
        PreparednessAction.objects.filter(
            alert_workflow_id__in=workflow_ids,
            created_at__gte=period_start,
            created_at__lt=period_end,
        ).values_list("alert_workflow_id", flat=True)
    )
    activated = [
        workflow
        for workflow in workflows
        if workflow.active_alert_count > 0
        or workflow.delivered_alert_count > 0
        or workflow.id in action_workflow_ids
        or workflow.status in {AlertWorkflowState.STATUS_DELIVERED, AlertWorkflowState.STATUS_QUEUED}
    ]
    warnings = [] if workflows else ["no_eligible_high_or_medium_workflows_in_window"]
    metric_key = "trigger_activation_rate"
    specs = _definition_specs_by_key()[metric_key]
    return MetricSnapshotDraft(
        metric_key=metric_key,
        value=_percent(len(activated), len(workflows)),
        numerator=_decimal(len(activated)),
        denominator=_decimal(len(workflows)),
        status=_status_for(len(workflows), len(workflows), []),
        source_record_count=len(workflows),
        source_coverage=_source_coverage(
            metric_key=metric_key,
            source_models=specs["source_models"],
            period_start=period_start,
            period_end=period_end,
            warnings=warnings,
            details={"eligible_workflows": len(workflows), "activated_workflows": len(activated)},
        ),
    )


def _action_queryset_for_period(period_start: datetime, period_end: datetime):
    return PreparednessAction.objects.select_related("ward", "facility", "chv", "risk_score").filter(
        Q(created_at__gte=period_start, created_at__lt=period_end)
        | Q(due_at__gte=period_start, due_at__lt=period_end)
        | Q(completed_at__gte=period_start, completed_at__lt=period_end)
    ).distinct()


def _build_action_acknowledgement_time(period_start: datetime, period_end: datetime) -> MetricSnapshotDraft:
    actions = list(_action_queryset_for_period(period_start, period_end).order_by("id"))
    latencies: list[float] = []
    invalid = 0
    for action in actions:
        if action.acknowledged_at is None:
            continue
        latency = (action.acknowledged_at - action.created_at).total_seconds()
        if latency < 0:
            invalid += 1
            continue
        latencies.append(latency)
    warnings = []
    if actions and not latencies:
        warnings.append("actions_missing_acknowledgement_timestamp")
    if invalid:
        warnings.append("actions_with_negative_acknowledgement_latency_excluded")
    metric_key = "action_acknowledgement_time_p50_seconds"
    specs = _definition_specs_by_key()[metric_key]
    return MetricSnapshotDraft(
        metric_key=metric_key,
        value=_percentile(latencies, 0.50),
        numerator=_decimal(len(latencies)),
        denominator=_decimal(len(actions)),
        status=_status_for(len(actions), len(latencies), warnings),
        source_record_count=len(actions),
        source_coverage=_source_coverage(
            metric_key=metric_key,
            source_models=specs["source_models"],
            period_start=period_start,
            period_end=period_end,
            warnings=warnings,
            details={"actions_in_window": len(actions), "acknowledged_actions": len(latencies)},
        ),
    )


def _build_action_completion_rate(period_start: datetime, period_end: datetime) -> MetricSnapshotDraft:
    actions = list(_action_queryset_for_period(period_start, period_end).order_by("id"))
    completed = [
        action
        for action in actions
        if action.status == PreparednessAction.STATUS_COMPLETED
        and action.completed_at is not None
        and bool(action.completion_evidence)
    ]
    warnings = [] if actions else ["no_due_created_or_closed_actions_in_window"]
    metric_key = "action_completion_rate"
    specs = _definition_specs_by_key()[metric_key]
    return MetricSnapshotDraft(
        metric_key=metric_key,
        value=_percent(len(completed), len(actions)),
        numerator=_decimal(len(completed)),
        denominator=_decimal(len(actions)),
        status=OperationalMetricSnapshot.STATUS_COMPLETE if actions else OperationalMetricSnapshot.STATUS_NO_SOURCE,
        source_record_count=len(actions),
        source_coverage=_source_coverage(
            metric_key=metric_key,
            source_models=specs["source_models"],
            period_start=period_start,
            period_end=period_end,
            warnings=warnings,
            details={"actions_in_denominator": len(actions), "completed_with_evidence": len(completed)},
        ),
    )


def _build_overdue_action_count(period_start: datetime, period_end: datetime) -> MetricSnapshotDraft:
    active_actions = PreparednessAction.objects.filter(status__in=PreparednessAction.ACTIVE_STATUSES)
    source_count = active_actions.count()
    total_actions = PreparednessAction.objects.count()
    overdue_count = active_actions.filter(Q(due_at__lt=period_end) | Q(sla_target_at__lt=period_end)).count()
    metric_key = "overdue_action_count"
    specs = _definition_specs_by_key()[metric_key]
    warnings = [] if total_actions else ["no_preparedness_action_records_available"]
    return MetricSnapshotDraft(
        metric_key=metric_key,
        value=_decimal(overdue_count),
        numerator=_decimal(overdue_count),
        denominator=_decimal(source_count),
        status=OperationalMetricSnapshot.STATUS_COMPLETE if total_actions else OperationalMetricSnapshot.STATUS_NO_SOURCE,
        source_record_count=source_count,
        source_coverage=_source_coverage(
            metric_key=metric_key,
            source_models=specs["source_models"],
            period_start=period_start,
            period_end=period_end,
            warnings=warnings,
            details={"total_actions": total_actions, "active_actions": source_count, "overdue_actions": overdue_count},
        ),
    )


def _build_facility_review_completion_rate(period_start: datetime, period_end: datetime) -> MetricSnapshotDraft:
    reviews = list(FacilityReadinessReview.objects.filter(created_at__gte=period_start, created_at__lt=period_end))
    review_ids = [review.id for review in reviews]
    closed_event_review_ids = set(
        FacilityReadinessReviewEvent.objects.filter(
            review_id__in=review_ids,
            action__in=[FacilityReadinessReviewEvent.ACTION_RESOLVED, FacilityReadinessReviewEvent.ACTION_DISMISSED],
        ).values_list("review_id", flat=True)
    )
    completed = [
        review
        for review in reviews
        if review.status in {FacilityReadinessReview.STATUS_RESOLVED, FacilityReadinessReview.STATUS_DISMISSED}
        and review.id in closed_event_review_ids
    ]
    metric_key = "facility_review_completion_rate"
    specs = _definition_specs_by_key()[metric_key]
    warnings = [] if reviews else ["no_facility_readiness_reviews_opened_in_window"]
    overdue_cutoff = period_end - timedelta(days=2)
    overdue_active_reviews = FacilityReadinessReview.objects.filter(
        status__in=FacilityReadinessReview.ACTIVE_STATUSES,
        created_at__lt=overdue_cutoff,
    ).count()
    if overdue_active_reviews:
        warnings.append("facility_readiness_review_overdue")
    return MetricSnapshotDraft(
        metric_key=metric_key,
        value=_percent(len(completed), len(reviews)),
        numerator=_decimal(len(completed)),
        denominator=_decimal(len(reviews)),
        status=OperationalMetricSnapshot.STATUS_PARTIAL if warnings and reviews else OperationalMetricSnapshot.STATUS_COMPLETE if reviews else OperationalMetricSnapshot.STATUS_NO_SOURCE,
        source_record_count=len(reviews),
        source_coverage=_source_coverage(
            metric_key=metric_key,
            source_models=specs["source_models"],
            period_start=period_start,
            period_end=period_end,
            warnings=warnings,
            details={
                "reviews_in_window": len(reviews),
                "closed_reviews_with_event": len(completed),
                "overdue_active_reviews": overdue_active_reviews,
                "overdue_cutoff": overdue_cutoff.isoformat(),
            },
        ),
    )


def _build_chv_active_use_rate(period_start: datetime, period_end: datetime) -> MetricSnapshotDraft:
    rolling_start = period_end - timedelta(days=7)
    active_chvs = list(CHV.objects.filter(is_active=True))
    active_ids = {item.id for item in active_chvs}
    active_phone_numbers = {item.phone_number for item in active_chvs if item.phone_number}
    used_ids = set(
        CHVAssignment.objects.filter(chv_id__in=active_ids, created_at__gte=rolling_start, created_at__lt=period_end).values_list(
            "chv_id", flat=True
        )
    )
    used_ids.update(
        CHVMessage.objects.filter(chv_id__in=active_ids, created_at__gte=rolling_start, created_at__lt=period_end).values_list(
            "chv_id", flat=True
        )
    )
    active_phones_with_sync = set(
        SyncQueue.objects.filter(
            phone_number__in=active_phone_numbers,
            created_at__gte=rolling_start,
            created_at__lt=period_end,
        ).values_list("phone_number", flat=True)
    )
    active_phones_with_triage = set(
        TriageSession.objects.filter(
            phone_number__in=active_phone_numbers,
            created_at__gte=rolling_start,
            created_at__lt=period_end,
        ).values_list("phone_number", flat=True)
    )
    used_ids.update(item.id for item in active_chvs if item.phone_number in active_phones_with_sync | active_phones_with_triage)
    metric_key = "chv_active_use_rate"
    specs = _definition_specs_by_key()[metric_key]
    warnings = [] if active_chvs else ["no_active_chv_roster_records"]
    if active_chvs and active_phone_numbers and not active_phones_with_sync:
        warnings.append("chv_sync_stale")
    return MetricSnapshotDraft(
        metric_key=metric_key,
        value=_percent(len(used_ids), len(active_chvs)),
        numerator=_decimal(len(used_ids)),
        denominator=_decimal(len(active_chvs)),
        status=OperationalMetricSnapshot.STATUS_PARTIAL if warnings and active_chvs else OperationalMetricSnapshot.STATUS_COMPLETE if active_chvs else OperationalMetricSnapshot.STATUS_NO_SOURCE,
        source_record_count=len(active_chvs),
        source_coverage=_source_coverage(
            metric_key=metric_key,
            source_models=specs["source_models"],
            period_start=rolling_start,
            period_end=period_end,
            warnings=warnings,
            details={
                "active_chvs": len(active_chvs),
                "active_use_chvs": len(used_ids),
                "active_phone_numbers": len(active_phone_numbers),
                "active_phones_with_sync": len(active_phones_with_sync),
            },
        ),
    )


def _build_ussd_completion_rate(period_start: datetime, period_end: datetime) -> MetricSnapshotDraft:
    logs = list(UssdSessionLog.objects.filter(created_at__gte=period_start, created_at__lt=period_end).order_by("session_id", "id"))
    sessions: dict[str, list[UssdSessionLog]] = {}
    for log in logs:
        sessions.setdefault(log.session_id, []).append(log)
    completed_sessions = 0
    invalid_option_sessions = 0
    abandoned_sessions = 0
    for session_logs in sessions.values():
        has_invalid_option = any(
            log.invalid_option
            or log.session_outcome == UssdSessionLog.OUTCOME_INVALID_INPUT
            or log.menu_level == "invalid"
            for log in session_logs
        )
        has_abandoned = any(log.session_outcome == UssdSessionLog.OUTCOME_ABANDONED_INFERRED for log in session_logs)
        has_completed = any(
            log.session_outcome == UssdSessionLog.OUTCOME_COMPLETED
            or (
                (log.response_text or "").strip().upper().startswith("END ")
                and log.menu_level not in {"invalid", "safe_fallback"}
                and log.session_outcome
                not in {
                    UssdSessionLog.OUTCOME_INVALID_INPUT,
                    UssdSessionLog.OUTCOME_SAFE_FALLBACK,
                    UssdSessionLog.OUTCOME_ABANDONED_INFERRED,
                }
            )
            for log in session_logs
        )
        invalid_option_sessions += int(has_invalid_option)
        abandoned_sessions += int(has_abandoned and not has_completed)
        if has_completed:
            completed_sessions += 1
    metric_key = "ussd_completion_rate"
    specs = _definition_specs_by_key()[metric_key]
    warnings = [] if sessions else ["no_ussd_session_logs_in_window"]
    invalid_option_rate = (invalid_option_sessions / len(sessions)) * 100 if sessions else 0
    abandonment_rate = (abandoned_sessions / len(sessions)) * 100 if sessions else 0
    if sessions and invalid_option_rate >= 25:
        warnings.append("ussd_invalid_option_spike")
    if sessions and abandonment_rate >= 25:
        warnings.append("ussd_abandonment_spike")
    return MetricSnapshotDraft(
        metric_key=metric_key,
        value=_percent(completed_sessions, len(sessions)),
        numerator=_decimal(completed_sessions),
        denominator=_decimal(len(sessions)),
        status=OperationalMetricSnapshot.STATUS_PARTIAL if warnings and sessions else OperationalMetricSnapshot.STATUS_COMPLETE if sessions else OperationalMetricSnapshot.STATUS_NO_SOURCE,
        source_record_count=len(logs),
        source_channel="USSD",
        source_coverage=_source_coverage(
            metric_key=metric_key,
            source_models=specs["source_models"],
            period_start=period_start,
            period_end=period_end,
            warnings=warnings,
            details={
                "ussd_log_rows": len(logs),
                "distinct_sessions": len(sessions),
                "completed_sessions": completed_sessions,
                "invalid_option_sessions": invalid_option_sessions,
                "abandoned_sessions": abandoned_sessions,
                "invalid_option_rate_pct": round(invalid_option_rate, 6),
                "abandonment_rate_pct": round(abandonment_rate, 6),
            },
        ),
    )


def _build_households_reached_count(period_start: datetime, period_end: datetime) -> MetricSnapshotDraft:
    delivered_chv_messages = CHVMessage.objects.filter(
        status=CHVMessage.STATUS_DELIVERED,
        created_at__gte=period_start,
        created_at__lt=period_end,
    ).count()
    completed_household_actions = PreparednessAction.objects.filter(
        action_type=PreparednessAction.ACTION_HOUSEHOLD_PREVENTION_MESSAGE,
        status=PreparednessAction.STATUS_COMPLETED,
        completed_at__gte=period_start,
        completed_at__lt=period_end,
    ).count()
    value = delivered_chv_messages + completed_household_actions
    source_count = CHVMessage.objects.filter(created_at__gte=period_start, created_at__lt=period_end).count() + PreparednessAction.objects.filter(
        action_type=PreparednessAction.ACTION_HOUSEHOLD_PREVENTION_MESSAGE,
        created_at__lt=period_end,
    ).count()
    metric_key = "households_reached_count"
    specs = _definition_specs_by_key()[metric_key]
    warnings = []
    if source_count == 0:
        warnings.append("no_household_reach_message_or_action_records")
    return MetricSnapshotDraft(
        metric_key=metric_key,
        value=_decimal(value),
        numerator=_decimal(value),
        denominator=_decimal(source_count),
        status=OperationalMetricSnapshot.STATUS_COMPLETE if source_count else OperationalMetricSnapshot.STATUS_NO_SOURCE,
        source_record_count=source_count,
        source_coverage=_source_coverage(
            metric_key=metric_key,
            source_models=specs["source_models"],
            period_start=period_start,
            period_end=period_end,
            warnings=warnings,
            details={
                "delivered_chv_messages": delivered_chv_messages,
                "completed_household_prevention_actions": completed_household_actions,
            },
        ),
    )


def _build_false_alerts_per_completed_response(period_start: datetime, period_end: datetime) -> MetricSnapshotDraft:
    rolling_start = period_end - timedelta(days=28)
    responses = list(
        PreparednessAction.objects.select_related("ward", "risk_score")
        .filter(
            status=PreparednessAction.STATUS_COMPLETED,
            completed_at__gte=rolling_start,
            completed_at__lt=period_end,
            source_trigger_type__in=[
                PreparednessAction.SOURCE_ALERT,
                PreparednessAction.SOURCE_ALERT_WORKFLOW,
                PreparednessAction.SOURCE_RISK_SCORE,
            ],
        )
        .order_by("id")
    )
    false_alerts = 0
    for action in responses:
        label_exists = SurveillanceLabelWindow.objects.filter(
            ward=action.ward,
            label_window_start__lte=period_end.date(),
            label_window_end__gte=rolling_start.date(),
            outbreak_label__in=[SurveillanceOutbreakLabel.ACTIVE, SurveillanceOutbreakLabel.WATCH],
        ).exists()
        if not label_exists:
            false_alerts += 1
    metric_key = "false_alerts_per_completed_response"
    specs = _definition_specs_by_key()[metric_key]
    warnings = [] if responses else ["no_completed_alert_driven_responses_in_mature_window"]
    return MetricSnapshotDraft(
        metric_key=metric_key,
        value=_ratio(false_alerts, len(responses)),
        numerator=_decimal(false_alerts),
        denominator=_decimal(len(responses)),
        status=_status_for(len(responses), len(responses), warnings if responses else []),
        source_record_count=len(responses),
        source_coverage=_source_coverage(
            metric_key=metric_key,
            source_models=specs["source_models"],
            period_start=rolling_start,
            period_end=period_end,
            warnings=warnings,
            details={"completed_alert_driven_responses": len(responses), "responses_without_label_evidence": false_alerts},
        ),
    )


def _build_missed_outbreak_without_action_count(period_start: datetime, period_end: datetime) -> MetricSnapshotDraft:
    rolling_start = period_end.date() - timedelta(days=28)
    active_labels = list(
        SurveillanceLabelWindow.objects.select_related("ward")
        .filter(
            outbreak_label=SurveillanceOutbreakLabel.ACTIVE,
            label_window_end__gte=rolling_start,
            label_window_end__lt=period_end.date() + timedelta(days=1),
        )
        .order_by("id")
    )
    missed = 0
    for label in active_labels:
        lead_start = timezone.make_aware(datetime.combine(label.label_window_start - timedelta(days=14), time.min), timezone.get_current_timezone())
        label_end = timezone.make_aware(datetime.combine(label.label_window_end + timedelta(days=1), time.min), timezone.get_current_timezone())
        has_alert = Alert.objects.filter(ward=label.ward, created_at__gte=lead_start, created_at__lt=label_end).exists()
        has_action = PreparednessAction.objects.filter(ward=label.ward, created_at__gte=lead_start, created_at__lt=label_end).exists()
        if not has_alert and not has_action:
            missed += 1
    metric_key = "missed_outbreak_without_action_count"
    specs = _definition_specs_by_key()[metric_key]
    warnings = [] if active_labels else ["no_active_outbreak_label_windows_in_mature_window"]
    return MetricSnapshotDraft(
        metric_key=metric_key,
        value=_decimal(missed),
        numerator=_decimal(missed),
        denominator=_decimal(len(active_labels)),
        status=OperationalMetricSnapshot.STATUS_COMPLETE if active_labels else OperationalMetricSnapshot.STATUS_NO_SOURCE,
        source_record_count=len(active_labels),
        source_coverage=_source_coverage(
            metric_key=metric_key,
            source_models=specs["source_models"],
            period_start=period_start,
            period_end=period_end,
            warnings=warnings,
            details={"active_label_windows": len(active_labels), "missed_without_alert_or_action": missed},
        ),
    )


def _latest_record_status(
    model,
    timestamp_field: str,
    status_field: str | None = None,
    *,
    as_of: datetime | None = None,
) -> tuple[bool, str | None, datetime | None]:
    queryset = model.objects.filter(**{f"{timestamp_field}__isnull": False})
    if as_of is not None:
        queryset = queryset.filter(**{f"{timestamp_field}__lte": as_of})
    latest = queryset.order_by(f"-{timestamp_field}", "-id").first()
    if latest is None:
        return False, None, None
    status = getattr(latest, status_field) if status_field else None
    return True, status, getattr(latest, timestamp_field)


def _build_source_data_freshness_pass_rate(period_start: datetime, period_end: datetime) -> MetricSnapshotDraft:
    freshness_cutoff = period_end - timedelta(days=2)
    feed_specs = [
        ("etl_heartbeat", ETLHeartbeat, "recorded_at", "status", {ETLHeartbeat.STATUS_OK, ETLHeartbeat.STATUS_WARN}),
        ("rainfall_ingestion", IngestionRun, "completed_at", "status", {IngestionRun.STATUS_SUCCESS, IngestionRun.STATUS_PARTIAL}),
        (
            "surveillance_ingestion",
            SurveillanceIngestionRun,
            "completed_at",
            "status",
            {SurveillanceIngestionRun.STATUS_SUCCESS, SurveillanceIngestionRun.STATUS_PARTIAL},
        ),
        (
            "population_exposure_ingestion",
            PopulationExposureIngestionRun,
            "completed_at",
            "status",
            {PopulationExposureIngestionRun.STATUS_SUCCESS, PopulationExposureIngestionRun.STATUS_PARTIAL},
        ),
    ]
    feed_details = {}
    passing = 0
    existing = 0
    warnings: list[str] = []
    for feed_key, model, timestamp_field, status_field, passing_statuses in feed_specs:
        has_record, status, timestamp_value = _latest_record_status(
            model,
            timestamp_field,
            status_field,
            as_of=period_end,
        )
        is_fresh = bool(timestamp_value and timestamp_value >= freshness_cutoff)
        is_passing = bool(has_record and is_fresh and status in passing_statuses)
        if has_record:
            existing += 1
        if is_passing:
            passing += 1
        else:
            warnings.append(f"{feed_key}_missing_stale_or_not_successful")
        feed_details[feed_key] = {
            "has_record": has_record,
            "status": status,
            "timestamp": timestamp_value.isoformat() if timestamp_value else None,
            "freshness_cutoff": freshness_cutoff.isoformat(),
            "passes": is_passing,
        }
    metric_key = "source_data_freshness_pass_rate"
    specs = _definition_specs_by_key()[metric_key]
    status = OperationalMetricSnapshot.STATUS_COMPLETE
    if existing == 0:
        status = OperationalMetricSnapshot.STATUS_NO_SOURCE
    elif warnings:
        status = OperationalMetricSnapshot.STATUS_PARTIAL
    return MetricSnapshotDraft(
        metric_key=metric_key,
        value=_percent(passing, len(feed_specs)),
        numerator=_decimal(passing),
        denominator=_decimal(len(feed_specs)),
        status=status,
        source_record_count=existing,
        source_coverage=_source_coverage(
            metric_key=metric_key,
            source_models=specs["source_models"],
            period_start=period_start,
            period_end=period_end,
            warnings=warnings,
            details={"feeds": feed_details},
        ),
    )


def build_metric_snapshot_drafts(snapshot_date: date, *, metric_keys: list[str] | None = None) -> list[MetricSnapshotDraft]:
    period_start, period_end = daily_period(snapshot_date)
    drafts = [
        _build_alert_delivery_metric("alert_delivery_time_p50_seconds", period_start, period_end),
        _build_alert_delivery_metric("alert_delivery_time_p95_seconds", period_start, period_end),
        _build_alert_delivery_metric("alerts_delivered_under_5m_pct", period_start, period_end),
        _build_trigger_activation_rate(period_start, period_end),
        _build_action_acknowledgement_time(period_start, period_end),
        _build_action_completion_rate(period_start, period_end),
        _build_overdue_action_count(period_start, period_end),
        _build_facility_review_completion_rate(period_start, period_end),
        _build_chv_active_use_rate(period_start, period_end),
        _build_ussd_completion_rate(period_start, period_end),
        _build_households_reached_count(period_start, period_end),
        _build_false_alerts_per_completed_response(period_start, period_end),
        _build_missed_outbreak_without_action_count(period_start, period_end),
        _build_source_data_freshness_pass_rate(period_start, period_end),
    ]
    if not metric_keys:
        return drafts
    requested = set(metric_keys)
    return [draft for draft in drafts if draft.metric_key in requested]


def _upsert_snapshot(
    *,
    definition: OperationalMetricDefinition,
    draft: MetricSnapshotDraft,
    snapshot_date: date,
    period_start: datetime,
    period_end: datetime,
    calculation_run_id: uuid.UUID,
) -> tuple[OperationalMetricSnapshot, bool]:
    candidate = OperationalMetricSnapshot(
        metric_definition=definition,
        date=snapshot_date,
        period_start=period_start,
        period_end=period_end,
        grain=draft.grain,
        dimension_values=draft.dimension_values,
        county=draft.county,
        sub_county=draft.sub_county,
        ward=draft.ward,
        facility=draft.facility,
        chv=draft.chv,
        source_channel=draft.source_channel,
        action_type=draft.action_type,
        alert_severity=draft.alert_severity,
        model_version=draft.model_version,
    )
    snapshot_key = candidate.compute_snapshot_key()
    snapshot, created = OperationalMetricSnapshot.objects.update_or_create(
        snapshot_key=snapshot_key,
        defaults={
            "metric_definition": definition,
            "date": snapshot_date,
            "period_start": period_start,
            "period_end": period_end,
            "grain": draft.grain,
            "value": draft.value,
            "numerator": draft.numerator,
            "denominator": draft.denominator,
            "value_unit": definition.value_unit,
            "status": draft.status,
            "source_record_count": draft.source_record_count,
            "source_coverage": draft.source_coverage,
            "dimension_values": draft.dimension_values,
            "county": draft.county,
            "sub_county": draft.sub_county,
            "ward": draft.ward,
            "facility": draft.facility,
            "chv": draft.chv,
            "source_channel": draft.source_channel,
            "action_type": draft.action_type,
            "alert_severity": draft.alert_severity,
            "model_version": draft.model_version,
            "calculation_run_id": calculation_run_id,
            "calculation_metadata": {
                "schema_version": OPERATIONAL_KPI_SNAPSHOT_SCHEMA_VERSION,
                "builder": "build_daily_operational_kpi_snapshots",
                "recalculation_idempotency_key": snapshot_key,
            },
            "generated_at": timezone.now(),
        },
    )
    return snapshot, created


@transaction.atomic
def build_daily_operational_kpi_snapshots(*, snapshot_date: date | None = None, metric_keys: list[str] | None = None) -> dict:
    sync_operational_metric_catalog()
    resolved_date = snapshot_date or timezone.localdate()
    period_start, period_end = daily_period(resolved_date)
    calculation_run_id = uuid.uuid4()
    definitions = {
        definition.metric_key: definition
        for definition in OperationalMetricDefinition.objects.filter(is_active=True, metric_family=OperationalMetricDefinition.FAMILY_OPERATIONAL)
    }
    created = 0
    updated = 0
    snapshots: list[dict] = []
    warnings: list[dict] = []
    all_known_metric_keys = {spec["metric_key"] for spec in OPERATIONAL_KPI_DEFINITIONS}
    requested_unknown_metric_keys = sorted(set(metric_keys or []) - all_known_metric_keys)
    for metric_key in requested_unknown_metric_keys:
        warnings.append({"metric_key": metric_key, "warning": "unknown_requested_metric_key"})

    for draft in build_metric_snapshot_drafts(resolved_date, metric_keys=metric_keys):
        definition = definitions.get(draft.metric_key)
        if definition is None:
            warnings.append({"metric_key": draft.metric_key, "warning": "missing_active_metric_definition"})
            continue
        snapshot, was_created = _upsert_snapshot(
            definition=definition,
            draft=draft,
            snapshot_date=resolved_date,
            period_start=period_start,
            period_end=period_end,
            calculation_run_id=calculation_run_id,
        )
        created += int(was_created)
        updated += int(not was_created)
        coverage_warnings = snapshot.source_coverage.get("warnings", [])
        for warning in coverage_warnings:
            warnings.append({"metric_key": snapshot.metric_definition.metric_key, "warning": warning})
        snapshots.append(
            {
                "snapshot_key": snapshot.snapshot_key,
                "metric_key": snapshot.metric_definition.metric_key,
                "status": snapshot.status,
                "value": snapshot.value,
                "source_record_count": snapshot.source_record_count,
                "warnings": coverage_warnings,
            }
        )
    return {
        "schema_version": OPERATIONAL_KPI_SNAPSHOT_SCHEMA_VERSION,
        "calculation_run_id": str(calculation_run_id),
        "date": resolved_date.isoformat(),
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "created": created,
        "updated": updated,
        "snapshot_count": len(snapshots),
        "metric_keys": metric_keys or sorted(all_known_metric_keys),
        "warnings": warnings,
        "snapshots": snapshots,
    }


def backfill_daily_operational_kpi_snapshots(*, start_date: date, end_date: date, metric_keys: list[str] | None = None) -> dict:
    if end_date < start_date:
        raise ValueError("end_date must be on or after start_date")
    results = []
    current = start_date
    while current <= end_date:
        results.append(build_daily_operational_kpi_snapshots(snapshot_date=current, metric_keys=metric_keys))
        current += timedelta(days=1)
    return {
        "schema_version": OPERATIONAL_KPI_SNAPSHOT_SCHEMA_VERSION,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "days": len(results),
        "created": sum(item["created"] for item in results),
        "updated": sum(item["updated"] for item in results),
        "snapshot_count": sum(item["snapshot_count"] for item in results),
        "warnings": [warning for item in results for warning in item["warnings"]],
        "results": results,
    }


def _normalise_snapshot_filter_args(filters: dict | None = None) -> dict:
    filters = filters or {}
    ward_id = filters.get("ward_id")
    if ward_id in (None, ""):
        parsed_ward_id = None
    else:
        try:
            parsed_ward_id = int(ward_id)
        except (TypeError, ValueError) as error:
            raise ValueError("ward_id must be an integer.") from error
    return {
        "ward_id": parsed_ward_id,
        "sub_county": (filters.get("sub_county") or "").strip(),
        "source_channel": (filters.get("source_channel") or "").strip().upper(),
    }


def _apply_snapshot_filters(queryset, filters: dict):
    if filters.get("ward_id"):
        queryset = queryset.filter(ward_id=filters["ward_id"])
    if filters.get("sub_county"):
        queryset = queryset.filter(sub_county__iexact=filters["sub_county"])
    if filters.get("source_channel"):
        queryset = queryset.filter(source_channel__iexact=filters["source_channel"])
    return queryset


def _has_scoped_snapshot_filters(filters: dict) -> bool:
    return bool(filters.get("ward_id") or filters.get("sub_county") or filters.get("source_channel"))


def _snapshot_dimension_payload(snapshot: OperationalMetricSnapshot) -> dict:
    payload = {
        "county": snapshot.county or "",
        "sub_county": snapshot.sub_county or "",
        "ward_id": snapshot.ward_id,
        "ward_name": snapshot.ward.name if snapshot.ward_id else "",
        "facility_id": snapshot.facility_id,
        "chv_id": snapshot.chv_id,
        "source_channel": snapshot.source_channel or "",
        "action_type": snapshot.action_type or "",
        "alert_severity": snapshot.alert_severity or "",
        "model_version": snapshot.model_version or "",
    }
    payload.update(snapshot.dimension_values or {})
    return payload


def _dimension_value_matches(actual, expected) -> bool:
    if isinstance(expected, list):
        return any(_dimension_value_matches(actual, item) for item in expected)
    if actual == expected:
        return True
    if actual in (None, "") or expected in (None, ""):
        return actual == expected
    return str(actual) == str(expected)


def operational_baseline_matches_snapshot(baseline: OperationalBaselinePeriod, snapshot: OperationalMetricSnapshot) -> bool:
    expected_dimensions = baseline.dimensions or {}
    if not expected_dimensions:
        return True
    snapshot_dimensions = _snapshot_dimension_payload(snapshot)
    return all(
        _dimension_value_matches(snapshot_dimensions.get(key), expected)
        for key, expected in expected_dimensions.items()
    )


def select_operational_baseline_for_snapshot(
    snapshot: OperationalMetricSnapshot,
) -> tuple[OperationalBaselinePeriod | None, int]:
    candidates = list(
        snapshot.metric_definition.baseline_periods.filter(
            status=OperationalBaselinePeriod.STATUS_ACTIVE,
            baseline_value__isnull=False,
            period_end__lte=snapshot.period_start,
        ).order_by("-period_end", "-updated_at")
    )
    matching = [
        baseline
        for baseline in candidates
        if operational_baseline_matches_snapshot(baseline, snapshot)
    ]
    matching.sort(
        key=lambda baseline: (
            len(baseline.dimensions or {}),
            baseline.period_end,
            baseline.updated_at,
        ),
        reverse=True,
    )
    return (matching[0] if matching else None, len(candidates))


def build_operational_kpi_source_coverage_audit(
    *,
    as_of_date: date | None = None,
    stale_after_days: int = 1,
    filters: dict | None = None,
) -> dict:
    sync_operational_metric_catalog()
    if stale_after_days < 0:
        raise ValueError("stale_after_days must be zero or greater.")
    resolved_date = as_of_date or timezone.localdate()
    stale_before = resolved_date - timedelta(days=stale_after_days)
    normalised_filters = _normalise_snapshot_filter_args(filters)
    scoped_filters = _has_scoped_snapshot_filters(normalised_filters)
    definitions = list(
        OperationalMetricDefinition.objects.filter(
            is_active=True,
            metric_family=OperationalMetricDefinition.FAMILY_OPERATIONAL,
        ).order_by("metric_key")
    )
    warnings: list[dict] = []
    latest_by_metric = {}
    for definition in definitions:
        snapshot_queryset = _apply_snapshot_filters(
            definition.snapshots.filter(date__lte=resolved_date),
            normalised_filters,
        )
        latest = snapshot_queryset.order_by("-date", "-generated_at").first()
        latest_by_metric[definition.metric_key] = latest
        if latest is None:
            if not scoped_filters:
                warnings.append({"metric_key": definition.metric_key, "warning": "metric_has_no_snapshots"})
            continue
        if latest.date < stale_before:
            warnings.append(
                {
                    "metric_key": definition.metric_key,
                    "warning": "stale_metric_window",
                    "latest_date": latest.date.isoformat(),
                    "stale_before": stale_before.isoformat(),
                }
            )
        if latest.status in {OperationalMetricSnapshot.STATUS_NO_SOURCE, OperationalMetricSnapshot.STATUS_PARTIAL, OperationalMetricSnapshot.STATUS_STALE}:
            warnings.append(
                {
                    "metric_key": definition.metric_key,
                    "warning": f"latest_snapshot_status_{latest.status.lower()}",
                    "snapshot_key": latest.snapshot_key,
                }
            )
        for source_warning in latest.source_coverage.get("warnings", []):
            warnings.append({"metric_key": definition.metric_key, "warning": source_warning, "snapshot_key": latest.snapshot_key})
    overall_status = "pass"
    if any(item["warning"] == "metric_has_no_snapshots" for item in warnings):
        overall_status = "fail"
    elif warnings:
        overall_status = "warning"
    return {
        "schema_version": OPERATIONAL_KPI_AUDIT_SCHEMA_VERSION,
        "overall_status": overall_status,
        "as_of_date": resolved_date.isoformat(),
        "stale_after_days": stale_after_days,
        "filters": normalised_filters,
        "record_totals": {
            "active_metric_definitions": len(definitions),
            "snapshots": _apply_snapshot_filters(
                OperationalMetricSnapshot.objects.filter(date__lte=resolved_date),
                normalised_filters,
            ).count(),
            "no_source_snapshots": _apply_snapshot_filters(
                OperationalMetricSnapshot.objects.filter(
                    date__lte=resolved_date,
                    status=OperationalMetricSnapshot.STATUS_NO_SOURCE,
                ),
                normalised_filters,
            ).count(),
            "partial_snapshots": _apply_snapshot_filters(
                OperationalMetricSnapshot.objects.filter(
                    date__lte=resolved_date,
                    status=OperationalMetricSnapshot.STATUS_PARTIAL,
                ),
                normalised_filters,
            ).count(),
        },
        "warnings": warnings,
        "latest_snapshots": [
            {
                "metric_key": definition.metric_key,
                "latest_date": latest_by_metric[definition.metric_key].date.isoformat() if latest_by_metric[definition.metric_key] else None,
                "status": latest_by_metric[definition.metric_key].status if latest_by_metric[definition.metric_key] else "missing",
            }
            for definition in definitions
        ],
    }


def compare_operational_kpis_to_baseline(
    *,
    as_of_date: date | None = None,
    metric_keys: list[str] | None = None,
    filters: dict | None = None,
) -> dict:
    sync_operational_metric_catalog()
    resolved_date = as_of_date or timezone.localdate()
    normalised_filters = _normalise_snapshot_filter_args(filters)
    definitions = OperationalMetricDefinition.objects.filter(
        is_active=True,
        metric_family=OperationalMetricDefinition.FAMILY_OPERATIONAL,
    )
    if metric_keys:
        definitions = definitions.filter(metric_key__in=metric_keys)
    comparisons = []
    warnings = []
    for definition in definitions.order_by("metric_key"):
        current_queryset = _apply_snapshot_filters(
            definition.snapshots.filter(date__lte=resolved_date),
            normalised_filters,
        )
        current = current_queryset.order_by("-date", "-generated_at").first()
        if current is None:
            warnings.append({"metric_key": definition.metric_key, "warning": "missing_current_snapshot"})
            comparisons.append({"metric_key": definition.metric_key, "status": "missing_current_snapshot"})
            continue
        baseline, active_baseline_count = select_operational_baseline_for_snapshot(current)
        if baseline is None or baseline.baseline_value is None:
            warning_code = "missing_active_baseline"
            if active_baseline_count:
                warning_code = "missing_dimension_matching_active_baseline"
            warnings.append({"metric_key": definition.metric_key, "warning": warning_code})
            comparisons.append(
                {
                    "metric_key": definition.metric_key,
                    "status": warning_code,
                    "current_value": current.value,
                    "current_snapshot_key": current.snapshot_key,
                    "current_dimensions": _snapshot_dimension_payload(current),
                }
            )
            continue
        if current.value is None:
            warnings.append({"metric_key": definition.metric_key, "warning": "current_snapshot_has_no_value"})
            comparisons.append(
                {
                    "metric_key": definition.metric_key,
                    "status": "current_snapshot_has_no_value",
                    "current_snapshot_key": current.snapshot_key,
                    "baseline_key": baseline.baseline_key,
                }
            )
            continue
        delta = current.value - baseline.baseline_value
        percent_change = _percent(delta, baseline.baseline_value) if baseline.baseline_value != 0 else None
        comparisons.append(
            {
                "metric_key": definition.metric_key,
                "status": "compared",
                "current_snapshot_key": current.snapshot_key,
                "current_date": current.date.isoformat(),
                "current_value": current.value,
                "current_dimensions": _snapshot_dimension_payload(current),
                "baseline_key": baseline.baseline_key,
                "baseline_value": baseline.baseline_value,
                "baseline_dimensions": baseline.dimensions,
                "delta": delta,
                "percent_change": percent_change,
                "value_unit": current.value_unit,
            }
        )
    return {
        "schema_version": OPERATIONAL_KPI_BASELINE_COMPARISON_SCHEMA_VERSION,
        "overall_status": "pass" if not warnings else "warning",
        "as_of_date": resolved_date.isoformat(),
        "filters": normalised_filters,
        "warnings": warnings,
        "comparisons": comparisons,
    }
