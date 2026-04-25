from __future__ import annotations

from risk.models import ModelRun


def _run_summary(run: ModelRun) -> dict:
    metadata = run.metadata or {}
    evaluation_metrics = run.evaluation_metrics or {}
    return {
        "model_version": run.model_version,
        "algorithm_name": run.algorithm_name,
        "training_accuracy": float(evaluation_metrics.get("training_accuracy", 0.0)),
        "training_dataset_ref": run.training_dataset_ref,
        "inference_dataset_ref": run.inference_dataset_ref,
        "feature_schema_version": run.feature_schema_version,
        "execution_context": metadata.get("execution_context"),
        "run_purpose": metadata.get("run_purpose"),
        "promotion_target": metadata.get("promotion_target"),
        "evaluation_metrics": evaluation_metrics,
    }


def build_model_comparison_summary(
    *,
    logistic_run: ModelRun,
    random_forest_run: ModelRun,
) -> dict:
    same_training_dataset = logistic_run.training_dataset_ref == random_forest_run.training_dataset_ref
    same_inference_dataset = logistic_run.inference_dataset_ref == random_forest_run.inference_dataset_ref
    same_feature_schema = logistic_run.feature_schema_version == random_forest_run.feature_schema_version

    logistic_accuracy = float((logistic_run.evaluation_metrics or {}).get("training_accuracy", 0.0))
    random_forest_accuracy = float((random_forest_run.evaluation_metrics or {}).get("training_accuracy", 0.0))
    accuracy_delta = round(random_forest_accuracy - logistic_accuracy, 4)

    comparison_validity = "comparable_inputs"
    if not (same_training_dataset and same_inference_dataset and same_feature_schema):
        comparison_validity = "comparison_input_mismatch"

    promotion_blockers = []
    if comparison_validity != "comparable_inputs":
        promotion_blockers.append("feature_or_dataset_mismatch")

    # Early-phase promotion must remain conservative until these dimensions are
    # evaluated explicitly with real operational evidence rather than inferred.
    promotion_blockers.extend(
        [
            "calibration_evidence_missing",
            "lead_time_evidence_missing",
            "temporal_robustness_evidence_missing",
            "operational_promotion_review_pending",
        ]
    )

    decision = {
        "recommended_primary_model": "logistic_regression",
        "governance_mode": "shadow_benchmark_mode",
        "promotion_readiness": "not_ready_for_promotion",
        "comparison_validity": comparison_validity,
        "promotion_blockers": promotion_blockers,
        "decision_reason": (
            "Random Forest is benchmark-capable, but early-phase promotion evidence is still incomplete. "
            "Keep Logistic Regression as the live primary model and retain Random Forest in shadow benchmark mode."
        ),
        "dashboard_wording_impact": "none",
        "live_alert_task": "risk.tasks.run_risk_model_task",
        "benchmark_only_tasks": ["risk.tasks.run_random_forest_benchmark_task"],
        "retraining_task": None,
        "retraining_mode": "manual_only_no_scheduled_retraining_task",
        "evaluation_dimensions_reviewed": {
            "discrimination_quality": "partial",
            "calibration_quality": "not_yet_complete",
            "lead_time_usefulness": "not_yet_complete",
            "temporal_robustness": "not_yet_complete",
            "interpretability_cost": "reviewed_conservatively",
            "operational_trustworthiness": "partially_reviewed",
        },
    }

    return {
        "logistic_regression": _run_summary(logistic_run),
        "random_forest": _run_summary(random_forest_run),
        "comparison": {
            "same_training_dataset": same_training_dataset,
            "same_inference_dataset": same_inference_dataset,
            "same_feature_schema": same_feature_schema,
            "training_accuracy_delta_rf_minus_lr": accuracy_delta,
        },
        "decision": decision,
    }
