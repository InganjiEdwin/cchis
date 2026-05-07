import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SetupTwoFactorPage from "@/app/setup-2fa/page";
import type { CurrentUser } from "@/lib/auth";

const mockBeginTwoFactorEnrollment = vi.fn();
const mockClearPendingEnrollment = vi.fn();
const mockConfirmTwoFactorEnrollment = vi.fn();
const mockClipboardWriteText = vi.fn();
const mockGetDefaultRoute = vi.fn();
const mockReplace = vi.fn();
const mockRouter = { replace: mockReplace };
const mockUseAuth = vi.fn();

const recoveryCodes = ["CCHIS-7K3P-Q9V2", "CCHIS-A8MX-R2TT"];

vi.mock("next/navigation", () => ({
  useRouter: () => mockRouter,
}));

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) =>
    React.createElement("a", { href, ...props }, children),
}));

vi.mock("qrcode.react", () => ({
  QRCodeSVG: ({ value }: { value: string }) =>
    React.createElement("svg", { "aria-label": "QR code", role: "img" }, React.createElement("title", null, value)),
}));

vi.mock("@/components/auth-provider", () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock("@/lib/navigation", () => ({
  buildPolicyReviewRoute: (returnTo: string) => `/policy-review?returnTo=${encodeURIComponent(returnTo)}`,
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
    two_factor_policy: "REQUIRED",
    is_totp_enabled: false,
    is_active: true,
    ...overrides,
  };
}

function renderSetupPage() {
  Object.defineProperty(navigator, "clipboard", {
    value: {
      writeText: mockClipboardWriteText,
    },
    configurable: true,
  });

  mockUseAuth.mockReturnValue({
    beginTwoFactorEnrollment: mockBeginTwoFactorEnrollment,
    clearPendingEnrollment: mockClearPendingEnrollment,
    confirmTwoFactorEnrollment: mockConfirmTwoFactorEnrollment,
    currentUser: buildUser(),
    isAuthenticated: true,
    isHydrating: false,
    pendingEnrollment: null,
  });

  render(React.createElement(SetupTwoFactorPage));
}

async function finishTotpSetup(user: ReturnType<typeof userEvent.setup>) {
  await waitFor(() => {
    expect(mockBeginTwoFactorEnrollment).toHaveBeenCalled();
    expect(screen.getByText("Policy: REQUIRED")).toBeInTheDocument();
  });
  await user.type(screen.getByLabelText("Verification code"), "123456");
  await user.click(screen.getByRole("button", { name: /finish two-factor setup/i }));
  await screen.findByText("Save your recovery codes");
}

describe("SetupTwoFactorPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    mockBeginTwoFactorEnrollment.mockImplementation(async () => ({
      manual_entry_key: "JBSWY3DPEHPK3PXP",
      provisioning_uri: "otpauth://totp/CCHIS:admin?secret=JBSWY3DPEHPK3PXP",
      account_name: "admin",
      issuer: "CCHIS",
      two_factor_policy: "REQUIRED",
      is_totp_enabled: false,
    }));
    mockConfirmTwoFactorEnrollment.mockResolvedValue({
      detail: "Two-factor enrollment completed successfully.",
      user: buildUser({ is_totp_enabled: true }),
      enrollment_completed: true,
      recovery_codes: recoveryCodes,
      recovery_codes_generated: true,
    });
    mockGetDefaultRoute.mockReturnValue("/overview");
    mockClipboardWriteText.mockResolvedValue(undefined);
    Object.defineProperty(window.URL, "createObjectURL", {
      value: vi.fn(() => "blob:recovery-codes"),
      configurable: true,
    });
    Object.defineProperty(window.URL, "revokeObjectURL", {
      value: vi.fn(),
      configurable: true,
    });
    Object.defineProperty(window, "print", {
      value: vi.fn(),
      configurable: true,
    });
  });

  it("requires explicit recovery-code acknowledgement before routing to the dashboard", async () => {
    const user = userEvent.setup();
    renderSetupPage();

    await finishTotpSetup(user);

    for (const recoveryCode of recoveryCodes) {
      expect(screen.getByText(recoveryCode)).toBeInTheDocument();
    }
    expect(screen.getByText(/Each code works once/i)).toBeInTheDocument();
    expect(screen.getByText(/will not be shown again/i)).toBeInTheDocument();

    const continueButton = screen.getByRole("button", { name: "Continue" });
    expect(continueButton).toBeDisabled();

    await user.click(screen.getByRole("button", { name: /copy codes/i }));

    expect(mockClipboardWriteText).toHaveBeenCalledWith(recoveryCodes.join("\n"));
    expect(screen.getByText("Copied")).toBeInTheDocument();
    expect(continueButton).toBeDisabled();

    await user.click(screen.getByRole("checkbox", { name: /I have saved these recovery codes/i }));

    expect(continueButton).toBeEnabled();
    await user.click(continueButton);

    expect(mockGetDefaultRoute).toHaveBeenCalledWith("ADMIN");
    expect(mockReplace).toHaveBeenCalledWith("/overview");
  });

  it("offers download and print actions without bypassing acknowledgement or browser-storing codes", async () => {
    const user = userEvent.setup();
    const anchorClickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    const storageSetItemSpy = vi.spyOn(Storage.prototype, "setItem");
    renderSetupPage();

    await finishTotpSetup(user);

    const continueButton = screen.getByRole("button", { name: "Continue" });
    await user.click(screen.getByRole("button", { name: /download codes/i }));
    await user.click(screen.getByRole("button", { name: /print codes/i }));

    expect(window.URL.createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
    expect(anchorClickSpy).toHaveBeenCalled();
    expect(window.URL.revokeObjectURL).toHaveBeenCalledWith("blob:recovery-codes");
    expect(window.print).toHaveBeenCalled();
    expect(continueButton).toBeDisabled();

    await waitFor(() => {
      expect(storageSetItemSpy).not.toHaveBeenCalledWith(expect.any(String), expect.stringContaining(recoveryCodes[0]));
    });
  });

  it("routes completed login enrollment with missing policy acceptance to policy review", async () => {
    const user = userEvent.setup();
    mockConfirmTwoFactorEnrollment.mockResolvedValue({
      detail: "Two-factor enrollment completed successfully.",
      user: buildUser({
        is_totp_enabled: true,
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
      enrollment_completed: true,
      recovery_codes: [],
      recovery_codes_generated: false,
    });
    renderSetupPage();

    await waitFor(() => {
      expect(screen.getByText("Policy: REQUIRED")).toBeInTheDocument();
    });
    await user.type(screen.getByLabelText("Verification code"), "123456");
    await user.click(screen.getByRole("button", { name: /finish two-factor setup/i }));

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith("/policy-review?returnTo=%2Foverview");
    });
  });
});
