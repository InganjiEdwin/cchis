# Backend ETL Heartbeat Hardening Status

## Purpose

This mini-phase hardens ETL orchestration trust between ETL completion and ML Phase 0.

It exists so the live logistic baseline can be audited on top of:

- real Celery Beat scheduling evidence
- real worker execution evidence
- explicit heartbeat-aware ETL trust policy

## What Was Added

- `ETLHeartbeat` model for persisted scheduler and worker heartbeat records
- Celery Beat schedule entry:
  - `etl-heartbeat`
- task:
  - `risk.tasks.record_etl_heartbeat_task`
- admin support for heartbeat inspection
- serializer support for heartbeat inspection
- ETL trust-policy integration so missing or stale heartbeat state can:
  - degrade prediction trust
  - block automatic alerts
  - block scoring when orchestration health is too stale

## Verification

Verified with:

- Docker migration for `risk.0014_etlheartbeat`
- focused tests for:
  - persisted heartbeat records
  - missing heartbeat degradation
  - stale heartbeat blocking
  - schedule-gap trust behavior
  - static-mode trust behavior

## Outcome

The ETL backbone now has a minimally hardened orchestration-trust layer.

That is sufficient to proceed into:

- `BACKEND_ML_MODEL_ROADMAP_PLAN.md`
  - `Phase 0: Baseline Freeze and Truth Audit`

without pretending the scheduler and worker layer is invisible or automatically healthy.
