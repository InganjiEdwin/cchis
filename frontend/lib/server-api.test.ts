import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  cookies: vi.fn(),
  getApiBaseUrl: vi.fn(() => "http://backend.test/api/v1"),
}));

vi.mock("server-only", () => ({}));
vi.mock("next/headers", () => ({
  cookies: mocks.cookies,
}));
vi.mock("@/lib/auth", () => ({
  getApiBaseUrl: mocks.getApiBaseUrl,
}));

import {
  fetchBackendAuthorizedResponse,
  getBackendSetCookieHeaders,
  jsonWithBackendCookies,
} from "@/lib/server-api";

function jsonResponse(payload: unknown, status = 200, setCookies: string[] = []) {
  const headers = new Headers({ "content-type": "application/json" });
  setCookies.forEach((setCookie) => headers.append("set-cookie", setCookie));
  return new Response(JSON.stringify(payload), { status, headers });
}

describe("server-api auth cookie handling", () => {
  const cookieSet = vi.fn();
  const originalFetch = global.fetch;
  const originalAccessCookieName = process.env.AUTH_ACCESS_COOKIE_NAME;
  const originalFrontendAppUrl = process.env.FRONTEND_APP_URL;

  beforeEach(() => {
    vi.clearAllMocks();
    cookieSet.mockClear();
    mocks.cookies.mockResolvedValue({
      toString: () => "cchis_access=old-access; cchis_refresh=old-refresh",
      set: cookieSet,
    });
    process.env.AUTH_ACCESS_COOKIE_NAME = "cchis_access";
    process.env.FRONTEND_APP_URL = "http://localhost:3000";
    global.fetch = vi.fn() as typeof fetch;
  });

  afterEach(() => {
    global.fetch = originalFetch;
    if (originalAccessCookieName === undefined) {
      delete process.env.AUTH_ACCESS_COOKIE_NAME;
    } else {
      process.env.AUTH_ACCESS_COOKIE_NAME = originalAccessCookieName;
    }
    if (originalFrontendAppUrl === undefined) {
      delete process.env.FRONTEND_APP_URL;
    } else {
      process.env.FRONTEND_APP_URL = originalFrontendAppUrl;
    }
  });

  it("splits combined backend Set-Cookie values without breaking Expires dates", () => {
    const setCookies = getBackendSetCookieHeaders(
      "cchis_access=abc; Expires=Thu, 01 Jan 2026 00:00:00 GMT; Path=/; HttpOnly, cchis_refresh=def; Path=/; HttpOnly",
    );

    expect(setCookies).toHaveLength(2);
    expect(setCookies[0]).toContain("cchis_access=abc");
    expect(setCookies[1]).toContain("cchis_refresh=def");
  });

  it("refreshes once on an expired access cookie and propagates rotated cookies", async () => {
    const fetchMock = vi.mocked(global.fetch);
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ detail: "Token is invalid or expired" }, 401))
      .mockResolvedValueOnce(
        jsonResponse(
          { access: "new-access", refresh: "new-refresh" },
          200,
          [
            "cchis_access=new-access; Max-Age=900; Path=/; HttpOnly; SameSite=Lax",
            "cchis_refresh=new-refresh; Max-Age=604800; Path=/; HttpOnly; SameSite=Lax",
          ],
        ),
      )
      .mockResolvedValueOnce(jsonResponse({ ok: true }));

    const response = await fetchBackendAuthorizedResponse("/wards/", {
      cookieHeader: "cchis_access=old-access; cchis_refresh=old-refresh",
    });

    expect(await response.json()).toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[0][0]).toBe("http://backend.test/api/v1/wards/");
    expect(fetchMock.mock.calls[1][0]).toBe("http://backend.test/api/v1/auth/refresh/");
    expect(fetchMock.mock.calls[2][0]).toBe("http://backend.test/api/v1/wards/");

    const retryHeaders = fetchMock.mock.calls[2][1]?.headers as Headers;
    expect(retryHeaders.get("Authorization")).toBe("Bearer new-access");
    expect(retryHeaders.get("Cookie")).toContain("cchis_access=new-access");
    expect(retryHeaders.get("Cookie")).toContain("cchis_refresh=new-refresh");
    const refreshHeaders = fetchMock.mock.calls[1][1]?.headers as Headers;
    expect(refreshHeaders.get("Origin")).toBe("http://localhost:3000");
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/auth/session/"))).toBe(false);

    const responseCookies = getBackendSetCookieHeaders(response);
    expect(responseCookies).toHaveLength(2);
    expect(responseCookies[0]).toContain("cchis_access=new-access");
    expect(responseCookies[1]).toContain("cchis_refresh=new-refresh");
    expect(cookieSet).toHaveBeenCalledWith(
      "cchis_access",
      "new-access",
      expect.objectContaining({ httpOnly: true, maxAge: 900, path: "/", sameSite: "lax" }),
    );
  });

  it("uses the refreshed access cookie when the backend omits token bodies", async () => {
    const fetchMock = vi.mocked(global.fetch);
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ detail: "Token is invalid or expired" }, 401))
      .mockResolvedValueOnce(
        jsonResponse(
          { session_established: true },
          200,
          [
            "cchis_access=cookie-only-access; Max-Age=900; Path=/; HttpOnly; SameSite=Lax",
            "cchis_refresh=cookie-only-refresh; Max-Age=604800; Path=/; HttpOnly; SameSite=Lax",
          ],
        ),
      )
      .mockResolvedValueOnce(jsonResponse({ ok: true }));

    const response = await fetchBackendAuthorizedResponse("/wards/", {
      cookieHeader: "cchis_access=old-access; cchis_refresh=old-refresh",
    });

    expect(await response.json()).toEqual({ ok: true });
    const retryHeaders = fetchMock.mock.calls[2][1]?.headers as Headers;
    expect(retryHeaders.get("Authorization")).toBe("Bearer cookie-only-access");
    expect(retryHeaders.get("Cookie")).toContain("cchis_access=cookie-only-access");
    expect(getBackendSetCookieHeaders(response)[0]).toContain("cchis_access=cookie-only-access");
  });

  it("returns clear session-expiry details when refresh fails before retry", async () => {
    const fetchMock = vi.mocked(global.fetch);
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ detail: "Token is invalid or expired" }, 401))
      .mockResolvedValueOnce(
        jsonResponse(
          {
            detail: "Your session expired after a period of inactivity. Please sign in again.",
            code: "session_idle_timeout",
          },
          401,
          [
            "cchis_access=; Max-Age=0; Path=/; HttpOnly; SameSite=Lax",
            "cchis_refresh=; Max-Age=0; Path=/; HttpOnly; SameSite=Lax",
          ],
        ),
      );

    const response = await fetchBackendAuthorizedResponse("/wards/", {
      cookieHeader: "cchis_access=old-access; cchis_refresh=old-refresh",
    });

    expect(response.status).toBe(401);
    expect(await response.json()).toEqual({
      detail: "Your session expired after a period of inactivity. Please sign in again.",
      code: "session_idle_timeout",
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const responseCookies = getBackendSetCookieHeaders(response);
    expect(responseCookies).toHaveLength(2);
    expect(responseCookies[0]).toContain("cchis_access=;");
    expect(responseCookies[1]).toContain("cchis_refresh=;");
  });

  it("adds a trusted origin to unsafe backend writes with auth cookies", async () => {
    const fetchMock = vi.mocked(global.fetch);
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "Logged out." }));

    await fetchBackendAuthorizedResponse("/auth/logout/", {
      method: "POST",
      cookieHeader: "cchis_access=old-access; cchis_refresh=old-refresh",
    });

    const headers = fetchMock.mock.calls[0][1]?.headers as Headers;
    expect(headers.get("Origin")).toBe("http://localhost:3000");
    expect(headers.get("Authorization")).toBe("Bearer old-access");
  });

  it("adds backend cookies to JSON BFF responses", () => {
    const response = jsonWithBackendCookies(
      { ok: true },
      { status: 202 },
      ["cchis_access=new-access; Path=/; HttpOnly"],
    );

    expect(response.status).toBe(202);
    expect(response.headers.get("set-cookie")).toContain("cchis_access=new-access");
  });
});
