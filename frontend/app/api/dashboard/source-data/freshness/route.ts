import { NextResponse } from "next/server";

import type { SourceDataFreshnessResponse } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function GET(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  try {
    const freshness = await fetchBackendJson<SourceDataFreshnessResponse>(
      "/source-data/freshness/",
      { cookieHeader },
    );
    return NextResponse.json(freshness);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json(error.payload ?? { detail: error.message }, { status: error.status });
    }
    return NextResponse.json({ detail: "Unable to load source-data freshness." }, { status: 500 });
  }
}
