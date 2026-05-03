import { NextResponse } from "next/server";

import type { SystemControlStatus } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function POST(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  try {
    const body = await request.text();
    const response = await fetchBackendJson<SystemControlStatus>("/system/controls/alert-delivery-pause/", {
      method: "POST",
      body,
      cookieHeader,
    });

    return NextResponse.json(response);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to update alert delivery pause." }, { status: 500 });
  }
}
