import { isStepUpPurpose, requestStepUp, StepUpUnavailableError } from "@/lib/step-up";
import type { StepUpPurpose } from "@/lib/auth";

export type PaginatedResponse<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};

export type WardSummary = {
  id: number;
  public_id: string;
  name: string;
  county: string;
  sub_county: string;
  ward_code: string;
  current_risk_level: "LOW" | "MEDIUM" | "HIGH";
  current_risk_score: number;
  is_active: boolean;
  updated_at: string;
};

export type WardDetailSummary = {
  id: number;
  public_id: string;
  name: string;
  county: string;
  sub_county: string;
  ward_code: string;
  current_risk_level: "LOW" | "MEDIUM" | "HIGH";
  current_risk_score: number;
  predicted_cases: number;
  latest_generated_at: string | null;
  latest_source: string | null;
  latest_model_version: string | null;
  is_active: boolean;
  updated_at: string;
};

export type LatestWardRisk = {
  ward_id: number;
  ward_name: string;
  risk_level: "LOW" | "MEDIUM" | "HIGH" | null;
  risk_score: number | null;
  predicted_cases: number;
  generated_at: string | null;
};

export type AlertWorkflowRecord = {
  id: number;
  public_id: string;
  ward_id: number;
  ward_name: string;
  status: "REVIEW_PENDING" | "QUEUED" | "DELIVERED" | "RETRY_PENDING" | "FAILED" | "RESOLVED";
  decision_mode: OverviewDecisionMode;
  confidence: OverviewTriggerConfidence;
  trigger_severity: OverviewTriggerSeverity;
  alert_delivery_state: OverviewTriggerDeliveryState;
  alert_delivery_label: string;
  risk_level: "LOW" | "MEDIUM" | "HIGH" | null;
  risk_score: number | null;
  predicted_cases: number;
  reason_flagged: string;
  trigger_reason: string;
  recommended_action: string;
  recommended_response: string;
  expected_operational_effect: string;
  rules_basis: OverviewRuleBasis;
  trigger_reason_items: OverviewTriggerReasonItem[];
  eligible_actions: OverviewEligibleAction[];
  active_alert_count: number;
  delivered_alert_count: number;
  retry_pending_alert_count: number;
  failed_alert_count: number;
  queued_alert_count: number;
  triggered_at: string | null;
  latest_risk_update_at: string | null;
  last_manual_request_at: string | null;
  updated_at: string;
};

export type AlertRecord = {
  id: number;
  public_id: string;
  ward: number;
  ward_name: string;
  risk_score: number | null;
  channel: "SMS" | "WHATSAPP" | "DASHBOARD";
  recipient: string;
  message: string;
  status: "QUEUED" | "RETRY_PENDING" | "DELIVERED" | "FAILED";
  delivery_backend: string;
  attempt_count: number;
  max_attempts: number;
  last_attempted_at: string | null;
  next_retry_at: string | null;
  external_id: string;
  sent_at: string | null;
  created_at: string;
  error_message: string;
  privacy_context?: {
    classification: string;
    redacted: boolean;
    reason: string;
  };
};

export type SensitiveExportType = "ALERT_LIST_CSV" | "ALERT_DETAIL_REPORT";
export type SensitiveExportApprovalState = "PENDING" | "APPROVED" | "REJECTED" | "EXPIRED";

export type SensitiveExportRecord = {
  public_id: string;
  export_type: SensitiveExportType;
  requester: number;
  requester_username: string;
  purpose: string;
  filters: Record<string, unknown>;
  sensitive_fields_included: string[];
  approval_state: SensitiveExportApprovalState;
  requires_approval: boolean;
  generated_at: string | null;
  expires_at: string | null;
  approved_by: number | null;
  approved_by_username: string | null;
  approved_at: string | null;
  rejected_by: number | null;
  rejected_by_username: string | null;
  rejected_at: string | null;
  rejection_reason: string;
  generated_filename: string;
  generated_content_type: string;
  payload_sha256: string;
  row_count: number;
  download_count: number;
  download_audit_count: number;
  last_downloaded_at: string | null;
  has_payload: boolean;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type SensitiveExportCreatePayload = {
  export_type: SensitiveExportType;
  purpose: string;
  filters?: Record<string, unknown>;
};

export type SensitiveExportDownloadResponse = {
  public_id: string;
  filename: string;
  content_type: string;
  payload: string;
  payload_sha256: string;
  expires_at: string;
};

export type ChvRecord = {
  id: number;
  name: string;
  phone_number: string;
  language: string;
  is_active: boolean;
  ward: number;
  ward_name: string;
  created_at: string;
};

export type ChvOperationsRecord = {
  id: number;
  public_id: string;
  name: string;
  phone_number: string;
  language: string;
  is_active: boolean;
  ward: number;
  ward_name: string;
  created_at: string;
  last_sync_at: string | null;
  last_activity_at: string | null;
  operational_status: "ACTIVE" | "IDLE" | "OFFLINE";
  sync_health: "ONLINE" | "DELAYED" | "OFFLINE";
  triage_sessions_24h: number;
  referrals_24h: number;
  sync_payloads_24h: number;
  ussd_sessions_24h: number;
  ward_alerts_total: number;
  ward_alerts_delivered: number;
  can_message: boolean;
  message_mode: "SEND" | "QUEUE_ONLY" | "UNAVAILABLE";
  message_delivery_kind: "LIVE" | "SIMULATED" | "QUEUE_ONLY" | "UNAVAILABLE";
  can_view_activity: boolean;
};

export type ChvOfflineAuditStatus = "PASS" | "WARN" | "FAIL";

export type ChvOfflineAuditCheck = {
  key: string;
  title: string;
  status: ChvOfflineAuditStatus;
  count: number;
  summary: string;
  sample_records: Array<Record<string, unknown>>;
};

export type ChvOfflineWardSyncHealth = {
  ward_id: number;
  ward_name: string;
  registered_device_count: number;
  active_device_count: number;
  successful_syncs_24h: number;
  pending_upload_count: number;
  failed_upload_count_24h: number;
  pre_validation_rejection_count_24h: number;
  conflict_count_7d: number;
  last_successful_sync_at: string | null;
  sync_health: "ONLINE" | "DELAYED" | "OFFLINE";
};

export type ChvOfflineSyncDecision = {
  id: number;
  created_at: string | null;
  processed_at: string | null;
  ward_id: number | null;
  ward_name: string;
  upload_type: string;
  status: "PENDING" | "PROCESSED" | "FAILED";
  decision: "ACCEPTED" | "REJECTED" | "PENDING";
  conflict_state: string;
  client_submission_id: string;
  idempotency_key: string;
  download_bundle_version: string;
  domain_record: Record<string, unknown>;
  explanation: string;
};

export type ChvOfflineRejectedSubmissionAudit = {
  public_id: string;
  created_at: string | null;
  ward_id: number | null;
  ward_name: string;
  source_device_id: string;
  client_submission_id: string;
  idempotency_key: string;
  upload_type: string;
  contract_version: string;
  rejection_stage: string;
  error_code: string;
  safe_error_summary: string;
  field_paths: string[];
  status_code: number;
};

export type ChvOfflineMonitoringSnapshot = {
  schema_version: string;
  generated_at: string | null;
  scope: {
    ward_ids: number[];
    ward_count: number;
    window_hours: number;
    audit_window_days: number;
  };
  metrics: {
    registered_chv_devices: number;
    active_chv_devices: number;
    successful_syncs_24h: number;
    failed_syncs_24h: number;
    pre_validation_rejections_24h: number;
    pending_uploads: number;
    stale_guidance_bundles: number;
    conflict_count_7d: number;
    offline_task_completion_latency_minutes: number | null;
  };
  audit_checks: ChvOfflineAuditCheck[];
  sync_health_by_ward: ChvOfflineWardSyncHealth[];
  recent_sync_decisions: ChvOfflineSyncDecision[];
  recent_rejected_submission_audits: ChvOfflineRejectedSubmissionAudit[];
};

export type ChvActivityRecord = {
  public_id: string;
  event_type: string;
  category: "MESSAGE" | "ASSIGNMENT" | "ALERT" | "SYNC" | "TRIAGE" | "STATUS";
  title: string;
  description: string;
  source: string;
  metadata: Record<string, unknown>;
  created_by: number | null;
  created_by_username: string | null;
  created_at: string;
};

export type ChvMessageRecord = {
  public_id: string;
  channel: "SMS";
  message_body: string;
  status: "QUEUED" | "SENT" | "DELIVERED" | "FAILED";
  delivery_kind: "LIVE" | "SIMULATED" | "QUEUE_ONLY" | "UNAVAILABLE";
  delivery_backend: string;
  provider_reference: string;
  failure_reason: string;
  sent_by: number | null;
  sent_by_username: string | null;
  created_at: string;
  updated_at: string;
};

export type CreateChvMessagePayload = {
  message_body: string;
  channel?: "SMS";
};

export type ChvCoverageRequestStatus =
  | "OPEN"
  | "APPROVED"
  | "REJECTED"
  | "IN_PROGRESS"
  | "RESOLVED"
  | "CANCELLED";

export type ChvCoverageRequestPriority = "LOW" | "MEDIUM" | "HIGH";

export type ChvCoverageRequestTriggerSource = "MANUAL" | "ALERT_DRIVEN";

export type ChvCoverageAssignmentStatus = "ACTIVE" | "COMPLETED" | "CANCELLED";

export type ChvCoverageRequestEventAction =
  | "CREATED"
  | "ALERT_LINKAGE_ATTACHED"
  | "ALERT_LINKAGE_REDIRECTED"
  | "APPROVED"
  | "REJECTED"
  | "CANCELLED"
  | "RESOLVED"
  | "OWNERSHIP_CHANGED"
  | "ASSIGNMENT_CREATED"
  | "ASSIGNMENT_COMPLETED"
  | "ASSIGNMENT_CANCELLED";

export type ChvCoverageAssignmentRecord = {
  public_id: string;
  coverage_request: number;
  ward: number;
  ward_name: string;
  ward_public_id: string;
  chv: number;
  chv_name: string;
  chv_phone_number: string;
  assigned_by: number | null;
  assigned_by_username: string | null;
  status: ChvCoverageAssignmentStatus;
  start_at: string | null;
  end_at: string | null;
  notes: string;
  created_at: string;
  updated_at: string;
};

export type ChvCoverageRequestEventRecord = {
  public_id: string;
  action: ChvCoverageRequestEventAction;
  actor: number | null;
  actor_username: string | null;
  assignment: number | null;
  assignment_public_id: string | null;
  old_status: string;
  new_status: string;
  detail: string;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type ChvCoverageRequestRecord = {
  public_id: string;
  ward: number;
  ward_name: string;
  ward_public_id: string;
  requested_by: number | null;
  requested_by_username: string | null;
  status: ChvCoverageRequestStatus;
  priority: ChvCoverageRequestPriority;
  trigger_source: ChvCoverageRequestTriggerSource;
  linked_alert_public_ids: string[];
  linked_alerts_summary: ChvCoverageLinkedAlertSummary[];
  reason: string;
  requested_chv_count: number;
  notes: string;
  assigned_to_user: number | null;
  assigned_to_username: string | null;
  assigned_to_team: string;
  reviewed_by: number | null;
  reviewed_by_username: string | null;
  reviewed_at: string | null;
  review_decision_reason: string;
  expected_response_by: string | null;
  resolved_at: string | null;
  request_age: number;
  is_overdue: boolean;
  sla_status: "ON_TRACK" | "OVERDUE" | "NOT_APPLICABLE";
  assignments: ChvCoverageAssignmentRecord[];
  events: ChvCoverageRequestEventRecord[];
  created_at: string;
  updated_at: string;
};

export type ChvCoverageLinkedAlertSummary = {
  alert_id: number;
  alert_public_id: string;
  ward_id: number | null;
  ward_name: string | null;
  status: AlertRecord["status"];
  channel: AlertRecord["channel"];
  created_at: string;
  sent_at: string | null;
  risk_score: number | null;
};

export type CreateChvCoverageRequestPayload = {
  ward_id: number;
  priority: ChvCoverageRequestPriority;
  reason: string;
  requested_chv_count: number;
  notes?: string;
  trigger_source?: ChvCoverageRequestTriggerSource;
  linked_alert_public_ids?: string[];
};

export type ChvCoverageRequestFromAlertPrefillPayload = {
  alert_public_ids: string[];
};

export type ChvCoverageRequestCreateDefaults = {
  ward_id: number;
  ward_public_id: string;
  ward_name: string;
  trigger_source: ChvCoverageRequestTriggerSource;
  linked_alert_public_ids: string[];
  linked_alerts_summary: ChvCoverageLinkedAlertSummary[];
  priority: ChvCoverageRequestPriority;
  requested_chv_count: number;
  reason: string;
  notes: string;
};

export type ChvCoverageRequestFromAlertPrefillResponse = {
  mode: "CREATE_READY" | "EXISTING_LIVE_REQUEST";
  detail: string;
  create_defaults: ChvCoverageRequestCreateDefaults | null;
  existing_request: ChvCoverageRequestRecord | null;
};

export type AssignChvCoverageRequestPayload = {
  chv_id: number;
  notes?: string;
  start_at?: string;
};

export type FetchChvCoverageRequestsParams = {
  page?: number;
  ward_id?: number;
  status?: ChvCoverageRequestStatus;
  priority?: ChvCoverageRequestPriority;
  trigger_source?: ChvCoverageRequestTriggerSource;
  overdue?: boolean;
  has_linked_alerts?: boolean;
};

export type PreparednessActionType =
  | "chv_follow_up"
  | "household_prevention_message"
  | "facility_ors_review"
  | "facility_staffing_review"
  | "county_escalation"
  | "water_treatment_distribution"
  | "surveillance_follow_up"
  | "field_verification";

export type PreparednessActionSourceTrigger =
  | "manual"
  | "alert"
  | "alert_workflow"
  | "risk_score"
  | "chv_coverage_request"
  | "facility_readiness_review"
  | "facility_update_request"
  | "facility_escalation"
  | "outcome_feedback"
  | "system";

export type PreparednessActionStatus =
  | "DRAFT"
  | "QUEUED"
  | "ASSIGNED"
  | "ACKNOWLEDGED"
  | "IN_PROGRESS"
  | "COMPLETED"
  | "BLOCKED"
  | "CANCELLED"
  | "ESCALATED"
  | "EXPIRED";

export type PreparednessActionPriority = "LOW" | "MEDIUM" | "HIGH" | "URGENT";

export type PreparednessActionEventRecord = {
  public_id: string;
  event_type: string;
  actor: number | null;
  actor_username: string | null;
  old_status: string;
  new_status: string;
  detail: string;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type PreparednessActionRecord = {
  id: number;
  public_id: string;
  action_type: PreparednessActionType;
  source_trigger_type: PreparednessActionSourceTrigger;
  source_trigger_ref: string;
  ward: number;
  ward_name: string;
  ward_public_id: string;
  facility: number | null;
  facility_name: string | null;
  chv: number | null;
  chv_name: string | null;
  alert: number | null;
  alert_public_id: string | null;
  alert_workflow: number | null;
  alert_workflow_public_id: string | null;
  risk_score: number | null;
  model_run: number | null;
  model_run_version: string | null;
  facility_readiness_review: number | null;
  facility_readiness_review_public_id: string | null;
  facility_update_request: number | null;
  facility_update_request_public_id: string | null;
  facility_escalation: number | null;
  facility_escalation_public_id: string | null;
  chv_coverage_request: number | null;
  chv_coverage_request_public_id: string | null;
  status: PreparednessActionStatus;
  priority: PreparednessActionPriority;
  created_by: number | null;
  created_by_username: string | null;
  assigned_to: number | null;
  assigned_to_username: string | null;
  assigned_to_team: string;
  decision_policy_version: string;
  due_at: string | null;
  sla_target_at: string | null;
  acknowledged_at: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
  escalated_at: string | null;
  completion_evidence: Record<string, unknown>;
  cancellation_reason: string;
  escalation_metadata: Record<string, unknown>;
  lineage_metadata: Record<string, unknown>;
  notes: string;
  is_overdue: boolean;
  sla_status: "ON_TRACK" | "OVERDUE" | "NOT_APPLICABLE";
  created_at: string;
  updated_at: string;
  events: PreparednessActionEventRecord[];
};

export type FetchPreparednessActionsParams = {
  page?: number;
  page_size?: number;
  ward_id?: number;
  facility_id?: number;
  chv_id?: number;
  status?: PreparednessActionStatus;
  statuses?: PreparednessActionStatus[];
  action_type?: PreparednessActionType;
  priority?: PreparednessActionPriority;
  source_trigger_type?: PreparednessActionSourceTrigger;
  assigned?: "mine" | "unassigned";
  overdue?: boolean;
  ordering?: string;
};

export type PreparednessActionTransitionPayload = {
  status: PreparednessActionStatus;
  detail?: string;
  assigned_to_id?: number | null;
  assigned_to_team?: string;
  due_at?: string | null;
  sla_target_at?: string | null;
  completion_evidence?: Record<string, unknown>;
  cancellation_reason?: string;
  escalation_metadata?: Record<string, unknown>;
};

export type FacilityRecord = {
  id: number;
  public_id: string;
  name: string;
  facility_code: string;
  ward: number;
  ward_name: string;
  sub_county: string;
  facility_type: string;
  ownership: string;
  level: string;
  ward_risk_level: "LOW" | "MEDIUM" | "HIGH";
  ward_risk_score: number;
  is_active: boolean;
  point: [number, number] | null;
  contact_phone: string;
  updated_at: string;
};

export type ModelRunRecord = {
  id: number;
  model_type: string;
  version: string;
  status: string;
  metrics: Record<string, unknown>;
  metadata: Record<string, unknown>;
  training_window_start: string | null;
  training_window_end: string | null;
  scoring_window_start: string | null;
  scoring_window_end: string | null;
  feature_dataset_ref: string;
  started_at: string;
  completed_at: string | null;
};

export type IngestionRunRecord = {
  id: number;
  run_type: string;
  status: string;
  source_mode: string;
  source_kind: string;
  source_name: string;
  source_priority: number | null;
  requested_wards: string[];
  source_timestamp: string | null;
  freshness_state: string;
  fallback_used: boolean;
  records_seen: number;
  records_loaded: number;
  records_rejected: number;
  operator_note: string;
  results: Record<string, unknown>;
  error_message: string;
  started_at: string;
  completed_at: string | null;
};

export type DashboardNotification = {
  id: number;
  public_id: string;
  external_key: string;
  type:
    | "WARD_RISK_HIGH"
    | "ALERT_FAILED"
    | "ALERT_RETRY_PENDING"
    | "FEED_STALE"
    | "CHV_COVERAGE_REQUEST_STATUS"
    | "OPERATIONAL_KPI_THRESHOLD"
    | "SESSION_REPLAY_DETECTED";
  category:
    | "system_health"
    | "alert_delivery"
    | "trigger_review"
    | "chv_coverage_workflow"
    | "operational_kpi_threshold"
    | "security"
    | "general";
  group_key:
    | "data_freshness"
    | "alert_delivery_failures"
    | "alert_delivery_retries"
    | "chv_coverage_requests"
    | "operational_kpi_thresholds"
    | "session_security"
    | null;
  severity: "INFO" | "WARNING" | "CRITICAL";
  title: string;
  body: string;
  source_system: string;
  source_object_type: string;
  source_object_id: string;
  href: string;
  state: "NEW" | "SEEN" | "ACKNOWLEDGED" | "RESOLVED" | "DISMISSED" | "EXPIRED";
  recipient_scope: "GLOBAL" | "WARD";
  recipient_role: string;
  recipient_user: number | null;
  ward: number | null;
  ward_name: string;
  requires_acknowledgement: boolean;
  dismissible: boolean;
  auto_resolve: boolean;
  pinned_until_actioned: boolean;
  metadata: Record<string, unknown>;
  created_at: string;
  seen_at: string | null;
  acknowledged_at: string | null;
  resolved_at: string | null;
  dismissed_at: string | null;
  expires_at: string | null;
  updated_at: string;
};

export type TopbarFeedStatus = {
  id: "risks" | "alerts" | "facilities";
  label: string;
  latest_timestamp: string | null;
  stale: boolean;
};

export type DashboardFreshnessSummary = {
  last_model_run_at: string | null;
  last_data_sync_at: string | null;
  last_alert_ingestion_at: string | null;
  prediction_generated_at: string | null;
  freshness_state: "fresh" | "delayed" | "stale";
};

export type NotificationSystemStatus = "STABLE" | "DATA_FRESHNESS_DEGRADED" | "ACTION_REQUIRED";

export type TopbarData = {
  notifications: DashboardNotification[];
  unread_count: number;
  highest_unread_severity: "INFO" | "WARNING" | "CRITICAL" | null;
  system_status: NotificationSystemStatus;
  feeds: TopbarFeedStatus[];
  freshness: DashboardFreshnessSummary;
};

export type DashboardNotificationStreamToken = {
  token: string;
  websocket_path: string;
  expires_in_seconds: number;
};

export type DashboardNotificationStreamEvent = {
  event:
    | "notification.connected"
    | "notification.created"
    | "notification.updated"
    | "notification.resolved"
    | "topbar.snapshot";
  notification?: DashboardNotification;
  unread_count: number;
  highest_unread_severity?: "INFO" | "WARNING" | "CRITICAL" | null;
  system_status?: NotificationSystemStatus;
  feeds?: TopbarFeedStatus[];
  freshness?: DashboardFreshnessSummary;
  changed_fields?: string[];
};

export type WardMapGeometry = {
  type: "Polygon" | "MultiPolygon";
  coordinates: number[][][] | number[][][][];
};

export type WardMapPrediction = {
  available: boolean;
  horizon_days: number;
  predicted_risk_level: "LOW" | "MEDIUM" | "HIGH" | null;
  predicted_risk_score: number | null;
  predicted_cases: number;
  prediction_generated_at: string | null;
  prediction_model_version: string | null;
};

export type WardMapFeature = {
  type: "Feature";
  geometry: WardMapGeometry;
  properties: {
    name: string;
    ward_code: string;
    source_name?: string | null;
    source_ward_code?: string | null;
    centroid: [number, number] | null;
    backend_ward_id: number | null;
    backend_public_id: string | null;
    has_backend_ward: boolean;
    matching_source?: "ward_code" | "name" | null;
    current_risk_level: "LOW" | "MEDIUM" | "HIGH" | null;
    current_risk_score: number | null;
    risk_level: "LOW" | "MEDIUM" | "HIGH" | null;
    risk_score: number | null;
    predicted_cases: number;
    risk_generated_at: string | null;
    prediction: WardMapPrediction;
    trend: WardIntelligenceTrend;
    chv_count: number;
    active_chv_count: number;
    alert_count: number;
    facility_count: number;
  };
};

export type WardMapResponse = {
  type: "FeatureCollection";
  metadata: {
    county: string;
    geometry_source: string;
    source_dataset?: string | null;
    source_license?: string | null;
    source_crs?: string | null;
    geometry_feature_count: number;
    expected_ward_count: number;
    missing_source_wards: string[];
    backend_ward_match_count: number;
    backend_ward_code_match_count?: number;
    backend_ward_name_fallback_match_count?: number;
    matching_strategy?: string | null;
    returned_feature_count: number;
    backend_wards_without_geometry: string[];
    placeholder_geometry_detected: boolean;
    geometry_note: string | null;
  };
  features: WardMapFeature[];
};

export type RiskScoreRecord = {
  id: number;
  ward: number;
  ward_name: string;
  model_run: number | null;
  model_run_status: string;
  model_run_version: string;
  score: number;
  risk_level: "LOW" | "MEDIUM" | "HIGH";
  rainfall_mm: number;
  flood_indicator: number;
  predicted_cases: number;
  source: string;
  model_version: string;
  notes: string;
  decision_policy?: Record<string, unknown>;
  generated_at: string;
};

export type WardOperationalEvidenceTone = "success" | "warning" | "danger" | "default";

export type WardOperationalEvidenceBadge = {
  id: string;
  label: string;
  value: string;
  tone: WardOperationalEvidenceTone;
  detail: string;
};

export type ClimateEvidence = {
  schema_version?: string;
  record_type: string;
  source_provider: string;
  observed_vs_forecast_source_label: string;
  issue_time: string | null;
  valid_date: string | null;
  lead_day: number | null;
  forecast_horizon_days: number | null;
  claimed_forecast_horizon_days: number;
  forecast_coverage_days: number;
  forecast_missing_lead_days: number[];
  claimed_lead_time_climate_coverage_sufficient: boolean;
  fallback_static_rainfall_used: boolean;
  climate_source_confidence: number;
  climate_source_confidence_label: string;
  climate_coverage_status: string;
  climate_coverage_caveats: string[];
};

export type WardPredictionOutcomeClassification =
  | "hit"
  | "false_alert"
  | "missed_outbreak"
  | "correct_quiet"
  | "pending_label";

export type WardPredictionLabelHistoryRow = {
  risk_score_id: number;
  prediction_generated_at: string;
  forecast_window_start: string;
  forecast_window_end: string;
  risk_level: "LOW" | "MEDIUM" | "HIGH";
  risk_score: number;
  predicted_cases: number;
  alert_decision: string;
  policy_version: string;
  observed_label: string;
  observed_truth_level: string;
  observed_suspected_cases: number;
  observed_confirmed_cases: number;
  observed_proxy_cases: number;
  label_window_ref: string;
  label_dataset_ref: string;
  classification: WardPredictionOutcomeClassification;
  review_required: boolean;
  confidence_caveat: string;
};

export type WardOutcomeFeedback = {
  mode: string;
  reference_at: string | null;
  model_quality_state: string;
  response_quality_state: string;
  attribution: string;
  accountability_note: string;
  observed_outcome: {
    state: string;
    label: string;
    detail: string;
    observed_label: string;
    observed_truth_level: string;
    suspected_case_count: number;
    confirmed_case_count: number;
  };
  summary: {
    step_count: number;
    recorded_step_count: number;
    downstream_failure_count: number;
    alert_failure_count?: number;
    response_execution_failure_count?: number;
    in_progress_step_count: number;
    review_item_count: number;
  };
  steps: Array<{
    key: string;
    label: string;
    status: "recorded" | "in_progress" | "missing" | "failed" | "not_applicable" | "pending";
    tone: WardOperationalEvidenceTone;
    detail: string;
    occurred_at: string | null;
    evidence_level: string;
    evidence_refs: string[];
  }>;
  review_items: Array<{
    category: string;
    severity: "low" | "medium" | "high" | string;
    title: string;
    detail: string;
    step_keys: string[];
  }>;
  facility_action_evidence: {
    reviews: Array<Record<string, unknown>>;
    update_requests: Array<Record<string, unknown>>;
    escalations: Array<Record<string, unknown>>;
  };
  preparedness_action_evidence?: {
    mode: string;
    outcome_ref: string;
    reference_at: string | null;
    window_start: string | null;
    related_alert_public_ids: string[];
    prediction_risk_score_ids: number[];
    summary: {
      total_count: number;
      completed_count: number;
      completed_without_substantive_evidence_count: number;
      in_progress_count: number;
      failed_count: number;
      blocked_count: number;
      overdue_count: number;
      completed_with_evidence_count: number;
      first_action_at: string | null;
      first_acknowledged_at: string | null;
      first_completed_at: string | null;
    };
    response_time_measurements: {
      hours_to_first_action: number | null;
      hours_to_first_acknowledgement: number | null;
      hours_to_first_completion: number | null;
    };
    completion_quality_flags: string[];
    action_history: Array<{
      public_id: string;
      action_type: PreparednessActionType;
      action_type_label: string;
      status: PreparednessActionStatus;
      outcome_status: "recorded" | "in_progress" | "failed" | "missing";
      priority: PreparednessActionPriority;
      ward_id: number;
      ward_name: string;
      facility_id: number | null;
      facility_name: string;
      chv_id: number | null;
      chv_name: string;
      assigned_to: number | null;
      assigned_to_username: string;
      assigned_to_team: string;
      source_trigger_type: PreparednessActionSourceTrigger;
      source_trigger_ref: string;
      risk_score_id: number | null;
      model_run_id: number | null;
      model_run_version: string;
      alert_public_id: string;
      linked_alert_public_ids: string[];
      related_alert_public_ids: string[];
      created_at: string;
      acknowledged_at: string | null;
      completed_at: string | null;
      due_at: string | null;
      is_overdue: boolean;
      completion_evidence_present: boolean;
      completion_quality_flags: string[];
      response_step_keys: string[];
      outcome_links: {
        outcome_ref: string;
        label_window_ref: string;
        prediction_risk_score_ids: number[];
        alert_public_ids: string[];
      };
    }>;
    missed_action_review: {
      review_required: boolean;
      missing_required_action_keys: string[];
      overdue_action_public_ids: string[];
      blocked_action_public_ids: string[];
      cancelled_action_public_ids: string[];
      detail: string;
    };
    false_alert_review_context: {
      review_required: boolean;
      completed_action_public_ids: string[];
      detail: string;
    };
  };
};

export type WardOperationalEvidence = {
  schema_version: string;
  ward_id: number;
  forecast_horizon: {
    label: string;
    min_days: number;
    max_days: number;
    display_value: string;
    expected_cases_label: string;
    lead_time_supported_days: number[];
    validation_status: string | null;
    mode: string;
    source_label?: string;
    claimed_forecast_horizon_days?: number | null;
    forecast_coverage_days?: number | null;
    forecast_missing_lead_days?: number[];
    climate_coverage_status?: string;
    claimed_lead_time_climate_coverage_sufficient?: boolean | null;
    issue_time?: string | null;
    valid_date?: string | null;
    lead_day?: number | null;
    fallback_static_rainfall_used?: boolean;
  };
  climate_source?: ClimateEvidence;
  model_readiness: {
    state: "seeded_demo" | "proxy_backed" | "evaluated" | "promoted";
    label: string;
    tone: WardOperationalEvidenceTone;
    detail: string;
    evidence: string[];
    readiness_caveats?: string[];
  };
  source_badges: WardOperationalEvidenceBadge[];
  alert_candidate_review: {
    review_state: "alert_active" | "needs_human_review" | "routine_monitoring";
    alert_decision: string;
    policy_version: string;
    risk_level: "LOW" | "MEDIUM" | "HIGH" | null;
    risk_score: number | null;
    predicted_cases: number;
    automatic_alert_allowed: boolean;
    automatic_alert_blockers: string[];
    reason_codes: string[];
    recommended_action: string;
    active_alert_count: number;
  };
  outcome_evaluation: {
    mode: string;
    evaluated_count: number;
    hit_count: number;
    false_alert_count: number;
    missed_outbreak_count: number;
    pending_label_count: number;
    correct_quiet_count: number;
    precision_review_note?: string;
    rows: WardPredictionLabelHistoryRow[];
  };
  prediction_label_history: WardPredictionLabelHistoryRow[];
  outcome_feedback?: WardOutcomeFeedback;
  false_missed_review: {
    mode: string;
    open_review_count: number;
    workflow_label: string;
    items: Array<{
      classification: "false_alert" | "missed_outbreak";
      risk_score_id: number;
      prediction_generated_at: string;
      label_window_ref: string;
      observed_label: string;
      recommended_review_action: string;
    }>;
  };
  chv_action_status: {
    mode: string;
    summary: {
      visible_request_count: number;
      active_request_count: number;
      linked_alert_count: number;
      latest_status: ChvCoverageRequestStatus | "NO_REQUEST";
    };
    requests: Array<{
      public_id: string;
      status: ChvCoverageRequestStatus;
      priority: ChvCoverageRequestPriority;
      trigger_source: ChvCoverageRequestTriggerSource;
      created_at: string;
      expected_response_by: string | null;
      resolved_at: string | null;
      linked_alert_public_ids: string[];
      linked_alert_statuses: Array<{
        public_id: string;
        status: AlertRecord["status"];
        channel: AlertRecord["channel"];
        created_at: string;
      }>;
      assignment_counts: {
        active: number;
        completed: number;
        cancelled: number;
        total: number;
      };
    }>;
  };
};

export type WardSpatialEvidenceNeighbor = {
  ward_id: number;
  ward_name: string;
  county: string;
  ward_code: string;
  relationship_types: string[];
  relationship_labels: string[];
  relationship_refs: string[];
  generation_methods: string[];
  is_approximate_relationship: boolean;
  approximation_notice: string | null;
  confidence: number;
  distance: number | null;
  distance_unit: string;
  geometry_dataset_ref: string;
  relationship_generated_at: string | null;
  risk_level: "LOW" | "MEDIUM" | "HIGH" | null;
  risk_score: number | null;
  predicted_cases: number;
  risk_generated_at: string | null;
  risk_score_ref: string | null;
  active_outbreak_label: boolean;
  suspected_cases_28d: number;
  suspected_case_trend_14d_delta: number;
  surveillance_record_count_28d: number;
  latest_surveillance_reporting_period_end: string | null;
};

export type WardSpatialEvidenceCatchment = {
  catchment_id: number;
  facility_id: number;
  facility_name: string;
  facility_code: string;
  primary_ward_id: number;
  primary_ward_name: string;
  covered_ward_ids: number[];
  covered_ward_names: string[];
  catchment_method: string;
  catchment_method_label: string;
  source_kind: string;
  source_kind_label: string;
  is_approximate: boolean;
  confidence: number;
  population_estimate: number | null;
  generated_at: string;
  projected_pressure_score: number | null;
  projected_readiness_state: string | null;
  projected_readiness_label: string;
  forecast_generated_at: string | null;
  forecast_ref: string | null;
  source_ref: string;
};

export type WardSpatialEvidence = {
  schema_version: string;
  ward_id: number;
  ward_name: string;
  as_of: string;
  summary: {
    neighbor_count: number;
    high_risk_neighbor_count: number;
    active_outbreak_neighbor_count: number;
    neighbor_suspected_case_trend_14d_delta: number;
    nearest_high_risk_distance: number | null;
    nearest_facility_distance: number | null;
    nearest_facility_distance_unit: string;
    catchment_facility_count: number;
    approximate_catchment_count: number;
    max_catchment_pressure_score: number | null;
    water_proximity_available: boolean;
    water_proximity_value: number | null;
  };
  neighbors: WardSpatialEvidenceNeighbor[];
  high_risk_neighbor_ward_ids: number[];
  active_outbreak_neighbor_ward_ids: number[];
  facility_catchments: WardSpatialEvidenceCatchment[];
  nearest_facility: {
    facility_id: number;
    facility_name: string;
    facility_code: string;
    ward_id: number;
    ward_name: string;
    distance: number;
    distance_unit: string;
    source_ref: string;
    source_created_at: string | null;
  } | null;
  water_proximity: {
    source_available: boolean;
    value: number | null;
    display_caveat: string;
  };
  lineage: Record<string, unknown>;
  caveats: string[];
};

export type WardIntelligenceTrend = {
  label: string;
  direction: "up" | "down" | "flat";
  delta_points: number | null;
  mode: string;
};

export type WardIntelligenceDriverItem = {
  text: string;
  tone: "critical" | "warning" | "info";
  source_field: string | null;
};

export type WardIntelligenceGuidanceItem = {
  text: string;
  urgency: "primary" | "review_only";
};

export type WardIntelligenceFreshness = {
  generated_at: string | null;
  is_stale: boolean;
  stale_threshold_minutes: number;
  history_count: number;
  alert_count: number;
  mode: string;
};

export type AlertIntelligenceClassification = {
  label: string;
  tone: "red" | "amber" | "orange" | "blue" | "slate";
  icon_key: string;
  trigger_source: string;
  mode: string;
};

export type AlertIntelligenceRiskContext = {
  level_label: string;
  trend_label: string;
  summary: string;
  recorded_risk_score: number | null;
  threshold: number | null;
  mode: string;
};

export type AlertIntelligenceDelivery = {
  channel_label: string;
  audience_label: string;
  status_label: string;
  status_tone: "default" | "success" | "warning" | "danger";
  recipient_count: number;
  attempt_count?: number;
  max_attempts?: number;
  delivery_backend?: string;
  last_attempted_at?: string | null;
  next_retry_at?: string | null;
  sent_at?: string | null;
  mode: string;
};

export type AlertIntelligenceStateItem = {
  label: string;
  tone: "success" | "warning" | "neutral";
};

export type AlertIntelligenceLifecycle = {
  status: "active" | "monitoring" | "escalated" | "resolved";
  status_label: string;
  summary: string;
  last_updated_at: string | null;
  mode: string;
};

export type AlertIntelligenceResponseSummary = {
  status_label: string;
  coverage_label: string;
  summary: string;
  response_count: number;
  mode: string;
};

export type AlertIntelligenceRecommendedAction = {
  label: string;
  detail: string;
  blocked: boolean;
  blocked_reason: string;
  mode: string;
};

export type AlertIntelligenceMessageSource = {
  mode: "backend_generated" | "operator_edited" | "unavailable";
  label: string;
  summary: string;
  trigger_type: string;
  preview_text: string;
};

export type AlertIntelligenceFreshness = {
  updated_at: string | null;
  is_stale: boolean;
  stale_threshold_minutes: number;
  mode: string;
};

export type AlertIntelligenceTimelineEntry = {
  id: string;
  title: string;
  description: string;
  timestamp: string | null;
  tone: "primary" | "progress" | "success" | "danger" | "warning" | "neutral";
  category: "all" | "system" | "communication" | "field_activity" | "escalation" | "resolution";
  meta: string | null;
  actor?: string;
  event_type?: string;
  message?: string;
  details?: string[];
};

export type AlertIntelligenceCapabilities = {
  can_resend: boolean;
  can_recall: boolean;
  can_notify_facilities: boolean;
  can_send_follow_up: boolean;
  can_dispatch_additional_chvs?: boolean;
  can_close_alert?: boolean;
  mode: string;
};

export type FacilityIntelligenceReadiness = {
  facility_type_label: string;
  surge_risk: "EXTREME" | "MODERATE" | "LOW";
  surge_risk_label: string;
  status_banner_label: string;
  projected_cases: number;
  predicted_cases_per_day: number;
  ors_estimate_percent: number;
  ors_state: "CRITICAL" | "STABLE" | "READY";
  staffing_filled: number;
  staffing_required: number;
  staffing_percent: number;
  staffing_state: "LIMITED" | "OPTIMAL";
  last_reported_at: string | null;
  freshness_state: "FRESH" | "WARNING" | "STALE";
  mode: string;
  backing_source: string;
  dashboard_truth_state: string;
};

export type FacilityIntelligenceContext = {
  summary: string;
  ward_risk_score: number | null;
  ward_alert_count: number;
  map_mode: string;
  driving_ward_ids: number[];
  action_reasoning: string[];
};

export type FacilityIntelligenceFreshness = {
  updated_at: string | null;
  is_stale: boolean;
  stale_threshold_minutes: number;
  mode: string;
};

export type FacilityIntelligenceTimelineEntry = {
  id: string;
  title: string;
  description: string;
  timestamp: string | null;
  tone: "success" | "warning" | "danger" | "info";
  category: "system" | "alert";
  meta: string | null;
  details?: string[];
};

export type FacilityContactAvailability = {
  public_id: string;
  display_label: string;
  role: string;
  preferred_channel: "SMS" | "EMAIL" | "SYSTEM";
  is_verified: boolean;
  is_active: boolean;
  source: string;
  verified_at: string | null;
  phone_last4: string;
  has_phone: boolean;
  has_email: boolean;
};

export type FacilityReadinessReviewSummary = {
  public_id: string;
  facility: number;
  facility_name: string;
  ward: number;
  ward_name: string;
  status: "OPEN" | "ACKNOWLEDGED" | "RESOLVED" | "DISMISSED";
  severity: "LOW" | "MEDIUM" | "HIGH";
  reason_codes: string[];
  notes: string;
  created_at: string;
  updated_at: string;
  acknowledged_at: string | null;
  resolved_at: string | null;
  dismissed_at: string | null;
};

export type FacilityReadinessUpdateRequestSummary = {
  public_id: string;
  review: string;
  facility: number;
  facility_name: string;
  contact: string;
  contact_display_label: string;
  requested_by: number;
  requested_by_username: string;
  channel: "SMS" | "EMAIL" | "SYSTEM";
  status: "DRAFT" | "QUEUED" | "SENT" | "ACKNOWLEDGED" | "FAILED" | "CANCELLED";
  requested_at: string;
  sent_at: string | null;
  acknowledged_at: string | null;
  created_at: string;
  updated_at: string;
  message_body?: string;
  provider_reference?: string | null;
  failure_reason?: string;
};

export type FacilityReadinessEscalationSummary = {
  public_id: string;
  review: string;
  facility: number;
  facility_name: string;
  ward: number;
  ward_name: string;
  status: "OPEN" | "ACKNOWLEDGED" | "RESOLVED" | "DISMISSED";
  severity: "LOW" | "MEDIUM" | "HIGH";
  reason: string;
  created_by: number;
  created_by_username: string;
  acknowledged_by: number | null;
  acknowledged_by_username: string | null;
  assigned_to: number | null;
  assigned_to_username: string | null;
  notes: string;
  created_at: string;
  updated_at: string;
  acknowledged_at: string | null;
  resolved_at: string | null;
  dismissed_at: string | null;
};

export type FacilityLinkedAlertNavigation = {
  id: number;
  public_id: string;
  ward_id: number;
  ward_name: string;
  status: AlertRecord["status"];
  channel: AlertRecord["channel"];
  recipient: string;
  risk_score: number | null;
  created_at: string;
  sent_at: string | null;
  api_url: string;
  intelligence_api_url: string;
  dashboard_url: string;
  filtered_alerts_url: string;
};

export type FacilityChvOperationsNavigation = {
  available: boolean;
  ward_id: number;
  ward_name: string;
  active_chv_count: number;
  total_chv_count: number;
  api_url: string;
  dashboard_url: string;
  mode: "chv_operations_deep_link_only";
  message: string;
};

export type FacilityIntelligenceCapabilities = {
  can_view_contacts: boolean;
  can_open_readiness_review: boolean;
  can_request_facility_update: boolean;
  can_escalate_county_review: boolean;
  can_open_linked_alert: boolean;
  can_open_chv_operations: boolean;
  can_acknowledge_review: boolean;
  has_verified_contact: boolean;
  has_active_review: boolean;
  has_active_update_request: boolean;
  has_active_escalation: boolean;
  has_county_review_queue: boolean;
  mode: string;
};

export type FacilityIntelligenceForecasting = {
  source_kind: string;
  governance_mode: string;
  model_version: string | null;
  forecast_mode: string;
  projected_pressure_score: number;
  projected_readiness_state: string;
  driving_ward_ids: number[];
  dashboard_truth_state: string;
};

export type TriggerAlertRequest = {
  ward_id: number;
  send_sms: boolean;
  trigger_type?: "HIGH_RISK_ESCALATION" | "FOLLOW_UP_REVIEW" | "DELIVERY_RETRY" | "CUSTOM";
  message_override?: string;
  template_key?: string;
  template_version?: number | null;
  template_language?: string;
  template_context?: Record<string, string | number | boolean | null>;
};

export type TriggerAlertResponse = {
  message: string;
  request_id: string;
  alert_id: number | null;
  ward_id: number;
  ward_name: string;
  risk_level: "LOW" | "MEDIUM" | "HIGH";
  risk_score: number;
  predicted_cases: number;
  risk_score_id: number;
  task_id: string;
  send_sms: boolean;
  trigger_type?: "HIGH_RISK_ESCALATION" | "FOLLOW_UP_REVIEW" | "DELIVERY_RETRY" | "CUSTOM" | null;
  message_mode?: "backend_generated" | "operator_edited" | "template_rendered" | null;
  queued_at: string;
  last_risk_update_at: string | null;
  estimated_chv_recipient_count: number | null;
  trigger_linkage_state?: string | null;
};

export type TriggerAlertRequestStatusResponse = {
  request_id: string;
  status: "PENDING_CREATION" | "MATERIALIZED";
  alert_id: number | null;
  ward_id: number;
  ward_name: string;
  created_alert_count: number;
  sms_alert_count: number;
  dashboard_alert_id: number | null;
  last_materialized_at: string | null;
};

export type TriggerActionType = "HIGH_RISK_ESCALATION" | "FOLLOW_UP_REVIEW" | "DELIVERY_RETRY" | "CUSTOM";

export type TriggerContextResponse = {
  ward: {
    id: number;
    name: string;
    county: string;
    sub_county: string;
  };
  risk: {
    level: "LOW" | "MEDIUM" | "HIGH" | null;
    score: number | null;
    predicted_cases: number;
    last_risk_update_at: string | null;
  };
  workflow: {
    status: string;
    decision_mode: string;
    trigger_reason: string;
    recommended_action: string;
    active_alert_count: number;
    alert_delivery_state: string;
    alert_delivery_label: string;
  };
  system_context: {
    why_this_might_need_an_alert: string[];
    what_happens_if_no_action: string;
    trigger_status_label: string;
    recommended_trigger_type: TriggerActionType;
    confidence_label: string;
  };
  recipient_preview: {
    chv_count: number;
  };
  supported_delivery_channels: string[];
  supported_trigger_types: TriggerActionType[];
};

export type TriggerPreviewResponse = {
  message_preview: string;
  message_mode: "backend_generated" | "operator_edited" | "template_rendered";
  supports_editing: boolean;
  channel_defaults: string[];
  recipient_preview: {
    chv_count: number;
  };
  recommended_action: string;
  message_template?: Record<string, unknown>;
};

export type OverviewSystemState = "stable" | "watch" | "action_required";
export type OverviewDecisionMode = "risk_only" | "triggered" | "alert_active" | "facility_capacity_concern";
export type OverviewEligibleAction = "view_alerts" | "dispatch_chvs" | "send_message" | "investigate";
export type OverviewTriggerConfidence = "high" | "moderate" | "review";

export type OverviewRuleBasis = {
  source: "bff_rules_v1";
  rule_id: string;
  rule_label: string;
  inputs: string[];
};

export type OverviewTriggerReasonItem = {
  label: string;
  detail: string;
  tone: "danger" | "warning" | "info";
};

export type OverviewTriggerEvent = {
  trigger_id: string;
  ward_id: number;
  ward_name: string;
  risk_level: "LOW" | "MEDIUM" | "HIGH" | null;
  risk_score: number | null;
  predicted_cases: number;
  trend_label: string;
  trigger_reason_items: OverviewTriggerReasonItem[];
  confidence: OverviewTriggerConfidence;
  triggered_at: string | null;
  recommended_action: string;
  rules_basis: OverviewRuleBasis;
  expected_operational_effect: string;
  dismissible: boolean;
  has_active_alert: boolean;
  alert_count: number;
  eligible_actions: OverviewEligibleAction[];
  latest_risk_update_at: string | null;
};

export type OverviewDecisionSummary = {
  top_priority_ward: {
    ward_id: number;
    ward_name: string;
    risk_level: "LOW" | "MEDIUM" | "HIGH" | null;
    risk_score: number | null;
    predicted_cases: number;
    alert_count: number;
    has_active_alert: boolean;
    generated_at: string | null;
  } | null;
  reason_flagged: string;
  recommended_action: string;
  decision_mode: OverviewDecisionMode;
  eligible_actions: OverviewEligibleAction[];
  rules_basis: OverviewRuleBasis;
};

export type OverviewStateModel = {
  system_state: OverviewSystemState;
  state_reason: string;
  system_state_reason: string;
  trigger_count: number;
  watch_count: number;
  action_required_count: number;
  last_triggered_at: string | null;
  trigger_summary: {
    triggered_wards_count: number;
    under_watch_wards_count: number;
    action_required_wards_count: number;
  };
  risk_state: {
    label: string;
    high_risk_wards_count: number;
    under_watch_wards_count: number;
  };
  alert_state: {
    label: string;
    visible_alert_count: number;
    triggered_wards_count: number;
  };
  action_state: {
    label: string;
    recommended_mode: "monitor" | "review" | "act";
    action_required_wards_count: number;
  };
};

export type OverviewFreshnessSummary = DashboardFreshnessSummary;

export type OverviewKpiTemporalDelta = {
  current_value: number;
  previous_value: number;
  delta: number;
  direction: "up" | "down" | "flat";
  context_label: string;
};

export type OverviewTemporalMetrics = {
  high_risk: OverviewKpiTemporalDelta;
  medium_risk: OverviewKpiTemporalDelta;
  alerts_today: OverviewKpiTemporalDelta;
  delivered_alert_rate: OverviewKpiTemporalDelta;
};

export type OverviewMissionMetrics = {
  monitored_wards_count: number;
  workflow_active_wards_count: number;
  trigger_delivery_concern_count: number;
  last_trigger_lead_time_hours: number | null;
  last_trigger_lead_time_label: string;
  last_triggered_at: string | null;
  last_trigger_risk_signal_at: string | null;
};

export type OverviewMapGuidanceTarget = {
  ward_id: number;
  ward_name: string;
  label: string;
  reason: string;
  risk_level: "LOW" | "MEDIUM" | "HIGH" | null;
  risk_score: number | null;
  alert_count: number;
  predicted_cases: number;
};

export type OverviewMapGuidance = {
  top_triggered_ward: OverviewMapGuidanceTarget | null;
  most_active_alert_ward: OverviewMapGuidanceTarget | null;
  biggest_recent_escalation: OverviewMapGuidanceTarget | null;
  predicted_highest_risk_ward: OverviewMapGuidanceTarget | null;
};

export type OverviewTriggerSeverity = "high" | "medium" | "review";

export type OverviewTriggerDeliveryState =
  | "awaiting_review"
  | "triggered_queued"
  | "triggered_delivered"
  | "triggered_retry_pending"
  | "triggered_failed";

export type OverviewTriggeredWard = {
  ward_id: number;
  ward_name: string;
  risk_level: "LOW" | "MEDIUM" | "HIGH" | null;
  risk_score: number | null;
  predicted_cases: number;
  trigger_reason: string;
  trigger_severity: OverviewTriggerSeverity;
  triggered_at: string | null;
  recommended_response: string;
  rules_basis: OverviewRuleBasis;
  workflow_state: WardDecisionConsoleTriggerState;
  workflow_state_label: string;
  alert_delivery_state: OverviewTriggerDeliveryState;
  alert_delivery_label: string;
  alert_count: number;
  delivered_alert_count: number;
  retry_pending_alert_count: number;
  failed_alert_count: number;
  queued_alert_count: number;
};

export type OverviewTriggerLinkageSummary = {
  triggered_wards: OverviewTriggeredWard[];
  active_alert_wards_count: number;
  delivered_wards_count: number;
  retry_pending_wards_count: number;
  failed_wards_count: number;
  awaiting_review_wards_count: number;
  delivery_concern_wards_count: number;
};

export type OverviewFacilityReadinessState = "ready" | "watch" | "capacity_concern";

export type OverviewPriorityFacility = {
  facility_id: number;
  facility_name: string;
  ward_id: number;
  ward_name: string;
  readiness_state: OverviewFacilityReadinessState;
  readiness_score: number;
  projected_pressure_score: number;
  projected_case_burden: number;
  driving_ward_ids: number[];
  readiness_factors: string[];
  snapshot_at: string | null;
  generated_at: string | null;
  freshness_state: "FRESH" | "WARNING" | "STALE";
  backing_source: string;
  dashboard_truth_state: string;
};

export type OverviewFacilityWardSignal = {
  ward_id: number;
  ward_name: string;
  facility_capacity_signal: OverviewFacilityReadinessState;
  facility_readiness_tone: "success" | "warning" | "danger";
  facility_count: number;
  priority_facility_ids: number[];
  priority_facility_names: string[];
};

export type OverviewFacilityReadinessSummary = {
  facilities_at_risk_count: number;
  facilities_capacity_concern_count: number;
  priority_facilities: OverviewPriorityFacility[];
  ward_capacity_signals: OverviewFacilityWardSignal[];
  honesty_note: string;
};

export type OverviewSimulationReadiness = {
  supported: boolean;
  status_label: string;
  status_reason: string;
  required_contracts: string[];
  prepared_inputs: {
    rainfall_adjustments: string;
    forecast_perturbation_inputs: string;
    predicted_risk_recomputation_envelope: string;
    safe_non_production_execution_rules: string;
  };
  reserved_scenarios: Array<{
    id: "rainfall_increase" | "response_delay";
    label: string;
    prompt: string;
    blocked_reason?: string;
  }>;
};

export type ScenarioSimulationRun = {
  id: number;
  public_id: string;
  scenario_id: "RAINFALL_INCREASE" | "RESPONSE_DELAY";
  created_by: number | null;
  created_by_username: string | null;
  input_parameters: {
    rainfall_uplift_percent?: number;
    response_delay_hours?: number;
  };
  summary: {
    scenario_id: string;
    scenario_label: string;
    top_impacted_ward_name: string | null;
    high_risk_ward_count: number;
    watch_ward_count: number;
    capacity_concern_facility_count: number;
    non_production: boolean;
  };
  ward_results: Array<{
    ward_id: number;
    ward_name: string;
    baseline_risk_level: "LOW" | "MEDIUM" | "HIGH" | null;
    baseline_risk_score: number;
    baseline_predicted_cases: number;
    simulated_risk_level: "LOW" | "MEDIUM" | "HIGH";
    simulated_risk_score: number;
    simulated_predicted_cases: number;
    explanation: string;
  }>;
  facility_results: Array<{
    facility_id: number;
    facility_name: string;
    ward_id: number;
    ward_name: string;
    baseline_capacity_signal: string;
    simulated_capacity_signal: "ready" | "watch" | "capacity_concern";
    projected_pressure_score: number;
  }>;
  expires_at: string | null;
  created_at: string;
};

export type FetchWardRiskDataParams = {
  county?: string;
  q?: string;
  risk?: string;
  sub_county?: string;
  ordering?: string;
};

export type WardDecisionConsoleTriggerState =
  | "NONE"
  | "TRIGGER_ACTIVE"
  | "REVIEW_PENDING"
  | "ACTION_IN_PROGRESS"
  | "RESOLVED";

export function normalizeAlertWorkflowStatusToPageState(
  status: AlertWorkflowRecord["status"] | null | undefined,
): WardDecisionConsoleTriggerState {
  if (!status) {
    return "NONE";
  }
  if (status === "REVIEW_PENDING") {
    return "REVIEW_PENDING";
  }
  if (status === "QUEUED" || status === "RETRY_PENDING" || status === "FAILED") {
    return "ACTION_IN_PROGRESS";
  }
  if (status === "DELIVERED") {
    return "TRIGGER_ACTIVE";
  }
  if (status === "RESOLVED") {
    return "RESOLVED";
  }
  return "NONE";
}

export function getPageWorkflowStateLabel(state: WardDecisionConsoleTriggerState) {
  if (state === "TRIGGER_ACTIVE") return "Trigger active";
  if (state === "REVIEW_PENDING") return "Awaiting review";
  if (state === "ACTION_IN_PROGRESS") return "Action in progress";
  if (state === "RESOLVED") return "Resolved";
  return "No active trigger";
}

export function pageWorkflowStateRequiresAction(state: WardDecisionConsoleTriggerState) {
  return state === "REVIEW_PENDING" || state === "ACTION_IN_PROGRESS";
}

export function pageWorkflowStateCountsAsWorkflowActive(state: WardDecisionConsoleTriggerState) {
  return state === "REVIEW_PENDING" || state === "TRIGGER_ACTIVE" || state === "ACTION_IN_PROGRESS";
}

export type WardDecisionConsolePrimaryCtaKind =
  | "REVIEW_TRIGGER"
  | "OPEN_TRIGGER_FLOW"
  | "VIEW_ALERT_HISTORY";

export type WardQueueItem = {
  id: number;
  public_id: string;
  name: string;
  county: string;
  sub_county: string;
  risk_level: "LOW" | "MEDIUM" | "HIGH" | "UNKNOWN";
  risk_score: number | null;
  expected_cases_7d: number | null;
  last_updated_at: string | null;
  trigger_state: WardDecisionConsoleTriggerState;
  requires_action: boolean;
  recent_alert_count: number;
  delivery_concern_count: number;
  workflow_public_id: string | null;
  recommended_action: string | null;
};

export type WardQueueSummary = {
  wards_requiring_action: number;
  workflow_active_wards: number;
  alerts_pending: number;
};

export type WardQueueUrgency = {
  has_actionable_wards: boolean;
  requires_action_count: number;
};

type OverviewRouteResponse = {
  wards: PaginatedResponse<WardSummary>;
  latestRisks: LatestWardRisk[];
  alerts: PaginatedResponse<AlertRecord>;
  wardMap: WardMapResponse;
  overviewState: OverviewStateModel;
  decisionSummary: OverviewDecisionSummary;
  triggerReviewQueue: OverviewTriggerEvent[];
  freshness: OverviewFreshnessSummary;
  temporalMetrics: OverviewTemporalMetrics;
  missionMetrics: OverviewMissionMetrics;
  mapGuidance: OverviewMapGuidance;
  triggerLinkage: OverviewTriggerLinkageSummary;
  facilityReadiness: OverviewFacilityReadinessSummary;
  simulationReadiness: OverviewSimulationReadiness;
  alertWorkflows?: AlertWorkflowRecord[];
};

type WardsRouteResponse = {
  wards: PaginatedResponse<WardSummary>;
  latestRisks: LatestWardRisk[];
  recentAlertCountsByWard: Record<string, number>;
  wardQueue: {
    items: WardQueueItem[];
    summary: WardQueueSummary;
    urgency: WardQueueUrgency;
  };
};

export type WardIntelligenceRouteResponse = {
  ward: WardDetailSummary;
  current_risk: {
    risk_level: "LOW" | "MEDIUM" | "HIGH" | null;
    risk_score: number | null;
    predicted_cases: number;
    decision_policy?: Record<string, unknown>;
    generated_at: string | null;
    source: string | null;
    model_version: string | null;
    model_run_status: string | null;
  };
  trend: WardIntelligenceTrend;
  driver_summary: {
    mode: string;
    items: WardIntelligenceDriverItem[];
  };
  guidance_summary: {
    mode: string;
    items: WardIntelligenceGuidanceItem[];
  };
  freshness: WardIntelligenceFreshness;
  risk_history: RiskScoreRecord[];
  related_alerts: AlertRecord[];
  workflow: {
    public_id: string;
    status: WardDecisionConsoleTriggerState;
    status_label: string;
    recommended_action: string;
    expected_operational_effect: string;
    eligible_actions: Array<WardDecisionConsolePrimaryCtaKind>;
    active_alert_count: number;
    retry_pending_alert_count: number;
    failed_alert_count: number;
    queued_alert_count: number;
    latest_risk_update_at: string | null;
    updated_at: string;
  } | null;
  decision_summary: {
    action_required: boolean;
    headline: string;
    why: string;
    next_steps: string[];
    primary_cta_kind: WardDecisionConsolePrimaryCtaKind;
  };
  header_context: {
    last_alert_at: string | null;
    latest_record_at: string | null;
    freshness_state: "FRESH" | "STALE";
    trigger_state: WardDecisionConsoleTriggerState;
    expected_cases_7d: number;
    risk_score: number | null;
  };
  surveillance?: Record<string, unknown>;
  spatial_evidence?: WardSpatialEvidence;
  operational_evidence?: WardOperationalEvidence;
};

type AlertDetailRouteResponse = {
  alert: AlertRecord | null;
  ward_detail: WardDetailSummary | null;
  classification: AlertIntelligenceClassification;
  risk_context: AlertIntelligenceRiskContext;
  lifecycle: AlertIntelligenceLifecycle;
  delivery: AlertIntelligenceDelivery;
  delivery_summary: AlertIntelligenceDelivery;
  message_source: AlertIntelligenceMessageSource;
  climate_evidence?: ClimateEvidence;
  chv_response_summary: AlertIntelligenceResponseSummary;
  facility_response_summary: AlertIntelligenceResponseSummary;
  recommended_next_action: AlertIntelligenceRecommendedAction;
  last_updated_at: string | null;
  current_state: AlertIntelligenceStateItem[];
  freshness: AlertIntelligenceFreshness;
  timeline: AlertIntelligenceTimelineEntry[];
  capabilities: AlertIntelligenceCapabilities;
};

export type FacilityIntelligenceRouteResponse = {
  facility: FacilityRecord | null;
  contact: FacilityContactAvailability | null;
  active_review: FacilityReadinessReviewSummary | null;
  active_update_request: FacilityReadinessUpdateRequestSummary | null;
  active_escalation: FacilityReadinessEscalationSummary | null;
  linked_alerts: FacilityLinkedAlertNavigation[];
  chv_operations: FacilityChvOperationsNavigation;
  readiness: FacilityIntelligenceReadiness;
  context: FacilityIntelligenceContext;
  forecasting: FacilityIntelligenceForecasting;
  freshness: FacilityIntelligenceFreshness;
  decision_summary: FacilityReadinessDecisionSummary;
  timeline: FacilityIntelligenceTimelineEntry[];
  capabilities: FacilityIntelligenceCapabilities;
};

export type FacilityReadinessDecisionSummaryPriority = {
  facility_id: number;
  facility_name: string;
  ward_id: number;
  ward_name: string;
  priority_rank: number;
  priority_label: string;
  reason_codes: Array<
    | "HIGH_READINESS_DIFFERENCE"
    | "MODERATE_READINESS_DIFFERENCE"
    | "ELEVATED_WARD_RISK"
    | "STALE_INPUTS"
    | "MULTIPLE_ALERTS_IN_WARD"
    | "FORECAST_PRESSURE_ELEVATED"
    | "CALM_VISIBLE_SCOPE"
    | "WEAK_PROXY_INPUTS"
  >;
  reason_text: string;
  review_href: string | null;
};

export type FacilityReadinessDecisionSummary = {
  state: "CALM" | "REVIEW" | "DEGRADED_CONFIDENCE";
  headline: string;
  body: string;
  confidence: "NORMAL" | "DEGRADED";
  confidence_reason: "stale_inputs" | "weak_proxy_inputs" | "stale_and_weak_proxy_inputs" | null;
  total_review_facility_count: number;
  top_priorities: FacilityReadinessDecisionSummaryPriority[];
  related_surfaces: {
    has_linked_alerts: boolean;
    linked_alert_count: number;
  };
};

export type FacilityReadinessWorkflowState = {
  facility_id: number;
  has_active_review: boolean;
  review_public_id: string | null;
  review_status: FacilityReadinessReviewSummary["status"] | null;
  has_active_update_request: boolean;
  update_request_public_id: string | null;
  update_request_status: FacilityReadinessUpdateRequestSummary["status"] | null;
  has_active_escalation: boolean;
  escalation_public_id: string | null;
  escalation_status: FacilityReadinessEscalationSummary["status"] | null;
  label: string;
  tone: "success" | "warning" | "default";
};

export type FacilityListRouteResponse = PaginatedResponse<FacilityRecord> & {
  decision_summary: FacilityReadinessDecisionSummary;
  workflow_states: FacilityReadinessWorkflowState[];
};

export type SystemControlStatus = {
  mode: "control_contracts_enabled";
  can_retry_background_jobs: boolean;
  can_run_manual_risk_scoring: boolean;
  can_pause_alert_delivery: boolean;
  alert_delivery_paused: boolean;
  alert_delivery_paused_until: string | null;
  alert_delivery_pause_reason: string;
  alert_delivery_pause_updated_at: string | null;
  alert_delivery_pause_updated_by: string | null;
};

export type SystemRetryControlResponse = {
  detail: string;
  queued_alert_delivery_count: number;
  failed_sync_payload_count: number;
  task_ids: string[];
  control_status: SystemControlStatus;
};

export type SystemManualRiskScoringResponse = {
  detail: string;
  task_id: string;
  control_status: SystemControlStatus;
};

export type SystemRouteResponse = {
  wards: PaginatedResponse<WardSummary>;
  latestRisks: LatestWardRisk[];
  alerts: PaginatedResponse<AlertRecord>;
  queuedAlerts: PaginatedResponse<AlertRecord>;
  retryAlerts: PaginatedResponse<AlertRecord>;
  failedAlerts: PaginatedResponse<AlertRecord>;
  deliveredAlerts: PaginatedResponse<AlertRecord>;
  facilities: PaginatedResponse<FacilityRecord>;
  chvOperations: ChvOperationsRecord[];
  controlStatus: SystemControlStatus;
};

export type OperationalMetricSnapshotStatus = "COMPLETE" | "PARTIAL" | "NO_SOURCE" | "STALE" | "FAILED" | "MISSING";
export type OperationalMetricStatusTone = "default" | "success" | "warning" | "danger" | "info";

export type OperationalMetricBaselineComparison = {
  status: "compared" | "not_configured" | "not_evaluable";
  baseline: {
    baseline_key: string;
    name: string;
    baseline_value: number;
    delta: number;
    percent_delta: number | null;
    period_start: string;
    period_end: string;
  } | null;
};

export type OperationalMetricSlaStatus = {
  status: "pass" | "breach" | "not_configured" | "not_evaluable";
  label: string;
  threshold: {
    threshold_key: string;
    display_name: string;
    comparator: "LTE" | "GTE" | "LT" | "GT";
    target_value: number;
    warning_value: number | null;
    critical_value: number | null;
    value_unit: string;
  } | null;
};

export type OperationalMetricCard = {
  metric_key: string;
  display_name: string;
  description: string;
  metric_group: string;
  metric_family: "OPERATIONAL" | "MODEL";
  owner: string;
  formula: string;
  window: string;
  source_model: string;
  source_models: string[];
  interpretation: string;
  value_type: "count" | "percent" | "rate" | "duration_seconds" | "ratio";
  value_unit: string;
  value: number | null;
  display_value: string;
  status: OperationalMetricSnapshotStatus;
  status_tone: OperationalMetricStatusTone;
  snapshot_key: string | null;
  snapshot_date: string | null;
  period_start: string | null;
  period_end: string | null;
  source_record_count: number;
  source_coverage_warnings: string[];
  dimension_values: Record<string, unknown>;
  source_channel: string;
  baseline: OperationalMetricBaselineComparison;
  sla: OperationalMetricSlaStatus;
};

export type OperationalMetricTrendPoint = {
  date: string;
  value: number | null;
  display_value: string;
  status: OperationalMetricSnapshotStatus;
  source_record_count: number;
};

export type OperationalMetricTrendSeries = {
  metric_key: string;
  display_name: string;
  value_type: OperationalMetricCard["value_type"];
  value_unit: string;
  points: OperationalMetricTrendPoint[];
};

export type OperationalMetricSourceWarning = {
  metric_key: string;
  warning: string;
  snapshot_key: string | null;
  snapshot_date: string | null;
  status: string;
};

export type OperationalMetricThresholdAlert = {
  public_id: string | null;
  breach_key: string | null;
  metric_key: string;
  metric_version: string;
  display_name: string;
  breach_type:
    | "THRESHOLD_WARNING"
    | "THRESHOLD_BREACH"
    | "SOURCE_WARNING"
    | "SNAPSHOT_STALE"
    | "MISSING_SNAPSHOT"
    | "STATUS_WARNING";
  severity: "WARNING" | "CRITICAL";
  status: "ACTIVE" | "RESOLVED";
  title: string;
  body: string;
  date: string;
  warning_code: string;
  observed_value: number | null;
  observed_display_value: string;
  observed_status: string;
  observed_unit: string;
  snapshot_key: string | null;
  threshold: {
    threshold_key: string;
    version: string;
    display_name: string;
    comparator: "LTE" | "GTE" | "LT" | "GT";
    target_value: number;
    warning_value: number | null;
    critical_value: number | null;
    value_unit: string;
  } | null;
  attribution: {
    metric_key: string;
    metric_version: string;
    metric_group: string;
    metric_owner: string;
    threshold_key: string;
    threshold_version: string;
    threshold_owner: string;
    snapshot_key: string;
    snapshot_date: string;
    source_record_count: number;
    warning_code: string;
    ward_id: number | null;
    ward_name: string;
    county: string;
    sub_county: string;
    source_channel: string;
    dimension_values: Record<string, unknown>;
  };
  first_seen_at: string | null;
  last_seen_at: string | null;
  resolved_at: string | null;
};

export type OperationalInteroperabilityContractsPanel = {
  schema_version: "interoperability-operational-kpi-feed-v1";
  generated_at: string;
  audit_status: "pass" | "fail";
  latest_mapping_coverage: number | null;
  latest_run: InteroperabilityRunRecord | null;
  active_mapping_version_count: number;
  active_org_unit_mapping_count: number;
  failed_run_count: number;
  audit_failures: InteroperabilityAuditCheck[];
  source_coverage_warnings: OperationalMetricSourceWarning[];
};

export type OperationalKpiDashboardResponse = {
  schema_version: "operational-kpi-dashboard-v1";
  generated_at: string;
  filters: {
    date_from: string;
    date_to: string;
    ward_id: number | null;
    ward_name: string;
    sub_county: string;
    source_channel: string;
  };
  available_filters: {
    wards: Array<{ id: number; name: string; county: string; sub_county: string }>;
    sub_counties: string[];
    source_channels: string[];
  };
  summary: {
    metric_count: number;
    snapshot_count: number;
    latest_snapshot_date: string | null;
    complete_metric_count: number;
    evaluable_metric_count: number;
    warning_count: number;
    threshold_alert_count: number;
    critical_threshold_alert_count: number;
    warning_threshold_alert_count: number;
    status_counts: Record<string, number>;
    operational_health: "pass" | "warning" | "critical";
    model_metric_count: number;
  };
  panels: {
    operational_overview: OperationalMetricCard[];
    sla: OperationalMetricCard[];
    adoption_coverage: OperationalMetricCard[];
    response_time_trends: OperationalMetricTrendSeries[];
    facility_preparedness_trends: OperationalMetricTrendSeries[];
    ussd_completion_trends: OperationalMetricTrendSeries[];
    model_vs_operations: {
      separation_statement: string;
      operational_metric_family: "OPERATIONAL";
      model_metric_family: "MODEL";
      latest_model_run: {
        model_version: string | null;
        status: string | null;
        started_at: string | null;
        completed_at: string | null;
        evaluation_metrics: Record<string, unknown>;
      };
      operational_metric_groups: string[];
    };
    source_coverage_warnings: OperationalMetricSourceWarning[];
    threshold_alerts: OperationalMetricThresholdAlert[];
    interoperability_contracts: OperationalInteroperabilityContractsPanel;
  };
  metrics: OperationalMetricCard[];
};

export type ModelOperationsHealthTone = "default" | "success" | "warning" | "danger" | "info";

export type ModelOperationsActiveModel = {
  registry_entry_id: number;
  registry_entry_public_id: string;
  model_run_id: number;
  algorithm: string;
  algorithm_name: string;
  model_version: string;
  promotion_state: string;
  promotion_state_label: string;
  promotion_date: string | null;
  active_from: string | null;
  active_until: string | null;
  monitoring_state: string;
  monitoring_state_label: string;
  review_due_date: string | null;
  owner: string;
  phase_4_promotion_gates_passed: boolean | null;
  alert_eligible: boolean;
  promotion_evidence_report_ref: string | null;
};

export type ModelMonitoringSnapshotPanel = {
  snapshot_id: number;
  snapshot_public_id: string;
  monitoring_run_id: string;
  metric_name: string;
  metric_family: string;
  value: number | null;
  baseline_value: number | null;
  threshold_value: number | null;
  threshold_version: string;
  state: string;
  state_label: string;
  generated_at: string;
  source_dataset_refs: string[];
  metadata: Record<string, unknown>;
};

export type ModelRollbackHistoryItem = {
  rollback_event_id: number;
  rollback_event_public_id: string;
  rolled_back_from: {
    registry_entry_id: number;
    model_run_id: number;
    model_version: string;
    algorithm: string;
  };
  rollback_target: {
    registry_entry_id: number;
    model_run_id: number;
    model_version: string;
    algorithm: string;
  };
  rolled_back_by: string;
  authorized_role: string | null;
  reason: string;
  occurred_at: string;
  current_risk_materialization: Record<string, unknown>;
};

export type ModelOperationsModelState = {
  model_run_id: number;
  algorithm: string | null;
  algorithm_name: string;
  model_version: string;
  status: string;
  visual_state: string;
  visual_state_label: string;
  promotion_target: string | null;
  promotion_state: string | null;
  registry_promotion_state: string | null;
  alert_eligible: boolean;
  run_purpose: string | null;
  started_at: string;
  completed_at: string | null;
};

export type ModelOperationsHealthResponse = {
  schema_version: "ward-risk-model-operations-health-v1";
  generated_at: string;
  summary: {
    health_state: string;
    health_state_label: string;
    health_tone: ModelOperationsHealthTone;
    active_model_healthy: boolean;
    active_model_present: boolean;
    monitoring_state: string;
    drift_warning_count: number;
    calibration_warning_count: number;
    rollback_event_count: number;
    challenger_benchmark_status: string;
  };
  active_model: ModelOperationsActiveModel | null;
  monitoring: {
    state: string;
    state_label: string;
    latest_monitoring_run_id: string | null;
    latest_generated_at: string | null;
    snapshots: ModelMonitoringSnapshotPanel[];
    drift_warnings: ModelMonitoringSnapshotPanel[];
    calibration_warnings: ModelMonitoringSnapshotPanel[];
  };
  challenger_comparison: {
    configured: boolean;
    comparison_id?: number;
    comparison_public_id?: string;
    generated_at?: string;
    benchmark_status: string;
    benchmark_status_label?: string;
    comparison_validity: string | null;
    recommended_action?: string;
    promotion_blockers?: string[];
    dashboard_summary: Record<string, unknown>;
    comparison: Record<string, unknown> | null;
  };
  rollback_history: ModelRollbackHistoryItem[];
  model_states: ModelOperationsModelState[];
  dashboard_policy: Record<string, unknown>;
};

export type SourceDataFeedDefinition = {
  feed_key: string;
  label: string;
  scope: string;
  domain: string;
  backend_target: string;
  source_type: string;
  cadence: string;
  ingestion_family: string;
  downstream_action: string;
  required_metadata: string[];
  adapter_key: string;
  adapter_notes: string;
  scheduled_supported: boolean;
  required_any_columns: string[][];
  accepted_columns: string[];
  template_url: string;
  requires_new_ingestion_path: boolean;
  default_reporting_granularity: string;
  feed_policy?: Record<string, unknown>;
  feed_mode?: "api" | "csv" | "manual" | "fallback" | "demo";
  csv_upload_enabled?: boolean;
  connector_status?: {
    enabled: boolean;
    connector_key: string;
    label: string;
    configured: boolean;
    status: string;
    last_run_status: string;
    last_run_at: string | null;
    last_successful_fetch_at: string | null;
    required_settings: string[];
    credential_values_exposed: boolean;
    notes: string;
  };
};

export type SourceDataFeedTypesResponse = {
  schema_version: string;
  phase_contract_schema_version: string;
  generated_at: string;
  scope: string;
  feed_count: number;
  feeds: SourceDataFeedDefinition[];
  feature_flags?: Record<string, boolean>;
  templates: Record<string, { filename: string; columns: string[]; example_row: Record<string, string> }>;
  template_contract_errors: string[];
  validation_error_catalog?: {
    schema_version: string;
    codes: Array<{
      code: string;
      severity: string;
      operator_message: string;
      remediation: string;
    }>;
  };
};

export type SourceDataValidationIssueRecord = {
  id: number;
  row_number: number | null;
  severity: "error" | "warning" | "info";
  code: string;
  column_name: string;
  message: string;
  safe_context: Record<string, unknown>;
  created_at: string;
};

export type SourceDataUploadEventRecord = {
  id: number;
  event_type: string;
  event_at: string;
  actor_username: string | null;
  metadata: Record<string, unknown>;
};

export type SourceDataDownstreamActionResult = {
  schema_version: string;
  action_key: string;
  action_label?: string;
  action_status: "available" | "unavailable" | "completed" | "queued" | "failed";
  requested_by_username?: string | null;
  started_at?: string;
  completed_at?: string;
  queued_at?: string;
  downstream_celery_task_id?: string;
  safe_reason?: string;
  triggers_sms?: boolean;
  promotes_model?: boolean;
  evidence?: Record<string, unknown>;
};

export type SourceDataDownstreamActionDefinition = {
  action_key: string;
  label: string;
  supported_ingestion_families: string[];
  safe_reason: string;
  mutates_downstream_evidence: boolean;
  triggers_sms: boolean;
  promotes_model: boolean;
  availability_status: "available" | "unavailable";
  unavailable_reason: string;
  recommended: boolean;
  latest_result: SourceDataDownstreamActionResult | null;
};

export type SourceDataUploadBatchRecord = {
  public_id: string;
  feed_key: string;
  domain: string;
  source_type: string;
  source_name: string;
  source_ref: string;
  source_timestamp: string | null;
  release_version: string;
  reporting_period_start: string | null;
  reporting_period_end: string | null;
  correction_mode: string;
  replacement_reason: string;
  operator_note: string;
  status:
    | "draft"
    | "uploaded"
    | "validating"
    | "validation_failed"
    | "ready_for_confirmation"
    | "confirming"
    | "imported"
    | "import_failed"
    | "cancelled"
    | "superseded";
  validation_status: "not_started" | "running" | "passed" | "failed";
  import_status: "not_started" | "running" | "imported" | "failed";
  row_count: number;
  accepted_count: number;
  rejected_count: number;
  warning_count: number;
  duplicate_of_public_id: string | null;
  replaces_upload_public_id: string | null;
  approval_status: "not_required" | "pending" | "approved" | "rejected" | "expired";
  approval_risk_category: string;
  approval_requested_by_username: string | null;
  approval_requested_at: string | null;
  approved_by_username: string | null;
  approved_at: string | null;
  approval_reason: string;
  approval_expires_at: string | null;
  validation_celery_task_id: string;
  import_celery_task_id: string;
  downstream_celery_task_id: string;
  domain_ingestion_run_type: string;
  domain_ingestion_run_id: number | null;
  surveillance_ingestion_run: number | null;
  population_exposure_ingestion_run: number | null;
  facility_readiness_ingestion_run_id: number | null;
  created_by_username: string | null;
  confirmed_by_username: string | null;
  confirmed_at: string | null;
  metadata: Record<string, unknown>;
  validation_summary: Record<string, unknown>;
  downstream_actions: SourceDataDownstreamActionDefinition[];
  validation_issues: SourceDataValidationIssueRecord[];
  events: SourceDataUploadEventRecord[];
  created_at: string;
  updated_at: string;
};

export type SourceDataUploadListResponse = {
  schema_version: string;
  count: number;
  results: SourceDataUploadBatchRecord[];
};

export type SourceDataUploadFilters = {
  feed_key?: string;
  domain?: string;
  status?: string;
  source_name?: string;
  actor?: string;
  date_from?: string;
  date_to?: string;
  limit?: number;
};

export type SourceDataUploadCreatePayload = {
  feed_key: string;
  source_name: string;
  source_timestamp: string;
  source_ref?: string;
  release_version?: string;
  reporting_period_start?: string;
  reporting_period_end?: string;
  correction_mode?: string;
  replacement_reason?: string;
  operator_note?: string;
  replaces_upload_public_id?: string;
  file: File;
};

export type SourceDataApprovalPayload = {
  action: "request" | "approve" | "reject";
  reason?: string;
};

export type SourceDataConfirmPayload = {
  allow_duplicate_replay?: boolean;
  force_async?: boolean;
};

export type SourceDataCancelPayload = {
  reason: string;
};

export type SourceDataDownstreamActionPayload = {
  action_key: string;
  reason?: string;
  as_of?: string;
  prediction_date?: string;
  prediction_dates?: string[];
  dataset_role?: "training" | "evaluation";
  force_async?: boolean;
};

export type SourceDataDownstreamActionResponse = SourceDataDownstreamActionResult & {
  batch: SourceDataUploadBatchRecord;
};

export type SourceDataConnectorRunRecord = {
  id: number;
  connector_key: string;
  target_feed_key: string;
  feed_mode: string;
  status: "running" | "success" | "failed" | "skipped";
  source_name: string;
  source_ref: string;
  fetched_record_count: number;
  upload_batch_public_id: string | null;
  error_summary: string;
  safe_metadata: Record<string, unknown>;
  requested_by_username: string | null;
  started_at: string;
  completed_at: string | null;
};

export type SourceDataConnectorRegistryResponse = {
  schema_version: string;
  generated_at: string;
  enabled: boolean;
  connectors: Array<NonNullable<SourceDataFeedDefinition["connector_status"]> & {
    target_feed_key: string;
    feed_mode: string;
    source_name: string;
    source_ref_prefix: string;
  }>;
};

export type SourceDataFeedModePayload = {
  feed_mode: "api" | "csv" | "manual" | "fallback" | "demo";
  csv_upload_enabled: boolean;
  authoritative_connector_key?: string;
  reason?: string;
};

export type SourceDataErrorFileResponse = {
  filename: string;
  content_type: string;
  row_count: number;
  payload: string;
  payload_sha256: string;
};

export type SourceDataCsvTemplateFileResponse = SourceDataErrorFileResponse & {
  feed_key: string;
};

export type SourceDataFreshnessStatus =
  | "current"
  | "due_soon"
  | "stale"
  | "missing"
  | "demo_backed"
  | "failed";

export type SourceDataFreshnessSource = {
  key: string;
  feed_key: string;
  label: string;
  domain: string;
  source_type: string;
  status: SourceDataFreshnessStatus;
  truth_state: string;
  expected_cadence: string;
  last_source_timestamp: string | null;
  last_import_timestamp: string | null;
  current_gap_days: number | null;
  record_count: number;
  recommended_action: string;
  source_path: string;
};

export type SourceDataFreshnessResponse = {
  schema_version: string;
  generated_at: string;
  state_counts: Record<string, number>;
  truth_state_counts: Record<string, number>;
  upload_status_counts: Record<string, number>;
  sources: SourceDataFreshnessSource[];
};

export type SourceDataOverviewRecentUpload = {
  public_id: string;
  feed_key: string;
  domain: string;
  source_type: string;
  source_name: string;
  status: string;
  validation_status: string;
  import_status: string;
  row_count: number;
  accepted_count: number;
  rejected_count: number;
  warning_count: number;
  created_by_username: string | null;
  confirmed_by_username: string | null;
  created_at: string | null;
  confirmed_at: string | null;
};

export type SourceDataSourceGap = {
  feed_key: string;
  label: string;
  status: SourceDataFreshnessStatus;
  truth_state: string;
  recommended_action: string;
  template_url: string;
};

export type SourceDataOverviewResponse = {
  schema_version: string;
  generated_at: string;
  freshness: SourceDataFreshnessResponse;
  feed_statuses: SourceDataFreshnessSource[];
  source_gaps: SourceDataSourceGap[];
  recent_uploads: SourceDataOverviewRecentUpload[];
  source_matrix_reference: string;
};

export type SourceDataOperationsAlert = {
  key: string;
  severity: "default" | "success" | "warning" | "danger" | "info";
  title: string;
  message: string;
  recommended_action: string;
};

export type SourceDataOperationsTaskRecord = {
  public_id: string;
  feed_key: string;
  status: string;
  import_celery_task_id?: string;
  validation_celery_task_id?: string;
  updated_at: string;
};

export type SourceDataOperationsResponse = {
  schema_version: string;
  generated_at: string;
  lookback_hours: number;
  metrics: {
    upload_count: number;
    recent_upload_count: number;
    validation_failure_count: number;
    import_failure_count: number;
    stale_feed_count: number;
    duplicate_attempt_count: number;
    status_counts: Record<string, number>;
  };
  worker_health: {
    status: "current" | "stale" | "missing" | "failed";
    latest_heartbeat_at: string | null;
    latest_task_name: string;
    latest_status: string;
    age_seconds: number | null;
    stale_after_seconds: number;
  };
  stuck_tasks: {
    stale_after_minutes: number;
    imports: SourceDataOperationsTaskRecord[];
    validations: SourceDataOperationsTaskRecord[];
  };
  retention: {
    raw_upload_retention_days: number;
    expired_raw_artifact_count: number;
    purged_artifact_count: number;
    next_artifact_expiry_at: string | null;
    cleanup_task_name: string;
  };
  alerts: SourceDataOperationsAlert[];
  production_controls: {
    backup_restore_reference: string;
    antivirus_scanning_hook: string;
    audit_review_reference: string;
  };
};

export type InteroperabilityAuditCheck = {
  key: string;
  title: string;
  status: "PASS" | "FAIL";
  count: number;
  summary: string;
};

export type InteroperabilityRunRecord = {
  public_id: string;
  direction: "IMPORT" | "EXPORT";
  exchange_type: string;
  system_key: string;
  system_name: string;
  mapping_version: string | null;
  retry_of: string | null;
  status: "DRAFT" | "READY_FOR_CONFIRMATION" | "COMPLETED" | "PARTIAL" | "FAILED" | "RETRY_CREATED";
  dry_run: boolean;
  source_file_name: string;
  endpoint_url: string;
  source_reference: string;
  records_seen: number;
  records_accepted: number;
  records_rejected: number;
  mapping_coverage: number;
  operator_username: string;
  error_summary: string;
  dry_run_preview: Record<string, unknown>;
  export_payload: Record<string, unknown>;
  started_at: string;
  completed_at: string | null;
  created_at: string;
  contract_errors: string[];
  items: Array<{
    id: number;
    row_number: number;
    external_identifier: string;
    internal_object_type: string;
    internal_object_public_id: string;
    internal_object_code: string;
    status: string;
    action: string;
    safe_context: Record<string, unknown>;
    source_record_ref: string;
    created_at: string;
  }>;
  errors: Array<{
    public_id: string;
    item_id: number | null;
    severity: "INFO" | "WARNING" | "ERROR";
    error_code: string;
    field_path: string;
    safe_message: string;
    remediation_hint: string;
    created_at: string;
  }>;
};

export type InteroperabilityDashboardResponse = {
  schema_version: "interoperability-contracts-v1";
  generated_at: string;
  exchange_inventory: Array<{
    exchange_type: string;
    label: string;
    direction: "IMPORT" | "EXPORT";
    source_owner: string;
    format: string;
    cadence: string;
    quality_risk: string;
    csv_first: boolean;
  }>;
  exchange_inventory_contract_errors?: string[];
  csv_templates: Record<string, { filename: string; columns: string[]; example_row: Record<string, string> }>;
  csv_template_contract_errors?: string[];
  connector_boundary: {
    schema_version: string;
    connector_interface: string[];
    auth_config_reference: string;
    paging_strategy: string;
    retry_policy: Record<string, unknown>;
    rate_limit_handling: string;
    failure_taxonomy: string[];
    failure_taxonomy_detail?: Record<string, Record<string, unknown>>;
    dry_run_mode: string;
    canonical_data_safety?: string;
  };
  connector_boundary_contract_errors?: string[];
  summary: {
    system_count: number;
    active_system_count: number;
    mapping_version_count: number;
    active_mapping_version_count: number;
    org_unit_mapping_count: number;
    active_org_unit_mapping_count: number;
    run_count: number;
    failed_run_count: number;
    latest_run_at: string | null;
    run_status_counts: Record<string, number>;
    audit_status: "pass" | "fail";
  };
  systems: Array<Record<string, unknown>>;
  mapping_versions: Array<Record<string, unknown>>;
  org_unit_mappings: Array<{
    public_id: string;
    system_key: string;
    mapping_version: string;
    external_identifier: string;
    external_display_name: string;
    internal_object_type: string;
    internal_object_public_id: string;
    internal_object_code: string;
    ward_name: string;
    facility_name: string;
    mapping_confidence: number;
    status: string;
    effective_date: string;
    retired_date: string | null;
  }>;
  runs: InteroperabilityRunRecord[];
  audit_checks: InteroperabilityAuditCheck[];
};

export type InteroperabilityOrgUnitMappingImportPayload = {
  system_key?: string;
  mapping_version_label?: string;
  source_file_name?: string;
  csv_text: string;
  confirm?: boolean;
  retry_of_public_id?: string | null;
};

export type InteroperabilityErrorFileResponse = {
  filename: string;
  content_type: string;
  row_count: number;
  payload: string;
  payload_sha256: string;
};

export type InteroperabilityCsvTemplateFileResponse = InteroperabilityErrorFileResponse & {
  exchange_type: string;
};

export type MessageTemplateApprovalStatus = "draft" | "pending_review" | "approved" | "rejected" | "retired";
export type MessageTemplateTranslationStatus =
  | "draft"
  | "needs_translation_review"
  | "approved"
  | "retired"
  | "blocked_source_retired";
export type MessageTemplateAudienceType = "chv" | "household" | "facility_contact" | "county_operator" | "system_operator";
export type MessageTemplateChannel = "sms" | "ussd" | "dashboard" | "offline_chv_bundle";

export type MessageTemplateRecord = {
  public_id: string;
  template_key: string;
  audience_type: MessageTemplateAudienceType;
  channel: MessageTemplateChannel;
  language: string;
  version: number;
  title: string;
  body: string;
  placeholders: string[];
  approval_status: MessageTemplateApprovalStatus;
  approved_by: number | null;
  approved_by_username: string;
  approved_at: string | null;
  retired_at: string | null;
  translation_status?: MessageTemplateTranslationStatus;
  source_template?: string;
  source_template_key?: string;
  source_template_version?: number | null;
  translation_reviewed_by?: number | null;
  translation_reviewed_by_username?: string;
  translation_reviewed_at?: string | null;
  translation_review_notes?: string;
  owner: string;
  risk_level: "low" | "medium" | "high" | "critical";
  public_health_caveats: string;
  lineage_metadata: Record<string, unknown>;
  created_by: number | null;
  created_by_username: string;
  created_at: string;
  updated_at: string;
  preview: {
    context: Record<string, string>;
    rendered_body: string;
    declared_placeholders: string[];
    discovered_placeholders: string[];
    render_error: string;
  };
  audience_preview: {
    audience_type: MessageTemplateAudienceType;
    channel: MessageTemplateChannel;
    risk_level: string;
    scope: string;
    consent_requirement: string;
    emergency_override_allowed: boolean;
    public_health_caveats: string;
  };
  usage_summary: {
    alert_count: number;
    chv_message_count: number;
    facility_update_request_count: number;
    total_delivery_count: number;
  };
};

export type MessageLanguagePreviewRecord = {
  language: string;
  label: string;
  exists: boolean;
  public_id: string;
  title: string;
  approval_status: MessageTemplateApprovalStatus | "";
  translation_status: MessageTemplateTranslationStatus | "";
  source_template: string;
  source_template_key: string;
  source_template_version: number | null;
  body: string;
  rendered_body: string;
  delivery_rendered_body: string;
  requested_language: string;
  resolved_language: string;
  fallback_used: boolean;
  placeholders: string[];
  placeholder_parity_status: "source" | "pass" | "warning" | "missing";
  placeholder_warnings: string[];
  render_error: string;
};

export type TemplateLanguageCoverageVariant = {
  language: string;
  label: string;
  exists: boolean;
  public_id: string;
  title: string;
  approval_status: MessageTemplateApprovalStatus | "";
  translation_status: MessageTemplateTranslationStatus | "";
  placeholder_parity_status: "source" | "pass" | "warning" | "missing";
  warnings: string[];
};

export type TemplateLanguageCoverageWarning = {
  language: string;
  label: string;
  message: string;
};

export type TemplateLanguageCoverageRow = {
  template_key: string;
  version: number;
  title: string;
  audience_type: MessageTemplateAudienceType;
  channel: MessageTemplateChannel;
  risk_level: "low" | "medium" | "high" | "critical";
  owner: string;
  requires_translation: boolean;
  present_languages: string[];
  missing_languages: string[];
  missing_language_labels: string[];
  variants: TemplateLanguageCoverageVariant[];
  placeholder_warnings: TemplateLanguageCoverageWarning[];
  translation_review_warnings: TemplateLanguageCoverageWarning[];
};

export type TemplateLanguageCoverageMatrix = {
  supported_languages: Array<{ code: string; label: string }>;
  row_count: number;
  missing_variant_count: number;
  placeholder_warning_count: number;
  translation_review_warning_count: number;
  rows: TemplateLanguageCoverageRow[];
};

export type MissingTranslationDashboardItem = {
  issue_type:
    | "missing_variant"
    | "placeholder_parity"
    | "translation_review"
    | "missing_ussd_menu"
    | "ussd_route_parity"
    | "offline_guidance_fallback";
  severity: "low" | "medium" | "high";
  template_key: string;
  version: number;
  version_label?: string;
  title: string;
  audience_type: MessageTemplateAudienceType;
  channel: MessageTemplateChannel;
  language: string;
  label: string;
  message: string;
};

export type MissingTranslationDashboard = {
  total_issue_count: number;
  by_issue_type: Record<string, number>;
  by_severity: Record<string, number>;
  items: MissingTranslationDashboardItem[];
};

export type MessageDeliveryOutcomeRow = {
  audience_type: string;
  channel: string;
  status: string;
  count: number;
  latest_at: string | null;
};

export type MessageDeliveryTemplateRow = {
  template_key: string;
  template_version: number | null;
  count: number;
  statuses: Record<string, number>;
  latest_at: string | null;
};

export type MessageDeliveryReachRow = {
  audience_type: string;
  channel: string;
  message_count: number;
  unique_recipient_count: number;
  successful_count: number;
  failed_count: number;
  success_rate_pct: number;
  latest_at: string | null;
};

export type MessageOptOutMonitoringRow = {
  audience_type: string;
  channel: string;
  current_opt_out_count: number;
  blocked_opt_out_event_count: number;
  latest_opt_out_at: string | null;
  latest_blocked_at: string | null;
};

export type MessageOptOutSummary = {
  total_current_opt_out_count: number;
  total_blocked_opt_out_event_count: number;
  by_audience_channel: MessageOptOutMonitoringRow[];
};

export type MessageDeliveryRecord = {
  model: string;
  public_id: string;
  audience_type: string;
  channel: string;
  template_key: string;
  template_version: number | null;
  requested_language: string;
  resolved_language: string;
  fallback_used: boolean;
  status: string;
  created_at: string;
};

export type MessageDeliverySummary = {
  total_count: number;
  successful_count: number;
  failed_count: number;
  success_rate_pct: number;
  by_audience_channel_status: MessageDeliveryOutcomeRow[];
  by_template: MessageDeliveryTemplateRow[];
  template_usage_by_version: MessageDeliveryTemplateRow[];
  reach_by_audience_channel: MessageDeliveryReachRow[];
  opt_out_summary: MessageOptOutSummary;
  recent_records: MessageDeliveryRecord[];
};

export type UssdGovernanceAnalytics = {
  schema_version: "ussd-menu-governance-phase-3-v1";
  total_logs: number;
  total_sessions: number;
  completed_sessions: number;
  invalid_input_sessions: number;
  abandoned_sessions: number;
  safe_fallback_sessions: number;
  completion_rate_pct: number;
  invalid_input_rate_pct: number;
  abandonment_rate_pct: number;
  by_outcome: Array<{
    session_outcome: string;
    log_count: number;
    session_count: number;
    latest_at: string | null;
  }>;
  by_language: Array<{
    language: string;
    log_count: number;
    session_count: number;
    invalid_input_count: number;
    abandoned_count: number;
  }>;
  by_menu_version: Array<{
    menu_key: string;
    menu_version_label: string;
    language: string;
    log_count: number;
    session_count: number;
    completed_count: number;
    invalid_input_count: number;
    abandoned_count: number;
    latest_at: string | null;
  }>;
  recent_logs: Array<{
    id: number;
    session_id: string;
    menu_key: string;
    menu_version_label: string;
    language: string;
    requested_language: string;
    resolved_language: string;
    fallback_used: boolean;
    menu_level: string;
    session_outcome: string;
    invalid_option: boolean;
    abandonment_reason: string;
    is_terminal: boolean;
    created_at: string;
  }>;
};

export type UssdRoutePreviewRecord = {
  route: string;
  route_label: string;
  node_key: string;
  response_type: string;
  body: string;
  response_text: string;
  character_count: number;
};

export type UssdMenuLanguageRoutePreview = {
  language: string;
  label: string;
  exists: boolean;
  public_id: string;
  title: string;
  approval_status: "DRAFT" | "APPROVED" | "RETIRED" | "";
  translation_status: MessageTemplateTranslationStatus | "";
  safe_fallback_copy: string;
  requested_language: string;
  resolved_language: string;
  fallback_used: boolean;
  route_count: number;
  routes: UssdRoutePreviewRecord[];
  warnings: string[];
};

export type UssdRouteTreePreviewRecord = {
  menu_key: string;
  source_menu_version: string;
  source_version_label: string;
  source_title: string;
  languages: UssdMenuLanguageRoutePreview[];
};

export type UssdMenuVersionRecord = {
  public_id: string;
  menu_key: string;
  version_label: string;
  language: string;
  title: string;
  approval_status: "DRAFT" | "APPROVED" | "RETIRED";
  approved_by: number | null;
  approved_by_username: string;
  approved_at: string | null;
  retired_at: string | null;
  translation_status?: MessageTemplateTranslationStatus;
  source_menu_version?: string;
  source_menu_version_label?: string;
  translation_reviewed_by?: number | null;
  translation_reviewed_by_username?: string;
  translation_reviewed_at?: string | null;
  translation_review_notes?: string;
  is_active: boolean;
  safe_fallback_copy: string;
  lineage_metadata: Record<string, unknown>;
  created_by: number | null;
  created_by_username: string;
  created_at: string;
  updated_at: string;
  route_count: number;
  node_count: number;
  route_tree_preview: UssdRoutePreviewRecord[];
  validation_status: "pass" | "fail";
  validation_messages: string[];
};

export type OfflineGuidancePreviewItem = {
  guidance_public_id: string;
  template_key: string;
  version: number;
  title: string;
  language: string;
  requested_language: string;
  resolved_language: string;
  fallback_used: boolean;
  audience_type: MessageTemplateAudienceType;
  body: string;
  rendered_body: string;
  public_health_caveats: string;
};

export type OfflineGuidanceLanguagePreview = {
  language: string;
  label: string;
  requested_language: string;
  resolved_language: string;
  fallback_used: boolean;
  item_count: number;
  items: OfflineGuidancePreviewItem[];
  warnings: string[];
};

export type LocalizationRolloutCounterRecord = {
  key: string;
  count: number;
};

export type LocalizationFallbackMetric = {
  surface: string;
  total_count: number;
  fallback_count: number;
  fallback_rate_pct: number;
  by_requested_language: LocalizationRolloutCounterRecord[];
  by_resolved_language: LocalizationRolloutCounterRecord[];
  fallback_by_resolved_language: LocalizationRolloutCounterRecord[];
};

export type LocalizationReviewAgeRecord = {
  model: string;
  public_id: string;
  key: string;
  language: string;
  status: string;
  age_days: number;
};

export type LocalizationRolloutSnapshot = {
  schema_version: "chv-localization-rollout-phase-7-v1";
  generated_at: string;
  supported_languages: string[];
  default_language: string;
  chv_preferred_language_counts: LocalizationRolloutCounterRecord[];
  active_chv_count: number;
  device_preferred_language_counts: LocalizationRolloutCounterRecord[];
  active_device_count: number;
  offline_bundle_requests_by_language: LocalizationFallbackMetric;
  fallback_metrics: LocalizationFallbackMetric[];
  fallback_rate_pct: number;
  ussd_sessions_by_language_and_outcome: Array<{ language: string; outcome: string; count: number }>;
  chv_sms_deliveries_by_language_and_outcome: Array<{ language: string; outcome: string; count: number }>;
  missing_translation_count: number;
  translation_review_age: {
    pending_review_count: number;
    max_age_days: number;
    average_age_days: number;
    oldest_records: LocalizationReviewAgeRecord[];
  };
  rollout_path: Array<{ step: string; status: string }>;
};

export type MessageGovernanceDashboardResponse = {
  schema_version: "message-management-phase-7-v1";
  generated_at: string;
  filters: Record<string, string>;
  available_filters: {
    audience_types: MessageTemplateAudienceType[];
    channels: MessageTemplateChannel[];
    languages: string[];
    approval_statuses: MessageTemplateApprovalStatus[];
  };
  summary: {
    template_count: number;
    approved_template_count: number;
    pending_review_template_count: number;
    draft_template_count: number;
    retired_template_count: number;
    language_count: number;
    languages: string[];
    audience_counts: Record<string, number>;
    channel_counts: Record<string, number>;
    approval_status_counts: Record<string, number>;
    unapproved_high_risk_template_count: number;
    delivery_record_count: number;
    communication_reach_count: number;
    delivery_failure_count: number;
    delivery_success_rate_pct: number;
    opt_out_count: number;
    opt_out_blocked_count: number;
    template_usage_version_count: number;
    ussd_total_sessions: number;
    ussd_completion_rate_pct: number;
    ussd_invalid_input_rate_pct: number;
    ussd_abandonment_rate_pct: number;
    ussd_menu_version_count: number;
    active_ussd_menu_version_count: number;
    missing_translation_count: number;
    placeholder_parity_warning_count: number;
    translation_review_warning_count: number;
    missing_translation_issue_count: number;
    offline_guidance_language_count: number;
    strict_localization_issue_count: number;
    localization_fallback_rate_pct: number;
    audit_status: "pass" | "fail";
  };
  templates: MessageTemplateRecord[];
  template_language_coverage: TemplateLanguageCoverageMatrix;
  missing_translation_dashboard: MissingTranslationDashboard;
  ussd_menu_versions: UssdMenuVersionRecord[];
  ussd_route_tree_preview: UssdRouteTreePreviewRecord[];
  offline_guidance_preview: OfflineGuidanceLanguagePreview[];
  delivery_summary: MessageDeliverySummary;
  ussd_analytics: UssdGovernanceAnalytics;
  audit: {
    schema_version: string;
    overall_status: "pass" | "fail";
    strict_localization_issue_count: number;
    localization_rollout: LocalizationRolloutSnapshot;
    checks: Array<{
      id: string;
      status: "pass" | "fail";
      answer: string;
      evidence: Record<string, unknown>;
      gaps: string[];
    }>;
  };
};

export type MessageTemplateDetailResponse = {
  schema_version: "message-management-phase-7-v1";
  generated_at: string;
  template: MessageTemplateRecord;
  version_history: MessageTemplateRecord[];
  language_variants: MessageTemplateRecord[];
  side_by_side_preview: MessageLanguagePreviewRecord[];
  delivery_summary: MessageDeliverySummary;
};

export type FetchMessageGovernanceParams = {
  q?: string;
  audience_type?: string;
  channel?: string;
  language?: string;
  approval_status?: string;
  date_from?: string;
  date_to?: string;
};

export type MessageTemplateApprovalPayload = {
  action: "approve" | "request_review" | "reject" | "retire";
  reason?: string;
};

export type UssdMenuVersionApprovalPayload = {
  action: "approve" | "request_review" | "reject" | "retire";
  reason?: string;
};

export type FetchOperationalKpiDashboardParams = {
  date_from?: string;
  date_to?: string;
  ward_id?: number | string;
  sub_county?: string;
  source_channel?: string;
};

export type OperationalKpiMeExportResponse = {
  schema_version: "operational-kpi-me-export-v1";
  generated_at: string;
  filters: {
    date_from: string;
    date_to: string;
    ward_id: number | null;
    sub_county: string;
    source_channel: string;
  };
  format: "json" | "csv";
  filename: string;
  content_type: string;
  row_count: number;
  data_sha256: string;
  payload_sha256: string;
  payload: string;
  audit_status: "pass" | "warning" | "fail";
  audit_issue_count: number;
};

export type FetchOperationalKpiMeExportParams = FetchOperationalKpiDashboardParams & {
  export_format?: "json" | "csv";
};

export class DashboardStepUpRequiredError extends Error {
  code = "step_up_required" as const;
  purpose: StepUpPurpose;

  constructor(message: string, purpose: StepUpPurpose) {
    super(message);
    this.name = "DashboardStepUpRequiredError";
    this.purpose = purpose;
  }
}

async function requestDashboardRoute<T>(
  path: string,
  init: RequestInit = {},
  options: { retriedAfterStepUp?: boolean } = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  const isFormDataBody = typeof FormData !== "undefined" && init.body instanceof FormData;
  if (!headers.has("Content-Type") && init.body && !isFormDataBody) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(path, {
    ...init,
    credentials: "include",
    headers,
  });

  if (!response.ok) {
    let detail = "Unable to load dashboard data.";
    let stepUpPurpose: StepUpPurpose | null = null;

    try {
      const data = (await response.json()) as { detail?: string; code?: string; purpose?: string };
      detail = data.detail ?? detail;
      if (data.code === "step_up_required" && data.purpose && isStepUpPurpose(data.purpose)) {
        stepUpPurpose = data.purpose;
      }
    } catch {
      // Keep the generic message.
    }

    if (stepUpPurpose) {
      if (!options.retriedAfterStepUp) {
        try {
          await requestStepUp(stepUpPurpose);
          return requestDashboardRoute<T>(path, init, { retriedAfterStepUp: true });
        } catch (error) {
          if (!(error instanceof StepUpUnavailableError)) {
            throw error;
          }
        }
      }

      throw new DashboardStepUpRequiredError(detail, stepUpPurpose);
    }

    throw new Error(detail);
  }

  return (await response.json()) as T;
}

export async function fetchOverviewDataViaBff() {
  return requestDashboardRoute<OverviewRouteResponse>("/api/dashboard/overview");
}

export async function fetchWardRiskDataViaBff(params: FetchWardRiskDataParams = {}) {
  const searchParams = new URLSearchParams();

  if (params.county) {
    searchParams.set("county", params.county);
  }
  if (params.q) {
    searchParams.set("q", params.q);
  }
  if (params.risk) {
    searchParams.set("risk", params.risk);
  }
  if (params.sub_county) {
    searchParams.set("sub_county", params.sub_county);
  }
  if (params.ordering) {
    searchParams.set("ordering", params.ordering);
  }

  const query = searchParams.toString();
  return requestDashboardRoute<WardsRouteResponse>(`/api/dashboard/wards${query ? `?${query}` : ""}`);
}

export async function fetchWardDetailViaBff(wardId: number) {
  return requestDashboardRoute<WardIntelligenceRouteResponse>(`/api/dashboard/wards/${wardId}`);
}

export async function fetchAlertsDataViaBff() {
  return requestDashboardRoute<PaginatedResponse<AlertRecord>>("/api/dashboard/alerts");
}

export async function fetchAlertByIdViaBff(alertId: number) {
  return requestDashboardRoute<AlertDetailRouteResponse>(`/api/dashboard/alerts/${alertId}`);
}

export async function createSensitiveExportViaBff(payload: SensitiveExportCreatePayload) {
  return requestDashboardRoute<SensitiveExportRecord>("/api/dashboard/sensitive-exports", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function downloadSensitiveExportViaBff(publicId: string) {
  return requestDashboardRoute<SensitiveExportDownloadResponse>(
    `/api/dashboard/sensitive-exports/${encodeURIComponent(publicId)}/download`,
  );
}

export function downloadSensitiveExportFile(download: SensitiveExportDownloadResponse) {
  const blob = new Blob([download.payload], { type: `${download.content_type};charset=utf-8;` });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = download.filename;
  link.click();
  URL.revokeObjectURL(url);
}

export async function triggerAlertViaBff(payload: TriggerAlertRequest) {
  return requestDashboardRoute<TriggerAlertResponse>("/api/dashboard/alerts/trigger", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchTriggerAlertRequestStatusViaBff(requestId: string) {
  return requestDashboardRoute<TriggerAlertRequestStatusResponse>(
    `/api/dashboard/alerts/trigger/requests/${encodeURIComponent(requestId)}`,
  );
}

export async function fetchTriggerAlertContextViaBff(params: { ward_id: number }) {
  const searchParams = new URLSearchParams();
  searchParams.set("ward_id", String(params.ward_id));
  return requestDashboardRoute<TriggerContextResponse>(`/api/dashboard/alerts/trigger/context?${searchParams.toString()}`);
}

export async function fetchTriggerAlertPreviewViaBff(payload: {
  ward_id: number;
  trigger_type: TriggerActionType;
  message_override?: string;
  template_key?: string;
  template_version?: number | null;
  template_language?: string;
  template_context?: Record<string, string | number | boolean | null>;
}) {
  return requestDashboardRoute<TriggerPreviewResponse>("/api/dashboard/alerts/trigger/preview", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function runScenarioSimulationViaBff(payload: {
  scenario_id: "RAINFALL_INCREASE" | "RESPONSE_DELAY";
  rainfall_uplift_percent?: number;
  response_delay_hours?: number;
}) {
  return requestDashboardRoute<ScenarioSimulationRun>("/api/dashboard/simulation", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchChvDataViaBff() {
  return requestDashboardRoute<PaginatedResponse<ChvRecord>>("/api/dashboard/chvs");
}

export async function fetchChvOperationsDataViaBff() {
  return requestDashboardRoute<ChvOperationsRecord[]>("/api/dashboard/chvs/operations");
}

export async function fetchChvOfflineMonitoringViaBff() {
  return requestDashboardRoute<ChvOfflineMonitoringSnapshot>("/api/dashboard/chvs/offline-monitoring");
}

export async function fetchChvActivityViaBff(publicId: string) {
  return requestDashboardRoute<ChvActivityRecord[]>(`/api/dashboard/chvs/${encodeURIComponent(publicId)}/activity`);
}

export async function fetchChvMessagesViaBff(publicId: string) {
  return requestDashboardRoute<ChvMessageRecord[]>(`/api/dashboard/chvs/${encodeURIComponent(publicId)}/messages`);
}

export async function createChvMessageViaBff(publicId: string, payload: CreateChvMessagePayload) {
  return requestDashboardRoute<ChvMessageRecord>(`/api/dashboard/chvs/${encodeURIComponent(publicId)}/messages`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchChvCoverageRequestsViaBff(params: FetchChvCoverageRequestsParams = {}) {
  const searchParams = new URLSearchParams();

  if (params.page) {
    searchParams.set("page", String(params.page));
  }
  if (params.ward_id) {
    searchParams.set("ward_id", String(params.ward_id));
  }
  if (params.status) {
    searchParams.set("status", params.status);
  }
  if (params.priority) {
    searchParams.set("priority", params.priority);
  }
  if (params.trigger_source) {
    searchParams.set("trigger_source", params.trigger_source);
  }
  if (params.overdue !== undefined) {
    searchParams.set("overdue", String(params.overdue));
  }
  if (params.has_linked_alerts !== undefined) {
    searchParams.set("has_linked_alerts", String(params.has_linked_alerts));
  }

  const query = searchParams.toString();
  return requestDashboardRoute<PaginatedResponse<ChvCoverageRequestRecord>>(
    `/api/dashboard/chvs/coverage-requests${query ? `?${query}` : ""}`,
  );
}

export async function fetchChvCoverageRequestDetailViaBff(publicId: string) {
  return requestDashboardRoute<ChvCoverageRequestRecord>(
    `/api/dashboard/chvs/coverage-requests/${encodeURIComponent(publicId)}`,
  );
}

export async function createChvCoverageRequestViaBff(payload: CreateChvCoverageRequestPayload) {
  return requestDashboardRoute<ChvCoverageRequestRecord>("/api/dashboard/chvs/coverage-requests", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchChvCoverageRequestFromAlertPrefillViaBff(
  payload: ChvCoverageRequestFromAlertPrefillPayload,
) {
  return requestDashboardRoute<ChvCoverageRequestFromAlertPrefillResponse>(
    "/api/dashboard/chvs/coverage-requests/from-alert",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function assignChvCoverageRequestViaBff(publicId: string, payload: AssignChvCoverageRequestPayload) {
  return requestDashboardRoute<ChvCoverageRequestRecord>(
    `/api/dashboard/chvs/coverage-requests/${encodeURIComponent(publicId)}/assign`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function fetchPreparednessActionsViaBff(params: FetchPreparednessActionsParams = {}) {
  const searchParams = new URLSearchParams();

  searchParams.set("page_size", String(params.page_size ?? 200));

  if (params.page) {
    searchParams.set("page", String(params.page));
  }
  if (params.ward_id) {
    searchParams.set("ward_id", String(params.ward_id));
  }
  if (params.facility_id) {
    searchParams.set("facility_id", String(params.facility_id));
  }
  if (params.chv_id) {
    searchParams.set("chv_id", String(params.chv_id));
  }
  if (params.status) {
    searchParams.set("status", params.status);
  } else if (params.statuses?.length) {
    searchParams.set("status", params.statuses.join(","));
  }
  if (params.action_type) {
    searchParams.set("action_type", params.action_type);
  }
  if (params.priority) {
    searchParams.set("priority", params.priority);
  }
  if (params.source_trigger_type) {
    searchParams.set("source_trigger_type", params.source_trigger_type);
  }
  if (params.assigned) {
    searchParams.set("assigned", params.assigned);
  }
  if (params.overdue !== undefined) {
    searchParams.set("overdue", String(params.overdue));
  }
  if (params.ordering) {
    searchParams.set("ordering", params.ordering);
  }

  return requestDashboardRoute<PaginatedResponse<PreparednessActionRecord>>(
    `/api/dashboard/preparedness-actions?${searchParams.toString()}`,
  );
}

export async function fetchPreparednessActionViaBff(publicId: string) {
  return requestDashboardRoute<PreparednessActionRecord>(
    `/api/dashboard/preparedness-actions/${encodeURIComponent(publicId)}`,
  );
}

export async function updatePreparednessActionViaBff(
  publicId: string,
  payload: PreparednessActionTransitionPayload,
) {
  return requestDashboardRoute<PreparednessActionRecord>(
    `/api/dashboard/preparedness-actions/${encodeURIComponent(publicId)}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
  );
}

export async function fetchFacilityDataViaBff() {
  return requestDashboardRoute<FacilityListRouteResponse>("/api/dashboard/facilities");
}

export async function fetchFacilityByIdViaBff(facilityId: number) {
  return requestDashboardRoute<FacilityIntelligenceRouteResponse>(`/api/dashboard/facilities/${facilityId}`);
}

export type CreateFacilityReadinessReviewPayload = {
  notes?: string;
};

export async function createFacilityReadinessReviewViaBff(
  facilityId: number,
  payload: CreateFacilityReadinessReviewPayload,
) {
  return requestDashboardRoute<FacilityReadinessReviewSummary>(
    `/api/dashboard/facilities/${facilityId}/readiness-reviews`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export type AcknowledgeFacilityReadinessReviewPayload = {
  notes?: string;
};

export async function acknowledgeFacilityReadinessReviewViaBff(
  publicId: string,
  payload: AcknowledgeFacilityReadinessReviewPayload,
) {
  return requestDashboardRoute<FacilityReadinessReviewSummary>(
    `/api/dashboard/facility-readiness/reviews/${encodeURIComponent(publicId)}/acknowledge`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export type CreateFacilityUpdateRequestPayload = {
  message_body?: string;
  channel?: "SMS" | "EMAIL" | "SYSTEM";
};

export async function createFacilityUpdateRequestViaBff(
  reviewPublicId: string,
  payload: CreateFacilityUpdateRequestPayload,
) {
  return requestDashboardRoute<FacilityReadinessUpdateRequestSummary>(
    `/api/dashboard/facility-readiness/reviews/${encodeURIComponent(reviewPublicId)}/update-requests`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export type CreateFacilityEscalationPayload = {
  reason?: string;
  severity?: "LOW" | "MEDIUM" | "HIGH";
  assigned_to?: number | null;
};

export async function createFacilityEscalationViaBff(
  reviewPublicId: string,
  payload: CreateFacilityEscalationPayload,
) {
  return requestDashboardRoute<FacilityReadinessEscalationSummary>(
    `/api/dashboard/facility-readiness/reviews/${encodeURIComponent(reviewPublicId)}/escalations`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function fetchWardMapViaBff() {
  return requestDashboardRoute<WardMapResponse>("/api/dashboard/maps/wards");
}

export async function fetchTopbarDataViaBff() {
  return requestDashboardRoute<TopbarData>("/api/dashboard/topbar");
}

export async function fetchNotificationStreamTokenViaBff() {
  return requestDashboardRoute<DashboardNotificationStreamToken>("/api/dashboard/notifications/stream-token");
}

export async function markNotificationSeenViaBff(publicId: string) {
  return requestDashboardRoute<DashboardNotification>(`/api/dashboard/notifications/${publicId}/seen`, {
    method: "POST",
  });
}

export async function acknowledgeNotificationViaBff(publicId: string) {
  return requestDashboardRoute<DashboardNotification>(`/api/dashboard/notifications/${publicId}/acknowledge`, {
    method: "POST",
  });
}

export async function dismissNotificationViaBff(publicId: string) {
  return requestDashboardRoute<DashboardNotification>(`/api/dashboard/notifications/${publicId}/dismiss`, {
    method: "POST",
  });
}

export async function markAllNotificationsSeenViaBff() {
  return requestDashboardRoute<{ count: number; unread_count: number; results: DashboardNotification[] }>(
    "/api/dashboard/notifications/mark-all-seen",
    {
      method: "POST",
    },
  );
}

export async function fetchSystemDataViaBff() {
  return requestDashboardRoute<SystemRouteResponse>("/api/dashboard/system");
}

export async function fetchMessageGovernanceDashboardViaBff(params: FetchMessageGovernanceParams = {}) {
  const searchParams = new URLSearchParams();

  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") {
      searchParams.set(key, String(value));
    }
  }

  const query = searchParams.toString();
  return requestDashboardRoute<MessageGovernanceDashboardResponse>(
    `/api/dashboard/message-governance${query ? `?${query}` : ""}`,
  );
}

export async function fetchMessageTemplateDetailViaBff(publicId: string) {
  return requestDashboardRoute<MessageTemplateDetailResponse>(
    `/api/dashboard/message-governance/templates/${encodeURIComponent(publicId)}`,
  );
}

export async function approveMessageTemplateViaBff(
  publicId: string,
  payload: MessageTemplateApprovalPayload,
) {
  return requestDashboardRoute<MessageTemplateDetailResponse>(
    `/api/dashboard/message-governance/templates/${encodeURIComponent(publicId)}/approval`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function approveUssdMenuVersionViaBff(
  publicId: string,
  payload: UssdMenuVersionApprovalPayload,
) {
  return requestDashboardRoute<UssdMenuVersionRecord>(
    `/api/dashboard/message-governance/ussd-menu-versions/${encodeURIComponent(publicId)}/approval`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function fetchOperationalKpiDashboardViaBff(params: FetchOperationalKpiDashboardParams = {}) {
  const searchParams = new URLSearchParams();

  if (params.date_from) {
    searchParams.set("date_from", params.date_from);
  }
  if (params.date_to) {
    searchParams.set("date_to", params.date_to);
  }
  if (params.ward_id) {
    searchParams.set("ward_id", String(params.ward_id));
  }
  if (params.sub_county) {
    searchParams.set("sub_county", params.sub_county);
  }
  if (params.source_channel) {
    searchParams.set("source_channel", params.source_channel);
  }

  const query = searchParams.toString();
  return requestDashboardRoute<OperationalKpiDashboardResponse>(
    `/api/dashboard/operational-metrics${query ? `?${query}` : ""}`,
  );
}

export async function fetchModelOperationsHealthViaBff() {
  return requestDashboardRoute<ModelOperationsHealthResponse>("/api/dashboard/model-health");
}

export async function fetchSourceDataFeedTypesViaBff() {
  return requestDashboardRoute<SourceDataFeedTypesResponse>("/api/dashboard/source-data/feed-types");
}

export async function fetchSourceDataOverviewViaBff() {
  return requestDashboardRoute<SourceDataOverviewResponse>("/api/dashboard/source-data/overview");
}

export async function fetchSourceDataFreshnessViaBff() {
  return requestDashboardRoute<SourceDataFreshnessResponse>("/api/dashboard/source-data/freshness");
}

export async function fetchSourceDataOperationsViaBff() {
  return requestDashboardRoute<SourceDataOperationsResponse>("/api/dashboard/source-data/operations");
}

export async function fetchSourceDataConnectorsViaBff() {
  return requestDashboardRoute<SourceDataConnectorRegistryResponse>("/api/dashboard/source-data/connectors");
}

export async function refreshSourceDataConnectorViaBff(connectorKey: string, payload: { force?: boolean; options?: Record<string, unknown> } = {}) {
  return requestDashboardRoute<SourceDataConnectorRunRecord>(
    `/api/dashboard/source-data/connectors/${encodeURIComponent(connectorKey)}/refresh`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function updateSourceDataFeedModeViaBff(feedKey: string, payload: SourceDataFeedModePayload) {
  return requestDashboardRoute<Pick<SourceDataFeedDefinition, "feed_mode" | "csv_upload_enabled" | "connector_status">>(
    `/api/dashboard/source-data/feed-modes/${encodeURIComponent(feedKey)}`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function fetchSourceDataUploadsViaBff(params: SourceDataUploadFilters = {}) {
  const searchParams = new URLSearchParams();

  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") {
      searchParams.set(key, String(value));
    }
  }

  const query = searchParams.toString();
  return requestDashboardRoute<SourceDataUploadListResponse>(
    `/api/dashboard/source-data/uploads${query ? `?${query}` : ""}`,
  );
}

export async function fetchSourceDataUploadViaBff(publicId: string) {
  return requestDashboardRoute<SourceDataUploadBatchRecord>(
    `/api/dashboard/source-data/uploads/${encodeURIComponent(publicId)}`,
  );
}

export async function createSourceDataUploadViaBff(payload: SourceDataUploadCreatePayload) {
  const formData = new FormData();
  formData.set("feed_key", payload.feed_key);
  formData.set("source_name", payload.source_name);
  formData.set("source_timestamp", payload.source_timestamp);
  formData.set("file", payload.file);

  for (const field of [
    "source_ref",
    "release_version",
    "reporting_period_start",
    "reporting_period_end",
    "correction_mode",
    "replacement_reason",
    "operator_note",
    "replaces_upload_public_id",
  ] as const) {
    const value = payload[field];
    if (value !== undefined && value !== "") {
      formData.set(field, value);
    }
  }

  return requestDashboardRoute<SourceDataUploadBatchRecord>("/api/dashboard/source-data/uploads", {
    method: "POST",
    body: formData,
  });
}

export async function validateSourceDataUploadViaBff(publicId: string) {
  return requestDashboardRoute<SourceDataUploadBatchRecord>(
    `/api/dashboard/source-data/uploads/${encodeURIComponent(publicId)}/validate`,
    {
      method: "POST",
      body: JSON.stringify({}),
    },
  );
}

export async function approveSourceDataUploadViaBff(publicId: string, payload: SourceDataApprovalPayload) {
  return requestDashboardRoute<SourceDataUploadBatchRecord>(
    `/api/dashboard/source-data/uploads/${encodeURIComponent(publicId)}/approval`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function confirmSourceDataUploadViaBff(publicId: string, payload: SourceDataConfirmPayload = {}) {
  return requestDashboardRoute<SourceDataUploadBatchRecord>(
    `/api/dashboard/source-data/uploads/${encodeURIComponent(publicId)}/confirm`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function cancelSourceDataUploadViaBff(publicId: string, payload: SourceDataCancelPayload) {
  return requestDashboardRoute<SourceDataUploadBatchRecord>(
    `/api/dashboard/source-data/uploads/${encodeURIComponent(publicId)}/cancel`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function runSourceDataDownstreamActionViaBff(
  publicId: string,
  payload: SourceDataDownstreamActionPayload,
) {
  return requestDashboardRoute<SourceDataDownstreamActionResponse>(
    `/api/dashboard/source-data/uploads/${encodeURIComponent(publicId)}/downstream-actions`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function downloadSourceDataErrorsFile(download: SourceDataErrorFileResponse) {
  const blob = new Blob([download.payload], { type: `${download.content_type};charset=utf-8;` });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = download.filename;
  link.click();
  URL.revokeObjectURL(url);
}

export async function fetchInteroperabilityDashboardViaBff() {
  return requestDashboardRoute<InteroperabilityDashboardResponse>("/api/dashboard/interoperability");
}

export async function fetchInteroperabilityRunViaBff(publicId: string) {
  return requestDashboardRoute<InteroperabilityRunRecord>(
    `/api/dashboard/interoperability/runs/${encodeURIComponent(publicId)}`,
  );
}

export async function createInteroperabilityOrgUnitMappingImportViaBff(
  payload: InteroperabilityOrgUnitMappingImportPayload,
) {
  return requestDashboardRoute<InteroperabilityRunRecord>(
    "/api/dashboard/interoperability/org-unit-mapping-imports",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function createInteroperabilityRiskScoreExportPreviewViaBff(payload: {
  system_key?: string;
  mapping_version_label?: string;
}) {
  return requestDashboardRoute<InteroperabilityRunRecord>(
    "/api/dashboard/interoperability/export-previews/risk-scores",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function retryInteroperabilityRunViaBff(publicId: string) {
  return requestDashboardRoute<InteroperabilityRunRecord>(
    `/api/dashboard/interoperability/runs/${encodeURIComponent(publicId)}/retry`,
    {
      method: "POST",
      body: JSON.stringify({}),
    },
  );
}

export async function fetchOperationalKpiMeExportViaBff(params: FetchOperationalKpiMeExportParams = {}) {
  const searchParams = new URLSearchParams();

  if (params.date_from) {
    searchParams.set("date_from", params.date_from);
  }
  if (params.date_to) {
    searchParams.set("date_to", params.date_to);
  }
  if (params.ward_id) {
    searchParams.set("ward_id", String(params.ward_id));
  }
  if (params.sub_county) {
    searchParams.set("sub_county", params.sub_county);
  }
  if (params.source_channel) {
    searchParams.set("source_channel", params.source_channel);
  }
  if (params.export_format) {
    searchParams.set("export_format", params.export_format);
  }

  const query = searchParams.toString();
  return requestDashboardRoute<OperationalKpiMeExportResponse>(
    `/api/dashboard/operational-metrics/me-export${query ? `?${query}` : ""}`,
  );
}

export function downloadOperationalKpiExportFile(exportPayload: OperationalKpiMeExportResponse) {
  const blob = new Blob([exportPayload.payload], { type: `${exportPayload.content_type};charset=utf-8;` });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = exportPayload.filename;
  link.click();
  URL.revokeObjectURL(url);
}

export async function retrySystemBackgroundJobsViaBff(payload: { limit?: number } = {}) {
  return requestDashboardRoute<SystemRetryControlResponse>("/api/dashboard/system/retry", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function runManualRiskScoringViaBff(payload: {
  month?: number;
  trigger_alerts?: boolean;
  send_sms?: boolean;
  dual_model?: boolean;
} = {}) {
  return requestDashboardRoute<SystemManualRiskScoringResponse>("/api/dashboard/system/risk-scoring", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function setAlertDeliveryPauseViaBff(payload: {
  paused: boolean;
  duration_minutes?: number;
  reason?: string;
}) {
  return requestDashboardRoute<SystemControlStatus>("/api/dashboard/system/alert-delivery-pause", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
