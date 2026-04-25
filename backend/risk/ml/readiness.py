from __future__ import annotations

from risk.ml.model import ALGORITHM_LIGHTGBM, ALGORITHM_XGBOOST, FEATURE_KEYS, MODEL_CATALOG


def build_boosting_readiness_summary() -> dict:
    candidate_algorithms = [ALGORITHM_XGBOOST, ALGORITHM_LIGHTGBM]
    candidates = {
        algorithm: {
            "run_name": MODEL_CATALOG[algorithm]["run_name"],
            "readiness_state": MODEL_CATALOG[algorithm]["readiness_state"],
            "runnable": MODEL_CATALOG[algorithm]["runnable"],
            "family": MODEL_CATALOG[algorithm]["family"],
        }
        for algorithm in candidate_algorithms
    }

    return {
        "phase": "xgboost_lightgbm_readiness",
        "live_state": {
            "current_live_baseline": "logistic_regression",
            "current_benchmark_model": "random_forest",
            "candidate_models": candidate_algorithms,
            "promotion_state": "candidate_only_not_live",
        },
        "boosting_feature_discipline": {
            "required_feature_schema_versioning": True,
            "required_feature_keys": FEATURE_KEYS,
            "categorical_expansion_policy": "keep_explicit_and_auditable",
            "missing_value_policy": "must_be_defined_before_training",
            "training_inference_parity_required": True,
        },
        "resource_and_training_expectations": {
            "training_execution": "manual_or_explicit_benchmark_only",
            "scheduled_live_training_allowed": False,
            "memory_expectation": "higher_than_logistic_and_random_forest_baseline",
            "hyperparameter_search_required": True,
            "time_aware_evaluation_required": True,
        },
        "promotion_gates_stricter_than_random_forest": {
            "lead_time_evidence_required": True,
            "temporal_robustness_required": True,
            "calibration_review_required": True,
            "feature_importance_or_explanation_strategy_required": True,
            "dashboard_language_review_required": True,
            "manual_promotion_decision_required": True,
        },
        "explainability_and_monitoring_requirements": {
            "feature_attribution_strategy": "required_before_promotion",
            "prediction_drift_monitoring": "required_before_promotion",
            "calibration_monitoring": "required_before_promotion",
            "benchmark_shadow_run_period": "required_before_promotion",
        },
        "candidate_models": candidates,
        "decision": {
            "recommended_action": "prepare_interfaces_only",
            "do_not_enable_in_run_risk_model": True,
            "do_not_schedule_as_live_default": True,
            "do_not_surface_on_dashboard_as_live_model": True,
        },
    }
