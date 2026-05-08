import { NextResponse } from "next/server";

import type { InteroperabilityRunRecord } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ publicId: string }> },
) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const { publicId } = await params;

  try {
    const run = await fetchBackendJson<InteroperabilityRunRecord>(
      `/interoperability/runs/${encodeURIComponent(publicId)}/`,
      { cookieHeader },
    );
    return NextResponse.json(run);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json(error.payload ?? { detail: error.message }, { status: error.status });
    }
    return NextResponse.json({ detail: "Unable to load transfer review." }, { status: 500 });
  }
}
