# Backend ETL and Feature Pipeline Plan

## Goal

Establish the backend data pipeline required to support the core CCHIS outcome from the proposal:

- predict ward-level cholera risk `7 to 14 days` before observed outbreak signals
- generate trustworthy alert candidates from those predictions
- support downstream preparedness actions across CHVs, facilities, and county operations

This plan exists because the prediction goal depends as much on data quality, freshness, lineage, and feature discipline as it does on model choice.

---

## Why This Is Its Own Plan

The ETL layer should not be buried inside either the dashboard plan or the ML roadmap.

It is its own backbone because it must define:

- which data sources matter
- how often they must be ingested
- how they are normalized
- how failed or late data is handled
- how features are generated and versioned
- how training and inference datasets are snapshotted
- how predictions and alerts remain traceable back to source data

The dashboard consumes ETL outputs.
The ML layer depends on ETL outputs.
Neither should outrun ETL truth.

---

## Industry-Standard Principles

This plan follows a simple industry-standard rule:

- do not optimize for sophistication first
- optimize for trustworthy operational outcomes first

For ETL, that means:

- reproducible ingestion before clever downstream modeling
- explicit freshness before confident visualization
- canonical normalized records before model-specific shortcuts
- lineage and replayability before scale claims

The data pipeline should make it easier to govern model promotion and operational decisions, not harder.

---

## Ops Surface Strategy

### Early-phase recommendation

The ETL layer does **not** require a dedicated frontend in its first serious implementation phase.

Early-phase operational control can be handled through:

- Django admin
- authenticated backend endpoints
- management commands
- observability dashboards
- structured run-history models

This is enough if the ops surface supports:

- ingestion run visibility
- source freshness visibility
- failure visibility
- replay / retry controls
- manual correction notes where necessary
- provenance inspection

### When a dedicated frontend becomes justified

Add a dedicated ETL frontend only if operations become too complex for admin-first management, for example:

- many external sources with different cadences
- frequent partial-failure handling
- many operator-owned retries and overrides
- non-technical operations users needing a controlled interface

Until then, `Django admin + endpoints + run tracking + observability` is the correct intentional choice.

### Ops input modes

The ETL layer should intentionally support two input modes:

- `seeded demo mode`
- `live source mode`

These modes should share the same canonical pipeline expectations wherever possible, so dev/test behavior exercises the real ingestion and feature machinery instead of bypassing it completely.

### Scheduling and orchestration requirement

The ETL layer should be orchestrated explicitly, not informally.

Early-phase scheduling should be handled through:

- Celery workers for execution
- Celery Beat for scheduled ingestion
- management commands for manual replay and backfill

This should cover:

- scheduled source pulls
- feature-generation jobs
- freshness checks
- replay / catch-up jobs after downtime

The ETL plan should not assume cron-only execution once ingestion becomes operationally important.

---

## Proposal-Aligned Outcome

The proposal requires a system that combines:

- rainfall patterns and forecasts
- flood indicators
- geospatial and vulnerability signals
- historical disease trends
- CHV and facility response data where available

to generate ward-level cholera risk predictions up to `7 to 14 days` in advance.

This ETL plan therefore targets a pipeline that supports:

1. prediction of near-term cholera risk by ward
2. alert generation from model- and rule-mediated risk signals
3. facility preparedness reasoning
4. explainable lineage from source data to alert candidate

---

## Core Data Domains Needed

To actually achieve the proposal goals, the system needs at least the following categories of data.

### 1. Climate and hydrometeorological data

Minimum useful inputs:

- rainfall observations
- rainfall forecasts
- rolling rainfall totals
  - `3-day`
  - `7-day`
  - `14-day`
- rainfall anomaly relative to baseline
- flood proxy or flood indicator
- days since heavy rainfall threshold exceedance

Why it matters:

- this is the primary anticipatory signal for cholera risk in the proposal

### 2. Ward geography and spatial context

Minimum useful inputs:

- ward boundaries
- ward centroids or equivalent spatial anchors
- neighboring-ward relationships
- facility proximity / catchment approximations
- water-body distance or floodplain exposure where available

Why it matters:

- prediction, spatial spillover, and facility reasoning all depend on stable ward geography

### 3. Historical disease and surveillance data

Minimum useful inputs:

- cholera case counts or outbreak labels by ward and time window
- diarrheal disease trend proxies if cholera labels are sparse
- neighboring ward outbreak signal
- outbreak history by season / epidemiological week

Why it matters:

- this is the target signal and temporal context required to train and validate 7–14 day predictions

### 4. Facility readiness and burden data

Minimum useful inputs:

- facility locations
- facility availability / activity state
- facility readiness signals
- surge-sensitive indicators where available
  - staffing proxy
  - stock or supply readiness proxy
  - referral burden proxy
- recent case burden or admissions proxy
- bed, observation, or treatment-capacity proxy where relevant
- stock levels for cholera-relevant supplies where available
  - ORS
  - IV fluids
  - IPC or water-treatment support supplies
- service disruption indicators
  - closure
  - reduced service
  - staff gap
  - access disruption

Why it matters:

- the proposal explicitly includes facility preparedness and surge forecasting

### 5. Population and settlement exposure data

Minimum useful inputs:

- ward population totals
- population density proxy
- household count proxy where available
- settlement distribution or settlement concentration proxy
- catchment population estimates for facilities where possible

Better spatial inputs where available:

- gridded population surfaces
- settlement footprints
- population concentration near flood-prone areas
- population concentration near unsafe-water or poor-sanitation exposure proxies

Why it matters:

- cholera risk depends not only on climate hazard but also on how many people are exposed
- population distribution is needed for more realistic expected case counts
- facility burden forecasting is weaker without catchment population context

### 6. CHV and community response signals

Minimum useful inputs:

- CHV submissions
- symptom / suspected-case reports where available
- household visit activity
- localized field observations
- alert delivery and response outcomes

Why it matters:

- this provides last-mile ground truth, operational feedback, and eventual model refinement

### 7. Vulnerability and contextual risk signals

Useful inputs where available:

- settlement density or population proxy
- sanitation vulnerability proxy
- water access vulnerability proxy
- displacement or disruption signals
- seasonal calendar features

Why it matters:

- these improve localized risk ranking and explain ward differences under similar rainfall conditions

---

## Ingestion Frequency Guidance

To support `7 to 14 day` ward-level early warning, not every source needs the same cadence.

### Climate and forecast ingestion

Recommended cadence:

- rainfall observations: `daily`, ideally more often if source updates support it
- rainfall forecasts: `daily` on each source refresh
- flood proxy / flood indicator refresh: `daily` after climate ingestion

Reason:

- the predictive horizon depends on climate movement, so these are the most time-sensitive upstream signals

### Disease and surveillance ingestion

Recommended cadence:

- `daily` where real daily feeds exist
- `weekly` minimum where only weekly public-health reporting is available
- if only weekly data exists, ETL must still stamp and align it explicitly so models do not pretend daily certainty

Reason:

- labels may be slower than climate data, but they are still needed frequently enough to maintain temporal learning and validation

### CHV ingestion

Recommended cadence:

- near-real-time when connectivity exists
- otherwise ingest on every sync submission

Reason:

- CHV data is both operational feedback and potential early signal enrichment

### Facility readiness ingestion

Recommended cadence:

- `daily` preferred
- `every shift` or more often only if the source genuinely supports it

Reason:

- facility preparedness matters operationally, but usually changes slower than rainfall

### Static or slow-moving datasets

Recommended cadence:

- ward geometry: on controlled dataset release only
- vulnerability layers: monthly, quarterly, or when source revisions occur
- facility master data: as changed, with regular reconciliation

Reason:

- these should be versioned and activatable, not reingested noisily

---

## Freshness Standards

The system should distinguish source freshness explicitly.

At minimum, ETL must track:

- `last_successful_ingestion_at`
- `source_data_timestamp`
- `freshness_state`
  - `fresh`
  - `delayed`
  - `stale`
- `fallback_used`

The dashboard and alert layers should never compress all freshness into one ambiguous timestamp.

---

## Demo Data Generation and Live Ops Feeding

The ETL plan should explicitly support both:

- generated dummy data for development, QA, demos, and workflow validation
- operator-fed or source-fed real data for credible prediction and alerting

### 1. Seeded dummy-data generation

Seeded or generated data is appropriate for:

- ETL pipeline testing
- schema and validation testing
- feature generation testing
- dashboard state testing
- alert-flow testing
- notification and websocket testing
- end-to-end scenario validation

Seeded data is **not** sufficient for:

- model performance claims
- real lead-time validation
- real false-alert evaluation
- real alert-threshold tuning
- production confidence claims

#### Recommended seeded scenario families

The ETL layer should support stable scenario bundles such as:

- `stable_baseline`
- `rainfall_watch_cluster`
- `escalating_triggered_hotspot`
- `facility_capacity_pressure`
- `delivery_failure_concern`
- `mixed_data_freshness`

#### Recommended dummy data coverage

Seeded generation should be able to create coherent examples for:

- rainfall observations and forecasts
- flood indicators
- ward-level surveillance labels or case proxies
- facility-readiness snapshots
- CHV reports and alert outcomes
- vulnerability and population exposure features
- source freshness states

#### Rules for seeded data

- all seeded ETL data must be explicitly marked non-production
- seeded predictions must never be mislabeled as real live model results
- seeded scenario names should be stable and human-readable
- seeded data should exercise realistic temporal windows rather than random disconnected records

### 2. How ops can feed actual data

Ops should be able to feed real data without needing a separate custom frontend in the early phase.

Supported operational paths should include:

- source adapters calling external APIs on schedule
- management commands for manual pulls or replays
- authenticated ingestion endpoints for trusted source pushes
- Django admin for controlled metadata review, corrections, and manual activation where appropriate
- bulk import utilities for approved CSV or file-based backfills

#### Recommended early-phase ops workflow

For each source domain, ops should have a documented path for:

1. `configure source`
   - source URL or source file location
   - credentials or access token if needed
   - refresh cadence
   - expected timestamp behavior

2. `run ingestion`
   - scheduled task for normal operation
   - management command for manual run
   - optional authenticated endpoint for trusted upstream pushes

3. `inspect run result`
   - records seen
   - records loaded
   - records rejected
   - fallback used
   - freshness state
   - error summary

4. `correct or replay`
   - rerun a failed ingestion
   - import corrected backfill data
   - annotate manual correction reason

5. `promote downstream use`
   - make the normalized data available for feature generation
   - make generated features available for model runs
   - make resulting prediction lineage visible to dashboard and alert layers

### 3. Source-specific ops guidance

#### Climate and forecast data

Preferred ops path:

- scheduled adapter pulls
- manual backfill command for missed windows
- explicit source timestamp capture

#### Surveillance data

Preferred ops path:

- trusted integration endpoint or scheduled import
- CSV backfill support for historical datasets
- reconciliation notes for late or corrected reporting

#### Facility readiness data

Preferred ops path:

- admin-managed snapshot imports early on
- endpoint-based sync later when facility systems are available
- manual annotation support when proxy values are being used

#### CHV and alert-response data

Preferred ops path:

- app sync ingestion
- communication and alert outcome ingestion
- replay-safe ingestion discipline

### 4. Required operator documentation

For every real source introduced, ETL work should produce an ops note covering:

- what the source is
- how it is ingested
- expected cadence
- fallback behavior
- replay / backfill procedure
- validation rules
- who owns source access

### 5. Required honesty rules

- dev mode may use generated dummy data
- production credibility requires real historical and live source data
- the same ETL contracts should apply to both seeded and live data
- dashboard and alerting layers must remain aware of whether upstream data is seeded, delayed, proxy-based, or real

---

## Weather API Readiness

If a strong weather or climate API becomes available, the ETL layer should already be ready to absorb it without redesigning the whole pipeline.

### Recommended preparation

Define a weather-source adapter contract now, even before the final provider is chosen.

The adapter boundary should capture at least:

- `source_name`
- `source_type`
  - `observation`
  - `forecast`
- `provider`
- `source_timestamp`
- `ingested_at`
- `spatial_resolution`
- `temporal_resolution`
- `ward_mapping_method`
- `units`
- `quality_flag`
- `raw_source_ref`

### What to prepare before the provider is finalized

- provider-agnostic canonical weather record shape
- credentials and secret-management path
- source configuration model or settings structure
- retry and backoff rules
- rate-limit awareness
- backfill strategy
- ward-aggregation logic
- fallback behavior if the provider is unavailable

### Why this matters

This allows the team to:

- plug in a new weather API quickly
- compare providers if needed
- preserve the same downstream feature pipeline
- avoid coupling model code directly to one provider's payload format

### Recommended execution pattern

Weather ingestion should run as scheduled ETL work:

- Celery Beat schedules the pull
- Celery worker executes the fetch and normalization
- ingestion run history records the result
- downstream feature jobs run only after successful or policy-accepted ingestion

---

## ETL Architecture Requirements

### 1. Source adapters

Each external source should have its own explicit adapter boundary.

Adapters should handle:

- source authentication
- payload fetch
- source timestamp capture
- raw payload recording where policy allows
- normalization into canonical internal shapes

### 2. Ingestion run tracking

Every ingestion job should create a persistent run record.

Minimum fields:

- `source_name`
- `run_started_at`
- `run_finished_at`
- `status`
- `records_seen`
- `records_loaded`
- `records_rejected`
- `fallback_used`
- `error_summary`
- `operator_note`

### 3. Canonical intermediate data

Do not let model code consume provider-specific payloads directly.

ETL should normalize to stable internal records before feature generation.

### 4. Feature generation layer

The feature pipeline must generate reproducible ward-time features such as:

- cumulative rainfall windows
- rainfall anomalies
- flood proxy windows
- seasonal indicators
- neighboring-ward outbreak signal
- facility burden and readiness proxies
- vulnerability indicators

### 5. Training and inference dataset snapshots

The system must persist enough information to distinguish:

- training dataset reference
- inference dataset reference
- feature set version
- source coverage assumptions

This is essential for comparing model runs and explaining alerts.

---

## Feature Strategy for the Early Models

The ETL layer must support both:

- `Logistic Regression`
- `Random Forest`

for early-phase prediction work.

That means feature generation should produce a shared, disciplined baseline feature set suitable for both models.

Recommended early feature families:

- `3-day`, `7-day`, and `14-day` rainfall accumulation
- rainfall anomaly versus seasonal baseline
- recent flood proxy
- days since heavy rainfall threshold exceedance
- seasonal month / epi week
- historical outbreak density
- neighboring ward outbreak signal
- ward population total
- population density or settlement concentration proxy
- exposed population proxy near flood or water-risk areas where available
- facility catchment vulnerability proxy
- facility readiness / burden proxy
- CHV alert and field-response signals where stable enough

The ETL plan should not assume a feature set tailored only to one model family.

### Model-strength acknowledgement

The ETL and feature pipeline should explicitly acknowledge that these two early-phase models have different strengths and should be used with that in mind.

#### Logistic Regression strengths

- stronger interpretability
- clearer directional reasoning on structured baseline features
- better fit for early low-data public-health deployment
- easier to explain to operational and government stakeholders

ETL implication:

- preserve clean, stable, well-documented baseline features
- avoid unnecessary feature noise
- keep categorical handling and scaling discipline explicit

#### Random Forest strengths

- captures non-linear interactions more naturally
- handles threshold and interaction behavior better across mixed structured features
- can surface patterns the linear baseline may miss

ETL implication:

- preserve richer interaction-supporting features
- keep enough feature breadth to test non-linear signal combinations
- avoid collapsing all useful contextual variation into oversimplified linear summaries

#### Shared ETL rule

The pipeline should support both models on comparable inputs, while still respecting their different strengths.

That means:

- one disciplined canonical feature backbone
- explicit feature lineage
- room for model-specific preprocessing where justified
- no assumption that the feature strategy should only optimize for one model family

---

## Facility Readiness Prediction Inputs

To forecast facility readiness or likely pressure, ETL should combine two classes of signals:

### 1. Expected demand

- ward risk predictions
- predicted cases by ward or catchment
- recent diarrheal / cholera trends
- CHV suspected-case signals
- alert escalation patterns
- catchment population exposure

### 2. Ability to cope

- facility type and service scope
- facility staffing proxy
- critical-stock readiness proxy
- service availability state
- recent burden proxy
- referral overflow proxy
- geographic accessibility / disruption proxy

Early-phase facility-readiness outputs may be simple and still useful, for example:

- `ready`
- `watch`
- `capacity_concern`

or:

- `readiness_score`
- `projected_pressure_score`

The ETL layer should support these as truthful derived outputs, even before a richer facility-operations model exists.

---

## Dedicated Facility Readiness Data Model

To keep facility-readiness forecasting explicit and auditable, ETL should normalize facility-readiness data into a stable internal model shape instead of scattering these signals across unrelated payloads.

### Objective

Represent both:

- current facility coping ability
- projected facility pressure

in a way that can support:

- dashboard summaries
- ward detail and facility readiness views
- alert and escalation reasoning
- historical evaluation of preparedness performance

### Recommended logical entities

#### 1. Facility master record

Stable reference data for a facility:

- `facility_id`
- `facility_name`
- `facility_type`
- `county`
- `sub_county`
- `ward_id`
- `latitude`
- `longitude`
- `catchment_reference`
- `is_active`

#### 2. Facility readiness snapshot

Time-bound record of current readiness state:

- `facility_id`
- `snapshot_at`
- `readiness_state`
  - `ready`
  - `watch`
  - `capacity_concern`
- `readiness_score`
- `staffing_signal`
- `stock_signal`
- `service_availability_signal`
- `current_burden_signal`
- `access_disruption_signal`
- `source_ref`
- `freshness_state`

#### 3. Facility pressure forecast

Time-bound forecast of expected operational strain:

- `facility_id`
- `generated_at`
- `horizon_days`
- `projected_pressure_score`
- `projected_case_burden`
- `projected_readiness_state`
- `driving_ward_ids`
- `population_exposure_signal`
- `facility_capacity_signal`
- `model_or_rule_version`

#### 4. Facility readiness factors

Structured explainability layer for why a readiness state or forecast exists:

- `facility_id`
- `recorded_at`
- `factor_type`
  - `predicted_demand`
  - `staffing_constraint`
  - `stock_constraint`
  - `service_disruption`
  - `flood_access_risk`
  - `catchment_population_pressure`
- `factor_value`
- `factor_direction`
  - `improving`
  - `worsening`
  - `stable`
- `notes`

### Minimum early-phase requirement

Even if the full model above is not implemented immediately, ETL should still produce a truthful minimum facility-readiness shape containing:

- `facility_id`
- `snapshot_at`
- `readiness_state`
- `readiness_score`
- `projected_pressure_score`
- `driving_ward_ids`
- `freshness_state`

### Rules

- readiness must not be a vague UI adjective with no backend basis
- forecasted pressure must remain traceable to ward-risk and capacity inputs
- if true capacity data is weak, the system must explicitly treat some readiness fields as derived proxies rather than pretending they are direct operational truth

---

## Dual-Model Prediction Requirement

To stay aligned with the proposal and the project’s stated direction, the backend must eventually support both early-phase models in the prediction pipeline:

- `Logistic Regression`
- `Random Forest`

### What this means operationally

It does **not** mean both models must immediately become equal production authorities.

It means the ETL and feature pipeline must support a stage where:

- both models can be trained on comparable data windows
- both models can infer on the same ward-time slices
- both model outputs can be stored with lineage
- alert-generation logic can compare or govern against both outputs where configured

### Acceptable early rollout path

1. `Logistic Regression` remains the live baseline
2. `Random Forest` is added as a real benchmark inference path
3. both model outputs are evaluated against lead-time usefulness and false-alert tradeoffs
4. alert generation remains governed by explicit promotion or governance rules

### Future alert-governance options

Once both models are live in the backend, alert generation may use one of:

- primary-model only
- consensus gating
- disagreement review
- benchmark shadow mode

That governance decision belongs to ML + alerting policy, but ETL must support it by keeping the inputs and lineage consistent.

---

## Alert-Generation Alignment

The core goal is not prediction for its own sake.

The goal is:

- predict high-risk wards `7 to 14 days` early enough
- turn those predictions into trustworthy alert candidates
- support mediated human-in-the-loop action

Therefore ETL must support:

- prediction timestamps
- horizon timestamps
- lead-time evaluation
- alert-threshold feature context
- rule-engine inputs
- traceability from alert candidate back to feature values and source freshness

The prediction layer must not send alerts without mediation, consistent with the proposal’s assisted-response direction.

---

## Phase 0: Source and Gap Audit

### Objective

List what data we truly have, what is partial, and what remains missing.

### Phase-close git discipline

This phase is not complete until:

- the phase work is committed to git with an intentional phase-specific commit
- the branch is pushed after the commit

### Work

- inventory current climate inputs
- inventory current disease / outbreak labels
- inventory facility-readiness data already present in the system
- inventory CHV-originating data available for reuse
- identify which proposal data classes are absent or weak
- identify which current pipeline steps are still prototype or mock oriented
- identify which source domains can already be fed by ops in real mode
- identify which domains still need seeded demo generation to unblock development

### Output

Create:

- `docs/BACKEND_ETL_PHASE_0_STATUS.md`

---

## Phase 1: Ingestion Run Discipline

### Objective

Make every ingestion source observable and auditable.

### Phase-close git discipline

This phase is not complete until:

- the phase work is committed to git with an intentional phase-specific commit
- the branch is pushed after the commit

### Work

- add or harden ingestion-run persistence
- add source freshness state
- add failure and fallback tracking
- add retry / replay discipline
- distinguish seeded runs from real-source runs
- define Celery task boundaries for scheduled ingestion and replay

---

## Phase 2: Canonical Source Normalization

### Objective

Ensure provider-specific payloads are normalized before they reach model or dashboard logic.

### Phase-close git discipline

This phase is not complete until:

- the phase work is committed to git with an intentional phase-specific commit
- the branch is pushed after the commit

### Work

- define canonical climate records
- define canonical surveillance records
- define canonical facility-readiness records
- define canonical CHV response records
- define how seeded demo inputs map into the same canonical records
- define a provider-agnostic weather API adapter contract

---

## Phase 3: Feature Pipeline and Dataset Versioning

### Objective

Create reproducible ward-time feature datasets for both training and inference.

### Phase-close git discipline

This phase is not complete until:

- the phase work is committed to git with an intentional phase-specific commit
- the branch is pushed after the commit

### Work

- define baseline feature set version
- persist training and inference dataset references
- generate shared feature windows for Logistic Regression and Random Forest
- add dataset lineage to model runs and prediction outputs

---

## Phase 4: Dual-Model Inference Readiness

### Objective

Support consistent inference inputs for both early-phase models.

### Phase-close git discipline

This phase is not complete until:

- the phase work is committed to git with an intentional phase-specific commit
- the branch is pushed after the commit

### Work

- ensure the same inference slice can feed `Logistic Regression` and `Random Forest`
- persist both outputs cleanly when dual-model mode is enabled
- make alert governance capable of referencing explicit model lineage

---

## Phase 5: Freshness and Operational Trust

### Objective

Expose enough freshness and data quality truth for dashboard and alerting layers.

### Phase-close git discipline

This phase is not complete until:

- the phase work is committed to git with an intentional phase-specific commit
- the branch is pushed after the commit

### Work

- define stale-source behavior
- define delayed-source behavior
- define fallback semantics
- define when prediction or alerting should degrade, warn, or block
- define what happens when scheduled Celery ingestion is missed or delayed

---

## Phase 6: Verification and Audit

### Objective

Prove the ETL layer supports the project’s predictive and operational claims.

### Phase-close git discipline

This phase is not complete until:

- the phase work is committed to git with an intentional phase-specific commit
- the branch is pushed after the commit

### Verification questions

1. Do we have the minimum data needed for 7–14 day ward-level prediction?
2. Are ingestion cadences appropriate for the proposal’s early-warning goals?
3. Can every prediction be traced to source freshness and feature lineage?
4. Can both `Logistic Regression` and `Random Forest` consume the same disciplined feature set?
5. Can alert candidates be explained from actual data and rule context?
6. Does the system remain honest when sources are late, partial, or stale?
7. Can seeded demo data exercise the same ETL contracts as live-source data?
8. Can ops manually feed, replay, and inspect real source ingestion without a bespoke frontend?

---

## Cross-Plan Dependencies

This plan should be referenced by:

- [BACKEND_ML_MODEL_ROADMAP_PLAN.md](/Users/edwininganji/VSCodeProjects/cchis/docs/BACKEND_ML_MODEL_ROADMAP_PLAN.md)
- [DASHBOARD_DECISION_LAYER_IMPLEMENTATION_PLAN.md](/Users/edwininganji/VSCodeProjects/cchis/docs/DASHBOARD_DECISION_LAYER_IMPLEMENTATION_PLAN.md)

The dependency direction is:

- ETL defines trustworthy inputs
- ML consumes ETL outputs and produces predictions
- dashboard consumes prediction and alert outputs honestly

### Execution-order note

Implementation should follow this sequence:

1. `ETL scheduling first`
2. `daily scoring next`
3. `retraining cadence after that`
4. `dashboard consumes only promoted outputs`

This is the guardrail against building polished downstream behavior on top of unstable ingestion or ungoverned model runs.

---

## Self-Critical Audit

Before calling this plan complete, audit it critically against the following questions:

1. Does the plan define enough real source and freshness discipline to support 7-14 day prediction credibly?
2. Does it separate seeded demo data from real-source data honestly enough?
3. Does it make ops input paths concrete enough without inventing a frontend too early?
4. Does it support both `Logistic Regression` and `Random Forest` without flattening their different strengths?
5. Does it define replay, backfill, and fallback behavior well enough for operational use?
6. Does it describe facility-readiness and population-exposure inputs clearly enough to support later forecasting?
7. Does every phase include an explicit close-out expectation with git commit and push discipline?

Any gap found in this audit must be closed in the plan before treating the plan as execution-ready.

---

## Final Note

If the project’s core promise is:

- `predict cholera risk by ward 7 to 14 days early`

then the data backbone must be designed around that exact promise.

That means:

- the right data domains
- the right ingestion cadence
- explicit freshness
- reproducible features
- support for both early-phase models
- and alert generation grounded in traceable prediction logic
