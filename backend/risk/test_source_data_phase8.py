from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User

from .models import ETLHeartbeat, SourceDataUploadArtifact, SourceDataUploadBatch, SourceDataValidationIssue
from .source_data.operations import cleanup_expired_source_data_artifacts


def throttled_rest_framework(upload_rate: str = "2/minute", validate_rate: str = "2/minute") -> dict:
    return {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": {
            **settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"],
            "source_data_upload": upload_rate,
            "source_data_validate": validate_rate,
        },
    }


class SourceDataPhaseEightProductionHardeningTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.upload_root = TemporaryDirectory()
        self.addCleanup(self.upload_root.cleanup)
        self.settings_override = override_settings(
            SOURCE_DATA_UPLOAD_ROOT=Path(self.upload_root.name),
            SOURCE_DATA_MAX_UPLOAD_SIZE_BYTES=1024 * 1024,
            SOURCE_DATA_MAX_UPLOAD_ROWS=20,
            SOURCE_DATA_ASYNC_IMPORT_SIZE_BYTES=1024 * 1024,
            SOURCE_DATA_TASK_STALE_MINUTES=10,
            SOURCE_DATA_FAILED_IMPORT_ALERT_THRESHOLD=2,
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

        self.admin = User.objects.create_user(
            username="source-data-phase8-admin",
            password="StrongPass123!",
            role=User.ROLE_ADMIN,
        )
        self.supervisor = User.objects.create_user(
            username="source-data-phase8-supervisor",
            password="StrongPass123!",
            role=User.ROLE_SUPERVISOR,
        )
        self.analyst = User.objects.create_user(
            username="source-data-phase8-analyst",
            password="StrongPass123!",
            role=User.ROLE_ANALYST,
        )

    def weekly_csv(self, *, extra_rows: list[str] | None = None, notes: str = "") -> str:
        return "\n".join(
            [
                "ward_code,reporting_period_start,reporting_period_end,suspected_cases,confirmed_cases,diarrheal_count,reporting_granularity,notes,source_ref",
                f"MIG-WARD-001,2026-04-27,2026-05-03,3,1,8,week,{notes},dhis2-weekly-export:row-1",
                *(extra_rows or []),
            ]
        )

    def upload_payload(
        self,
        *,
        csv_text: str | None = None,
        filename: str = "weekly.csv",
        content_type: str = "text/csv",
    ):
        return {
            "feed_key": "surveillance_weekly_aggregate",
            "source_name": "Migori DHIS2 weekly export",
            "source_timestamp": "2026-05-05T08:00:00Z",
            "reporting_period_start": "2026-04-27",
            "reporting_period_end": "2026-05-03",
            "file": SimpleUploadedFile(
                filename,
                (csv_text or self.weekly_csv()).encode("utf-8"),
                content_type=content_type,
            ),
        }

    def create_upload(
        self,
        *,
        actor=None,
        csv_text: str | None = None,
        filename: str = "weekly.csv",
        content_type: str = "text/csv",
    ):
        self.client.force_authenticate(actor or self.supervisor)
        return self.client.post(
            reverse("source-data-upload-list-create"),
            self.upload_payload(csv_text=csv_text, filename=filename, content_type=content_type),
            format="multipart",
        )

    def validate_upload(self, public_id: str):
        self.client.force_authenticate(self.supervisor)
        return self.client.post(
            reverse("source-data-upload-validate", kwargs={"public_id": public_id}),
            {},
            format="json",
        )

    def test_upload_and_validation_endpoints_are_rate_limited(self):
        with self.settings(REST_FRAMEWORK=throttled_rest_framework()):
            first_response = self.create_upload(filename="weekly-1.csv")
            second_response = self.create_upload(filename="weekly-2.csv")
            third_response = self.create_upload(filename="weekly-3.csv")

            self.assertEqual(first_response.status_code, status.HTTP_201_CREATED)
            self.assertEqual(second_response.status_code, status.HTTP_201_CREATED)
            self.assertEqual(third_response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

        cache.clear()
        upload_response = self.create_upload(filename="validate-throttle.csv")
        with self.settings(REST_FRAMEWORK=throttled_rest_framework()):
            first_validate = self.validate_upload(upload_response.data["public_id"])
            second_validate = self.validate_upload(upload_response.data["public_id"])
            third_validate = self.validate_upload(upload_response.data["public_id"])

            self.assertEqual(first_validate.status_code, status.HTTP_200_OK)
            self.assertEqual(second_validate.status_code, status.HTTP_200_OK)
            self.assertEqual(third_validate.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_artifact_cleanup_purges_expired_raw_files_and_records_worker_heartbeat(self):
        upload_response = self.create_upload(filename="cleanup.csv")
        artifact = SourceDataUploadArtifact.objects.get(upload_batch__public_id=upload_response.data["public_id"])
        artifact_path = Path(artifact.storage_path)
        SourceDataUploadArtifact.objects.filter(pk=artifact.pk).update(
            retention_expires_at=timezone.now() - timedelta(minutes=5)
        )

        result = cleanup_expired_source_data_artifacts()
        artifact.refresh_from_db()

        self.assertEqual(result["deleted_file_count"], 1)
        self.assertFalse(artifact_path.exists())
        self.assertEqual(artifact.redaction_state, "purged")
        self.assertTrue(
            ETLHeartbeat.objects.filter(task_name="risk.tasks.cleanup_source_data_upload_artifacts_task").exists()
        )

    def test_artifact_cleanup_task_is_scheduled_by_celery_beat(self):
        schedule = settings.CELERY_BEAT_SCHEDULE["source-data-upload-artifact-cleanup"]

        self.assertEqual(schedule["task"], "risk.tasks.cleanup_source_data_upload_artifacts_task")
        self.assertIn("schedule", schedule)

    def test_operations_endpoint_reports_metrics_alerts_stuck_tasks_and_retention_state(self):
        now = timezone.now()
        SourceDataUploadBatch.objects.create(
            feed_key="surveillance_weekly_aggregate",
            domain="health_surveillance",
            source_type="weekly_aggregate",
            source_name="Migori stuck import",
            source_timestamp=now,
            status=SourceDataUploadBatch.STATUS_CONFIRMING,
            validation_status=SourceDataUploadBatch.VALIDATION_PASSED,
            import_status=SourceDataUploadBatch.IMPORT_RUNNING,
            import_celery_task_id="stuck-task-id",
            created_by=self.supervisor,
        )
        SourceDataUploadBatch.objects.filter(source_name="Migori stuck import").update(
            updated_at=now - timedelta(hours=1)
        )
        for index in range(2):
            SourceDataUploadBatch.objects.create(
                feed_key="surveillance_weekly_aggregate",
                domain="health_surveillance",
                source_type="weekly_aggregate",
                source_name=f"Migori failed import {index}",
                source_timestamp=now,
                status=SourceDataUploadBatch.STATUS_IMPORT_FAILED,
                validation_status=SourceDataUploadBatch.VALIDATION_PASSED,
                import_status=SourceDataUploadBatch.IMPORT_FAILED,
                created_by=self.supervisor,
            )

        self.client.force_authenticate(self.analyst)
        response = self.client.get(reverse("source-data-operations"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["schema_version"], "source-data-operations-v1")
        self.assertGreaterEqual(response.data["metrics"]["import_failure_count"], 2)
        self.assertEqual(response.data["stuck_tasks"]["imports"][0]["import_celery_task_id"], "stuck-task-id")
        alert_keys = {item["key"] for item in response.data["alerts"]}
        self.assertIn("repeated_failed_imports", alert_keys)
        self.assertIn("stuck_source_data_tasks", alert_keys)
        self.assertIn("backup_restore_reference", response.data["production_controls"])

    def test_upload_abuse_cases_are_blocked_without_leaking_raw_values(self):
        malicious_response = self.create_upload(filename="../../evil name.csv")
        artifact = SourceDataUploadArtifact.objects.get(upload_batch__public_id=malicious_response.data["public_id"])
        self.assertEqual(artifact.original_filename, "evil_name.csv")
        Path(artifact.storage_path).resolve().relative_to(Path(self.upload_root.name).resolve())

        formula_response = self.create_upload(
            filename="formula.csv",
            csv_text=self.weekly_csv(notes="=IMPORTXML('http://example.invalid')"),
        )
        formula_validate = self.validate_upload(formula_response.data["public_id"])
        self.assertEqual(formula_validate.data["status"], SourceDataUploadBatch.STATUS_VALIDATION_FAILED)
        self.assertTrue(SourceDataValidationIssue.objects.filter(code="formula_injection_value").exists())

        hidden_formula_rows = [
            f"MIG-WARD-001,2026-04-27,2026-05-03,{index},0,{index},week,,dhis2-weekly-export:row-{index}"
            for index in range(1, 60)
        ]
        hidden_formula_rows.append(
            "MIG-WARD-001,2026-04-27,2026-05-03,4,0,9,week,=IMPORTXML('http://example.invalid'),dhis2-weekly-export:hidden-formula"
        )
        with self.settings(SOURCE_DATA_MAX_UPLOAD_ROWS=80):
            hidden_formula_response = self.create_upload(
                filename="hidden-formula.csv",
                csv_text="\n".join(
                    [
                        "ward_code,reporting_period_start,reporting_period_end,suspected_cases,confirmed_cases,diarrheal_count,reporting_granularity,notes,source_ref",
                        *hidden_formula_rows,
                    ]
                ),
            )
            hidden_formula_validate = self.validate_upload(hidden_formula_response.data["public_id"])
        self.assertEqual(hidden_formula_validate.data["status"], SourceDataUploadBatch.STATUS_VALIDATION_FAILED)
        self.assertTrue(
            SourceDataValidationIssue.objects.filter(
                upload_batch__public_id=hidden_formula_response.data["public_id"],
                code="formula_injection_value",
                row_number=61,
            ).exists()
        )

        pii_header_csv = self.weekly_csv().replace(",notes,", ",phone,")
        pii_response = self.create_upload(filename="pii-header.csv", csv_text=pii_header_csv)
        pii_validate = self.validate_upload(pii_response.data["public_id"])
        self.assertEqual(pii_validate.data["status"], SourceDataUploadBatch.STATUS_VALIDATION_FAILED)
        self.assertTrue(SourceDataValidationIssue.objects.filter(code="pii_header_detected").exists())

        html_response = self.create_upload(
            filename="html.csv",
            csv_text="<html><body>not csv</body></html>",
            content_type="text/html",
        )
        html_validate = self.validate_upload(html_response.data["public_id"])
        self.assertEqual(html_validate.data["status"], SourceDataUploadBatch.STATUS_VALIDATION_FAILED)
        self.assertTrue(SourceDataValidationIssue.objects.filter(code="unexpected_content_type").exists())
        self.assertTrue(SourceDataValidationIssue.objects.filter(code="html_or_xml_file_detected").exists())

        with self.settings(SOURCE_DATA_MAX_UPLOAD_ROWS=1):
            huge_response = self.create_upload(
                filename="too-many-rows.csv",
                csv_text=self.weekly_csv(
                    extra_rows=[
                        "MIG-WARD-001,2026-04-27,2026-05-03,4,1,9,week,,dhis2-weekly-export:row-2"
                    ]
                ),
            )
            huge_validate = self.validate_upload(huge_response.data["public_id"])
        self.assertEqual(huge_validate.data["status"], SourceDataUploadBatch.STATUS_VALIDATION_FAILED)
        self.assertTrue(SourceDataValidationIssue.objects.filter(code="row_limit_exceeded").exists())

    def test_duplicate_upload_attempts_are_counted_and_analyst_confirm_is_blocked(self):
        first_response = self.create_upload(filename="duplicate-1.csv")
        second_response = self.create_upload(filename="duplicate-2.csv")
        self.validate_upload(first_response.data["public_id"])
        self.client.force_authenticate(self.analyst)

        confirm_response = self.client.post(
            reverse("source-data-upload-confirm", kwargs={"public_id": first_response.data["public_id"]}),
            {},
            format="json",
        )
        operations_response = self.client.get(reverse("source-data-operations"))

        self.assertEqual(second_response.status_code, status.HTTP_201_CREATED)
        self.assertIsNotNone(second_response.data["duplicate_of_public_id"])
        self.assertEqual(confirm_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertGreaterEqual(operations_response.data["metrics"]["duplicate_attempt_count"], 1)

    def test_feature_flags_gate_source_data_ops_confirm_and_downstream_paths(self):
        self.client.force_authenticate(self.analyst)
        with self.settings(SOURCE_DATA_OPS_ENABLED=False):
            disabled_surface_response = self.client.get(reverse("source-data-feed-types"))

        self.assertEqual(disabled_surface_response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertIn("SOURCE_DATA_OPS_ENABLED", disabled_surface_response.data["disabled_flags"])

        upload_response = self.create_upload(filename="feature-flags.csv")
        self.validate_upload(upload_response.data["public_id"])

        self.client.force_authenticate(self.supervisor)
        with self.settings(SOURCE_DATA_IMPORT_CONFIRM_ENABLED=False):
            disabled_confirm_response = self.client.post(
                reverse("source-data-upload-confirm", kwargs={"public_id": upload_response.data["public_id"]}),
                {},
                format="json",
            )
        with self.settings(SOURCE_DATA_DOWNSTREAM_ACTIONS_ENABLED=False):
            disabled_downstream_response = self.client.post(
                reverse("source-data-upload-downstream-actions", kwargs={"public_id": upload_response.data["public_id"]}),
                {"action_key": "run_source_audits"},
                format="json",
            )

        self.assertEqual(disabled_confirm_response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertIn("SOURCE_DATA_IMPORT_CONFIRM_ENABLED", disabled_confirm_response.data["disabled_flags"])
        self.assertEqual(disabled_downstream_response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertIn("SOURCE_DATA_DOWNSTREAM_ACTIONS_ENABLED", disabled_downstream_response.data["disabled_flags"])
