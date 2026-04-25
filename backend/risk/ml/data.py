from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4
from typing import Iterable

from risk.models import FeatureDataset, FeatureDatasetRow, IngestionRun, Ward

from .ingestion import fetch_rainfall_for_wards


FEATURE_SCHEMA_VERSION = "baseline-v1"


@dataclass
class WardFeatureRow:
    ward_id: int
    ward_name: str
    rainfall_mm: float
    flood_indicator: float
    historical_cases: float
    month: int
    population_proxy: float
    label: int | None = None


@dataclass
class InferenceDataset:
    rows: list[WardFeatureRow]
    feature_dataset: FeatureDataset | None = None
    rainfall_ingestion_run: IngestionRun | None = None


@dataclass
class TrainingDataset:
    rows: list[WardFeatureRow]
    feature_dataset: FeatureDataset | None = None


def month_to_seasonality(month: int) -> float:
    rainy_months = {3, 4, 5, 10, 11, 12}
    return 1.0 if month in rainy_months else 0.0


def build_mock_training_rows() -> list[WardFeatureRow]:
    rows = [
        WardFeatureRow(1, "North Kamagambo", 120.0, 0.80, 16, 4, 5400, 1),
        WardFeatureRow(2, "North Kadem", 65.0, 0.40, 7, 4, 4700, 0),
        WardFeatureRow(3, "Macalder Kanyarwanda", 110.0, 0.76, 14, 11, 5100, 1),
        WardFeatureRow(4, "Got Kachola", 118.0, 0.82, 17, 5, 4900, 1),
        WardFeatureRow(5, "Central Karungu", 58.0, 0.35, 5, 7, 4500, 0),
        WardFeatureRow(6, "West Kanyamkago", 75.0, 0.45, 8, 10, 5200, 0),
        WardFeatureRow(7, "Aneko", 98.0, 0.66, 11, 11, 4300, 1),
        WardFeatureRow(8, "Kaler", 55.0, 0.30, 4, 1, 4000, 0),
    ]
    return rows


def _feature_values_from_row(row: WardFeatureRow) -> dict:
    return {
        "rainfall_mm": row.rainfall_mm,
        "flood_indicator": row.flood_indicator,
        "historical_cases": row.historical_cases,
        "month": row.month,
        "seasonality": month_to_seasonality(row.month),
        "population_proxy": row.population_proxy,
    }


def build_training_feature_dataset(month: int) -> TrainingDataset:
    rows = build_mock_training_rows()
    dataset = FeatureDataset.objects.create(
        dataset_ref=f"training-{FEATURE_SCHEMA_VERSION}-month-{month}-{uuid4().hex[:8]}",
        dataset_kind=FeatureDataset.KIND_TRAINING,
        schema_version=FEATURE_SCHEMA_VERSION,
        source_kind=FeatureDataset.SOURCE_KIND_SEEDED,
        month=month,
        feature_keys=[
            "rainfall_mm",
            "flood_indicator",
            "historical_cases",
            "month",
            "seasonality",
            "population_proxy",
        ],
        row_count=len(rows),
        lineage_metadata={
            "builder": "build_training_feature_dataset",
            "source_mode": "seeded-training-baseline",
        },
    )
    FeatureDatasetRow.objects.bulk_create(
        [
            FeatureDatasetRow(
                dataset=dataset,
                ward_id=None,
                ward_name_snapshot=row.ward_name,
                month=row.month,
                feature_values=_feature_values_from_row(row),
                label=row.label,
            )
            for row in rows
        ]
    )
    return TrainingDataset(rows=rows, feature_dataset=dataset)


def build_inference_feature_dataset(wards: Iterable[Ward], month: int) -> InferenceDataset:
    ward_list = list(wards)
    rainfall_rows, ingestion_run = fetch_rainfall_for_wards(ward_list, return_ingestion_run=True)

    rows: list[WardFeatureRow] = []

    for idx, ward in enumerate(ward_list, start=1):
        rainfall = rainfall_rows.get(ward.name)
        rainfall_mm = rainfall.rainfall_mm if rainfall else round(45 + (ward.current_risk_score * 90), 2)

        # Keep flood proxy mock-derived for now, but partially shaped by real rainfall.
        current_score = ward.current_risk_score or 0.0
        flood_indicator = round(min(0.95, 0.15 + (rainfall_mm / 150.0) + (current_score * 0.20)), 3)
        historical_cases = max(1, int(round((current_score * 14) + (rainfall_mm / 20.0))))
        population_proxy = float(4000 + (idx * 250))

        rows.append(
            WardFeatureRow(
                ward_id=ward.id,
                ward_name=ward.name,
                rainfall_mm=rainfall_mm,
                flood_indicator=flood_indicator,
                historical_cases=historical_cases,
                month=month,
                population_proxy=population_proxy,
                label=None,
            )
        )

    source_kind = FeatureDataset.SOURCE_KIND_HYBRID
    if ingestion_run and ingestion_run.source_kind == IngestionRun.SOURCE_KIND_LIVE:
        source_kind = FeatureDataset.SOURCE_KIND_LIVE
    elif ingestion_run and ingestion_run.source_kind == IngestionRun.SOURCE_KIND_SEEDED:
        source_kind = FeatureDataset.SOURCE_KIND_SEEDED

    dataset = FeatureDataset.objects.create(
        dataset_ref=f"inference-{FEATURE_SCHEMA_VERSION}-month-{month}-{uuid4().hex[:8]}",
        dataset_kind=FeatureDataset.KIND_INFERENCE,
        schema_version=FEATURE_SCHEMA_VERSION,
        source_kind=source_kind,
        month=month,
        feature_keys=[
            "rainfall_mm",
            "flood_indicator",
            "historical_cases",
            "month",
            "seasonality",
            "population_proxy",
        ],
        row_count=len(rows),
        lineage_metadata={
            "builder": "build_inference_feature_dataset",
            "rainfall_ingestion_run_id": ingestion_run.id if ingestion_run else None,
            "rainfall_source_kind": ingestion_run.source_kind if ingestion_run else None,
        },
    )
    FeatureDatasetRow.objects.bulk_create(
        [
            FeatureDatasetRow(
                dataset=dataset,
                ward_id=row.ward_id,
                ward_name_snapshot=row.ward_name,
                month=row.month,
                feature_values=_feature_values_from_row(row),
                label=row.label,
            )
            for row in rows
        ]
    )

    return InferenceDataset(rows=rows, feature_dataset=dataset, rainfall_ingestion_run=ingestion_run)
