import { NextResponse } from "next/server";

import type { SystemRetryControlResponse } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function POST(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  try {
    const body = await request.text();
    const response = await fetchBackendJson<SystemRetryControlResponse>("/system/controls/retry/", {
      method: "POST",
      body,
      cookieHeader,
    });

    return NextResponse.json(response, { status: 202 });
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json(error.payload, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to queue background retry controls." }, { status: 500 });
  }
}
