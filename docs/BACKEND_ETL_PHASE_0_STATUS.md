# Backend ETL Phase 0 Status

## Scope

This status note records the current truth after executing:

- `Phase 0: Source and Gap Audit`
- `Phase 1: Ingestion Run Discipline`

from [BACKEND_ETL_AND_FEATURE_PIPELINE_PLAN.md](/Users/edwininganji/VSCodeProjects/cchis/docs/BACKEND_ETL_AND_FEATURE_PIPELINE_PLAN.md).

---

## What Already Existed

Before this pass, the backend already had useful ETL foundations:

- a real `IngestionRun` model in [models.py](/Users/edwininganji/VSCodeProjects/cchis/backend/risk/models.py)
- rainfall ingestion code in [ingestion.py](/Users/edwininganji/VSCodeProjects/cchis/backend/risk/ml/ingestion.py)
- linkage from `ModelRun` to `IngestionRun`
- a scheduled daily risk-model task in [settings.py](/Users/edwininganji/VSCodeProjects/cchis/backend/core/settings.py)
- observability references that already assumed ingestion and model provenance matter

So phase 0 did not start from zero.

---

## Phase 0 Findings

### Real and already backend-owned

- rainfall ingestion run records existed
- rainfall source mode and source priority were already stored
- requested wards and per-ward result payloads were already stored
- partial vs failed rainfall runs were already distinguished
- the prediction pipeline already attached rainfall ingestion runs to model runs

### Present but too thin before phase 1

- no explicit seeded-vs-live source classification on `IngestionRun`
- no explicit freshness state on `IngestionRun`
- no explicit source name on `IngestionRun`
- no source timestamp persisted on `IngestionRun`
- no explicit fallback-used flag on `IngestionRun`
- no records-seen / loaded / rejected counters on `IngestionRun`
- no dedicated rainfall ingestion task / command boundary separate from model scoring

### Still intentionally incomplete after phase 0

- rainfall ingestion is still prototype-oriented and currently centered on:
  - `open-meteo-forecast`
  - static CSV/default fallback
- surveillance, facility-readiness, CHV, and vulnerability ETL streams are not yet implemented as first-class ingestion domains
- the risk-model pipeline still performs inline rainfall fetches instead of consuming a fully materialized shared feature store

---

## Phase 1 Implemented In This Pass

The following ingestion-discipline improvements are now implemented:

### Ingestion-run metadata hardening

`IngestionRun` now stores:

- `source_kind`
  - `LIVE`
  - `SEEDED`
  - `HYBRID`
  - `UNKNOWN`
- `source_name`
- `source_timestamp`
- `freshness_state`
  - `FRESH`
  - `DELAYED`
  - `STALE`
  - `UNKNOWN`
- `fallback_used`
- `records_seen`
- `records_loaded`
- `records_rejected`

### Rainfall ingestion wiring

Rainfall ingestion now derives and stores:

- primary source identity
- source-kind classification
- source freshness state
- latest source timestamp when available
- fallback usage
- row-count metadata

### Operational boundaries

The backend now has:

- a dedicated Celery task:
  - `risk.tasks.run_rainfall_ingestion_task`
- a dedicated management command:
  - `python manage.py ingest_rainfall`
- a dedicated daily beat entry for rainfall ingestion ahead of the daily risk-model run

### Admin visibility

Admin now shows richer ingestion-run state including:

- source kind
- source name
- freshness state
- fallback usage

### Test coverage added

Rainfall ingestion tests now cover:

- live-source classification
- freshness-state persistence
- fallback-used persistence
- seeded-source classification on static fallback

---

## Current Truth After Phase 0 and 1

### What is now credible

- rainfall ingestion runs are auditable in a more operationally meaningful way
- seeded/static vs live rainfall inputs are now explicitly distinguished
- rainfall freshness is now visible on the ingestion-run record
- the backend now has a real ETL task boundary for rainfall ingestion

### What is still not yet fully credible

- the scheduled rainfall-ingestion task and the risk-model task are still only loosely coupled
- live rainfall source freshness is currently inferred from fetch time, not from a richer provider-native source timestamp contract
- non-rainfall ETL domains remain planned rather than implemented
- canonical cross-domain feature generation is still at an early mock/prototype stage

---

## Remaining Gaps To Close Next

The next ETL work should focus on:

1. making rainfall ingestion reusable by downstream scoring without duplicate inline fetch behavior
2. introducing canonical ingestion shapes beyond rainfall
3. extending ingestion-run discipline to surveillance, facility-readiness, and CHV data
4. tightening source-freshness semantics once richer provider timestamps are available
5. moving from mock feature generation toward explicit feature dataset versioning

---

## Verdict

Phase 0 and 1 are now materially stronger than before.

The backend does not yet have a full multi-source ETL platform, but it now has:

- a clearer audit of current ETL truth
- more disciplined rainfall ingestion provenance
- a real ingestion task boundary
- enough metadata to support the next ETL phases without pretending the pipeline is already mature
