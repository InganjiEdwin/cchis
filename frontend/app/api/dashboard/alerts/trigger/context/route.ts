import { NextResponse } from "next/server";

import type { TriggerContextResponse } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function GET(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const { searchParams } = new URL(request.url);
  const wardId = searchParams.get("ward_id");

  try {
    const backendSearch = new URLSearchParams();
    if (wardId) {
      backendSearch.set("ward_id", wardId);
    }

    const response = await fetchBackendJson<TriggerContextResponse>(
      `/alerts/trigger/context/${backendSearch.toString() ? `?${backendSearch.toString()}` : ""}`,
      {
        method: "GET",
        cookieHeader,
      },
    );

    return NextResponse.json(response, { status: 200 });
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to load alert trigger context." }, { status: 500 });
  }
}
