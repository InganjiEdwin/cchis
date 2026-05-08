import { NextResponse } from "next/server";

import type { SourceDataConnectorRunRecord } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

type RouteContext = {
  params: Promise<{ connectorKey: string }>;
};

export async function POST(request: Request, context: RouteContext) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const { connectorKey } = await context.params;
  const payload = await request.json().catch(() => ({}));

  try {
    const run = await fetchBackendJson<SourceDataConnectorRunRecord>(
      `/source-data/connectors/${encodeURIComponent(connectorKey)}/refresh/`,
      {
        method: "POST",
        cookieHeader,
        body: JSON.stringify(payload),
      },
    );
    return NextResponse.json(run);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json(error.payload, { status: error.status });
    }
    return NextResponse.json({ detail: "Unable to refresh source-data connector." }, { status: 500 });
  }
}
