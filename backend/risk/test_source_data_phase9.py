from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import StepUpGrant, User

from .models import PopulationExposureSource, SourceDataConnectorRun, SourceDataFeedModeOverride, SourceDataUploadBatch, Ward
from .source_data.connectors import source_data_csv_upload_enabled
from .test_step_up_utils import force_authenticate_with_step_up


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

    def worldpop_csv(self) -> str:
        return "\n".join(
            [
                "ward_code,ward_name,population_total,population_density,gridded_population_value,aggregation_method,spatial_resolution,unit,truth_class,source_kind,freshness_state,source_ref,notes",
                (
                    "MIG-WARD-001,North Kamagambo,24500,412.5,24500,"
                    "ward_sum_from_worldpop_100m_grid_pixel_centers,100m,people_per_km2,"
                    "spatially_aggregated_source,live,fresh,"
                    "https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/2026/KEN/v1/100m/constrained/ken_pop_2026_CN_100m_R2025A_v1.tif,"
                    "WorldPop test; polygon_sha256=5554c913ff082f7cc2536c772a9190ca81d3b1a7370d872800ff540ce40f6997; pixel-center aggregation."
                ),
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

    def test_worldpop_connector_targets_gridded_population_feed(self):
        self.client.force_authenticate(self.analyst)

        response = self.client.get(reverse("source-data-feed-types"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        gridded_feed = next(item for item in response.data["feeds"] if item["feed_key"] == "gridded_population")
        population_feed = next(item for item in response.data["feeds"] if item["feed_key"] == "population_baseline")
        self.assertEqual(gridded_feed["connector_status"]["connector_key"], "worldpop_knbs_population")
        self.assertEqual(gridded_feed["connector_status"]["required_settings"], [
            "SOURCE_DATA_WORLDPOP_KNBS_SOURCE_URL",
            "SOURCE_DATA_WORLDPOP_KNBS_RELEASE_VERSION",
        ])
        self.assertEqual(population_feed["connector_status"]["connector_key"], "")

    def test_connector_refresh_creates_validated_upload_with_same_canonical_checks(self):
        self.write_connector_fixture("dhis2_surveillance_weekly", self.weekly_csv())
        force_authenticate_with_step_up(self.client, self.admin, StepUpGrant.PURPOSE_SOURCE_DATA)

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

    def test_worldpop_connector_refresh_uses_generated_migori_fixture_alias(self):
        self.write_connector_fixture("migori_worldpop_2026_population", self.worldpop_csv())
        force_authenticate_with_step_up(self.client, self.admin, StepUpGrant.PURPOSE_SOURCE_DATA)

        with self.settings(
            SOURCE_DATA_WORLDPOP_KNBS_SOURCE_URL=(
                "https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/2026/KEN/v1/100m/constrained/"
                "ken_pop_2026_CN_100m_R2025A_v1.tif"
            ),
            SOURCE_DATA_WORLDPOP_KNBS_RELEASE_VERSION="WorldPop G2_CN_POP_R25A_100m KEN 2026 v1",
        ):
            response = self.client.post(
                reverse("source-data-connector-refresh", kwargs={"connector_key": "worldpop_knbs_population"}),
                {"options": {"source_timestamp": "2025-09-01T00:00:00Z"}},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], SourceDataConnectorRun.STATUS_SUCCESS)
        self.assertEqual(response.data["target_feed_key"], "gridded_population")
        self.assertEqual(response.data["fetched_record_count"], 1)
        self.assertEqual(response.data["safe_metadata"]["fixture_filename"], "migori_worldpop_2026_population.csv")
        upload = SourceDataUploadBatch.objects.get(public_id=response.data["upload_batch_public_id"])
        self.assertEqual(upload.feed_key, "gridded_population")
        self.assertEqual(upload.source_type, PopulationExposureSource.SOURCE_TYPE_GRIDDED_POPULATION)
        self.assertEqual(upload.validation_status, SourceDataUploadBatch.VALIDATION_PASSED)
        self.assertEqual(upload.row_count, 1)
        self.assertEqual(upload.accepted_count, 1)
        self.assertEqual(upload.metadata["source_data_connector"]["connector_key"], "worldpop_knbs_population")

    def test_connector_failure_is_audited_and_uses_validation_diagnostics(self):
        self.write_connector_fixture("dhis2_surveillance_weekly", self.weekly_csv(notes="call +254712345678"))
        force_authenticate_with_step_up(self.client, self.admin, StepUpGrant.PURPOSE_SOURCE_DATA)

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

    def test_connector_refresh_options_use_same_pii_safe_metadata_guard(self):
        self.write_connector_fixture("dhis2_surveillance_weekly", self.weekly_csv())
        force_authenticate_with_step_up(self.client, self.admin, StepUpGrant.PURPOSE_SOURCE_DATA)

        response = self.client.post(
            reverse("source-data-connector-refresh", kwargs={"connector_key": "dhis2_surveillance_weekly"}),
            {
                "options": {
                    "source_name": "Patient name Jane Doe",
                    "reporting_period_start": "2026-04-27",
                    "reporting_period_end": "2026-05-03",
                }
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("direct identifiers", str(response.data).lower())
        self.assertEqual(SourceDataUploadBatch.objects.count(), 0)

    def test_admin_can_disable_csv_when_api_connector_is_authoritative(self):
        self.write_connector_fixture("dhis2_surveillance_weekly", self.weekly_csv())
        force_authenticate_with_step_up(self.client, self.admin, StepUpGrant.PURPOSE_SOURCE_DATA)

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

        force_authenticate_with_step_up(self.client, self.supervisor, StepUpGrant.PURPOSE_SOURCE_DATA)
        upload_response = self.client.post(
            reverse("source-data-upload-list-create"),
            self.upload_payload(),
            format="multipart",
        )

        self.assertEqual(upload_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("CSV uploads are disabled", str(upload_response.data))

    def test_connector_registry_is_readable_but_refresh_is_restricted_to_admin(self):
        self.client.force_authenticate(self.analyst)

        registry_response = self.client.get(reverse("source-data-connectors"))
        analyst_refresh_response = self.client.post(
            reverse("source-data-connector-refresh", kwargs={"connector_key": "dhis2_surveillance_weekly"}),
            {},
            format="json",
        )
        force_authenticate_with_step_up(self.client, self.supervisor, StepUpGrant.PURPOSE_SOURCE_DATA)
        supervisor_refresh_response = self.client.post(
            reverse("source-data-connector-refresh", kwargs={"connector_key": "dhis2_surveillance_weekly"}),
            {},
            format="json",
        )

        self.assertEqual(registry_response.status_code, status.HTTP_200_OK)
        self.assertEqual(registry_response.data["schema_version"], "source-data-connector-registry-v1")
        self.assertEqual(analyst_refresh_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(supervisor_refresh_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_api_connector_flag_gates_connector_surface_and_restores_csv_fallback(self):
        SourceDataFeedModeOverride.objects.create(
            feed_key="surveillance_weekly_aggregate",
            feed_mode=SourceDataFeedModeOverride.MODE_API,
            csv_upload_enabled=False,
            authoritative_connector_key="dhis2_surveillance_weekly",
            reason="Connector is normally authoritative.",
            updated_by=self.admin,
        )
        force_authenticate_with_step_up(self.client, self.admin, StepUpGrant.PURPOSE_SOURCE_DATA)

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
