# Backend Facility Burden Forecasting Implementation Audit

## Audit Standard

This audit treats the plan as if it is being reviewed for the first time.

The question is not whether status notes exist.

The question is whether each phase claim is actually reflected in backend code and testable behavior.

## Phase 0 Audit

### Planned

- truth audit of facility inputs
- distinction between direct operational truth and proxy-derived inputs
- explicit statement on historical burden availability

### Implemented

Yes.

Evidence exists in:

- `backend/risk/facility_forecasting.py`
- `GET /api/v1/risk/facility-forecasting/status/`
- `docs/BACKEND_FACILITY_BURDEN_FORECASTING_PHASE_0_STATUS.md`

### Verdict

- `implemented`

## Phase 1 Audit

### Planned

- define target window
- define count target
- define readiness-state mapping
- define forecast output fields
- define what dashboard is allowed to show

### Implemented

Yes.

Evidence exists in:

- `build_initial_facility_forecast_contract_definition`
- serializer-backed status surface
- preview contract fields

### Verdict

- `implemented`

## Phase 2 Audit

### Planned

- build training path
- build scoring path
- persist forecast lineage
- connect outputs to facility-readiness model shape
- keep scheduled scoring separate from retraining

### Initial audit finding

This phase was only partially implemented on a stricter external-audit reading.

What was present:

- training path
- scoring path
- persisted forecast runs and forecast rows
- facility-readiness integration
- scheduled scoring separated from retraining

What was not strong enough yet:

- forecast lineage was only represented by metadata dataset-ref strings
- unlike the main ML stack, those refs did not point to actual persisted `FeatureDataset` and `FeatureDatasetRow` records

### Gap closure

This audit closed that gap by adding:

- persisted training feature datasets for facility forecasting
- persisted inference feature datasets for facility forecasting
- real dataset refs in forecast-run metadata that resolve to stored dataset rows
- command-level verification that forecast lineage rows exist and are shaped correctly

Evidence now exists in:

- `backend/risk/facility_forecasting.py`
- `risk.tests.SeedAndModelCommandTestCase.test_run_facility_burden_forecast_command_persists_forecast_run_and_rows`

### Residual limitation

- training target is still proxy-derived

### Verdict

- `implemented with explicit limitations after audit gap closure`

## Scheduling Audit

### Planned

- shared execution order includes daily scoring before later retraining cadence
- recommended early cadence includes daily facility burden scoring

### Fresh-audit finding

On this stricter audit pass, the backend had:

- a dedicated facility burden forecast task

but it did not yet have:

- a Celery beat schedule for daily facility burden scoring

That meant the cadence claim was only partially implemented.

### Gap closure

This audit closed that gap by adding:

- `daily-facility-burden-forecast-run` to `CELERY_BEAT_SCHEDULE`

and a direct test asserting that the schedule is present.

### Verdict

- `implemented after audit gap closure`

## Phase 3 Audit

### Planned

- evaluate trustworthiness
- define promotion discipline
- block dashboard reliance until promotion

### Implemented

Yes.

Evidence exists in:

- `build_facility_forecast_promotion_summary`
- `GET /api/v1/risk/facility-forecasting/evaluation/`
- `python manage.py evaluate_facility_burden_forecast`
- `python manage.py promote_facility_burden_forecast`

### Verdict

- `implemented`

## Phase 4 Audit

### Planned

- connect promoted outputs to readiness summaries
- connect `driving_ward_ids` to map and action reasoning
- show facility pressure honestly
- distinguish proxy-based readiness from forecast-backed readiness

### Initial audit finding

This phase was only partially implemented at first.

What was present:

- facility intelligence distinguished proxy vs forecast-preview readiness

What was missing:

- dashboard/map summary integration for facility forecast linkage

### Gap closure

This audit closed that gap by adding:

- ward-map metadata block for facility forecasting
- ward-level `drives_facility_pressure_preview`
- ward-level facility forecast dashboard-truth-state field
- explicit promoted forecast selection for dashboard/map consumption
- a manual promotion command so promoted outputs can actually exist
- promoted-state truth in status and evaluation surfaces
- explicit override acknowledgement for blocked promotions
- promoted-forecast preference in facility intelligence over newer preview-only runs
- promoted-state truth in preview and honesty-rule surfaces
- promoted-forecast preference in dashboard/map summary over newer preview-only runs
- promoted-forecast preference in the facility forecast preview surface over newer preview-only runs
- promoted dashboard/map summaries now expose a truly empty `blocked_product_surfaces` list instead of a sentinel `"none"` value

Evidence now exists in:

- `backend/risk/map_data.py`
- `backend/risk/facility_forecasting.py`
- `backend/risk/management/commands/promote_facility_burden_forecast.py`
- `risk.tests.RiskPermissionsTestCase.test_migori_ward_map_exposes_facility_forecast_dashboard_summary_honestly`
- `risk.tests.RiskPermissionsTestCase.test_migori_ward_map_uses_promoted_facility_forecast_outputs_when_available`
- `risk.tests.RiskPermissionsTestCase.test_facility_forecasting_status_reflects_promoted_baseline_run`
- `risk.tests.RiskPermissionsTestCase.test_facility_forecasting_evaluation_reflects_promoted_run`
- `risk.tests.SeedAndModelCommandTestCase.test_promote_facility_burden_forecast_command_requires_explicit_override_for_blocked_run`
- `risk.tests.RiskPermissionsTestCase.test_facility_intelligence_prefers_promoted_facility_forecast_over_newer_preview_run`
- `risk.tests.RiskPermissionsTestCase.test_facility_forecast_preview_reflects_promoted_baseline_status`
- `risk.tests.RiskPermissionsTestCase.test_facility_forecast_preview_prefers_promoted_run_over_newer_preview_run`
- `risk.tests.RiskPermissionsTestCase.test_migori_ward_map_prefers_promoted_facility_forecast_over_newer_preview_run`

### Important honesty note

The backend now supports both:

- preview-only facility forecasts
- explicitly promoted facility forecasts

By default, forecasts remain preview-only until promoted manually.

So the implemented behavior is:

- preview forecasts remain blocked from dashboard truth
- promoted forecasts can now flow into dashboard/map-facing backend surfaces

That is the correct conservative implementation for the current state.

### Verdict

- `implemented with promotion block still enforced`

## Overall Verdict

The facility burden forecasting plan is now materially implemented through Phase 4.

The most meaningful gaps found in this audit were:

- missing dashboard/map-facing facility forecast linkage
- forecast lineage refs that were not backed by persisted feature datasets

Those gaps have now been closed in code and tested.

On later fresh-audit passes, two smaller but still real contract-hygiene gaps were also closed:

- promoted dashboard summaries no longer represent an unblocked state as `["none"]`
- they now return an actually empty blocked-surfaces list

Another audit pass also closed a promotion-consistency gap:

- the facility forecast preview surface no longer regresses from an older promoted run to a newer preview-only run
- preview selection now matches the governance-preference already used by facility intelligence and dashboard/map summaries

## Remaining Honest Limits

1. Real facility historical case counts are still not in the training target.
2. Out-of-time validation is still missing.
3. Promotion is still correctly blocked.
4. The dashboard should consume this track as preview-linked backend context, not promoted truth.
