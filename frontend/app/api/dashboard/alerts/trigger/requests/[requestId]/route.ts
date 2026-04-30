import { NextResponse } from "next/server";

import type { TriggerAlertRequestStatusResponse } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

type RouteContext = {
  params: Promise<{
    requestId: string;
  }>;
};

export async function GET(request: Request, context: RouteContext) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const { requestId } = await context.params;

  try {
    const response = await fetchBackendJson<TriggerAlertRequestStatusResponse>(
      `/alerts/trigger/requests/${encodeURIComponent(requestId)}/`,
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

    return NextResponse.json({ detail: "Unable to load alert request tracking." }, { status: 500 });
  }
}
