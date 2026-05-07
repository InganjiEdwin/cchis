from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any

from django.db.models import Count, Sum
from django.utils import timezone

from risk.migori_worldpop_population_csv import (
    AGGREGATION_METHOD,
    DEFAULT_SUMMARY_PATH,
    POPULATION_DENSITY_UNIT,
    SPATIAL_RESOLUTION,
    load_json,
)
from risk.migori_worldpop_population_validation import DEFAULT_VALIDATION_SUMMARY_PATH
from risk.models import (
    ExposureFeatureRecord,
    PopulationBaselineRecord,
    PopulationExposureFreshness,
    PopulationExposureIngestionRun,
    PopulationExposureSource,
    PopulationExposureSourceKind,
    PopulationExposureTruth,
)


DEFAULT_IMPORT_SUMMARY_PATH = DEFAULT_SUMMARY_PATH.parent / "migori_worldpop_2026_population_import.json"
DEFAULT_SOURCE_NAME = "WorldPop R2025A constrained 100m Migori ward aggregate"
DEFAULT_RELEASE_VERSION = "WorldPop G2_CN_POP_R25A_100m KEN 2026 v1"
DEFAULT_SOURCE_TYPE = PopulationExposureSource.SOURCE_TYPE_GRIDDED_POPULATION
DEFAULT_EXPECTED_WARD_COUNT = 40
DEFAULT_COUNTY = "Migori"


def _run_for_import(run_id: int | None = None) -> PopulationExposureIngestionRun:
    queryset = PopulationExposureIngestionRun.objects.filter(
        source_name=DEFAULT_SOURCE_NAME,
        source_type=DEFAULT_SOURCE_TYPE,
        release_version=DEFAULT_RELEASE_VERSION,
    )
    if run_id is not None:
        queryset = queryset.filter(id=run_id).order_by("-id")
    else:
        queryset = queryset.filter(status=PopulationExposureIngestionRun.STATUS_SUCCESS).order_by(
            "-started_at",
            "-id",
        )
    run = queryset.first()
    if run is None:
        label = f"run_id={run_id}" if run_id is not None else DEFAULT_SOURCE_NAME
        raise ValueError(f"No Migori WorldPop population ingestion run found for {label}.")
    return run


def _counts_by_fields(queryset, *fields: str) -> list[dict[str, Any]]:
    return list(queryset.values(*fields).annotate(count=Count("id")).order_by(*fields))


def _local_date(value) -> str:
    if value is None:
        return ""
    return timezone.localtime(value).date().isoformat()


def _phase1_rows_by_ward_code(phase1_summary: dict[str, Any]) -> dict[str, dict[str, str]]:
    path_value = str(phase1_summary.get("output_csv_path") or "").strip()
    if not path_value:
        return {}
    csv_path = Path(path_value)
    if not csv_path.exists():
        return {}
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        rows = {}
        for row in csv.DictReader(handle):
            ward_code = str(row.get("ward_code") or "").strip()
            if ward_code:
                rows[ward_code] = row
        return rows


def _phase1_row_value_comparison(
    *,
    expected_rows: dict[str, dict[str, str]],
    population_qs,
    density_qs,
    density_tolerance: float = 0.0005,
) -> dict[str, Any]:
    population_by_ward_code = {
        record.ward.ward_code: record
        for record in population_qs.select_related("ward")
        if record.ward and record.ward.ward_code
    }
    density_by_ward_code = {
        record.ward.ward_code: record
        for record in density_qs.select_related("ward")
        if record.ward and record.ward.ward_code
    }
    population_mismatches = []
    density_mismatches = []
    missing_population_ward_codes = []
    missing_density_ward_codes = []

    for ward_code, row in expected_rows.items():
        population_record = population_by_ward_code.get(ward_code)
        density_record = density_by_ward_code.get(ward_code)
        expected_population = int(float(str(row.get("population_total") or "0").replace(",", "")))
        expected_density = float(str(row.get("population_density") or "0").replace(",", ""))
        if population_record is None:
            missing_population_ward_codes.append(ward_code)
        elif population_record.population_total != expected_population:
            population_mismatches.append(
                {
                    "ward_code": ward_code,
                    "expected_population_total": expected_population,
                    "actual_population_total": population_record.population_total,
                }
            )
        if density_record is None:
            missing_density_ward_codes.append(ward_code)
        elif not math.isclose(
            float(density_record.exposure_value),
            expected_density,
            rel_tol=0.0,
            abs_tol=density_tolerance,
        ):
            density_mismatches.append(
                {
                    "ward_code": ward_code,
                    "expected_population_density": expected_density,
                    "actual_population_density": density_record.exposure_value,
                }
            )

    expected_ward_codes = set(expected_rows)
    return {
        "expected_csv_row_count": len(expected_rows),
        "population_mismatch_count": len(population_mismatches),
        "density_mismatch_count": len(density_mismatches),
        "missing_population_ward_codes": sorted(missing_population_ward_codes),
        "missing_density_ward_codes": sorted(missing_density_ward_codes),
        "unexpected_population_ward_codes": sorted(set(population_by_ward_code) - expected_ward_codes),
        "unexpected_density_ward_codes": sorted(set(density_by_ward_code) - expected_ward_codes),
        "population_mismatches": population_mismatches[:25],
        "density_mismatches": density_mismatches[:25],
        "density_tolerance": density_tolerance,
    }


def build_migori_worldpop_phase3_import_summary(
    *,
    run_id: int | None = None,
    phase1_summary_path: Path = DEFAULT_SUMMARY_PATH,
    validation_summary_path: Path = DEFAULT_VALIDATION_SUMMARY_PATH,
    expected_ward_count: int = DEFAULT_EXPECTED_WARD_COUNT,
    county: str = DEFAULT_COUNTY,
) -> dict[str, Any]:
    run = _run_for_import(run_id)
    population_qs = PopulationBaselineRecord.objects.filter(ingestion_run=run)
    exposure_qs = ExposureFeatureRecord.objects.filter(ingestion_run=run)
    density_qs = exposure_qs.filter(exposure_type=ExposureFeatureRecord.EXPOSURE_POPULATION_DENSITY)
    phase1_summary = load_json(phase1_summary_path) if phase1_summary_path.exists() else {}
    validation_summary = load_json(validation_summary_path) if validation_summary_path.exists() else {}
    population_sum = population_qs.aggregate(total=Sum("population_total"))["total"] or 0
    expected_population_sum = int(phase1_summary.get("population_total_rounded") or 0)
    canonical_summary = (run.results or {}).get("canonical_summary", {})
    expected_source_ref = str(phase1_summary.get("source_ref") or "")
    expected_csv_sha256 = str(phase1_summary.get("output_csv_sha256") or "")
    expected_source_date = str(((phase1_summary.get("worldpop_record") or {}).get("source_date")) or "")
    phase1_rows = _phase1_rows_by_ward_code(phase1_summary)
    validation_csv_sha256 = str(validation_summary.get("csv_sha256") or "")
    population_ward_ids = set(population_qs.values_list("ward_id", flat=True))
    density_ward_ids = set(density_qs.values_list("ward_id", flat=True))
    population_county_counts = _counts_by_fields(population_qs, "ward__county")
    density_county_counts = _counts_by_fields(density_qs, "ward__county")
    population_source_refs = set(population_qs.values_list("source_ref", flat=True))
    density_source_refs = set(density_qs.values_list("source_ref", flat=True))
    population_release_versions = set(population_qs.values_list("release_version", flat=True))
    density_release_versions = set(density_qs.values_list("release_version", flat=True))
    density_units = set(density_qs.values_list("unit", flat=True))
    density_aggregation_methods = set(density_qs.values_list("aggregation_method", flat=True))
    density_spatial_resolutions = set(density_qs.values_list("spatial_resolution", flat=True))
    phase1_row_values = _phase1_row_value_comparison(
        expected_rows=phase1_rows,
        population_qs=population_qs,
        density_qs=density_qs,
    )

    gates = {
        "phase1_summary_passed": phase1_summary.get("passed") is True,
        "validation_passed": validation_summary.get("passed") is True,
        "validation_csv_hash_matches_phase1": bool(expected_csv_sha256)
        and validation_csv_sha256 == expected_csv_sha256,
        "run_status_success": run.status == PopulationExposureIngestionRun.STATUS_SUCCESS,
        "run_source_name_expected": run.source_name == DEFAULT_SOURCE_NAME,
        "run_source_type_expected": run.source_type == DEFAULT_SOURCE_TYPE,
        "run_release_version_expected": run.release_version == DEFAULT_RELEASE_VERSION,
        "run_source_ref_matches_phase1": bool(expected_source_ref) and run.source_ref == expected_source_ref,
        "run_source_timestamp_matches_worldpop_source_date": bool(expected_source_date)
        and _local_date(run.source_timestamp) == expected_source_date,
        "run_adapter_expected": run.adapter_key == "gridded_population_csv",
        "run_input_ref_matches_phase1_output": bool(phase1_summary.get("output_csv_path"))
        and run.input_ref == phase1_summary.get("output_csv_path"),
        "phase1_csv_rows_available": len(phase1_rows) == expected_ward_count,
        "source_rows_match_expected": run.records_seen == expected_ward_count,
        "source_rows_loaded_expected": run.records_loaded == expected_ward_count,
        "no_rejected_rows": run.records_rejected == 0,
        "population_records_match_expected": population_qs.count() == expected_ward_count,
        "density_records_match_expected": density_qs.count() == expected_ward_count,
        "population_distinct_wards_expected": len(population_ward_ids) == expected_ward_count,
        "density_distinct_wards_expected": len(density_ward_ids) == expected_ward_count,
        "population_and_density_ward_sets_match": population_ward_ids == density_ward_ids,
        "population_records_scoped_to_county": population_county_counts == [
            {"ward__county": county, "count": expected_ward_count}
        ],
        "density_records_scoped_to_county": density_county_counts == [
            {"ward__county": county, "count": expected_ward_count}
        ],
        "population_source_refs_match_phase1": bool(expected_source_ref)
        and population_source_refs == {expected_source_ref},
        "density_source_refs_match_phase1": bool(expected_source_ref)
        and density_source_refs == {expected_source_ref},
        "population_release_versions_expected": population_release_versions == {DEFAULT_RELEASE_VERSION},
        "density_release_versions_expected": density_release_versions == {DEFAULT_RELEASE_VERSION},
        "density_units_expected": density_units == {POPULATION_DENSITY_UNIT},
        "density_aggregation_methods_expected": density_aggregation_methods == {AGGREGATION_METHOD},
        "density_spatial_resolutions_expected": density_spatial_resolutions == {SPATIAL_RESOLUTION},
        "imported_population_values_match_phase1_rows": phase1_row_values["population_mismatch_count"] == 0
        and not phase1_row_values["missing_population_ward_codes"],
        "imported_density_values_match_phase1_rows": phase1_row_values["density_mismatch_count"] == 0
        and not phase1_row_values["missing_density_ward_codes"],
        "imported_ward_codes_match_phase1_rows": not phase1_row_values["unexpected_population_ward_codes"]
        and not phase1_row_values["unexpected_density_ward_codes"],
        "canonical_records_total_expected": canonical_summary.get("canonical_records_total") == expected_ward_count * 2,
        "population_sum_matches_phase1": population_sum == expected_population_sum,
        "population_truth_is_spatially_aggregated": not population_qs.exclude(
            truth_class=PopulationExposureTruth.SPATIALLY_AGGREGATED_SOURCE
        ).exists(),
        "density_truth_is_spatially_aggregated": not density_qs.exclude(
            truth_class=PopulationExposureTruth.SPATIALLY_AGGREGATED_SOURCE
        ).exists(),
        "population_source_kind_live": not population_qs.exclude(source_kind=PopulationExposureSourceKind.LIVE).exists(),
        "density_source_kind_live": not density_qs.exclude(source_kind=PopulationExposureSourceKind.LIVE).exists(),
        "population_freshness_fresh": not population_qs.exclude(freshness_state=PopulationExposureFreshness.FRESH).exists(),
        "density_freshness_fresh": not density_qs.exclude(freshness_state=PopulationExposureFreshness.FRESH).exists(),
        "no_seeded_demo_records": not population_qs.filter(truth_class=PopulationExposureTruth.SEEDED_DEMO).exists()
        and not exposure_qs.filter(truth_class=PopulationExposureTruth.SEEDED_DEMO).exists(),
    }

    return {
        "phase": "migori_knbs_worldpop_phase_3_import",
        "generated_at": timezone.now().isoformat(),
        "passed": all(gates.values()),
        "phase3_gates": gates,
        "run": {
            "id": run.id,
            "status": run.status,
            "source_name": run.source_name,
            "source_type": run.source_type,
            "source_timestamp": run.source_timestamp.isoformat() if run.source_timestamp else None,
            "release_version": run.release_version,
            "source_ref": run.source_ref,
            "adapter_key": run.adapter_key,
            "input_ref": run.input_ref,
            "execution_mode": run.execution_mode,
            "correction_mode": run.correction_mode,
            "fallback_used": run.fallback_used,
            "records_seen": run.records_seen,
            "records_loaded": run.records_loaded,
            "records_rejected": run.records_rejected,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "canonical_summary": canonical_summary,
            "error_summary": run.error_summary,
        },
        "records": {
            "population_baseline_records": population_qs.count(),
            "density_exposure_records": density_qs.count(),
            "all_exposure_records_for_run": exposure_qs.count(),
            "population_total_sum": population_sum,
            "expected_population_total_sum": expected_population_sum,
            "population_distinct_ward_count": len(population_ward_ids),
            "density_distinct_ward_count": len(density_ward_ids),
            "population_county_counts": population_county_counts,
            "density_county_counts": density_county_counts,
            "population_source_refs": sorted(population_source_refs),
            "density_source_refs": sorted(density_source_refs),
            "population_release_versions": sorted(population_release_versions),
            "density_release_versions": sorted(density_release_versions),
            "density_units": sorted(density_units),
            "density_aggregation_methods": sorted(density_aggregation_methods),
            "density_spatial_resolutions": sorted(density_spatial_resolutions),
            "phase1_row_value_comparison": phase1_row_values,
            "population_by_truth_source_freshness": _counts_by_fields(
                population_qs,
                "truth_class",
                "source_kind",
                "freshness_state",
            ),
            "exposure_by_truth_source_freshness_type": _counts_by_fields(
                exposure_qs,
                "truth_class",
                "source_kind",
                "freshness_state",
                "exposure_type",
            ),
        },
        "phase1_summary_path": str(phase1_summary_path),
        "validation_summary_path": str(validation_summary_path),
        "validation_csv_sha256": validation_csv_sha256,
    }


def write_import_summary(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
