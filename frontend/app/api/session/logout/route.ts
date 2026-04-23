import { NextResponse } from "next/server";

import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function POST(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  try {
    await fetchBackendJson<void>("/auth/logout/", {
      method: "POST",
      body: JSON.stringify({}),
      cookieHeader,
    });

    return new NextResponse(null, { status: 204 });
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to end the current session." }, { status: 500 });
  }
}
