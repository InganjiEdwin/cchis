import { NextResponse } from "next/server";

import type { FacilityReadinessReviewSummary } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

function parseFacilityId(value: string) {
  const facilityId = Number(value);
  return Number.isInteger(facilityId) && facilityId > 0 ? facilityId : null;
}

export async function POST(request: Request, context: { params: Promise<{ id: string }> }) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const { id } = await context.params;
  const facilityId = parseFacilityId(id);

  if (!facilityId) {
    return NextResponse.json({ detail: "Facility id must be a positive integer." }, { status: 400 });
  }

  try {
    const body = await request.json();
    const review = await fetchBackendJson<FacilityReadinessReviewSummary>(
      `/facilities/${facilityId}/readiness-reviews/`,
      {
        method: "POST",
        cookieHeader,
        body: JSON.stringify(body),
      },
    );

    return NextResponse.json(review, { status: 201 });
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json(error.payload ?? { detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to open readiness review." }, { status: 500 });
  }
}
