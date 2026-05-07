from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone

from risk.models import (
    FacilityReadinessFreshness,
    FacilityReadinessIngestionRun,
    FacilityReadinessSnapshot,
    FacilityReadinessSource,
    FacilityReadinessSourceKind,
    FacilityReadinessState,
    HealthFacility,
    Ward,
)
from risk.privacy_access import redact_direct_identifiers_in_text
from risk.privacy_minimization import PrivacyMinimizationViolation, ensure_pii_safe_text


MAX_REJECTED_ROW_DETAILS = 25
MAX_SAMPLE_ROWS = 5
READINESS_DELAYED_AFTER_DAYS = 7
READINESS_STALE_AFTER_DAYS = 14


FACILITY_READINESS_ACCEPTED_COLUMNS = frozenset(
    {
        "facility_code",
        "facility_name",
        "ward_code",
        "ward_name",
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
    }
)

REQUIRED_COLUMNS = (
    "facility_code",
    "ward_code",
    "reported_at",
    "ors_sachets_available",
    "iv_fluids_available",
    "zinc_available",
    "chlorine_available",
    "beds_available",
    "staff_on_duty",
    "referral_available",
    "service_disruption",
    "source_kind",
)

NUMERIC_COLUMNS = (
    "ors_sachets_available",
    "iv_fluids_available",
    "zinc_available",
    "chlorine_available",
    "beds_available",
    "staff_on_duty",
)

BOOL_COLUMNS = ("referral_available", "service_disruption")


@dataclass(frozen=True)
class ValidatedReadinessRow:
    row_number: int
    row: dict[str, Any]
    facility: HealthFacility
    ward: Ward
    reported_at: datetime
    source_ref: str
    source_kind: str
    freshness_state: str
    readiness_state: str
    readiness_score: float
    stockout_flags: list[str]
    staffing_required: int
    staffing_percent: int
    ors_readiness_percent: int
    redacted_stockout_notes: str


def normalize_column_name(value: str | None) -> str:
    return "_".join((value or "").strip().lower().replace("-", "_").split())


def parse_reported_at(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _normalized_csv_rows(file_path: str | Path) -> tuple[list[str], list[dict[str, Any]]]:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Facility readiness import file does not exist: {path}")

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


def _parse_bool(value: str | bool | int | None) -> bool | None:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return None
    normalized = str(value).strip().lower()
    if normalized in {"true", "t", "yes", "y", "1"}:
        return True
    if normalized in {"false", "f", "no", "n", "0"}:
        return False
    return None


def _normalise_source_kind(value: str) -> str | None:
    normalized = normalize_column_name(value)
    if normalized == "county_ops_review":
        normalized = FacilityReadinessSourceKind.COUNTY_OPERATIONS
    allowed = {choice[0] for choice in FacilityReadinessSourceKind.choices}
    return normalized if normalized in allowed else None


def _stockout_flags(values: dict[str, int]) -> list[str]:
    flags = []
    if values["ors_sachets_available"] <= 0:
        flags.append("ors_stockout")
    if values["iv_fluids_available"] <= 0:
        flags.append("iv_fluids_stockout")
    if values["zinc_available"] <= 0:
        flags.append("zinc_stockout")
    if values["chlorine_available"] <= 0:
        flags.append("chlorine_stockout")
    return flags


def _staffing_required_for_facility(facility: HealthFacility) -> int:
    if facility.level == HealthFacility.LEVEL_5:
        return 15
    if facility.level == HealthFacility.LEVEL_4:
        return 10
    return 6


def _freshness_state(reported_at: datetime) -> str:
    age_days = (timezone.now() - reported_at).total_seconds() / 86400
    if age_days > READINESS_STALE_AFTER_DAYS:
        return FacilityReadinessFreshness.STALE
    if age_days > READINESS_DELAYED_AFTER_DAYS:
        return FacilityReadinessFreshness.DELAYED
    return FacilityReadinessFreshness.FRESH


def _readiness_state_and_score(
    *,
    values: dict[str, int],
    referral_available: bool,
    service_disruption: bool,
    stockout_flags: list[str],
    staffing_required: int,
) -> tuple[str, float, int, int]:
    staffing_percent = min(100, round((values["staff_on_duty"] / staffing_required) * 100)) if staffing_required else 0
    ors_readiness_percent = min(100, round((values["ors_sachets_available"] / 100) * 100))
    score = 100.0
    score -= len(stockout_flags) * 12
    score -= 20 if service_disruption else 0
    score -= 10 if not referral_available else 0
    score -= max(0, 70 - staffing_percent) * 0.35
    score -= 12 if values["beds_available"] <= 0 else 0
    score = max(0.0, min(100.0, round(score, 2)))

    if service_disruption or not referral_available or values["beds_available"] <= 0 or values["staff_on_duty"] <= 0 or len(stockout_flags) >= 2:
        state = FacilityReadinessState.CAPACITY_CONCERN
    elif stockout_flags or staffing_percent < 70 or values["beds_available"] < 2:
        state = FacilityReadinessState.WATCH
    else:
        state = FacilityReadinessState.READY
    return state, score, staffing_percent, ors_readiness_percent


def _redacted_note(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    try:
        ensure_pii_safe_text(text, location="stockout_notes")
    except PrivacyMinimizationViolation:
        return "[redacted unsafe note]"
    return redact_direct_identifiers_in_text(text, can_view=False)


def _safe_sample_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: ("[redacted]" if key == "stockout_notes" and str(value or "").strip() else value)
        for key, value in row.items()
        if key in FACILITY_READINESS_ACCEPTED_COLUMNS
    }


def _validated_facility_readiness_csv(file_path: str | Path) -> dict[str, Any]:
    headers, rows = _normalized_csv_rows(file_path)
    unknown_columns = sorted(set(headers) - FACILITY_READINESS_ACCEPTED_COLUMNS)

    records_seen = len(rows)
    accepted_rows: list[ValidatedReadinessRow] = []
    rejected_rows: list[dict[str, Any]] = []
    warning_rows: list[dict[str, Any]] = []
    sample_rows: list[dict[str, Any]] = []
    seen_facility_report_keys: set[tuple[int, datetime]] = set()

    facilities_by_code = {
        facility.facility_code: facility
        for facility in HealthFacility.objects.filter(is_active=True).select_related("ward")
    }
    wards_by_code = {ward.ward_code: ward for ward in Ward.objects.filter(is_active=True)}

    def reject(row_number: int, reason: str, **context) -> None:
        if len(rejected_rows) < MAX_REJECTED_ROW_DETAILS:
            rejected_rows.append({"row_number": row_number, "reason": reason, **context})

    def warn(row_number: int, reason: str, **context) -> None:
        warning_rows.append({"row_number": row_number, "reason": reason, **context})

    for row_number, row in enumerate(rows, start=2):
        if len(sample_rows) < MAX_SAMPLE_ROWS:
            sample_rows.append(_safe_sample_row(row))

        missing_columns = [column for column in REQUIRED_COLUMNS if not _first_nonempty(row, column)]
        if missing_columns:
            reject(row_number, "missing_required_field", missing_columns=missing_columns)
            continue

        facility_code = _first_nonempty(row, "facility_code")
        ward_code = _first_nonempty(row, "ward_code")
        facility = facilities_by_code.get(facility_code)
        ward = wards_by_code.get(ward_code)
        if facility is None:
            reject(row_number, "unknown_facility_code", facility_code=facility_code)
            continue
        if ward is None:
            reject(row_number, "unknown_ward_code", ward_code=ward_code)
            continue
        if facility.ward_id != ward.id:
            reject(
                row_number,
                "facility_ward_mismatch",
                facility_code=facility_code,
                ward_code=ward_code,
                expected_ward_code=facility.ward.ward_code,
            )
            continue

        try:
            reported_at = parse_reported_at(_first_nonempty(row, "reported_at"))
        except ValueError as error:
            reject(row_number, "invalid_reported_at", error=str(error))
            continue
        if reported_at is None:
            reject(row_number, "invalid_reported_at", error="reported_at is required")
            continue
        if reported_at > timezone.now() + timedelta(days=1):
            reject(row_number, "future_reported_at", error="reported_at cannot be more than one day in the future")
            continue

        numeric_values: dict[str, int] = {}
        invalid_numeric = []
        for column in NUMERIC_COLUMNS:
            value = _parse_nonnegative_int(row.get(column))
            if value is None:
                invalid_numeric.append(column)
            else:
                numeric_values[column] = value
        if invalid_numeric:
            reject(row_number, "invalid_nonnegative_integer", columns=invalid_numeric)
            continue

        bool_values: dict[str, bool] = {}
        invalid_bool = []
        for column in BOOL_COLUMNS:
            value = _parse_bool(row.get(column))
            if value is None:
                invalid_bool.append(column)
            else:
                bool_values[column] = value
        if invalid_bool:
            reject(row_number, "invalid_boolean", columns=invalid_bool)
            continue

        source_kind = _normalise_source_kind(_first_nonempty(row, "source_kind"))
        if source_kind is None:
            reject(row_number, "invalid_source_kind", allowed_values=[choice[0] for choice in FacilityReadinessSourceKind.choices])
            continue

        duplicate_key = (facility.id, reported_at)
        if duplicate_key in seen_facility_report_keys:
            reject(row_number, "duplicate_snapshot_in_file", facility_code=facility_code)
            continue
        seen_facility_report_keys.add(duplicate_key)
        if FacilityReadinessSnapshot.objects.filter(facility=facility, reported_at=reported_at).exists():
            reject(row_number, "duplicate_snapshot", facility_code=facility_code)
            continue

        facility_name = _first_nonempty(row, "facility_name")
        if facility_name and facility_name.casefold() != facility.name.casefold():
            warn(row_number, "facility_name_mismatch", facility_code=facility_code)

        freshness_state = _freshness_state(reported_at)
        if freshness_state == FacilityReadinessFreshness.STALE:
            warn(row_number, "stale_report", facility_code=facility_code)
        elif freshness_state == FacilityReadinessFreshness.DELAYED:
            warn(row_number, "delayed_report", facility_code=facility_code)

        stockout_flags = _stockout_flags(numeric_values)
        if stockout_flags:
            warn(row_number, "stockout_detected", stockout_flags=stockout_flags)
        if bool_values["service_disruption"]:
            warn(row_number, "service_disruption_reported", facility_code=facility_code)

        staffing_required = _staffing_required_for_facility(facility)
        readiness_state, readiness_score, staffing_percent, ors_readiness_percent = _readiness_state_and_score(
            values=numeric_values,
            referral_available=bool_values["referral_available"],
            service_disruption=bool_values["service_disruption"],
            stockout_flags=stockout_flags,
            staffing_required=staffing_required,
        )

        accepted_rows.append(
            ValidatedReadinessRow(
                row_number=row_number,
                row=row,
                facility=facility,
                ward=ward,
                reported_at=reported_at,
                source_ref=_first_nonempty(row, "source_ref"),
                source_kind=source_kind,
                freshness_state=freshness_state,
                readiness_state=readiness_state,
                readiness_score=readiness_score,
                stockout_flags=stockout_flags,
                staffing_required=staffing_required,
                staffing_percent=staffing_percent,
                ors_readiness_percent=ors_readiness_percent,
                redacted_stockout_notes=_redacted_note(_first_nonempty(row, "stockout_notes")),
            )
        )

    coverage = {
        "facility_count": HealthFacility.objects.filter(is_active=True).count(),
        "facilities_reported": len({item.facility.id for item in accepted_rows}),
        "wards_reported": len({item.ward.id for item in accepted_rows}),
        "stale_report_count": sum(1 for item in warning_rows if item["reason"] == "stale_report"),
        "delayed_report_count": sum(1 for item in warning_rows if item["reason"] == "delayed_report"),
        "stockout_facility_count": len({item.facility.id for item in accepted_rows if item.stockout_flags}),
        "service_disruption_count": sum(1 for item in accepted_rows if _parse_bool(item.row.get("service_disruption"))),
        "readiness_state_counts": dict(Counter(item.readiness_state for item in accepted_rows)),
        "source_kind_counts": dict(Counter(item.source_kind for item in accepted_rows)),
    }
    coverage["facility_coverage_percent"] = (
        round((coverage["facilities_reported"] / coverage["facility_count"]) * 100, 2)
        if coverage["facility_count"]
        else 0.0
    )

    return {
        "adapter_key": "facility_readiness_snapshot_csv",
        "adapter_notes": "Canonical facility readiness snapshot CSV.",
        "scheduled_supported": False,
        "headers": headers,
        "unknown_columns": unknown_columns,
        "unknown_columns_are_errors": True,
        "records_seen": records_seen,
        "records_loaded": len(accepted_rows),
        "records_rejected": records_seen - len(accepted_rows),
        "accepted_rows": accepted_rows,
        "sample_rows": sample_rows,
        "rejected_rows": rejected_rows,
        "warning_rows": warning_rows[:MAX_REJECTED_ROW_DETAILS],
        "readiness_summary": coverage,
    }


def inspect_facility_readiness_snapshot_csv(file_path: str | Path) -> dict[str, Any]:
    inspection = _validated_facility_readiness_csv(file_path)
    inspection.pop("accepted_rows", None)
    return inspection


@transaction.atomic
def run_facility_readiness_snapshot_ingestion(
    *,
    file_path: str | Path,
    source_name: str,
    source_type: str = FacilityReadinessSource.SOURCE_TYPE_READINESS_SNAPSHOT,
    source_timestamp: datetime | None = None,
    reporting_period_start=None,
    reporting_period_end=None,
    source_ref: str = "",
    operator_note: str = "",
    execution_mode: str = FacilityReadinessIngestionRun.EXECUTION_MANUAL,
) -> FacilityReadinessIngestionRun:
    if source_type != FacilityReadinessSource.SOURCE_TYPE_READINESS_SNAPSHOT:
        raise ValueError("Facility readiness ingestion only supports readiness_snapshot source_type.")

    inspection = _validated_facility_readiness_csv(file_path)
    source = FacilityReadinessSource.objects.create(
        source_name=source_name,
        source_type=source_type,
        source_timestamp=source_timestamp,
        reporting_period_start=reporting_period_start,
        reporting_period_end=reporting_period_end,
        source_ref=source_ref,
        operator_note=operator_note,
        metadata={
            "adapter_key": inspection["adapter_key"],
            "headers": inspection["headers"],
            "unknown_columns": inspection["unknown_columns"],
        },
    )
    run = FacilityReadinessIngestionRun.objects.create(
        source=source,
        status=FacilityReadinessIngestionRun.STATUS_RUNNING,
        source_name=source_name,
        source_type=source_type,
        source_timestamp=source_timestamp,
        reporting_period_start=reporting_period_start,
        reporting_period_end=reporting_period_end,
        source_ref=source_ref,
        input_ref=str(file_path),
        execution_mode=execution_mode,
        records_seen=inspection["records_seen"],
        records_loaded=0,
        records_rejected=inspection["records_rejected"],
        operator_note=operator_note,
        source_metadata={
            "adapter_key": inspection["adapter_key"],
            "headers": inspection["headers"],
            "unknown_columns": inspection["unknown_columns"],
        },
        rejected_rows=inspection["rejected_rows"],
    )

    snapshots = []
    for item in inspection["accepted_rows"]:
        values = {column: _parse_nonnegative_int(item.row.get(column)) or 0 for column in NUMERIC_COLUMNS}
        referral_available = bool(_parse_bool(item.row.get("referral_available")))
        service_disruption = bool(_parse_bool(item.row.get("service_disruption")))
        snapshots.append(
            FacilityReadinessSnapshot(
                facility=item.facility,
                ward=item.ward,
                ingestion_run=run,
                source=source,
                reported_at=item.reported_at,
                ors_sachets_available=values["ors_sachets_available"],
                iv_fluids_available=values["iv_fluids_available"],
                zinc_available=values["zinc_available"],
                chlorine_available=values["chlorine_available"],
                beds_available=values["beds_available"],
                staff_on_duty=values["staff_on_duty"],
                referral_available=referral_available,
                service_disruption=service_disruption,
                stockout_notes=item.redacted_stockout_notes,
                source_kind=item.source_kind,
                freshness_state=item.freshness_state,
                readiness_state=item.readiness_state,
                readiness_score=item.readiness_score,
                source_name=source_name,
                source_ref=item.source_ref or source_ref,
                raw_payload={
                    **_safe_sample_row(item.row),
                    "stockout_flags": item.stockout_flags,
                    "staffing_required": item.staffing_required,
                    "staffing_percent": item.staffing_percent,
                    "ors_readiness_percent": item.ors_readiness_percent,
                },
            )
        )

    try:
        FacilityReadinessSnapshot.objects.bulk_create(snapshots)
    except IntegrityError as error:
        run.status = FacilityReadinessIngestionRun.STATUS_FAILED
        run.completed_at = timezone.now()
        run.records_loaded = 0
        run.records_rejected = inspection["records_seen"]
        run.error_summary = "Duplicate facility readiness snapshots were detected during import."
        run.results = {"error": str(error)}
        run.save(update_fields=["status", "completed_at", "records_loaded", "records_rejected", "error_summary", "results"])
        raise ValueError(run.error_summary) from error

    run.records_loaded = len(snapshots)
    run.records_rejected = inspection["records_seen"] - len(snapshots)
    if run.records_loaded and run.records_rejected:
        run.status = FacilityReadinessIngestionRun.STATUS_PARTIAL
    elif run.records_loaded:
        run.status = FacilityReadinessIngestionRun.STATUS_SUCCESS
    else:
        run.status = FacilityReadinessIngestionRun.STATUS_FAILED
    run.completed_at = timezone.now()
    run.results = {
        "readiness_summary": inspection["readiness_summary"],
        "warning_rows": inspection["warning_rows"],
        "snapshot_ids": [snapshot.id for snapshot in snapshots],
    }
    if run.status == FacilityReadinessIngestionRun.STATUS_FAILED:
        run.error_summary = "No facility readiness rows were accepted."
    run.save(
        update_fields=[
            "status",
            "completed_at",
            "records_loaded",
            "records_rejected",
            "results",
            "error_summary",
        ]
    )
    return run
