# Source Data API Connectors

Phase 9 adds connector hooks that reduce manual CSV burden while keeping CSV as the fallback and correction path.

## Connector Model

Each connector fetches or receives a canonical CSV payload, creates a normal source-data upload batch, and runs the same dry-validation checks used by operator uploads. Clean connector batches can then follow the same confirmation, history, freshness, approval, and downstream governance surfaces as CSV batches.

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
- `SOURCE_DATA_DHIS2_MAPPING_JSON`
- `SOURCE_DATA_DHIS2_CANONICAL_CSV_URL`

For tests and deployment rehearsals, `SOURCE_DATA_CONNECTOR_FIXTURE_DIR` may point at canonical CSV fixtures named `<connector_key>.csv`.

Scheduled connector refreshes are controlled by:

- `SOURCE_DATA_API_CONNECTORS_ENABLED`
- `SOURCE_DATA_SCHEDULED_CONNECTOR_KEYS`
- `SOURCE_DATA_CONNECTOR_REFRESH_HOUR`
- `SOURCE_DATA_CONNECTOR_REFRESH_MINUTE`

The default schedule includes `dhis2_surveillance_weekly`. Unconfigured connector runs skip safely and leave CSV upload available as fallback.

## Feed Modes

Feeds expose a mode of `api`, `csv`, `manual`, `fallback`, or `demo`.

Admins can mark a connector as authoritative and disable routine CSV upload for that feed. CSV can be re-enabled as fallback when source gaps, corrections, or recovery require it.

## Audit And Failure Reporting

Every connector refresh creates a `SourceDataConnectorRun` record with:

- Connector key and target feed.
- Status, source reference, record count, and safe metadata.
- Linked source-data upload batch when a payload was fetched.
- Failure summary when fetch or canonical validation fails.

Connector payload failures are handled as source-data validation failures, not as special bypasses.
