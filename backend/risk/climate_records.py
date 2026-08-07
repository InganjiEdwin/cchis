from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timedelta
from typing import Any

from django.db import connection
from django.utils import timezone

from risk.models import ClimateRecord, ClimateRecordQualityFlag, ClimateRecordType, IngestionRun, Ward


CLIMATE_RECORD_CONTRACT_SCHEMA_VERSION = "climate-record-contract-v1"

FORECAST_SOURCE_HINTS = ("forecast", "gfs", "ecmwf", "icpac", "open-meteo")
OBSERVED_SOURCE_HINTS = ("observed", "observation", "gauge", "station", "imerg", "chirps", "era5")
STATIC_SOURCE_HINTS = ("static", "seed", "fallback")

# Keep source classification in one place.  A connector must opt into LIVE by
# using a provider in this registry; unknown providers are never promoted to
# live merely because they happen to return a value.
LIVE_SOURCE_PROVIDERS = frozenset({"open-meteo-forecast", "chirps-v3.0"})


def classify_source_kind(
    source_provider: str,
    *,
    fallback_flag: bool = False,
    fallback_reason: str = "",
) -> str:
    provider = (source_provider or "").strip().lower()
    if fallback_flag or fallback_reason or _source_has_hint(provider, STATIC_SOURCE_HINTS):
        return IngestionRun.SOURCE_KIND_SEEDED
    if provider in LIVE_SOURCE_PROVIDERS:
        return IngestionRun.SOURCE_KIND_LIVE
    return IngestionRun.SOURCE_KIND_SEEDED


def _normalise_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if timezone.is_naive(value):
        return timezone.make_aware(value, timezone.get_current_timezone())
    return value


def _parse_datetime(value: Any) -> datetime | None:
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


def _parse_date(value: Any) -> date | None:
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


def _ward_identity_skip_reason(enriched: dict[str, Any]) -> str:
    ward_id = _safe_int(enriched.get("ward_id"))
    if ward_id is None:
        return "missing_ward_id"
    ward_name = Ward.objects.filter(pk=ward_id).values_list("name", flat=True).first()
    if ward_name is None:
        return "ward_not_found"
    source_ward_name = _normalise_identity(enriched.get("ward_name"))
    if source_ward_name and source_ward_name != _normalise_identity(ward_name):
        return "ward_identity_mismatch"
    return ""


def _source_has_hint(source: str, hints: Iterable[str]) -> bool:
    lowered = (source or "").strip().lower()
    return any(hint in lowered for hint in hints)


def classify_climate_record_type(
    *,
    source_provider: str,
    fallback_reason: str = "",
    fallback_flag: bool = False,
) -> str:
    if fallback_flag or fallback_reason or _source_has_hint(source_provider, STATIC_SOURCE_HINTS):
        return ClimateRecordType.FALLBACK_STATIC
    if _source_has_hint(source_provider, FORECAST_SOURCE_HINTS):
        return ClimateRecordType.FORECAST
    if _source_has_hint(source_provider, OBSERVED_SOURCE_HINTS):
        return ClimateRecordType.OBSERVED
    return ClimateRecordType.OBSERVED


def climate_record_table_available() -> bool:
    return ClimateRecord._meta.db_table in connection.introspection.table_names()


def _quality_flag_for_contract(
    *,
    record_type: str,
    fallback_flag: bool,
    issue_time: datetime | None,
    valid_date: date | None,
    lead_day: int | None,
    observed_timestamp: datetime | None,
) -> str:
    if fallback_flag or record_type == ClimateRecordType.FALLBACK_STATIC:
        return ClimateRecordQualityFlag.DEGRADED_FALLBACK
    if record_type == ClimateRecordType.FORECAST and (
        issue_time is None or valid_date is None or lead_day is None
    ):
        return ClimateRecordQualityFlag.MISSING_FORECAST_CONTRACT
    if record_type == ClimateRecordType.OBSERVED and observed_timestamp is None:
        return ClimateRecordQualityFlag.MISSING_OBSERVED_TIMESTAMP
    if record_type in {ClimateRecordType.DERIVED_ROLLING_WINDOW, ClimateRecordType.DERIVED_ANOMALY}:
        return ClimateRecordQualityFlag.DERIVED
    return ClimateRecordQualityFlag.ACCEPTED


def _legacy_forecast_contract_patch(
    *,
    ingestion_run: IngestionRun,
    result: dict[str, Any],
    infer_horizon_days: int | None,
) -> dict[str, Any]:
    if not infer_horizon_days:
        return result
    source_provider = result.get("source") or (result.get("canonical_record") or {}).get("source_name") or ""
    record_type = result.get("record_type") or (result.get("canonical_record") or {}).get("record_type")
    if record_type not in (None, "", ClimateRecordType.FORECAST) and not _source_has_hint(
        source_provider,
        FORECAST_SOURCE_HINTS,
    ):
        return result
    if not _source_has_hint(source_provider, FORECAST_SOURCE_HINTS):
        return result
    if result.get("issue_time") and result.get("valid_date") and result.get("lead_day"):
        return result

    issue_time = (
        _parse_datetime(result.get("issue_time"))
        or _parse_datetime(result.get("source_timestamp"))
        or _parse_datetime(ingestion_run.source_timestamp)
        or _parse_datetime(ingestion_run.completed_at)
        or _parse_datetime(ingestion_run.started_at)
    )
    if issue_time is None:
        return result

    patched = dict(result)
    canonical = dict(patched.get("canonical_record") or {})
    lineage_metadata = {
        **(canonical.get("lineage_metadata") if isinstance(canonical.get("lineage_metadata"), dict) else {}),
        **(patched.get("lineage_metadata") if isinstance(patched.get("lineage_metadata"), dict) else {}),
        "legacy_contract_inference": {
            "source": "backfill_climate_records",
            "issue_time_policy": "ingestion_timestamp_used_when_provider_issue_time_missing",
            "forecast_horizon_days": infer_horizon_days,
        },
    }
    valid_date = issue_time.date() + timedelta(days=max(infer_horizon_days - 1, 0))
    patched.update(
        {
            "record_type": ClimateRecordType.FORECAST,
            "issue_time": issue_time.isoformat(),
            "valid_date": valid_date.isoformat(),
            "lead_day": infer_horizon_days,
            "forecast_horizon_days": infer_horizon_days,
            "quality_flag": patched.get("quality_flag") or ClimateRecordQualityFlag.MISSING_FORECAST_CONTRACT,
            "fallback_flag": False,
            "lineage_metadata": lineage_metadata,
        }
    )
    canonical.update(
        {
            "record_type": ClimateRecordType.FORECAST,
            "issue_time": issue_time.isoformat(),
            "valid_date": valid_date.isoformat(),
            "lead_day": infer_horizon_days,
            "forecast_horizon_days": infer_horizon_days,
            "quality_flag": patched["quality_flag"],
            "fallback_flag": False,
            "lineage_metadata": lineage_metadata,
        }
    )
    patched["canonical_record"] = canonical
    return patched


def enrich_rainfall_result_with_climate_contract(
    *,
    ingestion_run: IngestionRun,
    result: dict[str, Any],
    row_index: int,
) -> dict[str, Any]:
    enriched = dict(result)
    canonical = dict(enriched.get("canonical_record") or {})
    source_provider = (
        enriched.get("source")
        or canonical.get("source_name")
        or ingestion_run.source_name
        or "unknown-rainfall-source"
    )
    fallback_reason = enriched.get("fallback_reason") or canonical.get("fallback_reason") or ""
    fallback_flag = bool(
        enriched.get("fallback_flag")
        or canonical.get("fallback_flag")
        or fallback_reason
        or _source_has_hint(source_provider, STATIC_SOURCE_HINTS)
    )
    record_type = (
        enriched.get("record_type")
        or canonical.get("record_type")
        or classify_climate_record_type(
            source_provider=source_provider,
            fallback_reason=fallback_reason,
            fallback_flag=fallback_flag,
        )
    )
    source_timestamp = (
        _parse_datetime(enriched.get("source_timestamp"))
        or _parse_datetime(canonical.get("source_timestamp"))
        or _parse_datetime(ingestion_run.source_timestamp)
        or _parse_datetime(ingestion_run.completed_at)
    )
    issue_time = _parse_datetime(enriched.get("issue_time")) or _parse_datetime(canonical.get("issue_time"))
    observed_timestamp = _parse_datetime(enriched.get("observed_timestamp")) or _parse_datetime(
        canonical.get("observed_timestamp")
    )
    lead_day = _safe_int(enriched.get("lead_day"))
    if lead_day is None:
        lead_day = _safe_int(canonical.get("lead_day"))
    forecast_horizon_days = _safe_int(enriched.get("forecast_horizon_days"))
    if forecast_horizon_days is None:
        forecast_horizon_days = _safe_int(canonical.get("forecast_horizon_days"))
    valid_date = _parse_date(enriched.get("valid_date")) or _parse_date(canonical.get("valid_date"))

    if record_type == ClimateRecordType.FORECAST:
        issue_time = issue_time or source_timestamp
        if lead_day is None and valid_date is not None and issue_time is not None:
            lead_day = max((valid_date - issue_time.date()).days + 1, 1)
        if lead_day is not None and lead_day <= 0:
            lead_day = None
        if forecast_horizon_days is not None and forecast_horizon_days <= 0:
            forecast_horizon_days = None
        if forecast_horizon_days is None and lead_day is not None:
            forecast_horizon_days = lead_day
        if valid_date is None and issue_time is not None:
            valid_date = (
                issue_time.date() + timedelta(days=max(lead_day - 1, 0))
                if lead_day is not None
                else None
            )
    elif record_type == ClimateRecordType.OBSERVED:
        observed_timestamp = observed_timestamp or source_timestamp
        valid_date = valid_date or (observed_timestamp.date() if observed_timestamp else None)
    else:
        forecast_horizon_days = forecast_horizon_days or 0

    quality_flag = (
        enriched.get("quality_flag")
        or canonical.get("quality_flag")
        or _quality_flag_for_contract(
            record_type=record_type,
            fallback_flag=fallback_flag,
            issue_time=issue_time,
            valid_date=valid_date,
            lead_day=lead_day,
            observed_timestamp=observed_timestamp,
        )
    )
    source_run = enriched.get("source_run") or canonical.get("source_run") or f"ingestion_run:{ingestion_run.id}"
    source_ref = (
        enriched.get("source_ref")
        or canonical.get("record_ref")
        or f"climate_record:rainfall_ingestion_run:{ingestion_run.id}:result:{row_index}"
    )
    lineage_metadata = {
        **(canonical.get("lineage_metadata") if isinstance(canonical.get("lineage_metadata"), dict) else {}),
        **(enriched.get("lineage_metadata") if isinstance(enriched.get("lineage_metadata"), dict) else {}),
        "contract_schema_version": CLIMATE_RECORD_CONTRACT_SCHEMA_VERSION,
        "contract_source": "rainfall_ingestion_finalizer",
        "rainfall_ingestion_run_id": ingestion_run.id,
        "rainfall_ingestion_status": ingestion_run.status,
        "rainfall_result_row_index": row_index,
        "source_mode": ingestion_run.source_mode,
        "source_kind": ingestion_run.source_kind,
        "freshness_state": ingestion_run.freshness_state,
        "fallback_reason": fallback_reason,
    }
    contract_fields = {
        "source_ref": source_ref,
        "record_ref": source_ref,
        "record_type": record_type,
        "issue_time": issue_time.isoformat() if issue_time else None,
        "valid_date": valid_date.isoformat() if valid_date else None,
        "lead_day": lead_day,
        "observed_timestamp": observed_timestamp.isoformat() if observed_timestamp else None,
        "forecast_horizon_days": forecast_horizon_days,
        "quality_flag": quality_flag,
        "fallback_flag": fallback_flag,
        "source_run": source_run,
        "lineage_metadata": lineage_metadata,
    }
    canonical.update(contract_fields)
    enriched.update(
        {
            **contract_fields,
            "source": source_provider,
            "fallback_reason": fallback_reason,
            "canonical_record": canonical,
        }
    )
    return enriched


def persist_climate_records_for_ingestion_run(ingestion_run: IngestionRun) -> int:
    if ingestion_run.run_type != IngestionRun.RUN_TYPE_RAINFALL:
        return 0
    if not climate_record_table_available():
        return 0

    saved_count = 0
    results = ingestion_run.results if isinstance(ingestion_run.results, list) else []
    for row_index, result in enumerate(results):
        if not isinstance(result, dict):
            continue
        enriched = enrich_rainfall_result_with_climate_contract(
            ingestion_run=ingestion_run,
            result=result,
            row_index=row_index,
        )
        ward_id = _safe_int(enriched.get("ward_id"))
        rainfall_mm = _safe_float(enriched.get("rainfall_mm"))
        source_ref = enriched.get("source_ref") or enriched.get("record_ref")
        if _ward_identity_skip_reason(enriched) or rainfall_mm is None or not source_ref:
            continue
        if (
            enriched["record_type"] == ClimateRecordType.FORECAST
            and (
                _parse_datetime(enriched.get("issue_time")) is None
                or _parse_date(enriched.get("valid_date")) is None
                or _safe_int(enriched.get("lead_day")) is None
            )
        ):
            continue

        ClimateRecord.objects.update_or_create(
            ingestion_run=ingestion_run,
            source_ref=source_ref,
            defaults={
                "ward_id": ward_id,
                "record_type": enriched["record_type"],
                "source_provider": enriched["source"],
                "source_kind": ingestion_run.source_kind,
                "source_mode": ingestion_run.source_mode,
                "issue_time": _parse_datetime(enriched.get("issue_time")),
                "valid_date": _parse_date(enriched.get("valid_date")),
                "lead_day": _safe_int(enriched.get("lead_day")),
                "observed_timestamp": _parse_datetime(enriched.get("observed_timestamp")),
                "forecast_horizon_days": _safe_int(enriched.get("forecast_horizon_days")) or 0,
                "rainfall_mm": rainfall_mm,
                "quality_flag": enriched["quality_flag"],
                "fallback_flag": bool(enriched.get("fallback_flag")),
                "source_run": enriched["source_run"],
                "lineage_metadata": enriched.get("lineage_metadata") or {},
                "raw_payload": enriched,
            },
        )
        saved_count += 1
    return saved_count


def _climate_record_backfill_row_status(enriched: dict[str, Any]) -> tuple[str, str]:
    ward_skip_reason = _ward_identity_skip_reason(enriched)
    if ward_skip_reason:
        return "skipped", ward_skip_reason
    rainfall_mm = _safe_float(enriched.get("rainfall_mm"))
    source_ref = enriched.get("source_ref") or enriched.get("record_ref")
    if rainfall_mm is None:
        return "skipped", "missing_rainfall_mm"
    if not source_ref:
        return "skipped", "missing_source_ref"
    record_type = enriched.get("record_type")
    if record_type == ClimateRecordType.FORECAST and (
        _parse_datetime(enriched.get("issue_time")) is None
        or _parse_date(enriched.get("valid_date")) is None
        or _safe_int(enriched.get("lead_day")) is None
        or (_safe_int(enriched.get("lead_day")) or 0) <= 0
        or (_safe_int(enriched.get("forecast_horizon_days")) or 0) < (_safe_int(enriched.get("lead_day")) or 0)
    ):
        return "skipped", "invalid_forecast_contract"
    if record_type == ClimateRecordType.OBSERVED and _parse_datetime(enriched.get("observed_timestamp")) is None:
        return "skipped", "invalid_observed_contract"
    if record_type == ClimateRecordType.FALLBACK_STATIC and not enriched.get("fallback_flag"):
        return "skipped", "invalid_fallback_contract"
    return "ready", ""


def backfill_climate_records_from_ingestion_runs(
    *,
    dry_run: bool = True,
    infer_legacy_open_meteo_horizon_days: int | None = None,
    run_id: int | None = None,
) -> dict:
    if infer_legacy_open_meteo_horizon_days is not None and infer_legacy_open_meteo_horizon_days <= 0:
        raise ValueError("infer_legacy_open_meteo_horizon_days must be greater than zero.")

    table_available = climate_record_table_available()
    if not table_available:
        return {
            "schema_version": CLIMATE_RECORD_CONTRACT_SCHEMA_VERSION,
            "dry_run": dry_run,
            "climate_record_table_available": False,
            "runs_scanned": 0,
            "rows_seen": 0,
            "ready_rows": 0,
            "skipped_rows": 0,
            "saved_records": 0,
            "skip_reasons": {"climate_record_table_missing_or_migrations_not_applied": 1},
            "examples": [],
        }

    queryset = IngestionRun.objects.filter(run_type=IngestionRun.RUN_TYPE_RAINFALL).order_by("id")
    if run_id is not None:
        queryset = queryset.filter(id=run_id)

    runs_scanned = 0
    rows_seen = 0
    ready_rows = 0
    skipped_rows = 0
    saved_records = 0
    skip_reasons: dict[str, int] = {}
    examples = []

    for ingestion_run in queryset:
        runs_scanned += 1
        raw_results = ingestion_run.results if isinstance(ingestion_run.results, list) else []
        enriched_results = []
        run_ready_rows = 0
        for row_index, result in enumerate(raw_results):
            if not isinstance(result, dict):
                skipped_rows += 1
                skip_reasons["non_dict_result"] = skip_reasons.get("non_dict_result", 0) + 1
                continue
            rows_seen += 1
            patched = _legacy_forecast_contract_patch(
                ingestion_run=ingestion_run,
                result=result,
                infer_horizon_days=infer_legacy_open_meteo_horizon_days,
            )
            enriched = enrich_rainfall_result_with_climate_contract(
                ingestion_run=ingestion_run,
                result=patched,
                row_index=row_index,
            )
            status, reason = _climate_record_backfill_row_status(enriched)
            enriched_results.append(enriched)
            if status == "ready":
                ready_rows += 1
                run_ready_rows += 1
                continue
            skipped_rows += 1
            skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
            if len(examples) < 50:
                examples.append(
                    {
                        "ingestion_run_id": ingestion_run.id,
                        "row_index": row_index,
                        "ward_id": enriched.get("ward_id"),
                        "record_type": enriched.get("record_type"),
                        "status": status,
                        "reason": reason,
                    }
                )

        if dry_run or run_ready_rows == 0:
            continue
        ingestion_run.results = enriched_results
        ingestion_run.save(update_fields=["results"])
        saved_records += persist_climate_records_for_ingestion_run(ingestion_run)

    return {
        "schema_version": CLIMATE_RECORD_CONTRACT_SCHEMA_VERSION,
        "dry_run": dry_run,
        "climate_record_table_available": True,
        "runs_scanned": runs_scanned,
        "rows_seen": rows_seen,
        "ready_rows": ready_rows,
        "skipped_rows": skipped_rows,
        "saved_records": saved_records,
        "skip_reasons": skip_reasons,
        "examples": examples,
    }
