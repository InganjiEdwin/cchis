import { NextResponse } from "next/server";

import type { AssignChvCoverageRequestPayload, ChvCoverageRequestRecord } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ publicId: string }> },
) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const { publicId } = await params;

  let payload: AssignChvCoverageRequestPayload;
  try {
    payload = (await request.json()) as AssignChvCoverageRequestPayload;
  } catch {
    return NextResponse.json({ detail: "Invalid CHV assignment payload." }, { status: 400 });
  }

  try {
    const coverageRequest = await fetchBackendJson<ChvCoverageRequestRecord>(
      `/chv/coverage-requests/${encodeURIComponent(publicId)}/assign/`,
      {
        method: "POST",
        cookieHeader,
        body: JSON.stringify(payload),
      },
    );

    return NextResponse.json(coverageRequest);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to assign CHV coverage request." }, { status: 500 });
  }
}
