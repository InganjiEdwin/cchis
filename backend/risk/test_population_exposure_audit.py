import json
import tempfile
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from risk.facility_forecasting import FACILITY_FORECAST_FEATURE_SCHEMA_VERSION
from risk.models import (
    CatchmentPopulationRecord,
    ExposureFeatureRecord,
    FacilityForecast,
    FacilityForecastRun,
    HealthFacility,
    ModelRun,
    PopulationBaselineRecord,
    PopulationExposureFreshness,
    PopulationExposureIngestionRun,
    PopulationExposureSource,
    PopulationExposureSourceKind,
    PopulationExposureTruth,
    Ward,
)
from risk.population_exposure_audit import build_population_exposure_pipeline_audit
from risk.population_exposure_features import build_population_exposure_feature_dataset
from risk.population_exposure_ingestion import (
    inspect_population_exposure_csv,
    replay_population_exposure_ingestion_run,
    run_population_exposure_csv_ingestion,
)


class PopulationExposurePipelineAuditTestCase(TestCase):
    def setUp(self):
        self.ward = Ward.objects.create(
            name="North Kamagambo",
            county="Migori",
            current_risk_level=Ward.RISK_HIGH,
            current_risk_score=0.82,
        )
        self.facility = HealthFacility.objects.create(
            name="North Kamagambo Dispensary",
            facility_code="PE-AUDIT-HF-001",
            ward=self.ward,
            facility_type=HealthFacility.TYPE_DISPENSARY,
            ownership=HealthFacility.OWNERSHIP_PUBLIC,
            level=HealthFacility.LEVEL_2,
        )

    def _source_and_run(
        self,
        *,
        source_name: str = "audit-population-exposure",
        source_kind: str = PopulationExposureSourceKind.LIVE,
        truth_metadata: dict | None = None,
    ):
        source = PopulationExposureSource.objects.create(
            source_name=source_name,
            source_type=PopulationExposureSource.SOURCE_TYPE_CSV_BACKFILL,
            release_version="audit-release-v1",
            source_ref=f"{source_name}.csv",
            metadata=truth_metadata or {},
        )
        run = PopulationExposureIngestionRun.objects.create(
            source=source,
            status=PopulationExposureIngestionRun.STATUS_SUCCESS,
            source_name=source.source_name,
            source_type=source.source_type,
            release_version=source.release_version,
            source_ref=source.source_ref,
            adapter_key="population_exposure_backfill_csv",
            input_ref=f"fixtures/{source_name}.csv",
            execution_mode=PopulationExposureIngestionRun.EXECUTION_MANUAL,
            correction_mode=PopulationExposureIngestionRun.CORRECTION_ORIGINAL,
            records_seen=3,
            records_loaded=3,
            completed_at=timezone.now(),
            source_metadata=truth_metadata or {},
        )
        return source, run, source_kind

    def _create_canonical_records(self):
        source, run, source_kind = self._source_and_run()
        common = {
            "ingestion_run": run,
            "source": source,
            "recorded_at": timezone.now(),
            "source_name": source.source_name,
            "source_kind": source_kind,
            "freshness_state": PopulationExposureFreshness.FRESH,
            "release_version": source.release_version,
            "source_ref": source.source_ref,
        }
        PopulationBaselineRecord.objects.create(
            ward=self.ward,
            population_total=12400,
            population_under_five=1700,
            household_count_proxy=2800,
            truth_class=PopulationExposureTruth.DIRECT_POPULATION_BASELINE,
            **common,
        )
        ExposureFeatureRecord.objects.create(
            ward=self.ward,
            exposure_type=ExposureFeatureRecord.EXPOSURE_FLOODPLAIN_EXPOSURE,
            exposure_value=0.74,
            unit="index",
            truth_class=PopulationExposureTruth.DERIVED_EXPOSURE_PROXY,
            aggregation_method="ward_overlay_mean",
            spatial_resolution="ward",
            notes="Audit fixture exposure proxy.",
            **common,
        )
        CatchmentPopulationRecord.objects.create(
            facility=self.facility,
            catchment_population_estimate=9200,
            catchment_under_five_estimate=1300,
            assigned_ward_ids=[self.ward.id],
            assignment_method="facility_ward_assignment",
            truth_class=PopulationExposureTruth.SPATIALLY_AGGREGATED_SOURCE,
            **common,
        )

        seed_source, seed_run, _ = self._source_and_run(
            source_name="seed-scenario-population-exposure",
            source_kind=PopulationExposureSourceKind.SEEDED,
            truth_metadata={"seeded": True, "seeded_non_production": True},
        )
        PopulationBaselineRecord.objects.create(
            ward=self.ward,
            ingestion_run=seed_run,
            source=seed_source,
            recorded_at=timezone.now(),
            population_total=11111,
            truth_class=PopulationExposureTruth.SEEDED_DEMO,
            source_name=seed_source.source_name,
            source_kind=PopulationExposureSourceKind.SEEDED,
            freshness_state=PopulationExposureFreshness.FRESH,
            release_version=seed_source.release_version,
            source_ref=seed_source.source_ref,
        )

    def test_phase_5_audit_answers_verification_questions_with_lineage_and_caveats(self):
        self._create_canonical_records()
        population_exposure_dataset = build_population_exposure_feature_dataset([self.ward], month=4)
        ModelRun.objects.create(
            algorithm_name="logistic-regression-baseline",
            model_version="phase-5-audit-model",
            status=ModelRun.STATUS_SUCCESS,
            month=4,
            feature_schema_version="baseline-v1",
            feature_keys=["rainfall_mm", "population_density", "catchment_population_estimate_scaled"],
            inference_dataset_ref="phase-5-inference",
            inference_feature_dataset=population_exposure_dataset.feature_dataset,
            metadata={
                "population_exposure_dataset_ref": population_exposure_dataset.feature_dataset.dataset_ref,
                "population_exposure_truth_assumptions": population_exposure_dataset.feature_dataset.lineage_metadata.get(
                    "truth_assumptions",
                    {},
                ),
            },
        )
        forecast_run = FacilityForecastRun.objects.create(
            model_version="phase-5-facility-forecast",
            status=FacilityForecastRun.STATUS_SUCCESS,
            feature_schema_version=FACILITY_FORECAST_FEATURE_SCHEMA_VERSION,
            metadata={
                "population_exposure_dataset_ref": population_exposure_dataset.feature_dataset.dataset_ref,
            },
        )
        FacilityForecast.objects.create(
            facility=self.facility,
            forecast_run=forecast_run,
            projected_case_burden=8,
            projected_pressure_score=40,
            driving_ward_ids=[self.ward.id],
            forecast_factors=[
                {
                    "label": "Catchment population estimate",
                    "value": 9200,
                    "source": "population_exposure_snapshot",
                    "mode": "proxy_or_aggregated_context",
                    "truth_class_counts": {
                        PopulationExposureTruth.SPATIALLY_AGGREGATED_SOURCE: 1,
                    },
                    "caveat": "Catchment population estimate; do not treat as exact facility census truth.",
                }
            ],
        )

        audit = build_population_exposure_pipeline_audit()
        questions = {item["id"]: item for item in audit["verification_questions"]}

        self.assertEqual(audit["overall_status"], "pass")
        self.assertEqual(questions["truth_class_separation"]["status"], "pass")
        self.assertIn(
            PopulationExposureTruth.DERIVED_EXPOSURE_PROXY,
            questions["truth_class_separation"]["evidence"]["observed_truth_class_counts"],
        )
        self.assertEqual(questions["source_replay"]["status"], "pass")
        self.assertGreaterEqual(questions["source_replay"]["evidence"]["replayable_run_count"], 1)
        self.assertEqual(questions["source_lineage"]["status"], "pass")
        self.assertEqual(questions["source_lineage"]["evidence"]["missing_aggregation_method_count"], 0)
        self.assertEqual(questions["downstream_explainability"]["status"], "pass")
        self.assertEqual(questions["honesty_under_partial_inputs"]["status"], "pass")
        self.assertEqual(questions["ops_without_frontend"]["status"], "pass")
        self.assertEqual(questions["seeded_scenario_discipline"]["status"], "pass")
        self.assertGreater(questions["seeded_scenario_discipline"]["evidence"]["seeded_record_count"], 0)

    def test_phase_5_audit_flags_exposure_records_without_aggregation_method(self):
        source, run, source_kind = self._source_and_run(source_name="audit-missing-aggregation")
        ExposureFeatureRecord.objects.create(
            ward=self.ward,
            ingestion_run=run,
            source=source,
            recorded_at=timezone.now(),
            exposure_type=ExposureFeatureRecord.EXPOSURE_WASH_VULNERABILITY,
            exposure_value=0.56,
            unit="index",
            truth_class=PopulationExposureTruth.DERIVED_EXPOSURE_PROXY,
            source_name=source.source_name,
            source_kind=source_kind,
            freshness_state=PopulationExposureFreshness.FRESH,
            release_version=source.release_version,
            source_ref=source.source_ref,
        )

        audit = build_population_exposure_pipeline_audit()
        source_lineage = {
            item["id"]: item for item in audit["verification_questions"]
        }["source_lineage"]

        self.assertEqual(source_lineage["status"], "warning")
        self.assertIn("missing_exposure_aggregation_method", source_lineage["gaps"])
        self.assertEqual(source_lineage["evidence"]["missing_aggregation_method_count"], 1)

    def test_gridded_population_value_is_not_imported_as_density(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv") as csv_file:
            csv_file.write(
                "ward_id,population_total,gridded_population_value,truth_class,source_kind,freshness_state,source_ref\n"
            )
            csv_file.write(
                f"{self.ward.id},13200,13200.49,spatially_aggregated_source,live,fresh,worldpop-test.tif\n"
            )
            csv_file.flush()

            run = run_population_exposure_csv_ingestion(
                file_path=csv_file.name,
                source_name="WorldPop gridded population audit",
                source_type=PopulationExposureSource.SOURCE_TYPE_GRIDDED_POPULATION,
                source_timestamp=timezone.now(),
                release_version="WorldPop audit release",
                source_ref="worldpop-test.tif",
            )

        self.assertEqual(run.status, PopulationExposureIngestionRun.STATUS_SUCCESS)
        self.assertEqual(PopulationBaselineRecord.objects.filter(ingestion_run=run).count(), 1)
        self.assertEqual(ExposureFeatureRecord.objects.filter(ingestion_run=run).count(), 0)
        self.assertEqual(run.results["canonical_summary"]["exposure_feature_records"], 0)

    def test_gridded_population_value_alone_is_not_a_valid_canonical_measure(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv") as csv_file:
            csv_file.write("ward_id,gridded_population_value,source_ref\n")
            csv_file.write(f"{self.ward.id},13200.49,worldpop-test.tif\n")
            csv_file.flush()

            inspection = inspect_population_exposure_csv(
                csv_file.name,
                source_type=PopulationExposureSource.SOURCE_TYPE_GRIDDED_POPULATION,
            )

        self.assertEqual(inspection["records_seen"], 1)
        self.assertEqual(inspection["records_rejected"], 1)
        self.assertEqual(inspection["rejected_rows"][0]["reason"], "missing_required_column_group")

    def test_release_replacement_marks_old_records_and_current_snapshot_excludes_them(self):
        source, old_run, source_kind = self._source_and_run(source_name="audit-replacement-source")
        PopulationBaselineRecord.objects.create(
            ward=self.ward,
            ingestion_run=old_run,
            source=source,
            recorded_at=timezone.now(),
            population_total=9000,
            truth_class=PopulationExposureTruth.DIRECT_POPULATION_BASELINE,
            source_name=source.source_name,
            source_kind=source_kind,
            freshness_state=PopulationExposureFreshness.FRESH,
            release_version=source.release_version,
            source_ref=source.source_ref,
        )
        ExposureFeatureRecord.objects.create(
            ward=self.ward,
            ingestion_run=old_run,
            source=source,
            recorded_at=timezone.now(),
            exposure_type=ExposureFeatureRecord.EXPOSURE_FLOODPLAIN_EXPOSURE,
            exposure_value=0.25,
            unit="index",
            truth_class=PopulationExposureTruth.DERIVED_EXPOSURE_PROXY,
            source_name=source.source_name,
            source_kind=source_kind,
            freshness_state=PopulationExposureFreshness.FRESH,
            aggregation_method="ward_overlay_mean",
            spatial_resolution="ward",
            release_version=source.release_version,
            source_ref=source.source_ref,
        )

        with tempfile.NamedTemporaryFile("w", suffix=".csv") as csv_file:
            csv_file.write(
                "ward_id,population_total,floodplain_exposure,unit,aggregation_method,spatial_resolution,source_ref\n"
            )
            csv_file.write(f"{self.ward.id},13200,0.81,index,ward_overlay_mean,ward,replacement.csv\n")
            csv_file.flush()

            replacement_run = run_population_exposure_csv_ingestion(
                file_path=csv_file.name,
                source_name=source.source_name,
                source_type=source.source_type,
                release_version="audit-release-v2",
                source_ref="replacement.csv",
                correction_mode=PopulationExposureIngestionRun.CORRECTION_RELEASE_REPLACEMENT,
                replacement_reason="Corrected official release.",
                replaces_run=old_run,
            )

        self.assertEqual(replacement_run.status, PopulationExposureIngestionRun.STATUS_SUCCESS)
        self.assertEqual(
            PopulationBaselineRecord.objects.get(ingestion_run=old_run).freshness_state,
            PopulationExposureFreshness.REPLACED_BY_NEW_RELEASE,
        )
        self.assertEqual(
            ExposureFeatureRecord.objects.get(ingestion_run=old_run).freshness_state,
            PopulationExposureFreshness.REPLACED_BY_NEW_RELEASE,
        )
        snapshot = build_population_exposure_feature_dataset([self.ward], month=4)
        row = snapshot.rows_by_ward_id[self.ward.id]

        self.assertEqual(row["population_total"], 13200)
        self.assertEqual(row["floodplain_exposure"], 0.81)
        self.assertEqual(row["source_lineage"]["replaced_record_count"], 0)
        self.assertEqual(
            replacement_run.results["replacement_activation"]["replaced_records_marked"]["canonical_records_total"],
            2,
        )

    def test_partial_release_replacement_does_not_contaminate_current_snapshot(self):
        source, old_run, source_kind = self._source_and_run(source_name="audit-partial-replacement")
        old_record = PopulationBaselineRecord.objects.create(
            ward=self.ward,
            ingestion_run=old_run,
            source=source,
            recorded_at=timezone.now(),
            population_total=9000,
            truth_class=PopulationExposureTruth.DIRECT_POPULATION_BASELINE,
            source_name=source.source_name,
            source_kind=source_kind,
            freshness_state=PopulationExposureFreshness.FRESH,
            release_version=source.release_version,
            source_ref=source.source_ref,
        )

        with tempfile.NamedTemporaryFile("w", suffix=".csv") as csv_file:
            csv_file.write("ward_id,population_total,source_ref\n")
            csv_file.write(f"{self.ward.id},13200,partial-replacement.csv\n")
            csv_file.write("99999999,15000,partial-replacement.csv\n")
            csv_file.flush()

            replacement_run = run_population_exposure_csv_ingestion(
                file_path=csv_file.name,
                source_name=source.source_name,
                source_type=source.source_type,
                release_version="audit-release-v2-partial",
                source_ref="partial-replacement.csv",
                correction_mode=PopulationExposureIngestionRun.CORRECTION_RELEASE_REPLACEMENT,
                replacement_reason="Corrected official release with a bad row.",
                replaces_run=old_run,
            )

        old_record.refresh_from_db()
        candidate_record = PopulationBaselineRecord.objects.get(ingestion_run=replacement_run)
        snapshot = build_population_exposure_feature_dataset([self.ward], month=4)
        row = snapshot.rows_by_ward_id[self.ward.id]
        audit = build_population_exposure_pipeline_audit()
        source_replay = {
            item["id"]: item for item in audit["verification_questions"]
        }["source_replay"]

        self.assertEqual(replacement_run.status, PopulationExposureIngestionRun.STATUS_PARTIAL)
        self.assertFalse(replacement_run.results["replacement_activation"]["activated"])
        self.assertEqual(old_record.freshness_state, PopulationExposureFreshness.FRESH)
        self.assertEqual(candidate_record.freshness_state, PopulationExposureFreshness.REPLACEMENT_NOT_ACTIVATED)
        self.assertEqual(row["population_total"], 9000)
        self.assertEqual(row["source_lineage"]["replacement_not_activated_record_count"], 0)
        self.assertEqual(source_replay["evidence"]["unactivated_replacement_records_not_isolated_count"], 0)

    def test_replay_records_are_diagnostic_and_not_current(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv") as original_csv:
            original_csv.write("ward_id,population_total,source_ref\n")
            original_csv.write(f"{self.ward.id},11000,original-release.csv\n")
            original_csv.flush()

            original_run = run_population_exposure_csv_ingestion(
                file_path=original_csv.name,
                source_name="audit-replay-source",
                source_type=PopulationExposureSource.SOURCE_TYPE_POPULATION_BASELINE,
                release_version="audit-replay-v1",
                source_ref="original-release.csv",
            )

            with tempfile.NamedTemporaryFile("w", suffix=".csv") as replay_csv:
                replay_csv.write("ward_id,population_total,source_ref\n")
                replay_csv.write(f"{self.ward.id},99999,replay-diagnostic.csv\n")
                replay_csv.flush()

                replay_run = replay_population_exposure_ingestion_run(
                    original_run.id,
                    file_path=replay_csv.name,
                    operator_note="Replay isolation test.",
                )

        replay_record = PopulationBaselineRecord.objects.get(ingestion_run=replay_run)
        snapshot = build_population_exposure_feature_dataset([self.ward], month=4)
        row = snapshot.rows_by_ward_id[self.ward.id]
        audit = build_population_exposure_pipeline_audit()
        source_replay = {
            item["id"]: item for item in audit["verification_questions"]
        }["source_replay"]

        self.assertEqual(original_run.status, PopulationExposureIngestionRun.STATUS_SUCCESS)
        self.assertEqual(replay_run.status, PopulationExposureIngestionRun.STATUS_SUCCESS)
        self.assertEqual(replay_record.freshness_state, PopulationExposureFreshness.REPLAY_DIAGNOSTIC)
        self.assertEqual(row["population_total"], 11000)
        self.assertEqual(row["source_lineage"]["replay_diagnostic_record_count"], 0)
        self.assertEqual(source_replay["evidence"]["replay_records_not_isolated_count"], 0)

    def test_audit_management_command_can_emit_json(self):
        output = StringIO()

        call_command("audit_population_exposure_pipeline", "--format", "json", stdout=output)
        payload = json.loads(output.getvalue())

        self.assertEqual(payload["audit_name"], "population_exposure_pipeline_phase_5")
        self.assertIn("verification_questions", payload)
