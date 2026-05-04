from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import CommandError, call_command
from django.test import TestCase
from django.utils import timezone

from risk.feedback_governance import (
    adjudicate_prediction_feedback,
    build_feedback_governance_decision_record,
    record_prediction_feedback,
    supersede_feedback_label_candidates_with_surveillance_truth,
)
from risk.feedback_governance_audit import build_feedback_to_model_governance_audit
from risk.models import (
    FeedbackAdjudication,
    FeedbackAdjudicationState,
    FeedbackLabelCandidate,
    ModelRun,
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


class FeedbackToModelGovernanceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="feedback-reviewer")
        self.ward = Ward.objects.create(
            name="Feedback Governance Ward",
            county="Migori",
            ward_code="FB-GOV",
        )
        self.model_run = ModelRun.objects.create(
            algorithm_name="logistic-regression-baseline",
            model_version="feedback-governance-v1",
            status=ModelRun.STATUS_SUCCESS,
            metadata={
                "promotion_target": "live_baseline",
                "promotion_state": "promoted",
                "phase_4_promotion_gates_passed": True,
                "alert_eligible": True,
            },
            completed_at=timezone.now(),
        )
        self.anchor = timezone.now()
        self.risk_score = RiskScore.objects.create(
            ward=self.ward,
            model_run=self.model_run,
            score=0.78,
            risk_level=Ward.RISK_HIGH,
            predicted_cases=7,
            model_version=self.model_run.model_version,
            generated_at=self.anchor,
        )
        self.label_window = SurveillanceLabelWindow.objects.create(
            ward=self.ward,
            dataset_ref="feedback-governance-labels",
            label_window_start=(self.anchor + timedelta(days=7)).date(),
            label_window_end=(self.anchor + timedelta(days=14)).date(),
            outbreak_label=SurveillanceOutbreakLabel.WATCH,
            label_truth_level=SurveillanceTruthLevel.SUSPECTED_SURVEILLANCE,
            suspected_case_count=5,
            source_record_count=1,
        )

    def _record_feedback(self) -> PredictionFeedback:
        return record_prediction_feedback(
            risk_score=self.risk_score,
            label_window=self.label_window,
            feedback_type=PredictionFeedback.FEEDBACK_SUSPECTED_FALSE_ALERT,
            feedback_source_type=PredictionFeedback.SOURCE_TYPE_REVIEWER,
            source_confidence=PredictionFeedbackSourceConfidence.COUNTY_SURVEILLANCE_OFFICER,
            submitted_by=self.user,
            note="Reviewer thinks this alert may need label review.",
            attached_evidence_refs=["field-note:77"],
        )

    def test_phase_zero_decision_record_blocks_live_self_learning(self):
        decision = build_feedback_governance_decision_record()

        self.assertFalse(decision["live_reinforcement_learning_allowed"])
        self.assertFalse(decision["online_model_weight_updates_allowed"])
        self.assertFalse(decision["automatic_threshold_changes_from_feedback_allowed"])
        self.assertIn("versioned_feedback_training_dataset", decision["deferred_scope"])

    def test_feedback_capture_links_lineage_without_mutating_labels_or_model_state(self):
        label_count = SurveillanceLabelWindow.objects.count()

        feedback = self._record_feedback()

        self.assertEqual(feedback.ward, self.ward)
        self.assertEqual(feedback.risk_score, self.risk_score)
        self.assertEqual(feedback.model_run, self.model_run)
        self.assertEqual(feedback.label_window, self.label_window)
        self.assertEqual(feedback.training_usage_state, PredictionFeedbackTrainingUsageState.NEEDS_REVIEW)
        self.assertTrue(feedback.lineage_metadata["no_direct_label_mutation"])
        self.assertEqual(SurveillanceLabelWindow.objects.count(), label_count)
        self.assertEqual(
            feedback.events.get().event_type,
            PredictionFeedbackEvent.EVENT_CREATED,
        )

        audit = build_feedback_to_model_governance_audit()
        self.assertEqual(audit["overall_status"], "pass")

    def test_adjudication_creates_weak_label_candidate_not_confirmed_truth(self):
        feedback = self._record_feedback()
        label_count = SurveillanceLabelWindow.objects.count()

        adjudication = adjudicate_prediction_feedback(
            feedback=feedback,
            reviewer=self.user,
            adjudication_state=FeedbackAdjudicationState.ACCEPTED_AS_LABEL_CANDIDATE,
            accepted_label_impact={
                "outbreak_label": SurveillanceOutbreakLabel.NONE,
                "label_truth_level": SurveillanceTruthLevel.FIELD_SIGNAL_ONLY,
                "case_note": "Field team reports no active cluster, but surveillance truth is still pending.",
            },
            reason="Accept as weak field-signal label candidate only.",
        )

        feedback.refresh_from_db()
        candidate = FeedbackLabelCandidate.objects.get(adjudication=adjudication)
        self.assertEqual(feedback.training_usage_state, PredictionFeedbackTrainingUsageState.ADJUDICATED_LABEL_CANDIDATE)
        self.assertEqual(candidate.label_truth_level, SurveillanceTruthLevel.FIELD_SIGNAL_ONLY)
        self.assertEqual(candidate.outbreak_label, SurveillanceOutbreakLabel.NONE)
        self.assertFalse(candidate.lineage_metadata["confirmed_truth_allowed"])
        self.assertEqual(SurveillanceLabelWindow.objects.count(), label_count)
        self.assertEqual(
            list(feedback.events.values_list("event_type", flat=True)),
            [
                PredictionFeedbackEvent.EVENT_CREATED,
                PredictionFeedbackEvent.EVENT_ADJUDICATED,
                PredictionFeedbackEvent.EVENT_LABEL_CANDIDATE_CREATED,
            ],
        )

        audit = build_feedback_to_model_governance_audit()
        self.assertEqual(audit["overall_status"], "pass")

    def test_confirmed_surveillance_truth_is_rejected_for_feedback_label_candidates(self):
        feedback = self._record_feedback()

        with self.assertRaises(ValidationError):
            adjudicate_prediction_feedback(
                feedback=feedback,
                reviewer=self.user,
                adjudication_state=FeedbackAdjudicationState.ACCEPTED_AS_LABEL_CANDIDATE,
                accepted_label_impact={
                    "outbreak_label": SurveillanceOutbreakLabel.ACTIVE,
                    "label_truth_level": SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE,
                },
                reason="Unsafe direct promotion to confirmed truth.",
            )

        self.assertEqual(FeedbackAdjudication.objects.count(), 0)
        self.assertEqual(FeedbackLabelCandidate.objects.count(), 0)

    def test_confirmed_surveillance_label_supersedes_feedback_label_candidate(self):
        feedback = self._record_feedback()
        adjudicate_prediction_feedback(
            feedback=feedback,
            reviewer=self.user,
            adjudication_state=FeedbackAdjudicationState.ACCEPTED_AS_LABEL_CANDIDATE,
            accepted_label_impact={
                "outbreak_label": SurveillanceOutbreakLabel.ACTIVE,
                "label_truth_level": SurveillanceTruthLevel.FIELD_SIGNAL_ONLY,
            },
            reason="Weak candidate until surveillance labels settle.",
        )
        candidate = FeedbackLabelCandidate.objects.get()
        confirmed_label = SurveillanceLabelWindow.objects.create(
            ward=self.ward,
            dataset_ref="feedback-governance-confirmed-labels",
            label_window_start=candidate.label_window_start,
            label_window_end=candidate.label_window_end,
            outbreak_label=SurveillanceOutbreakLabel.ACTIVE,
            label_truth_level=SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE,
            confirmed_case_count=1,
            source_record_count=1,
        )

        result = supersede_feedback_label_candidates_with_surveillance_truth(surveillance_label=confirmed_label)

        self.assertEqual(result["superseded_count"], 1)
        candidate.refresh_from_db()
        feedback.refresh_from_db()
        self.assertEqual(candidate.superseded_by_surveillance_label, confirmed_label)
        self.assertEqual(
            candidate.training_usage_state,
            PredictionFeedbackTrainingUsageState.SUPERSEDED_BY_SURVEILLANCE_TRUTH,
        )
        self.assertEqual(
            feedback.training_usage_state,
            PredictionFeedbackTrainingUsageState.SUPERSEDED_BY_SURVEILLANCE_TRUTH,
        )

        audit = build_feedback_to_model_governance_audit()
        self.assertEqual(audit["overall_status"], "pass")

    def test_audit_flags_training_facing_feedback_without_reviewed_adjudication(self):
        PredictionFeedback.objects.create(
            ward=self.ward,
            risk_score=self.risk_score,
            model_run=self.model_run,
            label_window=self.label_window,
            prediction_date=self.anchor.date(),
            feedback_type=PredictionFeedback.FEEDBACK_PREDICTION_REVIEWED_WRONG,
            feedback_source_type=PredictionFeedback.SOURCE_TYPE_COMMUNITY,
            submitted_by=self.user,
            source_confidence=PredictionFeedbackSourceConfidence.COMMUNITY_REPORT,
            training_usage_state=PredictionFeedbackTrainingUsageState.TRAINING_ELIGIBLE,
        )

        audit = build_feedback_to_model_governance_audit()

        self.assertEqual(audit["overall_status"], "fail")
        self.assertIn(
            "feedback_training_state_without_adjudication",
            next(check for check in audit["checks"] if check["id"] == "training_usage_requires_reviewed_adjudication")["gaps"],
        )
        with self.assertRaises(CommandError):
            call_command("audit_feedback_to_model_governance", "--strict", stdout=StringIO())

    def test_pii_feedback_cannot_be_marked_training_facing(self):
        feedback = PredictionFeedback(
            ward=self.ward,
            risk_score=self.risk_score,
            model_run=self.model_run,
            label_window=self.label_window,
            prediction_date=self.anchor.date(),
            feedback_type=PredictionFeedback.FEEDBACK_CHV_FIELD_OBSERVATION,
            feedback_source_type=PredictionFeedback.SOURCE_TYPE_FIELD_OPERATOR,
            submitted_by=self.user,
            source_confidence=PredictionFeedbackSourceConfidence.ASSIGNED_CHV,
            privacy_classification=PredictionFeedbackPrivacyClassification.CONTAINS_PII,
            training_usage_state=PredictionFeedbackTrainingUsageState.ADJUDICATED_LABEL_CANDIDATE,
        )

        with self.assertRaises(ValidationError):
            feedback.full_clean()
