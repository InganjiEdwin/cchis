import { NextResponse } from "next/server";

import type { LatestWardRisk, PaginatedResponse, WardSummary } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function GET(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const { searchParams } = new URL(request.url);

  const county = searchParams.get("county")?.trim() || "Migori";
  const q = searchParams.get("q")?.trim() || "";
  const risk = searchParams.get("risk")?.trim() || "";
  const subCounty = searchParams.get("sub_county")?.trim() || "";
  const ordering = searchParams.get("ordering")?.trim() || "name";

  const wardParams = new URLSearchParams({
    page_size: "200",
    ordering,
    county,
  });

  if (q) {
    wardParams.set("q", q);
  }
  if (risk) {
    wardParams.set("risk", risk);
  }
  if (subCounty) {
    wardParams.set("sub_county", subCounty);
  }

  const latestRiskParams = new URLSearchParams({ county });
  if (q) {
    latestRiskParams.set("q", q);
  }
  if (risk) {
    latestRiskParams.set("risk", risk);
  }
  if (subCounty) {
    latestRiskParams.set("sub_county", subCounty);
  }

  try {
    const [wards, latestRisks] = await Promise.all([
      fetchBackendJson<PaginatedResponse<WardSummary>>(`/wards/?${wardParams.toString()}`, {
        cookieHeader,
      }),
      fetchBackendJson<LatestWardRisk[]>(`/risk-score/latest/?${latestRiskParams.toString()}`, {
        cookieHeader,
      }),
    ]);

    return NextResponse.json({ wards, latestRisks });
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to load ward risk data." }, { status: 500 });
  }
}
