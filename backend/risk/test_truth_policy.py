from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import StepUpGrant, User

from risk.lead_time_features import build_lead_time_feature_dataset
from risk.ml.data import InferenceDataset, TrainingDataset
from risk.ml.registry import ensure_registry_entry_for_promoted_run
from risk.ml.pipeline import run_mock_prediction_pipeline
from risk.models import (
    Alert,
    AlertWorkflowState,
    ClimateRecord,
    ClimateRecordQualityFlag,
    ClimateRecordType,
    FeatureDataset,
    FeatureDatasetRow,
    IngestionRun,
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
from risk.services import create_alerts_for_riskscore
from risk.surveillance_labels import (
    build_surveillance_label_dataset,
    build_surveillance_lead_time_label_dataset,
)
from risk.truth_policy import (
    PRODUCTION_SEEDED_TRUTH_BLOCKED,
    PRODUCTION_STATIC_FALLBACK_BLOCKED,
    PRODUCTION_ALERT_ACTIVE_REGISTRY_REQUIRED,
    PRODUCTION_ALERT_ELIGIBILITY_BLOCKED,
    PRODUCTION_ALERT_MODEL_RUN_NOT_SUCCESS,
    PRODUCTION_ALERT_MODEL_RUN_REQUIRED,
    PRODUCTION_CANONICAL_REFERENCE_INVALID,
    PRODUCTION_CANONICAL_REFERENCE_REQUIRED,
    PRODUCTION_INVALID_FEATURE_ROW_BLOCKED,
    PRODUCTION_PROXY_NOT_CONFIRMED,
    PRODUCTION_SUPERSEDED_TRUTH_BLOCKED,
    PRODUCTION_SYNTHETIC_FEATURE_FALLBACK_BLOCKED,
    ProductionTruthPolicyError,
    production_alert_eligibility_blockers,
    production_feature_dataset_blockers,
    production_model_run_blockers,
    require_demo_data_allowed,
)
from risk.tasks import trigger_alerts_task
from risk.test_step_up_utils import force_authenticate_with_step_up


def feature_dataset(*, source_kind="LIVE", lineage_metadata=None, dataset_ref="dataset-ref", dataset_kind=None):
    return SimpleNamespace(
        source_kind=source_kind,
        lineage_metadata=lineage_metadata or {},
        dataset_ref=dataset_ref,
        dataset_kind=dataset_kind,
    )


class ProductionTruthPolicyTestCase(SimpleTestCase):
    @override_settings(CCHIS_ENVIRONMENT="production")
    def test_seeded_training_and_static_rainfall_are_blocked(self):
        blockers = production_feature_dataset_blockers(
            training_dataset=SimpleNamespace(
                feature_dataset=feature_dataset(
                    source_kind="SEEDED",
                    lineage_metadata={"training_label_source": "seeded_mock_training_rows"},
                    dataset_kind="TRAINING",
                )
            ),
            inference_dataset=SimpleNamespace(
                feature_dataset=feature_dataset(source_kind="LIVE", dataset_kind="INFERENCE"),
                rainfall_ingestion_run=SimpleNamespace(
                    source_kind="SEEDED",
                    fallback_used=True,
                    results=[{"record_type": "fallback_static"}],
                ),
            ),
        )

        self.assertEqual(
            blockers,
            [PRODUCTION_SEEDED_TRUTH_BLOCKED, PRODUCTION_STATIC_FALLBACK_BLOCKED],
        )

    @override_settings(CCHIS_ENVIRONMENT="production")
    def test_seeded_persisted_model_run_cannot_be_promoted_or_used_for_alerts(self):
        blockers = production_model_run_blockers(
            SimpleNamespace(
                model_version="v0-demo",
                metadata={"seeded": True, "seeded_non_production": True},
                training_feature_dataset=None,
                inference_feature_dataset=None,
                rainfall_ingestion_run=None,
            )
        )

        self.assertEqual(
            blockers,
            [
                "production_canonical_dataset_required",
                PRODUCTION_SEEDED_TRUTH_BLOCKED,
                PRODUCTION_CANONICAL_REFERENCE_REQUIRED,
            ],
        )

    @override_settings(CCHIS_ENVIRONMENT="production")
    def test_demo_operations_fail_with_stable_code(self):
        with self.assertRaises(ProductionTruthPolicyError) as context:
            require_demo_data_allowed("dashboard scenario simulation")

        self.assertEqual(context.exception.code, PRODUCTION_SEEDED_TRUTH_BLOCKED)

    @override_settings(CCHIS_ENVIRONMENT="local")
    def test_local_demo_operations_remain_allowed(self):
        require_demo_data_allowed("dashboard scenario simulation")

    @override_settings(CCHIS_ENVIRONMENT="production")
    def test_demo_commands_and_seeded_training_option_fail_in_production(self):
        for command_name, command_kwargs in (
            ("seed_demo_data", {}),
            ("seed_e2e_source_feeds", {}),
            ("run_risk_model", {"include_seeded_training_labels": True}),
        ):
            with self.subTest(command_name=command_name), self.assertRaises(CommandError) as context:
                call_command(command_name, **command_kwargs)
            self.assertIn("production_seeded_truth_blocked", str(context.exception))

    @override_settings(CCHIS_ENVIRONMENT="production")
    def test_explicit_seeded_label_and_feature_builders_fail_closed(self):
        builders = (
            (build_surveillance_label_dataset, {"include_seeded": True}),
            (build_surveillance_lead_time_label_dataset, {"include_seeded": True}),
            (build_lead_time_feature_dataset, {"include_seeded_surveillance": True}),
        )
        for builder, kwargs in builders:
            with self.subTest(builder=builder.__name__), self.assertRaises(ProductionTruthPolicyError) as context:
                builder(**kwargs)
            self.assertEqual(context.exception.code, PRODUCTION_SEEDED_TRUTH_BLOCKED)


@override_settings(CCHIS_ENVIRONMENT="production")
class ProductionAlertEligibilityTestCase(APITestCase):
    def setUp(self):
        self.ward = Ward.objects.create(
            name="Production Gate Ward",
            county="Migori",
            ward_code="PROD-GATE-001",
        )
        self.period_start = date(2026, 7, 1)
        self.period_end = date(2026, 7, 7)
        source_timestamp = timezone.now()
        self.surveillance_source = SurveillanceSource.objects.create(
            source_name="Production gate surveillance",
            source_type=SurveillanceSource.SOURCE_TYPE_WEEKLY_AGGREGATE,
            source_timestamp=source_timestamp,
            reporting_period_start=self.period_start,
            reporting_period_end=self.period_end,
            source_ref="production-gate-surveillance-source-v1",
        )
        self.surveillance_ingestion_run = SurveillanceIngestionRun.objects.create(
            source=self.surveillance_source,
            status=SurveillanceIngestionRun.STATUS_SUCCESS,
            source_name=self.surveillance_source.source_name,
            source_type=self.surveillance_source.source_type,
            source_timestamp=source_timestamp,
            reporting_period_start=self.period_start,
            reporting_period_end=self.period_end,
            source_ref="production-gate-surveillance-run-v1",
            adapter_key="production_gate_fixture",
            input_ref="production-gate-surveillance-input-v1",
            execution_mode=SurveillanceIngestionRun.EXECUTION_MANUAL,
            correction_mode=SurveillanceIngestionRun.CORRECTION_ORIGINAL,
            records_seen=1,
            records_loaded=1,
            completed_at=source_timestamp,
        )
        self.surveillance_record = SurveillanceRecord.objects.create(
            ward=self.ward,
            ingestion_run=self.surveillance_ingestion_run,
            source=self.surveillance_source,
            disease_category=SurveillanceDiseaseCategory.CHOLERA,
            case_class=SurveillanceCaseClass.CONFIRMED,
            outbreak_label=SurveillanceOutbreakLabel.ACTIVE,
            count_value=1,
            reporting_period_start=self.period_start,
            reporting_period_end=self.period_end,
            truth_level=SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE,
            source_name=self.surveillance_source.source_name,
            source_kind=SurveillanceSourceKind.LIVE,
            freshness_state=SurveillanceFreshnessState.FRESH,
            source_ref="production-gate-surveillance-record-v1",
            raw_payload={
                "source_credibility": "high",
                "source_status": "active_success",
            },
        )
        self.rainfall_run = IngestionRun.objects.create(
            source_kind=IngestionRun.SOURCE_KIND_LIVE,
            status=IngestionRun.STATUS_SUCCESS,
            source_name="production-gate-live-rainfall",
            source_mode="live",
            source_timestamp=source_timestamp,
            freshness_state=IngestionRun.FRESHNESS_FRESH,
            records_seen=1,
            records_loaded=1,
            results=[{"record_type": ClimateRecordType.OBSERVED, "source_ref": "production-gate-climate-record-v1"}],
            completed_at=source_timestamp,
        )
        self.climate_record = ClimateRecord.objects.create(
            ward=self.ward,
            ingestion_run=self.rainfall_run,
            record_type=ClimateRecordType.OBSERVED,
            source_provider="production-gate-rainfall-provider",
            source_kind=IngestionRun.SOURCE_KIND_LIVE,
            source_mode="live",
            valid_date=self.period_end,
            observed_timestamp=source_timestamp,
            rainfall_mm=120.0,
            quality_flag=ClimateRecordQualityFlag.ACCEPTED,
            fallback_flag=False,
            source_run="production-gate-live-rainfall-v1",
            source_ref="production-gate-climate-record-v1",
            lineage_metadata={"source_status": "active_success"},
        )
        self.training_dataset = self._dataset("training")
        self.inference_dataset = self._dataset("inference")
        self.label_dataset = FeatureDataset.objects.create(
            dataset_ref="production-gate-label",
            dataset_kind=FeatureDataset.KIND_TRAINING,
            schema_version="production-gate-label-v1",
            source_kind=FeatureDataset.SOURCE_KIND_LIVE,
            month=8,
            row_count=1,
            lineage_metadata=self._lineage_metadata(include_climate=False),
        )
        surveillance_ref = f"surveillance_record:{self.surveillance_record.id}"
        self.label_window = SurveillanceLabelWindow.objects.create(
            ward=self.ward,
            feature_dataset=self.label_dataset,
            dataset_ref=self.label_dataset.dataset_ref,
            label_window_start=self.period_start,
            label_window_end=self.period_end,
            confirmed_case_count=1,
            outbreak_label=SurveillanceOutbreakLabel.ACTIVE,
            label_truth_level=SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE,
            generation_mode="production_gate_source_backed_fixture",
            source_coverage_summary={
                "coverage_mode": "source_covered",
                "record_count": 1,
                "source_record_refs": [surveillance_ref],
                "record_ids": [self.surveillance_record.id],
            },
            generated_from_record_refs=[surveillance_ref],
            source_record_count=1,
        )
        FeatureDatasetRow.objects.create(
            dataset=self.label_dataset,
            ward=self.ward,
            ward_name_snapshot=self.ward.name,
            month=8,
            feature_values=self._feature_values(include_label=True),
            label=1,
        )
        self.training_row = self._dataset_row(self.training_dataset, include_label=True)
        self.inference_row = self._dataset_row(self.inference_dataset)
        self.model_run = self._model_run("production-gate-v1")
        self.risk_score = self._risk_score(self.model_run, generated_at=timezone.now())
        self.registry_entry = ensure_registry_entry_for_promoted_run(
            model_run=self.model_run,
            promoted_by="production-gate-test",
            owner="production-gate-test",
        )
        self.admin = User.objects.create_user(
            username="production-gate-admin",
            password="ChangeMe123!",
            role=User.ROLE_ADMIN,
            ward=self.ward,
        )

    def _dataset(self, kind: str) -> FeatureDataset:
        dataset_kind = (
            FeatureDataset.KIND_TRAINING
            if kind == "training"
            else FeatureDataset.KIND_INFERENCE
        )
        return FeatureDataset.objects.create(
            dataset_ref=f"production-gate-{kind}",
            dataset_kind=dataset_kind,
            schema_version="production-gate-v1",
            source_kind=FeatureDataset.SOURCE_KIND_LIVE,
            month=8,
            row_count=1,
            lineage_metadata=self._lineage_metadata(include_climate=True),
        )

    def _lineage_metadata(self, *, include_climate: bool) -> dict:
        surveillance_ref = f"surveillance_record:{self.surveillance_record.id}"
        climate_ref = getattr(self, "climate_record", None)
        climate_ref = f"climate_record:{climate_ref.id}" if climate_ref is not None else None
        source_record_refs = [surveillance_ref]
        if include_climate and climate_ref:
            source_record_refs.append(climate_ref)
        return {
            "source_record_refs": source_record_refs,
            "surveillance_record_refs": [surveillance_ref],
            "surveillance_truth_gate": {"proxy_only_as_confirmed_allowed": False},
            "source_lineage": {"source_record_refs": source_record_refs},
            "rainfall_source_lineage": {"source_record_refs": [climate_ref]} if climate_ref else {},
        }

    def _feature_values(self, *, include_label: bool = False) -> dict:
        surveillance_ref = f"surveillance_record:{self.surveillance_record.id}"
        climate_ref = f"climate_record:{self.climate_record.id}"
        values = {
            "population_total": 1000,
            "synthetic_rainfall_fallback_used": False,
            "synthetic_population_fallback_used": False,
            "source_record_refs": [surveillance_ref, climate_ref],
            "surveillance_record_refs": [surveillance_ref],
            "climate_record_refs": [climate_ref],
            "rainfall_source_lineage": {"source_record_refs": [climate_ref]},
        }
        if include_label:
            values.update(
                {
                    "label_window_id": self.label_window.id,
                    "surveillance_label_window_ref": f"surveillance_label_window:{self.label_window.id}",
                    "generated_from_record_refs": [surveillance_ref],
                    "suspected_case_count": 0,
                    "confirmed_case_count": 1,
                    "proxy_case_count": 0,
                    "source_record_count": 1,
                    "label_truth_level": SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE,
                    "outbreak_label": SurveillanceOutbreakLabel.ACTIVE,
                }
            )
        return values

    def _dataset_row(self, dataset: FeatureDataset, *, include_label: bool = False) -> FeatureDatasetRow:
        return FeatureDatasetRow.objects.create(
            dataset=dataset,
            ward=self.ward,
            ward_name_snapshot=self.ward.name,
            month=8,
            feature_values=self._feature_values(include_label=include_label),
            label=1 if include_label else None,
        )

    def _model_run(self, model_version: str, *, status: str = ModelRun.STATUS_SUCCESS) -> ModelRun:
        return ModelRun.objects.create(
            algorithm_name="logistic-regression-baseline",
            model_version=model_version,
            status=status,
            month=8,
            feature_schema_version="production-gate-v1",
            training_dataset_ref=self.training_dataset.dataset_ref,
            inference_dataset_ref=self.inference_dataset.dataset_ref,
            training_row_count=1,
            inference_row_count=1,
            training_feature_dataset=self.training_dataset,
            inference_feature_dataset=self.inference_dataset,
            rainfall_ingestion_run=self.rainfall_run,
            metadata={
                "algorithm": "logistic_regression",
                "promotion_target": "live_baseline",
                "promotion_state": "promoted",
                "phase_4_promotion_gates_passed": True,
                "alert_eligible": True,
                "surveillance_label_dataset_ref": self.label_dataset.dataset_ref,
            },
            completed_at=timezone.now() if status == ModelRun.STATUS_SUCCESS else None,
        )

    def _risk_score(self, model_run: ModelRun | None, *, generated_at=None) -> RiskScore:
        return RiskScore.objects.create(
            ward=self.ward,
            model_run=model_run,
            score=0.91,
            risk_level=Ward.RISK_HIGH,
            rainfall_mm=120,
            flood_indicator=0.8,
            predicted_cases=12,
            source=RiskScore.SOURCE_MODEL if model_run else RiskScore.SOURCE_MANUAL,
            model_version=model_run.model_version if model_run else "manual",
            generated_at=generated_at or timezone.now(),
        )

    def test_clean_promoted_score_is_eligible_and_creates_dashboard_alert(self):
        self.assertEqual(production_alert_eligibility_blockers(self.risk_score), [])
        self.assertEqual(ClimateRecord.objects.filter(ingestion_run=self.rainfall_run).count(), 1)
        self.assertEqual(
            SurveillanceRecord.objects.filter(ingestion_run=self.surveillance_ingestion_run).count(),
            1,
        )

        alerts = create_alerts_for_riskscore(self.risk_score)

        self.assertEqual(len(alerts), 1)
        self.assertEqual(Alert.objects.filter(risk_score=self.risk_score).count(), 1)
        self.assertEqual(AlertWorkflowState.objects.filter(ward=self.ward).count(), 1)

    def test_missing_canonical_feature_reference_is_blocked(self):
        self.inference_row.feature_values = {
            "population_total": 1000,
            "synthetic_rainfall_fallback_used": False,
            "synthetic_population_fallback_used": False,
        }
        self.inference_row.save(update_fields=["feature_values"])

        blockers = production_model_run_blockers(self.model_run)

        self.assertIn(PRODUCTION_CANONICAL_REFERENCE_REQUIRED, blockers)

    def test_model_run_without_label_dataset_reference_is_blocked(self):
        self.model_run.metadata = {
            key: value
            for key, value in self.model_run.metadata.items()
            if key != "surveillance_label_dataset_ref"
        }
        self.model_run.save(update_fields=["metadata"])

        blockers = production_model_run_blockers(self.model_run)

        self.assertIn(PRODUCTION_CANONICAL_REFERENCE_REQUIRED, blockers)

    def test_cross_ward_climate_reference_is_blocked(self):
        other_ward = Ward.objects.create(
            name="Other Production Gate Ward",
            county="Migori",
            ward_code="PROD-GATE-002",
        )
        other_climate_record = ClimateRecord.objects.create(
            ward=other_ward,
            ingestion_run=self.rainfall_run,
            record_type=ClimateRecordType.OBSERVED,
            source_provider="production-gate-rainfall-provider",
            source_kind=IngestionRun.SOURCE_KIND_LIVE,
            source_mode="live",
            valid_date=self.period_end,
            observed_timestamp=timezone.now(),
            rainfall_mm=80.0,
            quality_flag=ClimateRecordQualityFlag.ACCEPTED,
            fallback_flag=False,
            source_run="production-gate-live-rainfall-v1",
            source_ref="production-gate-climate-record-other-ward-v1",
        )
        self.inference_row.feature_values = {
            **self.inference_row.feature_values,
            "source_record_refs": [
                f"surveillance_record:{self.surveillance_record.id}",
                f"climate_record:{other_climate_record.id}",
            ],
            "climate_record_refs": [f"climate_record:{other_climate_record.id}"],
            "rainfall_source_lineage": {
                "source_record_refs": [f"climate_record:{other_climate_record.id}"]
            },
        }
        self.inference_row.save(update_fields=["feature_values"])

        blockers = production_model_run_blockers(self.model_run)

        self.assertIn(PRODUCTION_CANONICAL_REFERENCE_INVALID, blockers)

    def test_proxy_only_records_cannot_support_confirmed_label(self):
        self.surveillance_record.case_class = SurveillanceCaseClass.PROXY
        self.surveillance_record.disease_category = SurveillanceDiseaseCategory.DIARRHEAL
        self.surveillance_record.truth_level = SurveillanceTruthLevel.PROXY_DIARRHEAL_SIGNAL
        self.surveillance_record.save(update_fields=["case_class", "disease_category", "truth_level"])
        self.label_window.confirmed_case_count = 0
        self.label_window.proxy_case_count = 1
        self.label_window.save(update_fields=["confirmed_case_count", "proxy_case_count"])

        blockers = production_model_run_blockers(self.model_run)

        self.assertIn(PRODUCTION_PROXY_NOT_CONFIRMED, blockers)

    def test_model_less_score_is_rejected_before_workflow_or_task_mutation(self):
        manual_score = self._risk_score(
            None,
            generated_at=timezone.now() + timedelta(seconds=1),
        )
        force_authenticate_with_step_up(
            self.client,
            self.admin,
            StepUpGrant.PURPOSE_ALERT_DELIVERY,
        )

        with (
            patch("risk.views.sync_alert_workflow_for_ward") as workflow_sync,
            patch("risk.views.trigger_alerts_task.delay") as task_delay,
        ):
            response = self.client.post(
                reverse("trigger-alerts"),
                {
                    "ward_id": self.ward.id,
                    "send_sms": False,
                    "trigger_type": "HIGH_RISK_ESCALATION",
                },
                format="json",
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["code"], PRODUCTION_ALERT_ELIGIBILITY_BLOCKED)
        self.assertIn(PRODUCTION_ALERT_MODEL_RUN_REQUIRED, response.data["reason_codes"])
        workflow_sync.assert_not_called()
        task_delay.assert_not_called()
        self.assertEqual(Alert.objects.filter(risk_score=manual_score).count(), 0)
        self.assertEqual(AlertWorkflowState.objects.filter(ward=self.ward).count(), 0)

    def test_failed_model_run_is_rejected_with_stable_reason(self):
        failed_run = self._model_run("production-gate-failed-v1", status=ModelRun.STATUS_FAILED)
        failed_score = self._risk_score(failed_run)

        with self.assertRaises(ProductionTruthPolicyError) as context:
            create_alerts_for_riskscore(failed_score)

        self.assertEqual(context.exception.code, PRODUCTION_ALERT_ELIGIBILITY_BLOCKED)
        self.assertIn(PRODUCTION_ALERT_MODEL_RUN_NOT_SUCCESS, context.exception.reason_codes)
        self.assertEqual(Alert.objects.filter(risk_score=failed_score).count(), 0)

    def test_successful_but_unpromoted_model_run_is_rejected(self):
        unpromoted_run = self._model_run("production-gate-unpromoted-v1")
        unpromoted_score = self._risk_score(unpromoted_run)

        with self.assertRaises(ProductionTruthPolicyError) as context:
            create_alerts_for_riskscore(unpromoted_score)

        self.assertIn(PRODUCTION_ALERT_ACTIVE_REGISTRY_REQUIRED, context.exception.reason_codes)
        self.assertEqual(Alert.objects.filter(risk_score=unpromoted_score).count(), 0)

    def test_blocked_model_run_cannot_create_alerts(self):
        self.model_run.metadata = {**self.model_run.metadata, "seeded": True}
        self.model_run.save(update_fields=["metadata"])

        with self.assertRaises(ProductionTruthPolicyError):
            create_alerts_for_riskscore(self.risk_score)

        self.assertEqual(Alert.objects.count(), 0)
        self.assertEqual(AlertWorkflowState.objects.count(), 0)

    def test_task_rechecks_model_less_score_before_service(self):
        manual_score = self._risk_score(
            None,
            generated_at=timezone.now() + timedelta(seconds=1),
        )

        with self.assertRaises(ProductionTruthPolicyError) as context:
            trigger_alerts_task.run(manual_score.id)

        self.assertIn(PRODUCTION_ALERT_MODEL_RUN_REQUIRED, context.exception.reason_codes)
        self.assertEqual(Alert.objects.count(), 0)

    def test_synthetic_rows_invalid_wards_and_proxy_confirmed_claims_are_blocked(self):
        self.inference_row.feature_values = {
            **self.inference_row.feature_values,
            "synthetic_rainfall_fallback_used": True,
        }
        self.inference_row.save(update_fields=["feature_values"])
        blockers = production_model_run_blockers(self.model_run)
        self.assertIn(PRODUCTION_SYNTHETIC_FEATURE_FALLBACK_BLOCKED, blockers)

        self.inference_row.feature_values = {
            **self.inference_row.feature_values,
            "synthetic_rainfall_fallback_used": False,
        }
        self.inference_row.save(update_fields=["feature_values"])
        self.ward.is_active = False
        self.ward.save(update_fields=["is_active"])
        blockers = production_model_run_blockers(self.model_run)
        self.assertIn(PRODUCTION_INVALID_FEATURE_ROW_BLOCKED, blockers)

        self.ward.is_active = True
        self.ward.save(update_fields=["is_active"])
        self.inference_dataset.lineage_metadata = {
            "surveillance_truth_gate": {"proxy_only_as_confirmed_allowed": True}
        }
        self.inference_dataset.save(update_fields=["lineage_metadata"])
        blockers = production_model_run_blockers(self.model_run)
        self.assertIn(PRODUCTION_PROXY_NOT_CONFIRMED, blockers)

    def test_dataset_reference_to_superseded_surveillance_record_is_blocked(self):
        source = SurveillanceSource.objects.create(
            source_name="Production gate surveillance",
            source_type=SurveillanceSource.SOURCE_TYPE_WEEKLY_AGGREGATE,
        )
        ingestion_run = SurveillanceIngestionRun.objects.create(
            source=source,
            status=SurveillanceIngestionRun.STATUS_SUCCESS,
            source_name=source.source_name,
            source_type=source.source_type,
        )
        original = SurveillanceRecord.objects.create(
            ward=self.ward,
            ingestion_run=ingestion_run,
            source=source,
            disease_category=SurveillanceDiseaseCategory.CHOLERA,
            case_class=SurveillanceCaseClass.SUSPECTED,
            count_value=2,
            reporting_period_start=date(2026, 7, 1),
            reporting_period_end=date(2026, 7, 7),
            truth_level=SurveillanceTruthLevel.SUSPECTED_SURVEILLANCE,
            source_name=source.source_name,
            source_kind=SurveillanceSourceKind.LIVE,
            freshness_state=SurveillanceFreshnessState.FRESH,
            source_ref="production-gate-original",
        )
        SurveillanceRecord.objects.create(
            ward=self.ward,
            ingestion_run=ingestion_run,
            source=source,
            disease_category=SurveillanceDiseaseCategory.CHOLERA,
            case_class=SurveillanceCaseClass.SUSPECTED,
            count_value=3,
            reporting_period_start=date(2026, 7, 1),
            reporting_period_end=date(2026, 7, 7),
            truth_level=SurveillanceTruthLevel.SUSPECTED_SURVEILLANCE,
            source_name=source.source_name,
            source_kind=SurveillanceSourceKind.LIVE,
            freshness_state=SurveillanceFreshnessState.FRESH,
            supersedes_record_ref=f"surveillance_record:{original.id}",
            source_ref="production-gate-amendment",
        )
        self.training_row.feature_values = {
            **self.training_row.feature_values,
            "generated_from_record_refs": [f"surveillance_record:{original.id}"],
        }
        self.training_row.save(update_fields=["feature_values"])
        label_dataset = FeatureDataset.objects.create(
            dataset_ref="production-gate-superseded-label",
            dataset_kind=FeatureDataset.KIND_TRAINING,
            source_kind=FeatureDataset.SOURCE_KIND_LIVE,
            schema_version="production-gate-label-v1",
            month=8,
            lineage_metadata={},
        )
        SurveillanceLabelWindow.objects.create(
            ward=self.ward,
            feature_dataset=label_dataset,
            label_window_start=date(2026, 7, 1),
            label_window_end=date(2026, 7, 7),
            label_truth_level=SurveillanceTruthLevel.SUSPECTED_SURVEILLANCE,
            outbreak_label=SurveillanceOutbreakLabel.WATCH,
            generated_from_record_refs=[f"surveillance_record:{original.id}"],
            source_record_count=1,
        )
        self.model_run.metadata = {
            **self.model_run.metadata,
            "surveillance_label_dataset_ref": label_dataset.dataset_ref,
        }
        self.model_run.save(update_fields=["metadata"])

        blockers = production_model_run_blockers(self.model_run)

        self.assertIn(PRODUCTION_SUPERSEDED_TRUTH_BLOCKED, blockers)

    def test_blocked_production_pipeline_persists_failed_run_without_scores_or_alerts(self):
        self.inference_row.feature_values = {
            **self.inference_row.feature_values,
            "synthetic_population_fallback_used": True,
        }
        self.inference_row.save(update_fields=["feature_values"])
        training_dataset = TrainingDataset(rows=[SimpleNamespace()], feature_dataset=self.training_dataset)
        inference_dataset = InferenceDataset(
            rows=[SimpleNamespace()],
            feature_dataset=self.inference_dataset,
            rainfall_ingestion_run=self.rainfall_run,
        )
        model_run_count = ModelRun.objects.count()
        risk_score_count = RiskScore.objects.count()

        with (
            patch("risk.ml.pipeline.build_training_feature_dataset", return_value=training_dataset),
            patch("risk.ml.pipeline.build_inference_feature_dataset", return_value=inference_dataset),
            patch("risk.ml.pipeline.build_operational_trust_snapshot", return_value={}),
            patch("risk.ml.pipeline.predictions_blocked_for_snapshot", return_value=False),
        ):
            scores = run_mock_prediction_pipeline(
                month=8,
                model_version="production-gate-blocked-v1",
                trigger_alerts=True,
            )

        self.assertEqual(scores, [])
        self.assertEqual(ModelRun.objects.count(), model_run_count + 1)
        self.assertEqual(RiskScore.objects.count(), risk_score_count)
        blocked_run = ModelRun.objects.get(model_version="production-gate-blocked-v1")
        self.assertEqual(blocked_run.status, ModelRun.STATUS_FAILED)
        self.assertIn(
            PRODUCTION_SYNTHETIC_FEATURE_FALLBACK_BLOCKED,
            blocked_run.metadata["production_truth_policy"]["blocked_reason_codes"],
        )
        self.assertEqual(Alert.objects.count(), 0)
