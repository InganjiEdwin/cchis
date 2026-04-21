# CCHIS Feature and Dataset Provenance

## Purpose

This document defines the v1 policy for feature provenance and dataset references so model inputs are explainable and future training or inference datasets are not conceptually invisible.

## Current Feature Provenance Direction

`ModelRun` now carries:

- `feature_schema_version`
- `feature_keys`

These fields are the minimum v1 contract for explaining what feature shape a forecast run used.

### Policy

- every model pipeline must declare the feature keys it used
- every model pipeline must declare a feature schema version string
- changing the meaning, ordering, or semantics of the feature set should result in a new `feature_schema_version`

### Why this is enough for v1

The backend does not need a full feature store yet.
It does need enough lineage to explain what inputs a forecast depended on and to compare later model runs without guessing.

## Current Dataset Versioning Direction

`ModelRun` now carries:

- `training_dataset_ref`
- `inference_dataset_ref`

These are dataset reference strings, not full snapshot tables.

### Policy

- training and inference data should be referenced explicitly on a model run
- dataset references may point to a named snapshot, exported file, generated dataset artifact, or controlled mock dataset version
- the reference string must change when the underlying dataset contract materially changes

### v1 Reference Style

Current examples:

- `mock-training-dataset:v1`
- `mock-inference-dataset:month-4`
- `seed-training-dataset:v1`

This is intentionally lightweight but still far better than having no dataset identity at all.

## Practical v1 Rules

1. No new model pipeline should omit a feature schema version.
2. No new model pipeline should omit training and inference dataset references.
3. If feature semantics change, increment the feature schema version instead of silently reusing the old label.
