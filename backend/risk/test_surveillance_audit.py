import json
import tempfile
from datetime import date
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from risk.ml.pipeline import run_mock_prediction_pipeline
from risk.models import (
    FeatureDataset,
    ModelRun,
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
from risk.surveillance_audit import build_surveillance_pipeline_audit
from risk.surveillance_ingestion import replay_surveillance_ingestion_run, run_surveillance_csv_ingestion
from risk.surveillance_labels import build_surveillance_label_dataset


class SurveillancePipelineAuditPhaseSixTestCase(TestCase):
    def setUp(self):
        self.ward = Ward.objects.create(
            name="North Kamagambo",
            county="Migori",
            ward_code="KE-MIG-NK",
            current_risk_level=Ward.RISK_HIGH,
            current_risk_score=0.84,
            is_active=True,
        )

    def _write_surveillance_csv(self, csv_file):
        csv_file.write(
            "ward_code,reporting_period_start,reporting_period_end,"
            "suspected_cholera_count,confirmed_cholera_count,diarrheal_count,source_ref\n"
        )
        csv_file.write("KE-MIG-NK,2026-04-01,2026-04-07,5,1,,weekly.csv\n")
        csv_file.write("KE-MIG-NK,2026-04-08,2026-04-14,6,,,weekly.csv\n")
        csv_file.write("KE-MIG-NK,2026-04-15,2026-04-21,,,14,weekly.csv\n")
        csv_file.flush()

    def _build_full_audit_fixture(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv") as csv_file:
            self._write_surveillance_csv(csv_file)
            original = run_surveillance_csv_ingestion(
                file_path=csv_file.name,
                source_name="county-weekly-report",
                source_type=SurveillanceSource.SOURCE_TYPE_WEEKLY_AGGREGATE,
                source_timestamp="2026-04-22T00:00:00+03:00",
                correction_mode=SurveillanceIngestionRun.CORRECTION_BACKFILL,
            )
            replay_surveillance_ingestion_run(original.id, file_path=csv_file.name)

        with tempfile.NamedTemporaryFile("w", suffix=".csv") as seed_file:
            seed_file.write(
                "ward_code,reporting_period_start,reporting_period_end,suspected_case_count,source_ref\n"
            )
            seed_file.write("KE-MIG-NK,2026-04-22,2026-04-28,2,seed.csv\n")
            seed_file.flush()
            run_surveillance_csv_ingestion(
                file_path=seed_file.name,
                source_name="seed-demo-surveillance",
                source_type=SurveillanceSource.SOURCE_TYPE_WEEKLY_AGGREGATE,
                source_timestamp="2026-04-29T00:00:00+03:00",
            )

        build_surveillance_label_dataset(
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 28),
            dataset_role="training",
        )
        run_mock_prediction_pipeline(month=4, model_version="lr-phase6-audit-v1")
        run_mock_prediction_pipeline(
            month=4,
            model_version="rf-phase6-audit-v1",
            algorithm="random_forest",
        )

    def _manual_source_and_run(
        self,
        *,
        source_name="manual-surveillance",
        execution_mode=SurveillanceIngestionRun.EXECUTION_MANUAL,
        replay_of=None,
        source_metadata=None,
    ):
        source = SurveillanceSource.objects.create(
            source_name=source_name,
            source_type=SurveillanceSource.SOURCE_TYPE_WEEKLY_AGGREGATE,
            source_timestamp=timezone.now(),
            reporting_period_start=date(2026, 4, 1),
            reporting_period_end=date(2026, 4, 7),
            source_ref=f"{source_name}.csv",
            metadata=source_metadata or {},
        )
        run = SurveillanceIngestionRun.objects.create(
            source=source,
            status=SurveillanceIngestionRun.STATUS_SUCCESS,
            source_name=source.source_name,
            source_type=source.source_type,
            source_timestamp=source.source_timestamp,
            reporting_period_start=source.reporting_period_start,
            reporting_period_end=source.reporting_period_end,
            source_ref=source.source_ref,
            adapter_key="surveillance_weekly_aggregate_csv",
            input_ref=f"fixtures/{source_name}.csv",
            execution_mode=execution_mode,
            correction_mode=SurveillanceIngestionRun.CORRECTION_ORIGINAL,
            records_seen=1,
            records_loaded=1,
            source_metadata=source_metadata or {},
            replay_of=replay_of,
            completed_at=timezone.now(),
        )
        return source, run

    def _manual_record(
        self,
        *,
        ward=None,
        count_value=5,
        case_class=SurveillanceCaseClass.SUSPECTED,
        raw_payload=None,
    ):
        source, run = self._manual_source_and_run()
        truth_level = (
            SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE
            if case_class == SurveillanceCaseClass.CONFIRMED
            else SurveillanceTruthLevel.SUSPECTED_SURVEILLANCE
        )
        return SurveillanceRecord.objects.create(
            ward=ward or self.ward,
            ingestion_run=run,
            source=source,
            disease_category="cholera",
            case_class=case_class,
            count_value=count_value,
            reporting_period_start=date(2026, 4, 1),
            reporting_period_end=date(2026, 4, 7),
            truth_level=truth_level,
            source_name=source.source_name,
            source_kind=SurveillanceSourceKind.LIVE,
            freshness_state=SurveillanceFreshnessState.FRESH,
            source_ref=source.source_ref,
            raw_payload=raw_payload if raw_payload is not None else {"source_credibility": "medium"},
        )

    def test_phase_6_audit_answers_all_verification_questions_with_lineage_and_truth_gates(self):
        self._build_full_audit_fixture()

        audit = build_surveillance_pipeline_audit()
        questions = {item["id"]: item for item in audit["verification_questions"]}

        self.assertEqual(audit["overall_status"], "pass")
        self.assertEqual(len(audit["verification_questions"]), 8)
        self.assertEqual(questions["truth_level_separation"]["status"], "pass")
        self.assertIn(
            SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE,
            questions["truth_level_separation"]["evidence"]["record_truth_level_counts"],
        )
        self.assertIn(
            SurveillanceTruthLevel.PROXY_DIARRHEAL_SIGNAL,
            questions["truth_level_separation"]["evidence"]["label_window_truth_level_counts"],
        )
        self.assertEqual(questions["replay_and_corrections"]["status"], "pass")
        self.assertEqual(questions["replay_and_corrections"]["evidence"]["replay_records_not_diagnostic_count"], 0)
        self.assertEqual(questions["label_window_lineage"]["status"], "pass")
        self.assertEqual(questions["model_backbone_consumption"]["status"], "pass")
        self.assertEqual(
            questions["model_backbone_consumption"]["evidence"]["model_run_counts_by_algorithm"]["logistic_regression"],
            1,
        )
        self.assertEqual(
            questions["model_backbone_consumption"]["evidence"]["model_run_counts_by_algorithm"]["random_forest"],
            1,
        )
        self.assertEqual(questions["lead_time_period_truth"]["status"], "pass")
        self.assertEqual(questions["honesty_under_weak_inputs"]["status"], "pass")
        self.assertEqual(questions["ops_without_frontend"]["status"], "pass")
        self.assertEqual(questions["seeded_scenario_discipline"]["status"], "pass")
        self.assertGreater(questions["seeded_scenario_discipline"]["evidence"]["seeded_record_count"], 0)

    def test_audit_flags_label_windows_that_cannot_trace_to_records(self):
        SurveillanceLabelWindow.objects.create(
            ward=self.ward,
            label_window_start=date(2026, 4, 1),
            label_window_end=date(2026, 4, 7),
            suspected_case_count=5,
            outbreak_label=SurveillanceOutbreakLabel.WATCH,
            label_truth_level=SurveillanceTruthLevel.SUSPECTED_SURVEILLANCE,
            source_record_count=1,
            generated_from_record_refs=[],
        )

        audit = build_surveillance_pipeline_audit()
        label_lineage = {item["id"]: item for item in audit["verification_questions"]}["label_window_lineage"]

        self.assertEqual(audit["overall_status"], "fail")
        self.assertEqual(label_lineage["status"], "fail")
        self.assertIn("label_windows_missing_record_refs", label_lineage["gaps"])

    def test_audit_warns_when_proxy_only_window_carries_confirmed_cases(self):
        SurveillanceLabelWindow.objects.create(
            ward=self.ward,
            label_window_start=date(2026, 4, 1),
            label_window_end=date(2026, 4, 7),
            confirmed_case_count=1,
            outbreak_label=SurveillanceOutbreakLabel.ACTIVE,
            label_truth_level=SurveillanceTruthLevel.PROXY_DIARRHEAL_SIGNAL,
            source_record_count=0,
            generated_from_record_refs=[],
        )

        audit = build_surveillance_pipeline_audit()
        truth = {item["id"]: item for item in audit["verification_questions"]}["truth_level_separation"]

        self.assertEqual(truth["status"], "warning")
        self.assertIn("truth_level_semantic_misuse", truth["gaps"])

    def test_audit_fails_label_windows_with_fake_counts_or_wrong_record_refs(self):
        other_ward = Ward.objects.create(
            name="South Kamagambo",
            county="Migori",
            ward_code="KE-MIG-SK",
            current_risk_level=Ward.RISK_MEDIUM,
            current_risk_score=0.44,
            is_active=True,
        )
        record = self._manual_record(ward=self.ward, count_value=5)

        SurveillanceLabelWindow.objects.create(
            ward=other_ward,
            label_window_start=date(2026, 4, 1),
            label_window_end=date(2026, 4, 7),
            suspected_case_count=99,
            outbreak_label=SurveillanceOutbreakLabel.ACTIVE,
            label_truth_level=SurveillanceTruthLevel.SUSPECTED_SURVEILLANCE,
            source_record_count=1,
            generated_from_record_refs=[f"surveillance_record:{record.id}", f"surveillance_record:{record.id}"],
        )

        audit = build_surveillance_pipeline_audit()
        label_lineage = {item["id"]: item for item in audit["verification_questions"]}["label_window_lineage"]

        self.assertEqual(label_lineage["status"], "fail")
        self.assertIn("label_windows_have_duplicate_record_refs", label_lineage["gaps"])
        self.assertIn("label_windows_reference_records_outside_ward_or_window", label_lineage["gaps"])
        self.assertIn("label_window_counts_do_not_match_referenced_records", label_lineage["gaps"])

    def test_audit_fails_label_windows_that_reference_superseded_records(self):
        record = self._manual_record(
            ward=self.ward,
            count_value=5,
            raw_payload={
                "source_credibility": "medium",
                "superseded_by_record_ref": "surveillance_record:999999",
            },
        )

        SurveillanceLabelWindow.objects.create(
            ward=self.ward,
            label_window_start=date(2026, 4, 1),
            label_window_end=date(2026, 4, 7),
            suspected_case_count=5,
            outbreak_label=SurveillanceOutbreakLabel.WATCH,
            label_truth_level=SurveillanceTruthLevel.SUSPECTED_SURVEILLANCE,
            source_record_count=1,
            source_coverage_summary={"source_credibility_counts": {"medium": 1}},
            generated_from_record_refs=[f"surveillance_record:{record.id}"],
        )

        audit = build_surveillance_pipeline_audit()
        label_lineage = {item["id"]: item for item in audit["verification_questions"]}["label_window_lineage"]

        self.assertEqual(label_lineage["status"], "fail")
        self.assertIn("label_windows_reference_superseded_records", label_lineage["gaps"])

    def test_audit_fails_replay_runs_without_parent_provenance(self):
        self._manual_source_and_run(execution_mode=SurveillanceIngestionRun.EXECUTION_REPLAY)

        audit = build_surveillance_pipeline_audit()
        replay = {item["id"]: item for item in audit["verification_questions"]}["replay_and_corrections"]

        self.assertEqual(replay["status"], "fail")
        self.assertIn("replay_run_missing_parent", replay["gaps"])

    def test_audit_fails_model_runs_with_missing_surveillance_label_dataset_refs(self):
        ModelRun.objects.create(
            algorithm_name="logistic-regression-baseline",
            model_version="lr-missing-surveillance-label-ref",
            status=ModelRun.STATUS_SUCCESS,
            month=4,
            training_dataset_ref="training-baseline-v1",
            evaluation_metrics={
                "surveillance_lead_time_validation": {
                    "validation_mode": "retrospective_surveillance_label_window_alignment",
                    "status": "ready_for_lead_time_review",
                    "label_dataset_ref": "missing-surveillance-label-dataset",
                },
            },
            metadata={
                "surveillance_label_usage": "phase_5_reference_and_validation_context_current_training_rows_remain_seeded",
                "surveillance_label_dataset_ref": "missing-surveillance-label-dataset",
                "surveillance_label_feature_dataset_id": 999999,
                "surveillance_label_truth_gate": {
                    "proxy_only_as_confirmed_allowed": False,
                },
            },
        )

        audit = build_surveillance_pipeline_audit()
        model = {item["id"]: item for item in audit["verification_questions"]}["model_backbone_consumption"]

        self.assertEqual(model["status"], "fail")
        self.assertIn("model_runs_reference_missing_label_dataset", model["gaps"])

    def test_audit_fails_seeded_sources_without_non_production_metadata(self):
        source, run = self._manual_source_and_run(
            source_name="seed-demo-surveillance",
            source_metadata={},
        )
        SurveillanceRecord.objects.create(
            ward=self.ward,
            ingestion_run=run,
            source=source,
            disease_category="cholera",
            case_class=SurveillanceCaseClass.SUSPECTED,
            count_value=2,
            reporting_period_start=date(2026, 4, 1),
            reporting_period_end=date(2026, 4, 7),
            truth_level=SurveillanceTruthLevel.SEEDED_DEMO,
            source_name=source.source_name,
            source_kind=SurveillanceSourceKind.SEEDED,
            freshness_state=SurveillanceFreshnessState.FRESH,
            source_ref=source.source_ref,
        )

        audit = build_surveillance_pipeline_audit()
        seeded = {item["id"]: item for item in audit["verification_questions"]}["seeded_scenario_discipline"]

        self.assertEqual(seeded["status"], "fail")
        self.assertIn("seeded_sources_missing_non_production_metadata", seeded["gaps"])
        self.assertIn("seeded_runs_missing_non_production_metadata", seeded["gaps"])

    def test_audit_management_command_can_emit_json(self):
        output = StringIO()

        call_command("audit_surveillance_pipeline", "--format", "json", stdout=output)
        payload = json.loads(output.getvalue())

        self.assertEqual(payload["audit_name"], "surveillance_pipeline_phase_6")
        self.assertIn("verification_questions", payload)
        self.assertEqual(
            {item["id"] for item in payload["verification_questions"]},
            {
                "truth_level_separation",
                "replay_and_corrections",
                "label_window_lineage",
                "model_backbone_consumption",
                "lead_time_period_truth",
                "honesty_under_weak_inputs",
                "ops_without_frontend",
                "seeded_scenario_discipline",
            },
        )
