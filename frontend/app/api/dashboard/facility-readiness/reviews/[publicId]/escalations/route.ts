import { NextResponse } from "next/server";

import type { FacilityReadinessEscalationSummary } from "@/lib/dashboard";
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
    const escalation = await fetchBackendJson<FacilityReadinessEscalationSummary>(
      `/facility-readiness/reviews/${encodeURIComponent(publicId)}/escalations/`,
      {
        method: "POST",
        cookieHeader,
        body: JSON.stringify(body),
      },
    );

    return NextResponse.json(escalation, { status: 201 });
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json(error.payload ?? { detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to escalate readiness review." }, { status: 500 });
  }
}
