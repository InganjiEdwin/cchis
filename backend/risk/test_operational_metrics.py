import json
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.test import TestCase
from django.utils import timezone

from .models import (
    CHV,
    HealthFacility,
    OperationalBaselinePeriod,
    OperationalMetricDefinition,
    OperationalMetricDimension,
    OperationalMetricSnapshot,
    OperationalSLAThreshold,
    Ward,
)
from .operational_metrics import (
    OPERATIONAL_KPI_DEFINITIONS,
    OPERATIONAL_METRIC_DIMENSIONS,
    OPERATIONAL_METRIC_SCHEMA_VERSION,
    sync_operational_metric_catalog,
    validate_operational_metric_dictionary,
)


class OperationalMetricDictionaryTestCase(TestCase):
    def test_dictionary_has_governance_fields_and_keeps_model_metrics_separate(self):
        self.assertEqual(validate_operational_metric_dictionary(), [])
        self.assertGreaterEqual(len(OPERATIONAL_KPI_DEFINITIONS), 13)

        groups = {item["metric_group"] for item in OPERATIONAL_KPI_DEFINITIONS}
        self.assertSetEqual(
            groups,
            {
                OperationalMetricDefinition.GROUP_ALERT_DELIVERY,
                OperationalMetricDefinition.GROUP_TRIGGER_ACTIVATION,
                OperationalMetricDefinition.GROUP_ACTION_COMPLETION,
                OperationalMetricDefinition.GROUP_CHV_ADOPTION,
                OperationalMetricDefinition.GROUP_FACILITY_PREPAREDNESS,
                OperationalMetricDefinition.GROUP_USSD_COMPLETION,
                OperationalMetricDefinition.GROUP_HOUSEHOLD_REACH,
                OperationalMetricDefinition.GROUP_OUTCOME_FEEDBACK,
                OperationalMetricDefinition.GROUP_SOURCE_DATA_HEALTH,
            },
        )

        for definition in OPERATIONAL_KPI_DEFINITIONS:
            self.assertEqual(definition["metric_family"], OperationalMetricDefinition.FAMILY_OPERATIONAL)
            self.assertTrue(definition["owner"])
            self.assertTrue(definition["formula"])
            self.assertTrue(definition["window"])
            self.assertTrue(definition["source_model"])
            self.assertIn(definition["source_model"], definition["source_models"])
            self.assertNotIn("model_accuracy", definition["metric_key"])

    def test_sync_operational_metric_catalog_is_idempotent(self):
        first = sync_operational_metric_catalog()
        second = sync_operational_metric_catalog()

        self.assertEqual(first["dimensions"], len(OPERATIONAL_METRIC_DIMENSIONS))
        self.assertEqual(second["definitions"], len(OPERATIONAL_KPI_DEFINITIONS))
        self.assertEqual(OperationalMetricDimension.objects.count(), len(OPERATIONAL_METRIC_DIMENSIONS))
        self.assertEqual(OperationalMetricDefinition.objects.count(), len(OPERATIONAL_KPI_DEFINITIONS))
        self.assertFalse(OperationalMetricDefinition.objects.filter(metric_family=OperationalMetricDefinition.FAMILY_MODEL).exists())

        duplicate_active = (
            OperationalMetricDefinition.objects.filter(is_active=True)
            .values("metric_key")
            .annotate(active_count=Count("id"))
            .filter(active_count__gt=1)
        )
        self.assertFalse(duplicate_active.exists())

    def test_sync_operational_metric_catalog_handles_new_active_version_without_unique_collision(self):
        sync_operational_metric_catalog()
        upgraded_specs = [dict(item) for item in OPERATIONAL_KPI_DEFINITIONS]
        upgraded_specs[0] = {
            **upgraded_specs[0],
            "version": "v2",
            "display_name": f"{upgraded_specs[0]['display_name']} v2",
            "metadata": {
                "schema_version": OPERATIONAL_METRIC_SCHEMA_VERSION,
                "upgrade_test": True,
            },
        }

        with patch("risk.operational_metrics.OPERATIONAL_KPI_DEFINITIONS", upgraded_specs):
            sync_operational_metric_catalog()

        metric_key = upgraded_specs[0]["metric_key"]
        self.assertTrue(OperationalMetricDefinition.objects.get(metric_key=metric_key, version="v2").is_active)
        retired = OperationalMetricDefinition.objects.get(metric_key=metric_key, version="v1")
        self.assertFalse(retired.is_active)
        self.assertIsNotNone(retired.effective_to)

    def test_sync_command_validates_dictionary_as_json(self):
        stdout = StringIO()

        call_command("sync_operational_metric_catalog", "--validate-only", "--format=json", stdout=stdout)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["schema"], "operational-kpi-dictionary-v1")
        self.assertEqual(payload["status"], "pass")
        self.assertEqual(payload["issues"], [])


class OperationalMetricDataMartModelTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        sync_operational_metric_catalog()
        cls.ward = Ward.objects.create(name="Kakrao", county="Migori", sub_county="Suna East", ward_code="KE-MIG-KAK")
        cls.facility = HealthFacility.objects.create(
            name="Kakrao Dispensary",
            facility_code="KAK-DISP",
            ward=cls.ward,
            facility_type=HealthFacility.TYPE_DISPENSARY,
            ownership=HealthFacility.OWNERSHIP_PUBLIC,
            level=HealthFacility.LEVEL_2,
        )
        cls.chv = CHV.objects.create(name="Amina Otieno", phone_number="+254700000001", ward=cls.ward)

    def _definition(self, metric_key="alert_delivery_time_p95_seconds"):
        return OperationalMetricDefinition.objects.get(metric_key=metric_key, version="v1")

    def setUp(self):
        self.period_end = timezone.now().replace(microsecond=0)
        self.period_start = self.period_end - timedelta(days=1)

    def _snapshot_kwargs(self):
        return {
            "metric_definition": self._definition(),
            "date": self.period_start.date(),
            "period_start": self.period_start,
            "period_end": self.period_end,
            "grain": OperationalMetricSnapshot.GRAIN_DAILY,
            "value": Decimal("240.000000"),
            "numerator": Decimal("240.000000"),
            "denominator": Decimal("1.000000"),
            "status": OperationalMetricSnapshot.STATUS_COMPLETE,
            "source_record_count": 2,
            "source_coverage": {"source_model": "risk.Alert", "complete": True},
            "dimension_values": {"ward_name": self.ward.name, "source_channel": "SMS"},
            "county": self.ward.county,
            "sub_county": self.ward.sub_county,
            "ward": self.ward,
            "source_channel": "SMS",
            "alert_severity": "HIGH",
            "model_version": "ops-model-v1",
        }

    def test_snapshot_identity_prevents_duplicate_recalculation_rows(self):
        first = OperationalMetricSnapshot.objects.create(**self._snapshot_kwargs())
        duplicate_kwargs = self._snapshot_kwargs()
        duplicate_kwargs["value"] = Decimal("300.000000")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                OperationalMetricSnapshot.objects.create(**duplicate_kwargs)

        stored = OperationalMetricSnapshot.objects.get(pk=first.pk)
        self.assertTrue(stored.snapshot_key.startswith("opsmetric:alert_delivery_time_p95_seconds:v1:"))
        self.assertEqual(stored.value_unit, "seconds")

    def test_snapshot_identity_changes_for_distinct_dimension_slice(self):
        first = OperationalMetricSnapshot.objects.create(**self._snapshot_kwargs())
        second_kwargs = self._snapshot_kwargs()
        second_kwargs["source_channel"] = "DASHBOARD"
        second_kwargs["dimension_values"] = {"ward_name": self.ward.name, "source_channel": "DASHBOARD"}

        second = OperationalMetricSnapshot.objects.create(**second_kwargs)

        self.assertNotEqual(first.snapshot_key, second.snapshot_key)

    def test_baseline_periods_and_sla_thresholds_are_explicit_and_versioned(self):
        definition = self._definition()
        period_end = timezone.now().replace(microsecond=0)
        period_start = period_end - timedelta(days=28)

        baseline = OperationalBaselinePeriod.objects.create(
            metric_definition=definition,
            name="April operational baseline",
            description="Pre-pilot baseline for alert delivery p95.",
            period_start=period_start,
            period_end=period_end,
            baseline_value=Decimal("180.000000"),
            source_snapshot_count=4,
            source_snapshot_keys=["snapshot-a", "snapshot-b"],
            dimensions={"county": "Migori", "source_channel": "SMS"},
            owner="M&E lead",
        )
        threshold = OperationalSLAThreshold.objects.create(
            threshold_key="alert_delivery_p95_seconds",
            metric_definition=definition,
            version="v1",
            display_name="Alert delivery p95 under five minutes",
            comparator=OperationalSLAThreshold.COMPARATOR_LTE,
            target_value=Decimal("300.000000"),
            warning_value=Decimal("240.000000"),
            critical_value=Decimal("600.000000"),
            owner="County EOC operations",
            rationale="Operators need high-risk alerts delivered fast enough for same-day action.",
        )

        self.assertTrue(baseline.baseline_key.startswith("opsbase:alert_delivery_time_p95_seconds:v1:"))
        self.assertEqual(baseline.status, OperationalBaselinePeriod.STATUS_ACTIVE)
        self.assertEqual(threshold.value_unit, "seconds")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                OperationalSLAThreshold.objects.create(
                    threshold_key="alert_delivery_p95_seconds",
                    metric_definition=definition,
                    version="v2",
                    display_name="Competing active alert delivery p95 threshold",
                    comparator=OperationalSLAThreshold.COMPARATOR_LTE,
                    target_value=Decimal("300.000000"),
                    owner="County EOC operations",
                    rationale="Only one active threshold version may exist for the same threshold key.",
                )
