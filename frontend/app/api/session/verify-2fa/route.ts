import { NextResponse } from "next/server";

import type { VerifyTwoFactorResponse } from "@/lib/auth";
import { applyBackendSetCookie, fetchBackendResponse } from "@/lib/server-api";

export async function POST(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  try {
    const body = await request.text();
    const backendResponse = await fetchBackendResponse("/auth/verify-2fa/", {
      method: "POST",
      body,
      cookieHeader,
    });

    const data = (await backendResponse.json().catch(() => ({}))) as Record<string, unknown>;

    if (!backendResponse.ok) {
      return applyBackendSetCookie(
        NextResponse.json(
          { detail: typeof data.detail === "string" ? data.detail : "Unable to verify your code." },
          { status: backendResponse.status },
        ),
        backendResponse,
      );
    }

    const responseBody: VerifyTwoFactorResponse = {
      requires_2fa: false,
      user: data.user as VerifyTwoFactorResponse["user"],
      session_established: true,
      second_factor_method:
        data.second_factor_method === "recovery_code" || data.second_factor_method === "totp"
          ? data.second_factor_method
          : undefined,
      recovery_codes_remaining:
        typeof data.recovery_codes_remaining === "number" ? data.recovery_codes_remaining : undefined,
      recovery_codes_low: typeof data.recovery_codes_low === "boolean" ? data.recovery_codes_low : undefined,
    };

    return applyBackendSetCookie(NextResponse.json(responseBody), backendResponse);
  } catch {
    return NextResponse.json({ detail: "Unable to verify your code." }, { status: 500 });
  }
}
