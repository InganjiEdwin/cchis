from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from risk.models import (
    Alert,
    CHV,
    CHVAssignment,
    CHVCoverageRequest,
    CHVCoverageRequestAlertLink,
    ModelRun,
    RiskScore,
    SurveillanceLabelWindow,
    SurveillanceOutbreakLabel,
    SurveillanceTruthLevel,
    Ward,
)
from risk.registry_test_fixtures import seed_approved_active_registry_entry
from risk.services import build_ward_intelligence_snapshot


class WardFrontendAlignmentPhaseSixTestCase(TestCase):
    def setUp(self):
        self.ward = Ward.objects.create(
            name="Phase Six Ward",
            county="Migori",
            sub_county="Rongo",
            ward_code="P6-WARD",
            current_risk_level=Ward.RISK_HIGH,
            current_risk_score=0.82,
        )
        self.model_run = ModelRun.objects.create(
            algorithm_name="logistic-regression-baseline",
            model_version="phase6-promoted-v1",
            status=ModelRun.STATUS_SUCCESS,
            evaluation_metrics={
                "surveillance_lead_time_validation": {
                    "status": "ready_for_lead_time_review",
                    "horizons": {
                        "7": {"matching_label_window_count": 1},
                        "14": {"matching_label_window_count": 1},
                    },
                },
                "recall": 0.81,
            },
            metadata={
                "promotion_target": "live_baseline",
                "promotion_state": "promoted",
                "phase_4_promotion_gates_passed": True,
                "alert_eligible": True,
            },
            completed_at=timezone.now(),
        )
        seed_approved_active_registry_entry(
            self,
            self.model_run,
            reason="Phase six frontend evidence fixture represents a governed live run",
        )

    def test_ward_intelligence_exposes_phase_six_operational_evidence(self):
        anchor = timezone.now()
        latest_risk = RiskScore.objects.create(
            ward=self.ward,
            model_run=self.model_run,
            score=0.82,
            risk_level=Ward.RISK_HIGH,
            rainfall_mm=92,
            flood_indicator=0.6,
            predicted_cases=15,
            model_version=self.model_run.model_version,
            decision_policy={
                "policy_version": "ward-risk-policy-test",
                "alert_decision": "alert_candidate",
                "automatic_alert_allowed": True,
                "automatic_alert_blockers": [],
                "inputs": {
                    "source_freshness": {"combined_state": "FRESH"},
                    "source_confidence": {"confidence": "high", "source_kind": "LIVE"},
                    "climate_coverage": {
                        "observed_vs_forecast_source_label": "Forecast rainfall",
                        "claimed_forecast_horizon_days": 14,
                        "forecast_coverage_days": 3,
                        "forecast_missing_lead_days": list(range(4, 15)),
                        "claimed_lead_time_climate_coverage_sufficient": False,
                        "climate_coverage_status": "insufficient_forecast_horizon",
                        "climate_coverage_caveats": ["forecast_missing_claimed_lead_days"],
                    },
                },
            },
            generated_at=anchor - timedelta(days=14),
        )
        older_risk = RiskScore.objects.create(
            ward=self.ward,
            model_run=self.model_run,
            score=0.78,
            risk_level=Ward.RISK_HIGH,
            rainfall_mm=88,
            flood_indicator=0.2,
            predicted_cases=10,
            model_version=self.model_run.model_version,
            generated_at=anchor - timedelta(days=30),
        )
        SurveillanceLabelWindow.objects.create(
            ward=self.ward,
            dataset_ref="phase6-labels",
            label_window_start=(latest_risk.generated_at + timedelta(days=7)).date(),
            label_window_end=(latest_risk.generated_at + timedelta(days=14)).date(),
            outbreak_label=SurveillanceOutbreakLabel.ACTIVE,
            label_truth_level=SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE,
            confirmed_case_count=5,
            source_record_count=2,
        )
        SurveillanceLabelWindow.objects.create(
            ward=self.ward,
            dataset_ref="phase6-labels",
            label_window_start=(older_risk.generated_at + timedelta(days=7)).date(),
            label_window_end=(older_risk.generated_at + timedelta(days=14)).date(),
            outbreak_label=SurveillanceOutbreakLabel.NONE,
            label_truth_level=SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE,
            source_record_count=1,
        )
        alert = Alert.objects.create(
            ward=self.ward,
            risk_score=latest_risk,
            channel=Alert.CHANNEL_DASHBOARD,
            recipient="ops",
            message="Phase 6 alert",
            status=Alert.STATUS_DELIVERED,
        )
        coverage_request = CHVCoverageRequest.objects.create(
            ward=self.ward,
            status=CHVCoverageRequest.STATUS_IN_PROGRESS,
            priority=CHVCoverageRequest.PRIORITY_HIGH,
            trigger_source=CHVCoverageRequest.TRIGGER_SOURCE_ALERT_DRIVEN,
            reason="Follow up phase 6 alert",
            requested_chv_count=1,
        )
        CHVCoverageRequestAlertLink.objects.create(coverage_request=coverage_request, alert=alert)
        chv = CHV.objects.create(name="Phase Six CHV", phone_number="+254700000060", ward=self.ward)
        CHVAssignment.objects.create(
            coverage_request=coverage_request,
            ward=self.ward,
            chv=chv,
            status=CHVAssignment.STATUS_ACTIVE,
        )

        payload = build_ward_intelligence_snapshot(self.ward)
        evidence = payload["operational_evidence"]

        self.assertEqual(evidence["forecast_horizon"]["display_value"], "7 to 14 days")
        self.assertEqual(evidence["forecast_horizon"]["source_label"], "Forecast rainfall")
        self.assertEqual(evidence["forecast_horizon"]["forecast_missing_lead_days"], list(range(4, 15)))
        self.assertEqual(evidence["climate_source"]["observed_vs_forecast_source_label"], "Forecast rainfall")
        self.assertEqual(evidence["model_readiness"]["state"], "promoted")
        self.assertIn("forecast_missing_claimed_lead_days", evidence["model_readiness"]["readiness_caveats"])
        self.assertEqual(evidence["source_badges"][0]["id"], "source_freshness")
        climate_badges = [badge for badge in evidence["source_badges"] if badge["id"] == "climate_coverage"]
        self.assertEqual(climate_badges[0]["value"], "Insufficient Forecast Horizon")
        self.assertIn("Forecast rainfall", climate_badges[0]["detail"])
        self.assertEqual(evidence["alert_candidate_review"]["alert_decision"], "alert_candidate")
        self.assertEqual(evidence["outcome_evaluation"]["hit_count"], 1)
        self.assertEqual(evidence["outcome_evaluation"]["false_alert_count"], 1)
        self.assertEqual(evidence["false_missed_review"]["open_review_count"], 1)
        self.assertEqual(evidence["prediction_label_history"][0]["classification"], "hit")
        self.assertEqual(evidence["chv_action_status"]["summary"]["active_request_count"], 1)
        self.assertIn(str(alert.public_id), evidence["chv_action_status"]["requests"][0]["linked_alert_public_ids"])
        self.assertTrue(
            any("Forecast rainfall" in item["text"] for item in payload["driver_summary"]["items"])
        )
