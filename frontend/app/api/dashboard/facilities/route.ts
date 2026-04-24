import { NextResponse } from "next/server";

import type { FacilityRecord, PaginatedResponse } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function GET(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  try {
    const facilities = await fetchBackendJson<PaginatedResponse<FacilityRecord>>(
      "/facilities/?page_size=100&ordering=ward__name,name",
      {
        cookieHeader,
      },
    );

    return NextResponse.json(facilities);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to load facilities." }, { status: 500 });
  }
}
