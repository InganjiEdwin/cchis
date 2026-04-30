import { NextResponse } from "next/server";

import type { ChvMessageRecord } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

type RouteContext = {
  params: Promise<{
    publicId: string;
  }>;
};

export async function GET(request: Request, context: RouteContext) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const { publicId } = await context.params;

  try {
    const messages = await fetchBackendJson<ChvMessageRecord[]>(`/chvs/${encodeURIComponent(publicId)}/messages/`, {
      cookieHeader,
    });

    return NextResponse.json(messages);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to load CHV messages." }, { status: 500 });
  }
}

export async function POST(request: Request, context: RouteContext) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const { publicId } = await context.params;

  try {
    const body = await request.json();
    const message = await fetchBackendJson<ChvMessageRecord>(`/chvs/${encodeURIComponent(publicId)}/messages/`, {
      method: "POST",
      cookieHeader,
      body: JSON.stringify(body),
    });

    return NextResponse.json(message, { status: 201 });
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to create CHV message." }, { status: 500 });
  }
}
