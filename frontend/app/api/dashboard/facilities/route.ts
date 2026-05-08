import { NextResponse } from "next/server";

import type { FacilityListRouteResponse } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

function toBackendPath(nextUrl: string): string {
  const parsed = new URL(nextUrl);
  return `${parsed.pathname}${parsed.search}`;
}

export async function GET(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  try {
    const firstPage = await fetchBackendJson<FacilityListRouteResponse>(
      "/facilities/?page_size=100&ordering=ward__name,name",
      {
        cookieHeader,
      },
    );

    const results = [...firstPage.results];
    const workflowStates = [...(firstPage.workflow_states ?? [])];
    let next = firstPage.next;

    while (next) {
      const page = await fetchBackendJson<FacilityListRouteResponse>(toBackendPath(next), {
        cookieHeader,
      });
      results.push(...page.results);
      workflowStates.push(...(page.workflow_states ?? []));
      next = page.next;
    }

    return NextResponse.json({
      ...firstPage,
      next: null,
      previous: null,
      results,
      workflow_states: workflowStates,
    });
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json(error.payload ?? { detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to load facilities." }, { status: 500 });
  }
}
