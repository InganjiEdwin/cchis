from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User

from .models import IngestionRun, SourceDataUploadBatch, SurveillanceIngestionRun, SurveillanceSource


class SourceDataPhaseFourFreshnessOverviewTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="source-data-phase4-admin",
            password="StrongPass123!",
            role=User.ROLE_ADMIN,
        )
        self.analyst = User.objects.create_user(
            username="source-data-phase4-analyst",
            password="StrongPass123!",
            role=User.ROLE_ANALYST,
        )
        self.chv = User.objects.create_user(
            username="source-data-phase4-chv",
            password="StrongPass123!",
            role=User.ROLE_CHV,
        )

    def test_overview_exposes_feed_freshness_gaps_and_recent_imports_without_row_data(self):
        source_timestamp = timezone.now() - timedelta(days=2)
        IngestionRun.objects.create(
            run_type=IngestionRun.RUN_TYPE_RAINFALL,
            status=IngestionRun.STATUS_SUCCESS,
            source_kind=IngestionRun.SOURCE_KIND_LIVE,
            source_name="Open-Meteo",
            source_timestamp=source_timestamp,
            freshness_state=IngestionRun.FRESHNESS_FRESH,
            records_loaded=40,
            completed_at=timezone.now(),
        )
        SourceDataUploadBatch.objects.create(
            feed_key="surveillance_weekly_aggregate",
            domain="health_surveillance",
            source_type="weekly_aggregate",
            source_name="Migori DHIS2 weekly export",
            source_timestamp=source_timestamp,
            reporting_period_start=source_timestamp.date() - timedelta(days=7),
            reporting_period_end=source_timestamp.date(),
            status=SourceDataUploadBatch.STATUS_IMPORTED,
            validation_status=SourceDataUploadBatch.VALIDATION_PASSED,
            import_status=SourceDataUploadBatch.IMPORT_IMPORTED,
            row_count=1,
            accepted_count=1,
            confirmed_by=self.admin,
            confirmed_at=timezone.now(),
            created_by=self.admin,
        )

        self.client.force_authenticate(self.analyst)
        response = self.client.get(reverse("source-data-overview"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["schema_version"], "source-data-overview-v1")
        self.assertEqual(response.data["source_matrix_reference"], "docs/CCHIS_DATA_SOURCE_FEEDS.md")
        feed_statuses = {item["feed_key"]: item for item in response.data["feed_statuses"]}
        self.assertEqual(feed_statuses["surveillance_weekly_aggregate"]["status"], "current")
        self.assertEqual(feed_statuses["surveillance_weekly_aggregate"]["truth_state"], "csv_backed")
        self.assertIn("facility_readiness_snapshot", {gap["feed_key"] for gap in response.data["source_gaps"]})
        self.assertEqual(response.data["recent_uploads"][0]["source_name"], "Migori DHIS2 weekly export")
        self.assertNotIn("validation_issues", response.data["recent_uploads"][0])
        self.assertNotIn("artifacts", response.data["recent_uploads"][0])

    def test_freshness_is_lightweight_and_restricted_to_source_data_roles(self):
        self.client.force_authenticate(self.analyst)
        response = self.client.get(reverse("source-data-freshness"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["schema_version"], "source-data-freshness-v1")
        self.assertGreaterEqual(len(response.data["sources"]), 1)
        self.assertIn("state_counts", response.data)
        self.assertIn("truth_state_counts", response.data)

        self.client.force_authenticate(self.chv)
        forbidden_response = self.client.get(reverse("source-data-freshness"))
        self.assertEqual(forbidden_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_freshness_marks_domain_csv_ingestion_as_csv_backed_without_dashboard_upload(self):
        source_timestamp = timezone.now() - timedelta(days=2)
        source = SurveillanceSource.objects.create(
            source_name="CLI weekly surveillance import",
            source_type=SurveillanceSource.SOURCE_TYPE_WEEKLY_AGGREGATE,
            source_timestamp=source_timestamp,
            reporting_period_start=source_timestamp.date() - timedelta(days=7),
            reporting_period_end=source_timestamp.date(),
        )
        SurveillanceIngestionRun.objects.create(
            source=source,
            status=SurveillanceIngestionRun.STATUS_SUCCESS,
            source_name="CLI weekly surveillance import",
            source_type=SurveillanceSource.SOURCE_TYPE_WEEKLY_AGGREGATE,
            source_timestamp=source_timestamp,
            reporting_period_start=source_timestamp.date() - timedelta(days=7),
            reporting_period_end=source_timestamp.date(),
            completed_at=timezone.now(),
        )

        self.client.force_authenticate(self.analyst)
        response = self.client.get(reverse("source-data-freshness"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        feed_sources = {item["feed_key"]: item for item in response.data["sources"] if item["feed_key"]}
        weekly = feed_sources["surveillance_weekly_aggregate"]
        self.assertEqual(weekly["status"], "current")
        self.assertEqual(weekly["truth_state"], "csv_backed")
        self.assertEqual(weekly["source_path"], "csv_upload")
