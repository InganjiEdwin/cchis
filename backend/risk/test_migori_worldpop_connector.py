import hashlib
import json
import tempfile
from pathlib import Path

from django.test import TestCase, override_settings
from django.utils import timezone

from risk.migori_worldpop_connector import (
    DEFAULT_CONNECTOR_KEY,
    build_migori_worldpop_phase6_connector_summary,
)
from risk.migori_worldpop_population_import import DEFAULT_RELEASE_VERSION
from risk.models import (
    ExposureFeatureRecord,
    PopulationExposureFreshness,
    PopulationExposureIngestionRun,
    PopulationExposureSource,
    PopulationExposureSourceKind,
    PopulationExposureTruth,
    SourceDataConnectorRun,
    SourceDataUploadBatch,
    Ward,
)
from risk.source_data.connectors import run_source_data_connector_refresh


WORLDPOP_SOURCE_REF = (
    "https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/2026/KEN/v1/100m/constrained/"
    "ken_pop_2026_CN_100m_R2025A_v1.tif"
)


def worldpop_connector_csv() -> str:
    return "\n".join(
        [
            "ward_code,ward_name,population_total,population_density,gridded_population_value,aggregation_method,spatial_resolution,unit,truth_class,source_kind,freshness_state,source_ref,notes",
            (
                "KE-WARD-1,Alpha,24500,412.5,24500,"
                "ward_sum_from_worldpop_100m_grid_pixel_centers,100m,people_per_km2,"
                f"spatially_aggregated_source,live,fresh,{WORLDPOP_SOURCE_REF},"
                "WorldPop test; polygon_sha256=5554c913ff082f7cc2536c772a9190ca81d3b1a7370d872800ff540ce40f6997; pixel-center aggregation."
            ),
        ]
    )


class MigoriWorldPopConnectorTestCase(TestCase):
    def test_phase6_summary_verifies_connector_upload_validation(self):
        Ward.objects.create(name="Alpha", county="Migori", ward_code="KE-WARD-1")
        with tempfile.TemporaryDirectory() as upload_dir, tempfile.TemporaryDirectory() as fixture_dir:
            csv_payload = worldpop_connector_csv()
            Path(fixture_dir, "migori_worldpop_2026_population.csv").write_text(csv_payload, encoding="utf-8")
            phase1_summary_path = Path(fixture_dir, "phase1.json")
            phase1_summary_path.write_text(
                json.dumps(
                    {
                        "passed": True,
                        "output_csv_sha256": hashlib.sha256(csv_payload.encode("utf-8")).hexdigest(),
                        "source_ref": WORLDPOP_SOURCE_REF,
                        "worldpop_record": {"source_date": "2025-09-01"},
                    }
                ),
                encoding="utf-8",
            )
            with override_settings(
                SOURCE_DATA_UPLOAD_ROOT=Path(upload_dir),
                SOURCE_DATA_CONNECTOR_FIXTURE_DIR=Path(fixture_dir),
                SOURCE_DATA_WORLDPOP_KNBS_SOURCE_URL=WORLDPOP_SOURCE_REF,
                SOURCE_DATA_WORLDPOP_KNBS_RELEASE_VERSION=DEFAULT_RELEASE_VERSION,
                SOURCE_DATA_MAX_UPLOAD_ROWS=20,
            ):
                run = run_source_data_connector_refresh(
                    connector_key=DEFAULT_CONNECTOR_KEY,
                    options={"source_timestamp": "2025-09-01T00:00:00Z"},
                )
                source = PopulationExposureSource.objects.create(
                    source_name="WorldPop R2025A constrained 100m Migori ward aggregate",
                    source_type=PopulationExposureSource.SOURCE_TYPE_GRIDDED_POPULATION,
                    source_timestamp=timezone.now(),
                    release_version=DEFAULT_RELEASE_VERSION,
                    source_ref=WORLDPOP_SOURCE_REF,
                )
                ingestion_run = PopulationExposureIngestionRun.objects.create(
                    source=source,
                    status=PopulationExposureIngestionRun.STATUS_SUCCESS,
                    source_name=source.source_name,
                    source_type=PopulationExposureSource.SOURCE_TYPE_GRIDDED_POPULATION,
                    source_timestamp=timezone.now(),
                    release_version=DEFAULT_RELEASE_VERSION,
                    source_ref=WORLDPOP_SOURCE_REF,
                )
                ExposureFeatureRecord.objects.create(
                    ward=Ward.objects.get(ward_code="KE-WARD-1"),
                    ingestion_run=ingestion_run,
                    source=source,
                    exposure_type=ExposureFeatureRecord.EXPOSURE_POPULATION_DENSITY,
                    exposure_value=412.5,
                    truth_class=PopulationExposureTruth.SPATIALLY_AGGREGATED_SOURCE,
                    source_name=source.source_name,
                    source_kind=PopulationExposureSourceKind.LIVE,
                    freshness_state=PopulationExposureFreshness.FRESH,
                    release_version=DEFAULT_RELEASE_VERSION,
                    source_ref=WORLDPOP_SOURCE_REF,
                )
                summary = build_migori_worldpop_phase6_connector_summary(
                    run_id=run.id,
                    phase1_summary_path=phase1_summary_path,
                    expected_ward_count=1,
                )

        self.assertTrue(summary["passed"])
        self.assertEqual(summary["connector_run"]["status"], SourceDataConnectorRun.STATUS_SUCCESS)
        self.assertEqual(summary["connector_run"]["target_feed_key"], "gridded_population")
        self.assertEqual(summary["upload_batch"]["validation_status"], SourceDataUploadBatch.VALIDATION_PASSED)
        self.assertTrue(summary["phase6_gates"]["phase1_summary_passed"])
        self.assertTrue(summary["phase6_gates"]["upload_source_timestamp_matches_phase1"])
        self.assertTrue(summary["artifact"]["content_matches_phase1"])
