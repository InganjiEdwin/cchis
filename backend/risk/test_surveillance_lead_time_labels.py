from datetime import date, timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from risk.models import (
    FeatureDataset,
    FeatureDatasetRow,
    ModelRun,
    RiskScore,
    SurveillanceCaseClass,
    SurveillanceDiseaseCategory,
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
from risk.surveillance_features import build_surveillance_lead_time_validation_summary
from risk.surveillance_labels import (
    SURVEILLANCE_LEAD_TIME_LABEL_GENERATION_MODE,
    SURVEILLANCE_LABEL_SCHEMA_VERSION,
    build_surveillance_lead_time_label_dataset,
    evaluate_model_run_against_surveillance_lead_time_labels,
    latest_surveillance_lead_time_label_dataset,
)


class SurveillanceLeadTimeLabelPhaseThreeTestCase(TestCase):
    def setUp(self):
        self.ward = Ward.objects.create(
            name="North Kamagambo",
            county="Migori",
            ward_code="KE-MIG-NK",
            current_risk_level=Ward.RISK_HIGH,
            current_risk_score=0.84,
        )

    def _source_and_run(
        self,
        *,
        period_start,
        period_end,
        source_name="phase3-surveillance",
        correction_mode=SurveillanceIngestionRun.CORRECTION_ORIGINAL,
        correction_reason="",
    ):
        source_timestamp = timezone.now()
        source = SurveillanceSource.objects.create(
            source_name=source_name,
            source_type=SurveillanceSource.SOURCE_TYPE_WEEKLY_AGGREGATE,
            source_timestamp=source_timestamp,
            reporting_period_start=period_start,
            reporting_period_end=period_end,
            source_ref=f"{source_name}-{period_start.isoformat()}.csv",
        )
        run = SurveillanceIngestionRun.objects.create(
            source=source,
            status=SurveillanceIngestionRun.STATUS_SUCCESS,
            source_name=source.source_name,
            source_type=source.source_type,
            source_timestamp=source.source_timestamp,
            reporting_period_start=period_start,
            reporting_period_end=period_end,
            source_ref=source.source_ref,
            correction_mode=correction_mode,
            correction_reason=correction_reason,
            records_seen=1,
            records_loaded=1,
            completed_at=source_timestamp,
        )
        return source, run

    def _record(
        self,
        *,
        case_class,
        count_value,
        period_start,
        period_end,
        truth_level=None,
        freshness_state=SurveillanceFreshnessState.FRESH,
        correction_mode=SurveillanceIngestionRun.CORRECTION_ORIGINAL,
        correction_reason="",
        revision_number=1,
        supersedes_record_ref="",
        raw_payload=None,
    ):
        source, run = self._source_and_run(
            period_start=period_start,
            period_end=period_end,
            source_name=f"phase3-{case_class}-{period_start.isoformat()}-{revision_number}",
            correction_mode=correction_mode,
            correction_reason=correction_reason,
        )
        truth_level = truth_level or (
            SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE
            if case_class == SurveillanceCaseClass.CONFIRMED
            else SurveillanceTruthLevel.SUSPECTED_SURVEILLANCE
        )
        return SurveillanceRecord.objects.create(
            ward=self.ward,
            ingestion_run=run,
            source=source,
            disease_category=SurveillanceDiseaseCategory.CHOLERA,
            case_class=case_class,
            count_value=count_value,
            reporting_period_start=period_start,
            reporting_period_end=period_end,
            truth_level=truth_level,
            source_name=source.source_name,
            source_kind=SurveillanceSourceKind.LIVE,
            freshness_state=freshness_state,
            revision_number=revision_number,
            supersedes_record_ref=supersedes_record_ref,
            source_ref=source.source_ref,
            raw_payload=raw_payload if raw_payload is not None else {"source_credibility": "high"},
        )

    def _model_run_with_prediction(self, *, prediction_date, risk_level=Ward.RISK_HIGH, score=0.91):
        inference_dataset = FeatureDataset.objects.create(
            dataset_ref=f"phase3-inference-{prediction_date.isoformat()}",
            dataset_kind=FeatureDataset.KIND_INFERENCE,
            schema_version="lead-time-feature-v1",
            source_kind=FeatureDataset.SOURCE_KIND_LIVE,
            month=prediction_date.month,
            feature_keys=["prediction_date"],
            row_count=1,
        )
        FeatureDatasetRow.objects.create(
            dataset=inference_dataset,
            ward=self.ward,
            ward_name_snapshot=self.ward.name,
            month=prediction_date.month,
            feature_values={"prediction_date": prediction_date.isoformat()},
            label=None,
        )
        model_run = ModelRun.objects.create(
            algorithm_name="logistic-regression-baseline",
            model_version=f"lr-phase3-{prediction_date.isoformat()}",
            status=ModelRun.STATUS_SUCCESS,
            month=prediction_date.month,
            inference_feature_dataset=inference_dataset,
            inference_dataset_ref=inference_dataset.dataset_ref,
            inference_row_count=1,
            evaluation_metrics={},
            metadata={},
            completed_at=timezone.now(),
        )
        RiskScore.objects.create(
            ward=self.ward,
            model_run=model_run,
            score=score,
            risk_level=risk_level,
            predicted_cases=8,
            source=RiskScore.SOURCE_MODEL,
            model_version=model_run.model_version,
            generated_at=timezone.now(),
        )
        return model_run

    def test_build_surveillance_lead_time_labels_keyed_by_prediction_date(self):
        prediction_date = date(2026, 5, 1)
        window_start = prediction_date + timedelta(days=7)
        window_end = prediction_date + timedelta(days=14)
        self._record(
            case_class=SurveillanceCaseClass.CONFIRMED,
            count_value=1,
            period_start=window_start,
            period_end=window_start,
        )
        self._record(
            case_class=SurveillanceCaseClass.SUSPECTED,
            count_value=3,
            period_start=window_start + timedelta(days=1),
            period_end=window_start + timedelta(days=1),
        )
        self._record(
            case_class=SurveillanceCaseClass.SUSPECTED,
            count_value=99,
            period_start=prediction_date + timedelta(days=1),
            period_end=prediction_date + timedelta(days=1),
        )

        snapshot = build_surveillance_lead_time_label_dataset(
            [self.ward],
            prediction_dates=[prediction_date],
            as_of=timezone.now() + timedelta(seconds=1),
        )

        dataset = snapshot.feature_dataset
        row = FeatureDatasetRow.objects.get(dataset=dataset)
        values = row.feature_values
        self.assertEqual(dataset.schema_version, SURVEILLANCE_LABEL_SCHEMA_VERSION)
        self.assertEqual(dataset.lineage_metadata["generation_mode"], SURVEILLANCE_LEAD_TIME_LABEL_GENERATION_MODE)
        self.assertEqual(dataset.lineage_metadata["dataset_role"], "evaluation")
        self.assertEqual(values["prediction_date"], prediction_date.isoformat())
        self.assertEqual(values["label_window_start"], window_start.isoformat())
        self.assertEqual(values["label_window_end"], window_end.isoformat())
        self.assertEqual(values["ward_id"], self.ward.id)
        self.assertEqual(values["confirmed_case_count"], 1)
        self.assertEqual(values["suspected_case_count"], 3)
        self.assertEqual(values["outbreak_label"], SurveillanceOutbreakLabel.ACTIVE)
        self.assertEqual(values["truth_level"], SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE)
        self.assertEqual(values["late_revision_state"], "original")
        self.assertEqual(len(values["source_refs"]), 2)
        self.assertEqual(row.label, 1)
        self.assertTrue(dataset.lineage_metadata["correction_replay_contract"]["can_rebuild_from_prediction_dates"])
        self.assertEqual(latest_surveillance_lead_time_label_dataset(), dataset)

        validation = build_surveillance_lead_time_validation_summary(label_dataset=dataset)
        self.assertEqual(validation["status"], "ready_for_7_to_14_day_evaluation")
        self.assertEqual(validation["validation_mode"], "future_7_to_14_day_surveillance_label_window_alignment")
        self.assertEqual(validation["confirmed_truth_label_count"], 1)
        self.assertFalse(validation["truth_gate"]["proxy_only_as_confirmed_allowed"])

    def test_correction_replay_excludes_superseded_records_and_updates_old_model_run_evaluation(self):
        prediction_date = date(2026, 5, 1)
        window_start = prediction_date + timedelta(days=7)
        original = self._record(
            case_class=SurveillanceCaseClass.SUSPECTED,
            count_value=5,
            period_start=window_start,
            period_end=window_start,
        )
        first_snapshot = build_surveillance_lead_time_label_dataset(
            [self.ward],
            prediction_dates=[prediction_date],
            as_of=timezone.now() + timedelta(seconds=1),
        )
        model_run = self._model_run_with_prediction(prediction_date=prediction_date, risk_level=Ward.RISK_HIGH)
        first_summary = evaluate_model_run_against_surveillance_lead_time_labels(
            model_run,
            label_dataset=first_snapshot.feature_dataset,
            persist=True,
        )
        self.assertEqual(first_summary["metrics"]["false_positive"], 1)

        amended = self._record(
            case_class=SurveillanceCaseClass.CONFIRMED,
            count_value=1,
            period_start=window_start,
            period_end=window_start,
            freshness_state=SurveillanceFreshnessState.CORRECTED_AFTER_INITIAL_SUBMISSION,
            correction_mode=SurveillanceIngestionRun.CORRECTION_AMENDMENT,
            correction_reason="Late lab confirmation corrected the original suspected-only report.",
            revision_number=2,
            supersedes_record_ref=f"surveillance_record:{original.id}",
        )
        original.raw_payload = {
            **(original.raw_payload or {}),
            "superseded_by_record_ref": f"surveillance_record:{amended.id}",
        }
        original.save(update_fields=["raw_payload"])

        second_snapshot = build_surveillance_lead_time_label_dataset(
            [self.ward],
            prediction_dates=[prediction_date],
            as_of=timezone.now() + timedelta(seconds=1),
        )
        row = FeatureDatasetRow.objects.get(dataset=second_snapshot.feature_dataset)
        values = row.feature_values
        self.assertEqual(values["confirmed_case_count"], 1)
        self.assertEqual(values["suspected_case_count"], 0)
        self.assertEqual(values["source_refs"], [f"surveillance_record:{amended.id}"])
        self.assertEqual(values["late_revision_state"], "corrected_after_initial_submission")
        self.assertEqual(SurveillanceLabelWindow.objects.get(id=values["label_window_id"]).source_record_count, 1)

        second_summary = evaluate_model_run_against_surveillance_lead_time_labels(
            model_run,
            label_dataset=second_snapshot.feature_dataset,
            persist=True,
        )
        model_run.refresh_from_db()
        self.assertEqual(second_summary["metrics"]["true_positive"], 1)
        self.assertEqual(
            model_run.evaluation_metrics["surveillance_7_to_14_day_evaluation"]["label_dataset_ref"],
            second_snapshot.feature_dataset.dataset_ref,
        )
        self.assertEqual(
            model_run.evaluation_metrics["surveillance_7_to_14_day_evaluation_history"][0]["label_dataset_ref"],
            first_snapshot.feature_dataset.dataset_ref,
        )
        self.assertTrue(model_run.metadata["surveillance_7_to_14_day_replayable_after_corrections"])

    def test_build_surveillance_lead_time_labels_command_creates_snapshot(self):
        prediction_date = date(2026, 5, 1)
        output = StringIO()

        call_command(
            "build_surveillance_lead_time_labels",
            "--prediction-date",
            prediction_date.isoformat(),
            stdout=output,
        )

        self.assertIn("Surveillance lead-time label dataset built.", output.getvalue())
        dataset = FeatureDataset.objects.get(schema_version=SURVEILLANCE_LABEL_SCHEMA_VERSION)
        row = FeatureDatasetRow.objects.get(dataset=dataset)
        self.assertEqual(row.feature_values["prediction_date"], prediction_date.isoformat())
        self.assertEqual(row.feature_values["late_revision_state"], "no_source_records")

    def test_evaluate_model_run_surveillance_labels_command_persists_summary(self):
        prediction_date = date(2026, 5, 1)
        self._record(
            case_class=SurveillanceCaseClass.CONFIRMED,
            count_value=1,
            period_start=prediction_date + timedelta(days=7),
            period_end=prediction_date + timedelta(days=7),
        )
        snapshot = build_surveillance_lead_time_label_dataset(
            [self.ward],
            prediction_dates=[prediction_date],
            as_of=timezone.now() + timedelta(seconds=1),
        )
        model_run = self._model_run_with_prediction(prediction_date=prediction_date, risk_level=Ward.RISK_HIGH)
        output = StringIO()

        call_command(
            "evaluate_model_run_surveillance_labels",
            str(model_run.id),
            "--label-dataset-ref",
            snapshot.feature_dataset.dataset_ref,
            stdout=output,
        )

        model_run.refresh_from_db()
        self.assertIn("Surveillance 7-to-14 day evaluation complete.", output.getvalue())
        summary = model_run.evaluation_metrics["surveillance_7_to_14_day_evaluation"]
        self.assertEqual(summary["status"], "evaluated")
        self.assertEqual(summary["metrics"]["true_positive"], 1)
