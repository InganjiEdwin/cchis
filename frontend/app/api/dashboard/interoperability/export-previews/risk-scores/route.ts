import { NextResponse } from "next/server";

import type { InteroperabilityRunRecord } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function POST(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const payload = (await request.json().catch(() => ({}))) as Record<string, unknown>;

  try {
    const run = await fetchBackendJson<InteroperabilityRunRecord>(
      "/interoperability/export-previews/risk-scores/",
      {
        method: "POST",
        cookieHeader,
        body: JSON.stringify(payload),
      },
    );
    return NextResponse.json(run, { status: 201 });
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }
    return NextResponse.json({ detail: "Unable to create interoperability export preview." }, { status: 500 });
  }
}
