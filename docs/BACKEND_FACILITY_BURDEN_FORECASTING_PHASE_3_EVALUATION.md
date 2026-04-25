# Backend Facility Burden Forecasting Phase 3 Evaluation

## Phase

Phase 3: Evaluation and Promotion

## Objective

Decide whether the facility burden forecasting baseline is trustworthy enough to drive promoted dashboard readiness outputs.

## Decision

The current facility burden forecasting baseline remains:

- `implemented`
- `persisted`
- `preview_only`
- `not_promoted`

The current early baseline is:

- `Negative Binomial Regression`

But it is not yet approved to drive:

- dashboard readiness warnings
- promoted facility pressure summaries
- action-layer facility pressure decisions

## Governance Decision

### Recommended state

- `not_promoted`

### Governance mode

- `preview_only`

### Why promotion did not occur

Promotion remains blocked because the current forecast path still depends on proxy-derived training targets and incomplete real-world evidence.

Current blockers are:

- `proxy_training_target_only`
- `real_facility_case_history_missing`
- `out_of_time_validation_missing`
- `threshold_usefulness_review_incomplete`
- `operational_promotion_review_pending`

## Evaluation Dimensions

### Count error discipline

The backend now records:

- `training_count_mae`
- `alpha`
- target mode

This is useful, but still limited because the target remains proxy-derived rather than sourced from real facility burden history.

### Threshold usefulness

The backend now checks:

- readiness-state distribution across forecast outputs
- surge-threshold coverage across forecasts

This is still treated as partial evidence, not promotion-grade evidence.

### Operational usefulness

The backend now checks:

- presence of `driving_ward_ids`
- presence of `forecast_factors`
- facility-level readiness-state outputs

This supports preview and ops review, but it is not enough to justify production promotion by itself.

### Stability across time windows

This remains unproven.

The backend evaluation summary explicitly records:

- `not_yet_established`

### Explainability

The baseline remains relatively explainable because it exposes:

- explicit forecast factors
- readiness-state mapping
- surge-threshold state

## Backend Surfaces Added

Phase 3 now provides:

- command:
  - `python manage.py evaluate_facility_burden_forecast`
- API:
  - `GET /api/v1/risk/facility-forecasting/evaluation/`
- enriched status API:
  - `GET /api/v1/risk/facility-forecasting/status/`

These surfaces expose the current evaluation summary and promotion decision directly.

## Allowed vs Blocked Product Use

Currently allowed:

- facility forecast preview
- ops/admin review
- forecast evaluation review

Currently blocked:

- dashboard readiness warning
- promoted facility summary
- action-panel facility pressure output

## Verification

Verified with:

- Python compile check for facility forecasting, serializers, views, urls, command, and tests
- Docker test run:
  - `risk.tests.AuthenticatedAPITestCase`
  - `risk.tests.SeedAndModelCommandTestCase`

Verified behaviors include:

- status API exposes current baseline state and promotion summary
- evaluation API exposes a conservative promotion decision
- evaluation command emits the same not-promoted decision
- successful forecast runs still leave the model in preview-only governance

## Honest Remaining Gaps

1. Real facility historical burden counts are still missing from the training target.
2. Out-of-time validation is not yet implemented.
3. Threshold usefulness is not yet reviewed against real operational outcomes.
4. Promotion review is still pending by design.

## Verdict

Phase 3 is complete.

The backend now has:

- an explicit evaluation surface
- explicit promotion blockers
- a conservative governance decision

The correct current decision is:

- keep the facility burden baseline available for preview and ops review
- do not promote it into dashboard truth yet
