from datetime import date, datetime, time, timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from risk.lead_time_features import LEAD_TIME_FEATURE_SCHEMA_VERSION, build_lead_time_feature_dataset
from risk.models import (
    ExposureFeatureRecord,
    FeatureDataset,
    FeatureDatasetRow,
    IngestionRun,
    PopulationBaselineRecord,
    PopulationExposureFreshness,
    PopulationExposureIngestionRun,
    PopulationExposureSource,
    PopulationExposureSourceKind,
    PopulationExposureTruth,
    RiskScore,
    SurveillanceCaseClass,
    SurveillanceDiseaseCategory,
    SurveillanceFreshnessState,
    SurveillanceIngestionRun,
    SurveillanceRecord,
    SurveillanceSource,
    SurveillanceSourceKind,
    SurveillanceTruthLevel,
    Ward,
)


class LeadTimeFeaturePhaseTwoTestCase(TestCase):
    def setUp(self):
        self.ward = Ward.objects.create(
            name="North Kamagambo",
            county="Migori",
            ward_code="KE-MIG-NK",
            current_risk_level=Ward.RISK_HIGH,
            current_risk_score=0.84,
        )
        self.peer_ward = Ward.objects.create(
            name="North Kadem",
            county="Migori",
            ward_code="KE-MIG-NKD",
            current_risk_level=Ward.RISK_MEDIUM,
            current_risk_score=0.52,
        )

    def _cutoff_for_prediction_date(self, prediction_date: date):
        return timezone.make_aware(datetime.combine(prediction_date, time.min), timezone.get_current_timezone())

    def _create_rainfall_run(self, *, observed_at, rainfall_mm, ward=None):
        ward = ward or self.ward
        return IngestionRun.objects.create(
            run_type=IngestionRun.RUN_TYPE_RAINFALL,
            status=IngestionRun.STATUS_SUCCESS,
            source_mode="test",
            source_kind=IngestionRun.SOURCE_KIND_LIVE,
            source_name="test-rainfall-feed",
            source_timestamp=observed_at,
            freshness_state=IngestionRun.FRESHNESS_FRESH,
            requested_wards=[ward.name],
            records_seen=1,
            records_loaded=1,
            completed_at=observed_at,
            results=[
                {
                    "ward_id": ward.id,
                    "ward_name": ward.name,
                    "rainfall_mm": rainfall_mm,
                    "source": "test-rainfall-feed",
                    "source_timestamp": observed_at.isoformat(),
                    "canonical_record": {"record_ref": f"climate_record:{ward.id}:{observed_at.date()}"},
                }
            ],
        )

    def _create_population_sources(self, *, recorded_at):
        source = PopulationExposureSource.objects.create(
            source_name="phase2-population-exposure",
            source_type=PopulationExposureSource.SOURCE_TYPE_POPULATION_BASELINE,
            release_version="phase2-pop-v1",
            source_ref="phase2-pop.csv",
        )
        run = PopulationExposureIngestionRun.objects.create(
            source=source,
            status=PopulationExposureIngestionRun.STATUS_SUCCESS,
            source_name=source.source_name,
            source_type=source.source_type,
            release_version=source.release_version,
            source_ref=source.source_ref,
            adapter_key="population_exposure_test",
            input_ref="tests/phase2-pop.csv",
            records_seen=2,
            records_loaded=2,
            completed_at=recorded_at,
        )
        PopulationBaselineRecord.objects.create(
            ward=self.ward,
            ingestion_run=run,
            source=source,
            recorded_at=recorded_at,
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
        ExposureFeatureRecord.objects.create(
            ward=self.ward,
            ingestion_run=run,
            source=source,
            recorded_at=recorded_at,
            exposure_type=ExposureFeatureRecord.EXPOSURE_WASH_VULNERABILITY,
            exposure_value=0.72,
            unit="index",
            truth_class=PopulationExposureTruth.DERIVED_EXPOSURE_PROXY,
            source_name=source.source_name,
            source_kind=PopulationExposureSourceKind.LIVE,
            freshness_state=PopulationExposureFreshness.FRESH,
            aggregation_method="ward_join",
            spatial_resolution="ward",
            release_version=source.release_version,
            source_ref=source.source_ref,
        )

    def _create_surveillance_record(self, *, prediction_date, reporting_end_offset_days, count_value):
        reporting_end = prediction_date + timedelta(days=reporting_end_offset_days)
        reporting_start = reporting_end - timedelta(days=6)
        source_timestamp = timezone.now()
        source = SurveillanceSource.objects.create(
            source_name=f"phase2-surveillance-{reporting_end.isoformat()}",
            source_type=SurveillanceSource.SOURCE_TYPE_WEEKLY_AGGREGATE,
            source_timestamp=source_timestamp,
            reporting_period_start=reporting_start,
            reporting_period_end=reporting_end,
            source_ref=f"phase2-{reporting_end.isoformat()}.csv",
        )
        run = SurveillanceIngestionRun.objects.create(
            source=source,
            status=SurveillanceIngestionRun.STATUS_SUCCESS,
            source_name=source.source_name,
            source_type=source.source_type,
            source_timestamp=source.source_timestamp,
            reporting_period_start=reporting_start,
            reporting_period_end=reporting_end,
            source_ref=source.source_ref,
            records_seen=1,
            records_loaded=1,
            completed_at=source_timestamp,
        )
        return SurveillanceRecord.objects.create(
            ward=self.ward,
            ingestion_run=run,
            source=source,
            disease_category=SurveillanceDiseaseCategory.CHOLERA,
            case_class=SurveillanceCaseClass.SUSPECTED,
            count_value=count_value,
            reporting_period_start=reporting_start,
            reporting_period_end=reporting_end,
            truth_level=SurveillanceTruthLevel.SUSPECTED_SURVEILLANCE,
            source_name=source.source_name,
            source_kind=SurveillanceSourceKind.LIVE,
            freshness_state=SurveillanceFreshnessState.FRESH,
            source_ref=source.source_ref,
        )

    def test_lead_time_feature_rows_have_cutoff_windows_and_no_future_surveillance_leakage(self):
        prediction_date = timezone.localdate() + timedelta(days=1)
        source_cutoff = self._cutoff_for_prediction_date(prediction_date)
        self._create_rainfall_run(observed_at=source_cutoff - timedelta(days=1), rainfall_mm=55)
        self._create_rainfall_run(observed_at=source_cutoff - timedelta(days=5), rainfall_mm=20)
        self._create_rainfall_run(observed_at=source_cutoff + timedelta(hours=2), rainfall_mm=99)
        self._create_population_sources(recorded_at=source_cutoff - timedelta(days=2))
        self._create_surveillance_record(
            prediction_date=prediction_date,
            reporting_end_offset_days=-1,
            count_value=4,
        )
        self._create_surveillance_record(
            prediction_date=prediction_date,
            reporting_end_offset_days=1,
            count_value=99,
        )
        RiskScore.objects.create(
            ward=self.peer_ward,
            score=0.62,
            risk_level=Ward.RISK_MEDIUM,
            rainfall_mm=20,
            flood_indicator=0.2,
            predicted_cases=3,
            generated_at=source_cutoff - timedelta(hours=2),
        )
        RiskScore.objects.create(
            ward=self.peer_ward,
            score=0.99,
            risk_level=Ward.RISK_HIGH,
            rainfall_mm=120,
            flood_indicator=0.8,
            predicted_cases=15,
            generated_at=source_cutoff + timedelta(hours=2),
        )

        snapshot = build_lead_time_feature_dataset([self.ward], prediction_dates=[prediction_date])

        dataset = snapshot.feature_dataset
        self.assertEqual(dataset.schema_version, LEAD_TIME_FEATURE_SCHEMA_VERSION)
        self.assertEqual(dataset.dataset_kind, FeatureDataset.KIND_INFERENCE)
        self.assertEqual(dataset.row_count, 1)
        row = FeatureDatasetRow.objects.get(dataset=dataset)
        values = row.feature_values
        self.assertEqual(values["prediction_date"], prediction_date.isoformat())
        self.assertEqual(values["source_cutoff_timestamp"], source_cutoff.isoformat())
        self.assertEqual(values["rainfall_total_3d"], 55)
        self.assertEqual(values["rainfall_total_7d"], 75)
        self.assertEqual(values["rainfall_total_14d"], 75)
        self.assertEqual(values["heavy_rain_threshold_exceedance_count_14d"], 1)
        self.assertEqual(values["days_since_heavy_rain"], 1)
        self.assertEqual(values["population_total"], 12400)
        self.assertEqual(values["wash_vulnerability"], 0.72)
        self.assertEqual(values["surveillance_total_cases_28d_before_prediction"], 4)
        self.assertEqual(values["surveillance_record_count_28d_before_prediction"], 1)
        self.assertEqual(values["upstream_or_neighboring_ward_risk_signal"], 0.62)
        self.assertFalse(values["leakage_proof"]["future_label_data_used"])
        self.assertFalse(values["leakage_proof"]["label_windows_used_as_input"])
        self.assertTrue(values["leakage_proof"]["passes_cutoff_check"])
        self.assertLess(values["leakage_proof"]["max_surveillance_reporting_period_end"], prediction_date.isoformat())
        self.assertEqual(
            dataset.lineage_metadata["coverage"]["rows_passing_leakage_check"],
            1,
        )

    def test_build_lead_time_feature_dataset_command_creates_snapshot(self):
        prediction_date = timezone.localdate() + timedelta(days=1)
        output = StringIO()

        call_command(
            "build_lead_time_feature_dataset",
            "--prediction-date",
            prediction_date.isoformat(),
            stdout=output,
        )

        self.assertIn("Lead-time feature dataset built.", output.getvalue())
        dataset = FeatureDataset.objects.get(schema_version=LEAD_TIME_FEATURE_SCHEMA_VERSION)
        self.assertEqual(dataset.lineage_metadata["prediction_dates"], [prediction_date.isoformat()])
