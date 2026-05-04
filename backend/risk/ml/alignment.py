from __future__ import annotations

from typing import Iterable

from django.core.exceptions import ObjectDoesNotExist

from risk.models import ModelRegistryEntry, ModelRegistryPromotionState, ModelRun, RiskScore

from .model import (
    ALGORITHM_LIGHTGBM,
    ALGORITHM_LOGISTIC_REGRESSION,
    ALGORITHM_RANDOM_FOREST,
    ALGORITHM_XGBOOST,
    MODEL_CATALOG,
)


PROMOTION_TARGET_LIVE_BASELINE = "live_baseline"
PROMOTION_TARGET_BENCHMARK_ONLY = "benchmark_only"
PROMOTION_TARGET_DEMO_ONLY = "demo_only"


def algorithm_key_from_run(run: ModelRun | None) -> str | None:
    if run is None:
        return None
    metadata = run.metadata or {}
    return metadata.get("algorithm") or {
        "logistic-regression-baseline": ALGORITHM_LOGISTIC_REGRESSION,
        "random-forest-benchmark": ALGORITHM_RANDOM_FOREST,
        "xgboost-candidate": ALGORITHM_XGBOOST,
        "lightgbm-candidate": ALGORITHM_LIGHTGBM,
    }.get(run.algorithm_name)


def model_run_has_phase_4_promotion_metadata(run: ModelRun | None) -> bool:
    if run is None or run.status != ModelRun.STATUS_SUCCESS:
        return False
    metadata = run.metadata or {}
    return (
        metadata.get("promotion_target") == PROMOTION_TARGET_LIVE_BASELINE
        and metadata.get("promotion_state") == "promoted"
        and metadata.get("phase_4_promotion_gates_passed") is True
        and metadata.get("alert_eligible") is True
    )


def registry_entry_has_promotion_event_provenance(entry: ModelRegistryEntry | None) -> bool:
    if entry is None or not entry.promotion_event_id:
        return False
    promotion_event = entry.promotion_event
    return (
        promotion_event.registry_entry_id == entry.id
        and promotion_event.model_run_id == entry.model_run_id
    )


def is_promoted_model_run(run: ModelRun | None) -> bool:
    if not model_run_has_phase_4_promotion_metadata(run):
        return False
    try:
        registry_entry = run.registry_entry
    except ObjectDoesNotExist:
        registry_exists = ModelRegistryEntry.objects.exists()
        if not registry_exists:
            return True
        return False
    return (
        registry_entry.promotion_state == ModelRegistryPromotionState.ACTIVE_PROMOTED
        and registry_entry.active_from is not None
        and registry_entry.active_until is None
        and registry_entry_has_promotion_event_provenance(registry_entry)
    )


def promoted_risk_scores(risk_scores: Iterable[RiskScore]) -> list[RiskScore]:
    promoted = [risk_score for risk_score in risk_scores if is_promoted_model_run(risk_score.model_run)]
    return sorted(promoted, key=lambda risk_score: risk_score.generated_at, reverse=True)


def latest_promoted_riskscore_for_ward(ward) -> RiskScore | None:
    prefetched = getattr(ward, "_prefetched_objects_cache", {})
    if "risk_scores" in prefetched:
        return next(iter(promoted_risk_scores(prefetched["risk_scores"])), None)

    queryset = ward.risk_scores.select_related("model_run").order_by("-generated_at")
    for risk_score in queryset:
        if is_promoted_model_run(risk_score.model_run):
            return risk_score
    return None


def _latest_successful_run_for_target(promotion_target: str) -> ModelRun | None:
    if promotion_target == PROMOTION_TARGET_LIVE_BASELINE:
        from .registry import active_model_registry_entry

        active_entry = active_model_registry_entry()
        if active_entry is not None:
            return active_entry.model_run

    queryset = ModelRun.objects.filter(status=ModelRun.STATUS_SUCCESS).order_by("-started_at")
    for run in queryset:
        if promotion_target == PROMOTION_TARGET_LIVE_BASELINE:
            if is_promoted_model_run(run):
                return run
            continue
        if (run.metadata or {}).get("promotion_target") == promotion_target:
            return run
    return None


def get_live_model_alignment_summary() -> dict:
    live_run = _latest_successful_run_for_target(PROMOTION_TARGET_LIVE_BASELINE)
    benchmark_run = _latest_successful_run_for_target(PROMOTION_TARGET_BENCHMARK_ONLY)
    candidate_models = [
        algorithm
        for algorithm in [ALGORITHM_XGBOOST, ALGORITHM_LIGHTGBM]
        if MODEL_CATALOG[algorithm]["readiness_state"] == "candidate_only"
    ]

    return {
        "current_live_baseline": {
            "algorithm": algorithm_key_from_run(live_run),
            "algorithm_name": live_run.algorithm_name if live_run else None,
            "model_version": live_run.model_version if live_run else None,
            "promotion_target": (live_run.metadata or {}).get("promotion_target") if live_run else None,
        },
        "current_benchmark_model": {
            "algorithm": algorithm_key_from_run(benchmark_run),
            "algorithm_name": benchmark_run.algorithm_name if benchmark_run else None,
            "model_version": benchmark_run.model_version if benchmark_run else None,
            "promotion_target": (benchmark_run.metadata or {}).get("promotion_target") if benchmark_run else None,
        },
        "future_candidate_models": candidate_models,
        "dashboard_policy": {
            "surface_only_promoted_outputs": True,
            "model_family_agnostic_default": True,
            "benchmark_outputs_hidden_from_operational_truth": True,
            "candidate_models_hidden_from_operational_truth": True,
        },
    }
