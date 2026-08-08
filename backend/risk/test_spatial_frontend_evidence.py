from datetime import timedelta

from django.contrib.gis.geos import Point
from django.test import TestCase
from django.utils import timezone

from risk.models import (
    ExposureFeatureRecord,
    FacilityCatchment,
    FacilityCatchmentMethod,
    FacilityCatchmentSourceKind,
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
from risk.services import build_ward_intelligence_snapshot
from risk.registry_test_fixtures import seed_approved_active_registry_entry


class WardSpatialFrontendEvidenceTestCase(TestCase):
    def setUp(self):
        self.ward = Ward.objects.create(
            name="Spatial Evidence Ward",
            county="Migori",
            sub_county="Rongo",
            ward_code="SPATIAL-001",
            current_risk_level=Ward.RISK_MEDIUM,
            current_risk_score=0.62,
            centroid=Point(34.5, -1.0, srid=4326),
        )
        self.neighbor = Ward.objects.create(
            name="Spatial Neighbor Ward",
            county="Migori",
            sub_county="Rongo",
            ward_code="SPATIAL-002",
            current_risk_level=Ward.RISK_HIGH,
            current_risk_score=0.91,
            centroid=Point(34.9, -1.0, srid=4326),
        )
        self.model_run = ModelRun.objects.create(
            algorithm_name="logistic-regression-baseline",
            model_version="phase4-spatial-evidence-v1",
            status=ModelRun.STATUS_SUCCESS,
            metadata={
                "promotion_target": "live_baseline",
                "promotion_state": "promoted",
                "phase_4_promotion_gates_passed": True,
                "alert_eligible": True,
            },
            completed_at=timezone.now(),
        )
        seed_approved_active_registry_entry(
            self,
            self.model_run,
            reason="Spatial frontend evidence fixture represents a governed live run",
        )

    def _create_population_exposure(self, recorded_at):
        source = PopulationExposureSource.objects.create(
            source_name="phase4-spatial-population-exposure",
            source_type=PopulationExposureSource.SOURCE_TYPE_WATER_BODY_DISTANCE_LAYER,
            release_version="phase4-spatial-pop-v1",
            source_ref="phase4-spatial-pop.csv",
        )
        run = PopulationExposureIngestionRun.objects.create(
            source=source,
            status=PopulationExposureIngestionRun.STATUS_SUCCESS,
            source_name=source.source_name,
            source_type=source.source_type,
            release_version=source.release_version,
            source_ref=source.source_ref,
            adapter_key="population_exposure_test",
            input_ref="tests/phase4-spatial-pop.csv",
            records_seen=2,
            records_loaded=2,
            completed_at=recorded_at,
        )
        PopulationBaselineRecord.objects.create(
            ward=self.ward,
            ingestion_run=run,
            source=source,
            recorded_at=recorded_at,
            population_total=11200,
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
            exposure_type=ExposureFeatureRecord.EXPOSURE_WATER_BODY_PROXIMITY,
            exposure_value=0.41,
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

    def _create_neighbor_surveillance(self, reporting_end):
        source_timestamp = timezone.now() - timedelta(hours=1)
        reporting_start = reporting_end - timedelta(days=6)
        source = SurveillanceSource.objects.create(
            source_name="phase4-spatial-neighbor-surveillance",
            source_type=SurveillanceSource.SOURCE_TYPE_WEEKLY_AGGREGATE,
            source_timestamp=source_timestamp,
            reporting_period_start=reporting_start,
            reporting_period_end=reporting_end,
            source_ref="phase4-spatial-neighbor-surveillance.csv",
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
        SurveillanceRecord.objects.create(
            ward=self.neighbor,
            ingestion_run=run,
            source=source,
            disease_category=SurveillanceDiseaseCategory.CHOLERA,
            case_class=SurveillanceCaseClass.SUSPECTED,
            outbreak_label=SurveillanceOutbreakLabel.ACTIVE,
            count_value=6,
            reporting_period_start=reporting_start,
            reporting_period_end=reporting_end,
            truth_level=SurveillanceTruthLevel.SUSPECTED_SURVEILLANCE,
            source_name=source.source_name,
            source_kind=SurveillanceSourceKind.LIVE,
            freshness_state=SurveillanceFreshnessState.FRESH,
            source_ref=source.source_ref,
        )

    def test_ward_intelligence_exposes_phase_four_spatial_evidence(self):
        anchor = timezone.now()
        dataset = WardGeometryDataset.objects.create(
            slug="phase4-spatial-evidence",
            name="Phase 4 Spatial Evidence",
            coverage_scope=WardGeometryDataset.SCOPE_COUNTY,
            geometry_kind=WardGeometryDataset.KIND_WARD_BOUNDARIES,
        )
        version = WardGeometryDatasetVersion.objects.create(
            dataset=dataset,
            version_label="phase4-v1",
            source_name="test ward geometry",
            source_crs="EPSG:4326",
            is_active=True,
            activated_at=anchor - timedelta(days=3),
        )
        relationship = WardSpatialRelationship.objects.create(
            source_ward=self.ward,
            target_ward=self.neighbor,
            relationship_type=WardSpatialRelationshipType.ADJACENT,
            geometry_dataset_version=version,
            centroid_distance=0.42,
            confidence=0.95,
            generation_method=WardSpatialRelationshipSource.DERIVED_GEOMETRY,
            generated_at=anchor - timedelta(days=2),
        )
        approximate_relationship = WardSpatialRelationship.objects.create(
            source_ward=self.ward,
            target_ward=self.neighbor,
            relationship_type=WardSpatialRelationshipType.SAME_FACILITY_CATCHMENT,
            geometry_dataset_version=version,
            centroid_distance=0.42,
            confidence=0.7,
            generation_method=WardSpatialRelationshipSource.DERIVED_FACILITY_CATCHMENT,
            generated_at=anchor - timedelta(days=1),
            lineage_metadata={
                "approximation_notice": (
                    "Same-facility-catchment relationship is derived from FacilityCatchment approximations."
                )
            },
        )
        RiskScore.objects.create(
            ward=self.ward,
            model_run=self.model_run,
            score=0.62,
            risk_level=Ward.RISK_MEDIUM,
            rainfall_mm=44,
            flood_indicator=0.2,
            predicted_cases=5,
            model_version=self.model_run.model_version,
            generated_at=anchor - timedelta(hours=3),
        )
        neighbor_risk = RiskScore.objects.create(
            ward=self.neighbor,
            model_run=self.model_run,
            score=0.91,
            risk_level=Ward.RISK_HIGH,
            rainfall_mm=72,
            flood_indicator=0.4,
            predicted_cases=11,
            model_version=self.model_run.model_version,
            generated_at=anchor - timedelta(hours=2),
        )
        self._create_neighbor_surveillance((anchor - timedelta(days=1)).date())
        self._create_population_exposure(anchor - timedelta(days=2))
        facility = HealthFacility.objects.create(
            name="Spatial Evidence Facility",
            facility_code="SPATIAL-FAC-001",
            ward=self.ward,
            facility_type=HealthFacility.TYPE_HEALTH_CENTER,
            ownership=HealthFacility.OWNERSHIP_PUBLIC,
            level=HealthFacility.LEVEL_3,
            point=Point(34.51, -1.01, srid=4326),
        )
        catchment = FacilityCatchment.objects.create(
            facility=facility,
            primary_ward=self.ward,
            geometry_dataset_version=version,
            catchment_method=FacilityCatchmentMethod.SPATIAL_GRAPH_ADJACENT_WARDS,
            source_kind=FacilityCatchmentSourceKind.APPROXIMATED,
            population_estimate=14000,
            confidence=0.7,
            is_approximate=True,
            generated_at=anchor - timedelta(days=1),
        )
        catchment.covered_wards.set([self.ward, self.neighbor])
        forecast_run = FacilityForecastRun.objects.create(
            model_version="phase4-facility-v1",
            status=FacilityForecastRun.STATUS_SUCCESS,
            completed_at=anchor - timedelta(hours=2),
        )
        FacilityForecast.objects.create(
            facility=facility,
            forecast_run=forecast_run,
            generated_at=anchor - timedelta(hours=1),
            projected_case_burden=8,
            projected_pressure_score=82,
            projected_readiness_state=FacilityForecast.READINESS_CAPACITY_CONCERN,
            model_version="phase4-facility-v1",
        )

        payload = build_ward_intelligence_snapshot(self.ward)
        spatial = payload["spatial_evidence"]

        self.assertEqual(spatial["schema_version"], "ward-spatial-evidence-v1")
        self.assertEqual(spatial["summary"]["neighbor_count"], 1)
        self.assertEqual(spatial["summary"]["high_risk_neighbor_count"], 1)
        self.assertEqual(spatial["summary"]["active_outbreak_neighbor_count"], 1)
        self.assertEqual(spatial["summary"]["max_catchment_pressure_score"], 82)
        self.assertEqual(spatial["summary"]["water_proximity_value"], 0.41)
        self.assertEqual(spatial["neighbors"][0]["ward_id"], self.neighbor.id)
        self.assertTrue(spatial["neighbors"][0]["is_approximate_relationship"])
        self.assertEqual(
            spatial["neighbors"][0]["approximation_notice"],
            "Same-facility-catchment relationship is derived from FacilityCatchment approximations.",
        )
        self.assertEqual(spatial["neighbors"][0]["risk_score_ref"], f"risk_score:{neighbor_risk.id}")
        self.assertIn(f"ward_spatial_relationship:{relationship.id}", spatial["lineage"]["relationship_refs"])
        self.assertIn(
            f"ward_spatial_relationship:{approximate_relationship.id}",
            spatial["lineage"]["relationship_refs"],
        )
        self.assertIn(f"facility_catchment:{catchment.id}", spatial["lineage"]["facility_catchment_refs"])
        self.assertTrue(
            any("spatial relationship edges are approximate" in caveat for caveat in spatial["caveats"])
        )
        self.assertTrue(
            any("Some facility catchments are approximate" in caveat for caveat in spatial["caveats"])
        )
