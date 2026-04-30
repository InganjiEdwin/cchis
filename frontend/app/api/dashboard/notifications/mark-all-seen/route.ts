import { NextResponse } from "next/server";

import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function POST(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  try {
    const payload = await fetchBackendJson("/notifications/mark-all-seen/", {
      method: "POST",
      cookieHeader,
    });
    return NextResponse.json(payload);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to mark all notifications as seen." }, { status: 500 });
  }
}
