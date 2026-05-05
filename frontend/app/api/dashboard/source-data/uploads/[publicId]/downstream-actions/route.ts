import { NextResponse } from "next/server";

import type { SourceDataDownstreamActionPayload, SourceDataDownstreamActionResponse } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ publicId: string }> },
) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const { publicId } = await params;
  const payload = (await request.json().catch(() => ({}))) as SourceDataDownstreamActionPayload;

  try {
    const response = await fetchBackendJson<SourceDataDownstreamActionResponse>(
      `/source-data/uploads/${encodeURIComponent(publicId)}/downstream-actions/`,
      {
        method: "POST",
        cookieHeader,
        body: JSON.stringify(payload),
      },
    );
    return NextResponse.json(response, { status: response.action_status === "queued" ? 202 : 200 });
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }
    return NextResponse.json({ detail: "Unable to run source-data downstream action." }, { status: 500 });
  }
}
