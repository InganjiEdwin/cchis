import { NextResponse } from "next/server";

import { applyBackendSetCookie, fetchBackendAuthorizedResponse, ServerApiError } from "@/lib/server-api";

export async function POST(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  try {
    const backendResponse = await fetchBackendAuthorizedResponse("/auth/logout/", {
      method: "POST",
      body: JSON.stringify({}),
      cookieHeader,
    });

    if (!backendResponse.ok) {
      const data = (await backendResponse.json().catch(() => ({
        detail: "Unable to end the current session.",
      }))) as Record<string, unknown>;
      return applyBackendSetCookie(
        NextResponse.json(data, { status: backendResponse.status }),
        backendResponse,
      );
    }

    return applyBackendSetCookie(new NextResponse(null, { status: 204 }), backendResponse);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json(error.payload ?? { detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to end the current session." }, { status: 500 });
  }
}
