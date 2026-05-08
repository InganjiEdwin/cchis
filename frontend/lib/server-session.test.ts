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

import { fetchServerSessionResult } from "@/lib/server-session";

function jsonResponse(payload: unknown, status = 200, setCookies: string[] = []) {
  const headers = new Headers({ "content-type": "application/json" });
  setCookies.forEach((setCookie) => headers.append("set-cookie", setCookie));
  return new Response(JSON.stringify(payload), { status, headers });
}

describe("server session bootstrap", () => {
  const originalFetch = global.fetch;
  const originalAccessCookieName = process.env.AUTH_ACCESS_COOKIE_NAME;

  beforeEach(() => {
    vi.clearAllMocks();
    process.env.AUTH_ACCESS_COOKIE_NAME = "cchis_access";
    global.fetch = vi.fn() as typeof fetch;
  });

  afterEach(() => {
    global.fetch = originalFetch;
    if (originalAccessCookieName === undefined) {
      delete process.env.AUTH_ACCESS_COOKIE_NAME;
    } else {
      process.env.AUTH_ACCESS_COOKIE_NAME = originalAccessCookieName;
    }
  });

  it("does not spend refresh cookies during access-only server rendering", async () => {
    mocks.cookies.mockResolvedValue({
      toString: () => "cchis_refresh=refresh-token",
      get: () => undefined,
    });

    const result = await fetchServerSessionResult({ allowRefreshBootstrap: false });

    expect(result).toEqual({ session: null, cookieHeaders: [] });
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it("sends only the access cookie during access-only server rendering", async () => {
    mocks.cookies.mockResolvedValue({
      toString: () => "cchis_access=access-token; cchis_refresh=refresh-token",
      get: (name: string) => (
        name === "cchis_access" ? { name: "cchis_access", value: "access-token" } : undefined
      ),
    });
    vi.mocked(global.fetch).mockResolvedValueOnce(
      jsonResponse({
        authenticated: true,
        user: { id: 1, username: "admin" },
        access: null,
        session_source: "access",
      }),
    );

    const result = await fetchServerSessionResult({ allowRefreshBootstrap: false });

    expect(result.session?.authenticated).toBe(true);
    const headers = vi.mocked(global.fetch).mock.calls[0][1]?.headers as Record<string, string>;
    expect(headers.Cookie).toBe("cchis_access=access-token");
    expect(headers.Cookie).not.toContain("cchis_refresh");
  });
});
