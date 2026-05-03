from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Iterable
from uuid import uuid4

from django.utils import timezone

from risk.models import (
    FeatureDataset,
    FeatureDatasetRow,
    IngestionRun,
    RiskScore,
    SurveillanceCaseClass,
    SurveillanceFreshnessState,
    SurveillanceRecord,
    SurveillanceSourceKind,
    SurveillanceTruthLevel,
    Ward,
)
from risk.population_exposure_features import (
    POPULATION_EXPOSURE_FEATURE_KEYS,
    build_population_exposure_feature_dataset,
)
from risk.surveillance_labels import record_is_superseded_by_correction


LEAD_TIME_FEATURE_SCHEMA_VERSION = "lead-time-feature-v1"
LEAD_TIME_FEATURE_GENERATION_MODE = "phase_2_lead_time_feature_windows_v1"
LEAD_TIME_SOURCE_CUTOFF_POLICY = "exclusive_before_prediction_date_midnight"
LEAD_TIME_RAINFALL_WINDOWS_DAYS = (3, 7, 14)
LEAD_TIME_SURVEILLANCE_LOOKBACK_DAYS = 28
DEFAULT_HEAVY_RAIN_THRESHOLD_MM = 50.0

LEAD_TIME_FEATURE_KEYS = [
    "prediction_date",
    "source_cutoff_timestamp",
    "source_cutoff_policy",
    "rainfall_total_3d",
    "rainfall_total_7d",
    "rainfall_total_14d",
    "rainfall_local_baseline_mm",
    "rainfall_anomaly_against_local_baseline",
    "heavy_rain_threshold_exceedance_count_14d",
    "days_since_heavy_rain",
    "upstream_or_neighboring_ward_risk_signal",
    "upstream_or_neighboring_ward_count",
    "upstream_or_neighboring_ward_signal_source",
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
            return _normalise_aware(datetime.fromisoformat(value))
        except ValueError:
            return None
    return None


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


def _rainfall_observation_timestamp(result: dict, ingestion_run: IngestionRun) -> datetime | None:
    return (
        _parse_datetime(result.get("source_timestamp"))
        or _parse_datetime(ingestion_run.source_timestamp)
        or _parse_datetime(ingestion_run.completed_at)
    )


def _rainfall_observations_by_ward_id(
    *,
    ward_ids: set[int],
    source_cutoff: datetime,
) -> dict[int, list[dict]]:
    observations_by_ward_id: dict[int, list[dict]] = defaultdict(list)
    runs = IngestionRun.objects.filter(
        run_type=IngestionRun.RUN_TYPE_RAINFALL,
        completed_at__lt=source_cutoff,
    ).order_by("completed_at", "id")
    for run in runs:
        results = run.results if isinstance(run.results, list) else []
        for result in results:
            ward_id = result.get("ward_id")
            if not ward_id or int(ward_id) not in ward_ids:
                continue
            observed_at = _rainfall_observation_timestamp(result, run)
            if observed_at is None or observed_at >= source_cutoff:
                continue
            rainfall_mm = _safe_float(result.get("rainfall_mm"))
            if rainfall_mm is None:
                continue
            canonical = result.get("canonical_record") or {}
            observations_by_ward_id[int(ward_id)].append(
                {
                    "ingestion_run_id": run.id,
                    "rainfall_mm": rainfall_mm,
                    "observed_at": observed_at,
                    "source": result.get("source") or run.source_name,
                    "source_kind": run.source_kind,
                    "source_mode": run.source_mode,
                    "freshness_state": run.freshness_state,
                    "fallback_reason": result.get("fallback_reason") or "",
                    "canonical_record_ref": canonical.get("record_ref"),
                }
            )
    return observations_by_ward_id


def _rainfall_window_features(
    *,
    observations: list[dict],
    prediction_date: date,
    source_cutoff: datetime,
    heavy_rain_threshold_mm: float,
) -> tuple[dict, dict]:
    values = {
        "rainfall_total_3d": 0.0,
        "rainfall_total_7d": 0.0,
        "rainfall_total_14d": 0.0,
        "rainfall_local_baseline_mm": 0.0,
        "rainfall_anomaly_against_local_baseline": 0.0,
        "heavy_rain_threshold_exceedance_count_14d": 0,
        "days_since_heavy_rain": None,
    }
    lineage = {
        "window_mode": "trailing_available_rainfall_ingestion_results_before_prediction_date",
        "daily_gauge_claim": False,
        "heavy_rain_threshold_mm": heavy_rain_threshold_mm,
        "record_count": len(observations),
        "windows": {},
        "source_kinds": dict(Counter(observation["source_kind"] for observation in observations)),
        "ingestion_run_ids": sorted({observation["ingestion_run_id"] for observation in observations}),
        "canonical_record_refs": sorted(
            {observation["canonical_record_ref"] for observation in observations if observation["canonical_record_ref"]}
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
        values[f"rainfall_total_{window_days}d"] = total
        lineage["windows"][f"{window_days}d"] = {
            "window_start_exclusive_policy": window_start.isoformat(),
            "window_end_exclusive": source_cutoff.isoformat(),
            "record_count": len(window_observations),
            "ingestion_run_ids": sorted({item["ingestion_run_id"] for item in window_observations}),
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


def _neighbor_risk_features(ward: Ward, source_cutoff: datetime) -> tuple[dict, dict]:
    latest_by_ward_id: dict[int, RiskScore] = {}
    queryset = (
        RiskScore.objects.filter(
            ward__county=ward.county,
            generated_at__lt=source_cutoff,
        )
        .exclude(ward_id=ward.id)
        .select_related("ward", "model_run")
        .order_by("ward_id", "-generated_at", "-id")
    )
    for score in queryset:
        latest_by_ward_id.setdefault(score.ward_id, score)

    peer_scores = list(latest_by_ward_id.values())
    if not peer_scores:
        return (
            {
                "upstream_or_neighboring_ward_risk_signal": None,
                "upstream_or_neighboring_ward_count": 0,
                "upstream_or_neighboring_ward_signal_source": "unavailable_no_peer_risk_scores_before_cutoff",
            },
            {
                "risk_score_count": 0,
                "source_mode": "same_county_peer_proxy_not_hydrological_upstream_truth",
                "risk_score_refs": [],
            },
        )
    average_score = round(sum(score.score for score in peer_scores) / len(peer_scores), 6)
    return (
        {
            "upstream_or_neighboring_ward_risk_signal": average_score,
            "upstream_or_neighboring_ward_count": len(peer_scores),
            "upstream_or_neighboring_ward_signal_source": "same_county_latest_peer_risk_scores_before_cutoff",
        },
        {
            "risk_score_count": len(peer_scores),
            "source_mode": "same_county_peer_proxy_not_hydrological_upstream_truth",
            "risk_score_refs": [f"risk_score:{score.id}" for score in peer_scores],
            "model_run_refs": [
                f"model_run:{score.model_run_id}" for score in peer_scores if score.model_run_id is not None
            ],
            "max_generated_at": max(score.generated_at for score in peer_scores).isoformat(),
        },
    )


def _row_leakage_proof(
    *,
    prediction_date: date,
    source_cutoff: datetime,
    population_as_of: datetime,
    rainfall_lineage: dict,
    surveillance_lineage: dict,
) -> dict:
    rainfall_timestamp = _parse_datetime(rainfall_lineage.get("max_source_timestamp"))
    surveillance_created_at = _parse_datetime(surveillance_lineage.get("max_record_created_at"))
    max_reporting_end = surveillance_lineage.get("max_reporting_period_end")
    reporting_period_passes = max_reporting_end is None or max_reporting_end < prediction_date.isoformat()
    source_timestamp_passes = all(
        timestamp is None or timestamp < source_cutoff
        for timestamp in (rainfall_timestamp, surveillance_created_at)
    )
    return {
        "future_label_data_used": False,
        "label_windows_used_as_input": False,
        "label_window_feature_policy": "surveillance_label_windows_are_not_queried_by_phase_2_feature_builder",
        "source_cutoff_timestamp": source_cutoff.isoformat(),
        "source_cutoff_policy": LEAD_TIME_SOURCE_CUTOFF_POLICY,
        "population_exposure_as_of": population_as_of.isoformat(),
        "surveillance_filter": {
            "created_at": f"< {source_cutoff.isoformat()}",
            "reporting_period_end": f"< {prediction_date.isoformat()}",
        },
        "rainfall_filter": {
            "completed_at": f"< {source_cutoff.isoformat()}",
            "source_timestamp": f"< {source_cutoff.isoformat()}",
        },
        "max_rainfall_source_timestamp": rainfall_lineage.get("max_source_timestamp"),
        "max_surveillance_record_created_at": surveillance_lineage.get("max_record_created_at"),
        "max_surveillance_reporting_period_end": max_reporting_end,
        "passes_cutoff_check": bool(reporting_period_passes and source_timestamp_passes),
    }


def build_lead_time_feature_dataset(
    wards: Iterable[Ward] | None = None,
    *,
    prediction_dates: Iterable[date] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    step_days: int = 1,
    include_seeded_surveillance: bool = False,
    heavy_rain_threshold_mm: float = DEFAULT_HEAVY_RAIN_THRESHOLD_MM,
) -> LeadTimeFeatureDatasetSnapshot:
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
        source_cutoff = _prediction_source_cutoff(prediction_date)
        population_as_of = _inclusive_as_of_for_exclusive_cutoff(source_cutoff)
        population_snapshot = build_population_exposure_feature_dataset(
            ward_list,
            as_of=population_as_of,
            month=prediction_date.month,
        )
        population_exposure_feature_datasets.append(population_snapshot.feature_dataset)
        source_kinds.append(population_snapshot.feature_dataset.source_kind)
        rainfall_by_ward_id = _rainfall_observations_by_ward_id(
            ward_ids=ward_ids,
            source_cutoff=source_cutoff,
        )
        surveillance_by_ward_id = _surveillance_records_by_ward_id(
            ward_ids=ward_ids,
            prediction_date=prediction_date,
            source_cutoff=source_cutoff,
            lookback_days=LEAD_TIME_SURVEILLANCE_LOOKBACK_DAYS,
            include_seeded_surveillance=include_seeded_surveillance,
        )

        for ward in ward_list:
            population_values = population_snapshot.rows_by_ward_id.get(ward.id, {})
            rainfall_values, rainfall_lineage = _rainfall_window_features(
                observations=rainfall_by_ward_id.get(ward.id, []),
                prediction_date=prediction_date,
                source_cutoff=source_cutoff,
                heavy_rain_threshold_mm=heavy_rain_threshold_mm,
            )
            surveillance_values, surveillance_lineage = _surveillance_trend_features(
                records=surveillance_by_ward_id.get(ward.id, []),
                prediction_date=prediction_date,
            )
            neighbor_values, neighbor_lineage = _neighbor_risk_features(ward, source_cutoff)
            source_kinds.extend(
                _feature_source_kind_from_rainfall(source_kind)
                for source_kind in (rainfall_lineage.get("source_kinds") or {}).keys()
            )
            source_kinds.extend(
                _feature_source_kind_from_surveillance(source_kind)
                for source_kind in (surveillance_lineage.get("source_kinds") or {}).keys()
            )

            leakage_proof = _row_leakage_proof(
                prediction_date=prediction_date,
                source_cutoff=source_cutoff,
                population_as_of=population_as_of,
                rainfall_lineage=rainfall_lineage,
                surveillance_lineage=surveillance_lineage,
            )
            feature_values = {
                "prediction_date": prediction_date.isoformat(),
                "source_cutoff_timestamp": source_cutoff.isoformat(),
                "source_cutoff_policy": LEAD_TIME_SOURCE_CUTOFF_POLICY,
                **rainfall_values,
                **neighbor_values,
                **surveillance_values,
                **{key: population_values.get(key) for key in POPULATION_EXPOSURE_FEATURE_KEYS},
                "source_lineage": {
                    "rainfall": rainfall_lineage,
                    "population_exposure": population_values.get("source_lineage") or {},
                    "population_exposure_dataset_ref": population_snapshot.feature_dataset.dataset_ref,
                    "surveillance": surveillance_lineage,
                    "upstream_or_neighboring_ward_risk": neighbor_lineage,
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
            if row["source_lineage"]["rainfall"]["record_count"] > 0
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
        "rows_passing_leakage_check": sum(
            1 for row in rows_by_ward_prediction_date.values() if row["leakage_proof"]["passes_cutoff_check"]
        ),
    }
    dataset = FeatureDataset.objects.create(
        dataset_ref=(
            f"lead-time-features-{LEAD_TIME_FEATURE_SCHEMA_VERSION}-"
            f"{prediction_date_list[0].isoformat()}-{uuid4().hex[:8]}"
        ),
        dataset_kind=FeatureDataset.KIND_INFERENCE,
        schema_version=LEAD_TIME_FEATURE_SCHEMA_VERSION,
        source_kind=_combine_feature_source_kinds(source_kinds),
        month=dataset_month,
        feature_keys=LEAD_TIME_FEATURE_KEYS,
        row_count=len(feature_rows),
        lineage_metadata={
            "builder": "build_lead_time_feature_dataset",
            "generation_mode": LEAD_TIME_FEATURE_GENERATION_MODE,
            "prediction_dates": [item.isoformat() for item in prediction_date_list],
            "source_cutoff_policy": LEAD_TIME_SOURCE_CUTOFF_POLICY,
            "rainfall_windows_days": list(LEAD_TIME_RAINFALL_WINDOWS_DAYS),
            "rainfall_window_mode": "trailing_available_rainfall_ingestion_results_before_prediction_date",
            "heavy_rain_threshold_mm": heavy_rain_threshold_mm,
            "surveillance_lookback_days": LEAD_TIME_SURVEILLANCE_LOOKBACK_DAYS,
            "include_seeded_surveillance": include_seeded_surveillance,
            "population_exposure_dataset_refs": [
                dataset.dataset_ref for dataset in population_exposure_feature_datasets
            ],
            "population_exposure_feature_dataset_ids": [
                dataset.id for dataset in population_exposure_feature_datasets
            ],
            "coverage": coverage,
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
