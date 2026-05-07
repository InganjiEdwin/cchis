from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zipfile import ZipFile

import requests
from django.db.models import Count, Sum
from django.utils import timezone

from risk.migori_worldpop_population_import import (
    DEFAULT_IMPORT_SUMMARY_PATH,
    DEFAULT_RELEASE_VERSION,
    DEFAULT_SOURCE_NAME,
    DEFAULT_SOURCE_TYPE,
)
from risk.migori_worldpop_population_csv import DEFAULT_SUMMARY_PATH as DEFAULT_PHASE1_SUMMARY_PATH
from risk.models import (
    ExposureFeatureRecord,
    PopulationBaselineRecord,
    PopulationExposureFreshness,
    PopulationExposureIngestionRun,
    PopulationExposureSourceKind,
    PopulationExposureTruth,
)


RISK_DATA_DIR = Path(__file__).resolve().parent / "data"
KNBS_CACHE_DIR = RISK_DATA_DIR / "source_cache" / "knbs"
DEFAULT_RECONCILIATION_SUMMARY_PATH = (
    RISK_DATA_DIR / "source_feeds" / "migori_knbs_worldpop_2026_reconciliation.json"
)
KNBS_COUNTY_BASELINE_URL = (
    "https://new.knbs.or.ke/wp-content/uploads/2023/09/"
    "2019-Kenya-population-and-Housing-Census-Population-households-density-by-county.xlsx"
)
KNBS_SUB_COUNTY_BASELINE_URL = (
    "https://new.knbs.or.ke/wp-content/uploads/2023/09/"
    "2019-Kenya-population-and-Housing-Census-Population-households-density-by-sub-county.xlsx"
)
KNBS_PROJECTION_URL = (
    "https://new.knbs.or.ke/wp-content/uploads/2024/04/"
    "2023-Economic-Survey-Kenya-Highlights-of-Population-Projections.xlsx"
)
DEFAULT_COUNTY_BASELINE_PATH = KNBS_CACHE_DIR / "knbs_2019_population_households_density_by_county.xlsx"
DEFAULT_SUB_COUNTY_BASELINE_PATH = KNBS_CACHE_DIR / "knbs_2019_population_households_density_by_sub_county.xlsx"
DEFAULT_PROJECTION_PATH = KNBS_CACHE_DIR / "knbs_2023_economic_survey_population_projections.xlsx"
DEFAULT_COUNTY = "Migori"
DEFAULT_TARGET_YEAR = 2026
DEFAULT_WARNING_THRESHOLD = 0.20
DEFAULT_EXPECTED_WARD_COUNT = 40
XLSX_MAIN_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


@dataclass(frozen=True)
class KnbsSourceFile:
    label: str
    url: str
    path: Path


KNBS_SOURCE_FILES = (
    KnbsSourceFile("county_2019_baseline", KNBS_COUNTY_BASELINE_URL, DEFAULT_COUNTY_BASELINE_PATH),
    KnbsSourceFile("sub_county_2019_baseline", KNBS_SUB_COUNTY_BASELINE_URL, DEFAULT_SUB_COUNTY_BASELINE_PATH),
    KnbsSourceFile("county_projection", KNBS_PROJECTION_URL, DEFAULT_PROJECTION_PATH),
)


def normalize_label(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _to_float(value: Any) -> float | None:
    text = str(value or "").strip().replace(",", "")
    if text in {"", "-"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _to_int(value: Any) -> int | None:
    parsed = _to_float(value)
    if parsed is None:
        return None
    return int(round(parsed))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _knbs_source_download_metadata(source_file: KnbsSourceFile, *, downloaded: bool, verify_tls: bool) -> dict[str, Any]:
    return {
        "label": source_file.label,
        "downloaded": downloaded,
        "path": str(source_file.path),
        "url": source_file.url,
        "bytes": source_file.path.stat().st_size,
        "sha256": file_sha256(source_file.path),
        "tls_verification_disabled": not verify_tls,
    }


def download_source_file(source_file: KnbsSourceFile, *, verify_tls: bool = True, timeout: int = 60) -> dict[str, Any]:
    source_file.path.parent.mkdir(parents=True, exist_ok=True)
    if source_file.path.exists() and source_file.path.stat().st_size > 0:
        return _knbs_source_download_metadata(source_file, downloaded=False, verify_tls=verify_tls)

    response = requests.get(source_file.url, timeout=timeout, verify=verify_tls)
    response.raise_for_status()
    source_file.path.write_bytes(response.content)
    return _knbs_source_download_metadata(source_file, downloaded=True, verify_tls=verify_tls)


def ensure_knbs_source_files(*, download_if_missing: bool = True, verify_tls: bool = True) -> list[dict[str, Any]]:
    results = []
    for source_file in KNBS_SOURCE_FILES:
        if source_file.path.exists() and source_file.path.stat().st_size > 0:
            results.append(_knbs_source_download_metadata(source_file, downloaded=False, verify_tls=True))
            continue
        if not download_if_missing:
            raise FileNotFoundError(f"Missing KNBS source file: {source_file.path}")
        results.append(download_source_file(source_file, verify_tls=verify_tls))
    return results


def _column_index(cell_ref: str) -> int:
    letters = "".join(character for character in cell_ref if character.isalpha())
    value = 0
    for character in letters:
        value = value * 26 + ord(character.upper()) - 64
    return max(value - 1, 0)


def read_xlsx_sheet_rows(path: Path, *, sheet_path: str = "xl/worksheets/sheet1.xml") -> list[list[str]]:
    import xml.etree.ElementTree as ET

    with ZipFile(path) as archive:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall("m:si", XLSX_MAIN_NS):
                shared_strings.append("".join(text.text or "" for text in item.findall(".//m:t", XLSX_MAIN_NS)))

        root = ET.fromstring(archive.read(sheet_path))
        rows: list[list[str]] = []
        for row in root.findall(".//m:sheetData/m:row", XLSX_MAIN_NS):
            values: list[str] = []
            for cell in row.findall("m:c", XLSX_MAIN_NS):
                index = _column_index(cell.attrib.get("r", "A"))
                while len(values) <= index:
                    values.append("")
                cell_type = cell.attrib.get("t")
                value_node = cell.find("m:v", XLSX_MAIN_NS)
                inline_node = cell.find("m:is", XLSX_MAIN_NS)
                value = ""
                if cell_type == "s" and value_node is not None:
                    value = shared_strings[int(value_node.text or "0")]
                elif cell_type == "inlineStr" and inline_node is not None:
                    value = "".join(text.text or "" for text in inline_node.findall(".//m:t", XLSX_MAIN_NS))
                elif value_node is not None:
                    value = value_node.text or ""
                values[index] = value
            rows.append(values)
        return rows


def extract_county_2019_baseline(path: Path, *, county: str = DEFAULT_COUNTY) -> dict[str, Any]:
    target = normalize_label(county)
    for row_number, row in enumerate(read_xlsx_sheet_rows(path), start=1):
        if not row or normalize_label(str(row[0])) != target:
            continue
        return {
            "row_number": row_number,
            "county": str(row[0]).strip(),
            "total_population": _to_int(row[1]),
            "male": _to_int(row[2]),
            "female": _to_int(row[3]),
            "intersex": _to_int(row[4]),
            "households_total": _to_int(row[5]),
            "land_area_sq_km": _to_float(row[8]),
            "density_persons_per_sq_km": _to_float(row[9]),
            "source_url": KNBS_COUNTY_BASELINE_URL,
        }
    raise ValueError(f"County '{county}' was not found in {path}.")


def extract_sub_county_2019_rows(path: Path, *, county: str = DEFAULT_COUNTY) -> dict[str, Any]:
    rows = read_xlsx_sheet_rows(path)
    target = normalize_label(county)
    county_row_index = None
    for index, row in enumerate(rows):
        if row and normalize_label(str(row[0])) == target:
            county_row_index = index
            break
    if county_row_index is None:
        raise ValueError(f"County '{county}' was not found in {path}.")

    sub_counties = []
    for row in rows[county_row_index + 1 :]:
        label = str(row[0] if row else "")
        if not label:
            continue
        if not label.startswith("        "):
            break
        sub_counties.append(
            {
                "sub_county": label.strip(),
                "total_population": _to_int(row[1]),
                "male": _to_int(row[2]),
                "female": _to_int(row[3]),
                "households_total": _to_int(row[4]),
                "land_area_sq_km": _to_float(row[7]),
                "density_persons_per_sq_km": _to_float(row[8]),
            }
        )

    return {
        "county": county,
        "sub_county_count": len(sub_counties),
        "sub_county_population_sum": sum(item["total_population"] or 0 for item in sub_counties),
        "sub_counties": sub_counties,
        "source_url": KNBS_SUB_COUNTY_BASELINE_URL,
    }


def extract_county_projection(path: Path, *, county: str = DEFAULT_COUNTY, target_year: int = DEFAULT_TARGET_YEAR) -> dict[str, Any]:
    rows = read_xlsx_sheet_rows(path, sheet_path="xl/worksheets/sheet2.xml")
    header = rows[2]
    year_columns: dict[int, int] = {}
    for index, value in enumerate(header):
        parsed = _to_int(value)
        if parsed:
            year_columns[parsed] = index

    target = normalize_label(county)
    county_row = None
    for row_number, row in enumerate(rows, start=1):
        if row and normalize_label(str(row[0])) == target:
            county_row = row
            break
    if county_row is None:
        raise ValueError(f"County '{county}' was not found in {path}.")

    projections = {
        year: int(round(float(county_row[column]) * 1000))
        for year, column in year_columns.items()
        if column < len(county_row) and _to_float(county_row[column]) is not None
    }
    if target_year in projections:
        target_projection = projections[target_year]
        method = "exact"
        lower_year = upper_year = target_year
    else:
        lower_candidates = [year for year in projections if year < target_year]
        upper_candidates = [year for year in projections if year > target_year]
        if not lower_candidates or not upper_candidates:
            raise ValueError(f"Cannot interpolate projection for {target_year}; surrounding years are missing.")
        lower_year = max(lower_candidates)
        upper_year = min(upper_candidates)
        lower_value = projections[lower_year]
        upper_value = projections[upper_year]
        fraction = (target_year - lower_year) / (upper_year - lower_year)
        target_projection = int(round(lower_value + (upper_value - lower_value) * fraction))
        method = f"linear_interpolation_{lower_year}_{upper_year}"

    return {
        "county": county,
        "target_year": target_year,
        "target_projection": target_projection,
        "method": method,
        "lower_year": lower_year,
        "upper_year": upper_year,
        "available_projections": projections,
        "source_url": KNBS_PROJECTION_URL,
        "unit_note": "Source workbook values are in thousands; values here are converted to people.",
    }


def percentage_difference(candidate: int | float, reference: int | float) -> float | None:
    if not reference:
        return None
    return (candidate - reference) / reference


def comparison(candidate: int, reference: int, *, label: str) -> dict[str, Any]:
    pct = percentage_difference(candidate, reference)
    return {
        "label": label,
        "candidate": candidate,
        "reference": reference,
        "absolute_difference": candidate - reference,
        "percentage_difference": pct,
        "percentage_difference_display": None if pct is None else round(pct * 100, 3),
    }


def _source_file_metadata(path: Path, url: str) -> dict[str, Any]:
    return {
        "path": str(path),
        "filename": Path(urlparse(url).path).name,
        "url": url,
        "bytes": path.stat().st_size if path.exists() else 0,
        "sha256": file_sha256(path) if path.exists() else "",
        "exists": path.exists(),
    }


def _replacement_ward_ids_from_import_summary(import_summary: dict[str, Any]) -> set[int]:
    run_id = (import_summary.get("run") or {}).get("id")
    if not run_id:
        return set()
    try:
        run = PopulationExposureIngestionRun.objects.get(id=run_id)
    except PopulationExposureIngestionRun.DoesNotExist:
        return set()
    population_ward_ids = set(PopulationBaselineRecord.objects.filter(ingestion_run=run).values_list("ward_id", flat=True))
    density_ward_ids = set(
        ExposureFeatureRecord.objects.filter(
            ingestion_run=run,
            exposure_type=ExposureFeatureRecord.EXPOSURE_POPULATION_DENSITY,
        ).values_list("ward_id", flat=True)
    )
    return population_ward_ids | density_ward_ids


def _worldpop_import_db_summary(import_summary: dict[str, Any], *, county: str) -> dict[str, Any]:
    run_id = (import_summary.get("run") or {}).get("id")
    if not run_id:
        return {
            "run_found": False,
            "run_status": "",
            "source_name": "",
            "source_type": "",
            "release_version": "",
            "source_ref": "",
            "population_record_count": 0,
            "density_record_count": 0,
            "population_total_sum": 0,
            "population_distinct_ward_count": 0,
            "density_distinct_ward_count": 0,
            "population_and_density_ward_sets_match": False,
            "population_county_counts": [],
            "density_county_counts": [],
        }
    try:
        run = PopulationExposureIngestionRun.objects.get(id=run_id)
    except PopulationExposureIngestionRun.DoesNotExist:
        return {
            "run_found": False,
            "run_id": run_id,
            "run_status": "",
            "source_name": "",
            "source_type": "",
            "release_version": "",
            "source_ref": "",
            "population_record_count": 0,
            "density_record_count": 0,
            "population_total_sum": 0,
            "population_distinct_ward_count": 0,
            "density_distinct_ward_count": 0,
            "population_and_density_ward_sets_match": False,
            "population_county_counts": [],
            "density_county_counts": [],
        }

    population_qs = PopulationBaselineRecord.objects.filter(ingestion_run=run)
    density_qs = ExposureFeatureRecord.objects.filter(
        ingestion_run=run,
        exposure_type=ExposureFeatureRecord.EXPOSURE_POPULATION_DENSITY,
    )
    population_ward_ids = set(population_qs.values_list("ward_id", flat=True))
    density_ward_ids = set(density_qs.values_list("ward_id", flat=True))
    return {
        "run_found": True,
        "run_id": run.id,
        "run_status": run.status,
        "source_name": run.source_name,
        "source_type": run.source_type,
        "release_version": run.release_version,
        "source_ref": run.source_ref,
        "population_record_count": population_qs.count(),
        "density_record_count": density_qs.count(),
        "population_total_sum": population_qs.aggregate(total=Sum("population_total")).get("total") or 0,
        "population_distinct_ward_count": len(population_ward_ids),
        "density_distinct_ward_count": len(density_ward_ids),
        "population_and_density_ward_sets_match": population_ward_ids == density_ward_ids,
        "population_county_counts": list(
            population_qs.values("ward__county").annotate(count=Count("id")).order_by("ward__county")
        ),
        "density_county_counts": list(
            density_qs.values("ward__county").annotate(count=Count("id")).order_by("ward__county")
        ),
        "population_truth_counts": dict(population_qs.values_list("truth_class").annotate(count=Count("id"))),
        "density_truth_counts": dict(density_qs.values_list("truth_class").annotate(count=Count("id"))),
        "population_source_kind_counts": dict(population_qs.values_list("source_kind").annotate(count=Count("id"))),
        "density_source_kind_counts": dict(density_qs.values_list("source_kind").annotate(count=Count("id"))),
        "population_freshness_counts": dict(population_qs.values_list("freshness_state").annotate(count=Count("id"))),
        "density_freshness_counts": dict(density_qs.values_list("freshness_state").annotate(count=Count("id"))),
        "expected_county": county,
    }


def _load_json_if_exists(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _area_reconciliation(*, phase1_summary: dict[str, Any], knbs_2019: dict[str, Any], worldpop_total: int) -> dict[str, Any]:
    polygon_area = _to_float(phase1_summary.get("ward_area_total_km2"))
    knbs_land_area = _to_float(knbs_2019.get("land_area_sq_km"))
    area_pct = percentage_difference(polygon_area or 0, knbs_land_area or 0)
    polygon_density = (worldpop_total / polygon_area) if polygon_area else None
    knbs_area_density = (worldpop_total / knbs_land_area) if knbs_land_area else None
    discrepancy_threshold = 0.05
    caveat_required = area_pct is not None and abs(area_pct) > discrepancy_threshold
    caveat = (
        "WorldPop CSV population_density uses local Migori polygon area from the aggregation GeoJSON, "
        "not KNBS official land area; compare density values with this denominator difference in mind."
        if caveat_required
        else ""
    )
    return {
        "phase1_ward_area_total_km2": polygon_area,
        "knbs_2019_land_area_sq_km": knbs_land_area,
        "area_percentage_difference": area_pct,
        "area_percentage_difference_display": None if area_pct is None else round(area_pct * 100, 3),
        "worldpop_density_using_phase1_polygon_area": None if polygon_density is None else round(polygon_density, 3),
        "worldpop_density_using_knbs_land_area": None if knbs_area_density is None else round(knbs_area_density, 3),
        "discrepancy_threshold": discrepancy_threshold,
        "caveat_required": caveat_required,
        "density_denominator_caveat": caveat,
    }


def build_migori_knbs_worldpop_reconciliation(
    *,
    county: str = DEFAULT_COUNTY,
    target_year: int = DEFAULT_TARGET_YEAR,
    warning_threshold: float = DEFAULT_WARNING_THRESHOLD,
    expected_ward_count: int = DEFAULT_EXPECTED_WARD_COUNT,
    worldpop_import_summary_path: Path = DEFAULT_IMPORT_SUMMARY_PATH,
    phase1_summary_path: Path | None = DEFAULT_PHASE1_SUMMARY_PATH,
    county_baseline_path: Path = DEFAULT_COUNTY_BASELINE_PATH,
    sub_county_baseline_path: Path = DEFAULT_SUB_COUNTY_BASELINE_PATH,
    projection_path: Path = DEFAULT_PROJECTION_PATH,
) -> dict[str, Any]:
    import_summary = json.loads(worldpop_import_summary_path.read_text(encoding="utf-8"))
    import_summary_worldpop_total = int(import_summary["records"]["population_total_sum"])
    worldpop_db_summary = _worldpop_import_db_summary(import_summary, county=county)
    worldpop_total = int(worldpop_db_summary["population_total_sum"] or 0)
    replacement_ward_ids = _replacement_ward_ids_from_import_summary(import_summary)
    seeded_population_scope = PopulationBaselineRecord.objects.filter(
        source_kind=PopulationExposureSourceKind.SEEDED,
        truth_class=PopulationExposureTruth.SEEDED_DEMO,
        ward__county__iexact=county,
    )
    seeded_density_scope = ExposureFeatureRecord.objects.filter(
        source_kind=PopulationExposureSourceKind.SEEDED,
        truth_class=PopulationExposureTruth.SEEDED_DEMO,
        exposure_type=ExposureFeatureRecord.EXPOSURE_POPULATION_DENSITY,
        ward__county__iexact=county,
    )
    if replacement_ward_ids:
        seeded_population_scope = seeded_population_scope.filter(ward_id__in=replacement_ward_ids)
        seeded_density_scope = seeded_density_scope.filter(ward_id__in=replacement_ward_ids)
    current_seeded_population_count = seeded_population_scope.exclude(
        freshness_state=PopulationExposureFreshness.REPLACED_BY_NEW_RELEASE
    ).count()
    current_seeded_density_count = seeded_density_scope.exclude(
        freshness_state=PopulationExposureFreshness.REPLACED_BY_NEW_RELEASE
    ).count()
    retired_seeded_population_count = seeded_population_scope.filter(
        freshness_state=PopulationExposureFreshness.REPLACED_BY_NEW_RELEASE
    ).count()
    retired_seeded_density_count = seeded_density_scope.filter(
        freshness_state=PopulationExposureFreshness.REPLACED_BY_NEW_RELEASE
    ).count()
    seeded_demo_total = (
        seeded_population_scope.filter(freshness_state=PopulationExposureFreshness.REPLACED_BY_NEW_RELEASE)
        .aggregate(total=Sum("population_total"))
        .get("total")
        or 0
    )
    knbs_2019 = extract_county_2019_baseline(county_baseline_path, county=county)
    sub_counties = extract_sub_county_2019_rows(sub_county_baseline_path, county=county)
    projection = extract_county_projection(projection_path, county=county, target_year=target_year)
    projection_reference = int(projection["target_projection"])
    phase1_summary = _load_json_if_exists(phase1_summary_path)
    area_reconciliation = _area_reconciliation(
        phase1_summary=phase1_summary,
        knbs_2019=knbs_2019,
        worldpop_total=worldpop_total,
    )

    comparisons = {
        "worldpop_vs_knbs_2019_baseline": comparison(
            worldpop_total,
            int(knbs_2019["total_population"]),
            label="WorldPop 2026 ward aggregate vs KNBS 2019 census baseline",
        ),
        "worldpop_vs_knbs_projection": comparison(
            worldpop_total,
            projection_reference,
            label=f"WorldPop 2026 ward aggregate vs KNBS {target_year} projection",
        ),
        "seeded_demo_vs_knbs_2019_baseline": comparison(
            int(seeded_demo_total),
            int(knbs_2019["total_population"]),
            label="Retired seeded-demo total vs KNBS 2019 census baseline",
        ),
    }
    knbs_source_files = {
        "county_baseline": _source_file_metadata(county_baseline_path, KNBS_COUNTY_BASELINE_URL),
        "sub_county_baseline": _source_file_metadata(sub_county_baseline_path, KNBS_SUB_COUNTY_BASELINE_URL),
        "projection": _source_file_metadata(projection_path, KNBS_PROJECTION_URL),
    }
    projection_pct = comparisons["worldpop_vs_knbs_projection"]["percentage_difference"]
    sub_county_matches = sub_counties["sub_county_population_sum"] == knbs_2019["total_population"]
    gates = {
        "worldpop_import_summary_passed": import_summary.get("passed") is True,
        "worldpop_import_summary_total_matches_db": import_summary_worldpop_total == worldpop_total,
        "worldpop_db_run_found": worldpop_db_summary["run_found"] is True,
        "worldpop_db_run_status_success": worldpop_db_summary.get("run_status")
        == PopulationExposureIngestionRun.STATUS_SUCCESS,
        "worldpop_db_run_identity_expected": worldpop_db_summary.get("source_name") == DEFAULT_SOURCE_NAME
        and worldpop_db_summary.get("source_type") == DEFAULT_SOURCE_TYPE
        and worldpop_db_summary.get("release_version") == DEFAULT_RELEASE_VERSION,
        "worldpop_db_run_source_ref_matches_import_summary": bool((import_summary.get("run") or {}).get("source_ref"))
        and worldpop_db_summary.get("source_ref") == (import_summary.get("run") or {}).get("source_ref"),
        "worldpop_db_population_ward_count_expected": worldpop_db_summary["population_distinct_ward_count"]
        == expected_ward_count,
        "worldpop_db_density_ward_count_expected": worldpop_db_summary["density_distinct_ward_count"]
        == expected_ward_count,
        "worldpop_db_population_density_ward_sets_match": worldpop_db_summary[
            "population_and_density_ward_sets_match"
        ]
        is True,
        "worldpop_db_records_scoped_to_county": worldpop_db_summary["population_county_counts"]
        == [{"ward__county": county, "count": expected_ward_count}]
        and worldpop_db_summary["density_county_counts"] == [{"ward__county": county, "count": expected_ward_count}],
        "worldpop_db_record_metadata_expected": worldpop_db_summary.get("population_truth_counts")
        == {PopulationExposureTruth.SPATIALLY_AGGREGATED_SOURCE: expected_ward_count}
        and worldpop_db_summary.get("density_truth_counts")
        == {PopulationExposureTruth.SPATIALLY_AGGREGATED_SOURCE: expected_ward_count}
        and worldpop_db_summary.get("population_source_kind_counts")
        == {PopulationExposureSourceKind.LIVE: expected_ward_count}
        and worldpop_db_summary.get("density_source_kind_counts")
        == {PopulationExposureSourceKind.LIVE: expected_ward_count}
        and worldpop_db_summary.get("population_freshness_counts")
        == {PopulationExposureFreshness.FRESH: expected_ward_count}
        and worldpop_db_summary.get("density_freshness_counts")
        == {PopulationExposureFreshness.FRESH: expected_ward_count},
        "knbs_2019_baseline_found": bool(knbs_2019.get("total_population")),
        "knbs_projection_found_or_interpolated": bool(projection_reference),
        "knbs_source_files_exist_with_hashes": all(
            metadata["exists"] and metadata["bytes"] > 0 and bool(metadata["sha256"])
            for metadata in knbs_source_files.values()
        ),
        "knbs_projection_method_documented": bool(projection.get("method")),
        "sub_county_sum_matches_county_baseline": sub_county_matches,
        "worldpop_projection_difference_within_threshold": (
            projection_pct is not None and abs(projection_pct) <= warning_threshold
        ),
        "worldpop_total_exceeds_2019_baseline": worldpop_total >= int(knbs_2019["total_population"]),
        "seeded_demo_total_lower_than_knbs_baseline": int(seeded_demo_total) < int(knbs_2019["total_population"]),
        "replacement_ward_scope_expected": len(replacement_ward_ids) == expected_ward_count,
        "seeded_population_retired_in_replacement_scope": current_seeded_population_count == 0
        and retired_seeded_population_count >= expected_ward_count,
        "seeded_density_retired_in_replacement_scope": current_seeded_density_count == 0
        and retired_seeded_density_count >= expected_ward_count,
        "density_denominator_reconciliation_recorded": bool(area_reconciliation.get("phase1_ward_area_total_km2"))
        and bool(area_reconciliation.get("knbs_2019_land_area_sq_km")),
        "density_denominator_caveat_recorded_when_needed": (
            not area_reconciliation["caveat_required"]
            or bool(area_reconciliation["density_denominator_caveat"])
        ),
    }
    return {
        "phase": "migori_knbs_worldpop_phase_4_reconciliation",
        "generated_at": timezone.now().isoformat(),
        "county": county,
        "target_year": target_year,
        "passed": all(gates.values()),
        "warning_threshold": warning_threshold,
        "gates": gates,
        "worldpop": {
            "population_total": worldpop_total,
            "import_summary_population_total": import_summary_worldpop_total,
            "db_summary": worldpop_db_summary,
            "import_run_id": import_summary.get("run", {}).get("id"),
            "release_version": import_summary.get("run", {}).get("release_version", ""),
            "source_ref": import_summary.get("run", {}).get("source_ref", ""),
            "import_summary_path": str(worldpop_import_summary_path),
            "validation_csv_sha256": import_summary.get("validation_csv_sha256", ""),
        },
        "knbs": {
            "baseline_2019": knbs_2019,
            "sub_county_2019": sub_counties,
            "projection": projection,
            "source_files": knbs_source_files,
            "download_note": (
                "Initial local acquisition used TLS verification disabled because the KNBS file host "
                "presented an expired certificate to curl on 2026-05-05."
            ),
        },
        "seeded_demo": {
            "retired_population_total": int(seeded_demo_total),
            "replacement_ward_count": len(replacement_ward_ids),
            "current_seeded_population_records": current_seeded_population_count,
            "current_seeded_density_records": current_seeded_density_count,
            "retired_seeded_population_records": retired_seeded_population_count,
            "retired_seeded_density_records": retired_seeded_density_count,
            "note": "Seeded-demo total is included only as a before/after sanity check, not as a source comparator.",
        },
        "comparisons": comparisons,
        "area_reconciliation": area_reconciliation,
        "interpretation": {
            "projection_comparison": (
                "pass"
                if gates["worldpop_projection_difference_within_threshold"]
                else "warning"
            ),
            "projection_method": projection["method"],
            "caveat": (
                "KNBS projection workbook provides 2025 and 2030 county totals but no direct 2026 county total; "
                "the 2026 comparator is linearly interpolated unless a direct KNBS 2026 county projection source is added."
            ),
        },
    }


def write_reconciliation_summary(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
