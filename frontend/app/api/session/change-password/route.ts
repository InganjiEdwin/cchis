import { NextResponse } from "next/server";

import type { ChangePasswordResponse } from "@/lib/auth";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function POST(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  try {
    const body = await request.text();
    const response = await fetchBackendJson<ChangePasswordResponse>("/auth/change-password/", {
      method: "POST",
      body,
      cookieHeader,
    });

    return NextResponse.json(response);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json(error.payload ?? { detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to change password." }, { status: 500 });
  }
}
