from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from typing import Any

from django.db import connection
from django.utils import timezone

from risk.climate_records import classify_climate_record_type, enrich_rainfall_result_with_climate_contract
from risk.models import ClimateRecord, ClimateRecordType, IngestionRun, Ward


CLIMATE_SOURCE_AUDIT_SCHEMA_VERSION = "climate-source-separation-audit-v1"
CLIMATE_SOURCE_RECORD_TYPES = {
    ClimateRecordType.OBSERVED,
    ClimateRecordType.FORECAST,
    ClimateRecordType.DERIVED_ROLLING_WINDOW,
    ClimateRecordType.DERIVED_ANOMALY,
    ClimateRecordType.FALLBACK_STATIC,
}


def _parse_datetime(value: Any):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _parse_date(value: Any):
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


def _safe_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalise_identity(value: Any) -> str:
    return str(value or "").strip().casefold()


def _climate_record_table_available() -> bool:
    return ClimateRecord._meta.db_table in connection.introspection.table_names()


def _climate_record_count() -> int:
    if not _climate_record_table_available():
        return 0
    return ClimateRecord.objects.count()


def _records_from_climate_table() -> dict[str, dict]:
    if not _climate_record_table_available():
        return {}
    records = {}
    queryset = ClimateRecord.objects.select_related("ward", "ingestion_run").order_by("ingestion_run_id", "id")
    for record in queryset:
        raw_payload = record.raw_payload if isinstance(record.raw_payload, dict) else {}
        canonical = raw_payload.get("canonical_record") if isinstance(raw_payload.get("canonical_record"), dict) else {}
        records[record.source_ref] = {
            "source_ref": record.source_ref,
            "storage": "climate_record_table",
            "ward_id": record.ward_id,
            "ward_name": record.ward.name if record.ward_id else "",
            "source_ward_name": raw_payload.get("ward_name") or canonical.get("ward_name") or "",
            "record_type": record.record_type,
            "source_provider": record.source_provider,
            "source_kind": record.source_kind,
            "source_mode": record.source_mode,
            "issue_time": record.issue_time.isoformat() if record.issue_time else None,
            "valid_date": record.valid_date.isoformat() if record.valid_date else None,
            "lead_day": record.lead_day,
            "observed_timestamp": record.observed_timestamp.isoformat() if record.observed_timestamp else None,
            "forecast_horizon_days": record.forecast_horizon_days,
            "rainfall_mm": record.rainfall_mm,
            "quality_flag": record.quality_flag,
            "fallback_flag": record.fallback_flag,
            "source_run": record.source_run,
            "ingestion_run_id": record.ingestion_run_id,
            "lineage_metadata": record.lineage_metadata or {},
            "raw_payload": raw_payload,
        }
    return records


def _records_from_ingestion_json(existing_refs: set[str]) -> dict[str, dict]:
    records = {}
    runs = IngestionRun.objects.filter(run_type=IngestionRun.RUN_TYPE_RAINFALL).order_by("id")
    for run in runs:
        results = run.results if isinstance(run.results, list) else []
        for row_index, result in enumerate(results):
            if not isinstance(result, dict):
                continue
            enriched = enrich_rainfall_result_with_climate_contract(
                ingestion_run=run,
                result=result,
                row_index=row_index,
            )
            source_ref = enriched.get("source_ref") or enriched.get("record_ref")
            if not source_ref or source_ref in existing_refs:
                continue
            canonical = enriched.get("canonical_record") if isinstance(enriched.get("canonical_record"), dict) else {}
            source_provider = enriched.get("source") or canonical.get("source_name") or run.source_name
            fallback_reason = enriched.get("fallback_reason") or canonical.get("fallback_reason") or ""
            fallback_flag = bool(enriched.get("fallback_flag") or fallback_reason)
            record_type = enriched.get("record_type") or classify_climate_record_type(
                source_provider=source_provider,
                fallback_reason=fallback_reason,
                fallback_flag=fallback_flag,
            )
            records[source_ref] = {
                "source_ref": source_ref,
                "storage": "ingestion_run_json",
                "ward_id": enriched.get("ward_id"),
                "ward_name": enriched.get("ward_name") or "",
                "source_ward_name": enriched.get("ward_name") or canonical.get("ward_name") or "",
                "record_type": record_type,
                "source_provider": source_provider,
                "source_kind": run.source_kind,
                "source_mode": run.source_mode,
                "issue_time": enriched.get("issue_time"),
                "valid_date": enriched.get("valid_date"),
                "lead_day": enriched.get("lead_day"),
                "observed_timestamp": enriched.get("observed_timestamp"),
                "forecast_horizon_days": enriched.get("forecast_horizon_days") or 0,
                "rainfall_mm": enriched.get("rainfall_mm"),
                "quality_flag": enriched.get("quality_flag"),
                "fallback_flag": fallback_flag,
                "source_run": enriched.get("source_run"),
                "ingestion_run_id": run.id,
                "lineage_metadata": enriched.get("lineage_metadata") or {},
            }
    return records


def _all_climate_contract_records() -> list[dict]:
    records_by_ref = _records_from_climate_table()
    records_by_ref.update(_records_from_ingestion_json(set(records_by_ref)))
    return list(records_by_ref.values())


def _audit_question(
    *,
    question_id: str,
    status: str,
    answer: str,
    evidence: dict,
    gaps: list[str] | None = None,
) -> dict:
    return {
        "id": question_id,
        "status": status,
        "answer": answer,
        "evidence": evidence,
        "gaps": gaps or [],
    }


def build_climate_source_separation_audit() -> dict:
    records = _all_climate_contract_records()
    climate_record_table_available = _climate_record_table_available()
    referenced_ward_ids = {
        ward_id for ward_id in (_safe_int(record.get("ward_id")) for record in records) if ward_id is not None
    }
    existing_wards_by_id = dict(Ward.objects.filter(id__in=referenced_ward_ids).values_list("id", "name"))
    existing_ward_ids = set(existing_wards_by_id)
    record_type_counts = Counter(record.get("record_type") or "missing" for record in records)
    source_provider_counts = Counter(record["source_provider"] for record in records if record.get("source_provider"))
    storage_counts = Counter(record["storage"] for record in records)
    fallback_records = [record for record in records if record.get("fallback_flag")]
    forecast_records = [record for record in records if record.get("record_type") == ClimateRecordType.FORECAST]
    observed_records = [record for record in records if record.get("record_type") == ClimateRecordType.OBSERVED]
    derived_records = [
        record
        for record in records
        if record.get("record_type") in {ClimateRecordType.DERIVED_ROLLING_WINDOW, ClimateRecordType.DERIVED_ANOMALY}
    ]
    records_invalid_record_type = [
        record for record in records if record.get("record_type") not in CLIMATE_SOURCE_RECORD_TYPES
    ]
    records_missing_source_provider = [
        record
        for record in records
        if str(record.get("source_provider") or "").strip() in {"", "unknown-rainfall-source"}
    ]
    records_missing_source_run = [record for record in records if not str(record.get("source_run") or "").strip()]
    records_missing_or_invalid_rainfall = [
        record for record in records if _safe_float(record.get("rainfall_mm")) is None
    ]
    forecast_missing_issue = [record for record in forecast_records if _parse_datetime(record.get("issue_time")) is None]
    forecast_missing_valid_date = [record for record in forecast_records if _parse_date(record.get("valid_date")) is None]
    forecast_missing_lead_day = [record for record in forecast_records if _safe_int(record.get("lead_day")) is None]
    forecast_invalid_lead_day = [
        record
        for record in forecast_records
        if _safe_int(record.get("lead_day")) is not None and (_safe_int(record.get("lead_day")) or 0) <= 0
    ]
    forecast_invalid_horizon = [
        record
        for record in forecast_records
        if (_safe_int(record.get("forecast_horizon_days")) or 0) <= 0
        or (
            _safe_int(record.get("lead_day")) is not None
            and (_safe_int(record.get("forecast_horizon_days")) or 0) < (_safe_int(record.get("lead_day")) or 0)
        )
    ]
    observed_missing_timestamp = [
        record for record in observed_records if _parse_datetime(record.get("observed_timestamp")) is None
    ]
    fallback_without_flag = [
        record
        for record in records
        if record.get("record_type") == ClimateRecordType.FALLBACK_STATIC and not record.get("fallback_flag")
    ]
    records_missing_or_invalid_ward = [
        record
        for record in records
        if _safe_int(record.get("ward_id")) is None or _safe_int(record.get("ward_id")) not in existing_ward_ids
    ]
    records_with_ward_identity_mismatch = [
        record
        for record in records
        if _safe_int(record.get("ward_id")) in existing_ward_ids
        and _normalise_identity(record.get("source_ward_name") or record.get("ward_name"))
        and _normalise_identity(record.get("source_ward_name") or record.get("ward_name"))
        != _normalise_identity(existing_wards_by_id[_safe_int(record.get("ward_id"))])
    ]
    max_lead_day = max(
        (_safe_int(record.get("lead_day")) or 0 for record in forecast_records),
        default=0,
    )
    max_forecast_horizon_days = max(
        (_safe_int(record.get("forecast_horizon_days")) or 0 for record in forecast_records),
        default=0,
    )
    source_gaps = []
    hard_gaps = []
    if not climate_record_table_available:
        hard_gaps.append("climate_record_table_missing_or_migrations_not_applied")
    if not records:
        source_gaps.append("no_rainfall_records_available_for_climate_audit")
    if records_invalid_record_type:
        hard_gaps.append("climate_records_invalid_record_type")
    if records_missing_source_provider:
        hard_gaps.append("climate_records_missing_source_provider")
    if records_missing_source_run:
        hard_gaps.append("climate_records_missing_source_run")
    if records_missing_or_invalid_rainfall:
        hard_gaps.append("climate_records_missing_or_invalid_rainfall_value")
    if not observed_records:
        source_gaps.append("no_observed_rainfall_records_available")
    if not forecast_records:
        source_gaps.append("no_forecast_rainfall_records_available")
    if max_lead_day < 7:
        source_gaps.append("forecast_horizon_below_7_days")
    if max_lead_day < 14:
        source_gaps.append("forecast_horizon_below_14_days")
    if forecast_missing_issue:
        hard_gaps.append("forecast_records_missing_issue_time")
    if forecast_missing_valid_date:
        hard_gaps.append("forecast_records_missing_valid_date")
    if forecast_missing_lead_day:
        hard_gaps.append("forecast_records_missing_lead_day")
    if forecast_invalid_lead_day:
        hard_gaps.append("forecast_records_invalid_lead_day")
    if forecast_invalid_horizon:
        hard_gaps.append("forecast_records_invalid_forecast_horizon")
    if observed_missing_timestamp:
        hard_gaps.append("observed_records_missing_observed_timestamp")
    if fallback_without_flag:
        hard_gaps.append("fallback_static_records_without_fallback_flag")
    if records_missing_or_invalid_ward:
        hard_gaps.append("climate_records_missing_or_invalid_ward")
    if records_with_ward_identity_mismatch:
        hard_gaps.append("climate_records_ward_identity_mismatch")

    verification_questions = [
        _audit_question(
            question_id="which_records_are_observed_rainfall",
            status="pass" if observed_records else "warning",
            answer=(
                "Observed rainfall records are explicitly typed."
                if observed_records
                else "No observed rainfall records are currently present; existing live rainfall source is forecast-typed."
            ),
            evidence={"observed_record_count": len(observed_records)},
            gaps=[] if observed_records else ["no_observed_rainfall_records_available"],
        ),
        _audit_question(
            question_id="which_records_are_forecasts",
            status="pass" if forecast_records else "warning",
            answer=(
                "Forecast rainfall records are explicitly typed and separable from observed rainfall."
                if forecast_records
                else "No forecast rainfall records are currently present."
            ),
            evidence={
                "forecast_record_count": len(forecast_records),
                "forecast_source_providers": sorted(
                    {record["source_provider"] for record in forecast_records if record.get("source_provider")}
                ),
            },
            gaps=[] if forecast_records else ["no_forecast_rainfall_records_available"],
        ),
        _audit_question(
            question_id="issue_time_available",
            status=(
                "pass"
                if forecast_records and not forecast_missing_issue
                else "fail"
                if forecast_missing_issue
                else "warning"
            ),
            answer=(
                "Every forecast record has an issue time."
                if forecast_records and not forecast_missing_issue
                else "One or more forecast records lack issue time."
                if forecast_missing_issue
                else "No forecast records exist to verify issue time."
            ),
            evidence={
                "forecast_record_count": len(forecast_records),
                "records_missing_issue_time": len(forecast_missing_issue),
            },
            gaps=["forecast_records_missing_issue_time"] if forecast_missing_issue else [],
        ),
        _audit_question(
            question_id="valid_dates_and_lead_days_available",
            status=(
                "pass"
                if forecast_records
                and not forecast_missing_valid_date
                and not forecast_missing_lead_day
                and not forecast_invalid_lead_day
                and not forecast_invalid_horizon
                else "fail"
                if forecast_missing_valid_date
                or forecast_missing_lead_day
                or forecast_invalid_lead_day
                or forecast_invalid_horizon
                else "warning"
            ),
            answer=(
                "Every forecast record has a valid date and lead day."
                if forecast_records
                and not forecast_missing_valid_date
                and not forecast_missing_lead_day
                and not forecast_invalid_lead_day
                and not forecast_invalid_horizon
                else "One or more forecast records lack valid-date or lead-day coverage."
                if forecast_missing_valid_date
                or forecast_missing_lead_day
                or forecast_invalid_lead_day
                or forecast_invalid_horizon
                else "No forecast records exist to verify valid dates and lead days."
            ),
            evidence={
                "records_missing_valid_date": len(forecast_missing_valid_date),
                "records_missing_lead_day": len(forecast_missing_lead_day),
                "records_invalid_lead_day": len(forecast_invalid_lead_day),
                "records_invalid_forecast_horizon": len(forecast_invalid_horizon),
                "max_lead_day": max_lead_day,
                "max_forecast_horizon_days": max_forecast_horizon_days,
            },
            gaps=[
                gap
                for gap, condition in [
                    ("forecast_records_missing_valid_date", bool(forecast_missing_valid_date)),
                    ("forecast_records_missing_lead_day", bool(forecast_missing_lead_day)),
                    ("forecast_records_invalid_lead_day", bool(forecast_invalid_lead_day)),
                    ("forecast_records_invalid_forecast_horizon", bool(forecast_invalid_horizon)),
                ]
                if condition
            ],
        ),
        _audit_question(
            question_id="rolling_derived_windows_classified",
            status="pass" if derived_records else "warning",
            answer=(
                "Derived climate records exist with derived record types."
                if derived_records
                else "No derived rolling-window or anomaly climate records are persisted yet; current rolling windows live in feature rows."
            ),
            evidence={"derived_record_count": len(derived_records)},
            gaps=[] if derived_records else ["derived_climate_records_not_persisted_yet"],
        ),
        _audit_question(
            question_id="fallback_behavior_classified",
            status=(
                "pass"
                if fallback_records and not fallback_without_flag
                else "fail"
                if fallback_without_flag
                else "warning"
            ),
            answer=(
                "Fallback rainfall records are explicitly flagged."
                if fallback_records and not fallback_without_flag
                else "Fallback static records exist without fallback flags."
                if fallback_without_flag
                else "No fallback rainfall records are currently present."
            ),
            evidence={
                "fallback_record_count": len(fallback_records),
                "fallback_records_without_flag": len(fallback_without_flag),
            },
            gaps=["fallback_static_records_without_fallback_flag"] if fallback_without_flag else [],
        ),
        _audit_question(
            question_id="ward_linkage_available",
            status=(
                "pass"
                if records and not records_missing_or_invalid_ward and not records_with_ward_identity_mismatch
                else "fail"
                if records_missing_or_invalid_ward or records_with_ward_identity_mismatch
                else "warning"
            ),
            answer=(
                "Every climate record links to an existing ward and any supplied ward name matches that ward."
                if records and not records_missing_or_invalid_ward and not records_with_ward_identity_mismatch
                else "One or more climate records have missing, stale, or mismatched ward linkage."
                if records_missing_or_invalid_ward or records_with_ward_identity_mismatch
                else "No climate records exist to verify ward linkage."
            ),
            evidence={
                "record_count": len(records),
                "records_missing_or_invalid_ward": len(records_missing_or_invalid_ward),
                "records_with_ward_identity_mismatch": len(records_with_ward_identity_mismatch),
            },
            gaps=[
                gap
                for gap, condition in [
                    ("climate_records_missing_or_invalid_ward", bool(records_missing_or_invalid_ward)),
                    ("climate_records_ward_identity_mismatch", bool(records_with_ward_identity_mismatch)),
                ]
                if condition
            ],
        ),
        _audit_question(
            question_id="climate_record_contract",
            status="fail" if hard_gaps else "pass" if records else "warning",
            answer=(
                "Climate records satisfy the Phase 1 source-separation contract."
                if records and not hard_gaps
                else "Climate records violate the Phase 1 source-separation contract."
                if hard_gaps
                else "No climate records exist to verify the Phase 1 contract."
            ),
            evidence={
                "contract_schema_version": CLIMATE_SOURCE_AUDIT_SCHEMA_VERSION,
                "record_count": len(records),
                "climate_record_table_available": climate_record_table_available,
                "records_invalid_record_type": len(records_invalid_record_type),
                "records_missing_source_provider": len(records_missing_source_provider),
                "records_missing_source_run": len(records_missing_source_run),
                "records_missing_or_invalid_rainfall_value": len(records_missing_or_invalid_rainfall),
                "records_missing_or_invalid_ward": len(records_missing_or_invalid_ward),
                "records_with_ward_identity_mismatch": len(records_with_ward_identity_mismatch),
                "hard_gap_count": len(hard_gaps),
            },
            gaps=hard_gaps,
        ),
    ]
    if hard_gaps:
        overall_status = "fail"
    elif source_gaps:
        overall_status = "warning"
    else:
        overall_status = "pass"

    return {
        "audit_name": "climate_forecast_horizon_source_separation_phase_0_1",
        "schema_version": CLIMATE_SOURCE_AUDIT_SCHEMA_VERSION,
        "overall_status": overall_status,
        "record_totals": {
            "rainfall_ingestion_runs": IngestionRun.objects.filter(run_type=IngestionRun.RUN_TYPE_RAINFALL).count(),
            "climate_records": _climate_record_count(),
            "contract_records_seen": len(records),
            "fallback_records": len(fallback_records),
            "forecast_records": len(forecast_records),
            "observed_records": len(observed_records),
            "derived_records": len(derived_records),
        },
        "source_inventory": {
            "record_type_counts": dict(record_type_counts),
            "source_provider_counts": dict(source_provider_counts),
            "storage_counts": dict(storage_counts),
            "max_lead_day": max_lead_day,
            "max_forecast_horizon_days": max_forecast_horizon_days,
            "supports_7_day_forecast_claim": max_lead_day >= 7,
            "supports_14_day_forecast_claim": max_lead_day >= 14,
        },
        "source_gaps": source_gaps,
        "hard_gaps": hard_gaps,
        "verification_questions": verification_questions,
        "operator_guidance": {
            "phase_0_exit_criteria": "Current rainfall lineage, source gaps, and fallback behavior are explicitly inventoried.",
            "phase_1_exit_criteria": "Climate records carry record type, issue/valid dates, lead day, fallback flag, source run, and lineage metadata.",
            "strict_command": "python manage.py audit_climate_sources --strict",
        },
    }
