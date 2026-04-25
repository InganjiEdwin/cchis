# Backend Facility Burden Forecasting Phase 2 Status

## Verdict

`complete with explicit limitations`

Phase 2 is now implemented as a real backend baseline path.

The backend now supports:

- a persisted `Negative Binomial` facility-burden forecast run model
- persisted per-facility forecast outputs
- a manual command entry point
- a queued Celery task entry point
- forecast lineage for both successful and failed runs
- preview-surface preference for model-backed facility forecasts when available

It does not yet mean the forecast is promoted for dashboard truth or live readiness warnings.

## What Was Implemented

### Forecast persistence

Added backend models for:

- `FacilityForecastRun`
- `FacilityForecast`

These persist:

- algorithm name
- model version
- status
- feature schema
- evaluation metadata
- execution metadata
- per-facility projected case burden
- projected pressure score
- projected readiness state

### Negative Binomial baseline path

Implemented a first backend baseline in:

- `backend/risk/facility_forecasting.py`

This now:

- builds facility-level training rows from current facility intelligence and ward-risk context
- expands those rows into a deterministic training slice
- fits a `Negative Binomial` count model
- scores active facilities
- persists forecast outputs

### Operational entry points

Added:

- management command:
  - `python manage.py run_facility_burden_forecast`
- Celery task:
  - `risk.tasks.run_facility_burden_forecast_task`

This keeps scoring entry points explicit and separate from any future retraining workflow.

### Product and ops behavior

- the facility forecast preview endpoint now prefers persisted model-backed forecasts over the older proxy-only preview when a successful forecast run exists
- Django admin now exposes facility forecast runs and forecast rows for ops inspection

## Verification

The following checks passed:

- `python3 -m py_compile backend/risk/facility_forecasting.py backend/risk/tasks.py backend/risk/admin.py backend/risk/management/commands/run_facility_burden_forecast.py backend/risk/tests.py backend/risk/migrations/0015_facilityforecast_facilityforecastrun_and_more.py`
- `docker compose exec backend python manage.py migrate risk`
- `docker compose exec backend python manage.py test risk.tests.AuthenticatedAPITestCase risk.tests.SeedAndModelCommandTestCase --keepdb`
- `docker compose exec backend python manage.py showmigrations risk`

## Explicit Limitations

This phase is intentionally still limited in important ways:

- training targets are still proxy-derived from current readiness and ward-risk context
- real facility historical burden counts are not yet available in the training path
- the model is implemented but not promoted
- no daily beat schedule was added yet for facility forecasting
- no retraining workflow was added yet
- no formal evaluation or promotion decision has been completed yet

## Honest Interpretation

Phase 2 is now real backend implementation, not just planning.

But it is still a `baseline preview track`, not a promoted operational forecasting truth layer.
