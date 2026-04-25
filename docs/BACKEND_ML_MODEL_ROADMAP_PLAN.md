# Backend ML Model Roadmap Plan

## Goal

Define the intentional early-phase model progression for CCHIS so model rollout stays aligned with:

- the project proposal
- current backend reality
- dashboard prediction claims
- operational trust requirements

This plan exists so model evolution is treated as a deliberate backend track, not as an implied side effect of dashboard work.

This roadmap depends on a separate ETL and feature-pipeline plan:

- [BACKEND_ETL_AND_FEATURE_PIPELINE_PLAN.md](/Users/edwininganji/VSCodeProjects/cchis/docs/BACKEND_ETL_AND_FEATURE_PIPELINE_PLAN.md)
- [BACKEND_FACILITY_BURDEN_FORECASTING_PLAN.md](/Users/edwininganji/VSCodeProjects/cchis/docs/BACKEND_FACILITY_BURDEN_FORECASTING_PLAN.md)

The ETL plan defines the source cadence, feature lineage, and dataset discipline required to make model comparison and alert generation trustworthy.

---

## Industry-Standard Principles

This roadmap follows an industry-standard promotion principle:

- the best model is not automatically the fanciest model
- the best model is the most governable model that produces the best operational outcome

For CCHIS, that means:

- interpretable baselines are legitimate production choices
- benchmark models must prove value, not just complexity
- model promotion must be evidence-based and documented
- live alerting should follow promoted outputs only, not experimental runs

This is why promotion discipline matters more than model prestige.

---

## Current Truth

The current live scheduled backend baseline is:

- `Logistic Regression`

This remains the only model currently scheduled as the live alert-governing baseline.

Code alignment today:

- `backend/risk/ml/model.py`
  - trains logistic regression and Random Forest
- `backend/risk/ml/pipeline.py`
  - defaults to logistic regression
  - supports an explicit Random Forest benchmark path
- `backend/risk/management/commands/run_risk_model.py`
  - supports explicit algorithm selection and dual-model runs
- `backend/core/settings.py`
  - scheduled execution still uses `model_version="lr-v1"` with the logistic default path

This means the backend is now in a transitional state:

- `Logistic Regression` is the live scheduled baseline
- `Random Forest` exists as a backend benchmark-capable path
- `Random Forest` is not yet promoted as the live scheduled model

That is closer to the proposal's early-phase intent, and promotion discipline is now both documented and partially enforced in backend comparison and alignment surfaces.

Additional current truth after execution of Phases 0 to 5:

- `XGBoost` and `LightGBM` now exist only as backend-owned readiness candidates
- they are not runnable live defaults
- they are not benchmark-promoted models
- dashboard-facing ward, latest-risk, intelligence, facility, and map surfaces now prefer promoted live outputs over newer benchmark-only or demo-only outputs
- no scheduled retraining task exists yet
- retraining remains manual only
- a dedicated backend truth surface now exists for product consumers:
  - `/api/v1/risk/model-alignment/`
- a dedicated backend comparison command now exists for promotion review:
  - `compare_model_candidates`

### Current executed status

The roadmap is no longer purely aspirational.
The following phase outputs now exist and should be treated as the audited record of what was actually implemented:

- [BACKEND_ML_MODEL_PHASE_0_STATUS.md](/Users/edwininganji/VSCodeProjects/cchis/docs/BACKEND_ML_MODEL_PHASE_0_STATUS.md)
- [BACKEND_ML_MODEL_PHASE_1_STATUS.md](/Users/edwininganji/VSCodeProjects/cchis/docs/BACKEND_ML_MODEL_PHASE_1_STATUS.md)
- [BACKEND_ML_MODEL_PHASE_2_STATUS.md](/Users/edwininganji/VSCodeProjects/cchis/docs/BACKEND_ML_MODEL_PHASE_2_STATUS.md)
- [BACKEND_ML_MODEL_PHASE_3_EVALUATION.md](/Users/edwininganji/VSCodeProjects/cchis/docs/BACKEND_ML_MODEL_PHASE_3_EVALUATION.md)
- [BACKEND_ML_MODEL_PHASE_4_STATUS.md](/Users/edwininganji/VSCodeProjects/cchis/docs/BACKEND_ML_MODEL_PHASE_4_STATUS.md)
- [BACKEND_ML_MODEL_PHASE_5_STATUS.md](/Users/edwininganji/VSCodeProjects/cchis/docs/BACKEND_ML_MODEL_PHASE_5_STATUS.md)

The stricter claims-versus-implementation audit is recorded in:

- [BACKEND_ML_MODEL_IMPLEMENTATION_AUDIT.md](/Users/edwininganji/VSCodeProjects/cchis/docs/BACKEND_ML_MODEL_IMPLEMENTATION_AUDIT.md)

### Current unresolved limitations

The roadmap must remain honest about the following residual limitations:

- current comparative evidence is still early-phase and still depends heavily on seeded or proxy-heavy data
- calibration review is not complete
- lead-time validation against real outbreak timing is not complete
- temporal robustness over longer historical windows is not complete
- no scheduled retraining workflow exists yet
- no boosted-model explainability implementation exists yet
- model promotion is still intentionally conservative

---

## Target Early-Phase Model Progression

The intended progression is:

1. current live baseline = `Logistic Regression`
2. next model after the live baseline = `Random Forest` benchmark
3. later evolution = `XGBoost / LightGBM`

This ordering should remain explicit in both backend planning and dashboard-facing prediction language.

The intended backend direction for early prediction work is:

- `Logistic Regression` as the live baseline
- `Random Forest` as the benchmark model already landed in backend execution paths
- eventual support for both models on comparable inference slices

This is important because the project goal is not merely to score wards in the abstract.
It is to support `7 to 14 day` early cholera-risk prediction and alert generation under disciplined model governance.

### Model-track distinction

This roadmap is primarily for:

- ward-risk classification models

It should explicitly distinguish those from:

- facility burden and surge forecasting models
- calibration methods
- later temporal and spatiotemporal evolution

The main separation is:

- `Logistic Regression`
- `Random Forest`
- later `XGBoost / LightGBM`
  - classification and alert-support track

- `Negative Binomial Regression`
  - facility burden / surge forecasting track

- `Isotonic regression` / `Platt scaling`
  - calibration methods, not primary forecasting models

- `SARIMAX`, `Prophet`, and lagged temporal models
  - later temporal evolution track

---

## Why This Order

### Logistic Regression

Use as the current live baseline because it is:

- already implemented
- interpretable
- suitable for low-data early-stage deployment
- easier to explain to public-health and government stakeholders

### Random Forest

Add next as the benchmark model because it is:

- a strong non-linear benchmark for structured data
- part of the proposal's early-phase model set
- useful for testing whether the logistic baseline is leaving predictive performance on the table

Random Forest should be introduced as a benchmark first, not assumed to replace the live baseline automatically.

### XGBoost / LightGBM

Treat as later evolution because they are:

- higher-capacity structured-data models
- likely stronger once data quality and quantity improve
- more complex to govern, explain, and operationalize

These should only be promoted after disciplined benchmarking and lineage controls are in place.

### Negative Binomial Regression

This proposal model remains important, but it belongs to a separate forecasting plan because it addresses:

- expected case counts
- facility pressure
- surge-readiness reasoning

It should not be folded casually into the ward-risk classification roadmap.

---

## Model Roadmap Principles

### 1. Dashboard claims must follow live backend truth

The dashboard must not imply that Random Forest or boosting-based models are live until they are actually implemented, evaluated, and promoted.

### 2. Benchmarking does not mean automatic promotion

Adding a new model family does not by itself justify replacing the live baseline.

Promotion must require:

- comparable evaluation windows
- explicit success criteria
- documented tradeoffs
- auditability

And promotion must not be based only on:

- training accuracy
- prettier feature-importance outputs
- a single benchmark run
- a newer model family existing in code

### 3. Early-phase backend must support both Logistic Regression and Random Forest

To stay aligned with the proposal, the backend roadmap must reach a stage where both early-phase models are usable for prediction work:

- `Logistic Regression`
- `Random Forest`

This does not require both to become equal production authorities immediately.
It does require:

- shared ETL inputs
- shared feature discipline
- comparable inference windows
- persisted lineage for both outputs
- explicit alert-governance decisions about which output drives action

### 4. Model lineage must remain explicit

Every prediction-producing run should retain:

- `model_version`
- `algorithm_name`
- run timestamp
- training/inference provenance

### 5. Interpretability matters in early deployment

Where model performance differences are modest, simpler and more explainable models should retain strong preference in early public-health deployment.

### 6. Training and retraining must be orchestrated explicitly

The ML layer should not rely on ad hoc manual execution once it becomes operationally meaningful.

Early-phase orchestration should use:

- Celery workers for model-execution jobs
- Celery Beat for scheduled scoring jobs
- scheduled retraining only after a later phase explicitly implements it
- management commands for manual reruns, benchmark runs, and backfills

The plan should distinguish clearly between:

- scheduled inference / scoring
- scheduled retraining
- manual benchmark evaluation
- seeded demo prediction runs

### 7. Product surfaces must prefer promoted truth over recency

Dashboard-facing and operator-facing backend reads must not simply use the newest available model output.

They must prefer:

- promoted live-baseline outputs

over:

- benchmark-only outputs
- seeded demo outputs
- candidate-only future model states

This rule matters because product trust is broken if a newer benchmark run silently outranks the actual live baseline.

Admin and audit surfaces may still expose broader run history, including benchmark-only and demo-only records.
That is acceptable as long as those surfaces are not mistaken for operational truth surfaces.

---

## Phase 0: Baseline Freeze and Truth Audit

### Objective

Freeze the current live baseline and document what is already real.

### Phase-close git discipline

This phase is not complete until:

- the phase work is committed to git with an intentional phase-specific commit
- the branch is pushed after the commit

### Work

- confirm the current scheduled model path is logistic regression only
- confirm the current stored lineage fields are sufficient for dashboard and audit usage
- document any mock or synthetic prediction behavior still present in the pipeline
- record the exact backend files and settings that make logistic regression the live baseline

### Output

Create:

- `docs/BACKEND_ML_MODEL_PHASE_0_STATUS.md`

---

## Phase 1: Logistic Regression Baseline Hardening

### Objective

Make the current live baseline explicit, stable, and auditable before adding benchmark models.

### Phase-close git discipline

This phase is not complete until:

- the phase work is committed to git with an intentional phase-specific commit
- the branch is pushed after the commit

### Backend work

- verify feature set provenance for the live baseline
- verify model version naming discipline
- ensure prediction outputs persist algorithm and version metadata
- ensure scheduled runs, manual runs, and seeded demo runs remain distinguishable
- define Celery task boundaries for live scoring versus retraining
- define whether retraining is time-based, data-volume-based, or manually promoted in early phase

### Rules

- do not relabel the current model vaguely as just `ML model`
- use explicit baseline naming in backend lineage and internal admin surfaces

---

## Phase 2: Random Forest Benchmark Implementation

### Objective

Add Random Forest as the next intentional benchmark model without silently replacing the live baseline.

### Phase-close git discipline

This phase is not complete until:

- the phase work is committed to git with an intentional phase-specific commit
- the branch is pushed after the commit

### Backend work

- implement Random Forest training path
- implement benchmark inference path
- add explicit model version naming for Random Forest
- ensure shared feature inputs with the logistic baseline where appropriate
- ensure benchmark outputs can be compared against the same target window
- ensure benchmark runs can be scheduled or queued without replacing the live scoring task

### Minimum contract expectations

The backend should be able to distinguish at least:

- `lr-v1`
- `rf-v1`

And store:

- `algorithm_name`
- `model_version`
- evaluation metadata where available

### Rules

- Random Forest must first land as a benchmarkable backend option
- do not silently switch Celery or scheduled runs to Random Forest without an explicit promotion step

### Required outcome

By the end of this phase, the backend should be able to run comparable prediction jobs for:

- `Logistic Regression`
- `Random Forest`

even if only one remains the live alert-driving baseline at that point.

---

## Phase 3: Comparative Evaluation and Promotion Decision

### Objective

Decide whether the live baseline should remain logistic regression or be replaced by Random Forest.

### Phase-close git discipline

This phase is not complete until:

- the phase work is committed to git with an intentional phase-specific commit
- the branch is pushed after the commit

### Evaluation dimensions

- discrimination quality
- calibration quality
- lead-time usefulness
- temporal robustness
- interpretability cost
- operational trustworthiness

### Evidence discipline

The following are not sufficient on their own to justify promotion:

- training accuracy
- in-sample comparison only
- a single-day benchmark result
- feature importance visibility alone

Promotion-quality evidence should prefer:

- out-of-time comparison windows
- lead-time usefulness against the operational target
- calibration review
- explicit trust-policy behavior under degraded ETL conditions
- written rollback readiness if promotion later occurs

### Promotion rule

Promotion should require:

- written comparison of `Logistic Regression` vs `Random Forest`
- explicit decision note
- documented impact on dashboard wording if promotion occurs

The decision note must also state how alert generation is governed:

- logistic-regression primary
- random-forest primary
- shadow benchmark mode
- consensus / disagreement review mode

It must also state:

- which Celery task drives live alert-producing predictions
- which task, if any, performs retraining
- which tasks are benchmark-only and must not affect live alerts

If the decision introduces:

- `consensus / disagreement review mode`

then the note must also state:

- what constitutes disagreement
- whether disagreement blocks alerts or routes them to review
- what backend and dashboard contract changes are required before that mode is considered real

---

## Scheduling Guidance

### Early-phase recommendation

Keep training and scoring separate.

Recommended pattern:

- ingestion runs on a scheduled basis in ETL
- scoring / inference runs after fresh enough data is available
- retraining runs less frequently and only when enough new data justifies it

### Practical cadence

For the early phase, a reasonable discipline is:

- scoring / prediction generation: `daily`
- retraining review cadence: `weekly` or `biweekly`
- full model-promotion decisions: manual and documented

This keeps the system responsive enough for `7 to 14 day` early warning without pretending constant retraining is automatically better.

### Output

Create:

- `docs/BACKEND_ML_MODEL_PHASE_3_EVALUATION.md`

This should clearly state whether:

- logistic regression remains live
- Random Forest becomes the new live model
- more evidence is required before changing production behavior

---

## Phase 4: XGBoost / LightGBM Readiness

### Objective

Prepare for later boosting-model evolution without prematurely committing the live system to it.

### Phase-close git discipline

This phase is not complete until:

- the phase work is committed to git with an intentional phase-specific commit
- the branch is pushed after the commit

### Backend work

- define requirements for boosting-model feature discipline
- define resource and training expectations
- define evaluation gates stricter than the Random Forest benchmark gate
- define explainability and monitoring requirements for higher-capacity models

### Rules

- do not present XGBoost or LightGBM as near-term live defaults until benchmark discipline is complete
- do not add boosted-model branding to the dashboard before a backend promotion decision exists

### Output

Create:

- `docs/BACKEND_ML_MODEL_PHASE_4_STATUS.md`

---

## Phase 5: Dashboard and Product Alignment

### Objective

Keep product language aligned with the true live model state.

### Phase-close git discipline

This phase is not complete until:

- the phase work is committed to git with an intentional phase-specific commit
- the branch is pushed after the commit

### Required alignment rules

- dashboard prediction UI must remain model-family agnostic for end users unless a specific model name is intentionally surfaced
- internal docs must state:
  - current live baseline
  - current benchmark model
  - future candidate models
- any dashboard metadata field such as `prediction_model_version` must reflect backend truth
- dashboard-facing backend selectors must prefer promoted outputs over newer benchmark-only or demo-only outputs
- benchmark-only or candidate-only model families must not become apparent operational authority through recency alone

### Cross-plan dependency

The dashboard decision-layer plan should reference this roadmap so map prediction and alerting semantics do not outrun backend model reality.

This roadmap should also remain explicitly linked to:

- [BACKEND_ETL_AND_FEATURE_PIPELINE_PLAN.md](/Users/edwininganji/VSCodeProjects/cchis/docs/BACKEND_ETL_AND_FEATURE_PIPELINE_PLAN.md)

because dual-model prediction and alert generation are only credible if both models consume disciplined ETL outputs.

The separate facility-burden forecasting track is documented in:

- [BACKEND_FACILITY_BURDEN_FORECASTING_PLAN.md](/Users/edwininganji/VSCodeProjects/cchis/docs/BACKEND_FACILITY_BURDEN_FORECASTING_PLAN.md)

### Execution-order note

Implementation should follow this sequence:

1. `ETL scheduling first`
2. `daily scoring next`
3. `retraining cadence after that`
4. `dashboard consumes only promoted outputs`

This means benchmark models and retraining work must not outrun source freshness discipline or the explicit promotion of live model outputs.

### Output

Create:

- `docs/BACKEND_ML_MODEL_PHASE_5_STATUS.md`

### Implemented backend truth surfaces

At the end of this phase, the backend should expose or preserve:

- a product-facing truth surface for current live-versus-benchmark state
- dashboard-facing selectors that prefer promoted outputs
- broader admin and audit surfaces that still preserve non-promoted run history without promoting it accidentally

### Start condition for ML Phase 0

Before beginning ML Phase 0, complete the small ETL hardening step for:

- `scheduler / worker heartbeat`

This is intentionally narrower than full multi-source ETL completion.
The purpose is to ensure the current scheduled logistic baseline is audited on top of a minimally hardened orchestration surface, without blocking Phase 0 on every later data-domain expansion.

---

## Success Condition

This roadmap is successful when:

- the live backend baseline is explicit and auditable
- Random Forest exists as a real benchmark path
- promotion decisions are evidence-based
- later XGBoost / LightGBM work is intentional rather than implied
- the dashboard never overclaims the sophistication of the backend model layer

---

## Self-Critical Audit

Before calling this plan complete, audit it critically against the following questions:

1. Does the roadmap clearly separate classification, facility forecasting, calibration, and later temporal evolution?
2. Does it make promotion discipline stronger than model prestige?
3. Does it keep `Logistic Regression` and `Random Forest` aligned to comparable ETL and inference inputs?
4. Does it define scheduling, scoring, retraining, and benchmark-only execution clearly enough?
5. Does it avoid implying that calibration methods or temporal models are early-phase production defaults?
6. Does it link live alerting only to promoted outputs?
7. Does every phase include explicit git commit and push closure discipline?
8. Does it forbid promotion by weak evidence such as training accuracy alone?
9. Does it state current unresolved limitations instead of only future intent?
10. Does it prevent benchmark recency from outranking promoted operational truth?

Any gap found in this audit must be closed in the plan before treating the plan as execution-ready.

---

## Final Note

The early-phase target is not to sound advanced.

It is to be:

- truthful
- benchmarked
- explainable
- operationally trustworthy

That means the correct current statement is:

- live baseline now = `Logistic Regression`
- next model after the live baseline = `Random Forest` benchmark, already landed as a backend benchmark path
- later evolution = `XGBoost / LightGBM`

And the correct early-phase target state is:

- both `Logistic Regression` and `Random Forest` are supported in backend prediction work
- alert generation remains governed by explicit model and policy decisions
- the system stays honest about which model is actually driving live alerts at any given time
