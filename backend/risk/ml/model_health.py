from __future__ import annotations

from django.utils import timezone

from risk.models import (
    Alert,
    ModelChampionChallengerComparison,
    ModelMonitoringSnapshot,
    ModelMonitoringState,
    ModelRegistryEntry,
    ModelRegistryMonitoringState,
    ModelRegistryPromotionState,
    ModelRollbackEvent,
    ModelRun,
)

from .alignment import algorithm_key_from_run, model_run_has_phase_4_promotion_metadata
from .registry import active_model_registry_entry


MODEL_OPERATIONS_HEALTH_SCHEMA_VERSION = "ward-risk-model-operations-health-v1"


def _display_state(value: str | None) -> str:
    if not value:
        return "Unknown"
    return value.replace("_", " ").title()


def _tone_for_health_state(health_state: str) -> str:
    if health_state == "healthy":
        return "success"
    if health_state in {"warning", "review_required"}:
        return "warning"
    if health_state in {"breached", "no_active_model"}:
        return "danger"
    return "default"


def _challenger_dashboard_summary_is_safe(challenger: dict) -> bool:
    return not (challenger.get("dashboard_summary") or {}).get("challenger_outputs_affect_alerts", False)


def _active_health_state(entry: ModelRegistryEntry | None, drift_warnings: list[dict], calibration_warnings: list[dict]) -> str:
    if entry is None:
        return "no_active_model"
    if entry.monitoring_state == ModelRegistryMonitoringState.REVIEW_REQUIRED:
        return "review_required"
    if entry.monitoring_state == ModelRegistryMonitoringState.BREACHED:
        return "breached"
    if entry.monitoring_state == ModelRegistryMonitoringState.WARNING or drift_warnings or calibration_warnings:
        return "warning"
    return "healthy"


def _entry_summary(entry: ModelRegistryEntry | None) -> dict | None:
    if entry is None:
        return None
    run = entry.model_run
    metadata = entry.metadata or {}
    return {
        "registry_entry_id": entry.id,
        "registry_entry_public_id": str(entry.public_id),
        "model_run_id": run.id,
        "algorithm": entry.algorithm,
        "algorithm_name": run.algorithm_name,
        "model_version": entry.model_version,
        "promotion_state": entry.promotion_state,
        "promotion_state_label": _display_state(entry.promotion_state),
        "promotion_date": entry.active_from,
        "active_from": entry.active_from,
        "active_until": entry.active_until,
        "monitoring_state": entry.monitoring_state,
        "monitoring_state_label": _display_state(entry.monitoring_state),
        "review_due_date": entry.review_due_date,
        "owner": entry.owner,
        "phase_4_promotion_gates_passed": metadata.get("phase_4_promotion_gates_passed"),
        "alert_eligible": (run.metadata or {}).get("alert_eligible", False),
        "promotion_evidence_report_ref": metadata.get("promotion_evidence_report_ref"),
    }


def _snapshot_payload(snapshot: ModelMonitoringSnapshot) -> dict:
    return {
        "snapshot_id": snapshot.id,
        "snapshot_public_id": str(snapshot.public_id),
        "monitoring_run_id": str(snapshot.monitoring_run_id),
        "metric_name": snapshot.metric_name,
        "metric_family": snapshot.metric_family,
        "value": snapshot.value,
        "baseline_value": snapshot.baseline_value,
        "threshold_value": snapshot.threshold_value,
        "threshold_version": snapshot.threshold_version,
        "state": snapshot.state,
        "state_label": _display_state(snapshot.state),
        "generated_at": snapshot.generated_at,
        "source_dataset_refs": snapshot.source_dataset_refs,
        "metadata": snapshot.metadata,
    }


def _monitoring_panel(entry: ModelRegistryEntry | None) -> dict:
    if entry is None:
        return {
            "state": ModelRegistryMonitoringState.NOT_CONFIGURED,
            "state_label": _display_state(ModelRegistryMonitoringState.NOT_CONFIGURED),
            "latest_monitoring_run_id": None,
            "latest_generated_at": None,
            "snapshots": [],
            "drift_warnings": [],
            "calibration_warnings": [],
        }

    queryset = ModelMonitoringSnapshot.objects.filter(registry_entry=entry).order_by("-generated_at", "metric_name")
    latest_monitoring_run_id = (entry.metadata or {}).get("latest_monitoring_run_id")
    if latest_monitoring_run_id:
        queryset = queryset.filter(monitoring_run_id=latest_monitoring_run_id)
    else:
        latest_snapshot = queryset.first()
        latest_monitoring_run_id = str(latest_snapshot.monitoring_run_id) if latest_snapshot else None
        if latest_monitoring_run_id:
            queryset = queryset.filter(monitoring_run_id=latest_monitoring_run_id)

    snapshots = [_snapshot_payload(snapshot) for snapshot in queryset]
    warning_states = {ModelMonitoringState.WARNING, ModelMonitoringState.BREACHED}
    drift_warnings = [
        snapshot
        for snapshot in snapshots
        if "drift" in snapshot["metric_name"] and snapshot["state"] in warning_states
    ]
    calibration_warnings = [
        snapshot
        for snapshot in snapshots
        if "calibration" in snapshot["metric_name"] and snapshot["state"] in warning_states
    ]
    latest_generated_at = max((snapshot["generated_at"] for snapshot in snapshots), default=None)
    return {
        "state": entry.monitoring_state,
        "state_label": _display_state(entry.monitoring_state),
        "latest_monitoring_run_id": latest_monitoring_run_id,
        "latest_generated_at": latest_generated_at,
        "snapshots": snapshots,
        "drift_warnings": drift_warnings,
        "calibration_warnings": calibration_warnings,
    }


def _latest_challenger_comparison(entry: ModelRegistryEntry | None) -> dict:
    empty = {
        "configured": False,
        "benchmark_status": "not_configured",
        "comparison_validity": None,
        "dashboard_summary": {
            "safe_for_dashboard": True,
            "challenger_outputs_affect_alerts": False,
            "challenger_outputs_update_current_ward_risk": False,
            "can_replace_champion_without_phase_4_promotion": False,
        },
        "comparison": None,
    }
    if entry is None:
        return empty
    comparison = (
        ModelChampionChallengerComparison.objects.filter(champion_registry_entry=entry)
        .select_related("challenger_model_run", "champion_model_run")
        .order_by("-generated_at", "-id")
        .first()
    )
    if comparison is None:
        return empty
    challenger_alert_count = Alert.objects.filter(risk_score__model_run=comparison.challenger_model_run).count()
    dashboard_summary = {
        **(comparison.dashboard_summary or {}),
        "challenger_alert_count": challenger_alert_count,
    }
    if challenger_alert_count:
        dashboard_summary.update(
            {
                "safe_for_dashboard": False,
                "challenger_outputs_affect_alerts": True,
                "operator_label": "Unsafe alert linkage",
            }
        )
    return {
        "configured": True,
        "comparison_id": comparison.id,
        "comparison_public_id": str(comparison.public_id),
        "generated_at": comparison.generated_at,
        "benchmark_status": comparison.benchmark_status,
        "benchmark_status_label": _display_state(comparison.benchmark_status),
        "comparison_validity": comparison.comparison_validity,
        "recommended_action": comparison.recommended_action,
        "promotion_blockers": comparison.promotion_blockers,
        "dashboard_summary": dashboard_summary,
        "comparison": {
            "input_alignment": comparison.input_alignment,
            "operational_metrics": comparison.operational_metrics,
            "temporal_metrics": comparison.temporal_metrics,
        },
    }


def _rollback_item(event: ModelRollbackEvent) -> dict:
    metadata = event.metadata or {}
    return {
        "rollback_event_id": event.id,
        "rollback_event_public_id": str(event.public_id),
        "rolled_back_from": {
            "registry_entry_id": event.rolled_back_from_id,
            "model_run_id": event.rolled_back_from.model_run_id,
            "model_version": event.rolled_back_from.model_version,
            "algorithm": event.rolled_back_from.algorithm,
        },
        "rollback_target": {
            "registry_entry_id": event.rollback_target_id,
            "model_run_id": event.rollback_target.model_run_id,
            "model_version": event.rollback_target.model_version,
            "algorithm": event.rollback_target.algorithm,
        },
        "rolled_back_by": event.rolled_back_by,
        "authorized_role": metadata.get("authorized_role"),
        "reason": event.reason,
        "occurred_at": event.occurred_at,
        "current_risk_materialization": metadata.get("current_risk_materialization", {}),
    }


def _rollback_history(limit: int = 8) -> list[dict]:
    events = (
        ModelRollbackEvent.objects.select_related(
            "rolled_back_from__model_run",
            "rollback_target__model_run",
        )
        .order_by("-occurred_at", "-id")[:limit]
    )
    return [_rollback_item(event) for event in events]


def _visual_state_for_run(run: ModelRun, registry_entry: ModelRegistryEntry | None) -> str:
    metadata = run.metadata or {}
    if registry_entry is not None:
        if (
            registry_entry.promotion_state == ModelRegistryPromotionState.ACTIVE_PROMOTED
            and registry_entry.active_until is None
        ):
            return "active_promoted"
        if registry_entry.promotion_state == ModelRegistryPromotionState.RETIRED:
            return "retired_promoted"
        if registry_entry.promotion_state == ModelRegistryPromotionState.ROLLED_BACK:
            return "rolled_back"
        return registry_entry.promotion_state.lower()
    if metadata.get("promotion_target") == "benchmark_only":
        return "benchmark_only"
    if model_run_has_phase_4_promotion_metadata(run):
        return "registry_missing_promoted_metadata"
    if metadata.get("promotion_state") == "promoted":
        return "ungoverned_promoted_metadata"
    return "candidate"


def _model_state_item(run: ModelRun, registry_by_run_id: dict[int, ModelRegistryEntry]) -> dict:
    metadata = run.metadata or {}
    registry_entry = registry_by_run_id.get(run.id)
    visual_state = _visual_state_for_run(run, registry_entry)
    return {
        "model_run_id": run.id,
        "algorithm": algorithm_key_from_run(run),
        "algorithm_name": run.algorithm_name,
        "model_version": run.model_version,
        "status": run.status,
        "visual_state": visual_state,
        "visual_state_label": _display_state(visual_state),
        "promotion_target": metadata.get("promotion_target"),
        "promotion_state": metadata.get("promotion_state"),
        "registry_promotion_state": registry_entry.promotion_state if registry_entry else None,
        "alert_eligible": metadata.get("alert_eligible", False),
        "run_purpose": metadata.get("run_purpose"),
        "started_at": run.started_at,
        "completed_at": run.completed_at,
    }


def _recent_model_states(limit: int = 12) -> list[dict]:
    runs = list(ModelRun.objects.filter(status=ModelRun.STATUS_SUCCESS).order_by("-started_at", "-id")[:limit])
    registry_entries = ModelRegistryEntry.objects.filter(model_run_id__in=[run.id for run in runs])
    registry_by_run_id = {entry.model_run_id: entry for entry in registry_entries}
    return [_model_state_item(run, registry_by_run_id) for run in runs]


def build_model_operations_health_dashboard() -> dict:
    active_entry = active_model_registry_entry()
    monitoring = _monitoring_panel(active_entry)
    challenger = _latest_challenger_comparison(active_entry)
    rollback_history = _rollback_history()
    health_state = _active_health_state(
        active_entry,
        monitoring["drift_warnings"],
        monitoring["calibration_warnings"],
    )
    return {
        "schema_version": MODEL_OPERATIONS_HEALTH_SCHEMA_VERSION,
        "generated_at": timezone.now(),
        "summary": {
            "health_state": health_state,
            "health_state_label": _display_state(health_state),
            "health_tone": _tone_for_health_state(health_state),
            "active_model_healthy": health_state == "healthy",
            "active_model_present": active_entry is not None,
            "monitoring_state": monitoring["state"],
            "drift_warning_count": len(monitoring["drift_warnings"]),
            "calibration_warning_count": len(monitoring["calibration_warnings"]),
            "rollback_event_count": ModelRollbackEvent.objects.count(),
            "challenger_benchmark_status": challenger["benchmark_status"],
        },
        "active_model": _entry_summary(active_entry),
        "monitoring": monitoring,
        "challenger_comparison": challenger,
        "rollback_history": rollback_history,
        "model_states": _recent_model_states(),
        "dashboard_policy": {
            "active_model_source_of_truth": (
                "ModelRegistryEntry.ACTIVE_PROMOTED with active_from set, active_until null, "
                "and valid ModelPromotionEvent provenance"
            ),
            "candidate_and_challenger_outputs_can_alert": False,
            "candidate_and_promoted_states_visually_distinct": True,
            "rollback_history_visible": True,
            "challenger_comparison_safe_for_dashboard": _challenger_dashboard_summary_is_safe(challenger),
        },
    }
