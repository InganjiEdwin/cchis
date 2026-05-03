from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score

from risk.lead_time_features import LEAD_TIME_FEATURE_SCHEMA_VERSION
from risk.models import FeatureDataset, FeatureDatasetRow, ModelRun
from risk.surveillance_labels import SURVEILLANCE_LEAD_TIME_LABEL_GENERATION_MODE

from .alignment import PROMOTION_TARGET_LIVE_BASELINE, algorithm_key_from_run
from .data import SURVEILLANCE_LABEL_TRAINING_USAGE
from .model import ALGORITHM_LOGISTIC_REGRESSION, ALGORITHM_RANDOM_FOREST


WARD_RISK_TEMPORAL_BACKTEST_SCHEMA_VERSION = "ward-risk-temporal-backtest-v1"
RAINFALL_THRESHOLD_BASELINE_KEY = "rainfall_threshold_baseline"
MIN_PROMOTION_ACCURACY = 0.80
MIN_PROMOTION_LEAD_TIME_RECALL = 0.80
MIN_PROMOTION_PRECISION = 0.20
MAX_FALSE_ALERTS_PER_TRUE_HIT = 5.0
SEEDED_DEMO_TRUTH_LEVEL = "seeded_demo"
ACCEPTED_PROMOTION_TRUTH_LEVELS = {"confirmed_surveillance", "suspected_surveillance"}
TEMPORAL_BACKTEST_FEATURE_KEYS = [
    "rainfall_total_3d",
    "rainfall_total_7d",
    "rainfall_total_14d",
    "rainfall_anomaly_against_local_baseline",
    "heavy_rain_threshold_exceedance_count_14d",
    "days_since_heavy_rain",
    "upstream_or_neighboring_ward_risk_signal",
    "surveillance_suspected_cases_28d_before_prediction",
    "surveillance_confirmed_cases_28d_before_prediction",
    "surveillance_proxy_cases_28d_before_prediction",
    "surveillance_total_cases_28d_before_prediction",
    "surveillance_record_count_28d_before_prediction",
    "surveillance_case_trend_14d_delta",
    "population_total",
    "population_density",
    "settlement_concentration",
    "floodplain_exposure",
    "water_body_proximity",
    "wash_vulnerability",
]


def _parse_date(value) -> date | None:
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _safe_float(value) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _season_for_month(month: int) -> str:
    if month in {3, 4, 5}:
        return "long_rains"
    if month in {10, 11, 12}:
        return "short_rains"
    return "dry_or_transition"


def _label_rows_by_ward_prediction_date(
    label_dataset: FeatureDataset,
) -> dict[tuple[int, date], FeatureDatasetRow]:
    rows_by_key = {}
    for row in FeatureDatasetRow.objects.filter(dataset=label_dataset, ward__isnull=False).order_by("id"):
        prediction_date = _parse_date((row.feature_values or {}).get("prediction_date"))
        if prediction_date is None:
            continue
        rows_by_key[(row.ward_id, prediction_date)] = row
    return rows_by_key


def _aligned_examples(*, feature_dataset: FeatureDataset, label_dataset: FeatureDataset) -> list[dict]:
    label_rows_by_key = _label_rows_by_ward_prediction_date(label_dataset)
    examples = []
    for feature_row in FeatureDatasetRow.objects.filter(dataset=feature_dataset, ward__isnull=False).order_by("id"):
        feature_values = feature_row.feature_values or {}
        prediction_date = _parse_date(feature_values.get("prediction_date"))
        if prediction_date is None:
            continue
        label_row = label_rows_by_key.get((feature_row.ward_id, prediction_date))
        if label_row is None or label_row.label not in {0, 1}:
            continue
        label_values = label_row.feature_values or {}
        leakage_proof = feature_values.get("leakage_proof") or {}
        truth_level = label_values.get("truth_level") or label_values.get("label_truth_level") or "unknown"
        examples.append(
            {
                "ward_id": feature_row.ward_id,
                "ward_name": feature_row.ward_name_snapshot,
                "prediction_date": prediction_date,
                "month": prediction_date.month,
                "season": _season_for_month(prediction_date.month),
                "feature_row_id": feature_row.id,
                "label_row_id": label_row.id,
                "label_window_id": label_values.get("label_window_id"),
                "label": int(label_row.label),
                "truth_level": truth_level,
                "late_revision_state": label_values.get("late_revision_state", "unknown"),
                "leakage_check_passed": leakage_proof.get("passes_cutoff_check") is True,
                "feature_values": feature_values,
                "label_values": label_values,
            }
        )
    return sorted(examples, key=lambda item: (item["prediction_date"], item["ward_name"], item["ward_id"]))


def _temporal_split(
    examples: list[dict],
    *,
    train_end_date: date | None = None,
    validation_start_date: date | None = None,
) -> tuple[list[dict], list[dict], dict]:
    prediction_dates = sorted({example["prediction_date"] for example in examples})
    if not prediction_dates:
        return [], [], {"status": "not_ready_no_prediction_dates"}
    if train_end_date is None and validation_start_date is None:
        if len(prediction_dates) < 2:
            return [], [], {"status": "not_ready_requires_at_least_two_prediction_dates"}
        split_index = max(1, len(prediction_dates) // 2)
        validation_start_date = prediction_dates[split_index]
        train_end_date = prediction_dates[split_index - 1]
    elif train_end_date is None:
        train_dates = [item for item in prediction_dates if item < validation_start_date]
        train_end_date = max(train_dates) if train_dates else None
    elif validation_start_date is None:
        validation_dates = [item for item in prediction_dates if item > train_end_date]
        validation_start_date = min(validation_dates) if validation_dates else None

    train_examples = [
        example for example in examples if train_end_date is not None and example["prediction_date"] <= train_end_date
    ]
    validation_examples = [
        example
        for example in examples
        if validation_start_date is not None and example["prediction_date"] >= validation_start_date
    ]
    return (
        train_examples,
        validation_examples,
        {
            "status": "ready" if train_examples and validation_examples else "not_ready_empty_train_or_validation_split",
            "train_start_date": min((example["prediction_date"] for example in train_examples), default=None),
            "train_end_date": train_end_date,
            "validation_start_date": validation_start_date,
            "validation_end_date": max((example["prediction_date"] for example in validation_examples), default=None),
            "prediction_dates": [item.isoformat() for item in prediction_dates],
        },
    )


def _matrix(examples: list[dict]) -> np.ndarray:
    return np.array(
        [
            [_safe_float(example["feature_values"].get(feature_key)) for feature_key in TEMPORAL_BACKTEST_FEATURE_KEYS]
            for example in examples
        ],
        dtype=float,
    )


def _labels(examples: list[dict]) -> np.ndarray:
    return np.array([example["label"] for example in examples], dtype=int)


def _binary_metrics(labels: list[int], predictions: list[int], probabilities: list[float] | None = None) -> dict:
    count = len(labels)
    true_positive = sum(1 for truth, prediction in zip(labels, predictions) if truth == 1 and prediction == 1)
    false_positive = sum(1 for truth, prediction in zip(labels, predictions) if truth == 0 and prediction == 1)
    true_negative = sum(1 for truth, prediction in zip(labels, predictions) if truth == 0 and prediction == 0)
    false_negative = sum(1 for truth, prediction in zip(labels, predictions) if truth == 1 and prediction == 0)
    predicted_positive = true_positive + false_positive
    observed_positive = true_positive + false_negative
    observed_negative = true_negative + false_positive
    brier_score = None
    calibration_score = None
    area_under_precision_recall_curve = None
    if probabilities is not None and count:
        brier_score = round(
            sum((probability - truth) ** 2 for probability, truth in zip(probabilities, labels)) / count,
            6,
        )
        calibration_score = round(max(0.0, 1.0 - brier_score), 6)
        if len(set(labels)) >= 2:
            area_under_precision_recall_curve = round(float(average_precision_score(labels, probabilities)), 6)
    accuracy = round((true_positive + true_negative) / count, 6) if count else None
    precision = round(true_positive / predicted_positive, 6) if predicted_positive else None
    recall = round(true_positive / observed_positive, 6) if observed_positive else None
    specificity = round(true_negative / observed_negative, 6) if observed_negative else None
    f1_score = (
        round((2 * precision * recall) / (precision + recall), 6)
        if precision is not None and recall is not None and precision + recall > 0
        else None
    )
    balanced_accuracy = (
        round((recall + specificity) / 2, 6) if recall is not None and specificity is not None else None
    )
    return {
        "row_count": count,
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "lead_time_hit_rate": recall,
        "specificity": specificity,
        "balanced_accuracy": balanced_accuracy,
        "f1_score": f1_score,
        "true_positive": true_positive,
        "false_positive": false_positive,
        "true_negative": true_negative,
        "false_negative": false_negative,
        "observed_positive_count": observed_positive,
        "observed_negative_count": observed_negative,
        "predicted_positive_count": predicted_positive,
        "positive_class_balance": round(observed_positive / count, 6) if count else None,
        "false_alert_rate": round(false_positive / observed_negative, 6) if observed_negative else None,
        "false_alerts_per_true_hit": round(false_positive / true_positive, 6) if true_positive else None,
        "area_under_precision_recall_curve": area_under_precision_recall_curve,
        "brier_score": brier_score,
        "calibration_score": calibration_score,
    }


def _grouped_metrics(evaluation_rows: list[dict], dimension: str) -> dict:
    grouped = defaultdict(list)
    for row in evaluation_rows:
        grouped[str(row.get(dimension) or "unknown")].append(row)
    return {
        key: _binary_metrics(
            [row["label"] for row in rows],
            [row["predicted_label"] for row in rows],
            [row["predicted_probability"] for row in rows],
        )
        for key, rows in sorted(grouped.items())
    }


def _fit_model_metrics(*, algorithm: str, train_examples: list[dict], validation_examples: list[dict]) -> dict:
    if not validation_examples:
        return {
            "status": "not_ready_no_validation_rows",
            "row_count": 0,
        }
    train_labels = [example["label"] for example in train_examples]
    if len(set(train_labels)) < 2:
        return {
            "status": "not_ready_training_split_lacks_positive_and_negative_classes",
            "row_count": len(validation_examples),
        }
    model = (
        RandomForestClassifier(n_estimators=200, max_depth=6, random_state=42)
        if algorithm == ALGORITHM_RANDOM_FOREST
        else LogisticRegression(max_iter=1000, random_state=42)
    )
    model.fit(_matrix(train_examples), _labels(train_examples))
    probabilities = [float(value) for value in model.predict_proba(_matrix(validation_examples))[:, 1]]
    predictions = [1 if probability >= 0.5 else 0 for probability in probabilities]
    evaluation_rows = []
    for example, probability, prediction in zip(validation_examples, probabilities, predictions):
        evaluation_rows.append(
            {
                "ward_id": example["ward_id"],
                "ward_name": example["ward_name"],
                "prediction_date": example["prediction_date"].isoformat(),
                "month": example["month"],
                "season": example["season"],
                "truth_level": example["truth_level"],
                "late_revision_state": example["late_revision_state"],
                "label": example["label"],
                "predicted_label": prediction,
                "predicted_probability": round(probability, 6),
                "feature_row_id": example["feature_row_id"],
                "label_row_id": example["label_row_id"],
                "label_window_id": example["label_window_id"],
            }
        )
    return {
        "status": "evaluated",
        "algorithm": algorithm,
        "metrics": _binary_metrics(
            [row["label"] for row in evaluation_rows],
            [row["predicted_label"] for row in evaluation_rows],
            [row["predicted_probability"] for row in evaluation_rows],
        ),
        "by_ward": _grouped_metrics(evaluation_rows, "ward_name"),
        "by_month": _grouped_metrics(evaluation_rows, "month"),
        "by_season": _grouped_metrics(evaluation_rows, "season"),
        "by_truth_level": _grouped_metrics(evaluation_rows, "truth_level"),
        "evaluation_rows": evaluation_rows,
    }


def _rainfall_threshold_metrics(*, validation_examples: list[dict], threshold_mm: float) -> dict:
    evaluation_rows = []
    for example in validation_examples:
        rainfall_total = _safe_float(example["feature_values"].get("rainfall_total_14d"))
        predicted_label = 1 if rainfall_total >= threshold_mm else 0
        evaluation_rows.append(
            {
                "ward_id": example["ward_id"],
                "ward_name": example["ward_name"],
                "prediction_date": example["prediction_date"].isoformat(),
                "month": example["month"],
                "season": example["season"],
                "truth_level": example["truth_level"],
                "late_revision_state": example["late_revision_state"],
                "label": example["label"],
                "predicted_label": predicted_label,
                "predicted_probability": 1.0 if predicted_label else 0.0,
                "rainfall_total_14d": rainfall_total,
                "feature_row_id": example["feature_row_id"],
                "label_row_id": example["label_row_id"],
                "label_window_id": example["label_window_id"],
            }
        )
    return {
        "status": "evaluated" if evaluation_rows else "not_ready_no_validation_rows",
        "algorithm": RAINFALL_THRESHOLD_BASELINE_KEY,
        "threshold_mm": threshold_mm,
        "metrics": _binary_metrics(
            [row["label"] for row in evaluation_rows],
            [row["predicted_label"] for row in evaluation_rows],
            [row["predicted_probability"] for row in evaluation_rows],
        ),
        "by_ward": _grouped_metrics(evaluation_rows, "ward_name"),
        "by_month": _grouped_metrics(evaluation_rows, "month"),
        "by_season": _grouped_metrics(evaluation_rows, "season"),
        "by_truth_level": _grouped_metrics(evaluation_rows, "truth_level"),
        "evaluation_rows": evaluation_rows,
    }


def _metrics_for_rows(rows: list[dict]) -> dict:
    return _binary_metrics(
        [row["label"] for row in rows],
        [row["predicted_label"] for row in rows],
        [row["predicted_probability"] for row in rows],
    )


def _algorithm_promotion_metric_gate(model_result: dict) -> dict:
    if model_result.get("status") != "evaluated":
        return {
            "passed": False,
            "blockers": ["model_temporal_backtest_missing"],
            "metrics_checked": {},
        }

    metrics = model_result.get("metrics") or {}
    accepted_rows = [
        row
        for row in model_result.get("evaluation_rows", [])
        if row.get("truth_level") in ACCEPTED_PROMOTION_TRUTH_LEVELS
    ]
    accepted_truth_metrics = _metrics_for_rows(accepted_rows) if accepted_rows else _binary_metrics([], [])
    blockers = []

    accuracy = metrics.get("accuracy")
    if accuracy is None or float(accuracy) < MIN_PROMOTION_ACCURACY:
        blockers.append("accuracy_below_80_percent")

    accepted_recall = accepted_truth_metrics.get("lead_time_hit_rate")
    if accepted_recall is None or float(accepted_recall) < MIN_PROMOTION_LEAD_TIME_RECALL:
        blockers.append("lead_time_recall_below_80_percent_on_accepted_truth")

    if accepted_truth_metrics.get("observed_positive_count", 0) < 1:
        blockers.append("accepted_outbreak_validation_window_missing")

    accepted_precision = accepted_truth_metrics.get("precision")
    if accepted_precision is None or float(accepted_precision) < MIN_PROMOTION_PRECISION:
        blockers.append("precision_collapsed_on_accepted_truth")

    false_alerts_per_true_hit = accepted_truth_metrics.get("false_alerts_per_true_hit")
    if false_alerts_per_true_hit is not None and float(false_alerts_per_true_hit) > MAX_FALSE_ALERTS_PER_TRUE_HIT:
        blockers.append("false_alert_cost_too_high_on_accepted_truth")

    return {
        "passed": not blockers,
        "blockers": list(dict.fromkeys(blockers)),
        "metrics_checked": {
            "minimum_accuracy": MIN_PROMOTION_ACCURACY,
            "minimum_lead_time_recall_on_accepted_truth": MIN_PROMOTION_LEAD_TIME_RECALL,
            "minimum_precision_on_accepted_truth": MIN_PROMOTION_PRECISION,
            "maximum_false_alerts_per_true_hit_on_accepted_truth": MAX_FALSE_ALERTS_PER_TRUE_HIT,
            "overall_metrics": metrics,
            "accepted_truth_metrics": accepted_truth_metrics,
            "accepted_truth_levels": sorted(ACCEPTED_PROMOTION_TRUTH_LEVELS),
        },
    }


def _promotion_gates(
    *,
    feature_dataset: FeatureDataset,
    label_dataset: FeatureDataset,
    train_examples: list[dict],
    validation_examples: list[dict],
    split: dict,
    model_metrics: dict,
    baseline_metrics: dict,
) -> dict:
    blockers = []
    train_label_counts = Counter(example["label"] for example in train_examples)
    validation_truth_levels = Counter(example["truth_level"] for example in validation_examples)
    accepted_truth_validation_row_count = sum(
        validation_truth_levels.get(truth_level, 0) for truth_level in ACCEPTED_PROMOTION_TRUTH_LEVELS
    )
    accepted_outbreak_validation_row_count = sum(
        1
        for example in validation_examples
        if example["truth_level"] in ACCEPTED_PROMOTION_TRUTH_LEVELS and example["label"] == 1
    )
    seeded_demo_validation_row_count = validation_truth_levels.get(SEEDED_DEMO_TRUTH_LEVEL, 0)
    algorithm_metric_gate_results = {
        algorithm: _algorithm_promotion_metric_gate(model_metrics[algorithm])
        for algorithm in [ALGORITHM_LOGISTIC_REGRESSION, ALGORITHM_RANDOM_FOREST]
    }
    lead_time_label_dataset = (
        (label_dataset.lineage_metadata or {}).get("generation_mode")
        == SURVEILLANCE_LEAD_TIME_LABEL_GENERATION_MODE
    )
    leakage_checks_pass = bool(validation_examples) and all(
        example["leakage_check_passed"] for example in validation_examples
    )
    if split.get("status") != "ready":
        blockers.append("out_of_time_validation_missing")
    if len(train_label_counts) < 2:
        blockers.append("training_split_lacks_positive_and_negative_classes")
    if not validation_examples:
        blockers.append("validation_split_missing")
    if not leakage_checks_pass:
        blockers.append("leakage_checks_not_passing")
    if not validation_truth_levels:
        blockers.append("truth_level_evidence_missing")
    if validation_examples and not accepted_truth_validation_row_count:
        blockers.append("accepted_surveillance_truth_missing")
    if validation_examples and seeded_demo_validation_row_count == len(validation_examples):
        blockers.append("seeded_demo_only_validation_truth_cannot_promote")
    if validation_examples and not accepted_outbreak_validation_row_count:
        blockers.append("accepted_outbreak_validation_window_missing")
    if not lead_time_label_dataset:
        blockers.append("lead_time_label_dataset_missing")
    if feature_dataset.schema_version != LEAD_TIME_FEATURE_SCHEMA_VERSION:
        blockers.append("lead_time_feature_dataset_missing")
    if baseline_metrics.get("status") != "evaluated":
        blockers.append("rainfall_threshold_baseline_missing")
    if any(
        model_metrics[algorithm].get("status") != "evaluated"
        for algorithm in [ALGORITHM_LOGISTIC_REGRESSION, ALGORITHM_RANDOM_FOREST]
    ):
        blockers.append("model_temporal_backtest_missing")
    if not any(result["passed"] for result in algorithm_metric_gate_results.values()):
        blockers.append("promotion_metric_thresholds_not_met")

    return {
        "passed": not blockers,
        "blockers": list(dict.fromkeys(blockers)),
        "checks": {
            "temporal_split_ready": split.get("status") == "ready",
            "training_contains_both_classes": len(train_label_counts) >= 2,
            "validation_contains_rows": bool(validation_examples),
            "validation_leakage_checks_pass": leakage_checks_pass,
            "truth_level_counts": dict(validation_truth_levels),
            "accepted_truth_validation_row_count": accepted_truth_validation_row_count,
            "accepted_outbreak_validation_row_count": accepted_outbreak_validation_row_count,
            "seeded_demo_validation_row_count": seeded_demo_validation_row_count,
            "accepted_surveillance_truth_available": accepted_truth_validation_row_count > 0,
            "lead_time_label_dataset": lead_time_label_dataset,
            "lead_time_feature_dataset": feature_dataset.schema_version == LEAD_TIME_FEATURE_SCHEMA_VERSION,
            "rainfall_threshold_baseline_compared": baseline_metrics.get("status") == "evaluated",
            "promotion_metric_thresholds": {
                "minimum_accuracy": MIN_PROMOTION_ACCURACY,
                "minimum_lead_time_recall_on_accepted_truth": MIN_PROMOTION_LEAD_TIME_RECALL,
                "minimum_precision_on_accepted_truth": MIN_PROMOTION_PRECISION,
                "maximum_false_alerts_per_true_hit_on_accepted_truth": MAX_FALSE_ALERTS_PER_TRUE_HIT,
                "algorithm_results": algorithm_metric_gate_results,
            },
            "negative_binomial_facility_burden_forecasting_separate": True,
        },
    }


def build_temporal_backtest_report(
    *,
    feature_dataset: FeatureDataset,
    label_dataset: FeatureDataset,
    train_end_date: date | None = None,
    validation_start_date: date | None = None,
    rainfall_threshold_mm: float = 50.0,
) -> dict:
    examples = _aligned_examples(feature_dataset=feature_dataset, label_dataset=label_dataset)
    train_examples, validation_examples, split = _temporal_split(
        examples,
        train_end_date=train_end_date,
        validation_start_date=validation_start_date,
    )
    split = {
        **split,
        "train_start_date": split.get("train_start_date").isoformat() if split.get("train_start_date") else None,
        "train_end_date": split.get("train_end_date").isoformat() if split.get("train_end_date") else None,
        "validation_start_date": split.get("validation_start_date").isoformat()
        if split.get("validation_start_date")
        else None,
        "validation_end_date": split.get("validation_end_date").isoformat() if split.get("validation_end_date") else None,
    }

    model_metrics = {
        ALGORITHM_LOGISTIC_REGRESSION: _fit_model_metrics(
            algorithm=ALGORITHM_LOGISTIC_REGRESSION,
            train_examples=train_examples,
            validation_examples=validation_examples,
        ),
        ALGORITHM_RANDOM_FOREST: _fit_model_metrics(
            algorithm=ALGORITHM_RANDOM_FOREST,
            train_examples=train_examples,
            validation_examples=validation_examples,
        ),
    }
    baseline_metrics = _rainfall_threshold_metrics(
        validation_examples=validation_examples,
        threshold_mm=rainfall_threshold_mm,
    )
    promotion_gates = _promotion_gates(
        feature_dataset=feature_dataset,
        label_dataset=label_dataset,
        train_examples=train_examples,
        validation_examples=validation_examples,
        split=split,
        model_metrics=model_metrics,
        baseline_metrics=baseline_metrics,
    )
    validation_dates = sorted({example["prediction_date"] for example in validation_examples})
    lead_time_days_supported = [
        (label_dataset.lineage_metadata or {}).get("label_window_start_offset_days"),
        (label_dataset.lineage_metadata or {}).get("label_window_end_offset_days"),
    ]
    lead_time_days_supported = [value for value in lead_time_days_supported if isinstance(value, int)]
    truth_level_counts = Counter(example["truth_level"] for example in validation_examples)
    leakage_failures = [
        {
            "feature_row_id": example["feature_row_id"],
            "ward_id": example["ward_id"],
            "prediction_date": example["prediction_date"].isoformat(),
        }
        for example in validation_examples
        if not example["leakage_check_passed"]
    ]

    return {
        "schema_version": WARD_RISK_TEMPORAL_BACKTEST_SCHEMA_VERSION,
        "feature_dataset_ref": feature_dataset.dataset_ref,
        "feature_dataset_id": feature_dataset.id,
        "feature_schema_version": feature_dataset.schema_version,
        "label_dataset_ref": label_dataset.dataset_ref,
        "label_feature_dataset_id": label_dataset.id,
        "label_generation_mode": (label_dataset.lineage_metadata or {}).get("generation_mode"),
        "temporal_split": split,
        "row_counts": {
            "aligned_row_count": len(examples),
            "training_row_count": len(train_examples),
            "validation_row_count": len(validation_examples),
            "validation_prediction_date_count": len(validation_dates),
        },
        "evaluation_dimensions": ["ward", "month", "season", "truth_level"],
        "metrics": {
            **model_metrics,
            RAINFALL_THRESHOLD_BASELINE_KEY: baseline_metrics,
        },
        "comparison": {
            "logistic_vs_rainfall_accuracy_delta": _accuracy_delta(
                model_metrics[ALGORITHM_LOGISTIC_REGRESSION],
                baseline_metrics,
            ),
            "random_forest_vs_rainfall_accuracy_delta": _accuracy_delta(
                model_metrics[ALGORITHM_RANDOM_FOREST],
                baseline_metrics,
            ),
            "random_forest_vs_logistic_accuracy_delta": _accuracy_delta(
                model_metrics[ALGORITHM_RANDOM_FOREST],
                model_metrics[ALGORITHM_LOGISTIC_REGRESSION],
            ),
        },
        "truth_summary": {
            "validation_truth_level_counts": dict(truth_level_counts),
            "confirmed_truth_validation_row_count": truth_level_counts.get("confirmed_surveillance", 0),
            "proxy_or_field_validation_row_count": sum(
                truth_level_counts.get(value, 0)
                for value in ["proxy_diarrheal_signal", "field_signal_only", "seeded_demo"]
            ),
        },
        "leakage_summary": {
            "validation_rows_passing_leakage_check": sum(
                1 for example in validation_examples if example["leakage_check_passed"]
            ),
            "validation_rows_failing_leakage_check": len(leakage_failures),
            "leakage_failures": leakage_failures[:50],
        },
        "lead_time_days_supported": lead_time_days_supported,
        "promotion_gates": promotion_gates,
        "facility_burden_forecast_separation": {
            "negative_binomial_facility_burden_forecasting_separate": True,
            "ward_risk_classification_model_family": "ward_risk_classification",
            "facility_forecast_model_family": "facility_burden_forecast_negative_binomial",
        },
    }


def _accuracy_delta(left: dict, right: dict) -> float | None:
    left_accuracy = (left.get("metrics") or {}).get("accuracy")
    right_accuracy = (right.get("metrics") or {}).get("accuracy")
    if left_accuracy is None or right_accuracy is None:
        return None
    return round(float(left_accuracy) - float(right_accuracy), 6)


def _selected_algorithm_promotion_gate(report: dict, algorithm: str) -> dict:
    algorithm_results = (
        ((report.get("promotion_gates") or {}).get("checks") or {})
        .get("promotion_metric_thresholds", {})
        .get("algorithm_results", {})
    )
    selected_result = algorithm_results.get(algorithm)
    if not selected_result:
        return {
            "passed": False,
            "blockers": ["selected_model_promotion_metric_gate_missing"],
        }
    return {
        "passed": selected_result.get("passed") is True,
        "blockers": selected_result.get("blockers") or [],
    }


def _promotion_evidence_binding_gate(*, model_run: ModelRun, report: dict) -> dict:
    blockers = []
    report_feature_dataset_ref = report.get("feature_dataset_ref")
    report_label_dataset_ref = report.get("label_dataset_ref")

    if model_run.status != ModelRun.STATUS_SUCCESS:
        blockers.append("model_run_not_successful")
    if not report_feature_dataset_ref:
        blockers.append("promotion_feature_dataset_ref_missing")
    elif not model_run.inference_dataset_ref:
        blockers.append("model_run_inference_dataset_ref_missing")
    elif model_run.inference_dataset_ref != report_feature_dataset_ref:
        blockers.append("promotion_feature_dataset_mismatch")
    if not report_label_dataset_ref:
        blockers.append("promotion_label_dataset_ref_missing")

    return {
        "passed": not blockers,
        "blockers": blockers,
        "model_run_id": model_run.id,
        "model_run_status": model_run.status,
        "model_run_inference_dataset_ref": model_run.inference_dataset_ref,
        "report_feature_dataset_ref": report_feature_dataset_ref,
        "report_label_dataset_ref": report_label_dataset_ref,
    }


def _training_truth_promotion_gate(model_run: ModelRun) -> dict:
    blockers = []
    training_dataset = model_run.training_feature_dataset
    lineage = (training_dataset.lineage_metadata or {}) if training_dataset else {}
    usage = lineage.get("surveillance_label_usage")
    readiness = lineage.get("training_label_readiness") or {}
    truth_gate = lineage.get("surveillance_label_truth_gate") or {}
    try:
        seeded_row_count = int(lineage.get("training_label_seeded_demo_row_count") or 0)
    except (TypeError, ValueError):
        seeded_row_count = 0

    if training_dataset is None:
        blockers.append("promotion_training_feature_dataset_missing")
    else:
        if training_dataset.dataset_kind != FeatureDataset.KIND_TRAINING:
            blockers.append("promotion_training_feature_dataset_kind_invalid")
        if training_dataset.source_kind == FeatureDataset.SOURCE_KIND_SEEDED:
            blockers.append("promotion_training_feature_dataset_seeded")

    if usage != SURVEILLANCE_LABEL_TRAINING_USAGE:
        blockers.append("promotion_training_labels_not_surveillance_aligned")
    if seeded_row_count > 0:
        blockers.append("promotion_training_seeded_demo_rows_present")
    if readiness.get("ready") is not True:
        blockers.append(readiness.get("reason") or "promotion_training_label_readiness_not_ready")
    if truth_gate.get("proxy_only_as_confirmed_allowed") is True:
        blockers.append("promotion_training_proxy_only_truth_allowed")
    if not lineage.get("surveillance_label_dataset_ref"):
        blockers.append("promotion_training_label_dataset_ref_missing")

    return {
        "passed": not blockers,
        "blockers": list(dict.fromkeys(blockers)),
        "training_feature_dataset_id": training_dataset.id if training_dataset else None,
        "training_dataset_ref": training_dataset.dataset_ref if training_dataset else None,
        "training_dataset_source_kind": training_dataset.source_kind if training_dataset else None,
        "surveillance_label_usage": usage,
        "training_label_seeded_demo_row_count": seeded_row_count,
        "training_label_readiness": readiness,
        "surveillance_label_truth_gate": truth_gate,
        "surveillance_label_dataset_ref": lineage.get("surveillance_label_dataset_ref"),
    }


def _materialize_promoted_risk_scores_to_wards(model_run: ModelRun) -> int:
    updated_ward_ids = set()
    for risk_score in model_run.risk_scores.select_related("ward").order_by("-generated_at", "-id"):
        if risk_score.ward_id in updated_ward_ids:
            continue
        ward = risk_score.ward
        ward.current_risk_level = risk_score.risk_level
        ward.current_risk_score = risk_score.score
        ward.save(update_fields=["current_risk_level", "current_risk_score", "updated_at"])
        updated_ward_ids.add(risk_score.ward_id)
    return len(updated_ward_ids)


def persist_temporal_backtest_report(
    *,
    model_run: ModelRun,
    report: dict,
    promote: bool = False,
) -> ModelRun:
    algorithm = algorithm_key_from_run(model_run) or ALGORITHM_LOGISTIC_REGRESSION
    selected_metrics = ((report.get("metrics") or {}).get(algorithm) or {}).get("metrics") or {}
    gates = report.get("promotion_gates") or {}
    selected_algorithm_gate = _selected_algorithm_promotion_gate(report, algorithm)
    binding_gate = _promotion_evidence_binding_gate(model_run=model_run, report=report)
    training_truth_gate = _training_truth_promotion_gate(model_run)
    if promote and not gates.get("passed"):
        blockers = ", ".join(gates.get("blockers") or ["unknown"])
        raise ValueError(f"Cannot promote model_run={model_run.id}; Phase 4 gates failed: {blockers}")
    if promote and not selected_algorithm_gate["passed"]:
        blockers = ", ".join(selected_algorithm_gate["blockers"] or ["unknown"])
        raise ValueError(
            f"Cannot promote model_run={model_run.id}; selected model Phase 4 metric gates failed: {blockers}"
        )
    if promote and not binding_gate["passed"]:
        blockers = ", ".join(binding_gate["blockers"] or ["unknown"])
        raise ValueError(f"Cannot promote model_run={model_run.id}; promotion evidence binding failed: {blockers}")
    if promote and not training_truth_gate["passed"]:
        blockers = ", ".join(training_truth_gate["blockers"] or ["unknown"])
        raise ValueError(f"Cannot promote model_run={model_run.id}; training truth gate failed: {blockers}")

    evaluation_metrics = model_run.evaluation_metrics or {}
    evaluation_metrics.update(
        {
            "temporal_backtest_report": report,
            "phase_4_temporal_backtest_schema_version": report.get("schema_version"),
            "out_of_time_score": selected_metrics.get("accuracy"),
            "calibration_score": selected_metrics.get("calibration_score"),
            "lead_time_recall": selected_metrics.get("lead_time_hit_rate"),
            "precision": selected_metrics.get("precision"),
            "balanced_accuracy": selected_metrics.get("balanced_accuracy"),
            "f1_score": selected_metrics.get("f1_score"),
            "false_alert_rate": selected_metrics.get("false_alert_rate"),
            "false_alerts_per_true_hit": selected_metrics.get("false_alerts_per_true_hit"),
            "area_under_precision_recall_curve": selected_metrics.get("area_under_precision_recall_curve"),
            "positive_class_balance": selected_metrics.get("positive_class_balance"),
            "lead_time_days_supported": report.get("lead_time_days_supported", []),
            "temporal_validation_window_count": (report.get("row_counts") or {}).get(
                "validation_prediction_date_count",
                0,
            ),
            "rainfall_threshold_baseline_accuracy": (
                ((report.get("metrics") or {}).get(RAINFALL_THRESHOLD_BASELINE_KEY) or {}).get("metrics") or {}
            ).get("accuracy"),
            "promotion_truth_and_leakage_checks_passed": gates.get("passed", False),
            "phase_4_selected_model_promotion_metric_gate_passed": selected_algorithm_gate["passed"],
            "phase_4_promotion_evidence_binding_passed": binding_gate["passed"],
            "phase_4_training_truth_gate_passed": training_truth_gate["passed"],
        }
    )
    metadata = model_run.metadata or {}
    materialized_ward_count = 0
    if promote:
        materialized_ward_count = _materialize_promoted_risk_scores_to_wards(model_run)
    metadata.update(
        {
            "phase_4_promotion_evidence_persisted": True,
            "phase_4_promotion_gates_passed": gates.get("passed", False),
            "phase_4_promotion_blockers": gates.get("blockers", []),
            "phase_4_selected_model_promotion_metric_gate_passed": selected_algorithm_gate["passed"],
            "phase_4_selected_model_promotion_metric_blockers": selected_algorithm_gate["blockers"],
            "phase_4_promotion_evidence_binding": binding_gate,
            "phase_4_training_truth_gate": training_truth_gate,
            "promotion_evidence_report_ref": f"model_run:{model_run.id}:temporal_backtest_report",
            "ward_risk_classification_backtest_dataset_ref": report.get("feature_dataset_ref"),
            "ward_risk_classification_label_dataset_ref": report.get("label_dataset_ref"),
            "facility_burden_forecast_model_family_separate": True,
            "risk_score_model_run_linkage": {
                "risk_score_count": model_run.risk_scores.count(),
                "risk_scores_link_to_model_run": True,
                "model_version": model_run.model_version,
            },
        }
    )
    if promote:
        metadata.update(
            {
                "promotion_state": "promoted",
                "promotion_target": PROMOTION_TARGET_LIVE_BASELINE,
                "promotion_decision_source": "phase_4_temporal_backtest",
                "promotion_blockers_at_decision": [],
                "alert_eligible": True,
                "promoted_risk_scores_materialized_to_wards": materialized_ward_count,
            }
        )
    model_run.evaluation_metrics = evaluation_metrics
    model_run.metadata = metadata
    model_run.save(update_fields=["evaluation_metrics", "metadata"])
    return model_run
