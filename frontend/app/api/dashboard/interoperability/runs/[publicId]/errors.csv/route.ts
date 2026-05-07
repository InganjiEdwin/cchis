import { NextResponse } from "next/server";

import type { InteroperabilityErrorFileResponse } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

function safeFilename(filename: string) {
  return filename.replace(/[^A-Za-z0-9._-]/g, "_") || "interoperability-run-errors.csv";
}

export async function GET(
  request: Request,
  { params }: { params: Promise<{ publicId: string }> },
) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const { publicId } = await params;

  try {
    const file = await fetchBackendJson<InteroperabilityErrorFileResponse>(
      `/interoperability/runs/${encodeURIComponent(publicId)}/errors.csv/`,
      { cookieHeader },
    );
    return new NextResponse(file.payload, {
      status: 200,
      headers: {
        "Content-Type": file.content_type || "text/csv",
        "Content-Disposition": `attachment; filename="${safeFilename(file.filename)}"`,
        "X-Payload-SHA256": file.payload_sha256,
        "X-Row-Count": String(file.row_count),
      },
    });
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }
    return NextResponse.json({ detail: "Unable to download rows to fix." }, { status: 500 });
  }
}
