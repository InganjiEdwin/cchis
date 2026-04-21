# CCHIS V1 Backend Future-Readiness Plan

## Purpose

This document defines the strict backend plan for **CCHIS v1** while keeping the long-term CCHIS vision intact.

The goal is not to prematurely build every future feature now. The goal is to make sure **v1 backend decisions do not corner us into expensive rewrites** when CCHIS matures into later versions with:

- richer climate and health data ingestion
- stronger ML and forecasting workflows
- facility readiness forecasting
- CHV mobile applications
- dashboards and analytics
- DHIS2 and external-system interoperability
- multilingual SMS and USSD delivery
- broader geographic scale beyond the initial pilot wards

This plan is grounded in:

- the CCHIS proposal vision and technical direction
- the current repo state as of `2026-04-21`
- the already-completed auth, security, and open-source hardening work

## Immediate Focus

We are focused on **v1 backend** now.

That means:

- stabilizing the backend as the platform backbone
- designing clean seams for later versions
- avoiding shortcuts in API design, data modeling, and async workflows that would require tearing up core systems later

That does **not** mean building the full dashboard, full CHV app, full UNICEF-scale analytics, or advanced spatiotemporal AI immediately.

## Strategic Rule

For v1, every major backend decision must answer this question:

**If CCHIS grows into v2, v3, and beyond, can this decision evolve cleanly without breaking API contracts, rewriting core tables, or re-educating all downstream clients?**

If the answer is no, the design is not acceptable for v1.

## What The Proposal Implies We Must Prepare For

The proposal makes the future system direction clear. Even if v1 only delivers a subset, the backend must be ready to grow toward:

- ward-level and facility-level intelligence
- multiple data sources with provenance and quality differences
- historical monitoring and learning loops
- ML model evolution from simple baseline models to stronger structured and spatial models
- anticipatory action workflows, not just passive analytics
- frontline and low-connectivity delivery channels
- real interoperability with external health systems
- scale across more wards, counties, and potentially countries

Those realities should shape v1 backend design now.

## Current V1 Backend Snapshot

### Strong Foundations Already In Place

- custom user model with roles
- JWT auth, audit events, and admin-only auth event review
- role-based protection for current APIs
- Docker + PostGIS + Redis + Celery baseline
- async task execution for model runs and alert triggering
- public USSD endpoint protected with throttling
- environment-driven security settings
- open-source security and contributor docs
- CI baseline with tests and dependency auditing

### Current Backend Scope

The backend currently handles:

- wards
- CHVs
- risk scores
- alerts
- triage sessions
- offline sync queue records
- USSD session logs
- auth audit events

### Important Reality Check

The backend is already in a **good prototype state**, but it is still **thin as a long-lived platform foundation**.

Several parts are still prototype-grade:

- the domain model is narrow
- the ML/data layer is still mock-heavy
- external-system boundaries are still informal
- API contracts are not versioned
- observability is still light
- interoperability seams are not yet explicit

If we do not address those seams in v1, later versions will force invasive changes.

## Non-Negotiable V1 Design Principles

These are strict. They should guide every backend change from now on.

### 1. API Contracts Must Be Stable

Even if frontend and mobile clients are not mature yet, the backend should behave like clients will soon depend on it.

Implications:

- define backward-compatibility expectations now
- avoid ad hoc response-shape changes
- move toward explicit pagination, filtering, ordering, and schema documentation
- introduce API versioning before the API surface becomes too broad

### 2. Domain Boundaries Must Be Clear

The backend should not keep accumulating everything inside the `risk` app indefinitely.

Implications:

- future concerns should have obvious homes
- app boundaries should reflect domain responsibilities
- business logic should not remain overly concentrated in views or generic services forever

### 3. Data Provenance Must Exist

Future models, dashboards, and operational decisions will require knowing:

- where data came from
- when it was collected
- how it was transformed
- which model version produced which result

If provenance is not designed now, trust and explainability become painful later.

### 4. Async Workflows Must Be Idempotent

SMS sending, USSD callbacks, sync ingestion, and scheduled model jobs must tolerate retries, duplicates, and partial failure.

Prototype shortcuts here become production incidents later.

### 5. Observability Must Be Designed, Not Added Randomly

Logs alone are not enough for a scaling system.

We need to know:

- what happened
- why it happened
- whether it succeeded
- whether it happened twice
- what changed after it happened

### 6. ML Must Be a First-Class Platform Concern

Even if the current model is simple, the system must assume:

- models will change
- features will change
- datasets will change
- evaluation standards will rise

That means the backend must preserve model lineage and data lineage from v1.

### 7. Interoperability Must Be Anticipated Early

The proposal explicitly points toward future integration with systems like DHIS2 and other public-health workflows.

Even if real integration is later, the backend should not be shaped in a way that makes import/export and mapping painful.

## Current V1 Backend Gaps

This is the strict gap list based on the current codebase, not on wishful future scope.

## Gap Group 1: API and Contract Maturity

### Current Gap

There is no explicit API versioning yet.

### Why This Matters Later

As soon as dashboard, mobile, external partners, or DHIS2-like integrations consume the API, unversioned changes become expensive and risky.

### V1 Preparation Required

- introduce API versioning policy now
- decide whether versioning lives in URL namespace, headers, or both
- document compatibility expectations

### Current Gap

List endpoints are not consistently paginated.

### Why This Matters Later

Once data grows across wards, alerts, logs, and audit events, unpaginated endpoints will become operational and client-performance problems.

### V1 Preparation Required

- adopt default pagination in DRF
- standardize filtering and ordering patterns
- document list endpoint conventions

### Current Gap

There is no formal OpenAPI or machine-readable API contract yet.

### Why This Matters Later

Frontend, mobile, and partner integrations will drift if the API contract only lives in code and README prose.

### V1 Preparation Required

- add schema generation
- publish endpoint descriptions and auth expectations
- treat schema changes as compatibility events

## Gap Group 2: Domain Model Readiness

### Current Gap

The backend has `Ward`, `CHV`, `RiskScore`, `Alert`, `TriageSession`, `SyncQueue`, and `UssdSessionLog`, but does not yet model several future-critical entities explicitly.

### Missing Future-Critical Domain Areas

- `HealthFacility`
- facility readiness or stock snapshots
- disease case or surveillance event records
- intervention or response action records
- data source ingestion records
- model run metadata
- feature snapshots or feature provenance
- notification template definitions
- message delivery event history
- geographic hierarchy beyond the current ward-centric structure

### Why This Matters Later

The proposal clearly points toward facility forecasting, preparedness actions, learning loops, and broader system integration. If we keep everything flattened into the current minimal tables, later versions will require schema rewrites instead of additive evolution.

### V1 Preparation Required

- define the future domain map now, even if not all tables are built immediately
- identify which entities must exist in v1 as real models
- identify which entities may remain deferred but require stable extension points

## Gap Group 3: Domain Separation Inside The Codebase

### Current Gap

The `risk` app currently carries too many concerns:

- risk APIs
- alerting
- CHV workflows
- USSD
- sync processing
- ML orchestration

### Why This Matters Later

This is manageable for a prototype, but it will become a maintenance bottleneck as features grow.

### V1 Preparation Required

- define a bounded-context target structure now
- do not rush a giant refactor, but stop deepening the monolith blindly
- create a migration path toward clearer app boundaries such as:
  - `risk`
  - `alerts`
  - `fieldwork`
  - `ingestion`
  - `interoperability`
  - `analytics` or `mlops`

## Gap Group 4: Data Ingestion and Provenance

### Current Gap

Rainfall ingestion is still prototype-oriented and partly relies on hardcoded ward coordinates and fallback static CSV logic.

### Why This Matters Later

The proposal expects multiple data streams and real geospatial inputs. Hardcoded ward coordinates and implicit source fallback are acceptable for a demo, but not as a durable backend contract.

### V1 Preparation Required

- define canonical ingestion source records
- define source priority and fallback policy explicitly
- capture provenance for every ingested or derived record
- plan for real centroid extraction from PostGIS instead of hardcoded coordinate maps

### Current Gap

There is no persistent ingestion-run history yet.

### Why This Matters Later

Without ingestion-run records, we cannot audit:

- what data was fetched
- what failed
- what was skipped
- what source produced downstream predictions

### V1 Preparation Required

- add ingestion run tracking
- record source, timestamp, status, and errors
- preserve enough metadata to support debugging and evaluation

## Gap Group 5: ML and Forecasting Lineage

### Current Gap

The current ML pipeline writes `RiskScore` rows but does not yet persist a full model-run record with training data snapshot, feature set version, evaluation summary, and execution metadata.

### Why This Matters Later

The proposal clearly expects model evolution. If we only keep final `RiskScore` outputs, we lose the lineage needed for:

- reproducibility
- explainability
- rollback
- regulator or stakeholder trust
- model comparison over time

### V1 Preparation Required

- add a `ModelRun` or equivalent table
- tie `RiskScore` rows to model runs
- capture feature schema version
- capture dataset provenance
- capture evaluation metrics
- capture execution metadata and runtime status

### Current Gap

Facility-level surge forecasting is not represented in the current schema or services.

### Why This Matters Later

The proposal includes healthcare readiness and facility burden forecasting as part of the intended system value.

### V1 Preparation Required

- preserve extension space for facility-level predictions now
- avoid assuming ward-level predictions are the only operational forecast object

## Gap Group 6: Alerting and Decision Automation

### Current Gap

Alert lifecycle is still relatively simple.

Today it mostly covers:

- dashboard alerts
- SMS alert send attempts
- basic sent or failed status

### Why This Matters Later

Future versions will need:

- richer trigger rules
- intervention workflows
- delivery retries and backoff policies
- acknowledgements
- escalation paths
- multilingual templates
- community messaging versus CHV messaging versus admin messaging

### V1 Preparation Required

- define alert lifecycle states more explicitly
- separate decision rules from delivery implementation
- introduce template and channel abstraction direction
- preserve room for delivery receipts and acknowledgements

### Current Gap

SMS provider logic is still directly embedded in service code.

### Why This Matters Later

Provider switching, sandbox versus production handling, and channel expansion become harder if provider logic is not isolated behind adapters.

### V1 Preparation Required

- define provider adapter interfaces
- separate message construction from provider transport
- treat Africa’s Talking as one implementation, not the whole abstraction

## Gap Group 7: Field Workflow and Offline Sync Safety

### Current Gap

Offline sync exists, but conflict resolution, deduplication strategy, and idempotent re-submit behavior are still thin.

### Why This Matters Later

Once CHV tools become real devices in the field, retries and duplicate submissions are normal.

### V1 Preparation Required

- define idempotency keys or client submission IDs
- define duplicate-detection policy
- define sync replay behavior
- define failure-recovery semantics

### Current Gap

Triage data is still session-oriented and lightweight, not yet shaped as a broader case-management or surveillance event model.

### Why This Matters Later

If future versions need:

- referral tracking
- follow-up tracking
- household-level outcomes
- surveillance exports

then raw triage sessions alone will be too narrow.

### V1 Preparation Required

- decide whether `TriageSession` remains the durable core record
- or whether future `CaseReport` / `Encounter` / `Referral` entities need to be introduced early

## Gap Group 8: Interoperability and External System Readiness

### Current Gap

There is no explicit interoperability layer yet.

### Why This Matters Later

The proposal calls out modularity and potential integration with systems like DHIS2. That requires more than generic REST endpoints.

### V1 Preparation Required

- define import/export boundaries now
- define canonical internal field names versus external mappings
- avoid hardcoding internal assumptions into future partner payloads
- plan for scheduled exports and import jobs

### Current Gap

There is no mapping framework for code systems, location identifiers, or future facility identifiers.

### Why This Matters Later

Once external data arrives, field mapping chaos becomes a real source of operational bugs.

### V1 Preparation Required

- establish stable identifiers for wards and future facilities
- protect against using display names as long-term integration keys

## Gap Group 9: Observability, Metrics, and Operational Control

### Current Gap

Logging exists, but metrics, tracing, and SLO-oriented visibility are still minimal.

### Why This Matters Later

Later versions will need to answer questions such as:

- how many predictions ran successfully this week
- how many alerts failed by channel
- how many USSD sessions completed
- how long sync processing takes
- what proportion of runs used fallback data

### V1 Preparation Required

- define operational metrics now
- classify which events are logs versus metrics versus audit records
- prepare for Prometheus-style or equivalent metric export later

### Current Gap

There is still no broader domain audit trail outside auth-focused audit events.

### Why This Matters Later

Operational trust will eventually require auditing of:

- model runs
- alert triggers
- manual overrides
- admin intervention actions
- ingestion corrections

### V1 Preparation Required

- define what belongs in auth audit versus domain event audit
- avoid stuffing all future audit needs into the auth event table

## Gap Group 10: Testing and Change Management

### Current Gap

The repo has useful automated tests, but the future-risk areas still need stronger contract and regression coverage.

### Missing Test Categories For Long-Term Maturity

- API contract tests
- migration safety tests
- async/idempotency tests
- provider adapter tests
- ingestion provenance tests
- schema documentation validation

### Why This Matters Later

The more clients and integrations we add, the more change safety depends on contracts, not just behavior seen in a few endpoint tests.

### V1 Preparation Required

- define the backend testing pyramid now
- add contract and migration safety expectations early

## Gap Group 11: Governance, Data Policy, and Multi-Environment Discipline

### Current Gap

The repo has good open-source hardening, but not yet a full backend governance layer for:

- data retention
- retention of logs and audit events
- anonymization or minimization policy for future patient-like records
- environment promotion discipline
- backup and restore policy

### Why This Matters Later

Public-health systems cannot mature safely on ad hoc operational policy.

### V1 Preparation Required

- define retention policy direction now
- define backup and restore expectations now
- define environment separation expectations now
- define what data must never be committed or exported casually

## V1 Must-Prepare Workstreams

These are the workstreams v1 should explicitly prepare now.

## Workstream A: Stable API Foundation

### Required In V1

- API versioning strategy
- default pagination
- standardized filtering and ordering conventions
- machine-readable schema docs
- error response conventions

### Why This Cannot Wait

Once dashboard and mobile work start, API instability gets expensive immediately.

## Workstream B: Future-Ready Domain Map

### Required In V1

- define domain boundaries
- define future entity map
- identify which entities are core now versus deferred
- stop growing `risk` as an everything-app

### Why This Cannot Wait

App and model sprawl are far easier to prevent than to untangle.

## Workstream C: Provenance and Lineage

### Required In V1

- ingestion run tracking
- model run tracking
- source attribution
- feature or input snapshot policy
- stable identifiers for operational entities

### Why This Cannot Wait

Without lineage from the beginning, later ML trust and interoperability become weak.

## Workstream D: Idempotent Async and Delivery Architecture

### Required In V1

- idempotent sync behavior
- idempotent alert dispatch behavior
- explicit retry policy
- provider abstraction seams
- clearer alert lifecycle

### Why This Cannot Wait

Retries and duplicates are normal in production. If they are not designed for now, later fixes will be invasive.

## Workstream E: Interoperability Seams

### Required In V1

- canonical internal identifiers
- mapping strategy for external identifiers
- import/export architecture direction
- payload normalization rules

### Why This Cannot Wait

Future DHIS2 and partner integration should be additive, not a redesign.

## Workstream F: Observability and Operational Trust

### Required In V1

- operational metric inventory
- domain audit inventory
- clear log taxonomy
- incident review inputs

### Why This Cannot Wait

You cannot scale trust in a system you cannot inspect.

## Workstream G: Data Governance and Lifecycle

### Required In V1

- retention policy direction
- backup and restore playbook
- local versus staging versus production expectations
- future privacy posture for sensitive field data

### Why This Cannot Wait

Operational discipline should arrive before scale, not after incidents.

## Strict V1 Build Rules

These are mandatory rules for all upcoming backend work.

### Rule 1

No new list endpoint should be added without:

- pagination
- documented filters
- documented auth expectations

### Rule 2

No new async workflow should be added without:

- idempotency strategy
- retry strategy
- failure logging
- success logging

### Rule 3

No new external integration should be added without:

- adapter abstraction
- config isolation
- test coverage for failure cases

### Rule 4

No model output should be treated as durable intelligence without:

- model version
- run metadata
- source/provenance linkage

### Rule 5

No public endpoint should be added without:

- explicit rationale
- throttling
- abuse assumptions
- documentation update

### Rule 6

No future-facing domain feature should be hacked into the `risk` app blindly if it introduces a new bounded context.

### Rule 7

No identifier used for future integration should depend on mutable display names.

## Proposed Phase Plan

## Phase 0: Lock The V1 Architecture Contract

### Objective

Write down what v1 backend is, what it is not, and which invariants later versions will depend on.

### Deliverables

- explicit v1 backend scope statement
- API versioning decision
- domain-boundary target map
- identifier policy

## Phase 1: Contract Hardening

### Objective

Make the API safe for future clients.

### Deliverables

- pagination
- filter conventions
- ordering conventions
- schema generation
- response and error conventions

## Phase 2: Domain and Model Readiness

### Objective

Prepare the backend schema for additive growth.

### Deliverables

- future entity map
- decision on `HealthFacility`
- decision on case or encounter records
- decision on `ModelRun` and ingestion-run models
- stable keys for wards and future facilities

## Phase 3: Async and Delivery Discipline

### Objective

Ensure retries and duplicates do not corrupt the system.

### Deliverables

- idempotent sync design
- alert delivery lifecycle policy
- adapter boundary for SMS and future channels
- retry and dead-letter direction

## Phase 4: Data Provenance and MLOps Readiness

### Objective

Make the ML and ingestion layers traceable from v1 onward.

### Deliverables

- ingestion run model or equivalent
- model run model or equivalent
- risk score linkage to model runs
- source provenance policy

## Phase 5: Observability and Operational Trust

### Objective

Give maintainers enough visibility to operate the system as it matures.

### Deliverables

- operational metric inventory
- domain audit event inventory
- monitoring dashboard requirements
- backup and restore direction

## Phase 6: Interoperability Readiness

### Objective

Prepare the backend to exchange data with future systems without redesign.

### Deliverables

- canonical internal payload shapes
- mapping strategy for external systems
- export/import integration boundary
- naming and identifier conventions

## V1 Exit Criteria

We should consider the backend **future-ready enough for v1** only when all of the following are true:

- API versioning strategy is defined
- default pagination and schema docs exist
- future entity map is documented
- `ModelRun` / ingestion provenance direction is implemented or explicitly scaffolded
- async workflows have idempotency rules
- provider integrations have abstraction seams
- stable identifiers are defined beyond display names
- observability inventory exists
- backup and restore expectations are documented
- the repo has a clear rule for adding new public endpoints and new integrations

## Recommended Next Patch Sets After This Plan

This is the strict recommended order from the current backend state.

1. API maturity patch set
   Add pagination, filtering conventions, schema generation, and versioning direction.

2. Lineage patch set
   Add ingestion-run and model-run tracking, plus linkage from `RiskScore`.

3. Domain readiness patch set
   Introduce `HealthFacility` and decide the future shape of case or encounter records.

4. Async safety patch set
   Add idempotency strategy for sync and alert workflows, plus provider adapter boundaries.

5. Observability patch set
   Add domain event inventory, metric definitions, and operational runbook direction.

## Final Guidance

The right v1 backend is not the one that tries to build the entire future system now.

The right v1 backend is the one that:

- is disciplined about contracts
- preserves lineage
- respects domain boundaries
- survives retries and integration complexity
- leaves clean extension seams for facilities, forecasting, dashboard, CHV mobile, DHIS2, and stronger ML

That is how CCHIS can mature from v1 to later versions without tearing up its backend foundation.
