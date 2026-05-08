import { NextResponse } from "next/server";

import type { ProfileSessionResponse } from "@/lib/auth";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function GET(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const requestUrl = new URL(request.url);
  const query = new URLSearchParams();
  const userId = requestUrl.searchParams.get("user_id");

  if (userId) {
    query.set("user_id", userId);
  }

  const queryString = query.toString();
  const backendPath = `/auth/sessions/${queryString ? `?${queryString}` : ""}`;

  try {
    const response = await fetchBackendJson<ProfileSessionResponse>(backendPath, {
      method: "GET",
      cookieHeader,
    });

    return NextResponse.json(response);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json(error.payload, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to load active sessions." }, { status: 500 });
  }
}
