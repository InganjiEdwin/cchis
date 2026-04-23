import { NextResponse } from "next/server";

import type { AlertRecord, LatestWardRisk, PaginatedResponse, WardSummary } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function GET(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  try {
    const [wards, latestRisks, alerts] = await Promise.all([
      fetchBackendJson<PaginatedResponse<WardSummary>>("/wards/?page_size=1", {
        cookieHeader,
      }),
      fetchBackendJson<LatestWardRisk[]>("/risk-score/latest/", {
        cookieHeader,
      }),
      fetchBackendJson<PaginatedResponse<AlertRecord>>("/alerts/?page_size=20&ordering=-created_at", {
        cookieHeader,
      }),
    ]);

    return NextResponse.json({ wards, latestRisks, alerts });
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to load system freshness data." }, { status: 500 });
  }
}
