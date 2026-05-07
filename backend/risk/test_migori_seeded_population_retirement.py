from django.test import TestCase
from django.utils import timezone

from risk.migori_seeded_population_retirement import retire_seeded_population_density_records
from risk.migori_worldpop_population_import import DEFAULT_RELEASE_VERSION, DEFAULT_SOURCE_NAME, DEFAULT_SOURCE_TYPE
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


class MigoriSeededPopulationRetirementTestCase(TestCase):
    def test_retirement_fails_when_replacement_density_scope_is_missing(self):
        ward = Ward.objects.create(name="Alpha", county="Migori", ward_code="KE-WARD-1")
        replacement_source = PopulationExposureSource.objects.create(
            source_name=DEFAULT_SOURCE_NAME,
            source_type=DEFAULT_SOURCE_TYPE,
            source_timestamp=timezone.now(),
            release_version=DEFAULT_RELEASE_VERSION,
        )
        replacement_run = PopulationExposureIngestionRun.objects.create(
            source=replacement_source,
            status=PopulationExposureIngestionRun.STATUS_SUCCESS,
            source_name=DEFAULT_SOURCE_NAME,
            source_type=DEFAULT_SOURCE_TYPE,
            source_timestamp=replacement_source.source_timestamp,
            release_version=DEFAULT_RELEASE_VERSION,
            records_seen=1,
            records_loaded=1,
        )
        PopulationBaselineRecord.objects.create(
            ward=ward,
            ingestion_run=replacement_run,
            source=replacement_source,
            population_total=100,
            truth_class=PopulationExposureTruth.SPATIALLY_AGGREGATED_SOURCE,
            source_name=replacement_source.source_name,
            source_kind=PopulationExposureSourceKind.LIVE,
            freshness_state=PopulationExposureFreshness.FRESH,
        )

        summary = retire_seeded_population_density_records(
            replacement_run_id=replacement_run.id,
            apply=True,
            expected_ward_count=1,
        )

        self.assertFalse(summary["passed"])
        self.assertTrue(summary["gates"]["replacement_population_ward_count_expected"])
        self.assertFalse(summary["gates"]["replacement_density_ward_count_expected"])
        self.assertFalse(summary["gates"]["replacement_population_and_density_ward_sets_match"])

    def test_retirement_marks_only_seeded_population_and_density(self):
        ward = Ward.objects.create(name="Alpha", county="Migori", ward_code="KE-WARD-1")
        other_county_ward = Ward.objects.create(name="Beta", county="Kisumu", ward_code="KE-WARD-2")
        seed_source = PopulationExposureSource.objects.create(
            source_name="seed-e2e-population-exposure-demo",
            source_type=PopulationExposureSource.SOURCE_TYPE_CSV_BACKFILL,
            source_timestamp=timezone.now(),
            release_version="seed-e2e",
        )
        seed_run = PopulationExposureIngestionRun.objects.create(
            source=seed_source,
            status=PopulationExposureIngestionRun.STATUS_SUCCESS,
            source_name=seed_source.source_name,
            source_type=seed_source.source_type,
            source_timestamp=seed_source.source_timestamp,
            release_version=seed_source.release_version,
            records_seen=2,
            records_loaded=2,
        )
        replacement_source = PopulationExposureSource.objects.create(
            source_name=DEFAULT_SOURCE_NAME,
            source_type=DEFAULT_SOURCE_TYPE,
            source_timestamp=timezone.now(),
            release_version=DEFAULT_RELEASE_VERSION,
        )
        replacement_run = PopulationExposureIngestionRun.objects.create(
            source=replacement_source,
            status=PopulationExposureIngestionRun.STATUS_SUCCESS,
            source_name=DEFAULT_SOURCE_NAME,
            source_type=DEFAULT_SOURCE_TYPE,
            source_timestamp=replacement_source.source_timestamp,
            release_version=DEFAULT_RELEASE_VERSION,
            records_seen=1,
            records_loaded=1,
        )
        PopulationBaselineRecord.objects.create(
            ward=ward,
            ingestion_run=replacement_run,
            source=replacement_source,
            population_total=100,
            truth_class=PopulationExposureTruth.SPATIALLY_AGGREGATED_SOURCE,
            source_name=replacement_source.source_name,
            source_kind=PopulationExposureSourceKind.LIVE,
            freshness_state=PopulationExposureFreshness.FRESH,
        )
        ExposureFeatureRecord.objects.create(
            ward=ward,
            ingestion_run=replacement_run,
            source=replacement_source,
            exposure_type=ExposureFeatureRecord.EXPOSURE_POPULATION_DENSITY,
            exposure_value=25.0,
            truth_class=PopulationExposureTruth.SPATIALLY_AGGREGATED_SOURCE,
            source_name=replacement_source.source_name,
            source_kind=PopulationExposureSourceKind.LIVE,
            freshness_state=PopulationExposureFreshness.FRESH,
        )
        seeded_population = PopulationBaselineRecord.objects.create(
            ward=ward,
            ingestion_run=seed_run,
            source=seed_source,
            population_total=10,
            truth_class=PopulationExposureTruth.SEEDED_DEMO,
            source_name=seed_source.source_name,
            source_kind=PopulationExposureSourceKind.SEEDED,
            freshness_state=PopulationExposureFreshness.FRESH,
        )
        out_of_scope_seeded_population = PopulationBaselineRecord.objects.create(
            ward=other_county_ward,
            ingestion_run=seed_run,
            source=seed_source,
            population_total=99,
            truth_class=PopulationExposureTruth.SEEDED_DEMO,
            source_name=seed_source.source_name,
            source_kind=PopulationExposureSourceKind.SEEDED,
            freshness_state=PopulationExposureFreshness.FRESH,
        )
        out_of_scope_seeded_density = ExposureFeatureRecord.objects.create(
            ward=other_county_ward,
            ingestion_run=seed_run,
            source=seed_source,
            exposure_type=ExposureFeatureRecord.EXPOSURE_POPULATION_DENSITY,
            exposure_value=9.9,
            truth_class=PopulationExposureTruth.SEEDED_DEMO,
            source_name=seed_source.source_name,
            source_kind=PopulationExposureSourceKind.SEEDED,
            freshness_state=PopulationExposureFreshness.FRESH,
        )
        seeded_density = ExposureFeatureRecord.objects.create(
            ward=ward,
            ingestion_run=seed_run,
            source=seed_source,
            exposure_type=ExposureFeatureRecord.EXPOSURE_POPULATION_DENSITY,
            exposure_value=1.5,
            truth_class=PopulationExposureTruth.SEEDED_DEMO,
            source_name=seed_source.source_name,
            source_kind=PopulationExposureSourceKind.SEEDED,
            freshness_state=PopulationExposureFreshness.FRESH,
        )
        seeded_wash = ExposureFeatureRecord.objects.create(
            ward=ward,
            ingestion_run=seed_run,
            source=seed_source,
            exposure_type=ExposureFeatureRecord.EXPOSURE_WASH_VULNERABILITY,
            exposure_value=0.5,
            truth_class=PopulationExposureTruth.SEEDED_DEMO,
            source_name=seed_source.source_name,
            source_kind=PopulationExposureSourceKind.SEEDED,
            freshness_state=PopulationExposureFreshness.FRESH,
        )

        dry_run = retire_seeded_population_density_records(
            replacement_run_id=replacement_run.id,
            apply=False,
            expected_ward_count=1,
        )
        self.assertFalse(dry_run["passed"])
        seeded_population.refresh_from_db()
        self.assertEqual(seeded_population.freshness_state, PopulationExposureFreshness.FRESH)

        summary = retire_seeded_population_density_records(
            replacement_run_id=replacement_run.id,
            apply=True,
            expected_ward_count=1,
        )

        self.assertTrue(summary["passed"])
        seeded_population.refresh_from_db()
        seeded_density.refresh_from_db()
        seeded_wash.refresh_from_db()
        out_of_scope_seeded_population.refresh_from_db()
        out_of_scope_seeded_density.refresh_from_db()
        self.assertEqual(seeded_population.freshness_state, PopulationExposureFreshness.REPLACED_BY_NEW_RELEASE)
        self.assertEqual(seeded_density.freshness_state, PopulationExposureFreshness.REPLACED_BY_NEW_RELEASE)
        self.assertEqual(seeded_wash.freshness_state, PopulationExposureFreshness.FRESH)
        self.assertEqual(out_of_scope_seeded_population.freshness_state, PopulationExposureFreshness.FRESH)
        self.assertEqual(out_of_scope_seeded_density.freshness_state, PopulationExposureFreshness.FRESH)
        self.assertEqual(seeded_population.raw_payload["seeded_retirement"]["replacement_run_id"], replacement_run.id)

        unrelated_source = PopulationExposureSource.objects.create(
            source_name="Other gridded population",
            source_type=DEFAULT_SOURCE_TYPE,
            source_timestamp=timezone.now(),
            release_version="other-release",
        )
        PopulationExposureIngestionRun.objects.create(
            source=unrelated_source,
            status=PopulationExposureIngestionRun.STATUS_SUCCESS,
            source_name=unrelated_source.source_name,
            source_type=unrelated_source.source_type,
            source_timestamp=unrelated_source.source_timestamp,
            release_version=unrelated_source.release_version,
        )

        rerun = retire_seeded_population_density_records(
            apply=True,
            expected_ward_count=1,
        )
        self.assertTrue(rerun["passed"])
        self.assertEqual(rerun["replacement_run"]["id"], replacement_run.id)
        self.assertEqual(rerun["records_marked"]["population_baseline_records"], 0)
        self.assertEqual(rerun["records_marked"]["density_exposure_records"], 0)
