# Source Data Ops Phase 0 Alignment

Status date: 2026-05-05

Implementation contract: `backend/risk/source_data/phase0.py`

Phase 0 locks the source-data ops scope before API and UI implementation. It confirms feed scope, role policy, risky-import approval, lifecycle states, retention, shared upload storage, threat model, and UX blueprint.

## Feed Scope

MVP feeds:

| Feed key | Backend target | Source type | Cadence |
| --- | --- | --- | --- |
| `surveillance_weekly_aggregate` | `ingest_surveillance` | `weekly_aggregate` | Weekly minimum |
| `surveillance_daily_aggregate` | `ingest_surveillance` | `daily_aggregate` | Daily where available |
| `surveillance_backfill` | `ingest_surveillance` | `csv_backfill` | One-off, then corrections |
| `population_baseline` | `ingest_population_exposure` | `population_baseline` | Annual/source-change driven |
| `gridded_population` | `ingest_population_exposure` | `gridded_population` | Quarterly/source-change driven |
| `settlement_layer` | `ingest_population_exposure` | `settlement_layer` | Quarterly/source-change driven |
| `wash_vulnerability_layer` | `ingest_population_exposure` | `wash_vulnerability_layer` | Quarterly or assessment-change driven |
| `water_body_distance_layer` | `ingest_population_exposure` | `water_body_distance_layer` | Quarterly/source-change driven |
| `flood_exposure_layer` | `ingest_population_exposure` | `flood_exposure_layer` | Monthly in rainy season, event-driven after floods |
| `facility_catchment_mapping` | `ingest_population_exposure` | `catchment_mapping` | Setup, then facility/catchment changes |
| `facility_readiness_snapshot` | New readiness snapshot ingestion path | `readiness_snapshot` | Weekly routine, daily during alerts |

Later feeds:

- DHIS2 API scheduled pull.
- OpenMRS facility extracts.
- WorldPop/KNBS processed source pulls.
- OSM/Overpass exposure refresh.
- Logistics/stock system integration for readiness commodities and capacity.

## Role Policy

| Role | Decision |
| --- | --- |
| Admin | Full source-data ops, replacements, approvals, downstream actions, retention controls |
| Supervisor | View, template download, upload, validate, routine confirm, request approval, download diagnostics, downstream action request |
| Analyst | View and template download only |
| CHV | No source-data ops access |
| Superuser | Emergency override through documented admin/incident workflow only |

Risky imports require maker-checker approval:

- Historical backfills.
- Replacement imports.
- Replay imports.
- Production surveillance-truth imports.
- Unusually large source deltas.
- Production downstream rebuilds.

The uploader/requester cannot approve their own risky import. Approval decisions must store actor, timestamp, reason, risk category, and affected feed.

## Lifecycle

Upload batch statuses:

```text
draft
uploaded
validating
validation_failed
ready_for_confirmation
confirming
imported
import_failed
cancelled
superseded
```

Approval state is tracked separately:

```text
not_required
pending
approved
rejected
expired
```

## Retention

| Artifact | Decision |
| --- | --- |
| Raw uploads | Default 60 days; allowed deployment range 30-90 days |
| Rejected-row diagnostics | Default 30 days; redacted and formula-sanitized |
| Metadata, hashes, counts, audit events | Default 730 days; no raw source values |

## Shared Upload Storage

Chosen MVP storage backend: shared filesystem.

Runtime defaults:

```text
SOURCE_DATA_UPLOAD_STORAGE_BACKEND=shared_filesystem
SOURCE_DATA_UPLOAD_ROOT=/var/lib/cchis/source_uploads
```

Docker now mounts a named `source_uploads` volume into both the Django web container and the Celery worker. Queued validation/import must read artifacts by upload/artifact identity and verify the stored hash. Local process temp files are not acceptable for queued imports.

Production may replace the shared filesystem with object storage if the same web/worker durability, identity lookup, retention, and hash-verification guarantees are preserved.

## Threat Model

| Risk | Mitigation |
| --- | --- |
| Malicious files | CSV-only MVP, extension/content checks, MIME sniffing, size/row limits, formula-injection detection, storage outside web-served paths |
| Accidental PII | Header rejection, sampled first rows and bounded random rows, redacted validation issues, contact fields only in approved readiness/contact workflows |
| Stale/demo source data | Freshness/truth-state badges, source audit blockers, visible seeded/proxy/fallback states |
| Duplicate import | SHA-256 hash, idempotency key, duplicate metadata checks, explicit replay mode, domain-run linkage |
| Unauthorized replacement | Role policy, maker-checker, self-approval block, approval event log, required replacement reason |
| Downstream leakage | Explicit `as_of`, source cutoff inputs, persisted leakage-check results, manual model promotion |

## UX Blueprint

Navigation: add `Source Data` to the primary dashboard nav at `/source-data`, after `Interoperability` and before `CHV Operations`, visible to Admin, Supervisor, and Analyst roles.

Views:

- Overview: feed freshness, truth state, templates, latest batch, owner action, row actions.
- Feed detail: cadence, schema contract, history, validation outcomes, downstream actions.
- Upload wizard: choose feed, upload file/metadata, dry validate, confirm import.
- Validation summary: accepted/rejected rows, warnings, coverage, duplicates, PII safety, downstream impact.
- Import result: timeline, domain ingestion run, row counts, approval decision, recommended downstream action, audit log.

Primary overview columns:

```text
feed
domain
freshness
truth_state
last_successful_import
next_expected
owner
latest_batch_status
```

Primary feed-detail history columns:

```text
batch
source_name
source_timestamp
period_or_release
status
rows
warnings
confirmed_by
domain_run
```

Overview row actions:

```text
download_template
upload_csv
view_history
view_feed_detail
```

Feed-detail row actions:

```text
view_batch
download_errors
request_replay
open_downstream_actions
```

States:

- Empty.
- Loading.
- Failed.
- Stale.
- Demo-backed.
- Success.
