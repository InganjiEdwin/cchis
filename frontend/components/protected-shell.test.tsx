import React from "react";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ProtectedShell } from "@/components/protected-shell";

const mockReplace = vi.fn();
const mockUseAuth = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: mockReplace,
  }),
}));

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) =>
    React.createElement("a", { href, ...props }, children),
}));

vi.mock("@/components/auth-provider", () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock("@/components/dashboard-sidebar", () => ({
  DashboardSidebar: () => React.createElement("div", null, "Sidebar mock"),
}));

vi.mock("@/components/dashboard-footer", () => ({
  DashboardFooter: () => React.createElement("div", null, "Footer mock"),
}));

describe("ProtectedShell", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.sessionStorage.clear();
  });

  it("shows the restoring state only while hydrating", () => {
    mockUseAuth.mockReturnValue({
      currentUser: null,
      isAuthenticated: false,
      isHydrating: true,
    });

    render(React.createElement(ProtectedShell, null, React.createElement("div", null, "Body")));

    expect(screen.getByText("Restoring your session")).toBeInTheDocument();
  });

  it("does not keep showing the restoring state after hydration when redirecting to login", () => {
    mockUseAuth.mockReturnValue({
      currentUser: null,
      isAuthenticated: false,
      isHydrating: false,
    });

    const { container } = render(
      React.createElement(ProtectedShell, null, React.createElement("div", null, "Body")),
    );

    expect(screen.queryByText("Restoring your session")).not.toBeInTheDocument();
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the dashboard shell for an authorized dashboard user", () => {
    mockUseAuth.mockReturnValue({
      currentUser: {
        id: 1,
        username: "admin",
        email: "admin@example.com",
        full_name: "Admin User",
        phone_number: null,
        role: "ADMIN",
        theme_preference: "LIGHT",
        ward: null,
        ward_name: null,
        is_active: true,
      },
      isAuthenticated: true,
      isHydrating: false,
    });

    render(React.createElement(ProtectedShell, null, React.createElement("div", null, "Body")));

    expect(screen.getByText("Sidebar mock")).toBeInTheDocument();
    expect(screen.getByText("Footer mock")).toBeInTheDocument();
    expect(screen.getByText("Body")).toBeInTheDocument();
  });

  it("shows a one-time dashboard notice after recovery-code login leaves few codes", () => {
    window.sessionStorage.setItem(
      "cchis.recovery_code_login_notice",
      JSON.stringify({ remaining_count: 1, created_at: "2026-05-02T10:00:00Z" }),
    );
    mockUseAuth.mockReturnValue({
      currentUser: {
        id: 1,
        username: "admin",
        email: "admin@example.com",
        full_name: "Admin User",
        phone_number: null,
        role: "ADMIN",
        theme_preference: "LIGHT",
        ward: null,
        ward_name: null,
        is_active: true,
      },
      isAuthenticated: true,
      isHydrating: false,
    });

    render(React.createElement(ProtectedShell, null, React.createElement("div", null, "Body")));

    expect(screen.getByText("Recovery codes are running low.")).toBeInTheDocument();
    expect(screen.getByText("1 recovery code remains. Generate a fresh set from Profile.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Manage codes" })).toHaveAttribute("href", "/profile");
    expect(window.sessionStorage.getItem("cchis.recovery_code_login_notice")).toBeNull();
  });
});
