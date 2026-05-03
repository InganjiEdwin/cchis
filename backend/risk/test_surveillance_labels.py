import tempfile
from datetime import date
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from risk.ml.data import SURVEILLANCE_LABEL_TRAINING_USAGE, build_training_feature_dataset
from risk.models import (
    FeatureDataset,
    FeatureDatasetRow,
    PopulationBaselineRecord,
    PopulationExposureFreshness,
    PopulationExposureIngestionRun,
    PopulationExposureSource,
    PopulationExposureSourceKind,
    PopulationExposureTruth,
    SurveillanceIngestionRun,
    SurveillanceLabelWindow,
    SurveillanceOutbreakLabel,
    SurveillanceSource,
    SurveillanceTruthLevel,
    Ward,
)
from risk.surveillance_ingestion import replay_surveillance_ingestion_run, run_surveillance_csv_ingestion
from risk.surveillance_labels import (
    SURVEILLANCE_LABEL_SCHEMA_VERSION,
    build_surveillance_label_dataset,
)


class SurveillanceLabelPhaseThreeTestCase(TestCase):
    def setUp(self):
        self.ward = Ward.objects.create(
            name="North Kamagambo",
            county="Migori",
            ward_code="KE-MIG-NK",
            current_risk_level=Ward.RISK_HIGH,
            current_risk_score=0.84,
        )

    def _create_population_baseline(self):
        source = PopulationExposureSource.objects.create(
            source_name="county-population-baseline",
            source_type=PopulationExposureSource.SOURCE_TYPE_POPULATION_BASELINE,
            release_version="phase1-pop-v1",
            source_ref="population-baseline.csv",
        )
        run = PopulationExposureIngestionRun.objects.create(
            source=source,
            status=PopulationExposureIngestionRun.STATUS_SUCCESS,
            source_name=source.source_name,
            source_type=source.source_type,
            release_version=source.release_version,
            source_ref=source.source_ref,
            adapter_key="population_baseline_csv",
            input_ref="fixtures/population-baseline.csv",
            records_seen=1,
            records_loaded=1,
            completed_at=timezone.now(),
        )
        return PopulationBaselineRecord.objects.create(
            ward=self.ward,
            ingestion_run=run,
            source=source,
            recorded_at=timezone.now(),
            population_total=12400,
            population_under_five=1800,
            household_count_proxy=2600,
            truth_class=PopulationExposureTruth.DIRECT_POPULATION_BASELINE,
            source_name=source.source_name,
            source_kind=PopulationExposureSourceKind.LIVE,
            freshness_state=PopulationExposureFreshness.FRESH,
            release_version=source.release_version,
            source_ref=source.source_ref,
        )

    def _write_two_window_csv(self, csv_file):
        csv_file.write(
            "ward_code,reporting_period_start,reporting_period_end,"
            "suspected_cholera_count,confirmed_cholera_count,diarrheal_count,source_ref\n"
        )
        csv_file.write("KE-MIG-NK,2026-04-01,2026-04-07,4,1,,weekly.csv\n")
        csv_file.write("KE-MIG-NK,2026-04-08,2026-04-14,6,,,weekly.csv\n")
        csv_file.flush()

    def test_build_surveillance_label_dataset_generates_weekly_windows_and_feature_rows(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv") as csv_file:
            self._write_two_window_csv(csv_file)
            run_surveillance_csv_ingestion(
                file_path=csv_file.name,
                source_name="county-weekly-report",
                source_type=SurveillanceSource.SOURCE_TYPE_WEEKLY_AGGREGATE,
            )

        snapshot = build_surveillance_label_dataset(
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 14),
        )

        dataset = snapshot.feature_dataset
        self.assertEqual(dataset.schema_version, SURVEILLANCE_LABEL_SCHEMA_VERSION)
        self.assertEqual(dataset.dataset_kind, FeatureDataset.KIND_TRAINING)
        self.assertEqual(dataset.row_count, 2)
        self.assertEqual(dataset.lineage_metadata["coverage"]["active_label_count"], 1)
        self.assertEqual(dataset.lineage_metadata["coverage"]["watch_label_count"], 1)

        windows = list(SurveillanceLabelWindow.objects.order_by("label_window_start"))
        self.assertEqual(len(windows), 2)
        self.assertEqual(windows[0].outbreak_label, SurveillanceOutbreakLabel.ACTIVE)
        self.assertEqual(windows[0].confirmed_case_count, 1)
        self.assertEqual(windows[0].label_truth_level, SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE)
        self.assertEqual(windows[1].outbreak_label, SurveillanceOutbreakLabel.WATCH)
        self.assertEqual(windows[1].suspected_case_count, 6)
        self.assertEqual(windows[1].label_truth_level, SurveillanceTruthLevel.SUSPECTED_SURVEILLANCE)

        rows = list(FeatureDatasetRow.objects.filter(dataset=dataset).order_by("id"))
        self.assertEqual([row.label for row in rows], [1, 0])
        self.assertEqual(rows[0].feature_values["generated_from_record_refs"], windows[0].generated_from_record_refs)
        self.assertEqual(rows[0].feature_values["source_coverage_summary"]["record_count"], windows[0].source_record_count)
        self.assertEqual(
            rows[0].feature_values["source_coverage_summary"]["source_credibility_counts"],
            {"high": 1, "medium": 1},
        )

    def test_replay_diagnostic_records_are_excluded_from_label_windows(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv") as csv_file:
            csv_file.write(
                "ward_code,reporting_period_start,reporting_period_end,suspected_cholera_count,source_ref\n"
            )
            csv_file.write("KE-MIG-NK,2026-04-01,2026-04-07,5,weekly.csv\n")
            csv_file.flush()
            original = run_surveillance_csv_ingestion(
                file_path=csv_file.name,
                source_name="county-weekly-report",
                source_type=SurveillanceSource.SOURCE_TYPE_WEEKLY_AGGREGATE,
                correction_mode=SurveillanceIngestionRun.CORRECTION_BACKFILL,
            )
            replay_surveillance_ingestion_run(original.id, file_path=csv_file.name)

        snapshot = build_surveillance_label_dataset(start_date=date(2026, 4, 1), end_date=date(2026, 4, 7))

        window = snapshot.label_windows[0]
        self.assertEqual(window.suspected_case_count, 5)
        self.assertEqual(window.source_record_count, 1)
        self.assertEqual(window.source_coverage_summary["freshness_state_counts"], {"stale": 1})

    def test_latest_label_dataset_is_attached_to_training_dataset_lineage(self):
        self._create_population_baseline()
        with tempfile.NamedTemporaryFile("w", suffix=".csv") as csv_file:
            self._write_two_window_csv(csv_file)
            run_surveillance_csv_ingestion(
                file_path=csv_file.name,
                source_name="county-weekly-report",
                source_type=SurveillanceSource.SOURCE_TYPE_WEEKLY_AGGREGATE,
            )

        snapshot = build_surveillance_label_dataset(start_date=date(2026, 4, 1), end_date=date(2026, 4, 14))
        training_dataset = build_training_feature_dataset(month=4)

        self.assertEqual(training_dataset.surveillance_label_dataset, snapshot.feature_dataset)
        self.assertEqual(
            training_dataset.feature_dataset.lineage_metadata["surveillance_label_dataset_ref"],
            snapshot.feature_dataset.dataset_ref,
        )
        self.assertEqual(
            training_dataset.feature_dataset.lineage_metadata["surveillance_label_usage"],
            SURVEILLANCE_LABEL_TRAINING_USAGE,
        )
        self.assertEqual(
            training_dataset.feature_dataset.lineage_metadata["training_label_seeded_demo_row_count"],
            0,
        )
        self.assertEqual([row.label for row in training_dataset.rows], [1, 0])
        training_row = FeatureDatasetRow.objects.filter(dataset=training_dataset.feature_dataset).order_by("id").first()
        self.assertEqual(training_row.feature_values["training_label_source"], "surveillance_label_window")
        self.assertEqual(training_row.feature_values["training_label_dataset_ref"], snapshot.feature_dataset.dataset_ref)
        self.assertEqual(training_row.feature_values["population_proxy_source"], "population_baseline_record")
        self.assertEqual(training_row.feature_values["population_total"], 12400)
        self.assertGreater(
            training_dataset.feature_dataset.lineage_metadata["population_exposure_coverage"][
                "wards_with_population_baseline"
            ],
            0,
        )

    def test_build_surveillance_label_dataset_command_creates_snapshot(self):
        output = StringIO()
        with tempfile.NamedTemporaryFile("w", suffix=".csv") as csv_file:
            self._write_two_window_csv(csv_file)
            run_surveillance_csv_ingestion(
                file_path=csv_file.name,
                source_name="county-weekly-report",
                source_type=SurveillanceSource.SOURCE_TYPE_WEEKLY_AGGREGATE,
            )

        call_command(
            "build_surveillance_label_dataset",
            "--start-date",
            "2026-04-01",
            "--end-date",
            "2026-04-14",
            stdout=output,
        )

        self.assertIn("Surveillance label dataset built.", output.getvalue())
        self.assertEqual(FeatureDataset.objects.filter(schema_version=SURVEILLANCE_LABEL_SCHEMA_VERSION).count(), 1)
        self.assertEqual(SurveillanceLabelWindow.objects.count(), 2)
