from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import (
    DashboardNotification,
    DashboardNotificationEvent,
    OperationalMetricDefinition,
    OperationalMetricSnapshot,
    OperationalSLAThreshold,
    OperationalThresholdBreach,
)
from .operational_metrics import sync_operational_metric_catalog


OPERATIONAL_THRESHOLD_SCHEMA_VERSION = "operational-kpi-threshold-evaluation-v1"
OPERATIONAL_THRESHOLD_CATALOG_SCHEMA_VERSION = "operational-kpi-threshold-catalog-v1"
OPERATIONAL_THRESHOLD_NOTIFICATION_PREFIX = "operational-threshold-breach:"

DEFAULT_OPERATIONAL_SLA_THRESHOLDS = [
    {
        "threshold_key": "alert-delivery-p95-under-5m",
        "metric_key": "alert_delivery_time_p95_seconds",
        "version": "v1",
        "display_name": "Alert delivery p95 under five minutes",
        "comparator": OperationalSLAThreshold.COMPARATOR_LTE,
        "target_value": "300.000000",
        "warning_value": "240.000000",
        "critical_value": "600.000000",
        "owner": "County EOC operations",
        "rationale": "High-risk alerts must reach operators fast enough for same-day action.",
    },
    {
        "threshold_key": "overdue-action-backlog-empty",
        "metric_key": "overdue_action_count",
        "version": "v1",
        "display_name": "No overdue response actions",
        "comparator": OperationalSLAThreshold.COMPARATOR_LTE,
        "target_value": "0.000000",
        "warning_value": "1.000000",
        "critical_value": "5.000000",
        "owner": "Response task owners",
        "rationale": "Preparedness actions past due require visible follow-up and escalation.",
    },
    {
        "threshold_key": "action-completion-rate-minimum",
        "metric_key": "action_completion_rate",
        "version": "v1",
        "display_name": "Action completion rate at least 85%",
        "comparator": OperationalSLAThreshold.COMPARATOR_GTE,
        "target_value": "85.000000",
        "warning_value": "70.000000",
        "critical_value": "50.000000",
        "owner": "Response task owners",
        "rationale": "Warnings only become useful when response tasks are closed with evidence.",
    },
    {
        "threshold_key": "chv-active-use-rate-minimum",
        "metric_key": "chv_active_use_rate",
        "version": "v1",
        "display_name": "CHV active-use rate at least 75%",
        "comparator": OperationalSLAThreshold.COMPARATOR_GTE,
        "target_value": "75.000000",
        "warning_value": "60.000000",
        "critical_value": "40.000000",
        "owner": "CHV coordination lead",
        "rationale": "Low CHV activity means household reach and field verification may not happen.",
    },
    {
        "threshold_key": "facility-review-completion-rate-minimum",
        "metric_key": "facility_review_completion_rate",
        "version": "v1",
        "display_name": "Facility review completion rate at least 90%",
        "comparator": OperationalSLAThreshold.COMPARATOR_GTE,
        "target_value": "90.000000",
        "warning_value": "75.000000",
        "critical_value": "50.000000",
        "owner": "Facility preparedness lead",
        "rationale": "Readiness reviews must move quickly enough to surface facility constraints.",
    },
    {
        "threshold_key": "ussd-completion-rate-minimum",
        "metric_key": "ussd_completion_rate",
        "version": "v1",
        "display_name": "USSD completion rate at least 80%",
        "comparator": OperationalSLAThreshold.COMPARATOR_GTE,
        "target_value": "80.000000",
        "warning_value": "65.000000",
        "critical_value": "50.000000",
        "owner": "Digital engagement lead",
        "rationale": "Incomplete USSD sessions weaken triage, referral, and prevention messaging coverage.",
    },
    {
        "threshold_key": "source-freshness-pass-rate-complete",
        "metric_key": "source_data_freshness_pass_rate",
        "version": "v1",
        "display_name": "All operational KPI sources fresh",
        "comparator": OperationalSLAThreshold.COMPARATOR_GTE,
        "target_value": "100.000000",
        "warning_value": "75.000000",
        "critical_value": "50.000000",
        "owner": "Data engineering",
        "rationale": "Operational KPIs are not trustworthy when source feeds are missing or stale.",
    },
]

SOURCE_WARNING_SEVERITY = {
    "delivered_alerts_missing_sent_at": OperationalThresholdBreach.SEVERITY_WARNING,
    "delivered_alerts_with_negative_latency_excluded": OperationalThresholdBreach.SEVERITY_CRITICAL,
    "chv_sync_stale": OperationalThresholdBreach.SEVERITY_WARNING,
    "facility_readiness_review_overdue": OperationalThresholdBreach.SEVERITY_WARNING,
    "ussd_invalid_option_spike": OperationalThresholdBreach.SEVERITY_WARNING,
    "stale_metric_window": OperationalThresholdBreach.SEVERITY_CRITICAL,
    "metric_has_no_snapshots": OperationalThresholdBreach.SEVERITY_CRITICAL,
    "latest_snapshot_status_failed": OperationalThresholdBreach.SEVERITY_CRITICAL,
    "latest_snapshot_status_stale": OperationalThresholdBreach.SEVERITY_CRITICAL,
    "latest_snapshot_status_no_source": OperationalThresholdBreach.SEVERITY_WARNING,
    "latest_snapshot_status_partial": OperationalThresholdBreach.SEVERITY_WARNING,
}


def _decimal(value: str | int | float | Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value)).quantize(Decimal("0.000001"))


def _number(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _format_observed(value: Decimal | None, unit: str) -> str:
    if value is None:
        return "no value"
    numeric = float(value)
    if unit == "seconds":
        if numeric >= 3600:
            return f"{numeric / 3600:.1f} hr"
        if numeric >= 60:
            return f"{numeric / 60:.1f} min"
        return f"{numeric:.0f} sec"
    if unit == "percent":
        return f"{numeric:.1f}%"
    return f"{numeric:,.0f} {unit}".strip()


def _passes_target(value: Decimal, comparator: str, target: Decimal) -> bool:
    if comparator == OperationalSLAThreshold.COMPARATOR_LTE:
        return value <= target
    if comparator == OperationalSLAThreshold.COMPARATOR_LT:
        return value < target
    if comparator == OperationalSLAThreshold.COMPARATOR_GTE:
        return value >= target
    if comparator == OperationalSLAThreshold.COMPARATOR_GT:
        return value > target
    raise ValueError(f"Unsupported operational SLA comparator: {comparator}")


def _crosses_bad_boundary(value: Decimal, comparator: str, boundary: Decimal | None) -> bool:
    if boundary is None:
        return False
    if comparator in {OperationalSLAThreshold.COMPARATOR_LTE, OperationalSLAThreshold.COMPARATOR_LT}:
        return value >= boundary
    if comparator in {OperationalSLAThreshold.COMPARATOR_GTE, OperationalSLAThreshold.COMPARATOR_GT}:
        return value <= boundary
    raise ValueError(f"Unsupported operational SLA comparator: {comparator}")


def _threshold_state(snapshot: OperationalMetricSnapshot, threshold: OperationalSLAThreshold) -> tuple[str, str] | None:
    if snapshot.value is None:
        return None

    value = snapshot.value
    if _crosses_bad_boundary(value, threshold.comparator, threshold.critical_value):
        return OperationalThresholdBreach.SEVERITY_CRITICAL, OperationalThresholdBreach.BREACH_THRESHOLD_BREACH
    if not _passes_target(value, threshold.comparator, threshold.target_value):
        return OperationalThresholdBreach.SEVERITY_WARNING, OperationalThresholdBreach.BREACH_THRESHOLD_BREACH
    if _crosses_bad_boundary(value, threshold.comparator, threshold.warning_value):
        return OperationalThresholdBreach.SEVERITY_WARNING, OperationalThresholdBreach.BREACH_THRESHOLD_WARNING
    return None


def _dimension_value(snapshot: OperationalMetricSnapshot, key: str):
    if key == "ward_id":
        return snapshot.ward_id
    if key == "ward_name":
        return snapshot.ward.name if snapshot.ward_id else ""
    if key == "facility_id":
        return snapshot.facility_id
    if key == "chv_id":
        return snapshot.chv_id
    if hasattr(snapshot, key):
        return getattr(snapshot, key)
    return (snapshot.dimension_values or {}).get(key)


def _threshold_applies_to_snapshot(threshold: OperationalSLAThreshold, snapshot: OperationalMetricSnapshot) -> bool:
    dimensions = threshold.applies_to_dimensions or {}
    for key, expected in dimensions.items():
        actual = _dimension_value(snapshot, key)
        if isinstance(expected, list):
            if actual not in expected:
                return False
        elif actual != expected:
            return False
    return True


def operational_threshold_applies_to_snapshot(
    threshold: OperationalSLAThreshold,
    snapshot: OperationalMetricSnapshot,
) -> bool:
    return _threshold_applies_to_snapshot(threshold, snapshot)


def _apply_snapshot_filters(queryset, filters: dict | None):
    if not filters:
        return queryset
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


def _scoped_filters_applied(filters: dict | None) -> bool:
    if not filters:
        return False
    return bool(filters.get("ward_id") or filters.get("sub_county") or filters.get("source_channel"))


def _latest_snapshot_for_definition(
    definition: OperationalMetricDefinition,
    *,
    as_of_date: date,
    filters: dict | None,
) -> OperationalMetricSnapshot | None:
    queryset = OperationalMetricSnapshot.objects.select_related("metric_definition", "ward").filter(
        metric_definition=definition,
        date__lte=as_of_date,
    )
    queryset = _apply_snapshot_filters(queryset, filters)
    return queryset.order_by("-date", "-generated_at", "-id").first()


def _attribution(
    *,
    definition: OperationalMetricDefinition,
    snapshot: OperationalMetricSnapshot | None,
    threshold: OperationalSLAThreshold | None = None,
    warning_code: str = "",
) -> dict:
    return {
        "schema_version": OPERATIONAL_THRESHOLD_SCHEMA_VERSION,
        "metric_key": definition.metric_key,
        "metric_version": definition.version,
        "metric_group": definition.metric_group,
        "metric_owner": definition.owner,
        "threshold_key": threshold.threshold_key if threshold else "",
        "threshold_version": threshold.version if threshold else "",
        "threshold_owner": threshold.owner if threshold else "",
        "snapshot_key": snapshot.snapshot_key if snapshot else "",
        "snapshot_date": snapshot.date.isoformat() if snapshot else "",
        "source_record_count": snapshot.source_record_count if snapshot else 0,
        "warning_code": warning_code,
        "ward_id": snapshot.ward_id if snapshot else None,
        "ward_name": snapshot.ward.name if snapshot and snapshot.ward_id else "",
        "county": snapshot.county if snapshot else "",
        "sub_county": snapshot.sub_county if snapshot else "",
        "source_channel": snapshot.source_channel if snapshot else "",
        "dimension_values": snapshot.dimension_values if snapshot else {},
    }


def _candidate_payload(
    *,
    definition: OperationalMetricDefinition,
    as_of_date: date,
    breach_type: str,
    severity: str,
    title: str,
    body: str,
    snapshot: OperationalMetricSnapshot | None = None,
    threshold: OperationalSLAThreshold | None = None,
    warning_code: str = "",
) -> dict:
    return {
        "metric_definition": definition,
        "threshold": threshold,
        "snapshot": snapshot,
        "ward": snapshot.ward if snapshot and snapshot.ward_id else None,
        "breach_type": breach_type,
        "severity": severity,
        "status": OperationalThresholdBreach.STATUS_ACTIVE,
        "date": snapshot.date if snapshot else as_of_date,
        "title": title,
        "body": body,
        "warning_code": warning_code,
        "observed_value": snapshot.value if snapshot else None,
        "observed_status": snapshot.status if snapshot else "",
        "observed_unit": snapshot.value_unit if snapshot else definition.value_unit,
        "comparator": threshold.comparator if threshold else "",
        "target_value": threshold.target_value if threshold else None,
        "warning_value": threshold.warning_value if threshold else None,
        "critical_value": threshold.critical_value if threshold else None,
        "threshold_key_snapshot": threshold.threshold_key if threshold else "",
        "threshold_version_snapshot": threshold.version if threshold else "",
        "metric_key_snapshot": definition.metric_key,
        "metric_version_snapshot": definition.version,
        "dimension_values": snapshot.dimension_values if snapshot else {},
        "source_coverage": snapshot.source_coverage if snapshot else {},
        "attribution": _attribution(
            definition=definition,
            snapshot=snapshot,
            threshold=threshold,
            warning_code=warning_code,
        ),
        "evaluation_metadata": {
            "schema_version": OPERATIONAL_THRESHOLD_SCHEMA_VERSION,
            "as_of_date": as_of_date.isoformat(),
            "evaluator": "evaluate_operational_kpi_thresholds",
        },
        "last_seen_at": timezone.now(),
        "resolved_at": None,
    }


def _serialize_candidate(candidate: dict, breach: OperationalThresholdBreach | None = None) -> dict:
    threshold = candidate["threshold"]
    snapshot = candidate["snapshot"]
    return {
        "public_id": str(breach.public_id) if breach else None,
        "breach_key": breach.breach_key if breach else None,
        "metric_key": candidate["metric_key_snapshot"],
        "metric_version": candidate["metric_version_snapshot"],
        "display_name": candidate["metric_definition"].display_name,
        "breach_type": candidate["breach_type"],
        "severity": candidate["severity"],
        "status": candidate["status"],
        "title": candidate["title"],
        "body": candidate["body"],
        "date": candidate["date"].isoformat(),
        "warning_code": candidate["warning_code"],
        "observed_value": _number(candidate["observed_value"]),
        "observed_display_value": _format_observed(candidate["observed_value"], candidate["observed_unit"]),
        "observed_status": candidate["observed_status"],
        "observed_unit": candidate["observed_unit"],
        "snapshot_key": snapshot.snapshot_key if snapshot else None,
        "threshold": {
            "threshold_key": threshold.threshold_key,
            "version": threshold.version,
            "display_name": threshold.display_name,
            "comparator": threshold.comparator,
            "target_value": _number(threshold.target_value),
            "warning_value": _number(threshold.warning_value),
            "critical_value": _number(threshold.critical_value),
            "value_unit": threshold.value_unit,
        }
        if threshold
        else None,
        "attribution": candidate["attribution"],
        "first_seen_at": breach.first_seen_at.isoformat() if breach else None,
        "last_seen_at": breach.last_seen_at.isoformat() if breach else None,
        "resolved_at": breach.resolved_at.isoformat() if breach and breach.resolved_at else None,
    }


def _candidate_to_breach_key(candidate: dict) -> str:
    breach = OperationalThresholdBreach(**candidate)
    return breach.compute_breach_key()


@transaction.atomic
def sync_operational_sla_threshold_catalog() -> dict:
    sync_operational_metric_catalog()
    definitions = {
        definition.metric_key: definition
        for definition in OperationalMetricDefinition.objects.filter(metric_family=OperationalMetricDefinition.FAMILY_OPERATIONAL)
    }
    synced = 0
    skipped: list[dict] = []
    for spec in DEFAULT_OPERATIONAL_SLA_THRESHOLDS:
        definition = definitions.get(spec["metric_key"])
        if definition is None:
            skipped.append({"threshold_key": spec["threshold_key"], "reason": "missing_metric_definition"})
            continue
        if spec.get("is_active", True):
            OperationalSLAThreshold.objects.filter(
                threshold_key=spec["threshold_key"],
                is_active=True,
            ).exclude(version=spec["version"]).update(is_active=False, effective_to=timezone.now())
        defaults = {
            "metric_definition": definition,
            "display_name": spec["display_name"],
            "comparator": spec["comparator"],
            "target_value": _decimal(spec["target_value"]),
            "warning_value": _decimal(spec.get("warning_value")),
            "critical_value": _decimal(spec.get("critical_value")),
            "value_unit": spec.get("value_unit") or definition.value_unit,
            "applies_to_dimensions": spec.get("applies_to_dimensions", {}),
            "owner": spec["owner"],
            "rationale": spec["rationale"],
            "is_active": spec.get("is_active", True),
            "metadata": {
                "schema_version": OPERATIONAL_THRESHOLD_CATALOG_SCHEMA_VERSION,
                "phase": "child_plan_4_phase_4",
                **spec.get("metadata", {}),
            },
        }
        threshold, _ = OperationalSLAThreshold.objects.update_or_create(
            threshold_key=spec["threshold_key"],
            version=spec["version"],
            defaults=defaults,
        )
        if threshold.is_active:
            OperationalSLAThreshold.objects.filter(
                threshold_key=threshold.threshold_key,
                is_active=True,
            ).exclude(pk=threshold.pk).update(is_active=False, effective_to=threshold.effective_from)
        synced += 1
    return {
        "schema_version": OPERATIONAL_THRESHOLD_CATALOG_SCHEMA_VERSION,
        "synced": synced,
        "skipped": skipped,
    }


def _threshold_candidates_for_snapshot(
    *,
    definition: OperationalMetricDefinition,
    snapshot: OperationalMetricSnapshot,
    thresholds: list[OperationalSLAThreshold],
    as_of_date: date,
) -> list[dict]:
    candidates = []
    for threshold in thresholds:
        if not _threshold_applies_to_snapshot(threshold, snapshot):
            continue
        state = _threshold_state(snapshot, threshold)
        if state is None:
            continue
        severity, breach_type = state
        title = f"{definition.display_name}: threshold warning"
        if severity == OperationalThresholdBreach.SEVERITY_CRITICAL:
            title = f"{definition.display_name}: critical threshold breach"
        elif breach_type == OperationalThresholdBreach.BREACH_THRESHOLD_BREACH:
            title = f"{definition.display_name}: threshold breach"
        body = (
            f"Observed {_format_observed(snapshot.value, snapshot.value_unit)} against "
            f"{threshold.display_name} ({threshold.comparator} {_format_observed(threshold.target_value, threshold.value_unit)})."
        )
        candidates.append(
            _candidate_payload(
                definition=definition,
                threshold=threshold,
                snapshot=snapshot,
                as_of_date=as_of_date,
                breach_type=breach_type,
                severity=severity,
                title=title,
                body=body,
            )
        )
    return candidates


def _status_candidates_for_snapshot(
    *,
    definition: OperationalMetricDefinition,
    snapshot: OperationalMetricSnapshot,
    as_of_date: date,
    stale_before: date,
) -> list[dict]:
    candidates = []
    if snapshot.date < stale_before:
        warning_code = "stale_metric_window"
        candidates.append(
            _candidate_payload(
                definition=definition,
                snapshot=snapshot,
                as_of_date=as_of_date,
                breach_type=OperationalThresholdBreach.BREACH_SNAPSHOT_STALE,
                severity=SOURCE_WARNING_SEVERITY[warning_code],
                title=f"{definition.display_name}: KPI snapshot stale",
                body=f"Latest KPI snapshot is {snapshot.date.isoformat()}, older than the required freshness window.",
                warning_code=warning_code,
            )
        )

    if snapshot.status != OperationalMetricSnapshot.STATUS_COMPLETE:
        warning_code = f"latest_snapshot_status_{snapshot.status.lower()}"
        candidates.append(
            _candidate_payload(
                definition=definition,
                snapshot=snapshot,
                as_of_date=as_of_date,
                breach_type=OperationalThresholdBreach.BREACH_STATUS_WARNING,
                severity=SOURCE_WARNING_SEVERITY.get(warning_code, OperationalThresholdBreach.SEVERITY_WARNING),
                title=f"{definition.display_name}: snapshot status {snapshot.status.lower()}",
                body="The latest KPI snapshot is not complete and should be reviewed before operational interpretation.",
                warning_code=warning_code,
            )
        )

    for warning_code in snapshot.source_coverage.get("warnings", []):
        candidates.append(
            _candidate_payload(
                definition=definition,
                snapshot=snapshot,
                as_of_date=as_of_date,
                breach_type=OperationalThresholdBreach.BREACH_SOURCE_WARNING,
                severity=SOURCE_WARNING_SEVERITY.get(warning_code, OperationalThresholdBreach.SEVERITY_WARNING),
                title=f"{definition.display_name}: {warning_code.replace('_', ' ')}",
                body="The KPI source coverage emitted a warning that affects operational interpretation.",
                warning_code=warning_code,
            )
        )
    return candidates


def _missing_snapshot_candidate(definition: OperationalMetricDefinition, *, as_of_date: date) -> dict:
    warning_code = "metric_has_no_snapshots"
    return _candidate_payload(
        definition=definition,
        snapshot=None,
        as_of_date=as_of_date,
        breach_type=OperationalThresholdBreach.BREACH_MISSING_SNAPSHOT,
        severity=SOURCE_WARNING_SEVERITY[warning_code],
        title=f"{definition.display_name}: KPI snapshot missing",
        body="No operational KPI snapshot exists for this metric, so threshold status cannot be evaluated.",
        warning_code=warning_code,
    )


def _persist_candidates(candidates: list[dict], *, definitions: list[OperationalMetricDefinition], resolve_existing: bool) -> tuple[list[dict], dict]:
    persisted_payloads = []
    active_keys: set[str] = set()
    created = 0
    updated = 0
    now = timezone.now()
    for candidate in candidates:
        breach_key = _candidate_to_breach_key(candidate)
        active_keys.add(breach_key)
        defaults = {
            **candidate,
            "breach_key": breach_key,
            "last_seen_at": now,
            "status": OperationalThresholdBreach.STATUS_ACTIVE,
            "resolved_at": None,
        }
        breach, was_created = OperationalThresholdBreach.objects.update_or_create(
            breach_key=breach_key,
            defaults=defaults,
        )
        created += int(was_created)
        updated += int(not was_created)
        persisted_payloads.append(_serialize_candidate(candidate, breach))

    resolved = 0
    if resolve_existing:
        queryset = OperationalThresholdBreach.objects.filter(
            metric_definition__in=definitions,
            status=OperationalThresholdBreach.STATUS_ACTIVE,
        )
        if active_keys:
            queryset = queryset.exclude(breach_key__in=active_keys)
        for breach in queryset:
            breach.status = OperationalThresholdBreach.STATUS_RESOLVED
            breach.resolved_at = now
            breach.save(update_fields=["status", "resolved_at", "updated_at"])
            resolved += 1

    return persisted_payloads, {"created": created, "updated": updated, "resolved": resolved, "active_keys": active_keys}


def _sync_threshold_notifications(active_breaches):
    from .notifications import _upsert_notification, transition_notification

    active_notification_keys = set()
    for breach in active_breaches:
        external_key = f"{OPERATIONAL_THRESHOLD_NOTIFICATION_PREFIX}{breach.breach_key}"
        active_notification_keys.add(external_key)
        _upsert_notification(
            external_key=external_key,
            defaults={
                "type": DashboardNotification.TYPE_OPERATIONAL_KPI_THRESHOLD,
                "severity": (
                    DashboardNotification.SEVERITY_CRITICAL
                    if breach.severity == OperationalThresholdBreach.SEVERITY_CRITICAL
                    else DashboardNotification.SEVERITY_WARNING
                ),
                "title": breach.title,
                "body": breach.body,
                "source_system": "operational_metrics",
                "source_object_type": "operational_threshold_breach",
                "source_object_id": str(breach.public_id),
                "href": "/operational-metrics",
                "recipient_scope": DashboardNotification.SCOPE_WARD if breach.ward_id else DashboardNotification.SCOPE_GLOBAL,
                "ward": breach.ward,
                "recipient_role": "",
                "requires_acknowledgement": breach.severity == OperationalThresholdBreach.SEVERITY_CRITICAL,
                "dismissible": breach.severity != OperationalThresholdBreach.SEVERITY_CRITICAL,
                "auto_resolve": True,
                "pinned_until_actioned": breach.severity == OperationalThresholdBreach.SEVERITY_CRITICAL,
                "metadata": {
                    "breach_public_id": str(breach.public_id),
                    "breach_key": breach.breach_key,
                    "metric_key": breach.metric_key_snapshot,
                    "threshold_key": breach.threshold_key_snapshot,
                    "breach_type": breach.breach_type,
                    "warning_code": breach.warning_code,
                    "attribution": breach.attribution,
                },
            },
        )

    queryset = DashboardNotification.objects.filter(
        type=DashboardNotification.TYPE_OPERATIONAL_KPI_THRESHOLD,
        external_key__startswith=OPERATIONAL_THRESHOLD_NOTIFICATION_PREFIX,
    ).exclude(state__in=[DashboardNotification.STATE_RESOLVED, DashboardNotification.STATE_EXPIRED])
    if active_notification_keys:
        queryset = queryset.exclude(external_key__in=active_notification_keys)
    for notification in queryset:
        transition_notification(notification, DashboardNotificationEvent.ACTION_RESOLVED)


def evaluate_operational_kpi_thresholds(
    *,
    as_of_date: date | None = None,
    filters: dict | None = None,
    stale_after_days: int = 1,
    persist: bool = False,
    notify: bool = False,
    resolve_existing: bool = True,
) -> dict:
    sync_operational_sla_threshold_catalog()
    resolved_date = as_of_date or timezone.localdate()
    stale_before = resolved_date - timedelta(days=stale_after_days)
    definitions = list(
        OperationalMetricDefinition.objects.filter(
            is_active=True,
            metric_family=OperationalMetricDefinition.FAMILY_OPERATIONAL,
        ).order_by("metric_key")
    )
    thresholds_by_metric: dict[int, list[OperationalSLAThreshold]] = {}
    for threshold in OperationalSLAThreshold.objects.select_related("metric_definition").filter(
        is_active=True,
        metric_definition__in=definitions,
        effective_from__lte=timezone.now(),
    ).filter(Q(effective_to__isnull=True) | Q(effective_to__gt=timezone.now())):
        thresholds_by_metric.setdefault(threshold.metric_definition_id, []).append(threshold)

    candidates: list[dict] = []
    scoped_filters = _scoped_filters_applied(filters)
    for definition in definitions:
        snapshot = _latest_snapshot_for_definition(definition, as_of_date=resolved_date, filters=filters)
        if snapshot is None:
            if not scoped_filters:
                candidates.append(_missing_snapshot_candidate(definition, as_of_date=resolved_date))
            continue
        candidates.extend(
            _threshold_candidates_for_snapshot(
                definition=definition,
                snapshot=snapshot,
                thresholds=thresholds_by_metric.get(definition.id, []),
                as_of_date=resolved_date,
            )
        )
        candidates.extend(
            _status_candidates_for_snapshot(
                definition=definition,
                snapshot=snapshot,
                as_of_date=resolved_date,
                stale_before=stale_before,
            )
        )

    serialized = [_serialize_candidate(candidate) for candidate in candidates]
    persistence = {"created": 0, "updated": 0, "resolved": 0, "active_keys": set()}
    if persist:
        serialized, persistence = _persist_candidates(
            candidates,
            definitions=definitions,
            resolve_existing=resolve_existing and not scoped_filters,
        )
        if notify:
            active_breaches = OperationalThresholdBreach.objects.filter(
                breach_key__in=persistence["active_keys"],
                status=OperationalThresholdBreach.STATUS_ACTIVE,
            ).select_related("ward")
            _sync_threshold_notifications(active_breaches)

    critical_count = sum(1 for item in serialized if item["severity"] == OperationalThresholdBreach.SEVERITY_CRITICAL)
    warning_count = sum(1 for item in serialized if item["severity"] == OperationalThresholdBreach.SEVERITY_WARNING)
    return {
        "schema_version": OPERATIONAL_THRESHOLD_SCHEMA_VERSION,
        "as_of_date": resolved_date.isoformat(),
        "stale_after_days": stale_after_days,
        "persisted": persist,
        "created": persistence["created"],
        "updated": persistence["updated"],
        "resolved": persistence["resolved"],
        "active_count": len(serialized),
        "critical_count": critical_count,
        "warning_count": warning_count,
        "overall_status": "critical" if critical_count else "warning" if warning_count else "pass",
        "breaches": sorted(serialized, key=lambda item: (item["severity"] != OperationalThresholdBreach.SEVERITY_CRITICAL, item["metric_key"])),
    }
