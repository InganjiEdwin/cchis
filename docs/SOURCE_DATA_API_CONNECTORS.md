# Source Data API Connectors

Phase 9 adds connector hooks that reduce manual CSV burden while keeping CSV as the fallback and correction path.

## Connector Model

Each connector fetches or receives a canonical CSV payload, creates a normal source-data upload batch, and runs the same dry-validation checks used by operator uploads. The DHIS2 connector additionally performs a genuine authenticated read-only API discovery/query, transforms the response through an explicit UID crosswalk, and sends the resulting CSV envelope through the normal validation and surveillance ingestion path. Clean connector batches can then follow the same confirmation, history, freshness, approval, and downstream governance surfaces as CSV batches.

Current connector keys:

- `dhis2_surveillance_weekly`
- `openmrs_facility_surveillance`
- `worldpop_knbs_population`
- `osm_overpass_settlement`
- `logistics_stock_readiness`

## Configuration

Credentials and endpoint URLs are read only from runtime settings/environment variables. API responses never include credential values; connector status exposes only setting names and whether the connector is configured.

Examples:

- `SOURCE_DATA_DHIS2_BASE_URL`
- `SOURCE_DATA_DHIS2_USERNAME`
- `SOURCE_DATA_DHIS2_PASSWORD`
- `SOURCE_DATA_DHIS2_API_TOKEN` (preferred; alternative to username/password)
- `SOURCE_DATA_DHIS2_MAPPING_JSON`
- `SOURCE_DATA_DHIS2_QUERY_JSON`
- `SOURCE_DATA_DHIS2_TIMEOUT_SECONDS`
- `SOURCE_DATA_DHIS2_MAX_RETRIES`
- `SOURCE_DATA_DHIS2_CANONICAL_CSV_URL`

For tests and deployment rehearsals, `SOURCE_DATA_CONNECTOR_FIXTURE_DIR` may point at canonical CSV fixtures named `<connector_key>.csv`.
The `worldpop_knbs_population` connector also accepts the generated Migori pilot
fixture name `migori_worldpop_2026_population.csv` so the Phase 1 canonical CSV
can be replayed without copying it.

WorldPop/KNBS connector settings:

- `SOURCE_DATA_WORLDPOP_KNBS_SOURCE_URL`
- `SOURCE_DATA_WORLDPOP_KNBS_RELEASE_VERSION`
- `SOURCE_DATA_WORLDPOP_KNBS_CANONICAL_CSV_URL`

For the Migori pilot, `worldpop_knbs_population` targets the
`gridded_population` feed because the canonical CSV contains both
`population_total` and `population_density` fields generated from the WorldPop
raster aggregation. KNBS remains the reconciliation anchor rather than the
direct imported source.

Scheduled connector refreshes are controlled by:

- `SOURCE_DATA_API_CONNECTORS_ENABLED`
- `SOURCE_DATA_SCHEDULED_CONNECTOR_KEYS`
- `SOURCE_DATA_CONNECTOR_REFRESH_HOUR`
- `SOURCE_DATA_CONNECTOR_REFRESH_MINUTE`

The default schedule includes `dhis2_surveillance_weekly`. Unconfigured connector runs skip safely and leave CSV upload available as fallback.

## DHIS2 API Boundary

`dhis2_surveillance_weekly` uses `risk.source_data.dhis2.Dhis2Client` for GET-only calls. It verifies `/api/me`, reads `/api/system/info`, retrieves the explicitly configured organisation-unit and data-element/indicator metadata, and executes the explicitly configured `analytics` or `dataValueSets` query. PAT authentication uses `Authorization: ApiToken ...`; basic authentication is accepted only over HTTPS outside local DEBUG mode.

`SOURCE_DATA_DHIS2_MAPPING_JSON` is a versioned UID crosswalk. It must contain explicit DHIS2 organisation-unit UIDs, explicit data-element/indicator UIDs, canonical CCHIS fields, and (when relevant) category-option-combo UIDs. A CCHIS ward is resolved by its stable public ID or ward code; display-name matching is never used. Unknown UIDs, ambiguous duplicate values, malformed periods, and invalid counts are rejected into the interoperability run.

The mapping and query must be labelled for their actual scope. A Play proof should use a label such as `DHIS2_PLAY_DEMO_CROSSWALK_V1`, a non-operational reviewer status, and the JSON boolean `operational_eligible=false`. The persisted mapping version remains `DRAFT` and each individual mapping remains `NEEDS_REVIEW`; it is not an approved operational crosswalk. Queries are bounded to one explicit period and mapped UIDs with small page/result limits. Resulting canonical records carry `seeded_demo` truth, `DEMO` and `NON_OPERATIONAL` classifications, complete DHIS2 provenance, and are excluded by the existing production model-training, confirmed-truth, and alerting gates.

The API transport is preferred when fully configured. If it is unavailable, `SOURCE_DATA_DHIS2_CANONICAL_CSV_URL` remains an optional correction/fallback transport and its run metadata reports `canonical_csv_url`, never `dhis2_api`. Fixtures report `fixture_csv`.

## Feed Modes

Feeds expose a mode of `api`, `csv`, `manual`, `fallback`, or `demo`.

Admins can mark a connector as authoritative and disable routine CSV upload for that feed. CSV can be re-enabled as fallback when source gaps, corrections, or recovery require it.

## Authorization

Source-data connector APIs follow the role contract in `README.md`.

- `ADMIN` has full source-data access, including connector refreshes, feed-mode/admin controls, risky import approval, downstream actions, templates, upload validation, and confirmation.
- `SUPERVISOR` can upload, validate, confirm, request approval, and run allowed downstream source-data actions within the operational source-data workflow, but cannot approve risky imports or use admin connector/feed-mode controls.
- `ANALYST` can view source-data readiness and download templates or safe validation outputs, but cannot upload, confirm, approve, refresh connectors, or trigger downstream actions.
- `CHV` has no source-data dashboard/API access.

Source-data write operations require fresh `source_data` step-up for roles that are otherwise allowed. Frontend controls are UX only; backend permission checks remain authoritative for direct API calls.

Population/exposure freshness is feed-scoped. Current counts and truth states
exclude non-current records such as `replaced_by_new_release`,
`replay_diagnostic`, and `replacement_not_activated`, so retired seeded rows do
not keep a feed marked as demo-backed after a source-backed replacement lands.

## Audit And Failure Reporting

Every connector refresh creates a `SourceDataConnectorRun` record with:

- Connector key and target feed.
- Status, source reference, record count, and safe metadata.
- Linked source-data upload batch when a payload was fetched.
- Failure summary when fetch or canonical validation fails.

Connector payload failures are handled as source-data validation failures, not as special bypasses.
