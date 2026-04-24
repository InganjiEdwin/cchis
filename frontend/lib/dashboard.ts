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
    centroid: [number, number] | null;
    backend_ward_id: number | null;
    backend_public_id: string | null;
    has_backend_ward: boolean;
    risk_level: "LOW" | "MEDIUM" | "HIGH" | null;
    risk_score: number | null;
    predicted_cases: number;
    risk_generated_at: string | null;
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
    geometry_feature_count: number;
    expected_ward_count: number;
    missing_source_wards: string[];
    backend_ward_match_count: number;
    returned_feature_count: number;
    backend_wards_without_geometry: string[];
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
};

type WardsRouteResponse = {
  wards: PaginatedResponse<WardSummary>;
  latestRisks: LatestWardRisk[];
};

type WardDetailRouteResponse = {
  ward: WardDetailSummary;
  riskHistory: PaginatedResponse<RiskScoreRecord>;
  alerts: PaginatedResponse<AlertRecord>;
};

type AlertDetailRouteResponse = {
  alert: AlertRecord | null;
  wardDetail: WardDetailSummary | null;
};

type FacilityDetailRouteResponse = {
  facility: FacilityRecord | null;
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
  return requestDashboardRoute<WardDetailRouteResponse>(`/api/dashboard/wards/${wardId}`);
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

export async function fetchFacilityDataViaBff() {
  return requestDashboardRoute<PaginatedResponse<FacilityRecord>>("/api/dashboard/facilities");
}

export async function fetchFacilityByIdViaBff(facilityId: number) {
  return requestDashboardRoute<FacilityDetailRouteResponse>(`/api/dashboard/facilities/${facilityId}`);
}

export async function fetchWardMapViaBff() {
  return requestDashboardRoute<WardMapResponse>("/api/dashboard/maps/wards");
}

export async function fetchTopbarDataViaBff() {
  return requestDashboardRoute<TopbarData>("/api/dashboard/topbar");
}

export async function fetchSystemDataViaBff() {
  return requestDashboardRoute<OverviewRouteResponse>("/api/dashboard/system");
}
