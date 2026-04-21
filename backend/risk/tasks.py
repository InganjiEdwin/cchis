import logging

from celery import shared_task
from django.utils import timezone

from risk.ml.pipeline import run_mock_prediction_pipeline
from risk.models import Alert, RiskScore
from risk.services import deliver_alert, trigger_alerts_for_riskscore


logger = logging.getLogger("risk")


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
    trigger_alerts: bool = False,
    send_sms: bool = False,
) -> int:
    if month is None:
        month = timezone.now().month

    created_scores = run_mock_prediction_pipeline(
        month=month,
        model_version=model_version,
        trigger_alerts=trigger_alerts,
        send_sms=send_sms,
    )
    logger.info(
        "run_risk_model_task_completed",
        extra={"scores_created": len(created_scores), "model_version": model_version, "month": month},
    )
    return len(created_scores)
