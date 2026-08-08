# CCHIS Technical Capability Audit — Post-remediation rerun

Audit date: 2026-08-08<br>
Repository: cchis<br>
Audited commit: 02b3a049e3ceebbce7b9b32d1f14b6e1a4cc191e (main, local; origin/main remains c2629a53b5bc7594ee0fe5f1e8a937cde900f863)<br>
Previous audit commit: 51249097f40ce23a201ce1cb341cbc2f0a1d3822<br>
Environment: existing healthy local Docker Compose stack, Africa/Nairobi timezone, seeded development database

This rerun verifies the strict-audit geography and Source Data Phase 7 remediation, then closes and retests the AlertSerializer provider-message privacy/schema regression. It supersedes the previous report’s claims that the fake Mobitech ward existed, strict CHIRPS failed, Phase 7 had two open evidence gaps, and the alert serializer remained broken.

The AlertSerializer correction and focused regression tests are committed in the audited commit. The model registry was not changed: zero models are approved for operational use.

## Executive verdict

The completed tranche is successful:

- The fake Mobitech-controlled ward is absent from the seeded database.
- Exactly 40 canonical active Migori wards remain, and all 40 have valid, non-empty polygons.
- The strict CHIRPS audit passes all 14 checks against 1,200 records across 3 runs.
- The Source Data phase auditor passes all 76 checks, including both former Phase 7 gaps.
- `AlertSerializer` now exposes `provider_message_id` in `Meta.fields` and preserves its redaction policy.
- The focused privacy/serializer suite passes 38/38, and the live OpenAPI schema returns HTTP 200 with `provider_message_id` present.
- The strict privacy audit passes with zero high-risk findings, zero warnings, and zero gaps.
- Affected backend tests pass 41/41: Mobitech SMS 19/19, CHIRPS 16/16, and Source Data Phase 7 6/6.
- The focused Source Data frontend test passes 19/19.
- The model registry remains empty and fail-closed: 0 registered entries, 0 active models, NOT_APPROVED_FOR_OPERATIONAL_USE.

This does not make CCHIS production-ready. The complete backend suite was not rerun locally. The clean-database climate-source, climate-horizon, and surveillance strict audits still report the exact residual gaps recorded below; external providers, model validation, and operational deployment evidence also remain open.

The current posture is therefore **AlertSerializer/privacy closure complete; overall pilot/production readiness still open**.

## Verification scope

The requested focused verification limits were followed. This pass ran only:

- canonical geography and polygon state checks;
- migration application;
- the targeted strict CHIRPS audit;
- the Source Data phase auditor;
- the model-registry safety audit;
- strict climate-source, climate-horizon, surveillance, and privacy audits against the current seeded database;
- the focused AlertSerializer/privacy test modules and Django system check;
- the live OpenAPI schema endpoint check after reloading the backend;
- affected Mobitech, CHIRPS, and Phase 7 backend tests;
- the focused Source Data frontend test;
- repository status/diff checks.

Full backend/frontend suites, builds, container rebuilds, and unrelated audits were not rerun locally in this pass. They remain CI responsibilities.

## Verification results

| Check | Result |
|---|---|
| Commit state | Passed: HEAD is 02b3a049e3ceebbce7b9b32d1f14b6e1a4cc191e; local main is one commit ahead of origin/main |
| Existing Compose stack | Passed: backend, worker, frontend, database, Redis, and Beat are running; backend/worker/frontend/database health is healthy |
| Database migrations | Passed: migrations 0084 and 0085 are applied; migrate reports no pending work |
| Canonical geography query | Passed: 40 expected geometry wards, 40 active Migori wards, exact code-set match, 0 invalid polygons |
| Fake-ward cleanup query | Passed: exact fake public ID absent; no ward name containing Mobitech remains |
| Strict CHIRPS audit | **Passed: 14/14 checks; 1,200 records; 3 runs** |
| Source Data phase audit | **Passed: 76/76 checks; 0 open gaps; 11 phases claimed implemented** |
| Phase 7 audit subset | **Passed: 6/6 checks; 0 gaps** |
| Focused alert/privacy tests | **Passed: 38/38** across `risk.test_privacy_access`, `risk.test_privacy_audit`, `risk.test_privacy_minimization`, and `risk.test_privacy_retention` |
| Live OpenAPI schema | **Passed: HTTP 200; `provider_message_id` present** |
| Strict privacy audit | **Passed: 7/7 checks; 0 high-risk findings; 0 warnings; 0 gaps** |
| Strict climate-source audit | **Failed with recorded residual gaps**: rainfall-value/ward contract gaps; 7/14-day forecast claims unsupported |
| Strict climate-horizon audit | **Failed with recorded residual gaps**: incomplete model/alert climate evidence |
| Strict surveillance audit | **Failed with recorded residual gaps**: superseded records referenced by labels |
| Strict spatial source audit | Warning: `facilities_without_coordinates`, `facility_points_outside_assigned_ward_geometry` |
| Mobitech focused backend tests | **Passed: 19/19** |
| CHIRPS focused backend tests | **Passed: 16/16** |
| Phase 7 focused backend tests | **Passed: 6/6** |
| Combined affected backend tests | **Passed: 41/41** |
| Focused Source Data frontend test | **Passed: 1 file, 19 tests** |
| Strict model registry audit | **Passed: 5/5 structural checks; 0 entries; 0 active models** |

## 1. Fake Mobitech ward remediation

### Identified source

The fake ward was:

- Name: Mobitech Controlled Test Ward
- Database ID: 1774
- Public ID: 11b83323-4a36-4f66-af6f-f6d6e4a5373c
- Origin: the former MobitechSmsTests.setUp fixture in backend/risk/test_mobitech_sms.py
- Defect: non-canonical Migori test geography without a managed polygon

### Recurrence prevention

The current Mobitech fixture uses canonical Migori data:

- seed_kenya_administrative_areas loads the real county/ward set.
- import_ward_geometry loads the managed 40-feature Migori geometry.
- The test selects existing canonical ward code KE-WARD-1261.
- The fixture no longer creates a persistent ad hoc ward.
- The focused regression test asserts the exact 40-ward code set, polygon validity, and absence of Mobitech-named wards.

Relevant file: backend/risk/test_mobitech_sms.py.

### Database cleanup

Migration 0084 removes only the exact stable public ID above. The remediation cleanup removed the fake ward and exclusive dependent test records: 1 CHV, 5 risk scores, 10 alerts, 4 notifications, 1 workflow state, and linked alert-delivery events. No legitimate ward was deleted, renamed, or modified.

Relevant file: backend/risk/migrations/0084_remove_mobitech_controlled_test_geography.py.

Current read-only state:

| Geography check | Result |
|---|---|
| Expected canonical geometry wards | 40 |
| Active Migori wards | 40 |
| Active ward code set equals canonical geometry code set | Yes |
| Active wards with invalid, empty, or missing polygons | 0 |
| Exact fake public ID exists | No |
| Wards with Mobitech in the name | 0 |

## 2. CHIRPS audit consistency

The strict audit now passes all 14 checks:

- genuine LIVE observed CHIRPS records;
- complete source/version/status/variant lineage;
- accepted quality flags;
- canonical URL, identity, source reference, and source-run reconstruction;
- durable identity and ward/date uniqueness;
- canonical active Migori ward identity;
- every run referencing all canonical wards;
- complete persisted observations for accepted runs;
- finite non-negative rainfall;
- no static fallback;
- ward coverage threshold;
- complete processed-date coverage;
- feature temporal cutoffs;
- single-variant feature pinning.

The audit scanned 1,200 records across 3 ingestion runs.

### Historical run treatment

The remediation preserves historical counts and does not fabricate observations:

| Run | Current status | Eligibility | Persisted record state |
|---|---|---|---|
| 36 | PARTIAL | non_eligible; superseded | Historical run retained for audit history |
| 37 | PARTIAL | non_eligible; superseded | Historical run retained for audit history |
| 38 | SUCCESS | accepted | 1,200 persisted observations across the canonical 40 wards |

Migration 0085 marks runs 36 and 37 PARTIAL/non-eligible because their observation set was superseded by the later force-reconciled run. The strict audit evaluates run 38 as the accepted complete run while retaining the superseded history.

Relevant files:

- backend/risk/chirps_audit.py
- backend/risk/migrations/0085_mark_superseded_chirps_runs_non_eligible.py
- backend/risk/management/commands/audit_chirps_ingestion.py
- backend/risk/test_chirps_ingestion.py

No audit threshold was weakened, no legitimate ward was excluded, and no rainfall record was invented.

## 3. Source Data Phase 7 evidence closure

The Phase 7 auditor now passes both formerly failing evidence keys:

| Evidence key | Result | Closure |
|---|---|---|
| phase7_frontend_operator_ui | Passed | Auditor maps to stable current components and behavior identifiers for feed truth, staged upload/validation/review, readiness, operations, connectors, roles, refresh, and accessibility |
| phase7_frontend_tests | Passed | Auditor maps to current focused behavior tests covering templates, provenance, truth labels, validation, upload staging, readiness, scoped failures, downstream actions, role controls, refresh, and accessible tabs |

The full source-data phase report is 76/76 passed with zero open gaps. The Phase 7 subset is 6/6 passed.

The auditor continues to cover:

- feed registry and truthful source states;
- upload without automatic import;
- dry validation and correction review;
- scoped operational health;
- independent loading/failure states;
- role-controlled mutation controls;
- query refresh behavior;
- accessibility identifiers and roles.

Relevant files:

- backend/risk/source_data/phase_auditor.py
- frontend/app/(dashboard)/source-data/page.tsx
- frontend/app/source-data-page.test.tsx
- backend/risk/test_source_data_phase7.py

## Focused test evidence

### Mobitech SMS

The affected suite passes 19/19. It now tests provider selection, callback behavior, credentials/configuration paths, delivery handling, truth-gate ordering, and canonical 40-ward polygon-backed test geography without leaving persistent fake geography.

### CHIRPS

The affected suite passes 16/16. It covers official URL/variant guards, spatial aggregation, quality and identity checks, canonical run ward references, missing observations, retrospective feature loading, variant pinning, and future-leakage protections.

### Source Data Phase 7

The affected suite passes 6/6. It covers validation diagnostics, serializer redaction, operator UI evidence, security/role behavior, and the current stable Phase 7 contract.

### Frontend

The focused Source Data page test passes 19/19.

## 4. AlertSerializer and privacy closure

The former contract defect is closed in `backend/risk/serializers.py`:

- `provider_message_id` is included beside `external_id` in `AlertSerializer.Meta.fields`;
- `get_provider_message_id` continues to use `redact_provider_identifier`;
- admin responses expose the exact provider ID;
- analyst responses and serializers without request context return the redacted empty form.

The focused regression fixture stores `provider-message-privacy-access` and verifies the privileged and unauthorized paths through alert list/detail responses and direct serializer use. The live schema endpoint was checked after reloading the backend and returned HTTP 200 with `provider_message_id` in the Alert component.

`audit_privacy_controls --strict` now passes all seven checks with zero high-risk findings, zero warnings, and zero gaps. This closes the former privacy/schema blocker; it does not imply that provider delivery itself has been externally verified.

## Known residual release blockers and audit gaps

### Complete backend suite

The previous broader audit at commit 5124909 discovered 1,013 backend tests and ended with 42 failures and 45 errors. This tranche intentionally did not repeat the full suite. CI must establish the new complete-suite baseline after commit 02b3a04.

### Clean-database strict audit results

The requested rerun used the current seeded development database rather than the older contaminated snapshot. These are the exact remaining keys:

| Audit | Result | Remaining keys/evidence |
|---|---|---|
| Climate source separation | **Fail** | `climate_records_missing_or_invalid_rainfall_value` (95 records), `climate_records_missing_or_invalid_ward` (4,322 contract rows); `forecast_horizon_below_7_days`, `forecast_horizon_below_14_days`; warning `derived_climate_records_not_persisted_yet`; maximum forecast horizon is 3 days |
| Climate horizon | **Fail** | `model_evidence_climate_source_separation_present` fails on 2 risk scores; `frontend_climate_horizon_payload_fields_present` has 57 failures and 5 unavailable-evidence warnings; `promotion_report_climate_coverage_summary_present` is warning-only because no promoted runs exist |
| Surveillance pipeline | **Fail** | `superseded_records_used_in_label_windows`, `label_windows_reference_superseded_records`; warnings `truth_level_semantic_misuse`, `model_runs_missing_surveillance_metadata`; all 7 ingestion runs and 7,202 records are explicitly `seeded_demo` |
| Spatial source | **Warning** | `facilities_without_coordinates`, `facility_points_outside_assigned_ward_geometry`; canonical 40-ward geometry coverage still passes |

These gaps are data/evidence readiness issues, not silently accepted claims. Seeded/demo surveillance truth remains unsuitable for confirmed-case performance claims, and the 3-day provider forecast cannot support a 7- or 14-day operational claim.

### External delivery and model artifact follow-up

No live Mobitech delivery is claimed. The local runtime has provider configuration, but no callback URL or status endpoint is configured and no controlled recipient was supplied for an externally consequential send. The adapter remains verified by focused tests only.

The model artifact root is empty. There are 22 `ModelRun` rows but no existing stored artifact to register; therefore no candidate was fabricated or registered. The strict registry audit passes 5/5 structural checks with 0 entries, 0 active models, and `NOT_APPROVED_FOR_OPERATIONAL_USE`.

The following conclusions remain unchanged:

- No model is approved for operational use.
- DHIS2 evidence remains a bounded Play demonstration, not Kenya/Migori production interoperability.
- Live external source connectors, deployment secrets, backups, production ingress, held-out model performance, calibration, drift monitoring, and trusted registered-artifact inference remain open.

## Capability matrix

| Capability | Current status | Evidence and limitation |
|---|---|---|
| Canonical Migori geography | **Verified working** | Exactly 40 active canonical wards; all 40 have valid non-empty polygons; exact fake Mobitech UUID absent |
| CHIRPS v3 historical ingestion | **Verified working within strict scope** | Strict audit 14/14; 1,200 records; accepted run 38 complete; superseded runs retained as non-eligible history |
| Source Data Phase 7 operator evidence | **Verified working within strict scope** | Phase auditor 76/76; Phase 7 6/6; focused frontend 19/19 |
| Containerized runtime | **Previously verified; not rebuilt in this pass** | Existing stack is healthy; rebuild/build checks remain CI responsibilities for this focused rerun |
| Authentication and RBAC | **Implemented, partially verified** | Existing role, ward-scope, step-up, and privacy contracts remain; broader suite was not rerun |
| Privacy minimization | **Verified working within focused scope** | AlertSerializer closure, 38/38 focused privacy tests, live schema HTTP 200, and strict privacy audit 7/7 with zero gaps |
| Source-data lifecycle | **Implemented, partially verified** | Phase 7 evidence and focused behavior are green; live external feeds and production upload operations remain unverified |
| Climate source separation | **Open with current strict findings** | Exact rainfall-value/ward linkage gaps remain; provider horizon is 3 days, below 7/14-day claims |
| Surveillance truth | **Open with current strict findings** | Superseded records are still referenced by label windows; current records and labels are seeded-demo |
| Production truth policy | **Verified as a safety block** | Weak/demo/fallback/unresolved model inputs remain designed to fail closed |
| Model registry | **Safety-governed, not operational** | 5/5 strict registry checks pass; 0 entries and 0 active models |
| Alert workflow | **Focused contract closure verified** | AlertSerializer field/schema/privacy defect closed; complete backend baseline remains pending |
| Mobitech SMS adapter | **Focused tests verified** | 19/19 affected tests pass; no live provider delivery claimed because callback/status/controlled-recipient evidence is absent |
| CHV/offline/USSD | **Implemented, partially verified** | Existing application contracts remain; not part of this focused rerun |
| Facility readiness/forecast | **Partial** | Calculated/preview behavior remains; live capacity and promotion evidence absent |
| DHIS2 interoperability | **Bounded demo proof only** | Read-only DHIS2 Play proof remains DEMO/NON_OPERATIONAL and production_eligible=false |
| Operational model monitoring | **Not ready** | No active model exists to monitor |
| Durable domain audit ledger | **Planned/documented only** | General immutable domain event ledger remains absent |

## DHIS2 Play evidence

The checked-in evidence in backend/risk/data/source_feeds/dhis2_play_proof_evidence.json remains valid:

- official Play host play.im.dhis2.org;
- DHIS2 version 2.43.1;
- GET-only discovery and bounded analytics;
- HTTP 200 responses;
- identical response hash on replay;
- one mapped source value and one canonical surveillance row per read;
- zero duplicate delta;
- DEMO_ONLY mapping scope;
- DEMO/NON_OPERATIONAL truth classification;
- production_eligible=false;
- no credential material persisted.

This is genuine bounded interoperability evidence, not a production Kenya/Migori connector.

## Priority recommendations

### P0 — release blockers

1. Rerun the complete backend suite in CI after commit 02b3a04 and reconcile any changed fixture counts or failures.
2. Resolve the climate source contract and evidence gaps before making any 7- or 14-day operational claim.
3. Rebuild or supersede surveillance label windows so they cannot reference superseded records; replace seeded/demo truth before performance claims.

### P1 — controlled-pilot readiness

1. Configure and contract-test external DHIS2/OpenMRS, climate, population, settlement, logistics, and SMS providers.
2. Register a real existing model artifact as a non-operational candidate only after the artifact is supplied; complete evaluation, calibration, monitoring, rollback rehearsal, and trusted registered-artifact inference before approving any model.
3. Add authenticated browser smoke coverage and make strict data audits CI gates.
4. Add durable domain audit/event coverage for scoring, decisions, alerts, corrections, exports, and sync conflicts.
5. Replace calculated facility proxies with live readiness, stock, staffing, referral, and case-history inputs.

### P2 — adoption and sustainability

1. Add an installable service-worker field client if required.
2. Add reporting-period pipelines for operational metrics.
3. Complete deployment-specific secrets, backup/restore, retention, lawful-sharing, and release evidence.

## Useful focused commands

~~~bash
docker compose exec -T backend python manage.py migrate --noinput
docker compose exec -T backend python manage.py audit_spatial_sources --strict --format json
docker compose exec -T backend python manage.py audit_chirps_ingestion --strict
docker compose exec -T backend python manage.py audit_source_data_phases --format=json --strict
docker compose exec -T backend python manage.py audit_privacy_controls --strict --format json
docker compose exec -T backend python manage.py audit_climate_sources --strict --format json
docker compose exec -T backend python manage.py audit_climate_horizon --strict --format json
docker compose exec -T backend python manage.py audit_surveillance_pipeline --strict --format json
docker compose exec -T backend python manage.py audit_model_registry --strict
docker compose exec -T backend python manage.py test --noinput risk.test_privacy_access risk.test_privacy_audit risk.test_privacy_minimization risk.test_privacy_retention
curl -fsS http://localhost:8000/api/v1/schema/ | grep -q provider_message_id
docker compose exec -T backend python manage.py test --noinput risk.test_mobitech_sms
docker compose exec -T backend python manage.py test --noinput risk.test_chirps_ingestion
docker compose exec -T backend python manage.py test --noinput risk.test_source_data_phase7
cd frontend
npx vitest run app/source-data-page.test.tsx
~~~

## Key evidence files

- Geography cleanup: backend/risk/migrations/0084_remove_mobitech_controlled_test_geography.py
- CHIRPS eligibility reconciliation: backend/risk/migrations/0085_mark_superseded_chirps_runs_non_eligible.py
- CHIRPS audit and tests: backend/risk/chirps_audit.py, backend/risk/management/commands/audit_chirps_ingestion.py, backend/risk/test_chirps_ingestion.py
- Mobitech fixture and geography regression: backend/risk/test_mobitech_sms.py
- Phase 7 auditor: backend/risk/source_data/phase_auditor.py
- Source Data UI/tests: frontend/app/(dashboard)/source-data/page.tsx, frontend/app/source-data-page.test.tsx
- Model registry safety state: backend/risk/management/commands/audit_model_registry.py
- Alert serializer and privacy regression: backend/risk/serializers.py, backend/risk/test_privacy_access.py, backend/risk/privacy_audit.py
- Climate and surveillance strict results: backend/risk/management/commands/audit_climate_sources.py, backend/risk/management/commands/audit_climate_horizon.py, backend/risk/management/commands/audit_surveillance_pipeline.py
- DHIS2 proof: backend/risk/data/source_feeds/dhis2_play_proof_evidence.json, docs/DHIS2_PLAY_INTEROPERABILITY_PROOF.md
- Previous broader findings: this document’s Known residual release blockers section

## Final assessment

The focused remediation did what it was intended to do without changing model governance:

- canonical Migori geography is restored to 40 polygon-backed wards;
- the exact fake Mobitech ward and its exclusive dependent test data are removed;
- strict CHIRPS passes truthfully using a complete accepted run while superseded historical runs remain non-eligible;
- all Source Data Phase 7 evidence checks pass against real current components and behavior tests;
- the AlertSerializer provider ID is present in API/schema output and correctly privileged/redacted;
- strict privacy controls pass with zero findings;
- zero models remain approved for operational use.

The overall system is still not production-ready. The complete backend suite remains un-baselined, and the current strict audits still show climate data/evidence and surveillance lineage gaps. External integrations, model validation, monitoring, and deployment operations remain unproven.

The next gate is CI rerun of the broader suite and closure of the recorded climate/surveillance evidence gaps—not promotion of a model.
