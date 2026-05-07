import logging

from celery import shared_task
from django.utils import timezone

from accounts.models import User

from risk.facility_forecasting import run_facility_burden_forecast_pipeline
from risk.facility_readiness_ingestion import run_facility_readiness_snapshot_ingestion
from risk.ml.ingestion import fetch_rainfall_for_wards
from risk.ml.pipeline import run_mock_prediction_pipeline
from risk.models import Alert, ETLHeartbeat, PopulationExposureIngestionRun, RiskScore, SourceDataUploadBatch, SourceDataUploadEvent, SurveillanceIngestionRun, Ward
from risk.population_exposure_ingestion import parse_source_timestamp, run_population_exposure_csv_ingestion
from risk.services import deliver_alert, trigger_alerts_for_riskscore
from risk.source_data.imports import run_confirmed_source_data_import
from risk.source_data.downstream import run_source_data_downstream_action
from risk.source_data.events import record_source_data_upload_system_event
from risk.source_data.operations import cleanup_expired_source_data_artifacts
from risk.source_data.connectors import run_source_data_connector_refresh
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
def run_facility_readiness_snapshot_ingestion_task(
    self,
    file_path: str,
    source_name: str,
    source_timestamp: str | None = None,
    reporting_period_start: str | None = None,
    reporting_period_end: str | None = None,
    source_ref: str = "",
    operator_note: str = "",
) -> int:
    run = run_facility_readiness_snapshot_ingestion(
        file_path=file_path,
        source_name=source_name,
        source_timestamp=parse_source_timestamp(source_timestamp),
        reporting_period_start=parse_surveillance_date(reporting_period_start),
        reporting_period_end=parse_surveillance_date(reporting_period_end),
        source_ref=source_ref,
        operator_note=operator_note,
        execution_mode="scheduled",
    )
    logger.info(
        "run_facility_readiness_snapshot_ingestion_task_completed",
        extra={
            "ingestion_run_id": run.id,
            "status": run.status,
            "source_name": run.source_name,
            "records_seen": run.records_seen,
            "records_loaded": run.records_loaded,
            "records_rejected": run.records_rejected,
        },
    )
    return run.id


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    dont_autoretry_for=(ValueError,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def import_source_data_upload_batch_task(self, batch_id: int, actor_id: int | None = None) -> int:
    batch = SourceDataUploadBatch.objects.get(pk=batch_id)
    actor = User.objects.filter(pk=actor_id).first() if actor_id is not None else None
    try:
        imported_batch = run_confirmed_source_data_import(batch, actor=actor, worker_execution=True)
    except Exception as error:
        SourceDataUploadBatch.objects.filter(pk=batch_id).update(
            status=SourceDataUploadBatch.STATUS_IMPORT_FAILED,
            import_status=SourceDataUploadBatch.IMPORT_FAILED,
            metadata={
                **(batch.metadata or {}),
                "import_summary": {
                    **((batch.metadata or {}).get("import_summary") or {}),
                    "error_summary": str(error),
                    "celery_task_id": self.request.id,
                    "worker_execution": True,
                },
            },
            updated_at=timezone.now(),
        )
        failed_batch = SourceDataUploadBatch.objects.get(pk=batch_id)
        record_source_data_upload_system_event(
            batch=failed_batch,
            event_type=SourceDataUploadEvent.EVENT_IMPORT_FAILED,
            actor=actor,
            metadata={"error_summary": str(error), "celery_task_id": self.request.id},
        )
        ETLHeartbeat.objects.create(
            component=ETLHeartbeat.COMPONENT_WORKER,
            task_name="risk.tasks.import_source_data_upload_batch_task",
            status=ETLHeartbeat.STATUS_FAILED,
            details={
                "source_data_upload_batch_id": batch_id,
                "source_data_upload_public_id": str(batch.public_id),
                "error_summary": str(error),
                "celery_task_id": self.request.id,
            },
        )
        raise
    logger.info(
        "import_source_data_upload_batch_task_completed",
        extra={
            "source_data_upload_batch_id": imported_batch.id,
            "source_data_upload_public_id": str(imported_batch.public_id),
            "status": imported_batch.status,
            "import_status": imported_batch.import_status,
            "domain_ingestion_run_type": imported_batch.domain_ingestion_run_type,
            "domain_ingestion_run_id": imported_batch.domain_ingestion_run_id,
        },
    )
    return imported_batch.id


@shared_task(bind=True)
def cleanup_source_data_upload_artifacts_task(self, dry_run: bool = False, limit: int = 500) -> dict:
    result = cleanup_expired_source_data_artifacts(dry_run=dry_run, limit=limit)
    logger.info("cleanup_source_data_upload_artifacts_task_completed", extra=result)
    return result


@shared_task(bind=True)
def run_source_data_connector_refresh_task(
    self,
    connector_key: str,
    actor_id: int | None = None,
    options: dict | None = None,
    force: bool = False,
) -> int:
    actor = User.objects.filter(pk=actor_id).first() if actor_id is not None else None
    run = run_source_data_connector_refresh(
        connector_key=connector_key,
        actor=actor,
        options=options or {},
        force=force,
    )
    ETLHeartbeat.objects.create(
        component=ETLHeartbeat.COMPONENT_WORKER,
        task_name="risk.tasks.run_source_data_connector_refresh_task",
        status=ETLHeartbeat.STATUS_OK if run.status == "success" else ETLHeartbeat.STATUS_WARN,
        details={
            "connector_key": connector_key,
            "connector_run_id": run.id,
            "status": run.status,
            "target_feed_key": run.target_feed_key,
            "upload_batch_public_id": str(run.upload_batch.public_id) if run.upload_batch_id else "",
        },
    )
    logger.info(
        "run_source_data_connector_refresh_task_completed",
        extra={
            "connector_key": connector_key,
            "connector_run_id": run.id,
            "status": run.status,
            "target_feed_key": run.target_feed_key,
        },
    )
    return run.id


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    dont_autoretry_for=(ValueError,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def run_source_data_downstream_action_task(
    self,
    batch_id: int,
    action_key: str,
    actor_id: int | None = None,
    options: dict | None = None,
) -> dict:
    batch = SourceDataUploadBatch.objects.select_related(
        "surveillance_ingestion_run",
        "population_exposure_ingestion_run",
    ).get(pk=batch_id)
    actor = User.objects.filter(pk=actor_id).first() if actor_id is not None else None
    result = run_source_data_downstream_action(
        batch=batch,
        action_key=action_key,
        actor=actor,
        options=options or {},
        worker_execution=True,
    )
    logger.info(
        "run_source_data_downstream_action_task_completed",
        extra={
            "source_data_upload_batch_id": batch.id,
            "source_data_upload_public_id": str(batch.public_id),
            "action_key": action_key,
            "action_status": result.get("action_status"),
        },
    )
    return result


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    dont_autoretry_for=(ValueError,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def trigger_alerts_task(
    self,
    risk_score_id: int,
    send_sms: bool = False,
    trigger_type: str | None = None,
    message_override: str | None = None,
    guided_request_metadata: dict | None = None,
    template_key: str = "",
    template_version: int | None = None,
    template_language: str | None = None,
    template_context: dict | None = None,
) -> int:
    risk_score = RiskScore.objects.select_related("ward", "model_run").get(id=risk_score_id)
    alerts = trigger_alerts_for_riskscore(
        risk_score,
        send_sms_enabled=send_sms,
        trigger_type=trigger_type,
        message_override=message_override,
        guided_request_metadata=guided_request_metadata,
        template_key=template_key,
        template_version=template_version,
        template_language=template_language,
        template_context=template_context,
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
    include_seeded_training_labels: bool = False,
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
        include_seeded_training_labels=include_seeded_training_labels,
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
