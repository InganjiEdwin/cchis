# Backend Facility Burden Forecasting Phase 1 Status

## Phase

Phase 1: Target and Contract Definition

## Objective

Define the first real forecasting target and backend output contract.

## Contract Decisions

### Initial target window

- `7 days`

### Initial count target

- expected suspected cholera or diarrheal case count per facility over 7 days

### Initial readiness-state mapping

- `low`
  - routine projected pressure
- `watch`
  - elevated projected pressure needing closer monitoring
- `capacity_concern`
  - projected pressure high enough to justify explicit preparedness concern

### Initial backend output contract

The backend contract now defines:

- `facility_id`
- `generated_at`
- `horizon_days`
- `projected_case_burden`
- `projected_pressure_score`
- `projected_readiness_state`
- `surge_threshold_state`
- `driving_ward_ids`
- `forecast_factors`
- `model_version`
- `freshness_state`
- `forecast_mode`

## Honest Early-Phase Rule

The current phase-1 preview is:

- `proxy-backed`
- `pre-model`
- `not a promoted Negative Binomial forecast`

So the backend now distinguishes between:

- a truthful early contract
- and the later real forecasting model that will fill that contract

## What The Dashboard Is Allowed To Show Now

Allowed now:

- projected case burden
- projected pressure score
- projected readiness state
- surge-threshold state
- driving ward IDs
- forecast factors
- freshness state
- forecast mode

Not allowed to imply yet:

- that Negative Binomial is live
- that true confidence intervals exist
- that facility historical fit quality exists
- that a promoted facility forecasting model version exists

## Implemented Backend Surfaces

Phase 1 now exposes:

- `/api/v1/risk/facilities/{id}/forecast-preview/`

This preview:

- uses current truthful proxy inputs
- returns the phase-1 contract shape
- leaves `model_version` empty
- labels itself as:
  - `proxy_preforecast_from_current_readiness_contract`

## Verification

Verified with:

- focused API tests in `risk.tests`

Verified behaviors include:

- analysts can retrieve the forecast preview
- supervisors remain ward-scoped
- the preview stays explicit that Negative Binomial is not yet implemented

## Verdict

Phase 1 is complete.

The backend now has a truthful first forecasting contract and a concrete preview surface without pretending the forecasting baseline model already exists.
