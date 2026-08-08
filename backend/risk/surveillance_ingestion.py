from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from risk.models import (
    FeatureDataset,
    HealthFacility,
    SurveillanceCaseClass,
    SurveillanceDiseaseCategory,
    SurveillanceFreshnessState,
    SurveillanceIngestionRun,
    SurveillanceOutbreakLabel,
    SurveillanceRecord,
    SurveillanceSource,
    SurveillanceSourceKind,
    SurveillanceTruthLevel,
    Ward,
)
from .truth_policy import (
    PRODUCTION_SEEDED_TRUTH_BLOCKED,
    PRODUCTION_UNMAPPED_WARD_BLOCKED,
    require_seeded_truth_allowed,
)
from .surveillance_lineage import reconcile_surveillance_label_lineage


MAX_REJECTED_ROW_DETAILS = 25
MAX_SAMPLE_ROWS = 5

TRUTH_LEVEL_CONFIRMED = SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE
TRUTH_LEVEL_SUSPECTED = SurveillanceTruthLevel.SUSPECTED_SURVEILLANCE
TRUTH_LEVEL_PROXY = SurveillanceTruthLevel.PROXY_DIARRHEAL_SIGNAL
TRUTH_LEVEL_FIELD = SurveillanceTruthLevel.FIELD_SIGNAL_ONLY
TRUTH_LEVEL_SEEDED = SurveillanceTruthLevel.SEEDED_DEMO
SURVEILLANCE_TRUTH_LEVELS = frozenset(choice[0] for choice in SurveillanceTruthLevel.choices)


def _columns(*names: str) -> frozenset[str]:
    return frozenset(names)


WARD_KEY_COLUMNS = _columns("ward_id", "ward_code", "ward_name")
FACILITY_KEY_COLUMNS = _columns("facility_id", "facility_code", "facility_name")
PERIOD_START_COLUMNS = _columns("reporting_period_start", "period_start", "week_start", "date")
PERIOD_END_COLUMNS = _columns("reporting_period_end", "period_end", "week_end", "date")
COUNT_COLUMNS = _columns(
    "suspected_cholera_count",
    "suspected_case_count",
    "suspected_cases",
    "confirmed_cholera_count",
    "confirmed_case_count",
    "confirmed_cases",
    "diarrheal_count",
    "diarrhoea_count",
    "proxy_case_count",
    "case_count",
    "count_value",
)


@dataclass(frozen=True)
class SurveillanceAdapterSpec:
    source_type: str
    adapter_key: str
    required_any_columns: tuple[frozenset[str], ...]
    accepted_columns: frozenset[str]
    scheduled_supported: bool
    default_reporting_granularity: str
    notes: str


@dataclass(frozen=True)
class SurveillanceFeedPolicy:
    source_type: str
    expected_reporting_lag_days: int
    stale_after_days: int
    catch_up_supported: bool
    trusted_push_supported: bool
    delayed_behavior: str
    stale_behavior: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "expected_reporting_lag_days": self.expected_reporting_lag_days,
            "stale_after_days": self.stale_after_days,
            "catch_up_supported": self.catch_up_supported,
            "trusted_push_supported": self.trusted_push_supported,
            "delayed_behavior": self.delayed_behavior,
            "stale_behavior": self.stale_behavior,
        }


BASE_ACCEPTED_COLUMNS = _columns(
    "ward_id",
    "ward_code",
    "ward_name",
    "facility_id",
    "facility_code",
    "facility_name",
    "source_name",
    "source_type",
    "source_timestamp",
    "reporting_period_start",
    "reporting_period_end",
    "period_start",
    "period_end",
    "week_start",
    "week_end",
    "date",
    "source_ref",
    "operator_note",
    "correction_reason",
    "amendment_flag",
    "revision_number",
    "supersedes_record_ref",
    "reporting_granularity",
    "disease_category",
    "case_class",
    "truth_level",
    "source_kind",
    "freshness_state",
    "outbreak_label",
    "source_system",
    "provider",
    "provider_record_id",
    "provider_org_unit",
    "provider_org_unit_id",
    "provider_data_element",
    "provider_data_element_id",
    "dhis2_period",
    "dhis2_dataset",
    "dhis2_org_unit",
    "dhis2_org_unit_id",
    "dhis2_data_element",
    "dhis2_data_element_id",
    "dhis2_category_option_combo",
    "dhis2_instance_hostname",
    "dhis2_api_resource",
    "dhis2_query_hash",
    "dhis2_source_reference_hash",
    "dhis2_query_identity_hash",
    "dhis2_response_payload_hash",
    "dhis2_row_identity_hash",
    "dhis2_retrieved_at",
    "dhis2_mapping_version",
    "dhis2_connector_run_id",
    "notes",
)


SURVEILLANCE_ADAPTERS: dict[str, SurveillanceAdapterSpec] = {
    SurveillanceSource.SOURCE_TYPE_WEEKLY_AGGREGATE: SurveillanceAdapterSpec(
        source_type=SurveillanceSource.SOURCE_TYPE_WEEKLY_AGGREGATE,
        adapter_key="surveillance_weekly_aggregate_csv",
        required_any_columns=(WARD_KEY_COLUMNS | FACILITY_KEY_COLUMNS, PERIOD_START_COLUMNS, PERIOD_END_COLUMNS, COUNT_COLUMNS),
        accepted_columns=BASE_ACCEPTED_COLUMNS | COUNT_COLUMNS,
        scheduled_supported=True,
        default_reporting_granularity="week",
        notes="Weekly public-health aggregate or partner export with explicit reporting week.",
    ),
    SurveillanceSource.SOURCE_TYPE_DAILY_AGGREGATE: SurveillanceAdapterSpec(
        source_type=SurveillanceSource.SOURCE_TYPE_DAILY_AGGREGATE,
        adapter_key="surveillance_daily_aggregate_csv",
        required_any_columns=(WARD_KEY_COLUMNS | FACILITY_KEY_COLUMNS, PERIOD_START_COLUMNS, PERIOD_END_COLUMNS, COUNT_COLUMNS),
        accepted_columns=BASE_ACCEPTED_COLUMNS | COUNT_COLUMNS,
        scheduled_supported=True,
        default_reporting_granularity="day",
        notes="Daily aggregate where the reporting source truly reports daily.",
    ),
    SurveillanceSource.SOURCE_TYPE_LINE_LIST_SUMMARY: SurveillanceAdapterSpec(
        source_type=SurveillanceSource.SOURCE_TYPE_LINE_LIST_SUMMARY,
        adapter_key="surveillance_line_list_summary_csv",
        required_any_columns=(WARD_KEY_COLUMNS | FACILITY_KEY_COLUMNS, PERIOD_START_COLUMNS, PERIOD_END_COLUMNS, COUNT_COLUMNS),
        accepted_columns=BASE_ACCEPTED_COLUMNS | COUNT_COLUMNS | _columns("line_list_ref", "deduplication_method"),
        scheduled_supported=False,
        default_reporting_granularity="week",
        notes="Line-list rollup import; raw person-level line lists stay outside the model feature path.",
    ),
    SurveillanceSource.SOURCE_TYPE_TRUSTED_PUSH: SurveillanceAdapterSpec(
        source_type=SurveillanceSource.SOURCE_TYPE_TRUSTED_PUSH,
        adapter_key="surveillance_trusted_push_csv",
        required_any_columns=(WARD_KEY_COLUMNS | FACILITY_KEY_COLUMNS, PERIOD_START_COLUMNS, PERIOD_END_COLUMNS, COUNT_COLUMNS),
        accepted_columns=BASE_ACCEPTED_COLUMNS | COUNT_COLUMNS | _columns("provider_event_id", "push_batch_id"),
        scheduled_supported=True,
        default_reporting_granularity="week",
        notes="Partner-governed push or export that can later map to DHIS2/API payloads.",
    ),
    SurveillanceSource.SOURCE_TYPE_CSV_BACKFILL: SurveillanceAdapterSpec(
        source_type=SurveillanceSource.SOURCE_TYPE_CSV_BACKFILL,
        adapter_key="surveillance_csv_backfill",
        required_any_columns=(WARD_KEY_COLUMNS | FACILITY_KEY_COLUMNS, PERIOD_START_COLUMNS, PERIOD_END_COLUMNS, COUNT_COLUMNS),
        accepted_columns=BASE_ACCEPTED_COLUMNS | COUNT_COLUMNS | _columns("backfill_batch_id"),
        scheduled_supported=False,
        default_reporting_granularity="week",
        notes="Manual historical backfill envelope for county or partner surveillance spreadsheets.",
    ),
    SurveillanceSource.SOURCE_TYPE_FIELD_SIGNAL: SurveillanceAdapterSpec(
        source_type=SurveillanceSource.SOURCE_TYPE_FIELD_SIGNAL,
        adapter_key="surveillance_field_signal_csv",
        required_any_columns=(WARD_KEY_COLUMNS | FACILITY_KEY_COLUMNS, PERIOD_START_COLUMNS, PERIOD_END_COLUMNS, COUNT_COLUMNS | _columns("outbreak_label")),
        accepted_columns=BASE_ACCEPTED_COLUMNS | COUNT_COLUMNS | _columns("field_signal_ref", "symptom_signal"),
        scheduled_supported=False,
        default_reporting_granularity="day",
        notes="Internal CHV or triage support signal; never upgraded to confirmed surveillance truth by default.",
    ),
    SurveillanceSource.SOURCE_TYPE_FACILITY_PROXY: SurveillanceAdapterSpec(
        source_type=SurveillanceSource.SOURCE_TYPE_FACILITY_PROXY,
        adapter_key="surveillance_facility_proxy_csv",
        required_any_columns=(FACILITY_KEY_COLUMNS, PERIOD_START_COLUMNS, PERIOD_END_COLUMNS, COUNT_COLUMNS),
        accepted_columns=BASE_ACCEPTED_COLUMNS | COUNT_COLUMNS | _columns("encounter_type", "admission_count"),
        scheduled_supported=False,
        default_reporting_granularity="week",
        notes="Facility burden proxy import; useful for forecasting context but not confirmed ward truth.",
    ),
}


SURVEILLANCE_FEED_POLICIES: dict[str, SurveillanceFeedPolicy] = {
    SurveillanceSource.SOURCE_TYPE_WEEKLY_AGGREGATE: SurveillanceFeedPolicy(
        source_type=SurveillanceSource.SOURCE_TYPE_WEEKLY_AGGREGATE,
        expected_reporting_lag_days=7,
        stale_after_days=14,
        catch_up_supported=True,
        trusted_push_supported=False,
        delayed_behavior="preserve_records_with_delayed_freshness_and_include_in_labels",
        stale_behavior="preserve_records_with_stale_freshness_and_surface_in_lineage",
    ),
    SurveillanceSource.SOURCE_TYPE_DAILY_AGGREGATE: SurveillanceFeedPolicy(
        source_type=SurveillanceSource.SOURCE_TYPE_DAILY_AGGREGATE,
        expected_reporting_lag_days=2,
        stale_after_days=5,
        catch_up_supported=True,
        trusted_push_supported=False,
        delayed_behavior="preserve_records_with_delayed_freshness_and_include_in_labels",
        stale_behavior="preserve_records_with_stale_freshness_and_surface_in_lineage",
    ),
    SurveillanceSource.SOURCE_TYPE_LINE_LIST_SUMMARY: SurveillanceFeedPolicy(
        source_type=SurveillanceSource.SOURCE_TYPE_LINE_LIST_SUMMARY,
        expected_reporting_lag_days=14,
        stale_after_days=30,
        catch_up_supported=True,
        trusted_push_supported=False,
        delayed_behavior="preserve_line_list_rollup_with_delayed_freshness",
        stale_behavior="preserve_for_history_but_surface_as_stale_lineage",
    ),
    SurveillanceSource.SOURCE_TYPE_TRUSTED_PUSH: SurveillanceFeedPolicy(
        source_type=SurveillanceSource.SOURCE_TYPE_TRUSTED_PUSH,
        expected_reporting_lag_days=2,
        stale_after_days=5,
        catch_up_supported=True,
        trusted_push_supported=True,
        delayed_behavior="accept_push_with_delayed_freshness_and_alert_lineage_consumers",
        stale_behavior="accept_push_with_stale_freshness_and_require_review_before_operational_use",
    ),
    SurveillanceSource.SOURCE_TYPE_CSV_BACKFILL: SurveillanceFeedPolicy(
        source_type=SurveillanceSource.SOURCE_TYPE_CSV_BACKFILL,
        expected_reporting_lag_days=30,
        stale_after_days=90,
        catch_up_supported=True,
        trusted_push_supported=False,
        delayed_behavior="preserve_historical_backfill_with_delayed_freshness",
        stale_behavior="preserve_historical_backfill_with_stale_freshness",
    ),
    SurveillanceSource.SOURCE_TYPE_FIELD_SIGNAL: SurveillanceFeedPolicy(
        source_type=SurveillanceSource.SOURCE_TYPE_FIELD_SIGNAL,
        expected_reporting_lag_days=1,
        stale_after_days=3,
        catch_up_supported=False,
        trusted_push_supported=False,
        delayed_behavior="preserve_field_signal_as_delayed_weak_context",
        stale_behavior="preserve_field_signal_as_stale_weak_context",
    ),
    SurveillanceSource.SOURCE_TYPE_FACILITY_PROXY: SurveillanceFeedPolicy(
        source_type=SurveillanceSource.SOURCE_TYPE_FACILITY_PROXY,
        expected_reporting_lag_days=7,
        stale_after_days=14,
        catch_up_supported=True,
        trusted_push_supported=False,
        delayed_behavior="preserve_facility_proxy_as_delayed_weak_context",
        stale_behavior="preserve_facility_proxy_as_stale_weak_context",
    ),
}


def normalize_column_name(value: str | None) -> str:
    return "_".join((value or "").strip().lower().replace("-", "_").split())


def parse_surveillance_source_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def parse_surveillance_date(value: str | date | datetime | None) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    normalized = str(value).strip()
    if not normalized:
        return None
    return datetime.fromisoformat(normalized.replace("Z", "+00:00")).date()


def adapter_spec_for_surveillance_source_type(source_type: str) -> SurveillanceAdapterSpec:
    try:
        return SURVEILLANCE_ADAPTERS[source_type]
    except KeyError as error:
        choices = ", ".join(sorted(SURVEILLANCE_ADAPTERS))
        raise ValueError(f"Unsupported surveillance source_type '{source_type}'. Expected one of: {choices}") from error


def feed_policy_for_surveillance_source_type(source_type: str) -> SurveillanceFeedPolicy:
    adapter_spec_for_surveillance_source_type(source_type)
    return SURVEILLANCE_FEED_POLICIES[source_type]


def _feed_contract_for_source_type(source_type: str) -> dict[str, Any]:
    spec = adapter_spec_for_surveillance_source_type(source_type)
    policy = feed_policy_for_surveillance_source_type(source_type)
    return {
        **policy.as_dict(),
        "adapter_key": spec.adapter_key,
        "scheduled_supported": spec.scheduled_supported,
        "default_reporting_granularity": spec.default_reporting_granularity,
        "replay_diagnostic_records_excluded_from_label_generation": True,
    }


def _has_any_value(row: dict[str, Any], columns: frozenset[str]) -> bool:
    return any(str(row.get(column, "")).strip() for column in columns)


def _first_nonempty(row: dict[str, Any], *columns: str) -> str:
    for column in columns:
        value = row.get(column)
        if value is None:
            continue
        text = str(value).strip()
        if text and text.lower() not in {"null", "none", "nan"}:
            return text
    return ""


def _parse_nonnegative_int(value: str | int | float | None) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(float(str(value).replace(",", "").strip()))
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def _normalize_choice(value: str) -> str:
    return "_".join(value.strip().lower().replace("-", "_").split())


def _normalized_csv_rows(file_path: str | Path) -> tuple[list[str], list[dict[str, Any]]]:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Surveillance import file does not exist: {path}")

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


def _case_counts_for_row(row: dict[str, Any]) -> dict[str, int]:
    suspected = _parse_nonnegative_int(_first_nonempty(row, "suspected_cholera_count", "suspected_case_count", "suspected_cases"))
    confirmed = _parse_nonnegative_int(_first_nonempty(row, "confirmed_cholera_count", "confirmed_case_count", "confirmed_cases"))
    diarrheal = _parse_nonnegative_int(_first_nonempty(row, "diarrheal_count", "diarrhoea_count"))
    proxy = _parse_nonnegative_int(_first_nonempty(row, "proxy_case_count"))
    generic = _parse_nonnegative_int(_first_nonempty(row, "case_count", "count_value"))
    case_class = _normalize_choice(_first_nonempty(row, "case_class"))

    counts = {}
    if suspected is not None:
        counts["suspected"] = suspected
    if confirmed is not None:
        counts["confirmed"] = confirmed
    if diarrheal is not None:
        counts["diarrheal_proxy"] = diarrheal
    if proxy is not None:
        counts["proxy"] = proxy
    if generic is not None and case_class in {"confirmed", "suspected", "proxy"}:
        counts[case_class] = generic
    elif generic is not None and "suspected" not in counts:
        counts["suspected"] = generic
    return counts


def _truth_level_for_row(row: dict[str, Any], *, source_type: str, source_name: str) -> str:
    supplied = _normalize_choice(_first_nonempty(row, "truth_level"))
    if supplied in SURVEILLANCE_TRUTH_LEVELS:
        return supplied
    if "seed" in source_name.lower():
        return TRUTH_LEVEL_SEEDED
    if source_type == SurveillanceSource.SOURCE_TYPE_FIELD_SIGNAL:
        return TRUTH_LEVEL_FIELD
    if source_type == SurveillanceSource.SOURCE_TYPE_FACILITY_PROXY:
        return TRUTH_LEVEL_PROXY

    counts = _case_counts_for_row(row)
    case_class = _normalize_choice(_first_nonempty(row, "case_class"))
    if case_class == SurveillanceCaseClass.CONFIRMED:
        return TRUTH_LEVEL_CONFIRMED
    if counts.get("confirmed", 0) > 0:
        return TRUTH_LEVEL_CONFIRMED
    if "confirmed" in counts and set(counts) == {"confirmed"}:
        return TRUTH_LEVEL_CONFIRMED
    if case_class == SurveillanceCaseClass.SUSPECTED or "suspected" in counts:
        return TRUTH_LEVEL_SUSPECTED
    return TRUTH_LEVEL_PROXY


def _disease_category_for_row(row: dict[str, Any]) -> str:
    supplied = _normalize_choice(_first_nonempty(row, "disease_category"))
    if supplied in {"cholera", "diarrheal"}:
        return supplied
    if _first_nonempty(row, "diarrheal_count", "diarrhoea_count"):
        return "diarrheal"
    return "cholera"


def _period_for_row(row: dict[str, Any]) -> tuple[date | None, date | None]:
    start = parse_surveillance_date(_first_nonempty(row, "reporting_period_start", "period_start", "week_start", "date"))
    end = parse_surveillance_date(_first_nonempty(row, "reporting_period_end", "period_end", "week_end", "date"))
    return start, end


def _period_bounds(accepted_rows: list[dict[str, Any]]) -> tuple[date | None, date | None]:
    starts = []
    ends = []
    for accepted in accepted_rows:
        start, end = _period_for_row(accepted["row"])
        if start:
            starts.append(start)
        if end:
            ends.append(end)
    return (min(starts) if starts else None, max(ends) if ends else None)


PROVIDER_CONTRACT_COLUMNS = _columns(
    "source_system",
    "provider",
    "provider_record_id",
    "provider_org_unit",
    "provider_org_unit_id",
    "provider_data_element",
    "provider_data_element_id",
    "dhis2_period",
    "dhis2_dataset",
    "dhis2_org_unit",
    "dhis2_org_unit_id",
    "dhis2_data_element",
    "dhis2_data_element_id",
    "dhis2_category_option_combo",
    "dhis2_instance_hostname",
    "dhis2_api_resource",
    "dhis2_query_hash",
    "dhis2_source_reference_hash",
    "dhis2_query_identity_hash",
    "dhis2_response_payload_hash",
    "dhis2_row_identity_hash",
    "dhis2_retrieved_at",
    "dhis2_mapping_version",
    "dhis2_connector_run_id",
)


def _provider_import_contract(spec: SurveillanceAdapterSpec) -> dict[str, Any]:
    return {
        "adapter_key": spec.adapter_key,
        "source_type": spec.source_type,
        "feed_policy": _feed_contract_for_source_type(spec.source_type),
        "required_any_columns": [sorted(group) for group in spec.required_any_columns],
        "location_columns": sorted(WARD_KEY_COLUMNS | FACILITY_KEY_COLUMNS),
        "reporting_period_columns": sorted(PERIOD_START_COLUMNS | PERIOD_END_COLUMNS),
        "count_columns": sorted(COUNT_COLUMNS),
        "provider_columns": sorted(PROVIDER_CONTRACT_COLUMNS),
        "truth_level_choices": sorted(SURVEILLANCE_TRUTH_LEVELS),
        "default_reporting_granularity": spec.default_reporting_granularity,
    }


def _provider_payload_for_row(row: dict[str, Any]) -> dict[str, str]:
    return {
        column: _first_nonempty(row, column)
        for column in sorted(PROVIDER_CONTRACT_COLUMNS)
        if _first_nonempty(row, column)
    }


def _outbreak_label_for_row(row: dict[str, Any]) -> str:
    supplied = _normalize_choice(_first_nonempty(row, "outbreak_label"))
    valid = {choice[0] for choice in SurveillanceOutbreakLabel.choices}
    if supplied in valid:
        return supplied
    if supplied in {"active_outbreak", "outbreak", "true", "yes", "1"}:
        return SurveillanceOutbreakLabel.ACTIVE
    if supplied in {"watch", "warning", "possible", "signal"}:
        return SurveillanceOutbreakLabel.WATCH
    return SurveillanceOutbreakLabel.NONE


def _reporting_granularity_for_row(row: dict[str, Any], spec: SurveillanceAdapterSpec) -> str:
    supplied = _normalize_choice(_first_nonempty(row, "reporting_granularity"))
    if supplied in {"day", "week"}:
        return supplied
    return spec.default_reporting_granularity


def _find_ward(row: dict[str, Any]) -> Ward | None:
    ward_id = _parse_nonnegative_int(_first_nonempty(row, "ward_id"))
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
    facility_id = _parse_nonnegative_int(_first_nonempty(row, "facility_id"))
    if facility_id is not None:
        facility = HealthFacility.objects.select_related("ward").filter(pk=facility_id).first()
        if facility:
            return facility

    facility_code = _first_nonempty(row, "facility_code")
    if facility_code:
        facility = HealthFacility.objects.select_related("ward").filter(facility_code__iexact=facility_code).first()
        if facility:
            return facility

    facility_name = _first_nonempty(row, "facility_name")
    if facility_name:
        normalized_name = " ".join(facility_name.split())
        return HealthFacility.objects.select_related("ward").filter(name__iexact=normalized_name).order_by("ward__name", "name").first()
    return None


def _source_kind_for_row(row: dict[str, Any], run: SurveillanceIngestionRun, truth_level: str) -> str:
    supplied = _normalize_choice(_first_nonempty(row, "source_kind"))
    valid = {choice[0] for choice in SurveillanceSourceKind.choices}
    if supplied in valid:
        return supplied
    if truth_level == SurveillanceTruthLevel.SEEDED_DEMO or "seed" in run.source_name.lower():
        return SurveillanceSourceKind.SEEDED
    if run.correction_mode == SurveillanceIngestionRun.CORRECTION_BACKFILL or run.source_type == SurveillanceSource.SOURCE_TYPE_CSV_BACKFILL:
        return SurveillanceSourceKind.BACKFILL
    return SurveillanceSourceKind.LIVE


def _submission_date_for_run(run: SurveillanceIngestionRun) -> date:
    if run.source_timestamp:
        return run.source_timestamp.date()
    if run.completed_at:
        return run.completed_at.date()
    if run.started_at:
        return run.started_at.date()
    return timezone.localdate()


def _freshness_evaluation_for_row(
    row: dict[str, Any],
    run: SurveillanceIngestionRun,
    *,
    period_end: date | None,
) -> dict[str, Any]:
    supplied = _normalize_choice(_first_nonempty(row, "freshness_state"))
    valid = {choice[0] for choice in SurveillanceFreshnessState.choices}
    policy = feed_policy_for_surveillance_source_type(run.source_type)
    submission_date = _submission_date_for_run(run)
    reporting_lag_days = (submission_date - period_end).days if period_end else None

    if supplied in valid:
        return {
            "freshness_state": supplied,
            "classification_source": "source_supplied",
            "submission_date": submission_date.isoformat(),
            "period_end": period_end.isoformat() if period_end else None,
            "reporting_lag_days": reporting_lag_days,
            "policy": policy.as_dict(),
        }
    if run.execution_mode == SurveillanceIngestionRun.EXECUTION_REPLAY:
        return {
            "freshness_state": SurveillanceFreshnessState.REPLAY_DIAGNOSTIC,
            "classification_source": "execution_mode_replay",
            "submission_date": submission_date.isoformat(),
            "period_end": period_end.isoformat() if period_end else None,
            "reporting_lag_days": reporting_lag_days,
            "policy": policy.as_dict(),
        }
    if run.correction_mode == SurveillanceIngestionRun.CORRECTION_AMENDMENT:
        return {
            "freshness_state": SurveillanceFreshnessState.CORRECTED_AFTER_INITIAL_SUBMISSION,
            "classification_source": "correction_mode_amendment",
            "submission_date": submission_date.isoformat(),
            "period_end": period_end.isoformat() if period_end else None,
            "reporting_lag_days": reporting_lag_days,
            "policy": policy.as_dict(),
        }
    if period_end is None:
        return {
            "freshness_state": SurveillanceFreshnessState.UNKNOWN,
            "classification_source": "missing_period_end",
            "submission_date": submission_date.isoformat(),
            "period_end": None,
            "reporting_lag_days": None,
            "policy": policy.as_dict(),
        }

    if reporting_lag_days is not None and reporting_lag_days > policy.stale_after_days:
        freshness_state = SurveillanceFreshnessState.STALE
        classification_source = "derived_from_feed_policy_stale"
    elif reporting_lag_days is not None and reporting_lag_days > policy.expected_reporting_lag_days:
        freshness_state = SurveillanceFreshnessState.DELAYED
        classification_source = "derived_from_feed_policy_delayed"
    else:
        freshness_state = SurveillanceFreshnessState.FRESH
        classification_source = "derived_from_feed_policy_fresh"

    return {
        "freshness_state": freshness_state,
        "classification_source": classification_source,
        "submission_date": submission_date.isoformat(),
        "period_end": period_end.isoformat(),
        "reporting_lag_days": reporting_lag_days,
        "policy": policy.as_dict(),
    }


def _source_credibility_for_truth_level(truth_level: str) -> str:
    if truth_level == SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE:
        return "high"
    if truth_level == SurveillanceTruthLevel.SUSPECTED_SURVEILLANCE:
        return "medium"
    if truth_level == SurveillanceTruthLevel.SEEDED_DEMO:
        return "demo_only"
    return "low"


def _seeded_non_production_metadata() -> dict[str, Any]:
    return {
        "seeded": True,
        "seeded_non_production": True,
        "production_use_allowed": False,
        "operational_use": "demo_only_not_for_real_evaluation",
    }


def _surveillance_record_ref(record: SurveillanceRecord) -> str:
    return f"surveillance_record:{record.id}"


def _parse_surveillance_record_ref(value: str) -> int | None:
    text = (value or "").strip()
    if text.startswith("surveillance_record:"):
        text = text.split(":", 1)[1]
    if text.isdigit():
        return int(text)
    return None


def _truth_level_for_record(*, row: dict[str, Any], run: SurveillanceIngestionRun, case_class: str) -> str:
    supplied = _normalize_choice(_first_nonempty(row, "truth_level"))
    if supplied == SurveillanceTruthLevel.SEEDED_DEMO or "seed" in run.source_name.lower():
        return SurveillanceTruthLevel.SEEDED_DEMO
    if run.source_type == SurveillanceSource.SOURCE_TYPE_FIELD_SIGNAL:
        return SurveillanceTruthLevel.FIELD_SIGNAL_ONLY
    if run.source_type == SurveillanceSource.SOURCE_TYPE_FACILITY_PROXY:
        return SurveillanceTruthLevel.PROXY_DIARRHEAL_SIGNAL
    if case_class == SurveillanceCaseClass.CONFIRMED:
        return SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE
    if case_class == SurveillanceCaseClass.SUSPECTED:
        return SurveillanceTruthLevel.SUSPECTED_SURVEILLANCE
    return SurveillanceTruthLevel.PROXY_DIARRHEAL_SIGNAL


def _case_records_for_accepted_row(accepted: dict[str, Any]) -> list[dict[str, Any]]:
    row = accepted["row"]
    case_records = []
    for case_key, count_value in accepted["case_counts"].items():
        if case_key == "confirmed":
            case_records.append(
                {
                    "disease_category": SurveillanceDiseaseCategory.CHOLERA,
                    "case_class": SurveillanceCaseClass.CONFIRMED,
                    "count_value": count_value,
                    "source_count_key": case_key,
                    "count_derived_from_outbreak_label": False,
                }
            )
        elif case_key == "suspected":
            case_records.append(
                {
                    "disease_category": SurveillanceDiseaseCategory.CHOLERA,
                    "case_class": SurveillanceCaseClass.SUSPECTED,
                    "count_value": count_value,
                    "source_count_key": case_key,
                    "count_derived_from_outbreak_label": False,
                }
            )
        elif case_key in {"diarrheal_proxy", "proxy"}:
            case_records.append(
                {
                    "disease_category": SurveillanceDiseaseCategory.DIARRHEAL,
                    "case_class": SurveillanceCaseClass.PROXY,
                    "count_value": count_value,
                    "source_count_key": case_key,
                    "count_derived_from_outbreak_label": False,
                }
            )

    outbreak_label = _outbreak_label_for_row(row)
    if not case_records and outbreak_label != SurveillanceOutbreakLabel.NONE:
        case_records.append(
            {
                "disease_category": SurveillanceDiseaseCategory.DIARRHEAL,
                "case_class": SurveillanceCaseClass.PROXY,
                "count_value": 0,
                "source_count_key": "outbreak_label",
                "count_derived_from_outbreak_label": True,
            }
        )
    return case_records


def _canonical_lineage_for_run(run: SurveillanceIngestionRun) -> dict[str, Any]:
    return {
        "ingestion_run_id": run.id,
        "source_id": run.source_id,
        "replay_of_run_id": run.replay_of_id,
        "execution_mode": run.execution_mode,
        "correction_mode": run.correction_mode,
        "correction_reason": run.correction_reason,
        "source_ref": run.source_ref,
    }


def _canonical_records_for_accepted_row(
    *,
    run: SurveillanceIngestionRun,
    spec: SurveillanceAdapterSpec,
    accepted: dict[str, Any],
) -> tuple[list[SurveillanceRecord], list[dict[str, Any]]]:
    row = accepted["row"]
    row_number = accepted["row_number"]
    period_start, period_end = _period_for_row(row)
    ward = _find_ward(row)
    facility = _find_facility(row)
    errors: list[dict[str, Any]] = []

    if facility and ward and facility.ward_id != ward.id:
        return [], [
            {
                "row_number": row_number,
                "reason": "facility_ward_mismatch",
                "facility_id": facility.id,
                "facility_ward_id": facility.ward_id,
                "ward_id": ward.id,
            }
        ]
    if ward is None and facility:
        ward = facility.ward
    if run.source_type == SurveillanceSource.SOURCE_TYPE_FACILITY_PROXY and facility is None:
        errors.append({"row_number": row_number, "reason": "facility_not_found_for_facility_proxy_record"})
    if ward is None:
        errors.append({"row_number": row_number, "reason": "ward_not_found_for_surveillance_record"})
    if period_start is None or period_end is None:
        errors.append({"row_number": row_number, "reason": "missing_reporting_period_for_canonical_record"})
    if errors:
        return [], errors

    revision_number = _parse_nonnegative_int(_first_nonempty(row, "revision_number")) or (
        2 if run.correction_mode == SurveillanceIngestionRun.CORRECTION_AMENDMENT else 1
    )
    outbreak_label = _outbreak_label_for_row(row)
    provider_payload = _provider_payload_for_row(row)
    reporting_granularity = accepted.get("reporting_granularity") or _reporting_granularity_for_row(row, spec)
    freshness_evaluation = _freshness_evaluation_for_row(row, run, period_end=period_end)
    raw_payload = {
        "row_number": row_number,
        "row": row,
        "case_counts": accepted["case_counts"],
        "row_truth_level": accepted["truth_level"],
        "row_disease_category": accepted["disease_category"],
        "row_reporting_granularity": reporting_granularity,
        "provider_contract": provider_payload,
        "feed_policy": _feed_contract_for_source_type(run.source_type),
        "freshness_evaluation": freshness_evaluation,
        "ingestion_lineage": _canonical_lineage_for_run(run),
    }

    records = []
    for case_record in _case_records_for_accepted_row(accepted):
        truth_level = _truth_level_for_record(row=row, run=run, case_class=case_record["case_class"])
        source_credibility = _source_credibility_for_truth_level(truth_level)
        records.append(
            SurveillanceRecord(
                ward=ward,
                facility=facility,
                ingestion_run=run,
                source=run.source,
                disease_category=case_record["disease_category"],
                case_class=case_record["case_class"],
                outbreak_label=outbreak_label,
                count_value=case_record["count_value"],
                reporting_period_start=period_start,
                reporting_period_end=period_end,
                reporting_granularity=reporting_granularity,
                truth_level=truth_level,
                source_name=run.source_name,
                source_kind=_source_kind_for_row(row, run, truth_level),
                freshness_state=freshness_evaluation["freshness_state"],
                revision_number=revision_number,
                supersedes_record_ref=_first_nonempty(row, "supersedes_record_ref"),
                source_ref=_first_nonempty(row, "source_ref") or run.source_ref,
                raw_payload={
                    **raw_payload,
                    "source_count_key": case_record["source_count_key"],
                    "count_derived_from_outbreak_label": case_record["count_derived_from_outbreak_label"],
                    "source_credibility": source_credibility,
                },
            )
        )

    if not records:
        errors.append({"row_number": row_number, "reason": "no_canonical_surveillance_records"})
    return records, errors


def _mark_superseded_surveillance_records(
    *,
    run: SurveillanceIngestionRun,
    new_records: list[SurveillanceRecord],
) -> dict[str, Any]:
    marked_record_ids: set[int] = set()
    unresolved_refs: list[dict[str, Any]] = []
    superseded_at = timezone.now().isoformat()

    for new_record in new_records:
        supersedes_ref = (new_record.supersedes_record_ref or "").strip()
        if not supersedes_ref:
            continue
        target_id = _parse_surveillance_record_ref(supersedes_ref)
        target_queryset = SurveillanceRecord.objects.exclude(ingestion_run=run).filter(
            ward_id=new_record.ward_id,
            disease_category=new_record.disease_category,
            case_class=new_record.case_class,
            reporting_period_start=new_record.reporting_period_start,
            reporting_period_end=new_record.reporting_period_end,
        )
        if target_id is not None:
            target_queryset = target_queryset.filter(id=target_id)
        else:
            target_queryset = target_queryset.filter(source_ref=supersedes_ref)

        targets = list(target_queryset.order_by("id"))
        if not targets:
            unresolved_refs.append(
                {
                    "new_record_id": new_record.id,
                    "supersedes_record_ref": supersedes_ref,
                    "ward_id": new_record.ward_id,
                    "case_class": new_record.case_class,
                    "reporting_period_start": new_record.reporting_period_start.isoformat(),
                    "reporting_period_end": new_record.reporting_period_end.isoformat(),
                }
            )
            continue

        for target in targets:
            raw_payload = target.raw_payload or {}
            raw_payload["superseded_by_record_ref"] = _surveillance_record_ref(new_record)
            raw_payload["superseded_by_run_id"] = run.id
            raw_payload["superseded_at"] = superseded_at
            raw_payload["superseded_correction_reason"] = run.correction_reason
            target.raw_payload = raw_payload
            target.save(update_fields=["raw_payload"])
            marked_record_ids.add(target.id)

    return {
        "records_with_supersedes_ref": sum(1 for record in new_records if record.supersedes_record_ref),
        "superseded_record_count": len(marked_record_ids),
        "superseded_record_ids": sorted(marked_record_ids),
        "superseded_record_ids_sample": sorted(marked_record_ids)[:MAX_REJECTED_ROW_DETAILS],
        "unresolved_supersedes_refs": unresolved_refs[:MAX_REJECTED_ROW_DETAILS],
    }


def _persist_canonical_surveillance_records_for_run(
    run: SurveillanceIngestionRun,
    accepted_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    spec = adapter_spec_for_surveillance_source_type(run.source_type)
    records: list[SurveillanceRecord] = []
    canonical_rejections: list[dict[str, Any]] = []
    normalized_row_numbers: set[int] = set()

    for accepted in accepted_rows:
        row_records, row_errors = _canonical_records_for_accepted_row(run=run, spec=spec, accepted=accepted)
        records.extend(row_records)
        canonical_rejections.extend(row_errors)
        if row_records:
            normalized_row_numbers.add(accepted["row_number"])

    SurveillanceRecord.objects.bulk_create(records)
    records = list(SurveillanceRecord.objects.filter(ingestion_run=run).order_by("id"))
    supersession_summary = _mark_superseded_surveillance_records(run=run, new_records=records)

    truth_level_counts = Counter(record.truth_level for record in records)
    case_class_counts = Counter(record.case_class for record in records if record.count_value > 0)
    disease_category_counts = Counter(record.disease_category for record in records if record.count_value > 0)
    source_credibility_counts = Counter(
        _source_credibility_for_truth_level(record.truth_level) for record in records
    )
    freshness_state_counts = Counter(record.freshness_state for record in records)
    reporting_granularity_counts = Counter(record.reporting_granularity for record in records)
    return {
        "source_rows_normalized": len(normalized_row_numbers),
        "source_rows_not_normalized": len(accepted_rows) - len(normalized_row_numbers),
        "surveillance_records": len(records),
        "canonical_rejections": canonical_rejections[:MAX_REJECTED_ROW_DETAILS],
        "truth_level_counts": dict(truth_level_counts),
        "case_class_counts": dict(case_class_counts),
        "disease_category_counts": dict(disease_category_counts),
        "source_credibility_counts": dict(source_credibility_counts),
        "freshness_state_counts": dict(freshness_state_counts),
        "reporting_granularity_counts": dict(reporting_granularity_counts),
        "supersession_summary": supersession_summary,
    }


def _production_truth_rejections_for_accepted_rows(
    *,
    run: SurveillanceIngestionRun,
    spec: SurveillanceAdapterSpec,
    accepted_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Preflight production mappings before any canonical row can be written."""

    rejections: list[dict[str, Any]] = []
    for accepted in accepted_rows:
        row = accepted["row"]
        row_number = accepted["row_number"]
        ward = _find_ward(row)
        facility = _find_facility(row)
        if accepted.get("truth_level") == SurveillanceTruthLevel.SEEDED_DEMO:
            rejections.append(
                {
                    "row_number": row_number,
                    "code": PRODUCTION_SEEDED_TRUTH_BLOCKED,
                    "reason": "seeded_surveillance_truth_is_not_production_eligible",
                }
            )
        if ward is None and facility is not None:
            ward = facility.ward

        mapping_reason = None
        if ward is None:
            mapping_reason = "ward_not_found_for_surveillance_record"
        elif not ward.is_active:
            mapping_reason = "ward_is_inactive"
        elif facility is not None and not facility.is_active:
            mapping_reason = "facility_is_inactive"
        elif facility is not None and facility.ward_id != ward.id:
            mapping_reason = "facility_ward_mismatch"
        elif facility is not None and facility.ward is not None and not facility.ward.is_active:
            mapping_reason = "facility_ward_is_inactive"

        if mapping_reason:
            rejections.append(
                {
                    "row_number": row_number,
                    "code": PRODUCTION_UNMAPPED_WARD_BLOCKED,
                    "reason": mapping_reason,
                    "ward_id": ward.id if ward else None,
                    "facility_id": facility.id if facility else None,
                }
            )

        _, canonical_errors = _canonical_records_for_accepted_row(
            run=run,
            spec=spec,
            accepted=accepted,
        )
        for error in canonical_errors:
            if error.get("reason") in {
                "ward_not_found_for_surveillance_record",
                "facility_not_found_for_facility_proxy_record",
                "facility_ward_mismatch",
            }:
                rejections.append(
                    {
                        **error,
                        "code": PRODUCTION_UNMAPPED_WARD_BLOCKED,
                    }
                )
    return rejections[:MAX_REJECTED_ROW_DETAILS]


def _validated_surveillance_csv(
    file_path: str | Path,
    *,
    source_type: str,
    source_name: str = "",
) -> dict[str, Any]:
    spec = adapter_spec_for_surveillance_source_type(source_type)
    headers, rows = _normalized_csv_rows(file_path)
    unknown_columns = sorted(set(headers) - set(spec.accepted_columns))

    accepted_rows: list[dict[str, Any]] = []
    rejected_rows: list[dict[str, Any]] = []
    sample_rows: list[dict[str, Any]] = []
    truth_level_counts: Counter[str] = Counter()
    disease_category_counts: Counter[str] = Counter()
    case_class_counts: Counter[str] = Counter()
    reporting_granularity_counts: Counter[str] = Counter()
    reporting_granularity_warnings: list[dict[str, Any]] = []

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

        try:
            period_start, period_end = _period_for_row(row)
        except ValueError as error:
            if len(rejected_rows) < MAX_REJECTED_ROW_DETAILS:
                rejected_rows.append({"row_number": row_number, "reason": "invalid_reporting_period", "error": str(error)})
            continue
        if period_start is None or period_end is None or period_start > period_end:
            if len(rejected_rows) < MAX_REJECTED_ROW_DETAILS:
                rejected_rows.append({"row_number": row_number, "reason": "invalid_reporting_period_bounds"})
            continue

        counts = _case_counts_for_row(row)
        if not counts and not _first_nonempty(row, "outbreak_label"):
            if len(rejected_rows) < MAX_REJECTED_ROW_DETAILS:
                rejected_rows.append({"row_number": row_number, "reason": "no_case_counts_or_outbreak_label"})
            continue

        truth_level = _truth_level_for_row(row, source_type=source_type, source_name=source_name)
        disease_category = _disease_category_for_row(row)
        reporting_granularity = _reporting_granularity_for_row(row, spec)
        supplied_reporting_granularity = _normalize_choice(_first_nonempty(row, "reporting_granularity"))
        if (
            supplied_reporting_granularity in {"day", "week"}
            and supplied_reporting_granularity != spec.default_reporting_granularity
            and len(reporting_granularity_warnings) < MAX_REJECTED_ROW_DETAILS
        ):
            reporting_granularity_warnings.append(
                {
                    "row_number": row_number,
                    "supplied_reporting_granularity": supplied_reporting_granularity,
                    "adapter_default_reporting_granularity": spec.default_reporting_granularity,
                    "behavior": "preserved_source_supplied_granularity",
                }
            )
        accepted_rows.append(
            {
                "row_number": row_number,
                "row": row,
                "truth_level": truth_level,
                "disease_category": disease_category,
                "case_counts": counts,
                "reporting_granularity": reporting_granularity,
            }
        )
        truth_level_counts[truth_level] += 1
        disease_category_counts[disease_category] += 1
        reporting_granularity_counts[reporting_granularity] += 1
        for case_class, count in counts.items():
            if count > 0:
                case_class_counts[case_class] += 1
        if len(sample_rows) < MAX_SAMPLE_ROWS:
            sample_rows.append({key: row.get(key) for key in headers if key in row})

    period_start, period_end = _period_bounds(accepted_rows)
    return {
        "adapter_key": spec.adapter_key,
        "adapter_notes": spec.notes,
        "provider_import_contract": _provider_import_contract(spec),
        "scheduled_supported": spec.scheduled_supported,
        "default_reporting_granularity": spec.default_reporting_granularity,
        "headers": headers,
        "unknown_columns": unknown_columns,
        "records_seen": len(rows),
        "records_loaded": len(accepted_rows),
        "records_rejected": len(rows) - len(accepted_rows),
        "accepted_rows": accepted_rows,
        "sample_rows": sample_rows,
        "rejected_rows": rejected_rows,
        "period_start": period_start,
        "period_end": period_end,
        "truth_level_counts": dict(truth_level_counts),
        "disease_category_counts": dict(disease_category_counts),
        "case_class_counts": dict(case_class_counts),
        "reporting_granularity_counts": dict(reporting_granularity_counts),
        "reporting_granularity_warnings": reporting_granularity_warnings,
    }


def inspect_surveillance_csv(file_path: str | Path, *, source_type: str, source_name: str = "") -> dict[str, Any]:
    inspection = _validated_surveillance_csv(file_path, source_type=source_type, source_name=source_name)
    inspection.pop("accepted_rows", None)
    return inspection


def upsert_surveillance_source(
    *,
    source_name: str,
    source_type: str,
    source_timestamp: datetime | None = None,
    reporting_period_start: date | None = None,
    reporting_period_end: date | None = None,
    source_ref: str = "",
    operator_note: str = "",
    metadata: dict[str, Any] | None = None,
) -> SurveillanceSource:
    adapter_spec_for_surveillance_source_type(source_type)
    queryset = SurveillanceSource.objects.filter(
        source_name=source_name,
        source_type=source_type,
        reporting_period_start=reporting_period_start,
        reporting_period_end=reporting_period_end,
        source_ref=source_ref,
    ).order_by("-submitted_at", "-id")
    source = queryset.first()
    if source is None:
        return SurveillanceSource.objects.create(
            source_name=source_name,
            source_type=source_type,
            source_timestamp=source_timestamp,
            reporting_period_start=reporting_period_start,
            reporting_period_end=reporting_period_end,
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


def run_surveillance_csv_ingestion(
    *,
    file_path: str | Path,
    source_name: str,
    source_type: str,
    source_timestamp: datetime | str | None = None,
    reporting_period_start: date | str | None = None,
    reporting_period_end: date | str | None = None,
    source_ref: str = "",
    correction_mode: str = SurveillanceIngestionRun.CORRECTION_ORIGINAL,
    correction_reason: str = "",
    operator_note: str = "",
    execution_mode: str = SurveillanceIngestionRun.EXECUTION_MANUAL,
    fallback_used: bool = False,
    replay_of: SurveillanceIngestionRun | None = None,
    regenerate_label_windows: bool = False,
    label_dataset_role: str = "evaluation",
    label_window_days: int = 7,
    label_step_days: int = 7,
    include_seeded_labels: bool = False,
) -> SurveillanceIngestionRun:
    require_seeded_truth_allowed(
        "seeded surveillance label regeneration",
        requested=include_seeded_labels,
    )
    spec = adapter_spec_for_surveillance_source_type(source_type)
    feed_contract = _feed_contract_for_source_type(source_type)
    if not source_name.strip():
        raise ValueError("source_name is required for surveillance ingestion.")
    if correction_mode not in {choice[0] for choice in SurveillanceIngestionRun.CORRECTION_MODE_CHOICES}:
        raise ValueError(f"Unsupported correction_mode '{correction_mode}'.")
    if execution_mode not in {choice[0] for choice in SurveillanceIngestionRun.EXECUTION_MODE_CHOICES}:
        raise ValueError(f"Unsupported execution_mode '{execution_mode}'.")
    if correction_mode == SurveillanceIngestionRun.CORRECTION_AMENDMENT and not correction_reason.strip():
        raise ValueError("correction_reason is required for surveillance amendment ingestion runs.")
    if execution_mode == SurveillanceIngestionRun.EXECUTION_SCHEDULED and not spec.scheduled_supported:
        raise ValueError(f"Scheduled surveillance ingestion is not supported for source_type '{source_type}'.")
    if (
        execution_mode == SurveillanceIngestionRun.EXECUTION_TRUSTED_PUSH
        and source_type != SurveillanceSource.SOURCE_TYPE_TRUSTED_PUSH
    ):
        raise ValueError("execution_mode='trusted_push' requires source_type='trusted_push'.")
    if label_dataset_role not in {"training", "evaluation"}:
        raise ValueError("label_dataset_role must be either 'training' or 'evaluation'.")
    if label_window_days <= 0:
        raise ValueError("label_window_days must be greater than zero.")
    if label_step_days <= 0:
        raise ValueError("label_step_days must be greater than zero.")

    parsed_source_timestamp = (
        parse_surveillance_source_timestamp(source_timestamp)
        if isinstance(source_timestamp, str)
        else source_timestamp
    )
    parsed_period_start = parse_surveillance_date(reporting_period_start)
    parsed_period_end = parse_surveillance_date(reporting_period_end)
    if parsed_period_start and parsed_period_end and parsed_period_start > parsed_period_end:
        raise ValueError("reporting_period_start cannot be after reporting_period_end.")

    seeded_source_metadata = _seeded_non_production_metadata() if "seed" in source_name.lower() else {}
    source = upsert_surveillance_source(
        source_name=source_name,
        source_type=source_type,
        source_timestamp=parsed_source_timestamp,
        reporting_period_start=parsed_period_start,
        reporting_period_end=parsed_period_end,
        source_ref=source_ref,
        operator_note=operator_note,
        metadata={
            "adapter_key": spec.adapter_key,
            "scheduled_supported": spec.scheduled_supported,
            "feed_policy": feed_contract,
            **seeded_source_metadata,
        },
    )
    run = SurveillanceIngestionRun.objects.create(
        source=source,
        status=SurveillanceIngestionRun.STATUS_RUNNING,
        source_name=source.source_name,
        source_type=source.source_type,
        source_timestamp=source.source_timestamp,
        reporting_period_start=source.reporting_period_start,
        reporting_period_end=source.reporting_period_end,
        source_ref=source.source_ref,
        adapter_key=spec.adapter_key,
        input_ref=str(file_path),
        execution_mode=execution_mode,
        correction_mode=correction_mode,
        correction_reason=correction_reason,
        fallback_used=fallback_used,
        operator_note=operator_note,
        source_metadata={
            "source_id": source.id,
            "source_name": source.source_name,
            "source_type": source.source_type,
            "source_timestamp": source.source_timestamp.isoformat() if source.source_timestamp else None,
            "reporting_period_start": source.reporting_period_start.isoformat() if source.reporting_period_start else None,
            "reporting_period_end": source.reporting_period_end.isoformat() if source.reporting_period_end else None,
            "source_ref": source.source_ref,
            "adapter_key": spec.adapter_key,
            "feed_policy": feed_contract,
            **seeded_source_metadata,
        },
        replay_of=replay_of,
    )

    if settings.CCHIS_ENVIRONMENT == "production":
        production_inspection = _validated_surveillance_csv(
            file_path,
            source_type=source_type,
            source_name=source_name,
        )
        production_rejections = _production_truth_rejections_for_accepted_rows(
            run=run,
            spec=spec,
            accepted_rows=production_inspection["accepted_rows"],
        )
        supplied_seeded_source = "seed" in source_name.lower() or any(
            _normalize_choice(_first_nonempty(item["row"], "source_kind")) == SurveillanceSourceKind.SEEDED
            for item in production_inspection["accepted_rows"]
        )
        if supplied_seeded_source:
            production_rejections.append(
                {
                    "row_number": None,
                    "code": PRODUCTION_SEEDED_TRUTH_BLOCKED,
                    "reason": "seeded_surveillance_source_feed_is_not_production_eligible",
                }
            )
        if production_rejections:
            derived_period_start = parsed_period_start or production_inspection["period_start"]
            derived_period_end = parsed_period_end or production_inspection["period_end"]
            source.reporting_period_start = derived_period_start
            source.reporting_period_end = derived_period_end
            source.save(update_fields=["reporting_period_start", "reporting_period_end", "updated_at"])
            run.records_seen = production_inspection["records_seen"]
            run.records_loaded = 0
            run.records_rejected = production_inspection["records_rejected"] + production_inspection["records_loaded"]
            run.reporting_period_start = derived_period_start
            run.reporting_period_end = derived_period_end
            run.rejected_rows = (
                production_inspection["rejected_rows"] + production_rejections
            )[:MAX_REJECTED_ROW_DETAILS]
            run.results = {
                "adapter_key": production_inspection["adapter_key"],
                "source_rows_accepted_by_contract": production_inspection["records_loaded"],
                "source_rows_rejected_by_contract": production_inspection["records_rejected"],
                "production_truth_policy": {
                    "fail_closed": True,
                    "blocked_reason_codes": list(
                        dict.fromkeys(item["code"] for item in production_rejections if item.get("code"))
                    ),
                    "rejections": production_rejections,
                },
                "canonical_records_persisted": False,
            }
            run.status = SurveillanceIngestionRun.STATUS_FAILED
            run.error_summary = production_rejections[0].get("code", PRODUCTION_UNMAPPED_WARD_BLOCKED)
            run.completed_at = timezone.now()
            run.save(
                update_fields=[
                    "status",
                    "records_seen",
                    "records_loaded",
                    "records_rejected",
                    "reporting_period_start",
                    "reporting_period_end",
                    "rejected_rows",
                    "results",
                    "error_summary",
                    "completed_at",
                ]
            )
            return run

    try:
        with transaction.atomic():
            inspection = _validated_surveillance_csv(file_path, source_type=source_type, source_name=source_name)
            derived_period_start = parsed_period_start or inspection["period_start"]
            derived_period_end = parsed_period_end or inspection["period_end"]
            if derived_period_start and derived_period_end and derived_period_start > derived_period_end:
                raise ValueError("Derived reporting period start cannot be after reporting period end.")

            source.reporting_period_start = derived_period_start
            source.reporting_period_end = derived_period_end
            source.metadata = {
                **(source.metadata or {}),
                "adapter_key": inspection["adapter_key"],
                "scheduled_supported": inspection["scheduled_supported"],
                "default_reporting_granularity": inspection["default_reporting_granularity"],
                "provider_import_contract": inspection["provider_import_contract"],
                "feed_policy": feed_contract,
                **seeded_source_metadata,
            }
            source.save(update_fields=["reporting_period_start", "reporting_period_end", "metadata", "updated_at"])

            run.records_seen = inspection["records_seen"]
            run.records_loaded = inspection["records_loaded"]
            run.records_rejected = inspection["records_rejected"]
            run.reporting_period_start = derived_period_start
            run.reporting_period_end = derived_period_end
            run.source_metadata = {
                **(run.source_metadata or {}),
                "reporting_period_start": derived_period_start.isoformat() if derived_period_start else None,
                "reporting_period_end": derived_period_end.isoformat() if derived_period_end else None,
                "feed_policy": feed_contract,
                **seeded_source_metadata,
            }
            canonical_summary = _persist_canonical_surveillance_records_for_run(run, inspection["accepted_rows"])
            canonical_truth_counts = canonical_summary.get("truth_level_counts") or {}
            if canonical_truth_counts.get(SurveillanceTruthLevel.SEEDED_DEMO):
                seeded_source_metadata = _seeded_non_production_metadata()
                source.metadata = {
                    **(source.metadata or {}),
                    **seeded_source_metadata,
                }
                source.save(update_fields=["metadata", "updated_at"])
                run.source_metadata = {
                    **(run.source_metadata or {}),
                    **seeded_source_metadata,
                }
            run.records_loaded = canonical_summary["source_rows_normalized"]
            run.records_rejected = inspection["records_rejected"] + canonical_summary["source_rows_not_normalized"]
            run.rejected_rows = (inspection["rejected_rows"] + canonical_summary["canonical_rejections"])[:MAX_REJECTED_ROW_DETAILS]
            run.results = {
                "adapter_key": inspection["adapter_key"],
                "adapter_notes": inspection["adapter_notes"],
                "provider_import_contract": inspection["provider_import_contract"],
                "scheduled_supported": inspection["scheduled_supported"],
                "default_reporting_granularity": inspection["default_reporting_granularity"],
                "headers": inspection["headers"],
                "unknown_columns": inspection["unknown_columns"],
                "sample_rows": inspection["sample_rows"],
                "source_rows_accepted_by_contract": inspection["records_loaded"],
                "source_rows_rejected_by_contract": inspection["records_rejected"],
                "truth_level_counts": inspection["truth_level_counts"],
                "disease_category_counts": inspection["disease_category_counts"],
                "case_class_counts": inspection["case_class_counts"],
                "reporting_granularity_counts": inspection["reporting_granularity_counts"],
                "reporting_granularity_warnings": inspection["reporting_granularity_warnings"],
                "feed_policy": feed_contract,
                "operational_safety": {
                    "scheduled_source_supported": spec.scheduled_supported,
                    "catch_up_mode": correction_mode == SurveillanceIngestionRun.CORRECTION_BACKFILL,
                    "trusted_push_mode": execution_mode == SurveillanceIngestionRun.EXECUTION_TRUSTED_PUSH,
                    "replay_mode": execution_mode == SurveillanceIngestionRun.EXECUTION_REPLAY,
                    "label_regeneration_requested": regenerate_label_windows,
                    "correction_regenerates_downstream_windows": bool(
                        regenerate_label_windows
                        and correction_mode
                        in {
                            SurveillanceIngestionRun.CORRECTION_AMENDMENT,
                            SurveillanceIngestionRun.CORRECTION_BACKFILL,
                        }
                        and execution_mode != SurveillanceIngestionRun.EXECUTION_REPLAY
                    ),
                    "replay_diagnostic_records_excluded_from_label_generation": True,
                },
                "phase": "phase_4_ongoing_feed_readiness",
                "canonical_records_persisted": True,
                "canonical_summary": {
                    key: value
                    for key, value in canonical_summary.items()
                    if key != "canonical_rejections"
                },
            }

            supersession_summary = canonical_summary.get("supersession_summary") or {}
            superseded_record_ids = supersession_summary.get("superseded_record_ids") or []
            if superseded_record_ids:
                run.results["label_lineage_reconciliation"] = reconcile_surveillance_label_lineage(
                    superseding_ingestion_run=run,
                    superseded_record_ids=superseded_record_ids,
                    apply=True,
                    now=timezone.now(),
                )

            if run.records_seen == 0:
                run.status = SurveillanceIngestionRun.STATUS_FAILED
                run.error_summary = "No source rows were found in the surveillance import file."
            elif run.records_loaded == 0:
                run.status = SurveillanceIngestionRun.STATUS_FAILED
                run.error_summary = "No canonical surveillance records were created."
            elif run.records_rejected == 0:
                run.status = SurveillanceIngestionRun.STATUS_SUCCESS
            else:
                run.status = SurveillanceIngestionRun.STATUS_PARTIAL
    except Exception as error:
        run.status = SurveillanceIngestionRun.STATUS_FAILED
        run.error_summary = str(error)

    run.completed_at = timezone.now()
    run.save(
        update_fields=[
            "status",
            "records_seen",
            "records_loaded",
            "records_rejected",
            "reporting_period_start",
            "reporting_period_end",
            "source_metadata",
            "rejected_rows",
            "results",
            "error_summary",
            "completed_at",
        ]
    )
    if regenerate_label_windows and run.status in {
        SurveillanceIngestionRun.STATUS_SUCCESS,
        SurveillanceIngestionRun.STATUS_PARTIAL,
    }:
        regenerate_surveillance_label_windows_for_run(
            run,
            dataset_role=label_dataset_role,
            window_days=label_window_days,
            step_days=label_step_days,
            include_seeded=include_seeded_labels,
        )
        run.refresh_from_db(fields=["results"])
    return run


def regenerate_surveillance_label_windows_for_run(
    run: SurveillanceIngestionRun,
    *,
    dataset_role: str = "evaluation",
    window_days: int = 7,
    step_days: int = 7,
    include_seeded: bool = False,
) -> dict[str, Any]:
    require_seeded_truth_allowed(
        "seeded surveillance label regeneration",
        requested=include_seeded,
    )

    def store(summary: dict[str, Any]) -> dict[str, Any]:
        run.results = {
            **(run.results or {}),
            "downstream_label_regeneration": summary,
        }
        run.save(update_fields=["results"])
        return summary

    if dataset_role not in {"training", "evaluation"}:
        raise ValueError("dataset_role must be either 'training' or 'evaluation'.")
    if window_days <= 0:
        raise ValueError("window_days must be greater than zero.")
    if step_days <= 0:
        raise ValueError("step_days must be greater than zero.")
    if run.execution_mode == SurveillanceIngestionRun.EXECUTION_REPLAY:
        return store(
            {
                "requested": True,
                "regenerated": False,
                "skipped": True,
                "reason": "replay_diagnostic_run",
                "run_id": run.id,
            }
        )
    if run.status == SurveillanceIngestionRun.STATUS_FAILED:
        return store(
            {
                "requested": True,
                "regenerated": False,
                "skipped": True,
                "reason": "failed_ingestion_run",
                "run_id": run.id,
            }
        )
    if run.reporting_period_start is None or run.reporting_period_end is None:
        return store(
            {
                "requested": True,
                "regenerated": False,
                "skipped": True,
                "reason": "missing_reporting_period_bounds",
                "run_id": run.id,
            }
        )

    lineage_reconciliation = (run.results or {}).get("label_lineage_reconciliation") or {}
    replacement_candidates = list(lineage_reconciliation.get("replacement_datasets") or [])
    for affected_dataset in lineage_reconciliation.get("affected_datasets") or []:
        if affected_dataset.get("replacement_dataset_ref") and not any(
            item.get("dataset_ref") == affected_dataset.get("replacement_dataset_ref")
            for item in replacement_candidates
        ):
            replacement_candidates.append(
                {
                    "dataset_ref": affected_dataset["replacement_dataset_ref"],
                    "row_count": None,
                }
            )
    for replacement_candidate in replacement_candidates:
        replacement = FeatureDataset.objects.filter(
            dataset_ref=replacement_candidate.get("dataset_ref"),
        ).first()
        if replacement is None:
            continue
        replacement_lineage = replacement.lineage_metadata or {}
        if replacement_lineage.get("dataset_role") != dataset_role:
            continue
        return store(
            {
                "requested": True,
                "regenerated": True,
                "skipped": False,
                "run_id": run.id,
                "dataset_ref": replacement.dataset_ref,
                "schema_version": replacement.schema_version,
                "dataset_role": dataset_role,
                "window_days": replacement_lineage.get("window_days", window_days),
                "step_days": replacement_lineage.get("step_days", step_days),
                "include_seeded": replacement_lineage.get("include_seeded", include_seeded),
                "ward_ids": list(
                    SurveillanceLabelWindow.objects.filter(feature_dataset=replacement)
                    .order_by()
                    .values_list("ward_id", flat=True)
                    .distinct()
                ),
                "label_window_count": SurveillanceLabelWindow.objects.filter(
                    feature_dataset=replacement,
                ).count(),
                "feature_dataset_row_count": replacement.row_count,
                "supersession_replacement": True,
            }
        )

    ward_ids = list(
        run.surveillance_records.order_by().values_list("ward_id", flat=True).distinct()
    )
    if not ward_ids:
        return store(
            {
                "requested": True,
                "regenerated": False,
                "skipped": True,
                "reason": "no_canonical_surveillance_records_for_run",
                "run_id": run.id,
            }
        )

    from risk.surveillance_labels import SURVEILLANCE_LABEL_SCHEMA_VERSION, build_surveillance_label_dataset

    wards = Ward.objects.filter(id__in=ward_ids).order_by("name")
    try:
        snapshot = build_surveillance_label_dataset(
            wards=wards,
            start_date=run.reporting_period_start,
            end_date=run.reporting_period_end,
            window_days=window_days,
            step_days=step_days,
            dataset_role=dataset_role,
            include_seeded=include_seeded,
        )
    except ValueError as error:
        return store(
            {
                "requested": True,
                "regenerated": False,
                "skipped": True,
                "reason": "label_generation_error",
                "error": str(error),
                "run_id": run.id,
            }
        )

    return store(
        {
            "requested": True,
            "regenerated": True,
            "skipped": False,
            "run_id": run.id,
            "dataset_ref": snapshot.feature_dataset.dataset_ref,
            "schema_version": SURVEILLANCE_LABEL_SCHEMA_VERSION,
            "dataset_role": dataset_role,
            "window_days": window_days,
            "step_days": step_days,
            "include_seeded": include_seeded,
            "ward_ids": ward_ids,
            "label_window_count": len(snapshot.label_windows),
            "feature_dataset_row_count": snapshot.feature_dataset.row_count,
        }
    )


def replay_surveillance_ingestion_run(
    run_id: int,
    *,
    file_path: str | Path | None = None,
    operator_note: str = "",
) -> SurveillanceIngestionRun:
    original = SurveillanceIngestionRun.objects.select_related("source").get(pk=run_id)
    return run_surveillance_csv_ingestion(
        file_path=file_path or original.input_ref,
        source_name=original.source_name,
        source_type=original.source_type,
        source_timestamp=original.source_timestamp,
        reporting_period_start=original.reporting_period_start,
        reporting_period_end=original.reporting_period_end,
        source_ref=original.source_ref,
        correction_mode=original.correction_mode,
        correction_reason=original.correction_reason,
        operator_note=operator_note or f"Replay of surveillance ingestion run {original.id}",
        execution_mode=SurveillanceIngestionRun.EXECUTION_REPLAY,
        fallback_used=original.fallback_used,
        replay_of=original,
    )


def build_surveillance_replay_plan(run: SurveillanceIngestionRun) -> dict[str, Any]:
    return {
        "run_id": run.id,
        "source_name": run.source_name,
        "source_type": run.source_type,
        "feed_policy": _feed_contract_for_source_type(run.source_type),
        "reporting_period_start": run.reporting_period_start.isoformat() if run.reporting_period_start else None,
        "reporting_period_end": run.reporting_period_end.isoformat() if run.reporting_period_end else None,
        "input_ref": run.input_ref,
        "replay_command": f"python manage.py ingest_surveillance --replay-of {run.id}",
        "replay_label_regeneration_behavior": "skipped_replay_diagnostic_records_are_excluded_from_label_generation",
        "backfill_command_shape": (
            "python manage.py ingest_surveillance --file <csv> --source-name <name> "
            "--source-type csv_backfill --reporting-period-start <date> --reporting-period-end <date> "
            "--correction-mode backfill --regenerate-label-windows"
        ),
        "amendment_command_shape": (
            "python manage.py ingest_surveillance --file <csv> --source-name <name> "
            "--source-type <type> --reporting-period-start <date> --reporting-period-end <date> "
            "--correction-mode amendment --correction-reason <reason> --regenerate-label-windows"
        ),
        "trusted_push_command_shape": (
            "python manage.py ingest_surveillance --file <csv> --source-name <name> "
            "--source-type trusted_push --execution-mode trusted_push --source-ref <push-batch-id>"
        ),
    }
