import { NextResponse } from "next/server";

import type { SourceDataOperationsResponse } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function GET(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  try {
    const operations = await fetchBackendJson<SourceDataOperationsResponse>(
      "/source-data/operations/",
      { cookieHeader },
    );
    return NextResponse.json(operations);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }
    return NextResponse.json({ detail: "Unable to load source-data operations health." }, { status: 500 });
  }
}
