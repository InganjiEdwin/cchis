import { NextResponse } from "next/server";

import type { SensitiveExportCreatePayload, SensitiveExportRecord } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function POST(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const payload = (await request.json()) as SensitiveExportCreatePayload;

  try {
    const exportRequest = await fetchBackendJson<SensitiveExportRecord>("/sensitive-exports/", {
      method: "POST",
      body: JSON.stringify(payload),
      cookieHeader,
    });

    return NextResponse.json(exportRequest);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json(error.payload, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to request sensitive export." }, { status: 500 });
  }
}
