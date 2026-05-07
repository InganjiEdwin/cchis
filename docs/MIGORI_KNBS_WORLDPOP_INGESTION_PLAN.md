# Migori KNBS And WorldPop Ingestion Plan

Status date: 2026-05-06

This plan scopes a first real population/exposure test import to Migori County.
The goal is to replace the current seeded-demo population layer with a traceable
source-backed test feed while keeping the claims honest.

## Operating Decision

Use KNBS as the official demographic anchor and WorldPop as the ward-level
processed spatial feed for testing.

- KNBS 2019 KPHC is the preferred official baseline for population, households,
  age/sex structure, density, and census-derived vulnerability context.
- WorldPop can provide ward-level current-year gridded estimates after spatial
  aggregation into the local Migori ward geometry.
- The first import should be Migori-only and should use the existing
  `ingest_population_exposure` path rather than creating a separate ingestion
  lane.
- Raw census microdata and personal line lists are out of scope. Use aggregated
  census tables and processed ward-level outputs only.

## Why This Matters

The current CCHIS e2e population/exposure data is intentionally seeded demo
data. That is useful for integration testing, but it should not be presented as
real operational truth.

Migori is a good first slice because the repo already has:

- 40 Migori wards in the local ward register.
- A canonical local ward boundary file at `backend/risk/data/migori_wards.geojson`.
- A population/exposure ingestion command that accepts `population_baseline`
  and `gridded_population`.
- A source-data ops model that can later treat processed WorldPop/KNBS data as
  a connector-backed canonical CSV.

## Source Roles

| Source | Role in this pilot | Vintage / release | CCHIS treatment |
| --- | --- | --- | --- |
| KNBS 2019 Kenya Population and Housing Census | Official demographic anchor and plausibility check. Use direct ward/sub-county/county values where available. | Census conducted in 2019; source-published tables and reports from KNBS portals. | Prefer `population_baseline` when a clean Migori ward extract exists. Otherwise use as reconciliation evidence. |
| WorldPop Kenya 2026 constrained 100m grid | Ward-level current-year gridded estimate after spatial aggregation. | `G2_CN_POP_R25A_100m`, Kenya, `popyear=2026`, source date `2025-09-01`, DOI `10.5258/SOTON/WP00839`. | Import as `gridded_population`, truth class `spatially_aggregated_source`. |
| Local Migori ward GeoJSON | Spatial aggregation boundary. | Repo artifact at `backend/risk/data/migori_wards.geojson`. | Use as the polygon source for ward-level WorldPop aggregation. |

## WorldPop API Note

WorldPop exposes two useful API surfaces:

- Metadata/download API: `https://hub.worldpop.org/rest/data/pop`
- Advanced stats API: `https://api.worldpop.org/v1/services`

The polygon stats API currently advertises `wpgppop` and `wpgpas`, which are
older 2000-2020 datasets. The newer 2015-2030 Global2 releases are available
through the metadata/download path as GeoTIFF files. For a 2026 Migori feed,
the safer workflow is therefore:

```text
WorldPop metadata -> Kenya 2026 GeoTIFF -> aggregate into Migori wards -> canonical CSV -> existing CCHIS ingestion
```

WorldPop source URL for the planned 2026 file:

```text
https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/2026/KEN/v1/100m/constrained/ken_pop_2026_CN_100m_R2025A_v1.tif
```

## Target Feed Design

### KNBS Direct Baseline

Use this path only if a clean KNBS ward-level Migori extract is available.

```text
source_type: population_baseline
truth_class: direct_population_baseline
source_kind: live
freshness_state: fresh
release_version: KNBS 2019 KPHC
```

Canonical CSV columns:

```csv
ward_code,population_total,population_under_five,household_count_proxy,unit,source_ref
```

### WorldPop Processed Ward Aggregate

Use this path for the first real test import.

```text
source_type: gridded_population
truth_class: spatially_aggregated_source
source_kind: live
freshness_state: fresh
release_version: WorldPop G2_CN_POP_R25A_100m KEN 2026 v1
```

Recommended canonical CSV columns:

```csv
ward_code,population_total,population_density,gridded_population_value,aggregation_method,spatial_resolution,unit,source_ref,notes
```

Column meaning:

- `ward_code`: local CCHIS ward code, for example `KE-WARD-1269`.
- `population_total`: rounded ward population from raster-cell aggregation.
- `population_density`: ward population divided by ward area.
- `gridded_population_value`: raw aggregate total from the WorldPop grid before rounding, if retained.
- `aggregation_method`: use `ward_sum_from_worldpop_100m_grid`.
- `spatial_resolution`: use `100m`.
- `unit`: use `people_per_km2` for the density exposure record.
- `source_ref`: use the WorldPop GeoTIFF URL or `worldpop:74000`.
- `notes`: include the release, polygon source, and any processing caveat.

The ingestion code will create:

- `PopulationBaselineRecord` rows from `population_total`.
- `ExposureFeatureRecord` rows for `population_density`.

`gridded_population_value` is audit evidence only. It must not be used as a
fallback for `population_density`, because it is a raw people count, not a
people-per-sq.-km exposure value.

Because this is `source_type=gridded_population`, the population records should
be treated as spatially aggregated source evidence, not direct KNBS truth.

## Proposed Workflow

### Phase 0: Source Inventory

1. Confirm the 40 local Migori wards and codes:

   ```bash
   docker compose exec -T backend python manage.py shell -c \
     "from risk.models import Ward; print(Ward.objects.filter(county__iexact='Migori').count())"
   ```

2. Confirm the local GeoJSON has 40 features and matches local ward names/codes.
3. Record KNBS source references for Migori census baseline, including whether
   the cleanest available extract is county, sub-county, administrative unit, or
   ward-level.
4. Record WorldPop metadata for the selected Kenya 2026 file.
5. Confirm license and citation requirements for any generated test artifact.

Phase 0 implementation status:

- Added `inventory_migori_population_sources` to build a repeatable JSON source
  inventory from the local ward register, local Migori GeoJSON, KNBS reference
  list, and WorldPop metadata.
- Latest strict run wrote
  `backend/risk/data/source_feeds/migori_knbs_worldpop_phase0_inventory.json`.
- Local register check passed: 40 active Migori wards, 40 total Migori wards,
  and zero missing ward codes.
- Local GeoJSON check passed: 40 Migori features, 40 backend ward-code matches,
  zero unmatched features, zero duplicate names/codes, and no placeholder
  geometry detected.
- WorldPop metadata check passed for Kenya 2026 record `74000`, source date
  `2025-09-01`, DOI `10.5258/SOTON/WP00839`, and GeoTIFF file
  `ken_pop_2026_CN_100m_R2025A_v1.tif`.
- Cold re-audit hardening: strict Phase 0 now fails if the WorldPop metadata
  drifts away from the exact planned record id, source date, DOI, or GeoTIFF
  URL. The inventory records both the expected release tuple and the fetched
  release tuple.
- External-audit hardening: strict Phase 0 now also verifies the selected
  WorldPop record is `popyear=2026`, `data_format=Geotiff`, advertises the
  100m category, names WorldPop as the source, and carries a citation containing
  DOI `10.5258/SOTON/WP00839`.
- License/citation check is recorded in the inventory: WorldPop data uses
  Creative Commons Attribution 4.0 International, attribution is required, and
  the raw GeoTIFF must stay outside git.
- KNBS references are recorded, but direct KNBS import remains pending until a
  clean Migori ward-level extract is confirmed. Until then, KNBS is the
  reconciliation anchor and WorldPop is the spatially aggregated test feed.

Repeatable command:

```bash
docker compose exec -T backend python manage.py inventory_migori_population_sources \
  --strict \
  --output /app/risk/data/source_feeds/migori_knbs_worldpop_phase0_inventory.json
```

### Phase 1: Build The Processed CSV

Add a small processing utility or one-off command that:

1. Reads `backend/risk/data/migori_wards.geojson`.
2. Downloads or receives a cached WorldPop Kenya 2026 GeoTIFF.
3. Clips/aggregates raster population counts by each ward polygon.
4. Computes ward population density using a documented area calculation.
5. Writes `backend/risk/data/source_feeds/migori_worldpop_2026_population.csv`.

Implementation preference for the first pass:

- Do not add heavy raster dependencies to the app runtime unless needed.
- Prefer a one-off processing utility, local container, or optional script that
  outputs canonical CSV.
- Do not commit the raw GeoTIFF to the repo.
- If the generated CSV is small and useful as a fixture, commit it with clear
  provenance, or store it in the configured source-data fixture directory.

Phase 1 implementation status:

- Added `build_migori_worldpop_population_csv` to generate the processed
  Migori canonical CSV from the Phase 0 inventory, local Migori GeoJSON, and
  WorldPop 2026 GeoTIFF.
- The builder uses the GDAL command-line tools already present in the backend
  image. No Python raster/geospatial dependencies were added.
- The WorldPop GeoTIFF is downloaded to
  `backend/risk/data/source_cache/worldpop/` and that cache path is ignored by
  git. The raw TIFF is not a repository artifact.
- The aggregation method is
  `ward_sum_from_worldpop_100m_grid_pixel_centers`: GDAL streams the Migori
  bounding-box raster as XYZ, and the builder assigns non-negative pixel-center
  values to the containing Migori ward polygon.
- Generated CSV:
  `backend/risk/data/source_feeds/migori_worldpop_2026_population.csv`.
- Generated summary:
  `backend/risk/data/source_feeds/migori_worldpop_2026_population_summary.json`.
- Latest generated CSV has 40 data rows, raw total population `1,345,269.748`,
  rounded total population `1,345,269`, density range `76.734` to `3276.919`
  people per sq. km, and CSV SHA-256
  `858d74c593232d5040a24f30e517434236aa6e2e30125c85dac305bc71753b87`.
- Cold external re-audit hardening: Phase 1 now records positive raster
  population mass accounting for the full Migori bounding-box crop. The latest
  run assigned `1,345,269.752` people to Migori ward polygons and recorded
  `872,695.650` positive people in bounding-box pixels outside the Migori ward
  polygons, proving the non-Migori rectangular crop remainder is explicit
  rather than silently lost.
- Phase 1 now also gates the declared WorldPop grid pixel size against the
  expected 3 arc-second / approximately 100m grid (`0.00083333333` degrees),
  positive ward areas, and CSV raw-total agreement within the documented
  three-decimal per-row CSV rounding tolerance.
- The builder records the raster SHA-256
  `02e8cbb21de86ea25eb894cca277b45b5c90af8ae450a623590793906ac96139`,
  Migori GeoJSON SHA-256
  `5554c913ff082f7cc2536c772a9190ca81d3b1a7370d872800ff540ce40f6997`,
  and WorldPop record metadata from Phase 0.
- Cold re-audit hardening: Phase 1 now writes explicit `phase1_gates` and
  `passed=true`. The gates require a passing Phase 0 inventory with exact
  WorldPop release checks, including the stricter year/format/source/citation
  checks, a unique 40-ward CSV, positive population/density values, a recorded
  raster SHA-256, a source-cache raster path outside git, and GDAL metadata
  proving a declared WGS84-like raster with positive pixel size.

Repeatable command:

```bash
docker compose exec -T backend python manage.py build_migori_worldpop_population_csv \
  --strict \
  --output /app/risk/data/source_feeds/migori_worldpop_2026_population.csv \
  --summary-output /app/risk/data/source_feeds/migori_worldpop_2026_population_summary.json
```

### Phase 2: Dry Validation

Inspect the generated CSV before creating records:

```bash
docker compose exec -T backend python manage.py ingest_population_exposure \
  --inspect-only \
  --file /app/risk/data/source_feeds/migori_worldpop_2026_population.csv \
  --source-type gridded_population
```

Acceptance gates:

- 40 source rows.
- 40 accepted rows.
- Zero `ward_not_found` rejections.
- No unknown high-risk columns.
- No spreadsheet formulas or PII-like values in notes/source fields.

Phase 2 preflight status:

- Added `validate_migori_worldpop_population_csv` to run the repeatable Phase 2
  dry-validation gate and persist
  `backend/risk/data/source_feeds/migori_worldpop_2026_population_validation.json`.
- Strict validation passed for
  `backend/risk/data/source_feeds/migori_worldpop_2026_population.csv`.
- Adapter inspection result: `adapter=gridded_population_csv`, `rows=40`,
  `accepted=40`, `rejected=0`, `unknown_columns=[]`.
- Additional gate results: no formula-like cells, no PII-like cells, and the
  CSV SHA-256 matches the Phase 1 summary SHA-256.
- Cold re-audit hardening: Phase 2 now also requires the Phase 1 summary itself
  to have passed, so a hash-matching CSV cannot hide a failed upstream raster or
  source-release gate.
- Additional cold re-audit hardening: Phase 2 now resolves every CSV row
  against the active Migori ward register before import, requires 40 distinct
  Migori wards, and fails on duplicate, unresolved, or missing expected ward
  codes. This closes the previous gap where `ward_not_found` could only be
  caught during the import.
- External-audit hardening: Phase 2 now validates the WorldPop row contract
  itself. Every row must carry the Phase 1 source URL,
  `spatially_aggregated_source`, `live`, `fresh`,
  `ward_sum_from_worldpop_100m_grid_pixel_centers`, `100m`, and
  `people_per_km2`; the latest run has zero row-contract mismatches.
- Additional external-audit hardening: Phase 2 now treats
  `gridded_population_value` as auxiliary evidence, not as an importable density
  substitute. The strict validation artifact requires positive numeric
  `population_total`, `population_density`, and `gridded_population_value`
  values on every row, and requires `population_total` to equal the rounded
  raw gridded value. The latest run has zero numeric contract failures.
- Validation artifact CSV SHA-256:
  `858d74c593232d5040a24f30e517434236aa6e2e30125c85dac305bc71753b87`.

Repeatable command:

```bash
docker compose exec -T backend python manage.py validate_migori_worldpop_population_csv \
  --strict \
  --file /app/risk/data/source_feeds/migori_worldpop_2026_population.csv \
  --phase1-summary /app/risk/data/source_feeds/migori_worldpop_2026_population_summary.json \
  --output /app/risk/data/source_feeds/migori_worldpop_2026_population_validation.json
```

### Phase 3: Import

Run the import through the existing population/exposure ingestion path:

```bash
docker compose exec -T backend python manage.py ingest_population_exposure \
  --file /app/risk/data/source_feeds/migori_worldpop_2026_population.csv \
  --source-name "WorldPop R2025A constrained 100m Migori ward aggregate" \
  --source-type gridded_population \
  --source-timestamp 2025-09-01 \
  --release-version "WorldPop G2_CN_POP_R25A_100m KEN 2026 v1" \
  --source-ref "https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/2026/KEN/v1/100m/constrained/ken_pop_2026_CN_100m_R2025A_v1.tif" \
  --operator-note "Migori-only WorldPop 2026 ward aggregation test. KNBS 2019 remains official baseline anchor."
```

Expected result:

- Ingestion run status is `success`.
- 40 `PopulationBaselineRecord` records are created from `population_total`.
- 40 `ExposureFeatureRecord` records are created for `population_density`.
- Records are not marked `seeded_demo`.

Phase 3 implementation status:

- Imported the validated CSV with `ingest_population_exposure`.
- Import run id: `2`.
- Import status: `SUCCESS`.
- Source rows: `records_seen=40`, `records_loaded=40`,
  `records_rejected=0`.
- Canonical summary: 80 canonical records total, split into 40
  `PopulationBaselineRecord` rows and 40 `ExposureFeatureRecord` rows.
- Population total imported from WorldPop ward aggregates: `1,345,269`.
- Imported population records are `truth_class=spatially_aggregated_source`,
  `source_kind=live`, `freshness_state=fresh`.
- Imported exposure records are 40 `population_density` rows with
  `truth_class=spatially_aggregated_source`, `source_kind=live`,
  `freshness_state=fresh`.
- No imported Phase 3 records are marked `seeded_demo`.
- Added `verify_migori_worldpop_population_import` to persist
  `backend/risk/data/source_feeds/migori_worldpop_2026_population_import.json`.
- Added `retire_seeded_population_density_records` to mark overlapping seeded
  population baseline and seeded population-density records as
  `replaced_by_new_release`, linked to the WorldPop replacement run recorded in
  the retirement summary.
- Retirement summary:
  `backend/risk/data/source_feeds/migori_seeded_population_density_retirement.json`.
- Retirement result: 40 seeded population baseline records and 40 seeded
  population-density exposure records marked non-current; 200 other seeded
  exposure proxy records were preserved for now because WorldPop does not
  replace settlement, floodplain, water-body, WASH, or exposed-population proxy
  layers.
- Current population and population-density context now resolves to the
  WorldPop source-backed records. Full context still reports proxy/seeded
  caveats while the remaining exposure proxy fields are demo-backed.
- Cold re-audit hardening: seeded-overlap retirement is now replay-safe. A
  strict re-run passes when the expected seeded population and density records
  are already retired, and it defaults to the latest successful
  `gridded_population` import when no replacement run id is supplied.
- Additional cold re-audit hardening: import verification now gates the exact
  Phase 1 source URL, WorldPop source date, release version, input CSV path,
  CSV hash, adapter, distinct ward count, Migori county scope, and matching
  population/density ward sets. Seeded-overlap retirement is scoped to the
  replacement run's Migori ward set, so out-of-scope seeded records in other
  counties cannot be retired by this pilot command.
- External-audit hardening: import verification now also gates row-level
  source refs and release versions for both imported population and density
  records, plus density `unit`, aggregation method, and spatial resolution.
  This prevents a successful run envelope from hiding wrong canonical record
  metadata.
- Additional external-audit hardening: import verification now compares every
  imported ward's `population_total` and `population_density` back to the Phase
  1 CSV, with zero ward-level mismatches in the latest strict artifact. This
  closes the previous gap where swapped ward values could hide behind a matching
  county total.
- Cold re-audit hardening: the default import verifier now selects the latest
  successful Migori WorldPop import, so an unrelated later failed/partial run no
  longer makes the default verification target drift away from the proven import.
- The retirement command now defaults only to the exact Migori WorldPop source
  name, `gridded_population` source type, and WorldPop 2026 release version;
  an unrelated later `gridded_population` run cannot become the replacement
  target by accident.
- External-audit hardening: seeded-overlap retirement now independently gates
  that the replacement run has 40 WorldPop population ward records and 40
  WorldPop population-density ward records, with identical ward sets, before it
  can be accepted as the seeded replacement scope.

Repeatable verification command. By default this verifies the latest successful
WorldPop population import; pass `--run-id` only when intentionally pinning an
older local run.

```bash
docker compose exec -T backend python manage.py verify_migori_worldpop_population_import \
  --strict \
  --phase1-summary /app/risk/data/source_feeds/migori_worldpop_2026_population_summary.json \
  --validation-summary /app/risk/data/source_feeds/migori_worldpop_2026_population_validation.json \
  --output /app/risk/data/source_feeds/migori_worldpop_2026_population_import.json
```

Repeatable seeded-overlap retirement command. By default this uses the latest
successful `gridded_population` import; pass `--replacement-run-id` only when
pinning a specific replacement run.

```bash
docker compose exec -T backend python manage.py retire_seeded_population_density_records \
  --apply \
  --strict \
  --output /app/risk/data/source_feeds/migori_seeded_population_density_retirement.json
```

### Phase 4: Reconcile Against KNBS

After import, compare:

- Sum of WorldPop 2026 Migori ward totals.
- KNBS Migori 2019 baseline total.
- KNBS population projection if available.
- Existing seeded-demo Migori total, only as a before/after sanity check.

Flag the import for review if the WorldPop 2026 sum is implausibly far from
KNBS/projection expectations. A first-pass warning threshold of 15-20 percent is
reasonable for testing, but the final threshold should be documented once the
KNBS projection source is selected.

Phase 4 implementation status:

- Added `reconcile_migori_knbs_worldpop_population` to compare the imported
  WorldPop Migori total against KNBS 2019 census workbooks, KNBS projection
  evidence, and the retired seeded-demo Migori total.
- Latest strict run wrote
  `backend/risk/data/source_feeds/migori_knbs_worldpop_2026_reconciliation.json`.
- KNBS 2019 Migori county baseline: `1,116,436` people, `240,168`
  households, `2,613.4842` sq. km, and `427.183` people per sq. km.
- KNBS 2019 sub-county cross-check passed: 8 Migori sub-counties sum to
  `1,116,436`, matching the county workbook.
- KNBS projection source provides county values for 2025 and 2030 but no direct
  2026 county value. The Phase 4 comparator therefore linearly interpolates
  `1,322,400` people for 2026 from the KNBS 2025 and 2030 projections.
- WorldPop 2026 imported ward total: `1,345,269`.
- WorldPop 2026 vs interpolated KNBS 2026 projection: `+22,869` people,
  `+1.729%`, which passes the current 20% warning threshold.
- WorldPop 2026 vs KNBS 2019 census baseline: `+228,833` people, `+20.497%`.
  This is recorded as expected growth context rather than a failure gate.
- Retired seeded-demo Migori population total: `384,894`, which is `-65.525%`
  below the KNBS 2019 county baseline. This confirms the seeded data should not
  remain the active population layer.
- Cold re-audit hardening: reconciliation now fails if the replacement ward
  scope is not the expected 40 Migori wards, or if current seeded population or
  population-density records still exist in that replacement scope.
- KNBS source workbooks are cached under
  `backend/risk/data/source_cache/knbs/`, which remains outside git. Initial
  local acquisition used TLS verification disabled because the KNBS file host
  presented an expired certificate on 2026-05-05.
- Cold re-audit hardening: KNBS downloads are now TLS-verified by default, with
  insecure download requiring an explicit recovery flag. The reconciliation
  artifact records SHA-256 hashes for each cached KNBS workbook.
- External-audit hardening: strict reconciliation now fails unless the KNBS
  county, sub-county, and projection workbooks all exist, have non-zero byte
  sizes, and have recorded SHA-256 hashes; it also requires the projection
  method to be documented.
- External-audit hardening: strict reconciliation no longer trusts the Phase 3
  JSON summary alone. It reloads the referenced ingestion run from the database,
  recomputes WorldPop population totals and ward counts from canonical records,
  and gates that the summary total matches the database total.
- Additional external-audit hardening: strict reconciliation now also gates the
  reloaded database run's exact source name, source type, release version,
  source ref, success status, truth class, source kind, and freshness state for
  both population and population-density records. This prevents a tampered Phase
  3 JSON summary from pointing reconciliation at a right-sized but wrong-source
  run.
- Cold finding fixed as an explicit caveat: the Phase 1 Migori polygon area
  total is `3,166.335` sq. km while the KNBS 2019 county land area is
  `2,613.4842` sq. km, a `+21.154%` difference. The reconciliation artifact now
  records that WorldPop CSV `population_density` uses the local aggregation
  GeoJSON polygon area, not KNBS official land area, and records the implied
  county density both ways: `424.866` people per sq. km using Phase 1 polygons
  and `514.742` people per sq. km using KNBS land area.

Repeatable reconciliation command:

```bash
docker compose exec -T backend python manage.py reconcile_migori_knbs_worldpop_population \
  --strict \
  --phase1-summary /app/risk/data/source_feeds/migori_worldpop_2026_population_summary.json \
  --download-if-missing \
  --output /app/risk/data/source_feeds/migori_knbs_worldpop_2026_reconciliation.json
```

If the KNBS host certificate is broken during an emergency cache refresh, add
`--allow-insecure-download` and record the operator reason outside the source
artifact. Do not use insecure download as the default path.

### Phase 5: Build Downstream Dataset

Build the population/exposure feature dataset after a successful import:

```bash
docker compose exec -T backend python manage.py build_population_exposure_dataset \
  --as-of 2026-05-05 \
  --release-version "WorldPop G2_CN_POP_R25A_100m KEN 2026 v1"
```

Acceptance gates:

- 40 rows in the feature dataset.
- 40 wards with population baseline coverage.
- 40 wards with population-density exposure coverage.
- Lineage references the WorldPop release and Migori ward polygon source.

Phase 5 implementation status:

- Built the downstream `population-exposure-v1` feature dataset with the
  WorldPop release filter.
- Latest dataset ref:
  `population-exposure-population-exposure-v1-month-5-d6761b2c`.
- Added source-lineage enrichment to the population/exposure feature builder so
  dataset and row lineage now include source refs, aggregation methods, spatial
  resolutions, and polygon SHA-256 values.
- Added `verify_migori_worldpop_feature_dataset` to persist the repeatable
  Phase 5 verification artifact:
  `backend/risk/data/source_feeds/migori_worldpop_2026_population_feature_dataset.json`.
- The verifier defaults to the latest WorldPop feature dataset, so the runbook
  is not tied to a local dataset ref.
- Strict verification passed:
  - `row_count=40`
  - `wards_with_population_baseline=40`
  - `population_density` exposure coverage `40`
  - persisted rows all belong to Migori County
  - row population total sum `1,345,269`, matching the Phase 1 CSV summary
  - dataset source kind `LIVE`
  - source lineage has 80 records, all `live`, `fresh`, and
    `spatially_aggregated_source`
  - lineage references the WorldPop GeoTIFF URL and Migori GeoJSON SHA-256
    `5554c913ff082f7cc2536c772a9190ca81d3b1a7370d872800ff540ce40f6997`
- Cold re-audit hardening: the Migori-only county assertion is now an actual
  strict gate, not just a reported row-count breakdown.
- Additional cold re-audit hardening: row-level lineage now gates the WorldPop
  source URL and Migori polygon SHA-256 for all 40 dataset rows, not only the
  dataset-level lineage block.
- External-audit hardening: Phase 5 verification now requires the Phase 1
  summary to have passed and binds the feature dataset back to the reconciliation
  artifact by matching WorldPop population total, release version, and source
  URL.
- Additional external-audit hardening: Phase 5 verification now compares every
  feature dataset row's `population_total` and `population_density` back to the
  Phase 1 CSV by ward code. The latest strict artifact has zero row-value
  mismatches and zero unexpected ward codes.

Repeatable verification command:

```bash
docker compose exec -T backend python manage.py verify_migori_worldpop_feature_dataset \
  --strict \
  --output /app/risk/data/source_feeds/migori_worldpop_2026_population_feature_dataset.json
```

### Phase 6: Connectorize Later

Once the one-off CSV path is proven, wire it into the existing connector model:

```text
connector_key: worldpop_knbs_population
target_feed_key: gridded_population
canonical_csv_url_setting: SOURCE_DATA_WORLDPOP_KNBS_CANONICAL_CSV_URL
```

For the connector phase, decide whether CCHIS should:

- Fetch a precomputed canonical CSV from object storage.
- Run the raster aggregation job outside the app and publish a CSV.
- Add controlled raster tooling to a scheduled data-processing worker.

The first connector version should still create a source-data upload batch and
run the same dry validation as operator CSV uploads.

Phase 6 implementation status:

- Retargeted the existing `worldpop_knbs_population` source-data connector to
  `gridded_population`, matching the proven Migori CSV contract.
- The connector now uses the WorldPop release setting and source URL setting as
  default upload metadata:
  - `SOURCE_DATA_WORLDPOP_KNBS_SOURCE_URL`
  - `SOURCE_DATA_WORLDPOP_KNBS_RELEASE_VERSION`
  - `SOURCE_DATA_WORLDPOP_KNBS_CANONICAL_CSV_URL`
- The fixture loader now accepts
  `backend/risk/data/source_feeds/migori_worldpop_2026_population.csv` through
  `SOURCE_DATA_CONNECTOR_FIXTURE_DIR=/app/risk/data/source_feeds`, so the Phase
  1 canonical CSV can be replayed without making a duplicate fixture.
- Ran `worldpop_knbs_population` through the source-data connector path. The
  connector created a normal `SourceDataUploadBatch` and ran the same
  source-data dry validation used by operator CSV uploads.
- Connector run id: `1`.
- Linked source-data upload public id:
  `d41e0b40-45ee-457e-889a-cf5bebd101b8`.
- Connector result: `success`, `fetched_record_count=40`, target feed
  `gridded_population`.
- Upload validation result: `passed`, `row_count=40`, `accepted_count=40`,
  `rejected_count=0`, `warning_count=0`.
- CSV fallback remains enabled for correction/recovery; the feed is not forced
  into API-authoritative mode yet.
- Added `verify_migori_worldpop_source_data_connector` and wrote
  `backend/risk/data/source_feeds/migori_worldpop_2026_source_data_connector.json`.
- Strict Phase 6 verification passed. The uploaded artifact content matches the
  Phase 1 CSV after line-ending normalization; the connector rewrites the CSV
  payload through text transport, so the exact byte hash differs while the
  canonical row content remains identical.
- Cold re-audit finding fixed: source-data freshness previously counted
  retired seeded `PopulationBaselineRecord` rows as if they were active direct
  `population_baseline` evidence. Freshness now scopes population/exposure
  counts by feed source type and excludes non-current states
  (`replaced_by_new_release`, `replay_diagnostic`,
  `replacement_not_activated`).
- Current source-data freshness evidence in the Phase 6 artifact:
  - `gridded_population`: `truth_state=csv_backed`, `record_count=40`,
    `status=stale`. The stale status is honest cadence debt from the
    2025-09-01 source timestamp, not a demo-data signal.
  - `population_baseline`: `truth_state=missing`, `record_count=0`, because no
    direct KNBS ward baseline has been imported. KNBS remains reconciliation
    evidence for this pilot.
- Strict Phase 6 verification now gates that the `gridded_population` feed is
  not demo-backed, has 40 current records, the direct `population_baseline`
  feed is not demo-backed, and the connector upload is visible in source-data
  overview.
- Additional cold re-audit hardening: Phase 6 now also gates the connector
  run's source name and source URL against the Phase 1 source evidence, requires
  `gridded_population` to be `csv_backed`, and requires direct
  `population_baseline` to remain `missing` with zero records until a clean
  KNBS ward extract is imported.
- External-audit hardening: Phase 6 now gates the connector upload source name,
  source timestamp (`2025-09-01`), source URL, release version, fetched row
  count versus upload row count, and credential-safe metadata. This prevents
  the connector proof from passing on a right-shaped CSV with stale or generic
  upload metadata.
- External-audit hardening: Phase 6 verification now also requires the Phase 1
  summary to have passed before a connector artifact can be accepted as proof
  that it replayed the generated canonical CSV.

Repeatable connector refresh command for the local generated fixture:

```bash
docker compose exec -T \
  -e SOURCE_DATA_CONNECTOR_FIXTURE_DIR=/app/risk/data/source_feeds \
  -e SOURCE_DATA_WORLDPOP_KNBS_SOURCE_URL=https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/2026/KEN/v1/100m/constrained/ken_pop_2026_CN_100m_R2025A_v1.tif \
  -e SOURCE_DATA_WORLDPOP_KNBS_RELEASE_VERSION="WorldPop G2_CN_POP_R25A_100m KEN 2026 v1" \
  backend python manage.py shell -c \
  "from risk.source_data.connectors import run_source_data_connector_refresh; run=run_source_data_connector_refresh(connector_key='worldpop_knbs_population', options={'source_timestamp':'2025-09-01T00:00:00Z'}); print(run.id, run.status, run.fetched_record_count)"
```

Repeatable connector verification command. By default this verifies the latest
`worldpop_knbs_population` connector run; pass `--run-id` only to pin an older
run.

```bash
docker compose exec -T backend python manage.py verify_migori_worldpop_source_data_connector \
  --strict \
  --output /app/risk/data/source_feeds/migori_worldpop_2026_source_data_connector.json
```

## Validation Checklist

- [x] Local Migori ward register has exactly 40 active wards.
- [x] Local Migori GeoJSON has exactly 40 features.
- [x] Every GeoJSON feature maps to a `Ward` row by code or normalized name.
- [x] WorldPop metadata is stored with id, release, DOI, date, and file URL.
- [x] Raw GeoTIFF is cached outside git.
- [x] Generated CSV has one row per Migori ward.
- [x] Dry validation accepts all 40 rows.
- [x] Dry validation proves `population_total`, `population_density`, and
      `gridded_population_value` are present, positive, and numerically coherent.
- [x] Import creates expected population and exposure records.
- [x] Import verification compares ward-level imported population and density
      values back to the Phase 1 CSV, not just county totals.
- [x] Imported records are not `seeded_demo`.
- [x] Reconciliation summary compares WorldPop 2026 against KNBS 2019/projection.
- [x] Reconciliation recomputes WorldPop totals from canonical DB records and
      records the polygon-area versus KNBS land-area density caveat.
- [x] Downstream feature dataset builds with complete Migori coverage.
- [x] Downstream feature verification compares ward-level feature values back
      to the Phase 1 CSV.
- [x] Dashboard/source freshness surfaces distinguish this feed from demo data
      and ignore retired seeded records.

## Risks And Mitigations

| Risk | Mitigation |
| --- | --- |
| KNBS ward-level extract is not immediately available. | Use KNBS county/sub-county totals for reconciliation and use WorldPop ward aggregates for the test feed. Keep truth class as spatially aggregated. |
| WorldPop 2026 release is alpha/current and may change. | Store release version, DOI, file URL, source date, and generated CSV hash. Treat replacements as release replacements, not silent updates. |
| Raster aggregation introduces spatial error at boundaries. | Use documented polygon source, aggregation method, raster resolution, and area calculation. Keep raw aggregate in `gridded_population_value`. |
| Heavy GIS dependencies complicate backend runtime. | Keep the first pass as an offline processing utility or dedicated data-processing container. Only add app dependencies after the workflow stabilizes. |
| Users misread WorldPop as direct census truth. | Label records as `spatially_aggregated_source`; keep KNBS as the official direct baseline anchor. |
| Old seeded records remain visible beside real imports. | Use freshness/history surfaces to make demo-backed, seeded, and source-backed states explicit. |

## Resolved And Open Decisions

- Resolved for this pilot: keep the generated Migori WorldPop CSV as the small,
  source-backed fixture at
  `backend/risk/data/source_feeds/migori_worldpop_2026_population.csv`, with the
  raw raster staying in ignored `source_cache/`.
- Resolved for this pilot: target `gridded_population`; keep direct KNBS
  `population_baseline` missing until a clean ward-level KNBS extract is found.
- Resolved for this pilot: raster aggregation lives in a Django management
  command using GDAL CLI tooling. A scheduled external data-processing job is
  still the likely production shape after the pilot.
- What reconciliation tolerance should become the official warning threshold
  after KNBS projections are selected?
- Should production dashboards display polygon-area density, KNBS land-area
  normalized density, or both when ward polygons and KNBS land-area denominators
  materially differ?

## Definition Of Done

This pilot is done when CCHIS can show a Migori-only population/exposure dataset
where:

- seeded-demo population records are no longer the only e2e baseline;
- WorldPop 2026 ward aggregates are ingested through the existing audited path;
- KNBS 2019/projection evidence is recorded as the official demographic anchor;
- downstream feature generation has complete coverage for all 40 Migori wards;
- documentation clearly says this is source-backed testing, not live outbreak
  surveillance and not automatic model-promotion evidence.

## References

- KNBS portals: https://www.knbs.or.ke/portals/
- KNBS 2019 census reports: https://www.knbs.or.ke/reports/kenya-census-2019/
- WorldPop API introduction: https://www.worldpop.org/sdi/introapi/
- WorldPop advanced API: https://www.worldpop.org/sdi/advancedapi/
- WorldPop API rate limits: https://www.worldpop.org/sdi/api_rate_limits/
- WorldPop population metadata API: https://hub.worldpop.org/rest/data/pop
- Existing source strategy: `docs/CCHIS_DATA_SOURCE_FEEDS.md`
- Existing connector plan: `docs/SOURCE_DATA_API_CONNECTORS.md`
