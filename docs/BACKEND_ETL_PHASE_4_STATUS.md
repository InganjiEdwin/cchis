# Backend ETL Phase 4 Status

## Phase

Phase 4: Dual-Model Inference Readiness

## Status

Completed for the current early-phase backend prediction path.

## What Was Implemented

- a shared feature-dataset build remains the single source of inference inputs
- the same persisted training and inference dataset slice can now feed:
  - `Logistic Regression`
  - `Random Forest`
- dual-model run mode now persists separate `ModelRun` records for each algorithm
- both model runs retain shared dataset lineage through:
  - `training_dataset_ref`
  - `inference_dataset_ref`
  - `training_feature_dataset`
  - `inference_feature_dataset`
- explicit alert-governance metadata is now attached to each model run:
  - algorithm
  - run role
  - benchmark group reference
  - alert eligibility
  - promotion state

## Operational Meaning

The backend can now:

- keep `Logistic Regression` as the live promoted baseline
- run `Random Forest` against the same disciplined feature slice
- persist benchmark outputs without pretending they are the alert-driving truth
- keep alert lineage tied to the explicit promoted model output

## What This Does Not Yet Mean

This phase does **not** mean:

- `Random Forest` is already promoted for live alert generation
- model comparison has been fully audited for production promotion
- calibration methods or later temporal models are now active

Those remain part of the ML roadmap and promotion-governance work.

## Verification Completed

- Python compile check for updated ETL and prediction modules
- focused Docker test run:
  - `risk.tests.SeedAndModelCommandTestCase`
- explicit assertion that dual-model mode:
  - creates two model runs
  - creates two sets of risk scores
  - shares the same dataset lineage
  - keeps the benchmark path non-alert-eligible by default

## Honest Remaining Gaps

- promotion governance is still metadata-driven rather than backed by a dedicated promotion model
- scheduled execution still defaults to the logistic baseline path
- external real-data coverage across all proposed source domains is still incomplete

## Conclusion

Phase 4 is complete for current ETL and prediction-readiness scope.

The ETL backbone now supports:

- canonical ingestion
- persisted feature datasets
- shared dual-model inference slices
- explicit lineage between datasets, model runs, and alert-eligible outputs
