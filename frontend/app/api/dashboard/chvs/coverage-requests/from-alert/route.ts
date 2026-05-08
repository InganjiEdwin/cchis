import { NextResponse } from "next/server";

import type {
  ChvCoverageRequestFromAlertPrefillPayload,
  ChvCoverageRequestFromAlertPrefillResponse,
} from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";

export async function POST(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  let payload: ChvCoverageRequestFromAlertPrefillPayload;
  try {
    payload = (await request.json()) as ChvCoverageRequestFromAlertPrefillPayload;
  } catch {
    return NextResponse.json({ detail: "Invalid alert-linked coverage request payload." }, { status: 400 });
  }

  try {
    const response = await fetchBackendJson<ChvCoverageRequestFromAlertPrefillResponse>(
      "/chv/coverage-requests/from-alert/prefill/",
      {
        method: "POST",
        cookieHeader,
        body: JSON.stringify(payload),
      },
    );

    return NextResponse.json(response);
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json(error.payload ?? { detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to prepare alert-linked CHV coverage request." }, { status: 500 });
  }
}
