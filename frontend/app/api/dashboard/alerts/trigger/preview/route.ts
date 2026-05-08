import { NextResponse } from "next/server";

import type { TriggerPreviewResponse } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function POST(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  try {
    const body = await request.text();
    const response = await fetchBackendJson<TriggerPreviewResponse>("/alerts/trigger/preview/", {
      method: "POST",
      body,
      cookieHeader,
    });

    return NextResponse.json(response, { status: 200 });
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json(error.payload ?? { detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to load alert message preview." }, { status: 500 });
  }
}
