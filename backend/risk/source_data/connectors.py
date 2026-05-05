from __future__ import annotations

import csv
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any

import requests
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.utils import timezone

from risk.models import (
    SourceDataConnectorRun,
    SourceDataFeedModeOverride,
    SourceDataUploadBatch,
)
from risk.source_data.features import (
    FEATURE_API_CONNECTORS,
    require_source_data_feature,
    source_data_api_connectors_enabled,
)


SOURCE_DATA_CONNECTOR_REGISTRY_SCHEMA_VERSION = "source-data-connector-registry-v1"
SOURCE_DATA_CONNECTOR_RUN_SCHEMA_VERSION = "source-data-connector-run-v1"


class SourceDataConnectorError(ValueError):
    pass


@dataclass(frozen=True)
class SourceDataConnectorDefinition:
    connector_key: str
    label: str
    target_feed_key: str
    feed_mode: str
    source_name: str
    source_ref_prefix: str
    required_settings: tuple[str, ...]
    canonical_csv_url_setting: str
    notes: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "connector_key": self.connector_key,
            "label": self.label,
            "target_feed_key": self.target_feed_key,
            "feed_mode": self.feed_mode,
            "source_name": self.source_name,
            "source_ref_prefix": self.source_ref_prefix,
            "required_settings": list(self.required_settings),
            "canonical_csv_url_setting": self.canonical_csv_url_setting,
            "notes": self.notes,
        }


SOURCE_DATA_CONNECTORS: tuple[SourceDataConnectorDefinition, ...] = (
    SourceDataConnectorDefinition(
        connector_key="dhis2_surveillance_weekly",
        label="DHIS2 weekly surveillance pull",
        target_feed_key="surveillance_weekly_aggregate",
        feed_mode=SourceDataFeedModeOverride.MODE_API,
        source_name="Migori DHIS2 API",
        source_ref_prefix="dhis2-api",
        required_settings=(
            "SOURCE_DATA_DHIS2_BASE_URL",
            "SOURCE_DATA_DHIS2_USERNAME",
            "SOURCE_DATA_DHIS2_PASSWORD",
            "SOURCE_DATA_DHIS2_MAPPING_JSON",
        ),
        canonical_csv_url_setting="SOURCE_DATA_DHIS2_CANONICAL_CSV_URL",
        notes="Scheduled DHIS2 acquisition after org-unit and data-element mappings are approved.",
    ),
    SourceDataConnectorDefinition(
        connector_key="openmrs_facility_surveillance",
        label="OpenMRS facility surveillance extract",
        target_feed_key="surveillance_daily_aggregate",
        feed_mode=SourceDataFeedModeOverride.MODE_API,
        source_name="OpenMRS facility extract",
        source_ref_prefix="openmrs-extract",
        required_settings=(
            "SOURCE_DATA_OPENMRS_BASE_URL",
            "SOURCE_DATA_OPENMRS_CLIENT_ID",
            "SOURCE_DATA_OPENMRS_CLIENT_SECRET",
            "SOURCE_DATA_OPENMRS_MAPPING_JSON",
        ),
        canonical_csv_url_setting="SOURCE_DATA_OPENMRS_CANONICAL_CSV_URL",
        notes="Facility-level extract connector that still validates through canonical surveillance CSV checks.",
    ),
    SourceDataConnectorDefinition(
        connector_key="worldpop_knbs_population",
        label="WorldPop/KNBS processed population refresh",
        target_feed_key="population_baseline",
        feed_mode=SourceDataFeedModeOverride.MODE_API,
        source_name="WorldPop/KNBS processed source",
        source_ref_prefix="worldpop-knbs",
        required_settings=(
            "SOURCE_DATA_WORLDPOP_KNBS_SOURCE_URL",
            "SOURCE_DATA_WORLDPOP_KNBS_RELEASE_VERSION",
        ),
        canonical_csv_url_setting="SOURCE_DATA_WORLDPOP_KNBS_CANONICAL_CSV_URL",
        notes="Processed population release acquisition; raw credentials stay in runtime configuration.",
    ),
    SourceDataConnectorDefinition(
        connector_key="osm_overpass_settlement",
        label="OSM/Overpass settlement exposure refresh",
        target_feed_key="settlement_layer",
        feed_mode=SourceDataFeedModeOverride.MODE_API,
        source_name="OSM/Overpass processed exposure",
        source_ref_prefix="osm-overpass",
        required_settings=(
            "SOURCE_DATA_OSM_OVERPASS_ENDPOINT",
            "SOURCE_DATA_OSM_OVERPASS_QUERY_REF",
        ),
        canonical_csv_url_setting="SOURCE_DATA_OSM_OVERPASS_CANONICAL_CSV_URL",
        notes="Processed OSM/Overpass exposure refresh after aggregation into CCHIS geography.",
    ),
    SourceDataConnectorDefinition(
        connector_key="logistics_stock_readiness",
        label="Logistics stock readiness connector",
        target_feed_key="facility_readiness_snapshot",
        feed_mode=SourceDataFeedModeOverride.MODE_API,
        source_name="Logistics stock system",
        source_ref_prefix="logistics-stock",
        required_settings=(
            "SOURCE_DATA_LOGISTICS_BASE_URL",
            "SOURCE_DATA_LOGISTICS_CLIENT_ID",
            "SOURCE_DATA_LOGISTICS_CLIENT_SECRET",
            "SOURCE_DATA_LOGISTICS_MAPPING_JSON",
        ),
        canonical_csv_url_setting="SOURCE_DATA_LOGISTICS_CANONICAL_CSV_URL",
        notes="Facility readiness stock and capacity connector using the same canonical readiness validation.",
    ),
)


def source_data_connector_definitions() -> tuple[SourceDataConnectorDefinition, ...]:
    return SOURCE_DATA_CONNECTORS


def source_data_connector_definition(connector_key: str) -> SourceDataConnectorDefinition:
    for definition in SOURCE_DATA_CONNECTORS:
        if definition.connector_key == connector_key:
            return definition
    raise KeyError(connector_key)


def _connector_fixture_path(connector_key: str) -> Path | None:
    fixture_dir = str(getattr(settings, "SOURCE_DATA_CONNECTOR_FIXTURE_DIR", "") or "").strip()
    if not fixture_dir:
        return None
    path = Path(fixture_dir) / f"{connector_key}.csv"
    return path if path.exists() else None


def _configured_settings(definition: SourceDataConnectorDefinition) -> dict[str, bool]:
    return {name: bool(str(getattr(settings, name, "") or "").strip()) for name in definition.required_settings}


def _canonical_url_configured(definition: SourceDataConnectorDefinition) -> bool:
    return bool(str(getattr(settings, definition.canonical_csv_url_setting, "") or "").strip())


def _connector_is_configured(definition: SourceDataConnectorDefinition) -> bool:
    if not source_data_api_connectors_enabled():
        return False
    if _connector_fixture_path(definition.connector_key):
        return True
    return all(_configured_settings(definition).values()) and _canonical_url_configured(definition)


def _count_csv_records(csv_payload: str) -> int:
    reader = csv.DictReader(StringIO(csv_payload))
    return sum(1 for _ in reader) if reader.fieldnames else 0


def _fetch_connector_csv(definition: SourceDataConnectorDefinition) -> tuple[str, dict[str, Any]]:
    fixture_path = _connector_fixture_path(definition.connector_key)
    if fixture_path:
        return fixture_path.read_text(encoding="utf-8"), {
            "transport": "fixture_csv",
            "fixture_filename": fixture_path.name,
        }

    url = str(getattr(settings, definition.canonical_csv_url_setting, "") or "").strip()
    if not url:
        raise SourceDataConnectorError("Connector is not configured with a canonical CSV URL or fixture.")

    headers: dict[str, str] = {}
    token_setting = f"{definition.canonical_csv_url_setting}_BEARER_TOKEN"
    bearer_token = str(getattr(settings, token_setting, "") or "").strip()
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"

    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.text, {
        "transport": "canonical_csv_url",
        "url_configured": True,
        "status_code": response.status_code,
    }


def _default_connector_metadata(
    definition: SourceDataConnectorDefinition,
    *,
    now,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    options = options or {}
    today = now.date()
    metadata: dict[str, Any] = {
        "feed_key": definition.target_feed_key,
        "source_name": options.get("source_name") or definition.source_name,
        "source_timestamp": options.get("source_timestamp") or now,
        "source_ref": options.get("source_ref") or f"{definition.source_ref_prefix}:{today.isoformat()}",
        "release_version": options.get("release_version") or getattr(settings, "SOURCE_DATA_WORLDPOP_KNBS_RELEASE_VERSION", ""),
        "operator_note": "Source-data connector refresh; CSV remains fallback/correction path.",
    }
    if definition.target_feed_key in {
        "surveillance_weekly_aggregate",
        "surveillance_daily_aggregate",
        "facility_readiness_snapshot",
    }:
        metadata["reporting_period_start"] = options.get("reporting_period_start") or today
        metadata["reporting_period_end"] = options.get("reporting_period_end") or today
    return metadata


def latest_connector_run_for_feed(feed_key: str) -> SourceDataConnectorRun | None:
    return SourceDataConnectorRun.objects.filter(target_feed_key=feed_key).order_by("-started_at").first()


def latest_successful_connector_run_for_feed(feed_key: str) -> SourceDataConnectorRun | None:
    return (
        SourceDataConnectorRun.objects.filter(
            target_feed_key=feed_key,
            status=SourceDataConnectorRun.STATUS_SUCCESS,
        )
        .order_by("-completed_at", "-started_at")
        .first()
    )


def source_data_feed_mode_override(feed_key: str) -> SourceDataFeedModeOverride | None:
    return SourceDataFeedModeOverride.objects.filter(feed_key=feed_key).first()


def source_data_csv_upload_enabled(feed_key: str) -> bool:
    if not source_data_api_connectors_enabled():
        return True
    override = source_data_feed_mode_override(feed_key)
    return True if override is None else override.csv_upload_enabled


def connector_definition_for_feed(feed_key: str) -> SourceDataConnectorDefinition | None:
    return next((definition for definition in SOURCE_DATA_CONNECTORS if definition.target_feed_key == feed_key), None)


def source_data_connector_state_for_feed(feed_key: str) -> dict[str, Any]:
    definition = connector_definition_for_feed(feed_key)
    override = source_data_feed_mode_override(feed_key)
    latest_run = latest_connector_run_for_feed(feed_key)
    latest_success = latest_successful_connector_run_for_feed(feed_key)
    connectors_enabled = source_data_api_connectors_enabled()
    configured = _connector_is_configured(definition) if definition else False
    default_mode = SourceDataFeedModeOverride.MODE_API if definition and configured else SourceDataFeedModeOverride.MODE_CSV
    feed_mode = override.feed_mode if override else default_mode
    csv_upload_enabled = source_data_csv_upload_enabled(feed_key)
    status_value = "disabled" if definition and not connectors_enabled else "not_configured"
    if configured:
        status_value = "configured"
    if latest_run:
        status_value = latest_run.status
    return {
        "feed_mode": feed_mode,
        "csv_upload_enabled": csv_upload_enabled,
        "connector_status": {
            "enabled": connectors_enabled,
            "connector_key": definition.connector_key if definition else "",
            "label": definition.label if definition else "",
            "configured": configured,
            "status": status_value,
            "last_run_status": latest_run.status if latest_run else "",
            "last_run_at": latest_run.started_at.isoformat() if latest_run else None,
            "last_successful_fetch_at": latest_success.completed_at.isoformat() if latest_success and latest_success.completed_at else None,
            "required_settings": list(definition.required_settings) if definition else [],
            "credential_values_exposed": False,
            "notes": definition.notes if definition else "",
        },
    }


def build_source_data_connector_registry_payload() -> dict[str, Any]:
    connectors = []
    for definition in SOURCE_DATA_CONNECTORS:
        state = source_data_connector_state_for_feed(definition.target_feed_key)
        connectors.append({**definition.as_dict(), **state["connector_status"]})
    return {
        "schema_version": SOURCE_DATA_CONNECTOR_REGISTRY_SCHEMA_VERSION,
        "generated_at": timezone.now().isoformat(),
        "enabled": source_data_api_connectors_enabled(),
        "connectors": connectors,
    }


@transaction.atomic
def set_source_data_feed_mode_override(
    *,
    feed_key: str,
    feed_mode: str,
    csv_upload_enabled: bool,
    authoritative_connector_key: str = "",
    reason: str = "",
    actor=None,
) -> SourceDataFeedModeOverride:
    require_source_data_feature(FEATURE_API_CONNECTORS)
    if authoritative_connector_key:
        source_data_connector_definition(authoritative_connector_key)
    override, _ = SourceDataFeedModeOverride.objects.update_or_create(
        feed_key=feed_key,
        defaults={
            "feed_mode": feed_mode,
            "csv_upload_enabled": csv_upload_enabled,
            "authoritative_connector_key": authoritative_connector_key,
            "reason": reason,
            "updated_by": actor,
        },
    )
    return override


@transaction.atomic
def run_source_data_connector_refresh(
    *,
    connector_key: str,
    actor=None,
    options: dict[str, Any] | None = None,
    force: bool = False,
) -> SourceDataConnectorRun:
    require_source_data_feature(FEATURE_API_CONNECTORS)
    now = timezone.now()
    definition = source_data_connector_definition(connector_key)
    run = SourceDataConnectorRun.objects.create(
        connector_key=definition.connector_key,
        target_feed_key=definition.target_feed_key,
        feed_mode=definition.feed_mode,
        source_name=definition.source_name,
        source_ref=f"{definition.source_ref_prefix}:{now.date().isoformat()}",
        requested_by=actor,
        safe_metadata={
            "required_settings_present": _configured_settings(definition),
            "canonical_csv_url_configured": _canonical_url_configured(definition),
            "fixture_configured": bool(_connector_fixture_path(definition.connector_key)),
            "credential_values_exposed": False,
        },
    )

    if not force and not _connector_is_configured(definition):
        run.status = SourceDataConnectorRun.STATUS_SKIPPED
        run.error_summary = "Connector is not configured; CSV upload remains the fallback path."
        run.completed_at = timezone.now()
        run.save(update_fields=["status", "error_summary", "completed_at"])
        return run

    try:
        from risk.source_data.uploads import create_source_data_upload_batch
        from risk.source_data.validation import validate_source_data_upload_batch

        csv_payload, fetch_metadata = _fetch_connector_csv(definition)
        fetched_record_count = _count_csv_records(csv_payload)
        upload_metadata = _default_connector_metadata(definition, now=now, options=options)
        uploaded_file = SimpleUploadedFile(
            f"{definition.connector_key}_{now.strftime('%Y%m%d%H%M%S')}.csv",
            csv_payload.encode("utf-8"),
            content_type="text/csv",
        )
        batch = create_source_data_upload_batch(
            uploaded_file=uploaded_file,
            created_by=actor,
            metadata=upload_metadata,
        )
        batch.metadata = {
            **(batch.metadata or {}),
            "source_data_connector": {
                "connector_key": definition.connector_key,
                "connector_run_id": run.id,
                "feed_mode": definition.feed_mode,
                "csv_fallback_available": source_data_csv_upload_enabled(definition.target_feed_key),
            },
        }
        batch.save(update_fields=["metadata", "updated_at"])
        validated_batch = validate_source_data_upload_batch(batch)
        run.upload_batch = validated_batch
        run.fetched_record_count = fetched_record_count
        run.source_ref = upload_metadata.get("source_ref", run.source_ref)
        run.safe_metadata = {
            **(run.safe_metadata or {}),
            **fetch_metadata,
            "validated_upload_public_id": str(validated_batch.public_id),
            "validation_status": validated_batch.validation_status,
            "credential_values_exposed": False,
        }
        if validated_batch.validation_status == SourceDataUploadBatch.VALIDATION_FAILED:
            run.status = SourceDataConnectorRun.STATUS_FAILED
            run.error_summary = "Connector payload failed canonical source-data validation."
        else:
            run.status = SourceDataConnectorRun.STATUS_SUCCESS
        run.completed_at = timezone.now()
        run.save(
            update_fields=[
                "upload_batch",
                "fetched_record_count",
                "source_ref",
                "safe_metadata",
                "status",
                "error_summary",
                "completed_at",
            ]
        )
        return run
    except Exception as error:
        run.status = SourceDataConnectorRun.STATUS_FAILED
        run.error_summary = str(error)
        run.completed_at = timezone.now()
        run.safe_metadata = {
            **(run.safe_metadata or {}),
            "credential_values_exposed": False,
        }
        run.save(update_fields=["status", "error_summary", "completed_at", "safe_metadata"])
        return run
