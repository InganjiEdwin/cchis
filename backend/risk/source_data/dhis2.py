"""Read-only DHIS2 API interoperability for aggregate demonstration data.

The adapter in this module deliberately stops at a narrow boundary:

    DHIS2 API -> explicit UID mappings -> canonical CSV envelope
        -> source-data validation/import -> surveillance ingestion

It never sends a write request to DHIS2.  The API credentials are read from
runtime settings and are not copied into any persisted run metadata.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from io import StringIO
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit

import requests
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.utils import timezone
from requests.auth import HTTPBasicAuth

from risk.interoperability import get_or_create_external_system
from risk.models import (
    ExternalDataElementMapping,
    ExternalOrgUnitMapping,
    ExternalSystem,
    ExternalValueSetMapping,
    InteroperabilityMappingStatus,
    InteroperabilityMappingVersion,
    InteroperabilityRun,
    InteroperabilityRunError,
    InteroperabilityRunItem,
    SourceDataConnectorRun,
    SourceDataUploadBatch,
    SurveillanceIngestionRun,
    SurveillanceTruthLevel,
    Ward,
)
from risk.source_data.imports import run_confirmed_source_data_import
from risk.source_data.uploads import create_source_data_upload_batch
from risk.source_data.validation import validate_source_data_upload_batch


DHIS2_API_ADAPTER_KEY = "dhis2_api"
DHIS2_API_SCHEMA_VERSION = "dhis2-api-adapter-v1"
DHIS2_MAPPING_SCHEMA_VERSION = "dhis2-play-demo-crosswalk-v1"
DHIS2_DEFAULT_TIMEOUT_SECONDS = 30
DHIS2_DEFAULT_MAX_RETRIES = 2
DHIS2_MAX_PAGES = 10
DHIS2_MAX_DISCOVERY_ITEMS = 100
DHIS2_MAX_QUERY_UIDS = 25
DHIS2_MAX_QUERY_PAGE_SIZE = 100
DHIS2_MAX_QUERY_RECORDS = 500
DHIS2_MAX_QUERY_PERIOD_DAYS = 366
DHIS2_DEMO_TRUTH_LABELS = ("DEMO", "NON_OPERATIONAL")
DHIS2_DEMO_MAPPING_STATUSES = frozenset({"DEMO_ONLY", "NON_OPERATIONAL"})
DHIS2_VALUE_SET_KEY_CATEGORY_OPTION_COMBO = "dhis2_category_option_combo"
DHIS2_CANONICAL_FIELDS = {
    "suspected_cases",
    "confirmed_cases",
    "diarrheal_count",
    "proxy_case_count",
    "case_count",
}


class Dhis2Error(ValueError):
    """Base error whose string representation is safe for run metadata."""

    default_code = "dhis2_error"

    def __init__(self, message: str = "", *, code: str | None = None, retryable: bool = False):
        self.code = code or self.default_code
        self.retryable = retryable
        super().__init__(message)


class Dhis2ConfigurationError(Dhis2Error):
    default_code = "dhis2_configuration_invalid"


class Dhis2MappingError(Dhis2Error):
    default_code = "dhis2_mapping_invalid"


class Dhis2QueryScopeError(Dhis2MappingError):
    default_code = "dhis2_query_scope_invalid"


class Dhis2AuthenticationError(Dhis2Error):
    default_code = "dhis2_authentication_failed"


class Dhis2OperatorError(Dhis2Error):
    default_code = "dhis2_operator_invalid"


class Dhis2RequestError(Dhis2Error):
    default_code = "dhis2_request_failed"

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
        code: str | None = None,
    ):
        self.status_code = status_code
        super().__init__(message, code=code, retryable=retryable)


@dataclass(frozen=True)
class Dhis2OrgUnitMapping:
    external_identifier: str
    external_display_name: str
    cchis_ward_code: str
    cchis_ward_public_id: str
    status: str
    mapping_confidence: float


@dataclass(frozen=True)
class Dhis2DataElementMapping:
    external_identifier: str
    external_display_name: str
    canonical_field: str
    value_type: str
    status: str
    mapping_confidence: float


@dataclass(frozen=True)
class Dhis2CategoryOptionComboMapping:
    external_identifier: str
    internal_value: str
    external_label: str
    status: str


@dataclass(frozen=True)
class Dhis2Mapping:
    version_label: str
    mapping_status: str
    reviewer_status: str
    operational_eligible: bool
    system_key: str
    org_units: dict[str, Dhis2OrgUnitMapping]
    data_elements: dict[str, Dhis2DataElementMapping]
    category_option_combinations: dict[str, Dhis2CategoryOptionComboMapping]
    query: dict[str, Any]


@dataclass(frozen=True)
class Dhis2AggregateRow:
    data_element: str
    organisation_unit: str
    period: str
    value: str
    category_option_combo: str = ""
    indicator: str = ""


@dataclass
class Dhis2Transformation:
    rows: list[dict[str, str]]
    rejected_rows: list[dict[str, Any]]
    raw_record_count: int
    source_ref: str
    source_reference_hash: str
    query_hash: str
    period_start: date | None
    period_end: date | None
    mapped_record_count: int
    query_identity_hash: str
    response_payload_hash: str
    mapped_source_data_value_count: int
    rejected_source_data_value_count: int
    canonical_grouped_row_count: int
    validated_canonical_row_count: int = 0
    persisted_surveillance_record_count: int = 0
    correction_detected: bool = False
    correction_previous_ingestion_id: int | None = None


def _safe_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _safe_json(nested) for key, nested in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_json(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _stable_hash(value: Any) -> str:
    payload = json.dumps(_safe_json(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalise_query_value(value: Any) -> Any:
    """Normalise query values without retaining credential material or order noise."""

    if isinstance(value, dict):
        return {
            str(key).strip(): _normalise_query_value(nested)
            for key, nested in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (list, tuple)):
        values = [_normalise_query_value(item) for item in value]
        if all(isinstance(item, (str, int, float, bool)) or item is None for item in values):
            return sorted(values, key=lambda item: str(item))
        return values
    if isinstance(value, str):
        return value.strip()
    return _safe_json(value)


def _normalise_query_params(params: dict[str, Any]) -> dict[str, Any]:
    return {
        str(key).strip(): _normalise_query_value(value)
        for key, value in sorted(params.items(), key=lambda item: str(item[0]))
    }


def _param_values(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        values: list[str] = []
        for item in value:
            values.extend(_param_values(item))
        return values
    if value in (None, ""):
        return []
    return [part.strip() for part in re.split(r"[;,]", str(value)) if part.strip()]


def _dimension_tokens(value: Any) -> list[tuple[str, list[str]]]:
    tokens: list[tuple[str, list[str]]] = []
    raw_values: list[str] = []
    if isinstance(value, (list, tuple)):
        for item in value:
            raw_values.extend([part.strip() for part in str(item or "").split(",") if part.strip()])
    elif value not in (None, ""):
        raw_values.extend([part.strip() for part in str(value).split(",") if part.strip()])
    for token in raw_values:
        if ":" not in token:
            raise Dhis2QueryScopeError("DHIS2 analytics dimensions must use an explicit dimension prefix.")
        dimension, raw_uids = token.split(":", 1)
        dimension = dimension.strip().lower()
        uids = _param_values(raw_uids)
        if not dimension or not uids:
            raise Dhis2QueryScopeError("DHIS2 analytics dimensions must contain explicit UID values.")
        tokens.append((dimension, uids))
    return tokens


def _reject_wildcard_uids(uids: Iterable[str]) -> None:
    forbidden = {"*", "all", "user_orgunit", "user_orgunits", "user_orgunit_children"}
    for uid in uids:
        normalized = str(uid or "").strip().lower()
        if not normalized or normalized in forbidden or normalized.startswith(("level-", "ou_group-", "user_")):
            raise Dhis2QueryScopeError("DHIS2 query scope must use explicit UID values; wildcard or relative scope is not allowed.")


def _validate_explicit_periods(periods: list[str]) -> str:
    if len(periods) != 1:
        raise Dhis2QueryScopeError("DHIS2 query must contain exactly one explicit period.")
    period = periods[0].strip().upper()
    if re.search(r"relative|last_|this_|current|now|open|start|end", period, re.IGNORECASE):
        raise Dhis2QueryScopeError("DHIS2 query cannot use relative or open-ended periods.")
    try:
        period_start, period_end = parse_dhis2_period(period)
    except Dhis2Error as error:
        raise Dhis2QueryScopeError("DHIS2 query period is not a valid explicit bounded period.") from error
    if (period_end - period_start).days + 1 > DHIS2_MAX_QUERY_PERIOD_DAYS:
        raise Dhis2QueryScopeError("DHIS2 query period exceeds the configured bounded proof window.")
    return period


def validate_dhis2_query(query: dict[str, Any], mapping: Dhis2Mapping) -> dict[str, Any]:
    """Validate a small, explicit DHIS2 read scope before making any request."""

    if not isinstance(query, dict):
        raise Dhis2QueryScopeError("DHIS2 query must be an object.")
    resource = str(query.get("resource") or "").strip().strip("/")
    if resource not in {"analytics", "dataValueSets"}:
        raise Dhis2QueryScopeError("DHIS2 query resource must be analytics or dataValueSets.")
    params = query.get("params") or {}
    if not isinstance(params, dict) or not params:
        raise Dhis2QueryScopeError("DHIS2 query params must be a non-empty object.")
    params = _normalise_query_params(params)

    try:
        page_size = int(query.get("page_size") or params.get("pageSize") or 100)
    except (TypeError, ValueError) as error:
        raise Dhis2QueryScopeError("DHIS2 query page size must be a bounded integer.") from error
    if page_size <= 0 or page_size > DHIS2_MAX_QUERY_PAGE_SIZE:
        raise Dhis2QueryScopeError("DHIS2 query page size exceeds the configured safety limit.")

    if resource == "analytics":
        allowed_params = {
            "dimension",
            "page",
            "pageSize",
            "skipMeta",
            "displayProperty",
            "outputIdScheme",
            "tableLayout",
            "hideEmptyRows",
            "includeNumDen",
            "completedOnly",
            "hierarchyMeta",
        }
        unsupported = set(params) - allowed_params
        if unsupported:
            raise Dhis2QueryScopeError("DHIS2 analytics query contains unsupported parameters or dimensions.")
        tokens = _dimension_tokens(params.get("dimension"))
        by_dimension: dict[str, list[str]] = {}
        for dimension, uids in tokens:
            if dimension not in {"dx", "ou", "pe"}:
                raise Dhis2QueryScopeError("DHIS2 analytics query supports only dx, ou, and pe dimensions.")
            if dimension in by_dimension:
                raise Dhis2QueryScopeError("DHIS2 analytics query may specify each dimension only once.")
            _reject_wildcard_uids(uids)
            by_dimension[dimension] = uids
        if set(by_dimension) != {"dx", "ou", "pe"}:
            raise Dhis2QueryScopeError("DHIS2 analytics query must explicitly specify dx, ou, and pe dimensions.")
        periods = by_dimension["pe"]
        _validate_explicit_periods(periods)
        org_units = by_dimension["ou"]
        elements = by_dimension["dx"]
    else:
        allowed_params = {
            "dataSet",
            "dataElement",
            "orgUnit",
            "period",
            "attributeOptionCombo",
            "page",
            "pageSize",
        }
        unsupported = set(params) - allowed_params
        if unsupported:
            raise Dhis2QueryScopeError("DHIS2 dataValueSets query contains unsupported parameters or open-ended scope.")
        org_units = _param_values(params.get("orgUnit"))
        elements = _param_values(params.get("dataElement"))
        periods = _param_values(params.get("period"))
        _reject_wildcard_uids(org_units)
        _reject_wildcard_uids(elements)
        _reject_wildcard_uids(_param_values(params.get("dataSet")))
        _reject_wildcard_uids(_param_values(params.get("attributeOptionCombo")))
        if not org_units or not elements:
            raise Dhis2QueryScopeError("DHIS2 dataValueSets query must explicitly specify orgUnit and dataElement UIDs.")
        _validate_explicit_periods(periods)
        if len(_param_values(params.get("dataSet"))) > 1:
            raise Dhis2QueryScopeError("DHIS2 dataValueSets query may specify at most one dataSet UID.")

    additional_uids = []
    if resource == "dataValueSets":
        additional_uids.extend(_param_values(params.get("dataSet")))
        additional_uids.extend(_param_values(params.get("attributeOptionCombo")))
    if len(org_units) + len(elements) + len(additional_uids) > DHIS2_MAX_QUERY_UIDS:
        raise Dhis2QueryScopeError("DHIS2 query contains more UIDs than the configured proof scope limit.")
    if not set(org_units).issubset(mapping.org_units):
        raise Dhis2QueryScopeError("DHIS2 query organisation units must be a subset of the explicit mapping.")
    if not set(elements).issubset(mapping.data_elements):
        raise Dhis2QueryScopeError("DHIS2 query data elements or indicators must be a subset of the explicit mapping.")

    page_values = _param_values(params.get("page"))
    if page_values and page_values != ["1"]:
        raise Dhis2QueryScopeError("DHIS2 proof queries must start at page 1.")
    if "pageSize" in params and _param_values(params.get("pageSize")) != [str(page_size)]:
        raise Dhis2QueryScopeError("DHIS2 query pageSize must match the bounded page_size setting.")

    normalized_params = dict(params)
    if resource == "analytics":
        normalized_params["dimension"] = [
            f"{dimension}:{';'.join(sorted(uids))}"
            for dimension, uids in sorted(_dimension_tokens(params.get("dimension")))
        ]
    else:
        for key in ("orgUnit", "dataElement", "period", "dataSet", "attributeOptionCombo"):
            values = _param_values(normalized_params.get(key))
            if values:
                normalized_params[key] = ";".join(sorted(values))
    normalized_params["pageSize"] = page_size
    return {"resource": resource, "params": normalized_params, "page_size": page_size}


def _normalised_dhis2_rows(rows: Iterable[Dhis2AggregateRow]) -> list[dict[str, str]]:
    normalized = [
        {
            "organisation_unit": str(row.organisation_unit or "").strip(),
            "data_element": str(row.data_element or "").strip(),
            "indicator": str(row.indicator or "").strip(),
            "period": str(row.period or "").strip().upper(),
            "category_option_combo": str(row.category_option_combo or "").strip(),
            "value": str(row.value or "").strip(),
        }
        for row in rows
    ]
    return sorted(normalized, key=lambda row: tuple(row[field] for field in row))


def dhis2_response_payload_hash(rows: Iterable[Dhis2AggregateRow]) -> str:
    return _stable_hash(_normalised_dhis2_rows(rows))


def dhis2_query_identity_hash(
    *,
    instance_hostname: str,
    api_resource: str,
    query: dict[str, Any],
    mapping_version: str,
) -> str:
    return _stable_hash(
        {
            "instance_hostname": str(instance_hostname or "").strip().lower(),
            "api_resource": str(api_resource or "").strip().strip("/").lower(),
            "query": _normalise_query_value(query),
            "mapping_version": str(mapping_version or "").strip(),
        }
    )


def dhis2_failure_summary(error: Exception) -> dict[str, Any]:
    """Return a stable, credential-free failure summary for persisted metadata."""

    if isinstance(error, Dhis2Error):
        summary: dict[str, Any] = {
            "code": error.code,
            "retryable": bool(getattr(error, "retryable", False)),
        }
        status_code = getattr(error, "status_code", None)
        if status_code is not None:
            summary["status_code"] = int(status_code)
        return summary
    return {"code": "dhis2_unexpected_error", "retryable": False}


def resolve_dhis2_operator(username: str):
    """Resolve an active CCHIS administrative/data-operations operator."""

    normalized_username = str(username or "").strip()
    if not normalized_username:
        raise Dhis2OperatorError(
            "DHIS2 proof requires an accountable operator.",
            code="dhis2_operator_required",
        )
    from accounts.models import User

    try:
        operator = User.objects.get(username=normalized_username)
    except User.DoesNotExist as error:
        raise Dhis2OperatorError(
            "The requested CCHIS operator was not found.",
            code="dhis2_operator_not_found",
        ) from error
    if not operator.is_active:
        raise Dhis2OperatorError(
            "The requested CCHIS operator is inactive.",
            code="dhis2_operator_inactive",
        )
    if not (
        operator.is_superuser
        or operator.role in {User.ROLE_ADMIN, User.ROLE_SUPERVISOR}
    ):
        raise Dhis2OperatorError(
            "The requested CCHIS operator is not authorized for data operations.",
            code="dhis2_operator_unauthorized",
        )
    return operator


def _safe_hostname(url: str) -> str:
    parsed = urlsplit(str(url or "").strip())
    if not parsed.scheme or not parsed.hostname:
        return ""
    netloc = parsed.hostname
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    return netloc


def safe_instance_url(url: str) -> str:
    """Return an instance URL without userinfo, query strings, or fragments."""

    parsed = urlsplit(str(url or "").strip())
    if not parsed.scheme or not parsed.hostname:
        return ""
    netloc = parsed.hostname
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path.rstrip("/"), "", ""))


def _normalise_status(value: Any, *, default: str = InteroperabilityMappingStatus.ACTIVE) -> str:
    status = str(value or default).strip().upper()
    valid = {choice[0] for choice in InteroperabilityMappingStatus.choices}
    if status not in valid:
        raise Dhis2MappingError(f"Unsupported mapping status '{status}'.")
    return status


def _normalise_confidence(value: Any, *, default: float = 1.0) -> float:
    try:
        confidence = float(default if value in (None, "") else value)
    except (TypeError, ValueError) as error:
        raise Dhis2MappingError("Mapping confidence must be a decimal from 0 to 1.") from error
    if confidence < 0 or confidence > 1:
        raise Dhis2MappingError("Mapping confidence must be a decimal from 0 to 1.")
    return confidence


def _mapping_items(raw: Any, *, label: str) -> Iterable[tuple[str, dict[str, Any]]]:
    if not isinstance(raw, dict) or not raw:
        raise Dhis2MappingError(f"DHIS2 mapping must contain a non-empty {label} object.")
    for external_identifier, item in raw.items():
        if not isinstance(item, dict):
            raise Dhis2MappingError(f"Mapping for {external_identifier} must be an object.")
        identifier = str(external_identifier or "").strip()
        if not identifier:
            raise Dhis2MappingError(f"Mapping in {label} contains an empty external UID.")
        yield identifier, item


def load_dhis2_mapping(value: str | dict[str, Any], *, query: dict[str, Any] | None = None) -> Dhis2Mapping:
    """Parse a versioned UID-only mapping document.

    Location mappings deliberately accept a ward code or public ID only.  A
    display name is retained for audit context but is never used to resolve a
    CCHIS ward.
    """

    if isinstance(value, str):
        try:
            payload = json.loads(value)
        except json.JSONDecodeError as error:
            raise Dhis2MappingError("SOURCE_DATA_DHIS2_MAPPING_JSON is not valid JSON.") from error
    else:
        payload = value
    if not isinstance(payload, dict):
        raise Dhis2MappingError("DHIS2 mapping must be a JSON object.")

    version_label = str(payload.get("mapping_version") or payload.get("version_label") or "").strip()
    if not version_label:
        raise Dhis2MappingError("DHIS2 mapping_version is required.")
    if len(version_label) > 120:
        raise Dhis2MappingError("DHIS2 mapping_version must be 120 characters or fewer.")
    org_raw = payload.get("organisation_units") or payload.get("organization_units") or payload.get("org_units")
    element_raw = payload.get("data_elements") or payload.get("indicators")
    category_raw = payload.get("category_option_combinations") or {}

    org_units: dict[str, Dhis2OrgUnitMapping] = {}
    for external_identifier, item in _mapping_items(org_raw, label="organisation_units"):
        ward_code = str(item.get("cchis_ward_code") or item.get("internal_object_code") or "").strip()
        ward_public_id = str(item.get("cchis_ward_public_id") or item.get("internal_object_public_id") or "").strip()
        if not ward_code and not ward_public_id:
            raise Dhis2MappingError(
                f"DHIS2 org-unit {external_identifier} must specify cchis_ward_code or cchis_ward_public_id."
            )
        org_units[external_identifier] = Dhis2OrgUnitMapping(
            external_identifier=external_identifier,
            external_display_name=str(item.get("external_display_name") or item.get("name") or "").strip(),
            cchis_ward_code=ward_code,
            cchis_ward_public_id=ward_public_id,
            status=_normalise_status(item.get("status")),
            mapping_confidence=_normalise_confidence(item.get("mapping_confidence")),
        )

    data_elements: dict[str, Dhis2DataElementMapping] = {}
    for external_identifier, item in _mapping_items(element_raw, label="data_elements"):
        canonical_field = str(item.get("canonical_field") or item.get("internal_field") or "").strip()
        if canonical_field not in DHIS2_CANONICAL_FIELDS:
            raise Dhis2MappingError(
                f"DHIS2 data-element {external_identifier} maps to unsupported canonical field '{canonical_field}'."
            )
        data_elements[external_identifier] = Dhis2DataElementMapping(
            external_identifier=external_identifier,
            external_display_name=str(item.get("external_display_name") or item.get("name") or "").strip(),
            canonical_field=canonical_field,
            value_type=str(item.get("value_type") or "NUMBER").strip().upper(),
            status=_normalise_status(item.get("status")),
            mapping_confidence=_normalise_confidence(item.get("mapping_confidence")),
        )

    category_mappings: dict[str, Dhis2CategoryOptionComboMapping] = {}
    category_internal_values: set[str] = set()
    if category_raw:
        if not isinstance(category_raw, dict):
            raise Dhis2MappingError("category_option_combinations must be a JSON object.")
        for external_identifier, item in _mapping_items(category_raw, label="category_option_combinations"):
            internal_value = str(item.get("internal_value") or item.get("value") or "").strip()
            if not internal_value:
                raise Dhis2MappingError(
                    f"DHIS2 category-option-combination {external_identifier} must specify internal_value."
                )
            if internal_value in category_internal_values:
                raise Dhis2MappingError(
                    "DHIS2 category-option-combination mappings must use unique internal values."
                )
            category_internal_values.add(internal_value)
            category_mappings[external_identifier] = Dhis2CategoryOptionComboMapping(
                external_identifier=external_identifier,
                internal_value=internal_value,
                external_label=str(item.get("external_label") or item.get("name") or "").strip(),
                status=_normalise_status(item.get("status")),
            )

    query_payload = query if query is not None else payload.get("query")
    if not isinstance(query_payload, dict):
        raise Dhis2QueryScopeError("An explicit DHIS2 API query object is required.")

    mapping_status = str(payload.get("mapping_status") or payload.get("status") or "DEMO_ONLY").strip().upper()
    reviewer_status = str(payload.get("reviewer_status") or "DEMO_ONLY").strip().upper()
    operational_eligible = payload.get("operational_eligible", None)
    if operational_eligible is not False or not isinstance(operational_eligible, bool):
        raise Dhis2MappingError("DHIS2 Play proof mapping operational_eligible must be the JSON boolean false.")
    if mapping_status not in DHIS2_DEMO_MAPPING_STATUSES or reviewer_status not in DHIS2_DEMO_MAPPING_STATUSES:
        raise Dhis2MappingError("DHIS2 Play proof mapping must remain DEMO_ONLY or NON_OPERATIONAL.")

    # Query validation depends on the explicit UID mappings, so it is done
    # after the mapping document has been parsed.
    provisional_mapping = Dhis2Mapping(
        version_label=version_label,
        mapping_status=mapping_status,
        reviewer_status=reviewer_status,
        operational_eligible=False,
        system_key=str(payload.get("system_key") or "dhis2_play_demo").strip().lower(),
        org_units=org_units,
        data_elements=data_elements,
        category_option_combinations=category_mappings,
        query={},
    )
    normalized_query = validate_dhis2_query(query_payload, provisional_mapping)
    return Dhis2Mapping(**{**provisional_mapping.__dict__, "query": normalized_query})


def dhis2_mapping_from_settings() -> Dhis2Mapping:
    mapping_json = str(getattr(settings, "SOURCE_DATA_DHIS2_MAPPING_JSON", "") or "").strip()
    if not mapping_json:
        raise Dhis2ConfigurationError("SOURCE_DATA_DHIS2_MAPPING_JSON is not configured.")
    query_json = str(getattr(settings, "SOURCE_DATA_DHIS2_QUERY_JSON", "") or "").strip()
    query = None
    if query_json:
        try:
            query = json.loads(query_json)
        except json.JSONDecodeError as error:
            raise Dhis2ConfigurationError("SOURCE_DATA_DHIS2_QUERY_JSON is not valid JSON.") from error
    return load_dhis2_mapping(mapping_json, query=query)


def dhis2_api_configured() -> bool:
    base_url = str(getattr(settings, "SOURCE_DATA_DHIS2_BASE_URL", "") or "").strip()
    mapping_json = str(getattr(settings, "SOURCE_DATA_DHIS2_MAPPING_JSON", "") or "").strip()
    query_json = str(getattr(settings, "SOURCE_DATA_DHIS2_QUERY_JSON", "") or "").strip()
    pat = str(getattr(settings, "SOURCE_DATA_DHIS2_API_TOKEN", "") or "").strip()
    basic = bool(
        str(getattr(settings, "SOURCE_DATA_DHIS2_USERNAME", "") or "").strip()
        and str(getattr(settings, "SOURCE_DATA_DHIS2_PASSWORD", "") or "").strip()
    )
    return bool(base_url and mapping_json and query_json and (pat or basic))


def parse_dhis2_period(value: str) -> tuple[date, date]:
    """Convert supported DHIS2 period identifiers to inclusive dates."""

    period = str(value or "").strip().upper()
    if match := re.fullmatch(r"(\d{4})W(\d{2})", period):
        year, week = int(match.group(1)), int(match.group(2))
        try:
            start = date.fromisocalendar(year, week, 1)
        except ValueError as error:
            raise Dhis2MappingError(f"Invalid DHIS2 weekly period '{value}'.") from error
        return start, start + timedelta(days=6)
    if match := re.fullmatch(r"(\d{4})(\d{2})", period):
        year, month = int(match.group(1)), int(match.group(2))
        try:
            start = date(year, month, 1)
        except ValueError as error:
            raise Dhis2MappingError(f"Invalid DHIS2 monthly period '{value}'.") from error
        next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
        return start, next_month - timedelta(days=1)
    if match := re.fullmatch(r"(\d{4})Q([1-4])", period):
        year, quarter = int(match.group(1)), int(match.group(2))
        start_month = (quarter - 1) * 3 + 1
        start = date(year, start_month, 1)
        next_month = start_month + 3
        next_date = date(year + (next_month > 12), next_month - 12 if next_month > 12 else next_month, 1)
        return start, next_date - timedelta(days=1)
    if match := re.fullmatch(r"(\d{4})S([12])", period):
        year, half = int(match.group(1)), int(match.group(2))
        start = date(year, 1 if half == 1 else 7, 1)
        end = date(year, 6 if half == 1 else 12, 30 if half == 1 else 31)
        return start, end
    if match := re.fullmatch(r"(\d{4})", period):
        year = int(match.group(1))
        return date(year, 1, 1), date(year, 12, 31)
    if match := re.fullmatch(r"(\d{4})-?(\d{2})-?(\d{2})", period):
        try:
            point = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError as error:
            raise Dhis2MappingError(f"Invalid DHIS2 daily period '{value}'.") from error
        return point, point
    raise Dhis2MappingError(f"Unsupported or malformed DHIS2 period '{value}'.")


def _parse_count(value: Any) -> int:
    try:
        decimal_value = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError) as error:
        raise Dhis2MappingError("DHIS2 aggregate value must be a non-negative integer.") from error
    if decimal_value < 0 or decimal_value != decimal_value.to_integral_value():
        raise Dhis2MappingError("DHIS2 aggregate value must be a non-negative integer.")
    return int(decimal_value)


def _normalise_header(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _analytics_rows(payload: dict[str, Any]) -> list[Dhis2AggregateRow]:
    headers = payload.get("headers") or []
    raw_rows = payload.get("rows") or []
    if not isinstance(headers, list) or not isinstance(raw_rows, list):
        raise Dhis2RequestError(
            "DHIS2 analytics response did not contain rows and headers.",
            code="dhis2_response_invalid",
        )
    positions: dict[str, int] = {}
    for index, header in enumerate(headers):
        if not isinstance(header, dict):
            continue
        for candidate in (header.get("column"), header.get("name"), header.get("id")):
            normalized = _normalise_header(candidate)
            if normalized:
                positions.setdefault(normalized, index)

    def position(*names: str) -> int | None:
        for name in names:
            if _normalise_header(name) in positions:
                return positions[_normalise_header(name)]
        return None

    data_position = position("dx", "data", "dataelement", "indicator")
    org_position = position("ou", "organisationunit", "organizationunit", "orgunit")
    period_position = position("pe", "period")
    value_position = position("value", "val")
    category_position = position("co", "categoryoptioncombo", "categoryoptioncombination")
    if None in {data_position, org_position, period_position, value_position}:
        raise Dhis2RequestError(
            "DHIS2 analytics response is missing dx, ou, pe, or value columns.",
            code="dhis2_response_invalid",
        )

    result = []
    for raw_row in raw_rows:
        if not isinstance(raw_row, (list, tuple)):
            continue
        result.append(
            Dhis2AggregateRow(
                data_element=str(raw_row[data_position] if data_position < len(raw_row) else "").strip(),
                organisation_unit=str(raw_row[org_position] if org_position < len(raw_row) else "").strip(),
                period=str(raw_row[period_position] if period_position < len(raw_row) else "").strip(),
                value=str(raw_row[value_position] if value_position < len(raw_row) else "").strip(),
                category_option_combo=(
                    str(raw_row[category_position] if category_position is not None and category_position < len(raw_row) else "").strip()
                ),
                indicator="",
            )
        )
    return result


def _data_value_set_rows(payload: dict[str, Any]) -> list[Dhis2AggregateRow]:
    values = payload.get("dataValues") or []
    if not isinstance(values, list):
        raise Dhis2RequestError(
            "DHIS2 data-value-set response did not contain dataValues.",
            code="dhis2_response_invalid",
        )
    rows = []
    for item in values:
        if not isinstance(item, dict):
            continue
        rows.append(
            Dhis2AggregateRow(
                data_element=str(item.get("dataElement") or "").strip(),
                organisation_unit=str(item.get("orgUnit") or "").strip(),
                period=str(item.get("period") or "").strip(),
                value=str(item.get("value") if item.get("value") is not None else "").strip(),
                category_option_combo=str(item.get("categoryOptionCombo") or "").strip(),
                indicator="",
            )
        )
    return rows


class Dhis2Client:
    """Small authenticated GET-only DHIS2 client."""

    def __init__(
        self,
        base_url: str,
        *,
        username: str = "",
        password: str = "",
        api_token: str = "",
        timeout_seconds: int = DHIS2_DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DHIS2_DEFAULT_MAX_RETRIES,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = safe_instance_url(base_url)
        if not self.base_url:
            raise Dhis2ConfigurationError("SOURCE_DATA_DHIS2_BASE_URL must be an HTTPS or HTTP instance URL.")
        if urlsplit(self.base_url).scheme != "https" and not getattr(settings, "DEBUG", False):
            raise Dhis2ConfigurationError("DHIS2 credentials may only be used over HTTPS outside DEBUG mode.")
        self.username = username.strip()
        self.password = password
        self.api_token = api_token.strip()
        if not self.api_token and not (self.username and self.password):
            raise Dhis2ConfigurationError("Configure a DHIS2 API token or username/password pair.")
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.max_retries = max(0, min(int(max_retries), 5))
        self.session = session or requests.Session()
        self.request_receipts: list[dict[str, Any]] = []

    @property
    def instance_hostname(self) -> str:
        return _safe_hostname(self.base_url)

    @property
    def auth_scheme(self) -> str:
        return "api_token" if self.api_token else "basic"

    @property
    def safe_auth_metadata(self) -> dict[str, Any]:
        return {
            "auth_scheme": self.auth_scheme,
            "credential_values_exposed": False,
            "credential_material_present_in_persisted_evidence": False,
        }

    def api_url(self, resource: str) -> str:
        base = self.base_url.rstrip("/")
        api_root = base if base.endswith("/api") else f"{base}/api"
        return f"{api_root}/{str(resource or '').strip().lstrip('/')}"

    def _request_json(self, resource: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        headers = {"Accept": "application/json"}
        auth = None
        if self.api_token:
            headers["Authorization"] = f"ApiToken {self.api_token}"
        else:
            auth = HTTPBasicAuth(self.username, self.password)

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                request_url = self.api_url(resource)
                response = self.session.get(
                    request_url,
                    params=params or {},
                    headers=headers,
                    auth=auth,
                    timeout=self.timeout_seconds,
                    allow_redirects=False,
                )
            except requests.Timeout as error:
                last_error = error
                if attempt < self.max_retries:
                    continue
                raise Dhis2RequestError(
                    "DHIS2 API request timed out.",
                    retryable=True,
                    code="dhis2_timeout",
                ) from error
            except requests.RequestException as error:
                last_error = error
                if attempt < self.max_retries:
                    continue
                raise Dhis2RequestError(
                    "DHIS2 API request failed.",
                    retryable=True,
                    code="dhis2_connection_failed",
                ) from error

            self.request_receipts.append(
                {
                    "method": "GET",
                    "resource": str(resource or "").strip().strip("/"),
                    "status_code": int(response.status_code),
                    "retrieved_at": timezone.now().isoformat(),
                    "instance_hostname": self.instance_hostname,
                }
            )

            if response.status_code in {401, 403}:
                raise Dhis2AuthenticationError("DHIS2 API authentication failed.")
            if response.status_code == 429:
                if attempt < self.max_retries:
                    continue
                raise Dhis2RequestError(
                    "DHIS2 API rate limit reached.",
                    status_code=429,
                    retryable=True,
                    code="dhis2_rate_limited",
                )
            if response.status_code >= 500:
                if attempt < self.max_retries:
                    continue
                raise Dhis2RequestError(
                    "DHIS2 API returned a server error.",
                    status_code=response.status_code,
                    retryable=True,
                    code="dhis2_server_error",
                )
            if 300 <= response.status_code < 400:
                raise Dhis2RequestError(
                    "DHIS2 API redirects are not permitted for credentialed reads.",
                    status_code=response.status_code,
                    code="dhis2_response_invalid",
                )
            if response.status_code >= 400:
                raise Dhis2RequestError(
                    "DHIS2 API rejected the read request.",
                    status_code=response.status_code,
                    code="dhis2_response_invalid",
                )
            try:
                payload = response.json()
            except (TypeError, ValueError) as error:
                raise Dhis2RequestError(
                    "DHIS2 API returned malformed JSON.",
                    status_code=response.status_code,
                    code="dhis2_response_invalid",
                ) from error
            if not isinstance(payload, dict):
                raise Dhis2RequestError(
                    "DHIS2 API returned an unexpected JSON shape.",
                    status_code=response.status_code,
                    code="dhis2_response_invalid",
                )
            return payload
        raise Dhis2RequestError(
            "DHIS2 API request failed after retries.",
            retryable=True,
            code="dhis2_connection_failed",
        ) from last_error

    def get_json(self, resource: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request_json(resource, params=params)

    def get_paginated(
        self,
        resource: str,
        *,
        params: dict[str, Any],
        row_key: str,
        max_records: int = DHIS2_MAX_QUERY_RECORDS,
    ) -> list[dict[str, Any]]:
        current_params = dict(params)
        pages: list[dict[str, Any]] = []
        record_count = 0
        page = int(current_params.get("page") or 1)
        for _ in range(DHIS2_MAX_PAGES):
            payload = self.get_json(resource, params=current_params)
            pages.append(payload)
            page_rows = payload.get(row_key) or []
            if not isinstance(page_rows, list):
                raise Dhis2RequestError(
                    "DHIS2 API paginated response has an invalid row collection.",
                    code="dhis2_response_invalid",
                )
            record_count += len(page_rows)
            if record_count > max_records:
                raise Dhis2QueryScopeError("DHIS2 API response exceeded the configured record limit.")
            pager = payload.get("pager") or {}
            if not isinstance(pager, dict):
                break
            page_count = int(pager.get("pageCount") or page)
            current_page = int(pager.get("page") or page)
            if current_page >= page_count:
                break
            page = current_page + 1
            current_params["page"] = page
            if "pageSize" in pager and "pageSize" not in current_params:
                current_params["pageSize"] = pager["pageSize"]
        else:
            raise Dhis2RequestError("DHIS2 API pagination exceeded the configured safety limit.")
        return pages

    def discover(self, mapping: Dhis2Mapping) -> dict[str, Any]:
        receipt_start = len(self.request_receipts)
        me = self.get_json("me", params={"fields": "id,displayName,userCredentials[username]"})
        system_info = self.get_json("system/info")
        organisation_units = []
        for uid in list(mapping.org_units)[:DHIS2_MAX_DISCOVERY_ITEMS]:
            item = self.get_json(
                f"organisationUnits/{uid}",
                params={"fields": "id,name,level,parent[id,name]"},
            )
            if str(item.get("id") or "").strip() != uid:
                raise Dhis2MappingError(
                    "DHIS2 discovery returned an organisation-unit UID different from the explicit mapping.",
                    code="dhis2_discovery_uid_mismatch",
                )
            organisation_units.append(item)
        data_elements = []
        for uid, element_mapping in list(mapping.data_elements.items())[:DHIS2_MAX_DISCOVERY_ITEMS]:
            resource = "indicators" if element_mapping.value_type == "INDICATOR" else "dataElements"
            item = self.get_json(
                f"{resource}/{uid}",
                params={"fields": "id,name,valueType,aggregationType"},
            )
            if str(item.get("id") or "").strip() != uid:
                raise Dhis2MappingError(
                    "DHIS2 discovery returned an element or indicator UID different from the explicit mapping.",
                    code="dhis2_discovery_uid_mismatch",
                )
            data_elements.append(item)
        return {
            "me": {
                "id": str(me.get("id") or ""),
                "displayName": str(me.get("displayName") or ""),
                "username_present": bool((me.get("userCredentials") or {}).get("username")),
            },
            "server_version": str(
                system_info.get("version")
                or system_info.get("systemVersion")
                or system_info.get("revision")
                or "unknown"
            ),
            "organisation_units": organisation_units,
            "data_elements": data_elements,
            "http_receipts": [dict(receipt) for receipt in self.request_receipts[receipt_start:]],
        }

    def fetch_aggregate(self, query: dict[str, Any]) -> tuple[list[Dhis2AggregateRow], dict[str, Any]]:
        resource = query["resource"]
        params = dict(query["params"])
        params.setdefault("pageSize", query["page_size"])
        receipt_start = len(self.request_receipts)
        payloads = self.get_paginated(
            resource,
            params=params,
            row_key="rows" if resource == "analytics" else "dataValues",
            max_records=DHIS2_MAX_QUERY_RECORDS,
        )
        rows: list[Dhis2AggregateRow] = []
        for payload in payloads:
            rows.extend(_analytics_rows(payload) if resource == "analytics" else _data_value_set_rows(payload))
        receipts = [dict(receipt) for receipt in self.request_receipts[receipt_start:]]
        for receipt in receipts:
            receipt["page_count"] = len(payloads)
        return rows, {
            "resource": resource,
            "params": _normalise_query_params(params),
            "page_count": len(payloads),
            "record_count": len(rows),
            "http_receipts": receipts,
            "http_status": receipts[-1]["status_code"] if receipts else None,
        }


def dhis2_client_from_settings() -> Dhis2Client:
    return Dhis2Client(
        str(getattr(settings, "SOURCE_DATA_DHIS2_BASE_URL", "") or "").strip(),
        username=str(getattr(settings, "SOURCE_DATA_DHIS2_USERNAME", "") or "").strip(),
        password=str(getattr(settings, "SOURCE_DATA_DHIS2_PASSWORD", "") or ""),
        api_token=str(getattr(settings, "SOURCE_DATA_DHIS2_API_TOKEN", "") or "").strip(),
        timeout_seconds=int(getattr(settings, "SOURCE_DATA_DHIS2_TIMEOUT_SECONDS", DHIS2_DEFAULT_TIMEOUT_SECONDS)),
        max_retries=int(getattr(settings, "SOURCE_DATA_DHIS2_MAX_RETRIES", DHIS2_DEFAULT_MAX_RETRIES)),
    )


def transform_dhis2_rows(
    rows: list[Dhis2AggregateRow],
    *,
    mapping: Dhis2Mapping,
    instance_hostname: str,
    query_metadata: dict[str, Any],
    retrieved_at: str | None = None,
    connector_run_id: int | None = None,
) -> Dhis2Transformation:
    """Turn DHIS2 aggregate rows into the canonical surveillance CSV envelope."""

    retrieved_at = retrieved_at or timezone.now().isoformat()
    normalized_query = {
        "resource": query_metadata.get("resource"),
        "params": _normalise_query_params(query_metadata.get("params") or {}),
        "page_size": query_metadata.get("page_size") or (query_metadata.get("params") or {}).get("pageSize"),
    }
    query_identity_hash = dhis2_query_identity_hash(
        instance_hostname=instance_hostname,
        api_resource=str(query_metadata.get("resource") or ""),
        query=normalized_query,
        mapping_version=mapping.version_label,
    )
    # Keep the old field name as a compatibility alias.  It now contains the
    # query identity only; response content is represented separately.
    query_hash = query_identity_hash
    source_reference_hash = query_identity_hash
    response_payload_hash = dhis2_response_payload_hash(rows)
    source_ref = f"dhis2-api:{instance_hostname}:query:{query_identity_hash[:32]}"

    grouped: dict[tuple[str, date, date, str], dict[str, Any]] = {}
    rejected: list[dict[str, Any]] = []
    mapped_source_data_value_count = 0
    for row_number, aggregate in enumerate(rows, start=1):
        identity = {
            "row_number": row_number,
            "dhis2_org_unit_id": aggregate.organisation_unit,
            "dhis2_data_element_id": aggregate.data_element,
            "dhis2_category_option_combo": aggregate.category_option_combo,
            "dhis2_period": aggregate.period,
        }
        org_mapping = mapping.org_units.get(aggregate.organisation_unit)
        element_mapping = mapping.data_elements.get(aggregate.data_element)
        if org_mapping is None:
            rejected.append({**identity, "code": "unknown_organisation_unit"})
            continue
        if element_mapping is None:
            rejected.append({**identity, "code": "unknown_data_element"})
            continue
        if (
            aggregate.category_option_combo
            and aggregate.category_option_combo not in mapping.category_option_combinations
        ):
            rejected.append({**identity, "code": "unknown_category_option_combo"})
            continue
        try:
            period_start, period_end = parse_dhis2_period(aggregate.period)
            count_value = _parse_count(aggregate.value)
        except Dhis2MappingError as error:
            rejected.append({**identity, "code": "invalid_period_or_value", "detail": str(error)})
            continue

        group_key = (org_mapping.external_identifier, period_start, period_end, aggregate.category_option_combo)
        group = grouped.setdefault(
            group_key,
            {
                "org_mapping": org_mapping,
                "period_start": period_start,
                "period_end": period_end,
                "category_option_combo": aggregate.category_option_combo,
                "counts": {},
                "data_element_ids": {},
                "raw_rows": [],
            },
        )
        canonical_field = element_mapping.canonical_field
        if canonical_field in group["counts"]:
            rejected.append({**identity, "code": "duplicate_canonical_field_for_period"})
            continue
        group["counts"][canonical_field] = count_value
        group["data_element_ids"][canonical_field] = aggregate.data_element
        group["raw_rows"].append(identity)
        mapped_source_data_value_count += 1

    output_rows: list[dict[str, str]] = []
    period_starts: list[date] = []
    period_ends: list[date] = []
    for row_number, group in enumerate(grouped.values(), start=1):
        org_mapping: Dhis2OrgUnitMapping = group["org_mapping"]
        period_start: date = group["period_start"]
        period_end: date = group["period_end"]
        period_starts.append(period_start)
        period_ends.append(period_end)
        data_element_ids = sorted(set(group["data_element_ids"].values()))
        row_identity_hash = _stable_hash(
            {
                "query_identity_hash": query_identity_hash,
                "org_unit": org_mapping.external_identifier,
                "data_elements": data_element_ids,
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "category_option_combo": group["category_option_combo"],
            }
        )
        canonical_row_hash = _stable_hash(
            {
                "row_identity_hash": row_identity_hash,
                "org_unit": org_mapping.external_identifier,
                "data_elements": data_element_ids,
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "category_option_combo": group["category_option_combo"],
                "counts": group["counts"],
            }
        )
        row_source_ref = f"{source_ref}:row:{canonical_row_hash[:24]}"
        provider_data_elements = ",".join(data_element_ids)
        row: dict[str, str] = {
            "ward_code": org_mapping.cchis_ward_code,
            "reporting_period_start": period_start.isoformat(),
            "reporting_period_end": period_end.isoformat(),
            "reporting_granularity": "week" if (period_end - period_start).days == 6 else "day",
            "source_ref": row_source_ref,
            "source_system": "dhis2",
            "provider": "dhis2",
            "provider_org_unit_id": org_mapping.external_identifier,
            "provider_data_element_id": provider_data_elements,
            "dhis2_period": str(group["raw_rows"][0]["dhis2_period"]),
            "dhis2_org_unit_id": org_mapping.external_identifier,
            "dhis2_data_element_id": provider_data_elements,
            "dhis2_category_option_combo": group["category_option_combo"],
            "dhis2_instance_hostname": instance_hostname,
            "dhis2_api_resource": str(query_metadata.get("resource") or ""),
            "dhis2_query_hash": query_hash,
            "dhis2_source_reference_hash": source_reference_hash,
            "dhis2_query_identity_hash": query_identity_hash,
            "dhis2_response_payload_hash": response_payload_hash,
            "dhis2_row_identity_hash": row_identity_hash,
            "dhis2_retrieved_at": retrieved_at,
            "dhis2_mapping_version": mapping.version_label,
            "dhis2_connector_run_id": str(connector_run_id or ""),
            "truth_level": SurveillanceTruthLevel.SEEDED_DEMO,
            "source_kind": "seeded",
            "notes": (
                "DEMO; NON_OPERATIONAL; official DHIS2 Play aggregate demonstration data; "
                "not Kenya or Migori surveillance truth; mapping is a demonstration crosswalk."
            ),
        }
        for field_name in DHIS2_CANONICAL_FIELDS:
            if field_name in group["counts"]:
                row[field_name] = str(group["counts"][field_name])
        output_rows.append(row)

    return Dhis2Transformation(
        rows=output_rows,
        rejected_rows=rejected,
        raw_record_count=len(rows),
        source_ref=source_ref,
        source_reference_hash=source_reference_hash,
        query_hash=query_hash,
        period_start=min(period_starts) if period_starts else None,
        period_end=max(period_ends) if period_ends else None,
        mapped_record_count=len(output_rows),
        query_identity_hash=query_identity_hash,
        response_payload_hash=response_payload_hash,
        mapped_source_data_value_count=mapped_source_data_value_count,
        rejected_source_data_value_count=len(rejected),
        canonical_grouped_row_count=len(output_rows),
    )


def _resolve_demo_ward(mapping: Dhis2OrgUnitMapping) -> Ward | None:
    if mapping.cchis_ward_public_id:
        return Ward.objects.filter(public_id=mapping.cchis_ward_public_id, is_active=True).first()
    if mapping.cchis_ward_code:
        return Ward.objects.filter(ward_code=mapping.cchis_ward_code, is_active=True).first()
    return None


@transaction.atomic
def persist_dhis2_mapping_set(
    *,
    mapping: Dhis2Mapping,
    client: Dhis2Client,
    operator=None,
) -> tuple[ExternalSystem, InteroperabilityMappingVersion, list[dict[str, Any]]]:
    system = get_or_create_external_system(mapping.system_key)
    system.display_name = "DHIS2 Play demo (read-only)"
    system.system_type = ExternalSystem.SYSTEM_DHIS2
    system.owner = "dhis2_play_demo"
    system.default_exchange_format = "DHIS2_API"
    system.auth_config_reference = (
        "env://SOURCE_DATA_DHIS2_API_TOKEN" if client.api_token else "env://SOURCE_DATA_DHIS2_USERNAME_PASSWORD"
    )
    system.api_base_url = client.base_url
    system.lineage_metadata = {
        **(system.lineage_metadata or {}),
        "adapter_key": DHIS2_API_ADAPTER_KEY,
        "instance_hostname": client.instance_hostname,
        "read_only": True,
        "demo_only": True,
        "operational_eligible": False,
        "credential_material_present_in_persisted_evidence": False,
    }
    system.save(
        update_fields=[
            "display_name",
            "system_type",
            "owner",
            "default_exchange_format",
            "auth_config_reference",
            "api_base_url",
            "lineage_metadata",
            "updated_at",
        ]
    )

    version, _created = InteroperabilityMappingVersion.objects.get_or_create(
        system=system,
        version_label=mapping.version_label,
        defaults={
            "status": InteroperabilityMappingVersion.STATUS_DRAFT,
            "reviewed_by": operator,
            "lineage_metadata": {},
        },
    )
    version.status = InteroperabilityMappingVersion.STATUS_DRAFT
    version.reviewed_by = operator
    version.retired_at = None
    version.lineage_metadata = {
        "schema_version": DHIS2_MAPPING_SCHEMA_VERSION,
        "mapping_status": mapping.mapping_status,
        "reviewer_status": mapping.reviewer_status,
        "operational_eligible": mapping.operational_eligible,
        "scope": "DEMO_ONLY",
        "demo_truth_labels": list(DHIS2_DEMO_TRUTH_LABELS),
        "source_instance_hostname": client.instance_hostname,
        "category_option_combinations": {
            key: {
                "internal_value": value.internal_value,
                "external_label": value.external_label,
                "status": value.status,
            }
            for key, value in mapping.category_option_combinations.items()
        },
    }
    version.save(update_fields=["status", "reviewed_by", "retired_at", "lineage_metadata", "updated_at"])

    mapping_errors: list[dict[str, Any]] = []
    for external_identifier, org_mapping in mapping.org_units.items():
        ward = _resolve_demo_ward(org_mapping)
        if ward is None:
            mapping_errors.append({"code": "cchis_demo_ward_not_found", "external_identifier": external_identifier})
            continue
        ExternalOrgUnitMapping.objects.update_or_create(
            system=system,
            mapping_version=version,
            external_identifier=external_identifier,
            defaults={
                "external_display_name": org_mapping.external_display_name,
                "internal_object_type": ExternalOrgUnitMapping.INTERNAL_WARD,
                "internal_object_public_id": str(ward.public_id),
                "internal_object_code": ward.ward_code,
                "ward": ward,
                "facility": None,
                "mapping_confidence": org_mapping.mapping_confidence,
                "status": InteroperabilityMappingStatus.NEEDS_REVIEW,
                "effective_date": timezone.localdate(),
                "retired_date": None,
                "reviewed_by": operator,
                "lineage_metadata": {
                    "schema_version": DHIS2_MAPPING_SCHEMA_VERSION,
                    "demo_only": True,
                    "operational_eligible": False,
                    "source_instance_hostname": client.instance_hostname,
                    "scope": "DEMO_ONLY",
                },
            },
        )

    for external_identifier, element_mapping in mapping.data_elements.items():
        ExternalDataElementMapping.objects.update_or_create(
            system=system,
            mapping_version=version,
            exchange_type=InteroperabilityRun.EXCHANGE_SURVEILLANCE_CASE_COUNT_IMPORT,
            internal_field=element_mapping.canonical_field,
            defaults={
                "external_identifier": external_identifier,
                "external_display_name": element_mapping.external_display_name,
                "value_type": "NUMBER",
                "required_for_exchange": False,
                "mapping_confidence": element_mapping.mapping_confidence,
                "status": InteroperabilityMappingStatus.NEEDS_REVIEW,
                "effective_date": timezone.localdate(),
                "retired_date": None,
                "reviewed_by": operator,
                "lineage_metadata": {
                    "schema_version": DHIS2_MAPPING_SCHEMA_VERSION,
                    "demo_only": True,
                    "operational_eligible": False,
                    "source_instance_hostname": client.instance_hostname,
                    "scope": "DEMO_ONLY",
                },
            },
        )

    for external_identifier, value_mapping in mapping.category_option_combinations.items():
        if not value_mapping.internal_value:
            mapping_errors.append(
                {
                    "code": "dhis2_category_mapping_invalid",
                    "external_identifier": external_identifier,
                }
            )
            continue
        ExternalValueSetMapping.objects.update_or_create(
            system=system,
            mapping_version=version,
            value_set_key=DHIS2_VALUE_SET_KEY_CATEGORY_OPTION_COMBO,
            internal_value=value_mapping.internal_value,
            defaults={
                "external_value": external_identifier,
                "external_label": value_mapping.external_label,
                "internal_label": value_mapping.internal_value,
                "mapping_confidence": 1.0,
                "status": InteroperabilityMappingStatus.NEEDS_REVIEW,
                "effective_date": timezone.localdate(),
                "retired_date": None,
                "reviewed_by": operator,
                "lineage_metadata": {
                    "schema_version": DHIS2_MAPPING_SCHEMA_VERSION,
                    "demo_only": True,
                    "scope": "DEMO_ONLY",
                    "operational_eligible": False,
                    "source_instance_hostname": client.instance_hostname,
                },
            },
        )
    return system, version, mapping_errors


def _canonical_csv(rows: list[dict[str, str]]) -> str:
    columns = [
        "ward_code",
        "reporting_period_start",
        "reporting_period_end",
        "reporting_granularity",
        "suspected_cases",
        "confirmed_cases",
        "diarrheal_count",
        "proxy_case_count",
        "case_count",
        "source_ref",
        "source_system",
        "provider",
        "provider_org_unit_id",
        "provider_data_element_id",
        "dhis2_period",
        "dhis2_org_unit_id",
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
        "correction_reason",
        "revision_number",
        "supersedes_record_ref",
        "truth_level",
        "source_kind",
        "notes",
    ]
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _safe_query_metadata(query_metadata: dict[str, Any]) -> dict[str, Any]:
    def safe_receipts(values: Any) -> list[dict[str, Any]]:
        receipts = []
        for receipt in values or []:
            if not isinstance(receipt, dict):
                continue
            receipts.append(
                {
                    "method": "GET",
                    "resource": str(receipt.get("resource") or ""),
                    "status_code": receipt.get("status_code"),
                    "page_count": receipt.get("page_count"),
                    "retrieved_at": receipt.get("retrieved_at"),
                    "instance_hostname": receipt.get("instance_hostname") or "",
                }
            )
        return receipts

    receipts = safe_receipts(query_metadata.get("http_receipts"))
    discovery_receipts = safe_receipts(query_metadata.get("discovery_http_receipts"))
    return {
        "resource": query_metadata.get("resource"),
        "params": _normalise_query_params(query_metadata.get("params") or {}),
        "page_size": query_metadata.get("page_size") or (query_metadata.get("params") or {}).get("pageSize"),
        "page_count": query_metadata.get("page_count"),
        "record_count": query_metadata.get("record_count"),
        "http_status": query_metadata.get("http_status"),
        "http_receipts": receipts,
        "discovery_http_receipts": discovery_receipts,
    }


def _create_interoperability_run(
    *,
    system: ExternalSystem,
    mapping_version: InteroperabilityMappingVersion,
    transformation: Dhis2Transformation,
    query_metadata: dict[str, Any],
    discovery: dict[str, Any],
    client: Dhis2Client,
    operator=None,
) -> InteroperabilityRun:
    run = InteroperabilityRun.objects.create(
        direction=InteroperabilityRun.DIRECTION_IMPORT,
        exchange_type=InteroperabilityRun.EXCHANGE_SURVEILLANCE_CASE_COUNT_IMPORT,
        system=system,
        mapping_version=mapping_version,
        status=InteroperabilityRun.STATUS_DRAFT,
        dry_run=False,
        endpoint_url=client.api_url(str(query_metadata.get("resource") or ""))[:500],
        operator=operator,
        connector_config={
            "schema_version": DHIS2_API_SCHEMA_VERSION,
            "transport": DHIS2_API_ADAPTER_KEY,
            "read_only": True,
            "auth_scheme": client.auth_scheme,
            "credential_values_exposed": False,
            "credential_material_present_in_persisted_evidence": False,
            "canonical_csv_fallback_available": True,
            "mapping_scope": "DEMO_ONLY",
        },
        lineage_metadata={
            "schema_version": DHIS2_API_SCHEMA_VERSION,
            "source_reference": transformation.source_ref,
            "source_reference_hash": transformation.source_reference_hash,
            "query_hash": transformation.query_hash,
            "query_identity_hash": transformation.query_identity_hash,
            "response_payload_hash": transformation.response_payload_hash,
            "instance_hostname": client.instance_hostname,
            "api_resource": query_metadata.get("resource"),
            "query_parameters": _safe_json(query_metadata.get("params") or {}),
            "retrieved_at": (discovery.get("retrieved_at") or timezone.now().isoformat()),
            "dhis2_server_version": discovery.get("server_version") or "unknown",
            "mapping_version": mapping_version.version_label,
            "truth_classification": list(DHIS2_DEMO_TRUTH_LABELS),
            "production_eligible": False,
            "canonical_path": "dhis2_api_response -> canonical_validation -> source_data_import -> surveillance_ingestion",
            "credential_material_present_in_persisted_evidence": False,
            "http_evidence": _safe_query_metadata(query_metadata),
            "mapping_scope": "DEMO_ONLY",
        },
    )
    for row_number, row in enumerate(transformation.rows, start=1):
        external_identifier = ":".join(
            [
                row.get("dhis2_org_unit_id", ""),
                row.get("dhis2_data_element_id", ""),
                row.get("dhis2_period", ""),
                row.get("dhis2_category_option_combo", ""),
            ]
        )[:160]
        InteroperabilityRunItem.objects.create(
            run=run,
            row_number=row_number,
            external_identifier=external_identifier,
            internal_object_type=ExternalOrgUnitMapping.INTERNAL_WARD,
            internal_object_code=row.get("ward_code", ""),
            status=InteroperabilityRunItem.STATUS_ACCEPTED,
            action=InteroperabilityRunItem.ACTION_NOOP,
            safe_context={
                "dhis2_org_unit_id": row.get("dhis2_org_unit_id", ""),
                "dhis2_data_element_id": row.get("dhis2_data_element_id", ""),
                "dhis2_category_option_combo": row.get("dhis2_category_option_combo", ""),
                "dhis2_period": row.get("dhis2_period", ""),
                "canonical_field_values": {
                    field: row[field] for field in DHIS2_CANONICAL_FIELDS if row.get(field, "") != ""
                },
                "truth_classification": list(DHIS2_DEMO_TRUTH_LABELS),
            },
            source_record_ref=row.get("source_ref") or f"{transformation.source_ref}:row:{row_number}",
        )
    for offset, rejected in enumerate(transformation.rejected_rows, start=len(transformation.rows) + 1):
        item = InteroperabilityRunItem.objects.create(
            run=run,
            row_number=int(rejected.get("row_number") or offset),
            external_identifier=str(
                rejected.get("dhis2_data_element_id") or rejected.get("dhis2_org_unit_id") or ""
            )[:160],
            internal_object_type=ExternalOrgUnitMapping.INTERNAL_WARD,
            status=(
                InteroperabilityRunItem.STATUS_UNMAPPED
                if str(rejected.get("code") or "").startswith("unknown_")
                else InteroperabilityRunItem.STATUS_REJECTED
            ),
            action=InteroperabilityRunItem.ACTION_NOOP,
            safe_context={
                key: rejected.get(key)
                for key in (
                    "dhis2_org_unit_id",
                    "dhis2_data_element_id",
                    "dhis2_category_option_combo",
                    "dhis2_period",
                    "code",
                )
                if rejected.get(key) not in (None, "")
            },
            source_record_ref=f"{transformation.source_ref}:rejected:{offset}",
        )
        InteroperabilityRunError.objects.create(
            run=run,
            item=item,
            severity=InteroperabilityRunError.SEVERITY_ERROR,
            error_code=str(rejected.get("code") or "dhis2_row_rejected"),
            field_path="dhis2_response",
            safe_message="DHIS2 aggregate row was rejected by the explicit mapping contract.",
            remediation_hint="Review the published DHIS2 UID mapping and query scope.",
            raw_value_digest=_stable_hash(item.safe_context),
        )
    run.records_seen = transformation.raw_record_count
    run.records_accepted = transformation.mapped_source_data_value_count
    run.records_rejected = transformation.rejected_source_data_value_count
    run.mapping_coverage = (
        round((transformation.mapped_source_data_value_count / transformation.raw_record_count) * 100, 2)
        if transformation.raw_record_count
        else 0.0
    )
    run.dry_run_preview = {
        "schema_version": "dhis2-api-import-preview-v1",
        "source_record_count": transformation.raw_record_count,
        "mapped_record_count": transformation.mapped_source_data_value_count,
        "rejected_record_count": transformation.rejected_source_data_value_count,
        "counts": {
            "source_data_value_count": transformation.raw_record_count,
            "mapped_source_data_value_count": transformation.mapped_source_data_value_count,
            "rejected_source_data_value_count": transformation.rejected_source_data_value_count,
            "canonical_grouped_row_count": transformation.canonical_grouped_row_count,
            "validated_canonical_row_count": transformation.validated_canonical_row_count,
            "persisted_surveillance_record_count": transformation.persisted_surveillance_record_count,
        },
        "mapping_coverage": run.mapping_coverage,
        "query": _safe_query_metadata(query_metadata),
        "truth_classification": list(DHIS2_DEMO_TRUTH_LABELS),
        "mutation_performed": False,
    }
    run.save(update_fields=["records_seen", "records_accepted", "records_rejected", "mapping_coverage", "dry_run_preview", "updated_at"])
    return run


def _dhis2_run_provenance(run: SurveillanceIngestionRun) -> dict[str, Any]:
    return (run.source_metadata or {}).get("dhis2_provenance") or {}


def _successful_dhis2_ingestion_runs() -> list[SurveillanceIngestionRun]:
    return list(
        SurveillanceIngestionRun.objects.filter(
            adapter_key=DHIS2_API_ADAPTER_KEY,
            status=SurveillanceIngestionRun.STATUS_SUCCESS,
        ).order_by("-completed_at", "-id")
    )


def _existing_idempotent_ingestion(
    *,
    query_identity_hash: str,
    response_payload_hash: str,
) -> SurveillanceIngestionRun | None:
    """Return a prior run only when both identity hashes match exactly."""

    for run in _successful_dhis2_ingestion_runs():
        provenance = _dhis2_run_provenance(run)
        if (
            provenance.get("query_identity_hash") == query_identity_hash
            and provenance.get("response_payload_hash") == response_payload_hash
        ):
            return run
    return None


def _latest_dhis2_ingestion_for_query(query_identity_hash: str) -> SurveillanceIngestionRun | None:
    for run in _successful_dhis2_ingestion_runs():
        if _dhis2_run_provenance(run).get("query_identity_hash") == query_identity_hash:
            return run
    return None


def _dhis2_row_identity_key(row: dict[str, str]) -> tuple[str, str, str, str]:
    data_element_ids = ",".join(
        sorted(item.strip() for item in str(row.get("dhis2_data_element_id") or "").split(",") if item.strip())
    )
    return (
        str(row.get("dhis2_org_unit_id") or "").strip(),
        data_element_ids,
        str(row.get("dhis2_period") or "").strip().upper(),
        str(row.get("dhis2_category_option_combo") or "").strip(),
    )


def _prior_record_identity_key(record) -> tuple[str, str, str, str]:
    provider = ((record.raw_payload or {}).get("provider_contract") or {})
    return _dhis2_row_identity_key(
        {
            "dhis2_org_unit_id": provider.get("dhis2_org_unit_id"),
            "dhis2_data_element_id": provider.get("dhis2_data_element_id"),
            "dhis2_period": provider.get("dhis2_period"),
            "dhis2_category_option_combo": provider.get("dhis2_category_option_combo"),
        }
    )


def _attach_dhis2_correction_supersession_refs(
    transformation: Dhis2Transformation,
    *,
    previous_run: SurveillanceIngestionRun,
) -> None:
    prior_records = list(previous_run.surveillance_records.order_by("id"))
    records_by_identity: dict[tuple[str, str, str, str], list[Any]] = {}
    for record in prior_records:
        records_by_identity.setdefault(_prior_record_identity_key(record), []).append(record)

    for row in transformation.rows:
        candidates = records_by_identity.get(_dhis2_row_identity_key(row), [])
        if not candidates:
            continue
        source_refs = [str(record.source_ref or "").strip() for record in candidates if record.source_ref]
        if source_refs:
            # All records emitted from one grouped canonical row normally
            # share the row-level source_ref.  The surveillance amendment
            # workflow resolves the target again by ward, period, and class.
            row["supersedes_record_ref"] = source_refs[0]
        else:
            row["supersedes_record_ref"] = f"surveillance_record:{candidates[0].id}"
    transformation.correction_detected = True
    transformation.correction_previous_ingestion_id = previous_run.id


def _upload_for_ingestion(run: SurveillanceIngestionRun) -> SourceDataUploadBatch | None:
    return (
        SourceDataUploadBatch.objects.filter(surveillance_ingestion_run=run)
        .order_by("-created_at")
        .first()
    )


def _finalise_interoperability_run(
    *,
    run: InteroperabilityRun,
    connector_run: SourceDataConnectorRun,
    batch: SourceDataUploadBatch | None,
    domain_run: SurveillanceIngestionRun | None,
    transformation: Dhis2Transformation,
    discovery: dict[str, Any],
    query_metadata: dict[str, Any],
    idempotent_replay: bool = False,
) -> None:
    domain_status = getattr(domain_run, "status", "") if domain_run else ""
    import_succeeded = domain_status in {
        SurveillanceIngestionRun.STATUS_SUCCESS,
        SurveillanceIngestionRun.STATUS_PARTIAL,
    }
    run.status = (
        InteroperabilityRun.STATUS_COMPLETED
        if import_succeeded and not transformation.rejected_rows
        else InteroperabilityRun.STATUS_PARTIAL
        if import_succeeded
        else InteroperabilityRun.STATUS_FAILED
    )
    if run.status == InteroperabilityRun.STATUS_FAILED:
        run.error_summary = getattr(domain_run, "error_summary", "DHIS2 canonical import failed.") or "DHIS2 canonical import failed."
    else:
        run.error_summary = ""
    validated_canonical_row_count = batch.accepted_count if batch else transformation.canonical_grouped_row_count
    persisted_surveillance_record_count = (
        domain_run.surveillance_records.count()
        if domain_run
        else 0
    )
    count_summary = {
        "source_data_value_count": transformation.raw_record_count,
        "mapped_source_data_value_count": transformation.mapped_source_data_value_count,
        "rejected_source_data_value_count": transformation.rejected_source_data_value_count,
        "canonical_grouped_row_count": transformation.canonical_grouped_row_count,
        "validated_canonical_row_count": validated_canonical_row_count,
        "persisted_surveillance_record_count": persisted_surveillance_record_count,
    }
    run.lineage_metadata = {
        **(run.lineage_metadata or {}),
        "retrieved_at": discovery.get("retrieved_at"),
        "dhis2_server_version": discovery.get("server_version") or "unknown",
        "query": _safe_query_metadata(query_metadata),
        "query_identity_hash": transformation.query_identity_hash,
        "response_payload_hash": transformation.response_payload_hash,
        "count_summary": count_summary,
        "domain_ingestion_run_id": getattr(domain_run, "id", None),
        "source_data_upload_public_id": str(batch.public_id) if batch else "",
        "idempotency": {
            "replay_detected": idempotent_replay,
            "duplicate_canonical_records_created": 0,
            "existing_ingestion_run_id": getattr(domain_run, "id", None) if idempotent_replay else None,
            "query_identity_hash": transformation.query_identity_hash,
            "response_payload_hash": transformation.response_payload_hash,
        },
        "correction": {
            "detected": transformation.correction_detected,
            "previous_ingestion_run_id": transformation.correction_previous_ingestion_id,
            "correction_mode": "amendment" if transformation.correction_detected else "original",
        },
    }
    run.dry_run_preview = {
        **(run.dry_run_preview or {}),
        "canonical_validation": {
            "status": batch.validation_status if batch else "replay_skipped",
            "row_count": batch.row_count if batch else transformation.canonical_grouped_row_count,
            "accepted_count": batch.accepted_count if batch else transformation.canonical_grouped_row_count,
            "rejected_count": batch.rejected_count if batch else transformation.rejected_source_data_value_count,
            "counts": count_summary,
        },
        "canonical_ingestion": {
            "status": domain_status or "replay_skipped",
            "run_id": getattr(domain_run, "id", None),
            "records_seen": getattr(domain_run, "records_seen", transformation.raw_record_count),
            "records_loaded": getattr(domain_run, "records_loaded", transformation.canonical_grouped_row_count),
            "records_rejected": getattr(domain_run, "records_rejected", len(transformation.rejected_rows)),
            "persisted_surveillance_record_count": persisted_surveillance_record_count,
        },
        "mutation_performed": not idempotent_replay and bool(domain_run),
        "truth_classification": list(DHIS2_DEMO_TRUTH_LABELS),
    }
    run.completed_at = timezone.now()
    run.save(update_fields=["status", "error_summary", "lineage_metadata", "dry_run_preview", "completed_at", "updated_at"])
    connector_run.upload_batch = batch
    connector_run.fetched_record_count = transformation.raw_record_count
    connector_run.status = SourceDataConnectorRun.STATUS_SUCCESS if import_succeeded else SourceDataConnectorRun.STATUS_FAILED
    connector_run.error_summary = "" if import_succeeded else run.error_summary
    connector_run.safe_metadata = {
        **(connector_run.safe_metadata or {}),
        "transport": DHIS2_API_ADAPTER_KEY,
        "instance_hostname": run.lineage_metadata.get("instance_hostname", ""),
        "api_resource": run.lineage_metadata.get("api_resource", ""),
        "dhis2_server_version": run.lineage_metadata.get("dhis2_server_version", "unknown"),
        "retrieved_at": run.lineage_metadata.get("retrieved_at"),
        "mapping_version": run.mapping_version.version_label if run.mapping_version_id else "",
        "source_reference_hash": transformation.source_reference_hash,
        "interoperability_run_id": str(run.public_id),
        "domain_ingestion_run_id": getattr(domain_run, "id", None),
        "source_record_count": transformation.raw_record_count,
        "mapped_record_count": transformation.mapped_source_data_value_count,
        "rejected_record_count": transformation.rejected_source_data_value_count,
        "idempotency_replay": idempotent_replay,
        "duplicate_canonical_records_created": 0,
        "query_identity_hash": transformation.query_identity_hash,
        "response_payload_hash": transformation.response_payload_hash,
        "count_summary": count_summary,
        "http_evidence": _safe_query_metadata(query_metadata),
        "credential_material_present_in_persisted_evidence": False,
        "truth_classification": list(DHIS2_DEMO_TRUTH_LABELS),
    }
    connector_run.completed_at = timezone.now()
    connector_run.save(update_fields=["upload_batch", "fetched_record_count", "status", "error_summary", "safe_metadata", "completed_at"])


def _update_domain_provenance(
    domain_run: SurveillanceIngestionRun,
    *,
    discovery: dict[str, Any],
    query_metadata: dict[str, Any],
    mapping: Dhis2Mapping,
    transformation: Dhis2Transformation,
    connector_run_id: int,
    instance_hostname: str,
) -> None:
    provenance = {
        "schema_version": DHIS2_API_SCHEMA_VERSION,
        "source_system": "dhis2_play_demo",
        "instance_hostname": instance_hostname,
        "api_resource": query_metadata.get("resource"),
        "query_parameters": _safe_json(query_metadata.get("params") or {}),
        "dhis2_server_version": discovery.get("server_version") or "unknown",
        "retrieved_at": discovery.get("retrieved_at"),
        "mapping_version": mapping.version_label,
        "source_reference_hash": transformation.source_reference_hash,
        "query_identity_hash": transformation.query_identity_hash,
        "response_payload_hash": transformation.response_payload_hash,
        "source_data_value_count": transformation.raw_record_count,
        "mapped_source_data_value_count": transformation.mapped_source_data_value_count,
        "rejected_source_data_value_count": transformation.rejected_source_data_value_count,
        "canonical_grouped_row_count": transformation.canonical_grouped_row_count,
        "connector_run_id": connector_run_id,
        "http_evidence": _safe_query_metadata(query_metadata),
        "truth_classification": list(DHIS2_DEMO_TRUTH_LABELS),
        "production_eligible": False,
        "operational_use": "demo_only_not_for_real_evaluation_or_alerting",
    }
    domain_run.adapter_key = DHIS2_API_ADAPTER_KEY
    domain_run.source_metadata = {
        **(domain_run.source_metadata or {}),
        "dhis2_provenance": provenance,
        "seeded": True,
        "seeded_non_production": True,
        "production_use_allowed": False,
        "operational_use": "demo_only_not_for_real_evaluation",
    }
    domain_run.results = {
        **(domain_run.results or {}),
        "dhis2_provenance": provenance,
        "truth_gates": {
            "production_model_training_eligible": False,
            "confirmed_outbreak_truth_eligible": False,
            "production_alerting_eligible": False,
        },
    }
    domain_run.save(update_fields=["adapter_key", "source_metadata", "results"])
    domain_run.source.metadata = {
        **(domain_run.source.metadata or {}),
        "dhis2_provenance": provenance,
        "seeded": True,
        "seeded_non_production": True,
        "production_use_allowed": False,
        "operational_use": "demo_only_not_for_real_evaluation",
    }
    domain_run.source.save(update_fields=["metadata", "updated_at"])


def run_dhis2_connector_refresh(
    *,
    connector_run: SourceDataConnectorRun,
    actor=None,
    options: dict[str, Any] | None = None,
) -> SourceDataConnectorRun:
    """Run one small authenticated DHIS2 read and the CCHIS canonical path."""

    if not dhis2_api_configured():
        raise Dhis2ConfigurationError("DHIS2 API transport is not fully configured.")
    options = options or {}
    mapping = dhis2_mapping_from_settings()
    validate_dhis2_query(mapping.query, mapping)
    client = dhis2_client_from_settings()
    retrieved_at = timezone.now().isoformat()
    discovery = client.discover(mapping)
    discovery["retrieved_at"] = retrieved_at
    aggregate_rows, query_metadata = client.fetch_aggregate(mapping.query)
    query_metadata["discovery_http_receipts"] = discovery.get("http_receipts") or []
    transformation = transform_dhis2_rows(
        aggregate_rows,
        mapping=mapping,
        instance_hostname=client.instance_hostname,
        query_metadata=query_metadata,
        retrieved_at=retrieved_at,
        connector_run_id=connector_run.id,
    )
    existing_run = _existing_idempotent_ingestion(
        query_identity_hash=transformation.query_identity_hash,
        response_payload_hash=transformation.response_payload_hash,
    )
    if existing_run is None:
        previous_run = _latest_dhis2_ingestion_for_query(transformation.query_identity_hash)
        if previous_run is not None:
            _attach_dhis2_correction_supersession_refs(transformation, previous_run=previous_run)
    connector_run.source_name = "DHIS2 Play demo aggregate (DEMO, NON_OPERATIONAL)"
    connector_run.source_ref = transformation.source_ref
    connector_run.save(update_fields=["source_name", "source_ref"])
    system, mapping_version, mapping_errors = persist_dhis2_mapping_set(mapping=mapping, client=client, operator=actor)
    interop_run = _create_interoperability_run(
        system=system,
        mapping_version=mapping_version,
        transformation=transformation,
        query_metadata=query_metadata,
        discovery=discovery,
        client=client,
        operator=actor,
    )
    if mapping_errors:
        for mapping_error in mapping_errors:
            InteroperabilityRunError.objects.create(
                run=interop_run,
                severity=InteroperabilityRunError.SEVERITY_ERROR,
                error_code=str(mapping_error.get("code") or "demo_mapping_error"),
                field_path="organisation_units",
                safe_message="A demonstration DHIS2 org-unit mapping has no active CCHIS demonstration ward.",
                remediation_hint="Create or review the explicit non-operational CCHIS demonstration ward crosswalk.",
                raw_value_digest=_stable_hash(mapping_error),
            )
        interop_run.status = InteroperabilityRun.STATUS_FAILED
        interop_run.error_summary = "DHIS2 demonstration mapping has unresolved CCHIS wards."
        interop_run.completed_at = timezone.now()
        interop_run.save(update_fields=["status", "error_summary", "completed_at", "updated_at"])
        connector_run.status = SourceDataConnectorRun.STATUS_FAILED
        connector_run.error_summary = interop_run.error_summary
        connector_run.fetched_record_count = transformation.raw_record_count
        connector_run.safe_metadata = {
            **(connector_run.safe_metadata or {}),
            "transport": DHIS2_API_ADAPTER_KEY,
            "interoperability_run_id": str(interop_run.public_id),
            "source_record_count": transformation.raw_record_count,
            "mapped_record_count": transformation.mapped_source_data_value_count,
            "rejected_record_count": transformation.rejected_source_data_value_count,
            "query_identity_hash": transformation.query_identity_hash,
            "response_payload_hash": transformation.response_payload_hash,
            "credential_material_present_in_persisted_evidence": False,
            "mapping_errors": mapping_errors,
        }
        connector_run.completed_at = timezone.now()
        connector_run.save(update_fields=["status", "error_summary", "fetched_record_count", "safe_metadata", "completed_at"])
        return connector_run

    existing_batch = _upload_for_ingestion(existing_run) if existing_run else None
    if existing_run:
        _finalise_interoperability_run(
            run=interop_run,
            connector_run=connector_run,
            batch=existing_batch,
            domain_run=existing_run,
            transformation=transformation,
            discovery=discovery,
            query_metadata=query_metadata,
            idempotent_replay=True,
        )
        return connector_run

    csv_payload = _canonical_csv(transformation.rows)
    upload_metadata = {
        "feed_key": "surveillance_weekly_aggregate",
        "source_name": "DHIS2 Play demo aggregate (DEMO, NON_OPERATIONAL)",
        "source_timestamp": timezone.now(),
        "source_ref": transformation.source_ref,
        "reporting_period_start": transformation.period_start,
        "reporting_period_end": transformation.period_end,
        "operator_note": (
            "DEMO; NON_OPERATIONAL; read-only DHIS2 Play aggregate interoperability proof; "
            "not Migori/Kenya data; explicit UID crosswalk; production truth and alerting blocked."
        ),
        "correction_mode": "amendment" if transformation.correction_detected else "",
        "replacement_reason": (
            "DHIS2 returned a changed payload for the same bounded query identity; "
            "imported through the surveillance amendment workflow."
            if transformation.correction_detected
            else ""
        ),
    }
    upload = create_source_data_upload_batch(
        uploaded_file=SimpleUploadedFile(
            f"dhis2_play_demo_{transformation.source_reference_hash[:16]}.csv",
            csv_payload.encode("utf-8"),
            content_type="text/csv",
        ),
        created_by=actor,
        metadata=upload_metadata,
    )
    upload.metadata = {
        **(upload.metadata or {}),
        "source_data_connector": {
            "connector_key": connector_run.connector_key,
            "connector_run_id": connector_run.id,
            "transport": DHIS2_API_ADAPTER_KEY,
            "interoperability_run_id": str(interop_run.public_id),
            "truth_classification": list(DHIS2_DEMO_TRUTH_LABELS),
            "credential_material_present_in_persisted_evidence": False,
            "query_identity_hash": transformation.query_identity_hash,
            "response_payload_hash": transformation.response_payload_hash,
        },
    }
    upload.save(update_fields=["metadata", "updated_at"])
    upload = validate_source_data_upload_batch(upload)
    if upload.validation_status != SourceDataUploadBatch.VALIDATION_PASSED:
        _finalise_interoperability_run(
            run=interop_run,
            connector_run=connector_run,
            batch=upload,
            domain_run=None,
            transformation=transformation,
            discovery=discovery,
            query_metadata=query_metadata,
        )
        return connector_run

    upload.status = SourceDataUploadBatch.STATUS_READY_FOR_CONFIRMATION
    upload.approval_status = SourceDataUploadBatch.APPROVAL_NOT_REQUIRED
    upload.save(update_fields=["status", "approval_status", "updated_at"])
    imported_upload = run_confirmed_source_data_import(upload, actor=actor, worker_execution=True)
    domain_run = imported_upload.surveillance_ingestion_run
    if domain_run:
        _update_domain_provenance(
            domain_run,
            discovery=discovery,
            query_metadata=query_metadata,
            mapping=mapping,
            transformation=transformation,
            connector_run_id=connector_run.id,
            instance_hostname=client.instance_hostname,
        )
    _finalise_interoperability_run(
        run=interop_run,
        connector_run=connector_run,
        batch=imported_upload,
        domain_run=domain_run,
        transformation=transformation,
        discovery=discovery,
        query_metadata=query_metadata,
    )
    return connector_run


__all__ = [
    "DHIS2_API_ADAPTER_KEY",
    "Dhis2AggregateRow",
    "Dhis2AuthenticationError",
    "Dhis2Client",
    "Dhis2ConfigurationError",
    "Dhis2MappingError",
    "Dhis2Mapping",
    "Dhis2OperatorError",
    "Dhis2QueryScopeError",
    "Dhis2RequestError",
    "dhis2_api_configured",
    "dhis2_failure_summary",
    "dhis2_query_identity_hash",
    "dhis2_response_payload_hash",
    "load_dhis2_mapping",
    "parse_dhis2_period",
    "persist_dhis2_mapping_set",
    "resolve_dhis2_operator",
    "run_dhis2_connector_refresh",
    "safe_instance_url",
    "transform_dhis2_rows",
    "validate_dhis2_query",
]
