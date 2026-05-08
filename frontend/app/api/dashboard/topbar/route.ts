import { NextResponse } from "next/server";

import type {
  DashboardNotification,
  FacilityRecord,
  ModelRunRecord,
  IngestionRunRecord,
  LatestWardRisk,
  PaginatedResponse,
  TopbarData,
  TopbarFeedStatus,
} from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";
import {
  buildFreshnessSummary,
  getLatestDataSyncTimestamp,
  getLatestModelRunTimestamp,
  getLatestPredictionTimestamp,
} from "@/app/api/dashboard/_freshness";

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

type NotificationListResponse = {
  count: number;
  unread_count: number;
  highest_unread_severity: "INFO" | "WARNING" | "CRITICAL" | null;
  system_status: "STABLE" | "DATA_FRESHNESS_DEGRADED" | "ACTION_REQUIRED";
  results: DashboardNotification[];
};

export async function GET(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  try {
    const [notifications, latestRisks, facilities, modelRuns, ingestionRuns] = await Promise.all([
      fetchBackendJson<NotificationListResponse>("/notifications/?page_size=100", {
        cookieHeader,
      }),
      fetchBackendJson<LatestWardRisk[]>("/risk-score/latest/", {
        cookieHeader,
      }),
      fetchBackendJson<PaginatedResponse<FacilityRecord>>("/facilities/?page_size=100&ordering=-updated_at", {
        cookieHeader,
      }),
      fetchBackendJson<PaginatedResponse<ModelRunRecord>>("/model-runs/?page_size=1&ordering=-completed_at", {
        cookieHeader,
      }),
      fetchBackendJson<PaginatedResponse<IngestionRunRecord>>("/ingestion-runs/?page_size=1&ordering=-started_at", {
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

    const latestAlertTimestamp = notifications.results
      .filter((item) => item.source_object_type === "alert")
      .reduce<string | null>((latest, item) => {
        if (!latest || new Date(item.created_at).getTime() > new Date(latest).getTime()) {
          return item.created_at;
        }
        return latest;
      }, null);

    const latestFacilityTimestamp = facilities.results.reduce<string | null>((latest, facility) => {
      if (!latest || new Date(facility.updated_at).getTime() > new Date(latest).getTime()) {
        return facility.updated_at;
      }
      return latest;
    }, null);
    const latestModelRunTimestamp = getLatestModelRunTimestamp(modelRuns.results);
    const latestDataSyncTimestamp = getLatestDataSyncTimestamp(ingestionRuns.results);
    const predictionGeneratedAt = getLatestPredictionTimestamp(latestRisks);

    const payload: TopbarData = {
      notifications: notifications.results,
      unread_count: notifications.unread_count,
      highest_unread_severity: notifications.highest_unread_severity,
      system_status: notifications.system_status,
      feeds: buildFeedStatuses(latestRiskTimestamp, latestAlertTimestamp, latestFacilityTimestamp),
      freshness: buildFreshnessSummary(
        latestModelRunTimestamp,
        latestDataSyncTimestamp,
        latestAlertTimestamp,
        predictionGeneratedAt,
      ),
    };

    return NextResponse.json(payload);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json(error.payload ?? { detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to load topbar data." }, { status: 500 });
  }
}
