from __future__ import annotations

from collections import defaultdict

from django.db.models import Q
from django.utils import timezone

from risk.ml.alignment import is_promoted_model_run
from risk.models import Alert, PreparednessAction, PreparednessActionEvent, Ward
from risk.preparedness_action_evidence import completion_evidence_has_substance


PREPAREDNESS_ACTION_LEDGER_AUDIT_SCHEMA_VERSION = "preparedness-action-ledger-audit-v1"

COMPLETION_EVIDENCE_REQUIRED_ACTION_TYPES = {
    PreparednessAction.ACTION_CHV_FOLLOW_UP,
    PreparednessAction.ACTION_HOUSEHOLD_PREVENTION_MESSAGE,
    PreparednessAction.ACTION_FACILITY_ORS_REVIEW,
    PreparednessAction.ACTION_FACILITY_STAFFING_REVIEW,
    PreparednessAction.ACTION_COUNTY_ESCALATION,
    PreparednessAction.ACTION_WATER_TREATMENT_DISTRIBUTION,
    PreparednessAction.ACTION_SURVEILLANCE_FOLLOW_UP,
    PreparednessAction.ACTION_FIELD_VERIFICATION,
}

SOURCE_FK_FIELD_BY_TRIGGER = {
    PreparednessAction.SOURCE_ALERT: "alert",
    PreparednessAction.SOURCE_ALERT_WORKFLOW: "alert_workflow",
    PreparednessAction.SOURCE_RISK_SCORE: "risk_score",
    PreparednessAction.SOURCE_CHV_COVERAGE_REQUEST: "chv_coverage_request",
    PreparednessAction.SOURCE_FACILITY_READINESS_REVIEW: "facility_readiness_review",
    PreparednessAction.SOURCE_FACILITY_UPDATE_REQUEST: "facility_update_request",
    PreparednessAction.SOURCE_FACILITY_ESCALATION: "facility_escalation",
}

PROMOTED_ALERT_ACTION_SATISFYING_STATUSES = {
    PreparednessAction.STATUS_QUEUED,
    PreparednessAction.STATUS_ASSIGNED,
    PreparednessAction.STATUS_ACKNOWLEDGED,
    PreparednessAction.STATUS_IN_PROGRESS,
    PreparednessAction.STATUS_BLOCKED,
    PreparednessAction.STATUS_ESCALATED,
    PreparednessAction.STATUS_COMPLETED,
}

OPERATING_RULES = [
    "Live promoted high-risk alerts must create or link at least one non-draft, non-cancelled preparedness action before review closure.",
    "Alert delivery status and preparedness action completion are separate facts; one must not mask the other.",
    "Every preparedness action must have auditable lifecycle events for creation and the current terminal or active state.",
    "Active overdue preparedness actions require escalation status, escalation metadata, or an escalation event.",
    "Completed preparedness actions require structured, substantive non-boilerplate completion evidence.",
    "Outcome feedback may count completed response only when substantive completion evidence is present.",
    "User-assigned preparedness action owners must be active admins or belong to the action ward.",
    "Active non-draft preparedness actions must have due and SLA target timestamps.",
    "Any action with a user or team owner must have an auditable assignment event and cannot remain draft or queued.",
    "Repeated source triggers must reuse one active action for the same action type, trigger type, and normalized source ref.",
    "Non-manual source-triggered actions must keep source lineage through source_trigger_ref and/or the matching source FK.",
    "Source-linked facility, CHV, alert, risk-score, and workflow records must stay inside the action ward boundary.",
    "Alert, workflow, risk-score, model-run, and decision-policy lineage must be internally consistent.",
]


def _action_ref(action: PreparednessAction) -> dict:
    return {
        "public_id": str(action.public_id),
        "action_type": action.action_type,
        "source_trigger_type": action.source_trigger_type,
        "source_trigger_ref": action.source_trigger_ref,
        "status": action.status,
        "ward_id": action.ward_id,
        "ward_name": action.ward.name,
        "priority": action.priority,
        "due_at": action.due_at,
    }


def _alert_ref(alert: Alert) -> dict:
    risk_score = alert.risk_score
    model_run = risk_score.model_run if risk_score and risk_score.model_run_id else None
    return {
        "id": alert.id,
        "public_id": str(alert.public_id),
        "ward_id": alert.ward_id,
        "ward_name": alert.ward.name,
        "status": alert.status,
        "risk_score_id": alert.risk_score_id,
        "risk_level": risk_score.risk_level if risk_score else "",
        "model_run_id": model_run.id if model_run else None,
        "model_version": model_run.model_version if model_run else "",
        "created_at": alert.created_at,
    }


def _source_identity_for_action(action: PreparednessAction) -> str:
    source_trigger_ref = action.source_trigger_ref.strip()
    if source_trigger_ref:
        return source_trigger_ref.casefold()

    if action.source_trigger_type == PreparednessAction.SOURCE_ALERT and action.alert_id:
        return f"alert:{action.alert.public_id}"
    if action.source_trigger_type == PreparednessAction.SOURCE_ALERT_WORKFLOW and action.alert_workflow_id:
        return f"alert_workflow:{action.alert_workflow.public_id}"
    if action.source_trigger_type == PreparednessAction.SOURCE_RISK_SCORE and action.risk_score_id:
        return f"risk_score:{action.risk_score_id}"
    if (
        action.source_trigger_type == PreparednessAction.SOURCE_CHV_COVERAGE_REQUEST
        and action.chv_coverage_request_id
    ):
        return f"chv_coverage_request:{action.chv_coverage_request.public_id}"
    if (
        action.source_trigger_type == PreparednessAction.SOURCE_FACILITY_READINESS_REVIEW
        and action.facility_readiness_review_id
    ):
        return f"facility_readiness_review:{action.facility_readiness_review.public_id}"
    if (
        action.source_trigger_type == PreparednessAction.SOURCE_FACILITY_UPDATE_REQUEST
        and action.facility_update_request_id
    ):
        return f"facility_update_request:{action.facility_update_request.public_id}"
    if action.source_trigger_type == PreparednessAction.SOURCE_FACILITY_ESCALATION and action.facility_escalation_id:
        return f"facility_escalation:{action.facility_escalation.public_id}"

    return ""


def _check_result(*, check_id: str, status: str, answer: str, evidence: dict, gaps: list[str]) -> dict:
    return {
        "id": check_id,
        "status": status,
        "answer": answer,
        "evidence": evidence,
        "gaps": gaps,
    }


def _status_from_findings(findings: list) -> str:
    return "fail" if findings else "pass"


def _high_risk_promoted_alerts_without_actions_check() -> dict:
    evaluated_alerts = []
    missing_alerts = []
    alerts = (
        Alert.objects.select_related("ward", "risk_score", "risk_score__model_run")
        .filter(risk_score__risk_level=Ward.RISK_HIGH)
        .order_by("-created_at", "-id")
    )
    for alert in alerts:
        if not is_promoted_model_run(alert.risk_score.model_run if alert.risk_score_id else None):
            continue
        evaluated_alerts.append(alert)
        alert_ref = f"alert:{alert.public_id}"
        linked_action_exists = PreparednessAction.objects.filter(
            (
                Q(alert=alert)
                | Q(source_trigger_type=PreparednessAction.SOURCE_ALERT, source_trigger_ref=alert_ref)
                | Q(risk_score=alert.risk_score, alert=alert)
            ),
            status__in=PROMOTED_ALERT_ACTION_SATISFYING_STATUSES,
        ).exists()
        if not linked_action_exists:
            missing_alerts.append(_alert_ref(alert))

    return _check_result(
        check_id="high_risk_promoted_alerts_without_action_tasks",
        status=_status_from_findings(missing_alerts),
        answer=(
            "Every live-promoted high-risk alert has a linked non-draft, non-cancelled preparedness action."
            if not missing_alerts
            else "One or more live-promoted high-risk alerts lack linked non-draft, non-cancelled preparedness actions."
        ),
        evidence={
            "evaluated_alert_count": len(evaluated_alerts),
            "missing_action_alert_count": len(missing_alerts),
            "missing_action_alerts": missing_alerts[:25],
            "satisfying_action_statuses": sorted(PROMOTED_ALERT_ACTION_SATISFYING_STATUSES),
        },
        gaps=["live_promoted_high_risk_alert_without_preparedness_action"] if missing_alerts else [],
    )


def _overdue_actions_without_escalation_check(now) -> dict:
    overdue_actions = list(
        PreparednessAction.objects.select_related("ward")
        .filter(status__in=PreparednessAction.ACTIVE_STATUSES, due_at__lt=now)
        .order_by("due_at", "id")
    )
    escalated_action_ids = set(
        PreparednessActionEvent.objects.filter(
            preparedness_action_id__in=[action.id for action in overdue_actions],
            event_type=PreparednessActionEvent.EVENT_ESCALATED,
        ).values_list("preparedness_action_id", flat=True)
    )
    findings = [
        _action_ref(action)
        for action in overdue_actions
        if not (
            action.status == PreparednessAction.STATUS_ESCALATED
            or action.escalated_at
            or action.escalation_metadata
            or action.id in escalated_action_ids
        )
    ]
    return _check_result(
        check_id="overdue_actions_without_escalation",
        status=_status_from_findings(findings),
        answer=(
            "Every active overdue action has explicit escalation evidence."
            if not findings
            else "One or more active overdue actions lack escalation evidence."
        ),
        evidence={
            "active_overdue_action_count": len(overdue_actions),
            "overdue_without_escalation_count": len(findings),
            "overdue_without_escalation_actions": findings[:25],
        },
        gaps=["active_overdue_action_without_escalation"] if findings else [],
    )


def _completed_actions_without_evidence_check() -> dict:
    completed_actions = list(
        PreparednessAction.objects.select_related("ward")
        .filter(status=PreparednessAction.STATUS_COMPLETED, action_type__in=COMPLETION_EVIDENCE_REQUIRED_ACTION_TYPES)
        .order_by("-completed_at", "-updated_at", "-id")
    )
    findings = [
        _action_ref(action)
        for action in completed_actions
        if not completion_evidence_has_substance(action.completion_evidence)
    ]
    return _check_result(
        check_id="completed_actions_without_required_evidence",
        status=_status_from_findings(findings),
        answer=(
            "Every completed evidence-required action has substantive completion evidence."
            if not findings
            else "One or more completed evidence-required actions are missing substantive completion evidence."
        ),
        evidence={
            "completed_evidence_required_action_count": len(completed_actions),
            "completed_missing_evidence_count": len(findings),
            "completed_missing_evidence_actions": findings[:25],
            "evidence_required_action_types": sorted(COMPLETION_EVIDENCE_REQUIRED_ACTION_TYPES),
        },
        gaps=["completed_preparedness_action_missing_evidence"] if findings else [],
    )


def _lifecycle_events_integrity_check() -> dict:
    status_event_by_status = {
        PreparednessAction.STATUS_ASSIGNED: PreparednessActionEvent.EVENT_ASSIGNED,
        PreparednessAction.STATUS_ACKNOWLEDGED: PreparednessActionEvent.EVENT_ACKNOWLEDGED,
        PreparednessAction.STATUS_IN_PROGRESS: PreparednessActionEvent.EVENT_IN_PROGRESS,
        PreparednessAction.STATUS_COMPLETED: PreparednessActionEvent.EVENT_COMPLETED,
        PreparednessAction.STATUS_BLOCKED: PreparednessActionEvent.EVENT_BLOCKED,
        PreparednessAction.STATUS_CANCELLED: PreparednessActionEvent.EVENT_CANCELLED,
        PreparednessAction.STATUS_ESCALATED: PreparednessActionEvent.EVENT_ESCALATED,
        PreparednessAction.STATUS_EXPIRED: PreparednessActionEvent.EVENT_EXPIRED,
    }
    actions = (
        PreparednessAction.objects.select_related("ward")
        .prefetch_related("events")
        .all()
        .order_by("-created_at", "-id")
    )
    findings = []
    for action in actions:
        event_types = {event.event_type for event in action.events.all()}
        gaps = []
        if PreparednessActionEvent.EVENT_CREATED not in event_types:
            gaps.append("missing_created_event")
        expected_status_event = status_event_by_status.get(action.status)
        if expected_status_event and expected_status_event not in event_types:
            gaps.append(f"missing_{expected_status_event.lower()}_event")
        if action.status == PreparednessAction.STATUS_COMPLETED and action.completed_at is None:
            gaps.append("completed_status_missing_completed_at")
        if action.status == PreparednessAction.STATUS_CANCELLED:
            if action.cancelled_at is None:
                gaps.append("cancelled_status_missing_cancelled_at")
            if not action.cancellation_reason.strip():
                gaps.append("cancelled_status_missing_reason")
        if action.status == PreparednessAction.STATUS_ESCALATED and action.escalated_at is None:
            gaps.append("escalated_status_missing_escalated_at")
        if gaps:
            findings.append(
                {
                    **_action_ref(action),
                    "lifecycle_gaps": gaps,
                }
            )

    return _check_result(
        check_id="lifecycle_events_are_auditable",
        status=_status_from_findings(findings),
        answer=(
            "Every preparedness action has required lifecycle events and status timestamps."
            if not findings
            else "One or more preparedness actions are missing required lifecycle events or status timestamps."
        ),
        evidence={
            "audited_action_count": actions.count(),
            "lifecycle_gap_count": len(findings),
            "lifecycle_gap_actions": findings[:25],
        },
        gaps=["preparedness_action_lifecycle_not_auditable"] if findings else [],
    )


def _due_sla_integrity_check() -> dict:
    actions = (
        PreparednessAction.objects.select_related("ward")
        .filter(status__in=PreparednessAction.ACTIVE_STATUSES)
        .exclude(status=PreparednessAction.STATUS_DRAFT)
        .order_by("due_at", "-created_at", "-id")
    )
    findings = []
    for action in actions:
        gaps = []
        if action.due_at is None:
            gaps.append("missing_due_at")
        if action.sla_target_at is None:
            gaps.append("missing_sla_target_at")
        if gaps:
            findings.append(
                {
                    **_action_ref(action),
                    "due_sla_gaps": gaps,
                    "sla_target_at": action.sla_target_at,
                }
            )

    return _check_result(
        check_id="active_actions_have_due_and_sla_targets",
        status=_status_from_findings(findings),
        answer=(
            "Every active non-draft preparedness action has due and SLA target timestamps."
            if not findings
            else "One or more active non-draft preparedness actions are missing due or SLA target timestamps."
        ),
        evidence={
            "audited_active_non_draft_action_count": actions.count(),
            "missing_due_or_sla_count": len(findings),
            "missing_due_or_sla_actions": findings[:25],
        },
        gaps=["active_preparedness_action_missing_due_or_sla_target"] if findings else [],
    )


def _assignment_state_integrity_check() -> dict:
    actions = (
        PreparednessAction.objects.select_related("ward", "assigned_to")
        .prefetch_related("events")
        .all()
        .order_by("-created_at", "-id")
    )
    findings = []
    for action in actions:
        event_types = {event.event_type for event in action.events.all()}
        has_owner = bool(action.assigned_to_id or action.assigned_to_team.strip())
        gaps = []
        if action.status == PreparednessAction.STATUS_ASSIGNED and not has_owner:
            gaps.append("assigned_status_without_owner")
        if has_owner and PreparednessActionEvent.EVENT_ASSIGNED not in event_types:
            gaps.append("owner_without_assignment_event")
        if has_owner and action.status in {PreparednessAction.STATUS_DRAFT, PreparednessAction.STATUS_QUEUED}:
            gaps.append("draft_or_queued_action_has_owner")
        if gaps:
            findings.append(
                {
                    **_action_ref(action),
                    "assigned_to": action.assigned_to_id,
                    "assigned_to_team": action.assigned_to_team,
                    "assignment_gaps": gaps,
                }
            )

    return _check_result(
        check_id="assignment_state_is_auditable",
        status=_status_from_findings(findings),
        answer=(
            "Every assigned preparedness action has owner state aligned with assignment events."
            if not findings
            else "One or more preparedness actions have owner state that is not auditable."
        ),
        evidence={
            "audited_action_count": actions.count(),
            "assignment_gap_count": len(findings),
            "assignment_gap_actions": findings[:25],
        },
        gaps=["preparedness_action_assignment_state_not_auditable"] if findings else [],
    )


def _duplicate_active_source_actions_check() -> dict:
    groups = defaultdict(list)
    active_actions = (
        PreparednessAction.objects.select_related(
            "ward",
            "alert",
            "alert_workflow",
            "risk_score",
            "risk_score__model_run",
            "model_run",
            "facility_readiness_review",
            "facility_update_request",
            "facility_escalation",
            "chv_coverage_request",
        )
        .filter(status__in=PreparednessAction.ACTIVE_STATUSES)
        .order_by("action_type", "source_trigger_type", "source_trigger_ref", "id")
    )
    for action in active_actions:
        normalized_ref = _source_identity_for_action(action)
        if not normalized_ref:
            continue
        groups[(action.action_type, action.source_trigger_type, normalized_ref)].append(action)

    duplicate_groups = [
        {
            "action_type": action_type,
            "source_trigger_type": source_trigger_type,
            "normalized_source_trigger_ref": source_trigger_ref,
            "active_count": len(actions),
            "actions": [_action_ref(action) for action in actions],
        }
        for (action_type, source_trigger_type, source_trigger_ref), actions in groups.items()
        if len(actions) > 1
    ]
    return _check_result(
        check_id="duplicate_active_actions_for_same_source_trigger",
        status=_status_from_findings(duplicate_groups),
        answer=(
            "No duplicate active source-triggered preparedness actions were found."
            if not duplicate_groups
            else "One or more normalized source triggers have duplicate active preparedness actions."
        ),
        evidence={
            "active_source_trigger_group_count": len(groups),
            "duplicate_group_count": len(duplicate_groups),
            "duplicate_groups": duplicate_groups[:25],
        },
        gaps=["duplicate_active_preparedness_actions_for_source_trigger"] if duplicate_groups else [],
    )


def _action_has_any_source_fk(action: PreparednessAction) -> bool:
    return any(
        getattr(action, f"{field_name}_id", None)
        for field_name in [
            "alert",
            "alert_workflow",
            "risk_score",
            "facility_readiness_review",
            "facility_update_request",
            "facility_escalation",
            "chv_coverage_request",
        ]
    )


def _source_lineage_findings_for_action(action: PreparednessAction) -> list[str]:
    findings = []
    required_fk_field = SOURCE_FK_FIELD_BY_TRIGGER.get(action.source_trigger_type)
    if required_fk_field and getattr(action, f"{required_fk_field}_id", None) is None:
        findings.append(f"missing_{required_fk_field}_fk_for_{action.source_trigger_type}_source")

    if (
        action.source_trigger_type != PreparednessAction.SOURCE_MANUAL
        and not action.source_trigger_ref.strip()
        and not _action_has_any_source_fk(action)
    ):
        findings.append("missing_source_trigger_ref_or_source_fk")

    if (
        action.source_trigger_type in {PreparednessAction.SOURCE_SYSTEM, PreparednessAction.SOURCE_OUTCOME_FEEDBACK}
        and not action.source_trigger_ref.strip()
        and not action.lineage_metadata
    ):
        findings.append(f"{action.source_trigger_type}_action_missing_lineage_metadata")

    ward_mismatch_checks = [
        ("facility", action.facility.ward_id if action.facility_id else None),
        ("chv", action.chv.ward_id if action.chv_id else None),
        ("alert", action.alert.ward_id if action.alert_id else None),
        ("alert_workflow", action.alert_workflow.ward_id if action.alert_workflow_id else None),
        ("risk_score", action.risk_score.ward_id if action.risk_score_id else None),
        (
            "facility_readiness_review",
            action.facility_readiness_review.ward_id if action.facility_readiness_review_id else None,
        ),
        (
            "facility_update_request",
            action.facility_update_request.facility.ward_id if action.facility_update_request_id else None,
        ),
        ("facility_escalation", action.facility_escalation.ward_id if action.facility_escalation_id else None),
        ("chv_coverage_request", action.chv_coverage_request.ward_id if action.chv_coverage_request_id else None),
    ]
    for source_name, source_ward_id in ward_mismatch_checks:
        if source_ward_id is not None and source_ward_id != action.ward_id:
            findings.append(f"{source_name}_ward_mismatch")
    if (
        action.alert_id
        and action.risk_score_id
        and action.alert.risk_score_id
        and action.alert.risk_score_id != action.risk_score_id
    ):
        findings.append("alert_risk_score_mismatch")
    if (
        action.risk_score_id
        and action.model_run_id
        and action.risk_score.model_run_id
        and action.risk_score.model_run_id != action.model_run_id
    ):
        findings.append("risk_score_model_run_mismatch")
    expected_policy_version = (
        (action.risk_score.decision_policy or {}).get("policy_version", "")
        if action.risk_score_id
        else ""
    )
    if action.risk_score_id and expected_policy_version and action.decision_policy_version != expected_policy_version:
        findings.append("decision_policy_version_mismatch")
    if action.assigned_to_id:
        if not action.assigned_to.is_active:
            findings.append("assigned_owner_inactive")
        if (
            action.assigned_to.role != "ADMIN"
            and not action.assigned_to.is_superuser
            and action.assigned_to.ward_id != action.ward_id
        ):
            findings.append("assigned_owner_ward_mismatch")
    return findings


def _detached_or_cross_ward_actions_check() -> dict:
    actions = (
        PreparednessAction.objects.select_related(
            "ward",
            "facility",
            "chv",
            "alert",
            "alert_workflow",
            "risk_score",
            "facility_readiness_review",
            "facility_update_request",
            "facility_update_request__facility",
            "facility_escalation",
            "chv_coverage_request",
            "assigned_to",
        )
        .all()
        .order_by("-created_at", "-id")
    )
    findings = []
    for action in actions:
        action_findings = _source_lineage_findings_for_action(action)
        if action_findings:
            findings.append(
                {
                    **_action_ref(action),
                    "lineage_gaps": action_findings,
                }
            )
    return _check_result(
        check_id="actions_detached_from_ward_or_source_lineage",
        status=_status_from_findings(findings),
        answer=(
            "Preparedness actions keep source lineage inside the action ward boundary."
            if not findings
            else "One or more preparedness actions are detached from source lineage or cross ward boundaries."
        ),
        evidence={
            "audited_action_count": actions.count(),
            "detached_or_cross_ward_action_count": len(findings),
            "detached_or_cross_ward_actions": findings[:25],
        },
        gaps=["preparedness_action_detached_from_source_or_ward_lineage"] if findings else [],
    )


def _record_totals(now) -> dict:
    high_risk_promoted_alert_count = 0
    for alert in Alert.objects.select_related("risk_score", "risk_score__model_run").filter(
        risk_score__risk_level=Ward.RISK_HIGH
    ):
        if is_promoted_model_run(alert.risk_score.model_run if alert.risk_score_id else None):
            high_risk_promoted_alert_count += 1

    return {
        "alerts": Alert.objects.count(),
        "high_risk_promoted_alerts": high_risk_promoted_alert_count,
        "preparedness_actions": PreparednessAction.objects.count(),
        "active_preparedness_actions": PreparednessAction.objects.filter(
            status__in=PreparednessAction.ACTIVE_STATUSES
        ).count(),
        "active_overdue_preparedness_actions": PreparednessAction.objects.filter(
            status__in=PreparednessAction.ACTIVE_STATUSES,
            due_at__lt=now,
        ).count(),
        "completed_preparedness_actions": PreparednessAction.objects.filter(
            status=PreparednessAction.STATUS_COMPLETED
        ).count(),
    }


def _overall_status(checks: list[dict]) -> str:
    if any(check["status"] == "fail" for check in checks):
        return "fail"
    if any(check["status"] == "warning" for check in checks):
        return "warning"
    return "pass"


def build_preparedness_action_ledger_audit() -> dict:
    now = timezone.now()
    checks = [
        _high_risk_promoted_alerts_without_actions_check(),
        _overdue_actions_without_escalation_check(now),
        _completed_actions_without_evidence_check(),
        _lifecycle_events_integrity_check(),
        _due_sla_integrity_check(),
        _assignment_state_integrity_check(),
        _duplicate_active_source_actions_check(),
        _detached_or_cross_ward_actions_check(),
    ]
    return {
        "schema_version": PREPAREDNESS_ACTION_LEDGER_AUDIT_SCHEMA_VERSION,
        "generated_at": now,
        "overall_status": _overall_status(checks),
        "record_totals": _record_totals(now),
        "operating_rules": OPERATING_RULES,
        "audit_checks": checks,
    }
