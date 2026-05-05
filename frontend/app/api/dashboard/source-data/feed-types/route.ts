import { NextResponse } from "next/server";

import type { SourceDataFeedTypesResponse } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function GET(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  try {
    const feedTypes = await fetchBackendJson<SourceDataFeedTypesResponse>(
      "/source-data/feed-types/",
      { cookieHeader },
    );
    return NextResponse.json(feedTypes);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }
    return NextResponse.json({ detail: "Unable to load source-data feed types." }, { status: 500 });
  }
}
