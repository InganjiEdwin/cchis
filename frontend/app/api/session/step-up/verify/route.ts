import { NextResponse } from "next/server";

import { applyBackendSetCookie, fetchBackendAuthorizedResponse } from "@/lib/server-api";

export async function POST(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  try {
    const body = await request.text();
    const backendResponse = await fetchBackendAuthorizedResponse("/auth/step-up/verify/", {
      method: "POST",
      body,
      cookieHeader,
    });
    const data = (await backendResponse.json().catch(() => ({}))) as Record<string, unknown>;

    if (!backendResponse.ok) {
      return applyBackendSetCookie(
        NextResponse.json(
          {
            detail: typeof data.detail === "string" ? data.detail : "Unable to verify your code.",
            ...(typeof data.code === "string" ? { code: data.code } : {}),
            ...(typeof data.purpose === "string" ? { purpose: data.purpose } : {}),
          },
          { status: backendResponse.status },
        ),
        backendResponse,
      );
    }

    return applyBackendSetCookie(NextResponse.json(data), backendResponse);
  } catch {
    return NextResponse.json({ detail: "Unable to verify your code." }, { status: 500 });
  }
}
