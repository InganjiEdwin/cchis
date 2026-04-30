import { NextResponse } from "next/server";

import type { PaginatedResponse, ScenarioSimulationRun, WardSummary } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function POST(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  try {
    const body = await request.text();
    const [response, wards] = await Promise.all([
      fetchBackendJson<ScenarioSimulationRun>("/dashboard-scenarios/run/", {
        method: "POST",
        body,
        cookieHeader,
      }),
      fetchBackendJson<PaginatedResponse<WardSummary>>("/wards/?page_size=100&ordering=name&county=Migori", {
        cookieHeader,
      }),
    ]);

    const scopedWardIds = new Set(wards.results.map((ward) => ward.id));
    const scopedWardResults = response.ward_results.filter((result) => scopedWardIds.has(result.ward_id));
    const scopedFacilityResults = response.facility_results.filter((result) => scopedWardIds.has(result.ward_id));
    const scopedSummary = {
      ...response.summary,
      top_impacted_ward_name: scopedWardResults[0]?.ward_name ?? null,
      high_risk_ward_count: scopedWardResults.filter((result) => result.simulated_risk_level === "HIGH").length,
      watch_ward_count: scopedWardResults.filter((result) => result.simulated_risk_level === "MEDIUM").length,
      capacity_concern_facility_count: scopedFacilityResults.filter(
        (result) => result.simulated_capacity_signal === "capacity_concern",
      ).length,
    };

    return NextResponse.json(
      {
        ...response,
        summary: scopedSummary,
        ward_results: scopedWardResults,
        facility_results: scopedFacilityResults,
      },
      { status: 201 },
    );
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to run dashboard simulation." }, { status: 500 });
  }
}
