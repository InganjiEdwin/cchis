import { NextResponse } from "next/server";

import { fetchServerSession, sanitizeSessionResponse } from "@/lib/server-session";

export async function GET() {
  try {
    const session = sanitizeSessionResponse(await fetchServerSession());

    if (!session?.authenticated || !session.user) {
      return NextResponse.json(session ?? {
        authenticated: false,
        user: null,
        access: null,
        session_source: null,
      });
    }

    return NextResponse.json(session);
  } catch {
    return NextResponse.json({ detail: "Unable to resolve session state." }, { status: 500 });
  }
}
