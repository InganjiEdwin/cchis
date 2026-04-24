import logging
from datetime import timedelta

from decouple import config
from django.db.models import Count, Max, Q
from django.utils import timezone

from .models import Alert, CHV, HealthFacility, RiskScore, SyncQueue, TriageSession, UssdSessionLog, Ward
from .providers import DeliveryResult, get_sms_provider


alerts_logger = logging.getLogger("risk.alerts")
ml_logger = logging.getLogger("risk.ml")


def alert_retry_delay() -> timedelta:
    return timedelta(minutes=config("ALERT_RETRY_DELAY_MINUTES", cast=int, default=5))


def build_alert_message(ward: Ward, risk_score: RiskScore) -> str:
    return (
        f"Cholera early warning for {ward.name}. "
        f"Risk level: {risk_score.risk_level}. "
        f"Predicted cases: {risk_score.predicted_cases}. "
        f"Advise households on safe water, hygiene, and early referral."
    )


def send_sms(phone_number: str, message: str, provider_name: str | None = None) -> DeliveryResult:
    provider = get_sms_provider(provider_name=provider_name)
    return provider.send(phone_number, message)


def create_alerts_for_riskscore(risk_score: RiskScore, send_sms_enabled: bool = False) -> list[Alert]:
    ward = risk_score.ward
    alerts_created: list[Alert] = []

    alerts_logger.info(
        "trigger_alerts_started",
        extra={
            "ward_id": ward.id,
            "risk_score_id": risk_score.id,
            "risk_level": risk_score.risk_level,
            "send_sms_enabled": send_sms_enabled,
        },
    )

    delivered_at = timezone.now()
    dashboard_alert = Alert.objects.create(
        ward=ward,
        risk_score=risk_score,
        channel=Alert.CHANNEL_DASHBOARD,
        recipient="dashboard",
        message=build_alert_message(ward, risk_score),
        status=Alert.STATUS_DELIVERED,
        delivery_backend="internal-dashboard",
        attempt_count=1,
        max_attempts=1,
        last_attempted_at=delivered_at,
        sent_at=delivered_at,
    )
    alerts_created.append(dashboard_alert)

    if send_sms_enabled:
        chvs = CHV.objects.filter(ward=ward, is_active=True)

        for chv in chvs:
            message = build_alert_message(ward, risk_score)
            alert = Alert.objects.create(
                ward=ward,
                risk_score=risk_score,
                channel=Alert.CHANNEL_SMS,
                recipient=chv.phone_number,
                message=message,
                status=Alert.STATUS_QUEUED,
                delivery_backend=config("SMS_PROVIDER", default="stub").strip().lower() or "stub",
                max_attempts=config("ALERT_MAX_ATTEMPTS", cast=int, default=3),
            )
            alerts_created.append(alert)

    alerts_logger.info(
        "trigger_alerts_completed",
        extra={
            "ward_id": ward.id,
            "risk_score_id": risk_score.id,
            "alerts_created": len(alerts_created),
        },
    )

    return alerts_created


def deliver_alert(alert: Alert) -> Alert:
    if alert.channel == Alert.CHANNEL_DASHBOARD:
        return alert

    if alert.channel != Alert.CHANNEL_SMS:
        alert.status = Alert.STATUS_FAILED
        alert.error_message = f"Unsupported alert channel: {alert.channel}"
        alert.next_retry_at = None
        alert.save(update_fields=["status", "error_message", "next_retry_at"])
        return alert

    attempted_at = timezone.now()
    alert.attempt_count += 1
    alert.last_attempted_at = attempted_at

    provider_name = alert.delivery_backend or None
    result = send_sms(alert.recipient, alert.message, provider_name=provider_name)
    alert.external_id = result.external_id
    alert.error_message = result.error
    alert.delivery_backend = result.provider

    if result.success:
        alert.status = Alert.STATUS_DELIVERED
        alert.sent_at = attempted_at
        alert.next_retry_at = None
    elif alert.attempt_count < alert.max_attempts:
        alert.status = Alert.STATUS_RETRY_PENDING
        alert.next_retry_at = attempted_at + alert_retry_delay()
        alert.sent_at = None
    else:
        alert.status = Alert.STATUS_FAILED
        alert.next_retry_at = None
        alert.sent_at = None

    alert.save(
        update_fields=[
            "attempt_count",
            "last_attempted_at",
            "delivery_backend",
            "external_id",
            "error_message",
            "status",
            "next_retry_at",
            "sent_at",
        ]
    )
    return alert


def trigger_alerts_for_riskscore(risk_score: RiskScore, send_sms_enabled: bool = False) -> list[Alert]:
    return create_alerts_for_riskscore(risk_score, send_sms_enabled=send_sms_enabled)


def latest_riskscore_for_ward(ward: Ward) -> RiskScore | None:
    return ward.risk_scores.order_by("-generated_at").first()


def _classify_alert_record(alert: Alert) -> dict:
    haystack = f"{alert.message} {alert.recipient} {alert.ward.name}".lower()

    if "cholera" in haystack:
        return {
            "label": "Cholera Risk",
            "tone": "red",
            "icon_key": "droplets",
            "trigger_source": "Cholera threshold exceeded",
        }
    if "flood" in haystack:
        return {
            "label": "Flood Risk",
            "tone": "blue",
            "icon_key": "waves",
            "trigger_source": "Flood proxy exceeded",
        }
    if "water" in haystack:
        return {
            "label": "Water Contamination",
            "tone": "red",
            "icon_key": "circle-alert",
            "trigger_source": "Water safety signal elevated",
        }
    if "rain" in haystack:
        return {
            "label": "Heavy Rainfall",
            "tone": "orange",
            "icon_key": "cloud-rain",
            "trigger_source": "Rainfall threshold exceeded",
        }

    return {
        "label": "Operational Alert",
        "tone": "slate",
        "icon_key": "shield-alert",
        "trigger_source": "Recorded risk threshold crossed",
    }


def _alert_status_label(status_value: str) -> str:
    if status_value == Alert.STATUS_DELIVERED:
        return "Alert Delivered Successfully"
    if status_value == Alert.STATUS_FAILED:
        return "Delivery Failed"
    if status_value == Alert.STATUS_RETRY_PENDING:
        return "Delivery Retry Pending"
    return "Queued for Dispatch"


def _alert_status_tone(status_value: str) -> str:
    if status_value == Alert.STATUS_DELIVERED:
        return "success"
    if status_value == Alert.STATUS_FAILED:
        return "danger"
    if status_value == Alert.STATUS_RETRY_PENDING:
        return "warning"
    return "default"


def _alert_channel_label(channel: str) -> str:
    if channel == Alert.CHANNEL_SMS:
        return "SMS"
    if channel == Alert.CHANNEL_WHATSAPP:
        return "WhatsApp"
    return "Dashboard"


def _alert_channel_audience(channel: str) -> str:
    if channel == Alert.CHANNEL_SMS:
        return "CHVs & officials"
    if channel == Alert.CHANNEL_WHATSAPP:
        return "Field recipients"
    return "Dashboard viewers"


def build_alert_intelligence_snapshot(
    alert: Alert,
    *,
    ward_detail: Ward | None = None,
    stale_threshold_minutes: int = 30,
) -> dict:
    classification_core = _classify_alert_record(alert)
    classification = {
        **classification_core,
        "mode": "derived_from_record_text",
    }

    risk_score_value = alert.risk_score.score if alert.risk_score else None
    if risk_score_value is not None and risk_score_value >= 75:
        risk_context = {
            "level_label": "High Risk",
            "trend_label": "Escalating",
            "summary": "Threshold crossed in the recorded risk score. Review linked ward and delivery records closely.",
            "recorded_risk_score": risk_score_value,
            "threshold": 75,
            "mode": "derived_from_risk_score",
        }
    elif risk_score_value is not None and risk_score_value >= 40:
        risk_context = {
            "level_label": "Medium Risk",
            "trend_label": "Monitoring",
            "summary": "Watch closely and prepare ward follow-up if indicators rise again.",
            "recorded_risk_score": risk_score_value,
            "threshold": 75,
            "mode": "derived_from_risk_score",
        }
    else:
        risk_context = {
            "level_label": "Low Risk" if risk_score_value is not None else "Risk Score Unavailable",
            "trend_label": "Stable" if risk_score_value is not None else "Unknown",
            "summary": (
                "Threshold not crossed. Maintain routine monitoring and review later records if conditions change."
                if risk_score_value is not None
                else "No linked risk score is available for interpretation on this alert record."
            ),
            "recorded_risk_score": risk_score_value,
            "threshold": 75 if risk_score_value is not None else None,
            "mode": "derived_from_risk_score" if risk_score_value is not None else "unavailable",
        }

    delivery = {
        "channel_label": _alert_channel_label(alert.channel),
        "audience_label": _alert_channel_audience(alert.channel),
        "status_label": _alert_status_label(alert.status),
        "status_tone": _alert_status_tone(alert.status),
        "recipient_count": 1,
        "mode": "backend_record_fields",
    }

    current_state = [
        {
            "label": (
                "Alert delivered"
                if alert.status == Alert.STATUS_DELIVERED
                else "Delivery blocked"
                if alert.status == Alert.STATUS_FAILED
                else "Delivery still in progress"
            ),
            "tone": "warning" if alert.status == Alert.STATUS_FAILED else "success",
        },
        {
            "label": (
                "This alert record failed delivery"
                if alert.status == Alert.STATUS_FAILED
                else "A retry is still pending"
                if alert.status == Alert.STATUS_RETRY_PENDING
                else "No active delivery failure recorded"
            ),
            "tone": "warning" if alert.status in {Alert.STATUS_FAILED, Alert.STATUS_RETRY_PENDING} else "success",
        },
        {
            "label": (
                "High ward risk accompanies this alert"
                if risk_score_value is not None and risk_score_value >= 75
                else "No high ward-risk threshold recorded"
            ),
            "tone": "warning" if risk_score_value is not None and risk_score_value >= 75 else "neutral",
        },
    ]

    timeline = [
        {
            "id": "triggered",
            "title": "Alert triggered",
            "description": f"Alert record generated from the risk model using {classification_core['trigger_source'].lower()} signals.",
            "timestamp": alert.created_at,
            "tone": "primary",
            "category": "system",
            "meta": f"Risk score: {round(risk_score_value)}/100" if risk_score_value is not None else None,
            "details": [f"Trigger source: {classification_core['trigger_source']}"],
        },
        {
            "id": "created",
            "title": "Alert record created",
            "description": f"A {_alert_channel_label(alert.channel).lower()} alert record was created for {alert.ward.name}.",
            "timestamp": alert.created_at,
            "tone": "neutral",
            "category": "system",
            "meta": None,
            "details": [
                f"Recipient: {alert.recipient}",
                f"Channel: {_alert_channel_label(alert.channel)}",
            ],
        },
        {
            "id": "dispatch",
            "title": "Delivery attempt state",
            "description": f"Latest delivery activity is tracked through {alert.delivery_backend or 'the recorded backend'}.",
            "timestamp": alert.last_attempted_at or alert.sent_at or alert.created_at,
            "tone": (
                "danger"
                if alert.status == Alert.STATUS_FAILED
                else "success"
                if alert.status == Alert.STATUS_DELIVERED
                else "progress"
            ),
            "category": "delivery",
            "meta": None,
            "details": [
                f"Attempt count: {alert.attempt_count}/{alert.max_attempts}",
                f"Backend: {alert.delivery_backend or 'Unspecified'}",
            ],
        },
        {
            "id": "delivery-status",
            "title": "Recorded delivery outcome",
            "description": (
                "This alert record is marked as delivered."
                if alert.status == Alert.STATUS_DELIVERED
                else "This alert record is marked as failed and needs operator review."
                if alert.status == Alert.STATUS_FAILED
                else "This alert record is waiting for another delivery attempt."
                if alert.status == Alert.STATUS_RETRY_PENDING
                else "This alert record is queued and awaiting delivery processing."
            ),
            "timestamp": alert.sent_at or alert.last_attempted_at,
            "tone": (
                "success"
                if alert.status == Alert.STATUS_DELIVERED
                else "danger"
                if alert.status == Alert.STATUS_FAILED
                else "warning"
            ),
            "category": "delivery",
            "meta": None,
            "details": [
                f"Status: {_alert_status_label(alert.status)}",
                f"Last attempted at: {alert.last_attempted_at.isoformat() if alert.last_attempted_at else 'No timestamp'}",
                f"Sent at: {alert.sent_at.isoformat() if alert.sent_at else 'No timestamp'}",
            ],
        },
    ]
    if alert.next_retry_at:
        timeline.append(
            {
                "id": "retry",
                "title": "Next retry scheduled",
                "description": "The backend has recorded a future retry time for this alert record.",
                "timestamp": alert.next_retry_at,
                "tone": "warning",
                "category": "delivery",
                "meta": None,
                "details": [f"Next retry at: {alert.next_retry_at.isoformat()}"],
            }
        )

    updated_candidates = [
        alert.sent_at,
        alert.last_attempted_at,
        alert.next_retry_at,
        alert.created_at,
        ward_detail.updated_at if ward_detail else None,
    ]
    updated_at = max((value for value in updated_candidates if value is not None), default=None)
    is_stale = True
    if updated_at is not None:
        is_stale = (timezone.now() - updated_at).total_seconds() / 60 > stale_threshold_minutes

    freshness = {
        "updated_at": updated_at,
        "is_stale": is_stale,
        "stale_threshold_minutes": stale_threshold_minutes,
        "mode": "timestamp_and_record_availability",
    }

    capabilities = {
        "can_resend": False,
        "can_recall": False,
        "can_notify_facilities": False,
        "can_send_follow_up": False,
        "mode": "read_only_detail_with_trigger_flow_elsewhere",
    }

    return {
        "alert": alert,
        "ward_detail": ward_detail,
        "classification": classification,
        "risk_context": risk_context,
        "delivery": delivery,
        "current_state": current_state,
        "freshness": freshness,
        "timeline": timeline,
        "capabilities": capabilities,
    }


def build_ward_intelligence_snapshot(ward: Ward, *, stale_threshold_minutes: int = 120) -> dict:
    risk_history = list(
        ward.risk_scores.select_related("model_run").order_by("-generated_at")[:6]
    )
    related_alerts = list(
        ward.alerts.select_related("risk_score").order_by("-created_at")[:6]
    )
    latest_risk = risk_history[0] if risk_history else latest_riskscore_for_ward(ward)
    previous_risk = risk_history[1] if len(risk_history) > 1 else None

    generated_at = latest_risk.generated_at if latest_risk else None
    is_stale = True
    if generated_at is not None:
        is_stale = (timezone.now() - generated_at).total_seconds() / 60 > stale_threshold_minutes

    current_risk = {
        "risk_level": latest_risk.risk_level if latest_risk else ward.current_risk_level,
        "risk_score": latest_risk.score if latest_risk else ward.current_risk_score,
        "predicted_cases": latest_risk.predicted_cases if latest_risk else 0,
        "generated_at": generated_at,
        "source": latest_risk.source if latest_risk else None,
        "model_version": latest_risk.model_version if latest_risk else None,
        "model_run_status": latest_risk.model_run.status if latest_risk and latest_risk.model_run else None,
    }

    if latest_risk and previous_risk:
        delta_points = round((latest_risk.score - previous_risk.score) * 100)
        if abs(delta_points) < 1:
            trend = {
                "label": "Stable versus previous run",
                "direction": "flat",
                "delta_points": 0,
                "mode": "derived_from_recent_history",
            }
        else:
            trend = {
                "label": f"{delta_points:+d} points vs previous run",
                "direction": "up" if delta_points > 0 else "down",
                "delta_points": delta_points,
                "mode": "derived_from_recent_history",
            }
    else:
        trend = {
            "label": "No previous run available",
            "direction": "flat",
            "delta_points": None,
            "mode": "derived_from_recent_history",
        }

    driver_items: list[dict] = []
    if latest_risk:
        if latest_risk.rainfall_mm > 80:
            driver_items.append(
                {
                    "text": f"Rainfall is elevated at {latest_risk.rainfall_mm:.0f} mm in the latest record.",
                    "tone": "critical",
                    "source_field": "rainfall_mm",
                }
            )
        if latest_risk.flood_indicator > 0:
            driver_items.append(
                {
                    "text": "Flood indicator is elevated in the latest risk record.",
                    "tone": "warning",
                    "source_field": "flood_indicator",
                }
            )
        if latest_risk.predicted_cases > 0:
            driver_items.append(
                {
                    "text": f"Predicted cases are recorded at {latest_risk.predicted_cases} in the latest run.",
                    "tone": "info",
                    "source_field": "predicted_cases",
                }
            )
        if latest_risk.model_run:
            driver_items.append(
                {
                    "text": f"Latest model run status is {latest_risk.model_run.status.lower()}.",
                    "tone": "info",
                    "source_field": "model_run.status",
                }
            )

    driver_summary = {
        "mode": "derived_from_latest_record" if latest_risk else "unavailable",
        "items": driver_items
        or [
            {
                "text": "No recent driver summary is available from the latest ward record yet.",
                "tone": "info",
                "source_field": None,
            }
        ],
    }

    current_risk_level = current_risk["risk_level"] or "UNKNOWN"
    if current_risk_level == Ward.RISK_HIGH:
        guidance_items = [
            "Send CHV alert using the supported trigger flow.",
            "Review hygiene and safe-water messaging readiness for this ward.",
            "Check ORS and dehydration-response readiness before case pressure rises.",
            "Watch the next model run and linked alerts closely for escalation.",
        ]
    elif current_risk_level == Ward.RISK_MEDIUM:
        guidance_items = [
            "Increase review cadence for the next ward update.",
            "Prepare outreach messaging in case this ward escalates.",
            "Confirm local readiness for rapid response if alert volume rises.",
        ]
    elif current_risk_level == Ward.RISK_LOW:
        guidance_items = [
            "Continue routine surveillance for this ward.",
            "Monitor for score movement in the next model run.",
            "Keep reporting continuity in place so risk changes are visible early.",
        ]
    else:
        guidance_items = [
            "Continue monitoring until a fresher ward record is available.",
            "Review the next model run before taking new action from this page.",
        ]

    guidance_summary = {
        "mode": "static_risk_playbook",
        "items": [
            {"text": text, "urgency": "review_only" if index else "primary"}
            for index, text in enumerate(guidance_items)
        ],
    }

    freshness = {
        "generated_at": generated_at,
        "is_stale": is_stale,
        "stale_threshold_minutes": stale_threshold_minutes,
        "history_count": len(risk_history),
        "alert_count": len(related_alerts),
        "mode": "timestamp_and_record_availability",
    }

    return {
        "ward": ward,
        "current_risk": current_risk,
        "trend": trend,
        "driver_summary": driver_summary,
        "guidance_summary": guidance_summary,
        "freshness": freshness,
        "risk_history": risk_history,
        "related_alerts": related_alerts,
    }


def generate_triage_recommendation(
    ward: Ward,
    diarrhea: bool,
    vomiting: bool,
    dehydration: bool,
    fever: bool,
) -> tuple[str, bool]:
    ward_risk = ward.current_risk_level

    if diarrhea and vomiting and dehydration:
        if ward_risk == Ward.RISK_HIGH:
            return (
                "High cholera suspicion. Start ORS immediately, assess dehydration urgently, "
                "refer to nearest health facility now, and alert supervisor.",
                True,
            )
        return (
            "Severe diarrhea case. Start ORS immediately, assess dehydration, "
            "and refer to a health facility urgently.",
            True,
        )

    if diarrhea and dehydration:
        return (
            "Possible acute watery diarrhea with dehydration. Start ORS, monitor closely, "
            "and refer if symptoms worsen.",
            True,
        )

    if diarrhea and vomiting:
        return (
            "Possible diarrheal illness. Give ORS, reinforce safe water and hygiene guidance, "
            "and monitor closely.",
            False,
        )

    if fever and ward_risk == Ward.RISK_HIGH:
        return (
            "Fever reported in high-risk ward. Assess for malaria and diarrheal symptoms, "
            "advise prompt testing and follow-up.",
            False,
        )

    if diarrhea:
        return (
            "Provide ORS, advise safe water use, handwashing, and monitor for worsening symptoms "
            "or dehydration signs.",
            False,
        )

    return (
        "No immediate cholera danger signs identified. Continue observation, reinforce prevention "
        "messaging, and follow routine guidance.",
        False,
    )


def create_triage_session(
    ward: Ward,
    phone_number: str,
    diarrhea: bool,
    vomiting: bool,
    dehydration: bool,
    fever: bool,
    text_input: str = "",
    channel: str = "USSD",
) -> TriageSession:
    recommendation, referral_needed = generate_triage_recommendation(
        ward=ward,
        diarrhea=diarrhea,
        vomiting=vomiting,
        dehydration=dehydration,
        fever=fever,
    )
    referral_facility = None

    if referral_needed:
        referral_facility = (
            HealthFacility.objects.filter(ward=ward, is_active=True)
            .order_by("name")
            .first()
        )

    return TriageSession.objects.create(
        channel=channel,
        phone_number=phone_number,
        ward=ward,
        referral_facility=referral_facility,
        text_input=text_input,
        diarrhea=diarrhea,
        vomiting=vomiting,
        dehydration=dehydration,
        fever=fever,
        recommendation=recommendation,
        referral_needed=referral_needed,
    )


def process_sync_payload(
    *,
    ward: Ward,
    phone_number: str,
    source_device_id: str,
    payload: dict,
) -> tuple[SyncQueue, TriageSession, bool]:
    client_submission_id = (payload.get("client_submission_id") or "").strip()
    if not client_submission_id:
        raise ValueError("client_submission_id is required.")

    existing_sync_item = (
        SyncQueue.objects.select_related("triage_session")
        .filter(
            source_device_id=source_device_id,
            client_submission_id=client_submission_id,
        )
        .first()
    )
    if existing_sync_item and existing_sync_item.triage_session:
        return existing_sync_item, existing_sync_item.triage_session, True

    sync_item = SyncQueue.objects.create(
        source_device_id=source_device_id,
        client_submission_id=client_submission_id,
        phone_number=phone_number,
        ward=ward,
        payload=payload,
        status=SyncQueue.STATUS_PENDING,
    )

    try:
        triage_session = create_triage_session(
            ward=ward,
            phone_number=phone_number,
            diarrhea=payload.get("diarrhea", False),
            vomiting=payload.get("vomiting", False),
            dehydration=payload.get("dehydration", False),
            fever=payload.get("fever", False),
            text_input=payload.get("text_input", ""),
            channel="OFFLINE_SYNC",
        )
        sync_item.status = SyncQueue.STATUS_PROCESSED
        sync_item.triage_session = triage_session
        sync_item.processed_at = timezone.now()
        sync_item.save(update_fields=["status", "triage_session", "processed_at"])
        return sync_item, triage_session, False
    except Exception as exc:
        sync_item.status = SyncQueue.STATUS_FAILED
        sync_item.error_message = str(exc)
        sync_item.processed_at = timezone.now()
        sync_item.save(update_fields=["status", "error_message", "processed_at"])
        raise


def _derive_operational_status(is_active: bool, last_activity_at):
    if not is_active:
        return "OFFLINE"
    if not last_activity_at:
        return "IDLE"

    age = timezone.now() - last_activity_at
    if age <= timedelta(hours=1):
        return "ACTIVE"
    if age <= timedelta(hours=24):
        return "IDLE"
    return "OFFLINE"


def _derive_sync_health(last_sync_at):
    if not last_sync_at:
        return "OFFLINE"

    age = timezone.now() - last_sync_at
    if age <= timedelta(minutes=30):
        return "ONLINE"
    if age <= timedelta(hours=6):
        return "DELAYED"
    return "OFFLINE"


def build_chv_operations_snapshot(chv_queryset) -> list[dict]:
    now = timezone.now()
    since_24h = now - timedelta(hours=24)
    chvs = list(chv_queryset.select_related("ward"))
    phone_numbers = [chv.phone_number for chv in chvs if chv.phone_number]
    ward_ids = [chv.ward_id for chv in chvs]

    sync_rows = SyncQueue.objects.filter(phone_number__in=phone_numbers).values("phone_number").annotate(
        latest_activity=Max("created_at"),
        latest_sync=Max("processed_at"),
        sync_payloads_24h=Count("id", filter=Q(created_at__gte=since_24h)),
    )
    triage_rows = TriageSession.objects.filter(phone_number__in=phone_numbers).values("phone_number").annotate(
        latest_activity=Max("created_at"),
        triage_sessions_24h=Count("id", filter=Q(created_at__gte=since_24h)),
        referrals_24h=Count("id", filter=Q(created_at__gte=since_24h, referral_needed=True)),
    )
    ussd_rows = UssdSessionLog.objects.filter(phone_number__in=phone_numbers).values("phone_number").annotate(
        latest_activity=Max("created_at"),
        ussd_sessions_24h=Count("id", filter=Q(created_at__gte=since_24h)),
    )
    alert_rows = Alert.objects.filter(ward_id__in=ward_ids).values("ward_id").annotate(
        total=Count("id"),
        delivered=Count("id", filter=Q(status=Alert.STATUS_DELIVERED)),
    )

    sync_by_phone = {row["phone_number"]: row for row in sync_rows}
    triage_by_phone = {row["phone_number"]: row for row in triage_rows}
    ussd_by_phone = {row["phone_number"]: row for row in ussd_rows}
    alerts_by_ward = {row["ward_id"]: row for row in alert_rows}

    snapshot = []
    for chv in chvs:
        sync_row = sync_by_phone.get(chv.phone_number, {})
        triage_row = triage_by_phone.get(chv.phone_number, {})
        ussd_row = ussd_by_phone.get(chv.phone_number, {})
        ward_alert_row = alerts_by_ward.get(chv.ward_id, {})

        last_sync_at = sync_row.get("latest_sync")
        candidate_activity_times = [
            value
            for value in [
                last_sync_at,
                sync_row.get("latest_activity"),
                triage_row.get("latest_activity"),
                ussd_row.get("latest_activity"),
            ]
            if value
        ]
        last_activity_at = max(candidate_activity_times) if candidate_activity_times else None

        snapshot.append(
            {
                "id": chv.id,
                "name": chv.name,
                "phone_number": chv.phone_number,
                "language": chv.language,
                "is_active": chv.is_active,
                "ward": chv.ward_id,
                "ward_name": chv.ward.name,
                "created_at": chv.created_at,
                "last_sync_at": last_sync_at,
                "last_activity_at": last_activity_at,
                "operational_status": _derive_operational_status(chv.is_active, last_activity_at),
                "sync_health": _derive_sync_health(last_sync_at),
                "triage_sessions_24h": triage_row.get("triage_sessions_24h", 0),
                "referrals_24h": triage_row.get("referrals_24h", 0),
                "sync_payloads_24h": sync_row.get("sync_payloads_24h", 0),
                "ussd_sessions_24h": ussd_row.get("ussd_sessions_24h", 0),
                "ward_alerts_total": ward_alert_row.get("total", 0),
                "ward_alerts_delivered": ward_alert_row.get("delivered", 0),
            }
        )

    return snapshot
