import { NextResponse } from "next/server";

import type { SourceDataConfirmPayload, SourceDataUploadBatchRecord } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ publicId: string }> },
) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const { publicId } = await params;
  const payload = (await request.json().catch(() => ({}))) as SourceDataConfirmPayload;

  try {
    const upload = await fetchBackendJson<SourceDataUploadBatchRecord>(
      `/source-data/uploads/${encodeURIComponent(publicId)}/confirm/`,
      {
        method: "POST",
        cookieHeader,
        body: JSON.stringify(payload),
      },
    );
    return NextResponse.json(upload, { status: upload.status === "confirming" ? 202 : 200 });
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }
    return NextResponse.json({ detail: "Unable to confirm source-data upload." }, { status: 500 });
  }
}
