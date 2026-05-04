from __future__ import annotations

from collections import Counter
from typing import Iterable


CLIMATE_COVERAGE_POLICY_SCHEMA_VERSION = "climate-coverage-policy-v1"
CLIMATE_ALERT_EVIDENCE_SCHEMA_VERSION = "climate-alert-evidence-v1"
DEFAULT_CLAIMED_FORECAST_HORIZON_DAYS = 14


def _safe_int(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_present(*values):
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _bool_from_any(*values) -> bool:
    for value in values:
        if isinstance(value, bool):
            return value
        if value not in (None, "", [], {}):
            return bool(value)
    return False


def _as_int_list(value) -> list[int]:
    if not isinstance(value, (list, tuple, set)):
        return []
    days = []
    for item in value:
        day = _safe_int(item)
        if day is not None:
            days.append(day)
    return sorted(dict.fromkeys(days))


def _as_string_list(value) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(item) for item in value if item not in (None, "")]


def _first_list_item(value):
    if isinstance(value, (list, tuple)) and value:
        return value[0]
    return None


def _iso_date_from_prediction_and_lead_day(prediction: dict, lead_day: int | None):
    if lead_day is None:
        return None
    prediction_date = prediction.get("prediction_date")
    if not prediction_date:
        return None
    try:
        from datetime import date, timedelta

        parsed_prediction_date = date.fromisoformat(str(prediction_date)[:10])
    except ValueError:
        return None
    return (parsed_prediction_date + timedelta(days=max(lead_day - 1, 0))).isoformat()


def climate_source_label_for_record_type(record_type: str | None) -> str:
    if record_type == "observed":
        return "Observed rainfall"
    if record_type == "forecast":
        return "Forecast rainfall"
    if record_type == "fallback_static":
        return "Fallback static rainfall"
    if record_type in {"derived_rolling_window", "derived_anomaly"}:
        return "Derived climate feature"
    return "Climate source unavailable"


def climate_coverage_from_prediction(prediction: dict | None) -> dict:
    prediction = prediction or {}
    source_lineage = prediction.get("source_lineage") if isinstance(prediction.get("source_lineage"), dict) else {}
    rainfall_lineage = prediction.get("rainfall_source_lineage")
    if not isinstance(rainfall_lineage, dict):
        rainfall_lineage = source_lineage.get("rainfall") if isinstance(source_lineage.get("rainfall"), dict) else {}
    forecast_lineage = source_lineage.get("forecast_rainfall")
    if not isinstance(forecast_lineage, dict):
        forecast_lineage = {}
    fallback_lineage = source_lineage.get("fallback_static_rainfall")
    if not isinstance(fallback_lineage, dict):
        fallback_lineage = {}

    raw_coverage = prediction.get("climate_coverage_summary")
    if not isinstance(raw_coverage, dict):
        raw_coverage = prediction.get("climate_coverage")
    if not isinstance(raw_coverage, dict):
        raw_coverage = source_lineage.get("climate_coverage")
    if not isinstance(raw_coverage, dict):
        raw_coverage = rainfall_lineage.get("climate_coverage")
    if not isinstance(raw_coverage, dict):
        raw_coverage = {}

    record_type = _first_present(
        prediction.get("record_type"),
        rainfall_lineage.get("record_type"),
        rainfall_lineage.get("climate_record_type"),
        raw_coverage.get("record_type"),
    )
    if not record_type and (forecast_lineage.get("selected_record_count") or forecast_lineage.get("record_count")):
        record_type = "forecast"
    if not record_type and (fallback_lineage.get("record_count") or fallback_lineage.get("latest_source_ref")):
        record_type = "fallback_static"
    claimed_horizon = _safe_int(
        _first_present(
            prediction.get("claimed_forecast_horizon_days"),
            raw_coverage.get("claimed_forecast_horizon_days"),
            rainfall_lineage.get("claimed_forecast_horizon_days"),
        )
    ) or DEFAULT_CLAIMED_FORECAST_HORIZON_DAYS
    covered_lead_days = _as_int_list(
        _first_present(
            prediction.get("forecast_covered_lead_days"),
            raw_coverage.get("forecast_covered_lead_days"),
            raw_coverage.get("covered_lead_days"),
            rainfall_lineage.get("forecast_covered_lead_days"),
            forecast_lineage.get("covered_lead_days"),
        )
    )
    forecast_coverage_days = _safe_int(
        _first_present(
            prediction.get("forecast_coverage_days"),
            raw_coverage.get("forecast_coverage_days"),
            raw_coverage.get("coverage_days"),
            rainfall_lineage.get("forecast_coverage_days"),
            forecast_lineage.get("coverage_days"),
        )
    )
    lead_day = _safe_int(
        _first_present(
            prediction.get("lead_day"),
            raw_coverage.get("lead_day"),
            rainfall_lineage.get("lead_day"),
            forecast_lineage.get("max_contract_lead_day"),
        )
    )
    forecast_horizon_days = _safe_int(
        _first_present(
            prediction.get("forecast_horizon_days"),
            raw_coverage.get("forecast_horizon_days"),
            rainfall_lineage.get("forecast_horizon_days"),
            forecast_lineage.get("max_forecast_horizon_days"),
        )
    )
    if forecast_coverage_days is None:
        forecast_coverage_days = len(covered_lead_days) or forecast_horizon_days or lead_day or 0
    if not covered_lead_days and forecast_coverage_days:
        covered_lead_days = list(range(1, min(forecast_coverage_days, claimed_horizon) + 1))

    missing_lead_days = _as_int_list(
        _first_present(
            prediction.get("forecast_missing_lead_days"),
            raw_coverage.get("forecast_missing_lead_days"),
            raw_coverage.get("missing_lead_days"),
            rainfall_lineage.get("forecast_missing_lead_days"),
            forecast_lineage.get("missing_lead_days"),
        )
    )
    explicit_sufficient = _first_present(
        prediction.get("claimed_lead_time_climate_coverage_sufficient"),
        raw_coverage.get("claimed_lead_time_climate_coverage_sufficient"),
        raw_coverage.get("ready_for_claimed_forecast_horizon"),
        rainfall_lineage.get("claimed_lead_time_climate_coverage_sufficient"),
    )
    fallback_used = _bool_from_any(
        prediction.get("fallback_static_rainfall_used"),
        raw_coverage.get("fallback_static_rainfall_used"),
        rainfall_lineage.get("fallback_static_rainfall_used"),
        rainfall_lineage.get("fallback_flag"),
        (fallback_lineage.get("record_count") or 0) > 0,
        record_type == "fallback_static",
    )
    evidence_available = _bool_from_any(
        raw_coverage,
        prediction.get("climate_coverage_status"),
        prediction.get("forecast_coverage_days"),
        rainfall_lineage.get("record_type"),
        rainfall_lineage.get("forecast_horizon_days"),
        rainfall_lineage.get("fallback_flag"),
        forecast_lineage,
        fallback_lineage,
    )

    if not missing_lead_days and explicit_sufficient is not True and evidence_available:
        missing_lead_days = [day for day in range(1, claimed_horizon + 1) if day not in set(covered_lead_days)]
    if isinstance(explicit_sufficient, bool):
        sufficient = explicit_sufficient
    elif not evidence_available:
        sufficient = False
    else:
        sufficient = bool(not missing_lead_days and forecast_coverage_days >= claimed_horizon and not fallback_used)

    caveats = [
        *_as_string_list(prediction.get("climate_coverage_caveats")),
        *_as_string_list(raw_coverage.get("climate_coverage_caveats") or raw_coverage.get("caveats")),
    ]
    if not evidence_available:
        caveats.append("climate_coverage_evidence_missing")
    if evidence_available and not sufficient:
        caveats.append("forecast_missing_claimed_lead_days")
    if fallback_used:
        caveats.append("fallback_static_rainfall_present_not_live_forecast")
    caveats = list(dict.fromkeys(caveats))

    confidence_score = _safe_float(
        _first_present(
            prediction.get("climate_source_confidence"),
            raw_coverage.get("climate_source_confidence"),
            rainfall_lineage.get("climate_source_confidence"),
        )
    )
    if confidence_score is None:
        if fallback_used:
            confidence_score = 0.2
        elif sufficient:
            confidence_score = 1.0
        elif evidence_available:
            confidence_score = 0.55
        else:
            confidence_score = 0.0
    if fallback_used:
        confidence_score = min(confidence_score, 0.4)

    status = _first_present(
        prediction.get("climate_coverage_status"),
        raw_coverage.get("climate_coverage_status"),
        raw_coverage.get("status"),
    )
    if not status:
        status = "sufficient" if sufficient else "insufficient_forecast_horizon" if evidence_available else "unavailable"

    source_label = _first_present(
        raw_coverage.get("observed_vs_forecast_source_label"),
        rainfall_lineage.get("observed_vs_forecast_source_label"),
        climate_source_label_for_record_type(record_type),
    )
    return {
        "schema_version": CLIMATE_COVERAGE_POLICY_SCHEMA_VERSION,
        "evidence_available": evidence_available,
        "record_type": record_type or "unavailable",
        "source_provider": _first_present(
            prediction.get("source_provider"),
            raw_coverage.get("source_provider"),
            rainfall_lineage.get("source_provider"),
            rainfall_lineage.get("source"),
            _first_list_item(forecast_lineage.get("source_providers")),
            _first_list_item(fallback_lineage.get("source_providers")),
        )
        or "",
        "observed_vs_forecast_source_label": source_label,
        "claimed_forecast_horizon_days": claimed_horizon,
        "forecast_coverage_days": forecast_coverage_days,
        "forecast_covered_lead_days": covered_lead_days,
        "forecast_missing_lead_days": missing_lead_days,
        "forecast_horizon_7d_sufficient": bool(
            _first_present(prediction.get("forecast_horizon_7d_sufficient"), raw_coverage.get("forecast_horizon_7d_sufficient"))
            or all(day in set(covered_lead_days) for day in range(1, 8))
        ),
        "forecast_horizon_14d_sufficient": bool(
            _first_present(
                prediction.get("forecast_horizon_14d_sufficient"),
                raw_coverage.get("forecast_horizon_14d_sufficient"),
            )
            or all(day in set(covered_lead_days) for day in range(1, 15))
        ),
        "claimed_lead_time_climate_coverage_sufficient": sufficient,
        "fallback_static_rainfall_used": fallback_used,
        "fallback_static_rainfall_mm": _safe_float(
            _first_present(prediction.get("fallback_static_rainfall_mm"), raw_coverage.get("fallback_static_rainfall_mm"))
        ),
        "climate_coverage_status": status,
        "climate_coverage_caveats": caveats,
        "climate_source_confidence": round(confidence_score, 2),
        "climate_source_confidence_label": _first_present(
            prediction.get("climate_source_confidence_label"),
            raw_coverage.get("climate_source_confidence_label"),
        )
        or ("high" if confidence_score >= 0.85 else "moderate" if confidence_score >= 0.6 else "low"),
        "issue_time": _first_present(
            prediction.get("issue_time"),
            raw_coverage.get("issue_time"),
            rainfall_lineage.get("issue_time"),
            forecast_lineage.get("selected_issue_time"),
        ),
        "valid_date": _first_present(
            prediction.get("valid_date"),
            raw_coverage.get("valid_date"),
            rainfall_lineage.get("valid_date"),
            _iso_date_from_prediction_and_lead_day(prediction, max(covered_lead_days, default=0) or lead_day),
        ),
        "lead_day": lead_day,
        "forecast_horizon_days": forecast_horizon_days,
        "observed_timestamp": _first_present(
            prediction.get("observed_timestamp"),
            rainfall_lineage.get("observed_timestamp"),
        ),
    }


def climate_alert_evidence_from_prediction(prediction: dict | None) -> dict:
    coverage = climate_coverage_from_prediction(prediction)
    return {
        "schema_version": CLIMATE_ALERT_EVIDENCE_SCHEMA_VERSION,
        "record_type": coverage["record_type"],
        "source_provider": coverage["source_provider"],
        "observed_vs_forecast_source_label": coverage["observed_vs_forecast_source_label"],
        "issue_time": coverage["issue_time"],
        "valid_date": coverage["valid_date"],
        "lead_day": coverage["lead_day"],
        "forecast_horizon_days": coverage["forecast_horizon_days"],
        "claimed_forecast_horizon_days": coverage["claimed_forecast_horizon_days"],
        "forecast_coverage_days": coverage["forecast_coverage_days"],
        "forecast_missing_lead_days": coverage["forecast_missing_lead_days"],
        "claimed_lead_time_climate_coverage_sufficient": coverage[
            "claimed_lead_time_climate_coverage_sufficient"
        ],
        "fallback_static_rainfall_used": coverage["fallback_static_rainfall_used"],
        "climate_source_confidence": coverage["climate_source_confidence"],
        "climate_source_confidence_label": coverage["climate_source_confidence_label"],
        "climate_coverage_status": coverage["climate_coverage_status"],
        "climate_coverage_caveats": coverage["climate_coverage_caveats"],
    }


def climate_coverage_summary_from_feature_values(feature_values_rows: Iterable[dict]) -> dict:
    coverages = [climate_coverage_from_prediction(values) for values in feature_values_rows]
    row_count = len(coverages)
    evidence_count = sum(1 for coverage in coverages if coverage["evidence_available"])
    sufficient_count = sum(
        1 for coverage in coverages if coverage["claimed_lead_time_climate_coverage_sufficient"]
    )
    fallback_count = sum(1 for coverage in coverages if coverage["fallback_static_rainfall_used"])
    caveat_counts = Counter(caveat for coverage in coverages for caveat in coverage["climate_coverage_caveats"])
    source_label_counts = Counter(coverage["observed_vs_forecast_source_label"] for coverage in coverages)
    confidence_scores = [coverage["climate_source_confidence"] for coverage in coverages]
    readiness_caveats = []
    if evidence_count < row_count:
        readiness_caveats.append("climate_coverage_evidence_missing_for_some_rows")
    if sufficient_count < row_count:
        readiness_caveats.append("insufficient_forecast_horizon_for_some_rows")
    if fallback_count:
        readiness_caveats.append("fallback_static_climate_source_present")

    return {
        "schema_version": CLIMATE_COVERAGE_POLICY_SCHEMA_VERSION,
        "row_count": row_count,
        "rows_with_climate_coverage_evidence": evidence_count,
        "rows_with_sufficient_claimed_climate_coverage": sufficient_count,
        "rows_with_insufficient_claimed_climate_coverage": row_count - sufficient_count,
        "rows_with_fallback_static_rainfall": fallback_count,
        "rows_with_missing_forecast_lead_days": sum(
            1 for coverage in coverages if coverage["forecast_missing_lead_days"]
        ),
        "caveat_counts": dict(caveat_counts),
        "source_label_counts": dict(source_label_counts),
        "min_climate_source_confidence": min(confidence_scores, default=None),
        "average_climate_source_confidence": round(sum(confidence_scores) / row_count, 4)
        if row_count
        else None,
        "claimed_forecast_horizon_days": DEFAULT_CLAIMED_FORECAST_HORIZON_DAYS,
        "ready_for_claimed_forecast_horizon": bool(row_count and not readiness_caveats),
        "readiness_caveats": readiness_caveats,
    }
