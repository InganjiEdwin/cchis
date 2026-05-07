import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockRedirect = vi.fn();
const mockFetchServerSession = vi.fn();

vi.mock("next/navigation", () => ({
  redirect: (...args: unknown[]) => {
    mockRedirect(...args);
    throw new Error("NEXT_REDIRECT");
  },
}));

vi.mock("next/headers", () => ({
  headers: async () => new Headers({ "x-cchis-current-path": "/wards/12?tab=actions" }),
}));

vi.mock("@/lib/server-session", () => ({
  fetchServerSession: () => mockFetchServerSession(),
}));

vi.mock("@/components/protected-shell", () => ({
  ProtectedShell: ({ children }: { children: React.ReactNode }) => React.createElement("div", null, children),
}));

describe("DashboardLayout", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("redirects to login when the server cannot resolve a session", async () => {
    mockFetchServerSession.mockResolvedValue(null);

    const { default: DashboardLayout } = await import("@/app/(dashboard)/layout");

    await expect(DashboardLayout({ children: React.createElement("div", null, "Body") })).rejects.toThrow(
      "NEXT_REDIRECT",
    );

    expect(mockRedirect).toHaveBeenCalledWith("/login");
  });

  it("redirects policy-missing dashboard users before rendering dashboard children", async () => {
    mockFetchServerSession.mockResolvedValue({
      authenticated: true,
      access: null,
      session_source: "refresh",
      user: {
        id: 1,
        username: "analyst",
        email: "analyst@example.com",
        full_name: "Analyst",
        phone_number: null,
        role: "ANALYST",
        theme_preference: "SYSTEM",
        ward: null,
        ward_name: null,
        is_active: true,
        policy_acceptance: {
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
        },
      },
    });

    const { default: DashboardLayout } = await import("@/app/(dashboard)/layout");

    await expect(DashboardLayout({ children: React.createElement("div", null, "Body") })).rejects.toThrow(
      "NEXT_REDIRECT",
    );

    expect(mockRedirect).toHaveBeenCalledWith("/policy-review?returnTo=%2Fwards%2F12%3Ftab%3Dactions");
  });
});
