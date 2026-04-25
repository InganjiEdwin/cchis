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

### Implemented

Mostly yes, with honest early-phase limitations.

Evidence exists in:

- `FacilityForecastRun`
- `FacilityForecast`
- `run_facility_burden_forecast_pipeline`
- `run_facility_burden_forecast` management command
- `run_facility_burden_forecast_task`
- persisted failed-run handling

### Residual limitation

- training target is still proxy-derived

### Verdict

- `implemented with explicit limitations`

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

Evidence now exists in:

- `backend/risk/map_data.py`
- `risk.tests.RiskPermissionsTestCase.test_migori_ward_map_exposes_facility_forecast_dashboard_summary_honestly`

### Important honesty note

The plan language says `promoted outputs`, but the current backend still correctly blocks promotion.

So the implemented behavior is:

- integrated into dashboard-facing backend surfaces
- still clearly blocked from promoted truth

That is the correct conservative interpretation for the current state.

### Verdict

- `implemented with promotion block still enforced`

## Overall Verdict

The facility burden forecasting plan is now materially implemented through Phase 4.

The most meaningful gap found in this audit was:

- missing dashboard/map-facing facility forecast linkage

That gap has now been closed in code and tested.

## Remaining Honest Limits

1. Real facility historical case counts are still not in the training target.
2. Out-of-time validation is still missing.
3. Promotion is still correctly blocked.
4. The dashboard should consume this track as preview-linked backend context, not promoted truth.
