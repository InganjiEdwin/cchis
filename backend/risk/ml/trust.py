from __future__ import annotations

from decouple import config
from django.utils import timezone

from risk.models import ETLHeartbeat, IngestionRun


TRUST_STATE_NORMAL = "normal"
TRUST_STATE_DEGRADED = "degraded"
TRUST_STATE_BLOCKED = "blocked"

ALERT_STATE_ALLOWED = "allowed"
ALERT_STATE_REVIEW_ONLY = "review_only"
ALERT_STATE_BLOCKED = "blocked"

SCHEDULE_STATE_FIRST_RUN = "first_run"
SCHEDULE_STATE_ON_TIME = "on_time"
SCHEDULE_STATE_DELAYED = "delayed"

HEARTBEAT_STATE_FRESH = "fresh"
HEARTBEAT_STATE_DELAYED = "delayed"
HEARTBEAT_STATE_STALE = "stale"
HEARTBEAT_STATE_UNKNOWN = "unknown"


def _scheduled_gap_hours(run: IngestionRun | None) -> tuple[str, float | None]:
    if run is None or run.completed_at is None:
        return SCHEDULE_STATE_DELAYED, None

    previous_run = (
        IngestionRun.objects.filter(
            run_type=run.run_type,
            completed_at__isnull=False,
            status__in=[IngestionRun.STATUS_SUCCESS, IngestionRun.STATUS_PARTIAL],
        )
        .exclude(id=run.id)
        .order_by("-completed_at")
        .first()
    )

    if previous_run is None or previous_run.completed_at is None:
        return SCHEDULE_STATE_FIRST_RUN, None

    gap_hours = round((run.completed_at - previous_run.completed_at).total_seconds() / 3600, 2)
    delayed_hours = config("RAINFALL_INGESTION_DELAY_WARNING_HOURS", cast=int, default=30)
    if gap_hours > delayed_hours:
        return SCHEDULE_STATE_DELAYED, gap_hours
    return SCHEDULE_STATE_ON_TIME, gap_hours


def _heartbeat_snapshot() -> dict:
    scheduler = (
        ETLHeartbeat.objects.filter(component=ETLHeartbeat.COMPONENT_SCHEDULER)
        .order_by("-recorded_at")
        .first()
    )
    worker = (
        ETLHeartbeat.objects.filter(component=ETLHeartbeat.COMPONENT_WORKER)
        .order_by("-recorded_at")
        .first()
    )
    latest_seen = None
    if scheduler and worker:
        latest_seen = min(scheduler.recorded_at, worker.recorded_at)
    elif scheduler:
        latest_seen = scheduler.recorded_at
    elif worker:
        latest_seen = worker.recorded_at

    heartbeat = {
        "state": HEARTBEAT_STATE_UNKNOWN,
        "scheduler_recorded_at": scheduler.recorded_at.isoformat() if scheduler else None,
        "worker_recorded_at": worker.recorded_at.isoformat() if worker else None,
        "age_minutes": None,
    }
    if latest_seen is None:
        return heartbeat

    age_minutes = round((timezone.now() - latest_seen).total_seconds() / 60, 2)
    heartbeat["age_minutes"] = age_minutes
    delayed_minutes = config("ETL_HEARTBEAT_DELAY_WARNING_MINUTES", cast=int, default=20)
    stale_minutes = config("ETL_HEARTBEAT_STALE_MINUTES", cast=int, default=60)
    if age_minutes <= delayed_minutes:
        heartbeat["state"] = HEARTBEAT_STATE_FRESH
    elif age_minutes <= stale_minutes:
        heartbeat["state"] = HEARTBEAT_STATE_DELAYED
    else:
        heartbeat["state"] = HEARTBEAT_STATE_STALE
    return heartbeat


def build_operational_trust_snapshot(ingestion_run: IngestionRun | None) -> dict:
    source_mode = config("RAINFALL_SOURCE_MODE", default="hybrid").strip().lower()
    heartbeat = _heartbeat_snapshot()
    snapshot = {
        "source_mode": source_mode,
        "prediction_state": TRUST_STATE_NORMAL,
        "alert_state": ALERT_STATE_ALLOWED,
        "schedule_state": SCHEDULE_STATE_FIRST_RUN,
        "schedule_gap_hours": None,
        "heartbeat": heartbeat,
        "source_kind": ingestion_run.source_kind if ingestion_run else IngestionRun.SOURCE_KIND_UNKNOWN,
        "freshness_state": ingestion_run.freshness_state if ingestion_run else IngestionRun.FRESHNESS_UNKNOWN,
        "fallback_used": ingestion_run.fallback_used if ingestion_run else False,
        "ingestion_status": ingestion_run.status if ingestion_run else IngestionRun.STATUS_FAILED,
        "reasons": [],
    }

    if ingestion_run is None:
        snapshot["prediction_state"] = TRUST_STATE_BLOCKED
        snapshot["alert_state"] = ALERT_STATE_BLOCKED
        snapshot["reasons"].append("missing-ingestion-run")
        return snapshot

    schedule_state, schedule_gap_hours = _scheduled_gap_hours(ingestion_run)
    snapshot["schedule_state"] = schedule_state
    snapshot["schedule_gap_hours"] = schedule_gap_hours

    if source_mode == "static":
        snapshot["prediction_state"] = TRUST_STATE_DEGRADED
        snapshot["alert_state"] = ALERT_STATE_BLOCKED
        snapshot["reasons"].append("static-mode-forced")
    elif ingestion_run.status == IngestionRun.STATUS_FAILED:
        snapshot["prediction_state"] = TRUST_STATE_BLOCKED
        snapshot["alert_state"] = ALERT_STATE_BLOCKED
        snapshot["reasons"].append("ingestion-failed")
    elif ingestion_run.freshness_state == IngestionRun.FRESHNESS_STALE:
        snapshot["prediction_state"] = TRUST_STATE_BLOCKED
        snapshot["alert_state"] = ALERT_STATE_BLOCKED
        snapshot["reasons"].append("source-stale")
    elif ingestion_run.freshness_state == IngestionRun.FRESHNESS_UNKNOWN:
        if ingestion_run.source_kind == IngestionRun.SOURCE_KIND_SEEDED:
            snapshot["prediction_state"] = TRUST_STATE_DEGRADED
            snapshot["alert_state"] = ALERT_STATE_BLOCKED
            snapshot["reasons"].append("seeded-or-fallback-source")
        else:
            snapshot["prediction_state"] = TRUST_STATE_BLOCKED
            snapshot["alert_state"] = ALERT_STATE_BLOCKED
            snapshot["reasons"].append("source-freshness-unknown")
    elif ingestion_run.freshness_state == IngestionRun.FRESHNESS_DELAYED:
        snapshot["prediction_state"] = TRUST_STATE_DEGRADED
        snapshot["alert_state"] = ALERT_STATE_REVIEW_ONLY
        snapshot["reasons"].append("source-delayed")

    if ingestion_run.fallback_used or ingestion_run.source_kind in {
        IngestionRun.SOURCE_KIND_SEEDED,
        IngestionRun.SOURCE_KIND_HYBRID,
    }:
        if snapshot["prediction_state"] != TRUST_STATE_BLOCKED:
            snapshot["prediction_state"] = TRUST_STATE_DEGRADED
        snapshot["alert_state"] = ALERT_STATE_BLOCKED
        if ingestion_run.fallback_used:
            snapshot["reasons"].append("fallback-used")
        if ingestion_run.source_kind in {IngestionRun.SOURCE_KIND_SEEDED, IngestionRun.SOURCE_KIND_HYBRID}:
            snapshot["reasons"].append("non-live-source-kind")

    if schedule_state == SCHEDULE_STATE_DELAYED and snapshot["prediction_state"] != TRUST_STATE_BLOCKED:
        snapshot["prediction_state"] = TRUST_STATE_DEGRADED
        snapshot["alert_state"] = ALERT_STATE_BLOCKED
        snapshot["reasons"].append("scheduled-ingestion-gap")

    if heartbeat["state"] == HEARTBEAT_STATE_UNKNOWN and snapshot["prediction_state"] != TRUST_STATE_BLOCKED:
        snapshot["prediction_state"] = TRUST_STATE_DEGRADED
        snapshot["alert_state"] = ALERT_STATE_BLOCKED
        snapshot["reasons"].append("heartbeat-missing")
    elif heartbeat["state"] == HEARTBEAT_STATE_DELAYED and snapshot["prediction_state"] != TRUST_STATE_BLOCKED:
        snapshot["prediction_state"] = TRUST_STATE_DEGRADED
        snapshot["alert_state"] = ALERT_STATE_BLOCKED
        snapshot["reasons"].append("heartbeat-delayed")
    elif heartbeat["state"] == HEARTBEAT_STATE_STALE:
        snapshot["prediction_state"] = TRUST_STATE_BLOCKED
        snapshot["alert_state"] = ALERT_STATE_BLOCKED
        snapshot["reasons"].append("heartbeat-stale")

    # Remove duplicates but keep ordering stable.
    snapshot["reasons"] = list(dict.fromkeys(snapshot["reasons"]))
    return snapshot


def alerts_allowed_for_snapshot(snapshot: dict) -> bool:
    return snapshot.get("alert_state") == ALERT_STATE_ALLOWED


def predictions_blocked_for_snapshot(snapshot: dict) -> bool:
    return snapshot.get("prediction_state") == TRUST_STATE_BLOCKED
