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
});
