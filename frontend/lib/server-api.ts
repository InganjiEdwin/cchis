import "server-only";

import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { getApiBaseUrl, type SessionResponse } from "@/lib/auth";

type ServerApiRequestInit = Omit<RequestInit, "headers"> & {
  cookieHeader?: string;
  headers?: HeadersInit;
};

export class ServerApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function resolveCookieHeader(explicitCookieHeader?: string) {
  if (explicitCookieHeader !== undefined) {
    return explicitCookieHeader;
  }

  const cookieStore = await cookies();
  return cookieStore.toString();
}

export async function fetchBackendResponse(path: string, init: ServerApiRequestInit = {}): Promise<Response> {
  const cookieHeader = await resolveCookieHeader(init.cookieHeader);
  const headers = new Headers(init.headers);

  if (!headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json");
  }

  if (cookieHeader && !headers.has("Cookie")) {
    headers.set("Cookie", cookieHeader);
  }

  return fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });
}

export function applyBackendSetCookie(target: NextResponse, source: Response): NextResponse {
  const setCookie = source.headers.get("set-cookie");

  if (setCookie) {
    target.headers.set("set-cookie", setCookie);
  }

  return target;
}

async function fetchBackendSession(cookieHeader: string): Promise<SessionResponse | null> {
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

export async function fetchBackendJson<T>(path: string, init: ServerApiRequestInit = {}): Promise<T> {
  const cookieHeader = await resolveCookieHeader(init.cookieHeader);
  const session = await fetchBackendSession(cookieHeader);

  if (!session?.authenticated || !session.access) {
    throw new ServerApiError(401, "Authentication required.");
  }

  const headers = new Headers(init.headers);

  if (!headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json");
  }

  headers.set("Authorization", `Bearer ${session.access}`);

  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });

  if (!response.ok) {
    let detail = "Unable to load server-side dashboard data.";

    try {
      const data = (await response.json()) as { detail?: string };
      detail = data.detail ?? detail;
    } catch {
      // Keep generic detail if parsing fails.
    }

    throw new ServerApiError(response.status, detail);
  }

  if (response.status === 204 || response.status === 205) {
    return undefined as T;
  }

  return (await response.json()) as T;
}
