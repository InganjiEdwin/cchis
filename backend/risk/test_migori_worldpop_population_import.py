import json
import tempfile
from pathlib import Path

from django.test import TestCase
from django.utils import timezone

from risk.migori_worldpop_population_csv import AGGREGATION_METHOD, POPULATION_DENSITY_UNIT, SPATIAL_RESOLUTION
from risk.migori_worldpop_population_import import (
    DEFAULT_RELEASE_VERSION,
    DEFAULT_SOURCE_NAME,
    DEFAULT_SOURCE_TYPE,
    build_migori_worldpop_phase3_import_summary,
)
from risk.models import (
    ExposureFeatureRecord,
    PopulationBaselineRecord,
    PopulationExposureFreshness,
    PopulationExposureIngestionRun,
    PopulationExposureSource,
    PopulationExposureSourceKind,
    PopulationExposureTruth,
    Ward,
)


class MigoriWorldPopPopulationImportSummaryTestCase(TestCase):
    def test_import_summary_passes_expected_worldpop_records(self):
        ward = Ward.objects.create(
            name="Alpha",
            county="Migori",
            sub_county="Test",
            ward_code="KE-WARD-1",
        )
        source = PopulationExposureSource.objects.create(
            source_name=DEFAULT_SOURCE_NAME,
            source_type=DEFAULT_SOURCE_TYPE,
            source_timestamp=timezone.now(),
            release_version=DEFAULT_RELEASE_VERSION,
            source_ref="worldpop:74000",
        )
        run = PopulationExposureIngestionRun.objects.create(
            source=source,
            status=PopulationExposureIngestionRun.STATUS_SUCCESS,
            source_name=DEFAULT_SOURCE_NAME,
            source_type=DEFAULT_SOURCE_TYPE,
            source_timestamp=source.source_timestamp,
            release_version=DEFAULT_RELEASE_VERSION,
            source_ref=source.source_ref,
            adapter_key="gridded_population_csv",
            records_seen=1,
            records_loaded=1,
            records_rejected=0,
            fallback_used=False,
            results={
                "canonical_summary": {
                    "source_rows_normalized": 1,
                    "canonical_records_total": 2,
                    "population_baseline_records": 1,
                    "exposure_feature_records": 1,
                    "catchment_population_records": 0,
                }
            },
        )
        PopulationBaselineRecord.objects.create(
            ward=ward,
            ingestion_run=run,
            source=source,
            population_total=100,
            truth_class=PopulationExposureTruth.SPATIALLY_AGGREGATED_SOURCE,
            source_name=DEFAULT_SOURCE_NAME,
            source_kind=PopulationExposureSourceKind.LIVE,
            freshness_state=PopulationExposureFreshness.FRESH,
            release_version=DEFAULT_RELEASE_VERSION,
            source_ref=source.source_ref,
        )
        ExposureFeatureRecord.objects.create(
            ward=ward,
            ingestion_run=run,
            source=source,
            exposure_type=ExposureFeatureRecord.EXPOSURE_POPULATION_DENSITY,
            exposure_value=12.5,
            unit=POPULATION_DENSITY_UNIT,
            truth_class=PopulationExposureTruth.SPATIALLY_AGGREGATED_SOURCE,
            source_name=DEFAULT_SOURCE_NAME,
            source_kind=PopulationExposureSourceKind.LIVE,
            freshness_state=PopulationExposureFreshness.FRESH,
            release_version=DEFAULT_RELEASE_VERSION,
            source_ref=source.source_ref,
            aggregation_method=AGGREGATION_METHOD,
            spatial_resolution=SPATIAL_RESOLUTION,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            phase1_summary_path = Path(tmpdir) / "phase1.json"
            validation_summary_path = Path(tmpdir) / "validation.json"
            csv_path = Path(tmpdir) / "population.csv"
            csv_path.write_text(
                "ward_code,population_total,population_density\nKE-WARD-1,100,12.5\n",
                encoding="utf-8",
            )
            run.input_ref = str(csv_path)
            run.save(update_fields=["input_ref"])
            phase1_summary_path.write_text(
                json.dumps(
                    {
                        "passed": True,
                        "population_total_rounded": 100,
                        "output_csv_path": str(csv_path),
                        "output_csv_sha256": "abc123",
                        "source_ref": source.source_ref,
                        "worldpop_record": {"source_date": timezone.localtime(source.source_timestamp).date().isoformat()},
                    }
                ),
                encoding="utf-8",
            )
            validation_summary_path.write_text(json.dumps({"passed": True, "csv_sha256": "abc123"}), encoding="utf-8")

            summary = build_migori_worldpop_phase3_import_summary(
                run_id=run.id,
                phase1_summary_path=phase1_summary_path,
                validation_summary_path=validation_summary_path,
                expected_ward_count=1,
            )

        self.assertTrue(summary["passed"])
        self.assertEqual(summary["records"]["population_baseline_records"], 1)
        self.assertEqual(summary["records"]["density_exposure_records"], 1)
        self.assertEqual(summary["records"]["population_total_sum"], 100)
        self.assertTrue(summary["phase3_gates"]["imported_population_values_match_phase1_rows"])
        self.assertTrue(summary["phase3_gates"]["imported_density_values_match_phase1_rows"])
        self.assertTrue(summary["phase3_gates"]["density_units_expected"])
        self.assertTrue(summary["phase3_gates"]["density_aggregation_methods_expected"])

    def test_import_summary_fails_when_ward_values_do_not_match_phase1_csv(self):
        source = PopulationExposureSource.objects.create(
            source_name=DEFAULT_SOURCE_NAME,
            source_type=DEFAULT_SOURCE_TYPE,
            source_timestamp=timezone.now(),
            release_version=DEFAULT_RELEASE_VERSION,
            source_ref="worldpop:74000",
        )
        run = PopulationExposureIngestionRun.objects.create(
            source=source,
            status=PopulationExposureIngestionRun.STATUS_SUCCESS,
            source_name=DEFAULT_SOURCE_NAME,
            source_type=DEFAULT_SOURCE_TYPE,
            source_timestamp=source.source_timestamp,
            release_version=DEFAULT_RELEASE_VERSION,
            source_ref=source.source_ref,
            adapter_key="gridded_population_csv",
            records_seen=2,
            records_loaded=2,
            records_rejected=0,
            fallback_used=False,
            results={
                "canonical_summary": {
                    "source_rows_normalized": 2,
                    "canonical_records_total": 4,
                    "population_baseline_records": 2,
                    "exposure_feature_records": 2,
                    "catchment_population_records": 0,
                }
            },
        )
        alpha = Ward.objects.create(name="Alpha", county="Migori", sub_county="Test", ward_code="KE-WARD-1")
        beta = Ward.objects.create(name="Beta", county="Migori", sub_county="Test", ward_code="KE-WARD-2")
        common = {
            "ingestion_run": run,
            "source": source,
            "truth_class": PopulationExposureTruth.SPATIALLY_AGGREGATED_SOURCE,
            "source_name": DEFAULT_SOURCE_NAME,
            "source_kind": PopulationExposureSourceKind.LIVE,
            "freshness_state": PopulationExposureFreshness.FRESH,
            "release_version": DEFAULT_RELEASE_VERSION,
            "source_ref": source.source_ref,
        }
        PopulationBaselineRecord.objects.create(ward=alpha, population_total=200, **common)
        PopulationBaselineRecord.objects.create(ward=beta, population_total=100, **common)
        ExposureFeatureRecord.objects.create(
            ward=alpha,
            exposure_type=ExposureFeatureRecord.EXPOSURE_POPULATION_DENSITY,
            exposure_value=20.0,
            unit=POPULATION_DENSITY_UNIT,
            aggregation_method=AGGREGATION_METHOD,
            spatial_resolution=SPATIAL_RESOLUTION,
            **common,
        )
        ExposureFeatureRecord.objects.create(
            ward=beta,
            exposure_type=ExposureFeatureRecord.EXPOSURE_POPULATION_DENSITY,
            exposure_value=10.0,
            unit=POPULATION_DENSITY_UNIT,
            aggregation_method=AGGREGATION_METHOD,
            spatial_resolution=SPATIAL_RESOLUTION,
            **common,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            phase1_summary_path = Path(tmpdir) / "phase1.json"
            validation_summary_path = Path(tmpdir) / "validation.json"
            csv_path = Path(tmpdir) / "population.csv"
            csv_path.write_text(
                "ward_code,population_total,population_density\n"
                "KE-WARD-1,100,10.0\n"
                "KE-WARD-2,200,20.0\n",
                encoding="utf-8",
            )
            run.input_ref = str(csv_path)
            run.save(update_fields=["input_ref"])
            phase1_summary_path.write_text(
                json.dumps(
                    {
                        "passed": True,
                        "population_total_rounded": 300,
                        "output_csv_path": str(csv_path),
                        "output_csv_sha256": "abc123",
                        "source_ref": source.source_ref,
                        "worldpop_record": {"source_date": timezone.localtime(source.source_timestamp).date().isoformat()},
                    }
                ),
                encoding="utf-8",
            )
            validation_summary_path.write_text(json.dumps({"passed": True, "csv_sha256": "abc123"}), encoding="utf-8")

            summary = build_migori_worldpop_phase3_import_summary(
                run_id=run.id,
                phase1_summary_path=phase1_summary_path,
                validation_summary_path=validation_summary_path,
                expected_ward_count=2,
            )

        self.assertFalse(summary["passed"])
        self.assertFalse(summary["phase3_gates"]["imported_population_values_match_phase1_rows"])
        self.assertFalse(summary["phase3_gates"]["imported_density_values_match_phase1_rows"])
        self.assertEqual(
            summary["records"]["phase1_row_value_comparison"]["population_mismatch_count"],
            2,
        )
