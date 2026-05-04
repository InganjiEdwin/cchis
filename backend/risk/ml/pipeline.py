from __future__ import annotations

import logging
from uuid import uuid4

from django.db import transaction
from django.utils import timezone

from risk.climate_coverage import climate_alert_evidence_from_prediction
from risk.models import ModelRun, RiskScore, Ward
from risk.surveillance_features import build_surveillance_lead_time_validation_summary

from .data import (
    FEATURE_SCHEMA_VERSION,
    SURVEILLANCE_LABEL_TRAINING_USAGE,
    build_inference_feature_dataset,
    build_training_feature_dataset,
)
from .model import (
    ALGORITHM_LOGISTIC_REGRESSION,
    FEATURE_KEYS,
    algorithm_to_run_name,
    evaluate_model,
    predict_probabilities,
    probability_to_predicted_cases,
    train_model,
)
from .decision_policy import current_ward_risk_decision_policy, evaluate_ward_risk_decision_policy
from .trust import alerts_allowed_for_snapshot, build_operational_trust_snapshot, predictions_blocked_for_snapshot


ml_logger = logging.getLogger("risk.ml")


def _default_run_purpose(algorithm: str, requested_run_purpose: str | None) -> str:
    if requested_run_purpose:
        return requested_run_purpose
    if algorithm == ALGORITHM_LOGISTIC_REGRESSION:
        return "live_scoring"
    return "benchmark_scoring"


def _default_alert_algorithm(algorithm: str, requested_alert_algorithm: str | None) -> str | None:
    if requested_alert_algorithm is not None:
        return requested_alert_algorithm
    if algorithm == ALGORITHM_LOGISTIC_REGRESSION:
        return algorithm
    return None


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
    decision_policy: dict,
) -> ModelRun:
    blocked_at = timezone.now()
    surveillance_label_metadata = _surveillance_label_metadata(training_dataset)
    requested_alert_eligible = alert_eligible
    live_promotion_policy = _live_promotion_policy(
        training_dataset=training_dataset,
        requested_live_promotion=requested_alert_eligible,
    )
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
            "surveillance_lead_time_validation": surveillance_label_metadata["surveillance_lead_time_validation"],
            "decision_policy_version": decision_policy["policy_version"],
            "decision_policy_schema_version": decision_policy["schema_version"],
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
            "requested_alert_eligible": requested_alert_eligible,
            "alert_eligible": False,
            "dual_model_mode": benchmark_group_ref is not None,
            "promotion_state": "scoring_blocked" if requested_alert_eligible else "benchmark_only",
            "promotion_target": "benchmark_only",
            "live_promotion_policy": live_promotion_policy,
            "phase_4_promotion_evidence_required": requested_alert_eligible,
            "retraining_policy": "manual_promotion_only",
            "model_family": "ward_risk_classification",
            "operational_trust": operational_trust,
            "automatic_alerts_blocked_by_trust_policy": requested_trigger_alerts,
            "automatic_alerts_blocked_by_promotion_policy": requested_trigger_alerts and requested_alert_eligible,
            "scoring_blocked_by_trust_policy": True,
            "decision_policy": {
                "schema_version": decision_policy["schema_version"],
                "policy_version": decision_policy["policy_version"],
                "thresholds": decision_policy["thresholds"],
            },
            "population_exposure_dataset_ref": inference_dataset.population_exposure_feature_dataset.dataset_ref
            if inference_dataset.population_exposure_feature_dataset
            else None,
            "population_exposure_feature_dataset_id": inference_dataset.population_exposure_feature_dataset.id
            if inference_dataset.population_exposure_feature_dataset
            else None,
            "population_exposure_coverage": (
                inference_dataset.population_exposure_feature_dataset.lineage_metadata or {}
            ).get("coverage", {})
            if inference_dataset.population_exposure_feature_dataset
            else {},
            "population_exposure_truth_assumptions": (
                inference_dataset.population_exposure_feature_dataset.lineage_metadata or {}
            ).get("truth_assumptions", {})
            if inference_dataset.population_exposure_feature_dataset
            else {},
            **surveillance_label_metadata,
        },
        rainfall_ingestion_run=inference_dataset.rainfall_ingestion_run,
        completed_at=blocked_at,
    )


def _surveillance_label_metadata(training_dataset) -> dict:
    label_dataset = getattr(training_dataset, "surveillance_label_dataset", None)
    training_feature_dataset = getattr(training_dataset, "feature_dataset", None)
    training_lineage = (training_feature_dataset.lineage_metadata or {}) if training_feature_dataset else {}
    if label_dataset is None:
        return {
            "surveillance_label_dataset_ref": None,
            "surveillance_label_feature_dataset_id": None,
            "surveillance_label_schema_version": None,
            "surveillance_label_usage": "not_available",
            "surveillance_label_coverage": {},
            "surveillance_label_truth_assumptions": {},
            "surveillance_lead_time_validation": build_surveillance_lead_time_validation_summary(label_dataset=None),
            "surveillance_label_truth_gate": {
                "proxy_only_as_confirmed_allowed": False,
                "confirmed_truth_required_for_confirmed_outbreak_claims": True,
            },
        }
    lineage = label_dataset.lineage_metadata or {}
    lead_time_validation = build_surveillance_lead_time_validation_summary(label_dataset=label_dataset)
    return {
        "surveillance_label_dataset_ref": label_dataset.dataset_ref,
        "surveillance_label_feature_dataset_id": label_dataset.id,
        "surveillance_label_schema_version": label_dataset.schema_version,
        "surveillance_label_usage": training_lineage.get(
            "surveillance_label_usage",
            "phase_1_training_labels_from_surveillance_label_dataset",
        ),
        "training_label_source": training_lineage.get("training_label_source", ""),
        "training_label_seeded_demo_row_count": training_lineage.get("training_label_seeded_demo_row_count", 0),
        "training_label_readiness": training_lineage.get("training_label_readiness", {}),
        "surveillance_label_coverage": lineage.get("coverage", {}),
        "surveillance_label_truth_assumptions": lineage.get("truth_assumptions", {}),
        "surveillance_lead_time_validation": lead_time_validation,
        "surveillance_label_truth_gate": lead_time_validation["truth_gate"],
    }


def _training_truth_policy(training_dataset) -> dict:
    training_feature_dataset = getattr(training_dataset, "feature_dataset", None)
    lineage = (training_feature_dataset.lineage_metadata or {}) if training_feature_dataset else {}
    usage = lineage.get("surveillance_label_usage")
    readiness = lineage.get("training_label_readiness") or {}
    seeded_row_count = int(lineage.get("training_label_seeded_demo_row_count") or 0)
    truth_gate = lineage.get("surveillance_label_truth_gate") or {}
    blockers = []

    if usage != SURVEILLANCE_LABEL_TRAINING_USAGE:
        blockers.append("surveillance_training_labels_not_goal_aligned")
    if seeded_row_count > 0:
        blockers.append("seeded_training_labels_present")
    if readiness.get("ready") is not True:
        blockers.append(readiness.get("reason") or "training_label_readiness_not_ready")
    if truth_gate.get("proxy_only_as_confirmed_allowed") is True:
        blockers.append("proxy_only_truth_allowed_as_confirmed")

    return {
        "ready_for_live_promotion": not blockers,
        "blockers": list(dict.fromkeys(blockers)),
        "surveillance_label_usage": usage,
        "training_label_seeded_demo_row_count": seeded_row_count,
        "training_label_readiness": readiness,
        "surveillance_label_truth_gate": truth_gate,
    }


def _live_promotion_policy(*, training_dataset, requested_live_promotion: bool) -> dict:
    training_truth_policy = _training_truth_policy(training_dataset)
    if not requested_live_promotion:
        return {
            "requested_live_promotion": False,
            "ready_for_live_promotion": False,
            "blockers": [],
            "training_truth_policy": training_truth_policy,
            "phase_4_temporal_promotion_required": False,
        }

    blockers = [*training_truth_policy["blockers"], "phase_4_temporal_promotion_missing"]
    return {
        "requested_live_promotion": True,
        "ready_for_live_promotion": False,
        "blockers": list(dict.fromkeys(blockers)),
        "training_truth_policy": training_truth_policy,
        "phase_4_temporal_promotion_required": True,
    }


def _promotion_state_from_policy(*, requested_live_promotion: bool, ready_for_live_promotion: bool) -> str:
    if ready_for_live_promotion:
        return "promoted"
    if requested_live_promotion:
        return "promotion_blocked"
    return "benchmark_only"


def _surveillance_alert_metadata_from_prediction(prediction: dict) -> dict:
    return {
        "schema_version": "surveillance-alert-evidence-v1",
        "ward_id": prediction.get("ward_id"),
        "ward_name": prediction.get("ward_name"),
        "recent_suspected_cases_28d": prediction.get("surveillance_recent_suspected_cases_28d", 0),
        "recent_confirmed_cases_28d": prediction.get("surveillance_recent_confirmed_cases_28d", 0),
        "recent_proxy_cases_28d": prediction.get("surveillance_recent_proxy_cases_28d", 0),
        "recent_total_cases_28d": prediction.get("surveillance_recent_total_cases_28d", 0),
        "active_label_count_28d": prediction.get("surveillance_active_label_count_28d", 0),
        "watch_label_count_28d": prediction.get("surveillance_watch_label_count_28d", 0),
        "confirmed_label_window_count_28d": prediction.get("surveillance_confirmed_label_window_count_28d", 0),
        "proxy_only_label_window_count_28d": prediction.get("surveillance_proxy_only_label_window_count_28d", 0),
        "delayed_or_stale_record_count_28d": prediction.get("surveillance_delayed_or_stale_record_count_28d", 0),
        "latest_label_window_ref": prediction.get("surveillance_latest_label_window_ref"),
        "latest_label_dataset_ref": prediction.get("surveillance_latest_label_dataset_ref"),
        "latest_label_truth_level": prediction.get("surveillance_latest_label_truth_level"),
        "latest_freshness_state": prediction.get("surveillance_latest_freshness_state"),
        "label_truth_state": prediction.get("surveillance_label_truth_state"),
        "proxy_only_as_confirmed_allowed": False,
        "caveat": prediction.get("surveillance_display_caveat"),
    }


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
    requested_alert_eligible = alert_eligible
    live_promotion_policy = _live_promotion_policy(
        training_dataset=training_dataset,
        requested_live_promotion=requested_alert_eligible,
    )
    alert_eligible = live_promotion_policy["ready_for_live_promotion"]
    promotion_state = _promotion_state_from_policy(
        requested_live_promotion=requested_alert_eligible,
        ready_for_live_promotion=alert_eligible,
    )
    trust_allows_alerts = alerts_allowed_for_snapshot(operational_trust)
    effective_trigger_alerts = trigger_alerts and alert_eligible and trust_allows_alerts
    decision_policy = current_ward_risk_decision_policy()

    if effective_trigger_alerts:
        from risk.tasks import trigger_alerts_task

    model = train_model(training_rows, algorithm=algorithm)
    evaluation_metrics = evaluate_model(model, training_rows, algorithm=algorithm)
    predictions = predict_probabilities(model, inference_rows, algorithm=algorithm)
    created_scores: list[RiskScore] = []
    ward_map = {ward.id: ward for ward in wards}
    surveillance_label_metadata = _surveillance_label_metadata(training_dataset)
    evaluation_metrics = {
        **evaluation_metrics,
        "surveillance_lead_time_validation": surveillance_label_metadata["surveillance_lead_time_validation"],
        "decision_policy_version": decision_policy["policy_version"],
        "decision_policy_schema_version": decision_policy["schema_version"],
    }

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
            "requested_alert_eligible": requested_alert_eligible,
            "alert_eligible": alert_eligible,
            "dual_model_mode": benchmark_group_ref is not None,
            "promotion_state": promotion_state,
            "promotion_target": "live_baseline" if alert_eligible else "benchmark_only",
            "live_promotion_policy": live_promotion_policy,
            "phase_4_promotion_evidence_required": requested_alert_eligible,
            "retraining_policy": "manual_promotion_only",
            "model_family": "ward_risk_classification",
            "operational_trust": operational_trust,
            "automatic_alerts_blocked_by_trust_policy": (
                requested_trigger_alerts and requested_alert_eligible and not trust_allows_alerts
            ),
            "automatic_alerts_blocked_by_promotion_policy": (
                requested_trigger_alerts and requested_alert_eligible and not alert_eligible
            ),
            "decision_policy": {
                "schema_version": decision_policy["schema_version"],
                "policy_version": decision_policy["policy_version"],
                "thresholds": decision_policy["thresholds"],
            },
            "population_exposure_dataset_ref": inference_dataset.population_exposure_feature_dataset.dataset_ref
            if inference_dataset.population_exposure_feature_dataset
            else None,
            "population_exposure_feature_dataset_id": inference_dataset.population_exposure_feature_dataset.id
            if inference_dataset.population_exposure_feature_dataset
            else None,
            "population_exposure_coverage": (
                inference_dataset.population_exposure_feature_dataset.lineage_metadata or {}
            ).get("coverage", {})
            if inference_dataset.population_exposure_feature_dataset
            else {},
            "population_exposure_truth_assumptions": (
                inference_dataset.population_exposure_feature_dataset.lineage_metadata or {}
            ).get("truth_assumptions", {})
            if inference_dataset.population_exposure_feature_dataset
            else {},
            **surveillance_label_metadata,
        },
        rainfall_ingestion_run=inference_dataset.rainfall_ingestion_run,
    )

    for prediction in predictions:
        ward = ward_map[prediction["ward_id"]]
        probability = prediction["predicted_probability"]
        predicted_cases = probability_to_predicted_cases(probability)
        generated_at = timezone.now()
        decision_policy_evaluation = evaluate_ward_risk_decision_policy(
            ward=ward,
            prediction=prediction,
            model_score=probability,
            expected_case_burden=predicted_cases,
            policy=decision_policy,
            now=generated_at,
        )
        risk_level = decision_policy_evaluation["risk_level"]

        if effective_trigger_alerts:
            note_mode = "This output is alert-eligible."
        elif requested_alert_eligible and not alert_eligible:
            note_mode = (
                "This output is not alert-eligible because live promotion requires non-seeded training truth "
                "and Phase 4 temporal promotion evidence."
            )
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
            decision_policy=decision_policy_evaluation,
            notes=(
                f"Generated by {algorithm_to_run_name(algorithm)} using shared feature datasets "
                "for rainfall input, flood proxy, historical cases, seasonality, population baseline/proxy, "
                "and source-fed exposure or catchment context where available. Population/exposure fields "
                "retain truth classes and must not be read as exact census truth. Surveillance context "
                "retains label-window, freshness, and truth-class lineage; proxy-only labels are not "
                "confirmed outbreak truth. "
                f"Decision policy {decision_policy_evaluation['policy_version']} classified this output as "
                f"{decision_policy_evaluation['alert_decision']}. "
                f"{note_mode}"
            ),
            generated_at=generated_at,
        )

        if alert_eligible:
            ward.current_risk_level = risk_level
            ward.current_risk_score = probability
            ward.save(update_fields=["current_risk_level", "current_risk_score", "updated_at"])

        created_scores.append(risk_score)

        if effective_trigger_alerts and decision_policy_evaluation["automatic_alert_allowed"]:
            trigger_alerts_task.delay(
                risk_score.id,
                send_sms=send_sms,
                guided_request_metadata={
                    "source": "risk_model_pipeline",
                    "surveillance_evidence": _surveillance_alert_metadata_from_prediction(prediction),
                    "climate_evidence": climate_alert_evidence_from_prediction(prediction),
                    "decision_policy": decision_policy_evaluation,
                },
            )

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
    run_purpose: str | None = None,
) -> list[RiskScore]:
    wards = Ward.objects.filter(is_active=True).order_by("name")
    inference_dataset = build_inference_feature_dataset(wards, month=month)
    inference_rows = inference_dataset.rows
    training_dataset = build_training_feature_dataset(month=month)
    training_rows = training_dataset.rows
    created_scores: list[RiskScore] = []
    ward_list = list(wards)
    benchmark_group_ref = uuid4().hex[:12] if dual_model else None
    alert_algorithm = _default_alert_algorithm(algorithm, alert_algorithm)
    run_purpose = _default_run_purpose(algorithm, run_purpose)
    operational_trust = build_operational_trust_snapshot(inference_dataset.rainfall_ingestion_run)
    decision_policy = current_ward_risk_decision_policy()

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
                decision_policy=decision_policy,
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
                    decision_policy=decision_policy,
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
