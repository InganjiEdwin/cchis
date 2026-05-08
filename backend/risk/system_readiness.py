from datetime import datetime, timedelta

from django.db.models import Count, Max, Q
from django.utils import timezone

from accounts.models import User

from .models import Alert, CHV, HealthFacility, RiskScore, SyncQueue, TriageSession, UssdSessionLog, Ward


SYSTEM_READINESS_SCHEMA_VERSION = "system-readiness-v1"
SYSTEM_READINESS_MODE = "analyst_safe_system_readiness_v1"


def _user_has_broad_scope(user: User) -> bool:
    return bool(
        getattr(user, "is_superuser", False)
        or getattr(user, "role", None) in {User.ROLE_ADMIN, User.ROLE_ANALYST}
    )


def _scope_for_user(user: User, ward_count: int) -> dict:
    if _user_has_broad_scope(user):
        return {
            "type": "BROAD",
            "ward_id": None,
            "ward_count": ward_count,
        }

    ward_id = getattr(user, "ward_id", None)
    if ward_id:
        return {
            "type": "WARD",
            "ward_id": ward_id,
            "ward_count": ward_count,
        }

    return {
        "type": "NONE",
        "ward_id": None,
        "ward_count": 0,
    }


def _apply_ward_scope(queryset, user: User, *, field_name: str = "ward_id"):
    if _user_has_broad_scope(user):
        return queryset

    ward_id = getattr(user, "ward_id", None)
    if not ward_id:
        return queryset.none()

    return queryset.filter(**{field_name: ward_id})


def _latest_timestamp(values) -> datetime | None:
    latest = None
    for value in values:
        if value is None:
            continue
        if latest is None or value > latest:
            latest = value
    return latest


def _derive_sync_health(last_sync_at):
    if not last_sync_at:
        return "OFFLINE"

    age = timezone.now() - last_sync_at
    if age <= timedelta(minutes=30):
        return "ONLINE"
    if age <= timedelta(hours=6):
        return "DELAYED"
    return "OFFLINE"


def _risk_summary_for_wards(wards: list[Ward]) -> dict:
    latest_risk_timestamp = None
    high_risk_wards = 0
    wards_with_fresh_risk = 0

    for ward in wards:
        latest = (
            RiskScore.objects.filter(ward_id=ward.id)
            .only("risk_level", "generated_at")
            .order_by("-generated_at")
            .first()
        )
        risk_level = latest.risk_level if latest else ward.current_risk_level
        if risk_level == Ward.RISK_HIGH:
            high_risk_wards += 1
        if latest and latest.generated_at:
            wards_with_fresh_risk += 1
            latest_risk_timestamp = _latest_timestamp([latest_risk_timestamp, latest.generated_at])

    return {
        "high_risk_wards": high_risk_wards,
        "wards_with_fresh_risk": wards_with_fresh_risk,
        "latest_risk_timestamp": latest_risk_timestamp,
    }


def _alert_summary(alert_queryset) -> dict:
    status_summary = alert_queryset.aggregate(
        visible_alerts=Count("id"),
        latest_alert_timestamp=Max("created_at"),
        queued_alerts=Count("id", filter=Q(status=Alert.STATUS_QUEUED)),
        retry_pending_alerts=Count("id", filter=Q(status=Alert.STATUS_RETRY_PENDING)),
        failed_alerts=Count("id", filter=Q(status=Alert.STATUS_FAILED)),
        delivered_alerts=Count("id", filter=Q(status=Alert.STATUS_DELIVERED)),
        latest_failed_alert_timestamp=Max("created_at", filter=Q(status=Alert.STATUS_FAILED)),
        latest_retry_alert_timestamp=Max("created_at", filter=Q(status=Alert.STATUS_RETRY_PENDING)),
        latest_delivered_alert_timestamp=Max("created_at", filter=Q(status=Alert.STATUS_DELIVERED)),
    )
    delivery_backends = [
        {
            "name": row["delivery_backend"] or "Unassigned delivery source",
            "count": row["count"],
        }
        for row in (
            alert_queryset.values("delivery_backend")
            .annotate(count=Count("id"))
            .order_by("-count", "delivery_backend")[:8]
        )
    ]

    return {
        **status_summary,
        "delivery_backends": delivery_backends,
    }


def _facility_summary(facility_queryset) -> dict:
    summary = facility_queryset.aggregate(
        visible_facilities=Count("id"),
        latest_facility_timestamp=Max("updated_at"),
    )
    return summary


def _chv_summary(chv_queryset) -> dict:
    now = timezone.now()
    since_24h = now - timedelta(hours=24)
    chvs = list(chv_queryset.only("id", "phone_number", "is_active", "ward_id"))
    phone_numbers = [chv.phone_number for chv in chvs if chv.phone_number]

    zero_summary = {
        "latest_chv_timestamp": None,
        "active_chvs": 0,
        "online_chvs": 0,
        "delayed_chvs": 0,
        "offline_chvs": 0,
        "triage_sessions_24h": 0,
        "referrals_24h": 0,
        "sync_payloads_24h": 0,
        "ussd_sessions_24h": 0,
    }
    if not chvs:
        return zero_summary

    sync_queryset = SyncQueue.objects.filter(phone_number__in=phone_numbers)
    triage_queryset = TriageSession.objects.filter(phone_number__in=phone_numbers)
    ussd_queryset = UssdSessionLog.objects.filter(phone_number__in=phone_numbers)

    sync_rows = sync_queryset.values("phone_number").annotate(latest_sync=Max("processed_at"))
    sync_by_phone = {row["phone_number"]: row["latest_sync"] for row in sync_rows}

    sync_health_counts = {"ONLINE": 0, "DELAYED": 0, "OFFLINE": 0}
    active_chvs = 0
    for chv in chvs:
        if chv.is_active:
            active_chvs += 1
        sync_health_counts[_derive_sync_health(sync_by_phone.get(chv.phone_number))] += 1

    sync_summary = sync_queryset.aggregate(
        latest_created_at=Max("created_at"),
        latest_processed_at=Max("processed_at"),
        sync_payloads_24h=Count("id", filter=Q(created_at__gte=since_24h)),
    )
    triage_summary = triage_queryset.aggregate(
        latest_created_at=Max("created_at"),
        triage_sessions_24h=Count("id", filter=Q(created_at__gte=since_24h)),
        referrals_24h=Count("id", filter=Q(created_at__gte=since_24h, referral_needed=True)),
    )
    ussd_summary = ussd_queryset.aggregate(
        latest_created_at=Max("created_at"),
        ussd_sessions_24h=Count("id", filter=Q(created_at__gte=since_24h)),
    )

    return {
        "latest_chv_timestamp": _latest_timestamp(
            [
                sync_summary["latest_created_at"],
                sync_summary["latest_processed_at"],
                triage_summary["latest_created_at"],
                ussd_summary["latest_created_at"],
            ]
        ),
        "active_chvs": active_chvs,
        "online_chvs": sync_health_counts["ONLINE"],
        "delayed_chvs": sync_health_counts["DELAYED"],
        "offline_chvs": sync_health_counts["OFFLINE"],
        "triage_sessions_24h": triage_summary["triage_sessions_24h"] or 0,
        "referrals_24h": triage_summary["referrals_24h"] or 0,
        "sync_payloads_24h": sync_summary["sync_payloads_24h"] or 0,
        "ussd_sessions_24h": ussd_summary["ussd_sessions_24h"] or 0,
    }


def build_system_readiness_snapshot(user: User) -> dict:
    ward_queryset = _apply_ward_scope(Ward.objects.filter(is_active=True).order_by("name"), user, field_name="id")
    wards = list(ward_queryset.only("id", "current_risk_level", "current_risk_score"))
    ward_count = len(wards)

    alert_queryset = _apply_ward_scope(Alert.objects.all(), user)
    facility_queryset = _apply_ward_scope(HealthFacility.objects.filter(is_active=True), user)
    chv_queryset = _apply_ward_scope(CHV.objects.all(), user)

    risk_summary = _risk_summary_for_wards(wards)
    alert_summary = _alert_summary(alert_queryset)
    facility_summary = _facility_summary(facility_queryset)
    chv_summary = _chv_summary(chv_queryset)

    return {
        "schema_version": SYSTEM_READINESS_SCHEMA_VERSION,
        "mode": SYSTEM_READINESS_MODE,
        "generated_at": timezone.now(),
        "scope": _scope_for_user(user, ward_count),
        "visible_wards": ward_count,
        **risk_summary,
        **alert_summary,
        **facility_summary,
        **chv_summary,
    }
