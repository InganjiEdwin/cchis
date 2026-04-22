import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ResetPasswordPage from "@/app/reset-password/page";

const mockReplace = vi.fn();
const mockValidatePasswordResetToken = vi.fn();
const mockConfirmPasswordReset = vi.fn();
const mockUseSearchParams = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: mockReplace,
  }),
  useSearchParams: () => mockUseSearchParams(),
}));

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) =>
    React.createElement("a", { href, ...props }, children),
}));

vi.mock("@/lib/auth", async () => {
  const actual = await vi.importActual<typeof import("@/lib/auth")>("@/lib/auth");
  return {
    ...actual,
    validatePasswordResetToken: (...args: unknown[]) => mockValidatePasswordResetToken(...args),
    confirmPasswordReset: (...args: unknown[]) => mockConfirmPasswordReset(...args),
  };
});

describe("ResetPasswordPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseSearchParams.mockReturnValue(new URLSearchParams("token=valid-token-123"));
    mockValidatePasswordResetToken.mockResolvedValue({ valid: true, detail: "Reset token is valid." });
  });

  it("validates the reset token from the URL before showing the form", async () => {
    render(React.createElement(ResetPasswordPage));

    await waitFor(() => {
      expect(mockValidatePasswordResetToken).toHaveBeenCalledWith("valid-token-123");
    });

    expect(await screen.findByLabelText("New Password")).toBeInTheDocument();
  });

  it("submits the new password to the backend confirm helper", async () => {
    const user = userEvent.setup();
    mockConfirmPasswordReset.mockResolvedValue({ detail: "Password reset successfully." });

    render(React.createElement(ResetPasswordPage));

    await screen.findByLabelText("New Password");
    await user.type(screen.getByLabelText("New Password"), "ResetStrongPass123!");
    await user.type(screen.getByLabelText("Confirm Password"), "ResetStrongPass123!");
    await user.click(screen.getByRole("button", { name: /update password/i }));

    await waitFor(() => {
      expect(mockConfirmPasswordReset).toHaveBeenCalledWith("valid-token-123", "ResetStrongPass123!");
    });
  });

  it("shows an invalid-link state when the backend rejects the token", async () => {
    mockValidatePasswordResetToken.mockRejectedValue(new Error("Invalid or expired reset token."));

    render(React.createElement(ResetPasswordPage));

    expect(await screen.findByText("Reset Link Unavailable")).toBeInTheDocument();
    expect(await screen.findByText("Invalid or expired reset token.")).toBeInTheDocument();
  });
});
