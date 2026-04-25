# Backend ML Model Phase 4 Status

## Phase

Phase 4: XGBoost / LightGBM Readiness

## Objective

Prepare for later boosting-model evolution without prematurely committing the live system to it.

## What Was Added

### 1. Backend model catalog now distinguishes candidate-only boosting models

The backend now explicitly recognizes:

- `xgboost`
- `lightgbm`

as:

- `candidate_only`
- `not runnable`
- `not promoted`

This keeps later boosting work intentional instead of leaving it implied or undocumented.

### 2. A readiness artifact now exists in backend code

The readiness summary records:

- current live baseline
- current benchmark model
- candidate boosting models
- feature-discipline expectations
- resource and training expectations
- stricter promotion gates
- explainability and monitoring requirements

This turns Phase 4 into a backend-owned readiness surface rather than a vague future note.

### 3. A management command now exposes the readiness summary

The backend now provides:

- `describe_boosting_readiness`

This command emits the current readiness contract without making XGBoost or LightGBM runnable in the main scoring command.

## Readiness Rules Now Made Explicit

The backend now states that XGBoost and LightGBM must not be treated as live-ready until:

- feature discipline remains explicit and auditable
- training and inference parity is preserved
- time-aware evaluation is completed
- calibration review is completed
- lead-time usefulness is shown
- temporal robustness is shown
- explainability strategy is defined
- dashboard language review is completed
- manual promotion is explicitly approved

## What Did Not Change

This phase did not:

- add XGBoost or LightGBM as runnable choices in `run_risk_model`
- add boosting-model scheduling to Celery
- promote boosting models to live alert generation
- change dashboard-facing live model semantics

That is intentional.

## Verification

Verified with:

- Python compile check for readiness modules and tests
- Docker test run:
  - `risk.tests.SeedAndModelCommandTestCase`

Verified behaviors include:

- readiness command emits candidate-only state
- XGBoost and LightGBM remain non-runnable in the readiness summary
- stricter promotion gates are recorded explicitly

## Honest Remaining Gaps

1. No boosted-model training implementation exists yet.
2. No boosted-model benchmark command exists yet.
3. No explainability implementation such as SHAP-style attribution is present yet.
4. No boosted-model calibration or drift monitoring is implemented yet.
5. Real-data breadth is still an upstream limiter on later boosting-model credibility.

## Verdict

Phase 4 is complete.

The backend is now ready to discuss XGBoost and LightGBM honestly as future candidates, while keeping them clearly outside the current live and benchmark execution paths.
