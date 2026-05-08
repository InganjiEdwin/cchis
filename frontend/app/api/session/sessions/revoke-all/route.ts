import { NextResponse } from "next/server";

import type { ProfileSessionRevokeResponse } from "@/lib/auth";
import { jsonWithBackendCookies, fetchBackendAuthorizedResponse } from "@/lib/server-api";

export async function POST(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  try {
    const backendResponse = await fetchBackendAuthorizedResponse("/auth/sessions/revoke-all/", {
      method: "POST",
      body: JSON.stringify({}),
      cookieHeader,
    });
    const data = (await backendResponse.json().catch(() => ({
      detail: "Unable to revoke sessions.",
    }))) as ProfileSessionRevokeResponse | Record<string, unknown>;

    return jsonWithBackendCookies(data, { status: backendResponse.status }, backendResponse);
  } catch {
    return NextResponse.json({ detail: "Unable to revoke sessions." }, { status: 500 });
  }
}
