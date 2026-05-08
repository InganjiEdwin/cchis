from __future__ import annotations

import hashlib
from datetime import timedelta
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from accounts.role_capabilities import user_is_admin_equivalent

from risk.models import (
    FacilityReadinessIngestionRun,
    PopulationExposureIngestionRun,
    SourceDataUploadArtifact,
    SourceDataUploadBatch,
    SourceDataUploadEvent,
    SourceDataValidationIssue,
    SurveillanceIngestionRun,
)
from risk.facility_readiness_ingestion import run_facility_readiness_snapshot_ingestion
from risk.population_exposure_ingestion import run_population_exposure_csv_ingestion
from risk.source_data.events import record_source_data_upload_system_event
from risk.source_data.features import (
    FEATURE_FACILITY_READINESS_IMPORT,
    FEATURE_IMPORT_CONFIRM,
    facility_readiness_snapshot_import_enabled,
    require_source_data_feature,
)
from risk.source_data.phase0 import (
    INGESTION_FAMILY_FACILITY_READINESS,
    INGESTION_FAMILY_POPULATION_EXPOSURE,
    INGESTION_FAMILY_SURVEILLANCE,
)
from risk.source_data.registry import source_data_feed_definition
from risk.source_data.uploads import latest_upload_artifact
from risk.surveillance_ingestion import run_surveillance_csv_ingestion


ROUTINE_APPROVAL_CATEGORY = ""
RISK_HISTORICAL_BACKFILL = "historical_backfill"
RISK_REPLACEMENT_IMPORT = "replacement_import"
RISK_REPLAY_IMPORT = "replay_import"
RISK_PRODUCTION_SURVEILLANCE_TRUTH = "production_surveillance_truth"
RISK_UNUSUALLY_LARGE_SOURCE_DELTA = "unusually_large_source_delta"


def _hash_file(path: Path) -> str:
    sha256 = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _approval_expiry_at():
    return timezone.now() + timedelta(hours=getattr(settings, "SOURCE_DATA_APPROVAL_EXPIRY_HOURS", 72))


def _is_admin(user) -> bool:
    return bool(user and user.is_authenticated and user_is_admin_equivalent(user))


def _is_admin_or_supervisor(user) -> bool:
    return bool(
        user
        and user.is_authenticated
        and (
            user_is_admin_equivalent(user)
            or user.role == User.ROLE_SUPERVISOR
        )
    )


def duplicate_replay_requires_approval(batch: SourceDataUploadBatch) -> bool:
    metadata = batch.metadata or {}
    return bool(metadata.get("duplicate_file_sha256") and metadata.get("duplicate_metadata_upload_public_id"))


def _validation_summary(batch: SourceDataUploadBatch) -> dict[str, Any]:
    return (batch.metadata or {}).get("validation_summary") or {}


def _contains_production_surveillance_truth(batch: SourceDataUploadBatch) -> bool:
    if not batch.feed_key.startswith("surveillance_"):
        return False
    summary = _validation_summary(batch)
    truth_level_counts = summary.get("truth_level_counts") or {}
    case_class_counts = summary.get("case_class_counts") or {}

    def count(mapping: dict[str, Any], key: str) -> int:
        try:
            return int(mapping.get(key) or 0)
        except (TypeError, ValueError):
            return 0

    return bool(
        count(truth_level_counts, "confirmed_surveillance") > 0
        or count(case_class_counts, "confirmed") > 0
    )


def source_data_import_risk_category(batch: SourceDataUploadBatch) -> str:
    correction_mode = (batch.correction_mode or "").strip()
    if duplicate_replay_requires_approval(batch):
        return RISK_REPLAY_IMPORT
    if batch.replaces_upload_id or batch.replacement_reason.strip() or correction_mode == "release_replacement":
        return RISK_REPLACEMENT_IMPORT
    if batch.feed_key == "surveillance_backfill" or correction_mode == SurveillanceIngestionRun.CORRECTION_BACKFILL:
        return RISK_HISTORICAL_BACKFILL
    if correction_mode == SurveillanceIngestionRun.CORRECTION_AMENDMENT:
        return RISK_REPLACEMENT_IMPORT
    if _contains_production_surveillance_truth(batch):
        return RISK_PRODUCTION_SURVEILLANCE_TRUTH
    if batch.row_count >= getattr(settings, "SOURCE_DATA_LARGE_DELTA_APPROVAL_ROW_THRESHOLD", 10000):
        return RISK_UNUSUALLY_LARGE_SOURCE_DELTA
    return ROUTINE_APPROVAL_CATEGORY


def _assert_validated_artifact_unchanged(batch: SourceDataUploadBatch) -> SourceDataUploadArtifact:
    artifact = latest_upload_artifact(batch)
    artifact_path = Path(artifact.storage_path)
    if not artifact_path.exists():
        raise ValueError("Stored upload artifact is missing from shared durable storage.")
    current_hash = _hash_file(artifact_path)
    if current_hash != artifact.sha256:
        raise ValueError("Stored upload artifact hash no longer matches the uploaded file hash.")

    validation_summary = _validation_summary(batch)
    validated_hash = validation_summary.get("validated_artifact_sha256")
    if not validated_hash:
        raise ValueError("Upload must be dry-validated again before confirmation.")
    if validated_hash != artifact.sha256:
        raise ValueError("Upload artifact has changed since dry validation.")
    return artifact


def _assert_reason_requirements(batch: SourceDataUploadBatch, risk_category: str) -> None:
    if risk_category == RISK_HISTORICAL_BACKFILL and not (batch.operator_note or "").strip():
        raise ValueError("Historical backfill imports require an explicit operator note.")
    if risk_category == RISK_REPLACEMENT_IMPORT and not (batch.replacement_reason or "").strip():
        raise ValueError("Replacement imports require an explicit replacement reason.")


def _assert_feed_import_feature_enabled(batch: SourceDataUploadBatch) -> None:
    definition = source_data_feed_definition(batch.feed_key)
    if definition.ingestion_family == INGESTION_FAMILY_FACILITY_READINESS and not facility_readiness_snapshot_import_enabled():
        raise ValueError(f"Facility readiness snapshot imports are disabled by {FEATURE_FACILITY_READINESS_IMPORT}.")


def _approval_is_expired(batch: SourceDataUploadBatch) -> bool:
    return bool(batch.approval_expires_at and batch.approval_expires_at <= timezone.now())


def assert_source_data_upload_can_confirm(
    batch: SourceDataUploadBatch,
    *,
    allow_duplicate_replay: bool = False,
) -> SourceDataUploadArtifact:
    if batch.status != SourceDataUploadBatch.STATUS_READY_FOR_CONFIRMATION:
        raise ValueError("Only uploads that passed dry validation can be confirmed.")
    if batch.validation_status != SourceDataUploadBatch.VALIDATION_PASSED:
        raise ValueError("Upload validation must pass before confirmation.")
    if batch.validation_issues.filter(severity=SourceDataValidationIssue.SEVERITY_ERROR).exists():
        raise ValueError("Upload has validation errors and cannot be confirmed.")
    _assert_feed_import_feature_enabled(batch)

    artifact = _assert_validated_artifact_unchanged(batch)
    risk_category = source_data_import_risk_category(batch)
    _assert_reason_requirements(batch, risk_category)

    if duplicate_replay_requires_approval(batch) and not allow_duplicate_replay:
        raise ValueError("Duplicate file and metadata imports are blocked unless explicitly confirmed as a replay.")

    if risk_category:
        if _approval_is_expired(batch):
            batch.approval_status = SourceDataUploadBatch.APPROVAL_EXPIRED
            batch.save(update_fields=["approval_status", "updated_at"])
            raise ValueError("Maker-checker approval has expired.")
        if batch.approval_status != SourceDataUploadBatch.APPROVAL_APPROVED:
            raise ValueError("This risky import requires approved maker-checker review before confirmation.")
    return artifact


@transaction.atomic
def request_source_data_upload_approval(
    *,
    batch: SourceDataUploadBatch,
    requested_by,
    reason: str,
) -> SourceDataUploadBatch:
    if not _is_admin_or_supervisor(requested_by):
        raise ValueError("Only admins or supervisors can request source-data import approval.")
    if batch.status != SourceDataUploadBatch.STATUS_READY_FOR_CONFIRMATION:
        raise ValueError("Approval can only be requested after successful dry validation.")

    risk_category = source_data_import_risk_category(batch)
    if not risk_category:
        batch.approval_status = SourceDataUploadBatch.APPROVAL_NOT_REQUIRED
        batch.approval_risk_category = ""
        batch.approval_reason = ""
        batch.save(update_fields=["approval_status", "approval_risk_category", "approval_reason", "updated_at"])
        return batch
    _assert_reason_requirements(batch, risk_category)
    if not reason.strip():
        raise ValueError("A reason is required when requesting maker-checker approval.")

    batch.approval_status = SourceDataUploadBatch.APPROVAL_PENDING
    batch.approval_risk_category = risk_category
    batch.approval_requested_by = requested_by
    batch.approval_requested_at = timezone.now()
    batch.approved_by = None
    batch.approved_at = None
    batch.approval_reason = reason.strip()
    batch.approval_expires_at = _approval_expiry_at()
    batch.save(
        update_fields=[
            "approval_status",
            "approval_risk_category",
            "approval_requested_by",
            "approval_requested_at",
            "approved_by",
            "approved_at",
            "approval_reason",
            "approval_expires_at",
            "updated_at",
        ]
    )
    return batch


@transaction.atomic
def decide_source_data_upload_approval(
    *,
    batch: SourceDataUploadBatch,
    decided_by,
    action: str,
    reason: str = "",
) -> SourceDataUploadBatch:
    if not _is_admin(decided_by):
        raise ValueError("Only admins can approve or reject risky source-data imports.")
    if batch.approval_status != SourceDataUploadBatch.APPROVAL_PENDING:
        raise ValueError("This upload does not have a pending approval request.")
    if _approval_is_expired(batch):
        batch.approval_status = SourceDataUploadBatch.APPROVAL_EXPIRED
        batch.save(update_fields=["approval_status", "updated_at"])
        raise ValueError("Maker-checker approval has expired.")
    if batch.approval_requested_by_id == decided_by.id or batch.created_by_id == decided_by.id:
        raise ValueError("The uploader/requester cannot approve their own risky import.")
    if not reason.strip():
        raise ValueError("A reason is required for maker-checker approval decisions.")

    if action == "approve":
        batch.approval_status = SourceDataUploadBatch.APPROVAL_APPROVED
    elif action == "reject":
        batch.approval_status = SourceDataUploadBatch.APPROVAL_REJECTED
    else:
        raise ValueError("Unsupported approval action.")
    batch.approved_by = decided_by
    batch.approved_at = timezone.now()
    batch.approval_reason = reason.strip()
    batch.save(
        update_fields=[
            "approval_status",
            "approved_by",
            "approved_at",
            "approval_reason",
            "updated_at",
        ]
    )
    return batch


def _surveillance_correction_mode(batch: SourceDataUploadBatch) -> str:
    valid_modes = {choice[0] for choice in SurveillanceIngestionRun.CORRECTION_MODE_CHOICES}
    if batch.correction_mode in valid_modes:
        return batch.correction_mode
    if batch.feed_key == "surveillance_backfill":
        return SurveillanceIngestionRun.CORRECTION_BACKFILL
    return SurveillanceIngestionRun.CORRECTION_ORIGINAL


def _population_exposure_correction_mode(batch: SourceDataUploadBatch) -> str:
    if batch.replaces_upload_id:
        return PopulationExposureIngestionRun.CORRECTION_RELEASE_REPLACEMENT
    valid_modes = {choice[0] for choice in PopulationExposureIngestionRun.CORRECTION_MODE_CHOICES}
    if batch.correction_mode in valid_modes:
        return batch.correction_mode
    return PopulationExposureIngestionRun.CORRECTION_ORIGINAL


def _execute_domain_import(
    *,
    batch: SourceDataUploadBatch,
    artifact: SourceDataUploadArtifact,
):
    definition = source_data_feed_definition(batch.feed_key)
    artifact_path = Path(artifact.storage_path)
    if definition.ingestion_family == INGESTION_FAMILY_SURVEILLANCE:
        return run_surveillance_csv_ingestion(
            file_path=artifact_path,
            source_name=batch.source_name,
            source_type=batch.source_type,
            source_timestamp=batch.source_timestamp,
            reporting_period_start=batch.reporting_period_start,
            reporting_period_end=batch.reporting_period_end,
            source_ref=batch.source_ref,
            correction_mode=_surveillance_correction_mode(batch),
            correction_reason=batch.replacement_reason or batch.operator_note,
            operator_note=batch.operator_note,
            execution_mode=SurveillanceIngestionRun.EXECUTION_MANUAL,
        )

    if definition.ingestion_family == INGESTION_FAMILY_POPULATION_EXPOSURE:
        replaces_run = None
        if batch.replaces_upload_id:
            replaces_run = batch.replaces_upload.population_exposure_ingestion_run
            if replaces_run is None:
                raise ValueError("Replacement upload must reference a prior population/exposure ingestion run.")
        return run_population_exposure_csv_ingestion(
            file_path=artifact_path,
            source_name=batch.source_name,
            source_type=batch.source_type,
            source_timestamp=batch.source_timestamp,
            release_version=batch.release_version,
            source_ref=batch.source_ref,
            correction_mode=_population_exposure_correction_mode(batch),
            replacement_reason=batch.replacement_reason,
            operator_note=batch.operator_note,
            execution_mode=PopulationExposureIngestionRun.EXECUTION_MANUAL,
            replaces_run=replaces_run,
        )

    if definition.ingestion_family == INGESTION_FAMILY_FACILITY_READINESS:
        if not facility_readiness_snapshot_import_enabled():
            raise ValueError(f"Facility readiness snapshot imports are disabled by {FEATURE_FACILITY_READINESS_IMPORT}.")
        return run_facility_readiness_snapshot_ingestion(
            file_path=artifact_path,
            source_name=batch.source_name,
            source_type=batch.source_type,
            source_timestamp=batch.source_timestamp,
            reporting_period_start=batch.reporting_period_start,
            reporting_period_end=batch.reporting_period_end,
            source_ref=batch.source_ref,
            operator_note=batch.operator_note,
            execution_mode=FacilityReadinessIngestionRun.EXECUTION_MANUAL,
        )
    raise ValueError(f"Unsupported source-data ingestion family: {definition.ingestion_family}")


def _link_domain_run(batch: SourceDataUploadBatch, run) -> None:
    if isinstance(run, SurveillanceIngestionRun):
        batch.domain_ingestion_run_type = "surveillance"
        batch.domain_ingestion_run_id = run.id
        batch.surveillance_ingestion_run = run
    elif isinstance(run, PopulationExposureIngestionRun):
        batch.domain_ingestion_run_type = "population_exposure"
        batch.domain_ingestion_run_id = run.id
        batch.population_exposure_ingestion_run = run
    elif isinstance(run, FacilityReadinessIngestionRun):
        batch.domain_ingestion_run_type = "facility_readiness"
        batch.domain_ingestion_run_id = run.id
        batch.facility_readiness_ingestion_run_id = run.id
    else:
        raise ValueError("Unsupported domain ingestion run type.")


def run_confirmed_source_data_import(
    batch: SourceDataUploadBatch,
    *,
    actor=None,
    worker_execution: bool = False,
) -> SourceDataUploadBatch:
    require_source_data_feature(FEATURE_IMPORT_CONFIRM)
    batch = SourceDataUploadBatch.objects.select_related(
        "replaces_upload",
        "population_exposure_ingestion_run",
        "surveillance_ingestion_run",
    ).get(pk=batch.pk)
    artifact = _assert_validated_artifact_unchanged(batch)

    record_source_data_upload_system_event(
        batch=batch,
        event_type=SourceDataUploadEvent.EVENT_IMPORT_STARTED,
        actor=actor,
        metadata={"artifact_sha256": artifact.sha256, "worker_execution": worker_execution},
    )

    try:
        run = _execute_domain_import(batch=batch, artifact=artifact)
        _link_domain_run(batch, run)
        batch.row_count = run.records_seen
        batch.accepted_count = run.records_loaded
        batch.rejected_count = run.records_rejected
        batch.import_status = (
            SourceDataUploadBatch.IMPORT_FAILED
            if run.status
            in {
                SurveillanceIngestionRun.STATUS_FAILED,
                PopulationExposureIngestionRun.STATUS_FAILED,
                FacilityReadinessIngestionRun.STATUS_FAILED,
            }
            else SourceDataUploadBatch.IMPORT_IMPORTED
        )
        batch.status = (
            SourceDataUploadBatch.STATUS_IMPORT_FAILED
            if batch.import_status == SourceDataUploadBatch.IMPORT_FAILED
            else SourceDataUploadBatch.STATUS_IMPORTED
        )
        batch.metadata = {
            **(batch.metadata or {}),
            "import_summary": {
                "domain_ingestion_run_type": batch.domain_ingestion_run_type,
                "domain_ingestion_run_id": batch.domain_ingestion_run_id,
                "domain_run_status": run.status,
                "records_seen": run.records_seen,
                "records_loaded": run.records_loaded,
                "records_rejected": run.records_rejected,
                "error_summary": getattr(run, "error_summary", ""),
            },
        }
        batch.save(
            update_fields=[
                "status",
                "import_status",
                "row_count",
                "accepted_count",
                "rejected_count",
                "domain_ingestion_run_type",
                "domain_ingestion_run_id",
                "surveillance_ingestion_run",
                "population_exposure_ingestion_run",
                "facility_readiness_ingestion_run_id",
                "metadata",
                "updated_at",
            ]
        )
    except Exception as error:
        batch.status = SourceDataUploadBatch.STATUS_IMPORT_FAILED
        batch.import_status = SourceDataUploadBatch.IMPORT_FAILED
        batch.metadata = {
            **(batch.metadata or {}),
            "import_summary": {
                "domain_ingestion_run_type": batch.domain_ingestion_run_type,
                "domain_ingestion_run_id": batch.domain_ingestion_run_id,
                "error_summary": str(error),
            },
        }
        batch.save(update_fields=["status", "import_status", "metadata", "updated_at"])
        record_source_data_upload_system_event(
            batch=batch,
            event_type=SourceDataUploadEvent.EVENT_IMPORT_FAILED,
            actor=actor,
            metadata={"error_summary": str(error)},
        )
        return batch

    event_type = (
        SourceDataUploadEvent.EVENT_IMPORT_FAILED
        if batch.import_status == SourceDataUploadBatch.IMPORT_FAILED
        else SourceDataUploadEvent.EVENT_IMPORT_COMPLETED
    )
    record_source_data_upload_system_event(
        batch=batch,
        event_type=event_type,
        actor=actor,
        metadata=(batch.metadata or {}).get("import_summary") or {},
    )
    return batch


@transaction.atomic
def confirm_source_data_upload(
    *,
    batch: SourceDataUploadBatch,
    confirmed_by,
    allow_duplicate_replay: bool = False,
    force_async: bool = False,
) -> SourceDataUploadBatch:
    require_source_data_feature(FEATURE_IMPORT_CONFIRM)
    if not _is_admin_or_supervisor(confirmed_by):
        raise ValueError("Only admins or supervisors can confirm source-data imports.")

    artifact = assert_source_data_upload_can_confirm(
        batch,
        allow_duplicate_replay=allow_duplicate_replay,
    )
    risk_category = source_data_import_risk_category(batch)
    if not risk_category:
        batch.approval_status = SourceDataUploadBatch.APPROVAL_NOT_REQUIRED

    batch.status = SourceDataUploadBatch.STATUS_CONFIRMING
    batch.import_status = SourceDataUploadBatch.IMPORT_RUNNING
    batch.confirmed_by = confirmed_by
    batch.confirmed_at = timezone.now()
    batch.metadata = {
        **(batch.metadata or {}),
        "confirmation": {
            "confirmed_by_user_id": confirmed_by.id,
            "confirmed_at": batch.confirmed_at.isoformat(),
            "allow_duplicate_replay": allow_duplicate_replay,
            "approval_risk_category": risk_category,
        },
    }
    batch.save(
        update_fields=[
            "status",
            "import_status",
            "confirmed_by",
            "confirmed_at",
            "approval_status",
            "metadata",
            "updated_at",
        ]
    )

    should_import_async = force_async or artifact.size_bytes >= getattr(settings, "SOURCE_DATA_ASYNC_IMPORT_SIZE_BYTES", 5 * 1024 * 1024)
    if should_import_async:
        from risk.tasks import import_source_data_upload_batch_task

        async_result = import_source_data_upload_batch_task.delay(batch.id, confirmed_by.id)
        batch.import_celery_task_id = async_result.id
        batch.save(update_fields=["import_celery_task_id", "updated_at"])
        record_source_data_upload_system_event(
            batch=batch,
            event_type=SourceDataUploadEvent.EVENT_IMPORT_STARTED,
            actor=confirmed_by,
            metadata={"queued": True, "celery_task_id": async_result.id, "artifact_size_bytes": artifact.size_bytes},
        )
        return batch

    return run_confirmed_source_data_import(batch, actor=confirmed_by)
