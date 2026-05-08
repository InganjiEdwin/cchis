import { readFileSync } from "node:fs";

import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { buildDashboardUser } from "@/test/dashboard-user";

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
  fetchServerSession: (...args: unknown[]) => mockFetchServerSession(...args),
}));

vi.mock("@/components/protected-shell", () => ({
  ProtectedShell: ({ children }: { children: React.ReactNode }) => React.createElement("div", null, children),
}));

describe("DashboardLayout", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("lets the client restore the session when server rendering has no access cookie", async () => {
    mockFetchServerSession.mockResolvedValue(null);

    const { default: DashboardLayout } = await import("@/app/(dashboard)/layout");

    const result = await DashboardLayout({ children: React.createElement("div", null, "Body") });

    expect(result).toBeTruthy();
    expect(mockFetchServerSession).toHaveBeenCalledWith({ allowRefreshBootstrap: false });
    expect(mockRedirect).not.toHaveBeenCalled();
  });

  it("redirects policy-missing dashboard users before rendering dashboard children", async () => {
    mockFetchServerSession.mockResolvedValue({
      authenticated: true,
      access: null,
      session_source: "refresh",
      user: buildDashboardUser("ANALYST", {
        username: "analyst",
        email: "analyst@example.com",
        full_name: "Analyst",
        theme_preference: "SYSTEM",
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
      }),
    });

    const { default: DashboardLayout } = await import("@/app/(dashboard)/layout");

    await expect(DashboardLayout({ children: React.createElement("div", null, "Body") })).rejects.toThrow(
      "NEXT_REDIRECT",
    );

    expect(mockRedirect).toHaveBeenCalledWith("/policy-review?returnTo=%2Fwards%2F12%3Ftab%3Dactions");
  });

  it("redirects CHV users away from the dashboard shell", async () => {
    mockFetchServerSession.mockResolvedValue({
      authenticated: true,
      access: null,
      session_source: "refresh",
      user: buildDashboardUser("CHV"),
    });

    const { default: DashboardLayout } = await import("@/app/(dashboard)/layout");

    await expect(DashboardLayout({ children: React.createElement("div", null, "Body") })).rejects.toThrow(
      "NEXT_REDIRECT",
    );

    expect(mockRedirect).toHaveBeenCalledWith("/unauthorized");
  });

  it("keeps dashboard page authorization display free of browser role storage", () => {
    const dashboardPageFiles = [
      "./(dashboard)/layout.tsx",
      "./(dashboard)/alerts/page.tsx",
      "./(dashboard)/wards/[id]/page.tsx",
      "./(dashboard)/preparedness-actions/page.tsx",
      "./(dashboard)/chvs/page.tsx",
      "./(dashboard)/facility-readiness/page.tsx",
      "./(dashboard)/source-data/page.tsx",
      "./(dashboard)/message-governance/page.tsx",
      "./(dashboard)/system/page.tsx",
    ];

    for (const file of dashboardPageFiles) {
      const source = readFileSync(new URL(file, import.meta.url), "utf8");
      expect(source, file).not.toMatch(/(?:localStorage|sessionStorage)/);
    }
  });
});
