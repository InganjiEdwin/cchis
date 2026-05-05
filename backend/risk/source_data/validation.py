from __future__ import annotations

import csv
import hashlib
import json
import random
import re
from io import StringIO
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import transaction

from risk.models import (
    SourceDataUploadArtifact,
    SourceDataUploadBatch,
    SourceDataValidationIssue,
)
from risk.population_exposure_ingestion import inspect_population_exposure_csv
from risk.source_data.phase0 import (
    INGESTION_FAMILY_FACILITY_READINESS,
    INGESTION_FAMILY_POPULATION_EXPOSURE,
    INGESTION_FAMILY_SURVEILLANCE,
)
from risk.source_data.registry import SourceDataFeedDefinition, source_data_feed_definition
from risk.source_data.uploads import latest_upload_artifact
from risk.surveillance_ingestion import inspect_surveillance_csv


MAX_VALIDATION_SAMPLE_ROWS = 50
MAX_REJECTED_ROW_DIAGNOSTICS = 100
PII_HEADER_NAMES = {
    "address",
    "date_of_birth",
    "dob",
    "email",
    "first_name",
    "full_name",
    "id_number",
    "last_name",
    "name",
    "national_id",
    "patient_name",
    "phone",
    "phone_number",
}
PHONE_RE = re.compile(r"(?:\+?254|0)?7\d{8}\b")
NATIONAL_ID_RE = re.compile(r"\b\d{7,9}\b")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
FORMULA_PREFIXES = ("=", "+", "-", "@")
AGGREGATE_NUMERIC_COLUMNS = {
    "beds_available",
    "confirmed_cases",
    "diarrheal_count",
    "distance_bucket_meters",
    "flood_exposure_index",
    "household_count_proxy",
    "iv_fluids_available",
    "lat",
    "latitude",
    "lon",
    "longitude",
    "population_total",
    "population_under_five",
    "staff_on_duty",
    "suspected_cases",
    "zinc_available",
}


def normalize_header(value: str | None) -> str:
    return "_".join((value or "").strip().lower().replace("-", "_").split())


def _issue(
    *,
    severity: str,
    code: str,
    message: str,
    row_number: int | None = None,
    column_name: str = "",
    safe_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "severity": severity,
        "code": code,
        "message": message,
        "row_number": row_number,
        "column_name": column_name,
        "safe_context": safe_context or {},
    }


def _read_csv_headers_and_rows(path: Path) -> tuple[list[str], list[dict[str, str]], list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            if reader.fieldnames is None:
                return [], [], [
                    _issue(
                        severity=SourceDataValidationIssue.SEVERITY_ERROR,
                        code="missing_headers",
                        message="CSV file must include a header row.",
                    )
                ]
            headers = [normalize_header(header) for header in reader.fieldnames]
            rows = [
                {normalize_header(key): value for key, value in row.items() if key is not None}
                for row in reader
            ]
            return headers, rows, issues
    except UnicodeDecodeError:
        return [], [], [
            _issue(
                severity=SourceDataValidationIssue.SEVERITY_ERROR,
                code="invalid_encoding",
                message="CSV file must be UTF-8 or UTF-8 with BOM.",
            )
        ]
    except csv.Error as error:
        return [], [], [
            _issue(
                severity=SourceDataValidationIssue.SEVERITY_ERROR,
                code="invalid_csv",
                message=f"CSV could not be parsed safely: {error}",
            )
        ]


def _sample_rows(rows: list[dict[str, str]]) -> list[tuple[int, dict[str, str]]]:
    indexed_rows = list(enumerate(rows, start=2))
    first_rows = indexed_rows[:25]
    if len(indexed_rows) <= 25:
        return first_rows
    random_source = random.Random(len(indexed_rows))
    remaining = indexed_rows[25:]
    random_rows = random_source.sample(remaining, min(25, len(remaining)))
    combined = {row_number: row for row_number, row in [*first_rows, *random_rows]}
    return sorted(combined.items())


def _file_level_issues(artifact: SourceDataUploadArtifact, headers: list[str], rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    filename = artifact.original_filename.lower()
    if not filename.endswith(".csv"):
        issues.append(
            _issue(
                severity=SourceDataValidationIssue.SEVERITY_ERROR,
                code="unsupported_file_extension",
                message="Only CSV uploads are accepted for source-data ops.",
                safe_context={"filename": artifact.original_filename},
            )
        )
    if artifact.content_type and artifact.content_type not in {"text/csv", "application/csv", "application/vnd.ms-excel"}:
        issues.append(
            _issue(
                severity=SourceDataValidationIssue.SEVERITY_WARNING,
                code="unexpected_content_type",
                message="Uploaded file content type is unusual for CSV; validation will rely on parsed CSV content.",
                safe_context={"content_type": artifact.content_type},
            )
        )
    if artifact.size_bytes <= 0:
        issues.append(
            _issue(
                severity=SourceDataValidationIssue.SEVERITY_ERROR,
                code="empty_file",
                message="CSV file is empty.",
            )
        )
    if not headers:
        issues.append(
            _issue(
                severity=SourceDataValidationIssue.SEVERITY_ERROR,
                code="missing_headers",
                message="CSV file must include headers.",
            )
        )
    duplicate_headers = sorted({header for header in headers if headers.count(header) > 1})
    for header in duplicate_headers:
        issues.append(
            _issue(
                severity=SourceDataValidationIssue.SEVERITY_ERROR,
                code="duplicate_header",
                column_name=header,
                message=f"CSV header '{header}' appears more than once.",
            )
        )
    if not rows:
        issues.append(
            _issue(
                severity=SourceDataValidationIssue.SEVERITY_ERROR,
                code="no_data_rows",
                message="CSV file must include at least one data row.",
            )
        )
    max_rows = getattr(settings, "SOURCE_DATA_MAX_UPLOAD_ROWS", 50000)
    if len(rows) > max_rows:
        issues.append(
            _issue(
                severity=SourceDataValidationIssue.SEVERITY_ERROR,
                code="row_limit_exceeded",
                message=f"CSV has {len(rows)} data rows, which exceeds the configured limit of {max_rows}.",
                safe_context={"row_count": len(rows), "row_limit": max_rows},
            )
        )
    return issues


def _pii_and_formula_issues(headers: list[str], rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for header in headers:
        if header in PII_HEADER_NAMES:
            issues.append(
                _issue(
                    severity=SourceDataValidationIssue.SEVERITY_ERROR,
                    code="pii_header_detected",
                    column_name=header,
                    message=f"Column '{header}' looks like direct personal information and is not allowed.",
                )
            )

    for row_number, row in _sample_rows(rows):
        for column, value in row.items():
            text = str(value or "").strip()
            if not text:
                continue
            if text.startswith(FORMULA_PREFIXES):
                issues.append(
                    _issue(
                        severity=SourceDataValidationIssue.SEVERITY_ERROR,
                        code="formula_injection_value",
                        row_number=row_number,
                        column_name=column,
                        message="Cell value starts with a spreadsheet formula prefix.",
                    )
                )
            if EMAIL_RE.search(text):
                issues.append(
                    _issue(
                        severity=SourceDataValidationIssue.SEVERITY_ERROR,
                        code="pii_email_value_detected",
                        row_number=row_number,
                        column_name=column,
                        message="Sampled value looks like an email address.",
                    )
                )
            if PHONE_RE.search(text):
                issues.append(
                    _issue(
                        severity=SourceDataValidationIssue.SEVERITY_ERROR,
                        code="pii_phone_value_detected",
                        row_number=row_number,
                        column_name=column,
                        message="Sampled value looks like a phone number.",
                    )
                )
            if (
                column not in {"ward_code", "facility_code", "source_ref"}
                and column not in AGGREGATE_NUMERIC_COLUMNS
                and NATIONAL_ID_RE.fullmatch(text)
            ):
                issues.append(
                    _issue(
                        severity=SourceDataValidationIssue.SEVERITY_ERROR,
                        code="pii_identifier_value_detected",
                        row_number=row_number,
                        column_name=column,
                        message="Sampled value looks like a national or patient identifier.",
                    )
                )
    return issues


def _domain_inspection(
    *,
    batch: SourceDataUploadBatch,
    definition: SourceDataFeedDefinition,
    artifact_path: Path,
    headers: list[str],
    rows: list[dict[str, str]],
) -> dict[str, Any]:
    if definition.ingestion_family == INGESTION_FAMILY_SURVEILLANCE:
        return inspect_surveillance_csv(
            artifact_path,
            source_type=definition.source_type,
            source_name=batch.source_name,
        )
    if definition.ingestion_family == INGESTION_FAMILY_POPULATION_EXPOSURE:
        return inspect_population_exposure_csv(artifact_path, source_type=definition.source_type)
    if definition.ingestion_family == INGESTION_FAMILY_FACILITY_READINESS:
        unknown_columns = sorted(set(headers) - set(definition.accepted_columns))
        rejected_rows = []
        accepted_count = 0
        for row_number, row in enumerate(rows, start=2):
            missing_groups = [
                list(group)
                for group in definition.required_any_columns
                if not any(str(row.get(column, "")).strip() for column in group)
            ]
            if missing_groups:
                rejected_rows.append(
                    {
                        "row_number": row_number,
                        "reason": "missing_required_column_group",
                        "required_any_columns": missing_groups,
                    }
                )
            else:
                accepted_count += 1
        return {
            "adapter_key": definition.adapter_key,
            "adapter_notes": definition.adapter_notes,
            "scheduled_supported": definition.scheduled_supported,
            "headers": headers,
            "unknown_columns": unknown_columns,
            "records_seen": len(rows),
            "records_loaded": accepted_count,
            "records_rejected": len(rows) - accepted_count,
            "sample_rows": rows[:5],
            "rejected_rows": rejected_rows[:MAX_REJECTED_ROW_DIAGNOSTICS],
        }
    raise ValueError(f"Unsupported source-data ingestion family: {definition.ingestion_family}")


def _issues_from_domain_inspection(inspection: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for column in inspection.get("unknown_columns") or []:
        issues.append(
            _issue(
                severity=SourceDataValidationIssue.SEVERITY_WARNING,
                code="unknown_column",
                column_name=str(column),
                message=f"Column '{column}' is not part of the source-data contract and will be ignored.",
            )
        )
    for rejected in inspection.get("rejected_rows") or []:
        issues.append(
            _issue(
                severity=SourceDataValidationIssue.SEVERITY_ERROR,
                code=str(rejected.get("reason") or "domain_row_rejected"),
                row_number=rejected.get("row_number"),
                message="Domain validation rejected this row.",
                safe_context={
                    key: value
                    for key, value in rejected.items()
                    if key in {"required_any_columns", "error"}
                },
            )
        )
    return issues


def _hash_file(path: Path) -> str:
    sha256 = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


@transaction.atomic
def validate_source_data_upload_batch(batch: SourceDataUploadBatch) -> SourceDataUploadBatch:
    batch.status = SourceDataUploadBatch.STATUS_VALIDATING
    batch.validation_status = SourceDataUploadBatch.VALIDATION_RUNNING
    batch.save(update_fields=["status", "validation_status", "updated_at"])
    batch.validation_issues.all().delete()

    artifact = latest_upload_artifact(batch)
    artifact_path = Path(artifact.storage_path)
    issues: list[dict[str, Any]] = []
    inspection: dict[str, Any] = {}
    headers: list[str] = []
    rows: list[dict[str, str]] = []

    if not artifact_path.exists():
        issues.append(
            _issue(
                severity=SourceDataValidationIssue.SEVERITY_ERROR,
                code="artifact_missing",
                message="Stored upload artifact is missing from shared durable storage.",
            )
        )
    elif _hash_file(artifact_path) != artifact.sha256:
        issues.append(
            _issue(
                severity=SourceDataValidationIssue.SEVERITY_ERROR,
                code="artifact_hash_mismatch",
                message="Stored upload artifact hash does not match the uploaded file hash.",
            )
        )
    else:
        headers, rows, parse_issues = _read_csv_headers_and_rows(artifact_path)
        issues.extend(parse_issues)
        issues.extend(_file_level_issues(artifact, headers, rows))
        issues.extend(_pii_and_formula_issues(headers, rows))
        if not any(issue["severity"] == SourceDataValidationIssue.SEVERITY_ERROR for issue in issues):
            definition = source_data_feed_definition(batch.feed_key)
            inspection = _domain_inspection(
                batch=batch,
                definition=definition,
                artifact_path=artifact_path,
                headers=headers,
                rows=rows,
            )
            issues.extend(_issues_from_domain_inspection(inspection))

    duplicate_metadata = batch.metadata or {}
    if duplicate_metadata.get("duplicate_file_sha256"):
        issues.append(
            _issue(
                severity=SourceDataValidationIssue.SEVERITY_WARNING,
                code="duplicate_file_hash",
                message="This upload has the same file hash as a previous upload.",
                safe_context={"duplicate_upload_public_id": str(batch.duplicate_of.public_id)},
            )
        )
    if duplicate_metadata.get("duplicate_metadata_upload_public_id"):
        issues.append(
            _issue(
                severity=SourceDataValidationIssue.SEVERITY_WARNING,
                code="duplicate_upload_metadata",
                message="This upload has the same feed and source metadata as a previous upload.",
                safe_context={
                    "duplicate_upload_public_id": duplicate_metadata["duplicate_metadata_upload_public_id"]
                },
            )
        )

    issue_records = [
        SourceDataValidationIssue(
            upload_batch=batch,
            severity=issue["severity"],
            code=issue["code"],
            row_number=issue.get("row_number"),
            column_name=issue.get("column_name") or "",
            message=issue["message"],
            safe_context=issue.get("safe_context") or {},
        )
        for issue in issues
    ]
    SourceDataValidationIssue.objects.bulk_create(issue_records)

    error_count = sum(1 for issue in issues if issue["severity"] == SourceDataValidationIssue.SEVERITY_ERROR)
    warning_count = sum(1 for issue in issues if issue["severity"] == SourceDataValidationIssue.SEVERITY_WARNING)
    row_count = int(inspection.get("records_seen") or len(rows))
    accepted_count = int(inspection.get("records_loaded") or 0)
    rejected_count = int(inspection.get("records_rejected") or max(row_count - accepted_count, 0))
    batch.row_count = row_count
    batch.accepted_count = accepted_count
    batch.rejected_count = rejected_count
    batch.warning_count = warning_count
    batch.validation_status = (
        SourceDataUploadBatch.VALIDATION_FAILED
        if error_count
        else SourceDataUploadBatch.VALIDATION_PASSED
    )
    batch.status = (
        SourceDataUploadBatch.STATUS_VALIDATION_FAILED
        if error_count
        else SourceDataUploadBatch.STATUS_READY_FOR_CONFIRMATION
    )
    batch.metadata = {
        **(batch.metadata or {}),
        "validation_summary": {
            "validated_artifact_id": artifact.id,
            "validated_artifact_sha256": artifact.sha256,
            "error_count": error_count,
            "warning_count": warning_count,
            "row_count": row_count,
            "accepted_count": accepted_count,
            "rejected_count": rejected_count,
            "unknown_columns": inspection.get("unknown_columns") or [],
            "sample_rows": inspection.get("sample_rows") or [],
            "rejected_row_diagnostics": (inspection.get("rejected_rows") or [])[:MAX_REJECTED_ROW_DIAGNOSTICS],
        },
    }
    batch.save(
        update_fields=[
            "status",
            "validation_status",
            "row_count",
            "accepted_count",
            "rejected_count",
            "warning_count",
            "metadata",
            "updated_at",
        ]
    )
    return batch


def build_source_data_upload_errors_csv(batch: SourceDataUploadBatch) -> dict[str, Any]:
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=["row_number", "severity", "code", "column_name", "message", "safe_context_json"],
    )
    writer.writeheader()
    issues = batch.validation_issues.order_by("severity", "row_number", "created_at")
    for issue in issues:
        writer.writerow(
            {
                "row_number": issue.row_number or "",
                "severity": issue.severity,
                "code": issue.code,
                "column_name": issue.column_name,
                "message": issue.message,
                "safe_context_json": json.dumps(issue.safe_context or {}, sort_keys=True),
            }
        )
    payload = output.getvalue()
    return {
        "filename": f"source_data_upload_{batch.public_id}_errors.csv",
        "content_type": "text/csv",
        "payload": payload,
        "payload_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "row_count": batch.validation_issues.count(),
    }
