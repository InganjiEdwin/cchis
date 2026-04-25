# Backend ML Model Phase 3 Evaluation

## Phase

Phase 3: Comparative Evaluation and Promotion Decision

## Objective

Decide whether the live baseline should remain Logistic Regression or be replaced by Random Forest.

## Decision

The current live baseline remains:

- `Logistic Regression`

Random Forest remains:

- `shadow benchmark mode`

## Governance Decision

### Recommended primary model

- `logistic_regression`

### Governance mode

- `shadow_benchmark_mode`

### Why promotion did not occur

Random Forest is now a real benchmarkable backend path, but promotion is still blocked by missing evidence in the dimensions that matter most operationally:

- calibration quality is not yet fully evaluated
- lead-time usefulness for `7 to 14 day` warning is not yet fully evaluated
- temporal robustness is not yet fully evaluated
- operational promotion review is still pending

This means the current backend can compare models, but it cannot yet honestly claim that Random Forest should replace the live logistic baseline.

## Alert Governance

### Live alert-producing task

- `risk.tasks.run_risk_model_task`

This remains the live alert-driving path for early-phase ward-risk predictions.

### Benchmark-only tasks

- `risk.tasks.run_random_forest_benchmark_task`

This task must not affect live alert generation unless a later promotion phase explicitly changes that rule.

### Retraining task

- `none`

Retraining remains:

- manual only
- not scheduled
- not auto-promoted

## Comparability Rule

Promotion discussion is only meaningful if the compared Logistic Regression and Random Forest runs share:

- compatible training dataset lineage
- compatible inference dataset lineage
- compatible feature schema version

If those inputs do not match, the comparison must be treated as:

- `comparison_input_mismatch`

and promotion remains blocked.

## Dashboard Impact

Current dashboard wording impact:

- `none`

Because Logistic Regression remains the live promoted model, the dashboard does not need to change wording or imply a model-family switch.

If a later phase promotes Random Forest, the dashboard plan must explicitly record:

- whether model wording changes publicly
- whether alert confidence/explanation language changes
- whether disagreement review behavior is introduced

## Verification

Verified with:

- Python compile check for the comparison module
- Docker test run:
  - `risk.tests.SeedAndModelCommandTestCase`

Verified behaviors include:

- comparison command emits a conservative promotion summary
- benchmark-only Random Forest runs remain non-promoted
- mismatched feature or dataset lineage is treated as a promotion blocker

## Honest Remaining Gaps

1. Comparative evidence is still heavily early-phase and uses the current seeded/proxy data backbone.
2. Calibration review is not yet complete.
3. Lead-time validation against real outbreak timing is not yet complete.
4. Temporal robustness over longer historical windows is not yet complete.
5. Promotion governance is explicit now, but still conservative by design.

## Verdict

Phase 3 is complete.

The backend now has:

- a written comparison path
- an explicit promotion decision artifact
- a documented live-versus-benchmark governance boundary

The correct current decision is:

- keep Logistic Regression live
- keep Random Forest in shadow benchmark mode
- require more evidence before changing production alert behavior
