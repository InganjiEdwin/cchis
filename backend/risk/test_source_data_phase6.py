from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import StepUpGrant, User

from .models import (
    FacilityForecastRun,
    FacilityReadinessFreshness,
    FacilityReadinessIngestionRun,
    FacilityReadinessSnapshot,
    FacilityReadinessState,
    HealthFacility,
    SourceDataUploadBatch,
    SourceDataValidationIssue,
    Ward,
)
from .services import build_facility_intelligence_snapshot
from .test_step_up_utils import force_authenticate_with_step_up


class SourceDataPhaseSixFacilityReadinessSnapshotTests(APITestCase):
    def setUp(self):
        self.upload_root = TemporaryDirectory()
        self.addCleanup(self.upload_root.cleanup)
        self.settings_override = override_settings(
            SOURCE_DATA_UPLOAD_ROOT=Path(self.upload_root.name),
            SOURCE_DATA_MAX_UPLOAD_SIZE_BYTES=1024 * 1024,
            SOURCE_DATA_MAX_UPLOAD_ROWS=20,
            SOURCE_DATA_ASYNC_IMPORT_SIZE_BYTES=1024 * 1024,
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

        self.ward = Ward.objects.create(
            name="North Kamagambo",
            county="Migori",
            ward_code="MIG-WARD-001",
        )
        self.facility = HealthFacility.objects.create(
            name="Got Kachola Dispensary",
            facility_code="FAC-MIG-001",
            ward=self.ward,
            facility_type=HealthFacility.TYPE_DISPENSARY,
            level=HealthFacility.LEVEL_2,
        )
        self.admin = User.objects.create_user(
            username="source-data-phase6-admin",
            password="StrongPass123!",
            role=User.ROLE_ADMIN,
        )
        self.supervisor = User.objects.create_user(
            username="source-data-phase6-supervisor",
            password="StrongPass123!",
            role=User.ROLE_SUPERVISOR,
        )
        self.analyst = User.objects.create_user(
            username="source-data-phase6-analyst",
            password="StrongPass123!",
            role=User.ROLE_ANALYST,
        )

    def readiness_csv(
        self,
        *,
        facility_code: str = "FAC-MIG-001",
        ward_code: str = "MIG-WARD-001",
        reported_at=None,
        ors: int = 120,
        iv: int = 36,
        zinc: int = 80,
        chlorine: int = 55,
        beds: int = 6,
        staff: int = 6,
        referral: str = "true",
        disruption: str = "false",
        notes: str = "",
        source_ref: str = "readiness-checklist:row-1",
        extra_rows: list[str] | None = None,
    ) -> str:
        reported_at = reported_at or timezone.now()
        header = (
            "facility_code,facility_name,ward_code,reported_at,ors_sachets_available,iv_fluids_available,"
            "zinc_available,chlorine_available,beds_available,staff_on_duty,referral_available,"
            "stockout_notes,service_disruption,source_kind,source_ref"
        )
        row = (
            f"{facility_code},Got Kachola Dispensary,{ward_code},{reported_at.isoformat()},"
            f"{ors},{iv},{zinc},{chlorine},{beds},{staff},{referral},{notes},{disruption},facility_report,{source_ref}"
        )
        return "\n".join([header, row, *(extra_rows or [])])

    def readiness_payload(self, csv_text: str, *, filename: str = "readiness.csv"):
        now = timezone.now()
        return {
            "feed_key": "facility_readiness_snapshot",
            "source_name": "Migori facility readiness checklist",
            "source_timestamp": now.isoformat(),
            "reporting_period_start": (now.date() - timedelta(days=7)).isoformat(),
            "reporting_period_end": now.date().isoformat(),
            "file": SimpleUploadedFile(filename, csv_text.encode("utf-8"), content_type="text/csv"),
        }

    def create_upload(self, csv_text: str):
        force_authenticate_with_step_up(self.client, self.supervisor, StepUpGrant.PURPOSE_SOURCE_DATA)
        return self.client.post(
            reverse("source-data-upload-list-create"),
            self.readiness_payload(csv_text),
            format="multipart",
        )

    def validate_upload(self, public_id: str):
        force_authenticate_with_step_up(self.client, self.supervisor, StepUpGrant.PURPOSE_SOURCE_DATA)
        return self.client.post(
            reverse("source-data-upload-validate", kwargs={"public_id": public_id}),
            {},
            format="json",
        )

    def confirm_upload(self, public_id: str):
        force_authenticate_with_step_up(self.client, self.supervisor, StepUpGrant.PURPOSE_SOURCE_DATA)
        return self.client.post(
            reverse("source-data-upload-confirm", kwargs={"public_id": public_id}),
            {},
            format="json",
        )

    def test_readiness_snapshot_upload_imports_and_updates_source_backed_facility_intelligence(self):
        upload_response = self.create_upload(self.readiness_csv())
        validate_response = self.validate_upload(upload_response.data["public_id"])
        confirm_response = self.confirm_upload(upload_response.data["public_id"])

        self.assertEqual(upload_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(validate_response.status_code, status.HTTP_200_OK)
        self.assertEqual(validate_response.data["status"], SourceDataUploadBatch.STATUS_READY_FOR_CONFIRMATION)
        self.assertEqual(validate_response.data["metadata"]["validation_summary"]["readiness_summary"]["facilities_reported"], 1)
        self.assertEqual(confirm_response.status_code, status.HTTP_200_OK)
        self.assertEqual(confirm_response.data["status"], SourceDataUploadBatch.STATUS_IMPORTED)
        self.assertEqual(confirm_response.data["domain_ingestion_run_type"], "facility_readiness")
        self.assertIsNotNone(confirm_response.data["facility_readiness_ingestion_run_id"])
        self.assertEqual(FacilityReadinessIngestionRun.objects.count(), 1)
        self.assertEqual(FacilityReadinessSnapshot.objects.count(), 1)

        snapshot = FacilityReadinessSnapshot.objects.get()
        self.assertEqual(snapshot.facility, self.facility)
        self.assertEqual(snapshot.readiness_state, FacilityReadinessState.READY)
        self.assertEqual(snapshot.freshness_state, FacilityReadinessFreshness.FRESH)

        intelligence = build_facility_intelligence_snapshot(self.facility)
        self.assertEqual(intelligence["readiness"]["backing_source"], "source_readiness_snapshot")
        self.assertEqual(intelligence["readiness"]["dashboard_truth_state"], "source_backed")

        self.client.force_authenticate(self.analyst)
        overview_response = self.client.get(reverse("source-data-overview"))
        feed_statuses = {item["feed_key"]: item for item in overview_response.data["feed_statuses"]}
        self.assertEqual(feed_statuses["facility_readiness_snapshot"]["truth_state"], "csv_backed")
        self.assertEqual(feed_statuses["facility_readiness_snapshot"]["source_path"], "csv_upload")

    def test_readiness_snapshot_import_flag_blocks_upload_path(self):
        with self.settings(FACILITY_READINESS_SNAPSHOT_IMPORT_ENABLED=False):
            upload_response = self.create_upload(self.readiness_csv())

        self.assertEqual(upload_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("FACILITY_READINESS_SNAPSHOT_IMPORT_ENABLED", str(upload_response.data))
        self.assertEqual(SourceDataUploadBatch.objects.count(), 0)

    def test_unknown_facility_is_rejected_during_dry_validation(self):
        upload_response = self.create_upload(self.readiness_csv(facility_code="FAC-MISSING"))
        validate_response = self.validate_upload(upload_response.data["public_id"])

        self.assertEqual(validate_response.status_code, status.HTTP_200_OK)
        self.assertEqual(validate_response.data["status"], SourceDataUploadBatch.STATUS_VALIDATION_FAILED)
        self.assertEqual(validate_response.data["accepted_count"], 0)
        self.assertTrue(SourceDataValidationIssue.objects.filter(code="unknown_facility_code").exists())
        self.assertEqual(FacilityReadinessSnapshot.objects.count(), 0)

    def test_unknown_readiness_columns_are_blocked_as_unapproved_operational_fields(self):
        csv_text = self.readiness_csv().replace(
            "source_kind,source_ref",
            "source_kind,source_ref,facility_generator_status",
        ).replace(
            "facility_report,readiness-checklist:row-1",
            "facility_report,readiness-checklist:row-1,not-persisted",
        )
        upload_response = self.create_upload(csv_text)
        validate_response = self.validate_upload(upload_response.data["public_id"])

        self.assertEqual(validate_response.data["status"], SourceDataUploadBatch.STATUS_VALIDATION_FAILED)
        self.assertTrue(
            SourceDataValidationIssue.objects.filter(
                code="unknown_column",
                severity=SourceDataValidationIssue.SEVERITY_ERROR,
            ).exists()
        )
        self.assertEqual(FacilityReadinessSnapshot.objects.count(), 0)

    def test_stale_report_is_warned_and_stored_with_stale_freshness(self):
        stale_reported_at = timezone.now() - timedelta(days=21)
        upload_response = self.create_upload(self.readiness_csv(reported_at=stale_reported_at))
        validate_response = self.validate_upload(upload_response.data["public_id"])
        confirm_response = self.confirm_upload(upload_response.data["public_id"])

        self.assertEqual(validate_response.data["status"], SourceDataUploadBatch.STATUS_READY_FOR_CONFIRMATION)
        self.assertTrue(SourceDataValidationIssue.objects.filter(code="stale_report", severity="warning").exists())
        self.assertEqual(
            validate_response.data["metadata"]["validation_summary"]["readiness_summary"]["stale_report_count"],
            1,
        )
        self.assertEqual(confirm_response.status_code, status.HTTP_200_OK)
        self.assertEqual(FacilityReadinessSnapshot.objects.get().freshness_state, FacilityReadinessFreshness.STALE)

    def test_stockout_and_service_disruption_are_warned_and_stored_as_capacity_concern(self):
        upload_response = self.create_upload(
            self.readiness_csv(
                ors=0,
                iv=0,
                beds=0,
                staff=0,
                referral="false",
                disruption="true",
                notes="ORS and IV fluids unavailable",
            )
        )
        validate_response = self.validate_upload(upload_response.data["public_id"])
        confirm_response = self.confirm_upload(upload_response.data["public_id"])

        self.assertEqual(validate_response.data["status"], SourceDataUploadBatch.STATUS_READY_FOR_CONFIRMATION)
        self.assertTrue(SourceDataValidationIssue.objects.filter(code="stockout_detected").exists())
        self.assertTrue(SourceDataValidationIssue.objects.filter(code="service_disruption_reported").exists())
        self.assertEqual(
            validate_response.data["metadata"]["validation_summary"]["readiness_summary"]["service_disruption_count"],
            1,
        )
        self.assertEqual(confirm_response.status_code, status.HTTP_200_OK)
        snapshot = FacilityReadinessSnapshot.objects.get()
        self.assertEqual(snapshot.readiness_state, FacilityReadinessState.CAPACITY_CONCERN)
        self.assertLess(snapshot.readiness_score, 100)

    def test_duplicate_snapshot_rows_are_rejected_before_import(self):
        reported_at = timezone.now()
        duplicate_row = (
            f"FAC-MIG-001,Got Kachola Dispensary,MIG-WARD-001,{reported_at.isoformat()},"
            "90,20,40,30,4,3,true,,false,facility_report,readiness-checklist:row-duplicate"
        )
        upload_response = self.create_upload(
            self.readiness_csv(reported_at=reported_at, extra_rows=[duplicate_row])
        )
        validate_response = self.validate_upload(upload_response.data["public_id"])
        confirm_response = self.confirm_upload(upload_response.data["public_id"])

        self.assertEqual(validate_response.data["status"], SourceDataUploadBatch.STATUS_VALIDATION_FAILED)
        self.assertEqual(validate_response.data["accepted_count"], 1)
        self.assertEqual(validate_response.data["rejected_count"], 1)
        self.assertTrue(SourceDataValidationIssue.objects.filter(code="duplicate_snapshot_in_file").exists())
        self.assertEqual(confirm_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(FacilityReadinessSnapshot.objects.count(), 0)

    def test_downstream_action_recomputes_readiness_evidence_and_forecast_inputs_without_promotion(self):
        upload_response = self.create_upload(self.readiness_csv())
        self.validate_upload(upload_response.data["public_id"])
        confirm_response = self.confirm_upload(upload_response.data["public_id"])

        force_authenticate_with_step_up(self.client, self.admin, StepUpGrant.PURPOSE_SOURCE_DATA)
        downstream_response = self.client.post(
            reverse("source-data-upload-downstream-actions", kwargs={"public_id": confirm_response.data["public_id"]}),
            {"action_key": "recompute_facility_readiness_evidence"},
            format="json",
        )

        self.assertEqual(downstream_response.status_code, status.HTTP_200_OK)
        self.assertEqual(downstream_response.data["action_status"], "completed")
        evidence = downstream_response.data["evidence"]
        self.assertEqual(evidence["snapshot_count"], 1)
        self.assertEqual(evidence["forecast_run_status"], FacilityForecastRun.STATUS_SUCCESS)
        self.assertFalse(evidence["triggers_sms"])
        self.assertFalse(evidence["promotes_model"])
        self.assertEqual(FacilityForecastRun.objects.count(), 1)
        self.assertNotEqual(evidence["promotion_target"], "dashboard_readiness_promoted")
