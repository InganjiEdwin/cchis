import { NextResponse } from "next/server";

import type {
  AlertRecord,
  FacilityRecord,
  LatestWardRisk,
  PaginatedResponse,
  TopbarData,
  TopbarFeedStatus,
  TopbarNotification,
} from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

const STALE_THRESHOLD_MINUTES = 120;

function isStale(timestamp: string | null) {
  if (!timestamp) {
    return true;
  }

  const value = new Date(timestamp).getTime();
  if (Number.isNaN(value)) {
    return true;
  }

  return Date.now() - value > STALE_THRESHOLD_MINUTES * 60 * 1000;
}

function buildAlertNotifications(alerts: AlertRecord[]): TopbarNotification[] {
  return alerts.slice(0, 4).map((alert) => ({
    id: `alert-${alert.id}`,
    level: alert.status === "FAILED" ? "critical" : alert.status === "RETRY_PENDING" ? "warning" : "info",
    title:
      alert.status === "FAILED"
        ? `${alert.ward_name}: alert delivery failed`
        : alert.status === "RETRY_PENDING"
          ? `${alert.ward_name}: alert retry pending`
          : `${alert.ward_name}: alert delivered`,
    context: `${alert.channel} alert for ${alert.recipient} is currently ${alert.status.toLowerCase().replaceAll("_", " ")}.`,
    action: "Open Alert",
    href: `/alerts/${alert.id}`,
    timestamp: alert.created_at,
  }));
}

function buildRiskNotifications(risks: LatestWardRisk[]): TopbarNotification[] {
  return risks
    .filter((risk) => risk.risk_level === "HIGH")
    .sort((left, right) => (right.risk_score ?? 0) - (left.risk_score ?? 0))
    .slice(0, 2)
    .map((risk) => ({
      id: `risk-${risk.ward_id}`,
      level: "warning" as const,
      title: `${risk.ward_name}: high ward risk`,
      context: `Latest ward score is ${Math.round((risk.risk_score ?? 0) * 100)}% with ${risk.predicted_cases} predicted cases.`,
      action: "Open Ward",
      href: `/wards/${risk.ward_id}`,
      timestamp: risk.generated_at ?? new Date().toISOString(),
    }));
}

function buildFeedStatuses(
  latestRiskTimestamp: string | null,
  latestAlertTimestamp: string | null,
  latestFacilityTimestamp: string | null,
): TopbarFeedStatus[] {
  return [
    {
      id: "risks",
      label: "Risk feed",
      latest_timestamp: latestRiskTimestamp,
      stale: isStale(latestRiskTimestamp),
    },
    {
      id: "alerts",
      label: "Alert log",
      latest_timestamp: latestAlertTimestamp,
      stale: isStale(latestAlertTimestamp),
    },
    {
      id: "facilities",
      label: "Facility records",
      latest_timestamp: latestFacilityTimestamp,
      stale: isStale(latestFacilityTimestamp),
    },
  ];
}

export async function GET(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  try {
    const [alerts, latestRisks, facilities] = await Promise.all([
      fetchBackendJson<PaginatedResponse<AlertRecord>>("/alerts/?page_size=20&ordering=-created_at", {
        cookieHeader,
      }),
      fetchBackendJson<LatestWardRisk[]>("/risk-score/latest/", {
        cookieHeader,
      }),
      fetchBackendJson<PaginatedResponse<FacilityRecord>>("/facilities/?page_size=100&ordering=-updated_at", {
        cookieHeader,
      }),
    ]);

    const latestRiskTimestamp = latestRisks.reduce<string | null>((latest, risk) => {
      if (!risk.generated_at) {
        return latest;
      }
      if (!latest || new Date(risk.generated_at).getTime() > new Date(latest).getTime()) {
        return risk.generated_at;
      }
      return latest;
    }, null);

    const latestAlertTimestamp = alerts.results.reduce<string | null>((latest, alert) => {
      if (!latest || new Date(alert.created_at).getTime() > new Date(latest).getTime()) {
        return alert.created_at;
      }
      return latest;
    }, null);

    const latestFacilityTimestamp = facilities.results.reduce<string | null>((latest, facility) => {
      if (!latest || new Date(facility.updated_at).getTime() > new Date(latest).getTime()) {
        return facility.updated_at;
      }
      return latest;
    }, null);

    const notifications: TopbarNotification[] = [
      ...buildAlertNotifications(alerts.results),
      ...buildRiskNotifications(latestRisks),
    ]
      .sort((left, right) => new Date(right.timestamp).getTime() - new Date(left.timestamp).getTime())
      .slice(0, 6);

    const payload: TopbarData = {
      notifications,
      feeds: buildFeedStatuses(latestRiskTimestamp, latestAlertTimestamp, latestFacilityTimestamp),
    };

    return NextResponse.json(payload);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to load topbar data." }, { status: 500 });
  }
}
