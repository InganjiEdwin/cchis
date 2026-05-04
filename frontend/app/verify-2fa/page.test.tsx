import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import VerifyTwoFactorPage from "@/app/verify-2fa/page";
import type { CurrentUser, VerifyTwoFactorResponse } from "@/lib/auth";

const mockClearPendingTwoFactor = vi.fn();
const mockGetDefaultRoute = vi.fn();
const mockReplace = vi.fn();
const mockRouter = { replace: mockReplace };
const mockUseAuth = vi.fn();
const mockVerifyTwoFactor = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => mockRouter,
}));

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) =>
    React.createElement("a", { href, ...props }, children),
}));

vi.mock("@/components/auth-provider", () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock("@/lib/navigation", () => ({
  getDefaultRoute: (...args: unknown[]) => mockGetDefaultRoute(...args),
}));

function buildUser(overrides: Partial<CurrentUser> = {}): CurrentUser {
  return {
    id: 1,
    username: "admin",
    email: "admin@example.com",
    full_name: "System Admin",
    phone_number: "+254700000001",
    role: "ADMIN",
    theme_preference: "SYSTEM",
    ward: null,
    ward_name: null,
    is_active: true,
    ...overrides,
  };
}

function buildVerifyResponse(overrides: Partial<VerifyTwoFactorResponse> = {}): VerifyTwoFactorResponse {
  return {
    user: buildUser(),
    requires_2fa: false,
    session_established: true,
    second_factor_method: "totp",
    ...overrides,
  };
}

function renderVerifyPage() {
  mockUseAuth.mockReturnValue({
    clearPendingTwoFactor: mockClearPendingTwoFactor,
    currentUser: null,
    isAuthenticated: false,
    isHydrating: false,
    pendingTwoFactor: { tempToken: "pending-token" },
    verifyTwoFactor: mockVerifyTwoFactor,
  });

  render(React.createElement(VerifyTwoFactorPage));
}

describe("VerifyTwoFactorPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.sessionStorage.clear();
    mockGetDefaultRoute.mockReturnValue("/overview");
    mockVerifyTwoFactor.mockResolvedValue(buildVerifyResponse());
  });

  it("keeps the fast authenticator flow by auto-submitting exactly six digits", async () => {
    const user = userEvent.setup();
    renderVerifyPage();

    await user.type(screen.getByLabelText("Authenticator or recovery code"), "123456");

    await waitFor(() => {
      expect(mockVerifyTwoFactor).toHaveBeenCalledWith("123456");
    });
    expect(mockGetDefaultRoute).toHaveBeenCalledWith("ADMIN");
    expect(mockReplace).toHaveBeenCalledWith("/overview");
  });

  it("does not auto-submit recovery codes and stores only a low-code notice after success", async () => {
    const user = userEvent.setup();
    const recoveryCode = "CCHIS-AAAA-BBBB-CCCC";
    mockVerifyTwoFactor.mockResolvedValue(
      buildVerifyResponse({
        second_factor_method: "recovery_code",
        recovery_codes_low: true,
        recovery_codes_remaining: 1,
      }),
    );
    renderVerifyPage();

    await user.click(screen.getByRole("button", { name: "Recovery code" }));
    await user.type(screen.getByLabelText("Authenticator or recovery code"), recoveryCode);

    expect(mockVerifyTwoFactor).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Use Recovery Code" }));

    await waitFor(() => {
      expect(mockVerifyTwoFactor).toHaveBeenCalledWith(recoveryCode);
    });
    expect(window.sessionStorage.getItem("cchis.recovery_code_login_notice")).toContain('"remaining_count":1');
    expect(window.sessionStorage.getItem("cchis.recovery_code_login_notice")).not.toContain(recoveryCode);
    expect(mockReplace).toHaveBeenCalledWith("/overview");
  });
});
