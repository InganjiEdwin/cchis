# Source Data Ops Surface Implementation Plan

Status date: 2026-05-05

This plan implements the operator-facing surface for CCHIS source-data intake: CSV template download, upload, validation, safe import, source freshness, ingestion history, and downstream rebuild controls.

The direction is to build a dedicated ops surface, not to rely on Django admin as the primary workflow. Django admin should remain available for superuser inspection, emergency correction, and development debugging only. County and partner operators need a guided, auditable, low-risk experience that makes it hard to upload the wrong data and easy to understand what happened after an upload.

## Operating Decision

Build a first-class source-data ops surface in the dashboard.

Keep Django admin for:

- superuser-only model inspection
- rare incident response
- local development checks
- emergency correction under documented approval

Do not use Django admin as the normal upload surface because it does not give operators enough guardrails, validation preview, import history, source freshness context, or downstream impact visibility.

## Product Goal

An authorized operator should be able to:

1. Open the source-data area.
2. See which feeds are current, stale, missing, or demo-backed.
3. Download the correct CSV template for the feed they manage.
4. Upload a CSV with source metadata.
5. Run a dry validation before data changes the system.
6. Review accepted rows, rejected rows, warnings, and downstream impact.
7. Confirm the import with an audit reason.
8. Track import progress and history.
9. Download a rejected-row file for correction.
10. Trigger safe downstream rebuilds when the source type requires them.

## Non-Goals

- Do not replace DHIS2, OpenMRS, WorldPop, stock/logistics, or GIS integrations. The ops surface is the CSV/manual bridge until those integrations are available.
- Do not accept raw personal line lists in the pilot surface. Use aggregate surveillance and line-list summaries only.
- Do not automatically promote models after import.
- Do not automatically send SMS after import.
- Do not allow arbitrary CSV columns to mutate production tables.
- Do not allow operators to create unsupported source types from the UI.

## Current Implementation Baseline

Already available:

- Rainfall ingestion is wired through `risk.tasks.run_rainfall_ingestion_task` and scheduled daily at 05:30.
- Daily ward-risk scoring is scheduled at 06:00 through `risk.tasks.run_risk_model_task`.
- Facility burden forecasting is scheduled at 06:30 through `risk.tasks.run_facility_burden_forecast_task`.
- Population/exposure CSV ingestion exists through `run_population_exposure_csv_ingestion` and the `ingest_population_exposure` command.
- Surveillance CSV ingestion exists through `run_surveillance_csv_ingestion` and the `ingest_surveillance` command.
- Async Celery task wrappers exist for population/exposure and surveillance ingestion.
- Interoperability CSV template/download/import patterns already exist, but they are for interoperability contracts, not source-data intake.
- Facility readiness review/update/escalation workflows exist, but a canonical source-file ingestion path for readiness snapshots is still a gap.

Missing:

- Dashboard source-data page.
- Source-feed template registry exposed to operators.
- Source-data upload API.
- Dry-run validation API.
- Confirm-import API.
- Source freshness summary API across rainfall, surveillance, exposure, population, and facility readiness.
- Operator-friendly rejected-row download for source-data imports.
- Facility readiness CSV ingestion path.
- Clear downstream action workflow after source upload.

## Feed Scope

MVP feed types:

| Feed | Domain | Backend target | Cadence |
| --- | --- | --- | --- |
| `surveillance_weekly_aggregate` | Health surveillance | `ingest_surveillance --source-type weekly_aggregate` | Weekly minimum |
| `surveillance_daily_aggregate` | Health surveillance | `ingest_surveillance --source-type daily_aggregate` | Daily where available |
| `surveillance_backfill` | Health surveillance | `ingest_surveillance --source-type csv_backfill` | One-off at pilot start, then corrections |
| `population_baseline` | Population | `ingest_population_exposure --source-type population_baseline` | Annual/source-change driven |
| `gridded_population` | Population/exposure | `ingest_population_exposure --source-type gridded_population` | Quarterly/source-change driven |
| `settlement_layer` | Exposure context | `ingest_population_exposure --source-type settlement_layer` | Quarterly/source-change driven |
| `wash_vulnerability_layer` | Exposure context | `ingest_population_exposure --source-type wash_vulnerability_layer` | Quarterly or assessment-change driven |
| `water_body_distance_layer` | Exposure context | `ingest_population_exposure --source-type water_body_distance_layer` | Quarterly/source-change driven |
| `flood_exposure_layer` | Flood exposure | `ingest_population_exposure --source-type flood_exposure_layer` | Monthly in rainy season, event-driven after floods |
| `facility_catchment_mapping` | Facility/spatial | `ingest_population_exposure --source-type catchment_mapping` | Setup, then facility/catchment changes |
| `facility_readiness_snapshot` | Facility readiness | New readiness snapshot ingestion path | Weekly routine, daily during alerts/outbreak risk |

Later feed types:

- DHIS2 API scheduled pulls.
- OpenMRS facility extracts.
- WorldPop/KNBS processed source pulls.
- OSM/Overpass-derived exposure refresh.
- Logistics/stock system integration for ORS, IV fluids, zinc, chlorine, beds, staffing, and referral capacity.

## Roles And Permissions

Use the existing role model as the base:

| Role | Source-data permissions |
| --- | --- |
| Admin | Full access, settings, imports, replays, replacement imports, retention controls |
| Supervisor | Upload, validate, confirm routine imports for assigned operational scope |
| Analyst | Read-only source freshness, history, validation summaries, templates |
| CHV | No source-data ops access |
| Superuser | Django admin and emergency override only |

Risky import approval policy:

- Routine clean imports can be confirmed by an authorized supervisor or admin.
- Historical backfills, replacement imports, replay imports, production surveillance-truth imports, unusually large source deltas, and production downstream rebuilds require maker-checker approval.
- The person who uploaded or requested a risky import cannot be the second approver.
- Approval decisions must store actor, timestamp, reason, risk category, and affected feed.
- The UI should make the approval state visible before confirmation: not required, pending approval, approved, rejected, or expired.

Add finer-grained backend checks through service-level policy:

- `source_data:view`
- `source_data:download_template`
- `source_data:upload`
- `source_data:validate`
- `source_data:confirm_import`
- `source_data:replace_import`
- `source_data:download_errors`
- `source_data:trigger_downstream`

For MVP, map these to existing roles in code. Later, move to explicit permission assignments if county deployments need separate data steward and approver roles.

## UX Principles

The source-data area should feel like an operational control room: calm, dense, predictable, and forgiving.

- Put the working surface first: feed status, upload, templates, validation, and history.
- Use a compact dashboard layout, not a marketing-style page.
- Use clear feed names and source freshness states.
- Make templates one click away from every feed card and upload step.
- Use a four-step upload wizard: choose feed, upload file, validate, confirm import.
- Default every upload to dry-run validation before import.
- Show accepted rows, rejected rows, warnings, date coverage, ward coverage, duplicate detection, and expected downstream effects before confirmation.
- Show the next safe action after import, such as rebuild labels, rebuild feature dataset, or wait for scheduled scoring.
- Keep error messages specific enough to fix the file.
- Make rejected-row downloads obvious.
- Avoid exposing internal model names where a human label is clearer.
- Support keyboard navigation, visible focus states, semantic headings, and screen-reader labels.
- Keep tables usable on laptop screens and readable on tablets.
- Use restrained color: status badges and alerts should carry meaning, not decoration.

## Backend Architecture

Add a source-data intake layer that wraps existing ingestion functions instead of duplicating parsing logic.

Proposed modules:

```text
backend/risk/source_data/
  __init__.py
  registry.py
  templates.py
  validation.py
  uploads.py
  freshness.py
  permissions.py
  downstream.py
```

Proposed responsibilities:

| Module | Responsibility |
| --- | --- |
| `registry.py` | Feed registry, user labels, source-type mapping, cadence, required metadata, downstream actions |
| `templates.py` | CSV template generation from adapter specs |
| `validation.py` | Dry-run validation, PII checks, duplicate checks, ward/facility coverage checks |
| `uploads.py` | Upload batch lifecycle, file hashing, durable shared artifact storage, confirm import orchestration |
| `freshness.py` | Source freshness and truth-state summary across domains |
| `permissions.py` | Role and action policy |
| `downstream.py` | Label rebuild, feature rebuild, audit commands, safe scoring hooks |

Do not make the frontend call management commands. The API should call service functions and Celery tasks.

## Backend Data Model

Add source-data upload tracking models. Names can be adjusted to match local conventions during implementation.

### `SourceDataUploadBatch`

Fields:

- `public_id`
- `feed_key`
- `domain`
- `source_type`
- `source_name`
- `source_ref`
- `source_timestamp`
- `release_version`
- `reporting_period_start`
- `reporting_period_end`
- `correction_mode`
- `replacement_reason`
- `operator_note`
- `status`
- `validation_status`
- `import_status`
- `row_count`
- `accepted_count`
- `rejected_count`
- `warning_count`
- `duplicate_of`
- `replaces_upload`
- `approval_status`
- `approval_risk_category`
- `approval_requested_by`
- `approval_requested_at`
- `approved_by`
- `approved_at`
- `approval_reason`
- `approval_expires_at`
- `validation_celery_task_id`
- `import_celery_task_id`
- `downstream_celery_task_id`
- `domain_ingestion_run_type`
- `domain_ingestion_run_id`
- `surveillance_ingestion_run`
- `population_exposure_ingestion_run`
- `facility_readiness_ingestion_run`
- `created_by`
- `confirmed_by`
- `confirmed_at`
- `created_at`
- `updated_at`
- `metadata`

Suggested statuses:

- `draft`
- `uploaded`
- `validating`
- `validation_failed`
- `ready_for_confirmation`
- `confirming`
- `imported`
- `import_failed`
- `cancelled`
- `superseded`

### `SourceDataUploadArtifact`

Fields:

- `upload_batch`
- `original_filename`
- `content_type`
- `size_bytes`
- `sha256`
- `storage_backend`
- `storage_path`
- `retention_expires_at`
- `redaction_state`
- `created_at`

Store only what is needed. Raw uploads should have a retention policy. For sensitive feeds, keep metadata plus rejected-row diagnostics rather than long-lived raw files.

Storage requirement: upload artifacts used by validation or import tasks must live in durable storage shared by the Django web process and Celery workers. Local process temp files are not acceptable for queued imports. Use a mounted shared volume or object storage, read artifacts by batch/artifact identity, and fail closed if the artifact is missing or the hash no longer matches the validated file.

Validation, import, and downstream Celery task IDs should be stored separately so operators can see where a batch is blocked. Domain ingestion run links should point to the canonical surveillance, population/exposure, or readiness run created by the import; if a generic reference is used, it must still preserve run type and run ID.

### `SourceDataValidationIssue`

Fields:

- `upload_batch`
- `row_number`
- `severity`
- `code`
- `field`
- `message`
- `redacted_row`
- `created_at`

Issue severities:

- `error`
- `warning`
- `info`

### `SourceDataUploadEvent`

Fields:

- `upload_batch`
- `actor`
- `event_type`
- `event_at`
- `ip_address_hash`
- `user_agent_hash`
- `metadata`

Event types:

- `template_downloaded`
- `upload_created`
- `validation_started`
- `validation_completed`
- `confirmation_requested`
- `import_started`
- `import_completed`
- `import_failed`
- `errors_downloaded`
- `downstream_action_requested`
- `replacement_requested`
- `upload_cancelled`

## Backend API

Add DRF endpoints under the risk API namespace:

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/source-data/overview/` | `GET` | Feed cards, freshness, missing/stale/demo states, recent uploads |
| `/source-data/feed-types/` | `GET` | Feed registry, metadata requirements, cadence, downstream rules |
| `/source-data/templates/<feed_key>/` | `GET` | Download CSV template |
| `/source-data/uploads/` | `POST` | Create upload batch with file and metadata |
| `/source-data/uploads/` | `GET` | List upload batches |
| `/source-data/uploads/<uuid:public_id>/` | `GET` | Upload detail, validation summary, events |
| `/source-data/uploads/<uuid:public_id>/validate/` | `POST` | Start or rerun dry validation |
| `/source-data/uploads/<uuid:public_id>/approval/` | `POST` | Request, approve, or reject maker-checker approval for risky imports |
| `/source-data/uploads/<uuid:public_id>/confirm/` | `POST` | Confirm import after clean validation |
| `/source-data/uploads/<uuid:public_id>/cancel/` | `POST` | Cancel a draft/failed upload |
| `/source-data/uploads/<uuid:public_id>/errors.csv/` | `GET` | Download rejected-row diagnostics |
| `/source-data/uploads/<uuid:public_id>/downstream-actions/` | `POST` | Trigger allowed downstream rebuilds |
| `/source-data/freshness/` | `GET` | Lightweight freshness status for nav/topbar |

API design rules:

- Use `public_id` in URLs.
- Use polling first for status; WebSockets can be added later.
- Return a consistent envelope with `status`, `counts`, `issues`, `next_actions`, and `links`.
- Do not return raw uploaded rows unless they are redacted and safe.
- For downloads, sanitize filenames and set explicit `Content-Type`.
- Use existing BFF route style from `frontend/app/api/dashboard/...`.

## Validation Rules

Apply validation in layers.

File-level checks:

- CSV only for MVP.
- Reject unsupported MIME types and suspicious extensions.
- Enforce file size and row count limits per feed type.
- Require UTF-8 or UTF-8 with BOM.
- Reject empty files.
- Reject files without headers.
- Reject duplicate headers.
- Normalize header case and whitespace.
- Detect formula-injection values in user-supplied strings.

Metadata checks:

- Required `source_name`.
- Required `source_timestamp`.
- Required reporting period for surveillance imports.
- Required release version for official/static source layers where applicable.
- Replacement imports require a replacement reason.
- Historical backfills require explicit correction/backfill mode.

Schema checks:

- Required columns by feed type.
- Type coercion for dates, integers, decimals, booleans, and enums.
- Ward/facility key resolution.
- Reporting period bounds.
- Non-negative counts.
- Known disease/category labels.
- Required source truth fields where applicable.

Coverage checks:

- Expected Migori ward coverage where ward-level feed is complete.
- Missing wards listed by name and code.
- Duplicate ward-period rows detected.
- Date coverage summarized.
- Facility IDs checked against canonical facilities.
- Catchment mapping checked for orphan wards/facilities.

Safety checks:

- Reject likely PII columns such as `name`, `phone`, `national_id`, `id_number`, `patient_name`, `date_of_birth`, and `address` for aggregate source feeds.
- Sample cell values for likely PII even when headers look harmless, including phone-like values, national-ID-like values, email addresses, full patient-name patterns, and free-text notes containing personal identifiers.
- Sample both the first rows and a bounded random row set so hidden PII is not missed when only later rows contain sensitive values.
- Allow facility contact fields only in approved facility contact/readiness workflows.
- Flag unusually large changes from the previous source run.
- Flag all-seeded or fallback-only loads clearly.
- Block confirmation when validation has errors.

## Import Rules

Use existing ingestion services as the single source of truth:

- Surveillance imports call `run_surveillance_csv_ingestion`.
- Population/exposure imports call `run_population_exposure_csv_ingestion`.
- Async execution uses existing Celery tasks or thin new task wrappers.
- Facility readiness imports require a new canonical ingestion function.

Confirmation rules:

- Import can start only after successful validation.
- Upload file hash and metadata must match the validated batch.
- A duplicate file with the same metadata should be blocked or require explicit replay.
- A replacement import must reference what it replaces and why.
- Import should be idempotent where possible.
- Partial imports are allowed only if the domain ingestion function already supports them and the UI makes the partial state explicit.

## Downstream Actions

After import, show only safe next actions:

| Source type | Suggested downstream action |
| --- | --- |
| Surveillance weekly/daily/backfill | Regenerate surveillance label windows, then rebuild feature datasets |
| Population baseline | Rebuild population/exposure features, then rebuild model feature datasets |
| Flood/WASH/water/settlement exposure | Rebuild exposure features, then rebuild model feature datasets |
| Facility catchment mapping | Recompute spatial/facility evidence and facility forecast inputs |
| Facility readiness snapshot | Recompute readiness truth, then facility burden forecast |

Guardrails:

- Daily risk scoring remains scheduled.
- Manual scoring can be exposed only through existing system controls and model readiness checks.
- Label rebuilds and feature rebuilds must preserve source cutoff rules: a prediction feature row can only use records available before that prediction day's allowed source cutoff.
- Feature builders must receive explicit `as_of` and source-cutoff inputs from the rebuild request rather than inferring eligibility from wall-clock time.
- Downstream rebuild requests must capture `as_of`, source run IDs, feature dataset version, label dataset role, and leakage-check results.
- Import completion does not automatically send messages.
- Model promotion remains manual and governed.
- Challenger/backtest outputs must be labeled as evaluation evidence, not operational truth.

## Facility Readiness Ingestion Gap

Add a dedicated readiness snapshot import path.

Minimum template fields:

```text
facility_code
facility_name
ward_code
reported_at
ors_sachets_available
iv_fluids_available
zinc_available
chlorine_available
beds_available
staff_on_duty
referral_available
stockout_notes
service_disruption
source_kind
source_ref
```

Implementation options:

1. Create canonical `FacilityReadinessSnapshot` records, then derive review/update status from snapshots.
2. Ingest directly into existing readiness review/update models.

Preferred direction: create canonical snapshot records first. Reviews and escalations should remain workflow decisions, while snapshots represent source truth. This keeps source data separate from operational review actions.

## Frontend Architecture

Add a dashboard route:

```text
frontend/app/(dashboard)/source-data/page.tsx
```

Add BFF routes:

```text
frontend/app/api/dashboard/source-data/overview/route.ts
frontend/app/api/dashboard/source-data/feed-types/route.ts
frontend/app/api/dashboard/source-data/templates/[feedKey]/route.ts
frontend/app/api/dashboard/source-data/uploads/route.ts
frontend/app/api/dashboard/source-data/uploads/[publicId]/route.ts
frontend/app/api/dashboard/source-data/uploads/[publicId]/validate/route.ts
frontend/app/api/dashboard/source-data/uploads/[publicId]/approval/route.ts
frontend/app/api/dashboard/source-data/uploads/[publicId]/confirm/route.ts
frontend/app/api/dashboard/source-data/uploads/[publicId]/cancel/route.ts
frontend/app/api/dashboard/source-data/uploads/[publicId]/errors.csv/route.ts
frontend/app/api/dashboard/source-data/uploads/[publicId]/downstream-actions/route.ts
```

Suggested components:

```text
frontend/components/source-data/
  SourceDataOverview.tsx
  SourceFeedStatusTable.tsx
  SourceFeedCard.tsx
  SourceUploadWizard.tsx
  SourceMetadataStep.tsx
  SourceFileDropzone.tsx
  SourceValidationSummary.tsx
  SourceValidationIssueTable.tsx
  SourceImportConfirmation.tsx
  SourceUploadHistoryTable.tsx
  SourceFreshnessPanel.tsx
  SourceDownstreamActions.tsx
  TemplateDownloadButton.tsx
```

Suggested user flow:

1. Overview page loads feed states and recent imports.
2. Operator selects a feed.
3. Operator downloads template if needed.
4. Operator uploads CSV and fills source metadata.
5. UI creates an upload batch.
6. UI starts dry-run validation.
7. UI polls upload detail until validation completes.
8. UI shows summary and errors.
9. Operator downloads rejected rows if needed.
10. Operator confirms clean import.
11. UI polls import state.
12. UI shows import event timeline and safe downstream actions.

## Frontend UX Details

Overview page:

- Feed status table grouped by domain: climate, surveillance, population, exposure, facility.
- Status badges: current, due soon, stale, missing, demo-backed, failed.
- Compact metrics: last source timestamp, last import, records loaded, rejected rows, next expected refresh.
- Template and upload actions beside each feed.
- Recent imports table with status and actor.

Upload wizard:

- Stepper with four steps.
- Feed type is locked once validation starts.
- File dropzone accepts `.csv`.
- Metadata fields adapt by feed type.
- Template download is available inside the wizard.
- Dry validation starts before confirmation.
- Confirmation button remains disabled while validation has errors.
- Import reason is required for corrections, backfills, and replacements.

Validation summary:

- Counts for rows seen, accepted, rejected, warnings.
- Ward/facility coverage.
- Date coverage.
- Duplicate checks.
- Freshness impact.
- PII/safety findings.
- Rejected-row table with row number, field, reason, and fix guidance.
- Download rejected rows button.

Import result:

- Import status and event timeline.
- Ingestion run link or ID.
- Records loaded/rejected.
- Source truth state.
- Downstream actions.
- Next scheduled scoring time.

Accessibility:

- All icon buttons have accessible labels.
- Tables have captions or labelled regions.
- Form errors are linked to inputs.
- Keyboard users can complete the entire upload.
- Status colors are paired with text.
- Loading/progress states use semantic live regions where useful.

Low-bandwidth support:

- Avoid loading full CSV previews for large files.
- Return first N issues plus downloadable full diagnostics.
- Use polling with modest intervals and clear timeout state.
- Keep the overview API lightweight.

## Security And Safety Requirements

Authentication:

- Require authenticated dashboard session.
- Use existing session/BFF pattern.
- Protect POST routes with CSRF/session safeguards used elsewhere in the app.

Authorization:

- Analysts can view but not upload/confirm.
- Supervisors can upload and confirm routine feeds.
- Admins can replace/replay imports.
- CHVs have no access to source-data ops.
- Superuser-only operations stay in Django admin or explicit emergency tools.

File security:

- CSV-only MVP.
- Strict extension and content-type allowlist.
- Server-side MIME sniffing.
- File size limit.
- Row count limit.
- Reject archives, macros, executables, HTML, XML, and binary files.
- Hash files on upload.
- Store uploads outside web-served paths.
- Store queued-upload artifacts in shared durable storage accessible to both web and worker processes.
- Use generated filenames, never user-provided paths.
- Optionally add antivirus scanning before production deployment.

Data safety:

- Reject raw PII for aggregate source feeds.
- Redact values in validation issues where needed.
- Prevent CSV formula injection in exported diagnostics.
- Make seeded/demo/proxy truth states visible.
- Do not treat `seeded_demo`, `proxy`, or `fallback` records as production evidence.
- Prevent import confirmation when model/source audits report blocking failures.

Audit:

- Log template downloads, uploads, validation, confirmations, imports, error downloads, downstream actions, and replacement decisions.
- Store actor, timestamp, source metadata, file hash, row counts, and result state.
- Link upload batches to domain ingestion runs.
- Keep a clear event timeline visible to operators and admins.

Retention:

- Raw upload artifacts expire by policy, for example 30-90 days depending on deployment risk.
- Keep metadata, hashes, counts, and audit events longer than raw files.
- Rejected-row exports should be redacted and expire.
- Document retention in the privacy/data lifecycle inventory.

Operational safety:

- Do not run import synchronously for large files.
- Use Celery with status polling.
- Use idempotency keys and file hashes.
- Detect duplicate imports.
- Require reasons for replacements.
- Require maker-checker approval for risky production imports and replacement/replay operations.
- Keep rollback/replay command paths for incident response.
- Do not trigger SMS from import workflows.

## Phase 0: Alignment, Threat Model, And UX Blueprint

Objective: lock scope before implementation.

Backend tasks:

- Confirm feed registry list and source-type mapping.
- Confirm which feed types are MVP versus later.
- Confirm role-to-permission mapping.
- Confirm maker-checker policy for backfills, replacements, replay imports, production surveillance truth, and production downstream rebuilds.
- Define upload lifecycle statuses.
- Define data retention policy for raw upload artifacts and diagnostics.
- Choose shared durable upload storage for web/Celery access.
- Write a simple threat model covering malicious files, accidental PII, stale source data, duplicate imports, and unauthorized replacement.

Frontend tasks:

- Sketch the source-data overview, feed detail, upload wizard, validation summary, and import result states.
- Define empty, loading, failed, stale, demo-backed, and success states.
- Confirm navigation placement in the dashboard.
- Define table columns and row actions.

Acceptance criteria:

- Source-data scope is documented.
- Feed registry contract is agreed.
- Security risks and mitigations are listed.
- UX flow has enough detail to implement without guesswork.

Phase 0 implementation artifacts:

- Code contract: `backend/risk/source_data/phase0.py`.
- Contract tests: `backend/risk/test_source_data_phase0.py`.
- Human-readable alignment note: `docs/SOURCE_DATA_OPS_PHASE0_ALIGNMENT.md`.
- Shared upload storage defaults: `SOURCE_DATA_UPLOAD_STORAGE_BACKEND=shared_filesystem` and `SOURCE_DATA_UPLOAD_ROOT=/var/lib/cchis/source_uploads`.
- Docker shared storage volume: `source_uploads`, mounted into both Django web and Celery worker containers.

## Phase 1: Backend Feed Registry And Templates

Objective: expose safe, versioned templates for each supported feed.

Backend tasks:

- Add `risk/source_data/registry.py`.
- Build feed definitions from existing surveillance and population/exposure adapter specs.
- Add user-facing labels, domains, cadences, metadata requirements, and downstream actions.
- Add `risk/source_data/templates.py`.
- Generate CSV templates with headers and one example row per feed.
- Add DRF serializers for feed type metadata.
- Add `GET /source-data/feed-types/`.
- Add `GET /source-data/templates/<feed_key>/`.
- Add tests for every feed template.

Frontend tasks:

- Add BFF routes for feed types and template downloads.
- Add a minimal source-data page shell.
- Add template download buttons.

Security tasks:

- Sanitize template filenames.
- Prevent arbitrary feed keys from resolving to files.
- Audit template downloads.

Acceptance criteria:

- Operators can download templates for every MVP feed.
- Unsupported feed keys return a safe 404.
- Template headers match ingestion contracts.
- Tests cover template contract completeness.

## Phase 2: Backend Upload Batch And Dry Validation

Objective: allow safe upload and validation without mutating domain data.

Backend tasks:

- Add upload tracking models and migrations.
- Add serializers for upload metadata and validation results.
- Add file storage helper with hash, size, retention timestamp, generated storage path, and shared durable storage support for Celery workers.
- Add `POST /source-data/uploads/`.
- Add `GET /source-data/uploads/` and detail endpoint.
- Add `POST /source-data/uploads/<public_id>/validate/`.
- Wrap existing `inspect_population_exposure_csv` and `inspect_surveillance_csv`.
- Add PII/header and sampled-value safety checks before domain validation.
- Add duplicate file and duplicate metadata checks.
- Store validation issues.
- Add rejected-row diagnostics generation.

Frontend tasks:

- Build upload wizard steps for feed selection, metadata, and file upload.
- Build validation polling client.
- Build validation summary and issue table.
- Add rejected-row download link.

Security tasks:

- Enforce role checks.
- Enforce size and row limits.
- Reject unknown feed keys and unsupported source types.
- Reject likely PII columns and sampled PII values for aggregate feeds.
- Store raw files outside web paths.

Acceptance criteria:

- Uploading a valid CSV creates an upload batch.
- Dry validation returns accepted/rejected counts.
- Invalid rows show human-readable issues.
- No domain ingestion records are created during validation.
- Analysts cannot upload.
- CHVs cannot access the route.

## Phase 3: Confirm Import And Ingestion History

Objective: safely turn a validated upload into canonical source records.

Backend tasks:

- Add `POST /source-data/uploads/<public_id>/confirm/`.
- Add maker-checker approval workflow for risky imports.
- Run import through Celery for large files.
- Call existing population/exposure or surveillance ingestion services.
- Link upload batches to created ingestion runs and Celery task IDs.
- Store import status and event timeline.
- Add `GET /source-data/uploads/<public_id>/errors.csv/`.
- Add history filters: feed, domain, status, source_name, date range, actor.
- Ensure replacement/backfill import paths capture correction reasons.

Frontend tasks:

- Add import confirmation step.
- Add import progress polling.
- Add upload history table.
- Add import result view.
- Add filters and status chips.

Security tasks:

- Require successful validation before confirmation.
- Require explicit reason for correction/replacement/backfill.
- Require admin plus second approval for replacement/replay and other risky production imports.
- Prevent the uploader/requester from approving their own risky import.
- Prevent confirmation if file hash changed after validation.
- Redact error CSV values where necessary.

Acceptance criteria:

- A clean surveillance upload can be validated, confirmed, imported, and linked to `SurveillanceIngestionRun`.
- A clean population/exposure upload can be validated, confirmed, imported, and linked to `PopulationExposureIngestionRun`.
- A rejected upload cannot be confirmed.
- A risky import cannot be confirmed until approved by a second eligible actor.
- Duplicate upload behavior is deterministic and visible.
- Import history is understandable without opening Django admin.

## Phase 4: Source Freshness And Ops Overview

Objective: make source coverage and gaps visible at a glance.

Backend tasks:

- Add `risk/source_data/freshness.py`.
- Compute freshness across rainfall, surveillance, population baseline, exposure features, facility readiness, feature datasets, model runs, and facility forecasts.
- Return status, last source timestamp, last import timestamp, expected cadence, current gap, truth state, and recommended action.
- Add `GET /source-data/overview/`.
- Add `GET /source-data/freshness/`.

Frontend tasks:

- Build source-data overview page.
- Add feed status table and recent import table.
- Add freshness panel to show current, stale, missing, failed, demo-backed states.
- Add source gaps callout for feeds requiring admin CSVs.
- Add clear actions: download template, upload, view history.

Security tasks:

- Avoid exposing sensitive row-level data in overview.
- Make demo/proxy/fallback states visible.

Acceptance criteria:

- User can see which feeds are API-backed, CSV-backed, missing, or demo-backed.
- User can see when each source was last refreshed and what action is due.
- Overview matches the source matrix in `CCHIS_DATA_SOURCE_FEEDS.md`.

## Phase 5: Downstream Rebuild Controls

Objective: connect source upload to the rest of the e2e flow without unsafe automation.

Backend tasks:

- Add downstream action registry.
- Add `POST /source-data/uploads/<public_id>/downstream-actions/`.
- Support surveillance label regeneration after surveillance import.
- Support feature dataset rebuild after source import where existing commands/services allow it.
- Enforce source cutoff/leakage rules for all label and feature rebuilds.
- Persist downstream task IDs, source run IDs, `as_of` values, feature dataset versions, and leakage-check results.
- Support audit runs for climate, surveillance, population/exposure, and model operations.
- Return action status and evidence.

Frontend tasks:

- Add downstream actions panel on import result.
- Show recommended next action and why it is safe.
- Show scheduled model scoring time.
- Show when manual risk scoring is unavailable because model/source readiness blocks it.

Security tasks:

- Restrict downstream actions to admin/supervisor/model-ops roles.
- Require maker-checker approval for production downstream rebuilds that replace or supersede evidence used for operational scoring.
- Do not trigger SMS.
- Do not promote models.
- Store every downstream action in the upload event log.

Acceptance criteria:

- After surveillance import, operator can regenerate labels when allowed.
- After exposure/population import, operator can request feature rebuild when allowed.
- Rebuilt feature datasets prove they did not use future labels or records after the configured prediction cutoff.
- UI clearly separates import success from model promotion or alert delivery.

## Phase 6: Facility Readiness Snapshot Ingestion

Objective: close the key facility readiness source-data gap.

Backend tasks:

- Add canonical readiness snapshot model or equivalent ingestion-safe record.
- Add readiness feed registry entry and template.
- Add `run_facility_readiness_snapshot_ingestion`.
- Validate facility code, ward code, report date, stock/capacity fields, and source kind.
- Link snapshots to facility intelligence and facility burden forecasting inputs.
- Add Celery task wrapper.
- Add tests for valid import, invalid facility, stale report, stockout fields, and duplicate snapshots.

Frontend tasks:

- Add facility readiness feed to overview and wizard.
- Add readiness-specific validation summary: facility coverage, stale facilities, stockout flags, service disruptions.
- Add downstream action to recompute readiness evidence and facility forecast inputs.

Security tasks:

- Allow only approved facility operational fields.
- Treat facility contacts separately from readiness snapshots.
- Redact free-text notes in diagnostics if they contain personal details.

Acceptance criteria:

- Operators can upload facility readiness snapshots.
- Facility readiness source state appears in source overview.
- Facility intelligence can distinguish source-backed readiness from seeded/demo readiness.

## Phase 7: World-Class UX Polish And Operator Training

Objective: make the surface clear, fast, and confidence-building.

Frontend tasks:

- Add inline field-level validation before upload.
- Add last-used source metadata suggestions by feed.
- Add clear copy for fixable errors.
- Add progress timeline.
- Add compact row-count and coverage visuals.
- Add keyboard and screen-reader QA.
- Add responsive table behavior.
- Add empty states that point directly to the next action.
- Add tests for happy path, rejected file, role-blocked access, and failed import.

Backend tasks:

- Improve validation issue codes and messages.
- Add stable error code documentation.
- Add sample template rows aligned to Migori context.
- Add API contract tests.

Security tasks:

- Run privacy minimization tests against upload diagnostics.
- Run permission tests for each role.
- Confirm sensitive export governance is not bypassed by source diagnostics.

Acceptance criteria:

- A first-time county data officer can complete a clean upload without reading developer docs.
- Validation errors are actionable.
- The page remains usable on common laptop and tablet widths.
- All critical actions are auditable.

## Phase 8: Production Hardening

Objective: make the feature safe for a pilot production environment.

Backend tasks:

- Add rate limits for upload and validation endpoints.
- Add artifact cleanup job.
- Add operational metrics for upload count, validation failures, import failures, stale feeds, and duplicate attempts.
- Add alerts for repeated failed imports or overdue critical feeds.
- Add health checks for Celery import tasks.
- Add backup/restore notes for upload metadata and domain ingestion records.

Frontend tasks:

- Add clear retry behavior when validation/import tasks fail.
- Add stale worker/scheduler state when progress cannot continue.
- Add admin-only replay/replacement affordances.

Security tasks:

- Add antivirus scanning or deployment hook if required by production policy.
- Confirm retention policy with privacy inventory.
- Confirm audit log review workflow.
- Add abuse-case tests for malicious filenames, formula injection, PII columns, huge rows, duplicate uploads, and unauthorized confirm attempts.

Acceptance criteria:

- Ops can detect failed/stuck imports.
- Raw artifacts expire as expected.
- Security tests cover the major file upload risks.
- Source-data ops can be enabled without granting operators Django admin access.

## Phase 9: API Integrations And CSV Reduction

Objective: reduce manual CSV burden as credentials and data-sharing agreements become available.

Backend tasks:

- Add DHIS2 scheduled surveillance pull with mapping configuration.
- Add OpenMRS facility extract connector where applicable.
- Add WorldPop/KNBS processed population refresh path.
- Add OSM/Overpass-derived exposure refresh pipeline.
- Add logistics/stock connector for facility readiness where available.
- Keep CSV upload as fallback and correction path.

Frontend tasks:

- Show feed mode: API, CSV, manual, fallback, or demo.
- Add connector status and last successful fetch.
- Allow admins to disable a CSV feed when an API connector becomes authoritative.

Security tasks:

- Store external credentials in secure configuration only.
- Add per-connector audit and failure reporting.
- Validate API data with the same canonical checks as CSV uploads.

Acceptance criteria:

- CSV uploads become fallback paths for feeds that have stable APIs.
- Operators can still correct source gaps safely.
- API and CSV feeds share the same source freshness and downstream governance.

## Phase 10: External Audit And Gap Closure

Objective: make the plan independently checkable by comparing each phase's implementation claims against actual repository artifacts and runtime evidence.

Backend tasks:

- Add a source-data phase auditor that can run outside normal request paths.
- Maintain a phase audit contract with every phase name, claimed implementation status, and required evidence artifacts.
- For each phase marked implemented, compare claimed implementation artifacts against the repository.
- Check for expected backend modules, tests, settings, Docker/runtime configuration, API routes, frontend routes, and docs where applicable.
- Return a machine-readable report with passed checks, missing artifacts, incomplete artifacts, and phase-level gaps.
- Add tests proving the auditor fails when a claimed artifact is missing or incomplete.
- Run the auditor after every phase before starting the next implementation phase.

Frontend tasks:

- Later, expose the latest audit summary in an admin/system view once audit reports are persisted.
- Keep the initial auditor CLI/module-only so the audit mechanism can be used before the source-data UI exists.

Security tasks:

- Treat audit output as operational metadata; do not include raw upload data or sensitive row values.
- Include permission, PII, retention, and leakage checks in the phase-specific evidence requirements as those phases are implemented.
- Require gaps found by the audit to be either remediated or explicitly accepted with owner, reason, and expiry.

Acceptance criteria:

- The auditor lists every source-data ops phase from Phase 0 through Phase 10.
- Implemented phases have concrete evidence checks, not only prose.
- Gaps found by the audit are either plugged or explicitly accepted before the next phase begins.
- Phase 0 and Phase 10 have baseline audit checks and tests.
- Future phases must add their audit evidence checks in the same pull/change set that claims implementation.

## 2026-05-05 Cold Re-Audit Closure

A skeptical re-audit against the implemented phase claims found and closed these gaps:

- Formula injection detection was previously bounded by sampled-row inspection. Validation now scans every CSV cell for spreadsheet formula prefixes before domain ingestion, with capped issue reporting to avoid unbounded diagnostics.
- Production surveillance truth was documented as risky, but confirmed surveillance/case-truth imports were not independently classified for maker-checker approval. Validation now records truth and case-class counts, and confirm import now requires second-admin approval for confirmed surveillance truth.
- Downstream feature rebuild requests stored an `as_of` value but did not pass it through to the lead-time feature builder. The builder now accepts an explicit source cutoff, applies the earlier of prediction cutoff and requested source cutoff, and records cutoff lineage.
- The dashboard was using browser wall-clock time as the downstream rebuild `as_of`. It now derives the cutoff from the upload source timestamp and refuses to build a downstream payload when that source timestamp is missing or invalid.
- Artifact cleanup existed as a task but was not scheduled. Celery Beat now schedules the cleanup task daily using `SOURCE_DATA_ARTIFACT_CLEANUP_HOUR` and `SOURCE_DATA_ARTIFACT_CLEANUP_MINUTE`.
- The phase auditor was too artifact-focused to catch these implementation gaps. It now checks for the specific controls above, including strengthened tests and scheduler evidence.

Verification evidence after remediation:

- Docker-backed source-data phase test suite: 77 tests passing.
- Docker-backed Django system check: no issues.
- Docker-backed phase auditor: 75 checks passing across Phase 0 through Phase 10, with 0 open gaps.
- Frontend source-data page tests and TypeScript check passing.

## Suggested Implementation Order

1. Feed registry and template downloads.
2. Upload batch models and dry validation.
3. Confirm import and history.
4. Source overview and freshness.
5. Downstream rebuild controls.
6. Facility readiness snapshot ingestion.
7. UX polish and operator training.
8. Production hardening.
9. API integrations.
10. External audit and gap closure after every phase gate.

This order gives value early: operators can download templates first, then validate files, then import safely, then get the full control-room experience.

## Testing Strategy

Backend tests:

- Feed registry completeness.
- Template headers match adapter specs.
- Template examples validate.
- Upload file constraints.
- PII column rejection.
- PII sampled-value rejection.
- Role permission matrix.
- Maker-checker approval for risky imports.
- Dry validation does not mutate domain records.
- Confirm import creates the expected ingestion run.
- Confirm import records Celery task ID and domain ingestion run linkage.
- Duplicate upload detection.
- Replacement reason enforcement.
- Leakage-safe downstream rebuilds.
- Rejected-row diagnostic export.
- Artifact retention cleanup.
- Facility readiness snapshot ingestion.
- Downstream action permission and audit events.
- Phase-auditor gap detection for missing claimed artifacts.
- Phase-auditor coverage for every implemented phase claim.

Frontend tests:

- Overview renders feed statuses.
- Template download route proxies backend response correctly.
- Upload wizard happy path.
- Validation error path.
- Confirmation disabled for rejected uploads.
- Role-blocked access.
- Import polling success and failure states.
- Rejected-row download action.
- Responsive layout smoke tests for source-data page.

E2E tests:

- Download template.
- Upload synthetic surveillance CSV.
- Validate.
- Confirm import.
- Regenerate labels.
- Rebuild features with source cutoff checks.
- Confirm source freshness updates.
- Confirm no SMS is sent.
- Run the source-data phase auditor and resolve any unaccepted gaps.

## Release Plan

Development rollout:

1. Enable templates behind dashboard navigation only.
2. Enable upload validation for admins and supervisors.
3. Enable confirm import in local/staging.
4. Run synthetic e2e feeds through the ops surface.
5. Run one real or partner-provided sample file through staging.
6. Add readiness snapshot ingestion.
7. Enable production/pilot with raw artifact retention and audit review.

Feature flags:

- `SOURCE_DATA_OPS_ENABLED`
- `SOURCE_DATA_IMPORT_CONFIRM_ENABLED`
- `SOURCE_DATA_DOWNSTREAM_ACTIONS_ENABLED`
- `FACILITY_READINESS_SNAPSHOT_IMPORT_ENABLED`
- `SOURCE_DATA_API_CONNECTORS_ENABLED`
- `SOURCE_DATA_PHASE_AUDIT_REQUIRED`

## Definition Of Done

The source-data ops surface is done when:

- Operators do not need Django admin or CLI access to provide routine source CSVs.
- Every MVP feed has a downloadable template.
- Every upload is validated before import.
- Every import is linked to source metadata, actor, file hash, and ingestion run.
- Rejected rows are understandable and downloadable.
- Freshness states show source gaps honestly.
- Facility readiness snapshots have a source-data path.
- Downstream rebuilds are available but guarded.
- Seeded/demo/fallback data cannot be mistaken for production evidence.
- Tests cover permissions, validation, import, audit, and frontend flows.
- The phase auditor passes for every phase claimed as implemented, with no unaccepted gaps.
- The UX is calm, clear, accessible, and resilient enough for county operators working under real operational pressure.
