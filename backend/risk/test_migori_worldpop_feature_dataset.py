import json
import tempfile
from datetime import timedelta
from pathlib import Path

from django.test import TestCase
from django.utils import timezone

from risk.migori_worldpop_feature_dataset import build_migori_worldpop_phase5_feature_dataset_summary
from risk.migori_worldpop_population_import import DEFAULT_RELEASE_VERSION, DEFAULT_SOURCE_NAME
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
from risk.population_exposure_features import build_population_exposure_feature_dataset


class MigoriWorldPopFeatureDatasetTestCase(TestCase):
    def test_phase5_summary_requires_worldpop_lineage_and_polygon_hash(self):
        polygon_sha256 = "a" * 64
        source_ref = "https://example.test/worldpop.tif"
        recorded_at = timezone.now()
        ward = Ward.objects.create(name="Alpha", county="Migori", ward_code="KE-WARD-1")
        source = PopulationExposureSource.objects.create(
            source_name=DEFAULT_SOURCE_NAME,
            source_type=PopulationExposureSource.SOURCE_TYPE_GRIDDED_POPULATION,
            source_timestamp=recorded_at,
            release_version=DEFAULT_RELEASE_VERSION,
            source_ref=source_ref,
        )
        run = PopulationExposureIngestionRun.objects.create(
            source=source,
            status=PopulationExposureIngestionRun.STATUS_SUCCESS,
            source_name=DEFAULT_SOURCE_NAME,
            source_type=PopulationExposureSource.SOURCE_TYPE_GRIDDED_POPULATION,
            source_timestamp=recorded_at,
            release_version=DEFAULT_RELEASE_VERSION,
            source_ref=source_ref,
            records_seen=1,
            records_loaded=1,
        )
        notes = f"WorldPop test; polygon_sha256={polygon_sha256}; pixel-center aggregation."
        PopulationBaselineRecord.objects.create(
            ward=ward,
            ingestion_run=run,
            source=source,
            recorded_at=recorded_at,
            population_total=1234,
            truth_class=PopulationExposureTruth.SPATIALLY_AGGREGATED_SOURCE,
            source_name=DEFAULT_SOURCE_NAME,
            source_kind=PopulationExposureSourceKind.LIVE,
            freshness_state=PopulationExposureFreshness.FRESH,
            release_version=DEFAULT_RELEASE_VERSION,
            source_ref=source_ref,
            raw_payload={"row": {"notes": notes}},
        )
        ExposureFeatureRecord.objects.create(
            ward=ward,
            ingestion_run=run,
            source=source,
            recorded_at=recorded_at,
            exposure_type=ExposureFeatureRecord.EXPOSURE_POPULATION_DENSITY,
            exposure_value=321.5,
            unit="people_per_km2",
            truth_class=PopulationExposureTruth.SPATIALLY_AGGREGATED_SOURCE,
            source_name=DEFAULT_SOURCE_NAME,
            source_kind=PopulationExposureSourceKind.LIVE,
            freshness_state=PopulationExposureFreshness.FRESH,
            aggregation_method="ward_sum_from_worldpop_100m_grid_pixel_centers",
            spatial_resolution="100m",
            release_version=DEFAULT_RELEASE_VERSION,
            source_ref=source_ref,
            notes=notes,
        )
        snapshot = build_population_exposure_feature_dataset(
            [ward],
            as_of=recorded_at + timedelta(minutes=1),
            release_version=DEFAULT_RELEASE_VERSION,
            month=5,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            phase1_summary_path = Path(tmpdir) / "phase1.json"
            reconciliation_summary_path = Path(tmpdir) / "reconciliation.json"
            csv_path = Path(tmpdir) / "phase1.csv"
            csv_path.write_text(
                "ward_code,population_total,population_density\nKE-WARD-1,1234,321.5\n",
                encoding="utf-8",
            )
            phase1_summary_path.write_text(
                json.dumps(
                    {
                        "passed": True,
                        "source_ref": source_ref,
                        "geojson_sha256": polygon_sha256,
                        "population_total_rounded": 1234,
                        "output_csv_path": str(csv_path),
                    }
                ),
                encoding="utf-8",
            )
            reconciliation_summary_path.write_text(
                json.dumps(
                    {
                        "passed": True,
                        "worldpop": {
                            "population_total": 1234,
                            "release_version": DEFAULT_RELEASE_VERSION,
                            "source_ref": source_ref,
                        },
                    }
                ),
                encoding="utf-8",
            )

            summary = build_migori_worldpop_phase5_feature_dataset_summary(
                dataset_ref=snapshot.feature_dataset.dataset_ref,
                phase1_summary_path=phase1_summary_path,
                reconciliation_summary_path=reconciliation_summary_path,
                expected_ward_count=1,
            )

        self.assertTrue(summary["passed"])
        self.assertEqual(summary["rows"]["population_total_sum"], 1234)
        self.assertEqual(summary["lineage"]["source_lineage"]["source_refs"], [source_ref])
        self.assertEqual(summary["lineage"]["source_lineage"]["polygon_sha256_values"], [polygon_sha256])
        self.assertTrue(summary["phase5_gates"]["row_lineage_source_ref_matches"])
        self.assertTrue(summary["phase5_gates"]["row_lineage_polygon_hash_matches_phase1"])
        self.assertTrue(summary["phase5_gates"]["row_population_totals_match_phase1"])
        self.assertTrue(summary["phase5_gates"]["row_population_densities_match_phase1"])
        self.assertTrue(summary["phase5_gates"]["phase1_summary_passed"])
        self.assertTrue(summary["phase5_gates"]["reconciliation_population_total_matches_dataset"])
