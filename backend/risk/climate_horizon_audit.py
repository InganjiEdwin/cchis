from __future__ import annotations

from datetime import date, datetime
from typing import Any

from django.utils import timezone

from risk.lead_time_features import LEAD_TIME_FEATURE_SCHEMA_VERSION
from risk.climate_coverage import climate_alert_evidence_from_prediction
from risk.models import Alert, FeatureDataset, FeatureDatasetRow, ModelRun, RiskScore


CLIMATE_HORIZON_AUDIT_SCHEMA_VERSION = "climate-horizon-monitoring-audit-v1"
CLIMATE_HORIZON_AUDIT_NAME = "climate_forecast_horizon_source_separation_phase_5"
CLIMATE_EVIDENCE_REQUIRED_FIELDS = [
    "record_type",
    "observed_vs_forecast_source_label",
    "claimed_forecast_horizon_days",
    "forecast_coverage_days",
    "forecast_missing_lead_days",
    "claimed_lead_time_climate_coverage_sufficient",
    "fallback_static_rainfall_used",
    "climate_coverage_status",
    "climate_coverage_caveats",
]
CLIMATE_EVIDENCE_FORECAST_FIELDS = ["source_provider", "issue_time", "valid_date"]
CLIMATE_EVIDENCE_RECORD_TYPES = {
    "observed",
    "forecast",
    "derived_rolling_window",
    "derived_anomaly",
    "fallback_static",
    "unavailable",
}


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


def _parse_datetime(value) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _parse_date(value) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _as_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value) -> list:
    return value if isinstance(value, list) else []


def _as_int_list(value) -> list[int]:
    if not isinstance(value, (list, tuple, set)):
        return []
    days = []
    for item in value:
        day = _safe_int(item)
        if day is not None:
            days.append(day)
    return sorted(dict.fromkeys(days))


def _climate_evidence_for_riskscore(risk_score: RiskScore | None) -> dict:
    if risk_score is None:
        return climate_alert_evidence_from_prediction({})
    decision_policy = risk_score.decision_policy or {}
    policy_inputs = _as_dict(decision_policy.get("inputs"))
    source_confidence = _as_dict(policy_inputs.get("source_confidence"))
    climate_coverage = (
        _as_dict(policy_inputs.get("climate_coverage"))
        or _as_dict(source_confidence.get("climate_coverage"))
        or {}
    )
    return climate_alert_evidence_from_prediction({"climate_coverage": climate_coverage})


def _source_lineage(values: dict, key: str) -> dict:
    return _as_dict(_as_dict(values.get("source_lineage")).get(key))


def _row_context(row: FeatureDatasetRow, *, check_id: str, severity: str, message: str) -> dict:
    values = _as_dict(row.feature_values)
    return {
        "check_id": check_id,
        "severity": severity,
        "record_type": "risk.FeatureDatasetRow",
        "record_id": row.id,
        "dataset_ref": row.dataset.dataset_ref,
        "ward_id": row.ward_id,
        "ward_name": row.ward_name_snapshot,
        "prediction_date": values.get("prediction_date"),
        "message": message,
    }


def _model_run_context(model_run: ModelRun, *, check_id: str, severity: str, message: str) -> dict:
    return {
        "check_id": check_id,
        "severity": severity,
        "record_type": "risk.ModelRun",
        "record_id": model_run.id,
        "model_version": model_run.model_version,
        "algorithm_name": model_run.algorithm_name,
        "promotion_target": (model_run.metadata or {}).get("promotion_target"),
        "message": message,
    }


def _risk_score_context(risk_score: RiskScore, *, check_id: str, severity: str, message: str) -> dict:
    return {
        "check_id": check_id,
        "severity": severity,
        "record_type": "risk.RiskScore",
        "record_id": risk_score.id,
        "ward_id": risk_score.ward_id,
        "ward_name": risk_score.ward.name if risk_score.ward_id else "",
        "model_run_id": risk_score.model_run_id,
        "message": message,
    }


def _alert_context(alert: Alert, *, check_id: str, severity: str, message: str) -> dict:
    return {
        "check_id": check_id,
        "severity": severity,
        "record_type": "risk.Alert",
        "record_id": alert.id,
        "public_id": str(alert.public_id),
        "ward_id": alert.ward_id,
        "ward_name": alert.ward.name if alert.ward_id else "",
        "risk_score_id": alert.risk_score_id,
        "message": message,
    }


def _forecast_lead_days(values: dict, forecast_lineage: dict) -> list[int]:
    return _as_int_list(values.get("forecast_covered_lead_days")) or _as_int_list(
        forecast_lineage.get("covered_lead_days")
    )


def _expected_missing_lead_days(covered_days: list[int], claimed_horizon: int | None) -> list[int]:
    if claimed_horizon is None or claimed_horizon <= 0:
        return []
    return [day for day in range(1, claimed_horizon + 1) if day not in set(covered_days)]


def _climate_evidence_consistency_messages(evidence: dict) -> list[str]:
    messages = []
    missing_fields = _required_climate_evidence_missing(evidence)
    if missing_fields:
        messages.append("missing fields: " + ", ".join(missing_fields))
        return messages

    claimed_horizon = _safe_int(evidence.get("claimed_forecast_horizon_days"))
    coverage_days = _safe_int(evidence.get("forecast_coverage_days"))
    missing_days = _as_int_list(evidence.get("forecast_missing_lead_days"))
    sufficient = evidence.get("claimed_lead_time_climate_coverage_sufficient")
    fallback_used = bool(evidence.get("fallback_static_rainfall_used"))
    status = str(evidence.get("climate_coverage_status") or "")
    record_type = str(evidence.get("record_type") or "")
    source_label = str(evidence.get("observed_vs_forecast_source_label") or "")

    if record_type not in CLIMATE_EVIDENCE_RECORD_TYPES:
        messages.append("record type must be explicit and recognized")
    if claimed_horizon is None or claimed_horizon < 1 or claimed_horizon > 14:
        messages.append("claimed forecast horizon must be between 1 and 14 days")
    if coverage_days is None or coverage_days < 0:
        messages.append("forecast coverage days must be present and non-negative")
    if claimed_horizon is not None and coverage_days is not None and coverage_days > claimed_horizon:
        messages.append("forecast coverage days cannot exceed claimed forecast horizon")
    if claimed_horizon is not None:
        outside_claim = [day for day in missing_days if day < 1 or day > claimed_horizon]
        if outside_claim:
            messages.append("missing lead days fall outside the claimed horizon")
        if coverage_days is not None and coverage_days < claimed_horizon and not missing_days and status != "unavailable":
            messages.append("coverage is below claimed horizon but missing lead days are empty")
        if coverage_days is not None and coverage_days + len(missing_days) < claimed_horizon and status != "unavailable":
            messages.append("coverage days plus missing lead days do not account for the claimed horizon")
    if sufficient is True and missing_days:
        messages.append("sufficiency is true while missing lead days are present")
    if sufficient is True and coverage_days is not None and claimed_horizon is not None and coverage_days < claimed_horizon:
        messages.append("sufficiency is true while coverage is below the claimed horizon")
    if sufficient is True and fallback_used:
        messages.append("fallback static rainfall cannot be marked sufficient live forecast evidence")
    if missing_days and status == "sufficient":
        messages.append("coverage status is sufficient while missing lead days are present")
    if fallback_used and "forecast" in source_label.lower():
        messages.append("fallback static rainfall is labelled as forecast rainfall")
    if record_type == "forecast" or (coverage_days or 0) > 0:
        for field in CLIMATE_EVIDENCE_FORECAST_FIELDS:
            if evidence.get(field) in (None, ""):
                messages.append(f"forecast evidence is missing {field}")
    return messages


def _climate_evidence_warning_messages(evidence: dict) -> list[str]:
    if evidence.get("record_type") == "unavailable" or evidence.get("climate_coverage_status") == "unavailable":
        return ["climate evidence is unavailable; horizon support cannot be independently verified"]
    return []


def _forecast_evidence_present(values: dict, forecast_lineage: dict) -> bool:
    forecast_totals = [
        values.get("forecast_rainfall_total_day_1_to_7"),
        values.get("forecast_rainfall_total_day_8_to_14"),
        values.get("forecast_rainfall_unsplit_aggregate_mm"),
    ]
    return bool(
        (_safe_int(values.get("forecast_coverage_days")) or 0) > 0
        or (_safe_int(forecast_lineage.get("selected_record_count")) or 0) > 0
        or _forecast_lead_days(values, forecast_lineage)
        or forecast_lineage.get("selected_issue_time")
        or any((_safe_float(value) or 0.0) > 0 for value in forecast_totals)
    )


def _check_feature_climate_coverage_consistency(rows: list[FeatureDatasetRow]) -> list[dict]:
    issues = []
    for row in rows:
        values = _as_dict(row.feature_values)
        claimed_horizon = _safe_int(values.get("claimed_forecast_horizon_days"))
        covered_days = _forecast_lead_days(values, _source_lineage(values, "forecast_rainfall"))
        expected_missing_days = _expected_missing_lead_days(covered_days, claimed_horizon)
        actual_missing_days = _as_int_list(values.get("forecast_missing_lead_days"))
        coverage_days = _safe_int(values.get("forecast_coverage_days"))
        sufficient = values.get("claimed_lead_time_climate_coverage_sufficient")
        status = str(values.get("climate_coverage_status") or "")
        messages = []
        if claimed_horizon is None:
            messages.append("claimed forecast horizon is missing")
        elif claimed_horizon < 1 or claimed_horizon > 14:
            messages.append("claimed forecast horizon is outside the supported 1-14 day range")
        if coverage_days is None:
            messages.append("forecast coverage days are missing")
        elif coverage_days != len([day for day in covered_days if claimed_horizon is None or day <= claimed_horizon]):
            messages.append("forecast coverage days do not match the covered lead-day list")
        if claimed_horizon is not None and actual_missing_days != expected_missing_days:
            messages.append("forecast missing lead days are not the complement of covered lead days")
        expected_sufficient = bool(claimed_horizon and not expected_missing_days and _forecast_evidence_present(values, _source_lineage(values, "forecast_rainfall")))
        if sufficient is not expected_sufficient:
            messages.append("claimed climate coverage sufficiency does not match lead-day coverage")
        if status == "sufficient" and not expected_sufficient:
            messages.append("climate coverage status is sufficient but lead-day coverage is insufficient")
        if messages:
            issues.append(
                _row_context(
                    row,
                    check_id="climate_coverage_arithmetic_consistent",
                    severity="fail",
                    message="; ".join(messages),
                )
            )
    return issues


def _feature_rows(*, feature_dataset_ref: str | None = None) -> list[FeatureDatasetRow]:
    datasets = FeatureDataset.objects.filter(schema_version=LEAD_TIME_FEATURE_SCHEMA_VERSION)
    if feature_dataset_ref:
        datasets = datasets.filter(dataset_ref=feature_dataset_ref)
    return list(
        FeatureDatasetRow.objects.filter(dataset__in=datasets)
        .select_related("dataset", "ward")
        .order_by("dataset_id", "id")
    )


def _model_runs(*, model_run_id: int | None = None) -> list[ModelRun]:
    queryset = ModelRun.objects.filter(status=ModelRun.STATUS_SUCCESS).order_by("id")
    if model_run_id is not None:
        queryset = queryset.filter(id=model_run_id)
    runs = list(queryset)
    if model_run_id is not None:
        return runs
    return [run for run in runs if _model_run_needs_promotion_audit(run)]


def _model_run_needs_promotion_audit(model_run: ModelRun) -> bool:
    metadata = model_run.metadata or {}
    metrics = model_run.evaluation_metrics or {}
    return bool(
        metrics.get("temporal_backtest_report")
        or metrics.get("climate_coverage_gate_passed") is not None
        or metadata.get("phase_4_promotion_evidence_persisted")
        or metadata.get("phase_4_promotion_gates_passed")
        or metadata.get("promotion_target") == "live_baseline"
    )


def _check_forecast_issue_time(rows: list[FeatureDatasetRow]) -> list[dict]:
    issues = []
    for row in rows:
        values = _as_dict(row.feature_values)
        forecast_lineage = _source_lineage(values, "forecast_rainfall")
        if not _forecast_evidence_present(values, forecast_lineage):
            continue
        issue_time = _parse_datetime(forecast_lineage.get("selected_issue_time") or values.get("issue_time"))
        if issue_time is None:
            issues.append(
                _row_context(
                    row,
                    check_id="forecast_feature_issue_time_present",
                    severity="fail",
                    message="Forecast feature evidence exists without a selected forecast issue time.",
                )
            )
    return issues


def _check_forecast_lead_days_within_provider_horizon(rows: list[FeatureDatasetRow]) -> list[dict]:
    issues = []
    for row in rows:
        values = _as_dict(row.feature_values)
        forecast_lineage = _source_lineage(values, "forecast_rainfall")
        if not _forecast_evidence_present(values, forecast_lineage):
            continue
        lead_days = _forecast_lead_days(values, forecast_lineage)
        provider_horizon = _safe_int(forecast_lineage.get("max_forecast_horizon_days")) or _safe_int(
            values.get("forecast_horizon_days")
        )
        max_contract_lead_day = _safe_int(forecast_lineage.get("max_contract_lead_day"))
        effective_horizon = provider_horizon or max_contract_lead_day
        out_of_supported_range = [day for day in lead_days if day < 1 or day > 14]
        outside_provider_horizon = [
            day for day in lead_days if effective_horizon is not None and day > effective_horizon
        ]
        if out_of_supported_range or outside_provider_horizon:
            issues.append(
                _row_context(
                    row,
                    check_id="forecast_lead_days_within_provider_horizon",
                    severity="fail",
                    message=(
                        "Forecast covered lead days exceed the supported 1-14 day policy range "
                        "or the provider horizon recorded in lineage."
                    ),
                )
            )
        elif lead_days and effective_horizon is None:
            issues.append(
                _row_context(
                    row,
                    check_id="forecast_provider_horizon_present",
                    severity="warning",
                    message="Forecast lead days are present, but provider horizon lineage is missing.",
                )
            )
    return issues


def _check_future_observed_rainfall_not_used(rows: list[FeatureDatasetRow]) -> list[dict]:
    issues = []
    for row in rows:
        values = _as_dict(row.feature_values)
        leakage_proof = _as_dict(values.get("leakage_proof"))
        rainfall_lineage = _source_lineage(values, "rainfall")
        source_cutoff = _parse_datetime(
            values.get("source_cutoff_timestamp") or leakage_proof.get("source_cutoff_timestamp")
        )
        max_observed_timestamp = _parse_datetime(
            leakage_proof.get("max_observed_rainfall_timestamp")
            or leakage_proof.get("max_rainfall_source_timestamp")
            or rainfall_lineage.get("max_source_timestamp")
        )
        observed_totals = [
            _safe_float(values.get("observed_rainfall_total_3d")) or 0.0,
            _safe_float(values.get("observed_rainfall_total_7d")) or 0.0,
            _safe_float(values.get("observed_rainfall_total_14d")) or 0.0,
        ]
        if leakage_proof.get("future_observed_climate_used") is True:
            issues.append(
                _row_context(
                    row,
                    check_id="future_observed_rainfall_not_used",
                    severity="fail",
                    message="Feature leakage proof says future observed climate was used.",
                )
            )
            continue
        if source_cutoff and max_observed_timestamp and max_observed_timestamp >= source_cutoff and any(observed_totals):
            issues.append(
                _row_context(
                    row,
                    check_id="future_observed_rainfall_not_used",
                    severity="fail",
                    message="Observed rainfall totals include a source timestamp at or after the prediction cutoff.",
                )
            )
    return issues


def _check_fallback_static_not_presented_as_live_forecast(rows: list[FeatureDatasetRow]) -> list[dict]:
    issues = []
    for row in rows:
        values = _as_dict(row.feature_values)
        forecast_lineage = _source_lineage(values, "forecast_rainfall")
        fallback_lineage = _source_lineage(values, "fallback_static_rainfall")
        climate_lineage = _source_lineage(values, "climate_coverage")
        caveats = [
            *_as_list(values.get("climate_coverage_caveats")),
            *_as_list(climate_lineage.get("caveats")),
        ]
        fallback_used = bool(
            values.get("fallback_static_rainfall_used")
            or (_safe_int(fallback_lineage.get("record_count")) or 0) > 0
            or climate_lineage.get("fallback_static_rainfall_used")
        )
        if not fallback_used:
            continue
        forecast_record_count = _safe_int(forecast_lineage.get("selected_record_count")) or 0
        forecast_coverage_days = _safe_int(values.get("forecast_coverage_days")) or 0
        label = str(
            values.get("observed_vs_forecast_source_label")
            or climate_lineage.get("observed_vs_forecast_source_label")
            or ""
        ).lower()
        record_type = str(values.get("record_type") or climate_lineage.get("record_type") or "").lower()
        fallback_only = forecast_record_count == 0 and forecast_coverage_days == 0
        masquerades_as_forecast = (
            "forecast" in label
            or record_type == "forecast"
            or values.get("claimed_lead_time_climate_coverage_sufficient") is True
            or values.get("climate_coverage_status") == "sufficient"
        )
        if fallback_only and masquerades_as_forecast:
            issues.append(
                _row_context(
                    row,
                    check_id="fallback_static_not_presented_as_live_forecast",
                    severity="fail",
                    message="Fallback-only climate evidence is labelled as forecast or sufficient live coverage.",
                )
            )
            continue
        if "fallback_static_rainfall_present_not_live_forecast" not in caveats:
            issues.append(
                _row_context(
                    row,
                    check_id="fallback_static_warning_present",
                    severity="fail",
                    message="Fallback static rainfall is present without the required not-live-forecast caveat.",
                )
            )
    return issues


def _check_promotion_reports_include_climate_coverage_summary(model_runs: list[ModelRun]) -> list[dict]:
    issues = []
    for model_run in model_runs:
        metadata = model_run.metadata or {}
        metrics = model_run.evaluation_metrics or {}
        report = _as_dict(metrics.get("temporal_backtest_report"))
        report_summary = _as_dict(report.get("climate_coverage_summary"))
        validation_summary = _as_dict(report.get("validation_climate_coverage_summary"))
        metric_summary = _as_dict(metrics.get("climate_coverage_summary"))
        metric_validation_summary = _as_dict(metrics.get("validation_climate_coverage_summary"))
        metadata_summary = _as_dict(metadata.get("climate_coverage_summary"))
        metadata_gate = _as_dict(metadata.get("climate_coverage_gate"))
        metadata_validation_summary = _as_dict(metadata_gate.get("validation_summary"))
        missing = []
        if not report_summary:
            missing.append("temporal_backtest_report.climate_coverage_summary")
        if not validation_summary:
            missing.append("temporal_backtest_report.validation_climate_coverage_summary")
        if not metric_summary:
            missing.append("evaluation_metrics.climate_coverage_summary")
        if not metric_validation_summary:
            missing.append("evaluation_metrics.validation_climate_coverage_summary")
        if metrics.get("climate_coverage_gate_passed") is None:
            missing.append("evaluation_metrics.climate_coverage_gate_passed")
        if not metadata_summary:
            missing.append("metadata.climate_coverage_summary")
        if not metadata_validation_summary:
            missing.append("metadata.climate_coverage_gate.validation_summary")
        if metadata.get("promotion_target") == "live_baseline" and metrics.get("climate_coverage_gate_passed") is not True:
            missing.append("live_baseline.climate_coverage_gate_passed_true")
        if missing:
            issues.append(
                _model_run_context(
                    model_run,
                    check_id="promotion_report_climate_coverage_summary_present",
                    severity="fail",
                    message="Promotion evidence is missing climate coverage fields: " + ", ".join(missing),
                )
            )
    return issues


def _required_climate_evidence_missing(evidence: dict) -> list[str]:
    return [field for field in CLIMATE_EVIDENCE_REQUIRED_FIELDS if field not in evidence]


def _check_risk_model_evidence_source_separation() -> tuple[list[dict], int]:
    issues = []
    risk_scores = list(
        RiskScore.objects.filter(source=RiskScore.SOURCE_MODEL)
        .exclude(decision_policy={})
        .select_related("ward", "model_run")
        .order_by("id")
    )
    for risk_score in risk_scores:
        climate_evidence = _as_dict(_as_dict(_as_dict(risk_score.decision_policy).get("inputs")).get("climate_coverage"))
        messages = _climate_evidence_consistency_messages(climate_evidence)
        if messages:
            issues.append(
                _risk_score_context(
                    risk_score,
                    check_id="model_evidence_climate_source_separation_present",
                    severity="fail",
                    message="RiskScore decision policy climate evidence is inconsistent: " + "; ".join(messages),
                )
            )
            continue
        warning_messages = _climate_evidence_warning_messages(climate_evidence)
        if warning_messages:
            issues.append(
                _risk_score_context(
                    risk_score,
                    check_id="model_evidence_climate_source_separation_present",
                    severity="warning",
                    message="RiskScore decision policy climate evidence is incomplete: "
                    + "; ".join(warning_messages),
                )
            )
    return issues, len(risk_scores)


def _check_alert_payload_climate_evidence_consistency() -> tuple[list[dict], int]:
    issues = []
    alerts = list(
        Alert.objects.filter(risk_score__isnull=False)
        .select_related("ward", "risk_score")
        .order_by("id")
    )
    for alert in alerts:
        metadata = _as_dict(alert.guided_request_metadata)
        climate_evidence = _as_dict(metadata.get("climate_evidence"))
        messages = _climate_evidence_consistency_messages(climate_evidence)
        if messages:
            issues.append(
                _alert_context(
                    alert,
                    check_id="frontend_climate_horizon_payload_fields_present",
                    severity="fail",
                    message="Alert payload climate evidence is inconsistent or incomplete: " + "; ".join(messages),
                )
            )
            continue
        warning_messages = _climate_evidence_warning_messages(climate_evidence)
        if warning_messages:
            issues.append(
                _alert_context(
                    alert,
                    check_id="frontend_climate_horizon_payload_fields_present",
                    severity="warning",
                    message="Alert payload climate evidence is incomplete: " + "; ".join(warning_messages),
                )
            )
            continue
        if climate_evidence.get("fallback_static_rainfall_used") and "forecast" in str(
            climate_evidence.get("observed_vs_forecast_source_label") or ""
        ).lower():
            issues.append(
                _alert_context(
                    alert,
                    check_id="frontend_climate_horizon_payload_fields_present",
                    severity="fail",
                    message="Alert payload labels fallback static rainfall as forecast rainfall.",
                )
            )
    return issues, len(alerts)


def _check(
    *,
    check_id: str,
    title: str,
    issues: list[dict],
    scanned_count: int,
    empty_warning: str,
) -> dict:
    failed = [issue for issue in issues if issue.get("severity") == "fail"]
    warnings = [issue for issue in issues if issue.get("severity") == "warning"]
    if failed:
        status = "fail"
    elif warnings or scanned_count == 0:
        status = "warning"
    else:
        status = "pass"
    return {
        "id": check_id,
        "title": title,
        "status": status,
        "scanned_count": scanned_count,
        "issue_count": len(issues),
        "fail_count": len(failed),
        "warning_count": len(warnings),
        "summary": empty_warning if scanned_count == 0 else "Check passed." if status == "pass" else "Issues found.",
        "issues": issues[:50],
    }


def build_climate_horizon_monitoring_audit(
    *,
    feature_dataset_ref: str | None = None,
    model_run_id: int | None = None,
) -> dict:
    rows = _feature_rows(feature_dataset_ref=feature_dataset_ref)
    model_runs = _model_runs(model_run_id=model_run_id)
    risk_issues, risk_score_count = _check_risk_model_evidence_source_separation()
    alert_issues, alert_count = _check_alert_payload_climate_evidence_consistency()

    checks = [
        _check(
            check_id="climate_coverage_arithmetic_consistent",
            title="Climate coverage arithmetic consistency",
            issues=_check_feature_climate_coverage_consistency(rows),
            scanned_count=len(rows),
            empty_warning="No Phase 2 lead-time feature rows are available to audit.",
        ),
        _check(
            check_id="forecast_feature_issue_time_present",
            title="Forecast feature issue time",
            issues=_check_forecast_issue_time(rows),
            scanned_count=len(rows),
            empty_warning="No Phase 2 lead-time feature rows are available to audit.",
        ),
        _check(
            check_id="forecast_lead_days_within_provider_horizon",
            title="Forecast lead days within provider horizon",
            issues=_check_forecast_lead_days_within_provider_horizon(rows),
            scanned_count=len(rows),
            empty_warning="No Phase 2 lead-time feature rows are available to audit.",
        ),
        _check(
            check_id="future_observed_rainfall_not_used",
            title="Observed future rainfall cutoff",
            issues=_check_future_observed_rainfall_not_used(rows),
            scanned_count=len(rows),
            empty_warning="No Phase 2 lead-time feature rows are available to audit.",
        ),
        _check(
            check_id="fallback_static_not_presented_as_live_forecast",
            title="Fallback static source display",
            issues=_check_fallback_static_not_presented_as_live_forecast(rows),
            scanned_count=len(rows),
            empty_warning="No Phase 2 lead-time feature rows are available to audit.",
        ),
        _check(
            check_id="promotion_report_climate_coverage_summary_present",
            title="Promotion report climate coverage summary",
            issues=_check_promotion_reports_include_climate_coverage_summary(model_runs),
            scanned_count=len(model_runs),
            empty_warning="No successful model runs with Phase 4 promotion evidence are available to audit.",
        ),
        _check(
            check_id="model_evidence_climate_source_separation_present",
            title="Model evidence climate source separation",
            issues=risk_issues,
            scanned_count=risk_score_count,
            empty_warning="No model risk scores with decision-policy evidence are available to audit.",
        ),
        _check(
            check_id="frontend_climate_horizon_payload_fields_present",
            title="Frontend climate horizon payload",
            issues=alert_issues,
            scanned_count=alert_count,
            empty_warning="No linked alert payloads are available to audit.",
        ),
    ]
    issues = [issue for check in checks for issue in check["issues"]]
    if any(check["status"] == "fail" for check in checks):
        overall_status = "fail"
    elif any(check["status"] == "warning" for check in checks):
        overall_status = "warning"
    else:
        overall_status = "pass"

    return {
        "audit_name": CLIMATE_HORIZON_AUDIT_NAME,
        "schema_version": CLIMATE_HORIZON_AUDIT_SCHEMA_VERSION,
        "overall_status": overall_status,
        "record_totals": {
            "feature_rows_scanned": len(rows),
            "promotion_model_runs_scanned": len(model_runs),
            "risk_scores_with_decision_policy_scanned": risk_score_count,
            "linked_alert_payloads_scanned": alert_count,
        },
        "filters": {
            "feature_dataset_ref": feature_dataset_ref or "",
            "model_run_id": model_run_id,
        },
        "checks": checks,
        "issues": issues,
        "operator_guidance": {
            "phase_5_exit_criteria": (
                "Climate horizon audit passes, model evidence includes climate source separation, "
                "and frontend alert payloads carry horizon caveats consistently."
            ),
            "strict_command": "python manage.py audit_climate_horizon --strict",
        },
    }


def backfill_alert_climate_evidence(*, dry_run: bool = True, force: bool = False, limit: int | None = None) -> dict:
    alerts = (
        Alert.objects.filter(risk_score__isnull=False)
        .select_related("risk_score", "ward")
        .order_by("id")
    )
    if limit is not None:
        alerts = alerts[:limit]

    scanned_count = 0
    update_count = 0
    skipped_count = 0
    examples = []
    for alert in alerts:
        scanned_count += 1
        metadata = _as_dict(alert.guided_request_metadata)
        current_evidence = _as_dict(metadata.get("climate_evidence"))
        current_messages = _climate_evidence_consistency_messages(current_evidence)
        if current_evidence and not current_messages and not force:
            skipped_count += 1
            continue
        repaired_evidence = _climate_evidence_for_riskscore(alert.risk_score)
        repaired_messages = _climate_evidence_consistency_messages(repaired_evidence)
        if repaired_messages:
            skipped_count += 1
            examples.append(
                {
                    "alert_id": alert.id,
                    "public_id": str(alert.public_id),
                    "status": "skipped_repaired_evidence_inconsistent",
                    "messages": repaired_messages,
                }
            )
            continue
        update_count += 1
        examples.append(
            {
                "alert_id": alert.id,
                "public_id": str(alert.public_id),
                "status": "would_update" if dry_run else "updated",
                "record_type": repaired_evidence.get("record_type"),
                "climate_coverage_status": repaired_evidence.get("climate_coverage_status"),
            }
        )
        if dry_run:
            continue
        alert.guided_request_metadata = {
            **metadata,
            "climate_evidence": repaired_evidence,
            "climate_evidence_backfill": {
                "schema_version": CLIMATE_HORIZON_AUDIT_SCHEMA_VERSION,
                "backfilled_at": timezone.now().isoformat(),
                "source": "audit_climate_horizon_backfill",
                "force": force,
            },
        }
        alert.save(update_fields=["guided_request_metadata"])

    return {
        "schema_version": CLIMATE_HORIZON_AUDIT_SCHEMA_VERSION,
        "dry_run": dry_run,
        "force": force,
        "scanned_count": scanned_count,
        "updated_count": update_count,
        "skipped_count": skipped_count,
        "examples": examples[:50],
    }
