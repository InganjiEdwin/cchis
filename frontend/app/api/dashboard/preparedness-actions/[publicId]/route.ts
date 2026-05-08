import { NextResponse } from "next/server";

import type { PreparednessActionRecord } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ publicId: string }> },
) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const { publicId } = await params;

  try {
    const action = await fetchBackendJson<PreparednessActionRecord>(
      `/preparedness-actions/${encodeURIComponent(publicId)}/`,
      {
        cookieHeader,
      },
    );

    return NextResponse.json(action);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json(error.payload ?? { detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to load preparedness action." }, { status: 500 });
  }
}

export async function PATCH(
  request: Request,
  { params }: { params: Promise<{ publicId: string }> },
) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const { publicId } = await params;

  try {
    const body = await request.json();
    const action = await fetchBackendJson<PreparednessActionRecord>(
      `/preparedness-actions/${encodeURIComponent(publicId)}/`,
      {
        method: "PATCH",
        body: JSON.stringify(body),
        cookieHeader,
      },
    );

    return NextResponse.json(action);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json(error.payload ?? { detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to update preparedness action." }, { status: 500 });
  }
}
