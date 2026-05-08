import { NextResponse } from "next/server";

import type { BeginTwoFactorEnrollmentResponse } from "@/lib/auth";
import { applyBackendSetCookie, fetchBackendAuthorizedResponse, fetchBackendResponse } from "@/lib/server-api";

export async function POST(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  try {
    const body = await request.text();
    let token = "";

    try {
      const parsed = body ? (JSON.parse(body) as { token?: unknown }) : {};
      token = typeof parsed.token === "string" ? parsed.token.trim() : "";
    } catch {
      token = "";
    }

    const fetchBackend = token ? fetchBackendResponse : fetchBackendAuthorizedResponse;
    const backendResponse = await fetchBackend("/auth/2fa/setup/", {
      method: "POST",
      body: body || JSON.stringify({}),
      cookieHeader,
    });

    const data = (await backendResponse.json().catch(() => ({}))) as
      | BeginTwoFactorEnrollmentResponse
      | { detail?: string };

    if (!backendResponse.ok) {
      return applyBackendSetCookie(
        NextResponse.json(
          { detail: "detail" in data && typeof data.detail === "string" ? data.detail : "Unable to start two-factor setup." },
          { status: backendResponse.status },
        ),
        backendResponse,
      );
    }

    return applyBackendSetCookie(NextResponse.json(data), backendResponse);
  } catch {
    return NextResponse.json({ detail: "Unable to start two-factor setup." }, { status: 500 });
  }
}
