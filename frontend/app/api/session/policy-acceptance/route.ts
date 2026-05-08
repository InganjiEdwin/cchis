import { NextResponse } from "next/server";

import { applyBackendSetCookie, fetchBackendAuthorizedResponse, ServerApiError } from "@/lib/server-api";

async function readBackendJson(response: Response) {
  return (await response.json().catch(() => ({}))) as Record<string, unknown>;
}

function jsonFromBackend(data: Record<string, unknown>, backendResponse: Response) {
  return applyBackendSetCookie(
    NextResponse.json(data, { status: backendResponse.status }),
    backendResponse,
  );
}

export async function GET(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  try {
    const backendResponse = await fetchBackendAuthorizedResponse("/auth/policy-acceptance/", {
      method: "GET",
      cookieHeader,
    });
    const data = await readBackendJson(backendResponse);

    return jsonFromBackend(data, backendResponse);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json(error.payload ?? { detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to load policy acceptance status." }, { status: 500 });
  }
}

export async function POST(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  try {
    const body = await request.text();
    const backendResponse = await fetchBackendAuthorizedResponse("/auth/policy-acceptance/", {
      method: "POST",
      body,
      cookieHeader,
    });
    const data = await readBackendJson(backendResponse);

    return jsonFromBackend(data, backendResponse);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json(error.payload ?? { detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to accept policies." }, { status: 500 });
  }
}
