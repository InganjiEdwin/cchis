import { NextResponse } from "next/server";

import type { OperationalKpiMeExportResponse } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

const FORWARDED_PARAMS = ["date_from", "date_to", "ward_id", "sub_county", "source_channel", "export_format"];

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
    const exportPayload = await fetchBackendJson<OperationalKpiMeExportResponse>(
      `/operational-metrics/me-export/${backendParams.size ? `?${backendParams.toString()}` : ""}`,
      {
        cookieHeader,
      },
    );

    return NextResponse.json(exportPayload);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to export operational KPI M&E report." }, { status: 500 });
  }
}
