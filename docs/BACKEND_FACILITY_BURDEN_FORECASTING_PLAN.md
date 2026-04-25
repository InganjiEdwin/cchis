# Backend Facility Burden Forecasting Plan

## Goal

Define the backend forecasting track for facility burden and surge readiness so CCHIS can move from:

- ward-level cholera risk prediction

to:

- expected case-burden forecasting
- facility pressure forecasting
- surge-readiness guidance

This plan exists because facility burden forecasting is not the same problem as ward-risk classification.
It needs its own target variable, evaluation discipline, cadence, and operational outputs.

---

## Why This Is A Separate Plan

`Logistic Regression` and `Random Forest` in the main ML roadmap primarily support:

- ward-level risk classification
- early-warning alert generation

Facility burden forecasting is a separate modeling problem because it focuses on:

- expected counts
- likely facility load
- readiness thresholds
- surge-sensitive operational planning

The proposal’s main early forecasting model for this is:

- `Negative Binomial Regression`

This deserves a separate plan so it is not buried inside the classification roadmap.

---

## Proposal Alignment

The proposal positions facility forecasting as:

- forecasting expected counts of diarrhea or suspected cholera cases
- supporting surge thresholds for ORS, staffing, and bed readiness

It specifically highlights:

- `Negative Binomial Regression`

because overdispersed count data is a better fit for this than simpler count assumptions such as Poisson.

---

## Model Position

### Early facility-forecasting baseline

The early intended model for facility burden forecasting is:

- `Negative Binomial Regression`

### Why this model fits

- appropriate for count data
- interpretable
- epidemiologically defensible
- better suited when variance exceeds the mean

### Later evolution

Later forecasting evolution may include:

- temporal count models
- lagged boosted models
- richer spatiotemporal burden models

But those should not be phase-one operational defaults.

---

## Relationship To The Other Plans

This plan depends on:

- [BACKEND_ETL_AND_FEATURE_PIPELINE_PLAN.md](/Users/edwininganji/VSCodeProjects/cchis/docs/BACKEND_ETL_AND_FEATURE_PIPELINE_PLAN.md)
- [BACKEND_ML_MODEL_ROADMAP_PLAN.md](/Users/edwininganji/VSCodeProjects/cchis/docs/BACKEND_ML_MODEL_ROADMAP_PLAN.md)

And it feeds:

- [DASHBOARD_DECISION_LAYER_IMPLEMENTATION_PLAN.md](/Users/edwininganji/VSCodeProjects/cchis/docs/DASHBOARD_DECISION_LAYER_IMPLEMENTATION_PLAN.md)

Dependency logic:

- ETL provides facility, population, ward-risk, and surveillance inputs
- classification models estimate ward risk and expected pressure drivers
- facility burden forecasting estimates likely case load and readiness strain
- dashboard consumes promoted readiness and pressure outputs

---

## Industry-Standard Principles

This forecasting track should follow the same promotion philosophy as the other plans:

- choose the most governable model that produces the best operational outcome
- do not replace clear interpretable forecasting with higher complexity without evidence
- keep forecasting outputs explainable enough for public-health operations

For this track, that means:

- count forecasting must be traceable to demand and capacity drivers
- readiness warnings must not be vague UI text
- promotion discipline matters more than forecasting sophistication

---

## Forecasting Objective

The primary backend objective is to forecast:

- expected case counts by facility or catchment over a near-term window
- projected facility pressure state
- surge-readiness thresholds for critical operational resources

Example outputs:

- `projected_case_burden`
- `projected_pressure_score`
- `projected_readiness_state`
- `surge_threshold_state`

---

## Core Inputs

Facility burden forecasting should combine:

### 1. Expected demand signals

- ward-level risk predictions
- predicted cases by ward where available
- recent diarrheal / cholera trends
- CHV suspected-case and activity signals
- alert escalation patterns
- catchment population exposure

### 2. Facility coping-capacity signals

- facility type and service scope
- staffing proxy
- stock and supply readiness
- current burden signal
- service availability state
- referral overflow signal
- access disruption or flood-access risk

### 3. Spatial and catchment context

- ward-to-facility relationships
- travel or access proxy
- neighboring-facility alternatives
- catchment population estimates

---

## Target Variables

This track should explicitly define what is being predicted.

Recommended early target choices:

- expected suspected-cholera or diarrheal case counts per facility-time window
- expected burden bucket:
  - `low`
  - `watch`
  - `capacity_concern`
- surge threshold crossings for:
  - ORS
  - staffing
  - bed or observation burden

The model should not be left ambiguous between:

- classification
- count prediction
- readiness scoring

Those should be related, but explicitly distinguished.

---

## Negative Binomial Regression Role

`Negative Binomial Regression` should be the early forecasting baseline for this track.

### Operational role

- estimate expected counts, not just general risk tone
- support interpretable burden drivers
- support surge-threshold reasoning

### Why it should come first here

- it fits overdispersed count data better than Poisson
- it stays explainable for operations
- it aligns cleanly with the proposal’s facility forecasting direction

---

## Forecast Outputs For Product Use

Once promoted, backend forecasting outputs should support:

- facility readiness summaries
- dashboard readiness warnings
- action-panel context
- facility detail pages
- resource-preparedness reasoning

Minimum promoted contract should include:

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

---

## Scheduling and Cadence

This forecasting track should follow the shared execution-order discipline:

1. `ETL scheduling first`
2. `daily scoring next`
3. `retraining cadence after that`
4. `dashboard consumes only promoted outputs`

Recommended early cadence:

- facility burden scoring: `daily`
- retraining review cadence: `weekly` or `biweekly`
- promotion of new forecasting variants: manual and documented

---

## Phase 0: Forecasting Truth Audit

### Objective

Document what real facility-readiness and case-burden data exists today.

### Phase-close git discipline

This phase is not complete until:

- the phase work is committed to git with an intentional phase-specific commit
- the branch is pushed after the commit

### Work

- confirm what facility inputs exist in the backend now
- confirm which inputs are direct operational truth versus derived proxy
- confirm whether historical case counts are available at facility or catchment level
- identify which readiness outputs can be made truthful early

### Output

Create:

- `docs/BACKEND_FACILITY_BURDEN_FORECASTING_PHASE_0_STATUS.md`

---

## Phase 1: Target and Contract Definition

### Objective

Define the first real forecasting target and backend output contract.

### Phase-close git discipline

This phase is not complete until:

- the phase work is committed to git with an intentional phase-specific commit
- the branch is pushed after the commit

### Work

- pick the initial target window
- define the count target
- define readiness-state mapping
- define forecast output fields
- define what the dashboard is allowed to show

---

## Phase 2: Negative Binomial Baseline Implementation

### Objective

Implement `Negative Binomial Regression` as the initial facility-burden forecasting baseline.

### Phase-close git discipline

This phase is not complete until:

- the phase work is committed to git with an intentional phase-specific commit
- the branch is pushed after the commit

### Work

- build training path
- build scoring path
- persist forecast lineage
- connect outputs to facility-readiness model shape
- keep scheduled scoring separate from retraining

---

## Phase 3: Evaluation and Promotion

### Objective

Decide whether the forecast is trustworthy enough to drive dashboard and readiness outputs.

### Phase-close git discipline

This phase is not complete until:

- the phase work is committed to git with an intentional phase-specific commit
- the branch is pushed after the commit

### Evaluation dimensions

- count error discipline
- threshold usefulness
- operational usefulness
- stability across time windows
- explainability

### Promotion rule

Do not let dashboard readiness warnings rely on this model until promotion is documented.

---

## Phase 4: Dashboard Integration

### Objective

Feed promoted facility-burden outputs into the dashboard decision layer.

### Phase-close git discipline

This phase is not complete until:

- the phase work is committed to git with an intentional phase-specific commit
- the branch is pushed after the commit

### Work

- connect promoted outputs to readiness summaries
- connect `driving_ward_ids` to map and action reasoning
- show facility pressure honestly
- distinguish proxy-based readiness from forecast-backed readiness

---

## Final Note

Yes, this should be a separate plan.

The ward-risk classification track and the facility-burden forecasting track are related, but they are not the same modeling problem.

The clean separation is:

- `Logistic Regression` and `Random Forest`
  - ward-risk classification and alert support
- `Negative Binomial Regression`
  - facility burden / surge forecasting

That separation is the more intentional and less wasteful architecture.

---

## Self-Critical Audit

Before calling this plan complete, audit it critically against the following questions:

1. Does the plan keep facility burden forecasting clearly separate from ward-risk classification?
2. Does it define expected counts, projected pressure, and readiness-state outputs clearly enough?
3. Does it stay honest about proxy-based readiness inputs versus direct operational truth?
4. Does it make `Negative Binomial Regression` the explicit early baseline for this track?
5. Does it define promotion discipline before dashboard exposure?
6. Does it connect cleanly to ETL, ward-risk prediction, and dashboard consumers?
7. Does every phase include explicit git commit and push closure discipline?

Any gap found in this audit must be closed in the plan before treating the plan as execution-ready.
