# CCHIS Prototype Technical Capability Audit

Audit date: 2026-08-07<br>
Repository: cchis<br>
Audited baseline commit: 0bc975f586e2a532fe414111a6cc705fc631ddfc (main, equal to origin/main); correction pass is recorded in a forward commit<br>
Environment: local Docker Compose stack, Africa/Nairobi timezone, seeded demonstration database

This document separates the baseline audit from the subsequent correction pass. The baseline hardening release did not establish production readiness. The correction pass closes specific alert-gating, truth-lineage, Compose wiring, frontend image, scheduler-tracking and audit-evidence gaps while retaining the conclusion that the system is not production-ready.

## Executive verdict

CCHIS is a substantial, runnable prototype with a credible local demonstration path from source-data handling and ward risk scoring through decision context, alert workflow, dashboard presentation, CHV triage/offline synchronization, and USSD interaction.

It is not yet a production public-health surveillance or automated early-warning system. The principal limitation is not missing UI: it is truth provenance and operational readiness. The local system is dominated by seeded/demo data, proxy or fallback climate inputs, and seeded surveillance labels. The model governance layer correctly blocks promotion and automated alert eligibility under those conditions, but the repository should not be represented as having validated predictive performance, live external interoperability, live SMS delivery, or confirmed outbreak truth.

### Audit status labels

- **Verified working** — exercised against the running stack or demonstrated by passing automated tests, with the stated scope.
- **Implemented, partially verified** — meaningful code and contracts exist, but live external or end-to-end verification is incomplete.
- **Partial** — usable prototype behavior exists, with a material limitation that prevents the claimed production capability.
- **Planned/documented only** — described in plans/contracts or represented as a future governance state without an operational implementation.
- **Not found** — no implementation or repository evidence was found during this audit.

## What was actually run

The audit used source inspection, backend API calls, a browser pass through the Next.js application, management commands, and the committed automated test suites. A follow-up audit found one remaining population-lineage loophole and added a fail-closed correction without rerunning the full suite locally; the full-suite CI job remains the verifier for that change.

### Stack bootstrap

| Check | Result |
|---|---|
| docker compose config --services | Passed: db, redis, backend, celery_worker, celery_beat, frontend |
| docker compose up --build -d | Passed; PostGIS, Redis, Daphne, Celery worker, Celery beat and the standalone Next.js frontend started; backend, database, Redis, worker and frontend healthchecks were healthy |
| docker compose exec -T backend python manage.py migrate --noinput | Passed; no migrations pending |
| docker compose exec -T backend python manage.py seed_demo_data | Passed; 40 active county/ward records refreshed and demo scenarios/accounts created |
| docker compose exec -T backend python -m compileall -q . | Passed |
| docker compose exec -T celery_worker celery -A core inspect ping --timeout=5 | Passed; one worker online and responding with pong |
| Production-like Django deployment check | Passed with the resolved production Compose env file, provider wiring and no command-line overrides; a regression run with ambient `DEBUG=release` also passed |
| Backend and frontend health endpoints | Passed: `/health/live/`, `/health/ready/` and `/api/health` returned healthy responses; readiness verified database and Redis |

The frontend is a Compose service built as a Node 22 Alpine standalone image. Its browser-facing API/WebSocket origin is compiled through an explicit production build argument; the server-only backend URL remains a separate runtime setting. The correction CI path also health-checks the image and rejects compiled localhost API/WebSocket origins.

The subsequent model-artifact-registry correction pass (2026-08-08) adds explicit candidate registration, SHA-256/size integrity evidence, approval requests/reviews, challenger designation, activation, retirement and explicit-target rollback transitions. It does not approve or activate a model. The local registry remains empty (`active_model_count=0`) and the read-only registry audit reports `NOT_APPROVED_FOR_OPERATIONAL_USE`; this document therefore remains a “not production ready” assessment.

Permitted claim: CCHIS implements a fail-closed model lifecycle registry with artifact integrity, dataset and feature-contract provenance, approval controls, challenger states and explicit rollback targets. No current model is approved for operational use.

### Automated tests and build

| Area | Result |
|---|---|
| Backend Django suite | Baseline: **924 tests discovered; 924 passed**. Correction verification before the follow-up: **937 tests discovered; 937 passed** in 610.734 seconds. The follow-up full suite was intentionally not rerun locally; CI is the verifier for the added regressions |
| Surveillance truth/regression tests | Passed; focused production truth-policy coverage is **22/22**, including source-backed surveillance/climate/population records, missing and cross-ward references, population-value mismatch, cross-dataset label windows, proxy-only labels and superseded references. The population-exposure producer regression also passed **1/1**. Explicit `as_of` timestamps keep historical fixtures deterministic while preserving rolling-window cutoffs and truth gates |
| Frontend Vitest | **64 test files and 294 tests passed** |
| Frontend production build | Passed with the Webpack production build in the native environment and in the final Docker image |
| Frontend TypeScript | `npm run typecheck` passed, including a clean typecheck without a pre-generated `.next` directory |
| Frontend route validator | Passed four cycles, including auth routes, dashboard routes and CSS asset checks |
| Frontend lint | `npm run lint` passed with the committed flat ESLint configuration and no interactive setup |
| Frontend dependency audit | `npm audit --omit=dev --audit-level=high` passed with 0 production vulnerabilities after upgrading to Next.js 16.3.0 |
| Python dependency audit | `pip-audit -r requirements.txt` passed with no known vulnerabilities |

The audit commands generated local model/forecast and demonstration interaction records in the local database. The previously modified `backend/celerybeat-schedule` was pre-existing runtime state, not part of the baseline hardening; the correction pass removes it from Git tracking while retaining the Compose runtime volume for Beat state.

The earlier three Phase 5 failures were caused by date-relative fixtures being evaluated against the current rolling window. They are resolved by threading explicit reference timestamps through surveillance, inference, forecasting and alert/intelligence paths. The remaining production limitation is evidentiary rather than test integrity: local demonstration labels and fallback/proxy climate inputs are still not valid proof of outbreak-prediction performance.

### Hardening delta since the previous audit snapshot

- Added a central production truth policy that blocks seeded/demo labels, static climate fallback, synthetic feature rows, invalid/unmapped wards, missing or unresolved typed source references, inactive/failed source records, mismatched wards or reporting periods, superseded canonical references and unsafe production model metadata before scores or alerts can be produced. Production feature rows now carry typed `population_baseline_record:<id>` references; scoring and promotion resolve them, require live/fresh source-backed population records in the same ward, and require the canonical population value to match the feature value. Production model runs must reference a real label dataset; label counts and truth level are recomputed from referenced surveillance records, every referenced label window must belong to that declared dataset, and proxy evidence cannot satisfy an explicit confirmed-truth claim.
- Added fail-closed guards to training, inference, lead-time features, surveillance label generation, CSV ingestion, source-data rebuild actions, demo/e2e seed commands and scenario simulation.
- Added liveness/readiness endpoints, database/Redis readiness checks, Compose health dependencies, Celery worker health validation and a standalone non-root frontend image.
- Added production-like security validation for secrets, HTTPS, HSTS, secure cookies, trusted origins, forwarded headers and provider configuration.
- Expanded CI to install, audit, lint, type-check, test and build the frontend, smoke-test its production image and compiled origins, validate resolved production Compose, build/validate the backend, run the complete backend suite, run `pip-audit` and fail on production deployment warnings.
- Added [MODEL_CARD.md](../MODEL_CARD.md), [DATASET_CARD.md](../DATASET_CARD.md), [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md), issue forms and a placeholder-only [production environment template](../deploy/production.env.example).

### CHIRPS v3 historical rainfall correction pass

This correction pass adds a dedicated CHIRPS path without changing the existing Open-Meteo forecast connector or weakening the forecast-horizon audit. The selected product is CHIRPS v3.0 `daily/final/sat`; its daily values use IMERG Late V07 disaggregation and the implementation rejects pre-1998 `sat` requests rather than silently mixing variants. `daily/final/rnl` is available as an explicit whole-period alternative for earlier health-label periods. Preliminary products are out of scope.

Implementation evidence:

- `backend/risk/climate/connectors/chirps.py` builds only the allowlisted official UCSB CHC COG URL, prefers one remote COG window per date, falls back to one bounded full download when range access or provenance metadata is unavailable, and computes fractional-cell, coverage-weighted ward means. It rejects no-data gaps below the configured 0.95 coverage threshold and invalid negative/non-finite values.
- `backend/risk/chirps_ingestion.py` and `ingest_chirps_rainfall` persist observed `chirps-v3.0` `LIVE` records with stable provider/version/status/variant/date/ward/processing identities, compact payloads, daily UTC interval timestamps and retrieval/spatial/source hashes. Missing or rejected assets produce failed/partial runs without static fallback.
- Migration `0077_chirps_identity_and_ingestion_lineage` adds durable identity and run lineage storage. `rasterio==1.4.3` and `shapely==2.0.7` are pinned and the Docker image includes the required C++ build toolchain.
- `backend/risk/lead_time_features.py` now exposes CHIRPS observed 7-, 14- and 30-day rainfall totals with source references and an explicit `--retrospective-chirps` mode. Retrospective mode exempts CHIRPS ingestion completion time only; every selected CHIRPS record still requires `valid_date < prediction_date`. The feature schema is `lead-time-feature-v2-chirps-historical`.
- Feature datasets pin one CHIRPS daily variant in lineage (`sat` or `rnl`); the loader and audit reject mixed variants rather than silently combining them.
- `audit_chirps_ingestion --strict` checks genuine LIVE observed records, accepted quality flags, version/status/variant, complete active-ward coverage, canonical ward identity, canonical URL/identity/source-ref/source-run reconstruction, finite non-negative values, no fallback, provenance, coverage, date-range exceptions, persisted CHIRPS-backed feature rows, same-ward feature references, recomputed 7/14/30-day totals, variant pinning and feature cutoffs.

Verification performed on 2026-08-07, with the live CHIRPS backfill and post-run audit completed on 2026-08-08:

| Check | Result |
|---|---|
| `docker compose exec -T backend python manage.py test risk.test_chirps_ingestion -v 1` | **14/14 passed**; includes persisted retrospective loading, dataset-scoped variant selection, real-loader future leakage, recomputation/ward checks, non-vacuous audit failure and strict-audit success. |
| `docker compose exec -T backend python manage.py test risk.test_lead_time_features -v 1` | **9/9 passed**. |
| `docker compose exec -T backend python manage.py makemigrations risk --check --dry-run` | Passed; no pending model changes. |
| Official source HEAD and one-day remote COG window | **Passed** for `chirps-v3.0.sat.2024.01.01.cog`; HTTP content length `17162842`, ETag and Last-Modified were retained, and the extracted window hash was `ab8704666697a0710457d693b6eddc721ac725c337cdc0e0767e58c849decdf1`. |
| Direct bounded 30-day source/raster verification | **Passed** for 2024-01-01 through 2024-01-30 using managed geometry `migori-ward-boundaries:2026-04-25-backfill-clean`: 30 official COG windows, 40 canonical wards per date, 1,200 valid ward/date aggregates, remote-window mode throughout, and minimum ward coverage above 0.95. No raster artifacts were written to the repository. |
| Managed geometry repair | **Passed**; the two exact noncanonical rows `Phase9 Other Ward dac83567` and `Phase9 Supervisor Ward dac83567` were deactivated after confirming they had no managed polygons. They were not hard-deleted because protected historical dependencies exist. The active ward set is now 40/40 covered by the managed geometry version. |
| Live 30-day CHIRPS ingestion | **Passed** with run `36`: 30/30 official assets processed, 1,200 `LIVE` `chirps-v3.0` records created, zero rejected/unavailable assets. Resume run `37` skipped all 1,200 stable identities; normalization rerun `38` updated all 1,200 records without changing identity or row count. |
| Persisted CHIRPS-backed feature dataset | **Passed**: `build_lead_time_feature_dataset --prediction-date 2024-01-31 --retrospective-chirps --chirps-variant sat` created dataset `lead-time-features-lead-time-feature-v2-chirps-historical-2024-01-31-f941018d` with 40 persisted rows; all 40 rows contain CHIRPS references and nonzero 7/14/30-day windows. |
| Strict post-ingestion audit | **Passed**: `audit_chirps_ingestion --strict` scanned 1,200 records across 3 ingestion runs and passed all 12 checks, including accepted quality, canonical source identity, persisted feature evidence, same-ward references, recomputed totals, temporal cutoffs and single-variant pinning. |

The original geometry blocker was resolved by deactivating only those two exact noncanonical rows; their protected historical dependencies remain intact. The requested command then completed against the 40 active canonical wards and persisted 1,200 records for 2024-01-01 through 2024-01-30. The retrospective feature build explicitly permits those 2026-ingested historical records while retaining `valid_date < prediction_date`; it persisted 40 CHIRPS-backed rows for prediction date 2024-01-31. The dataset is pinned to `sat` and the strict audit rejects zero-feature or mixed-variant states.

Independent CHIRPS-backed ward-value spot checks (`prediction_date=2024-01-31`, millimetres). The persisted feature totals were compared with a separate calculation from the 30 official `daily/final/sat` COG windows using the same managed ward geometries and fractional-cell zonal aggregation; the independent calculation did not read the persisted `ClimateRecord` or `FeatureDatasetRow` values. Acceptance tolerance was ±0.01 mm per window.

| Ward | Persisted 7d | Raster 7d | Persisted 14d | Raster 14d | Persisted 30d | Raster 30d | Max abs diff | Source refs |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Bukira Centrl/Ikerege | 24.51 | 24.51 | 65.27 | 65.27 | 143.42 | 143.42 | 0.00 mm | 30 |
| Bukira East | 23.70 | 23.70 | 70.13 | 70.13 | 155.13 | 155.13 | 0.00 mm | 30 |
| Central Kamagambo | 36.06 | 36.06 | 87.68 | 87.68 | 198.78 | 198.78 | 0.00 mm | 30 |

Complete sanitized CHIRPS record lineage example (identifiers and volatile retrieval values intentionally redacted):

```json
{
  "record": {
    "source_provider": "chirps-v3.0",
    "source_kind": "LIVE",
    "source_mode": "final-sat",
    "record_type": "observed",
    "valid_date": "2024-01-01",
    "observed_timestamp": "2024-01-01T00:00:00+00:00",
    "rainfall_mm": "<source value redacted>",
    "quality_flag": "accepted",
    "fallback_flag": false,
    "source_run": "chirps-ingestion:v3.0:final:sat:2024-01-01",
    "source_ref": "chirps:v3.0:final:sat:2024-01-01:ward:<redacted>",
    "identity_key": "chirps-v3.0|v3.0|final|sat|2024-01-01|<ward-public-id-redacted>|chirps-fractional-zonal-v1"
  },
  "lineage_metadata": {
    "provider": "chirps-v3.0",
    "chirps_version": "v3.0",
    "product_status": "final",
    "daily_variant": "sat",
    "source_date": "2024-01-01",
    "official_asset_url": "https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/final/sat/cogs/2024/chirps-v3.0.sat.2024.01.01.cog",
    "asset_filename": "chirps-v3.0.sat.2024.01.01.cog",
    "retrieval_timestamp": "<redacted>",
    "raster_crs": "EPSG:4326",
    "raster_transform": ["<redacted>"],
    "raster_resolution": ["<redacted>"],
    "raster_nodata": "<redacted>",
    "aggregation_method": "fractional_cell_area_weighted_zonal_mean",
    "valid_pixel_count": "<redacted>",
    "ward_coverage_fraction": "<redacted; >= 0.95>",
    "ward_public_id": "<redacted>",
    "ward_geometry_dataset_version": "migori-ward-boundaries:2026-04-25-backfill-clean",
    "ward_geometry_hash": "<redacted>",
    "processing_code_version": "chirps-fractional-zonal-v1",
    "chirps_daily_disaggregation_method": "IMERG Late V07 disaggregation of CHIRPS pentad totals",
    "daily_interval_start": "2024-01-01T00:00:00+00:00",
    "daily_interval_end": "2024-01-02T00:00:00+00:00",
    "daily_interval_timezone": "UTC",
    "etag": "<redacted>",
    "last_modified": "<redacted>",
    "content_length": "<redacted>",
    "hashes": {
      "full_asset_sha256": null,
      "extracted_window_sha256": "<redacted>"
    },
    "source_access_mode": "remote_window",
    "identity_key": "chirps-v3.0|v3.0|final|sat|2024-01-01|<ward-public-id-redacted>|chirps-fractional-zonal-v1",
    "source_ref": "chirps:v3.0:final:sat:2024-01-01:ward:<redacted>",
    "source_run": "chirps-ingestion:v3.0:final:sat:2024-01-01"
  }
}
```

CHIRPS is a gridded satellite/station rainfall estimate, not ward rain-gauge ground truth, real-time rainfall or a 7–14-day forecast. The official references are the [CHIRPS v3 overview](https://www.chc.ucsb.edu/data/chirps3), [daily product documentation](https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/readme.txt), and [v3.0 release notes](https://data.chc.ucsb.edu/products/CHIRPS/v3.0/README-CHIRPSv3.0.txt), accessed 2026-08-07. No claim of improved prediction accuracy is made.

## Architecture and runtime capability

| Capability | Status | Evidence and limitation |
|---|---|---|
| Containerized backend runtime | **Verified working** | backend/Dockerfile, docker-compose.yml, Daphne on port 8000, PostGIS 16/3.4 and Redis 7 started successfully. |
| Asynchronous processing | **Verified working** | Celery worker and beat are present with scheduled ETL, rainfall, risk, facility forecast, cleanup and connector tasks. The worker responds to `celery inspect ping`; backend readiness checks database/Redis and Compose waits on healthy dependencies. Celery beat intentionally has no application health endpoint. |
| Frontend runtime | **Verified working** | Next.js 16.3.0 standalone output runs in a Node 22 Alpine, non-root Compose image on port 3000. Native lint/typecheck/test/build and the container build passed. |
| Database migrations | **Verified working** | 77 risk migration files were applied; migrate --check completed without pending work. |
| PostGIS/geospatial storage | **Verified working** | Django uses the PostGIS engine. The managed migori-ward-boundaries dataset has 40 expected and 40 actual active features, EPSG:4326, with no missing source wards. |
| County/ward seed | **Verified working** | seed_demo_data refreshed 40 active wards and loaded the scenario bundle decision_layer_full_suite. |
| Production deployment packaging | **Implemented, partially verified** | Compose now packages backend, worker, beat, frontend, PostGIS and Redis with health-gated dependencies and a production-like validation path. Managed secret storage, TLS termination, external ingress, backups and production orchestration remain deployment responsibilities. |

The principal backend routes are versioned below /api/v1/; the unversioned /api/wards/ probe returned 404. The public schema endpoint exposed OpenAPI 3.0.2 with 139 paths.

## Capability matrix: current implementation

### 1. Identity, authentication, authorization and privacy

| Capability | Status | Audit finding |
|---|---|---|
| Username/password login | **Verified working** | Analyst and CHV logins returned access/refresh tokens. Login failure and throttling paths are covered by tests; repeated login activity produced HTTP 429 as configured. |
| Admin/supervisor TOTP | **Verified working** | A real seeded admin login returned a temporary token; a current TOTP code accepted by /api/v1/auth/verify-2fa/ returned a usable access token. Admin and supervisor are required-policy roles. |
| Refresh rotation and logout | **Verified working** | Analyst refresh returned rotated tokens; logout returned HTTP 205 and invalidated the session state. |
| Password recovery privacy | **Verified working** | Unknown-account recovery returned the generic response, “If the account exists and is eligible for recovery...” without account enumeration. |
| Role capabilities | **Verified working** | Admin, supervisor, analyst and CHV contracts are explicit in backend/accounts/role_capabilities.py. Analyst is broad read-only; CHV is ward-scoped and field-focused; admin/supervisor have operational controls subject to step-up. |
| Ward scope enforcement | **Verified working** | CHV offline contract resolved to ward 1, and backend tests/API permissions enforce ward scope. Analyst received HTTP 403 on CHV operations, USSD logs, sensitive exports and restricted mutations. |
| Fresh step-up protection | **Verified working** | Admin trigger context and preview were available; a direct trigger without fresh step-up returned HTTP 403 with a security-check message. |
| Origin/CSRF/cookie protection | **Implemented, partially verified** | CookieAuthOriginMiddleware, Django CSRF, BFF request-origin validation and security headers are present. Local responses included X-Frame-Options, nosniff and same-origin referrer policy. |
| Rate limiting | **Verified working** | Scoped throttles exist for auth, 2FA, recovery, USSD, source uploads and other writes; a live login sequence hit the configured throttle. |
| Privacy minimization | **Verified working** | audit_privacy_controls --format=json returned pass with no high-risk or warning findings, including CHV ward scope, consent/override, phone integrity, export attribution and direct-identifier masking. |
| Durable non-auth domain audit | **Planned/documented only** | docs/DOMAIN_AUDIT_READINESS.md states that the durable audit store currently implemented is AuthAuditEvent; a general domain audit/event ledger is not implemented. |
| Enterprise identity/SSO/secrets manager | **Not found** | No repository evidence of OIDC/SAML/enterprise SSO or an external secrets manager integration was found. |

### 2. Ward, map and spatial intelligence

| Capability | Status | Audit finding |
|---|---|---|
| Ward map GeoJSON | **Verified working** | Authenticated /api/v1/maps/wards/ returned GeoJSON features and metadata; the browser map rendered a current-risk view. |
| Ward risk scope and detail | **Verified working** | /api/v1/wards/ returned 42 wards to an analyst; ward UI showed current risk, score, update age, workflow activity and action signals. |
| PostGIS boundary provenance | **Verified working** | Active dataset source, version, license, EPSG and importer metadata are stored and exposed by the geometry-status audit. |
| Population/spatial exposure features | **Implemented, partially verified** | Population density, settlement concentration, floodplain exposure, water-body proximity and WASH vulnerability appear in model/decision features. External population and settlement connectors were not configured locally. |
| Live flood or satellite hazard feed | **Not found** | Flood-related fields and policy language exist as proxy/model features; no live flood or satellite hazard integration was verified. |

### 3. Source data, ingestion and truth provenance

| Capability | Status | Audit finding |
|---|---|---|
| Source-data registry and readiness model | **Implemented, partially verified** | The API and source-data screen render feed status, freshness, truth state, missing data and upload state. The earlier local snapshot reported 14 items needing attention, 2 up to date, 3 demo-backed and 0 ready to add; those values remain demo-database observations rather than production readiness evidence. |
| Rainfall ingestion orchestration | **Partial** | Hybrid Open-Meteo plus static fallback code and scheduled ingestion exist. Static fallback remains useful for local demonstration but is now explicitly blocked from production feature datasets and model runs. |
| Observed rainfall | **Implemented, partially verified** | The legacy Open-Meteo climate audit remains a separate path with 936 legacy climate records, 4,394 fallback records and 774 forecast records; its maximum forecast lead remains 3 days, so 7- and 14-day forecast-horizon support still fails. Independently, the CHIRPS path has 1,200 persisted `LIVE` records for 30 dates across 40 canonical wards and a 40-row CHIRPS-backed historical feature dataset, with a passing strict ingestion audit. |
| Climate data quality | **Partial** | The same audit reported missing/invalid ward values in 4,232 records and 5 invalid rainfall values. Strict mode would fail the audit. audit_climate_horizon also found missing climate evidence fields in 2 risk scores and incomplete climate evidence in 57 of 62 linked alert payloads. |
| CHIRPS | **Implemented, partially verified** | CHIRPS v3.0 final daily `sat` is implemented as a dedicated official COG connector with bounded ingestion, durable identity, fractional zonal means, provenance and strict audits. The requested backfill persisted 1,200 `LIVE` records for 40 canonical wards; an explicit retrospective feature build persisted 40 CHIRPS-backed rows for 2024-01-31 with `sat` pinned and passed the strict audit. |
| Surveillance ingestion | **Implemented, partially verified** | Ingestion runs, source records, label windows and feature datasets exist. Production ingestion now preflights inactive/unmapped wards, seeded sources and seeded labels before canonical persistence; local demonstration ingestion remains supported. |
| Confirmed surveillance truth | **Not ready / Partial** | All local surveillance records and label windows were seeded_demo; the truth audit found no reliable confirmed-case truth basis. It reported 2,400 confirmed-case records without confirmed truth and 60 non-confirmed windows containing confirmed cases. |
| Correction and supersession lineage | **Partial** | Replay/correction audit failed: 2,880 superseded records were used in label windows, with 1,440 records carrying supersession references. The correction pass adds a stable production blocker and revalidates referenced records at promotion/scoring/alert time; real-source cleanup is still required. |
| External source connectors | **Implemented, partially verified** | Connector registry exposes DHIS2, OpenMRS, WorldPop/KNBS population, OSM Overpass settlement and logistics readiness. All five were configured=false in the local environment; interoperability had 0 systems, 0 mappings and 0 transfer runs. |
| Production truth boundary | **Verified working as a safety block** | `backend/risk/truth_policy.py` centralizes stable blocker codes. Production alerting now requires a linked successful `ModelRun`, an actual referenced label dataset, typed surveillance/climate/population references that resolve to active successful source records with matching ward and reporting period/value, recomputed label counts/truth, label-window ownership within the declared label dataset and the active promoted registry entry; API gating occurs before workflow/task mutation and the Celery/service layers re-check. Proxy context is allowed as caveat evidence, while explicit proxy-as-confirmed claims, synthetic fallback, invalid geography and superseded references fail closed. |
| Upload and dry-validation workflow | **Partial** | Backend/source-data API contracts and upload objects exist. Production CSV ingestion now rejects seeded or unmapped ward data before canonical persistence; the complete operator UI and external feed contract testing remain incomplete. |

The most important operational truth snapshot was:

| Feed state | Local count/state |
|---|---|
| Current | 3 |
| Demo-backed | 2 |
| Stale | 2 |
| Missing | 9 |
| Truth state | 2 fallback, 2 CSV-backed, 3 derived, 9 missing |

The weekly surveillance screen also showed a demo-backed source timestamp 92 days old; gridded population was approximately 340 days stale and facility readiness approximately 90 days stale.

### 4. Machine learning and model operations

| Capability | Status | Audit finding |
|---|---|---|
| Logistic-regression risk scoring | **Verified working** | run_risk_model --month=8 --model-version=lr-audit2-20260807 --algorithm=logistic_regression completed and created 42 risk scores. The scheduled default is lr-v1. |
| Random-forest benchmark | **Verified working** | run_random_forest_benchmark --month=8 --model-version=rf-audit2-20260807 completed and created 42 benchmark scores. This is not evidence of production performance. |
| Model feature generation | **Implemented, partially verified** | Features include rainfall, CHIRPS observed 7/14/30-day totals, flood indicator, historical cases, seasonality, population proxies, settlement concentration, floodplain exposure, water-body proximity and WASH vulnerability. A persisted 40-row CHIRPS-backed historical dataset now proves the real loader path; feature provenance, retrospective-mode exception and typed population-baseline references are persisted. Production still blocks seeded labels, static/synthetic fallback rows, invalid geography, missing/unresolved source references, population ward/value mismatches and stale or superseded canonical references. |
| XGBoost | **Planned/documented only** | Catalogued as candidate-only and non-runnable; package/operational path is absent. |
| LightGBM | **Planned/documented only** | Catalogued as candidate-only and non-runnable; package/operational path is absent. |
| 7/14-day lead-time forecasting | **Partial** | Date-bounded label-window schemas and 7/14-day validation fields exist, but climate data only reached a 3-day horizon and the lead-time truth is seeded rather than a validated real-outbreak dataset. |
| Model version metadata | **Implemented, partially verified** | Model runs and risk scores retain model-version, snapshot and decision-policy metadata. Production model-run blockers also reject demo model versions such as `v0-demo`. |
| Production model truth gate | **Verified working as a safety block** | Seeded training/inference, seeded simulation lineage, static/synthetic rainfall or population fallback, missing/unresolved canonical references, invalid row geography, cross-ward or value-mismatched population references, cross-dataset label windows, superseded references, proxy-only confirmed labels and demo model metadata are blocked in production. Blocked runs do not create scores or alerts and record stable reason codes for review. |
| Model artifact registry | **Implemented, partially verified** | `ModelRegistryEntry` now persists a stable registry version, model/run and dataset references, ordered feature contract, evaluation metrics, code commit, artifact location/format/size/SHA-256 and intended/prohibited use. `ModelGovernanceEvent` is append-only. The focused registry tests pass; the local registry has 0 entries and 0 active models, so no operational artifact is claimed. |
| Promotion governance | **Implemented, partially verified as a safety block** | Registration, approval request/review, challenger designation, activation, retirement and explicit-target rollback are separate actor/reason transitions. Database constraints and the production gate require an approved active entry with intact artifact and truth/feature evidence. No current model is approved or active. |
| Monitoring and drift | **Planned/documented only** | run_model_monitoring failed with active_model_registry_entry_missing; score-distribution baselines and active-model monitoring are not operational. |
| Model evaluation | **Partial** | Evaluation reports training accuracy and row count, with RF feature importance. No held-out/out-of-time performance, calibration, PR/ROC analysis, threshold utility or live outbreak lead-time validation was found. |
| Active production model | **Not ready** | /api/v1/model-operations/health/ reported no active model and “Not ready for operational use”; the UI correctly showed no approved forecast live. |

The implementation is technically capable of producing scores. The evidence does not support the claims “validated predictor,” “confirmed case predictor,” “7–14 day accurate warning,” or “production-ready model.”

### 5. Decision policy, alerts and communications

| Capability | Status | Audit finding |
|---|---|---|
| Risk-level decision policy | **Verified working** | Live wards showed low/medium/high levels, scores, predicted cases, freshness and workflow state. Threshold and evidence metadata are carried into risk/alert records. |
| Guided alert context | **Verified working** | Admin context for North Kamagambo returned high risk 0.88, workflow DELIVERED, trigger active, recommended trigger type and recipient count. |
| Alert preview | **Verified working** | Admin preview returned a backend-generated message, editable-preview support, dashboard/SMS channel defaults and recommended action. |
| Alert confirmation/step-up | **Verified working** | Direct confirmation without fresh step-up returned 403. Backend tests cover authenticated trigger paths; this audit did not enqueue a new alert because that would mutate operational state unnecessarily. |
| Alert workflow state | **Verified working** | Alerts screen and API displayed delivered, retry and failed records. The local system-readiness snapshot showed 62 alerts, 59 delivered, 2 waiting and 1 failed. |
| Automatic alert eligibility under weak truth | **Verified working as a block** | Latest model metadata set alert_eligible=false and recorded blockers. This is the correct prototype safety behavior but means the automated production workflow is not currently available. |
| SMS provider | **Partial** | Stub SMS mode is active locally. An Africa’s Talking adapter exists using raw HTTP and is queue-only unless credentials/configuration are present; no live provider delivery was verified. |
| Message governance | **Partial** | The UI/API reported 21/22 messages ready, 2 needing review and 95.2% local delivery success, while also showing missing Kiswahili/Dholuo message warnings. Governance records exist; actual language rollout and provider delivery are not proven. |
| Email/other external notification | **Partial** | Stub/Mailgun provider abstractions exist, but no production outbound configuration was verified. |

### 6. CHV field workflow, offline support and USSD

| Capability | Status | Audit finding |
|---|---|---|
| CHV authentication and ward scope | **Verified working** | chv_demo authenticated with role CHV, ward scope North Kamagambo, and no dashboard access. The offline contract returned chv-offline-v1, assigned-user ward scope and supported en, sw and luo. |
| CHV triage/recommendation/referral | **Verified working** | Live POST to /api/v1/chv/triage/ returned 201 for diarrhea, vomiting and dehydration, produced high cholera suspicion guidance, referral-needed=true, and selected North Kamagambo Dispensary. Sensitive fields were marked redacted. |
| Offline sync | **Verified working** | Live POST to /api/v1/chv/sync/ returned 201, PROCESSED, ACCEPTED, with a server receipt and domain record. |
| Offline idempotency/replay | **Verified working** | Reposting the same client submission returned 201 with conflict_state=REPLAYED and replayed=true against the same sync queue item. |
| Browser CHV workflow | **Implemented, partially verified** | frontend/app/chv/page.tsx, frontend/lib/chv-offline-api.ts and frontend/lib/chv-offline-store.ts implement local drafts, retention, device identity, bundle caching and pending/failed/conflict sync states, with tests. The analyst dashboard intentionally redirects /chv to unauthorized; the CHV page is field-role gated. |
| Installable PWA/service worker | **Not found** | LocalStorage-based offline behavior is present, but no service-worker/workbox/manifest implementation was found. This is a browser offline client, not yet a demonstrably installable background-sync PWA. |
| USSD public menu | **Verified working** | /api/v1/ussd/menu/ returned language selection, English menu, child-diarrhea submenu, safety guidance and invalid-option handling, all HTTP 200. |
| USSD language/session logging | **Verified working** | Five live requests for one session were persisted with outcomes STARTED, IN_PROGRESS, COMPLETED and INVALID_INPUT; the session used the built-in menu version. |
| USSD telecom gateway | **Partial** | The public application endpoint and logging are real; no external telecom callback/provider deployment was verified. |

### 7. Facility readiness, capacity and forecasts

| Capability | Status | Audit finding |
|---|---|---|
| Facility readiness view | **Verified working** | Browser/API view showed 7 facilities assessed, 4 high calculated-risk facilities, an estimated ORS measure and actionable facility rows. The UI explicitly says it is calculated from ward risk and facility identity, not live stock feeds. |
| Facility capacity signals | **Partial** | Capacity concerns and review queues are modeled and displayed, but no live stock, staffing, bed, referral or roster feeds were found. |
| Facility burden forecast | **Implemented, partially verified** | run_facility_burden_forecast --model-version=fnb-audit2-20260807 --horizon-days=7 completed successfully. API state was phase_2_baseline_implemented_not_promoted and governance was preview_only. |
| Forecast promotion | **Planned/documented only** | Blockers included proxy training targets, missing real facility case history, missing out-of-time validation, incomplete threshold review and pending operational promotion review. |

### 8. Dashboard and operator experience

| Capability | Status | Audit finding |
|---|---|---|
| Overview | **Verified working** | Live cards, map, recent alerts, action-required wards and facility readiness signals rendered from BFF/backend data. |
| Wards and ward decisions | **Verified working** | Live 42-ward table showed score, risk level, update age and queue signals. |
| Alerts | **Verified working** | Live delivery states, failures, retry records and review counts rendered. |
| Facility readiness | **Verified working with explicit caveat** | Calculated readiness and forecast preview rendered; the limitation text correctly disclaimed live inventory/staffing feeds. |
| Model health | **Verified working as governance UI** | The screen correctly showed “Not ready for operational use,” no approved model, testing-only versions and zero readiness of four checks. |
| Source data | **Verified working with incomplete Phase 7 surface** | Live feed freshness, missing/demo/stale states and upload readiness rendered. Source-phase audit found missing expected operator UI sections and tests. |
| Interoperability | **Verified working as an empty boundary** | Live screen correctly showed 0 external systems, 0 mappings and 0 transfers plus a not-set-up state. It is not evidence of a connected national-system integration. |
| System readiness | **Verified working** | Live screen summarized risk freshness, alert delivery failures, CHV activity and safe operator actions. |
| Operational metrics | **Partial** | Fourteen measures were configured, but the selected periods had 0 reporting data. This is a functioning empty state, not an operational KPI result. |
| Message governance | **Verified working with data gaps** | Live readiness/review counts and language warnings rendered. |
| Preparedness actions | **Verified working** | Two active/overdue local actions rendered with queue status and assignment state. |
| CHV operator dashboard | **Partial by design** | The web dashboard is intentionally limited to admin/supervisor/analyst roles; CHV uses the field page/contracts rather than the operator dashboard. |

The browser pass found a hydration warning attributable to a Chrome extension-added cz-shortcut-listen attribute and extension async-response messages. No product-specific browser exception was observed.

## Current versus planned capability matrix

| Capability claim | Current status | What can safely be claimed today |
|---|---|---|
| Secure role-based county/ward platform | **Verified working** | Authenticated local platform with role and ward controls, TOTP for privileged roles, step-up for high-risk actions. |
| PostGIS ward intelligence | **Verified working** | Managed 40-feature Migori ward geometry and GeoJSON/dashboard rendering. |
| Multi-source public-health ingestion | **Implemented, partially verified** | Registries, adapters, uploads and freshness contracts; no configured DHIS2/OpenMRS/logistics/OSM production source. |
| Observed rainfall/CHIRPS foundation | **Implemented, partially verified** | The CHIRPS v3 historical connector and lagged feature contract are implemented; real official COG aggregation and persistence passed for 40 canonical wards across 30 dates, yielding 1,200 audited records, and the retrospective loader persisted 40 CHIRPS-backed feature rows with a pinned `sat` variant. Forecast evidence remains limited to the separately audited three-day path. |
| Confirmed surveillance truth | **Partial** | Seeded surveillance records and truth-gate logic exist; no verified confirmed-case label source. |
| Logistic risk model | **Verified working as prototype scoring** | Local scores can be produced; promotion is blocked and performance is not validated. |
| Random Forest | **Verified working as benchmark** | Manual benchmark command runs; no promotion or out-of-time evidence. |
| XGBoost/LightGBM | **Planned/documented only** | Candidate catalog entries, no runnable installed implementation. |
| 7–14-day lead time | **Partial** | Contracts and validation scaffolding exist; current climate evidence reaches only 3 forecast days and truth is seeded. |
| Model registry/promotion/rollback | **Implemented, partially verified** | Explicit artifact/lifecycle governance, immutable events, integrity checks, read-only admin surface and focused tests exist; the local registry intentionally has no approved model, active target or rollback event. |
| Automated alerting | **Partial** | Alert records, workflows, context and delivery states work; weak-input model runs are not alert-eligible. |
| Live SMS | **Partial** | Stub and Africa’s Talking adapter exist; live credentials/provider delivery are not configured. |
| CHV offline field workflow | **Verified working for API/browser-local prototype** | Triage, local storage, bundle contract, sync, replay and privacy behavior work; no installable service-worker PWA verified. |
| Facility readiness/forecasting | **Partial** | Calculated readiness and preview-only baseline forecast work; live facility feeds and promotion are absent. |
| DHIS2/OpenMRS interoperability | **Implemented, partially verified** | Boundary contracts and connector registry exist; 0 live systems/mappings/runs in the audited environment. |
| Production auditability | **Partial** | Auth audit and selected privacy/export evidence exist; general domain audit ledger is not implemented. |
| UNICEF/DPG readiness | **Planned/documented only / not ready** | Open-source scaffolding, governance documents, production-like security checks and CI now exist, but data/model truth, external interoperability, operational evidence and performance validation remain insufficient for a production or performance claim. |

## End-to-end flows

### Flow 1 — Climate/source data → risk score → decision → alert → dashboard

**Status: Partial, demonstrable locally.**

1. Celery scheduling and run_risk_model are wired.
2. The model command successfully generated LR and RF scores for 42 wards.
3. Ward risk and decision metadata were exposed through /api/v1/wards/, /api/v1/risk-scores/, ward intelligence and the dashboard.
4. Alert workflow records and delivery states were visible in the Alerts and System screens.
5. Admin context and preview worked; confirmation was protected by fresh step-up.
6. Promotion/alert eligibility was blocked because current training labels and source inputs are seeded/proxy/fallback.
7. SMS was in stub mode; no live provider delivery was proven.

The flow is suitable for a controlled demo. It is not a verified live surveillance-to-warning pipeline.

### Flow 2 — CHV login → triage → recommendation/referral → offline sync/logging

**Status: Verified working within local prototype scope.**

The live CHV test authenticated a ward-scoped CHV, generated an urgent referral recommendation to the ward facility, synced a symptom payload, received a server receipt, and replayed the same idempotency key without creating a duplicate. Response privacy metadata marked sensitive echoes as redacted.

### Flow 3 — Supervisor → ward → high-risk review → preparedness → alert review

**Status: Implemented, partially verified.**

Ward risk tables, action queue, alerts, guided trigger context, preview and step-up boundary all work. The audit did not enqueue a new supervisor alert because that is a state-changing operational action; backend tests cover supervisor authorization and trigger behavior. A complete live supervisor mutation cycle should be re-run in a disposable integration environment when external delivery and operational credentials are available.

### Flow 4 — Facility readiness → forecast → review/promotion → dashboard

**Status: Partial.**

The facility forecast command completed and the readiness UI rendered facility concerns and a seven-day calculated outlook. The API explicitly reports preview-only, not promoted, with missing real facility history, out-of-time validation and operational review. The UI correctly labels the outputs as estimates rather than live stock/capacity truth.

### Flow 5 — USSD request → menu → result → logging

**Status: Verified working within application scope.**

The live public endpoint handled language selection, English menu navigation, child-diarrhea guidance and invalid input. Five requests for one session were persisted with lifecycle outcomes. A telecom gateway or production handset test was not part of the local stack.

## Security and privacy findings

### Strengths verified

- TOTP policy and fresh step-up are enforced for privileged/high-risk actions.
- JWT access/refresh rotation and session checks are implemented.
- Ward-scoped field access and role serializers reduce direct identifier exposure.
- Cookie-origin, CSRF and BFF request-security checks are present.
- Auth audit events, throttles and password-recovery anti-enumeration behavior are implemented.
- Privacy-control audit passed with no high-risk findings.
- Backend response headers included X-Frame-Options, nosniff, same-origin referrer policy and same-origin opener policy.

### Deployment configuration status

The correction pass makes the production profile self-consistent: the project-scoped `CCHIS_DJANGO_DEBUG` input maps to Django's `DEBUG` container variable, HSTS include-subdomains/preload, Mailgun and Africa's Talking variables are resolved through Compose, and live providers fail startup when required credentials are absent. The CI acceptance command is `docker compose --env-file deploy/ci-production.env run --rm --no-deps backend python manage.py check --deploy --fail-level WARNING`, without command-line overrides; the same command also passes with ambient `DEBUG=release`, proving a host-wide debug variable cannot collide with the production profile. [deploy/production.env.example](../deploy/production.env.example) is intentionally placeholder-only and must be replaced by a deployment secret manager or equivalent protected configuration.

The local profile remains intentionally developer-friendly and should not be treated as a production security profile. TLS termination, external ingress headers, secret storage, backups, key rotation and infrastructure-level network policy still require deployment-specific verification. The frontend now disables the Next.js powered-by header and keeps its internal backend URL server-only; a full CSP policy remains an ingress/deployment concern.

The previous Next.js 15 dependency finding is resolved in the repository by the Next.js 16.3.0 upgrade. Production-only npm audit now passes with zero vulnerabilities; the full development install still reports non-production findings, so development dependency remediation remains a maintenance task rather than a production release blocker.

## Testing, CI and maintainability

### CI coverage currently present

`.github/workflows/ci.yml` now installs Node 22 dependencies, runs the production-only npm audit, lint, type-check, frontend tests and production build, builds and smoke-tests the frontend production image, validates resolved production Compose, builds the backend, starts database/Redis, runs compileall and the complete backend suite, runs `pip-audit`, and executes the production-like Django deploy check both normally and with ambient `DEBUG=release`. Cleanup runs even when a job fails. It does not yet enforce coverage, schema drift, strict climate/surveillance audit results, active model promotion/monitoring, or authenticated browser-level smoke tests.

### Quality risks

1. There is no measured coverage configuration in the backend requirements or CI workflow.
2. Strict climate/surveillance audits and real-source quality thresholds are not yet release gates.
3. No active model registry/monitoring state means operational monitoring cannot be validated end-to-end.
4. External DHIS2/OpenMRS, climate, population, settlement, logistics and SMS providers remain unconfigured in the audited environment.
5. No installable service-worker PWA or browser-level smoke suite is part of the release gate.

## Open-source and DPG-readiness observations

| Area | Finding |
|---|---|
| License | LICENSE is present. |
| Documentation | README.md is extensive and includes local setup, API surface, role contract and security/deployment notes. |
| Security reporting | SECURITY.md is present with private vulnerability-reporting guidance. |
| Contribution guidance | CONTRIBUTING.md is present. |
| Code of conduct | **Present** in CODE_OF_CONDUCT.md. |
| Issue templates | **Present** for bugs, features, data-quality/truth provenance and configuration issues. |
| Model card/datasheet | **Present** in MODEL_CARD.md and DATASET_CARD.md; both retain prototype limitations, provenance constraints and prohibited-use guidance. |
| Data/privacy governance | Privacy audit and operator-handling documentation exist; confirmed truth, consent, retention and lawful sharing still need deployment-specific evidence. |
| Reproducibility | Docker/seed commands, scenario bundles and locked frontend dependencies are useful; real-source reproducibility and deployment-specific dependency/update policy still need strengthening. |
| Interoperability | Boundary contract is explicit, but no live DHIS2/OpenMRS/other transfer evidence exists. |

## Priority recommendations

### P0 — required before any operational or performance claim

1. **Correction pass implemented; readiness remains open.** `backend/risk/truth_policy.py` and downstream guards prohibit seeded/demo truth, static/synthetic fallback, missing/unresolved source references, invalid/unmapped geography, source-status/reporting-period mismatches, superseded canonical references and explicit proxy-as-confirmed claims from production scoring/alerting. Proxy context may remain as caveat evidence. Real source validation is still required before an operational claim.
2. Bring in and validate real observed climate and surveillance sources with source timestamps, completeness, corrections, truth level, geographic lineage and retention rules. Re-run strict climate and surveillance audits until they pass.
3. Do not claim UNICEF, early-warning accuracy, confirmed-case prediction, or 7–14-day lead time until a held-out, time-based evaluation on credible labels is completed and published with limitations.
4. **Code/configuration completed; deployment evidence remains.** Production-like checks now fail closed for HTTPS, HSTS, secure cookies, DEBUG, hosts/origins, secrets and forwarded headers, with healthchecks in Compose. Add managed secret storage, TLS/ingress evidence and operational backups per deployment.
5. **Completed for the production dependency path.** Next.js is upgraded to 16.3.0 and production-only npm audit is a CI gate with zero known vulnerabilities. Continue routine development-dependency remediation.

### P1 — required before a controlled pilot

1. **Correction regressions covered.** The focused production truth-policy suite passes **22/22**, including source-backed population acceptance, missing/cross-ward/value-mismatched population references, cross-dataset label-window rejection, proxy-only confirmed-label rejection, supersession rejection and explicit date-relative surveillance regression coverage; the earlier correction full suite passed **937/937**, and the follow-up full suite is delegated to CI. Supersession/correction data quality still needs real-source validation.
2. **Mostly completed.** CI now performs frontend install, production audit, lint, type-check, tests, build and a lightweight production-image health/compiled-origin smoke check with a committed ESLint configuration. Authenticated browser smoke coverage and live-dashboard checks remain to be added.
3. **Artifact registry governance implemented; operational readiness remains open.** Complete real artifact registration/evidence review, out-of-time metrics, calibration/threshold review, drift baselines and monitoring jobs before any model is approved or activated. The current registry audit must remain `NOT_APPROVED_FOR_OPERATIONAL_USE` until those checks are satisfied.
4. Configure and contract-test external integrations (DHIS2/OpenMRS, climate, population, settlement, logistics and SMS) in a non-production integration environment. Record provider health and idempotent transfer receipts.
5. Implement a durable domain audit/event ledger covering score generation, policy decisions, alert confirmations, message changes, exports, sync conflict resolution and data corrections.
6. **Partially completed.** Production ingestion guards, stable rejection reasons and health endpoints are in place; the remaining source-data operator surface and dedicated Phase 7 UI tests still need completion.
7. Replace calculated facility proxies with real facility case, stock, staffing, bed, ORS and referral inputs before using facility burden outputs operationally.

### P2 — readiness and adoption improvements

1. **Partially completed.** Model and dataset cards are published; threat model, decision-policy catalog and deployment-specific privacy/retention assessment remain.
2. **Partially completed.** Code of Conduct, issue templates and a locked frontend dependency graph are present; release/versioning policy and full reproducibility controls remain.
3. If an installable field application is required, add a service worker/manifest and test background sync, device recovery, encryption/retention and stale-bundle failure behavior.
4. Add reporting-period data pipelines so operational metrics are backed by actual source records rather than an empty-state screen.

## Demo runbook

### Start and seed

~~~bash
docker compose up --build -d
docker compose exec -T backend python manage.py migrate --noinput
docker compose exec -T backend python manage.py seed_demo_data
~~~

The Compose frontend is available at http://localhost:3000. For native frontend development instead of the containerized frontend:

~~~bash
cd frontend
npm ci --cache /tmp/cchis-npm-cache
npm run dev
~~~

Open http://localhost:3000 and use the local-only demo credentials documented in README.md:

| User | Role | Intended demo path |
|---|---|---|
| analyst_demo | Analyst | Overview, wards, alerts, source readiness, model health, system readiness |
| admin | Admin | Privileged trigger context/preview and governance controls; TOTP required |
| supervisor | Supervisor | Ward-scoped operational review and alert actions; TOTP required |
| chv_demo | CHV | Field triage/offline workflow and ward-scoped sync |

The shared demo password is for local development only and must not be reused.

### Useful audit commands

~~~bash
docker compose exec -T backend python manage.py test --noinput
docker compose exec -T backend python manage.py audit_climate_sources --format=json
docker compose exec -T backend python manage.py audit_climate_horizon --format=json
docker compose exec -T backend python manage.py audit_surveillance_pipeline --format=json
docker compose exec -T backend python manage.py audit_source_data_phases --format=json
docker compose exec -T backend python manage.py audit_privacy_controls --format=json
docker compose exec -T backend python manage.py run_risk_model --month=8 --model-version=lr-v1 --algorithm=logistic_regression
docker compose exec -T backend python manage.py run_random_forest_benchmark --month=8 --model-version=rf-audit
docker compose exec -T backend python manage.py run_facility_burden_forecast --model-version=fnb-v1 --horizon-days=7
~~~

### Representative endpoints

| Purpose | Endpoint | Access |
|---|---|---|
| OpenAPI schema | GET /api/v1/schema/ | Public |
| Login | POST /api/v1/auth/login/ | Public |
| Ward list | GET /api/v1/wards/ | Authenticated |
| Ward map | GET /api/v1/maps/wards/ | Authenticated |
| Risk scores | GET /api/v1/risk-scores/ | Authenticated |
| Alert list | GET /api/v1/alerts/ | Authenticated |
| Alert context | GET /api/v1/alerts/trigger/context/?ward_id=1 | Admin/supervisor |
| Alert preview | POST /api/v1/alerts/trigger/preview/ | Admin/supervisor |
| CHV offline contract | GET /api/v1/chv/offline/contract/ | Field role |
| CHV triage | POST /api/v1/chv/triage/ | Field role |
| CHV sync | POST /api/v1/chv/sync/ | Field role |
| USSD menu | POST /api/v1/ussd/menu/ | Public |
| Source readiness | GET /api/v1/source-data/overview/ | Authenticated |
| Interoperability | GET /api/v1/interoperability/dashboard/ | Authenticated |
| System readiness | GET /api/v1/system/readiness/ | Authenticated |
| Backend liveness | GET /health/live/ | Public |
| Backend readiness | GET /health/ready/ | Public |
| Frontend health | GET /api/health | Public |

## Key implementation files and documents

- Runtime and configuration: docker-compose.yml, backend/Dockerfile, frontend/Dockerfile, frontend/.dockerignore, backend/core/settings.py, backend/core/urls.py, backend/core/health.py.
- Authentication/RBAC: backend/accounts/, backend/accounts/role_capabilities.py, backend/core/security.py.
- Risk/model code: backend/risk/ml/model.py, backend/risk/ml/pipeline.py, backend/risk/truth_policy.py, backend/risk/surveillance_labels.py, backend/risk/surveillance_ingestion.py, backend/risk/management/commands/run_risk_model.py, backend/risk/management/commands/run_random_forest_benchmark.py.
- Data audits: backend/risk/management/commands/audit_climate_sources.py, audit_climate_horizon.py, audit_surveillance_pipeline.py, audit_source_data_phases.py, audit_privacy_controls.py.
- Alert/decision API: backend/risk/views.py, backend/risk/services.py, backend/risk/urls.py.
- CHV field path: backend/risk/chv_offline.py, backend/risk/views.py, frontend/app/chv/page.tsx, frontend/lib/chv-offline-api.ts, frontend/lib/chv-offline-store.ts.
- Frontend runtime/security: frontend/next.config.mjs, frontend/eslint.config.mjs, frontend/middleware.ts, frontend/lib/auth.ts, frontend/lib/server-api.ts, frontend/lib/request-security.ts.
- Governance/limitations: MODEL_CARD.md, DATASET_CARD.md, deploy/production.env.example, docs/DOMAIN_AUDIT_READINESS.md, docs/BACKEND_ML_MODEL_IMPLEMENTATION_AUDIT.md, docs/BACKEND_FACILITY_BURDEN_FORECASTING_IMPLEMENTATION_AUDIT.md, docs/INTEROPERABILITY_BOUNDARY.md, docs/IMPLEMENTATION_STATUS.md.
- Community/security: README.md, CODE_OF_CONDUCT.md, SECURITY.md, CONTRIBUTING.md, LICENSE, .github/ISSUE_TEMPLATE/, .github/workflows/ci.yml.

## Final assessment

The prototype is technically credible as a local, seeded decision-support demonstration and is now materially better hardened for a future pilot. Its strongest evidence is the working identity/RBAC boundary, managed geospatial foundation, deterministic surveillance feature propagation, explicit production truth blockers, runnable risk/forecast commands, guarded alert workflow, CHV offline contract and replay handling, public USSD state machine, health-gated Compose stack and live dashboard surfaces.

Its release posture remains **pilot-readiness work in progress, not production readiness**. The hardening program remains open: the correction pass strengthens production truth guards, Compose/provider wiring, frontend image provenance, scheduler hygiene and repository evidence, but does not create real-world evidence. The next milestone is real observed climate/surveillance feeds, corrected lineage, strict data-quality gates, time-based model validation, active registry/monitoring, external integration contract tests, authenticated browser smoke tests and deployment-specific operations. Until then, outputs should be labelled demo/proxy/calculated/preview-only wherever the UI and API already provide those caveats.
