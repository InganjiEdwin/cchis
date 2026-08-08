"""Explicit model-artifact registry transitions.

This module is deliberately boring: every state change requires an identified
actor and a reason, and an append-only event is written in the same transaction.
It never loads a model artifact.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from django.db import transaction
from django.utils import timezone

from risk.models import (
    FeatureDataset,
    ModelGovernanceEvent,
    ModelPromotionEvent,
    ModelRegistryApprovalState,
    ModelRegistryEntry,
    ModelRegistryLifecycleState,
    ModelRegistryMonitoringState,
    ModelRegistryPromotionState,
    ModelRun,
)

from .alignment import model_run_has_phase_4_promotion_metadata
from .model_artifacts import inspect_artifact, sanitized_artifact_evidence, verify_registry_artifact
from .model_governance_identity import (
    MODEL_REGISTRY_GOVERNANCE_ROLES,
    MODEL_REGISTRY_REQUEST_ROLES,
    ModelGovernanceIdentityError,
    actor_identity_snapshot,
    resolve_governance_actor,
)
from .registry import _lock_deployment_target, default_review_due_date
from risk.surveillance_lineage import dataset_is_currently_eligible


OPERATIONAL_DEPLOYMENT_TARGET = "live_baseline"
ALLOWED_DEPLOYMENT_TARGETS = frozenset({OPERATIONAL_DEPLOYMENT_TARGET, "benchmark_only", "demo_only"})


class ModelRegistryGovernanceError(ValueError):
    def __init__(self, code: str, detail: str = ""):
        self.code = code
        self.detail = detail or code
        super().__init__(self.detail)


def _required_actor_reason(
    actor,
    reason: str,
    *,
    required_roles=frozenset(MODEL_REGISTRY_REQUEST_ROLES),
):
    reason = (reason or "").strip()
    if not reason:
        raise ModelRegistryGovernanceError("governance_reason_required")
    try:
        actor_user = resolve_governance_actor(actor, required_roles=required_roles)
    except ModelGovernanceIdentityError as error:
        raise ModelRegistryGovernanceError(error.code, error.detail) from error
    return actor_user, actor_user.get_username(), reason


def _event_snapshot(entry: ModelRegistryEntry, *, artifact_inspection: dict | None = None) -> dict:
    return {
        "registry_entry_id": entry.id,
        "registry_entry_public_id": str(entry.public_id),
        "registry_version": str(entry.registry_version),
        "model_run_id": entry.model_run_id,
        "model_version": entry.model_version,
        "feature_schema_version": entry.feature_schema_version,
        "algorithm": entry.algorithm,
        "model_family": entry.model_family,
        "deployment_target": entry.deployment_target,
        "training_dataset_ref": entry.model_run.training_dataset_ref,
        "inference_dataset_ref": entry.model_run.inference_dataset_ref,
        "training_feature_dataset_ref": entry.training_feature_dataset_ref,
        "inference_feature_dataset_ref": entry.inference_feature_dataset_ref,
        "training_label_dataset_ref": entry.training_label_dataset_ref,
        "feature_contract": list(entry.feature_contract or []),
        "metrics": dict(entry.metrics or {}),
        "artifact": sanitized_artifact_evidence(entry, artifact_inspection),
        "approval_state": entry.approval_state,
        "lifecycle_state": entry.lifecycle_state,
        "promotion_state": entry.promotion_state,
    }


def _record_event(
    *,
    entry: ModelRegistryEntry,
    event_type: str,
    actor_user,
    actor: str,
    reason: str,
    previous_approval_state: str = "",
    previous_lifecycle_state: str = "",
    previous_promotion_state: str = "",
    evidence_snapshot: dict | None = None,
    request_id: str = "",
) -> ModelGovernanceEvent:
    snapshot = dict(evidence_snapshot or _event_snapshot(entry))
    snapshot.setdefault("actor_identity", actor_identity_snapshot(actor_user))
    return ModelGovernanceEvent.objects.create(
        registry_entry=entry,
        event_type=event_type,
        actor=actor,
        actor_user=actor_user,
        reason=reason,
        previous_approval_state=previous_approval_state,
        resulting_approval_state=entry.approval_state,
        previous_lifecycle_state=previous_lifecycle_state,
        resulting_lifecycle_state=entry.lifecycle_state,
        previous_promotion_state=previous_promotion_state,
        resulting_promotion_state=entry.promotion_state,
        evidence_snapshot=snapshot,
        request_id=(request_id or "").strip(),
    )


def _metadata_label_ref(metadata: dict) -> str:
    for key in (
        "surveillance_label_dataset_ref",
        "ward_risk_classification_label_dataset_ref",
        "training_label_dataset_ref",
        "label_dataset_ref",
    ):
        value = str(metadata.get(key) or "").strip()
        if value:
            return value
    evidence_binding = metadata.get("phase_4_promotion_evidence_binding") or {}
    if isinstance(evidence_binding, dict):
        return str(evidence_binding.get("report_label_dataset_ref") or "").strip()
    return ""


def _parse_datetime(value) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return timezone.make_aware(parsed) if timezone.is_naive(parsed) else parsed


def _feature_contract(model_run: ModelRun) -> list[str]:
    return [str(value) for value in (model_run.feature_keys or []) if str(value).strip()]


def _artifact_location_from_path(path: str) -> str:
    resolved = str(Path(path).expanduser().resolve(strict=True))
    return f"file://{quote(resolved, safe='/:._-~')}"


def register_model_artifact(
    *,
    model_run: ModelRun,
    artifact_path: str,
    actor: str,
    reason: str,
    deployment_target: str = OPERATIONAL_DEPLOYMENT_TARGET,
    artifact_format: str = "",
    request_id: str = "",
) -> ModelRegistryEntry:
    actor_user, actor, reason = _required_actor_reason(actor, reason)
    if deployment_target not in ALLOWED_DEPLOYMENT_TARGETS:
        raise ModelRegistryGovernanceError("deployment_target_unsupported")
    if model_run is None or model_run.status != ModelRun.STATUS_SUCCESS:
        raise ModelRegistryGovernanceError("model_run_not_success")

    try:
        location = _artifact_location_from_path(artifact_path)
    except (OSError, RuntimeError, ValueError) as error:
        raise ModelRegistryGovernanceError("artifact_not_found") from error
    inspection = inspect_artifact(location=location, artifact_format=artifact_format, expected_sha256="")
    if inspection.get("blockers"):
        codes = [item.get("code") for item in inspection["blockers"]]
        if codes == ["artifact_sha256_required"]:
            # Registration computes the digest; a caller does not get to supply
            # a potentially stale value in place of the persisted digest.
            inspection = inspect_artifact(
                location=location,
                artifact_format=artifact_format,
                expected_sha256=inspection.get("artifact_sha256", ""),
            )
        else:
            raise ModelRegistryGovernanceError(codes[0] or "artifact_integrity_failed")
    if not inspection.get("artifact_sha256"):
        raise ModelRegistryGovernanceError("artifact_integrity_failed")

    metadata = dict(model_run.metadata or {})
    training_dataset = getattr(model_run, "training_feature_dataset", None)
    feature_contract = _feature_contract(model_run)
    label_ref = _metadata_label_ref(metadata)
    registry_version_seed = f"{model_run.model_version}-{inspection['artifact_sha256'][:12]}"

    with transaction.atomic():
        if ModelRegistryEntry.objects.filter(model_run_id=model_run.id).exists():
            raise ModelRegistryGovernanceError("model_run_already_registered")
        if ModelRegistryEntry.objects.filter(registry_version=registry_version_seed[:36]).exists():
            raise ModelRegistryGovernanceError("registry_version_already_registered")
        entry = ModelRegistryEntry.objects.create(
            registry_version=registry_version_seed[:36],
            algorithm=(metadata.get("algorithm") or model_run.algorithm_name)[:80],
            model_family=str(metadata.get("model_family") or "ward_risk_classification")[:120],
            model_version=model_run.model_version,
            feature_schema_version=model_run.feature_schema_version,
            model_run=model_run,
            approval_state=ModelRegistryApprovalState.NOT_REVIEWED,
            lifecycle_state=ModelRegistryLifecycleState.CANDIDATE,
            promotion_state=ModelRegistryPromotionState.CANDIDATE,
            deployment_target=deployment_target,
            artifact_location=location,
            artifact_format=inspection["artifact_format"],
            artifact_size_bytes=inspection["artifact_size_bytes"],
            artifact_sha256=inspection["artifact_sha256"],
            training_feature_dataset_ref=(training_dataset.dataset_ref if training_dataset else ""),
            inference_feature_dataset_ref=(
                model_run.inference_feature_dataset.dataset_ref
                if model_run.inference_feature_dataset
                else ""
            ),
            training_label_dataset_ref=label_ref,
            feature_contract=feature_contract,
            code_commit=str(
                metadata.get("code_commit") or metadata.get("git_commit") or metadata.get("commit_sha") or ""
            )[:160],
            training_started_at=model_run.started_at,
            training_completed_at=model_run.completed_at,
            evaluation_started_at=_parse_datetime(metadata.get("evaluation_started_at")),
            evaluation_completed_at=_parse_datetime(metadata.get("evaluation_completed_at")) or model_run.completed_at,
            metrics=dict(model_run.evaluation_metrics or {}),
            truth_source_classification=str(metadata.get("truth_source_classification") or "unverified")[:80],
            intended_use=str(metadata.get("intended_use") or "ward-risk-classification")[:10000],
            prohibited_uses=list(metadata.get("prohibited_uses") or ["unreviewed operational alerting"]),
            registration_reason=reason,
            metadata={
                "registry_schema_version": "model-artifact-registry-v1",
                "source": "register_model_artifact",
                "training_feature_dataset_id": training_dataset.id if training_dataset else None,
            },
            owner=actor,
            monitoring_state=ModelRegistryMonitoringState.NOT_CONFIGURED,
        )
        _record_event(
            entry=entry,
            event_type=ModelGovernanceEvent.EVENT_REGISTERED,
            actor_user=actor_user,
            actor=actor,
            reason=reason,
            evidence_snapshot=_event_snapshot(entry, artifact_inspection=inspection),
            request_id=request_id,
        )
        return entry


def _entry_for_update(entry_id: int) -> ModelRegistryEntry:
    try:
        return (
            ModelRegistryEntry.objects.select_for_update()
            .select_related("model_run")
            .get(id=entry_id)
        )
    except ModelRegistryEntry.DoesNotExist as error:
        raise ModelRegistryGovernanceError("registry_entry_not_found") from error


def request_model_approval(*, entry: ModelRegistryEntry, actor: str, reason: str, request_id: str = "") -> ModelRegistryEntry:
    actor_user, actor, reason = _required_actor_reason(actor, reason)
    with transaction.atomic():
        locked = _entry_for_update(entry.id)
        if locked.lifecycle_state not in {
            ModelRegistryLifecycleState.CANDIDATE,
            ModelRegistryLifecycleState.CHALLENGER,
        }:
            raise ModelRegistryGovernanceError("approval_request_invalid_lifecycle")
        if locked.approval_state == ModelRegistryApprovalState.PENDING_REVIEW:
            raise ModelRegistryGovernanceError("approval_request_already_pending")
        previous = locked.approval_state
        locked.approval_state = ModelRegistryApprovalState.PENDING_REVIEW
        locked.save(update_fields=["approval_state", "updated_at"])
        _record_event(
            entry=locked,
            event_type=ModelGovernanceEvent.EVENT_APPROVAL_REQUESTED,
            actor_user=actor_user,
            actor=actor,
            reason=reason,
            previous_approval_state=previous,
            previous_lifecycle_state=locked.lifecycle_state,
            previous_promotion_state=locked.promotion_state,
            request_id=request_id,
        )
        return locked


def resolve_registry_entry(reference: str | int) -> ModelRegistryEntry:
    value = str(reference or "").strip()
    if not value:
        raise ModelRegistryGovernanceError("registry_entry_reference_required")
    queryset = ModelRegistryEntry.objects.select_related("model_run")
    try:
        if value.isdigit():
            return queryset.get(id=int(value))
        return queryset.get(registry_version=value)
    except ModelRegistryEntry.DoesNotExist:
        try:
            return queryset.get(public_id=value)
        except (ModelRegistryEntry.DoesNotExist, ValueError) as error:
            raise ModelRegistryGovernanceError("registry_entry_not_found") from error


def model_artifact_approval_blockers(entry: ModelRegistryEntry) -> list[str]:
    blockers: list[str] = []
    model_run = getattr(entry, "model_run", None)
    if model_run is None:
        return ["model_run_missing"]
    if model_run.status != ModelRun.STATUS_SUCCESS:
        blockers.append("model_run_not_success")
    artifact = verify_registry_artifact(entry)
    blockers.extend(item.get("code") for item in artifact.get("blockers", []))
    training_dataset = getattr(model_run, "training_feature_dataset", None)
    inference_dataset = getattr(model_run, "inference_feature_dataset", None)
    if training_dataset is None:
        blockers.append("training_feature_dataset_missing")
    else:
        if (
            model_run.training_dataset_ref != training_dataset.dataset_ref
            or entry.training_feature_dataset_ref != training_dataset.dataset_ref
        ):
            blockers.append("training_dataset_reference_mismatch")
        if training_dataset.dataset_kind != FeatureDataset.KIND_TRAINING:
            blockers.append("training_feature_dataset_wrong_kind")
        if training_dataset.source_kind != FeatureDataset.SOURCE_KIND_LIVE:
            blockers.append("training_feature_dataset_not_live")
        if not training_dataset.row_count:
            blockers.append("training_feature_dataset_empty")
        lineage = training_dataset.lineage_metadata or {}
        if int(lineage.get("training_label_seeded_demo_row_count") or 0) > 0:
            blockers.append("seeded_training_labels_present")
        if any("fallback" in str(key).lower() or "synthetic" in str(key).lower() for key in lineage):
            blockers.append("synthetic_feature_fallback_present")
        if not (lineage.get("source_record_refs") or lineage.get("surveillance_label_dataset_ref")):
            blockers.append("training_truth_lineage_missing")
    if inference_dataset is None:
        blockers.append("inference_feature_dataset_missing")
    elif (
        model_run.inference_dataset_ref != inference_dataset.dataset_ref
        or entry.inference_feature_dataset_ref != inference_dataset.dataset_ref
    ):
        blockers.append("inference_dataset_reference_mismatch")

    label_ref = (entry.training_label_dataset_ref or "").strip()
    if not label_ref:
        blockers.append("training_label_dataset_reference_missing")
    else:
        label_dataset = FeatureDataset.objects.filter(dataset_ref=label_ref).first()
        if label_dataset is None:
            blockers.append("training_label_dataset_not_found")
        else:
            if not dataset_is_currently_eligible(label_dataset):
                blockers.append("training_label_dataset_not_current_eligible")
            if label_dataset.dataset_kind != FeatureDataset.KIND_TRAINING:
                blockers.append("training_label_dataset_wrong_kind")
            if label_dataset.source_kind != FeatureDataset.SOURCE_KIND_LIVE:
                blockers.append("training_label_dataset_not_live")
            if not label_dataset.row_count:
                blockers.append("training_label_dataset_empty")
            lineage = label_dataset.lineage_metadata or {}
            if not (lineage.get("source_record_refs") or lineage.get("coverage")):
                blockers.append("training_label_truth_lineage_missing")
            if any(
                value is True
                for value in (
                    lineage.get("seeded"),
                    lineage.get("synthetic"),
                    lineage.get("proxy_only_as_confirmed_allowed"),
                )
            ):
                blockers.append("unverified_training_truth")

    contract = [str(value) for value in (entry.feature_contract or [])]
    run_contract = _feature_contract(model_run)
    training_contract = [str(value) for value in (getattr(training_dataset, "feature_keys", []) or [])]
    if entry.feature_schema_version != model_run.feature_schema_version:
        blockers.append("feature_schema_version_mismatch")
    if not contract:
        blockers.append("feature_contract_missing")
    if contract != run_contract or (training_dataset is not None and contract != training_contract):
        blockers.append("feature_contract_mismatch")
    if not (entry.metrics or model_run.evaluation_metrics):
        blockers.append("evaluation_metrics_missing")
    metadata = model_run.metadata or {}
    truth_evidence = metadata.get("production_truth_policy") or metadata.get("truth_policy")
    training_lineage = (getattr(training_dataset, "lineage_metadata", {}) or {}) if training_dataset else {}
    if not truth_evidence and not training_lineage.get("production_truth_policy"):
        blockers.append("truth_policy_evidence_missing")
    elif isinstance(truth_evidence, dict) and truth_evidence.get("blocked_reason_codes"):
        blockers.extend(str(code) for code in truth_evidence["blocked_reason_codes"])
    from ..truth_policy import strict_persisted_truth_blockers

    blockers.extend(strict_persisted_truth_blockers(model_run))
    return list(dict.fromkeys(code for code in blockers if code))


def review_model_artifact(
    *,
    entry: ModelRegistryEntry,
    actor: str,
    reason: str,
    approve: bool,
    request_id: str = "",
) -> ModelRegistryEntry:
    actor_user, actor, reason = _required_actor_reason(
        actor,
        reason,
        required_roles=MODEL_REGISTRY_GOVERNANCE_ROLES,
    )
    with transaction.atomic():
        locked = _entry_for_update(entry.id)
        if locked.approval_state != ModelRegistryApprovalState.PENDING_REVIEW:
            raise ModelRegistryGovernanceError("approval_review_not_pending")
        if approve and locked.governance_events.filter(
            event_type=ModelGovernanceEvent.EVENT_APPROVAL_REQUESTED,
            actor_user_id=actor_user.id,
        ).exists():
            raise ModelRegistryGovernanceError("governance_self_approval_forbidden")
        previous = locked.approval_state
        if approve:
            blockers = model_artifact_approval_blockers(locked)
            if blockers:
                raise ModelRegistryGovernanceError(blockers[0], ",".join(blockers))
            locked.approval_state = ModelRegistryApprovalState.APPROVED
            locked.approved_at = timezone.now()
            locked.approved_by = actor
            locked.approval_reason = reason
            event_type = ModelGovernanceEvent.EVENT_APPROVED
        else:
            locked.approval_state = ModelRegistryApprovalState.REJECTED
            locked.approved_at = None
            locked.approved_by = ""
            locked.approval_reason = reason
            event_type = ModelGovernanceEvent.EVENT_REJECTED
        locked.save(update_fields=["approval_state", "approved_at", "approved_by", "approval_reason", "updated_at"])
        _record_event(
            entry=locked,
            event_type=event_type,
            actor_user=actor_user,
            actor=actor,
            reason=reason,
            previous_approval_state=previous,
            previous_lifecycle_state=locked.lifecycle_state,
            previous_promotion_state=locked.promotion_state,
            request_id=request_id,
        )
        return locked


def designate_model_challenger(
    *,
    entry: ModelRegistryEntry,
    actor: str,
    reason: str,
    champion: ModelRegistryEntry | None = None,
    request_id: str = "",
) -> ModelRegistryEntry:
    actor_user, actor, reason = _required_actor_reason(actor, reason)
    with transaction.atomic():
        locked = _entry_for_update(entry.id)
        if locked.lifecycle_state not in {
            ModelRegistryLifecycleState.CANDIDATE,
            ModelRegistryLifecycleState.CHALLENGER,
        }:
            raise ModelRegistryGovernanceError("challenger_designation_invalid_lifecycle")
        if champion is None:
            from .registry import active_model_registry_entry

            champion = active_model_registry_entry(deployment_target=locked.deployment_target)
        if champion is None or champion.id == locked.id:
            raise ModelRegistryGovernanceError("challenger_target_missing")
        champion = ModelRegistryEntry.objects.select_for_update().get(id=champion.id)
        if champion.approval_state != ModelRegistryApprovalState.APPROVED or champion.lifecycle_state != ModelRegistryLifecycleState.ACTIVE:
            raise ModelRegistryGovernanceError("challenger_target_not_active_approved")
        if champion.deployment_target != locked.deployment_target:
            raise ModelRegistryGovernanceError("challenger_target_deployment_mismatch")
        previous = locked.lifecycle_state
        locked.challenger_of = champion
        locked.lifecycle_state = ModelRegistryLifecycleState.CHALLENGER
        locked.save(update_fields=["challenger_of", "lifecycle_state", "updated_at"])
        _record_event(
            entry=locked,
            event_type=ModelGovernanceEvent.EVENT_CHALLENGER_DESIGNATED,
            actor_user=actor_user,
            actor=actor,
            reason=reason,
            previous_approval_state=locked.approval_state,
            previous_lifecycle_state=previous,
            previous_promotion_state=locked.promotion_state,
            request_id=request_id,
        )
        return locked


def activate_registered_model(
    *,
    entry: ModelRegistryEntry,
    actor: str,
    reason: str,
    request_id: str = "",
) -> ModelRegistryEntry:
    actor_user, actor, reason = _required_actor_reason(
        actor,
        reason,
        required_roles=MODEL_REGISTRY_GOVERNANCE_ROLES,
    )
    if entry.deployment_target != OPERATIONAL_DEPLOYMENT_TARGET:
        raise ModelRegistryGovernanceError("deployment_target_not_operational")
    with transaction.atomic():
        _lock_deployment_target(entry.deployment_target)
        locked = _entry_for_update(entry.id)
        if locked.approval_state != ModelRegistryApprovalState.APPROVED:
            raise ModelRegistryGovernanceError("model_not_approved")
        if locked.lifecycle_state not in {
            ModelRegistryLifecycleState.CANDIDATE,
            ModelRegistryLifecycleState.CHALLENGER,
        }:
            raise ModelRegistryGovernanceError("activation_invalid_lifecycle")
        blockers = model_artifact_approval_blockers(locked)
        from ..truth_policy import strict_persisted_truth_blockers

        blockers.extend(strict_persisted_truth_blockers(locked.model_run))
        blockers = list(dict.fromkeys(blockers))
        if blockers:
            raise ModelRegistryGovernanceError(blockers[0], ",".join(blockers))
        if not model_run_has_phase_4_promotion_metadata(locked.model_run):
            raise ModelRegistryGovernanceError("model_run_not_phase_4_promoted")

        active_entries = list(
            ModelRegistryEntry.objects.select_for_update()
            .filter(
                deployment_target=locked.deployment_target,
                lifecycle_state=ModelRegistryLifecycleState.ACTIVE,
            )
        )
        activated_at = timezone.now()
        previous_lifecycle_state = locked.lifecycle_state
        previous_promotion_state = locked.promotion_state
        previous_active = next((item for item in active_entries if item.id != locked.id), None)
        for old_entry in active_entries:
            if old_entry.id == locked.id:
                continue
            old_previous = old_entry.lifecycle_state
            old_previous_promotion = old_entry.promotion_state
            old_entry.lifecycle_state = ModelRegistryLifecycleState.RETIRED
            old_entry.promotion_state = ModelRegistryPromotionState.RETIRED
            old_entry.active_until = activated_at
            old_entry.retired_reason = f"Superseded by registry_entry:{locked.id}"
            old_entry.save(update_fields=["lifecycle_state", "promotion_state", "active_until", "retired_reason", "updated_at"])
            _record_event(
                entry=old_entry,
                event_type=ModelGovernanceEvent.EVENT_RETIRED,
                actor_user=actor_user,
                actor=actor,
                reason=f"Superseded by activation of registry entry {locked.id}. {reason}",
                previous_approval_state=old_entry.approval_state,
                previous_lifecycle_state=old_previous,
                previous_promotion_state=old_previous_promotion,
                request_id=request_id,
            )

        promotion_event = ModelPromotionEvent.objects.create(
            registry_entry=locked,
            model_run=locked.model_run,
            previous_registry_entry=previous_active,
            source="model_artifact_registry",
            promoted_by=actor,
            promoted_by_user=actor_user,
            active_from=activated_at,
            review_due_date=locked.review_due_date,
            evidence_metadata={
                "registry_version": str(locked.registry_version),
                "governance_reason": reason,
                "deployment_target": locked.deployment_target,
            },
        )
        locked.lifecycle_state = ModelRegistryLifecycleState.ACTIVE
        locked.promotion_state = ModelRegistryPromotionState.ACTIVE_PROMOTED
        locked.active_from = activated_at
        locked.active_until = None
        locked.retired_reason = ""
        locked.rollback_target = previous_active
        locked.owner = actor
        locked.review_due_date = locked.review_due_date or default_review_due_date(activated_at)
        locked.metadata = {
            **(locked.metadata or {}),
            "activation_reason": reason,
            "activated_at": activated_at.isoformat(),
            "deployment_target": locked.deployment_target,
        }
        locked.promotion_event = promotion_event
        locked.save()
        _record_event(
            entry=locked,
            event_type=ModelGovernanceEvent.EVENT_ACTIVATED,
            actor_user=actor_user,
            actor=actor,
            reason=reason,
            previous_approval_state=locked.approval_state,
            previous_lifecycle_state=previous_lifecycle_state,
            previous_promotion_state=previous_promotion_state,
            evidence_snapshot=_event_snapshot(locked, artifact_inspection=verify_registry_artifact(locked)),
            request_id=request_id,
        )
        return locked


def retire_registered_model(*, entry: ModelRegistryEntry, actor: str, reason: str, request_id: str = "") -> ModelRegistryEntry:
    actor_user, actor, reason = _required_actor_reason(
        actor,
        reason,
        required_roles=MODEL_REGISTRY_GOVERNANCE_ROLES,
    )
    with transaction.atomic():
        locked = _entry_for_update(entry.id)
        if locked.lifecycle_state != ModelRegistryLifecycleState.ACTIVE:
            raise ModelRegistryGovernanceError("retirement_requires_active_model")
        previous = locked.lifecycle_state
        previous_promotion_state = locked.promotion_state
        retired_at = timezone.now()
        locked.lifecycle_state = ModelRegistryLifecycleState.RETIRED
        locked.promotion_state = ModelRegistryPromotionState.RETIRED
        locked.active_until = retired_at
        locked.retired_reason = reason
        locked.save(update_fields=["lifecycle_state", "promotion_state", "active_until", "retired_reason", "updated_at"])
        _record_event(
            entry=locked,
            event_type=ModelGovernanceEvent.EVENT_RETIRED,
            actor_user=actor_user,
            actor=actor,
            reason=reason,
            previous_approval_state=locked.approval_state,
            previous_lifecycle_state=previous,
            previous_promotion_state=previous_promotion_state,
            request_id=request_id,
        )
        return locked
