from __future__ import annotations

import logging
from uuid import uuid4

from django.db import transaction
from django.utils import timezone

from risk.models import ModelRun, RiskScore, Ward

from .data import FEATURE_SCHEMA_VERSION, build_inference_feature_dataset, build_training_feature_dataset
from .model import (
    ALGORITHM_LOGISTIC_REGRESSION,
    FEATURE_KEYS,
    algorithm_to_run_name,
    evaluate_model,
    predict_probabilities,
    probability_to_predicted_cases,
    probability_to_risk_level,
    train_model,
)
from .trust import alerts_allowed_for_snapshot, build_operational_trust_snapshot, predictions_blocked_for_snapshot


ml_logger = logging.getLogger("risk.ml")


def _persist_blocked_model_run(
    *,
    training_dataset,
    inference_dataset,
    training_rows,
    inference_rows,
    algorithm: str,
    model_version: str,
    month: int,
    benchmark_group_ref: str | None,
    run_role: str,
    alert_eligible: bool,
    operational_trust: dict,
    requested_trigger_alerts: bool,
    execution_context: str,
    run_purpose: str,
) -> ModelRun:
    blocked_at = timezone.now()
    return ModelRun.objects.create(
        algorithm_name=algorithm_to_run_name(algorithm),
        model_version=model_version,
        status=ModelRun.STATUS_FAILED,
        month=month,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        feature_keys=FEATURE_KEYS,
        training_dataset_ref=training_dataset.feature_dataset.dataset_ref,
        inference_dataset_ref=inference_dataset.feature_dataset.dataset_ref,
        training_row_count=len(training_rows),
        inference_row_count=len(inference_rows),
        evaluation_metrics={
            "blocked_by_trust_policy": True,
            "blocked_at": blocked_at.isoformat(),
        },
        training_feature_dataset=training_dataset.feature_dataset,
        inference_feature_dataset=inference_dataset.feature_dataset,
        metadata={
            "trigger_alerts": False,
            "requested_trigger_alerts": requested_trigger_alerts,
            "send_sms": False,
            "algorithm": algorithm,
            "run_role": run_role,
            "execution_context": execution_context,
            "run_purpose": run_purpose,
            "benchmark_group_ref": benchmark_group_ref,
            "alert_eligible": alert_eligible,
            "dual_model_mode": benchmark_group_ref is not None,
            "promotion_state": "promoted" if alert_eligible else "benchmark_only",
            "promotion_target": "live_baseline" if alert_eligible else "benchmark_only",
            "retraining_policy": "manual_promotion_only",
            "model_family": "ward_risk_classification",
            "operational_trust": operational_trust,
            "automatic_alerts_blocked_by_trust_policy": requested_trigger_alerts,
            "scoring_blocked_by_trust_policy": True,
        },
        rainfall_ingestion_run=inference_dataset.rainfall_ingestion_run,
        completed_at=blocked_at,
    )


def _persist_model_outputs(
    *,
    wards: list[Ward],
    training_dataset,
    inference_dataset,
    training_rows,
    inference_rows,
    algorithm: str,
    model_version: str,
    month: int,
    trigger_alerts: bool,
    send_sms: bool,
    benchmark_group_ref: str | None,
    run_role: str,
    alert_eligible: bool,
    operational_trust: dict,
    requested_trigger_alerts: bool,
    execution_context: str,
    run_purpose: str,
) -> list[RiskScore]:
    effective_trigger_alerts = trigger_alerts and alert_eligible and alerts_allowed_for_snapshot(operational_trust)

    if effective_trigger_alerts:
        from risk.tasks import trigger_alerts_task

    model = train_model(training_rows, algorithm=algorithm)
    evaluation_metrics = evaluate_model(model, training_rows, algorithm=algorithm)
    predictions = predict_probabilities(model, inference_rows, algorithm=algorithm)
    created_scores: list[RiskScore] = []
    ward_map = {ward.id: ward for ward in wards}

    model_run = ModelRun.objects.create(
        algorithm_name=algorithm_to_run_name(algorithm),
        model_version=model_version,
        status=ModelRun.STATUS_RUNNING,
        month=month,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        feature_keys=FEATURE_KEYS,
        training_dataset_ref=training_dataset.feature_dataset.dataset_ref,
        inference_dataset_ref=inference_dataset.feature_dataset.dataset_ref,
        training_row_count=len(training_rows),
        inference_row_count=len(inference_rows),
        evaluation_metrics=evaluation_metrics,
        training_feature_dataset=training_dataset.feature_dataset,
        inference_feature_dataset=inference_dataset.feature_dataset,
        metadata={
            "trigger_alerts": effective_trigger_alerts,
            "requested_trigger_alerts": requested_trigger_alerts,
            "send_sms": send_sms and effective_trigger_alerts,
            "algorithm": algorithm,
            "run_role": run_role,
            "execution_context": execution_context,
            "run_purpose": run_purpose,
            "benchmark_group_ref": benchmark_group_ref,
            "alert_eligible": alert_eligible,
            "dual_model_mode": benchmark_group_ref is not None,
            "promotion_state": "promoted" if alert_eligible else "benchmark_only",
            "promotion_target": "live_baseline" if alert_eligible else "benchmark_only",
            "retraining_policy": "manual_promotion_only",
            "model_family": "ward_risk_classification",
            "operational_trust": operational_trust,
            "automatic_alerts_blocked_by_trust_policy": requested_trigger_alerts and not effective_trigger_alerts,
        },
        rainfall_ingestion_run=inference_dataset.rainfall_ingestion_run,
    )

    for prediction in predictions:
        ward = ward_map[prediction["ward_id"]]
        probability = prediction["predicted_probability"]
        risk_level = probability_to_risk_level(probability)
        predicted_cases = probability_to_predicted_cases(probability)

        if effective_trigger_alerts:
            note_mode = "This output is alert-eligible."
        elif alert_eligible:
            note_mode = "This output is alert-eligible in principle, but automatic alerts were blocked by ETL trust policy."
        else:
            note_mode = "This output is benchmark-only."
        risk_score = RiskScore.objects.create(
            ward=ward,
            model_run=model_run,
            score=probability,
            risk_level=risk_level,
            rainfall_mm=prediction["rainfall_mm"],
            flood_indicator=prediction["flood_indicator"],
            predicted_cases=predicted_cases,
            source=RiskScore.SOURCE_MODEL,
            model_version=model_version,
            notes=(
                f"Generated by {algorithm_to_run_name(algorithm)} using shared feature datasets "
                "for rainfall input, flood proxy, historical cases, seasonality, and population proxy. "
                f"{note_mode}"
            ),
            generated_at=timezone.now(),
        )

        if alert_eligible:
            ward.current_risk_level = risk_level
            ward.current_risk_score = probability
            ward.save(update_fields=["current_risk_level", "current_risk_score", "updated_at"])

        created_scores.append(risk_score)

        if effective_trigger_alerts and risk_level == Ward.RISK_HIGH:
            trigger_alerts_task.delay(risk_score.id, send_sms=send_sms)

    model_run.status = ModelRun.STATUS_SUCCESS
    model_run.completed_at = timezone.now()
    model_run.save(update_fields=["status", "completed_at"])
    return created_scores


def run_mock_prediction_pipeline(
    *,
    month: int,
    model_version: str = "lr-v1",
    algorithm: str = ALGORITHM_LOGISTIC_REGRESSION,
    trigger_alerts: bool = False,
    send_sms: bool = False,
    dual_model: bool = False,
    benchmark_algorithm: str = "random_forest",
    benchmark_model_version: str = "rf-v1",
    alert_algorithm: str | None = None,
    execution_context: str = "manual_command",
    run_purpose: str = "live_scoring",
) -> list[RiskScore]:
    wards = Ward.objects.filter(is_active=True).order_by("name")
    inference_dataset = build_inference_feature_dataset(wards, month=month)
    inference_rows = inference_dataset.rows
    training_dataset = build_training_feature_dataset(month=month)
    training_rows = training_dataset.rows
    created_scores: list[RiskScore] = []
    ward_list = list(wards)
    benchmark_group_ref = uuid4().hex[:12] if dual_model else None
    if alert_algorithm is None:
        alert_algorithm = algorithm
    operational_trust = build_operational_trust_snapshot(inference_dataset.rainfall_ingestion_run)

    ml_logger.info(
        "risk_model_run_started",
        extra={
            "ward_count": len(ward_list),
            "model_version": model_version,
            "month": month,
            "algorithm": algorithm,
            "dual_model": dual_model,
            "benchmark_algorithm": benchmark_algorithm if dual_model else None,
            "operational_trust": operational_trust,
        },
    )

    if predictions_blocked_for_snapshot(operational_trust):
        ml_logger.warning(
            "risk_model_run_blocked_by_etl_trust_policy",
            extra={
                "month": month,
                "model_version": model_version,
                "algorithm": algorithm,
                "operational_trust": operational_trust,
            },
        )
        with transaction.atomic():
            _persist_blocked_model_run(
                training_dataset=training_dataset,
                inference_dataset=inference_dataset,
                training_rows=training_rows,
                inference_rows=inference_rows,
                algorithm=algorithm,
                model_version=model_version,
                month=month,
                benchmark_group_ref=benchmark_group_ref,
                run_role="primary",
                alert_eligible=alert_algorithm == algorithm,
                operational_trust=operational_trust,
                requested_trigger_alerts=trigger_alerts,
                execution_context=execution_context,
                run_purpose=run_purpose,
            )
            if dual_model:
                _persist_blocked_model_run(
                    training_dataset=training_dataset,
                    inference_dataset=inference_dataset,
                    training_rows=training_rows,
                    inference_rows=inference_rows,
                    algorithm=benchmark_algorithm,
                    model_version=benchmark_model_version,
                    month=month,
                    benchmark_group_ref=benchmark_group_ref,
                    run_role="benchmark",
                    alert_eligible=alert_algorithm == benchmark_algorithm,
                    operational_trust=operational_trust,
                    requested_trigger_alerts=trigger_alerts,
                    execution_context=execution_context,
                    run_purpose="benchmark_scoring",
                )
        return []

    with transaction.atomic():
        created_scores.extend(
            _persist_model_outputs(
                wards=ward_list,
                training_dataset=training_dataset,
                inference_dataset=inference_dataset,
                training_rows=training_rows,
                inference_rows=inference_rows,
                algorithm=algorithm,
                model_version=model_version,
                month=month,
                trigger_alerts=trigger_alerts,
                send_sms=send_sms,
                benchmark_group_ref=benchmark_group_ref,
                run_role="primary",
                alert_eligible=alert_algorithm == algorithm,
                operational_trust=operational_trust,
                requested_trigger_alerts=trigger_alerts,
                execution_context=execution_context,
                run_purpose=run_purpose,
            )
        )
        if dual_model:
            created_scores.extend(
                _persist_model_outputs(
                    wards=ward_list,
                    training_dataset=training_dataset,
                    inference_dataset=inference_dataset,
                    training_rows=training_rows,
                    inference_rows=inference_rows,
                    algorithm=benchmark_algorithm,
                    model_version=benchmark_model_version,
                    month=month,
                    trigger_alerts=trigger_alerts,
                    send_sms=send_sms,
                    benchmark_group_ref=benchmark_group_ref,
                    run_role="benchmark",
                    alert_eligible=alert_algorithm == benchmark_algorithm,
                    operational_trust=operational_trust,
                    requested_trigger_alerts=trigger_alerts,
                    execution_context=execution_context,
                    run_purpose="benchmark_scoring",
                )
            )

    ml_logger.info(
        "risk_model_run_completed",
        extra={
            "scores_created": len(created_scores),
            "model_version": model_version,
            "algorithm": algorithm,
            "dual_model": dual_model,
            "benchmark_group_ref": benchmark_group_ref,
        },
    )

    return created_scores
