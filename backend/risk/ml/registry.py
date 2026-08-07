from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from risk.models import (
    ModelPromotionEvent,
    ModelRegistryEntry,
    ModelRegistryMonitoringState,
    ModelRegistryPromotionState,
    ModelRollbackEvent,
    ModelRun,
)

from .alignment import (
    algorithm_key_from_run,
    model_run_has_phase_4_promotion_metadata,
    registry_entry_has_promotion_event_provenance,
)
from ..truth_policy import production_model_run_blockers


MODEL_REGISTRY_SCHEMA_VERSION = "ward-risk-model-registry-v1"
MODEL_ROLLBACK_WORKFLOW_SCHEMA_VERSION = "ward-risk-model-rollback-workflow-v1"
DEFAULT_MODEL_REVIEW_INTERVAL_DAYS = 90
AUTHORIZED_ROLLBACK_ROLES = {
    "admin",
    "model_operations",
    "county_operator",
}


def default_review_due_date(active_from=None):
    active_from = active_from or timezone.now()
    return timezone.localtime(active_from).date() + timedelta(days=DEFAULT_MODEL_REVIEW_INTERVAL_DAYS)


def active_model_registry_entry() -> ModelRegistryEntry | None:
    return (
        ModelRegistryEntry.objects.select_related(
            "model_run",
            "rollback_target__model_run",
            "promotion_event",
        )
        .filter(
            promotion_state=ModelRegistryPromotionState.ACTIVE_PROMOTED,
            active_from__isnull=False,
            active_until__isnull=True,
            promotion_event__isnull=False,
            promotion_event__registry_entry_id=F("id"),
            promotion_event__model_run_id=F("model_run_id"),
        )
        .order_by("-active_from", "-id")
        .first()
    )


def promoted_model_runs_from_phase_4_metadata() -> list[ModelRun]:
    return [
        run
        for run in ModelRun.objects.filter(status=ModelRun.STATUS_SUCCESS).order_by("-started_at", "-id")
        if model_run_has_phase_4_promotion_metadata(run)
    ]


def latest_promoted_model_run_from_phase_4_metadata() -> ModelRun | None:
    return next(iter(promoted_model_runs_from_phase_4_metadata()), None)


def _promotion_metadata_snapshot(model_run: ModelRun) -> dict:
    metadata = model_run.metadata or {}
    evaluation_metrics = model_run.evaluation_metrics or {}
    return {
        "schema_version": MODEL_REGISTRY_SCHEMA_VERSION,
        "model_run_id": model_run.id,
        "algorithm_name": model_run.algorithm_name,
        "algorithm": algorithm_key_from_run(model_run) or model_run.algorithm_name,
        "model_version": model_run.model_version,
        "training_dataset_ref": model_run.training_dataset_ref,
        "inference_dataset_ref": model_run.inference_dataset_ref,
        "training_feature_dataset_id": model_run.training_feature_dataset_id,
        "inference_feature_dataset_id": model_run.inference_feature_dataset_id,
        "feature_schema_version": model_run.feature_schema_version,
        "promotion_target": metadata.get("promotion_target"),
        "promotion_state": metadata.get("promotion_state"),
        "phase_4_promotion_gates_passed": metadata.get("phase_4_promotion_gates_passed"),
        "promotion_evidence_report_ref": metadata.get("promotion_evidence_report_ref"),
        "ward_risk_classification_backtest_dataset_ref": metadata.get(
            "ward_risk_classification_backtest_dataset_ref"
        ),
        "ward_risk_classification_label_dataset_ref": metadata.get(
            "ward_risk_classification_label_dataset_ref"
        ),
        "lead_time_recall": evaluation_metrics.get("lead_time_recall"),
        "precision": evaluation_metrics.get("precision"),
        "calibration_score": evaluation_metrics.get("calibration_score"),
    }


def ensure_registry_entry_for_promoted_run(
    *,
    model_run: ModelRun,
    promoted_by: str = "",
    owner: str = "",
    review_due_date=None,
    source: str = "phase_4_temporal_backtest",
    metadata: dict | None = None,
) -> ModelRegistryEntry:
    truth_blockers = production_model_run_blockers(model_run)
    if truth_blockers:
        raise ValueError(
            f"production_truth_policy_blocked:{','.join(truth_blockers)}"
        )
    if not model_run_has_phase_4_promotion_metadata(model_run):
        raise ValueError("model_run_not_phase_4_promoted")

    activated_at = timezone.now()
    review_due_date = review_due_date or default_review_due_date(activated_at)
    algorithm = algorithm_key_from_run(model_run) or model_run.algorithm_name
    metadata = {
        **_promotion_metadata_snapshot(model_run),
        **(metadata or {}),
    }

    with transaction.atomic():
        active_entries = list(
            ModelRegistryEntry.objects.select_for_update()
            .select_related("model_run")
            .filter(
                promotion_state=ModelRegistryPromotionState.ACTIVE_PROMOTED,
                active_until__isnull=True,
            )
            .order_by("-active_from", "-id")
        )
        rollback_target = next(
            (entry for entry in active_entries if entry.model_run_id != model_run.id),
            None,
        )

        for entry in active_entries:
            if entry.model_run_id == model_run.id:
                continue
            entry.promotion_state = ModelRegistryPromotionState.RETIRED
            entry.active_until = activated_at
            entry.retired_reason = f"Superseded by model_run:{model_run.id}"
            entry.save(update_fields=["promotion_state", "active_until", "retired_reason", "updated_at"])

        entry = (
            ModelRegistryEntry.objects.select_for_update()
            .filter(model_run=model_run)
            .first()
        )
        entry_was_active = (
            entry is not None
            and entry.promotion_state == ModelRegistryPromotionState.ACTIVE_PROMOTED
            and entry.active_until is None
        )
        if entry is None:
            entry = ModelRegistryEntry(
                model_run=model_run,
                active_from=activated_at,
            )
        elif not entry_was_active:
            entry.active_from = activated_at
        elif entry.active_from is None:
            entry.active_from = activated_at

        entry.algorithm = algorithm
        entry.model_version = model_run.model_version
        entry.promotion_state = ModelRegistryPromotionState.ACTIVE_PROMOTED
        entry.active_until = None
        entry.retired_reason = ""
        entry.rollback_target = rollback_target or entry.rollback_target
        entry.monitoring_state = entry.monitoring_state or ModelRegistryMonitoringState.NOT_CONFIGURED
        entry.owner = owner or entry.owner
        entry.review_due_date = review_due_date
        entry.metadata = {
            **(entry.metadata or {}),
            **metadata,
            "rollback_target_model_run_id": (
                (rollback_target.model_run_id if rollback_target else None)
                or ((entry.rollback_target.model_run_id if entry.rollback_target_id else None))
            ),
        }
        entry.save()

        if not entry_was_active or entry.promotion_event_id is None:
            event_active_from = entry.active_from if entry_was_active and entry.active_from else activated_at
            event = ModelPromotionEvent.objects.create(
                registry_entry=entry,
                model_run=model_run,
                previous_registry_entry=rollback_target,
                source=source,
                promoted_by=promoted_by,
                active_from=event_active_from,
                review_due_date=review_due_date,
                evidence_metadata=metadata,
            )
            entry.promotion_event = event
            entry.save(update_fields=["promotion_event", "updated_at"])

        return entry


def rollback_target_for_entry(entry: ModelRegistryEntry | None = None) -> ModelRegistryEntry | None:
    entry = entry or active_model_registry_entry()
    if entry is None:
        return None
    if entry.rollback_target_id:
        return entry.rollback_target
    return (
        ModelRegistryEntry.objects.select_related("model_run")
        .filter(
            promotion_state__in=[
                ModelRegistryPromotionState.RETIRED,
                ModelRegistryPromotionState.ROLLED_BACK,
            ],
            active_from__lt=entry.active_from,
        )
        .exclude(id=entry.id)
        .order_by("-active_from", "-id")
        .first()
    )


def _validate_rollback_authorization(*, rolled_back_by: str, authorized_role: str) -> None:
    if not (rolled_back_by or "").strip():
        raise ValueError("rollback_operator_required")
    if authorized_role not in AUTHORIZED_ROLLBACK_ROLES:
        raise ValueError("rollback_role_not_authorized")


def _validate_rollback_target(*, rolled_back_from: ModelRegistryEntry, rollback_target: ModelRegistryEntry) -> None:
    if rolled_back_from.id == rollback_target.id:
        raise ValueError("rollback_target_must_differ")
    if not model_run_has_phase_4_promotion_metadata(rollback_target.model_run):
        raise ValueError("rollback_target_not_phase_4_promoted")
    if rollback_target.promotion_state == ModelRegistryPromotionState.CANDIDATE:
        raise ValueError("rollback_target_never_promoted")
    if not registry_entry_has_promotion_event_provenance(rollback_target):
        raise ValueError("rollback_target_missing_promotion_event")
    if rollback_target.active_until is None and rollback_target.promotion_state == ModelRegistryPromotionState.ACTIVE_PROMOTED:
        raise ValueError("rollback_target_already_active")


def _validate_rollback_event_target(*, rolled_back_from: ModelRegistryEntry, rollback_target: ModelRegistryEntry) -> None:
    if rolled_back_from.id == rollback_target.id:
        raise ValueError("rollback_target_must_differ")
    if not model_run_has_phase_4_promotion_metadata(rollback_target.model_run):
        raise ValueError("rollback_target_not_phase_4_promoted")
    if rollback_target.promotion_state == ModelRegistryPromotionState.CANDIDATE:
        raise ValueError("rollback_target_never_promoted")
    if not registry_entry_has_promotion_event_provenance(rollback_target):
        raise ValueError("rollback_target_missing_promotion_event")


def materialize_registry_entry_current_risk(registry_entry: ModelRegistryEntry) -> dict:
    updated_ward_ids = set()
    updated_risk_score_ids = []
    for risk_score in registry_entry.model_run.risk_scores.select_related("ward").order_by("-generated_at", "-id"):
        if risk_score.ward_id in updated_ward_ids:
            continue
        ward = risk_score.ward
        ward.current_risk_level = risk_score.risk_level
        ward.current_risk_score = risk_score.score
        ward.save(update_fields=["current_risk_level", "current_risk_score", "updated_at"])
        updated_ward_ids.add(risk_score.ward_id)
        updated_risk_score_ids.append(risk_score.id)
    return {
        "schema_version": MODEL_ROLLBACK_WORKFLOW_SCHEMA_VERSION,
        "materialization_mode": "recomputed_from_rollback_target_risk_scores",
        "materialized_ward_count": len(updated_ward_ids),
        "materialized_ward_ids": sorted(updated_ward_ids),
        "source_risk_score_ids": updated_risk_score_ids,
        "source_model_run_id": registry_entry.model_run_id,
        "source_model_version": registry_entry.model_version,
    }


def _rollback_target_for_locked_entry(entry: ModelRegistryEntry) -> ModelRegistryEntry | None:
    if entry.rollback_target_id:
        return (
            ModelRegistryEntry.objects.select_for_update()
            .select_related("model_run")
            .get(id=entry.rollback_target_id)
        )
    return (
        ModelRegistryEntry.objects.select_for_update()
        .select_related("model_run")
        .filter(
            promotion_state__in=[
                ModelRegistryPromotionState.RETIRED,
                ModelRegistryPromotionState.ROLLED_BACK,
            ],
            active_from__lt=entry.active_from,
        )
        .exclude(id=entry.id)
        .order_by("-active_from", "-id")
        .first()
    )


def execute_model_rollback(
    *,
    rolled_back_from: ModelRegistryEntry | None = None,
    rollback_target: ModelRegistryEntry | None = None,
    reason: str,
    rolled_back_by: str,
    authorized_role: str = "model_operations",
    materialize_current_risk: bool = True,
    metadata: dict | None = None,
) -> ModelRollbackEvent:
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("rollback_reason_required")
    _validate_rollback_authorization(
        rolled_back_by=rolled_back_by,
        authorized_role=authorized_role,
    )

    with transaction.atomic():
        if rolled_back_from is None:
            rolled_back_from = (
                ModelRegistryEntry.objects.select_for_update()
                .select_related("model_run")
                .filter(
                    promotion_state=ModelRegistryPromotionState.ACTIVE_PROMOTED,
                    active_until__isnull=True,
                )
                .order_by("-active_from", "-id")
                .first()
            )
        else:
            rolled_back_from = (
                ModelRegistryEntry.objects.select_for_update()
                .select_related("model_run")
                .get(id=rolled_back_from.id)
            )
        if rolled_back_from is None:
            raise ValueError("active_model_registry_entry_missing")
        if rolled_back_from.promotion_state != ModelRegistryPromotionState.ACTIVE_PROMOTED:
            raise ValueError("rolled_back_from_not_active_promoted")
        if rolled_back_from.active_until is not None:
            raise ValueError("rolled_back_from_inactive")
        if rolled_back_from.active_from is None:
            raise ValueError("rolled_back_from_missing_active_from")
        if not registry_entry_has_promotion_event_provenance(rolled_back_from):
            raise ValueError("rolled_back_from_missing_promotion_event")

        if rollback_target is None:
            rollback_target = _rollback_target_for_locked_entry(rolled_back_from)
        else:
            rollback_target = (
                ModelRegistryEntry.objects.select_for_update()
                .select_related("model_run")
                .get(id=rollback_target.id)
            )
        if rollback_target is None:
            raise ValueError("rollback_target_missing")

        _validate_rollback_target(
            rolled_back_from=rolled_back_from,
            rollback_target=rollback_target,
        )

        occurred_at = timezone.now()
        previous_active_metadata = {
            "registry_entry_id": rolled_back_from.id,
            "model_run_id": rolled_back_from.model_run_id,
            "model_version": rolled_back_from.model_version,
            "active_from": rolled_back_from.active_from.isoformat() if rolled_back_from.active_from else None,
        }
        target_previous_state = {
            "registry_entry_id": rollback_target.id,
            "promotion_state": rollback_target.promotion_state,
            "active_from": rollback_target.active_from.isoformat() if rollback_target.active_from else None,
            "active_until": rollback_target.active_until.isoformat() if rollback_target.active_until else None,
        }

        rolled_back_from.promotion_state = ModelRegistryPromotionState.ROLLED_BACK
        rolled_back_from.active_until = occurred_at
        rolled_back_from.retired_reason = f"Rolled back to model_run:{rollback_target.model_run_id}. {reason}"
        rolled_back_from.metadata = {
            **(rolled_back_from.metadata or {}),
            "rolled_back_at": occurred_at.isoformat(),
            "rolled_back_to_registry_entry_id": rollback_target.id,
            "rolled_back_to_model_run_id": rollback_target.model_run_id,
            "rollback_reason": reason,
        }
        rolled_back_from.save(update_fields=["promotion_state", "active_until", "retired_reason", "metadata", "updated_at"])

        rollback_target.promotion_state = ModelRegistryPromotionState.ACTIVE_PROMOTED
        rollback_target.active_from = occurred_at
        rollback_target.active_until = None
        rollback_target.retired_reason = ""
        rollback_target.rollback_target = rolled_back_from
        rollback_target.metadata = {
            **(rollback_target.metadata or {}),
            "reactivated_by_rollback_at": occurred_at.isoformat(),
            "reactivated_from_registry_entry_id": rolled_back_from.id,
            "reactivated_from_model_run_id": rolled_back_from.model_run_id,
            "rollback_reason": reason,
        }
        rollback_target.save(
            update_fields=[
                "promotion_state",
                "active_from",
                "active_until",
                "retired_reason",
                "rollback_target",
                "metadata",
                "updated_at",
            ]
        )

        if materialize_current_risk:
            materialization_review = materialize_registry_entry_current_risk(rollback_target)
        else:
            materialization_review = {
                "schema_version": MODEL_ROLLBACK_WORKFLOW_SCHEMA_VERSION,
                "materialization_mode": "review_only_no_recompute",
                "materialized_ward_count": 0,
                "materialized_ward_ids": [],
                "source_risk_score_ids": [],
                "source_model_run_id": rollback_target.model_run_id,
                "source_model_version": rollback_target.model_version,
            }

        event = record_model_rollback(
            rolled_back_from=rolled_back_from,
            rollback_target=rollback_target,
            reason=reason,
            rolled_back_by=rolled_back_by,
            metadata={
                "schema_version": MODEL_ROLLBACK_WORKFLOW_SCHEMA_VERSION,
                "authorized_role": authorized_role,
                "previous_active": previous_active_metadata,
                "target_previous_state": target_previous_state,
                "new_active": {
                    "registry_entry_id": rollback_target.id,
                    "model_run_id": rollback_target.model_run_id,
                    "model_version": rollback_target.model_version,
                    "active_from": rollback_target.active_from.isoformat() if rollback_target.active_from else None,
                },
                "current_risk_materialization": materialization_review,
                "alerts_respect_active_registry_state": True,
                **(metadata or {}),
            },
        )
        rollback_target.metadata = {
            **(rollback_target.metadata or {}),
            "latest_rollback_event_id": event.id,
            "latest_rollback_event_public_id": str(event.public_id),
            "current_risk_materialization": materialization_review,
        }
        rollback_target.save(update_fields=["metadata", "updated_at"])
        return event


def record_model_rollback(
    *,
    rolled_back_from: ModelRegistryEntry,
    rollback_target: ModelRegistryEntry,
    reason: str,
    rolled_back_by: str = "",
    metadata: dict | None = None,
) -> ModelRollbackEvent:
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("rollback_reason_required")
    rolled_back_by = (rolled_back_by or "").strip()
    if not rolled_back_by:
        raise ValueError("rollback_operator_required")
    _validate_rollback_event_target(
        rolled_back_from=rolled_back_from,
        rollback_target=rollback_target,
    )
    return ModelRollbackEvent.objects.create(
        rolled_back_from=rolled_back_from,
        rollback_target=rollback_target,
        reason=reason,
        rolled_back_by=rolled_back_by,
        metadata=metadata or {},
    )
