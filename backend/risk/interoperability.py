from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from datetime import date
from io import StringIO
from typing import Any, Protocol

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from .canonical import (
    CanonicalFacilityRef,
    CanonicalRiskScoreRecord,
    CanonicalWardRef,
)
from .models import (
    ExternalDataElementMapping,
    ExternalOrgUnitMapping,
    ExternalSystem,
    ExternalValueSetMapping,
    HealthFacility,
    InteroperabilityMappingStatus,
    InteroperabilityMappingVersion,
    InteroperabilityRun,
    InteroperabilityRunError,
    InteroperabilityRunItem,
    RiskScore,
    Ward,
)
from accounts.models import User


INTEROPERABILITY_DASHBOARD_SCHEMA_VERSION = "interoperability-contracts-v1"
REQUIRED_RISK_SCORE_EXPORT_FIELDS = (
    "risk_score.score",
    "risk_score.risk_level",
    "risk_score.predicted_cases",
)
INTEROPERABILITY_RISK_SCORE_EXPORT_SOURCE = "cchis://risk-scores/latest"


@dataclass(frozen=True)
class LocationCrosswalkKey:
    entity_type: str
    cchis_public_id: str
    local_reference_code: str


def ward_location_crosswalk_key(ward: CanonicalWardRef) -> LocationCrosswalkKey:
    return LocationCrosswalkKey(
        entity_type="ward",
        cchis_public_id=ward.public_id,
        local_reference_code=ward.ward_code,
    )


def facility_location_crosswalk_key(facility: CanonicalFacilityRef) -> LocationCrosswalkKey:
    return LocationCrosswalkKey(
        entity_type="health_facility",
        cchis_public_id=facility.public_id,
        local_reference_code=facility.facility_code,
    )


def build_dhis2_org_unit_mapping_stub(
    *,
    source_system: str,
    location_key: LocationCrosswalkKey,
    external_org_unit_id: str,
) -> dict[str, str]:
    return {
        "source_system": source_system,
        "entity_type": location_key.entity_type,
        "cchis_public_id": location_key.cchis_public_id,
        "local_reference_code": location_key.local_reference_code,
        "external_org_unit_id": external_org_unit_id,
    }


def build_dhis2_risk_score_export_stub(
    risk_score: CanonicalRiskScoreRecord,
    *,
    external_org_unit_id: str,
    data_element_id: str,
) -> dict[str, object]:
    return {
        "dataSet": "TBD",
        "completeDate": risk_score.generated_at[:10],
        "orgUnit": external_org_unit_id,
        "dataValues": [
            {
                "dataElement": data_element_id,
                "value": risk_score.score,
            },
            {
                "dataElement": f"{data_element_id}_risk_level",
                "value": risk_score.risk_level,
            },
            {
                "dataElement": f"{data_element_id}_predicted_cases",
                "value": risk_score.predicted_cases,
            },
        ],
        "metadata": {
            "source_system": "cchis",
            "schema_version": "cchis.v1",
            "ward_public_id": risk_score.ward_public_id,
            "ward_code": risk_score.ward_code,
            "model_version": risk_score.model_version,
        },
    }


EXCHANGE_INVENTORY = [
    {
        "exchange_type": InteroperabilityRun.EXCHANGE_SURVEILLANCE_CASE_COUNT_IMPORT,
        "label": "Surveillance case count import",
        "direction": InteroperabilityRun.DIRECTION_IMPORT,
        "source_owner": "county_surveillance_team",
        "format": "CSV",
        "cadence": "daily_or_weekly",
        "quality_risk": "case definition drift, duplicate periods, unmapped wards",
        "csv_first": True,
    },
    {
        "exchange_type": InteroperabilityRun.EXCHANGE_OUTBREAK_LABEL_IMPORT,
        "label": "Outbreak label import",
        "direction": InteroperabilityRun.DIRECTION_IMPORT,
        "source_owner": "county_surveillance_team",
        "format": "CSV",
        "cadence": "as_labels_are_confirmed",
        "quality_risk": "late corrections and label-window mismatch",
        "csv_first": True,
    },
    {
        "exchange_type": InteroperabilityRun.EXCHANGE_FACILITY_IMPORT,
        "label": "Facility import",
        "direction": InteroperabilityRun.DIRECTION_IMPORT,
        "source_owner": "county_health_records",
        "format": "CSV",
        "cadence": "monthly_or_on_change",
        "quality_risk": "facility rename, inactive facility, duplicate code",
        "csv_first": True,
    },
    {
        "exchange_type": InteroperabilityRun.EXCHANGE_WARD_ORG_UNIT_MAPPING_IMPORT,
        "label": "Ward/org-unit mapping import",
        "direction": InteroperabilityRun.DIRECTION_IMPORT,
        "source_owner": "health_information_officer",
        "format": "CSV",
        "cadence": "on_external_mapping_change",
        "quality_risk": "mutable display-name matching and retired mapping reuse",
        "csv_first": True,
    },
    {
        "exchange_type": InteroperabilityRun.EXCHANGE_POPULATION_EXPOSURE_IMPORT,
        "label": "Population/exposure import",
        "direction": InteroperabilityRun.DIRECTION_IMPORT,
        "source_owner": "planning_and_statistics_team",
        "format": "CSV",
        "cadence": "release_based",
        "quality_risk": "mixed truth classes and stale denominators",
        "csv_first": True,
    },
    {
        "exchange_type": InteroperabilityRun.EXCHANGE_AGGREGATE_REPORT_EXPORT,
        "label": "Aggregate report export",
        "direction": InteroperabilityRun.DIRECTION_EXPORT,
        "source_owner": "cchis_operations",
        "format": "CSV_OR_API_PAYLOAD",
        "cadence": "weekly_or_monthly",
        "quality_risk": "missing data-element mapping or stale org-unit mapping",
        "csv_first": True,
    },
    {
        "exchange_type": InteroperabilityRun.EXCHANGE_ALERT_ACTION_SUMMARY_EXPORT,
        "label": "Alert/action summary export",
        "direction": InteroperabilityRun.DIRECTION_EXPORT,
        "source_owner": "cchis_operations",
        "format": "CSV_OR_API_PAYLOAD",
        "cadence": "weekly_or_event_based",
        "quality_risk": "status vocabulary drift and over-detailed operational notes",
        "csv_first": True,
    },
]

EXCHANGE_INVENTORY_REQUIRED_FIELDS = (
    "exchange_type",
    "label",
    "direction",
    "source_owner",
    "format",
    "cadence",
    "quality_risk",
    "csv_first",
)


def validate_exchange_inventory_contract() -> list[str]:
    errors: list[str] = []
    declared_exchange_types = {exchange_type for exchange_type, _label in InteroperabilityRun.EXCHANGE_CHOICES}
    inventory_exchange_types = [str(item.get("exchange_type") or "") for item in EXCHANGE_INVENTORY]
    inventory_exchange_type_set = set(inventory_exchange_types)
    missing_exchange_types = sorted(declared_exchange_types - inventory_exchange_type_set)
    unexpected_exchange_types = sorted(inventory_exchange_type_set - declared_exchange_types)
    duplicate_exchange_types = sorted(
        {
            exchange_type
            for exchange_type in inventory_exchange_types
            if exchange_type and inventory_exchange_types.count(exchange_type) > 1
        }
    )

    if missing_exchange_types:
        errors.append(f"exchange_inventory_missing_declared_types:{','.join(missing_exchange_types)}")
    if unexpected_exchange_types:
        errors.append(f"exchange_inventory_unexpected_types:{','.join(unexpected_exchange_types)}")
    if duplicate_exchange_types:
        errors.append(f"exchange_inventory_duplicate_types:{','.join(duplicate_exchange_types)}")

    valid_directions = {InteroperabilityRun.DIRECTION_IMPORT, InteroperabilityRun.DIRECTION_EXPORT}
    for item in EXCHANGE_INVENTORY:
        exchange_type = str(item.get("exchange_type") or "<missing>")
        for field in EXCHANGE_INVENTORY_REQUIRED_FIELDS:
            if item.get(field) in ("", None):
                errors.append(f"{exchange_type}:missing_{field}")
        if item.get("direction") not in valid_directions:
            errors.append(f"{exchange_type}:invalid_direction")
        if item.get("csv_first") is not True:
            errors.append(f"{exchange_type}:csv_first_not_defined")
        if "CSV" not in str(item.get("format") or "").upper():
            errors.append(f"{exchange_type}:csv_format_not_defined")
    return errors


CSV_TEMPLATES = {
    InteroperabilityRun.EXCHANGE_SURVEILLANCE_CASE_COUNT_IMPORT: {
        "filename": "surveillance_case_count_import_template.csv",
        "columns": [
            "external_identifier",
            "ward_public_id",
            "ward_code",
            "reporting_period_start",
            "reporting_period_end",
            "suspected_cases",
            "confirmed_cases",
            "source_record_ref",
        ],
        "example_row": {
            "external_identifier": "DHIS2_EVENT_OR_DATA_VALUE_ID",
            "ward_public_id": "cchis-ward-public-id",
            "ward_code": "WARD-CODE",
            "reporting_period_start": "2026-05-01",
            "reporting_period_end": "2026-05-07",
            "suspected_cases": "3",
            "confirmed_cases": "1",
            "source_record_ref": "dhis2:analytics:row-1",
        },
    },
    InteroperabilityRun.EXCHANGE_OUTBREAK_LABEL_IMPORT: {
        "filename": "outbreak_label_import_template.csv",
        "columns": [
            "external_identifier",
            "ward_public_id",
            "ward_code",
            "label_window_start",
            "label_window_end",
            "outbreak_status",
            "source_record_ref",
        ],
        "example_row": {
            "external_identifier": "DHIS2_OUTBREAK_LABEL_ID",
            "ward_public_id": "cchis-ward-public-id",
            "ward_code": "WARD-CODE",
            "label_window_start": "2026-05-01",
            "label_window_end": "2026-05-14",
            "outbreak_status": "CONFIRMED_OUTBREAK",
            "source_record_ref": "surveillance-label-file:row-1",
        },
    },
    InteroperabilityRun.EXCHANGE_FACILITY_IMPORT: {
        "filename": "facility_import_template.csv",
        "columns": [
            "external_identifier",
            "external_display_name",
            "facility_public_id",
            "facility_code",
            "ward_public_id",
            "ward_code",
            "status",
            "source_record_ref",
        ],
        "example_row": {
            "external_identifier": "DHIS2_FACILITY_ORG_UNIT_ID",
            "external_display_name": "External facility name",
            "facility_public_id": "cchis-facility-public-id",
            "facility_code": "FAC-CODE",
            "ward_public_id": "cchis-ward-public-id",
            "ward_code": "WARD-CODE",
            "status": "ACTIVE",
            "source_record_ref": "facility-master-list:row-1",
        },
    },
    InteroperabilityRun.EXCHANGE_WARD_ORG_UNIT_MAPPING_IMPORT: {
        "filename": "ward_org_unit_mapping_template.csv",
        "columns": [
            "external_identifier",
            "external_display_name",
            "internal_object_type",
            "internal_object_public_id",
            "internal_object_code",
            "mapping_confidence",
            "status",
        ],
        "example_row": {
            "external_identifier": "DHIS2_ORG_UNIT_ID",
            "external_display_name": "External ward name",
            "internal_object_type": "WARD",
            "internal_object_public_id": "cchis-ward-public-id",
            "internal_object_code": "WARD-CODE",
            "mapping_confidence": "0.95",
            "status": "ACTIVE",
        },
    },
    InteroperabilityRun.EXCHANGE_POPULATION_EXPOSURE_IMPORT: {
        "filename": "population_exposure_import_template.csv",
        "columns": [
            "external_identifier",
            "ward_public_id",
            "ward_code",
            "as_of_date",
            "population_estimate",
            "water_exposure_index",
            "source_record_ref",
        ],
        "example_row": {
            "external_identifier": "PLANNING_POPULATION_ROW_ID",
            "ward_public_id": "cchis-ward-public-id",
            "ward_code": "WARD-CODE",
            "as_of_date": "2026-05-01",
            "population_estimate": "24500",
            "water_exposure_index": "0.42",
            "source_record_ref": "population-exposure-file:row-1",
        },
    },
    InteroperabilityRun.EXCHANGE_AGGREGATE_REPORT_EXPORT: {
        "filename": "aggregate_report_export_template.csv",
        "columns": ["period", "org_unit", "data_element", "value", "source_record_ref"],
        "example_row": {
            "period": "202605",
            "org_unit": "DHIS2_ORG_UNIT_ID",
            "data_element": "DHIS2_DATA_ELEMENT_ID",
            "value": "0.82",
            "source_record_ref": "risk_score:123",
        },
    },
    InteroperabilityRun.EXCHANGE_ALERT_ACTION_SUMMARY_EXPORT: {
        "filename": "alert_action_summary_export_template.csv",
        "columns": [
            "period",
            "org_unit",
            "alert_public_id",
            "action_public_id",
            "action_status",
            "source_record_ref",
        ],
        "example_row": {
            "period": "202605",
            "org_unit": "DHIS2_ORG_UNIT_ID",
            "alert_public_id": "cchis-alert-public-id",
            "action_public_id": "cchis-action-public-id",
            "action_status": "COMPLETED",
            "source_record_ref": "preparedness_action:123",
        },
    },
}


def validate_csv_template_contract() -> list[str]:
    errors: list[str] = []
    exchange_types = {exchange_type for exchange_type, _label in InteroperabilityRun.EXCHANGE_CHOICES}
    missing_templates = sorted(exchange_types - set(CSV_TEMPLATES))
    if missing_templates:
        errors.append(f"csv_templates_missing:{','.join(missing_templates)}")
    for exchange_type, template in CSV_TEMPLATES.items():
        columns = template.get("columns") or []
        example_row = template.get("example_row") or {}
        if not template.get("filename"):
            errors.append(f"{exchange_type}:template_filename_missing")
        if not columns:
            errors.append(f"{exchange_type}:template_columns_missing")
        missing_example_columns = [column for column in columns if column not in example_row]
        if missing_example_columns:
            errors.append(f"{exchange_type}:template_example_missing:{','.join(missing_example_columns)}")
    return errors


def build_interoperability_csv_template_file(exchange_type: str) -> dict[str, str | int]:
    template = CSV_TEMPLATES.get(exchange_type)
    if template is None:
        raise ValueError(f"Unknown interoperability CSV template exchange type: {exchange_type}")

    buffer = StringIO()
    columns = list(template["columns"])
    writer = csv.DictWriter(buffer, fieldnames=columns)
    writer.writeheader()
    writer.writerow({column: template["example_row"].get(column, "") for column in columns})
    payload = buffer.getvalue()
    return {
        "filename": str(template["filename"]),
        "content_type": "text/csv",
        "exchange_type": exchange_type,
        "row_count": 1,
        "payload": payload,
        "payload_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    }


CONNECTOR_REQUIRED_INTERFACE_METHODS = (
    "validate_request",
    "dry_run",
    "submit",
    "page_results",
    "classify_failure",
)
CONNECTOR_RETRYABLE_FAILURES = ("timeout", "rate_limited", "server_error")
CONNECTOR_FAILURE_TAXONOMY = {
    "mapping_missing": {
        "retryable": False,
        "safe_message": "Required interoperability mapping is missing.",
        "remediation_hint": "Complete active org-unit, data-element, or value-set mappings before retrying.",
    },
    "schema_validation_failed": {
        "retryable": False,
        "safe_message": "Connector payload failed schema validation.",
        "remediation_hint": "Review the connector request contract and regenerate a dry-run preview.",
    },
    "auth_failed": {
        "retryable": False,
        "safe_message": "Connector authentication failed.",
        "remediation_hint": "Verify the external system auth configuration reference and credentials.",
    },
    "rate_limited": {
        "retryable": True,
        "safe_message": "Connector was rate limited by the external system.",
        "remediation_hint": "Retry after the connector backoff window or configured Retry-After value.",
    },
    "timeout": {
        "retryable": True,
        "safe_message": "Connector request timed out.",
        "remediation_hint": "Retry using the connector retry policy and persisted run checkpoint.",
    },
    "server_error": {
        "retryable": True,
        "safe_message": "External system returned a server error.",
        "remediation_hint": "Retry after the external system is healthy; canonical records remain unchanged.",
    },
    "operator_cancelled": {
        "retryable": False,
        "safe_message": "Connector operation was cancelled before submission.",
        "remediation_hint": "Start a new dry-run preview when the operator is ready to proceed.",
    },
}
CONNECTOR_FAILURE_HTTP_STATUS_MAP = {
    400: "schema_validation_failed",
    401: "auth_failed",
    403: "auth_failed",
    408: "timeout",
    422: "schema_validation_failed",
    429: "rate_limited",
    500: "server_error",
    502: "server_error",
    503: "server_error",
    504: "timeout",
}
CONNECTOR_PAGING_STRATEGY = "cursor_or_page_token_with_run_item_checkpoint"
CONNECTOR_BOUNDARY = {
    "schema_version": "interoperability-connector-boundary-v1",
    "connector_interface": list(CONNECTOR_REQUIRED_INTERFACE_METHODS),
    "auth_config_reference": "stored outside domain records; referenced by ExternalSystem.auth_config_reference",
    "paging_strategy": CONNECTOR_PAGING_STRATEGY,
    "retry_policy": {
        "max_attempts": 3,
        "backoff": "exponential_with_jitter",
        "retryable_failures": list(CONNECTOR_RETRYABLE_FAILURES),
        "idempotency_key": "interoperability_run.public_id",
    },
    "rate_limit_handling": "record connector throttle as run error and leave canonical records unchanged",
    "failure_taxonomy": list(CONNECTOR_FAILURE_TAXONOMY),
    "failure_taxonomy_detail": CONNECTOR_FAILURE_TAXONOMY,
    "dry_run_mode": "dry-run required before any canonical mutation or outbound submission",
    "canonical_data_safety": "connector dry-runs and failed submissions only write InteroperabilityRun ledger records",
}


def validate_connector_boundary_contract(boundary: dict[str, Any] | None = None) -> list[str]:
    boundary = boundary or CONNECTOR_BOUNDARY
    errors: list[str] = []
    if boundary.get("schema_version") != "interoperability-connector-boundary-v1":
        errors.append("connector_boundary_schema_version_invalid")

    interface = set(boundary.get("connector_interface") or [])
    missing_methods = [method for method in CONNECTOR_REQUIRED_INTERFACE_METHODS if method not in interface]
    if missing_methods:
        errors.append(f"connector_interface_missing:{','.join(missing_methods)}")

    if not boundary.get("auth_config_reference"):
        errors.append("connector_auth_config_reference_missing")
    if CONNECTOR_PAGING_STRATEGY != boundary.get("paging_strategy"):
        errors.append("connector_paging_strategy_invalid")

    retry_policy = boundary.get("retry_policy") or {}
    try:
        max_attempts = int(retry_policy.get("max_attempts") or 0)
    except (TypeError, ValueError):
        max_attempts = 0
    if max_attempts < 1:
        errors.append("connector_retry_policy_max_attempts_missing")
    if not retry_policy.get("backoff"):
        errors.append("connector_retry_policy_backoff_missing")
    retryable_failures = set(retry_policy.get("retryable_failures") or [])
    missing_retryable_failures = [code for code in CONNECTOR_RETRYABLE_FAILURES if code not in retryable_failures]
    if missing_retryable_failures:
        errors.append(f"connector_retryable_failures_missing:{','.join(missing_retryable_failures)}")

    taxonomy = set(boundary.get("failure_taxonomy") or [])
    missing_failure_codes = [code for code in CONNECTOR_FAILURE_TAXONOMY if code not in taxonomy]
    if missing_failure_codes:
        errors.append(f"connector_failure_taxonomy_missing:{','.join(missing_failure_codes)}")
    taxonomy_detail = boundary.get("failure_taxonomy_detail") or {}
    for code in taxonomy:
        detail = taxonomy_detail.get(code) or {}
        if code not in CONNECTOR_FAILURE_TAXONOMY:
            errors.append(f"connector_failure_taxonomy_unexpected:{code}")
        if "retryable" not in detail:
            errors.append(f"{code}:connector_failure_retryable_missing")
        if not detail.get("safe_message"):
            errors.append(f"{code}:connector_failure_safe_message_missing")
        if not detail.get("remediation_hint"):
            errors.append(f"{code}:connector_failure_remediation_hint_missing")

    if not boundary.get("rate_limit_handling"):
        errors.append("connector_rate_limit_handling_missing")
    if "dry" not in str(boundary.get("dry_run_mode") or "").lower():
        errors.append("connector_dry_run_mode_missing")
    if "InteroperabilityRun" not in str(boundary.get("canonical_data_safety") or ""):
        errors.append("connector_canonical_data_safety_missing")
    return errors


@dataclass(frozen=True)
class InteroperabilityConnectorRequest:
    run_public_id: str
    direction: str
    exchange_type: str
    system_key: str
    endpoint_url: str
    auth_config_reference: str
    source_reference: str
    dry_run: bool
    payload: dict[str, Any]
    cursor: str = ""
    paging_strategy: str = CONNECTOR_PAGING_STRATEGY

    def as_payload(self) -> dict[str, Any]:
        return {
            "run_public_id": self.run_public_id,
            "direction": self.direction,
            "exchange_type": self.exchange_type,
            "system_key": self.system_key,
            "endpoint_url": self.endpoint_url,
            "auth_config_reference": self.auth_config_reference,
            "source_reference": self.source_reference,
            "dry_run": self.dry_run,
            "payload": self.payload,
            "cursor": self.cursor,
            "paging_strategy": self.paging_strategy,
        }


class InteroperabilityConnectorFailure(Exception):
    def __init__(
        self,
        failure_code: str,
        *,
        safe_message: str = "",
        remediation_hint: str = "",
        retryable: bool | None = None,
        http_status: int | None = None,
        retry_after_seconds: int | None = None,
        connector_context: dict[str, Any] | None = None,
    ) -> None:
        normalized_code = failure_code if failure_code in CONNECTOR_FAILURE_TAXONOMY else "server_error"
        detail = CONNECTOR_FAILURE_TAXONOMY[normalized_code]
        self.failure_code = normalized_code
        self.safe_message = safe_message or str(detail["safe_message"])
        self.remediation_hint = remediation_hint or str(detail["remediation_hint"])
        self.retryable = bool(detail["retryable"] if retryable is None else retryable)
        self.http_status = http_status
        self.retry_after_seconds = retry_after_seconds
        self.connector_context = connector_context or {}
        super().__init__(self.safe_message)

    def as_run_metadata(self) -> dict[str, Any]:
        return {
            "connector_failure_code": self.failure_code,
            "connector_failure_retryable": self.retryable,
            "connector_failure_http_status": self.http_status,
            "connector_retry_after_seconds": self.retry_after_seconds,
            "connector_context": self.connector_context,
            "canonical_mutation_performed": False,
        }


class InteroperabilityConnector(Protocol):
    def validate_request(self, request: InteroperabilityConnectorRequest) -> list[str]:
        ...

    def dry_run(self, request: InteroperabilityConnectorRequest) -> dict[str, Any]:
        ...

    def submit(self, request: InteroperabilityConnectorRequest) -> dict[str, Any]:
        ...

    def page_results(self, request: InteroperabilityConnectorRequest) -> dict[str, Any]:
        ...

    def classify_failure(self, error: Exception) -> InteroperabilityConnectorFailure:
        ...


def classify_connector_failure(
    error: Exception | str,
    *,
    status_code: int | None = None,
    retry_after_seconds: int | None = None,
) -> InteroperabilityConnectorFailure:
    failure_code = CONNECTOR_FAILURE_HTTP_STATUS_MAP.get(status_code or 0, "")
    error_text = str(error).lower()
    exception_type = error.__class__.__name__ if isinstance(error, Exception) else "connector_error"
    if not failure_code:
        if "rate" in error_text or "429" in error_text:
            failure_code = "rate_limited"
        elif "timeout" in error_text or "timed out" in error_text:
            failure_code = "timeout"
        elif "auth" in error_text or "401" in error_text or "403" in error_text:
            failure_code = "auth_failed"
        elif "schema" in error_text or "validation" in error_text or "422" in error_text:
            failure_code = "schema_validation_failed"
        else:
            failure_code = "server_error"
    return InteroperabilityConnectorFailure(
        failure_code,
        http_status=status_code,
        retry_after_seconds=retry_after_seconds,
        connector_context={
            "exception_type": exception_type,
            "http_status": status_code,
        },
    )


def _normalized_system_key(system_key: str) -> str:
    return (system_key or "dhis2").strip().lower()


def get_or_create_external_system(system_key: str = "dhis2") -> ExternalSystem:
    normalized_key = _normalized_system_key(system_key)
    defaults = {
        "display_name": "DHIS2" if normalized_key == "dhis2" else normalized_key.upper(),
        "system_type": ExternalSystem.SYSTEM_DHIS2 if normalized_key == "dhis2" else ExternalSystem.SYSTEM_OTHER,
        "owner": "health_information_officer",
        "default_exchange_format": "CSV",
        "lineage_metadata": {"created_by": "interoperability_contract_boundary"},
    }
    system, _created = ExternalSystem.objects.get_or_create(system_key=normalized_key, defaults=defaults)
    return system


def active_mapping_version(system: ExternalSystem, version_label: str = "") -> InteroperabilityMappingVersion | None:
    queryset = InteroperabilityMappingVersion.objects.filter(
        system=system,
        status=InteroperabilityMappingVersion.STATUS_ACTIVE,
        retired_at__isnull=True,
    )
    if version_label:
        queryset = queryset.filter(version_label=version_label)
    return queryset.order_by("-effective_date", "-created_at").first()


def _ensure_mapping_version(
    *,
    system: ExternalSystem,
    version_label: str,
    operator,
    activate: bool,
) -> InteroperabilityMappingVersion:
    normalized_label = (version_label or f"{system.system_key}-mapping-{timezone.localdate().isoformat()}").strip()
    mapping_version, _created = InteroperabilityMappingVersion.objects.get_or_create(
        system=system,
        version_label=normalized_label,
        defaults={
            "status": (
                InteroperabilityMappingVersion.STATUS_ACTIVE
                if activate
                else InteroperabilityMappingVersion.STATUS_DRAFT
            ),
            "reviewed_by": operator if activate else None,
            "lineage_metadata": {"created_by": "csv_org_unit_mapping_import"},
        },
    )
    if activate and mapping_version.status != InteroperabilityMappingVersion.STATUS_ACTIVE:
        mapping_version.status = InteroperabilityMappingVersion.STATUS_ACTIVE
        mapping_version.reviewed_by = operator
        mapping_version.retired_at = None
        mapping_version.save(update_fields=["status", "reviewed_by", "retired_at", "updated_at"])
    return mapping_version


def _safe_digest(value: object) -> str:
    if value in ("", None):
        return ""
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _parse_mapping_confidence(value: object) -> tuple[float | None, str, str]:
    raw_value = str(value or "").strip()
    if not raw_value:
        return None, "missing_mapping_confidence", "Mapping confidence is required as a decimal from 0 to 1."
    try:
        parsed = float(raw_value)
    except (TypeError, ValueError):
        return None, "invalid_mapping_confidence", "Mapping confidence must be a numeric decimal from 0 to 1."
    if parsed < 0 or parsed > 1:
        return None, "mapping_confidence_out_of_range", "Mapping confidence must be between 0 and 1."
    return parsed, "", ""


def _parse_mapping_status(value: object) -> tuple[str | None, str, str]:
    normalized = str(value or "").strip().upper()
    valid_statuses = {choice[0] for choice in InteroperabilityMappingStatus.choices}
    if not normalized:
        return None, "missing_mapping_status", "Mapping status is required."
    if normalized not in valid_statuses:
        return None, "invalid_mapping_status", "Mapping status must use a declared interoperability mapping status."
    return normalized, "", ""


def _row_value(row: dict[str, str], key: str) -> str:
    return str(row.get(key) or "").strip()


def _safe_row_context(row: dict[str, str]) -> dict[str, str]:
    allowed = CSV_TEMPLATES[InteroperabilityRun.EXCHANGE_WARD_ORG_UNIT_MAPPING_IMPORT]["columns"]
    return {key: _row_value(row, key) for key in allowed}


def _read_csv_rows(csv_text: str) -> tuple[list[dict[str, str]], list[str]]:
    reader = csv.DictReader(StringIO(csv_text or ""))
    rows = [dict(row) for row in reader]
    return rows, list(reader.fieldnames or [])


def _resolve_internal_org_unit(row: dict[str, str]) -> tuple[dict[str, Any] | None, str, str]:
    object_type = _row_value(row, "internal_object_type").upper()
    object_type = object_type.replace("HEALTH FACILITY", "HEALTH_FACILITY")
    public_id = _row_value(row, "internal_object_public_id")
    code = _row_value(row, "internal_object_code")

    if object_type in {"WARD", "WARDS"}:
        ward = None
        if public_id:
            try:
                ward = Ward.objects.filter(public_id=public_id, is_active=True).first()
            except (TypeError, ValueError):
                ward = None
        if ward is None and code:
            ward = Ward.objects.filter(ward_code=code, is_active=True).first()
        if ward is None:
            return None, "mapping_unresolved_internal_ward", "No active CCHIS ward matched the supplied public id or ward code."
        return {
            "internal_object_type": ExternalOrgUnitMapping.INTERNAL_WARD,
            "internal_object_public_id": str(ward.public_id),
            "internal_object_code": ward.ward_code,
            "ward": ward,
            "facility": None,
        }, "", ""

    if object_type in {"FACILITY", "HEALTH_FACILITY", "HEALTH_FACILITIES"}:
        facility = None
        if public_id:
            try:
                facility = HealthFacility.objects.select_related("ward").filter(public_id=public_id, is_active=True).first()
            except (TypeError, ValueError):
                facility = None
        if facility is None and code:
            facility = HealthFacility.objects.select_related("ward").filter(facility_code=code, is_active=True).first()
        if facility is None:
            return None, "mapping_unresolved_internal_facility", "No CCHIS facility matched the supplied public id or facility code."
        return {
            "internal_object_type": ExternalOrgUnitMapping.INTERNAL_FACILITY,
            "internal_object_public_id": str(facility.public_id),
            "internal_object_code": facility.facility_code,
            "ward": None,
            "facility": facility,
        }, "", ""

    return None, "unsupported_internal_object_type", "Use WARD or HEALTH_FACILITY as the internal_object_type."


def _record_run_error(
    *,
    run: InteroperabilityRun,
    item: InteroperabilityRunItem | None = None,
    error_code: str,
    field_path: str = "",
    safe_message: str,
    remediation_hint: str = "",
    raw_value: object = "",
    severity: str = InteroperabilityRunError.SEVERITY_ERROR,
) -> InteroperabilityRunError:
    return InteroperabilityRunError.objects.create(
        run=run,
        item=item,
        severity=severity,
        error_code=error_code,
        field_path=field_path,
        safe_message=safe_message,
        remediation_hint=remediation_hint,
        raw_value_digest=_safe_digest(raw_value),
    )


RUN_TERMINAL_STATUSES = {
    InteroperabilityRun.STATUS_READY_FOR_CONFIRMATION,
    InteroperabilityRun.STATUS_COMPLETED,
    InteroperabilityRun.STATUS_PARTIAL,
    InteroperabilityRun.STATUS_FAILED,
}
RUN_REVIEW_ITEM_STATUSES = {
    InteroperabilityRunItem.STATUS_REJECTED,
    InteroperabilityRunItem.STATUS_UNMAPPED,
}


def interoperability_run_source_reference(run: InteroperabilityRun) -> str:
    metadata = run.lineage_metadata or {}
    return (
        run.source_file_name
        or run.endpoint_url
        or str(metadata.get("source_reference") or "")
        or str(metadata.get("source_file_sha256") or "")
        or str(metadata.get("original_source_file_sha256") or "")
        or str(metadata.get("canonical_source") or "")
    )


def validate_interoperability_run_record_contract(run: InteroperabilityRun) -> list[str]:
    errors: list[str] = []
    metadata = run.lineage_metadata or {}
    valid_directions = {choice[0] for choice in InteroperabilityRun.DIRECTION_CHOICES}
    valid_exchange_types = {choice[0] for choice in InteroperabilityRun.EXCHANGE_CHOICES}
    valid_statuses = {choice[0] for choice in InteroperabilityRun.STATUS_CHOICES}

    if run.direction not in valid_directions:
        errors.append("run_direction_invalid")
    if run.exchange_type not in valid_exchange_types:
        errors.append("run_exchange_type_invalid")
    if run.status not in valid_statuses:
        errors.append("run_status_invalid")
    if not run.system_id:
        errors.append("run_system_missing")
    if not run.started_at:
        errors.append("run_started_at_missing")
    if not interoperability_run_source_reference(run):
        errors.append("run_source_reference_missing")
    if run.status in RUN_TERMINAL_STATUSES and run.completed_at is None:
        errors.append("terminal_run_completed_at_missing")
    if run.status in {InteroperabilityRun.STATUS_FAILED, InteroperabilityRun.STATUS_PARTIAL} and not run.error_summary:
        errors.append("problem_run_error_summary_missing")
    if metadata.get("retry_created_from_public_id") and not run.retry_of_id:
        errors.append("retry_original_run_missing")

    review_items = run.items.filter(status__in=RUN_REVIEW_ITEM_STATUSES)
    for item in review_items:
        if not item.safe_context and not item.source_record_ref:
            errors.append("review_item_context_missing")
            break
    if run.records_rejected > 0 and not run.errors.exists():
        errors.append("rejected_records_error_records_missing")
    return errors


def build_connector_request_for_run(
    run: InteroperabilityRun,
    *,
    payload: dict[str, Any] | None = None,
    cursor: str = "",
) -> InteroperabilityConnectorRequest:
    connector_payload = payload
    if connector_payload is None:
        connector_payload = run.export_payload if run.direction == InteroperabilityRun.DIRECTION_EXPORT else run.dry_run_preview
    return InteroperabilityConnectorRequest(
        run_public_id=str(run.public_id),
        direction=run.direction,
        exchange_type=run.exchange_type,
        system_key=run.system.system_key,
        endpoint_url=run.endpoint_url or run.system.api_base_url,
        auth_config_reference=run.system.auth_config_reference,
        source_reference=interoperability_run_source_reference(run),
        dry_run=run.dry_run,
        payload=connector_payload or {},
        cursor=cursor,
    )


@transaction.atomic
def create_connector_failure_run(
    *,
    system_key: str,
    direction: str,
    exchange_type: str,
    operator,
    failure: InteroperabilityConnectorFailure | Exception | str,
    endpoint_url: str = "",
    source_reference: str = "",
    retry_of: InteroperabilityRun | None = None,
    dry_run: bool = True,
) -> InteroperabilityRun:
    system = get_or_create_external_system(system_key)
    classified_failure = (
        failure if isinstance(failure, InteroperabilityConnectorFailure) else classify_connector_failure(failure)
    )
    durable_source_reference = (
        source_reference
        or endpoint_url
        or system.api_base_url
        or f"connector://{system.system_key}/{exchange_type}"
    )
    run = InteroperabilityRun.objects.create(
        direction=direction,
        exchange_type=exchange_type,
        system=system,
        retry_of=retry_of,
        status=InteroperabilityRun.STATUS_FAILED,
        dry_run=dry_run,
        endpoint_url=(endpoint_url or durable_source_reference)[:500],
        records_rejected=1,
        operator=operator,
        error_summary=classified_failure.safe_message,
        connector_config=CONNECTOR_BOUNDARY,
        dry_run_preview={
            "schema_version": "interoperability-connector-failure-v1",
            "dry_run": dry_run,
            "failure_code": classified_failure.failure_code,
            "retryable": classified_failure.retryable,
            "retry_after_seconds": classified_failure.retry_after_seconds,
            "canonical_mutation_performed": False,
            "next_action": (
                "retry_after_backoff"
                if classified_failure.retryable
                else "review_connector_configuration_or_mapping"
            ),
        },
        completed_at=timezone.now(),
        lineage_metadata={
            "source_reference": durable_source_reference,
            "connector_boundary_schema_version": CONNECTOR_BOUNDARY["schema_version"],
            "connector_paging_strategy": CONNECTOR_PAGING_STRATEGY,
            "connector_retry_policy": CONNECTOR_BOUNDARY["retry_policy"],
            "dry_run_required": True,
            **classified_failure.as_run_metadata(),
        },
    )
    _record_run_error(
        run=run,
        error_code=classified_failure.failure_code,
        field_path="connector",
        safe_message=classified_failure.safe_message,
        remediation_hint=classified_failure.remediation_hint,
        raw_value=f"{classified_failure.failure_code}:{classified_failure.http_status or ''}",
    )
    return run


@transaction.atomic
def create_org_unit_mapping_import_run(
    *,
    system_key: str,
    csv_text: str,
    source_file_name: str,
    mapping_version_label: str,
    operator,
    confirm: bool = False,
    retry_of: InteroperabilityRun | None = None,
) -> InteroperabilityRun:
    system = get_or_create_external_system(system_key)
    rows, columns = _read_csv_rows(csv_text)
    source_file_hash = hashlib.sha256((csv_text or "").encode("utf-8")).hexdigest()
    mapping_version = _ensure_mapping_version(
        system=system,
        version_label=mapping_version_label,
        operator=operator,
        activate=False,
    )
    run = InteroperabilityRun.objects.create(
        direction=InteroperabilityRun.DIRECTION_IMPORT,
        exchange_type=InteroperabilityRun.EXCHANGE_WARD_ORG_UNIT_MAPPING_IMPORT,
        system=system,
        mapping_version=mapping_version,
        retry_of=retry_of,
        status=InteroperabilityRun.STATUS_DRAFT,
        dry_run=not confirm,
        source_file_name=source_file_name[:200],
        operator=operator,
        lineage_metadata={
            "source_file_sha256": source_file_hash,
            "csv_columns": columns,
            "csv_first": True,
            "operator_confirmation": confirm,
            "confirmed_from_public_id": str(retry_of.public_id) if confirm and retry_of else "",
        },
    )

    confirmation_error_code = ""
    confirmation_error_message = ""
    if confirm:
        retry_metadata = (retry_of.lineage_metadata or {}) if retry_of else {}
        retry_preview = (retry_of.dry_run_preview or {}) if retry_of else {}
        if retry_of is None:
            confirmation_error_code = "prior_dry_run_required"
            confirmation_error_message = "Confirmed mapping import requires a matching clean dry-run."
        elif retry_of.system_id != system.id or retry_of.exchange_type != InteroperabilityRun.EXCHANGE_WARD_ORG_UNIT_MAPPING_IMPORT:
            confirmation_error_code = "dry_run_confirmation_mismatch"
            confirmation_error_message = "Confirmed mapping import must reference a dry-run for the same system and exchange."
        elif retry_of.mapping_version_id and retry_of.mapping_version_id != mapping_version.id:
            confirmation_error_code = "dry_run_mapping_version_mismatch"
            confirmation_error_message = "Confirmed mapping import must use the same mapping version as the reviewed dry-run."
        elif retry_metadata.get("source_file_sha256") != source_file_hash:
            confirmation_error_code = "dry_run_source_mismatch"
            confirmation_error_message = "Confirmed mapping import CSV does not match the reviewed dry-run source digest."
        elif (
            not retry_of.dry_run
            or retry_of.status != InteroperabilityRun.STATUS_READY_FOR_CONFIRMATION
            or retry_of.records_rejected
            or retry_preview.get("confirmable") is not True
        ):
            confirmation_error_code = "dry_run_not_confirmable"
            confirmation_error_message = "Confirmed mapping import must reference a clean dry-run that is ready for confirmation."

    if confirmation_error_code:
        _record_run_error(
            run=run,
            error_code=confirmation_error_code,
            field_path="retry_of_public_id",
            safe_message=confirmation_error_message,
            remediation_hint="Run a clean dry-run, review the result, then confirm that exact source file.",
            raw_value=str(retry_of.public_id) if retry_of else "",
        )

    accepted = 0
    rejected = 0
    accepted_mapping_intents: list[dict[str, Any]] = []
    seen_external_identifiers: set[str] = set()
    seen_internal_targets: set[tuple[str, str]] = set()
    mutation_performed = False
    required_columns = CSV_TEMPLATES[InteroperabilityRun.EXCHANGE_WARD_ORG_UNIT_MAPPING_IMPORT]["columns"]
    missing_columns = [column for column in required_columns if column not in columns]
    if missing_columns:
        _record_run_error(
            run=run,
            error_code="csv_missing_required_columns",
            safe_message="CSV is missing required interoperability mapping columns.",
            remediation_hint=", ".join(missing_columns),
            raw_value=missing_columns,
        )

    for index, row in enumerate(rows, start=2):
        external_identifier = _row_value(row, "external_identifier")
        status_value = InteroperabilityRunItem.STATUS_ACCEPTED
        error_code = ""
        safe_message = ""
        field_path = ""
        resolved = None
        mapping_confidence: float | None = None
        mapping_status = ""

        if not external_identifier:
            status_value = InteroperabilityRunItem.STATUS_REJECTED
            error_code = "missing_external_identifier"
            field_path = "external_identifier"
            safe_message = "External org-unit identifier is required."
        elif external_identifier in seen_external_identifiers:
            status_value = InteroperabilityRunItem.STATUS_REJECTED
            error_code = "duplicate_external_identifier"
            field_path = "external_identifier"
            safe_message = "External org-unit identifier appears more than once in this CSV."
        else:
            seen_external_identifiers.add(external_identifier)
            resolved, error_code, safe_message = _resolve_internal_org_unit(row)
            if resolved is None:
                status_value = InteroperabilityRunItem.STATUS_UNMAPPED
                field_path = "internal_object_public_id"
            else:
                internal_target = (resolved["internal_object_type"], resolved["internal_object_public_id"])
                if internal_target in seen_internal_targets:
                    status_value = InteroperabilityRunItem.STATUS_REJECTED
                    error_code = "duplicate_internal_object_mapping"
                    field_path = "internal_object_public_id"
                    safe_message = "A CCHIS location appears more than once in this mapping CSV."
                else:
                    mapping_confidence, error_code, safe_message = _parse_mapping_confidence(
                        _row_value(row, "mapping_confidence")
                    )
                    if mapping_confidence is None:
                        status_value = InteroperabilityRunItem.STATUS_REJECTED
                        field_path = "mapping_confidence"
                    else:
                        parsed_status, error_code, safe_message = _parse_mapping_status(_row_value(row, "status"))
                        if parsed_status is None:
                            status_value = InteroperabilityRunItem.STATUS_REJECTED
                            field_path = "status"
                        else:
                            mapping_status = parsed_status
                            seen_internal_targets.add(internal_target)

        item = InteroperabilityRunItem.objects.create(
            run=run,
            row_number=index,
            external_identifier=external_identifier,
            internal_object_type=(resolved or {}).get("internal_object_type", _row_value(row, "internal_object_type")),
            internal_object_public_id=(resolved or {}).get("internal_object_public_id", _row_value(row, "internal_object_public_id")),
            internal_object_code=(resolved or {}).get("internal_object_code", _row_value(row, "internal_object_code")),
            status=status_value,
            action=(
                InteroperabilityRunItem.ACTION_IMPORT_MAPPING
                if status_value == InteroperabilityRunItem.STATUS_ACCEPTED
                else InteroperabilityRunItem.ACTION_NOOP
            ),
            safe_context=_safe_row_context(row),
            source_record_ref=f"{source_file_name}:{index}",
        )

        if status_value == InteroperabilityRunItem.STATUS_ACCEPTED:
            accepted += 1
            accepted_mapping_intents.append(
                {
                    "external_identifier": external_identifier,
                    "external_display_name": _row_value(row, "external_display_name"),
                    "internal_object_type": resolved["internal_object_type"],
                    "internal_object_public_id": resolved["internal_object_public_id"],
                    "internal_object_code": resolved["internal_object_code"],
                    "ward": resolved["ward"],
                    "facility": resolved["facility"],
                    "mapping_confidence": mapping_confidence,
                    "status": mapping_status,
                    "source_row_number": index,
                }
            )
        else:
            rejected += 1
            _record_run_error(
                run=run,
                item=item,
                error_code=error_code,
                field_path=field_path,
                safe_message=safe_message,
                remediation_hint="Review the external identifier and stable CCHIS public id/code before confirming.",
                raw_value=_safe_row_context(row),
            )

    run.records_seen = len(rows)
    run.records_accepted = accepted
    run.records_rejected = rejected
    run.mapping_coverage = round((accepted / len(rows)) * 100, 2) if rows else 0.0
    row_confirmable = not missing_columns and accepted > 0 and rejected == 0
    mutation_allowed = row_confirmable and not confirmation_error_code
    if not rows or missing_columns:
        run.status = InteroperabilityRun.STATUS_FAILED
        run.error_summary = "CSV validation failed before operator confirmation."
    elif confirmation_error_code:
        run.status = InteroperabilityRun.STATUS_FAILED
        run.error_summary = f"{confirmation_error_message} No mapping records were written."
    elif rejected:
        run.status = InteroperabilityRun.STATUS_PARTIAL
        run.error_summary = f"{rejected} row(s) need review before this exchange can be trusted."
        if confirm:
            run.error_summary += " No mapping records were written."
    elif confirm:
        if mapping_version.status != InteroperabilityMappingVersion.STATUS_ACTIVE:
            mapping_version.status = InteroperabilityMappingVersion.STATUS_ACTIVE
            mapping_version.reviewed_by = operator
            mapping_version.retired_at = None
            mapping_version.save(update_fields=["status", "reviewed_by", "retired_at", "updated_at"])
        for intent in accepted_mapping_intents:
            ExternalOrgUnitMapping.objects.update_or_create(
                system=system,
                mapping_version=mapping_version,
                external_identifier=intent["external_identifier"],
                defaults={
                    "external_display_name": intent["external_display_name"],
                    "internal_object_type": intent["internal_object_type"],
                    "internal_object_public_id": intent["internal_object_public_id"],
                    "internal_object_code": intent["internal_object_code"],
                    "ward": intent["ward"],
                    "facility": intent["facility"],
                    "mapping_confidence": intent["mapping_confidence"],
                    "status": intent["status"],
                    "effective_date": timezone.localdate(),
                    "retired_date": None,
                    "reviewed_by": operator,
                    "lineage_metadata": {
                        "source_run_public_id": str(run.public_id),
                        "source_file_sha256": source_file_hash,
                        "source_row_number": intent["source_row_number"],
                    },
                },
            )
        mutation_performed = True
        run.status = InteroperabilityRun.STATUS_COMPLETED
        run.error_summary = ""
    else:
        run.status = InteroperabilityRun.STATUS_READY_FOR_CONFIRMATION
        run.error_summary = ""
    run.dry_run_preview = {
        "schema_version": "interoperability-csv-preview-v1",
        "columns": columns,
        "required_columns": required_columns,
        "missing_columns": missing_columns,
        "accepted_rows": accepted,
        "rejected_rows": rejected,
        "mapping_coverage": run.mapping_coverage,
        "mapping_coverage_report": {
            "records_seen": len(rows),
            "records_with_resolved_mapping": accepted,
            "records_requiring_review": rejected,
            "coverage_percent": run.mapping_coverage,
        },
        "confirmable": mutation_allowed,
        "operator_confirmation_required": not confirm and row_confirmable,
        "confirmation_error": confirmation_error_code,
        "mutation_allowed": mutation_allowed,
        "mutation_performed": mutation_performed,
        "next_action": (
            "mapping_records_written"
            if mutation_performed
            else "confirm_import"
            if row_confirmable and not confirm
            else "run_clean_dry_run_first"
            if confirmation_error_code
            else "confirm_import"
            if mutation_allowed
            else "review_errors"
        ),
    }
    run.completed_at = timezone.now()
    run.save(
        update_fields=[
            "records_seen",
            "records_accepted",
            "records_rejected",
            "mapping_coverage",
            "status",
            "error_summary",
            "dry_run_preview",
            "completed_at",
            "updated_at",
        ]
    )
    return run


def active_org_unit_mapping_for_ward(system: ExternalSystem, ward: Ward) -> ExternalOrgUnitMapping | None:
    return (
        ExternalOrgUnitMapping.objects.select_related("mapping_version", "system", "ward")
        .filter(
            system=system,
            system__status=ExternalSystem.STATUS_ACTIVE,
            mapping_version__status=InteroperabilityMappingVersion.STATUS_ACTIVE,
            mapping_version__retired_at__isnull=True,
            internal_object_type=ExternalOrgUnitMapping.INTERNAL_WARD,
            ward=ward,
            ward__is_active=True,
            status=InteroperabilityMappingStatus.ACTIVE,
            retired_date__isnull=True,
        )
        .order_by("-mapping_version__effective_date", "-updated_at")
        .first()
    )


def active_org_unit_mapping_for_facility(
    system: ExternalSystem,
    facility: HealthFacility,
) -> ExternalOrgUnitMapping | None:
    return (
        ExternalOrgUnitMapping.objects.select_related("mapping_version", "system", "facility")
        .filter(
            system=system,
            system__status=ExternalSystem.STATUS_ACTIVE,
            mapping_version__status=InteroperabilityMappingVersion.STATUS_ACTIVE,
            mapping_version__retired_at__isnull=True,
            internal_object_type=ExternalOrgUnitMapping.INTERNAL_FACILITY,
            facility=facility,
            facility__is_active=True,
            status=InteroperabilityMappingStatus.ACTIVE,
            retired_date__isnull=True,
        )
        .order_by("-mapping_version__effective_date", "-updated_at")
        .first()
    )


def _active_data_element_mappings(
    *,
    system: ExternalSystem,
    mapping_version: InteroperabilityMappingVersion,
    exchange_type: str,
) -> dict[str, ExternalDataElementMapping]:
    mappings = (
        ExternalDataElementMapping.objects.filter(
            system=system,
            system__status=ExternalSystem.STATUS_ACTIVE,
            mapping_version=mapping_version,
            mapping_version__status=InteroperabilityMappingVersion.STATUS_ACTIVE,
            mapping_version__retired_at__isnull=True,
            exchange_type=exchange_type,
            status=InteroperabilityMappingStatus.ACTIVE,
            retired_date__isnull=True,
        )
        .order_by("internal_field")
    )
    return {mapping.internal_field: mapping for mapping in mappings}


def active_data_element_mappings_for_exchange(
    *,
    system: ExternalSystem,
    mapping_version: InteroperabilityMappingVersion,
    exchange_type: str,
) -> dict[str, ExternalDataElementMapping]:
    return _active_data_element_mappings(
        system=system,
        mapping_version=mapping_version,
        exchange_type=exchange_type,
    )


def active_data_element_mapping_for_field(
    *,
    system: ExternalSystem,
    mapping_version: InteroperabilityMappingVersion,
    exchange_type: str,
    internal_field: str,
) -> ExternalDataElementMapping | None:
    return active_data_element_mappings_for_exchange(
        system=system,
        mapping_version=mapping_version,
        exchange_type=exchange_type,
    ).get(internal_field)


def active_value_set_mapping_for_internal_value(
    *,
    system: ExternalSystem,
    mapping_version: InteroperabilityMappingVersion,
    value_set_key: str,
    internal_value: str,
) -> ExternalValueSetMapping | None:
    return (
        ExternalValueSetMapping.objects.filter(
            system=system,
            system__status=ExternalSystem.STATUS_ACTIVE,
            mapping_version=mapping_version,
            mapping_version__status=InteroperabilityMappingVersion.STATUS_ACTIVE,
            mapping_version__retired_at__isnull=True,
            value_set_key=value_set_key,
            internal_value=internal_value,
            status=InteroperabilityMappingStatus.ACTIVE,
            retired_date__isnull=True,
        )
        .order_by("-effective_date", "-updated_at")
        .first()
    )


def _latest_risk_scores() -> list[RiskScore]:
    latest_by_ward: dict[int, RiskScore] = {}
    for risk_score in RiskScore.objects.select_related("ward", "model_run").order_by("ward_id", "-generated_at", "-id"):
        latest_by_ward.setdefault(risk_score.ward_id, risk_score)
    return list(latest_by_ward.values())


@transaction.atomic
def create_risk_score_export_preview(
    *,
    system_key: str,
    operator,
    mapping_version_label: str = "",
) -> InteroperabilityRun:
    system = get_or_create_external_system(system_key)
    mapping_version = active_mapping_version(system, mapping_version_label)
    run = InteroperabilityRun.objects.create(
        direction=InteroperabilityRun.DIRECTION_EXPORT,
        exchange_type=InteroperabilityRun.EXCHANGE_AGGREGATE_REPORT_EXPORT,
        system=system,
        mapping_version=mapping_version,
        status=InteroperabilityRun.STATUS_DRAFT,
        dry_run=True,
        endpoint_url=INTEROPERABILITY_RISK_SCORE_EXPORT_SOURCE,
        operator=operator,
        connector_config=CONNECTOR_BOUNDARY,
        lineage_metadata={"csv_first": True, "canonical_source": "risk_score"},
    )

    if mapping_version is None:
        _record_run_error(
            run=run,
            error_code="active_mapping_version_missing",
            safe_message="No active interoperability mapping version is available for this system.",
            remediation_hint="Activate a reviewed mapping version before exporting.",
        )
        run.status = InteroperabilityRun.STATUS_FAILED
        run.error_summary = "Active mapping version is missing."
        run.dry_run_preview = {
            "schema_version": "interoperability-export-preview-v1",
            "records_seen": 0,
            "records_accepted": 0,
            "records_rejected": 1,
            "mapping_coverage": 0.0,
            "mapping_coverage_report": {
                "records_seen": 0,
                "records_with_resolved_mapping": 0,
                "records_requiring_review": 1,
                "coverage_percent": 0.0,
            },
            "missing_required_fields": list(REQUIRED_RISK_SCORE_EXPORT_FIELDS),
            "confirmable": False,
            "operator_confirmation_required": False,
            "mutation_performed": False,
            "source_trace": [],
        }
        run.completed_at = timezone.now()
        run.save(update_fields=["status", "error_summary", "dry_run_preview", "completed_at", "updated_at"])
        return run

    data_elements = active_data_element_mappings_for_exchange(
        system=system,
        mapping_version=mapping_version,
        exchange_type=InteroperabilityRun.EXCHANGE_AGGREGATE_REPORT_EXPORT,
    )
    missing_fields = [field for field in REQUIRED_RISK_SCORE_EXPORT_FIELDS if field not in data_elements]
    for field in missing_fields:
        _record_run_error(
            run=run,
            error_code="required_data_element_mapping_missing",
            field_path=field,
            safe_message="A required data-element mapping is missing for aggregate export.",
            remediation_hint="Create and activate an ExternalDataElementMapping for this field.",
        )

    export_records = []
    export_csv_rows = []
    accepted = 0
    rejected = len(missing_fields)
    risk_scores = _latest_risk_scores()
    for risk_score in risk_scores:
        org_mapping = active_org_unit_mapping_for_ward(system, risk_score.ward)
        if org_mapping is None:
            item = InteroperabilityRunItem.objects.create(
                run=run,
                row_number=0,
                external_identifier="",
                internal_object_type=ExternalOrgUnitMapping.INTERNAL_WARD,
                internal_object_public_id=str(risk_score.ward.public_id),
                internal_object_code=risk_score.ward.ward_code,
                status=InteroperabilityRunItem.STATUS_UNMAPPED,
                action=InteroperabilityRunItem.ACTION_EXPORT_RECORD,
                safe_context={
                    "ward_public_id": str(risk_score.ward.public_id),
                    "ward_code": risk_score.ward.ward_code,
                    "risk_score_id": risk_score.id,
                    "model_version": risk_score.model_version,
                },
                source_record_ref=f"risk_score:{risk_score.id}",
            )
            rejected += 1
            _record_run_error(
                run=run,
                item=item,
                error_code="org_unit_mapping_missing",
                field_path="ward",
                safe_message="No active org-unit mapping exists for this ward.",
                remediation_hint="Import or activate a reviewed ward/org-unit mapping before export.",
                raw_value=str(risk_score.ward.public_id),
            )
            continue

        values = {
            "risk_score.score": risk_score.score,
            "risk_score.risk_level": risk_score.risk_level,
            "risk_score.predicted_cases": risk_score.predicted_cases,
        }
        item_status = (
            InteroperabilityRunItem.STATUS_ACCEPTED
            if not missing_fields
            else InteroperabilityRunItem.STATUS_REJECTED
        )
        InteroperabilityRunItem.objects.create(
            run=run,
            row_number=0,
            external_identifier=org_mapping.external_identifier,
            internal_object_type=ExternalOrgUnitMapping.INTERNAL_WARD,
            internal_object_public_id=str(risk_score.ward.public_id),
            internal_object_code=risk_score.ward.ward_code,
            status=item_status,
            action=InteroperabilityRunItem.ACTION_EXPORT_RECORD,
            safe_context={
                "ward_public_id": str(risk_score.ward.public_id),
                "ward_code": risk_score.ward.ward_code,
                "risk_score_id": risk_score.id,
                "model_version": risk_score.model_version,
            },
            source_record_ref=f"risk_score:{risk_score.id}",
        )
        if missing_fields:
            continue

        data_values = [
            {
                "dataElement": data_elements[field].external_identifier,
                "value": values[field],
                "source_record_ref": f"risk_score:{risk_score.id}",
            }
            for field in REQUIRED_RISK_SCORE_EXPORT_FIELDS
        ]
        accepted += 1
        export_records.append(
            {
                "orgUnit": org_mapping.external_identifier,
                "period": risk_score.generated_at.strftime("%Y%m"),
                "dataValues": [
                    {
                        "dataElement": item["dataElement"],
                        "value": item["value"],
                    }
                    for item in data_values
                ],
                "metadata": {
                    "source_system": "cchis",
                    "schema_version": "cchis.v1",
                    "ward_public_id": str(risk_score.ward.public_id),
                    "ward_code": risk_score.ward.ward_code,
                    "risk_score_id": risk_score.id,
                    "mapping_version": mapping_version.version_label,
                },
            }
        )
        export_csv_rows.extend(
            [
                {
                    "period": risk_score.generated_at.strftime("%Y%m"),
                    "org_unit": org_mapping.external_identifier,
                    "data_element": item["dataElement"],
                    "value": item["value"],
                    "source_record_ref": item["source_record_ref"],
                }
                for item in data_values
            ]
        )

    run.records_seen = len(risk_scores)
    run.records_accepted = accepted
    run.records_rejected = rejected
    run.mapping_coverage = round((accepted / len(risk_scores)) * 100, 2) if risk_scores else 0.0
    run.export_payload = {
        "schema_version": "interoperability-export-preview-v1",
        "system": system.system_key,
        "exchange_type": InteroperabilityRun.EXCHANGE_AGGREGATE_REPORT_EXPORT,
        "records": export_records,
        "csv": {
            "filename": CSV_TEMPLATES[InteroperabilityRun.EXCHANGE_AGGREGATE_REPORT_EXPORT]["filename"],
            "columns": CSV_TEMPLATES[InteroperabilityRun.EXCHANGE_AGGREGATE_REPORT_EXPORT]["columns"],
            "rows": export_csv_rows,
        },
    }
    run.dry_run_preview = {
        "schema_version": "interoperability-export-preview-v1",
        "records_seen": run.records_seen,
        "records_accepted": run.records_accepted,
        "records_rejected": run.records_rejected,
        "mapping_coverage": run.mapping_coverage,
        "mapping_coverage_report": {
            "records_seen": run.records_seen,
            "records_with_resolved_mapping": run.records_accepted,
            "records_requiring_review": run.records_rejected,
            "coverage_percent": run.mapping_coverage,
        },
        "missing_required_fields": missing_fields,
        "confirmable": accepted > 0 and rejected == 0,
        "operator_confirmation_required": accepted > 0 and rejected == 0,
        "mutation_performed": False,
        "source_trace": [row["source_record_ref"] for row in export_csv_rows],
    }
    run.status = (
        InteroperabilityRun.STATUS_READY_FOR_CONFIRMATION
        if rejected == 0
        else InteroperabilityRun.STATUS_PARTIAL
    )
    run.error_summary = f"{rejected} export issue(s) require review." if rejected else ""
    run.completed_at = timezone.now()
    run.save(
        update_fields=[
            "records_seen",
            "records_accepted",
            "records_rejected",
            "mapping_coverage",
            "export_payload",
            "dry_run_preview",
            "status",
            "error_summary",
            "completed_at",
            "updated_at",
        ]
    )
    return run


@transaction.atomic
def create_interoperability_retry_run(*, run: InteroperabilityRun, operator) -> InteroperabilityRun:
    retry = InteroperabilityRun.objects.create(
        direction=run.direction,
        exchange_type=run.exchange_type,
        system=run.system,
        mapping_version=run.mapping_version,
        retry_of=run,
        status=InteroperabilityRun.STATUS_DRAFT,
        dry_run=True,
        source_file_name=run.source_file_name,
        endpoint_url=run.endpoint_url,
        operator=operator,
        connector_config=run.connector_config,
        lineage_metadata={
            "retry_created_from_public_id": str(run.public_id),
            "retry_created_from_status": run.status,
            "original_source_file_sha256": (run.lineage_metadata or {}).get("source_file_sha256", ""),
        },
    )
    return retry


def build_interoperability_error_file(run: InteroperabilityRun) -> dict[str, str | int]:
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["row_number", "external_identifier", "error_code", "field_path", "safe_message", "remediation_hint"])
    errors = run.errors.select_related("item").order_by("item__row_number", "id")
    for error in errors:
        item = error.item
        writer.writerow(
            [
                item.row_number if item else "",
                item.external_identifier if item else "",
                error.error_code,
                error.field_path,
                error.safe_message,
                error.remediation_hint,
            ]
        )
    payload = buffer.getvalue()
    return {
        "filename": f"interoperability-run-{run.public_id}-errors.csv",
        "content_type": "text/csv",
        "row_count": run.errors.count(),
        "payload": payload,
        "payload_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    }


def _user_can_view_interoperability_operational_details(user) -> bool:
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and (
            getattr(user, "is_superuser", False)
            or getattr(user, "role", None) in {User.ROLE_ADMIN, User.ROLE_SUPERVISOR}
        )
    )


def _system_payload(system: ExternalSystem, *, include_operational_details: bool = True) -> dict[str, Any]:
    return {
        "public_id": str(system.public_id),
        "system_key": system.system_key,
        "display_name": system.display_name,
        "system_type": system.system_type,
        "owner": system.owner,
        "default_exchange_format": system.default_exchange_format,
        "auth_config_reference": system.auth_config_reference if include_operational_details else "",
        "api_base_url": system.api_base_url if include_operational_details else "",
        "status": system.status,
        "created_at": system.created_at.isoformat(),
        "updated_at": system.updated_at.isoformat(),
    }


def _mapping_version_payload(version: InteroperabilityMappingVersion) -> dict[str, Any]:
    return {
        "public_id": str(version.public_id),
        "system_key": version.system.system_key,
        "version_label": version.version_label,
        "status": version.status,
        "effective_date": version.effective_date.isoformat(),
        "retired_at": version.retired_at.isoformat() if version.retired_at else None,
        "reviewed_by_username": version.reviewed_by.username if version.reviewed_by else "",
    }


def _org_mapping_payload(mapping: ExternalOrgUnitMapping) -> dict[str, Any]:
    return {
        "public_id": str(mapping.public_id),
        "system_key": mapping.system.system_key,
        "mapping_version": mapping.mapping_version.version_label,
        "external_identifier": mapping.external_identifier,
        "external_display_name": mapping.external_display_name,
        "internal_object_type": mapping.internal_object_type,
        "internal_object_public_id": mapping.internal_object_public_id,
        "internal_object_code": mapping.internal_object_code,
        "ward_name": mapping.ward.name if mapping.ward else "",
        "facility_name": mapping.facility.name if mapping.facility else "",
        "mapping_confidence": mapping.mapping_confidence,
        "status": mapping.status,
        "effective_date": mapping.effective_date.isoformat(),
        "retired_date": mapping.retired_date.isoformat() if mapping.retired_date else None,
    }


def _run_item_payload(item: InteroperabilityRunItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "row_number": item.row_number,
        "external_identifier": item.external_identifier,
        "internal_object_type": item.internal_object_type,
        "internal_object_public_id": item.internal_object_public_id,
        "internal_object_code": item.internal_object_code,
        "status": item.status,
        "action": item.action,
        "safe_context": item.safe_context,
        "source_record_ref": item.source_record_ref,
        "created_at": item.created_at.isoformat(),
    }


def _run_error_payload(error: InteroperabilityRunError) -> dict[str, Any]:
    return {
        "public_id": str(error.public_id),
        "item_id": error.item_id,
        "severity": error.severity,
        "error_code": error.error_code,
        "field_path": error.field_path,
        "safe_message": error.safe_message,
        "remediation_hint": error.remediation_hint,
        "created_at": error.created_at.isoformat(),
    }


def _analyst_safe_dry_run_preview(preview: dict[str, Any]) -> dict[str, Any]:
    allowed_keys = {
        "schema_version",
        "records_seen",
        "records_accepted",
        "records_rejected",
        "accepted_rows",
        "rejected_rows",
        "mapping_coverage",
        "mapping_coverage_report",
        "confirmable",
        "operator_confirmation_required",
        "confirmation_error",
        "mutation_allowed",
        "mutation_performed",
        "next_action",
        "missing_columns",
        "missing_required_fields",
    }
    return {key: value for key, value in (preview or {}).items() if key in allowed_keys}


def _run_payload(
    run: InteroperabilityRun,
    *,
    include_children: bool = True,
    include_operational_details: bool = True,
    include_child_keys: bool | None = None,
) -> dict[str, Any]:
    include_child_keys = include_children if include_child_keys is None else include_child_keys
    payload = {
        "public_id": str(run.public_id),
        "direction": run.direction,
        "exchange_type": run.exchange_type,
        "system_key": run.system.system_key,
        "system_name": run.system.display_name,
        "mapping_version": run.mapping_version.version_label if run.mapping_version else "",
        "retry_of": str(run.retry_of.public_id) if run.retry_of else None,
        "status": run.status,
        "dry_run": run.dry_run,
        "source_file_name": run.source_file_name if include_operational_details else "",
        "endpoint_url": run.endpoint_url if include_operational_details else "",
        "source_reference": interoperability_run_source_reference(run) if include_operational_details else "",
        "records_seen": run.records_seen,
        "records_accepted": run.records_accepted,
        "records_rejected": run.records_rejected,
        "mapping_coverage": run.mapping_coverage,
        "operator_username": run.operator.username if include_operational_details and run.operator else "",
        "error_summary": run.error_summary,
        "dry_run_preview": run.dry_run_preview if include_operational_details else _analyst_safe_dry_run_preview(run.dry_run_preview),
        "export_payload": run.export_payload if include_operational_details else {},
        "started_at": run.started_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "created_at": run.created_at.isoformat(),
        "contract_errors": validate_interoperability_run_record_contract(run),
    }
    if include_children:
        payload["items"] = [_run_item_payload(item) for item in run.items.all()[:25]]
        payload["errors"] = [_run_error_payload(error) for error in run.errors.all()[:25]]
    elif include_child_keys:
        payload["items"] = []
        payload["errors"] = []
    return payload


def build_interoperability_audit_checks() -> list[dict[str, Any]]:
    active_mapping_to_inactive = ExternalOrgUnitMapping.objects.filter(
        status=InteroperabilityMappingStatus.ACTIVE,
    ).filter(
        Q(ward__is_active=False) | Q(facility__is_active=False)
    )
    stale_export_runs = InteroperabilityRun.objects.filter(
        direction=InteroperabilityRun.DIRECTION_EXPORT,
        status__in=[
            InteroperabilityRun.STATUS_READY_FOR_CONFIRMATION,
            InteroperabilityRun.STATUS_COMPLETED,
        ],
    ).exclude(mapping_version__status=InteroperabilityMappingVersion.STATUS_ACTIVE)
    failed_without_summary = InteroperabilityRun.objects.filter(
        status=InteroperabilityRun.STATUS_FAILED,
        error_summary="",
    )
    retry_without_original = InteroperabilityRun.objects.filter(
        lineage_metadata__has_key="retry_created_from_public_id",
        retry_of__isnull=True,
    )
    accepted_without_mapping = InteroperabilityRunItem.objects.filter(
        status=InteroperabilityRunItem.STATUS_ACCEPTED,
        action=InteroperabilityRunItem.ACTION_EXPORT_RECORD,
        external_identifier="",
    )

    missing_required_data_elements = 0
    for version in InteroperabilityMappingVersion.objects.filter(
        status=InteroperabilityMappingVersion.STATUS_ACTIVE,
        retired_at__isnull=True,
    ).select_related("system"):
        mapped_fields = set(
            ExternalDataElementMapping.objects.filter(
                system=version.system,
                mapping_version=version,
                exchange_type=InteroperabilityRun.EXCHANGE_AGGREGATE_REPORT_EXPORT,
                status=InteroperabilityMappingStatus.ACTIVE,
                retired_date__isnull=True,
            ).values_list("internal_field", flat=True)
        )
        missing_required_data_elements += len(set(REQUIRED_RISK_SCORE_EXPORT_FIELDS) - mapped_fields)

    checks = [
        (
            "accepted_record_without_mapping",
            "Accepted record without mapping",
            accepted_without_mapping.count(),
            "Accepted export records must carry an external mapping identifier.",
        ),
        (
            "active_mapping_to_inactive_unit",
            "Active mapping to inactive ward/facility",
            active_mapping_to_inactive.count(),
            "Active mappings must not point to inactive local locations.",
        ),
        (
            "export_using_stale_mapping_version",
            "Export using stale mapping version",
            stale_export_runs.count(),
            "Export previews must use an active reviewed mapping version.",
        ),
        (
            "failed_run_without_error_summary",
            "Failed run without error summary",
            failed_without_summary.count(),
            "Failed runs must explain the failure without requiring logs.",
        ),
        (
            "retry_not_linked_to_original_run",
            "Retry not linked to original run",
            retry_without_original.count(),
            "Retries must retain a durable pointer to the original run.",
        ),
        (
            "required_data_element_mapping_missing",
            "Data-element mapping missing for required field",
            missing_required_data_elements,
            "Required aggregate export fields must have active external data-element mappings.",
        ),
    ]
    return [
        {
            "key": key,
            "title": title,
            "status": "PASS" if count == 0 else "FAIL",
            "count": count,
            "summary": summary,
        }
        for key, title, count, summary in checks
    ]


def build_interoperability_dashboard_snapshot(user=None) -> dict[str, Any]:
    include_operational_details = (
        True if user is None else _user_can_view_interoperability_operational_details(user)
    )
    systems = list(ExternalSystem.objects.order_by("system_key")[:50])
    versions = list(
        InteroperabilityMappingVersion.objects.select_related("system", "reviewed_by").order_by("-created_at")[:50]
    )
    org_mappings = list(
        ExternalOrgUnitMapping.objects.select_related("system", "mapping_version", "ward", "facility")
        .order_by("-updated_at")[:100]
    )
    runs = list(
        InteroperabilityRun.objects.select_related("system", "mapping_version", "operator", "retry_of")
        .prefetch_related("items", "errors")
        .order_by("-started_at", "-created_at")[:30]
    )
    run_status_counts = {
        item["status"]: item["count"]
        for item in InteroperabilityRun.objects.values("status").annotate(count=Count("id"))
    }
    latest_run = runs[0] if runs else None
    audit_checks = build_interoperability_audit_checks()
    return {
        "schema_version": INTEROPERABILITY_DASHBOARD_SCHEMA_VERSION,
        "generated_at": timezone.now().isoformat(),
        "exchange_inventory": EXCHANGE_INVENTORY,
        "exchange_inventory_contract_errors": validate_exchange_inventory_contract(),
        "csv_templates": CSV_TEMPLATES,
        "csv_template_contract_errors": validate_csv_template_contract(),
        "connector_boundary": CONNECTOR_BOUNDARY,
        "connector_boundary_contract_errors": validate_connector_boundary_contract(),
        "summary": {
            "system_count": len(systems),
            "active_system_count": ExternalSystem.objects.filter(status=ExternalSystem.STATUS_ACTIVE).count(),
            "mapping_version_count": InteroperabilityMappingVersion.objects.count(),
            "active_mapping_version_count": InteroperabilityMappingVersion.objects.filter(
                status=InteroperabilityMappingVersion.STATUS_ACTIVE,
                retired_at__isnull=True,
            ).count(),
            "org_unit_mapping_count": ExternalOrgUnitMapping.objects.count(),
            "active_org_unit_mapping_count": ExternalOrgUnitMapping.objects.filter(
                status=InteroperabilityMappingStatus.ACTIVE,
                retired_date__isnull=True,
            ).count(),
            "run_count": InteroperabilityRun.objects.count(),
            "failed_run_count": InteroperabilityRun.objects.filter(status=InteroperabilityRun.STATUS_FAILED).count(),
            "latest_run_at": latest_run.started_at.isoformat() if latest_run else None,
            "run_status_counts": run_status_counts,
            "audit_status": "pass" if all(check["status"] == "PASS" for check in audit_checks) else "fail",
        },
        "systems": [
            _system_payload(system, include_operational_details=include_operational_details)
            for system in systems
        ],
        "mapping_versions": [_mapping_version_payload(version) for version in versions],
        "org_unit_mappings": [_org_mapping_payload(mapping) for mapping in org_mappings],
        "runs": [
            _run_payload(
                run,
                include_children=include_operational_details,
                include_operational_details=include_operational_details,
                include_child_keys=True,
            )
            for run in runs
        ],
        "audit_checks": audit_checks,
    }


def build_interoperability_operational_kpi_feed(*, as_of_date: date | None = None) -> dict[str, Any]:
    latest_run = (
        InteroperabilityRun.objects.select_related("system", "mapping_version")
        .order_by("-started_at", "-created_at")
        .first()
    )
    audit_checks = build_interoperability_audit_checks()
    audit_failures = [check for check in audit_checks if check["status"] == "FAIL"]
    snapshot_date = (as_of_date or timezone.localdate()).isoformat()
    source_coverage_warnings = [
        {
            "metric_key": "interoperability_mapping_coverage",
            "warning": check["key"],
            "snapshot_key": f"interoperability-audit-{check['key']}",
            "snapshot_date": snapshot_date,
            "status": "AUDIT",
        }
        for check in audit_failures
    ]

    if latest_run and latest_run.status in {
        InteroperabilityRun.STATUS_FAILED,
        InteroperabilityRun.STATUS_PARTIAL,
    }:
        source_coverage_warnings.append(
            {
                "metric_key": "interoperability_mapping_coverage",
                "warning": "latest_interoperability_run_not_clean",
                "snapshot_key": str(latest_run.public_id),
                "snapshot_date": latest_run.started_at.date().isoformat(),
                "status": latest_run.status,
            }
        )

    return {
        "schema_version": "interoperability-operational-kpi-feed-v1",
        "generated_at": timezone.now().isoformat(),
        "audit_status": "pass" if not audit_failures else "fail",
        "latest_mapping_coverage": latest_run.mapping_coverage if latest_run else None,
        "latest_run": _run_payload(latest_run, include_children=False) if latest_run else None,
        "active_mapping_version_count": InteroperabilityMappingVersion.objects.filter(
            status=InteroperabilityMappingVersion.STATUS_ACTIVE,
            retired_at__isnull=True,
        ).count(),
        "active_org_unit_mapping_count": ExternalOrgUnitMapping.objects.filter(
            status=InteroperabilityMappingStatus.ACTIVE,
            retired_date__isnull=True,
        ).count(),
        "failed_run_count": InteroperabilityRun.objects.filter(status=InteroperabilityRun.STATUS_FAILED).count(),
        "audit_failures": audit_failures,
        "source_coverage_warnings": source_coverage_warnings,
    }
