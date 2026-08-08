from django.test import TestCase
from django.utils import timezone

from risk.ml.decision_policy import (
    DECISION_ALERT_CANDIDATE,
    DECISION_URGENT_ALERT,
    WARD_RISK_DECISION_POLICY_SCHEMA_VERSION,
    current_ward_risk_decision_policy,
    evaluate_ward_risk_decision_policy,
    set_ward_risk_decision_policy,
)
from risk.models import (
    Alert,
    FacilityForecast,
    FacilityForecastRun,
    HealthFacility,
    ModelRun,
    RiskScore,
    SystemControlState,
    Ward,
)
from risk.registry_test_fixtures import seed_approved_active_registry_entry
from risk.serializers import RiskScoreSerializer
from risk.services import create_alerts_for_riskscore, sync_alert_workflow_for_ward


class WardRiskDecisionPolicyPhaseFiveTestCase(TestCase):
    def setUp(self):
        self.ward = Ward.objects.create(
            name="Phase Five Ward",
            county="Migori",
            ward_code="P5-W",
            current_risk_level=Ward.RISK_MEDIUM,
            current_risk_score=0.50,
        )

    def _fresh_prediction(self, **overrides):
        payload = {
            "rainfall_source_lineage": {
                "source_kind": "LIVE",
                "freshness_state": "FRESH",
            },
            "population_exposure_feature_mode": "source_fed_population_exposure_context",
            "population_total": 12000,
            "exposed_population_proxy": 9000,
            "catchment_population_estimate": 10000,
            "surveillance_label_truth_state": "confirmed_surveillance",
            "surveillance_latest_freshness_state": "FRESH",
        }
        payload.update(overrides)
        return payload

    def test_policy_evaluates_model_score_cases_exposure_readiness_and_source_quality(self):
        facility = HealthFacility.objects.create(
            name="Phase Five Facility",
            facility_code="P5-FAC",
            ward=self.ward,
        )
        run = FacilityForecastRun.objects.create(
            model_version="fnb-phase5-v1",
            status=FacilityForecastRun.STATUS_SUCCESS,
            completed_at=timezone.now(),
        )
        FacilityForecast.objects.create(
            facility=facility,
            forecast_run=run,
            projected_case_burden=18,
            projected_pressure_score=90,
            projected_readiness_state=FacilityForecast.READINESS_CAPACITY_CONCERN,
            model_version=run.model_version,
        )

        decision = evaluate_ward_risk_decision_policy(
            ward=self.ward,
            prediction=self._fresh_prediction(population_total=30000),
            model_score=0.62,
            expected_case_burden=9,
        )

        self.assertEqual(decision["schema_version"], WARD_RISK_DECISION_POLICY_SCHEMA_VERSION)
        self.assertEqual(decision["risk_level"], Ward.RISK_HIGH)
        self.assertEqual(decision["alert_decision"], DECISION_URGENT_ALERT)
        self.assertTrue(decision["automatic_alert_allowed"])
        self.assertEqual(decision["inputs"]["facility_readiness_pressure"]["score"], 3)
        self.assertEqual(decision["inputs"]["source_confidence"]["confidence"], "high")
        self.assertEqual(decision["trace"]["risk_score_to_policy_link"], "RiskScore.decision_policy")

    def test_insufficient_forecast_horizon_adds_readiness_caveat_and_blocks_automatic_alert(self):
        decision = evaluate_ward_risk_decision_policy(
            ward=self.ward,
            prediction=self._fresh_prediction(
                rainfall_source_lineage={
                    "source_kind": "LIVE",
                    "freshness_state": "FRESH",
                    "record_type": "forecast",
                    "source_provider": "open-meteo-forecast",
                    "forecast_horizon_days": 3,
                    "lead_day": 3,
                },
            ),
            model_score=0.76,
            expected_case_burden=10,
        )

        climate_coverage = decision["inputs"]["climate_coverage"]
        self.assertFalse(climate_coverage["claimed_lead_time_climate_coverage_sufficient"])
        self.assertEqual(climate_coverage["forecast_covered_lead_days"], [1, 2, 3])
        self.assertIn(14, climate_coverage["forecast_missing_lead_days"])
        self.assertIn(
            "climate_forecast_horizon_insufficient",
            decision["inputs"]["source_confidence"]["moderate_reasons"],
        )
        self.assertFalse(decision["automatic_alert_allowed"])
        self.assertIn(
            "climate_forecast_horizon_blocks_automatic_alert",
            decision["automatic_alert_blockers"],
        )

    def test_fallback_static_climate_source_lowers_source_confidence(self):
        decision = evaluate_ward_risk_decision_policy(
            ward=self.ward,
            prediction=self._fresh_prediction(
                rainfall_source_lineage={
                    "source_kind": "SEEDED",
                    "freshness_state": "FRESH",
                    "record_type": "fallback_static",
                    "source_provider": "static-default",
                    "fallback_flag": True,
                },
            ),
            model_score=0.76,
            expected_case_burden=10,
        )

        source_confidence = decision["inputs"]["source_confidence"]
        self.assertEqual(source_confidence["confidence"], "low")
        self.assertIn("fallback_static_climate_source_used", source_confidence["weak_reasons"])
        self.assertTrue(decision["inputs"]["climate_coverage"]["fallback_static_rainfall_used"])

    def test_recent_alert_fatigue_blocks_non_urgent_automatic_alerts_but_keeps_trace(self):
        for index in range(4):
            Alert.objects.create(
                ward=self.ward,
                recipient=f"recipient-{index}",
                message="Recent alert",
                status=Alert.STATUS_DELIVERED,
            )

        decision = evaluate_ward_risk_decision_policy(
            ward=self.ward,
            prediction=self._fresh_prediction(),
            model_score=0.70,
            expected_case_burden=8,
        )

        self.assertEqual(decision["alert_decision"], DECISION_ALERT_CANDIDATE)
        self.assertFalse(decision["automatic_alert_allowed"])
        self.assertIn("recent_alert_fatigue_blocks_automatic_alert", decision["automatic_alert_blockers"])
        self.assertEqual(decision["inputs"]["recent_alert_fatigue"]["alert_count"], 4)

    def test_threshold_changes_are_versioned_and_auditable(self):
        result = set_ward_risk_decision_policy(
            policy_updates={
                "policy_version": "ward-risk-policy-test-v2",
                "thresholds": {
                    "risk_level": {"high_min_probability": 0.72},
                    "alerting": {"urgent_alert_min_probability": 0.88},
                },
            },
            reason="Phase 5 threshold calibration dry run",
        )

        policy = result["policy"]
        self.assertEqual(policy["policy_version"], "ward-risk-policy-test-v2")
        self.assertEqual(policy["thresholds"]["risk_level"]["high_min_probability"], 0.72)
        control = SystemControlState.objects.get(control_key=SystemControlState.KEY_WARD_RISK_DECISION_POLICY)
        self.assertTrue(control.is_active)
        self.assertEqual(control.metadata["change_history"][-1]["reason"], "Phase 5 threshold calibration dry run")
        self.assertEqual(current_ward_risk_decision_policy()["policy_version"], "ward-risk-policy-test-v2")

    def test_risk_score_serialization_and_alert_metadata_keep_policy_trace(self):
        decision = evaluate_ward_risk_decision_policy(
            ward=self.ward,
            prediction=self._fresh_prediction(
                rainfall_source_lineage={
                    "source_kind": "LIVE",
                    "freshness_state": "FRESH",
                    "record_type": "forecast",
                    "source_provider": "open-meteo-forecast",
                    "forecast_horizon_days": 14,
                    "lead_day": 14,
                },
            ),
            model_score=0.76,
            expected_case_burden=10,
        )
        risk_score = RiskScore.objects.create(
            ward=self.ward,
            score=0.76,
            risk_level=decision["risk_level"],
            predicted_cases=10,
            source=RiskScore.SOURCE_MODEL,
            model_version="lr-phase5-v1",
            decision_policy=decision,
        )

        serialized = RiskScoreSerializer(risk_score).data
        self.assertEqual(serialized["decision_policy"]["policy_version"], decision["policy_version"])
        dashboard_alert = create_alerts_for_riskscore(risk_score)[0]
        self.assertEqual(
            dashboard_alert.guided_request_metadata["decision_policy"]["policy_version"],
            decision["policy_version"],
        )
        self.assertEqual(
            dashboard_alert.guided_request_metadata["decision_policy"]["trace"]["model_score"],
            0.76,
        )
        climate_evidence = dashboard_alert.guided_request_metadata["climate_evidence"]
        self.assertEqual(climate_evidence["observed_vs_forecast_source_label"], "Forecast rainfall")
        self.assertTrue(climate_evidence["claimed_lead_time_climate_coverage_sufficient"])

    def test_policy_traced_risk_materializes_decision_policy_workflow(self):
        decision = evaluate_ward_risk_decision_policy(
            ward=self.ward,
            prediction=self._fresh_prediction(),
            model_score=0.78,
            expected_case_burden=11,
        )
        model_run = ModelRun.objects.create(
            algorithm_name="logistic-regression-baseline",
            model_version="lr-phase5-v1",
            status=ModelRun.STATUS_SUCCESS,
            metadata={
                "promotion_target": "live_baseline",
                "promotion_state": "promoted",
                "phase_4_promotion_gates_passed": True,
                "alert_eligible": True,
            },
            completed_at=timezone.now(),
        )
        RiskScore.objects.create(
            ward=self.ward,
            model_run=model_run,
            score=0.78,
            risk_level=decision["risk_level"],
            predicted_cases=11,
            source=RiskScore.SOURCE_MODEL,
            model_version="lr-phase5-v1",
            decision_policy=decision,
        )

        seed_approved_active_registry_entry(
            self,
            model_run,
            reason="Decision-policy workflow fixture uses an approved active model registry entry",
        )

        workflow = sync_alert_workflow_for_ward(self.ward)

        self.assertEqual(workflow.decision_mode, "decision_policy")
        self.assertEqual(workflow.rules_basis["rule_id"], "decision_policy_review_before_alerting")
        self.assertIn(f"policy_version={decision['policy_version']}", workflow.rules_basis["inputs"])
