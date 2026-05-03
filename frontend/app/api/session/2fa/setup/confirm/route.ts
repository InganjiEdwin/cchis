import { NextResponse } from "next/server";

import type { ConfirmTwoFactorEnrollmentResponse } from "@/lib/auth";
import { applyBackendSetCookie, fetchBackendResponse } from "@/lib/server-api";

export async function POST(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  try {
    const body = await request.text();
    let token = "";

    try {
      const parsed = body ? (JSON.parse(body) as { token?: unknown }) : {};
      token = typeof parsed.token === "string" ? parsed.token : "";
    } catch {
      token = "";
    }

    const backendResponse = await fetchBackendResponse("/auth/2fa/setup/confirm/", {
      method: "POST",
      body,
      cookieHeader,
    });

    const data = (await backendResponse.json().catch(() => ({}))) as
      | ConfirmTwoFactorEnrollmentResponse
      | { detail?: string; user?: unknown; enrollment_completed?: true };
    const dataRecord = data as Record<string, unknown>;

    if (!backendResponse.ok) {
      return applyBackendSetCookie(
        NextResponse.json(
          { detail: "detail" in data && typeof data.detail === "string" ? data.detail : "Unable to finish two-factor setup." },
          { status: backendResponse.status },
        ),
        backendResponse,
      );
    }

    const responseBody =
      token && "enrollment_completed" in data
        ? {
            detail: "detail" in data && typeof data.detail === "string"
              ? data.detail
              : "Two-factor enrollment completed successfully.",
            user: "user" in data ? data.user : null,
            enrollment_completed: true as const,
            requires_2fa: false as const,
            session_established: true as const,
            recovery_codes: Array.isArray(dataRecord.recovery_codes) ? dataRecord.recovery_codes : [],
            recovery_codes_generated: dataRecord.recovery_codes_generated === true,
          }
        : data;

    return applyBackendSetCookie(NextResponse.json(responseBody), backendResponse);
  } catch {
    return NextResponse.json({ detail: "Unable to finish two-factor setup." }, { status: 500 });
  }
}
