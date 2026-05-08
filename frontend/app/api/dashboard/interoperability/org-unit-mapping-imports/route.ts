import { NextResponse } from "next/server";

import type { InteroperabilityRunRecord } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function POST(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const payload = (await request.json().catch(() => ({}))) as Record<string, unknown>;

  try {
    const run = await fetchBackendJson<InteroperabilityRunRecord>(
      "/interoperability/org-unit-mapping-imports/",
      {
        method: "POST",
        cookieHeader,
        body: JSON.stringify(payload),
      },
    );
    return NextResponse.json(run, { status: 201 });
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json(error.payload, { status: error.status });
    }
    return NextResponse.json({ detail: "Unable to check the location matching file." }, { status: 500 });
  }
}
