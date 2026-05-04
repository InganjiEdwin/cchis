from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from math import sqrt
from uuid import uuid4

from django.db import transaction
from django.utils import timezone

from risk.models import (
    FeatureDataset,
    FeatureDatasetRow,
    ModelMonitoringSnapshot,
    ModelMonitoringState,
    ModelMonitoringThreshold,
    ModelMonitoringThresholdDirection,
    ModelRegistryEntry,
    ModelRegistryMonitoringState,
    RiskScore,
    Ward,
)

from .registry import active_model_registry_entry


MODEL_MONITORING_SCHEMA_VERSION = "ward-risk-model-monitoring-v1"
MODEL_MONITORING_THRESHOLD_VERSION = "phase-2-default-v1"

METRIC_FEATURE_DISTRIBUTION_DRIFT = "feature_distribution_drift"
METRIC_SCORE_DISTRIBUTION_DRIFT = "score_distribution_drift"
METRIC_CALIBRATION_DRIFT = "calibration_drift"
METRIC_RECALL_DECAY = "recall_decay"
METRIC_PRECISION_DECAY = "precision_decay"
METRIC_SOURCE_QUALITY_DRIFT = "source_quality_drift"
METRIC_WARD_PERFORMANCE_DEGRADATION = "ward_performance_degradation"
METRIC_SEASON_PERFORMANCE_DEGRADATION = "season_performance_degradation"

DEFAULT_MONITORING_THRESHOLDS = {
    METRIC_FEATURE_DISTRIBUTION_DRIFT: {
        "warning_threshold": 0.25,
        "breach_threshold": 0.50,
        "baseline_window": "training_feature_dataset_vs_current_inference_feature_dataset",
    },
    METRIC_SCORE_DISTRIBUTION_DRIFT: {
        "warning_threshold": 0.10,
        "breach_threshold": 0.20,
        "baseline_window": "promotion_score_mean_vs_current_score_mean",
    },
    METRIC_CALIBRATION_DRIFT: {
        "warning_threshold": 0.10,
        "breach_threshold": 0.20,
        "baseline_window": "phase_4_calibration_score_vs_new_labels",
    },
    METRIC_RECALL_DECAY: {
        "warning_threshold": 0.10,
        "breach_threshold": 0.20,
        "baseline_window": "phase_4_lead_time_recall_vs_new_labels",
    },
    METRIC_PRECISION_DECAY: {
        "warning_threshold": 0.10,
        "breach_threshold": 0.20,
        "baseline_window": "phase_4_precision_vs_new_labels",
    },
    METRIC_SOURCE_QUALITY_DRIFT: {
        "warning_threshold": 0.20,
        "breach_threshold": 0.40,
        "baseline_window": "training_source_quality_vs_current_inference_source_quality",
    },
    METRIC_WARD_PERFORMANCE_DEGRADATION: {
        "warning_threshold": 0.15,
        "breach_threshold": 0.30,
        "baseline_window": "phase_4_calibration_score_vs_worst_labeled_ward",
    },
    METRIC_SEASON_PERFORMANCE_DEGRADATION: {
        "warning_threshold": 0.15,
        "breach_threshold": 0.30,
        "baseline_window": "phase_4_calibration_score_vs_worst_labeled_season",
    },
}


def ensure_default_monitoring_thresholds() -> dict[str, ModelMonitoringThreshold]:
    thresholds = {}
    with transaction.atomic():
        for metric_name, config in DEFAULT_MONITORING_THRESHOLDS.items():
            active_threshold = ModelMonitoringThreshold.objects.filter(
                metric_name=metric_name,
                is_active=True,
            ).order_by("-created_at", "-id").first()
            if active_threshold is not None:
                thresholds[metric_name] = active_threshold
                continue
            threshold, _created = ModelMonitoringThreshold.objects.update_or_create(
                metric_name=metric_name,
                version=MODEL_MONITORING_THRESHOLD_VERSION,
                defaults={
                    "warning_threshold": config["warning_threshold"],
                    "breach_threshold": config["breach_threshold"],
                    "direction": ModelMonitoringThresholdDirection.HIGHER_IS_WORSE,
                    "baseline_window": config["baseline_window"],
                    "is_active": True,
                    "metadata": {
                        "schema_version": MODEL_MONITORING_SCHEMA_VERSION,
                        "phase": "phase_2_drift_and_calibration_monitoring",
                    },
                },
            )
            thresholds[metric_name] = threshold
    return thresholds


def run_model_monitoring(
    *,
    registry_entry: ModelRegistryEntry | None = None,
    label_dataset_ref: str = "",
) -> list[ModelMonitoringSnapshot]:
    registry_entry = registry_entry or active_model_registry_entry()
    if registry_entry is None:
        raise ValueError("active_model_registry_entry_missing")

    thresholds = ensure_default_monitoring_thresholds()
    model_run = registry_entry.model_run
    training_dataset = model_run.training_feature_dataset
    inference_dataset = model_run.inference_feature_dataset
    label_dataset = _resolve_label_dataset(
        model_run=model_run,
        label_dataset_ref=label_dataset_ref,
    )
    monitoring_run_id = uuid4()
    generated_at = timezone.now()

    snapshot_inputs = [
        _feature_distribution_drift(
            registry_entry=registry_entry,
            training_dataset=training_dataset,
            inference_dataset=inference_dataset,
        ),
        _score_distribution_drift(registry_entry=registry_entry),
        _source_quality_drift(
            training_dataset=training_dataset,
            inference_dataset=inference_dataset,
        ),
        *_label_metric_snapshots(
            registry_entry=registry_entry,
            label_dataset=label_dataset,
        ),
    ]

    snapshots: list[ModelMonitoringSnapshot] = []
    with transaction.atomic():
        for item in snapshot_inputs:
            threshold = thresholds[item["metric_name"]]
            state = _state_for_value(item["value"], threshold)
            snapshot = ModelMonitoringSnapshot.objects.create(
                monitoring_run_id=monitoring_run_id,
                registry_entry=registry_entry,
                model_run=model_run,
                threshold=threshold,
                metric_name=item["metric_name"],
                metric_family=item["metric_family"],
                value=item["value"],
                baseline_value=item["baseline_value"],
                threshold_value=threshold.breach_threshold,
                threshold_version=threshold.version,
                state=state,
                generated_at=generated_at,
                source_dataset_refs=item["source_dataset_refs"],
                metadata={
                    "schema_version": MODEL_MONITORING_SCHEMA_VERSION,
                    "warning_threshold": threshold.warning_threshold,
                    "breach_threshold": threshold.breach_threshold,
                    "threshold_direction": threshold.direction,
                    **item["metadata"],
                },
            )
            snapshots.append(snapshot)
        registry_metadata = registry_entry.metadata or {}
        score_item = next(
            (item for item in snapshot_inputs if item["metric_name"] == METRIC_SCORE_DISTRIBUTION_DRIFT),
            None,
        )
        if (
            score_item is not None
            and "score_distribution_baseline_mean" not in registry_metadata
            and score_item["metadata"].get("current_score_mean") is not None
        ):
            registry_metadata["score_distribution_baseline_mean"] = score_item["metadata"]["current_score_mean"]
        registry_entry.monitoring_state = _registry_monitoring_state(snapshots)
        registry_entry.metadata = {
            **registry_metadata,
            "latest_monitoring_run_id": str(monitoring_run_id),
            "latest_monitoring_generated_at": generated_at.isoformat(),
            "latest_monitoring_snapshot_states": {
                snapshot.metric_name: snapshot.state for snapshot in snapshots
            },
        }
        registry_entry.save(update_fields=["monitoring_state", "metadata", "updated_at"])
    return snapshots


def _state_for_value(value: float | None, threshold: ModelMonitoringThreshold) -> str:
    if value is None:
        return ModelMonitoringState.NOT_READY
    warning = threshold.warning_threshold
    breach = threshold.breach_threshold
    if threshold.direction == ModelMonitoringThresholdDirection.LOWER_IS_WORSE:
        if breach is not None and value <= breach:
            return ModelMonitoringState.BREACHED
        if warning is not None and value <= warning:
            return ModelMonitoringState.WARNING
        return ModelMonitoringState.HEALTHY
    if breach is not None and value >= breach:
        return ModelMonitoringState.BREACHED
    if warning is not None and value >= warning:
        return ModelMonitoringState.WARNING
    return ModelMonitoringState.HEALTHY


def _registry_monitoring_state(snapshots: list[ModelMonitoringSnapshot]) -> str:
    states = {snapshot.state for snapshot in snapshots}
    if ModelMonitoringState.BREACHED in states:
        return ModelRegistryMonitoringState.BREACHED
    if ModelMonitoringState.WARNING in states or ModelMonitoringState.NOT_READY in states:
        return ModelRegistryMonitoringState.WARNING
    return ModelRegistryMonitoringState.HEALTHY


def _resolve_label_dataset(*, model_run, label_dataset_ref: str = "") -> FeatureDataset | None:
    refs = []
    if label_dataset_ref:
        refs.append(label_dataset_ref)
    metadata = model_run.metadata or {}
    evaluation_metrics = model_run.evaluation_metrics or {}
    temporal_report = evaluation_metrics.get("temporal_backtest_report") or {}
    refs.extend(
        [
            metadata.get("ward_risk_classification_label_dataset_ref"),
            temporal_report.get("label_dataset_ref"),
            (metadata.get("phase_4_promotion_evidence_binding") or {}).get("report_label_dataset_ref"),
        ]
    )
    for ref in refs:
        if not ref:
            continue
        dataset = FeatureDataset.objects.filter(dataset_ref=ref).first()
        if dataset is not None:
            return dataset
    return None


def _feature_distribution_drift(
    *,
    registry_entry: ModelRegistryEntry,
    training_dataset: FeatureDataset | None,
    inference_dataset: FeatureDataset | None,
) -> dict:
    source_dataset_refs = _dataset_refs(training_dataset, inference_dataset)
    if training_dataset is None or inference_dataset is None:
        return _not_ready_metric(
            metric_name=METRIC_FEATURE_DISTRIBUTION_DRIFT,
            metric_family="drift",
            source_dataset_refs=source_dataset_refs,
            reason="training_or_inference_feature_dataset_missing",
        )
    baseline_stats = _numeric_feature_stats(training_dataset)
    current_stats = _numeric_feature_stats(inference_dataset)
    shared_keys = sorted(set(baseline_stats) & set(current_stats))
    if not shared_keys:
        return _not_ready_metric(
            metric_name=METRIC_FEATURE_DISTRIBUTION_DRIFT,
            metric_family="drift",
            source_dataset_refs=source_dataset_refs,
            reason="no_shared_numeric_feature_keys",
        )
    feature_drifts = {}
    for key in shared_keys:
        baseline = baseline_stats[key]
        current = current_stats[key]
        denominator = baseline["stddev"] or abs(baseline["mean"]) or 1.0
        feature_drifts[key] = round(abs(current["mean"] - baseline["mean"]) / denominator, 6)
    value = round(sum(feature_drifts.values()) / len(feature_drifts), 6)
    return {
        "metric_name": METRIC_FEATURE_DISTRIBUTION_DRIFT,
        "metric_family": "drift",
        "value": value,
        "baseline_value": 0.0,
        "source_dataset_refs": source_dataset_refs,
        "metadata": {
            "feature_drifts": feature_drifts,
            "shared_feature_keys": shared_keys,
            "registry_entry_id": registry_entry.id,
        },
    }


def _score_distribution_drift(*, registry_entry: ModelRegistryEntry) -> dict:
    risk_scores = list(
        RiskScore.objects.filter(model_run=registry_entry.model_run).order_by("generated_at", "id")
    )
    source_dataset_refs = [f"model_run:{registry_entry.model_run_id}:risk_scores"]
    if not risk_scores:
        return _not_ready_metric(
            metric_name=METRIC_SCORE_DISTRIBUTION_DRIFT,
            metric_family="drift",
            source_dataset_refs=source_dataset_refs,
            reason="model_run_has_no_risk_scores",
        )
    score_mean = _mean([risk_score.score for risk_score in risk_scores])
    metadata = registry_entry.metadata or {}
    baseline_mean = metadata.get("score_distribution_baseline_mean")
    if baseline_mean is None:
        baseline_mean = score_mean
    value = round(abs(score_mean - float(baseline_mean)), 6)
    return {
        "metric_name": METRIC_SCORE_DISTRIBUTION_DRIFT,
        "metric_family": "drift",
        "value": value,
        "baseline_value": round(float(baseline_mean), 6),
        "source_dataset_refs": source_dataset_refs,
        "metadata": {
            "current_score_mean": round(score_mean, 6),
            "risk_score_count": len(risk_scores),
            "baseline_source": (
                "registry_entry.metadata.score_distribution_baseline_mean"
                if "score_distribution_baseline_mean" in metadata
                else "current_scores_first_monitoring_run"
            ),
        },
    }


def _source_quality_drift(
    *,
    training_dataset: FeatureDataset | None,
    inference_dataset: FeatureDataset | None,
) -> dict:
    source_dataset_refs = _dataset_refs(training_dataset, inference_dataset)
    if training_dataset is None or inference_dataset is None:
        return _not_ready_metric(
            metric_name=METRIC_SOURCE_QUALITY_DRIFT,
            metric_family="source_quality",
            source_dataset_refs=source_dataset_refs,
            reason="training_or_inference_feature_dataset_missing",
        )
    baseline_quality = _dataset_quality_score(training_dataset)
    current_quality = _dataset_quality_score(inference_dataset)
    value = round(max(0.0, baseline_quality["score"] - current_quality["score"]), 6)
    return {
        "metric_name": METRIC_SOURCE_QUALITY_DRIFT,
        "metric_family": "source_quality",
        "value": value,
        "baseline_value": baseline_quality["score"],
        "source_dataset_refs": source_dataset_refs,
        "metadata": {
            "baseline_quality": baseline_quality,
            "current_quality": current_quality,
        },
    }


def _label_metric_snapshots(
    *,
    registry_entry: ModelRegistryEntry,
    label_dataset: FeatureDataset | None,
) -> list[dict]:
    source_dataset_refs = _dataset_refs(label_dataset)
    metric_names = [
        METRIC_CALIBRATION_DRIFT,
        METRIC_RECALL_DECAY,
        METRIC_PRECISION_DECAY,
        METRIC_WARD_PERFORMANCE_DEGRADATION,
        METRIC_SEASON_PERFORMANCE_DEGRADATION,
    ]
    if label_dataset is None:
        return [
            _not_ready_metric(
                metric_name=metric_name,
                metric_family="post_label_performance",
                source_dataset_refs=source_dataset_refs,
                reason="label_dataset_missing",
            )
            for metric_name in metric_names
        ]

    examples = _labeled_prediction_examples(registry_entry=registry_entry, label_dataset=label_dataset)
    if not examples:
        return [
            _not_ready_metric(
                metric_name=metric_name,
                metric_family="post_label_performance",
                source_dataset_refs=source_dataset_refs,
                reason="no_labeled_prediction_examples",
            )
            for metric_name in metric_names
        ]

    observed = _binary_metrics(examples)
    metrics = registry_entry.model_run.evaluation_metrics or {}
    baseline_calibration = _float_or_none(metrics.get("calibration_score"))
    baseline_recall = _float_or_none(metrics.get("lead_time_recall"))
    baseline_precision = _float_or_none(metrics.get("precision"))
    ward_summaries = _grouped_calibration(examples, "ward_name")
    season_summaries = _grouped_calibration(examples, "season")
    worst_ward = _worst_group(ward_summaries)
    worst_season = _worst_group(season_summaries)

    return [
        _decay_metric(
            metric_name=METRIC_CALIBRATION_DRIFT,
            metric_family="calibration",
            baseline_value=baseline_calibration,
            observed_value=observed["calibration_score"],
            source_dataset_refs=source_dataset_refs,
            metadata={"observed_metrics": observed, "label_dataset_ref": label_dataset.dataset_ref},
        ),
        _decay_metric(
            metric_name=METRIC_RECALL_DECAY,
            metric_family="post_label_performance",
            baseline_value=baseline_recall,
            observed_value=observed["recall"],
            source_dataset_refs=source_dataset_refs,
            metadata={"observed_metrics": observed, "label_dataset_ref": label_dataset.dataset_ref},
        ),
        _decay_metric(
            metric_name=METRIC_PRECISION_DECAY,
            metric_family="post_label_performance",
            baseline_value=baseline_precision,
            observed_value=observed["precision"],
            source_dataset_refs=source_dataset_refs,
            metadata={"observed_metrics": observed, "label_dataset_ref": label_dataset.dataset_ref},
        ),
        _decay_metric(
            metric_name=METRIC_WARD_PERFORMANCE_DEGRADATION,
            metric_family="post_label_performance",
            baseline_value=baseline_calibration,
            observed_value=worst_ward["calibration_score"] if worst_ward else None,
            source_dataset_refs=source_dataset_refs,
            metadata={
                "group_dimension": "ward",
                "worst_group": worst_ward,
                "group_summaries": ward_summaries,
                "label_dataset_ref": label_dataset.dataset_ref,
            },
        ),
        _decay_metric(
            metric_name=METRIC_SEASON_PERFORMANCE_DEGRADATION,
            metric_family="post_label_performance",
            baseline_value=baseline_calibration,
            observed_value=worst_season["calibration_score"] if worst_season else None,
            source_dataset_refs=source_dataset_refs,
            metadata={
                "group_dimension": "season",
                "worst_group": worst_season,
                "group_summaries": season_summaries,
                "label_dataset_ref": label_dataset.dataset_ref,
            },
        ),
    ]


def _decay_metric(
    *,
    metric_name: str,
    metric_family: str,
    baseline_value: float | None,
    observed_value: float | None,
    source_dataset_refs: list[str],
    metadata: dict,
) -> dict:
    if baseline_value is None or observed_value is None:
        return _not_ready_metric(
            metric_name=metric_name,
            metric_family=metric_family,
            source_dataset_refs=source_dataset_refs,
            reason="baseline_or_observed_metric_missing",
            metadata=metadata,
        )
    return {
        "metric_name": metric_name,
        "metric_family": metric_family,
        "value": round(max(0.0, baseline_value - observed_value), 6),
        "baseline_value": round(baseline_value, 6),
        "source_dataset_refs": source_dataset_refs,
        "metadata": {
            **metadata,
            "observed_value": round(observed_value, 6),
        },
    }


def _not_ready_metric(
    *,
    metric_name: str,
    metric_family: str,
    source_dataset_refs: list[str],
    reason: str,
    metadata: dict | None = None,
) -> dict:
    return {
        "metric_name": metric_name,
        "metric_family": metric_family,
        "value": None,
        "baseline_value": None,
        "source_dataset_refs": source_dataset_refs,
        "metadata": {
            "not_ready_reason": reason,
            **(metadata or {}),
        },
    }


def _numeric_feature_stats(dataset: FeatureDataset) -> dict[str, dict]:
    values_by_key: dict[str, list[float]] = defaultdict(list)
    for row in FeatureDatasetRow.objects.filter(dataset=dataset).order_by("id"):
        for key, value in (row.feature_values or {}).items():
            numeric_value = _float_or_none(value)
            if numeric_value is None:
                continue
            values_by_key[key].append(numeric_value)
    return {
        key: {
            "mean": _mean(values),
            "stddev": _stddev(values),
            "count": len(values),
        }
        for key, values in values_by_key.items()
        if values
    }


def _dataset_quality_score(dataset: FeatureDataset) -> dict:
    source_kind_scores = {
        FeatureDataset.SOURCE_KIND_LIVE: 1.0,
        FeatureDataset.SOURCE_KIND_HYBRID: 0.7,
        FeatureDataset.SOURCE_KIND_SEEDED: 0.2,
    }
    base_score = source_kind_scores.get(dataset.source_kind, 0.5)
    rows = list(FeatureDatasetRow.objects.filter(dataset=dataset).order_by("id"))
    row_count = len(rows)
    if not row_count:
        return {
            "score": round(base_score * 0.8, 6),
            "source_kind": dataset.source_kind,
            "row_count": 0,
            "quality_penalty": round(base_score * 0.2, 6),
            "caveat_count": 0,
        }
    caveat_count = 0
    for row in rows:
        values = row.feature_values or {}
        if values.get("fallback_static_rainfall_used") is True:
            caveat_count += 1
        if values.get("climate_coverage_status") in {"insufficient", "insufficient_forecast_horizon"}:
            caveat_count += 1
        if values.get("source_confidence") in {"low", "unknown"}:
            caveat_count += 1
    penalty = min(0.5, caveat_count / max(row_count, 1) * 0.1)
    return {
        "score": round(max(0.0, base_score - penalty), 6),
        "source_kind": dataset.source_kind,
        "row_count": row_count,
        "quality_penalty": round(penalty, 6),
        "caveat_count": caveat_count,
    }


def _labeled_prediction_examples(*, registry_entry: ModelRegistryEntry, label_dataset: FeatureDataset) -> list[dict]:
    risk_scores_by_ward = {}
    for risk_score in RiskScore.objects.filter(model_run=registry_entry.model_run).order_by("-generated_at", "-id"):
        risk_scores_by_ward.setdefault(risk_score.ward_id, risk_score)

    examples = []
    for row in FeatureDatasetRow.objects.filter(dataset=label_dataset, ward__isnull=False).order_by("id"):
        if row.label not in {0, 1}:
            continue
        risk_score = risk_scores_by_ward.get(row.ward_id)
        if risk_score is None:
            continue
        probability = _bounded_probability(risk_score.score)
        examples.append(
            {
                "ward_id": row.ward_id,
                "ward_name": row.ward_name_snapshot,
                "season": _season_from_row(row),
                "label": int(row.label),
                "probability": probability,
                "predicted_label": 1 if risk_score.risk_level == Ward.RISK_HIGH or probability >= 0.7 else 0,
            }
        )
    return examples


def _binary_metrics(examples: list[dict]) -> dict:
    count = len(examples)
    true_positive = sum(1 for item in examples if item["label"] == 1 and item["predicted_label"] == 1)
    false_positive = sum(1 for item in examples if item["label"] == 0 and item["predicted_label"] == 1)
    true_negative = sum(1 for item in examples if item["label"] == 0 and item["predicted_label"] == 0)
    false_negative = sum(1 for item in examples if item["label"] == 1 and item["predicted_label"] == 0)
    predicted_positive = true_positive + false_positive
    observed_positive = true_positive + false_negative
    brier_score = (
        sum((item["probability"] - item["label"]) ** 2 for item in examples) / count if count else None
    )
    return {
        "row_count": count,
        "true_positive": true_positive,
        "false_positive": false_positive,
        "true_negative": true_negative,
        "false_negative": false_negative,
        "recall": round(true_positive / observed_positive, 6) if observed_positive else None,
        "precision": round(true_positive / predicted_positive, 6) if predicted_positive else None,
        "calibration_score": round(max(0.0, 1.0 - brier_score), 6) if brier_score is not None else None,
    }


def _grouped_calibration(examples: list[dict], group_key: str) -> list[dict]:
    grouped = defaultdict(list)
    for example in examples:
        grouped[str(example.get(group_key) or "unknown")].append(example)
    summaries = []
    for group, rows in sorted(grouped.items()):
        metrics = _binary_metrics(rows)
        summaries.append(
            {
                "group": group,
                "row_count": metrics["row_count"],
                "calibration_score": metrics["calibration_score"],
                "recall": metrics["recall"],
                "precision": metrics["precision"],
            }
        )
    return summaries


def _worst_group(group_summaries: list[dict]) -> dict | None:
    scored = [item for item in group_summaries if item.get("calibration_score") is not None]
    if not scored:
        return None
    return sorted(scored, key=lambda item: (item["calibration_score"], -item["row_count"], item["group"]))[0]


def _dataset_refs(*datasets: FeatureDataset | None) -> list[str]:
    return [
        f"feature_dataset:{dataset.dataset_ref}"
        for dataset in datasets
        if dataset is not None and dataset.dataset_ref
    ]


def _season_from_row(row: FeatureDatasetRow) -> str:
    values = row.feature_values or {}
    if values.get("season"):
        return str(values["season"])
    prediction_date = _parse_date(values.get("prediction_date"))
    month = prediction_date.month if prediction_date else row.month
    if month in {3, 4, 5}:
        return "long_rains"
    if month in {10, 11, 12}:
        return "short_rains"
    return "dry_or_transition"


def _parse_date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _bounded_probability(value) -> float:
    numeric = _float_or_none(value)
    if numeric is None:
        return 0.0
    return max(0.0, min(1.0, numeric))


def _float_or_none(value) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _stddev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = _mean(values)
    return sqrt(sum((value - mean) ** 2 for value in values) / len(values))
