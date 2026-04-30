import { NextResponse } from "next/server";

import type { FacilityReadinessReviewSummary } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

type RouteContext = {
  params: Promise<{
    publicId: string;
  }>;
};

export async function POST(request: Request, context: RouteContext) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const { publicId } = await context.params;

  try {
    const body = await request.json();
    const review = await fetchBackendJson<FacilityReadinessReviewSummary>(
      `/facility-readiness/reviews/${encodeURIComponent(publicId)}/acknowledge/`,
      {
        method: "POST",
        cookieHeader,
        body: JSON.stringify(body),
      },
    );

    return NextResponse.json(review);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to mark readiness review as reviewed." }, { status: 500 });
  }
}
