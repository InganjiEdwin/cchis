import { NextResponse } from "next/server";

import type { RecoveryCodeStatusResponse } from "@/lib/auth";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function GET(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  try {
    const response = await fetchBackendJson<RecoveryCodeStatusResponse>("/auth/2fa/recovery-codes/", {
      method: "GET",
      cookieHeader,
    });

    return NextResponse.json(response);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to load recovery code status." }, { status: 500 });
  }
}
