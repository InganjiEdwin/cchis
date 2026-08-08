"""Small persisted registry fixtures for tests of downstream workflows.

These helpers represent a model that has already completed governance. Tests
of registration, review, activation, retirement, and rollback use the public
governance services directly; downstream alert and policy tests should not
silently rely on promotion metadata alone.
"""

from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import override_settings
from django.utils import timezone

from accounts.models import User
from risk.ml.model_registry_governance import register_model_artifact, request_model_approval
from risk.ml.registry import active_model_registry_entry
from risk.models import (
    ModelGovernanceEvent,
    ModelPromotionEvent,
    ModelRegistryApprovalState,
    ModelRegistryLifecycleState,
    ModelRegistryPromotionState,
)


def seed_approved_active_registry_entry(test_case, model_run, *, reason: str):
    """Persist a valid active registry state for a downstream workflow test."""

    if not hasattr(test_case, "_registry_fixture_artifact_path"):
        temp_dir = TemporaryDirectory()
        test_case.addCleanup(temp_dir.cleanup)
        settings_override = override_settings(MODEL_ARTIFACT_ROOT=Path(temp_dir.name))
        settings_override.enable()
        test_case.addCleanup(settings_override.disable)

        artifact_path = Path(temp_dir.name) / "workflow-fixture.joblib"
        artifact_path.write_bytes(b"approved downstream workflow fixture artifact")
        test_case._registry_fixture_artifact_path = artifact_path
        test_case._registry_fixture_operator = User.objects.create_user(
            username="workflow-registry-operator",
            password="test-password",
            role=User.ROLE_ADMIN,
        )
        test_case._registry_fixture_requester = User.objects.create_user(
            username="workflow-review-requester",
            password="test-password",
            role=User.ROLE_ANALYST,
        )
        test_case._registry_fixture_board = User.objects.create_user(
            username="workflow-review-board",
            password="test-password",
            role=User.ROLE_ADMIN,
        )

    entry = register_model_artifact(
        model_run=model_run,
        artifact_path=str(test_case._registry_fixture_artifact_path),
        actor=test_case._registry_fixture_operator.username,
        reason="Register an already-governed downstream workflow fixture",
    )
    request_model_approval(
        entry=entry,
        actor=test_case._registry_fixture_requester.username,
        reason="Request review for downstream workflow fixture",
    )

    approved_at = timezone.now()
    entry.approval_state = ModelRegistryApprovalState.APPROVED
    entry.approved_at = approved_at
    entry.approved_by = test_case._registry_fixture_board.username
    entry.approval_reason = "Approved fixture state for downstream workflow coverage"
    entry.save(update_fields=["approval_state", "approved_at", "approved_by", "approval_reason", "updated_at"])
    ModelGovernanceEvent.objects.create(
        registry_entry=entry,
        event_type=ModelGovernanceEvent.EVENT_APPROVED,
        actor=test_case._registry_fixture_board.username,
        actor_user=test_case._registry_fixture_board,
        reason="Approve downstream workflow fixture",
        previous_approval_state=ModelRegistryApprovalState.PENDING_REVIEW,
        resulting_approval_state=ModelRegistryApprovalState.APPROVED,
        previous_lifecycle_state=entry.lifecycle_state,
        resulting_lifecycle_state=entry.lifecycle_state,
        previous_promotion_state=entry.promotion_state,
        resulting_promotion_state=entry.promotion_state,
    )

    active_from = timezone.now()
    promotion_event = ModelPromotionEvent.objects.create(
        registry_entry=entry,
        model_run=model_run,
        previous_registry_entry=active_model_registry_entry(deployment_target=entry.deployment_target),
        source="downstream_workflow_test_fixture",
        promoted_by=test_case._registry_fixture_board.username,
        promoted_by_user=test_case._registry_fixture_board,
        active_from=active_from,
        evidence_metadata={"reason": reason},
    )
    entry.lifecycle_state = ModelRegistryLifecycleState.ACTIVE
    entry.promotion_state = ModelRegistryPromotionState.ACTIVE_PROMOTED
    entry.active_from = active_from
    entry.active_until = None
    entry.promotion_event = promotion_event
    entry.owner = test_case._registry_fixture_board.username
    entry.save()
    ModelGovernanceEvent.objects.create(
        registry_entry=entry,
        event_type=ModelGovernanceEvent.EVENT_ACTIVATED,
        actor=test_case._registry_fixture_board.username,
        actor_user=test_case._registry_fixture_board,
        reason=reason,
        previous_approval_state=entry.approval_state,
        resulting_approval_state=entry.approval_state,
        previous_lifecycle_state=ModelRegistryLifecycleState.CANDIDATE,
        resulting_lifecycle_state=ModelRegistryLifecycleState.ACTIVE,
        previous_promotion_state=ModelRegistryPromotionState.CANDIDATE,
        resulting_promotion_state=ModelRegistryPromotionState.ACTIVE_PROMOTED,
        evidence_snapshot={"promotion_event_id": promotion_event.id},
    )
    model_run.refresh_from_db()
    return entry
