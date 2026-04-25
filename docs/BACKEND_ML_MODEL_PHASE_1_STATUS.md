# Backend ML Model Phase 1 Status

## Phase

Phase 1: Logistic Regression Baseline Hardening

## Objective

Make the current live logistic-regression baseline explicit, stable, and auditable before any promotion decision.

## What Was Hardened

### 1. Feature-set provenance remains explicit

The live baseline still records:

- `feature_schema_version`
- `feature_keys`
- `training_dataset_ref`
- `inference_dataset_ref`
- linked `FeatureDataset` objects
- linked `IngestionRun`

This keeps feature provenance auditable for the current baseline path.

### 2. Model version naming remains explicit

The baseline keeps explicit naming:

- algorithm:
  - `logistic-regression-baseline`
- live default version:
  - `lr-v1`

The backend still avoids vague internal naming such as just `ML model`.

### 3. Prediction outputs now persist clearer run provenance

`ModelRun.metadata` now distinguishes:

- `execution_context`
  - `scheduled_task`
  - `manual_command`
  - `manual_task`
  - `seeded_demo`
- `run_purpose`
  - `live_scoring`
  - `benchmark_scoring`
  - `demo_seed`
- `promotion_target`
  - `live_baseline`
  - `benchmark_only`
  - `demo_only`
- `retraining_policy`
  - `manual_promotion_only`

This makes scheduled, manual, benchmark, and seeded runs visibly different in stored lineage.

### 4. Internal admin and serializer surfaces are clearer

Admin-facing `ModelRun` views now expose:

- run purpose
- execution context
- promotion target

Serializer output also exposes:

- execution context
- run purpose
- promotion target
- retraining policy
- alert eligibility

### 5. Seeded demo runs are now explicitly marked as demo-only

The seeded demo path now records:

- `execution_context = seeded_demo`
- `run_purpose = demo_seed`
- `promotion_target = demo_only`
- `alert_eligible = false`

This reduces the chance of demo lineage being mistaken for live baseline lineage.

## Early-Phase Retraining Decision

Retraining remains:

- `manual`
- `not auto-scheduled`
- `not auto-promoted`

Early-phase rule:

- `run_risk_model_task` is the live scoring boundary
- retraining and promotion remain manual governance actions until a later ML phase

This is intentional.
It prevents the backend from implying that retraining cadence is already production-governed when it is not.

## Verification

Verified with:

- Python compile check for updated ML/admin/serializer/seed paths
- Docker test run:
  - `risk.tests.SeedAndModelCommandTestCase`

Verified behaviors include:

- manual logistic runs carry explicit lineage metadata
- dual-model runs distinguish live scoring vs benchmark scoring
- seeded demo runs remain clearly non-promoted

## Honest Remaining Gaps

1. The live baseline still uses seeded training data and proxy-derived feature components.
2. Retraining is governed by policy and naming discipline, but not yet by a fully implemented retraining workflow.
3. Comparative evaluation and promotion logic still belong to later ML phases.

## Verdict

Phase 1 is complete for early-phase baseline hardening.

The backend is now better at saying:

- what the live baseline is
- where a run came from
- what the run was for
- whether it is eligible to drive promoted alert behavior
