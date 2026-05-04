import { NextResponse } from "next/server";

import type { ModelOperationsHealthResponse } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function GET(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  try {
    const dashboard = await fetchBackendJson<ModelOperationsHealthResponse>(
      "/model-operations/health/",
      { cookieHeader },
    );
    return NextResponse.json(dashboard);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }
    return NextResponse.json({ detail: "Unable to load model health dashboard." }, { status: 500 });
  }
}
