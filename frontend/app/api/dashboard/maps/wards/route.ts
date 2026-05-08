import { NextResponse } from "next/server";

import type { WardMapResponse } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function GET(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  try {
    const wardMap = await fetchBackendJson<WardMapResponse>("/maps/wards/", {
      cookieHeader,
    });

    return NextResponse.json(wardMap);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json(error.payload ?? { detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to load ward map." }, { status: 500 });
  }
}
