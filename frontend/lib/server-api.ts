import "server-only";

import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { getApiBaseUrl } from "@/lib/auth";

type ServerApiRequestInit = Omit<RequestInit, "headers"> & {
  cookieHeader?: string;
  headers?: HeadersInit;
};

export class ServerApiError extends Error {
  status: number;
  payload: Record<string, unknown>;

  constructor(status: number, message: string, payload?: Record<string, unknown>) {
    super(message);
    this.status = status;
    this.payload = payload ?? { detail: message };
  }
}

type CookieOptions = {
  path?: string;
  maxAge?: number;
  expires?: Date;
  httpOnly?: boolean;
  secure?: boolean;
  sameSite?: "lax" | "strict" | "none";
};

type ParsedSetCookie = {
  name: string;
  value: string;
  options: CookieOptions;
};

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
    .filter(([field]) => field !== "detail" && field !== "errors" && field !== "code" && field !== "purpose")
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

function getCchisEnvironment() {
  return (process.env.CCHIS_ENVIRONMENT ?? process.env.NEXT_PUBLIC_CCHIS_ENVIRONMENT ?? "local")
    .trim()
    .toLowerCase();
}

function getFrontendAppUrl() {
  return (process.env.FRONTEND_APP_URL ?? process.env.NEXT_PUBLIC_FRONTEND_APP_URL ?? "http://localhost:3000")
    .trim()
    .replace(/\/$/, "");
}

function isUnsafeMethod(method: string | undefined) {
  return ["POST", "PUT", "PATCH", "DELETE"].includes((method ?? "GET").toUpperCase());
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

function splitSetCookieHeader(header: string) {
  return header
    .split(/,(?=\s*[^;,=\s]+=[^;]+)/g)
    .map((value) => value.trim())
    .filter(Boolean);
}

export function getBackendSetCookieHeaders(source: Response | string[] | string | null | undefined) {
  if (!source) {
    return [];
  }

  if (Array.isArray(source)) {
    return source.filter(Boolean);
  }

  if (typeof source === "string") {
    return splitSetCookieHeader(source);
  }

  const headersWithSetCookie = source.headers as Headers & {
    getSetCookie?: () => string[];
  };
  const setCookies = headersWithSetCookie.getSetCookie?.();
  if (setCookies?.length) {
    return setCookies;
  }

  const header = source.headers.get("set-cookie");
  return header ? splitSetCookieHeader(header) : [];
}

function parseCookieHeader(cookieHeader: string) {
  const cookiesByName = new Map<string, string>();
  cookieHeader
    .split(";")
    .map((part) => part.trim())
    .filter(Boolean)
    .forEach((part) => {
      const equalsIndex = part.indexOf("=");
      if (equalsIndex <= 0) {
        return;
      }
      cookiesByName.set(part.slice(0, equalsIndex).trim(), part.slice(equalsIndex + 1).trim());
    });

  return cookiesByName;
}

function getCookieValue(cookieHeader: string, name: string) {
  return parseCookieHeader(cookieHeader).get(name) ?? "";
}

function parseSameSite(value: string): CookieOptions["sameSite"] | undefined {
  const normalizedValue = value.trim().toLowerCase();
  if (normalizedValue === "lax" || normalizedValue === "strict" || normalizedValue === "none") {
    return normalizedValue;
  }
  return undefined;
}

function parseSetCookieHeader(header: string): ParsedSetCookie | null {
  const [nameValuePair, ...attributePairs] = header.split(";").map((part) => part.trim());
  const equalsIndex = nameValuePair.indexOf("=");
  if (equalsIndex <= 0) {
    return null;
  }

  const parsedCookie: ParsedSetCookie = {
    name: nameValuePair.slice(0, equalsIndex),
    value: nameValuePair.slice(equalsIndex + 1),
    options: {},
  };

  attributePairs.forEach((attribute) => {
    const [rawName, ...rawValueParts] = attribute.split("=");
    const attributeName = rawName.trim().toLowerCase();
    const attributeValue = rawValueParts.join("=").trim();

    if (attributeName === "path" && attributeValue) {
      parsedCookie.options.path = attributeValue;
    } else if (attributeName === "max-age" && attributeValue) {
      const maxAge = Number(attributeValue);
      if (Number.isFinite(maxAge)) {
        parsedCookie.options.maxAge = maxAge;
      }
    } else if (attributeName === "expires" && attributeValue) {
      const expires = new Date(attributeValue);
      if (!Number.isNaN(expires.valueOf())) {
        parsedCookie.options.expires = expires;
      }
    } else if (attributeName === "httponly") {
      parsedCookie.options.httpOnly = true;
    } else if (attributeName === "secure") {
      parsedCookie.options.secure = true;
    } else if (attributeName === "samesite" && attributeValue) {
      const sameSite = parseSameSite(attributeValue);
      if (sameSite) {
        parsedCookie.options.sameSite = sameSite;
      }
    }
  });

  return parsedCookie;
}

function applySetCookiesToCookieHeader(cookieHeader: string, setCookieHeaders: string[]) {
  const cookiesByName = parseCookieHeader(cookieHeader);
  const now = Date.now();

  setCookieHeaders
    .map(parseSetCookieHeader)
    .filter((cookie): cookie is ParsedSetCookie => Boolean(cookie))
    .forEach((cookie) => {
      const isExpiredByMaxAge = cookie.options.maxAge !== undefined && cookie.options.maxAge <= 0;
      const isExpiredByDate = cookie.options.expires !== undefined && cookie.options.expires.valueOf() <= now;
      if (isExpiredByMaxAge || isExpiredByDate) {
        cookiesByName.delete(cookie.name);
        return;
      }
      cookiesByName.set(cookie.name, cookie.value);
    });

  return Array.from(cookiesByName.entries())
    .map(([name, value]) => `${name}=${value}`)
    .join("; ");
}

async function commitBackendCookies(setCookieHeaders: string[]) {
  if (setCookieHeaders.length === 0) {
    return;
  }

  try {
    const cookieStore = await cookies();
    setCookieHeaders
      .map(parseSetCookieHeader)
      .filter((cookie): cookie is ParsedSetCookie => Boolean(cookie))
      .forEach((cookie) => {
        cookieStore.set(cookie.name, cookie.value, cookie.options);
      });
  } catch {
    // Server components can read cookies but cannot always mutate the outgoing response.
  }
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

  if (isUnsafeMethod(init.method) && cookieHeader && !headers.has("Origin")) {
    headers.set("Origin", getFrontendAppUrl());
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

export function withBackendCookies(
  target: NextResponse,
  source: Response | string[] | string | null | undefined,
): NextResponse {
  const setCookieHeaders = getBackendSetCookieHeaders(source);

  setCookieHeaders.forEach((setCookie) => {
    target.headers.append("set-cookie", setCookie);
  });

  return target;
}

export function jsonWithBackendCookies<T>(
  payload: T,
  init?: ResponseInit,
  cookieHeaders?: Response | string[] | string | null,
): NextResponse {
  return withBackendCookies(NextResponse.json(payload, init), cookieHeaders);
}

export function applyBackendSetCookie(target: NextResponse, source: Response): NextResponse {
  return withBackendCookies(target, source);
}

function responseWithBackendCookies(response: Response, setCookieHeaders: string[]) {
  if (setCookieHeaders.length === 0) {
    return response;
  }

  const responseSetCookieHeaders = getBackendSetCookieHeaders(response);
  const headers = new Headers(response.headers);
  headers.delete("set-cookie");
  Array.from(new Set([...setCookieHeaders, ...responseSetCookieHeaders])).forEach((setCookie) => {
    headers.append("set-cookie", setCookie);
  });

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

type RefreshBackendSessionResult =
  | {
      ok: true;
      accessToken: string;
      cookieHeader: string;
      setCookieHeaders: string[];
    }
  | {
      ok: false;
      response: Response;
      setCookieHeaders: string[];
    };

async function refreshBackendSession(cookieHeader: string): Promise<RefreshBackendSessionResult> {
  const headers = new Headers(cookieHeader ? { Cookie: cookieHeader } : {});
  if (cookieHeader) {
    headers.set("Origin", getFrontendAppUrl());
  }

  const response = await fetch(`${getApiBaseUrl()}/auth/refresh/`, {
    method: "POST",
    headers,
    cache: "no-store",
  });
  const setCookieHeaders = getBackendSetCookieHeaders(response);
  await commitBackendCookies(setCookieHeaders);

  if (!response.ok) {
    return {
      ok: false,
      response,
      setCookieHeaders,
    };
  }

  const data = (await response.json().catch(() => ({}))) as Record<string, unknown>;
  const accessToken = typeof data.access === "string"
    ? data.access
    : getCookieValue(applySetCookiesToCookieHeader(cookieHeader, setCookieHeaders), getAccessCookieName());

  if (!accessToken) {
    return {
      ok: false,
      response: responseWithBackendCookies(
        NextResponse.json({ detail: "Authentication required." }, { status: 401 }),
        setCookieHeaders,
      ),
      setCookieHeaders,
    };
  }

  return {
    ok: true,
    accessToken,
    cookieHeader: applySetCookiesToCookieHeader(cookieHeader, setCookieHeaders),
    setCookieHeaders,
  };
}

export async function fetchBackendAuthorizedResponse(path: string, init: ServerApiRequestInit = {}): Promise<Response> {
  const initialCookieHeader = await resolveCookieHeader(init.cookieHeader);
  let cookieHeader = initialCookieHeader;
  let accessToken = getCookieValue(cookieHeader, getAccessCookieName());
  let setCookieHeaders: string[] = [];
  let refreshedBeforeRequest = false;

  if (!accessToken) {
    const refreshedSession = await refreshBackendSession(cookieHeader);
    if (!refreshedSession.ok) {
      return refreshedSession.response;
    }
    accessToken = refreshedSession.accessToken;
    cookieHeader = refreshedSession.cookieHeader;
    setCookieHeaders = refreshedSession.setCookieHeaders;
    refreshedBeforeRequest = true;
  }

  const headers = buildBackendHeaders(init, cookieHeader);
  headers.set("Authorization", `Bearer ${accessToken}`);

  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });

  if (response.status !== 401 || refreshedBeforeRequest) {
    return responseWithBackendCookies(response, setCookieHeaders);
  }

  const refreshedSession = await refreshBackendSession(initialCookieHeader);
  if (!refreshedSession.ok) {
    return responseWithBackendCookies(refreshedSession.response, setCookieHeaders);
  }

  const retryHeaders = buildBackendHeaders(init, refreshedSession.cookieHeader);
  retryHeaders.set("Authorization", `Bearer ${refreshedSession.accessToken}`);

  const retryResponse = await fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    headers: retryHeaders,
    cache: "no-store",
  });

  return responseWithBackendCookies(retryResponse, refreshedSession.setCookieHeaders);
}

export async function fetchBackendJson<T>(path: string, init: ServerApiRequestInit = {}): Promise<T> {
  const response = await fetchBackendAuthorizedResponse(path, init);
  await commitBackendCookies(getBackendSetCookieHeaders(response));

  if (!response.ok) {
    let detail = "Unable to load server-side dashboard data.";
    let payload: Record<string, unknown> | undefined;

    try {
      const data = (await response.json()) as Record<string, unknown>;
      detail = typeof data.detail === "string" ? data.detail : formatBackendErrorDetail(data);
      payload = {
        ...data,
        detail,
      };
    } catch {
      // Keep generic detail if parsing fails.
    }

    throw new ServerApiError(response.status, detail, payload);
  }

  if (response.status === 204 || response.status === 205) {
    return undefined as T;
  }

  return (await response.json()) as T;
}
