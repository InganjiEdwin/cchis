import { NextResponse } from "next/server";

import type { CurrentUser } from "@/lib/auth";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function PATCH(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  try {
    const body = await request.text();
    const user = await fetchBackendJson<CurrentUser>("/auth/me/", {
      method: "PATCH",
      body,
      cookieHeader,
    });

    return NextResponse.json(user);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to update profile." }, { status: 500 });
  }
}
