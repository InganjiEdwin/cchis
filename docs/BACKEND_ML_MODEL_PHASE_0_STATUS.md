# Backend ML Model Phase 0 Status

## Phase

Phase 0: Baseline Freeze and Truth Audit

## Objective

Freeze the current live baseline truth before additional ML promotion work.

## Confirmed Live Scheduled Baseline

The current live scheduled baseline is:

- `Logistic Regression`

This is confirmed by:

- [backend/core/settings.py](/Users/edwininganji/VSCodeProjects/cchis/backend/core/settings.py:300)
  - scheduled `daily-risk-model-run`
  - no algorithm override supplied
  - default `model_version="lr-v1"`
- [backend/risk/tasks.py](/Users/edwininganji/VSCodeProjects/cchis/backend/risk/tasks.py:89)
  - task default `algorithm="logistic_regression"`
- [backend/risk/ml/pipeline.py](/Users/edwininganji/VSCodeProjects/cchis/backend/risk/ml/pipeline.py:170)
  - pipeline default uses logistic regression unless explicitly overridden

## Confirmed Benchmark Reality

`Random Forest` is now implemented as a benchmark-capable backend path, but it is **not** the promoted scheduled baseline.

This is confirmed by:

- [backend/risk/ml/model.py](/Users/edwininganji/VSCodeProjects/cchis/backend/risk/ml/model.py:46)
  - Random Forest training path exists
- [backend/risk/management/commands/run_risk_model.py](/Users/edwininganji/VSCodeProjects/cchis/backend/risk/management/commands/run_risk_model.py:12)
  - manual algorithm selection exists
- [backend/risk/ml/pipeline.py](/Users/edwininganji/VSCodeProjects/cchis/backend/risk/ml/pipeline.py:187)
  - dual-model mode persists benchmark lineage

## Current Lineage Sufficiency

Current stored lineage is strong enough for early audit and dashboard honesty.

Implemented lineage fields include:

- `ModelRun.algorithm_name`
- `ModelRun.model_version`
- `ModelRun.feature_schema_version`
- `ModelRun.training_dataset_ref`
- `ModelRun.inference_dataset_ref`
- `ModelRun.training_feature_dataset`
- `ModelRun.inference_feature_dataset`
- `ModelRun.rainfall_ingestion_run`
- `ModelRun.metadata`

This is sufficient for:

- distinguishing live baseline vs benchmark path
- tracing inference to ETL freshness and datasets
- exposing operational trust-policy decisions

## Mock / Synthetic Behavior Still Present

The backend still contains important synthetic or proxy behavior that must remain explicit.

### Training data

- training rows are still seeded baseline rows, not real historical surveillance datasets
- source:
  - [backend/risk/ml/data.py](/Users/edwininganji/VSCodeProjects/cchis/backend/risk/ml/data.py:36)

### Some inference features

- flood indicator remains partly mock-derived
- historical case count remains proxy-derived from current score and rainfall
- population remains a simple proxy
- source:
  - [backend/risk/ml/data.py](/Users/edwininganji/VSCodeProjects/cchis/backend/risk/ml/data.py:103)

### ETL reality

- rainfall ingestion is real enough for the early backbone, but fallback/static paths still exist and remain important in dev and degraded trust conditions

## Current Baseline Naming Discipline

The baseline is named explicitly enough to audit today:

- algorithm name:
  - `logistic-regression-baseline`
- model version default:
  - `lr-v1`

This is materially better than a vague `ml-model` label and should remain explicit.

## Honest Phase-0 Verdict

Phase 0 is complete with this truth:

- the live scheduled model is still `Logistic Regression`
- `Random Forest` exists as a benchmark-capable backend path
- lineage is sufficient for early governance
- synthetic feature and training behavior still exists and must not be hidden

## Immediate Next Phase-1 Implications

Phase 1 should now focus on:

- keeping baseline naming explicit in admin and operational surfaces
- hardening the distinction between:
  - live scheduled scoring
  - benchmark scoring
  - seeded demo behavior
- documenting retraining discipline and promotion rules before any live-model switch
