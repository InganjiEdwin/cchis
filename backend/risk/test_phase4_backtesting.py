import json
from datetime import date, timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from risk.lead_time_features import LEAD_TIME_FEATURE_SCHEMA_VERSION
from risk.ml.data import SURVEILLANCE_LABEL_TRAINING_USAGE
from risk.ml.backtesting import (
    RAINFALL_THRESHOLD_BASELINE_KEY,
    WARD_RISK_TEMPORAL_BACKTEST_SCHEMA_VERSION,
    build_temporal_backtest_report,
    persist_temporal_backtest_report,
)
from risk.models import FeatureDataset, FeatureDatasetRow, ModelRun, RiskScore, Ward
from risk.serializers import RiskScoreSerializer
from risk.services import create_alerts_for_riskscore
from risk.surveillance_labels import (
    SURVEILLANCE_LEAD_TIME_LABEL_GENERATION_MODE,
    SURVEILLANCE_LABEL_SCHEMA_VERSION,
)


class WardRiskTemporalBacktestingPhaseFourTestCase(TestCase):
    def setUp(self):
        self.ward_a = Ward.objects.create(
            name="Phase Four A",
            county="Migori",
            ward_code="P4-A",
            current_risk_level=Ward.RISK_LOW,
            current_risk_score=0.20,
        )
        self.ward_b = Ward.objects.create(
            name="Phase Four B",
            county="Migori",
            ward_code="P4-B",
            current_risk_level=Ward.RISK_HIGH,
            current_risk_score=0.80,
        )

    def _create_feature_and_label_datasets(self, *, leak_validation_row=False):
        feature_dataset = FeatureDataset.objects.create(
            dataset_ref=f"phase4-features-{timezone.now().timestamp()}",
            dataset_kind=FeatureDataset.KIND_INFERENCE,
            schema_version=LEAD_TIME_FEATURE_SCHEMA_VERSION,
            source_kind=FeatureDataset.SOURCE_KIND_LIVE,
            month=4,
            feature_keys=["prediction_date", "rainfall_total_14d", "leakage_proof"],
            row_count=6,
            lineage_metadata={"builder": "phase4-test"},
        )
        label_dataset = FeatureDataset.objects.create(
            dataset_ref=f"phase4-labels-{timezone.now().timestamp()}",
            dataset_kind=FeatureDataset.KIND_TRAINING,
            schema_version=SURVEILLANCE_LABEL_SCHEMA_VERSION,
            source_kind=FeatureDataset.SOURCE_KIND_LIVE,
            month=4,
            feature_keys=["prediction_date", "truth_level", "late_revision_state"],
            row_count=6,
            lineage_metadata={
                "generation_mode": SURVEILLANCE_LEAD_TIME_LABEL_GENERATION_MODE,
                "dataset_role": "evaluation",
                "label_window_start_offset_days": 7,
                "label_window_end_offset_days": 14,
            },
        )
        rows = [
            (date(2026, 4, 1), self.ward_a, 12, 0, "suspected_surveillance"),
            (date(2026, 4, 1), self.ward_b, 95, 1, "confirmed_surveillance"),
            (date(2026, 4, 8), self.ward_a, 18, 0, "suspected_surveillance"),
            (date(2026, 4, 8), self.ward_b, 105, 1, "confirmed_surveillance"),
            (date(2026, 4, 15), self.ward_a, 20, 0, "suspected_surveillance"),
            (date(2026, 4, 15), self.ward_b, 115, 1, "confirmed_surveillance"),
        ]
        for prediction_date, ward, rainfall_total, label, truth_level in rows:
            leakage_passed = not (leak_validation_row and prediction_date == date(2026, 4, 15) and ward == self.ward_b)
            FeatureDatasetRow.objects.create(
                dataset=feature_dataset,
                ward=ward,
                ward_name_snapshot=ward.name,
                month=prediction_date.month,
                label=None,
                feature_values={
                    "prediction_date": prediction_date.isoformat(),
                    "rainfall_total_3d": rainfall_total / 3,
                    "rainfall_total_7d": rainfall_total / 2,
                    "rainfall_total_14d": rainfall_total,
                    "rainfall_anomaly_against_local_baseline": rainfall_total - 40,
                    "heavy_rain_threshold_exceedance_count_14d": 1 if rainfall_total >= 50 else 0,
                    "days_since_heavy_rain": 2 if rainfall_total >= 50 else None,
                    "upstream_or_neighboring_ward_risk_signal": 0.5,
                    "surveillance_total_cases_28d_before_prediction": label,
                    "surveillance_record_count_28d_before_prediction": 1,
                    "surveillance_case_trend_14d_delta": label,
                    "population_total": 10000,
                    "population_density": 120,
                    "settlement_concentration": 0.4,
                    "floodplain_exposure": 0.2,
                    "water_body_proximity": 0.3,
                    "wash_vulnerability": 0.5,
                    "source_refs": [f"rainfall:phase4:{ward.ward_code}:{prediction_date.isoformat()}"],
                    "source_record_refs": [f"rainfall_record:phase4:{ward.ward_code}:{prediction_date.isoformat()}"],
                    "source_lineage": {
                        "rainfall": {
                            "source_refs": [f"rainfall:phase4:{ward.ward_code}"],
                            "source_record_refs": [
                                f"rainfall_record:phase4:{ward.ward_code}:{prediction_date.isoformat()}"
                            ],
                        },
                        "surveillance": {
                            "source_refs": [f"surveillance:phase4:{ward.ward_code}"],
                            "source_record_refs": [
                                f"surveillance_record:phase4:{ward.ward_code}:{prediction_date.isoformat()}"
                            ],
                        },
                    },
                    "leakage_proof": {"passes_cutoff_check": leakage_passed},
                },
            )
            FeatureDatasetRow.objects.create(
                dataset=label_dataset,
                ward=ward,
                ward_name_snapshot=ward.name,
                month=prediction_date.month,
                label=label,
                feature_values={
                    "prediction_date": prediction_date.isoformat(),
                    "label_window_start": (prediction_date + timedelta(days=7)).isoformat(),
                    "label_window_end": (prediction_date + timedelta(days=14)).isoformat(),
                    "truth_level": truth_level,
                    "late_revision_state": "original",
                    "outbreak_label": "active" if label else "none",
                    "label_window_id": None,
                },
            )
        return feature_dataset, label_dataset

    def _force_seeded_demo_truth(self, label_dataset):
        for row in FeatureDatasetRow.objects.filter(dataset=label_dataset).order_by("id"):
            values = row.feature_values or {}
            values["truth_level"] = "seeded_demo"
            row.feature_values = values
            row.save(update_fields=["feature_values"])

    def _invert_validation_labels(self, label_dataset):
        validation_date = date(2026, 4, 15).isoformat()
        for row in FeatureDatasetRow.objects.filter(dataset=label_dataset).order_by("id"):
            values = row.feature_values or {}
            if values.get("prediction_date") != validation_date:
                continue
            if row.ward_id == self.ward_a.id:
                row.label = 1
                values["outbreak_label"] = "active"
            else:
                row.label = 0
                values["outbreak_label"] = "none"
            values["truth_level"] = "confirmed_surveillance"
            row.feature_values = values
            row.save(update_fields=["label", "feature_values"])

    def _training_feature_dataset(self, *, source_kind=FeatureDataset.SOURCE_KIND_LIVE, lineage_overrides=None):
        lineage = {
            "surveillance_label_usage": SURVEILLANCE_LABEL_TRAINING_USAGE,
            "training_label_seeded_demo_row_count": 0,
            "training_label_readiness": {
                "ready": True,
                "reason": "surveillance_label_dataset_ready",
            },
            "surveillance_label_truth_gate": {
                "proxy_only_as_confirmed_allowed": False,
                "confirmed_truth_required_for_confirmed_outbreak_claims": True,
            },
            "surveillance_label_dataset_ref": "phase4-training-surveillance-labels",
        }
        if lineage_overrides:
            lineage.update(lineage_overrides)
        return FeatureDataset.objects.create(
            dataset_ref=f"phase4-training-{timezone.now().timestamp()}",
            dataset_kind=FeatureDataset.KIND_TRAINING,
            schema_version="baseline-v1",
            source_kind=source_kind,
            month=4,
            feature_keys=["rainfall_mm", "historical_cases", "training_label_source"],
            row_count=4,
            lineage_metadata=lineage,
        )

    def _model_run(self, *, feature_dataset, training_feature_dataset=None):
        training_feature_dataset = training_feature_dataset or self._training_feature_dataset()
        model_run = ModelRun.objects.create(
            algorithm_name="logistic-regression-baseline",
            model_version="lr-phase4-evidence-v1",
            status=ModelRun.STATUS_SUCCESS,
            month=4,
            feature_schema_version=LEAD_TIME_FEATURE_SCHEMA_VERSION,
            training_feature_dataset=training_feature_dataset,
            training_dataset_ref=training_feature_dataset.dataset_ref,
            inference_feature_dataset=feature_dataset,
            inference_dataset_ref=feature_dataset.dataset_ref,
            evaluation_metrics={},
            metadata={"algorithm": "logistic_regression", "promotion_target": "benchmark_only"},
            completed_at=timezone.now(),
        )
        RiskScore.objects.create(
            ward=self.ward_b,
            model_run=model_run,
            score=0.92,
            risk_level=Ward.RISK_HIGH,
            predicted_cases=10,
            source=RiskScore.SOURCE_MODEL,
            model_version=model_run.model_version,
        )
        return model_run

    def test_temporal_backtest_trains_earlier_validates_later_and_persists_promotion_evidence(self):
        feature_dataset, label_dataset = self._create_feature_and_label_datasets()
        model_run = self._model_run(feature_dataset=feature_dataset)

        report = build_temporal_backtest_report(
            feature_dataset=feature_dataset,
            label_dataset=label_dataset,
            train_end_date=date(2026, 4, 8),
            validation_start_date=date(2026, 4, 15),
            rainfall_threshold_mm=50,
        )
        self.assertEqual(report["schema_version"], WARD_RISK_TEMPORAL_BACKTEST_SCHEMA_VERSION)
        self.assertEqual(report["row_counts"]["training_row_count"], 4)
        self.assertEqual(report["row_counts"]["validation_row_count"], 2)
        self.assertEqual(report["metrics"]["logistic_regression"]["status"], "evaluated")
        self.assertEqual(report["metrics"]["random_forest"]["status"], "evaluated")
        self.assertEqual(report["metrics"][RAINFALL_THRESHOLD_BASELINE_KEY]["status"], "evaluated")
        logistic_metrics = report["metrics"]["logistic_regression"]["metrics"]
        self.assertEqual(logistic_metrics["accuracy"], 1.0)
        self.assertEqual(logistic_metrics["lead_time_hit_rate"], 1.0)
        self.assertEqual(logistic_metrics["balanced_accuracy"], 1.0)
        self.assertEqual(logistic_metrics["f1_score"], 1.0)
        self.assertEqual(logistic_metrics["false_alert_rate"], 0.0)
        self.assertEqual(logistic_metrics["false_alerts_per_true_hit"], 0.0)
        self.assertEqual(logistic_metrics["positive_class_balance"], 0.5)
        self.assertIn("area_under_precision_recall_curve", logistic_metrics)
        self.assertIn("Phase Four B", report["metrics"]["logistic_regression"]["by_ward"])
        self.assertIn("4", report["metrics"]["logistic_regression"]["by_month"])
        self.assertIn("long_rains", report["metrics"]["logistic_regression"]["by_season"])
        self.assertIn("confirmed_surveillance", report["metrics"]["logistic_regression"]["by_truth_level"])
        self.assertTrue(report["promotion_gates"]["passed"])
        promotion_metric_thresholds = report["promotion_gates"]["checks"]["promotion_metric_thresholds"]
        self.assertTrue(promotion_metric_thresholds["algorithm_results"]["logistic_regression"]["passed"])
        self.assertEqual(report["promotion_gates"]["checks"]["accepted_outbreak_validation_row_count"], 1)
        self.assertTrue(
            report["facility_burden_forecast_separation"][
                "negative_binomial_facility_burden_forecasting_separate"
            ]
        )

        persist_temporal_backtest_report(model_run=model_run, report=report, promote=True)
        model_run.refresh_from_db()
        self.assertEqual(model_run.metadata["promotion_target"], "live_baseline")
        self.assertEqual(model_run.metadata["promotion_state"], "promoted")
        self.assertTrue(model_run.metadata["phase_4_promotion_evidence_persisted"])
        self.assertTrue(model_run.metadata["phase_4_promotion_evidence_binding"]["passed"])
        self.assertTrue(model_run.metadata["phase_4_training_truth_gate"]["passed"])
        self.assertTrue(model_run.evaluation_metrics["phase_4_training_truth_gate_passed"])
        self.assertEqual(
            model_run.metadata["phase_4_promotion_evidence_binding"]["report_feature_dataset_ref"],
            feature_dataset.dataset_ref,
        )
        self.assertTrue(model_run.evaluation_metrics["promotion_truth_and_leakage_checks_passed"])
        self.assertTrue(model_run.evaluation_metrics["phase_4_selected_model_promotion_metric_gate_passed"])
        self.assertTrue(model_run.evaluation_metrics["phase_4_promotion_evidence_binding_passed"])
        self.assertEqual(model_run.evaluation_metrics["lead_time_recall"], 1.0)
        self.assertEqual(model_run.evaluation_metrics["balanced_accuracy"], 1.0)
        self.assertEqual(model_run.evaluation_metrics["false_alert_rate"], 0.0)
        self.assertEqual(model_run.evaluation_metrics["temporal_validation_window_count"], 1)
        self.assertIn("temporal_backtest_report", model_run.evaluation_metrics)
        self.assertEqual(model_run.metadata["risk_score_model_run_linkage"]["risk_score_count"], 1)
        self.assertEqual(model_run.metadata["promoted_risk_scores_materialized_to_wards"], 1)
        self.ward_b.refresh_from_db()
        self.assertEqual(self.ward_b.current_risk_level, Ward.RISK_HIGH)
        self.assertAlmostEqual(self.ward_b.current_risk_score, 0.92)
        risk_score = model_run.risk_scores.first()
        serialized_score = RiskScoreSerializer(risk_score).data
        self.assertEqual(serialized_score["model_run_promotion_target"], "live_baseline")
        self.assertTrue(serialized_score["model_run_phase_4_promotion_evidence_persisted"])
        self.assertTrue(serialized_score["model_run_phase_4_promotion_gates_passed"])

        dashboard_alert = create_alerts_for_riskscore(risk_score)[0]
        model_run_evidence = dashboard_alert.guided_request_metadata["model_run_evidence"]
        self.assertEqual(model_run_evidence["model_run_id"], model_run.id)
        self.assertEqual(model_run_evidence["promotion_target"], "live_baseline")
        self.assertTrue(model_run_evidence["phase_4_promotion_gates_passed"])
        self.assertTrue(model_run_evidence["promotion_truth_and_leakage_checks_passed"])
        self.assertEqual(model_run_evidence["promotion_evaluation_metrics"]["lead_time_recall"], 1.0)
        feature_lineage = model_run_evidence["feature_lineage"]
        self.assertEqual(feature_lineage["inference_feature_dataset_ref"], feature_dataset.dataset_ref)
        self.assertTrue(feature_lineage["lineage_available"])
        self.assertGreaterEqual(feature_lineage["ward_feature_row_count"], 1)
        self.assertTrue(feature_lineage["feature_row_refs"])
        self.assertTrue(feature_lineage["source_refs"])
        self.assertTrue(feature_lineage["source_record_refs"])

    def test_promotion_fails_when_report_is_not_bound_to_model_run_feature_dataset(self):
        feature_dataset, label_dataset = self._create_feature_and_label_datasets()
        model_run = self._model_run(feature_dataset=feature_dataset)
        model_run.inference_dataset_ref = "different-lead-time-feature-dataset"
        model_run.save(update_fields=["inference_dataset_ref"])
        report = build_temporal_backtest_report(
            feature_dataset=feature_dataset,
            label_dataset=label_dataset,
            train_end_date=date(2026, 4, 8),
            validation_start_date=date(2026, 4, 15),
            rainfall_threshold_mm=50,
        )

        with self.assertRaisesMessage(ValueError, "promotion_feature_dataset_mismatch"):
            persist_temporal_backtest_report(model_run=model_run, report=report, promote=True)

        model_run.refresh_from_db()
        self.assertEqual(model_run.metadata["promotion_target"], "benchmark_only")

    def test_promotion_fails_when_model_run_training_truth_is_seeded_fallback(self):
        feature_dataset, label_dataset = self._create_feature_and_label_datasets()
        seeded_training_dataset = self._training_feature_dataset(
            source_kind=FeatureDataset.SOURCE_KIND_SEEDED,
            lineage_overrides={
                "surveillance_label_usage": "seeded_training_baseline_not_goal_aligned",
                "training_label_seeded_demo_row_count": 4,
                "training_label_readiness": {
                    "ready": False,
                    "reason": "missing_surveillance_label_dataset",
                },
                "surveillance_label_dataset_ref": None,
            },
        )
        model_run = self._model_run(
            feature_dataset=feature_dataset,
            training_feature_dataset=seeded_training_dataset,
        )
        report = build_temporal_backtest_report(
            feature_dataset=feature_dataset,
            label_dataset=label_dataset,
            train_end_date=date(2026, 4, 8),
            validation_start_date=date(2026, 4, 15),
            rainfall_threshold_mm=50,
        )
        self.assertTrue(report["promotion_gates"]["passed"])

        with self.assertRaisesMessage(ValueError, "promotion_training_seeded_demo_rows_present"):
            persist_temporal_backtest_report(model_run=model_run, report=report, promote=True)

        model_run.refresh_from_db()
        self.assertEqual(model_run.metadata["promotion_target"], "benchmark_only")
        self.assertNotIn("phase_4_training_truth_gate", model_run.metadata)

    def test_promotion_fails_when_leakage_check_fails(self):
        feature_dataset, label_dataset = self._create_feature_and_label_datasets(leak_validation_row=True)
        model_run = self._model_run(feature_dataset=feature_dataset)
        report = build_temporal_backtest_report(
            feature_dataset=feature_dataset,
            label_dataset=label_dataset,
            train_end_date=date(2026, 4, 8),
            validation_start_date=date(2026, 4, 15),
            rainfall_threshold_mm=50,
        )

        self.assertFalse(report["promotion_gates"]["passed"])
        self.assertIn("leakage_checks_not_passing", report["promotion_gates"]["blockers"])
        with self.assertRaises(ValueError):
            persist_temporal_backtest_report(model_run=model_run, report=report, promote=True)

    def test_promotion_fails_when_validation_truth_is_seeded_demo_only(self):
        feature_dataset, label_dataset = self._create_feature_and_label_datasets()
        self._force_seeded_demo_truth(label_dataset)
        model_run = self._model_run(feature_dataset=feature_dataset)
        report = build_temporal_backtest_report(
            feature_dataset=feature_dataset,
            label_dataset=label_dataset,
            train_end_date=date(2026, 4, 8),
            validation_start_date=date(2026, 4, 15),
            rainfall_threshold_mm=50,
        )

        self.assertFalse(report["promotion_gates"]["passed"])
        self.assertIn("accepted_surveillance_truth_missing", report["promotion_gates"]["blockers"])
        self.assertIn("seeded_demo_only_validation_truth_cannot_promote", report["promotion_gates"]["blockers"])
        self.assertIn("promotion_metric_thresholds_not_met", report["promotion_gates"]["blockers"])
        logistic_gate = report["promotion_gates"]["checks"]["promotion_metric_thresholds"]["algorithm_results"][
            "logistic_regression"
        ]
        self.assertIn("accepted_outbreak_validation_window_missing", logistic_gate["blockers"])
        with self.assertRaises(ValueError):
            persist_temporal_backtest_report(model_run=model_run, report=report, promote=True)

    def test_promotion_fails_when_model_misses_accepted_outbreak_window(self):
        feature_dataset, label_dataset = self._create_feature_and_label_datasets()
        self._invert_validation_labels(label_dataset)
        model_run = self._model_run(feature_dataset=feature_dataset)
        report = build_temporal_backtest_report(
            feature_dataset=feature_dataset,
            label_dataset=label_dataset,
            train_end_date=date(2026, 4, 8),
            validation_start_date=date(2026, 4, 15),
            rainfall_threshold_mm=50,
        )

        self.assertFalse(report["promotion_gates"]["passed"])
        self.assertIn("promotion_metric_thresholds_not_met", report["promotion_gates"]["blockers"])
        logistic_gate = report["promotion_gates"]["checks"]["promotion_metric_thresholds"]["algorithm_results"][
            "logistic_regression"
        ]
        self.assertFalse(logistic_gate["passed"])
        self.assertIn("accuracy_below_80_percent", logistic_gate["blockers"])
        self.assertIn("lead_time_recall_below_80_percent_on_accepted_truth", logistic_gate["blockers"])
        with self.assertRaises(ValueError):
            persist_temporal_backtest_report(model_run=model_run, report=report, promote=True)

    def test_promote_checks_the_selected_model_not_just_the_report_level_gate(self):
        feature_dataset, label_dataset = self._create_feature_and_label_datasets()
        model_run = self._model_run(feature_dataset=feature_dataset)
        report = build_temporal_backtest_report(
            feature_dataset=feature_dataset,
            label_dataset=label_dataset,
            train_end_date=date(2026, 4, 8),
            validation_start_date=date(2026, 4, 15),
            rainfall_threshold_mm=50,
        )
        report["promotion_gates"]["checks"]["promotion_metric_thresholds"]["algorithm_results"][
            "logistic_regression"
        ] = {
            "passed": False,
            "blockers": ["synthetic_selected_model_failed_metric_gate"],
            "metrics_checked": {},
        }
        report["promotion_gates"]["passed"] = True
        report["promotion_gates"]["blockers"] = []

        with self.assertRaisesRegex(ValueError, "selected model Phase 4 metric gates failed"):
            persist_temporal_backtest_report(model_run=model_run, report=report, promote=True)

    def test_run_ward_risk_backtest_command_persists_report_and_promotes_only_after_gates_pass(self):
        feature_dataset, label_dataset = self._create_feature_and_label_datasets()
        model_run = self._model_run(feature_dataset=feature_dataset)
        output = StringIO()

        call_command(
            "run_ward_risk_backtest",
            "--feature-dataset-ref",
            feature_dataset.dataset_ref,
            "--label-dataset-ref",
            label_dataset.dataset_ref,
            "--model-run-id",
            str(model_run.id),
            "--train-end-date",
            "2026-04-08",
            "--validation-start-date",
            "2026-04-15",
            "--promote",
            stdout=output,
        )

        payload = json.loads(output.getvalue())
        self.assertTrue(payload["promotion_gates"]["passed"])
        model_run.refresh_from_db()
        self.assertEqual(model_run.metadata["promotion_decision_source"], "phase_4_temporal_backtest")
        self.assertEqual(
            model_run.evaluation_metrics["temporal_backtest_report"]["label_dataset_ref"],
            label_dataset.dataset_ref,
        )
