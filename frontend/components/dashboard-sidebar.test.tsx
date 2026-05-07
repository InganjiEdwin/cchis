import React from "react";
import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DashboardSidebar } from "@/components/dashboard-sidebar";
import type { CurrentUser } from "@/lib/auth";

const mockUseAuth = vi.fn();
const mockReplace = vi.fn();
const mockPathname = vi.fn();

vi.mock("next/image", () => ({
  default: ({ alt, ...props }: React.ImgHTMLAttributes<HTMLImageElement>) =>
    React.createElement("img", { alt, ...props }),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => mockPathname(),
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
    mockPathname.mockReturnValue("/profile");
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

  it("pins account actions at the foot while the navigation owns the scroll area", () => {
    render(<DashboardSidebar />);

    const navScrollRegion = screen.getByRole("navigation", { name: "Primary navigation" }).parentElement as HTMLElement;
    const accountFooter = screen.getByLabelText("Open profile summary").parentElement as HTMLElement;

    expect(navScrollRegion).toHaveClass("overflow-y-auto");
    expect(navScrollRegion).toHaveClass("pb-44");
    expect(accountFooter).toHaveClass("sticky");
    expect(accountFooter).toHaveClass("bottom-0");
    expect(accountFooter).toHaveClass("row-start-2");
    expect(accountFooter).toHaveClass("self-end");
  });

  it("groups the sidebar around operator work before technical administration", () => {
    render(<DashboardSidebar />);

    const nav = screen.getByRole("navigation", { name: "Primary navigation" });

    expect(within(nav).getByRole("heading", { name: "Operate" })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Overview" })).toHaveAttribute("href", "/overview");
    expect(within(nav).getByRole("link", { name: "Ward Decisions" })).toHaveAttribute("href", "/wards");
    expect(within(nav).getByRole("link", { name: "Response Tasks" })).toHaveAttribute("href", "/preparedness-actions");
    expect(within(nav).getByRole("heading", { name: "Response Capacity" })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Metrics" })).toHaveAttribute("href", "/operational-metrics");
    expect(within(nav).getByText("Data & Admin")).toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: "Profile" })).not.toBeInTheDocument();
  });

  it("opens the technical group when a technical route is active", () => {
    mockPathname.mockReturnValue("/source-data");

    render(<DashboardSidebar />);

    const dataAdminGroup = screen.getByText("Data & Admin").closest("details");

    expect(dataAdminGroup).toHaveAttribute("open");
    expect(screen.getByRole("link", { name: "Data Readiness" })).toHaveClass("text-[var(--dashboard-sidebar-title)]");
  });

  it("compacts the navigation into a short horizontal rail on narrow screens", () => {
    render(<DashboardSidebar />);

    const nav = screen.getByRole("navigation", { name: "Primary navigation" });
    const navScrollRegion = nav.parentElement as HTMLElement;
    const accountFooter = screen.getByLabelText("Open profile summary").parentElement as HTMLElement;

    expect(navScrollRegion).toHaveClass("max-[960px]:w-full");
    expect(navScrollRegion).toHaveClass("max-[960px]:min-w-0");
    expect(navScrollRegion).toHaveClass("max-[960px]:overflow-x-auto");
    expect(navScrollRegion).toHaveClass("max-[960px]:overflow-y-hidden");
    expect(nav).toHaveClass("max-[960px]:flex");
    expect(accountFooter).toHaveClass("max-[960px]:hidden");
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
