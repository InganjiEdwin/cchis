import { NextResponse } from "next/server";

import type { RegenerateRecoveryCodesResponse } from "@/lib/auth";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function POST(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  try {
    const body = await request.text();
    const response = await fetchBackendJson<RegenerateRecoveryCodesResponse>("/auth/2fa/recovery-codes/regenerate/", {
      method: "POST",
      body,
      cookieHeader,
    });

    return NextResponse.json(response);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to regenerate recovery codes." }, { status: 500 });
  }
}
