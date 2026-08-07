# Child-Centered Climate Health Intelligence System (CCHIS)

CCHIS is an open-source, AI-assisted public health platform focused on predicting flood-driven cholera risk and enabling early, coordinated response in climate-vulnerable communities.

This repository currently contains the backend foundation for that platform: authenticated APIs, risk data workflows, async processing, CHV support endpoints, and low-connectivity access patterns.

## Safety and evidence documentation

The implementation is decision-support software, not a diagnostic or autonomous public-health authority. Read [MODEL_CARD.md](MODEL_CARD.md) for model scope, evaluation limits, truth gates, and human oversight; [DATASET_CARD.md](DATASET_CARD.md) for source provenance, privacy, proxy, freshness, and production-eligibility contracts; and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for community expectations. Security reports belong in [SECURITY.md](SECURITY.md), not public issues.

## Why This Matters

Flood-prone regions such as Migori County in Kenya face recurring cholera outbreaks driven by climate variability and extreme weather events. In many settings, response systems are still reactive, fragmented, and slow to act.

CCHIS is designed to shift that workflow from reaction to prediction to early action, with particular attention to children under five and other vulnerable populations.

## What CCHIS Does

CCHIS turns climate, environmental, and health data into localized operational intelligence.

Current and planned capabilities include:

- ward-level cholera risk prediction and storage
- automated early warning and alert workflows
- CHV triage and offline sync support
- USSD handling for low-connectivity and feature-phone flows
- role-based operational APIs for supervisors, analysts, and admins
- auditability and abuse controls around auth and public endpoints

## Current Backend Capabilities

- ward-level cholera risk score storage and retrieval
- async alert triggering with Celery and Redis
- CHV triage and offline sync endpoints
- USSD session handling and logging
- JWT authentication with role-based API permissions
- DB-backed auth audit events for key account actions
- scoped API throttling for auth endpoints and public USSD callbacks
- Docker-first local development with PostGIS and Redis

## System Architecture

At a high level, CCHIS follows this flow:

```text
Data Sources -> ETL / Ingestion -> Feature Engineering -> ML Prediction -> Decision Engine -> Alerts and Interfaces
```

Core layers:

- Data layer: rainfall, flood proxy signals, historical cholera data, and geospatial context
- AI prediction layer: risk classification and scoring models
- Action layer: alerting, trigger rules, and recommended interventions
- User layer: CHV workflows, USSD access, dashboards, and messaging channels

## Machine Learning Direction

Initial MVP model direction:

- Logistic Regression for interpretable baseline risk prediction
- Random Forest for nonlinear benchmark comparisons

Feature areas:

- rainfall accumulation across short windows
- rainfall anomalies
- flood indicators
- historical cholera incidence
- seasonality
- spatial relationships between wards

Planned evolution:

- Gradient Boosting such as XGBoost or LightGBM
- time-series forecasting models
- spatiotemporal approaches
- Bayesian methods for uncertainty-aware forecasting

## Local Stack

- Django
- Django REST Framework
- PostgreSQL + PostGIS
- Celery + Redis
- Docker Compose

## Supported Tooling Baseline

- Python `3.12`
- Docker Engine with Docker Compose v2
- PostgreSQL `16` with PostGIS `3.4`
- Redis `7`

The backend image and local development flow are currently aligned to these versions. If you change them, update the Docker image, dependency policy, and CI workflow together so contributors are not debugging mismatched environments.

## Authentication

The backend uses JWT authentication via `djangorestframework-simplejwt`.

Auth endpoints:

- `POST /api/v1/auth/login/`
- `POST /api/v1/auth/verify-2fa/`
- `POST /api/v1/auth/step-up/verify/`
- `POST /api/v1/auth/2fa/setup/`
- `POST /api/v1/auth/2fa/setup/confirm/`
- `POST /api/v1/auth/refresh/`
- `GET /api/v1/auth/session/`
- `POST /api/v1/auth/logout/`
- `POST /api/v1/auth/change-password/`
- `GET /api/v1/auth/me/`
- `POST /api/v1/auth/password-reset/request/`
- `POST /api/v1/auth/password-reset/confirm/`
- `POST /api/v1/auth/access/request/`
- `GET /api/v1/auth/access/request/options/`
- `GET /api/v1/auth/access/requests/`
- `POST /api/v1/auth/access/requests/<id>/approve/`
- `POST /api/v1/auth/access/requests/<id>/reject/`
- `POST /api/v1/auth/register/` for admin-controlled user creation
- `POST /api/v1/auth/users/<id>/deactivate/` for admin-controlled deactivation
- `POST /api/v1/auth/users/<id>/reactivate/` for admin-controlled reactivation
- `GET /api/v1/auth/audit-events/` for admin-only auth audit review
- `GET /api/v1/auth/audit-events/summary/` for admin-only auth event aggregation

Most API endpoints are protected. The deliberate public exceptions are limited to authentication/bootstrap flows, the machine-readable schema, and the USSD callback endpoint. Every operational route still requires authentication plus backend role and scope checks.

For abuse monitoring, the most important auth events currently captured are login success or failure, refresh success or failure, logout attempts, password changes, user creation, and user activation changes.

## Public Endpoint Policy

The backend is intentionally private-by-default. If an endpoint is not documented here as public, contributors should assume it requires authentication and role checks.

Current intentionally public endpoints:

- `POST /api/v1/auth/login/`
- `POST /api/v1/auth/verify-2fa/`
- `POST /api/v1/auth/refresh/`
- `GET /api/v1/auth/session/`
- `POST /api/v1/auth/2fa/setup/`
- `POST /api/v1/auth/2fa/setup/confirm/`
- `POST /api/v1/auth/password-reset/request/`
- `POST /api/v1/auth/password-reset/confirm/`
- `POST /api/v1/auth/access/request/`
- `GET /api/v1/auth/access/request/options/`
- `GET /api/v1/schema/`
- `POST /api/v1/ussd/menu/`

Why these are public:

- auth bootstrap and recovery endpoints must be reachable before a user has a session
- the schema endpoint lets client developers inspect the contract, but schema visibility does not grant route access
- it supports provider-initiated USSD callbacks
- it enables low-connectivity access patterns for feature-phone users
- public endpoints are rate-limited or otherwise abuse-controlled because they are part of the unauthenticated surface

If you introduce a new public endpoint, document the rationale, abuse controls, and expected deployment assumptions in both `README.md` and `SECURITY.md`.

## Authorization And Role Contract

Backend authorization is the source of truth. Frontend route gates, hidden buttons, and disabled controls are UX affordances only; direct API calls must still be rejected by backend permission classes, object-scope filters, and step-up checks.

`GET /api/v1/auth/me/` returns the current user plus authorization metadata used by the dashboard:

- `role`
- `ward` and `ward_name`
- `scope_type` and `scope_ward_id`
- `two_factor_policy`
- `profile_capabilities`
- `dashboard_capabilities`
- `policy_acceptance`

The dashboard capability payload includes page flags, action flags, scope, and a schema version. Clients should consume those flags instead of hard-coding role strings where possible.

Role definitions:

- `ADMIN`: broad administrative and operational access across wards; default 2FA policy is required.
- `SUPERVISOR`: ward-scoped operational access for the user's assigned ward; default 2FA policy is required.
- `ANALYST`: broad read and analysis access; mutation, sensitive export, CHV operations, and approval controls are blocked; default 2FA policy is optional.
- `CHV`: field/offline workflow role, not a dashboard role; dashboard pages and operational admin APIs are blocked by default.

Scope behavior:

- `ADMIN` and `ANALYST` use broad dashboard scope.
- `SUPERVISOR` uses ward scope when assigned to a ward. Ward-scoped direct object access outside that ward returns a scoped denial, usually `404`, so cross-ward record existence is not leaked.
- `CHV` uses field scope for CHV/offline flows and has no dashboard page capability.

Capability matrix:

| Capability | Admin | Supervisor | Analyst |
| --- | --- | --- | --- |
| Dashboard access | Yes | Yes | Yes |
| Ward/data scope | Broad | Own ward for ward-scoped data | Broad |
| Trigger alerts | Yes | Yes, ward-scoped | No |
| Manage preparedness actions | Yes | Yes, ward-scoped | View only |
| CHV operations | Yes | Yes, ward-scoped | No |
| Facility readiness reviews | Yes | Yes, ward-scoped | View only |
| Sensitive exports | Auto/request/approve/download | Request/download own approved | No |
| Source data imports | Full, including risky approval/admin controls | Upload/validate/confirm/request approval | View/download templates only |
| Message governance | View and approve | View only | View only |
| System controls | Full write controls | Backend read only, frontend hidden | Frontend shown, backend write blocked |
| Auth/user admin | Yes | No | No |
| 2FA policy | Required by default | Required by default | Optional by default |

Dashboard page matrix:

| Dashboard page | Admin | Supervisor | Analyst | CHV |
| --- | --- | --- | --- | --- |
| Dashboard shell | Yes | Yes | Yes | No |
| Overview | Yes | Yes | Yes | No |
| Ward Decisions | Yes | Yes, ward-scoped | Yes | No |
| Alerts | Yes | Yes, ward-scoped | Yes, read-only for delivery actions | No |
| Response Tasks | Yes | Yes, ward-scoped | Yes, read-only | No |
| CHV Operations | Yes | Yes, ward-scoped | No | No |
| Facility Readiness | Yes | Yes, ward-scoped | Yes, read-only | No |
| Metrics | Yes | Yes, ward-scoped where data is ward-owned | Yes | No |
| Data Readiness | Yes | Yes, upload/validate/request approval | Yes, read/templates only | No |
| Communication Review | Yes, approve | Yes, view only | Yes, view only | No |
| Forecast Readiness | Yes | Yes, operational view | Yes | No |
| Data Connections | Yes | Yes, upload/validate/request approval | Yes, read/templates only | No |
| Operations Readiness | Yes | Frontend hidden; backend read-only status only | Yes, read-only status only | No |

High-risk action step-up:

- Fresh step-up is session-bound and purpose-specific. A valid login TOTP alone is not enough for a later high-risk operation after the step-up window expires.
- The backend responds with `403`, `code: step_up_required`, and the required `purpose` when a permitted role still needs fresh verification.
- Current step-up purposes are `admin_actions`, `security_admin`, `system_controls`, `sensitive_exports`, `sensitive_export_download`, `source_data`, `message_governance`, `alert_delivery`, and `operational_data`.
- Examples include admin user creation/deactivation/reactivation, access-request decisions, admin session revocation, alert triggering, preparedness and facility-readiness writes, CHV coverage operations, sensitive export request/approval/download, source-data upload/validation/confirmation/approval/downstream actions, message-template or USSD governance approval, and system control writes.

## API Surface Snapshot

Current notable API routes include:

- `POST /api/v1/auth/password-reset/request/`
- `POST /api/v1/auth/password-reset/confirm/`
- `POST /api/v1/auth/access/request/`
- `GET /api/v1/auth/session/`
- `GET /api/v1/auth/me/`
- `GET /api/v1/wards/`
- `GET /api/v1/risk-scores/`
- `GET /api/v1/risk-score/latest/`
- `GET /api/v1/alerts/`
- `POST /api/v1/alerts/trigger/`
- `GET /api/v1/preparedness-actions/`
- `GET /api/v1/chvs/`
- `GET /api/v1/facility-readiness/reviews/`
- `GET /api/v1/sensitive-exports/`
- `GET /api/v1/source-data/overview/`
- `POST /api/v1/source-data/uploads/`
- `GET /api/v1/message-governance/dashboard/`
- `GET /api/v1/system/readiness/`
- `GET /api/v1/system/controls/`
- `POST /api/v1/chv/triage/`
- `POST /api/v1/chv/sync/`
- `POST /api/v1/ussd/menu/`
- `GET /api/v1/ussd/logs/`

Example usage:

```bash
curl -X POST http://localhost:8000/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"ChangeMe123!"}'
```

Machine-readable schema:

- `GET /api/v1/schema/`

The canonical API surface is `/api/v1/`. Unversioned `/api/` routes are intentionally removed so the contract stays explicit from this point forward.

The schema endpoint is intentionally public so client developers and integrators can inspect the contract, but the routes described inside it still keep their own authentication and permission requirements.

## API Versioning Strategy

CCHIS now uses URL-path versioning for public API contracts.

Current policy:

- `/api/v1/` is the canonical stable contract for the current backend
- there is no parallel unversioned public API surface
- additive, backward-compatible changes may ship inside `v1`
- breaking changes require a new version path such as `/api/v2/`
- version retirement must be documented before an older version is removed

This keeps future expansion additive instead of forcing disruptive rewrites when dashboard, CHV mobile, analytics, or partner integrations mature.

## v1 Route Freeze Notes

The current v1 contract being frozen is:

- auth routes under `/api/v1/auth/`
- risk and operational routes under `/api/v1/`
- public USSD callback at `POST /api/v1/ussd/menu/`
- machine-readable contract at `GET /api/v1/schema/`

Migration note:

- there is no supported unversioned route surface
- future docs and client examples must use the versioned form
- breaking route moves must happen through new version paths, not hidden aliases

## API Contract Conventions

The v1 backend now follows a basic contract baseline for list and error responses.

### Pagination

- list endpoints are paginated by default
- the default page size is controlled by `API_PAGE_SIZE`
- clients may request a smaller or larger page with `page_size`, up to the server-side maximum
- paginated responses return:
  - `count`
  - `next`
  - `previous`
  - `results`

### Filtering

Current list endpoints use predictable query parameter names based on the resource:

- `ward_id` for ward-scoped records such as CHVs, risk scores, alerts, audit events, and USSD logs
- `status` for status-based filtering
- `risk_level` for risk score filtering
- `event_type` for auth audit filtering
- `session_id` and `phone_number` for USSD log filtering
- `county`, `sub_county`, and `is_active` where they apply to ward or CHV listings

### Ordering

- list endpoints support an `ordering` query parameter
- use field names such as `name`, `created_at`, or `generated_at`
- prefix with `-` for descending order, for example `?ordering=-generated_at`
- each list endpoint exposes only an explicit safe set of ordering fields

### Error Responses

The backend uses these response conventions:

- non-field API errors return a top-level `detail`
- validation errors return:
  - `detail`
  - `errors`
- validation field entries are preserved for backward compatibility with current clients and tests

This contract baseline is intended to reduce future breakage as dashboard, mobile, and partner integrations are added.

## Core Endpoint Contracts

These are the main v1 contract expectations for current backend consumers.

### Auth Endpoints

- `POST /api/v1/auth/login/`
  - public
  - request body: `username`, `password`
  - returns the serialized current user and establishes the auth session, or a `requires_2fa` branch with a temporary pre-auth token for users whose policy requires 2FA
  - shared/staging/production deployments should use secure cookie transport; local token responses are only a development convenience when enabled
- `POST /api/v1/auth/verify-2fa/`
  - public after successful primary credential verification
  - request body: `token`, `code`
  - verifies TOTP or recovery code, establishes the final auth session, and returns the serialized current user
- `POST /api/v1/auth/2fa/setup/` and `POST /api/v1/auth/2fa/setup/confirm/`
  - public when used with a valid pre-auth enrollment token, or authenticated when used inside an existing session
  - starts and confirms TOTP enrollment for roles whose policy requires or permits 2FA
- `POST /api/v1/auth/step-up/verify/`
  - authenticated
  - request body: `purpose`, `code`
  - creates a session-bound fresh step-up grant for the requested high-risk action purpose
- `POST /api/v1/auth/refresh/`
  - public
  - rotates the refresh session using the configured cookie or token transport
- `GET /api/v1/auth/session/`
  - public bootstrap endpoint
  - returns anonymous session state or the current authenticated user from valid access/refresh cookies
- `GET /api/v1/auth/me/`
  - authenticated
  - returns the current user profile, scope metadata, 2FA policy, policy-acceptance state, and dashboard/profile capabilities
- `POST /api/v1/auth/password-reset/request/`
  - public
  - request body: username or email identifier
  - returns a non-enumerating recovery response
- `POST /api/v1/auth/password-reset/confirm/`
  - public
  - request body: reset token and new password
  - sets the new password and invalidates existing refresh sessions
- `POST /api/v1/auth/access/request/`
  - public
  - accepts access-request submission data
- `GET /api/v1/auth/access/requests/`
  - admin only
- `POST /api/v1/auth/access/requests/<id>/approve/`
  - admin only with fresh `admin_actions` step-up
- `POST /api/v1/auth/access/requests/<id>/reject/`
  - admin only with fresh `admin_actions` step-up

### Risk and Operational Endpoints

- `GET /api/v1/wards/`
  - admin, supervisor, or analyst
  - admin and analyst see broad data
  - supervisor responses are restricted to the user's assigned ward
  - paginated
  - supports filtering and ordering
- `GET /api/v1/risk-scores/`
  - admin, supervisor, or analyst
  - admin and analyst see broad data
  - supervisor responses are restricted to the user's assigned ward
  - paginated
  - supports `ward_id`, `risk_level`, `source`, and `ordering`
- `GET /api/v1/alerts/`
  - admin, supervisor, or analyst
  - admin and analyst see broad data; analyst delivery identifiers are redacted where required
  - supervisor responses are restricted to the user's assigned ward
  - paginated
  - supports `ward_id`, `channel`, `status`, and `ordering`
- `POST /api/v1/alerts/trigger/`
  - admin or supervisor only with fresh `alert_delivery` step-up
  - supervisors can trigger only for their assigned ward
- `GET /api/v1/preparedness-actions/`
  - admin, supervisor, or analyst
  - supervisors are ward-scoped; analysts are read-only
- `POST/PATCH /api/v1/preparedness-actions/`
  - admin or ward-scoped supervisor only with fresh `operational_data` step-up
- `GET /api/v1/chvs/` and `GET /api/v1/chv/coverage-requests/`
  - admin or supervisor only
  - supervisors are ward-scoped
- `POST/PATCH` CHV coverage and related operational actions
  - admin or ward-scoped supervisor only with fresh `operational_data` step-up
- `GET /api/v1/facility-readiness/reviews/`
  - admin, supervisor, or analyst
  - supervisors are ward-scoped; analysts are read-only
- `POST/PATCH` facility-readiness reviews and escalations
  - admin or ward-scoped supervisor only with fresh `operational_data` step-up
- `GET /api/v1/sensitive-exports/`
  - admin or supervisor
  - supervisors can see and download only their own approved ward-scoped exports
- `POST /api/v1/sensitive-exports/`
  - admin or supervisor with fresh `sensitive_exports` step-up
  - admin requests can be auto-approved by policy; supervisor requests require admin approval before download
- `POST /api/v1/sensitive-exports/<id>/approve/`
  - admin only with fresh `sensitive_exports` step-up
- `GET /api/v1/sensitive-exports/<id>/download/`
  - admin or owning supervisor with fresh `sensitive_export_download` step-up
- `GET` source-data feed, overview, freshness, template, and validation-error endpoints
  - admin, supervisor, or analyst
  - analysts are view/template-only
- `POST/PATCH` source-data upload, validation, confirmation, cancellation, and downstream-action endpoints
  - admin or supervisor only with fresh `source_data` step-up
  - risky import approval and admin connector controls are admin only
- `GET` message-governance dashboards and template detail endpoints
  - admin, supervisor, or analyst
  - supervisors and analysts are view-only
- `POST` message-template and USSD approval endpoints
  - admin only with fresh `message_governance` step-up
- `GET /api/v1/system/readiness/` and `GET /api/v1/system/controls/`
  - admin, supervisor, or analyst
  - supervisor and analyst responses expose read-only status and `can_*` write flags as false
- `POST` system retry, manual risk scoring, and alert-delivery pause endpoints
  - admin only with fresh `system_controls` step-up

### Field and Low-Connectivity Endpoints

- `GET /api/v1/chv/offline/contract/`
  - field/operator roles only
  - returns the versioned offline workflow, bundle, upload envelope, and sync health contract for the user's assigned ward
- `POST /api/v1/chv/device-registrations/`
  - field/operator roles only
  - registers or refreshes a CHV offline device against the user's assigned ward and current contract version
- `POST /api/v1/chv/triage/`
  - supervisor or CHV only
  - ward checks are enforced for both roles
  - accepts ward and symptom data
  - returns triage guidance and referral decision
- `POST /api/v1/chv/sync/`
  - supervisor or CHV only
  - ward checks are enforced for both roles
  - accepts legacy `payloads` or versioned `uploads` envelopes for supported offline submissions
  - returns sync processing results, conflict state, server receipts, and sync health
- `POST /api/v1/ussd/menu/`
  - public
  - accepts provider-style session payloads
  - returns a single `response` string for the USSD flow

For exact machine-readable field definitions, use `GET /api/v1/schema/`.

## Domain Boundary Map

The backend will not keep expanding everything inside `risk`.

Current target bounded contexts:

- `accounts`
  - authentication, roles, password lifecycle, account audit events
- `geo`
  - geographic hierarchy, ward metadata, boundaries, centroids, future facility locations
- `forecasting`
  - feature inputs, model runs, model metadata, risk scores, forecast lineage
- `surveillance`
  - case-like records, triage records, referrals, follow-up outcomes, sync ingestion
- `operations`
  - alerts, interventions, preparedness actions, assignment workflows
- `messaging`
  - SMS, USSD, templates, delivery events, provider callbacks
- `integrations`
  - DHIS2 mappings, import/export jobs, partner identifiers, external payload logs
- `platform`
  - shared API concerns, idempotency helpers, provenance utilities, common operational tooling

Current v1 placement rule:

- `risk` remains a temporary composite app for prototype velocity
- no new concern should be added to `risk` unless it is directly about risk computation or ward-level forecasting
- new messaging, surveillance, integration, or operational workflow work should be designed toward its future bounded context from day one

Current `risk` audit summary:

- should stay in `risk` for now:
  - `RiskScore`
  - model-triggering tasks
  - forecast-oriented querying and scoring helpers
- acceptable to stay temporarily but should become `geo`:
  - `Ward`
  - geographic filters and serializers
- should eventually move to `surveillance`:
  - `CHV`
  - `TriageSession`
  - `SyncQueue`
- should eventually move to `operations`:
  - `Alert`
- should eventually move to `messaging`:
  - `UssdSessionLog`
  - USSD menu handling
  - SMS provider delivery code currently living in `risk.services`

The practical rule for v1 is simple: we do not need to split every app immediately, but we do need to stop deepening the current mixing of geography, forecasting, field operations, and communications as if they were one domain.

## Future-Critical Entity Decisions

Phase 2.2 decisions for v1 are now explicit:

- `HealthFacility` is introduced now as a minimal anchor entity for future facility-aware forecasting and referral workflows
- `TriageSession` remains a decision-support encounter record, not the long-term surveillance or case model
- `Alert` remains a notification record, not the long-term intervention or preparedness action model

The detailed design note lives in [docs/DOMAIN_BOUNDARIES.md](/Users/edwininganji/VSCodeProjects/cchis/docs/DOMAIN_BOUNDARIES.md) and [docs/FUTURE_ENTITY_DECISIONS.md](/Users/edwininganji/VSCodeProjects/cchis/docs/FUTURE_ENTITY_DECISIONS.md).

## Identifier Policy

CCHIS now treats display names as labels, not canonical identifiers.

Current rule set:

- `Ward.public_id` is the immutable CCHIS-level ward identifier
- `HealthFacility.public_id` is the immutable CCHIS-level facility identifier
- `ward_code` and `facility_code` are reference codes for ops and cross-system mapping
- names must not be used as long-term integration keys

The full policy lives in [docs/IDENTIFIER_POLICY.md](/Users/edwininganji/VSCodeProjects/cchis/docs/IDENTIFIER_POLICY.md).

## Ingestion Provenance

Rainfall ingestion now persists `IngestionRun` records so we can audit:

- which wards were requested
- which source mode was used
- whether live data or fallback data was used
- which coordinate source was used
- whether the run completed fully or partially

Current rainfall policy:

- live mode prefers `Ward.centroid` when available
- if no centroid exists, the prototype may still fall back to the temporary hardcoded ward map
- live-fetch failures fall back to static rainfall sources and are recorded as partial ingestion

The full provenance and fallback policy lives in [docs/INGESTION_PROVENANCE.md](/Users/edwininganji/VSCodeProjects/cchis/docs/INGESTION_PROVENANCE.md).

## Model Lineage

Forecast execution now persists `ModelRun` records so model-generated `RiskScore` rows can be traced to:

- a concrete run
- the algorithm and model version used
- the feature keys used for inference
- the feature schema version
- the training and inference dataset references
- lightweight evaluation metadata
- the rainfall ingestion run used by that forecast

This means `model_version` is no longer the only lineage clue. Model-generated scores now have a real run link.

The detailed policy lives in [docs/MODEL_LINEAGE.md](/Users/edwininganji/VSCodeProjects/cchis/docs/MODEL_LINEAGE.md).

## Feature and Dataset Provenance

The backend now carries explicit lightweight provenance for:

- feature schema version
- feature keys
- training dataset reference
- inference dataset reference

This is intentionally lighter than a full feature store or experiment tracker, but it gives v1 a real path for future ML maturity instead of leaving those concepts invisible.

The detailed policy lives in [docs/FEATURE_AND_DATASET_PROVENANCE.md](/Users/edwininganji/VSCodeProjects/cchis/docs/FEATURE_AND_DATASET_PROVENANCE.md).

## Domain Audit Direction

Durable auditing is currently implemented for auth-sensitive actions through `AuthAuditEvent`, but v1 now also defines the future-required non-auth audit inventory so later operational trust work does not get improvised.

That current domain audit direction covers future audit expectations for:

- manual risk-score overrides
- manual alert triggering and alert requeue actions
- ingestion corrections and model backfills
- triage referral overrides
- sync replay actions
- future intervention or response-action state overrides

The policy boundary is explicit: non-auth operational history should not be stuffed into the auth audit table. The detailed direction lives in [docs/DOMAIN_AUDIT_READINESS.md](/Users/edwininganji/VSCodeProjects/cchis/docs/DOMAIN_AUDIT_READINESS.md).

## Operational Runbook Direction

The repo now also defines the minimum incident-review and recovery inputs maintainers should expect before operational tooling gets more sophisticated.

That current runbook direction covers:

- the logs, metrics, and durable records needed to diagnose API, auth, sync, triage, USSD, forecasting, and alert incidents
- the minimum visibility expected from backup workflows
- the minimum visibility expected from restore workflows
- post-restore validation expectations so recovery is not declared complete without evidence

The detailed policy lives in [docs/OPERATIONAL_RUNBOOK_AND_RECOVERY_INPUTS.md](/Users/edwininganji/VSCodeProjects/cchis/docs/OPERATIONAL_RUNBOOK_AND_RECOVERY_INPUTS.md).

## Deployment Security Notes

Local Docker defaults are intentionally developer-friendly. Before any shared, staging, or production deployment, you should change the security-related environment variables in `.env`.

`CCHIS_ENVIRONMENT` is the deployer-owned environment label used by the backend for environment discipline:

- `local` for isolated developer machines and disposable local Docker stacks
- `staging` for shared test, QA, or rehearsal environments
- `production` for real operational deployments

If you leave it unset, the backend defaults to `local`.

At minimum review and set:

- `CCHIS_ENVIRONMENT`
- `DEBUG=False`
- `ALLOWED_HOSTS`
- `CORS_ALLOW_ALL_ORIGINS=False`
- `CORS_ALLOWED_ORIGINS`
- `CSRF_TRUSTED_ORIGINS`
- `SECURE_SSL_REDIRECT=True` when TLS is terminated correctly
- `SECURE_SSL_REDIRECT_REVERSE_PROXY_EXEMPTION=True` only when a trusted proxy already enforces HTTPS redirects before Django
- `SESSION_COOKIE_SECURE=True`
- `CSRF_COOKIE_SECURE=True`
- `AUTH_ACCESS_COOKIE_NAME=__Host-cchis_access`
- `AUTH_REFRESH_COOKIE_NAME=__Host-cchis_refresh`
- `AUTH_REFRESH_COOKIE_LEGACY_NAMES=cchis_refresh` only during the refresh-cookie migration window
- `USE_X_FORWARDED_HOST=True` only when you trust the reverse proxy
- `TRUST_X_FORWARDED_PROTO=True` only when your proxy sets `X-Forwarded-Proto` correctly
- `TRUST_X_FORWARDED_FOR=True` only when your proxy strips and rewrites `X-Forwarded-For`
- `SECURE_HSTS_SECONDS` with non-zero values only after HTTPS is confirmed end to end

The app now supports these deployment-oriented settings in [backend/core/settings.py](/Users/edwininganji/VSCodeProjects/cchis/backend/core/settings.py).

For deployment boundaries, assume TLS terminates at Nginx or your cloud load balancer and only trust forwarded headers from that layer. In local Docker development, keep the forwarded-header trust flags disabled unless you are deliberately testing behind a proxy that you control. Shared environments now fail startup when secure cookie, HSTS, host, CORS, or SSL redirect settings remain in local-development shape.

The full environment promotion, migration, and seeding policy lives in [docs/ENVIRONMENT_DISCIPLINE.md](/Users/edwininganji/VSCodeProjects/cchis/docs/ENVIRONMENT_DISCIPLINE.md).

## Demo Credentials

The seed command creates local demo users with password `ChangeMe123!`.

- `admin` with role `ADMIN`: full dashboard, broad ward/data scope, auth/user admin, system write controls, approval controls, sensitive exports, and required 2FA by default.
- `supervisor` with role `SUPERVISOR`: dashboard access for ward-scoped operations, alert triggering, preparedness actions, CHV operations, facility readiness, source-data upload/validation/request flows, own approved export download, and required 2FA by default. The Operations Readiness page is hidden in the frontend; backend system status is read-only.
- `analyst_demo` with role `ANALYST`: broad read and analysis access, including read-only Operations Readiness status. Alert triggering, CHV operations, operational mutations, sensitive exports, source-data writes, approval controls, and auth/user admin are blocked. 2FA is optional by default.
- `chv_demo` with role `CHV`: field/offline workflow role for CHV endpoints and assigned-ward low-connectivity flows. The dashboard shell and dashboard admin APIs are blocked by default.

These credentials are for local development only. Do not reuse them in shared or deployed environments.

The seed command also creates a dedicated `superuser` account for local administration. You can override the seeded usernames, emails, and passwords with:

- `SEED_ENABLE_SUPERUSER`
- `SEED_ENABLE_DEMO_USERS`
- `SEED_ALLOW_NON_LOCAL`
- `SEED_SUPERUSER_USERNAME`
- `SEED_SUPERUSER_EMAIL`
- `SEED_SUPERUSER_PASSWORD`
- `SEED_DEFAULT_PASSWORD`

By default, `seed_demo_data` is blocked when `CCHIS_ENVIRONMENT` is `staging` or `production`. For shared demos or rehearsal environments, require an explicit one-time opt-in with `SEED_ALLOW_NON_LOCAL=True`, and keep `SEED_ENABLE_DEMO_USERS=False` unless you intentionally need demo accounts for that session.

## Demo Use Versus Real Deployment

Safe for isolated local development:

- demo users seeded by `seed_demo_data`
- Docker-exposed local ports
- non-HTTPS localhost traffic
- permissive local CORS values used only on your machine

Not acceptable for real deployment without change:

- demo passwords
- `DEBUG=True`
- broad `ALLOWED_HOSTS`
- `CORS_ALLOW_ALL_ORIGINS=True`
- disabled secure-cookie and SSL redirect settings
- trusting forwarded headers without a controlled reverse proxy

For real deployment, review the deployment security notes, disable demo-user seeding, and treat every environment variable as deployer-owned configuration.

## Environment Promotion Policy

The backend now assumes three environment classes:

- `local`: developer-friendly defaults, local Docker ports, disposable data, and demo seeding allowed
- `staging`: production-like config rehearsal, no habitual demo seeding, and explicit host/origin/proxy settings
- `production`: real operational data, least-privilege configuration, and no demo seeding by habit

Migration and seed discipline:

- run schema migrations in every environment as a deliberate deployment step
- treat seed/demo commands as local-only unless a shared-environment demo is explicitly approved
- never rely on fixture or demo seeding as part of staging or production startup
- keep sample credentials and local convenience flags out of deployment defaults

See [docs/ENVIRONMENT_DISCIPLINE.md](/Users/edwininganji/VSCodeProjects/cchis/docs/ENVIRONMENT_DISCIPLINE.md) for the fuller policy.

## Data Lifecycle Policy

The backend now defines a v1 data lifecycle direction so retention and sensitive-data handling are not left informal while more field data accumulates.

Current direction:

- request logs are short-lived operational traces, not indefinite history
- auth audit events are durable security records
- USSD logs, sync payloads, triage sessions, and alert records are bounded operational or field records and should not grow forever by habit
- ingestion runs, model runs, and risk scores are durable provenance and analytical history
- future patient-like or household-linked records should default to structured, least-identifying data

The detailed policy lives in [docs/DATA_LIFECYCLE_POLICY.md](/Users/edwininganji/VSCodeProjects/cchis/docs/DATA_LIFECYCLE_POLICY.md).

## Backup And Restore Discipline

The backend now defines a v1 backup-and-restore discipline so recoverability is treated as a design expectation rather than an emergency-only concern.

Current direction:

- backups must leave identifiable artifact, timing, engine-version, schema-state, and coverage-window evidence
- restores must record source artifact, target environment, applied migration state, and completion outcome
- post-restore validation must include app health, API smoke checks, and critical-record sanity summaries
- recovery rehearsals should leave written evidence of duration, gaps, and follow-up actions

The detailed policy lives in [docs/BACKUP_AND_RESTORE_DISCIPLINE.md](/Users/edwininganji/VSCodeProjects/cchis/docs/BACKUP_AND_RESTORE_DISCIPLINE.md).

## Local Reset and Bootstrap

If you are resetting the local database to adopt the custom user model from a clean baseline:

```bash
docker compose down -v
find backend -path "*/migrations/*.py" ! -name "__init__.py" -delete
find backend -path "*/migrations/*.pyc" -delete
docker compose up --build -d
docker compose ps
docker compose exec backend python manage.py makemigrations
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py seed_demo_data
docker compose exec backend python manage.py test
```

The `docker compose ps` step is there to confirm the `backend`, `db`, and `redis` services are actually up before you run migrations or seeding.

## Project Structure

```text
cchis/
├── backend/
│   ├── accounts/
│   ├── core/
│   └── risk/
├── docs/
├── docker-compose.yml
├── README.md
├── SECURITY.md
└── CONTRIBUTING.md
```

## Dependency and CI Policy

The project currently uses bounded version ranges in [backend/requirements.txt](/Users/edwininganji/VSCodeProjects/cchis/backend/requirements.txt) rather than fully pinned transitive lockfiles. That keeps early development flexible, but it increases the importance of CI and routine dependency review.

Current maintenance guardrails:

- GitHub Actions CI builds the backend container and runs compile plus Django test checks
- `pip-audit` runs in CI against `backend/requirements.txt`
- Dependabot is configured for both Python dependencies and GitHub Actions updates

Recommended maintainer workflow:

- review dependency PRs promptly, especially security-related updates
- merge dependency bumps only after CI passes
- keep Docker, Python, and dependency changes coordinated in the same patch set when they are coupled

## Contributing

See [CONTRIBUTING.md](/Users/edwininganji/VSCodeProjects/cchis/CONTRIBUTING.md) for local setup, secrets handling, seeded-credential guidance, and expectations for security-sensitive changes.

## Additional Documentation

- [SECURITY.md](/Users/edwininganji/VSCodeProjects/cchis/SECURITY.md) for deployment and incident guidance
- [docs/TECHNICAL_APPENDIX.md](/Users/edwininganji/VSCodeProjects/cchis/docs/TECHNICAL_APPENDIX.md) for deeper technical context
- `CCHIS_README_UPDATED.md` remains as a separate draft/reference file if you still want to compare alternative wording
