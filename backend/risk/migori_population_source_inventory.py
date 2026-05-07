from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests
from django.utils import timezone

from risk.map_data import MIGORI_WARD_GEOMETRY_PATH
from risk.models import Ward
from risk.ward_geometry_pipeline import (
    build_geometry_validation_summary,
    compute_file_sha256,
    load_geojson_payload,
)


DEFAULT_COUNTY = "Migori"
DEFAULT_EXPECTED_WARD_COUNT = 40
DEFAULT_WORLDPOP_DATASET_KEY = "G2_CN_POP_R25A_100m"
DEFAULT_WORLDPOP_ISO3 = "KEN"
DEFAULT_WORLDPOP_YEAR = "2026"
EXPECTED_WORLDPOP_RECORD_ID = "74000"
EXPECTED_WORLDPOP_SOURCE_DATE = "2025-09-01"
EXPECTED_WORLDPOP_DOI = "10.5258/SOTON/WP00839"
EXPECTED_WORLDPOP_DATA_FORMAT = "Geotiff"
EXPECTED_WORLDPOP_FILE_URL = (
    "https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/2026/KEN/v1/100m/constrained/"
    "ken_pop_2026_CN_100m_R2025A_v1.tif"
)
WORLDPOP_METADATA_API_ROOT = "https://hub.worldpop.org/rest/data/pop"
WORLDPOP_LICENSE_URL = "https://hub.worldpop.org/data/licence.txt"


KNBS_2019_KPHC_REFERENCES: tuple[dict[str, str], ...] = (
    {
        "label": "KNBS 2019 Kenya Population and Housing Census reports",
        "url": "https://new.knbs.or.ke/2019-kenya-population-and-housing-census-reports/",
        "use": "Official KPHC report landing page and volume references.",
    },
    {
        "label": "KNBS 2019 census data tables",
        "url": "https://new.knbs.or.ke/reports/kenya-census-2019/",
        "use": "Official downloadable census table index, including population, households, density, and projections.",
    },
    {
        "label": "KNBS 2019 KPHC Volume II administrative units table",
        "url": "https://new.knbs.or.ke/wp-content/uploads/2023/09/2019-Kenya-population-and-Housing-Census-Population-households-density-by-administrative-units.xlsx",
        "use": "Candidate source for official administrative-unit totals; assess Migori ward/sub-location fit before direct import.",
    },
    {
        "label": "KNBS 2019 KPHC sub-county table",
        "url": "https://new.knbs.or.ke/wp-content/uploads/2023/09/2019-Kenya-population-and-Housing-Census-Population-households-density-by-sub-county.xlsx",
        "use": "Sub-county reconciliation source when ward-level direct import is not available.",
    },
    {
        "label": "KNBS Kenya population projections summary",
        "url": "https://www.knbs.or.ke/wp-content/uploads/2023/09/2019-Kenya-population-and-Housing-Census-Summary-Report-on-Kenyas-Population-Projections.pdf",
        "use": "Projection anchor for comparing 2026 WorldPop ward aggregates against KNBS expectations.",
    },
    {
        "label": "KeNADA KPHC 2019 catalog",
        "url": "https://statistics.knbs.or.ke/nada/index.php/catalog/study/KEN-KNBS-KPHC-2019-v01",
        "use": "Catalog provenance for the 2019 census collection; do not ingest raw microdata in the pilot.",
    },
)


def worldpop_metadata_url(*, dataset_key: str = DEFAULT_WORLDPOP_DATASET_KEY, iso3: str = DEFAULT_WORLDPOP_ISO3) -> str:
    return f"{WORLDPOP_METADATA_API_ROOT}/{dataset_key}?iso3={iso3}"


def select_worldpop_population_record(payload: dict[str, Any], *, popyear: str = DEFAULT_WORLDPOP_YEAR) -> dict[str, Any]:
    records = payload.get("data")
    if not isinstance(records, list):
        raise ValueError("WorldPop metadata payload did not contain a data list.")

    for record in records:
        if not isinstance(record, dict):
            continue
        if str(record.get("popyear") or "").strip() == str(popyear):
            return record
    raise ValueError(f"WorldPop metadata payload did not contain popyear={popyear}.")


def fetch_worldpop_population_record(
    *,
    dataset_key: str = DEFAULT_WORLDPOP_DATASET_KEY,
    iso3: str = DEFAULT_WORLDPOP_ISO3,
    popyear: str = DEFAULT_WORLDPOP_YEAR,
    timeout: int = 30,
) -> dict[str, Any]:
    response = requests.get(worldpop_metadata_url(dataset_key=dataset_key, iso3=iso3), timeout=timeout)
    response.raise_for_status()
    return select_worldpop_population_record(response.json(), popyear=popyear)


def normalize_worldpop_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(record.get("id") or ""),
        "title": str(record.get("title") or ""),
        "popyear": str(record.get("popyear") or ""),
        "source_date": str(record.get("date") or ""),
        "doi": str(record.get("doi") or ""),
        "category": str(record.get("category") or ""),
        "data_format": str(record.get("data_format") or ""),
        "source": str(record.get("source") or ""),
        "license_url": str(record.get("license") or WORLDPOP_LICENSE_URL),
        "files": [str(item) for item in record.get("files", []) if str(item).strip()],
        "citation": str(record.get("citation") or ""),
        "description": str(record.get("desc") or ""),
        "url_summary": str(record.get("url_summary") or ""),
    }


def worldpop_record_expected_release_gates(
    record: dict[str, Any] | None,
    *,
    expected_popyear: str = DEFAULT_WORLDPOP_YEAR,
) -> dict[str, bool]:
    if not record:
        return {
            "worldpop_record_id_matches_expected": False,
            "worldpop_popyear_matches_expected": False,
            "worldpop_source_date_matches_expected": False,
            "worldpop_doi_matches_expected": False,
            "worldpop_data_format_is_geotiff": False,
            "worldpop_file_url_matches_expected": False,
            "worldpop_category_mentions_100m": False,
            "worldpop_source_mentions_worldpop": False,
            "worldpop_citation_records_expected_doi": False,
        }

    files = set(record.get("files") or [])
    category = str(record.get("category") or "").lower()
    source = str(record.get("source") or "").lower()
    citation = str(record.get("citation") or "")
    return {
        "worldpop_record_id_matches_expected": record.get("id") == EXPECTED_WORLDPOP_RECORD_ID,
        "worldpop_popyear_matches_expected": record.get("popyear") == str(expected_popyear),
        "worldpop_source_date_matches_expected": record.get("source_date") == EXPECTED_WORLDPOP_SOURCE_DATE,
        "worldpop_doi_matches_expected": record.get("doi") == EXPECTED_WORLDPOP_DOI,
        "worldpop_data_format_is_geotiff": str(record.get("data_format") or "").lower() == EXPECTED_WORLDPOP_DATA_FORMAT.lower(),
        "worldpop_file_url_matches_expected": EXPECTED_WORLDPOP_FILE_URL in files,
        "worldpop_category_mentions_100m": "100m" in category,
        "worldpop_source_mentions_worldpop": "worldpop" in source,
        "worldpop_citation_records_expected_doi": bool(citation) and EXPECTED_WORLDPOP_DOI in citation,
    }


def build_migori_population_phase0_inventory(
    *,
    county: str = DEFAULT_COUNTY,
    geojson_path: str | Path = MIGORI_WARD_GEOMETRY_PATH,
    expected_ward_count: int = DEFAULT_EXPECTED_WARD_COUNT,
    worldpop_dataset_key: str = DEFAULT_WORLDPOP_DATASET_KEY,
    worldpop_iso3: str = DEFAULT_WORLDPOP_ISO3,
    worldpop_popyear: str = DEFAULT_WORLDPOP_YEAR,
    worldpop_record: dict[str, Any] | None = None,
    worldpop_fetch_error: str = "",
) -> dict[str, Any]:
    path = Path(geojson_path).expanduser().resolve()
    payload = load_geojson_payload(path)
    geometry_summary = build_geometry_validation_summary(payload, county)

    active_wards = list(
        Ward.objects.filter(county__iexact=county, is_active=True)
        .order_by("name")
        .values("name", "ward_code", "sub_county")
    )
    all_county_ward_count = Ward.objects.filter(county__iexact=county).count()

    normalized_worldpop_record = normalize_worldpop_record(worldpop_record) if worldpop_record else None
    phase0_gates = {
        "active_ward_count_matches_expected": len(active_wards) == expected_ward_count,
        "geojson_feature_count_matches_expected": geometry_summary["filtered_feature_count"] == expected_ward_count,
        "geojson_backend_count_matches_expected": geometry_summary["backend_ward_count"] == expected_ward_count,
        "geojson_has_no_unmatched_features": geometry_summary["backend_ward_unmatched_feature_count"] == 0,
        "geojson_has_no_missing_backend_ward_names": not geometry_summary["missing_backend_ward_names"],
        "geojson_has_no_missing_backend_ward_codes": not geometry_summary["missing_backend_ward_codes"],
        "geojson_has_no_duplicates": not geometry_summary["duplicate_source_names"]
        and not geometry_summary["duplicate_source_codes"],
        "geojson_has_no_placeholder_geometry": not geometry_summary["placeholder_geometry_detected"],
        "worldpop_2026_metadata_recorded": normalized_worldpop_record is not None and not worldpop_fetch_error,
        "knbs_references_recorded": True,
    }
    phase0_gates.update(
        worldpop_record_expected_release_gates(
            normalized_worldpop_record,
            expected_popyear=str(worldpop_popyear),
        )
    )

    return {
        "phase": "migori_knbs_worldpop_phase_0_source_inventory",
        "generated_at": timezone.now().isoformat(),
        "passed": all(phase0_gates.values()),
        "county": county,
        "expected_ward_count": expected_ward_count,
        "phase0_gates": phase0_gates,
        "local_ward_register": {
            "active_ward_count": len(active_wards),
            "all_county_ward_count": all_county_ward_count,
            "ward_codes_missing_count": sum(1 for ward in active_wards if not ward["ward_code"]),
            "wards": active_wards,
        },
        "local_geojson": {
            "path": str(path),
            "sha256": compute_file_sha256(path),
            "summary": geometry_summary,
        },
        "worldpop": {
            "metadata_url": worldpop_metadata_url(dataset_key=worldpop_dataset_key, iso3=worldpop_iso3),
            "selected_popyear": str(worldpop_popyear),
            "expected_release": {
                "id": EXPECTED_WORLDPOP_RECORD_ID,
                "popyear": str(worldpop_popyear),
                "source_date": EXPECTED_WORLDPOP_SOURCE_DATE,
                "doi": EXPECTED_WORLDPOP_DOI,
                "data_format": EXPECTED_WORLDPOP_DATA_FORMAT,
                "file_url": EXPECTED_WORLDPOP_FILE_URL,
            },
            "record": normalized_worldpop_record,
            "fetch_error": worldpop_fetch_error,
            "license_confirmation": {
                "license": "Creative Commons Attribution 4.0 International",
                "license_url": WORLDPOP_LICENSE_URL,
                "attribution_required": True,
                "raw_geotiff_commit_policy": "Do not commit the raw GeoTIFF to the repo.",
            },
        },
        "knbs": {
            "role": "Official demographic anchor and reconciliation source for Migori population/exposure testing.",
            "direct_import_status": "pending_clean_migori_ward_extract",
            "pilot_rule": "Use aggregated tables only; do not ingest raw census microdata in the pilot source-data path.",
            "references": list(KNBS_2019_KPHC_REFERENCES),
        },
    }


def inventory_to_json(inventory: dict[str, Any]) -> str:
    return json.dumps(inventory, indent=2, sort_keys=True)
