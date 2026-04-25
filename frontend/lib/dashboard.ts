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

export type AlertRecord = {
  id: number;
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

export type TopbarNotification = {
  id: string;
  level: "critical" | "warning" | "info";
  title: string;
  context: string;
  action: string;
  href: string;
  timestamp: string;
};

export type TopbarFeedStatus = {
  id: "risks" | "alerts" | "facilities";
  label: string;
  latest_timestamp: string | null;
  stale: boolean;
};

export type TopbarData = {
  notifications: TopbarNotification[];
  feeds: TopbarFeedStatus[];
};

export type WardMapGeometry = {
  type: "Polygon" | "MultiPolygon";
  coordinates: number[][][] | number[][][][];
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
    risk_level: "LOW" | "MEDIUM" | "HIGH" | null;
    risk_score: number | null;
    predicted_cases: number;
    risk_generated_at: string | null;
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
  generated_at: string;
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
  mode: string;
};

export type AlertIntelligenceStateItem = {
  label: string;
  tone: "success" | "warning" | "neutral";
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
  category: "all" | "delivery" | "responses" | "system";
  meta: string | null;
  details?: string[];
};

export type AlertIntelligenceCapabilities = {
  can_resend: boolean;
  can_recall: boolean;
  can_notify_facilities: boolean;
  can_send_follow_up: boolean;
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
};

export type FacilityIntelligenceContext = {
  summary: string;
  ward_risk_score: number | null;
  ward_alert_count: number;
  map_mode: string;
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

export type FacilityIntelligenceCapabilities = {
  can_dispatch: boolean;
  can_open_chat: boolean;
  can_notify_chvs: boolean;
  can_escalate_county: boolean;
  can_view_dispatch_history: boolean;
  can_view_contacts: boolean;
  mode: string;
};

export type TriggerAlertRequest = {
  ward_id: number;
  send_sms: boolean;
};

export type TriggerAlertResponse = {
  message: string;
  risk_score_id: number;
  task_id: string;
};

export type FetchWardRiskDataParams = {
  county?: string;
  q?: string;
  risk?: string;
  sub_county?: string;
  ordering?: string;
};

type OverviewRouteResponse = {
  wards: PaginatedResponse<WardSummary>;
  latestRisks: LatestWardRisk[];
  alerts: PaginatedResponse<AlertRecord>;
  wardMap: WardMapResponse;
};

type WardsRouteResponse = {
  wards: PaginatedResponse<WardSummary>;
  latestRisks: LatestWardRisk[];
};

export type WardIntelligenceRouteResponse = {
  ward: WardDetailSummary;
  current_risk: {
    risk_level: "LOW" | "MEDIUM" | "HIGH" | null;
    risk_score: number | null;
    predicted_cases: number;
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
};

type AlertDetailRouteResponse = {
  alert: AlertRecord | null;
  ward_detail: WardDetailSummary | null;
  classification: AlertIntelligenceClassification;
  risk_context: AlertIntelligenceRiskContext;
  delivery: AlertIntelligenceDelivery;
  current_state: AlertIntelligenceStateItem[];
  freshness: AlertIntelligenceFreshness;
  timeline: AlertIntelligenceTimelineEntry[];
  capabilities: AlertIntelligenceCapabilities;
};

export type FacilityIntelligenceRouteResponse = {
  facility: FacilityRecord | null;
  readiness: FacilityIntelligenceReadiness;
  context: FacilityIntelligenceContext;
  freshness: FacilityIntelligenceFreshness;
  timeline: FacilityIntelligenceTimelineEntry[];
  capabilities: FacilityIntelligenceCapabilities;
};

type SystemRouteResponse = {
  wards: PaginatedResponse<WardSummary>;
  latestRisks: LatestWardRisk[];
  alerts: PaginatedResponse<AlertRecord>;
  queuedAlerts: PaginatedResponse<AlertRecord>;
  retryAlerts: PaginatedResponse<AlertRecord>;
  failedAlerts: PaginatedResponse<AlertRecord>;
  deliveredAlerts: PaginatedResponse<AlertRecord>;
  facilities: PaginatedResponse<FacilityRecord>;
  chvOperations: ChvOperationsRecord[];
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

export async function fetchChvDataViaBff() {
  return requestDashboardRoute<PaginatedResponse<ChvRecord>>("/api/dashboard/chvs");
}

export async function fetchChvOperationsDataViaBff() {
  return requestDashboardRoute<ChvOperationsRecord[]>("/api/dashboard/chvs/operations");
}

export async function fetchFacilityDataViaBff() {
  return requestDashboardRoute<PaginatedResponse<FacilityRecord>>("/api/dashboard/facilities");
}

export async function fetchFacilityByIdViaBff(facilityId: number) {
  return requestDashboardRoute<FacilityIntelligenceRouteResponse>(`/api/dashboard/facilities/${facilityId}`);
}

export async function fetchWardMapViaBff() {
  return requestDashboardRoute<WardMapResponse>("/api/dashboard/maps/wards");
}

export async function fetchTopbarDataViaBff() {
  return requestDashboardRoute<TopbarData>("/api/dashboard/topbar");
}

export async function fetchSystemDataViaBff() {
  return requestDashboardRoute<SystemRouteResponse>("/api/dashboard/system");
}
