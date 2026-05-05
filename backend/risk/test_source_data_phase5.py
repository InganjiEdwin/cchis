from datetime import datetime, timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User

from .models import (
    FeatureDataset,
    PopulationExposureIngestionRun,
    PopulationExposureSource,
    SourceDataUploadBatch,
    SourceDataUploadEvent,
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
)


class SourceDataPhaseFiveDownstreamActionTests(APITestCase):
    def setUp(self):
        self.ward = Ward.objects.create(
            name="North Kamagambo",
            county="Migori",
            ward_code="MIG-WARD-001",
        )
        self.admin = User.objects.create_user(
            username="source-data-phase5-admin",
            password="StrongPass123!",
            role=User.ROLE_ADMIN,
        )
        self.supervisor = User.objects.create_user(
            username="source-data-phase5-supervisor",
            password="StrongPass123!",
            role=User.ROLE_SUPERVISOR,
        )
        self.analyst = User.objects.create_user(
            username="source-data-phase5-analyst",
            password="StrongPass123!",
            role=User.ROLE_ANALYST,
        )

    def create_surveillance_upload(self) -> SourceDataUploadBatch:
        source_timestamp = timezone.now() - timedelta(days=1)
        source = SurveillanceSource.objects.create(
            source_name="Migori DHIS2 weekly export",
            source_type=SurveillanceSource.SOURCE_TYPE_WEEKLY_AGGREGATE,
            source_timestamp=source_timestamp,
            reporting_period_start=source_timestamp.date() - timedelta(days=7),
            reporting_period_end=source_timestamp.date(),
        )
        run = SurveillanceIngestionRun.objects.create(
            source=source,
            status=SurveillanceIngestionRun.STATUS_SUCCESS,
            source_name=source.source_name,
            source_type=source.source_type,
            source_timestamp=source_timestamp,
            reporting_period_start=source.reporting_period_start,
            reporting_period_end=source.reporting_period_end,
            records_seen=1,
            records_loaded=1,
            completed_at=timezone.now(),
        )
        SurveillanceRecord.objects.create(
            ward=self.ward,
            ingestion_run=run,
            source=source,
            disease_category=SurveillanceDiseaseCategory.CHOLERA,
            case_class=SurveillanceCaseClass.SUSPECTED,
            outbreak_label=SurveillanceOutbreakLabel.WATCH,
            count_value=6,
            reporting_period_start=source.reporting_period_start,
            reporting_period_end=source.reporting_period_end,
            truth_level=SurveillanceTruthLevel.SUSPECTED_SURVEILLANCE,
            source_name=source.source_name,
            source_kind=SurveillanceSourceKind.LIVE,
            freshness_state=SurveillanceFreshnessState.FRESH,
        )
        return SourceDataUploadBatch.objects.create(
            feed_key="surveillance_weekly_aggregate",
            domain="health_surveillance",
            source_type=SurveillanceSource.SOURCE_TYPE_WEEKLY_AGGREGATE,
            source_name=source.source_name,
            source_timestamp=source_timestamp,
            reporting_period_start=source.reporting_period_start,
            reporting_period_end=source.reporting_period_end,
            status=SourceDataUploadBatch.STATUS_IMPORTED,
            validation_status=SourceDataUploadBatch.VALIDATION_PASSED,
            import_status=SourceDataUploadBatch.IMPORT_IMPORTED,
            row_count=1,
            accepted_count=1,
            surveillance_ingestion_run=run,
            domain_ingestion_run_type="surveillance",
            domain_ingestion_run_id=run.id,
            created_by=self.supervisor,
            confirmed_by=self.supervisor,
            confirmed_at=timezone.now(),
        )

    def create_population_upload(self) -> SourceDataUploadBatch:
        source_timestamp = timezone.now() - timedelta(days=1)
        source = PopulationExposureSource.objects.create(
            source_name="KNBS ward population baseline",
            source_type=PopulationExposureSource.SOURCE_TYPE_POPULATION_BASELINE,
            source_timestamp=source_timestamp,
            release_version="knbs-2026-v1",
        )
        run = PopulationExposureIngestionRun.objects.create(
            source=source,
            status=PopulationExposureIngestionRun.STATUS_SUCCESS,
            source_name=source.source_name,
            source_type=source.source_type,
            source_timestamp=source_timestamp,
            release_version=source.release_version,
            records_seen=1,
            records_loaded=1,
            completed_at=timezone.now(),
        )
        return SourceDataUploadBatch.objects.create(
            feed_key="population_baseline",
            domain="population",
            source_type=PopulationExposureSource.SOURCE_TYPE_POPULATION_BASELINE,
            source_name=source.source_name,
            source_timestamp=source_timestamp,
            release_version=source.release_version,
            status=SourceDataUploadBatch.STATUS_IMPORTED,
            validation_status=SourceDataUploadBatch.VALIDATION_PASSED,
            import_status=SourceDataUploadBatch.IMPORT_IMPORTED,
            row_count=1,
            accepted_count=1,
            population_exposure_ingestion_run=run,
            domain_ingestion_run_type="population_exposure",
            domain_ingestion_run_id=run.id,
            created_by=self.supervisor,
            confirmed_by=self.supervisor,
            confirmed_at=timezone.now(),
        )

    def post_downstream_action(self, batch: SourceDataUploadBatch, payload: dict, *, actor=None):
        self.client.force_authenticate(actor or self.admin)
        return self.client.post(
            reverse("source-data-upload-downstream-actions", kwargs={"public_id": batch.public_id}),
            payload,
            format="json",
        )

    def test_surveillance_import_can_regenerate_labels_with_cutoff_evidence(self):
        batch = self.create_surveillance_upload()

        response = self.post_downstream_action(
            batch,
            {
                "action_key": "regenerate_surveillance_labels",
                "as_of": timezone.now().isoformat(),
                "dataset_role": "evaluation",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["action_status"], "completed")
        evidence = response.data["evidence"]
        self.assertEqual(evidence["source_run_ids"]["surveillance_ingestion_run_id"], batch.surveillance_ingestion_run_id)
        self.assertTrue(evidence["leakage_check"]["passed"])
        self.assertFalse(evidence["leakage_check"]["label_windows_used_as_input"])
        self.assertEqual(FeatureDataset.objects.filter(schema_version="surveillance-label-v1").count(), 1)
        self.assertTrue(
            SourceDataUploadEvent.objects.filter(
                upload_batch=batch,
                event_type=SourceDataUploadEvent.EVENT_DOWNSTREAM_ACTION_REQUESTED,
            ).exists()
        )
        batch.refresh_from_db()
        self.assertEqual(batch.metadata["latest_downstream_action"]["action_key"], "regenerate_surveillance_labels")

    def test_population_import_can_request_feature_rebuild_with_leakage_proof(self):
        batch = self.create_population_upload()
        as_of = timezone.now()

        response = self.post_downstream_action(
            batch,
            {
                "action_key": "rebuild_lead_time_features",
                "as_of": as_of.isoformat(),
                "prediction_date": (timezone.localdate() + timedelta(days=1)).isoformat(),
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["action_status"], "completed")
        evidence = response.data["evidence"]
        self.assertTrue(evidence["leakage_check"]["passed"])
        self.assertEqual(evidence["leakage_check"]["row_count"], evidence["leakage_check"]["rows_passing_leakage_check"])
        self.assertEqual(evidence["source_run_ids"]["population_exposure_ingestion_run_id"], batch.population_exposure_ingestion_run_id)
        self.assertIn("as_of", evidence)
        dataset = FeatureDataset.objects.get(schema_version="lead-time-feature-v1")
        self.assertEqual(datetime.fromisoformat(dataset.lineage_metadata["source_cutoff_as_of"]), as_of)
        self.assertTrue(dataset.lineage_metadata["source_cutoff_as_of_applied"])

    def test_mutating_downstream_actions_require_explicit_cutoff_inputs(self):
        surveillance_batch = self.create_surveillance_upload()
        population_batch = self.create_population_upload()

        label_response = self.post_downstream_action(
            surveillance_batch,
            {
                "action_key": "regenerate_surveillance_labels",
                "dataset_role": "evaluation",
            },
        )
        feature_response = self.post_downstream_action(
            population_batch,
            {
                "action_key": "rebuild_lead_time_features",
                "as_of": timezone.now().isoformat(),
            },
        )

        self.assertEqual(label_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("as_of", label_response.data["detail"])
        self.assertEqual(feature_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("prediction_date", feature_response.data["detail"])

    def test_audits_are_supported_without_triggering_scoring_sms_or_promotion(self):
        batch = self.create_surveillance_upload()

        response = self.post_downstream_action(batch, {"action_key": "run_source_audits"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["action_status"], "completed")
        self.assertFalse(response.data["triggers_sms"])
        self.assertFalse(response.data["promotes_model"])
        self.assertIn("audits", response.data["evidence"])

    def test_downstream_actions_are_restricted_and_production_replacement_is_blocked(self):
        batch = self.create_surveillance_upload()

        self.client.force_authenticate(self.analyst)
        forbidden = self.client.post(
            reverse("source-data-upload-downstream-actions", kwargs={"public_id": batch.public_id}),
            {"action_key": "regenerate_surveillance_labels"},
            format="json",
        )
        self.assertEqual(forbidden.status_code, status.HTTP_403_FORBIDDEN)

        blocked = self.post_downstream_action(
            batch,
            {
                "action_key": "rebuild_lead_time_features",
                "production": True,
                "reason": "Replace production feature evidence.",
            },
            actor=self.admin,
        )
        self.assertEqual(blocked.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("maker-checker", blocked.data["detail"])
