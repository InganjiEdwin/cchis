import { NextResponse } from "next/server";

import type { ChvCoverageRequestRecord } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ publicId: string }> },
) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const { publicId } = await params;

  try {
    const coverageRequest = await fetchBackendJson<ChvCoverageRequestRecord>(
      `/chv/coverage-requests/${encodeURIComponent(publicId)}/`,
      {
        cookieHeader,
      },
    );

    return NextResponse.json(coverageRequest);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to load CHV coverage request detail." }, { status: 500 });
  }
}
