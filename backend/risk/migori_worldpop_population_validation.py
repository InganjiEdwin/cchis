from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from django.utils import timezone

from risk.migori_population_source_inventory import EXPECTED_WORLDPOP_FILE_URL
from risk.migori_worldpop_population_csv import (
    AGGREGATION_METHOD,
    DEFAULT_OUTPUT_CSV_PATH,
    DEFAULT_SUMMARY_PATH,
    POPULATION_DENSITY_UNIT,
    SPATIAL_RESOLUTION,
    file_sha256,
    load_json,
)
from risk.models import Ward
from risk.population_exposure_ingestion import inspect_population_exposure_csv


DEFAULT_VALIDATION_SUMMARY_PATH = (
    DEFAULT_OUTPUT_CSV_PATH.parent / "migori_worldpop_2026_population_validation.json"
)
DEFAULT_EXPECTED_ROW_COUNT = 40
FORMULA_PREFIXES = ("=", "+", "-", "@")
EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
KENYA_PHONE_PATTERN = re.compile(r"(?:\+?254|0)7\d{8}\b")
DEFAULT_COUNTY = "Migori"


def _cell_values(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _formula_like_cells(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    formula_cells = []
    for row_index, row in enumerate(rows, start=2):
        for column, raw_value in row.items():
            value = str(raw_value or "").lstrip()
            if value.startswith(FORMULA_PREFIXES):
                formula_cells.append(
                    {
                        "row_number": row_index,
                        "column": column,
                        "prefix": value[:1],
                    }
                )
    return formula_cells


def _pii_like_cells(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    pii_cells = []
    for row_index, row in enumerate(rows, start=2):
        for column, raw_value in row.items():
            value = str(raw_value or "")
            matched_patterns = []
            if EMAIL_PATTERN.search(value):
                matched_patterns.append("email")
            if KENYA_PHONE_PATTERN.search(value):
                matched_patterns.append("kenya_phone")
            if matched_patterns:
                pii_cells.append(
                    {
                        "row_number": row_index,
                        "column": column,
                        "patterns": matched_patterns,
                    }
                )
    return pii_cells


def _normalized_name(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _ward_resolution_summary(rows: list[dict[str, str]], *, county: str) -> dict[str, Any]:
    wards = list(Ward.objects.filter(county__iexact=county, is_active=True).values("name", "ward_code"))
    by_code = {str(ward["ward_code"]).strip().upper(): ward for ward in wards if str(ward["ward_code"]).strip()}
    by_name = {_normalized_name(str(ward["name"])): ward for ward in wards}
    unresolved_rows = []
    duplicate_ward_codes: list[str] = []
    seen_codes: set[str] = set()
    resolved_codes: set[str] = set()

    for row_index, row in enumerate(rows, start=2):
        raw_code = str(row.get("ward_code") or "").strip()
        raw_name = str(row.get("ward_name") or "").strip()
        ward = by_code.get(raw_code.upper()) if raw_code else None
        if ward is None and raw_name:
            ward = by_name.get(_normalized_name(raw_name))
        if ward is None:
            unresolved_rows.append(
                {
                    "row_number": row_index,
                    "ward_code": raw_code,
                    "ward_name": raw_name,
                    "reason": "ward_not_found",
                }
            )
            continue

        resolved_code = str(ward["ward_code"]).strip()
        if resolved_code in seen_codes and resolved_code not in duplicate_ward_codes:
            duplicate_ward_codes.append(resolved_code)
        seen_codes.add(resolved_code)
        resolved_codes.add(resolved_code)

    missing_expected_ward_codes = sorted(set(by_code) - {code.upper() for code in resolved_codes})
    return {
        "county": county,
        "expected_active_ward_count": len(wards),
        "resolved_row_count": len(rows) - len(unresolved_rows),
        "resolved_distinct_ward_count": len(resolved_codes),
        "unresolved_rows": unresolved_rows,
        "duplicate_ward_codes": sorted(duplicate_ward_codes),
        "missing_expected_ward_codes": missing_expected_ward_codes,
    }


def _row_contract_summary(rows: list[dict[str, str]], *, expected_source_ref: str) -> dict[str, Any]:
    def mismatches(column: str, expected_value: str) -> list[dict[str, Any]]:
        failed = []
        for row_index, row in enumerate(rows, start=2):
            value = str(row.get(column) or "").strip()
            if value != expected_value:
                failed.append(
                    {
                        "row_number": row_index,
                        "column": column,
                        "expected": expected_value,
                        "actual": value,
                    }
                )
        return failed

    checks = {
        "source_ref": mismatches("source_ref", expected_source_ref),
        "truth_class": mismatches("truth_class", "spatially_aggregated_source"),
        "source_kind": mismatches("source_kind", "live"),
        "freshness_state": mismatches("freshness_state", "fresh"),
        "aggregation_method": mismatches("aggregation_method", AGGREGATION_METHOD),
        "spatial_resolution": mismatches("spatial_resolution", SPATIAL_RESOLUTION),
        "unit": mismatches("unit", POPULATION_DENSITY_UNIT),
    }
    return {
        "expected_source_ref": expected_source_ref,
        "expected_truth_class": "spatially_aggregated_source",
        "expected_source_kind": "live",
        "expected_freshness_state": "fresh",
        "expected_aggregation_method": AGGREGATION_METHOD,
        "expected_spatial_resolution": SPATIAL_RESOLUTION,
        "expected_unit": POPULATION_DENSITY_UNIT,
        "mismatches": checks,
        "mismatch_count": sum(len(items) for items in checks.values()),
    }


def _parse_float_cell(value: str) -> float | None:
    try:
        return float(str(value or "").replace(",", "").strip())
    except ValueError:
        return None


def _numeric_contract_summary(rows: list[dict[str, str]]) -> dict[str, Any]:
    missing_or_invalid = []
    population_rounding_mismatches = []
    positive_value_failures = []
    for row_index, row in enumerate(rows, start=2):
        parsed = {
            "population_total": _parse_float_cell(row.get("population_total", "")),
            "population_density": _parse_float_cell(row.get("population_density", "")),
            "gridded_population_value": _parse_float_cell(row.get("gridded_population_value", "")),
        }
        for column, value in parsed.items():
            if value is None:
                missing_or_invalid.append(
                    {
                        "row_number": row_index,
                        "column": column,
                    }
                )
            elif column == "population_total" and not value.is_integer():
                missing_or_invalid.append(
                    {
                        "row_number": row_index,
                        "column": column,
                        "value": value,
                        "reason": "population_total_must_be_an_integer",
                    }
                )
            elif value <= 0:
                positive_value_failures.append(
                    {
                        "row_number": row_index,
                        "column": column,
                        "value": value,
                    }
                )

        population_total = parsed["population_total"]
        gridded_value = parsed["gridded_population_value"]
        if (
            population_total is not None
            and gridded_value is not None
            and int(round(gridded_value)) != int(population_total)
        ):
            population_rounding_mismatches.append(
                {
                    "row_number": row_index,
                    "expected_population_total": int(round(gridded_value)),
                    "actual_population_total": int(population_total),
                    "gridded_population_value": gridded_value,
                }
            )

    return {
        "missing_or_invalid_numeric_cells": missing_or_invalid,
        "positive_value_failures": positive_value_failures,
        "population_rounding_mismatches": population_rounding_mismatches,
        "missing_or_invalid_numeric_cell_count": len(missing_or_invalid),
        "positive_value_failure_count": len(positive_value_failures),
        "population_rounding_mismatch_count": len(population_rounding_mismatches),
    }


def _phase1_csv_hash_matches(csv_path: Path, phase1_summary_path: Path | None) -> bool | None:
    if phase1_summary_path is None or not phase1_summary_path.exists():
        return None
    phase1_summary = load_json(phase1_summary_path)
    expected_sha = str(phase1_summary.get("output_csv_sha256") or "")
    return bool(expected_sha) and expected_sha == file_sha256(csv_path)


def build_migori_worldpop_phase2_validation(
    *,
    csv_path: Path = DEFAULT_OUTPUT_CSV_PATH,
    phase1_summary_path: Path | None = DEFAULT_SUMMARY_PATH,
    source_type: str = "gridded_population",
    expected_row_count: int = DEFAULT_EXPECTED_ROW_COUNT,
    county: str = DEFAULT_COUNTY,
) -> dict[str, Any]:
    csv_path = csv_path.expanduser().resolve()
    inspection = inspect_population_exposure_csv(csv_path, source_type=source_type)
    rows = _cell_values(csv_path)
    formula_cells = _formula_like_cells(rows)
    pii_cells = _pii_like_cells(rows)
    ward_resolution = _ward_resolution_summary(rows, county=county)
    phase1_hash_matches = _phase1_csv_hash_matches(
        csv_path,
        phase1_summary_path.expanduser().resolve() if phase1_summary_path else None,
    )
    phase1_summary = load_json(phase1_summary_path) if phase1_summary_path and phase1_summary_path.exists() else {}
    expected_source_ref = str(phase1_summary.get("source_ref") or EXPECTED_WORLDPOP_FILE_URL)
    row_contract = _row_contract_summary(rows, expected_source_ref=expected_source_ref)
    numeric_contract = _numeric_contract_summary(rows)

    gates = {
        "phase1_summary_passed": phase1_summary.get("passed") is True,
        "source_rows_match_expected": inspection["records_seen"] == expected_row_count,
        "accepted_rows_match_expected": inspection["records_loaded"] == expected_row_count,
        "no_rejected_rows": inspection["records_rejected"] == 0,
        "no_unknown_columns": not inspection["unknown_columns"],
        "no_formula_like_cells": not formula_cells,
        "no_pii_like_cells": not pii_cells,
        "all_rows_resolve_to_migori_wards": not ward_resolution["unresolved_rows"],
        "resolved_distinct_wards_match_expected": ward_resolution["resolved_distinct_ward_count"]
        == expected_row_count,
        "no_duplicate_ward_codes": not ward_resolution["duplicate_ward_codes"],
        "no_missing_expected_ward_codes": not ward_resolution["missing_expected_ward_codes"],
        "row_source_refs_match_phase1": not row_contract["mismatches"]["source_ref"],
        "row_truth_classes_expected": not row_contract["mismatches"]["truth_class"],
        "row_source_kinds_expected": not row_contract["mismatches"]["source_kind"],
        "row_freshness_states_expected": not row_contract["mismatches"]["freshness_state"],
        "row_aggregation_methods_expected": not row_contract["mismatches"]["aggregation_method"],
        "row_spatial_resolutions_expected": not row_contract["mismatches"]["spatial_resolution"],
        "row_units_expected": not row_contract["mismatches"]["unit"],
        "row_numeric_cells_present_and_valid": numeric_contract["missing_or_invalid_numeric_cell_count"] == 0,
        "row_numeric_values_positive": numeric_contract["positive_value_failure_count"] == 0,
        "row_population_totals_round_gridded_values": numeric_contract["population_rounding_mismatch_count"] == 0,
        "phase1_csv_hash_matches": phase1_hash_matches is True,
    }
    if phase1_hash_matches is None:
        gates["phase1_csv_hash_matches"] = False

    return {
        "phase": "migori_knbs_worldpop_phase_2_dry_validation",
        "generated_at": timezone.now().isoformat(),
        "csv_path": str(csv_path),
        "csv_sha256": file_sha256(csv_path),
        "source_type": source_type,
        "expected_row_count": expected_row_count,
        "inspection": {
            key: value
            for key, value in inspection.items()
            if key not in {"sample_rows"}
        },
        "sample_rows": inspection.get("sample_rows", []),
        "formula_like_cells": formula_cells,
        "pii_like_cells": pii_cells,
        "ward_resolution": ward_resolution,
        "row_contract": row_contract,
        "numeric_contract": numeric_contract,
        "phase1_summary_path": str(phase1_summary_path) if phase1_summary_path else "",
        "phase2_gates": gates,
        "passed": all(gates.values()),
    }


def write_validation_summary(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
