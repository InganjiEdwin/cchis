from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User

from .models import (
    PopulationBaselineRecord,
    PopulationExposureIngestionRun,
    SourceDataUploadBatch,
    SourceDataUploadEvent,
    SurveillanceIngestionRun,
    SurveillanceRecord,
    Ward,
)


class SourceDataPhaseThreeConfirmImportHistoryTests(APITestCase):
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
        self.admin = User.objects.create_user(
            username="source-data-phase3-admin",
            password="StrongPass123!",
            role=User.ROLE_ADMIN,
        )
        self.approver = User.objects.create_user(
            username="source-data-phase3-approver",
            password="StrongPass123!",
            role=User.ROLE_ADMIN,
        )
        self.supervisor = User.objects.create_user(
            username="source-data-phase3-supervisor",
            password="StrongPass123!",
            role=User.ROLE_SUPERVISOR,
        )
        self.analyst = User.objects.create_user(
            username="source-data-phase3-analyst",
            password="StrongPass123!",
            role=User.ROLE_ANALYST,
        )

    def valid_weekly_csv(self) -> str:
        return "\n".join(
            [
                "ward_code,reporting_period_start,reporting_period_end,suspected_cases,diarrheal_count,reporting_granularity,source_ref",
                "MIG-WARD-001,2026-04-27,2026-05-03,3,8,week,dhis2-weekly-export:row-1",
            ]
        )

    def confirmed_surveillance_csv(self) -> str:
        return "\n".join(
            [
                "ward_code,reporting_period_start,reporting_period_end,confirmed_cases,reporting_granularity,source_ref",
                "MIG-WARD-001,2026-04-27,2026-05-03,1,week,dhis2-weekly-export:confirmed-row-1",
            ]
        )

    def valid_population_csv(self) -> str:
        return "\n".join(
            [
                "ward_code,population_total,population_under_five,household_count_proxy,unit,source_ref",
                "MIG-WARD-001,24500,3600,5200,people,knbs-release:table-ward-population",
            ]
        )

    def surveillance_payload(
        self,
        *,
        csv_text: str | None = None,
        feed_key: str = "surveillance_weekly_aggregate",
        source_name: str = "Migori DHIS2 weekly export",
        correction_mode: str = "",
        operator_note: str = "",
    ):
        return {
            "feed_key": feed_key,
            "source_name": source_name,
            "source_timestamp": "2026-05-05T08:00:00Z",
            "reporting_period_start": "2026-04-27",
            "reporting_period_end": "2026-05-03",
            "correction_mode": correction_mode,
            "operator_note": operator_note,
            "file": SimpleUploadedFile(
                "surveillance.csv",
                (csv_text or self.valid_weekly_csv()).encode("utf-8"),
                content_type="text/csv",
            ),
        }

    def population_payload(self):
        return {
            "feed_key": "population_baseline",
            "source_name": "KNBS ward population baseline",
            "source_timestamp": "2026-05-05T08:00:00Z",
            "release_version": "knbs-2026-v1",
            "file": SimpleUploadedFile(
                "population.csv",
                self.valid_population_csv().encode("utf-8"),
                content_type="text/csv",
            ),
        }

    def create_upload(self, payload: dict, *, actor=None):
        self.client.force_authenticate(actor or self.supervisor)
        return self.client.post(reverse("source-data-upload-list-create"), payload, format="multipart")

    def validate_upload(self, public_id: str, *, actor=None):
        self.client.force_authenticate(actor or self.supervisor)
        return self.client.post(
            reverse("source-data-upload-validate", kwargs={"public_id": public_id}),
            {},
            format="json",
        )

    def confirm_upload(self, public_id: str, *, actor=None, payload: dict | None = None):
        self.client.force_authenticate(actor or self.supervisor)
        return self.client.post(
            reverse("source-data-upload-confirm", kwargs={"public_id": public_id}),
            payload or {},
            format="json",
        )

    def test_clean_surveillance_upload_can_be_confirmed_and_linked_to_ingestion_run(self):
        upload_response = self.create_upload(self.surveillance_payload())
        validate_response = self.validate_upload(upload_response.data["public_id"])

        confirm_response = self.confirm_upload(upload_response.data["public_id"])

        self.assertEqual(validate_response.status_code, status.HTTP_200_OK)
        self.assertEqual(confirm_response.status_code, status.HTTP_200_OK)
        self.assertEqual(confirm_response.data["status"], SourceDataUploadBatch.STATUS_IMPORTED)
        self.assertEqual(confirm_response.data["import_status"], SourceDataUploadBatch.IMPORT_IMPORTED)
        self.assertEqual(confirm_response.data["domain_ingestion_run_type"], "surveillance")
        self.assertIsNotNone(confirm_response.data["surveillance_ingestion_run"])
        self.assertEqual(SurveillanceIngestionRun.objects.count(), 1)
        self.assertGreater(SurveillanceRecord.objects.count(), 0)
        self.assertTrue(
            SourceDataUploadEvent.objects.filter(
                event_type=SourceDataUploadEvent.EVENT_IMPORT_COMPLETED
            ).exists()
        )

        history_response = self.client.get(
            reverse("source-data-upload-list-create"),
            {
                "feed_key": "surveillance_weekly_aggregate",
                "status": SourceDataUploadBatch.STATUS_IMPORTED,
                "source_name": "weekly",
                "actor": "supervisor",
                "date_from": "2026-01-01",
                "date_to": "2026-12-31",
            },
        )
        self.assertEqual(history_response.status_code, status.HTTP_200_OK)
        self.assertEqual(history_response.data["count"], 1)

    def test_clean_population_upload_can_be_confirmed_and_linked_to_ingestion_run(self):
        upload_response = self.create_upload(self.population_payload(), actor=self.admin)
        validate_response = self.validate_upload(upload_response.data["public_id"], actor=self.admin)

        confirm_response = self.confirm_upload(upload_response.data["public_id"], actor=self.admin)

        self.assertEqual(validate_response.status_code, status.HTTP_200_OK)
        self.assertEqual(confirm_response.status_code, status.HTTP_200_OK)
        self.assertEqual(confirm_response.data["status"], SourceDataUploadBatch.STATUS_IMPORTED)
        self.assertEqual(confirm_response.data["domain_ingestion_run_type"], "population_exposure")
        self.assertIsNotNone(confirm_response.data["population_exposure_ingestion_run"])
        self.assertEqual(PopulationExposureIngestionRun.objects.count(), 1)
        self.assertEqual(PopulationBaselineRecord.objects.count(), 1)

    def test_rejected_upload_cannot_be_confirmed(self):
        invalid_csv = "\n".join(
            [
                "ward_code,reporting_period_start,reporting_period_end,suspected_cases,confirmed_cases,notes",
                "MIG-WARD-001,2026-04-27,2026-05-03,3,1,call +254712345678",
            ]
        )
        upload_response = self.create_upload(self.surveillance_payload(csv_text=invalid_csv))
        validate_response = self.validate_upload(upload_response.data["public_id"])

        confirm_response = self.confirm_upload(upload_response.data["public_id"])

        self.assertEqual(validate_response.data["status"], SourceDataUploadBatch.STATUS_VALIDATION_FAILED)
        self.assertEqual(confirm_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(SurveillanceIngestionRun.objects.count(), 0)

    def test_risky_backfill_requires_second_admin_approval_before_confirmation(self):
        upload_response = self.create_upload(
            self.surveillance_payload(
                feed_key="surveillance_backfill",
                source_name="Migori surveillance backfill",
                correction_mode=SurveillanceIngestionRun.CORRECTION_BACKFILL,
                operator_note="Initial pilot history load for April.",
            ),
            actor=self.admin,
        )
        validate_response = self.validate_upload(upload_response.data["public_id"], actor=self.admin)

        blocked_confirm_response = self.confirm_upload(upload_response.data["public_id"], actor=self.admin)
        self.assertEqual(validate_response.status_code, status.HTTP_200_OK)
        self.assertEqual(blocked_confirm_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("maker-checker", blocked_confirm_response.data["detail"])

        request_response = self.client.post(
            reverse("source-data-upload-approval", kwargs={"public_id": upload_response.data["public_id"]}),
            {"action": "request", "reason": "Backfill changes production surveillance history."},
            format="json",
        )
        self.assertEqual(request_response.status_code, status.HTTP_200_OK)
        self.assertEqual(request_response.data["approval_status"], SourceDataUploadBatch.APPROVAL_PENDING)

        same_actor_approval_response = self.client.post(
            reverse("source-data-upload-approval", kwargs={"public_id": upload_response.data["public_id"]}),
            {"action": "approve", "reason": "Trying to self-approve."},
            format="json",
        )
        self.assertEqual(same_actor_approval_response.status_code, status.HTTP_400_BAD_REQUEST)

        self.client.force_authenticate(self.approver)
        missing_reason_response = self.client.post(
            reverse("source-data-upload-approval", kwargs={"public_id": upload_response.data["public_id"]}),
            {"action": "approve"},
            format="json",
        )
        self.assertEqual(missing_reason_response.status_code, status.HTTP_400_BAD_REQUEST)

        approval_response = self.client.post(
            reverse("source-data-upload-approval", kwargs={"public_id": upload_response.data["public_id"]}),
            {"action": "approve", "reason": "Second admin reviewed source and period."},
            format="json",
        )
        self.assertEqual(approval_response.status_code, status.HTTP_200_OK)
        self.assertEqual(approval_response.data["approval_status"], SourceDataUploadBatch.APPROVAL_APPROVED)

        confirm_response = self.confirm_upload(upload_response.data["public_id"], actor=self.admin)
        self.assertEqual(confirm_response.status_code, status.HTTP_200_OK)
        self.assertEqual(confirm_response.data["status"], SourceDataUploadBatch.STATUS_IMPORTED)
        self.assertEqual(SurveillanceIngestionRun.objects.count(), 1)

    def test_confirmed_surveillance_truth_requires_second_admin_approval(self):
        upload_response = self.create_upload(
            self.surveillance_payload(csv_text=self.confirmed_surveillance_csv()),
            actor=self.supervisor,
        )
        validate_response = self.validate_upload(upload_response.data["public_id"], actor=self.supervisor)

        blocked_confirm_response = self.confirm_upload(upload_response.data["public_id"], actor=self.supervisor)

        self.assertEqual(validate_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            validate_response.data["validation_summary"]["truth_level_counts"]["confirmed_surveillance"],
            1,
        )
        self.assertEqual(blocked_confirm_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("maker-checker", blocked_confirm_response.data["detail"])

        request_response = self.client.post(
            reverse("source-data-upload-approval", kwargs={"public_id": upload_response.data["public_id"]}),
            {"action": "request", "reason": "Confirmed surveillance truth updates operational evidence."},
            format="json",
        )
        self.client.force_authenticate(self.approver)
        approval_response = self.client.post(
            reverse("source-data-upload-approval", kwargs={"public_id": upload_response.data["public_id"]}),
            {"action": "approve", "reason": "Confirmed counts reconciled against the source extract."},
            format="json",
        )
        confirm_response = self.confirm_upload(upload_response.data["public_id"], actor=self.supervisor)

        self.assertEqual(request_response.data["approval_risk_category"], "production_surveillance_truth")
        self.assertEqual(approval_response.status_code, status.HTTP_200_OK)
        self.assertEqual(confirm_response.status_code, status.HTTP_200_OK)
        self.assertEqual(confirm_response.data["status"], SourceDataUploadBatch.STATUS_IMPORTED)

    def test_analyst_can_view_history_but_cannot_confirm_or_approve(self):
        upload_response = self.create_upload(self.surveillance_payload())
        self.validate_upload(upload_response.data["public_id"])
        self.client.force_authenticate(self.analyst)

        history_response = self.client.get(reverse("source-data-upload-list-create"))
        confirm_response = self.client.post(
            reverse("source-data-upload-confirm", kwargs={"public_id": upload_response.data["public_id"]}),
            {},
            format="json",
        )
        approval_response = self.client.post(
            reverse("source-data-upload-approval", kwargs={"public_id": upload_response.data["public_id"]}),
            {"action": "request", "reason": "Analyst request should be blocked."},
            format="json",
        )

        self.assertEqual(history_response.status_code, status.HTTP_200_OK)
        self.assertEqual(confirm_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(approval_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_upload_can_be_cancelled_before_import_and_audited(self):
        upload_response = self.create_upload(self.surveillance_payload())
        public_id = upload_response.data["public_id"]

        self.client.force_authenticate(self.supervisor)
        cancel_response = self.client.post(
            reverse("source-data-upload-cancel", kwargs={"public_id": public_id}),
            {"reason": "Wrong reporting period selected before validation."},
            format="json",
        )
        validate_response = self.client.post(
            reverse("source-data-upload-validate", kwargs={"public_id": public_id}),
            {},
            format="json",
        )

        self.assertEqual(cancel_response.status_code, status.HTTP_200_OK)
        self.assertEqual(cancel_response.data["status"], SourceDataUploadBatch.STATUS_CANCELLED)
        self.assertEqual(
            cancel_response.data["metadata"]["cancellation"]["reason"],
            "Wrong reporting period selected before validation.",
        )
        self.assertTrue(
            SourceDataUploadEvent.objects.filter(
                event_type=SourceDataUploadEvent.EVENT_UPLOAD_CANCELLED,
                metadata__reason="Wrong reporting period selected before validation.",
            ).exists()
        )
        self.assertEqual(validate_response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_imported_upload_cannot_be_cancelled(self):
        upload_response = self.create_upload(self.surveillance_payload())
        self.validate_upload(upload_response.data["public_id"])
        confirm_response = self.confirm_upload(upload_response.data["public_id"])

        cancel_response = self.client.post(
            reverse("source-data-upload-cancel", kwargs={"public_id": confirm_response.data["public_id"]}),
            {"reason": "Trying to cancel after import."},
            format="json",
        )

        self.assertEqual(confirm_response.status_code, status.HTTP_200_OK)
        self.assertEqual(cancel_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("cannot be cancelled", cancel_response.data["detail"])
