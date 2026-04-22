import {
  getApiBaseUrl,
  persistAccessToken,
  persistEnrollmentToken,
  persistPreAuthToken,
  persistRefreshToken,
  readAccessToken,
  readRefreshToken,
  refreshAccessToken,
} from "@/lib/auth";

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

async function request<T>(path: string, accessToken: string, init: RequestInit = {}): Promise<T> {
  const execute = async (token: string) =>
    fetch(`${getApiBaseUrl()}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
        ...(init.headers ?? {}),
      },
    });

  const initialToken = readAccessToken() ?? accessToken;
  let response = await execute(initialToken);

  if (response.status === 401) {
    const refresh = readRefreshToken();

    if (refresh) {
      try {
        const refreshed = await refreshAccessToken(refresh);
        persistAccessToken(refreshed.access);

        if (refreshed.refresh) {
          persistRefreshToken(refreshed.refresh);
        }

        response = await execute(refreshed.access);
      } catch {
        persistAccessToken(null);
        persistRefreshToken(null);
        persistPreAuthToken(null);
        persistEnrollmentToken(null);
      }
    }
  }

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

function buildListPath(path: string, params: Record<string, string | number | undefined>) {
  const searchParams = new URLSearchParams();

  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== "") {
      searchParams.set(key, String(value));
    }
  });

  const query = searchParams.toString();
  return query ? `${path}?${query}` : path;
}

export async function fetchOverviewData(accessToken: string) {
  const [wards, latestRisks, alerts] = await Promise.all([
    request<PaginatedResponse<WardSummary>>("/wards/?page_size=100&ordering=name&county=Migori", accessToken),
    request<LatestWardRisk[]>("/risk-score/latest/", accessToken),
    request<PaginatedResponse<AlertRecord>>("/alerts/?page_size=100&ordering=-created_at", accessToken),
  ]);

  return { wards, latestRisks, alerts };
}

export async function fetchWardRiskData(accessToken: string) {
  const [wards, latestRisks] = await Promise.all([
    request<PaginatedResponse<WardSummary>>("/wards/?page_size=200&ordering=name", accessToken),
    request<LatestWardRisk[]>("/risk-score/latest/", accessToken),
  ]);

  return { wards, latestRisks };
}

export async function fetchAlertsData(accessToken: string) {
  return request<PaginatedResponse<AlertRecord>>("/alerts/?page_size=100&ordering=-created_at", accessToken);
}

export async function fetchAlertsForWard(accessToken: string, wardId: number) {
  return request<PaginatedResponse<AlertRecord>>(
    buildListPath("/alerts/", { page_size: 50, ordering: "-created_at", ward_id: wardId }),
    accessToken,
  );
}

export async function fetchAlertById(accessToken: string, alertId: number) {
  const response = await request<PaginatedResponse<AlertRecord>>(
    buildListPath("/alerts/", { page_size: 200, ordering: "-created_at" }),
    accessToken,
  );

  return response.results.find((alert) => alert.id === alertId) ?? null;
}

export async function fetchChvData(accessToken: string) {
  return request<PaginatedResponse<ChvRecord>>("/chvs/?page_size=100&ordering=name", accessToken);
}

export async function fetchSystemData(accessToken: string) {
  const [wards, latestRisks, alerts] = await Promise.all([
    request<PaginatedResponse<WardSummary>>("/wards/?page_size=1", accessToken),
    request<LatestWardRisk[]>("/risk-score/latest/", accessToken),
    request<PaginatedResponse<AlertRecord>>("/alerts/?page_size=20&ordering=-created_at", accessToken),
  ]);

  return { wards, latestRisks, alerts };
}

export async function fetchRiskHistoryForWard(accessToken: string, wardId: number) {
  return request<PaginatedResponse<RiskScoreRecord>>(
    buildListPath("/risk-scores/", { page_size: 20, ordering: "-generated_at", ward_id: wardId }),
    accessToken,
  );
}

export async function triggerAlert(accessToken: string, payload: TriggerAlertRequest) {
  return request<TriggerAlertResponse>("/alerts/trigger/", accessToken, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
