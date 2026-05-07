import { describe, expect, it, vi } from "vitest";

const { mockFetchBackendAuthorizedResponse } = vi.hoisted(() => ({
  mockFetchBackendAuthorizedResponse: vi.fn(),
}));

vi.mock("@/lib/server-api", () => ({
  ServerApiError: class ServerApiError extends Error {
    status: number;

    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
  applyBackendSetCookie: (target: Response, source: Response) => {
    const setCookie = source.headers.get("set-cookie");
    if (setCookie) {
      target.headers.set("set-cookie", setCookie);
    }
    return target;
  },
  fetchBackendAuthorizedResponse: (...args: unknown[]) => mockFetchBackendAuthorizedResponse(...args),
}));

import { GET, POST } from "@/app/api/session/policy-acceptance/route";

const policyState = {
  required: true,
  is_current: false,
  terms_version: "terms-2026-05",
  privacy_version: "privacy-2026-05",
  cookie_notice_version: "cookies-2026-05",
  accepted_terms_version: null,
  accepted_privacy_version: null,
  accepted_cookie_notice_version: null,
  missing_documents: ["TERMS", "PRIVACY", "COOKIE_NOTICE"],
  terms_url: "/terms",
  privacy_url: "/privacy",
  cookie_notice_url: "/privacy#cookies",
};

describe("policy acceptance session route", () => {
  it("forwards GET requests to the authenticated backend endpoint", async () => {
    mockFetchBackendAuthorizedResponse.mockResolvedValueOnce(
      new Response(JSON.stringify(policyState), {
        status: 200,
        headers: {
          "set-cookie": "cchis_refresh=rotated; Path=/; HttpOnly",
        },
      }),
    );

    const response = await GET(
      new Request("http://localhost/api/session/policy-acceptance", {
        headers: {
          cookie: "cchis_refresh=abc",
        },
      }),
    );

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual(policyState);
    expect(response.headers.get("set-cookie")).toContain("cchis_refresh=rotated");
    expect(mockFetchBackendAuthorizedResponse).toHaveBeenCalledWith("/auth/policy-acceptance/", {
      method: "GET",
      cookieHeader: "cchis_refresh=abc",
    });
  });

  it("forwards POST payloads and preserves backend validation responses", async () => {
    const payload = {
      accepted_terms: true,
      accepted_privacy: true,
      accepted_cookie_notice: true,
      terms_version: "terms-2026-04",
      privacy_version: "privacy-2026-05",
      cookie_notice_version: "cookies-2026-05",
    };
    const backendError = {
      terms_version: "This policy version is no longer current. Refresh and review the latest version.",
    };

    mockFetchBackendAuthorizedResponse.mockResolvedValueOnce(
      new Response(JSON.stringify(backendError), { status: 400 }),
    );

    const request = new Request("http://localhost/api/session/policy-acceptance", {
      method: "POST",
      headers: {
        cookie: "cchis_refresh=abc",
      },
      body: JSON.stringify(payload),
    });
    const response = await POST(request);

    expect(response.status).toBe(400);
    expect(await response.json()).toEqual(backendError);
    expect(mockFetchBackendAuthorizedResponse).toHaveBeenCalledWith("/auth/policy-acceptance/", {
      method: "POST",
      body: JSON.stringify(payload),
      cookieHeader: "cchis_refresh=abc",
    });
  });
});
