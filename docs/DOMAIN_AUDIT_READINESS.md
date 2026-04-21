# Domain Audit Readiness

## Purpose

This document defines the minimum non-auth audit direction for CCHIS v1 so later operationally significant actions are not left unaudited by design.

## Current Boundary

Today, the only implemented durable audit store is `AuthAuditEvent`.

That is still correct for v1 because auth-sensitive actions are already live and must remain attributable now.

But `AuthAuditEvent` is not the future home for every audit need in the platform.

## Core Rule

Use a durable domain audit event when an operator or system action:

- materially changes operational state
- can alter risk interpretation, response, or reporting
- may need later human accountability beyond transient logs
- should be explainable even after metrics and application logs have rolled away

Do not overload `AuthAuditEvent` with non-auth workflow history.

Future non-auth audit needs should land in a dedicated domain audit mechanism such as `DomainAuditEvent`, even if that table is not implemented yet in v1.

## Current Domain Audit Inventory

The source of truth for the current inventory lives in `backend/core/observability.py` as `DOMAIN_AUDIT_INVENTORY`.

The current minimum future-required domain audit actions are:

### Forecasting

- `risk_score_manual_override`
  - target: `RiskScore`
  - why: manual forecast changes can alter downstream alerts and operational decisions
- `ingestion_run_manual_correction`
  - target: `IngestionRun`
  - why: source or provenance corrections affect how forecasts are trusted and interpreted
- `model_run_manual_backfill`
  - target: `ModelRun`
  - why: backfills and manual reruns affect lineage, reporting windows, and explainability

### Operations and Messaging

- `alert_manual_trigger`
  - target: `Alert`
  - why: manually triggered alerts can change response activity even when automation did not create them
- `alert_delivery_manual_requeue`
  - target: `Alert`
  - why: operator replay of delivery work must be distinguishable from automatic retry behavior
- `response_action_state_override`
  - target: future `ResponseAction`
  - why: future intervention assignment and completion changes require durable accountability

### Surveillance and Field Workflows

- `triage_referral_manual_override`
  - target: `TriageSession`
  - why: manual referral changes affect frontline guidance and escalation decisions
- `sync_queue_manual_replay`
  - target: `SyncQueue`
  - why: replaying field submissions can create duplicates or change what becomes durable operational data

## Manual Override Policy

Manual overrides are higher-risk than ordinary automated workflow execution and must be treated as explicitly auditable events.

Every future manual override audit event should capture at least:

- actor identity
- event timestamp
- action name
- target entity type and identifier
- reason for the override
- before and after summary for the changed operational state
- ward, facility, or other location scope when relevant
- correlation references when the action relates to a model run, ingestion run, alert, or sync submission

The reason field should be required for manual overrides rather than optional free text.

## Intervention and Response-Action Policy

Future intervention workflows should distinguish:

- notification history
  - what message or alert was created or delivered
- action history
  - what preparedness or response action was assigned, changed, escalated, or completed

`Alert` remains notification history.
It should not absorb full intervention audit history.

When a future `ResponseAction` or `InterventionAction` model exists, the audit trail should record at least:

- who created or changed the action
- what ward or facility the action targeted
- assignment or ownership changes
- status transitions
- due-date changes when relevant
- override or completion notes
- links to related risk scores, alerts, or external references

## What This Phase Does And Does Not Require

This phase does require:

- a written domain audit inventory
- a clear boundary between auth audit and future domain audit
- explicit policy for manual overrides and intervention state changes

This phase does not yet require:

- a new audit table
- admin UI for domain audit review
- automatic instrumentation of every listed action
- a retention policy for domain audit records

Those are later implementation steps, but the inventory and policy now make future work additive instead of improvised.
