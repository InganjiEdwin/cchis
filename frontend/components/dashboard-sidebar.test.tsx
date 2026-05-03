import React from "react";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DashboardSidebar } from "@/components/dashboard-sidebar";
import type { CurrentUser } from "@/lib/auth";

const mockUseAuth = vi.fn();
const mockReplace = vi.fn();

vi.mock("next/image", () => ({
  default: ({ alt, ...props }: React.ImgHTMLAttributes<HTMLImageElement>) =>
    React.createElement("img", { alt, ...props }),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/profile",
  useRouter: () => ({
    replace: mockReplace,
  }),
}));

vi.mock("@/components/auth-provider", () => ({
  useAuth: () => mockUseAuth(),
}));

function buildUser(overrides: Partial<CurrentUser> = {}): CurrentUser {
  return {
    id: 1,
    username: "admin",
    email: "admin@example.com",
    full_name: "Edwin Inganji",
    phone_number: "+254711000001",
    role: "ADMIN",
    theme_preference: "SYSTEM",
    ward: 1,
    ward_name: "North Kamagambo",
    scope_type: "BROAD",
    scope_ward_id: null,
    two_factor_policy: "REQUIRED",
    is_totp_enabled: true,
    is_active: true,
    ...overrides,
  };
}

describe("DashboardSidebar", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({
      currentUser: buildUser(),
      logout: vi.fn().mockResolvedValue(undefined),
    });
  });

  it("shows county scope for broad admin accounts even when a ward name is present", () => {
    render(<DashboardSidebar />);

    expect(screen.getByLabelText("Open profile summary")).toHaveTextContent("Migori County");
    expect(screen.getByLabelText("Open profile summary")).not.toHaveTextContent("North Kamagambo");
  });

  it("shows the ward only for ward-scoped accounts", () => {
    mockUseAuth.mockReturnValue({
      currentUser: buildUser({
        role: "SUPERVISOR",
        scope_type: "WARD",
        scope_ward_id: 1,
      }),
      logout: vi.fn().mockResolvedValue(undefined),
    });

    render(<DashboardSidebar />);

    expect(screen.getByLabelText("Open profile summary")).toHaveTextContent("North Kamagambo");
  });
});
