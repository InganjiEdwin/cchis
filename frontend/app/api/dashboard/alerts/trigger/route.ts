import { NextResponse } from "next/server";

import type { TriggerAlertResponse } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function POST(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  try {
    const body = await request.text();
    const response = await fetchBackendJson<TriggerAlertResponse>("/alerts/trigger/", {
      method: "POST",
      body,
      cookieHeader,
    });

    return NextResponse.json(response, { status: 202 });
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json(error.payload, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to queue the alert trigger request." }, { status: 500 });
  }
}
