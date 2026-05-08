import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  buildContentSecurityPolicy,
  CSRF_REJECTION_CODE,
  shouldApplyProductionCsp,
  validateBffUnsafeRequest,
} from "@/lib/request-security";

describe("BFF request security", () => {
  const originalFrontendAppUrl = process.env.FRONTEND_APP_URL;
  const originalApiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
  const originalCchisEnvironment = process.env.CCHIS_ENVIRONMENT;
  const originalNextPublicCchisEnvironment = process.env.NEXT_PUBLIC_CCHIS_ENVIRONMENT;
  const originalCspEnabled = process.env.CCHIS_CSP_ENABLED;

  beforeEach(() => {
    process.env.FRONTEND_APP_URL = "http://localhost:3000";
    process.env.NEXT_PUBLIC_API_BASE_URL = "https://api.cchis.example/api/v1";
    process.env.NEXT_PUBLIC_CCHIS_ENVIRONMENT = "local";
    delete process.env.CCHIS_ENVIRONMENT;
    delete process.env.CCHIS_CSP_ENABLED;
  });

  afterEach(() => {
    if (originalFrontendAppUrl === undefined) {
      delete process.env.FRONTEND_APP_URL;
    } else {
      process.env.FRONTEND_APP_URL = originalFrontendAppUrl;
    }
    if (originalApiBaseUrl === undefined) {
      delete process.env.NEXT_PUBLIC_API_BASE_URL;
    } else {
      process.env.NEXT_PUBLIC_API_BASE_URL = originalApiBaseUrl;
    }
    if (originalCchisEnvironment === undefined) {
      delete process.env.CCHIS_ENVIRONMENT;
    } else {
      process.env.CCHIS_ENVIRONMENT = originalCchisEnvironment;
    }
    if (originalNextPublicCchisEnvironment === undefined) {
      delete process.env.NEXT_PUBLIC_CCHIS_ENVIRONMENT;
    } else {
      process.env.NEXT_PUBLIC_CCHIS_ENVIRONMENT = originalNextPublicCchisEnvironment;
    }
    if (originalCspEnabled === undefined) {
      delete process.env.CCHIS_CSP_ENABLED;
    } else {
      process.env.CCHIS_CSP_ENABLED = originalCspEnabled;
    }
  });

  it("rejects cross-site unsafe API requests", () => {
    const error = validateBffUnsafeRequest({
      method: "POST",
      pathname: "/api/session/logout",
      headers: new Headers({
        origin: "https://evil.example",
        "sec-fetch-site": "cross-site",
      }),
      requestOrigin: "http://localhost:3000",
    });

    expect(error).toEqual({
      detail: "Cross-site requests are not allowed for this action.",
      code: CSRF_REJECTION_CODE,
    });
  });

  it("requires an origin or referer for unsafe API requests", () => {
    const error = validateBffUnsafeRequest({
      method: "DELETE",
      pathname: "/api/session/sessions/session-1/revoke",
      headers: new Headers(),
      requestOrigin: "http://localhost:3000",
    });

    expect(error?.code).toBe(CSRF_REJECTION_CODE);
  });

  it("allows same-origin unsafe API requests", () => {
    const error = validateBffUnsafeRequest({
      method: "POST",
      pathname: "/api/session/logout",
      headers: new Headers({
        origin: "http://localhost:3000",
        "sec-fetch-site": "same-origin",
      }),
      requestOrigin: "http://localhost:3000",
    });

    expect(error).toBeNull();
  });

  it("emits production CSP with backend and websocket connect sources", () => {
    process.env.CCHIS_ENVIRONMENT = "staging";

    expect(shouldApplyProductionCsp()).toBe(true);
    expect(buildContentSecurityPolicy()).toContain("default-src 'self'");
    expect(buildContentSecurityPolicy()).toContain("frame-ancestors 'none'");
    expect(buildContentSecurityPolicy()).toContain(
      "connect-src 'self' https://api.cchis.example wss://api.cchis.example",
    );
  });

  it("uses a script nonce when one is provided for Next hydration", () => {
    process.env.CCHIS_ENVIRONMENT = "production";

    const policy = buildContentSecurityPolicy("abc123");

    expect(policy).toContain("script-src 'self' 'nonce-abc123'");
    expect(policy).not.toContain("script-src 'self' 'unsafe-inline'");
    expect(policy).toContain("upgrade-insecure-requests");
  });
});
