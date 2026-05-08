from datetime import timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User

from .models import (
    ExternalSystem,
    InteroperabilityRun,
    ModelRun,
    OperationalBaselinePeriod,
    OperationalMetricDefinition,
    OperationalMetricSnapshot,
    OperationalSLAThreshold,
    Ward,
)
from .operational_metric_builders import daily_period
from .operational_metrics import sync_operational_metric_catalog


class OperationalMetricDashboardApiTestCase(APITestCase):
    password = "ChangeMe123!"

    def setUp(self):
        sync_operational_metric_catalog()
        self.ward = Ward.objects.create(
            name="Kanyasa",
            county="Migori",
            sub_county="Nyatike",
            ward_code="KNY",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="ops_dashboard_admin",
            password=self.password,
            email="ops-dashboard-admin@example.com",
            role=User.ROLE_ADMIN,
            ward=self.ward,
            is_active=True,
        )
        self.snapshot_date = timezone.localdate() - timedelta(days=1)
        self.period_start, self.period_end = daily_period(self.snapshot_date)
        self.client.force_authenticate(self.user)
        ModelRun.objects.create(
            model_version="risk-model-v1",
            status=ModelRun.STATUS_SUCCESS,
            feature_schema_version="baseline-v1",
            evaluation_metrics={"auc": 0.81},
            completed_at=self.period_end,
        )

    def _definition(self, metric_key: str):
        return OperationalMetricDefinition.objects.get(metric_key=metric_key, version="v1")

    def _snapshot(self, metric_key: str, **kwargs):
        definition = self._definition(metric_key)
        defaults = {
            "metric_definition": definition,
            "date": self.snapshot_date,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "grain": OperationalMetricSnapshot.GRAIN_DAILY,
            "value": Decimal("100.000000"),
            "numerator": Decimal("1.000000"),
            "denominator": Decimal("1.000000"),
            "status": OperationalMetricSnapshot.STATUS_COMPLETE,
            "source_record_count": 1,
            "source_coverage": {
                "schema_version": "operational-kpi-source-coverage-v1",
                "warnings": [],
                "details": {},
            },
            "dimension_values": {"scope": "global"},
        }
        defaults.update(kwargs)
        return OperationalMetricSnapshot.objects.create(**defaults)

    def test_dashboard_contract_separates_operational_kpis_from_model_metrics(self):
        self._snapshot(
            "alert_delivery_time_p95_seconds",
            value=Decimal("240.000000"),
            source_channel="SMS",
        )
        self._snapshot(
            "ussd_completion_rate",
            value=Decimal("75.000000"),
            source_channel="USSD",
        )
        OperationalSLAThreshold.objects.create(
            threshold_key="dashboard-alert-p95",
            metric_definition=self._definition("alert_delivery_time_p95_seconds"),
            display_name="Alert delivery p95",
            comparator=OperationalSLAThreshold.COMPARATOR_LTE,
            target_value=Decimal("300.000000"),
            owner="County EOC operations",
            rationale="Alerts should reach operators inside five minutes.",
        )

        response = self.client.get(
            reverse("operational-kpi-dashboard"),
            {
                "date_from": self.snapshot_date.isoformat(),
                "date_to": self.snapshot_date.isoformat(),
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["schema_version"], "operational-kpi-dashboard-v1")
        self.assertEqual(response.data["filters"]["date_from"], self.snapshot_date.isoformat())
        self.assertIn("operational_overview", response.data["panels"])
        self.assertIn("response_time_trends", response.data["panels"])
        self.assertIn("facility_preparedness_trends", response.data["panels"])
        self.assertIn("ussd_completion_trends", response.data["panels"])
        self.assertEqual(response.data["panels"]["model_vs_operations"]["operational_metric_family"], "OPERATIONAL")
        self.assertEqual(response.data["summary"]["model_metric_count"], 0)
        self.assertTrue(all(item["metric_family"] == "OPERATIONAL" for item in response.data["metrics"]))

        sla_items = {item["metric_key"]: item for item in response.data["panels"]["sla"]}
        self.assertEqual(sla_items["alert_delivery_time_p95_seconds"]["sla"]["status"], "pass")
        self.assertEqual(sla_items["alert_delivery_time_p95_seconds"]["display_value"], "4.0 min")

    def test_dashboard_filters_and_source_warnings_are_visible(self):
        self._snapshot(
            "source_data_freshness_pass_rate",
            value=None,
            status=OperationalMetricSnapshot.STATUS_PARTIAL,
            source_record_count=1,
            source_coverage={
                "schema_version": "operational-kpi-source-coverage-v1",
                "warnings": ["rainfall_ingestion_missing_stale_or_not_successful"],
                "details": {},
            },
        )
        self._snapshot(
            "alerts_delivered_under_5m_pct",
            value=Decimal("100.000000"),
            ward=self.ward,
            county=self.ward.county,
            sub_county=self.ward.sub_county,
            source_channel="SMS",
        )

        response = self.client.get(
            reverse("operational-kpi-dashboard"),
            {
                "date_from": self.snapshot_date.isoformat(),
                "date_to": self.snapshot_date.isoformat(),
                "ward_id": self.ward.id,
                "sub_county": self.ward.sub_county,
                "source_channel": "SMS",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["filters"]["ward_id"], self.ward.id)
        self.assertEqual(response.data["filters"]["sub_county"], self.ward.sub_county)
        self.assertEqual(response.data["filters"]["source_channel"], "SMS")
        self.assertEqual(response.data["summary"]["snapshot_count"], 1)
        self.assertEqual(response.data["panels"]["operational_overview"][0]["metric_key"], "alerts_delivered_under_5m_pct")
        scoped_warning_codes = {
            warning["warning"]
            for warning in response.data["panels"]["source_coverage_warnings"]
        }
        self.assertNotIn("rainfall_ingestion_missing_stale_or_not_successful", scoped_warning_codes)

        unfiltered_response = self.client.get(
            reverse("operational-kpi-dashboard"),
            {
                "date_from": self.snapshot_date.isoformat(),
                "date_to": self.snapshot_date.isoformat(),
            },
        )
        warning_codes = {
            warning["warning"]
            for warning in unfiltered_response.data["panels"]["source_coverage_warnings"]
        }
        self.assertIn("rainfall_ingestion_missing_stale_or_not_successful", warning_codes)

    def test_supervisor_dashboard_is_forced_to_assigned_ward_and_rejects_peer_ward(self):
        other_ward = Ward.objects.create(
            name="Suna Central",
            county="Migori",
            sub_county="Suna East",
            ward_code="SCT",
            is_active=True,
        )
        supervisor = User.objects.create_user(
            username="ops_dashboard_supervisor",
            password=self.password,
            email="ops-dashboard-supervisor@example.com",
            role=User.ROLE_SUPERVISOR,
            ward=self.ward,
            is_active=True,
        )
        self._snapshot(
            "alerts_delivered_under_5m_pct",
            value=Decimal("91.000000"),
            ward=self.ward,
            county=self.ward.county,
            sub_county=self.ward.sub_county,
        )
        self._snapshot(
            "alerts_delivered_under_5m_pct",
            value=Decimal("12.000000"),
            ward=other_ward,
            county=other_ward.county,
            sub_county=other_ward.sub_county,
        )

        self.client.force_authenticate(supervisor)
        response = self.client.get(
            reverse("operational-kpi-dashboard"),
            {
                "date_from": self.snapshot_date.isoformat(),
                "date_to": self.snapshot_date.isoformat(),
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["filters"]["ward_id"], self.ward.id)
        self.assertEqual(response.data["filters"]["sub_county"], self.ward.sub_county)
        self.assertEqual(response.data["summary"]["snapshot_count"], 1)
        metric = next(
            item
            for item in response.data["metrics"]
            if item["metric_key"] == "alerts_delivered_under_5m_pct"
        )
        self.assertEqual(metric["value"], 91.0)
        self.assertEqual(
            [ward["id"] for ward in response.data["available_filters"]["wards"]],
            [self.ward.id],
        )

        blocked_response = self.client.get(
            reverse("operational-kpi-dashboard"),
            {
                "date_from": self.snapshot_date.isoformat(),
                "date_to": self.snapshot_date.isoformat(),
                "ward_id": other_ward.id,
            },
        )
        self.assertEqual(blocked_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_dashboard_feeds_interoperability_mapping_coverage_warnings(self):
        system = ExternalSystem.objects.create(
            system_key="dhis2",
            display_name="DHIS2",
            system_type=ExternalSystem.SYSTEM_DHIS2,
            owner="health_information_officer",
        )
        run = InteroperabilityRun.objects.create(
            direction=InteroperabilityRun.DIRECTION_EXPORT,
            exchange_type=InteroperabilityRun.EXCHANGE_AGGREGATE_REPORT_EXPORT,
            system=system,
            status=InteroperabilityRun.STATUS_PARTIAL,
            records_seen=4,
            records_accepted=3,
            records_rejected=1,
            mapping_coverage=75.0,
            error_summary="1 export issue requires review.",
            operator=self.user,
        )

        response = self.client.get(
            reverse("operational-kpi-dashboard"),
            {
                "date_from": self.snapshot_date.isoformat(),
                "date_to": self.snapshot_date.isoformat(),
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        panel = response.data["panels"]["interoperability_contracts"]
        self.assertEqual(panel["schema_version"], "interoperability-operational-kpi-feed-v1")
        self.assertEqual(panel["latest_mapping_coverage"], 75.0)
        self.assertEqual(panel["latest_run"]["public_id"], str(run.public_id))
        warning_codes = {
            warning["warning"]
            for warning in response.data["panels"]["source_coverage_warnings"]
        }
        self.assertIn("latest_interoperability_run_not_clean", warning_codes)

    def test_dashboard_surfaces_threshold_alert_panel(self):
        self._snapshot("overdue_action_count", value=Decimal("6.000000"))

        response = self.client.get(
            reverse("operational-kpi-dashboard"),
            {
                "date_from": self.snapshot_date.isoformat(),
                "date_to": self.snapshot_date.isoformat(),
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(response.data["summary"]["critical_threshold_alert_count"], 1)
        alerts = {
            item["metric_key"]: item
            for item in response.data["panels"]["threshold_alerts"]
        }
        self.assertEqual(alerts["overdue_action_count"]["severity"], "CRITICAL")
        self.assertEqual(alerts["overdue_action_count"]["threshold"]["threshold_key"], "overdue-action-backlog-empty")

    def test_dashboard_baseline_and_sla_respect_snapshot_dimensions(self):
        other_ward = Ward.objects.create(
            name="North Kadem",
            county="Migori",
            sub_county="Nyatike",
            ward_code="NKD",
            is_active=True,
        )
        snapshot = self._snapshot(
            "alert_delivery_time_p95_seconds",
            value=Decimal("120.000000"),
            ward=self.ward,
            county=self.ward.county,
            sub_county=self.ward.sub_county,
            source_channel="SMS",
        )
        definition = snapshot.metric_definition
        OperationalBaselinePeriod.objects.create(
            metric_definition=definition,
            name="Newer global baseline",
            period_start=self.period_start - timedelta(days=30),
            period_end=self.period_start - timedelta(days=1),
            baseline_value=Decimal("90.000000"),
            source_snapshot_count=1,
            source_snapshot_keys=["global-baseline-source"],
            dimensions={},
            owner="M&E lead",
        )
        matching_baseline = OperationalBaselinePeriod.objects.create(
            metric_definition=definition,
            name="Ward SMS baseline",
            period_start=self.period_start - timedelta(days=40),
            period_end=self.period_start - timedelta(days=10),
            baseline_value=Decimal("60.000000"),
            source_snapshot_count=1,
            source_snapshot_keys=["ward-sms-baseline-source"],
            dimensions={"ward_id": self.ward.id, "source_channel": "SMS"},
            owner="M&E lead",
        )
        OperationalSLAThreshold.objects.create(
            threshold_key="ward-alert-p95",
            metric_definition=definition,
            display_name="Ward alert delivery p95",
            comparator=OperationalSLAThreshold.COMPARATOR_LTE,
            target_value=Decimal("300.000000"),
            applies_to_dimensions={"ward_id": self.ward.id, "source_channel": "SMS"},
            owner="County EOC operations",
            rationale="Ward-scoped alert delivery target.",
        )
        OperationalSLAThreshold.objects.create(
            threshold_key="other-ward-alert-p95",
            metric_definition=definition,
            display_name="Other ward alert delivery p95",
            comparator=OperationalSLAThreshold.COMPARATOR_LTE,
            target_value=Decimal("10.000000"),
            applies_to_dimensions={"ward_id": other_ward.id, "source_channel": "SMS"},
            owner="County EOC operations",
            rationale="Other ward target should not apply here.",
        )

        response = self.client.get(
            reverse("operational-kpi-dashboard"),
            {
                "date_from": self.snapshot_date.isoformat(),
                "date_to": self.snapshot_date.isoformat(),
                "ward_id": self.ward.id,
                "source_channel": "SMS",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        metric = next(
            item
            for item in response.data["metrics"]
            if item["metric_key"] == "alert_delivery_time_p95_seconds"
        )
        self.assertEqual(metric["baseline"]["status"], "compared")
        self.assertEqual(metric["baseline"]["baseline"]["baseline_key"], matching_baseline.baseline_key)
        self.assertEqual(metric["baseline"]["baseline"]["baseline_value"], 60.0)
        self.assertEqual(metric["sla"]["status"], "pass")
        self.assertEqual(metric["sla"]["threshold"]["threshold_key"], "ward-alert-p95")

    def test_dashboard_rejects_invalid_date_ranges(self):
        response = self.client.get(
            reverse("operational-kpi-dashboard"),
            {
                "date_from": self.snapshot_date.isoformat(),
                "date_to": (self.snapshot_date - timedelta(days=1)).isoformat(),
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
