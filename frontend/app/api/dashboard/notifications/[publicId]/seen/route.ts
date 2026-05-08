import { NextResponse } from "next/server";

import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function POST(request: Request, context: { params: Promise<{ publicId: string }> }) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const { publicId } = await context.params;

  try {
    const payload = await fetchBackendJson(`/notifications/${publicId}/seen/`, {
      method: "POST",
      cookieHeader,
    });
    return NextResponse.json(payload);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json(error.payload ?? { detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to mark the notification as seen." }, { status: 500 });
  }
}
