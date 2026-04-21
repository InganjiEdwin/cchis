# CCHIS V1 Backend Future-Readiness Execution Plan

## Purpose

This document is the execution tracker for [cchis_v1_backend_future_readiness_plan.md](/Users/edwininganji/VSCodeProjects/cchis/cchis_v1_backend_future_readiness_plan.md).

It translates the future-readiness umbrella tasks into:

- phased implementation slices
- auditable microtasks
- strict completion rules
- clear status tracking

This file is the **working execution plan**.

The architecture plan explains **what must be true**.
This execution plan explains **how we get there without fooling ourselves**.

## Operating Rule

No umbrella task, phase, or microtask is marked `Completed` unless it has passed:

- implementation
- verification
- audit
- documentation update where applicable

If the work exists but has not passed audit, it is **not complete**.

Legacy cleanup is required when a legacy path, alias, field, or flow materially blocks clean progress or truthful architecture.

If a legacy construct adds confusion, dual-maintenance burden, or prevents the repo from matching the intended design, it should be removed instead of preserved by default.

## Status Vocabulary

Use only these statuses:

- `Not Started`
- `In Progress`
- `Blocked`
- `In Audit`
- `Completed`

## Completion Standard

### Microtask Completion Standard

A microtask may be marked `Completed` only when all of the following are true:

1. The code or document change is actually implemented.
2. The intended behavior is verified.
3. Relevant tests or validation commands pass.
4. Negative-path or failure-path behavior has been checked where relevant.
5. A direct audit confirms the implementation matches the plan.
6. Any affected plan/docs are updated.

### Phase Completion Standard

A phase may be marked `Completed` only when:

- every microtask in that phase is `Completed`
- phase-level verification has been run
- no unresolved audit finding remains inside the phase

### Umbrella Completion Standard

An umbrella task may be marked `Completed` only when:

- every phase in the umbrella is `Completed`
- the umbrella-level design intent is actually satisfied
- no follow-up marked as critical remains open

## Audit Checklist Template

Every microtask audit should check:

- implementation audit:
  - is the change actually present in code/docs?
  - is it in the correct architectural location?
- behavior audit:
  - does it do what the phase said it should do?
  - are edge cases handled?
- regression audit:
  - did existing behavior remain safe?
- contract audit:
  - are API shape, permissions, side effects, and naming correct?
- operational audit:
  - are logs, retries, idempotency, and error handling acceptable where relevant?
- documentation audit:
  - were plan/docs/statuses updated?

## Umbrella Status Tracker

| Umbrella | Status | Notes |
| --- | --- | --- |
| Umbrella 1: API Maturity and Contract Stability | Completed | Phases 1.1, 1.2, and 1.3 completed after implementation, verification, and audit. |
| Umbrella 2: Domain and Data Model Readiness | Completed | Phases 2.1, 2.2, and 2.3 completed after entity decisions, stable identifier implementation, and verification. |
| Umbrella 3: Provenance, Ingestion, and MLOps Lineage | Completed | Phases 3.1, 3.2, and 3.3 completed after provenance implementation, dataset-reference direction, and verification. |
| Umbrella 4: Async Safety and Delivery Architecture | Completed | Phases 4.1, 4.2, and 4.3 completed after idempotency, alert lifecycle, provider-boundary implementation, and full audit. |
| Umbrella 5: Interoperability and Identifier Strategy | Completed | Phases 5.1 and 5.2 completed after canonical mapping, crosswalk direction, DHIS2-ready payload stubs, and full audit. |
| Umbrella 6: Observability, Audit, and Operational Trust | Completed | Phases 6.1, 6.2, and 6.3 completed after metric inventory, domain-audit direction, runbook inputs, recovery visibility expectations, and verification. |
| Umbrella 7: Governance, Retention, and Environment Discipline | Completed | Phases 7.1, 7.2, and 7.3 completed after environment discipline, data lifecycle policy, recovery discipline, verification, and audit. |

## Umbrella 1: API Maturity and Contract Stability

### Why This Exists

Future dashboard, mobile, analytics, and partner integrations will depend on stable contracts. If we leave API behavior informal in v1, later versions will pay for it with breaking changes.

### Umbrella Status

Completed

### Phase 1.1: API Contract Baseline

#### Phase Status

Completed

#### Goal

Define the basic contract discipline for list endpoints and response behavior.

#### Microtasks

##### 1.1.1 Add default pagination policy

- Status: `Completed`
- Deliverables:
  - default DRF pagination settings
  - documented page size behavior
  - endpoint behavior verified on current list APIs
- Acceptance Criteria:
  - list endpoints do not return unbounded collections by default
  - pagination behavior is consistent across current list views

##### 1.1.2 Standardize filtering conventions

- Status: `Completed`
- Deliverables:
  - documented filter naming rules
  - consistent query parameter style across current list endpoints
- Acceptance Criteria:
  - filters are predictable
  - inconsistent ad hoc filter names are eliminated or documented

##### 1.1.3 Standardize ordering conventions

- Status: `Completed`
- Deliverables:
  - documented ordering policy
  - explicit default ordering on major list endpoints
- Acceptance Criteria:
  - clients can predict record ordering
  - ordering does not differ silently across similar endpoints

##### 1.1.4 Define error response conventions

- Status: `Completed`
- Deliverables:
  - standard shape for API errors
  - consistent handling for validation, auth, permission, and not-found responses
- Acceptance Criteria:
  - common API errors are structurally predictable

#### Phase Audit Requirements

- verify paginated response shapes
- verify existing clients/tests are updated
- verify no list endpoint remains unbounded without an explicit reason

#### Audit Evidence

- DRF default pagination and exception-handling conventions now live in `backend/core/api.py`.
- Global REST API contract defaults now live in `backend/core/settings.py`, including:
  - `DEFAULT_PAGINATION_CLASS`
  - default page size
  - OpenAPI schema class
  - shared exception handler
- The v1 README contract now documents:
  - pagination response shape
  - filtering conventions
  - ordering conventions
  - error response conventions
- Verification evidence is preserved in `backend/risk/tests.py`, including:
  - `test_paginated_list_endpoints_return_count_and_results`
  - `test_list_endpoint_supports_ordering_parameter`

### Phase 1.2: API Schema and Documentation

#### Phase Status

Completed

#### Goal

Make the API contract machine-readable and easier to evolve safely.

#### Microtasks

##### 1.2.1 Add OpenAPI schema generation

- Status: `Completed`
- Deliverables:
  - schema generation configured
  - schema endpoint or generated artifact available
- Acceptance Criteria:
  - auth and risk endpoints appear in schema output

##### 1.2.2 Document endpoint auth/public expectations

- Status: `Completed`
- Deliverables:
  - schema or docs show auth requirements
  - public endpoint rationale remains explicit
- Acceptance Criteria:
  - public vs protected routes are unambiguous

##### 1.2.3 Document request/response contracts for major endpoints

- Status: `Completed`
- Deliverables:
  - core endpoint contract documentation
  - examples for auth, risks, alerts, CHV sync, and USSD
- Acceptance Criteria:
  - consumers do not need to infer contract shape from source code alone

#### Phase Audit Requirements

- verify schema generation reflects actual behavior
- verify at least one example per major endpoint group

#### Audit Evidence

- The versioned schema endpoint now exists at `GET /api/v1/schema/` through `backend/core/urls.py`.
- Schema routing is isolated through `backend/core/api_v1_schema_urls.py` and `backend/core/api_v1_urls.py`.
- The repo-level API contract documentation in `README.md` now covers:
  - auth routes
  - risk and operational routes
  - CHV sync and triage
  - USSD
  - schema discovery
- Verification evidence is preserved in `backend/risk/tests.py`, including:
  - `test_versioned_schema_endpoint_returns_openapi_document`
  - schema-path checks for auth and USSD routes

### Phase 1.3: Versioning Strategy

#### Phase Status

Completed

#### Goal

Introduce a versioning direction before the API surface grows further.

#### Microtasks

##### 1.3.1 Decide API versioning approach

- Status: `Completed`
- Deliverables:
  - written versioning decision
  - compatibility policy
- Acceptance Criteria:
  - the repo explicitly states how version changes will work

##### 1.3.2 Implement initial versioning structure

- Status: `Completed`
- Deliverables:
  - URL or router structure prepared for versioned APIs
- Acceptance Criteria:
  - future version expansion is additive, not disruptive

##### 1.3.3 Audit current route stability against the versioning decision

- Status: `Completed`
- Deliverables:
  - route inventory
  - migration notes if current routes need compatibility handling
- Acceptance Criteria:
  - we know exactly what contract we are freezing for v1

#### Audit Evidence

- The canonical versioned API routing now exists through:
  - `backend/core/urls.py`
  - `backend/core/api_v1_urls.py`
  - `backend/core/api_v1_schema_urls.py`
- Repo-level documentation now states:
  - `/api/v1/` is the canonical surface
  - unversioned `/api/` routes are intentionally removed
  - breaking changes require a new version path
- Verification evidence is preserved in `backend/risk/tests.py`, including:
  - `test_versioned_routes_are_canonical`
  - explicit assertions that unversioned `/api/wards/` and `/api/auth/login/` return `404`

#### Umbrella 1 Exit Criteria

- pagination exists
- filter and ordering rules exist
- schema generation exists
- versioning direction is explicit
- core API contracts are documented

## Umbrella 2: Domain and Data Model Readiness

### Why This Exists

The current schema is enough for a prototype, but not enough for healthy evolution into facility forecasting, intervention workflows, and broader public-health operations.

### Umbrella Status

Completed

### Phase 2.1: Domain Map Lock

#### Phase Status

Completed

#### Goal

Define the domain map so we stop growing the backend without boundaries.

#### Microtasks

##### 2.1.1 Define bounded-context target map

- Status: `Completed`
- Deliverables:
  - documented target app/domain boundary map
- Acceptance Criteria:
  - new work has a clear domain home

##### 2.1.2 Audit current `risk` app responsibilities

- Status: `Completed`
- Deliverables:
  - inventory of concerns currently living in `risk`
  - recommendation for what stays vs eventually moves
- Acceptance Criteria:
  - we can explain why each major concern is where it is

#### Audit Evidence

- Repo-level domain boundary direction is now documented in:
  - `docs/DOMAIN_BOUNDARIES.md`
  - `README.md`
- The current `risk` app responsibility audit now explicitly distinguishes:
  - what stays in `risk` for v1
  - what is temporarily tolerated
  - what should move to future bounded contexts
- The repo now names future domain homes for geography, surveillance, operations, messaging, integrations, and platform concerns.

### Phase 2.2: Future Entity Readiness

#### Phase Status

Completed

#### Goal

Identify and implement the minimum future-critical entities that should not be deferred.

#### Microtasks

##### 2.2.1 Decide `HealthFacility` introduction strategy

- Status: `Completed`
- Deliverables:
  - yes/no decision for v1
  - schema draft if yes
  - documented defer rationale if no
- Acceptance Criteria:
  - facility forecasting is not left architecturally vague

##### 2.2.2 Decide case or encounter model direction

- Status: `Completed`
- Deliverables:
  - decision on whether `TriageSession` is sufficient
  - future record model direction for case/referral tracking
- Acceptance Criteria:
  - we know how v2+ case workflows will grow from v1

##### 2.2.3 Define intervention/action record direction

- Status: `Completed`
- Deliverables:
  - future design note for response actions and preparedness interventions
- Acceptance Criteria:
  - alerts are not the only future operational object in the design

#### Audit Evidence

- `HealthFacility` is now implemented in `backend/risk/models.py` and exposed in admin/serialization paths.
- Future entity direction is now documented in:
  - `docs/FUTURE_ENTITY_DECISIONS.md`
  - `docs/DOMAIN_BOUNDARIES.md`
  - `README.md`
- The repo now explicitly records that:
  - `TriageSession` is a v1 encounter/decision-support record, not the full future case model
  - alerts are not the long-term intervention or preparedness action model

### Phase 2.3: Stable Identifier Policy

#### Phase Status

Completed

#### Goal

Ensure future integrations do not depend on mutable names.

#### Microtasks

##### 2.3.1 Define canonical ward identifier strategy

- Status: `Completed`
- Deliverables:
  - stable identifier policy for wards
- Acceptance Criteria:
  - display names are not treated as permanent external keys

##### 2.3.2 Define future facility and partner identifier direction

- Status: `Completed`
- Deliverables:
  - identifier policy for future facilities and external mappings
- Acceptance Criteria:
  - identifier strategy exists before interoperability work expands

#### Audit Evidence

- Immutable `public_id` fields now exist on `Ward` and `HealthFacility` in `backend/risk/models.py`.
- Identifier direction is documented in:
  - `docs/IDENTIFIER_POLICY.md`
  - `README.md`
- Verification evidence is preserved in `backend/risk/tests.py`, including:
  - `test_ward_and_facility_receive_public_ids`
  - canonical and mapping tests that use immutable identifiers instead of names

#### Umbrella 2 Exit Criteria

- target domain map exists
- current schema growth path is documented
- future-critical entities have explicit decisions
- stable identifier policy exists

## Umbrella 3: Provenance, Ingestion, and MLOps Lineage

### Why This Exists

The proposal clearly depends on trusted data inputs and evolving models. Without lineage, later versions will not be reproducible or explainable.

### Umbrella Status

Completed

### Phase 3.1: Ingestion Provenance

#### Phase Status

Completed

#### Goal

Track what data entered the system and how.

#### Microtasks

##### 3.1.1 Add ingestion run model or equivalent

- Status: `Completed`
- Deliverables:
  - ingestion run persistence
  - source, status, timestamps, and errors captured
- Acceptance Criteria:
  - data fetch and fallback behavior is auditable

##### 3.1.2 Define source priority and fallback policy

- Status: `Completed`
- Deliverables:
  - documented source hierarchy
  - fallback semantics in code/docs
- Acceptance Criteria:
  - fallback is explicit, not hidden behavior

##### 3.1.3 Replace hardcoded ward coordinate assumptions with a clear migration path

- Status: `Completed`
- Deliverables:
  - plan or implementation for PostGIS-derived coordinates
- Acceptance Criteria:
  - hardcoded geography does not remain the silent long-term assumption

#### Audit Evidence

- Rainfall ingestion provenance now persists through `IngestionRun` in `backend/risk/models.py`.
- Ingestion policy and fallback direction are documented in `docs/INGESTION_PROVENANCE.md` and summarized in `README.md`.
- Verification evidence is preserved in `backend/risk/tests.py`, including:
  - `test_fetch_rainfall_for_known_ward_uses_live_source_when_available`
  - `test_fetch_rainfall_falls_back_to_static`
  - `test_fetch_rainfall_prefers_ward_centroid_when_available`

### Phase 3.2: Model Run Lineage

#### Phase Status

Completed

#### Goal

Track what produced each prediction.

#### Microtasks

##### 3.2.1 Add `ModelRun` model or equivalent

- Status: `Completed`
- Deliverables:
  - model run persistence
  - model version, execution metadata, status
- Acceptance Criteria:
  - predictions can be traced to a specific run

##### 3.2.2 Link `RiskScore` to model runs

- Status: `Completed`
- Deliverables:
  - lineage link from predictions to run metadata
- Acceptance Criteria:
  - no model-generated risk score exists without source lineage

##### 3.2.3 Capture evaluation and feature metadata direction

- Status: `Completed`
- Deliverables:
  - decision on evaluation metric persistence
  - feature schema version direction
- Acceptance Criteria:
  - future model comparison is architecturally supported

#### Audit Evidence

- Model execution lineage now persists through `ModelRun` in `backend/risk/models.py`.
- `RiskScore` now links to `ModelRun`, preserving run-level lineage for model-generated predictions.
- Model-lineage direction is documented in:
  - `docs/MODEL_LINEAGE.md`
  - `README.md`
- Verification evidence is preserved in `backend/risk/tests.py`, including:
  - `test_run_risk_model_creates_scores`
  - `test_seed_demo_data_assigns_model_run_to_seeded_model_scores`

### Phase 3.3: Feature and Dataset Readiness

#### Phase Status

Completed

#### Goal

Prepare for more serious ML inputs without building a full feature store prematurely.

#### Microtasks

##### 3.3.1 Define feature provenance policy

- Status: `Completed`
- Deliverables:
  - documented policy for derived feature traceability
- Acceptance Criteria:
  - key prediction inputs can be explained later

##### 3.3.2 Define dataset versioning direction

- Status: `Completed`
- Deliverables:
  - documented approach to dataset snapshots or references
- Acceptance Criteria:
  - training and inference datasets are not conceptually invisible

#### Audit Evidence

- `ModelRun` now carries lightweight feature and dataset provenance fields, including:
  - `feature_schema_version`
  - `feature_keys`
  - `training_dataset_ref`
  - `inference_dataset_ref`
- Feature and dataset provenance direction is documented in:
  - `docs/FEATURE_AND_DATASET_PROVENANCE.md`
  - `README.md`
- Verification evidence is preserved in `backend/risk/tests.py`, including assertions on stored schema-version and dataset-reference fields in `test_run_risk_model_creates_scores`

#### Umbrella 3 Exit Criteria

- ingestion run tracking exists
- model run tracking exists
- `RiskScore` lineage exists
- source and feature provenance direction is explicit

## Umbrella 4: Async Safety and Delivery Architecture

### Why This Exists

Retries, duplicate requests, and delayed connectivity are normal, not edge cases.

### Umbrella Status

Completed

### Phase 4.1: Sync Idempotency and Replay Safety

#### Phase Status

Completed

#### Goal

Make CHV sync behavior safe under retries and duplicates.

#### Microtasks

##### 4.1.1 Define client submission identity strategy

- Status: `Completed`
- Deliverables:
  - idempotency key or submission ID direction
- Acceptance Criteria:
  - duplicate sync submissions can be detected reliably

##### 4.1.2 Define duplicate handling behavior

- Status: `Completed`
- Deliverables:
  - duplicate policy
  - replay semantics
- Acceptance Criteria:
  - retries do not silently create ambiguous duplicates

##### 4.1.3 Add sync idempotency tests

- Status: `Completed`
- Deliverables:
  - test coverage for replay and duplicate scenarios
- Acceptance Criteria:
  - duplicate behavior is verified, not assumed

#### Audit Evidence

- `SyncQueue` now stores `client_submission_id` plus a `triage_session` link, and enforces uniqueness on `source_device_id + client_submission_id`.
- Legacy local rows were backfilled safely via `risk.0007_syncqueue_idempotency` before the uniqueness constraint was applied.
- Replay semantics were verified with duplicate-submission and duplicate-in-request tests.
- Verification completed with:
  - `docker compose exec backend python manage.py makemigrations --check`
  - `docker compose exec backend python manage.py migrate`
  - `docker compose exec backend python manage.py test --noinput`
  - `docker compose exec backend python manage.py test risk.tests.RiskPermissionsTestCase.test_chv_sync_replays_duplicate_submission_without_creating_duplicates risk.tests.RiskPermissionsTestCase.test_chv_sync_requires_unique_submission_ids_within_request --noinput`

### Phase 4.2: Alert Lifecycle Maturity

#### Phase Status

Completed

#### Goal

Move alerts from basic event records toward a real delivery workflow.

#### Microtasks

##### 4.2.1 Define alert lifecycle states

- Status: `Completed`
- Deliverables:
  - lifecycle state model
- Acceptance Criteria:
  - alert delivery flow is richer than pending/sent/failed alone if needed

##### 4.2.2 Separate trigger logic from delivery transport direction

- Status: `Completed`
- Deliverables:
  - documented rule-vs-delivery architecture
- Acceptance Criteria:
  - alert decision rules are not tightly bound to one channel implementation

##### 4.2.3 Add retry and failure policy for alert delivery

- Status: `Completed`
- Deliverables:
  - delivery retry policy
  - failure handling policy
- Acceptance Criteria:
  - retries are intentional and observable

#### Audit Evidence

- `Alert` now tracks `QUEUED`, `RETRY_PENDING`, `DELIVERED`, and `FAILED` states instead of a flat pending/sent/failed flow.
- Delivery metadata is now stored on each alert: backend, attempt count, max attempts, last attempted time, and next retry time.
- Alert creation and transport were separated:
  - `create_alerts_for_riskscore(...)` persists alert records
  - `deliver_alert(...)` performs transport for one alert
  - `deliver_alert_task` schedules retries for retryable SMS failures
- Existing alert rows are normalized by migration `risk.0008_alert_attempt_count_alert_delivery_backend_and_more`.
- Architecture notes were documented in `docs/ALERT_DELIVERY_ARCHITECTURE.md`.
- Verification completed with:
  - `python3 -m compileall backend/risk`
  - `docker compose exec backend python manage.py migrate`
  - `docker compose exec backend python manage.py test risk.tests.RiskPermissionsTestCase.test_create_alerts_for_riskscore_creates_dashboard_and_queued_sms_alerts risk.tests.RiskPermissionsTestCase.test_deliver_alert_marks_sms_delivered_on_success risk.tests.RiskPermissionsTestCase.test_deliver_alert_marks_retry_pending_before_max_attempts risk.tests.RiskPermissionsTestCase.test_deliver_alert_task_marks_failed_when_max_attempts_reached risk.tests.RiskPermissionsTestCase.test_trigger_alerts_task_queues_delivery_for_sms_alerts --noinput`
  - `docker compose exec backend python manage.py test --noinput`

### Phase 4.3: Provider Adapter Boundaries

#### Phase Status

Completed

#### Goal

Keep Africa’s Talking from becoming the architecture.

#### Microtasks

##### 4.3.1 Introduce provider adapter interface

- Status: `Completed`
- Deliverables:
  - adapter abstraction for messaging providers
- Acceptance Criteria:
  - provider-specific code is no longer the only shape of messaging logic

##### 4.3.2 Separate message construction from transport

- Status: `Completed`
- Deliverables:
  - message-building layer
  - transport layer
- Acceptance Criteria:
  - content logic and delivery logic are independently evolvable

#### Audit Evidence

- SMS provider resolution now happens through `risk.providers.get_sms_provider(...)`.
- Provider-specific transport code was extracted into `risk/providers.py`.
- The alert workflow no longer embeds Africa's Talking request logic directly inside the alert rule and retry path.
- `send_sms(...)` now delegates to a provider adapter and returns a typed delivery result.
- `create_alerts_for_riskscore(...)` continues to own message construction while `deliver_alert(...)` owns transport execution.
- Environment configuration now exposes `SMS_PROVIDER` explicitly in `.env.example`.
- Alert delivery architecture docs were updated to describe the adapter seam and supported v1 providers.
- Verification completed with:
  - `python3 -m compileall backend/risk`
  - `docker compose exec backend python manage.py test risk.tests.RiskPermissionsTestCase.test_create_alerts_for_riskscore_creates_dashboard_and_queued_sms_alerts risk.tests.RiskPermissionsTestCase.test_deliver_alert_marks_sms_delivered_on_success risk.tests.RiskPermissionsTestCase.test_deliver_alert_marks_retry_pending_before_max_attempts risk.tests.RiskPermissionsTestCase.test_deliver_alert_task_marks_failed_when_max_attempts_reached risk.tests.RiskPermissionsTestCase.test_get_sms_provider_defaults_to_stub risk.tests.RiskPermissionsTestCase.test_get_sms_provider_raises_for_unknown_provider risk.tests.RiskPermissionsTestCase.test_trigger_alerts_task_queues_delivery_for_sms_alerts --noinput`
  - `docker compose exec backend python manage.py test --noinput`

#### Umbrella 4 Exit Criteria

- sync idempotency strategy exists
- alert retry behavior exists
- provider abstraction seam exists

## Umbrella 5: Interoperability and Identifier Strategy

### Why This Exists

The proposal points toward DHIS2 and broader partner-system integration. That requires intentional seams, not generic hope.

### Umbrella Status

Completed

### Phase 5.1: Internal Canonical Model Mapping

#### Phase Status

Completed

#### Goal

Define stable internal names and shapes before partner mappings arrive.

#### Microtasks

##### 5.1.1 Define canonical internal entity naming policy

- Status: `Completed`
- Deliverables:
  - naming conventions for internal system objects
- Acceptance Criteria:
  - future mapping work has a stable target

##### 5.1.2 Define export/import boundary direction

- Status: `Completed`
- Deliverables:
  - integration boundary design note
- Acceptance Criteria:
  - interoperability has an explicit architectural home

#### Audit Evidence

- Canonical internal mapping objects now exist in `backend/risk/canonical.py`.
- Stable canonical shapes were defined for:
  - ward references
  - facility references
  - risk score records
  - alert records
- Canonical export envelopes now carry:
  - `source_system`
  - `entity_name`
  - `schema_version`
  - canonical record content
- The import and export architectural boundary was documented in `docs/INTEROPERABILITY_BOUNDARY.md`.
- The boundary direction now explicitly requires partner-specific translation to happen outside core domain models.
- Verification completed with:
  - `python3 -m compileall backend/risk`
  - `docker compose exec backend python manage.py test risk.tests.IdentifierPolicyTestCase.test_ward_and_facility_receive_public_ids risk.tests.IdentifierPolicyTestCase.test_ward_maps_to_canonical_reference risk.tests.IdentifierPolicyTestCase.test_facility_maps_to_canonical_reference risk.tests.IdentifierPolicyTestCase.test_riskscore_maps_to_canonical_record risk.tests.IdentifierPolicyTestCase.test_alert_maps_to_canonical_record risk.tests.IdentifierPolicyTestCase.test_canonical_export_envelope_wraps_internal_record --noinput`
  - `docker compose exec backend python manage.py test --noinput`

### Phase 5.2: External Mapping Readiness

#### Phase Status

Completed

#### Goal

Prepare for external code systems and location mappings.

#### Microtasks

##### 5.2.1 Define location mapping strategy

- Status: `Completed`
- Deliverables:
  - ward and future facility mapping policy
- Acceptance Criteria:
  - external system mapping does not depend on mutable labels

##### 5.2.2 Define future DHIS2-ready payload direction

- Status: `Completed`
- Deliverables:
  - data exchange direction note
- Acceptance Criteria:
  - external reporting/export shape is anticipated early

#### Audit Evidence

- Stable location crosswalk helpers now exist in `backend/risk/interoperability.py`.
- The location mapping direction explicitly anchors mappings to:
  - immutable CCHIS identifiers
  - operational reference codes
  - never mutable labels
- DHIS2-ready export stub helpers now exist for:
  - org-unit mapping records
  - risk score export payloads built from canonical records
- External mapping and DHIS2 direction were documented in `docs/EXTERNAL_MAPPING_AND_DHIS2_DIRECTION.md`.
- Verification completed with:
  - `python3 -m compileall backend/risk`
  - `docker compose exec backend python manage.py test risk.tests.IdentifierPolicyTestCase.test_ward_location_crosswalk_uses_stable_identifiers risk.tests.IdentifierPolicyTestCase.test_facility_location_crosswalk_uses_stable_identifiers risk.tests.IdentifierPolicyTestCase.test_dhis2_org_unit_mapping_stub_uses_crosswalk_inputs risk.tests.IdentifierPolicyTestCase.test_dhis2_risk_score_export_stub_uses_canonical_record --noinput`
  - `docker compose exec backend python manage.py test --noinput`

#### Umbrella 5 Exit Criteria

- canonical identifier and mapping direction exists
- interoperability boundary is documented

## Umbrella 6: Observability, Audit, and Operational Trust

### Why This Exists

We need to operate the platform we are building, not just run it once in demos.

### Umbrella Status

Completed

### Phase 6.1: Operational Metrics Inventory

#### Phase Status

Completed

#### Goal

Define what should be measured, not just logged.

#### Microtasks

##### 6.1.1 Define key backend operational metrics

- Status: `Completed`
- Deliverables:
  - metric inventory for predictions, alerts, sync, USSD, and auth
- Acceptance Criteria:
  - maintainers know what should be graphed and monitored

##### 6.1.2 Classify log vs metric vs audit event boundaries

- Status: `Completed`
- Deliverables:
  - event taxonomy
- Acceptance Criteria:
  - operational visibility layers are not conceptually mixed together

#### Audit Evidence

- Operational metric inventory now exists in `backend/core/observability.py`.
- The inventory covers:
  - API
  - auth
  - sync
  - triage
  - USSD
  - forecasting
  - alerts
- Event classification now explicitly distinguishes:
  - log
  - metric
  - audit event
- Observability direction and taxonomy were documented in `docs/OPERATIONAL_METRICS_AND_EVENT_TAXONOMY.md`.
- Verification completed with:
  - `python3 -m compileall backend/core backend/risk`
  - `docker compose exec backend python manage.py test risk.tests.ObservabilityInventoryTestCase.test_operational_metric_inventory_covers_core_domains risk.tests.ObservabilityInventoryTestCase.test_event_taxonomy_distinguishes_logs_metrics_and_audit_events risk.tests.ObservabilityInventoryTestCase.test_auth_audit_event_is_marked_durable --noinput`
  - `docker compose exec backend python manage.py test --noinput`

### Phase 6.2: Domain Audit Readiness

#### Phase Status

Completed

#### Goal

Extend audit thinking beyond auth.

#### Microtasks

##### 6.2.1 Define domain audit inventory

- Status: `Completed`
- Deliverables:
  - list of non-auth actions that require durable auditing
- Acceptance Criteria:
  - future operationally significant actions have audit direction

##### 6.2.2 Define manual override and intervention audit direction

- Status: `Completed`
- Deliverables:
  - audit policy for future manual changes and interventions
- Acceptance Criteria:
  - admin and operational overrides are not left unaudited by design

#### Audit Evidence

- Domain audit inventory now exists in `backend/core/observability.py` as `DOMAIN_AUDIT_INVENTORY`.
- The inventory explicitly covers future non-auth durable audit needs across:
  - forecasting
  - operations
  - messaging
  - surveillance
- Manual overrides and future intervention state changes now have explicit audit-direction rules for:
  - actor attribution
  - required reason capture
  - minimum metadata
  - before/after state context where relevant
- Domain audit readiness and policy boundaries were documented in `docs/DOMAIN_AUDIT_READINESS.md`.
- `README.md` now points to the non-auth domain audit direction so repo-level guidance stays discoverable.
- Verification completed with:
  - `python3 -m compileall backend/core backend/risk`
  - `docker compose exec backend python manage.py test risk.tests.ObservabilityInventoryTestCase.test_domain_audit_inventory_covers_future_non_auth_operational_actions risk.tests.ObservabilityInventoryTestCase.test_manual_override_audit_inventory_requires_actor_reason_and_minimum_metadata --noinput`
  - `docker compose exec backend python manage.py test --noinput`

### Phase 6.3: Runbook and Recovery Inputs

#### Phase Status

Completed

#### Goal

Make incidents diagnosable.

#### Microtasks

##### 6.3.1 Define minimum operational runbook inputs

- Status: `Completed`
- Deliverables:
  - list of logs, events, and metrics needed during incidents
- Acceptance Criteria:
  - incident review inputs are known in advance

##### 6.3.2 Define backup and restore visibility expectations

- Status: `Completed`
- Deliverables:
  - operational visibility requirements for recovery workflows
- Acceptance Criteria:
  - restoreability is not treated as an afterthought

#### Audit Evidence

- Minimum incident-review inputs now exist in `backend/core/observability.py` as `MINIMUM_RUNBOOK_INPUTS`.
- The runbook input inventory explicitly covers:
  - API request traces
  - auth audit review inputs
  - sync, triage, and USSD diagnostics
  - ingestion and model-run diagnostics
  - alert delivery state and retry visibility
  - future manual-action accountability context
- Backup and restore visibility expectations now exist in `backend/core/observability.py` as `RECOVERY_VISIBILITY_REQUIREMENTS`.
- Recovery visibility direction explicitly requires evidence for:
  - backup execution
  - restore execution
  - post-restore validation
  - restore rehearsal
- Runbook and recovery-input policy was documented in `docs/OPERATIONAL_RUNBOOK_AND_RECOVERY_INPUTS.md`.
- `README.md` now points to the operational runbook direction so repo-level guidance remains discoverable.
- Verification completed with:
  - `python3 -m compileall backend/core backend/risk`
  - `docker compose exec backend python manage.py test risk.tests.ObservabilityInventoryTestCase.test_runbook_input_inventory_covers_core_incident_domains risk.tests.ObservabilityInventoryTestCase.test_recovery_visibility_expectations_cover_backup_restore_and_validation --noinput`
  - `docker compose exec backend python manage.py test --noinput`

#### Umbrella 6 Exit Criteria

- operational metric inventory exists
- audit-event scope extends beyond auth in design
- runbook inputs are documented

## Umbrella 7: Governance, Retention, and Environment Discipline

### Why This Exists

If CCHIS becomes a real operating system for public-health action, data lifecycle and environment discipline cannot stay informal.

### Umbrella Status

Completed

### Phase 7.1: Environment Discipline

#### Phase Status

Completed

#### Goal

Define how local, staging, and production-like environments must differ.

#### Microtasks

##### 7.1.1 Define environment promotion expectations

- Status: `Completed`
- Deliverables:
  - local/staging/production configuration discipline
- Acceptance Criteria:
  - deployer assumptions are not left informal

##### 7.1.2 Define migration and seed policy by environment

- Status: `Completed`
- Deliverables:
  - environment-specific migration and seeding rules
- Acceptance Criteria:
  - demo seeding does not leak into operational environments by habit

#### Audit Evidence

- `backend/core/settings.py` now defines explicit `CCHIS_ENVIRONMENT` handling with allowed values `local`, `staging`, and `production`.
- `backend/risk/management/commands/seed_demo_data.py` now blocks non-local demo seeding unless `SEED_ALLOW_NON_LOCAL=True` is set intentionally.
- `docs/ENVIRONMENT_DISCIPLINE.md` now documents:
  - local, staging, and production promotion expectations
  - migration rules by environment
  - demo seeding policy and its explicit non-local override
- `README.md` now documents the environment label, deployment expectations, and the non-local seeding guard.
- `SECURITY.md` now includes the explicit environment label and shared-environment seeding restriction in the deployment checklist.
- Verification completed with:
  - `python3 -m compileall backend/core backend/risk`
  - `docker compose exec backend python manage.py test risk.tests.SeedAndModelCommandTestCase.test_seed_demo_data_command_blocks_non_local_environment_by_default risk.tests.SeedAndModelCommandTestCase.test_seed_demo_data_command_can_run_in_non_local_environment_with_explicit_override --noinput`

### Phase 7.2: Data Lifecycle Policy

#### Phase Status

Completed

#### Goal

Set direction for retention and sensitive data handling before more field data accumulates.

#### Microtasks

##### 7.2.1 Define retention policy direction

- Status: `Completed`
- Deliverables:
  - retention direction for logs, audit events, sync data, and future case data
- Acceptance Criteria:
  - storage growth and data sensitivity are acknowledged early

##### 7.2.2 Define data minimization direction for future field records

- Status: `Completed`
- Deliverables:
  - minimization and privacy direction note
- Acceptance Criteria:
  - future patient-like or household-linked records have guardrails early

#### Audit Evidence

- `backend/core/data_lifecycle.py` now defines code-level inventories for:
  - retention direction across current record families
  - field-data minimization rules for future sensitive records
- The retention inventory now explicitly covers:
  - request trace logs
  - auth audit events
  - USSD session logs
  - sync queue payloads
  - triage sessions
  - alerts
  - ingestion/model provenance
- `docs/DATA_LIFECYCLE_POLICY.md` now documents:
  - retention classes and expectations
  - minimization direction for future field records
  - the boundary between bounded operational history and durable provenance
- `README.md` now links the repo’s data lifecycle direction.
- `SECURITY.md` now requires retention/minimization thinking before expanding patient-like or household-linked records.
- Verification completed with:
  - `python3 -m compileall backend/core`
  - `docker compose exec backend python manage.py test risk.tests.DataLifecyclePolicyTestCase --noinput`

### Phase 7.3: Backup and Restore Discipline

#### Phase Status

Completed

#### Goal

Ensure recoverability becomes a design expectation, not emergency improvisation.

#### Microtasks

##### 7.3.1 Define backup expectations

- Status: `Completed`
- Deliverables:
  - minimum backup expectations
- Acceptance Criteria:
  - backups are not treated as opaque artifacts

##### 7.3.2 Define restore verification expectations

- Status: `Completed`
- Deliverables:
  - minimum restore verification expectations
- Acceptance Criteria:
  - restore success is not claimed without explicit validation

#### Audit Evidence

- `backend/core/recovery_discipline.py` now defines code-level expectations for:
  - backup evidence requirements
  - restore execution evidence requirements
  - post-restore validation requirements
  - shared-environment recovery rehearsal expectations
- `docs/BACKUP_AND_RESTORE_DISCIPLINE.md` now documents:
  - minimum backup evidence
  - minimum restore evidence
  - post-restore validation rules
  - a practical rehearsal checklist
- `README.md` now links the repo’s backup and restore discipline.
- `SECURITY.md` now marks backup and restore workflows as security-sensitive operational paths.
- Verification completed with:
  - `python3 -m compileall backend/core`
  - `docker compose exec backend python manage.py test risk.tests.RecoveryDisciplineTestCase --noinput`

#### Umbrella 7 Exit Criteria

- environment expectations are explicit
- retention direction exists
- backup and restore direction exists

## Recommended Execution Order

This is the recommended order for actual implementation work:

1. Umbrella 1: API Maturity and Contract Stability
2. Umbrella 3: Provenance, Ingestion, and MLOps Lineage
3. Umbrella 2: Domain and Data Model Readiness
4. Umbrella 4: Async Safety and Delivery Architecture
5. Umbrella 6: Observability, Audit, and Operational Trust
6. Umbrella 5: Interoperability and Identifier Strategy
7. Umbrella 7: Governance, Retention, and Environment Discipline

## First Recommended Active Slice

The best first active slice is:

- Umbrella 1
- Phase 1.1
- Microtasks 1.1.1 to 1.1.4

Reason:

- API maturity affects every future client
- the current backend already has enough routes to justify contract hardening
- this work is foundational but still contained

## Plan Update Rule

As we execute:

- update microtask status first
- update phase status second
- update umbrella status last
- never mark a parent `Completed` before all children are complete
- if audit fails, move the item back from `In Audit` to `In Progress`

## Final Discipline Rule

The plan is only useful if it stays honest.

That means:

- we do not mark work complete because “it mostly works”
- we do not mark work complete because “tests probably cover it”
- we do not mark work complete because “the architecture intent seems fine”

We mark work complete only after a **true and thorough successful audit**.
