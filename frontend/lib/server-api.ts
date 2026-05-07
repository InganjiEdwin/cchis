import "server-only";

import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { getApiBaseUrl, requiresPolicyAcceptance, type SessionResponse } from "@/lib/auth";

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

function stringifyErrorValue(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }

  if (Array.isArray(value)) {
    return value.map((item) => stringifyErrorValue(item)).filter(Boolean).join(" ");
  }

  if (value && typeof value === "object") {
    return formatBackendErrorDetail(value as Record<string, unknown>);
  }

  return "";
}

function formatBackendErrorDetail(data: Record<string, unknown>) {
  const errors = data.errors && typeof data.errors === "object" && !Array.isArray(data.errors)
    ? data.errors as Record<string, unknown>
    : data;
  const fieldMessages = Object.entries(errors)
    .filter(([field]) => field !== "detail" && field !== "errors")
    .map(([field, value]) => {
      const message = stringifyErrorValue(value);
      return message ? `${field.replaceAll("_", " ")}: ${message}` : "";
    })
    .filter(Boolean);

  if (fieldMessages.length > 0) {
    return fieldMessages.join(" ");
  }

  return typeof data.detail === "string" ? data.detail : "Request failed.";
}

function isFormDataBody(body: BodyInit | null | undefined) {
  return typeof FormData !== "undefined" && body instanceof FormData;
}

async function resolveCookieHeader(explicitCookieHeader?: string) {
  if (explicitCookieHeader !== undefined) {
    return explicitCookieHeader;
  }

  const cookieStore = await cookies();
  return cookieStore.toString();
}

function buildBackendHeaders(init: ServerApiRequestInit, cookieHeader: string) {
  const headers = new Headers(init.headers);

  if (!headers.has("Content-Type") && init.body && !isFormDataBody(init.body)) {
    headers.set("Content-Type", "application/json");
  }

  if (cookieHeader && !headers.has("Cookie")) {
    headers.set("Cookie", cookieHeader);
  }

  return headers;
}

export async function fetchBackendResponse(path: string, init: ServerApiRequestInit = {}): Promise<Response> {
  const cookieHeader = await resolveCookieHeader(init.cookieHeader);
  const headers = buildBackendHeaders(init, cookieHeader);

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

function isPolicyAcceptanceBypassPath(path: string, method: string) {
  const normalizedMethod = method.toUpperCase();
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const exactAllowedPaths = new Set([
    "/auth/session/",
    "/auth/policy-acceptance/",
    "/auth/logout/",
    "/auth/verify-2fa/",
    "/auth/2fa/setup/",
    "/auth/2fa/setup/confirm/",
  ]);

  if (exactAllowedPaths.has(normalizedPath)) {
    return true;
  }

  return normalizedMethod === "GET" && normalizedPath === "/auth/me/";
}

export async function fetchBackendAuthorizedResponse(path: string, init: ServerApiRequestInit = {}): Promise<Response> {
  const cookieHeader = await resolveCookieHeader(init.cookieHeader);
  const session = await fetchBackendSession(cookieHeader);

  if (!session?.authenticated || !session.access) {
    throw new ServerApiError(401, "Authentication required.");
  }

  if (
    session.user &&
    requiresPolicyAcceptance(session.user) &&
    !isPolicyAcceptanceBypassPath(path, init.method ?? "GET")
  ) {
    throw new ServerApiError(403, "Policy acceptance is required before using this API.");
  }

  const headers = buildBackendHeaders(init, cookieHeader);
  headers.set("Authorization", `Bearer ${session.access}`);

  return fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });
}

export async function fetchBackendJson<T>(path: string, init: ServerApiRequestInit = {}): Promise<T> {
  const response = await fetchBackendAuthorizedResponse(path, init);

  if (!response.ok) {
    let detail = "Unable to load server-side dashboard data.";

    try {
      const data = (await response.json()) as Record<string, unknown>;
      detail = formatBackendErrorDetail(data);
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
