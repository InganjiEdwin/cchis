import { NextResponse } from "next/server";

import type { SourceDataCsvTemplateFileResponse } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

function safeFilename(filename: string) {
  return filename.replace(/[^A-Za-z0-9._-]/g, "_") || "source-data-template.csv";
}

export async function GET(
  request: Request,
  { params }: { params: Promise<{ feedKey: string }> },
) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const { feedKey } = await params;

  try {
    const file = await fetchBackendJson<SourceDataCsvTemplateFileResponse>(
      `/source-data/templates/${encodeURIComponent(feedKey)}/`,
      { cookieHeader },
    );
    return new NextResponse(file.payload, {
      status: 200,
      headers: {
        "Content-Type": file.content_type || "text/csv",
        "Content-Disposition": `attachment; filename="${safeFilename(file.filename)}"`,
        "X-Payload-SHA256": file.payload_sha256,
        "X-Row-Count": String(file.row_count),
        "X-Feed-Key": file.feed_key,
      },
    });
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json(error.payload ?? { detail: error.message }, { status: error.status });
    }
    return NextResponse.json({ detail: "Unable to download source-data CSV template." }, { status: 500 });
  }
}
