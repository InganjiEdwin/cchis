import React from "react";
import { describe, expect, it, vi } from "vitest";

const mockRedirect = vi.fn();
const mockFetchServerSession = vi.fn();

vi.mock("next/navigation", () => ({
  redirect: (...args: unknown[]) => {
    mockRedirect(...args);
    throw new Error("NEXT_REDIRECT");
  },
}));

vi.mock("@/lib/server-session", () => ({
  fetchServerSession: () => mockFetchServerSession(),
}));

vi.mock("@/components/protected-shell", () => ({
  ProtectedShell: ({ children }: { children: React.ReactNode }) => React.createElement("div", null, children),
}));

describe("DashboardLayout", () => {
  it("redirects to login when the server cannot resolve a session", async () => {
    mockFetchServerSession.mockResolvedValue(null);

    const { default: DashboardLayout } = await import("@/app/(dashboard)/layout");

    await expect(DashboardLayout({ children: React.createElement("div", null, "Body") })).rejects.toThrow(
      "NEXT_REDIRECT",
    );

    expect(mockRedirect).toHaveBeenCalledWith("/login");
  });
});
