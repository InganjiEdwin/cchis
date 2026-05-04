import json
from datetime import date, datetime, timedelta, timezone as dt_timezone
from io import StringIO

from django.contrib.gis.geos import GEOSGeometry, Point
from django.core.management import call_command
from django.test import TestCase

from risk.models import (
    FeatureDataset,
    FeatureDatasetRow,
    FacilityCatchment,
    FacilityCatchmentMethod,
    FacilityCatchmentSourceKind,
    FacilityForecast,
    FacilityForecastRun,
    HealthFacility,
    PopulationBaselineRecord,
    PopulationExposureFreshness,
    PopulationExposureIngestionRun,
    PopulationExposureSource,
    PopulationExposureSourceKind,
    PopulationExposureTruth,
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
    WardGeometryFeature,
    WardSpatialRelationship,
    WardSpatialRelationshipSource,
    WardSpatialRelationshipType,
)
from risk.spatial_relationships import (
    build_spatial_graph_monitoring_audit,
    build_spatial_source_quality_report,
    rebuild_facility_catchment_approximations,
    rebuild_ward_spatial_relationship_graph,
)


def _square_multipolygon(x_min, y_min, x_max, y_max):
    return GEOSGeometry(
        json.dumps(
            {
                "type": "MultiPolygon",
                "coordinates": [
                    [
                        [
                            [x_min, y_min],
                            [x_max, y_min],
                            [x_max, y_max],
                            [x_min, y_max],
                            [x_min, y_min],
                        ]
                    ]
                ],
            }
        ),
        srid=4326,
    )


class SpatialRelationshipPhaseZeroOneTestCase(TestCase):
    def setUp(self):
        self.alpha = Ward.objects.create(
            name="Spatial Alpha",
            county="Migori",
            ward_code="SP-ALPHA",
            is_active=True,
        )
        self.beta = Ward.objects.create(
            name="Spatial Beta",
            county="Migori",
            ward_code="SP-BETA",
            is_active=True,
        )
        self.gamma = Ward.objects.create(
            name="Spatial Gamma",
            county="Migori",
            ward_code="SP-GAMMA",
            is_active=True,
        )
        self.dataset = WardGeometryDataset.objects.create(
            slug="migori-ward-boundaries",
            name="Migori Ward Boundaries",
            coverage_scope=WardGeometryDataset.SCOPE_COUNTY,
            geometry_kind=WardGeometryDataset.KIND_WARD_BOUNDARIES,
            is_active=True,
        )
        self.version = WardGeometryDatasetVersion.objects.create(
            dataset=self.dataset,
            version_label="spatial-v1",
            source_name="unit-test-geometry",
            source_url="https://example.test/geometry.geojson",
            source_license="test-only",
            source_crs="EPSG:4326",
            validation_summary={
                "county": "Migori",
                "placeholder_geometry_detected": False,
            },
            feature_count=3,
            expected_feature_count=3,
            is_active=True,
        )
        self._feature(self.alpha, _square_multipolygon(0, 0, 1, 1), Point(0.5, 0.5, srid=4326))
        self._feature(self.beta, _square_multipolygon(1, 0, 2, 1), Point(1.5, 0.5, srid=4326))
        self._feature(self.gamma, _square_multipolygon(4, 0, 5, 1), Point(4.5, 0.5, srid=4326))

    def _feature(self, ward, geometry, centroid):
        ward.boundary = geometry
        ward.centroid = centroid
        ward.save(update_fields=["boundary", "centroid"])
        return WardGeometryFeature.objects.create(
            dataset_version=self.version,
            ward=ward,
            backend_public_id_snapshot=ward.public_id,
            ward_code_snapshot=ward.ward_code,
            display_name_snapshot=ward.name,
            source_name=ward.name,
            source_ward_code=ward.ward_code,
            matching_source="ward_code",
            geometry=geometry,
            centroid=centroid,
            properties={"name": ward.name, "ward_code": ward.ward_code},
        )

    def _population_source_and_run(self):
        source = PopulationExposureSource.objects.create(
            source_name="spatial-catchment-population",
            source_type=PopulationExposureSource.SOURCE_TYPE_POPULATION_BASELINE,
            release_version="spatial-catchment-v1",
            source_ref="spatial-catchment-population.csv",
        )
        run = PopulationExposureIngestionRun.objects.create(
            source=source,
            status=PopulationExposureIngestionRun.STATUS_SUCCESS,
            source_name=source.source_name,
            source_type=source.source_type,
            release_version=source.release_version,
            source_ref=source.source_ref,
            adapter_key="spatial_catchment_test",
            input_ref="fixtures/spatial-catchment-population.csv",
            execution_mode=PopulationExposureIngestionRun.EXECUTION_MANUAL,
            correction_mode=PopulationExposureIngestionRun.CORRECTION_ORIGINAL,
            records_seen=3,
            records_loaded=3,
        )
        return source, run

    def _population_baseline(self, ward, population_total):
        source, run = self._population_source_and_run()
        return PopulationBaselineRecord.objects.create(
            ward=ward,
            ingestion_run=run,
            source=source,
            population_total=population_total,
            truth_class=PopulationExposureTruth.DIRECT_POPULATION_BASELINE,
            source_name=source.source_name,
            source_kind=PopulationExposureSourceKind.LIVE,
            freshness_state=PopulationExposureFreshness.FRESH,
            release_version=source.release_version,
            source_ref=f"{source.source_ref}:{ward.ward_code}",
        )

    def _surveillance_record(self, *, ward, reporting_end, created_at=None):
        reporting_start = reporting_end - timedelta(days=6)
        source_timestamp = datetime(
            reporting_end.year,
            reporting_end.month,
            reporting_end.day,
            12,
            tzinfo=dt_timezone.utc,
        )
        source = SurveillanceSource.objects.create(
            source_name=f"phase5-spatial-surveillance-{ward.id}-{reporting_end.isoformat()}",
            source_type=SurveillanceSource.SOURCE_TYPE_WEEKLY_AGGREGATE,
            source_timestamp=source_timestamp,
            reporting_period_start=reporting_start,
            reporting_period_end=reporting_end,
            source_ref=f"phase5-spatial-surveillance-{ward.id}-{reporting_end.isoformat()}.csv",
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
        record = SurveillanceRecord.objects.create(
            ward=ward,
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
        if created_at is not None:
            SurveillanceRecord.objects.filter(pk=record.pk).update(created_at=created_at)
            record.refresh_from_db(fields=["created_at"])
        return record

    def _facility_forecast(self, *, facility, generated_at, pressure_score=82):
        forecast_run = FacilityForecastRun.objects.create(
            model_version="phase5-facility-v1",
            status=FacilityForecastRun.STATUS_SUCCESS,
            horizon_days=7,
            completed_at=generated_at,
        )
        return FacilityForecast.objects.create(
            facility=facility,
            forecast_run=forecast_run,
            generated_at=generated_at,
            horizon_days=7,
            projected_case_burden=8,
            projected_pressure_score=pressure_score,
            projected_readiness_state=FacilityForecast.READINESS_CAPACITY_CONCERN,
            driving_ward_ids=[facility.ward_id],
            model_version="phase5-facility-v1",
        )

    def test_phase_0_spatial_source_audit_documents_geometry_coordinate_and_input_gaps(self):
        HealthFacility.objects.create(
            name="Spatial Alpha Dispensary",
            facility_code="SPATIAL-HF-001",
            ward=self.alpha,
            facility_type=HealthFacility.TYPE_DISPENSARY,
            ownership=HealthFacility.OWNERSHIP_PUBLIC,
            level=HealthFacility.LEVEL_2,
            is_active=True,
        )

        report = build_spatial_source_quality_report()
        questions = {item["id"]: item for item in report["verification_questions"]}

        self.assertEqual(report["schema_version"], "spatial-source-audit-v1")
        self.assertEqual(report["overall_status"], "warning")
        self.assertEqual(questions["active_ward_geometry_coverage"]["status"], "pass")
        self.assertIn(
            "facilities_without_coordinates",
            questions["facility_coordinate_coverage"]["gaps"],
        )
        self.assertIn(
            "water_body_proximity_inputs_not_available",
            questions["water_and_floodplain_inputs"]["gaps"],
        )
        self.assertEqual(
            questions["coordinate_reference_system"]["evidence"]["distance_unit_for_phase_1"],
            "source_crs_degrees",
        )
        self.assertIn(
            "Spatial Gamma",
            questions["ward_boundary_relationship_signal"]["evidence"]["isolated_ward_names"],
        )

        stdout = StringIO()
        call_command("audit_spatial_sources", "--format", "json", stdout=stdout)
        command_report = json.loads(stdout.getvalue())
        self.assertEqual(command_report["geometry_dataset"]["version_label"], "spatial-v1")

    def test_phase_1_rebuilds_idempotent_derived_edges_and_preserves_manual_links(self):
        manual = WardSpatialRelationship.objects.create(
            source_ward=self.alpha,
            target_ward=self.gamma,
            relationship_type=WardSpatialRelationshipType.MANUAL_PUBLIC_HEALTH_LINK,
            geometry_dataset_version=self.version,
            confidence=0.65,
            generation_method=WardSpatialRelationshipSource.MANUAL_PUBLIC_HEALTH,
            lineage_metadata={"reason": "Manual outbreak-management link for test."},
        )

        summary = rebuild_ward_spatial_relationship_graph()

        self.assertEqual(summary["schema_version"], "ward-spatial-relationship-graph-v1")
        self.assertEqual(summary["created_derived_edge_count"], 2)
        self.assertEqual(summary["undirected_adjacent_pair_count"], 1)
        self.assertEqual(summary["manual_edge_count_preserved"], 1)

        derived_edges = WardSpatialRelationship.objects.filter(
            generation_method=WardSpatialRelationshipSource.DERIVED_GEOMETRY
        )
        self.assertEqual(derived_edges.count(), 2)
        self.assertEqual(
            {
                (edge.source_ward.name, edge.target_ward.name, edge.relationship_type)
                for edge in derived_edges
            },
            {
                ("Spatial Alpha", "Spatial Beta", WardSpatialRelationshipType.ADJACENT),
                ("Spatial Beta", "Spatial Alpha", WardSpatialRelationshipType.ADJACENT),
            },
        )

        alpha_to_beta = derived_edges.get(source_ward=self.alpha, target_ward=self.beta)
        self.assertGreater(alpha_to_beta.shared_boundary_length, 0)
        self.assertEqual(alpha_to_beta.geometry_dataset_version, self.version)
        self.assertEqual(alpha_to_beta.lineage_metadata["geometry_dataset"]["version_label"], "spatial-v1")
        self.assertTrue(alpha_to_beta.lineage_metadata["calculation"]["directed_edge"])

        second_summary = rebuild_ward_spatial_relationship_graph()
        self.assertEqual(second_summary["created_derived_edge_count"], 2)
        self.assertEqual(
            WardSpatialRelationship.objects.filter(
                generation_method=WardSpatialRelationshipSource.DERIVED_GEOMETRY
            ).count(),
            2,
        )
        self.assertTrue(WardSpatialRelationship.objects.filter(pk=manual.pk).exists())

        stdout = StringIO()
        call_command("build_ward_spatial_relationships", "--format", "json", stdout=stdout)
        command_summary = json.loads(stdout.getvalue())
        self.assertEqual(command_summary["created_derived_edge_count"], 2)

    def test_phase_2_builds_approximate_facility_catchment_with_population_and_edges(self):
        self._population_baseline(self.alpha, 1000)
        self._population_baseline(self.beta, 600)
        self._population_baseline(self.gamma, 900)
        facility = HealthFacility.objects.create(
            name="Spatial Alpha Catchment Facility",
            facility_code="SPATIAL-HF-CATCH-001",
            ward=self.alpha,
            facility_type=HealthFacility.TYPE_DISPENSARY,
            ownership=HealthFacility.OWNERSHIP_PUBLIC,
            level=HealthFacility.LEVEL_2,
            is_active=True,
            point=Point(0.5, 0.5, srid=4326),
        )
        rebuild_ward_spatial_relationship_graph()

        summary = rebuild_facility_catchment_approximations()

        self.assertEqual(summary["schema_version"], "facility-catchment-approximation-v1")
        self.assertEqual(summary["created_catchment_count"], 1)
        self.assertEqual(summary["created_same_facility_relationship_count"], 2)

        catchment = FacilityCatchment.objects.get(facility=facility)
        self.assertEqual(catchment.catchment_method, FacilityCatchmentMethod.SPATIAL_GRAPH_ADJACENT_WARDS)
        self.assertEqual(catchment.source_kind, FacilityCatchmentSourceKind.APPROXIMATED)
        self.assertTrue(catchment.is_approximate)
        self.assertEqual(catchment.population_estimate, 1600)
        self.assertEqual(
            list(catchment.covered_wards.order_by("name").values_list("name", flat=True)),
            ["Spatial Alpha", "Spatial Beta"],
        )
        self.assertIn("approximation_notice", catchment.lineage_metadata)
        self.assertEqual(
            catchment.lineage_metadata["population_estimate_source"]["method"],
            "population_baseline_sum",
        )

        catchment_edges = WardSpatialRelationship.objects.filter(
            relationship_type=WardSpatialRelationshipType.SAME_FACILITY_CATCHMENT,
            generation_method=WardSpatialRelationshipSource.DERIVED_FACILITY_CATCHMENT,
        )
        self.assertEqual(catchment_edges.count(), 2)
        self.assertTrue(
            catchment_edges.filter(source_ward=self.alpha, target_ward=self.beta).exists()
        )

        second_summary = rebuild_facility_catchment_approximations()
        self.assertEqual(second_summary["created_catchment_count"], 1)
        self.assertEqual(FacilityCatchment.objects.filter(facility=facility).count(), 1)
        self.assertEqual(catchment_edges.count(), 2)

        stdout = StringIO()
        call_command("build_facility_catchments", "--format", "json", stdout=stdout)
        command_summary = json.loads(stdout.getvalue())
        self.assertEqual(command_summary["created_catchment_count"], 1)

    def test_phase_5_spatial_graph_audit_passes_and_detects_lineage_or_leakage_regressions(self):
        self._population_baseline(self.alpha, 1000)
        self._population_baseline(self.beta, 600)
        self._population_baseline(self.gamma, 900)
        facility = HealthFacility.objects.create(
            name="Spatial Alpha Phase Five Facility",
            facility_code="SPATIAL-HF-PHASE5-001",
            ward=self.alpha,
            facility_type=HealthFacility.TYPE_DISPENSARY,
            ownership=HealthFacility.OWNERSHIP_PUBLIC,
            level=HealthFacility.LEVEL_2,
            is_active=True,
            point=Point(0.5, 0.5, srid=4326),
        )
        rebuild_ward_spatial_relationship_graph()
        wrong_source_relationship = WardSpatialRelationship.objects.create(
            source_ward=self.gamma,
            target_ward=self.alpha,
            relationship_type=WardSpatialRelationshipType.MANUAL_PUBLIC_HEALTH_LINK,
            geometry_dataset_version=self.version,
            confidence=0.7,
            generation_method=WardSpatialRelationshipSource.MANUAL_PUBLIC_HEALTH,
            lineage_metadata={"reason": "Manual phase 5 audit link to avoid isolated ward."},
        )
        rebuild_facility_catchment_approximations()

        relationship = WardSpatialRelationship.objects.get(
            source_ward=self.alpha,
            target_ward=self.beta,
            relationship_type=WardSpatialRelationshipType.ADJACENT,
            generation_method=WardSpatialRelationshipSource.DERIVED_GEOMETRY,
        )
        catchment = FacilityCatchment.objects.get(facility__facility_code="SPATIAL-HF-PHASE5-001")
        surveillance_record = self._surveillance_record(
            ward=self.beta,
            reporting_end=date(2030, 1, 10),
        )
        forecast = self._facility_forecast(
            facility=facility,
            generated_at=datetime(2030, 1, 14, 12, tzinfo=dt_timezone.utc),
        )
        source_cutoff = "2030-01-15T00:00:00+00:00"
        prediction_date = "2030-01-15"
        neighboring_surveillance_lineage = {
            "record_count": 1,
            "neighbor_ward_ids": [self.beta.id],
            "source_record_refs": [f"surveillance_record:{surveillance_record.id}"],
            "max_reporting_period_end": "2030-01-10",
            "max_record_created_at": "2030-01-10T12:00:00+00:00",
        }
        neighbor_climate_lineage_without_observations = {
            "neighbor_ward_count": 1,
            "neighbor_ward_ids": [self.beta.id],
            "neighbor_wards_with_observed_rainfall": 0,
            "source_record_refs": [],
            "max_source_timestamp": None,
            "source_cutoff_timestamp": source_cutoff,
        }
        catchment_lineage = {
            "catchment_count": 1,
            "facility_count": 1,
            "catchment_refs": [f"facility_catchment:{catchment.id}"],
            "facility_refs": [f"health_facility:{facility.id}"],
            "forecast_refs": [f"facility_forecast:{forecast.id}"],
            "max_catchment_generated_at": catchment.generated_at.isoformat(),
            "max_forecast_generated_at": forecast.generated_at.isoformat(),
        }
        spatial_lineage = {
            "relationships": {
                "relationship_count": 1,
                "relationship_refs": [f"ward_spatial_relationship:{relationship.id}"],
                "relationship_type_counts": {WardSpatialRelationshipType.ADJACENT: 1},
            },
            "neighbor_surveillance": neighboring_surveillance_lineage,
            "neighbor_climate": neighbor_climate_lineage_without_observations,
            "catchment_facility_pressure": catchment_lineage,
            "max_relationship_generated_at": relationship.generated_at.isoformat(),
            "max_catchment_generated_at": catchment.generated_at.isoformat(),
            "max_neighbor_surveillance_record_created_at": "2030-01-10T12:00:00+00:00",
            "max_neighbor_surveillance_reporting_period_end": "2030-01-10",
        }
        feature_values = {
            "prediction_date": prediction_date,
            "source_cutoff_timestamp": source_cutoff,
            "upstream_or_neighboring_ward_signal_source": (
                "ward_spatial_relationship_graph_latest_risk_scores_before_cutoff"
            ),
            "spatial_neighbor_ward_count": 1,
            "spatial_neighbor_relationship_types": [WardSpatialRelationshipType.ADJACENT],
            "neighboring_high_risk_ward_count": 1,
            "neighboring_active_outbreak_label_count": 1,
            "neighboring_surveillance_record_count": 1,
            "catchment_facility_readiness_pressure": 82,
            "catchment_facility_count": 1,
            "source_lineage": {
                "spatial_relationships": spatial_lineage,
                "spatial_features": spatial_lineage,
                "neighboring_surveillance": neighboring_surveillance_lineage,
                "neighboring_climate": neighbor_climate_lineage_without_observations,
                "facility_catchment_pressure": catchment_lineage,
            },
            "leakage_proof": {
                "source_cutoff_timestamp": source_cutoff,
                "max_spatial_relationship_generated_at": relationship.generated_at.isoformat(),
                "max_facility_catchment_generated_at": catchment.generated_at.isoformat(),
                "max_facility_forecast_generated_at": forecast.generated_at.isoformat(),
                "max_neighbor_surveillance_record_created_at": "2030-01-10T12:00:00+00:00",
                "max_neighbor_surveillance_reporting_period_end": "2030-01-10",
                "passes_cutoff_check": True,
            },
        }
        dataset = FeatureDataset.objects.create(
            dataset_ref="phase5-spatial-audit-ok",
            dataset_kind=FeatureDataset.KIND_INFERENCE,
            schema_version="lead-time-feature-v1",
            source_kind=FeatureDataset.SOURCE_KIND_LIVE,
            month=1,
            feature_keys=list(feature_values),
            row_count=1,
            lineage_metadata={"builder": "phase_5_spatial_graph_audit_test"},
        )
        row = FeatureDatasetRow.objects.create(
            dataset=dataset,
            ward=self.alpha,
            ward_name_snapshot=self.alpha.name,
            month=1,
            feature_values=feature_values,
            label=None,
        )

        audit = build_spatial_graph_monitoring_audit(feature_dataset_ref=dataset.dataset_ref)
        checks = {item["id"]: item for item in audit["checks"]}
        self.assertEqual(audit["schema_version"], "spatial-graph-monitoring-audit-v1")
        self.assertEqual(audit["overall_status"], "pass")
        self.assertEqual(checks["spatial_features_have_source_relationship_lineage"]["status"], "pass")
        self.assertEqual(checks["spatial_neighbor_features_cutoff_safe"]["status"], "pass")
        self.assertEqual(checks["approximate_spatial_relationships_labelled_honestly"]["status"], "pass")

        stdout = StringIO()
        call_command(
            "audit_spatial_graph",
            "--feature-dataset-ref",
            dataset.dataset_ref,
            "--format",
            "json",
            stdout=stdout,
        )
        command_audit = json.loads(stdout.getvalue())
        self.assertEqual(command_audit["overall_status"], "pass")

        wrong_row_facility = HealthFacility.objects.create(
            name="Spatial Beta Wrong Row Catchment Facility",
            facility_code="SPATIAL-HF-WRONG-ROW-001",
            ward=self.beta,
            facility_type=HealthFacility.TYPE_DISPENSARY,
            ownership=HealthFacility.OWNERSHIP_PUBLIC,
            level=HealthFacility.LEVEL_2,
            is_active=True,
            point=Point(1.55, 0.55, srid=4326),
        )
        wrong_row_catchment = FacilityCatchment.objects.create(
            facility=wrong_row_facility,
            primary_ward=self.beta,
            geometry_dataset_version=self.version,
            catchment_method=FacilityCatchmentMethod.PRIMARY_WARD_ONLY,
            source_kind=FacilityCatchmentSourceKind.APPROXIMATED,
            population_estimate=600,
            confidence=0.5,
            is_approximate=True,
            lineage_metadata={
                "schema_version": "facility-catchment-approximation-v1",
                "approximation_notice": "Regression fixture for catchment refs that do not cover the feature row.",
            },
        )
        wrong_row_catchment.covered_wards.set([self.beta])
        wrong_row_forecast = self._facility_forecast(
            facility=wrong_row_facility,
            generated_at=datetime(2030, 1, 14, 12, tzinfo=dt_timezone.utc),
        )
        forged_values = json.loads(json.dumps(feature_values))
        forged_relationship_refs = [f"ward_spatial_relationship:{wrong_source_relationship.id}"]
        forged_values["source_lineage"]["spatial_relationships"]["relationships"][
            "relationship_refs"
        ] = forged_relationship_refs
        forged_values["source_lineage"]["spatial_relationships"]["relationships"]["relationship_count"] = 1
        forged_values["source_lineage"]["spatial_features"]["relationships"][
            "relationship_refs"
        ] = forged_relationship_refs
        forged_values["source_lineage"]["spatial_features"]["relationships"]["relationship_count"] = 1
        forged_catchment_refs = [f"facility_catchment:{wrong_row_catchment.id}"]
        forged_facility_refs = [f"health_facility:{wrong_row_facility.id}"]
        forged_forecast_refs = [f"facility_forecast:{wrong_row_forecast.id}"]
        for lineage_key in ("facility_catchment_pressure",):
            forged_values["source_lineage"][lineage_key]["catchment_refs"] = forged_catchment_refs
            forged_values["source_lineage"][lineage_key]["facility_refs"] = forged_facility_refs
            forged_values["source_lineage"][lineage_key]["forecast_refs"] = forged_forecast_refs
            forged_values["source_lineage"][lineage_key][
                "max_forecast_generated_at"
            ] = wrong_row_forecast.generated_at.isoformat()
        for lineage_key in ("spatial_relationships", "spatial_features"):
            forged_values["source_lineage"][lineage_key]["catchment_facility_pressure"][
                "catchment_refs"
            ] = forged_catchment_refs
            forged_values["source_lineage"][lineage_key]["catchment_facility_pressure"][
                "facility_refs"
            ] = forged_facility_refs
            forged_values["source_lineage"][lineage_key]["catchment_facility_pressure"][
                "forecast_refs"
            ] = forged_forecast_refs
            forged_values["source_lineage"][lineage_key]["catchment_facility_pressure"][
                "max_forecast_generated_at"
            ] = wrong_row_forecast.generated_at.isoformat()
        forged_values["leakage_proof"][
            "max_facility_forecast_generated_at"
        ] = wrong_row_forecast.generated_at.isoformat()
        forged_dataset = FeatureDataset.objects.create(
            dataset_ref="phase5-spatial-audit-forged-lineage",
            dataset_kind=FeatureDataset.KIND_INFERENCE,
            schema_version="lead-time-feature-v1",
            source_kind=FeatureDataset.SOURCE_KIND_LIVE,
            month=1,
            feature_keys=list(forged_values),
            row_count=1,
            lineage_metadata={"builder": "phase_5_spatial_graph_audit_forged_lineage_test"},
        )
        FeatureDatasetRow.objects.create(
            dataset=forged_dataset,
            ward=self.alpha,
            ward_name_snapshot=self.alpha.name,
            month=1,
            feature_values=forged_values,
            label=None,
        )
        forged_audit = build_spatial_graph_monitoring_audit(feature_dataset_ref=forged_dataset.dataset_ref)
        forged_messages = [issue["message"] for issue in forged_audit["issues"]]
        self.assertEqual(forged_audit["overall_status"], "fail")
        self.assertIn(
            "spatial_features_have_source_relationship_lineage",
            {issue["check_id"] for issue in forged_audit["issues"]},
        )
        self.assertTrue(
            any("not sourced from the feature row ward" in message for message in forged_messages)
        )
        self.assertTrue(
            any("do not cover the feature row ward" in message for message in forged_messages)
        )

        stale_version = WardGeometryDatasetVersion.objects.create(
            dataset=self.dataset,
            version_label="spatial-v0-stale",
            source_name="stale unit-test-geometry",
            source_crs="EPSG:4326",
            is_active=False,
        )
        delta = Ward.objects.create(
            name="Spatial Delta",
            county="Migori",
            ward_code="SP-DELTA",
            is_active=True,
        )
        self._feature(delta, _square_multipolygon(8, 0, 9, 1), Point(8.5, 0.5, srid=4326))
        WardSpatialRelationship.objects.create(
            source_ward=delta,
            target_ward=self.alpha,
            relationship_type=WardSpatialRelationshipType.ADJACENT,
            geometry_dataset_version=stale_version,
            confidence=0.9,
            generation_method=WardSpatialRelationshipSource.DERIVED_GEOMETRY,
            lineage_metadata={"fixture": "stale_relationship_should_not_mask_isolation"},
        )
        stale_only_facility = HealthFacility.objects.create(
            name="Spatial Stale Catchment Facility",
            facility_code="SPATIAL-HF-STALE-001",
            ward=self.alpha,
            facility_type=HealthFacility.TYPE_DISPENSARY,
            ownership=HealthFacility.OWNERSHIP_PUBLIC,
            level=HealthFacility.LEVEL_2,
            is_active=True,
            point=Point(0.55, 0.55, srid=4326),
        )
        stale_catchment = FacilityCatchment.objects.create(
            facility=stale_only_facility,
            primary_ward=self.alpha,
            geometry_dataset_version=stale_version,
            catchment_method=FacilityCatchmentMethod.PRIMARY_WARD_ONLY,
            source_kind=FacilityCatchmentSourceKind.APPROXIMATED,
            population_estimate=1000,
            confidence=0.4,
            is_approximate=True,
            lineage_metadata={
                "schema_version": "facility-catchment-approximation-v1",
                "approximation_notice": "Stale catchment should not satisfy active-version audit checks.",
            },
        )
        stale_catchment.covered_wards.set([self.alpha])
        future_surveillance_record = self._surveillance_record(
            ward=self.beta,
            reporting_end=date(2030, 1, 15),
            created_at=datetime(2030, 1, 15, 1, tzinfo=dt_timezone.utc),
        )
        future_forecast = self._facility_forecast(
            facility=facility,
            generated_at=datetime(2030, 1, 15, 1, tzinfo=dt_timezone.utc),
            pressure_score=94,
        )
        bogus_verified_catchment = FacilityCatchment.objects.create(
            facility=facility,
            primary_ward=self.alpha,
            geometry_dataset_version=self.version,
            catchment_method=FacilityCatchmentMethod.EXTERNALLY_VERIFIED,
            source_kind=FacilityCatchmentSourceKind.EXTERNALLY_VERIFIED,
            population_estimate=1600,
            confidence=0.9,
            is_approximate=False,
            lineage_metadata={"fixture": "verified_claim_without_external_validation_should_fail"},
        )
        bogus_verified_catchment.covered_wards.set([self.alpha, self.beta])

        bad_values = json.loads(json.dumps(feature_values))
        bad_values["upstream_or_neighboring_ward_signal_source"] = (
            "unavailable_no_spatial_relationships_before_cutoff"
        )
        bad_values["spatial_neighbor_ward_count"] = 0
        bad_values["spatial_neighbor_relationship_types"] = []
        bad_values["neighboring_high_risk_ward_count"] = 0
        bad_values["source_lineage"]["spatial_relationships"]["relationships"]["relationship_refs"] = []
        bad_values["source_lineage"]["spatial_relationships"]["relationships"]["relationship_count"] = 0
        bad_values["source_lineage"]["facility_catchment_pressure"]["catchment_refs"] = []
        forged_safe_neighbor_climate = {
            "neighbor_ward_ids": [self.beta.id],
            "neighbor_ward_count": 1,
            "neighbor_wards_with_observed_rainfall": 1,
            "source_record_refs": ["ingestion_run_result:999999:0"],
            "max_source_timestamp": "2030-01-10T12:00:00+00:00",
            "source_cutoff_timestamp": source_cutoff,
        }
        bad_values["source_lineage"]["neighboring_climate"] = forged_safe_neighbor_climate
        bad_values["source_lineage"]["spatial_relationships"]["neighbor_climate"] = forged_safe_neighbor_climate
        forged_safe_neighbor_refs = [f"surveillance_record:{future_surveillance_record.id}"]
        bad_values["source_lineage"]["neighboring_surveillance"]["source_record_refs"] = forged_safe_neighbor_refs
        bad_values["source_lineage"]["spatial_relationships"]["neighbor_surveillance"][
            "source_record_refs"
        ] = forged_safe_neighbor_refs
        bad_values["source_lineage"]["neighboring_surveillance"]["max_reporting_period_end"] = "2030-01-10"
        bad_values["source_lineage"]["spatial_relationships"]["neighbor_surveillance"][
            "max_reporting_period_end"
        ] = "2030-01-10"
        bad_values["source_lineage"]["neighboring_surveillance"]["max_record_created_at"] = (
            "2030-01-10T12:00:00+00:00"
        )
        bad_values["source_lineage"]["spatial_relationships"]["neighbor_surveillance"][
            "max_record_created_at"
        ] = "2030-01-10T12:00:00+00:00"
        forged_safe_forecast_refs = [f"facility_forecast:{future_forecast.id}"]
        bad_values["source_lineage"]["facility_catchment_pressure"]["forecast_refs"] = forged_safe_forecast_refs
        bad_values["source_lineage"]["spatial_relationships"]["catchment_facility_pressure"][
            "forecast_refs"
        ] = forged_safe_forecast_refs
        bad_values["source_lineage"]["facility_catchment_pressure"]["max_forecast_generated_at"] = (
            "2030-01-14T12:00:00+00:00"
        )
        bad_values["source_lineage"]["spatial_relationships"]["catchment_facility_pressure"][
            "max_forecast_generated_at"
        ] = "2030-01-14T12:00:00+00:00"
        bad_values["leakage_proof"]["max_neighbor_surveillance_reporting_period_end"] = "2030-01-10"
        bad_values["leakage_proof"]["max_neighbor_surveillance_record_created_at"] = "2030-01-10T12:00:00+00:00"
        bad_values["leakage_proof"]["max_facility_forecast_generated_at"] = "2030-01-14T12:00:00+00:00"
        row.feature_values = bad_values
        row.save(update_fields=["feature_values"])

        failing_audit = build_spatial_graph_monitoring_audit(feature_dataset_ref=dataset.dataset_ref)
        failing_issue_ids = {issue["check_id"] for issue in failing_audit["issues"]}
        self.assertEqual(failing_audit["overall_status"], "fail")
        self.assertIn("active_wards_have_spatial_neighbors", failing_issue_ids)
        self.assertIn("active_facilities_have_catchments", failing_issue_ids)
        self.assertIn("spatial_features_have_source_relationship_lineage", failing_issue_ids)
        self.assertIn("spatial_neighbor_features_cutoff_safe", failing_issue_ids)
        self.assertIn("approximate_spatial_relationships_labelled_honestly", failing_issue_ids)
