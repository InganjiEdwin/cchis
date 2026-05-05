import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from risk.models import (
    ExposureFeatureRecord,
    PopulationBaselineRecord,
    SurveillanceLabelWindow,
    SurveillanceRecord,
    Ward,
)
from risk.population_exposure_ingestion import inspect_population_exposure_csv
from risk.surveillance_ingestion import inspect_surveillance_csv


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
