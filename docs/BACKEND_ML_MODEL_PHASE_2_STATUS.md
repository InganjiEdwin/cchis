# Backend ML Model Phase 2 Status

## Phase

Phase 2: Random Forest Benchmark Implementation

## Objective

Add Random Forest as an explicit benchmark path without silently replacing the live logistic baseline.

## What Was Hardened

### 1. Random Forest remains benchmark-only by default

A Random Forest-only run no longer inherits live alert-governing status automatically.

Current behavior:

- explicit Random Forest benchmark runs default to:
  - `run_purpose = benchmark_scoring`
  - `promotion_target = benchmark_only`
  - `alert_eligible = false`

This closes the governance bug where a benchmark-only run could otherwise be mistaken for a promoted live path.

### 2. Dedicated benchmark execution path now exists

The backend now exposes a dedicated benchmark command and task:

- command:
  - [run_random_forest_benchmark.py](/Users/edwininganji/VSCodeProjects/cchis/backend/risk/management/commands/run_random_forest_benchmark.py)
- task:
  - `risk.tasks.run_random_forest_benchmark_task`

This means Random Forest can be:

- run manually
- queued asynchronously

without changing the scheduled live logistic scoring task.

### 3. Version naming discipline is reinforced

The benchmark command and the generic scoring command now warn when:

- logistic versions do not start with `lr-`
- Random Forest versions do not start with `rf-`

This keeps model lineage more readable and auditable.

### 4. Random Forest evaluation metadata is richer

Random Forest evaluation now persists:

- `algorithm = random_forest`
- `training_accuracy`
- `training_row_count`
- `feature_importances`

This gives the benchmark path more useful comparison metadata than a bare score alone.

## Comparability Outcome

The backend can now run comparable prediction jobs for:

- `Logistic Regression`
- `Random Forest`

while keeping:

- shared feature inputs
- shared training and inference dataset lineage
- benchmark-only governance for Random Forest unless a later promotion phase changes that

## Verification

Verified with:

- Python compile check for updated benchmark modules
- Docker test run:
  - `risk.tests.SeedAndModelCommandTestCase`

Verified behaviors include:

- explicit Random Forest benchmark command creates benchmark-only outputs
- explicit async benchmark command queues the dedicated benchmark task
- dual-model runs keep the Random Forest path benchmark-only
- Random Forest evaluation metadata includes feature importances

## Honest Remaining Gaps

1. Random Forest exists as a benchmark path, but no comparative promotion decision has been made yet.
2. Evaluation is still using the current seeded/proxy early-phase data backbone.
3. Comparative evaluation, calibration, and promotion rules remain Phase 3 work.

## Verdict

Phase 2 is complete.

The backend now supports Random Forest as a real, explicit, benchmarkable model path without silently replacing the live logistic baseline.
