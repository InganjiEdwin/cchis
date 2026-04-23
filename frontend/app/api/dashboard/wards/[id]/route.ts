import { NextResponse } from "next/server";

import type {
  AlertRecord,
  PaginatedResponse,
  RiskScoreRecord,
  WardDetailSummary,
} from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const { id } = await params;
  const wardId = Number(id);

  if (!Number.isFinite(wardId)) {
    return NextResponse.json({ detail: "Invalid ward identifier." }, { status: 400 });
  }

  try {
    const [ward, riskHistory, alerts] = await Promise.all([
      fetchBackendJson<WardDetailSummary>(`/wards/${wardId}/`, {
        cookieHeader,
      }),
      fetchBackendJson<PaginatedResponse<RiskScoreRecord>>(
        `/risk-scores/?page_size=20&ordering=-generated_at&ward_id=${wardId}`,
        {
          cookieHeader,
        },
      ),
      fetchBackendJson<PaginatedResponse<AlertRecord>>(
        `/alerts/?page_size=50&ordering=-created_at&ward_id=${wardId}`,
        {
          cookieHeader,
        },
      ),
    ]);

    return NextResponse.json({ ward, riskHistory, alerts });
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to load ward detail." }, { status: 500 });
  }
}
