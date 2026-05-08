import { NextResponse } from "next/server";

import type { ProfileSessionRevokeResponse } from "@/lib/auth";
import { jsonWithBackendCookies, fetchBackendAuthorizedResponse } from "@/lib/server-api";

type RouteContext = {
  params: Promise<{ publicId: string }>;
};

export async function POST(request: Request, context: RouteContext) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const { publicId } = await context.params;

  try {
    const backendResponse = await fetchBackendAuthorizedResponse(
      `/auth/sessions/${encodeURIComponent(publicId)}/revoke/`,
      {
        method: "POST",
        body: JSON.stringify({}),
        cookieHeader,
      },
    );
    const data = (await backendResponse.json().catch(() => ({
      detail: "Unable to revoke this session.",
    }))) as ProfileSessionRevokeResponse | Record<string, unknown>;

    return jsonWithBackendCookies(data, { status: backendResponse.status }, backendResponse);
  } catch {
    return NextResponse.json({ detail: "Unable to revoke this session." }, { status: 500 });
  }
}
