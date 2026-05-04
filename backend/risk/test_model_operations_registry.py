import json
from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from risk.ml.alignment import is_promoted_model_run
from risk.ml.comparison import record_champion_challenger_comparison
from risk.ml.monitoring import (
    METRIC_CALIBRATION_DRIFT,
    METRIC_FEATURE_DISTRIBUTION_DRIFT,
    METRIC_PRECISION_DECAY,
    METRIC_RECALL_DECAY,
    METRIC_SOURCE_QUALITY_DRIFT,
    MODEL_MONITORING_THRESHOLD_VERSION,
    run_model_monitoring,
)
from risk.ml.model_health import build_model_operations_health_dashboard
from risk.ml.model_ops_audit import build_model_operations_audit
from risk.ml.operations_inventory import build_model_ops_state_inventory
from risk.ml.registry import (
    active_model_registry_entry,
    ensure_registry_entry_for_promoted_run,
    execute_model_rollback,
    record_model_rollback,
)
from risk.ml.retraining_policy import evaluate_retraining_policy
from risk.models import (
    Alert,
    FeatureDataset,
    FeatureDatasetRow,
    ModelChallengerBenchmarkStatus,
    ModelChampionChallengerComparison,
    ModelMonitoringSnapshot,
    ModelMonitoringState,
    ModelMonitoringThreshold,
    ModelMonitoringThresholdDirection,
    ModelPromotionEvent,
    ModelRegistryEntry,
    ModelRegistryMonitoringState,
    ModelRegistryPromotionState,
    ModelRollbackEvent,
    ModelRetrainingRecommendation,
    ModelRetrainingRecommendationState,
    ModelRun,
    RiskScore,
    SurveillanceLabelWindow,
    SurveillanceOutbreakLabel,
    SurveillanceTruthLevel,
    Ward,
)
from risk.services import create_alerts_for_riskscore


class ModelOperationsTestHelpers:
    def setUp(self):
        self.ward = Ward.objects.create(
            name="Model Ops Ward",
            county="Migori",
            ward_code="MODEL-OPS",
        )

    def _dataset(self, dataset_ref: str, dataset_kind: str) -> FeatureDataset:
        return FeatureDataset.objects.create(
            dataset_ref=dataset_ref,
            dataset_kind=dataset_kind,
            schema_version="model-ops-test-v1",
            source_kind=FeatureDataset.SOURCE_KIND_LIVE,
            month=5,
            feature_keys=["prediction_date", "rainfall_total_14d"],
            row_count=1,
            lineage_metadata={"builder": "model-ops-test"},
        )

    def _promoted_run(self, model_version: str) -> ModelRun:
        training_dataset = self._dataset(f"{model_version}-training", FeatureDataset.KIND_TRAINING)
        inference_dataset = self._dataset(f"{model_version}-inference", FeatureDataset.KIND_INFERENCE)
        label_dataset = self._dataset(f"{model_version}-labels", FeatureDataset.KIND_TRAINING)
        model_run = ModelRun.objects.create(
            algorithm_name="logistic-regression-baseline",
            model_version=model_version,
            status=ModelRun.STATUS_SUCCESS,
            month=5,
            feature_schema_version="lead-time-feature-v1",
            training_feature_dataset=training_dataset,
            training_dataset_ref=training_dataset.dataset_ref,
            inference_feature_dataset=inference_dataset,
            inference_dataset_ref=inference_dataset.dataset_ref,
            training_row_count=12,
            inference_row_count=1,
            evaluation_metrics={
                "lead_time_recall": 0.92,
                "precision": 0.5,
                "calibration_score": 0.88,
                "temporal_backtest_report": {"label_dataset_ref": label_dataset.dataset_ref},
            },
            metadata={
                "algorithm": "logistic_regression",
                "promotion_target": "live_baseline",
                "promotion_state": "promoted",
                "phase_4_promotion_gates_passed": True,
                "alert_eligible": True,
                "promotion_evidence_report_ref": f"model_run:{model_version}:temporal_backtest_report",
                "ward_risk_classification_label_dataset_ref": label_dataset.dataset_ref,
            },
            completed_at=timezone.now(),
        )
        RiskScore.objects.create(
            ward=self.ward,
            model_run=model_run,
            score=0.82,
            risk_level=Ward.RISK_HIGH,
            predicted_cases=4,
            source=RiskScore.SOURCE_MODEL,
            model_version=model_version,
        )
        return model_run

    def _feature_row(self, dataset, ward, *, rainfall_total, label=None, quality_good=True):
        return FeatureDatasetRow.objects.create(
            dataset=dataset,
            ward=ward,
            ward_name_snapshot=ward.name,
            month=5,
            label=label,
            feature_values={
                "prediction_date": "2026-05-01",
                "season": "long_rains",
                "rainfall_total_14d": rainfall_total,
                "population_total": 10000,
                "fallback_static_rainfall_used": not quality_good,
                "climate_coverage_status": "sufficient" if quality_good else "insufficient_forecast_horizon",
            },
        )

    def _phase_two_ready_registry_entry(self):
        model_run = self._promoted_run("ops-phase2-v1")
        second_ward = Ward.objects.create(
            name="Model Ops Ward Two",
            county="Migori",
            ward_code="MODEL-OPS-2",
        )
        RiskScore.objects.create(
            ward=second_ward,
            model_run=model_run,
            score=0.20,
            risk_level=Ward.RISK_LOW,
            predicted_cases=0,
            source=RiskScore.SOURCE_MODEL,
            model_version=model_run.model_version,
        )

        self._feature_row(model_run.training_feature_dataset, self.ward, rainfall_total=10, quality_good=True)
        self._feature_row(model_run.training_feature_dataset, second_ward, rainfall_total=12, quality_good=True)
        self._feature_row(model_run.inference_feature_dataset, self.ward, rainfall_total=120, quality_good=False)
        self._feature_row(model_run.inference_feature_dataset, second_ward, rainfall_total=130, quality_good=False)

        label_dataset = FeatureDataset.objects.get(
            dataset_ref=model_run.metadata["ward_risk_classification_label_dataset_ref"]
        )
        self._feature_row(label_dataset, self.ward, rainfall_total=120, label=0, quality_good=True)
        self._feature_row(label_dataset, second_ward, rainfall_total=130, label=1, quality_good=True)
        entry = ensure_registry_entry_for_promoted_run(
            model_run=model_run,
            owner="model-ops",
            promoted_by="unit-test",
        )
        return entry, label_dataset

    def _challenger_run_for_entry(self, entry, label_dataset, *, model_version="rf-phase4-v1"):
        challenger_run = ModelRun.objects.create(
            algorithm_name="random-forest-benchmark",
            model_version=model_version,
            status=ModelRun.STATUS_SUCCESS,
            month=entry.model_run.month,
            feature_schema_version=entry.model_run.feature_schema_version,
            training_feature_dataset=entry.model_run.training_feature_dataset,
            training_dataset_ref=entry.model_run.training_dataset_ref,
            inference_feature_dataset=entry.model_run.inference_feature_dataset,
            inference_dataset_ref=entry.model_run.inference_dataset_ref,
            training_row_count=entry.model_run.training_row_count,
            inference_row_count=entry.model_run.inference_row_count,
            evaluation_metrics={
                "training_accuracy": 0.94,
                "out_of_time_score": 0.79,
                "lead_time_recall": 0.9,
                "precision": 0.55,
                "balanced_accuracy": 0.77,
                "false_alerts_per_true_hit": 1.2,
                "positive_class_balance": 0.5,
                "calibration_score": 0.84,
                "lead_time_days_supported": [7, 14],
                "temporal_validation_window_count": 2,
                "phase_4_training_truth_gate_passed": True,
                "climate_coverage_gate_passed": True,
                "temporal_backtest_report": {"label_dataset_ref": label_dataset.dataset_ref},
            },
            metadata={
                "algorithm": "random_forest",
                "run_role": "benchmark",
                "run_purpose": "benchmark_scoring",
                "promotion_target": "benchmark_only",
                "promotion_state": "benchmark_only",
                "alert_eligible": False,
                "benchmark_group_ref": "phase4-model-ops",
                "ward_risk_classification_label_dataset_ref": label_dataset.dataset_ref,
            },
            completed_at=timezone.now(),
        )
        for risk_score in RiskScore.objects.filter(model_run=entry.model_run).select_related("ward"):
            RiskScore.objects.create(
                ward=risk_score.ward,
                model_run=challenger_run,
                score=min(risk_score.score + 0.03, 0.99),
                risk_level=risk_score.risk_level,
                predicted_cases=risk_score.predicted_cases,
                source=RiskScore.SOURCE_MODEL,
                model_version=challenger_run.model_version,
                notes="Phase 4 benchmark-only challenger output.",
            )
        return challenger_run

    def _phase_five_rollback_entries(self):
        first_run = self._promoted_run("ops-phase5-v1")
        first_score = RiskScore.objects.get(model_run=first_run, ward=self.ward)
        first_score.score = 0.22
        first_score.risk_level = Ward.RISK_LOW
        first_score.predicted_cases = 0
        first_score.save(update_fields=["score", "risk_level", "predicted_cases"])
        first_entry = ensure_registry_entry_for_promoted_run(
            model_run=first_run,
            owner="model-ops",
            promoted_by="unit-test",
        )

        second_run = self._promoted_run("ops-phase5-v2")
        second_score = RiskScore.objects.get(model_run=second_run, ward=self.ward)
        second_score.score = 0.91
        second_score.risk_level = Ward.RISK_HIGH
        second_score.predicted_cases = 9
        second_score.save(update_fields=["score", "risk_level", "predicted_cases"])
        second_entry = ensure_registry_entry_for_promoted_run(
            model_run=second_run,
            owner="model-ops",
            promoted_by="unit-test",
        )

        self.ward.current_risk_level = Ward.RISK_HIGH
        self.ward.current_risk_score = 0.91
        self.ward.save(update_fields=["current_risk_level", "current_risk_score", "updated_at"])
        return first_entry, second_entry, first_score, second_score


class ModelOperationsRegistryPhaseZeroOneTests(ModelOperationsTestHelpers, TestCase):
    def test_phase_zero_inventory_documents_legacy_gaps_and_state_boundaries(self):
        self._promoted_run("ops-phase0-v1")

        inventory = build_model_ops_state_inventory()

        self.assertEqual(inventory["schema_version"], "ward-risk-model-ops-state-inventory-v1")
        self.assertIn("model_registry_entry_missing_for_promoted_run", inventory["gaps"])
        self.assertIn("score_distribution_baselines_not_persisted_until_phase_2_monitoring", inventory["gaps"])
        self.assertEqual(
            inventory["state_boundaries"]["operations_source_of_truth"],
            "ModelRegistryEntry is the active/retired post-promotion registry state.",
        )
        promoted_question = next(
            question for question in inventory["questions"] if question["id"] == "how_is_the_promoted_model_identified"
        )
        self.assertEqual(promoted_question["status"], "warning")

    def test_phase_one_registry_sync_creates_active_entry_and_queryable_rollback_target(self):
        first_run = self._promoted_run("ops-phase1-v1")
        first_entry = ensure_registry_entry_for_promoted_run(
            model_run=first_run,
            owner="model-ops",
            promoted_by="unit-test",
        )
        self.assertEqual(first_entry.promotion_state, ModelRegistryPromotionState.ACTIVE_PROMOTED)
        self.assertEqual(first_entry.algorithm, "logistic_regression")
        self.assertIsNotNone(first_entry.promotion_event)
        self.assertIsNone(first_entry.rollback_target)
        self.assertTrue(is_promoted_model_run(first_run))

        second_run = self._promoted_run("ops-phase1-v2")
        second_entry = ensure_registry_entry_for_promoted_run(
            model_run=second_run,
            owner="model-ops",
            promoted_by="unit-test",
            review_due_date=timezone.localdate() + timedelta(days=30),
        )

        first_entry.refresh_from_db()
        second_entry.refresh_from_db()
        self.assertEqual(first_entry.promotion_state, ModelRegistryPromotionState.RETIRED)
        self.assertIsNotNone(first_entry.active_until)
        self.assertEqual(second_entry.rollback_target, first_entry)
        self.assertEqual(active_model_registry_entry(), second_entry)
        self.assertEqual(ModelRegistryEntry.objects.count(), 2)
        self.assertEqual(ModelPromotionEvent.objects.count(), 2)
        self.assertFalse(is_promoted_model_run(first_run))
        self.assertTrue(is_promoted_model_run(second_run))

    def test_sync_command_backfills_selected_promoted_model_run(self):
        model_run = self._promoted_run("ops-sync-command-v1")
        output = StringIO()

        call_command(
            "sync_model_registry_entry",
            "--model-run-id",
            str(model_run.id),
            "--owner",
            "model-ops",
            stdout=output,
        )

        entry = ModelRegistryEntry.objects.get(model_run=model_run)
        self.assertEqual(entry.promotion_state, ModelRegistryPromotionState.ACTIVE_PROMOTED)
        self.assertIn('"model_version": "ops-sync-command-v1"', output.getvalue())

    def test_phase_one_resyncing_retired_model_starts_new_active_window(self):
        first_run = self._promoted_run("ops-phase1-window-v1")
        first_entry = ensure_registry_entry_for_promoted_run(
            model_run=first_run,
            owner="model-ops",
            promoted_by="unit-test",
        )
        original_active_from = first_entry.active_from
        second_run = self._promoted_run("ops-phase1-window-v2")
        second_entry = ensure_registry_entry_for_promoted_run(
            model_run=second_run,
            owner="model-ops",
            promoted_by="unit-test",
        )
        first_entry.refresh_from_db()
        self.assertEqual(first_entry.promotion_state, ModelRegistryPromotionState.RETIRED)
        self.assertIsNotNone(first_entry.active_until)

        reactivated_entry = ensure_registry_entry_for_promoted_run(
            model_run=first_run,
            owner="model-ops",
            promoted_by="unit-test-reactivation",
            source="manual_model_ops_sync",
        )

        reactivated_entry.refresh_from_db()
        second_entry.refresh_from_db()
        latest_event = reactivated_entry.promotion_events.order_by("-occurred_at", "-id").first()
        self.assertEqual(reactivated_entry.promotion_state, ModelRegistryPromotionState.ACTIVE_PROMOTED)
        self.assertGreater(reactivated_entry.active_from, original_active_from)
        self.assertEqual(reactivated_entry.rollback_target, second_entry)
        self.assertEqual(second_entry.promotion_state, ModelRegistryPromotionState.RETIRED)
        self.assertEqual(latest_event.previous_registry_entry, second_entry)
        self.assertEqual(latest_event.active_from, reactivated_entry.active_from)

    def test_phase_one_active_registry_entry_requires_open_active_window_at_database_level(self):
        missing_start_run = self._promoted_run("ops-phase1-db-window-missing-start-v1")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ModelRegistryEntry.objects.create(
                    algorithm="logistic_regression",
                    model_version=missing_start_run.model_version,
                    model_run=missing_start_run,
                    promotion_state=ModelRegistryPromotionState.ACTIVE_PROMOTED,
                    active_from=None,
                    active_until=None,
                    owner="model-ops",
                )

        closed_window_run = self._promoted_run("ops-phase1-db-window-closed-v1")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ModelRegistryEntry.objects.create(
                    algorithm="logistic_regression",
                    model_version=closed_window_run.model_version,
                    model_run=closed_window_run,
                    promotion_state=ModelRegistryPromotionState.ACTIVE_PROMOTED,
                    active_from=timezone.now() - timedelta(days=1),
                    active_until=timezone.now(),
                    owner="model-ops",
                )

    def test_phase_one_active_registry_entry_without_promotion_event_is_not_live(self):
        model_run = self._promoted_run("ops-phase1-no-promotion-event-v1")
        risk_score = RiskScore.objects.get(model_run=model_run, ward=self.ward)
        ModelRegistryEntry.objects.create(
            algorithm="logistic_regression",
            model_version=model_run.model_version,
            model_run=model_run,
            promotion_state=ModelRegistryPromotionState.ACTIVE_PROMOTED,
            active_from=timezone.now(),
            active_until=None,
            owner="model-ops",
        )

        payload = build_model_operations_audit()
        checks = {check["id"]: check for check in payload["checks"]}

        self.assertIsNone(active_model_registry_entry())
        self.assertFalse(is_promoted_model_run(model_run))
        with self.assertRaisesMessage(ValueError, "Alerts can only be created for the active promoted model run."):
            create_alerts_for_riskscore(risk_score)
        self.assertEqual(payload["overall_status"], "fail")
        self.assertEqual(
            checks["registry_active_model_missing_promotion_event_provenance"]["status"],
            "fail",
        )


class ModelOperationsMonitoringPhaseTwoTests(ModelOperationsTestHelpers, TestCase):
    def test_phase_two_monitoring_persists_drift_calibration_and_label_snapshots(self):
        entry, label_dataset = self._phase_two_ready_registry_entry()

        snapshots = run_model_monitoring(registry_entry=entry, label_dataset_ref=label_dataset.dataset_ref)

        self.assertEqual(len(snapshots), 8)
        self.assertEqual(ModelMonitoringSnapshot.objects.count(), 8)
        self.assertEqual(ModelMonitoringThreshold.objects.count(), 8)
        self.assertEqual({snapshot.threshold_version for snapshot in snapshots}, {MODEL_MONITORING_THRESHOLD_VERSION})
        snapshot_by_metric = {snapshot.metric_name: snapshot for snapshot in snapshots}
        self.assertEqual(snapshot_by_metric[METRIC_FEATURE_DISTRIBUTION_DRIFT].state, ModelMonitoringState.BREACHED)
        self.assertEqual(snapshot_by_metric[METRIC_CALIBRATION_DRIFT].state, ModelMonitoringState.BREACHED)
        self.assertEqual(snapshot_by_metric[METRIC_RECALL_DECAY].state, ModelMonitoringState.BREACHED)
        self.assertEqual(snapshot_by_metric[METRIC_PRECISION_DECAY].state, ModelMonitoringState.BREACHED)
        self.assertEqual(snapshot_by_metric[METRIC_SOURCE_QUALITY_DRIFT].state, ModelMonitoringState.WARNING)
        self.assertIn(
            f"feature_dataset:{label_dataset.dataset_ref}",
            snapshot_by_metric[METRIC_CALIBRATION_DRIFT].source_dataset_refs,
        )
        entry.refresh_from_db()
        self.assertEqual(entry.monitoring_state, ModelRegistryMonitoringState.BREACHED)
        self.assertIn("latest_monitoring_run_id", entry.metadata)
        self.assertIn("score_distribution_baseline_mean", entry.metadata)

    def test_run_model_monitoring_command_emits_snapshot_summary(self):
        entry, label_dataset = self._phase_two_ready_registry_entry()
        output = StringIO()

        call_command(
            "run_model_monitoring",
            "--registry-entry-id",
            str(entry.id),
            "--label-dataset-ref",
            label_dataset.dataset_ref,
            stdout=output,
        )

        self.assertIn('"snapshot_count": 8', output.getvalue())
        self.assertIn(f'"threshold_version": "{MODEL_MONITORING_THRESHOLD_VERSION}"', output.getvalue())

    def test_phase_two_monitoring_preserves_operator_active_threshold_version(self):
        entry, label_dataset = self._phase_two_ready_registry_entry()
        custom_threshold = ModelMonitoringThreshold.objects.create(
            metric_name=METRIC_FEATURE_DISTRIBUTION_DRIFT,
            version="county-approved-v2",
            warning_threshold=0.01,
            breach_threshold=0.02,
            direction=ModelMonitoringThresholdDirection.HIGHER_IS_WORSE,
            baseline_window="county_approved_feature_drift_window",
            is_active=True,
            metadata={"approved_by": "model-ops-review-board"},
        )

        snapshots = run_model_monitoring(registry_entry=entry, label_dataset_ref=label_dataset.dataset_ref)
        feature_snapshot = next(
            snapshot for snapshot in snapshots if snapshot.metric_name == METRIC_FEATURE_DISTRIBUTION_DRIFT
        )

        custom_threshold.refresh_from_db()
        self.assertTrue(custom_threshold.is_active)
        self.assertEqual(feature_snapshot.threshold, custom_threshold)
        self.assertEqual(feature_snapshot.threshold_version, "county-approved-v2")
        self.assertEqual(feature_snapshot.threshold_value, 0.02)


class ModelOperationsRetrainingPolicyPhaseThreeTests(ModelOperationsTestHelpers, TestCase):
    def _label_window(self, *, ward, risk_score, outbreak_label):
        return SurveillanceLabelWindow.objects.create(
            ward=ward,
            label_window_start=(risk_score.generated_at + timedelta(days=7)).date(),
            label_window_end=(risk_score.generated_at + timedelta(days=14)).date(),
            outbreak_label=outbreak_label,
            label_truth_level=SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE,
            suspected_case_count=8 if outbreak_label == SurveillanceOutbreakLabel.ACTIVE else 0,
            confirmed_case_count=2 if outbreak_label == SurveillanceOutbreakLabel.ACTIVE else 0,
            source_record_count=1,
        )

    def _phase_three_ready_entry(self):
        entry, label_dataset = self._phase_two_ready_registry_entry()
        run_model_monitoring(registry_entry=entry, label_dataset_ref=label_dataset.dataset_ref)
        old_active_from = timezone.now() - timedelta(days=120)
        entry.active_from = old_active_from
        entry.review_due_date = timezone.localdate() - timedelta(days=1)
        entry.save(update_fields=["active_from", "review_due_date", "updated_at"])
        high_risk_score = RiskScore.objects.get(model_run=entry.model_run, ward=self.ward)
        low_risk_ward = Ward.objects.get(ward_code="MODEL-OPS-2")
        low_risk_score = RiskScore.objects.get(model_run=entry.model_run, ward=low_risk_ward)
        Alert.objects.create(
            ward=self.ward,
            risk_score=high_risk_score,
            channel=Alert.CHANNEL_DASHBOARD,
            recipient="ops",
            message="Phase 3 review alert",
            status=Alert.STATUS_DELIVERED,
            sent_at=timezone.now(),
        )
        self._label_window(
            ward=self.ward,
            risk_score=high_risk_score,
            outbreak_label=SurveillanceOutbreakLabel.NONE,
        )
        self._label_window(
            ward=low_risk_ward,
            risk_score=low_risk_score,
            outbreak_label=SurveillanceOutbreakLabel.ACTIVE,
        )
        return entry

    def test_phase_three_policy_marks_review_required_and_records_retraining_recommendation(self):
        entry = self._phase_three_ready_entry()

        recommendation = evaluate_retraining_policy(
            registry_entry=entry,
            stale_model_max_days=90,
            new_label_volume_threshold=1,
            repeated_false_alert_threshold=1,
            repeated_miss_threshold=1,
        )

        self.assertEqual(
            recommendation.recommendation_state,
            ModelRetrainingRecommendationState.RETRAINING_RECOMMENDED,
        )
        self.assertIn("monitoring_threshold_breach", recommendation.reason_codes)
        self.assertIn("stale_model_age", recommendation.reason_codes)
        self.assertIn("new_surveillance_label_volume", recommendation.reason_codes)
        self.assertIn("repeated_false_alerts", recommendation.reason_codes)
        self.assertIn("repeated_misses", recommendation.reason_codes)
        self.assertEqual(recommendation.false_alert_count, 1)
        self.assertEqual(recommendation.miss_count, 1)
        self.assertFalse(recommendation.metadata["automatic_live_promotion_allowed"])
        self.assertTrue(recommendation.metadata["phase_4_promotion_gates_required"])
        entry.refresh_from_db()
        self.assertEqual(entry.monitoring_state, ModelRegistryMonitoringState.REVIEW_REQUIRED)
        self.assertTrue(entry.metadata["review_required"])
        self.assertEqual(entry.promotion_state, ModelRegistryPromotionState.ACTIVE_PROMOTED)
        self.assertEqual(ModelRetrainingRecommendation.objects.count(), 1)

    def test_evaluate_model_retraining_policy_command_emits_recommendation_summary(self):
        entry = self._phase_three_ready_entry()
        output = StringIO()

        call_command(
            "evaluate_model_retraining_policy",
            "--registry-entry-id",
            str(entry.id),
            "--new-label-volume-threshold",
            "1",
            "--repeated-false-alert-threshold",
            "1",
            "--repeated-miss-threshold",
            "1",
            stdout=output,
        )

        self.assertIn('"recommendation_state": "RETRAINING_RECOMMENDED"', output.getvalue())
        self.assertIn('"automatic_live_promotion_allowed": false', output.getvalue())


class ModelOperationsChampionChallengerPhaseFourTests(ModelOperationsTestHelpers, TestCase):
    def test_phase_four_records_benchmark_only_challenger_without_replacing_champion(self):
        entry, label_dataset = self._phase_two_ready_registry_entry()
        challenger_run = self._challenger_run_for_entry(entry, label_dataset)

        comparison = record_champion_challenger_comparison(
            champion_entry=entry,
            challenger_run=challenger_run,
        )

        self.assertEqual(comparison.champion_registry_entry, entry)
        self.assertEqual(comparison.champion_model_run, entry.model_run)
        self.assertEqual(comparison.challenger_model_run, challenger_run)
        self.assertEqual(comparison.benchmark_status, ModelChallengerBenchmarkStatus.BENCHMARK_ONLY)
        self.assertEqual(comparison.comparison_validity, "comparable_inputs")
        self.assertTrue(comparison.input_alignment["same_training_dataset"])
        self.assertTrue(comparison.input_alignment["same_inference_dataset"])
        self.assertTrue(comparison.input_alignment["same_feature_schema"])
        self.assertTrue(comparison.input_alignment["same_label_dataset"])
        self.assertEqual(comparison.operational_metrics["challenger"]["alert_count"], 0)
        self.assertFalse(comparison.dashboard_summary["challenger_outputs_affect_alerts"])
        self.assertFalse(comparison.dashboard_summary["challenger_outputs_update_current_ward_risk"])
        self.assertFalse(comparison.dashboard_summary["can_replace_champion_without_phase_4_promotion"])
        self.assertIn("operational_promotion_review_pending", comparison.promotion_blockers)

        entry.refresh_from_db()
        challenger_run.refresh_from_db()
        self.assertEqual(entry.promotion_state, ModelRegistryPromotionState.ACTIVE_PROMOTED)
        self.assertEqual(active_model_registry_entry(), entry)
        self.assertFalse(ModelRegistryEntry.objects.filter(model_run=challenger_run).exists())
        self.assertEqual(challenger_run.metadata["promotion_target"], "benchmark_only")
        self.assertFalse(challenger_run.metadata["alert_eligible"])
        self.assertFalse(challenger_run.metadata["challenger_outputs_affect_alerts"])
        self.assertEqual(ModelChampionChallengerComparison.objects.count(), 1)

    def test_record_champion_challenger_comparison_command_emits_safe_dashboard_summary(self):
        entry, label_dataset = self._phase_two_ready_registry_entry()
        challenger_run = self._challenger_run_for_entry(entry, label_dataset, model_version="rf-phase4-command-v1")
        output = StringIO()

        call_command(
            "record_champion_challenger_comparison",
            "--champion-registry-entry-id",
            str(entry.id),
            "--challenger-model-run-id",
            str(challenger_run.id),
            stdout=output,
        )
        payload = json.loads(output.getvalue())

        self.assertEqual(payload["benchmark_status"], "BENCHMARK_ONLY")
        self.assertEqual(payload["comparison_validity"], "comparable_inputs")
        self.assertEqual(payload["challenger_model_version"], "rf-phase4-command-v1")
        self.assertFalse(payload["dashboard_summary"]["challenger_outputs_affect_alerts"])
        self.assertFalse(payload["dashboard_summary"]["can_replace_champion_without_phase_4_promotion"])

    def test_phase_four_rejects_challenger_scores_already_linked_to_alerts(self):
        entry, label_dataset = self._phase_two_ready_registry_entry()
        challenger_run = self._challenger_run_for_entry(entry, label_dataset, model_version="rf-phase4-alert-v1")
        challenger_score = RiskScore.objects.filter(model_run=challenger_run).select_related("ward").first()
        Alert.objects.create(
            ward=challenger_score.ward,
            risk_score=challenger_score,
            channel=Alert.CHANNEL_DASHBOARD,
            recipient="ops",
            message="Unsafe challenger alert fixture",
            status=Alert.STATUS_DELIVERED,
            sent_at=timezone.now(),
        )

        with self.assertRaisesMessage(ValueError, "challenger_scores_already_used_for_alerts"):
            record_champion_challenger_comparison(
                champion_entry=entry,
                challenger_run=challenger_run,
            )

    def test_phase_four_comparison_cannot_use_champion_run_as_challenger_at_database_level(self):
        entry, _label_dataset = self._phase_two_ready_registry_entry()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ModelChampionChallengerComparison.objects.create(
                    champion_registry_entry=entry,
                    champion_model_run=entry.model_run,
                    challenger_model_run=entry.model_run,
                    challenger_algorithm=entry.algorithm,
                    challenger_model_version=entry.model_version,
                )


class ModelOperationsRollbackPhaseFiveTests(ModelOperationsTestHelpers, TestCase):
    def test_phase_five_rollback_updates_registry_materializes_risk_and_blocks_stale_alerts(self):
        first_entry, second_entry, first_score, second_score = self._phase_five_rollback_entries()

        event = execute_model_rollback(
            rolled_back_from=second_entry,
            rollback_target=first_entry,
            reason="Phase 5 safety rollback",
            rolled_back_by="ops-admin",
            authorized_role="model_operations",
        )

        first_entry.refresh_from_db()
        second_entry.refresh_from_db()
        self.ward.refresh_from_db()
        self.assertEqual(event.rollback_target, first_entry)
        self.assertEqual(event.rolled_back_from, second_entry)
        self.assertEqual(first_entry.promotion_state, ModelRegistryPromotionState.ACTIVE_PROMOTED)
        self.assertEqual(second_entry.promotion_state, ModelRegistryPromotionState.ROLLED_BACK)
        self.assertIsNotNone(second_entry.active_until)
        self.assertEqual(active_model_registry_entry(), first_entry)
        self.assertTrue(is_promoted_model_run(first_entry.model_run))
        self.assertFalse(is_promoted_model_run(second_entry.model_run))
        self.assertEqual(self.ward.current_risk_level, Ward.RISK_LOW)
        self.assertAlmostEqual(self.ward.current_risk_score, 0.22)
        self.assertEqual(event.metadata["current_risk_materialization"]["materialized_ward_count"], 1)
        self.assertTrue(event.metadata["alerts_respect_active_registry_state"])

        active_alerts = create_alerts_for_riskscore(first_score)
        self.assertEqual(len(active_alerts), 1)
        with self.assertRaisesMessage(ValueError, "Alerts can only be created for the active promoted model run."):
            create_alerts_for_riskscore(second_score)
        self.assertEqual(ModelRollbackEvent.objects.count(), 1)

    def test_perform_model_rollback_command_emits_auditable_summary(self):
        first_entry, second_entry, _first_score, _second_score = self._phase_five_rollback_entries()
        output = StringIO()

        call_command(
            "perform_model_rollback",
            "--rolled-back-from-registry-entry-id",
            str(second_entry.id),
            "--rollback-target-registry-entry-id",
            str(first_entry.id),
            "--reason",
            "Command rollback",
            "--rolled-back-by",
            "ops-admin",
            stdout=output,
        )
        payload = json.loads(output.getvalue())

        self.assertEqual(payload["rolled_back_from_registry_entry_id"], second_entry.id)
        self.assertEqual(payload["rollback_target_registry_entry_id"], first_entry.id)
        self.assertEqual(payload["new_active_model_version"], "ops-phase5-v1")
        self.assertEqual(payload["current_risk_materialization"]["materialized_ward_count"], 1)
        self.assertTrue(payload["alerts_respect_active_registry_state"])

    def test_phase_five_alert_guard_rejects_metadata_promoted_run_without_registry_when_registry_exists(self):
        active_run = self._promoted_run("ops-phase5-active-registry-v1")
        ensure_registry_entry_for_promoted_run(
            model_run=active_run,
            owner="model-ops",
            promoted_by="unit-test",
        )
        legacy_run = self._promoted_run("ops-phase5-legacy-no-registry-v1")
        legacy_score = RiskScore.objects.get(model_run=legacy_run, ward=self.ward)

        with self.assertRaisesMessage(ValueError, "Alerts can only be created for the active promoted model run."):
            create_alerts_for_riskscore(legacy_score)

    def test_phase_five_rollback_event_constraints_block_direct_invalid_writes(self):
        first_entry, second_entry, _first_score, _second_score = self._phase_five_rollback_entries()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ModelRollbackEvent.objects.create(
                    rolled_back_from=second_entry,
                    rollback_target=second_entry,
                    rolled_back_by="unit-test",
                    reason="Same target fixture",
                )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ModelRollbackEvent.objects.create(
                    rolled_back_from=second_entry,
                    rollback_target=first_entry,
                    rolled_back_by="unit-test",
                    reason="   ",
                )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ModelRollbackEvent.objects.create(
                    rolled_back_from=second_entry,
                    rollback_target=first_entry,
                    rolled_back_by="   ",
                    reason="Missing operator fixture",
                )

    def test_phase_five_record_model_rollback_rejects_non_promoted_target(self):
        entry, label_dataset = self._phase_two_ready_registry_entry()
        challenger_run = self._challenger_run_for_entry(entry, label_dataset, model_version="rf-phase5-bad-target-v1")
        bad_target = ModelRegistryEntry.objects.create(
            algorithm="random_forest",
            model_version=challenger_run.model_version,
            model_run=challenger_run,
            promotion_state=ModelRegistryPromotionState.RETIRED,
            active_from=timezone.now() - timedelta(days=30),
            active_until=timezone.now() - timedelta(days=1),
            owner="model-ops",
            metadata={"fixture": "phase_5_record_model_rollback_invalid_target"},
        )

        with self.assertRaisesMessage(ValueError, "rollback_target_not_phase_4_promoted"):
            record_model_rollback(
                rolled_back_from=entry,
                rollback_target=bad_target,
                reason="Invalid public helper target",
                rolled_back_by="unit-test",
            )

    def test_phase_five_record_model_rollback_rejects_phase4_target_without_promotion_event(self):
        entry, _label_dataset = self._phase_two_ready_registry_entry()
        target_run = self._promoted_run("ops-phase5-no-target-event-v1")
        bad_target = ModelRegistryEntry.objects.create(
            algorithm="logistic_regression",
            model_version=target_run.model_version,
            model_run=target_run,
            promotion_state=ModelRegistryPromotionState.RETIRED,
            active_from=timezone.now() - timedelta(days=30),
            active_until=timezone.now() - timedelta(days=1),
            owner="model-ops",
            metadata={"fixture": "phase_5_missing_promotion_event"},
        )

        with self.assertRaisesMessage(ValueError, "rollback_target_missing_promotion_event"):
            record_model_rollback(
                rolled_back_from=entry,
                rollback_target=bad_target,
                reason="Invalid missing promotion-event target",
                rolled_back_by="unit-test",
            )


class ModelOperationsFrontendHealthPhaseSixTests(ModelOperationsTestHelpers, TestCase):
    def test_phase_six_health_dashboard_exposes_active_monitoring_challenger_and_rollback_state(self):
        first_entry, label_dataset = self._phase_two_ready_registry_entry()
        second_run = self._promoted_run("ops-phase6-v2")
        second_entry = ensure_registry_entry_for_promoted_run(
            model_run=second_run,
            owner="model-ops",
            promoted_by="unit-test",
        )
        execute_model_rollback(
            rolled_back_from=second_entry,
            rollback_target=first_entry,
            reason="Phase 6 dashboard rollback evidence",
            rolled_back_by="ops-admin",
            authorized_role="model_operations",
        )
        first_entry.refresh_from_db()
        run_model_monitoring(registry_entry=first_entry, label_dataset_ref=label_dataset.dataset_ref)
        challenger_run = self._challenger_run_for_entry(first_entry, label_dataset, model_version="rf-phase6-v1")
        record_champion_challenger_comparison(
            champion_entry=first_entry,
            challenger_run=challenger_run,
        )

        payload = build_model_operations_health_dashboard()

        self.assertEqual(payload["schema_version"], "ward-risk-model-operations-health-v1")
        self.assertEqual(payload["active_model"]["model_version"], first_entry.model_version)
        self.assertEqual(payload["active_model"]["promotion_state"], ModelRegistryPromotionState.ACTIVE_PROMOTED)
        self.assertEqual(payload["monitoring"]["state"], ModelRegistryMonitoringState.BREACHED)
        self.assertGreaterEqual(payload["summary"]["drift_warning_count"], 1)
        self.assertGreaterEqual(payload["summary"]["calibration_warning_count"], 1)
        self.assertTrue(payload["challenger_comparison"]["configured"])
        self.assertFalse(
            payload["challenger_comparison"]["dashboard_summary"]["challenger_outputs_affect_alerts"]
        )
        self.assertEqual(payload["rollback_history"][0]["rollback_target"]["model_version"], first_entry.model_version)
        model_states = {item["model_version"]: item for item in payload["model_states"]}
        self.assertEqual(model_states[first_entry.model_version]["visual_state"], "active_promoted")
        self.assertEqual(model_states[second_entry.model_version]["visual_state"], "rolled_back")
        self.assertTrue(payload["dashboard_policy"]["candidate_and_promoted_states_visually_distinct"])

    def test_phase_six_health_dashboard_marks_post_comparison_challenger_alert_linkage_unsafe(self):
        entry, label_dataset = self._phase_two_ready_registry_entry()
        challenger_run = self._challenger_run_for_entry(entry, label_dataset, model_version="rf-phase6-unsafe-v1")
        record_champion_challenger_comparison(
            champion_entry=entry,
            challenger_run=challenger_run,
        )
        challenger_score = RiskScore.objects.filter(model_run=challenger_run).select_related("ward").first()
        Alert.objects.create(
            ward=challenger_score.ward,
            risk_score=challenger_score,
            channel=Alert.CHANNEL_DASHBOARD,
            recipient="ops",
            message="Unsafe post-comparison challenger alert fixture",
            status=Alert.STATUS_DELIVERED,
            sent_at=timezone.now(),
        )

        payload = build_model_operations_health_dashboard()

        self.assertFalse(payload["dashboard_policy"]["challenger_comparison_safe_for_dashboard"])
        self.assertTrue(
            payload["challenger_comparison"]["dashboard_summary"]["challenger_outputs_affect_alerts"]
        )
        self.assertEqual(payload["challenger_comparison"]["dashboard_summary"]["challenger_alert_count"], 1)

    def test_phase_six_health_dashboard_marks_promoted_metadata_without_registry_as_missing_registry(self):
        active_run = self._promoted_run("ops-phase6-active-registry-v1")
        ensure_registry_entry_for_promoted_run(
            model_run=active_run,
            owner="model-ops",
            promoted_by="unit-test",
        )
        orphan_run = self._promoted_run("ops-phase6-orphan-promoted-v1")

        payload = build_model_operations_health_dashboard()
        states = {item["model_run_id"]: item for item in payload["model_states"]}

        self.assertEqual(
            states[orphan_run.id]["visual_state"],
            "registry_missing_promoted_metadata",
        )


class ModelOperationsAuditGovernancePhaseSevenTests(ModelOperationsTestHelpers, TestCase):
    def _check_by_id(self, payload):
        return {check["id"]: check for check in payload["checks"]}

    def test_phase_seven_audit_passes_when_review_and_challenger_controls_exist(self):
        entry, label_dataset = self._phase_two_ready_registry_entry()
        run_model_monitoring(registry_entry=entry, label_dataset_ref=label_dataset.dataset_ref)
        evaluate_retraining_policy(registry_entry=entry, new_label_volume_threshold=1)
        entry.refresh_from_db()
        challenger_run = self._challenger_run_for_entry(entry, label_dataset, model_version="rf-phase7-v1")
        record_champion_challenger_comparison(
            champion_entry=entry,
            challenger_run=challenger_run,
        )

        payload = build_model_operations_audit()
        checks = self._check_by_id(payload)

        self.assertEqual(payload["schema_version"], "ward-risk-model-operations-audit-v1")
        self.assertEqual(payload["overall_status"], "pass")
        self.assertEqual(payload["governance"]["review_cadence_days"], 90)
        self.assertEqual(checks["registry_active_model_invalid_active_window"]["status"], "pass")
        self.assertEqual(checks["registry_active_model_missing_promotion_event_provenance"]["status"], "pass")
        self.assertEqual(checks["champion_challenger_comparison_integrity"]["status"], "pass")
        self.assertEqual(checks["monitoring_snapshot_integrity"]["status"], "pass")
        self.assertEqual(checks["retraining_recommendation_integrity"]["status"], "pass")
        self.assertEqual(checks["drift_breach_without_review_record"]["status"], "pass")
        self.assertEqual(checks["challenger_scores_used_as_alerts"]["status"], "pass")
        self.assertTrue(checks["drift_breach_without_review_record"]["evidence"]["review_recorded"])

    def test_phase_seven_audit_flags_stale_model_without_review_and_challenger_alerts(self):
        entry, label_dataset = self._phase_two_ready_registry_entry()
        entry.active_from = timezone.now() - timedelta(days=120)
        entry.review_due_date = timezone.localdate() - timedelta(days=1)
        entry.save(update_fields=["active_from", "review_due_date", "updated_at"])
        challenger_run = self._challenger_run_for_entry(entry, label_dataset, model_version="rf-phase7-alert-v1")
        challenger_score = RiskScore.objects.filter(model_run=challenger_run).select_related("ward").first()
        Alert.objects.create(
            ward=challenger_score.ward,
            risk_score=challenger_score,
            channel=Alert.CHANNEL_DASHBOARD,
            recipient="ops",
            message="Unsafe challenger alert fixture",
            status=Alert.STATUS_DELIVERED,
            sent_at=timezone.now(),
        )

        payload = build_model_operations_audit()
        checks = self._check_by_id(payload)

        self.assertEqual(payload["overall_status"], "fail")
        self.assertEqual(checks["stale_model_without_review_warning"]["status"], "fail")
        self.assertEqual(checks["challenger_scores_used_as_alerts"]["status"], "fail")
        self.assertEqual(
            checks["challenger_scores_used_as_alerts"]["evidence"]["unsafe_alert_count"],
            1,
        )

    def test_phase_seven_audit_flags_drift_breach_without_review_and_bad_rollback_target(self):
        entry, label_dataset = self._phase_two_ready_registry_entry()
        run_model_monitoring(registry_entry=entry, label_dataset_ref=label_dataset.dataset_ref)
        challenger_run = self._challenger_run_for_entry(entry, label_dataset, model_version="rf-phase7-rollback-v1")
        bad_target = ModelRegistryEntry.objects.create(
            algorithm="random_forest",
            model_version=challenger_run.model_version,
            model_run=challenger_run,
            promotion_state=ModelRegistryPromotionState.RETIRED,
            active_from=timezone.now() - timedelta(days=30),
            active_until=timezone.now() - timedelta(days=1),
            owner="model-ops",
            metadata={"fixture": "phase_7_invalid_rollback_target"},
        )
        ModelRollbackEvent.objects.create(
            rolled_back_from=entry,
            rollback_target=bad_target,
            rolled_back_by="unit-test",
            reason="Invalid rollback target audit fixture",
        )
        candidate_run = self._promoted_run("ops-phase7-candidate-target-v1")
        candidate_target = ModelRegistryEntry.objects.create(
            algorithm="logistic_regression",
            model_version=candidate_run.model_version,
            model_run=candidate_run,
            promotion_state=ModelRegistryPromotionState.CANDIDATE,
            owner="model-ops",
            metadata={"fixture": "phase_7_candidate_without_promotion_history"},
        )
        ModelRollbackEvent.objects.create(
            rolled_back_from=entry,
            rollback_target=candidate_target,
            rolled_back_by="unit-test",
            reason="Candidate rollback target audit fixture",
        )

        payload = build_model_operations_audit()
        checks = self._check_by_id(payload)

        self.assertEqual(payload["overall_status"], "fail")
        self.assertEqual(checks["drift_breach_without_review_record"]["status"], "fail")
        self.assertEqual(checks["rollback_to_non_promoted_run"]["status"], "fail")
        self.assertEqual(checks["rollback_event_missing_governance_provenance"]["status"], "fail")
        self.assertEqual(
            checks["rollback_to_non_promoted_run"]["evidence"]["invalid_rollback_event_count"],
            2,
        )
        self.assertEqual(
            checks["rollback_event_missing_governance_provenance"]["evidence"]["invalid_rollback_event_count"],
            2,
        )

    def test_phase_seven_audit_flags_phase4_promoted_run_without_registry_entry(self):
        active_run = self._promoted_run("ops-phase7-active-registry-v1")
        ensure_registry_entry_for_promoted_run(
            model_run=active_run,
            owner="model-ops",
            promoted_by="unit-test",
        )
        self._promoted_run("ops-phase7-promoted-without-registry-v1")

        payload = build_model_operations_audit()
        checks = self._check_by_id(payload)

        self.assertEqual(payload["overall_status"], "fail")
        self.assertEqual(checks["active_model_without_registry_entry"]["status"], "fail")
        self.assertEqual(
            checks["active_model_without_registry_entry"]["evidence"]["promoted_without_registry_count"],
            1,
        )

    def test_phase_seven_audit_flags_champion_registry_mismatch_in_comparison(self):
        first_entry, _first_label_dataset = self._phase_two_ready_registry_entry()
        second_run = self._promoted_run("ops-phase7-comparison-mismatch-v2")
        second_entry = ensure_registry_entry_for_promoted_run(
            model_run=second_run,
            owner="model-ops",
            promoted_by="unit-test",
        )
        second_label_dataset = FeatureDataset.objects.get(
            dataset_ref=second_run.metadata["ward_risk_classification_label_dataset_ref"]
        )
        challenger_run = self._challenger_run_for_entry(
            second_entry,
            second_label_dataset,
            model_version="rf-phase7-comparison-mismatch-v1",
        )
        ModelChampionChallengerComparison.objects.create(
            champion_registry_entry=first_entry,
            champion_model_run=second_run,
            challenger_model_run=challenger_run,
            challenger_algorithm="random_forest",
            challenger_model_version=challenger_run.model_version,
        )

        payload = build_model_operations_audit()
        checks = self._check_by_id(payload)

        self.assertEqual(payload["overall_status"], "fail")
        self.assertEqual(checks["champion_challenger_comparison_integrity"]["status"], "fail")
        self.assertEqual(
            checks["champion_challenger_comparison_integrity"]["evidence"]["invalid_comparison_count"],
            1,
        )

    def test_phase_seven_audit_flags_monitoring_snapshot_and_retraining_lineage_mismatch(self):
        entry, label_dataset = self._phase_two_ready_registry_entry()
        run_model_monitoring(registry_entry=entry, label_dataset_ref=label_dataset.dataset_ref)
        threshold = ModelMonitoringThreshold.objects.get(
            metric_name=METRIC_FEATURE_DISTRIBUTION_DRIFT,
            is_active=True,
        )
        challenger_run = self._challenger_run_for_entry(
            entry,
            label_dataset,
            model_version="rf-phase7-monitoring-lineage-v1",
        )
        ModelMonitoringSnapshot.objects.create(
            registry_entry=entry,
            model_run=challenger_run,
            threshold=threshold,
            metric_name=METRIC_FEATURE_DISTRIBUTION_DRIFT,
            metric_family="drift",
            value=0.1,
            baseline_value=0.0,
            threshold_value=threshold.breach_threshold,
            threshold_version=threshold.version,
            source_dataset_refs=["fixture:bad-monitoring-lineage"],
            metadata={"fixture": "phase_7_monitoring_lineage_mismatch"},
        )
        ModelRetrainingRecommendation.objects.create(
            registry_entry=entry,
            model_run=challenger_run,
            recommendation_state=ModelRetrainingRecommendationState.REVIEW_NOT_REQUIRED,
            recommended_action="unsafe_fixture",
            metadata={
                "schema_version": "unsafe-fixture",
                "automatic_live_promotion_allowed": True,
                "phase_4_promotion_gates_required": False,
            },
        )

        payload = build_model_operations_audit()
        checks = self._check_by_id(payload)

        self.assertEqual(payload["overall_status"], "fail")
        self.assertEqual(checks["monitoring_snapshot_integrity"]["status"], "fail")
        self.assertEqual(checks["retraining_recommendation_integrity"]["status"], "fail")
        self.assertEqual(
            checks["monitoring_snapshot_integrity"]["evidence"]["invalid_snapshot_count"],
            1,
        )
        self.assertEqual(
            checks["retraining_recommendation_integrity"]["evidence"]["invalid_recommendation_count"],
            1,
        )

    def test_audit_model_operations_command_emits_governance_summary(self):
        entry, label_dataset = self._phase_two_ready_registry_entry()
        run_model_monitoring(registry_entry=entry, label_dataset_ref=label_dataset.dataset_ref)
        evaluate_retraining_policy(registry_entry=entry, new_label_volume_threshold=1)
        output = StringIO()

        call_command("audit_model_operations", stdout=output)
        payload = json.loads(output.getvalue())

        self.assertEqual(payload["schema_version"], "ward-risk-model-operations-audit-v1")
        self.assertEqual(payload["overall_status"], "pass")
        self.assertEqual(
            payload["governance"]["promotion_source_of_truth"],
            "ModelRegistryEntry.promotion_state=ACTIVE_PROMOTED with active_from set, active_until null, "
            "and valid ModelPromotionEvent provenance",
        )
        self.assertEqual(payload["summary"]["failed_check_count"], 0)
