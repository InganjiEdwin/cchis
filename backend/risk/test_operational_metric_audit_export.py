import json
from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import StepUpGrant, User

from .models import (
    Alert,
    CHV,
    CHVMessage,
    OperationalMetricDefinition,
    OperationalMetricSnapshot,
    PreparednessAction,
    PreparednessActionEvent,
    Ward,
)
from .operational_metric_audit import (
    build_operational_kpi_integrity_audit,
    build_operational_kpi_me_export,
)
from .operational_metric_builders import daily_period
from .operational_metrics import sync_operational_metric_catalog
from .test_step_up_utils import force_authenticate_with_step_up


class OperationalMetricAuditExportTestCase(APITestCase):
    password = "ChangeMe123!"

    def setUp(self):
        sync_operational_metric_catalog()
        self.ward = Ward.objects.create(
            name="Muhuru",
            county="Migori",
            sub_county="Nyatike",
            ward_code="MHR",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="me_export_admin",
            password=self.password,
            email="me-export-admin@example.com",
            role=User.ROLE_ADMIN,
            ward=self.ward,
            is_active=True,
        )
        self.snapshot_date = timezone.localdate() - timedelta(days=1)
        self.period_start, self.period_end = daily_period(self.snapshot_date)
        force_authenticate_with_step_up(
            self.client,
            self.user,
            StepUpGrant.PURPOSE_SENSITIVE_EXPORT_DOWNLOAD,
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
            "value": Decimal("1.000000"),
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

    def test_integrity_audit_flags_phase_5_gap_examples(self):
        self._snapshot("alert_delivery_time_p50_seconds", source_coverage={})
        self._snapshot(
            "households_reached_count",
            value=Decimal("5.000000"),
            numerator=Decimal("5.000000"),
            denominator=Decimal("0.000000"),
        )
        inactive_definition = OperationalMetricDefinition.objects.create(
            metric_key="retired_metric_used_by_snapshot",
            version="v1",
            display_name="Retired metric",
            description="Retired metric should not appear in current dashboard exports.",
            metric_group=OperationalMetricDefinition.GROUP_SOURCE_DATA_HEALTH,
            metric_family=OperationalMetricDefinition.FAMILY_OPERATIONAL,
            value_type=OperationalMetricDefinition.VALUE_COUNT,
            value_unit="records",
            owner="M&E lead",
            formula="retired",
            window="daily",
            source_model="risk.Legacy",
            source_models=["risk.Legacy"],
            allowed_dimensions=["date"],
            interpretation="Retired metric.",
            is_active=False,
            effective_to=timezone.now() - timedelta(days=1),
        )
        OperationalMetricSnapshot.objects.create(
            metric_definition=inactive_definition,
            date=self.snapshot_date,
            period_start=self.period_start,
            period_end=self.period_end,
            value=Decimal("1.000000"),
            status=OperationalMetricSnapshot.STATUS_COMPLETE,
            source_record_count=1,
            source_coverage={"schema_version": "operational-kpi-source-coverage-v1", "warnings": [], "details": {}},
        )

        missing_timestamp_alert = Alert.objects.create(
            ward=self.ward,
            channel=Alert.CHANNEL_SMS,
            recipient="+254700000001",
            message="Delivered without timestamp",
            status=Alert.STATUS_DELIVERED,
        )
        Alert.objects.filter(pk=missing_timestamp_alert.pk).update(created_at=self.period_start + timedelta(hours=1))

        negative_latency_alert = Alert.objects.create(
            ward=self.ward,
            channel=Alert.CHANNEL_SMS,
            recipient="+254700000002",
            message="Negative latency",
            status=Alert.STATUS_DELIVERED,
            sent_at=self.period_start + timedelta(minutes=10),
        )
        Alert.objects.filter(pk=negative_latency_alert.pk).update(created_at=self.period_start + timedelta(minutes=20))

        completed_action = PreparednessAction.objects.create(
            action_type=PreparednessAction.ACTION_FIELD_VERIFICATION,
            source_trigger_type=PreparednessAction.SOURCE_MANUAL,
            source_trigger_ref="audit-gap-action",
            ward=self.ward,
            status=PreparednessAction.STATUS_COMPLETED,
            completed_at=self.period_start + timedelta(hours=3),
            completion_evidence={"summary": "Done"},
        )
        PreparednessAction.objects.filter(pk=completed_action.pk).update(created_at=self.period_start + timedelta(hours=2))
        completed_action.refresh_from_db()
        PreparednessActionEvent.objects.create(
            preparedness_action=completed_action,
            event_type=PreparednessActionEvent.EVENT_COMPLETED,
            new_status=PreparednessAction.STATUS_COMPLETED,
        )

        eventless_completed_action = PreparednessAction.objects.create(
            action_type=PreparednessAction.ACTION_FIELD_VERIFICATION,
            source_trigger_type=PreparednessAction.SOURCE_MANUAL,
            source_trigger_ref="audit-gap-eventless-action",
            ward=self.ward,
            status=PreparednessAction.STATUS_COMPLETED,
            completed_at=self.period_start + timedelta(hours=5),
            completion_evidence={"summary": "Done without event trail"},
        )
        PreparednessAction.objects.filter(pk=eventless_completed_action.pk).update(
            created_at=self.period_start + timedelta(hours=4)
        )

        audit = build_operational_kpi_integrity_audit(
            date_from=self.snapshot_date,
            date_to=self.snapshot_date,
        )

        self.assertEqual(audit["overall_status"], "fail")
        check_ids = {issue["check_id"] for issue in audit["issues"]}
        self.assertIn("snapshot_source_coverage_present", check_ids)
        self.assertIn("household_reach_not_above_sent_messages", check_ids)
        self.assertIn("dashboard_uses_current_metric_definition", check_ids)
        self.assertIn("delivered_alert_has_delivery_timestamp", check_ids)
        self.assertIn("alert_delivery_latency_non_negative", check_ids)
        self.assertIn("completed_action_has_creation_evidence", check_ids)
        action_issue_sets = [
            set(issue["evidence"]["issues"])
            for issue in audit["issues"]
            if issue["check_id"] == "completed_action_has_creation_evidence"
        ]
        self.assertTrue(any("missing_created_event" in issues for issues in action_issue_sets))
        self.assertTrue(any("missing_completed_event" in issues for issues in action_issue_sets))

    def test_integrity_audit_respects_ward_scope_for_direct_record_checks(self):
        self._snapshot("alerts_delivered_under_5m_pct", ward=self.ward)
        other_ward = Ward.objects.create(
            name="Suna Central",
            county="Migori",
            sub_county="Suna East",
            ward_code="SNC",
            is_active=True,
        )
        other_ward_alert = Alert.objects.create(
            ward=other_ward,
            channel=Alert.CHANNEL_SMS,
            recipient="+254700000003",
            message="Delivered without timestamp in another ward",
            status=Alert.STATUS_DELIVERED,
        )
        Alert.objects.filter(pk=other_ward_alert.pk).update(created_at=self.period_start + timedelta(hours=1))

        unscoped_audit = build_operational_kpi_integrity_audit(
            date_from=self.snapshot_date,
            date_to=self.snapshot_date,
        )
        scoped_audit = build_operational_kpi_integrity_audit(
            date_from=self.snapshot_date,
            date_to=self.snapshot_date,
            ward_id=self.ward.id,
        )

        self.assertEqual(unscoped_audit["overall_status"], "fail")
        self.assertEqual(scoped_audit["overall_status"], "pass")
        self.assertEqual(scoped_audit["filters"]["ward_id"], self.ward.id)
        self.assertEqual(scoped_audit["record_totals"]["delivered_alerts"], 0)
        scoped_check_ids = {issue["check_id"] for issue in scoped_audit["issues"]}
        self.assertNotIn("delivered_alert_has_delivery_timestamp", scoped_check_ids)

    def test_integrity_audit_treats_retired_definition_as_valid_for_historical_snapshot(self):
        now = timezone.now()
        retired_definition = OperationalMetricDefinition.objects.create(
            metric_key="historically_valid_retired_metric",
            version="v1",
            display_name="Historically valid retired metric",
            description="Retired after its historical snapshot was generated.",
            metric_group=OperationalMetricDefinition.GROUP_SOURCE_DATA_HEALTH,
            metric_family=OperationalMetricDefinition.FAMILY_OPERATIONAL,
            value_type=OperationalMetricDefinition.VALUE_COUNT,
            value_unit="records",
            owner="M&E lead",
            formula="historical",
            window="daily",
            source_model="risk.Legacy",
            source_models=["risk.Legacy"],
            allowed_dimensions=["date"],
            interpretation="Historical metric.",
            is_active=False,
            effective_from=now - timedelta(days=30),
            effective_to=now - timedelta(days=1),
        )
        snapshot = OperationalMetricSnapshot.objects.create(
            metric_definition=retired_definition,
            date=self.snapshot_date,
            period_start=self.period_start,
            period_end=self.period_end,
            value=Decimal("1.000000"),
            status=OperationalMetricSnapshot.STATUS_COMPLETE,
            source_record_count=1,
            source_coverage={"schema_version": "operational-kpi-source-coverage-v1", "warnings": [], "details": {}},
            generated_at=now - timedelta(days=2),
        )

        valid_audit = build_operational_kpi_integrity_audit(
            date_from=self.snapshot_date,
            date_to=self.snapshot_date,
        )
        valid_definition_issues = [
            issue
            for issue in valid_audit["issues"]
            if issue["record_id"] == snapshot.snapshot_key
            and issue["check_id"] == "dashboard_uses_current_metric_definition"
        ]
        self.assertEqual(valid_definition_issues, [])

        OperationalMetricSnapshot.objects.filter(pk=snapshot.pk).update(generated_at=now)
        invalid_audit = build_operational_kpi_integrity_audit(
            date_from=self.snapshot_date,
            date_to=self.snapshot_date,
        )
        invalid_definition_issue = next(
            issue
            for issue in invalid_audit["issues"]
            if issue["record_id"] == snapshot.snapshot_key
            and issue["check_id"] == "dashboard_uses_current_metric_definition"
        )
        self.assertIn("metric_definition_effective_to_elapsed", invalid_definition_issue["evidence"]["stale_reasons"])

    def test_household_reach_integrity_uses_snapshot_scope_for_supporting_records(self):
        other_ward = Ward.objects.create(
            name="Awendo",
            county="Migori",
            sub_county="Awendo",
            ward_code="AWD",
            is_active=True,
        )
        other_chv = CHV.objects.create(name="Other CHV", phone_number="+254700000004", ward=other_ward)
        other_message = CHVMessage.objects.create(
            chv=other_chv,
            ward=other_ward,
            channel=CHVMessage.CHANNEL_SMS,
            message_body="Prevention message in another ward",
            status=CHVMessage.STATUS_SENT,
        )
        CHVMessage.objects.filter(pk=other_message.pk).update(created_at=self.period_start + timedelta(hours=2))
        self._snapshot(
            "households_reached_count",
            ward=self.ward,
            value=Decimal("1.000000"),
            numerator=Decimal("1.000000"),
            denominator=Decimal("0.000000"),
        )

        audit = build_operational_kpi_integrity_audit(
            date_from=self.snapshot_date,
            date_to=self.snapshot_date,
            ward_id=self.ward.id,
        )

        self.assertEqual(audit["overall_status"], "fail")
        household_issue = next(
            issue for issue in audit["issues"] if issue["check_id"] == "household_reach_not_above_sent_messages"
        )
        self.assertEqual(household_issue["evidence"]["sent_or_delivered_chv_messages"], 0)
        self.assertEqual(household_issue["evidence"]["ward_id"], self.ward.id)

    def test_me_export_is_reproducible_and_carries_operational_interpretation(self):
        self._snapshot("alerts_delivered_under_5m_pct", value=Decimal("100.000000"), source_channel="SMS")

        first = build_operational_kpi_me_export(
            date_from=self.snapshot_date,
            date_to=self.snapshot_date,
            output_format="json",
        )
        second = build_operational_kpi_me_export(
            date_from=self.snapshot_date,
            date_to=self.snapshot_date,
            output_format="json",
        )

        self.assertEqual(first["data_sha256"], second["data_sha256"])
        self.assertEqual(first["payload_sha256"], second["payload_sha256"])
        self.assertEqual(first["row_count"], 1)
        self.assertIn("Operational KPIs measure delivery", first["payload"])
        self.assertIn("alerts_delivered_under_5m_pct", first["payload"])

        csv_export = build_operational_kpi_me_export(
            date_from=self.snapshot_date,
            date_to=self.snapshot_date,
            output_format="csv",
        )
        self.assertIn("metadata_key", csv_export["payload"])
        self.assertIn("interpretation.model_separation", csv_export["payload"])
        self.assertIn("Operational KPIs measure delivery", csv_export["payload"])
        self.assertIn(csv_export["data_sha256"], csv_export["payload"])

    def test_audit_and_export_api_contracts(self):
        self._snapshot("alerts_delivered_under_5m_pct", value=Decimal("100.000000"))

        audit_response = self.client.get(
            reverse("operational-kpi-audit"),
            {"date_from": self.snapshot_date.isoformat(), "date_to": self.snapshot_date.isoformat()},
        )
        export_response = self.client.get(
            reverse("operational-kpi-me-export"),
            {
                "date_from": self.snapshot_date.isoformat(),
                "date_to": self.snapshot_date.isoformat(),
                "export_format": "csv",
            },
        )

        self.assertEqual(audit_response.status_code, status.HTTP_200_OK)
        self.assertEqual(audit_response.data["schema_version"], "operational-kpi-integrity-audit-v1")
        self.assertEqual(export_response.status_code, status.HTTP_200_OK)
        self.assertEqual(export_response.data["schema_version"], "operational-kpi-me-export-v1")
        self.assertEqual(export_response.data["format"], "csv")
        self.assertIn("metadata_key", export_response.data["payload"])
        self.assertIn("audit.overall_status", export_response.data["payload"])
        self.assertIn("metric_key", export_response.data["payload"])

        stdout = StringIO()
        call_command(
            "audit_operational_kpi_integrity",
            f"--date-from={self.snapshot_date.isoformat()}",
            f"--date-to={self.snapshot_date.isoformat()}",
            f"--ward-id={self.ward.id}",
            f"--sub-county={self.ward.sub_county}",
            "--source-channel=SMS",
            "--format=json",
            stdout=stdout,
        )
        command_payload = json.loads(stdout.getvalue())
        self.assertEqual(command_payload["schema_version"], "operational-kpi-integrity-audit-v1")
        self.assertEqual(command_payload["filters"]["ward_id"], self.ward.id)
        self.assertEqual(command_payload["filters"]["source_channel"], "SMS")

    def test_me_export_requires_fresh_download_step_up(self):
        self._snapshot("alerts_delivered_under_5m_pct", value=Decimal("100.000000"))
        self.client.force_authenticate(self.user)

        export_response = self.client.get(
            reverse("operational-kpi-me-export"),
            {
                "date_from": self.snapshot_date.isoformat(),
                "date_to": self.snapshot_date.isoformat(),
                "export_format": "csv",
            },
        )

        self.assertEqual(export_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(str(export_response.data["code"]), "step_up_required")
        self.assertEqual(str(export_response.data["purpose"]), StepUpGrant.PURPOSE_SENSITIVE_EXPORT_DOWNLOAD)
