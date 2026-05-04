from __future__ import annotations

from django.utils import timezone

from risk.models import (
    FeatureDataset,
    ModelMonitoringSnapshot,
    ModelPromotionEvent,
    ModelRegistryEntry,
    ModelRollbackEvent,
    ModelRun,
    RiskScore,
    SurveillanceIngestionRun,
    SurveillanceLabelWindow,
)

from .registry import active_model_registry_entry, promoted_model_runs_from_phase_4_metadata


MODEL_OPS_STATE_INVENTORY_SCHEMA_VERSION = "ward-risk-model-ops-state-inventory-v1"


def _question(
    *,
    question_id: str,
    status: str,
    answer: str,
    evidence: dict,
    gaps: list[str] | None = None,
    boundary: str = "",
) -> dict:
    return {
        "id": question_id,
        "status": status,
        "answer": answer,
        "evidence": evidence,
        "gaps": gaps or [],
        "boundary": boundary,
    }


def _overall_status(questions: list[dict]) -> str:
    statuses = {question["status"] for question in questions}
    if "fail" in statuses:
        return "fail"
    if "warning" in statuses:
        return "warning"
    return "pass"


def _label_dataset_refs_for_run(model_run: ModelRun) -> list[str]:
    metadata = model_run.metadata or {}
    evaluation_metrics = model_run.evaluation_metrics or {}
    temporal_report = evaluation_metrics.get("temporal_backtest_report") or {}
    refs = [
        metadata.get("ward_risk_classification_label_dataset_ref"),
        temporal_report.get("label_dataset_ref"),
        (metadata.get("phase_4_promotion_evidence_binding") or {}).get("report_label_dataset_ref"),
    ]
    return sorted({ref for ref in refs if ref})


def _dataset_ref_state(model_run: ModelRun) -> dict:
    return {
        "training_dataset_ref": model_run.training_dataset_ref,
        "inference_dataset_ref": model_run.inference_dataset_ref,
        "training_feature_dataset_id": model_run.training_feature_dataset_id,
        "inference_feature_dataset_id": model_run.inference_feature_dataset_id,
        "has_training_dataset_link": bool(
            model_run.training_dataset_ref or model_run.training_feature_dataset_id
        ),
        "has_inference_dataset_link": bool(
            model_run.inference_dataset_ref or model_run.inference_feature_dataset_id
        ),
    }


def build_model_ops_state_inventory() -> dict:
    promoted_runs = promoted_model_runs_from_phase_4_metadata()
    active_registry = active_model_registry_entry()
    latest_promoted_run = promoted_runs[0] if promoted_runs else None
    registry_entries_count = ModelRegistryEntry.objects.count()
    rollback_events_count = ModelRollbackEvent.objects.count()
    promoted_run_count = len(promoted_runs)

    questions: list[dict] = []
    if active_registry is not None:
        questions.append(
            _question(
                question_id="how_is_the_promoted_model_identified",
                status="pass",
                answer=(
                    "The active promoted model is identified by "
                    "ModelRegistryEntry.promotion_state=ACTIVE_PROMOTED with active_from set, no active_until, "
                    "and valid ModelPromotionEvent provenance."
                ),
                evidence={
                    "registry_entry_id": active_registry.id,
                    "model_run_id": active_registry.model_run_id,
                    "model_version": active_registry.model_version,
                    "algorithm": active_registry.algorithm,
                    "active_from": active_registry.active_from,
                    "promotion_event_id": active_registry.promotion_event_id,
                },
                boundary=(
                    "ModelRun.metadata stores Phase 4 evidence; ModelRegistryEntry is the post-promotion "
                    "operations source of truth."
                ),
            )
        )
    elif latest_promoted_run is not None:
        questions.append(
            _question(
                question_id="how_is_the_promoted_model_identified",
                status="warning",
                answer="A promoted run exists only through legacy ModelRun.metadata Phase 4 flags.",
                evidence={
                    "model_run_id": latest_promoted_run.id,
                    "model_version": latest_promoted_run.model_version,
                    "metadata_promotion_target": (latest_promoted_run.metadata or {}).get("promotion_target"),
                },
                gaps=["model_registry_entry_missing_for_promoted_run"],
                boundary="Run sync should create the registry entry before operators treat this as the active operations state.",
            )
        )
    else:
        questions.append(
            _question(
                question_id="how_is_the_promoted_model_identified",
                status="warning",
                answer="No Phase 4-promoted ward-risk model was found.",
                evidence={"promoted_model_run_count": 0, "registry_entries_count": registry_entries_count},
                gaps=["no_promoted_model_run_found"],
                boundary="Candidate and benchmark model runs must remain non-live until Phase 4 promotion gates pass.",
            )
        )

    score_count = RiskScore.objects.filter(model_run__isnull=False).count()
    promoted_score_count = (
        RiskScore.objects.filter(model_run__in=[run.id for run in promoted_runs]).count() if promoted_runs else 0
    )
    score_distribution_snapshot_count = ModelMonitoringSnapshot.objects.filter(
        metric_name="score_distribution_drift"
    ).count()
    score_distribution_status = "pass" if score_distribution_snapshot_count else "warning"
    score_distribution_gaps = [] if score_distribution_snapshot_count else [
        "score_distribution_baselines_not_persisted_until_phase_2_monitoring"
    ]
    questions.append(
        _question(
            question_id="where_are_score_distributions_stored",
            status=score_distribution_status,
            answer="Ward score points are durable RiskScore rows linked to ModelRun; Phase 2 stores score-distribution drift snapshots.",
            evidence={
                "risk_scores_with_model_run": score_count,
                "risk_scores_for_phase_4_promoted_runs": promoted_score_count,
                "score_distribution_monitoring_snapshots": score_distribution_snapshot_count,
            },
            gaps=score_distribution_gaps,
            boundary="Phase 1 owns registry state; Phase 2 owns durable score-distribution monitoring snapshots.",
        )
    )

    promoted_dataset_states = [_dataset_ref_state(run) for run in promoted_runs]
    promoted_with_training = sum(1 for state in promoted_dataset_states if state["has_training_dataset_link"])
    promoted_with_inference = sum(1 for state in promoted_dataset_states if state["has_inference_dataset_link"])
    dataset_status = (
        "pass"
        if promoted_run_count
        and promoted_with_training == promoted_run_count
        and promoted_with_inference == promoted_run_count
        else "warning"
    )
    dataset_gaps = []
    if not promoted_run_count:
        dataset_gaps.append("no_promoted_model_run_to_check_feature_dataset_links")
    if promoted_with_training != promoted_run_count:
        dataset_gaps.append("promoted_model_missing_training_feature_dataset_link")
    if promoted_with_inference != promoted_run_count:
        dataset_gaps.append("promoted_model_missing_inference_feature_dataset_link")
    questions.append(
        _question(
            question_id="where_are_feature_datasets_linked",
            status=dataset_status,
            answer="ModelRun carries training and inference dataset refs plus optional FeatureDataset foreign keys.",
            evidence={
                "promoted_model_run_count": promoted_run_count,
                "promoted_with_training_dataset_link": promoted_with_training,
                "promoted_with_inference_dataset_link": promoted_with_inference,
                "feature_dataset_count": FeatureDataset.objects.count(),
            },
            gaps=dataset_gaps,
            boundary="Feature generation remains upstream of model ops; registry entries snapshot these refs for operations review.",
        )
    )

    runs_with_label_refs = [run for run in promoted_runs if _label_dataset_refs_for_run(run)]
    label_status = "pass" if promoted_run_count and len(runs_with_label_refs) == promoted_run_count else "warning"
    label_gaps = []
    if not promoted_run_count:
        label_gaps.append("no_promoted_model_run_to_check_post_prediction_labels")
    if len(runs_with_label_refs) != promoted_run_count:
        label_gaps.append("promoted_model_missing_label_dataset_reference")
    questions.append(
        _question(
            question_id="how_are_post_prediction_labels_attached",
            status=label_status,
            answer=(
                "Post-prediction labels are attached through temporal backtest reports and surveillance label "
                "FeatureDataset refs on ModelRun metadata/evaluation metrics."
            ),
            evidence={
                "promoted_model_run_count": promoted_run_count,
                "promoted_runs_with_label_dataset_refs": len(runs_with_label_refs),
                "surveillance_label_window_count": SurveillanceLabelWindow.objects.count(),
            },
            gaps=label_gaps,
            boundary="Labels remain surveillance-derived datasets; model ops consumes their refs and later monitoring snapshots.",
        )
    )

    corrected_ingestion_count = SurveillanceIngestionRun.objects.exclude(
        correction_mode=SurveillanceIngestionRun.CORRECTION_ORIGINAL
    ).count()
    questions.append(
        _question(
            question_id="how_are_corrections_handled",
            status="pass",
            answer=(
                "Surveillance ingestion records correction_mode/reason and label rows carry late_revision_state "
                "for replay after backfills or amendments."
            ),
            evidence={
                "corrected_surveillance_ingestion_runs": corrected_ingestion_count,
                "surveillance_label_window_count": SurveillanceLabelWindow.objects.count(),
            },
            boundary="Corrections change surveillance label datasets; registry state records which dataset refs informed promotion.",
        )
    )

    rollback_target = active_registry.rollback_target if active_registry and active_registry.rollback_target_id else None
    rollback_status = "pass" if active_registry is not None else "warning"
    rollback_gaps = [] if active_registry is not None else ["no_active_registry_entry_for_rollback_target"]
    questions.append(
        _question(
            question_id="what_rollback_metadata_exists",
            status=rollback_status,
            answer="ModelRegistryEntry stores rollback_target and ModelRollbackEvent stores auditable rollback decisions.",
            evidence={
                "registry_entries_count": registry_entries_count,
                "rollback_events_count": rollback_events_count,
                "active_registry_entry_id": active_registry.id if active_registry else None,
                "rollback_target_registry_entry_id": rollback_target.id if rollback_target else None,
                "rollback_target_model_run_id": rollback_target.model_run_id if rollback_target else None,
            },
            gaps=rollback_gaps,
            boundary="Phase 1 identifies rollback targets; Phase 5 will execute atomic rollback and risk materialization review.",
        )
    )

    gaps = sorted({gap for question in questions for gap in question["gaps"]})
    return {
        "schema_version": MODEL_OPS_STATE_INVENTORY_SCHEMA_VERSION,
        "generated_at": timezone.now(),
        "overall_status": _overall_status(questions),
        "questions": questions,
        "gaps": gaps,
        "counts": {
            "phase_4_promoted_model_runs": promoted_run_count,
            "model_registry_entries": registry_entries_count,
            "model_promotion_events": ModelPromotionEvent.objects.count(),
            "model_rollback_events": rollback_events_count,
        },
        "state_boundaries": {
            "promotion_evidence": "ModelRun.metadata and evaluation_metrics remain the Phase 4 evidence record.",
            "operations_source_of_truth": "ModelRegistryEntry is the active/retired post-promotion registry state.",
            "scores": "RiskScore stores per-ward score points linked to ModelRun, not drift baselines.",
            "feature_lineage": "ModelRun training/inference refs and FeatureDataset links anchor promotion lineage.",
            "labels": "Surveillance label FeatureDataset refs attach post-prediction truth and corrections.",
            "rollback": "Registry rollback_target identifies the candidate target; ModelRollbackEvent audits decisions.",
        },
    }
