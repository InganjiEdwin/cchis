# CCHIS Data Source Feeds

Status date: 2026-05-05

This is the current source strategy for feeding the CCHIS e2e flow:

```text
Data Sources -> ETL Pipeline -> Feature Engineering -> ML Prediction Layer -> Decision Engine -> Alerts & Interfaces
```

## Source Matrix

| Domain | Best live/API path | Current CCHIS path | E2E fallback |
| --- | --- | --- | --- |
| Rainfall | Open-Meteo is already wired. NASA POWER can supplement historical daily point meteorology. HDX HAPI rainfall may help where HAPI coverage fits the admin level. | `ingest_rainfall` plus `ClimateRecord` ledger. | Existing static/fallback rainfall seed path. Keep forecast claims at the audited horizon until 7/14 day coverage is proven. |
| Flood exposure | No dependable anonymous ward-level flood API should be assumed for the pilot. Longer-term candidates are Copernicus/GloFAS, county flood reports, and humanitarian feeds. | Population/exposure ETL accepts `flood_exposure_layer` or `csv_backfill`. | Synthetic floodplain exposure proxy generated per ward. |
| Health surveillance | DHIS2 analytics/export API is the preferred institutional path when credentials and data elements are available. OpenMRS REST can support facility-level extracts where facilities use OpenMRS. | `ingest_surveillance` accepts weekly, daily, line-list summary, trusted push, field signal, facility proxy, and CSV backfill feeds. | Synthetic weekly cholera aggregate feed with suspected, confirmed, diarrheal proxy counts, and outbreak labels. |
| Population | KNBS official releases are the preferred baseline; WorldPop API/data files can provide gridded population for spatial aggregation. | `ingest_population_exposure` accepts population baseline, gridded population, and CSV backfill feeds. | Synthetic ward population baseline and under-five/household proxies. |
| Geo and exposure context | Existing Migori ward GeoJSON, OpenStreetMap/Overpass for water, settlements, roads, and facility context; World Bank WASH indicators for coarse contextual vulnerability. | Ward geometry import, spatial graph builders, and population/exposure ETL. | Synthetic settlement, WASH, water proximity, floodplain, population density, and exposed population proxy values. |
| Facility readiness | Partner feeds from DHIS2, OpenMRS, logistics systems, or manual facility update workflows. | Source-data readiness snapshot CSV upload/validation/import, facility readiness review/update/escalation APIs, and facility burden forecast commands. | Existing `seed_demo_data` scenarios plus manual review/update records for UI testing. |
| Alerts and interfaces | Africa's Talking or equivalent provider for SMS/USSD once credentials are configured. | Dashboard, CHV, SMS/USSD, message governance, and preparedness action surfaces exist. | Seeded risk/action scenarios and local dashboard/API testing without sending provider messages. |

## Current Local Coverage

As of 2026-05-05, the local e2e dataset is intentionally demo-fed where real source data is still missing.

| Area | Local count | Current truth state |
| --- | ---: | --- |
| Migori wards | 40 | Source-backed from local Migori ward CSV/GeoJSON. |
| Climate records | 120 | Mixed Open-Meteo forecast and fallback-static records; current audit still does not support 7/14-day climate claims. |
| Population baselines | 40 | Seeded demo baseline records. |
| Exposure features | 240 | Seeded demo exposure proxies. |
| Surveillance records | 1,440 | Seeded demo weekly cholera aggregates. |
| Surveillance label windows | 960 | Seeded demo label windows. |
| Feature datasets | 15 | Mostly generated from seeded/demo source records. |
| Model runs | 4 | No active promoted model registry entry yet. |
| Facility forecasts | 0 | Facility burden forecasting path exists, but no forecast records have been generated in the current local DB snapshot. |

This means the application can be tested end to end, but the current dataset must not be presented as production evidence.

## Admin CSV Responsibility

These are the areas where admins or county/partner operators still need to provide files until authenticated API integrations are available.

| Upload area | Who likely provides it | Accepted backend route today | Minimum columns or content | Recommended cadence |
| --- | --- | --- | --- | --- |
| Weekly cholera/diarrheal surveillance | County surveillance team, DHIS2 export owner, implementing partner | `ingest_surveillance --source-type weekly_aggregate` | Ward or facility key, reporting period start/end, suspected/confirmed cholera counts, diarrheal/proxy counts where available | Weekly minimum; daily if daily aggregate reporting exists |
| Historical surveillance backfill | County surveillance team, DHIS2 export owner | `ingest_surveillance --source-type csv_backfill` or `weekly_aggregate` | Same as weekly surveillance, covering past reporting periods | One-off backfill at pilot start; corrections as needed |
| Population baseline | KNBS/official release extract, county planning team | `ingest_population_exposure --source-type population_baseline` or `csv_backfill` | Ward key, total population, under-five count if available, household proxy if available | Annual, or when official releases change |
| Gridded population / settlement layer | WorldPop/OpenStreetMap processing owner, GIS/data officer | `ingest_population_exposure --source-type gridded_population` or `settlement_layer` | Ward or geometry key plus population density or settlement concentration | Quarterly or when source layer is refreshed |
| Flood exposure / floodplain proxy | County disaster team, GIS partner, humanitarian data partner | `ingest_population_exposure --source-type flood_exposure_layer` | Ward or geometry key plus flood exposure/flood risk/exposed population proxy | Monthly in rainy season; quarterly otherwise; event-driven after floods |
| Water proximity / WASH vulnerability | GIS partner, WASH team, World Bank/partner-derived extract | `ingest_population_exposure --source-type water_body_distance_layer` or `wash_vulnerability_layer` | Ward or geometry key plus distance/proximity/vulnerability score | Quarterly or after major WASH assessment updates |
| Facility readiness snapshot | Facility in-charge, county health operations, logistics/stock system owner | Source-data ops upload to `facility_readiness_snapshot`, backed by `run_facility_readiness_snapshot_ingestion` | ORS/IV fluid stock, staffing/capacity state, bed/referral pressure, service disruptions | Weekly routine; daily during alerts, rainy season, or outbreak response |
| Facility catchment mapping | County health/GIS team | `ingest_population_exposure --source-type catchment_mapping` | Facility key, assigned wards, catchment population estimate | One-off setup; update when facilities/catchments change |

Current operator path: routine source CSVs can now move through the source-data dashboard surface for template download, upload, dry validation, confirm import, rejected-row diagnostics, freshness/history review, and guarded downstream actions. CLI commands remain useful for development, incident response, and scheduled jobs, but they are no longer the only path for source-data intake.

Implementation record: see `docs/SOURCE_DATA_OPS_SURFACE_IMPLEMENTATION_PLAN.md` for the phased backend/frontend roadmap and audit trail covering template downloads, guided uploads, dry-run validation, safe import confirmation, source freshness, ingestion history, and downstream rebuild controls.

## API And Scheduled Fetch Responsibility

| Feed | Current automation | Recommended cadence | Notes |
| --- | --- | --- | --- |
| Rainfall forecast | Celery beat runs `risk.tasks.run_rainfall_ingestion_task` daily at 05:30. | Daily before model scoring. | Open-Meteo is wired; fallback static records are retained and audited. |
| ETL heartbeat | Celery beat runs `risk.tasks.record_etl_heartbeat_task` every 10 minutes. | Every 10 minutes. | Used by trust/ops checks to detect scheduler/worker gaps. |
| Risk scoring | Celery beat runs `risk.tasks.run_risk_model_task` daily at 06:00. | Daily after rainfall and latest source updates. | Sends no SMS by default; alert creation can still be blocked by trust/promotion policy. |
| Facility burden forecast | Celery beat runs `risk.tasks.run_facility_burden_forecast_task` daily at 06:30. | Daily after risk scoring. | Meaning improves only after real facility readiness/surveillance feeds exist. |
| Surveillance ingestion | Callable by command/task, not fixed beat schedule. | Weekly after county/DHIS2 reporting; daily if source provides daily aggregate. | Should regenerate label windows after import. |
| Population/exposure ingestion | Callable by command/task, not fixed beat schedule. | Mostly manual/scheduled around source refreshes. | Population is not a daily source; exposure layers should be refreshed by source cadence. |
| Lead-time feature dataset build | Callable by command, not fixed beat schedule. | Daily for monitoring/evaluation once real labels exist; on demand during pilot testing. | Must respect source cutoff and leakage rules. |
| Operational KPI snapshots | Callable by command, not fixed beat schedule in the current settings file. | Daily. | Useful for M&E once real operational activity starts. |

## Model Training And Prediction Cadence

CCHIS has two different model rhythms: routine prediction and governed retraining/promotion.

| Activity | Current path | Recommended cadence | Promotion status |
| --- | --- | --- | --- |
| Daily ward-risk scoring | `run_risk_model_task` / `run_risk_model` | Daily at 06:00 after rainfall ingestion | Already scheduled, but automatic production trust is limited by current source quality. |
| Daily in-process model fit for scoring | `run_mock_prediction_pipeline` builds training/inference datasets and fits the selected model during the scoring run | Daily as part of current scoring path | Treat as operational scoring/candidate evidence, not automatic model promotion. |
| Surveillance label rebuild | `ingest_surveillance --regenerate-label-windows` or `build_surveillance_label_dataset` | After each surveillance import; weekly minimum | Seeded labels must not be used for real performance claims. |
| Lead-time backtest / model comparison | `run_ward_risk_backtest`, `compare_model_candidates`, related model-ops commands | Monthly during pilot, and after meaningful new label data arrives | Manual review required. |
| Champion/challenger benchmark | `run_random_forest_benchmark`, `record_champion_challenger_comparison` | Monthly or per model review cycle | Challenger outputs must not create alerts. |
| Model monitoring/retraining recommendation | `run_model_monitoring`, `evaluate_model_retraining_policy` | Monthly, and immediately after drift/performance concern | Recommendations do not auto-promote. |
| Model promotion | `sync_model_registry_entry` and model governance commands | Manual only after evidence review | No active promoted model exists in the current local DB snapshot. |

Recommended operating rule:

- Fetch rainfall daily.
- Ingest surveillance weekly minimum.
- Refresh population/exposure only when the source changes.
- Refresh facility readiness weekly in quiet periods and daily during alerts/outbreak risk.
- Run daily scoring.
- Review retraining/promotion monthly during pilot, not automatically.

## Synthetic E2E Feed Command

Use this when real surveillance, flood, population, or WASH feeds are not yet available but the full ETL path needs data.

```bash
docker compose exec -T backend python manage.py seed_e2e_source_feeds \
  --as-of 2026-05-05 \
  --weeks 12
```

That writes two CSV feeds:

```text
risk/data/e2e_source_feeds/population_exposure_seed_e2e_2026-05-05.csv
risk/data/e2e_source_feeds/surveillance_seed_e2e_2026-05-05.csv
```

When run through Docker, those container paths map to `backend/risk/data/e2e_source_feeds/` on the host.

To ingest those feeds and build downstream datasets:

```bash
docker compose exec -T backend python manage.py seed_e2e_source_feeds \
  --as-of 2026-05-05 \
  --weeks 12 \
  --ingest \
  --build-downstream
```

For a non-production scoring pass after the downstream build:

```bash
docker compose exec -T backend python manage.py seed_e2e_source_feeds \
  --as-of 2026-05-05 \
  --weeks 12 \
  --ingest \
  --build-downstream \
  --score
```

The command marks these records as `seeded_demo` / `seeded` and uses `fallback_used=True`, so dashboards and model governance can distinguish them from real operational truth.

`--build-downstream` builds lead-time feature rows for prediction dates after the source load date. This preserves the leakage rule that a feature row can only use records created before that prediction day's source cutoff.

## Real Feed Drop-In

The synthetic CSVs intentionally use the same adapter contracts as real feeds. When a real file arrives, replace the source metadata and keep the same ETL shape.

Population/exposure example:

```bash
docker compose exec -T backend python manage.py ingest_population_exposure \
  --file /path/to/population_or_exposure.csv \
  --source-name "WorldPop aggregated ward extract" \
  --source-type gridded_population \
  --source-timestamp 2026-05-05 \
  --release-version "source-release-label" \
  --source-ref "https://www.worldpop.org/rest/data/pop"
```

Surveillance example:

```bash
docker compose exec -T backend python manage.py ingest_surveillance \
  --file /path/to/dhis2_or_county_weekly.csv \
  --source-name "Migori DHIS2 weekly cholera export" \
  --source-type weekly_aggregate \
  --source-timestamp 2026-05-05 \
  --reporting-period-start 2026-02-11 \
  --reporting-period-end 2026-05-05 \
  --regenerate-label-windows \
  --label-dataset-role training
```

## Important Honesty Rule

The e2e command is for integration testing and demos. It should not be used as evidence that the system has production surveillance labels, production flood observations, or production-ready 7/14 day climate coverage. Real-data promotion still requires DHIS2/county/partner health feeds, stronger flood/exposure lineage, and climate horizon audit evidence.

## Official Source References

- WorldPop REST API: https://www.worldpop.org/sdi/introapi/
- HDX HAPI documentation: https://hdx-hapi.readthedocs.io/en/latest/
- HDX HAPI climate/rainfall guide: https://hdx-hapi.readthedocs.io/en/latest/data_usage_guides/climate/
- Copernicus GloFAS data/services: https://global-flood.emergency.copernicus.eu/general-information/data-and-services/
- OpenStreetMap Overpass API: https://wiki.openstreetmap.org/wiki/Overpass_API
- DHIS2 analytics API: https://docs.dhis2.org/en/develop/using-the-api/dhis-core-version-242/analytics.html
- OpenMRS REST API: https://rest.openmrs.org/
- World Bank Indicators API: https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-indicators-api-documentation
- NASA POWER Daily API: https://power.larc.nasa.gov/docs/services/api/temporal/daily/
- KNBS: https://www.knbs.or.ke/
