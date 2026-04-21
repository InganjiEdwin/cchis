# Operational Runbook And Recovery Inputs

## Purpose

This document defines the minimum operational inputs CCHIS maintainers should have available during incidents and recovery workflows.

The goal is not to write a full production runbook yet.
The goal is to make sure incident review and restoreability are not left vague until after something breaks.

## Current Rule

When an incident happens, maintainers should already know:

- which logs matter
- which metrics matter
- which durable records matter
- which restore signals must exist before anyone claims recovery succeeded

The source of truth for the inventories in this document lives in `backend/core/observability.py`.

## Minimum Incident Review Inputs

The minimum runbook inventory currently exists as `MINIMUM_RUNBOOK_INPUTS`.

### API and Security

- `request_trace_logs`
  - use to identify affected paths, methods, status classes, and time windows
- `auth_audit_events`
  - use to investigate login abuse, unexpected admin actions, and account misuse
- `api_latency_and_volume_metrics`
  - use to confirm whether the problem is local to one workflow or part of broader request degradation

### Sync, Triage, and USSD

- `sync_processing_metrics`
  - use to detect replay spikes, processing failures, and field-sync disruption
- `sync_queue_state`
  - use to inspect pending, processed, failed, and replayed submissions directly
- `triage_and_referral_metrics`
  - use to see whether frontline decision-support behavior changed unexpectedly
- `ussd_request_metrics_and_logs`
  - use to detect public-endpoint misuse, malformed payloads, or menu-flow failures
- `ussd_session_logs`
  - use to inspect exact inbound text and response strings for low-connectivity investigations

### Forecasting and Alerts

- `ingestion_run_records`
  - use to confirm source mode, fallback use, completion state, and affected wards
- `model_run_records`
  - use to trace forecast lineage, execution state, and dataset references
- `alert_delivery_state`
  - use to diagnose queued, retry-pending, delivered, or failed alert behavior

### Manual-Action Context

- `domain_audit_inventory`
  - use to identify which non-auth overrides and operator actions should have durable accountability when those workflows are implemented

## Practical Incident Questions

These inputs should let maintainers answer questions such as:

- Is the problem limited to auth, a single endpoint family, or the whole API surface?
- Are field submissions being replayed, dropped, or failing after ingestion?
- Did rainfall ingestion fall back to static data for the affected wards?
- Did a model run fail, partially complete, or use unexpected lineage inputs?
- Are alerts failing because creation stopped, delivery retries piled up, or a provider boundary broke?
- Did a manual override or operator action change the expected operational state?

## Backup And Restore Visibility Expectations

The minimum recovery visibility inventory currently exists as `RECOVERY_VISIBILITY_REQUIREMENTS`.

### Backup Execution

Every backup workflow should expose at least:

- backup start and completion time
- success or failure status
- artifact reference
- database engine version
- migration or schema state
- coverage window for the backed-up data

Without those signals, maintainers cannot tell whether a backup is recent, compatible, or complete enough to trust.

### Restore Execution

Every restore workflow should expose at least:

- restore start and completion time
- success or failure status
- source artifact reference
- target environment
- database engine version
- applied migration state

Without those signals, restore failures become guesswork and schema drift becomes hard to diagnose.

### Post-Restore Validation

A restore should not be considered complete until maintainers can see:

- application health-check outcome
- API smoke-test outcome
- validation completion time
- row-count sanity summary
- critical-model count summary
- operator validation notes

For CCHIS, the critical-model sanity check should focus first on records such as:

- `Ward`
- `RiskScore`
- `Alert`
- `IngestionRun`
- `ModelRun`
- `SyncQueue`

### Recovery Rehearsal

Restoreability should be proven, not assumed.

At minimum, recovery drills should leave evidence of:

- rehearsal date
- duration
- outcome
- backup artifact tested
- observed gaps
- follow-up actions

## What This Phase Does And Does Not Require

This phase does require:

- a written incident-input inventory
- a written backup and restore visibility inventory
- explicit expectations for post-restore validation

This phase does not yet require:

- automated backup tooling in the repo
- a restore command
- production dashboards
- a formal RPO or RTO commitment
- a dedicated incident-management system

Those belong to later operational maturity work, but the visibility expectations now keep future recovery work honest.
