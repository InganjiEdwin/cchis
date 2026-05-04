from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from risk.models import (
    Alert,
    CHV,
    CHVAssignment,
    CHVCoverageRequest,
    CHVCoverageRequestAlertLink,
    CHVMessage,
    FacilityReadinessEscalation,
    FacilityReadinessReview,
    HealthFacility,
    ModelRun,
    PreparednessAction,
    RiskScore,
    SurveillanceLabelWindow,
    SurveillanceOutbreakLabel,
    SurveillanceTruthLevel,
    Ward,
)
from risk.services import build_ward_intelligence_snapshot


class WardOutcomeFeedbackPhaseSevenTestCase(TestCase):
    def setUp(self):
        self.model_run = ModelRun.objects.create(
            algorithm_name="logistic-regression-baseline",
            model_version="phase7-promoted-v1",
            status=ModelRun.STATUS_SUCCESS,
            evaluation_metrics={"recall": 0.84},
            metadata={
                "promotion_target": "live_baseline",
                "promotion_state": "promoted",
                "phase_4_promotion_gates_passed": True,
                "alert_eligible": True,
            },
            completed_at=timezone.now(),
        )

    def _create_ward(self, name: str, ward_code: str) -> Ward:
        return Ward.objects.create(
            name=name,
            county="Migori",
            sub_county="Rongo",
            ward_code=ward_code,
            current_risk_level=Ward.RISK_HIGH,
            current_risk_score=0.84,
        )

    def _create_high_risk_prediction(self, ward: Ward, *, anchor) -> RiskScore:
        return RiskScore.objects.create(
            ward=ward,
            model_run=self.model_run,
            score=0.84,
            risk_level=Ward.RISK_HIGH,
            rainfall_mm=96,
            flood_indicator=0.7,
            predicted_cases=14,
            model_version=self.model_run.model_version,
            decision_policy={
                "policy_version": "ward-risk-policy-phase7",
                "alert_decision": "alert_candidate",
                "automatic_alert_allowed": True,
                "automatic_alert_blockers": [],
                "inputs": {
                    "source_freshness": {"combined_state": "FRESH"},
                    "source_confidence": {"confidence": "high", "source_kind": "LIVE"},
                },
            },
            generated_at=anchor - timedelta(days=14),
        )

    def _create_label(self, risk_score: RiskScore, *, outbreak_label: str, suspected: int = 0, confirmed: int = 0):
        return SurveillanceLabelWindow.objects.create(
            ward=risk_score.ward,
            dataset_ref="phase7-labels",
            label_window_start=(risk_score.generated_at + timedelta(days=7)).date(),
            label_window_end=(risk_score.generated_at + timedelta(days=14)).date(),
            outbreak_label=outbreak_label,
            label_truth_level=SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE,
            suspected_case_count=suspected,
            confirmed_case_count=confirmed,
            source_record_count=2,
        )

    def test_outcome_feedback_tracks_alert_to_action_response_chain(self):
        anchor = timezone.now()
        ward = self._create_ward("Phase Seven Response Ward", "P7-RESP")
        risk_score = self._create_high_risk_prediction(ward, anchor=anchor)
        self._create_label(risk_score, outbreak_label=SurveillanceOutbreakLabel.NONE)
        alert = Alert.objects.create(
            ward=ward,
            risk_score=risk_score,
            channel=Alert.CHANNEL_DASHBOARD,
            recipient="ops",
            message="Phase 7 alert",
            status=Alert.STATUS_DELIVERED,
            sent_at=anchor,
        )
        chv = CHV.objects.create(name="Phase Seven CHV", phone_number="+254700000071", ward=ward)
        CHVMessage.objects.create(
            chv=chv,
            ward=ward,
            sent_by=None,
            message_body="Follow up alert",
            status=CHVMessage.STATUS_DELIVERED,
            delivery_kind=CHVMessage.DELIVERY_KIND_SIMULATED,
        )
        coverage_request = CHVCoverageRequest.objects.create(
            ward=ward,
            status=CHVCoverageRequest.STATUS_RESOLVED,
            priority=CHVCoverageRequest.PRIORITY_HIGH,
            trigger_source=CHVCoverageRequest.TRIGGER_SOURCE_ALERT_DRIVEN,
            reason="Follow up phase 7 alert",
            requested_chv_count=1,
            resolved_at=timezone.now(),
        )
        CHVCoverageRequestAlertLink.objects.create(coverage_request=coverage_request, alert=alert)
        CHVAssignment.objects.create(
            coverage_request=coverage_request,
            ward=ward,
            chv=chv,
            status=CHVAssignment.STATUS_COMPLETED,
            end_at=timezone.now(),
        )
        facility = HealthFacility.objects.create(name="Phase Seven Facility", facility_code="P7-FAC-1", ward=ward)
        review = FacilityReadinessReview.objects.create(
            facility=facility,
            ward=ward,
            status=FacilityReadinessReview.STATUS_RESOLVED,
            severity=FacilityReadinessReview.SEVERITY_HIGH,
            reason_codes=["capacity_pressure"],
            resolved_at=timezone.now(),
        )
        FacilityReadinessEscalation.objects.create(
            review=review,
            facility=facility,
            ward=ward,
            status=FacilityReadinessEscalation.STATUS_RESOLVED,
            severity=FacilityReadinessEscalation.SEVERITY_HIGH,
            reason="Supplies reviewed",
            resolved_at=timezone.now(),
        )

        feedback = build_ward_intelligence_snapshot(ward)["operational_evidence"]["outcome_feedback"]

        self.assertEqual(feedback["mode"], "alert_to_action_outcome_feedback")
        self.assertEqual(feedback["model_quality_state"], "possible_false_alert")
        self.assertEqual(feedback["response_quality_state"], "response_complete")
        self.assertEqual(feedback["attribution"], "possible_response_success_or_model_false_positive")
        self.assertEqual(feedback["observed_outcome"]["state"], "possibly_avoided_or_reduced")
        self.assertEqual(feedback["summary"]["downstream_failure_count"], 0)
        step_keys = {step["key"] for step in feedback["steps"]}
        self.assertSetEqual(
            step_keys,
            {
                "alert_issued",
                "chv_notified",
                "chv_acknowledged",
                "household_follow_up_started",
                "facility_readiness_action_started",
                "supplies_or_staffing_escalated",
                "suspected_cases_observed",
                "confirmed_cases_observed",
                "outbreak_trajectory",
            },
        )
        self.assertEqual(feedback["review_items"][0]["category"], "model_vs_response_quality")

    def test_outcome_feedback_links_completed_preparedness_action_to_outcome_history(self):
        anchor = timezone.now()
        ward = self._create_ward("Phase Seven Ledger Ward", "P7-LEDGER")
        risk_score = self._create_high_risk_prediction(ward, anchor=anchor)
        label = self._create_label(risk_score, outbreak_label=SurveillanceOutbreakLabel.NONE)
        alert = Alert.objects.create(
            ward=ward,
            risk_score=risk_score,
            channel=Alert.CHANNEL_DASHBOARD,
            recipient="ops",
            message="Ledger-backed response alert",
            status=Alert.STATUS_DELIVERED,
            sent_at=anchor,
        )
        action = PreparednessAction.objects.create(
            ward=ward,
            alert=alert,
            risk_score=risk_score,
            model_run=self.model_run,
            action_type=PreparednessAction.ACTION_FIELD_VERIFICATION,
            source_trigger_type=PreparednessAction.SOURCE_ALERT,
            source_trigger_ref=f"alert:{alert.public_id}",
            status=PreparednessAction.STATUS_COMPLETED,
            priority=PreparednessAction.PRIORITY_HIGH,
            due_at=anchor + timedelta(hours=4),
            completed_at=anchor + timedelta(hours=2),
            completion_evidence={
                "summary": "Field team verified household conditions and reported no active cluster.",
                "reference": "field-report-77",
            },
        )
        PreparednessAction.objects.filter(pk=action.pk).update(
            created_at=anchor + timedelta(minutes=30),
            completed_at=anchor + timedelta(hours=2),
            updated_at=anchor + timedelta(hours=2),
        )

        feedback = build_ward_intelligence_snapshot(ward)["operational_evidence"]["outcome_feedback"]
        action_evidence = feedback["preparedness_action_evidence"]
        ledger_step = next(step for step in feedback["steps"] if step["key"] == "preparedness_action_ledger")

        self.assertEqual(feedback["response_quality_state"], "response_complete")
        self.assertEqual(ledger_step["status"], "recorded")
        self.assertEqual(action_evidence["summary"]["completed_count"], 1)
        self.assertEqual(action_evidence["summary"]["completed_with_evidence_count"], 1)
        self.assertEqual(action_evidence["response_time_measurements"]["hours_to_first_action"], 0.5)
        self.assertEqual(action_evidence["response_time_measurements"]["hours_to_first_completion"], 2.0)
        self.assertIn("completion_reference_present", action_evidence["completion_quality_flags"])
        self.assertEqual(action_evidence["action_history"][0]["outcome_links"]["label_window_ref"], f"surveillance_label_window:{label.id}")
        self.assertEqual(action_evidence["action_history"][0]["outcome_links"]["prediction_risk_score_ids"], [risk_score.id])
        self.assertTrue(action_evidence["false_alert_review_context"]["review_required"])

    def test_outcome_feedback_does_not_treat_boilerplate_completion_evidence_as_response(self):
        anchor = timezone.now()
        ward = self._create_ward("Phase Seven Boilerplate Ledger Ward", "P7-BOILER")
        risk_score = self._create_high_risk_prediction(ward, anchor=anchor)
        self._create_label(risk_score, outbreak_label=SurveillanceOutbreakLabel.NONE)
        alert = Alert.objects.create(
            ward=ward,
            risk_score=risk_score,
            channel=Alert.CHANNEL_DASHBOARD,
            recipient="ops",
            message="Ledger-backed response alert",
            status=Alert.STATUS_DELIVERED,
            sent_at=anchor,
        )
        action = PreparednessAction.objects.create(
            ward=ward,
            alert=alert,
            risk_score=risk_score,
            model_run=self.model_run,
            action_type=PreparednessAction.ACTION_FIELD_VERIFICATION,
            source_trigger_type=PreparednessAction.SOURCE_ALERT,
            source_trigger_ref=f"alert:{alert.public_id}",
            status=PreparednessAction.STATUS_COMPLETED,
            priority=PreparednessAction.PRIORITY_HIGH,
            due_at=anchor + timedelta(hours=4),
            completed_at=anchor + timedelta(hours=2),
            completion_evidence={
                "captured_via": "api",
                "captured_at": timezone.now().isoformat(),
            },
        )
        PreparednessAction.objects.filter(pk=action.pk).update(
            created_at=anchor + timedelta(minutes=30),
            completed_at=anchor + timedelta(hours=2),
            updated_at=anchor + timedelta(hours=2),
        )

        feedback = build_ward_intelligence_snapshot(ward)["operational_evidence"]["outcome_feedback"]
        action_evidence = feedback["preparedness_action_evidence"]
        ledger_step = next(step for step in feedback["steps"] if step["key"] == "preparedness_action_ledger")

        self.assertEqual(ledger_step["status"], "failed")
        self.assertEqual(action_evidence["summary"]["completed_count"], 0)
        self.assertEqual(action_evidence["summary"]["completed_with_evidence_count"], 0)
        self.assertEqual(action_evidence["summary"]["completed_without_substantive_evidence_count"], 1)
        self.assertFalse(action_evidence["action_history"][0]["completion_evidence_present"])
        self.assertIn("completion_evidence_boilerplate_only", action_evidence["completion_quality_flags"])
        self.assertFalse(action_evidence["false_alert_review_context"]["review_required"])

    def test_outcome_feedback_keeps_alert_failure_separate_from_completed_action(self):
        anchor = timezone.now()
        ward = self._create_ward("Phase Seven Alert Failure Ward", "P7-ALERT-FAIL")
        risk_score = self._create_high_risk_prediction(ward, anchor=anchor)
        self._create_label(
            risk_score,
            outbreak_label=SurveillanceOutbreakLabel.ACTIVE,
            suspected=5,
            confirmed=1,
        )
        alert = Alert.objects.create(
            ward=ward,
            risk_score=risk_score,
            channel=Alert.CHANNEL_DASHBOARD,
            recipient="ops",
            message="Failed delivery alert",
            status=Alert.STATUS_FAILED,
            error_message="recipient route unavailable",
        )
        action = PreparednessAction.objects.create(
            ward=ward,
            alert=alert,
            risk_score=risk_score,
            model_run=self.model_run,
            action_type=PreparednessAction.ACTION_FIELD_VERIFICATION,
            source_trigger_type=PreparednessAction.SOURCE_ALERT,
            source_trigger_ref=f"alert:{alert.public_id}",
            status=PreparednessAction.STATUS_COMPLETED,
            priority=PreparednessAction.PRIORITY_HIGH,
            due_at=anchor + timedelta(hours=4),
            completed_at=anchor + timedelta(hours=2),
            completion_evidence={
                "summary": "Supervisor completed manual follow-up after the failed alert delivery.",
                "reference": "manual-follow-up-41",
            },
        )
        PreparednessAction.objects.filter(pk=action.pk).update(
            created_at=anchor + timedelta(minutes=30),
            completed_at=anchor + timedelta(hours=2),
            updated_at=anchor + timedelta(hours=2),
        )

        feedback = build_ward_intelligence_snapshot(ward)["operational_evidence"]["outcome_feedback"]
        alert_step = next(step for step in feedback["steps"] if step["key"] == "alert_issued")
        ledger_step = next(step for step in feedback["steps"] if step["key"] == "preparedness_action_ledger")

        self.assertEqual(alert_step["status"], "failed")
        self.assertEqual(ledger_step["status"], "recorded")
        self.assertEqual(feedback["response_quality_state"], "alert_delivery_failure")
        self.assertEqual(feedback["attribution"], "alert_delivery_review")
        self.assertEqual(feedback["summary"]["alert_failure_count"], 1)
        self.assertEqual(feedback["summary"]["response_execution_failure_count"], 0)
        self.assertIn(
            "alert_delivery",
            {item["category"] for item in feedback["review_items"]},
        )

    def test_outcome_feedback_flags_response_gap_when_outbreak_active_after_alert(self):
        anchor = timezone.now()
        ward = self._create_ward("Phase Seven Gap Ward", "P7-GAP")
        risk_score = self._create_high_risk_prediction(ward, anchor=anchor)
        self._create_label(
            risk_score,
            outbreak_label=SurveillanceOutbreakLabel.ACTIVE,
            suspected=8,
            confirmed=3,
        )
        Alert.objects.create(
            ward=ward,
            risk_score=risk_score,
            channel=Alert.CHANNEL_DASHBOARD,
            recipient="ops",
            message="Phase 7 active outbreak alert",
            status=Alert.STATUS_DELIVERED,
            sent_at=anchor,
        )

        feedback = build_ward_intelligence_snapshot(ward)["operational_evidence"]["outcome_feedback"]

        self.assertEqual(feedback["model_quality_state"], "prediction_hit")
        self.assertEqual(feedback["response_quality_state"], "response_gap")
        self.assertEqual(feedback["attribution"], "response_quality_review")
        self.assertEqual(feedback["observed_outcome"]["observed_label"], SurveillanceOutbreakLabel.ACTIVE)
        self.assertEqual(feedback["observed_outcome"]["suspected_case_count"], 8)
        self.assertEqual(feedback["observed_outcome"]["confirmed_case_count"], 3)
        self.assertEqual(feedback["review_items"][0]["category"], "response_quality")
        self.assertIn("chv_notified", feedback["review_items"][0]["step_keys"])
        self.assertTrue(feedback["preparedness_action_evidence"]["missed_action_review"]["review_required"])
        self.assertIn(
            "missed_action_review",
            {item["category"] for item in feedback["review_items"]},
        )
