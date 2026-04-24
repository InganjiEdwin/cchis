import { NextResponse } from "next/server";

import type {
  AlertRecord,
  ChvOperationsRecord,
  FacilityRecord,
  LatestWardRisk,
  PaginatedResponse,
  WardSummary,
} from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function GET(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  try {
    const [wards, latestRisks, alerts, queuedAlerts, retryAlerts, failedAlerts, deliveredAlerts, facilities, chvOperations] =
      await Promise.all([
      fetchBackendJson<PaginatedResponse<WardSummary>>("/wards/?page_size=1", {
        cookieHeader,
      }),
      fetchBackendJson<LatestWardRisk[]>("/risk-score/latest/", {
        cookieHeader,
      }),
      fetchBackendJson<PaginatedResponse<AlertRecord>>("/alerts/?page_size=20&ordering=-created_at", {
        cookieHeader,
      }),
      fetchBackendJson<PaginatedResponse<AlertRecord>>("/alerts/?page_size=1&ordering=-created_at&status=QUEUED", {
        cookieHeader,
      }),
      fetchBackendJson<PaginatedResponse<AlertRecord>>("/alerts/?page_size=1&ordering=-created_at&status=RETRY_PENDING", {
        cookieHeader,
      }),
      fetchBackendJson<PaginatedResponse<AlertRecord>>("/alerts/?page_size=1&ordering=-created_at&status=FAILED", {
        cookieHeader,
      }),
      fetchBackendJson<PaginatedResponse<AlertRecord>>("/alerts/?page_size=1&ordering=-created_at&status=DELIVERED", {
        cookieHeader,
      }),
      fetchBackendJson<PaginatedResponse<FacilityRecord>>("/facilities/?page_size=1&ordering=-updated_at", {
        cookieHeader,
      }),
      fetchBackendJson<ChvOperationsRecord[]>("/chvs/operations/", {
        cookieHeader,
      }),
    ]);

    return NextResponse.json({
      wards,
      latestRisks,
      alerts,
      queuedAlerts,
      retryAlerts,
      failedAlerts,
      deliveredAlerts,
      facilities,
      chvOperations,
    });
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to load system freshness data." }, { status: 500 });
  }
}
