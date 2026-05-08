import { NextResponse } from "next/server";

import type { SystemControlStatus, SystemReadinessSnapshot } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function GET(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  try {
    const [readiness, controlStatus] = await Promise.all([
      fetchBackendJson<SystemReadinessSnapshot>("/system/readiness/", {
        cookieHeader,
      }),
      fetchBackendJson<SystemControlStatus>("/system/controls/", {
        cookieHeader,
      }),
    ]);

    return NextResponse.json({
      readiness,
      controlStatus,
    });
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json(error.payload ?? { detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to load system freshness data." }, { status: 500 });
  }
}
