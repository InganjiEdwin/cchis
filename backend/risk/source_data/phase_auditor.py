from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path


SOURCE_DATA_PHASE_AUDIT_SCHEMA_VERSION = "source-data-phase-audit-v1"

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
    must_exist: bool = True


@dataclass(frozen=True)
class ArtifactCheckResult:
    phase: int
    check_id: str
    path: str
    description: str
    status: str
    missing_substrings: tuple[str, ...] = ()


@dataclass(frozen=True)
class PhaseAuditResult:
    phase: int
    name: str
    claim_status: str
    checks: tuple[ArtifactCheckResult, ...]
    gaps: tuple[str, ...]


@dataclass(frozen=True)
class SourceDataPhaseAuditReport:
    schema_version: str
    repo_root: str
    phases: tuple[PhaseAuditResult, ...]

    @property
    def passed(self) -> bool:
        return all(not phase.gaps for phase in self.phases if phase.claim_status == "claimed_implemented")

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["passed"] = self.passed
        return payload


IMPLEMENTATION_CLAIM_CHECKS: tuple[ArtifactCheck, ...] = (
    ArtifactCheck(
        phase=0,
        check_id="phase0_contract_module",
        path="backend/risk/source_data/phase0.py",
        description=(
            "Phase 0 has a code-level contract for feed scope, roles, lifecycle, storage, "
            "threat model, and UX."
        ),
        required_substrings=(
            "SOURCE_DATA_FEED_DECISIONS",
            "ROLE_PERMISSION_MAP",
            "MAKER_CHECKER_POLICY",
            "UPLOAD_LIFECYCLE_STATUSES",
            "SOURCE_DATA_UPLOAD_STORAGE_DECISION",
            "THREAT_MODEL",
            "UX_BLUEPRINT",
            "validate_phase0_contract",
        ),
    ),
    ArtifactCheck(
        phase=0,
        check_id="phase0_contract_tests",
        path="backend/risk/test_source_data_phase0.py",
        description="Phase 0 contract tests lock the implementation decisions.",
        required_substrings=(
            "SourceDataPhaseZeroContractTests",
            "test_phase_zero_contract_is_self_consistent",
            "test_role_permissions_and_maker_checker_policy_are_locked",
            "test_lifecycle_retention_and_shared_storage_decisions_are_explicit",
        ),
    ),
    ArtifactCheck(
        phase=0,
        check_id="phase0_runtime_settings",
        path="backend/core/settings.py",
        description="Runtime settings expose source-data upload storage and retention decisions.",
        required_substrings=(
            "SOURCE_DATA_UPLOAD_STORAGE_BACKEND",
            "SOURCE_DATA_UPLOAD_ROOT",
            "SOURCE_DATA_RAW_UPLOAD_RETENTION_DAYS",
            "SOURCE_DATA_REJECTED_DIAGNOSTIC_RETENTION_DAYS",
            "SOURCE_DATA_METADATA_AUDIT_RETENTION_DAYS",
        ),
    ),
    ArtifactCheck(
        phase=0,
        check_id="phase0_docker_shared_storage",
        path="docker-compose.yml",
        description="Docker Compose mounts durable shared upload storage into web and worker services.",
        required_substrings=(
            "source_uploads:/var/lib/cchis/source_uploads",
            "source_uploads:",
        ),
    ),
    ArtifactCheck(
        phase=0,
        check_id="phase0_human_alignment_doc",
        path="docs/SOURCE_DATA_OPS_PHASE0_ALIGNMENT.md",
        description="Phase 0 has a human-readable alignment note.",
        required_substrings=(
            "Source Data Ops Phase 0 Alignment",
            "MVP feeds",
            "Role Policy",
            "Threat Model",
            "UX Blueprint",
        ),
    ),
    ArtifactCheck(
        phase=1,
        check_id="phase1_feed_registry",
        path="backend/risk/source_data/registry.py",
        description="Phase 1 exposes MVP source-data feed definitions from the Phase 0 contract.",
        required_substrings=(
            "SOURCE_DATA_FEED_REGISTRY_SCHEMA_VERSION",
            "SourceDataFeedDefinition",
            "source_data_feed_definitions",
            "build_source_data_feed_types_payload",
        ),
    ),
    ArtifactCheck(
        phase=1,
        check_id="phase1_csv_templates",
        path="backend/risk/source_data/templates.py",
        description="Phase 1 exposes CSV templates and validates template/feed contract completeness.",
        required_substrings=(
            "SOURCE_DATA_CSV_TEMPLATES",
            "build_source_data_csv_template_file",
            "validate_source_data_template_contract",
            "SOURCE_DATA_TEMPLATE_DOWNLOAD_EVENT",
        ),
    ),
    ArtifactCheck(
        phase=1,
        check_id="phase1_registry_template_api",
        path="backend/risk/views.py",
        description="Phase 1 API exposes feed types and safe CSV template downloads.",
        required_substrings=(
            "SourceDataFeedTypesAPIView",
            "SourceDataCSVTemplateFileAPIView",
            "build_source_data_feed_types_payload",
            "build_source_data_csv_template_file",
        ),
    ),
    ArtifactCheck(
        phase=1,
        check_id="phase1_registry_template_routes",
        path="backend/risk/urls.py",
        description="Phase 1 routes publish feed registry and template endpoints.",
        required_substrings=(
            "source-data/feed-types/",
            "source-data/templates/<str:feed_key>/",
            "source-data-feed-types",
            "source-data-template-file",
        ),
    ),
    ArtifactCheck(
        phase=1,
        check_id="phase1_registry_template_tests",
        path="backend/risk/test_source_data_phase1.py",
        description="Phase 1 tests cover feed registry, template downloads, permissions, and unsafe feed keys.",
        required_substrings=(
            "SourceDataPhaseOneRegistryTemplateTests",
            "test_feed_types_expose_every_mvp_feed_and_template_contract",
            "test_csv_template_file_is_downloadable_for_every_mvp_feed",
            "test_unsupported_template_feed_key_returns_safe_404",
        ),
    ),
    ArtifactCheck(
        phase=2,
        check_id="phase2_upload_models",
        path="backend/risk/models.py",
        description="Phase 2 has durable upload batch, artifact, validation issue, and upload event models.",
        required_substrings=(
            "class SourceDataUploadBatch",
            "class SourceDataUploadArtifact",
            "class SourceDataValidationIssue",
            "class SourceDataUploadEvent",
            "validation_celery_task_id",
            "surveillance_ingestion_run",
            "population_exposure_ingestion_run",
        ),
    ),
    ArtifactCheck(
        phase=2,
        check_id="phase2_upload_migration",
        path="backend/risk/migrations/0071_source_data_upload_batches.py",
        description="Phase 2 migration creates upload tracking and audit tables.",
        required_substrings=(
            "SourceDataUploadBatch",
            "SourceDataUploadArtifact",
            "SourceDataValidationIssue",
            "SourceDataUploadEvent",
            "risk_srcbatch_feed_created_idx",
        ),
    ),
    ArtifactCheck(
        phase=2,
        check_id="phase2_storage_helper",
        path="backend/risk/source_data/uploads.py",
        description="Phase 2 stores uploads in shared durable storage with hash, size, retention, and duplicate checks.",
        required_substrings=(
            "create_source_data_upload_batch",
            "SOURCE_DATA_UPLOAD_ROOT",
            "SOURCE_DATA_UPLOAD_STORAGE_BACKEND",
            "SOURCE_DATA_RAW_UPLOAD_RETENTION_DAYS",
            "duplicate_metadata_upload_public_id",
            "latest_upload_artifact",
        ),
    ),
    ArtifactCheck(
        phase=2,
        check_id="phase2_dry_validation",
        path="backend/risk/source_data/validation.py",
        description="Phase 2 dry validation wraps domain inspectors, rejects PII, enforces limits, and stores diagnostics.",
        required_substrings=(
            "validate_source_data_upload_batch",
            "inspect_surveillance_csv",
            "inspect_population_exposure_csv",
            "pii_phone_value_detected",
            "SOURCE_DATA_MAX_UPLOAD_ROWS",
            "build_source_data_upload_errors_csv",
        ),
    ),
    ArtifactCheck(
        phase=2,
        check_id="phase2_upload_serializers",
        path="backend/risk/serializers.py",
        description="Phase 2 serializers validate upload metadata and expose batch validation diagnostics.",
        required_substrings=(
            "SourceDataUploadCreateSerializer",
            "SourceDataUploadBatchSerializer",
            "SourceDataValidationIssueSerializer",
            "SOURCE_DATA_MAX_UPLOAD_SIZE_BYTES",
        ),
    ),
    ArtifactCheck(
        phase=2,
        check_id="phase2_upload_api_routes",
        path="backend/risk/urls.py",
        description="Phase 2 routes publish upload create/list/detail, dry validation, and diagnostics endpoints.",
        required_substrings=(
            "source-data/uploads/",
            "source-data/uploads/<uuid:public_id>/",
            "source-data/uploads/<uuid:public_id>/validate/",
            "source-data/uploads/<uuid:public_id>/errors.csv/",
        ),
    ),
    ArtifactCheck(
        phase=2,
        check_id="phase2_upload_tests",
        path="backend/risk/test_source_data_phase2.py",
        description="Phase 2 tests cover dry validation, role checks, PII checks, diagnostics, and no domain mutation.",
        required_substrings=(
            "SourceDataPhaseTwoUploadDryValidationTests",
            "test_admin_or_supervisor_can_create_upload_batch_without_domain_mutation",
            "test_dry_validation_wraps_surveillance_inspector_and_stores_issues",
            "test_dry_validation_rejects_sampled_pii_values_before_domain_validation",
            "test_analyst_can_list_and_view_but_cannot_upload_or_validate",
        ),
    ),
    ArtifactCheck(
        phase=10,
        check_id="phase10_plan_section",
        path="docs/SOURCE_DATA_OPS_SURFACE_IMPLEMENTATION_PLAN.md",
        description="The implementation plan includes Phase 10 external audit and gap closure.",
        required_substrings=(
            "## Phase 10: External Audit And Gap Closure",
            "compare claimed implementation artifacts against the repository",
            "Gaps found by the audit are either plugged or explicitly accepted",
        ),
    ),
    ArtifactCheck(
        phase=10,
        check_id="phase10_auditor_module",
        path="backend/risk/source_data/phase_auditor.py",
        description="Phase 10 has a runnable source-data phase auditor.",
        required_substrings=(
            "run_source_data_phase_audit",
            "IMPLEMENTATION_CLAIM_CHECKS",
            "SourceDataPhaseAuditReport",
        ),
    ),
    ArtifactCheck(
        phase=10,
        check_id="phase10_auditor_tests",
        path="backend/risk/test_source_data_phase_auditor.py",
        description="Phase 10 auditor tests prove missing claimed artifacts are reported as gaps.",
        required_substrings=(
            "SourceDataPhaseAuditorTests",
            "test_auditor_passes_when_claimed_phase_artifacts_exist",
            "test_auditor_reports_missing_claimed_artifact_as_gap",
        ),
    ),
)


def default_repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _evaluate_check(repo_root: Path, check: ArtifactCheck) -> ArtifactCheckResult:
    artifact_path = repo_root / check.path
    if check.must_exist and not artifact_path.exists():
        return ArtifactCheckResult(
            phase=check.phase,
            check_id=check.check_id,
            path=check.path,
            description=check.description,
            status="missing",
            missing_substrings=check.required_substrings,
        )

    missing_substrings: list[str] = []
    if check.required_substrings:
        content = artifact_path.read_text(encoding="utf-8") if artifact_path.exists() else ""
        missing_substrings = [item for item in check.required_substrings if item not in content]

    status = "passed" if not missing_substrings else "incomplete"
    return ArtifactCheckResult(
        phase=check.phase,
        check_id=check.check_id,
        path=check.path,
        description=check.description,
        status=status,
        missing_substrings=tuple(missing_substrings),
    )


def run_source_data_phase_audit(repo_root: str | Path | None = None) -> SourceDataPhaseAuditReport:
    root = Path(repo_root) if repo_root is not None else default_repo_root()
    root = root.resolve()
    checks_by_phase: dict[int, list[ArtifactCheckResult]] = {phase: [] for phase in PHASE_NAMES}
    for check in IMPLEMENTATION_CLAIM_CHECKS:
        checks_by_phase.setdefault(check.phase, []).append(_evaluate_check(root, check))

    phase_results: list[PhaseAuditResult] = []
    for phase, name in PHASE_NAMES.items():
        checks = tuple(checks_by_phase.get(phase, ()))
        claim_status = "claimed_implemented" if checks else "planned_not_claimed"
        gaps = tuple(
            f"{check.check_id}:{check.status}:{check.path}"
            for check in checks
            if check.status != "passed"
        )
        phase_results.append(
            PhaseAuditResult(
                phase=phase,
                name=name,
                claim_status=claim_status,
                checks=checks,
                gaps=gaps,
            )
        )

    return SourceDataPhaseAuditReport(
        schema_version=SOURCE_DATA_PHASE_AUDIT_SCHEMA_VERSION,
        repo_root=str(root),
        phases=tuple(phase_results),
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
            if phase.claim_status == "planned_not_claimed":
                print(f"Phase {phase.phase}: planned, no implementation claim")
                continue
            print(f"Phase {phase.phase}: {phase.claim_status}, gaps={len(phase.gaps)}")
            for gap in phase.gaps:
                print(f"  - {gap}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(_main())
