import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from risk.models import (
    Alert,
    ExposureFeatureRecord,
    ModelRun,
    PopulationBaselineRecord,
    SurveillanceLabelWindow,
    SurveillanceRecord,
    Ward,
)
from risk.population_exposure_ingestion import inspect_population_exposure_csv
from risk.surveillance_ingestion import inspect_surveillance_csv
from risk.surveillance_labels import record_is_superseded_by_correction


class SeedE2ESourceFeedsCommandTestCase(TestCase):
    def setUp(self):
        self.hotspot = Ward.objects.create(
            name="North Kamagambo",
            county="Migori",
            ward_code="KE-MIG-NK",
            current_risk_level=Ward.RISK_HIGH,
            current_risk_score=0.82,
        )
        self.quieter_ward = Ward.objects.create(
            name="Kaler",
            county="Migori",
            ward_code="KE-MIG-KAL",
            current_risk_level=Ward.RISK_LOW,
            current_risk_score=0.18,
        )

    def test_command_generates_adapter_valid_feeds_and_ingests_seeded_records(self):
        stdout = StringIO()
        with tempfile.TemporaryDirectory() as temp_dir:
            call_command(
                "seed_e2e_source_feeds",
                "--output-dir",
                temp_dir,
                "--as-of",
                "2026-05-05",
                "--weeks",
                "4",
                "--ingest",
                stdout=stdout,
            )

            population_path = Path(temp_dir) / "population_exposure_seed_e2e_2026-05-05.csv"
            surveillance_path = Path(temp_dir) / "surveillance_seed_e2e_2026-05-05.csv"
            self.assertTrue(population_path.exists())
            self.assertTrue(surveillance_path.exists())

            population_inspection = inspect_population_exposure_csv(
                population_path,
                source_type="csv_backfill",
            )
            surveillance_inspection = inspect_surveillance_csv(
                surveillance_path,
                source_type="weekly_aggregate",
                source_name="seed-e2e-county-surveillance-demo",
            )

        self.assertEqual(population_inspection["records_seen"], 14)
        self.assertEqual(population_inspection["records_rejected"], 0)
        self.assertEqual(surveillance_inspection["records_seen"], 8)
        self.assertEqual(surveillance_inspection["records_rejected"], 0)
        self.assertEqual(surveillance_inspection["truth_level_counts"], {"seeded_demo": 8})
        self.assertEqual(PopulationBaselineRecord.objects.count(), 2)
        self.assertEqual(ExposureFeatureRecord.objects.count(), 12)
        self.assertEqual(SurveillanceRecord.objects.count(), 24)
        self.assertGreater(SurveillanceLabelWindow.objects.count(), 0)
        self.assertIn("Ingested e2e source feeds", stdout.getvalue())

    def test_repeated_ingest_supersedes_prior_generated_surveillance_records(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            for _ in range(2):
                call_command(
                    "seed_e2e_source_feeds",
                    "--output-dir",
                    temp_dir,
                    "--as-of",
                    "2026-05-05",
                    "--weeks",
                    "4",
                    "--ingest",
                )

        records = list(SurveillanceRecord.objects.order_by("id"))
        active_records = [record for record in records if not record_is_superseded_by_correction(record)]

        self.assertEqual(SurveillanceRecord.objects.count(), 48)
        self.assertEqual(len(active_records), 24)
        self.assertEqual(
            SurveillanceRecord.objects.filter(supersedes_record_ref__gt="").count(),
            24,
        )

    def test_command_can_materialize_dashboard_only_simulation_alerts_after_scoring(self):
        stdout = StringIO()
        with tempfile.TemporaryDirectory() as temp_dir:
            call_command(
                "seed_e2e_source_feeds",
                "--output-dir",
                temp_dir,
                "--as-of",
                "2026-05-05",
                "--weeks",
                "4",
                "--ingest",
                "--build-downstream",
                "--score",
                "--simulate-alerts",
                stdout=stdout,
            )

        model_version = "lr-seed-e2e-20260505"
        model_run = ModelRun.objects.get(model_version=model_version)
        alerts = Alert.objects.filter(external_id__startswith=f"seed-e2e-sim-alert:{model_version}:")

        self.assertEqual(model_run.metadata["promotion_state"], "promotion_blocked")
        self.assertFalse(model_run.metadata["alert_eligible"])
        self.assertGreater(alerts.count(), 0)
        self.assertFalse(alerts.exclude(channel=Alert.CHANNEL_DASHBOARD).exists())
        self.assertFalse(alerts.exclude(status=Alert.STATUS_DELIVERED).exists())
        self.assertFalse(alerts.exclude(delivery_backend="internal-dashboard-e2e-simulation").exists())
        first_alert = alerts.first()
        self.assertTrue(first_alert.guided_request_metadata["simulation"])
        self.assertIn(
            first_alert.guided_request_metadata["simulation_trigger_mode"],
            {"decision_policy_alert_candidate", "top_ranked_threshold_probe"},
        )
        self.assertEqual(
            first_alert.guided_request_metadata["production_alert_guardrails"]["promotion_state"],
            "promotion_blocked",
        )
        self.assertIn("dashboard-only e2e simulation alerts", stdout.getvalue())
