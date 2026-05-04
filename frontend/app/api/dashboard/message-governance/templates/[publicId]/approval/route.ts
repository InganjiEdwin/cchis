import { NextResponse } from "next/server";

import type { MessageTemplateApprovalPayload, MessageTemplateDetailResponse } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

type RouteContext = {
  params: Promise<{ publicId: string }>;
};

export async function POST(request: Request, context: RouteContext) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const { publicId } = await context.params;
  const payload = (await request.json()) as MessageTemplateApprovalPayload;

  try {
    const updatedTemplate = await fetchBackendJson<MessageTemplateDetailResponse>(
      `/message-governance/templates/${encodeURIComponent(publicId)}/approval/`,
      {
        method: "POST",
        body: JSON.stringify(payload),
        cookieHeader,
      },
    );

    return NextResponse.json(updatedTemplate);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to update template approval." }, { status: 500 });
  }
}
