import { NextResponse } from "next/server";

import { jsonWithBackendCookies } from "@/lib/server-api";
import { fetchServerSessionResult, sanitizeSessionResponse } from "@/lib/server-session";

export async function GET() {
  try {
    const { session: backendSession, cookieHeaders } = await fetchServerSessionResult();
    const session = sanitizeSessionResponse(backendSession);

    if (!session?.authenticated || !session.user) {
      return jsonWithBackendCookies(
        session ?? {
          authenticated: false,
          user: null,
          access: null,
          session_source: null,
        },
        undefined,
        cookieHeaders,
      );
    }

    return jsonWithBackendCookies(session, undefined, cookieHeaders);
  } catch {
    return NextResponse.json({ detail: "Unable to resolve session state." }, { status: 500 });
  }
}
