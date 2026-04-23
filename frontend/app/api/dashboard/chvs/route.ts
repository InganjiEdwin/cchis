import { NextResponse } from "next/server";

import type { ChvRecord, PaginatedResponse } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function GET(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  try {
    const chvs = await fetchBackendJson<PaginatedResponse<ChvRecord>>(
      "/chvs/?page_size=100&ordering=name",
      {
        cookieHeader,
      },
    );

    return NextResponse.json(chvs);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to load CHV directory." }, { status: 500 });
  }
}
