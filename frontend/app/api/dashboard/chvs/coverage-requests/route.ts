import { NextResponse } from "next/server";

import type { ChvCoverageRequestRecord, CreateChvCoverageRequestPayload, PaginatedResponse } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

function buildCoverageRequestQuery(request: Request) {
  const url = new URL(request.url);
  const searchParams = new URLSearchParams();

  for (const key of ["page", "ward_id", "status", "priority", "trigger_source", "overdue", "has_linked_alerts"]) {
    const value = url.searchParams.get(key);
    if (value) {
      searchParams.set(key, value);
    }
  }

  const query = searchParams.toString();
  return query ? `?${query}` : "";
}

export async function GET(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  try {
    const coverageRequests = await fetchBackendJson<PaginatedResponse<ChvCoverageRequestRecord>>(
      `/chv/coverage-requests/${buildCoverageRequestQuery(request)}`,
      {
        cookieHeader,
      },
    );

    return NextResponse.json(coverageRequests);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json(error.payload ?? { detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to load CHV coverage requests." }, { status: 500 });
  }
}

export async function POST(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  let payload: CreateChvCoverageRequestPayload;
  try {
    payload = (await request.json()) as CreateChvCoverageRequestPayload;
  } catch {
    return NextResponse.json({ detail: "Invalid CHV coverage request payload." }, { status: 400 });
  }

  try {
    const coverageRequest = await fetchBackendJson<ChvCoverageRequestRecord>("/chv/coverage-requests/", {
      method: "POST",
      cookieHeader,
      body: JSON.stringify(payload),
    });

    return NextResponse.json(coverageRequest, { status: 201 });
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json(error.payload ?? { detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to create CHV coverage request." }, { status: 500 });
  }
}
