from __future__ import annotations

from dataclasses import dataclass

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from accounts.models import User
from communications.services import send_email

from .models import Alert, CHVCoverageRequestEmailDelivery, CHVCoverageRequestEvent, DashboardNotification, DashboardNotificationEvent, HealthFacility, IngestionRun, ModelRun, Ward
from .serializers import DashboardNotificationSerializer
from .services import latest_riskscore_for_ward


STALE_THRESHOLD_MINUTES = 120
DASHBOARD_ROLES = [User.ROLE_ADMIN, User.ROLE_SUPERVISOR, User.ROLE_ANALYST]
CHV_COVERAGE_NOTIFICATION_ACTIONS = {
    CHVCoverageRequestEvent.ACTION_APPROVED,
    CHVCoverageRequestEvent.ACTION_REJECTED,
    CHVCoverageRequestEvent.ACTION_CANCELLED,
    CHVCoverageRequestEvent.ACTION_ASSIGNMENT_CREATED,
    CHVCoverageRequestEvent.ACTION_ASSIGNMENT_COMPLETED,
    CHVCoverageRequestEvent.ACTION_ASSIGNMENT_CANCELLED,
    CHVCoverageRequestEvent.ACTION_RESOLVED,
}


@dataclass
class FeedStatusSnapshot:
    key: str
    label: str
    latest_timestamp: str | None
    stale: bool


def _is_stale(timestamp):
    if not timestamp:
        return True
    value = timestamp.timestamp() if hasattr(timestamp, "timestamp") else None
    if value is None:
        return True
    return (timezone.now().timestamp() - value) > STALE_THRESHOLD_MINUTES * 60


def _record_event(notification: DashboardNotification, action: str, old_state: str, new_state: str, actor=None, metadata=None):
    DashboardNotificationEvent.objects.create(
        notification=notification,
        actor=actor,
        action=action,
        old_state=old_state,
        new_state=new_state,
        metadata=metadata or {},
    )


def notification_group_name(user_id: int) -> str:
    return f"dashboard_notifications_user_{user_id}"


def _notifications_queryset_for_user(user: User):
    queryset = DashboardNotification.objects.select_related("ward", "recipient_user")
    queryset = queryset.filter(Q(recipient_user=user) | Q(recipient_user__isnull=True))
    queryset = queryset.filter(Q(recipient_role="") | Q(recipient_role=user.role))

    if user.role == User.ROLE_SUPERVISOR and user.ward_id:
        queryset = queryset.filter(Q(ward_id=user.ward_id) | Q(ward__isnull=True))

    return queryset.order_by("-created_at")


def notification_unread_count_for_user(user: User) -> int:
    return _notifications_queryset_for_user(user).filter(state=DashboardNotification.STATE_NEW).count()


def notification_summary_for_user(user: User) -> dict[str, str | int | None]:
    unread_queryset = _notifications_queryset_for_user(user).filter(state=DashboardNotification.STATE_NEW)
    unread_count = unread_queryset.count()
    highest_unread_severity = None

    if unread_queryset.filter(severity=DashboardNotification.SEVERITY_CRITICAL).exists():
        highest_unread_severity = DashboardNotification.SEVERITY_CRITICAL
    elif unread_queryset.filter(severity=DashboardNotification.SEVERITY_WARNING).exists():
        highest_unread_severity = DashboardNotification.SEVERITY_WARNING
    elif unread_queryset.filter(severity=DashboardNotification.SEVERITY_INFO).exists():
        highest_unread_severity = DashboardNotification.SEVERITY_INFO

    freshness = serialize_dashboard_freshness_summary()
    if highest_unread_severity == DashboardNotification.SEVERITY_CRITICAL:
        system_status = "ACTION_REQUIRED"
    elif freshness["freshness_state"] in {"stale", "delayed"} or highest_unread_severity == DashboardNotification.SEVERITY_WARNING:
        system_status = "DATA_FRESHNESS_DEGRADED"
    else:
        system_status = "STABLE"

    return {
        "unread_count": unread_count,
        "highest_unread_severity": highest_unread_severity,
        "system_status": system_status,
    }


def serialize_feed_status_snapshots() -> list[dict[str, str | bool | None]]:
    return [
        {
            "id": feed.key,
            "label": feed.label,
            "latest_timestamp": feed.latest_timestamp,
            "stale": feed.stale,
        }
        for feed in build_feed_status_snapshots()
    ]


def _latest_timestamp(values: list[str | None]) -> str | None:
    latest = None
    latest_value = None
    for value in values:
        if not value:
            continue
        parsed = timezone.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if latest is None or parsed > latest:
            latest = parsed
            latest_value = value
    return latest_value


def serialize_dashboard_freshness_summary() -> dict[str, str | None]:
    latest_model_run = ModelRun.objects.order_by("-completed_at", "-started_at").first()
    latest_ingestion_run = IngestionRun.objects.order_by("-started_at").first()
    latest_alert = Alert.objects.order_by("-created_at").first()
    wards = Ward.objects.filter(is_active=True).prefetch_related("risk_scores")
    latest_prediction = None
    for ward in wards:
        current = latest_riskscore_for_ward(ward)
        if current and (latest_prediction is None or current.generated_at > latest_prediction.generated_at):
            latest_prediction = current

    model_timestamp = (
        latest_model_run.completed_at.isoformat()
        if latest_model_run and latest_model_run.completed_at
        else latest_model_run.started_at.isoformat()
        if latest_model_run
        else None
    )
    data_sync_timestamp = (
        latest_ingestion_run.completed_at.isoformat()
        if latest_ingestion_run and latest_ingestion_run.completed_at
        else latest_ingestion_run.started_at.isoformat()
        if latest_ingestion_run
        else None
    )
    alert_timestamp = latest_alert.created_at.isoformat() if latest_alert else None
    prediction_timestamp = latest_prediction.generated_at.isoformat() if latest_prediction else None
    latest_timestamp = _latest_timestamp(
        [model_timestamp, data_sync_timestamp, alert_timestamp, prediction_timestamp]
    )
    freshness_state = "stale"
    if latest_timestamp:
        latest_dt = timezone.datetime.fromisoformat(latest_timestamp.replace("Z", "+00:00"))
        age_minutes = (timezone.now() - latest_dt).total_seconds() / 60
        if age_minutes <= 120:
            freshness_state = "fresh"
        elif age_minutes <= 360:
            freshness_state = "delayed"

    return {
        "last_model_run_at": model_timestamp,
        "last_data_sync_at": data_sync_timestamp,
        "last_alert_ingestion_at": alert_timestamp,
        "prediction_generated_at": prediction_timestamp,
        "freshness_state": freshness_state,
    }


def _recipient_users_for_notification(notification: DashboardNotification):
    queryset = User.objects.filter(is_active=True, role__in=DASHBOARD_ROLES)

    if notification.recipient_user_id:
        queryset = queryset.filter(pk=notification.recipient_user_id)

    if notification.recipient_role:
        queryset = queryset.filter(role=notification.recipient_role)

    if notification.ward_id:
        queryset = queryset.filter(
            Q(role__in=[User.ROLE_ADMIN, User.ROLE_ANALYST])
            | Q(role=User.ROLE_SUPERVISOR, ward_id=notification.ward_id)
        )

    return queryset.distinct()


def _chv_coverage_notification_content(event: CHVCoverageRequestEvent) -> dict[str, str]:
    request_record = event.coverage_request
    ward_name = request_record.ward.name
    actor_name = event.actor.full_name or event.actor.username if event.actor else "Operations"
    linked_alert_public_ids = [
        str(link.alert.public_id) for link in request_record.linked_alert_links.all() if link.alert_id
    ]
    is_alert_driven = (
        request_record.trigger_source == request_record.TRIGGER_SOURCE_ALERT_DRIVEN
        and bool(linked_alert_public_ids)
    )
    alert_origin_sentence = (
        " This request was opened from alert context."
        if is_alert_driven
        else ""
    )
    alert_origin_message = (
        " The request was opened from alert context."
        if is_alert_driven
        else ""
    )
    alert_reference_suffix = (
        f" Linked alert: {linked_alert_public_ids[0]}."
        if len(linked_alert_public_ids) == 1
        else f" Linked alerts: {len(linked_alert_public_ids)}."
        if len(linked_alert_public_ids) > 1
        else ""
    )

    if event.action == CHVCoverageRequestEvent.ACTION_APPROVED:
        return {
            "title": f"{ward_name}: coverage request approved",
            "body": (
                f"Your CHV coverage request for {ward_name} was approved and is ready for assignment."
                f"{alert_origin_sentence}{alert_reference_suffix}"
            ),
            "subject": f"Coverage request approved for {ward_name}",
            "message": (
                f"{actor_name} approved your CHV coverage request for {ward_name}."
                f"{alert_origin_message}{alert_reference_suffix}"
            ),
            "severity": DashboardNotification.SEVERITY_INFO,
        }
    if event.action == CHVCoverageRequestEvent.ACTION_REJECTED:
        reason = request_record.review_decision_reason or "No rejection reason was recorded."
        return {
            "title": f"{ward_name}: coverage request rejected",
            "body": (
                f"Your CHV coverage request for {ward_name} was rejected. Reason: {reason}"
                f"{alert_origin_sentence}{alert_reference_suffix}"
            ),
            "subject": f"Coverage request rejected for {ward_name}",
            "message": (
                f"{actor_name} rejected your CHV coverage request for {ward_name}. Reason: {reason}"
                f"{alert_origin_message}{alert_reference_suffix}"
            ),
            "severity": DashboardNotification.SEVERITY_WARNING,
        }
    if event.action == CHVCoverageRequestEvent.ACTION_CANCELLED:
        reason = request_record.review_decision_reason or "No cancellation reason was recorded."
        return {
            "title": f"{ward_name}: coverage request cancelled",
            "body": (
                f"Your CHV coverage request for {ward_name} was cancelled. Reason: {reason}"
                f"{alert_origin_sentence}{alert_reference_suffix}"
            ),
            "subject": f"Coverage request cancelled for {ward_name}",
            "message": (
                f"{actor_name} cancelled your CHV coverage request for {ward_name}. Reason: {reason}"
                f"{alert_origin_message}{alert_reference_suffix}"
            ),
            "severity": DashboardNotification.SEVERITY_WARNING,
        }
    if event.action == CHVCoverageRequestEvent.ACTION_ASSIGNMENT_CREATED:
        chv_name = event.assignment.chv.name if event.assignment else "A CHV"
        return {
            "title": f"{ward_name}: CHV assigned",
            "body": (
                f"{chv_name} was assigned to your CHV coverage request for {ward_name}."
                f"{alert_origin_sentence}{alert_reference_suffix}"
            ),
            "subject": f"CHV assigned for {ward_name}",
            "message": (
                f"{actor_name} assigned {chv_name} to your CHV coverage request for {ward_name}."
                f"{alert_origin_message}{alert_reference_suffix}"
            ),
            "severity": DashboardNotification.SEVERITY_INFO,
        }
    if event.action == CHVCoverageRequestEvent.ACTION_ASSIGNMENT_COMPLETED:
        chv_name = event.assignment.chv.name if event.assignment else "A CHV"
        return {
            "title": f"{ward_name}: assignment completed",
            "body": (
                f"{chv_name} completed work on your CHV coverage request for {ward_name}."
                f"{alert_origin_sentence}{alert_reference_suffix}"
            ),
            "subject": f"Assignment completed for {ward_name}",
            "message": (
                f"{actor_name} marked {chv_name}'s assignment as completed for {ward_name}."
                f"{alert_origin_message}{alert_reference_suffix}"
            ),
            "severity": DashboardNotification.SEVERITY_INFO,
        }
    if event.action == CHVCoverageRequestEvent.ACTION_ASSIGNMENT_CANCELLED:
        chv_name = event.assignment.chv.name if event.assignment else "A CHV"
        return {
            "title": f"{ward_name}: assignment cancelled",
            "body": (
                f"{chv_name}'s assignment was cancelled for your CHV coverage request in {ward_name}."
                f"{alert_origin_sentence}{alert_reference_suffix}"
            ),
            "subject": f"Assignment cancelled for {ward_name}",
            "message": (
                f"{actor_name} cancelled {chv_name}'s assignment for your CHV coverage request in {ward_name}."
                f"{alert_origin_message}{alert_reference_suffix}"
            ),
            "severity": DashboardNotification.SEVERITY_WARNING,
        }
    if event.action == CHVCoverageRequestEvent.ACTION_RESOLVED:
        return {
            "title": f"{ward_name}: coverage request resolved",
            "body": (
                f"Your CHV coverage request for {ward_name} was resolved."
                f"{alert_origin_sentence}{alert_reference_suffix}"
            ),
            "subject": f"Coverage request resolved for {ward_name}",
            "message": (
                f"{actor_name} resolved your CHV coverage request for {ward_name}."
                f"{alert_origin_message}{alert_reference_suffix}"
            ),
            "severity": DashboardNotification.SEVERITY_INFO,
        }
    raise ValueError(f"Unsupported CHV coverage notification action: {event.action}")


def _frontend_absolute_url(path: str) -> str:
    base_url = getattr(settings, "FRONTEND_APP_URL", "").strip().rstrip("/")
    if not base_url:
        return path
    normalized_path = path if path.startswith("/") else f"/{path}"
    return f"{base_url}{normalized_path}"


def dispatch_chv_coverage_request_event_side_effects(event_id: int) -> None:
    event = (
        CHVCoverageRequestEvent.objects.select_related(
            "coverage_request__ward",
            "coverage_request__requested_by",
            "assignment__chv",
            "actor",
        )
        .filter(pk=event_id)
        .first()
    )
    if event is None or event.action not in CHV_COVERAGE_NOTIFICATION_ACTIONS:
        return

    request_record = event.coverage_request
    recipient = request_record.requested_by
    if recipient is None:
        return

    content = _chv_coverage_notification_content(event)
    href = f"/chvs/requests/{request_record.public_id}"
    absolute_href = _frontend_absolute_url(href)
    notification = _upsert_notification(
        external_key=f"chv-coverage-request-event:{event.public_id}",
        defaults={
            "type": DashboardNotification.TYPE_CHV_COVERAGE_REQUEST_STATUS,
            "severity": content["severity"],
            "title": content["title"],
            "body": content["body"],
            "source_system": "risk",
            "source_object_type": "CHV_COVERAGE_REQUEST",
            "source_object_id": str(request_record.public_id),
            "href": href,
            "recipient_scope": DashboardNotification.SCOPE_WARD,
            "recipient_role": "",
            "recipient_user": recipient,
            "ward": request_record.ward,
            "requires_acknowledgement": False,
            "dismissible": True,
            "auto_resolve": False,
            "pinned_until_actioned": False,
            "metadata": {
                "coverage_request_public_id": str(request_record.public_id),
                "coverage_request_status": request_record.status,
                "coverage_event_public_id": str(event.public_id),
                "coverage_event_action": event.action,
                "assignment_public_id": str(event.assignment.public_id) if event.assignment else "",
            },
        },
    )

    recipient_email = (recipient.email or "").strip()
    if not recipient_email:
        CHVCoverageRequestEmailDelivery.objects.create(
            coverage_request=request_record,
            event=event,
            recipient_user=recipient,
            recipient_email="",
            status=CHVCoverageRequestEmailDelivery.STATUS_FAILED,
            delivery_backend="",
            external_id="",
            error_message="Requesting user does not have an email address.",
            metadata={"notification_public_id": str(notification.public_id)},
        )
        return

    result = send_email(
        to_email=recipient_email,
        subject=content["subject"],
        text_body=f"{content['message']}\n\nView request: {absolute_href}",
        html_body=(
            f"<p>{content['message']}</p>"
            f"<p><a href=\"{absolute_href}\">View request</a></p>"
        ),
    )
    CHVCoverageRequestEmailDelivery.objects.create(
        coverage_request=request_record,
        event=event,
        recipient_user=recipient,
        recipient_email=recipient_email,
        status=CHVCoverageRequestEmailDelivery.STATUS_SENT if result.success else CHVCoverageRequestEmailDelivery.STATUS_FAILED,
        delivery_backend=result.provider,
        external_id=result.external_id,
        error_message=result.error,
        metadata={
            "notification_public_id": str(notification.public_id),
            "status_code": result.status_code,
        },
    )


def _broadcast_notification_event(notification: DashboardNotification, event_name: str, changed_fields: list[str] | None = None) -> None:
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    serialized_notification = DashboardNotificationSerializer(notification).data
    for user in _recipient_users_for_notification(notification):
        payload = {
            "event": event_name,
            "notification": serialized_notification,
            **notification_summary_for_user(user),
            "feeds": serialize_feed_status_snapshots(),
            "freshness": serialize_dashboard_freshness_summary(),
            "changed_fields": changed_fields or [],
        }
        async_to_sync(channel_layer.group_send)(
            notification_group_name(user.id),
            {
                "type": "dashboard.notification.event",
                "payload": payload,
            },
        )


def transition_notification(notification: DashboardNotification, action: str, actor: User | None = None) -> DashboardNotification:
    old_state = notification.state
    now = timezone.now()

    if action == DashboardNotificationEvent.ACTION_SEEN and notification.state == DashboardNotification.STATE_NEW:
        notification.state = DashboardNotification.STATE_SEEN
        notification.seen_at = notification.seen_at or now
    elif action == DashboardNotificationEvent.ACTION_ACKNOWLEDGED and notification.state in {
        DashboardNotification.STATE_NEW,
        DashboardNotification.STATE_SEEN,
    }:
        notification.state = DashboardNotification.STATE_ACKNOWLEDGED
        notification.seen_at = notification.seen_at or now
        notification.acknowledged_at = now
    elif action == DashboardNotificationEvent.ACTION_DISMISSED and notification.dismissible and notification.state not in {
        DashboardNotification.STATE_RESOLVED,
        DashboardNotification.STATE_DISMISSED,
        DashboardNotification.STATE_EXPIRED,
    }:
        notification.state = DashboardNotification.STATE_DISMISSED
        notification.dismissed_at = now
    elif action == DashboardNotificationEvent.ACTION_RESOLVED and notification.state != DashboardNotification.STATE_RESOLVED:
        notification.state = DashboardNotification.STATE_RESOLVED
        notification.resolved_at = now
    elif action == DashboardNotificationEvent.ACTION_EXPIRED and notification.state != DashboardNotification.STATE_EXPIRED:
        notification.state = DashboardNotification.STATE_EXPIRED
    else:
        return notification

    notification.save(
        update_fields=[
            "state",
            "seen_at",
            "acknowledged_at",
            "dismissed_at",
            "resolved_at",
            "updated_at",
        ]
    )
    _record_event(notification, action, old_state, notification.state, actor=actor)
    event_name = "notification.resolved" if action == DashboardNotificationEvent.ACTION_RESOLVED else "notification.updated"
    _broadcast_notification_event(notification, event_name, changed_fields=["state"])
    return notification


def _upsert_notification(
    *,
    external_key: str,
    defaults: dict,
    action_if_created: str = DashboardNotificationEvent.ACTION_CREATED,
) -> DashboardNotification:
    notification, created = DashboardNotification.objects.get_or_create(
        external_key=external_key,
        defaults=defaults,
    )
    if created:
        _record_event(notification, action_if_created, "", notification.state, metadata={"external_key": external_key})
        _broadcast_notification_event(notification, "notification.created", changed_fields=list(defaults.keys()))
        return notification

    changed_fields: list[str] = []
    prior_state = notification.state
    for field, value in defaults.items():
        if getattr(notification, field) != value:
            setattr(notification, field, value)
            changed_fields.append(field)

    if notification.state in {DashboardNotification.STATE_RESOLVED, DashboardNotification.STATE_EXPIRED}:
        notification.state = DashboardNotification.STATE_NEW
        notification.seen_at = None
        notification.acknowledged_at = None
        notification.resolved_at = None
        notification.dismissed_at = None
        changed_fields.extend(["state", "seen_at", "acknowledged_at", "resolved_at", "dismissed_at"])

    if changed_fields:
        notification.save(update_fields=changed_fields + ["updated_at"])
        _record_event(notification, DashboardNotificationEvent.ACTION_UPDATED, prior_state, notification.state)
        _broadcast_notification_event(notification, "notification.updated", changed_fields=changed_fields)
    return notification


def build_feed_status_snapshots() -> list[FeedStatusSnapshot]:
    latest_risk = None
    wards = Ward.objects.filter(is_active=True).prefetch_related("risk_scores")
    for ward in wards:
        current = latest_riskscore_for_ward(ward)
        if current and (latest_risk is None or current.generated_at > latest_risk.generated_at):
            latest_risk = current

    latest_alert = Alert.objects.order_by("-created_at").first()
    latest_facility = HealthFacility.objects.filter(is_active=True).order_by("-updated_at").first()

    return [
        FeedStatusSnapshot(
            key="risks",
            label="Risk feed",
            latest_timestamp=latest_risk.generated_at.isoformat() if latest_risk else None,
            stale=_is_stale(latest_risk.generated_at if latest_risk else None),
        ),
        FeedStatusSnapshot(
            key="alerts",
            label="Alert log",
            latest_timestamp=latest_alert.created_at.isoformat() if latest_alert else None,
            stale=_is_stale(latest_alert.created_at if latest_alert else None),
        ),
        FeedStatusSnapshot(
            key="facilities",
            label="Facility records",
            latest_timestamp=latest_facility.updated_at.isoformat() if latest_facility else None,
            stale=_is_stale(latest_facility.updated_at if latest_facility else None),
        ),
    ]


def sync_dashboard_notifications() -> None:
    active_keys: set[str] = set()
    wards = Ward.objects.filter(is_active=True).prefetch_related("risk_scores")

    for ward in wards:
        latest = latest_riskscore_for_ward(ward)
        if latest and latest.risk_level == Ward.RISK_HIGH:
            key = f"ward-risk-high:{ward.id}"
            active_keys.add(key)
            _upsert_notification(
                external_key=key,
                defaults={
                    "type": DashboardNotification.TYPE_WARD_RISK_HIGH,
                    "severity": DashboardNotification.SEVERITY_CRITICAL,
                    "title": f"{ward.name}: action required",
                    "body": f"Promoted ward risk is currently HIGH with {latest.predicted_cases} predicted cases.",
                    "source_system": "risk",
                    "source_object_type": "ward",
                    "source_object_id": str(ward.id),
                    "href": f"/overview?trigger_review={ward.id}",
                    "recipient_scope": DashboardNotification.SCOPE_WARD,
                    "ward": ward,
                    "recipient_role": "",
                    "requires_acknowledgement": True,
                    "dismissible": False,
                    "auto_resolve": True,
                    "pinned_until_actioned": True,
                    "metadata": {"risk_score": latest.score, "predicted_cases": latest.predicted_cases},
                },
            )

    for alert in Alert.objects.select_related("ward").filter(status=Alert.STATUS_FAILED):
        key = f"alert-failed:{alert.id}"
        active_keys.add(key)
        _upsert_notification(
            external_key=key,
            defaults={
                "type": DashboardNotification.TYPE_ALERT_FAILED,
                "severity": DashboardNotification.SEVERITY_CRITICAL,
                "title": f"{alert.ward.name}: alert delivery failed",
                "body": f"{alert.channel} alert delivery failed for {alert.recipient}. Review the alert record.",
                "source_system": "alerts",
                "source_object_type": "alert",
                "source_object_id": str(alert.id),
                "href": f"/alerts/{alert.id}",
                "recipient_scope": DashboardNotification.SCOPE_WARD,
                "ward": alert.ward,
                "recipient_role": "",
                "requires_acknowledgement": True,
                "dismissible": False,
                "auto_resolve": True,
                "pinned_until_actioned": True,
                "metadata": {"channel": alert.channel, "recipient": alert.recipient},
            },
        )

    for alert in Alert.objects.select_related("ward").filter(status=Alert.STATUS_RETRY_PENDING):
        key = f"alert-retry:{alert.id}"
        active_keys.add(key)
        _upsert_notification(
            external_key=key,
            defaults={
                "type": DashboardNotification.TYPE_ALERT_RETRY_PENDING,
                "severity": DashboardNotification.SEVERITY_WARNING,
                "title": f"{alert.ward.name}: alert retry pending",
                "body": f"{alert.channel} alert for {alert.recipient} is waiting for another delivery attempt.",
                "source_system": "alerts",
                "source_object_type": "alert",
                "source_object_id": str(alert.id),
                "href": f"/alerts/{alert.id}",
                "recipient_scope": DashboardNotification.SCOPE_WARD,
                "ward": alert.ward,
                "recipient_role": "",
                "requires_acknowledgement": False,
                "dismissible": True,
                "auto_resolve": True,
                "pinned_until_actioned": False,
                "metadata": {"channel": alert.channel, "recipient": alert.recipient},
            },
        )

    for feed in build_feed_status_snapshots():
        key = f"feed-stale:{feed.key}"
        if feed.stale:
            active_keys.add(key)
            _upsert_notification(
                external_key=key,
                defaults={
                    "type": DashboardNotification.TYPE_FEED_STALE,
                    "severity": DashboardNotification.SEVERITY_WARNING,
                    "title": f"{feed.label} outdated",
                    "body": "Data is stale and may not reflect current conditions.",
                    "source_system": "etl",
                    "source_object_type": "feed",
                    "source_object_id": feed.key,
                    "href": "/system",
                    "recipient_scope": DashboardNotification.SCOPE_GLOBAL,
                    "ward": None,
                    "recipient_role": "",
                    "requires_acknowledgement": False,
                    "dismissible": True,
                    "auto_resolve": True,
                    "pinned_until_actioned": False,
                    "metadata": {"feed_label": feed.label, "latest_timestamp": feed.latest_timestamp},
                },
            )

    auto_resolve_queryset = DashboardNotification.objects.filter(auto_resolve=True).exclude(state__in=[
        DashboardNotification.STATE_RESOLVED,
        DashboardNotification.STATE_EXPIRED,
    ])
    for notification in auto_resolve_queryset:
        if notification.external_key not in active_keys:
            transition_notification(notification, DashboardNotificationEvent.ACTION_RESOLVED)

    expirable = DashboardNotification.objects.exclude(expires_at__isnull=True).exclude(state=DashboardNotification.STATE_EXPIRED)
    for notification in expirable:
        if notification.expires_at and notification.expires_at <= timezone.now():
            transition_notification(notification, DashboardNotificationEvent.ACTION_EXPIRED)


def notifications_for_user(user: User):
    sync_dashboard_notifications()
    return _notifications_queryset_for_user(user)
