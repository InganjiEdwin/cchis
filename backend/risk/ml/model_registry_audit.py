"""Read-only integrity audit for the model artifact registry."""

from __future__ import annotations

from collections import Counter

from django.utils import timezone

from risk.models import (
    FeatureDataset,
    ModelGovernanceEvent,
    ModelRegistryApprovalState,
    ModelRegistryEntry,
    ModelRegistryLifecycleState,
    ModelRegistryPromotionState,
    ModelRun,
)

from .alignment import model_run_has_phase_4_promotion_metadata
from .model_artifacts import sanitized_artifact_evidence, verify_registry_artifact


MODEL_REGISTRY_AUDIT_SCHEMA_VERSION = "model-artifact-registry-audit-v1"
NOT_APPROVED_FOR_OPERATIONAL_USE = "NOT_APPROVED_FOR_OPERATIONAL_USE"
AUDIT_PASS = "pass"
AUDIT_WARNING = "warning"
AUDIT_FAIL = "fail"


def _check(check_id: str, status: str, answer: str, evidence: dict, gaps: list[str] | None = None) -> dict:
    return {
        "id": check_id,
        "status": status,
        "answer": answer,
        "evidence": evidence,
        "gaps": list(gaps or []),
    }


def _entry_ref(entry: ModelRegistryEntry) -> dict:
    return {
        "registry_entry_id": entry.id,
        "registry_entry_public_id": str(entry.public_id),
        "registry_version": str(entry.registry_version),
        "model_run_id": entry.model_run_id,
        "model_version": entry.model_version,
        "deployment_target": entry.deployment_target,
        "approval_state": entry.approval_state,
        "lifecycle_state": entry.lifecycle_state,
    }


def _entry_issues(entry: ModelRegistryEntry) -> list[str]:
    issues: list[str] = []
    model_run = getattr(entry, "model_run", None)
    if model_run is None:
        return ["model_run_missing"]
    if not entry.registry_version:
        issues.append("registry_version_missing")
    artifact = verify_registry_artifact(entry)
    issues.extend(item.get("code") for item in artifact.get("blockers", []))
    training = getattr(model_run, "training_feature_dataset", None)
    inference = getattr(model_run, "inference_feature_dataset", None)
    if training is None:
        issues.append("training_feature_dataset_missing")
    elif (
        entry.model_run.training_dataset_ref != training.dataset_ref
        or entry.training_feature_dataset_ref != training.dataset_ref
    ):
        issues.append("training_dataset_reference_mismatch")
    if inference is None:
        issues.append("inference_feature_dataset_missing")
    elif (
        entry.model_run.inference_dataset_ref != inference.dataset_ref
        or entry.inference_feature_dataset_ref != inference.dataset_ref
    ):
        issues.append("inference_dataset_reference_mismatch")
    label_ref = (entry.training_label_dataset_ref or "").strip()
    if not label_ref:
        issues.append("training_label_dataset_reference_missing")
    elif not FeatureDataset.objects.filter(dataset_ref=label_ref).exists():
        issues.append("training_label_dataset_not_found")
    run_contract = list(model_run.feature_keys or [])
    if entry.feature_schema_version != model_run.feature_schema_version:
        issues.append("feature_schema_version_mismatch")
    if not entry.feature_contract:
        issues.append("feature_contract_missing")
    elif list(entry.feature_contract) != run_contract:
        issues.append("feature_contract_model_run_mismatch")
    if training is not None and list(entry.feature_contract or []) != list(training.feature_keys or []):
        issues.append("feature_contract_training_dataset_mismatch")
    if entry.approval_state == ModelRegistryApprovalState.APPROVED:
        if not entry.approved_at or not (entry.approved_by or "").strip():
            issues.append("approved_entry_missing_approval_evidence")
        if not entry.governance_events.filter(event_type=ModelGovernanceEvent.EVENT_APPROVED).exists():
            issues.append("approved_entry_missing_approval_event")
    elif entry.approved_at is not None or (entry.approved_by or "").strip():
        issues.append("unapproved_entry_has_approval_evidence")
    if (
        entry.lifecycle_state != ModelRegistryLifecycleState.ACTIVE
        and entry.promotion_state == ModelRegistryPromotionState.ACTIVE_PROMOTED
    ):
        issues.append("non_active_entry_has_active_promotion_state")
    if entry.lifecycle_state == ModelRegistryLifecycleState.ACTIVE:
        if entry.approval_state != ModelRegistryApprovalState.APPROVED:
            issues.append("active_entry_not_approved")
        if entry.promotion_state != ModelRegistryPromotionState.ACTIVE_PROMOTED:
            issues.append("active_entry_promotion_state_mismatch")
        if not entry.promotion_event_id or not entry.governance_events.filter(
            event_type=ModelGovernanceEvent.EVENT_ACTIVATED
        ).exists():
            issues.append("active_entry_missing_activation_event")
        if not model_run_has_phase_4_promotion_metadata(model_run):
            issues.append("active_entry_missing_phase_4_gates")
        if entry.active_from is None or entry.active_until is not None:
            issues.append("active_entry_window_invalid")
    if entry.lifecycle_state == ModelRegistryLifecycleState.CHALLENGER:
        if not entry.challenger_of_id:
            issues.append("challenger_target_missing")
        elif (
            entry.challenger_of.approval_state != ModelRegistryApprovalState.APPROVED
            or entry.challenger_of.lifecycle_state != ModelRegistryLifecycleState.ACTIVE
        ):
            issues.append("challenger_target_not_active_approved")
    if entry.lifecycle_state == ModelRegistryLifecycleState.ROLLED_BACK and not entry.rollback_target_id:
        issues.append("rolled_back_entry_missing_explicit_target")
    if entry.rollback_target_id:
        rollback_target = entry.rollback_target
        if rollback_target is None:
            issues.append("rollback_target_unavailable")
        else:
            if rollback_target.approval_state != ModelRegistryApprovalState.APPROVED:
                issues.append("rollback_target_not_approved")
            if list(rollback_target.feature_contract or []) != list(entry.feature_contract or []):
                issues.append("rollback_target_feature_contract_mismatch")
            if not verify_registry_artifact(rollback_target).get("valid"):
                issues.append("rollback_target_artifact_unavailable")
    latest_event = entry.governance_events.order_by("-occurred_at", "-id").first()
    if latest_event is not None:
        if (
            latest_event.resulting_approval_state
            and latest_event.resulting_approval_state != entry.approval_state
        ):
            issues.append("latest_event_approval_state_mismatch")
        if (
            latest_event.resulting_lifecycle_state
            and latest_event.resulting_lifecycle_state != entry.lifecycle_state
        ):
            issues.append("latest_event_lifecycle_state_mismatch")
    if entry.approval_state == ModelRegistryApprovalState.APPROVED:
        from .model_registry_governance import model_artifact_approval_blockers

        issues.extend(f"approval_evidence:{code}" for code in model_artifact_approval_blockers(entry))
    return list(dict.fromkeys(issue for issue in issues if issue))


def build_model_registry_audit(*, strict: bool = False) -> dict:
    now = timezone.now()
    entries = list(
        ModelRegistryEntry.objects.select_related(
            "model_run",
            "model_run__training_feature_dataset",
            "model_run__inference_feature_dataset",
            "challenger_of",
            "rollback_target",
        ).order_by("id")
    )
    active_entries = [entry for entry in entries if entry.lifecycle_state == ModelRegistryLifecycleState.ACTIVE]
    active_target_counts = Counter(entry.deployment_target for entry in active_entries)
    duplicate_active_targets = {
        target: count for target, count in active_target_counts.items() if count > 1
    }
    entry_findings = [
        {
            **_entry_ref(entry),
            "issues": _entry_issues(entry),
            "artifact": sanitized_artifact_evidence(entry),
        }
        for entry in entries
    ]
    invalid_entries = [item for item in entry_findings if item["issues"]]
    registry_version_counts = Counter(str(entry.registry_version) for entry in entries)
    duplicate_registry_versions = {
        version: count for version, count in registry_version_counts.items() if count > 1
    }
    operational_runs_without_active_entry = []
    for run in ModelRun.objects.filter(status=ModelRun.STATUS_SUCCESS).select_related("registry_entry"):
        if not model_run_has_phase_4_promotion_metadata(run):
            continue
        try:
            linked_entry = run.registry_entry
        except ModelRegistryEntry.DoesNotExist:
            linked_entry = None
        if (
            linked_entry is None
            or linked_entry.approval_state != ModelRegistryApprovalState.APPROVED
            or linked_entry.lifecycle_state != ModelRegistryLifecycleState.ACTIVE
        ):
            operational_runs_without_active_entry.append(
                {"model_run_id": run.id, "model_version": run.model_version}
            )

    checks = [
        _check(
            "registry_entry_integrity",
            AUDIT_FAIL if invalid_entries else AUDIT_PASS,
            "Registered entries have resolvable run, dataset, contract, artifact, and lifecycle evidence."
            if not invalid_entries
            else "One or more registry entries have incomplete or inconsistent evidence.",
            {"entry_count": len(entries), "invalid_entry_count": len(invalid_entries), "entries": invalid_entries[:50]},
            ["registry_entry_integrity_failed"] if invalid_entries else [],
        ),
        _check(
            "one_active_model_per_deployment_target",
            AUDIT_FAIL if duplicate_active_targets else AUDIT_PASS,
            "There is at most one active entry per deployment target."
            if not duplicate_active_targets
            else "More than one active entry exists for a deployment target.",
            {"active_target_counts": dict(active_target_counts), "duplicate_active_targets": duplicate_active_targets},
            ["multiple_active_models_for_target"] if duplicate_active_targets else [],
        ),
        _check(
            "governance_event_immutability_and_provenance",
            AUDIT_FAIL
            if any(
                entry.approval_state in {ModelRegistryApprovalState.APPROVED}
                and not entry.governance_events.exists()
                for entry in entries
            )
            else AUDIT_PASS,
            "Governed state changes have persisted event provenance."
            if not any(
                entry.approval_state == ModelRegistryApprovalState.APPROVED and not entry.governance_events.exists()
                for entry in entries
            )
            else "An approved entry has no governance event history.",
            {
                "event_count": ModelGovernanceEvent.objects.count(),
                "approved_entries_without_events": [entry.id for entry in entries if entry.approval_state == ModelRegistryApprovalState.APPROVED and not entry.governance_events.exists()],
            },
            ["approved_entry_event_history_missing"]
            if any(entry.approval_state == ModelRegistryApprovalState.APPROVED and not entry.governance_events.exists() for entry in entries)
            else [],
        ),
        _check(
            "registry_version_uniqueness",
            AUDIT_FAIL if duplicate_registry_versions else AUDIT_PASS,
            "Registry versions are unique."
            if not duplicate_registry_versions
            else "Duplicate registry versions are present.",
            {"duplicate_registry_versions": duplicate_registry_versions},
            ["duplicate_registry_version"] if duplicate_registry_versions else [],
        ),
        _check(
            "production_runs_linked_to_approved_active_registry",
            AUDIT_FAIL if operational_runs_without_active_entry else AUDIT_PASS,
            "Phase 4 operational model runs are linked to approved active entries."
            if not operational_runs_without_active_entry
            else "A Phase 4 operational model run is not linked to an approved active registry entry.",
            {
                "unlinked_operational_run_count": len(operational_runs_without_active_entry),
                "unlinked_operational_runs": operational_runs_without_active_entry[:50],
            },
            ["production_model_run_missing_approved_active_registry"]
            if operational_runs_without_active_entry
            else [],
        ),
    ]
    fail_count = sum(check["status"] == AUDIT_FAIL for check in checks)
    warning_count = sum(check["status"] == AUDIT_WARNING for check in checks)
    active_model_count = len(active_entries)
    operational_active_entries = [
        entry for entry in active_entries if entry.deployment_target == "live_baseline"
    ]
    operational_model_available = bool(operational_active_entries)
    readiness = (
        NOT_APPROVED_FOR_OPERATIONAL_USE
        if not operational_model_available
        else "OPERATIONAL_MODEL_AVAILABLE_PENDING_RUNTIME_CHECKS"
    )
    return {
        "schema_version": MODEL_REGISTRY_AUDIT_SCHEMA_VERSION,
        "generated_at": now,
        "overall_status": AUDIT_FAIL if fail_count else (AUDIT_WARNING if warning_count else AUDIT_PASS),
        "summary": {
            "check_count": len(checks),
            "passed_check_count": sum(check["status"] == AUDIT_PASS for check in checks),
            "warning_check_count": warning_count,
            "failed_check_count": fail_count,
            "registered_entry_count": len(entries),
            "active_model_count": active_model_count,
            "operational_model_available": operational_model_available,
        },
        "readiness": {
            "active_model_count": active_model_count,
            "operational_model_available": operational_model_available,
            "readiness": readiness,
        },
        "strict": strict,
        "checks": checks,
    }
