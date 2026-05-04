from __future__ import annotations

from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

from risk.models import (
    Alert,
    ModelChampionChallengerComparison,
    ModelMonitoringSnapshot,
    ModelMonitoringState,
    ModelRegistryEntry,
    ModelRegistryMonitoringState,
    ModelRegistryPromotionState,
    ModelRetrainingRecommendation,
    ModelRetrainingRecommendationState,
    ModelRollbackEvent,
    ModelRun,
)

from .alignment import (
    PROMOTION_TARGET_BENCHMARK_ONLY,
    model_run_has_phase_4_promotion_metadata,
    registry_entry_has_promotion_event_provenance,
)
from .registry import (
    AUTHORIZED_ROLLBACK_ROLES,
    DEFAULT_MODEL_REVIEW_INTERVAL_DAYS,
    MODEL_ROLLBACK_WORKFLOW_SCHEMA_VERSION,
    active_model_registry_entry,
    promoted_model_runs_from_phase_4_metadata,
)


MODEL_OPERATIONS_AUDIT_SCHEMA_VERSION = "ward-risk-model-operations-audit-v1"

AUDIT_PASS = "pass"
AUDIT_WARNING = "warning"
AUDIT_FAIL = "fail"

REVIEW_RECOMMENDATION_STATES = {
    ModelRetrainingRecommendationState.REVIEW_REQUIRED,
    ModelRetrainingRecommendationState.RETRAINING_RECOMMENDED,
}


def _model_run_ref(run: ModelRun | None) -> dict:
    if run is None:
        return {
            "model_run_id": None,
            "model_version": None,
            "algorithm_name": "",
            "promotion_target": None,
            "promotion_state": None,
        }
    metadata = run.metadata or {}
    return {
        "model_run_id": run.id,
        "model_version": run.model_version,
        "algorithm_name": run.algorithm_name,
        "promotion_target": metadata.get("promotion_target"),
        "promotion_state": metadata.get("promotion_state"),
        "phase_4_promotion_gates_passed": metadata.get("phase_4_promotion_gates_passed"),
        "alert_eligible": metadata.get("alert_eligible"),
    }


def _registry_entry_ref(entry: ModelRegistryEntry | None) -> dict | None:
    if entry is None:
        return None
    return {
        "registry_entry_id": entry.id,
        "registry_entry_public_id": str(entry.public_id),
        "model_run_id": entry.model_run_id,
        "model_version": entry.model_version,
        "algorithm": entry.algorithm,
        "promotion_state": entry.promotion_state,
        "monitoring_state": entry.monitoring_state,
        "active_from": entry.active_from,
        "active_until": entry.active_until,
        "promotion_event_id": entry.promotion_event_id,
        "review_due_date": entry.review_due_date,
    }


def _alert_ref(alert: Alert) -> dict:
    risk_score = alert.risk_score
    model_run = risk_score.model_run if risk_score and risk_score.model_run_id else None
    return {
        "alert_id": alert.id,
        "alert_public_id": str(alert.public_id),
        "ward_id": alert.ward_id,
        "ward_name": alert.ward.name,
        "risk_score_id": alert.risk_score_id,
        "model_run": _model_run_ref(model_run),
        "channel": alert.channel,
        "status": alert.status,
        "created_at": alert.created_at,
    }


def _check(
    *,
    check_id: str,
    status: str,
    answer: str,
    evidence: dict,
    gaps: list[str] | None = None,
    remediation: str = "",
) -> dict:
    return {
        "id": check_id,
        "status": status,
        "answer": answer,
        "evidence": evidence,
        "gaps": gaps or [],
        "remediation": remediation,
    }


def _overall_status(checks: list[dict]) -> str:
    statuses = {check["status"] for check in checks}
    if AUDIT_FAIL in statuses:
        return AUDIT_FAIL
    if AUDIT_WARNING in statuses:
        return AUDIT_WARNING
    return AUDIT_PASS


def _active_model_without_registry_entry_check(active_entry: ModelRegistryEntry | None) -> dict:
    promoted_runs = promoted_model_runs_from_phase_4_metadata()
    promoted_without_registry = []
    for run in promoted_runs:
        try:
            run.registry_entry
        except ObjectDoesNotExist:
            promoted_without_registry.append(_model_run_ref(run))

    if promoted_without_registry:
        status = AUDIT_FAIL
        answer = "One or more Phase 4-promoted model runs are missing ModelRegistryEntry governance."
        gaps = ["phase_4_promoted_model_run_without_registry_entry"]
    elif active_entry is None and promoted_runs:
        status = AUDIT_FAIL
        answer = "A Phase 4-promoted model exists but no active ModelRegistryEntry controls operations."
        gaps = ["active_model_registry_entry_missing"]
    elif active_entry is None:
        status = AUDIT_WARNING
        answer = "No Phase 4-promoted model or active registry entry is present."
        gaps = ["no_active_model_to_audit"]
    else:
        status = AUDIT_PASS
        answer = "The active model is governed by a ModelRegistryEntry."
        gaps = []

    return _check(
        check_id="active_model_without_registry_entry",
        status=status,
        answer=answer,
        evidence={
            "active_registry_entry": _registry_entry_ref(active_entry),
            "phase_4_promoted_model_run_count": len(promoted_runs),
            "promoted_without_registry_count": len(promoted_without_registry),
            "promoted_without_registry": promoted_without_registry[:25],
        },
        gaps=gaps,
        remediation="Run sync_model_registry_entry for the promoted run before treating it as operationally active.",
    )


def _active_registry_without_phase_4_gates_check(active_entry: ModelRegistryEntry | None) -> dict:
    active_entries = list(
        ModelRegistryEntry.objects.select_related("model_run")
        .filter(
            promotion_state=ModelRegistryPromotionState.ACTIVE_PROMOTED,
            active_until__isnull=True,
        )
        .order_by("-active_from", "-id")
    )
    invalid_entries = [
        {
            "registry_entry": _registry_entry_ref(entry),
            "model_run": _model_run_ref(entry.model_run),
        }
        for entry in active_entries
        if not model_run_has_phase_4_promotion_metadata(entry.model_run)
    ]

    return _check(
        check_id="registry_active_model_without_phase_4_gates",
        status=AUDIT_FAIL if invalid_entries else AUDIT_PASS,
        answer=(
            "Every active registry entry points to a model run with Phase 4 promotion gates."
            if not invalid_entries
            else "One or more active registry entries point to a model run without Phase 4 promotion gates."
        ),
        evidence={
            "active_registry_entry": _registry_entry_ref(active_entry),
            "active_registry_entry_count": len(active_entries),
            "invalid_active_registry_entry_count": len(invalid_entries),
            "invalid_active_registry_entries": invalid_entries[:25],
        },
        gaps=["active_registry_entry_missing_phase_4_promotion_gate_evidence"] if invalid_entries else [],
        remediation="Retire the unsafe registry entry and promote only a Phase 4-gated model run.",
    )


def _active_registry_window_invariant_check() -> dict:
    active_state_entries = list(
        ModelRegistryEntry.objects.select_related("model_run")
        .filter(promotion_state=ModelRegistryPromotionState.ACTIVE_PROMOTED)
        .order_by("-active_from", "-id")
    )
    invalid_entries = [
        {
            "registry_entry": _registry_entry_ref(entry),
            "model_run": _model_run_ref(entry.model_run),
            "active_from_missing": entry.active_from is None,
            "active_until_present": entry.active_until is not None,
        }
        for entry in active_state_entries
        if entry.active_from is None or entry.active_until is not None
    ]

    return _check(
        check_id="registry_active_model_invalid_active_window",
        status=AUDIT_FAIL if invalid_entries else AUDIT_PASS,
        answer=(
            "Every ACTIVE_PROMOTED registry entry has an open active window with active_from set."
            if not invalid_entries
            else "One or more ACTIVE_PROMOTED registry entries have a missing or closed active window."
        ),
        evidence={
            "active_state_registry_entry_count": len(active_state_entries),
            "invalid_active_window_count": len(invalid_entries),
            "invalid_active_windows": invalid_entries[:25],
        },
        gaps=["active_promoted_registry_entry_without_open_active_window"] if invalid_entries else [],
        remediation=(
            "Repair registry state so ACTIVE_PROMOTED entries have active_from populated and active_until empty."
        ),
    )


def _active_registry_promotion_event_provenance_check() -> dict:
    active_state_entries = list(
        ModelRegistryEntry.objects.select_related("model_run", "promotion_event")
        .filter(
            promotion_state=ModelRegistryPromotionState.ACTIVE_PROMOTED,
            active_until__isnull=True,
        )
        .order_by("-active_from", "-id")
    )
    invalid_entries = [
        {
            "registry_entry": _registry_entry_ref(entry),
            "model_run": _model_run_ref(entry.model_run),
            "promotion_event_id": entry.promotion_event_id,
            "promotion_event_model_run_id": (
                entry.promotion_event.model_run_id if entry.promotion_event_id else None
            ),
            "promotion_event_registry_entry_id": (
                entry.promotion_event.registry_entry_id if entry.promotion_event_id else None
            ),
        }
        for entry in active_state_entries
        if not registry_entry_has_promotion_event_provenance(entry)
    ]

    return _check(
        check_id="registry_active_model_missing_promotion_event_provenance",
        status=AUDIT_FAIL if invalid_entries else AUDIT_PASS,
        answer=(
            "Every active registry entry has a promotion event that points to the same registry entry and model run."
            if not invalid_entries
            else "One or more active registry entries are missing valid promotion-event provenance."
        ),
        evidence={
            "active_state_registry_entry_count": len(active_state_entries),
            "invalid_promotion_event_provenance_count": len(invalid_entries),
            "invalid_promotion_event_provenance": invalid_entries[:25],
        },
        gaps=["active_promoted_registry_entry_without_valid_promotion_event"] if invalid_entries else [],
        remediation="Re-sync the promoted run through sync_model_registry_entry so promotion provenance is recorded.",
    )


def _has_review_record(entry: ModelRegistryEntry | None) -> bool:
    if entry is None:
        return False
    metadata = entry.metadata or {}
    if (
        entry.monitoring_state == ModelRegistryMonitoringState.REVIEW_REQUIRED
        or metadata.get("review_required") is True
        or metadata.get("latest_retraining_recommendation_id")
    ):
        return True
    return ModelRetrainingRecommendation.objects.filter(
        registry_entry=entry,
        recommendation_state__in=REVIEW_RECOMMENDATION_STATES,
    ).exists()


def _stale_model_without_review_warning_check(
    *,
    active_entry: ModelRegistryEntry | None,
    stale_review_days: int,
    now,
) -> dict:
    if active_entry is None:
        return _check(
            check_id="stale_model_without_review_warning",
            status=AUDIT_WARNING,
            answer="No active registry entry is present for stale-model governance checks.",
            evidence={"active_registry_entry": None, "review_cadence_days": stale_review_days},
            gaps=["no_active_model_to_audit"],
            remediation="Create or sync the active ModelRegistryEntry before running stale-model review.",
        )

    active_from = active_entry.active_from or active_entry.model_run.completed_at or active_entry.model_run.started_at
    age_days = None if active_from is None else max(0, (now - active_from).days)
    review_due = active_entry.review_due_date
    review_due_triggered = review_due is not None and review_due <= timezone.localdate(now)
    stale = active_from is None or (age_days is not None and age_days >= stale_review_days) or review_due_triggered
    review_recorded = _has_review_record(active_entry)
    finding = stale and not review_recorded

    return _check(
        check_id="stale_model_without_review_warning",
        status=AUDIT_FAIL if finding else AUDIT_PASS,
        answer=(
            "Stale-model cadence is satisfied or review evidence exists."
            if not finding
            else "The active model is stale or review-due without a review warning or recommendation record."
        ),
        evidence={
            "active_registry_entry": _registry_entry_ref(active_entry),
            "review_cadence_days": stale_review_days,
            "active_from": active_from,
            "age_days": age_days,
            "review_due_date": review_due,
            "review_due_triggered": review_due_triggered,
            "review_recorded": review_recorded,
        },
        gaps=["stale_active_model_without_review_warning"] if finding else [],
        remediation="Run evaluate_model_retraining_policy or record an explicit review-required registry state.",
    )


def _latest_monitoring_snapshots(entry: ModelRegistryEntry | None):
    if entry is None:
        return []
    queryset = ModelMonitoringSnapshot.objects.filter(registry_entry=entry).order_by("-generated_at", "metric_name")
    latest_monitoring_run_id = (entry.metadata or {}).get("latest_monitoring_run_id")
    if latest_monitoring_run_id:
        return list(queryset.filter(monitoring_run_id=latest_monitoring_run_id))
    latest_snapshot = queryset.first()
    if latest_snapshot is None:
        return []
    return list(queryset.filter(monitoring_run_id=latest_snapshot.monitoring_run_id))


def _drift_breach_without_review_record_check(active_entry: ModelRegistryEntry | None) -> dict:
    snapshots = _latest_monitoring_snapshots(active_entry)
    breached_drift_snapshots = [
        snapshot
        for snapshot in snapshots
        if snapshot.state == ModelMonitoringState.BREACHED
        and ("drift" in snapshot.metric_name or snapshot.metric_family == "drift")
    ]
    review_recorded = _has_review_record(active_entry)
    finding = bool(breached_drift_snapshots) and not review_recorded

    return _check(
        check_id="drift_breach_without_review_record",
        status=AUDIT_FAIL if finding else AUDIT_PASS,
        answer=(
            "Drift breaches have review evidence or no drift breach is currently present."
            if not finding
            else "A drift breach exists without a retraining/review record."
        ),
        evidence={
            "active_registry_entry": _registry_entry_ref(active_entry),
            "latest_snapshot_count": len(snapshots),
            "breached_drift_snapshot_count": len(breached_drift_snapshots),
            "breached_drift_snapshots": [
                {
                    "snapshot_id": snapshot.id,
                    "snapshot_public_id": str(snapshot.public_id),
                    "metric_name": snapshot.metric_name,
                    "state": snapshot.state,
                    "value": snapshot.value,
                    "threshold_value": snapshot.threshold_value,
                    "monitoring_run_id": str(snapshot.monitoring_run_id),
                }
                for snapshot in breached_drift_snapshots[:25]
            ],
            "review_recorded": review_recorded,
        },
        gaps=["drift_breach_without_retraining_or_review_record"] if finding else [],
        remediation="Run evaluate_model_retraining_policy after breached monitoring snapshots are generated.",
    )


def _monitoring_snapshot_integrity_check() -> dict:
    invalid_snapshots = []
    snapshots = (
        ModelMonitoringSnapshot.objects.select_related("registry_entry", "model_run", "threshold")
        .order_by("-generated_at", "-id")
    )
    for snapshot in snapshots:
        issues = []
        if snapshot.registry_entry.model_run_id != snapshot.model_run_id:
            issues.append("snapshot_model_run_does_not_match_registry_entry")
        if snapshot.threshold_id is None:
            issues.append("threshold_missing")
        elif snapshot.threshold.metric_name != snapshot.metric_name:
            issues.append("threshold_metric_does_not_match_snapshot_metric")
        elif snapshot.threshold_version != snapshot.threshold.version:
            issues.append("threshold_version_does_not_match_threshold")
        if not snapshot.threshold_version:
            issues.append("threshold_version_blank")
        if not issues:
            continue
        invalid_snapshots.append(
            {
                "snapshot_id": snapshot.id,
                "snapshot_public_id": str(snapshot.public_id),
                "registry_entry": _registry_entry_ref(snapshot.registry_entry),
                "snapshot_model_run": _model_run_ref(snapshot.model_run),
                "metric_name": snapshot.metric_name,
                "threshold_id": snapshot.threshold_id,
                "threshold_version": snapshot.threshold_version,
                "issues": issues,
                "generated_at": snapshot.generated_at,
            }
        )

    return _check(
        check_id="monitoring_snapshot_integrity",
        status=AUDIT_FAIL if invalid_snapshots else AUDIT_PASS,
        answer=(
            "Monitoring snapshots are bound to their registry model run and versioned thresholds."
            if not invalid_snapshots
            else "One or more monitoring snapshots have invalid model-run or threshold lineage."
        ),
        evidence={
            "snapshot_count": ModelMonitoringSnapshot.objects.count(),
            "invalid_snapshot_count": len(invalid_snapshots),
            "invalid_snapshots": invalid_snapshots[:25],
        },
        gaps=["monitoring_snapshot_invalid_lineage_or_threshold"] if invalid_snapshots else [],
        remediation="Regenerate invalid monitoring snapshots through run_model_monitoring.",
    )


def _retraining_recommendation_integrity_check() -> dict:
    invalid_recommendations = []
    recommendations = (
        ModelRetrainingRecommendation.objects.select_related("registry_entry", "model_run")
        .order_by("-generated_at", "-id")
    )
    for recommendation in recommendations:
        metadata = recommendation.metadata or {}
        issues = []
        if recommendation.registry_entry.model_run_id != recommendation.model_run_id:
            issues.append("recommendation_model_run_does_not_match_registry_entry")
        if metadata.get("automatic_live_promotion_allowed") is not False:
            issues.append("automatic_live_promotion_not_explicitly_blocked")
        if metadata.get("phase_4_promotion_gates_required") is not True:
            issues.append("phase_4_promotion_gates_not_required")
        if not issues:
            continue
        invalid_recommendations.append(
            {
                "recommendation_id": recommendation.id,
                "recommendation_public_id": str(recommendation.public_id),
                "registry_entry": _registry_entry_ref(recommendation.registry_entry),
                "recommendation_model_run": _model_run_ref(recommendation.model_run),
                "recommendation_state": recommendation.recommendation_state,
                "issues": issues,
                "generated_at": recommendation.generated_at,
            }
        )

    return _check(
        check_id="retraining_recommendation_integrity",
        status=AUDIT_FAIL if invalid_recommendations else AUDIT_PASS,
        answer=(
            "Retraining recommendations are bound to their registry model run and forbid automatic promotion."
            if not invalid_recommendations
            else "One or more retraining recommendations have invalid lineage or promotion policy metadata."
        ),
        evidence={
            "recommendation_count": ModelRetrainingRecommendation.objects.count(),
            "invalid_recommendation_count": len(invalid_recommendations),
            "invalid_recommendations": invalid_recommendations[:25],
        },
        gaps=["retraining_recommendation_invalid_lineage_or_policy"] if invalid_recommendations else [],
        remediation="Recreate invalid recommendations through evaluate_model_retraining_policy.",
    )


def _rollback_to_non_promoted_run_check() -> dict:
    invalid_events = []
    events = ModelRollbackEvent.objects.select_related(
        "rolled_back_from__model_run",
        "rollback_target__model_run",
    ).order_by("-occurred_at", "-id")
    for event in events:
        target = event.rollback_target
        target_has_phase_4_gates = model_run_has_phase_4_promotion_metadata(target.model_run)
        target_has_promotion_history = registry_entry_has_promotion_event_provenance(target)
        target_was_previously_promoted = (
            target.promotion_state != ModelRegistryPromotionState.CANDIDATE
            and target_has_promotion_history
        )
        if target_has_phase_4_gates and target_was_previously_promoted:
            continue
        invalid_events.append(
            {
                "rollback_event_id": event.id,
                "rollback_event_public_id": str(event.public_id),
                "rolled_back_from": _registry_entry_ref(event.rolled_back_from),
                "rollback_target": _registry_entry_ref(event.rollback_target),
                "rollback_target_model_run": _model_run_ref(event.rollback_target.model_run),
                "rollback_target_has_phase_4_gates": target_has_phase_4_gates,
                "rollback_target_has_promotion_history": target_has_promotion_history,
                "rollback_target_was_previously_promoted": target_was_previously_promoted,
                "occurred_at": event.occurred_at,
                "reason": event.reason,
            }
        )

    return _check(
        check_id="rollback_to_non_promoted_run",
        status=AUDIT_FAIL if invalid_events else AUDIT_PASS,
        answer=(
            "Rollback history only targets Phase 4-promoted model runs with prior promotion history."
            if not invalid_events
            else "Rollback history includes a target model run without Phase 4 gates or prior promotion history."
        ),
        evidence={
            "rollback_event_count": ModelRollbackEvent.objects.count(),
            "invalid_rollback_event_count": len(invalid_events),
            "invalid_rollback_events": invalid_events[:25],
        },
        gaps=["rollback_target_without_phase_4_gates_or_promotion_history"] if invalid_events else [],
        remediation="Rollback only through execute_model_rollback, which rejects non-promoted targets.",
    )


def _rollback_event_governance_provenance_check() -> dict:
    invalid_events = []
    events = ModelRollbackEvent.objects.select_related(
        "rolled_back_from__model_run",
        "rollback_target__model_run",
    ).order_by("-occurred_at", "-id")
    for event in events:
        metadata = event.metadata or {}
        authorized_role = metadata.get("authorized_role")
        missing = []
        if not (event.reason or "").strip():
            missing.append("reason")
        if not (event.rolled_back_by or "").strip():
            missing.append("rolled_back_by")
        if metadata.get("schema_version") != MODEL_ROLLBACK_WORKFLOW_SCHEMA_VERSION:
            missing.append("metadata.schema_version")
        if authorized_role not in AUTHORIZED_ROLLBACK_ROLES:
            missing.append("metadata.authorized_role")
        if not metadata.get("previous_active"):
            missing.append("metadata.previous_active")
        if not metadata.get("new_active"):
            missing.append("metadata.new_active")
        if not metadata.get("current_risk_materialization"):
            missing.append("metadata.current_risk_materialization")
        if not missing:
            continue
        invalid_events.append(
            {
                "rollback_event_id": event.id,
                "rollback_event_public_id": str(event.public_id),
                "rolled_back_from": _registry_entry_ref(event.rolled_back_from),
                "rollback_target": _registry_entry_ref(event.rollback_target),
                "rolled_back_by": event.rolled_back_by,
                "missing_governance_fields": missing,
                "authorized_role": authorized_role,
                "schema_version": metadata.get("schema_version"),
                "occurred_at": event.occurred_at,
            }
        )

    return _check(
        check_id="rollback_event_missing_governance_provenance",
        status=AUDIT_FAIL if invalid_events else AUDIT_PASS,
        answer=(
            "Rollback events include operator, role, schema, active-state, and current-risk provenance."
            if not invalid_events
            else "One or more rollback events are missing required governance provenance."
        ),
        evidence={
            "rollback_event_count": ModelRollbackEvent.objects.count(),
            "invalid_rollback_event_count": len(invalid_events),
            "invalid_rollback_events": invalid_events[:25],
            "authorized_roles": sorted(AUTHORIZED_ROLLBACK_ROLES),
            "expected_schema_version": MODEL_ROLLBACK_WORKFLOW_SCHEMA_VERSION,
        },
        gaps=["rollback_event_missing_governance_provenance"] if invalid_events else [],
        remediation="Execute rollbacks through perform_model_rollback/execute_model_rollback, not direct event writes.",
    )


def _challenger_scores_used_as_alerts_check() -> dict:
    challenger_run_ids = set(
        ModelChampionChallengerComparison.objects.values_list("challenger_model_run_id", flat=True)
    )
    unsafe_alerts = []
    alerts = (
        Alert.objects.select_related("ward", "risk_score", "risk_score__model_run")
        .filter(risk_score__model_run__isnull=False)
        .order_by("-created_at", "-id")
    )
    for alert in alerts:
        run = alert.risk_score.model_run
        metadata = run.metadata or {}
        if metadata.get("promotion_target") != PROMOTION_TARGET_BENCHMARK_ONLY and run.id not in challenger_run_ids:
            continue
        unsafe_alerts.append(_alert_ref(alert))

    return _check(
        check_id="challenger_scores_used_as_alerts",
        status=AUDIT_FAIL if unsafe_alerts else AUDIT_PASS,
        answer=(
            "No alert records use benchmark-only challenger scores."
            if not unsafe_alerts
            else "One or more alert records are linked to benchmark-only challenger scores."
        ),
        evidence={
            "challenger_model_run_count": len(challenger_run_ids),
            "unsafe_alert_count": len(unsafe_alerts),
            "unsafe_alerts": unsafe_alerts[:25],
        },
        gaps=["challenger_or_benchmark_score_used_for_alert"] if unsafe_alerts else [],
        remediation="Create alerts only from the active promoted model run and remove any benchmark-only alert records.",
    )


def _champion_challenger_integrity_check() -> dict:
    invalid_comparisons = []
    comparisons = (
        ModelChampionChallengerComparison.objects.select_related(
            "champion_registry_entry",
            "champion_model_run",
            "challenger_model_run",
        )
        .order_by("-generated_at", "-id")
    )
    for comparison in comparisons:
        issues = []
        if comparison.champion_model_run_id == comparison.challenger_model_run_id:
            issues.append("challenger_model_run_matches_champion_model_run")
        if comparison.champion_registry_entry.model_run_id != comparison.champion_model_run_id:
            issues.append("champion_registry_entry_does_not_match_champion_model_run")
        if not issues:
            continue
        invalid_comparisons.append(
            {
                "comparison_id": comparison.id,
                "comparison_public_id": str(comparison.public_id),
                "champion_registry_entry": _registry_entry_ref(comparison.champion_registry_entry),
                "champion_model_run": _model_run_ref(comparison.champion_model_run),
                "challenger_model_run": _model_run_ref(comparison.challenger_model_run),
                "issues": issues,
                "generated_at": comparison.generated_at,
            }
        )

    return _check(
        check_id="champion_challenger_comparison_integrity",
        status=AUDIT_FAIL if invalid_comparisons else AUDIT_PASS,
        answer=(
            "Champion/challenger comparisons keep champion and challenger runs distinct."
            if not invalid_comparisons
            else "One or more champion/challenger comparisons have invalid model-run relationships."
        ),
        evidence={
            "comparison_count": ModelChampionChallengerComparison.objects.count(),
            "invalid_comparison_count": len(invalid_comparisons),
            "invalid_comparisons": invalid_comparisons[:25],
        },
        gaps=["champion_challenger_comparison_invalid_relationships"] if invalid_comparisons else [],
        remediation="Recreate invalid comparisons through record_champion_challenger_comparison.",
    )


def build_model_operations_audit(
    *,
    stale_review_days: int = DEFAULT_MODEL_REVIEW_INTERVAL_DAYS,
) -> dict:
    if stale_review_days <= 0:
        raise ValueError("stale_review_days_must_be_positive")

    now = timezone.now()
    active_entry = active_model_registry_entry()
    checks = [
        _active_model_without_registry_entry_check(active_entry),
        _active_registry_without_phase_4_gates_check(active_entry),
        _active_registry_window_invariant_check(),
        _active_registry_promotion_event_provenance_check(),
        _stale_model_without_review_warning_check(
            active_entry=active_entry,
            stale_review_days=stale_review_days,
            now=now,
        ),
        _drift_breach_without_review_record_check(active_entry),
        _monitoring_snapshot_integrity_check(),
        _retraining_recommendation_integrity_check(),
        _rollback_to_non_promoted_run_check(),
        _rollback_event_governance_provenance_check(),
        _challenger_scores_used_as_alerts_check(),
        _champion_challenger_integrity_check(),
    ]
    status_counts = {
        AUDIT_PASS: sum(1 for check in checks if check["status"] == AUDIT_PASS),
        AUDIT_WARNING: sum(1 for check in checks if check["status"] == AUDIT_WARNING),
        AUDIT_FAIL: sum(1 for check in checks if check["status"] == AUDIT_FAIL),
    }
    return {
        "schema_version": MODEL_OPERATIONS_AUDIT_SCHEMA_VERSION,
        "generated_at": now,
        "overall_status": _overall_status(checks),
        "summary": {
            "check_count": len(checks),
            "passed_check_count": status_counts[AUDIT_PASS],
            "warning_check_count": status_counts[AUDIT_WARNING],
            "failed_check_count": status_counts[AUDIT_FAIL],
            "active_model_present": active_entry is not None,
            "active_registry_entry_id": active_entry.id if active_entry else None,
        },
        "governance": {
            "review_cadence_days": stale_review_days,
            "review_due_date_source": "ModelRegistryEntry.review_due_date",
            "review_required_state": ModelRegistryMonitoringState.REVIEW_REQUIRED,
            "retraining_recommendation_record": "ModelRetrainingRecommendation",
            "promotion_source_of_truth": (
                "ModelRegistryEntry.promotion_state=ACTIVE_PROMOTED with active_from set, active_until null, "
                "and valid ModelPromotionEvent provenance"
            ),
            "phase_4_gate_source": "ModelRun.metadata Phase 4 promotion evidence",
            "rollback_audit_record": "ModelRollbackEvent",
            "challenger_alert_policy": "Benchmark-only challenger outputs must not create Alert records.",
            "manual_review_cadence": (
                "Review active promoted model health at least every 90 days, immediately after any monitoring "
                "breach, and after any rollback event."
            ),
        },
        "checks": checks,
    }
