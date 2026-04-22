from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MetricDefinition:
    name: str
    category: str
    metric_type: str
    unit: str
    source: str
    description: str


@dataclass(frozen=True)
class EventClassification:
    event_name: str
    classification: str
    durable: bool
    intended_use: str


@dataclass(frozen=True)
class AuditDefinition:
    action_name: str
    domain_area: str
    target_entity: str
    actor_required: bool
    reason_required: bool
    minimum_metadata: tuple[str, ...]
    rationale: str


@dataclass(frozen=True)
class RunbookInputDefinition:
    input_name: str
    incident_area: str
    input_type: str
    source: str
    purpose: str


@dataclass(frozen=True)
class RecoveryVisibilityDefinition:
    workflow_name: str
    stage: str
    required_signals: tuple[str, ...]
    required_records: tuple[str, ...]
    rationale: str


OPERATIONAL_METRICS: tuple[MetricDefinition, ...] = (
    MetricDefinition(
        name="http_requests_total",
        category="api",
        metric_type="counter",
        unit="requests",
        source="risk.request",
        description="Count all API requests by method, path family, and status class.",
    ),
    MetricDefinition(
        name="http_request_duration_ms",
        category="api",
        metric_type="histogram",
        unit="milliseconds",
        source="risk.request",
        description="Track request latency distribution for authenticated and public endpoints.",
    ),
    MetricDefinition(
        name="auth_login_attempts_total",
        category="auth",
        metric_type="counter",
        unit="attempts",
        source="accounts.audit",
        description="Count successful and failed login attempts.",
    ),
    MetricDefinition(
        name="auth_login_cooldowns_total",
        category="auth",
        metric_type="counter",
        unit="cooldowns",
        source="accounts.views",
        description="Count login attempts blocked by temporary cooldown after repeated failures.",
    ),
    MetricDefinition(
        name="auth_refresh_attempts_total",
        category="auth",
        metric_type="counter",
        unit="attempts",
        source="accounts.audit",
        description="Count successful and failed token refresh attempts.",
    ),
    MetricDefinition(
        name="auth_account_actions_total",
        category="auth",
        metric_type="counter",
        unit="events",
        source="accounts.audit",
        description="Track password changes, registrations, deactivations, and reactivations.",
    ),
    MetricDefinition(
        name="sync_payloads_processed_total",
        category="sync",
        metric_type="counter",
        unit="payloads",
        source="risk.services",
        description="Count CHV sync payloads processed successfully.",
    ),
    MetricDefinition(
        name="sync_payload_replays_total",
        category="sync",
        metric_type="counter",
        unit="payloads",
        source="risk.services",
        description="Count replayed sync submissions detected by idempotency logic.",
    ),
    MetricDefinition(
        name="sync_processing_failures_total",
        category="sync",
        metric_type="counter",
        unit="failures",
        source="risk.services",
        description="Track payload processing failures in offline sync ingestion.",
    ),
    MetricDefinition(
        name="triage_sessions_created_total",
        category="triage",
        metric_type="counter",
        unit="sessions",
        source="risk.services",
        description="Count triage sessions created across API, USSD, and sync channels.",
    ),
    MetricDefinition(
        name="triage_referrals_total",
        category="triage",
        metric_type="counter",
        unit="referrals",
        source="risk.services",
        description="Count triage outcomes that require referral escalation.",
    ),
    MetricDefinition(
        name="ussd_requests_total",
        category="ussd",
        metric_type="counter",
        unit="requests",
        source="risk.views",
        description="Count public USSD requests by menu branch and outcome.",
    ),
    MetricDefinition(
        name="ussd_invalid_option_total",
        category="ussd",
        metric_type="counter",
        unit="requests",
        source="risk.views",
        description="Track invalid or malformed USSD interactions.",
    ),
    MetricDefinition(
        name="rainfall_ingestion_runs_total",
        category="forecasting",
        metric_type="counter",
        unit="runs",
        source="risk.ml.ingestion",
        description="Count rainfall ingestion runs by outcome and source mode.",
    ),
    MetricDefinition(
        name="risk_model_runs_total",
        category="forecasting",
        metric_type="counter",
        unit="runs",
        source="risk.ml.pipeline",
        description="Count model runs by status and model version.",
    ),
    MetricDefinition(
        name="risk_scores_generated_total",
        category="forecasting",
        metric_type="counter",
        unit="scores",
        source="risk.ml.pipeline",
        description="Count generated risk scores by ward and risk level.",
    ),
    MetricDefinition(
        name="alerts_created_total",
        category="alerts",
        metric_type="counter",
        unit="alerts",
        source="risk.services",
        description="Count alerts created by channel and risk level.",
    ),
    MetricDefinition(
        name="alert_delivery_attempts_total",
        category="alerts",
        metric_type="counter",
        unit="attempts",
        source="risk.tasks",
        description="Track alert delivery attempts by channel, provider, and result.",
    ),
    MetricDefinition(
        name="alert_delivery_retry_pending_total",
        category="alerts",
        metric_type="gauge",
        unit="alerts",
        source="risk.models",
        description="Track how many alerts are waiting for retry.",
    ),
    MetricDefinition(
        name="access_request_submissions_total",
        category="auth",
        metric_type="counter",
        unit="requests",
        source="accounts.views",
        description="Count accepted public access-request submissions.",
    ),
    MetricDefinition(
        name="access_request_duplicates_suppressed_total",
        category="auth",
        metric_type="counter",
        unit="requests",
        source="accounts.views",
        description="Count duplicate public access requests suppressed within the configured cooling-off window.",
    ),
    MetricDefinition(
        name="access_request_suspicious_rejections_total",
        category="auth",
        metric_type="counter",
        unit="requests",
        source="accounts.serializers",
        description="Count public access requests rejected by honeypot or suspicious submission-timing rules.",
    ),
)


EVENT_CLASSIFICATIONS: tuple[EventClassification, ...] = (
    EventClassification(
        event_name="request_complete",
        classification="log",
        durable=False,
        intended_use="Transient operational debugging and latency analysis.",
    ),
    EventClassification(
        event_name="auth_audit_event",
        classification="audit_event",
        durable=True,
        intended_use="Durable security and accountability trail for auth-sensitive actions.",
    ),
    EventClassification(
        event_name="domain_audit_event",
        classification="audit_event",
        durable=True,
        intended_use="Durable accountability trail for non-auth operational actions and overrides.",
    ),
    EventClassification(
        event_name="trigger_alerts_started",
        classification="log",
        durable=False,
        intended_use="Execution trace for alert-creation flow.",
    ),
    EventClassification(
        event_name="trigger_alerts_completed",
        classification="log",
        durable=False,
        intended_use="Execution trace for alert-creation completion.",
    ),
    EventClassification(
        event_name="deliver_alert_task_completed",
        classification="log",
        durable=False,
        intended_use="Execution trace for asynchronous alert delivery tasks.",
    ),
    EventClassification(
        event_name="risk_model_run_started",
        classification="log",
        durable=False,
        intended_use="Execution trace for model-run start.",
    ),
    EventClassification(
        event_name="risk_model_run_completed",
        classification="log",
        durable=False,
        intended_use="Execution trace for model-run completion.",
    ),
    EventClassification(
        event_name="future_operational_metric",
        classification="metric",
        durable=False,
        intended_use="Numerical trend and threshold monitoring for dashboards and alerts.",
    ),
)


DOMAIN_AUDIT_INVENTORY: tuple[AuditDefinition, ...] = (
    AuditDefinition(
        action_name="risk_score_manual_override",
        domain_area="forecasting",
        target_entity="RiskScore",
        actor_required=True,
        reason_required=True,
        minimum_metadata=(
            "risk_score_id",
            "ward_public_id",
            "previous_risk_level",
            "new_risk_level",
            "previous_score",
            "new_score",
            "override_reason",
        ),
        rationale="Manual forecast changes can alter downstream alerts and must remain attributable.",
    ),
    AuditDefinition(
        action_name="alert_manual_trigger",
        domain_area="operations",
        target_entity="Alert",
        actor_required=True,
        reason_required=True,
        minimum_metadata=(
            "ward_public_id",
            "risk_score_id",
            "channels",
            "recipient_scope",
            "trigger_reason",
        ),
        rationale="Operator-triggered alerts change response behavior even when automation did not create them.",
    ),
    AuditDefinition(
        action_name="alert_delivery_manual_requeue",
        domain_area="messaging",
        target_entity="Alert",
        actor_required=True,
        reason_required=True,
        minimum_metadata=(
            "alert_id",
            "channel",
            "status_before",
            "attempt_count",
            "requeue_reason",
        ),
        rationale="Manual replay of delivery work must be distinguishable from automatic retry behavior.",
    ),
    AuditDefinition(
        action_name="ingestion_run_manual_correction",
        domain_area="forecasting",
        target_entity="IngestionRun",
        actor_required=True,
        reason_required=True,
        minimum_metadata=(
            "ingestion_run_id",
            "run_type",
            "source_mode",
            "affected_wards",
            "correction_reason",
        ),
        rationale="Corrections to source or provenance data can change how later forecasts are interpreted.",
    ),
    AuditDefinition(
        action_name="model_run_manual_backfill",
        domain_area="forecasting",
        target_entity="ModelRun",
        actor_required=True,
        reason_required=True,
        minimum_metadata=(
            "model_run_id",
            "model_version",
            "training_dataset_ref",
            "inference_dataset_ref",
            "backfill_reason",
        ),
        rationale="Backfills and operator-run forecasts affect lineage and must remain explainable later.",
    ),
    AuditDefinition(
        action_name="triage_referral_manual_override",
        domain_area="surveillance",
        target_entity="TriageSession",
        actor_required=True,
        reason_required=True,
        minimum_metadata=(
            "triage_session_id",
            "ward_public_id",
            "previous_referral_needed",
            "new_referral_needed",
            "override_reason",
        ),
        rationale="Changing referral guidance affects frontline care decisions and requires durable accountability.",
    ),
    AuditDefinition(
        action_name="sync_queue_manual_replay",
        domain_area="surveillance",
        target_entity="SyncQueue",
        actor_required=True,
        reason_required=True,
        minimum_metadata=(
            "sync_queue_id",
            "source_device_id",
            "client_submission_id",
            "status_before",
            "replay_reason",
        ),
        rationale="Manual sync replay can create or prevent duplicate field data and must be attributable.",
    ),
    AuditDefinition(
        action_name="response_action_state_override",
        domain_area="operations",
        target_entity="ResponseAction",
        actor_required=True,
        reason_required=True,
        minimum_metadata=(
            "response_action_id",
            "target_scope",
            "previous_status",
            "new_status",
            "override_reason",
        ),
        rationale="Future intervention workflows need accountability when operators change assignment or completion state.",
    ),
)


MINIMUM_RUNBOOK_INPUTS: tuple[RunbookInputDefinition, ...] = (
    RunbookInputDefinition(
        input_name="request_trace_logs",
        incident_area="api",
        input_type="log",
        source="risk.request",
        purpose="Confirm affected endpoints, methods, status classes, and time windows during incident review.",
    ),
    RunbookInputDefinition(
        input_name="auth_audit_events",
        incident_area="security",
        input_type="audit_event",
        source="accounts.AuthAuditEvent",
        purpose="Investigate account misuse, suspicious admin actions, and auth failure spikes.",
    ),
    RunbookInputDefinition(
        input_name="domain_audit_inventory",
        incident_area="operations",
        input_type="audit_policy",
        source="core.observability.DOMAIN_AUDIT_INVENTORY",
        purpose="Identify which non-auth manual actions or overrides should have durable accountability records.",
    ),
    RunbookInputDefinition(
        input_name="api_latency_and_volume_metrics",
        incident_area="api",
        input_type="metric",
        source="core.observability.OPERATIONAL_METRICS",
        purpose="Detect broad request failure, latency regression, or abuse patterns affecting API consumers.",
    ),
    RunbookInputDefinition(
        input_name="sync_processing_metrics",
        incident_area="sync",
        input_type="metric",
        source="core.observability.OPERATIONAL_METRICS",
        purpose="Diagnose replay spikes, ingestion failures, and field-sync disruption.",
    ),
    RunbookInputDefinition(
        input_name="triage_and_referral_metrics",
        incident_area="triage",
        input_type="metric",
        source="core.observability.OPERATIONAL_METRICS",
        purpose="Detect unexpected changes in frontline decision-support volume or referral escalation.",
    ),
    RunbookInputDefinition(
        input_name="ussd_request_metrics_and_logs",
        incident_area="ussd",
        input_type="metric_and_log",
        source="risk.views and core.observability.OPERATIONAL_METRICS",
        purpose="Diagnose low-connectivity flow failures, malformed requests, or abuse on the public USSD path.",
    ),
    RunbookInputDefinition(
        input_name="ingestion_run_records",
        incident_area="forecasting",
        input_type="domain_record",
        source="risk.IngestionRun",
        purpose="Confirm data-source mode, fallback usage, completion state, and affected wards for rainfall ingestion incidents.",
    ),
    RunbookInputDefinition(
        input_name="model_run_records",
        incident_area="forecasting",
        input_type="domain_record",
        source="risk.ModelRun",
        purpose="Trace model execution status, lineage, and dataset references for forecast anomalies.",
    ),
    RunbookInputDefinition(
        input_name="alert_delivery_state",
        incident_area="alerts",
        input_type="domain_record_and_metric",
        source="risk.Alert and core.observability.OPERATIONAL_METRICS",
        purpose="Diagnose queued, retry-pending, failed, or provider-specific alert-delivery incidents.",
    ),
    RunbookInputDefinition(
        input_name="sync_queue_state",
        incident_area="sync",
        input_type="domain_record",
        source="risk.SyncQueue",
        purpose="Inspect pending, processed, failed, and replayed sync submissions during recovery and duplicate-data review.",
    ),
    RunbookInputDefinition(
        input_name="ussd_session_logs",
        incident_area="ussd",
        input_type="domain_record",
        source="risk.UssdSessionLog",
        purpose="Review exact inbound text and returned response strings for USSD troubleshooting.",
    ),
)


RECOVERY_VISIBILITY_REQUIREMENTS: tuple[RecoveryVisibilityDefinition, ...] = (
    RecoveryVisibilityDefinition(
        workflow_name="database_backup",
        stage="backup_execution",
        required_signals=(
            "backup_started_at",
            "backup_completed_at",
            "backup_status",
            "backup_artifact_reference",
        ),
        required_records=(
            "database_engine_version",
            "schema_migration_state",
            "backup_coverage_window",
        ),
        rationale="A backup that cannot be tied to a concrete artifact, time window, and schema state is not operationally trustworthy.",
    ),
    RecoveryVisibilityDefinition(
        workflow_name="database_restore",
        stage="restore_execution",
        required_signals=(
            "restore_started_at",
            "restore_completed_at",
            "restore_status",
            "restore_source_artifact_reference",
        ),
        required_records=(
            "target_environment",
            "database_engine_version",
            "applied_migration_state",
        ),
        rationale="Restores must be attributable to a specific artifact and target environment so failures can be diagnosed, not guessed.",
    ),
    RecoveryVisibilityDefinition(
        workflow_name="post_restore_validation",
        stage="verification",
        required_signals=(
            "application_health_check_result",
            "api_smoke_test_result",
            "restore_validation_completed_at",
        ),
        required_records=(
            "row_count_sanity_summary",
            "critical_model_count_summary",
            "operator_validation_notes",
        ),
        rationale="A restore is incomplete until maintainers can verify the application boots, core APIs respond, and critical records look plausible.",
    ),
    RecoveryVisibilityDefinition(
        workflow_name="recovery_rehearsal",
        stage="drill_review",
        required_signals=(
            "rehearsal_date",
            "recovery_duration",
            "rehearsal_outcome",
        ),
        required_records=(
            "tested_backup_artifact_reference",
            "observed_gaps",
            "follow_up_actions",
        ),
        rationale="Restoreability should be proven through rehearsal evidence, not treated as an assumption until a real incident happens.",
    ),
)
