# Source Data Production Runbook

This runbook covers Phase 8 pilot hardening for the source-data operations surface.

## Rate Limits

- `THROTTLE_SOURCE_DATA_UPLOAD`: default `20/hour`.
- `THROTTLE_SOURCE_DATA_VALIDATE`: default `60/hour`.
- Treat repeated throttling as an abuse signal or a training issue; operators do not need Django admin access to use the source-data surface.

## Feature Flags

- `SOURCE_DATA_OPS_ENABLED`: gates all source-data dashboard APIs.
- `SOURCE_DATA_IMPORT_CONFIRM_ENABLED`: gates maker-checker approval and import confirmation.
- `SOURCE_DATA_DOWNSTREAM_ACTIONS_ENABLED`: gates downstream rebuild actions.
- `FACILITY_READINESS_SNAPSHOT_IMPORT_ENABLED`: gates readiness snapshot uploads and imports.
- `SOURCE_DATA_API_CONNECTORS_ENABLED`: gates connector registry, refresh, and feed-mode controls.
- `SOURCE_DATA_PHASE_AUDIT_REQUIRED`: makes the phase-audit command fail closed even without `--strict`.

## Artifact Retention

- Raw upload files expire according to `SOURCE_DATA_RAW_UPLOAD_RETENTION_DAYS`.
- `risk.tasks.cleanup_source_data_upload_artifacts_task` is scheduled daily by Celery Beat. The default schedule is controlled by `SOURCE_DATA_ARTIFACT_CLEANUP_HOUR=2` and `SOURCE_DATA_ARTIFACT_CLEANUP_MINUTE=15`.
- The cleanup task deletes expired files inside `SOURCE_DATA_UPLOAD_ROOT`, marks artifact records as `purged`, and records an `ETLHeartbeat`.
- Metadata, hashes, counts, validation issues, and upload events remain for audit after raw artifacts are purged.

## Operations Health

- Monitor `/source-data/operations/` for upload counts, validation failures, import failures, duplicate attempts, stale feeds, stuck tasks, and worker heartbeat state.
- Investigate any `repeated_failed_imports`, `overdue_critical_feeds`, or `stuck_source_data_tasks` alert before queueing large imports.
- If worker heartbeat is stale, check Celery workers and scheduler before asking operators to retry.

## Retry Workflow

- Validation failure: correct the CSV, upload again or re-run dry validation if metadata was the issue.
- Import failure: correct the source CSV, run dry validation again, then confirm import.
- Replacement: admins or supervisors should use the replacement path so the original failed or superseded batch remains auditable.
- Duplicate replay: confirm only when the duplicate is intentional and documented.

## Backup And Restore

Back up these records together:

- `SourceDataUploadBatch`
- `SourceDataUploadArtifact`
- `SourceDataValidationIssue`
- `SourceDataUploadEvent`
- Domain ingestion runs linked from source-data batches
- Domain records created by those ingestion runs

Restore rehearsal evidence must include:

- Database backup artifact reference and schema migration state.
- Raw artifact backup or documented retention-purged state.
- Post-restore validation that upload hashes, domain run links, and source freshness agree.

## Security Hooks

- If county production policy requires antivirus scanning, attach it at the ingress, shared filesystem, or object-storage layer before workers read uploaded files.
- Keep source diagnostics aggregate and redacted; never export raw rejected rows with direct identifiers.
- Review source-data upload events and template-download auth audit events weekly during pilot.
