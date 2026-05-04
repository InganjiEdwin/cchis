import { NextResponse } from "next/server";

import type { MessageTemplateDetailResponse } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

type RouteContext = {
  params: Promise<{ publicId: string }>;
};

export async function GET(request: Request, context: RouteContext) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const { publicId } = await context.params;

  try {
    const templateDetail = await fetchBackendJson<MessageTemplateDetailResponse>(
      `/message-governance/templates/${encodeURIComponent(publicId)}/`,
      {
        cookieHeader,
      },
    );

    return NextResponse.json(templateDetail);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to load message template detail." }, { status: 500 });
  }
}
