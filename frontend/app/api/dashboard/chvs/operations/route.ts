import { NextResponse } from "next/server";

import type { ChvOperationsRecord } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function GET(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  try {
    const chvOperations = await fetchBackendJson<ChvOperationsRecord[]>("/chvs/operations/", {
      cookieHeader,
    });

    return NextResponse.json(chvOperations);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to load CHV operations." }, { status: 500 });
  }
}
