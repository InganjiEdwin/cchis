import json
from datetime import date, timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from risk.climate_records import backfill_climate_records_from_ingestion_runs
from risk.climate_source_audit import build_climate_source_separation_audit
from risk.ml.ingestion import RainfallObservation, fetch_rainfall_for_ward
from risk.models import ClimateRecord, ClimateRecordQualityFlag, ClimateRecordType, IngestionRun, Ward


class ClimateRecordContractPhaseOneTestCase(TestCase):
    def setUp(self):
        self.ward = Ward.objects.create(
            name="North Kamagambo",
            county="Migori",
            ward_code="KE-MIG-NK",
            current_risk_level=Ward.RISK_LOW,
            current_risk_score=0.1,
        )

    @patch("risk.ml.ingestion.fetch_open_meteo_daily_precipitation")
    def test_live_rainfall_ingestion_persists_forecast_climate_record_contract(self, mock_fetch):
        issue_time = timezone.now()
        mock_fetch.return_value = RainfallObservation(
            ward_name=self.ward.name,
            rainfall_mm=31.25,
            source="open-meteo-forecast",
            source_timestamp=issue_time,
            latitude=-0.9876,
            longitude=34.641,
            record_type=ClimateRecordType.FORECAST,
            issue_time=issue_time,
            valid_date=issue_time.date() + timedelta(days=2),
            lead_day=3,
            forecast_horizon_days=3,
            quality_flag=ClimateRecordQualityFlag.ACCEPTED,
            lineage_metadata={"provider": "open-meteo", "rainfall_aggregation": "sum_daily_precipitation_sum"},
        )

        fetch_rainfall_for_ward(self.ward.name)

        run = IngestionRun.objects.get()
        result = run.results[0]
        record = ClimateRecord.objects.get()
        self.assertEqual(result["record_type"], ClimateRecordType.FORECAST)
        self.assertEqual(result["canonical_record"]["record_type"], ClimateRecordType.FORECAST)
        self.assertEqual(result["canonical_record"]["source_run"], f"ingestion_run:{run.id}")
        self.assertEqual(record.ward, self.ward)
        self.assertEqual(record.record_type, ClimateRecordType.FORECAST)
        self.assertEqual(record.issue_time, issue_time)
        self.assertEqual(record.valid_date, issue_time.date() + timedelta(days=2))
        self.assertEqual(record.lead_day, 3)
        self.assertEqual(record.forecast_horizon_days, 3)
        self.assertFalse(record.fallback_flag)
        self.assertEqual(record.quality_flag, ClimateRecordQualityFlag.ACCEPTED)
        self.assertEqual(record.lineage_metadata["contract_schema_version"], "climate-record-contract-v1")

    @patch("risk.ml.ingestion.fetch_open_meteo_daily_precipitation", side_effect=Exception("network down"))
    def test_static_fallback_persists_as_fallback_static_not_forecast(self, mock_fetch):
        fetch_rainfall_for_ward(self.ward.name)

        run = IngestionRun.objects.get()
        result = run.results[0]
        record = ClimateRecord.objects.get()
        self.assertEqual(run.status, IngestionRun.STATUS_PARTIAL)
        self.assertEqual(result["record_type"], ClimateRecordType.FALLBACK_STATIC)
        self.assertTrue(result["fallback_flag"])
        self.assertEqual(result["canonical_record"]["quality_flag"], ClimateRecordQualityFlag.DEGRADED_FALLBACK)
        self.assertEqual(record.record_type, ClimateRecordType.FALLBACK_STATIC)
        self.assertTrue(record.fallback_flag)
        self.assertIsNone(record.issue_time)
        self.assertIsNone(record.lead_day)
        self.assertEqual(record.forecast_horizon_days, 0)

    @patch("risk.ml.ingestion.fetch_open_meteo_daily_precipitation")
    def test_climate_source_audit_inventories_forecast_horizon_and_known_gaps(self, mock_fetch):
        issue_time = timezone.now()
        mock_fetch.return_value = RainfallObservation(
            ward_name=self.ward.name,
            rainfall_mm=12,
            source="open-meteo-forecast",
            source_timestamp=issue_time,
            record_type=ClimateRecordType.FORECAST,
            issue_time=issue_time,
            valid_date=issue_time.date() + timedelta(days=2),
            lead_day=3,
            forecast_horizon_days=3,
            quality_flag=ClimateRecordQualityFlag.ACCEPTED,
        )
        fetch_rainfall_for_ward(self.ward.name)

        audit = build_climate_source_separation_audit()

        self.assertEqual(audit["record_totals"]["forecast_records"], 1)
        self.assertEqual(audit["source_inventory"]["max_lead_day"], 3)
        self.assertFalse(audit["source_inventory"]["supports_7_day_forecast_claim"])
        self.assertIn("forecast_horizon_below_7_days", audit["source_gaps"])
        self.assertIn("no_observed_rainfall_records_available", audit["source_gaps"])
        self.assertEqual(
            {item["id"]: item["status"] for item in audit["verification_questions"]}["climate_record_contract"],
            "pass",
        )

    def test_audit_climate_sources_command_outputs_json(self):
        output = StringIO()

        call_command("audit_climate_sources", "--format", "json", stdout=output)

        payload = json.loads(output.getvalue())
        self.assertEqual(payload["audit_name"], "climate_forecast_horizon_source_separation_phase_0_1")
        self.assertIn("source_inventory", payload)

    @patch("risk.climate_source_audit._climate_record_table_available", return_value=False)
    def test_climate_source_audit_reports_missing_climate_record_table_without_crashing(self, mock_table_available):
        audit = build_climate_source_separation_audit()

        self.assertEqual(audit["overall_status"], "fail")
        self.assertIn("climate_record_table_missing_or_migrations_not_applied", audit["hard_gaps"])
        self.assertFalse(
            next(
                item
                for item in audit["verification_questions"]
                if item["id"] == "climate_record_contract"
            )["evidence"]["climate_record_table_available"]
        )

    def test_climate_source_audit_flags_records_with_stale_ward_ids(self):
        IngestionRun.objects.create(
            run_type=IngestionRun.RUN_TYPE_RAINFALL,
            status=IngestionRun.STATUS_PARTIAL,
            source_mode="test",
            source_kind=IngestionRun.SOURCE_KIND_SEEDED,
            source_name="static-fallback",
            completed_at=timezone.now(),
            results=[
                {
                    "ward_id": 999999,
                    "ward_name": "Deleted Ward",
                    "rainfall_mm": 50,
                    "source": "static-fallback",
                    "fallback_reason": "legacy stale ward",
                }
            ],
        )

        audit = build_climate_source_separation_audit()

        self.assertEqual(audit["overall_status"], "fail")
        self.assertIn("climate_records_missing_or_invalid_ward", audit["hard_gaps"])
        contract_question = next(
            item for item in audit["verification_questions"] if item["id"] == "climate_record_contract"
        )
        self.assertEqual(contract_question["evidence"]["records_missing_or_invalid_ward"], 1)

    def test_climate_source_audit_flags_records_with_mismatched_ward_identity(self):
        other_ward = Ward.objects.create(
            name="Got Kachola",
            county="Migori",
            ward_code="KE-MIG-GK",
            current_risk_level=Ward.RISK_LOW,
            current_risk_score=0.2,
        )
        IngestionRun.objects.create(
            run_type=IngestionRun.RUN_TYPE_RAINFALL,
            status=IngestionRun.STATUS_PARTIAL,
            source_mode="test",
            source_kind=IngestionRun.SOURCE_KIND_SEEDED,
            source_name="static-fallback",
            completed_at=timezone.now(),
            results=[
                {
                    "ward_id": self.ward.id,
                    "ward_name": other_ward.name,
                    "rainfall_mm": 50,
                    "source": "static-fallback",
                    "fallback_reason": "legacy mismatched ward",
                }
            ],
        )

        audit = build_climate_source_separation_audit()

        self.assertEqual(audit["overall_status"], "fail")
        self.assertIn("climate_records_ward_identity_mismatch", audit["hard_gaps"])
        ward_question = next(item for item in audit["verification_questions"] if item["id"] == "ward_linkage_available")
        self.assertEqual(ward_question["evidence"]["records_with_ward_identity_mismatch"], 1)

    def test_climate_source_audit_flags_persisted_records_with_mismatched_raw_ward_identity(self):
        other_ward = Ward.objects.create(
            name="Got Kachola",
            county="Migori",
            ward_code="KE-MIG-GK",
            current_risk_level=Ward.RISK_LOW,
            current_risk_score=0.2,
        )
        run = IngestionRun.objects.create(
            run_type=IngestionRun.RUN_TYPE_RAINFALL,
            status=IngestionRun.STATUS_PARTIAL,
            source_mode="test",
            source_kind=IngestionRun.SOURCE_KIND_SEEDED,
            source_name="static-fallback",
            completed_at=timezone.now(),
            results=[],
        )
        ClimateRecord.objects.create(
            ward=self.ward,
            ingestion_run=run,
            record_type=ClimateRecordType.FALLBACK_STATIC,
            source_provider="static-fallback",
            source_kind=IngestionRun.SOURCE_KIND_SEEDED,
            source_mode="test",
            forecast_horizon_days=0,
            rainfall_mm=50,
            quality_flag=ClimateRecordQualityFlag.DEGRADED_FALLBACK,
            fallback_flag=True,
            source_run=f"ingestion_run:{run.id}",
            source_ref="persisted-mismatched-ward",
            raw_payload={"ward_name": other_ward.name},
        )

        audit = build_climate_source_separation_audit()

        self.assertEqual(audit["overall_status"], "fail")
        self.assertIn("climate_records_ward_identity_mismatch", audit["hard_gaps"])
        ward_question = next(item for item in audit["verification_questions"] if item["id"] == "ward_linkage_available")
        self.assertEqual(ward_question["evidence"]["records_with_ward_identity_mismatch"], 1)

    def test_climate_source_audit_fails_malformed_contract_values_without_crashing(self):
        IngestionRun.objects.create(
            run_type=IngestionRun.RUN_TYPE_RAINFALL,
            status=IngestionRun.STATUS_SUCCESS,
            source_mode="test",
            source_kind=IngestionRun.SOURCE_KIND_LIVE,
            source_name="open-meteo-forecast",
            completed_at=timezone.now(),
            results=[
                {
                    "ward_id": self.ward.id,
                    "ward_name": self.ward.name,
                    "rainfall_mm": "wet",
                    "source": "open-meteo-forecast",
                    "record_type": ClimateRecordType.FORECAST,
                    "issue_time": "not-a-date",
                    "valid_date": "not-a-date",
                    "lead_day": "not-a-number",
                    "forecast_horizon_days": "not-a-number",
                    "fallback_flag": False,
                    "source_ref": "malformed-forecast-contract",
                }
            ],
        )

        audit = build_climate_source_separation_audit()

        self.assertEqual(audit["overall_status"], "fail")
        self.assertIn("forecast_records_missing_valid_date", audit["hard_gaps"])
        self.assertIn("forecast_records_missing_lead_day", audit["hard_gaps"])
        self.assertIn("forecast_records_invalid_forecast_horizon", audit["hard_gaps"])
        self.assertIn("climate_records_missing_or_invalid_rainfall_value", audit["hard_gaps"])

    def test_backfill_climate_records_skips_mismatched_ward_identity(self):
        run = IngestionRun.objects.create(
            run_type=IngestionRun.RUN_TYPE_RAINFALL,
            status=IngestionRun.STATUS_PARTIAL,
            source_mode="test",
            source_kind=IngestionRun.SOURCE_KIND_SEEDED,
            source_name="static-fallback",
            completed_at=timezone.now(),
            results=[
                {
                    "ward_id": self.ward.id,
                    "ward_name": "Wrong Ward",
                    "rainfall_mm": 50,
                    "source": "static-fallback",
                    "fallback_reason": "legacy mismatched ward",
                }
            ],
        )

        applied = backfill_climate_records_from_ingestion_runs(dry_run=False, run_id=run.id)

        self.assertEqual(applied["saved_records"], 0)
        self.assertEqual(applied["skip_reasons"]["ward_identity_mismatch"], 1)
        self.assertFalse(ClimateRecord.objects.filter(ingestion_run=run).exists())

    def test_backfill_climate_records_infers_legacy_open_meteo_contract_with_explicit_quality_flag(self):
        completed_at = timezone.now()
        run = IngestionRun.objects.create(
            run_type=IngestionRun.RUN_TYPE_RAINFALL,
            status=IngestionRun.STATUS_SUCCESS,
            source_mode="test",
            source_kind=IngestionRun.SOURCE_KIND_LIVE,
            source_name="open-meteo-forecast",
            completed_at=completed_at,
            results=[
                {
                    "ward_id": self.ward.id,
                    "ward_name": self.ward.name,
                    "rainfall_mm": 21.5,
                    "source": "open-meteo-forecast",
                    "fallback_reason": "",
                }
            ],
        )

        dry_run = backfill_climate_records_from_ingestion_runs(
            dry_run=True,
            infer_legacy_open_meteo_horizon_days=3,
            run_id=run.id,
        )
        self.assertEqual(dry_run["ready_rows"], 1)
        self.assertEqual(dry_run["saved_records"], 0)

        applied = backfill_climate_records_from_ingestion_runs(
            dry_run=False,
            infer_legacy_open_meteo_horizon_days=3,
            run_id=run.id,
        )
        run.refresh_from_db()
        record = ClimateRecord.objects.get(ingestion_run=run)

        self.assertEqual(applied["saved_records"], 1)
        self.assertEqual(run.results[0]["record_type"], ClimateRecordType.FORECAST)
        self.assertEqual(run.results[0]["lead_day"], 3)
        self.assertEqual(record.record_type, ClimateRecordType.FORECAST)
        self.assertEqual(record.lead_day, 3)
        self.assertEqual(record.forecast_horizon_days, 3)
        self.assertEqual(record.quality_flag, ClimateRecordQualityFlag.MISSING_FORECAST_CONTRACT)
        self.assertEqual(
            record.lineage_metadata["legacy_contract_inference"]["issue_time_policy"],
            "ingestion_timestamp_used_when_provider_issue_time_missing",
        )

    def test_backfill_climate_records_command_outputs_json(self):
        output = StringIO()

        call_command("backfill_climate_records", "--format", "json", stdout=output)

        payload = json.loads(output.getvalue())
        self.assertEqual(payload["schema_version"], "climate-record-contract-v1")
        self.assertTrue(payload["climate_record_table_available"])
