from __future__ import annotations

from copy import deepcopy
from datetime import timedelta

from django.utils import timezone

from risk.models import (
    Alert,
    FacilityForecast,
    FacilityForecastRun,
    FacilityReadinessReview,
    SystemControlState,
    Ward,
)


WARD_RISK_DECISION_POLICY_SCHEMA_VERSION = "ward-risk-decision-policy-v1"
DEFAULT_WARD_RISK_DECISION_POLICY_VERSION = "ward-risk-policy-v1.0.0"

DECISION_ROUTINE_MONITORING = "routine_monitoring"
DECISION_WATCHLIST_ONLY = "watchlist_only"
DECISION_ALERT_CANDIDATE = "alert_candidate"
DECISION_URGENT_ALERT = "urgent_alert"

SOURCE_CONFIDENCE_HIGH = "high"
SOURCE_CONFIDENCE_MODERATE = "moderate"
SOURCE_CONFIDENCE_LOW = "low"


DEFAULT_WARD_RISK_DECISION_POLICY = {
    "schema_version": WARD_RISK_DECISION_POLICY_SCHEMA_VERSION,
    "policy_version": DEFAULT_WARD_RISK_DECISION_POLICY_VERSION,
    "policy_name": "Initial cholera early-warning ward decision policy",
    "thresholds": {
        "risk_level": {
            "medium_min_probability": 0.45,
            "high_min_probability": 0.75,
            "medium_min_expected_cases": 5,
            "high_min_expected_cases": 10,
        },
        "alerting": {
            "watchlist_only_min_probability": 0.35,
            "alert_candidate_min_probability": 0.60,
            "urgent_alert_min_probability": 0.85,
            "watchlist_min_expected_cases": 3,
            "alert_candidate_min_expected_cases": 8,
            "urgent_alert_min_expected_cases": 15,
            "alert_candidate_population_exposed_min": 10000,
            "urgent_population_exposed_min": 25000,
            "facility_pressure_alert_min": 2,
            "facility_pressure_urgent_min": 3,
        },
        "confidence": {
            "block_automatic_alert_freshness_states": ["STALE", "UNKNOWN"],
            "block_automatic_alert_confidence_states": [SOURCE_CONFIDENCE_LOW],
            "fatigue_window_days": 7,
            "fatigue_alert_count": 4,
        },
    },
    "calibration_state": {
        "status": "initial_policy_pending_false_alert_and_miss_review",
        "requires_outcome_review_before_threshold_promotion": True,
    },
}


def _deep_merge(base: dict, updates: dict) -> dict:
    merged = deepcopy(base)
    for key, value in (updates or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _policy_for_storage(policy: dict) -> dict:
    cleaned = deepcopy(policy)
    cleaned.pop("active_control", None)
    cleaned.pop("audit_history", None)
    return cleaned


def validate_ward_risk_decision_policy(policy: dict) -> None:
    thresholds = policy.get("thresholds") or {}
    risk = thresholds.get("risk_level") or {}
    alerting = thresholds.get("alerting") or {}

    medium_probability = float(risk["medium_min_probability"])
    high_probability = float(risk["high_min_probability"])
    watch_probability = float(alerting["watchlist_only_min_probability"])
    alert_probability = float(alerting["alert_candidate_min_probability"])
    urgent_probability = float(alerting["urgent_alert_min_probability"])
    if not (0.0 <= medium_probability <= high_probability <= 1.0):
        raise ValueError("Risk probability thresholds must satisfy 0 <= medium <= high <= 1.")
    if not (0.0 <= watch_probability <= alert_probability <= urgent_probability <= 1.0):
        raise ValueError("Alert probability thresholds must satisfy 0 <= watchlist <= candidate <= urgent <= 1.")

    medium_cases = int(risk["medium_min_expected_cases"])
    high_cases = int(risk["high_min_expected_cases"])
    watch_cases = int(alerting["watchlist_min_expected_cases"])
    alert_cases = int(alerting["alert_candidate_min_expected_cases"])
    urgent_cases = int(alerting["urgent_alert_min_expected_cases"])
    if not (0 <= medium_cases <= high_cases):
        raise ValueError("Risk expected-case thresholds must satisfy medium <= high.")
    if not (0 <= watch_cases <= alert_cases <= urgent_cases):
        raise ValueError("Alert expected-case thresholds must satisfy watchlist <= candidate <= urgent.")


def current_ward_risk_decision_policy() -> dict:
    control = (
        SystemControlState.objects.filter(control_key=SystemControlState.KEY_WARD_RISK_DECISION_POLICY)
        .select_related("updated_by")
        .first()
    )
    policy = deepcopy(DEFAULT_WARD_RISK_DECISION_POLICY)
    active_control = None
    audit_history = []
    if control is not None:
        audit_history = (control.metadata or {}).get("change_history", [])
        if control.is_currently_active():
            policy = _deep_merge(policy, (control.metadata or {}).get("policy", {}))
            active_control = {
                "control_id": control.id,
                "reason": control.reason,
                "updated_at": control.updated_at.isoformat() if control.updated_at else None,
                "updated_by": control.updated_by.username if control.updated_by_id else None,
            }

    validate_ward_risk_decision_policy(policy)
    policy["active_control"] = active_control
    policy["audit_history"] = audit_history[-25:]
    return policy


def set_ward_risk_decision_policy(
    *,
    policy_updates: dict,
    actor=None,
    reason: str = "",
) -> dict:
    changed_at = timezone.now()
    existing_control = SystemControlState.objects.filter(
        control_key=SystemControlState.KEY_WARD_RISK_DECISION_POLICY,
    ).first()
    old_policy = current_ward_risk_decision_policy()
    new_policy = _deep_merge(_policy_for_storage(old_policy), policy_updates)
    validate_ward_risk_decision_policy(new_policy)
    old_storage_policy = _policy_for_storage(old_policy)
    history = []
    if existing_control is not None:
        history = list((existing_control.metadata or {}).get("change_history", []))
    audit_event = {
        "changed_at": changed_at.isoformat(),
        "changed_by_user_id": getattr(actor, "id", None) if getattr(actor, "is_authenticated", False) else None,
        "changed_by_username": getattr(actor, "username", None) if getattr(actor, "is_authenticated", False) else None,
        "reason": reason.strip(),
        "old_policy_version": old_storage_policy.get("policy_version"),
        "new_policy_version": new_policy.get("policy_version"),
        "old_thresholds": old_storage_policy.get("thresholds", {}),
        "new_thresholds": new_policy.get("thresholds", {}),
    }
    history.append(audit_event)

    control, _ = SystemControlState.objects.update_or_create(
        control_key=SystemControlState.KEY_WARD_RISK_DECISION_POLICY,
        defaults={
            "is_active": True,
            "reason": reason.strip(),
            "active_until": None,
            "metadata": {
                "policy": new_policy,
                "change_history": history[-50:],
            },
            "updated_by": actor if getattr(actor, "is_authenticated", False) else None,
        },
    )
    return {
        "policy": current_ward_risk_decision_policy(),
        "audit_event": audit_event,
        "control_id": control.id,
    }


def _safe_float(value, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _population_exposed_from_prediction(prediction: dict) -> float:
    candidates = [
        prediction.get("exposed_population_proxy"),
        prediction.get("catchment_population_estimate"),
        prediction.get("population_total"),
        prediction.get("population_proxy"),
    ]
    return max(_safe_float(value) for value in candidates)


def _normalise_freshness_state(value: str | None) -> str:
    normalized = str(value or "").upper()
    if normalized == "FRESH":
        return "FRESH"
    if normalized in {"DELAYED", "WARNING"}:
        return "WARNING"
    if normalized == "STALE":
        return "STALE"
    return "UNKNOWN"


def _source_freshness_from_prediction(prediction: dict) -> dict:
    rainfall_lineage = prediction.get("rainfall_source_lineage") or {}
    states = [
        _normalise_freshness_state(rainfall_lineage.get("freshness_state")),
        _normalise_freshness_state(prediction.get("surveillance_latest_freshness_state")),
    ]
    if "STALE" in states:
        combined = "STALE"
    elif "UNKNOWN" in states:
        combined = "UNKNOWN"
    elif "WARNING" in states:
        combined = "WARNING"
    else:
        combined = "FRESH"
    return {
        "combined_state": combined,
        "component_states": {
            "rainfall": states[0],
            "surveillance": states[1],
        },
    }


def _source_confidence_from_prediction(prediction: dict, source_freshness: dict) -> dict:
    rainfall_lineage = prediction.get("rainfall_source_lineage") or {}
    weak_reasons = []
    moderate_reasons = []
    if rainfall_lineage.get("source_kind") in {"SEEDED", "UNKNOWN"} or rainfall_lineage.get("fallback_reason"):
        weak_reasons.append("rainfall_source_not_live_or_fallback_used")
    if prediction.get("population_exposure_feature_mode") != "source_fed_population_exposure_context":
        moderate_reasons.append("population_exposure_context_not_source_fed")
    truth_state = prediction.get("surveillance_label_truth_state") or "no_surveillance_label_window"
    if "proxy_only" in truth_state or "seeded" in truth_state:
        weak_reasons.append("surveillance_truth_is_proxy_or_seeded")
    elif truth_state in {"no_surveillance_label_window", "field_signal_only_not_confirmed"}:
        moderate_reasons.append("surveillance_truth_not_confirmed")
    if source_freshness["combined_state"] in {"STALE", "UNKNOWN"}:
        weak_reasons.append("source_freshness_not_current")
    elif source_freshness["combined_state"] == "WARNING":
        moderate_reasons.append("source_freshness_delayed_or_warning")

    if weak_reasons:
        confidence = SOURCE_CONFIDENCE_LOW
    elif moderate_reasons:
        confidence = SOURCE_CONFIDENCE_MODERATE
    else:
        confidence = SOURCE_CONFIDENCE_HIGH
    return {
        "confidence": confidence,
        "weak_reasons": weak_reasons,
        "moderate_reasons": moderate_reasons,
    }


def _facility_readiness_pressure_for_ward(ward: Ward) -> dict:
    active_review_count = FacilityReadinessReview.objects.filter(
        ward=ward,
        status__in=FacilityReadinessReview.ACTIVE_STATUSES,
    ).count()
    latest_by_facility = {}
    forecasts = (
        FacilityForecast.objects.filter(
            facility__ward=ward,
            forecast_run__status=FacilityForecastRun.STATUS_SUCCESS,
        )
        .select_related("facility", "forecast_run")
        .order_by("facility_id", "-generated_at", "-id")
    )
    for forecast in forecasts:
        latest_by_facility.setdefault(forecast.facility_id, forecast)

    capacity_concern_count = sum(
        1
        for forecast in latest_by_facility.values()
        if forecast.projected_readiness_state == FacilityForecast.READINESS_CAPACITY_CONCERN
    )
    watch_count = sum(
        1
        for forecast in latest_by_facility.values()
        if forecast.projected_readiness_state == FacilityForecast.READINESS_WATCH
    )
    if capacity_concern_count or active_review_count >= 3:
        pressure_score = 3
    elif watch_count or active_review_count:
        pressure_score = 2
    elif latest_by_facility:
        pressure_score = 1
    else:
        pressure_score = 0
    return {
        "score": pressure_score,
        "active_readiness_review_count": active_review_count,
        "capacity_concern_forecast_count": capacity_concern_count,
        "watch_forecast_count": watch_count,
        "latest_forecast_count": len(latest_by_facility),
    }


def _recent_alert_fatigue_for_ward(ward: Ward, *, policy: dict, now) -> dict:
    confidence_thresholds = policy["thresholds"]["confidence"]
    window_days = int(confidence_thresholds["fatigue_window_days"])
    fatigue_count = int(confidence_thresholds["fatigue_alert_count"])
    since = now - timedelta(days=window_days)
    alert_count = Alert.objects.filter(ward=ward, created_at__gte=since).count()
    return {
        "window_days": window_days,
        "alert_count": alert_count,
        "fatigue_threshold_count": fatigue_count,
        "fatigued": alert_count >= fatigue_count,
    }


def _risk_level_from_thresholds(
    *,
    model_score: float,
    expected_case_burden: int,
    facility_pressure_score: int,
    policy: dict,
    reason_codes: list[str],
) -> str:
    risk_thresholds = policy["thresholds"]["risk_level"]
    alert_thresholds = policy["thresholds"]["alerting"]
    if (
        model_score >= float(risk_thresholds["high_min_probability"])
        or expected_case_burden >= int(risk_thresholds["high_min_expected_cases"])
        or facility_pressure_score >= int(alert_thresholds["facility_pressure_urgent_min"])
    ):
        reason_codes.append("risk_high_threshold_met")
        return Ward.RISK_HIGH
    if (
        model_score >= float(risk_thresholds["medium_min_probability"])
        or expected_case_burden >= int(risk_thresholds["medium_min_expected_cases"])
        or facility_pressure_score >= int(alert_thresholds["facility_pressure_alert_min"])
    ):
        reason_codes.append("risk_medium_threshold_met")
        return Ward.RISK_MEDIUM
    reason_codes.append("risk_low_threshold_met")
    return Ward.RISK_LOW


def evaluate_ward_risk_decision_policy(
    *,
    ward: Ward,
    prediction: dict,
    model_score: float,
    expected_case_burden: int,
    policy: dict | None = None,
    now=None,
) -> dict:
    now = now or timezone.now()
    policy = deepcopy(policy or current_ward_risk_decision_policy())
    validate_ward_risk_decision_policy(policy)
    reason_codes: list[str] = []
    model_score = round(max(0.0, min(1.0, float(model_score))), 6)
    expected_case_burden = int(expected_case_burden)
    population_exposed = _population_exposed_from_prediction(prediction)
    facility_pressure = _facility_readiness_pressure_for_ward(ward)
    source_freshness = _source_freshness_from_prediction(prediction)
    source_confidence = _source_confidence_from_prediction(prediction, source_freshness)
    fatigue = _recent_alert_fatigue_for_ward(ward, policy=policy, now=now)
    alert_thresholds = policy["thresholds"]["alerting"]
    confidence_thresholds = policy["thresholds"]["confidence"]

    risk_level = _risk_level_from_thresholds(
        model_score=model_score,
        expected_case_burden=expected_case_burden,
        facility_pressure_score=facility_pressure["score"],
        policy=policy,
        reason_codes=reason_codes,
    )

    urgent = (
        model_score >= float(alert_thresholds["urgent_alert_min_probability"])
        or expected_case_burden >= int(alert_thresholds["urgent_alert_min_expected_cases"])
        or population_exposed >= float(alert_thresholds["urgent_population_exposed_min"])
        or facility_pressure["score"] >= int(alert_thresholds["facility_pressure_urgent_min"])
    )
    candidate = (
        urgent
        or model_score >= float(alert_thresholds["alert_candidate_min_probability"])
        or expected_case_burden >= int(alert_thresholds["alert_candidate_min_expected_cases"])
        or (
            population_exposed >= float(alert_thresholds["alert_candidate_population_exposed_min"])
            and risk_level in {Ward.RISK_MEDIUM, Ward.RISK_HIGH}
        )
        or facility_pressure["score"] >= int(alert_thresholds["facility_pressure_alert_min"])
    )
    watchlist = (
        candidate
        or model_score >= float(alert_thresholds["watchlist_only_min_probability"])
        or expected_case_burden >= int(alert_thresholds["watchlist_min_expected_cases"])
        or risk_level == Ward.RISK_MEDIUM
    )

    if urgent:
        alert_decision = DECISION_URGENT_ALERT
        reason_codes.append("urgent_alert_threshold_met")
    elif candidate:
        alert_decision = DECISION_ALERT_CANDIDATE
        reason_codes.append("alert_candidate_threshold_met")
    elif watchlist:
        alert_decision = DECISION_WATCHLIST_ONLY
        reason_codes.append("watchlist_threshold_met")
    else:
        alert_decision = DECISION_ROUTINE_MONITORING
        reason_codes.append("routine_monitoring_threshold_met")

    blocked_reasons = []
    if source_freshness["combined_state"] in confidence_thresholds["block_automatic_alert_freshness_states"]:
        blocked_reasons.append("source_freshness_blocks_automatic_alert")
    if source_confidence["confidence"] in confidence_thresholds["block_automatic_alert_confidence_states"]:
        blocked_reasons.append("source_confidence_blocks_automatic_alert")
    if fatigue["fatigued"] and alert_decision != DECISION_URGENT_ALERT:
        blocked_reasons.append("recent_alert_fatigue_blocks_automatic_alert")
    automatic_alert_allowed = alert_decision in {DECISION_ALERT_CANDIDATE, DECISION_URGENT_ALERT} and not blocked_reasons

    return {
        "schema_version": WARD_RISK_DECISION_POLICY_SCHEMA_VERSION,
        "policy_version": policy["policy_version"],
        "policy_name": policy.get("policy_name", ""),
        "evaluated_at": now.isoformat(),
        "risk_level": risk_level,
        "alert_decision": alert_decision,
        "alert_candidate": alert_decision in {DECISION_ALERT_CANDIDATE, DECISION_URGENT_ALERT},
        "urgent_alert": alert_decision == DECISION_URGENT_ALERT,
        "watchlist_only": alert_decision == DECISION_WATCHLIST_ONLY,
        "automatic_alert_allowed": automatic_alert_allowed,
        "automatic_alert_blockers": blocked_reasons,
        "reason_codes": list(dict.fromkeys(reason_codes)),
        "inputs": {
            "model_score": model_score,
            "expected_case_burden": expected_case_burden,
            "population_exposed": population_exposed,
            "facility_readiness_pressure": facility_pressure,
            "source_freshness": source_freshness,
            "source_confidence": source_confidence,
            "recent_alert_fatigue": fatigue,
        },
        "thresholds": policy["thresholds"],
        "trace": {
            "model_score": model_score,
            "expected_case_burden": expected_case_burden,
            "policy_version": policy["policy_version"],
            "threshold_schema_version": policy["schema_version"],
            "risk_score_to_policy_link": "RiskScore.decision_policy",
        },
    }
