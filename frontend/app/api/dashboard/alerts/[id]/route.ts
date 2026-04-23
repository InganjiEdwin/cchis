import { NextResponse } from "next/server";

import type { AlertRecord, PaginatedResponse, WardDetailSummary } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const { id } = await params;
  const alertId = Number(id);

  if (!Number.isFinite(alertId)) {
    return NextResponse.json({ detail: "Invalid alert identifier." }, { status: 400 });
  }

  try {
    const alerts = await fetchBackendJson<PaginatedResponse<AlertRecord>>(
      "/alerts/?page_size=200&ordering=-created_at",
      {
        cookieHeader,
      },
    );

    const alert = alerts.results.find((item) => item.id === alertId) ?? null;

    if (!alert) {
      return NextResponse.json({ alert: null, wardDetail: null });
    }

    let wardDetail: WardDetailSummary | null = null;

    try {
      wardDetail = await fetchBackendJson<WardDetailSummary>(`/wards/${alert.ward}/`, {
        cookieHeader,
      });
    } catch (error) {
      if (error instanceof ServerApiError && (error.status === 403 || error.status === 404)) {
        wardDetail = null;
      } else {
        throw error;
      }
    }

    return NextResponse.json({ alert, wardDetail });
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to load alert detail." }, { status: 500 });
  }
}
