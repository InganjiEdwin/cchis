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
from risk.facility_readiness_ingestion import inspect_facility_readiness_snapshot_csv
from risk.population_exposure_ingestion import inspect_population_exposure_csv
from risk.privacy_minimization import unsafe_pii_findings_in_text
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
MAX_FORMULA_INJECTION_ISSUES = 100
CSV_CONTENT_TYPES = {"text/csv", "application/csv", "application/vnd.ms-excel"}
SNIFF_SAMPLE_BYTES = 4096
PII_HEADER_NAMES = {
    "address",
    "caregiver_name",
    "child_name",
    "date_of_birth",
    "dob",
    "email",
    "first_name",
    "full_name",
    "gps",
    "household_head_name",
    "id_number",
    "last_name",
    "mother_name",
    "name",
    "national_id",
    "passport_number",
    "patient_name",
    "phone",
    "phone_number",
    "precise_location",
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
SOURCE_DATA_VALIDATION_ERROR_CATALOG_SCHEMA_VERSION = "source-data-validation-error-catalog-v1"
SOURCE_DATA_VALIDATION_ERROR_CATALOG: dict[str, dict[str, str]] = {
    "artifact_hash_mismatch": {
        "severity": "error",
        "operator_message": "Stored upload artifact hash does not match the uploaded file hash.",
        "remediation": "Create a new upload from the original CSV before validating again.",
    },
    "artifact_missing": {
        "severity": "error",
        "operator_message": "Stored upload artifact is missing from shared durable storage.",
        "remediation": "Create a fresh upload so validation can read the file.",
    },
    "binary_file_detected": {
        "severity": "error",
        "operator_message": "Upload content looks like a binary, archive, or office document instead of CSV.",
        "remediation": "Export the source as plain UTF-8 CSV and upload that file.",
    },
    "delayed_report": {
        "severity": "warning",
        "operator_message": "Facility readiness report is delayed for the expected cadence.",
        "remediation": "Review whether the delayed source should still be imported.",
    },
    "domain_row_rejected": {
        "severity": "error",
        "operator_message": "Domain validation rejected this row.",
        "remediation": "Compare the row with the source-data template and validate again after correction.",
    },
    "domain_row_warning": {
        "severity": "warning",
        "operator_message": "Domain validation recorded a warning for this row.",
        "remediation": "Review the warning before confirming import.",
    },
    "duplicate_file_hash": {
        "severity": "warning",
        "operator_message": "This upload has the same file hash as a previous upload.",
        "remediation": "Confirm intentional replay, or upload the corrected file.",
    },
    "duplicate_header": {
        "severity": "error",
        "operator_message": "A CSV header appears more than once.",
        "remediation": "Keep a single copy of each template column.",
    },
    "duplicate_snapshot": {
        "severity": "error",
        "operator_message": "A facility readiness snapshot already exists for this facility and reported_at timestamp.",
        "remediation": "Use a later reported_at timestamp or submit a documented replacement.",
    },
    "duplicate_snapshot_in_file": {
        "severity": "error",
        "operator_message": "The same facility readiness snapshot appears more than once in this file.",
        "remediation": "Remove duplicate facility rows before validating again.",
    },
    "duplicate_upload_metadata": {
        "severity": "warning",
        "operator_message": "This upload has the same feed and source metadata as a previous upload.",
        "remediation": "Update the source timestamp or mark the import as an intentional replay.",
    },
    "empty_file": {
        "severity": "error",
        "operator_message": "CSV file is empty.",
        "remediation": "Export the template with headers and at least one data row.",
    },
    "facility_name_mismatch": {
        "severity": "warning",
        "operator_message": "Facility code was found, but the facility name does not match the register.",
        "remediation": "Check the facility name against the county facility register.",
    },
    "facility_not_found_for_catchment_record": {
        "severity": "error",
        "operator_message": "Catchment row references a facility that is not in the facility register.",
        "remediation": "Correct the facility code or register the facility before import.",
    },
    "facility_not_found_for_facility_proxy_record": {
        "severity": "error",
        "operator_message": "Surveillance facility-proxy row references a facility that is not in the facility register.",
        "remediation": "Correct the facility code or map the row to a known ward.",
    },
    "facility_ward_mismatch": {
        "severity": "error",
        "operator_message": "Facility and ward codes point to different registered locations.",
        "remediation": "Correct either the facility code or ward code so they refer to the same facility catchment.",
    },
    "formula_injection_value": {
        "severity": "error",
        "operator_message": "Cell value starts with a spreadsheet formula prefix.",
        "remediation": "Save plain values only; remove formulas before upload.",
    },
    "future_reported_at": {
        "severity": "error",
        "operator_message": "Facility readiness reported_at is too far in the future.",
        "remediation": "Use the actual facility report timestamp, not a future collection date.",
    },
    "html_or_xml_file_detected": {
        "severity": "error",
        "operator_message": "Upload content looks like HTML or XML instead of CSV.",
        "remediation": "Export the source as a plain CSV file before upload.",
    },
    "invalid_boolean": {
        "severity": "error",
        "operator_message": "Readiness yes/no fields must use true or false values.",
        "remediation": "Use true or false for referral_available and service_disruption.",
    },
    "invalid_csv": {
        "severity": "error",
        "operator_message": "CSV could not be parsed safely.",
        "remediation": "Re-export the source as a valid CSV file.",
    },
    "invalid_encoding": {
        "severity": "error",
        "operator_message": "CSV file must be UTF-8 or UTF-8 with BOM.",
        "remediation": "Save or export the file as UTF-8 CSV.",
    },
    "invalid_nonnegative_integer": {
        "severity": "error",
        "operator_message": "Numeric readiness fields must be whole numbers greater than or equal to zero.",
        "remediation": "Replace blank, negative, or decimal stock values with valid whole numbers.",
    },
    "invalid_reported_at": {
        "severity": "error",
        "operator_message": "Readiness reported_at is missing or cannot be parsed.",
        "remediation": "Use an ISO timestamp such as 2026-05-05T08:00:00+03:00.",
    },
    "invalid_reporting_period": {
        "severity": "error",
        "operator_message": "Reporting period dates could not be parsed.",
        "remediation": "Use YYYY-MM-DD dates for reporting_period_start and reporting_period_end.",
    },
    "invalid_reporting_period_bounds": {
        "severity": "error",
        "operator_message": "Reporting period end is before the start date.",
        "remediation": "Set reporting_period_end on or after reporting_period_start.",
    },
    "invalid_source_kind": {
        "severity": "error",
        "operator_message": "Readiness source_kind is not one of the allowed values.",
        "remediation": "Use an allowed source_kind value from the readiness template.",
    },
    "missing_headers": {
        "severity": "error",
        "operator_message": "CSV file must include a header row.",
        "remediation": "Download the source-data template and keep the first row as headers.",
    },
    "missing_required_column_group": {
        "severity": "error",
        "operator_message": "CSV is missing a required group of columns for this feed.",
        "remediation": "Add at least one required identity/date/count column from the template.",
    },
    "missing_required_field": {
        "severity": "error",
        "operator_message": "Readiness row is missing required fields.",
        "remediation": "Fill facility_code, ward_code, reported_at, and required stock/status fields.",
    },
    "no_canonical_population_exposure_or_catchment_fields": {
        "severity": "error",
        "operator_message": "Population exposure row has no importable exposure or catchment values.",
        "remediation": "Add one of the accepted population, exposure, or catchment columns.",
    },
    "no_case_counts_or_outbreak_label": {
        "severity": "error",
        "operator_message": "Surveillance row has no case counts or outbreak label.",
        "remediation": "Add suspected/confirmed/diarrheal counts or an outbreak label.",
    },
    "no_data_rows": {
        "severity": "error",
        "operator_message": "CSV file must include at least one data row.",
        "remediation": "Keep the header row and add source-data rows before uploading.",
    },
    "pii_email_value_detected": {
        "severity": "error",
        "operator_message": "Sampled value looks like an email address.",
        "remediation": "Remove direct identifiers from source-data uploads.",
    },
    "pii_header_detected": {
        "severity": "error",
        "operator_message": "A column header looks like direct personal information.",
        "remediation": "Remove personal-information columns such as names, phone numbers, or IDs.",
    },
    "pii_identifier_value_detected": {
        "severity": "error",
        "operator_message": "Sampled value looks like a national or patient identifier.",
        "remediation": "Replace direct identifiers with approved aggregate, facility, ward, or source references.",
    },
    "pii_phone_value_detected": {
        "severity": "error",
        "operator_message": "Sampled value looks like a phone number.",
        "remediation": "Remove phone numbers from the CSV before upload.",
    },
    "row_limit_exceeded": {
        "severity": "error",
        "operator_message": "CSV has more rows than the configured upload limit.",
        "remediation": "Split the CSV into smaller source-data uploads.",
    },
    "service_disruption_reported": {
        "severity": "warning",
        "operator_message": "Facility reported a service disruption.",
        "remediation": "Review the warning before import; it will be kept as operational readiness context.",
    },
    "stale_report": {
        "severity": "warning",
        "operator_message": "Facility readiness report is older than the expected freshness window.",
        "remediation": "Confirm the old report should still be imported, or collect a newer facility update.",
    },
    "stockout_detected": {
        "severity": "warning",
        "operator_message": "Facility readiness row reports one or more stockouts.",
        "remediation": "Review stockout flags before import; they will affect readiness evidence.",
    },
    "unexpected_content_type": {
        "severity": "error",
        "operator_message": "Uploaded file content type is not allowed for CSV source-data intake.",
        "remediation": "Upload a CSV file with a CSV content type.",
    },
    "unsafe_text_value_detected": {
        "severity": "error",
        "operator_message": "Sampled free text appears to include direct identifiers or unsupported sensitive details.",
        "remediation": "Remove names, contacts, identifiers, exact household locations, and clinical notes from the CSV.",
    },
    "unknown_column": {
        "severity": "warning",
        "operator_message": "Column is not part of the source-data contract.",
        "remediation": "Remove the extra column or request a contract update.",
    },
    "unknown_facility_code": {
        "severity": "error",
        "operator_message": "Facility code is not in the facility register.",
        "remediation": "Correct the facility code or register the facility before import.",
    },
    "unknown_ward_code": {
        "severity": "error",
        "operator_message": "Ward code is not in the Migori ward register.",
        "remediation": "Correct the ward code before import.",
    },
    "unsupported_file_extension": {
        "severity": "error",
        "operator_message": "Only CSV uploads are accepted for source-data ops.",
        "remediation": "Export the workbook as .csv and upload the CSV file.",
    },
    "ward_not_found_for_population_record": {
        "severity": "error",
        "operator_message": "Population row references a ward that is not in the ward register.",
        "remediation": "Correct the ward code or ward name before import.",
    },
    "ward_not_found_for_surveillance_record": {
        "severity": "error",
        "operator_message": "Surveillance row references a ward that is not in the ward register.",
        "remediation": "Correct the ward code or ward name before import.",
    },
}


def source_data_validation_error_catalog() -> dict[str, Any]:
    return {
        "schema_version": SOURCE_DATA_VALIDATION_ERROR_CATALOG_SCHEMA_VERSION,
        "codes": [
            {"code": code, **details}
            for code, details in sorted(SOURCE_DATA_VALIDATION_ERROR_CATALOG.items())
        ],
    }


def _documented_issue_message(code: str, default: str) -> str:
    return SOURCE_DATA_VALIDATION_ERROR_CATALOG.get(code, {}).get("operator_message", default)


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


def _sniffed_content_issues(artifact_path: Path) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    with artifact_path.open("rb") as input_file:
        sample = input_file.read(SNIFF_SAMPLE_BYTES)
    stripped = sample.lstrip().lower()

    if sample.startswith(b"PK\x03\x04") or sample.startswith(b"\xd0\xcf\x11\xe0") or b"\x00" in sample:
        issues.append(
            _issue(
                severity=SourceDataValidationIssue.SEVERITY_ERROR,
                code="binary_file_detected",
                message="Upload content looks like a binary, archive, or office document instead of CSV.",
            )
        )
    elif stripped.startswith((b"<html", b"<!doctype html", b"<?xml", b"<xml")):
        issues.append(
            _issue(
                severity=SourceDataValidationIssue.SEVERITY_ERROR,
                code="html_or_xml_file_detected",
                message="Upload content looks like HTML or XML instead of CSV.",
            )
        )
    return issues


def _file_level_issues(
    artifact: SourceDataUploadArtifact,
    artifact_path: Path,
    headers: list[str],
    rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
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
    if artifact.content_type and artifact.content_type not in CSV_CONTENT_TYPES:
        issues.append(
            _issue(
                severity=SourceDataValidationIssue.SEVERITY_ERROR,
                code="unexpected_content_type",
                message="Uploaded file content type is not allowed for CSV source-data intake.",
                safe_context={"content_type": artifact.content_type},
            )
        )
    issues.extend(_sniffed_content_issues(artifact_path))
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


def _formula_injection_issues(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for row_number, row in enumerate(rows, start=2):
        for column, value in row.items():
            text = str(value or "").strip()
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
                if len(issues) >= MAX_FORMULA_INJECTION_ISSUES:
                    return issues
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

    issues.extend(_formula_injection_issues(rows))

    for row_number, row in _sample_rows(rows):
        for column, value in row.items():
            text = str(value or "").strip()
            if not text:
                continue
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
            unsafe_text_findings = tuple(
                finding
                for finding in unsafe_pii_findings_in_text(
                    text,
                    location=f"row_{row_number}.{column}",
                )
                if "phone numbers" not in finding.reason
                and "email addresses" not in finding.reason
            )
            if unsafe_text_findings:
                issues.append(
                    _issue(
                        severity=SourceDataValidationIssue.SEVERITY_ERROR,
                        code="unsafe_text_value_detected",
                        row_number=row_number,
                        column_name=column,
                        message="Sampled free text appears to include direct identifiers or unsupported sensitive details.",
                        safe_context={
                            "finding_count": len(unsafe_text_findings),
                            "reasons": sorted({finding.reason for finding in unsafe_text_findings}),
                        },
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
        return inspect_facility_readiness_snapshot_csv(artifact_path)
    raise ValueError(f"Unsupported source-data ingestion family: {definition.ingestion_family}")


def _issues_from_domain_inspection(inspection: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for column in inspection.get("unknown_columns") or []:
        unknown_column_severity = (
            SourceDataValidationIssue.SEVERITY_ERROR
            if inspection.get("unknown_columns_are_errors")
            else SourceDataValidationIssue.SEVERITY_WARNING
        )
        issues.append(
            _issue(
                severity=unknown_column_severity,
                code="unknown_column",
                column_name=str(column),
                message=(
                    f"Column '{column}' is not part of the source-data contract; remove it before import."
                    if unknown_column_severity == SourceDataValidationIssue.SEVERITY_ERROR
                    else f"Column '{column}' is not part of the source-data contract and will be ignored."
                ),
                safe_context={"remediation": SOURCE_DATA_VALIDATION_ERROR_CATALOG["unknown_column"]["remediation"]},
            )
        )
    for rejected in inspection.get("rejected_rows") or []:
        code = str(rejected.get("reason") or "domain_row_rejected")
        issues.append(
            _issue(
                severity=SourceDataValidationIssue.SEVERITY_ERROR,
                code=code,
                row_number=rejected.get("row_number"),
                message=_documented_issue_message(code, "Domain validation rejected this row."),
                safe_context={
                    key: value
                    for key, value in rejected.items()
                    if key
                    in {
                        "allowed_values",
                        "columns",
                        "error",
                        "expected_ward_code",
                        "facility_code",
                        "missing_columns",
                        "required_any_columns",
                        "stockout_flags",
                        "ward_code",
                    }
                }
                | {
                    "remediation": SOURCE_DATA_VALIDATION_ERROR_CATALOG.get(code, {}).get(
                        "remediation",
                        "Compare the row with the source-data template and validate again after correction.",
                    )
                },
            )
        )
    for warning in inspection.get("warning_rows") or []:
        code = str(warning.get("reason") or "domain_row_warning")
        issues.append(
            _issue(
                severity=SourceDataValidationIssue.SEVERITY_WARNING,
                code=code,
                row_number=warning.get("row_number"),
                message=_documented_issue_message(code, "Domain validation recorded a warning for this row."),
                safe_context={
                    key: value
                    for key, value in warning.items()
                    if key in {"facility_code", "stockout_flags", "ward_code"}
                }
                | {
                    "remediation": SOURCE_DATA_VALIDATION_ERROR_CATALOG.get(code, {}).get(
                        "remediation",
                        "Review the warning before confirming import.",
                    )
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
        issues.extend(_file_level_issues(artifact, artifact_path, headers, rows))
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
            "truth_level_counts": inspection.get("truth_level_counts") or {},
            "case_class_counts": inspection.get("case_class_counts") or {},
            "sample_row_count": len(inspection.get("sample_rows") or []),
            "rejected_row_diagnostics": (inspection.get("rejected_rows") or [])[:MAX_REJECTED_ROW_DIAGNOSTICS],
            "readiness_summary": inspection.get("readiness_summary") or {},
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
