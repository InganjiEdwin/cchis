from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable

from django.utils import timezone

from risk.models import (
    FeatureDataset,
    FeatureDatasetRow,
    SurveillanceCaseClass,
    SurveillanceFreshnessState,
    SurveillanceLabelWindow,
    SurveillanceOutbreakLabel,
    SurveillanceRecord,
    SurveillanceTruthLevel,
    Ward,
)
from risk.surveillance_labels import (
    SURVEILLANCE_LEAD_TIME_LABEL_GENERATION_MODE,
    record_is_superseded_by_correction,
)


SURVEILLANCE_FEATURE_SCHEMA_VERSION = "surveillance-feature-v1"
SURVEILLANCE_FEATURE_LOOKBACK_DAYS = 28
SURVEILLANCE_CONTEXT_FEATURE_KEYS = [
    "surveillance_recent_suspected_cases_28d",
    "surveillance_recent_confirmed_cases_28d",
    "surveillance_recent_proxy_cases_28d",
    "surveillance_recent_total_cases_28d",
    "surveillance_active_label_count_28d",
    "surveillance_watch_label_count_28d",
    "surveillance_confirmed_label_window_count_28d",
    "surveillance_suspected_label_window_count_28d",
    "surveillance_proxy_only_label_window_count_28d",
    "surveillance_delayed_or_stale_record_count_28d",
    "surveillance_latest_label_window_ref",
    "surveillance_latest_label_dataset_ref",
    "surveillance_latest_label_truth_level",
    "surveillance_latest_freshness_state",
    "surveillance_label_truth_state",
    "surveillance_proxy_only_as_confirmed_allowed",
    "surveillance_display_caveat",
]
PROXY_ONLY_TRUTH_LEVELS = frozenset(
    {
        SurveillanceTruthLevel.PROXY_DIARRHEAL_SIGNAL,
        SurveillanceTruthLevel.FIELD_SIGNAL_ONLY,
        SurveillanceTruthLevel.SEEDED_DEMO,
    }
)
DEGRADED_FRESHNESS_STATES = frozenset(
    {
        SurveillanceFreshnessState.DELAYED,
        SurveillanceFreshnessState.STALE,
    }
)


@dataclass
class SurveillanceFeatureSnapshot:
    rows_by_ward_id: dict[int, dict]
    feature_keys: list[str]
    coverage: dict
    truth_gate: dict
    as_of: datetime
    lookback_days: int


def _normalise_as_of(as_of: datetime | None) -> datetime:
    as_of = as_of or timezone.now()
    if timezone.is_naive(as_of):
        return timezone.make_aware(as_of, timezone.get_current_timezone())
    return as_of


def _label_window_ref(window: SurveillanceLabelWindow | None) -> str | None:
    return f"surveillance_label_window:{window.id}" if window else None


def _empty_context_row(ward: Ward) -> dict:
    return {
        "ward_id": ward.id,
        "ward_name": ward.name,
        "surveillance_recent_suspected_cases_28d": 0,
        "surveillance_recent_confirmed_cases_28d": 0,
        "surveillance_recent_proxy_cases_28d": 0,
        "surveillance_recent_total_cases_28d": 0,
        "surveillance_active_label_count_28d": 0,
        "surveillance_watch_label_count_28d": 0,
        "surveillance_confirmed_label_window_count_28d": 0,
        "surveillance_suspected_label_window_count_28d": 0,
        "surveillance_proxy_only_label_window_count_28d": 0,
        "surveillance_delayed_or_stale_record_count_28d": 0,
        "surveillance_latest_label_window_ref": None,
        "surveillance_latest_label_dataset_ref": None,
        "surveillance_latest_label_truth_level": None,
        "surveillance_latest_freshness_state": None,
        "surveillance_label_truth_state": "no_surveillance_label_window",
        "surveillance_proxy_only_as_confirmed_allowed": False,
        "surveillance_display_caveat": (
            "Surveillance context may contain confirmed, suspected, proxy, field, or seeded truth. "
            "Proxy-only label windows must not be presented as confirmed outbreak truth."
        ),
        "surveillance_source_coverage_summary": {
            "record_count": 0,
            "label_window_count": 0,
            "truth_level_counts": {},
            "freshness_state_counts": {},
            "source_type_counts": {},
            "label_window_refs": [],
            "source_record_refs": [],
        },
    }


def _label_truth_state(latest_window: SurveillanceLabelWindow | None) -> str:
    if latest_window is None:
        return "no_surveillance_label_window"
    if latest_window.label_truth_level == SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE:
        return "confirmed_surveillance_truth"
    if latest_window.label_truth_level == SurveillanceTruthLevel.SUSPECTED_SURVEILLANCE:
        return "suspected_surveillance_truth_not_confirmed"
    if latest_window.label_truth_level == SurveillanceTruthLevel.SEEDED_DEMO:
        return "seeded_demo_not_production_truth"
    return "proxy_only_not_confirmed"


def _row_from_records_and_windows(
    *,
    ward: Ward,
    records: list[SurveillanceRecord],
    windows: list[SurveillanceLabelWindow],
) -> dict:
    row = _empty_context_row(ward)
    suspected = sum(record.count_value for record in records if record.case_class == SurveillanceCaseClass.SUSPECTED)
    confirmed = sum(record.count_value for record in records if record.case_class == SurveillanceCaseClass.CONFIRMED)
    proxy = sum(record.count_value for record in records if record.case_class == SurveillanceCaseClass.PROXY)
    latest_record = max(records, key=lambda record: (record.reporting_period_end, record.id), default=None)
    latest_window = max(windows, key=lambda window: (window.label_window_end, window.id), default=None)
    truth_level_counts = Counter(record.truth_level for record in records)
    freshness_state_counts = Counter(record.freshness_state for record in records)
    source_type_counts = Counter(record.source.source_type for record in records if record.source_id)
    source_credibility_counts = Counter((record.raw_payload or {}).get("source_credibility", "unknown") for record in records)

    active_label_count = sum(1 for window in windows if window.outbreak_label == SurveillanceOutbreakLabel.ACTIVE)
    watch_label_count = sum(1 for window in windows if window.outbreak_label == SurveillanceOutbreakLabel.WATCH)
    confirmed_label_count = sum(
        1 for window in windows if window.label_truth_level == SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE
    )
    suspected_label_count = sum(
        1 for window in windows if window.label_truth_level == SurveillanceTruthLevel.SUSPECTED_SURVEILLANCE
    )
    proxy_only_label_count = sum(1 for window in windows if window.label_truth_level in PROXY_ONLY_TRUTH_LEVELS)
    delayed_or_stale_count = sum(1 for record in records if record.freshness_state in DEGRADED_FRESHNESS_STATES)

    row.update(
        {
            "surveillance_recent_suspected_cases_28d": suspected,
            "surveillance_recent_confirmed_cases_28d": confirmed,
            "surveillance_recent_proxy_cases_28d": proxy,
            "surveillance_recent_total_cases_28d": suspected + confirmed + proxy,
            "surveillance_active_label_count_28d": active_label_count,
            "surveillance_watch_label_count_28d": watch_label_count,
            "surveillance_confirmed_label_window_count_28d": confirmed_label_count,
            "surveillance_suspected_label_window_count_28d": suspected_label_count,
            "surveillance_proxy_only_label_window_count_28d": proxy_only_label_count,
            "surveillance_delayed_or_stale_record_count_28d": delayed_or_stale_count,
            "surveillance_latest_label_window_ref": _label_window_ref(latest_window),
            "surveillance_latest_label_dataset_ref": latest_window.dataset_ref if latest_window else None,
            "surveillance_latest_label_truth_level": latest_window.label_truth_level if latest_window else None,
            "surveillance_latest_freshness_state": latest_record.freshness_state if latest_record else None,
            "surveillance_label_truth_state": _label_truth_state(latest_window),
            "surveillance_source_coverage_summary": {
                "record_count": len(records),
                "label_window_count": len(windows),
                "truth_level_counts": dict(truth_level_counts),
                "source_credibility_counts": dict(source_credibility_counts),
                "freshness_state_counts": dict(freshness_state_counts),
                "source_type_counts": dict(source_type_counts),
                "label_window_refs": [_label_window_ref(window) for window in windows],
                "source_record_refs": [f"surveillance_record:{record.id}" for record in records],
            },
        }
    )
    return row


def build_surveillance_feature_snapshot(
    wards: Iterable[Ward],
    *,
    as_of: datetime | None = None,
    lookback_days: int = SURVEILLANCE_FEATURE_LOOKBACK_DAYS,
    include_seeded: bool = False,
) -> SurveillanceFeatureSnapshot:
    if lookback_days <= 0:
        raise ValueError("lookback_days must be greater than zero.")

    as_of = _normalise_as_of(as_of)
    as_of_date = as_of.date()
    lookback_start = as_of_date - timedelta(days=lookback_days - 1)
    ward_list = list(wards)
    ward_ids = [ward.id for ward in ward_list]

    records_queryset = (
        SurveillanceRecord.objects.filter(
            ward_id__in=ward_ids,
            created_at__lte=as_of,
            reporting_period_start__lte=as_of_date,
            reporting_period_end__gte=lookback_start,
        )
        .exclude(freshness_state=SurveillanceFreshnessState.REPLAY_DIAGNOSTIC)
        .select_related("source")
        .order_by("ward_id", "reporting_period_start", "id")
    )
    windows_queryset = SurveillanceLabelWindow.objects.filter(
        ward_id__in=ward_ids,
        created_at__lte=as_of,
        label_window_start__lte=as_of_date,
        label_window_end__gte=lookback_start,
    ).order_by("ward_id", "label_window_start", "id")
    if not include_seeded:
        records_queryset = records_queryset.exclude(truth_level=SurveillanceTruthLevel.SEEDED_DEMO)
        windows_queryset = windows_queryset.exclude(label_truth_level=SurveillanceTruthLevel.SEEDED_DEMO)

    records_by_ward_id: dict[int, list[SurveillanceRecord]] = defaultdict(list)
    for record in records_queryset:
        if record_is_superseded_by_correction(record):
            continue
        records_by_ward_id[record.ward_id].append(record)

    candidate_windows = list(windows_queryset)
    latest_window_by_key: dict[tuple[int, object, object], SurveillanceLabelWindow] = {}
    for window in candidate_windows:
        key = (window.ward_id, window.label_window_start, window.label_window_end)
        current = latest_window_by_key.get(key)
        if current is None or (window.created_at, window.id) > (current.created_at, current.id):
            latest_window_by_key[key] = window

    windows_by_ward_id: dict[int, list[SurveillanceLabelWindow]] = defaultdict(list)
    for window in sorted(
        latest_window_by_key.values(),
        key=lambda label_window: (label_window.ward_id, label_window.label_window_start, label_window.id),
    ):
        windows_by_ward_id[window.ward_id].append(window)

    rows_by_ward_id = {
        ward.id: _row_from_records_and_windows(
            ward=ward,
            records=records_by_ward_id.get(ward.id, []),
            windows=windows_by_ward_id.get(ward.id, []),
        )
        for ward in ward_list
    }
    rows = list(rows_by_ward_id.values())
    coverage = {
        "schema_version": SURVEILLANCE_FEATURE_SCHEMA_VERSION,
        "as_of": as_of.isoformat(),
        "lookback_days": lookback_days,
        "ward_count": len(ward_list),
        "ward_with_record_count": sum(
            1 for row in rows if row["surveillance_source_coverage_summary"]["record_count"] > 0
        ),
        "ward_with_label_window_count": sum(
            1 for row in rows if row["surveillance_source_coverage_summary"]["label_window_count"] > 0
        ),
        "record_count": sum(row["surveillance_source_coverage_summary"]["record_count"] for row in rows),
        "candidate_label_window_count": len(candidate_windows),
        "label_window_count": sum(row["surveillance_source_coverage_summary"]["label_window_count"] for row in rows),
        "label_window_deduplication": "latest_window_per_ward_start_end",
        "active_label_count": sum(row["surveillance_active_label_count_28d"] for row in rows),
        "watch_label_count": sum(row["surveillance_watch_label_count_28d"] for row in rows),
        "confirmed_label_window_count": sum(row["surveillance_confirmed_label_window_count_28d"] for row in rows),
        "suspected_label_window_count": sum(row["surveillance_suspected_label_window_count_28d"] for row in rows),
        "proxy_only_label_window_count": sum(row["surveillance_proxy_only_label_window_count_28d"] for row in rows),
        "delayed_or_stale_record_count": sum(row["surveillance_delayed_or_stale_record_count_28d"] for row in rows),
    }
    truth_gate = {
        "proxy_only_as_confirmed_allowed": False,
        "confirmed_truth_required_for_confirmed_outbreak_claims": True,
        "proxy_only_label_window_count": coverage["proxy_only_label_window_count"],
        "confirmed_label_window_count": coverage["confirmed_label_window_count"],
        "seeded_labels_included": include_seeded,
        "operational_alerts_must_cite_label_truth_state": True,
    }
    return SurveillanceFeatureSnapshot(
        rows_by_ward_id=rows_by_ward_id,
        feature_keys=SURVEILLANCE_CONTEXT_FEATURE_KEYS,
        coverage=coverage,
        truth_gate=truth_gate,
        as_of=as_of,
        lookback_days=lookback_days,
    )


def build_surveillance_feature_context_for_ward(
    ward: Ward,
    *,
    as_of: datetime | None = None,
    lookback_days: int = SURVEILLANCE_FEATURE_LOOKBACK_DAYS,
) -> dict:
    snapshot = build_surveillance_feature_snapshot([ward], as_of=as_of, lookback_days=lookback_days)
    return {
        **snapshot.rows_by_ward_id[ward.id],
        "coverage": snapshot.coverage,
        "truth_gate": snapshot.truth_gate,
        "schema_version": SURVEILLANCE_FEATURE_SCHEMA_VERSION,
        "lookback_days": lookback_days,
    }


def build_surveillance_lead_time_validation_summary(
    *,
    label_dataset: FeatureDataset | None,
    prediction_ward_ids: Iterable[int] | None = None,
    horizons: tuple[int, ...] = (7, 14),
) -> dict:
    if label_dataset is None:
        return {
            "status": "not_available",
            "validation_mode": "surveillance_label_dataset_missing",
            "label_dataset_ref": None,
            "horizons": list(horizons),
            "truth_gate": {
                "proxy_only_as_confirmed_allowed": False,
                "confirmed_truth_required_for_confirmed_outbreak_claims": True,
            },
        }

    lineage = label_dataset.lineage_metadata or {}
    feature_keys = label_dataset.feature_keys or []
    ward_ids = list(prediction_ward_ids or [])
    if (
        lineage.get("generation_mode") == SURVEILLANCE_LEAD_TIME_LABEL_GENERATION_MODE
        or "prediction_date" in feature_keys
    ):
        rows_queryset = FeatureDatasetRow.objects.filter(dataset=label_dataset).select_related("ward")
        if ward_ids:
            rows_queryset = rows_queryset.filter(ward_id__in=ward_ids)
        rows = list(rows_queryset.order_by("id"))
        row_values = [row.feature_values or {} for row in rows]
        truth_levels = [
            values.get("truth_level") or values.get("label_truth_level")
            for values in row_values
            if values.get("truth_level") or values.get("label_truth_level")
        ]
        proxy_only_count = sum(1 for truth_level in truth_levels if truth_level in PROXY_ONLY_TRUTH_LEVELS)
        confirmed_count = sum(
            1 for truth_level in truth_levels if truth_level == SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE
        )
        active_count = sum(
            1
            for row, values in zip(rows, row_values)
            if row.label == 1 or values.get("outbreak_label") == SurveillanceOutbreakLabel.ACTIVE
        )
        watch_count = sum(1 for values in row_values if values.get("outbreak_label") == SurveillanceOutbreakLabel.WATCH)
        prediction_dates = sorted({values.get("prediction_date") for values in row_values if values.get("prediction_date")})
        lead_time_start_days = lineage.get("label_window_start_offset_days")
        lead_time_end_days = lineage.get("label_window_end_offset_days")
        late_revision_state_counts = dict(
            Counter(values.get("late_revision_state", "unknown") for values in row_values)
        )
        horizon_summaries = {}
        for horizon in horizons:
            horizon_in_band = (
                isinstance(lead_time_start_days, int)
                and isinstance(lead_time_end_days, int)
                and lead_time_start_days <= horizon <= lead_time_end_days
            )
            horizon_summaries[str(horizon)] = {
                "matching_label_window_count": len(rows) if horizon_in_band else 0,
                "active_label_count": active_count if horizon_in_band else 0,
                "confirmed_truth_label_count": confirmed_count if horizon_in_band else 0,
                "suspected_truth_label_count": sum(
                    1 for truth_level in truth_levels if truth_level == SurveillanceTruthLevel.SUSPECTED_SURVEILLANCE
                )
                if horizon_in_band
                else 0,
                "proxy_only_label_window_count": proxy_only_count if horizon_in_band else 0,
            }

        return {
            "status": "ready_for_7_to_14_day_evaluation" if rows else "not_ready_no_matching_rows",
            "validation_mode": "future_7_to_14_day_surveillance_label_window_alignment",
            "label_dataset_ref": label_dataset.dataset_ref,
            "label_feature_dataset_id": label_dataset.id,
            "schema_version": label_dataset.schema_version,
            "generation_mode": lineage.get("generation_mode"),
            "prediction_ward_count": len(set(ward_ids)) if ward_ids else None,
            "prediction_date_count": len(prediction_dates),
            "prediction_dates": prediction_dates,
            "lead_time_start_days": lead_time_start_days,
            "lead_time_end_days": lead_time_end_days,
            "matching_label_window_count": len(rows),
            "active_label_count": active_count,
            "watch_label_count": watch_count,
            "confirmed_truth_label_count": confirmed_count,
            "proxy_only_label_window_count": proxy_only_count,
            "late_revision_state_counts": late_revision_state_counts,
            "rows_with_prediction_date_count": sum(1 for values in row_values if values.get("prediction_date")),
            "correction_replay_contract": lineage.get("correction_replay_contract", {}),
            "horizons": horizon_summaries,
            "truth_gate": {
                "proxy_only_as_confirmed_allowed": False,
                "confirmed_truth_required_for_confirmed_outbreak_claims": True,
                "proxy_only_label_window_count": proxy_only_count,
                "confirmed_truth_label_count": confirmed_count,
                "evaluation_can_separate_confirmed_from_proxy": True,
            },
        }

    queryset = SurveillanceLabelWindow.objects.filter(feature_dataset=label_dataset).select_related("ward")
    if ward_ids:
        queryset = queryset.filter(ward_id__in=ward_ids)
    windows = list(queryset.order_by("label_window_start", "id"))
    proxy_only_count = sum(1 for window in windows if window.label_truth_level in PROXY_ONLY_TRUTH_LEVELS)
    confirmed_count = sum(
        1 for window in windows if window.label_truth_level == SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE
    )
    horizon_summaries = {}
    for horizon in horizons:
        horizon_windows = [
            window
            for window in windows
            if (window.label_window_end - window.label_window_start).days + 1 <= horizon
        ]
        horizon_summaries[str(horizon)] = {
            "matching_label_window_count": len(horizon_windows),
            "active_label_count": sum(
                1 for window in horizon_windows if window.outbreak_label == SurveillanceOutbreakLabel.ACTIVE
            ),
            "confirmed_truth_label_count": sum(
                1
                for window in horizon_windows
                if window.label_truth_level == SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE
            ),
            "suspected_truth_label_count": sum(
                1
                for window in horizon_windows
                if window.label_truth_level == SurveillanceTruthLevel.SUSPECTED_SURVEILLANCE
            ),
            "proxy_only_label_window_count": sum(
                1 for window in horizon_windows if window.label_truth_level in PROXY_ONLY_TRUTH_LEVELS
            ),
        }

    return {
        "status": "ready_for_lead_time_review" if windows else "not_ready_no_matching_windows",
        "validation_mode": "retrospective_surveillance_label_window_alignment",
        "label_dataset_ref": label_dataset.dataset_ref,
        "label_feature_dataset_id": label_dataset.id,
        "schema_version": label_dataset.schema_version,
        "prediction_ward_count": len(set(ward_ids)) if ward_ids else None,
        "matching_label_window_count": len(windows),
        "active_label_count": sum(1 for window in windows if window.outbreak_label == SurveillanceOutbreakLabel.ACTIVE),
        "watch_label_count": sum(1 for window in windows if window.outbreak_label == SurveillanceOutbreakLabel.WATCH),
        "confirmed_truth_label_count": confirmed_count,
        "proxy_only_label_window_count": proxy_only_count,
        "horizons": horizon_summaries,
        "truth_gate": {
            "proxy_only_as_confirmed_allowed": False,
            "confirmed_truth_required_for_confirmed_outbreak_claims": True,
            "proxy_only_label_window_count": proxy_only_count,
            "confirmed_truth_label_count": confirmed_count,
        },
    }
