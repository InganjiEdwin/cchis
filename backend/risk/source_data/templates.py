from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from io import StringIO
from typing import Any

from risk.source_data.registry import source_data_feed_definition, source_data_feed_definitions


SOURCE_DATA_TEMPLATE_SCHEMA_VERSION = "source-data-csv-template-v1"
SOURCE_DATA_TEMPLATE_DOWNLOAD_EVENT = "SOURCE_DATA_TEMPLATE_DOWNLOAD"


@dataclass(frozen=True)
class SourceDataTemplateDefinition:
    feed_key: str
    filename: str
    columns: tuple[str, ...]
    example_row: dict[str, str]


SOURCE_DATA_CSV_TEMPLATES: dict[str, SourceDataTemplateDefinition] = {
    "surveillance_weekly_aggregate": SourceDataTemplateDefinition(
        feed_key="surveillance_weekly_aggregate",
        filename="surveillance_weekly_aggregate_template.csv",
        columns=(
            "ward_code",
            "reporting_period_start",
            "reporting_period_end",
            "suspected_cases",
            "confirmed_cases",
            "diarrheal_count",
            "reporting_granularity",
            "source_ref",
        ),
        example_row={
            "ward_code": "MIG-WARD-001",
            "reporting_period_start": "2026-04-27",
            "reporting_period_end": "2026-05-03",
            "suspected_cases": "3",
            "confirmed_cases": "1",
            "diarrheal_count": "8",
            "reporting_granularity": "week",
            "source_ref": "dhis2-weekly-export:row-1",
        },
    ),
    "surveillance_daily_aggregate": SourceDataTemplateDefinition(
        feed_key="surveillance_daily_aggregate",
        filename="surveillance_daily_aggregate_template.csv",
        columns=(
            "ward_code",
            "reporting_period_start",
            "reporting_period_end",
            "suspected_cases",
            "confirmed_cases",
            "diarrheal_count",
            "reporting_granularity",
            "source_ref",
        ),
        example_row={
            "ward_code": "MIG-WARD-001",
            "reporting_period_start": "2026-05-05",
            "reporting_period_end": "2026-05-05",
            "suspected_cases": "1",
            "confirmed_cases": "0",
            "diarrheal_count": "2",
            "reporting_granularity": "day",
            "source_ref": "daily-line-summary:row-1",
        },
    ),
    "surveillance_backfill": SourceDataTemplateDefinition(
        feed_key="surveillance_backfill",
        filename="surveillance_backfill_template.csv",
        columns=(
            "ward_code",
            "reporting_period_start",
            "reporting_period_end",
            "suspected_cases",
            "confirmed_cases",
            "diarrheal_count",
            "backfill_batch_id",
            "source_ref",
        ),
        example_row={
            "ward_code": "MIG-WARD-001",
            "reporting_period_start": "2026-02-02",
            "reporting_period_end": "2026-02-08",
            "suspected_cases": "2",
            "confirmed_cases": "1",
            "diarrheal_count": "6",
            "backfill_batch_id": "migori-surveillance-backfill-2026-05",
            "source_ref": "county-surveillance-backfill:row-1",
        },
    ),
    "population_baseline": SourceDataTemplateDefinition(
        feed_key="population_baseline",
        filename="population_baseline_template.csv",
        columns=(
            "ward_code",
            "population_total",
            "population_under_five",
            "household_count_proxy",
            "unit",
            "source_ref",
        ),
        example_row={
            "ward_code": "MIG-WARD-001",
            "population_total": "24500",
            "population_under_five": "3600",
            "household_count_proxy": "5200",
            "unit": "people",
            "source_ref": "knbs-release:table-ward-population",
        },
    ),
    "gridded_population": SourceDataTemplateDefinition(
        feed_key="gridded_population",
        filename="gridded_population_template.csv",
        columns=(
            "ward_code",
            "population_density",
            "gridded_population_value",
            "aggregation_method",
            "spatial_resolution",
            "unit",
            "source_ref",
        ),
        example_row={
            "ward_code": "MIG-WARD-001",
            "population_density": "412.5",
            "gridded_population_value": "24500",
            "aggregation_method": "ward_sum_from_grid",
            "spatial_resolution": "100m",
            "unit": "people_per_km2",
            "source_ref": "worldpop-release:2026-v1",
        },
    ),
    "settlement_layer": SourceDataTemplateDefinition(
        feed_key="settlement_layer",
        filename="settlement_layer_template.csv",
        columns=(
            "ward_code",
            "settlement_concentration",
            "built_up_area",
            "aggregation_method",
            "unit",
            "source_ref",
        ),
        example_row={
            "ward_code": "MIG-WARD-001",
            "settlement_concentration": "0.62",
            "built_up_area": "14.3",
            "aggregation_method": "ward_mean",
            "unit": "index",
            "source_ref": "osm-settlement-extract:2026-05",
        },
    ),
    "wash_vulnerability_layer": SourceDataTemplateDefinition(
        feed_key="wash_vulnerability_layer",
        filename="wash_vulnerability_layer_template.csv",
        columns=(
            "ward_code",
            "wash_vulnerability",
            "sanitation_vulnerability",
            "water_access_vulnerability",
            "vulnerability_score",
            "aggregation_method",
            "unit",
            "source_ref",
        ),
        example_row={
            "ward_code": "MIG-WARD-001",
            "wash_vulnerability": "0.71",
            "sanitation_vulnerability": "0.64",
            "water_access_vulnerability": "0.77",
            "vulnerability_score": "0.71",
            "aggregation_method": "ward_weighted_mean",
            "unit": "index",
            "source_ref": "wash-assessment:2026-q2",
        },
    ),
    "water_body_distance_layer": SourceDataTemplateDefinition(
        feed_key="water_body_distance_layer",
        filename="water_body_distance_layer_template.csv",
        columns=(
            "ward_code",
            "water_body_distance",
            "distance_to_water",
            "water_body_proximity",
            "aggregation_method",
            "unit",
            "source_ref",
        ),
        example_row={
            "ward_code": "MIG-WARD-001",
            "water_body_distance": "1.8",
            "distance_to_water": "1.8",
            "water_body_proximity": "0.56",
            "aggregation_method": "ward_median",
            "unit": "km",
            "source_ref": "osm-water-bodies:2026-05",
        },
    ),
    "flood_exposure_layer": SourceDataTemplateDefinition(
        feed_key="flood_exposure_layer",
        filename="flood_exposure_layer_template.csv",
        columns=(
            "ward_code",
            "floodplain_exposure",
            "flood_exposure",
            "flood_risk",
            "exposed_population_proxy",
            "aggregation_method",
            "unit",
            "source_ref",
        ),
        example_row={
            "ward_code": "MIG-WARD-001",
            "floodplain_exposure": "0.34",
            "flood_exposure": "0.41",
            "flood_risk": "0.39",
            "exposed_population_proxy": "8200",
            "aggregation_method": "ward_overlay",
            "unit": "index",
            "source_ref": "county-flood-layer:2026-05",
        },
    ),
    "facility_catchment_mapping": SourceDataTemplateDefinition(
        feed_key="facility_catchment_mapping",
        filename="facility_catchment_mapping_template.csv",
        columns=(
            "facility_code",
            "assigned_ward_ids",
            "catchment_population",
            "catchment_under_five_estimate",
            "assignment_method",
            "unit",
            "source_ref",
        ),
        example_row={
            "facility_code": "FAC-MIG-001",
            "assigned_ward_ids": "MIG-WARD-001;MIG-WARD-002",
            "catchment_population": "18500",
            "catchment_under_five_estimate": "2800",
            "assignment_method": "county_facility_catchment_review",
            "unit": "people",
            "source_ref": "facility-catchment-workbook:row-1",
        },
    ),
    "facility_readiness_snapshot": SourceDataTemplateDefinition(
        feed_key="facility_readiness_snapshot",
        filename="facility_readiness_snapshot_template.csv",
        columns=(
            "facility_code",
            "facility_name",
            "ward_code",
            "reported_at",
            "ors_sachets_available",
            "iv_fluids_available",
            "zinc_available",
            "chlorine_available",
            "beds_available",
            "staff_on_duty",
            "referral_available",
            "stockout_notes",
            "service_disruption",
            "source_kind",
            "source_ref",
        ),
        example_row={
            "facility_code": "FAC-MIG-001",
            "facility_name": "Got Kachola Dispensary",
            "ward_code": "MIG-WARD-001",
            "reported_at": "2026-05-05T08:00:00+03:00",
            "ors_sachets_available": "120",
            "iv_fluids_available": "36",
            "zinc_available": "80",
            "chlorine_available": "55",
            "beds_available": "6",
            "staff_on_duty": "4",
            "referral_available": "true",
            "stockout_notes": "",
            "service_disruption": "false",
            "source_kind": "facility_report",
            "source_ref": "readiness-checklist:row-1",
        },
    ),
}


def source_data_template_definition(feed_key: str) -> SourceDataTemplateDefinition:
    template = SOURCE_DATA_CSV_TEMPLATES.get(feed_key)
    if template is None:
        raise KeyError(feed_key)
    source_data_feed_definition(feed_key)
    return template


def _template_as_dict(template: SourceDataTemplateDefinition) -> dict[str, Any]:
    return {
        "feed_key": template.feed_key,
        "filename": template.filename,
        "columns": list(template.columns),
        "example_row": dict(template.example_row),
    }


def source_data_template_contracts() -> dict[str, dict[str, Any]]:
    return {
        feed_key: _template_as_dict(template)
        for feed_key, template in sorted(SOURCE_DATA_CSV_TEMPLATES.items())
    }


def validate_source_data_template_contract() -> list[str]:
    errors: list[str] = []
    expected_feed_keys = {definition.feed_key for definition in source_data_feed_definitions()}
    template_feed_keys = set(SOURCE_DATA_CSV_TEMPLATES)
    missing_templates = sorted(expected_feed_keys - template_feed_keys)
    unexpected_templates = sorted(template_feed_keys - expected_feed_keys)
    if missing_templates:
        errors.append(f"source_data_templates_missing:{','.join(missing_templates)}")
    if unexpected_templates:
        errors.append(f"source_data_templates_unexpected:{','.join(unexpected_templates)}")

    for feed_key, template in sorted(SOURCE_DATA_CSV_TEMPLATES.items()):
        if not template.filename.endswith(".csv"):
            errors.append(f"{feed_key}:template_filename_not_csv")
        if not template.columns:
            errors.append(f"{feed_key}:template_columns_missing")

        missing_example_columns = [column for column in template.columns if column not in template.example_row]
        if missing_example_columns:
            errors.append(f"{feed_key}:template_example_missing:{','.join(missing_example_columns)}")

        try:
            definition = source_data_feed_definition(feed_key)
        except KeyError:
            continue
        unknown_template_columns = sorted(set(template.columns) - set(definition.accepted_columns))
        if unknown_template_columns:
            errors.append(f"{feed_key}:template_columns_not_accepted:{','.join(unknown_template_columns)}")
        for index, group in enumerate(definition.required_any_columns, start=1):
            if not set(template.columns).intersection(group):
                errors.append(f"{feed_key}:template_missing_required_group_{index}:{','.join(group)}")
    return errors


def build_source_data_csv_template_file(feed_key: str) -> dict[str, str | int | list[str] | dict[str, str]]:
    try:
        template = source_data_template_definition(feed_key)
    except KeyError as error:
        raise ValueError(f"Unknown source-data CSV template feed key: {feed_key}") from error

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(template.columns))
    writer.writeheader()
    writer.writerow({column: template.example_row.get(column, "") for column in template.columns})
    payload = buffer.getvalue()
    return {
        "schema_version": SOURCE_DATA_TEMPLATE_SCHEMA_VERSION,
        "filename": template.filename,
        "content_type": "text/csv",
        "feed_key": feed_key,
        "columns": list(template.columns),
        "example_row": dict(template.example_row),
        "row_count": 1,
        "payload": payload,
        "payload_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    }
