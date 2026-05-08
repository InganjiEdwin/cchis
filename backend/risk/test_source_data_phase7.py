from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import StepUpGrant, User

from .models import (
    SensitiveExportRequest,
    SourceDataUploadBatch,
    SourceDataUploadEvent,
    SourceDataValidationIssue,
)
from .source_data.validation import (
    SOURCE_DATA_VALIDATION_ERROR_CATALOG,
    source_data_validation_error_catalog,
)
from .test_step_up_utils import force_authenticate_with_step_up


class SourceDataPhaseSevenUxSecurityContractTests(APITestCase):
    def setUp(self):
        self.upload_root = TemporaryDirectory()
        self.addCleanup(self.upload_root.cleanup)
        self.settings_override = override_settings(
            SOURCE_DATA_UPLOAD_ROOT=Path(self.upload_root.name),
            SOURCE_DATA_MAX_UPLOAD_SIZE_BYTES=1024 * 1024,
            SOURCE_DATA_MAX_UPLOAD_ROWS=20,
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

        self.admin = User.objects.create_user(
            username="source-data-phase7-admin",
            password="StrongPass123!",
            role=User.ROLE_ADMIN,
        )
        self.supervisor = User.objects.create_user(
            username="source-data-phase7-supervisor",
            password="StrongPass123!",
            role=User.ROLE_SUPERVISOR,
        )
        self.analyst = User.objects.create_user(
            username="source-data-phase7-analyst",
            password="StrongPass123!",
            role=User.ROLE_ANALYST,
        )
        self.chv = User.objects.create_user(
            username="source-data-phase7-chv",
            password="StrongPass123!",
            role=User.ROLE_CHV,
        )

    def weekly_csv(self, *, row_note: str = "") -> str:
        return "\n".join(
            [
                "ward_code,reporting_period_start,reporting_period_end,suspected_cases,confirmed_cases,diarrheal_count,reporting_granularity,notes,source_ref",
                f"MIG-WARD-001,2026-04-27,2026-05-03,3,1,8,week,{row_note},dhis2-weekly-export:row-1",
            ]
        )

    def upload_payload(self, *, csv_text: str | None = None, filename: str = "weekly.csv"):
        return {
            "feed_key": "surveillance_weekly_aggregate",
            "source_name": "Migori DHIS2 weekly export",
            "source_timestamp": "2026-05-05T08:00:00Z",
            "reporting_period_start": "2026-04-27",
            "reporting_period_end": "2026-05-03",
            "file": SimpleUploadedFile(
                filename,
                (csv_text or self.weekly_csv()).encode("utf-8"),
                content_type="text/csv",
            ),
        }

    def create_upload(self, *, actor=None, csv_text: str | None = None):
        force_authenticate_with_step_up(self.client, actor or self.supervisor, StepUpGrant.PURPOSE_SOURCE_DATA)
        return self.client.post(
            reverse("source-data-upload-list-create"),
            self.upload_payload(csv_text=csv_text),
            format="multipart",
        )

    def test_feed_types_exposes_stable_validation_error_catalog_contract(self):
        self.client.force_authenticate(self.analyst)

        response = self.client.get(reverse("source-data-feed-types"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        catalog = response.data["validation_error_catalog"]
        self.assertEqual(catalog["schema_version"], "source-data-validation-error-catalog-v1")
        documented_codes = {item["code"] for item in catalog["codes"]}
        self.assertIn("unknown_column", documented_codes)
        self.assertIn("pii_phone_value_detected", documented_codes)
        self.assertEqual(
            source_data_validation_error_catalog()["schema_version"],
            "source-data-validation-error-catalog-v1",
        )

    def test_validation_issue_contract_redacts_direct_identifiers_from_response_and_csv(self):
        phone_number = "+254712345678"
        upload_response = self.create_upload(csv_text=self.weekly_csv(row_note=f"call {phone_number}"))
        validate_response = self.client.post(
            reverse("source-data-upload-validate", kwargs={"public_id": upload_response.data["public_id"]}),
            {},
            format="json",
        )

        self.assertEqual(validate_response.status_code, status.HTTP_200_OK)
        self.assertEqual(validate_response.data["status"], SourceDataUploadBatch.STATUS_VALIDATION_FAILED)
        pii_issue = next(
            issue for issue in validate_response.data["validation_issues"] if issue["code"] == "pii_phone_value_detected"
        )
        self.assertEqual(
            set(pii_issue),
            {"id", "row_number", "severity", "code", "column_name", "message", "safe_context", "created_at"},
        )
        self.assertEqual(pii_issue["severity"], SourceDataValidationIssue.SEVERITY_ERROR)
        self.assertNotIn(phone_number, pii_issue["message"])
        self.assertNotIn(phone_number, str(pii_issue["safe_context"]))
        self.assertNotIn(phone_number, str(validate_response.data["metadata"]))

        errors_response = self.client.get(
            reverse("source-data-upload-errors-file", kwargs={"public_id": upload_response.data["public_id"]})
        )

        self.assertEqual(errors_response.status_code, status.HTTP_200_OK)
        self.assertIn("pii_phone_value_detected", errors_response.data["payload"])
        self.assertNotIn(phone_number, errors_response.data["payload"])
        self.assertEqual(SensitiveExportRequest.objects.count(), 0)
        self.assertTrue(
            SourceDataUploadEvent.objects.filter(
                event_type=SourceDataUploadEvent.EVENT_ERRORS_DOWNLOADED
            ).exists()
        )

    def test_validation_summary_does_not_return_raw_sample_rows(self):
        upload_response = self.create_upload(csv_text=self.weekly_csv(row_note="aggregate-only"))
        validate_response = self.client.post(
            reverse("source-data-upload-validate", kwargs={"public_id": upload_response.data["public_id"]}),
            {},
            format="json",
        )

        self.assertEqual(validate_response.status_code, status.HTTP_200_OK)
        summary = validate_response.data["metadata"]["validation_summary"]
        self.assertIn("sample_row_count", summary)
        self.assertNotIn("sample_rows", summary)
        self.assertNotIn("dhis2-weekly-export:row-1", str(validate_response.data["metadata"]))
        self.assertNotIn("MIG-WARD-001", str(validate_response.data["metadata"]))

    def test_free_text_patient_identifier_patterns_are_blocked(self):
        upload_response = self.create_upload(csv_text=self.weekly_csv(row_note="patient full name Jane Doe"))
        validate_response = self.client.post(
            reverse("source-data-upload-validate", kwargs={"public_id": upload_response.data["public_id"]}),
            {},
            format="json",
        )

        self.assertEqual(validate_response.status_code, status.HTTP_200_OK)
        self.assertEqual(validate_response.data["status"], SourceDataUploadBatch.STATUS_VALIDATION_FAILED)
        self.assertTrue(
            SourceDataValidationIssue.objects.filter(code="unsafe_text_value_detected").exists()
        )

    def test_generated_validation_issue_codes_are_documented(self):
        upload_response = self.create_upload(csv_text=self.weekly_csv(row_note="call +254712345678"))
        self.client.post(
            reverse("source-data-upload-validate", kwargs={"public_id": upload_response.data["public_id"]}),
            {},
            format="json",
        )

        generated_codes = set(SourceDataValidationIssue.objects.values_list("code", flat=True))

        self.assertTrue(generated_codes)
        self.assertLessEqual(generated_codes, set(SOURCE_DATA_VALIDATION_ERROR_CATALOG))

    def test_role_permission_matrix_for_source_data_diagnostics(self):
        upload_response = self.create_upload(actor=self.supervisor)
        public_id = upload_response.data["public_id"]

        force_authenticate_with_step_up(self.client, self.admin, StepUpGrant.PURPOSE_SOURCE_DATA)
        self.assertEqual(self.client.get(reverse("source-data-feed-types")).status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.post(reverse("source-data-upload-list-create"), self.upload_payload(), format="multipart").status_code, status.HTTP_201_CREATED)

        force_authenticate_with_step_up(self.client, self.supervisor, StepUpGrant.PURPOSE_SOURCE_DATA)
        self.assertEqual(
            self.client.post(reverse("source-data-upload-validate", kwargs={"public_id": public_id}), {}, format="json").status_code,
            status.HTTP_200_OK,
        )

        self.client.force_authenticate(self.analyst)
        self.assertEqual(self.client.get(reverse("source-data-upload-list-create")).status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get(reverse("source-data-upload-detail", kwargs={"public_id": public_id})).status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get(reverse("source-data-upload-errors-file", kwargs={"public_id": public_id})).status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.post(reverse("source-data-upload-list-create"), self.upload_payload(), format="multipart").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            self.client.post(reverse("source-data-upload-validate", kwargs={"public_id": public_id}), {}, format="json").status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.client.post(reverse("source-data-upload-confirm", kwargs={"public_id": public_id}), {}, format="json").status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.client.post(
                reverse("source-data-upload-downstream-actions", kwargs={"public_id": public_id}),
                {"action_key": "regenerate_surveillance_labels"},
                format="json",
            ).status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.client.force_authenticate(self.chv)
        self.assertEqual(self.client.get(reverse("source-data-feed-types")).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get(reverse("source-data-upload-list-create")).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get(reverse("source-data-upload-detail", kwargs={"public_id": public_id})).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get(reverse("source-data-upload-errors-file", kwargs={"public_id": public_id})).status_code, status.HTTP_403_FORBIDDEN)
