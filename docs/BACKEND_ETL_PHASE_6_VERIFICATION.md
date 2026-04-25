# Backend ETL Phase 6 Verification and Audit

## Scope

This verification checks whether the implemented ETL backbone supports the predictive and operational claims in:

- [BACKEND_ETL_AND_FEATURE_PIPELINE_PLAN.md](/Users/edwininganji/VSCodeProjects/cchis/docs/BACKEND_ETL_AND_FEATURE_PIPELINE_PLAN.md)
- [BACKEND_ML_MODEL_ROADMAP_PLAN.md](/Users/edwininganji/VSCodeProjects/cchis/docs/BACKEND_ML_MODEL_ROADMAP_PLAN.md)
- [DASHBOARD_DECISION_LAYER_IMPLEMENTATION_PLAN.md](/Users/edwininganji/VSCodeProjects/cchis/docs/DASHBOARD_DECISION_LAYER_IMPLEMENTATION_PLAN.md)

## Verification Run

### Commands run

- `docker compose exec backend python manage.py test risk.tests.CanonicalETLNormalizationTestCase risk.tests.RainfallIngestionTestCase risk.tests.SeedAndModelCommandTestCase risk.tests.ETLOperationalTrustPolicyTestCase --keepdb`
- `docker compose exec backend python manage.py showmigrations risk`

### Result

- focused ETL and prediction-readiness tests passed
- all current `risk` migrations through `0013` are applied

## Verification Questions

### 1. Do we have the minimum data needed for 7–14 day ward-level prediction?

Partial yes.

Implemented now:

- rainfall ingestion
- ward geometry and ward lineage discipline
- triage and sync operational records
- current facility snapshot normalization
- seeded training baseline data

Still incomplete for the full proposal target:

- richer real surveillance feeds
- population and settlement exposure data
- richer vulnerability/context layers
- richer facility operations data
- explicit flood data beyond proxy handling

Conclusion:

- enough exists to build and govern the early ETL backbone
- not enough exists yet to claim full real-world 7–14 day predictive credibility

### 2. Are ingestion cadences appropriate for the proposal’s early-warning goals?

Mostly yes for the current backbone.

Implemented now:

- daily rainfall ingestion through Celery Beat
- daily model run scheduled after ingestion
- manual replay path through management commands

Conclusion:

- the current cadence is appropriate for the rainfall-driven early-warning baseline
- additional source domains will need their own explicit cadences as they are added

### 3. Can every prediction be traced to source freshness and feature lineage?

Yes for the current implemented path.

Implemented now:

- `IngestionRun` tracks source kind, source name, source timestamp, freshness state, fallback usage, and record counts
- `FeatureDataset` and `FeatureDatasetRow` persist training and inference dataset lineage
- `ModelRun` links to training and inference datasets and to rainfall ingestion
- model-run metadata now stores operational trust policy decisions

Conclusion:

- current prediction outputs are traceable back to ETL freshness and feature-dataset lineage

### 4. Can both `Logistic Regression` and `Random Forest` consume the same disciplined feature set?

Yes.

Implemented now:

- shared training dataset build
- shared inference dataset build
- dual-model run mode
- separate `ModelRun` records with shared dataset lineage
- benchmark outputs remain distinct from promoted outputs

Conclusion:

- the ETL backbone supports both early-phase models without forking feature discipline

### 5. Can alert candidates be explained from actual data and rule context?

Partially yes.

Implemented now:

- rainfall-source lineage
- dataset lineage
- model-run algorithm metadata
- operational trust metadata
- explicit alert-eligibility vs benchmark-only distinction

Still incomplete:

- richer action-derivation logic remains mostly part of downstream dashboard and ML governance work
- full multi-source rule explanation does not yet exist because not all core source domains are live

Conclusion:

- current alert candidates are explainable within the implemented rainfall-driven baseline
- explanation depth will improve as more real source domains land

### 6. Does the system remain honest when sources are late, partial, or stale?

Yes.

Implemented now:

- delayed data degrades trust
- fallback or seeded data blocks automatic alerting
- stale live-source conditions block prediction generation
- blocked runs now persist failed `ModelRun` audit records with shared dataset lineage and trust metadata

Conclusion:

- the system no longer treats freshness as decorative metadata only
- ETL trust now governs scoring and alert automation behavior

### 7. Can seeded demo data exercise the same ETL contracts as live-source data?

Yes, within the implemented source domains.

Implemented now:

- seeded and fallback rainfall runs still produce canonical ETL envelopes
- seeded training datasets persist through the same feature-dataset machinery
- trust policy keeps seeded/fallback paths from pretending to be live promoted-alert truth

Conclusion:

- dev and QA paths now exercise the real ETL backbone rather than bypassing it

### 8. Can ops manually feed, replay, and inspect real source ingestion without a bespoke frontend?

Yes for the current phase.

Implemented now:

- Django admin for `IngestionRun`, `FeatureDataset`, `FeatureDatasetRow`, and `ModelRun`
- `ingest_rainfall` management command
- scheduled Celery task for rainfall ingestion
- run-history inspection via stored models

Conclusion:

- an admin-first ops surface is in place and sufficient for the current ETL scope

## Evidence Summary

### Canonical ETL normalization

Covered by tests for:

- rainfall normalization
- triage-session normalization
- sync-queue normalization
- facility-readiness normalization
- CHV-response normalization

### Dataset and model lineage

Covered by tests for:

- persisted training dataset
- persisted inference dataset
- shared dual-model dataset lineage

### Freshness and trust policy

Covered by tests for:

- fresh live source
- delayed live source
- fallback / seeded source
- static-mode-forced source behavior
- stale live source
- scheduled-ingestion-gap degradation
- degraded trust suppressing automatic alerts
- blocked trust preventing scoring
- blocked trust persisting auditable failed `ModelRun` records
- blocked dual-model runs persisting both primary and benchmark failure records

## Honest Remaining Gaps

1. The ETL backbone is strongest today for rainfall-driven prediction, not yet for the full multi-source proposal target.
2. Population, settlement exposure, richer surveillance, flood, and vulnerability feeds remain planned rather than fully implemented.
3. Schedule-gap trust is based on ingestion-run history, not yet on a fuller scheduler heartbeat or worker-health model.
4. Facility-readiness ETL exists structurally, but richer real facility operations data is still needed for higher-confidence forecasting.
5. The backbone is still strongest for rainfall-governed prediction rather than the full eventual multi-source proposal footprint.

## Final Verification Verdict

`complete with explicit limitations`

The ETL backbone is now credible as an early operational foundation for:

- canonical ingestion
- feature lineage
- dual-model readiness
- freshness-aware trust governance
- auditable blocked-run behavior
- admin-first ops control

It is not yet the full real-data completion of every proposal data domain, and this verification document should not be read as claiming that broader completion.
