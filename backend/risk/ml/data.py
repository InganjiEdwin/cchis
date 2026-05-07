from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from uuid import uuid4
from typing import Iterable

from risk.climate_coverage import (
    DEFAULT_CLAIMED_FORECAST_HORIZON_DAYS,
    climate_coverage_from_prediction,
    climate_source_label_for_record_type,
)
from risk.models import FeatureDataset, FeatureDatasetRow, IngestionRun, SurveillanceTruthLevel, Ward
from risk.population_exposure_features import (
    POPULATION_EXPOSURE_FEATURE_KEYS,
    build_population_exposure_feature_dataset,
)
from risk.surveillance_labels import (
    SURVEILLANCE_LABEL_SCHEMA_VERSION,
    latest_surveillance_label_dataset,
)
from risk.surveillance_features import (
    SURVEILLANCE_CONTEXT_FEATURE_KEYS,
    SURVEILLANCE_FEATURE_SCHEMA_VERSION,
    build_surveillance_feature_snapshot,
    build_surveillance_lead_time_validation_summary,
)

from .ingestion import fetch_rainfall_for_wards


FEATURE_SCHEMA_VERSION = "baseline-v1"
SURVEILLANCE_LABEL_TRAINING_USAGE = "phase_1_training_labels_from_surveillance_label_dataset"
SEEDED_TRAINING_LABEL_USAGE = "seeded_training_baseline_not_goal_aligned"
SURVEILLANCE_REFERENCE_ONLY_LABEL_USAGE = "surveillance_label_reference_only_training_rows_seeded_fallback"
WARD_RISK_BASE_FEATURE_KEYS = [
    "rainfall_mm",
    "flood_indicator",
    "historical_cases",
    "month",
    "seasonality",
    "population_proxy",
]
WARD_RISK_POPULATION_EXPOSURE_MODEL_FEATURE_KEYS = [
    "population_density",
    "settlement_concentration",
    "floodplain_exposure",
    "water_body_proximity",
    "wash_vulnerability",
    "exposed_population_proxy_scaled",
    "catchment_population_estimate_scaled",
]
WARD_RISK_FEATURE_KEYS = [
    *WARD_RISK_BASE_FEATURE_KEYS,
    *WARD_RISK_POPULATION_EXPOSURE_MODEL_FEATURE_KEYS,
]
WARD_RISK_SURVEILLANCE_CONTEXT_FEATURE_KEYS = [
    "historical_cases_source",
    *SURVEILLANCE_CONTEXT_FEATURE_KEYS,
]


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
    population_total: float | None = None
    population_density: float | None = None
    settlement_concentration: float | None = None
    floodplain_exposure: float | None = None
    water_body_proximity: float | None = None
    wash_vulnerability: float | None = None
    exposed_population_proxy: float | None = None
    catchment_population_estimate: float | None = None
    population_proxy_source: str = "fallback_static_proxy"
    flood_indicator_source: str = "rainfall_risk_proxy"
    historical_cases_source: str = "seeded_training_baseline"
    rainfall_source_lineage: dict | None = None
    training_label_source: str = "seeded_mock_baseline"
    training_label_dataset_ref: str | None = None
    training_label_window_id: int | None = None
    training_label_truth_level: str | None = None
    training_label_source_coverage_summary: dict | None = None
    training_label_seeded_demo: bool = True
    population_exposure_feature_mode: str = "fallback_proxy_only"
    population_exposure_truth_summary: dict | None = None
    surveillance_recent_suspected_cases_28d: int = 0
    surveillance_recent_confirmed_cases_28d: int = 0
    surveillance_recent_proxy_cases_28d: int = 0
    surveillance_recent_total_cases_28d: int = 0
    surveillance_active_label_count_28d: int = 0
    surveillance_watch_label_count_28d: int = 0
    surveillance_confirmed_label_window_count_28d: int = 0
    surveillance_suspected_label_window_count_28d: int = 0
    surveillance_proxy_only_label_window_count_28d: int = 0
    surveillance_delayed_or_stale_record_count_28d: int = 0
    surveillance_latest_label_window_ref: str | None = None
    surveillance_latest_label_dataset_ref: str | None = None
    surveillance_latest_label_truth_level: str | None = None
    surveillance_latest_freshness_state: str | None = None
    surveillance_label_truth_state: str = "no_surveillance_label_window"
    surveillance_proxy_only_as_confirmed_allowed: bool = False
    surveillance_display_caveat: str = (
        "Surveillance context may contain confirmed, suspected, proxy, field, or seeded truth. "
        "Proxy-only label windows must not be presented as confirmed outbreak truth."
    )
    surveillance_source_coverage_summary: dict | None = None

    @property
    def exposed_population_proxy_scaled(self) -> float:
        return round(float(self.exposed_population_proxy or 0) / 10000.0, 6)

    @property
    def catchment_population_estimate_scaled(self) -> float:
        return round(float(self.catchment_population_estimate or 0) / 10000.0, 6)


@dataclass
class InferenceDataset:
    rows: list[WardFeatureRow]
    feature_dataset: FeatureDataset | None = None
    rainfall_ingestion_run: IngestionRun | None = None
    population_exposure_feature_dataset: FeatureDataset | None = None
    surveillance_feature_coverage: dict | None = None
    surveillance_truth_gate: dict | None = None


@dataclass
class TrainingDataset:
    rows: list[WardFeatureRow]
    feature_dataset: FeatureDataset | None = None
    surveillance_label_dataset: FeatureDataset | None = None


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
        "population_total": row.population_total,
        "population_density": row.population_density,
        "settlement_concentration": row.settlement_concentration,
        "floodplain_exposure": row.floodplain_exposure,
        "water_body_proximity": row.water_body_proximity,
        "wash_vulnerability": row.wash_vulnerability,
        "exposed_population_proxy": row.exposed_population_proxy,
        "catchment_population_estimate": row.catchment_population_estimate,
        "exposed_population_proxy_scaled": row.exposed_population_proxy_scaled,
        "catchment_population_estimate_scaled": row.catchment_population_estimate_scaled,
        "population_proxy_source": row.population_proxy_source,
        "flood_indicator_source": row.flood_indicator_source,
        "historical_cases_source": row.historical_cases_source,
        "rainfall_source_lineage": row.rainfall_source_lineage or {},
        "training_label_source": row.training_label_source,
        "training_label_dataset_ref": row.training_label_dataset_ref,
        "training_label_window_id": row.training_label_window_id,
        "training_label_truth_level": row.training_label_truth_level,
        "training_label_source_coverage_summary": row.training_label_source_coverage_summary or {},
        "training_label_seeded_demo": row.training_label_seeded_demo,
        "population_exposure_feature_mode": row.population_exposure_feature_mode,
        "population_exposure_truth_summary": row.population_exposure_truth_summary or {},
        "population_exposure_display_caveat": (
            "Population and exposure values may be baselines, spatial aggregations, or proxies; "
            "do not present proxy-only fields as exact census or exposure truth."
        ),
        "surveillance_recent_suspected_cases_28d": row.surveillance_recent_suspected_cases_28d,
        "surveillance_recent_confirmed_cases_28d": row.surveillance_recent_confirmed_cases_28d,
        "surveillance_recent_proxy_cases_28d": row.surveillance_recent_proxy_cases_28d,
        "surveillance_recent_total_cases_28d": row.surveillance_recent_total_cases_28d,
        "surveillance_active_label_count_28d": row.surveillance_active_label_count_28d,
        "surveillance_watch_label_count_28d": row.surveillance_watch_label_count_28d,
        "surveillance_confirmed_label_window_count_28d": row.surveillance_confirmed_label_window_count_28d,
        "surveillance_suspected_label_window_count_28d": row.surveillance_suspected_label_window_count_28d,
        "surveillance_proxy_only_label_window_count_28d": row.surveillance_proxy_only_label_window_count_28d,
        "surveillance_delayed_or_stale_record_count_28d": row.surveillance_delayed_or_stale_record_count_28d,
        "surveillance_latest_label_window_ref": row.surveillance_latest_label_window_ref,
        "surveillance_latest_label_dataset_ref": row.surveillance_latest_label_dataset_ref,
        "surveillance_latest_label_truth_level": row.surveillance_latest_label_truth_level,
        "surveillance_latest_freshness_state": row.surveillance_latest_freshness_state,
        "surveillance_label_truth_state": row.surveillance_label_truth_state,
        "surveillance_proxy_only_as_confirmed_allowed": row.surveillance_proxy_only_as_confirmed_allowed,
        "surveillance_display_caveat": row.surveillance_display_caveat,
        "surveillance_source_coverage_summary": row.surveillance_source_coverage_summary or {},
    }


def _safe_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalised_proxy_ratio(value) -> float | None:
    number = _safe_float(value)
    if number is None:
        return None
    if number > 1.0:
        number = number / 100.0
    return max(0.0, min(0.95, number))


def _combine_source_kinds(*source_kinds: str | None) -> str:
    observed = {source_kind for source_kind in source_kinds if source_kind}
    if observed == {FeatureDataset.SOURCE_KIND_LIVE}:
        return FeatureDataset.SOURCE_KIND_LIVE
    if observed == {FeatureDataset.SOURCE_KIND_SEEDED}:
        return FeatureDataset.SOURCE_KIND_SEEDED
    return FeatureDataset.SOURCE_KIND_HYBRID


def _surveillance_label_training_readiness(label_dataset: FeatureDataset | None) -> dict:
    if label_dataset is None:
        return {
            "ready": False,
            "reason": "missing_surveillance_label_dataset",
            "label_counts": {},
            "row_count": 0,
        }
    rows = list(FeatureDatasetRow.objects.filter(dataset=label_dataset).select_related("ward").order_by("id"))
    label_counts = Counter(row.label for row in rows if row.label in {0, 1})
    lineage = label_dataset.lineage_metadata or {}
    coverage = lineage.get("coverage") or {}
    truth_level_counts = coverage.get("truth_level_counts") or {}
    if label_dataset.source_kind == FeatureDataset.SOURCE_KIND_SEEDED:
        reason = "surveillance_label_dataset_is_seeded"
    elif truth_level_counts.get(SurveillanceTruthLevel.SEEDED_DEMO):
        reason = "surveillance_label_dataset_contains_seeded_demo_truth"
    elif not rows:
        reason = "surveillance_label_dataset_has_no_rows"
    elif any(row.ward_id is None for row in rows):
        reason = "surveillance_label_dataset_has_rows_without_ward_link"
    elif len(label_counts) < 2:
        reason = "surveillance_label_dataset_lacks_positive_and_negative_classes"
    else:
        reason = ""
    return {
        "ready": not reason,
        "reason": reason,
        "label_counts": dict(label_counts),
        "row_count": len(rows),
        "dataset_ref": label_dataset.dataset_ref,
    }


def _truth_state_for_label_truth_level(truth_level: str | None) -> str:
    if truth_level == SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE:
        return "confirmed_surveillance"
    if truth_level == SurveillanceTruthLevel.SUSPECTED_SURVEILLANCE:
        return "suspected_surveillance"
    if truth_level == SurveillanceTruthLevel.PROXY_DIARRHEAL_SIGNAL:
        return "proxy_only_not_confirmed"
    if truth_level == SurveillanceTruthLevel.SEEDED_DEMO:
        return "seeded_demo_not_production_truth"
    if truth_level == SurveillanceTruthLevel.FIELD_SIGNAL_ONLY:
        return "field_signal_only_not_confirmed"
    return "no_surveillance_label_window"


def _training_rows_from_surveillance_label_dataset(
    *,
    label_dataset: FeatureDataset,
    population_exposure_rows_by_ward_id: dict[int, dict],
) -> list[WardFeatureRow]:
    training_rows = []
    label_rows = FeatureDatasetRow.objects.filter(dataset=label_dataset).select_related("ward").order_by("id")
    for label_row in label_rows:
        if label_row.ward is None or label_row.label not in {0, 1}:
            continue
        feature_values = label_row.feature_values or {}
        population_exposure_row = population_exposure_rows_by_ward_id.get(label_row.ward_id, {})
        source_lineage = population_exposure_row.get("source_lineage") or {}
        population_total = population_exposure_row.get("population_total")
        population_proxy = float(population_total or 0.0)
        floodplain_exposure = _normalised_proxy_ratio(population_exposure_row.get("floodplain_exposure"))
        flood_indicator = round(float(floodplain_exposure or 0.0), 3)
        truth_level = feature_values.get("label_truth_level")
        source_coverage_summary = feature_values.get("source_coverage_summary") or {}
        label_window_id = feature_values.get("label_window_id")

        training_rows.append(
            WardFeatureRow(
                ward_id=label_row.ward_id,
                ward_name=label_row.ward_name_snapshot,
                rainfall_mm=0.0,
                flood_indicator=flood_indicator,
                historical_cases=0.0,
                month=label_row.month,
                population_proxy=population_proxy,
                label=label_row.label,
                population_total=population_total,
                population_density=population_exposure_row.get("population_density"),
                settlement_concentration=population_exposure_row.get("settlement_concentration"),
                floodplain_exposure=population_exposure_row.get("floodplain_exposure"),
                water_body_proximity=population_exposure_row.get("water_body_proximity"),
                wash_vulnerability=population_exposure_row.get("wash_vulnerability"),
                exposed_population_proxy=population_exposure_row.get("exposed_population_proxy"),
                catchment_population_estimate=population_exposure_row.get("catchment_population_estimate"),
                population_proxy_source=(
                    "population_baseline_record"
                    if population_total is not None
                    else "population_exposure_unavailable_for_training_row"
                ),
                flood_indicator_source=(
                    "floodplain_exposure_proxy"
                    if floodplain_exposure is not None
                    else "not_available_phase_1_training"
                ),
                historical_cases_source="not_used_phase_1_avoids_label_window_leakage",
                rainfall_source_lineage={
                    "source_available": False,
                    "reason": "phase_1_training_labels_only_no_lead_time_rainfall_window",
                },
                training_label_source="surveillance_label_window",
                training_label_dataset_ref=label_dataset.dataset_ref,
                training_label_window_id=label_window_id,
                training_label_truth_level=truth_level,
                training_label_source_coverage_summary=source_coverage_summary,
                training_label_seeded_demo=truth_level == SurveillanceTruthLevel.SEEDED_DEMO,
                population_exposure_feature_mode=(
                    "source_fed_population_exposure_context"
                    if source_lineage.get("record_count")
                    else "fallback_proxy_only"
                ),
                population_exposure_truth_summary=source_lineage,
                surveillance_recent_suspected_cases_28d=feature_values.get("suspected_case_count", 0),
                surveillance_recent_confirmed_cases_28d=feature_values.get("confirmed_case_count", 0),
                surveillance_recent_proxy_cases_28d=feature_values.get("proxy_case_count", 0),
                surveillance_recent_total_cases_28d=feature_values.get("total_case_count", 0),
                surveillance_active_label_count_28d=1 if feature_values.get("outbreak_label") == "active" else 0,
                surveillance_watch_label_count_28d=1 if feature_values.get("outbreak_label") == "watch" else 0,
                surveillance_confirmed_label_window_count_28d=(
                    1 if truth_level == SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE else 0
                ),
                surveillance_suspected_label_window_count_28d=(
                    1 if truth_level == SurveillanceTruthLevel.SUSPECTED_SURVEILLANCE else 0
                ),
                surveillance_proxy_only_label_window_count_28d=(
                    1 if truth_level == SurveillanceTruthLevel.PROXY_DIARRHEAL_SIGNAL else 0
                ),
                surveillance_latest_label_window_ref=(
                    f"surveillance_label_window:{label_window_id}" if label_window_id else None
                ),
                surveillance_latest_label_dataset_ref=label_dataset.dataset_ref,
                surveillance_latest_label_truth_level=truth_level,
                surveillance_label_truth_state=_truth_state_for_label_truth_level(truth_level),
                surveillance_source_coverage_summary=source_coverage_summary,
            )
        )
    return training_rows


def _rainfall_source_lineage_by_ward_id(ingestion_run: IngestionRun | None) -> dict[int, dict]:
    if ingestion_run is None:
        return {}
    lineage_by_ward_id = {}
    for result in ingestion_run.results or []:
        ward_id = result.get("ward_id")
        if not ward_id:
            continue
        canonical = result.get("canonical_record") or {}
        record_type = result.get("record_type") or canonical.get("record_type") or ""
        fallback_flag = bool(result.get("fallback_flag") or canonical.get("fallback_flag"))
        fallback_reason = result.get("fallback_reason") or canonical.get("fallback_reason") or ""
        forecast_horizon_days = (
            result.get("forecast_horizon_days")
            if result.get("forecast_horizon_days") is not None
            else canonical.get("forecast_horizon_days")
        )
        lead_day = result.get("lead_day") if result.get("lead_day") is not None else canonical.get("lead_day")
        forecast_coverage_days = forecast_horizon_days or lead_day or 0
        lineage = {
            "ingestion_run_id": ingestion_run.id,
            "source": result.get("source"),
            "source_provider": result.get("source") or canonical.get("source_name") or ingestion_run.source_name,
            "source_kind": ingestion_run.source_kind,
            "source_mode": ingestion_run.source_mode,
            "source_timestamp": result.get("source_timestamp"),
            "freshness_state": ingestion_run.freshness_state,
            "record_type": record_type,
            "observed_vs_forecast_source_label": climate_source_label_for_record_type(record_type),
            "issue_time": result.get("issue_time") or canonical.get("issue_time"),
            "valid_date": result.get("valid_date") or canonical.get("valid_date"),
            "lead_day": lead_day,
            "observed_timestamp": result.get("observed_timestamp") or canonical.get("observed_timestamp"),
            "forecast_horizon_days": forecast_horizon_days,
            "quality_flag": result.get("quality_flag") or canonical.get("quality_flag"),
            "fallback_flag": fallback_flag,
            "fallback_reason": fallback_reason,
            "coordinate_source": result.get("coordinate_source") or "",
            "canonical_record_ref": canonical.get("record_ref"),
            "claimed_forecast_horizon_days": DEFAULT_CLAIMED_FORECAST_HORIZON_DAYS,
            "forecast_coverage_days": forecast_coverage_days if record_type == "forecast" else 0,
            "fallback_static_rainfall_used": fallback_flag or record_type == "fallback_static",
        }
        climate_coverage = climate_coverage_from_prediction({"rainfall_source_lineage": lineage})
        lineage.update(
            {
                "forecast_covered_lead_days": climate_coverage["forecast_covered_lead_days"],
                "forecast_missing_lead_days": climate_coverage["forecast_missing_lead_days"],
                "claimed_lead_time_climate_coverage_sufficient": climate_coverage[
                    "claimed_lead_time_climate_coverage_sufficient"
                ],
                "climate_coverage_status": climate_coverage["climate_coverage_status"],
                "climate_coverage_caveats": climate_coverage["climate_coverage_caveats"],
                "climate_source_confidence": climate_coverage["climate_source_confidence"],
                "climate_source_confidence_label": climate_coverage["climate_source_confidence_label"],
                "climate_coverage": climate_coverage,
            }
        )
        lineage_by_ward_id[int(ward_id)] = lineage
    return lineage_by_ward_id


def build_training_feature_dataset(
    month: int,
    *,
    include_seeded_labels_for_simulation: bool = False,
) -> TrainingDataset:
    surveillance_label_dataset = latest_surveillance_label_dataset(dataset_role="training")
    surveillance_lead_time_validation = build_surveillance_lead_time_validation_summary(
        label_dataset=surveillance_label_dataset,
    )
    label_readiness = _surveillance_label_training_readiness(surveillance_label_dataset)
    population_exposure_snapshot = None

    if surveillance_label_dataset and (label_readiness["ready"] or include_seeded_labels_for_simulation):
        label_ward_ids = FeatureDatasetRow.objects.filter(
            dataset=surveillance_label_dataset,
            ward__isnull=False,
        ).values_list("ward_id", flat=True).distinct()
        label_wards = list(Ward.objects.filter(id__in=label_ward_ids).order_by("name"))
        population_exposure_snapshot = build_population_exposure_feature_dataset(label_wards, month=month)
        rows = _training_rows_from_surveillance_label_dataset(
            label_dataset=surveillance_label_dataset,
            population_exposure_rows_by_ward_id=population_exposure_snapshot.rows_by_ward_id,
        )
        source_kind = _combine_source_kinds(
            surveillance_label_dataset.source_kind,
            population_exposure_snapshot.feature_dataset.source_kind,
        )
        source_mode = (
            "surveillance-label-training"
            if label_readiness["ready"]
            else "seeded-surveillance-label-simulation-training"
        )
        surveillance_label_usage = SURVEILLANCE_LABEL_TRAINING_USAGE
    else:
        rows = build_mock_training_rows()
        source_kind = FeatureDataset.SOURCE_KIND_SEEDED
        source_mode = "seeded-training-baseline"
        surveillance_label_usage = (
            SURVEILLANCE_REFERENCE_ONLY_LABEL_USAGE
            if surveillance_label_dataset
            else SEEDED_TRAINING_LABEL_USAGE
        )

    dataset = FeatureDataset.objects.create(
        dataset_ref=f"training-{FEATURE_SCHEMA_VERSION}-month-{month}-{uuid4().hex[:8]}",
        dataset_kind=FeatureDataset.KIND_TRAINING,
        schema_version=FEATURE_SCHEMA_VERSION,
        source_kind=source_kind,
        month=month,
        feature_keys=list(
            dict.fromkeys(
                [
                    *WARD_RISK_FEATURE_KEYS,
                    *POPULATION_EXPOSURE_FEATURE_KEYS,
                    "rainfall_source_lineage",
                    "training_label_source",
                    "training_label_dataset_ref",
                    "training_label_window_id",
                    "training_label_truth_level",
                    "training_label_source_coverage_summary",
                    "training_label_seeded_demo",
                    *WARD_RISK_SURVEILLANCE_CONTEXT_FEATURE_KEYS,
                ]
            )
        ),
        row_count=len(rows),
        lineage_metadata={
            "builder": "build_training_feature_dataset",
            "source_mode": source_mode,
            "training_label_source": (
                "surveillance_label_dataset"
                if surveillance_label_usage == SURVEILLANCE_LABEL_TRAINING_USAGE
                else "seeded_mock_training_rows"
            ),
            "training_label_seeded_demo_row_count": sum(1 for row in rows if row.training_label_seeded_demo),
            "training_label_readiness": label_readiness,
            "population_exposure_dataset_ref": population_exposure_snapshot.feature_dataset.dataset_ref
            if population_exposure_snapshot
            else None,
            "population_exposure_feature_dataset_id": population_exposure_snapshot.feature_dataset.id
            if population_exposure_snapshot
            else None,
            "population_exposure_schema_version": population_exposure_snapshot.feature_dataset.schema_version
            if population_exposure_snapshot
            else None,
            "population_exposure_coverage": (population_exposure_snapshot.feature_dataset.lineage_metadata or {}).get(
                "coverage",
                {},
            )
            if population_exposure_snapshot
            else {},
            "population_exposure_truth_assumptions": (
                population_exposure_snapshot.feature_dataset.lineage_metadata or {}
            ).get("truth_assumptions", {})
            if population_exposure_snapshot
            else {},
            "surveillance_label_dataset_ref": surveillance_label_dataset.dataset_ref
            if surveillance_label_dataset
            else None,
            "surveillance_label_feature_dataset_id": surveillance_label_dataset.id
            if surveillance_label_dataset
            else None,
            "surveillance_label_schema_version": SURVEILLANCE_LABEL_SCHEMA_VERSION,
            "surveillance_label_usage": surveillance_label_usage,
            "surveillance_label_coverage": (surveillance_label_dataset.lineage_metadata or {}).get("coverage", {})
            if surveillance_label_dataset
            else {},
            "surveillance_label_truth_assumptions": (surveillance_label_dataset.lineage_metadata or {}).get(
                "truth_assumptions",
                {},
            )
            if surveillance_label_dataset
            else {},
            "surveillance_feature_schema_version": SURVEILLANCE_FEATURE_SCHEMA_VERSION,
            "surveillance_lead_time_validation": surveillance_lead_time_validation,
            "surveillance_label_truth_gate": surveillance_lead_time_validation["truth_gate"],
            "include_seeded_labels_for_simulation": include_seeded_labels_for_simulation,
        },
    )
    FeatureDatasetRow.objects.bulk_create(
        [
            FeatureDatasetRow(
                dataset=dataset,
                ward_id=row.ward_id if surveillance_label_usage == SURVEILLANCE_LABEL_TRAINING_USAGE else None,
                ward_name_snapshot=row.ward_name,
                month=row.month,
                feature_values=_feature_values_from_row(row),
                label=row.label,
            )
            for row in rows
        ]
    )
    return TrainingDataset(rows=rows, feature_dataset=dataset, surveillance_label_dataset=surveillance_label_dataset)


def build_inference_feature_dataset(wards: Iterable[Ward], month: int) -> InferenceDataset:
    ward_list = list(wards)
    rainfall_rows, ingestion_run = fetch_rainfall_for_wards(ward_list, return_ingestion_run=True)
    rainfall_lineage_by_ward_id = _rainfall_source_lineage_by_ward_id(ingestion_run)
    population_exposure_snapshot = build_population_exposure_feature_dataset(ward_list, month=month)
    surveillance_snapshot = build_surveillance_feature_snapshot(ward_list)

    rows: list[WardFeatureRow] = []

    for idx, ward in enumerate(ward_list, start=1):
        rainfall = rainfall_rows.get(ward.name)
        rainfall_mm = rainfall.rainfall_mm if rainfall else round(45 + (ward.current_risk_score * 90), 2)

        # Keep flood proxy mock-derived for now, but partially shaped by real rainfall.
        current_score = ward.current_risk_score or 0.0
        flood_indicator = round(min(0.95, 0.15 + (rainfall_mm / 150.0) + (current_score * 0.20)), 3)
        historical_cases = max(1, int(round((current_score * 14) + (rainfall_mm / 20.0))))
        population_exposure_row = population_exposure_snapshot.rows_by_ward_id.get(ward.id, {})
        source_lineage = population_exposure_row.get("source_lineage") or {}
        population_proxy = float(population_exposure_row.get("population_total") or (4000 + (idx * 250)))
        population_proxy_source = (
            "population_baseline_record"
            if population_exposure_row.get("population_total") is not None
            else "fallback_static_proxy"
        )
        flood_indicator_source = "rainfall_risk_proxy"
        floodplain_exposure = _normalised_proxy_ratio(population_exposure_row.get("floodplain_exposure"))
        if floodplain_exposure is not None:
            flood_indicator = round(max(flood_indicator, floodplain_exposure), 3)
            flood_indicator_source = "rainfall_risk_proxy_plus_floodplain_exposure_proxy"
        population_exposure_feature_mode = (
            "source_fed_population_exposure_context"
            if source_lineage.get("record_count")
            else "fallback_proxy_only"
        )
        surveillance_row = surveillance_snapshot.rows_by_ward_id.get(ward.id, {})
        surveillance_recent_total_cases = int(surveillance_row.get("surveillance_recent_total_cases_28d") or 0)
        historical_cases_source = "rainfall_risk_proxy"
        if surveillance_recent_total_cases > 0:
            historical_cases = max(historical_cases, surveillance_recent_total_cases)
            historical_cases_source = "canonical_surveillance_records_28d"

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
                population_total=population_exposure_row.get("population_total"),
                population_density=population_exposure_row.get("population_density"),
                settlement_concentration=population_exposure_row.get("settlement_concentration"),
                floodplain_exposure=population_exposure_row.get("floodplain_exposure"),
                water_body_proximity=population_exposure_row.get("water_body_proximity"),
                wash_vulnerability=population_exposure_row.get("wash_vulnerability"),
                exposed_population_proxy=population_exposure_row.get("exposed_population_proxy"),
                catchment_population_estimate=population_exposure_row.get("catchment_population_estimate"),
                population_proxy_source=population_proxy_source,
                flood_indicator_source=flood_indicator_source,
                historical_cases_source=historical_cases_source,
                rainfall_source_lineage=rainfall_lineage_by_ward_id.get(ward.id),
                population_exposure_feature_mode=population_exposure_feature_mode,
                population_exposure_truth_summary=source_lineage,
                surveillance_recent_suspected_cases_28d=surveillance_row.get("surveillance_recent_suspected_cases_28d", 0),
                surveillance_recent_confirmed_cases_28d=surveillance_row.get("surveillance_recent_confirmed_cases_28d", 0),
                surveillance_recent_proxy_cases_28d=surveillance_row.get("surveillance_recent_proxy_cases_28d", 0),
                surveillance_recent_total_cases_28d=surveillance_row.get("surveillance_recent_total_cases_28d", 0),
                surveillance_active_label_count_28d=surveillance_row.get("surveillance_active_label_count_28d", 0),
                surveillance_watch_label_count_28d=surveillance_row.get("surveillance_watch_label_count_28d", 0),
                surveillance_confirmed_label_window_count_28d=surveillance_row.get("surveillance_confirmed_label_window_count_28d", 0),
                surveillance_suspected_label_window_count_28d=surveillance_row.get("surveillance_suspected_label_window_count_28d", 0),
                surveillance_proxy_only_label_window_count_28d=surveillance_row.get("surveillance_proxy_only_label_window_count_28d", 0),
                surveillance_delayed_or_stale_record_count_28d=surveillance_row.get("surveillance_delayed_or_stale_record_count_28d", 0),
                surveillance_latest_label_window_ref=surveillance_row.get("surveillance_latest_label_window_ref"),
                surveillance_latest_label_dataset_ref=surveillance_row.get("surveillance_latest_label_dataset_ref"),
                surveillance_latest_label_truth_level=surveillance_row.get("surveillance_latest_label_truth_level"),
                surveillance_latest_freshness_state=surveillance_row.get("surveillance_latest_freshness_state"),
                surveillance_label_truth_state=surveillance_row.get(
                    "surveillance_label_truth_state",
                    "no_surveillance_label_window",
                ),
                surveillance_proxy_only_as_confirmed_allowed=surveillance_row.get(
                    "surveillance_proxy_only_as_confirmed_allowed",
                    False,
                ),
                surveillance_display_caveat=surveillance_row.get(
                    "surveillance_display_caveat",
                    (
                        "Surveillance context may contain confirmed, suspected, proxy, field, or seeded truth. "
                        "Proxy-only label windows must not be presented as confirmed outbreak truth."
                    ),
                ),
                surveillance_source_coverage_summary=surveillance_row.get("surveillance_source_coverage_summary", {}),
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
        feature_keys=list(
            dict.fromkeys(
                [
                    *WARD_RISK_FEATURE_KEYS,
                    *POPULATION_EXPOSURE_FEATURE_KEYS,
                    "population_proxy_source",
                    "flood_indicator_source",
                    "rainfall_source_lineage",
                    "population_exposure_feature_mode",
                    "population_exposure_truth_summary",
                    "population_exposure_display_caveat",
                    *WARD_RISK_SURVEILLANCE_CONTEXT_FEATURE_KEYS,
                ]
            )
        ),
        row_count=len(rows),
        lineage_metadata={
            "builder": "build_inference_feature_dataset",
            "rainfall_ingestion_run_id": ingestion_run.id if ingestion_run else None,
            "rainfall_source_kind": ingestion_run.source_kind if ingestion_run else None,
            "population_exposure_dataset_ref": population_exposure_snapshot.feature_dataset.dataset_ref,
            "population_exposure_feature_dataset_id": population_exposure_snapshot.feature_dataset.id,
            "population_exposure_schema_version": population_exposure_snapshot.feature_dataset.schema_version,
            "population_exposure_coverage": (population_exposure_snapshot.feature_dataset.lineage_metadata or {}).get("coverage", {}),
            "population_exposure_truth_assumptions": (population_exposure_snapshot.feature_dataset.lineage_metadata or {}).get("truth_assumptions", {}),
            "surveillance_feature_schema_version": SURVEILLANCE_FEATURE_SCHEMA_VERSION,
            "surveillance_feature_coverage": surveillance_snapshot.coverage,
            "surveillance_truth_gate": surveillance_snapshot.truth_gate,
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

    return InferenceDataset(
        rows=rows,
        feature_dataset=dataset,
        rainfall_ingestion_run=ingestion_run,
        population_exposure_feature_dataset=population_exposure_snapshot.feature_dataset,
        surveillance_feature_coverage=surveillance_snapshot.coverage,
        surveillance_truth_gate=surveillance_snapshot.truth_gate,
    )
