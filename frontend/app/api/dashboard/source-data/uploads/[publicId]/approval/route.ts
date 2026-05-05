import { NextResponse } from "next/server";

import type { SourceDataApprovalPayload, SourceDataUploadBatchRecord } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ publicId: string }> },
) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const { publicId } = await params;
  const payload = (await request.json().catch(() => ({}))) as SourceDataApprovalPayload;

  try {
    const upload = await fetchBackendJson<SourceDataUploadBatchRecord>(
      `/source-data/uploads/${encodeURIComponent(publicId)}/approval/`,
      {
        method: "POST",
        cookieHeader,
        body: JSON.stringify(payload),
      },
    );
    return NextResponse.json(upload);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }
    return NextResponse.json({ detail: "Unable to update source-data approval." }, { status: 500 });
  }
}
