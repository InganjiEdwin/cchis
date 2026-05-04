from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from .models import (
    DashboardNotification,
    OperationalMetricDefinition,
    OperationalMetricSnapshot,
    OperationalSLAThreshold,
    OperationalThresholdBreach,
    Ward,
)
from .operational_metric_builders import daily_period
from .operational_metric_thresholds import (
    DEFAULT_OPERATIONAL_SLA_THRESHOLDS,
    evaluate_operational_kpi_thresholds,
    sync_operational_sla_threshold_catalog,
)
from .operational_metrics import sync_operational_metric_catalog


class OperationalMetricThresholdTestCase(TestCase):
    def setUp(self):
        sync_operational_metric_catalog()
        self.ward = Ward.objects.create(
            name="Kaler",
            county="Migori",
            sub_county="Nyatike",
            ward_code="KLR",
            is_active=True,
        )
        self.snapshot_date = timezone.localdate() - timedelta(days=1)
        self.period_start, self.period_end = daily_period(self.snapshot_date)

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

    def test_threshold_catalog_creates_versioned_default_thresholds(self):
        result = sync_operational_sla_threshold_catalog()

        self.assertGreaterEqual(result["synced"], 7)
        threshold = OperationalSLAThreshold.objects.get(threshold_key="alert-delivery-p95-under-5m", version="v1")
        self.assertEqual(threshold.metric_definition.metric_key, "alert_delivery_time_p95_seconds")
        self.assertEqual(threshold.comparator, OperationalSLAThreshold.COMPARATOR_LTE)
        self.assertEqual(threshold.target_value, Decimal("300.000000"))
        self.assertEqual(threshold.metadata["schema_version"], "operational-kpi-threshold-catalog-v1")

    def test_threshold_catalog_handles_new_active_version_without_unique_collision(self):
        sync_operational_sla_threshold_catalog()
        upgraded_specs = [dict(item) for item in DEFAULT_OPERATIONAL_SLA_THRESHOLDS]
        upgraded_specs[0] = {
            **upgraded_specs[0],
            "version": "v2",
            "display_name": f"{upgraded_specs[0]['display_name']} v2",
        }

        with patch("risk.operational_metric_thresholds.DEFAULT_OPERATIONAL_SLA_THRESHOLDS", upgraded_specs):
            sync_operational_sla_threshold_catalog()

        threshold_key = upgraded_specs[0]["threshold_key"]
        self.assertTrue(OperationalSLAThreshold.objects.get(threshold_key=threshold_key, version="v2").is_active)
        retired = OperationalSLAThreshold.objects.get(threshold_key=threshold_key, version="v1")
        self.assertFalse(retired.is_active)
        self.assertIsNotNone(retired.effective_to)

    def test_evaluation_persists_threshold_breach_and_resolves_when_value_recovers(self):
        snapshot = self._snapshot("alert_delivery_time_p95_seconds", value=Decimal("650.000000"))

        first = evaluate_operational_kpi_thresholds(as_of_date=self.snapshot_date, persist=True)

        alert_breaches = [
            item for item in first["breaches"] if item["metric_key"] == "alert_delivery_time_p95_seconds"
        ]
        self.assertTrue(any(item["severity"] == OperationalThresholdBreach.SEVERITY_CRITICAL for item in alert_breaches))
        breach = OperationalThresholdBreach.objects.get(
            metric_definition=snapshot.metric_definition,
            breach_type=OperationalThresholdBreach.BREACH_THRESHOLD_BREACH,
            status=OperationalThresholdBreach.STATUS_ACTIVE,
        )
        self.assertEqual(breach.snapshot, snapshot)
        self.assertEqual(breach.threshold_key_snapshot, "alert-delivery-p95-under-5m")
        self.assertEqual(breach.observed_value, Decimal("650.000000"))

        snapshot.value = Decimal("120.000000")
        snapshot.save(update_fields=["value", "updated_at"])
        second = evaluate_operational_kpi_thresholds(as_of_date=self.snapshot_date, persist=True)

        breach.refresh_from_db()
        self.assertEqual(breach.status, OperationalThresholdBreach.STATUS_RESOLVED)
        self.assertGreaterEqual(second["resolved"], 1)

    def test_source_warning_breaches_are_visible_and_attributed(self):
        snapshot = self._snapshot(
            "chv_active_use_rate",
            value=Decimal("80.000000"),
            status=OperationalMetricSnapshot.STATUS_PARTIAL,
            source_coverage={
                "schema_version": "operational-kpi-source-coverage-v1",
                "warnings": ["chv_sync_stale"],
                "details": {"active_chvs": 4, "active_phones_with_sync": 0},
            },
        )

        result = evaluate_operational_kpi_thresholds(as_of_date=self.snapshot_date, persist=False)

        source_breach = next(
            item for item in result["breaches"] if item["metric_key"] == "chv_active_use_rate" and item["warning_code"] == "chv_sync_stale"
        )
        self.assertEqual(source_breach["breach_type"], OperationalThresholdBreach.BREACH_SOURCE_WARNING)
        self.assertEqual(source_breach["attribution"]["snapshot_key"], snapshot.snapshot_key)
        self.assertEqual(source_breach["attribution"]["metric_owner"], "CHV coordination lead")

    def test_persisted_breaches_can_create_dashboard_notifications(self):
        self._snapshot("overdue_action_count", value=Decimal("6.000000"))

        result = evaluate_operational_kpi_thresholds(as_of_date=self.snapshot_date, persist=True, notify=True)

        self.assertGreaterEqual(result["critical_count"], 1)
        notifications = list(DashboardNotification.objects.filter(type=DashboardNotification.TYPE_OPERATIONAL_KPI_THRESHOLD))
        notification = next(item for item in notifications if item.metadata["metric_key"] == "overdue_action_count")
        self.assertEqual(notification.severity, DashboardNotification.SEVERITY_CRITICAL)
        self.assertEqual(notification.source_object_type, "operational_threshold_breach")
        self.assertEqual(notification.metadata["metric_key"], "overdue_action_count")
