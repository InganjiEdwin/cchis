from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from django.utils import timezone

from risk.migori_worldpop_population_csv import DEFAULT_SUMMARY_PATH, load_json
from risk.migori_worldpop_population_import import DEFAULT_EXPECTED_WARD_COUNT, DEFAULT_RELEASE_VERSION
from risk.models import (
    PopulationExposureSource,
    SourceDataConnectorRun,
    SourceDataUploadBatch,
    SourceDataValidationIssue,
)
from risk.source_data.connectors import (
    source_data_connector_definition,
    source_data_connector_state_for_feed,
)
from risk.source_data.freshness import build_source_data_freshness_payload, build_source_data_overview_payload
from risk.source_data.uploads import latest_upload_artifact


DEFAULT_CONNECTOR_KEY = "worldpop_knbs_population"
DEFAULT_CONNECTOR_SUMMARY_PATH = (
    DEFAULT_SUMMARY_PATH.parent / "migori_worldpop_2026_source_data_connector.json"
)


def _run_for_connector(run_id: int | None = None) -> SourceDataConnectorRun:
    queryset = SourceDataConnectorRun.objects.filter(
        connector_key=DEFAULT_CONNECTOR_KEY,
        target_feed_key="gridded_population",
    ).order_by("-id")
    if run_id is not None:
        queryset = queryset.filter(id=run_id)
    run = queryset.select_related("upload_batch").first()
    if run is None:
        label = f"run_id={run_id}" if run_id is not None else DEFAULT_CONNECTOR_KEY
        raise ValueError(f"No Migori WorldPop source-data connector run found for {label}.")
    return run


def _normalised_text_sha256(path: str | Path) -> str:
    text = Path(path).read_text(encoding="utf-8-sig")
    normalised = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def _local_date(value) -> str:
    if value is None:
        return ""
    return timezone.localtime(value).date().isoformat()


def build_migori_worldpop_phase6_connector_summary(
    *,
    run_id: int | None = None,
    phase1_summary_path: Path = DEFAULT_SUMMARY_PATH,
    expected_ward_count: int = DEFAULT_EXPECTED_WARD_COUNT,
    expected_release_version: str = DEFAULT_RELEASE_VERSION,
) -> dict[str, Any]:
    definition = source_data_connector_definition(DEFAULT_CONNECTOR_KEY)
    run = _run_for_connector(run_id)
    upload = run.upload_batch
    phase1_summary = load_json(phase1_summary_path) if phase1_summary_path.exists() else {}
    artifact = latest_upload_artifact(upload) if upload is not None else None
    validation_error_count = (
        upload.validation_issues.filter(severity=SourceDataValidationIssue.SEVERITY_ERROR).count()
        if upload is not None
        else 0
    )
    validation_warning_count = (
        upload.validation_issues.filter(severity=SourceDataValidationIssue.SEVERITY_WARNING).count()
        if upload is not None
        else 0
    )
    upload_connector_metadata = ((upload.metadata or {}).get("source_data_connector") or {}) if upload else {}
    expected_csv_sha256 = phase1_summary.get("output_csv_sha256", "")
    phase1_output_csv_path = phase1_summary.get("output_csv_path", "")
    expected_source_ref = phase1_summary.get("source_ref", "")
    expected_source_date = str(((phase1_summary.get("worldpop_record") or {}).get("source_date")) or "")
    artifact_exact_hash_matches_phase1 = bool(artifact and artifact.sha256 == expected_csv_sha256)
    artifact_normalised_sha256 = _normalised_text_sha256(artifact.storage_path) if artifact else ""
    phase1_normalised_sha256 = (
        _normalised_text_sha256(phase1_output_csv_path)
        if phase1_output_csv_path and Path(phase1_output_csv_path).exists()
        else ""
    )
    artifact_content_matches_phase1 = artifact_exact_hash_matches_phase1 or (
        bool(artifact_normalised_sha256)
        and bool(phase1_normalised_sha256)
        and artifact_normalised_sha256 == phase1_normalised_sha256
    )
    freshness_payload = build_source_data_freshness_payload()
    feed_freshness = {
        source["feed_key"]: source
        for source in freshness_payload.get("sources", [])
        if source.get("feed_key") in {"gridded_population", "population_baseline"}
    }
    overview_payload = build_source_data_overview_payload()
    recent_uploads = overview_payload.get("recent_uploads") or []
    gridded_freshness = feed_freshness.get("gridded_population") or {}
    population_baseline_freshness = feed_freshness.get("population_baseline") or {}

    gates = {
        "phase1_summary_passed": phase1_summary.get("passed") is True,
        "connector_targets_gridded_population": definition.target_feed_key == "gridded_population",
        "connector_run_success": run.status == SourceDataConnectorRun.STATUS_SUCCESS,
        "connector_run_target_feed_expected": run.target_feed_key == "gridded_population",
        "connector_source_name_matches_definition": run.source_name == definition.source_name,
        "connector_source_ref_matches_phase1": bool(expected_source_ref) and run.source_ref == expected_source_ref,
        "connector_fetched_expected_rows": run.fetched_record_count == expected_ward_count,
        "connector_safe_metadata_no_credentials": (run.safe_metadata or {}).get("credential_values_exposed") is False,
        "upload_batch_linked": upload is not None,
        "upload_feed_key_expected": bool(upload and upload.feed_key == "gridded_population"),
        "upload_source_type_expected": bool(
            upload and upload.source_type == PopulationExposureSource.SOURCE_TYPE_GRIDDED_POPULATION
        ),
        "upload_source_name_matches_definition": bool(upload and upload.source_name == definition.source_name),
        "upload_source_timestamp_matches_phase1": bool(upload and expected_source_date)
        and _local_date(upload.source_timestamp) == expected_source_date,
        "upload_validation_passed": bool(
            upload and upload.validation_status == SourceDataUploadBatch.VALIDATION_PASSED
        ),
        "upload_row_count_expected": bool(upload and upload.row_count == expected_ward_count),
        "upload_accepted_count_expected": bool(upload and upload.accepted_count == expected_ward_count),
        "upload_rejected_count_zero": bool(upload and upload.rejected_count == 0),
        "connector_fetched_count_matches_upload_row_count": bool(upload)
        and run.fetched_record_count == upload.row_count,
        "upload_release_version_matches": bool(upload and upload.release_version == expected_release_version),
        "upload_source_ref_matches_phase1": bool(upload and upload.source_ref == expected_source_ref),
        "upload_connector_metadata_linked": upload_connector_metadata.get("connector_run_id") == run.id,
        "csv_fallback_remains_available": upload_connector_metadata.get("csv_fallback_available") is True,
        "artifact_content_matches_phase1": artifact_content_matches_phase1,
        "no_validation_errors": validation_error_count == 0,
        "freshness_gridded_population_not_demo_backed": gridded_freshness.get("truth_state") != "demo_backed",
        "freshness_gridded_population_csv_backed": gridded_freshness.get("truth_state") == "csv_backed",
        "freshness_gridded_population_has_records": gridded_freshness.get("record_count") == expected_ward_count,
        "freshness_population_baseline_not_demo_backed": population_baseline_freshness.get("truth_state") != "demo_backed",
        "freshness_population_baseline_missing_until_knbs_import": population_baseline_freshness.get("truth_state")
        == "missing"
        and population_baseline_freshness.get("record_count") == 0,
        "overview_recent_upload_exposes_connector_batch": any(
            item.get("public_id") == str(upload.public_id) and item.get("feed_key") == "gridded_population"
            for item in recent_uploads
        )
        if upload
        else False,
    }

    return {
        "phase": "migori_knbs_worldpop_phase_6_source_data_connector",
        "generated_at": timezone.now().isoformat(),
        "passed": all(gates.values()),
        "phase6_gates": gates,
        "connector_definition": definition.as_dict(),
        "connector_state_for_feed": source_data_connector_state_for_feed("gridded_population"),
        "connector_run": {
            "id": run.id,
            "connector_key": run.connector_key,
            "target_feed_key": run.target_feed_key,
            "feed_mode": run.feed_mode,
            "status": run.status,
            "source_name": run.source_name,
            "source_ref": run.source_ref,
            "fetched_record_count": run.fetched_record_count,
            "safe_metadata": run.safe_metadata,
            "error_summary": run.error_summary,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        },
        "upload_batch": {
            "id": upload.id if upload else None,
            "public_id": str(upload.public_id) if upload else "",
            "feed_key": upload.feed_key if upload else "",
            "source_type": upload.source_type if upload else "",
            "source_name": upload.source_name if upload else "",
            "source_ref": upload.source_ref if upload else "",
            "source_timestamp": upload.source_timestamp.isoformat() if upload and upload.source_timestamp else None,
            "release_version": upload.release_version if upload else "",
            "validation_status": upload.validation_status if upload else "",
            "status": upload.status if upload else "",
            "row_count": upload.row_count if upload else 0,
            "accepted_count": upload.accepted_count if upload else 0,
            "rejected_count": upload.rejected_count if upload else 0,
            "warning_count": upload.warning_count if upload else 0,
            "validation_error_count": validation_error_count,
            "validation_warning_count": validation_warning_count,
            "source_data_connector_metadata": upload_connector_metadata,
        },
        "artifact": {
            "id": artifact.id if artifact else None,
            "original_filename": artifact.original_filename if artifact else "",
            "sha256": artifact.sha256 if artifact else "",
            "phase1_csv_sha256": expected_csv_sha256,
            "exact_hash_matches_phase1": artifact_exact_hash_matches_phase1,
            "normalised_text_sha256": artifact_normalised_sha256,
            "phase1_normalised_text_sha256": phase1_normalised_sha256,
            "content_matches_phase1": artifact_content_matches_phase1,
            "size_bytes": artifact.size_bytes if artifact else 0,
            "storage_path": artifact.storage_path if artifact else "",
        },
        "source_data_freshness": {
            "gridded_population": gridded_freshness,
            "population_baseline": population_baseline_freshness,
            "truth_state_counts": freshness_payload.get("truth_state_counts") or {},
        },
        "source_data_overview": {
            "recent_connector_upload_visible": gates["overview_recent_upload_exposes_connector_batch"],
            "recent_uploads": recent_uploads[:3],
        },
        "phase1_summary_path": str(phase1_summary_path),
    }


def write_connector_summary(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
