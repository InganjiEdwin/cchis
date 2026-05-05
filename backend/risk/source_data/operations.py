from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db.models import Count
from django.utils import timezone

from risk.models import ETLHeartbeat, SourceDataUploadArtifact, SourceDataUploadBatch
from risk.source_data.freshness import (
    STATUS_FAILED,
    STATUS_MISSING,
    STATUS_STALE,
    build_source_data_freshness_payload,
)


logger = logging.getLogger("risk.source_data.operations")

SOURCE_DATA_OPERATIONS_SCHEMA_VERSION = "source-data-operations-v1"
SOURCE_DATA_ARTIFACT_CLEANUP_TASK_NAME = "risk.tasks.cleanup_source_data_upload_artifacts_task"


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _source_data_task_stale_minutes() -> int:
    return int(getattr(settings, "SOURCE_DATA_TASK_STALE_MINUTES", 30))


def _source_data_alert_lookback_hours() -> int:
    return int(getattr(settings, "SOURCE_DATA_OPERATIONS_ALERT_LOOKBACK_HOURS", 24))


def _source_data_failed_import_alert_threshold() -> int:
    return int(getattr(settings, "SOURCE_DATA_FAILED_IMPORT_ALERT_THRESHOLD", 3))


def _is_path_inside_upload_root(path: Path) -> bool:
    try:
        path.resolve().relative_to(Path(settings.SOURCE_DATA_UPLOAD_ROOT).resolve())
    except ValueError:
        return False
    return True


def cleanup_expired_source_data_artifacts(
    *,
    dry_run: bool = False,
    limit: int = 500,
    now=None,
) -> dict[str, Any]:
    now = now or timezone.now()
    candidates = list(
        SourceDataUploadArtifact.objects.select_related("upload_batch")
        .filter(retention_expires_at__isnull=False, retention_expires_at__lte=now)
        .exclude(redaction_state="purged")
        .order_by("retention_expires_at", "id")[:limit]
    )

    deleted_file_count = 0
    missing_file_count = 0
    skipped_path_count = 0
    marked_purged_count = 0

    for artifact in candidates:
        artifact_path = Path(artifact.storage_path)
        exists = artifact_path.exists()
        if not _is_path_inside_upload_root(artifact_path):
            skipped_path_count += 1
            logger.warning(
                "source_data_artifact_cleanup_skipped_outside_root",
                extra={
                    "artifact_id": artifact.id,
                    "upload_batch_id": artifact.upload_batch_id,
                    "storage_path": artifact.storage_path,
                },
            )
            continue

        if exists and not dry_run:
            artifact_path.unlink()
            deleted_file_count += 1
        elif not exists:
            missing_file_count += 1

        if not dry_run:
            artifact.redaction_state = "purged"
            artifact.save(update_fields=["redaction_state"])
            marked_purged_count += 1

    status = ETLHeartbeat.STATUS_OK if skipped_path_count == 0 else ETLHeartbeat.STATUS_WARN
    result = {
        "schema_version": SOURCE_DATA_OPERATIONS_SCHEMA_VERSION,
        "dry_run": dry_run,
        "candidate_count": len(candidates),
        "deleted_file_count": deleted_file_count,
        "missing_file_count": missing_file_count,
        "marked_purged_count": marked_purged_count,
        "skipped_path_count": skipped_path_count,
        "limit": limit,
        "completed_at": now.isoformat(),
    }
    ETLHeartbeat.objects.create(
        component=ETLHeartbeat.COMPONENT_WORKER,
        task_name=SOURCE_DATA_ARTIFACT_CLEANUP_TASK_NAME,
        status=status,
        details=result,
        recorded_at=now,
    )
    return result


def _latest_worker_heartbeat() -> ETLHeartbeat | None:
    return (
        ETLHeartbeat.objects.filter(component=ETLHeartbeat.COMPONENT_WORKER)
        .order_by("-recorded_at")
        .first()
    )


def _worker_health(now) -> dict[str, Any]:
    heartbeat = _latest_worker_heartbeat()
    stale_after_seconds = _source_data_task_stale_minutes() * 60
    if heartbeat is None:
        return {
            "status": "missing",
            "latest_heartbeat_at": None,
            "latest_task_name": "",
            "latest_status": "",
            "age_seconds": None,
            "stale_after_seconds": stale_after_seconds,
        }

    age_seconds = max(int((now - heartbeat.recorded_at).total_seconds()), 0)
    status = "current" if age_seconds <= stale_after_seconds and heartbeat.status == ETLHeartbeat.STATUS_OK else "stale"
    if heartbeat.status == ETLHeartbeat.STATUS_FAILED:
        status = "failed"
    return {
        "status": status,
        "latest_heartbeat_at": heartbeat.recorded_at.isoformat(),
        "latest_task_name": heartbeat.task_name,
        "latest_status": heartbeat.status,
        "age_seconds": age_seconds,
        "stale_after_seconds": stale_after_seconds,
    }


def build_source_data_operations_payload(*, now=None) -> dict[str, Any]:
    now = now or timezone.now()
    lookback_cutoff = now - timedelta(hours=_source_data_alert_lookback_hours())
    stale_task_cutoff = now - timedelta(minutes=_source_data_task_stale_minutes())
    recent_uploads = list(SourceDataUploadBatch.objects.filter(created_at__gte=lookback_cutoff))
    duplicate_attempts = [
        upload
        for upload in recent_uploads
        if upload.duplicate_of_id
        or (upload.metadata or {}).get("duplicate_file_sha256")
        or (upload.metadata or {}).get("duplicate_metadata_upload_public_id")
    ]

    freshness = build_source_data_freshness_payload()
    overdue_sources = [
        source
        for source in freshness["sources"]
        if source["feed_key"] and source["status"] in {STATUS_STALE, STATUS_MISSING, STATUS_FAILED}
    ]
    status_counts = dict(
        SourceDataUploadBatch.objects.values("status")
        .annotate(count=Count("id"))
        .values_list("status", "count")
    )
    validation_failure_count = SourceDataUploadBatch.objects.filter(
        validation_status=SourceDataUploadBatch.VALIDATION_FAILED,
        updated_at__gte=lookback_cutoff,
    ).count()
    import_failure_count = SourceDataUploadBatch.objects.filter(
        import_status=SourceDataUploadBatch.IMPORT_FAILED,
        updated_at__gte=lookback_cutoff,
    ).count()
    stuck_imports = list(
        SourceDataUploadBatch.objects.filter(
            status=SourceDataUploadBatch.STATUS_CONFIRMING,
            import_status=SourceDataUploadBatch.IMPORT_RUNNING,
            updated_at__lt=stale_task_cutoff,
        ).order_by("updated_at")[:10]
    )
    stuck_validations = list(
        SourceDataUploadBatch.objects.filter(
            status=SourceDataUploadBatch.STATUS_VALIDATING,
            validation_status=SourceDataUploadBatch.VALIDATION_RUNNING,
            updated_at__lt=stale_task_cutoff,
        ).order_by("updated_at")[:10]
    )
    expired_raw_artifact_count = (
        SourceDataUploadArtifact.objects.filter(
            retention_expires_at__isnull=False,
            retention_expires_at__lte=now,
        )
        .exclude(redaction_state="purged")
        .count()
    )
    next_artifact_expiry = (
        SourceDataUploadArtifact.objects.filter(
            retention_expires_at__isnull=False,
            retention_expires_at__gt=now,
        )
        .exclude(redaction_state="purged")
        .order_by("retention_expires_at")
        .first()
    )
    worker_health = _worker_health(now)

    alerts: list[dict[str, Any]] = []
    if import_failure_count >= _source_data_failed_import_alert_threshold():
        alerts.append(
            {
                "key": "repeated_failed_imports",
                "severity": "danger",
                "title": "Repeated failed imports",
                "message": f"{import_failure_count} source-data imports failed in the last {_source_data_alert_lookback_hours()} hours.",
                "recommended_action": "Review failed import summaries, correct the source CSV, then re-run dry validation.",
            }
        )
    if overdue_sources:
        labels = ", ".join(source["label"] for source in overdue_sources[:3])
        alerts.append(
            {
                "key": "overdue_critical_feeds",
                "severity": "danger",
                "title": "Overdue critical feeds",
                "message": f"{len(overdue_sources)} source-data feeds are stale, missing, or failed: {labels}.",
                "recommended_action": "Refresh the overdue CSV sources or investigate the latest failed feed import.",
            }
        )
    if stuck_imports or stuck_validations:
        alerts.append(
            {
                "key": "stuck_source_data_tasks",
                "severity": "danger",
                "title": "Stuck source-data task",
                "message": f"{len(stuck_imports)} imports and {len(stuck_validations)} validations are older than the task SLA.",
                "recommended_action": "Check Celery workers, then retry validation or confirmation after the worker is healthy.",
            }
        )
    if worker_health["status"] in {"missing", "stale", "failed"}:
        alerts.append(
            {
                "key": "source_data_worker_health",
                "severity": "warning" if worker_health["status"] != "failed" else "danger",
                "title": "Worker heartbeat is not current",
                "message": "Source-data background progress may not continue until worker heartbeat recovers.",
                "recommended_action": "Check Celery worker and scheduler health before queueing large imports.",
            }
        )

    return {
        "schema_version": SOURCE_DATA_OPERATIONS_SCHEMA_VERSION,
        "generated_at": now.isoformat(),
        "lookback_hours": _source_data_alert_lookback_hours(),
        "metrics": {
            "upload_count": SourceDataUploadBatch.objects.count(),
            "recent_upload_count": len(recent_uploads),
            "validation_failure_count": validation_failure_count,
            "import_failure_count": import_failure_count,
            "stale_feed_count": len(overdue_sources),
            "duplicate_attempt_count": len(duplicate_attempts),
            "status_counts": status_counts,
        },
        "worker_health": worker_health,
        "stuck_tasks": {
            "stale_after_minutes": _source_data_task_stale_minutes(),
            "imports": [
                {
                    "public_id": str(upload.public_id),
                    "feed_key": upload.feed_key,
                    "status": upload.status,
                    "import_celery_task_id": upload.import_celery_task_id,
                    "updated_at": upload.updated_at.isoformat(),
                }
                for upload in stuck_imports
            ],
            "validations": [
                {
                    "public_id": str(upload.public_id),
                    "feed_key": upload.feed_key,
                    "status": upload.status,
                    "validation_celery_task_id": upload.validation_celery_task_id,
                    "updated_at": upload.updated_at.isoformat(),
                }
                for upload in stuck_validations
            ],
        },
        "retention": {
            "raw_upload_retention_days": int(getattr(settings, "SOURCE_DATA_RAW_UPLOAD_RETENTION_DAYS", 30)),
            "expired_raw_artifact_count": expired_raw_artifact_count,
            "purged_artifact_count": SourceDataUploadArtifact.objects.filter(redaction_state="purged").count(),
            "next_artifact_expiry_at": _iso(next_artifact_expiry.retention_expires_at if next_artifact_expiry else None),
            "cleanup_task_name": SOURCE_DATA_ARTIFACT_CLEANUP_TASK_NAME,
        },
        "alerts": alerts,
        "production_controls": {
            "backup_restore_reference": "docs/SOURCE_DATA_PRODUCTION_RUNBOOK.md",
            "antivirus_scanning_hook": "deployment_ingress_or_object_storage_hook_required_before_pilot_if_policy_requires_av",
            "audit_review_reference": "Review source-data upload events and auth audit template-download events weekly.",
        },
    }
