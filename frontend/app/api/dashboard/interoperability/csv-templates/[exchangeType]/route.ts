import { NextResponse } from "next/server";

import type { InteroperabilityCsvTemplateFileResponse } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

function safeFilename(filename: string) {
  return filename.replace(/[^A-Za-z0-9._-]/g, "_") || "interoperability-template.csv";
}

export async function GET(
  request: Request,
  { params }: { params: Promise<{ exchangeType: string }> },
) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const { exchangeType } = await params;

  try {
    const file = await fetchBackendJson<InteroperabilityCsvTemplateFileResponse>(
      `/interoperability/csv-templates/${encodeURIComponent(exchangeType)}/`,
      { cookieHeader },
    );
    return new NextResponse(file.payload, {
      status: 200,
      headers: {
        "Content-Type": file.content_type || "text/csv",
        "Content-Disposition": `attachment; filename="${safeFilename(file.filename)}"`,
        "X-Payload-SHA256": file.payload_sha256,
        "X-Row-Count": String(file.row_count),
        "X-Exchange-Type": file.exchange_type,
      },
    });
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }
    return NextResponse.json({ detail: "Unable to download interoperability CSV template." }, { status: 500 });
  }
}
