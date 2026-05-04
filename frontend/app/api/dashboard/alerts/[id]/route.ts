import { NextResponse } from "next/server";

import type { AlertRecord } from "@/lib/dashboard";
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
    const alertIntelligence = await fetchBackendJson<{
      alert: AlertRecord | null;
      ward_detail: unknown;
      classification: unknown;
      risk_context: unknown;
      delivery: unknown;
      climate_evidence?: unknown;
      current_state: unknown;
      freshness: unknown;
      timeline: unknown;
      capabilities: unknown;
    }>(`/alerts/${alertId}/intelligence/`, {
      cookieHeader,
    });
    return NextResponse.json(alertIntelligence);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to load alert detail." }, { status: 500 });
  }
}
