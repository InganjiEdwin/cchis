import { NextResponse } from "next/server";

import type {
  WardIntelligenceRouteResponse,
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
    const intelligence = await fetchBackendJson<WardIntelligenceRouteResponse>(
      `/wards/${wardId}/intelligence/`,
      {
        cookieHeader,
      },
    );

    return NextResponse.json(intelligence);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json(error.payload ?? { detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to load ward detail." }, { status: 500 });
  }
}
