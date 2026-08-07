import tempfile
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from risk.facility_forecasting import run_facility_burden_forecast_pipeline
from risk.ml.data import SURVEILLANCE_REFERENCE_ONLY_LABEL_USAGE, build_inference_feature_dataset
from risk.ml.pipeline import run_mock_prediction_pipeline
from risk.models import (
    FacilityForecast,
    FeatureDatasetRow,
    HealthFacility,
    ModelRun,
    RiskScore,
    SurveillanceSource,
    Ward,
)
from risk.services import build_alert_intelligence_snapshot, create_alerts_for_riskscore, sync_alert_workflow_for_ward
from risk.surveillance_ingestion import run_surveillance_csv_ingestion
from risk.surveillance_features import build_surveillance_feature_snapshot
from risk.surveillance_labels import build_surveillance_label_dataset


class SurveillancePhaseFiveIntegrationTestCase(TestCase):
    def setUp(self):
        self.reference_date = timezone.localdate() - timedelta(days=1)
        self.as_of = None
        self.ward = Ward.objects.create(
            name="North Kamagambo",
            county="Migori",
            ward_code="KE-MIG-NK",
            current_risk_level=Ward.RISK_HIGH,
            current_risk_score=0.86,
            is_active=True,
        )
        self.facility = HealthFacility.objects.create(
            name="Kamagambo Dispensary",
            facility_code="KM-DISP",
            ward=self.ward,
            is_active=True,
        )
        self.live_model_run = ModelRun.objects.create(
            algorithm_name="logistic-regression-baseline",
            model_version="phase5-live-v1",
            status=ModelRun.STATUS_SUCCESS,
            metadata={
                "algorithm": "logistic_regression",
                "promotion_target": "live_baseline",
                "promotion_state": "promoted",
                "phase_4_promotion_gates_passed": True,
                "alert_eligible": True,
            },
        )
        self.risk_score = RiskScore.objects.create(
            ward=self.ward,
            model_run=self.live_model_run,
            score=0.86,
            risk_level=Ward.RISK_HIGH,
            rainfall_mm=120,
            flood_indicator=0.7,
            predicted_cases=12,
            source=RiskScore.SOURCE_MODEL,
            model_version="phase5-live-v1",
        )

    def _ingest_surveillance_csv(self, *, suspected=0, confirmed=0, proxy=0, source_name="county-weekly-report"):
        suspected_cell = "" if suspected is None else suspected
        confirmed_cell = "" if confirmed is None else confirmed
        proxy_cell = "" if proxy is None else proxy
        with tempfile.NamedTemporaryFile("w", suffix=".csv") as csv_file:
            csv_file.write(
                "ward_code,reporting_period_start,reporting_period_end,"
                "suspected_cholera_count,confirmed_cholera_count,diarrheal_count,source_ref\n"
            )
            csv_file.write(
                f"KE-MIG-NK,{self.reference_date - timedelta(days=6)},{self.reference_date},"
                f"{suspected_cell},{confirmed_cell},{proxy_cell},phase5.csv\n"
            )
            csv_file.flush()
            return run_surveillance_csv_ingestion(
                file_path=csv_file.name,
                source_name=source_name,
                source_type=SurveillanceSource.SOURCE_TYPE_WEEKLY_AGGREGATE,
                source_timestamp=f"{self.reference_date + timedelta(days=1)}T00:00:00+03:00",
            )

    def _build_labels(self, *, dataset_role="evaluation"):
        dataset = build_surveillance_label_dataset(
            start_date=self.reference_date - timedelta(days=6),
            end_date=self.reference_date,
            dataset_role=dataset_role,
        )
        self.as_of = timezone.now()
        return dataset

    def test_inference_feature_dataset_exposes_surveillance_context_and_truth_gate(self):
        self._ingest_surveillance_csv(suspected=7, confirmed=2, proxy=5)
        self._build_labels(dataset_role="evaluation")

        snapshot = build_inference_feature_dataset([self.ward], month=4, as_of=self.as_of)

        row = FeatureDatasetRow.objects.get(dataset=snapshot.feature_dataset)
        self.assertEqual(row.feature_values["surveillance_recent_suspected_cases_28d"], 7)
        self.assertEqual(row.feature_values["surveillance_recent_confirmed_cases_28d"], 2)
        self.assertEqual(row.feature_values["surveillance_recent_proxy_cases_28d"], 5)
        self.assertEqual(row.feature_values["historical_cases_source"], "canonical_surveillance_records_28d")
        self.assertEqual(
            row.feature_values["rainfall_source_lineage"]["ingestion_run_id"],
            snapshot.rainfall_ingestion_run.id,
        )
        self.assertEqual(
            snapshot.feature_dataset.lineage_metadata["surveillance_feature_coverage"]["record_count"],
            3,
        )
        self.assertFalse(
            snapshot.feature_dataset.lineage_metadata["surveillance_truth_gate"]["proxy_only_as_confirmed_allowed"]
        )

    def test_surveillance_snapshot_uses_reference_date_and_ages_out_after_calendar_advance(self):
        self._ingest_surveillance_csv(suspected=7, confirmed=2, proxy=5)
        self._build_labels(dataset_role="evaluation")

        current_snapshot = build_surveillance_feature_snapshot([self.ward], as_of=self.as_of)
        advanced_snapshot = build_surveillance_feature_snapshot(
            [self.ward],
            as_of=self.as_of + timedelta(days=180),
        )

        self.assertEqual(current_snapshot.coverage["record_count"], 3)
        self.assertEqual(current_snapshot.coverage["label_window_count"], 1)
        self.assertEqual(advanced_snapshot.coverage["record_count"], 0)
        self.assertEqual(advanced_snapshot.coverage["label_window_count"], 0)

    def test_model_run_records_surveillance_lead_time_validation_gate(self):
        self._ingest_surveillance_csv(suspected=4, confirmed=1)
        self._build_labels(dataset_role="training")

        run_mock_prediction_pipeline(month=4, model_version="lr-phase5-surveillance-v1", as_of=self.as_of)

        model_run = ModelRun.objects.get(model_version="lr-phase5-surveillance-v1")
        validation = model_run.evaluation_metrics["surveillance_lead_time_validation"]
        self.assertEqual(validation["status"], "ready_for_lead_time_review")
        self.assertEqual(validation["truth_gate"]["confirmed_truth_label_count"], 1)
        self.assertFalse(model_run.metadata["surveillance_label_truth_gate"]["proxy_only_as_confirmed_allowed"])
        self.assertEqual(
            model_run.metadata["surveillance_label_usage"],
            SURVEILLANCE_REFERENCE_ONLY_LABEL_USAGE,
        )
        self.assertEqual(
            model_run.metadata["training_label_readiness"]["reason"],
            "surveillance_label_dataset_lacks_positive_and_negative_classes",
        )

    def test_facility_forecast_consumes_surveillance_trend_context_with_caveat(self):
        self._ingest_surveillance_csv(suspected=9, confirmed=1, proxy=4)
        self._build_labels(dataset_role="evaluation")

        run = run_facility_burden_forecast_pipeline(
            model_version="fnb-phase5-surveillance-v1",
            as_of=self.as_of,
        )

        forecast = FacilityForecast.objects.get(forecast_run=run, facility=self.facility)
        factor_sources = {factor["source"] for factor in forecast.forecast_factors}
        self.assertIn("surveillance_trend_context", factor_sources)
        self.assertGreaterEqual(run.metadata["surveillance_feature_coverage"]["record_count"], 3)
        self.assertFalse(run.metadata["surveillance_truth_gate"]["proxy_only_as_confirmed_allowed"])

    def test_alert_workflow_and_intelligence_cite_proxy_only_surveillance_truth(self):
        self._ingest_surveillance_csv(
            suspected=None,
            confirmed=None,
            proxy=14,
            source_name="diarrheal-proxy-weekly-report",
        )
        self._build_labels(dataset_role="evaluation")

        workflow = sync_alert_workflow_for_ward(self.ward, as_of=self.as_of)
        labels = {item["label"] for item in workflow.trigger_reason_items}
        self.assertIn("Proxy-only surveillance evidence", labels)
        self.assertEqual(
            workflow.metadata["surveillance_evidence"]["label_truth_state"],
            "proxy_only_not_confirmed",
        )

        alert = create_alerts_for_riskscore(self.risk_score, as_of=self.as_of)[0]
        snapshot = build_alert_intelligence_snapshot(alert)

        self.assertEqual(snapshot["surveillance_evidence"]["label_truth_state"], "proxy_only_not_confirmed")
        self.assertFalse(snapshot["surveillance_evidence"]["proxy_only_as_confirmed_allowed"])
        self.assertTrue(
            any(item["label"] == "Surveillance truth: proxy_only_not_confirmed" for item in snapshot["current_state"])
        )
