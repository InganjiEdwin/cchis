from __future__ import annotations

from django.utils import timezone

from risk.models import HealthFacility

from .services import build_facility_intelligence_snapshot, latest_riskscore_for_ward


FACILITY_FORECAST_HORIZON_DAYS = 7
FACILITY_FORECAST_TARGET = "expected_suspected_cases_per_facility_7d"
FACILITY_FORECAST_MODE_PROXY = "proxy_preforecast_from_current_readiness_contract"


def build_facility_forecasting_truth_audit() -> dict:
    return {
        "forecasting_state": "phase_0_truth_audited_phase_1_contract_defined",
        "current_baseline_model": None,
        "planned_baseline_model": "negative_binomial_regression",
        "truth_sources": {
            "direct_operational_truth": [
                "facility master record",
                "ward-to-facility linkage",
                "ward risk linkage",
                "alert history by ward",
                "facility updated_at freshness marker",
            ],
            "derived_proxy_inputs": [
                "projected cases derived from promoted ward-risk outputs",
                "surge pressure derived from ward risk level",
                "ORS and staffing pressure derived from heuristic mappings",
            ],
            "not_yet_available_as_real_facility_forecast_inputs": [
                "facility-level historical suspected cholera case counts",
                "facility catchment-level observed burden history",
                "real staffing rosters",
                "real ORS or stock ledger data",
                "bed or observation occupancy history",
                "facility referral overflow history",
            ],
        },
        "honesty_rules": {
            "negative_binomial_not_yet_live": True,
            "current_readiness_is_proxy_backed": True,
            "dashboard_must_not_present_proxy_as_promoted_forecast": True,
        },
    }


def build_initial_facility_forecast_contract_definition() -> dict:
    return {
        "horizon_days": FACILITY_FORECAST_HORIZON_DAYS,
        "target_variable": FACILITY_FORECAST_TARGET,
        "count_target_definition": "expected suspected cholera or diarrheal case count per facility over 7 days",
        "readiness_state_mapping": {
            "low": "projected pressure is routine and no near-term capacity concern is visible",
            "watch": "projected pressure is elevated and closer monitoring is required",
            "capacity_concern": "projected pressure is high enough to justify explicit preparedness concern",
        },
        "forecast_output_fields": [
            "facility_id",
            "generated_at",
            "horizon_days",
            "projected_case_burden",
            "projected_pressure_score",
            "projected_readiness_state",
            "surge_threshold_state",
            "driving_ward_ids",
            "forecast_factors",
            "model_version",
            "freshness_state",
            "forecast_mode",
        ],
        "dashboard_allowed_now": [
            "projected_case_burden",
            "projected_pressure_score",
            "projected_readiness_state",
            "surge_threshold_state",
            "driving_ward_ids",
            "forecast_factors",
            "freshness_state",
            "forecast_mode",
        ],
        "dashboard_not_allowed_to_imply_yet": [
            "negative_binomial_is_live",
            "real_count_forecast_confidence_intervals",
            "facility_historical_case_fit_quality",
            "promoted_forecast_model_version_when_none_exists",
        ],
    }


def _pressure_score_from_snapshot(readiness: dict) -> int:
    surge_risk = readiness.get("surge_risk")
    base = 25
    if surge_risk == "EXTREME":
        base = 80
    elif surge_risk == "MODERATE":
        base = 55

    staffing_percent = int(readiness.get("staffing_percent") or 0)
    ors_percent = int(readiness.get("ors_estimate_percent") or 0)
    pressure = base + max(0, 70 - staffing_percent) // 4 + max(0, 70 - ors_percent) // 4
    return max(0, min(100, pressure))


def _readiness_state_from_score(score: int) -> str:
    if score >= 75:
        return "capacity_concern"
    if score >= 45:
        return "watch"
    return "low"


def build_initial_facility_forecast_preview(facility: HealthFacility) -> dict:
    snapshot = build_facility_intelligence_snapshot(facility)
    readiness = snapshot["readiness"]
    latest_risk = latest_riskscore_for_ward(facility.ward)
    pressure_score = _pressure_score_from_snapshot(readiness)
    generated_at = (
        latest_risk.generated_at
        if latest_risk is not None
        else facility.updated_at
        or timezone.now()
    )
    forecast_factors = [
        {
            "label": "Ward risk level",
            "value": latest_risk.risk_level if latest_risk is not None else facility.ward.current_risk_level,
            "source": "promoted_ward_risk",
            "mode": "direct_or_fallback",
        },
        {
            "label": "Projected case burden",
            "value": readiness["projected_cases"],
            "source": "facility_proxy_projection",
            "mode": "proxy",
        },
        {
            "label": "Staffing state",
            "value": readiness["staffing_state"],
            "source": "facility_proxy_projection",
            "mode": "proxy",
        },
        {
            "label": "ORS state",
            "value": readiness["ors_state"],
            "source": "facility_proxy_projection",
            "mode": "proxy",
        },
    ]

    return {
        "facility_id": facility.id,
        "generated_at": generated_at,
        "horizon_days": FACILITY_FORECAST_HORIZON_DAYS,
        "projected_case_burden": readiness["projected_cases"],
        "projected_pressure_score": pressure_score,
        "projected_readiness_state": _readiness_state_from_score(pressure_score),
        "surge_threshold_state": {
            "ors": readiness["ors_state"].lower(),
            "staffing": readiness["staffing_state"].lower(),
            "observation_burden": "capacity_concern"
            if readiness["surge_risk"] == "EXTREME"
            else "watch"
            if readiness["surge_risk"] == "MODERATE"
            else "low",
        },
        "driving_ward_ids": [facility.ward_id],
        "forecast_factors": forecast_factors,
        "model_version": None,
        "freshness_state": readiness["freshness_state"],
        "forecast_mode": FACILITY_FORECAST_MODE_PROXY,
        "baseline_model_status": "negative_binomial_not_yet_implemented",
    }
