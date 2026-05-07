from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any

from django.db.models import Count
from django.utils import timezone

from risk.migori_knbs_worldpop_reconciliation import DEFAULT_RECONCILIATION_SUMMARY_PATH
from risk.migori_worldpop_population_csv import DEFAULT_SUMMARY_PATH, load_json
from risk.migori_worldpop_population_import import (
    DEFAULT_EXPECTED_WARD_COUNT,
    DEFAULT_RELEASE_VERSION,
)
from risk.models import FeatureDataset, FeatureDatasetRow
from risk.population_exposure_features import POPULATION_EXPOSURE_FEATURE_SCHEMA_VERSION


DEFAULT_FEATURE_DATASET_SUMMARY_PATH = (
    DEFAULT_SUMMARY_PATH.parent / "migori_worldpop_2026_population_feature_dataset.json"
)
DEFAULT_COUNTY = "Migori"


def _latest_population_exposure_dataset(*, release_version: str) -> FeatureDataset:
    dataset = (
        FeatureDataset.objects.filter(
            schema_version=POPULATION_EXPOSURE_FEATURE_SCHEMA_VERSION,
            lineage_metadata__release_version_filter=release_version,
        )
        .order_by("-created_at", "-id")
        .first()
    )
    if dataset is None:
        raise ValueError(f"No population/exposure feature dataset found for release '{release_version}'.")
    return dataset


def _dataset_for_ref(dataset_ref: str | None, *, release_version: str) -> FeatureDataset:
    if dataset_ref:
        return FeatureDataset.objects.get(dataset_ref=dataset_ref)
    return _latest_population_exposure_dataset(release_version=release_version)


def _row_population_total(row: FeatureDatasetRow) -> int | None:
    value = (row.feature_values or {}).get("population_total")
    return int(value) if value is not None else None


def _row_population_density(row: FeatureDatasetRow) -> float | None:
    value = (row.feature_values or {}).get("population_density")
    return float(value) if value is not None else None


def _row_release_versions(row: FeatureDatasetRow) -> set[str]:
    return set(((row.feature_values or {}).get("source_lineage") or {}).get("release_versions") or [])


def _row_source_refs(row: FeatureDatasetRow) -> set[str]:
    return set(((row.feature_values or {}).get("source_lineage") or {}).get("source_refs") or [])


def _row_polygon_hashes(row: FeatureDatasetRow) -> set[str]:
    return set(((row.feature_values or {}).get("source_lineage") or {}).get("polygon_sha256_values") or [])


def _count_rows_by_county(rows: list[FeatureDatasetRow]) -> list[dict[str, Any]]:
    return list(
        FeatureDatasetRow.objects.filter(id__in=[row.id for row in rows])
        .values("ward__county")
        .annotate(count=Count("id"))
        .order_by("ward__county")
    )


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
    dataset_rows: list[FeatureDatasetRow],
    density_tolerance: float = 0.0005,
) -> dict[str, Any]:
    rows_by_ward_code = {
        row.ward.ward_code: row
        for row in dataset_rows
        if row.ward and row.ward.ward_code
    }
    population_mismatches = []
    density_mismatches = []
    missing_dataset_ward_codes = []

    for ward_code, expected in expected_rows.items():
        row = rows_by_ward_code.get(ward_code)
        if row is None:
            missing_dataset_ward_codes.append(ward_code)
            continue
        values = row.feature_values or {}
        expected_population = int(float(str(expected.get("population_total") or "0").replace(",", "")))
        expected_density = float(str(expected.get("population_density") or "0").replace(",", ""))
        actual_population = values.get("population_total")
        actual_density = values.get("population_density")
        if actual_population != expected_population:
            population_mismatches.append(
                {
                    "ward_code": ward_code,
                    "expected_population_total": expected_population,
                    "actual_population_total": actual_population,
                }
            )
        if actual_density is None or not math.isclose(
            float(actual_density),
            expected_density,
            rel_tol=0.0,
            abs_tol=density_tolerance,
        ):
            density_mismatches.append(
                {
                    "ward_code": ward_code,
                    "expected_population_density": expected_density,
                    "actual_population_density": actual_density,
                }
            )

    return {
        "expected_csv_row_count": len(expected_rows),
        "dataset_row_count_with_ward_codes": len(rows_by_ward_code),
        "population_mismatch_count": len(population_mismatches),
        "density_mismatch_count": len(density_mismatches),
        "missing_dataset_ward_codes": sorted(missing_dataset_ward_codes),
        "unexpected_dataset_ward_codes": sorted(set(rows_by_ward_code) - set(expected_rows)),
        "population_mismatches": population_mismatches[:25],
        "density_mismatches": density_mismatches[:25],
        "density_tolerance": density_tolerance,
    }


def build_migori_worldpop_phase5_feature_dataset_summary(
    *,
    dataset_ref: str | None = None,
    release_version: str = DEFAULT_RELEASE_VERSION,
    phase1_summary_path: Path = DEFAULT_SUMMARY_PATH,
    reconciliation_summary_path: Path = DEFAULT_RECONCILIATION_SUMMARY_PATH,
    expected_ward_count: int = DEFAULT_EXPECTED_WARD_COUNT,
    county: str = DEFAULT_COUNTY,
) -> dict[str, Any]:
    dataset = _dataset_for_ref(dataset_ref, release_version=release_version)
    rows = list(FeatureDatasetRow.objects.filter(dataset=dataset).select_related("ward").order_by("ward_name_snapshot"))
    lineage = dataset.lineage_metadata or {}
    coverage = lineage.get("coverage") or {}
    source_lineage = lineage.get("source_lineage") or {}
    phase1_summary = load_json(phase1_summary_path) if phase1_summary_path.exists() else {}
    reconciliation_summary = load_json(reconciliation_summary_path) if reconciliation_summary_path.exists() else {}

    population_totals = [value for row in rows if (value := _row_population_total(row)) is not None]
    population_densities = [value for row in rows if (value := _row_population_density(row)) is not None]
    expected_source_ref = phase1_summary.get("source_ref", "")
    expected_polygon_sha256 = phase1_summary.get("geojson_sha256", "")
    expected_population_total = int(phase1_summary.get("population_total_rounded") or 0)
    phase1_rows = _phase1_rows_by_ward_code(phase1_summary)
    reconciliation_worldpop = reconciliation_summary.get("worldpop") or {}
    row_release_matches = all(_row_release_versions(row) == {release_version} for row in rows)
    row_source_ref_matches = all(expected_source_ref in _row_source_refs(row) for row in rows)
    row_polygon_hash_matches = all(expected_polygon_sha256 in _row_polygon_hashes(row) for row in rows)
    row_count_by_county = _count_rows_by_county(rows)
    phase1_row_values = _phase1_row_value_comparison(expected_rows=phase1_rows, dataset_rows=rows)

    exposure_counts = coverage.get("exposure_record_counts_by_type") or {}
    source_kind_counts = source_lineage.get("source_kind_counts") or {}
    truth_class_counts = source_lineage.get("truth_class_counts") or {}
    freshness_state_counts = source_lineage.get("freshness_state_counts") or {}
    source_refs = source_lineage.get("source_refs") or []
    polygon_sha256_values = source_lineage.get("polygon_sha256_values") or []

    gates = {
        "phase1_summary_passed": phase1_summary.get("passed") is True,
        "reconciliation_passed": reconciliation_summary.get("passed") is True,
        "reconciliation_population_total_matches_dataset": reconciliation_worldpop.get("population_total")
        == sum(population_totals),
        "reconciliation_source_ref_matches_phase1": bool(expected_source_ref)
        and reconciliation_worldpop.get("source_ref") == expected_source_ref,
        "reconciliation_release_version_matches": reconciliation_worldpop.get("release_version") == release_version,
        "schema_version_expected": dataset.schema_version == POPULATION_EXPOSURE_FEATURE_SCHEMA_VERSION,
        "release_filter_matches": lineage.get("release_version_filter") == release_version,
        "dataset_row_count_expected": dataset.row_count == expected_ward_count,
        "persisted_row_count_expected": len(rows) == expected_ward_count,
        "phase1_csv_rows_available": len(phase1_rows) == expected_ward_count,
        "persisted_rows_scoped_to_county": row_count_by_county == [
            {"ward__county": county, "count": expected_ward_count}
        ],
        "coverage_ward_count_expected": coverage.get("ward_count") == expected_ward_count,
        "population_baseline_coverage_expected": coverage.get("wards_with_population_baseline") == expected_ward_count,
        "population_density_coverage_expected": exposure_counts.get("population_density") == expected_ward_count,
        "row_population_total_complete": len(population_totals) == expected_ward_count,
        "row_population_density_complete": len(population_densities) == expected_ward_count,
        "population_total_matches_phase1": sum(population_totals) == expected_population_total,
        "row_population_totals_match_phase1": phase1_row_values["population_mismatch_count"] == 0
        and not phase1_row_values["missing_dataset_ward_codes"],
        "row_population_densities_match_phase1": phase1_row_values["density_mismatch_count"] == 0
        and not phase1_row_values["missing_dataset_ward_codes"],
        "row_ward_codes_match_phase1": not phase1_row_values["unexpected_dataset_ward_codes"],
        "dataset_source_kind_live": dataset.source_kind == FeatureDataset.SOURCE_KIND_LIVE,
        "source_lineage_release_matches": source_lineage.get("release_versions") == [release_version],
        "source_lineage_source_ref_matches": expected_source_ref in source_refs,
        "source_lineage_polygon_hash_matches_phase1": expected_polygon_sha256 in polygon_sha256_values,
        "source_lineage_all_live": source_kind_counts == {"live": expected_ward_count * 2},
        "source_lineage_all_spatially_aggregated": truth_class_counts == {
            "spatially_aggregated_source": expected_ward_count * 2
        },
        "source_lineage_all_fresh": freshness_state_counts == {"fresh": expected_ward_count * 2},
        "row_lineage_release_matches": row_release_matches,
        "row_lineage_source_ref_matches": bool(expected_source_ref) and row_source_ref_matches,
        "row_lineage_polygon_hash_matches_phase1": bool(expected_polygon_sha256) and row_polygon_hash_matches,
        "no_seeded_lineage": not truth_class_counts.get("seeded_demo") and not source_kind_counts.get("seeded"),
    }

    return {
        "phase": "migori_knbs_worldpop_phase_5_feature_dataset",
        "generated_at": timezone.now().isoformat(),
        "passed": all(gates.values()),
        "phase5_gates": gates,
        "dataset": {
            "id": dataset.id,
            "dataset_ref": dataset.dataset_ref,
            "schema_version": dataset.schema_version,
            "source_kind": dataset.source_kind,
            "dataset_kind": dataset.dataset_kind,
            "month": dataset.month,
            "row_count": dataset.row_count,
            "created_at": dataset.created_at.isoformat() if dataset.created_at else None,
            "feature_keys": dataset.feature_keys,
        },
        "coverage": coverage,
        "lineage": {
            "release_version_filter": lineage.get("release_version_filter", ""),
            "snapshot_as_of": lineage.get("snapshot_as_of", ""),
            "source_lineage": source_lineage,
        },
        "rows": {
            "persisted_row_count": len(rows),
            "row_count_by_county": row_count_by_county,
            "population_total_sum": sum(population_totals),
            "population_density_min": min(population_densities) if population_densities else None,
            "population_density_max": max(population_densities) if population_densities else None,
            "rows_with_population_total": len(population_totals),
            "rows_with_population_density": len(population_densities),
            "rows_with_matching_release_lineage": sum(1 for row in rows if _row_release_versions(row) == {release_version}),
            "rows_with_matching_source_ref_lineage": sum(1 for row in rows if expected_source_ref in _row_source_refs(row)),
            "rows_with_matching_polygon_hash_lineage": sum(
                1 for row in rows if expected_polygon_sha256 in _row_polygon_hashes(row)
            ),
            "phase1_row_value_comparison": phase1_row_values,
        },
        "phase1_summary_path": str(phase1_summary_path),
        "reconciliation_summary_path": str(reconciliation_summary_path),
    }


def write_feature_dataset_summary(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
