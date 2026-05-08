import "server-only";

import { cookies } from "next/headers";

import { getApiBaseUrl, type SessionResponse } from "@/lib/auth";
import { getBackendSetCookieHeaders } from "@/lib/server-api";

type FetchServerSessionOptions = {
  allowRefreshBootstrap?: boolean;
};

function getCchisEnvironment() {
  return (process.env.CCHIS_ENVIRONMENT ?? process.env.NEXT_PUBLIC_CCHIS_ENVIRONMENT ?? "local")
    .trim()
    .toLowerCase();
}

function getAccessCookieName() {
  const configuredName = process.env.AUTH_ACCESS_COOKIE_NAME?.trim();
  if (configuredName) {
    return configuredName;
  }

  return ["staging", "production"].includes(getCchisEnvironment())
    ? "__Host-cchis_access"
    : "cchis_access";
}

export function sanitizeSessionResponse(session: SessionResponse | null): SessionResponse | null {
  if (!session) {
    return null;
  }

  return {
    ...session,
    access: null,
  };
}

export async function fetchServerSession(
  options: FetchServerSessionOptions = {},
): Promise<SessionResponse | null> {
  const result = await fetchServerSessionResult(options);
  return result.session;
}

export async function fetchServerSessionResult(
  { allowRefreshBootstrap = true }: FetchServerSessionOptions = {},
): Promise<{
  session: SessionResponse | null;
  cookieHeaders: string[];
}> {
  const cookieStore = await cookies();
  let cookieHeader = cookieStore.toString();

  if (!allowRefreshBootstrap) {
    const accessCookie = cookieStore.get(getAccessCookieName());
    if (!accessCookie?.value) {
      return { session: null, cookieHeaders: [] };
    }
    cookieHeader = `${accessCookie.name}=${accessCookie.value}`;
  }

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
