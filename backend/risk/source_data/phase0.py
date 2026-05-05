from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from accounts.models import User
from risk.models import PopulationExposureSource, SurveillanceSource


SOURCE_DATA_PHASE0_STATUS_DATE = "2026-05-05"
SOURCE_DATA_OPS_SCHEMA_VERSION = "source-data-ops-phase0-v1"

FEED_SCOPE_MVP = "mvp"
FEED_SCOPE_LATER = "later"

INGESTION_FAMILY_SURVEILLANCE = "surveillance"
INGESTION_FAMILY_POPULATION_EXPOSURE = "population_exposure"
INGESTION_FAMILY_FACILITY_READINESS = "facility_readiness"
INGESTION_FAMILY_EXTERNAL_CONNECTOR = "external_connector"


@dataclass(frozen=True)
class SourceDataFeedDecision:
    feed_key: str
    label: str
    scope: str
    domain: str
    backend_target: str
    source_type: str
    cadence: str
    ingestion_family: str
    downstream_action: str
    required_metadata: tuple[str, ...]
    notes: str
    requires_new_ingestion_path: bool = False


SOURCE_DATA_FEED_DECISIONS: tuple[SourceDataFeedDecision, ...] = (
    SourceDataFeedDecision(
        feed_key="surveillance_weekly_aggregate",
        label="Weekly surveillance aggregate",
        scope=FEED_SCOPE_MVP,
        domain="health_surveillance",
        backend_target="ingest_surveillance",
        source_type=SurveillanceSource.SOURCE_TYPE_WEEKLY_AGGREGATE,
        cadence="weekly_minimum",
        ingestion_family=INGESTION_FAMILY_SURVEILLANCE,
        downstream_action="regenerate_surveillance_label_windows_then_rebuild_feature_datasets",
        required_metadata=("source_name", "source_timestamp", "reporting_period_start", "reporting_period_end"),
        notes="County or partner weekly aggregate with explicit reporting period.",
    ),
    SourceDataFeedDecision(
        feed_key="surveillance_daily_aggregate",
        label="Daily surveillance aggregate",
        scope=FEED_SCOPE_MVP,
        domain="health_surveillance",
        backend_target="ingest_surveillance",
        source_type=SurveillanceSource.SOURCE_TYPE_DAILY_AGGREGATE,
        cadence="daily_where_available",
        ingestion_family=INGESTION_FAMILY_SURVEILLANCE,
        downstream_action="regenerate_surveillance_label_windows_then_rebuild_feature_datasets",
        required_metadata=("source_name", "source_timestamp", "reporting_period_start", "reporting_period_end"),
        notes="Daily aggregate only where the upstream reporting source truly reports daily.",
    ),
    SourceDataFeedDecision(
        feed_key="surveillance_backfill",
        label="Surveillance historical backfill",
        scope=FEED_SCOPE_MVP,
        domain="health_surveillance",
        backend_target="ingest_surveillance",
        source_type=SurveillanceSource.SOURCE_TYPE_CSV_BACKFILL,
        cadence="one_off_then_corrections",
        ingestion_family=INGESTION_FAMILY_SURVEILLANCE,
        downstream_action="maker_checker_then_regenerate_labels_and_rebuild_features",
        required_metadata=(
            "source_name",
            "source_timestamp",
            "reporting_period_start",
            "reporting_period_end",
            "correction_mode",
            "operator_note",
        ),
        notes="Historical county or partner spreadsheet backfill; always treated as risky production evidence.",
    ),
    SourceDataFeedDecision(
        feed_key="population_baseline",
        label="Population baseline",
        scope=FEED_SCOPE_MVP,
        domain="population",
        backend_target="ingest_population_exposure",
        source_type=PopulationExposureSource.SOURCE_TYPE_POPULATION_BASELINE,
        cadence="annual_or_source_change",
        ingestion_family=INGESTION_FAMILY_POPULATION_EXPOSURE,
        downstream_action="rebuild_population_exposure_features_then_model_feature_datasets",
        required_metadata=("source_name", "source_timestamp", "release_version"),
        notes="Official ward population baseline, ideally KNBS or county planning release.",
    ),
    SourceDataFeedDecision(
        feed_key="gridded_population",
        label="Gridded population",
        scope=FEED_SCOPE_MVP,
        domain="population_exposure",
        backend_target="ingest_population_exposure",
        source_type=PopulationExposureSource.SOURCE_TYPE_GRIDDED_POPULATION,
        cadence="quarterly_or_source_change",
        ingestion_family=INGESTION_FAMILY_POPULATION_EXPOSURE,
        downstream_action="rebuild_population_exposure_features_then_model_feature_datasets",
        required_metadata=("source_name", "source_timestamp", "release_version", "source_ref"),
        notes="Processed WorldPop or partner gridded population extract aggregated to CCHIS geography.",
    ),
    SourceDataFeedDecision(
        feed_key="settlement_layer",
        label="Settlement layer",
        scope=FEED_SCOPE_MVP,
        domain="exposure_context",
        backend_target="ingest_population_exposure",
        source_type=PopulationExposureSource.SOURCE_TYPE_SETTLEMENT_LAYER,
        cadence="quarterly_or_source_change",
        ingestion_family=INGESTION_FAMILY_POPULATION_EXPOSURE,
        downstream_action="rebuild_exposure_features_then_model_feature_datasets",
        required_metadata=("source_name", "source_timestamp", "release_version", "source_ref"),
        notes="Settlement or built-up-area layer extract with aggregation method.",
    ),
    SourceDataFeedDecision(
        feed_key="wash_vulnerability_layer",
        label="WASH vulnerability layer",
        scope=FEED_SCOPE_MVP,
        domain="exposure_context",
        backend_target="ingest_population_exposure",
        source_type=PopulationExposureSource.SOURCE_TYPE_WASH_VULNERABILITY_LAYER,
        cadence="quarterly_or_assessment_change",
        ingestion_family=INGESTION_FAMILY_POPULATION_EXPOSURE,
        downstream_action="rebuild_exposure_features_then_model_feature_datasets",
        required_metadata=("source_name", "source_timestamp", "release_version", "source_ref"),
        notes="WASH vulnerability context; often proxy-classed until local WASH layers are available.",
    ),
    SourceDataFeedDecision(
        feed_key="water_body_distance_layer",
        label="Water body distance layer",
        scope=FEED_SCOPE_MVP,
        domain="exposure_context",
        backend_target="ingest_population_exposure",
        source_type=PopulationExposureSource.SOURCE_TYPE_WATER_BODY_DISTANCE_LAYER,
        cadence="quarterly_or_source_change",
        ingestion_family=INGESTION_FAMILY_POPULATION_EXPOSURE,
        downstream_action="rebuild_exposure_features_then_model_feature_datasets",
        required_metadata=("source_name", "source_timestamp", "release_version", "source_ref"),
        notes="Water proximity layer with named distance or aggregation method.",
    ),
    SourceDataFeedDecision(
        feed_key="flood_exposure_layer",
        label="Flood exposure layer",
        scope=FEED_SCOPE_MVP,
        domain="flood_exposure",
        backend_target="ingest_population_exposure",
        source_type=PopulationExposureSource.SOURCE_TYPE_FLOOD_EXPOSURE_LAYER,
        cadence="monthly_in_rainy_season_event_driven_after_floods",
        ingestion_family=INGESTION_FAMILY_POPULATION_EXPOSURE,
        downstream_action="rebuild_exposure_features_then_model_feature_datasets",
        required_metadata=("source_name", "source_timestamp", "release_version", "source_ref"),
        notes="Flood exposure layer or proxy extract; never direct surveillance truth.",
    ),
    SourceDataFeedDecision(
        feed_key="facility_catchment_mapping",
        label="Facility catchment mapping",
        scope=FEED_SCOPE_MVP,
        domain="facility_spatial",
        backend_target="ingest_population_exposure",
        source_type=PopulationExposureSource.SOURCE_TYPE_CATCHMENT_MAPPING,
        cadence="setup_then_facility_or_catchment_change",
        ingestion_family=INGESTION_FAMILY_POPULATION_EXPOSURE,
        downstream_action="recompute_spatial_facility_evidence_and_facility_forecast_inputs",
        required_metadata=("source_name", "source_timestamp", "release_version"),
        notes="Manual or file-backed facility catchment approximation.",
    ),
    SourceDataFeedDecision(
        feed_key="facility_readiness_snapshot",
        label="Facility readiness snapshot",
        scope=FEED_SCOPE_MVP,
        domain="facility_readiness",
        backend_target="new_readiness_snapshot_ingestion_path",
        source_type="readiness_snapshot",
        cadence="weekly_routine_daily_during_alerts",
        ingestion_family=INGESTION_FAMILY_FACILITY_READINESS,
        downstream_action="recompute_readiness_truth_then_facility_burden_forecast",
        required_metadata=("source_name", "source_timestamp", "reporting_period_start", "reporting_period_end"),
        notes="Canonical CSV path still needs implementation; current readiness workflows are API/review oriented.",
        requires_new_ingestion_path=True,
    ),
    SourceDataFeedDecision(
        feed_key="dhis2_api_scheduled_pull",
        label="DHIS2 API scheduled pull",
        scope=FEED_SCOPE_LATER,
        domain="health_surveillance",
        backend_target="future_authenticated_connector",
        source_type="dhis2_api",
        cadence="scheduled_after_credentials_and_mapping",
        ingestion_family=INGESTION_FAMILY_EXTERNAL_CONNECTOR,
        downstream_action="same_as_surveillance_feed_after_contract_validation",
        required_metadata=("source_name", "source_timestamp", "source_ref"),
        notes="Preferred institutional path after credentials, org-unit mapping, and data elements are approved.",
    ),
    SourceDataFeedDecision(
        feed_key="openmrs_facility_extract",
        label="OpenMRS facility extract",
        scope=FEED_SCOPE_LATER,
        domain="facility_surveillance",
        backend_target="future_authenticated_connector",
        source_type="openmrs_extract",
        cadence="scheduled_or_facility_export",
        ingestion_family=INGESTION_FAMILY_EXTERNAL_CONNECTOR,
        downstream_action="facility_proxy_or_readiness_pipeline_after_contract_validation",
        required_metadata=("source_name", "source_timestamp", "source_ref"),
        notes="Facility-level extracts once OpenMRS deployments and identifiers are mapped.",
    ),
    SourceDataFeedDecision(
        feed_key="worldpop_knbs_processed_source_pull",
        label="WorldPop/KNBS processed source pull",
        scope=FEED_SCOPE_LATER,
        domain="population",
        backend_target="future_processed_source_connector",
        source_type="worldpop_knbs_pull",
        cadence="release_based",
        ingestion_family=INGESTION_FAMILY_EXTERNAL_CONNECTOR,
        downstream_action="same_as_population_or_gridded_population_after_contract_validation",
        required_metadata=("source_name", "source_timestamp", "release_version", "source_ref"),
        notes="Automated source acquisition remains separate from the CSV operator bridge.",
    ),
    SourceDataFeedDecision(
        feed_key="osm_overpass_exposure_refresh",
        label="OSM/Overpass exposure refresh",
        scope=FEED_SCOPE_LATER,
        domain="exposure_context",
        backend_target="future_processed_source_connector",
        source_type="osm_overpass_refresh",
        cadence="quarterly_or_source_change",
        ingestion_family=INGESTION_FAMILY_EXTERNAL_CONNECTOR,
        downstream_action="same_as_settlement_water_or_facility_context_after_contract_validation",
        required_metadata=("source_name", "source_timestamp", "release_version", "source_ref"),
        notes="Automated refresh after OSM extraction and aggregation contracts are stable.",
    ),
    SourceDataFeedDecision(
        feed_key="logistics_stock_system_integration",
        label="Logistics/stock system integration",
        scope=FEED_SCOPE_LATER,
        domain="facility_readiness",
        backend_target="future_authenticated_connector",
        source_type="logistics_stock",
        cadence="daily_or_weekly_by_system",
        ingestion_family=INGESTION_FAMILY_EXTERNAL_CONNECTOR,
        downstream_action="same_as_facility_readiness_after_contract_validation",
        required_metadata=("source_name", "source_timestamp", "source_ref"),
        notes="ORS, IV fluids, zinc, chlorine, beds, staffing, and referral capacity once system contracts exist.",
    ),
)

SOURCE_DATA_ACTIONS: tuple[str, ...] = (
    "source_data:view",
    "source_data:download_template",
    "source_data:upload",
    "source_data:validate",
    "source_data:confirm_import",
    "source_data:replace_import",
    "source_data:request_approval",
    "source_data:approve_risky_import",
    "source_data:download_errors",
    "source_data:trigger_downstream",
    "source_data:manage_retention",
    "source_data:emergency_override",
)

ROLE_PERMISSION_MAP: dict[str, tuple[str, ...]] = {
    User.ROLE_ADMIN: (
        "source_data:view",
        "source_data:download_template",
        "source_data:upload",
        "source_data:validate",
        "source_data:confirm_import",
        "source_data:replace_import",
        "source_data:request_approval",
        "source_data:approve_risky_import",
        "source_data:download_errors",
        "source_data:trigger_downstream",
        "source_data:manage_retention",
    ),
    User.ROLE_SUPERVISOR: (
        "source_data:view",
        "source_data:download_template",
        "source_data:upload",
        "source_data:validate",
        "source_data:confirm_import",
        "source_data:request_approval",
        "source_data:download_errors",
        "source_data:trigger_downstream",
    ),
    User.ROLE_ANALYST: (
        "source_data:view",
        "source_data:download_template",
    ),
    User.ROLE_CHV: (),
    "SUPERUSER": (
        "source_data:emergency_override",
    ),
}

APPROVAL_STATES: tuple[str, ...] = (
    "not_required",
    "pending",
    "approved",
    "rejected",
    "expired",
)

RISKY_IMPORT_CATEGORIES: tuple[str, ...] = (
    "historical_backfill",
    "replacement_import",
    "replay_import",
    "production_surveillance_truth",
    "unusually_large_source_delta",
    "production_downstream_rebuild",
)

MAKER_CHECKER_POLICY: dict[str, Any] = {
    "routine_clean_import": {
        "approval_required": False,
        "allowed_confirmers": (User.ROLE_ADMIN, User.ROLE_SUPERVISOR),
    },
    "risky_import": {
        "approval_required": True,
        "risk_categories": RISKY_IMPORT_CATEGORIES,
        "requesters": (User.ROLE_ADMIN, User.ROLE_SUPERVISOR),
        "second_approvers": (User.ROLE_ADMIN,),
        "self_approval_allowed": False,
        "decision_fields": ("actor", "timestamp", "reason", "risk_category", "affected_feed"),
        "expires_after_hours": 72,
    },
}

UPLOAD_LIFECYCLE_STATUSES: tuple[str, ...] = (
    "draft",
    "uploaded",
    "validating",
    "validation_failed",
    "ready_for_confirmation",
    "confirming",
    "imported",
    "import_failed",
    "cancelled",
    "superseded",
)

UPLOAD_STATUS_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "draft": ("uploaded", "cancelled"),
    "uploaded": ("validating", "cancelled"),
    "validating": ("validation_failed", "ready_for_confirmation", "cancelled"),
    "validation_failed": ("uploaded", "cancelled"),
    "ready_for_confirmation": ("confirming", "cancelled"),
    "confirming": ("imported", "import_failed"),
    "import_failed": ("ready_for_confirmation", "cancelled"),
    "imported": ("superseded",),
    "cancelled": (),
    "superseded": (),
}

RETENTION_POLICY: dict[str, dict[str, Any]] = {
    "raw_upload_artifacts": {
        "default_days": 60,
        "minimum_days": 30,
        "maximum_days": 90,
        "contains_raw_source_values": True,
        "expires_by_policy": True,
    },
    "rejected_row_diagnostics": {
        "default_days": 30,
        "maximum_days": 60,
        "redacted": True,
        "csv_formula_sanitized": True,
        "expires_by_policy": True,
    },
    "metadata_hashes_counts_audit_events": {
        "default_days": 730,
        "contains_raw_source_values": False,
        "expires_by_policy": False,
    },
}

SOURCE_DATA_UPLOAD_STORAGE_DECISION: dict[str, Any] = {
    "storage_backend": "shared_filesystem",
    "docker_volume": "source_uploads",
    "default_storage_root": "/var/lib/cchis/source_uploads",
    "environment_variables": (
        "SOURCE_DATA_UPLOAD_STORAGE_BACKEND",
        "SOURCE_DATA_UPLOAD_ROOT",
    ),
    "durable_between_web_and_worker": True,
    "local_process_temp_files_allowed_for_queued_imports": False,
    "artifact_identity_fields": ("upload_batch_public_id", "artifact_public_id", "sha256", "storage_path"),
    "hash_must_match_validated_file": True,
    "production_alternative": "object_storage_with_equivalent_web_worker_access_and_hash_verification",
}

THREAT_MODEL: tuple[dict[str, Any], ...] = (
    {
        "risk_id": "malicious_file",
        "severity": "high",
        "threat": (
            "Uploaded files may contain executable content, oversized payloads, formula injection, "
            "or spoofed MIME types."
        ),
        "mitigations": (
            "csv_only_mvp",
            "extension_allowlist",
            "server_side_mime_sniffing",
            "size_and_row_limits",
            "formula_injection_detection_and_export_sanitization",
            "uploads_stored_outside_web_served_paths",
        ),
    },
    {
        "risk_id": "accidental_pii",
        "severity": "high",
        "threat": (
            "Aggregate feeds may accidentally contain patient names, phone numbers, IDs, emails, "
            "dates of birth, or free-text identifiers."
        ),
        "mitigations": (
            "reject_likely_pii_headers",
            "sample_first_rows_and_bounded_random_rows_for_pii_values",
            "redact_validation_issues",
            "allow_contact_fields_only_in_approved_facility_contact_workflows",
        ),
    },
    {
        "risk_id": "stale_source_data",
        "severity": "medium",
        "threat": "Operators may treat stale, seeded, proxy, or fallback source data as production evidence.",
        "mitigations": (
            "freshness_state_per_feed",
            "truth_state_badges",
            "block_confirmation_on_source_audit_failures",
            "show_demo_proxy_fallback_states_in_overview_and_feed_detail",
        ),
    },
    {
        "risk_id": "duplicate_import",
        "severity": "medium",
        "threat": "The same source file or metadata period may be imported more than once, double-counting evidence.",
        "mitigations": (
            "sha256_file_hash",
            "idempotency_key",
            "duplicate_metadata_checks",
            "explicit_replay_mode",
            "domain_run_linkage_in_upload_batch",
        ),
    },
    {
        "risk_id": "unauthorized_replacement",
        "severity": "high",
        "threat": (
            "A single operator could replace, replay, or backfill production evidence without "
            "independent approval."
        ),
        "mitigations": (
            "role_based_policy",
            "maker_checker_for_risky_categories",
            "self_approval_blocked",
            "approval_event_log",
            "replacement_reason_required",
        ),
    },
    {
        "risk_id": "downstream_leakage",
        "severity": "high",
        "threat": "Label or feature rebuilds could use future labels or records after the prediction cutoff.",
        "mitigations": (
            "explicit_as_of_for_rebuilds",
            "source_cutoff_inputs_required",
            "leakage_check_results_persisted",
            "manual_model_promotion_only",
        ),
    },
)

UX_BLUEPRINT: dict[str, Any] = {
    "navigation": {
        "label": "Source Data",
        "href": "/source-data",
        "placement": "dashboard_primary_nav_after_interoperability_before_chv_operations",
        "roles": (User.ROLE_ADMIN, User.ROLE_SUPERVISOR, User.ROLE_ANALYST),
    },
    "views": {
        "overview": {
            "purpose": "Show feed freshness, truth state, templates, recent uploads, and blocking source risks.",
            "table_columns": (
                "feed",
                "domain",
                "freshness",
                "truth_state",
                "last_successful_import",
                "next_expected",
                "owner",
                "latest_batch_status",
            ),
            "row_actions": ("download_template", "upload_csv", "view_history", "view_feed_detail"),
        },
        "feed_detail": {
            "purpose": (
                "Show one feed's cadence, schema contract, history, validation outcomes, "
                "and downstream actions."
            ),
            "table_columns": (
                "batch",
                "source_name",
                "source_timestamp",
                "period_or_release",
                "status",
                "rows",
                "warnings",
                "confirmed_by",
                "domain_run",
            ),
            "row_actions": ("view_batch", "download_errors", "request_replay", "open_downstream_actions"),
        },
        "upload_wizard": {
            "steps": ("choose_feed", "upload_file_and_metadata", "dry_validate", "confirm_import"),
            "required_controls": (
                "template_download",
                "source_metadata_form",
                "validation_polling",
                "approval_state",
                "confirm_reason",
            ),
        },
        "validation_summary": {
            "sections": (
                "accepted_rows",
                "rejected_rows",
                "warnings",
                "date_coverage",
                "ward_or_facility_coverage",
                "duplicate_detection",
                "pii_safety",
                "downstream_impact",
            ),
        },
        "import_result": {
            "sections": (
                "status_timeline",
                "domain_ingestion_run",
                "row_counts",
                "approval_decision",
                "recommended_downstream_action",
                "audit_log",
            ),
        },
    },
    "states": {
        "empty": "No uploads or source runs exist yet; show first safe action and template download.",
        "loading": "Use compact skeleton rows and preserve page structure while polling.",
        "failed": "Show failure reason, retry eligibility, and safe correction path without hiding previous success.",
        "stale": "Show stale badge, last successful source timestamp, expected cadence, and owner action.",
        "demo_backed": "Show seeded, proxy, or fallback truth state as non-production evidence.",
        "success": "Show imported status, domain run, row counts, and next safe downstream action.",
    },
}


def feed_decisions_for_scope(scope: str) -> tuple[SourceDataFeedDecision, ...]:
    return tuple(feed for feed in SOURCE_DATA_FEED_DECISIONS if feed.scope == scope)


def mvp_feed_decisions() -> tuple[SourceDataFeedDecision, ...]:
    return feed_decisions_for_scope(FEED_SCOPE_MVP)


def later_feed_decisions() -> tuple[SourceDataFeedDecision, ...]:
    return feed_decisions_for_scope(FEED_SCOPE_LATER)


def feed_decision_for_key(feed_key: str) -> SourceDataFeedDecision:
    for feed in SOURCE_DATA_FEED_DECISIONS:
        if feed.feed_key == feed_key:
            return feed
    raise KeyError(feed_key)


def validate_phase0_contract() -> list[str]:
    errors: list[str] = []
    feed_keys = [feed.feed_key for feed in SOURCE_DATA_FEED_DECISIONS]
    duplicate_feed_keys = sorted({feed_key for feed_key in feed_keys if feed_keys.count(feed_key) > 1})
    if duplicate_feed_keys:
        errors.append(f"duplicate_feed_keys:{','.join(duplicate_feed_keys)}")

    mvp_feeds = mvp_feed_decisions()
    if len(mvp_feeds) != 11:
        errors.append(f"mvp_feed_count_expected_11:{len(mvp_feeds)}")

    surveillance_source_types = {choice[0] for choice in SurveillanceSource.SOURCE_TYPE_CHOICES}
    population_exposure_source_types = {choice[0] for choice in PopulationExposureSource.SOURCE_TYPE_CHOICES}
    for feed in mvp_feeds:
        if (
            feed.ingestion_family == INGESTION_FAMILY_SURVEILLANCE
            and feed.source_type not in surveillance_source_types
        ):
            errors.append(f"unsupported_surveillance_source_type:{feed.feed_key}:{feed.source_type}")
        if (
            feed.ingestion_family == INGESTION_FAMILY_POPULATION_EXPOSURE
            and feed.source_type not in population_exposure_source_types
        ):
            errors.append(f"unsupported_population_exposure_source_type:{feed.feed_key}:{feed.source_type}")
        if not feed.required_metadata:
            errors.append(f"missing_required_metadata:{feed.feed_key}")

    readiness = feed_decision_for_key("facility_readiness_snapshot")
    if not readiness.requires_new_ingestion_path:
        errors.append("facility_readiness_snapshot_must_mark_new_ingestion_path")

    for role in (User.ROLE_ADMIN, User.ROLE_SUPERVISOR, User.ROLE_ANALYST, User.ROLE_CHV, "SUPERUSER"):
        if role not in ROLE_PERMISSION_MAP:
            errors.append(f"missing_role_permission_map:{role}")

    unknown_actions = sorted(
        {
            action
            for permissions in ROLE_PERMISSION_MAP.values()
            for action in permissions
            if action not in SOURCE_DATA_ACTIONS
        }
    )
    if unknown_actions:
        errors.append(f"role_permission_unknown_actions:{','.join(unknown_actions)}")

    risky_policy = MAKER_CHECKER_POLICY["risky_import"]
    if not risky_policy["approval_required"]:
        errors.append("risky_import_approval_not_required")
    if risky_policy["self_approval_allowed"]:
        errors.append("risky_import_self_approval_allowed")
    for category in RISKY_IMPORT_CATEGORIES:
        if category not in risky_policy["risk_categories"]:
            errors.append(f"risky_import_category_missing_from_policy:{category}")

    for status in UPLOAD_LIFECYCLE_STATUSES:
        if status not in UPLOAD_STATUS_TRANSITIONS:
            errors.append(f"status_missing_transition_entry:{status}")
    if "imported" not in UPLOAD_STATUS_TRANSITIONS.get("confirming", ()):
        errors.append("confirming_must_transition_to_imported")

    raw_policy = RETENTION_POLICY["raw_upload_artifacts"]
    if not 30 <= raw_policy["default_days"] <= 90:
        errors.append("raw_upload_retention_outside_phase0_bounds")
    if RETENTION_POLICY["rejected_row_diagnostics"]["default_days"] > raw_policy["default_days"]:
        errors.append("diagnostic_retention_exceeds_raw_upload_retention")

    if not SOURCE_DATA_UPLOAD_STORAGE_DECISION["durable_between_web_and_worker"]:
        errors.append("upload_storage_not_shared_between_web_and_worker")
    if SOURCE_DATA_UPLOAD_STORAGE_DECISION["local_process_temp_files_allowed_for_queued_imports"]:
        errors.append("queued_import_local_temp_files_allowed")

    required_threats = {
        "malicious_file",
        "accidental_pii",
        "stale_source_data",
        "duplicate_import",
        "unauthorized_replacement",
    }
    threat_ids = {str(item.get("risk_id")) for item in THREAT_MODEL}
    missing_threats = sorted(required_threats - threat_ids)
    if missing_threats:
        errors.append(f"missing_threat_model_items:{','.join(missing_threats)}")

    required_views = {"overview", "feed_detail", "upload_wizard", "validation_summary", "import_result"}
    missing_views = sorted(required_views - set(UX_BLUEPRINT["views"].keys()))
    if missing_views:
        errors.append(f"missing_ux_views:{','.join(missing_views)}")

    required_states = {"empty", "loading", "failed", "stale", "demo_backed", "success"}
    missing_states = sorted(required_states - set(UX_BLUEPRINT["states"].keys()))
    if missing_states:
        errors.append(f"missing_ux_states:{','.join(missing_states)}")

    return errors
