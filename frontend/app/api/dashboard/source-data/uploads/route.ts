import { NextResponse } from "next/server";

import type { SourceDataUploadBatchRecord, SourceDataUploadListResponse } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

function sourceDataUploadQuery(request: Request) {
  const url = new URL(request.url);
  const query = url.searchParams.toString();
  return `/source-data/uploads/${query ? `?${query}` : ""}`;
}

export async function GET(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  try {
    const uploads = await fetchBackendJson<SourceDataUploadListResponse>(
      sourceDataUploadQuery(request),
      { cookieHeader },
    );
    return NextResponse.json(uploads);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json(error.payload, { status: error.status });
    }
    return NextResponse.json({ detail: "Unable to load source-data uploads." }, { status: 500 });
  }
}

export async function POST(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const formData = await request.formData();

  try {
    const upload = await fetchBackendJson<SourceDataUploadBatchRecord>(
      "/source-data/uploads/",
      {
        method: "POST",
        cookieHeader,
        body: formData,
      },
    );
    return NextResponse.json(upload, { status: 201 });
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json(error.payload, { status: error.status });
    }
    return NextResponse.json({ detail: "Unable to create source-data upload." }, { status: 500 });
  }
}
