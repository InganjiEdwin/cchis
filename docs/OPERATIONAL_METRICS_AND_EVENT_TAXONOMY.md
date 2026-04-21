# Operational Metrics And Event Taxonomy

## Purpose

This document defines the minimum observability inventory for CCHIS v1 so the system can be monitored, debugged, and operated intentionally.

## Current Visibility Layers

The codebase already uses three different visibility layers:

- logs
  - request logging
  - ML pipeline and ingestion logging
  - alert-delivery logging
- audit events
  - durable auth events stored in `AuthAuditEvent`
- domain records with operational meaning
  - `IngestionRun`
  - `ModelRun`
  - `Alert`
  - `SyncQueue`

The key rule is that these layers are not interchangeable.

## Event Taxonomy

### Log

Use a log when the event is primarily for debugging, timing, or execution tracing.

Examples:

- `request_complete`
- `risk_model_run_started`
- `risk_model_run_completed`
- `trigger_alerts_started`
- `trigger_alerts_completed`
- `deliver_alert_task_completed`

Logs are not the durable accountability record.

### Metric

Use a metric when the main question is:

- how many
- how often
- how long
- how much is failing right now

Metrics are for dashboards, SLOs, threshold alerts, and trend analysis.

### Audit Event

Use an audit event when the action must be durably attributable later.

Current durable audit scope:

- login success or failure
- refresh success or failure
- logout
- user creation
- password change
- user deactivation or reactivation

Audit events are not a substitute for metrics, and metrics are not a substitute for audit events.

## Minimum v1 Metric Inventory

The current source of truth for the inventory lives in `backend/core/observability.py`.

### API metrics

- `http_requests_total`
- `http_request_duration_ms`

### Auth metrics

- `auth_login_attempts_total`
- `auth_refresh_attempts_total`
- `auth_account_actions_total`

### Sync metrics

- `sync_payloads_processed_total`
- `sync_payload_replays_total`
- `sync_processing_failures_total`

### Triage metrics

- `triage_sessions_created_total`
- `triage_referrals_total`

### USSD metrics

- `ussd_requests_total`
- `ussd_invalid_option_total`

### Forecasting metrics

- `rainfall_ingestion_runs_total`
- `risk_model_runs_total`
- `risk_scores_generated_total`

### Alert metrics

- `alerts_created_total`
- `alert_delivery_attempts_total`
- `alert_delivery_retry_pending_total`

## Practical Monitoring Questions

These are the concrete questions the inventory should answer:

- Are login failures spiking?
- Are request latencies degrading on critical endpoints?
- Are CHV sync retries or failures increasing?
- Are triage referrals increasing in a ward or time window?
- Is USSD receiving invalid interactions that suggest usability or abuse problems?
- Are ingestion runs failing or falling back too often?
- Are model runs completing on schedule?
- Are alerts piling up in retry state?

## v1 Implementation Direction

This phase defines what should be measured.

It does not yet require:

- Prometheus integration
- OpenTelemetry adoption
- a full metrics backend
- operational dashboards committed to the repo

But any future instrumentation should implement this inventory instead of inventing ad hoc counters.
