import { NextResponse } from "next/server";

import type { SourceDataUploadBatchRecord } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ publicId: string }> },
) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const { publicId } = await params;

  try {
    const upload = await fetchBackendJson<SourceDataUploadBatchRecord>(
      `/source-data/uploads/${encodeURIComponent(publicId)}/`,
      { cookieHeader },
    );
    return NextResponse.json(upload);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json(error.payload ?? { detail: error.message }, { status: error.status });
    }
    return NextResponse.json({ detail: "Unable to load source-data upload." }, { status: 500 });
  }
}
