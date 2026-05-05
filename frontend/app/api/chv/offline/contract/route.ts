import { NextResponse } from "next/server";

import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function GET(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const search = new URL(request.url).search;

  try {
    const contract = await fetchBackendJson<Record<string, unknown>>(`/chv/offline/contract/${search}`, {
      cookieHeader,
    });

    return NextResponse.json(contract);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to load CHV offline bundle." }, { status: 500 });
  }
}
