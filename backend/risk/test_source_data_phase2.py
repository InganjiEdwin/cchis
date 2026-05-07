from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User

from .models import (
    PopulationExposureIngestionRun,
    SourceDataUploadArtifact,
    SourceDataUploadBatch,
    SourceDataUploadEvent,
    SourceDataValidationIssue,
    SurveillanceIngestionRun,
)


class SourceDataPhaseTwoUploadDryValidationTests(APITestCase):
    def setUp(self):
        self.upload_root = TemporaryDirectory()
        self.addCleanup(self.upload_root.cleanup)
        self.settings_override = override_settings(
            SOURCE_DATA_UPLOAD_ROOT=Path(self.upload_root.name),
            SOURCE_DATA_MAX_UPLOAD_SIZE_BYTES=1024 * 1024,
            SOURCE_DATA_MAX_UPLOAD_ROWS=5,
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

        self.admin = User.objects.create_user(
            username="source-data-phase2-admin",
            password="StrongPass123!",
            role=User.ROLE_ADMIN,
        )
        self.supervisor = User.objects.create_user(
            username="source-data-phase2-supervisor",
            password="StrongPass123!",
            role=User.ROLE_SUPERVISOR,
        )
        self.analyst = User.objects.create_user(
            username="source-data-phase2-analyst",
            password="StrongPass123!",
            role=User.ROLE_ANALYST,
        )

    def upload_payload(self, *, csv_text: str, filename: str = "weekly.csv", source_name: str = "Migori DHIS2"):
        return {
            "feed_key": "surveillance_weekly_aggregate",
            "source_name": source_name,
            "source_timestamp": "2026-05-05T08:00:00Z",
            "reporting_period_start": "2026-04-27",
            "reporting_period_end": "2026-05-03",
            "file": SimpleUploadedFile(filename, csv_text.encode("utf-8"), content_type="text/csv"),
        }

    def valid_weekly_csv(self, *, confirmed_cases: int = 1) -> str:
        return "\n".join(
            [
                "ward_code,reporting_period_start,reporting_period_end,suspected_cases,confirmed_cases,diarrheal_count,reporting_granularity,source_ref",
                f"MIG-WARD-001,2026-04-27,2026-05-03,3,{confirmed_cases},8,week,dhis2-weekly-export:row-1",
            ]
        )

    def create_upload(self, *, csv_text: str | None = None, filename: str = "weekly.csv"):
        self.client.force_authenticate(self.supervisor)
        return self.client.post(
            reverse("source-data-upload-list-create"),
            self.upload_payload(csv_text=csv_text or self.valid_weekly_csv(), filename=filename),
            format="multipart",
        )

    def test_admin_or_supervisor_can_create_upload_batch_without_domain_mutation(self):
        response = self.create_upload()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], SourceDataUploadBatch.STATUS_UPLOADED)
        self.assertEqual(response.data["validation_status"], SourceDataUploadBatch.VALIDATION_NOT_STARTED)
        self.assertEqual(response.data["feed_key"], "surveillance_weekly_aggregate")
        self.assertEqual(SourceDataUploadArtifact.objects.count(), 1)
        artifact = SourceDataUploadArtifact.objects.get()
        self.assertTrue(Path(artifact.storage_path).exists())
        self.assertEqual(len(artifact.sha256), 64)
        self.assertEqual(SurveillanceIngestionRun.objects.count(), 0)
        self.assertEqual(PopulationExposureIngestionRun.objects.count(), 0)
        self.assertTrue(
            SourceDataUploadEvent.objects.filter(event_type=SourceDataUploadEvent.EVENT_UPLOAD_CREATED).exists()
        )

    def test_dry_validation_wraps_surveillance_inspector_and_stores_issues(self):
        upload_response = self.create_upload()

        validate_response = self.client.post(
            reverse("source-data-upload-validate", kwargs={"public_id": upload_response.data["public_id"]}),
            {},
            format="json",
        )

        self.assertEqual(validate_response.status_code, status.HTTP_200_OK)
        self.assertEqual(validate_response.data["status"], SourceDataUploadBatch.STATUS_READY_FOR_CONFIRMATION)
        self.assertEqual(validate_response.data["validation_status"], SourceDataUploadBatch.VALIDATION_PASSED)
        self.assertEqual(validate_response.data["row_count"], 1)
        self.assertEqual(validate_response.data["accepted_count"], 1)
        self.assertEqual(validate_response.data["rejected_count"], 0)
        self.assertEqual(
            SourceDataUploadEvent.objects.filter(
                event_type=SourceDataUploadEvent.EVENT_VALIDATION_COMPLETED
            ).count(),
            1,
        )
        self.assertEqual(SourceDataValidationIssue.objects.filter(severity="error").count(), 0)
        self.assertEqual(SurveillanceIngestionRun.objects.count(), 0)

    def test_dry_validation_rejects_sampled_pii_values_before_domain_validation(self):
        pii_csv = "\n".join(
            [
                "ward_code,reporting_period_start,reporting_period_end,suspected_cases,confirmed_cases,notes",
                "MIG-WARD-001,2026-04-27,2026-05-03,3,1,call +254712345678",
            ]
        )
        upload_response = self.create_upload(csv_text=pii_csv, filename="weekly-pii.csv")

        validate_response = self.client.post(
            reverse("source-data-upload-validate", kwargs={"public_id": upload_response.data["public_id"]}),
            {},
            format="json",
        )

        self.assertEqual(validate_response.status_code, status.HTTP_200_OK)
        self.assertEqual(validate_response.data["status"], SourceDataUploadBatch.STATUS_VALIDATION_FAILED)
        self.assertEqual(validate_response.data["accepted_count"], 0)
        self.assertTrue(
            SourceDataValidationIssue.objects.filter(code="pii_phone_value_detected").exists()
        )
        self.assertEqual(SurveillanceIngestionRun.objects.count(), 0)

    def test_dry_validation_rejects_composite_pii_headers_before_domain_validation(self):
        pii_header_csv = "\n".join(
            [
                "ward_code,reporting_period_start,reporting_period_end,suspected_cases,confirmed_cases,patient_phone_number",
                "MIG-WARD-001,2026-04-27,2026-05-03,3,1,",
            ]
        )
        upload_response = self.create_upload(csv_text=pii_header_csv, filename="weekly-pii-header.csv")

        validate_response = self.client.post(
            reverse("source-data-upload-validate", kwargs={"public_id": upload_response.data["public_id"]}),
            {},
            format="json",
        )

        self.assertEqual(validate_response.status_code, status.HTTP_200_OK)
        self.assertEqual(validate_response.data["status"], SourceDataUploadBatch.STATUS_VALIDATION_FAILED)
        self.assertTrue(
            SourceDataValidationIssue.objects.filter(
                upload_batch__public_id=upload_response.data["public_id"],
                code="pii_header_detected",
                column_name="patient_phone_number",
            ).exists()
        )
        self.assertEqual(SurveillanceIngestionRun.objects.count(), 0)

    def test_dry_validation_scans_trailing_cells_not_named_by_headers(self):
        csv_with_trailing_pii_cell = "\n".join(
            [
                "ward_code,reporting_period_start,reporting_period_end,suspected_cases,confirmed_cases,source_ref",
                "MIG-WARD-001,2026-04-27,2026-05-03,3,1,dhis2-weekly-export:row-1,+254712345678",
            ]
        )
        upload_response = self.create_upload(csv_text=csv_with_trailing_pii_cell, filename="weekly-extra-cell.csv")

        validate_response = self.client.post(
            reverse("source-data-upload-validate", kwargs={"public_id": upload_response.data["public_id"]}),
            {},
            format="json",
        )

        self.assertEqual(validate_response.status_code, status.HTTP_200_OK)
        self.assertEqual(validate_response.data["status"], SourceDataUploadBatch.STATUS_VALIDATION_FAILED)
        self.assertTrue(
            SourceDataValidationIssue.objects.filter(
                upload_batch__public_id=upload_response.data["public_id"],
                code="row_has_extra_columns",
                row_number=2,
            ).exists()
        )
        self.assertTrue(
            SourceDataValidationIssue.objects.filter(
                upload_batch__public_id=upload_response.data["public_id"],
                code="pii_phone_value_detected",
                row_number=2,
                column_name="__extra_column_1",
            ).exists()
        )
        self.assertEqual(SurveillanceIngestionRun.objects.count(), 0)

    def test_duplicate_metadata_and_errors_csv_are_available_as_diagnostics(self):
        first_response = self.create_upload(csv_text=self.valid_weekly_csv(confirmed_cases=1), filename="weekly-1.csv")
        second_response = self.create_upload(csv_text=self.valid_weekly_csv(confirmed_cases=2), filename="weekly-2.csv")

        self.assertEqual(first_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second_response.status_code, status.HTTP_201_CREATED)
        self.assertIsNotNone(second_response.data["duplicate_of_public_id"])

        validate_response = self.client.post(
            reverse("source-data-upload-validate", kwargs={"public_id": second_response.data["public_id"]}),
            {},
            format="json",
        )
        self.assertEqual(validate_response.status_code, status.HTTP_200_OK)
        self.assertTrue(
            SourceDataValidationIssue.objects.filter(code="duplicate_upload_metadata").exists()
        )

        errors_response = self.client.get(
            reverse("source-data-upload-errors-file", kwargs={"public_id": second_response.data["public_id"]})
        )

        self.assertEqual(errors_response.status_code, status.HTTP_200_OK)
        self.assertEqual(errors_response.data["content_type"], "text/csv")
        self.assertIn("duplicate_upload_metadata", errors_response.data["payload"])
        self.assertTrue(
            SourceDataUploadEvent.objects.filter(event_type=SourceDataUploadEvent.EVENT_ERRORS_DOWNLOADED).exists()
        )

    def test_analyst_can_list_and_view_but_cannot_upload_or_validate(self):
        upload_response = self.create_upload()
        self.client.force_authenticate(self.analyst)

        list_response = self.client.get(reverse("source-data-upload-list-create"))
        detail_response = self.client.get(
            reverse("source-data-upload-detail", kwargs={"public_id": upload_response.data["public_id"]})
        )
        create_response = self.client.post(
            reverse("source-data-upload-list-create"),
            self.upload_payload(csv_text=self.valid_weekly_csv(), filename="analyst.csv"),
            format="multipart",
        )
        validate_response = self.client.post(
            reverse("source-data-upload-validate", kwargs={"public_id": upload_response.data["public_id"]}),
            {},
            format="json",
        )

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(create_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(validate_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unknown_feed_key_and_oversized_file_are_rejected_before_storage(self):
        self.client.force_authenticate(self.admin)
        unknown_response = self.client.post(
            reverse("source-data-upload-list-create"),
            {
                **self.upload_payload(csv_text=self.valid_weekly_csv()),
                "feed_key": "unknown_feed",
            },
            format="multipart",
        )
        oversized_response = self.client.post(
            reverse("source-data-upload-list-create"),
            {
                **self.upload_payload(csv_text="x" * (1024 * 1024 + 1), filename="oversized.csv"),
                "source_name": "Migori oversized source",
            },
            format="multipart",
        )

        self.assertEqual(unknown_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(oversized_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(SourceDataUploadBatch.objects.count(), 0)
