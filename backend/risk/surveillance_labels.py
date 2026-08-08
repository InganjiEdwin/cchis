from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable
from uuid import uuid4

from django.db import transaction
from django.db.models import Max, Min
from django.utils import timezone

from risk.models import (
    FeatureDataset,
    FeatureDatasetRow,
    ModelRun,
    RiskScore,
    SurveillanceCaseClass,
    SurveillanceFreshnessState,
    SurveillanceIngestionRun,
    SurveillanceLabelWindow,
    SurveillanceOutbreakLabel,
    SurveillanceRecord,
    SurveillanceSourceKind,
    SurveillanceTruthLevel,
    Ward,
)
from risk.truth_policy import require_seeded_truth_allowed
from risk.surveillance_lineage import dataset_is_currently_eligible


SURVEILLANCE_LABEL_SCHEMA_VERSION = "surveillance-label-v1"
SURVEILLANCE_LABEL_GENERATION_MODE = "surveillance_label_dataset_v1"
SURVEILLANCE_LEAD_TIME_LABEL_GENERATION_MODE = "phase_3_7_to_14_day_evaluation_labels_v1"
SURVEILLANCE_LEAD_TIME_LABEL_START_DAYS = 7
SURVEILLANCE_LEAD_TIME_LABEL_END_DAYS = 14
SURVEILLANCE_LABEL_FEATURE_KEYS = [
    "label_window_id",
    "label_window_start",
    "label_window_end",
    "window_days",
    "suspected_case_count",
    "confirmed_case_count",
    "proxy_case_count",
    "total_case_count",
    "confirmed_case_ratio",
    "proxy_case_ratio",
    "outbreak_label",
    "label_truth_level",
    "source_record_count",
    "source_coverage_summary",
    "generated_from_record_refs",
]
SURVEILLANCE_LEAD_TIME_LABEL_FEATURE_KEYS = list(
    dict.fromkeys(
        [
            "prediction_date",
            "label_window_start",
            "label_window_end",
            "lead_time_start_days",
            "lead_time_end_days",
            "ward_id",
            "ward_name",
            "suspected_case_count",
            "confirmed_case_count",
            "proxy_case_count",
            "total_case_count",
            "outbreak_label",
            "truth_level",
            "label_truth_level",
            "source_refs",
            "late_revision_state",
            *SURVEILLANCE_LABEL_FEATURE_KEYS,
        ]
    )
)
SURVEILLANCE_LABEL_TRUTH_ASSUMPTIONS = {
    SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE: "Confirmed surveillance records are treated as the strongest label evidence.",
    SurveillanceTruthLevel.SUSPECTED_SURVEILLANCE: "Suspected surveillance records can create watch or active labels but remain weaker than confirmed truth.",
    SurveillanceTruthLevel.PROXY_DIARRHEAL_SIGNAL: "Proxy diarrheal signals support weak burden labels and should not be described as confirmed cholera.",
    SurveillanceTruthLevel.FIELD_SIGNAL_ONLY: "Field-only signals are operational context, not confirmed surveillance truth.",
    SurveillanceTruthLevel.SEEDED_DEMO: "Seeded demo labels are non-production and must be excluded from real evaluation unless explicitly requested.",
}
SURVEILLANCE_LABEL_THRESHOLDS = {
    "active_confirmed_cases": 1,
    "active_suspected_cases": 10,
    "active_proxy_cases": 20,
    "watch_suspected_cases": 5,
    "watch_proxy_cases": 10,
}
SURVEILLANCE_LABEL_DATASET_CONTRACT = {
    "label_value": "FeatureDatasetRow.label is binary: 1 only for active outbreak labels, 0 for watch or none.",
    "empty_window_default": "Empty ward-time windows are excluded unless include_empty_windows=True.",
    "excluded_freshness_states": [SurveillanceFreshnessState.REPLAY_DIAGNOSTIC],
    "default_window_days": 7,
    "default_step_days": 7,
}
SURVEILLANCE_LEAD_TIME_LABEL_DATASET_CONTRACT = {
    **SURVEILLANCE_LABEL_DATASET_CONTRACT,
    "label_window_policy": "For each prediction_date, labels cover prediction_date + 7 through prediction_date + 14 inclusive.",
    "prediction_date": "FeatureDatasetRow.feature_values.prediction_date is the date the model score is evaluated from.",
    "late_revision_state": "Every row records whether source surveillance records were original, backfilled, revised, corrected, or absent.",
    "empty_window_default": "Phase 3 evaluation labels include explicit zero-count windows by default so negative examples are evaluable.",
    "replay_policy": "Rebuild this dataset for the same prediction_dates after late surveillance corrections to replay old model runs.",
}
EXCLUDED_LABEL_FRESHNESS_STATES = frozenset({SurveillanceFreshnessState.REPLAY_DIAGNOSTIC})
PROXY_ONLY_TRUTH_LEVELS = frozenset(
    {
        SurveillanceTruthLevel.PROXY_DIARRHEAL_SIGNAL,
        SurveillanceTruthLevel.FIELD_SIGNAL_ONLY,
        SurveillanceTruthLevel.SEEDED_DEMO,
    }
)


def record_is_superseded_by_correction(record: SurveillanceRecord) -> bool:
    return bool((record.raw_payload or {}).get("superseded_by_record_ref"))


@dataclass
class SurveillanceLabelDatasetSnapshot:
    feature_dataset: FeatureDataset
    label_windows: list[SurveillanceLabelWindow]
    rows_by_window_id: dict[int, dict]


@dataclass
class SurveillanceLeadTimeLabelDatasetSnapshot:
    feature_dataset: FeatureDataset
    label_windows: list[SurveillanceLabelWindow]
    rows_by_prediction_ward: dict[tuple[str, int], dict]


@dataclass
class _BuiltLabelWindow:
    label_window: SurveillanceLabelWindow
    feature_values: dict
    label_value: int
    month: int
    source_records: list[SurveillanceRecord]


def _normalise_as_of(as_of: datetime | None) -> datetime:
    as_of = as_of or timezone.now()
    if timezone.is_naive(as_of):
        as_of = timezone.make_aware(as_of, timezone.get_current_timezone())
    return as_of


def _window_ranges(start_date: date, end_date: date, *, window_days: int, step_days: int) -> list[tuple[date, date]]:
    if window_days <= 0:
        raise ValueError("window_days must be greater than zero.")
    if step_days <= 0:
        raise ValueError("step_days must be greater than zero.")
    if start_date > end_date:
        raise ValueError("start_date cannot be after end_date.")

    ranges = []
    current = start_date
    while current <= end_date:
        window_end = min(current + timedelta(days=window_days - 1), end_date)
        ranges.append((current, window_end))
        current = current + timedelta(days=step_days)
    return ranges


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


def _record_ref(record: SurveillanceRecord) -> str:
    return f"surveillance_record:{record.id}"


def _label_for_counts(
    *,
    suspected_case_count: int,
    confirmed_case_count: int,
    proxy_case_count: int,
    source_outbreak_labels: set[str],
) -> str:
    if SurveillanceOutbreakLabel.ACTIVE in source_outbreak_labels:
        return SurveillanceOutbreakLabel.ACTIVE
    if confirmed_case_count >= SURVEILLANCE_LABEL_THRESHOLDS["active_confirmed_cases"]:
        return SurveillanceOutbreakLabel.ACTIVE
    if suspected_case_count >= SURVEILLANCE_LABEL_THRESHOLDS["active_suspected_cases"]:
        return SurveillanceOutbreakLabel.ACTIVE
    if proxy_case_count >= SURVEILLANCE_LABEL_THRESHOLDS["active_proxy_cases"]:
        return SurveillanceOutbreakLabel.ACTIVE
    if SurveillanceOutbreakLabel.WATCH in source_outbreak_labels:
        return SurveillanceOutbreakLabel.WATCH
    if suspected_case_count >= SURVEILLANCE_LABEL_THRESHOLDS["watch_suspected_cases"]:
        return SurveillanceOutbreakLabel.WATCH
    if proxy_case_count >= SURVEILLANCE_LABEL_THRESHOLDS["watch_proxy_cases"]:
        return SurveillanceOutbreakLabel.WATCH
    return SurveillanceOutbreakLabel.NONE


def _truth_level_for_window(records: list[SurveillanceRecord]) -> str:
    truth_levels = {record.truth_level for record in records}
    if truth_levels == {SurveillanceTruthLevel.SEEDED_DEMO}:
        return SurveillanceTruthLevel.SEEDED_DEMO
    if SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE in truth_levels:
        return SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE
    if SurveillanceTruthLevel.SUSPECTED_SURVEILLANCE in truth_levels:
        return SurveillanceTruthLevel.SUSPECTED_SURVEILLANCE
    if SurveillanceTruthLevel.PROXY_DIARRHEAL_SIGNAL in truth_levels:
        return SurveillanceTruthLevel.PROXY_DIARRHEAL_SIGNAL
    if SurveillanceTruthLevel.FIELD_SIGNAL_ONLY in truth_levels:
        return SurveillanceTruthLevel.FIELD_SIGNAL_ONLY
    return SurveillanceTruthLevel.FIELD_SIGNAL_ONLY


def _source_kind_for_records(records: list[SurveillanceRecord]) -> str:
    if not records:
        return FeatureDataset.SOURCE_KIND_HYBRID
    source_kinds = {record.source_kind for record in records if record.source_kind}
    if source_kinds == {SurveillanceSourceKind.SEEDED}:
        return FeatureDataset.SOURCE_KIND_SEEDED
    if source_kinds == {SurveillanceSourceKind.LIVE}:
        return FeatureDataset.SOURCE_KIND_LIVE
    return FeatureDataset.SOURCE_KIND_HYBRID


def _late_revision_state(records: list[SurveillanceRecord]) -> str:
    if not records:
        return "no_source_records"
    if any(
        record.freshness_state == SurveillanceFreshnessState.CORRECTED_AFTER_INITIAL_SUBMISSION
        or (record.ingestion_run and record.ingestion_run.correction_mode == SurveillanceIngestionRun.CORRECTION_AMENDMENT)
        for record in records
    ):
        return "corrected_after_initial_submission"
    if any(record.revision_number > 1 or record.supersedes_record_ref for record in records):
        return "revised_record_present"
    if any(
        record.ingestion_run and record.ingestion_run.correction_mode == SurveillanceIngestionRun.CORRECTION_BACKFILL
        for record in records
    ):
        return "backfill"
    if any(record.freshness_state in {SurveillanceFreshnessState.DELAYED, SurveillanceFreshnessState.STALE} for record in records):
        return "late_or_stale_original"
    return "original"


def _source_coverage_summary(records: list[SurveillanceRecord], *, coverage_mode: str = "source_covered") -> dict:
    return {
        "coverage_mode": coverage_mode,
        "record_count": len(records),
        "source_names": sorted({record.source_name for record in records if record.source_name}),
        "source_ids": sorted({record.source_id for record in records if record.source_id}),
        "ingestion_run_ids": sorted({record.ingestion_run_id for record in records if record.ingestion_run_id}),
        "source_refs": sorted({record.source_ref for record in records if record.source_ref}),
        "source_type_counts": dict(Counter(record.source.source_type for record in records if record.source_id)),
        "source_credibility_counts": dict(
            Counter((record.raw_payload or {}).get("source_credibility", "unknown") for record in records)
        ),
        "truth_level_counts": dict(Counter(record.truth_level for record in records if record.truth_level)),
        "source_kind_counts": dict(Counter(record.source_kind for record in records if record.source_kind)),
        "freshness_state_counts": dict(Counter(record.freshness_state for record in records if record.freshness_state)),
        "case_class_counts": dict(Counter(record.case_class for record in records if record.case_class)),
        "disease_category_counts": dict(Counter(record.disease_category for record in records if record.disease_category)),
        "record_ids": [record.id for record in records],
    }


def _built_window(
    *,
    ward: Ward,
    window_start: date,
    window_end: date,
    records: list[SurveillanceRecord],
    include_empty_windows: bool,
) -> _BuiltLabelWindow | None:
    if not records and not include_empty_windows:
        return None

    suspected_case_count = sum(
        record.count_value for record in records if record.case_class == SurveillanceCaseClass.SUSPECTED
    )
    confirmed_case_count = sum(
        record.count_value for record in records if record.case_class == SurveillanceCaseClass.CONFIRMED
    )
    proxy_case_count = sum(record.count_value for record in records if record.case_class == SurveillanceCaseClass.PROXY)
    total_case_count = suspected_case_count + confirmed_case_count + proxy_case_count
    source_outbreak_labels = {record.outbreak_label for record in records if record.outbreak_label}
    outbreak_label = _label_for_counts(
        suspected_case_count=suspected_case_count,
        confirmed_case_count=confirmed_case_count,
        proxy_case_count=proxy_case_count,
        source_outbreak_labels=source_outbreak_labels,
    )
    label_truth_level = _truth_level_for_window(records)
    coverage_mode = "source_covered" if records else "empty_window_assumed_zero"
    source_coverage_summary = _source_coverage_summary(records, coverage_mode=coverage_mode)
    generated_from_record_refs = [_record_ref(record) for record in records]
    window_days = (window_end - window_start).days + 1
    feature_values = {
        "label_window_id": None,
        "label_window_start": window_start.isoformat(),
        "label_window_end": window_end.isoformat(),
        "window_days": window_days,
        "suspected_case_count": suspected_case_count,
        "confirmed_case_count": confirmed_case_count,
        "proxy_case_count": proxy_case_count,
        "total_case_count": total_case_count,
        "confirmed_case_ratio": round(confirmed_case_count / total_case_count, 6) if total_case_count else 0.0,
        "proxy_case_ratio": round(proxy_case_count / total_case_count, 6) if total_case_count else 0.0,
        "outbreak_label": outbreak_label,
        "label_truth_level": label_truth_level,
        "source_record_count": len(records),
        "source_coverage_summary": source_coverage_summary,
        "generated_from_record_refs": generated_from_record_refs,
    }
    label_window = SurveillanceLabelWindow(
        ward=ward,
        label_window_start=window_start,
        label_window_end=window_end,
        suspected_case_count=suspected_case_count,
        confirmed_case_count=confirmed_case_count,
        proxy_case_count=proxy_case_count,
        outbreak_label=outbreak_label,
        label_truth_level=label_truth_level,
        generation_mode=SURVEILLANCE_LABEL_GENERATION_MODE,
        source_coverage_summary=source_coverage_summary,
        generated_from_record_refs=generated_from_record_refs,
        source_record_count=len(records),
    )
    return _BuiltLabelWindow(
        label_window=label_window,
        feature_values=feature_values,
        label_value=1 if outbreak_label == SurveillanceOutbreakLabel.ACTIVE else 0,
        month=window_start.month,
        source_records=records,
    )


def _dataset_month(windows: list[_BuiltLabelWindow], supplied_month: int | None) -> int | None:
    if supplied_month is not None:
        return supplied_month
    months = {window.month for window in windows}
    if len(months) == 1:
        return next(iter(months))
    return None


def _base_record_queryset(*, ward_ids: list[int], as_of: datetime, include_seeded: bool):
    queryset = (
        SurveillanceRecord.objects.filter(ward_id__in=ward_ids, created_at__lte=as_of)
        .exclude(freshness_state__in=EXCLUDED_LABEL_FRESHNESS_STATES)
        .select_related("ward", "source", "ingestion_run")
        .order_by("reporting_period_start", "id")
    )
    if not include_seeded:
        queryset = queryset.exclude(truth_level=SurveillanceTruthLevel.SEEDED_DEMO)
    return queryset


def build_surveillance_label_dataset(
    wards: Iterable[Ward] | None = None,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    as_of: datetime | None = None,
    window_days: int = 7,
    step_days: int = 7,
    month: int | None = None,
    dataset_role: str = "training",
    include_seeded: bool = True,
    include_empty_windows: bool = False,
) -> SurveillanceLabelDatasetSnapshot:
    if dataset_role not in {"training", "evaluation"}:
        raise ValueError("dataset_role must be either 'training' or 'evaluation'.")
    require_seeded_truth_allowed(
        "seeded surveillance label generation",
        requested=include_seeded,
    )

    as_of = _normalise_as_of(as_of)
    ward_list = list(wards) if wards is not None else list(Ward.objects.filter(is_active=True).order_by("name"))
    ward_ids = [ward.id for ward in ward_list]
    if not ward_ids:
        raise ValueError("At least one ward is required to build a surveillance label dataset.")

    base_queryset = _base_record_queryset(ward_ids=ward_ids, as_of=as_of, include_seeded=include_seeded)
    if start_date is None or end_date is None:
        bounds = base_queryset.aggregate(start=Min("reporting_period_start"), end=Max("reporting_period_end"))
        start_date = start_date or bounds["start"]
        end_date = end_date or bounds["end"]
    if start_date is None or end_date is None:
        raise ValueError("No canonical surveillance records are available for deriving label window bounds.")
    if start_date > end_date:
        raise ValueError("start_date cannot be after end_date.")

    ranges = _window_ranges(start_date, end_date, window_days=window_days, step_days=step_days)
    records = list(
        base_queryset.filter(
            reporting_period_start__lte=end_date,
            reporting_period_end__gte=start_date,
        )
    )
    records = [record for record in records if not record_is_superseded_by_correction(record)]

    records_by_ward_id: dict[int, list[SurveillanceRecord]] = defaultdict(list)
    for record in records:
        records_by_ward_id[record.ward_id].append(record)

    built_windows: list[_BuiltLabelWindow] = []
    for window_start, window_end in ranges:
        for ward in ward_list:
            window_records = [
                record
                for record in records_by_ward_id.get(ward.id, [])
                if record.reporting_period_start <= window_end and record.reporting_period_end >= window_start
            ]
            built = _built_window(
                ward=ward,
                window_start=window_start,
                window_end=window_end,
                records=window_records,
                include_empty_windows=include_empty_windows,
            )
            if built is not None:
                built_windows.append(built)

    if not built_windows:
        raise ValueError("No surveillance label windows were generated for the selected wards and date range.")

    source_records_by_id = {
        record.id: record
        for built in built_windows
        for record in built.source_records
    }
    source_records = list(source_records_by_id.values())
    dataset_month = _dataset_month(built_windows, month)
    coverage = {
        "ward_count": len(ward_list),
        "candidate_window_count": len(ranges) * len(ward_list),
        "label_window_count": len(built_windows),
        "source_record_count": len(source_records),
        "active_label_count": sum(1 for built in built_windows if built.label_window.outbreak_label == SurveillanceOutbreakLabel.ACTIVE),
        "watch_label_count": sum(1 for built in built_windows if built.label_window.outbreak_label == SurveillanceOutbreakLabel.WATCH),
        "none_label_count": sum(1 for built in built_windows if built.label_window.outbreak_label == SurveillanceOutbreakLabel.NONE),
        "windows_without_source_records": sum(1 for built in built_windows if not built.source_records),
        "truth_level_counts": dict(Counter(built.label_window.label_truth_level for built in built_windows)),
        "outbreak_label_counts": dict(Counter(built.label_window.outbreak_label for built in built_windows)),
    }
    dataset_ref = (
        f"surveillance-label-{dataset_role}-{SURVEILLANCE_LABEL_SCHEMA_VERSION}-"
        f"{window_days}d-{uuid4().hex[:8]}"
    )

    with transaction.atomic():
        dataset = FeatureDataset.objects.create(
            dataset_ref=dataset_ref,
            dataset_kind=FeatureDataset.KIND_TRAINING,
            schema_version=SURVEILLANCE_LABEL_SCHEMA_VERSION,
            source_kind=_source_kind_for_records(source_records),
            month=dataset_month,
            feature_keys=SURVEILLANCE_LABEL_FEATURE_KEYS,
            row_count=len(built_windows),
            lineage_metadata={
                "builder": "build_surveillance_label_dataset",
                "dataset_role": dataset_role,
                "snapshot_as_of": as_of.isoformat(),
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "window_days": window_days,
                "step_days": step_days,
                "include_seeded": include_seeded,
                "include_empty_windows": include_empty_windows,
                "coverage": coverage,
                "source_lineage": _source_coverage_summary(source_records, coverage_mode="dataset_sources"),
                "truth_assumptions": SURVEILLANCE_LABEL_TRUTH_ASSUMPTIONS,
                "label_thresholds": SURVEILLANCE_LABEL_THRESHOLDS,
                "dataset_contract": SURVEILLANCE_LABEL_DATASET_CONTRACT,
            },
        )
        for built in built_windows:
            built.label_window.feature_dataset = dataset
            built.label_window.dataset_ref = dataset.dataset_ref
            built.label_window.schema_version = SURVEILLANCE_LABEL_SCHEMA_VERSION

        label_windows = SurveillanceLabelWindow.objects.bulk_create(
            [built.label_window for built in built_windows]
        )
        rows_by_window_id = {}
        feature_rows = []
        for built, label_window in zip(built_windows, label_windows):
            built.feature_values["label_window_id"] = label_window.id
            rows_by_window_id[label_window.id] = built.feature_values
            feature_rows.append(
                FeatureDatasetRow(
                    dataset=dataset,
                    ward=label_window.ward,
                    ward_name_snapshot=label_window.ward.name,
                    month=built.month,
                    feature_values=built.feature_values,
                    label=built.label_value,
                )
            )
        FeatureDatasetRow.objects.bulk_create(feature_rows)

    return SurveillanceLabelDatasetSnapshot(
        feature_dataset=dataset,
        label_windows=label_windows,
        rows_by_window_id=rows_by_window_id,
    )


def build_surveillance_lead_time_label_dataset(
    wards: Iterable[Ward] | None = None,
    *,
    prediction_dates: Iterable[date] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    step_days: int = 1,
    as_of: datetime | None = None,
    lead_time_start_days: int = SURVEILLANCE_LEAD_TIME_LABEL_START_DAYS,
    lead_time_end_days: int = SURVEILLANCE_LEAD_TIME_LABEL_END_DAYS,
    dataset_role: str = "evaluation",
    include_seeded: bool = False,
    include_empty_windows: bool = True,
) -> SurveillanceLeadTimeLabelDatasetSnapshot:
    if dataset_role not in {"training", "evaluation"}:
        raise ValueError("dataset_role must be either 'training' or 'evaluation'.")
    require_seeded_truth_allowed(
        "seeded surveillance lead-time label generation",
        requested=include_seeded,
    )
    if lead_time_start_days < 0:
        raise ValueError("lead_time_start_days cannot be negative.")
    if lead_time_end_days < lead_time_start_days:
        raise ValueError("lead_time_end_days cannot be before lead_time_start_days.")

    as_of = _normalise_as_of(as_of)
    prediction_date_list = _normalise_prediction_dates(
        prediction_dates=prediction_dates,
        start_date=start_date,
        end_date=end_date,
        step_days=step_days,
    )
    ward_list = list(wards) if wards is not None else list(Ward.objects.filter(is_active=True).order_by("name"))
    ward_ids = [ward.id for ward in ward_list]
    if not ward_ids:
        raise ValueError("At least one ward is required to build surveillance lead-time labels.")

    label_window_ranges = {
        prediction_date: (
            prediction_date + timedelta(days=lead_time_start_days),
            prediction_date + timedelta(days=lead_time_end_days),
        )
        for prediction_date in prediction_date_list
    }
    global_window_start = min(window_start for window_start, _ in label_window_ranges.values())
    global_window_end = max(window_end for _, window_end in label_window_ranges.values())

    base_queryset = _base_record_queryset(ward_ids=ward_ids, as_of=as_of, include_seeded=include_seeded)
    records = list(
        base_queryset.filter(
            reporting_period_start__lte=global_window_end,
            reporting_period_end__gte=global_window_start,
        )
    )
    records = [record for record in records if not record_is_superseded_by_correction(record)]

    records_by_ward_id: dict[int, list[SurveillanceRecord]] = defaultdict(list)
    for record in records:
        records_by_ward_id[record.ward_id].append(record)

    built_windows: list[_BuiltLabelWindow] = []
    rows_by_prediction_ward: dict[tuple[str, int], dict] = {}
    for prediction_date in prediction_date_list:
        window_start, window_end = label_window_ranges[prediction_date]
        for ward in ward_list:
            window_records = [
                record
                for record in records_by_ward_id.get(ward.id, [])
                if record.reporting_period_start <= window_end and record.reporting_period_end >= window_start
            ]
            built = _built_window(
                ward=ward,
                window_start=window_start,
                window_end=window_end,
                records=window_records,
                include_empty_windows=include_empty_windows,
            )
            if built is None:
                continue
            revision_state = _late_revision_state(window_records)
            source_refs = [_record_ref(record) for record in window_records]
            built.label_window.generation_mode = SURVEILLANCE_LEAD_TIME_LABEL_GENERATION_MODE
            built.feature_values.update(
                {
                    "prediction_date": prediction_date.isoformat(),
                    "lead_time_start_days": lead_time_start_days,
                    "lead_time_end_days": lead_time_end_days,
                    "ward_id": ward.id,
                    "ward_name": ward.name,
                    "truth_level": built.feature_values["label_truth_level"],
                    "source_refs": source_refs,
                    "late_revision_state": revision_state,
                    "evaluation_window_contract": {
                        "prediction_date": prediction_date.isoformat(),
                        "label_window_start": window_start.isoformat(),
                        "label_window_end": window_end.isoformat(),
                        "lead_time_start_days": lead_time_start_days,
                        "lead_time_end_days": lead_time_end_days,
                        "inclusive_window": True,
                    },
                }
            )
            rows_by_prediction_ward[(prediction_date.isoformat(), ward.id)] = built.feature_values
            built_windows.append(built)

    if not built_windows:
        raise ValueError("No surveillance lead-time label windows were generated for the selected wards and dates.")

    source_records_by_id = {
        record.id: record
        for built in built_windows
        for record in built.source_records
    }
    source_records = list(source_records_by_id.values())
    dataset_month = prediction_date_list[0].month if len({item.month for item in prediction_date_list}) == 1 else None
    window_days = lead_time_end_days - lead_time_start_days + 1
    coverage = {
        "ward_count": len(ward_list),
        "prediction_date_count": len(prediction_date_list),
        "candidate_window_count": len(prediction_date_list) * len(ward_list),
        "label_window_count": len(built_windows),
        "source_record_count": len(source_records),
        "active_label_count": sum(1 for built in built_windows if built.label_window.outbreak_label == SurveillanceOutbreakLabel.ACTIVE),
        "watch_label_count": sum(1 for built in built_windows if built.label_window.outbreak_label == SurveillanceOutbreakLabel.WATCH),
        "none_label_count": sum(1 for built in built_windows if built.label_window.outbreak_label == SurveillanceOutbreakLabel.NONE),
        "windows_without_source_records": sum(1 for built in built_windows if not built.source_records),
        "truth_level_counts": dict(Counter(built.label_window.label_truth_level for built in built_windows)),
        "outbreak_label_counts": dict(Counter(built.label_window.outbreak_label for built in built_windows)),
        "late_revision_state_counts": dict(
            Counter(built.feature_values["late_revision_state"] for built in built_windows)
        ),
        "confirmed_truth_label_count": sum(
            1
            for built in built_windows
            if built.label_window.label_truth_level == SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE
        ),
        "proxy_only_label_window_count": sum(
            1 for built in built_windows if built.label_window.label_truth_level in PROXY_ONLY_TRUTH_LEVELS
        ),
    }
    dataset_ref = (
        f"surveillance-label-{dataset_role}-{SURVEILLANCE_LABEL_SCHEMA_VERSION}-"
        f"lead-time-{lead_time_start_days}to{lead_time_end_days}d-{uuid4().hex[:8]}"
    )

    with transaction.atomic():
        dataset = FeatureDataset.objects.create(
            dataset_ref=dataset_ref,
            dataset_kind=FeatureDataset.KIND_TRAINING,
            schema_version=SURVEILLANCE_LABEL_SCHEMA_VERSION,
            source_kind=_source_kind_for_records(source_records),
            month=dataset_month,
            feature_keys=SURVEILLANCE_LEAD_TIME_LABEL_FEATURE_KEYS,
            row_count=len(built_windows),
            lineage_metadata={
                "builder": "build_surveillance_lead_time_label_dataset",
                "generation_mode": SURVEILLANCE_LEAD_TIME_LABEL_GENERATION_MODE,
                "dataset_role": dataset_role,
                "snapshot_as_of": as_of.isoformat(),
                "prediction_dates": [item.isoformat() for item in prediction_date_list],
                "start_date": global_window_start.isoformat(),
                "end_date": global_window_end.isoformat(),
                "label_window_start_offset_days": lead_time_start_days,
                "label_window_end_offset_days": lead_time_end_days,
                "window_days": window_days,
                "step_days": step_days,
                "include_seeded": include_seeded,
                "include_empty_windows": include_empty_windows,
                "coverage": coverage,
                "source_lineage": _source_coverage_summary(source_records, coverage_mode="dataset_sources"),
                "truth_assumptions": SURVEILLANCE_LABEL_TRUTH_ASSUMPTIONS,
                "label_thresholds": SURVEILLANCE_LABEL_THRESHOLDS,
                "dataset_contract": SURVEILLANCE_LEAD_TIME_LABEL_DATASET_CONTRACT,
                "correction_replay_contract": {
                    "can_rebuild_from_prediction_dates": True,
                    "prediction_dates": [item.isoformat() for item in prediction_date_list],
                    "late_revision_state_field": "late_revision_state",
                    "source_records_filtered_to_snapshot_as_of": as_of.isoformat(),
                    "superseded_records_excluded": True,
                },
            },
        )
        for built in built_windows:
            built.label_window.feature_dataset = dataset
            built.label_window.dataset_ref = dataset.dataset_ref
            built.label_window.schema_version = SURVEILLANCE_LABEL_SCHEMA_VERSION

        label_windows = SurveillanceLabelWindow.objects.bulk_create(
            [built.label_window for built in built_windows]
        )
        feature_rows = []
        persisted_rows_by_prediction_ward = {}
        for built, label_window in zip(built_windows, label_windows):
            built.feature_values["label_window_id"] = label_window.id
            key = (built.feature_values["prediction_date"], label_window.ward_id)
            persisted_rows_by_prediction_ward[key] = built.feature_values
            feature_rows.append(
                FeatureDatasetRow(
                    dataset=dataset,
                    ward=label_window.ward,
                    ward_name_snapshot=label_window.ward.name,
                    month=built.month,
                    feature_values=built.feature_values,
                    label=built.label_value,
                )
            )
        FeatureDatasetRow.objects.bulk_create(feature_rows)

    return SurveillanceLeadTimeLabelDatasetSnapshot(
        feature_dataset=dataset,
        label_windows=label_windows,
        rows_by_prediction_ward=persisted_rows_by_prediction_ward,
    )


def latest_surveillance_lead_time_label_dataset(*, dataset_role: str | None = "evaluation") -> FeatureDataset | None:
    queryset = FeatureDataset.objects.filter(
        schema_version=SURVEILLANCE_LABEL_SCHEMA_VERSION,
        eligibility_state=FeatureDataset.ELIGIBILITY_ACTIVE,
        lineage_metadata__generation_mode=SURVEILLANCE_LEAD_TIME_LABEL_GENERATION_MODE,
    )
    if dataset_role:
        queryset = queryset.filter(lineage_metadata__dataset_role=dataset_role)
    return next(
        (
            dataset
            for dataset in queryset.order_by("-created_at", "-id")
            if dataset_is_currently_eligible(dataset)
        ),
        None,
    )


def _parse_iso_date_value(value) -> date | None:
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _prediction_dates_by_ward_from_dataset(dataset: FeatureDataset | None) -> dict[int, list[date]]:
    if dataset is None:
        return {}
    dates_by_ward_id: dict[int, set[date]] = defaultdict(set)
    rows = FeatureDatasetRow.objects.filter(dataset=dataset, ward__isnull=False).order_by("id")
    for row in rows:
        prediction_date = _parse_iso_date_value((row.feature_values or {}).get("prediction_date"))
        if prediction_date is not None:
            dates_by_ward_id[row.ward_id].add(prediction_date)
    return {ward_id: sorted(values) for ward_id, values in dates_by_ward_id.items()}


def _prediction_date_for_score(
    score: RiskScore,
    *,
    inference_prediction_dates_by_ward_id: dict[int, list[date]],
) -> tuple[date, str]:
    inference_dates = inference_prediction_dates_by_ward_id.get(score.ward_id, [])
    if len(inference_dates) == 1:
        return inference_dates[0], "inference_feature_dataset_prediction_date"
    generated_at = timezone.localtime(score.generated_at) if score.generated_at else timezone.now()
    return generated_at.date(), "risk_score_generated_at_date_fallback"


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 6)


def evaluate_model_run_against_surveillance_lead_time_labels(
    model_run: ModelRun,
    *,
    label_dataset: FeatureDataset | None = None,
    persist: bool = True,
) -> dict:
    label_dataset = label_dataset or latest_surveillance_lead_time_label_dataset(dataset_role="evaluation")
    if label_dataset is not None and not dataset_is_currently_eligible(label_dataset):
        raise ValueError("superseded_label_dataset_not_current_evidence")
    if label_dataset is None:
        return {
            "status": "not_available",
            "evaluation_mode": "future_7_to_14_day_surveillance_labels_missing",
            "model_run_id": model_run.id,
            "model_version": model_run.model_version,
            "label_dataset_ref": None,
            "matched_prediction_count": 0,
            "truth_gate": {
                "proxy_only_as_confirmed_allowed": False,
                "confirmed_truth_required_for_confirmed_outbreak_claims": True,
            },
        }

    inference_prediction_dates_by_ward_id = _prediction_dates_by_ward_from_dataset(
        model_run.inference_feature_dataset
    )
    label_rows_by_key: dict[tuple[int, date], FeatureDatasetRow] = {}
    for row in FeatureDatasetRow.objects.filter(dataset=label_dataset, ward__isnull=False).order_by("id"):
        prediction_date = _parse_iso_date_value((row.feature_values or {}).get("prediction_date"))
        if prediction_date is None:
            continue
        label_rows_by_key[(row.ward_id, prediction_date)] = row

    scores = list(model_run.risk_scores.select_related("ward").order_by("id"))
    evaluation_rows = []
    unmatched_predictions = []
    prediction_date_source_counts = Counter()
    confusion = Counter()
    truth_level_counts = Counter()
    late_revision_state_counts = Counter()
    active_truth_count = 0
    confirmed_truth_count = 0
    proxy_only_count = 0

    for score in scores:
        prediction_date, prediction_date_source = _prediction_date_for_score(
            score,
            inference_prediction_dates_by_ward_id=inference_prediction_dates_by_ward_id,
        )
        prediction_date_source_counts[prediction_date_source] += 1
        label_row = label_rows_by_key.get((score.ward_id, prediction_date))
        if label_row is None:
            unmatched_predictions.append(
                {
                    "risk_score_ref": f"risk_score:{score.id}",
                    "ward_id": score.ward_id,
                    "ward_name": score.ward.name,
                    "prediction_date": prediction_date.isoformat(),
                    "prediction_date_source": prediction_date_source,
                }
            )
            continue

        label_values = label_row.feature_values or {}
        truth_level = label_values.get("truth_level") or label_values.get("label_truth_level")
        late_revision_state = label_values.get("late_revision_state", "unknown")
        predicted_positive = score.risk_level == Ward.RISK_HIGH
        observed_positive = label_row.label == 1
        if observed_positive:
            active_truth_count += 1
        if truth_level == SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE:
            confirmed_truth_count += 1
        if truth_level in PROXY_ONLY_TRUTH_LEVELS:
            proxy_only_count += 1
        truth_level_counts[truth_level or "unknown"] += 1
        late_revision_state_counts[late_revision_state] += 1

        if predicted_positive and observed_positive:
            confusion["true_positive"] += 1
        elif predicted_positive and not observed_positive:
            confusion["false_positive"] += 1
        elif not predicted_positive and observed_positive:
            confusion["false_negative"] += 1
        else:
            confusion["true_negative"] += 1

        evaluation_rows.append(
            {
                "risk_score_ref": f"risk_score:{score.id}",
                "ward_id": score.ward_id,
                "ward_name": score.ward.name,
                "prediction_date": prediction_date.isoformat(),
                "prediction_date_source": prediction_date_source,
                "predicted_risk_level": score.risk_level,
                "predicted_score": score.score,
                "predicted_positive": predicted_positive,
                "label": label_row.label,
                "outbreak_label": label_values.get("outbreak_label"),
                "truth_level": truth_level,
                "late_revision_state": late_revision_state,
                "label_window_id": label_values.get("label_window_id"),
                "source_refs": label_values.get("source_refs", []),
            }
        )

    matched_count = len(evaluation_rows)
    predicted_positive_count = confusion["true_positive"] + confusion["false_positive"]
    observed_positive_count = confusion["true_positive"] + confusion["false_negative"]
    metrics = {
        "accuracy": _safe_ratio(confusion["true_positive"] + confusion["true_negative"], matched_count),
        "precision": _safe_ratio(confusion["true_positive"], predicted_positive_count),
        "recall": _safe_ratio(confusion["true_positive"], observed_positive_count),
        "true_positive": confusion["true_positive"],
        "false_positive": confusion["false_positive"],
        "true_negative": confusion["true_negative"],
        "false_negative": confusion["false_negative"],
    }
    summary = {
        "status": "evaluated" if matched_count else "not_ready_no_matching_label_rows",
        "evaluation_mode": "future_7_to_14_day_surveillance_labels",
        "model_run_id": model_run.id,
        "model_version": model_run.model_version,
        "label_dataset_ref": label_dataset.dataset_ref,
        "label_feature_dataset_id": label_dataset.id,
        "label_generation_mode": (label_dataset.lineage_metadata or {}).get("generation_mode"),
        "matched_prediction_count": matched_count,
        "unmatched_prediction_count": len(unmatched_predictions),
        "risk_score_count": len(scores),
        "active_truth_label_count": active_truth_count,
        "confirmed_truth_label_count": confirmed_truth_count,
        "proxy_only_label_window_count": proxy_only_count,
        "truth_level_counts": dict(truth_level_counts),
        "late_revision_state_counts": dict(late_revision_state_counts),
        "prediction_date_source_counts": dict(prediction_date_source_counts),
        "metrics": metrics,
        "evaluation_rows": evaluation_rows,
        "unmatched_predictions": unmatched_predictions[:50],
        "correction_replay_contract": (label_dataset.lineage_metadata or {}).get("correction_replay_contract", {}),
        "truth_gate": {
            "proxy_only_as_confirmed_allowed": False,
            "confirmed_truth_required_for_confirmed_outbreak_claims": True,
            "proxy_only_label_window_count": proxy_only_count,
            "confirmed_truth_label_count": confirmed_truth_count,
            "evaluation_can_separate_confirmed_from_proxy": True,
        },
    }

    if persist:
        existing_metrics = model_run.evaluation_metrics or {}
        history = list(existing_metrics.get("surveillance_7_to_14_day_evaluation_history") or [])
        existing_current = existing_metrics.get("surveillance_7_to_14_day_evaluation")
        if existing_current:
            history.append(existing_current)
        existing_metrics["surveillance_7_to_14_day_evaluation"] = summary
        existing_metrics["surveillance_7_to_14_day_evaluation_history"] = history[-20:]
        metadata = model_run.metadata or {}
        metadata.update(
            {
                "surveillance_7_to_14_day_label_dataset_ref": label_dataset.dataset_ref,
                "surveillance_7_to_14_day_label_feature_dataset_id": label_dataset.id,
                "surveillance_7_to_14_day_evaluation_status": summary["status"],
                "surveillance_7_to_14_day_replayable_after_corrections": True,
            }
        )
        model_run.evaluation_metrics = existing_metrics
        model_run.metadata = metadata
        model_run.save(update_fields=["evaluation_metrics", "metadata"])

    return summary


def latest_surveillance_label_dataset(*, dataset_role: str | None = None) -> FeatureDataset | None:
    queryset = FeatureDataset.objects.filter(
        schema_version=SURVEILLANCE_LABEL_SCHEMA_VERSION,
        eligibility_state=FeatureDataset.ELIGIBILITY_ACTIVE,
    )
    if dataset_role:
        queryset = queryset.filter(lineage_metadata__dataset_role=dataset_role)
    return next(
        (
            dataset
            for dataset in queryset.order_by("-created_at", "-id")
            if dataset_is_currently_eligible(dataset)
        ),
        None,
    )
