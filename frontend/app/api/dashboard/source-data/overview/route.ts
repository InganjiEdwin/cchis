import { NextResponse } from "next/server";

import type { SourceDataOverviewResponse } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function GET(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  try {
    const overview = await fetchBackendJson<SourceDataOverviewResponse>(
      "/source-data/overview/",
      { cookieHeader },
    );
    return NextResponse.json(overview);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json(error.payload ?? { detail: error.message }, { status: error.status });
    }
    return NextResponse.json({ detail: "Unable to load source-data overview." }, { status: 500 });
  }
}
