from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from risk.models import (
    Alert,
    FeatureDataset,
    ModelMonitoringSnapshot,
    ModelMonitoringState,
    ModelRegistryEntry,
    ModelRegistryMonitoringState,
    ModelRetrainingRecommendation,
    ModelRetrainingRecommendationState,
    PopulationBaselineRecord,
    RiskScore,
    SurveillanceLabelWindow,
    SurveillanceOutbreakLabel,
    Ward,
)

from .registry import active_model_registry_entry
from .surveillance_lineage import label_window_is_currently_eligible


MODEL_RETRAINING_POLICY_SCHEMA_VERSION = "ward-risk-model-retraining-policy-v1"
DEFAULT_STALE_MODEL_MAX_DAYS = 90
DEFAULT_NEW_LABEL_VOLUME_THRESHOLD = 25
DEFAULT_REPEATED_FALSE_ALERT_THRESHOLD = 3
DEFAULT_REPEATED_MISS_THRESHOLD = 3


def evaluate_retraining_policy(
    *,
    registry_entry: ModelRegistryEntry | None = None,
    stale_model_max_days: int = DEFAULT_STALE_MODEL_MAX_DAYS,
    new_label_volume_threshold: int = DEFAULT_NEW_LABEL_VOLUME_THRESHOLD,
    repeated_false_alert_threshold: int = DEFAULT_REPEATED_FALSE_ALERT_THRESHOLD,
    repeated_miss_threshold: int = DEFAULT_REPEATED_MISS_THRESHOLD,
) -> ModelRetrainingRecommendation:
    registry_entry = registry_entry or active_model_registry_entry()
    if registry_entry is None:
        raise ValueError("active_model_registry_entry_missing")

    now = timezone.now()
    active_from = registry_entry.active_from or registry_entry.model_run.completed_at or registry_entry.model_run.started_at
    trigger_summary = _trigger_summary(
        registry_entry=registry_entry,
        active_from=active_from,
        now=now,
        stale_model_max_days=stale_model_max_days,
        new_label_volume_threshold=new_label_volume_threshold,
        repeated_false_alert_threshold=repeated_false_alert_threshold,
        repeated_miss_threshold=repeated_miss_threshold,
    )
    reason_codes = [
        code
        for code, item in trigger_summary.items()
        if item.get("triggered")
    ]
    recommendation_state = (
        ModelRetrainingRecommendationState.RETRAINING_RECOMMENDED
        if reason_codes
        else ModelRetrainingRecommendationState.REVIEW_NOT_REQUIRED
    )
    recommended_action = (
        "review_and_prepare_phase_4_gated_retraining_candidate"
        if reason_codes
        else "continue_monitoring"
    )
    source_snapshot_refs = [
        ref
        for item in trigger_summary.values()
        for ref in item.get("source_refs", [])
    ]

    with transaction.atomic():
        recommendation = ModelRetrainingRecommendation.objects.create(
            registry_entry=registry_entry,
            model_run=registry_entry.model_run,
            recommendation_state=recommendation_state,
            recommended_action=recommended_action,
            reason_codes=reason_codes,
            trigger_summary=trigger_summary,
            source_snapshot_refs=sorted(set(source_snapshot_refs)),
            new_label_count=trigger_summary["new_surveillance_label_volume"]["observed_count"],
            false_alert_count=trigger_summary["repeated_false_alerts"]["observed_count"],
            miss_count=trigger_summary["repeated_misses"]["observed_count"],
            metadata={
                "schema_version": MODEL_RETRAINING_POLICY_SCHEMA_VERSION,
                "automatic_live_promotion_allowed": False,
                "phase_4_promotion_gates_required": True,
                "policy_thresholds": {
                    "stale_model_max_days": stale_model_max_days,
                    "new_label_volume_threshold": new_label_volume_threshold,
                    "repeated_false_alert_threshold": repeated_false_alert_threshold,
                    "repeated_miss_threshold": repeated_miss_threshold,
                },
            },
            generated_at=now,
        )
        if reason_codes:
            registry_entry.monitoring_state = ModelRegistryMonitoringState.REVIEW_REQUIRED
            registry_entry.metadata = {
                **(registry_entry.metadata or {}),
                "review_required": True,
                "review_required_reason_codes": reason_codes,
                "latest_retraining_recommendation_id": recommendation.id,
                "latest_retraining_recommendation_public_id": str(recommendation.public_id),
                "automatic_live_promotion_allowed": False,
                "phase_4_promotion_gates_required_for_retraining": True,
            }
            registry_entry.save(update_fields=["monitoring_state", "metadata", "updated_at"])
        return recommendation


def _trigger_summary(
    *,
    registry_entry: ModelRegistryEntry,
    active_from,
    now,
    stale_model_max_days: int,
    new_label_volume_threshold: int,
    repeated_false_alert_threshold: int,
    repeated_miss_threshold: int,
) -> dict:
    monitoring = _monitoring_breach_trigger(registry_entry)
    stale = _stale_model_trigger(
        registry_entry=registry_entry,
        active_from=active_from,
        now=now,
        stale_model_max_days=stale_model_max_days,
    )
    label_volume = _new_label_volume_trigger(
        active_from=active_from,
        threshold=new_label_volume_threshold,
    )
    schema_change = _data_source_schema_change_trigger(
        registry_entry=registry_entry,
        active_from=active_from,
    )
    population_change = _population_baseline_change_trigger(active_from=active_from)
    false_alerts = _false_alert_trigger(
        registry_entry=registry_entry,
        threshold=repeated_false_alert_threshold,
    )
    misses = _miss_trigger(
        registry_entry=registry_entry,
        active_from=active_from,
        threshold=repeated_miss_threshold,
    )
    return {
        "monitoring_threshold_breach": monitoring,
        "stale_model_age": stale,
        "new_surveillance_label_volume": label_volume,
        "data_source_schema_change": schema_change,
        "population_exposure_baseline_change": population_change,
        "repeated_false_alerts": false_alerts,
        "repeated_misses": misses,
    }


def _monitoring_breach_trigger(registry_entry: ModelRegistryEntry) -> dict:
    latest_run_id = (registry_entry.metadata or {}).get("latest_monitoring_run_id")
    queryset = ModelMonitoringSnapshot.objects.filter(registry_entry=registry_entry)
    if latest_run_id:
        queryset = queryset.filter(monitoring_run_id=latest_run_id)
    snapshots = list(queryset.order_by("-generated_at", "metric_name"))
    breached = [snapshot for snapshot in snapshots if snapshot.state == ModelMonitoringState.BREACHED]
    return {
        "triggered": bool(breached),
        "observed_count": len(breached),
        "threshold": 1,
        "breached_metrics": [snapshot.metric_name for snapshot in breached],
        "source_refs": [f"model_monitoring_snapshot:{snapshot.public_id}" for snapshot in breached],
    }


def _stale_model_trigger(*, registry_entry: ModelRegistryEntry, active_from, now, stale_model_max_days: int) -> dict:
    if active_from is None:
        return {
            "triggered": True,
            "observed_count": None,
            "threshold": stale_model_max_days,
            "reason": "active_from_missing",
            "source_refs": [f"model_registry_entry:{registry_entry.public_id}"],
        }
    age_days = max(0, (now - active_from).days)
    review_due = registry_entry.review_due_date
    review_due_triggered = review_due is not None and review_due <= timezone.localdate(now)
    return {
        "triggered": age_days >= stale_model_max_days or review_due_triggered,
        "observed_count": age_days,
        "threshold": stale_model_max_days,
        "review_due_date": review_due.isoformat() if review_due else None,
        "review_due_triggered": review_due_triggered,
        "source_refs": [f"model_registry_entry:{registry_entry.public_id}"],
    }


def _new_label_volume_trigger(*, active_from, threshold: int) -> dict:
    queryset = SurveillanceLabelWindow.objects.select_related("feature_dataset").all()
    if active_from is not None:
        queryset = queryset.filter(created_at__gte=active_from)
    count = sum(1 for label in queryset if label_window_is_currently_eligible(label))
    return {
        "triggered": count >= threshold,
        "observed_count": count,
        "threshold": threshold,
        "source_refs": [f"surveillance_label_window_count:{count}"],
    }


def _data_source_schema_change_trigger(*, registry_entry: ModelRegistryEntry, active_from) -> dict:
    model_run = registry_entry.model_run
    source_refs = []
    changed = []
    if (
        model_run.inference_feature_dataset_id
        and model_run.inference_feature_dataset.schema_version != model_run.feature_schema_version
    ):
        changed.append(
            {
                "dataset_ref": model_run.inference_feature_dataset.dataset_ref,
                "schema_version": model_run.inference_feature_dataset.schema_version,
                "expected_schema_version": model_run.feature_schema_version,
            }
        )
        source_refs.append(f"feature_dataset:{model_run.inference_feature_dataset.dataset_ref}")

    latest_query = FeatureDataset.objects.filter(dataset_kind=FeatureDataset.KIND_INFERENCE)
    if active_from is not None:
        latest_query = latest_query.filter(created_at__gte=active_from)
    latest_dataset = latest_query.order_by("-created_at", "-id").first()
    if latest_dataset is not None and latest_dataset.schema_version != model_run.feature_schema_version:
        changed.append(
            {
                "dataset_ref": latest_dataset.dataset_ref,
                "schema_version": latest_dataset.schema_version,
                "expected_schema_version": model_run.feature_schema_version,
            }
        )
        source_refs.append(f"feature_dataset:{latest_dataset.dataset_ref}")

    return {
        "triggered": bool(changed),
        "observed_count": len(changed),
        "threshold": 1,
        "schema_changes": changed,
        "source_refs": sorted(set(source_refs)),
    }


def _population_baseline_change_trigger(*, active_from) -> dict:
    queryset = PopulationBaselineRecord.objects.all()
    if active_from is not None:
        queryset = queryset.filter(created_at__gte=active_from)
    count = queryset.count()
    return {
        "triggered": count > 0,
        "observed_count": count,
        "threshold": 1,
        "source_refs": [f"population_baseline_record_count:{count}"],
    }


def _false_alert_trigger(*, registry_entry: ModelRegistryEntry, threshold: int) -> dict:
    false_alerts = []
    alerts = Alert.objects.filter(
        risk_score__model_run=registry_entry.model_run,
        status=Alert.STATUS_DELIVERED,
    ).select_related("ward", "risk_score")
    for alert in alerts:
        label = _label_for_risk_score(alert.risk_score)
        if label is None:
            continue
        if label.outbreak_label == SurveillanceOutbreakLabel.NONE:
            false_alerts.append(
                {
                    "alert_id": alert.id,
                    "risk_score_id": alert.risk_score_id,
                    "ward_id": alert.ward_id,
                    "label_window_id": label.id,
                }
            )
    return {
        "triggered": len(false_alerts) >= threshold,
        "observed_count": len(false_alerts),
        "threshold": threshold,
        "examples": false_alerts[:50],
        "source_refs": [f"alert:{item['alert_id']}" for item in false_alerts[:50]],
    }


def _miss_trigger(*, registry_entry: ModelRegistryEntry, active_from, threshold: int) -> dict:
    risk_scores_by_ward = {}
    for risk_score in RiskScore.objects.filter(model_run=registry_entry.model_run).order_by("-generated_at", "-id"):
        risk_scores_by_ward.setdefault(risk_score.ward_id, risk_score)
    labels = SurveillanceLabelWindow.objects.filter(
        outbreak_label=SurveillanceOutbreakLabel.ACTIVE,
    ).select_related("ward", "feature_dataset")
    if active_from is not None:
        labels = labels.filter(created_at__gte=active_from)
    misses = []
    for label in labels:
        if not label_window_is_currently_eligible(label):
            continue
        risk_score = risk_scores_by_ward.get(label.ward_id)
        delivered_alert_exists = (
            risk_score is not None
            and Alert.objects.filter(risk_score=risk_score, status=Alert.STATUS_DELIVERED).exists()
        )
        if risk_score is None or risk_score.risk_level != Ward.RISK_HIGH or not delivered_alert_exists:
            misses.append(
                {
                    "label_window_id": label.id,
                    "ward_id": label.ward_id,
                    "risk_score_id": risk_score.id if risk_score else None,
                    "risk_level": risk_score.risk_level if risk_score else None,
                    "delivered_alert_exists": delivered_alert_exists,
                }
            )
    return {
        "triggered": len(misses) >= threshold,
        "observed_count": len(misses),
        "threshold": threshold,
        "examples": misses[:50],
        "source_refs": [f"surveillance_label_window:{item['label_window_id']}" for item in misses[:50]],
    }


def _label_for_risk_score(risk_score: RiskScore | None) -> SurveillanceLabelWindow | None:
    if risk_score is None:
        return None
    start_date = (risk_score.generated_at + timedelta(days=7)).date()
    for label in SurveillanceLabelWindow.objects.select_related("feature_dataset").filter(
        ward=risk_score.ward,
        label_window_end__gte=start_date,
    ).order_by("label_window_start", "id"):
        if label_window_is_currently_eligible(label):
            return label
    return None
