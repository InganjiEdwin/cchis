import { NextResponse } from "next/server";

import type { SourceDataConnectorRegistryResponse } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function GET(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  try {
    const connectors = await fetchBackendJson<SourceDataConnectorRegistryResponse>(
      "/source-data/connectors/",
      { cookieHeader },
    );
    return NextResponse.json(connectors);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json(error.payload ?? { detail: error.message }, { status: error.status });
    }
    return NextResponse.json({ detail: "Unable to load source-data connectors." }, { status: 500 });
  }
}
