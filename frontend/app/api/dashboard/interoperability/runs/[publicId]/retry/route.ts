import { NextResponse } from "next/server";

import type { InteroperabilityRunRecord } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ publicId: string }> },
) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const { publicId } = await params;

  try {
    const run = await fetchBackendJson<InteroperabilityRunRecord>(
      `/interoperability/runs/${encodeURIComponent(publicId)}/retry/`,
      {
        method: "POST",
        cookieHeader,
        body: JSON.stringify({}),
      },
    );
    return NextResponse.json(run, { status: 201 });
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json(error.payload, { status: error.status });
    }
    return NextResponse.json({ detail: "Unable to try the transfer again." }, { status: 500 });
  }
}
