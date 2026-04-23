import { NextResponse } from "next/server";

import type { CurrentUser, LoginResponse } from "@/lib/auth";
import { applyBackendSetCookie, fetchBackendResponse } from "@/lib/server-api";

type SanitizedLoginResponse = LoginResponse & {
  session_established?: true;
};

export async function POST(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  try {
    const body = await request.text();
    const backendResponse = await fetchBackendResponse("/auth/login/", {
      method: "POST",
      body,
      cookieHeader,
    });

    const data = (await backendResponse.json().catch(() => ({}))) as Record<string, unknown>;

    if (!backendResponse.ok) {
      return applyBackendSetCookie(
        NextResponse.json(
          { detail: typeof data.detail === "string" ? data.detail : "Unable to sign in." },
          { status: backendResponse.status },
        ),
        backendResponse,
      );
    }

    const responseBody: SanitizedLoginResponse =
      data.requires_2fa === true || data.requires_2fa_enrollment === true
        ? (data as SanitizedLoginResponse)
        : {
            requires_2fa: false,
            requires_2fa_enrollment: false,
            user: data.user as CurrentUser,
            session_established: true,
          };

    return applyBackendSetCookie(NextResponse.json(responseBody), backendResponse);
  } catch {
    return NextResponse.json({ detail: "Unable to sign in." }, { status: 500 });
  }
}
