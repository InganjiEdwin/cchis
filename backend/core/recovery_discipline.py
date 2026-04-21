from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BackupExpectation:
    workflow_name: str
    target_scope: str
    required_evidence: tuple[str, ...]
    minimum_validation: tuple[str, ...]
    rationale: str


@dataclass(frozen=True)
class RestoreRehearsalExpectation:
    rehearsal_name: str
    target_environment_class: str
    required_steps: tuple[str, ...]
    success_evidence: tuple[str, ...]
    rationale: str


BACKUP_EXPECTATIONS: tuple[BackupExpectation, ...] = (
    BackupExpectation(
        workflow_name="database_backup_artifact",
        target_scope="primary_postgres_database",
        required_evidence=(
            "backup_started_at",
            "backup_completed_at",
            "backup_status",
            "backup_artifact_reference",
            "database_engine_version",
            "schema_migration_state",
            "backup_coverage_window",
        ),
        minimum_validation=(
            "artifact_is_identifiable",
            "schema_state_is_recorded",
            "failure_is_visible",
        ),
        rationale="A database backup is not operationally trustworthy if maintainers cannot tie it to a concrete artifact, schema state, and time window.",
    ),
    BackupExpectation(
        workflow_name="restore_execution_record",
        target_scope="restore_attempt",
        required_evidence=(
            "restore_started_at",
            "restore_completed_at",
            "restore_status",
            "restore_source_artifact_reference",
            "target_environment",
            "database_engine_version",
            "applied_migration_state",
        ),
        minimum_validation=(
            "target_environment_is_named",
            "source_artifact_is_traceable",
            "migration_state_is_confirmed",
        ),
        rationale="A restore attempt must leave enough evidence to diagnose compatibility or ordering failures instead of forcing maintainers to guess.",
    ),
    BackupExpectation(
        workflow_name="post_restore_validation_record",
        target_scope="restored_application_state",
        required_evidence=(
            "application_health_check_result",
            "api_smoke_test_result",
            "restore_validation_completed_at",
            "row_count_sanity_summary",
            "critical_model_count_summary",
            "operator_validation_notes",
        ),
        minimum_validation=(
            "application_boots",
            "core_api_contract_responds",
            "critical_record_counts_look_plausible",
        ),
        rationale="A restore is incomplete until maintainers verify the restored system boots, answers core API requests, and contains plausible critical records.",
    ),
)


RESTORE_REHEARSAL_EXPECTATIONS: tuple[RestoreRehearsalExpectation, ...] = (
    RestoreRehearsalExpectation(
        rehearsal_name="shared_environment_restore_rehearsal",
        target_environment_class="staging",
        required_steps=(
            "select_backup_artifact",
            "record_target_environment",
            "perform_restore",
            "apply_or_confirm_migration_state",
            "run_post_restore_validation",
            "capture_gaps_and_follow_ups",
        ),
        success_evidence=(
            "rehearsal_date",
            "recovery_duration",
            "rehearsal_outcome",
            "tested_backup_artifact_reference",
            "observed_gaps",
            "follow_up_actions",
        ),
        rationale="Restoreability should be rehearsed in a shared, deployment-like environment before an actual incident forces the process.",
    ),
)
