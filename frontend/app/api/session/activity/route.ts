import { NextResponse } from "next/server";

import type { ProfileActivityResponse } from "@/lib/auth";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function GET(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const requestUrl = new URL(request.url);
  const query = new URLSearchParams();
  const allowedParams = [
    "page",
    "page_size",
    "event_type",
    "status",
    "date_from",
    "date_to",
    "security_only",
    "include_refresh_events",
  ];

  allowedParams.forEach((param) => {
    const value = requestUrl.searchParams.get(param);

    if (value !== null) {
      query.set(param, value);
    }
  });

  try {
    const response = await fetchBackendJson<ProfileActivityResponse>(`/auth/me/activity/?${query.toString()}`, {
      method: "GET",
      cookieHeader,
    });

    return NextResponse.json(response);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to load account activity." }, { status: 500 });
  }
}
