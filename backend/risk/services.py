import logging
from datetime import timedelta

from decouple import config
from django.db import transaction
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
    CHVMessage,
    FacilityContact,
    FacilityReadinessEscalation,
    FacilityReadinessReview,
    FacilityReadinessReviewEvent,
    FacilityReadinessUpdateRequest,
    HealthFacility,
    RiskScore,
    ScenarioSimulationRun,
    SyncQueue,
    TriageSession,
    UssdSessionLog,
    Ward,
)
from .ml.alignment import latest_promoted_riskscore_for_ward, promoted_risk_scores
from .providers import DeliveryResult, get_sms_provider


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
    elif workflow.risk_level == Ward.RISK_HIGH:
        reasons.append("The ward is currently in the promoted high-risk band.")
    elif workflow.risk_level == Ward.RISK_MEDIUM:
        reasons.append("The ward is currently at watch level and needs review before escalation.")
    else:
        reasons.append("Recent workflow state suggests a guided review before taking action.")
    return reasons


def _workflow_payload_for_ward(ward: Ward, latest_risk: RiskScore | None, alerts: list[Alert], *, manual_request_queued_at=None) -> dict:
    delivery_state = _workflow_alert_delivery_state(alerts)
    active_alert_count = len(alerts)
    delivered_alert_count = sum(1 for alert in alerts if alert.status == Alert.STATUS_DELIVERED)
    retry_pending_alert_count = sum(1 for alert in alerts if alert.status == Alert.STATUS_RETRY_PENDING)
    failed_alert_count = sum(1 for alert in alerts if alert.status == Alert.STATUS_FAILED)
    queued_alert_count = sum(1 for alert in alerts if alert.status == Alert.STATUS_QUEUED)

    risk_level = latest_risk.risk_level if latest_risk else ward.current_risk_level
    risk_score = latest_risk.score if latest_risk else ward.current_risk_score
    predicted_cases = latest_risk.predicted_cases if latest_risk else 0

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
    elif risk_level == Ward.RISK_HIGH:
        status = AlertWorkflowState.STATUS_REVIEW_PENDING
        decision_mode = "risk_only"
        confidence = "moderate"
        trigger_severity = AlertWorkflowState.SEVERITY_HIGH
        reason_flagged = f"{ward.name} is the highest current risk ward in the visible scope."
        trigger_reason = f"{ward.name} crossed the promoted high-risk threshold and is waiting for human confirmation."
        recommended_action = "Review the ward now and decide whether to create an operational alert request."
        recommended_response = recommended_action
        expected_operational_effect = "Preserves a human-reviewed trigger path before the system creates response work."
        rules_basis = _workflow_rule_basis(
            "high_risk_review_before_alerting",
            "High-risk ward review before alerting",
            ["promoted high-risk threshold crossed", "no alert created yet"],
        )
        trigger_reason_items = [
            {"label": "Threshold breach", "detail": f"{ward.name} is currently in the promoted high-risk band.", "tone": "danger"}
        ]
        eligible_actions = ["investigate", "view_alerts", "send_message"]
    elif risk_level == Ward.RISK_MEDIUM:
        status = AlertWorkflowState.STATUS_REVIEW_PENDING
        decision_mode = "risk_only"
        confidence = "review"
        trigger_severity = AlertWorkflowState.SEVERITY_MEDIUM
        reason_flagged = f"{ward.name} is the strongest watch-level candidate in the visible scope."
        trigger_reason = f"{ward.name} is currently at watch level and should be reviewed before escalation."
        recommended_action = "Review this watch-level ward and compare adjacent conditions before escalating."
        recommended_response = recommended_action
        expected_operational_effect = "Keeps watch-level wards visible without overstating them as triggered response work."
        rules_basis = _workflow_rule_basis(
            "watch_level_review_before_escalation",
            "Watch-level review before escalation",
            ["watch-level ward visible", "adjacent comparison still required"],
        )
        trigger_reason_items = [
            {"label": "Watch escalation", "detail": f"{ward.name} is currently at watch level and needs closer operator review.", "tone": "warning"}
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
) -> AlertWorkflowState:
    latest_risk = latest_promoted_riskscore_for_ward(ward)
    alerts = list(ward.alerts.select_related("risk_score").order_by("-created_at")[:12])
    payload = _workflow_payload_for_ward(ward, latest_risk, alerts, manual_request_queued_at=manual_request_queued_at)
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


def sync_alert_workflows_for_wards(wards) -> list[AlertWorkflowState]:
    workflows: list[AlertWorkflowState] = []
    for ward in wards:
        workflow = sync_alert_workflow_for_ward(ward)
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


def build_guided_trigger_preview(ward: Ward, trigger_type: str, message_override: str | None = None) -> dict:
    workflow = sync_alert_workflow_for_ward(ward, record_event=False)
    message_preview, message_mode = build_guided_trigger_message(
        ward,
        trigger_type,
        workflow=workflow,
        message_override=message_override,
    )

    return {
        "message_preview": message_preview,
        "message_mode": message_mode,
        "supports_editing": True,
        "channel_defaults": ["DASHBOARD", "SMS_CHV"],
        "recipient_preview": {
            "chv_count": CHV.objects.filter(ward=ward, is_active=True).count(),
        },
        "recommended_action": workflow.recommended_action,
    }


def alert_retry_delay() -> timedelta:
    return timedelta(minutes=config("ALERT_RETRY_DELAY_MINUTES", cast=int, default=5))


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


def create_chv_message(chv: CHV, *, message_body: str, sent_by=None, channel: str = CHVMessage.CHANNEL_SMS) -> CHVMessage:
    mode = resolve_chv_message_mode()
    if mode == "UNAVAILABLE":
        raise ValueError("Messaging is not available in this environment.")

    resolved_delivery_kind = resolve_chv_message_delivery_kind()
    if mode == "QUEUE_ONLY":
        delivery_kind = CHVMessage.DELIVERY_KIND_QUEUE_ONLY
    else:
        delivery_kind = resolved_delivery_kind
    delivery_backend = config("SMS_PROVIDER", default="stub").strip().lower() or "stub"
    message_record = CHVMessage.objects.create(
        chv=chv,
        ward=chv.ward,
        sent_by=sent_by,
        channel=channel,
        message_body=message_body,
        delivery_kind=delivery_kind,
        delivery_backend=delivery_backend if delivery_kind in {CHVMessage.DELIVERY_KIND_LIVE, CHVMessage.DELIVERY_KIND_SIMULATED} else "",
        status=CHVMessage.STATUS_QUEUED if mode == "QUEUE_ONLY" else CHVMessage.STATUS_SENT,
    )

    if mode != "SEND":
        return message_record

    result = send_sms(chv.phone_number, message_body)
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
) -> list[Alert]:
    ward = risk_score.ward
    alerts_created: list[Alert] = []
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
    dashboard_alert = Alert.objects.create(
        ward=ward,
        risk_score=risk_score,
        channel=Alert.CHANNEL_DASHBOARD,
        recipient="dashboard",
        message=message,
        status=Alert.STATUS_DELIVERED,
        delivery_backend="internal-dashboard",
        guided_request_metadata=guided_request_metadata or {},
        attempt_count=1,
        max_attempts=1,
        last_attempted_at=delivered_at,
        sent_at=delivered_at,
    )
    alerts_created.append(dashboard_alert)

    if send_sms_enabled:
        chvs = CHV.objects.filter(ward=ward, is_active=True)

        for chv in chvs:
            alert = Alert.objects.create(
                ward=ward,
                risk_score=risk_score,
                channel=Alert.CHANNEL_SMS,
                recipient=chv.phone_number,
                message=message,
                status=Alert.STATUS_QUEUED,
                delivery_backend=config("SMS_PROVIDER", default="stub").strip().lower() or "stub",
                guided_request_metadata=guided_request_metadata or {},
                max_attempts=config("ALERT_MAX_ATTEMPTS", cast=int, default=3),
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

    sync_alert_workflow_for_ward(ward)
    return alerts_created


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
) -> list[Alert]:
    return create_alerts_for_riskscore(
        risk_score,
        send_sms_enabled=send_sms_enabled,
        trigger_type=trigger_type,
        message_override=message_override,
        guided_request_metadata=guided_request_metadata,
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
    if risk_score_value is not None and risk_score_value >= 75:
        risk_context = {
            "level_label": "High Risk",
            "trend_label": "Escalating",
            "summary": "Threshold crossed in the recorded risk score. Review linked ward and delivery records closely.",
            "recorded_risk_score": risk_score_value,
            "threshold": 75,
            "mode": "derived_from_risk_score",
        }
    elif risk_score_value is not None and risk_score_value >= 40:
        risk_context = {
            "level_label": "Medium Risk",
            "trend_label": "Monitoring",
            "summary": "Watch closely and prepare ward follow-up if indicators rise again.",
            "recorded_risk_score": risk_score_value,
            "threshold": 75,
            "mode": "derived_from_risk_score",
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
            "threshold": 75 if risk_score_value is not None else None,
            "mode": "derived_from_risk_score" if risk_score_value is not None else "unavailable",
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
            "preview_text": preview_text or alert.message,
        }
    elif message_mode == MESSAGE_MODE_BACKEND_GENERATED:
        message_source = {
            "mode": MESSAGE_MODE_BACKEND_GENERATED,
            "label": "System-generated draft",
            "summary": "The queued alert used the system-generated guided message without operator edits.",
            "trigger_type": selected_trigger_type,
            "preview_text": preview_text or alert.message,
        }
    else:
        message_source = {
            "mode": "unavailable",
            "label": "Message source unavailable",
            "summary": "This alert record does not yet carry guided-flow message-source metadata.",
            "trigger_type": "",
            "preview_text": "",
        }

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
                f"Recipient: {alert.recipient}",
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
        "chv_response_summary": chv_response_summary,
        "facility_response_summary": facility_response_summary,
        "recommended_next_action": recommended_next_action,
        "last_updated_at": lifecycle["last_updated_at"],
        "current_state": current_state,
        "freshness": freshness,
        "timeline": timeline,
        "capabilities": capabilities,
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

    generated_at = latest_risk.generated_at if latest_risk else None
    is_stale = True
    if generated_at is not None:
        is_stale = (timezone.now() - generated_at).total_seconds() / 60 > stale_threshold_minutes

    current_risk = {
        "risk_level": latest_risk.risk_level if latest_risk else ward.current_risk_level,
        "risk_score": latest_risk.score if latest_risk else ward.current_risk_score,
        "predicted_cases": latest_risk.predicted_cases if latest_risk else 0,
        "generated_at": generated_at,
        "source": latest_risk.source if latest_risk else None,
        "model_version": latest_risk.model_version if latest_risk else None,
        "model_run_status": latest_risk.model_run.status if latest_risk and latest_risk.model_run else None,
    }

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
            driver_items.append(
                {
                    "text": f"Rainfall is elevated at {latest_risk.rainfall_mm:.0f} mm in the latest record.",
                    "tone": "critical",
                    "source_field": "rainfall_mm",
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
    return getattr(user, "role", None) in {"ADMIN", "SUPERVISOR"}


def _facility_user_can_escalate_county_review(user) -> bool:
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    return bool(getattr(user, "is_superuser", False) or getattr(user, "role", None) == "ADMIN")


def _facility_has_county_review_queue() -> bool:
    return True


def _facility_user_can_open_chv_operations(user) -> bool:
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    return getattr(user, "role", None) in {"ADMIN", "SUPERVISOR"}


def _facility_linked_alert_payload(alert: Alert) -> dict:
    return {
        "id": alert.id,
        "public_id": str(alert.public_id),
        "ward_id": alert.ward_id,
        "ward_name": alert.ward.name,
        "status": alert.status,
        "channel": alert.channel,
        "recipient": alert.recipient,
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


@transaction.atomic
def create_facility_readiness_update_request(
    review: FacilityReadinessReview,
    *,
    actor=None,
    message_body: str = "",
    channel: str | None = None,
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

    body = message_body.strip() or _default_facility_update_request_message(review)
    update_request = FacilityReadinessUpdateRequest.objects.create(
        review=review,
        facility=review.facility,
        contact=contact,
        requested_by=actor if getattr(actor, "is_authenticated", False) else None,
        channel=resolved_channel,
        message_body=body,
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
    active_review = active_facility_readiness_review_for_facility(facility)
    active_update_request = active_facility_readiness_update_request_for_facility(facility)
    active_escalation = active_facility_readiness_escalation_for_facility(facility)
    linked_alerts = [_facility_linked_alert_payload(alert) for alert in related_alerts]
    chv_operations = _facility_chv_operations_navigation_payload(facility, user=user)
    promoted_forecast = latest_promoted_facility_forecast_for_facility(facility)
    latest_forecast = promoted_forecast or latest_facility_forecast_for_facility(facility)

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

    if latest_forecast and latest_forecast.forecast_run.status == latest_forecast.forecast_run.STATUS_SUCCESS:
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

    freshness_state = _facility_freshness_state(
        latest_forecast.generated_at if latest_forecast else facility.updated_at
    )

    is_stale = True
    freshness_updated_at = latest_forecast.generated_at if latest_forecast else facility.updated_at
    if freshness_updated_at is not None:
        is_stale = (timezone.now() - freshness_updated_at).total_seconds() / 60 > stale_threshold_minutes

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
                "description": alert.message,
                "timestamp": alert.created_at,
                "tone": (
                    "danger"
                    if alert.status == Alert.STATUS_FAILED
                    else "success"
                    if alert.status == Alert.STATUS_DELIVERED
                    else "warning"
                ),
                "category": "alert",
                "meta": f"Recipient: {alert.recipient}",
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
        "freshness": {
            "updated_at": freshness_updated_at,
            "is_stale": is_stale,
            "stale_threshold_minutes": stale_threshold_minutes,
            "mode": "derived_from_forecast_or_facility_timestamp",
        },
        "decision_summary": decision_summary,
        "timeline": timeline,
        "contact": verified_contact,
        "active_review": active_review,
        "active_update_request": active_update_request,
        "active_escalation": active_escalation,
        "linked_alerts": linked_alerts,
        "chv_operations": chv_operations,
        "capabilities": {
            "can_view_contacts": verified_contact is not None,
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


def process_sync_payload(
    *,
    ward: Ward,
    phone_number: str,
    source_device_id: str,
    payload: dict,
) -> tuple[SyncQueue, TriageSession, bool]:
    client_submission_id = (payload.get("client_submission_id") or "").strip()
    if not client_submission_id:
        raise ValueError("client_submission_id is required.")

    existing_sync_item = (
        SyncQueue.objects.select_related("triage_session")
        .filter(
            source_device_id=source_device_id,
            client_submission_id=client_submission_id,
        )
        .first()
    )
    if existing_sync_item and existing_sync_item.triage_session:
        return existing_sync_item, existing_sync_item.triage_session, True

    sync_item = SyncQueue.objects.create(
        source_device_id=source_device_id,
        client_submission_id=client_submission_id,
        phone_number=phone_number,
        ward=ward,
        payload=payload,
        status=SyncQueue.STATUS_PENDING,
    )

    try:
        triage_session = create_triage_session(
            ward=ward,
            phone_number=phone_number,
            diarrhea=payload.get("diarrhea", False),
            vomiting=payload.get("vomiting", False),
            dehydration=payload.get("dehydration", False),
            fever=payload.get("fever", False),
            text_input=payload.get("text_input", ""),
            channel="OFFLINE_SYNC",
        )
        sync_item.status = SyncQueue.STATUS_PROCESSED
        sync_item.triage_session = triage_session
        sync_item.processed_at = timezone.now()
        sync_item.save(update_fields=["status", "triage_session", "processed_at"])
        return sync_item, triage_session, False
    except Exception as exc:
        sync_item.status = SyncQueue.STATUS_FAILED
        sync_item.error_message = str(exc)
        sync_item.processed_at = timezone.now()
        sync_item.save(update_fields=["status", "error_message", "processed_at"])
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
