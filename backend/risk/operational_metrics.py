from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from .models import OperationalMetricDefinition, OperationalMetricDimension


OPERATIONAL_METRIC_SCHEMA_VERSION = "operational-kpi-dictionary-v1"

OPERATIONAL_METRIC_DIMENSIONS = [
    {
        "dimension_key": "date",
        "display_name": "Date",
        "description": "Snapshot date for daily or rolling operational KPI windows.",
        "value_type": OperationalMetricDimension.VALUE_DATE,
        "source_model": "",
    },
    {
        "dimension_key": "ward",
        "display_name": "Ward",
        "description": "Ward associated with the source operational record.",
        "value_type": OperationalMetricDimension.VALUE_FOREIGN_KEY,
        "source_model": "risk.Ward",
    },
    {
        "dimension_key": "sub_county",
        "display_name": "Sub-county",
        "description": "Administrative sub-county snapshot copied from ward or facility context.",
        "value_type": OperationalMetricDimension.VALUE_TEXT,
        "source_model": "risk.Ward",
    },
    {
        "dimension_key": "county",
        "display_name": "County",
        "description": "Administrative county snapshot copied from ward or facility context.",
        "value_type": OperationalMetricDimension.VALUE_TEXT,
        "source_model": "risk.Ward",
    },
    {
        "dimension_key": "facility",
        "display_name": "Facility",
        "description": "Health facility associated with readiness, referral, or response records.",
        "value_type": OperationalMetricDimension.VALUE_FOREIGN_KEY,
        "source_model": "risk.HealthFacility",
    },
    {
        "dimension_key": "chv",
        "display_name": "CHV",
        "description": "Community health volunteer associated with coverage, assignment, or message records.",
        "value_type": OperationalMetricDimension.VALUE_FOREIGN_KEY,
        "source_model": "risk.CHV",
    },
    {
        "dimension_key": "source_channel",
        "display_name": "Source channel",
        "description": "Operational channel such as SMS, dashboard, WhatsApp, USSD, email, or system.",
        "value_type": OperationalMetricDimension.VALUE_ENUM,
        "source_model": "",
        "allowed_values": ["SMS", "DASHBOARD", "WHATSAPP", "USSD", "EMAIL", "SYSTEM"],
    },
    {
        "dimension_key": "action_type",
        "display_name": "Action type",
        "description": "Preparedness action or task type used for response-performance KPIs.",
        "value_type": OperationalMetricDimension.VALUE_ENUM,
        "source_model": "risk.PreparednessAction",
    },
    {
        "dimension_key": "alert_severity",
        "display_name": "Alert severity",
        "description": "Backend alert or workflow severity bucket at the time the KPI source was created.",
        "value_type": OperationalMetricDimension.VALUE_ENUM,
        "source_model": "risk.AlertWorkflowState",
        "allowed_values": ["HIGH", "MEDIUM", "REVIEW"],
    },
    {
        "dimension_key": "model_version",
        "display_name": "Model version",
        "description": "Prediction model version linked to alert or action lineage. This is a dimension, not a model metric.",
        "value_type": OperationalMetricDimension.VALUE_TEXT,
        "source_model": "risk.ModelRun",
    },
]

OPERATIONAL_KPI_DEFINITIONS = [
    {
        "metric_key": "alert_delivery_time_p50_seconds",
        "version": "v1",
        "display_name": "Alert delivery time p50",
        "description": "Median elapsed seconds between alert creation and confirmed delivery timestamp.",
        "metric_group": OperationalMetricDefinition.GROUP_ALERT_DELIVERY,
        "metric_family": OperationalMetricDefinition.FAMILY_OPERATIONAL,
        "value_type": OperationalMetricDefinition.VALUE_DURATION_SECONDS,
        "value_unit": "seconds",
        "owner": "County EOC operations",
        "formula": "percentile_cont(0.50) of Alert.sent_at - Alert.created_at for delivered alerts in the window.",
        "window": "daily with rolling_7d comparison support",
        "source_model": "risk.Alert",
        "source_models": ["risk.Alert"],
        "allowed_dimensions": ["date", "county", "sub_county", "ward", "source_channel", "alert_severity", "model_version"],
        "interpretation": "Operational delivery speed. This must not be shown as model performance.",
    },
    {
        "metric_key": "alert_delivery_time_p95_seconds",
        "version": "v1",
        "display_name": "Alert delivery time p95",
        "description": "Ninety-fifth percentile elapsed seconds between alert creation and confirmed delivery timestamp.",
        "metric_group": OperationalMetricDefinition.GROUP_ALERT_DELIVERY,
        "metric_family": OperationalMetricDefinition.FAMILY_OPERATIONAL,
        "value_type": OperationalMetricDefinition.VALUE_DURATION_SECONDS,
        "value_unit": "seconds",
        "owner": "County EOC operations",
        "formula": "percentile_cont(0.95) of Alert.sent_at - Alert.created_at for delivered alerts in the window.",
        "window": "daily with rolling_7d comparison support",
        "source_model": "risk.Alert",
        "source_models": ["risk.Alert"],
        "allowed_dimensions": ["date", "county", "sub_county", "ward", "source_channel", "alert_severity", "model_version"],
        "interpretation": "Tail-latency operational delivery speed. This must not be shown as model performance.",
    },
    {
        "metric_key": "alerts_delivered_under_5m_pct",
        "version": "v1",
        "display_name": "Alerts delivered under 5 minutes",
        "description": "Percent of delivered alerts whose delivery timestamp is within five minutes of creation.",
        "metric_group": OperationalMetricDefinition.GROUP_ALERT_DELIVERY,
        "metric_family": OperationalMetricDefinition.FAMILY_OPERATIONAL,
        "value_type": OperationalMetricDefinition.VALUE_PERCENT,
        "value_unit": "percent",
        "owner": "County EOC operations",
        "formula": "100 * count(delivered alerts with Alert.sent_at - Alert.created_at <= 5 minutes) / count(delivered alerts).",
        "window": "daily",
        "source_model": "risk.Alert",
        "source_models": ["risk.Alert"],
        "allowed_dimensions": ["date", "county", "sub_county", "ward", "source_channel", "alert_severity", "model_version"],
        "interpretation": "Alert delivery SLA compliance. This excludes queued or failed alerts from the denominator by design.",
    },
    {
        "metric_key": "trigger_activation_rate",
        "version": "v1",
        "display_name": "Trigger activation rate",
        "description": "Percent of eligible high-risk workflow states that activated an alert or response task.",
        "metric_group": OperationalMetricDefinition.GROUP_TRIGGER_ACTIVATION,
        "metric_family": OperationalMetricDefinition.FAMILY_OPERATIONAL,
        "value_type": OperationalMetricDefinition.VALUE_PERCENT,
        "value_unit": "percent",
        "owner": "Surveillance and response coordination",
        "formula": "100 * count(AlertWorkflowState with active alert or preparedness action) / count(eligible high-risk AlertWorkflowState records).",
        "window": "daily",
        "source_model": "risk.AlertWorkflowState",
        "source_models": ["risk.AlertWorkflowState", "risk.Alert", "risk.PreparednessAction"],
        "allowed_dimensions": ["date", "county", "sub_county", "ward", "alert_severity", "model_version"],
        "interpretation": "Measures conversion from warning signal to operational activation, not prediction accuracy.",
    },
    {
        "metric_key": "action_acknowledgement_time_p50_seconds",
        "version": "v1",
        "display_name": "Action acknowledgement time p50",
        "description": "Median seconds from preparedness action creation to first acknowledgement.",
        "metric_group": OperationalMetricDefinition.GROUP_ACTION_COMPLETION,
        "metric_family": OperationalMetricDefinition.FAMILY_OPERATIONAL,
        "value_type": OperationalMetricDefinition.VALUE_DURATION_SECONDS,
        "value_unit": "seconds",
        "owner": "Response task owners",
        "formula": "percentile_cont(0.50) of PreparednessAction.acknowledged_at - PreparednessAction.created_at for acknowledged actions.",
        "window": "daily with rolling_7d comparison support",
        "source_model": "risk.PreparednessAction",
        "source_models": ["risk.PreparednessAction", "risk.PreparednessActionEvent"],
        "allowed_dimensions": ["date", "county", "sub_county", "ward", "facility", "chv", "action_type", "model_version"],
        "interpretation": "Measures response-owner pickup speed after task creation.",
    },
    {
        "metric_key": "action_completion_rate",
        "version": "v1",
        "display_name": "Action completion rate",
        "description": "Percent of due or closed preparedness actions completed with completion evidence.",
        "metric_group": OperationalMetricDefinition.GROUP_ACTION_COMPLETION,
        "metric_family": OperationalMetricDefinition.FAMILY_OPERATIONAL,
        "value_type": OperationalMetricDefinition.VALUE_PERCENT,
        "value_unit": "percent",
        "owner": "Response task owners",
        "formula": "100 * count(PreparednessAction status COMPLETED with substantive evidence) / count(actions due or closed in the window).",
        "window": "daily",
        "source_model": "risk.PreparednessAction",
        "source_models": ["risk.PreparednessAction", "risk.PreparednessActionEvent"],
        "allowed_dimensions": ["date", "county", "sub_county", "ward", "facility", "chv", "action_type", "model_version"],
        "interpretation": "Operational follow-through rate. Cancelled and expired actions stay visible in the denominator.",
    },
    {
        "metric_key": "overdue_action_count",
        "version": "v1",
        "display_name": "Overdue action count",
        "description": "Count of active preparedness actions whose due date or SLA target has passed.",
        "metric_group": OperationalMetricDefinition.GROUP_ACTION_COMPLETION,
        "metric_family": OperationalMetricDefinition.FAMILY_OPERATIONAL,
        "value_type": OperationalMetricDefinition.VALUE_COUNT,
        "value_unit": "actions",
        "owner": "Response task owners",
        "formula": "count(active PreparednessAction records where due_at or sla_target_at is before snapshot time).",
        "window": "point-in-time daily snapshot",
        "source_model": "risk.PreparednessAction",
        "source_models": ["risk.PreparednessAction"],
        "allowed_dimensions": ["date", "county", "sub_county", "ward", "facility", "chv", "action_type", "model_version"],
        "interpretation": "Backlog pressure requiring operational follow-up.",
    },
    {
        "metric_key": "facility_review_completion_rate",
        "version": "v1",
        "display_name": "Facility review completion rate",
        "description": "Percent of facility readiness reviews resolved or dismissed with auditable workflow events.",
        "metric_group": OperationalMetricDefinition.GROUP_FACILITY_PREPAREDNESS,
        "metric_family": OperationalMetricDefinition.FAMILY_OPERATIONAL,
        "value_type": OperationalMetricDefinition.VALUE_PERCENT,
        "value_unit": "percent",
        "owner": "Facility preparedness lead",
        "formula": "100 * count(FacilityReadinessReview closed with event evidence) / count(FacilityReadinessReview records opened in or due by the window).",
        "window": "daily",
        "source_model": "risk.FacilityReadinessReview",
        "source_models": ["risk.FacilityReadinessReview", "risk.FacilityReadinessReviewEvent"],
        "allowed_dimensions": ["date", "county", "sub_county", "ward", "facility", "alert_severity"],
        "interpretation": "Readiness workflow throughput, not a claim that facilities are clinically ready.",
    },
    {
        "metric_key": "chv_active_use_rate",
        "version": "v1",
        "display_name": "CHV active-use rate",
        "description": "Percent of active CHVs with recent assignment, sync, triage, or message activity.",
        "metric_group": OperationalMetricDefinition.GROUP_CHV_ADOPTION,
        "metric_family": OperationalMetricDefinition.FAMILY_OPERATIONAL,
        "value_type": OperationalMetricDefinition.VALUE_PERCENT,
        "value_unit": "percent",
        "owner": "CHV coordination lead",
        "formula": "100 * count(active CHVs with CHVAssignment, CHVMessage, SyncQueue, or TriageSession activity) / count(active CHVs).",
        "window": "rolling_7d",
        "source_model": "risk.CHV",
        "source_models": ["risk.CHV", "risk.CHVAssignment", "risk.CHVMessage", "risk.SyncQueue", "risk.TriageSession"],
        "allowed_dimensions": ["date", "county", "sub_county", "ward", "chv", "source_channel"],
        "interpretation": "Adoption and activity coverage across CHV-facing workflows.",
    },
    {
        "metric_key": "ussd_completion_rate",
        "version": "v1",
        "display_name": "USSD completion rate",
        "description": "Percent of USSD sessions that reach a terminal recommendation or referral outcome.",
        "metric_group": OperationalMetricDefinition.GROUP_USSD_COMPLETION,
        "metric_family": OperationalMetricDefinition.FAMILY_OPERATIONAL,
        "value_type": OperationalMetricDefinition.VALUE_PERCENT,
        "value_unit": "percent",
        "owner": "Digital engagement lead",
        "formula": "100 * count(UssdSessionLog sessions with terminal completion marker or linked TriageSession) / count(distinct UssdSessionLog.session_id).",
        "window": "daily",
        "source_model": "risk.UssdSessionLog",
        "source_models": ["risk.UssdSessionLog", "risk.TriageSession"],
        "allowed_dimensions": ["date", "county", "sub_county", "ward", "source_channel"],
        "interpretation": "USSD journey completion and abandonment monitoring.",
    },
    {
        "metric_key": "households_reached_count",
        "version": "v1",
        "display_name": "Households reached",
        "description": "Count of household-prevention contacts or estimated households reached by outbound response messaging.",
        "metric_group": OperationalMetricDefinition.GROUP_HOUSEHOLD_REACH,
        "metric_family": OperationalMetricDefinition.FAMILY_OPERATIONAL,
        "value_type": OperationalMetricDefinition.VALUE_COUNT,
        "value_unit": "households",
        "owner": "Risk communication lead",
        "formula": "count(delivered CHVMessage or Alert household-prevention records), using explicit completion evidence when available.",
        "window": "daily",
        "source_model": "risk.CHVMessage",
        "source_models": ["risk.CHVMessage", "risk.Alert", "risk.PreparednessAction"],
        "allowed_dimensions": ["date", "county", "sub_county", "ward", "source_channel", "action_type", "model_version"],
        "interpretation": "Reach estimate from operational messaging records; it is not a causal impact claim.",
    },
    {
        "metric_key": "false_alerts_per_completed_response",
        "version": "v1",
        "display_name": "False alerts per completed response",
        "description": "Ratio of completed alert-driven responses whose evaluation window has no outbreak label evidence.",
        "metric_group": OperationalMetricDefinition.GROUP_OUTCOME_FEEDBACK,
        "metric_family": OperationalMetricDefinition.FAMILY_OPERATIONAL,
        "value_type": OperationalMetricDefinition.VALUE_RATIO,
        "value_unit": "ratio",
        "owner": "M&E lead",
        "formula": "count(completed alert-driven responses with no active/watch SurveillanceLabelWindow in evaluation window) / count(completed alert-driven responses).",
        "window": "rolling_28d after label window maturity",
        "source_model": "risk.PreparednessAction",
        "source_models": ["risk.PreparednessAction", "risk.RiskScore", "risk.SurveillanceLabelWindow"],
        "allowed_dimensions": ["date", "county", "sub_county", "ward", "action_type", "alert_severity", "model_version"],
        "interpretation": "Operational outcome review signal. It does not by itself prove a bad prediction or wasted response.",
    },
    {
        "metric_key": "missed_outbreak_without_action_count",
        "version": "v1",
        "display_name": "Missed outbreak without action",
        "description": "Count of active outbreak label windows without prior alert or response action in the operational lead window.",
        "metric_group": OperationalMetricDefinition.GROUP_OUTCOME_FEEDBACK,
        "metric_family": OperationalMetricDefinition.FAMILY_OPERATIONAL,
        "value_type": OperationalMetricDefinition.VALUE_COUNT,
        "value_unit": "label_windows",
        "owner": "M&E lead",
        "formula": "count(active SurveillanceLabelWindow records with no linked Alert or PreparednessAction before or during the configured lead window).",
        "window": "rolling_28d after label window maturity",
        "source_model": "risk.SurveillanceLabelWindow",
        "source_models": ["risk.SurveillanceLabelWindow", "risk.Alert", "risk.PreparednessAction", "risk.RiskScore"],
        "allowed_dimensions": ["date", "county", "sub_county", "ward", "model_version"],
        "interpretation": "Missed operational activation review signal. It is not automatic causal attribution.",
    },
    {
        "metric_key": "source_data_freshness_pass_rate",
        "version": "v1",
        "display_name": "Source data freshness pass rate",
        "description": "Percent of required source feeds whose latest successful heartbeat or ingestion run is within the freshness SLA.",
        "metric_group": OperationalMetricDefinition.GROUP_SOURCE_DATA_HEALTH,
        "metric_family": OperationalMetricDefinition.FAMILY_OPERATIONAL,
        "value_type": OperationalMetricDefinition.VALUE_PERCENT,
        "value_unit": "percent",
        "owner": "Data engineering",
        "formula": "100 * count(required feeds with fresh ETLHeartbeat or successful ingestion run) / count(required feeds).",
        "window": "point-in-time daily snapshot",
        "source_model": "risk.ETLHeartbeat",
        "source_models": [
            "risk.ETLHeartbeat",
            "risk.IngestionRun",
            "risk.SurveillanceIngestionRun",
            "risk.PopulationExposureIngestionRun",
        ],
        "allowed_dimensions": ["date", "source_channel"],
        "interpretation": "Source coverage and freshness guardrail for operational KPI trust.",
    },
]


def validate_operational_metric_dictionary() -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    required_fields = {
        "metric_key",
        "version",
        "display_name",
        "description",
        "metric_group",
        "metric_family",
        "value_type",
        "owner",
        "formula",
        "window",
        "source_model",
        "source_models",
        "allowed_dimensions",
    }
    dimension_keys = {item["dimension_key"] for item in OPERATIONAL_METRIC_DIMENSIONS}
    seen_keys: set[tuple[str, str]] = set()
    seen_groups: set[str] = set()

    for spec in OPERATIONAL_KPI_DEFINITIONS:
        key = spec.get("metric_key", "")
        version = spec.get("version", "")
        identity = (key, version)
        if identity in seen_keys:
            issues.append({"metric_key": key, "issue": "duplicate_metric_key_version"})
        seen_keys.add(identity)
        missing = sorted(field for field in required_fields if not spec.get(field))
        for field in missing:
            issues.append({"metric_key": key, "issue": f"missing_{field}"})
        if spec.get("metric_family") != OperationalMetricDefinition.FAMILY_OPERATIONAL:
            issues.append({"metric_key": key, "issue": "metric_family_must_be_operational"})
        unknown_dimensions = sorted(set(spec.get("allowed_dimensions", [])) - dimension_keys)
        for dimension in unknown_dimensions:
            issues.append({"metric_key": key, "issue": f"unknown_dimension:{dimension}"})
        source_models = spec.get("source_models", [])
        if spec.get("source_model") not in source_models:
            issues.append({"metric_key": key, "issue": "source_model_missing_from_source_models"})
        if spec.get("metric_group"):
            seen_groups.add(spec["metric_group"])

    required_groups = {
        OperationalMetricDefinition.GROUP_ALERT_DELIVERY,
        OperationalMetricDefinition.GROUP_TRIGGER_ACTIVATION,
        OperationalMetricDefinition.GROUP_ACTION_COMPLETION,
        OperationalMetricDefinition.GROUP_CHV_ADOPTION,
        OperationalMetricDefinition.GROUP_FACILITY_PREPAREDNESS,
        OperationalMetricDefinition.GROUP_USSD_COMPLETION,
        OperationalMetricDefinition.GROUP_HOUSEHOLD_REACH,
        OperationalMetricDefinition.GROUP_OUTCOME_FEEDBACK,
        OperationalMetricDefinition.GROUP_SOURCE_DATA_HEALTH,
    }
    for group in sorted(required_groups - seen_groups):
        issues.append({"metric_key": "*", "issue": f"missing_required_group:{group}"})

    return issues


@transaction.atomic
def sync_operational_metric_catalog() -> dict[str, int]:
    issues = validate_operational_metric_dictionary()
    if issues:
        raise ValueError(f"Operational metric dictionary is invalid: {issues}")

    dimension_count = 0
    definition_count = 0
    for dimension in OPERATIONAL_METRIC_DIMENSIONS:
        defaults = {
            "display_name": dimension["display_name"],
            "description": dimension["description"],
            "value_type": dimension["value_type"],
            "source_model": dimension.get("source_model", ""),
            "allowed_values": dimension.get("allowed_values", []),
            "is_active": dimension.get("is_active", True),
            "metadata": {
                "schema_version": OPERATIONAL_METRIC_SCHEMA_VERSION,
                **dimension.get("metadata", {}),
            },
        }
        OperationalMetricDimension.objects.update_or_create(
            dimension_key=dimension["dimension_key"],
            defaults=defaults,
        )
        dimension_count += 1

    for spec in OPERATIONAL_KPI_DEFINITIONS:
        if spec.get("is_active", True):
            OperationalMetricDefinition.objects.filter(
                metric_key=spec["metric_key"],
                is_active=True,
            ).exclude(version=spec["version"]).update(is_active=False, effective_to=timezone.now())
        defaults = {
            "display_name": spec["display_name"],
            "description": spec["description"],
            "metric_group": spec["metric_group"],
            "metric_family": spec["metric_family"],
            "value_type": spec["value_type"],
            "value_unit": spec.get("value_unit", ""),
            "owner": spec["owner"],
            "formula": spec["formula"],
            "window": spec["window"],
            "source_model": spec["source_model"],
            "source_models": spec["source_models"],
            "allowed_dimensions": spec["allowed_dimensions"],
            "interpretation": spec.get("interpretation", ""),
            "is_active": spec.get("is_active", True),
            "metadata": {
                "schema_version": OPERATIONAL_METRIC_SCHEMA_VERSION,
                "phase": "child_plan_4_phase_0",
                "separated_from_model_metrics": True,
                **spec.get("metadata", {}),
            },
        }
        definition, _ = OperationalMetricDefinition.objects.update_or_create(
            metric_key=spec["metric_key"],
            version=spec["version"],
            defaults=defaults,
        )
        if definition.is_active:
            OperationalMetricDefinition.objects.filter(
                metric_key=definition.metric_key,
                is_active=True,
            ).exclude(pk=definition.pk).update(is_active=False, effective_to=definition.effective_from)
        definition_count += 1

    return {"dimensions": dimension_count, "definitions": definition_count}
