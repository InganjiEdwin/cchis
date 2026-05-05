from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Iterable


SOURCE_DATA_PHASE_AUDIT_SCHEMA_VERSION = "source-data-phase-audit-v1"

CLAIMED_IMPLEMENTED = "claimed_implemented"
PLANNED_NOT_CLAIMED = "planned_not_claimed"

CHECK_PASSED = "passed"
CHECK_MISSING = "missing"
CHECK_INCOMPLETE = "incomplete"
CHECK_ACCEPTED_MISSING = "accepted_missing"
CHECK_ACCEPTED_INCOMPLETE = "accepted_incomplete"

PHASE_NAMES: dict[int, str] = {
    0: "Alignment, Threat Model, And UX Blueprint",
    1: "Backend Feed Registry And Templates",
    2: "Backend Upload Batch And Dry Validation",
    3: "Confirm Import And Ingestion History",
    4: "Source Freshness And Ops Overview",
    5: "Downstream Rebuild Controls",
    6: "Facility Readiness Snapshot Ingestion",
    7: "World-Class UX Polish And Operator Training",
    8: "Production Hardening",
    9: "API Integrations And CSV Reduction",
    10: "External Audit And Gap Closure",
}


@dataclass(frozen=True)
class ArtifactCheck:
    phase: int
    check_id: str
    path: str
    description: str
    required_substrings: tuple[str, ...] = ()
    forbidden_substrings: tuple[str, ...] = ()
    must_exist: bool = True


@dataclass(frozen=True)
class AcceptedGap:
    phase: int
    check_id: str
    owner: str
    reason: str
    expires_at: str


@dataclass(frozen=True)
class ArtifactCheckResult:
    phase: int
    check_id: str
    path: str
    description: str
    status: str
    missing_substrings: tuple[str, ...] = ()
    forbidden_substrings_present: tuple[str, ...] = ()
    accepted_gap: AcceptedGap | None = None
    acceptance_errors: tuple[str, ...] = ()

    @property
    def is_open_gap(self) -> bool:
        return self.status in {CHECK_MISSING, CHECK_INCOMPLETE} or bool(self.acceptance_errors)

    @property
    def is_accepted_gap(self) -> bool:
        return self.status in {CHECK_ACCEPTED_MISSING, CHECK_ACCEPTED_INCOMPLETE}


@dataclass(frozen=True)
class PhaseAuditContract:
    phase: int
    name: str
    claim_status: str
    checks: tuple[ArtifactCheck, ...]


@dataclass(frozen=True)
class PhaseAuditResult:
    phase: int
    name: str
    claim_status: str
    checks: tuple[ArtifactCheckResult, ...]
    gaps: tuple[str, ...]
    accepted_gaps: tuple[str, ...]


@dataclass(frozen=True)
class SourceDataPhaseAuditReport:
    schema_version: str
    repo_root: str
    generated_at: str
    phases: tuple[PhaseAuditResult, ...]
    summary: dict[str, int]

    @property
    def passed(self) -> bool:
        return all(not phase.gaps for phase in self.phases if phase.claim_status == CLAIMED_IMPLEMENTED)

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["passed"] = self.passed
        return payload


def _artifact(
    phase: int,
    check_id: str,
    path: str,
    description: str,
    *required_substrings: str,
    forbidden_substrings: tuple[str, ...] = (),
) -> ArtifactCheck:
    return ArtifactCheck(
        phase=phase,
        check_id=check_id,
        path=path,
        description=description,
        required_substrings=tuple(required_substrings),
        forbidden_substrings=tuple(forbidden_substrings),
    )


PHASE_AUDIT_CONTRACT: tuple[PhaseAuditContract, ...] = (
    PhaseAuditContract(
        phase=0,
        name=PHASE_NAMES[0],
        claim_status=CLAIMED_IMPLEMENTED,
        checks=(
            _artifact(
                0,
                "phase0_contract_module",
                "backend/risk/source_data/phase0.py",
                "Code-level contract covers feed scope, roles, lifecycle, storage, threat model, and UX.",
                "SOURCE_DATA_FEED_DECISIONS",
                "ROLE_PERMISSION_MAP",
                "MAKER_CHECKER_POLICY",
                "UPLOAD_LIFECYCLE_STATUSES",
                "SOURCE_DATA_UPLOAD_STORAGE_DECISION",
                "THREAT_MODEL",
                "UX_BLUEPRINT",
                "validate_phase0_contract",
            ),
            _artifact(
                0,
                "phase0_contract_tests",
                "backend/risk/test_source_data_phase0.py",
                "Phase 0 tests lock alignment, role, storage, retention, and lifecycle decisions.",
                "SourceDataPhaseZeroContractTests",
                "test_phase_zero_contract_is_self_consistent",
                "test_role_permissions_and_maker_checker_policy_are_locked",
                "test_lifecycle_retention_and_shared_storage_decisions_are_explicit",
            ),
            _artifact(
                0,
                "phase0_runtime_settings",
                "backend/core/settings.py",
                "Runtime settings expose source-data upload storage and retention decisions.",
                "SOURCE_DATA_UPLOAD_STORAGE_BACKEND",
                "SOURCE_DATA_UPLOAD_ROOT",
                "SOURCE_DATA_RAW_UPLOAD_RETENTION_DAYS",
                "SOURCE_DATA_REJECTED_DIAGNOSTIC_RETENTION_DAYS",
                "SOURCE_DATA_METADATA_AUDIT_RETENTION_DAYS",
            ),
            _artifact(
                0,
                "phase0_docker_shared_storage",
                "docker-compose.yml",
                "Docker Compose mounts durable shared upload storage into web and worker services.",
                "source_uploads:/var/lib/cchis/source_uploads",
                "source_uploads:",
            ),
            _artifact(
                0,
                "phase0_human_alignment_doc",
                "docs/SOURCE_DATA_OPS_PHASE0_ALIGNMENT.md",
                "Phase 0 has a human-readable alignment note.",
                "Source Data Ops Phase 0 Alignment",
                "MVP feeds",
                "Role Policy",
                "Threat Model",
                "UX Blueprint",
            ),
        ),
    ),
    PhaseAuditContract(
        phase=1,
        name=PHASE_NAMES[1],
        claim_status=CLAIMED_IMPLEMENTED,
        checks=(
            _artifact(
                1,
                "phase1_feed_registry",
                "backend/risk/source_data/registry.py",
                "MVP feed registry exposes source-data feed definitions from the Phase 0 contract.",
                "SOURCE_DATA_FEED_REGISTRY_SCHEMA_VERSION",
                "SourceDataFeedDefinition",
                "source_data_feed_definitions",
                "build_source_data_feed_types_payload",
            ),
            _artifact(
                1,
                "phase1_csv_templates",
                "backend/risk/source_data/templates.py",
                "CSV templates and template contract validation are available for source feeds.",
                "SOURCE_DATA_CSV_TEMPLATES",
                "build_source_data_csv_template_file",
                "validate_source_data_template_contract",
                "SOURCE_DATA_TEMPLATE_DOWNLOAD_EVENT",
            ),
            _artifact(
                1,
                "phase1_registry_template_api",
                "backend/risk/views.py",
                "Backend API exposes feed types and safe CSV template downloads.",
                "SourceDataFeedTypesAPIView",
                "SourceDataCSVTemplateFileAPIView",
                "build_source_data_feed_types_payload",
                "build_source_data_csv_template_file",
            ),
            _artifact(
                1,
                "phase1_registry_template_routes",
                "backend/risk/urls.py",
                "Backend routes publish feed registry and template endpoints.",
                "source-data/feed-types/",
                "source-data/templates/<str:feed_key>/",
                "source-data-feed-types",
                "source-data-template-file",
            ),
            _artifact(
                1,
                "phase1_frontend_bff_routes",
                "frontend/app/api/dashboard/source-data/feed-types/route.ts",
                "Dashboard BFF route forwards feed registry requests to the backend.",
                "fetchBackendJson<SourceDataFeedTypesResponse>",
                "/source-data/feed-types/",
                "Unable to load source-data feed types.",
            ),
            _artifact(
                1,
                "phase1_template_bff_route",
                "frontend/app/api/dashboard/source-data/templates/[feedKey]/route.ts",
                "Dashboard BFF route downloads CSV templates without exposing backend internals.",
                "fetchBackendJson<SourceDataCsvTemplateFileResponse>",
                "/source-data/templates/",
                "Unable to download source-data CSV template.",
            ),
            _artifact(
                1,
                "phase1_registry_template_tests",
                "backend/risk/test_source_data_phase1.py",
                "Phase 1 tests cover feed registry, template downloads, permissions, and unsafe feed keys.",
                "SourceDataPhaseOneRegistryTemplateTests",
                "test_feed_types_expose_every_mvp_feed_and_template_contract",
                "test_csv_template_file_is_downloadable_for_every_mvp_feed",
                "test_unsupported_template_feed_key_returns_safe_404",
            ),
        ),
    ),
    PhaseAuditContract(
        phase=2,
        name=PHASE_NAMES[2],
        claim_status=CLAIMED_IMPLEMENTED,
        checks=(
            _artifact(
                2,
                "phase2_upload_models",
                "backend/risk/models.py",
                "Durable upload batch, artifact, validation issue, and upload event models exist.",
                "class SourceDataUploadBatch",
                "class SourceDataUploadArtifact",
                "class SourceDataValidationIssue",
                "class SourceDataUploadEvent",
                "validation_celery_task_id",
                "surveillance_ingestion_run",
                "population_exposure_ingestion_run",
            ),
            _artifact(
                2,
                "phase2_upload_migration",
                "backend/risk/migrations/0071_source_data_upload_batches.py",
                "Upload tracking and audit tables are created by a migration.",
                "SourceDataUploadBatch",
                "SourceDataUploadArtifact",
                "SourceDataValidationIssue",
                "SourceDataUploadEvent",
                "risk_srcbatch_feed_created_idx",
            ),
            _artifact(
                2,
                "phase2_storage_helper",
                "backend/risk/source_data/uploads.py",
                "Upload storage uses shared durable storage, hashes, retention, and duplicate checks.",
                "create_source_data_upload_batch",
                "SOURCE_DATA_UPLOAD_ROOT",
                "SOURCE_DATA_UPLOAD_STORAGE_BACKEND",
                "SOURCE_DATA_RAW_UPLOAD_RETENTION_DAYS",
                "duplicate_metadata_upload_public_id",
                "latest_upload_artifact",
            ),
            _artifact(
                2,
                "phase2_dry_validation",
                "backend/risk/source_data/validation.py",
                "Dry validation wraps domain inspectors, rejects PII, enforces limits, and stores diagnostics.",
                "validate_source_data_upload_batch",
                "inspect_surveillance_csv",
                "inspect_population_exposure_csv",
                "pii_phone_value_detected",
                "unsafe_text_value_detected",
                "binary_file_detected",
                "MAX_FORMULA_INJECTION_ISSUES",
                "SOURCE_DATA_MAX_UPLOAD_ROWS",
                "sample_row_count",
                "build_source_data_upload_errors_csv",
                forbidden_substrings=(
                    '"sample_rows": inspection.get',
                    '"sample_rows": inspection["sample_rows"]',
                ),
            ),
            _artifact(
                2,
                "phase2_upload_serializers",
                "backend/risk/serializers.py",
                "Serializers validate upload metadata and expose safe validation diagnostics.",
                "SourceDataUploadCreateSerializer",
                "SourceDataUploadBatchSerializer",
                "SourceDataValidationIssueSerializer",
                "SOURCE_DATA_MAX_UPLOAD_SIZE_BYTES",
            ),
            _artifact(
                2,
                "phase2_upload_api_routes",
                "backend/risk/urls.py",
                "Upload create/list/detail, dry validation, and diagnostics endpoints are routed.",
                "source-data/uploads/",
                "source-data/uploads/<uuid:public_id>/",
                "source-data/uploads/<uuid:public_id>/validate/",
                "source-data/uploads/<uuid:public_id>/errors.csv/",
            ),
            _artifact(
                2,
                "phase2_upload_frontend_bff_routes",
                "frontend/app/api/dashboard/source-data/uploads/route.ts",
                "Dashboard BFF supports upload list and create flows.",
                "fetchBackendJson<SourceDataUploadListResponse>",
                "fetchBackendJson<SourceDataUploadBatchRecord>",
                "request.formData",
                "/source-data/uploads/",
            ),
            _artifact(
                2,
                "phase2_upload_tests",
                "backend/risk/test_source_data_phase2.py",
                "Phase 2 tests cover dry validation, role checks, PII checks, diagnostics, and no domain mutation.",
                "SourceDataPhaseTwoUploadDryValidationTests",
                "test_admin_or_supervisor_can_create_upload_batch_without_domain_mutation",
                "test_dry_validation_wraps_surveillance_inspector_and_stores_issues",
                "test_dry_validation_rejects_sampled_pii_values_before_domain_validation",
                "test_analyst_can_list_and_view_but_cannot_upload_or_validate",
            ),
        ),
    ),
    PhaseAuditContract(
        phase=3,
        name=PHASE_NAMES[3],
        claim_status=CLAIMED_IMPLEMENTED,
        checks=(
            _artifact(
                3,
                "phase3_confirm_import_service",
                "backend/risk/source_data/imports.py",
                "Confirm import service verifies validated artifacts and links domain ingestion runs.",
                "assert_source_data_upload_can_confirm",
                "request_source_data_upload_approval",
                "decide_source_data_upload_approval",
                "run_confirmed_source_data_import",
                "confirm_source_data_upload",
                "RISK_HISTORICAL_BACKFILL",
                "RISK_PRODUCTION_SURVEILLANCE_TRUTH",
                "truth_level_counts",
            ),
            _artifact(
                3,
                "phase3_confirm_import_views",
                "backend/risk/views.py",
                "Confirm, approval, and history APIs enforce source-data permissions.",
                "SourceDataUploadApprovalAPIView",
                "SourceDataUploadConfirmAPIView",
                "SourceDataUploadCancelAPIView",
                "SourceDataUploadListCreateAPIView",
                "cancel_source_data_upload_batch",
                "confirm_source_data_upload",
                "request_source_data_upload_approval",
            ),
            _artifact(
                3,
                "phase3_confirm_import_routes",
                "backend/risk/urls.py",
                "Backend routes expose approval and confirmation endpoints.",
                "source-data/uploads/<uuid:public_id>/approval/",
                "source-data/uploads/<uuid:public_id>/confirm/",
                "source-data/uploads/<uuid:public_id>/cancel/",
                "source-data-upload-approval",
                "source-data-upload-confirm",
                "source-data-upload-cancel",
            ),
            _artifact(
                3,
                "phase3_async_import_task",
                "backend/risk/tasks.py",
                "Celery task imports queued source-data batches and records failure evidence.",
                "import_source_data_upload_batch_task",
                "run_confirmed_source_data_import",
                "SourceDataUploadEvent.EVENT_IMPORT_FAILED",
                "celery_task_id",
            ),
            _artifact(
                3,
                "phase3_frontend_confirm_contract",
                "frontend/lib/dashboard.ts",
                "Frontend dashboard client supports approval, confirmation, and history operations.",
                "SourceDataApprovalPayload",
                "SourceDataConfirmPayload",
                "SourceDataCancelPayload",
                "approveSourceDataUploadViaBff",
                "confirmSourceDataUploadViaBff",
                "cancelSourceDataUploadViaBff",
                "fetchSourceDataUploadsViaBff",
            ),
            _artifact(
                3,
                "phase3_frontend_cancel_route",
                "frontend/app/api/dashboard/source-data/uploads/[publicId]/cancel/route.ts",
                "Dashboard BFF forwards upload cancellation requests.",
                "SourceDataCancelPayload",
                "/cancel/",
                "Unable to cancel source-data upload.",
            ),
            _artifact(
                3,
                "phase3_confirm_tests",
                "backend/risk/test_source_data_phase3.py",
                "Phase 3 tests cover clean imports, maker-checker approval, history, and analyst restrictions.",
                "SourceDataPhaseThreeConfirmImportHistoryTests",
                "test_clean_surveillance_upload_can_be_confirmed_and_linked_to_ingestion_run",
                "test_risky_backfill_requires_second_admin_approval_before_confirmation",
                "test_confirmed_surveillance_truth_requires_second_admin_approval",
                "test_analyst_can_view_history_but_cannot_confirm_or_approve",
                "test_upload_can_be_cancelled_before_import_and_audited",
            ),
        ),
    ),
    PhaseAuditContract(
        phase=4,
        name=PHASE_NAMES[4],
        claim_status=CLAIMED_IMPLEMENTED,
        checks=(
            _artifact(
                4,
                "phase4_freshness_service",
                "backend/risk/source_data/freshness.py",
                "Freshness service reports source status, truth state, gaps, and recent uploads without row data.",
                "SOURCE_DATA_FRESHNESS_SCHEMA_VERSION",
                "SOURCE_DATA_OVERVIEW_SCHEMA_VERSION",
                "build_source_data_freshness_payload",
                "build_source_data_overview_payload",
                "TRUTH_CSV_BACKED",
                "TRUTH_DEMO_BACKED",
            ),
            _artifact(
                4,
                "phase4_overview_api",
                "backend/risk/views.py",
                "Overview and freshness APIs are exposed to source-data roles.",
                "SourceDataOverviewAPIView",
                "SourceDataFreshnessAPIView",
                "build_source_data_overview_payload",
                "build_source_data_freshness_payload",
            ),
            _artifact(
                4,
                "phase4_overview_routes",
                "backend/risk/urls.py",
                "Backend routes expose overview and freshness endpoints.",
                "source-data/overview/",
                "source-data/freshness/",
                "source-data-overview",
                "source-data-freshness",
            ),
            _artifact(
                4,
                "phase4_frontend_routes",
                "frontend/app/api/dashboard/source-data/overview/route.ts",
                "Dashboard BFF route loads the source-data overview.",
                "fetchBackendJson<SourceDataOverviewResponse>",
                "/source-data/overview/",
                "Unable to load source-data overview.",
            ),
            _artifact(
                4,
                "phase4_frontend_client",
                "frontend/lib/dashboard.ts",
                "Frontend types and client functions model source freshness and source gaps.",
                "SourceDataFreshnessResponse",
                "SourceDataOverviewResponse",
                "fetchSourceDataFreshnessViaBff",
                "fetchSourceDataOverviewViaBff",
                "source_gaps",
            ),
            _artifact(
                4,
                "phase4_source_matrix_doc",
                "docs/CCHIS_DATA_SOURCE_FEEDS.md",
                "Source matrix documents live/API paths, current paths, and fallback truth states.",
                "CCHIS Data Source Feeds",
                "Source Matrix",
                "Current Local Coverage",
                "Admin CSV Responsibility",
                "API And Scheduled Fetch Responsibility",
            ),
            _artifact(
                4,
                "phase4_freshness_tests",
                "backend/risk/test_source_data_phase4.py",
                "Phase 4 tests cover freshness gaps, truth states, permissions, and row-data minimization.",
                "SourceDataPhaseFourFreshnessOverviewTests",
                "test_overview_exposes_feed_freshness_gaps_and_recent_imports_without_row_data",
                "test_freshness_is_lightweight_and_restricted_to_source_data_roles",
                "test_freshness_marks_domain_csv_ingestion_as_csv_backed_without_dashboard_upload",
            ),
        ),
    ),
    PhaseAuditContract(
        phase=5,
        name=PHASE_NAMES[5],
        claim_status=CLAIMED_IMPLEMENTED,
        checks=(
            _artifact(
                5,
                "phase5_downstream_service",
                "backend/risk/source_data/downstream.py",
                "Downstream action service exposes guarded rebuilds with leakage and no-promotion evidence.",
                "SOURCE_DATA_DOWNSTREAM_SCHEMA_VERSION",
                "SourceDataDownstreamActionDefinition",
                "ACTION_REGENERATE_SURVEILLANCE_LABELS",
                "ACTION_REBUILD_LEAD_TIME_FEATURES",
                "ACTION_RUN_SOURCE_AUDITS",
                "_require_explicit_as_of",
                "source_cutoff_as_of=as_of",
                "leakage_check",
                "triggers_sms",
                "promotes_model",
            ),
            _artifact(
                5,
                "phase5_downstream_api",
                "backend/risk/views.py",
                "Backend API exposes upload-scoped downstream actions.",
                "SourceDataUploadDownstreamActionsAPIView",
                "run_source_data_downstream_action",
                "SOURCE_DATA_DOWNSTREAM_SCHEMA_VERSION",
                "EVENT_DOWNSTREAM_ACTION_REQUESTED",
            ),
            _artifact(
                5,
                "phase5_downstream_route",
                "backend/risk/urls.py",
                "Backend route exposes upload downstream action endpoint.",
                "source-data/uploads/<uuid:public_id>/downstream-actions/",
                "source-data-upload-downstream-actions",
            ),
            _artifact(
                5,
                "phase5_frontend_downstream_route",
                "frontend/app/api/dashboard/source-data/uploads/[publicId]/downstream-actions/route.ts",
                "Dashboard BFF forwards downstream action requests.",
                "SourceDataDownstreamActionResponse",
                "/downstream-actions/",
                "Unable to run source-data downstream action.",
            ),
            _artifact(
                5,
                "phase5_downstream_tests",
                "backend/risk/test_source_data_phase5.py",
                "Phase 5 tests prove leakage-safe rebuilds, source audits, permissions, and production guardrails.",
                "SourceDataPhaseFiveDownstreamActionTests",
                "test_surveillance_import_can_regenerate_labels_with_cutoff_evidence",
                "test_population_import_can_request_feature_rebuild_with_leakage_proof",
                "source_cutoff_as_of",
                "test_audits_are_supported_without_triggering_scoring_sms_or_promotion",
                "test_downstream_actions_are_restricted_and_production_replacement_is_blocked",
            ),
        ),
    ),
    PhaseAuditContract(
        phase=6,
        name=PHASE_NAMES[6],
        claim_status=CLAIMED_IMPLEMENTED,
        checks=(
            _artifact(
                6,
                "phase6_readiness_models",
                "backend/risk/models.py",
                "Facility readiness ingestion and snapshot models are present and link to source-data uploads.",
                "class FacilityReadinessIngestionRun",
                "class FacilityReadinessSnapshot",
                "facility_readiness_ingestion_run_id",
                "FacilityReadinessFreshness",
                "FacilityReadinessState",
            ),
            _artifact(
                6,
                "phase6_readiness_migration",
                "backend/risk/migrations/0072_facility_readiness_snapshots.py",
                "Migration creates readiness source, ingestion run, and snapshot tables.",
                "FacilityReadinessSource",
                "FacilityReadinessIngestionRun",
                "FacilityReadinessSnapshot",
                "risk_facready_fac_rep_idx",
            ),
            _artifact(
                6,
                "phase6_readiness_ingestion",
                "backend/risk/facility_readiness_ingestion.py",
                "Readiness CSV ingestion validates facilities, source kind, freshness, and redacts unsafe notes.",
                "FACILITY_READINESS_ACCEPTED_COLUMNS",
                "ValidatedReadinessRow",
                "run_facility_readiness_snapshot_ingestion",
                "unknown_facility_code",
                "stockout_detected",
                "ensure_pii_safe_text",
            ),
            _artifact(
                6,
                "phase6_source_data_import_link",
                "backend/risk/source_data/imports.py",
                "Source-data confirm import can execute and link facility readiness ingestion runs.",
                "INGESTION_FAMILY_FACILITY_READINESS",
                "run_facility_readiness_snapshot_ingestion",
                "batch.domain_ingestion_run_type = \"facility_readiness\"",
                "facility_readiness_ingestion_run_id",
            ),
            _artifact(
                6,
                "phase6_readiness_template_registry",
                "backend/risk/source_data/templates.py",
                "Facility readiness snapshot has an upload template with operational columns.",
                "facility_readiness_snapshot",
                "ors_sachets_available",
                "service_disruption",
                "stockout_notes",
            ),
            _artifact(
                6,
                "phase6_readiness_tests",
                "backend/risk/test_source_data_phase6.py",
                "Phase 6 tests cover readiness import, validation, freshness, downstream recompute, and no promotion.",
                "SourceDataPhaseSixFacilityReadinessSnapshotTests",
                "test_readiness_snapshot_upload_imports_and_updates_source_backed_facility_intelligence",
                "test_unknown_facility_is_rejected_during_dry_validation",
                "test_stockout_and_service_disruption_are_warned_and_stored_as_capacity_concern",
                "test_downstream_action_recomputes_readiness_evidence_and_forecast_inputs_without_promotion",
            ),
        ),
    ),
    PhaseAuditContract(
        phase=7,
        name=PHASE_NAMES[7],
        claim_status=CLAIMED_IMPLEMENTED,
        checks=(
            _artifact(
                7,
                "phase7_validation_error_catalog",
                "backend/risk/source_data/validation.py",
                "Validation diagnostics have stable operator-facing codes and safe remediation text.",
                "SOURCE_DATA_VALIDATION_ERROR_CATALOG_SCHEMA_VERSION",
                "SOURCE_DATA_VALIDATION_ERROR_CATALOG",
                "source_data_validation_error_catalog",
                "operator_message",
                "remediation",
            ),
            _artifact(
                7,
                "phase7_validation_catalog_doc",
                "docs/SOURCE_DATA_VALIDATION_ERROR_CODES.md",
                "Operator validation error catalog is documented outside code.",
                "Source Data Validation Error Codes",
                "source-data-validation-error-catalog-v1",
                "pii_phone_value_detected",
                "formula_injection_value",
                "unknown_facility_code",
            ),
            _artifact(
                7,
                "phase7_serializer_redaction_contract",
                "backend/risk/serializers.py",
                "Serializers expose validation issues and source-data inputs through PII-safe contracts.",
                "SourceDataValidationIssueSerializer",
                "PiiSafeInputSerializerMixin",
                "safe_context",
                "SourceDataUploadCreateSerializer",
            ),
            _artifact(
                7,
                "phase7_frontend_operator_ui",
                "frontend/app/(dashboard)/source-data/page.tsx",
                "Source-data page includes polished operator states for feeds, validation, readiness, operations, and connectors.",
                "SourceDataPage",
                "Feed Registry",
                "Upload And Dry Validate",
                "Validation Summary",
                "Source Freshness",
                "Readiness",
                "Production Health",
                "connector",
            ),
            _artifact(
                7,
                "phase7_frontend_tests",
                "frontend/app/source-data-page.test.tsx",
                "Frontend tests cover source-data page state, templates, diagnostics, readiness, hardening, and connectors.",
                "SourceDataPage",
                "renders source-data feed cards with template download links",
                "renders readiness-specific validation summary",
                "validates required fields and rejected files before upload",
                "Production Health",
                "Downstream Actions",
                "sourceCutoffTimestampForUpload",
            ),
            _artifact(
                7,
                "phase7_security_tests",
                "backend/risk/test_source_data_phase7.py",
                "Phase 7 tests cover validation code contracts, redaction, role permissions, and diagnostics.",
                "SourceDataPhaseSevenUxSecurityContractTests",
                "test_feed_types_exposes_stable_validation_error_catalog_contract",
                "test_validation_issue_contract_redacts_direct_identifiers_from_response_and_csv",
                "test_generated_validation_issue_codes_are_documented",
                "test_role_permission_matrix_for_source_data_diagnostics",
            ),
        ),
    ),
    PhaseAuditContract(
        phase=8,
        name=PHASE_NAMES[8],
        claim_status=CLAIMED_IMPLEMENTED,
        checks=(
            _artifact(
                8,
                "phase8_runtime_settings",
                "backend/core/settings.py",
                "Runtime settings configure source-data rate limits, task SLAs, and operations alert thresholds.",
                "THROTTLE_SOURCE_DATA_UPLOAD",
                "THROTTLE_SOURCE_DATA_VALIDATE",
                "SOURCE_DATA_TASK_STALE_MINUTES",
                "SOURCE_DATA_OPERATIONS_ALERT_LOOKBACK_HOURS",
                "SOURCE_DATA_FAILED_IMPORT_ALERT_THRESHOLD",
                "source-data-upload-artifact-cleanup",
                "cleanup_source_data_upload_artifacts_task",
            ),
            _artifact(
                8,
                "phase8_operations_service",
                "backend/risk/source_data/operations.py",
                "Operations service reports metrics, stuck tasks, worker health, alerts, and retention cleanup.",
                "SOURCE_DATA_OPERATIONS_SCHEMA_VERSION",
                "SOURCE_DATA_ARTIFACT_CLEANUP_TASK_NAME",
                "cleanup_expired_source_data_artifacts",
                "build_source_data_operations_payload",
                "stuck_source_data_tasks",
                "backup_restore_reference",
            ),
            _artifact(
                8,
                "phase8_operations_api",
                "backend/risk/views.py",
                "Operations endpoint is available to source-data roles.",
                "SourceDataOperationsAPIView",
                "build_source_data_operations_payload",
                "source_data_upload",
                "source_data_validate",
            ),
            _artifact(
                8,
                "phase8_cleanup_task",
                "backend/risk/tasks.py",
                "Celery cleanup task removes expired artifacts and records worker heartbeat evidence.",
                "cleanup_source_data_upload_artifacts_task",
                "cleanup_expired_source_data_artifacts",
                "ETLHeartbeat",
            ),
            _artifact(
                8,
                "phase8_operations_route",
                "backend/risk/urls.py",
                "Backend route exposes source-data production operations health.",
                "source-data/operations/",
                "source-data-operations",
            ),
            _artifact(
                8,
                "phase8_runbook",
                "docs/SOURCE_DATA_PRODUCTION_RUNBOOK.md",
                "Production runbook documents rate limits, retention, health, retry, backup/restore, and security hooks.",
                "Source Data Production Runbook",
                "Rate Limits",
                "Artifact Retention",
                "Operations Health",
                "Feature Flags",
                "SOURCE_DATA_OPS_ENABLED",
                "Backup And Restore",
                "Security Hooks",
            ),
            _artifact(
                8,
                "phase8_hardening_tests",
                "backend/risk/test_source_data_phase8.py",
                "Phase 8 tests cover rate limiting, artifact cleanup, operations alerts, abuse cases, and duplicate attempts.",
                "SourceDataPhaseEightProductionHardeningTests",
                "test_upload_and_validation_endpoints_are_rate_limited",
                "test_artifact_cleanup_purges_expired_raw_files_and_records_worker_heartbeat",
                "test_artifact_cleanup_task_is_scheduled_by_celery_beat",
                "test_operations_endpoint_reports_metrics_alerts_stuck_tasks_and_retention_state",
                "test_upload_abuse_cases_are_blocked_without_leaking_raw_values",
                "hidden-formula.csv",
                "test_feature_flags_gate_source_data_ops_confirm_and_downstream_paths",
            ),
        ),
    ),
    PhaseAuditContract(
        phase=9,
        name=PHASE_NAMES[9],
        claim_status=CLAIMED_IMPLEMENTED,
        checks=(
            _artifact(
                9,
                "phase9_connector_models",
                "backend/risk/models.py",
                "Connector run and feed-mode override models persist API integration state.",
                "class SourceDataConnectorRun",
                "class SourceDataFeedModeOverride",
                "safe_metadata",
                "authoritative_connector_key",
            ),
            _artifact(
                9,
                "phase9_connector_migration",
                "backend/risk/migrations/0073_source_data_connectors.py",
                "Migration creates connector run and feed-mode override tables.",
                "SourceDataConnectorRun",
                "SourceDataFeedModeOverride",
                "risk_srcconn_key_started_idx",
            ),
            _artifact(
                9,
                "phase9_connector_service",
                "backend/risk/source_data/connectors.py",
                "Connector registry and refresh service fetch canonical CSV and reuse validation safely.",
                "SOURCE_DATA_CONNECTOR_REGISTRY_SCHEMA_VERSION",
                "SourceDataConnectorDefinition",
                "SOURCE_DATA_CONNECTORS",
                "run_source_data_connector_refresh",
                "build_source_data_connector_registry_payload",
                "FEATURE_API_CONNECTORS",
                "source_data_api_connectors_enabled",
                "credential_values_exposed",
            ),
            _artifact(
                9,
                "phase9_connector_api",
                "backend/risk/views.py",
                "Backend API exposes connector registry, refresh, and feed-mode controls.",
                "SourceDataConnectorRegistryAPIView",
                "SourceDataConnectorRefreshAPIView",
                "SourceDataFeedModeAPIView",
                "run_source_data_connector_refresh",
                "set_source_data_feed_mode_override",
            ),
            _artifact(
                9,
                "phase9_connector_routes",
                "backend/risk/urls.py",
                "Backend routes expose connector registry, refresh, and feed-mode endpoints.",
                "source-data/connectors/",
                "source-data/connectors/<str:connector_key>/refresh/",
                "source-data/feed-modes/<str:feed_key>/",
                "source-data-connectors",
                "source-data-feed-mode",
            ),
            _artifact(
                9,
                "phase9_connector_schedule",
                "backend/core/settings.py",
                "Celery beat schedules the DHIS2 source-data connector refresh while preserving safe skipped runs when unconfigured.",
                "SOURCE_DATA_SCHEDULED_CONNECTOR_KEYS",
                "dhis2_surveillance_weekly",
                "source-data-connector-",
                "run_source_data_connector_refresh_task",
                "SOURCE_DATA_CONNECTOR_REFRESH_HOUR",
            ),
            _artifact(
                9,
                "phase9_frontend_connector_client",
                "frontend/lib/dashboard.ts",
                "Frontend dashboard client can read connectors, refresh connectors, and update feed modes.",
                "SourceDataConnectorRegistryResponse",
                "refreshSourceDataConnectorViaBff",
                "updateSourceDataFeedModeViaBff",
                "credential_values_exposed",
            ),
            _artifact(
                9,
                "phase9_connector_docs",
                "docs/SOURCE_DATA_API_CONNECTORS.md",
                "API connector docs explain connector model, configuration, feed modes, and failure reporting.",
                "Source Data API Connectors",
                "Connector Model",
                "Configuration",
                "Feed Modes",
                "Audit And Failure Reporting",
            ),
            _artifact(
                9,
                "phase9_connector_tests",
                "backend/risk/test_source_data_phase9.py",
                "Phase 9 tests cover connector status, validation reuse, safe failures, feed modes, and permissions.",
                "SourceDataPhaseNineConnectorIntegrationTests",
                "test_feed_registry_exposes_connector_status_without_secret_values",
                "test_connector_refresh_creates_validated_upload_with_same_canonical_checks",
                "test_connector_failure_is_audited_and_uses_validation_diagnostics",
                "test_admin_can_disable_csv_when_api_connector_is_authoritative",
                "test_api_connector_flag_gates_connector_surface_and_restores_csv_fallback",
                "test_celery_schedule_includes_dhis2_connector_refresh",
            ),
        ),
    ),
    PhaseAuditContract(
        phase=10,
        name=PHASE_NAMES[10],
        claim_status=CLAIMED_IMPLEMENTED,
        checks=(
            _artifact(
                10,
                "phase10_plan_section",
                "docs/SOURCE_DATA_OPS_SURFACE_IMPLEMENTATION_PLAN.md",
                "The implementation plan includes Phase 10 external audit and gap closure.",
                "## Phase 10: External Audit And Gap Closure",
                "compare claimed implementation artifacts against the repository",
                "Gaps found by the audit are either plugged or explicitly accepted",
            ),
            _artifact(
                10,
                "phase10_auditor_module",
                "backend/risk/source_data/phase_auditor.py",
                "Runnable source-data phase auditor has a full phase contract and accepted-gap handling.",
                "run_source_data_phase_audit",
                "PHASE_AUDIT_CONTRACT",
                "IMPLEMENTATION_CLAIM_CHECKS",
                "SourceDataPhaseAuditReport",
                "AcceptedGap",
                "accepted_gaps",
            ),
            _artifact(
                10,
                "phase10_management_command",
                "backend/risk/management/commands/audit_source_data_phases.py",
                "Django management command runs the auditor outside normal request paths.",
                "run_source_data_phase_audit",
                "--repo-root",
                "--format",
                "--strict",
                "SOURCE_DATA_PHASE_AUDIT_REQUIRED",
                "Source-data phase audit",
            ),
            _artifact(
                10,
                "phase10_runtime_audit_mounts",
                "docker-compose.yml",
                "Backend runtime mounts monorepo evidence needed by the source-data phase auditor.",
                "./frontend:/frontend:ro",
                "./docs:/docs:ro",
                "./docker-compose.yml:/docker-compose.yml:ro",
            ),
            _artifact(
                10,
                "phase10_feature_flag_settings",
                "backend/core/settings.py",
                "Release feature flags are concrete runtime settings, not just plan text.",
                "SOURCE_DATA_OPS_ENABLED",
                "SOURCE_DATA_IMPORT_CONFIRM_ENABLED",
                "SOURCE_DATA_DOWNSTREAM_ACTIONS_ENABLED",
                "FACILITY_READINESS_SNAPSHOT_IMPORT_ENABLED",
                "SOURCE_DATA_API_CONNECTORS_ENABLED",
                "SOURCE_DATA_PHASE_AUDIT_REQUIRED",
            ),
            _artifact(
                10,
                "phase10_feature_flag_module",
                "backend/risk/source_data/features.py",
                "Source-data feature flags have reusable service-layer helpers and a structured payload.",
                "SOURCE_DATA_FEATURE_FLAGS",
                "SourceDataFeatureDisabledError",
                "source_data_feature_enabled",
                "require_source_data_feature",
                "source_data_feature_flags_payload",
            ),
            _artifact(
                10,
                "phase10_feature_flag_api_gates",
                "backend/risk/views.py",
                "Source-data API classes enforce release flags before executing protected workflows.",
                "SourceDataFeatureGateMixin",
                "SourceDataFeatureDisabled",
                "FEATURE_IMPORT_CONFIRM",
                "FEATURE_DOWNSTREAM_ACTIONS",
                "FEATURE_API_CONNECTORS",
            ),
            _artifact(
                10,
                "phase10_auditor_tests",
                "backend/risk/test_source_data_phase10.py",
                "Phase 10 tests prove full coverage, missing/incomplete gap detection, accepted gaps, and CLI JSON output.",
                "SourceDataPhaseTenAuditorTests",
                "test_auditor_lists_all_phases_and_passes_when_claimed_artifacts_exist",
                "test_auditor_reports_missing_claimed_artifact_as_gap",
                "test_auditor_reports_incomplete_claimed_artifact_as_gap",
                "test_accepted_gap_requires_owner_reason_and_expiry",
                "test_management_command_outputs_json_report",
            ),
        ),
    ),
)

IMPLEMENTATION_CLAIM_CHECKS: tuple[ArtifactCheck, ...] = tuple(
    check for phase_contract in PHASE_AUDIT_CONTRACT for check in phase_contract.checks
)


def default_repo_root() -> Path:
    module_path = Path(__file__).resolve()
    for parent in module_path.parents:
        if (parent / "backend" / "risk").exists() and (parent / "frontend").exists():
            return parent
        if (parent / "manage.py").exists():
            return parent
    return module_path.parents[2]


def _today() -> date:
    return date.today()


def _accepted_gap_errors(gap: AcceptedGap, *, today: date) -> tuple[str, ...]:
    errors: list[str] = []
    if not gap.owner.strip():
        errors.append("accepted_gap_owner_required")
    if not gap.reason.strip():
        errors.append("accepted_gap_reason_required")
    if not gap.expires_at.strip():
        errors.append("accepted_gap_expiry_required")
    else:
        try:
            expires_at = date.fromisoformat(gap.expires_at[:10])
        except ValueError:
            errors.append("accepted_gap_expiry_invalid")
        else:
            if expires_at < today:
                errors.append("accepted_gap_expired")
    return tuple(errors)


def _candidate_artifact_paths(repo_root: Path, artifact_path: str) -> tuple[Path, ...]:
    path = Path(artifact_path)
    candidates = [repo_root / path]
    parts = path.parts

    if parts and parts[0] == "backend":
        candidates.append(repo_root / Path(*parts[1:]))
    if parts and parts[0] in {"frontend", "docs"}:
        candidates.append(repo_root.parent / path)
        candidates.append(Path("/") / path)
    if len(parts) == 1:
        candidates.append(repo_root.parent / path)
        candidates.append(Path("/") / path)

    unique: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            unique.append(candidate)
    return tuple(unique)


def _resolve_artifact_path(repo_root: Path, artifact_path: str) -> Path:
    candidates = _candidate_artifact_paths(repo_root, artifact_path)
    return next((candidate for candidate in candidates if candidate.exists()), candidates[0])


def _evaluate_check(
    repo_root: Path,
    check: ArtifactCheck,
    *,
    accepted_gap: AcceptedGap | None,
    today: date,
) -> ArtifactCheckResult:
    artifact_path = _resolve_artifact_path(repo_root, check.path)
    missing_substrings: list[str] = []
    forbidden_substrings_present: list[str] = []

    if check.must_exist and not artifact_path.exists():
        status = CHECK_MISSING
        missing_substrings = list(check.required_substrings)
    else:
        content = artifact_path.read_text(encoding="utf-8") if artifact_path.exists() else ""
        if check.required_substrings:
            missing_substrings = [item for item in check.required_substrings if item not in content]
        if check.forbidden_substrings:
            forbidden_substrings_present = [
                item for item in check.forbidden_substrings if item in content
            ]
        status = CHECK_PASSED if not missing_substrings and not forbidden_substrings_present else CHECK_INCOMPLETE

    acceptance_errors: tuple[str, ...] = ()
    if status != CHECK_PASSED and accepted_gap is not None:
        acceptance_errors = _accepted_gap_errors(accepted_gap, today=today)
        if not acceptance_errors:
            status = CHECK_ACCEPTED_MISSING if status == CHECK_MISSING else CHECK_ACCEPTED_INCOMPLETE

    return ArtifactCheckResult(
        phase=check.phase,
        check_id=check.check_id,
        path=check.path,
        description=check.description,
        status=status,
        missing_substrings=tuple(missing_substrings),
        forbidden_substrings_present=tuple(forbidden_substrings_present),
        accepted_gap=accepted_gap,
        acceptance_errors=acceptance_errors,
    )


def _gap_summary(check: ArtifactCheckResult) -> str:
    detail = f"{check.check_id}:{check.status}:{check.path}"
    if check.forbidden_substrings_present:
        detail = f"{detail}:forbidden={','.join(check.forbidden_substrings_present)}"
    if check.acceptance_errors:
        detail = f"{detail}:acceptance_errors={','.join(check.acceptance_errors)}"
    return detail


def _default_contract() -> tuple[PhaseAuditContract, ...]:
    return PHASE_AUDIT_CONTRACT


def run_source_data_phase_audit(
    repo_root: str | Path | None = None,
    *,
    contract: Iterable[PhaseAuditContract] | None = None,
    accepted_gaps: Iterable[AcceptedGap] = (),
    today: date | None = None,
) -> SourceDataPhaseAuditReport:
    root = Path(repo_root) if repo_root is not None else default_repo_root()
    root = root.resolve()
    today = today or _today()
    contract_tuple = tuple(contract or _default_contract())
    accepted_gap_by_key = {(gap.phase, gap.check_id): gap for gap in accepted_gaps}

    phase_results: list[PhaseAuditResult] = []
    summary = {
        "phase_count": len(contract_tuple),
        "claimed_implemented_count": 0,
        "planned_not_claimed_count": 0,
        "check_count": 0,
        "passed_check_count": 0,
        "open_gap_count": 0,
        "accepted_gap_count": 0,
    }

    for phase_contract in contract_tuple:
        checks: list[ArtifactCheckResult] = []
        if phase_contract.claim_status == CLAIMED_IMPLEMENTED:
            summary["claimed_implemented_count"] += 1
        else:
            summary["planned_not_claimed_count"] += 1

        for check in phase_contract.checks:
            result = _evaluate_check(
                root,
                check,
                accepted_gap=accepted_gap_by_key.get((check.phase, check.check_id)),
                today=today,
            )
            checks.append(result)
            summary["check_count"] += 1
            if result.status == CHECK_PASSED:
                summary["passed_check_count"] += 1
            if result.is_open_gap:
                summary["open_gap_count"] += 1
            if result.is_accepted_gap:
                summary["accepted_gap_count"] += 1

        gaps = tuple(_gap_summary(check) for check in checks if check.is_open_gap)
        accepted = tuple(_gap_summary(check) for check in checks if check.is_accepted_gap)
        phase_results.append(
            PhaseAuditResult(
                phase=phase_contract.phase,
                name=phase_contract.name,
                claim_status=phase_contract.claim_status,
                checks=tuple(checks),
                gaps=gaps,
                accepted_gaps=accepted,
            )
        )

    return SourceDataPhaseAuditReport(
        schema_version=SOURCE_DATA_PHASE_AUDIT_SCHEMA_VERSION,
        repo_root=str(root),
        generated_at=today.isoformat(),
        phases=tuple(phase_results),
        summary=summary,
    )


def _main() -> int:
    parser = argparse.ArgumentParser(description="Audit source-data ops phase implementation claims.")
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repository root. Defaults to the current module's repo root.",
    )
    parser.add_argument("--json", action="store_true", help="Print the full audit report as JSON.")
    args = parser.parse_args()

    report = run_source_data_phase_audit(args.repo_root)
    if args.json:
        print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    else:
        print(f"Source-data phase audit: {'passed' if report.passed else 'failed'}")
        for phase in report.phases:
            print(
                f"Phase {phase.phase}: {phase.claim_status}, "
                f"checks={len(phase.checks)}, gaps={len(phase.gaps)}, accepted={len(phase.accepted_gaps)}"
            )
            for gap in phase.gaps:
                print(f"  - {gap}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(_main())
