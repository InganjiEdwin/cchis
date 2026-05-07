import "server-only";

import { cookies } from "next/headers";

import { getApiBaseUrl, type SessionResponse } from "@/lib/auth";
import { getBackendSetCookieHeaders } from "@/lib/server-api";

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
  const result = await fetchServerSessionResult();
  return result.session;
}

export async function fetchServerSessionResult(): Promise<{
  session: SessionResponse | null;
  cookieHeaders: string[];
}> {
  const cookieStore = await cookies();
  const cookieHeader = cookieStore.toString();

  try {
    const response = await fetch(`${getApiBaseUrl()}/auth/session/`, {
      method: "GET",
      headers: cookieHeader ? { Cookie: cookieHeader } : {},
      cache: "no-store",
    });

    if (!response.ok) {
      return { session: null, cookieHeaders: getBackendSetCookieHeaders(response) };
    }

    return {
      session: (await response.json()) as SessionResponse,
      cookieHeaders: getBackendSetCookieHeaders(response),
    };
  } catch {
    return { session: null, cookieHeaders: [] };
  }
}
