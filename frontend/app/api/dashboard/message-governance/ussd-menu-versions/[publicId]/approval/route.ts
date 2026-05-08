import { NextResponse } from "next/server";

import type { UssdMenuVersionApprovalPayload, UssdMenuVersionRecord } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

type RouteContext = {
  params: Promise<{ publicId: string }>;
};

export async function POST(request: Request, context: RouteContext) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const { publicId } = await context.params;
  const payload = (await request.json()) as UssdMenuVersionApprovalPayload;

  try {
    const updatedMenuVersion = await fetchBackendJson<UssdMenuVersionRecord>(
      `/message-governance/ussd-menu-versions/${encodeURIComponent(publicId)}/approval/`,
      {
        method: "POST",
        body: JSON.stringify(payload),
        cookieHeader,
      },
    );

    return NextResponse.json(updatedMenuVersion);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json(error.payload, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to update USSD menu approval." }, { status: 500 });
  }
}
