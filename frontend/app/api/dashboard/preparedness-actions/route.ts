import { NextResponse } from "next/server";

import type { PaginatedResponse, PreparednessActionRecord } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

const FORWARDED_PARAMS = [
  "page",
  "page_size",
  "ward_id",
  "facility_id",
  "chv_id",
  "status",
  "action_type",
  "priority",
  "source_trigger_type",
  "assigned",
  "overdue",
  "ordering",
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

  if (!backendParams.has("page_size")) {
    backendParams.set("page_size", "200");
  }
  if (!backendParams.has("ordering")) {
    backendParams.set("ordering", "due_at");
  }

  try {
    const actions = await fetchBackendJson<PaginatedResponse<PreparednessActionRecord>>(
      `/preparedness-actions/?${backendParams.toString()}`,
      {
        cookieHeader,
      },
    );

    return NextResponse.json(actions);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to load preparedness actions." }, { status: 500 });
  }
}
