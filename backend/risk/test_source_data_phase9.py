from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User

from .models import SourceDataConnectorRun, SourceDataFeedModeOverride, SourceDataUploadBatch, Ward
from .source_data.connectors import source_data_csv_upload_enabled


class SourceDataPhaseNineConnectorIntegrationTests(APITestCase):
    def setUp(self):
        self.upload_root = TemporaryDirectory()
        self.fixture_root = TemporaryDirectory()
        self.addCleanup(self.upload_root.cleanup)
        self.addCleanup(self.fixture_root.cleanup)
        self.settings_override = override_settings(
            SOURCE_DATA_UPLOAD_ROOT=Path(self.upload_root.name),
            SOURCE_DATA_CONNECTOR_FIXTURE_DIR=Path(self.fixture_root.name),
            SOURCE_DATA_MAX_UPLOAD_SIZE_BYTES=1024 * 1024,
            SOURCE_DATA_MAX_UPLOAD_ROWS=20,
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

        self.ward = Ward.objects.create(
            name="North Kamagambo",
            county="Migori",
            ward_code="MIG-WARD-001",
        )
        self.admin = User.objects.create_user(
            username="source-data-phase9-admin",
            password="StrongPass123!",
            role=User.ROLE_ADMIN,
        )
        self.supervisor = User.objects.create_user(
            username="source-data-phase9-supervisor",
            password="StrongPass123!",
            role=User.ROLE_SUPERVISOR,
        )
        self.analyst = User.objects.create_user(
            username="source-data-phase9-analyst",
            password="StrongPass123!",
            role=User.ROLE_ANALYST,
        )

    def weekly_csv(self, *, notes: str = "") -> str:
        return "\n".join(
            [
                "ward_code,reporting_period_start,reporting_period_end,suspected_cases,confirmed_cases,diarrheal_count,reporting_granularity,notes,source_ref",
                f"MIG-WARD-001,2026-04-27,2026-05-03,3,1,8,week,{notes},dhis2-api:row-1",
            ]
        )

    def write_connector_fixture(self, connector_key: str, payload: str):
        Path(self.fixture_root.name, f"{connector_key}.csv").write_text(payload, encoding="utf-8")

    def upload_payload(self):
        return {
            "feed_key": "surveillance_weekly_aggregate",
            "source_name": "Migori DHIS2 weekly export",
            "source_timestamp": "2026-05-05T08:00:00Z",
            "reporting_period_start": "2026-04-27",
            "reporting_period_end": "2026-05-03",
            "file": SimpleUploadedFile(
                "weekly.csv",
                self.weekly_csv().encode("utf-8"),
                content_type="text/csv",
            ),
        }

    def test_feed_registry_exposes_connector_status_without_secret_values(self):
        self.client.force_authenticate(self.analyst)

        response = self.client.get(reverse("source-data-feed-types"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        surveillance_feed = next(
            item for item in response.data["feeds"] if item["feed_key"] == "surveillance_weekly_aggregate"
        )
        connector_status = surveillance_feed["connector_status"]
        self.assertEqual(surveillance_feed["feed_mode"], "csv")
        self.assertEqual(connector_status["connector_key"], "dhis2_surveillance_weekly")
        self.assertIn("SOURCE_DATA_DHIS2_PASSWORD", connector_status["required_settings"])
        self.assertFalse(connector_status["credential_values_exposed"])
        self.assertNotIn("password", str(connector_status).lower().replace("source_data_dhis2_password", ""))

    def test_connector_refresh_creates_validated_upload_with_same_canonical_checks(self):
        self.write_connector_fixture("dhis2_surveillance_weekly", self.weekly_csv())
        self.client.force_authenticate(self.supervisor)

        response = self.client.post(
            reverse("source-data-connector-refresh", kwargs={"connector_key": "dhis2_surveillance_weekly"}),
            {
                "options": {
                    "reporting_period_start": "2026-04-27",
                    "reporting_period_end": "2026-05-03",
                    "source_timestamp": "2026-05-05T08:00:00Z",
                }
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], SourceDataConnectorRun.STATUS_SUCCESS)
        self.assertEqual(response.data["fetched_record_count"], 1)
        self.assertFalse(response.data["safe_metadata"]["credential_values_exposed"])
        upload = SourceDataUploadBatch.objects.get(public_id=response.data["upload_batch_public_id"])
        self.assertEqual(upload.validation_status, SourceDataUploadBatch.VALIDATION_PASSED)
        self.assertEqual(upload.metadata["source_data_connector"]["connector_key"], "dhis2_surveillance_weekly")

    def test_connector_failure_is_audited_and_uses_validation_diagnostics(self):
        self.write_connector_fixture("dhis2_surveillance_weekly", self.weekly_csv(notes="call +254712345678"))
        self.client.force_authenticate(self.supervisor)

        response = self.client.post(
            reverse("source-data-connector-refresh", kwargs={"connector_key": "dhis2_surveillance_weekly"}),
            {"options": {"reporting_period_start": "2026-04-27", "reporting_period_end": "2026-05-03"}},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["status"], SourceDataConnectorRun.STATUS_FAILED)
        self.assertEqual(response.data["error_summary"], "Connector payload failed canonical source-data validation.")
        self.assertFalse(response.data["safe_metadata"]["credential_values_exposed"])
        upload = SourceDataUploadBatch.objects.get(public_id=response.data["upload_batch_public_id"])
        self.assertEqual(upload.validation_status, SourceDataUploadBatch.VALIDATION_FAILED)
        self.assertTrue(upload.validation_issues.filter(code="pii_phone_value_detected").exists())

    def test_admin_can_disable_csv_when_api_connector_is_authoritative(self):
        self.write_connector_fixture("dhis2_surveillance_weekly", self.weekly_csv())
        self.client.force_authenticate(self.admin)

        mode_response = self.client.post(
            reverse("source-data-feed-mode", kwargs={"feed_key": "surveillance_weekly_aggregate"}),
            {
                "feed_mode": "api",
                "csv_upload_enabled": False,
                "authoritative_connector_key": "dhis2_surveillance_weekly",
                "reason": "DHIS2 connector is authoritative for routine weekly refresh.",
            },
            format="json",
        )

        self.assertEqual(mode_response.status_code, status.HTTP_200_OK)
        self.assertFalse(mode_response.data["csv_upload_enabled"])
        self.assertTrue(SourceDataFeedModeOverride.objects.filter(feed_key="surveillance_weekly_aggregate").exists())

        self.client.force_authenticate(self.supervisor)
        upload_response = self.client.post(
            reverse("source-data-upload-list-create"),
            self.upload_payload(),
            format="multipart",
        )

        self.assertEqual(upload_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("CSV uploads are disabled", str(upload_response.data))

    def test_connector_registry_is_readable_but_refresh_is_restricted(self):
        self.client.force_authenticate(self.analyst)

        registry_response = self.client.get(reverse("source-data-connectors"))
        refresh_response = self.client.post(
            reverse("source-data-connector-refresh", kwargs={"connector_key": "dhis2_surveillance_weekly"}),
            {},
            format="json",
        )

        self.assertEqual(registry_response.status_code, status.HTTP_200_OK)
        self.assertEqual(registry_response.data["schema_version"], "source-data-connector-registry-v1")
        self.assertEqual(refresh_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_api_connector_flag_gates_connector_surface_and_restores_csv_fallback(self):
        SourceDataFeedModeOverride.objects.create(
            feed_key="surveillance_weekly_aggregate",
            feed_mode=SourceDataFeedModeOverride.MODE_API,
            csv_upload_enabled=False,
            authoritative_connector_key="dhis2_surveillance_weekly",
            reason="Connector is normally authoritative.",
            updated_by=self.admin,
        )
        self.client.force_authenticate(self.admin)

        with self.settings(SOURCE_DATA_API_CONNECTORS_ENABLED=False):
            registry_response = self.client.get(reverse("source-data-connectors"))
            refresh_response = self.client.post(
                reverse("source-data-connector-refresh", kwargs={"connector_key": "dhis2_surveillance_weekly"}),
                {},
                format="json",
            )
            feed_mode_response = self.client.post(
                reverse("source-data-feed-mode", kwargs={"feed_key": "surveillance_weekly_aggregate"}),
                {
                    "feed_mode": "api",
                    "csv_upload_enabled": False,
                    "authoritative_connector_key": "dhis2_surveillance_weekly",
                    "reason": "Should be blocked while API connectors are disabled.",
                },
                format="json",
            )
            csv_enabled = source_data_csv_upload_enabled("surveillance_weekly_aggregate")

        self.assertEqual(registry_response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertIn("SOURCE_DATA_API_CONNECTORS_ENABLED", registry_response.data["disabled_flags"])
        self.assertEqual(refresh_response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(feed_mode_response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertTrue(csv_enabled)

    def test_celery_schedule_includes_dhis2_connector_refresh(self):
        schedule = settings.CELERY_BEAT_SCHEDULE["source-data-connector-dhis2_surveillance_weekly-refresh"]

        self.assertEqual(schedule["task"], "risk.tasks.run_source_data_connector_refresh_task")
        self.assertEqual(schedule["kwargs"]["connector_key"], "dhis2_surveillance_weekly")
        self.assertEqual(schedule["kwargs"]["options"]["execution_mode"], "scheduled")
