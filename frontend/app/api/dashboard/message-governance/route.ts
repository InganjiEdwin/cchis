import { NextResponse } from "next/server";

import type { MessageGovernanceDashboardResponse } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

const FORWARDED_PARAMS = [
  "q",
  "audience_type",
  "channel",
  "language",
  "approval_status",
  "date_from",
  "date_to",
];

export async function GET(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const { searchParams } = new URL(request.url);
  const backendParams = new URLSearchParams();

  for (const key of FORWARDED_PARAMS) {
    const value = searchParams.get(key);
    if (value !== null && value !== "") {
      backendParams.set(key, value);
    }
  }

  try {
    const dashboard = await fetchBackendJson<MessageGovernanceDashboardResponse>(
      `/message-governance/dashboard/${backendParams.size ? `?${backendParams.toString()}` : ""}`,
      {
        cookieHeader,
      },
    );

    return NextResponse.json(dashboard);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json(error.payload ?? { detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to load message governance dashboard." }, { status: 500 });
  }
}
