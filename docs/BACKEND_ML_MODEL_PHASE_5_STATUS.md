# Backend ML Model Phase 5 Status

## Phase

Phase 5: Dashboard and Product Alignment

## Objective

Keep product language aligned with the true live model state.

## What Was Hardened

### 1. Dashboard-facing model truth is now explicit

The backend now exposes a compact model-alignment summary that records:

- current live baseline
- current benchmark model
- future candidate models
- dashboard policy for consuming only promoted outputs

This reduces the risk of dashboard consumers inferring model truth from whichever run happened most recently.

### 2. Promoted-output selection is now enforced in backend helpers

Dashboard-facing ward and facility surfaces now prefer:

- promoted live-baseline `ModelRun` outputs

over:

- benchmark-only outputs
- demo-only outputs
- candidate-only future model states

This closes the product-alignment gap where a newer benchmark run could otherwise outrank the true live baseline in read surfaces.

### 3. Map metadata now carries model-alignment context

The Migori ward map summary now includes model-alignment metadata so the dashboard layer can remain:

- model-family agnostic by default

while still reflecting:

- which model family is actually live
- which model family is benchmark-only
- which model families are future candidates only

## What Did Not Change

This phase did not:

- promote Random Forest
- expose XGBoost or LightGBM as live metadata defaults
- add dashboard branding for non-promoted model families
- change the Phase 3 promotion decision

That is intentional.

## Verification

Verified with:

- Python compile check for updated alignment modules, serializers, map data, and tests
- Docker test run:
  - `risk.tests.SeedAndModelCommandTestCase`

Verified behaviors include:

- map metadata exposes current model alignment
- dashboard-facing ward detail prefers promoted live output over newer benchmark-only output
- benchmark and candidate models remain outside operational truth surfaces

## Honest Remaining Gaps

1. Some broader product surfaces outside the current ward/map APIs may still need the same alignment treatment later.
2. The dashboard frontend itself still needs to consume this metadata intentionally in its own implementation phases.
3. Real-data and later promotion decisions still determine how meaningful future model-family changes will be.

## Verdict

Phase 5 is complete.

The backend now does a better job of ensuring that product-facing prediction metadata reflects promoted operational truth rather than whichever experimental or benchmark record happened to be created last.
