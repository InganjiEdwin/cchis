import { NextResponse } from "next/server";

import type { SystemManualRiskScoringResponse } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function POST(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  try {
    const body = await request.text();
    const response = await fetchBackendJson<SystemManualRiskScoringResponse>("/system/controls/manual-risk-scoring/", {
      method: "POST",
      body,
      cookieHeader,
    });

    return NextResponse.json(response, { status: 202 });
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to queue manual risk scoring." }, { status: 500 });
  }
}
