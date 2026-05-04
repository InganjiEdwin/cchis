from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from risk.models import (
    FeedbackAdjudication,
    FeedbackAdjudicationState,
    FeedbackLabelCandidate,
    PredictionFeedback,
    PredictionFeedbackEvent,
    PredictionFeedbackPrivacyClassification,
    PredictionFeedbackSourceConfidence,
    PredictionFeedbackTrainingUsageState,
    RiskScore,
    SurveillanceLabelWindow,
    SurveillanceOutbreakLabel,
    SurveillanceTruthLevel,
    Ward,
)


FEEDBACK_GOVERNANCE_DECISION_SCHEMA_VERSION = "feedback-to-model-governance-decision-v1"
FEEDBACK_LABEL_CANDIDATE_SCHEMA_VERSION = "feedback-label-candidate-v1"


def build_feedback_governance_decision_record() -> dict:
    return {
        "schema_version": FEEDBACK_GOVERNANCE_DECISION_SCHEMA_VERSION,
        "decision": "governed_offline_retraining_only",
        "live_reinforcement_learning_allowed": False,
        "online_model_weight_updates_allowed": False,
        "automatic_threshold_changes_from_feedback_allowed": False,
        "automatic_retraining_promotion_allowed": False,
        "unadjudicated_feedback_as_confirmed_truth_allowed": False,
        "implemented_scope": [
            "phase_0_decision_record",
            "phase_1_feedback_capture_contract",
            "phase_2_adjudication_workflow",
            "phase_3_weak_label_candidate_integration",
        ],
        "deferred_scope": [
            "versioned_feedback_training_dataset",
            "offline_retraining_candidate",
            "temporal_shadow_deployment",
            "adaptive_policy_research_sandbox",
        ],
        "promotion_policy": "Any future model trained with feedback-derived labels must still pass Phase 4 and model-ops gates.",
    }


def _ensure_aware(value: datetime | None) -> datetime:
    value = value or timezone.now()
    if timezone.is_naive(value):
        return timezone.make_aware(value, timezone.get_current_timezone())
    return value


def _local_date(value: datetime) -> date:
    return timezone.localtime(_ensure_aware(value)).date()


def _parse_date(value: date | str | None) -> date | None:
    if value is None:
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _feedback_ref(feedback: PredictionFeedback) -> str:
    return f"prediction_feedback:{feedback.public_id}"


def _adjudication_ref(adjudication: FeedbackAdjudication) -> str:
    return f"feedback_adjudication:{adjudication.public_id}"


def record_prediction_feedback(
    *,
    ward: Ward | None = None,
    risk_score: RiskScore | None = None,
    model_run=None,
    label_window: SurveillanceLabelWindow | None = None,
    prediction_date: date | None = None,
    feedback_type: str,
    feedback_source_type: str,
    source_confidence: str,
    submitted_by=None,
    submitted_at: datetime | None = None,
    note: str = "",
    attached_evidence_refs: Iterable[str] | None = None,
    privacy_classification: str = PredictionFeedbackPrivacyClassification.NON_SENSITIVE,
    lineage_metadata: dict | None = None,
) -> PredictionFeedback:
    if risk_score is not None:
        ward = ward or risk_score.ward
        model_run = model_run or risk_score.model_run
        prediction_date = prediction_date or _local_date(risk_score.generated_at)
    if label_window is not None:
        ward = ward or label_window.ward
    if ward is None:
        raise ValueError("ward_or_risk_score_required")

    feedback = PredictionFeedback(
        ward=ward,
        risk_score=risk_score,
        model_run=model_run,
        label_window=label_window,
        prediction_date=prediction_date,
        feedback_type=feedback_type,
        feedback_source_type=feedback_source_type,
        submitted_by=submitted_by,
        submitted_at=_ensure_aware(submitted_at),
        source_confidence=source_confidence,
        note=note,
        attached_evidence_refs=list(attached_evidence_refs or []),
        privacy_classification=privacy_classification,
        training_usage_state=PredictionFeedbackTrainingUsageState.NEEDS_REVIEW,
        lineage_metadata={
            "schema_version": "prediction-feedback-lineage-v1",
            "decision_record_schema_version": FEEDBACK_GOVERNANCE_DECISION_SCHEMA_VERSION,
            "risk_score_id": risk_score.id if risk_score else None,
            "model_run_id": model_run.id if model_run else None,
            "label_window_id": label_window.id if label_window else None,
            "no_direct_label_mutation": True,
            **(lineage_metadata or {}),
        },
    )
    feedback.full_clean()
    with transaction.atomic():
        feedback.save()
        PredictionFeedbackEvent.objects.create(
            feedback=feedback,
            actor=submitted_by,
            event_type=PredictionFeedbackEvent.EVENT_CREATED,
            new_training_usage_state=feedback.training_usage_state,
            detail="Feedback captured for adjudication; no label or model state was mutated.",
            metadata={"feedback_ref": _feedback_ref(feedback)},
        )
    return feedback


def _training_state_for_adjudication(adjudication: FeedbackAdjudication) -> str:
    state = adjudication.adjudication_state
    if state == FeedbackAdjudicationState.ACCEPTED_AS_LABEL_CANDIDATE:
        return PredictionFeedbackTrainingUsageState.ADJUDICATED_LABEL_CANDIDATE
    if state in {
        FeedbackAdjudicationState.ACCEPTED_AS_RESPONSE_QUALITY_ISSUE,
        FeedbackAdjudicationState.ACCEPTED_AS_DATA_QUALITY_ISSUE,
        FeedbackAdjudicationState.NEEDS_MORE_EVIDENCE,
    }:
        return PredictionFeedbackTrainingUsageState.NOT_TRAINING_ELIGIBLE
    if state == FeedbackAdjudicationState.REJECTED:
        return PredictionFeedbackTrainingUsageState.REJECTED
    if state == FeedbackAdjudicationState.SUPERSEDED:
        return PredictionFeedbackTrainingUsageState.SUPERSEDED_BY_SURVEILLANCE_TRUTH
    return PredictionFeedbackTrainingUsageState.NEEDS_REVIEW


def adjudicate_prediction_feedback(
    *,
    feedback: PredictionFeedback,
    reviewer,
    adjudication_state: str,
    accepted_label_impact: dict | None = None,
    response_quality_impact: dict | None = None,
    data_quality_impact: dict | None = None,
    reason: str = "",
    reviewed_at: datetime | None = None,
    superseded_by_surveillance_label: SurveillanceLabelWindow | None = None,
    evidence_refs: Iterable[str] | None = None,
    metadata: dict | None = None,
) -> FeedbackAdjudication:
    terminal_state = adjudication_state != FeedbackAdjudicationState.PENDING
    adjudication = FeedbackAdjudication(
        feedback=feedback,
        reviewer=reviewer,
        adjudication_state=adjudication_state,
        accepted_label_impact=accepted_label_impact or {},
        response_quality_impact=response_quality_impact or {},
        data_quality_impact=data_quality_impact or {},
        reason=reason,
        reviewed_at=_ensure_aware(reviewed_at) if terminal_state else reviewed_at,
        superseded_by_surveillance_label=superseded_by_surveillance_label,
        evidence_refs=list(evidence_refs or []),
        metadata={
            "schema_version": "feedback-adjudication-v1",
            "decision_record_schema_version": FEEDBACK_GOVERNANCE_DECISION_SCHEMA_VERSION,
            "automatic_model_mutation_allowed": False,
            **(metadata or {}),
        },
    )
    adjudication.full_clean()

    with transaction.atomic():
        adjudication.save()
        old_state = feedback.training_usage_state
        feedback.training_usage_state = _training_state_for_adjudication(adjudication)
        feedback.full_clean()
        feedback.save(update_fields=["training_usage_state", "updated_at"])
        PredictionFeedbackEvent.objects.create(
            feedback=feedback,
            actor=reviewer,
            event_type=PredictionFeedbackEvent.EVENT_ADJUDICATED,
            old_training_usage_state=old_state,
            new_training_usage_state=feedback.training_usage_state,
            detail=reason,
            metadata={
                "feedback_ref": _feedback_ref(feedback),
                "adjudication_ref": _adjudication_ref(adjudication),
                "adjudication_state": adjudication.adjudication_state,
            },
        )
        if adjudication.adjudication_state == FeedbackAdjudicationState.ACCEPTED_AS_LABEL_CANDIDATE:
            create_feedback_label_candidate_from_adjudication(adjudication=adjudication)
    return adjudication


def create_feedback_label_candidate_from_adjudication(
    *,
    adjudication: FeedbackAdjudication,
) -> FeedbackLabelCandidate:
    if adjudication.adjudication_state != FeedbackAdjudicationState.ACCEPTED_AS_LABEL_CANDIDATE:
        raise ValueError("adjudication_is_not_label_candidate")
    try:
        existing = adjudication.label_candidate
    except FeedbackLabelCandidate.DoesNotExist:
        existing = None
    if existing is not None:
        return existing

    feedback = adjudication.feedback
    impact = adjudication.accepted_label_impact or {}
    label_window_start = _parse_date(impact.get("label_window_start"))
    label_window_end = _parse_date(impact.get("label_window_end"))
    if feedback.label_window_id:
        label_window_start = label_window_start or feedback.label_window.label_window_start
        label_window_end = label_window_end or feedback.label_window.label_window_end
    if not label_window_start and feedback.prediction_date:
        label_window_start = feedback.prediction_date + timedelta(days=7)
    if not label_window_end and feedback.prediction_date:
        label_window_end = feedback.prediction_date + timedelta(days=14)
    if label_window_start is None or label_window_end is None:
        raise ValidationError("Feedback label candidates require a label window.")

    label_truth_level = impact.get("label_truth_level") or SurveillanceTruthLevel.FIELD_SIGNAL_ONLY
    if label_truth_level == SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE:
        raise ValidationError("Feedback label candidates cannot be confirmed surveillance truth.")

    candidate = FeedbackLabelCandidate(
        feedback=feedback,
        adjudication=adjudication,
        ward=feedback.ward,
        risk_score=feedback.risk_score,
        model_run=feedback.model_run,
        label_window_start=label_window_start,
        label_window_end=label_window_end,
        outbreak_label=impact.get("outbreak_label") or SurveillanceOutbreakLabel.NONE,
        label_truth_level=label_truth_level,
        source_confidence=feedback.source_confidence,
        training_usage_state=PredictionFeedbackTrainingUsageState.ADJUDICATED_LABEL_CANDIDATE,
        lineage_metadata={
            "schema_version": FEEDBACK_LABEL_CANDIDATE_SCHEMA_VERSION,
            "feedback_ref": _feedback_ref(feedback),
            "adjudication_ref": _adjudication_ref(adjudication),
            "source_confidence": feedback.source_confidence,
            "source_feedback_type": feedback.feedback_type,
            "accepted_label_impact": impact,
            "surveillance_truth_policy": "confirmed_surveillance_labels_override_feedback_candidates",
            "confirmed_truth_allowed": False,
            "training_dataset_builder": "deferred_to_plan_10_phase_4",
        },
    )
    candidate.full_clean()
    candidate.save()
    PredictionFeedbackEvent.objects.create(
        feedback=feedback,
        actor=adjudication.reviewer,
        event_type=PredictionFeedbackEvent.EVENT_LABEL_CANDIDATE_CREATED,
        old_training_usage_state=feedback.training_usage_state,
        new_training_usage_state=feedback.training_usage_state,
        detail="Reviewed feedback was captured as a weak label candidate.",
        metadata={
            "candidate_ref": candidate.candidate_ref,
            "adjudication_ref": _adjudication_ref(adjudication),
            "confirmed_truth_allowed": False,
        },
    )
    return candidate


def supersede_feedback_label_candidates_with_surveillance_truth(
    *,
    surveillance_label: SurveillanceLabelWindow | None = None,
    superseded_at: datetime | None = None,
) -> dict:
    queryset = FeedbackLabelCandidate.objects.filter(
        superseded_by_surveillance_label__isnull=True,
    ).exclude(
        training_usage_state=PredictionFeedbackTrainingUsageState.SUPERSEDED_BY_SURVEILLANCE_TRUTH,
    )
    if surveillance_label is not None:
        queryset = queryset.filter(
            ward=surveillance_label.ward,
            label_window_start__lte=surveillance_label.label_window_end,
            label_window_end__gte=surveillance_label.label_window_start,
        )
        candidate_label_pairs = [(candidate, surveillance_label) for candidate in queryset]
    else:
        confirmed_labels = list(
            SurveillanceLabelWindow.objects.filter(
                label_truth_level=SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE,
            ).order_by("-label_window_end", "-id")
        )
        candidate_label_pairs = []
        for candidate in queryset.select_related("ward", "feedback"):
            superseding_label = next(
                (
                    label
                    for label in confirmed_labels
                    if label.ward_id == candidate.ward_id
                    and label.label_window_start <= candidate.label_window_end
                    and label.label_window_end >= candidate.label_window_start
                ),
                None,
            )
            if superseding_label is not None:
                candidate_label_pairs.append((candidate, superseding_label))

    superseded_at = _ensure_aware(superseded_at)
    updated_refs = []
    with transaction.atomic():
        for candidate, label in candidate_label_pairs:
            if label.label_truth_level != SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE:
                continue
            candidate.superseded_by_surveillance_label = label
            candidate.training_usage_state = PredictionFeedbackTrainingUsageState.SUPERSEDED_BY_SURVEILLANCE_TRUTH
            metadata = candidate.lineage_metadata or {}
            metadata["superseded_by"] = f"surveillance_label_window:{label.id}"
            metadata["superseded_at"] = superseded_at.isoformat()
            candidate.lineage_metadata = metadata
            candidate.full_clean()
            candidate.save(
                update_fields=[
                    "superseded_by_surveillance_label",
                    "training_usage_state",
                    "lineage_metadata",
                    "updated_at",
                ]
            )
            feedback = candidate.feedback
            old_state = feedback.training_usage_state
            feedback.training_usage_state = PredictionFeedbackTrainingUsageState.SUPERSEDED_BY_SURVEILLANCE_TRUTH
            feedback.save(update_fields=["training_usage_state", "updated_at"])
            PredictionFeedbackEvent.objects.create(
                feedback=feedback,
                event_type=PredictionFeedbackEvent.EVENT_SUPERSEDED,
                old_training_usage_state=old_state,
                new_training_usage_state=feedback.training_usage_state,
                detail="Feedback label candidate was superseded by confirmed surveillance truth.",
                metadata={
                    "candidate_ref": candidate.candidate_ref,
                    "surveillance_label_window_id": label.id,
                },
            )
            updated_refs.append(candidate.candidate_ref)

    return {
        "schema_version": "feedback-label-candidate-supersession-v1",
        "superseded_count": len(updated_refs),
        "candidate_refs": updated_refs,
    }


def build_feedback_label_candidate_summary() -> dict:
    total_count = FeedbackLabelCandidate.objects.count()
    superseded_count = FeedbackLabelCandidate.objects.filter(
        training_usage_state=PredictionFeedbackTrainingUsageState.SUPERSEDED_BY_SURVEILLANCE_TRUTH,
    ).count()
    return {
        "schema_version": "feedback-label-candidate-summary-v1",
        "candidate_count": total_count,
        "active_candidate_count": total_count - superseded_count,
        "superseded_candidate_count": superseded_count,
        "confirmed_truth_candidate_count": FeedbackLabelCandidate.objects.filter(
            label_truth_level=SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE,
        ).count(),
        "training_usage_state_counts": {
            state: FeedbackLabelCandidate.objects.filter(training_usage_state=state).count()
            for state, _label in PredictionFeedbackTrainingUsageState.choices
        },
        "source_confidence_counts": {
            source: PredictionFeedback.objects.filter(source_confidence=source).count()
            for source, _label in PredictionFeedbackSourceConfidence.choices
        },
    }
