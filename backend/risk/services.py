import logging
from datetime import timedelta

from decouple import config
from django.db import IntegrityError, transaction
from django.db.models import Count, Max, Q
from django.utils import timezone

from .models import (
    Alert,
    AlertWorkflowEvent,
    AlertWorkflowState,
    CHV,
    CHVAssignment,
    CHVCoverageRequest,
    CHVCoverageRequestAlertLink,
    CHVCoverageRequestEvent,
    CHVDeviceRegistration,
    CHVMessage,
    ContactPreference,
    ContactPreferenceAuditEvent,
    FacilityCatchment,
    FacilityForecast,
    FacilityContact,
    FacilityReadinessEscalation,
    FacilityReadinessFreshness,
    FacilityReadinessReview,
    FacilityReadinessReviewEvent,
    FacilityReadinessSnapshot,
    FacilityReadinessUpdateRequest,
    FeatureDatasetRow,
    HealthFacility,
    MessageTemplate,
    PreparednessAction,
    PreparednessActionEvent,
    RiskScore,
    ScenarioSimulationRun,
    SyncQueue,
    SystemControlState,
    SurveillanceLabelWindow,
    SurveillanceCaseClass,
    SurveillanceFreshnessState,
    SurveillanceOutbreakLabel,
    SurveillanceRecord,
    SurveillanceTruthLevel,
    TriageSession,
    UssdSessionLog,
    Ward,
    WardSpatialRelationship,
    WardSpatialRelationshipSource,
)
from .climate_coverage import climate_alert_evidence_from_prediction, climate_coverage_from_prediction
from .message_governance import TemplateRenderResult, render_message_template, template_reference
from .preparedness_action_evidence import completion_evidence_has_substance
from .ml.alignment import is_promoted_model_run, latest_promoted_riskscore_for_ward, promoted_risk_scores
from .ml.decision_policy import (
    DECISION_ALERT_CANDIDATE,
    DECISION_ROUTINE_MONITORING,
    DECISION_URGENT_ALERT,
    DECISION_WATCHLIST_ONLY,
    current_ward_risk_decision_policy,
)
from .population_exposure_features import (
    build_population_exposure_context_for_facility,
    build_population_exposure_context_for_ward,
)
from .privacy_access import mask_contact_value, redact_direct_identifiers_in_text, user_can_view_direct_identifiers
from .providers import DeliveryResult, get_sms_provider
from .surveillance_features import build_surveillance_feature_context_for_ward
from .truth_policy import (
    production_model_run_blockers,
    require_demo_data_allowed,
    require_production_alert_eligibility,
)


alerts_logger = logging.getLogger("risk.alerts")
ml_logger = logging.getLogger("risk.ml")

TRIGGER_TYPE_HIGH_RISK_ESCALATION = "HIGH_RISK_ESCALATION"
TRIGGER_TYPE_FOLLOW_UP_REVIEW = "FOLLOW_UP_REVIEW"
TRIGGER_TYPE_DELIVERY_RETRY = "DELIVERY_RETRY"
TRIGGER_TYPE_CUSTOM = "CUSTOM"

SUPPORTED_TRIGGER_TYPES = [
    TRIGGER_TYPE_HIGH_RISK_ESCALATION,
    TRIGGER_TYPE_FOLLOW_UP_REVIEW,
    TRIGGER_TYPE_DELIVERY_RETRY,
    TRIGGER_TYPE_CUSTOM,
]

MESSAGE_MODE_BACKEND_GENERATED = "backend_generated"
MESSAGE_MODE_OPERATOR_EDITED = "operator_edited"
MESSAGE_MODE_TEMPLATE_RENDERED = "template_rendered"
MESSAGE_AUDIENCE_GOVERNANCE_SCHEMA_VERSION = "message-audience-governance-phase-2-v1"

MESSAGE_PURPOSE_OPERATIONAL = "operational"
MESSAGE_PURPOSE_RISK_ALERT = "risk_alert"
MESSAGE_PURPOSE_FACILITY_UPDATE = "facility_update"
MESSAGE_PURPOSE_HOUSEHOLD_PREVENTION = "household_prevention"

WARD_DETAIL_STATUS_NONE = "NONE"
WARD_DETAIL_STATUS_TRIGGER_ACTIVE = "TRIGGER_ACTIVE"
WARD_DETAIL_STATUS_REVIEW_PENDING = "REVIEW_PENDING"
WARD_DETAIL_STATUS_ACTION_IN_PROGRESS = "ACTION_IN_PROGRESS"
WARD_DETAIL_STATUS_RESOLVED = "RESOLVED"

CHV_COVERAGE_SLA_HOURS = {
    CHVCoverageRequest.PRIORITY_HIGH: 4,
    CHVCoverageRequest.PRIORITY_MEDIUM: 24,
    CHVCoverageRequest.PRIORITY_LOW: 72,
}

PREPAREDNESS_ACTION_SLA_HOURS = {
    PreparednessAction.PRIORITY_URGENT: 4,
    PreparednessAction.PRIORITY_HIGH: 12,
    PreparednessAction.PRIORITY_MEDIUM: 24,
    PreparednessAction.PRIORITY_LOW: 72,
}

PREPAREDNESS_ACTION_STATUS_EVENT_MAP = {
    PreparednessAction.STATUS_ASSIGNED: PreparednessActionEvent.EVENT_ASSIGNED,
    PreparednessAction.STATUS_ACKNOWLEDGED: PreparednessActionEvent.EVENT_ACKNOWLEDGED,
    PreparednessAction.STATUS_IN_PROGRESS: PreparednessActionEvent.EVENT_IN_PROGRESS,
    PreparednessAction.STATUS_COMPLETED: PreparednessActionEvent.EVENT_COMPLETED,
    PreparednessAction.STATUS_BLOCKED: PreparednessActionEvent.EVENT_BLOCKED,
    PreparednessAction.STATUS_CANCELLED: PreparednessActionEvent.EVENT_CANCELLED,
    PreparednessAction.STATUS_ESCALATED: PreparednessActionEvent.EVENT_ESCALATED,
    PreparednessAction.STATUS_EXPIRED: PreparednessActionEvent.EVENT_EXPIRED,
}

PREPAREDNESS_ACTION_ALLOWED_TRANSITIONS = {
    PreparednessAction.STATUS_DRAFT: {
        PreparednessAction.STATUS_QUEUED,
        PreparednessAction.STATUS_CANCELLED,
    },
    PreparednessAction.STATUS_QUEUED: {
        PreparednessAction.STATUS_ASSIGNED,
        PreparednessAction.STATUS_ACKNOWLEDGED,
        PreparednessAction.STATUS_IN_PROGRESS,
        PreparednessAction.STATUS_BLOCKED,
        PreparednessAction.STATUS_CANCELLED,
        PreparednessAction.STATUS_ESCALATED,
        PreparednessAction.STATUS_EXPIRED,
    },
    PreparednessAction.STATUS_ASSIGNED: {
        PreparednessAction.STATUS_ACKNOWLEDGED,
        PreparednessAction.STATUS_IN_PROGRESS,
        PreparednessAction.STATUS_BLOCKED,
        PreparednessAction.STATUS_CANCELLED,
        PreparednessAction.STATUS_ESCALATED,
        PreparednessAction.STATUS_COMPLETED,
        PreparednessAction.STATUS_EXPIRED,
    },
    PreparednessAction.STATUS_ACKNOWLEDGED: {
        PreparednessAction.STATUS_IN_PROGRESS,
        PreparednessAction.STATUS_BLOCKED,
        PreparednessAction.STATUS_CANCELLED,
        PreparednessAction.STATUS_ESCALATED,
        PreparednessAction.STATUS_COMPLETED,
        PreparednessAction.STATUS_EXPIRED,
    },
    PreparednessAction.STATUS_IN_PROGRESS: {
        PreparednessAction.STATUS_BLOCKED,
        PreparednessAction.STATUS_CANCELLED,
        PreparednessAction.STATUS_ESCALATED,
        PreparednessAction.STATUS_COMPLETED,
        PreparednessAction.STATUS_EXPIRED,
    },
    PreparednessAction.STATUS_BLOCKED: {
        PreparednessAction.STATUS_ASSIGNED,
        PreparednessAction.STATUS_ACKNOWLEDGED,
        PreparednessAction.STATUS_IN_PROGRESS,
        PreparednessAction.STATUS_CANCELLED,
        PreparednessAction.STATUS_ESCALATED,
        PreparednessAction.STATUS_EXPIRED,
    },
    PreparednessAction.STATUS_ESCALATED: {
        PreparednessAction.STATUS_IN_PROGRESS,
        PreparednessAction.STATUS_BLOCKED,
        PreparednessAction.STATUS_CANCELLED,
        PreparednessAction.STATUS_COMPLETED,
        PreparednessAction.STATUS_EXPIRED,
    },
    PreparednessAction.STATUS_COMPLETED: set(),
    PreparednessAction.STATUS_CANCELLED: set(),
    PreparednessAction.STATUS_EXPIRED: set(),
}


def _actor_or_none(actor):
    return actor if getattr(actor, "is_authenticated", False) else None


def _preparedness_action_source_ref(
    *,
    action_type: str,
    source_trigger_type: str,
    ward: Ward,
    source_trigger_ref: str = "",
    alert: Alert | None = None,
    alert_workflow: AlertWorkflowState | None = None,
    risk_score: RiskScore | None = None,
    facility_readiness_review: FacilityReadinessReview | None = None,
    facility_update_request: FacilityReadinessUpdateRequest | None = None,
    facility_escalation: FacilityReadinessEscalation | None = None,
    chv_coverage_request: CHVCoverageRequest | None = None,
) -> str:
    if source_trigger_ref.strip():
        return source_trigger_ref.strip()

    source_ref_by_trigger = {
        PreparednessAction.SOURCE_ALERT: f"alert:{alert.public_id}" if alert is not None else "",
        PreparednessAction.SOURCE_ALERT_WORKFLOW: (
            f"alert_workflow:{alert_workflow.public_id}" if alert_workflow is not None else ""
        ),
        PreparednessAction.SOURCE_RISK_SCORE: f"risk_score:{risk_score.id}" if risk_score is not None else "",
        PreparednessAction.SOURCE_FACILITY_READINESS_REVIEW: (
            f"facility_readiness_review:{facility_readiness_review.public_id}"
            if facility_readiness_review is not None
            else ""
        ),
        PreparednessAction.SOURCE_FACILITY_UPDATE_REQUEST: (
            f"facility_update_request:{facility_update_request.public_id}"
            if facility_update_request is not None
            else ""
        ),
        PreparednessAction.SOURCE_FACILITY_ESCALATION: (
            f"facility_escalation:{facility_escalation.public_id}" if facility_escalation is not None else ""
        ),
        PreparednessAction.SOURCE_CHV_COVERAGE_REQUEST: (
            f"chv_coverage_request:{chv_coverage_request.public_id}" if chv_coverage_request is not None else ""
        ),
    }
    if source_ref_by_trigger.get(source_trigger_type):
        return source_ref_by_trigger[source_trigger_type]

    if alert is not None:
        return f"alert:{alert.public_id}"
    if alert_workflow is not None:
        return f"alert_workflow:{alert_workflow.public_id}"
    if risk_score is not None:
        return f"risk_score:{risk_score.id}"
    if facility_readiness_review is not None:
        return f"facility_readiness_review:{facility_readiness_review.public_id}"
    if facility_update_request is not None:
        return f"facility_update_request:{facility_update_request.public_id}"
    if facility_escalation is not None:
        return f"facility_escalation:{facility_escalation.public_id}"
    if chv_coverage_request is not None:
        return f"chv_coverage_request:{chv_coverage_request.public_id}"
    if source_trigger_type == PreparednessAction.SOURCE_MANUAL:
        return ""
    return f"{source_trigger_type}:ward:{ward.id}:action:{action_type}"


def _validate_preparedness_action_lineage(
    *,
    ward: Ward,
    facility: HealthFacility | None = None,
    chv: CHV | None = None,
    alert: Alert | None = None,
    alert_workflow: AlertWorkflowState | None = None,
    risk_score: RiskScore | None = None,
    facility_readiness_review: FacilityReadinessReview | None = None,
    facility_update_request: FacilityReadinessUpdateRequest | None = None,
    facility_escalation: FacilityReadinessEscalation | None = None,
    chv_coverage_request: CHVCoverageRequest | None = None,
) -> None:
    ward_checks = [
        ("facility", facility.ward_id if facility else None),
        ("chv", chv.ward_id if chv else None),
        ("alert", alert.ward_id if alert else None),
        ("alert_workflow", alert_workflow.ward_id if alert_workflow else None),
        ("risk_score", risk_score.ward_id if risk_score else None),
        ("facility_readiness_review", facility_readiness_review.ward_id if facility_readiness_review else None),
        ("facility_update_request", facility_update_request.facility.ward_id if facility_update_request else None),
        ("facility_escalation", facility_escalation.ward_id if facility_escalation else None),
        ("chv_coverage_request", chv_coverage_request.ward_id if chv_coverage_request else None),
    ]
    mismatched = [name for name, ward_id in ward_checks if ward_id is not None and ward_id != ward.id]
    if mismatched:
        raise ValueError(f"Preparedness action source lineage crosses ward boundaries: {', '.join(mismatched)}.")


def _validate_preparedness_action_provenance(
    *,
    alert: Alert | None = None,
    alert_workflow: AlertWorkflowState | None = None,
    risk_score: RiskScore | None = None,
    model_run=None,
    decision_policy_version: str = "",
) -> None:
    if alert is not None and risk_score is not None and alert.risk_score_id and alert.risk_score_id != risk_score.id:
        raise ValueError("Preparedness action alert and risk score lineage do not match.")
    if (
        alert_workflow is not None
        and alert is not None
        and alert_workflow.alert_id
        and alert_workflow.alert_id != alert.id
    ):
        raise ValueError("Preparedness action alert workflow and alert lineage do not match.")
    if (
        alert_workflow is not None
        and risk_score is not None
        and alert_workflow.latest_risk_score_id
        and alert_workflow.latest_risk_score_id != risk_score.id
    ):
        raise ValueError("Preparedness action alert workflow and risk score lineage do not match.")
    if (
        risk_score is not None
        and model_run is not None
        and risk_score.model_run_id
        and risk_score.model_run_id != model_run.id
    ):
        raise ValueError("Preparedness action risk score and model run lineage do not match.")
    expected_policy_version = (risk_score.decision_policy or {}).get("policy_version", "") if risk_score else ""
    if expected_policy_version and decision_policy_version and decision_policy_version != expected_policy_version:
        raise ValueError("Preparedness action decision policy lineage does not match the risk score.")


def _validate_preparedness_action_source_requirements(
    *,
    source_trigger_type: str,
    alert: Alert | None = None,
    alert_workflow: AlertWorkflowState | None = None,
    risk_score: RiskScore | None = None,
    facility_readiness_review: FacilityReadinessReview | None = None,
    facility_update_request: FacilityReadinessUpdateRequest | None = None,
    facility_escalation: FacilityReadinessEscalation | None = None,
    chv_coverage_request: CHVCoverageRequest | None = None,
    source_trigger_ref: str = "",
    lineage_metadata: dict | None = None,
) -> None:
    required_sources = {
        PreparednessAction.SOURCE_ALERT: ("alert", alert),
        PreparednessAction.SOURCE_ALERT_WORKFLOW: ("alert workflow", alert_workflow),
        PreparednessAction.SOURCE_RISK_SCORE: ("risk score", risk_score),
        PreparednessAction.SOURCE_CHV_COVERAGE_REQUEST: ("CHV coverage request", chv_coverage_request),
        PreparednessAction.SOURCE_FACILITY_READINESS_REVIEW: (
            "facility readiness review",
            facility_readiness_review,
        ),
        PreparednessAction.SOURCE_FACILITY_UPDATE_REQUEST: (
            "facility update request",
            facility_update_request,
        ),
        PreparednessAction.SOURCE_FACILITY_ESCALATION: ("facility escalation", facility_escalation),
    }
    required_source = required_sources.get(source_trigger_type)
    if required_source is not None and required_source[1] is None:
        raise ValueError(f"{source_trigger_type} preparedness actions require a linked {required_source[0]}.")
    if source_trigger_type in {PreparednessAction.SOURCE_SYSTEM, PreparednessAction.SOURCE_OUTCOME_FEEDBACK}:
        if not source_trigger_ref.strip() and not (lineage_metadata or {}):
            raise ValueError(
                f"{source_trigger_type} preparedness actions require a source reference or lineage metadata."
            )


def _validate_preparedness_action_assignee(*, ward: Ward, assigned_to) -> None:
    if assigned_to is None:
        return
    if not getattr(assigned_to, "is_active", False):
        raise ValueError("Assigned preparedness action owner must be active.")
    if getattr(assigned_to, "role", None) == "ADMIN" or getattr(assigned_to, "is_superuser", False):
        return
    if getattr(assigned_to, "ward_id", None) == ward.id:
        return
    raise ValueError("Assigned preparedness action owner must belong to the action ward or be an admin.")


def _preparedness_action_has_owner(*, assigned_to, assigned_to_team: str) -> bool:
    return assigned_to is not None or bool(assigned_to_team.strip())


def _preparedness_action_requires_due(status: str) -> bool:
    return status in PreparednessAction.ACTIVE_STATUSES and status != PreparednessAction.STATUS_DRAFT


def record_preparedness_action_event(
    preparedness_action: PreparednessAction,
    *,
    event_type: str,
    actor=None,
    old_status: str = "",
    new_status: str = "",
    detail: str = "",
    metadata: dict | None = None,
) -> PreparednessActionEvent:
    return PreparednessActionEvent.objects.create(
        preparedness_action=preparedness_action,
        actor=_actor_or_none(actor),
        event_type=event_type,
        old_status=old_status,
        new_status=new_status,
        detail=detail,
        metadata=metadata or {},
    )


@transaction.atomic
def get_or_create_preparedness_action(
    *,
    ward: Ward,
    action_type: str,
    source_trigger_type: str = PreparednessAction.SOURCE_MANUAL,
    actor=None,
    facility: HealthFacility | None = None,
    chv: CHV | None = None,
    alert: Alert | None = None,
    alert_workflow: AlertWorkflowState | None = None,
    risk_score: RiskScore | None = None,
    model_run=None,
    facility_readiness_review: FacilityReadinessReview | None = None,
    facility_update_request: FacilityReadinessUpdateRequest | None = None,
    facility_escalation: FacilityReadinessEscalation | None = None,
    chv_coverage_request: CHVCoverageRequest | None = None,
    priority: str = PreparednessAction.PRIORITY_MEDIUM,
    status: str = PreparednessAction.STATUS_QUEUED,
    assigned_to=None,
    assigned_to_team: str = "",
    decision_policy_version: str = "",
    due_at=None,
    sla_target_at=None,
    source_trigger_ref: str = "",
    notes: str = "",
    lineage_metadata: dict | None = None,
) -> tuple[PreparednessAction, bool]:
    valid_action_types = {choice[0] for choice in PreparednessAction.ACTION_TYPE_CHOICES}
    valid_sources = {choice[0] for choice in PreparednessAction.SOURCE_TRIGGER_CHOICES}
    valid_priorities = {choice[0] for choice in PreparednessAction.PRIORITY_CHOICES}
    allowed_initial_statuses = {
        PreparednessAction.STATUS_DRAFT,
        PreparednessAction.STATUS_QUEUED,
        PreparednessAction.STATUS_ASSIGNED,
    }
    if action_type not in valid_action_types:
        raise ValueError("Unsupported preparedness action type.")
    if source_trigger_type not in valid_sources:
        raise ValueError("Unsupported preparedness action source trigger type.")
    if priority not in valid_priorities:
        raise ValueError("Unsupported preparedness action priority.")
    if status not in allowed_initial_statuses:
        raise ValueError("Preparedness actions can only be created as draft, queued, or assigned.")
    assigned_to_team = assigned_to_team.strip()
    has_initial_owner = _preparedness_action_has_owner(
        assigned_to=assigned_to,
        assigned_to_team=assigned_to_team,
    )
    if status == PreparednessAction.STATUS_DRAFT and has_initial_owner:
        raise ValueError("Draft preparedness actions cannot be assigned.")
    if status == PreparednessAction.STATUS_QUEUED and has_initial_owner:
        status = PreparednessAction.STATUS_ASSIGNED
    if status == PreparednessAction.STATUS_ASSIGNED and not has_initial_owner:
        raise ValueError("Assigned preparedness actions require an owner or team.")
    resolved_due_at = due_at
    if _preparedness_action_requires_due(status) and resolved_due_at is None:
        resolved_due_at = _preparedness_due_at(priority)
    resolved_sla_target_at = sla_target_at or resolved_due_at

    risk_score = risk_score or (alert.risk_score if alert and alert.risk_score_id else None)
    model_run = model_run or (risk_score.model_run if risk_score and risk_score.model_run_id else None)
    if not decision_policy_version and risk_score:
        decision_policy_version = (risk_score.decision_policy or {}).get("policy_version", "")

    _validate_preparedness_action_source_requirements(
        source_trigger_type=source_trigger_type,
        alert=alert,
        alert_workflow=alert_workflow,
        risk_score=risk_score,
        facility_readiness_review=facility_readiness_review,
        facility_update_request=facility_update_request,
        facility_escalation=facility_escalation,
        chv_coverage_request=chv_coverage_request,
        source_trigger_ref=source_trigger_ref,
        lineage_metadata=lineage_metadata,
    )
    _validate_preparedness_action_provenance(
        alert=alert,
        alert_workflow=alert_workflow,
        risk_score=risk_score,
        model_run=model_run,
        decision_policy_version=decision_policy_version,
    )
    _validate_preparedness_action_lineage(
        ward=ward,
        facility=facility,
        chv=chv,
        alert=alert,
        alert_workflow=alert_workflow,
        risk_score=risk_score,
        facility_readiness_review=facility_readiness_review,
        facility_update_request=facility_update_request,
        facility_escalation=facility_escalation,
        chv_coverage_request=chv_coverage_request,
    )
    _validate_preparedness_action_assignee(ward=ward, assigned_to=assigned_to)
    resolved_source_ref = _preparedness_action_source_ref(
        action_type=action_type,
        source_trigger_type=source_trigger_type,
        ward=ward,
        source_trigger_ref=source_trigger_ref,
        alert=alert,
        alert_workflow=alert_workflow,
        risk_score=risk_score,
        facility_readiness_review=facility_readiness_review,
        facility_update_request=facility_update_request,
        facility_escalation=facility_escalation,
        chv_coverage_request=chv_coverage_request,
    )
    if resolved_source_ref:
        existing_action = (
            PreparednessAction.objects.select_for_update()
            .filter(
                action_type=action_type,
                source_trigger_type=source_trigger_type,
                source_trigger_ref=resolved_source_ref,
                status__in=PreparednessAction.ACTIVE_STATUSES,
            )
            .order_by("-created_at")
            .first()
        )
        if existing_action is not None:
            record_preparedness_action_event(
                existing_action,
                event_type=PreparednessActionEvent.EVENT_COMMENT,
                actor=actor,
                old_status=existing_action.status,
                new_status=existing_action.status,
                detail="Repeated source trigger reused existing active preparedness action.",
                metadata={
                    "idempotency": "existing_active_action_reused",
                    "source_trigger_ref": resolved_source_ref,
                },
            )
            return existing_action, False

    try:
        with transaction.atomic():
            action = PreparednessAction.objects.create(
                action_type=action_type,
                source_trigger_type=source_trigger_type,
                source_trigger_ref=resolved_source_ref,
                ward=ward,
                facility=facility,
                chv=chv,
                alert=alert,
                alert_workflow=alert_workflow,
                risk_score=risk_score,
                model_run=model_run,
                facility_readiness_review=facility_readiness_review,
                facility_update_request=facility_update_request,
                facility_escalation=facility_escalation,
                chv_coverage_request=chv_coverage_request,
                status=status,
                priority=priority,
                created_by=_actor_or_none(actor),
                assigned_to=assigned_to,
                assigned_to_team=assigned_to_team,
                decision_policy_version=decision_policy_version,
                due_at=resolved_due_at,
                sla_target_at=resolved_sla_target_at,
                acknowledged_at=None,
                lineage_metadata=lineage_metadata or {},
                notes=notes.strip(),
            )
    except IntegrityError:
        if not resolved_source_ref:
            raise
        existing_action = (
            PreparednessAction.objects.select_for_update()
            .filter(
                action_type=action_type,
                source_trigger_type=source_trigger_type,
                source_trigger_ref=resolved_source_ref,
                status__in=PreparednessAction.ACTIVE_STATUSES,
            )
            .order_by("-created_at")
            .first()
        )
        if existing_action is None:
            raise
        record_preparedness_action_event(
            existing_action,
            event_type=PreparednessActionEvent.EVENT_COMMENT,
            actor=actor,
            old_status=existing_action.status,
            new_status=existing_action.status,
            detail="Repeated source trigger reused existing active preparedness action after a concurrent create.",
            metadata={
                "idempotency": "existing_active_action_reused_after_integrity_error",
                "source_trigger_ref": resolved_source_ref,
            },
        )
        return existing_action, False
    record_preparedness_action_event(
        action,
        event_type=PreparednessActionEvent.EVENT_CREATED,
        actor=actor,
        new_status=action.status,
        detail="Preparedness action created.",
        metadata={
            "action_type": action.action_type,
            "source_trigger_type": action.source_trigger_type,
            "source_trigger_ref": action.source_trigger_ref,
            "idempotency": "new_action_created",
        },
    )
    if action.status == PreparednessAction.STATUS_ASSIGNED:
        record_preparedness_action_event(
            action,
            event_type=PreparednessActionEvent.EVENT_ASSIGNED,
            actor=actor,
            old_status=action.status,
            new_status=action.status,
            detail="Preparedness action assigned at creation.",
            metadata={
                "assigned_to": action.assigned_to_id,
                "assigned_to_team": action.assigned_to_team,
            },
        )
    return action, True


@transaction.atomic
def transition_preparedness_action(
    preparedness_action: PreparednessAction,
    *,
    actor=None,
    status: str,
    detail: str = "",
    assigned_to=None,
    assigned_to_provided: bool = False,
    assigned_to_team: str | None = None,
    due_at=None,
    due_at_provided: bool = False,
    sla_target_at=None,
    sla_target_at_provided: bool = False,
    completion_evidence: dict | None = None,
    cancellation_reason: str = "",
    escalation_metadata: dict | None = None,
) -> PreparednessAction:
    old_status = preparedness_action.status
    assigned_to_provided = assigned_to_provided or assigned_to is not None
    due_at_provided = due_at_provided or due_at is not None
    sla_target_at_provided = sla_target_at_provided or sla_target_at is not None
    valid_statuses = {choice[0] for choice in PreparednessAction.STATUS_CHOICES}
    if status not in valid_statuses:
        raise ValueError("Unsupported preparedness action status.")

    if status != old_status and status not in PREPAREDNESS_ACTION_ALLOWED_TRANSITIONS.get(old_status, set()):
        raise ValueError(f"Preparedness action cannot transition from {old_status} to {status}.")

    old_assigned_to_id = preparedness_action.assigned_to_id
    old_assigned_to_team = preparedness_action.assigned_to_team
    old_due_at = preparedness_action.due_at
    old_sla_target_at = preparedness_action.sla_target_at
    resolved_assigned_to = assigned_to if assigned_to_provided else preparedness_action.assigned_to
    resolved_assigned_to_team = (
        assigned_to_team.strip() if assigned_to_team is not None else preparedness_action.assigned_to_team
    )
    resolved_due_at = due_at if due_at_provided else preparedness_action.due_at
    resolved_sla_target_at = sla_target_at if sla_target_at_provided else preparedness_action.sla_target_at
    if due_at_provided and not sla_target_at_provided:
        resolved_sla_target_at = resolved_due_at
    assignment_changed = (
        (assigned_to_provided and getattr(resolved_assigned_to, "id", None) != old_assigned_to_id)
        or (assigned_to_team is not None and resolved_assigned_to_team != old_assigned_to_team)
    )
    due_date_changed = due_at_provided and resolved_due_at != old_due_at
    sla_target_changed = sla_target_at_provided and resolved_sla_target_at != old_sla_target_at
    if (
        old_status in PreparednessAction.CLOSED_STATUSES
        and (assignment_changed or due_date_changed or sla_target_changed)
    ):
        raise ValueError("Closed preparedness actions cannot change assignment, due date, or SLA target.")
    if status in {PreparednessAction.STATUS_DRAFT, PreparednessAction.STATUS_QUEUED} and assignment_changed:
        raise ValueError("Assignments require ASSIGNED or later active status.")
    if status == PreparednessAction.STATUS_ASSIGNED and not (resolved_assigned_to or resolved_assigned_to_team):
        raise ValueError("Assigned preparedness actions require an owner or team.")
    if _preparedness_action_requires_due(status) and resolved_due_at is None:
        raise ValueError("Active preparedness actions require a due time.")
    if _preparedness_action_requires_due(status) and resolved_sla_target_at is None:
        resolved_sla_target_at = resolved_due_at
    if (
        status == old_status
        and not due_date_changed
        and not sla_target_changed
        and completion_evidence is None
        and not assignment_changed
    ):
        raise ValueError(
            "Preparedness action transition did not change status, assignment, due date, SLA target, or evidence."
        )

    resolved_completion_evidence = completion_evidence if completion_evidence is not None else preparedness_action.completion_evidence
    if status == PreparednessAction.STATUS_COMPLETED and not completion_evidence_has_substance(
        resolved_completion_evidence
    ):
        raise ValueError("Completion evidence must include at least one substantive detail.")
    resolved_cancellation_reason = cancellation_reason.strip() or detail.strip() or preparedness_action.cancellation_reason
    if status == PreparednessAction.STATUS_CANCELLED and not resolved_cancellation_reason:
        raise ValueError("A cancellation reason is required before cancelling a preparedness action.")

    now = timezone.now()
    preparedness_action.status = status
    if assigned_to_provided:
        preparedness_action.assigned_to = assigned_to
    if assigned_to_team is not None:
        preparedness_action.assigned_to_team = resolved_assigned_to_team
    if due_at_provided:
        preparedness_action.due_at = resolved_due_at
    if sla_target_at_provided or (due_at_provided and not sla_target_at_provided):
        preparedness_action.sla_target_at = resolved_sla_target_at
    elif preparedness_action.sla_target_at is None and resolved_sla_target_at is not None:
        preparedness_action.sla_target_at = resolved_sla_target_at
    if completion_evidence is not None:
        preparedness_action.completion_evidence = completion_evidence
    if escalation_metadata is not None:
        preparedness_action.escalation_metadata = escalation_metadata
    if cancellation_reason.strip():
        preparedness_action.cancellation_reason = cancellation_reason.strip()
    if detail.strip():
        preparedness_action.notes = detail.strip()
    if assigned_to_provided:
        _validate_preparedness_action_assignee(ward=preparedness_action.ward, assigned_to=assigned_to)

    if status == PreparednessAction.STATUS_ACKNOWLEDGED and preparedness_action.acknowledged_at is None:
        preparedness_action.acknowledged_at = now
    if status == PreparednessAction.STATUS_IN_PROGRESS and preparedness_action.acknowledged_at is None:
        preparedness_action.acknowledged_at = now
    if status == PreparednessAction.STATUS_COMPLETED:
        preparedness_action.completed_at = now
    if status == PreparednessAction.STATUS_CANCELLED:
        preparedness_action.cancelled_at = now
        preparedness_action.cancellation_reason = resolved_cancellation_reason
    if status == PreparednessAction.STATUS_ESCALATED:
        preparedness_action.escalated_at = now

    preparedness_action.save(
        update_fields=[
            "status",
            "assigned_to",
            "assigned_to_team",
            "due_at",
            "sla_target_at",
            "acknowledged_at",
            "completed_at",
            "cancelled_at",
            "escalated_at",
            "completion_evidence",
            "cancellation_reason",
            "escalation_metadata",
            "notes",
            "updated_at",
        ]
    )
    event_type = PREPAREDNESS_ACTION_STATUS_EVENT_MAP.get(status, PreparednessActionEvent.EVENT_STATUS_CHANGED)
    if status == old_status and assignment_changed:
        event_type = PreparednessActionEvent.EVENT_ASSIGNED
    elif status == old_status and due_date_changed:
        event_type = PreparednessActionEvent.EVENT_DUE_DATE_CHANGED
    elif status == old_status and completion_evidence is not None:
        event_type = PreparednessActionEvent.EVENT_COMPLETION_EVIDENCE_ADDED
    default_detail = (
        "Preparedness action assignment updated."
        if status == old_status and assignment_changed
        else f"Preparedness action moved to {preparedness_action.status}."
    )
    status_event = record_preparedness_action_event(
        preparedness_action,
        event_type=event_type,
        actor=actor,
        old_status=old_status,
        new_status=preparedness_action.status,
        detail=detail.strip() or default_detail,
        metadata={
            "old_assigned_to": old_assigned_to_id,
            "old_assigned_to_team": old_assigned_to_team,
            "assigned_to": preparedness_action.assigned_to_id,
            "assigned_to_team": preparedness_action.assigned_to_team,
            "assignment_changed": assignment_changed,
            "old_due_at": old_due_at.isoformat() if old_due_at else None,
            "old_sla_target_at": old_sla_target_at.isoformat() if old_sla_target_at else None,
            "due_at": preparedness_action.due_at.isoformat() if preparedness_action.due_at else None,
            "sla_target_at": preparedness_action.sla_target_at.isoformat() if preparedness_action.sla_target_at else None,
            "due_at_changed": due_date_changed,
            "sla_target_at_changed": sla_target_changed,
            "completion_evidence_present": bool(preparedness_action.completion_evidence),
        },
    )
    if assignment_changed and event_type != PreparednessActionEvent.EVENT_ASSIGNED:
        record_preparedness_action_event(
            preparedness_action,
            event_type=PreparednessActionEvent.EVENT_ASSIGNED,
            actor=actor,
            old_status=old_status,
            new_status=preparedness_action.status,
            detail="Preparedness action assignment updated during status transition.",
            metadata={
                "old_assigned_to": old_assigned_to_id,
                "old_assigned_to_team": old_assigned_to_team,
                "assigned_to": preparedness_action.assigned_to_id,
                "assigned_to_team": preparedness_action.assigned_to_team,
                "assignment_changed": True,
                "paired_status_event": str(status_event.public_id),
            },
        )
    return preparedness_action


def _preparedness_priority_for_risk_level(risk_level: str | None) -> str:
    if risk_level == Ward.RISK_HIGH:
        return PreparednessAction.PRIORITY_HIGH
    if risk_level == Ward.RISK_MEDIUM:
        return PreparednessAction.PRIORITY_MEDIUM
    if risk_level == Ward.RISK_LOW:
        return PreparednessAction.PRIORITY_LOW
    return PreparednessAction.PRIORITY_MEDIUM


def _preparedness_priority_for_alert(alert: Alert, action_type: str) -> str:
    if action_type == PreparednessAction.ACTION_COUNTY_ESCALATION or alert.status == Alert.STATUS_FAILED:
        return PreparednessAction.PRIORITY_URGENT
    if alert.risk_score_id:
        return _preparedness_priority_for_risk_level(alert.risk_score.risk_level)
    return _preparedness_priority_for_risk_level(alert.ward.current_risk_level)


def _preparedness_priority_for_facility_review(review: FacilityReadinessReview) -> str:
    if review.severity == FacilityReadinessReview.SEVERITY_HIGH:
        return PreparednessAction.PRIORITY_HIGH
    if review.severity == FacilityReadinessReview.SEVERITY_MEDIUM:
        return PreparednessAction.PRIORITY_MEDIUM
    return PreparednessAction.PRIORITY_LOW


def _preparedness_priority_for_facility_escalation(escalation: FacilityReadinessEscalation) -> str:
    if escalation.severity == FacilityReadinessEscalation.SEVERITY_HIGH:
        return PreparednessAction.PRIORITY_URGENT
    if escalation.severity == FacilityReadinessEscalation.SEVERITY_MEDIUM:
        return PreparednessAction.PRIORITY_HIGH
    return PreparednessAction.PRIORITY_MEDIUM


def _preparedness_due_at(priority: str, due_at=None):
    if due_at is not None:
        return due_at
    hours = PREPAREDNESS_ACTION_SLA_HOURS.get(priority, PREPAREDNESS_ACTION_SLA_HOURS[PreparednessAction.PRIORITY_MEDIUM])
    return timezone.now() + timedelta(hours=hours)


def _preparedness_lineage_metadata(*, source_kind: str, extra: dict | None = None, user_metadata: dict | None = None) -> dict:
    return {
        "integration_phase": "child_plan_1_phase_2",
        "source_kind": source_kind,
        **(extra or {}),
        **(user_metadata or {}),
    }


def _first_linked_alert_for_chv_coverage_request(coverage_request: CHVCoverageRequest) -> Alert | None:
    link = (
        coverage_request.linked_alert_links.select_related("alert", "alert__risk_score")
        .order_by("created_at", "id")
        .first()
    )
    return link.alert if link is not None else None


def _active_assignment_chv_for_coverage_request(coverage_request: CHVCoverageRequest) -> CHV | None:
    assignment = (
        coverage_request.assignments.select_related("chv")
        .filter(status=CHVAssignment.STATUS_ACTIVE)
        .order_by("-created_at")
        .first()
    )
    return assignment.chv if assignment is not None else None


def create_preparedness_action_from_alert(
    alert: Alert,
    *,
    actor=None,
    action_type: str,
    priority: str | None = None,
    status: str = PreparednessAction.STATUS_QUEUED,
    assigned_to=None,
    assigned_to_team: str = "",
    due_at=None,
    sla_target_at=None,
    notes: str = "",
    lineage_metadata: dict | None = None,
) -> tuple[PreparednessAction, bool]:
    allowed_action_types = {
        PreparednessAction.ACTION_FIELD_VERIFICATION,
        PreparednessAction.ACTION_CHV_FOLLOW_UP,
        PreparednessAction.ACTION_HOUSEHOLD_PREVENTION_MESSAGE,
        PreparednessAction.ACTION_COUNTY_ESCALATION,
        PreparednessAction.ACTION_SURVEILLANCE_FOLLOW_UP,
    }
    if action_type not in allowed_action_types:
        raise ValueError("This alert source cannot create the requested preparedness action type.")

    resolved_priority = priority or _preparedness_priority_for_alert(alert, action_type)
    resolved_due_at = _preparedness_due_at(resolved_priority, due_at)
    return get_or_create_preparedness_action(
        ward=alert.ward,
        action_type=action_type,
        source_trigger_type=PreparednessAction.SOURCE_ALERT,
        actor=actor,
        alert=alert,
        risk_score=alert.risk_score,
        priority=resolved_priority,
        status=status,
        assigned_to=assigned_to,
        assigned_to_team=assigned_to_team,
        due_at=resolved_due_at,
        sla_target_at=sla_target_at or resolved_due_at,
        notes=notes
        or "Preparedness action created explicitly from alert review; alert delivery remains a separate state.",
        lineage_metadata=_preparedness_lineage_metadata(
            source_kind="alert",
            extra={
                "alert_public_id": str(alert.public_id),
                "alert_status": alert.status,
                "alert_channel": alert.channel,
                "risk_score_id": alert.risk_score_id,
            },
            user_metadata=lineage_metadata,
        ),
    )


def create_preparedness_action_from_alert_workflow(
    workflow: AlertWorkflowState,
    *,
    actor=None,
    action_type: str,
    priority: str | None = None,
    status: str = PreparednessAction.STATUS_QUEUED,
    assigned_to=None,
    assigned_to_team: str = "",
    due_at=None,
    sla_target_at=None,
    notes: str = "",
    lineage_metadata: dict | None = None,
) -> tuple[PreparednessAction, bool]:
    allowed_action_types = {
        PreparednessAction.ACTION_FIELD_VERIFICATION,
        PreparednessAction.ACTION_HOUSEHOLD_PREVENTION_MESSAGE,
        PreparednessAction.ACTION_COUNTY_ESCALATION,
        PreparednessAction.ACTION_SURVEILLANCE_FOLLOW_UP,
    }
    if action_type not in allowed_action_types:
        raise ValueError("This alert workflow source cannot create the requested preparedness action type.")
    if workflow.status == AlertWorkflowState.STATUS_RESOLVED and workflow.active_alert_count == 0:
        raise ValueError("Resolved alert workflows without active alert context cannot create preparedness actions.")

    risk_score = workflow.latest_risk_score
    alert = workflow.alert
    resolved_priority = priority or _preparedness_priority_for_risk_level(workflow.risk_level)
    if action_type == PreparednessAction.ACTION_COUNTY_ESCALATION:
        resolved_priority = priority or PreparednessAction.PRIORITY_URGENT
    resolved_due_at = _preparedness_due_at(resolved_priority, due_at)
    return get_or_create_preparedness_action(
        ward=workflow.ward,
        action_type=action_type,
        source_trigger_type=PreparednessAction.SOURCE_ALERT_WORKFLOW,
        actor=actor,
        alert=alert,
        alert_workflow=workflow,
        risk_score=risk_score,
        priority=resolved_priority,
        status=status,
        assigned_to=assigned_to,
        assigned_to_team=assigned_to_team,
        due_at=resolved_due_at,
        sla_target_at=sla_target_at or resolved_due_at,
        notes=notes
        or "Preparedness action created explicitly from alert workflow review; alert delivery remains a separate state.",
        lineage_metadata=_preparedness_lineage_metadata(
            source_kind="alert_workflow",
            extra={
                "alert_workflow_public_id": str(workflow.public_id),
                "workflow_status": workflow.status,
                "workflow_trigger_severity": workflow.trigger_severity,
                "alert_public_id": str(alert.public_id) if alert else None,
                "risk_score_id": risk_score.id if risk_score else None,
                "decision_policy": (risk_score.decision_policy if risk_score else {}) or {},
            },
            user_metadata=lineage_metadata,
        ),
    )


def create_preparedness_action_from_chv_coverage_request(
    coverage_request: CHVCoverageRequest,
    *,
    actor=None,
    action_type: str = PreparednessAction.ACTION_CHV_FOLLOW_UP,
    priority: str | None = None,
    status: str = PreparednessAction.STATUS_QUEUED,
    assigned_to=None,
    assigned_to_team: str = "",
    due_at=None,
    sla_target_at=None,
    notes: str = "",
    lineage_metadata: dict | None = None,
) -> tuple[PreparednessAction, bool]:
    if action_type != PreparednessAction.ACTION_CHV_FOLLOW_UP:
        raise ValueError("CHV coverage requests can only create CHV follow-up preparedness actions.")
    if coverage_request.status in {CHVCoverageRequest.STATUS_REJECTED, CHVCoverageRequest.STATUS_CANCELLED}:
        raise ValueError("Rejected or cancelled CHV coverage requests cannot create preparedness actions.")

    alert = _first_linked_alert_for_chv_coverage_request(coverage_request)
    risk_score = alert.risk_score if alert is not None else None
    chv = _active_assignment_chv_for_coverage_request(coverage_request)
    priority_map = {
        CHVCoverageRequest.PRIORITY_HIGH: PreparednessAction.PRIORITY_HIGH,
        CHVCoverageRequest.PRIORITY_MEDIUM: PreparednessAction.PRIORITY_MEDIUM,
        CHVCoverageRequest.PRIORITY_LOW: PreparednessAction.PRIORITY_LOW,
    }
    resolved_priority = priority or priority_map.get(coverage_request.priority, PreparednessAction.PRIORITY_MEDIUM)
    resolved_due_at = _preparedness_due_at(resolved_priority, due_at)
    return get_or_create_preparedness_action(
        ward=coverage_request.ward,
        action_type=action_type,
        source_trigger_type=PreparednessAction.SOURCE_CHV_COVERAGE_REQUEST,
        actor=actor,
        chv=chv,
        alert=alert,
        risk_score=risk_score,
        chv_coverage_request=coverage_request,
        priority=resolved_priority,
        status=status,
        assigned_to=assigned_to or coverage_request.assigned_to_user,
        assigned_to_team=assigned_to_team or coverage_request.assigned_to_team,
        due_at=resolved_due_at,
        sla_target_at=sla_target_at or resolved_due_at,
        notes=notes
        or "Preparedness action created explicitly from CHV coverage follow-up; coverage request state remains separate.",
        lineage_metadata=_preparedness_lineage_metadata(
            source_kind="chv_coverage_request",
            extra={
                "chv_coverage_request_public_id": str(coverage_request.public_id),
                "coverage_request_status": coverage_request.status,
                "coverage_request_trigger_source": coverage_request.trigger_source,
                "linked_alert_public_id": str(alert.public_id) if alert else None,
                "risk_score_id": risk_score.id if risk_score else None,
                "chv_public_id": str(chv.public_id) if chv else None,
            },
            user_metadata=lineage_metadata,
        ),
    )


def create_preparedness_action_from_facility_readiness_review(
    review: FacilityReadinessReview,
    *,
    actor=None,
    action_type: str,
    priority: str | None = None,
    status: str = PreparednessAction.STATUS_QUEUED,
    assigned_to=None,
    assigned_to_team: str = "",
    due_at=None,
    sla_target_at=None,
    notes: str = "",
    lineage_metadata: dict | None = None,
) -> tuple[PreparednessAction, bool]:
    allowed_action_types = {
        PreparednessAction.ACTION_FACILITY_ORS_REVIEW,
        PreparednessAction.ACTION_FACILITY_STAFFING_REVIEW,
    }
    if action_type not in allowed_action_types:
        raise ValueError("Facility readiness reviews can only create facility readiness preparedness actions.")
    if review.status not in FacilityReadinessReview.ACTIVE_STATUSES:
        raise ValueError("Only active facility readiness reviews can create preparedness actions.")

    resolved_priority = priority or _preparedness_priority_for_facility_review(review)
    resolved_due_at = _preparedness_due_at(resolved_priority, due_at)
    return get_or_create_preparedness_action(
        ward=review.ward,
        facility=review.facility,
        action_type=action_type,
        source_trigger_type=PreparednessAction.SOURCE_FACILITY_READINESS_REVIEW,
        actor=actor,
        facility_readiness_review=review,
        priority=resolved_priority,
        status=status,
        assigned_to=assigned_to or review.assigned_to,
        assigned_to_team=assigned_to_team,
        due_at=resolved_due_at,
        sla_target_at=sla_target_at or resolved_due_at,
        notes=notes
        or "Preparedness action created explicitly from facility readiness review; review state remains separate.",
        lineage_metadata=_preparedness_lineage_metadata(
            source_kind="facility_readiness_review",
            extra={
                "facility_readiness_review_public_id": str(review.public_id),
                "facility_public_id": str(review.facility.public_id),
                "review_status": review.status,
                "review_severity": review.severity,
                "reason_codes": review.reason_codes,
            },
            user_metadata=lineage_metadata,
        ),
    )


def create_preparedness_action_from_facility_escalation(
    escalation: FacilityReadinessEscalation,
    *,
    actor=None,
    action_type: str = PreparednessAction.ACTION_COUNTY_ESCALATION,
    priority: str | None = None,
    status: str = PreparednessAction.STATUS_QUEUED,
    assigned_to=None,
    assigned_to_team: str = "",
    due_at=None,
    sla_target_at=None,
    notes: str = "",
    lineage_metadata: dict | None = None,
) -> tuple[PreparednessAction, bool]:
    if action_type != PreparednessAction.ACTION_COUNTY_ESCALATION:
        raise ValueError("Facility escalations can only create county escalation preparedness actions.")
    if escalation.status not in FacilityReadinessEscalation.ACTIVE_STATUSES:
        raise ValueError("Only active facility escalations can create preparedness actions.")

    resolved_priority = priority or _preparedness_priority_for_facility_escalation(escalation)
    resolved_due_at = _preparedness_due_at(resolved_priority, due_at)
    return get_or_create_preparedness_action(
        ward=escalation.ward,
        facility=escalation.facility,
        action_type=action_type,
        source_trigger_type=PreparednessAction.SOURCE_FACILITY_ESCALATION,
        actor=actor,
        facility_readiness_review=escalation.review,
        facility_escalation=escalation,
        priority=resolved_priority,
        status=status,
        assigned_to=assigned_to or escalation.assigned_to,
        assigned_to_team=assigned_to_team or "County operations",
        due_at=resolved_due_at,
        sla_target_at=sla_target_at or resolved_due_at,
        notes=notes
        or "Preparedness action created explicitly from county facility escalation; escalation state remains separate.",
        lineage_metadata=_preparedness_lineage_metadata(
            source_kind="facility_escalation",
            extra={
                "facility_escalation_public_id": str(escalation.public_id),
                "facility_readiness_review_public_id": str(escalation.review.public_id),
                "facility_public_id": str(escalation.facility.public_id),
                "escalation_status": escalation.status,
                "escalation_severity": escalation.severity,
            },
            user_metadata=lineage_metadata,
        ),
    )


WARD_DETAIL_STATUS_LABELS = {
    WARD_DETAIL_STATUS_NONE: "No active trigger",
    WARD_DETAIL_STATUS_TRIGGER_ACTIVE: "Trigger active",
    WARD_DETAIL_STATUS_REVIEW_PENDING: "Awaiting review",
    WARD_DETAIL_STATUS_ACTION_IN_PROGRESS: "Action in progress",
    WARD_DETAIL_STATUS_RESOLVED: "Resolved",
}

FACILITY_READINESS_DECISION_STATE_CALM = "CALM"
FACILITY_READINESS_DECISION_STATE_REVIEW = "REVIEW"
FACILITY_READINESS_DECISION_STATE_DEGRADED_CONFIDENCE = "DEGRADED_CONFIDENCE"

FACILITY_READINESS_DECISION_CONFIDENCE_NORMAL = "NORMAL"
FACILITY_READINESS_DECISION_CONFIDENCE_DEGRADED = "DEGRADED"

FACILITY_READINESS_REASON_HIGH_READINESS_DIFFERENCE = "HIGH_READINESS_DIFFERENCE"
FACILITY_READINESS_REASON_MODERATE_READINESS_DIFFERENCE = "MODERATE_READINESS_DIFFERENCE"
FACILITY_READINESS_REASON_ELEVATED_WARD_RISK = "ELEVATED_WARD_RISK"
FACILITY_READINESS_REASON_STALE_INPUTS = "STALE_INPUTS"
FACILITY_READINESS_REASON_MULTIPLE_ALERTS_IN_WARD = "MULTIPLE_ALERTS_IN_WARD"
FACILITY_READINESS_REASON_FORECAST_PRESSURE_ELEVATED = "FORECAST_PRESSURE_ELEVATED"
FACILITY_READINESS_REASON_CALM_VISIBLE_SCOPE = "CALM_VISIBLE_SCOPE"
FACILITY_READINESS_REASON_WEAK_PROXY_INPUTS = "WEAK_PROXY_INPUTS"


def _workflow_rule_basis(rule_id: str, rule_label: str, inputs: list[str]) -> dict:
    return {
        "source": "backend_workflow_rules_v1",
        "rule_id": rule_id,
        "rule_label": rule_label,
        "inputs": inputs,
    }


def _workflow_alert_delivery_state(alerts: list[Alert]) -> str:
    if not alerts:
        return "awaiting_review"
    if any(alert.status == Alert.STATUS_FAILED for alert in alerts):
        return "triggered_failed"
    if any(alert.status == Alert.STATUS_RETRY_PENDING for alert in alerts):
        return "triggered_retry_pending"
    if any(alert.status == Alert.STATUS_QUEUED for alert in alerts):
        return "triggered_queued"
    return "triggered_delivered"


def _workflow_alert_delivery_label(state: str) -> str:
    if state == "no_active_delivery":
        return "No active delivery"
    if state == "triggered_delivered":
        return "Triggered and delivered"
    if state == "triggered_retry_pending":
        return "Triggered but retry pending"
    if state == "triggered_failed":
        return "Triggered but failed"
    if state == "triggered_queued":
        return "Triggered and queued"
    return "Trigger detected, awaiting alert request"


def _workflow_status_from_delivery_state(state: str) -> str:
    if state == "triggered_failed":
        return AlertWorkflowState.STATUS_FAILED
    if state == "triggered_retry_pending":
        return AlertWorkflowState.STATUS_RETRY_PENDING
    if state == "triggered_queued":
        return AlertWorkflowState.STATUS_QUEUED
    if state == "triggered_delivered":
        return AlertWorkflowState.STATUS_DELIVERED
    return AlertWorkflowState.STATUS_REVIEW_PENDING


def _workflow_confidence_label(confidence: str) -> str:
    if confidence == "high":
        return "High confidence"
    if confidence == "moderate":
        return "Moderate confidence"
    return "Review required"


def _ward_workflow_requires_action(status: str | None) -> bool:
    return status in {
        WARD_DETAIL_STATUS_REVIEW_PENDING,
        WARD_DETAIL_STATUS_ACTION_IN_PROGRESS,
    }


def _ward_detail_status_for_workflow(workflow: AlertWorkflowState) -> str:
    if workflow.status == AlertWorkflowState.STATUS_REVIEW_PENDING:
        return WARD_DETAIL_STATUS_REVIEW_PENDING
    if workflow.status in {
        AlertWorkflowState.STATUS_QUEUED,
        AlertWorkflowState.STATUS_RETRY_PENDING,
        AlertWorkflowState.STATUS_FAILED,
    }:
        return WARD_DETAIL_STATUS_ACTION_IN_PROGRESS
    if workflow.status == AlertWorkflowState.STATUS_DELIVERED:
        return WARD_DETAIL_STATUS_TRIGGER_ACTIVE
    if workflow.status == AlertWorkflowState.STATUS_RESOLVED:
        return (
            WARD_DETAIL_STATUS_RESOLVED
            if workflow.delivered_alert_count > 0
            else WARD_DETAIL_STATUS_NONE
        )
    return WARD_DETAIL_STATUS_NONE


def _ward_detail_status_label(status: str) -> str:
    return WARD_DETAIL_STATUS_LABELS.get(status, "Unknown")


def _ward_workflow_eligible_actions(workflow: AlertWorkflowState) -> list[str]:
    normalized_status = _ward_detail_status_for_workflow(workflow)
    actions: list[str] = []

    if normalized_status in {
        WARD_DETAIL_STATUS_REVIEW_PENDING,
        WARD_DETAIL_STATUS_TRIGGER_ACTIVE,
        WARD_DETAIL_STATUS_ACTION_IN_PROGRESS,
    }:
        actions.append("REVIEW_TRIGGER")
    elif normalized_status == WARD_DETAIL_STATUS_NONE:
        actions.append("OPEN_TRIGGER_FLOW")

    for action in workflow.eligible_actions or []:
        if action == "view_alerts":
            mapped = "VIEW_ALERT_HISTORY"
        elif normalized_status in {
            WARD_DETAIL_STATUS_REVIEW_PENDING,
            WARD_DETAIL_STATUS_TRIGGER_ACTIVE,
            WARD_DETAIL_STATUS_ACTION_IN_PROGRESS,
        }:
            mapped = "REVIEW_TRIGGER"
        else:
            mapped = "OPEN_TRIGGER_FLOW"
        if mapped not in actions:
            actions.append(mapped)

    if "VIEW_ALERT_HISTORY" not in actions:
        actions.append("VIEW_ALERT_HISTORY")

    return actions


def _ward_decision_summary_for_workflow(workflow: AlertWorkflowState) -> dict:
    normalized_status = _ward_detail_status_for_workflow(workflow)
    action_required = _ward_workflow_requires_action(normalized_status)

    if normalized_status == WARD_DETAIL_STATUS_REVIEW_PENDING:
        primary_cta_kind = "REVIEW_TRIGGER"
        headline = "Action required. Review active alerts and trigger status."
    elif normalized_status == WARD_DETAIL_STATUS_ACTION_IN_PROGRESS:
        primary_cta_kind = "REVIEW_TRIGGER"
        headline = "Trigger action is in progress. Review delivery status and continue follow-up."
    elif normalized_status == WARD_DETAIL_STATUS_TRIGGER_ACTIVE:
        primary_cta_kind = "REVIEW_TRIGGER"
        headline = "Trigger already active. Review the current trigger before creating new response work."
    elif normalized_status == WARD_DETAIL_STATUS_RESOLVED:
        primary_cta_kind = "VIEW_ALERT_HISTORY"
        headline = "No active trigger action is required right now."
    elif normalized_status == WARD_DETAIL_STATUS_NONE:
        primary_cta_kind = "OPEN_TRIGGER_FLOW"
        headline = "No active trigger action is required right now."
    else:
        primary_cta_kind = "VIEW_ALERT_HISTORY"
        headline = "Review the current ward workflow state."

    next_steps = (
        ["Review trigger", "Review full alert history"]
        if primary_cta_kind == "REVIEW_TRIGGER"
        else ["Open Trigger Flow", "Review full alert history"]
        if primary_cta_kind == "OPEN_TRIGGER_FLOW"
        else ["Review full alert history", "Open Trigger Flow"]
    )

    return {
        "action_required": action_required,
        "headline": headline,
        "why": workflow.trigger_reason or workflow.recommended_action,
        "next_steps": next_steps,
        "primary_cta_kind": primary_cta_kind,
    }


def _ward_header_context(
    ward: Ward,
    workflow: AlertWorkflowState,
    current_risk: dict,
    freshness: dict,
    related_alerts: list[Alert],
) -> dict:
    latest_record_at = (
        workflow.latest_risk_update_at
        or current_risk["generated_at"]
        or ward.updated_at
    )

    return {
        "last_alert_at": related_alerts[0].created_at if related_alerts else None,
        "latest_record_at": latest_record_at,
        "freshness_state": "STALE" if freshness["is_stale"] else "FRESH",
        "trigger_state": _ward_detail_status_for_workflow(workflow),
        "expected_cases_7d": workflow.predicted_cases if workflow.predicted_cases is not None else current_risk["predicted_cases"],
        "risk_score": workflow.risk_score if workflow.risk_score is not None else current_risk["risk_score"],
    }


def _ward_workflow_summary(workflow: AlertWorkflowState) -> dict:
    normalized_status = _ward_detail_status_for_workflow(workflow)
    return {
        "public_id": str(workflow.public_id),
        "status": normalized_status,
        "status_label": _ward_detail_status_label(normalized_status),
        "recommended_action": workflow.recommended_action,
        "expected_operational_effect": workflow.expected_operational_effect,
        "eligible_actions": _ward_workflow_eligible_actions(workflow),
        "active_alert_count": workflow.active_alert_count,
        "retry_pending_alert_count": workflow.retry_pending_alert_count,
        "failed_alert_count": workflow.failed_alert_count,
        "queued_alert_count": workflow.queued_alert_count,
        "latest_risk_update_at": workflow.latest_risk_update_at,
        "updated_at": workflow.updated_at,
    }


def _recommended_trigger_type_for_workflow(workflow: AlertWorkflowState) -> str:
    decision_policy = (workflow.metadata or {}).get("decision_policy") or {}
    if decision_policy.get("alert_decision") in {DECISION_URGENT_ALERT, DECISION_ALERT_CANDIDATE}:
        return TRIGGER_TYPE_HIGH_RISK_ESCALATION
    if workflow.alert_delivery_state in {"triggered_failed", "triggered_retry_pending"}:
        return TRIGGER_TYPE_DELIVERY_RETRY
    if workflow.active_alert_count > 0 or workflow.alert_delivery_state in {"triggered_queued", "triggered_delivered"}:
        return TRIGGER_TYPE_FOLLOW_UP_REVIEW
    if workflow.risk_level == Ward.RISK_HIGH:
        return TRIGGER_TYPE_HIGH_RISK_ESCALATION
    return TRIGGER_TYPE_CUSTOM


def _what_happens_if_no_action(workflow: AlertWorkflowState) -> str:
    if workflow.alert_delivery_state == "triggered_failed":
        return "Delivery failure will remain unresolved and the ward may miss the intended follow-up path."
    if workflow.alert_delivery_state == "triggered_retry_pending":
        return "The retry will remain pending and field follow-up may still stall if delivery stays blocked."
    if workflow.alert_delivery_state == "triggered_queued":
        return "The queued request will stay in flight without operator verification of first delivery progress."
    if workflow.active_alert_count > 0:
        return f"{workflow.active_alert_count} active alert{'s' if workflow.active_alert_count != 1 else ''} will remain unresolved in the current review loop."
    if workflow.risk_level == Ward.RISK_HIGH:
        return "This ward will remain at elevated risk without an operational response request being confirmed."
    if workflow.risk_level == Ward.RISK_MEDIUM:
        return "This ward will remain under watch without a confirmed follow-up action."
    return "The ward will stay in routine monitoring without any additional response request."


def _why_this_might_need_an_alert(workflow: AlertWorkflowState) -> list[str]:
    reasons: list[str] = []
    decision_policy = (workflow.metadata or {}).get("decision_policy") or {}
    alert_decision = decision_policy.get("alert_decision")
    if workflow.active_alert_count > 0:
        reasons.append(
            f"{workflow.active_alert_count} active alert{'s' if workflow.active_alert_count != 1 else ''} require follow-up."
        )
    if workflow.alert_delivery_state == "triggered_failed":
        reasons.append("Delivery failed in the current cycle.")
    elif workflow.alert_delivery_state == "triggered_retry_pending":
        reasons.append("Delivery retry is still pending in the current cycle.")
    elif workflow.alert_delivery_state == "triggered_queued":
        reasons.append("A queued trigger request is still awaiting first delivery work.")
    elif alert_decision == DECISION_URGENT_ALERT:
        reasons.append("The active decision policy classified this ward as an urgent alert.")
    elif alert_decision == DECISION_ALERT_CANDIDATE:
        reasons.append("The active decision policy classified this ward as an alert candidate.")
    elif alert_decision == DECISION_WATCHLIST_ONLY:
        reasons.append("The active decision policy classified this ward as watchlist-only.")
    elif workflow.risk_level == Ward.RISK_HIGH:
        reasons.append("The ward is currently in the promoted high-risk band.")
    elif workflow.risk_level == Ward.RISK_MEDIUM:
        reasons.append("The ward is currently at watch level and needs review before escalation.")
    else:
        reasons.append("Recent workflow state suggests a guided review before taking action.")
    return reasons


def _surveillance_alert_evidence_for_ward(ward: Ward, *, as_of=None) -> dict:
    context = build_surveillance_feature_context_for_ward(ward, as_of=as_of)
    return {
        "schema_version": context["schema_version"],
        "ward_id": ward.id,
        "ward_name": ward.name,
        "recent_suspected_cases_28d": context["surveillance_recent_suspected_cases_28d"],
        "recent_confirmed_cases_28d": context["surveillance_recent_confirmed_cases_28d"],
        "recent_proxy_cases_28d": context["surveillance_recent_proxy_cases_28d"],
        "recent_total_cases_28d": context["surveillance_recent_total_cases_28d"],
        "active_label_count_28d": context["surveillance_active_label_count_28d"],
        "watch_label_count_28d": context["surveillance_watch_label_count_28d"],
        "confirmed_label_window_count_28d": context["surveillance_confirmed_label_window_count_28d"],
        "proxy_only_label_window_count_28d": context["surveillance_proxy_only_label_window_count_28d"],
        "delayed_or_stale_record_count_28d": context["surveillance_delayed_or_stale_record_count_28d"],
        "latest_label_window_ref": context["surveillance_latest_label_window_ref"],
        "latest_label_dataset_ref": context["surveillance_latest_label_dataset_ref"],
        "latest_label_truth_level": context["surveillance_latest_label_truth_level"],
        "latest_freshness_state": context["surveillance_latest_freshness_state"],
        "label_truth_state": context["surveillance_label_truth_state"],
        "source_coverage_summary": context["surveillance_source_coverage_summary"],
        "truth_gate": context["truth_gate"],
        "proxy_only_as_confirmed_allowed": False,
        "caveat": context["surveillance_display_caveat"],
    }


def _surveillance_trigger_reason_items(evidence: dict) -> list[dict]:
    items = []
    latest_label_ref = evidence.get("latest_label_window_ref")
    label_truth_state = evidence.get("label_truth_state") or "no_surveillance_label_window"
    if latest_label_ref:
        items.append(
            {
                "label": "Surveillance label window",
                "detail": (
                    f"Latest label window {latest_label_ref} is classified as {label_truth_state}; "
                    f"freshness is {evidence.get('latest_freshness_state') or 'unknown'}."
                ),
                "tone": "info" if label_truth_state == "confirmed_surveillance_truth" else "warning",
            }
        )
    if int(evidence.get("recent_total_cases_28d") or 0) > 0:
        items.append(
            {
                "label": "Recent surveillance cases",
                "detail": (
                    f"{evidence.get('recent_total_cases_28d')} recent surveillance cases are visible "
                    "in the 28 day context window."
                ),
                "tone": "warning",
            }
        )
    if int(evidence.get("proxy_only_label_window_count_28d") or 0) > 0 and not int(
        evidence.get("confirmed_label_window_count_28d") or 0
    ):
        items.append(
            {
                "label": "Proxy-only surveillance evidence",
                "detail": "The visible surveillance label context is proxy-only and must not be treated as confirmed outbreak truth.",
                "tone": "warning",
            }
        )
    if int(evidence.get("delayed_or_stale_record_count_28d") or 0) > 0:
        items.append(
            {
                "label": "Delayed or stale surveillance reporting",
                "detail": "Some surveillance records in the context window are delayed or stale.",
                "tone": "warning",
            }
        )
    return items


def _workflow_payload_for_ward(
    ward: Ward,
    latest_risk: RiskScore | None,
    alerts: list[Alert],
    *,
    manual_request_queued_at=None,
    as_of=None,
) -> dict:
    delivery_state = _workflow_alert_delivery_state(alerts)
    active_alert_count = len(alerts)
    delivered_alert_count = sum(1 for alert in alerts if alert.status == Alert.STATUS_DELIVERED)
    retry_pending_alert_count = sum(1 for alert in alerts if alert.status == Alert.STATUS_RETRY_PENDING)
    failed_alert_count = sum(1 for alert in alerts if alert.status == Alert.STATUS_FAILED)
    queued_alert_count = sum(1 for alert in alerts if alert.status == Alert.STATUS_QUEUED)

    risk_level = latest_risk.risk_level if latest_risk else ward.current_risk_level
    risk_score = latest_risk.score if latest_risk else ward.current_risk_score
    predicted_cases = latest_risk.predicted_cases if latest_risk else 0
    decision_policy = latest_risk.decision_policy if latest_risk else {}
    alert_decision = decision_policy.get("alert_decision")
    has_decision_policy_trace = bool(
        decision_policy.get("policy_version") or decision_policy.get("schema_version") or alert_decision
    )
    surveillance_evidence = _surveillance_alert_evidence_for_ward(ward, as_of=as_of)

    timestamps = [value for value in [manual_request_queued_at, latest_risk.generated_at if latest_risk else None, *(alert.created_at for alert in alerts)] if value]
    triggered_at = max(timestamps) if timestamps else None

    if manual_request_queued_at and not alerts:
        status = AlertWorkflowState.STATUS_QUEUED
        decision_mode = "triggered"
        confidence = "high" if risk_level == Ward.RISK_HIGH else "moderate"
        trigger_severity = AlertWorkflowState.SEVERITY_HIGH if risk_level == Ward.RISK_HIGH else AlertWorkflowState.SEVERITY_MEDIUM
        reason_flagged = f"{ward.name} has a queued manual alert request awaiting backend delivery work."
        trigger_reason = f"{ward.name} has a manual alert request queued from the dashboard trigger flow."
        recommended_action = "Watch the queued request until the first alert record is created and avoid creating duplicate response work."
        recommended_response = "Track the queued trigger request and confirm that downstream alert creation completes."
        expected_operational_effect = "Preserves a governed handoff from manual review into backend alert creation."
        rules_basis = _workflow_rule_basis(
            "manual_trigger_request_queued",
            "Manual trigger request queued",
            ["dashboard trigger request accepted", "backend task queued", "no alert record created yet"],
        )
        trigger_reason_items = [
            {
                "label": "Manual trigger queued",
                "detail": "A dashboard operator has already queued this ward for alert creation.",
                "tone": "warning",
            }
        ]
        eligible_actions = ["view_alerts", "investigate"]
    elif delivery_state == "triggered_failed":
        status = AlertWorkflowState.STATUS_FAILED
        decision_mode = "triggered"
        confidence = "high"
        trigger_severity = AlertWorkflowState.SEVERITY_HIGH
        reason_flagged = f"{ward.name} has a recorded trigger with failed alert delivery."
        trigger_reason = f"{ward.name} has a recorded trigger with at least one failed delivery attempt that still needs operator follow-up."
        recommended_action = "Inspect the failed alert record, confirm the recipient path, and decide whether to resend or escalate manually."
        recommended_response = recommended_action
        expected_operational_effect = "Keeps failed delivery from being mistaken for completed operational follow-up."
        rules_basis = _workflow_rule_basis(
            "failed_alert_delivery_followup",
            "Failed alert delivery follow-up",
            ["recorded trigger exists", "alert delivery failed"],
        )
        trigger_reason_items = [
            {"label": "Delivery failure", "detail": "At least one alert delivery failed for this ward.", "tone": "danger"}
        ]
        eligible_actions = ["view_alerts", "investigate", "dispatch_chvs"]
    elif delivery_state == "triggered_retry_pending":
        status = AlertWorkflowState.STATUS_RETRY_PENDING
        decision_mode = "triggered"
        confidence = "high" if risk_level == Ward.RISK_HIGH else "moderate"
        trigger_severity = AlertWorkflowState.SEVERITY_HIGH if risk_level == Ward.RISK_HIGH else AlertWorkflowState.SEVERITY_MEDIUM
        reason_flagged = f"{ward.name} has a recorded trigger with delivery retry still pending."
        trigger_reason = f"{ward.name} has a recorded trigger with delivery retry still pending."
        recommended_action = "Track the pending retry, confirm field conditions, and prepare a manual follow-up if delivery remains blocked."
        recommended_response = recommended_action
        expected_operational_effect = "Prevents retry-pending alerts from being treated as completed operational action."
        rules_basis = _workflow_rule_basis(
            "retry_pending_alert_followup",
            "Retry-pending alert follow-up",
            ["recorded trigger exists", "alert retry pending"],
        )
        trigger_reason_items = [
            {"label": "Delivery retry pending", "detail": "At least one alert retry remains pending for this ward.", "tone": "warning"}
        ]
        eligible_actions = ["view_alerts", "investigate", "dispatch_chvs"]
    elif delivery_state == "triggered_queued":
        status = AlertWorkflowState.STATUS_QUEUED
        decision_mode = "triggered"
        confidence = "high" if risk_level == Ward.RISK_HIGH else "moderate"
        trigger_severity = AlertWorkflowState.SEVERITY_HIGH if risk_level == Ward.RISK_HIGH else AlertWorkflowState.SEVERITY_MEDIUM
        reason_flagged = f"{ward.name} has a recorded trigger and the alert is still queued for delivery."
        trigger_reason = f"{ward.name} has a recorded trigger and the alert is still queued for delivery."
        recommended_action = "Watch the queued alert until the first delivery attempt completes and avoid duplicating the response request."
        recommended_response = recommended_action
        expected_operational_effect = "Keeps queued alerts visible without duplicating response work."
        rules_basis = _workflow_rule_basis(
            "queued_alert_monitoring",
            "Queued alert monitoring",
            ["recorded trigger exists", "delivery has not completed"],
        )
        trigger_reason_items = [
            {"label": "Delivery queued", "detail": "At least one alert is still queued for this ward.", "tone": "warning"}
        ]
        eligible_actions = ["view_alerts", "investigate", "dispatch_chvs"]
    elif delivery_state == "triggered_delivered":
        status = AlertWorkflowState.STATUS_DELIVERED if risk_level != Ward.RISK_LOW else AlertWorkflowState.STATUS_RESOLVED
        decision_mode = "triggered"
        confidence = "high"
        trigger_severity = AlertWorkflowState.SEVERITY_HIGH if risk_level == Ward.RISK_HIGH else AlertWorkflowState.SEVERITY_MEDIUM
        reason_flagged = (
            f"{ward.name} has delivered alert activity and still sits in the current decision surface."
            if risk_level != Ward.RISK_LOW
            else f"{ward.name} has delivered alert activity and is no longer elevated in the current risk surface."
        )
        trigger_reason = (
            f"{ward.name} has a recorded trigger with at least one delivered alert in the current scope."
        )
        recommended_action = (
            "Review the delivered alert outcome, confirm the ward response, and watch for repeat escalation."
            if risk_level != Ward.RISK_LOW
            else "Record the delivered outcome and keep routine monitoring in place unless new risk rises again."
        )
        recommended_response = recommended_action
        expected_operational_effect = "Connects delivered alert records to the current ward posture instead of hiding them as history only."
        rules_basis = _workflow_rule_basis(
            "delivered_alert_review",
            "Delivered alert review",
            ["recorded trigger exists", "at least one delivered alert in scope"],
        )
        trigger_reason_items = [
            {"label": "Delivered alert", "detail": "At least one alert has already been delivered for this ward.", "tone": "info"}
        ]
        eligible_actions = ["view_alerts", "investigate"]
    elif alert_decision in {DECISION_URGENT_ALERT, DECISION_ALERT_CANDIDATE} or risk_level == Ward.RISK_HIGH:
        status = AlertWorkflowState.STATUS_REVIEW_PENDING
        decision_mode = "decision_policy" if has_decision_policy_trace else "risk_only"
        confidence = "high" if alert_decision == DECISION_URGENT_ALERT else "moderate"
        trigger_severity = AlertWorkflowState.SEVERITY_HIGH
        reason_flagged = (
            f"{ward.name} is an alert candidate under the active ward-risk decision policy."
            if has_decision_policy_trace
            else f"{ward.name} is high risk and needs review before an operational alert is created."
        )
        trigger_reason = (
            f"{ward.name} crossed the urgent alert policy and is waiting for human confirmation."
            if alert_decision == DECISION_URGENT_ALERT
            else f"{ward.name} crossed the alert-candidate policy and is waiting for human confirmation."
            if has_decision_policy_trace
            else f"{ward.name} is high risk and is waiting for human confirmation."
        )
        recommended_action = "Review the ward now and decide whether to create an operational alert request."
        recommended_response = recommended_action
        expected_operational_effect = "Preserves a human-reviewed trigger path before the system creates response work."
        rules_basis = (
            _workflow_rule_basis(
                "decision_policy_review_before_alerting",
                "Decision-policy review before alerting",
                [
                    f"policy_version={decision_policy.get('policy_version') or 'unknown'}",
                    f"alert_decision={alert_decision or 'risk_high'}",
                    "no alert created yet",
                ],
            )
            if has_decision_policy_trace
            else _workflow_rule_basis(
                "high_risk_review_before_alerting",
                "High-risk review before alerting",
                [
                    f"risk_level={risk_level or 'unknown'}",
                    f"risk_score={risk_score if risk_score is not None else 'unknown'}",
                    "no alert created yet",
                ],
            )
        )
        trigger_reason_items = [
            {
                "label": "Decision policy threshold" if has_decision_policy_trace else "High risk",
                "detail": (
                    f"{ward.name} is currently classified as {alert_decision or 'risk_high'}."
                    if has_decision_policy_trace
                    else f"{ward.name} is currently classified as high risk."
                ),
                "tone": "danger",
            }
        ]
        eligible_actions = ["investigate", "view_alerts", "send_message"]
    elif alert_decision == DECISION_WATCHLIST_ONLY or risk_level == Ward.RISK_MEDIUM:
        status = AlertWorkflowState.STATUS_REVIEW_PENDING
        decision_mode = "decision_policy" if has_decision_policy_trace else "risk_only"
        confidence = "review"
        trigger_severity = AlertWorkflowState.SEVERITY_MEDIUM
        reason_flagged = (
            f"{ward.name} is the strongest watch-level candidate in the visible scope."
            if has_decision_policy_trace
            else f"{ward.name} has medium risk and should be reviewed before escalation."
        )
        trigger_reason = (
            f"{ward.name} is currently a watchlist-only signal and should be reviewed before escalation."
            if has_decision_policy_trace
            else f"{ward.name} is currently a medium-risk signal and should be reviewed before escalation."
        )
        recommended_action = "Review this watch-level ward and compare adjacent conditions before escalating."
        recommended_response = recommended_action
        expected_operational_effect = "Keeps watch-level wards visible without overstating them as triggered response work."
        rules_basis = (
            _workflow_rule_basis(
                "watchlist_policy_review_before_escalation",
                "Watchlist policy review before escalation",
                [
                    f"policy_version={decision_policy.get('policy_version') or 'unknown'}",
                    "watchlist-only signal visible",
                    "adjacent comparison still required",
                ],
            )
            if has_decision_policy_trace
            else _workflow_rule_basis(
                "medium_risk_review_before_escalation",
                "Medium-risk review before escalation",
                [
                    f"risk_level={risk_level or 'unknown'}",
                    f"risk_score={risk_score if risk_score is not None else 'unknown'}",
                    "adjacent comparison still required",
                ],
            )
        )
        trigger_reason_items = [
            {
                "label": "Watch escalation" if has_decision_policy_trace else "Medium risk",
                "detail": (
                    f"{ward.name} is currently at watch level and needs closer operator review."
                    if has_decision_policy_trace
                    else f"{ward.name} is currently at medium risk and needs closer operator review."
                ),
                "tone": "warning",
            }
        ]
        eligible_actions = ["investigate", "view_alerts"]
    else:
        status = AlertWorkflowState.STATUS_RESOLVED
        decision_mode = "risk_only"
        confidence = "review"
        trigger_severity = AlertWorkflowState.SEVERITY_REVIEW
        reason_flagged = "No elevated trigger condition is visible for this ward right now."
        trigger_reason = f"{ward.name} remains in routine monitoring with no active trigger condition."
        recommended_action = "Continue routine monitoring and review recent activity for any early signal changes."
        recommended_response = recommended_action
        expected_operational_effect = "Keeps resolved workflow state explicit without elevating it into active action work."
        rules_basis = _workflow_rule_basis(
            "resolved_monitor_only",
            "Resolved routine monitoring",
            ["no visible high-risk threshold", "no active alert delivery concern"],
        )
        trigger_reason_items = [
            {"label": "Routine monitoring", "detail": "No active trigger or elevated delivery concern is visible.", "tone": "info"}
        ]
        eligible_actions = ["investigate", "view_alerts"]

    if status == AlertWorkflowState.STATUS_RESOLVED and active_alert_count == 0:
        delivery_state = "no_active_delivery"
    trigger_reason_items = [
        *trigger_reason_items,
        *_surveillance_trigger_reason_items(surveillance_evidence),
    ]

    return {
        "alert": alerts[0] if alerts else None,
        "latest_risk_score": latest_risk,
        "status": status,
        "decision_mode": decision_mode,
        "confidence": confidence,
        "trigger_severity": trigger_severity,
        "alert_delivery_state": delivery_state,
        "alert_delivery_label": _workflow_alert_delivery_label(delivery_state),
        "risk_level": risk_level,
        "risk_score": risk_score,
        "predicted_cases": predicted_cases,
        "reason_flagged": reason_flagged,
        "trigger_reason": trigger_reason,
        "recommended_action": recommended_action,
        "recommended_response": recommended_response,
        "expected_operational_effect": expected_operational_effect,
        "rules_basis": rules_basis,
        "trigger_reason_items": trigger_reason_items,
        "eligible_actions": eligible_actions,
        "active_alert_count": active_alert_count,
        "delivered_alert_count": delivered_alert_count,
        "retry_pending_alert_count": retry_pending_alert_count,
        "failed_alert_count": failed_alert_count,
        "queued_alert_count": queued_alert_count,
        "triggered_at": triggered_at,
        "latest_risk_update_at": latest_risk.generated_at if latest_risk else None,
        "last_manual_request_at": manual_request_queued_at,
        "metadata": {
            "materialized_from": "backend_alert_and_risk_records",
            "delivery_state": delivery_state,
            "surveillance_evidence": surveillance_evidence,
            "surveillance_truth_gate": surveillance_evidence["truth_gate"],
            "decision_policy": decision_policy,
        },
        "last_evaluated_at": timezone.now(),
    }


def sync_alert_workflow_for_ward(
    ward: Ward,
    *,
    actor=None,
    manual_request_queued_at=None,
    record_event: bool = True,
    event_metadata: dict | None = None,
    as_of=None,
) -> AlertWorkflowState:
    latest_risk = latest_promoted_riskscore_for_ward(ward)
    alerts = list(ward.alerts.select_related("risk_score").order_by("-created_at")[:12])
    payload = _workflow_payload_for_ward(
        ward,
        latest_risk,
        alerts,
        manual_request_queued_at=manual_request_queued_at,
        as_of=as_of,
    )
    workflow, created = AlertWorkflowState.objects.get_or_create(ward=ward, defaults=payload)
    old_status = workflow.status
    if not created:
        for field, value in payload.items():
            setattr(workflow, field, value)
        workflow.save()
    action = (
        AlertWorkflowEvent.ACTION_MANUAL_REQUEST_QUEUED
        if manual_request_queued_at
        else AlertWorkflowEvent.ACTION_MATERIALIZED if created or old_status == workflow.status
        else AlertWorkflowEvent.ACTION_STATUS_CHANGED
    )
    if record_event:
        metadata = {"manual_request_queued_at": manual_request_queued_at.isoformat() if manual_request_queued_at else None}
        if event_metadata:
            metadata.update(event_metadata)
        AlertWorkflowEvent.objects.create(
            workflow=workflow,
            actor=actor,
            action=action,
            old_status="" if created else old_status,
            new_status=workflow.status,
            metadata=metadata,
        )
    return workflow


def sync_alert_workflows_for_wards(wards, *, as_of=None) -> list[AlertWorkflowState]:
    workflows: list[AlertWorkflowState] = []
    for ward in wards:
        workflow = sync_alert_workflow_for_ward(ward, as_of=as_of)
        if workflow.status != AlertWorkflowState.STATUS_RESOLVED or workflow.active_alert_count > 0:
            workflows.append(workflow)
    return workflows


def build_alert_workflow_records(workflows) -> list[dict]:
    def workflow_priority(item: AlertWorkflowState):
        severity_rank = {
            AlertWorkflowState.SEVERITY_HIGH: 3,
            AlertWorkflowState.SEVERITY_MEDIUM: 2,
            AlertWorkflowState.SEVERITY_REVIEW: 1,
        }.get(item.trigger_severity, 0)
        status_rank = {
            AlertWorkflowState.STATUS_FAILED: 5,
            AlertWorkflowState.STATUS_RETRY_PENDING: 4,
            AlertWorkflowState.STATUS_QUEUED: 3,
            AlertWorkflowState.STATUS_DELIVERED: 2,
            AlertWorkflowState.STATUS_REVIEW_PENDING: 1,
            AlertWorkflowState.STATUS_RESOLVED: 0,
        }.get(item.status, 0)
        return (status_rank, severity_rank, item.risk_score or 0, item.predicted_cases, item.updated_at)

    records: list[dict] = []
    for workflow in sorted(workflows, key=workflow_priority, reverse=True):
        records.append(
            {
                "id": workflow.id,
                "public_id": workflow.public_id,
                "ward_id": workflow.ward_id,
                "ward_name": workflow.ward.name,
                "status": workflow.status,
                "decision_mode": workflow.decision_mode,
                "confidence": workflow.confidence,
                "trigger_severity": workflow.trigger_severity.lower(),
                "alert_delivery_state": workflow.alert_delivery_state,
                "alert_delivery_label": workflow.alert_delivery_label,
                "risk_level": workflow.risk_level,
                "risk_score": workflow.risk_score,
                "predicted_cases": workflow.predicted_cases,
                "reason_flagged": workflow.reason_flagged,
                "trigger_reason": workflow.trigger_reason,
                "recommended_action": workflow.recommended_action,
                "recommended_response": workflow.recommended_response,
                "expected_operational_effect": workflow.expected_operational_effect,
                "rules_basis": workflow.rules_basis,
                "trigger_reason_items": workflow.trigger_reason_items,
                "eligible_actions": workflow.eligible_actions,
                "active_alert_count": workflow.active_alert_count,
                "delivered_alert_count": workflow.delivered_alert_count,
                "retry_pending_alert_count": workflow.retry_pending_alert_count,
                "failed_alert_count": workflow.failed_alert_count,
                "queued_alert_count": workflow.queued_alert_count,
                "triggered_at": workflow.triggered_at,
                "latest_risk_update_at": workflow.latest_risk_update_at,
                "last_manual_request_at": workflow.last_manual_request_at,
                "updated_at": workflow.updated_at,
            }
        )
    return records


def build_guided_trigger_context(ward: Ward) -> dict:
    workflow = sync_alert_workflow_for_ward(ward, record_event=False)
    latest_risk = latest_promoted_riskscore_for_ward(ward)
    recommended_trigger_type = _recommended_trigger_type_for_workflow(workflow)

    return {
        "ward": {
            "id": ward.id,
            "name": ward.name,
            "county": ward.county,
            "sub_county": ward.sub_county,
        },
        "risk": {
            "level": latest_risk.risk_level if latest_risk else ward.current_risk_level,
            "score": latest_risk.score if latest_risk else ward.current_risk_score,
            "predicted_cases": latest_risk.predicted_cases if latest_risk else 0,
            "last_risk_update_at": latest_risk.generated_at if latest_risk else None,
        },
        "workflow": {
            "status": workflow.status,
            "decision_mode": workflow.decision_mode,
            "trigger_reason": workflow.trigger_reason,
            "recommended_action": workflow.recommended_action,
            "active_alert_count": workflow.active_alert_count,
            "alert_delivery_state": workflow.alert_delivery_state,
            "alert_delivery_label": workflow.alert_delivery_label,
        },
        "system_context": {
            "why_this_might_need_an_alert": _why_this_might_need_an_alert(workflow),
            "what_happens_if_no_action": _what_happens_if_no_action(workflow),
            "trigger_status_label": _ward_detail_status_label(
                _ward_detail_status_for_workflow(workflow)
            ),
            "recommended_trigger_type": recommended_trigger_type,
            "confidence_label": _workflow_confidence_label(workflow.confidence),
        },
        "recipient_preview": {
            "chv_count": CHV.objects.filter(ward=ward, is_active=True).count(),
        },
        "supported_delivery_channels": ["DASHBOARD", "SMS_CHV"],
        "supported_trigger_types": SUPPORTED_TRIGGER_TYPES,
    }


def sanitize_message_override(message_override: str | None) -> str | None:
    if message_override is None:
        return None
    normalized = message_override.strip()
    return normalized or None


def build_guided_trigger_message(
    ward: Ward,
    trigger_type: str | None = None,
    *,
    workflow: AlertWorkflowState | None = None,
    message_override: str | None = None,
) -> tuple[str, str]:
    cleaned_override = sanitize_message_override(message_override)
    if cleaned_override:
        return cleaned_override, MESSAGE_MODE_OPERATOR_EDITED

    effective_workflow = workflow or sync_alert_workflow_for_ward(ward, record_event=False)
    effective_trigger_type = trigger_type or _recommended_trigger_type_for_workflow(effective_workflow)

    if effective_trigger_type == TRIGGER_TYPE_HIGH_RISK_ESCALATION:
        message_preview = (
            f"CHVs: {ward.name} is in a high-risk state. Review field conditions, prioritize follow-up, and report urgent changes."
        )
    elif effective_trigger_type == TRIGGER_TYPE_DELIVERY_RETRY:
        message_preview = (
            f"CHVs: Please follow up in {ward.name}. A previous delivery attempt needs confirmation and the current alert path may require reinforcement."
        )
    elif effective_trigger_type == TRIGGER_TYPE_FOLLOW_UP_REVIEW:
        message_preview = (
            f"CHVs: Please review reported conditions in {ward.name}. Recent alerts require follow-up and confirmation from the field."
        )
    else:
        message_preview = (
            f"CHVs: Please review current conditions in {ward.name} and confirm whether additional response action is needed."
        )

    return message_preview, MESSAGE_MODE_BACKEND_GENERATED


def build_guided_trigger_preview(
    ward: Ward,
    trigger_type: str,
    message_override: str | None = None,
    *,
    template_key: str = "",
    template_version: int | None = None,
    template_language: str = "en",
    template_context: dict | None = None,
) -> dict:
    workflow = sync_alert_workflow_for_ward(ward, record_event=False)
    rendered_template = None
    if template_key:
        risk_score = RiskScore.objects.filter(ward=ward).order_by("-generated_at").first()
        if risk_score is None:
            raise ValueError("A risk score is required before previewing a template-rendered alert.")
        rendered_template = render_message_template(
            template_key=template_key,
            version=template_version,
            language=template_language,
            context=_template_context_for_alert(ward, risk_score, template_context),
            audience_type=MessageTemplate.AUDIENCE_CHV,
            channel=MessageTemplate.CHANNEL_SMS,
        )
        if message_override and message_override.strip() and message_override.strip() != rendered_template.body:
            raise ValueError("Template-rendered alert previews cannot also override message_override.")
        message_preview = rendered_template.body
        message_mode = MESSAGE_MODE_TEMPLATE_RENDERED
    else:
        message_preview, message_mode = build_guided_trigger_message(
            ward,
            trigger_type,
            workflow=workflow,
            message_override=message_override,
        )

    return {
        "message_preview": message_preview,
        "message_mode": message_mode,
        "supports_editing": rendered_template is None,
        "channel_defaults": ["DASHBOARD", "SMS_CHV"],
        "recipient_preview": {
            "chv_count": CHV.objects.filter(ward=ward, is_active=True).count(),
        },
        "recommended_action": workflow.recommended_action,
        "message_template": rendered_template.metadata if rendered_template else {},
    }


def alert_retry_delay() -> timedelta:
    return timedelta(minutes=config("ALERT_RETRY_DELAY_MINUTES", cast=int, default=5))


def get_alert_delivery_pause_state() -> dict:
    control = SystemControlState.objects.filter(
        control_key=SystemControlState.KEY_ALERT_DELIVERY_PAUSE,
    ).select_related("updated_by").first()

    if control is None:
        return {
            "is_active": False,
            "paused_until": None,
            "reason": "",
            "updated_at": None,
            "updated_by": None,
        }

    return {
        "is_active": control.is_currently_active(),
        "paused_until": control.active_until,
        "reason": control.reason,
        "updated_at": control.updated_at,
        "updated_by": control.updated_by.username if control.updated_by_id else None,
    }


def build_system_control_status(*, can_write: bool = False) -> dict:
    pause_state = get_alert_delivery_pause_state()
    decision_policy = current_ward_risk_decision_policy()
    return {
        "mode": "control_contracts_enabled",
        "can_retry_background_jobs": can_write,
        "can_run_manual_risk_scoring": can_write,
        "can_pause_alert_delivery": can_write,
        "alert_delivery_paused": pause_state["is_active"],
        "alert_delivery_paused_until": pause_state["paused_until"],
        "alert_delivery_pause_reason": pause_state["reason"],
        "alert_delivery_pause_updated_at": pause_state["updated_at"],
        "alert_delivery_pause_updated_by": pause_state["updated_by"],
        "ward_risk_decision_policy": {
            "schema_version": decision_policy["schema_version"],
            "policy_version": decision_policy["policy_version"],
            "policy_name": decision_policy.get("policy_name", ""),
            "thresholds": decision_policy["thresholds"],
            "active_control": decision_policy.get("active_control"),
            "audit_history": decision_policy.get("audit_history", []),
        },
    }


def set_alert_delivery_pause(
    *,
    paused: bool,
    actor=None,
    duration_minutes: int = 60,
    reason: str = "",
) -> dict:
    bounded_duration = max(1, min(duration_minutes, 1440))
    with transaction.atomic():
        control, _ = SystemControlState.objects.select_for_update().get_or_create(
            control_key=SystemControlState.KEY_ALERT_DELIVERY_PAUSE,
        )
        if paused:
            control.is_active = True
            control.active_until = timezone.now() + timedelta(minutes=bounded_duration)
            control.reason = reason.strip()
            control.metadata = {
                **(control.metadata or {}),
                "last_action": "paused",
                "duration_minutes": bounded_duration,
            }
        else:
            control.is_active = False
            control.active_until = None
            control.reason = reason.strip()
            control.metadata = {
                **(control.metadata or {}),
                "last_action": "resumed",
            }

        if getattr(actor, "is_authenticated", False):
            control.updated_by = actor
        control.save(update_fields=["is_active", "active_until", "reason", "metadata", "updated_by", "updated_at"])

    return get_alert_delivery_pause_state()


def build_alert_message(
    ward: Ward,
    risk_score: RiskScore,
    *,
    trigger_type: str | None = None,
    message_override: str | None = None,
) -> tuple[str, str]:
    workflow = sync_alert_workflow_for_ward(ward, record_event=False)
    return build_guided_trigger_message(
        ward,
        trigger_type,
        workflow=workflow,
        message_override=message_override,
    )


def send_sms(phone_number: str, message: str, provider_name: str | None = None) -> DeliveryResult:
    provider = get_sms_provider(provider_name=provider_name)
    return provider.send(phone_number, message)


def _template_context_for_chv(chv: CHV, extra_context: dict | None = None) -> dict:
    return {
        "chv_name": chv.name,
        "ward_name": chv.ward.name,
        "ward_id": chv.ward_id,
        **(extra_context or {}),
    }


def _template_context_for_alert(ward: Ward, risk_score: RiskScore, extra_context: dict | None = None) -> dict:
    return {
        "ward_name": ward.name,
        "ward_id": ward.id,
        "risk_level": risk_score.risk_level,
        "risk_score": risk_score.score,
        "predicted_cases": risk_score.predicted_cases,
        **(extra_context or {}),
    }


def _template_context_for_facility_update(
    review: FacilityReadinessReview,
    extra_context: dict | None = None,
) -> dict:
    reason_codes = ", ".join(review.reason_codes or []) or "readiness review"
    return {
        "facility_name": review.facility.name,
        "facility_code": review.facility.facility_code,
        "ward_name": review.ward.name,
        "ward_id": review.ward_id,
        "review_public_id": str(review.public_id),
        "reason_codes": reason_codes,
        **(extra_context or {}),
    }


def _message_template_snapshot(render_result: TemplateRenderResult | None) -> dict:
    if render_result is None:
        return {"template": None, "template_key": "", "template_version": None}
    return {
        "template": render_result.template,
        "template_key": render_result.template.template_key,
        "template_version": render_result.template.version,
    }


def _message_template_language_snapshot(render_result: TemplateRenderResult | None) -> dict:
    if render_result is None:
        return {
            "requested_language": "en",
            "resolved_language": "en",
            "fallback_used": False,
        }
    metadata = render_result.metadata or {}
    requested_language = (metadata.get("requested_language") or render_result.template.language or "en").strip().lower()
    resolved_language = (metadata.get("resolved_language") or render_result.template.language or "en").strip().lower()
    return {
        "requested_language": requested_language or "en",
        "resolved_language": resolved_language or "en",
        "fallback_used": bool(metadata.get("fallback_used")),
    }


def _message_delivery_language_metadata(rendered_template: TemplateRenderResult | None) -> dict:
    language_snapshot = _message_template_language_snapshot(rendered_template)
    return {
        **language_snapshot,
        "template_language": rendered_template.template.language if rendered_template else "",
    }


def _message_delivery_governance_metadata(
    *,
    rendered_template: TemplateRenderResult | None = None,
    audience_decision: dict | None = None,
    audience_scope: dict | None = None,
    workflow: str,
    extra: dict | None = None,
) -> dict:
    return {
        "schema_version": MESSAGE_AUDIENCE_GOVERNANCE_SCHEMA_VERSION,
        "workflow": workflow,
        "template": rendered_template.metadata if rendered_template else {},
        "language": _message_delivery_language_metadata(rendered_template),
        "audience_decision": audience_decision or {},
        "audience_scope": audience_scope or {},
        **(extra or {}),
    }


def normalize_contact_phone_number(phone_number: str) -> str:
    return ContactPreference.normalize_phone_number(phone_number)


def _validate_contact_phone_number(phone_number: str) -> str:
    normalized_phone = normalize_contact_phone_number(phone_number)
    if normalized_phone and not ContactPreference.is_valid_phone_number(normalized_phone):
        raise ValueError("Direct SMS contact phone numbers must be valid Kenyan mobile numbers.")
    return normalized_phone


def contact_reference_for_chv(chv: CHV) -> str:
    return f"chv:{chv.public_id}"


def contact_reference_for_facility_contact(contact: FacilityContact) -> str:
    return f"facility_contact:{contact.public_id}"


def _actor_scope_metadata(actor, *, target_ward_id: int | None = None, system_scope: str = "") -> dict:
    if actor is None or not getattr(actor, "is_authenticated", False):
        return {
            "scope_kind": "system",
            "scope_allowed": True,
            "scope_reason": system_scope or "system_or_background_workflow",
            "actor_id": None,
            "actor_role": "",
            "actor_ward_id": None,
            "target_ward_id": target_ward_id,
        }

    role = getattr(actor, "role", "") or ""
    is_admin = bool(getattr(actor, "is_superuser", False) or role == "ADMIN")
    actor_ward_id = getattr(actor, "ward_id", None)
    same_ward = bool(target_ward_id is not None and actor_ward_id == target_ward_id)
    scope_allowed = bool(is_admin or (role == "SUPERVISOR" and same_ward))
    scope_kind = "admin_global" if is_admin else "assigned_ward" if same_ward else "out_of_scope"
    return {
        "scope_kind": scope_kind,
        "scope_allowed": scope_allowed,
        "scope_reason": "actor_has_admin_scope" if is_admin else "actor_matches_target_ward" if same_ward else "actor_not_assigned_to_target_ward",
        "actor_id": actor.id,
        "actor_role": role,
        "actor_ward_id": actor_ward_id,
        "target_ward_id": target_ward_id,
    }


def _assert_chv_operational_scope(chv: CHV, actor) -> dict:
    scope = _actor_scope_metadata(
        actor,
        target_ward_id=chv.ward_id,
        system_scope="risk_alert_or_system_chv_operational_scope",
    )
    if not scope["scope_allowed"]:
        raise ValueError("CHV operational messages require assigned ward contact scope.")
    return scope


def _assert_facility_contact_scope(contact: FacilityContact, actor) -> dict:
    if not contact.is_active or not contact.is_verified:
        raise ValueError("Facility messages require an active, verified facility contact.")
    scope = _actor_scope_metadata(
        actor,
        target_ward_id=contact.facility.ward_id,
        system_scope="system_facility_update_scope",
    )
    if not scope["scope_allowed"]:
        raise ValueError("Facility update messages require assigned ward contact scope.")
    return {
        **scope,
        "facility_contact_public_id": str(contact.public_id),
        "facility_contact_verified": contact.is_verified,
        "facility_contact_active": contact.is_active,
        "facility_contact_source": contact.source,
        "facility_contact_source_reference": contact.source_reference,
    }


def _lawful_basis_decision(
    preference: ContactPreference | None,
    *,
    metadata: dict | None = None,
    lawful_basis: str = "",
    lawful_basis_reference: str = "",
) -> dict:
    message_metadata = metadata or {}
    preference_metadata = preference.metadata if preference and isinstance(preference.metadata, dict) else {}
    resolved_basis = (
        (lawful_basis or "").strip()
        or str(message_metadata.get("lawful_basis") or "").strip()
        or str(preference_metadata.get("lawful_basis") or "").strip()
    )
    resolved_reference = (
        (lawful_basis_reference or "").strip()
        or str(message_metadata.get("lawful_basis_reference") or "").strip()
        or str(message_metadata.get("lawful_basis_approval_ref") or "").strip()
        or str(preference_metadata.get("lawful_basis_reference") or "").strip()
        or str(preference_metadata.get("lawful_basis_approval_ref") or "").strip()
    )
    approved = bool(
        message_metadata.get("lawful_basis_approved")
        or message_metadata.get("approved_lawful_basis")
        or preference_metadata.get("lawful_basis_approved")
        or preference_metadata.get("approved_lawful_basis")
    )
    return {
        "lawful_basis": resolved_basis,
        "lawful_basis_reference": resolved_reference,
        "lawful_basis_approved": bool(approved and resolved_basis and resolved_reference),
    }


def latest_contact_preference(
    *,
    audience_type: str,
    channel: str,
    phone_number: str = "",
    contact_reference: str = "",
) -> ContactPreference | None:
    normalized_phone = _validate_contact_phone_number(phone_number)
    normalized_reference = (contact_reference or "").strip()
    identity_filter = Q()
    if normalized_phone:
        identity_filter |= Q(phone_number=normalized_phone)
    if normalized_reference:
        identity_filter |= Q(contact_reference=normalized_reference)
    if not identity_filter:
        return None

    now = timezone.now()
    return (
        ContactPreference.objects.filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=now),
            audience_type=audience_type,
            channel=channel,
        )
        .filter(identity_filter)
        .order_by("-recorded_at", "-created_at", "-id")
        .first()
    )


def record_contact_preference_audit_event(
    *,
    action: str,
    audience_type: str,
    channel: str,
    phone_number: str = "",
    contact_reference: str = "",
    actor=None,
    preference: ContactPreference | None = None,
    reason: str = "",
    metadata: dict | None = None,
) -> ContactPreferenceAuditEvent:
    return ContactPreferenceAuditEvent.objects.create(
        preference=preference,
        action=action,
        audience_type=audience_type,
        channel=channel,
        phone_number=phone_number,
        contact_reference=contact_reference,
        actor=_actor_or_none(actor),
        reason=reason.strip(),
        metadata=metadata or {},
    )


def record_contact_preference(
    *,
    audience_type: str,
    channel: str,
    source: str,
    phone_number: str = "",
    contact_reference: str = "",
    consent_status: str = ContactPreference.CONSENT_UNKNOWN,
    opt_out_status: str = ContactPreference.OPT_OUT_NOT_OPTED_OUT,
    source_reference: str = "",
    recorded_by=None,
    recorded_at=None,
    expires_at=None,
    metadata: dict | None = None,
) -> ContactPreference:
    normalized_phone = _validate_contact_phone_number(phone_number)
    with transaction.atomic():
        preference = ContactPreference.objects.create(
            audience_type=audience_type,
            channel=channel,
            phone_number=normalized_phone,
            contact_reference=contact_reference,
            consent_status=consent_status,
            opt_out_status=opt_out_status,
            source=source,
            source_reference=source_reference,
            recorded_by=_actor_or_none(recorded_by),
            recorded_at=recorded_at or timezone.now(),
            expires_at=expires_at,
            metadata=metadata or {},
        )
        record_contact_preference_audit_event(
            action=ContactPreferenceAuditEvent.ACTION_RECORDED,
            audience_type=preference.audience_type,
            channel=preference.channel,
            phone_number=preference.phone_number,
            contact_reference=preference.contact_reference,
            actor=recorded_by,
            preference=preference,
            reason="contact_preference_recorded",
            metadata={
                "consent_status": preference.consent_status,
                "opt_out_status": preference.opt_out_status,
                "source": preference.source,
                "source_reference": preference.source_reference,
                "expires_at": preference.expires_at.isoformat() if preference.expires_at else None,
            },
        )
    return preference


def _contact_preference_block(
    preference: ContactPreference | None,
    *,
    audience_type: str,
    emergency_override: bool,
    lawful_basis_approved: bool = False,
) -> tuple[str, str, str] | None:
    if preference and preference.opt_out_status == ContactPreference.OPT_OUT_OPTED_OUT:
        return (
            ContactPreferenceAuditEvent.ACTION_BLOCKED_OPT_OUT,
            "contact_opted_out",
            "Contact has opted out of this message audience.",
        )

    if preference and preference.consent_status == ContactPreference.CONSENT_DENIED:
        return (
            ContactPreferenceAuditEvent.ACTION_BLOCKED_CONSENT_DENIED,
            "contact_consent_denied",
            "Contact has denied consent for this message audience.",
        )

    if preference and preference.consent_status == ContactPreference.CONSENT_EXPIRED:
        return (
            ContactPreferenceAuditEvent.ACTION_BLOCKED_CONSENT_EXPIRED,
            "contact_consent_expired",
            "Contact consent has expired for this message audience.",
        )

    if (
        audience_type == ContactPreference.AUDIENCE_HOUSEHOLD
        and not emergency_override
        and not lawful_basis_approved
        and (preference is None or preference.consent_status != ContactPreference.CONSENT_GRANTED)
    ):
        return (
            ContactPreferenceAuditEvent.ACTION_BLOCKED_CONSENT_REQUIRED,
            "household_consent_required",
            "Household messaging requires consent or an approved emergency override.",
        )

    return None


def assert_contact_message_allowed(
    *,
    audience_type: str,
    channel: str,
    phone_number: str = "",
    contact_reference: str = "",
    actor=None,
    emergency_override: bool = False,
    override_reason: str = "",
    metadata: dict | None = None,
    audit_allowed: bool = False,
    lawful_basis: str = "",
    lawful_basis_reference: str = "",
    message_purpose: str = MESSAGE_PURPOSE_OPERATIONAL,
) -> ContactPreference | None:
    preference, _decision = authorize_contact_message(
        audience_type=audience_type,
        channel=channel,
        phone_number=phone_number,
        contact_reference=contact_reference,
        actor=actor,
        emergency_override=emergency_override,
        override_reason=override_reason,
        metadata=metadata,
        audit_allowed=audit_allowed,
        lawful_basis=lawful_basis,
        lawful_basis_reference=lawful_basis_reference,
        message_purpose=message_purpose,
    )
    return preference


def authorize_contact_message(
    *,
    audience_type: str,
    channel: str,
    phone_number: str = "",
    contact_reference: str = "",
    actor=None,
    emergency_override: bool = False,
    override_reason: str = "",
    metadata: dict | None = None,
    audit_allowed: bool = False,
    lawful_basis: str = "",
    lawful_basis_reference: str = "",
    message_purpose: str = MESSAGE_PURPOSE_OPERATIONAL,
) -> tuple[ContactPreference | None, dict]:
    normalized_phone = _validate_contact_phone_number(phone_number)
    normalized_reference = (contact_reference or "").strip()
    if not normalized_phone and not normalized_reference:
        raise ValueError("A phone number or contact reference is required before direct messaging.")

    reason = (override_reason or "").strip()
    if emergency_override and not reason:
        raise ValueError("Emergency messaging override requires a reason.")

    preference = latest_contact_preference(
        audience_type=audience_type,
        channel=channel,
        phone_number=normalized_phone,
        contact_reference=normalized_reference,
    )
    lawful_basis_metadata = _lawful_basis_decision(
        preference,
        metadata=metadata,
        lawful_basis=lawful_basis,
        lawful_basis_reference=lawful_basis_reference,
    )
    audit_metadata = {
        **(metadata or {}),
        "preference_public_id": str(preference.public_id) if preference else "",
        "consent_status": preference.consent_status if preference else "",
        "opt_out_status": preference.opt_out_status if preference else "",
        "message_purpose": message_purpose,
        **lawful_basis_metadata,
    }
    decision = {
        "schema_version": MESSAGE_AUDIENCE_GOVERNANCE_SCHEMA_VERSION,
        "audience_type": audience_type,
        "channel": channel,
        "contact_reference": normalized_reference,
        "phone_number_present": bool(normalized_phone),
        "preference_public_id": str(preference.public_id) if preference else "",
        "consent_status": preference.consent_status if preference else "",
        "opt_out_status": preference.opt_out_status if preference else "",
        "source": preference.source if preference else "",
        "source_reference": preference.source_reference if preference else "",
        "message_purpose": message_purpose,
        "emergency_override": bool(emergency_override),
        "override_reason": reason if emergency_override else "",
        **lawful_basis_metadata,
    }
    block = _contact_preference_block(
        preference,
        audience_type=audience_type,
        emergency_override=emergency_override,
        lawful_basis_approved=lawful_basis_metadata["lawful_basis_approved"],
    )
    if block is not None:
        action, block_reason, message = block
        if emergency_override:
            audit_event = record_contact_preference_audit_event(
                action=ContactPreferenceAuditEvent.ACTION_EMERGENCY_OVERRIDE_USED,
                audience_type=audience_type,
                channel=channel,
                phone_number=normalized_phone,
                contact_reference=normalized_reference,
                actor=actor,
                preference=preference,
                reason=reason,
                metadata={**audit_metadata, "overrode_block_reason": block_reason},
            )
            return preference, {
                **decision,
                "allowed": True,
                "decision": "emergency_override_allowed",
                "reason": reason,
                "overrode_block_reason": block_reason,
                "audit_event_public_id": str(audit_event.public_id),
            }
        audit_event = record_contact_preference_audit_event(
            action=action,
            audience_type=audience_type,
            channel=channel,
            phone_number=normalized_phone,
            contact_reference=normalized_reference,
            actor=actor,
            preference=preference,
            reason=block_reason,
            metadata=audit_metadata,
        )
        decision.update(
            {
                "allowed": False,
                "decision": action,
                "reason": block_reason,
                "audit_event_public_id": str(audit_event.public_id),
            }
        )
        raise ValueError(message)

    if emergency_override:
        audit_event = record_contact_preference_audit_event(
            action=ContactPreferenceAuditEvent.ACTION_EMERGENCY_OVERRIDE_USED,
            audience_type=audience_type,
            channel=channel,
            phone_number=normalized_phone,
            contact_reference=normalized_reference,
            actor=actor,
            preference=preference,
            reason=reason,
            metadata=audit_metadata,
        )
    elif audit_allowed:
        audit_event = record_contact_preference_audit_event(
            action=ContactPreferenceAuditEvent.ACTION_ALLOWED,
            audience_type=audience_type,
            channel=channel,
            phone_number=normalized_phone,
            contact_reference=normalized_reference,
            actor=actor,
            preference=preference,
            reason="contact_message_allowed",
            metadata=audit_metadata,
        )
    else:
        audit_event = None

    if emergency_override:
        decision_name = "emergency_override_allowed"
        decision_reason = reason
    elif lawful_basis_metadata["lawful_basis_approved"] and audience_type == ContactPreference.AUDIENCE_HOUSEHOLD:
        decision_name = "approved_lawful_basis_allowed"
        decision_reason = "household_lawful_basis_approved"
    elif preference and preference.consent_status == ContactPreference.CONSENT_GRANTED:
        decision_name = "consent_allowed"
        decision_reason = "contact_message_allowed"
    else:
        decision_name = "operational_contact_allowed"
        decision_reason = "contact_message_allowed"

    return preference, {
        **decision,
        "allowed": True,
        "decision": decision_name,
        "reason": decision_reason,
        "audit_event_public_id": str(audit_event.public_id) if audit_event else "",
    }


def resolve_chv_message_mode() -> str:
    provider_name = config("SMS_PROVIDER", default="stub").strip().lower() or "stub"

    if provider_name == "stub":
        return "SEND"

    if provider_name == "africastalking":
        username = config("AFRICASTALKING_USERNAME", default="").strip()
        api_key = config("AFRICASTALKING_API_KEY", default="").strip()
        return "SEND" if username and api_key else "QUEUE_ONLY"

    return "QUEUE_ONLY"


def resolve_chv_message_delivery_kind() -> str:
    provider_name = config("SMS_PROVIDER", default="stub").strip().lower() or "stub"

    if provider_name == "stub":
        return "SIMULATED"

    if provider_name == "africastalking":
        username = config("AFRICASTALKING_USERNAME", default="").strip()
        api_key = config("AFRICASTALKING_API_KEY", default="").strip()
        return "LIVE" if username and api_key else "QUEUE_ONLY"

    return "QUEUE_ONLY"


def create_chv_message(
    chv: CHV,
    *,
    message_body: str,
    sent_by=None,
    channel: str = CHVMessage.CHANNEL_SMS,
    emergency_override: bool = False,
    override_reason: str = "",
    template_key: str = "",
    template_version: int | None = None,
    template_language: str | None = None,
    template_context: dict | None = None,
) -> CHVMessage:
    mode = resolve_chv_message_mode()
    if mode == "UNAVAILABLE":
        raise ValueError("Messaging is not available in this environment.")

    resolved_delivery_kind = resolve_chv_message_delivery_kind()
    if mode == "QUEUE_ONLY":
        delivery_kind = CHVMessage.DELIVERY_KIND_QUEUE_ONLY
    else:
        delivery_kind = resolved_delivery_kind
    delivery_backend = config("SMS_PROVIDER", default="stub").strip().lower() or "stub"
    audience_scope = _assert_chv_operational_scope(chv, sent_by)
    rendered_template = None
    resolved_message_body = (message_body or "").strip()
    if template_key:
        rendered_template = render_message_template(
            template_key=template_key,
            version=template_version,
            language=template_language or chv.preferred_language or chv.language or "en",
            context=_template_context_for_chv(chv, template_context),
            audience_type=MessageTemplate.AUDIENCE_CHV,
            channel=MessageTemplate.CHANNEL_SMS,
        )
        if resolved_message_body and resolved_message_body != rendered_template.body:
            raise ValueError("Template-rendered CHV messages cannot also override message_body.")
        resolved_message_body = rendered_template.body
    if not resolved_message_body:
        raise ValueError("A message body or template key is required before creating a CHV message.")

    _preference, audience_decision = authorize_contact_message(
        audience_type=ContactPreference.AUDIENCE_CHV,
        channel=channel,
        phone_number=chv.phone_number,
        contact_reference=contact_reference_for_chv(chv),
        actor=sent_by,
        emergency_override=emergency_override,
        override_reason=override_reason,
        audit_allowed=True,
        metadata={
            "workflow": "chv_message",
            "chv_public_id": str(chv.public_id),
            "ward_id": chv.ward_id,
            "delivery_mode": mode,
            "delivery_backend": delivery_backend,
            "message_template": rendered_template.metadata if rendered_template else {},
            "audience_scope": audience_scope,
        },
        message_purpose=MESSAGE_PURPOSE_OPERATIONAL,
    )
    template_snapshot = _message_template_snapshot(rendered_template)
    language_snapshot = _message_template_language_snapshot(rendered_template)
    message_record = CHVMessage.objects.create(
        chv=chv,
        ward=chv.ward,
        sent_by=sent_by,
        channel=channel,
        message_body=resolved_message_body,
        **template_snapshot,
        **language_snapshot,
        governance_metadata=_message_delivery_governance_metadata(
            rendered_template=rendered_template,
            audience_decision=audience_decision,
            audience_scope=audience_scope,
            workflow="chv_message",
            extra={
                "delivery_mode": mode,
                "delivery_backend": delivery_backend,
                "emergency_override": bool(emergency_override),
            },
        ),
        delivery_kind=delivery_kind,
        delivery_backend=delivery_backend if delivery_kind in {CHVMessage.DELIVERY_KIND_LIVE, CHVMessage.DELIVERY_KIND_SIMULATED} else "",
        status=CHVMessage.STATUS_QUEUED if mode == "QUEUE_ONLY" else CHVMessage.STATUS_SENT,
    )

    if mode != "SEND":
        return message_record

    result = send_sms(chv.phone_number, resolved_message_body)
    message_record.provider_reference = result.external_id

    if result.success:
        message_record.status = CHVMessage.STATUS_SENT
        message_record.failure_reason = ""
    else:
        message_record.status = CHVMessage.STATUS_FAILED
        message_record.failure_reason = result.error

    message_record.save(update_fields=["provider_reference", "status", "failure_reason", "updated_at"])
    return message_record


def create_alerts_for_riskscore(
    risk_score: RiskScore,
    send_sms_enabled: bool = False,
    *,
    trigger_type: str | None = None,
    message_override: str | None = None,
    guided_request_metadata: dict | None = None,
    template_key: str = "",
    template_version: int | None = None,
    template_language: str | None = None,
    template_context: dict | None = None,
    template_audience_type: str = MessageTemplate.AUDIENCE_CHV,
    template_channel: str = MessageTemplate.CHANNEL_SMS,
    as_of=None,
) -> list[Alert]:
    require_production_alert_eligibility(risk_score)
    if risk_score.model_run_id:
        truth_blockers = production_model_run_blockers(risk_score.model_run)
        if truth_blockers:
            raise ValueError(f"production_truth_policy_blocked:{','.join(truth_blockers)}")
    if risk_score.model_run_id and not is_promoted_model_run(risk_score.model_run):
        raise ValueError("Alerts can only be created for the active promoted model run.")

    ward = risk_score.ward
    alerts_created: list[Alert] = []
    request_metadata = {
        **(guided_request_metadata or {}),
        "surveillance_evidence": (guided_request_metadata or {}).get("surveillance_evidence")
        or _surveillance_alert_evidence_for_ward(ward, as_of=as_of),
        "model_run_evidence": (guided_request_metadata or {}).get("model_run_evidence")
        or _model_run_alert_evidence_for_riskscore(risk_score),
        "climate_evidence": (guided_request_metadata or {}).get("climate_evidence")
        or _climate_alert_evidence_for_riskscore(risk_score),
        "decision_policy": (guided_request_metadata or {}).get("decision_policy")
        or risk_score.decision_policy
        or {},
    }
    rendered_template = None
    requested_template_language = (template_language or "").strip().lower()
    if template_key:
        rendered_template = render_message_template(
            template_key=template_key,
            version=template_version,
            language=requested_template_language or "en",
            context=_template_context_for_alert(ward, risk_score, template_context),
            audience_type=template_audience_type,
            channel=template_channel,
        )
        if message_override and message_override.strip() and message_override.strip() != rendered_template.body:
            raise ValueError("Template-rendered alerts cannot also override message_override.")
        message = rendered_template.body
        _message_mode = MESSAGE_MODE_TEMPLATE_RENDERED
        request_metadata["message_template"] = rendered_template.metadata
        request_metadata["message_preview_used"] = message
        request_metadata["message_mode"] = MESSAGE_MODE_TEMPLATE_RENDERED
    else:
        message, _message_mode = build_alert_message(
            ward,
            risk_score,
            trigger_type=trigger_type,
            message_override=message_override,
        )

    alerts_logger.info(
        "trigger_alerts_started",
        extra={
            "ward_id": ward.id,
            "risk_score_id": risk_score.id,
            "risk_level": risk_score.risk_level,
            "send_sms_enabled": send_sms_enabled,
            "trigger_type": trigger_type,
        },
    )

    delivered_at = timezone.now()
    dashboard_audience_decision = {
        "schema_version": MESSAGE_AUDIENCE_GOVERNANCE_SCHEMA_VERSION,
        "audience_type": MessageTemplate.AUDIENCE_COUNTY_OPERATOR,
        "channel": MessageTemplate.CHANNEL_DASHBOARD,
        "allowed": True,
        "decision": "internal_dashboard_delivery_allowed",
        "reason": "dashboard_delivery_uses_authenticated_operator_access_controls",
        "message_purpose": MESSAGE_PURPOSE_RISK_ALERT,
    }
    dashboard_rendered_template = (
        rendered_template
        if rendered_template
        and rendered_template.template.audience_type == MessageTemplate.AUDIENCE_COUNTY_OPERATOR
        and rendered_template.template.channel == MessageTemplate.CHANNEL_DASHBOARD
        else None
    )
    dashboard_alert = Alert.objects.create(
        ward=ward,
        risk_score=risk_score,
        channel=Alert.CHANNEL_DASHBOARD,
        recipient="dashboard",
        message=message,
        status=Alert.STATUS_DELIVERED,
        delivery_backend="internal-dashboard",
        guided_request_metadata=request_metadata,
        attempt_count=1,
        max_attempts=1,
        last_attempted_at=delivered_at,
        sent_at=delivered_at,
        **_message_template_snapshot(dashboard_rendered_template),
        **_message_template_language_snapshot(dashboard_rendered_template),
        governance_metadata=_message_delivery_governance_metadata(
            rendered_template=dashboard_rendered_template,
            audience_decision=dashboard_audience_decision,
            audience_scope={
                "scope_kind": "internal_dashboard",
                "scope_allowed": True,
                "target_ward_id": ward.id,
            },
            workflow="risk_alert_dashboard",
        ),
    )
    alerts_created.append(dashboard_alert)

    if send_sms_enabled:
        chvs = CHV.objects.filter(ward=ward, is_active=True)

        for chv in chvs:
            audience_scope = _assert_chv_operational_scope(chv, None)
            sms_rendered_template = rendered_template
            sms_message = message
            sms_request_metadata = request_metadata
            if template_key:
                sms_rendered_template = render_message_template(
                    template_key=template_key,
                    version=template_version,
                    language=requested_template_language or chv.preferred_language or chv.language or "en",
                    context=_template_context_for_alert(ward, risk_score, template_context),
                    audience_type=template_audience_type,
                    channel=template_channel,
                )
                sms_message = sms_rendered_template.body
                sms_request_metadata = {
                    **request_metadata,
                    "message_template": sms_rendered_template.metadata,
                    "message_preview_used": sms_message,
                    "message_mode": MESSAGE_MODE_TEMPLATE_RENDERED,
                }
            try:
                _preference, audience_decision = authorize_contact_message(
                    audience_type=ContactPreference.AUDIENCE_CHV,
                    channel=ContactPreference.CHANNEL_SMS,
                    phone_number=chv.phone_number,
                    contact_reference=contact_reference_for_chv(chv),
                    audit_allowed=True,
                    metadata={
                        "workflow": "risk_alert_sms",
                        "ward_id": ward.id,
                        "risk_score_id": risk_score.id,
                        "audience_scope": audience_scope,
                        "message_template": sms_rendered_template.metadata if sms_rendered_template else {},
                    },
                    message_purpose=MESSAGE_PURPOSE_RISK_ALERT,
                )
            except ValueError as exc:
                alerts_logger.warning(
                    "alert_sms_contact_preference_blocked",
                    extra={
                        "ward_id": ward.id,
                        "risk_score_id": risk_score.id,
                        "chv_id": chv.id,
                        "reason": str(exc),
                    },
                )
                continue

            alert = Alert.objects.create(
                ward=ward,
                risk_score=risk_score,
                channel=Alert.CHANNEL_SMS,
                recipient=chv.phone_number,
                message=sms_message,
                status=Alert.STATUS_QUEUED,
                delivery_backend=config("SMS_PROVIDER", default="stub").strip().lower() or "stub",
                guided_request_metadata=sms_request_metadata,
                max_attempts=config("ALERT_MAX_ATTEMPTS", cast=int, default=3),
                **_message_template_snapshot(sms_rendered_template),
                **_message_template_language_snapshot(sms_rendered_template),
                governance_metadata=_message_delivery_governance_metadata(
                    rendered_template=sms_rendered_template,
                    audience_decision=audience_decision,
                    audience_scope=audience_scope,
                    workflow="risk_alert_sms",
                    extra={
                        "risk_score_id": risk_score.id,
                        "risk_level": risk_score.risk_level,
                    },
                ),
            )
            alerts_created.append(alert)

    alerts_logger.info(
        "trigger_alerts_completed",
        extra={
            "ward_id": ward.id,
            "risk_score_id": risk_score.id,
            "alerts_created": len(alerts_created),
        },
    )

    sync_alert_workflow_for_ward(ward, as_of=as_of)
    return alerts_created


def _climate_alert_evidence_for_riskscore(risk_score: RiskScore) -> dict:
    decision_policy = risk_score.decision_policy or {}
    policy_inputs = decision_policy.get("inputs") or {}
    source_confidence = policy_inputs.get("source_confidence") or {}
    climate_coverage = (
        policy_inputs.get("climate_coverage")
        or source_confidence.get("climate_coverage")
        or {}
    )
    if climate_coverage:
        return climate_alert_evidence_from_prediction({"climate_coverage": climate_coverage})

    feature_lineage = _feature_lineage_for_riskscore(risk_score)
    climate_rows = feature_lineage.get("climate_coverage_rows") or []
    if climate_rows:
        return climate_alert_evidence_from_prediction({"climate_coverage": climate_rows[0]})

    return climate_alert_evidence_from_prediction({})


def _model_run_alert_evidence_for_riskscore(risk_score: RiskScore) -> dict:
    model_run = risk_score.model_run
    if model_run is None:
        return {
            "model_run_id": None,
            "model_version": risk_score.model_version,
            "promotion_target": None,
            "phase_4_promotion_evidence_persisted": False,
            "phase_4_promotion_gates_passed": False,
            "promotion_truth_and_leakage_checks_passed": False,
            "climate_coverage_summary": {},
        }

    metadata = model_run.metadata or {}
    evaluation_metrics = model_run.evaluation_metrics or {}
    feature_lineage = _feature_lineage_for_riskscore(risk_score)
    return {
        "model_run_id": model_run.id,
        "model_version": model_run.model_version,
        "algorithm_name": model_run.algorithm_name,
        "promotion_target": metadata.get("promotion_target"),
        "promotion_state": metadata.get("promotion_state"),
        "alert_eligible": metadata.get("alert_eligible"),
        "phase_4_promotion_evidence_persisted": metadata.get("phase_4_promotion_evidence_persisted", False),
        "phase_4_promotion_gates_passed": metadata.get("phase_4_promotion_gates_passed", False),
        "promotion_truth_and_leakage_checks_passed": evaluation_metrics.get(
            "promotion_truth_and_leakage_checks_passed",
            False,
        ),
        "climate_coverage_summary": evaluation_metrics.get("climate_coverage_summary")
        or metadata.get("climate_coverage_summary")
        or {},
        "temporal_backtest_schema_version": evaluation_metrics.get("phase_4_temporal_backtest_schema_version"),
        "promotion_evaluation_metrics": {
            "out_of_time_score": evaluation_metrics.get("out_of_time_score"),
            "lead_time_recall": evaluation_metrics.get("lead_time_recall"),
            "precision": evaluation_metrics.get("precision"),
            "balanced_accuracy": evaluation_metrics.get("balanced_accuracy"),
            "f1_score": evaluation_metrics.get("f1_score"),
            "false_alert_rate": evaluation_metrics.get("false_alert_rate"),
            "false_alerts_per_true_hit": evaluation_metrics.get("false_alerts_per_true_hit"),
            "area_under_precision_recall_curve": evaluation_metrics.get(
                "area_under_precision_recall_curve"
            ),
        },
        "feature_lineage": feature_lineage,
    }


def _append_lineage_values(target: set[str], value) -> None:
    if isinstance(value, str):
        if value:
            target.add(value)
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            _append_lineage_values(target, item)


def _collect_feature_lineage_refs(payload) -> tuple[list[str], list[str]]:
    source_refs: set[str] = set()
    source_record_refs: set[str] = set()

    def walk(value) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"source_ref", "source_refs"}:
                    _append_lineage_values(source_refs, item)
                    continue
                if key in {"source_record_ref", "source_record_refs", "record_refs"}:
                    _append_lineage_values(source_record_refs, item)
                    continue
                walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)

    walk(payload)
    return sorted(source_refs), sorted(source_record_refs)


def _feature_lineage_for_riskscore(risk_score: RiskScore) -> dict:
    model_run = risk_score.model_run
    dataset = model_run.inference_feature_dataset if model_run else None
    if dataset is None:
        return {
            "inference_feature_dataset_id": None,
            "inference_feature_dataset_ref": getattr(model_run, "inference_dataset_ref", None),
            "lineage_available": False,
            "ward_feature_row_count": 0,
            "feature_row_refs": [],
            "source_refs": [],
            "source_record_refs": [],
            "prediction_dates": [],
            "source_cutoff_timestamps": [],
            "climate_coverage_rows": [],
            "climate_coverage_caveats": [],
            "climate_source_labels": [],
        }

    ward_rows = FeatureDatasetRow.objects.filter(dataset=dataset, ward=risk_score.ward).order_by("-id")
    row_count = ward_rows.count()
    rows = list(ward_rows[:5])
    source_refs: set[str] = set()
    source_record_refs: set[str] = set()
    prediction_dates: list[str] = []
    source_cutoff_timestamps: list[str] = []
    climate_coverage_rows: list[dict] = []
    for row in rows:
        values = row.feature_values or {}
        row_source_refs, row_source_record_refs = _collect_feature_lineage_refs(values)
        source_refs.update(row_source_refs)
        source_record_refs.update(row_source_record_refs)
        climate_coverage_rows.append(climate_coverage_from_prediction(values))
        if values.get("prediction_date"):
            prediction_dates.append(values["prediction_date"])
        if values.get("source_cutoff_timestamp"):
            source_cutoff_timestamps.append(values["source_cutoff_timestamp"])
    climate_caveats = [
        caveat
        for climate_coverage in climate_coverage_rows
        for caveat in climate_coverage.get("climate_coverage_caveats", [])
    ]
    climate_source_labels = [
        climate_coverage.get("observed_vs_forecast_source_label")
        for climate_coverage in climate_coverage_rows
        if climate_coverage.get("observed_vs_forecast_source_label")
    ]

    return {
        "inference_feature_dataset_id": dataset.id,
        "inference_feature_dataset_ref": dataset.dataset_ref,
        "lineage_available": bool(rows),
        "ward_feature_row_count": row_count,
        "feature_row_refs": [f"feature_dataset_row:{row.id}" for row in rows],
        "source_refs": sorted(source_refs),
        "source_record_refs": sorted(source_record_refs),
        "prediction_dates": list(dict.fromkeys(prediction_dates)),
        "source_cutoff_timestamps": list(dict.fromkeys(source_cutoff_timestamps)),
        "climate_coverage_rows": climate_coverage_rows,
        "climate_coverage_caveats": list(dict.fromkeys(climate_caveats)),
        "climate_source_labels": list(dict.fromkeys(climate_source_labels)),
    }


def deliver_alert(alert: Alert) -> Alert:
    if alert.channel == Alert.CHANNEL_DASHBOARD:
        sync_alert_workflow_for_ward(alert.ward)
        return alert

    if alert.channel != Alert.CHANNEL_SMS:
        alert.status = Alert.STATUS_FAILED
        alert.error_message = f"Unsupported alert channel: {alert.channel}"
        alert.next_retry_at = None
        alert.save(update_fields=["status", "error_message", "next_retry_at"])
        sync_alert_workflow_for_ward(alert.ward)
        return alert

    pause_state = get_alert_delivery_pause_state()
    if pause_state["is_active"]:
        alert.status = Alert.STATUS_RETRY_PENDING
        alert.error_message = "Alert delivery paused by system control."
        alert.next_retry_at = pause_state["paused_until"] or timezone.now() + alert_retry_delay()
        alert.save(update_fields=["status", "error_message", "next_retry_at"])
        sync_alert_workflow_for_ward(alert.ward)
        return alert

    attempted_at = timezone.now()
    alert.attempt_count += 1
    alert.last_attempted_at = attempted_at

    provider_name = alert.delivery_backend or None
    result = send_sms(alert.recipient, alert.message, provider_name=provider_name)
    alert.external_id = result.external_id
    alert.error_message = result.error
    alert.delivery_backend = result.provider

    if result.success:
        alert.status = Alert.STATUS_DELIVERED
        alert.sent_at = attempted_at
        alert.next_retry_at = None
    elif alert.attempt_count < alert.max_attempts:
        alert.status = Alert.STATUS_RETRY_PENDING
        alert.next_retry_at = attempted_at + alert_retry_delay()
        alert.sent_at = None
    else:
        alert.status = Alert.STATUS_FAILED
        alert.next_retry_at = None
        alert.sent_at = None

    alert.save(
        update_fields=[
            "attempt_count",
            "last_attempted_at",
            "delivery_backend",
            "external_id",
            "error_message",
            "status",
            "next_retry_at",
            "sent_at",
        ]
    )
    sync_alert_workflow_for_ward(alert.ward)
    return alert


def trigger_alerts_for_riskscore(
    risk_score: RiskScore,
    send_sms_enabled: bool = False,
    *,
    trigger_type: str | None = None,
    message_override: str | None = None,
    guided_request_metadata: dict | None = None,
    template_key: str = "",
    template_version: int | None = None,
    template_language: str | None = None,
    template_context: dict | None = None,
) -> list[Alert]:
    require_production_alert_eligibility(risk_score)
    return create_alerts_for_riskscore(
        risk_score,
        send_sms_enabled=send_sms_enabled,
        trigger_type=trigger_type,
        message_override=message_override,
        guided_request_metadata=guided_request_metadata,
        template_key=template_key,
        template_version=template_version,
        template_language=template_language,
        template_context=template_context,
    )


def latest_riskscore_for_ward(ward: Ward) -> RiskScore | None:
    return latest_promoted_riskscore_for_ward(ward)


def _classify_alert_record(alert: Alert) -> dict:
    haystack = f"{alert.message} {alert.recipient} {alert.ward.name}".lower()

    if "cholera" in haystack:
        return {
            "label": "Cholera Risk",
            "tone": "red",
            "icon_key": "droplets",
            "trigger_source": "Cholera threshold exceeded",
        }
    if "flood" in haystack:
        return {
            "label": "Flood Risk",
            "tone": "blue",
            "icon_key": "waves",
            "trigger_source": "Flood proxy exceeded",
        }
    if "water" in haystack:
        return {
            "label": "Water Contamination",
            "tone": "red",
            "icon_key": "circle-alert",
            "trigger_source": "Water safety signal elevated",
        }
    if "rain" in haystack:
        return {
            "label": "Heavy Rainfall",
            "tone": "orange",
            "icon_key": "cloud-rain",
            "trigger_source": "Rainfall threshold exceeded",
        }

    return {
        "label": "Operational Alert",
        "tone": "slate",
        "icon_key": "shield-alert",
        "trigger_source": "Recorded risk threshold crossed",
    }


def _alert_status_label(status_value: str) -> str:
    if status_value == Alert.STATUS_DELIVERED:
        return "Alert Delivered Successfully"
    if status_value == Alert.STATUS_FAILED:
        return "Delivery Failed"
    if status_value == Alert.STATUS_RETRY_PENDING:
        return "Delivery Retry Pending"
    return "Queued for Dispatch"


def _alert_status_tone(status_value: str) -> str:
    if status_value == Alert.STATUS_DELIVERED:
        return "success"
    if status_value == Alert.STATUS_FAILED:
        return "danger"
    if status_value == Alert.STATUS_RETRY_PENDING:
        return "warning"
    return "default"


def _alert_channel_label(channel: str) -> str:
    if channel == Alert.CHANNEL_SMS:
        return "SMS"
    if channel == Alert.CHANNEL_WHATSAPP:
        return "WhatsApp"
    return "Dashboard"


def _alert_channel_audience(channel: str) -> str:
    if channel == Alert.CHANNEL_SMS:
        return "CHVs & officials"
    if channel == Alert.CHANNEL_WHATSAPP:
        return "Field recipients"
    return "Dashboard viewers"


def build_alert_intelligence_snapshot(
    alert: Alert,
    *,
    ward_detail: Ward | None = None,
    stale_threshold_minutes: int = 30,
    user=None,
    as_of=None,
) -> dict:
    request_metadata = alert.guided_request_metadata or {}
    if not request_metadata:
        latest_manual_request_event = (
            AlertWorkflowEvent.objects.filter(
                workflow__ward=alert.ward,
                action=AlertWorkflowEvent.ACTION_MANUAL_REQUEST_QUEUED,
                created_at__lte=alert.created_at,
            )
            .order_by("-created_at")
            .first()
        )
        request_metadata = latest_manual_request_event.metadata if latest_manual_request_event else {}

    classification_core = _classify_alert_record(alert)
    classification = {
        **classification_core,
        "mode": "derived_from_record_text",
    }

    risk_score_value = alert.risk_score.score if alert.risk_score else None
    decision_policy = request_metadata.get("decision_policy") or (
        alert.risk_score.decision_policy if alert.risk_score else {}
    )
    policy_version = decision_policy.get("policy_version")
    alert_decision = decision_policy.get("alert_decision")
    reason_codes = decision_policy.get("reason_codes", [])
    risk_thresholds = (decision_policy.get("thresholds") or {}).get("risk_level") or {}
    high_threshold = risk_thresholds.get("high_min_probability", 0.75)
    medium_threshold = risk_thresholds.get("medium_min_probability", 0.45)

    if alert_decision == DECISION_URGENT_ALERT:
        risk_context = {
            "level_label": "High Risk",
            "trend_label": "Urgent",
            "summary": "The recorded score crossed the urgent alert policy. Review linked ward and delivery records closely.",
            "recorded_risk_score": risk_score_value,
            "threshold": high_threshold,
            "policy_version": policy_version,
            "alert_decision": alert_decision,
            "reason_codes": reason_codes,
            "mode": "derived_from_decision_policy",
        }
    elif alert_decision == DECISION_ALERT_CANDIDATE or (
        risk_score_value is not None and risk_score_value >= high_threshold
    ):
        risk_context = {
            "level_label": "High Risk",
            "trend_label": "Escalating",
            "summary": "The recorded score is an alert candidate under the active decision policy.",
            "recorded_risk_score": risk_score_value,
            "threshold": high_threshold,
            "policy_version": policy_version,
            "alert_decision": alert_decision,
            "reason_codes": reason_codes,
            "mode": "derived_from_decision_policy" if decision_policy else "derived_from_risk_score",
        }
    elif alert_decision == DECISION_WATCHLIST_ONLY or (
        risk_score_value is not None and risk_score_value >= medium_threshold
    ):
        risk_context = {
            "level_label": "Medium Risk",
            "trend_label": "Monitoring",
            "summary": "Watch closely and prepare ward follow-up if indicators rise again.",
            "recorded_risk_score": risk_score_value,
            "threshold": medium_threshold,
            "policy_version": policy_version,
            "alert_decision": alert_decision,
            "reason_codes": reason_codes,
            "mode": "derived_from_decision_policy" if decision_policy else "derived_from_risk_score",
        }
    else:
        risk_context = {
            "level_label": "Low Risk" if risk_score_value is not None else "Risk Score Unavailable",
            "trend_label": "Stable" if risk_score_value is not None else "Unknown",
            "summary": (
                "Threshold not crossed. Maintain routine monitoring and review later records if conditions change."
                if risk_score_value is not None
                else "No linked risk score is available for interpretation on this alert record."
            ),
            "recorded_risk_score": risk_score_value,
            "threshold": medium_threshold if risk_score_value is not None else None,
            "policy_version": policy_version,
            "alert_decision": alert_decision or DECISION_ROUTINE_MONITORING,
            "reason_codes": reason_codes,
            "mode": "derived_from_decision_policy" if decision_policy else "derived_from_risk_score"
            if risk_score_value is not None
            else "unavailable",
        }

    delivery = {
        "channel_label": _alert_channel_label(alert.channel),
        "audience_label": _alert_channel_audience(alert.channel),
        "status_label": _alert_status_label(alert.status),
        "status_tone": _alert_status_tone(alert.status),
        "recipient_count": 1,
        "attempt_count": alert.attempt_count,
        "max_attempts": alert.max_attempts,
        "delivery_backend": alert.delivery_backend or "",
        "last_attempted_at": alert.last_attempted_at,
        "next_retry_at": alert.next_retry_at,
        "sent_at": alert.sent_at,
        "mode": "backend_record_fields",
    }

    message_mode = request_metadata.get("message_mode")
    selected_trigger_type = request_metadata.get("selected_trigger_type") or ""
    preview_text = request_metadata.get("message_preview_used") or ""
    if message_mode == MESSAGE_MODE_OPERATOR_EDITED:
        message_source = {
            "mode": MESSAGE_MODE_OPERATOR_EDITED,
            "label": "Edited by operator",
            "summary": "An operator adjusted the guided message before the alert request was queued.",
            "trigger_type": selected_trigger_type,
            "preview_text": _text_value_for_service_user(preview_text or alert.message, user),
        }
    elif message_mode == MESSAGE_MODE_BACKEND_GENERATED:
        message_source = {
            "mode": MESSAGE_MODE_BACKEND_GENERATED,
            "label": "System-generated draft",
            "summary": "The queued alert used the system-generated guided message without operator edits.",
            "trigger_type": selected_trigger_type,
            "preview_text": _text_value_for_service_user(preview_text or alert.message, user),
        }
    elif message_mode == MESSAGE_MODE_TEMPLATE_RENDERED:
        template_metadata = request_metadata.get("message_template") or {}
        template_key = template_metadata.get("template_key") or alert.template_key or ""
        template_version = template_metadata.get("template_version") or alert.template_version
        message_source = {
            "mode": MESSAGE_MODE_TEMPLATE_RENDERED,
            "label": "Approved template",
            "summary": (
                f"The queued alert used template {template_key} v{template_version}."
                if template_key and template_version
                else "The queued alert used a governed message template."
            ),
            "trigger_type": selected_trigger_type,
            "preview_text": _text_value_for_service_user(preview_text or alert.message, user),
        }
    else:
        message_source = {
            "mode": "unavailable",
            "label": "Message source unavailable",
            "summary": "This alert record does not yet carry guided-flow message-source metadata.",
            "trigger_type": "",
            "preview_text": "",
        }
    surveillance_evidence = request_metadata.get("surveillance_evidence") or _surveillance_alert_evidence_for_ward(
        alert.ward,
        as_of=as_of,
    )
    climate_evidence = request_metadata.get("climate_evidence") or (
        _climate_alert_evidence_for_riskscore(alert.risk_score) if alert.risk_score_id else {}
    )

    chv_total = CHV.objects.filter(ward=alert.ward, is_active=True).count()
    facility_total = HealthFacility.objects.filter(ward=alert.ward, is_active=True).count()
    triage_sessions_24h = TriageSession.objects.filter(
        ward=alert.ward,
        created_at__gte=timezone.now() - timedelta(hours=24),
    )
    sync_payloads_24h = SyncQueue.objects.filter(
        ward=alert.ward,
        created_at__gte=timezone.now() - timedelta(hours=24),
    )
    triage_count = triage_sessions_24h.count()
    sync_count = sync_payloads_24h.count()
    latest_field_timestamp = max(
        (
            value
            for value in [
                triage_sessions_24h.order_by("-created_at").values_list("created_at", flat=True).first(),
                sync_payloads_24h.order_by("-created_at").values_list("created_at", flat=True).first(),
            ]
            if value is not None
        ),
        default=None,
    )
    ward_risk_level = ward_detail.current_risk_level if ward_detail else alert.ward.current_risk_level

    if alert.status == Alert.STATUS_FAILED:
        lifecycle = {
            "status": "escalated",
            "status_label": "Escalated",
            "summary": "Delivery failed, so this alert now needs operator escalation and an alternate follow-up path.",
            "last_updated_at": alert.last_attempted_at or alert.created_at,
            "mode": "derived_from_alert_delivery_and_ward_context",
        }
    elif alert.status == Alert.STATUS_RETRY_PENDING:
        lifecycle = {
            "status": "monitoring",
            "status_label": "Monitoring",
            "summary": "Delivery is still in progress and should remain under watch until retry completes.",
            "last_updated_at": alert.next_retry_at or alert.last_attempted_at or alert.created_at,
            "mode": "derived_from_alert_delivery_and_ward_context",
        }
    elif alert.status == Alert.STATUS_DELIVERED and ward_risk_level == Ward.RISK_LOW:
        lifecycle = {
            "status": "resolved",
            "status_label": "Resolved",
            "summary": "The alert was delivered and the linked ward is no longer elevated in the current risk surface.",
            "last_updated_at": alert.sent_at or alert.created_at,
            "mode": "derived_from_alert_delivery_and_ward_context",
        }
    else:
        lifecycle = {
            "status": "active",
            "status_label": "Active",
            "summary": "The alert remains part of an active operational watch loop.",
            "last_updated_at": alert.sent_at or alert.last_attempted_at or alert.created_at,
            "mode": "derived_from_alert_delivery_and_ward_context",
        }

    if triage_count > 0 or sync_count > 0:
        chv_response_summary = {
            "status_label": "Field responses visible",
            "coverage_label": f"{triage_count + sync_count} recent response signals",
            "summary": "Recent CHV triage or sync activity is visible after alert creation.",
            "response_count": triage_count + sync_count,
            "mode": "derived_from_chv_and_field_activity",
        }
    elif chv_total > 0:
        chv_response_summary = {
            "status_label": "CHVs assigned, no recent field feedback",
            "coverage_label": f"{chv_total} CHVs assigned",
            "summary": "CHVs are assigned to this ward, but no recent response feedback is visible in the current backend record set.",
            "response_count": 0,
            "mode": "derived_from_chv_and_field_activity",
        }
    else:
        chv_response_summary = {
            "status_label": "No CHV coverage recorded",
            "coverage_label": "0 CHVs assigned",
            "summary": "No active CHV coverage is recorded for this ward, so field response cannot be confirmed from CHV data.",
            "response_count": 0,
            "mode": "derived_from_chv_and_field_activity",
        }

    if facility_total == 0:
        facility_response_summary = {
            "status_label": "No linked facilities recorded",
            "coverage_label": "0 facilities in ward",
            "summary": "No active facility records are linked to this ward in the current backend scope.",
            "response_count": 0,
            "mode": "derived_from_facility_presence_and_ward_risk",
        }
    elif ward_risk_level == Ward.RISK_HIGH:
        facility_response_summary = {
            "status_label": "Facility pressure likely",
            "coverage_label": f"{facility_total} facilities linked",
            "summary": "High ward risk means linked facilities should be treated as likely under pressure until facility-readiness detail confirms otherwise.",
            "response_count": facility_total,
            "mode": "derived_from_facility_presence_and_ward_risk",
        }
    elif ward_risk_level == Ward.RISK_MEDIUM:
        facility_response_summary = {
            "status_label": "Facility watch",
            "coverage_label": f"{facility_total} facilities linked",
            "summary": "Linked facilities should remain under watch while this alert is active.",
            "response_count": facility_total,
            "mode": "derived_from_facility_presence_and_ward_risk",
        }
    else:
        facility_response_summary = {
            "status_label": "Facility pressure not elevated",
            "coverage_label": f"{facility_total} facilities linked",
            "summary": "Linked facilities are recorded, but no elevated facility pressure signal is implied by the current ward context.",
            "response_count": facility_total,
            "mode": "derived_from_facility_presence_and_ward_risk",
        }

    if alert.status == Alert.STATUS_FAILED:
        recommended_next_action = {
            "label": "Escalate to facility",
            "detail": "Delivery failed and the safest next move is a coordinated escalation through facility and supervisor channels.",
            "blocked": True,
            "blocked_reason": "This page cannot start a facility escalation yet. Continue coordination through the ward and alerts workflow.",
            "mode": "not_available_from_alert_detail",
        }
    elif alert.status == Alert.STATUS_RETRY_PENDING:
        recommended_next_action = {
            "label": "Send follow-up SMS",
            "detail": "Retry is pending, so a follow-up communication path may be needed if delivery remains blocked.",
            "blocked": True,
            "blocked_reason": "This page cannot send a follow-up message yet. Keep tracking delivery and use the alerts workflow if escalation is needed.",
            "mode": "not_available_from_alert_detail",
        }
    elif ward_risk_level == Ward.RISK_HIGH:
        recommended_next_action = {
            "label": "Dispatch additional CHVs",
            "detail": "The alert is live in a high-risk ward, so extra CHV coverage would be the most likely next operational step.",
            "blocked": True,
            "blocked_reason": "This page cannot dispatch additional CHVs yet. Use ward coordination and field supervision to act on this alert.",
            "mode": "not_available_from_alert_detail",
        }
    else:
        recommended_next_action = {
            "label": "Close alert",
            "detail": "The linked ward context is no longer strongly elevated, but this page cannot complete the closure step yet.",
            "blocked": True,
            "blocked_reason": "This page cannot close the alert yet. Keep the record under review until closure is available through the workflow.",
            "mode": "not_available_from_alert_detail",
        }

    current_state = [
        {
            "label": (
                "Alert delivered"
                if alert.status == Alert.STATUS_DELIVERED
                else "Delivery blocked"
                if alert.status == Alert.STATUS_FAILED
                else "Delivery still in progress"
            ),
            "tone": "warning" if alert.status == Alert.STATUS_FAILED else "success",
        },
        {
            "label": (
                "This alert record failed delivery"
                if alert.status == Alert.STATUS_FAILED
                else "A retry is still pending"
                if alert.status == Alert.STATUS_RETRY_PENDING
                else "No active delivery failure recorded"
            ),
            "tone": "warning" if alert.status in {Alert.STATUS_FAILED, Alert.STATUS_RETRY_PENDING} else "success",
        },
        {
            "label": (
                "High ward risk accompanies this alert"
                if risk_score_value is not None and risk_score_value >= 75
                else "No high ward-risk threshold recorded"
            ),
            "tone": "warning" if risk_score_value is not None and risk_score_value >= 75 else "neutral",
        },
        {
            "label": (
                f"Surveillance truth: {surveillance_evidence.get('label_truth_state')}"
                if surveillance_evidence.get("latest_label_window_ref")
                else "No surveillance label window linked"
            ),
            "tone": (
                "success"
                if surveillance_evidence.get("label_truth_state") == "confirmed_surveillance_truth"
                else "warning"
                if surveillance_evidence.get("latest_label_window_ref")
                else "neutral"
            ),
        },
        {
            "label": (
                f"Climate source: {climate_evidence.get('observed_vs_forecast_source_label')}"
                if climate_evidence.get("observed_vs_forecast_source_label")
                else "Climate source unavailable"
            ),
            "tone": (
                "success"
                if climate_evidence.get("claimed_lead_time_climate_coverage_sufficient")
                else "warning"
                if climate_evidence
                else "neutral"
            ),
        },
    ]

    timeline = [
        {
            "id": "triggered",
            "title": "Alert triggered",
            "description": f"Alert record generated from the risk model using {classification_core['trigger_source'].lower()} signals.",
            "timestamp": alert.created_at,
            "tone": "primary",
            "category": "system",
            "actor": "System",
            "event_type": "triggered",
            "message": "Alert created from model or recorded warning signal.",
            "meta": f"Risk score: {round(risk_score_value)}/100" if risk_score_value is not None else None,
            "details": [f"Trigger source: {classification_core['trigger_source']}"],
        },
        {
            "id": "created",
            "title": "Alert record created",
            "description": f"A {_alert_channel_label(alert.channel).lower()} alert record was created for {alert.ward.name}.",
            "timestamp": alert.created_at,
            "tone": "neutral",
            "category": "system",
            "actor": "Backend",
            "event_type": "notified",
            "message": "Alert record persisted for operational review.",
            "meta": None,
            "details": [
                f"Recipient: {_contact_value_for_service_user(alert.recipient, user)}",
                f"Channel: {_alert_channel_label(alert.channel)}",
            ],
        },
        {
            "id": "dispatch",
            "title": "Delivery attempt state",
            "description": f"Latest delivery activity is tracked through {alert.delivery_backend or 'the recorded backend'}.",
            "timestamp": alert.last_attempted_at or alert.sent_at or alert.created_at,
            "tone": (
                "danger"
                if alert.status == Alert.STATUS_FAILED
                else "success"
                if alert.status == Alert.STATUS_DELIVERED
                else "progress"
            ),
            "category": "communication",
            "actor": "Delivery backend",
            "event_type": "delivery_attempt",
            "message": "Recorded delivery processing state updated.",
            "meta": None,
            "details": [
                f"Attempt count: {alert.attempt_count}/{alert.max_attempts}",
                f"Backend: {alert.delivery_backend or 'Unspecified'}",
            ],
        },
        {
            "id": "delivery-status",
            "title": "Recorded delivery outcome",
            "description": (
                "This alert record is marked as delivered."
                if alert.status == Alert.STATUS_DELIVERED
                else "This alert record is marked as failed and needs operator review."
                if alert.status == Alert.STATUS_FAILED
                else "This alert record is waiting for another delivery attempt."
                if alert.status == Alert.STATUS_RETRY_PENDING
                else "This alert record is queued and awaiting delivery processing."
            ),
            "timestamp": alert.sent_at or alert.last_attempted_at,
            "tone": (
                "success"
                if alert.status == Alert.STATUS_DELIVERED
                else "danger"
                if alert.status == Alert.STATUS_FAILED
                else "warning"
            ),
            "category": "communication",
            "actor": "Delivery backend",
            "event_type": "delivery_outcome",
            "message": "Current delivery outcome recorded on the alert.",
            "meta": None,
            "details": [
                f"Status: {_alert_status_label(alert.status)}",
                f"Last attempted at: {alert.last_attempted_at.isoformat() if alert.last_attempted_at else 'No timestamp'}",
                f"Sent at: {alert.sent_at.isoformat() if alert.sent_at else 'No timestamp'}",
            ],
        },
    ]
    if surveillance_evidence.get("latest_label_window_ref"):
        timeline.append(
            {
                "id": "surveillance-label-window",
                "title": "Surveillance label context",
                "description": "The alert candidate is linked to canonical surveillance label-window context.",
                "timestamp": alert.created_at,
                "tone": (
                    "success"
                    if surveillance_evidence.get("label_truth_state") == "confirmed_surveillance_truth"
                    else "warning"
                ),
                "category": "surveillance",
                "actor": "Backend",
                "event_type": "evidence_linked",
                "message": "Surveillance label and freshness truth attached to alert reasoning.",
                "meta": surveillance_evidence.get("latest_label_window_ref"),
                "details": [
                    f"Truth state: {surveillance_evidence.get('label_truth_state')}",
                    f"Freshness: {surveillance_evidence.get('latest_freshness_state') or 'unknown'}",
                    "Proxy-only labels are not confirmed outbreak truth.",
                ],
            }
        )
    if alert.next_retry_at:
        timeline.append(
            {
                "id": "retry",
                "title": "Next retry scheduled",
                "description": "The backend has recorded a future retry time for this alert record.",
                "timestamp": alert.next_retry_at,
                "tone": "warning",
                "category": "communication",
                "actor": "Delivery backend",
                "event_type": "monitoring",
                "message": "Retry remains pending.",
                "meta": None,
                "details": [f"Next retry at: {alert.next_retry_at.isoformat()}"],
            }
        )

    if triage_count > 0 or sync_count > 0:
        timeline.append(
            {
                "id": "field-response",
                "title": "Field response signals recorded",
                "description": "Recent CHV triage or sync activity is visible after alert creation.",
                "timestamp": latest_field_timestamp or alert.created_at,
                "tone": "success" if triage_count > 0 else "progress",
                "category": "field_activity",
                "actor": "Field operations",
                "event_type": "field_response",
                "message": "Field-side activity has come back into the system.",
                "meta": chv_response_summary["coverage_label"],
                "details": [
                    f"Triage sessions in last 24h: {triage_count}",
                    f"Sync payloads in last 24h: {sync_count}",
                ],
            }
        )

    if alert.status == Alert.STATUS_FAILED:
        timeline.append(
            {
                "id": "escalation-needed",
                "title": "Escalation required",
                "description": "Delivery failed and this alert now requires operator escalation.",
                "timestamp": alert.last_attempted_at or alert.created_at,
                "tone": "danger",
                "category": "escalation",
                "actor": "System",
                "event_type": "escalated",
                "message": "Alert should be escalated through another operational path.",
                "meta": None,
                "details": [recommended_next_action["blocked_reason"]],
            }
        )

    if alert.status == Alert.STATUS_DELIVERED and ward_risk_level == Ward.RISK_LOW:
        timeline.append(
            {
                "id": "resolved",
                "title": "Alert stabilization visible",
                "description": "Delivery is complete and the linked ward is no longer elevated in the current risk surface.",
                "timestamp": alert.sent_at or alert.created_at,
                "tone": "success",
                "category": "resolution",
                "actor": "System",
                "event_type": "resolved",
                "message": "Current records suggest the alert can move toward closure.",
                "meta": None,
                "details": [f"Linked ward risk level: {ward_risk_level}"],
            }
        )

    updated_candidates = [
        alert.sent_at,
        alert.last_attempted_at,
        alert.next_retry_at,
        alert.created_at,
        ward_detail.updated_at if ward_detail else None,
    ]
    updated_at = max((value for value in updated_candidates if value is not None), default=None)
    is_stale = True
    if updated_at is not None:
        is_stale = (timezone.now() - updated_at).total_seconds() / 60 > stale_threshold_minutes

    freshness = {
        "updated_at": updated_at,
        "is_stale": is_stale,
        "stale_threshold_minutes": stale_threshold_minutes,
        "mode": "timestamp_and_record_availability",
    }

    capabilities = {
        "can_resend": False,
        "can_recall": False,
        "can_notify_facilities": False,
        "can_send_follow_up": False,
        "can_dispatch_additional_chvs": False,
        "can_close_alert": False,
        "mode": "read_only_detail_with_trigger_flow_elsewhere",
    }

    return {
        "alert": alert,
        "ward_detail": ward_detail,
        "classification": classification,
        "risk_context": risk_context,
        "lifecycle": lifecycle,
        "delivery": delivery,
        "delivery_summary": delivery,
        "message_source": message_source,
        "surveillance_evidence": surveillance_evidence,
        "climate_evidence": climate_evidence,
        "chv_response_summary": chv_response_summary,
        "facility_response_summary": facility_response_summary,
        "recommended_next_action": recommended_next_action,
        "last_updated_at": lifecycle["last_updated_at"],
        "current_state": current_state,
        "freshness": freshness,
        "timeline": timeline,
        "capabilities": capabilities,
    }


def _evidence_badge_tone(state: str | None) -> str:
    normalized = (state or "").lower()
    if normalized in {"fresh", "high", "promoted", "evaluated", "hit", "correct_quiet", "confirmed_surveillance"}:
        return "success"
    if normalized in {"stale", "low", "proxy_backed", "seeded_demo", "false_alert", "missed_outbreak"}:
        return "warning"
    if normalized in {"failed", "blocked"}:
        return "danger"
    return "default"


def _model_readiness_evidence(latest_risk: RiskScore | None, population_exposure_context: dict) -> dict:
    if latest_risk is None or latest_risk.model_run is None:
        return {
            "state": "seeded_demo",
            "label": "Seeded demo",
            "tone": "warning",
            "detail": "No promoted model run is attached to the current ward score.",
            "evidence": ["current score has no promoted model-run lineage"],
        }

    model_run = latest_risk.model_run
    metadata = model_run.metadata or {}
    metrics = model_run.evaluation_metrics or {}
    decision_policy = latest_risk.decision_policy or {}
    policy_inputs = decision_policy.get("inputs") or {}
    source_confidence = policy_inputs.get("source_confidence") or {}
    climate_coverage = policy_inputs.get("climate_coverage") or source_confidence.get("climate_coverage") or {}
    climate_readiness_caveats = climate_coverage.get("climate_coverage_caveats") or []
    dataset_source_kinds = {
        dataset.source_kind
        for dataset in [model_run.training_feature_dataset, model_run.inference_feature_dataset]
        if dataset is not None
    }
    exposure_modes = {
        factor.get("mode")
        for factor in population_exposure_context.get("factor_items", [])
        if factor.get("mode")
    }

    evidence = [
        f"model_version={model_run.model_version}",
        f"status={model_run.status}",
    ]
    if metadata.get("promotion_target"):
        evidence.append(f"promotion_target={metadata.get('promotion_target')}")
    live_promotion_policy = metadata.get("live_promotion_policy") or {}
    live_promotion_blockers = live_promotion_policy.get("blockers") or []
    if live_promotion_blockers:
        evidence.append(f"live_promotion_blockers={','.join(live_promotion_blockers)}")
    if metrics:
        evidence.append("evaluation_metrics_present")
    if dataset_source_kinds:
        evidence.append(f"dataset_source={','.join(sorted(dataset_source_kinds))}")
    if exposure_modes:
        evidence.append(f"exposure_mode={','.join(sorted(exposure_modes))}")
    if climate_readiness_caveats:
        evidence.append(f"climate_caveats={','.join(climate_readiness_caveats)}")

    if is_promoted_model_run(model_run):
        state = "promoted"
        label = "Promoted"
        detail = "The current ward score is attached to a Phase 4-gated promoted live-baseline model run."
    elif "SEEDED" in dataset_source_kinds or metadata.get("execution_context") in {"demo", "seeded_demo", "test_fixture"}:
        state = "seeded_demo"
        label = "Seeded demo"
        detail = "The current score uses seeded or demo/test lineage and should not be treated as production-grade evidence."
    elif live_promotion_policy.get("requested_live_promotion") and live_promotion_blockers:
        state = "proxy_backed"
        label = "Promotion blocked"
        detail = "The model run is not live-promoted because promotion evidence or production training truth is incomplete."
    elif metrics and model_run.status == model_run.STATUS_SUCCESS:
        state = "evaluated"
        label = "Evaluated"
        detail = "The model run has stored evaluation metrics but is not Phase 4 promoted."
    else:
        state = "proxy_backed"
        label = "Proxy-backed"
        detail = "The current score depends on proxy or incomplete lineage and needs cautious interpretation."

    if state not in {"seeded_demo", "promoted"} and any("proxy" in str(mode) for mode in exposure_modes):
        state = "proxy_backed"
        label = "Proxy-backed"
        detail = "Population or exposure inputs include proxy-derived context."
    if climate_coverage and climate_coverage.get("claimed_lead_time_climate_coverage_sufficient") is not True:
        detail = f"{detail} Climate forecast coverage has caveats for the claimed horizon."

    return {
        "state": state,
        "label": label,
        "tone": _evidence_badge_tone(state),
        "detail": detail,
        "evidence": evidence,
        "readiness_caveats": climate_readiness_caveats,
    }


def _forecast_horizon_evidence(latest_risk: RiskScore | None, *, climate_evidence: dict | None = None) -> dict:
    validation = {}
    if latest_risk and latest_risk.model_run:
        metrics = latest_risk.model_run.evaluation_metrics or {}
        metadata = latest_risk.model_run.metadata or {}
        validation = metrics.get("surveillance_lead_time_validation") or metadata.get("surveillance_lead_time_validation") or {}

    horizons = validation.get("horizons") if isinstance(validation, dict) else {}
    horizon_7 = horizons.get("7") if isinstance(horizons, dict) else None
    horizon_14 = horizons.get("14") if isinstance(horizons, dict) else None
    supported = []
    for horizon, payload in [(7, horizon_7), (14, horizon_14)]:
        if isinstance(payload, dict) and payload.get("matching_label_window_count", 0):
            supported.append(horizon)

    return {
        "label": "7 to 14 day forecast horizon",
        "min_days": 7,
        "max_days": 14,
        "display_value": "7 to 14 days",
        "expected_cases_label": "Expected cases in the next 7 days",
        "lead_time_supported_days": supported,
        "validation_status": validation.get("status") if isinstance(validation, dict) else None,
        "mode": "lead_time_validation" if validation else "default_policy_window",
        "source_label": (climate_evidence or {}).get("observed_vs_forecast_source_label") or "",
        "claimed_forecast_horizon_days": (climate_evidence or {}).get("claimed_forecast_horizon_days"),
        "forecast_coverage_days": (climate_evidence or {}).get("forecast_coverage_days"),
        "forecast_missing_lead_days": (climate_evidence or {}).get("forecast_missing_lead_days") or [],
        "climate_coverage_status": (climate_evidence or {}).get("climate_coverage_status") or "",
        "claimed_lead_time_climate_coverage_sufficient": (climate_evidence or {}).get(
            "claimed_lead_time_climate_coverage_sufficient"
        ),
        "issue_time": (climate_evidence or {}).get("issue_time"),
        "valid_date": (climate_evidence or {}).get("valid_date"),
        "lead_day": (climate_evidence or {}).get("lead_day"),
        "fallback_static_rainfall_used": (climate_evidence or {}).get("fallback_static_rainfall_used", False),
    }


def _source_evidence_badges(
    *,
    current_risk: dict,
    freshness: dict,
    surveillance_context: dict,
    population_exposure_context: dict,
) -> list[dict]:
    decision_policy = current_risk.get("decision_policy") or {}
    policy_inputs = decision_policy.get("inputs") or {}
    source_freshness = policy_inputs.get("source_freshness") or {}
    source_confidence = policy_inputs.get("source_confidence") or {}
    climate_coverage = policy_inputs.get("climate_coverage") or source_confidence.get("climate_coverage") or {}

    freshness_state = source_freshness.get("combined_state") or ("STALE" if freshness.get("is_stale") else "FRESH")
    confidence_state = source_confidence.get("confidence")
    if not confidence_state:
        if surveillance_context.get("surveillance_label_truth_state") == "confirmed_surveillance_truth":
            confidence_state = "high"
        elif population_exposure_context.get("coverage", {}).get("record_count"):
            confidence_state = "moderate"
        else:
            confidence_state = "low"

    source_kind = source_confidence.get("source_kind") or current_risk.get("source") or "unknown"
    surveillance_truth = surveillance_context.get("surveillance_label_truth_state") or "no_surveillance_label_window"

    badges = [
        {
            "id": "source_freshness",
            "label": "Source freshness",
            "value": str(freshness_state).replace("_", " ").title(),
            "tone": _evidence_badge_tone(str(freshness_state)),
            "detail": source_freshness.get("detail")
            or ("Current ward data is inside the freshness window." if not freshness.get("is_stale") else "Current ward data is stale."),
        },
        {
            "id": "source_confidence",
            "label": "Source confidence",
            "value": str(confidence_state).replace("_", " ").title(),
            "tone": _evidence_badge_tone(str(confidence_state)),
            "detail": source_confidence.get("detail") or f"Confidence inferred from {source_kind} and visible surveillance/exposure context.",
        },
    ]
    if climate_coverage:
        missing_days = climate_coverage.get("forecast_missing_lead_days") or []
        climate_caveats = climate_coverage.get("climate_coverage_caveats") or []
        climate_label = climate_coverage.get("observed_vs_forecast_source_label") or "Climate source unavailable"
        climate_coverage_sufficient = climate_coverage.get("claimed_lead_time_climate_coverage_sufficient")
        if climate_coverage_sufficient:
            climate_detail = f"{climate_label}; claimed forecast horizon coverage is sufficient."
        elif missing_days:
            climate_detail = f"{climate_label}; missing lead days: {', '.join(str(day) for day in missing_days)}."
        elif climate_caveats:
            climate_detail = f"{climate_label}; caveats: {', '.join(climate_caveats)}."
        else:
            climate_detail = f"{climate_label}; claimed forecast horizon coverage is not confirmed."
        badges.append(
            {
                "id": "climate_coverage",
                "label": "Climate coverage",
                "value": str(climate_coverage.get("climate_coverage_status") or "unavailable").replace("_", " ").title(),
                "tone": (
                    "success"
                    if climate_coverage_sufficient
                    else "warning"
                ),
                "detail": climate_detail,
            }
        )
    badges.append(
        {
            "id": "surveillance_truth",
            "label": "Surveillance truth",
            "value": surveillance_truth.replace("_", " ").title(),
            "tone": "success" if surveillance_truth == "confirmed_surveillance_truth" else "warning",
            "detail": surveillance_context.get("surveillance_display_caveat") or "No confirmed surveillance label window is linked yet.",
        }
    )
    return badges


def _label_for_prediction(risk_score: RiskScore, label_windows: list[SurveillanceLabelWindow]) -> SurveillanceLabelWindow | None:
    prediction_date = risk_score.generated_at.date()
    horizon_start = prediction_date + timedelta(days=7)
    horizon_end = prediction_date + timedelta(days=14)
    for label_window in label_windows:
        if label_window.label_window_start <= horizon_end and label_window.label_window_end >= horizon_start:
            return label_window
    return None


def _prediction_outcome_classification(risk_score: RiskScore, label_window: SurveillanceLabelWindow | None) -> str:
    decision_policy = risk_score.decision_policy or {}
    alert_decision = decision_policy.get("alert_decision")
    predicted_positive = risk_score.risk_level == Ward.RISK_HIGH or alert_decision in {
        DECISION_URGENT_ALERT,
        DECISION_ALERT_CANDIDATE,
    }
    if label_window is None:
        return "pending_label"

    observed_active = label_window.outbreak_label == SurveillanceOutbreakLabel.ACTIVE
    if predicted_positive and observed_active:
        return "hit"
    if predicted_positive and not observed_active:
        return "false_alert"
    if not predicted_positive and observed_active:
        return "missed_outbreak"
    return "correct_quiet"


def _prediction_label_history(risk_history: list[RiskScore]) -> tuple[list[dict], dict]:
    if not risk_history:
        return [], {
            "mode": "no_prediction_history",
            "evaluated_count": 0,
            "hit_count": 0,
            "false_alert_count": 0,
            "missed_outbreak_count": 0,
            "pending_label_count": 0,
            "correct_quiet_count": 0,
        }

    ward = risk_history[0].ward
    min_prediction_date = min(risk.generated_at.date() + timedelta(days=7) for risk in risk_history)
    max_prediction_date = max(risk.generated_at.date() + timedelta(days=14) for risk in risk_history)
    label_windows = list(
        SurveillanceLabelWindow.objects.filter(
            ward=ward,
            label_window_start__lte=max_prediction_date,
            label_window_end__gte=min_prediction_date,
        ).order_by("label_window_start", "label_window_end", "id")
    )

    rows: list[dict] = []
    counts = {
        "hit": 0,
        "false_alert": 0,
        "missed_outbreak": 0,
        "pending_label": 0,
        "correct_quiet": 0,
    }
    for risk_score in risk_history:
        label_window = _label_for_prediction(risk_score, label_windows)
        classification = _prediction_outcome_classification(risk_score, label_window)
        counts[classification] += 1
        decision_policy = risk_score.decision_policy or {}
        rows.append(
            {
                "risk_score_id": risk_score.id,
                "prediction_generated_at": risk_score.generated_at,
                "forecast_window_start": risk_score.generated_at.date() + timedelta(days=7),
                "forecast_window_end": risk_score.generated_at.date() + timedelta(days=14),
                "risk_level": risk_score.risk_level,
                "risk_score": risk_score.score,
                "predicted_cases": risk_score.predicted_cases,
                "alert_decision": decision_policy.get("alert_decision") or "",
                "policy_version": decision_policy.get("policy_version") or "",
                "observed_label": label_window.outbreak_label if label_window else "PENDING",
                "observed_truth_level": label_window.label_truth_level if label_window else "",
                "observed_suspected_cases": label_window.suspected_case_count if label_window else 0,
                "observed_confirmed_cases": label_window.confirmed_case_count if label_window else 0,
                "observed_proxy_cases": label_window.proxy_case_count if label_window else 0,
                "label_window_ref": f"surveillance_label_window:{label_window.id}" if label_window else "",
                "label_dataset_ref": label_window.dataset_ref if label_window else "",
                "classification": classification,
                "review_required": classification in {"false_alert", "missed_outbreak"},
                "confidence_caveat": (
                    "Confirmed surveillance truth"
                    if label_window and label_window.label_truth_level == SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE
                    else "Proxy, suspected, demo, or pending label evidence"
                ),
            }
        )

    evaluated_count = len(rows) - counts["pending_label"]
    return rows, {
        "mode": "prediction_vs_surveillance_labels",
        "evaluated_count": evaluated_count,
        "hit_count": counts["hit"],
        "false_alert_count": counts["false_alert"],
        "missed_outbreak_count": counts["missed_outbreak"],
        "pending_label_count": counts["pending_label"],
        "correct_quiet_count": counts["correct_quiet"],
        "precision_review_note": (
            "Only rows with surveillance label windows are counted as evaluated; pending rows remain visible but are not scored."
        ),
    }


def _alert_candidate_review_evidence(current_risk: dict, workflow: AlertWorkflowState, related_alerts: list[Alert]) -> dict:
    decision_policy = current_risk.get("decision_policy") or {}
    alert_decision = decision_policy.get("alert_decision") or DECISION_ROUTINE_MONITORING
    blockers = decision_policy.get("automatic_alert_blockers") or []
    has_active_alert = bool(related_alerts) or workflow.active_alert_count > 0
    review_state = (
        "alert_active"
        if has_active_alert
        else "needs_human_review"
        if alert_decision in {DECISION_URGENT_ALERT, DECISION_ALERT_CANDIDATE, DECISION_WATCHLIST_ONLY}
        or workflow.status == AlertWorkflowState.STATUS_REVIEW_PENDING
        else "routine_monitoring"
    )
    return {
        "review_state": review_state,
        "alert_decision": alert_decision,
        "policy_version": decision_policy.get("policy_version") or "",
        "risk_level": current_risk.get("risk_level"),
        "risk_score": current_risk.get("risk_score"),
        "predicted_cases": current_risk.get("predicted_cases"),
        "automatic_alert_allowed": bool(decision_policy.get("automatic_alert_allowed", False)),
        "automatic_alert_blockers": blockers,
        "reason_codes": decision_policy.get("reason_codes") or [],
        "recommended_action": workflow.recommended_action,
        "active_alert_count": workflow.active_alert_count,
    }


def _chv_action_evidence_for_ward(ward: Ward) -> dict:
    coverage_requests = list(
        CHVCoverageRequest.objects.filter(ward=ward)
        .prefetch_related("assignments", "linked_alert_links__alert")
        .order_by("-created_at")[:4]
    )
    active_statuses = {
        CHVCoverageRequest.STATUS_OPEN,
        CHVCoverageRequest.STATUS_APPROVED,
        CHVCoverageRequest.STATUS_IN_PROGRESS,
    }
    rows = []
    for request in coverage_requests:
        assignments = list(request.assignments.all())
        linked_alerts = [link.alert for link in request.linked_alert_links.all()]
        rows.append(
            {
                "public_id": str(request.public_id),
                "status": request.status,
                "priority": request.priority,
                "trigger_source": request.trigger_source,
                "created_at": request.created_at,
                "expected_response_by": request.expected_response_by,
                "resolved_at": request.resolved_at,
                "linked_alert_public_ids": [str(alert.public_id) for alert in linked_alerts],
                "linked_alert_statuses": [
                    {
                        "public_id": str(alert.public_id),
                        "status": alert.status,
                        "channel": alert.channel,
                        "created_at": alert.created_at,
                    }
                    for alert in linked_alerts
                ],
                "assignment_counts": {
                    "active": sum(1 for assignment in assignments if assignment.status == CHVAssignment.STATUS_ACTIVE),
                    "completed": sum(1 for assignment in assignments if assignment.status == CHVAssignment.STATUS_COMPLETED),
                    "cancelled": sum(1 for assignment in assignments if assignment.status == CHVAssignment.STATUS_CANCELLED),
                    "total": len(assignments),
                },
            }
        )

    active_count = sum(1 for request in coverage_requests if request.status in active_statuses)
    linked_alert_count = sum(len(row["linked_alert_public_ids"]) for row in rows)
    return {
        "mode": "chv_coverage_requests_linked_to_alerts",
        "summary": {
            "visible_request_count": len(rows),
            "active_request_count": active_count,
            "linked_alert_count": linked_alert_count,
            "latest_status": rows[0]["status"] if rows else "NO_REQUEST",
        },
        "requests": rows,
    }


def _outcome_feedback_step(
    *,
    key: str,
    label: str,
    status: str,
    detail: str,
    occurred_at=None,
    evidence_level: str = "direct",
    evidence_refs: list[str] | None = None,
) -> dict:
    tone = "default"
    if status == "recorded":
        tone = "success"
    elif status in {"in_progress", "pending", "not_applicable"}:
        tone = "warning" if status == "in_progress" else "default"
    elif status in {"missing", "failed"}:
        tone = "danger"
    return {
        "key": key,
        "label": label,
        "status": status,
        "tone": tone,
        "detail": detail,
        "occurred_at": occurred_at,
        "evidence_level": evidence_level,
        "evidence_refs": evidence_refs or [],
    }


PREPAREDNESS_ACTION_OUTCOME_STEP_KEYS = {
    PreparednessAction.ACTION_CHV_FOLLOW_UP: [
        "chv_notified",
        "chv_acknowledged",
        "household_follow_up_started",
    ],
    PreparednessAction.ACTION_HOUSEHOLD_PREVENTION_MESSAGE: [
        "chv_notified",
        "household_follow_up_started",
    ],
    PreparednessAction.ACTION_FACILITY_ORS_REVIEW: ["facility_readiness_action_started"],
    PreparednessAction.ACTION_FACILITY_STAFFING_REVIEW: ["facility_readiness_action_started"],
    PreparednessAction.ACTION_COUNTY_ESCALATION: ["supplies_or_staffing_escalated"],
    PreparednessAction.ACTION_WATER_TREATMENT_DISTRIBUTION: ["supplies_or_staffing_escalated"],
    PreparednessAction.ACTION_SURVEILLANCE_FOLLOW_UP: ["surveillance_follow_up_completed"],
    PreparednessAction.ACTION_FIELD_VERIFICATION: ["field_verification_completed"],
}

OUTCOME_STEP_STATUS_RANK = {
    "not_applicable": 0,
    "pending": 0,
    "missing": 1,
    "failed": 2,
    "in_progress": 3,
    "recorded": 4,
}


def _hours_between(start_at, end_at) -> float | None:
    if not start_at or not end_at:
        return None
    return round(max(0, (end_at - start_at).total_seconds() / 3600), 2)


def _preparedness_action_completion_quality_flags(action: PreparednessAction) -> list[str]:
    flags = []
    evidence = action.completion_evidence or {}
    has_substantive_evidence = completion_evidence_has_substance(evidence)
    if action.status == PreparednessAction.STATUS_COMPLETED:
        flags.append("completed")
        flags.append("completion_evidence_present" if has_substantive_evidence else "completion_evidence_missing")
        if evidence and not has_substantive_evidence:
            flags.append("completion_evidence_boilerplate_only")
        if evidence.get("summary"):
            flags.append("completion_summary_present")
        if any(
            key in {"reference", "field_report", "call_log", "photo_ref", "dispatch_ref", "evidence_ref"}
            or key.endswith("_ref")
            for key in evidence
        ):
            flags.append("completion_reference_present")
        if action.due_at and action.completed_at:
            flags.append("completed_on_time" if action.completed_at <= action.due_at else "completed_after_due")
    if action.status == PreparednessAction.STATUS_BLOCKED:
        flags.append("blocked")
    if action.status == PreparednessAction.STATUS_CANCELLED:
        flags.append("cancelled")
    if action.status == PreparednessAction.STATUS_EXPIRED:
        flags.append("expired")
    if action.is_overdue:
        flags.append("active_overdue")
    if action.alert_id:
        flags.append("linked_to_alert")
    if action.risk_score_id:
        flags.append("linked_to_risk_score")
    if action.facility_id:
        flags.append("linked_to_facility")
    if action.chv_id:
        flags.append("linked_to_chv")
    if action.source_trigger_ref:
        flags.append("source_lineage_present")
    return flags


def _preparedness_action_outcome_status(action: PreparednessAction) -> str:
    if action.status == PreparednessAction.STATUS_COMPLETED:
        return "recorded" if completion_evidence_has_substance(action.completion_evidence) else "failed"
    if action.status in {
        PreparednessAction.STATUS_DRAFT,
        PreparednessAction.STATUS_QUEUED,
        PreparednessAction.STATUS_ASSIGNED,
        PreparednessAction.STATUS_ACKNOWLEDGED,
        PreparednessAction.STATUS_IN_PROGRESS,
        PreparednessAction.STATUS_ESCALATED,
    }:
        return "in_progress"
    if action.status in {
        PreparednessAction.STATUS_BLOCKED,
        PreparednessAction.STATUS_CANCELLED,
        PreparednessAction.STATUS_EXPIRED,
    }:
        return "failed"
    return "missing"


def _preparedness_action_step_signal(preparedness_action_evidence: dict, step_key: str) -> dict | None:
    candidates = [
        row
        for row in preparedness_action_evidence.get("action_history", [])
        if step_key in row.get("response_step_keys", [])
    ]
    if not candidates:
        return None

    candidates.sort(
        key=lambda row: (
            OUTCOME_STEP_STATUS_RANK.get(row["outcome_status"], 0),
            row.get("completed_at") or row.get("acknowledged_at") or row.get("created_at"),
        ),
        reverse=True,
    )
    selected = candidates[0]
    action_label = selected["action_type_label"]
    status = selected["outcome_status"]
    if status == "recorded":
        detail = f"{action_label} is completed in the preparedness action ledger."
        occurred_at = selected.get("completed_at") or selected.get("updated_at")
    elif status == "in_progress":
        detail = f"{action_label} is active in the preparedness action ledger."
        occurred_at = selected.get("acknowledged_at") or selected.get("created_at")
    else:
        detail = f"{action_label} is present in the preparedness action ledger but is {selected['status'].lower()}."
        occurred_at = selected.get("updated_at") or selected.get("created_at")
    return {
        "status": status,
        "detail": detail,
        "occurred_at": occurred_at,
        "evidence_level": "preparedness_action_ledger",
        "evidence_refs": [selected["public_id"]],
    }


def _merge_outcome_step_signal(
    *,
    status: str,
    detail: str,
    occurred_at,
    evidence_level: str,
    evidence_refs: list[str],
    preparedness_action_evidence: dict,
    step_key: str,
) -> tuple[str, str, object, str, list[str]]:
    action_signal = _preparedness_action_step_signal(preparedness_action_evidence, step_key)
    if not action_signal:
        return status, detail, occurred_at, evidence_level, evidence_refs

    if OUTCOME_STEP_STATUS_RANK[action_signal["status"]] > OUTCOME_STEP_STATUS_RANK.get(status, 0):
        return (
            action_signal["status"],
            action_signal["detail"],
            action_signal["occurred_at"],
            action_signal["evidence_level"],
            action_signal["evidence_refs"],
        )

    return status, detail, occurred_at, evidence_level, evidence_refs


def _preparedness_action_ledger_step(preparedness_action_evidence: dict) -> dict | None:
    summary = preparedness_action_evidence["summary"]
    if summary["total_count"] == 0:
        return None
    if summary["completed_count"] > 0:
        status = "recorded"
        detail = (
            f"{summary['completed_count']} completed preparedness action"
            f"{'s' if summary['completed_count'] != 1 else ''} linked to this outcome window."
        )
        occurred_at = summary["first_completed_at"]
    elif summary["in_progress_count"] > 0:
        status = "in_progress"
        detail = (
            f"{summary['in_progress_count']} preparedness action"
            f"{'s are' if summary['in_progress_count'] != 1 else ' is'} still active for this outcome window."
        )
        occurred_at = summary["first_action_at"]
    else:
        status = "failed"
        detail = "Preparedness actions exist for this outcome window, but they are blocked, cancelled, or expired."
        occurred_at = summary["first_action_at"]

    return _outcome_feedback_step(
        key="preparedness_action_ledger",
        label="Preparedness action ledger",
        status=status,
        detail=detail,
        occurred_at=occurred_at,
        evidence_level="preparedness_action_ledger",
        evidence_refs=[row["public_id"] for row in preparedness_action_evidence["action_history"]],
    )


def _recent_preparedness_action_evidence_for_ward(
    *,
    ward: Ward,
    reference_at,
    related_alerts: list[Alert],
    prediction_rows: list[dict],
    classification: str,
) -> dict:
    window_start = reference_at - timedelta(hours=1) if reference_at else timezone.now() - timedelta(days=30)
    alert_ids = [alert.id for alert in related_alerts]
    alert_public_ids = [str(alert.public_id) for alert in related_alerts]
    risk_score_ids = [
        row["risk_score_id"]
        for row in prediction_rows
        if row.get("risk_score_id")
    ]
    latest_row = _latest_evaluated_prediction_row(prediction_rows)
    label_ref = (latest_row or {}).get("label_window_ref") or ""
    outcome_ref = f"ward_outcome_feedback:{ward.id}:{label_ref or reference_at.isoformat()}"

    action_filter = Q(ward=ward) & Q(created_at__gte=window_start)
    if alert_ids:
        action_filter |= Q(ward=ward, alert_id__in=alert_ids)
    if risk_score_ids:
        action_filter |= Q(ward=ward, risk_score_id__in=risk_score_ids)

    actions = list(
        PreparednessAction.objects.filter(action_filter)
        .select_related(
            "ward",
            "facility",
            "chv",
            "alert",
            "risk_score",
            "model_run",
            "assigned_to",
        )
        .order_by("-created_at")[:20]
    )

    action_history = []
    aggregate_quality_flags = set()
    for action in actions:
        quality_flags = _preparedness_action_completion_quality_flags(action)
        aggregate_quality_flags.update(quality_flags)
        action_history.append(
            {
                "public_id": str(action.public_id),
                "action_type": action.action_type,
                "action_type_label": dict(PreparednessAction.ACTION_TYPE_CHOICES).get(action.action_type, action.action_type),
                "status": action.status,
                "outcome_status": _preparedness_action_outcome_status(action),
                "priority": action.priority,
                "ward_id": action.ward_id,
                "ward_name": action.ward.name,
                "facility_id": action.facility_id,
                "facility_name": action.facility.name if action.facility_id else "",
                "chv_id": action.chv_id,
                "chv_name": action.chv.name if action.chv_id else "",
                "assigned_to": action.assigned_to_id,
                "assigned_to_username": action.assigned_to.username if action.assigned_to_id else "",
                "assigned_to_team": action.assigned_to_team,
                "source_trigger_type": action.source_trigger_type,
                "source_trigger_ref": action.source_trigger_ref,
                "risk_score_id": action.risk_score_id,
                "model_run_id": action.model_run_id,
                "model_run_version": action.model_run.model_version if action.model_run_id else "",
                "alert_public_id": str(action.alert.public_id) if action.alert_id else "",
                "linked_alert_public_ids": [str(action.alert.public_id)] if action.alert_id else [],
                "related_alert_public_ids": alert_public_ids,
                "created_at": action.created_at,
                "acknowledged_at": action.acknowledged_at,
                "completed_at": action.completed_at,
                "due_at": action.due_at,
                "is_overdue": action.is_overdue,
                "completion_evidence_present": completion_evidence_has_substance(action.completion_evidence),
                "completion_quality_flags": quality_flags,
                "response_step_keys": PREPAREDNESS_ACTION_OUTCOME_STEP_KEYS.get(action.action_type, []),
                "outcome_links": {
                    "outcome_ref": outcome_ref,
                    "label_window_ref": label_ref,
                    "prediction_risk_score_ids": risk_score_ids,
                    "alert_public_ids": alert_public_ids,
                },
            }
        )

    first_action_at = min((action.created_at for action in actions if action.created_at), default=None)
    first_acknowledged_at = min((action.acknowledged_at for action in actions if action.acknowledged_at), default=None)
    first_completed_at = min((action.completed_at for action in actions if action.completed_at), default=None)
    completed_actions = [
        action
        for action in actions
        if action.status == PreparednessAction.STATUS_COMPLETED
        and completion_evidence_has_substance(action.completion_evidence)
    ]
    completed_without_substantive_evidence_actions = [
        action
        for action in actions
        if action.status == PreparednessAction.STATUS_COMPLETED
        and not completion_evidence_has_substance(action.completion_evidence)
    ]
    in_progress_actions = [
        action
        for action in actions
        if action.status in {
            PreparednessAction.STATUS_DRAFT,
            PreparednessAction.STATUS_QUEUED,
            PreparednessAction.STATUS_ASSIGNED,
            PreparednessAction.STATUS_ACKNOWLEDGED,
            PreparednessAction.STATUS_IN_PROGRESS,
            PreparednessAction.STATUS_ESCALATED,
        }
    ]
    failed_actions = [
        action
        for action in actions
        if action.status in {
            PreparednessAction.STATUS_BLOCKED,
            PreparednessAction.STATUS_CANCELLED,
            PreparednessAction.STATUS_EXPIRED,
        }
    ] + completed_without_substantive_evidence_actions
    overdue_action_public_ids = [str(action.public_id) for action in actions if action.is_overdue]
    blocked_action_public_ids = [
        str(action.public_id)
        for action in actions
        if action.status == PreparednessAction.STATUS_BLOCKED
    ]
    cancelled_action_public_ids = [
        str(action.public_id)
        for action in actions
        if action.status == PreparednessAction.STATUS_CANCELLED
    ]
    response_expected = bool(related_alerts) or classification in {"hit", "false_alert"}
    missed_action_review_required = response_expected and not actions

    false_alert_context_required = classification == "false_alert" and bool(completed_actions)
    return {
        "mode": "preparedness_action_ledger_outcome_linkage",
        "outcome_ref": outcome_ref,
        "reference_at": reference_at,
        "window_start": window_start,
        "related_alert_public_ids": alert_public_ids,
        "prediction_risk_score_ids": risk_score_ids,
        "summary": {
            "total_count": len(actions),
            "completed_count": len(completed_actions),
            "completed_without_substantive_evidence_count": len(completed_without_substantive_evidence_actions),
            "in_progress_count": len(in_progress_actions),
            "failed_count": len(failed_actions),
            "blocked_count": len(blocked_action_public_ids),
            "overdue_count": len(overdue_action_public_ids),
            "completed_with_evidence_count": sum(
                1 for action in completed_actions if completion_evidence_has_substance(action.completion_evidence)
            ),
            "first_action_at": first_action_at,
            "first_acknowledged_at": first_acknowledged_at,
            "first_completed_at": first_completed_at,
        },
        "response_time_measurements": {
            "hours_to_first_action": _hours_between(reference_at, first_action_at),
            "hours_to_first_acknowledgement": _hours_between(reference_at, first_acknowledged_at),
            "hours_to_first_completion": _hours_between(reference_at, first_completed_at),
        },
        "completion_quality_flags": sorted(aggregate_quality_flags),
        "action_history": action_history,
        "missed_action_review": {
            "review_required": missed_action_review_required,
            "missing_required_action_keys": ["preparedness_action_ledger"] if missed_action_review_required else [],
            "overdue_action_public_ids": overdue_action_public_ids,
            "blocked_action_public_ids": blocked_action_public_ids,
            "cancelled_action_public_ids": cancelled_action_public_ids,
            "detail": (
                "No preparedness action ledger record is linked to this alert/outcome window."
                if missed_action_review_required
                else "Preparedness action linkage is present or no response action was required."
            ),
        },
        "false_alert_review_context": {
            "review_required": false_alert_context_required,
            "completed_action_public_ids": [str(action.public_id) for action in completed_actions],
            "detail": (
                "Quiet observed label followed completed preparedness actions; review response effect before treating this as pure model error."
                if false_alert_context_required
                else "No completed preparedness action context changes the false-alert review."
            ),
        },
    }


def _latest_evaluated_prediction_row(prediction_rows: list[dict]) -> dict | None:
    for row in prediction_rows:
        if row["classification"] != "pending_label":
            return row
    return prediction_rows[0] if prediction_rows else None


def _phase_7_reference_time(related_alerts: list[Alert], prediction_rows: list[dict]):
    if related_alerts:
        return max(alert.created_at for alert in related_alerts if alert.created_at)
    prediction_times = [row["prediction_generated_at"] for row in prediction_rows if row.get("prediction_generated_at")]
    if prediction_times:
        return max(prediction_times)
    return timezone.now() - timedelta(days=30)


def _recent_facility_action_evidence_for_ward(ward: Ward, *, reference_at) -> dict:
    window_start = reference_at - timedelta(hours=1) if reference_at else timezone.now() - timedelta(days=30)
    reviews = list(
        FacilityReadinessReview.objects.filter(ward=ward, created_at__gte=window_start)
        .prefetch_related("update_requests", "escalations")
        .order_by("-created_at")[:4]
    )
    review_rows = []
    update_request_rows = []
    escalation_rows = []
    for review in reviews:
        review_rows.append(
            {
                "public_id": str(review.public_id),
                "status": review.status,
                "severity": review.severity,
                "created_at": review.created_at,
                "acknowledged_at": review.acknowledged_at,
                "resolved_at": review.resolved_at,
            }
        )
        for update_request in review.update_requests.all():
            update_request_rows.append(
                {
                    "public_id": str(update_request.public_id),
                    "status": update_request.status,
                    "channel": update_request.channel,
                    "requested_at": update_request.requested_at,
                    "sent_at": update_request.sent_at,
                    "acknowledged_at": update_request.acknowledged_at,
                }
            )
        for escalation in review.escalations.all():
            escalation_rows.append(
                {
                    "public_id": str(escalation.public_id),
                    "status": escalation.status,
                    "severity": escalation.severity,
                    "created_at": escalation.created_at,
                    "acknowledged_at": escalation.acknowledged_at,
                    "resolved_at": escalation.resolved_at,
                }
            )

    if not escalation_rows:
        direct_escalations = FacilityReadinessEscalation.objects.filter(ward=ward, created_at__gte=window_start).order_by(
            "-created_at"
        )[:4]
        escalation_rows = [
            {
                "public_id": str(escalation.public_id),
                "status": escalation.status,
                "severity": escalation.severity,
                "created_at": escalation.created_at,
                "acknowledged_at": escalation.acknowledged_at,
                "resolved_at": escalation.resolved_at,
            }
            for escalation in direct_escalations
        ]

    return {
        "reviews": review_rows,
        "update_requests": update_request_rows,
        "escalations": escalation_rows,
    }


def _phase_7_observed_outbreak_outcome(*, latest_row: dict | None, response_quality_state: str, response_started: bool) -> dict:
    if latest_row is None or latest_row["classification"] == "pending_label":
        return {
            "state": "pending",
            "label": "Pending outcome label",
            "detail": "The 7 to 14 day label window has not been observed yet.",
        }

    observed_label = latest_row["observed_label"]
    suspected_cases = int(latest_row.get("observed_suspected_cases") or 0)
    confirmed_cases = int(latest_row.get("observed_confirmed_cases") or 0)
    if observed_label == SurveillanceOutbreakLabel.ACTIVE:
        return {
            "state": "escalated",
            "label": "Outbreak escalated",
            "detail": (
                f"Observed label is active with {suspected_cases} suspected and {confirmed_cases} confirmed cases; "
                f"response quality is {response_quality_state.replace('_', ' ')}."
            ),
        }
    if response_started and observed_label in {SurveillanceOutbreakLabel.NONE, SurveillanceOutbreakLabel.WATCH}:
        return {
            "state": "possibly_avoided_or_reduced",
            "label": "Possibly avoided or reduced",
            "detail": (
                "No active outbreak label is visible after recorded response work. This is evidence for review, "
                "not proof that response alone prevented the outbreak."
            ),
        }
    return {
        "state": "no_outbreak_observed",
        "label": "No outbreak observed",
        "detail": "No active outbreak label is visible in the matched surveillance window.",
    }


def _build_phase_7_outcome_feedback(
    *,
    ward: Ward,
    related_alerts: list[Alert],
    prediction_rows: list[dict],
    chv_action_status: dict,
) -> dict:
    latest_row = _latest_evaluated_prediction_row(prediction_rows)
    classification = (latest_row or {}).get("classification") or "pending_label"
    response_required = bool(related_alerts) or classification in {"hit", "false_alert"}
    reference_at = _phase_7_reference_time(related_alerts, prediction_rows)
    window_start = reference_at - timedelta(hours=1) if reference_at else timezone.now() - timedelta(days=30)
    preparedness_action_evidence = _recent_preparedness_action_evidence_for_ward(
        ward=ward,
        reference_at=reference_at,
        related_alerts=related_alerts,
        prediction_rows=prediction_rows,
        classification=classification,
    )
    alert_refs = [str(alert.public_id) for alert in related_alerts]
    latest_alert = related_alerts[0] if related_alerts else None
    delivered_alerts = [alert for alert in related_alerts if alert.status == Alert.STATUS_DELIVERED]
    failed_alerts = [alert for alert in related_alerts if alert.status == Alert.STATUS_FAILED]

    if related_alerts:
        alert_status = "recorded" if delivered_alerts or len(failed_alerts) != len(related_alerts) else "failed"
        alert_detail = (
            f"{len(related_alerts)} alert record{'s' if len(related_alerts) != 1 else ''} exist; "
            f"{len(delivered_alerts)} delivered and {len(failed_alerts)} failed."
        )
        alert_occurred_at = latest_alert.created_at if latest_alert else None
    else:
        alert_status = "missing"
        alert_detail = "No alert record is visible for this ward in the current intelligence window."
        alert_occurred_at = None

    chv_messages = list(
        CHVMessage.objects.filter(ward=ward, created_at__gte=window_start).order_by("-created_at")[:6]
    )
    delivered_messages = [
        message
        for message in chv_messages
        if message.status in {CHVMessage.STATUS_SENT, CHVMessage.STATUS_DELIVERED}
    ]
    queued_messages = [message for message in chv_messages if message.status == CHVMessage.STATUS_QUEUED]
    failed_messages = [message for message in chv_messages if message.status == CHVMessage.STATUS_FAILED]

    coverage_rows = chv_action_status.get("requests", [])
    alert_linked_coverage_rows = [
        row
        for row in coverage_rows
        if row.get("linked_alert_public_ids") or row.get("trigger_source") == CHVCoverageRequest.TRIGGER_SOURCE_ALERT_DRIVEN
    ]
    coverage_rows_for_feedback = alert_linked_coverage_rows or coverage_rows
    assignment_active_count = sum(row["assignment_counts"]["active"] for row in coverage_rows_for_feedback)
    assignment_completed_count = sum(row["assignment_counts"]["completed"] for row in coverage_rows_for_feedback)
    assignment_total_count = sum(row["assignment_counts"]["total"] for row in coverage_rows_for_feedback)
    coverage_resolved_count = sum(1 for row in coverage_rows_for_feedback if row["status"] == CHVCoverageRequest.STATUS_RESOLVED)
    coverage_in_progress_count = sum(
        1
        for row in coverage_rows_for_feedback
        if row["status"] in {CHVCoverageRequest.STATUS_OPEN, CHVCoverageRequest.STATUS_APPROVED, CHVCoverageRequest.STATUS_IN_PROGRESS}
    )

    if delivered_messages:
        chv_notified_status = "recorded"
        chv_notified_detail = f"{len(delivered_messages)} direct CHV message record{'s' if len(delivered_messages) != 1 else ''} sent or delivered."
        chv_notified_occurred_at = delivered_messages[0].created_at
        chv_notified_evidence_level = "direct"
        chv_notified_refs = [str(message.public_id) for message in delivered_messages]
    elif queued_messages:
        chv_notified_status = "in_progress"
        chv_notified_detail = "CHV notification is queued but not yet sent or delivered."
        chv_notified_occurred_at = queued_messages[0].created_at
        chv_notified_evidence_level = "direct"
        chv_notified_refs = [str(message.public_id) for message in queued_messages]
    elif failed_messages:
        chv_notified_status = "failed"
        chv_notified_detail = "The latest CHV notification attempt failed."
        chv_notified_occurred_at = failed_messages[0].created_at
        chv_notified_evidence_level = "direct"
        chv_notified_refs = [str(message.public_id) for message in failed_messages]
    elif coverage_rows_for_feedback:
        chv_notified_status = "recorded"
        chv_notified_detail = "No direct CHV message is linked, but an alert-linked coverage request exists as operational proxy evidence."
        chv_notified_occurred_at = coverage_rows_for_feedback[0]["created_at"]
        chv_notified_evidence_level = "coverage_request_proxy"
        chv_notified_refs = [row["public_id"] for row in coverage_rows_for_feedback]
    else:
        chv_notified_status = "missing" if response_required else "not_applicable"
        chv_notified_detail = "No CHV notification or alert-linked coverage request is visible after the alert."
        chv_notified_occurred_at = None
        chv_notified_evidence_level = "missing"
        chv_notified_refs = []
    (
        chv_notified_status,
        chv_notified_detail,
        chv_notified_occurred_at,
        chv_notified_evidence_level,
        chv_notified_refs,
    ) = _merge_outcome_step_signal(
        status=chv_notified_status,
        detail=chv_notified_detail,
        occurred_at=chv_notified_occurred_at,
        evidence_level=chv_notified_evidence_level,
        evidence_refs=chv_notified_refs,
        preparedness_action_evidence=preparedness_action_evidence,
        step_key="chv_notified",
    )

    if assignment_completed_count > 0:
        chv_ack_status = "recorded"
        chv_ack_detail = f"{assignment_completed_count} CHV assignment{'s' if assignment_completed_count != 1 else ''} completed."
        chv_ack_occurred_at = None
        chv_ack_evidence_level = "assignment_proxy"
        chv_ack_refs = [row["public_id"] for row in coverage_rows_for_feedback]
    elif assignment_active_count > 0:
        chv_ack_status = "recorded"
        chv_ack_detail = f"{assignment_active_count} active CHV assignment{'s' if assignment_active_count != 1 else ''} exists; assignment start is proxy acknowledgement evidence."
        chv_ack_occurred_at = None
        chv_ack_evidence_level = "assignment_proxy"
        chv_ack_refs = [row["public_id"] for row in coverage_rows_for_feedback]
    elif coverage_in_progress_count > 0:
        chv_ack_status = "in_progress"
        chv_ack_detail = "A coverage request exists, but no CHV assignment acknowledgement proxy is recorded yet."
        chv_ack_occurred_at = None
        chv_ack_evidence_level = "coverage_request_proxy"
        chv_ack_refs = [row["public_id"] for row in coverage_rows_for_feedback]
    else:
        chv_ack_status = "missing" if response_required else "not_applicable"
        chv_ack_detail = "No CHV acknowledgement or assignment proxy is visible after the alert."
        chv_ack_occurred_at = None
        chv_ack_evidence_level = "missing"
        chv_ack_refs = []
    (
        chv_ack_status,
        chv_ack_detail,
        chv_ack_occurred_at,
        chv_ack_evidence_level,
        chv_ack_refs,
    ) = _merge_outcome_step_signal(
        status=chv_ack_status,
        detail=chv_ack_detail,
        occurred_at=chv_ack_occurred_at,
        evidence_level=chv_ack_evidence_level,
        evidence_refs=chv_ack_refs,
        preparedness_action_evidence=preparedness_action_evidence,
        step_key="chv_acknowledged",
    )

    if assignment_completed_count > 0 or coverage_resolved_count > 0:
        follow_up_status = "recorded"
        follow_up_detail = "Household follow-up is recorded through completed CHV assignment or resolved coverage request."
        follow_up_occurred_at = None
        follow_up_evidence_level = "assignment_proxy" if assignment_total_count else "coverage_request_proxy"
        follow_up_refs = [row["public_id"] for row in coverage_rows_for_feedback]
    elif assignment_active_count > 0 or coverage_in_progress_count > 0:
        follow_up_status = "in_progress"
        follow_up_detail = "Household follow-up has started through active CHV assignment or in-progress coverage request."
        follow_up_occurred_at = None
        follow_up_evidence_level = "assignment_proxy" if assignment_total_count else "coverage_request_proxy"
        follow_up_refs = [row["public_id"] for row in coverage_rows_for_feedback]
    else:
        follow_up_status = "missing" if response_required else "not_applicable"
        follow_up_detail = "No household follow-up start is visible after the alert."
        follow_up_occurred_at = None
        follow_up_evidence_level = "missing"
        follow_up_refs = []
    (
        follow_up_status,
        follow_up_detail,
        follow_up_occurred_at,
        follow_up_evidence_level,
        follow_up_refs,
    ) = _merge_outcome_step_signal(
        status=follow_up_status,
        detail=follow_up_detail,
        occurred_at=follow_up_occurred_at,
        evidence_level=follow_up_evidence_level,
        evidence_refs=follow_up_refs,
        preparedness_action_evidence=preparedness_action_evidence,
        step_key="household_follow_up_started",
    )

    facility_evidence = _recent_facility_action_evidence_for_ward(ward, reference_at=reference_at)
    review_rows = facility_evidence["reviews"]
    update_request_rows = facility_evidence["update_requests"]
    escalation_rows = facility_evidence["escalations"]
    if any(row["status"] == FacilityReadinessReview.STATUS_RESOLVED for row in review_rows) or any(
        row["status"] == FacilityReadinessUpdateRequest.STATUS_ACKNOWLEDGED for row in update_request_rows
    ):
        facility_status = "recorded"
        facility_detail = "Facility readiness work has a resolved review or acknowledged update request."
        facility_occurred_at = None
        facility_evidence_level = "direct"
        facility_refs = [row["public_id"] for row in [*review_rows, *update_request_rows]]
    elif review_rows or update_request_rows:
        facility_status = "in_progress"
        facility_detail = "Facility readiness action has started through review or update-request records."
        facility_occurred_at = None
        facility_evidence_level = "direct"
        facility_refs = [row["public_id"] for row in [*review_rows, *update_request_rows]]
    else:
        facility_status = "missing" if response_required else "not_applicable"
        facility_detail = "No facility readiness action is visible after the alert."
        facility_occurred_at = None
        facility_evidence_level = "missing"
        facility_refs = []
    (
        facility_status,
        facility_detail,
        facility_occurred_at,
        facility_evidence_level,
        facility_refs,
    ) = _merge_outcome_step_signal(
        status=facility_status,
        detail=facility_detail,
        occurred_at=facility_occurred_at,
        evidence_level=facility_evidence_level,
        evidence_refs=facility_refs,
        preparedness_action_evidence=preparedness_action_evidence,
        step_key="facility_readiness_action_started",
    )

    if any(row["status"] == FacilityReadinessEscalation.STATUS_RESOLVED for row in escalation_rows):
        escalation_status = "recorded"
        escalation_detail = "Supply or staffing escalation was resolved."
        escalation_occurred_at = None
        escalation_evidence_level = "direct"
        escalation_refs = [row["public_id"] for row in escalation_rows]
    elif escalation_rows:
        escalation_status = "in_progress"
        escalation_detail = "Supply or staffing escalation has started and remains open or acknowledged."
        escalation_occurred_at = None
        escalation_evidence_level = "direct"
        escalation_refs = [row["public_id"] for row in escalation_rows]
    else:
        escalation_status = "missing" if response_required else "not_applicable"
        escalation_detail = "No supply or staffing escalation is visible after the alert."
        escalation_occurred_at = None
        escalation_evidence_level = "missing"
        escalation_refs = []
    (
        escalation_status,
        escalation_detail,
        escalation_occurred_at,
        escalation_evidence_level,
        escalation_refs,
    ) = _merge_outcome_step_signal(
        status=escalation_status,
        detail=escalation_detail,
        occurred_at=escalation_occurred_at,
        evidence_level=escalation_evidence_level,
        evidence_refs=escalation_refs,
        preparedness_action_evidence=preparedness_action_evidence,
        step_key="supplies_or_staffing_escalated",
    )

    suspected_cases = int((latest_row or {}).get("observed_suspected_cases") or 0)
    confirmed_cases = int((latest_row or {}).get("observed_confirmed_cases") or 0)
    observed_label = (latest_row or {}).get("observed_label") or "PENDING"
    observed_truth_level = (latest_row or {}).get("observed_truth_level") or ""
    label_ref = (latest_row or {}).get("label_window_ref") or ""
    observed_status = "pending" if latest_row is None or latest_row["classification"] == "pending_label" else "recorded"

    steps = [
        _outcome_feedback_step(
            key="alert_issued",
            label="Alert issued",
            status=alert_status,
            detail=alert_detail,
            occurred_at=alert_occurred_at,
            evidence_refs=alert_refs,
        ),
        _outcome_feedback_step(
            key="chv_notified",
            label="CHV notified",
            status=chv_notified_status,
            detail=chv_notified_detail,
            occurred_at=chv_notified_occurred_at,
            evidence_level=chv_notified_evidence_level,
            evidence_refs=chv_notified_refs,
        ),
        _outcome_feedback_step(
            key="chv_acknowledged",
            label="CHV acknowledged",
            status=chv_ack_status,
            detail=chv_ack_detail,
            occurred_at=chv_ack_occurred_at,
            evidence_level=chv_ack_evidence_level,
            evidence_refs=chv_ack_refs,
        ),
        _outcome_feedback_step(
            key="household_follow_up_started",
            label="Household follow-up started",
            status=follow_up_status,
            detail=follow_up_detail,
            occurred_at=follow_up_occurred_at,
            evidence_level=follow_up_evidence_level,
            evidence_refs=follow_up_refs,
        ),
        _outcome_feedback_step(
            key="facility_readiness_action_started",
            label="Facility readiness action started",
            status=facility_status,
            detail=facility_detail,
            occurred_at=facility_occurred_at,
            evidence_level=facility_evidence_level,
            evidence_refs=facility_refs,
        ),
        _outcome_feedback_step(
            key="supplies_or_staffing_escalated",
            label="Supplies or staffing escalated",
            status=escalation_status,
            detail=escalation_detail,
            occurred_at=escalation_occurred_at,
            evidence_level=escalation_evidence_level,
            evidence_refs=escalation_refs,
        ),
        _outcome_feedback_step(
            key="suspected_cases_observed",
            label="Suspected cases observed",
            status=observed_status,
            detail=f"{suspected_cases} suspected cases recorded in the matched label window.",
            evidence_refs=[label_ref] if label_ref else [],
        ),
        _outcome_feedback_step(
            key="confirmed_cases_observed",
            label="Confirmed cases observed",
            status=observed_status,
            detail=f"{confirmed_cases} confirmed cases recorded in the matched label window.",
            evidence_refs=[label_ref] if label_ref else [],
        ),
    ]
    ledger_step = _preparedness_action_ledger_step(preparedness_action_evidence)
    if ledger_step:
        steps.insert(5, ledger_step)

    required_execution_keys = (
        {"preparedness_action_ledger"}
        if preparedness_action_evidence["summary"]["total_count"] > 0
        else {"chv_notified", "chv_acknowledged", "household_follow_up_started"}
    )
    alert_failure_steps = (
        [step for step in steps if step["key"] == "alert_issued" and step["status"] == "failed"] if response_required else []
    )
    required_execution_steps = [step for step in steps if step["key"] in required_execution_keys]
    execution_failure_steps = (
        [step for step in required_execution_steps if step["status"] in {"missing", "failed"}] if response_required else []
    )
    downstream_failure_steps = [*alert_failure_steps, *execution_failure_steps]
    in_progress_steps = [step for step in required_execution_steps if step["status"] == "in_progress"] if response_required else []
    response_started = any(
        step["key"]
        in {
            "chv_notified",
            "chv_acknowledged",
            "household_follow_up_started",
            "facility_readiness_action_started",
            "supplies_or_staffing_escalated",
            "preparedness_action_ledger",
        }
        and step["status"] in {"recorded", "in_progress"}
        for step in steps
    )
    if not response_required:
        response_quality_state = "response_not_required"
    elif alert_failure_steps:
        response_quality_state = "alert_delivery_failure"
    elif execution_failure_steps:
        response_quality_state = "response_gap"
    elif in_progress_steps:
        response_quality_state = "response_in_progress"
    elif response_required:
        response_quality_state = "response_complete"
    else:
        response_quality_state = "response_not_required"

    model_quality_state = {
        "hit": "prediction_hit",
        "false_alert": "possible_false_alert",
        "missed_outbreak": "missed_outbreak",
        "correct_quiet": "correct_quiet",
        "pending_label": "pending_label",
    }.get(classification, "pending_label")

    if alert_failure_steps:
        attribution = "alert_delivery_review"
    elif classification == "missed_outbreak":
        attribution = "model_quality_review"
    elif classification == "hit" and response_quality_state == "response_gap":
        attribution = "response_quality_review"
    elif classification == "hit" and response_quality_state == "response_in_progress":
        attribution = "mixed_pending_response_review"
    elif classification == "false_alert" and response_started:
        attribution = "possible_response_success_or_model_false_positive"
    elif classification == "false_alert":
        attribution = "model_quality_review"
    elif classification == "correct_quiet":
        attribution = "no_issue_detected"
    else:
        attribution = "pending_outcome"

    outbreak_outcome = _phase_7_observed_outbreak_outcome(
        latest_row=latest_row,
        response_quality_state=response_quality_state,
        response_started=response_started,
    )
    steps.append(
        _outcome_feedback_step(
            key="outbreak_trajectory",
            label="Outbreak avoided, reduced, or escalated",
            status="pending" if outbreak_outcome["state"] == "pending" else "recorded",
            detail=outbreak_outcome["detail"],
            evidence_refs=[label_ref] if label_ref else [],
        )
    )

    review_items = []
    if alert_failure_steps:
        review_items.append(
            {
                "category": "alert_delivery",
                "severity": "high",
                "title": "Alert delivery failure before outcome window",
                "detail": (
                    "Every linked alert record failed delivery, so outcome review must separate alert delivery failure "
                    "from model quality and response-task execution."
                ),
                "step_keys": [step["key"] for step in alert_failure_steps],
            }
        )
    if execution_failure_steps and observed_label == SurveillanceOutbreakLabel.ACTIVE:
        review_items.append(
            {
                "category": "response_quality",
                "severity": "high",
                "title": "Active outbreak with downstream response gap",
                "detail": (
                    "Do not blame this outcome only on the model; alert delivery, CHV acknowledgement, "
                    "or household follow-up evidence is missing or failed."
                ),
                "step_keys": [step["key"] for step in execution_failure_steps],
            }
        )
    missed_action_review = preparedness_action_evidence["missed_action_review"]
    if missed_action_review["review_required"] and execution_failure_steps:
        review_items.append(
            {
                "category": "missed_action_review",
                "severity": "high",
                "title": "No preparedness action ledger entry for response window",
                "detail": missed_action_review["detail"],
                "step_keys": missed_action_review["missing_required_action_keys"],
            }
        )
    if preparedness_action_evidence["summary"]["blocked_count"] or preparedness_action_evidence["summary"]["overdue_count"]:
        review_items.append(
            {
                "category": "action_execution",
                "severity": "high" if preparedness_action_evidence["summary"]["blocked_count"] else "medium",
                "title": "Preparedness action needs execution review",
                "detail": (
                    f"{preparedness_action_evidence['summary']['blocked_count']} blocked and "
                    f"{preparedness_action_evidence['summary']['overdue_count']} overdue action(s) are linked to this outcome window."
                ),
                "step_keys": ["preparedness_action_ledger"],
            }
        )
    if classification == "false_alert" and response_started:
        review_items.append(
            {
                "category": "model_vs_response_quality",
                "severity": "medium",
                "title": "False-alert review needs response context",
                "detail": (
                    "A quiet observed label after downstream action may be a false alert, a reduced outbreak, "
                    "or an avoided outbreak; review action timing before treating it as pure model error."
                ),
                "step_keys": ["household_follow_up_started", "suspected_cases_observed", "confirmed_cases_observed"],
            }
        )

    return {
        "mode": "alert_to_action_outcome_feedback",
        "reference_at": reference_at,
        "model_quality_state": model_quality_state,
        "response_quality_state": response_quality_state,
        "attribution": attribution,
        "accountability_note": (
            "Prediction outcome and response execution are shown separately so misses are not attributed to the model "
            "when alert delivery or CHV action failed downstream."
        ),
        "observed_outcome": {
            **outbreak_outcome,
            "observed_label": observed_label,
            "observed_truth_level": observed_truth_level,
            "suspected_case_count": suspected_cases,
            "confirmed_case_count": confirmed_cases,
        },
        "summary": {
            "step_count": len(steps),
            "recorded_step_count": sum(1 for step in steps if step["status"] == "recorded"),
            "downstream_failure_count": len(downstream_failure_steps),
            "alert_failure_count": len(alert_failure_steps),
            "response_execution_failure_count": len(execution_failure_steps),
            "in_progress_step_count": sum(1 for step in steps if step["status"] == "in_progress"),
            "review_item_count": len(review_items),
        },
        "steps": steps,
        "review_items": review_items,
        "facility_action_evidence": facility_evidence,
        "preparedness_action_evidence": preparedness_action_evidence,
    }


def _false_missed_review_evidence(outcome_rows: list[dict]) -> dict:
    review_items = []
    for row in outcome_rows:
        if row["classification"] not in {"false_alert", "missed_outbreak"}:
            continue
        review_items.append(
            {
                "classification": row["classification"],
                "risk_score_id": row["risk_score_id"],
                "prediction_generated_at": row["prediction_generated_at"],
                "label_window_ref": row["label_window_ref"],
                "observed_label": row["observed_label"],
                "recommended_review_action": (
                    "Review alert threshold, source confidence, and CHV follow-through for this false alert."
                    if row["classification"] == "false_alert"
                    else "Review missed-outbreak pathway, source freshness, and whether the threshold was too conservative."
                ),
            }
        )

    return {
        "mode": "ward_prediction_outcome_review",
        "open_review_count": len(review_items),
        "items": review_items,
        "workflow_label": (
            "Outcome review required"
            if review_items
            else "No false-alert or missed-outbreak review items in the visible ward history"
        ),
    }


def _build_phase_6_operational_evidence(
    *,
    ward: Ward,
    latest_risk: RiskScore | None,
    risk_history: list[RiskScore],
    current_risk: dict,
    freshness: dict,
    workflow: AlertWorkflowState,
    related_alerts: list[Alert],
    population_exposure_context: dict,
    surveillance_context: dict,
    climate_evidence: dict | None = None,
) -> dict:
    prediction_rows, outcome_summary = _prediction_label_history(risk_history)
    chv_action_status = _chv_action_evidence_for_ward(ward)
    climate_evidence = climate_evidence or {}
    return {
        "schema_version": "ward-operational-evidence-v1",
        "ward_id": ward.id,
        "forecast_horizon": _forecast_horizon_evidence(latest_risk, climate_evidence=climate_evidence),
        "climate_source": climate_evidence,
        "model_readiness": _model_readiness_evidence(latest_risk, population_exposure_context),
        "source_badges": _source_evidence_badges(
            current_risk=current_risk,
            freshness=freshness,
            surveillance_context=surveillance_context,
            population_exposure_context=population_exposure_context,
        ),
        "alert_candidate_review": _alert_candidate_review_evidence(current_risk, workflow, related_alerts),
        "outcome_evaluation": {
            **outcome_summary,
            "rows": prediction_rows,
        },
        "prediction_label_history": prediction_rows,
        "false_missed_review": _false_missed_review_evidence(prediction_rows),
        "chv_action_status": chv_action_status,
        "outcome_feedback": _build_phase_7_outcome_feedback(
            ward=ward,
            related_alerts=related_alerts,
            prediction_rows=prediction_rows,
            chv_action_status=chv_action_status,
        ),
    }


def _display_choice(value: str | None) -> str:
    return str(value or "").replace("_", " ").replace("-", " ").title()


def _ward_centroid_for_spatial_evidence(ward: Ward):
    if ward.centroid is not None:
        return ward.centroid
    if ward.boundary is not None:
        return ward.boundary.centroid
    return None


def _latest_facility_forecasts_for_spatial_evidence(
    *,
    facility_ids: set[int],
    as_of,
) -> dict[int, FacilityForecast]:
    latest_by_facility_id: dict[int, FacilityForecast] = {}
    if not facility_ids:
        return latest_by_facility_id

    forecasts = (
        FacilityForecast.objects.filter(
            facility_id__in=facility_ids,
            generated_at__lt=as_of,
        )
        .select_related("facility", "forecast_run")
        .order_by("facility_id", "-generated_at", "-id")
    )
    for forecast in forecasts:
        latest_by_facility_id.setdefault(forecast.facility_id, forecast)
    return latest_by_facility_id


def _neighbor_surveillance_summary_for_spatial_evidence(
    *,
    neighbor_ward_ids: set[int],
    as_of,
) -> tuple[dict[int, dict], dict]:
    if not neighbor_ward_ids:
        return {}, {
            "record_count": 0,
            "active_outbreak_ward_ids": [],
            "suspected_case_trend_14d_delta": 0,
            "max_reporting_period_end": None,
            "max_record_created_at": None,
            "source_record_refs": [],
        }

    today = as_of.date()
    recent_start = today - timedelta(days=14)
    previous_start = today - timedelta(days=28)
    records = list(
        SurveillanceRecord.objects.filter(
            ward_id__in=neighbor_ward_ids,
            created_at__lt=as_of,
            reporting_period_end__lte=today,
            reporting_period_end__gte=previous_start,
        )
        .exclude(freshness_state=SurveillanceFreshnessState.REPLAY_DIAGNOSTIC)
        .select_related("ward", "source", "ingestion_run")
        .order_by("ward_id", "reporting_period_end", "id")
    )

    summary_by_ward: dict[int, dict] = {
        ward_id: {
            "record_count": 0,
            "suspected_cases_28d": 0,
            "suspected_case_trend_14d_delta": 0,
            "active_outbreak_label": False,
            "latest_reporting_period_end": None,
        }
        for ward_id in neighbor_ward_ids
    }
    active_outbreak_ward_ids = set()
    recent_suspected_total = 0
    previous_suspected_total = 0

    for record in records:
        ward_summary = summary_by_ward.setdefault(
            record.ward_id,
            {
                "record_count": 0,
                "suspected_cases_28d": 0,
                "suspected_case_trend_14d_delta": 0,
                "active_outbreak_label": False,
                "latest_reporting_period_end": None,
            },
        )
        ward_summary["record_count"] += 1
        if record.outbreak_label == SurveillanceOutbreakLabel.ACTIVE:
            ward_summary["active_outbreak_label"] = True
            active_outbreak_ward_ids.add(record.ward_id)
        if record.case_class == SurveillanceCaseClass.SUSPECTED:
            ward_summary["suspected_cases_28d"] += record.count_value
            if recent_start <= record.reporting_period_end <= today:
                ward_summary["suspected_case_trend_14d_delta"] += record.count_value
                recent_suspected_total += record.count_value
            elif previous_start <= record.reporting_period_end < recent_start:
                ward_summary["suspected_case_trend_14d_delta"] -= record.count_value
                previous_suspected_total += record.count_value
        latest_reporting_end = ward_summary["latest_reporting_period_end"]
        if latest_reporting_end is None or record.reporting_period_end > latest_reporting_end:
            ward_summary["latest_reporting_period_end"] = record.reporting_period_end

    for ward_summary in summary_by_ward.values():
        if ward_summary["latest_reporting_period_end"] is not None:
            ward_summary["latest_reporting_period_end"] = ward_summary[
                "latest_reporting_period_end"
            ].isoformat()

    latest_reporting_end = max((record.reporting_period_end for record in records), default=None)
    latest_created_at = max((record.created_at for record in records), default=None)
    return summary_by_ward, {
        "record_count": len(records),
        "active_outbreak_ward_ids": sorted(active_outbreak_ward_ids),
        "suspected_case_trend_14d_delta": recent_suspected_total - previous_suspected_total,
        "max_reporting_period_end": latest_reporting_end.isoformat() if latest_reporting_end else None,
        "max_record_created_at": latest_created_at.isoformat() if latest_created_at else None,
        "source_record_refs": [f"surveillance_record:{record.id}" for record in records],
        "source_filter": {
            "created_at": f"< {as_of.isoformat()}",
            "reporting_period_end": f"<= {today.isoformat()}",
            "lookback_start": previous_start.isoformat(),
        },
    }


def _nearest_facility_for_spatial_evidence(*, ward: Ward, as_of) -> dict | None:
    ward_centroid = _ward_centroid_for_spatial_evidence(ward)
    if ward_centroid is None:
        return None

    facilities = list(
        HealthFacility.objects.filter(
            is_active=True,
            point__isnull=False,
            ward__county__iexact=ward.county,
            created_at__lt=as_of,
        )
        .select_related("ward")
        .order_by("ward__name", "name", "id")
    )
    if not facilities:
        return None

    distance, facility = min(
        (
            (float(ward_centroid.distance(facility.point)), facility)
            for facility in facilities
            if facility.point is not None
        ),
        key=lambda item: (item[0], item[1].id),
    )
    return {
        "facility_id": facility.id,
        "facility_name": facility.name,
        "facility_code": facility.facility_code,
        "ward_id": facility.ward_id,
        "ward_name": facility.ward.name,
        "distance": distance,
        "distance_unit": "source_crs_degrees",
        "source_ref": f"health_facility:{facility.id}",
        "source_created_at": facility.created_at.isoformat() if facility.created_at else None,
    }


def _build_spatial_evidence_for_ward(
    *,
    ward: Ward,
    population_exposure_context: dict,
    as_of=None,
) -> dict:
    as_of = as_of or timezone.now()
    relationships = list(
        WardSpatialRelationship.objects.filter(
            source_ward=ward,
            target_ward__is_active=True,
            geometry_dataset_version__is_active=True,
            geometry_dataset_version__dataset__is_active=True,
            generated_at__lt=as_of,
        )
        .select_related("target_ward", "geometry_dataset_version", "geometry_dataset_version__dataset")
        .order_by("target_ward__name", "relationship_type", "-confidence", "id")
    )

    neighbor_context: dict[int, dict] = {}
    for relationship in relationships:
        context = neighbor_context.setdefault(
            relationship.target_ward_id,
            {
                "ward": relationship.target_ward,
                "relationship_types": [],
                "relationship_refs": [],
                "generation_methods": [],
                "approximation_notices": [],
                "is_approximate_relationship": False,
                "confidence": 0.0,
                "distance": None,
                "distance_unit": relationship.distance_unit,
                "geometry_dataset_ref": str(relationship.geometry_dataset_version),
                "max_relationship_generated_at": None,
            },
        )
        context["relationship_types"].append(relationship.relationship_type)
        context["relationship_refs"].append(f"ward_spatial_relationship:{relationship.id}")
        context["generation_methods"].append(relationship.generation_method)
        lineage_metadata = relationship.lineage_metadata if isinstance(relationship.lineage_metadata, dict) else {}
        approximation_notice = lineage_metadata.get("approximation_notice")
        if (
            relationship.generation_method == WardSpatialRelationshipSource.DERIVED_FACILITY_CATCHMENT
            or approximation_notice
        ):
            context["is_approximate_relationship"] = True
        if approximation_notice:
            context["approximation_notices"].append(approximation_notice)
        context["confidence"] = max(context["confidence"], relationship.confidence)
        if relationship.centroid_distance is not None:
            current_distance = context["distance"]
            context["distance"] = (
                relationship.centroid_distance
                if current_distance is None
                else min(current_distance, relationship.centroid_distance)
            )
        generated_at = relationship.generated_at
        if context["max_relationship_generated_at"] is None or generated_at > context["max_relationship_generated_at"]:
            context["max_relationship_generated_at"] = generated_at

    neighbor_ward_ids = set(neighbor_context)
    surveillance_by_ward, surveillance_lineage = _neighbor_surveillance_summary_for_spatial_evidence(
        neighbor_ward_ids=neighbor_ward_ids,
        as_of=as_of,
    )

    neighbor_items = []
    for ward_id, context in neighbor_context.items():
        target_ward = context["ward"]
        latest_risk = latest_promoted_riskscore_for_ward(target_ward)
        surveillance_summary = surveillance_by_ward.get(ward_id, {})
        neighbor_items.append(
            {
                "ward_id": target_ward.id,
                "ward_name": target_ward.name,
                "county": target_ward.county,
                "ward_code": target_ward.ward_code,
                "relationship_types": sorted(set(context["relationship_types"])),
                "relationship_labels": [_display_choice(item) for item in sorted(set(context["relationship_types"]))],
                "relationship_refs": context["relationship_refs"],
                "generation_methods": sorted(set(context["generation_methods"])),
                "is_approximate_relationship": context["is_approximate_relationship"],
                "approximation_notice": sorted(set(context["approximation_notices"]))[0]
                if context["approximation_notices"]
                else None,
                "confidence": round(context["confidence"], 3),
                "distance": context["distance"],
                "distance_unit": context["distance_unit"],
                "geometry_dataset_ref": context["geometry_dataset_ref"],
                "relationship_generated_at": (
                    context["max_relationship_generated_at"].isoformat()
                    if context["max_relationship_generated_at"]
                    else None
                ),
                "risk_level": latest_risk.risk_level if latest_risk else target_ward.current_risk_level,
                "risk_score": latest_risk.score if latest_risk else target_ward.current_risk_score,
                "predicted_cases": latest_risk.predicted_cases if latest_risk else 0,
                "risk_generated_at": latest_risk.generated_at.isoformat() if latest_risk else None,
                "risk_score_ref": f"risk_score:{latest_risk.id}" if latest_risk else None,
                "active_outbreak_label": bool(surveillance_summary.get("active_outbreak_label")),
                "suspected_cases_28d": surveillance_summary.get("suspected_cases_28d", 0),
                "suspected_case_trend_14d_delta": surveillance_summary.get(
                    "suspected_case_trend_14d_delta",
                    0,
                ),
                "surveillance_record_count_28d": surveillance_summary.get("record_count", 0),
                "latest_surveillance_reporting_period_end": surveillance_summary.get(
                    "latest_reporting_period_end"
                ),
            }
        )
    neighbor_items.sort(
        key=lambda item: (
            item["risk_level"] != Ward.RISK_HIGH,
            item["distance"] is None,
            item["distance"] if item["distance"] is not None else 999999,
            item["ward_name"],
        )
    )

    catchments = list(
        FacilityCatchment.objects.filter(
            covered_wards=ward,
            facility__is_active=True,
            geometry_dataset_version__is_active=True,
            geometry_dataset_version__dataset__is_active=True,
            generated_at__lt=as_of,
        )
        .select_related("facility", "primary_ward", "geometry_dataset_version", "geometry_dataset_version__dataset")
        .prefetch_related("covered_wards")
        .distinct()
        .order_by("facility__name", "-generated_at", "id")
    )
    facility_ids = {catchment.facility_id for catchment in catchments}
    forecasts_by_facility_id = _latest_facility_forecasts_for_spatial_evidence(
        facility_ids=facility_ids,
        as_of=as_of,
    )
    catchment_items = []
    for catchment in catchments:
        forecast = forecasts_by_facility_id.get(catchment.facility_id)
        catchment_items.append(
            {
                "catchment_id": catchment.id,
                "facility_id": catchment.facility_id,
                "facility_name": catchment.facility.name,
                "facility_code": catchment.facility.facility_code,
                "primary_ward_id": catchment.primary_ward_id,
                "primary_ward_name": catchment.primary_ward.name,
                "covered_ward_ids": sorted(catchment.covered_wards.values_list("id", flat=True)),
                "covered_ward_names": sorted(catchment.covered_wards.values_list("name", flat=True)),
                "catchment_method": catchment.catchment_method,
                "catchment_method_label": _display_choice(catchment.catchment_method),
                "source_kind": catchment.source_kind,
                "source_kind_label": _display_choice(catchment.source_kind),
                "is_approximate": catchment.is_approximate,
                "confidence": catchment.confidence,
                "population_estimate": catchment.population_estimate,
                "generated_at": catchment.generated_at.isoformat(),
                "projected_pressure_score": forecast.projected_pressure_score if forecast else None,
                "projected_readiness_state": forecast.projected_readiness_state if forecast else None,
                "projected_readiness_label": _display_choice(forecast.projected_readiness_state) if forecast else "Unavailable",
                "forecast_generated_at": forecast.generated_at.isoformat() if forecast else None,
                "forecast_ref": f"facility_forecast:{forecast.id}" if forecast else None,
                "source_ref": f"facility_catchment:{catchment.id}",
            }
        )

    nearest_facility = _nearest_facility_for_spatial_evidence(ward=ward, as_of=as_of)
    water_proximity = (population_exposure_context.get("values") or {}).get("water_body_proximity")
    high_risk_neighbors = [item for item in neighbor_items if item["risk_level"] == Ward.RISK_HIGH]
    active_outbreak_neighbor_count = len(
        {item["ward_id"] for item in neighbor_items if item["active_outbreak_label"]}
    )
    approximate_catchment_count = sum(1 for item in catchment_items if item["is_approximate"])
    max_catchment_pressure = max(
        (
            item["projected_pressure_score"]
            for item in catchment_items
            if item["projected_pressure_score"] is not None
        ),
        default=None,
    )
    nearest_high_risk_distance = min(
        (item["distance"] for item in high_risk_neighbors if item["distance"] is not None),
        default=None,
    )

    caveats = []
    if not relationships:
        caveats.append("No generated spatial relationship edges are available for this ward yet.")
    if any(item["is_approximate_relationship"] for item in neighbor_items):
        caveats.append(
            "Some spatial relationship edges are approximate catchment-derived links and should not be read as verified boundary adjacency."
        )
    if approximate_catchment_count:
        caveats.append("Some facility catchments are approximate and should be used as operational context only.")
    if water_proximity is None:
        caveats.append("Water proximity is unavailable from the current population exposure context.")

    return {
        "schema_version": "ward-spatial-evidence-v1",
        "ward_id": ward.id,
        "ward_name": ward.name,
        "as_of": as_of.isoformat(),
        "summary": {
            "neighbor_count": len(neighbor_items),
            "high_risk_neighbor_count": len(high_risk_neighbors),
            "active_outbreak_neighbor_count": active_outbreak_neighbor_count,
            "neighbor_suspected_case_trend_14d_delta": surveillance_lineage["suspected_case_trend_14d_delta"],
            "nearest_high_risk_distance": nearest_high_risk_distance,
            "nearest_facility_distance": nearest_facility["distance"] if nearest_facility else None,
            "nearest_facility_distance_unit": nearest_facility["distance_unit"] if nearest_facility else "source_crs_degrees",
            "catchment_facility_count": len(facility_ids),
            "approximate_catchment_count": approximate_catchment_count,
            "max_catchment_pressure_score": max_catchment_pressure,
            "water_proximity_available": water_proximity is not None,
            "water_proximity_value": water_proximity,
        },
        "neighbors": neighbor_items,
        "high_risk_neighbor_ward_ids": [item["ward_id"] for item in high_risk_neighbors],
        "active_outbreak_neighbor_ward_ids": surveillance_lineage["active_outbreak_ward_ids"],
        "facility_catchments": catchment_items,
        "nearest_facility": nearest_facility,
        "water_proximity": {
            "source_available": water_proximity is not None,
            "value": water_proximity,
            "display_caveat": "Water proximity is ward-level exposure context where source data exists.",
        },
        "lineage": {
            "relationship_refs": [
                ref for item in neighbor_items for ref in item["relationship_refs"]
            ],
            "relationship_filter": (
                f"source_ward={ward.id}, target_ward__is_active=True, active_geometry_version=True, "
                f"generated_at < {as_of.isoformat()}"
            ),
            "surveillance": surveillance_lineage,
            "facility_catchment_refs": [item["source_ref"] for item in catchment_items],
            "facility_forecast_refs": [
                item["forecast_ref"] for item in catchment_items if item["forecast_ref"]
            ],
            "population_exposure_snapshot_as_of": population_exposure_context.get("snapshot_as_of"),
        },
        "caveats": caveats,
    }


def build_ward_intelligence_snapshot(ward: Ward, *, stale_threshold_minutes: int = 120) -> dict:
    prefetched = getattr(ward, "_prefetched_objects_cache", {})
    if "risk_scores" in prefetched:
        risk_history = promoted_risk_scores(prefetched["risk_scores"])[:6]
    else:
        risk_history = promoted_risk_scores(
            ward.risk_scores.select_related("model_run").order_by("-generated_at")[:12]
        )[:6]
    related_alerts = list(
        ward.alerts.select_related("risk_score").order_by("-created_at")[:6]
    )
    latest_risk = risk_history[0] if risk_history else latest_riskscore_for_ward(ward)
    previous_risk = risk_history[1] if len(risk_history) > 1 else None
    population_exposure_context = build_population_exposure_context_for_ward(ward)
    surveillance_context = build_surveillance_feature_context_for_ward(ward)

    generated_at = latest_risk.generated_at if latest_risk else None
    is_stale = True
    if generated_at is not None:
        is_stale = (timezone.now() - generated_at).total_seconds() / 60 > stale_threshold_minutes

    current_risk = {
        "risk_level": latest_risk.risk_level if latest_risk else ward.current_risk_level,
        "risk_score": latest_risk.score if latest_risk else ward.current_risk_score,
        "predicted_cases": latest_risk.predicted_cases if latest_risk else 0,
        "decision_policy": latest_risk.decision_policy if latest_risk else {},
        "generated_at": generated_at,
        "source": latest_risk.source if latest_risk else None,
        "model_version": latest_risk.model_version if latest_risk else None,
        "model_run_status": latest_risk.model_run.status if latest_risk and latest_risk.model_run else None,
    }
    climate_evidence = _climate_alert_evidence_for_riskscore(latest_risk) if latest_risk else {}
    spatial_evidence = _build_spatial_evidence_for_ward(
        ward=ward,
        population_exposure_context=population_exposure_context,
    )

    if latest_risk and previous_risk:
        delta_points = round((latest_risk.score - previous_risk.score) * 100)
        if abs(delta_points) < 1:
            trend = {
                "label": "Stable versus previous run",
                "direction": "flat",
                "delta_points": 0,
                "mode": "derived_from_recent_history",
            }
        else:
            trend = {
                "label": f"{delta_points:+d} points vs previous run",
                "direction": "up" if delta_points > 0 else "down",
                "delta_points": delta_points,
                "mode": "derived_from_recent_history",
            }
    else:
        trend = {
            "label": "No previous run available",
            "direction": "flat",
            "delta_points": None,
            "mode": "derived_from_recent_history",
        }

    driver_items: list[dict] = []
    if latest_risk:
        if latest_risk.rainfall_mm > 80:
            climate_source_label = climate_evidence.get("observed_vs_forecast_source_label") or "Rainfall"
            climate_record_type = climate_evidence.get("record_type") or "rainfall"
            climate_source_provider = climate_evidence.get("source_provider") or "unavailable source"
            driver_items.append(
                {
                    "text": (
                        f"{climate_source_label} is elevated at {latest_risk.rainfall_mm:.0f} mm "
                        f"from {climate_source_provider} in the latest record."
                    ),
                    "tone": "warning" if climate_evidence.get("fallback_static_rainfall_used") else "critical",
                    "source_field": f"climate.{climate_record_type}",
                }
            )
        if climate_evidence.get("fallback_static_rainfall_used"):
            driver_items.append(
                {
                    "text": "Rainfall driver is using fallback static climate data, so it should not be treated as live forecast evidence.",
                    "tone": "warning",
                    "source_field": "climate.fallback_static",
                }
            )
        if latest_risk.flood_indicator > 0:
            driver_items.append(
                {
                    "text": "Flood indicator is elevated in the latest risk record.",
                    "tone": "warning",
                    "source_field": "flood_indicator",
                }
            )
        if latest_risk.predicted_cases > 0:
            driver_items.append(
                {
                    "text": f"Predicted cases are recorded at {latest_risk.predicted_cases} in the latest run.",
                    "tone": "info",
                    "source_field": "predicted_cases",
                }
            )
        if latest_risk.model_run:
            driver_items.append(
                {
                    "text": f"Latest model run status is {latest_risk.model_run.status.lower()}.",
                    "tone": "info",
                    "source_field": "model_run.status",
                }
            )

    for factor in population_exposure_context.get("factor_items", [])[:4]:
        mode = factor.get("mode") or ""
        driver_items.append(
            {
                "text": f"{factor.get('summary_text')} {factor.get('display_caveat')}",
                "tone": "warning" if "proxy" in mode or "seeded" in mode else "info",
                "source_field": f"population_exposure.{factor.get('factor_type')}",
            }
        )
    if surveillance_context["surveillance_recent_total_cases_28d"] > 0:
        driver_items.append(
            {
                "text": (
                    f"Surveillance context shows {surveillance_context['surveillance_recent_total_cases_28d']} "
                    "recent case records in the 28 day window."
                ),
                "tone": "warning",
                "source_field": "surveillance.recent_total_cases_28d",
            }
        )
    if surveillance_context["surveillance_latest_label_window_ref"]:
        driver_items.append(
            {
                "text": (
                    "Latest surveillance label window is "
                    f"{surveillance_context['surveillance_label_truth_state']} with freshness "
                    f"{surveillance_context['surveillance_latest_freshness_state'] or 'unknown'}."
                ),
                "tone": (
                    "info"
                    if surveillance_context["surveillance_label_truth_state"] == "confirmed_surveillance_truth"
                    else "warning"
                ),
                "source_field": "surveillance.latest_label_window",
            }
        )
    spatial_summary = spatial_evidence["summary"]
    if spatial_summary["high_risk_neighbor_count"] > 0:
        driver_items.append(
            {
                "text": (
                    f"{spatial_summary['high_risk_neighbor_count']} neighboring ward"
                    f"{'' if spatial_summary['high_risk_neighbor_count'] == 1 else 's'} "
                    "are currently high risk in the spatial relationship graph."
                ),
                "tone": "warning",
                "source_field": "spatial.neighboring_high_risk_wards",
            }
        )
    if spatial_summary["active_outbreak_neighbor_count"] > 0:
        driver_items.append(
            {
                "text": (
                    f"{spatial_summary['active_outbreak_neighbor_count']} neighboring ward"
                    f"{'' if spatial_summary['active_outbreak_neighbor_count'] == 1 else 's'} "
                    "have active outbreak surveillance labels in the current lookback window."
                ),
                "tone": "warning",
                "source_field": "spatial.neighboring_outbreak_labels",
            }
        )
    if spatial_summary["max_catchment_pressure_score"] is not None:
        driver_items.append(
            {
                "text": (
                    "Facility catchment pressure is "
                    f"{spatial_summary['max_catchment_pressure_score']}/100 across covered facilities."
                ),
                "tone": "warning" if spatial_summary["max_catchment_pressure_score"] >= 75 else "info",
                "source_field": "spatial.catchment_facility_pressure",
            }
        )

    driver_summary = {
        "mode": "derived_from_latest_record" if latest_risk else "unavailable",
        "items": driver_items
        or [
            {
                "text": "No recent driver summary is available from the latest ward record yet.",
                "tone": "info",
                "source_field": None,
            }
        ],
    }

    current_risk_level = current_risk["risk_level"] or "UNKNOWN"
    if current_risk_level == Ward.RISK_HIGH:
        guidance_items = [
            "Send CHV alert using the supported trigger flow.",
            "Review hygiene and safe-water messaging readiness for this ward.",
            "Check ORS and dehydration-response readiness before case pressure rises.",
            "Watch the next model run and linked alerts closely for escalation.",
        ]
    elif current_risk_level == Ward.RISK_MEDIUM:
        guidance_items = [
            "Increase review cadence for the next ward update.",
            "Prepare outreach messaging in case this ward escalates.",
            "Confirm local readiness for rapid response if alert volume rises.",
        ]
    elif current_risk_level == Ward.RISK_LOW:
        guidance_items = [
            "Continue routine surveillance for this ward.",
            "Monitor for score movement in the next model run.",
            "Keep reporting continuity in place so risk changes are visible early.",
        ]
    else:
        guidance_items = [
            "Continue monitoring until a fresher ward record is available.",
            "Review the next model run before taking new action from this page.",
        ]
    if population_exposure_context["coverage"]["record_count"]:
        guidance_items.append(
            "Use population and exposure values as baseline/proxy context with lineage, not exact census or exposure truth."
        )
    if surveillance_context["surveillance_proxy_only_label_window_count_28d"] > 0:
        guidance_items.append(
            "Treat proxy-only surveillance label windows as weak evidence and avoid calling them confirmed outbreaks."
        )
    if spatial_evidence["summary"]["high_risk_neighbor_count"] > 0:
        guidance_items.append("Review spatial spillover context before deciding whether this ward needs follow-up.")
    if spatial_evidence["summary"]["approximate_catchment_count"] > 0:
        guidance_items.append(
            "Treat approximate facility catchments as planning context, not verified service-area truth."
        )

    guidance_summary = {
        "mode": "static_risk_playbook",
        "items": [
            {"text": text, "urgency": "review_only" if index else "primary"}
            for index, text in enumerate(guidance_items)
        ],
    }

    freshness = {
        "generated_at": generated_at,
        "is_stale": is_stale,
        "stale_threshold_minutes": stale_threshold_minutes,
        "history_count": len(risk_history),
        "alert_count": len(related_alerts),
        "mode": "timestamp_and_record_availability",
    }
    workflow = sync_alert_workflow_for_ward(ward, record_event=False)
    operational_evidence = _build_phase_6_operational_evidence(
        ward=ward,
        latest_risk=latest_risk,
        risk_history=risk_history,
        current_risk=current_risk,
        freshness=freshness,
        workflow=workflow,
        related_alerts=related_alerts,
        population_exposure_context=population_exposure_context,
        surveillance_context=surveillance_context,
        climate_evidence=climate_evidence,
    )

    return {
        "ward": ward,
        "current_risk": current_risk,
        "trend": trend,
        "driver_summary": driver_summary,
        "guidance_summary": guidance_summary,
        "freshness": freshness,
        "workflow": _ward_workflow_summary(workflow),
        "decision_summary": _ward_decision_summary_for_workflow(workflow),
        "header_context": _ward_header_context(ward, workflow, current_risk, freshness, related_alerts),
        "population_exposure": population_exposure_context,
        "surveillance": surveillance_context,
        "spatial_evidence": spatial_evidence,
        "operational_evidence": operational_evidence,
        "risk_history": risk_history,
        "related_alerts": related_alerts,
    }


def _facility_surge_risk(level: str | None) -> str:
    if level == Ward.RISK_HIGH:
        return "EXTREME"
    if level == Ward.RISK_MEDIUM:
        return "MODERATE"
    return "LOW"


def _facility_ors_state(percent: int) -> str:
    if percent < 30:
        return "CRITICAL"
    if percent < 75:
        return "STABLE"
    return "READY"


def _facility_format_type(facility: HealthFacility) -> str:
    label = facility.facility_type.replace("_", " ").lower()
    level = facility.level.replace("_", " ").replace("LEVEL ", "Level ")
    return f"{level} {label}".title()


def _facility_freshness_state(updated_at, *, warning_minutes: int = 30, stale_minutes: int = 120) -> str:
    if not updated_at:
        return "STALE"
    minutes = max(0, round((timezone.now() - updated_at).total_seconds() / 60))
    if minutes > stale_minutes:
        return "STALE"
    if minutes > warning_minutes:
        return "WARNING"
    return "FRESH"


def _facility_user_can_request_update(user) -> bool:
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    return bool(
        getattr(user, "is_superuser", False)
        or getattr(user, "role", None) in {"ADMIN", "SUPERVISOR"}
    )


def _facility_user_can_escalate_county_review(user) -> bool:
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    return bool(getattr(user, "is_superuser", False) or getattr(user, "role", None) == "ADMIN")


def _facility_has_county_review_queue() -> bool:
    return True


def _facility_user_can_open_chv_operations(user) -> bool:
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    return bool(
        getattr(user, "is_superuser", False)
        or getattr(user, "role", None) in {"ADMIN", "SUPERVISOR"}
    )


def _can_view_direct_identifiers_for_service_user(user) -> bool:
    return user_can_view_direct_identifiers(user)


def _contact_value_for_service_user(value: str, user) -> str:
    if _can_view_direct_identifiers_for_service_user(user):
        return value
    return mask_contact_value(value)


def _text_value_for_service_user(value: str, user) -> str:
    return redact_direct_identifiers_in_text(
        value,
        can_view=_can_view_direct_identifiers_for_service_user(user),
    )


def _facility_linked_alert_payload(alert: Alert, *, user=None) -> dict:
    return {
        "id": alert.id,
        "public_id": str(alert.public_id),
        "ward_id": alert.ward_id,
        "ward_name": alert.ward.name,
        "status": alert.status,
        "channel": alert.channel,
        "recipient": _contact_value_for_service_user(alert.recipient, user),
        "risk_score": alert.risk_score.score if alert.risk_score else None,
        "created_at": alert.created_at,
        "sent_at": alert.sent_at,
        "api_url": f"/api/v1/alerts/{alert.id}/",
        "intelligence_api_url": f"/api/v1/alerts/{alert.id}/intelligence/",
        "dashboard_url": f"/alerts/{alert.id}",
        "filtered_alerts_url": f"/alerts?ward_id={alert.ward_id}",
    }


def _facility_chv_operations_navigation_payload(
    facility: HealthFacility,
    *,
    user,
) -> dict:
    active_chv_count = CHV.objects.filter(ward=facility.ward, is_active=True).count()
    total_chv_count = CHV.objects.filter(ward=facility.ward).count()
    can_open = (
        _facility_user_can_open_chv_operations(user)
        and active_chv_count > 0
    )

    return {
        "available": can_open,
        "ward_id": facility.ward_id,
        "ward_name": facility.ward.name,
        "active_chv_count": active_chv_count,
        "total_chv_count": total_chv_count,
        "api_url": f"/api/v1/chvs/operations/?ward_id={facility.ward_id}",
        "dashboard_url": f"/chvs?ward_id={facility.ward_id}#chv-registry",
        "mode": "chv_operations_deep_link_only",
        "message": (
            "Open CHV Operations to review ward-linked CHVs. "
            "Facility Readiness does not send CHV messages directly."
        ),
    }


def _facility_review_severity_from_reason_codes(reason_codes: list[str]) -> str:
    if FACILITY_READINESS_REASON_HIGH_READINESS_DIFFERENCE in reason_codes:
        return FacilityReadinessReview.SEVERITY_HIGH
    if any(
        code in reason_codes
        for code in {
            FACILITY_READINESS_REASON_MODERATE_READINESS_DIFFERENCE,
            FACILITY_READINESS_REASON_ELEVATED_WARD_RISK,
            FACILITY_READINESS_REASON_MULTIPLE_ALERTS_IN_WARD,
            FACILITY_READINESS_REASON_FORECAST_PRESSURE_ELEVATED,
        }
    ):
        return FacilityReadinessReview.SEVERITY_MEDIUM
    return FacilityReadinessReview.SEVERITY_LOW


def active_facility_readiness_review_for_facility(facility: HealthFacility) -> FacilityReadinessReview | None:
    return (
        FacilityReadinessReview.objects.filter(
            facility=facility,
            status__in=FacilityReadinessReview.ACTIVE_STATUSES,
        )
        .select_related("facility", "ward", "created_by", "assigned_to")
        .prefetch_related("events__actor")
        .order_by("-created_at")
        .first()
    )


def verified_facility_contact_for_facility(facility: HealthFacility) -> FacilityContact | None:
    return (
        FacilityContact.objects.filter(facility=facility, is_active=True, is_verified=True)
        .order_by("-verified_at", "-updated_at")
        .first()
    )


def active_facility_readiness_update_request_for_review(
    review: FacilityReadinessReview,
) -> FacilityReadinessUpdateRequest | None:
    return (
        FacilityReadinessUpdateRequest.objects.filter(
            review=review,
            status__in=FacilityReadinessUpdateRequest.ACTIVE_STATUSES,
        )
        .select_related("review", "facility", "contact", "requested_by")
        .order_by("-requested_at", "-created_at")
        .first()
    )


def active_facility_readiness_update_request_for_facility(
    facility: HealthFacility,
) -> FacilityReadinessUpdateRequest | None:
    return (
        FacilityReadinessUpdateRequest.objects.filter(
            facility=facility,
            status__in=FacilityReadinessUpdateRequest.ACTIVE_STATUSES,
        )
        .select_related("review", "facility", "contact", "requested_by")
        .order_by("-requested_at", "-created_at")
        .first()
    )


def active_facility_readiness_escalation_for_review(
    review: FacilityReadinessReview,
) -> FacilityReadinessEscalation | None:
    return (
        FacilityReadinessEscalation.objects.filter(
            review=review,
            status__in=FacilityReadinessEscalation.ACTIVE_STATUSES,
        )
        .select_related("review", "facility", "ward", "created_by", "acknowledged_by", "assigned_to")
        .order_by("-created_at")
        .first()
    )


def active_facility_readiness_escalation_for_facility(
    facility: HealthFacility,
) -> FacilityReadinessEscalation | None:
    return (
        FacilityReadinessEscalation.objects.filter(
            facility=facility,
            status__in=FacilityReadinessEscalation.ACTIVE_STATUSES,
        )
        .select_related("review", "facility", "ward", "created_by", "acknowledged_by", "assigned_to")
        .order_by("-created_at")
        .first()
    )


def _facility_review_reason_codes_from_snapshot(snapshot: dict) -> list[str]:
    priorities = snapshot.get("decision_summary", {}).get("top_priorities") or []
    if priorities:
        return list(dict.fromkeys(priorities[0].get("reason_codes") or []))
    return []


def record_facility_readiness_review_event(
    review: FacilityReadinessReview,
    *,
    actor=None,
    action: str,
    old_status: str = "",
    new_status: str = "",
    detail: str = "",
    metadata: dict | None = None,
) -> FacilityReadinessReviewEvent:
    return FacilityReadinessReviewEvent.objects.create(
        review=review,
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        action=action,
        old_status=old_status,
        new_status=new_status,
        detail=detail,
        metadata=metadata or {},
    )


@transaction.atomic
def create_facility_readiness_review(
    *,
    facility: HealthFacility,
    actor=None,
    notes: str = "",
    decision_summary_snapshot: dict | None = None,
) -> FacilityReadinessReview:
    if active_facility_readiness_review_for_facility(facility) is not None:
        raise ValueError("An active readiness review already exists for this facility.")

    snapshot = decision_summary_snapshot or build_facility_intelligence_snapshot(facility, user=actor)
    reason_codes = _facility_review_reason_codes_from_snapshot(snapshot)
    review = FacilityReadinessReview.objects.create(
        facility=facility,
        ward=facility.ward,
        status=FacilityReadinessReview.STATUS_OPEN,
        severity=_facility_review_severity_from_reason_codes(reason_codes),
        reason_codes=reason_codes,
        decision_summary_snapshot=snapshot.get("decision_summary", {}),
        created_by=actor if getattr(actor, "is_authenticated", False) else None,
        notes=notes.strip(),
    )
    record_facility_readiness_review_event(
        review,
        actor=actor,
        action=FacilityReadinessReviewEvent.ACTION_CREATED,
        new_status=FacilityReadinessReview.STATUS_OPEN,
        detail="Readiness review opened.",
        metadata={"reason_codes": reason_codes},
    )
    return review


@transaction.atomic
def transition_facility_readiness_review(
    review: FacilityReadinessReview,
    *,
    actor=None,
    status: str,
    notes: str = "",
) -> FacilityReadinessReview:
    old_status = review.status
    valid_statuses = {
        FacilityReadinessReview.STATUS_ACKNOWLEDGED,
        FacilityReadinessReview.STATUS_RESOLVED,
        FacilityReadinessReview.STATUS_DISMISSED,
    }
    if status not in valid_statuses:
        raise ValueError("Unsupported readiness review status transition.")
    if old_status in {FacilityReadinessReview.STATUS_RESOLVED, FacilityReadinessReview.STATUS_DISMISSED}:
        raise ValueError("Closed readiness reviews cannot be changed.")
    if status == FacilityReadinessReview.STATUS_ACKNOWLEDGED and old_status != FacilityReadinessReview.STATUS_OPEN:
        raise ValueError("Only open readiness reviews can be acknowledged.")

    now = timezone.now()
    review.status = status
    if notes.strip():
        review.notes = notes.strip()
    update_fields = ["status", "updated_at", "notes"]

    if status == FacilityReadinessReview.STATUS_ACKNOWLEDGED:
        review.acknowledged_at = now
        update_fields.append("acknowledged_at")
        action = FacilityReadinessReviewEvent.ACTION_ACKNOWLEDGED
        detail = "Readiness review marked as reviewed."
    elif status == FacilityReadinessReview.STATUS_RESOLVED:
        review.resolved_at = now
        update_fields.append("resolved_at")
        action = FacilityReadinessReviewEvent.ACTION_RESOLVED
        detail = "Readiness review resolved."
    else:
        review.dismissed_at = now
        update_fields.append("dismissed_at")
        action = FacilityReadinessReviewEvent.ACTION_DISMISSED
        detail = "Readiness review dismissed."

    review.save(update_fields=update_fields)
    record_facility_readiness_review_event(
        review,
        actor=actor,
        action=action,
        old_status=old_status,
        new_status=status,
        detail=notes.strip() or detail,
    )
    return review


def acknowledge_facility_readiness_review(
    review: FacilityReadinessReview,
    *,
    actor=None,
    notes: str = "",
) -> FacilityReadinessReview:
    return transition_facility_readiness_review(
        review,
        actor=actor,
        status=FacilityReadinessReview.STATUS_ACKNOWLEDGED,
        notes=notes,
    )


def _default_facility_update_request_message(review: FacilityReadinessReview) -> str:
    reason_codes = ", ".join(review.reason_codes or []) or "readiness review"
    return (
        f"Please update readiness status for {review.facility.name}: ORS stock, staffing, "
        f"bed/capacity notes, and any urgent constraints. Reason: {reason_codes}."
    )


def create_facility_readiness_update_request(
    review: FacilityReadinessReview,
    *,
    actor=None,
    message_body: str = "",
    channel: str | None = None,
    emergency_override: bool = False,
    override_reason: str = "",
    template_key: str = "",
    template_version: int | None = None,
    template_language: str = "en",
    template_context: dict | None = None,
) -> FacilityReadinessUpdateRequest:
    if review.status not in FacilityReadinessReview.ACTIVE_STATUSES:
        raise ValueError("Facility update requests require an active readiness review.")

    if active_facility_readiness_update_request_for_review(review) is not None:
        raise ValueError("An active facility update request already exists for this review.")

    if active_facility_readiness_update_request_for_facility(review.facility) is not None:
        raise ValueError("An active facility update request already exists for this facility.")

    contact = verified_facility_contact_for_facility(review.facility)
    if contact is None:
        raise ValueError("A verified facility contact is required before requesting a facility update.")

    resolved_channel = channel or contact.preferred_channel or FacilityReadinessUpdateRequest.CHANNEL_SMS
    valid_channels = {choice[0] for choice in FacilityReadinessUpdateRequest.CHANNEL_CHOICES}
    if resolved_channel not in valid_channels:
        raise ValueError("Unsupported facility update request channel.")

    audience_scope = _assert_facility_contact_scope(contact, actor)
    preference, audience_decision = authorize_contact_message(
        audience_type=ContactPreference.AUDIENCE_FACILITY_CONTACT,
        channel=resolved_channel,
        phone_number=contact.phone if resolved_channel == FacilityReadinessUpdateRequest.CHANNEL_SMS else "",
        contact_reference=contact_reference_for_facility_contact(contact),
        actor=actor,
        emergency_override=emergency_override,
        override_reason=override_reason,
        audit_allowed=True,
        metadata={
            "workflow": "facility_readiness_update_request",
            "facility_id": review.facility_id,
            "review_public_id": str(review.public_id),
            "contact_public_id": str(contact.public_id),
            "audience_scope": audience_scope,
        },
        message_purpose=MESSAGE_PURPOSE_FACILITY_UPDATE,
    )

    rendered_template = None
    body = message_body.strip()
    if template_key:
        if resolved_channel != FacilityReadinessUpdateRequest.CHANNEL_SMS:
            raise ValueError("Template-rendered facility update requests currently support SMS delivery only.")
        rendered_template = render_message_template(
            template_key=template_key,
            version=template_version,
            language=template_language,
            context=_template_context_for_facility_update(review, template_context),
            audience_type=MessageTemplate.AUDIENCE_FACILITY_CONTACT,
            channel=MessageTemplate.CHANNEL_SMS,
        )
        if body and body != rendered_template.body:
            raise ValueError("Template-rendered facility update requests cannot also override message_body.")
        body = rendered_template.body
    if not body:
        body = _default_facility_update_request_message(review)

    template_snapshot = _message_template_snapshot(rendered_template)
    with transaction.atomic():
        update_request = FacilityReadinessUpdateRequest.objects.create(
            review=review,
            facility=review.facility,
            contact=contact,
            requested_by=actor if getattr(actor, "is_authenticated", False) else None,
            channel=resolved_channel,
            message_body=body,
            **template_snapshot,
            governance_metadata=_message_delivery_governance_metadata(
                rendered_template=rendered_template,
                audience_decision=audience_decision,
                audience_scope=audience_scope,
                workflow="facility_readiness_update_request",
                extra={
                    "facility_id": review.facility_id,
                    "review_public_id": str(review.public_id),
                    "contact_public_id": str(contact.public_id),
                },
            ),
            status=FacilityReadinessUpdateRequest.STATUS_QUEUED,
        )
        record_facility_readiness_review_event(
            review,
            actor=actor,
            action=FacilityReadinessReviewEvent.ACTION_UPDATE_REQUEST_CREATED,
            old_status=review.status,
            new_status=review.status,
            detail="Facility update request queued.",
            metadata={
                "update_request_public_id": str(update_request.public_id),
                "update_request_status": update_request.status,
                "channel": update_request.channel,
                "delivery_mode": "queued_only",
                "contact_public_id": str(contact.public_id),
                "contact_preference_public_id": str(preference.public_id) if preference else "",
                "emergency_override": bool(emergency_override),
                "override_reason": override_reason.strip() if emergency_override else "",
                "message_template": template_reference(rendered_template.template) if rendered_template else {},
            },
        )
    return update_request


def _default_facility_readiness_escalation_reason(review: FacilityReadinessReview) -> str:
    reason_codes = ", ".join(review.reason_codes or []) or "readiness review"
    return f"County review requested for {review.facility.name}. Reason: {reason_codes}."


@transaction.atomic
def create_facility_readiness_escalation(
    review: FacilityReadinessReview,
    *,
    actor=None,
    reason: str = "",
    severity: str | None = None,
    assigned_to=None,
) -> FacilityReadinessEscalation:
    if review.status not in FacilityReadinessReview.ACTIVE_STATUSES:
        raise ValueError("County review escalation requires an active readiness review.")

    if active_facility_readiness_escalation_for_review(review) is not None:
        raise ValueError("An active county review escalation already exists for this review.")

    if active_facility_readiness_escalation_for_facility(review.facility) is not None:
        raise ValueError("An active county review escalation already exists for this facility.")

    resolved_severity = severity or review.severity
    valid_severities = {choice[0] for choice in FacilityReadinessEscalation.SEVERITY_CHOICES}
    if resolved_severity not in valid_severities:
        raise ValueError("Unsupported county review escalation severity.")

    escalation = FacilityReadinessEscalation.objects.create(
        review=review,
        facility=review.facility,
        ward=review.ward,
        status=FacilityReadinessEscalation.STATUS_OPEN,
        severity=resolved_severity,
        reason=reason.strip() or _default_facility_readiness_escalation_reason(review),
        created_by=actor if getattr(actor, "is_authenticated", False) else None,
        assigned_to=assigned_to,
    )
    record_facility_readiness_review_event(
        review,
        actor=actor,
        action=FacilityReadinessReviewEvent.ACTION_ESCALATION_CREATED,
        old_status=review.status,
        new_status=review.status,
        detail="County review escalation opened.",
        metadata={
            "escalation_public_id": str(escalation.public_id),
            "escalation_status": escalation.status,
            "severity": escalation.severity,
            "assigned_to": escalation.assigned_to_id,
            "queue_mode": "county_review_queue",
        },
    )
    return escalation


@transaction.atomic
def transition_facility_readiness_escalation(
    escalation: FacilityReadinessEscalation,
    *,
    actor=None,
    status: str,
    notes: str = "",
    assigned_to=None,
) -> FacilityReadinessEscalation:
    old_status = escalation.status
    valid_statuses = {
        FacilityReadinessEscalation.STATUS_ACKNOWLEDGED,
        FacilityReadinessEscalation.STATUS_RESOLVED,
        FacilityReadinessEscalation.STATUS_DISMISSED,
    }
    if status not in valid_statuses:
        raise ValueError("Unsupported county review escalation status transition.")
    if old_status in {
        FacilityReadinessEscalation.STATUS_RESOLVED,
        FacilityReadinessEscalation.STATUS_DISMISSED,
    }:
        raise ValueError("Closed county review escalations cannot be changed.")
    if status == FacilityReadinessEscalation.STATUS_ACKNOWLEDGED and old_status != FacilityReadinessEscalation.STATUS_OPEN:
        raise ValueError("Only open county review escalations can be acknowledged.")

    now = timezone.now()
    escalation.status = status
    if notes.strip():
        escalation.notes = notes.strip()
    update_fields = ["status", "updated_at", "notes"]

    if status == FacilityReadinessEscalation.STATUS_ACKNOWLEDGED:
        escalation.acknowledged_at = now
        escalation.acknowledged_by = actor if getattr(actor, "is_authenticated", False) else None
        escalation.assigned_to = assigned_to or escalation.assigned_to or escalation.acknowledged_by
        update_fields.extend(["acknowledged_at", "acknowledged_by", "assigned_to"])
        action = FacilityReadinessReviewEvent.ACTION_ESCALATION_ACKNOWLEDGED
        detail = "County review escalation acknowledged."
    elif status == FacilityReadinessEscalation.STATUS_RESOLVED:
        escalation.resolved_at = now
        update_fields.append("resolved_at")
        action = FacilityReadinessReviewEvent.ACTION_ESCALATION_RESOLVED
        detail = "County review escalation resolved."
    else:
        escalation.dismissed_at = now
        update_fields.append("dismissed_at")
        action = FacilityReadinessReviewEvent.ACTION_ESCALATION_DISMISSED
        detail = "County review escalation dismissed."

    escalation.save(update_fields=update_fields)
    record_facility_readiness_review_event(
        escalation.review,
        actor=actor,
        action=action,
        old_status=old_status,
        new_status=status,
        detail=notes.strip() or detail,
        metadata={
            "escalation_public_id": str(escalation.public_id),
            "assigned_to": escalation.assigned_to_id,
        },
    )
    return escalation


def _facility_readiness_decision_confidence_reason(*, is_stale: bool, readiness_backing_source: str) -> str | None:
    weak_proxy_inputs = readiness_backing_source == "unavailable"

    if is_stale and weak_proxy_inputs:
        return "stale_and_weak_proxy_inputs"
    if is_stale:
        return "stale_inputs"
    if weak_proxy_inputs:
        return "weak_proxy_inputs"
    return None


def _build_facility_readiness_reason_codes(
    *,
    ward_risk_level: str | None,
    ward_alert_count: int,
    surge_risk: str,
    forecast_source_kind: str,
    confidence_reason: str | None,
) -> list[str]:
    codes: list[str] = []

    if confidence_reason in {"stale_inputs", "stale_and_weak_proxy_inputs"}:
        codes.append(FACILITY_READINESS_REASON_STALE_INPUTS)
    if confidence_reason in {"weak_proxy_inputs", "stale_and_weak_proxy_inputs"}:
        codes.append(FACILITY_READINESS_REASON_WEAK_PROXY_INPUTS)
    if ward_risk_level in {Ward.RISK_MEDIUM, Ward.RISK_HIGH}:
        codes.append(FACILITY_READINESS_REASON_ELEVATED_WARD_RISK)
    if ward_alert_count >= 2:
        codes.append(FACILITY_READINESS_REASON_MULTIPLE_ALERTS_IN_WARD)
    if forecast_source_kind in {"promoted_forecast", "forecast_preview"} and surge_risk in {"EXTREME", "MODERATE"}:
        codes.append(FACILITY_READINESS_REASON_FORECAST_PRESSURE_ELEVATED)
    if not codes:
        codes.append(FACILITY_READINESS_REASON_CALM_VISIBLE_SCOPE)

    return codes


def _build_initial_facility_readiness_decision_summary(
    *,
    facility: HealthFacility,
    ward_risk_level: str | None,
    surge_risk: str,
    readiness_backing_source: str,
    ward_alert_count: int,
    forecast_source_kind: str,
    is_stale: bool,
) -> dict:
    confidence_reason = _facility_readiness_decision_confidence_reason(
        is_stale=is_stale,
        readiness_backing_source=readiness_backing_source,
    )
    confidence = (
        FACILITY_READINESS_DECISION_CONFIDENCE_DEGRADED
        if confidence_reason is not None
        else FACILITY_READINESS_DECISION_CONFIDENCE_NORMAL
    )

    if confidence == FACILITY_READINESS_DECISION_CONFIDENCE_DEGRADED:
        state = FACILITY_READINESS_DECISION_STATE_DEGRADED_CONFIDENCE
        headline = "Decision confidence is degraded for this facility."
        body = (
            "Use this readiness detail for review only. Inputs are stale or still rely on weak proxy readiness signals."
        )
    elif ward_risk_level in {Ward.RISK_MEDIUM, Ward.RISK_HIGH} or ward_alert_count > 0 or surge_risk in {"EXTREME", "MODERATE"}:
        state = FACILITY_READINESS_DECISION_STATE_REVIEW
        headline = "Review this facility's readiness detail next."
        body = "This facility shows backend signals that justify closer readiness review before acting elsewhere."
    else:
        state = FACILITY_READINESS_DECISION_STATE_CALM
        headline = "No immediate facility-readiness concern is visible here."
        body = "Continue routine review unless newer risk, alert, or forecasting signals arrive."

    reason_codes = _build_facility_readiness_reason_codes(
        ward_risk_level=ward_risk_level,
        ward_alert_count=ward_alert_count,
        surge_risk=surge_risk,
        forecast_source_kind=forecast_source_kind,
        confidence_reason=confidence_reason,
    )
    reason_text_map = {
        FACILITY_READINESS_REASON_STALE_INPUTS: "stale backend inputs",
        FACILITY_READINESS_REASON_WEAK_PROXY_INPUTS: "weak proxy readiness backing",
        FACILITY_READINESS_REASON_ELEVATED_WARD_RISK: "elevated ward risk",
        FACILITY_READINESS_REASON_MULTIPLE_ALERTS_IN_WARD: "multiple ward-linked alerts",
        FACILITY_READINESS_REASON_FORECAST_PRESSURE_ELEVATED: "forecast-backed pressure elevation",
        FACILITY_READINESS_REASON_CALM_VISIBLE_SCOPE: "no elevated backend review signals",
    }
    reason_text = ", ".join(reason_text_map.get(code, code.lower()) for code in reason_codes)

    return {
        "state": state,
        "headline": headline,
        "body": body,
        "confidence": confidence,
        "confidence_reason": confidence_reason,
        "total_review_facility_count": 1 if state != FACILITY_READINESS_DECISION_STATE_CALM else 0,
        "top_priorities": [
            {
                "facility_id": facility.id,
                "facility_name": facility.name,
                "ward_id": facility.ward_id,
                "ward_name": facility.ward.name,
                "priority_rank": 1,
                "priority_label": "Current facility",
                "reason_codes": reason_codes,
                "reason_text": reason_text[:1].upper() + reason_text[1:] + ".",
                "review_href": None,
            }
        ],
        "related_surfaces": {
            "has_linked_alerts": ward_alert_count > 0,
            "linked_alert_count": ward_alert_count,
        },
    }


def _facility_readiness_difference_score_from_snapshot(snapshot: dict) -> int:
    readiness = snapshot["readiness"]
    ors_gap = max(0, 100 - int(readiness["ors_estimate_percent"]))
    staffing_gap = max(0, 100 - int(readiness["staffing_percent"]))
    surge_weight = 15 if readiness["surge_risk"] == "EXTREME" else 8 if readiness["surge_risk"] == "MODERATE" else 0
    return round((ors_gap * 0.55) + (staffing_gap * 0.35) + surge_weight)


def _facility_readiness_difference_reason_code(score: int) -> str | None:
    if score >= 55:
        return FACILITY_READINESS_REASON_HIGH_READINESS_DIFFERENCE
    if score >= 30:
        return FACILITY_READINESS_REASON_MODERATE_READINESS_DIFFERENCE
    return None


def _facility_readiness_priority_bucket(snapshot: dict, readiness_difference_reason: str | None) -> int:
    readiness = snapshot["readiness"]
    context = snapshot["context"]
    freshness = snapshot["freshness"]
    forecasting = snapshot["forecasting"]
    ward_risk_score = float(context["ward_risk_score"] or 0.0)

    if freshness["is_stale"] and readiness_difference_reason == FACILITY_READINESS_REASON_HIGH_READINESS_DIFFERENCE:
        return 0
    if readiness_difference_reason == FACILITY_READINESS_REASON_HIGH_READINESS_DIFFERENCE:
        return 1
    if forecasting["source_kind"] in {"promoted_forecast", "forecast_preview"} and readiness["surge_risk"] in {"EXTREME", "MODERATE"}:
        return 2
    if ward_risk_score >= 0.6:
        return 3
    return 4


def _facility_readiness_priority_reason_codes(snapshot: dict, readiness_difference_reason: str | None) -> list[str]:
    readiness = snapshot["readiness"]
    context = snapshot["context"]
    freshness = snapshot["freshness"]
    forecasting = snapshot["forecasting"]
    ward_risk_score = float(context["ward_risk_score"] or 0.0)
    ward_risk_level = Ward.RISK_HIGH if ward_risk_score >= 0.75 else Ward.RISK_MEDIUM if ward_risk_score >= 0.45 else Ward.RISK_LOW

    confidence_reason = _facility_readiness_decision_confidence_reason(
        is_stale=bool(freshness["is_stale"]),
        readiness_backing_source=readiness["backing_source"],
    )
    codes = _build_facility_readiness_reason_codes(
        ward_risk_level=ward_risk_level,
        ward_alert_count=int(context["ward_alert_count"]),
        surge_risk=readiness["surge_risk"],
        forecast_source_kind=forecasting["source_kind"],
        confidence_reason=confidence_reason,
    )
    if readiness_difference_reason is not None:
        codes = [readiness_difference_reason, *codes]
    return list(dict.fromkeys(codes))


def _facility_readiness_reason_text(reason_codes: list[str]) -> str:
    reason_text_map = {
        FACILITY_READINESS_REASON_HIGH_READINESS_DIFFERENCE: "high calculated readiness difference",
        FACILITY_READINESS_REASON_MODERATE_READINESS_DIFFERENCE: "moderate calculated readiness difference",
        FACILITY_READINESS_REASON_STALE_INPUTS: "stale backend inputs",
        FACILITY_READINESS_REASON_WEAK_PROXY_INPUTS: "weak proxy readiness backing",
        FACILITY_READINESS_REASON_ELEVATED_WARD_RISK: "elevated ward risk",
        FACILITY_READINESS_REASON_MULTIPLE_ALERTS_IN_WARD: "multiple ward-linked alerts",
        FACILITY_READINESS_REASON_FORECAST_PRESSURE_ELEVATED: "forecast-backed pressure elevation",
        FACILITY_READINESS_REASON_CALM_VISIBLE_SCOPE: "no elevated backend review signals",
    }
    text = ", ".join(reason_text_map.get(code, code.lower()) for code in reason_codes)
    return text[:1].upper() + text[1:] + "."


def _facility_readiness_summary_confidence_reason(priorities: list[dict], snapshots_by_id: dict[int, dict]) -> str | None:
    stale = False
    weak = False

    relevant_ids = [priority["facility_id"] for priority in priorities] if priorities else list(snapshots_by_id.keys())
    for facility_id in relevant_ids:
        snapshot = snapshots_by_id[facility_id]
        readiness = snapshot["readiness"]
        freshness = snapshot["freshness"]
        stale = stale or bool(freshness["is_stale"])
        weak = weak or readiness["backing_source"] == "unavailable"

    if stale and weak:
        return "stale_and_weak_proxy_inputs"
    if stale:
        return "stale_inputs"
    if weak:
        return "weak_proxy_inputs"
    return None


def build_facility_readiness_decision_summary(
    facilities: list[HealthFacility],
    *,
    stale_threshold_minutes: int = 120,
    max_priorities: int = 2,
) -> dict:
    snapshots_by_id: dict[int, dict] = {}
    scored: list[dict] = []

    for facility in facilities:
        snapshot = build_facility_intelligence_snapshot(facility, stale_threshold_minutes=stale_threshold_minutes)
        snapshots_by_id[facility.id] = snapshot
        difference_score = _facility_readiness_difference_score_from_snapshot(snapshot)
        difference_reason = _facility_readiness_difference_reason_code(difference_score)
        priority_bucket = _facility_readiness_priority_bucket(snapshot, difference_reason)
        reason_codes = _facility_readiness_priority_reason_codes(snapshot, difference_reason)
        context = snapshot["context"]
        readiness = snapshot["readiness"]
        forecast = snapshot["forecasting"]

        should_review = (
            difference_reason is not None
            or priority_bucket in {0, 1, 2, 3}
            or int(context["ward_alert_count"]) >= 2
        )

        scored.append(
            {
                "facility": facility,
                "snapshot": snapshot,
                "difference_score": difference_score,
                "difference_reason": difference_reason,
                "priority_bucket": priority_bucket,
                "reason_codes": reason_codes,
                "ward_alert_count": int(context["ward_alert_count"]),
                "projected_cases": int(readiness["projected_cases"]),
                "surge_risk": readiness["surge_risk"],
                "forecast_source_kind": forecast["source_kind"],
                "should_review": should_review,
            }
        )

    ranked = sorted(
        scored,
        key=lambda item: (
            item["priority_bucket"],
            -item["difference_score"],
            -item["ward_alert_count"],
            -item["projected_cases"],
            item["facility"].name,
        ),
    )

    review_items = [item for item in ranked if item["should_review"]]
    top_priority_items = review_items[:max_priorities]
    top_priorities = [
        {
            "facility_id": item["facility"].id,
            "facility_name": item["facility"].name,
            "ward_id": item["facility"].ward_id,
            "ward_name": item["facility"].ward.name,
            "priority_rank": index + 1,
            "priority_label": "Top review priority" if index == 0 else "Next review priority",
            "reason_codes": item["reason_codes"],
            "reason_text": _facility_readiness_reason_text(item["reason_codes"]),
            "review_href": None,
        }
        for index, item in enumerate(top_priority_items)
    ]

    confidence_reason = _facility_readiness_summary_confidence_reason(top_priorities, snapshots_by_id)
    confidence = (
        FACILITY_READINESS_DECISION_CONFIDENCE_DEGRADED
        if confidence_reason is not None
        else FACILITY_READINESS_DECISION_CONFIDENCE_NORMAL
    )

    if confidence == FACILITY_READINESS_DECISION_CONFIDENCE_DEGRADED and top_priorities:
        state = FACILITY_READINESS_DECISION_STATE_DEGRADED_CONFIDENCE
        headline = f"Decision confidence is degraded. Start with {top_priorities[0]['facility_name']}."
        body = (
            f"{top_priorities[0]['priority_label']}: {top_priorities[0]['facility_name']}. "
            "Use this page as review guidance while stale or weak inputs remain."
        )
    elif confidence == FACILITY_READINESS_DECISION_CONFIDENCE_DEGRADED:
        state = FACILITY_READINESS_DECISION_STATE_DEGRADED_CONFIDENCE
        headline = "Decision confidence is degraded"
        body = "Facility readiness inputs are stale or incomplete. Use this page as review guidance, not current operational truth."
    elif top_priorities:
        state = FACILITY_READINESS_DECISION_STATE_REVIEW
        headline = "Review top readiness priorities"
        body = (
            f"Top review priority: {top_priorities[0]['facility_name']}. "
            + (
                f"Next review priority: {top_priorities[1]['facility_name']}."
                if len(top_priorities) > 1
                else "Review detail for this facility first."
            )
        )
    else:
        state = FACILITY_READINESS_DECISION_STATE_CALM
        headline = "No immediate review required"
        body = "Based on the current derived readiness estimates, no facility is flagged for review."

    ward_ids_in_scope = {facility.ward_id for facility in facilities}
    total_linked_alerts = (
        Alert.objects.filter(ward_id__in=ward_ids_in_scope).count()
        if ward_ids_in_scope
        else 0
    )

    return {
        "state": state,
        "headline": headline,
        "body": body,
        "confidence": confidence,
        "confidence_reason": confidence_reason,
        "total_review_facility_count": len(review_items),
        "top_priorities": top_priorities,
        "related_surfaces": {
            "has_linked_alerts": total_linked_alerts > 0,
            "linked_alert_count": total_linked_alerts,
        },
    }


def _facility_surge_risk_from_forecast_state(readiness_state: str | None) -> str:
    if readiness_state == "capacity_concern":
        return "EXTREME"
    if readiness_state == "watch":
        return "MODERATE"
    return "LOW"


def _facility_staffing_required_from_level(facility: HealthFacility) -> int:
    if facility.level == HealthFacility.LEVEL_5:
        return 15
    if facility.level == HealthFacility.LEVEL_4:
        return 10
    return 6


def _latest_facility_readiness_snapshot_for_facility(facility: HealthFacility) -> FacilityReadinessSnapshot | None:
    return facility.readiness_snapshots.select_related("ingestion_run", "source").order_by("-reported_at", "-created_at").first()


def _dashboard_freshness_from_readiness_snapshot(snapshot: FacilityReadinessSnapshot) -> str:
    if snapshot.freshness_state == FacilityReadinessFreshness.STALE:
        return "STALE"
    if snapshot.freshness_state == FacilityReadinessFreshness.DELAYED:
        return "WARNING"
    return "FRESH"


def build_facility_intelligence_snapshot(
    facility: HealthFacility,
    *,
    stale_threshold_minutes: int = 120,
    user=None,
) -> dict:
    from .facility_forecasting import latest_facility_forecast_for_facility, latest_promoted_facility_forecast_for_facility

    latest_risk = latest_riskscore_for_ward(facility.ward)
    related_alerts = list(
        facility.ward.alerts.select_related("risk_score").order_by("-created_at")[:6]
    )
    verified_contact = verified_facility_contact_for_facility(facility)
    can_view_contact_detail = _facility_user_can_request_update(user) and verified_contact is not None
    active_review = active_facility_readiness_review_for_facility(facility)
    active_update_request = active_facility_readiness_update_request_for_facility(facility)
    active_escalation = active_facility_readiness_escalation_for_facility(facility)
    linked_alerts = [_facility_linked_alert_payload(alert, user=user) for alert in related_alerts]
    chv_operations = _facility_chv_operations_navigation_payload(facility, user=user)
    promoted_forecast = latest_promoted_facility_forecast_for_facility(facility)
    latest_forecast = promoted_forecast or latest_facility_forecast_for_facility(facility)
    latest_readiness_snapshot = _latest_facility_readiness_snapshot_for_facility(facility)
    population_exposure_context = build_population_exposure_context_for_facility(facility)

    ward_risk_level = latest_risk.risk_level if latest_risk else facility.ward.current_risk_level
    ward_risk_score = latest_risk.score if latest_risk else facility.ward.current_risk_score
    proxy_projected_cases = max(
        1,
        latest_risk.predicted_cases if latest_risk else round((ward_risk_score or 0) * 10),
    )
    proxy_surge_risk = _facility_surge_risk(ward_risk_level)
    proxy_ors_estimate_percent = (
        max(12, 42 - proxy_projected_cases)
        if proxy_surge_risk == "EXTREME"
        else max(48, 78 - proxy_projected_cases)
        if proxy_surge_risk == "MODERATE"
        else max(84, 96 - proxy_projected_cases)
    )
    proxy_staffing_required = 15 if proxy_surge_risk == "EXTREME" else 10 if proxy_surge_risk == "MODERATE" else 6
    proxy_staffing_filled = max(
        2,
        proxy_staffing_required - (3 if proxy_surge_risk == "EXTREME" else 2 if proxy_surge_risk == "MODERATE" else 0),
    )
    proxy_staffing_percent = round((proxy_staffing_filled / proxy_staffing_required) * 100) if proxy_staffing_required else 0

    if latest_readiness_snapshot is not None:
        projected_cases = proxy_projected_cases
        surge_risk = _facility_surge_risk_from_forecast_state(latest_readiness_snapshot.readiness_state)
        ors_estimate_percent = min(100, round((latest_readiness_snapshot.ors_sachets_available / 100) * 100))
        staffing_required = _facility_staffing_required_from_level(facility)
        staffing_filled = latest_readiness_snapshot.staff_on_duty
        staffing_percent = min(100, round((staffing_filled / staffing_required) * 100)) if staffing_required else 0
        readiness_mode = "source_backed_facility_readiness_snapshot"
        readiness_backing_source = (
            "seeded_demo_readiness_snapshot"
            if latest_readiness_snapshot.source_kind == "seeded_demo"
            else "source_readiness_snapshot"
        )
        dashboard_truth_state = "demo_backed" if latest_readiness_snapshot.source_kind == "seeded_demo" else "source_backed"
        driving_ward_ids = [facility.ward_id]
        action_reasoning = [
            "A source-data facility readiness snapshot is driving this readiness summary.",
            "Stock, staffing, referral, and service-disruption fields are stored separately from facility contacts.",
            "This readiness evidence updates facility context but does not send alerts or promote a model.",
        ]
        stockout_flags = (latest_readiness_snapshot.raw_payload or {}).get("stockout_flags") or []
        status_banner_label = (
            "Source snapshot indicates facility capacity concern"
            if surge_risk == "EXTREME"
            else "Source snapshot indicates readiness watch"
            if surge_risk == "MODERATE"
            else "Source snapshot indicates routine readiness"
        )
        context_summary = (
            f"{facility.name} is using a source-backed readiness snapshot reported "
            f"{latest_readiness_snapshot.reported_at:%Y-%m-%d}."
        )
        forecast_summary = {
            "source_kind": "direct_readiness_snapshot",
            "governance_mode": "source_backed",
            "model_version": None,
            "forecast_mode": "source_backed_facility_readiness_snapshot",
            "projected_pressure_score": max(0, min(100, round(100 - latest_readiness_snapshot.readiness_score))),
            "projected_readiness_state": latest_readiness_snapshot.readiness_state,
            "driving_ward_ids": driving_ward_ids,
            "dashboard_truth_state": dashboard_truth_state,
            "readiness_snapshot": {
                "snapshot_id": latest_readiness_snapshot.id,
                "ingestion_run_id": latest_readiness_snapshot.ingestion_run_id,
                "source_kind": latest_readiness_snapshot.source_kind,
                "reported_at": latest_readiness_snapshot.reported_at,
                "freshness_state": latest_readiness_snapshot.freshness_state,
                "readiness_score": latest_readiness_snapshot.readiness_score,
                "stockout_flags": stockout_flags,
                "service_disruption": latest_readiness_snapshot.service_disruption,
                "referral_available": latest_readiness_snapshot.referral_available,
            },
        }
        readiness_freshness_state = _dashboard_freshness_from_readiness_snapshot(latest_readiness_snapshot)
    elif latest_forecast and latest_forecast.forecast_run.status == latest_forecast.forecast_run.STATUS_SUCCESS:
        projected_cases = latest_forecast.projected_case_burden
        surge_risk = _facility_surge_risk_from_forecast_state(latest_forecast.projected_readiness_state)
        ors_state = str((latest_forecast.surge_threshold_state or {}).get("ors", "low")).upper()
        staffing_state = str((latest_forecast.surge_threshold_state or {}).get("staffing", "low")).upper()
        ors_estimate_percent = (
            25 if ors_state == "CAPACITY_CONCERN" else 55 if ors_state == "WATCH" else max(75, proxy_ors_estimate_percent)
        )
        staffing_required = 15 if surge_risk == "EXTREME" else 10 if surge_risk == "MODERATE" else 6
        staffing_percent = (
            45 if staffing_state == "CAPACITY_CONCERN" else 70 if staffing_state == "WATCH" else max(85, proxy_staffing_percent)
        )
        staffing_filled = max(1, round((staffing_percent / 100) * staffing_required))
        is_promoted_forecast = promoted_forecast is not None and latest_forecast.id == promoted_forecast.id
        readiness_mode = (
            "promoted_facility_burden_forecast"
            if is_promoted_forecast
            else "forecast_preview_backed_facility_burden_not_promoted"
        )
        readiness_backing_source = "forecast_promoted" if is_promoted_forecast else "forecast_preview"
        dashboard_truth_state = "promoted" if is_promoted_forecast else "blocked_until_promotion"
        driving_ward_ids = latest_forecast.driving_ward_ids or [facility.ward_id]
        action_reasoning = (
            [
                "A promoted facility burden forecast is driving this readiness summary.",
                "Use driving wards to trace which ward signals are contributing to projected facility strain.",
                "This forecast is eligible for dashboard readiness use because it has been explicitly promoted.",
            ]
            if is_promoted_forecast
            else [
                "Forecast preview is available for facility pressure review.",
                "Use driving wards to trace which ward signals are contributing to projected facility strain.",
                "Do not treat this facility forecast as promoted dashboard truth until promotion blockers are cleared.",
            ]
        )
        status_banner_label = (
            "Promoted forecast indicates high facility pressure"
            if is_promoted_forecast and surge_risk == "EXTREME"
            else "Promoted forecast indicates elevated facility pressure"
            if is_promoted_forecast and surge_risk == "MODERATE"
            else "Promoted forecast indicates low facility pressure"
            if is_promoted_forecast
            else "Forecast preview indicates high facility pressure"
            if surge_risk == "EXTREME"
            else "Forecast preview indicates elevated facility pressure"
            if surge_risk == "MODERATE"
            else "Forecast preview indicates low facility pressure"
        )
        context_summary = (
            f"{facility.name} is using a promoted facility burden forecast for near-term readiness."
            if is_promoted_forecast
            else f"{facility.name} has a forecast-backed preview for near-term burden. "
            "This preview is usable for review, but it is not yet a promoted dashboard readiness signal."
        )
        forecast_summary = {
            "source_kind": "promoted_forecast" if is_promoted_forecast else "forecast_preview",
            "governance_mode": "promoted" if is_promoted_forecast else "preview_only",
            "model_version": latest_forecast.model_version or latest_forecast.forecast_run.model_version,
            "forecast_mode": latest_forecast.forecast_mode,
            "projected_pressure_score": latest_forecast.projected_pressure_score,
            "projected_readiness_state": latest_forecast.projected_readiness_state,
            "driving_ward_ids": driving_ward_ids,
            "dashboard_truth_state": dashboard_truth_state,
        }
    else:
        projected_cases = proxy_projected_cases
        surge_risk = proxy_surge_risk
        ors_estimate_percent = proxy_ors_estimate_percent
        staffing_required = proxy_staffing_required
        staffing_filled = proxy_staffing_filled
        staffing_percent = proxy_staffing_percent
        readiness_mode = "unavailable_until_direct_snapshot_or_promoted_forecast"
        readiness_backing_source = "unavailable"
        dashboard_truth_state = "unavailable"
        driving_ward_ids = [facility.ward_id]
        action_reasoning = [
            "No promoted facility forecast is currently available for this facility.",
            "Ward-risk-derived burden remains visible as contextual preview, but the dashboard is withholding proxy-only readiness as operational capacity truth.",
        ]
        forecast_summary = {
            "source_kind": "unavailable",
            "governance_mode": "not_available",
            "model_version": None,
            "forecast_mode": "readiness_unavailable_without_promoted_forecast",
            "projected_pressure_score": 0,
            "projected_readiness_state": "not_available",
            "driving_ward_ids": driving_ward_ids,
            "dashboard_truth_state": dashboard_truth_state,
        }

    population_exposure_values = population_exposure_context.get("values") or {}
    forecast_summary["population_exposure"] = {
        "status": population_exposure_context.get("status"),
        "catchment_population_estimate": population_exposure_values.get("catchment_population_estimate"),
        "ward_population_total": population_exposure_values.get("population_total"),
        "exposed_population_proxy": population_exposure_values.get("exposed_population_proxy"),
        "truth_class_counts": (population_exposure_context.get("source_lineage") or {}).get("truth_class_counts", {}),
        "display_caveat": population_exposure_context.get("display_caveat"),
    }
    if population_exposure_context["coverage"]["has_catchment_population"]:
        action_reasoning.append(
            "Catchment population is available as an estimate with lineage; use it for context, not as facility census truth."
        )
    elif population_exposure_context["coverage"]["record_count"]:
        action_reasoning.append(
            "Population/exposure context is available, but no facility catchment estimate exists for this facility yet."
        )
    else:
        action_reasoning.append(
            "No source-fed population or exposure context is available for this facility yet."
        )

    if readiness_backing_source == "unavailable":
        inferred_status_banner_label = "Facility readiness currently unavailable"
        inferred_context_summary = (
            f"{facility.name} has no promoted facility forecast yet, so the dashboard is withholding capacity inference "
            "instead of projecting proxy readiness from ward risk alone."
        )
    elif surge_risk == "EXTREME":
        inferred_status_banner_label = "High calculated readiness pressure"
        inferred_context_summary = (
            f"This facility is linked to a high ward-risk record for {facility.ward.name}. "
            "The page combines facility identity, linked ward risk, and visible alert records."
        )
    elif surge_risk == "MODERATE":
        inferred_status_banner_label = "Moderate calculated readiness pressure"
        inferred_context_summary = (
            f"This facility is linked to a moderate ward-risk record for {facility.ward.name}. "
            "Review later records if pressure continues to rise."
        )
    else:
        inferred_status_banner_label = "Low calculated readiness pressure"
        inferred_context_summary = (
            f"This facility is linked to a low ward-risk record for {facility.ward.name}. "
            "Maintain routine monitoring until newer records arrive."
        )

    status_banner_label = locals().get("status_banner_label", inferred_status_banner_label)
    context_summary = locals().get("context_summary", inferred_context_summary)

    freshness_timestamp = (
        latest_readiness_snapshot.reported_at
        if latest_readiness_snapshot is not None
        else latest_forecast.generated_at
        if latest_forecast
        else facility.updated_at
    )
    freshness_state = locals().get("readiness_freshness_state") or _facility_freshness_state(freshness_timestamp)

    is_stale = True
    freshness_updated_at = freshness_timestamp
    if freshness_updated_at is not None:
        is_stale = (
            latest_readiness_snapshot.freshness_state == FacilityReadinessFreshness.STALE
            if latest_readiness_snapshot is not None
            else (timezone.now() - freshness_updated_at).total_seconds() / 60 > stale_threshold_minutes
        )

    timeline = [
        {
            "id": "facility-record",
            "title": "Facility record refreshed",
            "description": (
                f"{facility.name} is using its current backend facility record. "
                "Readiness figures on this page are calculated from facility identity plus ward risk data."
            ),
            "timestamp": facility.updated_at,
            "tone": "success",
            "category": "system",
            "meta": None,
            "details": [f"Facility code: {facility.facility_code}"],
        }
    ]

    if latest_readiness_snapshot is not None:
        timeline.insert(
            0,
            {
                "id": f"facility-readiness-snapshot-{latest_readiness_snapshot.id}",
                "title": "Source-backed readiness snapshot available",
                "description": (
                    "Facility stock, staffing, referral, and service-disruption fields were imported through "
                    "the source-data readiness snapshot feed."
                ),
                "timestamp": latest_readiness_snapshot.reported_at,
                "tone": "danger" if latest_readiness_snapshot.readiness_state == "capacity_concern" else "warning" if latest_readiness_snapshot.readiness_state == "watch" else "success",
                "category": "system",
                "meta": f"Source kind: {latest_readiness_snapshot.source_kind}",
                "details": [
                    f"Readiness state: {latest_readiness_snapshot.readiness_state}",
                    f"Readiness score: {latest_readiness_snapshot.readiness_score}",
                    f"Ingestion run: {latest_readiness_snapshot.ingestion_run_id}",
                ],
            }
        )

    if population_exposure_context["coverage"]["record_count"]:
        factor_labels = [
            factor.get("label")
            for factor in population_exposure_context.get("factor_items", [])[:3]
            if factor.get("label")
        ]
        timeline.append(
            {
                "id": "population-exposure-context",
                "title": "Population and exposure context available",
                "description": (
                    "Population, exposure, or catchment values are attached with truth-class metadata. "
                    "Use them as baseline/proxy context rather than exact census truth."
                ),
                "timestamp": freshness_updated_at,
                "tone": "info",
                "category": "system",
                "meta": population_exposure_context.get("status"),
                "details": factor_labels,
            }
        )

    if latest_forecast and latest_forecast.forecast_run.status == latest_forecast.forecast_run.STATUS_SUCCESS:
        timeline.insert(
            0,
            {
                "id": f"facility-forecast-{latest_forecast.id}",
                "title": "Facility burden forecast preview available",
                "description": (
                    "A promoted Negative Binomial facility burden forecast is active for this facility."
                    if promoted_forecast is not None and latest_forecast.id == promoted_forecast.id
                    else "A Negative Binomial facility burden preview exists for this facility. "
                    "It is available for review but still blocked from promoted dashboard truth."
                ),
                "timestamp": latest_forecast.generated_at,
                "tone": "success" if promoted_forecast is not None and latest_forecast.id == promoted_forecast.id else "warning",
                "category": "system",
                "meta": f"Model version: {latest_forecast.model_version or latest_forecast.forecast_run.model_version}",
                "details": [
                    f"Projected readiness: {latest_forecast.projected_readiness_state}",
                    f"Projected pressure score: {latest_forecast.projected_pressure_score}",
                    f"Driving wards: {', '.join(str(ward_id) for ward_id in (latest_forecast.driving_ward_ids or [])) or 'None'}",
                ],
            }
        )

    for alert in related_alerts[:2]:
        timeline.append(
            {
                "id": f"alert-{alert.id}",
                "title": f"{alert.channel.title()} alert {alert.status.lower().replace('_', ' ')}",
                "description": _text_value_for_service_user(alert.message, user),
                "timestamp": alert.created_at,
                "tone": (
                    "danger"
                    if alert.status == Alert.STATUS_FAILED
                    else "success"
                    if alert.status == Alert.STATUS_DELIVERED
                    else "warning"
                ),
                "category": "alert",
                "meta": f"Recipient: {_contact_value_for_service_user(alert.recipient, user)}",
                "details": [f"Backend: {alert.delivery_backend or 'Unspecified'}"],
            }
        )

    if not related_alerts:
        timeline.append(
            {
                "id": "alert-gap",
                "title": "No ward-linked alert records",
                "description": "No alert records are currently attached to this facility's ward in the backend alert log.",
                "timestamp": facility.updated_at,
                "tone": "info",
                "category": "alert",
                "meta": None,
                "details": [],
            }
        )

    decision_summary = _build_initial_facility_readiness_decision_summary(
        facility=facility,
        ward_risk_level=ward_risk_level,
        surge_risk=surge_risk,
        readiness_backing_source=readiness_backing_source,
        ward_alert_count=len(related_alerts),
        forecast_source_kind=forecast_summary["source_kind"],
        is_stale=is_stale,
    )

    return {
        "facility": facility,
        "readiness": {
            "facility_type_label": _facility_format_type(facility),
            "surge_risk": surge_risk,
            "surge_risk_label": "High" if surge_risk == "EXTREME" else "Moderate" if surge_risk == "MODERATE" else "Low",
            "status_banner_label": status_banner_label,
            "projected_cases": projected_cases,
            "predicted_cases_per_day": projected_cases * 5,
            "ors_estimate_percent": ors_estimate_percent,
            "ors_state": _facility_ors_state(ors_estimate_percent) if readiness_backing_source != "unavailable" else "READY",
            "staffing_filled": staffing_filled,
            "staffing_required": staffing_required,
            "staffing_percent": staffing_percent,
            "staffing_state": "LIMITED" if readiness_backing_source != "unavailable" and staffing_filled < staffing_required else "OPTIMAL",
            "last_reported_at": freshness_updated_at,
            "freshness_state": freshness_state,
            "mode": readiness_mode,
            "backing_source": readiness_backing_source,
            "dashboard_truth_state": dashboard_truth_state,
        },
        "context": {
            "summary": context_summary,
            "ward_risk_score": ward_risk_score,
            "ward_alert_count": len(related_alerts),
            "map_mode": "shared_ward_geometry_contract",
            "driving_ward_ids": driving_ward_ids,
            "action_reasoning": action_reasoning,
        },
        "forecasting": forecast_summary,
        "population_exposure": population_exposure_context,
        "freshness": {
            "updated_at": freshness_updated_at,
            "is_stale": is_stale,
            "stale_threshold_minutes": stale_threshold_minutes,
            "mode": "derived_from_forecast_or_facility_timestamp",
        },
        "decision_summary": decision_summary,
        "timeline": timeline,
        "contact": verified_contact if can_view_contact_detail else None,
        "active_review": active_review,
        "active_update_request": active_update_request,
        "active_escalation": active_escalation,
        "linked_alerts": linked_alerts,
        "chv_operations": chv_operations,
        "capabilities": {
            "can_view_contacts": can_view_contact_detail,
            "can_open_readiness_review": (
                _facility_user_can_request_update(user)
                and active_review is None
                and decision_summary["state"]
                in {
                    FACILITY_READINESS_DECISION_STATE_REVIEW,
                    FACILITY_READINESS_DECISION_STATE_DEGRADED_CONFIDENCE,
                }
            ),
            "can_request_facility_update": (
                _facility_user_can_request_update(user)
                and verified_contact is not None
                and active_review is not None
                and active_update_request is None
            ),
            "can_escalate_county_review": (
                _facility_has_county_review_queue()
                and _facility_user_can_escalate_county_review(user)
                and active_review is not None
                and active_escalation is None
            ),
            "can_open_linked_alert": bool(related_alerts),
            "can_open_chv_operations": chv_operations["available"],
            "can_acknowledge_review": (
                _facility_user_can_request_update(user)
                and active_review is not None
                and active_review.status == FacilityReadinessReview.STATUS_OPEN
            ),
            "has_verified_contact": verified_contact is not None,
            "has_active_review": active_review is not None,
            "has_active_update_request": active_update_request is not None,
            "has_active_escalation": active_escalation is not None,
            "has_county_review_queue": _facility_has_county_review_queue(),
            "mode": "contract_backed_readiness_workflows",
        },
    }


def generate_triage_recommendation(
    ward: Ward,
    diarrhea: bool,
    vomiting: bool,
    dehydration: bool,
    fever: bool,
) -> tuple[str, bool]:
    ward_risk = ward.current_risk_level

    if diarrhea and vomiting and dehydration:
        if ward_risk == Ward.RISK_HIGH:
            return (
                "High cholera suspicion. Start ORS immediately, assess dehydration urgently, "
                "refer to nearest health facility now, and alert supervisor.",
                True,
            )
        return (
            "Severe diarrhea case. Start ORS immediately, assess dehydration, "
            "and refer to a health facility urgently.",
            True,
        )

    if diarrhea and dehydration:
        return (
            "Possible acute watery diarrhea with dehydration. Start ORS, monitor closely, "
            "and refer if symptoms worsen.",
            True,
        )

    if diarrhea and vomiting:
        return (
            "Possible diarrheal illness. Give ORS, reinforce safe water and hygiene guidance, "
            "and monitor closely.",
            False,
        )

    if fever and ward_risk == Ward.RISK_HIGH:
        return (
            "Fever reported in high-risk ward. Assess for malaria and diarrheal symptoms, "
            "advise prompt testing and follow-up.",
            False,
        )

    if diarrhea:
        return (
            "Provide ORS, advise safe water use, handwashing, and monitor for worsening symptoms "
            "or dehydration signs.",
            False,
        )

    return (
        "No immediate cholera danger signs identified. Continue observation, reinforce prevention "
        "messaging, and follow routine guidance.",
        False,
    )


def create_triage_session(
    ward: Ward,
    phone_number: str,
    diarrhea: bool,
    vomiting: bool,
    dehydration: bool,
    fever: bool,
    text_input: str = "",
    channel: str = "USSD",
) -> TriageSession:
    recommendation, referral_needed = generate_triage_recommendation(
        ward=ward,
        diarrhea=diarrhea,
        vomiting=vomiting,
        dehydration=dehydration,
        fever=fever,
    )
    referral_facility = None

    if referral_needed:
        referral_facility = (
            HealthFacility.objects.filter(ward=ward, is_active=True)
            .order_by("name")
            .first()
        )

    return TriageSession.objects.create(
        channel=channel,
        phone_number=phone_number,
        ward=ward,
        referral_facility=referral_facility,
        text_input=text_input,
        diarrhea=diarrhea,
        vomiting=vomiting,
        dehydration=dehydration,
        fever=fever,
        recommendation=recommendation,
        referral_needed=referral_needed,
    )


class SyncPayloadProcessingError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = 400,
        conflict_state: str = SyncQueue.CONFLICT_NONE,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.conflict_state = conflict_state


def _payload_bool(payload_body: dict, key: str) -> bool:
    return bool(payload_body.get(key, False))


def _payload_int(payload_body: dict, key: str) -> int:
    value = payload_body.get(key, 0)
    if value in ("", None):
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError) as exc:
        raise SyncPayloadProcessingError(f"{key} must be a non-negative integer.") from exc


def _payload_public_id(payload_body: dict, *keys: str) -> str:
    for key in keys:
        value = payload_body.get(key)
        if value:
            return str(value).strip()
    return ""


def _resolve_chv_for_sync_user(user, ward: Ward) -> CHV | None:
    phone_number = (getattr(user, "phone_number", "") or "").strip()
    if not phone_number:
        return None
    return CHV.objects.filter(ward=ward, phone_number=phone_number, is_active=True).first()


def _assert_chv_payload_scope(ward: Ward, payload_body: dict) -> None:
    payload_ward_id = payload_body.get("ward_id")
    if payload_ward_id not in ("", None):
        try:
            payload_ward_id = int(payload_ward_id)
        except (TypeError, ValueError) as exc:
            raise SyncPayloadProcessingError("ward_id must be a valid ward.") from exc
        if payload_ward_id != ward.id:
            raise SyncPayloadProcessingError(
                "Ward not found.",
                status_code=404,
                conflict_state=SyncQueue.CONFLICT_SCOPE_MISMATCH,
            )

    for unsafe_key in ("household_id", "household_public_id", "household_name", "household_phone"):
        if payload_body.get(unsafe_key):
            raise SyncPayloadProcessingError(
                "Household identifiers are not accepted in CHV offline sync payloads.",
                conflict_state=SyncQueue.CONFLICT_SCOPE_MISMATCH,
            )


def _query_preparedness_action_by_public_id(public_id: str):
    if not public_id:
        return PreparednessAction.objects.none()
    try:
        return PreparednessAction.objects.select_related("ward", "chv", "assigned_to").filter(
            public_id=public_id,
        )
    except (TypeError, ValueError):
        return PreparednessAction.objects.none()


def _query_alert_by_public_id(public_id: str):
    if not public_id:
        return Alert.objects.none()
    try:
        return Alert.objects.filter(public_id=public_id)
    except (TypeError, ValueError):
        return Alert.objects.none()


def _sync_user_can_process_preparedness_action(user, action: PreparednessAction, ward: Ward) -> bool:
    if action.ward_id != ward.id:
        return False
    if getattr(user, "role", None) == "SUPERVISOR":
        return getattr(user, "ward_id", None) == ward.id
    if getattr(user, "role", None) != "CHV":
        return False

    chv = _resolve_chv_for_sync_user(user, ward)
    if action.assigned_to_id == getattr(user, "id", None):
        return True
    return bool(chv and action.chv_id == chv.id)


def _resolve_preparedness_action_for_sync_payload(
    *,
    user,
    ward: Ward,
    upload_type: str,
    payload_body: dict,
) -> PreparednessAction | None:
    if upload_type not in {
        SyncQueue.UPLOAD_PREVENTION_VISIT,
        SyncQueue.UPLOAD_TASK_ACK,
        SyncQueue.UPLOAD_ALERT_ACK,
    }:
        return None

    action_public_id = _payload_public_id(payload_body, "action_public_id", "task_public_id")
    action = _query_preparedness_action_by_public_id(action_public_id).filter(ward=ward).first()

    if action is None and upload_type == SyncQueue.UPLOAD_ALERT_ACK:
        alert_public_id = _payload_public_id(payload_body, "alert_public_id")
        alert = _query_alert_by_public_id(alert_public_id).filter(ward=ward).first()
        if alert is None and alert_public_id:
            raise SyncPayloadProcessingError(
                "Alert not found.",
                status_code=404,
                conflict_state=SyncQueue.CONFLICT_SCOPE_MISMATCH,
            )
        if alert is not None:
            action = (
                PreparednessAction.objects.select_related("ward", "chv", "assigned_to")
                .filter(ward=ward, alert=alert, status__in=PreparednessAction.ACTIVE_STATUSES)
                .order_by("-created_at")
                .first()
            )

    if action is None:
        raise SyncPayloadProcessingError(
            "Preparedness action not found.",
            status_code=404,
            conflict_state=SyncQueue.CONFLICT_SCOPE_MISMATCH,
        )

    if not _sync_user_can_process_preparedness_action(user, action, ward):
        raise SyncPayloadProcessingError(
            "Preparedness action not found.",
            status_code=404,
            conflict_state=SyncQueue.CONFLICT_SCOPE_MISMATCH,
        )

    return action


def _task_ack_target_status(payload_body: dict) -> str:
    acknowledgment_status = str(payload_body.get("acknowledgment_status") or "ACKNOWLEDGED").strip().upper()
    if acknowledgment_status in {"ACKNOWLEDGED", "ACK", "ACCEPTED"}:
        return PreparednessAction.STATUS_ACKNOWLEDGED
    if acknowledgment_status in {"IN_PROGRESS", "STARTED"}:
        return PreparednessAction.STATUS_IN_PROGRESS
    if acknowledgment_status in {"BLOCKED", "UNABLE", "UNABLE_TO_COMPLETE"}:
        return PreparednessAction.STATUS_BLOCKED
    if acknowledgment_status in {"COMPLETED", "DONE"}:
        return PreparednessAction.STATUS_COMPLETED
    raise SyncPayloadProcessingError("Unsupported acknowledgment_status.")


def _completion_evidence_from_sync_payload(
    *,
    sync_item: SyncQueue,
    payload_body: dict,
    upload_type: str,
) -> dict:
    evidence = {
        "schema_version": "chv-offline-action-evidence-v1",
        "upload_type": upload_type,
        "client_submission_id": sync_item.client_submission_id,
        "idempotency_key": sync_item.idempotency_key,
        "download_bundle_version": sync_item.download_bundle_version,
    }
    if upload_type == SyncQueue.UPLOAD_PREVENTION_VISIT:
        evidence.update(
            {
                "visit_completed": _payload_bool(payload_body, "visit_completed"),
                "households_reached_count": _payload_int(payload_body, "households_reached_count"),
                "messages_delivered_count": _payload_int(payload_body, "messages_delivered_count"),
                "water_treatment_demo": _payload_bool(payload_body, "water_treatment_demo"),
                "soap_or_handwashing_discussed": _payload_bool(payload_body, "soap_or_handwashing_discussed"),
            }
        )
    else:
        evidence["coded_reason"] = str(payload_body.get("coded_reason") or "").strip()
        evidence["acknowledgment_status"] = str(payload_body.get("acknowledgment_status") or "").strip()
    return evidence


def _record_offline_sync_action_audit(
    *,
    action: PreparednessAction,
    actor,
    sync_item: SyncQueue,
    old_status: str,
    new_status: str,
    upload_type: str,
) -> PreparednessActionEvent:
    return record_preparedness_action_event(
        action,
        event_type=PreparednessActionEvent.EVENT_COMMENT,
        actor=actor,
        old_status=old_status,
        new_status=new_status,
        detail="Offline CHV sync payload processed.",
        metadata={
            "source": "chv_offline_sync",
            "sync_queue_id": sync_item.id,
            "client_submission_id": sync_item.client_submission_id,
            "idempotency_key": sync_item.idempotency_key,
            "upload_type": upload_type,
            "download_bundle_version": sync_item.download_bundle_version,
            "contract_version": sync_item.contract_version,
        },
    )


def _process_action_sync_payload(
    *,
    action: PreparednessAction,
    user,
    sync_item: SyncQueue,
    payload_body: dict,
) -> dict:
    upload_type = sync_item.upload_type
    old_status = action.status

    if upload_type == SyncQueue.UPLOAD_PREVENTION_VISIT:
        target_status = (
            PreparednessAction.STATUS_COMPLETED
            if _payload_bool(payload_body, "visit_completed")
            else PreparednessAction.STATUS_IN_PROGRESS
        )
    else:
        target_status = _task_ack_target_status(payload_body)

    completion_evidence = None
    if target_status == PreparednessAction.STATUS_COMPLETED or upload_type == SyncQueue.UPLOAD_PREVENTION_VISIT:
        completion_evidence = _completion_evidence_from_sync_payload(
            sync_item=sync_item,
            payload_body=payload_body,
            upload_type=upload_type,
        )

    if target_status == action.status and completion_evidence is None:
        updated_action = action
    else:
        updated_action = transition_preparedness_action(
            action,
            actor=user,
            status=target_status,
            detail="Offline CHV field submission processed.",
            completion_evidence=completion_evidence,
        )

    audit_event = _record_offline_sync_action_audit(
        action=updated_action,
        actor=user,
        sync_item=sync_item,
        old_status=old_status,
        new_status=updated_action.status,
        upload_type=upload_type,
    )

    return {
        "type": "preparedness_action",
        "id": updated_action.id,
        "public_id": str(updated_action.public_id),
        "status": updated_action.status,
        "sync_audit_event_public_id": str(audit_event.public_id),
    }


def _domain_record_from_processed_sync_item(sync_item: SyncQueue) -> dict:
    server_receipt = sync_item.server_receipt if isinstance(sync_item.server_receipt, dict) else {}
    domain_record = server_receipt.get("domain_record")
    if isinstance(domain_record, dict):
        return domain_record
    if sync_item.triage_session_id:
        return {
            "type": "triage_session",
            "id": sync_item.triage_session_id,
        }
    return {}


def _sync_failure_status_code(sync_item: SyncQueue) -> int:
    if sync_item.conflict_state == SyncQueue.CONFLICT_SCOPE_MISMATCH:
        return 404
    return 400


def _touch_failed_chv_device_registration(
    *,
    device_registration: CHVDeviceRegistration | None,
    seen_at,
    bundle_version: str,
) -> None:
    if device_registration is None:
        return

    update_fields = ["last_seen_at", "updated_at"]
    device_registration.last_seen_at = seen_at
    if bundle_version:
        device_registration.last_bundle_version = bundle_version
        update_fields.append("last_bundle_version")
    device_registration.save(update_fields=update_fields)


def _mark_sync_item_rejected(
    *,
    sync_item: SyncQueue,
    exc: Exception,
    payload_version: str,
    language_metadata: dict | None = None,
) -> None:
    processed_at = timezone.now()
    conflict_state = (
        exc.conflict_state
        if isinstance(exc, SyncPayloadProcessingError)
        else SyncQueue.CONFLICT_NONE
    )
    sync_item.status = SyncQueue.STATUS_FAILED
    sync_item.conflict_state = conflict_state
    sync_item.error_message = str(exc)
    sync_item.processed_at = processed_at
    sync_item.server_receipt = {
        "receipt_id": f"sync-{sync_item.id}",
        "rejected_at": processed_at.isoformat(),
        "status": "REJECTED",
        "replayed": False,
        "contract_version": sync_item.contract_version,
        "payload_version": payload_version,
        "upload_type": sync_item.upload_type,
        "language": language_metadata or {},
        "conflict_state": conflict_state,
        "domain_record": {},
        "explanation": str(exc),
    }
    sync_item.save(
        update_fields=[
            "status",
            "conflict_state",
            "error_message",
            "processed_at",
            "server_receipt",
        ]
    )


def process_sync_payload(
    *,
    ward: Ward,
    phone_number: str,
    source_device_id: str,
    payload: dict,
    contract_version: str = SyncQueue.CONTRACT_VERSION_DEFAULT,
    device_registration: CHVDeviceRegistration | None = None,
    download_bundle_version: str = "",
    language_metadata: dict | None = None,
    user=None,
) -> tuple[SyncQueue, dict, bool]:
    client_submission_id = (payload.get("client_submission_id") or "").strip()
    if not client_submission_id:
        raise ValueError("client_submission_id is required.")

    if device_registration is not None and not source_device_id:
        source_device_id = device_registration.device_id

    idempotency_key = (payload.get("idempotency_key") or client_submission_id).strip()
    upload_type = payload.get("upload_type") or SyncQueue.UPLOAD_SYMPTOM_TRIAGE
    payload_body = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
    item_bundle_version = (payload.get("download_bundle_version") or download_bundle_version or "").strip()
    recorded_at = payload.get("recorded_at")
    payload_version = (payload.get("payload_version") or "chv-upload-payload-v1").strip()

    existing_sync_item = None
    if idempotency_key:
        existing_sync_item = (
            SyncQueue.objects.select_related("triage_session")
            .filter(
                source_device_id=source_device_id,
                idempotency_key=idempotency_key,
            )
            .first()
        )
    if existing_sync_item is None:
        existing_sync_item = (
            SyncQueue.objects.select_related("triage_session")
            .filter(
                source_device_id=source_device_id,
                client_submission_id=client_submission_id,
            )
            .first()
        )
    if existing_sync_item and existing_sync_item.status == SyncQueue.STATUS_PROCESSED:
        return existing_sync_item, _domain_record_from_processed_sync_item(existing_sync_item), True
    if existing_sync_item and existing_sync_item.status == SyncQueue.STATUS_FAILED:
        raise SyncPayloadProcessingError(
            existing_sync_item.error_message or "Previous CHV offline upload attempt was rejected.",
            status_code=_sync_failure_status_code(existing_sync_item),
            conflict_state=existing_sync_item.conflict_state,
        )
    if existing_sync_item:
        raise SyncPayloadProcessingError(
            "CHV offline upload is already queued for processing.",
            status_code=409,
            conflict_state=SyncQueue.CONFLICT_REPLAYED,
        )

    try:
        sync_item = SyncQueue.objects.create(
            source_device_id=source_device_id,
            device_registration=device_registration,
            contract_version=contract_version or SyncQueue.CONTRACT_VERSION_DEFAULT,
            upload_type=upload_type,
            client_submission_id=client_submission_id,
            idempotency_key=idempotency_key,
            download_bundle_version=item_bundle_version,
            recorded_at=recorded_at,
            phone_number=phone_number,
            ward=ward,
            payload=payload_body,
            status=SyncQueue.STATUS_PENDING,
            conflict_state=SyncQueue.CONFLICT_NONE,
        )
    except IntegrityError:
        existing_sync_item = (
            SyncQueue.objects.select_related("triage_session")
            .filter(
                source_device_id=source_device_id,
                idempotency_key=idempotency_key,
            )
            .first()
        ) or (
            SyncQueue.objects.select_related("triage_session")
            .filter(
                source_device_id=source_device_id,
                client_submission_id=client_submission_id,
            )
            .first()
        )
        if existing_sync_item and existing_sync_item.status == SyncQueue.STATUS_PROCESSED:
            return existing_sync_item, _domain_record_from_processed_sync_item(existing_sync_item), True
        if existing_sync_item and existing_sync_item.status == SyncQueue.STATUS_FAILED:
            raise SyncPayloadProcessingError(
                existing_sync_item.error_message or "Previous CHV offline upload attempt was rejected.",
                status_code=_sync_failure_status_code(existing_sync_item),
                conflict_state=existing_sync_item.conflict_state,
            )
        raise

    try:
        _assert_chv_payload_scope(ward, payload_body)
        action = _resolve_preparedness_action_for_sync_payload(
            user=user,
            ward=ward,
            upload_type=upload_type,
            payload_body=payload_body,
        )
        triage_session = None
        if upload_type in {SyncQueue.UPLOAD_SYMPTOM_TRIAGE, SyncQueue.UPLOAD_SUSPECTED_CASE_SIGNAL}:
            triage_session = create_triage_session(
                ward=ward,
                phone_number=phone_number,
                diarrhea=payload_body.get("diarrhea", False),
                vomiting=payload_body.get("vomiting", False),
                dehydration=payload_body.get("dehydration", False),
                fever=payload_body.get("fever", False),
                text_input=payload_body.get("text_input", ""),
                channel="OFFLINE_SYNC",
            )
            domain_record = {
                "type": "triage_session",
                "id": triage_session.id,
            }
        elif action is not None:
            domain_record = _process_action_sync_payload(
                action=action,
                user=user,
                sync_item=sync_item,
                payload_body=payload_body,
            )
        else:
            raise SyncPayloadProcessingError(
                "Unsupported CHV offline upload type.",
                conflict_state=SyncQueue.CONFLICT_UNSUPPORTED_UPLOAD,
            )
        processed_at = timezone.now()
        server_receipt = {
            "receipt_id": f"sync-{sync_item.id}",
            "accepted_at": processed_at.isoformat(),
            "status": "ACCEPTED",
            "replayed": False,
            "contract_version": sync_item.contract_version,
            "payload_version": payload_version,
            "upload_type": sync_item.upload_type,
            "language": language_metadata or {},
            "domain_record": domain_record,
        }
        sync_item.status = SyncQueue.STATUS_PROCESSED
        sync_item.triage_session = triage_session
        sync_item.processed_at = processed_at
        sync_item.server_receipt = server_receipt
        sync_item.save(update_fields=["status", "triage_session", "processed_at", "server_receipt"])
        if device_registration is not None:
            device_registration.last_sync_at = processed_at
            if item_bundle_version:
                device_registration.last_bundle_version = item_bundle_version
            device_registration.last_seen_at = processed_at
            device_registration.save(update_fields=["last_sync_at", "last_bundle_version", "last_seen_at", "updated_at"])
        return sync_item, domain_record, False
    except Exception as exc:
        _mark_sync_item_rejected(
            sync_item=sync_item,
            exc=exc,
            payload_version=payload_version,
            language_metadata=language_metadata,
        )
        _touch_failed_chv_device_registration(
            device_registration=device_registration,
            seen_at=sync_item.processed_at,
            bundle_version=item_bundle_version,
        )
        raise


def _derive_operational_status(is_active: bool, last_activity_at):
    if not is_active:
        return "OFFLINE"
    if not last_activity_at:
        return "IDLE"

    age = timezone.now() - last_activity_at
    if age <= timedelta(hours=1):
        return "ACTIVE"
    if age <= timedelta(hours=24):
        return "IDLE"
    return "OFFLINE"


def _derive_sync_health(last_sync_at):
    if not last_sync_at:
        return "OFFLINE"

    age = timezone.now() - last_sync_at
    if age <= timedelta(minutes=30):
        return "ONLINE"
    if age <= timedelta(hours=6):
        return "DELAYED"
    return "OFFLINE"


def build_chv_operations_snapshot(chv_queryset) -> list[dict]:
    now = timezone.now()
    since_24h = now - timedelta(hours=24)
    chvs = list(chv_queryset.select_related("ward"))
    phone_numbers = [chv.phone_number for chv in chvs if chv.phone_number]
    ward_ids = [chv.ward_id for chv in chvs]

    sync_rows = SyncQueue.objects.filter(phone_number__in=phone_numbers).values("phone_number").annotate(
        latest_activity=Max("created_at"),
        latest_sync=Max("processed_at"),
        sync_payloads_24h=Count("id", filter=Q(created_at__gte=since_24h)),
    )
    triage_rows = TriageSession.objects.filter(phone_number__in=phone_numbers).values("phone_number").annotate(
        latest_activity=Max("created_at"),
        triage_sessions_24h=Count("id", filter=Q(created_at__gte=since_24h)),
        referrals_24h=Count("id", filter=Q(created_at__gte=since_24h, referral_needed=True)),
    )
    ussd_rows = UssdSessionLog.objects.filter(phone_number__in=phone_numbers).values("phone_number").annotate(
        latest_activity=Max("created_at"),
        ussd_sessions_24h=Count("id", filter=Q(created_at__gte=since_24h)),
    )
    alert_rows = Alert.objects.filter(ward_id__in=ward_ids).values("ward_id").annotate(
        total=Count("id"),
        delivered=Count("id", filter=Q(status=Alert.STATUS_DELIVERED)),
    )

    sync_by_phone = {row["phone_number"]: row for row in sync_rows}
    triage_by_phone = {row["phone_number"]: row for row in triage_rows}
    ussd_by_phone = {row["phone_number"]: row for row in ussd_rows}
    alerts_by_ward = {row["ward_id"]: row for row in alert_rows}

    snapshot = []
    for chv in chvs:
        sync_row = sync_by_phone.get(chv.phone_number, {})
        triage_row = triage_by_phone.get(chv.phone_number, {})
        ussd_row = ussd_by_phone.get(chv.phone_number, {})
        ward_alert_row = alerts_by_ward.get(chv.ward_id, {})

        last_sync_at = sync_row.get("latest_sync")
        candidate_activity_times = [
            value
            for value in [
                last_sync_at,
                sync_row.get("latest_activity"),
                triage_row.get("latest_activity"),
                ussd_row.get("latest_activity"),
            ]
            if value
        ]
        last_activity_at = max(candidate_activity_times) if candidate_activity_times else None

        message_mode = resolve_chv_message_mode()
        message_delivery_kind = resolve_chv_message_delivery_kind()

        snapshot.append(
            {
                "id": chv.id,
                "public_id": chv.public_id,
                "name": chv.name,
                "phone_number": chv.phone_number,
                "language": chv.language,
                "preferred_language": chv.preferred_language,
                "is_active": chv.is_active,
                "ward": chv.ward_id,
                "ward_name": chv.ward.name,
                "created_at": chv.created_at,
                "last_sync_at": last_sync_at,
                "last_activity_at": last_activity_at,
                "operational_status": _derive_operational_status(chv.is_active, last_activity_at),
                "sync_health": _derive_sync_health(last_sync_at),
                "triage_sessions_24h": triage_row.get("triage_sessions_24h", 0),
                "referrals_24h": triage_row.get("referrals_24h", 0),
                "sync_payloads_24h": sync_row.get("sync_payloads_24h", 0),
                "ussd_sessions_24h": ussd_row.get("ussd_sessions_24h", 0),
                "ward_alerts_total": ward_alert_row.get("total", 0),
                "ward_alerts_delivered": ward_alert_row.get("delivered", 0),
                "can_message": message_mode in {"SEND", "QUEUE_ONLY"},
                "message_mode": message_mode,
                "message_delivery_kind": message_delivery_kind,
                "can_view_activity": True,
            }
        )

    return snapshot


def build_chv_activity_timeline(chv: CHV, *, limit: int = 20) -> list[dict]:
    events: list[dict] = []

    messages = CHVMessage.objects.filter(chv=chv).select_related("sent_by").order_by("-created_at")[:limit]
    for message_record in messages:
        if message_record.status == CHVMessage.STATUS_FAILED:
            event_type = "MESSAGE_FAILED"
            title = "Message failed"
        elif message_record.status == CHVMessage.STATUS_DELIVERED:
            event_type = "MESSAGE_DELIVERED"
            title = "Message delivered"
        elif message_record.status == CHVMessage.STATUS_QUEUED:
            event_type = "MESSAGE_QUEUED"
            title = "Message queued"
        else:
            event_type = "MESSAGE_SENT"
            title = "Message sent"

        detail = message_record.failure_reason or f"{message_record.channel} message recorded for {chv.phone_number}."
        events.append(
            {
                "public_id": str(message_record.public_id),
                "event_type": event_type,
                "category": "MESSAGE",
                "title": title,
                "description": detail,
                "source": "CHV messaging",
                "metadata": {
                    "channel": message_record.channel,
                    "status": message_record.status,
                    "delivery_kind": message_record.delivery_kind,
                    "delivery_backend": message_record.delivery_backend or None,
                    "provider_reference": message_record.provider_reference or None,
                },
                "created_by": message_record.sent_by_id,
                "created_by_username": getattr(message_record.sent_by, "username", None),
                "created_at": message_record.created_at,
            }
        )

    assignment_events = (
        CHVCoverageRequestEvent.objects.filter(assignment__chv=chv)
        .select_related("actor", "assignment", "coverage_request", "coverage_request__ward")
        .order_by("-created_at")[:limit]
    )
    for event in assignment_events:
        if event.action == CHVCoverageRequestEvent.ACTION_ASSIGNMENT_CREATED:
            event_type = "ASSIGNED"
            title = "Assigned to coverage request"
        elif event.action == CHVCoverageRequestEvent.ACTION_ASSIGNMENT_COMPLETED:
            event_type = "STATUS_CHANGED"
            title = "Assignment completed"
        elif event.action == CHVCoverageRequestEvent.ACTION_ASSIGNMENT_CANCELLED:
            event_type = "STATUS_CHANGED"
            title = "Assignment cancelled"
        else:
            event_type = event.action
            title = event.action.replace("_", " ").title()

        description = event.detail or f"{chv.name} assignment activity was recorded for {event.coverage_request.ward.name}."
        events.append(
            {
                "public_id": str(event.public_id),
                "event_type": event_type,
                "category": "ASSIGNMENT",
                "title": title,
                "description": description,
                "source": "Coverage request workflow",
                "metadata": event.metadata or {},
                "created_by": event.actor_id,
                "created_by_username": getattr(event.actor, "username", None),
                "created_at": event.created_at,
            }
        )

    ward_alerts = Alert.objects.filter(ward=chv.ward).select_related("ward").order_by("-created_at")[:limit]
    for alert in ward_alerts:
        events.append(
            {
                "public_id": f"alert-{alert.id}",
                "event_type": "ALERT_LINKED",
                "category": "ALERT",
                "title": "Ward alert recorded",
                "description": f"Alert {getattr(alert, 'public_id', alert.id)} is {alert.status.lower().replace('_', ' ')} for {chv.ward.name}.",
                "source": "Alert workflow",
                "metadata": {
                    "alert_id": alert.id,
                    "alert_public_id": str(getattr(alert, "public_id", "")) if getattr(alert, "public_id", None) else None,
                    "channel": alert.channel,
                    "status": alert.status,
                },
                "created_by": None,
                "created_by_username": None,
                "created_at": alert.created_at,
            }
        )

    sync_items = SyncQueue.objects.filter(phone_number=chv.phone_number).order_by("-created_at")[:limit]
    for sync_item in sync_items:
        detail = "Sync payload processed successfully." if sync_item.status == SyncQueue.STATUS_PROCESSED else (
            sync_item.error_message or f"Sync payload is {sync_item.status.lower()}."
        )
        events.append(
            {
                "public_id": f"sync-{sync_item.id}",
                "event_type": "SYNC_RECEIVED",
                "category": "SYNC",
                "title": "Sync received",
                "description": detail,
                "source": "CHV sync",
                "metadata": {
                    "sync_queue_id": sync_item.id,
                    "status": sync_item.status,
                    "source_device_id": sync_item.source_device_id,
                },
                "created_by": None,
                "created_by_username": None,
                "created_at": sync_item.created_at,
            }
        )

    triage_sessions = TriageSession.objects.filter(phone_number=chv.phone_number).order_by("-created_at")[:limit]
    for triage in triage_sessions:
        triage_description = "Referral needed." if triage.referral_needed else "No referral was recorded."
        events.append(
            {
                "public_id": f"triage-{triage.id}",
                "event_type": "TRIAGE_RECORDED",
                "category": "TRIAGE",
                "title": "Triage recorded",
                "description": f"{triage.channel} triage recorded for {chv.phone_number}. {triage_description}",
                "source": "Triage intake",
                "metadata": {
                    "triage_session_id": triage.id,
                    "referral_needed": triage.referral_needed,
                    "channel": triage.channel,
                },
                "created_by": None,
                "created_by_username": None,
                "created_at": triage.created_at,
            }
        )

    ussd_sessions = UssdSessionLog.objects.filter(phone_number=chv.phone_number).order_by("-created_at")[:limit]
    for ussd in ussd_sessions:
        events.append(
            {
                "public_id": f"ussd-{ussd.id}",
                "event_type": "SYNC_RECEIVED",
                "category": "SYNC",
                "title": "USSD activity recorded",
                "description": f"USSD session {ussd.session_id} reached menu level {ussd.menu_level or 'unknown'}.",
                "source": "USSD log",
                "metadata": {
                    "ussd_session_log_id": ussd.id,
                    "session_id": ussd.session_id,
                    "menu_level": ussd.menu_level,
                },
                "created_by": None,
                "created_by_username": None,
                "created_at": ussd.created_at,
            }
        )

    events.sort(key=lambda item: item["created_at"], reverse=True)
    return events[:limit]


def compute_chv_coverage_expected_response_by(priority: str, *, now=None):
    reference_time = now or timezone.now()
    hours = CHV_COVERAGE_SLA_HOURS.get(priority, CHV_COVERAGE_SLA_HOURS[CHVCoverageRequest.PRIORITY_MEDIUM])
    return reference_time + timedelta(hours=hours)


def record_chv_coverage_request_event(
    coverage_request: CHVCoverageRequest,
    *,
    action: str,
    actor=None,
    old_status: str = "",
    new_status: str = "",
    detail: str = "",
    assignment: CHVAssignment | None = None,
    metadata: dict | None = None,
    ) -> CHVCoverageRequestEvent:
    return CHVCoverageRequestEvent.objects.create(
        coverage_request=coverage_request,
        assignment=assignment,
        actor=actor,
        action=action,
        old_status=old_status,
        new_status=new_status,
        detail=detail,
        metadata=metadata or {},
    )


def schedule_chv_coverage_request_event_side_effects(event: CHVCoverageRequestEvent) -> None:
    if event.action not in {
        CHVCoverageRequestEvent.ACTION_APPROVED,
        CHVCoverageRequestEvent.ACTION_REJECTED,
        CHVCoverageRequestEvent.ACTION_CANCELLED,
        CHVCoverageRequestEvent.ACTION_ASSIGNMENT_CREATED,
        CHVCoverageRequestEvent.ACTION_ASSIGNMENT_COMPLETED,
        CHVCoverageRequestEvent.ACTION_ASSIGNMENT_CANCELLED,
        CHVCoverageRequestEvent.ACTION_RESOLVED,
    }:
        return

    def _dispatch():
        from .notifications import dispatch_chv_coverage_request_event_side_effects

        dispatch_chv_coverage_request_event_side_effects(event.id)

    connection = transaction.get_connection()
    if connection.in_atomic_block:
        transaction.on_commit(_dispatch)
    else:
        _dispatch()


def create_chv_coverage_request(
    *,
    ward: Ward,
    requested_by,
    priority: str,
    reason: str,
    requested_chv_count: int,
    notes: str = "",
    trigger_source: str = CHVCoverageRequest.TRIGGER_SOURCE_MANUAL,
    linked_alerts: list[Alert] | None = None,
) -> CHVCoverageRequest:
    now = timezone.now()
    linked_alerts = linked_alerts or []
    with transaction.atomic():
        request_record = CHVCoverageRequest.objects.create(
            ward=ward,
            requested_by=requested_by,
            status=CHVCoverageRequest.STATUS_OPEN,
            priority=priority,
            trigger_source=trigger_source,
            reason=reason,
            requested_chv_count=requested_chv_count,
            notes=notes,
            expected_response_by=compute_chv_coverage_expected_response_by(priority, now=now),
        )
        if linked_alerts:
            CHVCoverageRequestAlertLink.objects.bulk_create(
                [
                    CHVCoverageRequestAlertLink(
                        coverage_request=request_record,
                        alert=alert,
                        linked_by=requested_by,
                    )
                    for alert in linked_alerts
                ]
            )
            record_chv_coverage_request_event(
                request_record,
                action=CHVCoverageRequestEvent.ACTION_ALERT_LINKAGE_ATTACHED,
                actor=requested_by,
                old_status=request_record.status,
                new_status=request_record.status,
                detail="Linked alert context attached to the coverage request.",
                metadata={
                    "trigger_source": trigger_source,
                    "linked_alert_public_ids": [str(alert.public_id) for alert in linked_alerts],
                    "attachment_mode": "CREATE",
                },
            )
        record_chv_coverage_request_event(
            request_record,
            action=CHVCoverageRequestEvent.ACTION_CREATED,
            actor=requested_by,
            new_status=request_record.status,
            detail=(
                "Coverage request created from alert context."
                if trigger_source == CHVCoverageRequest.TRIGGER_SOURCE_ALERT_DRIVEN
                else "Coverage request created."
            ),
            metadata=(
                {
                    "trigger_source": trigger_source,
                    "linked_alert_public_ids": [str(alert.public_id) for alert in linked_alerts],
                }
                if linked_alerts or trigger_source == CHVCoverageRequest.TRIGGER_SOURCE_ALERT_DRIVEN
                else {"trigger_source": trigger_source}
            ),
        )
        return request_record


def build_chv_coverage_request_from_alert_defaults(*, ward: Ward, alerts: list[Alert]) -> dict:
    if ward.current_risk_level == Ward.RISK_HIGH:
        priority = CHVCoverageRequest.PRIORITY_HIGH
    elif ward.current_risk_level == Ward.RISK_MEDIUM:
        priority = CHVCoverageRequest.PRIORITY_MEDIUM
    else:
        priority = CHVCoverageRequest.PRIORITY_MEDIUM

    return {
        "ward_id": ward.id,
        "ward_public_id": ward.public_id,
        "ward_name": ward.name,
        "trigger_source": CHVCoverageRequest.TRIGGER_SOURCE_ALERT_DRIVEN,
        "linked_alert_public_ids": [alert.public_id for alert in alerts],
        "linked_alerts_summary": alerts,
        "priority": priority,
        "requested_chv_count": 1,
        "reason": "Coverage follow-up requested from linked alert context.",
        "notes": "",
    }


def approve_chv_coverage_request(coverage_request: CHVCoverageRequest, *, actor, reason: str = "") -> CHVCoverageRequest:
    if coverage_request.status != CHVCoverageRequest.STATUS_OPEN:
        raise ValueError("Only open coverage requests can be approved.")

    old_status = coverage_request.status
    coverage_request.status = CHVCoverageRequest.STATUS_APPROVED
    coverage_request.reviewed_by = actor
    coverage_request.reviewed_at = timezone.now()
    coverage_request.review_decision_reason = reason
    coverage_request.save(
        update_fields=[
            "status",
            "reviewed_by",
            "reviewed_at",
            "review_decision_reason",
            "updated_at",
        ]
    )
    event = record_chv_coverage_request_event(
        coverage_request,
        action=CHVCoverageRequestEvent.ACTION_APPROVED,
        actor=actor,
        old_status=old_status,
        new_status=coverage_request.status,
        detail="Coverage request approved.",
    )
    schedule_chv_coverage_request_event_side_effects(event)
    return coverage_request


def reject_chv_coverage_request(coverage_request: CHVCoverageRequest, *, actor, reason: str) -> CHVCoverageRequest:
    if coverage_request.status != CHVCoverageRequest.STATUS_OPEN:
        raise ValueError("Only open coverage requests can be rejected.")
    if not reason.strip():
        raise ValueError("A rejection reason is required.")

    old_status = coverage_request.status
    coverage_request.status = CHVCoverageRequest.STATUS_REJECTED
    coverage_request.reviewed_by = actor
    coverage_request.reviewed_at = timezone.now()
    coverage_request.review_decision_reason = reason.strip()
    coverage_request.save(
        update_fields=[
            "status",
            "reviewed_by",
            "reviewed_at",
            "review_decision_reason",
            "updated_at",
        ]
    )
    event = record_chv_coverage_request_event(
        coverage_request,
        action=CHVCoverageRequestEvent.ACTION_REJECTED,
        actor=actor,
        old_status=old_status,
        new_status=coverage_request.status,
        detail="Coverage request rejected.",
    )
    schedule_chv_coverage_request_event_side_effects(event)
    return coverage_request


def cancel_chv_coverage_request(coverage_request: CHVCoverageRequest, *, actor, reason: str) -> CHVCoverageRequest:
    if coverage_request.status in {
        CHVCoverageRequest.STATUS_REJECTED,
        CHVCoverageRequest.STATUS_CANCELLED,
        CHVCoverageRequest.STATUS_RESOLVED,
    }:
        raise ValueError("This coverage request cannot be cancelled in its current state.")

    if coverage_request.assignments.filter(status=CHVAssignment.STATUS_ACTIVE).exists():
        raise ValueError("Cancel active assignments before cancelling the coverage request.")
    if not reason.strip():
        raise ValueError("A cancellation reason is required.")

    old_status = coverage_request.status
    coverage_request.status = CHVCoverageRequest.STATUS_CANCELLED
    coverage_request.reviewed_by = actor
    coverage_request.reviewed_at = coverage_request.reviewed_at or timezone.now()
    coverage_request.review_decision_reason = reason.strip()
    coverage_request.save(
        update_fields=[
            "status",
            "reviewed_by",
            "reviewed_at",
            "review_decision_reason",
            "updated_at",
        ]
    )
    event = record_chv_coverage_request_event(
        coverage_request,
        action=CHVCoverageRequestEvent.ACTION_CANCELLED,
        actor=actor,
        old_status=old_status,
        new_status=coverage_request.status,
        detail="Coverage request cancelled.",
    )
    schedule_chv_coverage_request_event_side_effects(event)
    return coverage_request


def resolve_chv_coverage_request(coverage_request: CHVCoverageRequest, *, actor, reason: str = "") -> CHVCoverageRequest:
    if coverage_request.status not in {
        CHVCoverageRequest.STATUS_APPROVED,
        CHVCoverageRequest.STATUS_IN_PROGRESS,
    }:
        raise ValueError("Only approved or in-progress coverage requests can be resolved.")
    if coverage_request.assignments.filter(status=CHVAssignment.STATUS_ACTIVE).exists():
        raise ValueError("Complete or cancel active assignments before resolving the coverage request.")

    old_status = coverage_request.status
    coverage_request.status = CHVCoverageRequest.STATUS_RESOLVED
    coverage_request.reviewed_by = actor
    coverage_request.reviewed_at = coverage_request.reviewed_at or timezone.now()
    coverage_request.review_decision_reason = reason.strip() or coverage_request.review_decision_reason
    coverage_request.resolved_at = timezone.now()
    coverage_request.save(
        update_fields=[
            "status",
            "reviewed_by",
            "reviewed_at",
            "review_decision_reason",
            "resolved_at",
            "updated_at",
        ]
    )
    event = record_chv_coverage_request_event(
        coverage_request,
        action=CHVCoverageRequestEvent.ACTION_RESOLVED,
        actor=actor,
        old_status=old_status,
        new_status=coverage_request.status,
        detail="Coverage request resolved.",
    )
    schedule_chv_coverage_request_event_side_effects(event)
    return coverage_request


def assign_chv_to_coverage_request(
    coverage_request: CHVCoverageRequest,
    *,
    chv: CHV,
    actor,
    notes: str = "",
    start_at=None,
) -> CHVAssignment:
    if coverage_request.status != CHVCoverageRequest.STATUS_APPROVED:
        raise ValueError("Only approved coverage requests can receive CHV assignments.")
    if not chv.is_active:
        raise ValueError("Only active CHVs can be assigned.")
    if chv.ward_id != coverage_request.ward_id:
        raise ValueError("Only CHVs linked to the requested ward can be assigned from this workflow.")

    with transaction.atomic():
        assignment = CHVAssignment.objects.create(
            coverage_request=coverage_request,
            ward=coverage_request.ward,
            chv=chv,
            assigned_by=actor,
            status=CHVAssignment.STATUS_ACTIVE,
            start_at=start_at,
            notes=notes,
        )
        old_status = coverage_request.status
        coverage_request.status = CHVCoverageRequest.STATUS_IN_PROGRESS
        coverage_request.save(update_fields=["status", "updated_at"])
        event = record_chv_coverage_request_event(
            coverage_request,
            action=CHVCoverageRequestEvent.ACTION_ASSIGNMENT_CREATED,
            actor=actor,
            old_status=old_status,
            new_status=coverage_request.status,
            detail="CHV assignment created.",
            assignment=assignment,
            metadata={"chv_id": chv.id},
        )
        schedule_chv_coverage_request_event_side_effects(event)
        return assignment


def complete_chv_assignment(assignment: CHVAssignment, *, actor, notes: str = "") -> CHVAssignment:
    if assignment.status != CHVAssignment.STATUS_ACTIVE:
        raise ValueError("Only active assignments can be completed.")

    with transaction.atomic():
        assignment.status = CHVAssignment.STATUS_COMPLETED
        assignment.end_at = assignment.end_at or timezone.now()
        assignment.notes = notes or assignment.notes
        assignment.save(update_fields=["status", "end_at", "notes", "updated_at"])

        coverage_request = assignment.coverage_request
        old_status = coverage_request.status
        if not coverage_request.assignments.exclude(pk=assignment.pk).filter(status=CHVAssignment.STATUS_ACTIVE).exists():
            coverage_request.status = CHVCoverageRequest.STATUS_APPROVED
            coverage_request.save(update_fields=["status", "updated_at"])

        event = record_chv_coverage_request_event(
            coverage_request,
            action=CHVCoverageRequestEvent.ACTION_ASSIGNMENT_COMPLETED,
            actor=actor,
            old_status=old_status,
            new_status=coverage_request.status,
            detail="CHV assignment completed.",
            assignment=assignment,
            metadata={"chv_id": assignment.chv_id},
        )
    schedule_chv_coverage_request_event_side_effects(event)
    return assignment


def cancel_chv_assignment(assignment: CHVAssignment, *, actor, notes: str = "") -> CHVAssignment:
    if assignment.status != CHVAssignment.STATUS_ACTIVE:
        raise ValueError("Only active assignments can be cancelled.")

    with transaction.atomic():
        assignment.status = CHVAssignment.STATUS_CANCELLED
        assignment.end_at = assignment.end_at or timezone.now()
        assignment.notes = notes or assignment.notes
        assignment.save(update_fields=["status", "end_at", "notes", "updated_at"])

        coverage_request = assignment.coverage_request
        old_status = coverage_request.status
        if not coverage_request.assignments.exclude(pk=assignment.pk).filter(status=CHVAssignment.STATUS_ACTIVE).exists():
            coverage_request.status = CHVCoverageRequest.STATUS_APPROVED
            coverage_request.save(update_fields=["status", "updated_at"])

        event = record_chv_coverage_request_event(
            coverage_request,
            action=CHVCoverageRequestEvent.ACTION_ASSIGNMENT_CANCELLED,
            actor=actor,
            old_status=old_status,
            new_status=coverage_request.status,
            detail="CHV assignment cancelled.",
            assignment=assignment,
            metadata={"chv_id": assignment.chv_id},
        )
    schedule_chv_coverage_request_event_side_effects(event)
    return assignment


def run_dashboard_scenario_simulation(*, scenario_id: str, created_by, rainfall_uplift_percent: int = 20, response_delay_hours: int = 12) -> ScenarioSimulationRun:
    require_demo_data_allowed("dashboard scenario simulation")
    wards = list(Ward.objects.filter(is_active=True).order_by("name"))
    ward_results: list[dict] = []
    facility_results: list[dict] = []

    for ward in wards:
        latest_risk = latest_promoted_riskscore_for_ward(ward)
        base_score = latest_risk.score if latest_risk else ward.current_risk_score
        base_cases = latest_risk.predicted_cases if latest_risk else 0
        base_level = latest_risk.risk_level if latest_risk else ward.current_risk_level

        if scenario_id == ScenarioSimulationRun.SCENARIO_RAINFALL_INCREASE:
            score_delta = min(0.18, max(0.04, rainfall_uplift_percent / 1000))
            case_delta = max(1, round((base_cases or 1) * (rainfall_uplift_percent / 100)))
            explanation = f"Rainfall uplift of {rainfall_uplift_percent}% applied to non-production ward prediction sensitivity."
        else:
            score_delta = min(0.12, max(0.03, response_delay_hours / 200))
            case_delta = max(1, round((base_cases or 1) * (response_delay_hours / 24)))
            explanation = f"Response delay of {response_delay_hours} hours applied to non-production follow-up pressure assumptions."

        simulated_score = max(0.0, min(0.99, (base_score or 0) + score_delta))
        simulated_cases = max(base_cases, base_cases + case_delta)
        simulated_level = Ward.RISK_HIGH if simulated_score >= 0.75 else Ward.RISK_MEDIUM if simulated_score >= 0.45 else Ward.RISK_LOW

        ward_results.append(
            {
                "ward_id": ward.id,
                "ward_name": ward.name,
                "baseline_risk_level": base_level,
                "baseline_risk_score": round(base_score or 0, 4),
                "baseline_predicted_cases": base_cases,
                "simulated_risk_level": simulated_level,
                "simulated_risk_score": round(simulated_score, 4),
                "simulated_predicted_cases": simulated_cases,
                "explanation": explanation,
            }
        )

        linked_facilities = list(HealthFacility.objects.filter(ward=ward, is_active=True).order_by("name")[:3])
        for facility in linked_facilities:
            facility_results.append(
                {
                    "facility_id": facility.id,
                    "facility_name": facility.name,
                    "ward_id": ward.id,
                    "ward_name": ward.name,
                    "baseline_capacity_signal": "unknown",
                    "simulated_capacity_signal": "capacity_concern" if simulated_level == Ward.RISK_HIGH else "watch" if simulated_level == Ward.RISK_MEDIUM else "ready",
                    "projected_pressure_score": 90 if simulated_level == Ward.RISK_HIGH else 60 if simulated_level == Ward.RISK_MEDIUM else 25,
                }
            )

    ward_results.sort(key=lambda item: (item["simulated_risk_score"], item["simulated_predicted_cases"]), reverse=True)
    facility_results.sort(key=lambda item: item["projected_pressure_score"], reverse=True)

    summary = {
        "scenario_id": scenario_id,
        "scenario_label": "Rainfall increase" if scenario_id == ScenarioSimulationRun.SCENARIO_RAINFALL_INCREASE else "Response delay",
        "top_impacted_ward_name": ward_results[0]["ward_name"] if ward_results else None,
        "high_risk_ward_count": sum(1 for item in ward_results if item["simulated_risk_level"] == Ward.RISK_HIGH),
        "watch_ward_count": sum(1 for item in ward_results if item["simulated_risk_level"] == Ward.RISK_MEDIUM),
        "capacity_concern_facility_count": sum(1 for item in facility_results if item["simulated_capacity_signal"] == "capacity_concern"),
        "non_production": True,
    }

    expires_at = timezone.now() + timedelta(hours=6)
    return ScenarioSimulationRun.objects.create(
        scenario_id=scenario_id,
        created_by=created_by,
        input_parameters={
            "rainfall_uplift_percent": rainfall_uplift_percent,
            "response_delay_hours": response_delay_hours,
        },
        summary=summary,
        ward_results=ward_results[:10],
        facility_results=facility_results[:10],
        expires_at=expires_at,
    )
