import { NextResponse } from "next/server";

import type { SourceDataCancelPayload, SourceDataUploadBatchRecord } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ publicId: string }> },
) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const { publicId } = await params;
  const payload = (await request.json().catch(() => ({}))) as SourceDataCancelPayload;

  try {
    const upload = await fetchBackendJson<SourceDataUploadBatchRecord>(
      `/source-data/uploads/${encodeURIComponent(publicId)}/cancel/`,
      {
        method: "POST",
        cookieHeader,
        body: JSON.stringify(payload),
      },
    );
    return NextResponse.json(upload);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json(error.payload ?? { detail: error.message }, { status: error.status });
    }
    return NextResponse.json({ detail: "Unable to cancel source-data upload." }, { status: 500 });
  }
}
