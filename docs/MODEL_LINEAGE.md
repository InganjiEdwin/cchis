# CCHIS Model Lineage

## Purpose

This document defines the v1 lineage rules for model execution so forecasts can be traced back to a concrete run instead of only carrying a free-text model version.

## Current Model Run Tracking

CCHIS now persists model execution metadata in `ModelRun`.

Each run captures:

- algorithm name
- model version
- run status
- execution month
- feature schema version
- feature keys used by the model
- training dataset reference
- inference dataset reference
- training row count
- inference row count
- evaluation metrics
- freeform metadata
- linked rainfall ingestion run when available
- start and completion timestamps

## Risk Score Lineage Rule

Model-generated `RiskScore` rows must link to a `ModelRun`.

Policy:

- `RiskScore.source == MODEL` should always have `model_run` populated
- `model_version` remains useful for quick filtering, but it is no longer treated as sufficient lineage by itself
- future work should prefer following `RiskScore.model_run` rather than inferring lineage from text fields

## Evaluation Metadata Direction

Current v1 baseline stores lightweight evaluation metadata on `ModelRun.evaluation_metrics`.

Current scope:

- training accuracy for the baseline model
- room for future metrics in JSON form

Direction:

- later versions may promote evaluation metrics into richer structured records if model comparison becomes more formal
- v1 does not need a full experiment-tracking system yet, but evaluation cannot remain invisible

## Feature Schema Direction

Current v1 baseline stores feature names on `ModelRun.feature_keys` and a schema marker on `ModelRun.feature_schema_version`.

Purpose:

- make the input feature contract visible for a specific run
- support future comparison when feature sets evolve

Direction:

- later versions may introduce an explicit feature schema version or feature snapshot entity
- until then, `feature_keys` plus `feature_schema_version` is the minimum acceptable provenance layer

## Dataset Reference Direction

Current v1 baseline stores lightweight training and inference dataset references on `ModelRun`.

Direction:

- later versions may introduce richer dataset snapshot entities or external artifact references
- until then, training and inference datasets must still have explicit reference strings rather than remaining invisible

## Practical v1 Rules

1. No model-generated forecast should exist without a linked `ModelRun`.
2. New model pipelines must record the feature set they used.
3. New model pipelines must persist at least minimal evaluation metadata.
4. New model pipelines must persist feature schema and dataset references.
