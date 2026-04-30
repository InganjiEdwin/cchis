from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

import numpy as np
from django.utils import timezone
from scipy.optimize import minimize
from scipy.special import gammaln

from risk.models import FacilityForecast, FacilityForecastRun, FeatureDataset, FeatureDatasetRow, HealthFacility, Ward

from .services import build_facility_intelligence_snapshot, latest_riskscore_for_ward


FACILITY_FORECAST_HORIZON_DAYS = 7
FACILITY_FORECAST_TARGET = "expected_suspected_cases_per_facility_7d"
FACILITY_FORECAST_MODE_PROXY = "proxy_preforecast_from_current_readiness_contract"
FACILITY_FORECAST_MODE_MODEL = "negative_binomial_baseline_preview"
FACILITY_FORECAST_FEATURE_SCHEMA_VERSION = "facility-burden-v1"
FACILITY_FORECAST_PROMOTION_TARGET_PREVIEW = "forecast_preview_only"
FACILITY_FORECAST_PROMOTION_TARGET_DASHBOARD = "dashboard_readiness_promoted"
FACILITY_FORECAST_FEATURE_KEYS = [
    "ward_risk_score",
    "ward_alert_count",
    "facility_level_numeric",
    "facility_type_numeric",
    "staffing_percent",
    "ors_estimate_percent",
]
FACILITY_FORECAST_PROMOTION_BLOCKERS = [
    "proxy_training_target_only",
    "real_facility_case_history_missing",
    "out_of_time_validation_missing",
    "threshold_usefulness_review_incomplete",
    "operational_promotion_review_pending",
]


@dataclass
class FacilityForecastRow:
    facility: HealthFacility
    ward_risk_score: float
    ward_alert_count: int
    facility_level_numeric: int
    facility_type_numeric: int
    staffing_percent: int
    ors_estimate_percent: int
    target_count: int


def _facility_forecast_feature_values_from_row(row: FacilityForecastRow) -> dict:
    return {
        "facility_id": row.facility.id,
        "facility_name": row.facility.name,
        "ward_id": row.facility.ward_id,
        "ward_name": row.facility.ward.name,
        "ward_risk_score": row.ward_risk_score,
        "ward_alert_count": row.ward_alert_count,
        "facility_level_numeric": row.facility_level_numeric,
        "facility_type_numeric": row.facility_type_numeric,
        "staffing_percent": row.staffing_percent,
        "ors_estimate_percent": row.ors_estimate_percent,
    }


def _persist_facility_forecast_feature_dataset(
    *,
    rows: list[FacilityForecastRow],
    dataset_kind: str,
    month: int,
) -> FeatureDataset:
    dataset_role = "training" if dataset_kind == FeatureDataset.KIND_TRAINING else "inference"
    dataset = FeatureDataset.objects.create(
        dataset_ref=f"facility-forecast-{dataset_role}-{FACILITY_FORECAST_FEATURE_SCHEMA_VERSION}-month-{month}-{uuid4().hex[:8]}",
        dataset_kind=dataset_kind,
        schema_version=FACILITY_FORECAST_FEATURE_SCHEMA_VERSION,
        source_kind=FeatureDataset.SOURCE_KIND_HYBRID,
        month=month,
        feature_keys=FACILITY_FORECAST_FEATURE_KEYS,
        row_count=len(rows),
        lineage_metadata={
            "builder": "_persist_facility_forecast_feature_dataset",
            "dataset_role": dataset_role,
            "model_family": "facility_burden_forecasting",
            "target_mode": "proxy_derived_facility_burden" if dataset_kind == FeatureDataset.KIND_TRAINING else "not_applicable",
        },
    )
    FeatureDatasetRow.objects.bulk_create(
        [
            FeatureDatasetRow(
                dataset=dataset,
                ward=row.facility.ward,
                ward_name_snapshot=row.facility.ward.name,
                month=month,
                feature_values=_facility_forecast_feature_values_from_row(row),
                label=row.target_count if dataset_kind == FeatureDataset.KIND_TRAINING else None,
            )
            for row in rows
        ]
    )
    return dataset


def build_facility_forecasting_truth_audit() -> dict:
    promoted_run = _latest_promoted_facility_forecast_run()
    latest_run = _latest_successful_facility_forecast_run()
    current_run = promoted_run or latest_run
    current_model = current_run.algorithm_name if current_run else None
    current_state = (
        "promoted"
        if promoted_run
        else "implemented_not_promoted"
        if latest_run
        else "not_yet_implemented"
    )
    forecasting_state = (
        "phase_4_promoted_dashboard_forecast_available"
        if promoted_run
        else "phase_2_baseline_implemented_not_promoted"
        if latest_run
        else "phase_0_truth_audited_phase_1_contract_defined"
    )
    return {
        "forecasting_state": forecasting_state,
        "current_baseline_model": current_model,
        "current_baseline_state": current_state,
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
            "negative_binomial_not_yet_promoted": not bool(promoted_run),
            "current_readiness_is_proxy_backed": not bool(promoted_run),
            "dashboard_must_not_present_preview_as_promoted_forecast": True,
        },
    }


def _latest_successful_facility_forecast_run() -> FacilityForecastRun | None:
    return (
        FacilityForecastRun.objects.filter(status=FacilityForecastRun.STATUS_SUCCESS)
        .exclude(model_version__startswith="seed-scenario-ff-")
        .order_by("-started_at")
        .first()
    )


def _latest_promoted_facility_forecast_run() -> FacilityForecastRun | None:
    return (
        FacilityForecastRun.objects.filter(
            status=FacilityForecastRun.STATUS_SUCCESS,
            metadata__promotion_target=FACILITY_FORECAST_PROMOTION_TARGET_DASHBOARD,
        )
        .exclude(model_version__startswith="seed-scenario-ff-")
        .order_by("-started_at")
        .first()
    )


def _run_summary(run: FacilityForecastRun) -> dict:
    metadata = run.metadata or {}
    return {
        "model_version": run.model_version,
        "algorithm_name": run.algorithm_name,
        "status": run.status,
        "horizon_days": run.horizon_days,
        "feature_schema_version": run.feature_schema_version,
        "feature_keys": run.feature_keys,
        "target_definition": run.target_definition,
        "training_row_count": run.training_row_count,
        "inference_row_count": run.inference_row_count,
        "evaluation_metrics": run.evaluation_metrics or {},
        "execution_context": metadata.get("execution_context"),
        "run_purpose": metadata.get("run_purpose"),
        "promotion_target": metadata.get("promotion_target"),
        "retraining_policy": metadata.get("retraining_policy"),
        "target_mode": metadata.get("target_mode"),
        "started_at": run.started_at,
        "completed_at": run.completed_at,
    }


def build_facility_forecast_promotion_summary(run: FacilityForecastRun | None = None) -> dict:
    run = run or _latest_promoted_facility_forecast_run() or _latest_successful_facility_forecast_run()
    if run is None:
        return {
            "current_run": None,
            "evaluation": {
                "count_error_discipline": {"status": "not_available"},
                "threshold_usefulness": {"status": "not_available"},
                "operational_usefulness": {"status": "not_available"},
                "stability_across_time_windows": {"status": "not_available"},
                "explainability": {"status": "not_available"},
            },
            "decision": {
                "recommended_state": "not_promoted",
                "governance_mode": "not_yet_implemented",
                "promotion_readiness": "not_ready_for_promotion",
                "promotion_blockers": ["baseline_run_missing"],
                "decision_reason": "No successful facility burden baseline run exists yet.",
                "allowed_product_surfaces": ["truth_audit", "contract_definition"],
                "blocked_product_surfaces": [
                    "dashboard_readiness_warning",
                    "promoted_facility_summary",
                    "action_panel_facility_pressure",
                ],
            },
        }

    forecasts = list(run.forecasts.all())
    readiness_counts = {
        "low": sum(1 for forecast in forecasts if forecast.projected_readiness_state == FacilityForecast.READINESS_LOW),
        "watch": sum(1 for forecast in forecasts if forecast.projected_readiness_state == FacilityForecast.READINESS_WATCH),
        "capacity_concern": sum(
            1 for forecast in forecasts if forecast.projected_readiness_state == FacilityForecast.READINESS_CAPACITY_CONCERN
        ),
    }
    surge_threshold_coverage = sum(
        1
        for forecast in forecasts
        if {"ors", "staffing", "observation_burden"}.issubset(set((forecast.surge_threshold_state or {}).keys()))
    )
    factor_coverage = sum(1 for forecast in forecasts if forecast.forecast_factors)
    evaluation_metrics = run.evaluation_metrics or {}

    count_error_status = "partial_proxy_only"
    if "training_count_mae" in evaluation_metrics:
        count_error_status = "measured_on_proxy_training_target"

    threshold_status = "partial"
    if surge_threshold_coverage == len(forecasts) and forecasts:
        threshold_status = "derived_thresholds_present_but_not_operationally_reviewed"

    operational_status = "partial"
    if factor_coverage == len(forecasts) and forecasts:
        operational_status = "forecast_factors_and_driving_wards_present"

    explainability_status = "present" if forecasts else "not_available"

    is_promoted = is_promoted_facility_forecast_run(run)
    promotion_blockers = [] if is_promoted else FACILITY_FORECAST_PROMOTION_BLOCKERS
    recommended_state = "promoted" if is_promoted else "not_promoted"
    governance_mode = "promoted" if is_promoted else "preview_only"
    promotion_readiness = "promoted_with_manual_review" if is_promoted else "not_ready_for_promotion"
    decision_reason = (
        "This facility burden forecast run has been manually promoted for dashboard readiness use after explicit review."
        if is_promoted
        else "The Negative Binomial baseline is implemented and persisted, but promotion remains blocked because "
        "the target is still proxy-derived and real facility burden evidence is incomplete."
    )
    allowed_product_surfaces = (
        [
            "facility_forecast_preview",
            "ops_admin_review",
            "forecast_evaluation_review",
            "dashboard_readiness_warning",
            "promoted_facility_summary",
            "action_panel_facility_pressure",
        ]
        if is_promoted
        else [
            "facility_forecast_preview",
            "ops_admin_review",
            "forecast_evaluation_review",
        ]
    )
    blocked_product_surfaces = [] if is_promoted else [
        "dashboard_readiness_warning",
        "promoted_facility_summary",
        "action_panel_facility_pressure",
    ]

    return {
        "current_run": _run_summary(run),
        "evaluation": {
            "count_error_discipline": {
                "status": count_error_status,
                "training_count_mae": evaluation_metrics.get("training_count_mae"),
                "target_mode": evaluation_metrics.get("target_mode"),
            },
            "threshold_usefulness": {
                "status": threshold_status,
                "forecast_count": len(forecasts),
                "surge_threshold_coverage_count": surge_threshold_coverage,
                "readiness_state_counts": readiness_counts,
            },
            "operational_usefulness": {
                "status": operational_status,
                "driving_ward_linkage_present": all(bool(forecast.driving_ward_ids) for forecast in forecasts) if forecasts else False,
                "forecast_factor_coverage_count": factor_coverage,
            },
            "stability_across_time_windows": {
                "status": "not_yet_established",
                "blocker": "single_proxy_backbone_without_out_of_time_review",
            },
            "explainability": {
                "status": explainability_status,
                "factor_count_per_forecast": len(forecasts[0].forecast_factors) if forecasts else 0,
                "algorithm_family": "negative_binomial_regression",
            },
        },
        "decision": {
            "recommended_state": recommended_state,
            "governance_mode": governance_mode,
            "promotion_readiness": promotion_readiness,
            "promotion_blockers": promotion_blockers,
            "decision_reason": decision_reason,
            "allowed_product_surfaces": allowed_product_surfaces,
            "blocked_product_surfaces": blocked_product_surfaces,
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


def _level_to_numeric(level: str) -> int:
    return {
        HealthFacility.LEVEL_2: 2,
        HealthFacility.LEVEL_3: 3,
        HealthFacility.LEVEL_4: 4,
        HealthFacility.LEVEL_5: 5,
    }.get(level, 2)


def _type_to_numeric(facility_type: str) -> int:
    return {
        HealthFacility.TYPE_DISPENSARY: 1,
        HealthFacility.TYPE_HEALTH_CENTER: 2,
        HealthFacility.TYPE_CLINIC: 2,
        HealthFacility.TYPE_HOSPITAL: 4,
    }.get(facility_type, 1)


def _target_count_from_snapshot(readiness: dict, context: dict) -> int:
    projected_cases = int(readiness["projected_cases"])
    alert_weight = int(context["ward_alert_count"]) * 2
    surge_weight = 6 if readiness["surge_risk"] == "EXTREME" else 3 if readiness["surge_risk"] == "MODERATE" else 0
    return max(1, projected_cases + alert_weight + surge_weight)


def _build_base_training_rows(facilities: list[HealthFacility]) -> list[FacilityForecastRow]:
    rows: list[FacilityForecastRow] = []
    for facility in facilities:
        snapshot = build_facility_intelligence_snapshot(facility)
        readiness = snapshot["readiness"]
        context = snapshot["context"]
        rows.append(
            FacilityForecastRow(
                facility=facility,
                ward_risk_score=float(context["ward_risk_score"] or 0.0),
                ward_alert_count=int(context["ward_alert_count"] or 0),
                facility_level_numeric=_level_to_numeric(facility.level),
                facility_type_numeric=_type_to_numeric(facility.facility_type),
                staffing_percent=int(readiness["staffing_percent"]),
                ors_estimate_percent=int(readiness["ors_estimate_percent"]),
                target_count=_target_count_from_snapshot(readiness, context),
            )
        )
    return rows


def _expand_training_rows(rows: list[FacilityForecastRow]) -> list[FacilityForecastRow]:
    expanded: list[FacilityForecastRow] = []
    multipliers = [0.85, 1.0, 1.15]
    for row in rows:
        for idx, multiplier in enumerate(multipliers):
            target = max(1, int(round(row.target_count * multiplier + (idx - 1) + (row.facility.id % 3))))
            expanded.append(
                FacilityForecastRow(
                    facility=row.facility,
                    ward_risk_score=max(0.0, row.ward_risk_score * multiplier),
                    ward_alert_count=max(0, int(round(row.ward_alert_count * multiplier))),
                    facility_level_numeric=row.facility_level_numeric,
                    facility_type_numeric=row.facility_type_numeric,
                    staffing_percent=max(1, min(100, int(round(row.staffing_percent * (2 - multiplier))))),
                    ors_estimate_percent=max(1, min(100, int(round(row.ors_estimate_percent * (2 - multiplier))))),
                    target_count=target,
                )
            )
    return expanded


def _rows_to_matrix(rows: list[FacilityForecastRow]) -> tuple[np.ndarray, np.ndarray]:
    x = []
    y = []
    for row in rows:
        x.append(
            [
                1.0,
                row.ward_risk_score,
                row.ward_alert_count,
                row.facility_level_numeric,
                row.facility_type_numeric,
                row.staffing_percent / 100.0,
                row.ors_estimate_percent / 100.0,
            ]
        )
        y.append(row.target_count)
    return np.asarray(x, dtype=float), np.asarray(y, dtype=float)


def _negative_binomial_nll(params: np.ndarray, x: np.ndarray, y: np.ndarray) -> float:
    beta = params[:-1]
    log_alpha = params[-1]
    alpha = float(np.exp(log_alpha))
    mu = np.exp(np.clip(x @ beta, -20, 20))
    inv_alpha = 1.0 / max(alpha, 1e-8)
    term = (
        gammaln(y + inv_alpha)
        - gammaln(inv_alpha)
        - gammaln(y + 1.0)
        + inv_alpha * np.log(inv_alpha / (inv_alpha + mu))
        + y * np.log(mu / (inv_alpha + mu))
    )
    return float(-np.sum(term))


def _fit_negative_binomial(x: np.ndarray, y: np.ndarray) -> dict:
    initial = np.zeros(x.shape[1] + 1, dtype=float)
    initial[-1] = np.log(0.5)
    result = minimize(_negative_binomial_nll, initial, args=(x, y), method="L-BFGS-B")
    if not result.success:
        raise RuntimeError(f"Negative Binomial optimization failed: {result.message}")
    beta = result.x[:-1]
    alpha = float(np.exp(result.x[-1]))
    return {"coefficients": beta, "alpha": alpha, "optimizer_success": True}


def _predict_counts(model: dict, x: np.ndarray) -> np.ndarray:
    return np.exp(np.clip(x @ model["coefficients"], -20, 20))


def _pressure_score_from_forecast(case_burden: int, staffing_percent: int, ors_percent: int) -> int:
    score = case_burden * 3 + max(0, 70 - staffing_percent) // 2 + max(0, 70 - ors_percent) // 2
    return max(0, min(100, score))


def _readiness_state_from_score(score: int) -> str:
    if score >= 75:
        return FacilityForecast.READINESS_CAPACITY_CONCERN
    if score >= 45:
        return FacilityForecast.READINESS_WATCH
    return FacilityForecast.READINESS_LOW


def _surge_threshold_state(case_burden: int, staffing_percent: int, ors_percent: int) -> dict:
    def level_from_percent(percent: int) -> str:
        if percent < 35:
            return "capacity_concern"
        if percent < 65:
            return "watch"
        return "low"

    return {
        "ors": level_from_percent(ors_percent),
        "staffing": level_from_percent(staffing_percent),
        "observation_burden": "capacity_concern" if case_burden >= 20 else "watch" if case_burden >= 10 else "low",
    }


def _forecast_factors(row: FacilityForecastRow) -> list[dict]:
    return [
        {"label": "Ward risk score", "value": round(row.ward_risk_score, 4), "source": "promoted_ward_risk", "mode": "direct_or_fallback"},
        {"label": "Ward alert count", "value": row.ward_alert_count, "source": "ward_alert_history", "mode": "direct_or_fallback"},
        {"label": "Facility level", "value": row.facility_level_numeric, "source": "facility_master_record", "mode": "direct"},
        {"label": "Facility type", "value": row.facility_type_numeric, "source": "facility_master_record", "mode": "direct"},
        {"label": "Staffing percent", "value": row.staffing_percent, "source": "facility_proxy_projection", "mode": "proxy"},
        {"label": "ORS estimate percent", "value": row.ors_estimate_percent, "source": "facility_proxy_projection", "mode": "proxy"},
    ]


def run_facility_burden_forecast_pipeline(
    *,
    model_version: str = "fnb-v1",
    horizon_days: int = FACILITY_FORECAST_HORIZON_DAYS,
    execution_context: str = "manual_command",
    run_purpose: str = "forecast_scoring",
) -> FacilityForecastRun:
    facilities = list(HealthFacility.objects.filter(is_active=True).select_related("ward").order_by("ward__name", "name"))
    if not facilities:
        raise RuntimeError("No active facilities are available for facility burden forecasting.")

    base_rows = _build_base_training_rows(facilities)
    training_rows = _expand_training_rows(base_rows)
    dataset_month = timezone.now().month
    training_dataset = _persist_facility_forecast_feature_dataset(
        rows=training_rows,
        dataset_kind=FeatureDataset.KIND_TRAINING,
        month=dataset_month,
    )
    inference_dataset = _persist_facility_forecast_feature_dataset(
        rows=base_rows,
        dataset_kind=FeatureDataset.KIND_INFERENCE,
        month=dataset_month,
    )
    run = FacilityForecastRun.objects.create(
        algorithm_name="negative-binomial-baseline",
        model_version=model_version,
        status=FacilityForecastRun.STATUS_RUNNING,
        horizon_days=horizon_days,
        feature_schema_version=FACILITY_FORECAST_FEATURE_SCHEMA_VERSION,
        feature_keys=FACILITY_FORECAST_FEATURE_KEYS,
        target_definition=FACILITY_FORECAST_TARGET,
        training_row_count=0,
        inference_row_count=len(base_rows),
        evaluation_metrics={},
        metadata={
            "execution_context": execution_context,
            "run_purpose": run_purpose,
            "promotion_target": FACILITY_FORECAST_PROMOTION_TARGET_PREVIEW,
            "retraining_policy": "manual_promotion_only",
            "model_family": "facility_burden_forecasting",
            "baseline_model_status": "implemented_not_promoted",
            "target_mode": "proxy_derived_facility_burden",
            "training_dataset_ref": training_dataset.dataset_ref,
            "inference_dataset_ref": inference_dataset.dataset_ref,
            "training_feature_dataset_id": training_dataset.id,
            "inference_feature_dataset_id": inference_dataset.id,
        },
    )

    try:
        x_train, y_train = _rows_to_matrix(training_rows)
        model = _fit_negative_binomial(x_train, y_train)
        y_hat = _predict_counts(model, x_train)
        mae = float(np.mean(np.abs(y_train - y_hat)))

        run.training_row_count = len(training_rows)
        run.evaluation_metrics = {
            "algorithm": "negative_binomial_regression",
            "training_count_mae": round(mae, 4),
            "training_row_count": len(training_rows),
            "alpha": round(model["alpha"], 6),
            "target_mode": "proxy_derived_facility_burden",
            "evidence_limitations": [
                "facility_historical_case_counts_not_yet_available",
                "training_target_is_proxy_derived",
            ],
        }
        run.save(update_fields=["training_row_count", "evaluation_metrics"])

        inference_x, _ = _rows_to_matrix(base_rows)
        predictions = _predict_counts(model, inference_x)
        generated_at = timezone.now()

        forecasts = []
        for row, prediction in zip(base_rows, predictions):
            projected_case_burden = max(1, int(round(float(prediction))))
            pressure_score = _pressure_score_from_forecast(
                projected_case_burden,
                row.staffing_percent,
                row.ors_estimate_percent,
            )
            forecasts.append(
                FacilityForecast(
                    facility=row.facility,
                    forecast_run=run,
                    generated_at=generated_at,
                    horizon_days=horizon_days,
                    projected_case_burden=projected_case_burden,
                    projected_pressure_score=pressure_score,
                    projected_readiness_state=_readiness_state_from_score(pressure_score),
                    surge_threshold_state=_surge_threshold_state(
                        projected_case_burden,
                        row.staffing_percent,
                        row.ors_estimate_percent,
                    ),
                    driving_ward_ids=[row.facility.ward_id],
                    forecast_factors=_forecast_factors(row),
                    model_version=model_version,
                    freshness_state="FRESH",
                    forecast_mode=FACILITY_FORECAST_MODE_MODEL,
                )
            )
        FacilityForecast.objects.bulk_create(forecasts)

        run.status = FacilityForecastRun.STATUS_SUCCESS
        run.completed_at = timezone.now()
        run.save(update_fields=["status", "completed_at"])
        return run
    except Exception as exc:
        run.status = FacilityForecastRun.STATUS_FAILED
        run.completed_at = timezone.now()
        run.metadata = {
            **(run.metadata or {}),
            "failure_reason": str(exc),
        }
        run.save(update_fields=["status", "completed_at", "metadata"])
        raise


def latest_facility_forecast_for_facility(facility: HealthFacility) -> FacilityForecast | None:
    return facility.facility_forecasts.select_related("forecast_run").order_by("-generated_at").first()


def is_promoted_facility_forecast_run(run: FacilityForecastRun | None) -> bool:
    if run is None:
        return False
    return (run.metadata or {}).get("promotion_target") == FACILITY_FORECAST_PROMOTION_TARGET_DASHBOARD


def latest_promoted_facility_forecast_for_facility(facility: HealthFacility) -> FacilityForecast | None:
    return (
        facility.facility_forecasts.select_related("forecast_run")
        .filter(forecast_run__metadata__promotion_target=FACILITY_FORECAST_PROMOTION_TARGET_DASHBOARD)
        .order_by("-generated_at")
        .first()
    )


def preferred_facility_forecast_for_facility(facility: HealthFacility) -> FacilityForecast | None:
    promoted_forecast = latest_promoted_facility_forecast_for_facility(facility)
    if promoted_forecast is not None:
        return promoted_forecast
    return latest_facility_forecast_for_facility(facility)


def promote_facility_forecast_run(
    run: FacilityForecastRun,
    *,
    promoted_by: str | None = None,
    note: str | None = None,
    allow_blocked_promotion: bool = False,
) -> FacilityForecastRun:
    summary = build_facility_forecast_promotion_summary(run)
    blockers = summary["decision"]["promotion_blockers"]
    if blockers and not allow_blocked_promotion:
        raise ValueError(
            "Promotion is blocked by unresolved evidence gaps. "
            "Use explicit override acknowledgement to promote anyway."
        )

    for existing_run in FacilityForecastRun.objects.filter(
        status=FacilityForecastRun.STATUS_SUCCESS,
        metadata__promotion_target=FACILITY_FORECAST_PROMOTION_TARGET_DASHBOARD,
    ).exclude(id=run.id):
        existing_run.metadata = {
            **(existing_run.metadata or {}),
            "promotion_target": FACILITY_FORECAST_PROMOTION_TARGET_PREVIEW,
            "demoted_at": timezone.now().isoformat(),
            "demotion_reason": "superseded_by_new_promoted_run",
        }
        existing_run.save(update_fields=["metadata"])

    run.metadata = {
        **(run.metadata or {}),
        "promotion_target": FACILITY_FORECAST_PROMOTION_TARGET_DASHBOARD,
        "promoted_at": timezone.now().isoformat(),
        "promoted_by": promoted_by,
        "promotion_note": note or "",
        "promotion_override_acknowledged": allow_blocked_promotion,
        "promotion_blockers_at_decision": blockers,
    }
    run.save(update_fields=["metadata"])
    return run


def build_facility_forecasting_dashboard_summary(*, wards: list[Ward] | None = None) -> dict:
    ward_ids = {ward.id for ward in (wards or [])}
    forecasts = list(
        FacilityForecast.objects.select_related("facility", "forecast_run")
        .filter(forecast_run__status=FacilityForecastRun.STATUS_SUCCESS)
        .order_by("facility_id", "-generated_at")
    )

    latest_preview_by_facility: dict[int, FacilityForecast] = {}
    latest_promoted_by_facility: dict[int, FacilityForecast] = {}
    for forecast in forecasts:
        latest_preview_by_facility.setdefault(forecast.facility_id, forecast)
        if is_promoted_facility_forecast_run(forecast.forecast_run):
            latest_promoted_by_facility.setdefault(forecast.facility_id, forecast)

    latest_preview_forecasts = list(latest_preview_by_facility.values())
    if not latest_preview_forecasts:
        return {
            "source_kind": "proxy_only",
            "governance_mode": "not_promoted",
            "dashboard_truth_state": "blocked_until_promotion",
            "promoted_facility_count": 0,
            "preview_available_count": 0,
            "capacity_concern_count": 0,
            "watch_count": 0,
            "driving_ward_ids": [],
            "preview_driving_ward_ids": [],
            "blocked_product_surfaces": [
                "dashboard_readiness_warning",
                "promoted_facility_summary",
                "action_panel_facility_pressure",
            ],
        }

    relevant_preview_forecasts = latest_preview_forecasts
    relevant_promoted_forecasts = list(latest_promoted_by_facility.values())
    if ward_ids:
        relevant_preview_forecasts = [
            forecast
            for forecast in latest_preview_forecasts
            if forecast.facility.ward_id in ward_ids or bool(ward_ids.intersection(set(forecast.driving_ward_ids or [])))
        ]
        relevant_promoted_forecasts = [
            forecast
            for forecast in relevant_promoted_forecasts
            if forecast.facility.ward_id in ward_ids or bool(ward_ids.intersection(set(forecast.driving_ward_ids or [])))
        ]

    preview_driving_ward_ids = sorted(
        {
            ward_id
            for forecast in relevant_preview_forecasts
            for ward_id in (forecast.driving_ward_ids or [])
        }
    )
    driving_ward_ids = sorted(
        {
            ward_id
            for forecast in relevant_promoted_forecasts
            for ward_id in (forecast.driving_ward_ids or [])
        }
    )

    if not relevant_promoted_forecasts:
        return {
            "source_kind": "preview_available_but_blocked",
            "governance_mode": "preview_only_not_promoted",
            "dashboard_truth_state": "blocked_until_promotion",
            "promoted_facility_count": 0,
            "preview_available_count": len(relevant_preview_forecasts),
            "capacity_concern_count": 0,
            "watch_count": 0,
            "driving_ward_ids": [],
            "preview_driving_ward_ids": preview_driving_ward_ids,
            "blocked_product_surfaces": [
                "dashboard_readiness_warning",
                "promoted_facility_summary",
                "action_panel_facility_pressure",
            ],
        }

    return {
        "source_kind": "promoted_forecast",
        "governance_mode": "promoted",
        "dashboard_truth_state": "promoted",
        "promoted_facility_count": len(relevant_promoted_forecasts),
        "preview_available_count": len(relevant_preview_forecasts),
        "capacity_concern_count": sum(
            1 for forecast in relevant_promoted_forecasts if forecast.projected_readiness_state == FacilityForecast.READINESS_CAPACITY_CONCERN
        ),
        "watch_count": sum(
            1 for forecast in relevant_promoted_forecasts if forecast.projected_readiness_state == FacilityForecast.READINESS_WATCH
        ),
        "driving_ward_ids": driving_ward_ids,
        "preview_driving_ward_ids": preview_driving_ward_ids,
        "blocked_product_surfaces": [],
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


def build_initial_facility_forecast_preview(facility: HealthFacility) -> dict:
    latest_forecast = preferred_facility_forecast_for_facility(facility)
    if latest_forecast and latest_forecast.forecast_run.status == FacilityForecastRun.STATUS_SUCCESS:
        promoted_forecast = is_promoted_facility_forecast_run(latest_forecast.forecast_run)
        return {
            "facility_id": facility.id,
            "generated_at": latest_forecast.generated_at,
            "horizon_days": latest_forecast.horizon_days,
            "projected_case_burden": latest_forecast.projected_case_burden,
            "projected_pressure_score": latest_forecast.projected_pressure_score,
            "projected_readiness_state": latest_forecast.projected_readiness_state,
            "surge_threshold_state": latest_forecast.surge_threshold_state,
            "driving_ward_ids": latest_forecast.driving_ward_ids,
            "forecast_factors": latest_forecast.forecast_factors,
            "model_version": latest_forecast.model_version or latest_forecast.forecast_run.model_version,
            "freshness_state": latest_forecast.freshness_state,
            "forecast_mode": latest_forecast.forecast_mode,
            "baseline_model_status": (
                "negative_binomial_promoted_for_dashboard_readiness"
                if promoted_forecast
                else "negative_binomial_implemented_not_promoted"
            ),
        }

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
