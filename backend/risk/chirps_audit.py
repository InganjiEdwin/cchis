"""Strict audits for the CHIRPS v3 historical ingestion contract."""

from __future__ import annotations

import math
from collections import Counter
from datetime import date, datetime, timedelta

from django.db.models import Count

from risk.climate.connectors.chirps import (
    CHIRPS_DAILY_VARIANTS,
    CHIRPS_COVERAGE_NUMERICAL_EPSILON,
    CHIRPS_PROCESSING_CODE_VERSION,
    CHIRPS_PRODUCT_STATUS_FINAL,
    CHIRPS_PROVIDER,
    CHIRPS_VERSION,
    build_chirps_asset_url,
    chirps_min_coverage_fraction,
)
from risk.chirps_ingestion import (
    chirps_identity_key,
    chirps_source_ref,
    chirps_source_run_ref,
    load_active_migori_ward_polygons,
)
from risk.lead_time_features import LEAD_TIME_FEATURE_SCHEMA_VERSION
from risk.models import (
    ClimateRecord,
    ClimateRecordQualityFlag,
    ClimateRecordType,
    FeatureDataset,
    FeatureDatasetRow,
    IngestionRun,
    Ward,
)


CHIRPS_AUDIT_SCHEMA_VERSION = "chirps-ingestion-audit-v1"
CHIRPS_FEATURE_TOTAL_TOLERANCE_MM = 0.01
CHIRPS_REQUIRED_LINEAGE_FIELDS = (
    "chirps_version",
    "product_status",
    "daily_variant",
    "source_date",
    "official_asset_url",
    "asset_filename",
    "retrieval_timestamp",
    "raster_crs",
    "raster_transform",
    "raster_resolution",
    "raster_nodata",
    "aggregation_method",
    "valid_pixel_count",
    "ward_coverage_fraction",
    "ward_public_id",
    "ward_geometry_dataset_version",
    "ward_geometry_hash",
    "processing_code_version",
    "chirps_daily_disaggregation_method",
    "daily_interval_start",
    "daily_interval_end",
)


def _parse_date(value) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _parse_datetime(value) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _check(check_id: str, status: str, *, evidence: dict, issues: list[dict] | None = None) -> dict:
    issue_list = issues or []
    return {
        "id": check_id,
        "status": status,
        "evidence": evidence,
        "issues": issue_list,
        "fail_count": sum(1 for issue in issue_list if issue.get("severity") == "fail"),
        "warning_count": sum(1 for issue in issue_list if issue.get("severity") == "warning"),
    }


def _issue(*, severity: str, message: str, record: ClimateRecord | None = None, context: dict | None = None) -> dict:
    payload = {
        "severity": severity,
        "message": message,
    }
    if record is not None:
        payload.update(
            {
                "record_id": record.id,
                "ward_id": record.ward_id,
                "valid_date": record.valid_date.isoformat() if record.valid_date else None,
                "source_ref": record.source_ref,
            }
        )
    if context:
        payload.update(context)
    return payload


def _date_list(start_date: date, end_date: date) -> list[str]:
    return [
        (start_date + timedelta(days=offset)).isoformat()
        for offset in range((end_date - start_date).days + 1)
    ]


def _canonical_run_ward_reference_check(runs: list[IngestionRun], active_wards: list[Ward]) -> dict:
    expected_ward_public_ids = {str(ward.public_id) for ward in active_wards}
    issues: list[dict] = []

    for run in runs:
        requested_wards = {str(value) for value in (run.requested_wards or [])}
        lineage = run.lineage_metadata if isinstance(run.lineage_metadata, dict) else {}
        lineage_requested_wards = {
            str(value) for value in (lineage.get("requested_ward_public_ids") or [])
        }
        if requested_wards != expected_ward_public_ids or lineage_requested_wards != expected_ward_public_ids:
            issues.append(
                _issue(
                    severity="fail",
                    message="CHIRPS run does not reference every active canonical Migori ward.",
                    context={
                        "run_id": run.id,
                        "expected_ward_count": len(expected_ward_public_ids),
                        "requested_ward_count": len(requested_wards),
                        "lineage_requested_ward_count": len(lineage_requested_wards),
                        "missing_requested_ward_public_ids": sorted(
                            expected_ward_public_ids - requested_wards
                        ),
                        "missing_lineage_ward_public_ids": sorted(
                            expected_ward_public_ids - lineage_requested_wards
                        ),
                        "unexpected_requested_ward_public_ids": sorted(
                            requested_wards - expected_ward_public_ids
                        ),
                        "unexpected_lineage_ward_public_ids": sorted(
                            lineage_requested_wards - expected_ward_public_ids
                        ),
                    },
                )
            )

    return _check(
        "chirps_runs_reference_all_canonical_wards",
        "fail" if issues else "pass" if runs and active_wards else "warning",
        evidence={
            "run_count": len(runs),
            "active_migori_ward_count": len(active_wards),
            "expected_ward_public_id_count": len(expected_ward_public_ids),
        },
        issues=issues,
    )


def _accepted_run_observation_check(
    records: list[ClimateRecord],
    runs: list[IngestionRun],
    active_wards: list[Ward],
) -> dict:
    expected_ward_public_ids = {str(ward.public_id) for ward in active_wards}
    accepted_runs = [run for run in runs if run.status == IngestionRun.STATUS_SUCCESS]
    records_by_run_date_ward_mode = Counter(
        (
            record.ingestion_run_id,
            record.valid_date.isoformat(),
            str(record.ward.public_id),
            record.source_mode,
        )
        for record in records
        if record.ingestion_run_id and record.valid_date and record.ward_id
    )
    issues: list[dict] = []

    for run in accepted_runs:
        lineage = run.lineage_metadata if isinstance(run.lineage_metadata, dict) else {}
        run_variant = f"{lineage.get('product_status', CHIRPS_PRODUCT_STATUS_FINAL)}-{lineage.get('daily_variant', '')}"
        processed_dates = [str(value) for value in lineage.get("processed_dates", [])]
        attached_record_count = sum(
            count
            for (run_id, _source_date, ward_public_id, source_mode), count in records_by_run_date_ward_mode.items()
            if run_id == run.id
            and ward_public_id in expected_ward_public_ids
            and source_mode == run_variant
        )
        expected_record_count = len(processed_dates) * len(expected_ward_public_ids)
        if (
            attached_record_count != expected_record_count
            or run.records_loaded != attached_record_count
            or lineage.get("unavailable_dates")
            or lineage.get("rejected_dates")
        ):
            issues.append(
                _issue(
                    severity="fail",
                    message="Accepted CHIRPS run does not have its complete persisted observations.",
                    context={
                        "run_id": run.id,
                        "processed_date_count": len(processed_dates),
                        "expected_record_count": expected_record_count,
                        "attached_record_count": attached_record_count,
                        "run_records_loaded": run.records_loaded,
                        "unavailable_dates": [str(value) for value in lineage.get("unavailable_dates", [])],
                        "rejected_dates": [str(value) for value in lineage.get("rejected_dates", [])],
                    },
                )
            )

        for source_date in processed_dates:
            ward_count = sum(
                count
                for (run_id, record_date, ward_public_id, source_mode), count in records_by_run_date_ward_mode.items()
                if run_id == run.id
                and record_date == source_date
                and ward_public_id in expected_ward_public_ids
                and source_mode == run_variant
            )
            if ward_count != len(expected_ward_public_ids):
                issues.append(
                    _issue(
                        severity="fail",
                        message="Accepted CHIRPS date does not have one persisted observation for every canonical ward.",
                        context={
                            "run_id": run.id,
                            "source_date": source_date,
                            "expected_ward_count": len(expected_ward_public_ids),
                            "actual_record_count": ward_count,
                        },
                    )
                )

    return _check(
        "chirps_accepted_runs_have_complete_observations",
        "fail" if issues else "pass" if accepted_runs and active_wards else "warning",
        evidence={
            "accepted_run_count": len(accepted_runs),
            "active_migori_ward_count": len(active_wards),
            "records_scanned": len(records),
        },
        issues=issues,
    )


def _completeness_check(records: list[ClimateRecord], active_wards: list[Ward], runs: list[IngestionRun]) -> dict:
    records_by_date_ward = Counter(
        (record.valid_date.isoformat(), str(record.ward.public_id))
        for record in records
        if record.valid_date and record.ward_id
    )
    records_by_date_ward_mode = Counter(
        (record.valid_date.isoformat(), str(record.ward.public_id), record.source_mode)
        for record in records
        if record.valid_date and record.ward_id
    )
    issues: list[dict] = []
    incomplete_dates: list[dict] = []
    missing_requested_dates: list[dict] = []
    rejected_dates: list[dict] = []
    explicit_unavailable_dates: set[str] = set()
    processed_dates: set[str] = set()
    requested_dates: set[str] = set()
    expected_ward_ids = {str(ward.public_id) for ward in active_wards}

    for run in runs:
        metadata = run.lineage_metadata if isinstance(run.lineage_metadata, dict) else {}
        requested = [str(value) for value in metadata.get("requested_dates", [])]
        requested_dates.update(requested)
        explicit_unavailable_dates.update(str(value) for value in metadata.get("unavailable_dates", []))
        rejected_dates.extend(
            {"run_id": run.id, "source_date": str(value)}
            for value in metadata.get("rejected_dates", [])
        )
        processed_dates.update(str(value) for value in metadata.get("processed_dates", []))

        run_variant = f"{metadata.get('product_status', CHIRPS_PRODUCT_STATUS_FINAL)}-{metadata.get('daily_variant', '')}"
        for source_date in metadata.get("processed_dates", []):
            source_date = str(source_date)
            ward_count = sum(
                count
                for (record_date, ward_public_id, source_mode), count in records_by_date_ward_mode.items()
                if record_date == source_date
                and ward_public_id in expected_ward_ids
                and source_mode == run_variant
            )
            if ward_count != len(expected_ward_ids):
                incomplete_dates.append(
                    {
                        "run_id": run.id,
                        "source_date": source_date,
                        "expected_ward_count": len(expected_ward_ids),
                        "actual_record_count": ward_count,
                    }
                )

        start_date = _parse_date(metadata.get("start_date"))
        end_date = _parse_date(metadata.get("end_date"))
        if start_date and end_date:
            expected_dates = set(_date_list(start_date, end_date))
            if set(requested) != expected_dates:
                missing_requested_dates.append(
                    {
                        "run_id": run.id,
                        "expected_dates": sorted(expected_dates),
                        "requested_dates": sorted(requested),
                    }
                )
            reported = {str(value) for value in metadata.get("processed_dates", [])}
            reported.update(str(value) for value in metadata.get("unavailable_dates", []))
            reported.update(str(value) for value in metadata.get("rejected_dates", []))
            unreported = expected_dates - reported
            if unreported:
                issues.append(
                    _issue(
                        severity="fail",
                        message="Requested date range contains dates not represented as processed, unavailable or rejected.",
                        context={"run_id": run.id, "dates": sorted(unreported)},
                    )
                )
            unexpected = reported - expected_dates
            if unexpected:
                issues.append(
                    _issue(
                        severity="fail",
                        message="CHIRPS run lineage reports dates outside its requested range.",
                        context={"run_id": run.id, "dates": sorted(unexpected)},
                    )
                )

    if incomplete_dates:
        issues.extend(
            _issue(
                severity="fail",
                message="A processed CHIRPS date does not have one record for every active Migori ward.",
                context=item,
            )
            for item in incomplete_dates
        )
    if missing_requested_dates:
        issues.extend(
            _issue(
                severity="fail",
                message="CHIRPS run requested-date lineage is not contiguous.",
                context=item,
            )
            for item in missing_requested_dates
        )
    # Explicitly unavailable dates are permitted by the contract, but an
    # explicitly rejected date is not equivalent to a source-unavailable date.
    if rejected_dates:
        issues.extend(
            _issue(
                severity="fail",
                message="CHIRPS date was rejected during raster validation/aggregation.",
                context=item,
            )
            for item in rejected_dates
        )

    status = "fail" if issues else "pass" if runs and active_wards else "warning"
    return _check(
        "processed_dates_have_complete_active_ward_coverage",
        status,
        evidence={
            "run_count": len(runs),
            "active_ward_count": len(active_wards),
            "requested_date_count": len(requested_dates),
            "processed_date_count": len(processed_dates),
            "explicitly_unavailable_dates": sorted(explicit_unavailable_dates),
            "rejected_dates": rejected_dates,
            "incomplete_dates": incomplete_dates,
            "duplicate_date_ward_pairs": sum(
                1 for count in records_by_date_ward.values() if count > 1
            ),
        },
        issues=issues,
    )


def _quality_flag_check(records: list[ClimateRecord]) -> dict:
    issues = [
        _issue(
            severity="fail",
            message="CHIRPS records must have quality_flag=accepted.",
            record=record,
            context={"quality_flag": record.quality_flag},
        )
        for record in records
        if record.quality_flag != ClimateRecordQualityFlag.ACCEPTED
    ]
    return _check(
        "chirps_quality_flags_accepted",
        "fail" if issues else "pass" if records else "warning",
        evidence={
            "records_scanned": len(records),
            "accepted_record_count": sum(
                1 for record in records if record.quality_flag == ClimateRecordQualityFlag.ACCEPTED
            ),
            "invalid_quality_flag_count": len(issues),
        },
        issues=issues,
    )


def _canonical_source_identity_check(records: list[ClimateRecord]) -> dict:
    issues: list[dict] = []
    fields_checked = [
        "official_asset_url",
        "identity_key",
        "source_ref",
        "source_run",
    ]
    for record in records:
        lineage = record.lineage_metadata if isinstance(record.lineage_metadata, dict) else {}
        source_date = _parse_date(lineage.get("source_date"))
        variant = lineage.get("daily_variant")
        product_status = lineage.get("product_status")
        if source_date is None or variant not in CHIRPS_DAILY_VARIANTS or not product_status:
            continue

        ward_public_id = str(record.ward.public_id) if record.ward_id else ""
        expected = {}
        try:
            expected = {
                "official_asset_url": build_chirps_asset_url(
                    source_date,
                    variant=variant,
                    product_status=product_status,
                ),
                "identity_key": chirps_identity_key(
                    source_date=source_date,
                    variant=variant,
                    product_status=product_status,
                    ward_public_id=ward_public_id,
                ),
                "source_ref": chirps_source_ref(
                    source_date=source_date,
                    variant=variant,
                    product_status=product_status,
                    ward_public_id=ward_public_id,
                ),
                "source_run": chirps_source_run_ref(
                    source_date=source_date,
                    variant=variant,
                    product_status=product_status,
                ),
            }
        except (TypeError, ValueError) as exc:
            issues.append(
                _issue(
                    severity="fail",
                    message="CHIRPS canonical source identity could not be recomputed.",
                    record=record,
                    context={"error": str(exc)},
                )
            )
            continue

        actual = {
            "official_asset_url": lineage.get("official_asset_url"),
            "identity_key": record.identity_key,
            "source_ref": record.source_ref,
            "source_run": record.source_run,
        }
        mismatches = {
            field: {"expected": expected[field], "actual": actual[field]}
            for field in fields_checked
            if actual[field] != expected[field]
        }
        lineage_mismatches = {
            field: {"expected": expected[field], "actual": lineage.get(field)}
            for field in ("identity_key", "source_ref", "source_run")
            if lineage.get(field) != expected[field]
        }
        if mismatches or lineage_mismatches:
            issues.append(
                _issue(
                    severity="fail",
                    message="CHIRPS canonical URL, identity, source reference or source-run value does not match its source fields.",
                    record=record,
                    context={
                        "mismatches": mismatches,
                        "lineage_mismatches": lineage_mismatches,
                    },
                )
            )

    return _check(
        "canonical_chirps_url_identity_and_source_refs",
        "fail" if issues else "pass" if records else "warning",
        evidence={"records_scanned": len(records), "fields_recomputed": fields_checked},
        issues=issues,
    )


def _feature_temporal_cutoff_check(records: list[ClimateRecord]) -> dict:
    source_refs = {record.source_ref: record for record in records}
    rows = list(
        FeatureDatasetRow.objects.filter(
            dataset__schema_version=LEAD_TIME_FEATURE_SCHEMA_VERSION,
        ).select_related("dataset")
    )
    issues: list[dict] = []
    referenced_chirps = 0
    feature_rows_with_recomputed_totals = 0
    ward_reference_mismatch_count = 0
    duplicate_reference_count = 0
    if not rows:
        issues.append(
            _issue(
                severity="fail",
                message="No persisted lead-time feature rows exist for the CHIRPS source records.",
            )
        )
    for row in rows:
        values = row.feature_values if isinstance(row.feature_values, dict) else {}
        prediction_date = _parse_date(values.get("prediction_date"))
        source_cutoff = _parse_datetime(values.get("source_cutoff_timestamp"))
        rainfall_lineage = ((values.get("source_lineage") or {}).get("rainfall") or {})
        refs = rainfall_lineage.get("chirps_source_refs") or []
        if not isinstance(refs, list):
            refs = []
        refs = [str(ref) for ref in refs if ref]
        if prediction_date is None:
            issues.append(
                _issue(
                    severity="fail",
                    message="CHIRPS feature row is missing a valid prediction_date.",
                    context={"feature_row_id": row.id},
                )
            )
        if source_cutoff is None:
            issues.append(
                _issue(
                    severity="fail",
                    message="CHIRPS feature row is missing a valid source_cutoff_timestamp.",
                    context={"feature_row_id": row.id},
                )
            )
        if len(refs) != len(set(refs)):
            duplicate_reference_count += len(refs) - len(set(refs))
            issues.append(
                _issue(
                    severity="fail",
                    message="CHIRPS feature row repeats a source reference.",
                    context={"feature_row_id": row.id},
                )
            )
        referenced_records: list[ClimateRecord] = []
        for ref in refs:
            referenced_chirps += 1
            record = source_refs.get(ref)
            if record is None:
                issues.append(
                    _issue(
                        severity="fail",
                        message="Feature lineage references a missing CHIRPS source_ref.",
                        context={"feature_row_id": row.id, "source_ref": ref},
                    )
                )
                continue
            referenced_records.append(record)
            if row.ward_id is None or record.ward_id != row.ward_id:
                ward_reference_mismatch_count += 1
                issues.append(
                    _issue(
                        severity="fail",
                        message="CHIRPS feature lineage references a source record from a different ward.",
                        record=record,
                        context={
                            "feature_row_id": row.id,
                            "feature_ward_id": row.ward_id,
                            "source_ward_id": record.ward_id,
                        },
                    )
                )
            if record.record_type != ClimateRecordType.OBSERVED or record.fallback_flag:
                issues.append(
                    _issue(
                        severity="fail",
                        message="CHIRPS feature lineage includes a non-observed or fallback record.",
                        record=record,
                        context={"feature_row_id": row.id},
                    )
                )
            if prediction_date is not None and (
                record.valid_date is None or record.valid_date >= prediction_date
            ):
                issues.append(
                    _issue(
                        severity="fail",
                        message="CHIRPS feature includes rainfall on/after the prediction date.",
                        record=record,
                        context={"feature_row_id": row.id, "prediction_date": prediction_date.isoformat()},
                    )
                )
            if record.observed_timestamp is None:
                issues.append(
                    _issue(
                        severity="fail",
                        message="CHIRPS feature lineage references a record without observed_timestamp.",
                        record=record,
                        context={"feature_row_id": row.id},
                    )
                )
            elif source_cutoff and record.observed_timestamp >= source_cutoff:
                issues.append(
                    _issue(
                        severity="fail",
                        message="CHIRPS feature includes an observation at/after the source cutoff.",
                        record=record,
                        context={"feature_row_id": row.id},
                    )
                )

        if prediction_date is not None and source_cutoff is not None and referenced_records:
            for window_days in (7, 14, 30):
                window_start = source_cutoff - timedelta(days=window_days)
                expected_total = round(
                    sum(
                        float(record.rainfall_mm)
                        for record in referenced_records
                        if (
                            record.record_type == ClimateRecordType.OBSERVED
                            and record.source_kind == IngestionRun.SOURCE_KIND_LIVE
                            and record.quality_flag == ClimateRecordQualityFlag.ACCEPTED
                            and not record.fallback_flag
                            and record.valid_date is not None
                            and record.valid_date < prediction_date
                            and record.observed_timestamp is not None
                            and window_start <= record.observed_timestamp < source_cutoff
                        )
                    ),
                    2,
                )
                feature_key = f"chirps_observed_rainfall_total_{window_days}d"
                actual_total = values.get(feature_key)
                try:
                    actual_total_float = float(actual_total)
                except (TypeError, ValueError):
                    actual_total_float = None
                if actual_total_float is None or not math.isfinite(actual_total_float):
                    issues.append(
                        _issue(
                            severity="fail",
                            message="CHIRPS feature row is missing a finite recomputable rainfall total.",
                            context={
                                "feature_row_id": row.id,
                                "feature_key": feature_key,
                                "expected_total_mm": expected_total,
                                "actual_total_mm": actual_total,
                            },
                        )
                    )
                elif not math.isclose(
                    actual_total_float,
                    expected_total,
                    rel_tol=0.0,
                    abs_tol=CHIRPS_FEATURE_TOTAL_TOLERANCE_MM,
                ):
                    issues.append(
                        _issue(
                            severity="fail",
                            message="CHIRPS feature rainfall total does not match its referenced source records.",
                            context={
                                "feature_row_id": row.id,
                                "feature_key": feature_key,
                                "expected_total_mm": expected_total,
                                "actual_total_mm": actual_total_float,
                                "tolerance_mm": CHIRPS_FEATURE_TOTAL_TOLERANCE_MM,
                            },
                        )
                    )
            feature_rows_with_recomputed_totals += 1

    if records and referenced_chirps == 0:
        issues.append(
            _issue(
                severity="fail",
                message="Persisted lead-time feature rows contain no CHIRPS source references.",
                context={"feature_rows_scanned": len(rows)},
            )
        )

    status = "fail" if issues else "pass"
    return _check(
        "chirps_feature_temporal_cutoffs",
        status,
        evidence={
            "feature_dataset_schema_version": LEAD_TIME_FEATURE_SCHEMA_VERSION,
            "feature_rows_scanned": len(rows),
            "chirps_source_references_scanned": referenced_chirps,
            "feature_rows_required": True,
            "feature_rows_with_recomputed_totals": feature_rows_with_recomputed_totals,
            "ward_reference_mismatch_count": ward_reference_mismatch_count,
            "duplicate_reference_count": duplicate_reference_count,
            "feature_total_tolerance_mm": CHIRPS_FEATURE_TOTAL_TOLERANCE_MM,
        },
        issues=issues,
    )


def _feature_variant_pinning_check(records: list[ClimateRecord]) -> dict:
    source_records = {record.source_ref: record for record in records}
    datasets = list(
        FeatureDataset.objects.filter(
            schema_version=LEAD_TIME_FEATURE_SCHEMA_VERSION,
        ).prefetch_related("rows")
    )
    issues: list[dict] = []
    dataset_evidence: list[dict] = []
    datasets_with_chirps_refs = 0
    feature_rows_scanned = 0

    for dataset in datasets:
        rows = list(dataset.rows.all())
        feature_rows_scanned += len(rows)
        metadata = dataset.lineage_metadata if isinstance(dataset.lineage_metadata, dict) else {}
        policy = metadata.get("chirps_historical_feature_policy")
        policy = policy if isinstance(policy, dict) else {}
        pinned_variant = policy.get("daily_variant") or metadata.get("chirps_daily_variant")
        pinned_variant = str(pinned_variant).strip().lower() if pinned_variant else None
        row_refs: set[str] = set()
        observed_variants: set[str] = set()

        if pinned_variant not in CHIRPS_DAILY_VARIANTS:
            issues.append(
                _issue(
                    severity="fail",
                    message="CHIRPS feature dataset does not pin one supported daily variant.",
                    context={"dataset_id": dataset.id, "dataset_ref": dataset.dataset_ref},
                )
            )

        for row in rows:
            values = row.feature_values if isinstance(row.feature_values, dict) else {}
            rainfall_lineage = ((values.get("source_lineage") or {}).get("rainfall") or {})
            refs = rainfall_lineage.get("chirps_source_refs") or []
            if not isinstance(refs, list):
                refs = []
            row_refs_for_row = {str(ref) for ref in refs if ref}
            row_refs.update(row_refs_for_row)
            row_variant = values.get("chirps_daily_variant") or rainfall_lineage.get("chirps_daily_variant")
            if row_refs_for_row and row_variant:
                row_variant = str(row_variant).strip().lower()
                if row_variant in CHIRPS_DAILY_VARIANTS:
                    observed_variants.add(row_variant)
                else:
                    issues.append(
                        _issue(
                            severity="fail",
                            message="CHIRPS feature row declares an unsupported daily variant.",
                            context={"dataset_id": dataset.id, "feature_row_id": row.id, "variant": row_variant},
                        )
                    )
            for source_ref in refs:
                record = source_records.get(source_ref)
                if record is None:
                    continue
                lineage = record.lineage_metadata if isinstance(record.lineage_metadata, dict) else {}
                record_variant = lineage.get("daily_variant")
                if record_variant in CHIRPS_DAILY_VARIANTS:
                    observed_variants.add(record_variant)

        if row_refs:
            datasets_with_chirps_refs += 1
            if pinned_variant not in CHIRPS_DAILY_VARIANTS:
                issues.append(
                    _issue(
                        severity="fail",
                        message="CHIRPS-backed feature dataset has source rows but no valid pinned variant.",
                        context={"dataset_id": dataset.id, "dataset_ref": dataset.dataset_ref},
                    )
                )
            if len(observed_variants) > 1:
                issues.append(
                    _issue(
                        severity="fail",
                        message="CHIRPS feature dataset mixes daily variants.",
                        context={
                            "dataset_id": dataset.id,
                            "dataset_ref": dataset.dataset_ref,
                            "variants": sorted(observed_variants),
                        },
                    )
                )
            if observed_variants and observed_variants != {pinned_variant}:
                issues.append(
                    _issue(
                        severity="fail",
                        message="CHIRPS feature row variant does not match the dataset pin.",
                        context={
                            "dataset_id": dataset.id,
                            "dataset_ref": dataset.dataset_ref,
                            "pinned_variant": pinned_variant,
                            "observed_variants": sorted(observed_variants),
                        },
                    )
                )

        dataset_evidence.append(
            {
                "dataset_id": dataset.id,
                "dataset_ref": dataset.dataset_ref,
                "row_count": len(rows),
                "chirps_source_ref_count": len(row_refs),
                "pinned_variant": pinned_variant,
                "observed_variants": sorted(observed_variants),
            }
        )

    if records and datasets_with_chirps_refs == 0:
        issues.append(
            _issue(
                severity="fail",
                message="No persisted CHIRPS-backed feature dataset exists.",
                context={"feature_dataset_count": len(datasets), "feature_rows_scanned": feature_rows_scanned},
            )
        )

    return _check(
        "chirps_feature_variant_pinning",
        "fail" if issues else "pass",
        evidence={
            "feature_dataset_schema_version": LEAD_TIME_FEATURE_SCHEMA_VERSION,
            "feature_dataset_count": len(datasets),
            "feature_rows_scanned": feature_rows_scanned,
            "datasets_with_chirps_refs": datasets_with_chirps_refs,
            "datasets": dataset_evidence,
            "allowed_variants": sorted(CHIRPS_DAILY_VARIANTS),
        },
        issues=issues,
    )


def build_chirps_ingestion_audit() -> dict:
    records = list(
        ClimateRecord.objects.filter(source_provider=CHIRPS_PROVIDER)
        .select_related("ward", "ingestion_run")
        .order_by("valid_date", "ward_id", "id")
    )
    active_wards = list(Ward.objects.filter(is_active=True, county__iexact="Migori").order_by("id"))
    runs = list(
        IngestionRun.objects.filter(
            run_type=IngestionRun.RUN_TYPE_RAINFALL,
            source_name=CHIRPS_PROVIDER,
        ).order_by("id")
    )

    genuine_issues = [
        _issue(
            severity="fail",
            message="No genuine CHIRPS observed LIVE record exists.",
        )
    ] if not any(
        record.record_type == ClimateRecordType.OBSERVED
        and record.source_kind == IngestionRun.SOURCE_KIND_LIVE
        and not record.fallback_flag
        for record in records
    ) else []

    provenance_issues: list[dict] = []
    for record in records:
        lineage = record.lineage_metadata if isinstance(record.lineage_metadata, dict) else {}
        missing = [
            field
            for field in CHIRPS_REQUIRED_LINEAGE_FIELDS
            if field not in lineage or lineage.get(field) in ("", [])
        ]
        hashes = lineage.get("hashes") if isinstance(lineage.get("hashes"), dict) else {}
        if not lineage.get("extracted_window_sha256") and not hashes.get("extracted_window_sha256"):
            missing.append("hashes.extracted_window_sha256")
        if not lineage.get("full_asset_sha256") and not hashes.get("full_asset_sha256"):
            # Remote COG range reads legitimately have no full-file hash, but
            # must retain ETag/Last-Modified or content length as provenance.
            if not any(lineage.get(field) for field in ("etag", "last_modified", "content_length")):
                missing.append("asset_hash_or_http_validator")
        if lineage.get("provider") != CHIRPS_PROVIDER or lineage.get("chirps_version") != CHIRPS_VERSION:
            missing.append("provider_or_version")
        if lineage.get("product_status") != CHIRPS_PRODUCT_STATUS_FINAL:
            missing.append("product_status_final")
        variant = lineage.get("daily_variant")
        if variant not in CHIRPS_DAILY_VARIANTS:
            missing.append("daily_variant")
        elif record.source_mode != f"{CHIRPS_PRODUCT_STATUS_FINAL}-{variant}":
            missing.append("source_mode_variant")
        source_date = _parse_date(lineage.get("source_date"))
        if source_date is None or record.valid_date != source_date:
            missing.append("source_date_valid_date")
        if record.source_kind != IngestionRun.SOURCE_KIND_LIVE:
            missing.append("source_kind_live")
        if lineage.get("processing_code_version") != CHIRPS_PROCESSING_CODE_VERSION:
            missing.append("processing_code_version")
        if not record.identity_key or lineage.get("identity_key") != record.identity_key:
            missing.append("identity_key")
        if missing:
            provenance_issues.append(
                _issue(
                    severity="fail",
                    message="CHIRPS record is missing required lineage metadata.",
                    record=record,
                    context={"missing_fields": sorted(set(missing))},
                )
            )

    duplicate_identity_groups = list(
        ClimateRecord.objects.filter(source_provider=CHIRPS_PROVIDER)
        .exclude(identity_key__isnull=True)
        .values("identity_key")
        .annotate(record_count=Count("id"))
        .filter(record_count__gt=1)
    )
    duplicate_ward_date_groups = list(
        ClimateRecord.objects.filter(source_provider=CHIRPS_PROVIDER)
        .values("ward_id", "valid_date")
        .annotate(record_count=Count("id"))
        .filter(record_count__gt=1)
    )
    duplicate_issues = [
        _issue(
            severity="fail",
            message="Duplicate CHIRPS stable identity exists.",
            context=item,
        )
        for item in duplicate_identity_groups
    ] + [
        _issue(
            severity="fail",
            message="Duplicate CHIRPS ward/date records exist.",
            context=item,
        )
        for item in duplicate_ward_date_groups
    ]

    canonical_issues: list[dict] = []
    try:
        load_active_migori_ward_polygons()
    except Exception as exc:
        canonical_issues.append(
            _issue(
                severity="fail",
                message="Active Migori wards do not all have canonical valid polygons.",
                context={"error": str(exc)},
            )
        )
    active_by_id = {ward.id: ward for ward in active_wards}
    for record in records:
        lineage = record.lineage_metadata if isinstance(record.lineage_metadata, dict) else {}
        ward = active_by_id.get(record.ward_id)
        if ward is None or ward.county.casefold() != "migori":
            canonical_issues.append(
                _issue(
                    severity="fail",
                    message="CHIRPS record does not link to an active canonical Migori ward.",
                    record=record,
                )
            )
        elif lineage.get("ward_public_id") != str(ward.public_id):
            canonical_issues.append(
                _issue(
                    severity="fail",
                    message="CHIRPS lineage ward_public_id does not match the canonical ward.",
                    record=record,
                    context={"lineage_ward_public_id": lineage.get("ward_public_id")},
                )
            )

    invalid_values = [
        _issue(
            severity="fail",
            message="CHIRPS rainfall must be finite and non-negative.",
            record=record,
        )
        for record in records
        if not math.isfinite(float(record.rainfall_mm)) or float(record.rainfall_mm) < 0
    ]
    fallback_issues = [
        _issue(
            severity="fail",
            message="CHIRPS records must never be marked as static fallback.",
            record=record,
        )
        for record in records
        if record.fallback_flag or record.record_type != ClimateRecordType.OBSERVED
    ]
    coverage_issues = []
    for record in records:
        lineage = record.lineage_metadata if isinstance(record.lineage_metadata, dict) else {}
        coverage = lineage.get("ward_coverage_fraction")
        try:
            valid_coverage = float(coverage)
        except (TypeError, ValueError):
            valid_coverage = -1
        if (
            valid_coverage < chirps_min_coverage_fraction()
            or valid_coverage > 1 + CHIRPS_COVERAGE_NUMERICAL_EPSILON
        ):
            coverage_issues.append(
                _issue(
                    severity="fail",
                    message="CHIRPS ward coverage fraction is below the configured threshold or invalid.",
                    record=record,
                    context={"ward_coverage_fraction": coverage},
                )
            )

    checks = [
        _check(
            "genuine_chirps_observed_record_exists",
            "fail" if genuine_issues else "pass",
            evidence={
                "chirps_record_count": len(records),
                "genuine_observed_live_record_count": sum(
                    1
                    for record in records
                    if record.record_type == ClimateRecordType.OBSERVED
                    and record.source_kind == IngestionRun.SOURCE_KIND_LIVE
                    and not record.fallback_flag
                ),
            },
            issues=genuine_issues,
        ),
        _check(
            "source_version_status_variant_and_lineage_complete",
            "fail" if provenance_issues else "pass" if records else "warning",
            evidence={"records_scanned": len(records), "required_lineage_fields": list(CHIRPS_REQUIRED_LINEAGE_FIELDS)},
            issues=provenance_issues,
        ),
        _quality_flag_check(records),
        _canonical_source_identity_check(records),
        _check(
            "durable_identity_and_ward_date_uniqueness",
            "fail" if duplicate_issues else "pass" if records else "warning",
            evidence={
                "duplicate_identity_groups": len(duplicate_identity_groups),
                "duplicate_ward_date_groups": len(duplicate_ward_date_groups),
            },
            issues=duplicate_issues,
        ),
        _check(
            "canonical_active_migori_ward_identity",
            "fail" if canonical_issues else "pass" if records and active_wards else "warning",
            evidence={"active_migori_ward_count": len(active_wards), "records_scanned": len(records)},
            issues=canonical_issues,
        ),
        _canonical_run_ward_reference_check(runs, active_wards),
        _accepted_run_observation_check(records, runs, active_wards),
        _check(
            "finite_non_negative_rainfall",
            "fail" if invalid_values else "pass" if records else "warning",
            evidence={"records_scanned": len(records), "invalid_value_count": len(invalid_values)},
            issues=invalid_values,
        ),
        _check(
            "chirps_records_have_no_static_fallback",
            "fail" if fallback_issues else "pass" if records else "warning",
            evidence={"records_scanned": len(records), "fallback_or_non_observed_count": len(fallback_issues)},
            issues=fallback_issues,
        ),
        _check(
            "ward_coverage_fraction_meets_threshold",
            "fail" if coverage_issues else "pass" if records else "warning",
            evidence={
                "configured_minimum": chirps_min_coverage_fraction(),
                "records_scanned": len(records),
            },
            issues=coverage_issues,
        ),
        _completeness_check(records, active_wards, runs),
        _feature_temporal_cutoff_check(records),
        _feature_variant_pinning_check(records),
    ]
    failures = sum(1 for check in checks if check["status"] == "fail")
    warnings = sum(1 for check in checks if check["status"] == "warning")
    return {
        "audit_name": "chirps_v3_historical_ingestion",
        "schema_version": CHIRPS_AUDIT_SCHEMA_VERSION,
        "overall_status": "fail" if failures else "warning" if warnings else "pass",
        "provider": CHIRPS_PROVIDER,
        "chirps_version": CHIRPS_VERSION,
        "records_scanned": len(records),
        "runs_scanned": len(runs),
        "checks": checks,
        "strict_command": "python manage.py audit_chirps_ingestion --strict",
    }
