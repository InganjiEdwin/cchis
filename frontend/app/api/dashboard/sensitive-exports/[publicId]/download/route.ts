import { NextResponse } from "next/server";

import type { SensitiveExportDownloadResponse } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ publicId: string }> },
) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const { publicId } = await params;

  try {
    const download = await fetchBackendJson<SensitiveExportDownloadResponse>(
      `/sensitive-exports/${encodeURIComponent(publicId)}/download/`,
      {
        cookieHeader,
      },
    );

    return NextResponse.json(download);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to download sensitive export." }, { status: 500 });
  }
}
