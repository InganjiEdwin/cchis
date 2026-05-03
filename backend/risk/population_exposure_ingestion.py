from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from django.db import transaction
from django.utils import timezone

from risk.models import (
    CatchmentPopulationRecord,
    ExposureFeatureRecord,
    HealthFacility,
    PopulationBaselineRecord,
    PopulationExposureFreshness,
    PopulationExposureIngestionRun,
    PopulationExposureSource,
    PopulationExposureSourceKind,
    PopulationExposureTruth,
    Ward,
)


MAX_REJECTED_ROW_DETAILS = 25
MAX_SAMPLE_ROWS = 5


def _columns(*names: str) -> frozenset[str]:
    return frozenset(names)


WARD_KEY_COLUMNS = _columns("ward_id", "ward_code", "ward_name")
FACILITY_KEY_COLUMNS = _columns("facility_id", "facility_code", "facility_name")
GEOMETRY_KEY_COLUMNS = _columns("geometry_ref", "geometry_id", "grid_cell_id", "feature_id")


@dataclass(frozen=True)
class PopulationExposureAdapterSpec:
    source_type: str
    adapter_key: str
    required_any_columns: tuple[frozenset[str], ...]
    accepted_columns: frozenset[str]
    scheduled_supported: bool
    notes: str


BASE_ACCEPTED_COLUMNS = _columns(
    "ward_id",
    "ward_code",
    "ward_name",
    "facility_id",
    "facility_code",
    "facility_name",
    "geometry_ref",
    "geometry_id",
    "grid_cell_id",
    "feature_id",
    "source_name",
    "source_type",
    "source_timestamp",
    "release_version",
    "source_ref",
    "operator_note",
    "recorded_at",
    "source_kind",
    "truth_class",
    "freshness_state",
    "supersedes_record_ref",
    "revision_number",
    "notes",
    "unit",
    "aggregation_method",
    "spatial_resolution",
)


POPULATION_EXPOSURE_ADAPTERS: dict[str, PopulationExposureAdapterSpec] = {
    PopulationExposureSource.SOURCE_TYPE_POPULATION_BASELINE: PopulationExposureAdapterSpec(
        source_type=PopulationExposureSource.SOURCE_TYPE_POPULATION_BASELINE,
        adapter_key="population_baseline_csv",
        required_any_columns=(
            WARD_KEY_COLUMNS,
            _columns("population_total", "total_population", "population"),
        ),
        accepted_columns=BASE_ACCEPTED_COLUMNS
        | _columns(
            "population_total",
            "total_population",
            "population",
            "population_under_five",
            "under_five",
            "household_count_proxy",
            "households",
        ),
        scheduled_supported=False,
        notes="Manual release import for ward population baselines.",
    ),
    PopulationExposureSource.SOURCE_TYPE_GRIDDED_POPULATION: PopulationExposureAdapterSpec(
        source_type=PopulationExposureSource.SOURCE_TYPE_GRIDDED_POPULATION,
        adapter_key="gridded_population_csv",
        required_any_columns=(
            WARD_KEY_COLUMNS | GEOMETRY_KEY_COLUMNS,
            _columns("population_total", "population_density", "gridded_population_value", "population"),
        ),
        accepted_columns=BASE_ACCEPTED_COLUMNS
        | _columns("population_total", "population_density", "population_density_proxy", "gridded_population_value"),
        scheduled_supported=True,
        notes="File-backed gridded population extract after external download or aggregation.",
    ),
    PopulationExposureSource.SOURCE_TYPE_SETTLEMENT_LAYER: PopulationExposureAdapterSpec(
        source_type=PopulationExposureSource.SOURCE_TYPE_SETTLEMENT_LAYER,
        adapter_key="settlement_layer_csv",
        required_any_columns=(
            WARD_KEY_COLUMNS | GEOMETRY_KEY_COLUMNS,
            _columns("settlement_concentration", "settlement_concentration_proxy", "built_up_area", "settlement_count"),
        ),
        accepted_columns=BASE_ACCEPTED_COLUMNS
        | _columns("settlement_concentration", "settlement_concentration_proxy", "built_up_area", "settlement_count"),
        scheduled_supported=True,
        notes="Settlement or built-up-area layer extract with explicit aggregation method.",
    ),
    PopulationExposureSource.SOURCE_TYPE_WASH_VULNERABILITY_LAYER: PopulationExposureAdapterSpec(
        source_type=PopulationExposureSource.SOURCE_TYPE_WASH_VULNERABILITY_LAYER,
        adapter_key="wash_vulnerability_csv",
        required_any_columns=(
            WARD_KEY_COLUMNS | GEOMETRY_KEY_COLUMNS,
            _columns("wash_vulnerability", "sanitation_vulnerability", "water_access_vulnerability", "vulnerability_score"),
        ),
        accepted_columns=BASE_ACCEPTED_COLUMNS
        | _columns("wash_vulnerability", "sanitation_vulnerability", "water_access_vulnerability", "vulnerability_score"),
        scheduled_supported=True,
        notes="WASH vulnerability context; often coarse and proxy-classed until local layers exist.",
    ),
    PopulationExposureSource.SOURCE_TYPE_WATER_BODY_DISTANCE_LAYER: PopulationExposureAdapterSpec(
        source_type=PopulationExposureSource.SOURCE_TYPE_WATER_BODY_DISTANCE_LAYER,
        adapter_key="water_body_distance_csv",
        required_any_columns=(
            WARD_KEY_COLUMNS | GEOMETRY_KEY_COLUMNS,
            _columns("water_body_distance", "distance_to_water", "water_body_proximity"),
        ),
        accepted_columns=BASE_ACCEPTED_COLUMNS
        | _columns("water_body_distance", "distance_to_water", "water_body_proximity"),
        scheduled_supported=True,
        notes="Water proximity layer with a named distance or aggregation method.",
    ),
    PopulationExposureSource.SOURCE_TYPE_FLOOD_EXPOSURE_LAYER: PopulationExposureAdapterSpec(
        source_type=PopulationExposureSource.SOURCE_TYPE_FLOOD_EXPOSURE_LAYER,
        adapter_key="flood_exposure_csv",
        required_any_columns=(
            WARD_KEY_COLUMNS | GEOMETRY_KEY_COLUMNS,
            _columns("floodplain_exposure", "flood_exposure", "flood_risk", "exposed_population_proxy"),
        ),
        accepted_columns=BASE_ACCEPTED_COLUMNS
        | _columns("floodplain_exposure", "flood_exposure", "flood_risk", "exposed_population_proxy"),
        scheduled_supported=True,
        notes="Flood exposure layer or proxy extract; never treated as direct population truth.",
    ),
    PopulationExposureSource.SOURCE_TYPE_CATCHMENT_MAPPING: PopulationExposureAdapterSpec(
        source_type=PopulationExposureSource.SOURCE_TYPE_CATCHMENT_MAPPING,
        adapter_key="catchment_mapping_csv",
        required_any_columns=(
            FACILITY_KEY_COLUMNS,
            _columns("catchment_population", "catchment_population_estimate"),
        ),
        accepted_columns=BASE_ACCEPTED_COLUMNS
        | _columns("assigned_ward_ids", "assignment_method", "catchment_population", "catchment_population_estimate", "catchment_under_five_estimate"),
        scheduled_supported=False,
        notes="Manual or file-backed catchment assignment approximation.",
    ),
    PopulationExposureSource.SOURCE_TYPE_CSV_BACKFILL: PopulationExposureAdapterSpec(
        source_type=PopulationExposureSource.SOURCE_TYPE_CSV_BACKFILL,
        adapter_key="population_exposure_backfill_csv",
        required_any_columns=(WARD_KEY_COLUMNS | FACILITY_KEY_COLUMNS | GEOMETRY_KEY_COLUMNS,),
        accepted_columns=BASE_ACCEPTED_COLUMNS
        | _columns(
            "population_total",
            "total_population",
            "population",
            "population_under_five",
            "under_five",
            "household_count_proxy",
            "households",
            "population_density",
            "population_density_proxy",
            "settlement_concentration",
            "settlement_concentration_proxy",
            "floodplain_exposure",
            "flood_exposure",
            "flood_risk",
            "water_body_distance",
            "distance_to_water",
            "water_body_proximity",
            "wash_vulnerability",
            "sanitation_vulnerability",
            "water_access_vulnerability",
            "vulnerability_score",
            "exposed_population_proxy",
            "exposure_type",
            "exposure_value",
            "assigned_ward_ids",
            "assignment_method",
            "catchment_population",
            "catchment_population_estimate",
            "catchment_under_five_estimate",
        ),
        scheduled_supported=False,
        notes="Generic documented backfill envelope for legacy or correction files.",
    ),
}


def normalize_column_name(value: str | None) -> str:
    return "_".join((value or "").strip().lower().replace("-", "_").split())


def parse_source_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def adapter_spec_for_source_type(source_type: str) -> PopulationExposureAdapterSpec:
    try:
        return POPULATION_EXPOSURE_ADAPTERS[source_type]
    except KeyError as error:
        choices = ", ".join(sorted(POPULATION_EXPOSURE_ADAPTERS))
        raise ValueError(f"Unsupported population/exposure source_type '{source_type}'. Expected one of: {choices}") from error


def _has_any_value(row: dict[str, Any], columns: frozenset[str]) -> bool:
    return any(str(row.get(column, "")).strip() for column in columns)


def _normalized_csv_rows(file_path: str | Path) -> tuple[list[str], list[dict[str, Any]]]:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Population/exposure import file does not exist: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        if reader.fieldnames is None:
            return [], []
        normalized_headers = [normalize_column_name(header) for header in reader.fieldnames]
        rows = []
        for raw_row in reader:
            row = {}
            for raw_header, value in raw_row.items():
                row[normalize_column_name(raw_header)] = value
            rows.append(row)
        return normalized_headers, rows


def _validated_population_exposure_csv(file_path: str | Path, *, source_type: str) -> dict[str, Any]:
    spec = adapter_spec_for_source_type(source_type)
    headers, rows = _normalized_csv_rows(file_path)
    unknown_columns = sorted(set(headers) - set(spec.accepted_columns))

    records_seen = len(rows)
    records_loaded = 0
    accepted_rows: list[dict[str, Any]] = []
    rejected_rows: list[dict[str, Any]] = []
    sample_rows: list[dict[str, Any]] = []

    for row_number, row in enumerate(rows, start=2):
        missing_groups = [
            sorted(group)
            for group in spec.required_any_columns
            if not _has_any_value(row, group)
        ]
        if missing_groups:
            if len(rejected_rows) < MAX_REJECTED_ROW_DETAILS:
                rejected_rows.append(
                    {
                        "row_number": row_number,
                        "reason": "missing_required_column_group",
                        "required_any_columns": missing_groups,
                    }
                )
            continue

        records_loaded += 1
        accepted_rows.append({"row_number": row_number, "row": row})
        if len(sample_rows) < MAX_SAMPLE_ROWS:
            sample_rows.append({key: row.get(key) for key in headers if key in row})

    return {
        "adapter_key": spec.adapter_key,
        "adapter_notes": spec.notes,
        "scheduled_supported": spec.scheduled_supported,
        "headers": headers,
        "unknown_columns": unknown_columns,
        "records_seen": records_seen,
        "records_loaded": records_loaded,
        "records_rejected": records_seen - records_loaded,
        "accepted_rows": accepted_rows,
        "sample_rows": sample_rows,
        "rejected_rows": rejected_rows,
    }


def inspect_population_exposure_csv(file_path: str | Path, *, source_type: str) -> dict[str, Any]:
    inspection = _validated_population_exposure_csv(file_path, source_type=source_type)
    inspection.pop("accepted_rows", None)
    return inspection


def _first_nonempty(row: dict[str, Any], *columns: str) -> str:
    for column in columns:
        value = row.get(column)
        if value is None:
            continue
        text = str(value).strip()
        if text and text.lower() not in {"null", "none", "nan"}:
            return text
    return ""


def _parse_int(value: str | int | float | None) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value).replace(",", "").strip()))
    except ValueError:
        return None


def _parse_float(value: str | int | float | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None


def _normalize_choice(value: str) -> str:
    return "_".join(value.strip().lower().replace("-", "_").split())


def _recorded_at_for_row(row: dict[str, Any], run: PopulationExposureIngestionRun) -> datetime:
    value = _first_nonempty(row, "recorded_at", "source_timestamp")
    if value:
        try:
            parsed = parse_source_timestamp(value)
            if parsed is not None:
                return parsed
        except ValueError:
            pass
    return run.source_timestamp or run.started_at or timezone.now()


def _replacement_lineage_for_run(run: PopulationExposureIngestionRun) -> dict[str, Any]:
    return {
        "ingestion_run_id": run.id,
        "replay_of_run_id": run.replay_of_id,
        "replaces_run_id": run.replaces_run_id,
        "execution_mode": run.execution_mode,
        "correction_mode": run.correction_mode,
        "release_version": run.release_version,
        "source_ref": run.source_ref,
        "replacement_reason": run.replacement_reason,
    }


def _default_truth_class_for_record(*, run: PopulationExposureIngestionRun, record_kind: str) -> str:
    source_name = run.source_name.lower()
    correction_mode = run.correction_mode
    if "seed" in source_name:
        return PopulationExposureTruth.SEEDED_DEMO

    correction_or_operator_loaded = correction_mode in {
        PopulationExposureIngestionRun.CORRECTION_AMENDMENT,
        PopulationExposureIngestionRun.CORRECTION_BACKFILL,
        PopulationExposureIngestionRun.CORRECTION_RELEASE_REPLACEMENT,
    }
    if record_kind == "population":
        if run.source_type == PopulationExposureSource.SOURCE_TYPE_POPULATION_BASELINE:
            return PopulationExposureTruth.DIRECT_POPULATION_BASELINE
        if correction_or_operator_loaded or run.source_type == PopulationExposureSource.SOURCE_TYPE_CSV_BACKFILL:
            return PopulationExposureTruth.MANUAL_OVERRIDE
        return PopulationExposureTruth.SPATIALLY_AGGREGATED_SOURCE

    if record_kind == "catchment":
        if correction_or_operator_loaded:
            return PopulationExposureTruth.MANUAL_OVERRIDE
        return PopulationExposureTruth.SPATIALLY_AGGREGATED_SOURCE

    if correction_or_operator_loaded:
        return PopulationExposureTruth.MANUAL_OVERRIDE
    if run.source_type in {
        PopulationExposureSource.SOURCE_TYPE_GRIDDED_POPULATION,
        PopulationExposureSource.SOURCE_TYPE_SETTLEMENT_LAYER,
    }:
        return PopulationExposureTruth.SPATIALLY_AGGREGATED_SOURCE
    return PopulationExposureTruth.DERIVED_EXPOSURE_PROXY


def _truth_class_for_record(row: dict[str, Any], run: PopulationExposureIngestionRun, *, record_kind: str) -> str:
    supplied = _normalize_choice(_first_nonempty(row, "truth_class"))
    valid = {choice[0] for choice in PopulationExposureTruth.choices}
    if supplied in valid:
        if record_kind == "population" and supplied != PopulationExposureTruth.DERIVED_EXPOSURE_PROXY:
            return supplied
        if record_kind != "population" and supplied != PopulationExposureTruth.DIRECT_POPULATION_BASELINE:
            return supplied
    return _default_truth_class_for_record(run=run, record_kind=record_kind)


def _source_kind_for_row(row: dict[str, Any], run: PopulationExposureIngestionRun, truth_class: str) -> str:
    supplied = _normalize_choice(_first_nonempty(row, "source_kind"))
    valid = {choice[0] for choice in PopulationExposureSourceKind.choices}
    if supplied in valid:
        return supplied
    if truth_class == PopulationExposureTruth.SEEDED_DEMO or "seed" in run.source_name.lower():
        return PopulationExposureSourceKind.SEEDED
    if run.correction_mode == PopulationExposureIngestionRun.CORRECTION_BACKFILL or run.source_type == PopulationExposureSource.SOURCE_TYPE_CSV_BACKFILL:
        return PopulationExposureSourceKind.BACKFILL
    return PopulationExposureSourceKind.LIVE


def _freshness_for_row(row: dict[str, Any]) -> str:
    supplied = _normalize_choice(_first_nonempty(row, "freshness_state"))
    valid = {choice[0] for choice in PopulationExposureFreshness.choices}
    return supplied if supplied in valid else PopulationExposureFreshness.UNKNOWN


def _find_ward(row: dict[str, Any]) -> Ward | None:
    ward_id = _parse_int(_first_nonempty(row, "ward_id"))
    if ward_id is not None:
        ward = Ward.objects.filter(pk=ward_id).first()
        if ward:
            return ward

    ward_code = _first_nonempty(row, "ward_code")
    if ward_code:
        ward = Ward.objects.filter(ward_code__iexact=ward_code).order_by("county", "name").first()
        if ward:
            return ward

    ward_name = _first_nonempty(row, "ward_name")
    if ward_name:
        normalized_name = " ".join(ward_name.split())
        return Ward.objects.filter(name__iexact=normalized_name).order_by("county", "name").first()
    return None


def _find_facility(row: dict[str, Any]) -> HealthFacility | None:
    facility_id = _parse_int(_first_nonempty(row, "facility_id"))
    if facility_id is not None:
        facility = HealthFacility.objects.filter(pk=facility_id).first()
        if facility:
            return facility

    facility_code = _first_nonempty(row, "facility_code")
    if facility_code:
        facility = HealthFacility.objects.filter(facility_code__iexact=facility_code).first()
        if facility:
            return facility

    facility_name = _first_nonempty(row, "facility_name")
    if facility_name:
        normalized_name = " ".join(facility_name.split())
        return HealthFacility.objects.filter(name__iexact=normalized_name).order_by("ward__name", "name").first()
    return None


def _assigned_ward_ids(row: dict[str, Any], ward: Ward | None) -> list[int]:
    raw_ids = _first_nonempty(row, "assigned_ward_ids")
    assigned_ids = []
    for item in raw_ids.replace(";", ",").split(","):
        parsed = _parse_int(item)
        if parsed is not None:
            assigned_ids.append(parsed)
    if ward and ward.id not in assigned_ids:
        assigned_ids.append(ward.id)
    return assigned_ids


def _population_total_for_row(row: dict[str, Any]) -> int | None:
    return _parse_int(_first_nonempty(row, "population_total", "total_population", "population"))


EXPOSURE_FIELD_MAP: tuple[tuple[str, tuple[str, ...]], ...] = (
    (ExposureFeatureRecord.EXPOSURE_POPULATION_DENSITY, ("population_density", "population_density_proxy", "gridded_population_value")),
    (ExposureFeatureRecord.EXPOSURE_SETTLEMENT_CONCENTRATION, ("settlement_concentration", "settlement_concentration_proxy", "built_up_area", "settlement_count")),
    (ExposureFeatureRecord.EXPOSURE_FLOODPLAIN_EXPOSURE, ("floodplain_exposure", "flood_exposure", "flood_risk")),
    (ExposureFeatureRecord.EXPOSURE_WATER_BODY_PROXIMITY, ("water_body_proximity", "distance_to_water", "water_body_distance")),
    (ExposureFeatureRecord.EXPOSURE_WASH_VULNERABILITY, ("wash_vulnerability", "sanitation_vulnerability", "water_access_vulnerability", "vulnerability_score")),
    (ExposureFeatureRecord.EXPOSURE_EXPOSED_POPULATION_PROXY, ("exposed_population_proxy",)),
)


def _canonical_records_for_row(
    *,
    run: PopulationExposureIngestionRun,
    row_number: int,
    row: dict[str, Any],
) -> tuple[list[PopulationBaselineRecord], list[ExposureFeatureRecord], list[CatchmentPopulationRecord], list[dict[str, Any]]]:
    ward = _find_ward(row)
    facility = _find_facility(row)
    freshness_state = _freshness_for_row(row)
    recorded_at = _recorded_at_for_row(row, run)
    raw_payload = {
        "row_number": row_number,
        "row": row,
        "ingestion_lineage": _replacement_lineage_for_run(run),
    }
    common = {
        "ingestion_run": run,
        "source": run.source,
        "recorded_at": recorded_at,
        "source_name": run.source_name,
        "freshness_state": freshness_state,
        "release_version": run.release_version,
        "source_ref": _first_nonempty(row, "source_ref") or run.source_ref,
        "raw_payload": raw_payload,
    }

    errors: list[dict[str, Any]] = []
    population_records: list[PopulationBaselineRecord] = []
    exposure_records: list[ExposureFeatureRecord] = []
    catchment_records: list[CatchmentPopulationRecord] = []

    population_total = _population_total_for_row(row)
    if population_total is not None:
        if ward is None:
            errors.append({"row_number": row_number, "reason": "ward_not_found_for_population_record"})
        else:
            population_truth_class = _truth_class_for_record(row, run, record_kind="population")
            population_records.append(
                PopulationBaselineRecord(
                    ward=ward,
                    population_total=population_total,
                    population_under_five=_parse_int(_first_nonempty(row, "population_under_five", "under_five")),
                    household_count_proxy=_parse_int(_first_nonempty(row, "household_count_proxy", "households")),
                    truth_class=population_truth_class,
                    source_kind=_source_kind_for_row(row, run, population_truth_class),
                    supersedes_record_ref=_first_nonempty(row, "supersedes_record_ref")
                    or (f"population_exposure_run:{run.replaces_run_id}" if run.replaces_run_id else ""),
                    revision_number=_parse_int(_first_nonempty(row, "revision_number")) or (2 if run.replaces_run_id else 1),
                    **common,
                )
            )

    generic_exposure_type = _normalize_choice(_first_nonempty(row, "exposure_type"))
    generic_exposure_value = _parse_float(_first_nonempty(row, "exposure_value"))
    valid_exposure_types = {choice[0] for choice in ExposureFeatureRecord.EXPOSURE_TYPE_CHOICES}
    exposure_values: list[tuple[str, float]] = []
    if generic_exposure_type in valid_exposure_types and generic_exposure_value is not None:
        exposure_values.append((generic_exposure_type, generic_exposure_value))
    for exposure_type, columns in EXPOSURE_FIELD_MAP:
        value = _parse_float(_first_nonempty(row, *columns))
        if value is not None and all(existing_type != exposure_type for existing_type, _ in exposure_values):
            exposure_values.append((exposure_type, value))

    for exposure_type, exposure_value in exposure_values:
        if ward is None:
            errors.append({"row_number": row_number, "reason": f"ward_not_found_for_{exposure_type}_record"})
            continue
        exposure_truth_class = _truth_class_for_record(row, run, record_kind="exposure")
        exposure_records.append(
            ExposureFeatureRecord(
                ward=ward,
                exposure_type=exposure_type,
                exposure_value=exposure_value,
                unit=_first_nonempty(row, "unit"),
                truth_class=exposure_truth_class,
                source_kind=_source_kind_for_row(row, run, exposure_truth_class),
                aggregation_method=_first_nonempty(row, "aggregation_method"),
                spatial_resolution=_first_nonempty(row, "spatial_resolution"),
                notes=_first_nonempty(row, "notes"),
                **common,
            )
        )

    catchment_population = _parse_float(_first_nonempty(row, "catchment_population_estimate", "catchment_population"))
    if catchment_population is not None:
        if facility is None:
            errors.append({"row_number": row_number, "reason": "facility_not_found_for_catchment_record"})
        else:
            catchment_truth_class = _truth_class_for_record(row, run, record_kind="catchment")
            catchment_records.append(
                CatchmentPopulationRecord(
                    facility=facility,
                    catchment_population_estimate=catchment_population,
                    catchment_under_five_estimate=_parse_float(_first_nonempty(row, "catchment_under_five_estimate")),
                    assigned_ward_ids=_assigned_ward_ids(row, ward),
                    assignment_method=_first_nonempty(row, "assignment_method"),
                    truth_class=catchment_truth_class,
                    source_kind=_source_kind_for_row(row, run, catchment_truth_class),
                    **common,
                )
            )

    if not population_records and not exposure_records and not catchment_records and not errors:
        errors.append({"row_number": row_number, "reason": "no_canonical_population_exposure_or_catchment_fields"})
    return population_records, exposure_records, catchment_records, errors


def _persist_canonical_records_for_run(
    run: PopulationExposureIngestionRun,
    accepted_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    population_records: list[PopulationBaselineRecord] = []
    exposure_records: list[ExposureFeatureRecord] = []
    catchment_records: list[CatchmentPopulationRecord] = []
    canonical_rejections: list[dict[str, Any]] = []
    normalized_row_numbers: set[int] = set()

    for accepted in accepted_rows:
        row_population, row_exposure, row_catchment, row_errors = _canonical_records_for_row(
            run=run,
            row_number=accepted["row_number"],
            row=accepted["row"],
        )
        population_records.extend(row_population)
        exposure_records.extend(row_exposure)
        catchment_records.extend(row_catchment)
        canonical_rejections.extend(row_errors)
        if row_population or row_exposure or row_catchment:
            normalized_row_numbers.add(accepted["row_number"])

    PopulationBaselineRecord.objects.bulk_create(population_records)
    ExposureFeatureRecord.objects.bulk_create(exposure_records)
    CatchmentPopulationRecord.objects.bulk_create(catchment_records)
    return {
        "source_rows_normalized": len(normalized_row_numbers),
        "source_rows_not_normalized": len(accepted_rows) - len(normalized_row_numbers),
        "population_baseline_records": len(population_records),
        "exposure_feature_records": len(exposure_records),
        "catchment_population_records": len(catchment_records),
        "canonical_records_total": len(population_records) + len(exposure_records) + len(catchment_records),
        "canonical_rejections": canonical_rejections[:MAX_REJECTED_ROW_DETAILS],
    }


def _mark_replaced_records_for_run(
    *,
    replaced_run: PopulationExposureIngestionRun,
    replacement_run: PopulationExposureIngestionRun,
) -> dict[str, int]:
    replacement_payload = {
        "replaced_by_run_id": replacement_run.id,
        "replaced_at": timezone.now().isoformat(),
        "replacement_reason": replacement_run.replacement_reason,
    }

    def mark_records(records) -> int:
        count = 0
        for record in records:
            record.freshness_state = PopulationExposureFreshness.REPLACED_BY_NEW_RELEASE
            record.raw_payload = {
                **(record.raw_payload or {}),
                "replacement": replacement_payload,
            }
            record.save(update_fields=["freshness_state", "raw_payload"])
            count += 1
        return count

    population_count = mark_records(PopulationBaselineRecord.objects.filter(ingestion_run=replaced_run))
    exposure_count = mark_records(ExposureFeatureRecord.objects.filter(ingestion_run=replaced_run))
    catchment_count = mark_records(CatchmentPopulationRecord.objects.filter(ingestion_run=replaced_run))
    return {
        "population_baseline_records": population_count,
        "exposure_feature_records": exposure_count,
        "catchment_population_records": catchment_count,
        "canonical_records_total": population_count + exposure_count + catchment_count,
    }


def _mark_records_for_run_freshness(
    *,
    run: PopulationExposureIngestionRun,
    freshness_state: str,
    marker_key: str,
    reason: str,
) -> dict[str, int]:
    marker_payload = {
        "run_id": run.id,
        "marked_at": timezone.now().isoformat(),
        "reason": reason,
    }

    def mark_records(records) -> int:
        count = 0
        for record in records:
            record.freshness_state = freshness_state
            record.raw_payload = {
                **(record.raw_payload or {}),
                marker_key: marker_payload,
            }
            record.save(update_fields=["freshness_state", "raw_payload"])
            count += 1
        return count

    population_count = mark_records(PopulationBaselineRecord.objects.filter(ingestion_run=run))
    exposure_count = mark_records(ExposureFeatureRecord.objects.filter(ingestion_run=run))
    catchment_count = mark_records(CatchmentPopulationRecord.objects.filter(ingestion_run=run))
    return {
        "population_baseline_records": population_count,
        "exposure_feature_records": exposure_count,
        "catchment_population_records": catchment_count,
        "canonical_records_total": population_count + exposure_count + catchment_count,
    }


def upsert_population_exposure_source(
    *,
    source_name: str,
    source_type: str,
    source_timestamp: datetime | None = None,
    release_version: str = "",
    source_ref: str = "",
    operator_note: str = "",
    metadata: dict[str, Any] | None = None,
) -> PopulationExposureSource:
    adapter_spec_for_source_type(source_type)
    queryset = PopulationExposureSource.objects.filter(
        source_name=source_name,
        source_type=source_type,
        release_version=release_version,
        source_ref=source_ref,
    ).order_by("-submitted_at", "-id")
    source = queryset.first()
    if source is None:
        return PopulationExposureSource.objects.create(
            source_name=source_name,
            source_type=source_type,
            source_timestamp=source_timestamp,
            release_version=release_version,
            source_ref=source_ref,
            operator_note=operator_note,
            metadata=metadata or {},
        )

    source.source_timestamp = source_timestamp
    source.operator_note = operator_note
    source.metadata = metadata or source.metadata or {}
    source.is_active = True
    source.save(update_fields=["source_timestamp", "operator_note", "metadata", "is_active", "updated_at"])
    return source


def run_population_exposure_csv_ingestion(
    *,
    file_path: str | Path,
    source_name: str,
    source_type: str,
    source_timestamp: datetime | None = None,
    release_version: str = "",
    source_ref: str = "",
    correction_mode: str = PopulationExposureIngestionRun.CORRECTION_ORIGINAL,
    replacement_reason: str = "",
    operator_note: str = "",
    execution_mode: str = PopulationExposureIngestionRun.EXECUTION_MANUAL,
    fallback_used: bool = False,
    replay_of: PopulationExposureIngestionRun | None = None,
    replaces_run: PopulationExposureIngestionRun | None = None,
) -> PopulationExposureIngestionRun:
    spec = adapter_spec_for_source_type(source_type)
    if not source_name.strip():
        raise ValueError("source_name is required for population/exposure ingestion.")
    if correction_mode not in {choice[0] for choice in PopulationExposureIngestionRun.CORRECTION_MODE_CHOICES}:
        raise ValueError(f"Unsupported correction_mode '{correction_mode}'.")
    if execution_mode not in {choice[0] for choice in PopulationExposureIngestionRun.EXECUTION_MODE_CHOICES}:
        raise ValueError(f"Unsupported execution_mode '{execution_mode}'.")
    if correction_mode == PopulationExposureIngestionRun.CORRECTION_RELEASE_REPLACEMENT and not replacement_reason.strip():
        raise ValueError("replacement_reason is required for release replacement ingestion runs.")
    if correction_mode == PopulationExposureIngestionRun.CORRECTION_RELEASE_REPLACEMENT and replaces_run is None:
        raise ValueError("replaces_run is required for release replacement ingestion runs.")
    if replaces_run is not None and correction_mode != PopulationExposureIngestionRun.CORRECTION_RELEASE_REPLACEMENT:
        raise ValueError("replaces_run is only supported for release replacement ingestion runs.")
    if replaces_run is not None and replaces_run.source_type != source_type:
        raise ValueError("replaces_run must have the same source_type as the replacement ingestion run.")
    if replaces_run is not None and replaces_run.source_name != source_name:
        raise ValueError("replaces_run must have the same source_name as the replacement ingestion run.")
    if replaces_run is not None and replaces_run.status == PopulationExposureIngestionRun.STATUS_RUNNING:
        raise ValueError("replaces_run cannot target a still-running ingestion run.")
    if correction_mode == PopulationExposureIngestionRun.CORRECTION_RELEASE_REPLACEMENT and not release_version.strip():
        raise ValueError("release_version is required for release replacement ingestion runs.")
    if correction_mode == PopulationExposureIngestionRun.CORRECTION_RELEASE_REPLACEMENT and not source_ref.strip():
        raise ValueError("source_ref is required for release replacement ingestion runs.")
    if execution_mode == PopulationExposureIngestionRun.EXECUTION_SCHEDULED and not spec.scheduled_supported:
        raise ValueError(f"Scheduled ingestion is not supported for source_type '{source_type}'.")

    source = upsert_population_exposure_source(
        source_name=source_name,
        source_type=source_type,
        source_timestamp=source_timestamp,
        release_version=release_version,
        source_ref=source_ref,
        operator_note=operator_note,
        metadata={"adapter_key": spec.adapter_key, "scheduled_supported": spec.scheduled_supported},
    )
    run = PopulationExposureIngestionRun.objects.create(
        source=source,
        status=PopulationExposureIngestionRun.STATUS_RUNNING,
        source_name=source.source_name,
        source_type=source.source_type,
        source_timestamp=source.source_timestamp,
        release_version=source.release_version,
        source_ref=source.source_ref,
        adapter_key=spec.adapter_key,
        input_ref=str(file_path),
        execution_mode=execution_mode,
        correction_mode=correction_mode,
        replacement_reason=replacement_reason,
        fallback_used=fallback_used,
        operator_note=operator_note,
        source_metadata={
            "source_id": source.id,
            "source_name": source.source_name,
            "source_type": source.source_type,
            "release_version": source.release_version,
            "source_ref": source.source_ref,
            "source_timestamp": source.source_timestamp.isoformat() if source.source_timestamp else None,
            "adapter_key": spec.adapter_key,
        },
        replay_of=replay_of,
        replaces_run=replaces_run,
    )

    try:
        with transaction.atomic():
            inspection = _validated_population_exposure_csv(file_path, source_type=source_type)
            canonical_summary = _persist_canonical_records_for_run(run, inspection["accepted_rows"])
            run.records_seen = inspection["records_seen"]
            run.records_loaded = canonical_summary["source_rows_normalized"]
            run.records_rejected = inspection["records_rejected"] + canonical_summary["source_rows_not_normalized"]
            run.rejected_rows = (inspection["rejected_rows"] + canonical_summary["canonical_rejections"])[:MAX_REJECTED_ROW_DETAILS]
            run.results = {
                "adapter_key": inspection["adapter_key"],
                "adapter_notes": inspection["adapter_notes"],
                "scheduled_supported": inspection["scheduled_supported"],
                "headers": inspection["headers"],
                "unknown_columns": inspection["unknown_columns"],
                "sample_rows": inspection["sample_rows"],
                "phase": "phase_2_canonical_normalization",
                "canonical_records_persisted": True,
                "canonical_summary": {
                    key: value
                    for key, value in canonical_summary.items()
                    if key != "canonical_rejections"
                },
            }
            if run.records_seen == 0:
                run.error_summary = "No source rows were found in the import file."
                run.status = PopulationExposureIngestionRun.STATUS_FAILED
            elif run.records_loaded == 0:
                run.error_summary = "No canonical population, exposure, or catchment records were created."
                run.status = PopulationExposureIngestionRun.STATUS_FAILED
            elif run.records_rejected == 0:
                run.status = PopulationExposureIngestionRun.STATUS_SUCCESS
            else:
                run.status = PopulationExposureIngestionRun.STATUS_PARTIAL

            if (
                run.status == PopulationExposureIngestionRun.STATUS_SUCCESS
                and replaces_run is not None
                and execution_mode != PopulationExposureIngestionRun.EXECUTION_REPLAY
            ):
                replacement_summary = _mark_replaced_records_for_run(
                    replaced_run=replaces_run,
                    replacement_run=run,
                )
                run.results["replacement_activation"] = {
                    "activated": True,
                    "replaced_run_id": replaces_run.id,
                    "replaced_records_marked": replacement_summary,
                }
            elif replaces_run is not None:
                reason = (
                    "replay_runs_do_not_activate_replacements"
                    if execution_mode == PopulationExposureIngestionRun.EXECUTION_REPLAY
                    else "replacement_run_not_successful"
                )
                run.results["replacement_activation"] = {
                    "activated": False,
                    "replaced_run_id": replaces_run.id,
                    "reason": reason,
                }

            if execution_mode == PopulationExposureIngestionRun.EXECUTION_REPLAY and run.records_loaded > 0:
                isolation_reason = "replay_records_do_not_feed_current_snapshots"
                run.results["replay_isolation"] = {
                    "isolated": True,
                    "reason": isolation_reason,
                    "records_marked": _mark_records_for_run_freshness(
                        run=run,
                        freshness_state=PopulationExposureFreshness.REPLAY_DIAGNOSTIC,
                        marker_key="replay_isolation",
                        reason=isolation_reason,
                    ),
                }
            elif (
                correction_mode == PopulationExposureIngestionRun.CORRECTION_RELEASE_REPLACEMENT
                and run.status != PopulationExposureIngestionRun.STATUS_SUCCESS
                and run.records_loaded > 0
            ):
                isolation_reason = "replacement_run_not_successful"
                run.results.setdefault(
                    "replacement_activation",
                    {
                        "activated": False,
                        "replaced_run_id": replaces_run.id if replaces_run is not None else None,
                        "reason": isolation_reason,
                    },
                )
                run.results["replacement_activation"]["candidate_records_marked_non_current"] = (
                    _mark_records_for_run_freshness(
                        run=run,
                        freshness_state=PopulationExposureFreshness.REPLACEMENT_NOT_ACTIVATED,
                        marker_key="replacement_candidate_isolation",
                        reason=isolation_reason,
                    )
                )
    except Exception as error:
        run.status = PopulationExposureIngestionRun.STATUS_FAILED
        run.error_summary = str(error)

    run.completed_at = timezone.now()
    run.save(
        update_fields=[
            "status",
            "records_seen",
            "records_loaded",
            "records_rejected",
            "rejected_rows",
            "results",
            "error_summary",
            "completed_at",
        ]
    )
    return run


def replay_population_exposure_ingestion_run(
    run_id: int,
    *,
    file_path: str | Path | None = None,
    operator_note: str = "",
) -> PopulationExposureIngestionRun:
    original = PopulationExposureIngestionRun.objects.select_related("source").get(pk=run_id)
    return run_population_exposure_csv_ingestion(
        file_path=file_path or original.input_ref,
        source_name=original.source_name,
        source_type=original.source_type,
        source_timestamp=original.source_timestamp,
        release_version=original.release_version,
        source_ref=original.source_ref,
        correction_mode=original.correction_mode,
        replacement_reason=original.replacement_reason,
        operator_note=operator_note or f"Replay of population/exposure ingestion run {original.id}",
        execution_mode=PopulationExposureIngestionRun.EXECUTION_REPLAY,
        fallback_used=original.fallback_used,
        replay_of=original,
        replaces_run=original.replaces_run,
    )


def build_population_exposure_replay_plan(run: PopulationExposureIngestionRun) -> dict[str, Any]:
    return {
        "run_id": run.id,
        "source_name": run.source_name,
        "source_type": run.source_type,
        "release_version": run.release_version,
        "input_ref": run.input_ref,
        "replay_command": f"python manage.py ingest_population_exposure --replay-of {run.id}",
        "backfill_command_shape": (
            "python manage.py ingest_population_exposure --file <csv> --source-name <name> "
            "--source-type <type> --release-version <release> --correction-mode backfill"
        ),
        "release_replacement_command_shape": (
            "python manage.py ingest_population_exposure --file <csv> --source-name <name> "
            "--source-type <type> --release-version <release> "
            "--source-ref <ref> --correction-mode release_replacement "
            "--replacement-reason <reason> --replaces-run <run_id>"
        ),
    }
