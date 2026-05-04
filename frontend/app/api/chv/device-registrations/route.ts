import { NextResponse } from "next/server";

import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function POST(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const payload = (await request.json().catch(() => ({}))) as Record<string, unknown>;

  try {
    const registration = await fetchBackendJson<Record<string, unknown>>("/chv/device-registrations/", {
      method: "POST",
      cookieHeader,
      body: JSON.stringify(payload),
    });

    return NextResponse.json(registration, { status: 201 });
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to register this CHV device." }, { status: 500 });
  }
}

