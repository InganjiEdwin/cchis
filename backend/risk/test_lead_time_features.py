from datetime import date, datetime, time, timedelta
from io import StringIO

from django.contrib.gis.geos import Point
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from risk.lead_time_features import LEAD_TIME_FEATURE_SCHEMA_VERSION, build_lead_time_feature_dataset
from risk.models import (
    ClimateRecord,
    ClimateRecordQualityFlag,
    ClimateRecordType,
    ExposureFeatureRecord,
    FacilityCatchment,
    FacilityCatchmentMethod,
    FacilityCatchmentSourceKind,
    FacilityForecast,
    FacilityForecastRun,
    FeatureDataset,
    FeatureDatasetRow,
    HealthFacility,
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
    SurveillanceOutbreakLabel,
    SurveillanceRecord,
    SurveillanceSource,
    SurveillanceSourceKind,
    SurveillanceTruthLevel,
    Ward,
    WardGeometryDataset,
    WardGeometryDatasetVersion,
    WardSpatialRelationship,
    WardSpatialRelationshipSource,
    WardSpatialRelationshipType,
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

    def _create_forecast_run(self, *, prediction_date, lead_days, rainfall_for_lead=None):
        source_cutoff = self._cutoff_for_prediction_date(prediction_date)
        issue_time = source_cutoff - timedelta(hours=3)
        rainfall_for_lead = rainfall_for_lead or (lambda lead_day: float(lead_day))
        results = []
        for lead_day in lead_days:
            results.append(
                {
                    "ward_id": self.ward.id,
                    "ward_name": self.ward.name,
                    "rainfall_mm": rainfall_for_lead(lead_day),
                    "source": "open-meteo-forecast",
                    "source_timestamp": issue_time.isoformat(),
                    "record_type": ClimateRecordType.FORECAST,
                    "issue_time": issue_time.isoformat(),
                    "valid_date": (prediction_date + timedelta(days=lead_day - 1)).isoformat(),
                    "lead_day": lead_day,
                    "forecast_horizon_days": max(lead_days),
                    "quality_flag": ClimateRecordQualityFlag.ACCEPTED,
                    "fallback_flag": False,
                    "lineage_metadata": {"forecast_value_granularity": "single_lead_day"},
                    "source_ref": f"forecast:{self.ward.id}:{prediction_date.isoformat()}:lead:{lead_day}",
                    "canonical_record": {
                        "record_ref": f"forecast:{self.ward.id}:{prediction_date.isoformat()}:lead:{lead_day}"
                    },
                }
            )
        return IngestionRun.objects.create(
            run_type=IngestionRun.RUN_TYPE_RAINFALL,
            status=IngestionRun.STATUS_SUCCESS,
            source_mode="test",
            source_kind=IngestionRun.SOURCE_KIND_LIVE,
            source_name="open-meteo-forecast",
            source_timestamp=issue_time,
            freshness_state=IngestionRun.FRESHNESS_FRESH,
            requested_wards=[self.ward.name],
            records_seen=len(results),
            records_loaded=len(results),
            completed_at=source_cutoff - timedelta(hours=2),
            results=results,
        )

    def _create_fallback_static_run(self, *, prediction_date, rainfall_mm):
        source_cutoff = self._cutoff_for_prediction_date(prediction_date)
        completed_at = source_cutoff - timedelta(hours=4)
        return IngestionRun.objects.create(
            run_type=IngestionRun.RUN_TYPE_RAINFALL,
            status=IngestionRun.STATUS_PARTIAL,
            source_mode="test",
            source_kind=IngestionRun.SOURCE_KIND_SEEDED,
            source_name="static-default",
            freshness_state=IngestionRun.FRESHNESS_UNKNOWN,
            requested_wards=[self.ward.name],
            records_seen=1,
            records_loaded=1,
            fallback_used=True,
            completed_at=completed_at,
            results=[
                {
                    "ward_id": self.ward.id,
                    "ward_name": self.ward.name,
                    "rainfall_mm": rainfall_mm,
                    "source": "static-default",
                    "record_type": ClimateRecordType.FALLBACK_STATIC,
                    "forecast_horizon_days": 0,
                    "quality_flag": ClimateRecordQualityFlag.DEGRADED_FALLBACK,
                    "fallback_flag": True,
                    "fallback_reason": "test fallback source",
                    "source_ref": f"fallback:{self.ward.id}:{prediction_date.isoformat()}",
                    "canonical_record": {"record_ref": f"fallback:{self.ward.id}:{prediction_date.isoformat()}"},
                }
            ],
        )

    def _create_aggregate_forecast_run(self, *, prediction_date, rainfall_mm, valid_dates):
        source_cutoff = self._cutoff_for_prediction_date(prediction_date)
        issue_time = source_cutoff - timedelta(hours=3)
        return IngestionRun.objects.create(
            run_type=IngestionRun.RUN_TYPE_RAINFALL,
            status=IngestionRun.STATUS_SUCCESS,
            source_mode="test",
            source_kind=IngestionRun.SOURCE_KIND_LIVE,
            source_name="open-meteo-forecast",
            source_timestamp=issue_time,
            freshness_state=IngestionRun.FRESHNESS_FRESH,
            requested_wards=[self.ward.name],
            records_seen=1,
            records_loaded=1,
            completed_at=source_cutoff - timedelta(hours=2),
            results=[
                {
                    "ward_id": self.ward.id,
                    "ward_name": self.ward.name,
                    "rainfall_mm": rainfall_mm,
                    "source": "open-meteo-forecast",
                    "source_timestamp": issue_time.isoformat(),
                    "record_type": ClimateRecordType.FORECAST,
                    "issue_time": issue_time.isoformat(),
                    "valid_date": max(valid_dates).isoformat(),
                    "lead_day": len(valid_dates),
                    "forecast_horizon_days": len(valid_dates),
                    "quality_flag": ClimateRecordQualityFlag.ACCEPTED,
                    "fallback_flag": False,
                    "lineage_metadata": {"valid_dates": [item.isoformat() for item in valid_dates]},
                    "source_ref": f"forecast-aggregate:{self.ward.id}:{prediction_date.isoformat()}",
                    "canonical_record": {
                        "record_ref": f"forecast-aggregate:{self.ward.id}:{prediction_date.isoformat()}"
                    },
                }
            ],
        )

    def _create_future_observed_rainfall_record_loaded_before_cutoff(self, *, prediction_date, rainfall_mm):
        source_cutoff = self._cutoff_for_prediction_date(prediction_date)
        observed_at = source_cutoff + timedelta(hours=2)
        return IngestionRun.objects.create(
            run_type=IngestionRun.RUN_TYPE_RAINFALL,
            status=IngestionRun.STATUS_SUCCESS,
            source_mode="test",
            source_kind=IngestionRun.SOURCE_KIND_LIVE,
            source_name="observed-gauge-feed",
            source_timestamp=observed_at,
            freshness_state=IngestionRun.FRESHNESS_FRESH,
            requested_wards=[self.ward.name],
            records_seen=1,
            records_loaded=1,
            completed_at=source_cutoff - timedelta(hours=1),
            results=[
                {
                    "ward_id": self.ward.id,
                    "ward_name": self.ward.name,
                    "rainfall_mm": rainfall_mm,
                    "source": "observed-gauge-feed",
                    "source_timestamp": observed_at.isoformat(),
                    "record_type": ClimateRecordType.OBSERVED,
                    "observed_timestamp": observed_at.isoformat(),
                    "quality_flag": ClimateRecordQualityFlag.ACCEPTED,
                    "fallback_flag": False,
                    "source_ref": f"observed-future:{self.ward.id}:{prediction_date.isoformat()}",
                    "canonical_record": {
                        "record_ref": f"observed-future:{self.ward.id}:{prediction_date.isoformat()}"
                    },
                }
            ],
        )

    def _create_population_sources(self, *, recorded_at, include_water=False):
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
            records_seen=3 if include_water else 2,
            records_loaded=3 if include_water else 2,
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
        if include_water:
            ExposureFeatureRecord.objects.create(
                ward=self.ward,
                ingestion_run=run,
                source=source,
                recorded_at=recorded_at,
                exposure_type=ExposureFeatureRecord.EXPOSURE_WATER_BODY_PROXIMITY,
                exposure_value=0.34,
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

    def _create_surveillance_record(
        self,
        *,
        prediction_date,
        reporting_end_offset_days,
        count_value,
        ward=None,
        case_class=SurveillanceCaseClass.SUSPECTED,
        outbreak_label=SurveillanceOutbreakLabel.NONE,
    ):
        ward = ward or self.ward
        reporting_end = prediction_date + timedelta(days=reporting_end_offset_days)
        reporting_start = reporting_end - timedelta(days=6)
        source_timestamp = timezone.now()
        source = SurveillanceSource.objects.create(
            source_name=f"phase2-surveillance-{ward.id}-{reporting_end.isoformat()}",
            source_type=SurveillanceSource.SOURCE_TYPE_WEEKLY_AGGREGATE,
            source_timestamp=source_timestamp,
            reporting_period_start=reporting_start,
            reporting_period_end=reporting_end,
            source_ref=f"phase2-{ward.id}-{reporting_end.isoformat()}.csv",
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
            ward=ward,
            ingestion_run=run,
            source=source,
            disease_category=SurveillanceDiseaseCategory.CHOLERA,
            case_class=case_class,
            outbreak_label=outbreak_label,
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
        self.assertEqual(values["observed_rainfall_total_3d"], 55)
        self.assertEqual(values["observed_rainfall_total_7d"], 75)
        self.assertEqual(values["observed_rainfall_total_14d"], 75)
        self.assertEqual(values["rainfall_total_3d"], 55)
        self.assertEqual(values["rainfall_total_7d"], 75)
        self.assertEqual(values["rainfall_total_14d"], 75)
        self.assertEqual(values["heavy_rain_threshold_exceedance_count_14d"], 1)
        self.assertEqual(values["days_since_heavy_rain"], 1)
        self.assertEqual(values["forecast_coverage_days"], 0)
        self.assertEqual(values["forecast_missing_lead_days"], list(range(1, 15)))
        self.assertFalse(values["forecast_horizon_7d_sufficient"])
        self.assertFalse(values["forecast_horizon_14d_sufficient"])
        self.assertFalse(values["claimed_lead_time_climate_coverage_sufficient"])
        self.assertEqual(values["climate_coverage_status"], "insufficient_forecast_horizon")
        self.assertIn("no_forecast_records_available_before_prediction_cutoff", values["climate_coverage_caveats"])
        self.assertFalse(values["fallback_static_rainfall_used"])
        self.assertEqual(values["population_total"], 12400)
        self.assertEqual(values["wash_vulnerability"], 0.72)
        self.assertEqual(values["surveillance_total_cases_28d_before_prediction"], 4)
        self.assertEqual(values["surveillance_record_count_28d_before_prediction"], 1)
        self.assertIsNone(values["upstream_or_neighboring_ward_risk_signal"])
        self.assertEqual(values["upstream_or_neighboring_ward_signal_source"], "unavailable_no_spatial_relationships_before_cutoff")
        self.assertEqual(values["neighboring_high_risk_ward_count"], 0)
        self.assertFalse(values["leakage_proof"]["future_label_data_used"])
        self.assertFalse(values["leakage_proof"]["label_windows_used_as_input"])
        self.assertTrue(values["leakage_proof"]["passes_cutoff_check"])
        self.assertLess(values["leakage_proof"]["max_surveillance_reporting_period_end"], prediction_date.isoformat())
        self.assertEqual(
            dataset.lineage_metadata["coverage"]["rows_passing_leakage_check"],
            1,
        )
        self.assertEqual(dataset.lineage_metadata["coverage"]["rows_with_observed_rainfall_records"], 1)
        self.assertEqual(dataset.lineage_metadata["coverage"]["rows_with_forecast_rainfall_records"], 0)

    def test_phase_3_spatial_features_use_relationship_graph_and_cutoff_safe_neighbor_inputs(self):
        prediction_date = timezone.localdate() + timedelta(days=1)
        source_cutoff = self._cutoff_for_prediction_date(prediction_date)
        self.ward.centroid = Point(34.5, -1.0, srid=4326)
        self.ward.save(update_fields=["centroid"])
        self.peer_ward.centroid = Point(34.9, -1.0, srid=4326)
        self.peer_ward.save(update_fields=["centroid"])
        future_ward = Ward.objects.create(
            name="East Kadem",
            county="Migori",
            ward_code="KE-MIG-EKD",
            current_risk_level=Ward.RISK_HIGH,
            current_risk_score=0.97,
            centroid=Point(35.1, -1.0, srid=4326),
        )
        geometry_dataset = WardGeometryDataset.objects.create(
            slug="phase3-lead-time-geometry",
            name="Phase 3 Lead Time Geometry",
            coverage_scope=WardGeometryDataset.SCOPE_COUNTY,
            geometry_kind=WardGeometryDataset.KIND_WARD_BOUNDARIES,
        )
        geometry_version = WardGeometryDatasetVersion.objects.create(
            dataset=geometry_dataset,
            version_label="phase3-v1",
            source_name="test ward geometry",
            source_crs="EPSG:4326",
            is_active=True,
            activated_at=source_cutoff - timedelta(days=5),
            validation_summary={"fixture": "phase3"},
            feature_count=3,
            expected_feature_count=3,
        )
        relationship = WardSpatialRelationship.objects.create(
            source_ward=self.ward,
            target_ward=self.peer_ward,
            relationship_type=WardSpatialRelationshipType.ADJACENT,
            geometry_dataset_version=geometry_version,
            shared_boundary_length=1.2,
            centroid_distance=0.42,
            confidence=0.95,
            generation_method=WardSpatialRelationshipSource.DERIVED_GEOMETRY,
            generated_at=source_cutoff - timedelta(days=2),
            lineage_metadata={"fixture": "before_cutoff"},
        )
        WardSpatialRelationship.objects.create(
            source_ward=self.ward,
            target_ward=future_ward,
            relationship_type=WardSpatialRelationshipType.ADJACENT,
            geometry_dataset_version=geometry_version,
            shared_boundary_length=1.8,
            centroid_distance=0.2,
            confidence=0.95,
            generation_method=WardSpatialRelationshipSource.DERIVED_GEOMETRY,
            generated_at=source_cutoff + timedelta(hours=1),
            lineage_metadata={"fixture": "after_cutoff"},
        )
        RiskScore.objects.create(
            ward=self.peer_ward,
            score=0.91,
            risk_level=Ward.RISK_HIGH,
            rainfall_mm=42,
            flood_indicator=0.6,
            predicted_cases=12,
            generated_at=source_cutoff - timedelta(hours=2),
        )
        RiskScore.objects.create(
            ward=future_ward,
            score=0.98,
            risk_level=Ward.RISK_HIGH,
            rainfall_mm=90,
            flood_indicator=0.9,
            predicted_cases=20,
            generated_at=source_cutoff - timedelta(hours=2),
        )
        self._create_rainfall_run(
            ward=self.peer_ward,
            observed_at=source_cutoff - timedelta(days=1),
            rainfall_mm=40,
        )
        self._create_population_sources(recorded_at=source_cutoff - timedelta(days=2), include_water=True)
        self._create_surveillance_record(
            ward=self.peer_ward,
            prediction_date=prediction_date,
            reporting_end_offset_days=-2,
            count_value=5,
            outbreak_label=SurveillanceOutbreakLabel.ACTIVE,
        )
        self._create_surveillance_record(
            ward=self.peer_ward,
            prediction_date=prediction_date,
            reporting_end_offset_days=1,
            count_value=99,
            outbreak_label=SurveillanceOutbreakLabel.ACTIVE,
        )
        facility = HealthFacility.objects.create(
            name="Kamagambo Health Centre",
            facility_code="PHASE3-KAM-001",
            ward=self.ward,
            facility_type=HealthFacility.TYPE_HEALTH_CENTER,
            ownership=HealthFacility.OWNERSHIP_PUBLIC,
            level=HealthFacility.LEVEL_3,
            is_active=True,
            point=Point(34.51, -1.01, srid=4326),
        )
        catchment = FacilityCatchment.objects.create(
            facility=facility,
            primary_ward=self.ward,
            geometry_dataset_version=geometry_version,
            catchment_method=FacilityCatchmentMethod.SPATIAL_GRAPH_ADJACENT_WARDS,
            source_kind=FacilityCatchmentSourceKind.APPROXIMATED,
            population_estimate=16000,
            confidence=0.7,
            is_approximate=True,
            generated_at=source_cutoff - timedelta(days=1),
            lineage_metadata={"relationship_refs": [f"ward_spatial_relationship:{relationship.id}"]},
        )
        catchment.covered_wards.set([self.ward, self.peer_ward])
        forecast_run = FacilityForecastRun.objects.create(
            model_version="phase3-facility-v1",
            status=FacilityForecastRun.STATUS_SUCCESS,
            horizon_days=7,
            completed_at=source_cutoff - timedelta(hours=2),
        )
        FacilityForecast.objects.create(
            facility=facility,
            forecast_run=forecast_run,
            generated_at=source_cutoff - timedelta(hours=1),
            horizon_days=7,
            projected_case_burden=8,
            projected_pressure_score=82,
            projected_readiness_state=FacilityForecast.READINESS_CAPACITY_CONCERN,
            driving_ward_ids=[self.ward.id, self.peer_ward.id],
            model_version="phase3-facility-v1",
        )

        snapshot = build_lead_time_feature_dataset([self.ward], prediction_dates=[prediction_date])

        row = FeatureDatasetRow.objects.get(dataset=snapshot.feature_dataset)
        values = row.feature_values
        self.assertEqual(values["spatial_neighbor_ward_count"], 1)
        self.assertEqual(values["spatial_neighbor_relationship_types"], [WardSpatialRelationshipType.ADJACENT])
        self.assertEqual(values["upstream_or_neighboring_ward_count"], 1)
        self.assertEqual(values["upstream_or_neighboring_ward_risk_signal"], 0.91)
        self.assertEqual(values["neighboring_high_risk_ward_count"], 1)
        self.assertAlmostEqual(values["distance_to_nearest_high_risk_ward"], 0.42)
        self.assertEqual(values["neighboring_active_outbreak_label_count"], 1)
        self.assertEqual(values["neighboring_suspected_case_trend_14d_delta"], 5)
        self.assertEqual(values["neighboring_surveillance_record_count"], 1)
        self.assertEqual(values["neighboring_rainfall_anomaly"], 0.0)
        self.assertEqual(values["catchment_facility_readiness_pressure"], 82)
        self.assertEqual(values["catchment_facility_count"], 1)
        self.assertGreaterEqual(values["distance_to_nearest_facility"], 0)
        self.assertTrue(values["water_proximity_source_available"])
        self.assertEqual(values["water_proximity_spatial_feature_value"], 0.34)
        self.assertTrue(values["leakage_proof"]["passes_cutoff_check"])
        self.assertEqual(
            datetime.fromisoformat(values["leakage_proof"]["max_spatial_relationship_generated_at"]),
            relationship.generated_at,
        )
        self.assertLess(
            values["leakage_proof"]["max_neighbor_surveillance_reporting_period_end"],
            prediction_date.isoformat(),
        )
        self.assertIn(
            f"ward_spatial_relationship:{relationship.id}",
            values["source_lineage"]["spatial_relationships"]["relationships"]["relationship_refs"],
        )
        self.assertIn(
            f"facility_catchment:{catchment.id}",
            values["source_lineage"]["facility_catchment_pressure"]["catchment_refs"],
        )
        self.assertTrue(
            values["source_lineage"]["spatial_relationships"]["neighbor_climate"]["source_record_refs"]
        )
        coverage = snapshot.feature_dataset.lineage_metadata["coverage"]
        self.assertEqual(coverage["rows_with_spatial_neighbor_relationships"], 1)
        self.assertEqual(coverage["rows_with_neighboring_high_risk_wards"], 1)
        self.assertEqual(coverage["rows_with_neighboring_surveillance_records"], 1)
        self.assertEqual(coverage["rows_with_catchment_facility_pressure"], 1)
        self.assertEqual(coverage["rows_with_water_proximity_source"], 1)

    def test_forecast_horizon_features_mark_short_coverage_as_insufficient_for_14_day_claim(self):
        prediction_date = timezone.localdate() + timedelta(days=1)
        self._create_forecast_run(prediction_date=prediction_date, lead_days=range(1, 8))

        snapshot = build_lead_time_feature_dataset([self.ward], prediction_dates=[prediction_date])

        row = FeatureDatasetRow.objects.get(dataset=snapshot.feature_dataset)
        values = row.feature_values
        self.assertEqual(values["forecast_coverage_days"], 7)
        self.assertEqual(values["forecast_covered_lead_days"], list(range(1, 8)))
        self.assertEqual(values["forecast_missing_lead_days"], list(range(8, 15)))
        self.assertEqual(values["forecast_rainfall_total_day_1_to_7"], 28)
        self.assertEqual(values["forecast_rainfall_total_day_8_to_14"], 0)
        self.assertTrue(values["forecast_horizon_7d_sufficient"])
        self.assertFalse(values["forecast_horizon_14d_sufficient"])
        self.assertFalse(values["claimed_lead_time_climate_coverage_sufficient"])
        self.assertEqual(values["climate_coverage_status"], "insufficient_forecast_horizon")
        self.assertIn("forecast_missing_claimed_lead_days", values["climate_coverage_caveats"])

    def test_aggregate_forecast_with_pre_prediction_valid_date_stays_unsplit(self):
        prediction_date = timezone.localdate() + timedelta(days=1)
        self._create_aggregate_forecast_run(
            prediction_date=prediction_date,
            rainfall_mm=60,
            valid_dates=[
                prediction_date - timedelta(days=1),
                prediction_date,
                prediction_date + timedelta(days=1),
            ],
        )

        snapshot = build_lead_time_feature_dataset([self.ward], prediction_dates=[prediction_date])

        row = FeatureDatasetRow.objects.get(dataset=snapshot.feature_dataset)
        values = row.feature_values
        self.assertEqual(values["forecast_covered_lead_days"], [1, 2])
        self.assertEqual(values["forecast_rainfall_total_day_1_to_7"], 0)
        self.assertEqual(values["forecast_rainfall_unsplit_aggregate_mm"], 60)
        self.assertIn(
            "aggregate_includes_dates_outside_prediction_horizon",
            values["source_lineage"]["forecast_rainfall"]["aggregation_modes"],
        )
        self.assertIn(
            "forecast_rainfall_aggregate_not_split_into_7_day_buckets",
            values["climate_coverage_caveats"],
        )

    def test_forecast_fallback_and_future_observed_records_are_separated_in_feature_rows(self):
        prediction_date = timezone.localdate() + timedelta(days=1)
        self._create_forecast_run(prediction_date=prediction_date, lead_days=range(1, 15))
        self._create_fallback_static_run(prediction_date=prediction_date, rainfall_mm=999)
        self._create_future_observed_rainfall_record_loaded_before_cutoff(
            prediction_date=prediction_date,
            rainfall_mm=222,
        )

        snapshot = build_lead_time_feature_dataset([self.ward], prediction_dates=[prediction_date])

        row = FeatureDatasetRow.objects.get(dataset=snapshot.feature_dataset)
        values = row.feature_values
        self.assertEqual(values["forecast_coverage_days"], 14)
        self.assertEqual(values["forecast_missing_lead_days"], [])
        self.assertTrue(values["forecast_horizon_14d_sufficient"])
        self.assertTrue(values["claimed_lead_time_climate_coverage_sufficient"])
        self.assertEqual(values["forecast_rainfall_total_day_1_to_7"], 28)
        self.assertEqual(values["forecast_rainfall_total_day_8_to_14"], 77)
        self.assertEqual(values["forecast_rainfall_unsplit_aggregate_mm"], 0)
        self.assertTrue(values["fallback_static_rainfall_used"])
        self.assertEqual(values["fallback_static_rainfall_mm"], 999)
        self.assertEqual(values["observed_rainfall_total_14d"], 0)
        self.assertEqual(values["rainfall_total_14d"], 0)
        self.assertEqual(values["source_lineage"]["rainfall"]["records_excluded_after_cutoff"], 1)
        self.assertEqual(values["leakage_proof"]["observed_climate_records_excluded_after_cutoff"], 1)
        self.assertFalse(values["leakage_proof"]["future_observed_climate_used"])
        self.assertIn("fallback_static_rainfall_present_not_live_forecast", values["climate_coverage_caveats"])
        self.assertEqual(snapshot.feature_dataset.lineage_metadata["coverage"]["rows_with_14_day_forecast_coverage"], 1)
        self.assertEqual(
            snapshot.feature_dataset.lineage_metadata["coverage"]["rows_with_sufficient_claimed_climate_coverage"],
            1,
        )

    def test_mismatched_ward_identity_rainfall_is_not_used_as_feature_input(self):
        prediction_date = timezone.localdate() + timedelta(days=1)
        source_cutoff = self._cutoff_for_prediction_date(prediction_date)
        IngestionRun.objects.create(
            run_type=IngestionRun.RUN_TYPE_RAINFALL,
            status=IngestionRun.STATUS_SUCCESS,
            source_mode="test",
            source_kind=IngestionRun.SOURCE_KIND_LIVE,
            source_name="observed-gauge-feed",
            source_timestamp=source_cutoff - timedelta(days=1),
            freshness_state=IngestionRun.FRESHNESS_FRESH,
            requested_wards=[self.peer_ward.name],
            records_seen=1,
            records_loaded=1,
            completed_at=source_cutoff - timedelta(hours=1),
            results=[
                {
                    "ward_id": self.ward.id,
                    "ward_name": self.peer_ward.name,
                    "rainfall_mm": 88,
                    "source": "observed-gauge-feed",
                    "source_timestamp": (source_cutoff - timedelta(days=1)).isoformat(),
                    "record_type": ClimateRecordType.OBSERVED,
                    "observed_timestamp": (source_cutoff - timedelta(days=1)).isoformat(),
                    "quality_flag": ClimateRecordQualityFlag.ACCEPTED,
                    "fallback_flag": False,
                    "source_ref": "mismatched-ward-observed-rainfall",
                }
            ],
        )

        snapshot = build_lead_time_feature_dataset([self.ward], prediction_dates=[prediction_date])

        row = FeatureDatasetRow.objects.get(dataset=snapshot.feature_dataset)
        values = row.feature_values
        self.assertEqual(values["observed_rainfall_total_14d"], 0)
        self.assertEqual(values["source_lineage"]["rainfall"]["source_record_count"], 0)

    def test_persisted_mismatched_ward_identity_rainfall_is_not_used_as_feature_input(self):
        prediction_date = timezone.localdate() + timedelta(days=1)
        source_cutoff = self._cutoff_for_prediction_date(prediction_date)
        run = IngestionRun.objects.create(
            run_type=IngestionRun.RUN_TYPE_RAINFALL,
            status=IngestionRun.STATUS_SUCCESS,
            source_mode="test",
            source_kind=IngestionRun.SOURCE_KIND_LIVE,
            source_name="observed-gauge-feed",
            completed_at=source_cutoff - timedelta(hours=1),
            results=[],
        )
        ClimateRecord.objects.create(
            ward=self.ward,
            ingestion_run=run,
            record_type=ClimateRecordType.OBSERVED,
            source_provider="observed-gauge-feed",
            source_kind=IngestionRun.SOURCE_KIND_LIVE,
            source_mode="test",
            observed_timestamp=source_cutoff - timedelta(days=1),
            forecast_horizon_days=0,
            rainfall_mm=88,
            quality_flag=ClimateRecordQualityFlag.ACCEPTED,
            fallback_flag=False,
            source_run=f"ingestion_run:{run.id}",
            source_ref="persisted-mismatched-ward-observed-rainfall",
            raw_payload={"ward_name": self.peer_ward.name},
        )

        snapshot = build_lead_time_feature_dataset([self.ward], prediction_dates=[prediction_date])

        row = FeatureDatasetRow.objects.get(dataset=snapshot.feature_dataset)
        values = row.feature_values
        self.assertEqual(values["observed_rainfall_total_14d"], 0)
        self.assertEqual(values["source_lineage"]["rainfall"]["source_record_count"], 0)

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
