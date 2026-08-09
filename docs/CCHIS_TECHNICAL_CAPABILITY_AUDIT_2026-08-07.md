# CCHIS Technical Capability Audit — Current-truth rerun

Audit date: 2026-08-09<br>
Repository: `cchis`<br>
Audited implementation commit: `8d0bea8043d6394cc523624b3bbcf7c7a5da4643` (`main`, same commit as `origin/main`)<br>
Audit document: this compatibility-path document was regenerated after the audited implementation commit; the facility-coordinate reconciliation and legacy surveillance-provenance backfill are applied to the local seeded database and represented in the working tree<br>
Environment: healthy local Docker Compose stack, Africa/Nairobi timezone, seeded development database<br>
Frontend verification runtime: Node `v25.6.0` locally; CI baseline is Node `22`

This report supersedes the previous post-remediation report. It includes the surveillance supersession-lineage implementation and the governance-fixture changes committed after the earlier audit. Counts and statuses below were measured against the current seeded database or an isolated temporary test database; they are not inherited from the previous report.

## Executive verdict

The current engineering baseline is substantially stronger than the previous report stated:

- The complete backend suite passes **1,019/1,019** tests. The previous `1,013`-test, `42`-failure, `45`-error baseline is obsolete.
- The complete frontend suite passes **304/304** tests across **64/64** test files.
- Frontend lint, typecheck, production build, and production dependency audit pass; `npm audit --omit=dev --audit-level=high` reports **0 vulnerabilities**.
- Production-like Django deployment checks pass, including a check with an ambient `DEBUG=release` value; the production Compose configuration is valid.
- Canonical Migori geography remains intact: 40 active wards, 40 managed polygon features, no invalid geometry, and no Mobitech-named ward.
- Strict CHIRPS ingestion remains green at **14/14 checks**, covering **1,200 records across 3 runs**.
- Source Data auditing remains green at **76/76 checks across 11 phases**; Phase 7 is **6/6**.
- Strict privacy auditing is green at **7/7 checks**, with zero high-risk findings, zero warnings, and zero gaps. The live schema returns HTTP 200 and includes `provider_message_id` on the Alert component.
- Surveillance supersession lineage is now controlled: active label windows reference zero superseded records, retired historical windows have replacement evidence, and the former strict lineage failure is closed.
- The model registry remains deliberately empty and fail-closed: **0 registered entries, 0 active models, `NOT_APPROVED_FOR_OPERATIONAL_USE`**.

The system is still not ready for production or real-world model-performance claims. The current strict climate-source and climate-horizon audits fail; the surveillance audit remains warning-level because the seeded dataset is not production truth and its truth-level audit reports semantic misuse; no approved model artifact exists; and live external delivery, connectors, deployment, backup, and monitoring evidence remain open. The three legacy model runs that previously lacked surveillance metadata are now explicitly classified as having unavailable legacy provenance, without attaching invented label lineage or evaluation claims. The previously reported facility-coordinate warning is closed: the spatial audit is green for all five active local facility records. The remaining facility limitation is provenance—place evidence comes from browser-observed Google Maps listings rather than an official facility registry.

The accurate current posture is therefore:

> **Automated code and governance-contract baseline: green. Data-evidence and operational-readiness baseline: not ready for production promotion.**

## Changes included since the previous report

| Commit | Current-truth impact |
|---|---|
| `4152ab5` | Added durable surveillance label supersession lineage, current-eligibility filtering, replacement dataset generation, and corresponding audit gates. |
| `99cd4e6` | Corrected the surveillance-lineage import path used by retraining policy. |
| `4301a55`, `4b3992c`, `95f61aa`, `8d0bea8` | Aligned governance-dependent test fixtures with approved active registry states, including decision, spatial, preparedness, contact-preference, and workflow coverage. |
| `5116268` | CI now captures and surfaces backend test failure names as annotations. |
| `02b3a04`, `3126b6a` | Closed the AlertSerializer provider-message privacy/schema defect and recorded the prior focused closure. |
| `c2629a5` | Preserved the canonical geography, strict CHIRPS, and Source Data Phase 7 remediation already covered by the previous report. |
| Working tree migration `0087_backfill_legacy_surveillance_metadata` | Classified model runs 2, 3, and 4 as `surveillance_label_usage=not_available` from persisted legacy fields; no surveillance label dataset or performance evidence was attached. |

The governance fixture changes improve test validity for workflows that require an approved active model. They do **not** create an operational model in the seeded development database, and they are not evidence that a production artifact exists.

## Verification scope and interpretation

The rerun covered:

- repository/commit state and worktree review;
- Compose service health and migration state;
- strict spatial, CHIRPS, Source Data, privacy, climate-source, climate-horizon, surveillance, and model-registry audits;
- complete backend tests in a temporary test database;
- complete frontend tests, lint, typecheck, production build, and production dependency audit;
- live OpenAPI schema inspection;
- production-like Django security checks and Compose configuration validation.

The following were not claimed as verified:

- a rebuilt and deployed production Docker image or production ingress;
- live Mobitech, DHIS2, OpenMRS, climate, population, settlement, or logistics provider operation;
- a controlled external SMS send or delivery callback reconciliation;
- a supplied, registered, evaluated, calibrated, monitored, and approved model artifact;
- production backups, restore rehearsal, secrets, retention configuration, or disaster recovery;
- browser smoke tests against a deployed environment.

The requested local facility reconciliation updated the five `CCHIS-HF-*` records and retired two synthetic `P9-*` records from the active directory; protected history was retained. Migration `0087` also updated only the three matching legacy model runs with an explicit unavailable-provenance classification; it did not attach a surveillance dataset. Backend tests used and destroyed an isolated temporary test database. Frontend build generation changed a tracked Next.js environment file locally; that generated change was restored before review.

## Verification results

| Check | Current result |
|---|---|
| Implementation commit | **Passed:** `8d0bea8`; local `main` matches `origin/main` |
| Compose stack | **Passed:** backend, worker, frontend, database, Redis, and Beat are running; backend/worker/frontend/database health is healthy |
| Database migrations | **Passed:** `migrate --check` is clean; migrations through `0087_backfill_legacy_surveillance_metadata` are applied |
| Backend system check | **Passed:** no issues during the full test run |
| Complete backend suite | **Passed:** 1,019 tests in 891.160 seconds; `OK`; temporary database destroyed |
| Frontend lint | **Passed:** `npm run lint` |
| Frontend typecheck | **Passed:** `npm run typecheck` after the production build generated `.next` types |
| Frontend test suite | **Passed:** 64 files, 304 tests |
| Frontend production build | **Passed:** Next.js build completed and generated 84 static pages; the middleware deprecation notice remains informational |
| Frontend production dependency audit | **Passed:** 0 vulnerabilities at high severity or above |
| Production-like Django security check | **Passed:** CI production environment, including ambient `DEBUG=release` check |
| Production Compose configuration | **Passed:** `docker compose --env-file deploy/ci-production.env config --quiet` |
| Live OpenAPI schema | **Passed:** HTTP 200; Alert schema includes `provider_message_id` |
| Canonical geography | **Passed:** 40 active wards, 40 managed geometry features, 0 invalid/empty polygons, exact fake ward absent |
| Strict CHIRPS audit | **Passed:** 14/14 checks; 1,200 records; 3 runs |
| Source Data phase audit | **Passed:** 76/76 checks; 11 phases; zero open gaps |
| Source Data Phase 7 subset | **Passed:** 6/6 checks |
| Strict privacy audit | **Passed:** 7/7 checks; 0 high-risk findings; 0 warnings; 0 gaps |
| Surveillance audit | **Warning:** lineage and model-consumer gates pass; seeded-demo truth and truth-level semantic misuse remain |
| Strict climate-source audit | **Failed:** 95 invalid/missing rainfall values, 4,322 invalid/missing ward links, and maximum forecast horizon of 3 days |
| Strict climate-horizon audit | **Failed:** 2 model-evidence failures and 57 frontend payload field failures; 5 unavailable-evidence warnings |
| Spatial source audit | **Passed:** 5 active facilities have coordinates; 0 lack coordinates; 0 facility points fall outside assigned ward geometry |
| Strict model-registry audit | **Passed:** 5/5 structural checks; 0 entries; 0 active models |

## Capability matrix

| Capability | Current status | Evidence and limitation |
|---|---|---|
| Canonical Migori geography | **Verified in seeded scope** | 40 active canonical wards and 40 valid managed polygons; exact fake Mobitech public ID absent; no ward name contains `Mobitech`. |
| Ward spatial relationships | **Geometry and local facility coordinates verified** | 172 directed / 86 undirected boundary-adjacency candidates; no isolated wards or pair errors. Five active facilities are coordinate-complete and within their assigned managed ward geometry. Existing persisted spatial-relationship count is 0 in the seeded database. |
| CHIRPS v3 historical ingestion | **Strict contract verified** | 14/14 checks pass over 1,200 records and 3 runs; accepted complete run remains separated from superseded history. |
| Source Data lifecycle | **Verified in code and contract tests** | 76/76 phase checks pass, including upload staging, dry validation, review, approval, freshness, connectors, role controls, downstream actions, and accessibility evidence. Live source operation remains unverified. |
| Containerized runtime | **Locally healthy; deployment evidence incomplete** | Existing Compose services are healthy; production-like config/security checks pass. Image rebuild, production ingress, and deployed-environment smoke evidence were not run in this audit. |
| Authentication and RBAC | **Automated baseline verified** | Full backend suite passes, including role, scope, step-up, session, throttling, and privacy contracts. Production identity-provider and deployment configuration remain open. |
| Privacy minimization | **Strict audit verified** | 7/7 checks pass with zero high-risk findings, zero warnings, and zero gaps; Alert provider identifier is privileged/redacted as designed. |
| Alert workflow | **Automated workflow verified; delivery externality open** | Backend suite and serializer/schema checks pass. No live provider send, callback URL, status endpoint, or controlled-recipient evidence is claimed. |
| Mobitech SMS adapter | **Focused/automated behavior verified** | Provider selection, credentials, callback, status, delivery reconciliation, truth-gate ordering, and canonical geography paths are covered by the backend suite. Live Mobitech delivery is not verified. |
| Surveillance ingestion and lineage | **Supersession controls verified; source truth not production-ready** | 2,880 superseded records are retained as history; active windows reference 0 superseded records; replacement evidence is present. All 7,202 current records and 7,680 label windows are `seeded_demo`. |
| Climate source separation | **Open** | Observed, forecast, and fallback records are typed and flagged, but the strict contract still reports rainfall and ward-linkage defects; forecast horizon is only 3 days. |
| Climate horizon evidence | **Open** | Arithmetic, issue time, lead-day bounds, future-observation exclusion, and fallback labeling pass. Model evidence and frontend alert payload completeness fail. No promoted model runs exist. |
| Production truth policy | **Safety block verified** | Seeded, stale, fallback, unresolved, and superseded inputs are blocked or classified by policy. This is a safety control, not evidence of production-quality source data. |
| Model registry | **Governed and fail-closed; not operational** | 5/5 structural audit checks pass; 0 registered entries and 0 active models; readiness is `NOT_APPROVED_FOR_OPERATIONAL_USE`. |
| Model training/evaluation | **Tested workflows; no operational candidate** | Test fixtures can represent an approved active registry state for downstream workflow tests. The current seeded database contains no real registered artifact and no approved operational model. |
| CHV/offline/USSD | **Automated backend baseline verified** | Full backend suite passes the endpoint, permission, sync, localization, and governance contracts. Field-device installation, connectivity variability, and live USSD provider operation remain unverified. |
| Facility readiness and forecast | **Partial** | Calculated/preview and promotion-governance paths are covered by tests, but live readiness inputs, source completeness, and production promotion evidence are absent. |
| DHIS2 interoperability | **Bounded demo proof only** | Checked-in Play evidence is read-only, replayable, `DEMO_ONLY`, `NON_OPERATIONAL`, and `production_eligible=false`; it is not Kenya/Migori production interoperability. |
| Operational model monitoring | **Not ready** | No active model exists to monitor; drift, calibration, alert-performance, rollback, and retraining evidence are not operationally established. |
| Cross-domain audit ledger | **Incomplete** | Domain-specific governance/event records exist, but a complete immutable ledger spanning scoring, decisions, alerts, corrections, exports, and sync conflicts remains an open capability. |

## 1. Geography, facility-coordinate, and Mobitech test-data remediation

The former non-canonical Mobitech-controlled ward remains absent from the seeded database. The current fixture in `backend/risk/test_mobitech_sms.py` selects canonical ward code `KE-WARD-1261` after loading the managed Migori geometry. It does not create an ad hoc persistent ward.

Current spatial state:

| Measure | Result |
|---|---:|
| Active Migori wards | 40 |
| Managed Migori geometry features | 40 |
| Active wards with invalid, empty, or missing managed polygons | 0 |
| Fake Mobitech public ID present | No |
| Ward names containing `Mobitech` | 0 |
| Directed boundary adjacency candidates | 172 |
| Undirected boundary adjacency pairs | 86 |
| Isolated wards | 0 |

Facility-coordinate remediation status: **closed**. All 5 active facilities have coordinates, and all 5 points are covered by their assigned managed ward geometry. The two synthetic `P9-*` Phase 9 records are inactive and retained only as protected test history. The coordinate source is a browser-observed Google Maps place listing, which is sufficient for this local spatial reconciliation but not a substitute for an official Ministry of Health facility registry or operational-status verification. This provenance caveat does not reopen the resolved missing-coordinate or out-of-geometry warning.

The five reconciled records are:

| Facility | Coordinates (lat, lon) | Canonical ward |
|---|---:|---|
| Lwala Community Hospital | `-0.6781171, 34.6088094` | North Kamagambo (`KE-WARD-1261`) |
| AGENGA DISPENSARY | `-0.8840000, 34.2562910` | North Kadem (`KE-WARD-1284`) |
| Macalder Mission Dispensary | `-0.9546974, 34.2856868` | Macalder/Kanyarwanda (`KE-WARD-1285`) |
| Got Kachola Dispensary | `-0.9601557, 34.1437905` | Got Kachola (`KE-WARD-1287`) |
| Ikerege Medical Center | `-1.1811230, 34.5417619` | Bukira Centrl/Ikerege (`KE-WARD-1290`) |

The reproducible place-listing evidence and the reconciliation command are in [`migori_facility_seed.py`](/Users/edwininganji/VSCodeProjects/cchis/backend/risk/migori_facility_seed.py) and [`reconcile_migori_facilities.py`](/Users/edwininganji/VSCodeProjects/cchis/backend/risk/management/commands/reconcile_migori_facilities.py).

## 2. CHIRPS ingestion consistency

The strict CHIRPS audit passes all 14 checks over 1,200 persisted records and 3 ingestion runs. The checks cover:

- genuine LIVE observed CHIRPS records;
- source/version/status/variant lineage;
- accepted quality flags;
- canonical URL, identity, source references, and source-run reconstruction;
- durable identity and ward/date uniqueness;
- canonical active Migori ward identity;
- complete canonical ward references for runs;
- complete observations for accepted runs;
- finite, non-negative rainfall;
- absence of static fallback in CHIRPS records;
- ward coverage and processed-date completeness;
- feature temporal cutoffs; and
- single-variant feature pinning.

Historical supersession is retained rather than fabricated away. The accepted complete CHIRPS run has 1,200 observations across the canonical 40 wards; superseded historical runs remain identifiable and non-eligible.

## 3. Source Data phases and operator evidence

The phase auditor reports **76/76 passed**, zero gaps, and 11 implemented phases. Phase 7 reports **6/6 passed**. Current evidence covers:

- feed registry and safe CSV templates;
- upload staging without automatic domain import;
- dry validation, PII rejection, limits, diagnostics, and correction review;
- maker-checker approval and confirmation;
- freshness and scoped operational health;
- independent loading and failure states;
- role-controlled mutation and step-up behavior;
- refresh/query behavior;
- connector status and bounded refresh paths; and
- accessibility identifiers, roles, tabs, and operator-facing truth labels.

This verifies the local implementation and behavior-test contracts. It does not establish that external providers are configured, reachable, complete, or contractually usable in production.

## 4. Surveillance supersession and truth status

The current code closes the former lineage failure through `FeatureDataset.eligibility_state`, `surveillance_lineage.py`, the `0086_feature_dataset_eligibility_state` migration, and the `reconcile_surveillance_label_lineage` management command.

Current surveillance audit totals:

| Measure | Result |
|---|---:|
| Surveillance records | 7,202 |
| Label windows | 7,680 |
| Label feature datasets | 16 |
| Ingestion runs | 7 |
| Sources | 5 |
| Superseded records retained as history | 2,880 |
| Active windows referencing superseded records | 0 |
| Superseded datasets lacking replacement evidence | 0 |
| Current model evaluations referencing superseded datasets | 0 |

The audit is now warning-level, not failure-level. The remaining warnings are substantive:

- all 7,202 current surveillance records and all 7,680 label windows are `seeded_demo`;
- the truth-level audit reports `truth_level_semantic_misuse`, including 2,400 confirmed-case records without confirmed truth and 102 proxy-truth windows containing confirmed cases.

The former three-run metadata finding is closed as a provenance classification: model runs 2, 3, and 4 now carry `surveillance_label_usage=not_available`, a `surveillance_label_dataset_missing` validation status, and a fail-closed truth gate. This records what is known from the persisted legacy rows; it does not claim that those runs used surveillance labels or produced valid surveillance performance evidence. No external data was required for this closure.

The remaining warnings mean the lineage machinery is safer and more truthful, but seeded/demo surveillance evidence must not be presented as confirmed production-case performance evidence.

## 5. AlertSerializer and privacy closure

`AlertSerializer.Meta.fields` includes `provider_message_id`, while `get_provider_message_id` continues to apply `redact_provider_identifier` for unauthorized or context-free responses. The live schema check returned HTTP 200 and included the field in the Alert schema.

The strict privacy audit passes all seven checks:

- CHV data is assignment-scoped;
- household messaging has consent/override evidence;
- contact-preference phone integrity is enforced;
- sensitive export downloads are audited;
- stale raw sync payload retention is controlled;
- frontend role responses do not expose unauthorized PII; and
- unsupported free-text medical notes are not accepted.

Current privacy audit result: **7/7 pass, 0 high-risk findings, 0 warnings, 0 gaps**. This verifies the application contract; it does not verify external provider privacy or deployment-specific logging/retention configuration.

## 6. Climate source and horizon findings

The climate audits remain the main data-evidence blocker.

### Climate source separation

The current source inventory contains:

| Measure | Result |
|---|---:|
| Climate records in the climate table | 2,509 |
| Contract rows inspected | 6,831 |
| Observed records | 1,290 |
| Forecast records | 923 |
| Explicit fallback records | 4,618 |
| Persisted derived rolling/anomaly records | 0 |
| Maximum provider forecast horizon | 3 days |

The strict audit still fails on:

- `climate_records_missing_or_invalid_rainfall_value`: 95 records;
- `climate_records_missing_or_invalid_ward`: 4,322 contract rows;
- `forecast_horizon_below_7_days`; and
- `forecast_horizon_below_14_days`.

The good news is that observed, forecast, and fallback types are distinguishable, forecast issue times and lead days are present, and fallback records are explicitly flagged. The system cannot truthfully support a 7-day or 14-day forecast claim from the current provider horizon.

### Climate horizon monitoring

The strict horizon audit scanned 40 feature rows, 62 linked alert payloads, 658 risk scores with decision policy, and 0 promotion model runs. Arithmetic, issue-time, lead-day, future-observation, and fallback-label checks pass. The remaining failures are:

- `model_evidence_climate_source_separation_present`: 2 failures;
- `frontend_climate_horizon_payload_fields_present`: 57 field failures and 5 unavailable-evidence warnings; and
- promotion-report climate coverage is warning-only because no promoted model run exists.

Until those fields and model evidence are complete, risk scores and alerts must retain explicit source and horizon caveats rather than imply unsupported forecast coverage.

## 7. Model governance and operational truth

The strict registry audit passes 5/5 structural checks:

- registry entry integrity;
- one active entry per deployment target;
- immutable governance-event provenance;
- registry-version uniqueness; and
- linkage of operational runs to approved active registry entries.

The current seeded database contains **0 registry entries**, **0 active models**, and no model artifact available under the configured artifact root. The resulting readiness is `NOT_APPROVED_FOR_OPERATIONAL_USE`.

The newer tests use a small isolated approved-active registry fixture when testing downstream workflows that require one. That fixture is test-only evidence of service behavior; it is not a production model, a supplied artifact, or a change to the seeded model registry.

No model approval, performance, calibration, drift, rollback, or trusted registered-artifact inference claim should be made until a real artifact and complete evaluation evidence are supplied.

## 8. External integrations and deployment limits

The repository contains bounded adapters and proof paths, but no live external operation was claimed in this audit:

- Mobitech credentials, callback URL, status endpoint, and controlled recipient evidence are absent from the local environment.
- DHIS2 evidence remains a read-only Play proof classified as `DEMO_ONLY` / `NON_OPERATIONAL` with `production_eligible=false`.
- Climate, population, settlement, logistics, and health-system source reachability and completeness are not established.
- Production ingress, secrets, backups, restore rehearsal, retention, alerting/observability, and deployment rollback evidence remain deployment-specific open items.
- The existing local stack is healthy, but Docker image rebuild and deployed-environment smoke evidence were not repeated after the latest commits.

## Priority gates

### P0 — before any operational or performance claim

1. Repair the climate record contract and ward linkage; reduce product claims or expand the provider horizon until 7/14-day coverage is genuinely supported.
2. Complete and audit climate evidence in model metadata and frontend alert payloads; resolve the 2 model-evidence failures and the 57 frontend field failures.
3. Replace or explicitly quarantine seeded-demo surveillance truth before reporting confirmed-case performance; the three legacy runs are already explicitly classified as unavailable for surveillance claims because their provenance is unavailable.
4. Supply a real model artifact and complete evaluation, calibration, monitoring, rollback, and registered-artifact inference evidence before any promotion.

### P1 — controlled-pilot readiness

1. For production facility-identity and operational-status claims, replace the browser-observed Google Maps evidence with an official facility registry/source feed. This is provenance hardening; the missing-coordinate and out-of-geometry facility warning is resolved.
2. Configure and contract-test the live DHIS2/OpenMRS, climate, population, settlement, logistics, and SMS integrations.
3. Run CI on the Node 22 baseline, rebuild the production images, and perform authenticated browser smoke tests against the deployment target.
4. Add deployment-specific secrets, backup/restore, retention, monitoring, incident, and rollback evidence.
5. Complete a durable cross-domain audit ledger for scoring, decisions, alerts, corrections, exports, and sync conflicts.

### P2 — sustainability and adoption

1. Add an installable field service worker/client if offline deployment requires it.
2. Add reporting-period pipelines for operational metrics and alert-performance monitoring.
3. Establish data-refresh SLAs, ownership, correction runbooks, and evidence retention for each external source.

## Reproducible verification commands

```bash
docker compose exec -T backend python manage.py migrate --check
docker compose exec -T backend python manage.py audit_spatial_sources --format json
docker compose exec -T backend python manage.py reconcile_migori_facilities --dry-run
docker compose exec -T backend python manage.py audit_chirps_ingestion --strict
docker compose exec -T backend python manage.py audit_source_data_phases --format=json --strict
docker compose exec -T backend python manage.py audit_privacy_controls --strict --format json
docker compose exec -T backend python manage.py audit_climate_sources --strict --format json
docker compose exec -T backend python manage.py audit_climate_horizon --strict --format json
docker compose exec -T backend python manage.py audit_surveillance_pipeline --format json
docker compose exec -T backend python manage.py audit_model_registry --strict
docker compose exec -T backend python manage.py test --noinput

cd frontend
npm run lint
npm run typecheck
npm test
npm run build
npm audit --omit=dev --audit-level=high

cd ..
docker compose --env-file deploy/ci-production.env config --quiet
docker compose --env-file deploy/ci-production.env run --rm --no-deps backend python manage.py check --deploy --fail-level WARNING
DEBUG=release docker compose --env-file deploy/ci-production.env run --rm --no-deps backend python manage.py check --deploy --fail-level WARNING
curl -fsS http://localhost:8000/api/v1/schema/
```

`audit_climate_sources --strict` and `audit_climate_horizon --strict` are expected to exit non-zero under the current seeded data because their documented failure conditions remain open. `audit_spatial_sources --strict` passes on the current seeded database after the facility reconciliation. The surveillance audit is intentionally shown without `--strict` above so its warning report can be inspected without treating the known seeded-demo limitation as an unexpected command failure.

## Key evidence files

- Surveillance supersession and current eligibility: `backend/risk/surveillance_lineage.py`, `backend/risk/migrations/0086_feature_dataset_eligibility_state.py`, `backend/risk/management/commands/reconcile_surveillance_label_lineage.py`
- Legacy model provenance classification: `backend/risk/migrations/0087_backfill_legacy_surveillance_metadata.py`
- Surveillance audit and consumers: `backend/risk/surveillance_audit.py`, `backend/risk/surveillance_labels.py`, `backend/risk/surveillance_features.py`, `backend/risk/ml/retraining_policy.py`, `backend/risk/truth_policy.py`
- Governance-dependent test fixture: `backend/risk/registry_test_fixtures.py`
- CI test-failure visibility: `.github/workflows/ci.yml`
- Canonical geography and Mobitech fixture: `backend/risk/test_mobitech_sms.py`, `backend/risk/migrations/0084_remove_mobitech_controlled_test_geography.py`, `backend/risk/spatial_relationships.py`
- CHIRPS audit and ingestion: `backend/risk/chirps_audit.py`, `backend/risk/management/commands/audit_chirps_ingestion.py`, `backend/risk/test_chirps_ingestion.py`
- Source Data phases and UI evidence: `backend/risk/source_data/phase_auditor.py`, `frontend/app/(dashboard)/source-data/page.tsx`, `frontend/app/source-data-page.test.tsx`
- Alert serializer/privacy: `backend/risk/serializers.py`, `backend/risk/privacy_audit.py`, `backend/risk/test_privacy_access.py`
- Climate audits: `backend/risk/climate_source_audit.py`, `backend/risk/climate_horizon_audit.py`
- Model registry audit: `backend/risk/ml/model_registry_audit.py`, `backend/risk/management/commands/audit_model_registry.py`
- DHIS2 bounded proof: `backend/risk/data/source_feeds/dhis2_play_proof_evidence.json`, `docs/DHIS2_PLAY_INTEROPERABILITY_PROOF.md`

## Final assessment

CCHIS now has a green automated engineering baseline and materially improved governance behavior. The full backend and frontend suites pass, the privacy/schema regression is closed, surveillance supersession is no longer allowed to contaminate current label consumers, canonical Migori geography and CHIRPS strict ingestion remain verified, and Source Data operator evidence is complete within its local scope.

Those results do not establish production readiness. Climate source integrity and forecast horizon evidence still fail strict checks; seeded-demo surveillance truth is unsuitable for real performance claims; facility spatial coverage is no longer an open defect, although facility identity/provenance still relies on browser-observed Maps listings rather than an official registry; the model registry is correctly empty; and external integrations and deployment operations remain unproven. The next release gate is evidence/data closure and real artifact/integration validation, not model promotion.
