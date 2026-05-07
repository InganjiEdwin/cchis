import csv
from io import StringIO

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User

from .source_data.registry import source_data_feed_definitions
from .source_data.templates import validate_source_data_template_contract


class SourceDataPhaseOneRegistryTemplateTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="source-data-phase1-admin",
            password="StrongPass123!",
            role=User.ROLE_ADMIN,
        )
        self.analyst = User.objects.create_user(
            username="source-data-phase1-analyst",
            password="StrongPass123!",
            role=User.ROLE_ANALYST,
        )
        self.chv = User.objects.create_user(
            username="source-data-phase1-chv",
            password="StrongPass123!",
            role=User.ROLE_CHV,
        )

    def test_feed_types_expose_every_mvp_feed_and_template_contract(self):
        self.client.force_authenticate(self.analyst)

        response = self.client.get(reverse("source-data-feed-types"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        expected_feed_keys = {definition.feed_key for definition in source_data_feed_definitions()}
        self.assertEqual({feed["feed_key"] for feed in response.data["feeds"]}, expected_feed_keys)
        self.assertEqual(response.data["feed_count"], len(expected_feed_keys))
        self.assertEqual(response.data["template_contract_errors"], [])
        self.assertEqual(validate_source_data_template_contract(), [])

    def test_csv_template_file_is_downloadable_for_every_mvp_feed(self):
        self.client.force_authenticate(self.admin)

        for definition in source_data_feed_definitions():
            response = self.client.get(
                reverse("source-data-template-file", kwargs={"feed_key": definition.feed_key})
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["feed_key"], definition.feed_key)
            self.assertEqual(response.data["content_type"], "text/csv")
            self.assertTrue(response.data["filename"].endswith("_template.csv"))
            self.assertIn("payload_sha256", response.data)
            self.assertIn("\n", response.data["payload"])

    def test_ward_templates_prefill_migori_ward_names_and_codes(self):
        self.client.force_authenticate(self.admin)

        response = self.client.get(
            reverse("source-data-template-file", kwargs={"feed_key": "surveillance_weekly_aggregate"})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["row_count"], 40)
        reader = csv.DictReader(StringIO(response.data["payload"]))
        rows = list(reader)
        self.assertEqual(reader.fieldnames[:2], ["ward_code", "ward_name"])
        self.assertEqual(len(rows), 40)
        self.assertIn(
            {"ward_code": "KE-WARD-1261", "ward_name": "North Kamagambo"},
            [{"ward_code": row["ward_code"], "ward_name": row["ward_name"]} for row in rows],
        )
        self.assertIn(
            {"ward_code": "KE-WARD-1300", "ward_name": "Nyabasi West"},
            [{"ward_code": row["ward_code"], "ward_name": row["ward_name"]} for row in rows],
        )

    def test_facility_templates_show_ward_name_without_creating_fake_facility_rows(self):
        self.client.force_authenticate(self.admin)

        response = self.client.get(
            reverse("source-data-template-file", kwargs={"feed_key": "facility_readiness_snapshot"})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["row_count"], 1)
        reader = csv.DictReader(StringIO(response.data["payload"]))
        row = next(reader)
        self.assertIn("ward_name", reader.fieldnames)
        self.assertEqual(row["ward_name"], "North Kamagambo")

    def test_unsupported_template_feed_key_returns_safe_404(self):
        self.client.force_authenticate(self.admin)

        response = self.client.get(reverse("source-data-template-file", kwargs={"feed_key": "unknown_feed"}))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("detail", response.data)

    def test_chv_cannot_access_registry_or_templates(self):
        self.client.force_authenticate(self.chv)

        registry_response = self.client.get(reverse("source-data-feed-types"))
        template_response = self.client.get(
            reverse("source-data-template-file", kwargs={"feed_key": "surveillance_weekly_aggregate"})
        )

        self.assertEqual(registry_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(template_response.status_code, status.HTTP_403_FORBIDDEN)
