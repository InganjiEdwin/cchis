from __future__ import annotations

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils import timezone

from risk.models import (
    Alert,
    ModelChallengerBenchmarkStatus,
    ModelChampionChallengerComparison,
    ModelRegistryEntry,
    ModelRegistryPromotionState,
    ModelRun,
    RiskScore,
)

from .alignment import PROMOTION_TARGET_BENCHMARK_ONLY, algorithm_key_from_run
from .registry import active_model_registry_entry


REQUIRED_PROMOTION_EVIDENCE_KEYS = {
    "out_of_time_score": "out_of_time_validation_missing",
    "lead_time_recall": "lead_time_recall_evidence_missing",
    "precision": "precision_evidence_missing",
    "balanced_accuracy": "balanced_accuracy_evidence_missing",
    "false_alerts_per_true_hit": "false_alert_cost_evidence_missing",
    "positive_class_balance": "class_balance_evidence_missing",
    "calibration_score": "calibration_evidence_missing",
    "lead_time_days_supported": "lead_time_evidence_missing",
    "temporal_validation_window_count": "temporal_robustness_evidence_missing",
    "promotion_truth_and_leakage_checks_passed": "truth_or_leakage_gate_missing",
    "phase_4_training_truth_gate_passed": "training_truth_gate_missing",
    "climate_coverage_gate_passed": "climate_coverage_evidence_missing",
}
CHAMPION_CHALLENGER_SCHEMA_VERSION = "ward-risk-champion-challenger-comparison-v1"
COMPARISON_VALIDITY_COMPARABLE = "comparable_inputs"
COMPARISON_VALIDITY_INPUT_MISMATCH = "comparison_input_mismatch"

TEMPORAL_METRIC_KEYS = [
    "out_of_time_score",
    "lead_time_recall",
    "precision",
    "balanced_accuracy",
    "false_alerts_per_true_hit",
    "positive_class_balance",
    "calibration_score",
    "lead_time_days_supported",
    "temporal_validation_window_count",
    "phase_4_training_truth_gate_passed",
    "climate_coverage_gate_passed",
]


def _label_dataset_ref(run: ModelRun) -> str:
    metadata = run.metadata or {}
    evaluation_metrics = run.evaluation_metrics or {}
    temporal_report = evaluation_metrics.get("temporal_backtest_report") or {}
    evidence_binding = metadata.get("phase_4_promotion_evidence_binding") or {}
    return (
        metadata.get("ward_risk_classification_label_dataset_ref")
        or metadata.get("surveillance_label_dataset_ref")
        or evidence_binding.get("report_label_dataset_ref")
        or temporal_report.get("label_dataset_ref")
        or ""
    )


def _input_alignment(*, champion_run: ModelRun, challenger_run: ModelRun) -> dict:
    champion_label_dataset_ref = _label_dataset_ref(champion_run)
    challenger_label_dataset_ref = _label_dataset_ref(challenger_run)
    same_label_dataset = bool(
        champion_label_dataset_ref
        and challenger_label_dataset_ref
        and champion_label_dataset_ref == challenger_label_dataset_ref
    )
    return {
        "same_training_dataset": champion_run.training_dataset_ref == challenger_run.training_dataset_ref,
        "same_inference_dataset": champion_run.inference_dataset_ref == challenger_run.inference_dataset_ref,
        "same_feature_schema": champion_run.feature_schema_version == challenger_run.feature_schema_version,
        "same_label_dataset": same_label_dataset,
        "same_prediction_month": champion_run.month == challenger_run.month,
        "champion_training_dataset_ref": champion_run.training_dataset_ref,
        "challenger_training_dataset_ref": challenger_run.training_dataset_ref,
        "champion_inference_dataset_ref": champion_run.inference_dataset_ref,
        "challenger_inference_dataset_ref": challenger_run.inference_dataset_ref,
        "champion_label_dataset_ref": champion_label_dataset_ref,
        "challenger_label_dataset_ref": challenger_label_dataset_ref,
        "champion_feature_schema_version": champion_run.feature_schema_version,
        "challenger_feature_schema_version": challenger_run.feature_schema_version,
    }


def _comparison_validity(input_alignment: dict) -> str:
    required_flags = [
        "same_training_dataset",
        "same_inference_dataset",
        "same_feature_schema",
        "same_label_dataset",
    ]
    if all(input_alignment.get(flag) is True for flag in required_flags):
        return COMPARISON_VALIDITY_COMPARABLE
    return COMPARISON_VALIDITY_INPUT_MISMATCH


def _temporal_metric_snapshot(run: ModelRun) -> dict:
    evaluation_metrics = run.evaluation_metrics or {}
    temporal_report = evaluation_metrics.get("temporal_backtest_report") or {}
    promotion_gates = temporal_report.get("promotion_gates") or {}
    selected_model_metrics = temporal_report.get("selected_model_metrics") or {}
    snapshot = {
        key: evaluation_metrics.get(key, selected_model_metrics.get(key))
        for key in TEMPORAL_METRIC_KEYS
    }
    snapshot.update(
        {
            "temporal_backtest_schema_version": temporal_report.get("schema_version"),
            "temporal_backtest_row_counts": temporal_report.get("row_counts", {}),
            "temporal_promotion_gate_passed": promotion_gates.get("passed"),
            "temporal_promotion_gate_blockers": promotion_gates.get("blockers", []),
            "label_dataset_ref": _label_dataset_ref(run),
        }
    )
    return snapshot


def _operational_metric_snapshot(run: ModelRun, *, role: str) -> dict:
    metadata = run.metadata or {}
    risk_scores = RiskScore.objects.filter(model_run=run)
    alert_count = Alert.objects.filter(risk_score__model_run=run).count()
    return {
        "role": role,
        "algorithm": algorithm_key_from_run(run),
        "algorithm_name": run.algorithm_name,
        "model_version": run.model_version,
        "promotion_target": metadata.get("promotion_target"),
        "promotion_state": metadata.get("promotion_state"),
        "run_purpose": metadata.get("run_purpose"),
        "alert_eligible": metadata.get("alert_eligible", False),
        "benchmark_only": metadata.get("promotion_target") == PROMOTION_TARGET_BENCHMARK_ONLY,
        "risk_score_count": risk_scores.count(),
        "high_risk_score_count": risk_scores.filter(risk_level="HIGH").count(),
        "alert_count": alert_count,
        "current_risk_mutation_allowed": role == "champion",
        "automatic_alerts_allowed": role == "champion" and metadata.get("alert_eligible") is True,
    }


def _promotion_blockers(*, input_alignment: dict, challenger_run: ModelRun) -> list[str]:
    blockers = []
    if not (
        input_alignment.get("same_training_dataset")
        and input_alignment.get("same_inference_dataset")
        and input_alignment.get("same_feature_schema")
    ):
        blockers.append("feature_or_dataset_mismatch")
    if not input_alignment.get("same_label_dataset"):
        blockers.append("label_window_mismatch")
    metadata = challenger_run.metadata or {}
    if metadata.get("promotion_target") != PROMOTION_TARGET_BENCHMARK_ONLY:
        blockers.append("challenger_outputs_not_benchmark_only")
    if metadata.get("alert_eligible") is True:
        blockers.append("challenger_alert_eligible")
    blockers.extend(
        [
            "challenger_not_phase_4_promoted",
            "operational_promotion_review_pending",
        ]
    )
    return list(dict.fromkeys(blockers))


def _benchmark_status(*, comparison_validity: str, promotion_blockers: list[str]) -> str:
    if comparison_validity != COMPARISON_VALIDITY_COMPARABLE:
        return ModelChallengerBenchmarkStatus.NOT_COMPARABLE
    if promotion_blockers and promotion_blockers != [
        "challenger_not_phase_4_promoted",
        "operational_promotion_review_pending",
    ]:
        return ModelChallengerBenchmarkStatus.NOT_COMPARABLE
    return ModelChallengerBenchmarkStatus.BENCHMARK_ONLY


def _dashboard_summary(
    *,
    champion_entry: ModelRegistryEntry,
    challenger_run: ModelRun,
    benchmark_status: str,
    comparison_validity: str,
    promotion_blockers: list[str],
) -> dict:
    challenger_alert_count = Alert.objects.filter(risk_score__model_run=challenger_run).count()
    challenger_outputs_affect_alerts = challenger_alert_count > 0
    operator_label = (
        "Benchmark only"
        if benchmark_status == ModelChallengerBenchmarkStatus.BENCHMARK_ONLY
        else "Not comparable"
    )
    if challenger_outputs_affect_alerts:
        operator_label = "Unsafe alert linkage"
    return {
        "schema_version": CHAMPION_CHALLENGER_SCHEMA_VERSION,
        "safe_for_dashboard": not challenger_outputs_affect_alerts,
        "benchmark_status": benchmark_status,
        "comparison_validity": comparison_validity,
        "champion": {
            "registry_entry_id": champion_entry.id,
            "model_run_id": champion_entry.model_run_id,
            "algorithm": champion_entry.algorithm,
            "model_version": champion_entry.model_version,
            "promotion_state": champion_entry.promotion_state,
        },
        "challenger": {
            "model_run_id": challenger_run.id,
            "algorithm": algorithm_key_from_run(challenger_run),
            "algorithm_name": challenger_run.algorithm_name,
            "model_version": challenger_run.model_version,
            "promotion_target": (challenger_run.metadata or {}).get("promotion_target"),
        },
        "challenger_alert_count": challenger_alert_count,
        "challenger_outputs_affect_alerts": challenger_outputs_affect_alerts,
        "challenger_outputs_update_current_ward_risk": False,
        "can_replace_champion_without_phase_4_promotion": False,
        "promotion_blockers": promotion_blockers,
        "operator_label": operator_label,
    }


def _run_summary(run: ModelRun) -> dict:
    metadata = run.metadata or {}
    evaluation_metrics = run.evaluation_metrics or {}
    temporal_report = evaluation_metrics.get("temporal_backtest_report") or {}
    return {
        "model_version": run.model_version,
        "algorithm_name": run.algorithm_name,
        "training_accuracy": float(evaluation_metrics.get("training_accuracy", 0.0)),
        "training_dataset_ref": run.training_dataset_ref,
        "inference_dataset_ref": run.inference_dataset_ref,
        "feature_schema_version": run.feature_schema_version,
        "label_dataset_ref": _label_dataset_ref(run),
        "execution_context": metadata.get("execution_context"),
        "run_purpose": metadata.get("run_purpose"),
        "promotion_target": metadata.get("promotion_target"),
        "phase_4_promotion_evidence_persisted": metadata.get("phase_4_promotion_evidence_persisted", False),
        "phase_4_promotion_gates_passed": metadata.get("phase_4_promotion_gates_passed", False),
        "temporal_backtest_summary": {
            "schema_version": temporal_report.get("schema_version"),
            "row_counts": temporal_report.get("row_counts", {}),
            "promotion_gates": temporal_report.get("promotion_gates", {}),
            "climate_coverage_summary": temporal_report.get("climate_coverage_summary")
            or evaluation_metrics.get("climate_coverage_summary")
            or {},
            "validation_climate_coverage_summary": temporal_report.get("validation_climate_coverage_summary")
            or evaluation_metrics.get("validation_climate_coverage_summary")
            or {},
            "rainfall_threshold_baseline_accuracy": evaluation_metrics.get("rainfall_threshold_baseline_accuracy"),
            "selected_model_metrics": {
                "out_of_time_score": evaluation_metrics.get("out_of_time_score"),
                "lead_time_recall": evaluation_metrics.get("lead_time_recall"),
                "precision": evaluation_metrics.get("precision"),
                "balanced_accuracy": evaluation_metrics.get("balanced_accuracy"),
                "false_alerts_per_true_hit": evaluation_metrics.get("false_alerts_per_true_hit"),
                "positive_class_balance": evaluation_metrics.get("positive_class_balance"),
                "training_truth_gate_passed": evaluation_metrics.get("phase_4_training_truth_gate_passed"),
                "climate_coverage_gate_passed": evaluation_metrics.get("climate_coverage_gate_passed"),
            },
        },
        "evaluation_metrics": evaluation_metrics,
    }


def _promotion_evidence_assessment(*, logistic_run: ModelRun, random_forest_run: ModelRun) -> dict:
    logistic_metrics = logistic_run.evaluation_metrics or {}
    random_forest_metrics = random_forest_run.evaluation_metrics or {}

    evidence = {}
    for key, blocker in REQUIRED_PROMOTION_EVIDENCE_KEYS.items():
        if key in {
            "promotion_truth_and_leakage_checks_passed",
            "phase_4_training_truth_gate_passed",
            "climate_coverage_gate_passed",
        }:
            logistic_available = logistic_metrics.get(key) is True
            random_forest_available = random_forest_metrics.get(key) is True
        elif key == "lead_time_days_supported":
            logistic_available = bool(logistic_metrics.get(key))
            random_forest_available = bool(random_forest_metrics.get(key))
        else:
            logistic_available = logistic_metrics.get(key) is not None
            random_forest_available = random_forest_metrics.get(key) is not None
        evidence[key] = {
            "logistic_regression": logistic_available,
            "random_forest": random_forest_available,
            "blocker": blocker,
        }
    return evidence


def build_model_comparison_summary(
    *,
    logistic_run: ModelRun,
    random_forest_run: ModelRun,
) -> dict:
    input_alignment = _input_alignment(champion_run=logistic_run, challenger_run=random_forest_run)
    same_training_dataset = input_alignment["same_training_dataset"]
    same_inference_dataset = input_alignment["same_inference_dataset"]
    same_feature_schema = input_alignment["same_feature_schema"]
    same_label_dataset = input_alignment["same_label_dataset"]

    logistic_accuracy = float((logistic_run.evaluation_metrics or {}).get("training_accuracy", 0.0))
    random_forest_accuracy = float((random_forest_run.evaluation_metrics or {}).get("training_accuracy", 0.0))
    accuracy_delta = round(random_forest_accuracy - logistic_accuracy, 4)
    logistic_temporal_report = (logistic_run.evaluation_metrics or {}).get("temporal_backtest_report") or {}
    random_forest_temporal_report = (random_forest_run.evaluation_metrics or {}).get("temporal_backtest_report") or {}
    rainfall_baseline_accuracy = (
        (logistic_run.evaluation_metrics or {}).get("rainfall_threshold_baseline_accuracy")
        or (random_forest_run.evaluation_metrics or {}).get("rainfall_threshold_baseline_accuracy")
    )

    comparison_validity = "comparable_inputs"
    if not (same_training_dataset and same_inference_dataset and same_feature_schema and same_label_dataset):
        comparison_validity = COMPARISON_VALIDITY_INPUT_MISMATCH

    promotion_blockers = []
    if not (same_training_dataset and same_inference_dataset and same_feature_schema):
        promotion_blockers.append("feature_or_dataset_mismatch")
    if not same_label_dataset:
        promotion_blockers.append("label_window_mismatch")

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
            "Keep Logistic Regression as the primary scoring candidate and retain Random Forest in shadow "
            "benchmark mode until Phase 4 promotion gates pass."
        ),
        "dashboard_wording_impact": "do_not_label_candidate_scores_as_live_promoted",
        "candidate_scoring_task": "risk.tasks.run_risk_model_task",
        "live_alert_task": None,
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
            "same_label_dataset": same_label_dataset,
            "champion_label_dataset_ref": input_alignment["champion_label_dataset_ref"],
            "challenger_label_dataset_ref": input_alignment["challenger_label_dataset_ref"],
            "training_accuracy_delta_rf_minus_lr": accuracy_delta,
            "rainfall_threshold_baseline_accuracy": rainfall_baseline_accuracy,
            "phase_4_temporal_backtest_reports_present": {
                "logistic_regression": bool(logistic_temporal_report),
                "random_forest": bool(random_forest_temporal_report),
            },
        },
        "decision": decision,
    }


def build_champion_challenger_comparison_payload(
    *,
    champion_entry: ModelRegistryEntry,
    challenger_run: ModelRun,
) -> dict:
    champion_run = champion_entry.model_run
    input_alignment = _input_alignment(champion_run=champion_run, challenger_run=challenger_run)
    comparison_validity = _comparison_validity(input_alignment)
    blockers = _promotion_blockers(input_alignment=input_alignment, challenger_run=challenger_run)
    benchmark_status = _benchmark_status(
        comparison_validity=comparison_validity,
        promotion_blockers=blockers,
    )
    operational_metrics = {
        "schema_version": CHAMPION_CHALLENGER_SCHEMA_VERSION,
        "champion": _operational_metric_snapshot(champion_run, role="champion"),
        "challenger": _operational_metric_snapshot(challenger_run, role="challenger"),
    }
    temporal_metrics = {
        "schema_version": CHAMPION_CHALLENGER_SCHEMA_VERSION,
        "champion": _temporal_metric_snapshot(champion_run),
        "challenger": _temporal_metric_snapshot(challenger_run),
    }
    comparison_summary = {
        "schema_version": CHAMPION_CHALLENGER_SCHEMA_VERSION,
        "input_alignment": input_alignment,
        "operational_metrics": operational_metrics,
        "temporal_metrics": temporal_metrics,
        "decision": {
            "benchmark_status": benchmark_status,
            "comparison_validity": comparison_validity,
            "recommended_action": "keep_champion_monitor_challenger",
            "promotion_blockers": blockers,
            "automatic_live_promotion_allowed": False,
        },
    }
    return {
        "benchmark_status": benchmark_status,
        "comparison_validity": comparison_validity,
        "recommended_action": "keep_champion_monitor_challenger",
        "input_alignment": input_alignment,
        "operational_metrics": operational_metrics,
        "temporal_metrics": temporal_metrics,
        "comparison_summary": comparison_summary,
        "promotion_blockers": blockers,
        "dashboard_summary": _dashboard_summary(
            champion_entry=champion_entry,
            challenger_run=challenger_run,
            benchmark_status=benchmark_status,
            comparison_validity=comparison_validity,
            promotion_blockers=blockers,
        ),
    }


def latest_benchmark_challenger_run(*, algorithm_name: str = "") -> ModelRun | None:
    queryset = ModelRun.objects.filter(status=ModelRun.STATUS_SUCCESS).order_by("-started_at", "-id")
    if algorithm_name:
        queryset = queryset.filter(algorithm_name=algorithm_name)
    for run in queryset:
        if (run.metadata or {}).get("promotion_target") == PROMOTION_TARGET_BENCHMARK_ONLY:
            return run
    return None


def _validate_champion_and_challenger(*, champion_entry: ModelRegistryEntry, challenger_run: ModelRun) -> None:
    if champion_entry.promotion_state != ModelRegistryPromotionState.ACTIVE_PROMOTED:
        raise ValueError("champion_registry_entry_not_active_promoted")
    if champion_entry.active_until is not None:
        raise ValueError("champion_registry_entry_inactive")
    if challenger_run.status != ModelRun.STATUS_SUCCESS:
        raise ValueError("challenger_model_run_not_successful")
    if champion_entry.model_run_id == challenger_run.id:
        raise ValueError("challenger_must_differ_from_champion")

    try:
        challenger_registry_entry = challenger_run.registry_entry
    except ObjectDoesNotExist:
        challenger_registry_entry = None
    if (
        challenger_registry_entry is not None
        and challenger_registry_entry.promotion_state == ModelRegistryPromotionState.ACTIVE_PROMOTED
        and challenger_registry_entry.active_until is None
    ):
        raise ValueError("challenger_is_already_active_champion")

    challenger_metadata = challenger_run.metadata or {}
    if challenger_metadata.get("promotion_target") != PROMOTION_TARGET_BENCHMARK_ONLY:
        raise ValueError("challenger_outputs_must_be_benchmark_only")
    if challenger_metadata.get("alert_eligible") is True:
        raise ValueError("challenger_alert_eligible_not_allowed")
    if Alert.objects.filter(risk_score__model_run=challenger_run).exists():
        raise ValueError("challenger_scores_already_used_for_alerts")


def record_champion_challenger_comparison(
    *,
    challenger_run: ModelRun | None = None,
    champion_entry: ModelRegistryEntry | None = None,
    metadata: dict | None = None,
) -> ModelChampionChallengerComparison:
    champion_entry = champion_entry or active_model_registry_entry()
    if champion_entry is None:
        raise ValueError("active_champion_registry_entry_missing")
    challenger_run = challenger_run or latest_benchmark_challenger_run()
    if challenger_run is None:
        raise ValueError("benchmark_challenger_model_run_missing")

    with transaction.atomic():
        champion_entry = (
            ModelRegistryEntry.objects.select_for_update()
            .select_related("model_run")
            .get(id=champion_entry.id)
        )
        challenger_run = ModelRun.objects.select_for_update().get(id=challenger_run.id)
        _validate_champion_and_challenger(
            champion_entry=champion_entry,
            challenger_run=challenger_run,
        )
        payload = build_champion_challenger_comparison_payload(
            champion_entry=champion_entry,
            challenger_run=challenger_run,
        )
        comparison = ModelChampionChallengerComparison.objects.create(
            champion_registry_entry=champion_entry,
            champion_model_run=champion_entry.model_run,
            challenger_model_run=challenger_run,
            challenger_algorithm=algorithm_key_from_run(challenger_run) or challenger_run.algorithm_name,
            challenger_model_version=challenger_run.model_version,
            benchmark_status=payload["benchmark_status"],
            comparison_validity=payload["comparison_validity"],
            recommended_action=payload["recommended_action"],
            input_alignment=payload["input_alignment"],
            operational_metrics=payload["operational_metrics"],
            temporal_metrics=payload["temporal_metrics"],
            comparison_summary=payload["comparison_summary"],
            promotion_blockers=payload["promotion_blockers"],
            dashboard_summary=payload["dashboard_summary"],
            metadata={
                "schema_version": CHAMPION_CHALLENGER_SCHEMA_VERSION,
                "automatic_live_promotion_allowed": False,
                "generated_by": "record_champion_challenger_comparison",
                **(metadata or {}),
            },
            generated_at=timezone.now(),
        )

        challenger_run.metadata = {
            **(challenger_run.metadata or {}),
            "promotion_target": PROMOTION_TARGET_BENCHMARK_ONLY,
            "alert_eligible": False,
            "champion_challenger_role": "challenger",
            "latest_champion_challenger_comparison_id": comparison.id,
            "latest_champion_challenger_comparison_public_id": str(comparison.public_id),
            "challenger_outputs_affect_alerts": False,
            "can_replace_champion_without_phase_4_promotion": False,
        }
        challenger_run.save(update_fields=["metadata"])

        champion_entry.metadata = {
            **(champion_entry.metadata or {}),
            "latest_challenger_comparison_id": comparison.id,
            "latest_challenger_comparison_public_id": str(comparison.public_id),
            "latest_challenger_model_run_id": challenger_run.id,
            "latest_challenger_model_version": challenger_run.model_version,
            "latest_challenger_benchmark_status": comparison.benchmark_status,
        }
        champion_entry.save(update_fields=["metadata", "updated_at"])
        return comparison


def latest_champion_challenger_dashboard_summary(
    *,
    champion_entry: ModelRegistryEntry | None = None,
) -> dict:
    champion_entry = champion_entry or active_model_registry_entry()
    if champion_entry is None:
        return {
            "schema_version": CHAMPION_CHALLENGER_SCHEMA_VERSION,
            "safe_for_dashboard": True,
            "benchmark_status": None,
            "comparison_validity": None,
            "champion": None,
            "challenger": None,
            "challenger_outputs_affect_alerts": False,
            "challenger_outputs_update_current_ward_risk": False,
            "can_replace_champion_without_phase_4_promotion": False,
        }
    comparison = (
        ModelChampionChallengerComparison.objects.filter(champion_registry_entry=champion_entry)
        .order_by("-generated_at", "-id")
        .first()
    )
    if comparison is None:
        return {
            "schema_version": CHAMPION_CHALLENGER_SCHEMA_VERSION,
            "safe_for_dashboard": True,
            "benchmark_status": "not_configured",
            "comparison_validity": None,
            "champion": {
                "registry_entry_id": champion_entry.id,
                "model_run_id": champion_entry.model_run_id,
                "algorithm": champion_entry.algorithm,
                "model_version": champion_entry.model_version,
                "promotion_state": champion_entry.promotion_state,
            },
            "challenger": None,
            "challenger_outputs_affect_alerts": False,
            "challenger_outputs_update_current_ward_risk": False,
            "can_replace_champion_without_phase_4_promotion": False,
        }
    return comparison.dashboard_summary
