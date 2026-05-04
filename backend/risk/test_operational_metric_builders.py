import json
from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from .models import (
    Alert,
    AlertWorkflowState,
    CHV,
    CHVMessage,
    ETLHeartbeat,
    FacilityReadinessReview,
    FacilityReadinessReviewEvent,
    HealthFacility,
    IngestionRun,
    OperationalBaselinePeriod,
    OperationalMetricDefinition,
    OperationalMetricSnapshot,
    PopulationExposureIngestionRun,
    PopulationExposureSource,
    PreparednessAction,
    SurveillanceIngestionRun,
    SurveillanceLabelWindow,
    SurveillanceOutbreakLabel,
    SurveillanceSource,
    SyncQueue,
    UssdSessionLog,
    Ward,
)
from .operational_metric_builders import (
    build_daily_operational_kpi_snapshots,
    build_operational_kpi_source_coverage_audit,
    compare_operational_kpis_to_baseline,
    daily_period,
)
from .operational_metrics import OPERATIONAL_KPI_DEFINITIONS, sync_operational_metric_catalog


class OperationalMetricBuilderTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        sync_operational_metric_catalog()
        cls.ward = Ward.objects.create(name="Nyabisawa", county="Migori", sub_county="Suna East", ward_code="NYB")
        cls.facility = HealthFacility.objects.create(
            name="Nyabisawa Health Centre",
            facility_code="NYB-HC",
            ward=cls.ward,
            facility_type=HealthFacility.TYPE_HEALTH_CENTER,
            ownership=HealthFacility.OWNERSHIP_PUBLIC,
            level=HealthFacility.LEVEL_3,
        )
        cls.chv = CHV.objects.create(name="Achieng Ouma", phone_number="+254700111222", ward=cls.ward)

    def setUp(self):
        self.snapshot_date = timezone.localdate() - timedelta(days=1)
        self.period_start, self.period_end = daily_period(self.snapshot_date)

    def _retime(self, model, instance, **fields):
        model.objects.filter(pk=instance.pk).update(**fields)
        instance.refresh_from_db()
        return instance

    def _seed_complete_operational_sources(self):
        alert_created = self.period_start + timedelta(minutes=1)
        alert_sent = self.period_start + timedelta(minutes=3)
        alert = Alert.objects.create(
            ward=self.ward,
            channel=Alert.CHANNEL_SMS,
            recipient="+254700111222",
            message="High cholera risk alert",
            status=Alert.STATUS_DELIVERED,
            sent_at=alert_sent,
        )
        self._retime(Alert, alert, created_at=alert_created)

        AlertWorkflowState.objects.create(
            ward=self.ward,
            alert=alert,
            status=AlertWorkflowState.STATUS_DELIVERED,
            trigger_severity=AlertWorkflowState.SEVERITY_HIGH,
            active_alert_count=1,
            delivered_alert_count=1,
            last_evaluated_at=self.period_start + timedelta(minutes=10),
        )

        action = PreparednessAction.objects.create(
            action_type=PreparednessAction.ACTION_HOUSEHOLD_PREVENTION_MESSAGE,
            source_trigger_type=PreparednessAction.SOURCE_ALERT,
            ward=self.ward,
            alert=alert,
            chv=self.chv,
            status=PreparednessAction.STATUS_COMPLETED,
            due_at=self.period_start + timedelta(hours=8),
            acknowledged_at=self.period_start + timedelta(minutes=45),
            completed_at=self.period_start + timedelta(hours=4),
            completion_evidence={"households_reached": 12, "evidence_ref": "field-log-1"},
        )
        self._retime(PreparednessAction, action, created_at=self.period_start + timedelta(minutes=15))

        review = FacilityReadinessReview.objects.create(
            facility=self.facility,
            ward=self.ward,
            status=FacilityReadinessReview.STATUS_RESOLVED,
            severity=FacilityReadinessReview.SEVERITY_HIGH,
            resolved_at=self.period_start + timedelta(hours=5),
        )
        self._retime(FacilityReadinessReview, review, created_at=self.period_start + timedelta(minutes=30))
        event = FacilityReadinessReviewEvent.objects.create(
            review=review,
            action=FacilityReadinessReviewEvent.ACTION_RESOLVED,
            new_status=FacilityReadinessReview.STATUS_RESOLVED,
            detail="Stock confirmed.",
        )
        self._retime(FacilityReadinessReviewEvent, event, created_at=self.period_start + timedelta(hours=5))

        message = CHVMessage.objects.create(
            chv=self.chv,
            ward=self.ward,
            channel=CHVMessage.CHANNEL_SMS,
            message_body="Treat water and report symptoms.",
            status=CHVMessage.STATUS_DELIVERED,
        )
        self._retime(CHVMessage, message, created_at=self.period_start + timedelta(hours=1))

        first_session = UssdSessionLog.objects.create(
            session_id="session-complete",
            phone_number=self.chv.phone_number,
            response_text="END Visit the nearest facility",
            ward=self.ward,
            menu_level="referral",
        )
        second_session = UssdSessionLog.objects.create(
            session_id="session-open",
            phone_number="+254700333444",
            response_text="CON Select symptoms",
            ward=self.ward,
            menu_level="symptoms",
        )
        self._retime(UssdSessionLog, first_session, created_at=self.period_start + timedelta(hours=2))
        self._retime(UssdSessionLog, second_session, created_at=self.period_start + timedelta(hours=3))

        sync_item = SyncQueue.objects.create(
            client_submission_id="submission-1",
            phone_number=self.chv.phone_number,
            ward=self.ward,
            status=SyncQueue.STATUS_PROCESSED,
            processed_at=self.period_start + timedelta(hours=3),
        )
        self._retime(SyncQueue, sync_item, created_at=self.period_start + timedelta(hours=3))

        SurveillanceLabelWindow.objects.create(
            ward=self.ward,
            label_window_start=self.snapshot_date,
            label_window_end=self.snapshot_date,
            outbreak_label=SurveillanceOutbreakLabel.ACTIVE,
            suspected_case_count=3,
            source_record_count=1,
        )

        ETLHeartbeat.objects.create(
            component=ETLHeartbeat.COMPONENT_WORKER,
            task_name="operational-kpi-test",
            status=ETLHeartbeat.STATUS_OK,
            recorded_at=self.period_end - timedelta(hours=1),
        )
        IngestionRun.objects.create(
            status=IngestionRun.STATUS_SUCCESS,
            records_seen=1,
            records_loaded=1,
            completed_at=self.period_end - timedelta(hours=1),
        )
        surveillance_source = SurveillanceSource.objects.create(
            source_name="Test surveillance source",
            source_type=SurveillanceSource.SOURCE_TYPE_DAILY_AGGREGATE,
            submitted_at=self.period_start,
        )
        SurveillanceIngestionRun.objects.create(
            source=surveillance_source,
            source_name=surveillance_source.source_name,
            source_type=surveillance_source.source_type,
            status=SurveillanceIngestionRun.STATUS_SUCCESS,
            records_seen=1,
            records_loaded=1,
            completed_at=self.period_end - timedelta(hours=1),
        )
        population_source = PopulationExposureSource.objects.create(
            source_name="Test population source",
            source_type=PopulationExposureSource.SOURCE_TYPE_POPULATION_BASELINE,
            submitted_at=self.period_start,
        )
        PopulationExposureIngestionRun.objects.create(
            source=population_source,
            source_name=population_source.source_name,
            source_type=population_source.source_type,
            status=PopulationExposureIngestionRun.STATUS_SUCCESS,
            records_seen=1,
            records_loaded=1,
            completed_at=self.period_end - timedelta(hours=1),
        )

    def test_daily_builder_persists_idempotent_snapshots_and_values(self):
        self._seed_complete_operational_sources()

        first = build_daily_operational_kpi_snapshots(snapshot_date=self.snapshot_date)
        second = build_daily_operational_kpi_snapshots(snapshot_date=self.snapshot_date)

        self.assertEqual(first["snapshot_count"], len(OPERATIONAL_KPI_DEFINITIONS))
        self.assertEqual(first["created"], len(OPERATIONAL_KPI_DEFINITIONS))
        self.assertEqual(second["created"], 0)
        self.assertEqual(second["updated"], len(OPERATIONAL_KPI_DEFINITIONS))
        self.assertEqual(OperationalMetricSnapshot.objects.count(), len(OPERATIONAL_KPI_DEFINITIONS))

        p95 = OperationalMetricSnapshot.objects.get(metric_definition__metric_key="alert_delivery_time_p95_seconds")
        under_5m = OperationalMetricSnapshot.objects.get(metric_definition__metric_key="alerts_delivered_under_5m_pct")
        ussd = OperationalMetricSnapshot.objects.get(metric_definition__metric_key="ussd_completion_rate")

        self.assertEqual(p95.status, OperationalMetricSnapshot.STATUS_COMPLETE)
        self.assertEqual(p95.value, Decimal("120.000000"))
        self.assertEqual(under_5m.value, Decimal("100.000000"))
        self.assertEqual(ussd.value, Decimal("50.000000"))

    def test_missing_sources_emit_warnings_and_stale_windows_are_detectable(self):
        stale_date = self.snapshot_date - timedelta(days=5)

        build_daily_operational_kpi_snapshots(snapshot_date=stale_date)
        audit = build_operational_kpi_source_coverage_audit(as_of_date=self.snapshot_date, stale_after_days=1)

        warning_codes = {item["warning"] for item in audit["warnings"]}
        self.assertEqual(audit["overall_status"], "warning")
        self.assertIn("stale_metric_window", warning_codes)
        self.assertTrue(any(code.endswith("_missing_stale_or_not_successful") for code in warning_codes))
        self.assertGreater(audit["record_totals"]["no_source_snapshots"], 0)

        definition = OperationalMetricDefinition.objects.get(metric_key="alerts_delivered_under_5m_pct", version="v1")
        OperationalMetricSnapshot.objects.create(
            metric_definition=definition,
            date=self.snapshot_date,
            period_start=self.period_start,
            period_end=self.period_end,
            value=Decimal("100.000000"),
            numerator=Decimal("1.000000"),
            denominator=Decimal("1.000000"),
            status=OperationalMetricSnapshot.STATUS_COMPLETE,
            source_record_count=1,
            source_coverage={
                "schema_version": "operational-kpi-source-coverage-v1",
                "warnings": [],
                "details": {},
            },
            county=self.ward.county,
            sub_county=self.ward.sub_county,
            ward=self.ward,
            source_channel="SMS",
        )
        scoped_audit = build_operational_kpi_source_coverage_audit(
            as_of_date=self.snapshot_date,
            stale_after_days=1,
            filters={
                "ward_id": self.ward.id,
                "sub_county": self.ward.sub_county,
                "source_channel": "SMS",
            },
        )
        scoped_warning_codes = {item["warning"] for item in scoped_audit["warnings"]}
        self.assertEqual(scoped_audit["overall_status"], "pass")
        self.assertEqual(scoped_audit["filters"]["ward_id"], self.ward.id)
        self.assertEqual(scoped_audit["record_totals"]["snapshots"], 1)
        self.assertNotIn("stale_metric_window", scoped_warning_codes)
        self.assertNotIn("metric_has_no_snapshots", scoped_warning_codes)

    def test_source_coverage_audit_ignores_future_snapshots_for_historical_as_of_date(self):
        stale_date = self.snapshot_date - timedelta(days=5)
        future_date = self.snapshot_date + timedelta(days=4)
        future_start, future_end = daily_period(future_date)

        build_daily_operational_kpi_snapshots(
            snapshot_date=stale_date,
            metric_keys=["alerts_delivered_under_5m_pct"],
        )
        definition = OperationalMetricDefinition.objects.get(metric_key="alerts_delivered_under_5m_pct", version="v1")
        OperationalMetricSnapshot.objects.create(
            metric_definition=definition,
            date=future_date,
            period_start=future_start,
            period_end=future_end,
            value=Decimal("100.000000"),
            numerator=Decimal("1.000000"),
            denominator=Decimal("1.000000"),
            status=OperationalMetricSnapshot.STATUS_COMPLETE,
            source_record_count=1,
            source_coverage={
                "schema_version": "operational-kpi-source-coverage-v1",
                "warnings": [],
                "details": {},
            },
        )

        audit = build_operational_kpi_source_coverage_audit(
            as_of_date=self.snapshot_date,
            stale_after_days=1,
        )
        latest = next(item for item in audit["latest_snapshots"] if item["metric_key"] == "alerts_delivered_under_5m_pct")
        warning_codes = {
            item["warning"]
            for item in audit["warnings"]
            if item["metric_key"] == "alerts_delivered_under_5m_pct"
        }

        self.assertEqual(latest["latest_date"], stale_date.isoformat())
        self.assertIn("stale_metric_window", warning_codes)
        self.assertEqual(audit["record_totals"]["snapshots"], 1)

    def test_source_freshness_snapshot_does_not_use_future_feed_records(self):
        future_timestamp = self.period_end + timedelta(days=3)
        ETLHeartbeat.objects.create(
            component=ETLHeartbeat.COMPONENT_WORKER,
            task_name="future-operational-kpi-test",
            status=ETLHeartbeat.STATUS_OK,
            recorded_at=future_timestamp,
        )
        IngestionRun.objects.create(
            status=IngestionRun.STATUS_SUCCESS,
            records_seen=1,
            records_loaded=1,
            completed_at=future_timestamp,
        )
        surveillance_source = SurveillanceSource.objects.create(
            source_name="Future surveillance source",
            source_type=SurveillanceSource.SOURCE_TYPE_DAILY_AGGREGATE,
            submitted_at=future_timestamp,
        )
        SurveillanceIngestionRun.objects.create(
            source=surveillance_source,
            source_name=surveillance_source.source_name,
            source_type=surveillance_source.source_type,
            status=SurveillanceIngestionRun.STATUS_SUCCESS,
            records_seen=1,
            records_loaded=1,
            completed_at=future_timestamp,
        )
        population_source = PopulationExposureSource.objects.create(
            source_name="Future population source",
            source_type=PopulationExposureSource.SOURCE_TYPE_POPULATION_BASELINE,
            submitted_at=future_timestamp,
        )
        PopulationExposureIngestionRun.objects.create(
            source=population_source,
            source_name=population_source.source_name,
            source_type=population_source.source_type,
            status=PopulationExposureIngestionRun.STATUS_SUCCESS,
            records_seen=1,
            records_loaded=1,
            completed_at=future_timestamp,
        )

        build_daily_operational_kpi_snapshots(
            snapshot_date=self.snapshot_date,
            metric_keys=["source_data_freshness_pass_rate"],
        )
        snapshot = OperationalMetricSnapshot.objects.get(
            metric_definition__metric_key="source_data_freshness_pass_rate",
            date=self.snapshot_date,
        )

        self.assertEqual(snapshot.status, OperationalMetricSnapshot.STATUS_NO_SOURCE)
        self.assertEqual(snapshot.value, Decimal("0.000000"))
        self.assertEqual(snapshot.source_record_count, 0)
        self.assertIn("etl_heartbeat_missing_stale_or_not_successful", snapshot.source_coverage["warnings"])

    def test_baseline_comparison_requires_dimension_matching_baseline(self):
        other_ward = Ward.objects.create(
            name="Wasweta II",
            county="Migori",
            sub_county="Suna West",
            ward_code="WS2",
        )
        definition = OperationalMetricDefinition.objects.get(metric_key="alert_delivery_time_p95_seconds", version="v1")
        OperationalMetricSnapshot.objects.create(
            metric_definition=definition,
            date=self.snapshot_date,
            period_start=self.period_start,
            period_end=self.period_end,
            value=Decimal("120.000000"),
            numerator=Decimal("120.000000"),
            denominator=Decimal("1.000000"),
            status=OperationalMetricSnapshot.STATUS_COMPLETE,
            source_record_count=1,
            source_coverage={
                "schema_version": "operational-kpi-source-coverage-v1",
                "warnings": [],
                "details": {},
            },
            county=self.ward.county,
            sub_county=self.ward.sub_county,
            ward=self.ward,
            source_channel="SMS",
        )
        OperationalBaselinePeriod.objects.create(
            metric_definition=definition,
            name="Other ward baseline",
            period_start=self.period_start - timedelta(days=35),
            period_end=self.period_start - timedelta(days=7),
            baseline_value=Decimal("10.000000"),
            source_snapshot_count=1,
            source_snapshot_keys=["other-ward-baseline-source"],
            dimensions={"ward_id": other_ward.id, "source_channel": "SMS"},
            owner="M&E lead",
        )

        missing_match = compare_operational_kpis_to_baseline(
            as_of_date=self.snapshot_date,
            metric_keys=["alert_delivery_time_p95_seconds"],
            filters={"ward_id": self.ward.id, "source_channel": "SMS"},
        )

        self.assertEqual(missing_match["overall_status"], "warning")
        self.assertEqual(missing_match["filters"]["ward_id"], self.ward.id)
        self.assertEqual(missing_match["comparisons"][0]["status"], "missing_dimension_matching_active_baseline")

        OperationalBaselinePeriod.objects.create(
            metric_definition=definition,
            name="Global baseline should not beat specific baseline",
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

        compared = compare_operational_kpis_to_baseline(
            as_of_date=self.snapshot_date,
            metric_keys=["alert_delivery_time_p95_seconds"],
            filters={"ward_id": self.ward.id, "source_channel": "SMS"},
        )

        self.assertEqual(compared["overall_status"], "pass")
        self.assertEqual(compared["comparisons"][0]["baseline_key"], matching_baseline.baseline_key)
        self.assertEqual(compared["comparisons"][0]["baseline_value"], Decimal("60.000000"))
        self.assertEqual(compared["comparisons"][0]["delta"], Decimal("60.000000"))

    def test_required_management_commands_emit_json_contracts(self):
        self._seed_complete_operational_sources()

        stdout = StringIO()
        call_command(
            "build_daily_operational_kpi_snapshots",
            f"--date={self.snapshot_date.isoformat()}",
            "--metric-key=alert_delivery_time_p95_seconds",
            "--format=json",
            stdout=stdout,
        )
        daily_payload = json.loads(stdout.getvalue())
        self.assertEqual(daily_payload["schema_version"], "operational-kpi-snapshot-v1")
        self.assertEqual(daily_payload["snapshot_count"], 1)

        definition = OperationalMetricDefinition.objects.get(metric_key="alert_delivery_time_p95_seconds")
        OperationalBaselinePeriod.objects.create(
            metric_definition=definition,
            name="Test baseline",
            period_start=self.period_start - timedelta(days=28),
            period_end=self.period_start - timedelta(days=1),
            baseline_value=Decimal("60.000000"),
            source_snapshot_count=1,
            source_snapshot_keys=["baseline-source"],
            owner="M&E lead",
        )

        stdout = StringIO()
        call_command(
            "compare_operational_kpis_to_baseline",
            f"--as-of-date={self.snapshot_date.isoformat()}",
            "--metric-key=alert_delivery_time_p95_seconds",
            "--format=json",
            stdout=stdout,
        )
        comparison_payload = json.loads(stdout.getvalue())
        self.assertEqual(comparison_payload["schema_version"], "operational-kpi-baseline-comparison-v1")
        self.assertEqual(comparison_payload["overall_status"], "pass")
        self.assertEqual(comparison_payload["comparisons"][0]["delta"], "60.000000")

        stdout = StringIO()
        call_command(
            "backfill_daily_operational_kpi_snapshots",
            f"--start-date={(self.snapshot_date - timedelta(days=1)).isoformat()}",
            f"--end-date={self.snapshot_date.isoformat()}",
            "--metric-key=alert_delivery_time_p95_seconds",
            "--format=json",
            stdout=stdout,
        )
        backfill_payload = json.loads(stdout.getvalue())
        self.assertEqual(backfill_payload["schema_version"], "operational-kpi-snapshot-v1")
        self.assertEqual(backfill_payload["days"], 2)
        self.assertEqual(backfill_payload["snapshot_count"], 2)

        stdout = StringIO()
        call_command(
            "audit_operational_kpi_source_coverage",
            f"--as-of-date={self.snapshot_date.isoformat()}",
            f"--ward-id={self.ward.id}",
            f"--sub-county={self.ward.sub_county}",
            "--source-channel=SMS",
            "--format=json",
            stdout=stdout,
        )
        audit_payload = json.loads(stdout.getvalue())
        self.assertEqual(audit_payload["schema_version"], "operational-kpi-source-coverage-audit-v1")
        self.assertEqual(audit_payload["filters"]["ward_id"], self.ward.id)
        self.assertIn(audit_payload["overall_status"], {"pass", "warning", "fail"})
