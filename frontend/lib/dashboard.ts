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
  type: "WARD_RISK_HIGH" | "ALERT_FAILED" | "ALERT_RETRY_PENDING" | "FEED_STALE" | "CHV_COVERAGE_REQUEST_STATUS";
  category: "system_health" | "alert_delivery" | "trigger_review" | "chv_coverage_workflow" | "general";
  group_key: "data_freshness" | "alert_delivery_failures" | "alert_delivery_retries" | "chv_coverage_requests" | null;
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
  };
  model_readiness: {
    state: "seeded_demo" | "proxy_backed" | "evaluated" | "promoted";
    label: string;
    tone: WardOperationalEvidenceTone;
    detail: string;
    evidence: string[];
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
  message_mode?: "backend_generated" | "operator_edited" | null;
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
  message_mode: "backend_generated" | "operator_edited";
  supports_editing: boolean;
  channel_defaults: string[];
  recipient_preview: {
    chv_count: number;
  };
  recommended_action: string;
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

async function requestDashboardRoute<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });

  if (!response.ok) {
    let detail = "Unable to load dashboard data.";

    try {
      const data = (await response.json()) as { detail?: string };
      detail = data.detail ?? detail;
    } catch {
      // Keep the generic message.
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
