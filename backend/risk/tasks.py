import logging

from celery import shared_task
from django.utils import timezone

from risk.ml.ingestion import fetch_rainfall_for_wards
from risk.ml.pipeline import run_mock_prediction_pipeline
from risk.models import Alert, ETLHeartbeat, RiskScore, Ward
from risk.services import deliver_alert, trigger_alerts_for_riskscore


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
def trigger_alerts_task(self, risk_score_id: int, send_sms: bool = False) -> int:
    risk_score = RiskScore.objects.select_related("ward").get(id=risk_score_id)
    alerts = trigger_alerts_for_riskscore(risk_score, send_sms_enabled=send_sms)
    for alert in alerts:
        if alert.status == Alert.STATUS_QUEUED:
            deliver_alert_task.delay(alert.id)
    logger.info("trigger_alerts_task_completed", extra={"risk_score_id": risk_score_id, "alerts_created": len(alerts)})
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
