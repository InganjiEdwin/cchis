import { NextResponse } from "next/server";

import type { AlertRecord, LatestWardRisk, PaginatedResponse, WardMapResponse, WardSummary } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function GET(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  try {
    const [wards, latestRisks, alerts, wardMap] = await Promise.all([
      fetchBackendJson<PaginatedResponse<WardSummary>>("/wards/?page_size=100&ordering=name&county=Migori", {
        cookieHeader,
      }),
      fetchBackendJson<LatestWardRisk[]>("/risk-score/latest/", {
        cookieHeader,
      }),
      fetchBackendJson<PaginatedResponse<AlertRecord>>("/alerts/?page_size=100&ordering=-created_at", {
        cookieHeader,
      }),
      fetchBackendJson<WardMapResponse>("/maps/wards/", {
        cookieHeader,
      }),
    ]);

    return NextResponse.json({ wards, latestRisks, alerts, wardMap });
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to load overview data." }, { status: 500 });
  }
}
