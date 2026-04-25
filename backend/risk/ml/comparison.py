from __future__ import annotations

from risk.models import ModelRun


REQUIRED_PROMOTION_EVIDENCE_KEYS = {
    "out_of_time_score": "out_of_time_validation_missing",
    "calibration_score": "calibration_evidence_missing",
    "lead_time_days_supported": "lead_time_evidence_missing",
    "temporal_validation_window_count": "temporal_robustness_evidence_missing",
}


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


def _promotion_evidence_assessment(*, logistic_run: ModelRun, random_forest_run: ModelRun) -> dict:
    logistic_metrics = logistic_run.evaluation_metrics or {}
    random_forest_metrics = random_forest_run.evaluation_metrics or {}

    evidence = {}
    for key, blocker in REQUIRED_PROMOTION_EVIDENCE_KEYS.items():
        evidence[key] = {
            "logistic_regression": key in logistic_metrics,
            "random_forest": key in random_forest_metrics,
            "blocker": blocker,
        }
    return evidence


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

    evidence_assessment = _promotion_evidence_assessment(
        logistic_run=logistic_run,
        random_forest_run=random_forest_run,
    )
    for evidence in evidence_assessment.values():
        if not (evidence["logistic_regression"] and evidence["random_forest"]):
            promotion_blockers.append(evidence["blocker"])

    promotion_blockers.append("operational_promotion_review_pending")
    promotion_blockers = list(dict.fromkeys(promotion_blockers))

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
        "evidence_assessment": evidence_assessment,
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
