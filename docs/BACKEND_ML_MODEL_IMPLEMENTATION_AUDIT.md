# Backend ML Model Implementation Audit

## Purpose

Audit the claims in [BACKEND_ML_MODEL_ROADMAP_PLAN.md](/Users/edwininganji/VSCodeProjects/cchis/docs/BACKEND_ML_MODEL_ROADMAP_PLAN.md) against what is actually implemented in backend code.

This audit is intentionally skeptical.
A claim is only treated as true if there is:

- matching backend code
- matching test coverage
- or a clearly committed phase artifact that does not overstate implementation

## Audit Result

### 1. Claim: Logistic Regression is the live scheduled baseline

Verdict:

- `confirmed`

Evidence:

- [backend/core/settings.py](/Users/edwininganji/VSCodeProjects/cchis/backend/core/settings.py)
  - scheduled scoring still uses `run_risk_model_task` with `model_version="lr-v1"`
- [backend/risk/ml/pipeline.py](/Users/edwininganji/VSCodeProjects/cchis/backend/risk/ml/pipeline.py)
  - default live path remains logistic regression

### 2. Claim: Random Forest exists as a benchmark-capable backend path

Verdict:

- `confirmed`

Evidence:

- [backend/risk/ml/model.py](/Users/edwininganji/VSCodeProjects/cchis/backend/risk/ml/model.py)
- [backend/risk/management/commands/run_random_forest_benchmark.py](/Users/edwininganji/VSCodeProjects/cchis/backend/risk/management/commands/run_random_forest_benchmark.py)
- [backend/risk/tasks.py](/Users/edwininganji/VSCodeProjects/cchis/backend/risk/tasks.py)
- [backend/risk/tests.py](/Users/edwininganji/VSCodeProjects/cchis/backend/risk/tests.py)

### 3. Claim: Random Forest is not promoted as the live scheduled model

Verdict:

- `confirmed`

Evidence:

- scheduled settings still point to the logistic live path
- Random Forest benchmark runs persist:
  - `promotion_target = benchmark_only`
  - `alert_eligible = false`

### 4. Claim: Product surfaces prefer promoted truth over newer benchmark/demo recency

Verdict:

- `confirmed, but scoped`

What is truly implemented:

- ward detail
- latest ward risk
- ward intelligence
- facility intelligence
- Migori map summary

These now prefer promoted live outputs through:

- [backend/risk/ml/alignment.py](/Users/edwininganji/VSCodeProjects/cchis/backend/risk/ml/alignment.py)
- [backend/risk/services.py](/Users/edwininganji/VSCodeProjects/cchis/backend/risk/services.py)
- [backend/risk/serializers.py](/Users/edwininganji/VSCodeProjects/cchis/backend/risk/serializers.py)
- [backend/risk/map_data.py](/Users/edwininganji/VSCodeProjects/cchis/backend/risk/map_data.py)

Important limit:

- broader audit/admin-style surfaces such as raw model-run and risk-score lists still expose non-promoted records
- that is acceptable, but the roadmap must not imply that every read surface is promotion-filtered

Additional verification after the stricter repeat audit:

- dedicated test coverage now exists for:
  - latest ward risk
  - ward intelligence
  - facility intelligence
  - model-alignment endpoint when a benchmark model is present

This closes the earlier proof gap where some of these claims were true by shared helper behavior but not all were directly asserted in tests.

### 5. Claim: a dedicated backend truth surface exists for product consumers

Verdict:

- `confirmed`

Evidence:

- [backend/risk/views.py](/Users/edwininganji/VSCodeProjects/cchis/backend/risk/views.py)
  - `ModelAlignmentAPIView`
- [backend/risk/urls.py](/Users/edwininganji/VSCodeProjects/cchis/backend/risk/urls.py)
  - `/api/v1/risk/model-alignment/`
- [backend/risk/tests.py](/Users/edwininganji/VSCodeProjects/cchis/backend/risk/tests.py)
  - endpoint coverage exists

### 6. Claim: promotion discipline is stronger than model prestige

Verdict:

- `partially confirmed`

What is implemented:

- comparison summary remains conservative
- benchmark promotion is blocked by missing evidence
- live-versus-benchmark roles are explicit

What is not implemented yet:

- real out-of-time validation metrics
- completed calibration metrics
- real lead-time validation against outbreak timing
- rollback workflow if a future promotion occurs

So the principle is implemented in governance posture, but not yet supported by the full evidence stack the roadmap ultimately wants.

### 7. Claim: XGBoost / LightGBM are only later candidates

Verdict:

- `confirmed with precision`

What is implemented:

- backend candidate metadata and readiness summary
- non-runnable candidate state
- readiness command

What is not implemented:

- actual boosted-model training path
- actual benchmark command
- actual promotion path

So the truthful description is:

- they exist as readiness candidates, not as real benchmark models

### 8. Claim: training and retraining are orchestrated explicitly

Verdict:

- `partially confirmed`

What is implemented:

- scheduled live scoring
- explicit benchmark tasks
- manual commands
- explicit metadata indicating manual-promotion-only retraining policy

What is not implemented:

- scheduled retraining task
- data-volume-based retraining trigger
- weekly or biweekly retraining workflow

So the roadmap must stay careful not to imply that retraining is already operationally implemented.

## Gaps Found And Closed In This Audit

1. The roadmap still spoke as if Random Forest was merely the next model to add.

Closed by:

- updating the roadmap to say Random Forest has already landed as a benchmark path

2. The roadmap understated which backend truth surfaces now exist.

Closed by:

- updating the roadmap to mention:
  - `/api/v1/risk/model-alignment/`
  - `compare_model_candidates`

3. The roadmap risked overclaiming that all surfaces are promotion-filtered.

Closed by:

- narrowing the claim to dashboard-facing truth surfaces
- explicitly noting that admin/audit surfaces may remain broader

4. The roadmap implied broader scheduling maturity than is actually implemented.

Closed by:

- clarifying that scheduled scoring exists now
- clarifying that scheduled retraining does not

5. Some scoped product-surface claims were implemented but not directly proven by dedicated tests.

Closed by:

- adding focused tests for:
  - `latest-ward-risk`
  - `ward-intelligence`
  - `facility-intelligence`
  - benchmark-visible `model-alignment`

## Remaining Honest Gaps

1. Real out-of-time validation metrics are still not persisted.
2. Real calibration metrics are still not persisted.
3. Lead-time validation against real outbreak timing is still not implemented.
4. A future promotion rollback workflow is still not implemented.
5. Retraining remains policy-only, not workflow-complete.

## Verdict

The roadmap is now materially closer to the real backend state.

It is credible if read as:

- an executed roadmap through Phase 5
- with conservative promotion governance
- and with explicit remaining evidence gaps

It would not be credible if read as claiming:

- complete retraining maturity
- completed promotion evidence
- runnable boosted models
- or universal filtering of all backend read surfaces to promoted truth only
