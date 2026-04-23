import "server-only";

import { cookies } from "next/headers";

import { getApiBaseUrl, type SessionResponse } from "@/lib/auth";

export function sanitizeSessionResponse(session: SessionResponse | null): SessionResponse | null {
  if (!session) {
    return null;
  }

  return {
    ...session,
    access: null,
  };
}

export async function fetchServerSession(): Promise<SessionResponse | null> {
  const cookieStore = await cookies();
  const cookieHeader = cookieStore.toString();

  try {
    const response = await fetch(`${getApiBaseUrl()}/auth/session/`, {
      method: "GET",
      headers: cookieHeader ? { Cookie: cookieHeader } : {},
      cache: "no-store",
    });

    if (!response.ok) {
      return null;
    }

    return (await response.json()) as SessionResponse;
  } catch {
    return null;
  }
}
