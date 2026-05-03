import logging

from celery import shared_task
from django.utils import timezone

from risk.facility_forecasting import run_facility_burden_forecast_pipeline
from risk.ml.ingestion import fetch_rainfall_for_wards
from risk.ml.pipeline import run_mock_prediction_pipeline
from risk.models import Alert, ETLHeartbeat, PopulationExposureIngestionRun, RiskScore, SurveillanceIngestionRun, Ward
from risk.population_exposure_ingestion import parse_source_timestamp, run_population_exposure_csv_ingestion
from risk.services import deliver_alert, trigger_alerts_for_riskscore
from risk.surveillance_ingestion import (
    parse_surveillance_date,
    parse_surveillance_source_timestamp,
    run_surveillance_csv_ingestion,
)


logger = logging.getLogger("risk")


@shared_task(bind=True)
def record_etl_heartbeat_task(self) -> int:
    task_name = "risk.tasks.record_etl_heartbeat_task"
    recorded_at = timezone.now()
    ETLHeartbeat.objects.bulk_create(
        [
            ETLHeartbeat(
                component=ETLHeartbeat.COMPONENT_SCHEDULER,
                task_name=task_name,
                status=ETLHeartbeat.STATUS_OK,
                details={"origin": "celery-beat"},
                recorded_at=recorded_at,
            ),
            ETLHeartbeat(
                component=ETLHeartbeat.COMPONENT_WORKER,
                task_name=task_name,
                status=ETLHeartbeat.STATUS_OK,
                details={"origin": "celery-worker", "task_id": self.request.id},
                recorded_at=recorded_at,
            ),
        ]
    )
    logger.info(
        "record_etl_heartbeat_task_completed",
        extra={"task_name": task_name, "recorded_at": recorded_at.isoformat()},
    )
    return 2


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def run_rainfall_ingestion_task(self) -> int:
    wards = list(Ward.objects.filter(is_active=True).order_by("name"))
    if not wards:
        logger.info("run_rainfall_ingestion_task_completed", extra={"ward_count": 0})
        return 0

    _, ingestion_run = fetch_rainfall_for_wards(wards, return_ingestion_run=True)
    logger.info(
        "run_rainfall_ingestion_task_completed",
        extra={
            "ward_count": len(wards),
            "ingestion_run_id": ingestion_run.id,
            "status": ingestion_run.status,
            "source_kind": ingestion_run.source_kind,
            "freshness_state": ingestion_run.freshness_state,
        },
    )
    return ingestion_run.id


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def run_population_exposure_ingestion_task(
    self,
    file_path: str,
    source_name: str,
    source_type: str,
    source_timestamp: str | None = None,
    release_version: str = "",
    source_ref: str = "",
    correction_mode: str = "original",
    replacement_reason: str = "",
    operator_note: str = "",
    replaces_run_id: int | None = None,
) -> int:
    replaces_run = (
        PopulationExposureIngestionRun.objects.get(pk=replaces_run_id)
        if replaces_run_id is not None
        else None
    )
    run = run_population_exposure_csv_ingestion(
        file_path=file_path,
        source_name=source_name,
        source_type=source_type,
        source_timestamp=parse_source_timestamp(source_timestamp),
        release_version=release_version,
        source_ref=source_ref,
        correction_mode=correction_mode,
        replacement_reason=replacement_reason,
        operator_note=operator_note,
        execution_mode="scheduled",
        replaces_run=replaces_run,
    )
    logger.info(
        "run_population_exposure_ingestion_task_completed",
        extra={
            "ingestion_run_id": run.id,
            "status": run.status,
            "source_name": run.source_name,
            "source_type": run.source_type,
            "release_version": run.release_version,
            "records_seen": run.records_seen,
            "records_loaded": run.records_loaded,
            "records_rejected": run.records_rejected,
        },
    )
    return run.id


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def run_surveillance_ingestion_task(
    self,
    file_path: str,
    source_name: str,
    source_type: str,
    source_timestamp: str | None = None,
    reporting_period_start: str | None = None,
    reporting_period_end: str | None = None,
    source_ref: str = "",
    correction_mode: str = "original",
    correction_reason: str = "",
    operator_note: str = "",
    execution_mode: str = SurveillanceIngestionRun.EXECUTION_SCHEDULED,
    regenerate_label_windows: bool = False,
    label_dataset_role: str = "evaluation",
    label_window_days: int = 7,
    label_step_days: int = 7,
    include_seeded_labels: bool = False,
) -> int:
    run = run_surveillance_csv_ingestion(
        file_path=file_path,
        source_name=source_name,
        source_type=source_type,
        source_timestamp=parse_surveillance_source_timestamp(source_timestamp),
        reporting_period_start=parse_surveillance_date(reporting_period_start),
        reporting_period_end=parse_surveillance_date(reporting_period_end),
        source_ref=source_ref,
        correction_mode=correction_mode,
        correction_reason=correction_reason,
        operator_note=operator_note,
        execution_mode=execution_mode,
        regenerate_label_windows=regenerate_label_windows,
        label_dataset_role=label_dataset_role,
        label_window_days=label_window_days,
        label_step_days=label_step_days,
        include_seeded_labels=include_seeded_labels,
    )
    logger.info(
        "run_surveillance_ingestion_task_completed",
        extra={
            "ingestion_run_id": run.id,
            "status": run.status,
            "source_name": run.source_name,
            "source_type": run.source_type,
            "reporting_period_start": run.reporting_period_start.isoformat() if run.reporting_period_start else None,
            "reporting_period_end": run.reporting_period_end.isoformat() if run.reporting_period_end else None,
            "records_seen": run.records_seen,
            "records_loaded": run.records_loaded,
            "records_rejected": run.records_rejected,
            "execution_mode": run.execution_mode,
            "feed_policy": run.results.get("feed_policy") if isinstance(run.results, dict) else None,
            "downstream_label_regeneration": (
                run.results.get("downstream_label_regeneration") if isinstance(run.results, dict) else None
            ),
        },
    )
    return run.id


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def trigger_alerts_task(
    self,
    risk_score_id: int,
    send_sms: bool = False,
    trigger_type: str | None = None,
    message_override: str | None = None,
    guided_request_metadata: dict | None = None,
) -> int:
    risk_score = RiskScore.objects.select_related("ward", "model_run").get(id=risk_score_id)
    alerts = trigger_alerts_for_riskscore(
        risk_score,
        send_sms_enabled=send_sms,
        trigger_type=trigger_type,
        message_override=message_override,
        guided_request_metadata=guided_request_metadata,
    )
    for alert in alerts:
        if alert.status == Alert.STATUS_QUEUED:
            deliver_alert_task.delay(alert.id)
    logger.info(
        "trigger_alerts_task_completed",
        extra={
            "risk_score_id": risk_score_id,
            "alerts_created": len(alerts),
            "trigger_type": trigger_type,
            "message_override_used": bool(message_override),
            "guided_request_metadata_recorded": bool(guided_request_metadata),
        },
    )
    return len(alerts)


@shared_task(bind=True)
def deliver_alert_task(self, alert_id: int) -> str:
    alert = Alert.objects.get(id=alert_id)
    alert = deliver_alert(alert)

    if alert.status == Alert.STATUS_RETRY_PENDING and alert.next_retry_at:
        delay_seconds = max(int((alert.next_retry_at - timezone.now()).total_seconds()), 0)
        deliver_alert_task.apply_async(args=[alert.id], countdown=delay_seconds)

    logger.info(
        "deliver_alert_task_completed",
        extra={
            "alert_id": alert.id,
            "status": alert.status,
            "attempt_count": alert.attempt_count,
        },
    )
    return alert.status




@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def run_risk_model_task(
    self,
    month: int | None = None,
    model_version: str = "lr-v1",
    algorithm: str = "logistic_regression",
    trigger_alerts: bool = False,
    send_sms: bool = False,
    dual_model: bool = False,
    benchmark_algorithm: str = "random_forest",
    benchmark_model_version: str = "rf-v1",
    alert_algorithm: str | None = None,
    execution_context: str = "scheduled_task",
    run_purpose: str = "live_scoring",
) -> int:
    if month is None:
        month = timezone.now().month

    created_scores = run_mock_prediction_pipeline(
        month=month,
        model_version=model_version,
        algorithm=algorithm,
        trigger_alerts=trigger_alerts,
        send_sms=send_sms,
        dual_model=dual_model,
        benchmark_algorithm=benchmark_algorithm,
        benchmark_model_version=benchmark_model_version,
        alert_algorithm=alert_algorithm,
        execution_context=execution_context,
        run_purpose=run_purpose,
    )
    logger.info(
        "run_risk_model_task_completed",
        extra={
            "scores_created": len(created_scores),
            "model_version": model_version,
            "algorithm": algorithm,
            "month": month,
            "dual_model": dual_model,
            "execution_context": execution_context,
            "run_purpose": run_purpose,
        },
    )
    return len(created_scores)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def run_random_forest_benchmark_task(
    self,
    month: int | None = None,
    model_version: str = "rf-v1",
) -> int:
    if month is None:
        month = timezone.now().month

    created_scores = run_mock_prediction_pipeline(
        month=month,
        model_version=model_version,
        algorithm="random_forest",
        trigger_alerts=False,
        send_sms=False,
        dual_model=False,
        execution_context="benchmark_task",
        run_purpose="benchmark_scoring",
    )
    logger.info(
        "run_random_forest_benchmark_task_completed",
        extra={
            "scores_created": len(created_scores),
            "model_version": model_version,
            "algorithm": "random_forest",
            "month": month,
        },
    )
    return len(created_scores)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def run_facility_burden_forecast_task(
    self,
    model_version: str = "fnb-v1",
    horizon_days: int = 7,
) -> int:
    run = run_facility_burden_forecast_pipeline(
        model_version=model_version,
        horizon_days=horizon_days,
        execution_context="scheduled_task",
        run_purpose="forecast_scoring",
    )
    logger.info(
        "run_facility_burden_forecast_task_completed",
        extra={
            "forecast_run_id": run.id,
            "model_version": run.model_version,
            "algorithm": run.algorithm_name,
            "horizon_days": run.horizon_days,
            "status": run.status,
        },
    )
    return run.id
