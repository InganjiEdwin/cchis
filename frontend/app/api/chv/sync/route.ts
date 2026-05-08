import { NextResponse } from "next/server";

import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function POST(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const payload = (await request.json().catch(() => ({}))) as Record<string, unknown>;

  try {
    const syncResult = await fetchBackendJson<Record<string, unknown>>("/chv/sync/", {
      method: "POST",
      cookieHeader,
      body: JSON.stringify(payload),
    });

    return NextResponse.json(syncResult, { status: 201 });
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json(error.payload ?? { detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to sync CHV offline work." }, { status: 500 });
  }
}

