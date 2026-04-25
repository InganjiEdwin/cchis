# Backend Facility Burden Forecasting Phase 0 Status

## Phase

Phase 0: Forecasting Truth Audit

## Objective

Document what real facility-readiness and case-burden data exists today.

## Current Truth

What exists in the backend today:

- facility master records
- ward-to-facility linkage
- promoted ward-risk outputs
- ward alert history
- facility `updated_at` freshness marker

What exists mainly as derived proxy:

- projected facility cases
- surge pressure
- ORS pressure
- staffing pressure

These are currently derived from:

- facility identity
- promoted ward-risk state
- alert presence
- heuristic pressure mappings

What does not yet exist as real facility-burden forecasting truth:

- facility-level historical suspected cholera case counts
- catchment-level observed burden history
- real staffing rosters
- real ORS stock ledgers
- bed or observation occupancy history
- referral overflow history

## Honest Assessment

The backend already has:

- a facility-readiness view

but it does not yet have:

- a true facility-burden forecasting model

The current readiness surface is therefore:

- operationally useful as a proxy
- not yet a promoted burden forecast

## Implemented Backend Truth Surface

Phase 0 now exposes a backend truth-audit endpoint:

- `/api/v1/risk/facility-forecasting/status/`

This endpoint records:

- current forecasting state
- planned baseline model
- what is direct operational truth
- what is proxy-derived
- what is not yet available

## Verification

Verified with:

- focused API tests in `risk.tests`

Verified behaviors include:

- analysts can view the facility-forecasting truth surface
- the response clearly states that Negative Binomial is planned, not live

## Verdict

Phase 0 is complete.

The backend now has an explicit audited statement of what facility forecasting truth exists and what still remains proxy-only.
