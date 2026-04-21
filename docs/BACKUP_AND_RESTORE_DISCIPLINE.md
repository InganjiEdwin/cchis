# Backup And Restore Discipline

This document defines the v1 discipline for backup evidence, restore evidence, and recovery rehearsal so recoverability is treated as an expected property of the system.

## Why This Exists

CCHIS already defines recovery visibility expectations in:

- [docs/OPERATIONAL_RUNBOOK_AND_RECOVERY_INPUTS.md](/Users/edwininganji/VSCodeProjects/cchis/docs/OPERATIONAL_RUNBOOK_AND_RECOVERY_INPUTS.md)
- [backend/core/observability.py](/Users/edwininganji/VSCodeProjects/cchis/backend/core/observability.py)

This phase adds the next layer of discipline:

- what a trustworthy backup record must include
- what a restore record must include
- what a rehearsal must prove and record

## Current Rule

No backup should be treated as trustworthy unless maintainers can identify:

- when it started and completed
- whether it succeeded
- which artifact it produced
- which database engine and schema state it reflects
- which data window it covers

No restore should be treated as complete unless maintainers can show:

- which artifact was restored
- which environment it was restored into
- what migration state was applied or confirmed
- that the application booted and core APIs responded afterward
- that critical record counts looked plausible

## Source Of Truth

The code-level source of truth for this discipline lives in:

- [backend/core/observability.py](/Users/edwininganji/VSCodeProjects/cchis/backend/core/observability.py) for visibility requirements
- [backend/core/recovery_discipline.py](/Users/edwininganji/VSCodeProjects/cchis/backend/core/recovery_discipline.py) for backup and rehearsal expectations

## Minimum Backup Expectations

Every backup workflow should leave evidence for:

- `backup_started_at`
- `backup_completed_at`
- `backup_status`
- `backup_artifact_reference`
- `database_engine_version`
- `schema_migration_state`
- `backup_coverage_window`

If any of those are missing, maintainers cannot tell whether the backup is recent, compatible, or complete enough to trust during a recovery event.

## Minimum Restore Expectations

Every restore workflow should leave evidence for:

- `restore_started_at`
- `restore_completed_at`
- `restore_status`
- `restore_source_artifact_reference`
- `target_environment`
- `database_engine_version`
- `applied_migration_state`

This is the minimum trace needed to debug restore failures without relying on memory or ad hoc terminal history.

## Post-Restore Validation

A restore is not complete until maintainers record:

- application health-check outcome
- API smoke-test outcome
- validation completion time
- row-count sanity summary
- critical-model count summary
- operator validation notes

For CCHIS, the critical-model sanity summary should focus first on:

- `Ward`
- `RiskScore`
- `Alert`
- `IngestionRun`
- `ModelRun`
- `SyncQueue`

## Recovery Rehearsal Rule

At least shared, staging-like environments should be used to rehearse recovery before an incident makes the workflow urgent.

Every rehearsal should leave evidence for:

- rehearsal date
- recovery duration
- outcome
- tested backup artifact reference
- observed gaps
- follow-up actions

## Practical Rehearsal Checklist

1. Select the backup artifact and record its reference.
2. Record the target environment and expected migration state.
3. Perform the restore and capture start, completion, and outcome.
4. Confirm the restored schema or applied migrations.
5. Run application health and API smoke checks.
6. Capture row-count and critical-model sanity summaries.
7. Record observed gaps and the concrete follow-up actions.

## What This Phase Does Not Claim

This phase does not add:

- automated backup orchestration
- automated restore tooling
- formal RPO or RTO commitments
- cloud-specific backup integrations

It does require future backup and restore work to be observable, reviewable, and rehearsal-friendly.
