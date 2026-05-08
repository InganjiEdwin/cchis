import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RoleGate } from "@/components/role-gate";
import { buildUserWithoutPageCapability } from "@/test/dashboard-user";

const mockUseAuth = vi.fn();

vi.mock("@/components/auth-provider", () => ({
  useAuth: () => mockUseAuth(),
}));

describe("RoleGate", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("does not let deprecated role fallbacks override explicit capability gates", () => {
    mockUseAuth.mockReturnValue({
      currentUser: buildUserWithoutPageCapability("ADMIN", "system"),
    });

    render(
      <RoleGate
        pageCapability="system"
        allowedRoles={["ADMIN"]}
        title="No access"
        message="System access is disabled."
      >
        <p>System controls</p>
      </RoleGate>,
    );

    expect(screen.queryByText("System controls")).not.toBeInTheDocument();
    expect(screen.getByText("No access")).toBeInTheDocument();
  });
});
