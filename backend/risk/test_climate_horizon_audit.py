import json
from datetime import date, datetime, time, timedelta
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from risk.climate_horizon_audit import (
    CLIMATE_HORIZON_AUDIT_SCHEMA_VERSION,
    backfill_alert_climate_evidence,
    build_climate_horizon_monitoring_audit,
)
from risk.climate_coverage import climate_alert_evidence_from_prediction
from risk.lead_time_features import LEAD_TIME_FEATURE_SCHEMA_VERSION
from risk.models import Alert, FeatureDataset, FeatureDatasetRow, ModelRun, RiskScore, Ward


class ClimateHorizonAuditPhaseFiveTestCase(TestCase):
    def setUp(self):
        self.ward = Ward.objects.create(
            name="Climate Horizon Ward",
            county="Migori",
            ward_code="CH-P5",
            current_risk_level=Ward.RISK_HIGH,
            current_risk_score=0.81,
        )

    def _cutoff(self, prediction_date: date):
        return timezone.make_aware(datetime.combine(prediction_date, time.min), timezone.get_current_timezone())

    def _feature_dataset(self, suffix: str):
        return FeatureDataset.objects.create(
            dataset_ref=f"phase5-climate-horizon-{suffix}",
            dataset_kind=FeatureDataset.KIND_INFERENCE,
            schema_version=LEAD_TIME_FEATURE_SCHEMA_VERSION,
            source_kind=FeatureDataset.SOURCE_KIND_LIVE,
            month=4,
            feature_keys=["prediction_date", "forecast_coverage_days", "source_lineage"],
            row_count=1,
        )

    def _climate_evidence(self, *, sufficient=True):
        missing_days = [] if sufficient else list(range(4, 15))
        return {
            "schema_version": "climate-alert-evidence-v1",
            "record_type": "forecast",
            "source_provider": "open-meteo-forecast",
            "observed_vs_forecast_source_label": "Forecast rainfall",
            "issue_time": "2026-04-30T21:00:00+03:00",
            "valid_date": "2026-05-14",
            "lead_day": 14 if sufficient else 3,
            "forecast_horizon_days": 14 if sufficient else 3,
            "claimed_forecast_horizon_days": 14,
            "forecast_coverage_days": 14 if sufficient else 3,
            "forecast_missing_lead_days": missing_days,
            "claimed_lead_time_climate_coverage_sufficient": sufficient,
            "fallback_static_rainfall_used": False,
            "climate_source_confidence": 1.0 if sufficient else 0.55,
            "climate_source_confidence_label": "high" if sufficient else "moderate",
            "climate_coverage_status": "sufficient" if sufficient else "insufficient_forecast_horizon",
            "climate_coverage_caveats": [] if sufficient else ["forecast_missing_claimed_lead_days"],
        }

    def _promotion_model_run(self, *, complete_climate_summary: bool):
        climate_summary = {
            "schema_version": "climate-coverage-policy-v1",
            "row_count": 1,
            "ready_for_claimed_forecast_horizon": True,
            "readiness_caveats": [],
        }
        report = {
            "schema_version": "ward-risk-temporal-backtest-v1",
            "climate_coverage_summary": climate_summary if complete_climate_summary else {},
            "validation_climate_coverage_summary": climate_summary if complete_climate_summary else {},
            "promotion_gates": {"checks": {"climate_coverage_ready": complete_climate_summary}},
        }
        metrics = {
            "temporal_backtest_report": report,
            "climate_coverage_gate_passed": complete_climate_summary,
        }
        metadata = {
            "phase_4_promotion_evidence_persisted": True,
            "phase_4_promotion_gates_passed": complete_climate_summary,
            "promotion_target": "live_baseline" if complete_climate_summary else "benchmark_only",
        }
        if complete_climate_summary:
            metrics.update(
                {
                    "climate_coverage_summary": climate_summary,
                    "validation_climate_coverage_summary": climate_summary,
                }
            )
            metadata.update(
                {
                    "climate_coverage_summary": climate_summary,
                    "climate_coverage_gate": {
                        "passed": True,
                        "validation_summary": climate_summary,
                    },
                }
            )
        return ModelRun.objects.create(
            algorithm_name="logistic-regression-baseline",
            model_version=f"phase5-climate-audit-{complete_climate_summary}",
            status=ModelRun.STATUS_SUCCESS,
            feature_schema_version=LEAD_TIME_FEATURE_SCHEMA_VERSION,
            evaluation_metrics=metrics,
            metadata=metadata,
            completed_at=timezone.now(),
        )

    def _risk_score_and_alert(self, *, climate_evidence: dict):
        risk_score = RiskScore.objects.create(
            ward=self.ward,
            score=0.83,
            risk_level=Ward.RISK_HIGH,
            rainfall_mm=64,
            predicted_cases=8,
            decision_policy={
                "schema_version": "ward-risk-decision-policy-v1",
                "inputs": {"climate_coverage": climate_evidence},
            },
        )
        Alert.objects.create(
            ward=self.ward,
            risk_score=risk_score,
            channel=Alert.CHANNEL_DASHBOARD,
            recipient="dashboard",
            message="Climate horizon test alert",
            status=Alert.STATUS_DELIVERED,
            guided_request_metadata={"climate_evidence": climate_evidence},
        )
        return risk_score

    def test_climate_horizon_audit_passes_for_source_separated_evidence(self):
        prediction_date = date(2026, 5, 1)
        issue_time = self._cutoff(prediction_date) - timedelta(hours=3)
        dataset = self._feature_dataset("pass")
        FeatureDatasetRow.objects.create(
            dataset=dataset,
            ward=self.ward,
            ward_name_snapshot=self.ward.name,
            month=prediction_date.month,
            feature_values={
                "prediction_date": prediction_date.isoformat(),
                "source_cutoff_timestamp": self._cutoff(prediction_date).isoformat(),
                "observed_rainfall_total_3d": 0,
                "observed_rainfall_total_7d": 0,
                "observed_rainfall_total_14d": 0,
                "forecast_coverage_days": 14,
                "forecast_covered_lead_days": list(range(1, 15)),
                "forecast_missing_lead_days": [],
                "forecast_max_lead_day": 14,
                "claimed_forecast_horizon_days": 14,
                "claimed_lead_time_climate_coverage_sufficient": True,
                "fallback_static_rainfall_used": False,
                "climate_coverage_status": "sufficient",
                "climate_coverage_caveats": [],
                "source_lineage": {
                    "rainfall": {"max_source_timestamp": None},
                    "forecast_rainfall": {
                        "selected_record_count": 14,
                        "selected_issue_time": issue_time.isoformat(),
                        "covered_lead_days": list(range(1, 15)),
                        "max_forecast_horizon_days": 14,
                        "max_contract_lead_day": 14,
                    },
                    "fallback_static_rainfall": {"record_count": 0},
                    "climate_coverage": {
                        "fallback_static_rainfall_used": False,
                        "claimed_lead_time_climate_coverage_sufficient": True,
                    },
                },
                "leakage_proof": {
                    "future_observed_climate_used": False,
                    "passes_cutoff_check": True,
                    "source_cutoff_timestamp": self._cutoff(prediction_date).isoformat(),
                },
            },
        )
        self._promotion_model_run(complete_climate_summary=True)
        self._risk_score_and_alert(climate_evidence=self._climate_evidence())

        audit = build_climate_horizon_monitoring_audit(feature_dataset_ref=dataset.dataset_ref)

        self.assertEqual(audit["schema_version"], CLIMATE_HORIZON_AUDIT_SCHEMA_VERSION)
        self.assertEqual(audit["overall_status"], "pass")
        self.assertEqual(audit["record_totals"]["feature_rows_scanned"], 1)
        self.assertTrue(all(check["status"] == "pass" for check in audit["checks"]))

    def test_climate_horizon_audit_flags_phase_5_failure_modes(self):
        prediction_date = date(2026, 5, 1)
        cutoff = self._cutoff(prediction_date)
        dataset = self._feature_dataset("fail")
        dataset.row_count = 2
        dataset.save(update_fields=["row_count"])
        FeatureDatasetRow.objects.create(
            dataset=dataset,
            ward=self.ward,
            ward_name_snapshot=self.ward.name,
            month=prediction_date.month,
            feature_values={
                "prediction_date": prediction_date.isoformat(),
                "source_cutoff_timestamp": cutoff.isoformat(),
                "observed_rainfall_total_3d": 30,
                "observed_rainfall_total_7d": 30,
                "observed_rainfall_total_14d": 30,
                "forecast_coverage_days": 4,
                "forecast_covered_lead_days": [1, 2, 3, 4],
                "forecast_missing_lead_days": list(range(5, 15)),
                "forecast_max_lead_day": 4,
                "claimed_forecast_horizon_days": 14,
                "claimed_lead_time_climate_coverage_sufficient": True,
                "fallback_static_rainfall_used": True,
                "record_type": "forecast",
                "observed_vs_forecast_source_label": "Forecast rainfall",
                "climate_coverage_status": "sufficient",
                "climate_coverage_caveats": [],
                "source_lineage": {
                    "rainfall": {"max_source_timestamp": (cutoff + timedelta(hours=1)).isoformat()},
                    "forecast_rainfall": {
                        "selected_record_count": 1,
                        "covered_lead_days": [1, 2, 3, 4],
                        "max_forecast_horizon_days": 3,
                        "max_contract_lead_day": 3,
                    },
                    "fallback_static_rainfall": {"record_count": 1},
                    "climate_coverage": {"fallback_static_rainfall_used": True},
                },
                "leakage_proof": {
                    "future_observed_climate_used": True,
                    "passes_cutoff_check": False,
                    "source_cutoff_timestamp": cutoff.isoformat(),
                    "max_observed_rainfall_timestamp": (cutoff + timedelta(hours=1)).isoformat(),
                },
            },
        )
        FeatureDatasetRow.objects.create(
            dataset=dataset,
            ward=self.ward,
            ward_name_snapshot=self.ward.name,
            month=prediction_date.month,
            feature_values={
                "prediction_date": (prediction_date + timedelta(days=1)).isoformat(),
                "source_cutoff_timestamp": (cutoff + timedelta(days=1)).isoformat(),
                "observed_rainfall_total_3d": 0,
                "observed_rainfall_total_7d": 0,
                "observed_rainfall_total_14d": 0,
                "forecast_coverage_days": 0,
                "forecast_covered_lead_days": [],
                "forecast_missing_lead_days": list(range(1, 15)),
                "claimed_forecast_horizon_days": 14,
                "claimed_lead_time_climate_coverage_sufficient": True,
                "fallback_static_rainfall_used": True,
                "record_type": "forecast",
                "observed_vs_forecast_source_label": "Forecast rainfall",
                "climate_coverage_status": "sufficient",
                "climate_coverage_caveats": [],
                "source_lineage": {
                    "rainfall": {"max_source_timestamp": None},
                    "forecast_rainfall": {"selected_record_count": 0, "covered_lead_days": []},
                    "fallback_static_rainfall": {"record_count": 1},
                    "climate_coverage": {"fallback_static_rainfall_used": True},
                },
                "leakage_proof": {
                    "future_observed_climate_used": False,
                    "passes_cutoff_check": True,
                    "source_cutoff_timestamp": (cutoff + timedelta(days=1)).isoformat(),
                },
            },
        )
        self._promotion_model_run(complete_climate_summary=False)
        bad_climate_evidence = {
            "record_type": "forecast",
            "observed_vs_forecast_source_label": "Forecast rainfall",
            "fallback_static_rainfall_used": True,
        }
        self._risk_score_and_alert(climate_evidence=bad_climate_evidence)

        audit = build_climate_horizon_monitoring_audit(feature_dataset_ref=dataset.dataset_ref)

        self.assertEqual(audit["overall_status"], "fail")
        issue_check_ids = {issue["check_id"] for issue in audit["issues"]}
        self.assertIn("forecast_feature_issue_time_present", issue_check_ids)
        self.assertIn("forecast_lead_days_within_provider_horizon", issue_check_ids)
        self.assertIn("climate_coverage_arithmetic_consistent", issue_check_ids)
        self.assertIn("future_observed_rainfall_not_used", issue_check_ids)
        self.assertIn("fallback_static_not_presented_as_live_forecast", issue_check_ids)
        self.assertIn("promotion_report_climate_coverage_summary_present", issue_check_ids)
        self.assertIn("model_evidence_climate_source_separation_present", issue_check_ids)
        self.assertIn("frontend_climate_horizon_payload_fields_present", issue_check_ids)

    def test_climate_evidence_normalizer_reads_forecast_source_lineage_for_alerts(self):
        prediction = {
            "prediction_date": "2026-05-01",
            "forecast_coverage_days": 3,
            "forecast_covered_lead_days": [1, 2, 3],
            "forecast_missing_lead_days": list(range(4, 15)),
            "claimed_forecast_horizon_days": 14,
            "claimed_lead_time_climate_coverage_sufficient": False,
            "climate_coverage_status": "insufficient_forecast_horizon",
            "climate_coverage_caveats": ["forecast_missing_claimed_lead_days"],
            "source_lineage": {
                "forecast_rainfall": {
                    "selected_record_count": 1,
                    "selected_issue_time": "2026-04-30T21:00:00+03:00",
                    "covered_lead_days": [1, 2, 3],
                    "missing_lead_days": list(range(4, 15)),
                    "max_forecast_horizon_days": 3,
                    "max_contract_lead_day": 3,
                    "source_providers": ["open-meteo-forecast"],
                }
            },
        }

        climate_evidence = climate_alert_evidence_from_prediction(prediction)

        self.assertEqual(climate_evidence["record_type"], "forecast")
        self.assertEqual(climate_evidence["source_provider"], "open-meteo-forecast")
        self.assertEqual(climate_evidence["issue_time"], "2026-04-30T21:00:00+03:00")
        self.assertEqual(climate_evidence["valid_date"], "2026-05-03")
        self.assertEqual(climate_evidence["forecast_coverage_days"], 3)
        self.assertEqual(climate_evidence["forecast_missing_lead_days"], list(range(4, 15)))

    def test_backfill_alert_climate_evidence_repairs_existing_alert_metadata(self):
        climate_evidence = self._climate_evidence()
        risk_score = RiskScore.objects.create(
            ward=self.ward,
            score=0.83,
            risk_level=Ward.RISK_HIGH,
            decision_policy={
                "schema_version": "ward-risk-decision-policy-v1",
                "inputs": {"climate_coverage": climate_evidence},
            },
        )
        alert = Alert.objects.create(
            ward=self.ward,
            risk_score=risk_score,
            channel=Alert.CHANNEL_DASHBOARD,
            recipient="dashboard",
            message="Legacy alert missing climate evidence",
            status=Alert.STATUS_DELIVERED,
            guided_request_metadata={},
        )

        output = StringIO()
        call_command("backfill_alert_climate_evidence", "--format", "json", stdout=output)
        command_payload = json.loads(output.getvalue())
        self.assertEqual(command_payload["updated_count"], 1)

        dry_run = backfill_alert_climate_evidence(dry_run=True)
        self.assertEqual(dry_run["updated_count"], 1)
        alert.refresh_from_db()
        self.assertNotIn("climate_evidence", alert.guided_request_metadata)

        applied = backfill_alert_climate_evidence(dry_run=False)
        alert.refresh_from_db()

        self.assertEqual(applied["updated_count"], 1)
        self.assertEqual(alert.guided_request_metadata["climate_evidence"]["source_provider"], "open-meteo-forecast")
        self.assertEqual(alert.guided_request_metadata["climate_evidence"]["forecast_coverage_days"], 14)
        self.assertIn("climate_evidence_backfill", alert.guided_request_metadata)

    def test_backfill_alert_climate_evidence_repairs_malformed_existing_evidence(self):
        risk_score = RiskScore.objects.create(
            ward=self.ward,
            score=0.72,
            risk_level=Ward.RISK_HIGH,
            decision_policy={},
        )
        alert = Alert.objects.create(
            ward=self.ward,
            risk_score=risk_score,
            channel=Alert.CHANNEL_DASHBOARD,
            recipient="dashboard",
            message="Legacy alert with malformed climate evidence",
            status=Alert.STATUS_DELIVERED,
            guided_request_metadata={
                "climate_evidence": {
                    "schema_version": "climate-alert-evidence-v1",
                    "record_type": "",
                    "source_provider": "",
                    "observed_vs_forecast_source_label": "Climate source unavailable",
                    "claimed_forecast_horizon_days": 14,
                    "forecast_coverage_days": 0,
                    "forecast_missing_lead_days": [],
                    "claimed_lead_time_climate_coverage_sufficient": False,
                    "fallback_static_rainfall_used": False,
                    "climate_coverage_status": "unavailable",
                    "climate_coverage_caveats": ["climate_coverage_evidence_missing"],
                }
            },
        )

        applied = backfill_alert_climate_evidence(dry_run=False)
        alert.refresh_from_db()

        self.assertEqual(applied["updated_count"], 1)
        self.assertEqual(alert.guided_request_metadata["climate_evidence"]["record_type"], "unavailable")
        self.assertIn("climate_evidence_backfill", alert.guided_request_metadata)

    def test_unavailable_alert_climate_evidence_stays_visible_as_warning(self):
        risk_score = RiskScore.objects.create(
            ward=self.ward,
            score=0.72,
            risk_level=Ward.RISK_HIGH,
            decision_policy={},
        )
        Alert.objects.create(
            ward=self.ward,
            risk_score=risk_score,
            channel=Alert.CHANNEL_DASHBOARD,
            recipient="dashboard",
            message="Unavailable climate evidence",
            status=Alert.STATUS_DELIVERED,
            guided_request_metadata={
                "climate_evidence": {
                    "schema_version": "climate-alert-evidence-v1",
                    "record_type": "unavailable",
                    "source_provider": "",
                    "observed_vs_forecast_source_label": "Climate source unavailable",
                    "issue_time": None,
                    "valid_date": None,
                    "lead_day": None,
                    "forecast_horizon_days": None,
                    "claimed_forecast_horizon_days": 14,
                    "forecast_coverage_days": 0,
                    "forecast_missing_lead_days": list(range(1, 15)),
                    "claimed_lead_time_climate_coverage_sufficient": False,
                    "fallback_static_rainfall_used": False,
                    "climate_source_confidence": 0,
                    "climate_source_confidence_label": "low",
                    "climate_coverage_status": "unavailable",
                    "climate_coverage_caveats": ["climate_coverage_evidence_missing"],
                }
            },
        )

        audit = build_climate_horizon_monitoring_audit()
        alert_check = next(
            check for check in audit["checks"] if check["id"] == "frontend_climate_horizon_payload_fields_present"
        )

        self.assertEqual(alert_check["status"], "warning")
        self.assertIn("climate evidence is unavailable", alert_check["issues"][0]["message"])

    def test_audit_climate_horizon_command_outputs_json_and_strict_fails_on_issues(self):
        self._promotion_model_run(complete_climate_summary=False)
        output = StringIO()

        call_command("audit_climate_horizon", "--format", "json", stdout=output)
        payload = json.loads(output.getvalue())

        self.assertEqual(payload["schema_version"], CLIMATE_HORIZON_AUDIT_SCHEMA_VERSION)
        self.assertEqual(payload["overall_status"], "fail")
        with self.assertRaises(CommandError):
            call_command("audit_climate_horizon", "--strict", stdout=StringIO())
