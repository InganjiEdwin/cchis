import tempfile
from datetime import date
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from risk.models import (
    FeatureDataset,
    HealthFacility,
    SurveillanceCaseClass,
    SurveillanceFreshnessState,
    SurveillanceIngestionRun,
    SurveillanceLabelWindow,
    SurveillanceOutbreakLabel,
    SurveillanceRecord,
    SurveillanceSource,
    SurveillanceSourceKind,
    SurveillanceTruthLevel,
    Ward,
)
from risk.surveillance_ingestion import (
    TRUTH_LEVEL_CONFIRMED,
    build_surveillance_replay_plan,
    inspect_surveillance_csv,
    regenerate_surveillance_label_windows_for_run,
    replay_surveillance_ingestion_run,
    run_surveillance_csv_ingestion,
)
from risk.surveillance_labels import SURVEILLANCE_LABEL_SCHEMA_VERSION
from risk.surveillance_labels import build_surveillance_label_dataset


class SurveillanceIngestionPhaseTwoTestCase(TestCase):
    def setUp(self):
        self.ward = Ward.objects.create(
            name="North Kamagambo",
            county="Migori",
            ward_code="KE-MIG-NK",
            current_risk_level=Ward.RISK_HIGH,
            current_risk_score=0.84,
        )
        self.facility = HealthFacility.objects.create(
            name="Kamagambo Dispensary",
            facility_code="KM-DISP",
            ward=self.ward,
        )

    def _write_weekly_csv(self, csv_file, *, include_bad_row: bool = False):
        csv_file.write(
            "ward_id,reporting_period_start,reporting_period_end,"
            "suspected_cholera_count,confirmed_cholera_count,diarrheal_count,source_ref,unexpected_note\n"
        )
        csv_file.write(f"{self.ward.id},2026-04-01,2026-04-07,5,1,12,weekly.csv,kept-for-warning\n")
        if include_bad_row:
            csv_file.write(f"{self.ward.id},2026-04-08,2026-04-01,3,0,4,weekly.csv,bad-period\n")
        csv_file.flush()

    def test_inspect_surveillance_csv_reports_contract_counts_without_persisting(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv") as csv_file:
            self._write_weekly_csv(csv_file)

            inspection = inspect_surveillance_csv(
                csv_file.name,
                source_type=SurveillanceSource.SOURCE_TYPE_WEEKLY_AGGREGATE,
                source_name="county-weekly-report",
            )

        self.assertEqual(inspection["records_seen"], 1)
        self.assertEqual(inspection["records_loaded"], 1)
        self.assertEqual(inspection["records_rejected"], 0)
        self.assertEqual(inspection["truth_level_counts"], {TRUTH_LEVEL_CONFIRMED: 1})
        self.assertEqual(inspection["period_start"].isoformat(), "2026-04-01")
        self.assertEqual(inspection["period_end"].isoformat(), "2026-04-07")
        self.assertEqual(inspection["unknown_columns"], ["unexpected_note"])
        self.assertEqual(SurveillanceSource.objects.count(), 0)
        self.assertEqual(SurveillanceIngestionRun.objects.count(), 0)

    def test_run_surveillance_csv_ingestion_persists_source_run_and_correction_metadata(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv") as csv_file:
            self._write_weekly_csv(csv_file, include_bad_row=True)

            run = run_surveillance_csv_ingestion(
                file_path=csv_file.name,
                source_name="county-weekly-report",
                source_type=SurveillanceSource.SOURCE_TYPE_WEEKLY_AGGREGATE,
                source_ref="weekly.csv",
                correction_mode=SurveillanceIngestionRun.CORRECTION_AMENDMENT,
                correction_reason="Late correction from county surveillance team.",
                operator_note="Accepted with one bad-period row rejected.",
            )

        source = SurveillanceSource.objects.get()
        self.assertEqual(run.status, SurveillanceIngestionRun.STATUS_PARTIAL)
        self.assertEqual(run.records_seen, 2)
        self.assertEqual(run.records_loaded, 1)
        self.assertEqual(run.records_rejected, 1)
        self.assertEqual(run.correction_mode, SurveillanceIngestionRun.CORRECTION_AMENDMENT)
        self.assertEqual(run.correction_reason, "Late correction from county surveillance team.")
        self.assertEqual(run.reporting_period_start.isoformat(), "2026-04-01")
        self.assertEqual(run.reporting_period_end.isoformat(), "2026-04-07")
        self.assertEqual(run.results["phase"], "phase_4_ongoing_feed_readiness")
        self.assertTrue(run.results["canonical_records_persisted"])
        self.assertEqual(run.results["truth_level_counts"], {TRUTH_LEVEL_CONFIRMED: 1})
        self.assertEqual(run.results["canonical_summary"]["surveillance_records"], 3)
        self.assertEqual(run.results["canonical_summary"]["truth_level_counts"], {
            SurveillanceTruthLevel.SUSPECTED_SURVEILLANCE: 1,
            SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE: 1,
            SurveillanceTruthLevel.PROXY_DIARRHEAL_SIGNAL: 1,
        })
        self.assertEqual(source.reporting_period_start, run.reporting_period_start)
        self.assertEqual(source.reporting_period_end, run.reporting_period_end)
        records_by_case_class = {
            record.case_class: record
            for record in SurveillanceRecord.objects.filter(ingestion_run=run)
        }
        self.assertEqual(records_by_case_class[SurveillanceCaseClass.SUSPECTED].count_value, 5)
        self.assertEqual(records_by_case_class[SurveillanceCaseClass.CONFIRMED].count_value, 1)
        self.assertEqual(records_by_case_class[SurveillanceCaseClass.PROXY].disease_category, "diarrheal")
        self.assertEqual(
            records_by_case_class[SurveillanceCaseClass.CONFIRMED].freshness_state,
            SurveillanceFreshnessState.CORRECTED_AFTER_INITIAL_SUBMISSION,
        )

    def test_replay_surveillance_ingestion_keeps_original_metadata_and_marks_replay_mode(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv") as csv_file:
            self._write_weekly_csv(csv_file)
            original = run_surveillance_csv_ingestion(
                file_path=csv_file.name,
                source_name="county-weekly-report",
                source_type=SurveillanceSource.SOURCE_TYPE_WEEKLY_AGGREGATE,
                source_ref="weekly.csv",
                correction_mode=SurveillanceIngestionRun.CORRECTION_BACKFILL,
            )
            replay = replay_surveillance_ingestion_run(
                original.id,
                file_path=csv_file.name,
                operator_note="Replay after adapter check.",
            )

        self.assertEqual(original.status, SurveillanceIngestionRun.STATUS_SUCCESS)
        self.assertEqual(replay.status, SurveillanceIngestionRun.STATUS_SUCCESS)
        self.assertEqual(replay.execution_mode, SurveillanceIngestionRun.EXECUTION_REPLAY)
        self.assertEqual(replay.replay_of, original)
        self.assertEqual(replay.source_type, original.source_type)
        self.assertEqual(replay.reporting_period_start, original.reporting_period_start)
        self.assertEqual(replay.reporting_period_end, original.reporting_period_end)
        self.assertEqual(
            set(replay.surveillance_records.values_list("freshness_state", flat=True)),
            {SurveillanceFreshnessState.REPLAY_DIAGNOSTIC},
        )

    def test_scheduled_ingestion_rejects_manual_only_backfill_source_type(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv") as csv_file:
            self._write_weekly_csv(csv_file)

            with self.assertRaises(ValueError):
                run_surveillance_csv_ingestion(
                    file_path=csv_file.name,
                    source_name="historical-backfill",
                    source_type=SurveillanceSource.SOURCE_TYPE_CSV_BACKFILL,
                    correction_mode=SurveillanceIngestionRun.CORRECTION_BACKFILL,
                    execution_mode=SurveillanceIngestionRun.EXECUTION_SCHEDULED,
                )

    def test_feed_policy_marks_delayed_and_stale_reporting_from_submission_lag(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv") as delayed_file:
            self._write_weekly_csv(delayed_file)
            delayed_run = run_surveillance_csv_ingestion(
                file_path=delayed_file.name,
                source_name="county-weekly-delayed",
                source_type=SurveillanceSource.SOURCE_TYPE_WEEKLY_AGGREGATE,
                source_timestamp="2026-04-20T00:00:00+03:00",
            )

        with tempfile.NamedTemporaryFile("w", suffix=".csv") as stale_file:
            self._write_weekly_csv(stale_file)
            stale_run = run_surveillance_csv_ingestion(
                file_path=stale_file.name,
                source_name="county-weekly-stale",
                source_type=SurveillanceSource.SOURCE_TYPE_WEEKLY_AGGREGATE,
                source_timestamp="2026-04-30T00:00:00+03:00",
            )

        self.assertEqual(
            set(delayed_run.surveillance_records.values_list("freshness_state", flat=True)),
            {SurveillanceFreshnessState.DELAYED},
        )
        self.assertEqual(
            delayed_run.results["canonical_summary"]["freshness_state_counts"],
            {SurveillanceFreshnessState.DELAYED: 3},
        )
        self.assertEqual(
            set(stale_run.surveillance_records.values_list("freshness_state", flat=True)),
            {SurveillanceFreshnessState.STALE},
        )
        self.assertEqual(stale_run.results["feed_policy"]["expected_reporting_lag_days"], 7)
        self.assertEqual(stale_run.results["feed_policy"]["stale_after_days"], 14)

    def test_reporting_granularity_warning_preserves_source_supplied_truth(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv") as csv_file:
            csv_file.write(
                "ward_code,reporting_period_start,reporting_period_end,"
                "suspected_cholera_count,reporting_granularity\n"
            )
            csv_file.write("KE-MIG-NK,2026-04-01,2026-04-07,5,week\n")
            csv_file.flush()

            run = run_surveillance_csv_ingestion(
                file_path=csv_file.name,
                source_name="daily-export-with-weekly-row",
                source_type=SurveillanceSource.SOURCE_TYPE_DAILY_AGGREGATE,
                source_timestamp="2026-04-08T00:00:00+03:00",
            )

        record = SurveillanceRecord.objects.get(ingestion_run=run)
        self.assertEqual(record.reporting_granularity, "week")
        self.assertEqual(run.results["default_reporting_granularity"], "day")
        self.assertEqual(run.results["reporting_granularity_counts"], {"week": 1})
        self.assertEqual(
            run.results["reporting_granularity_warnings"][0]["behavior"],
            "preserved_source_supplied_granularity",
        )

    def test_trusted_push_execution_is_explicit_and_source_type_locked(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv") as csv_file:
            self._write_weekly_csv(csv_file)
            with self.assertRaises(ValueError):
                run_surveillance_csv_ingestion(
                    file_path=csv_file.name,
                    source_name="bad-trusted-push",
                    source_type=SurveillanceSource.SOURCE_TYPE_WEEKLY_AGGREGATE,
                    source_timestamp="2026-04-09T00:00:00+03:00",
                    execution_mode=SurveillanceIngestionRun.EXECUTION_TRUSTED_PUSH,
                )

        with tempfile.NamedTemporaryFile("w", suffix=".csv") as csv_file:
            csv_file.write(
                "ward_code,reporting_period_start,reporting_period_end,"
                "suspected_cholera_count,provider_event_id,push_batch_id\n"
            )
            csv_file.write("KE-MIG-NK,2026-04-01,2026-04-07,5,evt-001,push-20260409\n")
            csv_file.flush()

            run = run_surveillance_csv_ingestion(
                file_path=csv_file.name,
                source_name="trusted-partner-push",
                source_type=SurveillanceSource.SOURCE_TYPE_TRUSTED_PUSH,
                source_timestamp="2026-04-09T00:00:00+03:00",
                source_ref="push-20260409",
                execution_mode=SurveillanceIngestionRun.EXECUTION_TRUSTED_PUSH,
            )

        record = SurveillanceRecord.objects.get(ingestion_run=run)
        self.assertEqual(run.status, SurveillanceIngestionRun.STATUS_SUCCESS)
        self.assertEqual(run.execution_mode, SurveillanceIngestionRun.EXECUTION_TRUSTED_PUSH)
        self.assertTrue(run.results["operational_safety"]["trusted_push_mode"])
        self.assertTrue(run.results["feed_policy"]["trusted_push_supported"])
        self.assertEqual(record.raw_payload["row"]["provider_event_id"], "evt-001")

    def test_correction_can_regenerate_downstream_label_windows(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv") as csv_file:
            self._write_weekly_csv(csv_file)
            run = run_surveillance_csv_ingestion(
                file_path=csv_file.name,
                source_name="county-weekly-backfill",
                source_type=SurveillanceSource.SOURCE_TYPE_WEEKLY_AGGREGATE,
                source_timestamp="2026-04-12T00:00:00+03:00",
                correction_mode=SurveillanceIngestionRun.CORRECTION_BACKFILL,
                regenerate_label_windows=True,
                label_dataset_role="evaluation",
            )

        regeneration = run.results["downstream_label_regeneration"]
        self.assertTrue(regeneration["regenerated"])
        self.assertEqual(regeneration["dataset_role"], "evaluation")
        self.assertEqual(regeneration["label_window_count"], 1)
        self.assertEqual(
            FeatureDataset.objects.get(schema_version=SURVEILLANCE_LABEL_SCHEMA_VERSION).dataset_ref,
            regeneration["dataset_ref"],
        )
        self.assertEqual(SurveillanceLabelWindow.objects.count(), 1)

    def test_replay_label_regeneration_request_is_skipped_safely(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv") as csv_file:
            self._write_weekly_csv(csv_file)
            original = run_surveillance_csv_ingestion(
                file_path=csv_file.name,
                source_name="county-weekly-report",
                source_type=SurveillanceSource.SOURCE_TYPE_WEEKLY_AGGREGATE,
                source_timestamp="2026-04-12T00:00:00+03:00",
            )
            replay = replay_surveillance_ingestion_run(original.id, file_path=csv_file.name)

        summary = regenerate_surveillance_label_windows_for_run(replay)

        self.assertTrue(summary["skipped"])
        self.assertEqual(summary["reason"], "replay_diagnostic_run")
        self.assertEqual(FeatureDataset.objects.count(), 0)

    def test_amendment_supersedes_original_record_and_label_dataset_excludes_old_value(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv") as original_file:
            original_file.write(
                "ward_code,reporting_period_start,reporting_period_end,suspected_cholera_count,source_ref\n"
            )
            original_file.write("KE-MIG-NK,2026-04-01,2026-04-07,5,weekly-row-001\n")
            original_file.flush()
            original_run = run_surveillance_csv_ingestion(
                file_path=original_file.name,
                source_name="county-weekly-original",
                source_type=SurveillanceSource.SOURCE_TYPE_WEEKLY_AGGREGATE,
                source_timestamp="2026-04-08T00:00:00+03:00",
                correction_mode=SurveillanceIngestionRun.CORRECTION_ORIGINAL,
            )

        original_record = SurveillanceRecord.objects.get(ingestion_run=original_run)
        with tempfile.NamedTemporaryFile("w", suffix=".csv") as amendment_file:
            amendment_file.write(
                "ward_code,reporting_period_start,reporting_period_end,"
                "suspected_cholera_count,source_ref,supersedes_record_ref\n"
            )
            amendment_file.write(
                f"KE-MIG-NK,2026-04-01,2026-04-07,9,weekly-row-001-v2,"
                f"surveillance_record:{original_record.id}\n"
            )
            amendment_file.flush()
            amendment_run = run_surveillance_csv_ingestion(
                file_path=amendment_file.name,
                source_name="county-weekly-amendment",
                source_type=SurveillanceSource.SOURCE_TYPE_WEEKLY_AGGREGATE,
                source_timestamp="2026-04-09T00:00:00+03:00",
                correction_mode=SurveillanceIngestionRun.CORRECTION_AMENDMENT,
                correction_reason="Corrected county weekly suspected count.",
            )

        amendment_record = SurveillanceRecord.objects.get(ingestion_run=amendment_run)
        original_record.refresh_from_db()
        self.assertEqual(
            original_record.raw_payload["superseded_by_record_ref"],
            f"surveillance_record:{amendment_record.id}",
        )
        self.assertEqual(
            amendment_run.results["canonical_summary"]["supersession_summary"]["superseded_record_count"],
            1,
        )

        snapshot = build_surveillance_label_dataset(start_date=date(2026, 4, 1), end_date=date(2026, 4, 7))
        window = snapshot.label_windows[0]

        self.assertEqual(window.suspected_case_count, 9)
        self.assertEqual(window.source_record_count, 1)
        self.assertEqual(window.generated_from_record_refs, [f"surveillance_record:{amendment_record.id}"])
        self.assertEqual(window.source_coverage_summary["source_credibility_counts"], {"medium": 1})

    def test_inspect_management_command_does_not_create_ingestion_run(self):
        output = StringIO()
        with tempfile.NamedTemporaryFile("w", suffix=".csv") as csv_file:
            self._write_weekly_csv(csv_file)

            call_command(
                "ingest_surveillance",
                "--inspect-only",
                "--file",
                csv_file.name,
                "--source-type",
                SurveillanceSource.SOURCE_TYPE_WEEKLY_AGGREGATE,
                "--source-name",
                "county-weekly-report",
                stdout=output,
            )

        self.assertIn("accepted=1", output.getvalue())
        self.assertEqual(SurveillanceIngestionRun.objects.count(), 0)

    def test_replay_plan_shape_includes_replay_backfill_and_amendment_commands(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv") as csv_file:
            self._write_weekly_csv(csv_file)
            run = run_surveillance_csv_ingestion(
                file_path=csv_file.name,
                source_name="county-weekly-report",
                source_type=SurveillanceSource.SOURCE_TYPE_WEEKLY_AGGREGATE,
                source_ref="weekly.csv",
            )

        replay_plan = build_surveillance_replay_plan(run)

        self.assertEqual(replay_plan["run_id"], run.id)
        self.assertIn("--replay-of", replay_plan["replay_command"])
        self.assertIn("--correction-mode backfill", replay_plan["backfill_command_shape"])
        self.assertIn("--correction-mode amendment", replay_plan["amendment_command_shape"])

    def test_facility_proxy_row_derives_ward_from_facility_and_stays_proxy_truth(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv") as csv_file:
            csv_file.write(
                "facility_code,reporting_period_start,reporting_period_end,"
                "proxy_case_count,provider,dhis2_org_unit_id,dhis2_data_element_id\n"
            )
            csv_file.write("KM-DISP,2026-04-01,2026-04-07,9,dhis2,OU-1,DE-1\n")
            csv_file.flush()

            run = run_surveillance_csv_ingestion(
                file_path=csv_file.name,
                source_name="facility-proxy-feed",
                source_type=SurveillanceSource.SOURCE_TYPE_FACILITY_PROXY,
            )

        record = SurveillanceRecord.objects.get(ingestion_run=run)
        self.assertEqual(run.status, SurveillanceIngestionRun.STATUS_SUCCESS)
        self.assertEqual(record.ward, self.ward)
        self.assertEqual(record.facility, self.facility)
        self.assertEqual(record.truth_level, SurveillanceTruthLevel.PROXY_DIARRHEAL_SIGNAL)
        self.assertEqual(record.source_kind, SurveillanceSourceKind.LIVE)
        self.assertEqual(record.raw_payload["provider_contract"]["provider"], "dhis2")
        self.assertIn("provider_columns", run.results["provider_import_contract"])

    def test_seeded_demo_source_maps_to_seeded_truth_and_source_kind(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv") as csv_file:
            csv_file.write(
                "ward_code,reporting_period_start,reporting_period_end,"
                "suspected_case_count,outbreak_label\n"
            )
            csv_file.write("KE-MIG-NK,2026-04-01,2026-04-07,2,watch\n")
            csv_file.flush()

            run = run_surveillance_csv_ingestion(
                file_path=csv_file.name,
                source_name="seed-demo-surveillance",
                source_type=SurveillanceSource.SOURCE_TYPE_WEEKLY_AGGREGATE,
            )

        record = SurveillanceRecord.objects.get(ingestion_run=run)
        source = SurveillanceSource.objects.get()
        self.assertEqual(record.truth_level, SurveillanceTruthLevel.SEEDED_DEMO)
        self.assertEqual(record.source_kind, SurveillanceSourceKind.SEEDED)
        self.assertEqual(record.outbreak_label, SurveillanceOutbreakLabel.WATCH)
        self.assertTrue(source.metadata["seeded_non_production"])
        self.assertFalse(source.metadata["production_use_allowed"])
        self.assertTrue(run.source_metadata["seeded_non_production"])
        self.assertFalse(run.source_metadata["production_use_allowed"])

    def test_label_window_shape_can_reference_canonical_records(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv") as csv_file:
            self._write_weekly_csv(csv_file)
            run = run_surveillance_csv_ingestion(
                file_path=csv_file.name,
                source_name="county-weekly-report",
                source_type=SurveillanceSource.SOURCE_TYPE_WEEKLY_AGGREGATE,
            )

        record_ids = list(run.surveillance_records.values_list("id", flat=True))
        label_window = SurveillanceLabelWindow.objects.create(
            ward=self.ward,
            label_window_start="2026-04-01",
            label_window_end="2026-04-07",
            suspected_case_count=5,
            confirmed_case_count=1,
            proxy_case_count=12,
            outbreak_label=SurveillanceOutbreakLabel.ACTIVE,
            label_truth_level=SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE,
            source_coverage_summary={"weekly_aggregate": 1},
            generated_from_record_refs=[f"surveillance_record:{record_id}" for record_id in record_ids],
        )

        self.assertEqual(label_window.generated_from_record_refs, [
            f"surveillance_record:{record_id}" for record_id in record_ids
        ])
        self.assertEqual(label_window.generation_mode, "phase_2_shape_defined")
