# Backend Facility Burden Forecasting Phase 4 Status

## Verdict

`complete with explicit limitations`

Phase 4 is implemented as an honest backend integration layer.

The facility burden forecasting track now reaches product-facing facility intelligence surfaces without pretending that the forecast is already promoted dashboard truth.

## What Was Integrated

### Facility intelligence now distinguishes readiness source

Facility intelligence now explicitly separates:

- proxy-based readiness
- forecast-preview-backed readiness

The backend surface now exposes:

- readiness source
- dashboard truth state
- forecast governance mode
- model version when a forecast preview exists
- `driving_ward_ids`
- action reasoning for facility pressure interpretation

### Forecast-backed readiness summaries

When a successful facility burden forecast exists for a facility:

- facility intelligence uses the forecast-backed burden and readiness view
- the response is clearly marked as:
  - `forecast_preview`
  - `preview_only`
  - `blocked_until_promotion`

### Proxy fallback remains explicit

When no successful facility forecast exists:

- facility intelligence falls back to the older proxy readiness contract
- the response remains clearly marked as:
  - `proxy`
  - `proxy_only`

### Timeline integration

Facility intelligence timeline entries now show when a facility burden forecast preview exists, including:

- forecast model version
- projected readiness state
- projected pressure score
- driving ward linkage

## Files Updated

- `backend/risk/services.py`
- `backend/risk/serializers.py`
- `backend/risk/tests.py`

## Verification

Verified with:

- `python3 -m py_compile backend/risk/services.py backend/risk/serializers.py backend/risk/tests.py`
- Docker API tests:
  - `risk.tests.RiskPermissionsTestCase.test_analyst_can_view_facility_intelligence`
  - `risk.tests.RiskPermissionsTestCase.test_facility_intelligence_distinguishes_forecast_preview_from_proxy_readiness`
  - `risk.tests.RiskPermissionsTestCase.test_analyst_can_view_facility_forecasting_status`
  - `risk.tests.RiskPermissionsTestCase.test_facility_forecasting_status_reflects_successful_baseline_run`
  - `risk.tests.RiskPermissionsTestCase.test_analyst_can_view_facility_forecasting_evaluation`
- Docker command tests:
  - `risk.tests.SeedAndModelCommandTestCase.test_run_facility_burden_forecast_command_persists_forecast_run_and_rows`
  - `risk.tests.SeedAndModelCommandTestCase.test_evaluate_facility_burden_forecast_command_reports_not_promoted_decision`

## Honest Limitations

1. Facility intelligence now reflects forecast previews, but those previews are still not promoted outputs.
2. No dashboard-wide promoted readiness warning contract was enabled in this phase.
3. The integration is intentionally conservative and does not treat forecast-backed readiness as live truth.
4. This phase improves backend product alignment, but final dashboard behavior still depends on the dashboard decision-layer track.

## Honest Interpretation

Phase 4 is complete in the right cautious sense:

- the facility forecasting track is now connected to product-facing intelligence
- the backend distinguishes proxy from forecast-backed readiness
- the backend blocks premature truth claims

That is the correct integration posture at this stage. 
