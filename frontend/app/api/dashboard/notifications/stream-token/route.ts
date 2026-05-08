import { NextResponse } from "next/server";

import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function GET(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  try {
    const payload = await fetchBackendJson<{
      token: string;
      websocket_path: string;
      expires_in_seconds: number;
    }>("/notifications/stream-token/", {
      cookieHeader,
    });

    return NextResponse.json(payload);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json(error.payload ?? { detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to issue notification stream token." }, { status: 500 });
  }
}
