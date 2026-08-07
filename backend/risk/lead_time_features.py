from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Iterable
from uuid import uuid4

from django.utils import timezone

from risk.climate_records import enrich_rainfall_result_with_climate_contract
from risk.models import (
    ClimateRecord,
    ClimateRecordType,
    FacilityCatchment,
    FacilityForecast,
    FeatureDataset,
    FeatureDatasetRow,
    HealthFacility,
    IngestionRun,
    RiskScore,
    SurveillanceCaseClass,
    SurveillanceFreshnessState,
    SurveillanceOutbreakLabel,
    SurveillanceRecord,
    SurveillanceSourceKind,
    SurveillanceTruthLevel,
    Ward,
    WardSpatialRelationship,
    WardSpatialRelationshipType,
)
from risk.population_exposure_features import (
    POPULATION_EXPOSURE_FEATURE_KEYS,
    build_population_exposure_feature_dataset,
)
from risk.surveillance_labels import record_is_superseded_by_correction
from risk.truth_policy import require_seeded_truth_allowed


LEAD_TIME_FEATURE_SCHEMA_VERSION = "lead-time-feature-v1"
LEAD_TIME_FEATURE_GENERATION_MODE = "phase_3_spatial_relationship_features_v1"
LEAD_TIME_SOURCE_CUTOFF_POLICY = "exclusive_before_prediction_date_midnight"
LEAD_TIME_RAINFALL_WINDOWS_DAYS = (3, 7, 14)
LEAD_TIME_FORECAST_HORIZON_DAYS = tuple(range(1, 15))
DEFAULT_CLAIMED_FORECAST_HORIZON_DAYS = 14
LEAD_TIME_CLIMATE_COVERAGE_SCHEMA_VERSION = "lead-time-climate-coverage-v1"
LEAD_TIME_SURVEILLANCE_LOOKBACK_DAYS = 28
DEFAULT_HEAVY_RAIN_THRESHOLD_MM = 50.0

LEAD_TIME_FEATURE_KEYS = [
    "prediction_date",
    "source_cutoff_timestamp",
    "source_cutoff_policy",
    "observed_rainfall_total_3d",
    "observed_rainfall_total_7d",
    "observed_rainfall_total_14d",
    "rainfall_total_3d",
    "rainfall_total_7d",
    "rainfall_total_14d",
    "rainfall_local_baseline_mm",
    "rainfall_anomaly_against_local_baseline",
    "heavy_rain_threshold_exceedance_count_14d",
    "days_since_heavy_rain",
    "forecast_rainfall_total_day_1_to_7",
    "forecast_rainfall_total_day_8_to_14",
    "forecast_rainfall_unsplit_aggregate_mm",
    "forecast_coverage_days",
    "forecast_covered_lead_days",
    "forecast_missing_lead_days",
    "forecast_max_lead_day",
    "forecast_horizon_7d_sufficient",
    "forecast_horizon_14d_sufficient",
    "claimed_forecast_horizon_days",
    "claimed_lead_time_climate_coverage_sufficient",
    "climate_coverage_status",
    "climate_coverage_caveats",
    "climate_source_confidence",
    "climate_source_confidence_label",
    "fallback_static_rainfall_used",
    "fallback_static_rainfall_mm",
    "fallback_static_record_count",
    "synthetic_rainfall_fallback_used",
    "synthetic_population_fallback_used",
    "population_baseline_record_ref",
    "population_baseline_record_refs",
    "upstream_or_neighboring_ward_risk_signal",
    "upstream_or_neighboring_ward_count",
    "upstream_or_neighboring_ward_signal_source",
    "spatial_neighbor_ward_count",
    "spatial_neighbor_relationship_types",
    "neighboring_high_risk_ward_count",
    "neighboring_active_outbreak_label_count",
    "neighboring_suspected_case_trend_14d_delta",
    "neighboring_rainfall_anomaly",
    "neighboring_surveillance_record_count",
    "distance_to_nearest_high_risk_ward",
    "distance_to_nearest_facility",
    "catchment_facility_readiness_pressure",
    "catchment_facility_count",
    "catchment_facility_readiness_pressure_source",
    "water_proximity_source_available",
    "water_proximity_spatial_feature_value",
    "surveillance_suspected_cases_28d_before_prediction",
    "surveillance_confirmed_cases_28d_before_prediction",
    "surveillance_proxy_cases_28d_before_prediction",
    "surveillance_total_cases_28d_before_prediction",
    "surveillance_record_count_28d_before_prediction",
    "surveillance_case_trend_14d_delta",
    "surveillance_latest_reporting_period_end",
    *POPULATION_EXPOSURE_FEATURE_KEYS,
    "source_lineage",
    "leakage_proof",
]


@dataclass(frozen=True)
class LeadTimeFeatureDatasetSnapshot:
    feature_dataset: FeatureDataset
    rows_by_ward_prediction_date: dict[tuple[int, str], dict]
    population_exposure_feature_datasets: list[FeatureDataset]


def _normalise_aware(value: datetime) -> datetime:
    if timezone.is_naive(value):
        return timezone.make_aware(value, timezone.get_current_timezone())
    return value


def _prediction_source_cutoff(prediction_date: date) -> datetime:
    return _normalise_aware(datetime.combine(prediction_date, time.min))


def _effective_source_cutoff(prediction_date: date, source_cutoff_as_of: datetime | None = None) -> datetime:
    prediction_cutoff = _prediction_source_cutoff(prediction_date)
    if source_cutoff_as_of is None:
        return prediction_cutoff
    normalised_as_of = _normalise_aware(source_cutoff_as_of)
    return min(prediction_cutoff, normalised_as_of)


def _inclusive_as_of_for_exclusive_cutoff(source_cutoff: datetime) -> datetime:
    return source_cutoff - timedelta(microseconds=1)


def _normalise_prediction_dates(
    *,
    prediction_dates: Iterable[date] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    step_days: int = 1,
) -> list[date]:
    if step_days <= 0:
        raise ValueError("step_days must be greater than zero.")

    supplied_dates = list(prediction_dates or [])
    if supplied_dates:
        return sorted(set(supplied_dates))

    if start_date is None and end_date is None:
        return [timezone.localdate()]
    if start_date is None or end_date is None:
        raise ValueError("Both start_date and end_date are required when prediction_dates are not supplied.")
    if start_date > end_date:
        raise ValueError("start_date cannot be after end_date.")

    dates = []
    current = start_date
    while current <= end_date:
        dates.append(current)
        current = current + timedelta(days=step_days)
    return dates


def _safe_float(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_datetime(value) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return _normalise_aware(value)
    if isinstance(value, str):
        try:
            return _normalise_aware(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            return None
    return None


def _parse_date(value) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _safe_int(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalise_identity(value) -> str:
    return str(value or "").strip().casefold()


def _combine_feature_source_kinds(source_kinds: Iterable[str | None]) -> str:
    observed = {source_kind for source_kind in source_kinds if source_kind}
    if not observed:
        return FeatureDataset.SOURCE_KIND_HYBRID
    if observed == {FeatureDataset.SOURCE_KIND_LIVE}:
        return FeatureDataset.SOURCE_KIND_LIVE
    if observed == {FeatureDataset.SOURCE_KIND_SEEDED}:
        return FeatureDataset.SOURCE_KIND_SEEDED
    return FeatureDataset.SOURCE_KIND_HYBRID


def _feature_source_kind_from_rainfall(source_kind: str | None) -> str:
    if source_kind == IngestionRun.SOURCE_KIND_LIVE:
        return FeatureDataset.SOURCE_KIND_LIVE
    if source_kind == IngestionRun.SOURCE_KIND_SEEDED:
        return FeatureDataset.SOURCE_KIND_SEEDED
    return FeatureDataset.SOURCE_KIND_HYBRID


def _feature_source_kind_from_surveillance(source_kind: str | None) -> str:
    if source_kind == SurveillanceSourceKind.LIVE:
        return FeatureDataset.SOURCE_KIND_LIVE
    if source_kind == SurveillanceSourceKind.SEEDED:
        return FeatureDataset.SOURCE_KIND_SEEDED
    return FeatureDataset.SOURCE_KIND_HYBRID


def _climate_record_from_model(record: ClimateRecord) -> dict:
    raw_payload = record.raw_payload if isinstance(record.raw_payload, dict) else {}
    canonical = raw_payload.get("canonical_record") if isinstance(raw_payload.get("canonical_record"), dict) else {}
    return {
        "storage": "climate_record_table",
        "source_record_ref": f"climate_record:{record.id}",
        "ward_id": record.ward_id,
        "ward_name": record.ward.name if record.ward_id else "",
        "source_ward_name": raw_payload.get("ward_name") or canonical.get("ward_name") or "",
        "ingestion_run_id": record.ingestion_run_id,
        "ingestion_completed_at": _parse_datetime(record.ingestion_run.completed_at),
        "record_type": record.record_type,
        "source_provider": record.source_provider,
        "source_kind": record.source_kind,
        "source_mode": record.source_mode,
        "issue_time": _parse_datetime(record.issue_time),
        "valid_date": record.valid_date,
        "lead_day": record.lead_day,
        "observed_timestamp": _parse_datetime(record.observed_timestamp),
        "forecast_horizon_days": record.forecast_horizon_days or 0,
        "rainfall_mm": _safe_float(record.rainfall_mm),
        "quality_flag": record.quality_flag,
        "fallback_flag": bool(record.fallback_flag),
        "source_run": record.source_run,
        "source_ref": record.source_ref,
        "lineage_metadata": record.lineage_metadata or {},
        "raw_payload": raw_payload,
    }


def _climate_record_from_ingestion_result(
    *,
    ingestion_run: IngestionRun,
    result: dict[str, Any],
    row_index: int,
) -> dict | None:
    enriched = enrich_rainfall_result_with_climate_contract(
        ingestion_run=ingestion_run,
        result=result,
        row_index=row_index,
    )
    ward_id = _safe_int(enriched.get("ward_id"))
    rainfall_mm = _safe_float(enriched.get("rainfall_mm"))
    source_ref = enriched.get("source_ref") or enriched.get("record_ref")
    if ward_id is None or rainfall_mm is None or not source_ref:
        return None

    canonical = enriched.get("canonical_record") if isinstance(enriched.get("canonical_record"), dict) else {}
    lineage_metadata = enriched.get("lineage_metadata")
    if not isinstance(lineage_metadata, dict):
        lineage_metadata = (
            canonical.get("lineage_metadata") if isinstance(canonical.get("lineage_metadata"), dict) else {}
        )

    return {
        "storage": "ingestion_run_json",
        "source_record_ref": f"ingestion_run_result:{ingestion_run.id}:{row_index}",
        "ward_id": ward_id,
        "ward_name": enriched.get("ward_name") or canonical.get("ward_name") or "",
        "source_ward_name": enriched.get("ward_name") or canonical.get("ward_name") or "",
        "ingestion_run_id": ingestion_run.id,
        "ingestion_completed_at": _parse_datetime(ingestion_run.completed_at),
        "record_type": enriched.get("record_type") or canonical.get("record_type") or ClimateRecordType.OBSERVED,
        "source_provider": enriched.get("source") or canonical.get("source_name") or ingestion_run.source_name,
        "source_kind": ingestion_run.source_kind,
        "source_mode": ingestion_run.source_mode,
        "issue_time": _parse_datetime(enriched.get("issue_time") or canonical.get("issue_time")),
        "valid_date": _parse_date(enriched.get("valid_date") or canonical.get("valid_date")),
        "lead_day": _safe_int(
            enriched.get("lead_day") if enriched.get("lead_day") is not None else canonical.get("lead_day")
        ),
        "observed_timestamp": _parse_datetime(
            enriched.get("observed_timestamp") or canonical.get("observed_timestamp")
        ),
        "forecast_horizon_days": _safe_int(
            enriched.get("forecast_horizon_days")
            if enriched.get("forecast_horizon_days") is not None
            else canonical.get("forecast_horizon_days")
        )
        or 0,
        "rainfall_mm": rainfall_mm,
        "quality_flag": enriched.get("quality_flag") or canonical.get("quality_flag") or "unknown",
        "fallback_flag": bool(enriched.get("fallback_flag") or canonical.get("fallback_flag")),
        "source_run": enriched.get("source_run") or canonical.get("source_run") or f"ingestion_run:{ingestion_run.id}",
        "source_ref": source_ref,
        "lineage_metadata": lineage_metadata,
        "raw_payload": enriched,
    }


def _climate_records_by_ward_id(
    *,
    ward_ids: set[int],
    source_cutoff: datetime,
) -> dict[int, list[dict]]:
    records_by_ward_id: dict[int, list[dict]] = defaultdict(list)
    source_refs_seen: set[str] = set()
    ward_names_by_id = dict(Ward.objects.filter(id__in=ward_ids).values_list("id", "name"))

    climate_records = (
        ClimateRecord.objects.filter(
            ward_id__in=ward_ids,
            ingestion_run__run_type=IngestionRun.RUN_TYPE_RAINFALL,
            ingestion_run__completed_at__lt=source_cutoff,
        )
        .select_related("ingestion_run", "ward")
        .order_by("ingestion_run__completed_at", "ingestion_run_id", "id")
    )
    for record in climate_records:
        normalized = _climate_record_from_model(record)
        source_ward_name = _normalise_identity(normalized.get("source_ward_name"))
        if source_ward_name and source_ward_name != _normalise_identity(ward_names_by_id.get(normalized["ward_id"])):
            continue
        records_by_ward_id[normalized["ward_id"]].append(normalized)
        source_refs_seen.add(normalized["source_ref"])

    runs = IngestionRun.objects.filter(
        run_type=IngestionRun.RUN_TYPE_RAINFALL,
        completed_at__lt=source_cutoff,
    ).order_by("completed_at", "id")
    for run in runs:
        results = run.results if isinstance(run.results, list) else []
        for row_index, result in enumerate(results):
            if not isinstance(result, dict):
                continue
            normalized = _climate_record_from_ingestion_result(
                ingestion_run=run,
                result=result,
                row_index=row_index,
            )
            if normalized is None:
                continue
            if normalized["source_ref"] in source_refs_seen or normalized["ward_id"] not in ward_ids:
                continue
            source_ward_name = _normalise_identity(normalized.get("source_ward_name") or normalized.get("ward_name"))
            if source_ward_name and source_ward_name != _normalise_identity(ward_names_by_id.get(normalized["ward_id"])):
                continue
            records_by_ward_id[normalized["ward_id"]].append(normalized)
            source_refs_seen.add(normalized["source_ref"])

    return records_by_ward_id


def _observed_rainfall_observations_from_climate_records(
    *,
    climate_records: list[dict],
    source_cutoff: datetime,
) -> tuple[list[dict], dict]:
    observations = []
    summary = {
        "source_record_count": len(climate_records),
        "observed_source_record_count": 0,
        "records_excluded_after_cutoff": 0,
        "records_excluded_missing_observed_timestamp": 0,
        "records_excluded_fallback_static": 0,
        "records_excluded_non_observed": 0,
    }
    for record in climate_records:
        if record["record_type"] != ClimateRecordType.OBSERVED:
            if record["record_type"] == ClimateRecordType.FALLBACK_STATIC or record.get("fallback_flag"):
                summary["records_excluded_fallback_static"] += 1
            else:
                summary["records_excluded_non_observed"] += 1
            continue

        summary["observed_source_record_count"] += 1
        if record.get("fallback_flag"):
            summary["records_excluded_fallback_static"] += 1
            continue
        observed_at = _parse_datetime(record.get("observed_timestamp"))
        if observed_at is None:
            summary["records_excluded_missing_observed_timestamp"] += 1
            continue
        if observed_at >= source_cutoff:
            summary["records_excluded_after_cutoff"] += 1
            continue
        observations.append(
            {
                "ingestion_run_id": record["ingestion_run_id"],
                "rainfall_mm": record["rainfall_mm"],
                "observed_at": observed_at,
                "source": record["source_provider"],
                "source_kind": record["source_kind"],
                "source_mode": record["source_mode"],
                "freshness_state": (record.get("raw_payload") or {}).get("freshness_state"),
                "fallback_reason": (record.get("raw_payload") or {}).get("fallback_reason") or "",
                "canonical_record_ref": record["source_ref"],
                "source_record_ref": record.get("source_record_ref"),
                "record_type": record["record_type"],
                "quality_flag": record["quality_flag"],
                "storage": record["storage"],
            }
        )
    return observations, summary


def _rainfall_window_features(
    *,
    observations: list[dict],
    prediction_date: date,
    source_cutoff: datetime,
    heavy_rain_threshold_mm: float,
    source_summary: dict | None = None,
) -> tuple[dict, dict]:
    values = {
        "observed_rainfall_total_3d": 0.0,
        "observed_rainfall_total_7d": 0.0,
        "observed_rainfall_total_14d": 0.0,
        "rainfall_total_3d": 0.0,
        "rainfall_total_7d": 0.0,
        "rainfall_total_14d": 0.0,
        "rainfall_local_baseline_mm": 0.0,
        "rainfall_anomaly_against_local_baseline": 0.0,
        "heavy_rain_threshold_exceedance_count_14d": 0,
        "days_since_heavy_rain": None,
    }
    lineage = {
        "window_mode": "trailing_observed_climate_records_before_prediction_date",
        "daily_gauge_claim": False,
        "climate_coverage_schema_version": LEAD_TIME_CLIMATE_COVERAGE_SCHEMA_VERSION,
        "heavy_rain_threshold_mm": heavy_rain_threshold_mm,
        "record_count": len(observations),
        "source_record_count": (source_summary or {}).get("source_record_count", len(observations)),
        "observed_source_record_count": (source_summary or {}).get("observed_source_record_count", len(observations)),
        "records_excluded_after_cutoff": (source_summary or {}).get("records_excluded_after_cutoff", 0),
        "records_excluded_missing_observed_timestamp": (source_summary or {}).get(
            "records_excluded_missing_observed_timestamp",
            0,
        ),
        "records_excluded_fallback_static": (source_summary or {}).get("records_excluded_fallback_static", 0),
        "records_excluded_non_observed": (source_summary or {}).get("records_excluded_non_observed", 0),
        "windows": {},
        "source_kinds": dict(Counter(observation["source_kind"] for observation in observations)),
        "record_type_counts": dict(Counter(observation["record_type"] for observation in observations)),
        "quality_flag_counts": dict(Counter(observation["quality_flag"] for observation in observations)),
        "ingestion_run_ids": sorted({observation["ingestion_run_id"] for observation in observations}),
        "canonical_record_refs": sorted(
            {observation["canonical_record_ref"] for observation in observations if observation["canonical_record_ref"]}
        ),
        "source_record_refs": sorted(
            {observation["source_record_ref"] for observation in observations if observation.get("source_record_ref")}
        ),
        "max_source_timestamp": None,
    }
    if observations:
        lineage["max_source_timestamp"] = max(observation["observed_at"] for observation in observations).isoformat()

    observations = sorted(observations, key=lambda item: (item["observed_at"], item["ingestion_run_id"]))
    observations_before_cutoff = [item for item in observations if item["observed_at"] < source_cutoff]
    for window_days in LEAD_TIME_RAINFALL_WINDOWS_DAYS:
        window_start = source_cutoff - timedelta(days=window_days)
        window_observations = [
            item for item in observations_before_cutoff if window_start <= item["observed_at"] < source_cutoff
        ]
        total = round(sum(item["rainfall_mm"] for item in window_observations), 2)
        values[f"observed_rainfall_total_{window_days}d"] = total
        values[f"rainfall_total_{window_days}d"] = total
        lineage["windows"][f"{window_days}d"] = {
            "window_start_exclusive_policy": window_start.isoformat(),
            "window_end_exclusive": source_cutoff.isoformat(),
            "record_count": len(window_observations),
            "ingestion_run_ids": sorted({item["ingestion_run_id"] for item in window_observations}),
            "source_record_refs": sorted(
                {item["source_record_ref"] for item in window_observations if item.get("source_record_ref")}
            ),
            "source_timestamps": [item["observed_at"].isoformat() for item in window_observations],
        }

    baseline_cutoff = source_cutoff - timedelta(days=max(LEAD_TIME_RAINFALL_WINDOWS_DAYS))
    baseline_observations = [item for item in observations_before_cutoff if item["observed_at"] < baseline_cutoff]
    if not baseline_observations:
        baseline_observations = observations_before_cutoff
    if baseline_observations:
        baseline = round(
            sum(item["rainfall_mm"] for item in baseline_observations) / len(baseline_observations),
            2,
        )
        values["rainfall_local_baseline_mm"] = baseline
        values["rainfall_anomaly_against_local_baseline"] = round(values["rainfall_total_14d"] - baseline, 2)
        lineage["baseline_mode"] = "mean_available_source_observations_before_cutoff"
    else:
        lineage["baseline_mode"] = "insufficient_history_default_zero"

    fourteen_day_start = source_cutoff - timedelta(days=14)
    heavy_observations = [
        item
        for item in observations_before_cutoff
        if fourteen_day_start <= item["observed_at"] < source_cutoff
        and item["rainfall_mm"] >= heavy_rain_threshold_mm
    ]
    values["heavy_rain_threshold_exceedance_count_14d"] = len(heavy_observations)
    if heavy_observations:
        latest_heavy = max(heavy_observations, key=lambda item: item["observed_at"])
        values["days_since_heavy_rain"] = max(0, (prediction_date - latest_heavy["observed_at"].date()).days)

    return values, lineage


def _lineage_metadata(record: dict) -> dict:
    metadata = record.get("lineage_metadata")
    return metadata if isinstance(metadata, dict) else {}


def _parse_valid_dates_from_lineage(record: dict) -> list[date]:
    metadata = _lineage_metadata(record)
    raw_dates = metadata.get("valid_dates") or metadata.get("forecast_valid_dates") or []
    if not isinstance(raw_dates, list):
        return []
    parsed_dates = []
    for item in raw_dates:
        parsed = _parse_date(item)
        if parsed is not None:
            parsed_dates.append(parsed)
    return parsed_dates


def _forecast_record_covered_lead_days(
    *,
    record: dict,
    prediction_date: date,
) -> list[int]:
    metadata = _lineage_metadata(record)
    lead_day = _safe_int(record.get("lead_day"))
    explicit_days = metadata.get("covered_lead_days") or metadata.get("forecast_covered_lead_days")
    if isinstance(explicit_days, list):
        parsed_days = sorted(
            {
                day
                for day in (_safe_int(item) for item in explicit_days)
                if day is not None and day in LEAD_TIME_FORECAST_HORIZON_DAYS
            }
        )
        if parsed_days:
            return parsed_days

    if metadata.get("forecast_value_granularity") == "single_lead_day" and lead_day in LEAD_TIME_FORECAST_HORIZON_DAYS:
        return [lead_day]

    valid_dates = _parse_valid_dates_from_lineage(record)
    if valid_dates:
        return sorted(
            {
                (valid_date - prediction_date).days + 1
                for valid_date in valid_dates
                if (valid_date - prediction_date).days + 1 in LEAD_TIME_FORECAST_HORIZON_DAYS
            }
        )

    valid_date = _parse_date(record.get("valid_date"))
    if valid_date is not None:
        remaining_days = (valid_date - prediction_date).days + 1
        if remaining_days <= 0:
            return []
        horizon_days = _safe_int(record.get("forecast_horizon_days")) or lead_day or remaining_days
        if horizon_days and horizon_days > 1:
            return list(range(1, min(remaining_days, horizon_days, max(LEAD_TIME_FORECAST_HORIZON_DAYS)) + 1))
        if remaining_days in LEAD_TIME_FORECAST_HORIZON_DAYS:
            return [remaining_days]

    if lead_day in LEAD_TIME_FORECAST_HORIZON_DAYS:
        return [lead_day]
    horizon_days = _safe_int(record.get("forecast_horizon_days"))
    if horizon_days:
        return list(range(1, min(horizon_days, max(LEAD_TIME_FORECAST_HORIZON_DAYS)) + 1))
    return []


def _forecast_record_daily_values(record: dict) -> list[float] | None:
    metadata = _lineage_metadata(record)
    raw_values = (
        metadata.get("daily_forecast_values")
        or metadata.get("daily_rainfall_mm")
        or metadata.get("precipitation_values")
    )
    if not isinstance(raw_values, list):
        return None
    values = []
    for item in raw_values:
        value = _safe_float(item)
        if value is None:
            return None
        values.append(value)
    return values


def _forecast_bucket_totals(records: list[dict], covered_days_by_ref: dict[str, list[int]]) -> tuple[dict, dict]:
    totals = {
        "forecast_rainfall_total_day_1_to_7": 0.0,
        "forecast_rainfall_total_day_8_to_14": 0.0,
        "forecast_rainfall_unsplit_aggregate_mm": 0.0,
    }
    lineage = {
        "aggregation_modes": Counter(),
        "unsplit_aggregate_record_refs": [],
        "daily_value_record_refs": [],
    }
    for record in records:
        covered_days = covered_days_by_ref.get(record["source_ref"], [])
        if not covered_days:
            continue
        daily_values = _forecast_record_daily_values(record)
        valid_dates = _parse_valid_dates_from_lineage(record)
        if daily_values is not None and valid_dates and len(daily_values) == len(valid_dates):
            lineage["aggregation_modes"]["daily_values_from_lineage"] += 1
            lineage["daily_value_record_refs"].append(record["source_ref"])
            prediction_date = _parse_date(record.get("prediction_date_for_bucket"))
            if prediction_date is None:
                continue
            for valid_date, rainfall_mm in zip(valid_dates, daily_values):
                lead_from_prediction = (valid_date - prediction_date).days + 1
                if 1 <= lead_from_prediction <= 7:
                    totals["forecast_rainfall_total_day_1_to_7"] += rainfall_mm
                elif 8 <= lead_from_prediction <= 14:
                    totals["forecast_rainfall_total_day_8_to_14"] += rainfall_mm
            continue

        rainfall_mm = _safe_float(record.get("rainfall_mm")) or 0.0
        prediction_date = _parse_date(record.get("prediction_date_for_bucket"))
        valid_date_leads = []
        if prediction_date is not None:
            valid_date_leads = [(valid_date - prediction_date).days + 1 for valid_date in valid_dates]
        if any(lead_day not in LEAD_TIME_FORECAST_HORIZON_DAYS for lead_day in valid_date_leads):
            lineage["aggregation_modes"]["aggregate_includes_dates_outside_prediction_horizon"] += 1
            lineage["unsplit_aggregate_record_refs"].append(record["source_ref"])
            totals["forecast_rainfall_unsplit_aggregate_mm"] += rainfall_mm
            continue

        if len(covered_days) == 1:
            lineage["aggregation_modes"]["single_lead_day_record"] += 1
            if covered_days[0] <= 7:
                totals["forecast_rainfall_total_day_1_to_7"] += rainfall_mm
            else:
                totals["forecast_rainfall_total_day_8_to_14"] += rainfall_mm
        elif max(covered_days) <= 7:
            lineage["aggregation_modes"]["aggregate_within_day_1_to_7"] += 1
            totals["forecast_rainfall_total_day_1_to_7"] += rainfall_mm
        elif min(covered_days) >= 8:
            lineage["aggregation_modes"]["aggregate_within_day_8_to_14"] += 1
            totals["forecast_rainfall_total_day_8_to_14"] += rainfall_mm
        else:
            lineage["aggregation_modes"]["aggregate_crosses_7_day_bucket_boundary"] += 1
            lineage["unsplit_aggregate_record_refs"].append(record["source_ref"])
            totals["forecast_rainfall_unsplit_aggregate_mm"] += rainfall_mm

    return (
        {key: round(value, 2) for key, value in totals.items()},
        {
            **lineage,
            "aggregation_modes": dict(lineage["aggregation_modes"]),
        },
    )


def _forecast_rainfall_features(
    *,
    climate_records: list[dict],
    prediction_date: date,
    source_cutoff: datetime,
    claimed_forecast_horizon_days: int,
) -> tuple[dict, dict]:
    eligible_records = []
    excluded_missing_contract = 0
    excluded_after_cutoff = 0
    excluded_stale_valid_date = 0
    fallback_excluded = 0

    for record in climate_records:
        if record.get("record_type") != ClimateRecordType.FORECAST:
            continue
        if record.get("fallback_flag"):
            fallback_excluded += 1
            continue
        issue_time = _parse_datetime(record.get("issue_time"))
        valid_date = _parse_date(record.get("valid_date"))
        if issue_time is None or valid_date is None or record.get("lead_day") is None:
            excluded_missing_contract += 1
            continue
        if issue_time >= source_cutoff:
            excluded_after_cutoff += 1
            continue
        if valid_date < prediction_date:
            excluded_stale_valid_date += 1
            continue
        record = {**record, "prediction_date_for_bucket": prediction_date.isoformat()}
        eligible_records.append(record)

    if eligible_records:
        latest_issue_time = max(record["issue_time"] for record in eligible_records)
        selected_records = [record for record in eligible_records if record["issue_time"] == latest_issue_time]
    else:
        latest_issue_time = None
        selected_records = []

    covered_days_by_ref = {
        record["source_ref"]: _forecast_record_covered_lead_days(record=record, prediction_date=prediction_date)
        for record in selected_records
    }
    covered_days = sorted(
        {day for days in covered_days_by_ref.values() for day in days if day <= claimed_forecast_horizon_days}
    )
    target_days = list(range(1, claimed_forecast_horizon_days + 1))
    missing_days = [day for day in target_days if day not in set(covered_days)]
    bucket_values, bucket_lineage = _forecast_bucket_totals(selected_records, covered_days_by_ref)
    seven_day_sufficient = all(day in covered_days for day in range(1, 8))
    fourteen_day_sufficient = all(day in covered_days for day in range(1, 15))
    values = {
        **bucket_values,
        "forecast_coverage_days": len(covered_days),
        "forecast_covered_lead_days": covered_days,
        "forecast_missing_lead_days": missing_days,
        "forecast_max_lead_day": max(covered_days, default=0),
        "forecast_horizon_7d_sufficient": seven_day_sufficient,
        "forecast_horizon_14d_sufficient": fourteen_day_sufficient,
        "claimed_forecast_horizon_days": claimed_forecast_horizon_days,
        "claimed_lead_time_climate_coverage_sufficient": not missing_days and bool(selected_records),
    }
    lineage = {
        "coverage_schema_version": LEAD_TIME_CLIMATE_COVERAGE_SCHEMA_VERSION,
        "record_count": len(eligible_records),
        "selected_record_count": len(selected_records),
        "selected_issue_time": latest_issue_time.isoformat() if latest_issue_time else None,
        "claimed_forecast_horizon_days": claimed_forecast_horizon_days,
        "covered_lead_days": covered_days,
        "missing_lead_days": missing_days,
        "source_refs": [record["source_ref"] for record in selected_records],
        "source_providers": sorted(
            {record["source_provider"] for record in selected_records if record.get("source_provider")}
        ),
        "source_kinds": dict(
            Counter(record["source_kind"] for record in selected_records if record.get("source_kind"))
        ),
        "quality_flag_counts": dict(
            Counter(record["quality_flag"] for record in selected_records if record.get("quality_flag"))
        ),
        "max_forecast_horizon_days": max(
            (_safe_int(record.get("forecast_horizon_days")) or 0 for record in selected_records),
            default=0,
        ),
        "max_contract_lead_day": max(
            (_safe_int(record.get("lead_day")) or 0 for record in selected_records),
            default=0,
        ),
        "records_excluded_missing_contract": excluded_missing_contract,
        "records_excluded_issue_time_after_cutoff": excluded_after_cutoff,
        "records_excluded_stale_valid_date": excluded_stale_valid_date,
        "fallback_records_excluded_from_forecast_features": fallback_excluded,
        **bucket_lineage,
    }
    return values, lineage


def _fallback_static_rainfall_features(climate_records: list[dict]) -> tuple[dict, dict]:
    fallback_records = [
        record
        for record in climate_records
        if record.get("record_type") == ClimateRecordType.FALLBACK_STATIC or record.get("fallback_flag")
    ]
    latest_record = None
    if fallback_records:
        latest_record = max(
            fallback_records,
            key=lambda record: (
                _parse_datetime(record.get("ingestion_completed_at"))
                or datetime.min.replace(tzinfo=timezone.get_current_timezone()),
                record.get("source_ref") or "",
            ),
        )
    values = {
        "fallback_static_rainfall_used": bool(fallback_records),
        "fallback_static_rainfall_mm": latest_record["rainfall_mm"] if latest_record else None,
        "fallback_static_record_count": len(fallback_records),
    }
    lineage = {
        "record_count": len(fallback_records),
        "source_refs": [record["source_ref"] for record in fallback_records],
        "source_providers": sorted(
            {record["source_provider"] for record in fallback_records if record.get("source_provider")}
        ),
        "source_kinds": dict(
            Counter(record["source_kind"] for record in fallback_records if record.get("source_kind"))
        ),
        "quality_flag_counts": dict(
            Counter(record["quality_flag"] for record in fallback_records if record.get("quality_flag"))
        ),
        "latest_source_ref": latest_record["source_ref"] if latest_record else None,
    }
    return values, lineage


def _confidence_label(score: float) -> str:
    if score >= 0.85:
        return "high"
    if score >= 0.6:
        return "moderate"
    if score >= 0.35:
        return "limited"
    if score > 0:
        return "fallback_only"
    return "unavailable"


def _climate_coverage_features(
    *,
    observed_lineage: dict,
    forecast_values: dict,
    forecast_lineage: dict,
    fallback_values: dict,
) -> tuple[dict, dict]:
    caveats = []
    observed_count = observed_lineage.get("record_count", 0)
    forecast_count = forecast_lineage.get("selected_record_count", 0)
    fallback_used = bool(fallback_values.get("fallback_static_rainfall_used"))
    missing_days = forecast_values.get("forecast_missing_lead_days") or []
    unsplit_aggregate_mm = _safe_float(forecast_values.get("forecast_rainfall_unsplit_aggregate_mm")) or 0.0

    if observed_count == 0:
        caveats.append("no_observed_rainfall_records_before_prediction_cutoff")
    if forecast_count == 0:
        caveats.append("no_forecast_records_available_before_prediction_cutoff")
    if missing_days:
        caveats.append("forecast_missing_claimed_lead_days")
    if fallback_used:
        caveats.append("fallback_static_rainfall_present_not_live_forecast")
    if unsplit_aggregate_mm > 0:
        caveats.append("forecast_rainfall_aggregate_not_split_into_7_day_buckets")

    coverage_sufficient = bool(forecast_values.get("claimed_lead_time_climate_coverage_sufficient"))
    if coverage_sufficient and observed_count > 0 and not fallback_used:
        score = 1.0
    elif coverage_sufficient:
        score = 0.85
    elif forecast_values.get("forecast_horizon_7d_sufficient") and not fallback_used:
        score = 0.7
    elif forecast_count:
        score = 0.55
    elif observed_count:
        score = 0.45
    elif fallback_used:
        score = 0.2
    else:
        score = 0.0
    if fallback_used and not coverage_sufficient:
        score = min(score, 0.4)
    elif fallback_used:
        score = min(score, 0.75)

    status = "sufficient" if coverage_sufficient else "insufficient_forecast_horizon"
    values = {
        "climate_coverage_status": status,
        "climate_coverage_caveats": caveats,
        "climate_source_confidence": round(score, 2),
        "climate_source_confidence_label": _confidence_label(score),
    }
    lineage = {
        "coverage_schema_version": LEAD_TIME_CLIMATE_COVERAGE_SCHEMA_VERSION,
        "observed_record_count": observed_count,
        "forecast_record_count": forecast_count,
        "fallback_static_rainfall_used": fallback_used,
        "claimed_forecast_horizon_days": forecast_values.get("claimed_forecast_horizon_days"),
        "claimed_lead_time_climate_coverage_sufficient": coverage_sufficient,
        "caveats": caveats,
        "confidence_policy": "rule_based_source_separation_and_forecast_horizon_coverage_v1",
    }
    return values, lineage


def _surveillance_records_by_ward_id(
    *,
    ward_ids: set[int],
    prediction_date: date,
    source_cutoff: datetime,
    lookback_days: int,
    include_seeded_surveillance: bool,
) -> dict[int, list[SurveillanceRecord]]:
    lookback_start = prediction_date - timedelta(days=lookback_days)
    queryset = (
        SurveillanceRecord.objects.filter(
            ward_id__in=ward_ids,
            created_at__lt=source_cutoff,
            reporting_period_end__lt=prediction_date,
            reporting_period_end__gte=lookback_start,
        )
        .exclude(freshness_state=SurveillanceFreshnessState.REPLAY_DIAGNOSTIC)
        .select_related("source", "ingestion_run", "ward")
        .order_by("ward_id", "reporting_period_end", "id")
    )
    if not include_seeded_surveillance:
        queryset = queryset.exclude(truth_level=SurveillanceTruthLevel.SEEDED_DEMO)

    records_by_ward_id: dict[int, list[SurveillanceRecord]] = defaultdict(list)
    for record in queryset:
        if record_is_superseded_by_correction(record):
            continue
        records_by_ward_id[record.ward_id].append(record)
    return records_by_ward_id


def _surveillance_trend_features(
    *,
    records: list[SurveillanceRecord],
    prediction_date: date,
) -> tuple[dict, dict]:
    suspected = sum(record.count_value for record in records if record.case_class == SurveillanceCaseClass.SUSPECTED)
    confirmed = sum(record.count_value for record in records if record.case_class == SurveillanceCaseClass.CONFIRMED)
    proxy = sum(record.count_value for record in records if record.case_class == SurveillanceCaseClass.PROXY)
    recent_start = prediction_date - timedelta(days=14)
    previous_start = prediction_date - timedelta(days=28)
    recent_total = sum(record.count_value for record in records if recent_start <= record.reporting_period_end < prediction_date)
    previous_total = sum(record.count_value for record in records if previous_start <= record.reporting_period_end < recent_start)
    latest_reporting_end = max((record.reporting_period_end for record in records), default=None)
    latest_created_at = max((record.created_at for record in records), default=None)

    values = {
        "surveillance_suspected_cases_28d_before_prediction": suspected,
        "surveillance_confirmed_cases_28d_before_prediction": confirmed,
        "surveillance_proxy_cases_28d_before_prediction": proxy,
        "surveillance_total_cases_28d_before_prediction": suspected + confirmed + proxy,
        "surveillance_record_count_28d_before_prediction": len(records),
        "surveillance_case_trend_14d_delta": recent_total - previous_total,
        "surveillance_latest_reporting_period_end": latest_reporting_end.isoformat() if latest_reporting_end else None,
    }
    lineage = {
        "record_count": len(records),
        "source_names": sorted({record.source_name for record in records if record.source_name}),
        "source_refs": sorted({record.source_ref for record in records if record.source_ref}),
        "source_kinds": dict(Counter(record.source_kind for record in records if record.source_kind)),
        "truth_level_counts": dict(Counter(record.truth_level for record in records if record.truth_level)),
        "freshness_state_counts": dict(Counter(record.freshness_state for record in records if record.freshness_state)),
        "case_class_counts": dict(Counter(record.case_class for record in records if record.case_class)),
        "source_record_refs": [f"surveillance_record:{record.id}" for record in records],
        "max_reporting_period_end": latest_reporting_end.isoformat() if latest_reporting_end else None,
        "max_record_created_at": latest_created_at.isoformat() if latest_created_at else None,
    }
    return values, lineage


SPATIAL_NEIGHBOR_RELATIONSHIP_TYPES = {
    WardSpatialRelationshipType.ADJACENT,
    WardSpatialRelationshipType.NEARBY,
    WardSpatialRelationshipType.UPSTREAM,
    WardSpatialRelationshipType.SAME_FACILITY_CATCHMENT,
    WardSpatialRelationshipType.MANUAL_PUBLIC_HEALTH_LINK,
}


def _spatial_relationships_by_source_ward_id(
    *,
    ward_ids: set[int],
    source_cutoff: datetime,
) -> dict[int, list[WardSpatialRelationship]]:
    relationships_by_ward_id: dict[int, list[WardSpatialRelationship]] = defaultdict(list)
    queryset = (
        WardSpatialRelationship.objects.filter(
            source_ward_id__in=ward_ids,
            target_ward__is_active=True,
            relationship_type__in=SPATIAL_NEIGHBOR_RELATIONSHIP_TYPES,
            geometry_dataset_version__is_active=True,
            geometry_dataset_version__dataset__is_active=True,
            generated_at__lt=source_cutoff,
        )
        .select_related("target_ward", "geometry_dataset_version", "geometry_dataset_version__dataset")
        .order_by("source_ward_id", "relationship_type", "target_ward__name", "id")
    )
    for relationship in queryset:
        if relationship.source_ward_id == relationship.target_ward_id:
            continue
        relationships_by_ward_id[relationship.source_ward_id].append(relationship)
    return relationships_by_ward_id


def _latest_risk_scores_by_ward_id(*, ward_ids: set[int], source_cutoff: datetime) -> dict[int, RiskScore]:
    latest_by_ward_id: dict[int, RiskScore] = {}
    if not ward_ids:
        return latest_by_ward_id
    queryset = (
        RiskScore.objects.filter(
            ward_id__in=ward_ids,
            generated_at__lt=source_cutoff,
        )
        .select_related("ward", "model_run")
        .order_by("ward_id", "-generated_at", "-id")
    )
    for score in queryset:
        latest_by_ward_id.setdefault(score.ward_id, score)
    return latest_by_ward_id


def _neighbor_risk_features(
    ward: Ward,
    source_cutoff: datetime,
    *,
    spatial_relationships: list[WardSpatialRelationship] | None = None,
) -> tuple[dict, dict]:
    spatial_relationships = spatial_relationships or []
    if spatial_relationships:
        neighbor_ids = {relationship.target_ward_id for relationship in spatial_relationships}
        latest_by_ward_id = _latest_risk_scores_by_ward_id(ward_ids=neighbor_ids, source_cutoff=source_cutoff)
        peer_scores = [latest_by_ward_id[ward_id] for ward_id in sorted(latest_by_ward_id)]
        high_risk_scores = [
            score for score in peer_scores if score.risk_level == Ward.RISK_HIGH
        ]
        high_risk_ward_ids = {score.ward_id for score in high_risk_scores}
        high_risk_distances = [
            relationship.centroid_distance
            for relationship in spatial_relationships
            if relationship.target_ward_id in high_risk_ward_ids and relationship.centroid_distance is not None
        ]
        average_score = round(sum(score.score for score in peer_scores) / len(peer_scores), 6) if peer_scores else None
        relationship_type_counts = Counter(relationship.relationship_type for relationship in spatial_relationships)
        return (
            {
                "upstream_or_neighboring_ward_risk_signal": average_score,
                "upstream_or_neighboring_ward_count": len(neighbor_ids),
                "upstream_or_neighboring_ward_signal_source": (
                    "ward_spatial_relationship_graph_latest_risk_scores_before_cutoff"
                    if peer_scores
                    else "ward_spatial_relationship_graph_no_neighbor_risk_scores_before_cutoff"
                ),
                "spatial_neighbor_ward_count": len(neighbor_ids),
                "spatial_neighbor_relationship_types": sorted(relationship_type_counts),
                "neighboring_high_risk_ward_count": len(high_risk_scores),
                "distance_to_nearest_high_risk_ward": min(high_risk_distances) if high_risk_distances else None,
            },
            {
                "risk_score_count": len(peer_scores),
                "source_mode": "ward_spatial_relationship_graph",
                "relationship_count": len(spatial_relationships),
                "relationship_refs": [f"ward_spatial_relationship:{relationship.id}" for relationship in spatial_relationships],
                "relationship_type_counts": dict(relationship_type_counts),
                "neighbor_ward_ids": sorted(neighbor_ids),
                "neighbor_ward_names": sorted(
                    relationship.target_ward.name for relationship in spatial_relationships
                ),
                "risk_score_refs": [f"risk_score:{score.id}" for score in peer_scores],
                "high_risk_ward_ids": sorted(high_risk_ward_ids),
                "model_run_refs": [
                    f"model_run:{score.model_run_id}" for score in peer_scores if score.model_run_id is not None
                ],
                "max_generated_at": max((score.generated_at for score in peer_scores), default=None).isoformat()
                if peer_scores
                else None,
                "source_cutoff_timestamp": source_cutoff.isoformat(),
                "relationship_cutoff_filter": f"generated_at < {source_cutoff.isoformat()}",
            },
        )

    return (
        {
            "upstream_or_neighboring_ward_risk_signal": None,
            "upstream_or_neighboring_ward_count": 0,
            "upstream_or_neighboring_ward_signal_source": "unavailable_no_spatial_relationships_before_cutoff",
            "spatial_neighbor_ward_count": 0,
            "spatial_neighbor_relationship_types": [],
            "neighboring_high_risk_ward_count": 0,
            "distance_to_nearest_high_risk_ward": None,
        },
        {
            "risk_score_count": 0,
            "source_mode": "unavailable_no_spatial_relationships_before_cutoff",
            "risk_score_refs": [],
            "relationship_count": 0,
            "relationship_refs": [],
            "neighbor_ward_ids": [],
            "neighbor_ward_names": [],
            "source_cutoff_timestamp": source_cutoff.isoformat(),
        },
    )


def _neighbor_surveillance_features(
    *,
    neighbor_ward_ids: set[int],
    surveillance_by_ward_id: dict[int, list[SurveillanceRecord]],
    prediction_date: date,
) -> tuple[dict, dict]:
    records = [
        record
        for ward_id in sorted(neighbor_ward_ids)
        for record in surveillance_by_ward_id.get(ward_id, [])
    ]
    recent_start = prediction_date - timedelta(days=14)
    previous_start = prediction_date - timedelta(days=28)
    recent_suspected = sum(
        record.count_value
        for record in records
        if record.case_class == SurveillanceCaseClass.SUSPECTED
        and recent_start <= record.reporting_period_end < prediction_date
    )
    previous_suspected = sum(
        record.count_value
        for record in records
        if record.case_class == SurveillanceCaseClass.SUSPECTED
        and previous_start <= record.reporting_period_end < recent_start
    )
    active_outbreak_ward_ids = {
        record.ward_id for record in records if record.outbreak_label == SurveillanceOutbreakLabel.ACTIVE
    }
    latest_reporting_end = max((record.reporting_period_end for record in records), default=None)
    latest_created_at = max((record.created_at for record in records), default=None)
    return (
        {
            "neighboring_active_outbreak_label_count": len(active_outbreak_ward_ids),
            "neighboring_suspected_case_trend_14d_delta": recent_suspected - previous_suspected,
            "neighboring_surveillance_record_count": len(records),
        },
        {
            "record_count": len(records),
            "neighbor_ward_ids": sorted(neighbor_ward_ids),
            "active_outbreak_ward_ids": sorted(active_outbreak_ward_ids),
            "source_names": sorted({record.source_name for record in records if record.source_name}),
            "source_refs": sorted({record.source_ref for record in records if record.source_ref}),
            "source_kinds": dict(Counter(record.source_kind for record in records if record.source_kind)),
            "truth_level_counts": dict(Counter(record.truth_level for record in records if record.truth_level)),
            "case_class_counts": dict(Counter(record.case_class for record in records if record.case_class)),
            "outbreak_label_counts": dict(Counter(record.outbreak_label for record in records if record.outbreak_label)),
            "source_record_refs": [f"surveillance_record:{record.id}" for record in records],
            "max_reporting_period_end": latest_reporting_end.isoformat() if latest_reporting_end else None,
            "max_record_created_at": latest_created_at.isoformat() if latest_created_at else None,
            "cutoff_policy": "records_created_before_cutoff_and_reporting_period_end_before_prediction_date",
        },
    )


def _neighbor_climate_features(
    *,
    neighbor_ward_ids: set[int],
    climate_records_by_ward_id: dict[int, list[dict]],
    prediction_date: date,
    source_cutoff: datetime,
    heavy_rain_threshold_mm: float,
) -> tuple[dict, dict]:
    ward_summaries = []
    anomalies = []
    source_timestamps = []
    source_kind_counter = Counter()
    source_record_refs = []
    for ward_id in sorted(neighbor_ward_ids):
        climate_records = climate_records_by_ward_id.get(ward_id, [])
        observations, source_summary = _observed_rainfall_observations_from_climate_records(
            climate_records=climate_records,
            source_cutoff=source_cutoff,
        )
        rainfall_values, rainfall_lineage = _rainfall_window_features(
            observations=observations,
            prediction_date=prediction_date,
            source_cutoff=source_cutoff,
            heavy_rain_threshold_mm=heavy_rain_threshold_mm,
            source_summary=source_summary,
        )
        if rainfall_lineage.get("record_count", 0) > 0:
            anomalies.append(rainfall_values["rainfall_anomaly_against_local_baseline"])
        max_source_timestamp = _parse_datetime(rainfall_lineage.get("max_source_timestamp"))
        if max_source_timestamp is not None:
            source_timestamps.append(max_source_timestamp)
        source_kind_counter.update(rainfall_lineage.get("source_kinds") or {})
        source_record_refs.extend(rainfall_lineage.get("source_record_refs") or [])
        ward_summaries.append(
            {
                "ward_id": ward_id,
                "observed_record_count": rainfall_lineage.get("record_count", 0),
                "rainfall_total_14d": rainfall_values["rainfall_total_14d"],
                "rainfall_anomaly_against_local_baseline": rainfall_values[
                    "rainfall_anomaly_against_local_baseline"
                ],
                "source_record_count": rainfall_lineage.get("source_record_count", 0),
                "source_record_refs": rainfall_lineage.get("source_record_refs") or [],
            }
        )

    anomaly = round(sum(anomalies) / len(anomalies), 2) if anomalies else 0.0
    return (
        {
            "neighboring_rainfall_anomaly": anomaly,
        },
        {
            "neighbor_ward_ids": sorted(neighbor_ward_ids),
            "neighbor_ward_count": len(neighbor_ward_ids),
            "neighbor_wards_with_observed_rainfall": len(anomalies),
            "aggregation_mode": "mean_neighbor_rainfall_anomaly_against_each_ward_local_baseline",
            "source_kinds": dict(source_kind_counter),
            "ward_summaries": ward_summaries,
            "source_record_refs": sorted(set(source_record_refs)),
            "max_source_timestamp": max(source_timestamps).isoformat() if source_timestamps else None,
            "source_cutoff_timestamp": source_cutoff.isoformat(),
        },
    )


def _ward_centroid(ward: Ward):
    if ward.centroid is not None:
        return ward.centroid
    if ward.boundary is not None:
        return ward.boundary.centroid
    return None


def _distance_to_nearest_facility_feature(ward: Ward, source_cutoff: datetime) -> tuple[dict, dict]:
    ward_centroid = _ward_centroid(ward)
    if ward_centroid is None:
        return (
            {"distance_to_nearest_facility": None},
            {
                "source_mode": "unavailable_ward_centroid_missing",
                "source_cutoff_timestamp": source_cutoff.isoformat(),
                "facility_refs": [],
            },
        )
    facilities = list(
        HealthFacility.objects.filter(
            is_active=True,
            point__isnull=False,
            ward__county__iexact=ward.county,
            created_at__lt=source_cutoff,
        )
        .select_related("ward")
        .order_by("ward__name", "name", "id")
    )
    distances = [
        (float(ward_centroid.distance(facility.point)), facility)
        for facility in facilities
        if facility.point is not None
    ]
    if not distances:
        return (
            {"distance_to_nearest_facility": None},
            {
                "source_mode": "unavailable_no_facility_coordinates",
                "source_cutoff_timestamp": source_cutoff.isoformat(),
                "facility_refs": [],
            },
        )
    distance, facility = min(distances, key=lambda item: (item[0], item[1].id))
    return (
        {"distance_to_nearest_facility": distance},
        {
            "source_mode": "active_facility_points_same_county",
            "distance_unit": "source_crs_degrees",
            "source_cutoff_timestamp": source_cutoff.isoformat(),
            "nearest_facility_id": facility.id,
            "nearest_facility_name": facility.name,
            "nearest_facility_code": facility.facility_code,
            "facility_refs": [f"health_facility:{facility.id}"],
            "max_facility_created_at": facility.created_at.isoformat() if facility.created_at else None,
        },
    )


def _latest_facility_forecasts_by_facility_id(
    *,
    facility_ids: set[int],
    source_cutoff: datetime,
) -> dict[int, FacilityForecast]:
    latest_by_facility_id: dict[int, FacilityForecast] = {}
    if not facility_ids:
        return latest_by_facility_id
    forecasts = (
        FacilityForecast.objects.filter(
            facility_id__in=facility_ids,
            generated_at__lt=source_cutoff,
        )
        .select_related("facility", "forecast_run")
        .order_by("facility_id", "-generated_at", "-id")
    )
    for forecast in forecasts:
        latest_by_facility_id.setdefault(forecast.facility_id, forecast)
    return latest_by_facility_id


def _catchment_facility_pressure_features(
    *,
    ward: Ward,
    source_cutoff: datetime,
) -> tuple[dict, dict]:
    catchments = list(
        FacilityCatchment.objects.filter(
            covered_wards=ward,
            facility__is_active=True,
            geometry_dataset_version__is_active=True,
            geometry_dataset_version__dataset__is_active=True,
            generated_at__lt=source_cutoff,
        )
        .select_related("facility", "primary_ward", "geometry_dataset_version", "geometry_dataset_version__dataset")
        .prefetch_related("covered_wards")
        .distinct()
        .order_by("facility__name", "id")
    )
    facility_ids = {catchment.facility_id for catchment in catchments}
    forecasts_by_facility_id = _latest_facility_forecasts_by_facility_id(
        facility_ids=facility_ids,
        source_cutoff=source_cutoff,
    )
    forecasts = list(forecasts_by_facility_id.values())
    pressure = max((forecast.projected_pressure_score for forecast in forecasts), default=None)
    if pressure is None and catchments:
        source = "facility_catchments_without_forecast_before_cutoff"
    elif pressure is None:
        source = "unavailable_no_facility_catchment_before_cutoff"
    else:
        source = "facility_catchments_with_latest_forecast_before_cutoff"

    return (
        {
            "catchment_facility_readiness_pressure": pressure,
            "catchment_facility_count": len(facility_ids),
            "catchment_facility_readiness_pressure_source": source,
        },
        {
            "source_mode": source,
            "source_cutoff_timestamp": source_cutoff.isoformat(),
            "catchment_count": len(catchments),
            "facility_count": len(facility_ids),
            "catchment_refs": [f"facility_catchment:{catchment.id}" for catchment in catchments],
            "facility_refs": [f"health_facility:{facility_id}" for facility_id in sorted(facility_ids)],
            "forecast_refs": [f"facility_forecast:{forecast.id}" for forecast in forecasts],
            "max_catchment_generated_at": max(
                (catchment.generated_at for catchment in catchments),
                default=None,
            ).isoformat()
            if catchments
            else None,
            "max_forecast_generated_at": max((forecast.generated_at for forecast in forecasts), default=None).isoformat()
            if forecasts
            else None,
            "approximate_catchment_count": sum(1 for catchment in catchments if catchment.is_approximate),
            "catchment_methods": dict(Counter(catchment.catchment_method for catchment in catchments)),
            "readiness_state_counts": dict(
                Counter(forecast.projected_readiness_state for forecast in forecasts)
            ),
            "max_projected_pressure_score": pressure,
        },
    )


def _water_proximity_features(population_values: dict) -> tuple[dict, dict]:
    value = population_values.get("water_body_proximity")
    exposure_record_ids = population_values.get("exposure_record_ids") or {}
    water_record_id = exposure_record_ids.get("water_body_proximity")
    return (
        {
            "water_proximity_source_available": value is not None,
            "water_proximity_spatial_feature_value": value,
        },
        {
            "source_mode": "population_exposure_water_body_proximity",
            "source_available": value is not None,
            "exposure_record_ref": f"exposure_feature_record:{water_record_id}" if water_record_id else None,
            "display_caveat": "Water proximity is a ward-level exposure feature where source data exists.",
        },
    )


def _row_leakage_proof(
    *,
    prediction_date: date,
    source_cutoff: datetime,
    population_as_of: datetime,
    rainfall_lineage: dict,
    forecast_lineage: dict,
    surveillance_lineage: dict,
    spatial_lineage: dict | None = None,
) -> dict:
    rainfall_timestamp = _parse_datetime(rainfall_lineage.get("max_source_timestamp"))
    forecast_issue_time = _parse_datetime(forecast_lineage.get("selected_issue_time"))
    surveillance_created_at = _parse_datetime(surveillance_lineage.get("max_record_created_at"))
    max_reporting_end = surveillance_lineage.get("max_reporting_period_end")
    reporting_period_passes = max_reporting_end is None or max_reporting_end < prediction_date.isoformat()
    source_timestamp_passes = all(
        timestamp is None or timestamp < source_cutoff
        for timestamp in (rainfall_timestamp, forecast_issue_time, surveillance_created_at)
    )
    spatial_lineage = spatial_lineage or {}
    spatial_relationship_generated_at = _parse_datetime(spatial_lineage.get("max_relationship_generated_at"))
    catchment_generated_at = _parse_datetime(spatial_lineage.get("max_catchment_generated_at"))
    facility_forecast_generated_at = _parse_datetime(spatial_lineage.get("max_facility_forecast_generated_at"))
    neighbor_surveillance_created_at = _parse_datetime(
        spatial_lineage.get("max_neighbor_surveillance_record_created_at")
    )
    neighbor_risk_generated_at = _parse_datetime(spatial_lineage.get("max_neighbor_risk_generated_at"))
    neighbor_climate_source_timestamp = _parse_datetime(spatial_lineage.get("max_neighbor_climate_source_timestamp"))
    nearest_facility_created_at = _parse_datetime(spatial_lineage.get("max_nearest_facility_created_at"))
    max_neighbor_reporting_end = spatial_lineage.get("max_neighbor_surveillance_reporting_period_end")
    neighbor_reporting_period_passes = (
        max_neighbor_reporting_end is None or max_neighbor_reporting_end < prediction_date.isoformat()
    )
    spatial_timestamp_passes = all(
        timestamp is None or timestamp < source_cutoff
        for timestamp in (
            spatial_relationship_generated_at,
            catchment_generated_at,
            facility_forecast_generated_at,
            neighbor_surveillance_created_at,
            neighbor_risk_generated_at,
            neighbor_climate_source_timestamp,
            nearest_facility_created_at,
        )
    )
    return {
        "future_label_data_used": False,
        "label_windows_used_as_input": False,
        "label_window_feature_policy": "surveillance_label_windows_are_not_queried_by_phase_3_feature_builder",
        "future_observed_climate_used": bool(rainfall_timestamp is not None and rainfall_timestamp >= source_cutoff),
        "forecast_issue_time_after_cutoff_used": bool(
            forecast_issue_time is not None and forecast_issue_time >= source_cutoff
        ),
        "source_cutoff_timestamp": source_cutoff.isoformat(),
        "source_cutoff_policy": LEAD_TIME_SOURCE_CUTOFF_POLICY,
        "population_exposure_as_of": population_as_of.isoformat(),
        "surveillance_filter": {
            "created_at": f"< {source_cutoff.isoformat()}",
            "reporting_period_end": f"< {prediction_date.isoformat()}",
        },
        "neighbor_surveillance_filter": {
            "created_at": f"< {source_cutoff.isoformat()}",
            "reporting_period_end": f"< {prediction_date.isoformat()}",
        },
        "rainfall_filter": {
            "completed_at": f"< {source_cutoff.isoformat()}",
            "source_timestamp": f"< {source_cutoff.isoformat()}",
        },
        "max_rainfall_source_timestamp": rainfall_lineage.get("max_source_timestamp"),
        "max_observed_rainfall_timestamp": rainfall_lineage.get("max_source_timestamp"),
        "selected_forecast_issue_time": forecast_lineage.get("selected_issue_time"),
        "observed_climate_records_excluded_after_cutoff": rainfall_lineage.get("records_excluded_after_cutoff", 0),
        "max_surveillance_record_created_at": surveillance_lineage.get("max_record_created_at"),
        "max_surveillance_reporting_period_end": max_reporting_end,
        "spatial_relationships_filter": f"generated_at < {source_cutoff.isoformat()}",
        "max_spatial_relationship_generated_at": spatial_lineage.get("max_relationship_generated_at"),
        "max_facility_catchment_generated_at": spatial_lineage.get("max_catchment_generated_at"),
        "max_facility_forecast_generated_at": spatial_lineage.get("max_facility_forecast_generated_at"),
        "max_neighbor_risk_generated_at": spatial_lineage.get("max_neighbor_risk_generated_at"),
        "max_neighbor_climate_source_timestamp": spatial_lineage.get("max_neighbor_climate_source_timestamp"),
        "max_nearest_facility_created_at": spatial_lineage.get("max_nearest_facility_created_at"),
        "max_neighbor_surveillance_record_created_at": spatial_lineage.get(
            "max_neighbor_surveillance_record_created_at"
        ),
        "max_neighbor_surveillance_reporting_period_end": max_neighbor_reporting_end,
        "passes_cutoff_check": bool(
            reporting_period_passes
            and neighbor_reporting_period_passes
            and source_timestamp_passes
            and spatial_timestamp_passes
        ),
    }


def build_lead_time_feature_dataset(
    wards: Iterable[Ward] | None = None,
    *,
    prediction_dates: Iterable[date] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    step_days: int = 1,
    source_cutoff_as_of: datetime | None = None,
    include_seeded_surveillance: bool = False,
    heavy_rain_threshold_mm: float = DEFAULT_HEAVY_RAIN_THRESHOLD_MM,
    claimed_forecast_horizon_days: int = DEFAULT_CLAIMED_FORECAST_HORIZON_DAYS,
) -> LeadTimeFeatureDatasetSnapshot:
    if claimed_forecast_horizon_days not in LEAD_TIME_FORECAST_HORIZON_DAYS:
        raise ValueError("claimed_forecast_horizon_days must be between 1 and 14.")
    require_seeded_truth_allowed(
        "seeded surveillance lead-time feature generation",
        requested=include_seeded_surveillance,
    )

    prediction_date_list = _normalise_prediction_dates(
        prediction_dates=prediction_dates,
        start_date=start_date,
        end_date=end_date,
        step_days=step_days,
    )
    ward_list = list(wards) if wards is not None else list(Ward.objects.filter(is_active=True).order_by("name"))
    if not ward_list:
        raise ValueError("At least one ward is required to build lead-time feature windows.")
    ward_ids = {ward.id for ward in ward_list}

    feature_rows: list[FeatureDatasetRow] = []
    rows_by_ward_prediction_date: dict[tuple[int, str], dict] = {}
    source_kinds: list[str] = []
    population_exposure_feature_datasets: list[FeatureDataset] = []

    for prediction_date in prediction_date_list:
        source_cutoff = _effective_source_cutoff(prediction_date, source_cutoff_as_of=source_cutoff_as_of)
        population_as_of = _inclusive_as_of_for_exclusive_cutoff(source_cutoff)
        population_snapshot = build_population_exposure_feature_dataset(
            ward_list,
            as_of=population_as_of,
            month=prediction_date.month,
        )
        population_exposure_feature_datasets.append(population_snapshot.feature_dataset)
        source_kinds.append(population_snapshot.feature_dataset.source_kind)
        spatial_relationships_by_ward_id = _spatial_relationships_by_source_ward_id(
            ward_ids=ward_ids,
            source_cutoff=source_cutoff,
        )
        spatial_neighbor_ward_ids = {
            relationship.target_ward_id
            for relationships in spatial_relationships_by_ward_id.values()
            for relationship in relationships
        }
        expanded_ward_ids = ward_ids | spatial_neighbor_ward_ids
        climate_records_by_ward_id = _climate_records_by_ward_id(
            ward_ids=expanded_ward_ids,
            source_cutoff=source_cutoff,
        )
        surveillance_by_ward_id = _surveillance_records_by_ward_id(
            ward_ids=expanded_ward_ids,
            prediction_date=prediction_date,
            source_cutoff=source_cutoff,
            lookback_days=LEAD_TIME_SURVEILLANCE_LOOKBACK_DAYS,
            include_seeded_surveillance=include_seeded_surveillance,
        )

        for ward in ward_list:
            population_values = population_snapshot.rows_by_ward_id.get(ward.id, {})
            population_source_lineage = population_values.get("source_lineage") or {}
            population_baseline_refs = population_source_lineage.get(
                "population_baseline_record_refs", []
            )
            if isinstance(population_baseline_refs, str):
                population_baseline_refs = [population_baseline_refs]
            population_baseline_refs = list(population_baseline_refs or [])
            climate_records = climate_records_by_ward_id.get(ward.id, [])
            observed_observations, observed_source_summary = _observed_rainfall_observations_from_climate_records(
                climate_records=climate_records,
                source_cutoff=source_cutoff,
            )
            rainfall_values, rainfall_lineage = _rainfall_window_features(
                observations=observed_observations,
                prediction_date=prediction_date,
                source_cutoff=source_cutoff,
                heavy_rain_threshold_mm=heavy_rain_threshold_mm,
                source_summary=observed_source_summary,
            )
            forecast_values, forecast_lineage = _forecast_rainfall_features(
                climate_records=climate_records,
                prediction_date=prediction_date,
                source_cutoff=source_cutoff,
                claimed_forecast_horizon_days=claimed_forecast_horizon_days,
            )
            fallback_values, fallback_lineage = _fallback_static_rainfall_features(climate_records)
            climate_values, climate_lineage = _climate_coverage_features(
                observed_lineage=rainfall_lineage,
                forecast_values=forecast_values,
                forecast_lineage=forecast_lineage,
                fallback_values=fallback_values,
            )
            surveillance_values, surveillance_lineage = _surveillance_trend_features(
                records=surveillance_by_ward_id.get(ward.id, []),
                prediction_date=prediction_date,
            )
            spatial_relationships = spatial_relationships_by_ward_id.get(ward.id, [])
            neighbor_ward_ids = {relationship.target_ward_id for relationship in spatial_relationships}
            neighbor_values, neighbor_lineage = _neighbor_risk_features(
                ward,
                source_cutoff,
                spatial_relationships=spatial_relationships,
            )
            neighboring_surveillance_values, neighboring_surveillance_lineage = _neighbor_surveillance_features(
                neighbor_ward_ids=neighbor_ward_ids,
                surveillance_by_ward_id=surveillance_by_ward_id,
                prediction_date=prediction_date,
            )
            neighboring_climate_values, neighboring_climate_lineage = _neighbor_climate_features(
                neighbor_ward_ids=neighbor_ward_ids,
                climate_records_by_ward_id=climate_records_by_ward_id,
                prediction_date=prediction_date,
                source_cutoff=source_cutoff,
                heavy_rain_threshold_mm=heavy_rain_threshold_mm,
            )
            catchment_values, catchment_lineage = _catchment_facility_pressure_features(
                ward=ward,
                source_cutoff=source_cutoff,
            )
            nearest_facility_values, nearest_facility_lineage = _distance_to_nearest_facility_feature(
                ward,
                source_cutoff,
            )
            water_values, water_lineage = _water_proximity_features(population_values)
            spatial_lineage = {
                "relationships": neighbor_lineage,
                "neighbor_surveillance": neighboring_surveillance_lineage,
                "neighbor_climate": neighboring_climate_lineage,
                "catchment_facility_pressure": catchment_lineage,
                "nearest_facility": nearest_facility_lineage,
                "water_proximity": water_lineage,
                "max_relationship_generated_at": max(
                    (relationship.generated_at for relationship in spatial_relationships),
                    default=None,
                ).isoformat()
                if spatial_relationships
                else None,
                "max_catchment_generated_at": catchment_lineage.get("max_catchment_generated_at"),
                "max_facility_forecast_generated_at": catchment_lineage.get("max_forecast_generated_at"),
                "max_neighbor_risk_generated_at": neighbor_lineage.get("max_generated_at"),
                "max_neighbor_climate_source_timestamp": neighboring_climate_lineage.get("max_source_timestamp"),
                "max_nearest_facility_created_at": nearest_facility_lineage.get("max_facility_created_at"),
                "max_neighbor_surveillance_record_created_at": neighboring_surveillance_lineage.get(
                    "max_record_created_at"
                ),
                "max_neighbor_surveillance_reporting_period_end": neighboring_surveillance_lineage.get(
                    "max_reporting_period_end"
                ),
            }
            source_kinds.extend(
                _feature_source_kind_from_rainfall(source_kind)
                for source_kind in (rainfall_lineage.get("source_kinds") or {}).keys()
            )
            source_kinds.extend(
                _feature_source_kind_from_rainfall(source_kind)
                for source_kind in (forecast_lineage.get("source_kinds") or {}).keys()
            )
            source_kinds.extend(
                _feature_source_kind_from_rainfall(source_kind)
                for source_kind in (fallback_lineage.get("source_kinds") or {}).keys()
            )
            source_kinds.extend(
                _feature_source_kind_from_surveillance(source_kind)
                for source_kind in (surveillance_lineage.get("source_kinds") or {}).keys()
            )
            source_kinds.extend(
                _feature_source_kind_from_surveillance(source_kind)
                for source_kind in (neighboring_surveillance_lineage.get("source_kinds") or {}).keys()
            )
            source_kinds.extend(
                _feature_source_kind_from_rainfall(source_kind)
                for source_kind in (neighboring_climate_lineage.get("source_kinds") or {}).keys()
            )

            leakage_proof = _row_leakage_proof(
                prediction_date=prediction_date,
                source_cutoff=source_cutoff,
                population_as_of=population_as_of,
                rainfall_lineage=rainfall_lineage,
                forecast_lineage=forecast_lineage,
                surveillance_lineage=surveillance_lineage,
                spatial_lineage=spatial_lineage,
            )
            synthetic_rainfall_fallback_used = bool(fallback_values.get("fallback_static_rainfall_used"))
            synthetic_population_fallback_used = population_values.get("population_total") is None
            feature_values = {
                "prediction_date": prediction_date.isoformat(),
                "source_cutoff_timestamp": source_cutoff.isoformat(),
                "source_cutoff_policy": LEAD_TIME_SOURCE_CUTOFF_POLICY,
                **rainfall_values,
                **forecast_values,
                **fallback_values,
                "synthetic_rainfall_fallback_used": synthetic_rainfall_fallback_used,
                "synthetic_population_fallback_used": synthetic_population_fallback_used,
                "population_baseline_record_ref": (
                    population_baseline_refs[0] if len(population_baseline_refs) == 1 else None
                ),
                "population_baseline_record_refs": population_baseline_refs,
                **climate_values,
                **neighbor_values,
                **neighboring_surveillance_values,
                **neighboring_climate_values,
                **catchment_values,
                **nearest_facility_values,
                **water_values,
                **surveillance_values,
                **{key: population_values.get(key) for key in POPULATION_EXPOSURE_FEATURE_KEYS},
                "source_lineage": {
                    "rainfall": rainfall_lineage,
                    "forecast_rainfall": forecast_lineage,
                    "fallback_static_rainfall": fallback_lineage,
                    "climate_coverage": climate_lineage,
                    "population_exposure": population_source_lineage,
                    "population_exposure_dataset_ref": population_snapshot.feature_dataset.dataset_ref,
                    "surveillance": surveillance_lineage,
                    "upstream_or_neighboring_ward_risk": neighbor_lineage,
                    "spatial_neighbor_risk": neighbor_lineage,
                    "spatial_relationships": spatial_lineage,
                    "neighboring_surveillance": neighboring_surveillance_lineage,
                    "neighboring_climate": neighboring_climate_lineage,
                    "facility_catchment_pressure": catchment_lineage,
                    "nearest_facility_distance": nearest_facility_lineage,
                    "water_proximity": water_lineage,
                    "spatial_features": spatial_lineage,
                },
                "leakage_proof": leakage_proof,
            }
            key = (ward.id, prediction_date.isoformat())
            rows_by_ward_prediction_date[key] = feature_values
            feature_rows.append(
                FeatureDatasetRow(
                    ward=ward,
                    ward_name_snapshot=ward.name,
                    month=prediction_date.month,
                    feature_values=feature_values,
                    label=None,
                )
            )

    dataset_month = prediction_date_list[0].month if len({item.month for item in prediction_date_list}) == 1 else None
    coverage = {
        "ward_count": len(ward_list),
        "prediction_date_count": len(prediction_date_list),
        "row_count": len(feature_rows),
        "rows_with_rainfall_source_records": sum(
            1
            for row in rows_by_ward_prediction_date.values()
            if row["source_lineage"]["rainfall"]["source_record_count"] > 0
        ),
        "rows_with_observed_rainfall_records": sum(
            1
            for row in rows_by_ward_prediction_date.values()
            if row["source_lineage"]["rainfall"]["record_count"] > 0
        ),
        "rows_with_forecast_rainfall_records": sum(
            1
            for row in rows_by_ward_prediction_date.values()
            if row["source_lineage"]["forecast_rainfall"]["selected_record_count"] > 0
        ),
        "rows_with_fallback_static_rainfall": sum(
            1 for row in rows_by_ward_prediction_date.values() if row["fallback_static_rainfall_used"]
        ),
        "rows_with_synthetic_rainfall_fallback": sum(
            1 for row in rows_by_ward_prediction_date.values() if row["synthetic_rainfall_fallback_used"]
        ),
        "rows_with_synthetic_population_fallback": sum(
            1 for row in rows_by_ward_prediction_date.values() if row["synthetic_population_fallback_used"]
        ),
        "rows_with_7_day_forecast_coverage": sum(
            1 for row in rows_by_ward_prediction_date.values() if row["forecast_horizon_7d_sufficient"]
        ),
        "rows_with_14_day_forecast_coverage": sum(
            1 for row in rows_by_ward_prediction_date.values() if row["forecast_horizon_14d_sufficient"]
        ),
        "rows_with_sufficient_claimed_climate_coverage": sum(
            1
            for row in rows_by_ward_prediction_date.values()
            if row["claimed_lead_time_climate_coverage_sufficient"]
        ),
        "rows_with_surveillance_records": sum(
            1
            for row in rows_by_ward_prediction_date.values()
            if row["source_lineage"]["surveillance"]["record_count"] > 0
        ),
        "rows_with_population_baseline": sum(
            1 for row in rows_by_ward_prediction_date.values() if row.get("population_total") is not None
        ),
        "rows_with_neighbor_risk_signal": sum(
            1
            for row in rows_by_ward_prediction_date.values()
            if row.get("upstream_or_neighboring_ward_risk_signal") is not None
        ),
        "rows_with_spatial_neighbor_relationships": sum(
            1
            for row in rows_by_ward_prediction_date.values()
            if row["source_lineage"]["spatial_relationships"]["relationships"].get("relationship_count", 0) > 0
        ),
        "rows_with_neighboring_high_risk_wards": sum(
            1
            for row in rows_by_ward_prediction_date.values()
            if row.get("neighboring_high_risk_ward_count", 0) > 0
        ),
        "rows_with_neighboring_surveillance_records": sum(
            1
            for row in rows_by_ward_prediction_date.values()
            if row.get("neighboring_surveillance_record_count", 0) > 0
        ),
        "rows_with_catchment_facility_pressure": sum(
            1
            for row in rows_by_ward_prediction_date.values()
            if row.get("catchment_facility_readiness_pressure") is not None
        ),
        "rows_with_water_proximity_source": sum(
            1
            for row in rows_by_ward_prediction_date.values()
            if row.get("water_proximity_source_available")
        ),
        "rows_passing_leakage_check": sum(
            1 for row in rows_by_ward_prediction_date.values() if row["leakage_proof"]["passes_cutoff_check"]
        ),
    }
    source_kind = _combine_feature_source_kinds(source_kinds)
    if source_kind == FeatureDataset.SOURCE_KIND_LIVE and (
        coverage["rows_with_synthetic_rainfall_fallback"]
        or coverage["rows_with_synthetic_population_fallback"]
    ):
        source_kind = FeatureDataset.SOURCE_KIND_HYBRID
    dataset = FeatureDataset.objects.create(
        dataset_ref=(
            f"lead-time-features-{LEAD_TIME_FEATURE_SCHEMA_VERSION}-"
            f"{prediction_date_list[0].isoformat()}-{uuid4().hex[:8]}"
        ),
        dataset_kind=FeatureDataset.KIND_INFERENCE,
        schema_version=LEAD_TIME_FEATURE_SCHEMA_VERSION,
        source_kind=source_kind,
        month=dataset_month,
        feature_keys=LEAD_TIME_FEATURE_KEYS,
        row_count=len(feature_rows),
        lineage_metadata={
            "builder": "build_lead_time_feature_dataset",
            "generation_mode": LEAD_TIME_FEATURE_GENERATION_MODE,
            "prediction_dates": [item.isoformat() for item in prediction_date_list],
            "source_cutoff_policy": LEAD_TIME_SOURCE_CUTOFF_POLICY,
            "source_cutoff_as_of": source_cutoff_as_of.isoformat() if source_cutoff_as_of else None,
            "source_cutoff_as_of_applied": source_cutoff_as_of is not None,
            "rainfall_windows_days": list(LEAD_TIME_RAINFALL_WINDOWS_DAYS),
            "rainfall_window_mode": "trailing_observed_climate_records_before_prediction_date",
            "climate_coverage_schema_version": LEAD_TIME_CLIMATE_COVERAGE_SCHEMA_VERSION,
            "claimed_forecast_horizon_days": claimed_forecast_horizon_days,
            "forecast_horizon_days_supported_by_feature_builder": list(LEAD_TIME_FORECAST_HORIZON_DAYS),
            "climate_coverage_policy": {
                "observed_rainfall": "uses observed climate records with observed_timestamp before prediction cutoff",
                "forecast_rainfall": (
                    "uses forecast records with issue_time before prediction cutoff "
                    "and valid coverage for claimed lead days"
                ),
                "fallback_static": "reported separately and excluded from observed and forecast rainfall totals",
                "sufficiency": "all claimed lead days must be covered by selected forecast records",
            },
            "spatial_feature_policy": {
                "ward_relationships": (
                    "uses active-geometry WardSpatialRelationship edges generated before prediction cutoff; "
                    "same-county peers are not used as substitute neighbor truth"
                ),
                "neighbor_surveillance": (
                    "uses neighboring ward surveillance records created before cutoff with reporting periods "
                    "ending before prediction date"
                ),
                "neighbor_climate": "uses neighboring ward observed rainfall records before prediction cutoff",
                "nearest_facility": "uses active facility coordinates in the same county",
                "catchment_pressure": (
                    "uses active-geometry facility catchments and latest facility forecasts generated before cutoff"
                ),
                "water_proximity": "uses ward-level population exposure water_body_proximity where available",
                "label_windows": "surveillance label windows are never queried as phase 3 feature inputs",
            },
            "heavy_rain_threshold_mm": heavy_rain_threshold_mm,
            "surveillance_lookback_days": LEAD_TIME_SURVEILLANCE_LOOKBACK_DAYS,
            "include_seeded_surveillance": include_seeded_surveillance,
            "population_exposure_dataset_refs": [
                dataset.dataset_ref for dataset in population_exposure_feature_datasets
            ],
            "population_exposure_feature_dataset_ids": [
                dataset.id for dataset in population_exposure_feature_datasets
            ],
            "population_baseline_record_refs": sorted(
                {
                    reference
                    for row in feature_rows
                    for reference in (row.feature_values or {}).get(
                        "population_baseline_record_refs", []
                    )
                }
            ),
            "coverage": coverage,
            "production_truth_policy": {
                "eligible": not (
                    coverage["rows_with_synthetic_rainfall_fallback"]
                    or coverage["rows_with_synthetic_population_fallback"]
                ),
                "blocked_reason_codes": (
                    ["production_synthetic_feature_fallback_blocked"]
                    if coverage["rows_with_synthetic_rainfall_fallback"]
                    or coverage["rows_with_synthetic_population_fallback"]
                    else []
                ),
            },
            "leakage_proof_contract": {
                "future_label_data_used": False,
                "label_windows_used_as_input": False,
                "feature_inputs_must_be_created_before_source_cutoff": True,
                "surveillance_reporting_period_end_must_be_before_prediction_date": True,
            },
        },
    )
    for row in feature_rows:
        row.dataset = dataset
    FeatureDatasetRow.objects.bulk_create(feature_rows)

    return LeadTimeFeatureDatasetSnapshot(
        feature_dataset=dataset,
        rows_by_ward_prediction_date=rows_by_ward_prediction_date,
        population_exposure_feature_datasets=population_exposure_feature_datasets,
    )
