import { NextResponse } from "next/server";

import type { ChvActivityRecord } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function GET(request: Request, { params }: { params: Promise<{ publicId: string }> }) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const { publicId } = await params;

  try {
    const activity = await fetchBackendJson<ChvActivityRecord[]>(`/chvs/${encodeURIComponent(publicId)}/activity/`, {
      cookieHeader,
    });

    return NextResponse.json(activity);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to load CHV activity." }, { status: 500 });
  }
}
