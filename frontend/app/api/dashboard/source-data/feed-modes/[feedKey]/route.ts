import { NextResponse } from "next/server";

import type { SourceDataFeedDefinition, SourceDataFeedModePayload } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

type RouteContext = {
  params: Promise<{ feedKey: string }>;
};

export async function POST(request: Request, context: RouteContext) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const { feedKey } = await context.params;
  const payload = (await request.json().catch(() => ({}))) as SourceDataFeedModePayload;

  try {
    const state = await fetchBackendJson<
      Pick<SourceDataFeedDefinition, "feed_mode" | "csv_upload_enabled" | "connector_status">
    >(`/source-data/feed-modes/${encodeURIComponent(feedKey)}/`, {
      method: "POST",
      cookieHeader,
      body: JSON.stringify(payload),
    });
    return NextResponse.json(state);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json(error.payload, { status: error.status });
    }
    return NextResponse.json({ detail: "Unable to update source-data feed mode." }, { status: 500 });
  }
}
