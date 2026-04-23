import { NextResponse } from "next/server";

import type { AlertRecord, PaginatedResponse } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function GET(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  try {
    const alerts = await fetchBackendJson<PaginatedResponse<AlertRecord>>(
      "/alerts/?page_size=100&ordering=-created_at",
      {
        cookieHeader,
      },
    );

    return NextResponse.json(alerts);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to load alerts." }, { status: 500 });
  }
}
